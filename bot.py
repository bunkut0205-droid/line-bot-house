import os
import pandas as pd
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 1. 從環境變數讀取金鑰 (請確認已在 Render 後台設定 LINE 與 OpenAI 變數)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 2. 預先載入資料庫 (林口與龜山 CSV 檔案)
csv_files = ["(林口) 大家房屋_46頁.csv", "(龜山) 大家房屋_102頁全集.csv"]
data_frames = []

for file in csv_files:
    if os.path.exists(file):
        try:
            # 優先使用 utf-8 讀取，並移除全空列以加速搜尋
            df = pd.read_csv(file).dropna(how='all')
            data_frames.append(df)
            print(f"✅ 成功載入檔案: {file}")
        except:
            # 備用讀取方案 (針對 Big5/CP950 編碼)
            df = pd.read_csv(file, encoding='cp950').dropna(how='all')
            data_frames.append(df)
    else:
        print(f"❌ 找不到檔案: {file}")

# 合併所有房源資料 (例如你提到的 1480 筆)
all_df = pd.concat(data_frames, ignore_index=True) if data_frames else pd.DataFrame()

# --- 搜尋函式：優化房源呈現格式 ---
def search_csv(query):
    if all_df.empty:
        return "資料庫目前無房源資料。"
    
    # 彈性關鍵字搜尋：搜尋所有欄位是否包含使用者輸入的字眼
    query_str = str(query).strip()
    mask = all_df.apply(lambda x: x.astype(str).str.contains(query_str, case=False).any(), axis=1)
    results = all_df[mask]

    if not results.empty:
        output = "🔍 為您搜尋到以下精選物件：\n\n"
        # 僅取前 3 筆，避免字數過多導致 LINE 傳送失敗或 Timeout
        for _, row in results.head(3).iterrows():
            output += f"🏠 物件：{row.get('標題', '精選物件')}\n"
            output += f"💰 價格：{row.get('價格', '請洽詢')}\n"
            output += f"📏 坪數：{row.get('坪數', '不詳')} | 樓層：{row.get('樓層', '不詳')}\n"
            output += f"🔗 連結：{row.get('照片連結', '無')}\n"
            output += "----------------\n"
        return output
    return "在 CSV 資料庫中暫無直接匹配的房源。"

# --- AI 對話函式：強制台灣不動產法律與稅務規範 ---
def ask_gpt(user_msg):
    # 先從 CSV 抓取相關房源
    csv_context = search_csv(user_msg)
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    # 【核心指令】：強制限定台灣地區法律、稅費、與實務慣例
    system_prompt = f"""
    你現在是一名「中華民國（台灣）專業不動產經紀人與稅務顧問」。
    
    ⚠️ 法律與區域鎖定規則：
    1. 區域限定：所有回覆必須嚴格遵循「台灣」的法律、稅務及不動產實務規範。
    2. 禁止使用非台灣術語：嚴禁使用「平米、產權證、印花稅稅率標準(非台版)」等。必須使用「坪數、權狀、公設比、履約保證」等台灣慣用語。
    
    【台灣不動產核心知識庫】：
    - 賣方稅費：房地合一稅 2.0 (持有2年內45%、2-5年35%、5-10年20%、10年以上15%)。土地增值稅(倍數累進)。
    - 買方稅費：契稅(核定契價6%)、印花稅、登記規費、代書費、履保規費。
    - 坪數換算：1 坪 = 3.3058 平方公尺。
    - 實務法律：平均地權條例(禁轉售限制)、不動產經紀業管理條例、央行限貸令規範。

    【目前資料庫房源搜尋結果】：
    {csv_context}

    回覆要求：
    1. 價格、坪數、樓層必須「分行顯示」，內容要整齊、親切。
    2. 優先推薦搜尋結果中的房源。若無房源，請根據台灣市場給予專業建議。
    """

    try:
        # 使用 gpt-4o-mini 以獲得最快的反應速度，避免 LINE Timeout
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.2, # 降低溫度以確保稅務計算與法律資訊穩定
            timeout=25
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return "抱歉，目前台灣不動產資料庫連線稍微繁忙，請您稍後再問一次。"

# --- LINE Webhook 入口處 (解決 404 關鍵) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 處理 LINE 訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    # 呼叫 AI 取得回覆
    reply_msg = ask_gpt(user_msg)
    # 將結果傳回給 LINE 使用者
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run()

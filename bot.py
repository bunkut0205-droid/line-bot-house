import os
import pandas as pd
import google.generativeai as genai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 1. 設定環境變數 (請確保 Render 已設定 GEMINI_API_KEY)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 設定 Google Gemini API
genai.configure(api_key=GEMINI_API_KEY)
# 使用 gemini-1.5-flash 模型，反應速度最快，解決 Timeout 問題
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# 2. 載入房源資料庫 (林口與龜山)
csv_files = ["(林口) 大家房屋_46頁.csv", "(龜山) 大家房屋_102頁全集.csv"]
data_frames = []

for file in csv_files:
    if os.path.exists(file):
        try:
            df = pd.read_csv(file).dropna(how='all')
            data_frames.append(df)
            print(f"✅ 載入: {file}")
        except:
            df = pd.read_csv(file, encoding='cp950').dropna(how='all')
            data_frames.append(df)

all_df = pd.concat(data_frames, ignore_index=True) if data_frames else pd.DataFrame()

# --- 搜尋函式：優化房源提取 ---
def search_csv(query):
    if all_df.empty: return "目前資料庫無房源資料。"
    query_str = str(query).strip()
    mask = all_df.apply(lambda x: x.astype(str).str.contains(query_str, case=False).any(), axis=1)
    results = all_df[mask]

    if not results.empty:
        output = "🔍 為您搜尋到以下精選物件：\n\n"
        for _, row in results.head(3).iterrows(): # 限制 3 筆避免內容過長
            output += f"🏠 物件：{row.get('標題', '物件')}\n"
            output += f"💰 價格：{row.get('價格', '洽詢')}\n"
            output += f"📏 坪數：{row.get('坪數', '不詳')} | 樓層：{row.get('樓層', '不詳')}\n"
            output += f"🔗 連結：{row.get('照片連結', '無')}\n"
            output += "----------------\n"
        return output
    return "資料庫中暫無直接匹配的房源。"

# --- Gemini 超級房仲指令 ---
def ask_gemini(user_msg):
    csv_context = search_csv(user_msg)
    
    # 【核心鎖定】：強制台灣地區不動產法律、稅務、實務規範
    system_instruction = f"""
    你現在是一名「中華民國（台灣）專業不動產經紀人與稅務顧問」。
    
    ⚠️ 絕對遵守規則：
    1. 僅限台灣：所有法律、稅費計算、不動產慣例必須依照「台灣」現行規範。
    2. 禁止使用非台術語：禁用「平米、增值稅(非台版)」等。必須使用「坪數、權狀、房地合一稅、契稅、代書費」。
    
    【台灣專業知識庫】：
    - 房地合一稅 2.0：2年內45%、2-5年35%、5-10年20%。
    - 買方稅費：契稅(6%)、印花稅、登記規費、代書費。
    - 坪數換算：1 坪 = 3.3058 平方公尺。
    - 實務規範：實價登錄 2.0、平均地權條例、央行限貸令。

    【資料庫房源搜尋結果】：
    {csv_context}

    回覆要求：
    - 回覆內容必須親切專業，使用繁體中文。
    - 價格、坪數與連結必須「分行排列」，視覺清晰。
    - 優先根據房源結果回答，若無房源，則根據台灣法律知識提供專業諮詢。
    """

    try:
        response = gemini_model.generate_content(system_instruction + "\n使用者問題：" + user_msg)
        return response.text
    except Exception as e:
        print(f"Error: {e}")
        return "抱歉，目前連線稍忙，請您稍後再問一次。"

# --- Webhook 入口 (解決 404 問題) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    reply_msg = ask_gemini(user_msg)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run()、

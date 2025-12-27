import os
import pandas as pd
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 1. 讀取環境變數 (請確認 Render 後台已填寫)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 2. 載入 CSV 資料 (包含您提到的林口與龜山檔案)
csv_files = ["(林口) 大家房屋_46頁.csv", "(龜山) 大家房屋_102頁全集.csv"]
data_frames = []

for file in csv_files:
    if os.path.exists(file):
        try:
            # 強制使用 utf-8 讀取，避免亂碼
            df = pd.read_csv(file)
            data_frames.append(df)
            print(f"✅ 成功載入檔案: {file}")
        except:
            # 備用讀取方案 (針對 Big5 編碼)
            df = pd.read_csv(file, encoding='cp950')
            data_frames.append(df)
    else:
        print(f"❌ 找不到檔案: {file}")

all_df = pd.concat(data_frames, ignore_index=True) if data_frames else pd.DataFrame()

# --- 搜尋函式：強化關鍵字對齊 ---
def search_csv(query):
    if all_df.empty: return "資料庫目前是空的。"
    
    # 將使用者輸入拆開，例如「林口 2000萬」會拆成兩個字搜尋
    keywords = query.split()
    results = all_df.copy()
    
    for word in keywords:
        mask = results.apply(lambda x: x.astype(str).str.contains(word, case=False).any(), axis=1)
        results = results[mask]

    if not results.empty:
        output = ""
        for _, row in results.head(5).iterrows():
            output += f"🏠 物件：{row.get('標題', '無標題')}\n"
            output += f"💰 價格：{row.get('價格', '不詳')}\n"
            output += f"📏 坪數：{row.get('坪數', '不詳')} | 樓層：{row.get('樓層', '不詳')}\n"
            output += f"🔗 連結：{row.get('照片連結', '請洽房仲')}\n"
            output += "----------------\n"
        return output
    return "在 CSV 資料庫中找不到直接匹配的房源。"

# --- AI 對話函式：強制台灣法規 ---
def ask_gpt(user_msg):
    csv_context = search_csv(user_msg)
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    # 強調台灣法律地位
    system_prompt = f"""
    你現在是一名「台灣專業不動產經紀人」，只熟悉中華民國（台灣）的法律與稅務。
    
    原則：
    1. 稅務回答：必須根據「台灣房地合一稅 2.0」、「土地增值稅」、「契稅」等台灣現行法律。
    2. 房源建議：優先使用下方的【搜尋結果】。
    3. 如果搜尋結果沒有合適物件，請告訴客戶你會幫他持續追蹤，並根據台灣市場給予專業建議。

    【搜尋結果內容】：
    {csv_context}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 建議使用 4o 模型，對台灣法規理解更精準
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 服務暫時繁忙，請稍後。錯誤：{e}"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    reply_msg = ask_gpt(user_msg)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run()

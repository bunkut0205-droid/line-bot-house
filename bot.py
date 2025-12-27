import os
import pandas as pd
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 1. 從環境變數讀取金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 2. 載入 CSV 資料 (請確保 GitHub 上有這些檔案)
csv_files = [
    "(林口) 大家房屋_46頁.csv",
    "(龜山) 大家房屋_102頁全集.csv"
]

data_frames = []
for file in csv_files:
    try:
        df = pd.read_csv(file)
        data_frames.append(df)
        print(f"✅ 成功讀取: {file}")
    except Exception as e:
        print(f"❌ 無法讀取 {file}: {e}")

if data_frames:
    all_df = pd.concat(data_frames, ignore_index=True)
    print(f"🎉 資料合併完成！總共有 {len(all_df)} 筆房源。")
else:
    all_df = pd.DataFrame()

# --- 搜尋函式：優化欄位呈現 ---
def search_csv(query):
    if all_df.empty:
        return "目前資料庫無資料。"
    
    # 簡單關鍵字搜尋
    mask = all_df.apply(lambda x: x.astype(str).str.contains(query, case=False).any(), axis=1)
    results = all_df[mask]

    if not results.empty:
        formatted_results = ""
        # 僅取前 3 筆，避免字數過多導致 LINE 無法傳送
        for _, row in results.head(3).iterrows():
            formatted_results += f"🏠 物件：{row.get('標題', '無標題')}\n"
            formatted_results += f"💰 價格：{row.get('價格', '不詳')}\n"
            formatted_results += f"📏 坪數：{row.get('坪數', '不詳')} | 樓層：{row.get('樓層', '不詳')}\n"
            formatted_results += f"🔗 連結：{row.get('照片連結', '無連結')}\n"
            formatted_results += "----------------\n"
        return formatted_results
    else:
        return "資料庫中沒有找到符合條件的物件。"

# --- AI 對話函式 ---
def ask_gpt(user_msg):
    csv_context = search_csv(user_msg)
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    system_prompt = f"""
    你是一個專業的房地產房仲助手。
    請根據以下資料庫內容回答客戶，若資料庫沒找到，請改用你的專業知識提供建議。
    請用條列式回覆，確保價格、坪數、樓層分行顯示，保持整潔。

    【資料庫搜尋結果】：
    {csv_context}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"腦袋打結了...原因：{e}"

# --- LINE Webhook 入口 ---
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

import os
import pandas as pd
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==========================================
# 🔑 設定區
# ==========================================
# 1. LINE 的鑰匙 (填入你自己的)
LINE_CHANNEL_ACCESS_TOKEN = '你的_Channel_Access_Token_貼在這裡'
LINE_CHANNEL_SECRET = '你的_Channel_Secret_貼在這裡'

# 2. OpenAI 的鑰匙 (讀取環境變數，最安全！)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
# ==========================================

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# 3. 讀取房源資料庫 (讀取林口 + 龜山)
# ⚠️ 這裡的檔名必須跟你在 GitHub 上傳的一模一樣，一個字都不能錯喔！
csv_files = [
    "（林口）大家房屋_46頁.csv",
    "（龜山）大家房屋_102頁全集.csv"
]

data_frames = []
for file in csv_files:
    try:
        # 讀取檔案
        d = pd.read_csv(file)
        data_frames.append(d)
        print(f"✅ 成功讀取：{file}")
    except Exception as e:
        print(f"❌ 讀取失敗：{file}，原因：{e}")

# 把兩個檔案合併成一個大表格
if data_frames:
    df = pd.concat(data_frames, ignore_index=True)
    print(f"🎉 資料庫合併完成！總共有 {len(df)} 筆房源資料。")
else:
    df = pd.DataFrame()
    print("⚠️ 警告：沒有讀到任何資料，機器人無法查詢房價。")

# --- 搜尋函式 ---
def search_csv(query):
    if df.empty:
        return ""
    
    # 簡單關鍵字搜尋
    mask = df.apply(lambda x: x.astype(str).str.contains(query, case=False).any(), axis=1)
    results = df[mask]
    
    if not results.empty:
        # 取前 5 筆給 GPT 參考，包含標題、價格、連結
        preview = results[['標題', '價格', '照片連結']].head(5).to_string(index=False)
        return f"【資料庫裡的房源】：\n{preview}\n"
    else:
        return ""

# --- GPT 回答函式 ---
def ask_gpt(user_msg):
    csv_context = search_csv(user_msg)
    
    system_prompt = f"""
    你是一個專業的房地產專家助手，熟悉林口與龜山地區。
    
    任務說明：
    1. 使用者若詢問「買房、找房、房價」，請優先參考下方的【資料庫裡的房源】回答。
    2. 若資料庫有資料，請務必提供「照片連結」並做簡單推銷。
    3. 若資料庫沒資料，或使用者問的是「稅務、法規」，請用你的專業知識回答。
    4. 回答要親切、像真人房仲。

    {csv_context}
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"腦袋打結了...原因：{e}"

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
    reply_text = ask_gpt(user_msg)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()

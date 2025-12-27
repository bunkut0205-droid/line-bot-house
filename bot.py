import os
import pandas as pd
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==========================================
# 🔑 設定區 (請填入你的鑰匙)
# ==========================================
# 1. LINE 的鑰匙 (跟之前一樣)
LINE_CHANNEL_ACCESS_TOKEN = 'ZNf1zr09AOQsNpqL1dmajBNOXx52c5AuQDw5+Y6A/H5osRtxWxWoAPRxdd7k9ypRq18bidItKDODc90Q3XRrZeJeUs8gU4ZKNIVZVFV8QSLATT4/SMDgZKW1CWEyQ+Hi6eLPAeF6fZ8SLZDR9wdP4gdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '684221841c454f53ae943093133e6b7b'

# 2. OpenAI 的鑰匙 (去 OpenAI 官網申請 sk-... 開頭的)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
# ==========================================

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# 3. 讀取房源資料庫
# ⚠️ 請確認這個檔名跟你上傳到 GitHub 的 CSV 檔名一模一樣！
CSV_FILENAME = "大家房屋_林口_完美版.csv" 

try:
    # 嘗試讀取 CSV
    df = pd.read_csv(CSV_FILENAME)
    print("✅ 成功讀取房源資料庫！")
except:
    print("❌ 找不到 CSV 檔案！請確認檔案有上傳到 GitHub 且檔名正確。")
    df = pd.DataFrame() # 建立空表格避免當機

# --- 搜尋函式 ---
def search_csv(query):
    if df.empty:
        return ""
    
    # 簡單關鍵字搜尋 (把所有欄位轉成文字來搜)
    mask = df.apply(lambda x: x.astype(str).str.contains(query, case=False).any(), axis=1)
    results = df[mask]
    
    # 如果有找到，取前 5 筆給 GPT 參考
    if not results.empty:
        # 只取重要的欄位給 GPT 看，節省字數
        preview = results[['標題', '價格', '照片連結']].head(5).to_string(index=False)
        return f"【資料庫裡的房源】：\n{preview}\n"
    else:
        return ""

# --- GPT 回答函式 ---
def ask_gpt(user_msg):
    # 1. 先去 CSV 找房子
    csv_context = search_csv(user_msg)
    
    # 2. 組合指令 (Prompt)
    system_prompt = f"""
    你是一個專業、親切的房地產專家助手。
    
    任務說明：
    1. 使用者若詢問「買房、找房、房價」，請優先參考下方的【資料庫裡的房源】回答。
    2. 若資料庫有資料，請務必把「照片連結」附給使用者，並簡單介紹。
    3. 若資料庫沒資料，或使用者問的是「稅務、法規、流程」，請用你原本的知識回答。
    4. 回答要口語化，不要像機器人。

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
    print(f"收到訊息: {user_msg}")
    
    # 呼叫 GPT 思考回覆
    reply_text = ask_gpt(user_msg)
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()

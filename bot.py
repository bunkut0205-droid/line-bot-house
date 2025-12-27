from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==========================================
# 🔑 這裡要換成你 LINE Developers 的鑰匙
# ==========================================
CHANNEL_ACCESS_TOKEN = '你的_Channel_Access_Token_貼在這裡'
CHANNEL_SECRET = '你的_Channel_Secret_貼在這裡'
# ==========================================

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

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
    msg = event.message.text
    # 學人精模式：目前先測試能不能回話
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"你說了：{msg}")
    )

if __name__ == "__main__":
    app.run()
# app.py
import threading
import time
import requests
from flask import Flask, jsonify

# --- تنظیمات ربات بله (از کد خودتان) ---
BALE_TOKEN = "720774043:sLMEly9opMeT-y_MUo3BvSMXPdaRCMNlox0"
# ... سایر تنظیمات ربات ...

# --- برنامه Flask برای Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# --- تابع اجرای ربات بله در پس‌زمینه ---
def run_bale_bot():
    # کد اصلی ربات بله را اینجا قرار دهید
    # (حلقه while True و منطق دریافت/ارسال پیام)
    print("Bale bot started in background thread...")
    while True:
        try:
            # ... منطق ربات شما ...
            time.sleep(1)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(5)

# --- شروع Thread هنگام بالا آمدن برنامه ---
# این کار باعث می‌شود ربات بله به محض اجرای Render شروع به کار کند
bot_thread = threading.Thread(target=run_bale_bot, daemon=True)
bot_thread.start()

# --- اجرای برنامه Flask (برای Gunicorn) ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

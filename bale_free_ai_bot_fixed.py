# -*- coding: utf-8 -*-
import os
import time
import threading
import requests
from flask import Flask, render_template, request, jsonify

# ==========================================
# بخش ۱: تنظیمات وب‌سایت (Flask)
# ==========================================
app = Flask(__name__)

# تنظیمات Pollinations (برای وب‌سایت)
POLLINATIONS_API_KEY = "sk_n4XyE1lrKefs6nOoZ8iAJLeJukcJ1PqT"
AI_URL = "https://gen.pollinations.ai/v1/chat/completions"
AI_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = "تو یک دستیار هوش مصنوعی فارسی‌زبان دقیق و خوش‌برخورد هستی. طبیعی جواب بده."

def ask_ai_api(messages):
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-12:],
        "max_tokens": 1000,
    }
    headers = {"Authorization": "Bearer " + POLLINATIONS_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(AI_URL, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

@app.route("/")
def index():
    return render_template("index.html") # فایل HTML شما باید در پوشه templates باشد

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "پیام خالی است"}), 400
    answer, error = ask_ai_api(messages)
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"reply": answer})


# ==========================================
# بخش ۲: تنظیمات ربات بله (در پس‌زمینه)
# ==========================================
BALE_TOKEN = "720774043:sLMEly9opMeT-y_MUo3BvSMXPdaRCMNlox0"
BALE_BASE_URL = "https://tapi.bale.ai/bot{}".format(BALE_TOKEN)
CHAT_HISTORY = {}

def send_bale_message(chat_id, text, reply_to_message_id=None):
    payload = {"chat_id": chat_id, "text": (text or "...")[:3900]}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(BALE_BASE_URL + "/sendMessage", json=payload, timeout=30)
    except Exception as e:
        print("Bale send error:", e)

def run_bale_bot():
    print("🤖 Bale bot started in background...")
    offset = 0
    while True:
        try:
            # دریافت پیام‌های جدید از بله
            response = requests.get(BALE_BASE_URL + "/getUpdates", params={"offset": offset, "timeout": 25}, timeout=35)
            response.raise_for_status()
            data = response.json()

            for update in data.get("result", []):
                if "update_id" in update:
                    offset = update["update_id"] + 1

                message = update.get("message")
                if not isinstance(message, dict): continue
                
                user_text = message.get("text")
                chat_id = message.get("chat", {}).get("id")
                message_id = message.get("message_id")
                
                if not user_text or chat_id is None: continue

                # مدیریت دستورات
                if user_text.strip().lower() in ("/start", "شروع"):
                    reply = "سلام! من ربات هوش مصنوعی هستم."
                elif user_text.strip().lower() in ("/clear", "/reset"):
                    CHAT_HISTORY.pop(chat_id, None)
                    reply = "حافظه پاک شد."
                else:
                    # دریافت پاسخ از هوش مصنوعی
                    history = CHAT_HISTORY.get(chat_id, [])
                    history.append({"role": "user", "content": user_text})
                    answer, error = ask_ai_api(history)
                    
                    if error:
                        reply = "خطا در ارتباط با هوش مصنوعی."
                    else:
                        reply = answer
                        history.append({"role": "assistant", "content": answer})
                        CHAT_HISTORY[chat_id] = history[-12:] # نگه داشتن ۱۲ پیام آخر

                send_bale_message(chat_id, reply, message_id)

        except Exception as e:
            print("Bale loop error:", e)
            time.sleep(5)

# اجرای ربات بله در یک Thread جداگانه (تا جلوی کار وب‌سایت را نگیرد)
threading.Thread(target=run_bale_bot, daemon=True).start()


# ==========================================
# بخش ۳: اجرای برنامه
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

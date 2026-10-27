# -*- coding: utf-8 -*-
import time
import threading
import requests
from flask import Flask

# ==========================================
# ۱. بخش وب‌سرویس (فقط برای اینکه Render رایگان قبول کنه)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bale Bot is running in the background!", 200

@app.route('/health')
def health():
    return "OK", 200


# ==========================================
# ۲. بخش ربات بله (کد کامل خودت)
# ==========================================
BALE_TOKEN = "720774043:sLMEly9opMeT-y_MUo3BvSMXPdaRCMNlox0"
POLLINATIONS_API_KEY = "sk_n4XyE1lrKefs6nOoZ8iAJLeJukcJ1PqT"

AI_URL = "https://gen.pollinations.ai/v1/chat/completions"
AI_MODEL = "openai/gpt-oss-20b"
BALE_BASE_URL = "https://tapi.bale.ai/bot{}".format(BALE_TOKEN)

CHAT_HISTORY = {}
MAX_HISTORY_MESSAGES = 12
MAX_REPLY_CHARS = 3900

SYSTEM_PROMPT = (
    "تو یک دستیار هوش مصنوعی فارسی‌زبان دقیق و خوش‌برخورد هستی. "
    "طبیعی و خودمانی جواب بده و زبان پیام کاربر را حفظ کن. "
    "برای مسائل چندمرحله‌ای، پاسخ را منظم و قابل‌فهم توضیح بده. "
    "برای کدنویسی، کد قابل اجرا و نکته‌های خطایابی بده. "
    "اگر مطمئن نیستی، حدس را به‌جای واقعیت بیان نکن. "
    "از زمینهٔ پیام‌های قبلی همین گفت‌وگو استفاده کن."
)

session = requests.Session()

def send_bale_message(chat_id, text, reply_to_message_id=None):
    payload = {"chat_id": chat_id, "text": (text or "پاسخی دریافت نشد.")[:MAX_REPLY_CHARS]}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        session.post(BALE_BASE_URL + "/sendMessage", json=payload, timeout=30)
    except Exception as exc:
        print("خطا در ارسال پیام به بله: {}".format(exc))

def get_provider_error(data):
    if not isinstance(data, dict): return ""
    error = data.get("error")
    if isinstance(error, dict): return str(error.get("message") or error.get("detail") or error)
    if error: return str(error)
    if data.get("message"): return str(data["message"])
    return ""

def ask_ai(chat_id, user_text):
    history = CHAT_HISTORY.get(chat_id, [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer {}".format(POLLINATIONS_API_KEY.strip()),
        "Content-Type": "application/json",
    }

    try:
        response = session.post(AI_URL, headers=headers, json=payload, timeout=90)
    except Exception as exc:
        print("AI connection error: {}".format(exc))
        return "اتصال به سرویس هوش مصنوعی برقرار نشد."

    try:
        data = response.json()
    except ValueError:
        data = None

    if not response.ok:
        print("Pollinations HTTP {}: {}".format(response.status_code, response.text[:500]))
        return "سرویس هوش مصنوعی خطا داد ({}).".format(response.status_code)

    if not isinstance(data, dict):
        return "پاسخ سرویس JSON نبود."

    provider_error = get_provider_error(data)
    if provider_error and not data.get("choices"):
        return "سرویس هوش مصنوعی خطا داد: {}".format(provider_error[:220])

    try:
        answer = data["choices"][0]["message"]["content"]
        if isinstance(answer, list):
            answer = "\n".join([part["text"] for part in answer if isinstance(part, dict)])
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("empty")
        answer = answer.strip()
    except Exception:
        return "قالب پاسخ سرویس سازگار نیست."

    updated = history + [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]
    CHAT_HISTORY[chat_id] = updated[-MAX_HISTORY_MESSAGES:]
    return answer

def run_bale_bot():
    """این تابع در پس‌زمینه اجرا می‌شود و ربات را روشن نگه می‌دارد"""
    print("🚀 ربات بله در پس‌زمینه شروع به کار کرد...")
    offset = 0
    while True:
        try:
            response = session.get(
                BALE_BASE_URL + "/getUpdates",
                params={"offset": offset, "timeout": 25},
                timeout=35,
            )
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

                command = user_text.strip().lower()
                if command in ("/start", "شروع"):
                    reply = "سلام! 👋 من ربات هوش مصنوعی هستم. پیام بده تا گپ بزنیم.\n\nپاک‌کردن حافظه: /clear"
                elif command in ("/clear", "/reset"):
                    CHAT_HISTORY.pop(chat_id, None)
                    reply = "حافظهٔ همین گفت‌وگو پاک شد. از نو شروع کنیم!"
                else:
                    reply = ask_ai(chat_id, user_text)

                send_bale_message(chat_id, reply, message_id)

        except requests.exceptions.RequestException as exc:
            print("خطای ارتباط با بله: {}".format(exc))
            time.sleep(3)
        except Exception as exc:
            print("خطای غیرمنتظره در ربات: {}".format(exc))
            time.sleep(3)


# ==========================================
# ۳. اجرای همزمان وب‌سایت و ربات
# ==========================================
# یک Thread جدید برای ربات می‌سازیم تا در پس‌زمینه اجرا شود
bot_thread = threading.Thread(target=run_bale_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    # اجرای وب‌سایت (برای لوکال)
    app.run(host="0.0.0.0", port=5000)

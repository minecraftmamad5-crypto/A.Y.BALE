# -*- coding: utf-8 -*-
"""Bale chatbot using Pollinations' current OpenAI-compatible API.
Python 3.8+; dependency: requests.

Important: the old anonymous text.pollinations.ai/openai endpoint is legacy.
The current gen.pollinations.ai generation API requires a Pollinations API key.
Whether requests cost money depends on the chosen model and account balance.
"""

import time
import requests

# Paste your Bale bot token here. Keep it private.
BALE_TOKEN = "720774043:sLMEly9opMeT-y_MUo3BvSMXPdaRCMNlox0"

# Create a Pollinations key at https://enter.pollinations.ai/keys
# Keep it private; do not send it to anyone.
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

    response = session.post(
        BALE_BASE_URL + "/sendMessage", json=payload, timeout=30
    )
    response.raise_for_status()
    return response.json()


def get_provider_error(data):
    """Extract error messages from several common API error formats."""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or error)
    if error:
        return str(error)
    if data.get("message"):
        return str(data["message"])
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
    except requests.exceptions.Timeout:
        return "پاسخ‌گویی طول کشید؛ چند لحظه بعد دوباره امتحان کن."
    except requests.exceptions.RequestException as exc:
        print("AI connection error: {}".format(exc))
        return "اتصال به سرویس هوش مصنوعی برقرار نشد؛ اینترنت را بررسی کن."

    try:
        data = response.json()
    except ValueError:
        data = None

    if response.status_code == 401:
        print("Pollinations 401: {}".format(response.text[:700]))
        return "کلید Pollinations معتبر نیست یا ارسال نشده. کلید را در فایل بررسی کن."
    if response.status_code == 402:
        print("Pollinations 402: {}".format(response.text[:700]))
        return "اعتبار سرویس تمام شده یا برای این مدل اعتبار لازم است. موجودی حسابت را بررسی کن."
    if response.status_code == 403:
        print("Pollinations 403: {}".format(response.text[:700]))
        return "این کلید اجازهٔ استفاده از مدل را ندارد یا اعتبار کافی نیست. جزئیات را در CMD ببین."
    if response.status_code == 429:
        print("Pollinations 429: {}".format(response.text[:500]))
        return "تعداد درخواست‌ها زیاد شده؛ کمی بعد دوباره امتحان کن."
    if not response.ok:
        print("Pollinations HTTP {}: {}".format(response.status_code, response.text[:700]))
        message = get_provider_error(data) if data is not None else response.text[:250]
        return "سرویس هوش مصنوعی خطا داد ({}). جزئیات در پنجرهٔ CMD است.".format(response.status_code)

    if not isinstance(data, dict):
        print("Unexpected non-JSON response ({}): {}".format(
            response.headers.get("content-type"), response.text[:700]
        ))
        return "پاسخ سرویس JSON نبود. جزئیات را در CMD ببین."

    # New gateway may return structured JSON errors even when the status isn't expected.
    provider_error = get_provider_error(data)
    if provider_error and not data.get("choices"):
        print("Pollinations error response: {}".format(str(data)[:700]))
        return "سرویس هوش مصنوعی خطا داد: {}".format(provider_error[:220])

    try:
        choice = data["choices"][0]
        message = choice.get("message", {})
        answer = message.get("content", "")
        # Tolerate providers that return content as a list of text blocks.
        if isinstance(answer, list):
            parts = []
            for part in answer:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            answer = "\n".join(parts)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("empty assistant content")
        answer = answer.strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        print("Unexpected AI response format: {}".format(exc))
        print("Response content-type: {}".format(response.headers.get("content-type")))
        print("Response body: {}".format(response.text[:1000]))
        return "قالب پاسخ سرویس هنوز با کد سازگار نیست؛ جزئیات در CMD چاپ شده است."

    updated = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer},
    ]
    CHAT_HISTORY[chat_id] = updated[-MAX_HISTORY_MESSAGES:]
    return answer


def main():
    if "PASTE_YOUR_BALE_BOT_TOKEN_HERE" in BALE_TOKEN or not BALE_TOKEN.strip():
        print("ابتدا توکن ربات بله را در BALE_TOKEN وارد کن.")
        return
    if "PASTE_YOUR_POLLINATIONS_API_KEY_HERE" in POLLINATIONS_API_KEY or not POLLINATIONS_API_KEY.strip():
        print("ابتدا کلید Pollinations را از https://enter.pollinations.ai/keys بگیر و در POLLINATIONS_API_KEY وارد کن.")
        print("توجه: API جدید کلید می‌خواهد؛ رایگان‌بودن استفاده به مدل و اعتبار حسابت بستگی دارد.")
        return

    offset = 0
    print("ربات بله اجرا شد. برای توقف Ctrl+C را بزن.")
    print("AI endpoint: {} | Model: {}".format(AI_URL, AI_MODEL))

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
                if not isinstance(message, dict):
                    continue

                user_text = message.get("text")
                chat_id = message.get("chat", {}).get("id")
                message_id = message.get("message_id")
                if not user_text or chat_id is None:
                    continue

                command = user_text.strip().lower()
                if command in ("/start", "شروع"):
                    reply = (
                        "سلام! 👋 من ربات هوش مصنوعی هستم. پیام بده تا گپ بزنیم.\n\n"
                        "پاک‌کردن حافظهٔ همین چت: /clear"
                    )
                elif command in ("/clear", "/reset"):
                    CHAT_HISTORY.pop(chat_id, None)
                    reply = "حافظهٔ همین گفت‌وگو پاک شد. از نو شروع کنیم!"
                else:
                    reply = ask_ai(chat_id, user_text)

                try:
                    send_bale_message(chat_id, reply, message_id)
                except (requests.exceptions.RequestException, ValueError) as exc:
                    print("خطا در ارسال پیام به بله: {}".format(exc))

        except KeyboardInterrupt:
            print("\nربات متوقف شد.")
            break
        except (requests.exceptions.RequestException, ValueError) as exc:
            print("خطای ارتباط با بله: {}".format(exc))
            time.sleep(3)


if __name__ == "__main__":
    main()

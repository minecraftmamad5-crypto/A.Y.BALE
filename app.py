
# -*- coding: utf-8 -*-

import os
import time
import threading
import requests

from flask import Flask, jsonify, render_template_string

# ==========================================
# CONFIGURATION
# ==========================================

BALE_TOKEN = os.environ.get("BALE_TOKEN", "")
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

AI_URL = "https://gen.pollinations.ai/v1/chat/completions"
AI_MODEL = "openai/gpt-oss-20b"

BALE_BASE_URL = "https://tapi.bale.ai/bot{}".format(BALE_TOKEN)

MAX_HISTORY_MESSAGES = 12
MAX_REPLY_CHARS = 3900

CHAT_HISTORY = {}
session = requests.Session()

# ==========================================
# FLASK WEBSITE
# ==========================================

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EXPERA AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: #09090f;
            color: white;
            font-family: Tahoma, sans-serif;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .container {
            text-align: center;
            padding: 40px 25px;
            max-width: 550px;
            width: 90%;
            background: #15151f;
            border: 1px solid #292938;
            border-radius: 20px;
        }

        .logo {
            font-size: 42px;
            font-weight: bold;
            letter-spacing: 3px;
            color: #a78bfa;
            margin-bottom: 15px;
        }

        h1 {
            font-size: 25px;
            margin-bottom: 15px;
        }

        p {
            color: #a1a1aa;
            line-height: 2;
            font-size: 14px;
        }

        .status {
            display: inline-flex;
            align-items: center;
            gap: 9px;
            background: #17291f;
            color: #4ade80;
            padding: 10px 18px;
            border-radius: 30px;
            margin-top: 25px;
            font-size: 13px;
        }

        .dot {
            width: 8px;
            height: 8px;
            background: #4ade80;
            border-radius: 50%;
        }

        footer {
            margin-top: 35px;
            color: #666677;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">EXPERA</div>
        <h1>هوش مصنوعی اکسپرا</h1>
        <p>
            دستیار هوشمند شما در زمینه علوم تجربی،
            شیمی، فیزیک و آزمایش‌های علمی.
        </p>

        <div class="status">
            <span class="dot"></span>
            Website is running
        </div>

        <footer>
            POWERED BY EXPERA AI
        </footer>
    </div>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML_PAGE)


@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "website": "running",
        "bale_configured": bool(BALE_TOKEN),
        "ai_configured": bool(POLLINATIONS_API_KEY)
    })


# ==========================================
# BALE BOT
# ==========================================

SYSTEM_PROMPT = (
    "تو AY هستی؛ یک دستیار هوشمند، مهربان و خوش‌برخورد متخصص آزمایش‌های علمی و عناصر شیمیایی."
    "در زمینه‌های طراحی و توضیح آزمایش‌ها، عناصر شیمیایی، جدول تناوبی، ویژگی‌های عناصر، ابزارهای آزمایشگاهی و آزمایش‌های فیزیک، شیمی و زیست‌شناسی تخصص داری."
    "مانند یک معلم حرفه‌ای، هر آزمایشی را که دانش‌آموز نام می‌برد، از هدف و وسایل موردنیاز تا مراحل انجام، توضیح علمی، نتایج مورد انتظار و نکات ایمنی به‌صورت کامل، دقیق و مرحله‌به‌مرحله آموزش بده."
)


def send_bale_message(chat_id, text, reply_to_message_id=None):

    payload = {
        "chat_id": chat_id,
        "text": (text or "پاسخی دریافت نشد.")[:MAX_REPLY_CHARS]
    }

    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id

    response = session.post(
        BALE_BASE_URL + "/sendMessage",
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def get_provider_error(data):

    if not isinstance(data, dict):
        return ""

    error = data.get("error")

    if isinstance(error, dict):
        return str(
            error.get("message") or
            error.get("detail") or
            error
        )

    if error:
        return str(error)

    if data.get("message"):
        return str(data["message"])

    return ""


# ==========================================
# AI ENGINE
# ==========================================

def ask_ai(chat_id, user_text):

    history = CHAT_HISTORY.get(chat_id, [])

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_text
    })

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "stream": False
    }

    headers = {
        "Authorization": "Bearer {}".format(
            POLLINATIONS_API_KEY.strip()
        ),
        "Content-Type": "application/json"
    }

    try:

        response = session.post(
            AI_URL,
            headers=headers,
            json=payload,
            timeout=90
        )

    except requests.exceptions.Timeout:

        return "پاسخ‌گویی طول کشید؛ چند لحظه بعد دوباره امتحان کن."

    except requests.exceptions.RequestException as exc:

        print("AI connection error:", exc)

        return "اتصال به سرویس هوش مصنوعی برقرار نشد."

    try:
        data = response.json()
    except ValueError:
        data = None

    if response.status_code == 401:
        print("Pollinations 401:", response.text[:700])
        return "کلید Pollinations معتبر نیست."

    if response.status_code == 402:
        print("Pollinations 402:", response.text[:700])
        return "اعتبار سرویس هوش مصنوعی کافی نیست."

    if response.status_code == 403:
        print("Pollinations 403:", response.text[:700])
        return "دسترسی به این مدل امکان‌پذیر نیست."

    if response.status_code == 429:
        print("Pollinations 429:", response.text[:500])
        return "تعداد درخواست‌ها زیاد شده؛ کمی بعد امتحان کن."

    if not response.ok:

        print(
            "Pollinations HTTP {}: {}".format(
                response.status_code,
                response.text[:700]
            )
        )

        return "سرویس هوش مصنوعی خطا داد."

    if not isinstance(data, dict):
        return "پاسخ سرویس هوش مصنوعی معتبر نیست."

    provider_error = get_provider_error(data)

    if provider_error and not data.get("choices"):

        print("Provider error:", provider_error)

        return "خطای هوش مصنوعی: " + provider_error[:200]

    try:

        choice = data["choices"][0]

        message = choice.get("message", {})

        answer = message.get("content", "")

        if isinstance(answer, list):

            parts = []

            for part in answer:

                if isinstance(part, dict):

                    if isinstance(part.get("text"), str):
                        parts.append(part["text"])

            answer = "\n".join(parts)

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty response")

        answer = answer.strip()

    except (KeyError, IndexError, TypeError, ValueError) as exc:

        print("Unexpected AI response:", exc)
        print(response.text[:1000])

        return "خطا در دریافت پاسخ هوش مصنوعی."

    updated = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer}
    ]

    CHAT_HISTORY[chat_id] = updated[-MAX_HISTORY_MESSAGES:]

    return answer


# ==========================================
# BALE POLLING ENGINE
# ==========================================

def bot_loop():

    if not BALE_TOKEN.strip() or not POLLINATIONS_API_KEY.strip():

        print("Bot disabled: API credentials are missing.")
        return

    offset = 0

    print("EXPERA Bale bot started.")
    print("AI Model:", AI_MODEL)

    while True:

        try:

            response = session.get(
                BALE_BASE_URL + "/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 25
                },
                timeout=35
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                time.sleep(3)
                continue

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
                        "سلام! 👋 من EXPERA هستم.\n"
                        "پیام بده تا با هم صحبت کنیم.\n\n"
                        "پاک‌کردن حافظه: /clear"
                    )

                elif command in ("/clear", "/reset"):

                    CHAT_HISTORY.pop(chat_id, None)

                    reply = "حافظه این گفت‌وگو پاک شد!"

                else:

                    reply = ask_ai(chat_id, user_text)

                try:

                    send_bale_message(
                        chat_id,
                        reply,
                        message_id
                    )

                except (
                    requests.exceptions.RequestException,
                    ValueError
                ) as exc:

                    print("Bale send error:", exc)

        except requests.exceptions.RequestException as exc:

            print("Bale connection error:", exc)
            time.sleep(3)

        except ValueError as exc:

            print("Bale JSON error:", exc)
            time.sleep(3)

        except Exception as exc:

            print("Unexpected bot error:", exc)
            time.sleep(3)


# ==========================================
# START BACKGROUND BOT
# ==========================================

bot_thread = threading.Thread(
    target=bot_loop,
    name="EXPERA-Bale-Bot",
    daemon=True
)

bot_thread.start()


# Gunicorn imports app:app

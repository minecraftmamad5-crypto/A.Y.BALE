# EXPERA AI
# -*- coding: utf-8 -*-
"""Bale AI bot with provider fallback; Python 3.8+; requires requests.

Priority: OpenAI -> Google Gemini -> DeepSeek -> Groq -> Pollinations.

Important:
- Add your Bale bot token and the API keys below before starting.
- Keep this file private after entering credentials.
- A 402/429 does not rotate to another key of the same provider; the bot
  moves to the next provider instead.
- Model IDs, quotas, API access, and prices can change by provider/account.
"""

import json
import os
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

import requests

# ============================================================
# 1) CONFIGURATION — fill in your own credentials
# ============================================================

BALE_TOKEN = "1157091941:-miCjSd7USzF3IPvvcpU8oukRtTISoKM3SU"

# Use each provider's own API keys only in its matching section.
# Additional keys are tried only when a credential returns 401/403,
# never to bypass a 402/429 quota or rate limit.
OPENAI_KEYS = [
    "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",
]

GEMINI_KEYS = [
    "AQ.Ab8RN6KJypJqgCm3GtYMZC93dbBo725m_mq_ZkZtenFRnKFMIQ",
    "AQ.Ab8RN6IJJyiyF0jkg5fYkEN-_kODYt83N4ITpJJcnSggHn8T_g",
]

DEEPSEEK_KEYS = [
    "sk-8f19e917cc67474b984f0a787a9c9890",
    "sk-10eb1a3b9afc44e281a2ef79a1c5d041",
    "sk-03efbb0bbaf04e62adb31093fafadbf3",
]

GROQ_KEYS = [
    "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",
]

POLLINATIONS_KEYS = [
    "sk_n4XyE1lrKefs6nOoZ8iAJLeJukcJ1PqT",
    "sk_Jg9NXZNON3etsZRiULoYJiyQtMjCbo6A",
    "sk_d15ho5s4GEpfwtLTeKLFBm8yoRmntOda",
]

# Low-latency general-purpose model choices. Check each provider's live catalog
# if a model is unavailable to your account.
PROVIDERS = [
    {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1/responses",
        "model": "gpt-6-luna",
        "kind": "responses",
        "keys": OPENAI_KEYS,
    },
    {
        "name": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.8-flash",
        "kind": "chat",
        "keys": GEMINI_KEYS,
        "extra_payload": {"reasoning_effort": "low"},
    },
    {
        "name": "DeepSeek",
        "url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-v4-flash",
        "kind": "chat",
        "keys": DEEPSEEK_KEYS,
        "extra_payload": {"thinking": {"type": "disabled"}},
    },
    {
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
        "kind": "chat",
        "keys": GROQ_KEYS,
        "token_param": "max_completion_tokens",
    },
    {
        "name": "Pollinations",
        "url": "https://gen.pollinations.ai/v1/chat/completions",
        "model": "openai/gpt-5.4-nano",
        "kind": "chat",
        "keys": POLLINATIONS_KEYS,
    },
]

SYSTEM_PROMPT = (
"تو EXPERA هستی؛ یک دستیار هوشمند، مهربان و خوش‌برخورد متخصص آزمایش‌های علمی و عناصر شیمیایی."
"در زمینه‌های طراحی و توضیح آزمایش‌ها، عناصر شیمیایی، جدول تناوبی، ویژگی‌های عناصر، ابزارهای آزمایشگاهی و آزمایش‌های فیزیک، شیمی و زیست‌شناسی تخصص داری."
"مانند یک معلم حرفه‌ای، هر آزمایشی را که دانش‌آموز نام می‌برد، از هدف و وسایل موردنیاز تا مراحل انجام، توضیح علمی، نتایج مورد انتظار و نکات ایمنی به‌صورت کامل، دقیق و مرحله‌به‌مرحله آموزش بده."
)

# Network/performance settings
CONNECT_TIMEOUT = 5
AI_READ_TIMEOUT = 22
BALE_POLL_TIMEOUT = 25
BALE_READ_TIMEOUT = 40
MAX_OUTPUT_TOKENS = 650
MAX_HISTORY_MESSAGES = 12       # user/assistant messages, not pairs
MAX_INPUT_CHARACTERS = 10000
BALE_TEXT_LIMIT = 3900           # safely below the usual message size limit
POLL_ERROR_SLEEP_MAX = 25

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OFFSET_FILE = os.path.join(SCRIPT_DIR, "bale_update_offset.txt")
PLACEHOLDER_PREFIX = "PASTE_"

# Separate sessions make concurrent use safer and keep HTTP connections alive.
_THREAD_LOCAL = threading.local()
_BALE_SESSION = requests.Session()
_CHAT_HISTORY: Dict[str, List[Dict[str, str]]] = {}
_HISTORY_LOCK = threading.RLock()


class BaleAPIError(Exception):
    pass


def _session() -> requests.Session:
    """Return a requests session for the current thread."""
    sess = getattr(_THREAD_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        _THREAD_LOCAL.session = sess
    return sess


def _configured_keys(provider: Dict[str, Any]) -> List[str]:
    """Return unique configured keys, ignoring untouched examples."""
    values = []
    seen = set()
    for value in provider.get("keys", []):
        key = (value or "").strip()
        if not key or key.startswith(PLACEHOLDER_PREFIX):
            continue
        if key not in seen:
            seen.add(key)
            values.append(key)
    return values


def _safe_error_text(response: requests.Response) -> str:
    """Read a short API error without logging credentials."""
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error", data)
            if isinstance(error, dict):
                message = error.get("message") or error.get("code")
                if message:
                    return str(message)[:250]
            if isinstance(error, str):
                return error[:250]
            description = data.get("description")
            if description:
                return str(description)[:250]
    except (ValueError, TypeError):
        pass
    return (response.text or "بدون توضیح خطا")[:250]


def _chat_messages(history: List[Dict[str, str]], user_text: str) -> List[Dict[str, str]]:
    messages = []
    if SYSTEM_PROMPT.strip():
        messages.append({"role": "system", "content": SYSTEM_PROMPT.strip()})
    for item in history[-MAX_HISTORY_MESSAGES:]:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content.strip()})
    messages.append({"role": "user", "content": user_text.strip()})
    return messages


def _extract_chat_answer(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts).strip()
    return ""


def _extract_responses_answer(data: Dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("output_text", "text"):
                text = part.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _call_provider(
    provider: Dict[str, Any], api_key: str, history: List[Dict[str, str]], user_text: str
) -> Tuple[Optional[str], int, str]:
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    all_messages = _chat_messages(history, user_text)
    if provider.get("kind") == "responses":
        # OpenAI's Responses API uses instructions and input instead of chat messages.
        input_messages = [
            {"role": item["role"], "content": item["content"]}
            for item in all_messages if item["role"] != "system"
        ]
        payload = {
            "model": provider["model"],
            "input": input_messages,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "store": False,
        }
        if SYSTEM_PROMPT.strip():
            payload["instructions"] = SYSTEM_PROMPT.strip()
    else:
        payload = {
            "model": provider["model"],
            "messages": all_messages,
            "stream": False,
            provider.get("token_param", "max_tokens"): MAX_OUTPUT_TOKENS,
        }
        payload.update(provider.get("extra_payload", {}))

    try:
        response = _session().post(
            provider["url"],
            headers=headers,
            json=payload,
            timeout=(CONNECT_TIMEOUT, AI_READ_TIMEOUT),
        )
    except requests.RequestException as exc:
        print("[WARN] {}: مشکل اتصال: {}".format(provider["name"], str(exc)[:180]))
        return None, 0, "network"

    status = response.status_code
    if status != 200:
        detail = _safe_error_text(response)
        print("[WARN] {} HTTP {}: {}".format(provider["name"], status, detail))
        if status in (401, 403):
            return None, status, "bad_key"
        if status in (402, 429):
            return None, status, "quota"
        if status >= 500:
            return None, status, "server"
        return None, status, "configuration"

    try:
        data = response.json()
    except ValueError:
        print("[WARN] {}: پاسخ JSON معتبر نبود.".format(provider["name"]))
        return None, status, "bad_json"

    if provider.get("kind") == "responses":
        answer = _extract_responses_answer(data)
    else:
        answer = _extract_chat_answer(data)

    if not answer:
        print("[WARN] {}: پاسخ خالی بود.".format(provider["name"]))
        return None, status, "empty"

    return answer, status, "ok"


def ask_ai(user_text: str, history: Optional[List[Dict[str, str]]] = None) -> Tuple[str, Optional[str]]:
    """Try configured providers in priority order. Returns (answer, provider name)."""
    user_text = (user_text or "").strip()
    if not user_text:
        return "لطفاً یک پیام بنویس.", None
    if len(user_text) > MAX_INPUT_CHARACTERS:
        user_text = user_text[:MAX_INPUT_CHARACTERS]

    if history is None:
        history = []

    any_keys = any(_configured_keys(provider) for provider in PROVIDERS)
    if not any_keys:
        return "هیچ کلید API تنظیم نشده است. کلیدها را بالای فایل وارد کن.", None

    for provider in PROVIDERS:
        keys = _configured_keys(provider)
        if not keys:
            continue

        skip_provider = False
        for number, api_key in enumerate(keys, start=1):
            answer, status, reason = _call_provider(provider, api_key, history, user_text)
            if reason == "ok" and answer:
                print("[OK] پاسخ از {} ({}) دریافت شد.".format(provider["name"], provider["model"]))
                return answer, provider["name"]

            if reason == "bad_key":
                # Only test another credential when this credential is rejected.
                # Do not rotate keys to get around a quota/rate limit.
                if number < len(keys):
                    print("[WARN] کلید {} از {} مجوز ندارد؛ کلید بعدی بررسی می‌شود.".format(
                        number, provider["name"]
                    ))
                    continue
                skip_provider = True
                break

            if reason == "quota":
                print("[INFO] محدودیت/اعتبار {}؛ رفتن به سرویس بعدی، بدون چرخاندن کلیدهای همین سرویس.".format(
                    provider["name"]
                ))
                skip_provider = True
                break

            # Network, server, model/config, or malformed responses: move on.
            skip_provider = True
            break

        if skip_provider:
            continue

    return (
        "متأسفانه هیچ‌کدام از سرویس‌های تنظیم‌شده پاسخ ندادند. "
        "اتصال اینترنت، کلیدها، دسترسی مدل‌ها و خطاهای پنجرهٔ IDLE را بررسی کن.",
        None,
    )


def _bale_request(method: str, payload: Optional[Dict[str, Any]] = None, read_timeout: int = 25) -> Any:
    if not BALE_TOKEN or BALE_TOKEN.startswith("PASTE_"):
        raise BaleAPIError("توکن ربات بله وارد نشده است.")

    url = "https://tapi.bale.ai/bot{}/{}".format(BALE_TOKEN.strip(), method)
    response = _BALE_SESSION.post(
        url,
        json=payload or {},
        timeout=(CONNECT_TIMEOUT, read_timeout),
    )
    try:
        data = response.json()
    except ValueError:
        raise BaleAPIError("پاسخ سرور بله قابل خواندن نبود (HTTP {}).".format(response.status_code))

    if not response.ok or not data.get("ok"):
        description = data.get("description") or data.get("error") or response.status_code
        raise BaleAPIError("خطای بله: {}".format(str(description)[:250]))
    return data.get("result")


def _load_offset() -> int:
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as file_obj:
            value = int(file_obj.read().strip())
            return max(0, value)
    except (OSError, ValueError):
        return 0


def _save_offset(offset: int) -> None:
    try:
        with open(OFFSET_FILE, "w", encoding="utf-8") as file_obj:
            file_obj.write(str(offset))
    except OSError as exc:
        print("[WARN] ذخیره offset ناموفق بود: {}".format(exc))


def send_bale_message(chat_id: Any, text: str, reply_to_message_id: Optional[int] = None) -> None:
    """Send long answers in multiple safe-sized text messages."""
    text = (text or "پاسخی دریافت نشد.").strip()
    if not text:
        text = "پاسخی دریافت نشد."

    chunks = []
    while len(text) > BALE_TEXT_LIMIT:
        split_at = text.rfind("\n", 0, BALE_TEXT_LIMIT)
        if split_at < BALE_TEXT_LIMIT // 2:
            split_at = BALE_TEXT_LIMIT
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        chunks.append(text)

    for index, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        if index == 0 and reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        _bale_request("sendMessage", payload, read_timeout=25)


def _get_help_text() -> str:
    return (
        "سلام! 👋 من دستیار هوش مصنوعی هستم.\n\n"
        "فقط پیام خودت را بفرست تا جواب بدهم.\n"
        "/start — شروع\n"
        "/help — راهنما\n"
        "/reset — پاک کردن حافظهٔ همین گفت‌وگو\n"
        "/status — دیدن سرویس‌های تنظیم‌شده"
    )


def _status_text() -> str:
    lines = ["ترتیب سرویس‌های هوش مصنوعی:"]
    found = False
    for index, provider in enumerate(PROVIDERS, start=1):
        key_count = len(_configured_keys(provider))
        if key_count:
            found = True
            lines.append("{}. {} — مدل {} — {} کلید تنظیم‌شده".format(
                index, provider["name"], provider["model"], key_count
            ))
        else:
            lines.append("{}. {} — کلیدی وارد نشده".format(index, provider["name"]))
    if not found:
        lines.append("هیچ API Key وارد نشده است.")
    return "\n".join(lines)


def _process_message(message: Dict[str, Any]) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    user_text = message.get("text")

    if chat_id is None or not isinstance(user_text, str) or not user_text.strip():
        return

    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return

    user_text = user_text.strip()
    command = user_text.split()[0].split("@")[0].lower() if user_text else ""
    chat_key = str(chat_id)

    if command == "/start":
        send_bale_message(chat_id, "ربات فعال است. ✅", message_id)
        return
    if command == "/status":
        send_bale_message(chat_id, _status_text(), message_id)
        return
    if command == "/reset":
        with _HISTORY_LOCK:
            _CHAT_HISTORY.pop(chat_key, None)
        send_bale_message(chat_id, "حافظهٔ این گفت‌وگو پاک شد. ✅", message_id)
        return

    if user_text.startswith("/"):
        send_bale_message(chat_id, "دستور شناخته نشد.", message_id)
        return

    # This bot processes messages sequentially; the in-memory context is isolated per chat.
    with _HISTORY_LOCK:
        history = list(_CHAT_HISTORY.get(chat_key, []))

    answer, provider_name = ask_ai(user_text, history)
    try:
        send_bale_message(chat_id, answer, message_id)
    except (requests.RequestException, BaleAPIError) as exc:
        print("[ERROR] ارسال پاسخ به بله ناموفق بود: {}".format(str(exc)[:250]))
        return

    if provider_name:
        with _HISTORY_LOCK:
            updated = _CHAT_HISTORY.get(chat_key, [])
            updated.extend([
                {"role": "user", "content": user_text[:MAX_INPUT_CHARACTERS]},
                {"role": "assistant", "content": answer},
            ])
            _CHAT_HISTORY[chat_key] = updated[-MAX_HISTORY_MESSAGES:]


def main() -> None:
    print("=" * 54)
    print("دستیار هوش مصنوعی بله — اولویت پنج سرویس")
    print("OpenAI > Gemini > DeepSeek > Groq > Pollinations")
    print("SYSTEM_PROMPT خالی است؛ در صورت نیاز متن دلخواهت را در ابتدای فایل وارد کن.")
    print("برای توقف، پنجره را ببند یا Ctrl+C بزن.")
    print("=" * 54)

    if not BALE_TOKEN or BALE_TOKEN.startswith("PASTE_"):
        print("[ERROR] بالای فایل، BALE_TOKEN را با توکن ربات بله عوض کن.")
        return

    active = [p["name"] for p in PROVIDERS if _configured_keys(p)]
    if not active:
        print("[ERROR] هیچ کلید هوش مصنوعی تنظیم نشده است. کلیدها را بالای فایل وارد کن.")
        return
    print("سرویس‌های دارای کلید:", "، ".join(active))

    try:
        me = _bale_request("getMe", {}, read_timeout=15)
        if isinstance(me, dict):
            print("ربات بله متصل شد:", me.get("username") or me.get("first_name") or "OK")
        else:
            print("اتصال به بله برقرار شد.")
    except (requests.RequestException, BaleAPIError) as exc:
        print("[ERROR] اتصال اولیه به بله انجام نشد:", str(exc))
        print("توکن بله و اینترنت را بررسی کن.")
        return

    offset = _load_offset()
    error_sleep = 2
    while True:
        try:
            updates = _bale_request(
                "getUpdates",
                {"offset": offset, "timeout": BALE_POLL_TIMEOUT, "limit": 50},
                read_timeout=BALE_READ_TIMEOUT,
            )
            error_sleep = 2
            if not isinstance(updates, list):
                time.sleep(1)
                continue

            for update in updates:
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                message = update.get("message")
                try:
                    if isinstance(message, dict):
                        _process_message(message)
                except (requests.RequestException, BaleAPIError, ValueError, TypeError) as exc:
                    print("[ERROR] پردازش پیام ناموفق بود: {}".format(str(exc)[:250]))

                if isinstance(update_id, int):
                    offset = max(offset, update_id + 1)
                    _save_offset(offset)

        except KeyboardInterrupt:
            print("\nربات متوقف شد.")
            break
        except (requests.RequestException, BaleAPIError, ValueError, TypeError) as exc:
            print("[WARN] ارتباط با بله قطع شد: {}".format(str(exc)[:200]))
            time.sleep(error_sleep)
            error_sleep = min(error_sleep * 2, POLL_ERROR_SLEEP_MAX)
        except Exception as exc:
            # Prevent a single unexpected update from killing the polling loop.
            print("[ERROR] خطای پیش‌بینی‌نشده: {}".format(str(exc)[:250]))
            time.sleep(2)


if __name__ == "__main__":
    main()

"""Post the KaanChart chart and an Arabic summary to Telegram through a bot.

Usage: python scripts/telegram_post.py assets/btc-1h.png data/kaanchart.json

Environment:
    TELEGRAM_BOT_TOKEN  token from @BotFather for the posting bot (e.g. @arbicapp)
    TELEGRAM_CHAT_ID    channel username (@kaanchart) or numeric chat id;
                        the bot must be an admin of the channel

Exits quietly when either variable is missing, so the daily job still updates
the profile without Telegram.
"""
import json
import os
import sys
import urllib.request
import uuid


def caption(s):
    rows = "\n".join(f"• {r['indicator']}: {r['state']} ({r['detail']})" for r in s["reading"])
    levels = "\n".join(f"• {lv}" for lv in s.get("levels", []))
    text = (f"📊 #BTC | فريم الساعة | KaanChart\n"
            f"السعر: {s['price']:,.0f} · {s['updated_utc']} UTC\n\n"
            f"🧭 المؤشرات:\n{rows}\n\n"
            f"🎯 المستويات:\n{levels}\n\n"
            f"هذا تحليل للتعليم وليس توصية مالية.\n#KaanChart")
    return text[:1024]  # Telegram photo caption limit


def send_photo(token, chat, png, text):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat), ("caption", text)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"btc-1h.png\"\r\n"
                 f"Content-Type: image/png\r\n\r\n".encode() + open(png, "rb").read() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if not res.get("ok"):
        raise SystemExit(f"Telegram error: {res}")
    print("posted to", chat)


def main():
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    png, js = sys.argv[1], sys.argv[2]
    text = caption(json.load(open(js, encoding="utf-8")))
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping Telegram post")
        print(text)
        return
    send_photo(token, chat, png, text)


if __name__ == "__main__":
    main()

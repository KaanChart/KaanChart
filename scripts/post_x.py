"""Build the daily KaanChart tweet from kaanchart.json and post it to X with the chart image.

Usage:
    python scripts/post_x.py data/kaanchart.json assets/btc-1h.png [--dry-run]

The tweet follows the format agreed in CLAUDE.md: Arabic only, at most 280 characters
as X counts them. Posting uses the X API v2 (media upload + create post) with OAuth 1.0a
user credentials from these environment variables:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

--dry-run prints the tweet and its length without posting.
The script refuses to post when the derivatives data (liquidations) is missing, so an
incomplete tweet never goes out.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 280
MEDIA_URL = "https://api.x.com/2/media/upload"
POST_URL = "https://api.x.com/2/tweets"


# ---------------------------------------------------------------- length as X counts it
def x_length(text):
    """Weighted length per twitter-text v3: Latin, Arabic and common punctuation count 1,
    emoji and other characters count 2."""
    n, i = 0, 0
    while i < len(text):
        c = ord(text[i])
        if c > 0xFFFF:  # emoji outside the BMP
            n += 2
        elif c in (0xFE0F, 0x200D):  # emoji modifiers, part of the previous emoji
            pass
        elif c <= 0x10FF or 0x2000 <= c <= 0x200D or 0x2010 <= c <= 0x201F or 0x2032 <= c <= 0x2037:
            n += 1
        else:
            n += 2
        i += 1
    return n


# ---------------------------------------------------------------- tweet text
def fmt(x):
    return f"{x:,.0f}"


def build_tweet(d):
    deriv = d.get("derivatives")
    if not deriv:
        raise SystemExit("No derivatives data (check COINALYZE_API_KEY); not posting an incomplete tweet.")
    px = d["price"]
    st = d["structure"]
    hi, lo, trend = st["last_swing_high"], st["last_swing_low"], st["trend"]

    icon, word = {1: ("📈", "صاعد"), -1: ("📉", "هابط")}.get(trend, ("📊", "محايد"))
    if hi and px < hi and (not lo or px > lo):
        where = f"والسعر تحت آخر قمة {fmt(hi)}"
    elif hi and px >= hi:
        where = f"والسعر فوق آخر قمة {fmt(hi)}"
    else:
        where = f"والسعر تحت آخر قاع {fmt(lo)}"

    asks = sorted(d["liquidity_walls"]["asks"], key=lambda w: -w["usd"])  # biggest wall, like the bid line
    bids = sorted(d["liquidity_walls"]["bids"], key=lambda w: -w["usd"])
    fib_up = sorted((lv for lv in (d.get("fib") or {}).get("levels", []) if lv["price"] > px),
                    key=lambda lv: lv["price"])

    meaning = "استمرار للصعود" if trend == 1 else "كسر للهيكل"
    extras = []
    if asks:
        extras.append(f"جدار بيع {fmt(asks[0]['price'])}")
    fib_up = [lv for lv in fib_up if lv["price"] > hi] or fib_up
    fib_short = None
    if fib_up:
        extras.append(f"فيبو {fib_up[0]['ratio']:g} عند {fmt(fib_up[0]['price'])}")
        fib_short = f"فيبو {fib_up[0]['ratio']:g} ({fmt(fib_up[0]['price'])})"

    def compose(extras):
        # "فوقها" refers back to the last high named on the structure line.
        ref = "فوقها" if hi and px < hi else f"فوق {fmt(hi)}"
        green = f"🟢 إغلاق {ref} = {meaning}" + ("، " + " و".join(extras) if extras else "")
        lines = [f"#بيتكوين فريم الساعة | {fmt(px)}$", "",
                 f"{icon} الهيكل {word} {where}", green,
                 f"🔴 إغلاق تحت {fmt(lo)} = قاع جديد"]
        if bids:
            lines.append(f"- جدار شراء {fmt(bids[0]['price'])} ({bids[0]['usd'] / 1e6:.0f} مليون$)")
        lines += [f"- تصفيات 24س: البايعين {deriv['liq_24h_short_usd'] / 1e6:.0f}M$"
                  f" · المشترين {deriv['liq_24h_long_usd'] / 1e6:.0f}M$",
                  "", "$BTC #BTC",
                  "", "تعليمي وليس توصية مالية"]
        return "\n".join(lines)

    text = compose(extras)
    if x_length(text) > LIMIT and fib_short:  # first shorten the Fibonacci wording
        extras[-1] = fib_short
        text = compose(extras)
    while x_length(text) > LIMIT and extras:  # then drop the least important detail
        extras.pop()
        text = compose(extras)
    if x_length(text) > LIMIT:
        raise SystemExit(f"Tweet is {x_length(text)} characters, over {LIMIT}:\n{text}")
    return text


# ---------------------------------------------------------------- OAuth 1.0a
def _q(s):
    return urllib.parse.quote(str(s), safe="~")


def oauth_header(method, url, creds):
    """OAuth 1.0a header. Multipart and JSON bodies are not part of the signature."""
    p = {
        "oauth_consumer_key": creds["key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["token"],
        "oauth_version": "1.0",
    }
    base = "&".join([method, _q(url), _q("&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(p.items())))])
    key = f"{_q(creds['secret'])}&{_q(creds['token_secret'])}"
    p["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_q(k)}="{_q(v)}"' for k, v in sorted(p.items()))


def call(url, body, content_type, creds):
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": oauth_header("POST", url, creds),
        "Content-Type": content_type,
        "User-Agent": "kaanchart-bot",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"X API {url} failed: HTTP {e.code} {e.read().decode(errors='replace')}")


def upload_image(path, creds):
    boundary = "kaanchart" + secrets.token_hex(8)
    data = open(path, "rb").read()
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media_category\"\r\n\r\ntweet_image\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"btc-1h.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    res = call(MEDIA_URL, b"".join(parts), f"multipart/form-data; boundary={boundary}", creds)
    media = res.get("data", res)
    return str(media.get("id") or media.get("media_id_string") or media["media_id"])


def post(text, png):
    names = {"key": "X_API_KEY", "secret": "X_API_SECRET", "token": "X_ACCESS_TOKEN",
             "token_secret": "X_ACCESS_TOKEN_SECRET"}
    missing = [v for v in names.values() if not os.environ.get(v)]
    if missing:
        raise SystemExit("Missing X credentials: " + ", ".join(missing))
    creds = {k: os.environ[v] for k, v in names.items()}
    media_id = upload_image(png, creds)
    res = call(POST_URL, json.dumps({"text": text, "media": {"media_ids": [media_id]}}).encode(),
               "application/json", creds)
    return res["data"]["id"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    js, png = args
    d = json.load(open(js, encoding="utf-8"))
    text = build_tweet(d)
    print(text)
    print(f"\n[{x_length(text)}/{LIMIT} characters as X counts them]")
    if dry:
        print("Dry run: not posted.")
        return
    tid = post(text, png)
    print(f"Posted: https://x.com/kaanchart/status/{tid}")


if __name__ == "__main__":
    main()

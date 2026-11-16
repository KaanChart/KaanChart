"""KaanChart indicators: BTC/USDT 1H price structure, order-book liquidity walls,
and derivatives data across exchanges, in one chart plus a JSON summary.

Usage:
    python scripts/kaanchart.py assets/btc-1h.png data/kaanchart.json [README.md]

Sources (all public, except Coinalyze which needs a free key):
    candles      Binance public mirror, falls back to OKX
    order books  OKX perp + spot, Binance spot, Hyperliquid, Gate perp
    long/short   OKX account ratio
    derivatives  Coinalyze (open interest, funding, liquidations across exchanges)
                 read only when the COINALYZE_API_KEY environment variable is set

The output describes indicators. It is not financial advice.
"""
import datetime as d
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as md  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

UA = {"User-Agent": "kaanchart-bot", "Content-Type": "application/json"}


def get(url, body=None, headers=None, tries=4):
    h = dict(UA, **(headers or {}))
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = float(e.headers.get("Retry-After") or 15)
            print(f"rate limited, waiting {wait:.0f}s", flush=True)
            time.sleep(wait + 1)
    raise RuntimeError(f"rate limited: {url}")


# ---------------------------------------------------------------- candles
def candles():
    for u in (
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=240",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=240",
    ):
        try:
            k = get(u)
            if isinstance(k, list) and k:
                return [[int(r[0])] + [float(x) for x in r[1:6]] for r in k], "Binance"
        except Exception as e:  # noqa: BLE001
            print("candles failed:", u, e)
    rows, after = [], ""
    for _ in range(3):
        page = get("https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H&limit=100"
                   + (f"&after={after}" if after else ""))["data"]
        if not page:
            break
        rows += page
        after = page[-1][0]
    rows = sorted(rows, key=lambda x: int(x[0]))[-240:]
    return [[int(x[0])] + [float(v) for v in x[1:6]] for x in rows], "OKX"


# ---------------------------------------------------------------- structure
def structure(H, L, C, n=4):
    N = len(C)
    piv = []
    for i in range(n, N - n):
        if H[i] == max(H[i - n:i + n + 1]):
            piv.append((i, "H", H[i]))
        if L[i] == min(L[i - n:i + n + 1]):
            piv.append((i, "L", L[i]))
    alt = []
    for p in piv:
        if alt and alt[-1][1] == p[1]:
            if (p[1] == "H" and p[2] > alt[-1][2]) or (p[1] == "L" and p[2] < alt[-1][2]):
                alt[-1] = p
        else:
            alt.append(p)
    labels, lastH, lastL = [], None, None
    for p in alt:
        if p[1] == "H":
            labels.append((p, "" if lastH is None else ("HH" if p[2] > lastH else "LH")))
            lastH = p[2]
        else:
            labels.append((p, "" if lastL is None else ("HL" if p[2] > lastL else "LL")))
            lastL = p[2]
    events, trend, sH, sL, j = [], 0, None, None, 0
    for i in range(N):
        while j < len(alt) and alt[j][0] + n <= i:
            if alt[j][1] == "H":
                sH = alt[j]
            else:
                sL = alt[j]
            j += 1
        if sH and C[i] > sH[2]:
            events.append((sH, i, "BOS" if trend == 1 else "CHoCH", "up"))
            trend, sH = 1, None
        elif sL and C[i] < sL[2]:
            events.append((sL, i, "BOS" if trend == -1 else "CHoCH", "dn"))
            trend, sL = -1, None
    lastHigh = next((p[2] for p in reversed(alt) if p[1] == "H"), None)
    lastLow = next((p[2] for p in reversed(alt) if p[1] == "L"), None)
    return alt, labels, events, trend, lastHigh, lastLow


# ---------------------------------------------------------------- order books
BUCKET, RANGE, NEAR = 100, 0.03, 0.004


def order_books():
    books = {}

    def add(name, fn):
        try:
            books[name] = fn()
        except Exception as e:  # noqa: BLE001
            print("book skipped:", name, e)

    def okx(inst, mult):
        b = get(f"https://www.okx.com/api/v5/market/books-full?instId={inst}&sz=5000")["data"][0]
        return [(float(p), float(s) * mult, side) for side, key in (("bid", "bids"), ("ask", "asks"))
                for p, s, _ in b[key]]

    add("OKX perp", lambda: okx("BTC-USDT-SWAP", 0.01))
    add("OKX spot", lambda: okx("BTC-USDT", 1.0))
    add("Binance spot", lambda: [(float(p), float(s), side) for side, key in (("bid", "bids"), ("ask", "asks"))
                                 for p, s in get("https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=5000")[key]])
    add("Hyperliquid", lambda: [(float(x["px"]), float(x["sz"]), side) for side, lv in zip(
        ("bid", "ask"), get("https://api.hyperliquid.xyz/info", {"type": "l2Book", "coin": "BTC", "nSigFigs": 3})["levels"])
        for x in lv])
    add("Gate perp", lambda: [(float(x["p"]), float(x["s"]) * 0.0001, side) for side, key in (("bid", "bids"), ("ask", "asks"))
                              for x in get("https://api.gateio.ws/api/v4/futures/usdt/order_book?contract=BTC_USDT&limit=300&interval=10")[key]])
    return books


def walls(books, px):
    lo, hi = px * (1 - RANGE), px * (1 + RANGE)
    agg = defaultdict(float)
    for rows in books.values():
        for p, s, side in rows:
            if lo <= p <= hi and ((side == "bid" and p < px) or (side == "ask" and p > px)):
                agg[(round(p / BUCKET) * BUCKET, side)] += s * p
    bids = sorted([(b, v) for (b, s), v in agg.items() if s == "bid" and b < px * (1 - NEAR)], key=lambda x: -x[1])[:3]
    asks = sorted([(b, v) for (b, s), v in agg.items() if s == "ask" and b > px * (1 + NEAR)], key=lambda x: -x[1])[:3]
    return agg, bids, asks


# ---------------------------------------------------------------- derivatives
def okx_long_short():
    try:
        rows = get("https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H")["data"]
        return float(rows[0][1])
    except Exception as e:  # noqa: BLE001
        print("okx long/short failed:", e)
        return None


def coinalyze():
    key = os.environ.get("COINALYZE_API_KEY")
    if not key:
        print("COINALYZE_API_KEY not set; skipping cross-exchange derivatives")
        return None
    hdr = {"api_key": key}
    base = "https://api.coinalyze.net/v1/"
    try:
        names = {e["code"]: e["name"] for e in get(base + "exchanges", headers=hdr)}
        markets = get(base + "future-markets", headers=hdr)
        syms = [m["symbol"] for m in markets if m["base_asset"] == "BTC" and m["is_perpetual"]
                and m["quote_asset"] in ("USDT", "USD", "USDC") and names.get(m["exchange"]) != "Polymarket"]
        now = int(time.time())

        def batch(path, **q):
            out = []
            for i in range(0, len(syms), 20):
                q["symbols"] = ",".join(syms[i:i + 20])
                out += get(base + path + "?" + "&".join(f"{k}={v}" for k, v in q.items()), headers=hdr)
                time.sleep(2)
            return out

        oi = batch("open-interest", convert_to_usd="true")
        fr = batch("funding-rate")
        lq = batch("liquidation-history", interval="1hour", convert_to_usd="true", **{"from": now - 72 * 3600, "to": now})
    except Exception as e:  # noqa: BLE001
        print("coinalyze failed:", e)
        return None

    ex = lambda s: names.get(s.split(".")[-1], s)  # noqa: E731
    oi_by = defaultdict(float)
    for x in oi:
        oi_by[ex(x["symbol"])] += x["value"]
    oi_sym = {x["symbol"]: x["value"] for x in oi}
    w = sum(oi_sym.get(x["symbol"], 0) for x in fr)
    # Hyperliquid and Lighter quote hourly funding; scale to 8 hours to compare.
    per8 = lambda x: x["value"] * (8 if ex(x["symbol"]) in ("Hyperliquid", "Lighter") else 1)  # noqa: E731
    funding = sum(per8(x) * oi_sym.get(x["symbol"], 0) for x in fr) / w if w else None
    hourly = defaultdict(lambda: [0.0, 0.0])
    for x in lq:
        for h in x["history"]:
            hourly[h["t"]][0] += h["l"]
            hourly[h["t"]][1] += h["s"]
    last24 = [v for t, v in hourly.items() if t >= now - 24 * 3600]
    return {
        "oi_total_usd": sum(oi_by.values()),
        "oi_by_exchange_usd": dict(sorted(oi_by.items(), key=lambda kv: -kv[1])),
        "funding_8h_pct_oi_weighted": funding,
        "liq_24h_long_usd": sum(v[0] for v in last24),
        "liq_24h_short_usd": sum(v[1] for v in last24),
        "liq_72h_long_usd": sum(v[0] for v in hourly.values()),
        "liq_72h_short_usd": sum(v[1] for v in hourly.values()),
        "liq_hourly": sorted((t, v[0], v[1]) for t, v in hourly.items()),
    }


# ---------------------------------------------------------------- reading
def reading(trend, ev, px, lastHigh, lastLow, deriv, ls, bids, asks):
    """Plain-language state of each indicator. Describes, does not advise."""
    out = []
    last = ev[-1] if ev else None
    out.append(("الهيكل", "هابط" if trend < 0 else "صاعد" if trend > 0 else "محايد",
                f"آخر إشارة {last[2]} {'صاعد' if last[3] == 'up' else 'هابط'} عند {last[0][2]:,.0f}" if last else "—"))
    if deriv and deriv["funding_8h_pct_oi_weighted"] is not None:
        f = deriv["funding_8h_pct_oi_weighted"]
        out.append(("التمويل", "سالب" if f < 0 else "مرتفع" if f > 0.02 else "طبيعي", f"{f:+.4f}% لكل 8 ساعات"))
    if ls is not None:
        out.append(("Long/Short (OKX)", "مزدحم Long" if ls > 2.5 else "مزدحم Short" if ls < 0.8 else "متوازن", f"{ls:.2f}"))
    if deriv:
        L, S = deriv["liq_24h_long_usd"], deriv["liq_24h_short_usd"]
        out.append(("تصفيات 24 ساعة", "Long أكثر" if L > S else "Short أكثر", f"Long {L / 1e6:.1f}M$ · Short {S / 1e6:.1f}M$"))
    if bids and asks:
        bv, av = sum(v for _, v in bids), sum(v for _, v in asks)
        out.append(("جدران الأوامر", "شراء أثقل" if bv > av * 1.2 else "بيع أثقل" if av > bv * 1.2 else "متقاربة",
                    f"شراء {bids[0][0]:,.0f} ({bids[0][1] / 1e6:.0f}M$) · بيع {asks[0][0]:,.0f} ({asks[0][1] / 1e6:.0f}M$)"))
    levels = []
    if lastHigh:
        levels.append(f"إغلاق ساعة فوق {lastHigh:,.0f} يكسر آخر قمة")
    if lastLow:
        levels.append(f"إغلاق ساعة تحت {lastLow:,.0f} يكسر آخر قاع")
    return out, levels


# ---------------------------------------------------------------- chart
BG, FG, MU, GR = "#0e1117", "#e6e9ef", "#8a93a6", "#232a36"
UP, DN, GOLD = "#26a69a", "#ef5350", "#f2b84b"


def draw(path, k, src, alt, labels, events, agg, bids, asks, deriv, books):
    T = [d.datetime.fromtimestamp(r[0] / 1000, d.UTC) + d.timedelta(minutes=30) for r in k]
    O, H, L, C = ([r[i] for r in k] for i in (1, 2, 3, 4))
    N, cut, px = len(k), len(k) - 120, k[-1][4]
    plt.rcParams.update({"font.size": 11, "text.color": FG, "xtick.color": MU, "ytick.color": MU})
    fig = plt.figure(figsize=(16, 11), facecolor=BG)
    gs = fig.add_gridspec(2, 2, width_ratios=[4, 1.1], height_ratios=[3.2, 1], wspace=0.02, hspace=0.06)
    ax, axb = fig.add_subplot(gs[0, 0]), None
    axb = fig.add_subplot(gs[0, 1], sharey=ax)
    axl = fig.add_subplot(gs[1, 0], sharex=ax)
    axt = fig.add_subplot(gs[1, 1])
    for a in (ax, axb, axl, axt):
        a.set_facecolor(BG)
        a.grid(color=GR, lw=.6)
        for s in a.spines.values():
            s.set_visible(False)
    axt.grid(False)
    axt.set_xticks([])
    axt.set_yticks([])

    w = 0.7 / 24
    for i in range(cut, N):
        col = UP if C[i] >= O[i] else DN
        ax.vlines(T[i], L[i], H[i], color=col, lw=1)
        ax.bar(T[i], abs(C[i] - O[i]) or 5, bottom=min(O[i], C[i]), width=w, color=col)
    pts = [p for p in alt if p[0] >= cut]
    ax.plot([T[p[0]] for p in pts], [p[2] for p in pts], color=MU, lw=1, alpha=.5)
    for p, t in labels:
        if p[0] >= cut and t:
            ax.annotate(t, (T[p[0]], p[2]), xytext=(0, 9 if p[1] == "H" else -16), textcoords="offset points",
                        ha="center", fontsize=9, fontweight="bold", color=UP if t in ("HH", "HL") else DN)
    for s, i, name, dr in events:
        if i >= cut:
            col, x0 = (UP if dr == "up" else DN), T[max(s[0], cut)]
            ax.hlines(s[2], x0, T[i], color=col, lw=1.1, ls="--")
            ax.text(x0 + (T[i] - x0) / 2, s[2], name, color=col, ha="center",
                    va="bottom" if dr == "up" else "top", fontsize=9, fontweight="bold")
    for b, v in bids + asks:
        col = UP if b < px else DN
        ax.axhline(b, color=col, lw=1.6, alpha=.55, ls=":")
    ax.axhline(px, color=GOLD, lw=1)
    ax.set_xlim(T[cut] - d.timedelta(hours=1), T[-1] + d.timedelta(hours=14))
    lo, hi = min(L[cut:]), max(H[cut:])
    pad = (hi - lo) * .05
    ax.set_ylim(min(lo, px * (1 - RANGE)) - pad, max(hi, px * (1 + RANGE)) + pad)
    plt.setp(ax.get_xticklabels(), visible=False)

    rows = sorted(agg.items())
    axb.barh([b for (b, s), v in rows], [v / 1e6 for (b, s), v in rows], height=BUCKET * .85,
             color=[UP if s == "bid" else DN for (b, s), v in rows])
    axb.axhline(px, color=GOLD, lw=1)
    axb.yaxis.tick_right()
    axb.set_xlabel("Resting orders $M (±3%)", color=MU, fontsize=9)
    axb.xaxis.set_label_position("top")

    if deriv and deriv["liq_hourly"]:
        lt = [d.datetime.fromtimestamp(t, d.UTC) + d.timedelta(minutes=30) for t, _, _ in deriv["liq_hourly"]]
        axl.bar(lt, [l / 1e6 for _, l, _ in deriv["liq_hourly"]], width=w, color=DN, label="Long liquidated")
        axl.bar(lt, [-s / 1e6 for _, _, s in deriv["liq_hourly"]], width=w, color=UP, label="Short liquidated")
        axl.axhline(0, color=MU, lw=.6)
        axl.set_ylabel("Liquidations $M", color=MU)
        axl.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=FG)
    else:
        axl.text(.5, .5, "Cross-exchange liquidations need COINALYZE_API_KEY", transform=axl.transAxes,
                 ha="center", color=MU)
    axl.xaxis.set_major_locator(md.DayLocator(tz=d.UTC))
    axl.xaxis.set_major_formatter(md.DateFormatter("%d %b", tz=d.UTC))

    lines = [f"Last  {px:,.0f}"]
    if deriv:
        lines += [f"OI all exch  ${deriv['oi_total_usd'] / 1e9:.1f}B"]
        lines += [f"  {n:<12}${v / 1e9:.1f}B" for n, v in list(deriv["oi_by_exchange_usd"].items())[:4]]
        if deriv["funding_8h_pct_oi_weighted"] is not None:
            lines += [f"Funding 8h  {deriv['funding_8h_pct_oi_weighted']:+.4f}%"]
        lines += [f"Liq 24h  L ${deriv['liq_24h_long_usd'] / 1e6:.0f}M  S ${deriv['liq_24h_short_usd'] / 1e6:.0f}M"]
    lines += ["Ask walls"] + [f"  {b:,.0f}  ${v / 1e6:.0f}M" for b, v in sorted(asks, reverse=True)]
    lines += ["Bid walls"] + [f"  {b:,.0f}  ${v / 1e6:.0f}M" for b, v in sorted(bids, reverse=True)]
    axt.text(.04, .96, "\n".join(lines).replace("$", r"\$"), transform=axt.transAxes, va="top", ha="left", family="monospace",
             fontsize=9, color=FG, linespacing=1.25)

    ax.set_title(f"BTC/USDT · 1H · Structure + Liquidity · {src} · {T[-1] - d.timedelta(minutes=30):%d %b %H:00} UTC"
                 f"   |   Last {px:,.0f}", loc="left", color=FG, fontsize=13)
    fig.text(.45, .6, "KaanChart", fontsize=120, fontweight="bold", color=GOLD, alpha=.09, ha="center",
             va="center", rotation=12)
    fig.text(.01, .01, "KaanChart", fontsize=16, fontweight="bold", color=GOLD)
    fig.text(.99, .01, "Books: " + " · ".join(books) + " · Derivatives: " + ("Coinalyze" if deriv else "n/a")
             + " · Not financial advice", ha="right", color=MU, fontsize=8.5)
    fig.savefig(path, dpi=150, facecolor=BG, bbox_inches="tight")


# ---------------------------------------------------------------- README
START, END = "<!-- KAANCHART:START -->", "<!-- KAANCHART:END -->"


def update_readme(path, stamp, px, rows, levels):
    text = open(path, encoding="utf-8").read()
    if START not in text:
        return
    body = [START, "", f"**آخر تحديث:** {stamp} UTC · **السعر:** {px:,.0f}", "",
            "| المؤشر | الحالة | التفاصيل |", "|---|---|---|"]
    body += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    if levels:
        body += ["", "**المستويات:** " + " · ".join(levels)]
    body += ["", "> قراءة آلية للمؤشرات، وليست توصية مالية.", "", END]
    head, rest = text.split(START, 1)
    open(path, "w", encoding="utf-8").write(head + "\n".join(body) + rest.split(END, 1)[1])


def main():
    png, js = sys.argv[1], sys.argv[2]
    readme = sys.argv[3] if len(sys.argv) > 3 else None
    k, src = candles()
    H, L, C = ([r[i] for r in k] for i in (2, 3, 4))
    alt, labels, events, trend, lastHigh, lastLow = structure(H, L, C)
    px = C[-1]
    books = order_books()
    agg, bids, asks = walls(books, px)
    ls = okx_long_short()
    deriv = coinalyze()
    rows, levels = reading(trend, events, px, lastHigh, lastLow, deriv, ls, bids, asks)
    draw(png, k, src, alt, labels, events, agg, bids, asks, deriv, books)
    stamp = d.datetime.fromtimestamp(k[-1][0] / 1000, d.UTC).strftime("%Y-%m-%d %H:00")
    os.makedirs(os.path.dirname(js) or ".", exist_ok=True)
    out = {
        "updated_utc": stamp, "price": px, "candle_source": src,
        "structure": {"trend": trend, "last_swing_high": lastHigh, "last_swing_low": lastLow,
                      "last_event": ({"type": events[-1][2], "dir": events[-1][3], "level": events[-1][0][2]}
                                     if events else None)},
        "liquidity_walls": {"bids": [{"price": b, "usd": v} for b, v in bids],
                            "asks": [{"price": b, "usd": v} for b, v in asks], "books": list(books)},
        "okx_long_short_accounts": ls,
        "derivatives": ({kk: vv for kk, vv in deriv.items() if kk != "liq_hourly"} if deriv else None),
        "reading": [{"indicator": a, "state": b, "detail": c} for a, b, c in rows],
        "levels": levels,
        "note": "Indicator reading, not financial advice.",
    }
    json.dump(out, open(js, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if readme:
        update_readme(readme, stamp, px, rows, levels)
    print(json.dumps(out["reading"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

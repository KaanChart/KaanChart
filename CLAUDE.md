# KaanChart

Profile repository for KaanChart, a crypto technical-analysis channel (t.me/kaanchart, x.com/kaanchart).
The user writes in Gulf Arabic; reply in the same style.

## When the user asks for an hourly chart ("شارت ساعة", "اسحب الشارت", "حدّث الشارت")

Always deliver the full KaanChart chart, never a bare candle chart:

1. Run, from the repository root:
   `COINALYZE_API_KEY=proxy-injected python scripts/kaanchart.py <scratchpad>/btc-1h.png <scratchpad>/kaanchart.json`
   (the session proxy injects the real Coinalyze key; `pip install matplotlib` if missing).
   The chart combines price structure (HH/HL/LH/LL, BOS/CHoCH), order-book liquidity walls,
   cross-exchange liquidations, open interest and funding, with the KaanChart watermark.
2. Look at the PNG once and send it to the user.
3. Write a short public-facing analysis in Arabic from `kaanchart.json`:
   - one-line summary of the move
   - a table: structure, funding, long/short, 24h liquidations, liquidity walls
   - key levels: close above the last swing high / below the last swing low, nearest walls
   - end with: «هذا تحليل للتعليم وليس توصية مالية»
4. Only update `assets/btc-1h.png` in the repo (via a PR) when the user asks to update the profile.

## Data sources

- Candles and spot book: `data-api.binance.vision` (Binance's main and futures APIs are geo-blocked here).
- Order books: OKX, Hyperliquid, Gate. Bybit and BitMEX are geo-blocked.
- Cross-exchange derivatives: Coinalyze (free key; rate-limited, the script waits on 429).
- LiqVel's data API is paid (Prime); do not scrape it. Use screenshots the user sends instead.

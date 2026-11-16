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
3. Write the analysis from `kaanchart.json` as ONE ready-to-post tweet (no thread, no table),
   in a code block so the user can copy it, at most 280 characters, all in Arabic
   (no English terms like Long/Short, CHoCH, HH; say المشترين/البايعين, قمة/قاع):
   ```
   #بيتكوين فريم الساعة | <price>$

   📉/📈 <structure in one line, and where price sits vs the last swing high/low>
   🟢 إغلاق ساعة فوق <last swing high> = <meaning>، <nearest ask wall if it sits there>
   🔴 إغلاق تحت <last swing low> = قاع جديد
   🧱 جدار شراء <biggest bid wall> (<size> مليون$)
   💥 تصفيات 24س: البايعين <short liq>M$ · المشترين <long liq>M$

   تعليمي وليس توصية مالية
   ```
   The PNG is attached to the tweet. If the current hourly candle has not closed yet, say so
   in one line outside the tweet.
4. Only update `assets/btc-1h.png` in the repo (via a PR) when the user asks to update the profile.

## Data sources

- Candles and spot book: `data-api.binance.vision` (Binance's main and futures APIs are geo-blocked here).
- Order books: OKX, Hyperliquid, Gate. Bybit and BitMEX are geo-blocked.
- Cross-exchange derivatives: Coinalyze (free key; rate-limited, the script waits on 429).
- LiqVel's data API is paid (Prime); do not scrape it. Use screenshots the user sends instead.

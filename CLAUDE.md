# KaanChart

Profile repository for KaanChart, a crypto technical-analysis channel (t.me/kaanchart, x.com/kaanchart).
The user writes in Gulf Arabic; reply in the same style.

## When the user asks for an hourly chart ("شارت ساعة", "اسحب الشارت", "حدّث الشارت")

Always deliver the full KaanChart chart, never a bare candle chart:

1. Run, from the repository root:
   `COINALYZE_API_KEY=proxy-injected python scripts/kaanchart.py <scratchpad>/btc-1h.png <scratchpad>/kaanchart.json`
   (the session proxy injects the real Coinalyze key; `pip install matplotlib` if missing).
   The chart combines price structure (HH/HL/LH/LL, BOS/CHoCH), Fibonacci retracements of the
   largest move in view, volume (each break labelled with its volume vs the 20-candle average),
   order-book liquidity walls, cross-exchange liquidations, open interest (line + 24h change)
   and funding, with the KaanChart watermark.
2. Look at the PNG once and send it to the user.
3. Write the analysis from `kaanchart.json` as ONE ready-to-post tweet (no thread, no table),
   in a code block so the user can copy it, at most 280 characters, all in Arabic
   (no English terms like Long/Short, CHoCH, HH; say المشترين/البايعين, قمة/قاع):
   ```
   #بيتكوين فريم الساعة | <price>$

   📉/📈 <structure in one line, and where price sits vs the last swing high/low>
   🟢 إغلاق ساعة فوق <last swing high> = كسر للهيكل، وعندها جدار بيع <nearest ask wall> وفيبو <nearest fib level above>
   🔴 إغلاق تحت <last swing low> = قاع جديد
   🧱 جدار شراء <biggest bid wall> (<size> مليون$)
   💥 تصفيات 24س: البايعين <short liq>M$ · المشترين <long liq>M$

   تعليمي وليس توصية مالية
   ```
   Count the length as X does (emoji count 2) and trim wording if it goes over 280.
   Then a Telegram post in a second code block (no length limit, same Arabic-only rule):
   ```
   #بيتكوين | فريم الساعة | <price>$

   📉/📈 الهيكل: <structure>، <where price sits>
   آخر كسر <هابط/صاعد> كان بحجم <قوي/ضعيف> (×<last_break_volume_x_avg20> من المتوسط)

   🟢 فوق: إغلاق ساعة فوق <last swing high> = كسر للهيكل
   جدران بيع <ask walls with sizes>
   بعدها فيبو <ratio> عند <price>، و<ratio> عند <price>

   🔴 تحت: إغلاق تحت <last swing low> = قاع جديد
   جدران شراء <bid walls with sizes>

   📊 العقود المفتوحة: <oi>مليار$ (<oi_change_24h_pct>% خلال 24س)
   <one line: price change 24h vs OI change: new money in, or positions closing>

   💥 تصفيات 24س: البايعين <short>M$ · المشترين <long>M$
   ⚖️ <long/short reading> (<ratio>) والتمويل <funding reading> (<funding>%)

   تعليمي وليس توصية مالية
   ```
   Use `fib`, `last_break_volume_x_avg20`, `price_change_24h_pct` and
   `derivatives.oi_change_24h_pct` from the JSON. Volume above ×1.5 is a strong break,
   below ×1.2 a weak one. The PNG is attached to both. If the current hourly candle has not
   closed yet, say so in one line outside the posts.
4. Only update `assets/btc-1h.png` in the repo (via a PR) when the user asks to update the profile.

## Daily post on X

`.github/workflows/post-x.yml` posts the chart and the tweet to x.com/kaanchart every day at
06:03 UTC (9 AM Gulf time) with no review. `scripts/post_x.py` builds the tweet from the JSON in
the format above and refuses to post when the Coinalyze data is missing. A manual run from the
Actions tab is a dry run by default. It needs the repository secrets `COINALYZE_API_KEY`,
`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN` and `X_ACCESS_TOKEN_SECRET`. If you change the
tweet format above, change `build_tweet` in `scripts/post_x.py` to match.

## Data sources

- Candles and spot book: `data-api.binance.vision` (Binance's main and futures APIs are geo-blocked here).
- Order books: OKX, Hyperliquid, Gate. Bybit and BitMEX are geo-blocked.
- Cross-exchange derivatives: Coinalyze (free key; rate-limited, the script waits on 429).
- LiqVel's data API is paid (Prime); do not scrape it. Use screenshots the user sends instead.

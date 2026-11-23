# btc-race-zigzag-engulf-0511

[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/unot58/btc-race-zigzag-engulf-0511/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/unot58/btc-race-zigzag-engulf-0511/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

A cbBTC swing bot for make.fun's "Race a BTC trading bot live for 24 hours"
(btc-race-24h-20261123-0511). It trades the entrant's own Setup Tipe 3,
adapted to a long-only 1-minute replay: percentage-zigzag swing highs/lows
on 5-minute and 15-minute bars define the zones, a 1-minute bullish
engulfing bar at a confirmed swing low is the entry, the stop sits beyond
the swing, and the target is the opposite swing — never a fixed R multiple,
and no ATR anywhere. A 15-minute regime filter (no lower lows) keeps it out
of downtrend legs, a one-round-trip-per-day cap keeps it from grinding
through chop, and a hail-mary / last-resort guardrail guarantees at least
one filled trade on a quiet day.

Tested on the kit's own replay engine: dev window +$7.73 net PnL (1 round
trip, max drawdown 0.21%, deterministic across runs); 8 out-of-sample
24-hour windows mean −$1.33, range −$7.03 to +$6.83, exactly 1 round trip
on every window, max drawdown under 0.9% everywhere.

## Run it

```sh
python3 main.py
```

The bot speaks the make.fun bars protocol on stdin/stdout (one JSON line
per minute, orders back as JSON lines). Standard library only, plus the
vendored `vendor/makefun_bars.py` from the competition kit. No network, no
wall clock, no files outside the repository, no randomness: the same bars
always produce the same orders.

---

<sub>Entered on [make.fun](https://make.fun/?ref=xv8h587n&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511) · AI agents build software for cash rewards</sub>

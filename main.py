"""Zigzag + engulfing BTC race bot for make.fun btc-race-24h-20261123-0511.

The entrant's own Setup Tipe 3, adapted to a long-only 1-minute replay:

- STRUCTURE (zones): percentage zigzag swing highs/lows on 5-minute and
  15-minute bars built from the 1-minute feed. A confirmed swing low is a
  demand level, a confirmed swing high a supply level. No ATR anywhere.
- ENTRY: a 1-minute bullish engulfing bar (body >= BODY_MIN_BPS) touching
  a confirmed swing low, or sweeping below it and closing back above it,
  entered ON the engulfing bar itself. The winner of the last finished
  edition bought the first bounce bar off the low; waiting an extra bar
  for follow-through only pays a worse price. The swing low must sit at
  the foot of a real leg down (prior swing high to this low >=
  MIN_LEG_BPS): shallow 30bps wiggles are noise, and buying them is what
  bleeds the account on flat days. Full-size buy, one position max.
- STOP: below the swing low that triggered the entry (minus SL_BUF_BPS).
  A stop-out invalidates that swing and blocks new entries for
  COOLDOWN_BARS.
- TARGET: the nearest confirmed swing high above the entry (the OPPOSITE
  swing), never a fixed R multiple; a fixed bps fallback only when no
  opposite swing exists yet. The target is re-checked every bar while
  holding, so a swing high that confirms after entry and sits closer
  than the current target tightens it.
- EXITS: target hit, stop hit, or a time stop. No exit on
  counter-engulfings: a swing trade is held through pullbacks until its
  target, its stop, or the time stop — the last edition's winner held
  6-7 hours for +250bps and never exited early.
- FREQUENCY CAP: at most MAX_TRIPS round trips per day. The last
  edition's winner traded once; out-of-sample testing showed every extra
  marginal trade is pure cost (~34bps a round trip), so the bot stops
  trading after its best few setups instead of grinding through chop.
- REGIME FILTER: a main entry needs the 15-minute structure to agree —
  the last two confirmed 15m swing lows must NOT be descending (lower
  lows = a downtrend leg, where dip-buying gets run over). This is the
  race-scale version of the Setup Tipe 3 rule that the higher timeframe
  sets the direction. Guardrail trades are exempt: they exist to
  guarantee a trade, not to read structure.
- GUARDRAIL: a hail mary (strong engulfing anywhere after bar 1200) and a
  last-resort unconditional buy at bar 1350 guarantee at least one filled
  trade on every window, so a quiet race day can never leave the entry
  with zero trades.

Pure integer math (prices are scale-5 ints, bps math with //). No network,
no wall clock, no randomness, no file or environment reads: the same bars
always produce the same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (swept on the dev window + 8 OOS windows) ---
ZZ5_DEV_BPS = 30        # 5m zigzag deviation: a leg turns after this retracement
ZZ15_DEV_BPS = 50       # 15m zigzag deviation
BODY_MIN_BPS = 8        # engulfing bar body, min, in bps of its close
TOUCH_TOL_BPS = 15      # how close a bar's low must be to a swing low to count as a touch
SWEEP_MAX_BPS = 50      # deepest dip below a swing low that still counts as a sweep (not a break)
SL_BUF_BPS = 10         # stop buffer below the swing low
MIN_TARGET_BPS = 80     # an opposite swing must sit at least this far above the entry
TP_FALLBACK_BPS = 150   # target when no opposite swing exists yet
MIN_LEG_BPS = 150       # the dip into a swing low must be at least this deep
MAX_TRIPS = 1           # round-trip cap per day (guardrail trades exempt)
REGIME_FILTER = True    # block main entries when 15m swing lows are descending
TIME_STOP_BARS = 360    # exit a stale position after this many bars
COOLDOWN_BARS = 60      # no new entries this long after a stop-out
LAST_ENTRY_SEQ = 1380   # no (non-guardrail) entries in the final 60 bars
FIRST_ENTRY_SEQ = 0     # warm-up: no main entries before this bar (0 = off)
HAIL_MARY_SEQ = 1200    # from here, a strong engulfing anywhere is enough
HAIL_BODY_MIN_BPS = 12
LAST_RESORT_SEQ = 1350  # from here, buy unconditionally if still no filled trade
MAX_SLIPPAGE_BPS = 150

BPS = 10_000


def bps_of(amount, price):
    return amount * BPS // price if price > 0 else 0


class Zigzag:
    """Percentage zigzag over completed bars of one timeframe.

    Keeps only CONFIRMED swings: a swing high is confirmed when price falls
    dev bps below the leg's highest high; a swing low when price rises dev
    bps above the leg's lowest low. `swings` holds (bar_idx, price, kind)
    with kind +1 for a high, -1 for a low, in confirmation order.
    """

    def __init__(self, dev_bps):
        self.dev = dev_bps
        self.trend = 0  # 0 undecided, +1 hunting a high, -1 hunting a low
        self.cand_price = None
        self.cand_idx = -1
        self.swings = []

    def update(self, idx, high, low):
        if self.trend == 0:
            if self.cand_price is None:
                self.cand_price = high
                self.cand_idx = idx
                self._lo_price = low
                self._lo_idx = idx
                return None
            if high > self.cand_price:
                self.cand_price = high
                self.cand_idx = idx
            if low < self._lo_price:
                self._lo_price = low
                self._lo_idx = idx
            if high >= self._lo_price + self._lo_price * self.dev // BPS:
                self.swings.append((self._lo_idx, self._lo_price, -1))
                self.trend = 1
                self.cand_price = high
                self.cand_idx = idx
                return self.swings[-1]
            if low <= self.cand_price - self.cand_price * self.dev // BPS:
                self.swings.append((self.cand_idx, self.cand_price, 1))
                self.trend = -1
                self.cand_price = low
                self.cand_idx = idx
                return self.swings[-1]
            return None
        if self.trend == 1:
            if high > self.cand_price:
                self.cand_price = high
                self.cand_idx = idx
            if low <= self.cand_price - self.cand_price * self.dev // BPS:
                self.swings.append((self.cand_idx, self.cand_price, 1))
                self.trend = -1
                self.cand_price = low
                self.cand_idx = idx
                return self.swings[-1]
            return None
        if low < self.cand_price:
            self.cand_price = low
            self.cand_idx = idx
        if high >= self.cand_price + self.cand_price * self.dev // BPS:
            self.swings.append((self.cand_idx, self.cand_price, -1))
            self.trend = 1
            self.cand_price = high
            self.cand_idx = idx
            return self.swings[-1]
        return None

    def swing_lows(self):
        return [(i, p) for (i, p, k) in self.swings if k == -1]

    def swing_highs(self):
        return [(i, p) for (i, p, k) in self.swings if k == 1]


# --- rolling state (all derived from the bars seen so far) ---
bars1 = []          # 1m bars: dicts o/h/l/c (ints), t
bars5 = []          # completed 5m bars
bars15 = []         # completed 15m bars
_part5 = None       # current partial 5m bar [o, h, l]
_part15 = None      # current partial 15m bar [o, h, l]
zz5 = Zigzag(ZZ5_DEV_BPS)
zz15 = Zigzag(ZZ15_DEV_BPS)
invalidated = set()  # (timeframe, swing idx) broken by a stop-out
position = None      # open-trade plan: dict(sl, tp, entry, entry_seq, swing_key)
exiting = False      # a sell was sent; waiting for its fill before acting again
filled_trades = 0    # own filled orders seen in batch fills
trips_closed = 0     # round trips completed (sell fills); caps daily frequency
last_stop_seq = -10 ** 9


def _close_partial(part, close, idx, bars, zz):
    o, h, l = part
    bar = {"o": o, "h": h, "l": l, "c": close}
    bars.append(bar)
    zz.update(idx, h, l)


def _note_bar(bar):
    """Fold one 1m bar into the 1m/5m/15m series and both zigzags."""
    global _part5, _part15
    bars1.append(bar)
    t = bar["t"]
    if _part5 is None:
        _part5 = [bar["o"], bar["h"], bar["l"]]
    else:
        _part5[1] = max(_part5[1], bar["h"])
        _part5[2] = min(_part5[2], bar["l"])
    if _part15 is None:
        _part15 = [bar["o"], bar["h"], bar["l"]]
    else:
        _part15[1] = max(_part15[1], bar["h"])
        _part15[2] = min(_part15[2], bar["l"])
    if t % 300000 == 0:
        _close_partial(_part5, bar["c"], len(bars5), bars5, zz5)
        _part5 = None
    if t % 900000 == 0:
        _close_partial(_part15, bar["c"], len(bars15), bars15, zz15)
        _part15 = None


def _is_bull_engulfing(prev, cur):
    if prev["c"] >= prev["o"] or cur["c"] <= cur["o"]:
        return False
    if cur["o"] > prev["c"] or cur["c"] < prev["o"]:
        return False
    return bps_of(cur["c"] - cur["o"], cur["c"]) >= BODY_MIN_BPS


def _regime_ok():
    """True unless the 15m structure is a downtrend leg.

    The last two confirmed 15m swing lows descending (lower lows) means
    dip-buying is fighting the higher timeframe — skip the main entry.
    With fewer than two 15m lows there is no structure to read yet, so
    the entry is allowed.
    """
    if not REGIME_FILTER:
        return True
    lows = zz15.swing_lows()
    if len(lows) < 2:
        return True
    return lows[-1][1] >= lows[-2][1]


def _swing_at_low(bar):
    """The swing low this bar touches or sweeps, or None.

    Returns (timeframe, swing_idx, swing_price). Prefers the nearest level
    (smallest distance from the bar's low). Broken swings are skipped, and
    a low only counts when the leg down into it (prior swing high to this
    low) is at least MIN_LEG_BPS deep — shallow wiggles are noise.
    """
    best = None
    best_dist = None
    for tf, zz in (("5m", zz5), ("15m", zz15)):
        for idx, price in zz.swing_lows():
            if (tf, idx) in invalidated:
                continue
            # The leg down into this low: the most recent swing high BEFORE
            # the low's bar. (swings are stored in confirmation order, not
            # bar order, so scan all of them and keep the latest bar.)
            prior_high = None
            prior_high_idx = -1
            for (i2, p2, k2) in zz.swings:
                if k2 == 1 and i2 < idx and i2 > prior_high_idx:
                    prior_high = p2
                    prior_high_idx = i2
            if prior_high is None:
                continue
            if bps_of(prior_high - price, price) < MIN_LEG_BPS:
                continue
            tol = price * TOUCH_TOL_BPS // BPS
            touch = price - tol <= bar["l"] <= price + tol
            sweep = (
                bar["l"] < price - tol
                and bar["l"] >= price - price * SWEEP_MAX_BPS // BPS
                and bar["c"] > price
            )
            if touch or sweep:
                dist = abs(bar["l"] - price)
                if best_dist is None or dist < best_dist:
                    best = (tf, idx, price)
                    best_dist = dist
    return best


def _nearest_high_above(price):
    """Nearest confirmed swing high at least MIN_TARGET_BPS above price."""
    floor = price + price * MIN_TARGET_BPS // BPS
    best = None
    for zz in (zz5, zz15):
        for _idx, p in zz.swing_highs():
            if p >= floor and (best is None or p < best):
                best = p
    return best


def _buy_order(state, notional):
    return [{"side": "buy", "symbol": SYMBOL,
             "notional_quote_units": notional,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def _sell_order(state):
    holding = state.positions.get(SYMBOL)
    if holding is None or holding.qty <= 0:
        return []
    return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def _open_plan(entry_close, swing):
    """SL/TP for a new long: stop below the swing, target at the opposite swing."""
    if swing is not None:
        _tf, _idx, price = swing
        sl = price - price * SL_BUF_BPS // BPS
        swing_key = (_tf, _idx)
    else:
        sl = entry_close - entry_close * 100 // BPS
        swing_key = None
    tp = _nearest_high_above(entry_close)
    if tp is None:
        tp = entry_close + entry_close * TP_FALLBACK_BPS // BPS
    return {"sl": sl, "tp": tp, "entry": entry_close,
            "entry_seq": state_seq[0], "swing_key": swing_key}


state_seq = [0]


def on_batch(state, batch):
    global position, exiting, filled_trades, trips_closed, last_stop_seq
    state_seq[0] = state.seq

    # Sync the plan with this batch's fills first: a rejected buy voids its
    # plan (without this the bot would wait forever for a fill that never
    # comes), a filled sell closes it.
    for fill in batch.get("fills", []):
        cid = str(fill.get("client_id", ""))
        if cid.startswith("_"):
            continue
        if fill.get("status") == "filled":
            filled_trades += 1
            if fill.get("side") == "sell":
                position = None
                exiting = False
                trips_closed += 1
        elif fill.get("status") == "rejected" and fill.get("side") == "buy":
            position = None

    # Only bars present in THIS batch (state.latest is sticky across gaps).
    mine = [b for b in batch.get("bars", []) if b.get("symbol") == SYMBOL]
    if not mine:
        return []
    raw = mine[-1]
    bar = {"t": int(raw["t"]), "o": int(raw["o"]), "h": int(raw["h"]),
           "l": int(raw["l"]), "c": int(raw["c"])}
    prev = bars1[-1] if bars1 else None
    _note_bar(bar)
    seq = state.seq
    holding = state.positions.get(SYMBOL) is not None

    # A sell is in flight: wait for its fill, send nothing.
    if exiting:
        return []

    # --- manage the open position ---
    if holding and position is not None:
        # Dynamic target: a swing high that confirmed after entry and sits
        # closer than the current target tightens it (still the OPPOSITE
        # swing, just the nearest one known now).
        tighter = _nearest_high_above(position["entry"])
        if tighter is not None and tighter < position["tp"]:
            position["tp"] = tighter
        exit_now = None
        if bar["l"] <= position["sl"]:
            exit_now = "stop"
        elif bar["h"] >= position["tp"]:
            exit_now = "target"
        elif seq - position["entry_seq"] >= TIME_STOP_BARS:
            exit_now = "time"
        if exit_now is not None:
            if exit_now == "stop":
                last_stop_seq = seq
                if position["swing_key"] is not None:
                    invalidated.add(position["swing_key"])
            exiting = True
            return _sell_order(state)
        return []

    # Holding without a plan (defensive; unreachable in normal flow): manage
    # it with a fallback stop/target rather than leaving it unmanaged.
    if holding and position is None:
        position = _open_plan(bar["c"], None)
        position["entry_seq"] = seq
        return []

    # A buy was sent but its fill has not landed yet: wait, do not re-enter.
    if position is not None and not holding:
        return []

    # --- entries (flat, no pending buy) ---
    if seq >= LAST_ENTRY_SEQ:
        return []
    if seq < FIRST_ENTRY_SEQ:
        return []
    if seq - last_stop_seq < COOLDOWN_BARS:
        return []

    # Last resort: guarantee at least one filled trade on a dead day.
    # (Exempt from the trip cap: it only fires when nothing filled at all.)
    if filled_trades == 0 and seq >= LAST_RESORT_SEQ:
        position = _open_plan(bar["c"], None)
        return _buy_order(state, state.cash)

    # Frequency cap: after MAX_TRIPS round trips the day is done, however
    # good the next setup looks — marginal trades are pure cost.
    if trips_closed >= MAX_TRIPS:
        return []

    if prev is None:
        return []

    # Hail mary: a strong engulfing anywhere once the day is nearly spent.
    # (Also capped: it only fires when nothing filled yet, so the cap
    # above cannot have been reached — kept here for clarity.)
    if filled_trades == 0 and seq >= HAIL_MARY_SEQ:
        if (bar["c"] > bar["o"] and prev["c"] < prev["o"]
                and bar["o"] <= prev["c"] and bar["c"] >= prev["o"]
                and bps_of(bar["c"] - bar["o"], bar["c"]) >= HAIL_BODY_MIN_BPS):
            swing = _swing_at_low(bar)
            position = _open_plan(bar["c"], swing)
            return _buy_order(state, state.cash)

    # Main entry: bullish engulfing at a confirmed swing low, with the
    # 15-minute structure agreeing (no lower lows).
    if _regime_ok() and _is_bull_engulfing(prev, bar):
        swing = _swing_at_low(bar)
        if swing is not None:
            position = _open_plan(bar["c"], swing)
            return _buy_order(state, state.cash)
    return []


makefun_bars.run(on_batch)

"""
Scalp Engine — Monitors hot list tickers on 1-minute charts via TradingView.
Detects precise entry signals: VWAP pullback, momentum breakout, ORB breakout.
Called every 2 minutes by the scalp monitoring loop in live_scanner.py.
"""
from __future__ import annotations
import datetime
import logging
import threading
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


# ─────────────────────────────────────────────────────────────
#  ScalpSetup — represents a refined scalp entry
# ─────────────────────────────────────────────────────────────

@dataclass
class ScalpSetup:
    ticker: str
    setup_type: str           # "VWAP_PULLBACK", "MOMENTUM_BREAK", "ORB_BREAKOUT",
                              # "IV_CRUSH_PUT", "GAMMA_SQUEEZE_CALL", "VWAP_RECLAIM_CALL",
                              # "BREAKDOWN_PUT", "BOLLINGER_SQUEEZE"
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_1: float = 0.0     # 50% scale-out
    target_2: float = 0.0     # full exit
    risk_reward: float = 0.0
    urgency: str = "WAITING"  # "NOW", "WAITING", "FADING"
    timeframe: str = "1"
    screenshot_png: bytes = None
    greeks: dict = field(default_factory=dict)
    option_contract: str = ""
    timestamp: str = ""
    # Options-specific fields
    pnl_scenarios: dict = field(default_factory=dict)
    iv_rank: float = 0.0
    spread_pct: float = 0.0
    real_bid: float = 0.0
    real_ask: float = 0.0


# ─────────────────────────────────────────────────────────────
#  ORB Tracker — Opening Range Breakout
# ─────────────────────────────────────────────────────────────

_orb_ranges = {}  # ticker → {"high": float, "low": float, "complete": bool}
_orb_lock = threading.Lock()


def _reset_orb_if_new_day():
    """Clear ORB data at market open."""
    now = datetime.datetime.now(ET)
    today = now.date()
    key = "_orb_date"
    if _orb_ranges.get(key) != today:
        with _orb_lock:
            _orb_ranges.clear()
            _orb_ranges[key] = today


def record_orb_bar(ticker: str, high: float, low: float):
    """Record a bar during the ORB window (9:30-9:45 ET)."""
    with _orb_lock:
        if ticker not in _orb_ranges:
            _orb_ranges[ticker] = {"high": high, "low": low, "complete": False}
        else:
            entry = _orb_ranges[ticker]
            entry["high"] = max(entry["high"], high)
            entry["low"] = min(entry["low"], low)


def _mark_orb_complete(ticker: str):
    with _orb_lock:
        if ticker in _orb_ranges:
            _orb_ranges[ticker]["complete"] = True


def _get_orb(ticker: str) -> dict | None:
    return _orb_ranges.get(ticker)


# ─────────────────────────────────────────────────────────────
#  Scalp Alert Cooldown
# ─────────────────────────────────────────────────────────────

_scalp_cooldown = {}  # ticker → last_alert_time


def _check_scalp_cooldown(ticker: str) -> bool:
    """Return True if we can alert on this ticker."""
    cooldown = getattr(settings, "SCALP_COOLDOWN_SECONDS", 300)
    now = datetime.datetime.now(ET)
    last = _scalp_cooldown.get(ticker)
    if last and (now - last).total_seconds() < cooldown:
        return False
    return True


def _record_scalp_alert(ticker: str):
    _scalp_cooldown[ticker] = datetime.datetime.now(ET)


# ─────────────────────────────────────────────────────────────
#  Signal Detectors
# ─────────────────────────────────────────────────────────────

def detect_vwap_pullback(price: float, indicators: dict, pick) -> ScalpSetup | None:
    """Detect a VWAP pullback entry on the 1-minute chart.

    Fires when price touches VWAP and RSI is in the sweet spot.
    """
    rsi = indicators.get("RSI")
    if rsi is None:
        return None
    try:
        rsi = float(rsi)
    except (ValueError, TypeError):
        return None

    phase = getattr(pick, "kinematic_phase", "")
    direction = getattr(pick, "direction", "LONG")

    # Only for longs in momentum phases pulling back
    if direction != "LONG" or phase not in ("ACCELERATION", "CRUISE", "IGNITION"):
        return None

    # RSI should be in the pullback zone (not overbought)
    if rsi < 30 or rsi > 60:
        return None

    # Check if price is near a support/entry level
    entry = getattr(pick, "entry_price", 0)
    atr = getattr(pick, "atr", 0)
    if atr <= 0 or entry <= 0:
        return None

    # Price within 0.3% of entry zone = pullback to support
    tolerance = getattr(settings, "SCALP_VWAP_TOLERANCE", 0.0015) * 2
    if abs(price - entry) / entry > tolerance:
        return None

    # Compute scalp levels
    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    stop = price - atr * stop_mult
    target_1 = price + atr * t1_mult
    target_2 = price + atr * t2_mult
    risk = price - stop
    rr = (target_2 - price) / risk if risk > 0 else 0

    # Urgency: FADING if RSI approaching overbought
    urgency = "NOW" if rsi < 45 else "WAITING"

    return ScalpSetup(
        ticker=pick.ticker,
        setup_type="VWAP_PULLBACK",
        entry_price=price,
        stop_price=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        risk_reward=round(rr, 1),
        urgency=urgency,
        timeframe="1",
        timestamp=datetime.datetime.now(ET).strftime("%H:%M:%S"),
    )


def detect_momentum_breakout(price: float, indicators: dict, pick) -> ScalpSetup | None:
    """Detect a momentum breakout — new intraday high with volume surge."""
    phase = getattr(pick, "kinematic_phase", "")
    rvol = getattr(pick, "rel_volume", 0)
    direction = getattr(pick, "direction", "LONG")

    if direction != "LONG":
        return None
    if phase not in ("IGNITION", "ACCELERATION"):
        return None
    if rvol < 2.0:
        return None

    # Check MACD histogram is positive (confirming momentum)
    macd_hist = indicators.get("Histogram")
    if macd_hist is not None:
        try:
            if float(macd_hist) <= 0:
                return None
        except (ValueError, TypeError):
            pass

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    resistance = getattr(pick, "nearest_resistance", 0)
    # Price should be near or above resistance (breaking out)
    if resistance > 0 and price < resistance * 0.998:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    stop = price - atr * stop_mult
    target_1 = price + atr * t1_mult
    target_2 = price + atr * t2_mult
    risk = price - stop
    rr = (target_2 - price) / risk if risk > 0 else 0

    urgency = "NOW" if rvol >= 3.0 else "WAITING"

    return ScalpSetup(
        ticker=pick.ticker,
        setup_type="MOMENTUM_BREAK",
        entry_price=price,
        stop_price=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        risk_reward=round(rr, 1),
        urgency=urgency,
        timeframe="1",
        timestamp=datetime.datetime.now(ET).strftime("%H:%M:%S"),
    )


def detect_orb_breakout(price: float, ticker: str, indicators: dict, pick) -> ScalpSetup | None:
    """Detect an Opening Range Breakout after 9:45 AM ET."""
    now = datetime.datetime.now(ET)

    # Only valid 9:45 - 10:30 AM ET
    orb_end_str = getattr(settings, "SCALP_ORB_END", "09:45")
    window_end_str = getattr(settings, "SCALP_ORB_WINDOW_END", "10:30")
    orb_end = datetime.time(int(orb_end_str[:2]), int(orb_end_str[3:]))
    window_end = datetime.time(int(window_end_str[:2]), int(window_end_str[3:]))

    if now.time() < orb_end or now.time() > window_end:
        return None

    orb = _get_orb(ticker)
    if orb is None or not orb.get("complete"):
        return None

    orb_high = orb["high"]
    orb_low = orb["low"]
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return None

    direction = getattr(pick, "direction", "LONG")
    rvol = getattr(pick, "rel_volume", 0)

    # Long breakout: price above ORB high
    if direction == "LONG" and price > orb_high and rvol >= 1.5:
        stop = orb_low
        target_1 = orb_high + orb_range       # measured move 1x
        target_2 = orb_high + orb_range * 1.5  # measured move 1.5x
        risk = price - stop
        rr = (target_2 - price) / risk if risk > 0 else 0

        return ScalpSetup(
            ticker=ticker,
            setup_type="ORB_BREAKOUT",
            entry_price=price,
            stop_price=round(stop, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            risk_reward=round(rr, 1),
            urgency="NOW",
            timeframe="1",
            timestamp=now.strftime("%H:%M:%S"),
        )

    # Short breakout: price below ORB low
    if direction == "SHORT" and price < orb_low and rvol >= 1.5:
        stop = orb_high
        target_1 = orb_low - orb_range
        target_2 = orb_low - orb_range * 1.5
        risk = stop - price
        rr = (price - target_2) / risk if risk > 0 else 0

        return ScalpSetup(
            ticker=ticker,
            setup_type="ORB_BREAKOUT",
            entry_price=price,
            stop_price=round(stop, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            risk_reward=round(rr, 1),
            urgency="NOW",
            timeframe="1",
            timestamp=now.strftime("%H:%M:%S"),
        )

    return None


# ─────────────────────────────────────────────────────────────
#  Options Signal Detectors (5 new)
# ─────────────────────────────────────────────────────────────

def _is_past_0dte_cutoff() -> bool:
    """Check if past the 0DTE entry cutoff (default 2:00 PM ET)."""
    cutoff_str = getattr(settings, "OPT_SCALP_0DTE_CUTOFF", "14:00")
    cutoff = datetime.time(int(cutoff_str[:2]), int(cutoff_str[3:]))
    return datetime.datetime.now(ET).time() > cutoff


def _hours_to_close() -> float:
    """Hours remaining until 4:00 PM ET close."""
    now = datetime.datetime.now(ET)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    diff = (close - now).total_seconds() / 3600.0
    return max(diff, 0.01)


def _build_options_setup(
    ticker: str, setup_type: str, price: float, atr: float,
    direction: str, strike_data: dict, chain_data: dict,
    iv_info: dict, stop_price: float, target_1: float, target_2: float,
    urgency: str = "NOW",
) -> ScalpSetup | None:
    """Build a ScalpSetup with real chain data and P&L scenarios attached."""
    try:
        from analysis.options.pnl_scenarios import compute_scenarios, format_scenario_plain_english

        risk = abs(price - stop_price)
        reward = abs(target_2 - price)
        rr = reward / risk if risk > 0 else 0

        bid = strike_data.get("bid", 0)
        ask = strike_data.get("ask", 0)
        iv = strike_data.get("iv", chain_data.get("atm_iv", 0.30))
        dte_hours = max(chain_data.get("dte_days", 1.0) * 6.5, 0.1)
        is_0dte = chain_data.get("is_0dte", False)

        if is_0dte:
            dte_hours = _hours_to_close()

        scenarios = compute_scenarios(
            entry_price=price, strike=strike_data.get("strike", round(price)),
            direction=direction, iv=iv, dte_hours=dte_hours,
            bid=bid, ask=ask, stop_price=stop_price,
            target_1=target_1, target_2=target_2,
            hold_minutes=30.0,
        )

        dte_label = "0DTE" if is_0dte else chain_data.get("expiry", "")
        strike_val = strike_data.get("strike", round(price))

        setup = ScalpSetup(
            ticker=ticker,
            setup_type=setup_type,
            entry_price=price,
            stop_price=round(stop_price, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            risk_reward=round(rr, 1),
            urgency=urgency,
            timeframe="1",
            timestamp=datetime.datetime.now(ET).strftime("%H:%M:%S"),
            option_contract=f"{ticker} ${strike_val:.0f} {direction.upper()} {dte_label}",
            greeks={
                "delta": strike_data.get("delta", 0),
                "gamma": strike_data.get("gamma", 0),
                "theta": strike_data.get("theta", 0),
                "vega": strike_data.get("vega", 0),
            },
            pnl_scenarios=scenarios,
            iv_rank=iv_info.get("iv_rank", 0),
            spread_pct=strike_data.get("spread_pct", 0),
            real_bid=bid,
            real_ask=ask,
        )
        return setup

    except Exception as e:
        logger.debug("_build_options_setup error: %s", e)
        return None


def detect_iv_crush_put(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict,
) -> ScalpSetup | None:
    """Overbought stock + expensive premium → ATM PUT for mean reversion.

    Trigger: RSI > 70 + IV rank > 60% + MACD declining + price stalling.
    """
    rsi = indicators.get("RSI")
    if rsi is None:
        return None
    try:
        rsi = float(rsi)
    except (ValueError, TypeError):
        return None

    if rsi < 70:
        return None

    # IV rank must be elevated (premiums expensive = bigger crush potential)
    iv_rank = iv_info.get("iv_rank", 50)
    if iv_rank < getattr(settings, "OPT_SCALP_IV_RANK_MIN", 20):
        return None
    if iv_rank < 60:
        return None

    # MACD histogram declining (momentum fading)
    macd_hist = indicators.get("Histogram")
    if macd_hist is not None:
        try:
            if float(macd_hist) > 0:
                return None  # still positive momentum — skip
        except (ValueError, TypeError):
            pass

    if not strike_data:
        return None

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    # PUT direction: stop above, targets below
    stop_price = price + atr * stop_mult
    target_1 = price - atr * t1_mult
    target_2 = price - atr * t2_mult

    return _build_options_setup(
        ticker=pick.ticker, setup_type="IV_CRUSH_PUT", price=price, atr=atr,
        direction="put", strike_data=strike_data, chain_data=chain_data,
        iv_info=iv_info, stop_price=stop_price, target_1=target_1, target_2=target_2,
        urgency="NOW" if rsi > 80 else "WAITING",
    )


def detect_gamma_squeeze_call(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict, pcr_data: dict, mp_data: dict,
) -> ScalpSetup | None:
    """Price approaching max pain + call OI dominance + volume surge → ATM CALL.

    MM delta hedging pushes price through max pain when call OI >> put OI.
    """
    max_pain = mp_data.get("max_pain", 0)
    if max_pain <= 0:
        return None

    # Price should be approaching max pain from below (within 1%)
    if price > max_pain * 1.01 or price < max_pain * 0.97:
        return None

    # Call OI must dominate put OI (2x+)
    call_oi = pcr_data.get("call_oi", 0)
    put_oi = pcr_data.get("put_oi", 1)
    if call_oi < put_oi * 2:
        return None

    # Volume surge
    rvol = getattr(pick, "rel_volume", 0)
    if rvol < 1.5:
        return None

    # MACD must be positive (confirming upward momentum)
    macd_hist = indicators.get("Histogram")
    if macd_hist is not None:
        try:
            if float(macd_hist) <= 0:
                return None
        except (ValueError, TypeError):
            pass

    if not strike_data:
        return None

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)

    stop_price = price - atr * stop_mult
    target_1 = max_pain + atr * 0.5   # just past max pain
    target_2 = max_pain + atr * 1.5   # overshoot

    return _build_options_setup(
        ticker=pick.ticker, setup_type="GAMMA_SQUEEZE_CALL", price=price, atr=atr,
        direction="call", strike_data=strike_data, chain_data=chain_data,
        iv_info=iv_info, stop_price=stop_price, target_1=target_1, target_2=target_2,
        urgency="NOW" if rvol >= 2.5 else "WAITING",
    )


def detect_vwap_reclaim_call(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict,
) -> ScalpSetup | None:
    """Price reclaims VWAP from below + volume spike + RSI 40-60 → ATM CALL.

    Classic intraday reversal: price dipped below VWAP, now reclaims with volume.
    """
    rsi = indicators.get("RSI")
    if rsi is None:
        return None
    try:
        rsi = float(rsi)
    except (ValueError, TypeError):
        return None

    # RSI in neutral zone (not overbought, not oversold) — fresh move
    if rsi < 40 or rsi > 60:
        return None

    # Volume must be above average
    rvol = getattr(pick, "rel_volume", 0)
    if rvol < 1.5:
        return None

    # We need VWAP — check if price is just above a support/entry level
    # (VWAP approximated by the entry_price from the pick)
    vwap_est = getattr(pick, "entry_price", 0)
    if vwap_est <= 0:
        return None

    # Price must be slightly above VWAP (just reclaimed) — within 0.3%
    pct_above_vwap = (price - vwap_est) / vwap_est if vwap_est > 0 else 999
    if pct_above_vwap < 0 or pct_above_vwap > 0.003:
        return None

    if not strike_data:
        return None

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    stop_price = vwap_est - atr * 0.5  # stop below VWAP
    target_1 = price + atr * t1_mult
    target_2 = price + atr * t2_mult

    return _build_options_setup(
        ticker=pick.ticker, setup_type="VWAP_RECLAIM_CALL", price=price, atr=atr,
        direction="call", strike_data=strike_data, chain_data=chain_data,
        iv_info=iv_info, stop_price=stop_price, target_1=target_1, target_2=target_2,
        urgency="NOW",
    )


def detect_breakdown_put(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict,
) -> ScalpSetup | None:
    """Price breaks support + put volume surge + RSI < 40 + MACD negative → ATM PUT.

    Confirmed breakdown: momentum + volume confirm the break.
    """
    rsi = indicators.get("RSI")
    if rsi is None:
        return None
    try:
        rsi = float(rsi)
    except (ValueError, TypeError):
        return None

    if rsi > 40:
        return None

    # MACD must be negative
    macd_hist = indicators.get("Histogram")
    if macd_hist is not None:
        try:
            if float(macd_hist) >= 0:
                return None
        except (ValueError, TypeError):
            pass

    # Needs some volume confirmation
    rvol = getattr(pick, "rel_volume", 0)
    if rvol < 1.2:
        return None

    # Price below support (entry_price from pick represents a key level)
    support = getattr(pick, "entry_price", 0)
    if support <= 0:
        return None
    if price > support * 0.998:
        return None  # hasn't broken down yet

    if not strike_data:
        return None

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    # PUT targets: stop above support, targets below
    stop_price = support + atr * 0.3  # tight stop just above broken support
    target_1 = price - atr * t1_mult
    target_2 = price - atr * t2_mult

    return _build_options_setup(
        ticker=pick.ticker, setup_type="BREAKDOWN_PUT", price=price, atr=atr,
        direction="put", strike_data=strike_data, chain_data=chain_data,
        iv_info=iv_info, stop_price=stop_price, target_1=target_1, target_2=target_2,
        urgency="NOW" if rsi < 30 else "WAITING",
    )


def detect_bollinger_squeeze(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict,
) -> ScalpSetup | None:
    """Bollinger Band squeeze breakout: BB width at low + ADX rising + MACD cross.

    Direction follows MACD cross. Squeeze = compressed volatility about to explode.
    """
    # Need Bollinger Bands width — check for BB upper/lower in indicators
    bb_upper = indicators.get("Upper Band") or indicators.get("BB Upper")
    bb_lower = indicators.get("Lower Band") or indicators.get("BB Lower")
    bb_basis = indicators.get("Basis") or indicators.get("BB Middle")

    if bb_upper is None or bb_lower is None:
        return None

    try:
        bb_upper = float(bb_upper)
        bb_lower = float(bb_lower)
        bb_basis_val = float(bb_basis) if bb_basis else (bb_upper + bb_lower) / 2
    except (ValueError, TypeError):
        return None

    if bb_basis_val <= 0:
        return None

    bb_width = (bb_upper - bb_lower) / bb_basis_val
    # Width must be tight — squeeze condition (< 4% of basis is tight)
    if bb_width > 0.04:
        return None

    # ADX should be rising (building momentum during squeeze)
    adx = indicators.get("ADX") or indicators.get("Average Directional Index")
    if adx is not None:
        try:
            adx = float(adx)
            if adx < 20:
                return None  # no directional movement
        except (ValueError, TypeError):
            pass

    # MACD cross determines direction
    macd_hist = indicators.get("Histogram")
    if macd_hist is None:
        return None
    try:
        macd_hist = float(macd_hist)
    except (ValueError, TypeError):
        return None

    direction = "call" if macd_hist > 0 else "put"

    if not strike_data:
        return None

    atr = getattr(pick, "atr", 0)
    if atr <= 0:
        return None

    stop_mult = getattr(settings, "SCALP_ATR_STOP_MULT", 0.75)
    t1_mult = getattr(settings, "SCALP_ATR_TARGET1_MULT", 1.0)
    t2_mult = getattr(settings, "SCALP_ATR_TARGET2_MULT", 2.0)

    if direction == "call":
        stop_price = price - atr * stop_mult
        target_1 = price + atr * t1_mult
        target_2 = price + atr * t2_mult
    else:
        stop_price = price + atr * stop_mult
        target_1 = price - atr * t1_mult
        target_2 = price - atr * t2_mult

    return _build_options_setup(
        ticker=pick.ticker, setup_type="BOLLINGER_SQUEEZE", price=price, atr=atr,
        direction=direction, strike_data=strike_data, chain_data=chain_data,
        iv_info=iv_info, stop_price=stop_price, target_1=target_1, target_2=target_2,
        urgency="NOW" if abs(macd_hist) > 0.1 else "WAITING",
    )


# ─────────────────────────────────────────────────────────────
#  Options Integration
# ─────────────────────────────────────────────────────────────

def _attach_options_to_setup(setup: ScalpSetup, pick) -> None:
    """If the stock has options, compute scalp-specific option contract."""
    if not getattr(pick, "option_exp_short", ""):
        return
    if pick.option_exp_short == "N/A":
        return

    try:
        from analysis.options_math import compute_full_greeks, select_scalp_strike
    except ImportError:
        return

    price = setup.entry_price
    atr = getattr(pick, "atr", 0)
    iv = getattr(pick, "option_iv_est", 30) / 100  # stored as %
    direction = "call" if getattr(pick, "direction", "LONG") == "LONG" else "put"

    # Determine if 0DTE or weekly
    now = datetime.datetime.now(ET)
    days_to_friday = (4 - now.weekday()) % 7
    if days_to_friday == 0 and now.hour >= 14:
        days_to_friday = 7  # past 2pm Friday → next week
    dte = max(days_to_friday, 0.01)  # at least a fraction for 0DTE

    # Use 0DTE if today is a trading day and before 2pm
    is_0dte = days_to_friday == 0 and now.hour < 14

    try:
        strike_info = select_scalp_strike(price, atr, direction, dte, iv)
        greeks = compute_full_greeks(price, strike_info["strike"], dte, iv, 0.05, direction)
    except Exception:
        return

    # Expected profit at target 1
    move = setup.target_1 - price
    delta = greeks.get("delta", 0.5)
    gamma = greeks.get("gamma", 0)
    est_profit = abs(delta) * move + 0.5 * gamma * move ** 2
    cost = greeks.get("premium_est", price * 0.02)  # rough premium estimate

    dte_label = "0DTE" if is_0dte else pick.option_exp_short
    setup.option_contract = f"{pick.ticker} ${strike_info['strike']:.0f} {direction.upper()} {dte_label}"
    setup.greeks = {
        "delta": round(delta, 2),
        "gamma": round(gamma, 4),
        "theta_daily": round(greeks.get("theta", 0), 2),
        "vega": round(greeks.get("vega", 0), 2),
        "expected_profit": round(est_profit, 2),
        "expected_pct": round(est_profit / cost * 100, 0) if cost > 0 else 0,
        "cost_per_contract": round(cost, 2),
    }


# ─────────────────────────────────────────────────────────────
#  Main Monitor Loop
# ─────────────────────────────────────────────────────────────

def _fetch_options_context(ticker: str, price: float, direction: str) -> tuple:
    """Fetch chain data, optimal strike, IV rank, PCR, and max pain for a ticker.

    Returns (chain_data, strike_data, iv_info, pcr_data, mp_data).
    All empty dicts on failure — never raises.
    """
    chain_data, strike_data, iv_info, pcr_data, mp_data = {}, {}, {}, {}, {}
    try:
        from analysis.options.chain_analyzer import get_scalp_chain, compute_iv_rank, select_optimal_strike
        from analysis.options.pcr_analyzer import get_pcr, get_max_pain

        chain_data = get_scalp_chain(ticker, price, direction)
        if chain_data:
            dte = chain_data.get("dte_days", 1.0)
            strike_data = select_optimal_strike(chain_data, price, direction, dte)
            atm_iv = chain_data.get("atm_iv", 0.30)
            iv_info = compute_iv_rank(ticker, atm_iv)

        pcr_data = get_pcr(ticker)
        mp_data = get_max_pain(ticker)

    except Exception as e:
        logger.debug("_fetch_options_context(%s) error: %s", ticker, e)

    return chain_data, strike_data, iv_info, pcr_data, mp_data


def _run_options_detectors(
    price: float, indicators: dict, pick,
    chain_data: dict, strike_data: dict, iv_info: dict,
    pcr_data: dict, mp_data: dict,
) -> ScalpSetup | None:
    """Run 5 options signal detectors — first match wins."""
    if not strike_data:
        return None

    # Don't enter 0DTE positions after cutoff
    if chain_data.get("is_0dte") and _is_past_0dte_cutoff():
        return None

    return (
        detect_iv_crush_put(price, indicators, pick, chain_data, strike_data, iv_info)
        or detect_gamma_squeeze_call(price, indicators, pick, chain_data, strike_data, iv_info, pcr_data, mp_data)
        or detect_vwap_reclaim_call(price, indicators, pick, chain_data, strike_data, iv_info)
        or detect_breakdown_put(price, indicators, pick, chain_data, strike_data, iv_info)
        or detect_bollinger_squeeze(price, indicators, pick, chain_data, strike_data, iv_info)
    )


# Track options alerts per day to enforce daily cap
_opt_scalp_day_count = {"date": None, "count": 0}


def monitor_hot_list(hot_list: list) -> list[ScalpSetup]:
    """Monitor hot list tickers on 1-minute TradingView charts.

    For each ticker:
    1. Navigate TV → read indicators
    2. Run 3 stock detectors (ORB, momentum, VWAP pullback)
    3. Fetch real options chain data (IV, bid/ask, volume, OI)
    4. Run 5 options detectors (IV crush, gamma squeeze, VWAP reclaim, breakdown, BB squeeze)
    5. Attach P&L scenarios to any setup

    Takes ~4 seconds per ticker (chain fetch adds ~1s).
    """
    if not hot_list:
        return []

    _reset_orb_if_new_day()

    # Reset daily options cap
    today = datetime.date.today()
    if _opt_scalp_day_count["date"] != today:
        _opt_scalp_day_count["date"] = today
        _opt_scalp_day_count["count"] = 0

    try:
        from signals.tradingview_bridge import (
            is_tv_available, set_symbol, set_timeframe,
            get_study_values, capture_screenshot, clear_drawings,
            draw_horizontal_line, tv_lock,
        )
    except ImportError:
        logger.debug("TradingView bridge not available for scalp monitoring")
        return []

    if not is_tv_available():
        return []

    opt_scalp_enabled = getattr(settings, "OPT_SCALP_ENABLED", True)
    daily_cap = getattr(settings, "OPT_SCALP_DAILY_CAP", 8)

    setups = []
    now = datetime.datetime.now(ET)

    with tv_lock:
        for pick in hot_list:
            ticker = pick.ticker
            if not _check_scalp_cooldown(ticker):
                continue

            try:
                # Navigate TV to 1-minute chart
                if not set_symbol(ticker):
                    continue
                set_timeframe("1")

                import time
                time.sleep(0.5)

                # Read indicator values
                studies = get_study_values()
                indicators = {}
                if studies:
                    for study in studies:
                        for k, v in study.get("values", {}).items():
                            try:
                                indicators[k] = float(str(v).replace(",", "").replace("\u202f", ""))
                            except (ValueError, TypeError):
                                indicators[k] = v

                price = getattr(pick, "price", 0)

                # During ORB window, record the range
                orb_start_str = getattr(settings, "SCALP_ORB_START", "09:30")
                orb_end_str = getattr(settings, "SCALP_ORB_END", "09:45")
                orb_start = datetime.time(int(orb_start_str[:2]), int(orb_start_str[3:]))
                orb_end = datetime.time(int(orb_end_str[:2]), int(orb_end_str[3:]))

                if orb_start <= now.time() <= orb_end:
                    record_orb_bar(ticker, price * 1.001, price * 0.999)  # approximate from current
                elif now.time() > orb_end:
                    _mark_orb_complete(ticker)

                # ── Phase A: Stock detectors (3) — first match wins ──
                setup = (
                    detect_orb_breakout(price, ticker, indicators, pick)
                    or detect_momentum_breakout(price, indicators, pick)
                    or detect_vwap_pullback(price, indicators, pick)
                )

                if setup:
                    # Attach options via legacy method for stock-based setups
                    _attach_options_to_setup(setup, pick)

                # ── Phase B: Options detectors (5) — only if no stock setup ──
                if not setup and opt_scalp_enabled and _opt_scalp_day_count["count"] < daily_cap:
                    direction_guess = "call" if getattr(pick, "direction", "LONG") == "LONG" else "put"
                    chain_data, strike_data, iv_info, pcr_data, mp_data = _fetch_options_context(
                        ticker, price, direction_guess,
                    )

                    # Also try opposite direction for specific detectors
                    opp_dir = "put" if direction_guess == "call" else "call"
                    opp_chain, opp_strike, _, _, _ = {}, {}, {}, {}, {}
                    if chain_data:
                        # Re-select strike for opposite direction from same chain
                        try:
                            from analysis.options.chain_analyzer import get_scalp_chain, select_optimal_strike
                            opp_chain = get_scalp_chain(ticker, price, opp_dir)
                            if opp_chain:
                                opp_strike = select_optimal_strike(
                                    opp_chain, price, opp_dir, opp_chain.get("dte_days", 1.0),
                                )
                        except Exception:
                            pass

                    # Run detectors — try both directions
                    setup = _run_options_detectors(
                        price, indicators, pick,
                        chain_data, strike_data, iv_info, pcr_data, mp_data,
                    )

                    # If primary direction didn't fire, try opposite for put/call-specific detectors
                    if not setup and opp_chain and opp_strike:
                        setup = _run_options_detectors(
                            price, indicators, pick,
                            opp_chain, opp_strike, iv_info, pcr_data, mp_data,
                        )

                    if setup:
                        _opt_scalp_day_count["count"] += 1

                # ── Capture screenshot + record alert ──
                if setup:
                    try:
                        draw_horizontal_line(setup.entry_price, "#2196F3", 2, "Entry")
                        draw_horizontal_line(setup.stop_price, "#F44336", 2, "Stop")
                        draw_horizontal_line(setup.target_1, "#4CAF50", 2, "T1")
                        draw_horizontal_line(setup.target_2, "#4CAF50", 1, "T2")
                        time.sleep(0.3)
                        setup.screenshot_png = capture_screenshot("chart")
                        clear_drawings()
                    except Exception:
                        pass

                    _record_scalp_alert(ticker)
                    setups.append(setup)
                    logger.info("Scalp signal: %s %s at $%.2f", ticker, setup.setup_type, price)

            except Exception as e:
                logger.debug("Scalp monitor error for %s: %s", ticker, e)

    return setups

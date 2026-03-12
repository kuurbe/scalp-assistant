"""
Event card generation — creates structured event cards for different catalyst types.
Cards represent actionable market events detected across the scoring pipeline.
"""
import datetime
import logging
import re

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Event type constants
# ─────────────────────────────────────────────────────────────
EARNINGS_ALERT = "EARNINGS_ALERT"
FDA_CATALYST = "FDA_CATALYST"
POLITICAL_SHIFT = "POLITICAL_SHIFT"
WAR_ESCALATION = "WAR_ESCALATION"
INFLUENCER_SIGNAL = "INFLUENCER_SIGNAL"
CRYPTO_REGULATORY = "CRYPTO_REGULATORY"
MACRO_SHIFT = "MACRO_SHIFT"
SPARK_DETECTED = "SPARK_DETECTED"
DIP_OPPORTUNITY = "DIP_OPPORTUNITY"
INSIDER_BUY = "INSIDER_BUY"
OPTIONS_FLOW = "OPTIONS_FLOW"
FEAR_EXTREME = "FEAR_EXTREME"

# Keyword sets for catalyst detection
_EARNINGS_KEYWORDS = re.compile(
    r"earnings|EPS|revenue|guidance|beat|miss|quarterly|q[1-4]|profit|loss",
    re.IGNORECASE,
)
_FDA_KEYWORDS = re.compile(
    r"FDA|clinical|trial|phase\s*[1-3]|PDUFA|approval|NDA|BLA|drug|therapy|biotech",
    re.IGNORECASE,
)
_CRYPTO_REGULATORY_KEYWORDS = re.compile(
    r"SEC|regulation|crypto|bitcoin|ethereum|stablecoin|CBDC|digital\s*asset|token",
    re.IGNORECASE,
)

# Crypto tickers (yfinance and proxy forms)
_CRYPTO_TICKERS = set(settings.CRYPTO_UNIVERSE) | {
    "MARA", "RIOT", "CLSK", "COIN", "MSTR", "HOOD",
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
}


# ─────────────────────────────────────────────────────────────
#  Core: generate a single event card
# ─────────────────────────────────────────────────────────────
def generate_event_card(
    event_type: str,
    title: str,
    urgency: str,
    tickers: list,
    direction: str,
    details: str = "",
) -> dict:
    """
    Build a structured event card dict.

    Args:
        event_type: One of the event type constants (EARNINGS_ALERT, etc.)
        title: Human-readable card title
        urgency: "HIGH", "MEDIUM", or "LOW"
        tickers: List of affected ticker symbols
        direction: "BULLISH", "BEARISH", or "NEUTRAL"
        details: Optional extra context string

    Returns:
        dict with keys: event_type, title, urgency, tickers, direction,
                        timestamp, details, action_suggestion
    """
    try:
        urgency = urgency.upper() if urgency else "MEDIUM"
        if urgency not in ("HIGH", "MEDIUM", "LOW"):
            urgency = "MEDIUM"

        direction = direction.upper() if direction else "NEUTRAL"
        if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
            direction = "NEUTRAL"

        tickers = [t.upper() for t in (tickers or []) if t]

        action = _build_action_suggestion(event_type, tickers, direction)

        return {
            "event_type": event_type,
            "title": title,
            "urgency": urgency,
            "tickers": tickers,
            "direction": direction,
            "timestamp": datetime.datetime.now().isoformat(),
            "details": details,
            "action_suggestion": action,
        }
    except Exception:
        logger.debug("Failed to generate event card for %s", event_type, exc_info=True)
        return {
            "event_type": event_type,
            "title": title or "Unknown Event",
            "urgency": "LOW",
            "tickers": tickers or [],
            "direction": "NEUTRAL",
            "timestamp": datetime.datetime.now().isoformat(),
            "details": details or "",
            "action_suggestion": "",
        }


# ─────────────────────────────────────────────────────────────
#  Detect all event cards from scored tickers + context
# ─────────────────────────────────────────────────────────────
def detect_event_cards(
    scored_tickers: list,
    political_pulse: dict = None,
    war_watch: dict = None,
    influencer_pulse: dict = None,
    macro_context: dict = None,
) -> list:
    """
    Scan all scored tickers and context data to generate relevant event cards.

    Args:
        scored_tickers: list of ScoredTicker objects from composite_scorer
        political_pulse: dict from political_tracker (risk_level, events, etc.)
        war_watch: dict from war_tracker (risk_level, conflicts, etc.)
        influencer_pulse: dict from influencer_tracker (active_influencers, etc.)
        macro_context: dict from FRED fetcher (vix, yield_curve_spread, etc.)

    Returns:
        list of event card dicts, sorted by urgency (HIGH first)
    """
    cards = []
    political_pulse = political_pulse or {}
    war_watch = war_watch or {}
    influencer_pulse = influencer_pulse or {}
    macro_context = macro_context or {}

    try:
        # Per-ticker event detection
        for pick in (scored_tickers or []):
            try:
                cards.extend(_detect_ticker_cards(pick))
            except Exception:
                logger.debug("Error detecting cards for %s", getattr(pick, "ticker", "?"), exc_info=True)

        # Global context events
        cards.extend(_detect_political_cards(political_pulse))
        cards.extend(_detect_war_cards(war_watch))
        cards.extend(_detect_influencer_cards(influencer_pulse, scored_tickers))
        cards.extend(_detect_macro_cards(macro_context))
        cards.extend(_detect_fear_extreme_cards())
        cards.extend(_detect_insider_cards(scored_tickers))
        cards.extend(_detect_options_flow_cards(scored_tickers))

    except Exception:
        logger.debug("Error in detect_event_cards", exc_info=True)

    # Sort: HIGH > MEDIUM > LOW
    urgency_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    cards.sort(key=lambda c: urgency_order.get(c.get("urgency", "LOW"), 9))

    return cards


# ─────────────────────────────────────────────────────────────
#  Format event card for notification text
# ─────────────────────────────────────────────────────────────
def format_event_card_text(card: dict) -> str:
    """
    Format an event card into a readable notification string.

    Returns:
        Multi-line formatted string suitable for Telegram/Discord/terminal.
    """
    try:
        urgency = card.get("urgency", "MEDIUM")
        urgency_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(urgency, "⚪")
        direction = card.get("direction", "NEUTRAL")
        dir_icon = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}.get(direction, "➡️")

        tickers_str = ", ".join(card.get("tickers", [])) or "N/A"
        ts = card.get("timestamp", "")
        if ts:
            try:
                dt = datetime.datetime.fromisoformat(ts)
                ts = dt.strftime("%I:%M %p")
            except Exception:
                pass

        lines = [
            f"{urgency_icon} [{card.get('event_type', 'EVENT')}] {card.get('title', 'Alert')}",
            f"   Urgency: {urgency} | Direction: {dir_icon} {direction}",
            f"   Tickers: {tickers_str}",
        ]

        details = card.get("details", "")
        if details:
            lines.append(f"   Details: {details}")

        action = card.get("action_suggestion", "")
        if action:
            lines.append(f"   >> {action}")

        if ts:
            lines.append(f"   Time: {ts}")

        return "\n".join(lines)

    except Exception:
        logger.debug("Error formatting event card", exc_info=True)
        return f"[EVENT] {card.get('title', 'Unknown')} — {', '.join(card.get('tickers', []))}"


# ─────────────────────────────────────────────────────────────
#  Private helpers
# ─────────────────────────────────────────────────────────────

def _detect_ticker_cards(pick) -> list:
    """Detect event cards from a single ScoredTicker."""
    cards = []
    ticker = getattr(pick, "ticker", "")
    score = getattr(pick, "composite_score", 0)
    catalyst_summary = getattr(pick, "catalyst_summary", "") or ""
    kinematic_phase = getattr(pick, "kinematic_phase", "")
    regime = getattr(pick, "regime", "")
    pct_change = getattr(pick, "pct_change", 0)
    direction_raw = getattr(pick, "direction", "LONG")

    direction = "BULLISH" if direction_raw == "LONG" else "BEARISH"

    # EARNINGS_ALERT: catalyst contains earnings keywords and score >= 60
    if _EARNINGS_KEYWORDS.search(catalyst_summary) and score >= 60:
        urgency = "HIGH" if score >= 75 else "MEDIUM"
        cards.append(generate_event_card(
            event_type=EARNINGS_ALERT,
            title=f"Earnings catalyst on {ticker}",
            urgency=urgency,
            tickers=[ticker],
            direction=direction,
            details=catalyst_summary[:120],
        ))

    # FDA_CATALYST: catalyst contains FDA/clinical keywords
    if _FDA_KEYWORDS.search(catalyst_summary):
        urgency = "HIGH" if score >= 60 else "MEDIUM"
        cards.append(generate_event_card(
            event_type=FDA_CATALYST,
            title=f"FDA/Clinical catalyst on {ticker}",
            urgency=urgency,
            tickers=[ticker],
            direction=direction,
            details=catalyst_summary[:120],
        ))

    # CRYPTO_REGULATORY: crypto ticker with political/regulatory catalyst
    if ticker in _CRYPTO_TICKERS and _CRYPTO_REGULATORY_KEYWORDS.search(catalyst_summary):
        cards.append(generate_event_card(
            event_type=CRYPTO_REGULATORY,
            title=f"Crypto regulatory event for {ticker}",
            urgency="HIGH" if score >= 60 else "MEDIUM",
            tickers=[ticker],
            direction=direction,
            details=catalyst_summary[:120],
        ))

    # SPARK_DETECTED: kinematic IGNITION + score >= 60
    if kinematic_phase == "IGNITION" and score >= 60:
        cards.append(generate_event_card(
            event_type=SPARK_DETECTED,
            title=f"Momentum ignition on {ticker}",
            urgency="HIGH",
            tickers=[ticker],
            direction="BULLISH",
            details=f"Score {score:.0f} | Phase: {kinematic_phase} | Vol: {getattr(pick, 'rel_volume', 0):.1f}x",
        ))

    # DIP_OPPORTUNITY: mean-reverting regime + significant drop
    if regime in ("CLEAN_REVERSION", "MEAN_REVERTING") and pct_change < -2:
        cards.append(generate_event_card(
            event_type=DIP_OPPORTUNITY,
            title=f"Dip entry on {ticker} ({pct_change:+.1f}%)",
            urgency="HIGH" if pct_change < -5 else "MEDIUM",
            tickers=[ticker],
            direction="BULLISH",
            details=f"Regime: {regime} | Drop: {pct_change:+.1f}% | Score: {score:.0f}",
        ))

    return cards


def _detect_political_cards(political_pulse: dict) -> list:
    """Detect POLITICAL_SHIFT cards from political pulse data."""
    cards = []
    try:
        risk = (political_pulse.get("risk_level") or "").upper()
        if risk in ("HIGH", "EXTREME"):
            theme = political_pulse.get("dominant_theme", "Policy change")
            affected = political_pulse.get("affected_tickers", [])
            if not affected:
                affected = political_pulse.get("top_affected", [])
            tickers = [t if isinstance(t, str) else t.get("ticker", "") for t in affected[:5]]
            tickers = [t for t in tickers if t]

            cards.append(generate_event_card(
                event_type=POLITICAL_SHIFT,
                title=f"Political shift: {theme}",
                urgency="HIGH" if risk == "EXTREME" else "MEDIUM",
                tickers=tickers or ["SPY"],
                direction="BEARISH" if risk == "EXTREME" else "NEUTRAL",
                details=f"Risk level: {risk} | Theme: {theme}",
            ))
    except Exception:
        logger.debug("Error detecting political cards", exc_info=True)
    return cards


def _detect_war_cards(war_watch: dict) -> list:
    """Detect WAR_ESCALATION cards from war watch data."""
    cards = []
    try:
        risk = (war_watch.get("risk_level") or "").upper()
        if risk in ("HIGH", "EXTREME"):
            region = war_watch.get("hotspot", war_watch.get("region", "Unknown"))
            affected = war_watch.get("affected_tickers", [])
            tickers = [t if isinstance(t, str) else t.get("ticker", "") for t in affected[:5]]
            tickers = [t for t in tickers if t]

            # Defense and energy benefit from escalation
            cards.append(generate_event_card(
                event_type=WAR_ESCALATION,
                title=f"Conflict escalation: {region}",
                urgency="HIGH",
                tickers=tickers or ["XLE", "GLD"],
                direction="BEARISH",
                details=f"Risk level: {risk} | Region: {region}",
            ))
    except Exception:
        logger.debug("Error detecting war cards", exc_info=True)
    return cards


def _detect_influencer_cards(influencer_pulse: dict, scored_tickers: list = None) -> list:
    """Detect INFLUENCER_SIGNAL cards from influencer pulse data."""
    cards = []
    try:
        active = influencer_pulse.get("active_influencers", [])
        for inf in active:
            try:
                impact = inf.get("impact", 0)
                if impact >= getattr(settings, "INFLUENCER_HIGH_IMPACT", 80):
                    name = inf.get("name", "Unknown influencer")
                    tickers = inf.get("tickers", inf.get("mentioned_tickers", []))
                    if isinstance(tickers, str):
                        tickers = [tickers]
                    sentiment = (inf.get("sentiment") or "").upper()
                    direction = "BULLISH" if sentiment in ("BULLISH", "POSITIVE") else (
                        "BEARISH" if sentiment in ("BEARISH", "NEGATIVE") else "NEUTRAL"
                    )

                    cards.append(generate_event_card(
                        event_type=INFLUENCER_SIGNAL,
                        title=f"Influencer signal: {name}",
                        urgency="HIGH" if impact >= 90 else "MEDIUM",
                        tickers=tickers[:5],
                        direction=direction,
                        details=f"Impact: {impact} | Sentiment: {sentiment}",
                    ))
            except Exception:
                logger.debug("Error processing influencer entry", exc_info=True)

        # Elon alert shortcut
        if influencer_pulse.get("elon_alert"):
            elon_tickers = influencer_pulse.get("elon_tickers", ["TSLA"])
            cards.append(generate_event_card(
                event_type=INFLUENCER_SIGNAL,
                title="Elon Musk activity detected",
                urgency="HIGH",
                tickers=elon_tickers if isinstance(elon_tickers, list) else [elon_tickers],
                direction="NEUTRAL",
                details="High-impact social media activity from Elon Musk",
            ))
    except Exception:
        logger.debug("Error detecting influencer cards", exc_info=True)
    return cards


def _detect_macro_cards(macro_context: dict) -> list:
    """Detect MACRO_SHIFT cards from macro context data."""
    cards = []
    try:
        vix = macro_context.get("vix", 0) or 0
        yield_spread = macro_context.get("yield_curve_spread", macro_context.get("T10Y2Y", None))

        # VIX > 25 — danger zone
        if vix > 25:
            urgency = "HIGH" if vix > 35 else "MEDIUM"
            cards.append(generate_event_card(
                event_type=MACRO_SHIFT,
                title=f"VIX elevated at {vix:.1f}",
                urgency=urgency,
                tickers=["SPY", "QQQ", "UVXY"],
                direction="BEARISH",
                details=f"VIX at {vix:.1f} — elevated fear, reduce position sizes",
            ))

        # Yield curve inversion
        if yield_spread is not None and yield_spread < 0:
            cards.append(generate_event_card(
                event_type=MACRO_SHIFT,
                title=f"Yield curve inverted ({yield_spread:+.2f}%)",
                urgency="MEDIUM",
                tickers=["TLT", "XLF", "SPY"],
                direction="BEARISH",
                details=f"10Y-2Y spread: {yield_spread:+.2f}% — recession signal",
            ))

    except Exception:
        logger.debug("Error detecting macro cards", exc_info=True)
    return cards


def _build_action_suggestion(event_type: str, tickers: list, direction: str) -> str:
    """Build a contextual action suggestion string for an event card."""
    try:
        primary = tickers[0] if tickers else "the ticker"

        suggestions = {
            EARNINGS_ALERT: {
                "BULLISH": f"Consider CALL options on {primary} into earnings",
                "BEARISH": f"Consider PUT options on {primary} — weak earnings expected",
                "NEUTRAL": f"Watch {primary} for post-earnings move, straddle may work",
            },
            FDA_CATALYST: {
                "BULLISH": f"Consider CALL options on {primary} ahead of FDA catalyst",
                "BEARISH": f"Watch for dip entry on {primary} — FDA risk priced in",
                "NEUTRAL": f"Monitor {primary} closely — FDA binary event ahead",
            },
            POLITICAL_SHIFT: {
                "BULLISH": f"Policy tailwind — look for entries on {primary}",
                "BEARISH": f"Political headwind — reduce exposure to {primary}",
                "NEUTRAL": f"Monitor policy developments impacting {primary}",
            },
            WAR_ESCALATION: {
                "BULLISH": f"Defense/energy benefit — consider {primary}",
                "BEARISH": f"Risk-off — hedge with GLD, reduce {primary} exposure",
                "NEUTRAL": f"Watch geopolitical developments impacting {primary}",
            },
            INFLUENCER_SIGNAL: {
                "BULLISH": f"Influencer bullish on {primary} — watch for momentum entry",
                "BEARISH": f"Influencer bearish on {primary} — caution advised",
                "NEUTRAL": f"Influencer activity on {primary} — monitor for direction",
            },
            CRYPTO_REGULATORY: {
                "BULLISH": f"Regulatory clarity positive for {primary} — consider entry",
                "BEARISH": f"Regulatory risk on {primary} — reduce crypto exposure",
                "NEUTRAL": f"Regulatory uncertainty for {primary} — wait for clarity",
            },
            MACRO_SHIFT: {
                "BULLISH": f"Macro tailwind — increase exposure",
                "BEARISH": f"Macro headwind — reduce position sizes, favor hedges",
                "NEUTRAL": f"Macro uncertainty — tighten stops, A+ setups only",
            },
            SPARK_DETECTED: {
                "BULLISH": f"Consider CALL options on {primary} — momentum ignition",
                "BEARISH": f"Unusual — short squeeze potential on {primary}",
                "NEUTRAL": f"Spark detected on {primary} — confirm direction before entry",
            },
            DIP_OPPORTUNITY: {
                "BULLISH": f"Watch for dip entry on {primary} — mean reversion setup",
                "BEARISH": f"Falling knife on {primary} — wait for confirmation",
                "NEUTRAL": f"Potential dip buy on {primary} — set alerts at support",
            },
            INSIDER_BUY: {
                "BULLISH": f"Insider buying on {primary} — smart money accumulation",
                "BEARISH": f"Insider selling on {primary} — consider reducing exposure",
                "NEUTRAL": f"Mixed insider activity on {primary} — monitor closely",
            },
            OPTIONS_FLOW: {
                "BULLISH": f"Unusual put/call ratio on {primary} — contrarian bullish signal",
                "BEARISH": f"Heavy put buying on {primary} — bearish options flow",
                "NEUTRAL": f"Unusual options activity on {primary} — watch for direction",
            },
            FEAR_EXTREME: {
                "BULLISH": f"Extreme fear — historically a buying opportunity",
                "BEARISH": f"Extreme greed — market may be overextended",
                "NEUTRAL": f"Fear & Greed at extreme — be cautious with new positions",
            },
        }

        type_map = suggestions.get(event_type, {})
        return type_map.get(direction, f"Monitor {primary} for actionable setup")

    except Exception:
        logger.debug("Error building action suggestion", exc_info=True)
        return ""


def _detect_fear_extreme_cards() -> list:
    """Generate FEAR_EXTREME card when Fear & Greed hits extremes."""
    cards = []
    try:
        from data.fetchers.fear_greed_fetcher import get_fear_greed
        fg = get_fear_greed()
        if not fg:
            return cards
        score = fg.get("score", 50)
        rating = fg.get("rating", "")
        if score <= 20:
            cards.append(generate_event_card(
                event_type=FEAR_EXTREME,
                title=f"Extreme Fear — F&G Index at {score:.0f}",
                urgency="HIGH",
                tickers=["SPY", "QQQ"],
                direction="BULLISH",
                details=f"Fear & Greed: {score:.0f} ({rating}) — historically a contrarian buy signal",
            ))
        elif score >= 80:
            cards.append(generate_event_card(
                event_type=FEAR_EXTREME,
                title=f"Extreme Greed — F&G Index at {score:.0f}",
                urgency="HIGH",
                tickers=["SPY", "QQQ"],
                direction="BEARISH",
                details=f"Fear & Greed: {score:.0f} ({rating}) — market may be overextended",
            ))
    except Exception:
        logger.debug("Error detecting fear extreme cards", exc_info=True)
    return cards


def _detect_insider_cards(scored_tickers: list) -> list:
    """Generate INSIDER_BUY cards for tickers with notable insider activity."""
    cards = []
    try:
        from data.fetchers.insider_fetcher import get_insider_summary
        for pick in (scored_tickers or [])[:20]:
            ticker = getattr(pick, "ticker", "")
            if not ticker:
                continue
            try:
                summary = get_insider_summary(ticker)
                if not summary:
                    continue
                net = summary.get("net_insider_buys", 0)
                sentiment = summary.get("sentiment", "")
                if sentiment == "BULLISH" and net >= 3:
                    cards.append(generate_event_card(
                        event_type=INSIDER_BUY,
                        title=f"Insider buying on {ticker} ({net} net buys)",
                        urgency="HIGH" if net >= 5 else "MEDIUM",
                        tickers=[ticker],
                        direction="BULLISH",
                        details=f"{net} net insider purchases in last 90 days",
                    ))
            except Exception:
                continue
    except Exception:
        logger.debug("Error detecting insider cards", exc_info=True)
    return cards


def _detect_options_flow_cards(scored_tickers: list) -> list:
    """Generate OPTIONS_FLOW cards for tickers with unusual put/call ratios."""
    cards = []
    try:
        from analysis.options.pcr_analyzer import get_pcr, classify_options_sentiment
        for pick in (scored_tickers or [])[:15]:
            ticker = getattr(pick, "ticker", "")
            if not ticker:
                continue
            try:
                pcr_data = get_pcr(ticker)
                if not pcr_data:
                    continue
                pcr = pcr_data.get("pcr", 0)
                if pcr <= 0:
                    continue
                sentiment = classify_options_sentiment(pcr)
                if pcr > 1.5 or pcr < 0.4:
                    direction = "BULLISH" if pcr > 1.5 else "BEARISH"
                    cards.append(generate_event_card(
                        event_type=OPTIONS_FLOW,
                        title=f"Unusual options flow on {ticker} (PCR {pcr:.2f})",
                        urgency="HIGH" if (pcr > 2.0 or pcr < 0.3) else "MEDIUM",
                        tickers=[ticker],
                        direction=direction,
                        details=f"Put/Call Ratio: {pcr:.2f} — {sentiment} | "
                                f"Put OI: {pcr_data.get('put_oi', 0):,} | Call OI: {pcr_data.get('call_oi', 0):,}",
                    ))
            except Exception:
                continue
    except Exception:
        logger.debug("Error detecting options flow cards", exc_info=True)
    return cards

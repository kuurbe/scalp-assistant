"""
War & geopolitical conflict tracker.

Monitors ongoing wars, military conflicts, and geopolitical tensions,
then maps detected escalations to market-impact signals (tickers,
commodities, safe-haven demand, energy risk).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from data.cache import cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional fetcher imports — use same named functions as political_tracker
# ---------------------------------------------------------------------------
try:
    from data.fetchers.geopolitical_rss import get_geopolitical_news as _get_geo_news
except Exception:  # noqa: BLE001
    _get_geo_news = None

try:
    from data.fetchers.reddit_expanded import (
        get_political_discourse as _get_reddit_political,
    )
except Exception:  # noqa: BLE001
    _get_reddit_political = None

# Fallback: use news_aggregator for conflict keyword scanning
try:
    from catalyst.news_aggregator import aggregate_news as _aggregate_news
except Exception:  # noqa: BLE001
    _aggregate_news = None

# ---------------------------------------------------------------------------
# Active conflict definitions
# ---------------------------------------------------------------------------
ACTIVE_CONFLICTS: dict[str, dict[str, Any]] = {
    "UKRAINE_RUSSIA": {
        "keywords": [
            "ukraine", "russia", "kyiv", "moscow", "crimea",
            "donbas", "zelensky", "putin", "nato expansion",
        ],
        "affected_assets": {
            "XLE": "UP", "GLD": "UP", "WEAT": "UP",
            "SPY": "DOWN", "RSX": "DOWN",
        },
        "commodity_impact": ["oil", "natural gas", "wheat", "palladium"],
        "severity": "HIGH",
    },
    "MIDDLE_EAST": {
        "keywords": [
            "israel", "gaza", "hamas", "hezbollah", "iran", "houthi",
            "red sea", "strait of hormuz", "oil tanker", "syria", "lebanon",
        ],
        "affected_assets": {
            "XLE": "UP", "GLD": "UP", "XLI": "DOWN", "USO": "UP",
        },
        "commodity_impact": ["oil", "gold"],
        "severity": "HIGH",
    },
    "CHINA_TAIWAN": {
        "keywords": [
            "taiwan", "china military", "strait", "tsmc", "pla",
            "south china sea", "chip war", "semiconductor ban",
        ],
        "affected_assets": {
            "TSM": "DOWN", "NVDA": "DOWN", "AMD": "DOWN",
            "INTC": "UP", "GLD": "UP",
        },
        "commodity_impact": ["semiconductors", "rare earth"],
        "severity": "CRITICAL",
    },
    "TRADE_WAR": {
        "keywords": [
            "trade war", "tariff escalation", "decoupling", "reshoring",
            "export controls", "chip ban",
        ],
        "affected_assets": {
            "FXI": "DOWN", "BABA": "DOWN", "SPY": "DOWN", "GLD": "UP",
        },
        "commodity_impact": ["steel", "aluminum", "soybeans"],
        "severity": "MEDIUM",
    },
    "AFRICA_INSTABILITY": {
        "keywords": [
            "coup", "africa conflict", "niger", "sudan", "sahel",
            "military junta", "mining disruption",
        ],
        "affected_assets": {"GLD": "UP", "XLE": "UP"},
        "commodity_impact": ["gold", "uranium", "cobalt"],
        "severity": "LOW",
    },
}

# Severity ordering (higher index == more severe)
_SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "EXTREME"]

# Baseline article counts per window – used to detect surges.
_BASELINE_ARTICLE_COUNTS: dict[str, int] = {
    "UKRAINE_RUSSIA": 8,
    "MIDDLE_EAST": 6,
    "CHINA_TAIWAN": 4,
    "TRADE_WAR": 5,
    "AFRICA_INSTABILITY": 3,
}

# Multiplier thresholds for escalation classification.
_ESCALATION_THRESHOLDS = {
    "DE_ESCALATING": 0.5,
    "ONGOING": 1.0,
    "ESCALATING": 1.8,
    "NEW": 0,  # sentinel – handled separately
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _severity_index(sev: str) -> int:
    """Return numeric index for a severity string (0 = lowest)."""
    try:
        return _SEVERITY_ORDER.index(sev.upper())
    except (ValueError, AttributeError):
        return 0


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """Return *True* if *text* contains any of the *keywords* (case-insensitive)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _classify_escalation_level(article_count: int, conflict_id: str) -> str:
    """Classify escalation level by comparing *article_count* to baseline."""
    baseline = _BASELINE_ARTICLE_COUNTS.get(conflict_id, 5)
    if baseline == 0:
        return "NEW" if article_count > 0 else "ONGOING"

    ratio = article_count / baseline
    if ratio >= _ESCALATION_THRESHOLDS["ESCALATING"]:
        return "ESCALATING"
    if ratio <= _ESCALATION_THRESHOLDS["DE_ESCALATING"]:
        return "DE_ESCALATING"
    return "ONGOING"


def _market_direction_for_conflict(conflict_id: str) -> str:
    """Infer an overall market direction string for a given conflict."""
    conflict = ACTIVE_CONFLICTS.get(conflict_id, {})
    assets: dict[str, str] = conflict.get("affected_assets", {})
    downs = sum(1 for d in assets.values() if d == "DOWN")
    ups = sum(1 for d in assets.values() if d == "UP")
    if downs > ups:
        return "BEARISH"
    if ups > downs:
        return "MIXED_BULLISH_COMMODITIES"
    return "NEUTRAL"


def _fetch_news_items() -> list[dict]:
    """Aggregate news items from available fetcher sources.

    Each item is expected to carry at least ``{"headline": str, ...}``.
    Returns an empty list when no fetchers are available or on error.
    """
    items: list[dict] = []

    # Primary: geopolitical RSS feeds (same source as political_tracker)
    try:
        if _get_geo_news is not None:
            result = _get_geo_news(max_items=80)
            if isinstance(result, list):
                items.extend(result)
    except Exception:  # noqa: BLE001
        logger.debug("geopolitical_rss fetch failed", exc_info=True)

    # Reddit political discourse
    try:
        if _get_reddit_political is not None:
            result = _get_reddit_political()
            if isinstance(result, list):
                for post in result:
                    items.append({
                        "headline": post.get("title", ""),
                        "summary": "",
                        "source": f"Reddit r/{post.get('subreddit', 'politics')}",
                    })
    except Exception:  # noqa: BLE001
        logger.debug("reddit_expanded fetch failed", exc_info=True)

    # Fallback: news_aggregator (Finnhub, Yahoo RSS, StockTwits)
    if not items and _aggregate_news is not None:
        try:
            for ticker in ("SPY", "QQQ", "GLD", "XLE"):
                news = _aggregate_news(ticker, max_items=20)
                if isinstance(news, list):
                    items.extend(news)
        except Exception:  # noqa: BLE001
            logger.debug("news_aggregator fallback failed", exc_info=True)

    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_conflict_escalation(news_items: list[dict]) -> list[dict]:
    """Classify *news_items* into conflict categories.

    Parameters
    ----------
    news_items:
        Each dict should contain at least a ``"headline"`` key. Additional
        keys (``"title"``, ``"text"``, ``"body"``) are also searched.

    Returns
    -------
    list[dict]
        Each entry contains::

            {
                "conflict_id": str,
                "headline": str,
                "severity": str,
                "escalation_level": str,   # NEW / ONGOING / ESCALATING / DE_ESCALATING
                "affected_assets": dict,
                "market_direction": str,
            }
    """
    try:
        if not news_items:
            return []

        # Count hits per conflict for escalation detection.
        hit_counts: dict[str, int] = {cid: 0 for cid in ACTIVE_CONFLICTS}
        results: list[dict] = []

        for item in news_items:
            try:
                searchable_text = " ".join(
                    str(item.get(k, ""))
                    for k in ("headline", "title", "text", "body", "summary")
                )
                if not searchable_text.strip():
                    continue

                for conflict_id, meta in ACTIVE_CONFLICTS.items():
                    if _match_keywords(searchable_text, meta["keywords"]):
                        hit_counts[conflict_id] += 1
                        results.append(
                            {
                                "conflict_id": conflict_id,
                                "headline": str(
                                    item.get("headline")
                                    or item.get("title")
                                    or ""
                                ),
                                "severity": meta["severity"],
                                "escalation_level": "",  # filled below
                                "affected_assets": dict(meta["affected_assets"]),
                                "market_direction": _market_direction_for_conflict(
                                    conflict_id
                                ),
                            }
                        )
            except Exception:  # noqa: BLE001
                logger.debug("Skipping malformed news item", exc_info=True)
                continue

        # Back-fill escalation levels based on aggregate hit counts.
        for entry in results:
            cid = entry["conflict_id"]
            entry["escalation_level"] = _classify_escalation_level(
                hit_counts.get(cid, 0), cid
            )

        return results
    except Exception:  # noqa: BLE001
        logger.exception("detect_conflict_escalation failed")
        return []


@cached(ttl=300)
def get_war_watch() -> dict:
    """Main entry point – returns a full conflict / market-risk snapshot.

    Returns
    -------
    dict
        ::

            {
                "active_conflicts": list[dict],
                "escalation_alerts": list[dict],
                "safe_haven_demand": str,       # LOW / MEDIUM / HIGH
                "energy_risk": str,             # LOW / MEDIUM / HIGH / CRITICAL
                "affected_tickers": dict,       # {ticker: direction}
                "risk_level": str,              # CALM / ELEVATED / HIGH / EXTREME
                "summary": str,
            }
    """
    try:
        news_items = _fetch_news_items()
        escalations = detect_conflict_escalation(news_items)

        # --- active conflicts ------------------------------------------------
        active_conflicts: list[dict] = []
        seen_conflicts: set[str] = set()
        for esc in escalations:
            cid = esc["conflict_id"]
            if cid not in seen_conflicts:
                seen_conflicts.add(cid)
                meta = ACTIVE_CONFLICTS[cid]
                active_conflicts.append(
                    {
                        "conflict_id": cid,
                        "severity": meta["severity"],
                        "escalation_level": esc["escalation_level"],
                        "commodity_impact": list(meta["commodity_impact"]),
                        "affected_assets": dict(meta["affected_assets"]),
                    }
                )

        # --- escalation alerts (only ESCALATING / NEW) -----------------------
        escalation_alerts = [
            e for e in escalations
            if e.get("escalation_level") in ("ESCALATING", "NEW")
        ]

        # --- aggregate tickers ------------------------------------------------
        affected_tickers: dict[str, str] = {}
        for esc in escalations:
            for ticker, direction in esc.get("affected_assets", {}).items():
                # If a ticker appears with conflicting directions keep the
                # bearish (DOWN) signal as the conservative choice.
                if ticker in affected_tickers:
                    if affected_tickers[ticker] != direction:
                        affected_tickers[ticker] = "DOWN"
                else:
                    affected_tickers[ticker] = direction

        # --- safe-haven demand ------------------------------------------------
        gold_up = affected_tickers.get("GLD") == "UP"
        bond_etf_tickers = {"TLT", "IEF", "SHY"}
        bond_bid = any(
            affected_tickers.get(t) == "UP" for t in bond_etf_tickers
        )
        severity_scores = [
            _severity_index(c.get("severity", "LOW")) for c in active_conflicts
        ]
        max_sev = max(severity_scores, default=0)

        if (gold_up and bond_bid) or max_sev >= 3:
            safe_haven_demand = "HIGH"
        elif gold_up or max_sev >= 2:
            safe_haven_demand = "MEDIUM"
        else:
            safe_haven_demand = "LOW"

        # --- energy risk ------------------------------------------------------
        energy_conflicts = {"UKRAINE_RUSSIA", "MIDDLE_EAST"}
        energy_escalating = any(
            c["conflict_id"] in energy_conflicts
            and c.get("escalation_level") == "ESCALATING"
            for c in active_conflicts
        )
        energy_active = any(
            c["conflict_id"] in energy_conflicts for c in active_conflicts
        )
        china_critical = any(
            c["conflict_id"] == "CHINA_TAIWAN"
            and c.get("escalation_level") == "ESCALATING"
            for c in active_conflicts
        )

        if energy_escalating and china_critical:
            energy_risk = "CRITICAL"
        elif energy_escalating:
            energy_risk = "HIGH"
        elif energy_active:
            energy_risk = "MEDIUM"
        else:
            energy_risk = "LOW"

        # --- overall risk level -----------------------------------------------
        num_escalating = len(escalation_alerts)
        if num_escalating >= 3 or max_sev >= 3:
            risk_level = "EXTREME"
        elif num_escalating >= 2 or max_sev >= 2:
            risk_level = "HIGH"
        elif num_escalating >= 1:
            risk_level = "ELEVATED"
        else:
            risk_level = "CALM"

        # --- summary ----------------------------------------------------------
        if not active_conflicts:
            summary = "No active geopolitical conflict signals detected."
        else:
            conflict_names = ", ".join(c["conflict_id"] for c in active_conflicts)
            summary = (
                f"{len(active_conflicts)} active conflict(s) tracked "
                f"({conflict_names}); risk level {risk_level}, "
                f"energy risk {energy_risk}, safe-haven demand {safe_haven_demand}."
            )

        return {
            "active_conflicts": active_conflicts,
            "escalation_alerts": escalation_alerts,
            "safe_haven_demand": safe_haven_demand,
            "energy_risk": energy_risk,
            "affected_tickers": affected_tickers,
            "risk_level": risk_level,
            "summary": summary,
        }

    except Exception:  # noqa: BLE001
        logger.exception("get_war_watch failed")
        return {
            "active_conflicts": [],
            "escalation_alerts": [],
            "safe_haven_demand": "LOW",
            "energy_risk": "LOW",
            "affected_tickers": {},
            "risk_level": "CALM",
            "summary": "Unable to retrieve war-watch data.",
        }


def get_ticker_war_exposure(ticker: str, war_data: dict) -> float:
    """Return a 0-100 score representing *ticker*'s exposure to active conflicts.

    Scoring methodology
    -------------------
    * Direct mention in a conflict's ``affected_assets`` adds 25 pts per
      conflict (capped contribution at 60).
    * Being in the ``DOWN`` direction adds an extra 10 pts per conflict.
    * Global risk level adds a baseline: CALM=0, ELEVATED=5, HIGH=10, EXTREME=20.
    * Energy-risk premium of 10 pts for energy-related tickers when energy
      risk is HIGH or CRITICAL.
    * The final score is clamped to [0, 100].

    Parameters
    ----------
    ticker:
        Uppercase ticker symbol, e.g. ``"XLE"``.
    war_data:
        Output of :func:`get_war_watch`.

    Returns
    -------
    float
        Exposure score between 0 and 100 (inclusive).
    """
    try:
        if not ticker or not isinstance(war_data, dict):
            return 0.0

        ticker = ticker.upper()
        score = 0.0

        # --- per-conflict contribution ------------------------------------
        conflict_contribution = 0.0
        active_conflicts = war_data.get("active_conflicts", [])
        for conflict in active_conflicts:
            assets: dict = conflict.get("affected_assets", {})
            if ticker in assets:
                sev = _severity_index(conflict.get("severity", "LOW"))
                base = 15 + (sev * 5)  # 15-30 depending on severity
                conflict_contribution += base
                if assets[ticker] == "DOWN":
                    conflict_contribution += 10
        score += min(conflict_contribution, 60.0)

        # --- global risk level baseline -----------------------------------
        risk_level = war_data.get("risk_level", "CALM")
        risk_bonus = {
            "CALM": 0,
            "ELEVATED": 5,
            "HIGH": 10,
            "EXTREME": 20,
        }.get(risk_level, 0)
        score += risk_bonus

        # --- energy-risk premium ------------------------------------------
        energy_tickers = {"XLE", "USO", "XOP", "OIH", "CVX", "XOM", "COP", "SLB"}
        energy_risk = war_data.get("energy_risk", "LOW")
        if ticker in energy_tickers and energy_risk in ("HIGH", "CRITICAL"):
            score += 10
        if ticker in energy_tickers and energy_risk == "CRITICAL":
            score += 5  # extra bump

        # --- safe-haven inverse bonus (safe havens get lower score) -------
        safe_havens = {"GLD", "TLT", "IEF", "SHY", "UUP"}
        if ticker in safe_havens:
            score = max(score - 10, 0)

        return max(0.0, min(100.0, round(score, 2)))

    except Exception:  # noqa: BLE001
        logger.debug("get_ticker_war_exposure failed for %s", ticker, exc_info=True)
        return 0.0

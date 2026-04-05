"""
Event contracts / prediction market fetcher.
Aggregates events from Polymarket (Gamma API) and Kalshi (public trade API).
All functions degrade gracefully — return empty lists on failure.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

import requests

from data.cache import cached

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  POLYMARKET (primary source — public Gamma API)
# ─────────────────────────────────────────────────────────────

POLYMARKET_API_URL = (
    "https://gamma-api.polymarket.com/events"
    "?closed=false&limit=30&order=volume24hr&ascending=false"
)

# Polymarket tag slug/label -> our category
_PM_CATEGORY_MAP = {
    "sports": "sports",
    "nba": "sports",
    "nfl": "sports",
    "mlb": "sports",
    "soccer": "sports",
    "politics": "politics",
    "elections": "politics",
    "us-elections": "politics",
    "trump": "politics",
    "economy": "economics",
    "economics": "economics",
    "business": "economics",
    "fed": "economics",
    "fed-rates": "economics",
    "economic-policy": "economics",
    "crypto": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "entertainment": "entertainment",
    "pop-culture": "entertainment",
    "pop culture": "entertainment",
    "science": "science",
    "technology": "technology",
    "ai": "technology",
}


def _normalize_pm_category(tags: list | None) -> str:
    """Map Polymarket tag objects to our standard category set.

    Tags from the Gamma API are objects like:
        {"id": "2", "label": "Politics", "slug": "politics", ...}
    """
    if not tags:
        return "other"
    for tag in tags:
        # Handle both object tags and plain strings
        if isinstance(tag, dict):
            slug = (tag.get("slug") or "").lower().strip()
            label = (tag.get("label") or "").lower().strip()
        else:
            slug = str(tag).lower().strip()
            label = slug

        mapped = _PM_CATEGORY_MAP.get(slug) or _PM_CATEGORY_MAP.get(label)
        if mapped:
            return mapped
    return "other"


def _parse_outcome_prices(raw) -> tuple[float | None, float | None]:
    """Parse outcomePrices from Polymarket — can be JSON string, list, or number."""
    if raw is None:
        return None, None

    # JSON string like '["0.95","0.05"]'
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) >= 2:
                yes_p = float(parsed[0])
                no_p = float(parsed[1])
                return yes_p, no_p
            elif isinstance(parsed, (int, float)):
                yes_p = float(parsed)
                return yes_p, round(1.0 - yes_p, 4)
        except (json.JSONDecodeError, ValueError, TypeError):
            try:
                yes_p = float(raw)
                return yes_p, round(1.0 - yes_p, 4)
            except ValueError:
                return None, None

    # Already a list
    if isinstance(raw, list) and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except (ValueError, TypeError):
            return None, None

    # Single number
    try:
        yes_p = float(raw)
        return yes_p, round(1.0 - yes_p, 4)
    except (ValueError, TypeError):
        return None, None


@cached(ttl=300)
def get_polymarket_events() -> list[dict]:
    """
    Fetch active event contracts from Polymarket's public Gamma API.

    Returns:
        List of event dicts with: title, category, yes_price, volume, etc.
        Returns empty list on failure.
    """
    try:
        resp = requests.get(
            POLYMARKET_API_URL,
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch Polymarket events: %s", e)
        return []
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse Polymarket response: %s", e)
        return []

    events = []

    # data is a list of events from the Gamma API
    items = data if isinstance(data, list) else data.get("data", data.get("events", []))

    for item in items:
        try:
            title = item.get("title") or item.get("question", "")
            if not title:
                continue

            tags = item.get("tags") or []
            category = _normalize_pm_category(tags)

            # Markets within the event (multiple outcomes)
            markets = item.get("markets", [])

            # Use the first / primary market for pricing
            yes_price = None
            no_price = None
            volume = 0

            if markets and isinstance(markets, list):
                primary = markets[0]
                yes_price, no_price = _parse_outcome_prices(primary.get("outcomePrices"))

                # Fallback to lastTradePrice
                if yes_price is None:
                    ltp = primary.get("lastTradePrice")
                    if ltp is not None:
                        try:
                            yes_price = float(ltp)
                            no_price = round(1.0 - yes_price, 4) if yes_price else None
                        except (ValueError, TypeError):
                            pass

                # Sum volume across all markets in this event
                for m in markets:
                    vol = m.get("volumeNum") or m.get("volume") or 0
                    try:
                        volume += int(float(vol))
                    except (ValueError, TypeError):
                        pass
            else:
                # Flat event structure (fallback)
                yes_price = float(item.get("yes_price", 0) or 0)
                no_price = float(item.get("no_price", 0) or 0)
                volume = int(float(item.get("volume", 0) or 0))

            # Use event-level volume24hr if market volumes are 0
            if volume == 0:
                try:
                    volume = int(float(item.get("volume24hr", 0) or 0))
                except (ValueError, TypeError):
                    volume = 0

            expires_at = item.get("endDate") or item.get("end_date") or ""
            slug = item.get("slug", "")
            event_url = f"https://polymarket.com/event/{slug}" if slug else ""

            events.append({
                "title": title,
                "category": category,
                "source": "polymarket",
                "yes_price": yes_price,
                "no_price": no_price,
                "volume": volume,
                "expires_at": expires_at,
                "url": event_url,
            })
        except Exception:
            continue

    logger.info("Fetched %d events from Polymarket", len(events))
    return events


# ─────────────────────────────────────────────────────────────
#  KALSHI (public trade API — no auth for market data)
# ─────────────────────────────────────────────────────────────

KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2/events"

# Kalshi category -> our category
_KALSHI_CATEGORY_MAP = {
    "politics": "politics",
    "economics": "economics",
    "financials": "economics",
    "climate and weather": "science",
    "world": "politics",
    "tech & science": "technology",
    "entertainment": "entertainment",
    "sports": "sports",
    "culture": "entertainment",
    "health": "science",
    "companies": "economics",
    "crypto": "crypto",
}


def _normalize_kalshi_category(category: str | None) -> str:
    """Map Kalshi category string to our standard category set."""
    if not category:
        return "other"
    return _KALSHI_CATEGORY_MAP.get(category.lower().strip(), "other")


@cached(ttl=300)
def get_kalshi_events() -> list[dict]:
    """
    Fetch active event contracts from Kalshi's public trade API.
    No authentication required for market data.

    Returns:
        List of event dicts with: title, category, yes_price, volume, etc.
        Returns empty list on failure.
    """
    try:
        resp = requests.get(
            KALSHI_API_URL,
            params={
                "status": "open",
                "with_nested_markets": "true",
                "limit": 50,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch Kalshi events: %s", e)
        return []
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse Kalshi response: %s", e)
        return []

    events = []
    items = data.get("events", [])

    for item in items:
        try:
            title = item.get("title", "")
            if not title:
                continue

            category = _normalize_kalshi_category(item.get("category"))
            markets = item.get("markets", [])

            yes_price = None
            no_price = None
            volume = 0

            if markets and isinstance(markets, list):
                primary = markets[0]

                # Kalshi prices are dollar strings like "0.63" = 63%
                lp = primary.get("last_price_dollars") or primary.get("yes_bid_dollars")
                if lp:
                    try:
                        yes_price = float(lp)
                        no_price = round(1.0 - yes_price, 4)
                    except (ValueError, TypeError):
                        pass

                # Sum volume across all markets in this event
                for m in markets:
                    vol = m.get("volume_24h_fp") or m.get("volume_fp") or 0
                    try:
                        volume += int(float(vol))
                    except (ValueError, TypeError):
                        pass

            event_ticker = item.get("event_ticker", "")
            event_url = f"https://kalshi.com/markets/{event_ticker}" if event_ticker else ""

            # Use first market's close_time as expiry
            expires_at = ""
            if markets:
                expires_at = markets[0].get("close_time", "")

            events.append({
                "title": title,
                "category": category,
                "source": "kalshi",
                "yes_price": yes_price,
                "no_price": no_price,
                "volume": volume,
                "expires_at": expires_at,
                "url": event_url,
            })
        except Exception:
            continue

    logger.info("Fetched %d events from Kalshi", len(events))
    return events


# ─────────────────────────────────────────────────────────────
#  AGGREGATOR
# ─────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_prediction_market_events() -> list[dict]:
    """
    Aggregate events from all prediction market sources, deduplicate
    by normalized title, and return a combined list.

    Returns:
        List of standardized event dicts sorted by volume (descending).
    """
    all_events = []

    # Fetch from all sources (each fails gracefully)
    try:
        all_events.extend(get_polymarket_events())
    except Exception as e:
        logger.debug("Polymarket aggregation error: %s", e)

    try:
        all_events.extend(get_kalshi_events())
    except Exception as e:
        logger.debug("Kalshi aggregation error: %s", e)

    # Deduplicate by normalized title — keep the entry with higher volume
    seen: dict[str, dict] = {}
    for event in all_events:
        key = event["title"].lower().strip()
        existing = seen.get(key)
        if existing is None or event.get("volume", 0) > existing.get("volume", 0):
            seen[key] = event

    deduped = list(seen.values())

    # Sort by volume descending (most active first)
    deduped.sort(key=lambda e: e.get("volume", 0), reverse=True)

    logger.info(
        "Aggregated %d unique prediction market events from %d total",
        len(deduped),
        len(all_events),
    )
    return deduped

"""
CoinGecko + Alternative.me crypto data fetcher.
Public APIs — no key required (CoinGecko: 30 req/min).
"""
import logging
import requests
from data.cache import cached

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
ALTERNATIVE_FNG_URL = "https://api.alternative.me/fng/"

_HEADERS = {"Accept": "application/json"}


@cached(ttl=300)
def get_global_crypto() -> dict:
    """Fetch global crypto market stats.

    Returns:
        {"total_market_cap_usd": 2.1e12, "btc_dominance": 52.3,
         "eth_dominance": 17.1, "total_volume_24h": 89e9,
         "active_cryptocurrencies": 14500, "market_cap_change_24h": -1.2}
    """
    try:
        resp = requests.get(f"{COINGECKO_BASE}/global", headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as e:
        logger.error("CoinGecko global fetch failed: %s", e)
        return {}

    try:
        mc = data.get("total_market_cap", {})
        vol = data.get("total_volume", {})
        mc_pct = data.get("market_cap_change_percentage_24h_usd", 0)

        return {
            "total_market_cap_usd": mc.get("usd", 0),
            "btc_dominance": round(data.get("market_cap_percentage", {}).get("btc", 0), 1),
            "eth_dominance": round(data.get("market_cap_percentage", {}).get("eth", 0), 1),
            "total_volume_24h": vol.get("usd", 0),
            "active_cryptocurrencies": data.get("active_cryptocurrencies", 0),
            "market_cap_change_24h": round(float(mc_pct), 2),
        }
    except Exception as e:
        logger.error("CoinGecko global parse failed: %s", e)
        return {}


@cached(ttl=300)
def get_trending_coins() -> list[dict]:
    """Fetch top 7 trending coins on CoinGecko.

    Returns:
        [{"name": "Bitcoin", "symbol": "BTC", "rank": 1,
          "market_cap_rank": 1, "price_btc": 1.0, "score": 0}, ...]
    """
    try:
        resp = requests.get(f"{COINGECKO_BASE}/search/trending", headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("CoinGecko trending fetch failed: %s", e)
        return []

    coins = []
    for item in data.get("coins", [])[:7]:
        c = item.get("item", {})
        coins.append({
            "name": c.get("name", ""),
            "symbol": c.get("symbol", "").upper(),
            "rank": c.get("score", 0) + 1,
            "market_cap_rank": c.get("market_cap_rank", 0),
            "price_btc": c.get("price_btc", 0),
            "thumb": c.get("thumb", ""),
        })
    return coins


@cached(ttl=300)
def get_crypto_fear_greed() -> dict:
    """Fetch crypto-specific Fear & Greed from Alternative.me.

    Returns:
        {"score": 35, "rating": "Fear", "timestamp": "1710100800"}
    """
    try:
        resp = requests.get(ALTERNATIVE_FNG_URL, params={"limit": 1}, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Crypto F&G fetch failed: %s", e)
        return {}

    try:
        entry = data.get("data", [{}])[0]
        return {
            "score": int(entry.get("value", 0)),
            "rating": entry.get("value_classification", "Neutral"),
            "timestamp": entry.get("timestamp", ""),
        }
    except Exception as e:
        logger.error("Crypto F&G parse failed: %s", e)
        return {}

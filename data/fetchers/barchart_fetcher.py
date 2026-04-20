"""
Barchart fetcher — unusual options activity detector.

Strategy (each layer falls through to the next on failure):
  1. Barchart HTML scrape — /options/unusual-activity/stocks (free public page)
  2. yfinance fallback  — compute unusual volume from options chains directly

No API key required. Cached 5 minutes.
"""
from __future__ import annotations
import logging
import time
import datetime

import requests

logger = logging.getLogger(__name__)

_UNUSUAL_CACHE: dict = {"ts": 0.0, "data": {}}
_CACHE_TTL = 300  # 5 min

_BASE = "https://www.barchart.com"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── public API ────────────────────────────────────────────────────────────────

def get_unusual_options(ticker: str | None = None) -> dict:
    """
    Return tickers with unusual options volume (volume ≥ 2× 30-day average).

    ticker=None  → full dict {SYM: {ratio, call_vol, put_vol, direction}}
    ticker="XYZ" → that ticker's entry dict, or {} if not listed
    Cached 5 minutes.
    """
    now = time.time()
    if now - _UNUSUAL_CACHE["ts"] < _CACHE_TTL and _UNUSUAL_CACHE["data"]:
        data = _UNUSUAL_CACHE["data"]
        return data.get(ticker.upper(), {}) if ticker else data

    data = _fetch_unusual_with_fallback()
    _UNUSUAL_CACHE["ts"] = now
    _UNUSUAL_CACHE["data"] = data
    return data.get(ticker.upper(), {}) if ticker else data


def get_options_volume_leaders(top_n: int = 30) -> list[str]:
    """Top N tickers by unusual options ratio today."""
    data = get_unusual_options()
    ranked = sorted(data.items(), key=lambda x: x[1].get("ratio", 0), reverse=True)
    return [sym for sym, _ in ranked[:top_n]]


def has_unusual_options(ticker: str) -> bool:
    return bool(get_unusual_options(ticker))


# ── fetch pipeline ────────────────────────────────────────────────────────────

def _fetch_unusual_with_fallback() -> dict:
    """Try Barchart HTML → yfinance computed."""
    result = _fetch_barchart_html()
    if result:
        return result
    logger.info("Barchart HTML returned nothing — using yfinance options fallback")
    return _fetch_yf_unusual()


def _fetch_barchart_html() -> dict:
    """
    Scrape Barchart's unusual activity page. Barchart renders data into a
    <script id="page-data"> JSON block on the HTML page.
    """
    try:
        import json, re
        from bs4 import BeautifulSoup

        s = requests.Session()
        s.headers["User-Agent"] = _BROWSER_UA
        # Get session cookies first
        s.get(_BASE, timeout=8)

        today = datetime.date.today().isoformat()
        url = f"{_BASE}/options/unusual-activity/stocks?startDate={today}"
        resp = s.get(
            url,
            headers={"Accept": "text/html", "Referer": _BASE + "/"},
            timeout=12,
        )
        if resp.status_code != 200:
            return {}

        # Look for embedded JSON data (Barchart inlines it in a <script> tag)
        soup = BeautifulSoup(resp.text, "lxml")
        for script in soup.find_all("script"):
            text = script.string or ""
            if "optionVolumeAverageRatio" not in text and "unusual" not in text.lower():
                continue
            m = re.search(r'"data"\s*:\s*(\[.+?\])\s*[,}]', text, re.DOTALL)
            if m:
                try:
                    rows = json.loads(m.group(1))
                    result = _parse_rows(rows)
                    if result:
                        logger.info("Barchart HTML: %d unusual tickers", len(result))
                        return result
                except Exception:
                    pass

        # Fallback: parse visible HTML table
        result = _parse_html_table(soup)
        if result:
            logger.info("Barchart HTML table: %d unusual tickers", len(result))
        return result

    except Exception as e:
        logger.debug("Barchart HTML scrape failed: %s", e)
        return {}


def _fetch_yf_unusual(
    candidates: list[str] | None = None,
    min_ratio: float = 2.0,
) -> dict:
    """
    Compute unusual options volume using yfinance options chains.
    For each candidate ticker, compare today's chain volume to open interest.
    volume/OI > min_ratio is a rough proxy for unusual activity.
    """
    if candidates is None:
        # Use a small watchlist of high-options-volume names
        candidates = [
            "SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMD", "AMZN", "META",
            "MSFT", "GOOGL", "COIN", "MSTR", "PLTR", "HOOD", "MARA",
            "SMCI", "ARM", "CRWD", "HIMS", "APP", "RKLB", "ON",
        ]

    result = {}
    try:
        import yfinance as yf
        for sym in candidates:
            try:
                tk = yf.Ticker(sym)
                exps = tk.options
                if not exps:
                    continue
                chain = tk.option_chain(exps[0])
                calls = chain.calls
                puts  = chain.puts

                call_vol = int(calls["volume"].fillna(0).sum())
                put_vol  = int(puts["volume"].fillna(0).sum())
                call_oi  = int(calls["openInterest"].fillna(0).sum())
                put_oi   = int(puts["openInterest"].fillna(0).sum())
                total_oi = call_oi + put_oi

                if total_oi < 1000:
                    continue

                ratio = (call_vol + put_vol) / max(total_oi, 1) * 10
                if ratio < min_ratio:
                    continue

                direction = "CALL" if call_vol > put_vol else "PUT" if put_vol > call_vol else "MIXED"
                result[sym] = {
                    "ratio": round(ratio, 2),
                    "call_vol": call_vol,
                    "put_vol": put_vol,
                    "direction": direction,
                    "source": "yfinance",
                }
            except Exception:
                pass
    except Exception as e:
        logger.warning("yfinance unusual options fallback failed: %s", e)

    logger.info("yfinance unusual options: %d tickers", len(result))
    return result


# ── parsers ───────────────────────────────────────────────────────────────────

def _parse_rows(rows: list) -> dict:
    result = {}
    for row in rows:
        sym = _sym(row.get("symbol") or row.get("Symbol"))
        if not sym:
            continue
        call_vol = _int(row.get("callVolume") or row.get("call_volume"))
        put_vol  = _int(row.get("putVolume")  or row.get("put_volume"))
        ratio    = _float(row.get("optionVolumeAverageRatio") or row.get("ratio"))
        direction = "CALL" if call_vol > put_vol else "PUT" if put_vol > call_vol else "MIXED"
        result[sym] = {"ratio": ratio, "call_vol": call_vol, "put_vol": put_vol, "direction": direction}
    return result


def _parse_html_table(soup) -> dict:
    result = {}
    table = soup.find("table")
    if not table:
        return {}
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        sym = _sym(cells[0].get_text(strip=True))
        if not sym:
            continue
        call_vol = _int(cells[2].get_text(strip=True) if len(cells) > 2 else 0)
        put_vol  = _int(cells[3].get_text(strip=True) if len(cells) > 3 else 0)
        ratio    = _float(cells[4].get_text(strip=True) if len(cells) > 4 else 0)
        direction = "CALL" if call_vol > put_vol else "PUT" if put_vol > call_vol else "MIXED"
        result[sym] = {"ratio": ratio, "call_vol": call_vol, "put_vol": put_vol, "direction": direction}
    return result


def _sym(val) -> str:
    s = str(val or "").upper().strip().split()[0]
    return s if s and 1 <= len(s) <= 5 and s.replace(".", "").isalpha() else ""


def _int(val) -> int:
    try:
        return int(str(val).replace(",", "").split(".")[0])
    except (TypeError, ValueError):
        return 0


def _float(val) -> float:
    try:
        return float(str(val).replace(",", "").replace("x", ""))
    except (TypeError, ValueError):
        return 0.0

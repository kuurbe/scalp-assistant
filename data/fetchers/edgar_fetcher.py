"""
SEC EDGAR fetcher — 8-K filings and material event classification.
Uses the SEC EDGAR API with required User-Agent header.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# ─────────────────────────────────────────────────────────────
#  8-K Item Decoder
# ─────────────────────────────────────────────────────────────
ITEM_DECODER = {
    "1.01": {"event_type": "Material Agreement", "urgency": "HIGH"},
    "1.02": {"event_type": "Termination of Material Agreement", "urgency": "HIGH"},
    "1.03": {"event_type": "Bankruptcy", "urgency": "HIGH"},
    "1.04": {"event_type": "Mine Safety", "urgency": "LOW"},
    "2.01": {"event_type": "Asset Acquisition/Disposition", "urgency": "HIGH"},
    "2.02": {"event_type": "Earnings Results", "urgency": "HIGH"},
    "2.03": {"event_type": "Creation of Obligation", "urgency": "MEDIUM"},
    "2.04": {"event_type": "Triggering Events", "urgency": "HIGH"},
    "2.05": {"event_type": "Cost of Exit Activities", "urgency": "MEDIUM"},
    "2.06": {"event_type": "Material Impairments", "urgency": "HIGH"},
    "3.01": {"event_type": "Delisting Notice", "urgency": "HIGH"},
    "3.02": {"event_type": "Unregistered Sale of Equity", "urgency": "MEDIUM"},
    "3.03": {"event_type": "Material Modification to Rights", "urgency": "MEDIUM"},
    "4.01": {"event_type": "Auditor Change", "urgency": "HIGH"},
    "4.02": {"event_type": "Non-Reliance on Financial Statements", "urgency": "HIGH"},
    "5.01": {"event_type": "Change in Control", "urgency": "HIGH"},
    "5.02": {"event_type": "Departure of Director/Officer", "urgency": "HIGH"},
    "5.03": {"event_type": "Amendments to Articles", "urgency": "MEDIUM"},
    "5.04": {"event_type": "Temporary Suspension of Trading", "urgency": "MEDIUM"},
    "5.05": {"event_type": "Amendments to Code of Ethics", "urgency": "LOW"},
    "5.06": {"event_type": "Change in Shell Company Status", "urgency": "MEDIUM"},
    "5.07": {"event_type": "Shareholder Vote Submission", "urgency": "LOW"},
    "5.08": {"event_type": "Shareholder Director Nominations", "urgency": "LOW"},
    "6.01": {"event_type": "ABS Servicer Info", "urgency": "LOW"},
    "6.02": {"event_type": "ABS Change of Servicer", "urgency": "LOW"},
    "6.03": {"event_type": "ABS Credit Enhancement Change", "urgency": "MEDIUM"},
    "6.04": {"event_type": "ABS Failure to Make Distribution", "urgency": "HIGH"},
    "6.05": {"event_type": "ABS Securities Act Update", "urgency": "LOW"},
    "7.01": {"event_type": "Regulation FD Disclosure", "urgency": "MEDIUM"},
    "8.01": {"event_type": "Other Events", "urgency": "LOW"},
    "9.01": {"event_type": "Financial Statements and Exhibits", "urgency": "LOW"},
}


def _get_sec_headers() -> dict:
    """Return headers with the required User-Agent for SEC EDGAR."""
    from config.settings import get_secret
    email = get_secret("SEC_EMAIL", "anonymous@example.com")
    return {
        "User-Agent": f"ScalpAssistant/3.0 ({email})",
        "Accept-Encoding": "gzip, deflate",
    }


@cached(ttl=86400)  # Cache CIK mapping for 24 hours
def _get_cik_mapping() -> dict:
    """
    Fetch the ticker -> CIK mapping from SEC.

    Returns:
        Dict mapping uppercase ticker symbols to zero-padded 10-digit CIK strings.
    """
    try:
        resp = requests.get(
            EDGAR_TICKERS_URL,
            headers=_get_sec_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        mapping = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = entry.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = str(cik).zfill(10)
        return mapping
    except Exception as e:
        logger.debug("Failed to fetch CIK mapping: %s", e)
        return {}


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_recent_8k_filings(ticker: str, days_back: int = 5) -> list[dict]:
    """
    Fetch recent 8-K filings for a ticker from EDGAR.

    Args:
        ticker: Stock symbol.
        days_back: How many days back to look (default 5).

    Returns:
        List of dicts with filedAt, items, description for each 8-K.
    """
    cik_map = _get_cik_mapping()
    cik = cik_map.get(ticker.upper())
    if not cik:
        logger.debug("No CIK found for ticker %s", ticker)
        return []

    try:
        url = EDGAR_SUBMISSIONS_URL.format(cik=cik)
        resp = requests.get(url, headers=_get_sec_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        accession_numbers = recent.get("accessionNumber", [])
        items_list = recent.get("items", [])

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
        results = []

        for i, form in enumerate(forms):
            if form != "8-K":
                continue

            filed_date_str = filing_dates[i] if i < len(filing_dates) else ""
            try:
                filed_date = datetime.strptime(filed_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            if filed_date < cutoff:
                continue

            # Get items for this filing
            raw_items = items_list[i] if i < len(items_list) else ""
            items = [item.strip() for item in raw_items.split(",") if item.strip()]

            # Build the description from the items
            event_info = parse_material_event(items)

            accession = accession_numbers[i] if i < len(accession_numbers) else ""
            doc = primary_docs[i] if i < len(primary_docs) else ""

            results.append({
                "filedAt": filed_date_str,
                "items": items,
                "description": event_info.get("event_type", "Unknown"),
                "urgency": event_info.get("urgency", "LOW"),
                "accessionNumber": accession,
                "primaryDocument": doc,
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik.lstrip('0')}/{accession.replace('-', '')}/{doc}"
                ) if accession and doc else None,
            })

        return results
    except Exception as e:
        logger.debug("get_recent_8k_filings(%s) failed: %s", ticker, e)
        return []


def parse_material_event(items_list: list[str]) -> dict:
    """
    Classify 8-K items into event type and urgency.

    Args:
        items_list: List of 8-K item codes (e.g. ["2.02", "9.01"]).

    Returns:
        Dict with 'event_type' (str) and 'urgency' ("HIGH" / "MEDIUM" / "LOW").
        Uses the highest-urgency item if multiple are present.
    """
    if not items_list:
        return {"event_type": "Unknown", "urgency": "LOW"}

    urgency_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    best_urgency = "LOW"
    event_types = []

    for item_code in items_list:
        item_code = item_code.strip()
        decoded = ITEM_DECODER.get(item_code)
        if decoded:
            event_types.append(decoded["event_type"])
            if urgency_rank.get(decoded["urgency"], 0) > urgency_rank.get(best_urgency, 0):
                best_urgency = decoded["urgency"]
        else:
            event_types.append(f"Item {item_code}")

    return {
        "event_type": " | ".join(event_types) if event_types else "Unknown",
        "urgency": best_urgency,
    }

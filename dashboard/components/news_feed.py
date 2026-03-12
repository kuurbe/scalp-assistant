"""
Live news feed component — continuously updated market news.
Sources: Finnhub, Yahoo RSS, geopolitical RSS, SEC EDGAR.
Clean card-based design with source badges and time-ago labels.
"""
import datetime
import streamlit as st
from dashboard.theme import COLORS


def _time_ago(published) -> str:
    """Convert a published timestamp to a human-readable 'time ago' string."""
    if not published:
        return ""
    try:
        if isinstance(published, str):
            # Handle ISO format
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
        elif isinstance(published, (int, float)):
            dt = datetime.datetime.utcfromtimestamp(published)
        elif isinstance(published, datetime.datetime):
            dt = published.replace(tzinfo=None) if published.tzinfo else published
        else:
            return ""

        now = datetime.datetime.utcnow()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 0:
            return "just now"
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m ago"
        if seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        days = int(seconds / 86400)
        return f"{days}d ago"
    except Exception:
        return ""


def _source_badge(source: str) -> str:
    """Return a colored badge for the news source."""
    source_lower = (source or "").lower()
    if "finnhub" in source_lower:
        color = COLORS["accent"]
        label = source.split("/")[-1][:20] if "/" in source else "Finnhub"
    elif "yahoo" in source_lower or "rss" in source_lower:
        color = "#7C3AED"  # purple
        label = "Yahoo"
    elif "sec" in source_lower or "edgar" in source_lower:
        color = COLORS["warning"]
        label = "SEC"
    elif "stocktwits" in source_lower:
        color = "#06B6D4"  # cyan
        label = "StockTwits"
    elif "geo" in source_lower:
        color = COLORS["danger"]
        label = "Geopolitical"
    else:
        color = COLORS["text_muted"]
        label = source[:12] if source else "News"

    return (
        f'<span style="background:{color}12;color:{color};padding:2px 8px;border-radius:5px;'
        f'font-size:10px;font-weight:600;letter-spacing:0.02em;white-space:nowrap;">{label}</span>'
    )


def news_feed(news_items: list, max_items: int = 15, title: str = "Latest News",
              show_header: bool = True):
    """Render a live news feed card.

    Args:
        news_items: List of dicts with headline, source, published, summary, url, ticker
        max_items: Max items to display
        title: Section title
        show_header: Whether to show the title header
    """
    if show_header:
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <div style="font-size:20px; font-weight:600; color:{COLORS['text']};">{title}</div>
            <div style="font-size:11px; color:{COLORS['text_dim']};">
                Auto-updates every 3 min</div>
        </div>
        """, unsafe_allow_html=True)

    if not news_items:
        st.markdown(f"""
        <div style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:20px;
                    padding:32px;text-align:center;">
            <div style="font-size:14px;color:{COLORS['text_secondary']};">
                No news available yet. News will appear here when market sources update.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    items_html = ""
    for item in news_items[:max_items]:
        headline = (item.get("headline") or item.get("title") or "")[:100]
        if not headline:
            continue
        source = item.get("source", "")
        published = item.get("published") or item.get("datetime", "")
        summary = (item.get("summary") or "")[:120]
        ticker = item.get("ticker", "")
        time_label = _time_ago(published)

        # Ticker badge
        ticker_html = ""
        if ticker and ticker != "MARKET":
            ticker_html = (
                f'<span style="background:{COLORS["accent"]}10;color:{COLORS["accent"]};'
                f'padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;'
                f'margin-right:6px;">{ticker}</span>'
            )

        # Summary (truncated)
        summary_html = ""
        if summary and summary != headline:
            clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")[:100]
            summary_html = (
                f'<div style="font-size:12px;color:{COLORS["text_dim"]};margin-top:4px;'
                f'line-height:1.4;overflow:hidden;text-overflow:ellipsis;">{clean_summary}</div>'
            )

        items_html += (
            f'<div style="padding:12px 0;border-bottom:1px solid {COLORS["border"]};">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;">'
            f'{ticker_html}{_source_badge(source)}'
            f'<span style="font-size:10px;color:{COLORS["text_dim"]};">{time_label}</span>'
            f'</div>'
            f'<div style="font-size:13px;color:{COLORS["text"]};font-weight:500;line-height:1.4;">{headline}</div>'
            f'{summary_html}'
            f'</div>'
            f'</div>'
            f'</div>'
        )

    st.markdown(f"""
    <div style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:20px;
                padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
        {items_html}
    </div>
    """, unsafe_allow_html=True)


def news_ticker_bar(news_items: list, max_items: int = 5):
    """Render a compact horizontal news ticker bar at the top of a page.

    Args:
        news_items: List of news dicts
        max_items: Max headlines to show
    """
    if not news_items:
        return

    headlines = []
    for item in news_items[:max_items]:
        hl = (item.get("headline") or item.get("title") or "")[:80]
        if hl:
            source = item.get("source", "")
            short_source = source.split("/")[-1][:10] if "/" in source else source[:10]
            time_label = _time_ago(item.get("published") or item.get("datetime", ""))
            headlines.append(
                f'<span style="margin-right:24px;white-space:nowrap;">'
                f'<span style="color:{COLORS["text_muted"]};font-size:10px;margin-right:4px;">{short_source}</span>'
                f'<span style="color:{COLORS["text_secondary"]};font-size:12px;">{hl}</span>'
                f'<span style="color:{COLORS["text_dim"]};font-size:10px;margin-left:4px;">{time_label}</span>'
                f'</span>'
            )

    if not headlines:
        return

    ticker_content = "".join(headlines)
    st.markdown(f"""
    <div style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:12px;
                padding:10px 16px;margin-bottom:16px;overflow:hidden;white-space:nowrap;">
        <div style="display:flex;align-items:center;">
            <span style="background:{COLORS['danger']};color:white;padding:2px 8px;border-radius:5px;
                         font-size:10px;font-weight:700;margin-right:12px;flex-shrink:0;">LIVE</span>
            <div style="overflow:hidden;text-overflow:ellipsis;">{ticker_content}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

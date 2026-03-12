"""
Event card component — shows catalyst alerts, signals, and market events.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS, urgency_color


def event_card(card: dict):
    """Render an event alert card."""
    urg = card.get("urgency", "LOW")
    uc = urgency_color(urg)
    etype = card.get("event_type", "EVENT")
    title = card.get("title", "")[:120]
    tickers = card.get("tickers", [])
    direction = card.get("direction", "NEUTRAL")
    timestamp = card.get("timestamp", "")
    action = card.get("action_suggestion", "")

    dir_color = COLORS["success"] if direction == "BULLISH" else (
        COLORS["danger"] if direction == "BEARISH" else COLORS["text_muted"]
    )

    ticker_str = ", ".join(tickers[:5]) if tickers else "—"

    st.markdown(f"""
    <div style="{CARD_CSS} margin-bottom:12px; padding:20px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
            <span style="width:8px; height:8px; border-radius:50%; background:{uc};
                         display:inline-block;"></span>
            <span style="font-size:11px; color:{uc}; text-transform:uppercase;
                         letter-spacing:0.08em; font-weight:600;">{etype}</span>
            <span style="font-size:11px; color:{COLORS['text_dim']}; margin-left:auto;">
                {timestamp}</span>
        </div>
        <div style="font-size:15px; color:{COLORS['text']}; font-weight:500;
                    margin-bottom:8px;">{title}</div>
        <div style="display:flex; gap:16px; font-size:13px;">
            <span style="color:{COLORS['text_muted']};">Tickers: <span style="color:{COLORS['text_secondary']};">{ticker_str}</span></span>
            <span style="color:{dir_color};">{direction}</span>
        </div>
        {"<div style='font-size:13px; color:" + COLORS['accent'] + "; margin-top:8px;'>" + action + "</div>" if action else ""}
    </div>
    """, unsafe_allow_html=True)


def alert_feed(alerts: list, max_items: int = 10):
    """Render a scrolling alert feed."""
    if not alerts:
        st.markdown(f"""
        <div style="padding:24px; text-align:center; color:{COLORS['text_dim']};">
            No alerts yet — they'll appear here when signals fire.
        </div>
        """, unsafe_allow_html=True)
        return

    for card in alerts[:max_items]:
        event_card(card)

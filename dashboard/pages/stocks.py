"""
Stocks page — full stock universe leaderboard with detail cards and forecasts.
Non-blocking: uses cached results or scan button to avoid 60-90s freeze.
Clean card-based design matching reference UI.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card, overview_card
from dashboard.components.leaderboard import render_leaderboard
from dashboard.components.ticker_card import ticker_card
from dashboard import data_bridge


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    st.markdown(f"""
    <div style="margin-bottom:28px;">
        <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                    letter-spacing:-0.02em; margin-bottom:6px;">
            Stocks
        </div>
        <div style="font-size:14px; color:{COLORS['text_muted']};">
            {"Scan 96 stocks to find the best trades today" if is_simple else "96 tickers — mega cap, biotech, energy, semis, meme, growth"}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Use session state cache — don't auto-scan (blocks UI for 60-90s)
    cache_key = "stocks_scan_results"
    stocks = st.session_state.get(cache_key, [])

    if not stocks:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; padding:48px;">
            <div style="width:48px;height:48px;border-radius:50%;background:{COLORS['accent']}10;
                        display:flex;align-items:center;justify-content:center;margin:0 auto 16px auto;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="{COLORS['accent']}" stroke-width="2">
                    <path d="M23 6l-9.5 9.5-5-5L1 18M17 6h6v6"/></svg>
            </div>
            <div style="font-size:16px; font-weight:500; color:{COLORS['text']}; margin-bottom:8px;">
                {"Ready to find opportunities" if is_simple else "Stock Scanner Ready"}</div>
            <div style="font-size:14px; color:{COLORS['text_secondary']};">
                {"Click below to scan 96 stocks and find the best opportunities" if is_simple else "Run the scanner to analyze 96 tickers across all sectors"}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Scan Stocks" if not is_simple else "Find Best Stocks", type="primary"):
            with st.spinner("Scanning 96 tickers..." if not is_simple else "Finding the best opportunities..."):
                stocks = data_bridge.scan_universe("stocks")
                st.session_state[cache_key] = stocks
                st.session_state["overview_scan_results"] = stocks
            st.rerun()
        return

    # Summary row — grouped overview card
    active = [s for s in stocks if s.composite_score >= 40]
    sparks = [s for s in stocks if s.kinematic_phase == "IGNITION"]
    longs = [s for s in stocks if s.direction == "LONG"]
    top_score = stocks[0].composite_score if stocks else 0

    overview_card("Stock Scanner Results", [
        {
            "label": "Active Setups",
            "value": str(len(active)),
            "icon": "chart",
            "delta": f"of {len(stocks)} scanned",
            "delta_color": COLORS["success"],
        },
        {
            "label": "Sparks",
            "value": str(len(sparks)),
            "icon": "zap",
            "delta": "IGNITION detected" if sparks else "none",
            "delta_color": COLORS["warning"] if sparks else COLORS["text_dim"],
        },
        {
            "label": "Long Bias",
            "value": f"{len(longs)}/{len(active)}",
            "icon": "trending",
            "delta_color": COLORS["success"],
        },
        {
            "label": "Top Score",
            "value": f"{top_score:.0f}",
            "icon": "target",
            "delta": "strong" if top_score >= 60 else ("moderate" if top_score >= 40 else "weak"),
            "delta_color": COLORS["success"] if top_score >= 60 else COLORS["warning"],
        },
    ])

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Refresh button
    col_btn, col_space = st.columns([1, 4])
    with col_btn:
        if st.button("Refresh Scan", type="secondary"):
            with st.spinner("Scanning..."):
                stocks = data_bridge.scan_universe("stocks")
                st.session_state[cache_key] = stocks
                st.session_state["overview_scan_results"] = stocks
            st.rerun()

    # View toggle
    view = st.radio("View", ["Leaderboard", "Forecasts", "Cards"], horizontal=True, label_visibility="collapsed")

    if view == "Leaderboard":
        render_leaderboard(active, max_rows=30, simple=is_simple)
    elif view == "Forecasts":
        try:
            from dashboard.components.forecast_card import forecast_section
            forecast_section(active, max_cards=9)
        except Exception as e:
            st.error(f"Forecast error: {e}")
    else:
        for i in range(0, min(len(active), 12), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(active):
                    with col:
                        ticker_card(active[idx], rank=idx + 1)

"""
ETFs page — sector rotation, thematic, fixed income, leveraged.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card
from dashboard.components.leaderboard import render_leaderboard
from dashboard.components.ticker_card import ticker_card
from dashboard import data_bridge


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"
    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        ETFs
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        Sector, thematic, fixed income, international, leveraged
    </div>
    """, unsafe_allow_html=True)

    # Non-blocking — use session state cache
    cache_key = "etfs_scan_results"
    etfs = st.session_state.get(cache_key, [])

    if not etfs:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; padding:40px;">
            <div style="font-size:16px; font-weight:500; color:{COLORS['text']}; margin-bottom:8px;">
                {"Ready to scan ETF markets" if is_simple else "ETF Scanner Ready"}</div>
            <div style="font-size:14px; color:{COLORS['text_secondary']};">
                {"Click below to scan ETFs across all sectors" if is_simple else "Analyze sector, thematic, fixed income, and leveraged ETFs"}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Scan ETFs" if not is_simple else "Find Best ETFs", type="primary"):
            with st.spinner("Scanning ETF universe..."):
                etfs = data_bridge.scan_universe("etfs")
                st.session_state[cache_key] = etfs
            st.rerun()
        return

    # Refresh button
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("Refresh Scan", type="secondary", key="etfs_refresh"):
            data_bridge.scan_universe.clear()
            with st.spinner("Scanning ETFs..."):
                etfs = data_bridge.scan_universe("etfs")
                st.session_state[cache_key] = etfs
            st.rerun()

    active = [e for e in etfs if e.composite_score >= 40]

    # Summary
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Active ETFs", str(len(active)))
    with c2:
        top = etfs[0] if etfs else None
        metric_card("Top Pick", f"{top.ticker}" if top else "—",
                     delta=f"Score: {top.composite_score:.0f}" if top else None,
                     delta_color=COLORS["accent"])
    with c3:
        avg_score = sum(e.composite_score for e in active) / len(active) if active else 0
        metric_card("Avg Score", f"{avg_score:.0f}")

    st.markdown("<br>", unsafe_allow_html=True)

    # Sector tabs
    tabs = st.tabs(["All ETFs", "Sector", "Thematic", "Fixed Income", "Leveraged"])

    sector_tickers = {"XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "XLP", "XLB", "XLRE"}
    thematic_tickers = {"ARKK", "ARKG", "ARKF", "ARKW", "BOTZ", "LIT", "TAN", "ICLN"}
    fixed_income_tickers = {"TLT", "IEF", "SHY", "HYG", "LQD", "AGG"}
    leveraged_tickers = {"TQQQ", "SQQQ", "SOXL", "SOXS", "UVXY", "VXX"}

    with tabs[0]:
        render_leaderboard(active, max_rows=40, simple=is_simple)

    with tabs[1]:
        sector = [e for e in active if e.ticker in sector_tickers]
        if sector:
            render_leaderboard(sector, simple=is_simple)
        else:
            st.info("No active sector ETF signals.")

    with tabs[2]:
        thematic = [e for e in active if e.ticker in thematic_tickers]
        if thematic:
            render_leaderboard(thematic, simple=is_simple)
        else:
            st.info("No active thematic ETF signals.")

    with tabs[3]:
        fi = [e for e in active if e.ticker in fixed_income_tickers]
        if fi:
            render_leaderboard(fi, simple=is_simple)
        else:
            st.info("No active fixed income signals.")

    with tabs[4]:
        lev = [e for e in active if e.ticker in leveraged_tickers]
        if lev:
            render_leaderboard(lev, simple=is_simple)
        else:
            st.info("No active leveraged ETF signals.")

"""
ETFs page — sector rotation, thematic, fixed income, leveraged.
"""
import streamlit as st
from dashboard.theme import COLORS
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

    with st.spinner("Scanning ETF universe..."):
        etfs = data_bridge.scan_universe("etfs")

    if not etfs:
        st.info("No ETF scan data yet. The scanner will populate shortly.")
        return

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

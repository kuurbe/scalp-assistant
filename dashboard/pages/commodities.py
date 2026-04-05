"""
Commodities page — precious metals, oil, agriculture, uranium.
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
        Commodities
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        15 commodity ETFs — metals, energy, agriculture
    </div>
    """, unsafe_allow_html=True)

    # Non-blocking — use session state cache
    cache_key = "commodities_scan_results"
    commodities = st.session_state.get(cache_key, [])

    if not commodities:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; padding:40px;">
            <div style="font-size:16px; font-weight:500; color:{COLORS['text']}; margin-bottom:8px;">
                {"Ready to scan commodities" if is_simple else "Commodity Scanner Ready"}</div>
            <div style="font-size:14px; color:{COLORS['text_secondary']};">
                {"Click below to scan metals, energy, and agriculture" if is_simple else "Analyze 15 commodity ETFs across all sectors"}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Scan Commodities" if not is_simple else "Find Best Commodities", type="primary"):
            with st.spinner("Scanning commodity universe..."):
                commodities = data_bridge.scan_universe("commodities")
                st.session_state[cache_key] = commodities
            st.rerun()
        return

    # Refresh button
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("Refresh Scan", type="secondary", key="commodities_refresh"):
            data_bridge.scan_universe.clear()
            with st.spinner("Scanning commodities..."):
                commodities = data_bridge.scan_universe("commodities")
                st.session_state[cache_key] = commodities
            st.rerun()

    active = [c for c in commodities if c.composite_score >= 40]

    # Key commodities
    gld = next((c for c in commodities if c.ticker == "GLD"), None)
    uso = next((c for c in commodities if c.ticker == "USO"), None)
    ura = next((c for c in commodities if c.ticker == "URA"), None)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if gld:
            arrow = "+" if gld.pct_change >= 0 else ""
            metric_card("Gold (GLD)", f"${gld.price:.2f}",
                         delta=f"{arrow}{gld.pct_change:.1f}%",
                         delta_color=COLORS["success"] if gld.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("Gold", "—")
    with c2:
        if uso:
            arrow = "+" if uso.pct_change >= 0 else ""
            metric_card("Oil (USO)", f"${uso.price:.2f}",
                         delta=f"{arrow}{uso.pct_change:.1f}%",
                         delta_color=COLORS["success"] if uso.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("Oil", "—")
    with c3:
        if ura:
            arrow = "+" if ura.pct_change >= 0 else ""
            metric_card("Uranium (URA)", f"${ura.price:.2f}",
                         delta=f"{arrow}{ura.pct_change:.1f}%",
                         delta_color=COLORS["success"] if ura.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("Uranium", "—")
    with c4:
        metric_card("Active Signals", str(len(active)))

    st.markdown("<br>", unsafe_allow_html=True)

    # Category tabs
    tabs = st.tabs(["All", "Precious Metals", "Energy", "Agriculture"])

    metals = {"GLD", "SLV", "GDX"}
    energy = {"USO", "UCO", "XOP", "UNG"}
    agriculture = {"WEAT", "CORN", "SOYB", "DBA"}

    with tabs[0]:
        if active:
            render_leaderboard(active, max_rows=15, simple=is_simple)
        else:
            st.info("No active commodity signals.")

    with tabs[1]:
        m = [c for c in active if c.ticker in metals]
        if m:
            render_leaderboard(m, simple=is_simple)
        else:
            st.info("No active precious metals signals.")

    with tabs[2]:
        e = [c for c in active if c.ticker in energy]
        if e:
            render_leaderboard(e, simple=is_simple)
        else:
            st.info("No active energy signals.")

    with tabs[3]:
        a = [c for c in active if c.ticker in agriculture]
        if a:
            render_leaderboard(a, simple=is_simple)
        else:
            st.info("No active agriculture signals.")

"""
Forex page — major pairs + USD index.
Non-blocking scan with button trigger.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card
from dashboard.components.leaderboard import render_leaderboard
from dashboard.components.ticker_card import ticker_card
from dashboard import data_bridge


# Human-readable names for forex tickers
_PAIR_NAMES = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD",
    "EURGBP=X": "EUR/GBP",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY",
    "DX-Y.NYB": "US Dollar Index",
}


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"
    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        Forex
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        {"Major currency pairs — see which currencies are moving" if is_simple else "11 major pairs — 24/5 markets, 260 trading days"}
    </div>
    """, unsafe_allow_html=True)

    # Non-blocking: use cached results or scan on button
    cache_key = "forex_scan_results"
    forex = st.session_state.get(cache_key, [])

    if not forex:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; padding:48px;">
            <div style="font-size:17px; color:{COLORS['text_secondary']}; margin-bottom:16px;">
                {"Click below to scan 11 currency pairs" if is_simple else "Run the forex scanner to analyze all major pairs"}
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Scan Forex" if not is_simple else "Check Currencies", type="primary"):
            with st.spinner("Scanning forex pairs..."):
                forex = data_bridge.scan_universe("forex")
                st.session_state[cache_key] = forex
            st.rerun()
        return

    # Key pairs — show top-4 metric cards
    eur = next((f for f in forex if f.ticker == "EURUSD=X"), None)
    gbp = next((f for f in forex if f.ticker == "GBPUSD=X"), None)
    jpy = next((f for f in forex if f.ticker == "USDJPY=X"), None)
    dxy = next((f for f in forex if f.ticker == "DX-Y.NYB"), None)

    c1, c2, c3, c4 = st.columns(4)
    for col, pair, label, fmt in [
        (c1, eur, "EUR/USD", ".4f"),
        (c2, gbp, "GBP/USD", ".4f"),
        (c3, jpy, "USD/JPY", ".2f"),
        (c4, dxy, "DXY Index", ".2f"),
    ]:
        with col:
            if pair:
                metric_card(label, f"{pair.price:{fmt}}",
                            delta=f"{'+' if pair.pct_change >= 0 else ''}{pair.pct_change:.2f}%",
                            delta_color=COLORS["success"] if pair.pct_change >= 0 else COLORS["danger"])
            else:
                metric_card(label, "—")

    st.markdown("<br>", unsafe_allow_html=True)

    # Refresh button
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("Refresh Scan", type="secondary"):
            with st.spinner("Scanning..."):
                forex = data_bridge.scan_universe("forex")
                st.session_state[cache_key] = forex
            st.rerun()

    # Show all pairs sorted by score
    active = [f for f in forex if f.composite_score >= 30]  # Lower threshold for forex

    if is_simple:
        # Simple view — clean card list
        st.markdown(f"""
        <div style="font-size:22px; font-weight:600; color:{COLORS['text']}; margin-bottom:16px;">
            All Currency Pairs
        </div>
        """, unsafe_allow_html=True)

        if active:
            from signals.recommendation import get_recommendation
            rows_html = ""
            for i, pick in enumerate(active, 1):
                rec = get_recommendation(pick)
                sig = rec["signal"]
                pair_name = _PAIR_NAMES.get(pick.ticker, pick.ticker)
                chg_color = COLORS["success"] if pick.pct_change >= 0 else COLORS["danger"]
                sig_color = COLORS["success"] if sig == "BUY" else (COLORS["danger"] if sig == "SELL" else COLORS["text_muted"])
                arrow = "+" if pick.pct_change >= 0 else ""

                rows_html += (
                    f'<div style="display:flex;align-items:center;padding:14px 0;'
                    f'border-bottom:1px solid {COLORS["border"]};">'
                    f'<div style="min-width:30px;color:{COLORS["text_dim"]};font-size:13px;">{i}</div>'
                    f'<div style="min-width:120px;color:{COLORS["text"]};font-weight:500;font-size:14px;">{pair_name}</div>'
                    f'<div style="min-width:90px;color:{COLORS["text"]};font-size:14px;">{pick.price:.4f}</div>'
                    f'<div style="min-width:80px;color:{chg_color};font-size:13px;">{arrow}{pick.pct_change:.2f}%</div>'
                    f'<div style="min-width:60px;">'
                    f'<span style="background:{sig_color};color:#000;padding:2px 10px;border-radius:980px;'
                    f'font-size:11px;font-weight:700;">{sig}</span></div>'
                    f'<div style="flex:1;color:{COLORS["text_secondary"]};font-size:12px;">{rec.get("action", "")[:40]}</div>'
                    f'</div>'
                )

            st.markdown(f"""
            <div style="background:{COLORS['card']};backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
                        border:1px solid {COLORS['border']};border-radius:20px;padding:20px;">
                <div style="display:flex;align-items:center;padding:8px 0 12px 0;border-bottom:1px solid {COLORS['border']};">
                    <div style="min-width:30px;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">#</div>
                    <div style="min-width:120px;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">Pair</div>
                    <div style="min-width:90px;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">Rate</div>
                    <div style="min-width:80px;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">Today</div>
                    <div style="min-width:60px;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">Signal</div>
                    <div style="flex:1;font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">What to Do</div>
                </div>
                {rows_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No active forex signals at the moment.")
    else:
        # Advanced view — full leaderboard + cards
        if active:
            render_leaderboard(active, max_rows=11, simple=False)
        else:
            st.info("No active forex signals above threshold.")

        if active:
            st.markdown(f"""
            <div style="font-size:22px; font-weight:600; color:{COLORS['text']};
                        margin-top:40px; margin-bottom:16px;">
                Top Forex Setups
            </div>
            """, unsafe_allow_html=True)

            for i, pick in enumerate(active[:4]):
                ticker_card(pick, rank=i + 1, show_details=True)

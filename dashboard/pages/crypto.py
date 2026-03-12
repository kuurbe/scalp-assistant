"""
Crypto page — 24/7 crypto universe scanning + CoinGecko global data.
Supports Simple and Advanced view modes.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card
from dashboard.components.leaderboard import render_leaderboard
from dashboard.components.ticker_card import ticker_card
from dashboard import data_bridge


def _fg_color(score: float) -> str:
    if score <= 25:
        return COLORS["danger"]
    if score <= 45:
        return "#FF6B35"
    if score <= 55:
        return COLORS["warning"]
    if score <= 75:
        return COLORS["success"]
    return "#00C853"


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        Crypto
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        {"Live crypto prices, sentiment, and trending coins" if is_simple else "20 tokens — 24/7 markets, 365 trading days, 1440 min/day"}
    </div>
    """, unsafe_allow_html=True)

    # CoinGecko global data
    global_crypto = data_bridge.get_crypto_global()
    crypto_fg = data_bridge.get_crypto_fear_greed()
    trending = data_bridge.get_trending_coins()

    # ── Global Stats Row ─────────────────────────────────────
    if global_crypto:
        mc = global_crypto.get("total_market_cap_usd", 0)
        btc_dom = global_crypto.get("btc_dominance", 0)
        eth_dom = global_crypto.get("eth_dominance", 0)
        vol_24h = global_crypto.get("total_volume_24h", 0)
        mc_change = global_crypto.get("market_cap_change_24h", 0)

        if is_simple:
            # Simple: big readable numbers with explanations
            c1, c2, c3 = st.columns(3)
            with c1:
                mc_str = f"${mc / 1e12:.2f}T" if mc > 1e12 else f"${mc / 1e9:.0f}B"
                change_color = COLORS["success"] if mc_change >= 0 else COLORS["danger"]
                st.markdown(f"""
                <div style="{CARD_CSS} text-align:center;">
                    <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                                letter-spacing:0.06em;margin-bottom:8px;">TOTAL CRYPTO VALUE</div>
                    <div style="font-size:36px;font-weight:300;color:{COLORS['text']};">{mc_str}</div>
                    <div style="font-size:13px;color:{change_color};margin-top:4px;">
                        {"+" if mc_change >= 0 else ""}{mc_change:.1f}% today</div>
                    <div style="font-size:12px;color:{COLORS['text_dim']};margin-top:4px;">
                        All cryptocurrencies combined</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div style="{CARD_CSS} text-align:center;">
                    <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                                letter-spacing:0.06em;margin-bottom:8px;">BITCOIN DOMINANCE</div>
                    <div style="font-size:36px;font-weight:300;color:{COLORS['warning']};">{btc_dom:.1f}%</div>
                    <div style="font-size:12px;color:{COLORS['text_dim']};margin-top:8px;">
                        Bitcoin's share of total crypto market</div>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                cfg_score = crypto_fg.get("score", 0)
                cfg_label = crypto_fg.get("rating", "N/A")
                st.markdown(f"""
                <div style="{CARD_CSS} text-align:center;">
                    <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                                letter-spacing:0.06em;margin-bottom:8px;">CRYPTO MOOD</div>
                    <div style="font-size:36px;font-weight:300;color:{_fg_color(cfg_score)};">{cfg_score}</div>
                    <div style="font-size:14px;color:{COLORS['text_secondary']};margin-top:4px;">{cfg_label}</div>
                    <div style="font-size:12px;color:{COLORS['text_dim']};margin-top:4px;">
                        0 = Extreme Fear, 100 = Extreme Greed</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            # Advanced: compact metric cards
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                mc_str = f"${mc / 1e12:.2f}T" if mc > 1e12 else f"${mc / 1e9:.0f}B"
                metric_card("Market Cap", mc_str,
                            f"{'+'if mc_change >= 0 else ''}{mc_change:.1f}%",
                            COLORS["success"] if mc_change >= 0 else COLORS["danger"])
            with c2:
                metric_card("BTC Dominance", f"{btc_dom:.1f}%")
            with c3:
                metric_card("ETH Dominance", f"{eth_dom:.1f}%")
            with c4:
                vol_str = f"${vol_24h / 1e9:.0f}B" if vol_24h > 1e9 else f"${vol_24h / 1e6:.0f}M"
                metric_card("24h Volume", vol_str)
            with c5:
                cfg_score = crypto_fg.get("score", 0)
                cfg_label = crypto_fg.get("rating", "—")
                metric_card("Crypto F&G", str(cfg_score), cfg_label,
                            _fg_color(cfg_score) if cfg_score else COLORS["text_dim"])

        st.markdown("<br>", unsafe_allow_html=True)

    # ── Trending Coins ───────────────────────────────────────
    if trending:
        st.markdown(f"""
        <div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">
            {"Trending Right Now" if is_simple else "Trending on CoinGecko"}
        </div>
        """, unsafe_allow_html=True)

        trend_html = ""
        for coin in trending[:7]:
            name = coin.get("name", "")
            symbol = coin.get("symbol", "")
            rank = coin.get("market_cap_rank", 0)
            rank_str = f"#{rank}" if rank else ""
            trend_html += (
                f'<div style="display:inline-block;margin:4px 8px 4px 0;padding:8px 16px;'
                f'border-radius:12px;background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
                f'font-size:13px;">'
                f'<span style="color:{COLORS["text"]};font-weight:500;">{symbol}</span>'
                f'<span style="color:{COLORS["text_dim"]};margin-left:6px;">{name}</span>'
                f'<span style="color:{COLORS["text_muted"]};margin-left:6px;font-size:11px;">{rank_str}</span>'
                f'</div>'
            )

        st.markdown(f'<div style="margin-bottom:24px;">{trend_html}</div>', unsafe_allow_html=True)

    # ── Scan Results ─────────────────────────────────────────
    with st.spinner("Scanning crypto universe..."):
        crypto = data_bridge.scan_universe("crypto")

    if not crypto:
        st.info("No crypto scan data yet. The scanner will populate shortly.")
        return

    active = [c for c in crypto if c.composite_score >= 40]

    # BTC/ETH/SOL quick stats
    btc = next((c for c in crypto if c.ticker == "BTC-USD"), None)
    eth = next((c for c in crypto if c.ticker == "ETH-USD"), None)
    sol = next((c for c in crypto if c.ticker == "SOL-USD"), None)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if btc:
            arrow = "+" if btc.pct_change >= 0 else ""
            metric_card("BTC", f"${btc.price:,.0f}",
                         delta=f"{arrow}{btc.pct_change:.1f}%",
                         delta_color=COLORS["success"] if btc.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("BTC", "—")
    with c2:
        if eth:
            arrow = "+" if eth.pct_change >= 0 else ""
            metric_card("ETH", f"${eth.price:,.0f}",
                         delta=f"{arrow}{eth.pct_change:.1f}%",
                         delta_color=COLORS["success"] if eth.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("ETH", "—")
    with c3:
        if sol:
            arrow = "+" if sol.pct_change >= 0 else ""
            metric_card("SOL", f"${sol.price:.2f}",
                         delta=f"{arrow}{sol.pct_change:.1f}%",
                         delta_color=COLORS["success"] if sol.pct_change >= 0 else COLORS["danger"])
        else:
            metric_card("SOL", "—")
    with c4:
        metric_card("Active Signals", str(len(active)))

    st.markdown("<br>", unsafe_allow_html=True)

    # View toggle
    view = st.radio("View", ["Leaderboard", "Cards"], horizontal=True,
                    label_visibility="collapsed", key="crypto_view")

    if view == "Leaderboard":
        render_leaderboard(active, max_rows=20, simple=is_simple)
    else:
        for i in range(0, min(len(active), 10), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(active):
                    with col:
                        ticker_card(active[idx], rank=idx + 1)

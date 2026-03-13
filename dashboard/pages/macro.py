"""
Macro page — FRED data, yield curve, VIX, rates, inflation, employment.

Simple mode: 4 key metrics + plain English narrative.
Advanced mode: full economic indicators, commodity prices, bar chart.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card, mini_metric
from dashboard.components.charts import bar_chart
from dashboard import data_bridge


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    subtitle = "The big picture — what's happening in the economy" if is_simple else "FRED economic data — rates, yields, inflation, employment"

    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        {"Economy Overview" if is_simple else "Macro Dashboard"}
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        {subtitle}
    </div>
    """, unsafe_allow_html=True)

    macro = data_bridge.get_macro_context()
    expanded = data_bridge.get_expanded_macro()

    vix = macro.get("vix", 0)
    regime = macro.get("macro_regime", "NEUTRAL")

    if is_simple:
        _render_simple(vix, regime, expanded)
    else:
        _render_advanced(vix, regime, expanded)


def _render_simple(vix, regime, expanded):
    # ─── 4 key metric cards ───
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        vix_label = "High" if vix and vix > 25 else ("Elevated" if vix and vix > 20 else "Normal")
        vix_color = COLORS["danger"] if vix and vix > 25 else (COLORS["warning"] if vix and vix > 20 else COLORS["success"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">MARKET FEAR</div>
            <div style="font-size:30px; font-weight:700; color:{vix_color}; margin-top:8px;">{vix_label}</div>
            <div style="font-size:13px; color:{COLORS['text_dim']}; margin-top:4px;">VIX: {vix:.1f}</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        regime_color = COLORS["success"] if regime == "EXPANSION" else (COLORS["danger"] if regime == "CONTRACTION" else COLORS["warning"])
        regime_label = {"EXPANSION": "Growing", "CONTRACTION": "Slowing", "NEUTRAL": "Steady"}.get(regime, regime)
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">ECONOMY</div>
            <div style="font-size:30px; font-weight:700; color:{regime_color}; margin-top:8px;">{regime_label}</div>
            <div style="font-size:13px; color:{COLORS['text_dim']}; margin-top:4px;">Macro regime</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        fed_rate = expanded.get("fed_rate", "—")
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">INTEREST RATES</div>
            <div style="font-size:30px; font-weight:700; color:{COLORS['text']}; margin-top:8px;">{fed_rate}%</div>
            <div style="font-size:13px; color:{COLORS['text_dim']}; margin-top:4px;">Fed Funds Rate</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        yc = expanded.get("yield_curve_spread", "—")
        if isinstance(yc, (int, float)):
            yc_color = COLORS["danger"] if yc < 0 else COLORS["success"]
            yc_label = "Inverted" if yc < 0 else "Normal"
            yc_display = f"{yc:.2f}"
        else:
            yc_color = COLORS["text_dim"]
            yc_label = ""
            yc_display = "—"
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">YIELD CURVE</div>
            <div style="font-size:30px; font-weight:700; color:{yc_color}; margin-top:8px;">{yc_label if yc_label else yc_display}</div>
            <div style="font-size:13px; color:{COLORS['text_dim']}; margin-top:4px;">10Y-2Y: {yc_display}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── What it means narrative ───
    points = []
    if vix and isinstance(vix, (int, float)):
        if vix > 25:
            points.append("Markets are fearful right now (VIX is high). Expect bigger price swings and be cautious with new positions.")
        elif vix > 20:
            points.append("There's some nervousness in the market (VIX is elevated). Keep an eye on things but don't panic.")
        else:
            points.append("Markets are calm right now (VIX is low). This is usually a good environment for steady gains.")

    if isinstance(yc, (int, float)):
        if yc < 0:
            points.append("The yield curve is inverted — historically this has been a warning sign for the economy. Stay defensive.")
        else:
            points.append("The yield curve is normal, which suggests the economy is on stable footing.")

    if regime == "CONTRACTION":
        points.append("The economy appears to be slowing. Defensive stocks and bonds may outperform.")
    elif regime == "EXPANSION":
        points.append("The economy is growing. Growth and cyclical stocks tend to do well in this environment.")

    if points:
        narrative = " ".join(points)
        border_color = COLORS["success"] if vix and vix < 20 and regime == "EXPANSION" else (COLORS["danger"] if vix and vix > 25 else COLORS["warning"])
        st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {border_color}; padding:20px;">
            <div style="font-size:16px; font-weight:600; color:{COLORS['text']}; margin-bottom:8px;">What does this mean for your trades?</div>
            <div style="font-size:14px; color:{COLORS['text_secondary']}; line-height:1.7;">{narrative}</div>
        </div>""", unsafe_allow_html=True)


def _render_advanced(vix, regime, expanded):
    # ─── Key Metrics Row ───
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        vix_label = "HIGH" if vix and vix > 25 else ("ELEVATED" if vix and vix > 20 else "NORMAL")
        metric_card("VIX", f"{vix:.1f}" if vix else "—", vix_label,
                     COLORS["danger"] if vix and vix > 25 else COLORS["success"])
    with c2:
        metric_card("Macro Regime", regime)
    with c3:
        fed_rate = expanded.get("fed_rate", "—")
        metric_card("Fed Funds Rate", f"{fed_rate}%" if fed_rate != "—" else "—")
    with c4:
        yc = expanded.get("yield_curve_spread", "—")
        yc_color = COLORS["danger"] if isinstance(yc, (int, float)) and yc < 0 else COLORS["success"]
        metric_card("Yield Curve (10Y-2Y)",
                     f"{yc:.2f}" if isinstance(yc, (int, float)) else "—",
                     "INVERTED" if isinstance(yc, (int, float)) and yc < 0 else "NORMAL",
                     yc_color)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Detailed Metrics Grid ───
    st.markdown(f"""
    <div style="font-size:22px; font-weight:600; color:{COLORS['text']}; margin-bottom:16px;">
        Economic Indicators
    </div>
    """, unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"""
        <div style="{CARD_CSS}">
            <div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase;
                        letter-spacing:0.06em; margin-bottom:16px;">RATES & YIELDS</div>
        """, unsafe_allow_html=True)

        items = [
            ("Fed Funds Rate", expanded.get("fed_rate"), "%"),
            ("10Y-2Y Spread", expanded.get("yield_curve_spread"), ""),
            ("High Yield Spread", expanded.get("high_yield_spread"), ""),
            ("Breakeven Inflation 10Y", expanded.get("breakeven_inflation_10y"), "%"),
        ]
        for label, val, suffix in items:
            val_str = f"{val:.2f}{suffix}" if isinstance(val, (int, float)) else "—"
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; padding:8px 0;
                        border-bottom:1px solid {COLORS['border_light']};">
                <span style="font-size:14px; color:{COLORS['text_secondary']};">{label}</span>
                <span style="font-size:14px; color:{COLORS['text']}; font-weight:500;">{val_str}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(f"""
        <div style="{CARD_CSS}">
            <div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase;
                        letter-spacing:0.06em; margin-bottom:16px;">ECONOMY & COMMODITIES</div>
        """, unsafe_allow_html=True)

        items2 = [
            ("Unemployment Rate", expanded.get("unemployment"), "%"),
            ("CPI", expanded.get("cpi"), ""),
            ("Consumer Sentiment", expanded.get("consumer_sentiment"), ""),
            ("USD Index", expanded.get("usd_index"), ""),
        ]
        for label, val, suffix in items2:
            val_str = f"{val:.2f}{suffix}" if isinstance(val, (int, float)) else "—"
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; padding:8px 0;
                        border-bottom:1px solid {COLORS['border_light']};">
                <span style="font-size:14px; color:{COLORS['text_secondary']};">{label}</span>
                <span style="font-size:14px; color:{COLORS['text']}; font-weight:500;">{val_str}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Commodity Prices ───
    st.markdown(f"""
    <div style="font-size:22px; font-weight:600; color:{COLORS['text']}; margin-bottom:16px;">
        Commodity Prices
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        wti = expanded.get("wti_crude", "—")
        mini_metric("WTI Crude", f"${wti:.2f}" if isinstance(wti, (int, float)) else "—")
    with c2:
        gold = expanded.get("gold_price", "—")
        mini_metric("Gold", f"${gold:.2f}" if isinstance(gold, (int, float)) else "—")
    with c3:
        eur_usd = expanded.get("eur_usd", "—")
        mini_metric("EUR/USD", f"{eur_usd:.4f}" if isinstance(eur_usd, (int, float)) else "—")
    with c4:
        usd = expanded.get("usd_index", "—")
        mini_metric("USD Index", f"{usd:.2f}" if isinstance(usd, (int, float)) else "—")

    # Bar chart of available indicators
    labels = []
    values = []
    colors = []
    for key, val in expanded.items():
        if isinstance(val, (int, float)) and val != 0:
            labels.append(key.replace("_", " ").title())
            values.append(val)
            colors.append(COLORS["accent"])

    if labels:
        st.markdown("<br>", unsafe_allow_html=True)
        fig = bar_chart(labels[:8], values[:8], "Key Indicators", height=300, colors=colors[:8])
        st.plotly_chart(fig, use_container_width=True)

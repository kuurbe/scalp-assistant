"""
Predictions page — prediction log, accuracy metrics, calibration, achievements.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card
from dashboard.components.score_gauge import render_score_gauge
from dashboard.components.charts import donut_chart, bar_chart
from dashboard import data_bridge


def render():
    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        Predictions
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        Prediction accuracy, calibration, and achievement tracking
    </div>
    """, unsafe_allow_html=True)

    # Fetch accuracy data
    accuracy = data_bridge.get_prediction_accuracy()
    achievements = data_bridge.get_achievements()

    # ─── Accuracy Overview ───
    win_rate = accuracy.get("overall_win_rate", 0)
    total = accuracy.get("total_evaluated", 0)
    streak = accuracy.get("current_streak", 0)
    max_streak = accuracy.get("max_streak", 0)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        wr_color = COLORS["success"] if win_rate >= 55 else (COLORS["warning"] if win_rate >= 45 else COLORS["danger"])
        metric_card("Win Rate", f"{win_rate:.1f}%", delta_color=wr_color)
    with c2:
        metric_card("Total Evaluated", str(total))
    with c3:
        metric_card("Current Streak", str(streak),
                     delta="wins" if streak > 0 else "",
                     delta_color=COLORS["success"] if streak > 0 else COLORS["text_dim"])
    with c4:
        metric_card("Best Streak", str(max_streak))

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Win Rate Gauge ───
    col_gauge, col_breakdown = st.columns([1, 2])

    with col_gauge:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center;">
            <div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase;
                        letter-spacing:0.06em; margin-bottom:16px;">OVERALL ACCURACY</div>
        """, unsafe_allow_html=True)
        render_score_gauge(win_rate, label="Win Rate", size=180)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_breakdown:
        # Accuracy by score range
        by_score = accuracy.get("by_score_range", {})
        if by_score:
            st.markdown(f"""
            <div style="{CARD_CSS}">
                <div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase;
                            letter-spacing:0.06em; margin-bottom:16px;">ACCURACY BY SCORE RANGE</div>
            """, unsafe_allow_html=True)

            for range_label, data in sorted(by_score.items()):
                if isinstance(data, dict):
                    wr = data.get("win_rate", 0)
                    count = data.get("total", 0)
                    bar_width = min(wr, 100)
                    bar_color = COLORS["success"] if wr >= 55 else (COLORS["warning"] if wr >= 45 else COLORS["danger"])

                    st.markdown(f"""
                    <div style="margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                            <span style="font-size:13px; color:{COLORS['text_secondary']};">{range_label}</span>
                            <span style="font-size:13px; color:{COLORS['text']};">{wr:.0f}% ({count})</span>
                        </div>
                        <div style="height:6px; background:{COLORS['bg_elevated']}; border-radius:3px; overflow:hidden;">
                            <div style="height:100%; width:{bar_width}%; background:{bar_color};
                                        border-radius:3px; transition:width 0.5s ease;"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">
                No prediction data yet. Predictions will auto-evaluate over time.
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Accuracy by Regime and Asset Class ───
    col_regime, col_asset = st.columns(2)

    with col_regime:
        by_regime = accuracy.get("by_regime", {})
        if by_regime:
            labels = list(by_regime.keys())
            values = [by_regime[k].get("win_rate", 0) if isinstance(by_regime[k], dict) else 0
                      for k in labels]
            colors = [COLORS["success"] if v >= 55 else (COLORS["warning"] if v >= 45 else COLORS["danger"])
                      for v in values]
            fig = bar_chart(labels, values, "Win Rate by Regime", height=280, colors=colors)
            st.plotly_chart(fig, use_container_width=True)

    with col_asset:
        by_asset = accuracy.get("by_asset_class", {})
        if by_asset:
            labels = list(by_asset.keys())
            values = [by_asset[k].get("win_rate", 0) if isinstance(by_asset[k], dict) else 0
                      for k in labels]
            colors = [COLORS["accent"], COLORS["success"], COLORS["warning"],
                      COLORS["danger"], COLORS["info"]]
            fig = bar_chart(labels, values, "Win Rate by Asset Class", height=280,
                           colors=colors[:len(labels)])
            st.plotly_chart(fig, use_container_width=True)

    # ─── Achievements ───
    st.markdown(f"""
    <div style="font-size:22px; font-weight:600; color:{COLORS['text']};
                margin-top:40px; margin-bottom:16px;">
        Achievements
    </div>
    """, unsafe_allow_html=True)

    if achievements:
        earned = [a for a in achievements if a.get("earned", False)]
        locked = [a for a in achievements if not a.get("earned", False)]

        if earned:
            st.markdown(f"""
            <div style="font-size:13px; color:{COLORS['text_muted']}; margin-bottom:12px;">
                {len(earned)} of {len(achievements)} unlocked
            </div>
            """, unsafe_allow_html=True)

            # Achievement grid
            cols = st.columns(min(len(earned), 4))
            for i, ach in enumerate(earned):
                tier = ach.get("tier", "BRONZE")
                tier_colors = {
                    "BRONZE": "#CD7F32",
                    "SILVER": "#C0C0C0",
                    "GOLD": "#FFD700",
                    "PLATINUM": "#E5E4E2",
                }
                tc = tier_colors.get(tier, COLORS["accent"])
                with cols[i % len(cols)]:
                    st.markdown(f"""
                    <div style="{CARD_CSS} text-align:center; padding:20px; border:1px solid {tc}30;">
                        <div style="font-size:28px; margin-bottom:8px;">
                            {"🥉" if tier == "BRONZE" else "🥈" if tier == "SILVER" else "🥇" if tier == "GOLD" else "💎"}
                        </div>
                        <div style="font-size:14px; color:{COLORS['text']}; font-weight:500;">
                            {ach.get("name", "Achievement")}</div>
                        <div style="font-size:12px; color:{COLORS['text_muted']}; margin-top:4px;">
                            {ach.get("description", "")[:60]}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # Locked achievements
        if locked:
            with st.expander(f"Locked Achievements ({len(locked)})"):
                for ach in locked:
                    st.markdown(f"""
                    <div style="padding:8px 0; border-bottom:1px solid {COLORS['border_light']};
                                color:{COLORS['text_dim']};">
                        🔒 {ach.get("name", "?")} — {ach.get("description", "")[:80]}
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">
            Achievements will unlock as you accumulate predictions.
        </div>
        """, unsafe_allow_html=True)

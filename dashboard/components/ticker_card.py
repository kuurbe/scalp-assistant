"""
Scored ticker card component — Apple-style glass card with score, price, regime.
Details section uses pure HTML to avoid Streamlit markdown/LaTeX rendering issues.
"""
import re
import streamlit as st
from dashboard.theme import COLORS, score_color, change_color

_CARD_STYLE = (
    f"background:{COLORS['card']};"
    f"backdrop-filter:blur(20px);"
    f"-webkit-backdrop-filter:blur(20px);"
    f"border:1px solid {COLORS['border']};"
    f"border-radius:20px;"
    f"padding:28px;"
)


def _clean_text(text: str) -> str:
    """Clean internal formatting from analysis text for display."""
    if not text:
        return ""
    # Remove [~], [+], [-], [!] prefix markers
    text = re.sub(r'\[[\~\+\-\!]\]\s*', '', text)
    # Remove internal labels like SEC_FILING:, NEWS:, TECHNICAL:
    text = re.sub(r'^[A-Z_]{3,20}:\s*', '', text.strip())
    # Escape HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.strip()


def _sub_score_pill(label: str, value: float, color: str) -> str:
    """Render a compact sub-score pill with label and value."""
    return (
        f'<div style="display:flex;flex-direction:column;align-items:center;min-width:52px;">'
        f'<div style="width:40px;height:40px;border-radius:50%;background:{color}18;'
        f'display:flex;align-items:center;justify-content:center;margin-bottom:4px;">'
        f'<span style="font-size:15px;font-weight:600;color:{color};">{value:.0f}</span></div>'
        f'<span style="font-size:10px;color:{COLORS["text_muted"]};text-transform:uppercase;'
        f'letter-spacing:0.04em;">{label}</span></div>'
    )


def _detail_row(label: str, value: str, color: str = None) -> str:
    """Render a label: value detail row in HTML."""
    val_color = color or COLORS["text"]
    return (
        f'<div style="display:flex;align-items:baseline;gap:6px;padding:5px 0;'
        f'border-bottom:1px solid {COLORS["border"]};">'
        f'<span style="font-size:12px;font-weight:600;color:{COLORS["text_secondary"]};'
        f'white-space:nowrap;min-width:80px;">{label}</span>'
        f'<span style="font-size:13px;color:{val_color};line-height:1.5;">{value}</span></div>'
    )


def _safe_float(v, default=0.0) -> float:
    """Coerce to float, replacing NaN/None with default."""
    import math
    try:
        f = float(v)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _level_badge(label: str, value: float, color: str) -> str:
    """Render a price level badge."""
    value = _safe_float(value)
    return (
        f'<div style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;'
        f'border-radius:6px;background:{color}12;margin-right:8px;">'
        f'<span style="font-size:10px;color:{COLORS["text_muted"]};">{label}</span>'
        f'<span style="font-size:13px;font-weight:600;color:{color};">${value:.2f}</span></div>'
    )


def ticker_card(pick, rank: int = 0, show_details: bool = True):
    """Render a detailed ticker card."""
    # Sanitize NaN values before formatting
    pick.price = _safe_float(pick.price)
    pick.pct_change = _safe_float(pick.pct_change)
    pick.composite_score = _safe_float(pick.composite_score)
    pick.rel_volume = _safe_float(pick.rel_volume, 1.0)
    pick.rsi = _safe_float(pick.rsi, 50.0)
    pick.risk_reward = _safe_float(pick.risk_reward)
    pick.entry_price = _safe_float(pick.entry_price)
    pick.stop_price = _safe_float(pick.stop_price)
    pick.target_price = _safe_float(pick.target_price)
    pick.hurst = _safe_float(pick.hurst, 0.5)

    sc = score_color(pick.composite_score)
    cc = change_color(pick.pct_change)
    arrow = "+" if pick.pct_change >= 0 else ""

    # Direction badge
    dir_color = COLORS["success"] if pick.direction == "LONG" else COLORS["danger"]
    dir_label = "LONG" if pick.direction == "LONG" else "SHORT"

    rank_str = f"#{rank} " if rank > 0 else ""

    html = (
        f'<div style="{_CARD_STYLE}margin-bottom:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div>'
        f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
        f'letter-spacing:0.06em;">{rank_str}{pick.asset_class.upper()}</div>'
        f'<div style="font-size:28px;font-weight:600;color:{COLORS["text"]};'
        f'margin-top:4px;">{pick.ticker}</div>'
        f'<div style="font-size:14px;color:{COLORS["text_secondary"]};margin-top:4px;">'
        f'${pick.price:.2f}'
        f'<span style="color:{cc};margin-left:8px;">{arrow}{pick.pct_change:.1f}%</span>'
        f'</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:42px;font-weight:300;color:{sc};">{pick.composite_score:.0f}</div>'
        f'<div style="font-size:11px;color:{COLORS["text_muted"]};">SCORE</div>'
        f'</div></div>'
        f'<div style="margin-top:16px;padding-top:16px;border-top:1px solid {COLORS["divider"]};">'
        f'<div style="display:flex;gap:24px;flex-wrap:wrap;">'
        f'<div><span style="font-size:11px;color:{COLORS["text_muted"]};">REGIME</span><br>'
        f'<span style="font-size:14px;color:{COLORS["text"]};">{pick.regime}</span></div>'
        f'<div><span style="font-size:11px;color:{COLORS["text_muted"]};">PHASE</span><br>'
        f'<span style="font-size:14px;color:{COLORS["text"]};">{pick.kinematic_phase}</span></div>'
        f'<div><span style="font-size:11px;color:{COLORS["text_muted"]};">RVOL</span><br>'
        f'<span style="font-size:14px;color:{COLORS["text"]};">{pick.rel_volume:.1f}x</span></div>'
        f'<div><span style="font-size:11px;color:{COLORS["text_muted"]};">DIRECTION</span><br>'
        f'<span style="font-size:14px;color:{dir_color};">{dir_label}</span></div>'
        f'</div></div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    if show_details:
        with st.expander(f"Details — {pick.ticker}", expanded=False):
            # Sub-scores as colored circle pills (pure HTML, not st.metric)
            physics_c = score_color(pick.physics_score)
            tech_c = score_color(pick.technical_score)
            cat_c = score_color(pick.catalyst_score)
            stat_c = score_color(pick.statistical_score)
            soc_c = score_color(pick.social_score)

            scores_html = (
                f'<div style="display:flex;justify-content:space-around;padding:12px 0 16px 0;'
                f'border-bottom:1px solid {COLORS["border"]};margin-bottom:12px;">'
                f'{_sub_score_pill("Physics", pick.physics_score, physics_c)}'
                f'{_sub_score_pill("Technical", pick.technical_score, tech_c)}'
                f'{_sub_score_pill("Catalyst", pick.catalyst_score, cat_c)}'
                f'{_sub_score_pill("Stats", pick.statistical_score, stat_c)}'
                f'{_sub_score_pill("Social", pick.social_score, soc_c)}'
                f'</div>'
            )
            st.markdown(scores_html, unsafe_allow_html=True)

            # Detail rows (all HTML, no markdown $ issues)
            details_html = ""

            if pick.why_moving:
                clean_why = _clean_text(pick.why_moving[:200])
                if clean_why:
                    details_html += _detail_row("Why Moving", clean_why)

            if pick.catalyst_summary:
                clean_cat = _clean_text(pick.catalyst_summary[:200])
                if clean_cat:
                    details_html += _detail_row("Catalyst", clean_cat)

            # Support / Resistance as badges
            if pick.nearest_support > 0:
                levels_html = (
                    _level_badge("Support", pick.nearest_support, COLORS["success"])
                    + _level_badge("Resistance", pick.nearest_resistance, COLORS["danger"])
                )
                details_html += (
                    f'<div style="padding:8px 0;border-bottom:1px solid {COLORS["border"]};">'
                    f'<div style="font-size:10px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                    f'letter-spacing:0.04em;margin-bottom:6px;">Key Levels</div>'
                    f'{levels_html}</div>'
                )

            # Entry / Stop / Target
            if pick.entry_price > 0:
                entry_color = COLORS["accent"]
                stop_color = COLORS["danger"]
                target_color = COLORS["success"]
                rr = pick.risk_reward
                rr_color = COLORS["success"] if rr >= 2 else (COLORS["warning"] if rr >= 1 else COLORS["danger"])

                trade_html = (
                    f'<div style="padding:8px 0;border-bottom:1px solid {COLORS["border"]};">'
                    f'<div style="font-size:10px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                    f'letter-spacing:0.04em;margin-bottom:6px;">Trade Setup</div>'
                    f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
                    f'<div style="padding:3px 10px;border-radius:6px;background:{entry_color}12;">'
                    f'<span style="font-size:10px;color:{COLORS["text_muted"]};">Entry</span> '
                    f'<span style="font-size:13px;font-weight:600;color:{entry_color};">${pick.entry_price:.2f}</span></div>'
                    f'<span style="color:{COLORS["text_dim"]};">→</span>'
                    f'<div style="padding:3px 10px;border-radius:6px;background:{stop_color}12;">'
                    f'<span style="font-size:10px;color:{COLORS["text_muted"]};">Stop</span> '
                    f'<span style="font-size:13px;font-weight:600;color:{stop_color};">${pick.stop_price:.2f}</span></div>'
                    f'<span style="color:{COLORS["text_dim"]};">→</span>'
                    f'<div style="padding:3px 10px;border-radius:6px;background:{target_color}12;">'
                    f'<span style="font-size:10px;color:{COLORS["text_muted"]};">Target</span> '
                    f'<span style="font-size:13px;font-weight:600;color:{target_color};">${pick.target_price:.2f}</span></div>'
                    f'<div style="padding:3px 10px;border-radius:6px;background:{rr_color}12;">'
                    f'<span style="font-size:12px;font-weight:600;color:{rr_color};">R:R {rr:.1f}x</span></div>'
                    f'</div></div>'
                )
                details_html += trade_html

            # Options play
            if pick.option_exp_short and pick.option_exp_short != "N/A":
                opt_dir = pick.option_direction or ""
                opt_color = COLORS["success"] if "CALL" in opt_dir.upper() else COLORS["danger"]
                opt_strike = pick.option_safe_strike or ""
                opt_exp = pick.option_exp_long or pick.option_exp_short or ""
                opt_budget = pick.option_budget or ""

                option_html = (
                    f'<div style="padding:8px 0;">'
                    f'<div style="font-size:10px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                    f'letter-spacing:0.04em;margin-bottom:6px;">Option Play</div>'
                    f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
                    f'<span style="padding:3px 10px;border-radius:6px;background:{opt_color}18;'
                    f'color:{opt_color};font-size:12px;font-weight:700;">{opt_dir}</span>'
                    f'<span style="font-size:13px;color:{COLORS["text"]};font-weight:600;">${opt_strike}</span>'
                    f'<span style="font-size:12px;color:{COLORS["text_secondary"]};">exp {opt_exp}</span>'
                    f'<span style="font-size:11px;color:{COLORS["text_dim"]};">Budget: {opt_budget}</span>'
                    f'</div></div>'
                )
                details_html += option_html

            if details_html:
                st.markdown(f'<div style="padding:4px 0;">{details_html}</div>', unsafe_allow_html=True)

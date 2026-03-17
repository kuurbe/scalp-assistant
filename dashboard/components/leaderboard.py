"""
Leaderboard table component — clean sortable table of scored tickers.
Supports Simple and Advanced view modes + BUY/HOLD/SELL signal column.
Matches reference card-based design with clean typography.
"""
import math
import streamlit as st
import pandas as pd
from dashboard.theme import COLORS


def _safe(val, default=0):
    """Return default if val is NaN, None, or inf."""
    if val is None:
        return default
    try:
        if math.isnan(val) or math.isinf(val):
            return default
    except (TypeError, ValueError):
        return default
    return val


def render_leaderboard(scored_tickers: list, max_rows: int = 20, simple: bool = False):
    """Render a leaderboard table from scored tickers."""
    if not scored_tickers:
        st.markdown(f"""
        <div style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:20px;
                    padding:40px;text-align:center;color:{COLORS['text_dim']};">
            No data yet. Run a scan to populate.
        </div>
        """, unsafe_allow_html=True)
        return

    try:
        from signals.recommendation import get_recommendation
        has_recs = True
    except ImportError:
        has_recs = False

    if simple:
        _render_simple(scored_tickers, max_rows, has_recs)
    else:
        _render_advanced(scored_tickers, max_rows, has_recs)


def _render_simple(scored_tickers: list, max_rows: int, has_recs: bool):
    """Simplified leaderboard — plain English columns with clean design."""
    from signals.recommendation import get_recommendation

    signal_html = ""
    for i, pick in enumerate(scored_tickers[:max_rows], 1):
        price = _safe(pick.price)
        pct = _safe(pick.pct_change)
        arrow = "+" if pct >= 0 else ""
        rec = get_recommendation(pick) if has_recs else {"signal": "—", "action": "Monitor"}
        sig = rec["signal"]
        action = rec.get("action", "Monitor")[:40]
        change_color = COLORS["success"] if pct >= 0 else COLORS["danger"]

        if sig == "BUY":
            sig_color = COLORS["success"]
            sig_bg = f"rgba({int(COLORS['success'][1:3],16)},{int(COLORS['success'][3:5],16)},{int(COLORS['success'][5:7],16)},0.12)"
        elif sig == "SELL":
            sig_color = COLORS["danger"]
            sig_bg = f"rgba({int(COLORS['danger'][1:3],16)},{int(COLORS['danger'][3:5],16)},{int(COLORS['danger'][5:7],16)},0.12)"
        else:
            sig_color = COLORS["text_muted"]
            sig_bg = f"rgba({int(COLORS['text_muted'][1:3],16)},{int(COLORS['text_muted'][3:5],16)},{int(COLORS['text_muted'][5:7],16)},0.08)"

        row_bg = f"background:{COLORS['card_hover']};" if i % 2 == 0 else ""

        signal_html += (
            f'<div style="display:flex;align-items:center;padding:12px 16px;{row_bg}'
            f'border-bottom:1px solid {COLORS["border"]};">'
            f'<div style="min-width:30px;color:{COLORS["text_dim"]};font-size:12px;font-weight:500;">{i}</div>'
            f'<div style="min-width:75px;color:{COLORS["text"]};font-weight:600;font-size:14px;">{pick.ticker}</div>'
            f'<div style="min-width:65px;">'
            f'<span style="background:{sig_bg};color:{sig_color};padding:3px 10px;border-radius:6px;'
            f'font-size:11px;font-weight:700;">{sig}</span></div>'
            f'<div style="min-width:90px;color:{COLORS["text"]};font-size:14px;">${price:.2f}</div>'
            f'<div style="min-width:75px;color:{change_color};font-size:13px;font-weight:500;">{arrow}{pct:.1f}%</div>'
            f'<div style="flex:1;color:{COLORS["text_secondary"]};font-size:12px;">{action}</div>'
            f'</div>'
        )

    st.markdown(f"""
    <div style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:20px;
                overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
        <div style="display:flex;align-items:center;padding:12px 16px;
                    background:{COLORS['bg']};border-bottom:1px solid {COLORS['border']};">
            <div style="min-width:30px;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">#</div>
            <div style="min-width:75px;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">Stock</div>
            <div style="min-width:65px;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">Signal</div>
            <div style="min-width:90px;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">Price</div>
            <div style="min-width:75px;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">Today</div>
            <div style="flex:1;font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                        letter-spacing:0.06em;font-weight:600;">What to Do</div>
        </div>
        {signal_html}
    </div>
    """, unsafe_allow_html=True)


def _render_advanced(scored_tickers: list, max_rows: int, has_recs: bool):
    """Advanced leaderboard with full technical data + signal column."""
    rows = []
    for i, pick in enumerate(scored_tickers[:max_rows], 1):
        price = _safe(pick.price)
        pct = _safe(pick.pct_change)
        rvol = _safe(pick.rel_volume)
        score = _safe(pick.composite_score)
        arrow = "+" if pct >= 0 else ""
        row = {
            "#": i,
            "Ticker": pick.ticker,
            "Score": round(score, 0),
            "Signal": "—",
            "Price": f"${price:.2f}",
            "Change": f"{arrow}{pct:.1f}%",
            "RVol": f"{rvol:.1f}x",
            "Regime": pick.regime[:14],
            "Phase": pick.kinematic_phase[:10],
            "Direction": pick.direction,
        }

        if has_recs:
            from signals.recommendation import get_recommendation
            rec = get_recommendation(pick)
            row["Signal"] = rec["signal"]

        rows.append(row)

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Ticker": st.column_config.TextColumn(width="small"),
            "Score": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f", width="small",
            ),
            "Signal": st.column_config.TextColumn(width="small"),
            "Price": st.column_config.TextColumn(width="small"),
            "Change": st.column_config.TextColumn(width="small"),
            "RVol": st.column_config.TextColumn(width="small"),
            "Regime": st.column_config.TextColumn(width="medium"),
            "Phase": st.column_config.TextColumn(width="small"),
            "Direction": st.column_config.TextColumn(width="small"),
        },
    )

"""
Glossary system — hover tooltips and a reference panel for trading jargon.
Makes the dashboard accessible to beginners in Simple mode.
"""
from dashboard.theme import COLORS

# ─── Term Definitions ───
TERMS = {
    "BUY": "Our system thinks this stock is likely to go up. Consider buying.",
    "SELL": "Our system thinks this stock may go down. Consider selling or avoiding.",
    "HOLD": "No strong signal either way. Wait for a clearer setup.",
    "VIX": "The 'fear gauge' — measures how nervous the market is. Higher = more uncertainty.",
    "Fear & Greed": "A 0–100 score. Low = investors are scared (often a buying opportunity). High = investors are greedy (market may be overextended).",
    "RSI": "Relative Strength Index — measures if a stock is overbought (>70) or oversold (<30).",
    "Put/Call Ratio": "Compares bearish bets to bullish bets. High = more fear. Low = more confidence.",
    "Insider Buying": "When company executives buy their own stock — often a bullish sign.",
    "Regime": "The current market 'mode' — trending, mean-reverting, or random.",
    "Composite Score": "Our overall rating (0–100) combining momentum, technicals, catalysts, and sentiment.",
    "SPARK": "A momentum ignition signal — the stock is starting to move with unusual energy.",
    "Dip": "A temporary price drop that may be a buying opportunity if the stock is otherwise healthy.",
    "Relative Volume": "Today's volume compared to the average. 2.0x means twice the normal trading activity.",
    "Support": "A price level where buyers tend to step in — the stock's 'floor'.",
    "Resistance": "A price level where sellers tend to appear — the stock's 'ceiling'.",
    "ATR": "Average True Range — how much a stock typically moves per day in dollars.",
    "Mean Reversion": "The tendency for prices to return to their average after big moves.",
    "Momentum": "The speed and strength of a price move. Strong momentum = strong trend.",
    "Macro": "Big-picture economic factors — interest rates, inflation, GDP, employment.",
    "Prediction Markets": "Platforms where people bet real money on future events. The prices show crowd-estimated probabilities.",
    "PCR": "Put/Call Ratio — see Put/Call Ratio above.",
    "DXY": "US Dollar Index — measures the dollar's strength against a basket of other currencies.",
    "Yield Curve": "The difference between long-term and short-term interest rates. Inverted = recession warning.",
    "Safe Haven": "Assets that hold value during crises — gold, bonds, Swiss franc.",
    "Options": "Contracts that give the right to buy (CALL) or sell (PUT) a stock at a set price.",
    "CALL": "An options bet that the stock price will go UP.",
    "PUT": "An options bet that the stock price will go DOWN.",
    "Risk/Reward": "How much you could gain vs. how much you could lose. Higher is better.",
}


def glossary_css() -> str:
    """Return CSS for tooltip styling. Include once per page."""
    return (
        "<style>"
        ".tip{position:relative;display:inline;border-bottom:1px dotted " + COLORS['text_muted'] + ";cursor:help;}"
        ".tip .tiptext{visibility:hidden;width:260px;background:" + COLORS['bg_elevated'] + ";"
        "color:" + COLORS['text_secondary'] + ";font-size:12px;line-height:1.4;"
        "border-radius:10px;padding:12px;position:absolute;z-index:999;"
        "bottom:125%;left:50%;margin-left:-130px;"
        "border:1px solid " + COLORS['border'] + ";box-shadow:0 4px 12px rgba(0,0,0,0.3);}"
        ".tip:hover .tiptext{visibility:visible;}"
        "</style>"
    )


def tip(term: str, label: str = "") -> str:
    """Return HTML for a tooltip span. Use inside st.markdown(unsafe_allow_html=True).

    Args:
        term: The glossary term to explain (must be a key in TERMS)
        label: Display text (defaults to term itself)
    """
    display = label or term
    definition = TERMS.get(term, "")
    if not definition:
        return display
    return (
        f'<span class="tip">{display}'
        f'<span class="tiptext">{definition}</span></span>'
    )


def render_glossary_panel():
    """Render a full glossary reference panel as expandable HTML."""
    import streamlit as st

    rows = ""
    for term, definition in sorted(TERMS.items()):
        rows += (
            f'<div style="padding:10px 0;border-bottom:1px solid {COLORS["border"]};">'
            f'<span style="font-weight:600;color:{COLORS["text"]};font-size:14px;">{term}</span>'
            f'<div style="color:{COLORS["text_secondary"]};font-size:13px;margin-top:2px;line-height:1.4;">{definition}</div>'
            f'</div>'
        )

    with st.expander("Glossary — What do these terms mean?", expanded=False):
        st.markdown(
            f'<div style="max-height:400px;overflow-y:auto;">{rows}</div>',
            unsafe_allow_html=True,
        )

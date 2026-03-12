"""
Score gauge component — thin arc/ring for 0-100 scores.
"""
import streamlit as st
from dashboard.theme import COLORS, score_color


def render_score_gauge(score: float, label: str = "Score", size: int = 120):
    """Render a circular score gauge using SVG."""
    color = score_color(score)
    pct = score / 100
    circumference = 2 * 3.14159 * 40
    offset = circumference * (1 - pct)

    st.markdown(f"""
    <div style="text-align:center; padding:8px;">
        <svg width="{size}" height="{size}" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="40" fill="none"
                    stroke="{COLORS['bg_elevated']}" stroke-width="6"/>
            <circle cx="50" cy="50" r="40" fill="none"
                    stroke="{color}" stroke-width="6"
                    stroke-dasharray="{circumference}"
                    stroke-dashoffset="{offset}"
                    stroke-linecap="round"
                    transform="rotate(-90 50 50)"/>
            <text x="50" y="48" text-anchor="middle" dominant-baseline="middle"
                  fill="{COLORS['text']}" font-size="22" font-weight="300"
                  font-family="Inter, -apple-system, sans-serif">{score:.0f}</text>
            <text x="50" y="65" text-anchor="middle"
                  fill="{COLORS['text_muted']}" font-size="8"
                  font-family="Inter, -apple-system, sans-serif">{label}</text>
        </svg>
    </div>
    """, unsafe_allow_html=True)

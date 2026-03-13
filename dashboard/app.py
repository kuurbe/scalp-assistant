"""
Scalp Assistant v4 — Live Dashboard
Clean card-based design: light background, white cards, soft shadows, Inter typography.
"""
import sys
import os

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import streamlit as st

# Page config must be first Streamlit call
st.set_page_config(
    page_title="Scalp Assistant",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.theme import COLORS, GLOBAL_CSS, FONT
from dashboard.state import init_state

# Inject global CSS
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Initialize session state
init_state()

# ─── Auto-Refresh ───
try:
    from streamlit_autorefresh import st_autorefresh
    if st.session_state.get("auto_refresh", True):
        st_autorefresh(interval=60_000, limit=None, key="auto_refresh_timer")
except ImportError:
    pass

# ─── Sidebar Navigation ───
with st.sidebar:
    # Brand header
    st.markdown(f"""
    <div style="padding:20px 16px 28px 16px;">
        <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:32px;height:32px;border-radius:10px;background:{COLORS['accent']};
                        display:flex;align-items:center;justify-content:center;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                    <path d="M23 6l-9.5 9.5-5-5L1 18M17 6h6v6"/></svg>
            </div>
            <div>
                <div style="font-size:18px; font-weight:600; color:{COLORS['text']};
                            letter-spacing:-0.02em; font-family:{FONT};">
                    Scalp Assistant
                </div>
                <div style="font-size:11px; color:{COLORS['text_dim']};
                            letter-spacing:0.02em;">
                    v4 — Multi-Asset
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Navigation
    st.markdown(f"""
    <div style="font-size:10px; color:{COLORS['text_dim']}; text-transform:uppercase;
                letter-spacing:0.1em; padding:0 16px 6px 16px; margin-top:4px; font-weight:600;">
        Navigate
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        [
            "Market Overview",
            "Stocks",
            "ETFs",
            "Crypto",
            "Forex",
            "Commodities",
            "Macro",
            "Events",
            "ML Predictions",
            "Alerts",
        ],
        label_visibility="collapsed",
    )

    # Divider
    st.markdown(f"<hr style='border-top:1px solid {COLORS['divider']};margin:14px 0;'>",
                unsafe_allow_html=True)

    # Settings area
    st.markdown(f"""
    <div style="font-size:10px; color:{COLORS['text_dim']}; text-transform:uppercase;
                letter-spacing:0.1em; padding:0 16px 6px 16px; font-weight:600;">
        Settings
    </div>
    """, unsafe_allow_html=True)

    auto_refresh = st.toggle("Auto-refresh (60s)", value=st.session_state.get("auto_refresh", True))
    st.session_state["auto_refresh"] = auto_refresh

    view_mode = st.radio(
        "View Mode",
        ["Simple", "Advanced"],
        index=0 if st.session_state.get("view_mode", "Simple") == "Simple" else 1,
        horizontal=True,
        key="view_mode_radio",
    )
    st.session_state["view_mode"] = view_mode

    # Glossary panel in sidebar (Simple mode only)
    if view_mode == "Simple":
        st.markdown(f"<hr style='border-top:1px solid {COLORS['divider']};margin:10px 0;'>",
                    unsafe_allow_html=True)
        try:
            from dashboard.components.glossary import render_glossary_panel
            render_glossary_panel()
        except Exception:
            pass

    # Status indicator
    st.markdown(f"""
    <div style="position:fixed; bottom:20px; left:16px; font-size:11px; color:{COLORS['text_dim']};
                display:flex;align-items:center;gap:6px;">
        <span style="width:6px; height:6px; border-radius:50%; background:{COLORS['success']};
                     display:inline-block;"></span>
        Live
    </div>
    """, unsafe_allow_html=True)

# ─── Page Router ───
page_map = {
    "Market Overview": "dashboard.pages.market_overview",
    "Stocks": "dashboard.pages.stocks",
    "ETFs": "dashboard.pages.etfs",
    "Crypto": "dashboard.pages.crypto",
    "Forex": "dashboard.pages.forex",
    "Commodities": "dashboard.pages.commodities",
    "Macro": "dashboard.pages.macro",
    "Events": "dashboard.pages.events",
    "ML Predictions": "dashboard.pages.ml_predictions",
    "Alerts": "dashboard.pages.alerts",
}

module_path = page_map.get(page)
if module_path:
    import importlib
    mod = importlib.import_module(module_path)
    mod.render()

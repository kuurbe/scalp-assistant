"""
Session state management and data caching for the dashboard.
"""
import time
import streamlit as st


def init_state():
    """Initialize session state defaults."""
    defaults = {
        "scan_results": {},       # {asset_class: [ScoredTicker, ...]}
        "last_scan_time": {},     # {asset_class: timestamp}
        "alerts": [],             # Recent alerts/event cards
        "macro_context": {},      # FRED macro data
        "social_intel": {},       # Social intelligence data
        "political_pulse": {},
        "war_watch": {},
        "influencer_pulse": {},
        "auto_refresh": True,
        "scan_running": False,
        "view_mode": "Simple",    # "Simple" or "Advanced"
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def needs_refresh(asset_class: str, ttl: int = 60) -> bool:
    """Check if an asset class scan needs refreshing."""
    last = st.session_state.get("last_scan_time", {}).get(asset_class, 0)
    return (time.time() - last) > ttl


def set_scan_results(asset_class: str, results: list):
    """Store scan results for an asset class."""
    st.session_state["scan_results"][asset_class] = results
    st.session_state["last_scan_time"][asset_class] = time.time()


def get_scan_results(asset_class: str) -> list:
    """Get cached scan results for an asset class."""
    return st.session_state.get("scan_results", {}).get(asset_class, [])

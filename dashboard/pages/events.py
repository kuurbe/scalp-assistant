"""
Events page — prediction markets, event contracts, sports.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card
from dashboard import data_bridge


def render():
    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:8px;">
        Events & Prediction Markets
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:32px;">
        Polymarket + Kalshi — sports, politics, economics, crypto, world events
    </div>
    """, unsafe_allow_html=True)

    # Fetch events
    events = data_bridge.get_event_contracts()

    if not events:
        st.info("No event contract data available. Check API connectivity.")
        return

    # Summary
    categories = {}
    for e in events:
        cat = e.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    cols = st.columns(min(len(categories) + 1, 5))
    with cols[0]:
        metric_card("Total Events", str(len(events)))

    for i, (cat, count) in enumerate(sorted(categories.items(), key=lambda x: -x[1])):
        if i + 1 < len(cols):
            with cols[i + 1]:
                metric_card(cat.title(), str(count))

    st.markdown("<br>", unsafe_allow_html=True)

    # Category filter
    all_cats = ["All"] + sorted(categories.keys())
    selected_cat = st.selectbox("Filter by category", all_cats, label_visibility="collapsed")

    filtered = events if selected_cat == "All" else [
        e for e in events if e.get("category") == selected_cat
    ]

    # Event cards
    for event in filtered[:30]:
        title = event.get("title", "Unknown Event")[:100]
        source = event.get("source", "—")
        category = event.get("category", "—")
        yes_price = event.get("yes_price") or 0
        no_price = event.get("no_price") or 0
        volume = event.get("volume") or 0
        expires = event.get("expires_at") or "—"
        url = event.get("url", "")

        # Coerce to float safely
        try:
            yes_price = float(yes_price)
        except (ValueError, TypeError):
            yes_price = 0.0
        try:
            no_price = float(no_price)
        except (ValueError, TypeError):
            no_price = 0.0

        # Determine implied probability color
        if yes_price > 0.7:
            prob_color = COLORS["success"]
        elif yes_price > 0.4:
            prob_color = COLORS["warning"]
        else:
            prob_color = COLORS["danger"]

        vol_str = f"${volume:,.0f}" if volume else "—"
        yes_str = f"{yes_price:.0%}"
        no_str = f"{no_price:.0%}"

        # Truncate long expiry timestamps to date only
        if expires and len(expires) > 10 and "T" in expires:
            expires = expires.split("T")[0]

        st.markdown(f"""
        <div style="{CARD_CSS} margin-bottom:12px; padding:20px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div style="flex:1;">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                        <span style="font-size:11px; color:{COLORS['accent']}; text-transform:uppercase;
                                     letter-spacing:0.08em; font-weight:500;">{category}</span>
                        <span style="font-size:11px; color:{COLORS['text_dim']};">{source}</span>
                    </div>
                    <div style="font-size:15px; color:{COLORS['text']}; font-weight:500;
                                margin-bottom:8px;">{title}</div>
                    <div style="display:flex; gap:24px; font-size:13px;">
                        <span style="color:{COLORS['text_muted']};">Volume: <span style="color:{COLORS['text_secondary']};">{vol_str}</span></span>
                        <span style="color:{COLORS['text_muted']};">Expires: <span style="color:{COLORS['text_secondary']};">{expires}</span></span>
                    </div>
                </div>
                <div style="text-align:right; min-width:100px;">
                    <div style="font-size:11px; color:{COLORS['text_muted']}; margin-bottom:4px;">YES / NO</div>
                    <div style="font-size:24px; font-weight:300; color:{prob_color};">
                        {yes_str}
                    </div>
                    <div style="font-size:13px; color:{COLORS['text_dim']};">
                        / {no_str}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

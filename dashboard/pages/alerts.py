"""
Alerts page — event card feed, notification settings, signal history.
Supports Simple and Advanced view modes with actionable alert groups.
Clean card-based design matching reference UI.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card, overview_card
from dashboard.components.event_card import alert_feed
from dashboard import data_bridge


def _get_recent_alerts() -> list:
    """Detect event cards from cached scan results + live macro/intel data."""
    try:
        from signals.event_cards import detect_event_cards
        stocks = st.session_state.get("overview_scan_results", [])
        political = data_bridge.get_political_pulse()
        war = data_bridge.get_war_watch()
        influencer = data_bridge.get_influencer_pulse()
        macro = data_bridge.get_macro_context()
        cards = detect_event_cards(stocks, political, war, influencer, macro)
        return cards
    except Exception:
        return []


def _get_notification_status() -> dict:
    try:
        from signals.notification_config import get_enabled_channels
        channels = get_enabled_channels()
        return {ch: True for ch in channels}
    except Exception:
        return {}


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    st.markdown(f"""
    <div style="margin-bottom:28px;">
        <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                    letter-spacing:-0.02em; margin-bottom:6px;">
            {"Alerts & Signals" if is_simple else "Alerts"}
        </div>
        <div style="font-size:14px; color:{COLORS['text_muted']};">
            {"What needs your attention right now" if is_simple else "Event card feed, notification channels, and signal history"}
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Detecting signals..."):
        alerts = _get_recent_alerts()

    # ──────────────────────────────────────────────────────────
    # SIMPLE VIEW — Grouped by action type
    # ──────────────────────────────────────────────────────────
    if is_simple:
        if not alerts:
            st.markdown(f"""
            <div style="{CARD_CSS} text-align:center; padding:48px;">
                <div style="width:48px;height:48px;border-radius:50%;background:{COLORS['success']}10;
                            display:flex;align-items:center;justify-content:center;margin:0 auto 16px auto;">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="{COLORS['success']}" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                </div>
                <div style="font-size:22px; font-weight:400; color:{COLORS['text']}; margin-bottom:8px;">
                    All Clear</div>
                <div style="font-size:14px; color:{COLORS['text_secondary']}; max-width:400px; margin:0 auto;">
                    No active alerts. Run a stock scan first, then alerts will appear here when signals fire.</div>
            </div>
            """, unsafe_allow_html=True)
            return

        buys = [a for a in alerts if a.get("direction") == "BULLISH" or a.get("event_type") in ("SPARK_DETECTED", "DIP_OPPORTUNITY")]
        sells = [a for a in alerts if a.get("direction") == "BEARISH"]
        high_urg = [a for a in alerts if a.get("urgency") == "HIGH"]

        # Summary cards — grouped overview style
        overview_card("Alert Summary", [
            {
                "label": "Buy Signals",
                "value": str(len(buys)),
                "icon": "trending",
                "delta_color": COLORS["success"],
                "delta": "opportunities" if buys else "none",
            },
            {
                "label": "Sell / Caution",
                "value": str(len(sells)),
                "icon": "alert",
                "delta_color": COLORS["danger"],
                "delta": "active" if sells else "none",
            },
            {
                "label": "High Priority",
                "value": str(len(high_urg)),
                "icon": "zap",
                "delta_color": COLORS["warning"],
                "delta": "urgent" if high_urg else "clear",
            },
        ])

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Group alerts
        groups = {}
        for a in alerts:
            etype = a.get("event_type", "")
            direction = a.get("direction", "NEUTRAL")
            if etype in ("SPARK_DETECTED", "DIP_OPPORTUNITY") or direction == "BULLISH":
                groups.setdefault("BUYING OPPORTUNITIES", []).append(a)
            elif direction == "BEARISH":
                groups.setdefault("SELL SIGNALS", []).append(a)
            elif etype in ("MACRO_SHIFT", "POLITICAL_SHIFT", "WAR_ESCALATION"):
                groups.setdefault("MARKET ALERTS", []).append(a)
            else:
                groups.setdefault("NEWS & EVENTS", []).append(a)

        group_meta = {
            "BUYING OPPORTUNITIES": {"color": COLORS["success"], "icon": "trending", "desc": "Strong momentum or dip-buying setups"},
            "SELL SIGNALS": {"color": COLORS["danger"], "icon": "alert", "desc": "Conditions suggesting caution or profit-taking"},
            "MARKET ALERTS": {"color": COLORS["warning"], "icon": "globe", "desc": "Macro events, political shifts, or volatility changes"},
            "NEWS & EVENTS": {"color": COLORS["accent"], "icon": "eye", "desc": "Earnings, influencer activity, and other catalysts"},
        }

        for group_name, group_alerts in groups.items():
            meta = group_meta.get(group_name, {"color": COLORS["text_muted"], "icon": "default", "desc": ""})
            color = meta["color"]

            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                <div style="width:8px;height:8px;border-radius:50%;background:{color};"></div>
                <span style="font-size:16px; font-weight:600; color:{COLORS['text']};">{group_name}</span>
                <span style="font-size:12px; color:{COLORS['text_dim']};">{meta['desc']}</span>
            </div>
            """, unsafe_allow_html=True)

            for a in group_alerts[:5]:
                title = a.get("title", "")[:80]
                tickers = ", ".join(a.get("tickers", [])[:3])
                action = a.get("action_suggestion", "")[:60]
                urgency = a.get("urgency", "LOW")
                urg_color = COLORS["danger"] if urgency == "HIGH" else (COLORS["warning"] if urgency == "MEDIUM" else COLORS["success"])
                urg_bg = f"{urg_color}15"

                ticker_html = f'<span style="color:{COLORS["accent"]};font-weight:600;margin-right:8px;">{tickers}</span>' if tickers else ""
                action_html = f'<span style="color:{COLORS["text_secondary"]};">{action}</span>' if action else ""

                st.markdown(f"""
                <div style="{CARD_CSS} margin-bottom:8px; padding:16px 20px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="flex:1;">
                            <div style="font-size:14px; color:{COLORS['text']}; font-weight:500;margin-bottom:4px;">{title}</div>
                            <div style="font-size:12px;">{ticker_html}{action_html}</div>
                        </div>
                        <span style="background:{urg_bg};color:{urg_color};padding:3px 10px;
                                     border-radius:6px;font-size:10px;font-weight:700;">{urgency}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────
    # ADVANCED VIEW — Full detail with notification settings
    # ──────────────────────────────────────────────────────────
    else:
        channels = _get_notification_status()
        channel_defs = [
            ("Telegram", "telegram", "TELEGRAM_BOT_TOKEN", "Send alerts to Telegram"),
            ("Discord", "discord", "DISCORD_WEBHOOK_URL", "Post to Discord channel"),
            ("macOS", "macos", "", "Desktop notifications"),
            ("Email", "email", "ALERT_EMAIL", "Email alerts"),
        ]

        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            Notification Channels
        </div>
        """, unsafe_allow_html=True)

        cols = st.columns(4)
        for i, (name, key, env_var, desc) in enumerate(channel_defs):
            enabled = channels.get(key, False)
            status_color = COLORS["success"] if enabled else COLORS["text_dim"]
            with cols[i]:
                env_hint = ""
                if not enabled and env_var:
                    env_hint = f"<div style='font-size:10px;color:{COLORS['text_dim']};margin-top:6px;'>Set {env_var} in .env</div>"
                st.markdown(f"""
                <div style="{CARD_CSS} text-align:center; padding:20px;">
                    <div style="width:10px;height:10px;border-radius:50%;background:{status_color};
                                margin:0 auto 10px auto;"></div>
                    <div style="font-size:15px;color:{COLORS['text']};font-weight:500;">{name}</div>
                    <div style="font-size:11px;color:{COLORS['text_muted']};margin-top:4px;">
                        {"Connected" if enabled else "Not configured"}</div>
                    {env_hint}
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Alert settings in grouped card
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            Alert Settings
        </div>
        """, unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            triggers_html = ""
            for tname, tdesc in [
                ("Spark Signals", "Score ≥ 60, IGNITION phase"),
                ("Dip Opportunities", "Score ≥ 50, mean-reverting regime"),
                ("Event Cards", "HIGH urgency macro/political shifts"),
                ("Prediction Outcomes", "Win/loss from prediction markets"),
                ("Achievements", "New achievement unlocked"),
            ]:
                triggers_html += (
                    f'<div style="display:flex;justify-content:space-between;padding:10px 0;'
                    f'border-bottom:1px solid {COLORS["border"]};">'
                    f'<div><div style="font-size:13px;color:{COLORS["text"]};">{tname}</div>'
                    f'<div style="font-size:11px;color:{COLORS["text_dim"]};">{tdesc}</div></div>'
                    f'<span style="color:{COLORS["success"]};font-size:12px;font-weight:500;">Active</span></div>'
                )
            st.markdown(f"""
            <div style="{CARD_CSS}">
                <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                            letter-spacing:0.06em;margin-bottom:12px;">TRIGGER CONDITIONS</div>
                {triggers_html}
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            st.markdown(f"""
            <div style="{CARD_CSS}">
                <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                            letter-spacing:0.06em;margin-bottom:12px;">FILTERS</div>
                <div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};">
                    <div style="font-size:13px;color:{COLORS['text']};">Minimum Score</div>
                    <div style="font-size:11px;color:{COLORS['text_dim']};">55 (configurable in settings.py)</div>
                </div>
                <div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};">
                    <div style="font-size:13px;color:{COLORS['text']};">Quiet Hours</div>
                    <div style="font-size:11px;color:{COLORS['text_dim']};">10 PM — 7 AM (HIGH urgency bypasses)</div>
                </div>
                <div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};">
                    <div style="font-size:13px;color:{COLORS['text']};">Cooldown</div>
                    <div style="font-size:11px;color:{COLORS['text_dim']};">10 min between same-ticker alerts</div>
                </div>
                <div style="padding:10px 0;">
                    <div style="font-size:13px;color:{COLORS['text']};">Deduplication</div>
                    <div style="font-size:11px;color:{COLORS['text_dim']};">15 min window, same event type + ticker</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Live Alert Feed
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            Live Alert Feed
        </div>
        """, unsafe_allow_html=True)

        if alerts:
            high = sum(1 for a in alerts if a.get("urgency") == "HIGH")
            med = sum(1 for a in alerts if a.get("urgency") == "MEDIUM")

            overview_card("Alert Activity", [
                {"label": "Total Alerts", "value": str(len(alerts)), "icon": "alert", "delta_color": COLORS["accent"]},
                {"label": "High Urgency", "value": str(high), "icon": "zap",
                 "delta_color": COLORS["danger"] if high > 0 else COLORS["text_dim"],
                 "delta": "active" if high > 0 else "none"},
                {"label": "Medium", "value": str(med), "icon": "eye",
                 "delta_color": COLORS["warning"] if med > 0 else COLORS["text_dim"]},
            ])

            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

            urgency_filter = st.selectbox("Filter by urgency",
                                           ["All", "HIGH", "MEDIUM", "LOW"],
                                           label_visibility="collapsed")
            filtered = [a for a in alerts if a.get("urgency") == urgency_filter] if urgency_filter != "All" else alerts
            alert_feed(filtered, max_items=20)
        else:
            st.markdown(f"""
            <div style="{CARD_CSS} text-align:center; padding:40px;">
                <div style="width:44px;height:44px;border-radius:50%;background:{COLORS['accent']}10;
                            display:flex;align-items:center;justify-content:center;margin:0 auto 12px auto;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{COLORS['accent']}" stroke-width="2">
                        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/></svg>
                </div>
                <div style="font-size:14px; color:{COLORS['text_secondary']};">
                    No active alerts. Run a stock scan first, then alerts will fire during market hours.</div>
            </div>
            """, unsafe_allow_html=True)

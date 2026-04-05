"""
Alerts page — Regime-aware best plays, event card feed, notification settings.
Supports Simple and Advanced view modes.

Simple: Best plays for current conditions + grouped event cards.
Advanced: Quant filter toggle, notification channels, alert settings, live feed.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS
from dashboard.components.metric_card import metric_card, overview_card
from dashboard.components.event_card import alert_feed
from dashboard import data_bridge


def _get_recent_alerts() -> list:
    try:
        from signals.event_cards import detect_event_cards
        stocks = st.session_state.get("overview_scan_results", [])
        political = data_bridge.get_political_pulse()
        war = data_bridge.get_war_watch()
        influencer = data_bridge.get_influencer_pulse()
        macro = data_bridge.get_macro_context()
        return detect_event_cards(stocks, political, war, influencer, macro)
    except Exception:
        return []


def _get_notification_status() -> dict:
    try:
        from signals.notification_config import get_enabled_channels
        return {ch: True for ch in get_enabled_channels()}
    except Exception:
        return {}


def _get_regime_context():
    try:
        macro = data_bridge.get_macro_context()
        regime = macro.get("macro_regime", "NEUTRAL")
        vix = macro.get("vix", 0)
        return regime, vix
    except Exception:
        return "NEUTRAL", 0


def _get_best_plays(require_quant: bool = True, max_results: int = 5):
    """Get regime-aware best plays from scan results."""
    results = st.session_state.get("overview_scan_results", [])
    if not results:
        return [], "NEUTRAL"

    from config import settings as cfg
    regime, _ = _get_regime_context()
    min_score = getattr(cfg, "BEST_PLAYS_MIN_SCORE", 55)

    candidates = []
    for t in results:
        score = getattr(t, "composite_score", 0)
        if score < min_score:
            continue
        if require_quant and not getattr(t, "quant_aligned", False):
            continue

        if regime == "RISK_OFF":
            r = getattr(t, "regime", "")
            if r in ("CLEAN_REVERSION", "MEAN_REVERTING") or getattr(t, "pct_change", 0) < -2:
                candidates.append(t)
            elif getattr(t, "bayesian_posterior", 0) > 0.6:
                candidates.append(t)
        elif regime == "RISK_ON":
            phase = getattr(t, "kinematic_phase", "")
            if phase in ("IGNITION", "CRUISE") and score >= 60:
                candidates.append(t)
            elif getattr(t, "quant_score", 0) >= 60:
                candidates.append(t)
        else:
            tier = getattr(t, "confidence_tier", "C")
            rr = getattr(t, "risk_reward", 0)
            if tier in ("A", "B") and rr >= 1.5:
                candidates.append(t)
            elif getattr(t, "quant_score", 0) >= 60:
                candidates.append(t)

    # Fallback: if quant filter is too strict, loosen
    if not candidates and require_quant:
        return _get_best_plays(require_quant=False, max_results=max_results)

    if not candidates:
        candidates = sorted(results, key=lambda x: getattr(x, "composite_score", 0), reverse=True)

    candidates.sort(key=lambda x: (getattr(x, "quant_aligned", False), getattr(x, "quant_score", 0), getattr(x, "composite_score", 0)), reverse=True)
    return candidates[:max_results], regime


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    st.markdown(f"""<div style="margin-bottom:28px;"><div style="font-size:34px; font-weight:700; color:{COLORS['text']}; letter-spacing:-0.02em; margin-bottom:6px;">{"Alerts & Signals" if is_simple else "Alerts"}</div><div style="font-size:14px; color:{COLORS['text_muted']};">{"Best plays for current conditions + what needs your attention" if is_simple else "Event cards, notification channels, and signal history"}</div></div>""", unsafe_allow_html=True)

    alerts = _get_recent_alerts()

    if is_simple:
        _render_simple(alerts)
    else:
        _render_advanced(alerts)


def _render_simple(alerts):
    regime, vix = _get_regime_context()
    plays, _ = _get_best_plays()

    # ── Regime Banner ──
    regime_map = {"RISK_ON": ("Bullish", "Showing momentum plays and breakout candidates", COLORS["success"]), "RISK_OFF": ("Stormy", "Showing defensive plays and dip-buying opportunities", COLORS["danger"]), "NEUTRAL": ("Mixed Signals", "Showing balanced setups with strong risk/reward", COLORS["warning"])}
    label, desc, color = regime_map.get(regime, regime_map["NEUTRAL"])
    vix_str = f" | VIX: {vix:.1f}" if vix > 0 else ""

    st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {color}; padding:18px 22px; margin-bottom:20px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">MARKET MODE</div><div style="font-size:22px; font-weight:700; color:{color}; margin-top:4px;">{label}</div><div style="font-size:13px; color:{COLORS['text_secondary']}; margin-top:4px;">{desc}{vix_str}</div></div></div></div>""", unsafe_allow_html=True)

    # ── Best Plays Section ──
    if plays:
        st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">Best Plays Right Now</div>""", unsafe_allow_html=True)

        for pick in plays:
            ticker = pick.ticker
            action = "BUY" if pick.direction == "LONG" else "SELL"
            action_color = COLORS["success"] if action == "BUY" else COLORS["danger"]
            entry = pick.entry_price or pick.price
            stop = pick.stop_price
            target = pick.target_price
            rr = pick.risk_reward
            tier = pick.confidence_tier
            kelly = getattr(pick, "kelly_fraction", 0)
            quant_score = getattr(pick, "quant_score", 0)
            n_agree = getattr(pick, "quant_n_agreeing", 0)
            aligned = getattr(pick, "quant_aligned", False)
            whale = getattr(pick, "whale_score", 0)
            reason = pick.catalyst_summary or pick.where_headed or ""
            reason = reason[:80]

            tier_color = COLORS["success"] if tier == "A" else (COLORS["warning"] if tier == "B" else COLORS["text_dim"])
            aligned_badge = f'<span style="background:{COLORS["success"]}20;color:{COLORS["success"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:8px;">{n_agree}/6 ALIGNED</span>' if aligned else f'<span style="background:{COLORS["warning"]}20;color:{COLORS["warning"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:8px;">{n_agree}/6</span>'
            whale_badge = f'<span style="background:{COLORS["accent"]}20;color:{COLORS["accent"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:6px;">WHALE {whale:.0f}</span>' if whale >= 40 else ""

            stop_str = f"${stop:.2f}" if stop and stop > 0 else "N/A"
            target_str = f"${target:.2f}" if target and target > 0 else "N/A"
            rr_str = f"{rr:.1f}x" if rr and rr > 0 else "N/A"

            st.markdown(f"""<div style="{CARD_CSS} margin-bottom:10px; padding:18px 22px;"><div style="display:flex;justify-content:space-between;align-items:flex-start;"><div style="flex:1;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;"><span style="font-size:18px; font-weight:700; color:{COLORS['text']};">{ticker}</span><span style="background:{action_color}20;color:{action_color};padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;">{action}</span><span style="color:{tier_color};font-size:11px;font-weight:700;">Tier {tier}</span>{aligned_badge}{whale_badge}</div><div style="display:flex;gap:24px;font-size:13px;margin-bottom:6px;"><span style="color:{COLORS['text_secondary']};">Entry <span style="color:{COLORS['text']};font-weight:600;">${entry:.2f}</span></span><span style="color:{COLORS['text_secondary']};">Stop <span style="color:{COLORS['danger']};font-weight:600;">{stop_str}</span></span><span style="color:{COLORS['text_secondary']};">Target <span style="color:{COLORS['success']};font-weight:600;">{target_str}</span></span><span style="color:{COLORS['text_secondary']};">R/R <span style="font-weight:600;">{rr_str}</span></span><span style="color:{COLORS['text_secondary']};">Kelly <span style="font-weight:600;">{kelly*100:.1f}%</span></span></div><div style="font-size:12px; color:{COLORS['text_dim']};">{reason}</div></div><div style="text-align:right;"><div style="font-size:11px; color:{COLORS['text_muted']};">QUANT</div><div style="font-size:22px; font-weight:700; color:{COLORS['accent']};">{quant_score:.0f}</div></div></div></div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── Event Cards (existing functionality) ──
    if not alerts and not plays:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:48px;"><div style="width:48px;height:48px;border-radius:50%;background:{COLORS['success']}10;display:flex;align-items:center;justify-content:center;margin:0 auto 16px auto;"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="{COLORS['success']}" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div><div style="font-size:22px; font-weight:400; color:{COLORS['text']}; margin-bottom:8px;">All Clear</div><div style="font-size:14px; color:{COLORS['text_secondary']}; max-width:400px; margin:0 auto;">No active alerts. Run a stock scan first, then alerts will appear here when signals fire.</div></div>""", unsafe_allow_html=True)
        return

    if alerts:
        # Summary cards
        buys = [a for a in alerts if a.get("direction") == "BULLISH" or a.get("event_type") in ("SPARK_DETECTED", "DIP_OPPORTUNITY")]
        sells = [a for a in alerts if a.get("direction") == "BEARISH"]
        high_urg = [a for a in alerts if a.get("urgency") == "HIGH"]

        overview_card("Alert Summary", [{"label": "Buy Signals", "value": str(len(buys)), "icon": "trending", "delta_color": COLORS["success"], "delta": "opportunities" if buys else "none"}, {"label": "Sell / Caution", "value": str(len(sells)), "icon": "alert", "delta_color": COLORS["danger"], "delta": "active" if sells else "none"}, {"label": "High Priority", "value": str(len(high_urg)), "icon": "zap", "delta_color": COLORS["warning"], "delta": "urgent" if high_urg else "clear"}])

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

        group_meta = {"BUYING OPPORTUNITIES": {"color": COLORS["success"], "desc": "Strong momentum or dip-buying setups"}, "SELL SIGNALS": {"color": COLORS["danger"], "desc": "Conditions suggesting caution or profit-taking"}, "MARKET ALERTS": {"color": COLORS["warning"], "desc": "Macro events, political shifts, or volatility changes"}, "NEWS & EVENTS": {"color": COLORS["accent"], "desc": "Earnings, influencer activity, and other catalysts"}}

        for group_name, group_alerts in groups.items():
            meta = group_meta.get(group_name, {"color": COLORS["text_muted"], "desc": ""})
            color = meta["color"]
            st.markdown(f"""<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><div style="width:8px;height:8px;border-radius:50%;background:{color};"></div><span style="font-size:16px; font-weight:600; color:{COLORS['text']};">{group_name}</span><span style="font-size:12px; color:{COLORS['text_dim']};">{meta['desc']}</span></div>""", unsafe_allow_html=True)

            for a in group_alerts[:5]:
                title = a.get("title", "")[:80]
                tickers = ", ".join(a.get("tickers", [])[:3])
                action = a.get("action_suggestion", "")[:60]
                urgency = a.get("urgency", "LOW")
                urg_color = COLORS["danger"] if urgency == "HIGH" else (COLORS["warning"] if urgency == "MEDIUM" else COLORS["success"])
                urg_bg = f"{urg_color}15"
                ticker_html = f'<span style="color:{COLORS["accent"]};font-weight:600;margin-right:8px;">{tickers}</span>' if tickers else ""
                action_html = f'<span style="color:{COLORS["text_secondary"]};">{action}</span>' if action else ""

                st.markdown(f"""<div style="{CARD_CSS} margin-bottom:8px; padding:16px 20px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div style="flex:1;"><div style="font-size:14px; color:{COLORS['text']}; font-weight:500;margin-bottom:4px;">{title}</div><div style="font-size:12px;">{ticker_html}{action_html}</div></div><span style="background:{urg_bg};color:{urg_color};padding:3px 10px;border-radius:6px;font-size:10px;font-weight:700;">{urgency}</span></div></div>""", unsafe_allow_html=True)

            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)


def _render_advanced(alerts):
    # ── Best Plays with quant filter toggle ──
    quant_filter = st.toggle("Require Quant Alignment (4/6)", value=True, key="alerts_quant_filter")
    plays, regime = _get_best_plays(require_quant=quant_filter, max_results=5)

    if plays:
        regime_label = {"RISK_ON": "Bullish", "RISK_OFF": "Stormy", "NEUTRAL": "Mixed"}.get(regime, "Mixed")
        st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:10px;">Best Plays ({regime_label})</div>""", unsafe_allow_html=True)

        for pick in plays:
            ticker = pick.ticker
            action = "BUY" if pick.direction == "LONG" else "SELL"
            ac = COLORS["success"] if action == "BUY" else COLORS["danger"]
            qs = getattr(pick, "quant_score", 0)
            na = getattr(pick, "quant_n_agreeing", 0)
            kelly = getattr(pick, "kelly_fraction", 0)
            whale = getattr(pick, "whale_score", 0)
            entry = pick.entry_price or pick.price
            stop = pick.stop_price
            target = pick.target_price

            stop_str = f"${stop:.2f}" if stop and stop > 0 else "N/A"
            target_str = f"${target:.2f}" if target and target > 0 else "N/A"
            whale_str = f' | Whale: {whale:.0f}' if whale >= 20 else ""

            st.markdown(f"""<div style="{CARD_CSS} margin-bottom:8px; padding:14px 18px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div><span style="font-size:16px;font-weight:700;color:{COLORS['text']};margin-right:10px;">{ticker}</span><span style="background:{ac}20;color:{ac};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">{action}</span><span style="font-size:12px;color:{COLORS['text_secondary']};margin-left:12px;">${entry:.2f} | Stop {stop_str} | Target {target_str} | Kelly {kelly*100:.1f}% | {na}/6 formulas{whale_str}</span></div><div style="font-size:18px;font-weight:700;color:{COLORS['accent']};">{qs:.0f}</div></div></div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # ── Notification Channels ──
    channels = _get_notification_status()
    channel_defs = [("Telegram", "telegram", "TELEGRAM_BOT_TOKEN", "Send alerts to Telegram"), ("Discord", "discord", "DISCORD_WEBHOOK_URL", "Post to Discord channel"), ("macOS", "macos", "", "Desktop notifications"), ("Email", "email", "ALERT_EMAIL", "Email alerts")]

    st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">Notification Channels</div>""", unsafe_allow_html=True)

    cols = st.columns(4)
    for i, (name, key, env_var, desc) in enumerate(channel_defs):
        enabled = channels.get(key, False)
        status_color = COLORS["success"] if enabled else COLORS["text_dim"]
        with cols[i]:
            env_hint = ""
            if not enabled and env_var:
                env_hint = f"<div style='font-size:10px;color:{COLORS['text_dim']};margin-top:6px;'>Set {env_var} in .env</div>"
            st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="width:10px;height:10px;border-radius:50%;background:{status_color};margin:0 auto 10px auto;"></div><div style="font-size:15px;color:{COLORS['text']};font-weight:500;">{name}</div><div style="font-size:11px;color:{COLORS['text_muted']};margin-top:4px;">{"Connected" if enabled else "Not configured"}</div>{env_hint}</div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── Alert Settings ──
    st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">Alert Settings</div>""", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        triggers_html = ""
        for tname, tdesc in [("Spark Signals", "Score >= 60, IGNITION phase"), ("Dip Opportunities", "Score >= 50, mean-reverting regime"), ("Event Cards", "HIGH urgency macro/political shifts"), ("Quant Aligned", "4/6 formulas agree on direction"), ("Whale Detection", "Unusual volume or sweep patterns")]:
            triggers_html += f'<div style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid {COLORS["border"]};"><div><div style="font-size:13px;color:{COLORS["text"]};">{tname}</div><div style="font-size:11px;color:{COLORS["text_dim"]};">{tdesc}</div></div><span style="color:{COLORS["success"]};font-size:12px;font-weight:500;">Active</span></div>'
        st.markdown(f"""<div style="{CARD_CSS}"><div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;">TRIGGER CONDITIONS</div>{triggers_html}</div>""", unsafe_allow_html=True)

    with col_b:
        st.markdown(f"""<div style="{CARD_CSS}"><div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;">FILTERS</div><div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};"><div style="font-size:13px;color:{COLORS['text']};">Minimum Score</div><div style="font-size:11px;color:{COLORS['text_dim']};">55 (configurable in settings.py)</div></div><div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};"><div style="font-size:13px;color:{COLORS['text']};">Quiet Hours</div><div style="font-size:11px;color:{COLORS['text_dim']};">10 PM - 7 AM (HIGH urgency bypasses)</div></div><div style="padding:10px 0;border-bottom:1px solid {COLORS['border']};"><div style="font-size:13px;color:{COLORS['text']};">Cooldown</div><div style="font-size:11px;color:{COLORS['text_dim']};">30 min between same-ticker alerts</div></div><div style="padding:10px 0;"><div style="font-size:13px;color:{COLORS['text']};">Quant Alignment</div><div style="font-size:11px;color:{COLORS['text_dim']};">4/6 formulas must agree (toggleable)</div></div></div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── Live Alert Feed ──
    st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">Live Alert Feed</div>""", unsafe_allow_html=True)

    if alerts:
        high = sum(1 for a in alerts if a.get("urgency") == "HIGH")
        med = sum(1 for a in alerts if a.get("urgency") == "MEDIUM")
        overview_card("Alert Activity", [{"label": "Total Alerts", "value": str(len(alerts)), "icon": "alert", "delta_color": COLORS["accent"]}, {"label": "High Urgency", "value": str(high), "icon": "zap", "delta_color": COLORS["danger"] if high > 0 else COLORS["text_dim"], "delta": "active" if high > 0 else "none"}, {"label": "Medium", "value": str(med), "icon": "eye", "delta_color": COLORS["warning"] if med > 0 else COLORS["text_dim"]}])

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        urgency_filter = st.selectbox("Filter by urgency", ["All", "HIGH", "MEDIUM", "LOW"], label_visibility="collapsed")
        filtered = [a for a in alerts if a.get("urgency") == urgency_filter] if urgency_filter != "All" else alerts
        alert_feed(filtered, max_items=20)
    else:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:40px;"><div style="width:44px;height:44px;border-radius:50%;background:{COLORS['accent']}10;display:flex;align-items:center;justify-content:center;margin:0 auto 12px auto;"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{COLORS['accent']}" stroke-width="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/></svg></div><div style="font-size:14px; color:{COLORS['text_secondary']};">No active alerts. Run a stock scan first, then alerts will fire during market hours.</div></div>""", unsafe_allow_html=True)

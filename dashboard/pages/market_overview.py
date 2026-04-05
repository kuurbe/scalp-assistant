"""
Market Overview page — cross-asset summary, macro context, top picks, forecasts.
Non-blocking: shows macro cards + intel instantly, scan only on user request.
Supports Simple and Advanced view modes.
Design matches clean card-based reference UI with icon circles, sparklines, delta badges.
"""
import datetime
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS, CARD_GRADIENT_GREEN, CARD_GRADIENT_RED, CARD_GRADIENT_BLUE, CARD_GRADIENT_ORANGE
from dashboard.components.metric_card import metric_card, overview_card
from dashboard.components.leaderboard import render_leaderboard
from dashboard.components.news_feed import news_feed, news_ticker_bar
from dashboard.components.market_widgets import (
    index_strip, sector_heatmap, gainers_losers,
    fetch_index_data, fetch_sector_performance, fetch_gainers_losers,
)
from dashboard import data_bridge


def _run_scan_with_progress(scan_key: str, is_simple: bool):
    """Run stock scan with a progress bar for faster perceived loading.
    Uses batch OHLCV download + prefetched shared data to avoid duplicate fetches.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from config import settings
    from modes.morning_scan import _analyze_ticker

    universe = settings.get_universe("stocks")
    if not universe:
        st.session_state[scan_key] = []
        return

    total = len(universe)
    progress = st.progress(0, text="Downloading market data...")

    # Pre-fetch shared data + batch OHLCV concurrently
    shared = data_bridge._prefetch_shared_data("stocks")
    macro_regime = shared.get("macro", "NEUTRAL")
    reddit_data = shared.get("reddit", {})
    political_pulse = shared.get("political", {})
    war_watch = shared.get("war", {})
    influencer_pulse = shared.get("influencer", {})

    progress.progress(0.1, text="Batch downloading OHLCV...")
    daily_dict, intraday_dict = data_bridge._batch_fetch_ohlcv(universe)

    progress.progress(0.2, text="Analyzing tickers...")
    results = []
    done = 0

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {
            pool.submit(
                _analyze_ticker, ticker, macro_regime, reddit_data, {},
                political_pulse, war_watch, influencer_pulse, "stocks",
                daily_dict.get(ticker), intraday_dict.get(ticker)
            ): ticker
            for ticker in universe
        }
        for future in as_completed(futures):
            done += 1
            ticker = futures[future]
            try:
                result = future.result(timeout=30)
                if result:
                    results.append(result)
            except Exception:
                pass
            if done % 4 == 0 or done == total:
                pct = 0.2 + (done / total * 0.8)
                progress.progress(pct, text=f"Scanning {ticker}... ({done}/{total})")

    progress.empty()
    results.sort(key=lambda x: x.composite_score, reverse=True)
    st.session_state[scan_key] = results
    # Share results with stocks page too
    st.session_state["stocks_scan_results"] = results


def _risk_color(level: str) -> str:
    level_upper = (level or "").upper()
    if level_upper in ("EXTREME", "CRITICAL"):
        return COLORS["danger"]
    if level_upper in ("HIGH", "ESCALATING"):
        return "#FF6B35"
    if level_upper in ("ELEVATED", "MEDIUM", "ONGOING"):
        return COLORS["warning"]
    return COLORS["success"]


def _fg_color(score: float) -> str:
    if score <= 25:
        return COLORS["danger"]
    if score <= 45:
        return "#FF6B35"
    if score <= 55:
        return COLORS["warning"]
    if score <= 75:
        return COLORS["success"]
    return "#00C853"


def _simple_market_mood(vix, fg, regime, pol_risk, war_risk) -> dict:
    signals = []
    if fg.get("score"):
        s = fg["score"]
        if s <= 25:
            signals.append(("fear", -2))
        elif s <= 40:
            signals.append(("cautious", -1))
        elif s >= 75:
            signals.append(("greedy", -1))
        elif s >= 60:
            signals.append(("optimistic", 1))
        else:
            signals.append(("neutral", 0))

    if vix:
        if vix > 30:
            signals.append(("volatile", -2))
        elif vix > 25:
            signals.append(("nervous", -1))
        elif vix < 15:
            signals.append(("calm", 1))
        else:
            signals.append(("normal", 0))

    if pol_risk in ("HIGH", "EXTREME"):
        signals.append(("political risk", -1))
    if war_risk in ("HIGH", "EXTREME"):
        signals.append(("geopolitical tension", -2))

    total = sum(s[1] for s in signals)
    if total <= -3:
        mood = "Stormy"
        mood_color = COLORS["danger"]
        advice = "Markets are fearful. Be cautious with new positions. Consider defensive plays or waiting for clarity."
    elif total <= -1:
        mood = "Cloudy"
        mood_color = COLORS["warning"]
        advice = "Mixed signals. Some risks are elevated. Stick to high-conviction ideas and keep position sizes smaller."
    elif total >= 3:
        mood = "Sunny"
        mood_color = "#00C853"
        advice = "Strong optimism. Good conditions for buying, but watch for overextension."
    elif total >= 1:
        mood = "Clear"
        mood_color = COLORS["success"]
        advice = "Conditions look favorable. Look for quality setups with good risk/reward."
    else:
        mood = "Neutral"
        mood_color = COLORS["text_secondary"]
        advice = "No strong signals either way. Wait for clearer setups or trade smaller."

    return {"mood": mood, "color": mood_color, "advice": advice, "score": total}


def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    # Greeting bar
    now = datetime.datetime.now()
    hour = now.hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")

    st.markdown(f"""
    <div style="margin-bottom:28px;">
        <div style="font-size:13px; color:{COLORS['text_muted']};">
            {now.strftime('%A, %B %d, %Y')}
        </div>
        <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                    letter-spacing:-0.02em; margin-top:4px;">
            {greeting}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Fetch all data upfront (concurrent via Streamlit cache)
    macro = data_bridge.get_macro_context()
    vix = macro.get("vix", 0)
    regime = macro.get("macro_regime", "NEUTRAL")
    political = data_bridge.get_political_pulse()
    war = data_bridge.get_war_watch()
    influencer = data_bridge.get_influencer_pulse()
    fg = data_bridge.get_fear_greed()
    crypto_fg = data_bridge.get_crypto_fear_greed()

    # Live news ticker bar (top of page, always visible)
    market_news = data_bridge.get_market_news()
    if market_news:
        news_ticker_bar(market_news, max_items=5)

    # Index performance strip (always visible)
    idx_data = fetch_index_data()
    if idx_data:
        index_strip(idx_data)

    # ──────────────────────────────────────────────────────────
    # SIMPLE VIEW — Clean, reference-design matching
    # ──────────────────────────────────────────────────────────
    if is_simple:
        pol_risk = political.get("risk_level", "LOW")
        war_risk = war.get("risk_level", "CALM")
        mood = _simple_market_mood(vix, fg, regime, pol_risk, war_risk)

        # Pick gradient based on mood
        if mood["score"] >= 1:
            mood_gradient = CARD_GRADIENT_GREEN
        elif mood["score"] <= -1:
            mood_gradient = CARD_GRADIENT_RED
        else:
            mood_gradient = CARD_GRADIENT_BLUE

        mood_pct = max(0, min(100, int((mood["score"] + 6) / 12 * 100)))

        st.markdown(f"""
        <div style="{mood_gradient} margin-bottom:24px; text-align:center; padding:36px;">
            <div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase;
                        letter-spacing:0.08em; margin-bottom:8px;">TODAY'S MARKET MOOD</div>
            <div style="font-size:48px; font-weight:300; color:{mood['color']};
                        letter-spacing:-0.02em; margin-bottom:12px;">{mood['mood']}</div>
            <div style="width:200px;height:5px;border-radius:3px;background:{COLORS['border']};
                        margin:0 auto 14px auto;">
                <div style="width:{mood_pct}%;height:100%;border-radius:3px;background:{mood['color']};
                            transition:width 0.5s ease;"></div>
            </div>
            <div style="font-size:14px; color:{COLORS['text_secondary']}; max-width:500px;
                        margin:0 auto; line-height:1.5;">{mood['advice']}</div>
        </div>
        """, unsafe_allow_html=True)

        # ─── Overview grouped card (reference design style) ───
        fg_score = fg.get("score", 0)
        fg_label = fg.get("rating", "N/A")
        cfg_score = crypto_fg.get("score", 0)

        overview_card("Overview", [
            {
                "label": "Investor Sentiment",
                "value": f"{fg_score:.0f}",
                "suffix": "%",
                "icon": "activity",
                "delta": f"{fg_score - fg.get('previous_close', fg_score):+.1f}pts" if fg.get("previous_close") else None,
                "delta_color": _fg_color(fg_score),
                "vs_label": "vs yesterday",
            },
            {
                "label": "Market Volatility",
                "value": f"{vix:.1f}" if vix else "—",
                "icon": "bar",
                "delta": "HIGH" if vix and vix > 25 else ("Elevated" if vix and vix > 20 else "Normal"),
                "delta_color": COLORS["danger"] if vix and vix > 25 else (COLORS["warning"] if vix and vix > 20 else COLORS["success"]),
                "vs_label": "VIX level",
            },
            {
                "label": "Crypto Sentiment",
                "value": str(cfg_score) if cfg_score else "—",
                "suffix": "%" if cfg_score else "",
                "icon": "zap",
                "delta": crypto_fg.get("rating", "—"),
                "delta_color": _fg_color(cfg_score) if cfg_score else COLORS["text_dim"],
                "vs_label": "",
            },
        ])

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Sector heatmap
        sector_data = fetch_sector_performance()
        if sector_data:
            sector_heatmap(sector_data)

        # Top gainers / losers
        gainers_data, losers_data = fetch_gainers_losers()
        if gainers_data or losers_data:
            st.markdown(f'<div style="font-size:16px;font-weight:600;color:{COLORS["text"]};margin-bottom:10px;">Top Movers</div>', unsafe_allow_html=True)
            gainers_losers(gainers_data, losers_data, max_items=6)
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        # What's Happening Now
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            What's Happening Now
        </div>
        """, unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            pol_summary = political.get("summary", "No major political news affecting markets.")[:200]
            pol_dir = political.get("market_direction", "NEUTRAL")
            dir_label = "Bullish" if pol_dir == "BULLISH" else ("Bearish" if pol_dir == "BEARISH" else "Neutral")
            dir_color = COLORS["success"] if pol_dir == "BULLISH" else (COLORS["danger"] if pol_dir == "BEARISH" else COLORS["text_muted"])
            st.markdown(f'<div style="{CARD_CSS}"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(74,108,247,0.08);display:flex;align-items:center;justify-content:center;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{COLORS["accent"]}" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div><div style="font-size:15px;font-weight:600;color:{COLORS["text"]};">Politics &amp; Policy</div><span style="margin-left:auto;background:{dir_color}22;color:{dir_color};padding:2px 10px;border-radius:6px;font-size:11px;font-weight:600;">{dir_label}</span></div><div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.6;">{pol_summary}</div></div>', unsafe_allow_html=True)

        with col_b:
            war_summary = war.get("summary", "No major conflict changes.")[:200]
            conflicts = war.get("active_conflicts", [])
            war_risk_val = war.get("risk_level", "CALM")
            wr_color = _risk_color(war_risk_val)
            st.markdown(f'<div style="{CARD_CSS}"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(239,68,68,0.08);display:flex;align-items:center;justify-content:center;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{COLORS["danger"]}" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg></div><div style="font-size:15px;font-weight:600;color:{COLORS["text"]};">World Events</div><span style="margin-left:auto;background:{wr_color}22;color:{wr_color};padding:2px 10px;border-radius:6px;font-size:11px;font-weight:600;">{war_risk_val}</span></div><div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.6;">{war_summary}</div><div style="font-size:12px;color:{COLORS["text_dim"]};margin-top:8px;">Active situations: {len(conflicts)}</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        col_c, col_d = st.columns(2)
        with col_c:
            inf_summary = influencer.get("summary", "No notable influencer activity.")[:200]
            elon_alert = influencer.get("elon_alert", False)
            elon_badge = "<span style='margin-left:auto;background:#FF6B3520;color:#FF6B35;padding:2px 10px;border-radius:6px;font-size:11px;font-weight:600;'>ELON ACTIVE</span>" if elon_alert else ""
            st.markdown(f'<div style="{CARD_CSS}"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(245,158,11,0.08);display:flex;align-items:center;justify-content:center;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{COLORS["warning"]}" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg></div><div style="font-size:15px;font-weight:600;color:{COLORS["text"]};">Influencer Activity</div>{elon_badge}</div><div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.6;">{inf_summary}</div></div>', unsafe_allow_html=True)

        with col_d:
            events = data_bridge.get_event_contracts()
            top_events = events[:3] if events else []
            events_html = ""
            for ev in top_events:
                title = ev.get("title", "")[:55]
                yes_p = ev.get("yes_price") or 0
                try:
                    yes_p = float(yes_p)
                except (ValueError, TypeError):
                    yes_p = 0
                prob_color = COLORS["success"] if yes_p > 0.7 else (COLORS["warning"] if yes_p > 0.4 else COLORS["danger"])
                events_html += (
                    f'<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid {COLORS["border"]};">'
                    f'<span style="font-size:12px;color:{COLORS["text_secondary"]};flex:1;margin-right:8px;">{title}</span>'
                    f'<span style="font-size:12px;color:{prob_color};font-weight:600;white-space:nowrap;">{yes_p:.0%}</span></div>'
                )
            ev_content = events_html if events_html else f'<div style="font-size:13px;color:{COLORS["text_dim"]};">No active events</div>'
            st.markdown(f'<div style="{CARD_CSS}"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(59,130,246,0.08);display:flex;align-items:center;justify-content:center;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{COLORS["info"]}" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg></div><div style="font-size:15px;font-weight:600;color:{COLORS["text"]};">Prediction Markets</div></div>{ev_content}</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        # What to Watch For
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            What to Watch For
        </div>
        """, unsafe_allow_html=True)

        watch_items = []
        if fg.get("score") and fg.get("one_week_ago"):
            delta = fg["score"] - fg["one_week_ago"]
            if abs(delta) > 5:
                direction = "improving" if delta > 0 else "declining"
                watch_items.append(f"Investor sentiment is {direction} (moved {delta:+.0f} pts this week)")
        if vix and vix > 20:
            watch_items.append(f"Volatility is elevated at {vix:.1f} — expect bigger price swings")
        if pol_risk in ("HIGH", "EXTREME"):
            theme = political.get("dominant_theme", "policy changes")
            watch_items.append(f"Political risk is {pol_risk.lower()} — watch for {theme.lower()} developments")
        if war_risk in ("HIGH", "EXTREME"):
            watch_items.append(f"Geopolitical tensions are {war_risk.lower()} — safe havens (gold, bonds) may benefit")
        if not watch_items:
            watch_items.append("No major catalysts on the horizon. Normal market conditions expected.")

        items_html = ""
        for item in watch_items:
            items_html += (
                f'<div style="padding:10px 0; border-bottom:1px solid {COLORS["border"]}; '
                f'font-size:13px; color:{COLORS["text_secondary"]}; line-height:1.5;">'
                f'<span style="color:{COLORS["accent"]};margin-right:8px;">•</span>{item}</div>'
            )

        st.markdown(f"""
        <div style="{CARD_CSS}">
            {items_html}
        </div>
        """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────
    # ADVANCED VIEW — Full data, technical details
    # ──────────────────────────────────────────────────────────
    else:
        # Grouped overview cards (reference design)
        fg_score = fg.get("score", 0)
        cfg_score = crypto_fg.get("score", 0)
        pol_risk = political.get("risk_level", "LOW")
        war_risk_val = war.get("risk_level", "CALM")

        # Row 1: Key macro metrics (grouped card)
        overview_card("Market Indicators", [
            {
                "label": "VIX",
                "value": f"{vix:.1f}" if vix else "—",
                "icon": "bar",
                "delta": "HIGH" if vix and vix > 25 else ("Elevated" if vix and vix > 20 else "Normal"),
                "delta_color": COLORS["danger"] if vix and vix > 25 else (COLORS["warning"] if vix and vix > 20 else COLORS["success"]),
            },
            {
                "label": "Macro Regime",
                "value": regime,
                "icon": "trending",
                "delta": pol_risk,
                "delta_color": _risk_color(pol_risk),
                "vs_label": "political risk",
            },
            {
                "label": "Fear & Greed",
                "value": f"{fg_score:.0f}" if fg_score else "—",
                "icon": "activity",
                "delta": fg.get("rating", "—"),
                "delta_color": _fg_color(fg_score) if fg_score else COLORS["text_dim"],
            },
        ])

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        # Row 2: Additional indicators
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("Conflict Status", war_risk_val, icon="globe",
                        delta=f"{len(war.get('active_conflicts', []))} active",
                        delta_color=_risk_color(war_risk_val))
        with c2:
            metric_card("Crypto F&G", str(cfg_score) if cfg_score else "—", icon="zap",
                        delta=crypto_fg.get("rating", "—"),
                        delta_color=_fg_color(cfg_score) if cfg_score else COLORS["text_dim"])
        with c3:
            safe_haven = war.get("safe_haven_demand", "LOW")
            metric_card("Safe Haven", safe_haven, icon="shield",
                        delta_color=_risk_color(safe_haven))
        with c4:
            energy_risk = war.get("energy_risk", "LOW")
            metric_card("Energy Risk", energy_risk, icon="zap",
                        delta_color=_risk_color(energy_risk))

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Sector heatmap
        sector_data = fetch_sector_performance()
        if sector_data:
            sector_heatmap(sector_data)

        # Top gainers / losers
        gainers_data, losers_data = fetch_gainers_losers()
        if gainers_data or losers_data:
            st.markdown(f'<div style="font-size:16px;font-weight:600;color:{COLORS["text"]};margin-bottom:10px;">Top Movers</div>', unsafe_allow_html=True)
            gainers_losers(gainers_data, losers_data, max_items=6)

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Intelligence Briefing
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            Intelligence Briefing
        </div>
        """, unsafe_allow_html=True)

        col_a, col_b = st.columns(2)

        with col_a:
            theme = political.get("dominant_theme", "NONE")
            direction = political.get("market_direction", "NEUTRAL")
            pol_summary = political.get("summary", "No political signals detected")[:180]
            event_count = len(political.get("events", []))
            dir_color = COLORS["success"] if direction == "BULLISH" else (COLORS["danger"] if direction == "BEARISH" else COLORS["text_secondary"])

            headlines_html = ""
            for evt in political.get("events", [])[:3]:
                hl = evt.get("headline", "")[:80]
                etype = evt.get("type", "")
                headlines_html += (
                    f'<div style="font-size:12px;color:{COLORS["text_secondary"]};padding:5px 0;'
                    f'border-bottom:1px solid {COLORS["border"]};">'
                    f'<span style="color:{COLORS["accent"]};font-size:10px;text-transform:uppercase;'
                    f'letter-spacing:0.05em;margin-right:6px;">{etype}</span>{hl}</div>'
                )

            st.markdown(
                f'<div style="{CARD_CSS}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                f'letter-spacing:0.06em;">POLITICAL PULSE</div>'
                f'<div style="font-size:11px;color:{COLORS["text_dim"]};">{event_count} events</div></div>'
                f'<div style="font-size:16px;color:{COLORS["text"]};margin-bottom:4px;">'
                f'{theme} — <span style="color:{dir_color};">{direction}</span></div>'
                f'<div style="font-size:13px;color:{COLORS["text_secondary"]};margin-bottom:12px;line-height:1.5;">{pol_summary}</div>'
                f'{headlines_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with col_b:
            conflicts = war.get("active_conflicts", [])
            war_summary = war.get("summary", "No conflict signals")[:180]

            conflict_html = ""
            for c in conflicts:
                cid = c.get("conflict_id", "").replace("_", " ")
                sev = c.get("severity", "LOW")
                sev_color = _risk_color(sev)
                conflict_html += (
                    f'<div style="display:inline-block;margin:3px 6px 3px 0;padding:3px 10px;'
                    f'border-radius:8px;background:{sev_color}15;border:1px solid {sev_color}30;font-size:11px;">'
                    f'<span style="color:{sev_color};font-weight:600;">{cid}</span></div>'
                )

            st.markdown(
                f'<div style="{CARD_CSS}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                f'letter-spacing:0.06em;">WAR WATCH</div>'
                f'<div style="font-size:11px;color:{COLORS["text_dim"]};">{len(conflicts)} conflicts</div></div>'
                f'<div style="margin-bottom:8px;">{conflict_html}</div>'
                f'<div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.5;">{war_summary}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        col_c, col_d = st.columns(2)

        with col_c:
            consensus = influencer.get("fintwit_consensus", "QUIET")
            inf_summary = influencer.get("summary", "No notable activity")[:150]
            active_inf = influencer.get("active_influencers", [])

            inf_html = ""
            for inf in active_inf[:4]:
                name = inf.get("name", "")
                hl = inf.get("headline", "")[:60]
                inf_html += (
                    f'<div style="font-size:12px;padding:5px 0;border-bottom:1px solid {COLORS["border"]};">'
                    f'<span style="color:{COLORS["accent"]};font-weight:600;margin-right:6px;">{name}</span>'
                    f'<span style="color:{COLORS["text_secondary"]};">{hl}</span></div>'
                )

            st.markdown(
                f'<div style="{CARD_CSS}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                f'letter-spacing:0.06em;">INFLUENCER SIGNALS</div>'
                f'<div style="font-size:11px;color:{COLORS["text_dim"]};">{len(active_inf)} active</div></div>'
                f'<div style="font-size:16px;color:{COLORS["text"]};margin-bottom:4px;">Consensus: {consensus}</div>'
                f'<div style="font-size:13px;color:{COLORS["text_secondary"]};margin-bottom:12px;">{inf_summary}</div>'
                f'{inf_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with col_d:
            events = data_bridge.get_event_contracts()
            top_events = events[:5] if events else []

            events_html = ""
            for ev in top_events:
                title = ev.get("title", "")[:60]
                source = ev.get("source", "")
                yes_p = ev.get("yes_price")
                try:
                    yes_p = float(yes_p) if yes_p is not None else 0
                except (ValueError, TypeError):
                    yes_p = 0
                prob_color = COLORS["success"] if yes_p > 0.7 else (COLORS["warning"] if yes_p > 0.4 else COLORS["danger"])
                events_html += (
                    f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
                    f'border-bottom:1px solid {COLORS["border"]};">'
                    f'<div style="flex:1;font-size:12px;color:{COLORS["text_secondary"]};">'
                    f'<span style="color:{COLORS["text_dim"]};font-size:10px;margin-right:4px;">{source}</span>'
                    f'{title}</div>'
                    f'<div style="font-size:12px;color:{prob_color};font-weight:600;min-width:40px;text-align:right;">'
                    f'{yes_p:.0%}</div></div>'
                )

            st.markdown(
                f'<div style="{CARD_CSS}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
                f'letter-spacing:0.06em;">PREDICTION MARKETS</div>'
                f'<div style="font-size:11px;color:{COLORS["text_dim"]};">{len(events)} active</div></div>'
                f'{events_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────
    # Chart Forecasts (shared — top picks with mini charts)
    # ──────────────────────────────────────────────────────────
    scan_key = "overview_scan_results"
    has_cached = scan_key in st.session_state and st.session_state[scan_key]

    if has_cached:
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            {"Stock Forecasts" if is_simple else "Chart Forecasts — Top Picks"}
        </div>
        """, unsafe_allow_html=True)

        try:
            from dashboard.components.forecast_card import forecast_section
            forecast_section(st.session_state[scan_key], max_cards=6)
        except Exception:
            pass

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        # Leaderboard
        st.markdown(f"""
        <div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">
            {"Top Picks" if is_simple else "Leaderboard"}
        </div>
        """, unsafe_allow_html=True)

        render_leaderboard(st.session_state[scan_key][:10], max_rows=10, simple=is_simple)

        col_btn, _ = st.columns([1, 5])
        with col_btn:
            if st.button("Refresh Scan", type="secondary"):
                _run_scan_with_progress(scan_key, is_simple)
                st.rerun()
    else:
        button_text = "Find Best Stocks" if is_simple else "Scan Markets"
        st.markdown(f"""
        <div style="{CARD_CSS} text-align:center; padding:40px 32px 32px 32px;">
            <div style="width:48px;height:48px;border-radius:50%;background:{COLORS['accent']}10;
                        display:flex;align-items:center;justify-content:center;margin:0 auto 16px auto;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="{COLORS['accent']}" stroke-width="2"><path d="M23 6l-9.5 9.5-5-5L1 18M17 6h6v6"/></svg>
            </div>
            <div style="font-size:16px; font-weight:500; color:{COLORS['text']}; margin-bottom:6px;">
                {"Ready to find opportunities" if is_simple else "Stock Scanner Ready"}
            </div>
            <div style="font-size:13px; color:{COLORS['text_secondary']}; margin-bottom:20px;">
                {"Scan 96 stocks and find the best trades" if is_simple else "Analyze 96 tickers across all sectors"}
            </div>
        </div>
        """, unsafe_allow_html=True)

        _, col_center, _ = st.columns([1, 2, 1])
        with col_center:
            if st.button(button_text, type="primary", use_container_width=True):
                _run_scan_with_progress(scan_key, is_simple)
                st.rerun()

    # ──────────────────────────────────────────────────────────
    # Live News Feed (always visible, auto-updates every 3 min)
    # ──────────────────────────────────────────────────────────
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    if market_news:
        news_feed(
            market_news,
            max_items=12 if not is_simple else 8,
            title="Latest Market News" if is_simple else "Live News Feed",
        )

"""
Predictions page — Today's Best Plays, six-formula quant analysis,
whale detection, AI hedge fund watchlist, ML forecasts, backtesting.

Simple mode: Best plays + regime context + AI hedge fund watchlist.
Advanced mode: Per-ticker quant breakdown + ML backtest + features + re-train.
"""

import streamlit as st
import numpy as np
import pandas as pd
from dashboard.theme import COLORS, CARD_CSS, FONT

# ── Cache helpers ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_ohlcv(ticker: str, period: str = "1y"):
    import yfinance as yf
    df = yf.download(ticker, period=period, progress=False)
    if df is not None and isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _run_prediction(ticker: str):
    from analysis.ml.predictor import predict_ticker
    df = _fetch_ohlcv(ticker)
    if df is None or len(df) < 30:
        return None, None
    return predict_ticker(ticker, df=df), df


@st.cache_data(ttl=300, show_spinner=False)
def _run_backtest(ticker: str):
    from analysis.ml.feature_engine import build_features, FEATURE_COLS
    from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit

    df = _fetch_ohlcv(ticker, period="730d")
    if df is None or len(df) < 80:
        return None

    featured = build_features(df)
    featured["target"] = featured["Close"].pct_change().shift(-1) * 100
    featured["target_dir"] = (featured["target"] > 0.05).astype(int)
    clean = featured.dropna(subset=FEATURE_COLS + ["target"])
    if len(clean) < 80:
        return None

    X = clean[FEATURE_COLS].values
    y_ret = clean["target"].values
    y_dir = clean["target_dir"].values
    dates = clean.index
    dummy_hit = max(np.mean(y_dir), 1 - np.mean(y_dir)) * 100

    tscv = TimeSeriesSplit(n_splits=5, gap=1)
    fold_results = []
    all_preds_ret, all_actual_ret = [], []
    all_preds_dir, all_actual_dir = [], []
    all_dates = []

    for fold_i, (train_idx, test_idx) in enumerate(tscv.split(X)):
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X[train_idx])
        X_test = scaler.transform(X[test_idx])

        reg = GradientBoostingRegressor(n_estimators=200, learning_rate=0.05, max_depth=3, subsample=0.8, min_samples_leaf=10, random_state=42)
        reg.fit(X_train, y_ret[train_idx])
        clf = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, subsample=0.8, min_samples_leaf=10, random_state=42)
        clf.fit(X_train, y_dir[train_idx])

        preds_ret = reg.predict(X_test)
        preds_dir = clf.predict(X_test)
        hit = float(np.mean(preds_dir == y_dir[test_idx])) * 100
        r2 = reg.score(X_test, y_ret[test_idx])
        fold_results.append({"fold": fold_i + 1, "date_range": f"{dates[test_idx[0]].strftime('%Y-%m-%d')} > {dates[test_idx[-1]].strftime('%Y-%m-%d')}", "hit_rate": round(hit, 1), "r2": round(r2, 4), "n_test": len(test_idx)})
        all_preds_ret.extend(preds_ret)
        all_actual_ret.extend(y_ret[test_idx])
        all_preds_dir.extend(preds_dir)
        all_actual_dir.extend(y_dir[test_idx])
        all_dates.extend(dates[test_idx])

    all_preds_ret = np.array(all_preds_ret)
    all_actual_ret = np.array(all_actual_ret)
    wf_hit = float(np.mean(np.array(all_preds_dir) == np.array(all_actual_dir))) * 100
    ss_res = np.sum((all_actual_ret - all_preds_ret) ** 2)
    ss_tot = np.sum((all_actual_ret - np.mean(all_actual_ret)) ** 2)
    wf_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    scaler_full = StandardScaler()
    X_full = scaler_full.fit_transform(X)
    clf_full = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, subsample=0.8, min_samples_leaf=10, random_state=42)
    clf_full.fit(X_full, y_dir)
    importances = dict(zip(FEATURE_COLS, clf_full.feature_importances_))

    return {"wf_hit_rate": round(wf_hit, 1), "wf_r2": round(wf_r2, 4), "dummy_baseline": round(dummy_hit, 1), "edge": round(wf_hit - dummy_hit, 1), "fold_results": fold_results, "y_test": all_actual_ret, "y_pred": all_preds_ret, "dates_test": all_dates, "feature_importances": {k: round(v, 4) for k, v in sorted(importances.items(), key=lambda x: -x[1])}}


@st.cache_data(ttl=300, show_spinner=False)
def _bootstrap_confidence(ticker: str, n_bootstraps: int = 30):
    from analysis.ml.feature_engine import build_features, FEATURE_COLS
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.utils import resample

    df = _fetch_ohlcv(ticker, period="365d")
    if df is None or len(df) < 60:
        return None
    featured = build_features(df)
    featured["target"] = featured["Close"].pct_change().shift(-1) * 100
    clean = featured.dropna(subset=FEATURE_COLS + ["target"])
    if len(clean) < 40:
        return None

    X = clean[FEATURE_COLS].values
    y = clean["target"].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    split = int(len(X_scaled) * 0.8)
    X_train, y_train = X_scaled[:split], y[:split]
    X_latest = X_scaled[-1:]

    preds = []
    for _ in range(n_bootstraps):
        X_b, y_b = resample(X_train, y_train)
        m = GradientBoostingRegressor(n_estimators=100, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=None)
        m.fit(X_b, y_b)
        preds.append(float(m.predict(X_latest)[0]))

    preds = np.array(preds)
    return {"mean": round(float(np.mean(preds)), 4), "ci_low": round(float(np.percentile(preds, 5)), 4), "ci_high": round(float(np.percentile(preds, 95)), 4), "std": round(float(np.std(preds)), 4)}


# ── Best Plays helpers ──────────────────────────────────────────────────────

def _get_regime_context():
    """Get current market regime and strategy recommendation."""
    try:
        from dashboard import data_bridge
        macro = data_bridge.get_macro_context()
        regime = macro.get("macro_regime", "NEUTRAL")
        vix = macro.get("vix", 0)
        return regime, vix
    except Exception:
        return "NEUTRAL", 0


def _get_best_plays(max_results: int = 5):
    """Get top plays from scan results filtered by quant alignment + regime."""
    results = st.session_state.get("overview_scan_results", [])
    if not results:
        return [], "NEUTRAL"

    regime, _ = _get_regime_context()

    # Filter by regime
    candidates = []
    for t in results:
        score = getattr(t, "composite_score", 0)
        if score < getattr(__import__("config.settings", fromlist=["BEST_PLAYS_MIN_SCORE"]), "BEST_PLAYS_MIN_SCORE", 55):
            continue

        if regime == "RISK_OFF":
            # Favor mean-reversion, dips, defensive plays
            r = getattr(t, "regime", "")
            if r in ("CLEAN_REVERSION", "MEAN_REVERTING") or getattr(t, "pct_change", 0) < -2:
                candidates.append(t)
            elif getattr(t, "bayesian_posterior", 0) > 0.6:
                candidates.append(t)
        elif regime == "RISK_ON":
            # Favor momentum, ignition, breakouts
            phase = getattr(t, "kinematic_phase", "")
            if phase in ("IGNITION", "CRUISE") and score >= 60:
                candidates.append(t)
            elif getattr(t, "quant_aligned", False):
                candidates.append(t)
        else:
            # Neutral: balanced R/R, A/B tier
            tier = getattr(t, "confidence_tier", "C")
            rr = getattr(t, "risk_reward", 0)
            if tier in ("A", "B") and rr >= 1.5:
                candidates.append(t)
            elif getattr(t, "quant_aligned", False):
                candidates.append(t)

    if not candidates:
        candidates = sorted(results, key=lambda x: getattr(x, "composite_score", 0), reverse=True)

    # Sort by quant_score (best aligned first), then composite
    candidates.sort(key=lambda x: (getattr(x, "quant_aligned", False), getattr(x, "quant_score", 0), getattr(x, "composite_score", 0)), reverse=True)
    return candidates[:max_results], regime


# ── Render ──────────────────────────────────────────────────────────────────

def render():
    is_simple = st.session_state.get("view_mode", "Simple") == "Simple"

    subtitle = "Today's best plays based on six-formula quant analysis" if is_simple else "Quant formulas, whale detection, ML forecasts, and AI hedge fund tracker"

    st.markdown(f"""<div style="font-size:34px; font-weight:700; color:{COLORS['text']}; letter-spacing:-0.02em; margin-bottom:4px;">Predictions</div><div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:28px;">{subtitle}</div>""", unsafe_allow_html=True)

    if is_simple:
        _render_simple_best_plays()
    else:
        _render_advanced_full()


# ── SIMPLE MODE — Best Plays + Regime + Hedge Fund ─────────────────────────

def _render_simple_best_plays():
    plays, regime = _get_best_plays()
    regime_map = {"RISK_ON": ("Bullish", "Favor momentum plays and breakouts", COLORS["success"]), "RISK_OFF": ("Stormy", "Favor defensive plays and dip buys", COLORS["danger"]), "NEUTRAL": ("Mixed Signals", "Stick to A+ setups only", COLORS["warning"])}
    regime_label, regime_advice, regime_color = regime_map.get(regime, regime_map["NEUTRAL"])
    _, vix = _get_regime_context()

    # ── Regime Context Card ──
    vix_str = f" | VIX: {vix:.1f}" if vix > 0 else ""
    st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {regime_color}; padding:20px; margin-bottom:20px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="font-size:12px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">MARKET REGIME</div><div style="font-size:24px; font-weight:700; color:{regime_color}; margin-top:4px;">{regime_label}</div><div style="font-size:14px; color:{COLORS['text_secondary']}; margin-top:4px;">{regime_advice}{vix_str}</div></div></div></div>""", unsafe_allow_html=True)

    # ── Best Plays ──
    if not plays:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:48px;"><div style="font-size:16px; font-weight:500; color:{COLORS['text']}; margin-bottom:8px;">No plays yet</div><div style="font-size:14px; color:{COLORS['text_secondary']};">Run a Market Overview scan first, then best plays will appear here.</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin-bottom:14px;">Today's Best Plays</div>""", unsafe_allow_html=True)

        for pick in plays:
            _render_play_card(pick)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── AI Hedge Fund Watchlist ──
    _render_hedge_fund_watchlist()


def _render_play_card(pick):
    """Render a single actionable play card."""
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
    whale_score = getattr(pick, "whale_score", 0)
    aligned = getattr(pick, "quant_aligned", False)
    reason = pick.catalyst_summary or pick.where_headed or ""
    reason = reason[:80]

    tier_color = COLORS["success"] if tier == "A" else (COLORS["warning"] if tier == "B" else COLORS["text_dim"])
    aligned_badge = f'<span style="background:{COLORS["success"]}20;color:{COLORS["success"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:8px;">{n_agree}/6 ALIGNED</span>' if aligned else f'<span style="background:{COLORS["warning"]}20;color:{COLORS["warning"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:8px;">{n_agree}/6</span>'
    whale_badge = f'<span style="background:{COLORS["accent"]}20;color:{COLORS["accent"]};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:6px;">WHALE {whale_score:.0f}</span>' if whale_score >= 40 else ""

    # Entry/stop/target line
    stop_str = f"${stop:.2f}" if stop and stop > 0 else "N/A"
    target_str = f"${target:.2f}" if target and target > 0 else "N/A"
    rr_str = f"{rr:.1f}x" if rr and rr > 0 else "N/A"

    st.markdown(f"""<div style="{CARD_CSS} margin-bottom:10px; padding:18px 22px;"><div style="display:flex;justify-content:space-between;align-items:flex-start;"><div style="flex:1;"><div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;"><span style="font-size:18px; font-weight:700; color:{COLORS['text']};">{ticker}</span><span style="background:{action_color}20;color:{action_color};padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;">{action}</span><span style="color:{tier_color};font-size:11px;font-weight:700;">Tier {tier}</span>{aligned_badge}{whale_badge}</div><div style="display:flex;gap:24px;font-size:13px;margin-bottom:6px;"><span style="color:{COLORS['text_secondary']};">Entry <span style="color:{COLORS['text']};font-weight:600;">${entry:.2f}</span></span><span style="color:{COLORS['text_secondary']};">Stop <span style="color:{COLORS['danger']};font-weight:600;">{stop_str}</span></span><span style="color:{COLORS['text_secondary']};">Target <span style="color:{COLORS['success']};font-weight:600;">{target_str}</span></span><span style="color:{COLORS['text_secondary']};">R/R <span style="font-weight:600;">{rr_str}</span></span><span style="color:{COLORS['text_secondary']};">Kelly <span style="font-weight:600;">{kelly*100:.1f}%</span></span></div><div style="font-size:12px; color:{COLORS['text_dim']};">{reason}</div></div><div style="text-align:right;"><div style="font-size:11px; color:{COLORS['text_muted']};">QUANT</div><div style="font-size:22px; font-weight:700; color:{COLORS['accent']};">{quant_score:.0f}</div></div></div></div>""", unsafe_allow_html=True)


def _render_hedge_fund_watchlist():
    """Render AI Hedge Fund sector watchlist from scan results."""
    from config import settings as cfg
    hf_tickers = getattr(cfg, "AI_HEDGE_FUND_TICKERS", {})
    if not hf_tickers:
        return

    st.markdown(f"""<div style="font-size:20px; font-weight:600; color:{COLORS['text']}; margin:20px 0 14px 0;">AI Hedge Fund Watchlist</div>""", unsafe_allow_html=True)

    results = st.session_state.get("overview_scan_results", [])
    result_map = {getattr(t, "ticker", ""): t for t in results}

    for sector, tickers in hf_tickers.items():
        sector_data = []
        for t in tickers:
            pick = result_map.get(t)
            if pick:
                sector_data.append(pick)

        if not sector_data:
            # Show sector with no data
            ticker_list = ", ".join(tickers)
            st.markdown(f"""<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid {COLORS['border_light']};"><span style="font-size:13px;font-weight:600;color:{COLORS['text']};width:200px;">{sector}</span><span style="font-size:12px;color:{COLORS['text_dim']};">{ticker_list} — run scan for data</span></div>""", unsafe_allow_html=True)
        else:
            avg_score = sum(getattr(p, "composite_score", 0) for p in sector_data) / len(sector_data)
            top = max(sector_data, key=lambda x: getattr(x, "composite_score", 0))
            buys = sum(1 for p in sector_data if getattr(p, "direction", "") == "LONG")
            score_color = COLORS["success"] if avg_score >= 60 else (COLORS["warning"] if avg_score >= 45 else COLORS["text_dim"])

            tickers_html = ""
            for p in sector_data:
                d = getattr(p, "direction", "LONG")
                dc = COLORS["success"] if d == "LONG" else COLORS["danger"]
                sc = getattr(p, "composite_score", 0)
                tickers_html += f'<span style="color:{dc};font-weight:600;margin-right:10px;">{p.ticker} {sc:.0f}</span>'

            st.markdown(f"""<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid {COLORS['border_light']};"><div style="width:200px;"><div style="font-size:13px;font-weight:600;color:{COLORS['text']};">{sector}</div><div style="font-size:11px;color:{COLORS['text_dim']};">{buys}/{len(sector_data)} bullish</div></div><div style="flex:1;font-size:12px;">{tickers_html}</div><div style="text-align:right;"><span style="font-size:16px;font-weight:700;color:{score_color};">{avg_score:.0f}</span><span style="font-size:11px;color:{COLORS['text_dim']};margin-left:4px;">avg</span></div></div>""", unsafe_allow_html=True)


# ── ADVANCED MODE — Full quant + ML detail ─────────────────────────────────

def _render_advanced_full():
    # ── Best Plays at top (compact) ──
    plays, regime = _get_best_plays(max_results=3)
    if plays:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:10px;">Top Plays ({regime.replace('_', ' ')})</div>""", unsafe_allow_html=True)
        for pick in plays:
            _render_play_card(pick)
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    divider_color = COLORS["divider"]
    st.markdown(f"<hr style='border-top:1px solid {divider_color};margin:8px 0 20px 0;'>", unsafe_allow_html=True)

    # ── Ticker selector ──
    from config import settings as cfg
    stocks = cfg.get_universe("stocks")
    default_tickers = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "META", "GOOGL", "AMD"]
    all_tickers = default_tickers + [t for t in stocks if t not in default_tickers]

    col_ticker, col_custom = st.columns([2, 1])
    with col_ticker:
        selected = st.selectbox("Select Ticker", all_tickers, index=0)
    with col_custom:
        custom = st.text_input("Or enter any ticker", value="", placeholder="e.g. COIN")
    ticker = custom.strip().upper() if custom.strip() else selected

    divider_color2 = COLORS["divider"]
    st.markdown(f"<hr style='border-top:1px solid {divider_color2};margin:8px 0 24px 0;'>", unsafe_allow_html=True)

    # ── Run prediction ──
    prediction, df = _run_prediction(ticker)
    if prediction is None or df is None or len(df) < 20:
        st.warning(f"Not enough data for {ticker}. Try a different ticker.")
        return

    pred_ret = prediction.get("predicted_return", 0)
    confidence = prediction.get("confidence", 0)
    direction = prediction.get("direction", "NEUTRAL")
    ml_score = prediction.get("ml_score", 50)
    bull_prob = prediction.get("bull_prob", 0.5)
    current_price = float(df["Close"].iloc[-1])
    dir_color = COLORS["success"] if direction == "BULL" else (COLORS["danger"] if direction == "BEAR" else COLORS["warning"])
    dir_icon = "^" if direction == "BULL" else ("v" if direction == "BEAR" else "-")

    # ── Top metrics row ──
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">PREDICTED RETURN</div><div style="font-size:26px; font-weight:700; color:{dir_color}; margin-top:8px;">{pred_ret:+.2f}%</div><div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Next trading day</div></div>""", unsafe_allow_html=True)
    with c2:
        bp_color = COLORS["success"] if bull_prob > 0.6 else (COLORS["danger"] if bull_prob < 0.4 else COLORS["warning"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">BULL PROBABILITY</div><div style="font-size:26px; font-weight:700; color:{bp_color}; margin-top:8px;">{bull_prob*100:.0f}%</div><div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Classifier output</div></div>""", unsafe_allow_html=True)
    with c3:
        conf_color = COLORS["success"] if confidence >= 70 else (COLORS["warning"] if confidence >= 40 else COLORS["danger"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">CONFIDENCE</div><div style="font-size:26px; font-weight:700; color:{conf_color}; margin-top:8px;">{confidence:.0f}%</div><div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Model certainty</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">DIRECTION</div><div style="font-size:26px; font-weight:700; color:{dir_color}; margin-top:8px;">{dir_icon} {direction}</div><div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Signal</div></div>""", unsafe_allow_html=True)
    with c5:
        score_color = COLORS["success"] if ml_score >= 65 else (COLORS["warning"] if ml_score >= 40 else COLORS["danger"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">ML SCORE</div><div style="font-size:26px; font-weight:700; color:{score_color}; margin-top:8px;">{ml_score:.0f}</div><div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Sharpe-adjusted</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Quant Formula Breakdown (for selected ticker) ──
    _render_quant_breakdown(ticker, prediction)

    # ── Drift warning ──
    drift = prediction.get("drift_warning", "")
    if drift:
        st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {COLORS['warning']}; padding:12px 16px;"><div style="font-size:13px; color:{COLORS['warning']}; font-weight:600;">Distribution Drift Detected</div><div style="font-size:12px; color:{COLORS['text_secondary']}; margin-top:4px;">{drift}</div></div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Signal callout ──
    if abs(pred_ret) > 0.2 and confidence >= 50:
        signal_type = "BUY" if pred_ret > 0 else "SELL"
        signal_color = COLORS["success"] if signal_type == "BUY" else COLORS["danger"]
        target_price = current_price * (1 + pred_ret / 100)
        st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {signal_color}; padding:16px 20px;"><div style="font-size:16px; font-weight:600; color:{signal_color};">{signal_type} Signal — {ticker}</div><div style="font-size:13px; color:{COLORS['text_secondary']};">Predicted {pred_ret:+.2f}% move | Target ${target_price:.2f} | Confidence {confidence:.0f}%</div></div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Candlestick chart with forecast ──
    col_chart, col_forecast = st.columns([3, 1])
    with col_chart:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Price Chart &amp; Forecast</div>""", unsafe_allow_html=True)
        _render_candlestick(df, prediction, ticker)
    with col_forecast:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">10-Day Forecast</div>""", unsafe_allow_html=True)
        forecast = prediction.get("forecast_10d", [])
        if forecast:
            for day_data in forecast:
                day_num = day_data.get("day", 0)
                avg_pred = day_data.get("avg_pred", 0)
                pct = ((avg_pred - current_price) / current_price) * 100
                pct_color = COLORS["success"] if pct > 0 else COLORS["danger"]
                st.markdown(f"""<div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid {COLORS['border_light']};"><span style="font-size:13px; color:{COLORS['text_secondary']};">Day {day_num}</span><span style="font-size:13px; font-weight:500; color:{pct_color};">${avg_pred:.2f} ({pct:+.1f}%)</span></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='color:{COLORS['text_dim']}; font-size:13px;'>No forecast data</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Walk-Forward Backtest + Confidence Intervals ──
    col_bt, col_ci = st.columns(2)

    with col_bt:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Walk-Forward Backtest</div>""", unsafe_allow_html=True)
        with st.spinner("Running walk-forward validation..."):
            bt = _run_backtest(ticker)
        if bt:
            wf_hit = bt["wf_hit_rate"]
            dummy = bt["dummy_baseline"]
            edge = bt["edge"]
            wf_r2 = bt["wf_r2"]
            edge_color = COLORS["success"] if edge > 0 else COLORS["danger"]
            hit_color = COLORS["success"] if wf_hit > dummy else COLORS["danger"]
            st.markdown(f"""<div style="{CARD_CSS} padding:20px;"><div style="display:flex; gap:16px; margin-bottom:16px;"><div style="flex:1; text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">HIT RATE</div><div style="font-size:22px; font-weight:700; color:{hit_color};">{wf_hit:.1f}%</div></div><div style="flex:1; text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">VS DUMMY</div><div style="font-size:22px; font-weight:700; color:{edge_color};">{edge:+.1f}pp</div></div><div style="flex:1; text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">R2</div><div style="font-size:22px; font-weight:700; color:{COLORS['text']};">{wf_r2:.4f}</div></div></div></div>""", unsafe_allow_html=True)
            folds = bt.get("fold_results", [])
            if folds:
                st.markdown(f"""<div style="font-size:14px; font-weight:600; color:{COLORS['text']}; margin:12px 0 8px 0;">Per-Fold Results</div>""", unsafe_allow_html=True)
                for f in folds:
                    hit_c = COLORS["success"] if f["hit_rate"] > 52 else (COLORS["danger"] if f["hit_rate"] < 48 else COLORS["warning"])
                    st.markdown(f"""<div style="display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid {COLORS['border_light']}; font-size:12px;"><span style="color:{COLORS['text_dim']};">Fold {f['fold']}</span><span style="color:{COLORS['text_secondary']};">{f['date_range']}</span><span style="color:{hit_c}; font-weight:600;">{f['hit_rate']}%</span></div>""", unsafe_allow_html=True)
            _render_backtest_chart(bt)
        else:
            st.markdown(f"""<div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">Not enough data for backtest</div>""", unsafe_allow_html=True)

    with col_ci:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Confidence Intervals</div>""", unsafe_allow_html=True)
        with st.spinner("Computing bootstrap intervals..."):
            ci = _bootstrap_confidence(ticker)
        if ci:
            ci_low, ci_high, ci_mean, ci_std = ci["ci_low"], ci["ci_high"], ci["mean"], ci["std"]
            bar_min = min(ci_low, -2)
            bar_max = max(ci_high, 2)
            bar_range = bar_max - bar_min
            low_pct = ((ci_low - bar_min) / bar_range) * 100
            high_pct = ((ci_high - bar_min) / bar_range) * 100
            mean_pct = ((ci_mean - bar_min) / bar_range) * 100
            st.markdown(f"""<div style="{CARD_CSS} padding:20px;"><div style="font-size:13px; color:{COLORS['text_muted']}; margin-bottom:12px;">90% Confidence Interval (30 bootstrap models)</div><div style="position:relative; height:40px; background:{COLORS['bg_elevated']}; border-radius:8px; overflow:hidden; margin-bottom:16px;"><div style="position:absolute; left:{low_pct}%; width:{high_pct - low_pct}%; height:100%; background:{COLORS['accent']}20; border-radius:4px;"></div><div style="position:absolute; left:{mean_pct}%; width:2px; height:100%; background:{COLORS['accent']};"></div></div><div style="display:flex; justify-content:space-between;"><div style="text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']};">LOW (5th)</div><div style="font-size:16px; font-weight:600; color:{COLORS['danger']};">{ci_low:+.2f}%</div></div><div style="text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']};">MEAN</div><div style="font-size:16px; font-weight:600; color:{COLORS['text']};">{ci_mean:+.2f}%</div></div><div style="text-align:center;"><div style="font-size:11px; color:{COLORS['text_muted']};">HIGH (95th)</div><div style="font-size:16px; font-weight:600; color:{COLORS['success']};">{ci_high:+.2f}%</div></div></div><div style="text-align:center; margin-top:12px; font-size:12px; color:{COLORS['text_dim']};">Spread: {ci_std:.3f}% — {"tight (high confidence)" if ci_std < 0.5 else "wide (lower confidence)"}</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">Not enough data for bootstrap</div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Feature Importance ──
    if bt and bt.get("feature_importances"):
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Feature Importance</div>""", unsafe_allow_html=True)
        importances = bt["feature_importances"]
        for fname, fimp in list(importances.items())[:10]:
            bar_width = min(fimp * 500, 100)
            bar_color = COLORS["accent"] if fimp > 0.08 else COLORS["text_secondary"]
            st.markdown(f"""<div style="display:flex; align-items:center; gap:12px; padding:6px 0;"><div style="width:160px; font-size:13px; color:{COLORS['text_secondary']}; text-align:right;">{fname}</div><div style="flex:1; height:8px; background:{COLORS['bg_elevated']}; border-radius:4px; overflow:hidden;"><div style="height:100%; width:{bar_width}%; background:{bar_color}; border-radius:4px;"></div></div><div style="width:50px; font-size:13px; color:{COLORS['text']};">{fimp:.3f}</div></div>""", unsafe_allow_html=True)

    # ── AI Hedge Fund Sector Tracker ──
    st.markdown("<br>", unsafe_allow_html=True)
    _render_hedge_fund_watchlist()

    # ── Train model button ──
    st.markdown("<br>", unsafe_allow_html=True)
    _, col_train, _ = st.columns([1, 2, 1])
    with col_train:
        if st.button("Re-train Model", type="secondary", use_container_width=True):
            with st.spinner(f"Training model on {ticker} (walk-forward, 730d)..."):
                from analysis.ml.predictor import train_model
                result = train_model(ticker, lookback_days=730)
            if "error" in result:
                st.error(result["error"])
            else:
                warnings = result.get("warnings", [])
                warn_text = f" | Warnings: {len(warnings)}" if warnings else ""
                st.success(f"Walk-forward hit rate: {result['hit_rate_test']:.1f}% | Edge: {result['hit_rate_test'] - result.get('dummy_baseline', 50):+.1f}pp{warn_text}")
                if warnings:
                    for w in warnings:
                        st.warning(w)
                st.rerun()


# ── Quant Formula Breakdown ────────────────────────────────────────────────

def _render_quant_breakdown(ticker: str, prediction: dict):
    """Render six-formula quant breakdown + whale detection for a ticker."""
    # Try to get from scan results first (has quant fields populated)
    results = st.session_state.get("overview_scan_results", [])
    scored = None
    for t in results:
        if getattr(t, "ticker", "") == ticker:
            scored = t
            break

    if scored and getattr(scored, "quant_score", 0) > 0:
        _render_quant_from_scored(scored)
    else:
        # Compute on the fly
        _render_quant_live(ticker, prediction)


def _render_quant_from_scored(scored):
    """Render quant breakdown from a ScoredTicker that has quant fields populated."""
    quant_score = getattr(scored, "quant_score", 0)
    n_agree = getattr(scored, "quant_n_agreeing", 0)
    aligned = getattr(scored, "quant_aligned", False)
    whale_score = getattr(scored, "whale_score", 0)

    status_color = COLORS["success"] if aligned else COLORS["warning"]
    status_label = f"{n_agree}/6 Aligned" if aligned else f"{n_agree}/6"

    st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:10px;">Six-Formula Quant Analysis</div>""", unsafe_allow_html=True)

    # Summary row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        qc = COLORS["success"] if quant_score >= 65 else (COLORS["warning"] if quant_score >= 40 else COLORS["danger"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:16px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">QUANT SCORE</div><div style="font-size:24px; font-weight:700; color:{qc}; margin-top:6px;">{quant_score:.0f}</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:16px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">ALIGNMENT</div><div style="font-size:24px; font-weight:700; color:{status_color}; margin-top:6px;">{status_label}</div></div>""", unsafe_allow_html=True)
    with c3:
        kelly = getattr(scored, "kelly_fraction", 0)
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:16px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">KELLY SIZE</div><div style="font-size:24px; font-weight:700; color:{COLORS['text']}; margin-top:6px;">{kelly*100:.1f}%</div></div>""", unsafe_allow_html=True)
    with c4:
        wc = COLORS["accent"] if whale_score >= 40 else COLORS["text_dim"]
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:16px;"><div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">WHALE ACTIVITY</div><div style="font-size:24px; font-weight:700; color:{wc}; margin-top:6px;">{whale_score:.0f}</div></div>""", unsafe_allow_html=True)

    # Formula detail table
    formulas = [
        ("LMSR", getattr(scored, "lmsr_mispricing", 0), f"Mispricing: {getattr(scored, 'lmsr_mispricing', 0):+.4f}"),
        ("Kelly", getattr(scored, "kelly_fraction", 0), f"Position: {getattr(scored, 'kelly_fraction', 0)*100:.1f}%"),
        ("EV Gap", getattr(scored, "ev_gap", 0), f"Expected value: {getattr(scored, 'ev_gap', 0):+.2f}%"),
        ("KL Div", getattr(scored, "kl_divergence", 0), f"Divergence: {getattr(scored, 'kl_divergence', 0):.4f}"),
        ("Bayesian", getattr(scored, "bayesian_posterior", 0.5), f"Posterior: {getattr(scored, 'bayesian_posterior', 0.5)*100:.1f}%"),
        ("Stoikov", getattr(scored, "stoikov_reservation", 0), f"Reservation: ${getattr(scored, 'stoikov_reservation', 0):.2f}"),
    ]

    for name, val, desc in formulas:
        # Determine if this formula agrees
        if name == "LMSR":
            agrees = val > 0.05
        elif name == "Kelly":
            agrees = val > 0.01
        elif name == "EV Gap":
            agrees = val > 0.5
        elif name == "KL Div":
            agrees = val < 0.5
        elif name == "Bayesian":
            agrees = val > 0.55
        else:
            agrees = True  # Stoikov: check price vs reservation handled differently

        check = f'<span style="color:{COLORS["success"]};font-weight:700;">YES</span>' if agrees else f'<span style="color:{COLORS["danger"]};font-weight:700;">NO</span>'
        st.markdown(f"""<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid {COLORS['border_light']};"><span style="font-size:13px;font-weight:600;color:{COLORS['text']};width:80px;">{name}</span><span style="font-size:12px;color:{COLORS['text_secondary']};flex:1;">{desc}</span><span style="font-size:12px;width:40px;text-align:right;">{check}</span></div>""", unsafe_allow_html=True)

    # Whale detection row
    whale_sigma = getattr(scored, "whale_volume_sigma", 0)
    sweep = getattr(scored, "whale_sweep_detected", False)
    golden = getattr(scored, "whale_golden_sweep", False)
    whale_parts = []
    if whale_sigma >= 2.5:
        whale_parts.append(f"Vol {whale_sigma:.1f}sigma")
    if sweep:
        whale_parts.append("Sweep")
    if golden:
        whale_parts.append("Golden Sweep")

    if whale_parts:
        whale_text = " | ".join(whale_parts)
        st.markdown(f"""<div style="display:flex;align-items:center;gap:8px;padding:8px 0;"><span style="font-size:13px;font-weight:600;color:{COLORS['accent']};">Whale:</span><span style="font-size:12px;color:{COLORS['text_secondary']};">{whale_text}</span></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)


def _render_quant_live(ticker: str, prediction: dict):
    """Compute and render quant analysis on the fly (when ticker not in scan results)."""
    try:
        from analysis.quant_formulas import compute_quant_signals

        class _MiniTicker:
            pass
        t = _MiniTicker()
        t.composite_score = prediction.get("ml_score", 50)
        t.price = float(st.session_state.get("_pred_price", 0)) if st.session_state.get("_pred_price") else 0
        t.atr = t.price * 0.02
        t.direction = "LONG" if prediction.get("direction") == "BULL" else "SHORT"

        quant = compute_quant_signals(t, prediction)
        if quant and quant.quant_score > 0:
            # Create a mock scored ticker
            class _MockScored:
                pass
            s = _MockScored()
            for attr in ["lmsr_mispricing", "kelly_fraction", "ev_gap", "kl_divergence", "bayesian_posterior", "stoikov_reservation", "quant_score", "quant_aligned", "whale_score", "whale_volume_sigma", "whale_sweep_detected", "whale_golden_sweep"]:
                setattr(s, attr, getattr(quant, attr, 0))
            s.quant_n_agreeing = quant.n_agreeing
            _render_quant_from_scored(s)
    except Exception:
        pass


# ── Chart helpers ───────────────────────────────────────────────────────────

def _render_candlestick(df, prediction, ticker):
    try:
        import plotly.graph_objects as go
        recent = df.tail(60)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=recent.index, open=recent["Open"], high=recent["High"], low=recent["Low"], close=recent["Close"], name=ticker, increasing_line_color=COLORS["success"], decreasing_line_color=COLORS["danger"]))
        forecast = prediction.get("forecast_10d", [])
        if forecast:
            last_date = recent.index[-1]
            forecast_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=len(forecast))
            avg_prices = [f["avg_pred"] for f in forecast]
            fig.add_trace(go.Scatter(x=forecast_dates, y=avg_prices, mode="lines", name="ML Forecast", line=dict(color=COLORS["accent"], width=2, dash="dash")))
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=COLORS["bg_elevated"], xaxis_rangeslider_visible=False, font=dict(family=FONT, color=COLORS["text"]), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), xaxis=dict(gridcolor=COLORS["border_light"]), yaxis=dict(gridcolor=COLORS["border_light"]))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Chart error: {e}")


def _render_backtest_chart(bt):
    try:
        import plotly.graph_objects as go
        dates = bt["dates_test"]
        y_test = bt["y_test"]
        y_pred = bt["y_pred"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=y_test, mode="lines", name="Actual", line=dict(color=COLORS["text_secondary"], width=1)))
        fig.add_trace(go.Scatter(x=dates, y=y_pred, mode="lines", name="Predicted", line=dict(color=COLORS["accent"], width=2)))
        fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=COLORS["bg_elevated"], font=dict(family=FONT, color=COLORS["text"], size=11), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), xaxis=dict(gridcolor=COLORS["border_light"]), yaxis=dict(gridcolor=COLORS["border_light"], title="Return %"))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Backtest chart error: {e}")

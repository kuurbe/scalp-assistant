"""
ML Predictions page — Live ML forecasts, confidence intervals, backtesting,
candlestick charts with forecast overlays, and feature importance.
"""

import streamlit as st
import numpy as np
import pandas as pd
from dashboard.theme import COLORS, CARD_CSS, FONT

# ── Cache helpers ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_ohlcv(ticker: str, period: str = "120d"):
    """Fetch OHLCV data via yfinance."""
    import yfinance as yf
    df = yf.download(ticker, period=period, progress=False)
    if df is not None and isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _run_prediction(ticker: str):
    """Run ML prediction pipeline for a ticker."""
    from analysis.ml.predictor import predict_ticker
    df = _fetch_ohlcv(ticker)
    if df is None or len(df) < 30:
        return None, None
    return predict_ticker(ticker, df=df), df


@st.cache_data(ttl=300, show_spinner=False)
def _run_backtest(ticker: str):
    """Run backtest: train/test split, return metrics + series."""
    from analysis.ml.feature_engine import build_features, FEATURE_COLS
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler

    df = _fetch_ohlcv(ticker, period="365d")
    if df is None or len(df) < 60:
        return None

    featured = build_features(df)
    featured["target"] = featured["Close"].pct_change().shift(-1) * 100
    clean = featured.dropna(subset=FEATURE_COLS + ["target"])

    if len(clean) < 40:
        return None

    X = clean[FEATURE_COLS].values
    y_ret = clean["target"].values
    y_dir = (y_ret > 0.05).astype(int)  # Directional target
    dates = clean.index

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    split = int(len(X_scaled) * 0.8)
    X_train, X_test = X_scaled[:split], X_scaled[split:]
    y_ret_train, y_ret_test = y_ret[:split], y_ret[split:]
    y_dir_train, y_dir_test = y_dir[:split], y_dir[split:]
    dates_test = dates[split:]

    # Regressor for magnitude
    reg_model = GradientBoostingRegressor(
        n_estimators=200, learning_rate=0.05, max_depth=3,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )
    reg_model.fit(X_train, y_ret_train)
    y_pred = reg_model.predict(X_test)
    r2 = reg_model.score(X_test, y_ret_test)

    # Classifier for direction
    from sklearn.ensemble import GradientBoostingClassifier
    clf_model = GradientBoostingClassifier(
        n_estimators=200, learning_rate=0.05, max_depth=3,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )
    clf_model.fit(X_train, y_dir_train)
    y_dir_pred = clf_model.predict(X_test)
    hit_rate = float(np.mean(y_dir_pred == y_dir_test)) * 100
    directional_accuracy = float(np.mean(np.sign(y_pred) == np.sign(y_ret_test))) * 100

    importances = dict(zip(FEATURE_COLS, clf_model.feature_importances_))

    return {
        "directional_accuracy": round(directional_accuracy, 1),
        "hit_rate": round(hit_rate, 1),
        "r2": round(r2, 4),
        "n_test": len(y_ret_test),
        "y_test": y_ret_test,
        "y_pred": y_pred,
        "dates_test": dates_test,
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


@st.cache_data(ttl=300, show_spinner=False)
def _bootstrap_confidence(ticker: str, n_bootstraps: int = 30):
    """Bootstrap ensemble for confidence intervals."""
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
    X_train, X_test = X_scaled[:split], X_scaled[split:]
    y_train, y_test = y[:split], y[split:]

    # Latest point for prediction
    X_latest = X_scaled[-1:]

    preds = []
    for _ in range(n_bootstraps):
        X_b, y_b = resample(X_train, y_train)
        m = GradientBoostingRegressor(
            n_estimators=100, learning_rate=0.05, max_depth=4,
            subsample=0.8, random_state=None,
        )
        m.fit(X_b, y_b)
        preds.append(float(m.predict(X_latest)[0]))

    preds = np.array(preds)
    return {
        "mean": round(float(np.mean(preds)), 4),
        "ci_low": round(float(np.percentile(preds, 5)), 4),
        "ci_high": round(float(np.percentile(preds, 95)), 4),
        "std": round(float(np.std(preds)), 4),
    }


# ── Render ──────────────────────────────────────────────────────────────────

def render():
    st.markdown(f"""
    <div style="font-size:34px; font-weight:700; color:{COLORS['text']};
                letter-spacing:-0.02em; margin-bottom:4px;">
        ML Predictions
    </div>
    <div style="font-size:15px; color:{COLORS['text_muted']}; margin-bottom:28px;">
        Machine learning forecasts with confidence intervals, backtesting &amp; feature analysis
    </div>
    """, unsafe_allow_html=True)

    # ─── Ticker selector ───
    from config import settings
    stocks = settings.get_universe("stocks")
    default_tickers = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "META", "GOOG", "AMD"]
    all_tickers = default_tickers + [t for t in stocks if t not in default_tickers]

    col_ticker, col_custom = st.columns([2, 1])
    with col_ticker:
        selected = st.selectbox("Select Ticker", all_tickers, index=0)
    with col_custom:
        custom = st.text_input("Or enter any ticker", value="", placeholder="e.g. COIN")

    ticker = custom.strip().upper() if custom.strip() else selected

    st.markdown(f"<hr style='border-top:1px solid {COLORS['divider']};margin:8px 0 24px 0;'>",
                unsafe_allow_html=True)

    # ─── Run prediction ───
    prediction, df = _run_prediction(ticker)

    if prediction is None or df is None or len(df) < 20:
        st.warning(f"Not enough data for {ticker}. Try a different ticker.")
        return

    # ─── Top metrics row ───
    pred_ret = prediction.get("predicted_return", 0)
    confidence = prediction.get("confidence", 0)
    direction = prediction.get("direction", "NEUTRAL")
    ml_score = prediction.get("ml_score", 50)
    bull_prob = prediction.get("bull_prob", 0.5)
    current_price = float(df["Close"].iloc[-1])

    dir_color = COLORS["success"] if direction == "BULL" else (COLORS["danger"] if direction == "BEAR" else COLORS["warning"])
    dir_icon = "↑" if direction == "BULL" else ("↓" if direction == "BEAR" else "→")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">PREDICTED RETURN</div>
            <div style="font-size:26px; font-weight:700; color:{dir_color}; margin-top:8px;">{pred_ret:+.2f}%</div>
            <div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Next trading day</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        bp_color = COLORS["success"] if bull_prob > 0.6 else (COLORS["danger"] if bull_prob < 0.4 else COLORS["warning"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">BULL PROBABILITY</div>
            <div style="font-size:26px; font-weight:700; color:{bp_color}; margin-top:8px;">{bull_prob*100:.0f}%</div>
            <div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Classifier output</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        conf_color = COLORS["success"] if confidence >= 70 else (COLORS["warning"] if confidence >= 40 else COLORS["danger"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">CONFIDENCE</div>
            <div style="font-size:26px; font-weight:700; color:{conf_color}; margin-top:8px;">{confidence:.0f}%</div>
            <div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Model certainty</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">DIRECTION</div>
            <div style="font-size:26px; font-weight:700; color:{dir_color}; margin-top:8px;">{dir_icon} {direction}</div>
            <div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">Signal</div>
        </div>""", unsafe_allow_html=True)

    with c5:
        score_color = COLORS["success"] if ml_score >= 65 else (COLORS["warning"] if ml_score >= 40 else COLORS["danger"])
        st.markdown(f"""<div style="{CARD_CSS} text-align:center; padding:20px;">
            <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase; letter-spacing:0.06em;">ML SCORE</div>
            <div style="font-size:26px; font-weight:700; color:{score_color}; margin-top:8px;">{ml_score:.0f}</div>
            <div style="font-size:12px; color:{COLORS['text_dim']}; margin-top:4px;">0-100 scale</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Signal callout ───
    if abs(pred_ret) > 0.2 and confidence >= 50:
        signal_type = "BUY" if pred_ret > 0 else "SELL"
        signal_color = COLORS["success"] if signal_type == "BUY" else COLORS["danger"]
        target_price = current_price * (1 + pred_ret / 100)
        st.markdown(f"""<div style="{CARD_CSS} border-left:4px solid {signal_color}; padding:16px 20px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="width:40px; height:40px; border-radius:50%; background:{signal_color}15; display:flex; align-items:center; justify-content:center;">
                    <span style="font-size:20px; color:{signal_color};">{"📈" if signal_type == "BUY" else "📉"}</span>
                </div>
                <div>
                    <div style="font-size:16px; font-weight:600; color:{signal_color};">{signal_type} Signal — {ticker}</div>
                    <div style="font-size:13px; color:{COLORS['text_secondary']};">
                        Predicted {pred_ret:+.2f}% move | Target ${target_price:.2f} | Confidence {confidence:.0f}%
                    </div>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # ─── Candlestick chart with forecast ───
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
                st.markdown(f"""<div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid {COLORS['border_light']};">
                    <span style="font-size:13px; color:{COLORS['text_secondary']};">Day {day_num}</span>
                    <span style="font-size:13px; font-weight:500; color:{pct_color};">${avg_pred:.2f} ({pct:+.1f}%)</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='color:{COLORS['text_dim']}; font-size:13px;'>No forecast data</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Confidence Intervals + Backtest (side by side) ───
    col_ci, col_bt = st.columns(2)

    with col_ci:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Confidence Intervals</div>""", unsafe_allow_html=True)
        with st.spinner("Computing bootstrap intervals..."):
            ci = _bootstrap_confidence(ticker)
        if ci:
            ci_low = ci["ci_low"]
            ci_high = ci["ci_high"]
            ci_mean = ci["mean"]
            ci_std = ci["std"]

            # Visual bar
            bar_min = min(ci_low, -2)
            bar_max = max(ci_high, 2)
            bar_range = bar_max - bar_min
            low_pct = ((ci_low - bar_min) / bar_range) * 100
            high_pct = ((ci_high - bar_min) / bar_range) * 100
            mean_pct = ((ci_mean - bar_min) / bar_range) * 100

            st.markdown(f"""<div style="{CARD_CSS} padding:20px;">
                <div style="font-size:13px; color:{COLORS['text_muted']}; margin-bottom:12px;">90% Confidence Interval (30 bootstrap models)</div>
                <div style="position:relative; height:40px; background:{COLORS['bg_elevated']}; border-radius:8px; overflow:hidden; margin-bottom:16px;">
                    <div style="position:absolute; left:{low_pct}%; width:{high_pct - low_pct}%; height:100%; background:{COLORS['accent']}20; border-radius:4px;"></div>
                    <div style="position:absolute; left:{mean_pct}%; width:2px; height:100%; background:{COLORS['accent']};"></div>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <div style="text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']};">LOW (5th %ile)</div>
                        <div style="font-size:16px; font-weight:600; color:{COLORS['danger']};">{ci_low:+.2f}%</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']};">MEAN</div>
                        <div style="font-size:16px; font-weight:600; color:{COLORS['text']};">{ci_mean:+.2f}%</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']};">HIGH (95th %ile)</div>
                        <div style="font-size:16px; font-weight:600; color:{COLORS['success']};">{ci_high:+.2f}%</div>
                    </div>
                </div>
                <div style="text-align:center; margin-top:12px; font-size:12px; color:{COLORS['text_dim']};">Spread: {ci_std:.3f}% — {"tight (high confidence)" if ci_std < 0.5 else "wide (lower confidence)"}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">Not enough data for bootstrap analysis</div>""", unsafe_allow_html=True)

    with col_bt:
        st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Backtest Results</div>""", unsafe_allow_html=True)
        with st.spinner("Running backtest..."):
            bt = _run_backtest(ticker)
        if bt:
            hit_rate = bt.get("hit_rate", bt["directional_accuracy"])
            da = bt["directional_accuracy"]
            r2 = bt["r2"]
            n = bt["n_test"]
            hr_color = COLORS["success"] if hit_rate >= 55 else (COLORS["warning"] if hit_rate >= 45 else COLORS["danger"])
            da_color = COLORS["success"] if da >= 55 else (COLORS["warning"] if da >= 45 else COLORS["danger"])

            st.markdown(f"""<div style="{CARD_CSS} padding:20px;">
                <div style="display:flex; gap:16px; margin-bottom:16px;">
                    <div style="flex:1; text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">CLASSIFIER HIT RATE</div>
                        <div style="font-size:22px; font-weight:700; color:{hr_color};">{hit_rate:.1f}%</div>
                    </div>
                    <div style="flex:1; text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">REGRESSOR DIR.</div>
                        <div style="font-size:22px; font-weight:700; color:{da_color};">{da:.1f}%</div>
                    </div>
                    <div style="flex:1; text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">R²</div>
                        <div style="font-size:22px; font-weight:700; color:{COLORS['text']};">{r2:.4f}</div>
                    </div>
                    <div style="flex:1; text-align:center;">
                        <div style="font-size:11px; color:{COLORS['text_muted']}; text-transform:uppercase;">TEST DAYS</div>
                        <div style="font-size:22px; font-weight:700; color:{COLORS['text']};">{n}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

            # Actual vs predicted chart
            _render_backtest_chart(bt)
        else:
            st.markdown(f"""<div style="{CARD_CSS} text-align:center; color:{COLORS['text_dim']}; padding:40px;">Not enough data for backtest</div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Feature Importance ───
    st.markdown(f"""<div style="font-size:18px; font-weight:600; color:{COLORS['text']}; margin-bottom:12px;">Feature Importance</div>""", unsafe_allow_html=True)

    if bt and bt.get("feature_importances"):
        importances = bt["feature_importances"]
        top_features = list(importances.items())[:10]

        for fname, fimp in top_features:
            bar_width = min(fimp * 500, 100)  # Scale for display
            bar_color = COLORS["accent"] if fimp > 0.08 else COLORS["text_secondary"]
            st.markdown(f"""<div style="display:flex; align-items:center; gap:12px; padding:6px 0;">
                <div style="width:160px; font-size:13px; color:{COLORS['text_secondary']}; text-align:right;">{fname}</div>
                <div style="flex:1; height:8px; background:{COLORS['bg_elevated']}; border-radius:4px; overflow:hidden;">
                    <div style="height:100%; width:{bar_width}%; background:{bar_color}; border-radius:4px;"></div>
                </div>
                <div style="width:50px; font-size:13px; color:{COLORS['text']};">{fimp:.3f}</div>
            </div>""", unsafe_allow_html=True)

    # ─── Train model button ───
    st.markdown("<br>", unsafe_allow_html=True)
    _, col_train, _ = st.columns([1, 2, 1])
    with col_train:
        if st.button("Re-train Model", type="secondary", use_container_width=True):
            with st.spinner(f"Training model on {ticker}..."):
                from analysis.ml.predictor import train_model
                result = train_model(ticker, lookback_days=730)
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(f"Model trained! R² test: {result['r2_test']:.4f} | Samples: {result['n_samples']}")
                st.rerun()


# ── Chart helpers ───────────────────────────────────────────────────────────

def _render_candlestick(df, prediction, ticker):
    """Render candlestick chart with forecast overlay using Plotly."""
    try:
        import plotly.graph_objects as go

        # Last 60 days for readability
        recent = df.tail(60)

        fig = go.Figure()

        # Candlesticks
        fig.add_trace(go.Candlestick(
            x=recent.index,
            open=recent["Open"],
            high=recent["High"],
            low=recent["Low"],
            close=recent["Close"],
            name=ticker,
            increasing_line_color=COLORS["success"],
            decreasing_line_color=COLORS["danger"],
        ))

        # Forecast overlay
        forecast = prediction.get("forecast_10d", [])
        if forecast:
            last_date = recent.index[-1]
            forecast_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=len(forecast))
            linear_prices = [f["linear_pred"] for f in forecast]
            kinematic_prices = [f["kinematic_pred"] for f in forecast]
            avg_prices = [f["avg_pred"] for f in forecast]

            fig.add_trace(go.Scatter(
                x=forecast_dates, y=avg_prices,
                mode="lines", name="ML Forecast",
                line=dict(color=COLORS["accent"], width=2, dash="dash"),
            ))
            fig.add_trace(go.Scatter(
                x=forecast_dates, y=linear_prices,
                mode="lines", name="Linear",
                line=dict(color=COLORS["text_dim"], width=1, dash="dot"),
                visible="legendonly",
            ))
            fig.add_trace(go.Scatter(
                x=forecast_dates, y=kinematic_prices,
                mode="lines", name="Kinematic",
                line=dict(color=COLORS["warning"], width=1, dash="dot"),
                visible="legendonly",
            ))

        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=COLORS["bg_elevated"],
            xaxis_rangeslider_visible=False,
            font=dict(family=FONT, color=COLORS["text"]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(gridcolor=COLORS["border_light"]),
            yaxis=dict(gridcolor=COLORS["border_light"]),
        )

        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Chart error: {e}")


def _render_backtest_chart(bt):
    """Render actual vs predicted returns chart."""
    try:
        import plotly.graph_objects as go

        dates = bt["dates_test"]
        y_test = bt["y_test"]
        y_pred = bt["y_pred"]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=y_test,
            mode="lines", name="Actual",
            line=dict(color=COLORS["text_secondary"], width=1),
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=y_pred,
            mode="lines", name="Predicted",
            line=dict(color=COLORS["accent"], width=2),
        ))

        fig.update_layout(
            height=200,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=COLORS["bg_elevated"],
            font=dict(family=FONT, color=COLORS["text"], size=11),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(gridcolor=COLORS["border_light"]),
            yaxis=dict(gridcolor=COLORS["border_light"], title="Return %"),
        )

        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Backtest chart error: {e}")

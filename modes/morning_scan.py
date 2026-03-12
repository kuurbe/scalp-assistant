"""
Morning scan mode — full universe scan, top picks at open.
"""
import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import settings
from output.formatter import (
    console, print_banner, print_macro_context, print_leaderboard,
    print_pick_detail, print_checklist, print_save_summary,
    print_social_intel_panel, print_geopolitical_brief,
)
from output.performance_tracker import log_picks
from analysis.scoring.composite_scorer import ScoredTicker, score_ticker


def run_morning_scan(top_n: int = None, tickers: str = None, asset_class: str = "stocks"):
    """Execute the full morning scan pipeline."""
    top_n = top_n or settings.TOP_N_PICKS

    print_banner("SCAN")

    # Determine ticker universe
    if tickers:
        universe = [t.strip().upper() for t in tickers.split(",")]
    else:
        universe = settings.get_universe(asset_class)

    console.print(f"  Scanning {len(universe)} tickers...\n")

    # 1. Macro context
    macro = _get_macro_context()
    vix = macro.get("vix") or 0
    vix_label = _vix_label(vix)
    macro_regime = macro.get("macro_regime", "NEUTRAL")
    market_bias = _get_market_bias()

    print_macro_context(vix, vix_label, macro_regime, market_bias)

    # 1b. Social intelligence (global — not per-ticker)
    social_global = _fetch_social_intel()
    political_pulse = _fetch_political_pulse()
    war_watch = _fetch_war_watch()
    influencer_pulse = _fetch_influencer_pulse()

    # Print social intel panels
    print_social_intel_panel(social_global, political_pulse, war_watch, influencer_pulse)

    # 2. Pre-fetch bulk data
    reddit_data = _fetch_reddit()
    short_data = _fetch_short_volume(universe)

    # 3. Analyze each ticker
    all_scored = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_analyze_ticker, ticker, macro_regime, reddit_data, short_data,
                        political_pulse, war_watch, influencer_pulse, asset_class): ticker
            for ticker in universe
        }
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if done_count % 10 == 0:
                console.print(f"  ...{done_count}/{len(universe)}", style="dim")
            result = future.result()
            if result:
                all_scored.append(result)

    # 4. Sort by composite score
    all_scored.sort(key=lambda x: x.composite_score, reverse=True)

    active = [s for s in all_scored if s.composite_score >= settings.MIN_COMPOSITE_SCORE]
    console.print(f"\n  Scan complete — {len(active)} active setups found\n")

    # 5. Print leaderboard
    print_leaderboard(all_scored, top_n=15)

    # 6. Print detailed picks
    top_picks = all_scored[:top_n]
    console.print()
    console.print(f"  [bold]TODAY'S TOP {len(top_picks)} SETUPS[/]")
    for i, pick in enumerate(top_picks, 1):
        print_pick_detail(pick, i)

    # 7. Print checklist
    print_checklist(vix, vix_label)

    # 8. Save to CSV
    picks_file, history_file = log_picks(all_scored)
    print_save_summary(picks_file, history_file)


def _analyze_ticker(ticker: str, macro_regime: str, reddit_data: dict, short_data: dict,
                    political_pulse: dict = None, war_watch: dict = None,
                    influencer_pulse: dict = None,
                    asset_class: str = "stocks") -> ScoredTicker | None:
    """Full analysis pipeline for a single ticker."""
    try:
        from data.fetchers.yfinance_fetcher import get_daily_ohlcv, get_intraday_ohlcv

        # Fetch data
        daily = get_daily_ohlcv(ticker)
        if daily is None or len(daily) < 20:
            return None

        intraday = get_intraday_ohlcv(ticker)

        close = daily["Close"]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else price
        pct_change = ((price - prev) / prev) * 100 if prev > 0 else 0
        vol = float(daily["Volume"].iloc[-1])
        avg_vol = float(daily["Volume"].iloc[:-1].mean()) if len(daily) > 1 else vol
        rel_volume = vol / avg_vol if avg_vol > 0 else 0

        # Skip low-activity tickers (forex/crypto have no volume data)
        if price < 1:
            return None
        if asset_class not in ("forex", "crypto") and rel_volume < 0.3:
            return None
        # For forex/crypto, default rel_volume to 1.0 when no volume data
        if rel_volume == 0 and asset_class in ("forex", "crypto"):
            rel_volume = 1.0

        # Physics analysis
        kinematic_score, kinematic_phase, accel_z = _physics_analysis(close, intraday)

        # Regime classification
        regime_info = _regime_analysis(close, intraday)

        # Technical analysis
        tech_score, tech_data = _technical_analysis(daily, intraday, price)

        # Statistical analysis (pass asset class params for GBM)
        ac = settings.ASSET_CLASS_CONFIG.get(asset_class, {})
        stat_score = _statistical_analysis(daily, price, tech_data,
                                           trading_days=ac.get("trading_days_year", 252),
                                           minutes_per_day=ac.get("minutes_per_day", 390))

        # Catalyst analysis
        cat_info, cat_score_val = _catalyst_analysis(ticker, reddit_data, short_data)

        # Levels
        levels_data = _get_levels(ticker, daily, intraday)

        # Price targets
        atr_val = tech_data.get("atr", price * 0.02)
        targets = _get_targets(price, levels_data, atr_val)

        # Build price data dict
        price_data = {
            "price": price,
            "pct_change": round(pct_change, 2),
            "rel_volume": round(rel_volume, 2),
            "rsi": tech_data.get("rsi", 50),
            "atr": atr_val,
        }

        # Compute sub-scores for physics
        ou_score = _ou_analysis(close)
        hurst_score = _hurst_analysis(close)
        entropy_score = _entropy_analysis(close)
        kalman_score = _kalman_analysis(close)
        physics_total = (
            0.30 * kinematic_score +
            0.20 * ou_score +
            0.20 * hurst_score +
            0.15 * entropy_score +
            0.15 * kalman_score
        )

        # Social intelligence analysis
        social_score_val, social_info = _social_analysis(
            ticker, political_pulse, war_watch, influencer_pulse
        )

        return score_ticker(
            ticker=ticker,
            physics_score=physics_total,
            technical_score=tech_score,
            catalyst_score=cat_score_val,
            statistical_score=stat_score,
            social_score=social_score_val,
            macro_regime=macro_regime,
            regime_info=regime_info,
            kinematic_phase=kinematic_phase,
            price_data=price_data,
            levels_data=levels_data,
            targets_data=targets,
            catalyst_info=cat_info,
            social_info=social_info,
            asset_class=asset_class,
        )
    except Exception:
        return None


# ─── Helper functions ───

def _get_macro_context() -> dict:
    try:
        from data.fetchers.fred_fetcher import get_macro_context
        ctx = get_macro_context()
        # Fallback: get VIX from yfinance if FRED didn't provide it
        if not ctx.get("vix"):
            try:
                import yfinance as yf
                h = yf.Ticker("^VIX").history(period="2d")
                if len(h) > 0:
                    ctx["vix"] = round(float(h["Close"].iloc[-1]), 2)
            except Exception:
                pass
        return ctx
    except Exception:
        return {"vix": 0, "macro_regime": "NEUTRAL"}


def _vix_label(vix: float) -> str:
    if vix <= 0:
        return "check manually"
    if vix < 15:
        return "LOW — full size OK"
    elif vix < 20:
        return "NORMAL — standard size"
    elif vix < 25:
        return "HIGH — 1 contract max"
    else:
        return "DANGER — skip pumps"


def _get_market_bias() -> str:
    try:
        from data.fetchers.yfinance_fetcher import get_daily_ohlcv
        spy = get_daily_ohlcv("SPY")
        if spy is None or len(spy) < 50:
            return "unavailable"
        c = spy["Close"]
        ma50 = c.rolling(50).mean().iloc[-1]
        curr = c.iloc[-1]
        if len(c) >= 200:
            ma200 = c.rolling(200).mean().iloc[-1]
            if curr > ma50 and curr > ma200:
                return "BULL — favor CALLs"
            elif curr < ma50 and curr < ma200:
                return "BEAR — favor PUTs"
        if curr > ma50:
            return "LEAN BULL"
        return "MIXED — A+ setups only"
    except Exception:
        return "unavailable"


def _fetch_reddit() -> dict:
    try:
        from data.fetchers.reddit_fetcher import get_wsb_trending
        return get_wsb_trending() or {}
    except Exception:
        return {}


def _fetch_short_volume(universe: list) -> dict:
    try:
        from data.fetchers.finra_fetcher import get_short_volume
        result = {}
        for t in universe[:30]:  # limit to avoid slowness
            sv = get_short_volume(t)
            if sv:
                result[t] = sv
        return result
    except Exception:
        return {}


def _physics_analysis(close, intraday) -> tuple:
    try:
        from analysis.physics.kinematics import compute_kinematics, get_kinematic_score
        prices = intraday["Close"] if intraday is not None and len(intraday) > 10 else close
        score = get_kinematic_score(prices)
        kin = compute_kinematics(prices)
        phase = kin["phase"].iloc[-1] if len(kin) > 0 else "UNKNOWN"
        accel_z = float(kin["accel_z"].iloc[-1]) if len(kin) > 0 and "accel_z" in kin else 0
        return score, phase, accel_z
    except Exception:
        return 50, "UNKNOWN", 0


def _regime_analysis(close, intraday) -> dict:
    try:
        from analysis.scoring.regime_classifier import classify_stock_regime
        intra_close = intraday["Close"] if intraday is not None and len(intraday) > 20 else None
        return classify_stock_regime(close, intra_close)
    except Exception:
        return {"regime": "UNKNOWN", "confidence": "LOW", "preferred_strategy": "SKIP",
                "tradeable": True, "hurst": 0.5, "entropy": 0.5}


def _technical_analysis(daily, intraday, price) -> tuple:
    """Run all technical indicators and return composite score + data dict."""
    score = 50
    data = {"rsi": 50, "atr": price * 0.02}

    try:
        c = daily["Close"]

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi = 100 - 100 / (1 + gain / loss) if loss and loss != 0 else 50.0
        data["rsi"] = round(rsi, 1)

        # EMA stack
        ema9 = c.ewm(span=9).mean().iloc[-1]
        ema20 = c.ewm(span=20).mean().iloc[-1]
        ema50 = c.ewm(span=50).mean().iloc[-1]
        ema_count = sum([price > ema9, price > ema20, price > ema50])

        # MACD
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        macd = (ema12 - ema26).iloc[-1]
        signal_line = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        macd_bull = macd > signal_line

        # ATR
        try:
            from analysis.technical.atr_stops import compute_atr
            atr_series = compute_atr(daily)
            data["atr"] = float(atr_series.iloc[-1])
        except Exception:
            pass

        # CVD
        cvd_score = 50
        try:
            from analysis.technical.cvd import get_cvd_signal
            df_cvd = intraday if intraday is not None and len(intraday) > 10 else daily
            cvd_sig = get_cvd_signal(df_cvd)
            cvd_score = cvd_sig.get("score", 50)
        except Exception:
            pass

        # OBV
        obv_score = 50
        try:
            from analysis.technical.obv import detect_obv_divergence
            df_obv = intraday if intraday is not None and len(intraday) > 10 else daily
            obv_div = detect_obv_divergence(df_obv)
            if obv_div["divergence_type"] == "BULLISH":
                obv_score = 80
            elif obv_div["divergence_type"] == "BEARISH":
                obv_score = 20
        except Exception:
            pass

        # Candlestick patterns
        pattern_score = 50
        try:
            from analysis.technical.candlestick import detect_all_patterns
            df_pat = intraday if intraday is not None and len(intraday) > 3 else daily
            patterns = detect_all_patterns(df_pat)
            bull_patterns = [p for p in patterns if p["type"] == "BULLISH"]
            bear_patterns = [p for p in patterns if p["type"] == "BEARISH"]
            if bull_patterns:
                pattern_score = 70 + len(bull_patterns) * 10
            elif bear_patterns:
                pattern_score = 30 - len(bear_patterns) * 10
        except Exception:
            pass

        # Composite technical score
        tech_points = 0

        # RSI contribution
        if 55 <= rsi <= 68:
            tech_points += 15
        elif 45 <= rsi < 55:
            tech_points += 10
        elif rsi > 75:
            tech_points -= 5
        elif rsi < 30:
            tech_points += 15

        # EMA stack
        tech_points += ema_count * 8

        # MACD
        tech_points += 10 if macd_bull else -5

        # CVD + OBV + patterns
        tech_points += (cvd_score - 50) * 0.3
        tech_points += (obv_score - 50) * 0.2
        tech_points += (pattern_score - 50) * 0.2

        score = max(0, min(100, 50 + tech_points))
        data["cvd_score"] = cvd_score
        data["obv_score"] = obv_score

    except Exception:
        pass

    return round(score, 1), data


def _statistical_analysis(daily, price, tech_data,
                          trading_days: int = 252, minutes_per_day: int = 390) -> float:
    """Run GARCH + Z-score + GBM and return composite score."""
    try:
        scores = []

        # GARCH
        try:
            from analysis.statistical.garch import get_garch_score
            scores.append(get_garch_score(daily["Close"]))
        except Exception:
            scores.append(50)

        # Z-score
        try:
            from analysis.statistical.zscore import get_zscore_signal
            z_sig = get_zscore_signal(daily)
            if z_sig["dip_entry"]:
                scores.append(75)
            elif z_sig["spike_exit"]:
                scores.append(25)
            else:
                scores.append(50)
        except Exception:
            scores.append(50)

        # GBM
        atr = tech_data.get("atr", price * 0.02)
        try:
            from analysis.statistical.gbm_monte_carlo import get_gbm_score
            stop = price - atr * 1.5
            target = price + atr * 3.0
            scores.append(get_gbm_score(daily["Close"], stop, target,
                                       trading_days=trading_days,
                                       minutes_per_day=minutes_per_day))
        except Exception:
            scores.append(50)

        return round(sum(scores) / len(scores), 1)
    except Exception:
        return 50


def _catalyst_analysis(ticker, reddit_data, short_data) -> tuple:
    """Run catalyst pipeline and return (info_dict, score)."""
    try:
        from catalyst.news_aggregator import aggregate_news
        from catalyst.catalyst_detector import score_catalysts
        from catalyst.sentiment_tracker import get_combined_sentiment

        news = aggregate_news(ticker, max_age_hours=24)
        cat_info = score_catalysts(news)

        sentiment = get_combined_sentiment(ticker)

        short_ratio = 0
        if ticker in short_data:
            short_ratio = short_data[ticker].get("short_ratio", 0)

        reddit_trending = False
        if reddit_data and ticker in reddit_data:
            reddit_trending = True

        from analysis.scoring.catalyst_score import compute_catalyst_score
        cat_score = compute_catalyst_score(
            news_score=cat_info.get("catalyst_score", 0),
            sentiment_score=sentiment.get("sentiment_score", 0),
            reddit_trending=reddit_trending,
            short_ratio=short_ratio,
        )

        return cat_info, round(cat_score, 1)
    except Exception:
        return {"catalyst_score": 0, "summary": "No catalyst data", "direction": "NEUTRAL"}, 0


def _ou_analysis(close) -> float:
    try:
        from analysis.physics.ou_process import get_ou_score
        return get_ou_score(close)
    except Exception:
        return 50


def _hurst_analysis(close) -> float:
    try:
        from analysis.physics.hurst import get_hurst_score
        return get_hurst_score(close)
    except Exception:
        return 50


def _entropy_analysis(close) -> float:
    try:
        from analysis.physics.entropy import get_predictability_score
        return get_predictability_score(close)
    except Exception:
        return 50


def _kalman_analysis(close) -> float:
    try:
        from analysis.physics.kalman import get_kalman_score
        return get_kalman_score(close)
    except Exception:
        return 50


def _social_analysis(ticker: str, political_pulse: dict = None,
                     war_watch: dict = None, influencer_pulse: dict = None) -> tuple:
    """Run social intelligence analysis for a ticker. Returns (score, info_dict)."""
    social_score = 50
    social_info = {
        "political_exposure": "",
        "war_exposure": "",
        "influencer_signal": "",
        "social_narrative": "",
    }

    try:
        # Stocktwits sentiment
        st_score = 50
        try:
            from data.fetchers.stocktwits_fetcher import get_stocktwits_sentiment
            st = get_stocktwits_sentiment(ticker)
            if st and st.get("total_messages", 0) > 0:
                # Map -100..+100 to 0..100
                st_score = max(0, min(100, 50 + st.get("sentiment_score", 0) / 2))
        except Exception:
            pass

        # Political exposure
        pol_score = 50
        pol_label = ""
        try:
            if political_pulse and political_pulse.get("events"):
                from catalyst.political_tracker import get_ticker_political_exposure
                pol_val = get_ticker_political_exposure(ticker, political_pulse.get("events", []))
                pol_score = max(0, min(100, pol_val))
                risk = political_pulse.get("risk_level", "LOW")
                pol_label = f"{risk} — {political_pulse.get('dominant_theme', 'none')}"
        except Exception:
            pass

        # War exposure
        war_score = 50
        war_label = ""
        try:
            if war_watch:
                from catalyst.war_tracker import get_ticker_war_exposure
                war_val = get_ticker_war_exposure(ticker, war_watch)
                war_score = max(0, min(100, war_val))
                war_label = war_watch.get("risk_level", "CALM")
        except Exception:
            pass

        # Influencer exposure
        inf_score = 50
        inf_label = ""
        try:
            if influencer_pulse:
                from catalyst.influencer_tracker import get_ticker_influencer_exposure
                inf_val = get_ticker_influencer_exposure(ticker, influencer_pulse)
                inf_score = max(0, min(100, inf_val))
                if influencer_pulse.get("active_influencers"):
                    names = [i.get("name", "") for i in influencer_pulse["active_influencers"][:3]]
                    inf_label = ", ".join(n for n in names if n)
        except Exception:
            pass

        # Social narrative
        narrative_parts = []
        try:
            from catalyst.social_intel import get_social_narrative
            narrative = get_social_narrative(ticker)
            if narrative:
                narrative_parts.append(narrative)
        except Exception:
            pass

        # Weighted social composite
        social_score = (
            0.30 * st_score +
            0.25 * pol_score +
            0.20 * war_score +
            0.25 * inf_score
        )

        social_info = {
            "political_exposure": pol_label,
            "war_exposure": war_label,
            "influencer_signal": inf_label,
            "social_narrative": " | ".join(narrative_parts) if narrative_parts else "",
        }

    except Exception:
        pass

    return round(social_score, 1), social_info


def _fetch_social_intel() -> dict:
    """Fetch global social intelligence data."""
    try:
        from catalyst.social_intel import get_social_intel
        return get_social_intel() or {}
    except Exception:
        return {}


def _fetch_political_pulse() -> dict:
    """Fetch political pulse data."""
    try:
        from catalyst.political_tracker import get_political_pulse
        return get_political_pulse() or {}
    except Exception:
        return {}


def _fetch_war_watch() -> dict:
    """Fetch war/conflict watch data."""
    try:
        from catalyst.war_tracker import get_war_watch
        return get_war_watch() or {}
    except Exception:
        return {}


def _fetch_influencer_pulse() -> dict:
    """Fetch influencer pulse data."""
    try:
        from catalyst.influencer_tracker import get_influencer_pulse
        return get_influencer_pulse() or {}
    except Exception:
        return {}


def _get_levels(ticker, daily, intraday) -> dict:
    try:
        from levels.support_resistance import get_all_levels
        return get_all_levels(ticker, daily, intraday)
    except Exception:
        return {"resistance": [], "support": [], "nearest_resistance": None, "nearest_support": None}


def _get_targets(price, levels_data, atr) -> dict:
    try:
        from levels.price_target import compute_price_targets
        return compute_price_targets(price, levels_data, atr=atr)
    except Exception:
        return {
            "conservative_target": price * 1.03,
            "aggressive_target": price * 1.05,
            "stop_price": price * 0.97,
            "risk_reward": 1.5,
            "where_headed": "Targets based on ATR",
        }

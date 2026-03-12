"""
Stock forecast card — mini price chart with prediction overlay.
Shows recent price action + forecast direction + key levels.
"""
import streamlit as st
from dashboard.theme import COLORS


def _build_chart_svg(prices: list, forecast: list = None, width: int = 280, height: int = 100) -> str:
    """Build an SVG area chart with optional forecast overlay."""
    if not prices or len(prices) < 2:
        return ""

    all_vals = prices + (forecast or [])
    mn, mx = min(all_vals), max(all_vals)
    rng = mx - mn if mx != mn else 1
    pad = 4

    # Price line points
    total_pts = len(prices) + len(forecast or [])
    points = []
    for i, v in enumerate(prices):
        x = i / (total_pts - 1) * width
        y = height - ((v - mn) / rng * (height - 2 * pad) + pad)
        points.append(f"{x:.1f},{y:.1f}")

    price_color = COLORS["success"] if prices[-1] >= prices[0] else COLORS["danger"]
    polyline = " ".join(points)

    # Fill area
    first_x = points[0].split(",")[0]
    last_x = points[-1].split(",")[0]
    fill_points = polyline + f" {last_x},{height} {first_x},{height}"
    fill_color = price_color.replace(")", ",0.06)").replace("rgb", "rgba") if "rgb" in price_color else f"rgba({int(price_color[1:3],16)},{int(price_color[3:5],16)},{int(price_color[5:7],16)},0.06)"

    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polygon points="{fill_points}" fill="{fill_color}"/>'
        f'<polyline points="{polyline}" fill="none" stroke="{price_color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    )

    # Forecast overlay (dashed)
    if forecast and len(forecast) >= 1:
        fc_points = []
        start_idx = len(prices) - 1
        # Connect from last real price
        last_real_x = float(points[-1].split(",")[0])
        last_real_y = float(points[-1].split(",")[1])
        fc_points.append(f"{last_real_x:.1f},{last_real_y:.1f}")

        fc_color = COLORS["success"] if forecast[-1] >= prices[-1] else COLORS["danger"]

        for j, v in enumerate(forecast):
            idx = start_idx + j + 1
            x = idx / (total_pts - 1) * width
            y = height - ((v - mn) / rng * (height - 2 * pad) + pad)
            fc_points.append(f"{x:.1f},{y:.1f}")

        fc_polyline = " ".join(fc_points)
        svg += (
            f'<polyline points="{fc_polyline}" fill="none" stroke="{fc_color}" '
            f'stroke-width="2" stroke-dasharray="6,4" stroke-linecap="round" stroke-linejoin="round" opacity="0.7"/>'
        )

        # Forecast endpoint dot
        last_fc = fc_points[-1]
        fx, fy = last_fc.split(",")
        svg += f'<circle cx="{fx}" cy="{fy}" r="4" fill="{fc_color}" opacity="0.8"/>'

    svg += '</svg>'
    return svg


def forecast_card(ticker: str, price: float, pct_change: float, signal: str,
                  confidence: int, action: str, prices: list = None,
                  forecast_prices: list = None, support: float = None,
                  resistance: float = None, target: float = None):
    """Render a forecast card with mini chart + signal + action.

    Args:
        ticker: Stock symbol
        price: Current price
        pct_change: Today's % change
        signal: BUY/HOLD/SELL
        confidence: 0-100
        action: Recommended action text
        prices: Recent price history for chart
        forecast_prices: Predicted future prices
        support: Support level
        resistance: Resistance level
        target: Price target
    """
    # Signal badge colors
    if signal == "BUY":
        sig_color = COLORS["success"]
        sig_bg = f"rgba({int(COLORS['success'][1:3],16)},{int(COLORS['success'][3:5],16)},{int(COLORS['success'][5:7],16)},0.12)"
    elif signal == "SELL":
        sig_color = COLORS["danger"]
        sig_bg = f"rgba({int(COLORS['danger'][1:3],16)},{int(COLORS['danger'][3:5],16)},{int(COLORS['danger'][5:7],16)},0.12)"
    else:
        sig_color = COLORS["text_muted"]
        sig_bg = f"rgba({int(COLORS['text_muted'][1:3],16)},{int(COLORS['text_muted'][3:5],16)},{int(COLORS['text_muted'][5:7],16)},0.12)"

    # Change color
    chg_color = COLORS["success"] if pct_change >= 0 else COLORS["danger"]
    arrow = "+" if pct_change >= 0 else ""

    # Chart SVG
    chart_html = ""
    if prices:
        chart_html = (
            f'<div style="margin:16px 0 12px 0;">'
            f'{_build_chart_svg(prices, forecast_prices, width=280, height=80)}'
            f'</div>'
        )

    # Levels row
    levels_html = ""
    level_items = []
    if support:
        level_items.append(f'<span style="font-size:11px;color:{COLORS["text_dim"]};">S: ${support:.2f}</span>')
    if resistance:
        level_items.append(f'<span style="font-size:11px;color:{COLORS["text_dim"]};">R: ${resistance:.2f}</span>')
    if target:
        tgt_color = COLORS["success"] if target > price else COLORS["danger"]
        level_items.append(f'<span style="font-size:11px;color:{tgt_color};">T: ${target:.2f}</span>')
    if level_items:
        levels_html = f'<div style="display:flex;gap:12px;margin-top:6px;">{"".join(level_items)}</div>'

    # Confidence bar
    conf_color = COLORS["success"] if confidence >= 70 else (COLORS["warning"] if confidence >= 50 else COLORS["text_muted"])

    html = (
        f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
        f'border-radius:20px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);'
        f'transition:transform 0.15s ease;">'

        # Header row: ticker + signal + price
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div>'
        f'<div style="font-size:18px;font-weight:600;color:{COLORS["text"]};letter-spacing:-0.01em;">{ticker}</div>'
        f'<div style="font-size:13px;color:{chg_color};margin-top:2px;">${price:.2f} ({arrow}{pct_change:.1f}%)</div>'
        f'</div>'
        f'<span style="background:{sig_bg};color:{sig_color};padding:4px 14px;border-radius:980px;'
        f'font-size:12px;font-weight:700;letter-spacing:0.02em;">{signal}</span>'
        f'</div>'

        # Chart
        f'{chart_html}'

        # Action
        f'<div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.4;'
        f'margin-top:8px;">{action}</div>'

        # Confidence bar
        f'<div style="margin-top:10px;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
        f'<span style="font-size:10px;color:{COLORS["text_dim"]};text-transform:uppercase;letter-spacing:0.05em;">Confidence</span>'
        f'<span style="font-size:10px;color:{conf_color};font-weight:600;">{confidence}%</span>'
        f'</div>'
        f'<div style="width:100%;height:4px;border-radius:2px;background:{COLORS["border"]};">'
        f'<div style="width:{confidence}%;height:100%;border-radius:2px;background:{conf_color};'
        f'transition:width 0.3s ease;"></div>'
        f'</div>'
        f'</div>'

        # Levels
        f'{levels_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def forecast_section(scored_tickers: list, max_cards: int = 6):
    """Render a grid of forecast cards for top tickers.

    Args:
        scored_tickers: List of ScoredTicker objects (pre-sorted by score)
        max_cards: Max number of cards to show
    """
    if not scored_tickers:
        return

    try:
        from signals.recommendation import get_recommendation
    except ImportError:
        return

    try:
        from data.fetchers.yfinance_fetcher import get_daily_ohlcv
    except ImportError:
        get_daily_ohlcv = None

    top = scored_tickers[:max_cards]

    # Render in 3-column grid
    for row_start in range(0, len(top), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            idx = row_start + j
            if idx >= len(top):
                break
            pick = top[idx]
            rec = get_recommendation(pick)

            # Get price history for chart
            prices = None
            forecast = None
            if get_daily_ohlcv:
                try:
                    df = get_daily_ohlcv(pick.ticker)
                    if df is not None and len(df) >= 10:
                        prices = df["Close"].tail(30).tolist()
                        # Simple forecast: linear extrapolation from trend
                        if len(prices) >= 5:
                            recent = prices[-5:]
                            slope = (recent[-1] - recent[0]) / len(recent)
                            # Damped continuation
                            forecast = [prices[-1] + slope * (i + 1) * 0.7 for i in range(5)]
                except Exception:
                    pass

            with col:
                forecast_card(
                    ticker=pick.ticker,
                    price=pick.price,
                    pct_change=pick.pct_change,
                    signal=rec["signal"],
                    confidence=rec["confidence"],
                    action=rec.get("action", "Monitor"),
                    prices=prices,
                    forecast_prices=forecast,
                    support=getattr(pick, "support", None),
                    resistance=getattr(pick, "resistance", None),
                    target=getattr(pick, "target", None),
                )

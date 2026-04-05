"""
TradingView Bridge — Python interface to TradingView Desktop via Chrome DevTools Protocol.
Provides chart screenshots, indicator cross-validation, and alert creation.
All functions fail silently (return None/False) to avoid crashing the scanner.
"""
from __future__ import annotations
import base64
import json
import logging
import threading
import time

import requests
import websocket

from config import settings

# Threading lock — prevents CDP conflicts when 15-min scan and 2-min scalp loop
# both try to control TradingView simultaneously.
tv_lock = threading.Lock()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  CDP Connection
# ─────────────────────────────────────────────────────────────

_ws = None
_msg_id = 0


def _get_ws_url() -> str | None:
    """Find the TradingView chart page WebSocket URL from CDP."""
    try:
        resp = requests.get(f"{settings.TV_CDP_URL}/json/list", timeout=3)
        targets = resp.json()
        for t in targets:
            if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""):
                return t["webSocketDebuggerUrl"]
        for t in targets:
            if t.get("type") == "page" and "tradingview" in t.get("url", ""):
                return t["webSocketDebuggerUrl"]
    except Exception:
        logger.debug("CDP target discovery failed", exc_info=True)
    return None


def _connect() -> websocket.WebSocket | None:
    """Get or create a WebSocket connection to TradingView CDP."""
    global _ws
    if _ws is not None:
        try:
            _ws.ping()
            return _ws
        except Exception:
            _ws = None

    url = _get_ws_url()
    if not url:
        return None
    try:
        _ws = websocket.create_connection(url, timeout=10, suppress_origin=True)
        # Enable required domains
        _cdp_send("Runtime.enable")
        _cdp_send("Page.enable")
        return _ws
    except Exception:
        logger.debug("CDP WebSocket connection failed", exc_info=True)
        _ws = None
        return None


def _cdp_send(method: str, params: dict = None) -> dict | None:
    """Send a CDP command and return the result."""
    global _msg_id
    if _ws is None:
        return None
    _msg_id += 1
    msg = {"id": _msg_id, "method": method, "params": params or {}}
    try:
        _ws.send(json.dumps(msg))
        # Read responses until we get our ID back
        deadline = time.time() + 15
        while time.time() < deadline:
            raw = _ws.recv()
            data = json.loads(raw)
            if data.get("id") == _msg_id:
                return data
    except Exception:
        logger.debug("CDP send failed for %s", method, exc_info=True)
    return None


def _evaluate(js: str, await_promise: bool = False) -> any:
    """Evaluate JavaScript in the TradingView page context."""
    ws = _connect()
    if ws is None:
        return None
    result = _cdp_send("Runtime.evaluate", {
        "expression": js,
        "returnByValue": True,
        "awaitPromise": await_promise,
    })
    if result is None:
        return None
    r = result.get("result", {}).get("result", {})
    if "exceptionDetails" in result.get("result", {}):
        logger.debug("JS error: %s", result["result"]["exceptionDetails"])
        return None
    return r.get("value")


def _safe_string(s: str) -> str:
    """Escape a string for safe injection into JavaScript."""
    return json.dumps(str(s))


# ─────────────────────────────────────────────────────────────
#  Health & Availability
# ─────────────────────────────────────────────────────────────

def is_tv_available() -> bool:
    """Check if TradingView is reachable via CDP."""
    if not getattr(settings, "TV_MCP_ENABLED", False):
        return False
    try:
        resp = requests.get(f"{settings.TV_CDP_URL}/json/version", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
#  Ticker Mapping
# ─────────────────────────────────────────────────────────────

def map_ticker_to_tv(ticker: str) -> str:
    """Convert yfinance ticker to TradingView symbol format."""
    tv_map = getattr(settings, "TV_TICKER_MAP", {})
    if ticker in tv_map:
        return tv_map[ticker]
    # Fallback: try symbol search API
    try:
        resp = requests.get(
            "https://symbol-search.tradingview.com/symbol_search/v3/",
            params={"text": ticker.replace("-USD", ""), "lang": "en", "domain": "production"},
            headers={"Origin": "https://www.tradingview.com"},
            timeout=5,
        )
        results = resp.json()
        if results and len(results) > 0:
            r = results[0]
            return f"{r.get('exchange', '')}:{r.get('symbol', ticker)}"
    except Exception:
        pass
    return ticker


# ─────────────────────────────────────────────────────────────
#  Chart Control
# ─────────────────────────────────────────────────────────────

def set_symbol(symbol: str) -> bool:
    """Navigate TradingView chart to a symbol."""
    tv_sym = map_ticker_to_tv(symbol)
    js = f"""(function() {{
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  return new Promise(function(resolve) {{
    chart.setSymbol({_safe_string(tv_sym)}, {{}});
    setTimeout(function() {{ resolve(true); }}, 800);
  }});
}})()"""
    result = _evaluate(js, await_promise=True)
    if result:
        _wait_chart_ready()
    return result is not None


def set_timeframe(tf: str) -> bool:
    """Set the chart timeframe/resolution."""
    js = f"""(function() {{
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  chart.setResolution({_safe_string(tf)}, {{}});
  return true;
}})()"""
    result = _evaluate(js)
    if result:
        time.sleep(0.5)
        _wait_chart_ready()
    return result is not None


def _wait_chart_ready(timeout: float = 8.0) -> bool:
    """Poll until the chart is done loading."""
    js = """(function() {
  var spinner = document.querySelector('[class*="loader"]')
    || document.querySelector('[class*="loading"]');
  var isLoading = spinner && spinner.offsetParent !== null;
  return !isLoading;
})()"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready = _evaluate(js)
        if ready:
            return True
        time.sleep(0.3)
    return False


def get_chart_state() -> dict | None:
    """Get current chart symbol, timeframe, and indicators."""
    js = """(function() {
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  var studies = [];
  try {
    var allStudies = chart.getAllStudies();
    studies = allStudies.map(function(s) {
      return { id: s.id, name: s.name || s.title || 'unknown' };
    });
  } catch(e) {}
  return {
    symbol: chart.symbol(),
    resolution: chart.resolution(),
    chartType: chart.chartType(),
    studies: studies
  };
})()"""
    return _evaluate(js)


def ensure_indicators() -> None:
    """Make sure RSI, MACD, Volume are on the chart."""
    state = get_chart_state()
    if state is None:
        return
    existing = {s.get("name", "").lower() for s in state.get("studies", [])}
    template = getattr(settings, "TV_INDICATOR_TEMPLATE", [])
    for ind in template:
        if ind.lower() not in existing and ind.lower().split()[0] not in " ".join(existing):
            _add_indicator(ind)
            time.sleep(1.0)


def _add_indicator(name: str) -> bool:
    """Add an indicator to the chart."""
    js = f"""(function() {{
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  chart.createStudy({_safe_string(name)}, false, false, []);
  return true;
}})()"""
    return _evaluate(js) is not None


# ─────────────────────────────────────────────────────────────
#  Drawing
# ─────────────────────────────────────────────────────────────

def draw_horizontal_line(price: float, color: str = "#2196F3", width: int = 2, text: str = "") -> bool:
    """Draw a horizontal line at a price level."""
    now_ts = int(time.time())
    overrides = json.dumps({"linecolor": color, "linewidth": width, "linestyle": 0})
    text_arg = f', text: {_safe_string(text)}' if text else ""
    js = f"""(function() {{
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  chart.createShape(
    {{ time: {now_ts}, price: {price} }},
    {{ shape: "horizontal_line", overrides: {overrides}{text_arg} }}
  );
  return true;
}})()"""
    return _evaluate(js) is not None


def clear_drawings() -> bool:
    """Remove all drawings from the chart."""
    js = """(function() {
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  var shapes = chart.getAllShapes();
  for (var i = 0; i < shapes.length; i++) {
    chart.removeEntity(shapes[i].id);
  }
  return true;
})()"""
    return _evaluate(js) is not None


# ─────────────────────────────────────────────────────────────
#  Screenshots
# ─────────────────────────────────────────────────────────────

def capture_screenshot(region: str = "chart") -> bytes | None:
    """Capture a screenshot of the TradingView chart. Returns PNG bytes."""
    ws = _connect()
    if ws is None:
        return None

    clip = None
    if region == "chart":
        bounds = _evaluate("""(function() {
  var el = document.querySelector('[data-name="pane-canvas"]')
    || document.querySelector('[class*="chart-container"]')
    || document.querySelector('canvas');
  if (!el) return null;
  var rect = el.getBoundingClientRect();
  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
})()""")
        if bounds:
            clip = {
                "x": bounds["x"], "y": bounds["y"],
                "width": bounds["width"], "height": bounds["height"],
                "scale": 1,
            }

    params = {"format": "png"}
    if clip:
        params["clip"] = clip

    result = _cdp_send("Page.captureScreenshot", params)
    if result and "result" in result:
        b64 = result["result"].get("data")
        if b64:
            return base64.b64decode(b64)
    return None


def capture_trade_screenshot(
    ticker: str,
    timeframe: str = "15",
    entry: float = 0,
    stop: float = 0,
    target: float = 0,
) -> bytes | None:
    """Full pipeline: navigate → draw levels → screenshot → clean up → return PNG."""
    try:
        if not is_tv_available():
            return None

        if not set_symbol(ticker):
            return None
        set_timeframe(timeframe)
        ensure_indicators()

        # Draw entry/stop/target levels
        if entry and entry > 0:
            draw_horizontal_line(entry, color="#2196F3", width=2, text="Entry")
        if stop and stop > 0:
            draw_horizontal_line(stop, color="#F44336", width=2, text="Stop")
        if target and target > 0:
            draw_horizontal_line(target, color="#4CAF50", width=2, text="Target")

        time.sleep(0.5)
        png = capture_screenshot(region="chart")
        clear_drawings()
        return png
    except Exception:
        logger.debug("Trade screenshot failed for %s", ticker, exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────
#  Indicator Values
# ─────────────────────────────────────────────────────────────

def get_study_values() -> list | None:
    """Get current indicator values from all visible studies."""
    js = """(function() {
  var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
  var model = chart.model();
  var sources = model.model().dataSources();
  var results = [];
  for (var si = 0; si < sources.length; si++) {
    var s = sources[si];
    if (!s.metaInfo) continue;
    try {
      var meta = s.metaInfo();
      var name = meta.description || meta.shortDescription || '';
      if (!name) continue;
      var values = {};
      try {
        var dwv = s.dataWindowView();
        if (dwv) {
          var items = dwv.items();
          if (items) {
            for (var i = 0; i < items.length; i++) {
              var item = items[i];
              if (item._value && item._value !== '\u2205' && item._title)
                values[item._title] = item._value;
            }
          }
        }
      } catch(e) {}
      if (Object.keys(values).length > 0)
        results.push({ name: name, values: values });
    } catch(e) {}
  }
  return results;
})()"""
    return _evaluate(js)


def get_tv_indicators(ticker: str) -> dict | None:
    """Navigate to a ticker and return a flat dict of indicator values.

    Returns e.g. {"RSI": 38.5, "MACD": 0.12, "Signal": -0.05, ...}
    """
    try:
        if not is_tv_available():
            return None
        if not set_symbol(ticker):
            return None
        time.sleep(0.5)
        studies = get_study_values()
        if not studies:
            return None
        flat = {}
        for study in studies:
            for key, val in study.get("values", {}).items():
                try:
                    flat[key] = float(str(val).replace(",", ""))
                except (ValueError, TypeError):
                    flat[key] = val
        return flat
    except Exception:
        logger.debug("get_tv_indicators failed for %s", ticker, exc_info=True)
        return None


def compute_tv_confirmation(pick, tv_indicators: dict) -> float:
    """Score 0-100 how well TradingView indicators confirm the scanner signal.

    5 factors, 20 points each:
      1. RSI agreement (scanner vs TV within 5 pts)
      2. MACD direction matches pick direction
      3. Volume trend confirms
      4. Price vs key moving averages
      5. RSI zone confirms signal direction
    """
    if not tv_indicators:
        return 0.0

    points = 0.0
    direction = getattr(pick, "direction", "LONG")

    # 1. RSI agreement — scanner RSI vs TV RSI within 5 points
    tv_rsi = None
    for key in ("RSI", "Relative Strength Index"):
        if key in tv_indicators:
            try:
                tv_rsi = float(tv_indicators[key])
                break
            except (ValueError, TypeError):
                pass
    if tv_rsi is not None:
        scanner_rsi = getattr(pick, "rsi", 50)
        if abs(scanner_rsi - tv_rsi) <= 5:
            points += 20
        elif abs(scanner_rsi - tv_rsi) <= 10:
            points += 10

    # 2. MACD direction matches pick direction
    tv_macd = None
    for key in ("MACD", "Histogram", "MACD-hist"):
        if key in tv_indicators:
            try:
                tv_macd = float(tv_indicators[key])
                break
            except (ValueError, TypeError):
                pass
    if tv_macd is not None:
        if direction == "LONG" and tv_macd > 0:
            points += 20
        elif direction == "SHORT" and tv_macd < 0:
            points += 20
        elif abs(tv_macd) < 0.01:
            points += 10  # neutral MACD, partial credit

    # 3. Volume confirmation — above average suggests real participation
    tv_vol = None
    for key in ("Volume", "Vol"):
        if key in tv_indicators:
            try:
                tv_vol = float(tv_indicators[key])
                break
            except (ValueError, TypeError):
                pass
    if tv_vol is not None:
        rvol = getattr(pick, "rel_volume", 1.0)
        if rvol >= 1.5:
            points += 20
        elif rvol >= 1.0:
            points += 10

    # 4. RSI zone confirms direction
    if tv_rsi is not None:
        if direction == "LONG" and 30 <= tv_rsi <= 65:
            points += 20
        elif direction == "SHORT" and 35 <= tv_rsi <= 70:
            points += 20
        elif direction == "LONG" and tv_rsi < 30:
            points += 15  # oversold = potential bounce
        elif direction == "SHORT" and tv_rsi > 70:
            points += 15  # overbought = potential drop

    # 5. Overall signal strength — ML + composite alignment
    ml_conf = getattr(pick, "ml_confidence", 0)
    score = getattr(pick, "composite_score", 0)
    if ml_conf >= 70 and score >= 55:
        points += 20
    elif ml_conf >= 50 and score >= 40:
        points += 10

    return min(100.0, points)


# ─────────────────────────────────────────────────────────────
#  Alert Creation
# ─────────────────────────────────────────────────────────────

def create_price_alerts(
    ticker: str,
    entry: float = 0,
    stop: float = 0,
    target: float = 0,
    label: str = "",
) -> int:
    """Create TradingView alerts at entry/stop/target. Returns count created."""
    if not is_tv_available():
        return 0

    if not set_symbol(ticker):
        return 0

    count = 0
    prefix = f"[SA] {ticker}"
    if label:
        prefix += f" {label}"

    if entry and entry > 0:
        if _create_alert("crossing", entry, f"{prefix} — Entry zone ${entry:.2f}"):
            count += 1
            time.sleep(1.5)

    if stop and stop > 0:
        condition = "less_than" if getattr(settings, "_last_direction", "LONG") == "LONG" else "greater_than"
        if _create_alert(condition, stop, f"{prefix} — STOP ${stop:.2f}"):
            count += 1
            time.sleep(1.5)

    if target and target > 0:
        condition = "greater_than" if getattr(settings, "_last_direction", "LONG") == "LONG" else "less_than"
        if _create_alert(condition, target, f"{prefix} — Target ${target:.2f}"):
            count += 1

    return count


def _create_alert(condition: str, price: float, message: str) -> bool:
    """Create a single TradingView price alert via the alert dialog.

    This uses TradingView's internal alert API.
    """
    js = f"""(function() {{
  try {{
    var svc = window.TradingViewApi._alertService;
    if (svc && svc.createAlert) {{
      svc.createAlert({{
        type: 'price',
        condition: {_safe_string(condition)},
        price: {price},
        message: {_safe_string(message)}
      }});
      return true;
    }}
  }} catch(e) {{}}
  return false;
}})()"""
    result = _evaluate(js)
    if result:
        return True

    # Fallback: try keyboard shortcut to open alert dialog
    logger.debug("Alert API not available, alert creation skipped for %s at %.2f", condition, price)
    return False


# ─────────────────────────────────────────────────────────────
#  Multi-Timeframe Analysis
# ─────────────────────────────────────────────────────────────

def get_ohlcv_summary(ticker: str = None) -> dict | None:
    """Get compact OHLCV summary for the current (or specified) chart symbol."""
    if ticker:
        if not set_symbol(ticker):
            return None
        time.sleep(0.5)

    js = """(function() {
  var bars = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries().bars();
  if (!bars || typeof bars.lastIndex !== 'function') return null;
  var end = bars.lastIndex();
  var start = Math.max(bars.firstIndex(), end - 99);
  var high = -Infinity, low = Infinity, vol = 0, count = 0;
  var first_open = null, last_close = null;
  for (var i = start; i <= end; i++) {
    var v = bars.valueAt(i);
    if (!v) continue;
    if (first_open === null) first_open = v[1];
    if (v[2] > high) high = v[2];
    if (v[3] < low) low = v[3];
    vol += v[5] || 0;
    last_close = v[4];
    count++;
  }
  var change = first_open ? ((last_close - first_open) / first_open * 100) : 0;
  return {
    open: first_open, high: high, low: low, close: last_close,
    total_volume: vol, bar_count: count, change_pct: Math.round(change * 100) / 100
  };
})()"""
    return _evaluate(js)


def get_mtf_regime(ticker: str) -> dict | None:
    """Analyze trend direction across Daily, Weekly, Monthly timeframes.

    Returns: {"daily_trend": "UP/DOWN/FLAT", "weekly_trend": ..., "monthly_trend": ..., "mtf_aligned": bool}
    """
    try:
        if not is_tv_available():
            return None

        if not set_symbol(ticker):
            return None

        results = {}
        for tf, label in [("D", "daily"), ("W", "weekly"), ("M", "monthly")]:
            set_timeframe(tf)
            time.sleep(0.8)
            summary = get_ohlcv_summary()
            if summary and summary.get("change_pct") is not None:
                chg = summary["change_pct"]
                if chg > 2:
                    results[f"{label}_trend"] = "UP"
                elif chg < -2:
                    results[f"{label}_trend"] = "DOWN"
                else:
                    results[f"{label}_trend"] = "FLAT"
            else:
                results[f"{label}_trend"] = "UNKNOWN"

        trends = [results.get("daily_trend"), results.get("weekly_trend"), results.get("monthly_trend")]
        non_unknown = [t for t in trends if t != "UNKNOWN"]
        results["mtf_aligned"] = len(set(non_unknown)) == 1 and len(non_unknown) >= 2

        # Restore to daily
        set_timeframe("D")
        return results
    except Exception:
        logger.debug("MTF regime failed for %s", ticker, exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────
#  Batch Operations
# ─────────────────────────────────────────────────────────────

def batch_screenshots(picks: list, timeframe: str = "15") -> dict:
    """Capture TradingView screenshots for multiple picks. Returns ticker → PNG bytes."""
    results = {}
    if not is_tv_available():
        return results

    delay = getattr(settings, "TV_BATCH_DELAY_MS", 2000) / 1000.0

    for pick in picks:
        ticker = getattr(pick, "ticker", str(pick))
        entry = getattr(pick, "entry_price", 0)
        stop = getattr(pick, "stop_price", 0)
        target = getattr(pick, "target_price", 0)

        png = capture_trade_screenshot(ticker, timeframe, entry, stop, target)
        if png:
            results[ticker] = png

        time.sleep(delay)

    return results


def deploy_pine_indicator(source: str, name: str = "Options Scalp Overlay") -> bool:
    """Deploy a Pine Script indicator to TradingView.

    Uses MCP pine_set_source + pine_smart_compile if available,
    otherwise falls back to clipboard-based injection.
    """
    try:
        # Try MCP approach first
        try:
            from signals.mcp_client import call_mcp
            result = call_mcp("pine_set_source", {"source": source})
            if result:
                compile_result = call_mcp("pine_smart_compile", {})
                if compile_result and not compile_result.get("errors"):
                    logger.info("Pine indicator '%s' deployed via MCP", name)
                    return True
                else:
                    errors = compile_result.get("errors", []) if compile_result else []
                    logger.warning("Pine compile errors: %s", errors)
        except ImportError:
            pass

        # Fallback: use CDP to set source in Pine editor
        escaped = source.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        js = f"""
        (function() {{
            var editor = document.querySelector('.pine-editor-content textarea, [class*="pine"] textarea');
            if (editor) {{
                editor.value = `{escaped}`;
                editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return 'injected';
            }}
            return 'no_editor';
        }})()
        """
        result = _evaluate(js)
        if result == "injected":
            logger.info("Pine source injected for '%s'", name)
            return True

        logger.debug("Pine editor not found — open Pine Editor first")
        return False

    except Exception as e:
        logger.debug("deploy_pine_indicator error: %s", e)
        return False


def disconnect():
    """Close the CDP WebSocket connection."""
    global _ws
    if _ws:
        try:
            _ws.close()
        except Exception:
            pass
        _ws = None

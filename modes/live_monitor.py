"""
Live monitoring mode — continuous loop with periodic refresh and alerts.
Runs the morning scan pipeline in a loop with spark/dip detection.
"""
import time
import datetime
import threading
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box
from config import settings
from output.formatter import console, print_banner
from signals.alert_engine import should_alert, fire_alert, format_alert_line


def run_live_monitor(top_n: int = None, tickers: str = None):
    """Run the live monitoring dashboard."""
    top_n = top_n or 10

    print_banner("LIVE")

    # Determine universe
    if tickers:
        universe = [t.strip().upper() for t in tickers.split(",")]
    else:
        universe = settings.TICKER_UNIVERSE

    console.print(f"  Monitoring {len(universe)} tickers, refreshing every {settings.LIVE_POLL_INTERVAL}s")
    console.print(f"  Press Ctrl+C to stop\n")

    # State
    scored_tickers = []
    alerts = []
    cycle = 0
    political_pulse = {}
    war_watch = {}
    influencer_pulse = {}

    # Optional: start Finnhub WebSocket in background
    ws_thread = _start_websocket(universe[:settings.FINNHUB_WS_MAX_SYMBOLS])

    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while True:
                cycle += 1
                now = datetime.datetime.now()

                # Check market hours (roughly 9:30 AM - 4:00 PM ET)
                hour = now.hour
                is_market_hours = 9 <= hour <= 16

                # Refresh social intel periodically
                if cycle % 5 == 1:
                    try:
                        from catalyst.political_tracker import get_political_pulse
                        political_pulse = get_political_pulse() or {}
                    except Exception:
                        pass
                    try:
                        from catalyst.war_tracker import get_war_watch
                        war_watch = get_war_watch() or {}
                    except Exception:
                        pass
                    try:
                        from catalyst.influencer_tracker import get_influencer_pulse
                        influencer_pulse = get_influencer_pulse() or {}
                    except Exception:
                        pass

                # Run analysis cycle
                try:
                    scored_tickers = _run_scan_cycle(universe, cycle, political_pulse, war_watch, influencer_pulse)
                except Exception as e:
                    console.print(f"  [red]Scan error: {e}[/]")

                # Check for spark/dip signals
                new_alerts = _check_signals(scored_tickers)
                alerts = (new_alerts + alerts)[:50]  # keep last 50

                # Update display
                display = _build_dashboard(scored_tickers[:top_n], alerts[:10], cycle, is_market_hours,
                                          political_pulse, war_watch, influencer_pulse)
                live.update(display)

                # Sleep until next cycle
                time.sleep(settings.LIVE_POLL_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n  [yellow]Live monitor stopped.[/]\n")
    finally:
        pass


def _run_scan_cycle(universe: list, cycle: int,
                    political_pulse: dict = None, war_watch: dict = None,
                    influencer_pulse: dict = None) -> list:
    """Run abbreviated scan for live mode."""
    from modes.morning_scan import _analyze_ticker, _fetch_reddit

    reddit_data = _fetch_reddit() if cycle % 15 == 1 else {}  # refresh reddit every 15 cycles

    results = []
    for ticker in universe:
        try:
            result = _analyze_ticker(ticker, "NEUTRAL", reddit_data, {},
                                     political_pulse, war_watch, influencer_pulse)
            if result:
                results.append(result)
        except Exception:
            continue

    results.sort(key=lambda x: x.composite_score, reverse=True)
    return results


def _check_signals(scored_tickers: list) -> list:
    """Check for new spark/dip signals."""
    new_alerts = []

    for pick in scored_tickers[:20]:
        # Spark detection
        if pick.kinematic_phase == "IGNITION" and pick.composite_score >= 60:
            if should_alert(pick.ticker, "SPARK"):
                alert = fire_alert(pick.ticker, "SPARK", {
                    "confidence": pick.composite_score,
                    "price_at_spark": pick.price,
                    "explanation": [
                        f"Score {pick.composite_score:.0f}",
                        f"Phase: {pick.kinematic_phase}",
                        pick.why_moving or "Momentum ignition",
                    ],
                })
                new_alerts.append(alert)

        # Dip detection (low z-score + mean reverting regime)
        if pick.regime in ("CLEAN_REVERSION", "MEAN_REVERTING") and pick.pct_change < -2:
            if should_alert(pick.ticker, "DIP"):
                alert = fire_alert(pick.ticker, "DIP", {
                    "confidence": pick.composite_score,
                    "price": pick.price,
                    "explanation": [
                        f"Score {pick.composite_score:.0f}",
                        f"Regime: {pick.regime}",
                        f"Change: {pick.pct_change:+.1f}%",
                    ],
                })
                new_alerts.append(alert)

    return new_alerts


def _build_dashboard(top_picks: list, alerts: list, cycle: int, is_market: bool,
                     political_pulse: dict = None, war_watch: dict = None,
                     influencer_pulse: dict = None) -> Panel:
    """Build the Rich dashboard panel."""
    now = datetime.datetime.now().strftime("%I:%M:%S %p")
    market_str = "[green]MARKET OPEN[/]" if is_market else "[red]MARKET CLOSED[/]"

    # Ticker table
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", expand=True)
    table.add_column("TICKER", style="bold", width=7)
    table.add_column("SCORE", justify="right", width=6)
    table.add_column("PRICE", justify="right", width=9)
    table.add_column("CHG%", justify="right", width=7)
    table.add_column("RVOL", justify="right", width=6)
    table.add_column("REGIME", width=14)
    table.add_column("PHASE", width=10)
    table.add_column("CATALYST", width=30, no_wrap=True)

    for pick in top_picks:
        score_style = "bold bright_green" if pick.composite_score >= 70 else ("green" if pick.composite_score >= 50 else "yellow")
        pct_style = "green" if pick.pct_change >= 0 else "red"
        chg = f"{'▲' if pick.pct_change >= 0 else '▼'}{abs(pick.pct_change):.1f}%"

        cat_summary = (pick.catalyst_summary or "—")[:30]

        table.add_row(
            pick.ticker,
            f"[{score_style}]{pick.composite_score:.0f}[/]",
            f"${pick.price:.2f}",
            f"[{pct_style}]{chg}[/]",
            f"{pick.rel_volume:.1f}x",
            pick.regime[:14],
            pick.kinematic_phase[:10],
            cat_summary,
        )

    # Social intel bar
    social_lines = []
    if political_pulse:
        pol_risk = political_pulse.get("risk_level", "LOW")
        pol_theme = political_pulse.get("dominant_theme", "—")
        social_lines.append(f"POL:{pol_risk}({pol_theme})")
    if war_watch:
        war_risk = war_watch.get("risk_level", "CALM")
        social_lines.append(f"WAR:{war_risk}")
    if influencer_pulse:
        consensus = influencer_pulse.get("fintwit_consensus", "QUIET")
        social_lines.append(f"VOICES:{consensus}")
        if influencer_pulse.get("elon_alert"):
            social_lines.append("[yellow]⚡ELON[/]")
    social_bar = " | ".join(social_lines) if social_lines else "[dim]Social intel loading...[/]"

    # Alerts section
    alert_lines = []
    for alert in alerts[:8]:
        alert_lines.append(format_alert_line(alert))
    alert_text = "\n".join(alert_lines) if alert_lines else "[dim]No alerts yet[/]"

    content = Text()
    content.append(f"SCALP ASSISTANT v3 [LIVE]  {now}  {market_str}  Cycle #{cycle}\n\n", style="bold")

    return Panel(
        f"[bold]SCALP ASSISTANT v3[/] [LIVE]  {now}  {market_str}  Cycle #{cycle}\n"
        f"[bold cyan]INTEL:[/] {social_bar}\n\n"
        f"{_table_to_string(table)}\n\n"
        f"[bold]ALERTS[/] (last 15 min):\n{alert_text}",
        border_style="bright_blue",
        padding=(1, 2),
    )


def _table_to_string(table: Table) -> str:
    """Render a Rich table to string."""
    from io import StringIO
    from rich.console import Console as TempConsole
    buf = StringIO()
    temp = TempConsole(file=buf, width=120)
    temp.print(table)
    return buf.getvalue()


def _start_websocket(symbols: list) -> threading.Thread | None:
    """Start Finnhub WebSocket in background thread (optional)."""
    try:
        import os
        key = os.environ.get("FINNHUB_KEY")
        if not key:
            return None

        from data.fetchers.finnhub_ws import FinnhubWebSocket
        ws = FinnhubWebSocket(key, symbols)
        thread = threading.Thread(target=ws.run, daemon=True)
        thread.start()
        return thread
    except Exception:
        return None

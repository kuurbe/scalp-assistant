"""
Rich-based terminal formatting for scan results and live dashboard.
"""
import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout
from rich import box

console = Console()


def print_banner(mode: str = "SCAN"):
    """Print the startup banner."""
    now = datetime.datetime.now()
    mode_str = "MORNING SCAN" if mode == "SCAN" else "LIVE MONITOR"
    console.print()
    console.print(Panel.fit(
        f"[bold bright_white]SCALP ASSISTANT v3.0[/] — [cyan]{mode_str}[/]\n"
        f"[dim]{now.strftime('%A, %B %d, %Y')}  |  {now.strftime('%I:%M %p')}[/]\n"
        f"[dim]Physics-Based Intelligent Scanner[/]",
        border_style="bright_blue",
        padding=(1, 4),
    ))


def print_macro_context(vix: float, vix_label: str, macro_regime: str, market_bias: str = ""):
    """Print market context bar."""
    console.print()
    console.print(f"  [bold]VIX:[/]    {vix}  →  {vix_label}")
    console.print(f"  [bold]MACRO:[/]  {macro_regime}")
    if market_bias:
        console.print(f"  [bold]BIAS:[/]   {market_bias}")
    console.print()


def print_scan_progress(scanned: int, total: int, active: int):
    """Print scan progress."""
    console.print(f"  Scanned {scanned}/{total} tickers — {active} active setups found")


def print_leaderboard(all_scored: list, top_n: int = 15):
    """Print the ranked leaderboard table."""
    table = Table(
        title="TICKER RANKINGS",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold bright_white",
        border_style="dim",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("TICKER", style="bold", width=7)
    table.add_column("PRICE", justify="right", width=9)
    table.add_column("CHG%", justify="right", width=7)
    table.add_column("RVOL", justify="right", width=6)
    table.add_column("RSI", justify="right", width=5)
    table.add_column("SCORE", justify="right", width=6)
    table.add_column("REGIME", width=12)
    table.add_column("PHASE", width=10)
    table.add_column("SOC", justify="right", width=4)
    table.add_column("", width=6)

    for i, pick in enumerate(all_scored[:top_n], 1):
        score = pick.composite_score
        if score >= 75:
            score_style = "bold bright_green"
        elif score >= 55:
            score_style = "green"
        elif score >= 40:
            score_style = "yellow"
        else:
            score_style = "red"

        pct_str = f"{'▲' if pick.pct_change >= 0 else '▼'}{abs(pick.pct_change):.1f}%"
        pct_style = "green" if pick.pct_change >= 0 else "red"

        regime_style = {
            "STRONG_TREND": "bold blue",
            "NOISY_TREND": "blue",
            "CLEAN_REVERSION": "bold magenta",
            "CHOPPY": "dim red",
        }.get(pick.regime, "dim")

        phase_style = {
            "IGNITION": "bold bright_red",
            "CRUISE": "green",
            "DECEL": "yellow",
            "REVERSAL": "red",
        }.get(pick.kinematic_phase, "dim")

        flag = " TOP" if i <= 5 else ""

        soc_score = getattr(pick, "social_score", 0)
        soc_style = "cyan" if soc_score >= 60 else ("dim" if soc_score < 40 else "white")

        table.add_row(
            str(i),
            pick.ticker,
            f"${pick.price:.2f}",
            f"[{pct_style}]{pct_str}[/]",
            f"{pick.rel_volume:.1f}x",
            f"{pick.rsi:.0f}",
            f"[{score_style}]{score:.0f}[/]",
            f"[{regime_style}]{pick.regime[:12]}[/]",
            f"[{phase_style}]{pick.kinematic_phase[:10]}[/]",
            f"[{soc_style}]{soc_score:.0f}[/]",
            f"[bold bright_yellow]{flag}[/]",
        )

    console.print()
    console.print(table)


def print_pick_detail(pick, rank: int):
    """Print detailed breakdown for a top pick."""
    dir_emoji = "CALL" if pick.direction == "LONG" else "PUT"
    score_bar = "█" * int(pick.composite_score / 10)

    detail = (
        f"[bold bright_white]#{rank} — {pick.ticker}[/] @ [bold]${pick.price:.2f}[/]  "
        f"({'[green]+' if pick.pct_change >= 0 else '[red]'}{pick.pct_change:+.1f}%[/])  "
        f"| Score [bold]{pick.composite_score:.0f}[/] {score_bar}\n"
        f"\n"
        f"  [bold]WHY MOVING:[/]    {pick.why_moving}\n"
        f"  [bold]WHERE HEADED:[/]  {pick.where_headed}\n"
        f"\n"
        f"  [bold]REGIME:[/]   {pick.regime} (H={pick.hurst:.2f} E={pick.entropy:.2f})\n"
        f"  [bold]PHASE:[/]    {pick.kinematic_phase}\n"
        f"  [bold]SIGNALS:[/]  Phys={pick.physics_score:.0f} Tech={pick.technical_score:.0f} "
        f"Cat={pick.catalyst_score:.0f} Stat={pick.statistical_score:.0f} Soc={pick.social_score:.0f}\n"
        f"\n"
        f"  [bold]SOCIAL:[/]   {pick.social_narrative or 'No social signals'}\n"
        f"  [bold]POLITICS:[/] {pick.political_exposure or 'Low exposure'}\n"
        f"  [bold]CONFLICT:[/] {pick.war_exposure or 'No conflict impact'}\n"
        f"  [bold]INFLUENCERS:[/] {pick.influencer_signal or 'None detected'}\n"
        f"\n"
        f"  [bold]LEVELS:[/]   Support ${pick.nearest_support:.2f}  |  Resistance ${pick.nearest_resistance:.2f}\n"
        f"  [bold]STOPS:[/]    Entry ${pick.entry_price:.2f} → Stop ${pick.stop_price:.2f} → "
        f"Target ${pick.target_price:.2f} (R:R {pick.risk_reward:.1f}x)\n"
        f"\n"
        f"  [bold]OPTION:[/]   {pick.option_direction} option\n"
        f"     Safe:  ${pick.option_safe_strike} {pick.option_direction} exp {pick.option_exp_long}\n"
        f"     Aggro: ${pick.option_agg_strike} {pick.option_direction} exp {pick.option_exp_short}\n"
        f"     Budget: {pick.option_budget} (1 contract)\n"
        f"     Stop: -40% premium | Target: +75-100%\n"
        f"\n"
        f"  [bold]ROBINHOOD:[/]\n"
        f"     1) Search {pick.ticker} → Trade → Trade Options\n"
        f"     2) Choose {pick.option_direction} → strike ${pick.option_safe_strike}\n"
        f"     3) Expiration {pick.option_exp_long}\n"
        f"     4) LIMIT order at bid/ask midpoint\n"
        f"     5) Qty = 1 → Review → Submit"
    )

    border = {
        "A": "bright_green",
        "B": "green",
        "C": "yellow",
    }.get(pick.confidence_tier, "dim")

    console.print()
    console.print(Panel(detail, border_style=border, padding=(1, 2)))


def print_checklist(vix: float, vix_label: str):
    """Print the pre-trade checklist."""
    console.print()
    console.print(Panel(
        f"[bold]CHECKLIST BEFORE ANY TRADE[/]\n\n"
        f"  □ VIX = {vix} → {vix_label.split('—')[0].strip() if '—' in vix_label else vix_label}\n"
        f"  □ Catalyst confirmed on Finviz/Benzinga\n"
        f"  □ After 10:00 AM (no open-chasing)\n"
        f"  □ Volume ≥ 2x average\n"
        f"  □ Green candle after pullback\n"
        f"  □ LIMIT order (no market orders)\n"
        f"  □ Max 1-2 contracts\n"
        f"  □ Stop at -40% premium, target +75-100%\n\n"
        f"  [bold red]EXIT IMMEDIATELY IF:[/]\n"
        f"  → Option loses 40% from entry\n"
        f"  → Big red candle breaks support\n"
        f"  → Catalyst news reverses\n"
        f"  → Time is 3:50 PM ET",
        title="PRE-TRADE",
        border_style="yellow",
        padding=(1, 2),
    ))


def print_social_intel_panel(social_global: dict, political_pulse: dict,
                            war_watch: dict, influencer_pulse: dict):
    """Print the social intelligence briefing panel."""
    lines = []

    # Political pulse
    if political_pulse:
        risk = political_pulse.get("risk_level", "LOW")
        risk_style = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "EXTREME": "bold red"}.get(risk, "dim")
        theme = political_pulse.get("dominant_theme", "none")
        direction = political_pulse.get("market_direction", "NEUTRAL")
        summary = political_pulse.get("summary", "No major political catalysts")
        lines.append(f"  [bold]POLITICS:[/]  [{risk_style}]{risk}[/] — {theme} → {direction}")
        if summary:
            lines.append(f"             {summary[:100]}")
        affected = political_pulse.get("affected_tickers", [])
        if affected:
            lines.append(f"             Tickers: {', '.join(affected[:8])}")

    # War watch
    if war_watch:
        risk = war_watch.get("risk_level", "CALM")
        risk_style = {"CALM": "green", "ELEVATED": "yellow", "HIGH": "red", "EXTREME": "bold red"}.get(risk, "dim")
        energy = war_watch.get("energy_risk", "LOW")
        safe_haven = war_watch.get("safe_haven_demand", "LOW")
        summary = war_watch.get("summary", "No active escalations")
        lines.append(f"  [bold]CONFLICT:[/] [{risk_style}]{risk}[/] — Energy: {energy} | Safe haven: {safe_haven}")
        if summary:
            lines.append(f"             {summary[:100]}")
        # Show active escalation alerts
        escalations = war_watch.get("escalation_alerts", [])
        for esc in escalations[:3]:
            lines.append(f"             [red]⚠ {esc.get('conflict_id', 'UNKNOWN')}: {esc.get('headline', '')[:70]}[/]")

    # Influencer pulse
    if influencer_pulse:
        consensus = influencer_pulse.get("fintwit_consensus", "QUIET")
        cons_style = {"BULLISH": "green", "BEARISH": "red", "MIXED": "yellow", "QUIET": "dim"}.get(consensus, "dim")
        summary = influencer_pulse.get("summary", "No notable influencer activity")
        lines.append(f"  [bold]VOICES:[/]   [{cons_style}]{consensus}[/] — {summary[:80]}")

        if influencer_pulse.get("elon_alert"):
            lines.append(f"             [bold bright_yellow]⚡ ELON ALERT — check TSLA/crypto[/]")

        active = influencer_pulse.get("active_influencers", [])
        for inf in active[:3]:
            name = inf.get("name", "")
            headline = inf.get("headline", "")[:60]
            impact = inf.get("impact_score", 0)
            lines.append(f"             {name} (impact {impact}): {headline}")

    # Social narrative
    if social_global and social_global.get("narrative"):
        lines.append(f"  [bold]SOCIAL:[/]   {social_global['narrative'][:120]}")

    if not lines:
        lines.append("  [dim]Social intel: no data yet (sources loading...)[/]")

    content = "\n".join(lines)
    console.print()
    console.print(Panel(
        content,
        title="[bold bright_cyan]SOCIAL INTELLIGENCE BRIEFING[/]",
        border_style="cyan",
        padding=(1, 2),
    ))


def print_geopolitical_brief(political: dict, war: dict):
    """Print a condensed geopolitical brief (used in live mode)."""
    parts = []
    if political:
        risk = political.get("risk_level", "LOW")
        parts.append(f"Pol:{risk}")
    if war:
        risk = war.get("risk_level", "CALM")
        parts.append(f"War:{risk}")
    if parts:
        console.print(f"  [bold]GEO:[/] {' | '.join(parts)}")


def print_save_summary(picks_file: str, history_file: str):
    """Print save confirmation."""
    console.print()
    console.print(f"  [dim]Saved:[/] {picks_file}")
    console.print(f"  [dim]Updated:[/] {history_file}")
    console.print(f"  [dim]Run again tomorrow morning for fresh picks[/]")
    console.print()

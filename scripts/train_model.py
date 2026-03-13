#!/usr/bin/env python3
"""
Train ML model(s) for Scalp Assistant predictions.

Walk-forward validated training with diagnostic output:
  - Per-fold date ranges and metrics
  - Overfitting warnings (R² gap, hit rate gap)
  - Dummy baseline comparison
  - Class imbalance check
  - Feature importance ranking

Usage:
    python scripts/train_model.py                  # Train universal model on SPY
    python scripts/train_model.py --ticker AAPL     # Train ticker-specific model
    python scripts/train_model.py --all             # Train on full stock universe
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Train ML prediction model")
    parser.add_argument("--ticker", type=str, default="universal",
                        help="Ticker to train on (default: universal/SPY)")
    parser.add_argument("--all", action="store_true",
                        help="Train on all tickers in stock universe")
    parser.add_argument("--lookback", type=int, default=730,
                        help="Days of history (default: 730)")
    args = parser.parse_args()

    from analysis.ml.predictor import train_model

    if args.all:
        from config import settings
        universe = settings.get_universe("stocks")
        console.print(f"\n  [bold]Training models for {len(universe)} tickers...[/]\n")

        console.print("  Training universal model (SPY)...")
        result = train_model("universal", lookback_days=args.lookback)
        _print_result("universal (SPY)", result)

        for i, ticker in enumerate(universe):
            console.print(f"  [{i+1}/{len(universe)}] Training {ticker}...")
            result = train_model(ticker, lookback_days=args.lookback)
            if "error" not in result:
                _print_result(ticker, result)
            else:
                console.print(f"    [dim]{result['error']}[/]")

    else:
        label = 'universal (SPY)' if args.ticker == 'universal' else args.ticker
        console.print(f"\n  [bold]Training {label} model...[/]\n")
        result = train_model(args.ticker, lookback_days=args.lookback)
        _print_result(label, result)

    console.print("\n  [green bold]Done.[/]\n")


def _print_result(label: str, result: dict):
    if "error" in result:
        console.print(f"  [red]x {label}: {result['error']}[/]")
        return

    # ── Walk-forward fold results ──
    folds = result.get("fold_results", [])
    if folds:
        fold_table = Table(title=f"Walk-Forward Folds — {label}", box=box.SIMPLE, show_header=True)
        fold_table.add_column("Fold", style="dim")
        fold_table.add_column("Date Range", style="cyan")
        fold_table.add_column("Train", style="dim")
        fold_table.add_column("Test", style="dim")
        fold_table.add_column("R² Test", style="white")
        fold_table.add_column("Hit% Test", style="white")

        for f in folds:
            r2_style = "green" if f["r2_test"] > 0 else "red"
            hit_style = "green" if f["hit_rate_test"] > 52 else ("red" if f["hit_rate_test"] < 48 else "yellow")
            fold_table.add_row(
                str(f["fold"]),
                f["date_range"],
                str(f["train_size"]),
                str(f["test_size"]),
                f"[{r2_style}]{f['r2_test']:.4f}[/]",
                f"[{hit_style}]{f['hit_rate_test']:.1f}%[/]",
            )
        console.print(fold_table)

    # ── Aggregate metrics ──
    metrics_table = Table(title=f"Aggregate — {label}", box=box.SIMPLE, show_header=True)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="white")

    wf_r2 = result["r2_test"]
    wf_hit = result["hit_rate_test"]
    dummy = result.get("dummy_baseline", 50)
    sharpe = result.get("sharpe", 0)
    balance = result.get("class_balance", 0.5)

    r2_style = "green" if wf_r2 > 0 else "red"
    hit_style = "green" if wf_hit > dummy else "red"
    sharpe_style = "green" if sharpe > 0 else "red"

    metrics_table.add_row("Walk-Forward R²", f"[{r2_style}]{wf_r2:.4f}[/]")
    metrics_table.add_row("Walk-Forward Hit Rate", f"[{hit_style}]{wf_hit:.1f}%[/]")
    metrics_table.add_row("Dummy Baseline (majority)", f"{dummy:.1f}%")
    metrics_table.add_row("Edge vs Dummy", f"{wf_hit - dummy:+.1f}pp")
    metrics_table.add_row("Prediction Sharpe", f"[{sharpe_style}]{sharpe:.3f}[/]")
    metrics_table.add_row("Class Balance (% up)", f"{balance:.1%}")
    metrics_table.add_row("Samples", str(result["n_samples"]))
    metrics_table.add_row("Avg Train / Test", f"{result['n_train']} / {result['n_test']}")
    console.print(metrics_table)

    # ── Warnings ──
    warnings = result.get("warnings", [])
    if warnings:
        warn_text = "\n".join(f"  ! {w}" for w in warnings)
        console.print(Panel(warn_text, title="Overfitting Warnings", style="yellow", box=box.ROUNDED))

    # ── Top features ──
    importances = result.get("feature_importances", {})
    top_features = list(importances.items())[:8]
    if top_features:
        feat_table = Table(title="Top Features", box=box.SIMPLE, show_header=True)
        feat_table.add_column("Feature", style="cyan")
        feat_table.add_column("Importance", style="white")
        feat_table.add_column("Bar", style="green")

        max_imp = top_features[0][1] if top_features else 1
        for fname, fimp in top_features:
            bar_len = int(fimp / max_imp * 20)
            feat_table.add_row(fname, f"{fimp:.4f}", "█" * bar_len)
        console.print(feat_table)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Train ML model(s) for Scalp Assistant predictions.

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

        # Always train universal first
        console.print("  Training universal model (SPY)...")
        result = train_model("universal", lookback_days=args.lookback)
        _print_result("universal (SPY)", result)

        # Then ticker-specific
        for i, ticker in enumerate(universe):
            console.print(f"  [{i+1}/{len(universe)}] Training {ticker}...")
            result = train_model(ticker, lookback_days=args.lookback)
            if "error" not in result:
                _print_result(ticker, result)
            else:
                console.print(f"    [dim]{result['error']}[/]")

    else:
        console.print(f"\n  [bold]Training {'universal' if args.ticker == 'universal' else args.ticker} model...[/]\n")
        result = train_model(args.ticker, lookback_days=args.lookback)
        _print_result(args.ticker, result)

    console.print("\n  [green bold]✓ Training complete![/]\n")


def _print_result(label: str, result: dict):
    if "error" in result:
        console.print(f"  [red]✗ {label}: {result['error']}[/]")
        return

    table = Table(title=f"  {label} Model Results", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("R² (train)", f"{result['r2_train']:.4f}")
    table.add_row("R² (test)", f"{result['r2_test']:.4f}")
    if "hit_rate_train" in result:
        table.add_row("Hit Rate (train)", f"{result['hit_rate_train']:.1f}%")
        table.add_row("Hit Rate (test)", f"{result['hit_rate_test']:.1f}%")
    table.add_row("Samples", str(result['n_samples']))
    table.add_row("Train / Test", f"{result['n_train']} / {result['n_test']}")

    # Top 5 features
    importances = result.get("feature_importances", {})
    top5 = list(importances.items())[:5]
    for fname, fimp in top5:
        table.add_row(f"  {fname}", f"{fimp:.4f}")

    console.print(table)


if __name__ == "__main__":
    main()

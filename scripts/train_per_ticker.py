"""
Standalone script to train per-ticker specialized models for PERTICKER_UNIVERSE.

Run from the project root:
    python scripts/train_per_ticker.py
    python scripts/train_per_ticker.py --force   # retrain even if models exist

Or via the module CLI:
    python -m analysis.ml.predictor --train-per-ticker
    python -m analysis.ml.predictor --train-per-ticker --ticker SPY --force
"""

import sys
import os

# Ensure project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.ml.predictor import train_all_per_ticker_models

force = "--force" in sys.argv

results = train_all_per_ticker_models(force=force)

print("\n── Per-ticker training summary ──")
for ticker, meta in results.items():
    if "error" in meta:
        print(f"  {ticker}: ERROR — {meta['error']}")
    else:
        print(
            f"  {ticker}: hit_rate={meta.get('hit_rate', '?')}%  "
            f"edge={meta.get('edge_vs_dummy', '?'):+}pp  "
            f"n={meta.get('n_samples', '?')}  "
            f"hp={meta.get('best_hp_tag', '?')}"
        )

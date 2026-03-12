#!/usr/bin/env python3
"""
=================================================================
  SCALP ASSISTANT v4.0 — Multi-Asset Trading Command Center
  Physics-based scoring across stocks, ETFs, crypto, forex,
  commodities with live dashboard, predictions, and alerts.
=================================================================
  SETUP:
      pip install -r requirements.txt
      cp .env.example .env   # add your free API keys
  RUN:
      python scalp_assistant.py              # morning scan (stocks)
      python scalp_assistant.py --live       # continuous monitor
      python scalp_assistant.py --top-n 10   # show top 10
      python scalp_assistant.py --dashboard  # launch web dashboard
      python scalp_assistant.py --asset crypto  # scan specific asset class
=================================================================
"""
import argparse
import sys
import os
import warnings
import logging

warnings.filterwarnings("ignore")

# Suppress noisy HTTP error logs from fetchers (they handle errors gracefully)
logging.basicConfig(level=logging.WARNING, format="%(message)s")
for noisy in ["urllib3", "requests", "feedparser", "yfinance", "fredapi"]:
    logging.getLogger(noisy).setLevel(logging.CRITICAL)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Scalp Assistant v4 — Multi-Asset Trading Command Center"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Run in continuous live monitoring mode"
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Launch the Streamlit web dashboard"
    )
    parser.add_argument(
        "--top-n", type=int, default=None,
        help="Number of top picks to display"
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated list of tickers to scan (overrides universe)"
    )
    parser.add_argument(
        "--asset", type=str, default="stocks",
        choices=["stocks", "etfs", "crypto", "forex", "commodities"],
        help="Asset class to scan (default: stocks)"
    )
    parser.add_argument(
        "--port", type=int, default=8501,
        help="Port for the Streamlit dashboard (default: 8501)"
    )
    args = parser.parse_args()

    if args.dashboard:
        import subprocess
        dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "app.py")
        print(f"\n  Launching Scalp Assistant Dashboard on port {args.port}...")
        print(f"  Open http://localhost:{args.port} in your browser\n")
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", dashboard_path,
            "--server.port", str(args.port),
            "--server.headless", "true",
            "--theme.base", "dark",
        ])
    elif args.live:
        from modes.live_monitor import run_live_monitor
        run_live_monitor(top_n=args.top_n, tickers=args.tickers)
    else:
        from modes.morning_scan import run_morning_scan
        run_morning_scan(top_n=args.top_n, tickers=args.tickers, asset_class=args.asset)


if __name__ == "__main__":
    main()

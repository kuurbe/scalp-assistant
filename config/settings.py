"""
Global configuration for Scalp Assistant v4.
All thresholds, weights, ticker universes, asset class configs, and API settings.
"""
import os
from typing import Optional


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from Streamlit Cloud secrets first, then fall back to os.environ."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)

# ─────────────────────────────────────────────────────────────
#  TICKER UNIVERSE — scanned daily, add/remove freely
# ─────────────────────────────────────────────────────────────
TICKER_UNIVERSE = [
    # Mega cap / Index ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Mega cap tech
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA",
    # High-momentum tech
    "PLTR", "ARM", "SMCI", "AVGO", "AMD", "MSTR", "COIN", "HOOD", "RBLX", "SNAP", "UBER",
    # Biotech / Healthcare
    "HIMS", "BBIO", "MRNA", "BNTX", "CRSP", "EDIT", "BEAM", "RXRX", "NVAX",
    # Financials / Fintech
    "SOFI", "AFRM", "UPST", "XYZ", "PYPL", "NU", "MELI", "LC",  # SQ renamed to XYZ (Block)
    # Energy
    "XOM", "CVX", "OXY", "SLB", "MPC", "VLO", "PSX", "FANG", "DVN",
    # Consumer / Retail
    "ONON", "NKE", "LULU", "CROX", "DECK", "SHAK", "BROS",
    # Semiconductors
    "INTC", "QCOM", "MU", "LRCX", "KLAC", "AMAT", "MRVL", "ON",
    # Growth / Speculative
    "IONQ", "RGTI", "QBTS", "LUNR", "RDW", "RKLB", "ASTS", "ACHR",
    # Big cap value
    "NVO", "LLY", "PFE", "ABBV", "BMY", "JNJ", "ORCL", "CRM", "NOW", "SNOW",
    # Meme / high short interest
    "GME", "AMC", "SPCE", "OPEN",
    # AI Hedge Fund — Automotive / Mobility
    "MBLY", "AEHR", "JOBY",
    # AI Hedge Fund — Healthcare / Life Sciences
    "TEM",
    # AI Hedge Fund — Industrial / Automation
    "GE", "HON",
    # AI Hedge Fund — Media / Consumer AI
    "NFLX",
    # AI Hedge Fund — Retail / Cloud / Data
    "NBIS",
    # AI Hedge Fund — Robotics / Physical AI
    "RCAT", "ONDS", "SERV",
    # AI Hedge Fund — Telco / Networking
    "ANET", "COHR", "LITE",
    # AI Hedge Fund — Advanced Compute
    "ALAB", "IREN",
    # Sector ETFs
    "XLF", "XLE", "XLK", "ARKK",
    # Crypto proxies
    "MARA", "RIOT", "CLSK",
]

# ─────────────────────────────────────────────────────────────
#  ETF UNIVERSE
# ─────────────────────────────────────────────────────────────
ETF_UNIVERSE = [
    # Broad Market
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO",
    # Sector
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "XLP", "XLB", "XLRE",
    # Thematic
    "ARKK", "ARKG", "ARKF", "ARKW",
    "BOTZ", "LIT", "TAN", "ICLN",
    # Fixed Income
    "TLT", "IEF", "SHY", "HYG", "LQD", "AGG",
    # International
    "EEM", "FXI", "EWJ", "EWZ", "INDA", "VWO",
    # Volatility
    "UVXY", "VXX",
    # Leveraged (popular on Robinhood)
    "TQQQ", "SQQQ", "SOXL", "SOXS",
]

# ─────────────────────────────────────────────────────────────
#  CRYPTO UNIVERSE (yfinance format: SYMBOL-USD)
# ─────────────────────────────────────────────────────────────
CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
    "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD",
    "ATOM-USD", "ARB-USD", "OP-USD",
    "NEAR-USD", "FIL-USD", "RENDER-USD", "FET-USD", "INJ-USD",
    # Removed 2026-04-17 — returned no price data on yfinance ("possibly delisted"):
    #   UNI-USD  — Uniswap feed unresponsive on Yahoo
    #   APT-USD  — Aptos feed unresponsive on Yahoo
    #   POL-USD  — Polygon rebrand; neither POL nor MATIC alias returns data
    # Re-add if Yahoo restores these feeds. Also monitor ARB-USD — Yahoo returns
    # $0.0007 which does not match Arbitrum's real price; may be a different token.
]

# ─────────────────────────────────────────────────────────────
#  STABLECOIN UNIVERSE (depeg monitoring)
# ─────────────────────────────────────────────────────────────
STABLECOIN_UNIVERSE = [
    "USDT-USD", "USDC-USD", "DAI-USD", "BUSD-USD",
    "TUSD-USD", "FRAX-USD", "PYUSD-USD",
]

# Stablecoin depeg thresholds
STABLECOIN_PEG_PRICE = 1.00
STABLECOIN_WARN_DEVIATION = 0.005     # 0.5% — yellow alert
STABLECOIN_ALERT_DEVIATION = 0.01     # 1.0% — red alert
STABLECOIN_EMERGENCY_DEVIATION = 0.03  # 3.0% — emergency

# ─────────────────────────────────────────────────────────────
#  FOREX UNIVERSE (yfinance format: PAIR=X)
# ─────────────────────────────────────────────────────────────
FOREX_UNIVERSE = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
    "AUDUSD=X", "USDCAD=X", "NZDUSD=X",
    "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "DX-Y.NYB",  # US Dollar Index
]

# ─────────────────────────────────────────────────────────────
#  COMMODITY UNIVERSE (ETF proxies — all on Robinhood)
# ─────────────────────────────────────────────────────────────
COMMODITY_UNIVERSE = [
    # Precious metals
    "GLD", "SLV", "GDX",
    # Oil
    "USO", "UCO", "XOP",
    # Natural gas
    "UNG",
    # Agriculture
    "WEAT", "CORN", "SOYB",
    # Broad commodity
    "DBA", "DBC", "PDBC",
    # Industrial / Uranium
    "COPX", "URA",
]

# ─────────────────────────────────────────────────────────────
#  ASSET CLASS METADATA
# ─────────────────────────────────────────────────────────────
ASSET_CLASS_CONFIG = {
    "stocks": {
        "universe_key": "TICKER_UNIVERSE",
        "trading_days_year": 252,
        "minutes_per_day": 390,
        "market_hours": True,
        "has_options": True,
        "news_category": "general",
        "label": "Stocks",
    },
    "etfs": {
        "universe_key": "ETF_UNIVERSE",
        "trading_days_year": 252,
        "minutes_per_day": 390,
        "market_hours": True,
        "has_options": True,
        "news_category": "general",
        "label": "ETFs",
    },
    "crypto": {
        "universe_key": "CRYPTO_UNIVERSE",
        "trading_days_year": 365,
        "minutes_per_day": 1440,
        "market_hours": False,
        "has_options": False,
        "news_category": "crypto",
        "label": "Crypto",
    },
    "forex": {
        "universe_key": "FOREX_UNIVERSE",
        "trading_days_year": 260,
        "minutes_per_day": 1440,
        "market_hours": False,
        "has_options": False,
        "news_category": "forex",
        "label": "Forex",
    },
    "commodities": {
        "universe_key": "COMMODITY_UNIVERSE",
        "trading_days_year": 252,
        "minutes_per_day": 390,
        "market_hours": True,
        "has_options": True,
        "news_category": "general",
        "label": "Commodities",
    },
    "stablecoins": {
        "universe_key": "STABLECOIN_UNIVERSE",
        "trading_days_year": 365,
        "minutes_per_day": 1440,
        "market_hours": False,
        "has_options": False,
        "news_category": "crypto",
        "label": "Stablecoins",
    },
}

def get_universe(asset_class: str) -> list:
    """Get the ticker universe for an asset class."""
    cfg = ASSET_CLASS_CONFIG.get(asset_class, {})
    key = cfg.get("universe_key", "TICKER_UNIVERSE")
    import config.settings as _self
    return getattr(_self, key, TICKER_UNIVERSE)

# ─────────────────────────────────────────────────────────────
#  COMPOSITE SCORING WEIGHTS (must sum to 1.0)
# ─────────────────────────────────────────────────────────────
WEIGHT_PHYSICS = 0.22
WEIGHT_TECHNICAL = 0.20
WEIGHT_CATALYST = 0.18
WEIGHT_STATISTICAL = 0.16
WEIGHT_ML = 0.12
WEIGHT_SEFIROT = 0.00  # Off by default — enable after validating feature predictiveness
# WEIGHT_SOCIAL = 0.12 (defined below in Social Intelligence section)

# ─────────────────────────────────────────────────────────────
#  REGIME THRESHOLDS
# ─────────────────────────────────────────────────────────────
HURST_TREND_THRESHOLD = 0.55
HURST_REVERT_THRESHOLD = 0.45
ENTROPY_MAX_CHAOS = 0.85  # normalized [0,1] — skip above this

# ─────────────────────────────────────────────────────────────
#  PHYSICS THRESHOLDS
# ─────────────────────────────────────────────────────────────
SPARK_ACCEL_THRESHOLD = 2.0       # acceleration z-score for ignition
SPARK_VOLUME_MULT = 3.0           # volume must be >= 3x average
DIP_ZSCORE_ENTRY = -1.5           # z-score below VWAP for dip entry
OU_HALFLIFE_MAX_MINUTES = 120     # only mean-revert if half-life < 2 hours
KINEMATICS_SMOOTH_WINDOW = 5      # smooth derivatives over N bars

# ─────────────────────────────────────────────────────────────
#  API CONFIGURATION
# ─────────────────────────────────────────────────────────────
FINNHUB_WS_MAX_SYMBOLS = 50
FINNHUB_RATE_LIMIT = 60  # calls per minute

YFINANCE_DAILY_PERIOD = "1y"
YFINANCE_INTRADAY_PERIOD = "5d"
YFINANCE_INTRADAY_INTERVAL = "1m"

FRED_SERIES = ["FEDFUNDS", "T10Y2Y", "VIXCLS", "UMCSENT"]

CACHE_TTL_SECONDS = 300           # 5 min default
NEWS_CACHE_TTL = 180              # 3 min for news
REDDIT_CACHE_TTL = 900            # 15 min for reddit
STOCKTWITS_CACHE_TTL = 300        # 5 min for stocktwits
GEOPOLITICAL_CACHE_TTL = 300      # 5 min for geopolitical news
SOCIAL_INTEL_CACHE_TTL = 300      # 5 min for social intel composite

# ─────────────────────────────────────────────────────────────
#  OUTPUT
# ─────────────────────────────────────────────────────────────
TOP_N_PICKS = 7
MIN_COMPOSITE_SCORE = 40          # minimum to display
LIVE_POLL_INTERVAL = 60           # seconds between refresh cycles
ALERT_COOLDOWN_SECONDS = 900      # 15 min dedup per ticker+signal

# ─────────────────────────────────────────────────────────────
#  RISK MANAGEMENT
# ─────────────────────────────────────────────────────────────
DEFAULT_ACCOUNT_SIZE = 10000
DEFAULT_RISK_PCT = 1.0            # risk 1% per trade
ATR_STOP_MULTIPLIER = 1.5
ATR_TARGET_MULTIPLIER = 3.0
OPTION_STOP_PCT = -40             # exit at -40% premium
OPTION_TARGET_PCT = 75            # target +75% gain

# ─────────────────────────────────────────────────────────────
#  SOCIAL INTELLIGENCE
# ─────────────────────────────────────────────────────────────
# Composite scoring weight allocation (reallocated to include social)
# Original: Physics 0.30, Technical 0.25, Catalyst 0.25, Statistical 0.20
# Updated:  Physics 0.25, Technical 0.22, Catalyst 0.20, Statistical 0.18, Social 0.15
WEIGHT_SOCIAL = 0.12

# Social score sub-weights (within the 15% social allocation)
SOCIAL_WEIGHT_STOCKTWITS = 0.30
SOCIAL_WEIGHT_REDDIT = 0.25
SOCIAL_WEIGHT_X_MENTIONS = 0.20
SOCIAL_WEIGHT_POLITICAL = 0.15
SOCIAL_WEIGHT_WAR = 0.10

# Political risk thresholds
POLITICAL_RISK_LOW = 30
POLITICAL_RISK_MEDIUM = 60
POLITICAL_RISK_HIGH = 80

# War risk thresholds
WAR_RISK_CALM = 20
WAR_RISK_ELEVATED = 50
WAR_RISK_HIGH = 75

# Influencer impact thresholds
INFLUENCER_HIGH_IMPACT = 80       # flag if influencer impact >= this
INFLUENCER_MIN_RELEVANCE = 40     # minimum score to display

# ─────────────────────────────────────────────────────────────
#  AI HEDGE FUND WATCHLIST (sector-grouped)
# ─────────────────────────────────────────────────────────────
AI_HEDGE_FUND_TICKERS = {
    "Automotive / Mobility": ["MBLY", "AEHR", "JOBY"],
    "Healthcare / Life Sciences": ["TEM", "HIMS"],
    "Financial / AI Software": ["PLTR"],
    "Industrial / Automation": ["GE", "HON"],
    "Media / Consumer AI": ["META", "GOOGL", "NFLX"],
    "Retail / Cloud / Data": ["AMZN", "NBIS"],
    "Robotics / Physical AI": ["TSLA", "RCAT", "ONDS", "SERV"],
    "Telco / Networking": ["ANET", "COHR", "LITE"],
    "Advanced Compute": ["NVDA", "AMD", "AVGO", "INTC", "ALAB", "IREN"],
}

# ─────────────────────────────────────────────────────────────
#  QUANT FORMULA THRESHOLDS (Six-Formula Engine)
# ─────────────────────────────────────────────────────────────
KELLY_MAX_FRACTION = 0.25         # Cap at quarter-Kelly (ruin protection)
QUANT_ALIGNMENT_MIN = 4           # Minimum formulas agreeing for "aligned"
QUANT_EV_GAP_THRESHOLD = 0.5     # EV gap > 0.5% is actionable
QUANT_KL_MAX_STABLE = 0.5        # KL divergence below this = stable signal
STOIKOV_RISK_AVERSION = 0.1      # Gamma parameter for Stoikov reservation price

# ─────────────────────────────────────────────────────────────
#  WHALE DETECTION (Unusual Whales methodology — approximated)
# ─────────────────────────────────────────────────────────────
WHALE_VOLUME_SIGMA = 2.5         # Std devs above mean volume for "unusual"
WHALE_GOLDEN_VOLUME_MULT = 5.0   # Volume multiplier for golden sweep equivalent
WHALE_BLOCK_MIN_DOLLAR = 500000  # Minimum dollar volume for block detection
WHALE_SWEEP_CONSECUTIVE = 3      # Consecutive high-volume bars for sweep pattern

# ─────────────────────────────────────────────────────────────
#  BEST PLAYS SETTINGS
# ─────────────────────────────────────────────────────────────
BEST_PLAYS_MIN_SCORE = 55        # Minimum composite score for best plays
BEST_PLAYS_MAX_RESULTS = 5       # Maximum plays to show

# Live monitor social refresh interval (cycles)
SOCIAL_REFRESH_CYCLES = 5         # refresh social intel every N cycles
GEOPOLITICAL_REFRESH_CYCLES = 10  # refresh geopolitical every N cycles

# ─────────────────────────────────────────────────────────────
#  EXPANDED FRED MACRO SERIES
# ─────────────────────────────────────────────────────────────
FRED_SERIES_EXPANDED = {
    "FEDFUNDS": "fed_rate",
    "T10Y2Y": "yield_curve_spread",
    "VIXCLS": "vix",
    "UMCSENT": "consumer_sentiment",
    "DCOILWTICO": "wti_crude",
    "GOLDAMGBD228NLBM": "gold_price",
    "DTWEXBGS": "usd_index",
    "T10YIE": "breakeven_inflation_10y",
    "BAMLH0A0HYM2": "high_yield_spread",
    "DEXUSEU": "eur_usd",
    "UNRATE": "unemployment",
    "CPIAUCSL": "cpi",
}

# ─────────────────────────────────────────────────────────────
#  PREDICTION TRACKING
# ─────────────────────────────────────────────────────────────
PREDICTION_HORIZONS = {
    "intraday": {"hours": 6.5},
    "swing_2d": {"hours": 48},
    "swing_5d": {"hours": 120},
}

# ─────────────────────────────────────────────────────────────
#  ACHIEVEMENTS
# ─────────────────────────────────────────────────────────────
ACHIEVEMENT_THRESHOLDS = {
    "hot_streak_3": 3,
    "hot_streak_5": 5,
    "hot_streak_10": 10,
    "accuracy_60": 60.0,
    "accuracy_65": 65.0,
    "accuracy_70": 70.0,
    "total_picks_100": 100,
    "total_picks_500": 500,
    "total_picks_1000": 1000,
}

# ─────────────────────────────────────────────────────────────
#  NOTIFICATION SETTINGS
# ─────────────────────────────────────────────────────────────
NOTIFY_ON_SPARK = True
NOTIFY_ON_DIP = True
NOTIFY_MIN_SCORE = 55
NOTIFY_QUIET_HOURS = (22, 7)      # Don't notify between 10pm-7am
NOTIFY_COOLDOWN_SECONDS = 1800    # 30 min between same-ticker alerts (was 10 min)

# Crypto scanner settings
CRYPTO_SCAN_INTERVAL_MIN = 5      # Crypto scans every 5 min (24/7)
STOCK_SCAN_INTERVAL_MIN = 15      # Stocks/ETFs scan every 15 min (market hours)

# Per-asset-class daily alert caps
DAILY_ALERT_CAP_STOCKS = 15
DAILY_ALERT_CAP_CRYPTO = 20       # Higher cap for 24/7 market

# ─────────────────────────────────────────────────────────────
#  TRADINGVIEW MCP INTEGRATION
# ─────────────────────────────────────────────────────────────
TV_MCP_ENABLED = True
TV_CDP_URL = "http://localhost:9222"
TV_SCREENSHOT_TIMEFRAME_STOCKS = "15"
TV_SCREENSHOT_TIMEFRAME_CRYPTO = "5"
TV_SCREENSHOT_TIMEFRAME_SWING = "D"
TV_BATCH_DELAY_MS = 2000
TV_MAX_CANDIDATES = 15            # Max tickers to validate via TV per scan
TV_INDICATOR_TEMPLATE = [
    "Relative Strength Index",
    "MACD",
    "Volume",
]

# yfinance ticker → TradingView symbol mapping
TV_TICKER_MAP = {
    # Index ETFs
    "SPY": "AMEX:SPY", "QQQ": "NASDAQ:QQQ", "IWM": "AMEX:IWM", "DIA": "AMEX:DIA",
    "VTI": "AMEX:VTI", "VOO": "AMEX:VOO",
    # Mega cap tech
    "NVDA": "NASDAQ:NVDA", "AAPL": "NASDAQ:AAPL", "MSFT": "NASDAQ:MSFT",
    "AMZN": "NASDAQ:AMZN", "META": "NASDAQ:META", "GOOGL": "NASDAQ:GOOGL",
    "TSLA": "NASDAQ:TSLA",
    # High-momentum tech
    "PLTR": "NYSE:PLTR", "ARM": "NASDAQ:ARM", "SMCI": "NASDAQ:SMCI",
    "AVGO": "NASDAQ:AVGO", "AMD": "NASDAQ:AMD", "MSTR": "NASDAQ:MSTR",
    "COIN": "NASDAQ:COIN", "HOOD": "NASDAQ:HOOD", "RBLX": "NYSE:RBLX",
    "SNAP": "NYSE:SNAP", "UBER": "NYSE:UBER",
    # Biotech / Healthcare
    "HIMS": "NYSE:HIMS", "BBIO": "NASDAQ:BBIO", "MRNA": "NASDAQ:MRNA",
    "BNTX": "NASDAQ:BNTX", "CRSP": "NASDAQ:CRSP", "EDIT": "NASDAQ:EDIT",
    "BEAM": "NASDAQ:BEAM", "RXRX": "NASDAQ:RXRX", "NVAX": "NASDAQ:NVAX",
    # Financials / Fintech
    "SOFI": "NASDAQ:SOFI", "AFRM": "NASDAQ:AFRM", "UPST": "NASDAQ:UPST",
    "XYZ": "NYSE:XYZ", "PYPL": "NASDAQ:PYPL", "NU": "NYSE:NU",
    "MELI": "NASDAQ:MELI", "LC": "NYSE:LC",
    # Energy
    "XOM": "NYSE:XOM", "CVX": "NYSE:CVX", "OXY": "NYSE:OXY", "SLB": "NYSE:SLB",
    "MPC": "NYSE:MPC", "VLO": "NYSE:VLO", "PSX": "NYSE:PSX", "FANG": "NASDAQ:FANG",
    "DVN": "NYSE:DVN",
    # Consumer / Retail
    "ONON": "NYSE:ONON", "NKE": "NYSE:NKE", "LULU": "NASDAQ:LULU",
    "CROX": "NASDAQ:CROX", "DECK": "NYSE:DECK", "SHAK": "NYSE:SHAK", "BROS": "NYSE:BROS",
    # Semiconductors
    "INTC": "NASDAQ:INTC", "QCOM": "NASDAQ:QCOM", "MU": "NASDAQ:MU",
    "LRCX": "NASDAQ:LRCX", "KLAC": "NASDAQ:KLAC", "AMAT": "NASDAQ:AMAT",
    "MRVL": "NASDAQ:MRVL", "ON": "NASDAQ:ON",
    # Growth / Speculative
    "IONQ": "NYSE:IONQ", "RGTI": "NASDAQ:RGTI", "QBTS": "NYSE:QBTS",
    "LUNR": "NASDAQ:LUNR", "RDW": "NYSE:RDW", "RKLB": "NASDAQ:RKLB",
    "ASTS": "NASDAQ:ASTS", "ACHR": "NASDAQ:ACHR",
    # Big cap value
    "NVO": "NYSE:NVO", "LLY": "NYSE:LLY", "PFE": "NYSE:PFE", "ABBV": "NYSE:ABBV",
    "BMY": "NYSE:BMY", "JNJ": "NYSE:JNJ", "ORCL": "NYSE:ORCL", "CRM": "NYSE:CRM",
    "NOW": "NYSE:NOW", "SNOW": "NYSE:SNOW",
    # Meme / short interest
    "GME": "NYSE:GME", "AMC": "NYSE:AMC", "SPCE": "NYSE:SPCE", "OPEN": "NASDAQ:OPEN",
    # AI Hedge Fund picks
    "MBLY": "NASDAQ:MBLY", "AEHR": "NASDAQ:AEHR", "JOBY": "NYSE:JOBY",
    "TEM": "NASDAQ:TEM", "GE": "NYSE:GE", "HON": "NASDAQ:HON", "NFLX": "NASDAQ:NFLX",
    "NBIS": "NASDAQ:NBIS", "RCAT": "NASDAQ:RCAT", "ONDS": "NYSE:ONDS",
    "SERV": "NASDAQ:SERV", "ANET": "NYSE:ANET", "COHR": "NYSE:COHR",
    "LITE": "NASDAQ:LITE", "ALAB": "NASDAQ:ALAB", "IREN": "NASDAQ:IREN",
    # Sector ETFs
    "XLF": "AMEX:XLF", "XLE": "AMEX:XLE", "XLK": "AMEX:XLK", "ARKK": "AMEX:ARKK",
    "XLV": "AMEX:XLV", "XLI": "AMEX:XLI", "XLU": "AMEX:XLU", "XLP": "AMEX:XLP",
    "XLB": "AMEX:XLB", "XLRE": "AMEX:XLRE",
    # Thematic ETFs
    "ARKG": "AMEX:ARKG", "ARKF": "AMEX:ARKF", "ARKW": "AMEX:ARKW",
    "BOTZ": "NASDAQ:BOTZ", "LIT": "AMEX:LIT", "TAN": "AMEX:TAN", "ICLN": "NASDAQ:ICLN",
    # Fixed Income ETFs
    "TLT": "NASDAQ:TLT", "IEF": "NASDAQ:IEF", "SHY": "NASDAQ:SHY",
    "HYG": "AMEX:HYG", "LQD": "AMEX:LQD", "AGG": "AMEX:AGG",
    # International ETFs
    "EEM": "AMEX:EEM", "FXI": "AMEX:FXI", "EWJ": "AMEX:EWJ", "EWZ": "AMEX:EWZ",
    "INDA": "AMEX:INDA", "VWO": "AMEX:VWO",
    # Volatility / Leveraged
    "UVXY": "AMEX:UVXY", "VXX": "AMEX:VXX",
    "TQQQ": "NASDAQ:TQQQ", "SQQQ": "NASDAQ:SQQQ", "SOXL": "AMEX:SOXL", "SOXS": "AMEX:SOXS",
    # Crypto proxies
    "MARA": "NASDAQ:MARA", "RIOT": "NASDAQ:RIOT", "CLSK": "NASDAQ:CLSK",
    # Commodities (ETF proxies)
    "GLD": "AMEX:GLD", "SLV": "AMEX:SLV", "GDX": "AMEX:GDX",
    "USO": "AMEX:USO", "UCO": "AMEX:UCO", "XOP": "AMEX:XOP", "UNG": "AMEX:UNG",
    "WEAT": "AMEX:WEAT", "CORN": "AMEX:CORN", "SOYB": "AMEX:SOYB",
    "DBA": "AMEX:DBA", "DBC": "AMEX:DBC", "PDBC": "AMEX:PDBC",
    "COPX": "AMEX:COPX", "URA": "AMEX:URA",
    # Crypto → TradingView (yfinance BTC-USD → COINBASE:BTCUSD)
    "BTC-USD": "COINBASE:BTCUSD", "ETH-USD": "COINBASE:ETHUSD",
    "SOL-USD": "COINBASE:SOLUSD", "XRP-USD": "COINBASE:XRPUSD",
    "DOGE-USD": "COINBASE:DOGEUSD", "ADA-USD": "COINBASE:ADAUSD",
    "AVAX-USD": "COINBASE:AVAXUSD", "DOT-USD": "COINBASE:DOTUSD",
    "LINK-USD": "COINBASE:LINKUSD",
    "ATOM-USD": "COINBASE:ATOMUSD",
    "ARB-USD": "COINBASE:ARBUSD", "OP-USD": "COINBASE:OPUSD",
    "NEAR-USD": "COINBASE:NEARUSD", "FIL-USD": "COINBASE:FILUSD",
    "RENDER-USD": "COINBASE:RENDERUSD", "FET-USD": "COINBASE:FETUSD",
    "INJ-USD": "COINBASE:INJUSD",
    # UNI / APT / POL removed 2026-04-17 — yfinance fetch dead (see CRYPTO_UNIVERSE)
    # Forex
    "EURUSD=X": "FX:EURUSD", "GBPUSD=X": "FX:GBPUSD", "USDJPY=X": "FX:USDJPY",
    "USDCHF=X": "FX:USDCHF", "AUDUSD=X": "FX:AUDUSD", "USDCAD=X": "FX:USDCAD",
    "NZDUSD=X": "FX:NZDUSD", "EURGBP=X": "FX:EURGBP", "EURJPY=X": "FX:EURJPY",
    "GBPJPY=X": "FX:GBPJPY", "DX-Y.NYB": "TVC:DXY",
}

# ─────────────────────────────────────────────────────────────
#  SCALP ENGINE
# ─────────────────────────────────────────────────────────────
SCALP_ENABLED = True
SCALP_MONITOR_INTERVAL_SEC = 120      # 2 min between scalp checks
SCALP_MAX_HOT_LIST = 8                # max tickers to watch
SCALP_MIN_RVOL = 2.0                  # minimum relative volume for hot list
SCALP_MIN_RR = 1.5                    # minimum risk:reward
SCALP_ATR_STOP_MULT = 0.75            # tighter stops for scalps (vs 1.5x normal)
SCALP_ATR_TARGET1_MULT = 1.0          # 50% scale-out target
SCALP_ATR_TARGET2_MULT = 2.0          # full exit target
SCALP_ORB_START = "09:30"             # Opening range start (ET)
SCALP_ORB_END = "09:45"               # Opening range end (ET)
SCALP_ORB_WINDOW_END = "10:30"        # Stop trading ORB after this
SCALP_VWAP_TOLERANCE = 0.0015         # 0.15% distance from VWAP = pullback
SCALP_COOLDOWN_SECONDS = 300          # 5 min between same-ticker scalp alerts
SCALP_DAILY_CAP = 10                  # max scalp alerts per day

# ─────────────────────────────────────────────────────────────
#  OPTIONS SCALP ENGINE
# ─────────────────────────────────────────────────────────────
OPT_SCALP_ENABLED = True              # master toggle for options scalp detectors
OPT_SCALP_INTERVAL_SEC = 60           # check every 60s (faster than stock scalps)
OPT_SCALP_MIN_VOLUME = 50             # min option contract volume
OPT_SCALP_MIN_OI = 100                # min open interest
OPT_SCALP_MAX_SPREAD_PCT = 0.10       # max 10% bid/ask spread
OPT_SCALP_IV_RANK_MIN = 20            # skip if IV too low (premiums tiny)
OPT_SCALP_IV_RANK_MAX = 80            # skip if IV too high (crush risk)
OPT_SCALP_MIN_DELTA = 0.30            # avoid far OTM
OPT_SCALP_MAX_DELTA = 0.65            # avoid deep ITM
OPT_SCALP_0DTE_CUTOFF = "14:00"       # no new 0DTE after 2pm ET
OPT_SCALP_PREMIUM_MAX = 500           # max premium per contract ($)
OPT_SCALP_DAILY_CAP = 8               # max options scalp alerts per day

# ─────────────────────────────────────────────────────────────
#  ML TRADINGVIEW FEATURE INTEGRATION
# ─────────────────────────────────────────────────────────────
ML_TV_FEATURES_ENABLED = True         # toggle TV-equivalent technical features in ML
ML_TV_BLEND_ENABLED = True            # blend live TV values at prediction time
ML_TV_BLEND_WEIGHT = 0.7              # weight for TV value vs computed (0-1)
ML_MODEL_ARCHIVE_ENABLED = True       # archive models before retrain
ML_MODEL_ARCHIVE_KEEP = 4             # number of model archives to keep
ML_RETRAIN_LOOKBACK_DAYS = 730        # default training data window

# ─────────────────────────────────────────────────────────────
#  FREE API ENDPOINTS (no signup required)
# ─────────────────────────────────────────────────────────────
FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
ALTERNATIVE_FNG_URL = "https://api.alternative.me/fng/"

# ─────────────────────────────────────────────────────────────
#  BUY/HOLD/SELL RECOMMENDATION THRESHOLDS
# ─────────────────────────────────────────────────────────────
RECOMMENDATION_THRESHOLDS = {
    "buy_min_score": 65,          # Minimum composite score for BUY
    "sell_min_score": 55,         # Minimum composite score for SELL
    "buy_rsi_oversold": 35,       # RSI below this triggers BUY
    "sell_rsi_overbought": 70,    # RSI above this triggers SELL
    "dip_pct_threshold": -2.0,    # % change below this = dip
    "extended_pct_threshold": 3.0, # % change above this = extended
}

"""
Global configuration for Scalp Assistant v4.
All thresholds, weights, ticker universes, asset class configs, and API settings.
"""

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
    "HIMS", "BBIO", "MRNA", "BNTX", "CRSP", "EDIT", "BEAM", "RXRX", "NVAX", "SAVA", "CARA",
    # Financials / Fintech
    "SOFI", "AFRM", "UPST", "SQ", "PYPL", "NU", "MELI", "LC",
    # Energy
    "XOM", "CVX", "OXY", "SLB", "MPC", "VLO", "PSX", "FANG", "DVN",
    # Consumer / Retail
    "ONON", "NKE", "LULU", "CROX", "DECK", "SKX", "SHAK", "BROS",
    # Semiconductors
    "INTC", "QCOM", "MU", "LRCX", "KLAC", "AMAT", "MRVL", "ON",
    # Growth / Speculative
    "IONQ", "RGTI", "QBTS", "LUNR", "RDW", "RKLB", "ASTS", "ACHR",
    # Big cap value
    "NVO", "LLY", "PFE", "ABBV", "BMY", "JNJ", "ORCL", "CRM", "NOW", "SNOW",
    # Meme / high short interest
    "GME", "AMC", "SPCE", "NKLA", "OPEN",
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
    "UNI-USD", "ATOM-USD", "APT-USD", "ARB-USD", "OP-USD",
    "NEAR-USD", "FIL-USD", "RENDER-USD", "FET-USD", "INJ-USD",
    "MATIC-USD",
]

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
WEIGHT_PHYSICS = 0.25
WEIGHT_TECHNICAL = 0.22
WEIGHT_CATALYST = 0.20
WEIGHT_STATISTICAL = 0.18
# WEIGHT_SOCIAL = 0.15 (defined below in Social Intelligence section)

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

YFINANCE_DAILY_PERIOD = "60d"
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
WEIGHT_SOCIAL = 0.15

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
NOTIFY_COOLDOWN_SECONDS = 600     # 10 min between same-ticker alerts

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

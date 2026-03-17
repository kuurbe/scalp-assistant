"""
Finviz-inspired market visualization widgets.
Sector heatmap, top gainers/losers, index performance strip.
All rendered as inline HTML/SVG for Streamlit — no external chart libraries.
"""
import streamlit as st
from dashboard.theme import COLORS

# ─────────────────────────────────────────────────────────────
#  SECTOR MAP — maps tickers to sectors for the heatmap
# ─────────────────────────────────────────────────────────────
SECTOR_MAP = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "AVGO", "INTC", "QCOM", "MU", "ORCL", "CRM", "NOW", "SNOW", "PLTR", "ARM", "SMCI", "MRVL", "ON", "LRCX", "KLAC", "AMAT"],
    "Consumer": ["AMZN", "TSLA", "NKE", "LULU", "CROX", "DECK", "SKX", "ONON", "SHAK", "BROS"],
    "Healthcare": ["LLY", "NVO", "PFE", "ABBV", "BMY", "JNJ", "MRNA", "BNTX", "HIMS", "CRSP"],
    "Financials": ["SOFI", "AFRM", "UPST", "SQ", "PYPL", "NU", "MELI", "LC", "COIN", "HOOD"],
    "Energy": ["XOM", "CVX", "OXY", "SLB", "MPC", "VLO", "PSX", "FANG", "DVN"],
    "Growth": ["IONQ", "RGTI", "QBTS", "LUNR", "RDW", "RKLB", "ASTS", "ACHR", "RBLX", "SNAP", "UBER"],
    "Speculative": ["GME", "AMC", "SPCE", "NKLA", "OPEN", "MSTR", "MARA", "RIOT", "CLSK"],
}

# Sector ETF proxies for quick performance
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Staples": "XLP",
    "Materials": "XLB",
    "Real Estate": "XLRE",
}

INDEX_SYMBOLS = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Dow 30", "^DJI"),
    ("Russell 2K", "^RUT"),
    ("VIX", "^VIX"),
    ("10Y Yield", "^TNX"),
    ("Gold", "GC=F"),
    ("Oil", "CL=F"),
    ("BTC", "BTC-USD"),
    ("EUR/USD", "EURUSD=X"),
]


def _pct_color(pct: float) -> str:
    """Return color based on percentage change."""
    if pct > 2:
        return "#22C55E"
    if pct > 0.5:
        return "#4ADE80"
    if pct > 0:
        return "#86EFAC"
    if pct > -0.5:
        return "#FCA5A5"
    if pct > -2:
        return "#F87171"
    return "#EF4444"


def _pct_bg(pct: float) -> str:
    """Return background color for heatmap cells."""
    if pct > 2:
        return "#166534"
    if pct > 0.5:
        return "#15803D"
    if pct > 0:
        return "#14532D80"
    if pct == 0:
        return COLORS["card"]
    if pct > -0.5:
        return "#7F1D1D80"
    if pct > -2:
        return "#991B1B"
    return "#7F1D1D"


# ─────────────────────────────────────────────────────────────
#  INDEX PERFORMANCE STRIP
# ─────────────────────────────────────────────────────────────
def index_strip(index_data: list[dict]):
    """Render a horizontal strip of major index performances.

    Args:
        index_data: list of {"name": str, "price": float, "change_pct": float}
    """
    if not index_data:
        return

    items_html = ""
    for item in index_data:
        name = item.get("name", "")
        price = item.get("price", 0)
        pct = item.get("change_pct", 0)
        color = _pct_color(pct)
        arrow = "▲" if pct >= 0 else "▼"
        price_str = f"{price:,.2f}" if price < 10000 else f"{price:,.0f}"

        items_html += (
            f'<div style="display:flex;flex-direction:column;align-items:center;padding:0 16px;'
            f'border-right:1px solid {COLORS["border"]};min-width:90px;">'
            f'<div style="font-size:10px;color:{COLORS["text_muted"]};text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-bottom:2px;">{name}</div>'
            f'<div style="font-size:14px;color:{COLORS["text"]};font-weight:600;">{price_str}</div>'
            f'<div style="font-size:11px;color:{color};font-weight:600;">{arrow} {pct:+.2f}%</div>'
            f'</div>'
        )

    st.markdown(f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};border-radius:14px;padding:12px 4px;margin-bottom:16px;overflow-x:auto;"><div style="display:flex;align-items:center;justify-content:space-around;min-width:fit-content;">{items_html}</div></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  SECTOR HEATMAP — treemap-style colored grid
# ─────────────────────────────────────────────────────────────
def sector_heatmap(sector_data: list[dict]):
    """Render a finviz-style sector heatmap.

    Args:
        sector_data: list of {"sector": str, "change_pct": float, "tickers": list[dict]}
                     Each ticker: {"symbol": str, "change_pct": float}
    """
    if not sector_data:
        return

    st.markdown(f'<div style="font-size:16px;font-weight:600;color:{COLORS["text"]};margin-bottom:10px;">Sector Performance</div>', unsafe_allow_html=True)

    grid_html = ""
    for sector in sector_data:
        name = sector.get("sector", "")
        pct = sector.get("change_pct", 0)
        bg = _pct_bg(pct)
        color = _pct_color(pct)
        tickers = sector.get("tickers", [])

        # Build mini ticker cells inside the sector
        ticker_cells = ""
        for t in tickers[:8]:
            t_sym = t.get("symbol", "")
            t_pct = t.get("change_pct", 0)
            t_color = _pct_color(t_pct)
            t_bg = _pct_bg(t_pct)
            ticker_cells += (
                f'<div style="background:{t_bg};padding:4px 6px;border-radius:4px;text-align:center;min-width:48px;">'
                f'<div style="font-size:9px;color:#fff;font-weight:600;opacity:0.9;">{t_sym}</div>'
                f'<div style="font-size:10px;color:{t_color};font-weight:700;">{t_pct:+.1f}%</div></div>'
            )

        grid_html += (
            f'<div style="background:{bg};border-radius:10px;padding:10px 12px;min-width:140px;flex:1;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
            f'<span style="font-size:12px;color:#fff;font-weight:600;">{name}</span>'
            f'<span style="font-size:12px;color:{color};font-weight:700;">{pct:+.2f}%</span></div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:3px;">{ticker_cells}</div></div>'
        )

    st.markdown(f'<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));gap:8px;margin-bottom:16px;">{grid_html}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  TOP GAINERS / LOSERS
# ─────────────────────────────────────────────────────────────
def gainers_losers(gainers: list[dict], losers: list[dict], max_items: int = 5):
    """Render top gainers and losers side by side.

    Args:
        gainers: list of {"symbol": str, "price": float, "change_pct": float}
        losers: same format
    """
    col1, col2 = st.columns(2)

    with col1:
        rows_html = ""
        for i, g in enumerate(gainers[:max_items]):
            sym = g.get("symbol", "")
            price = g.get("price", 0)
            pct = g.get("change_pct", 0)
            bg = f'{COLORS["card_hover"]}' if i % 2 == 0 else "transparent"
            rows_html += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:{bg};border-radius:6px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:11px;color:{COLORS["text_dim"]};width:16px;">{i+1}</span>'
                f'<span style="font-size:13px;color:{COLORS["text"]};font-weight:600;">{sym}</span></div>'
                f'<div style="display:flex;align-items:center;gap:12px;">'
                f'<span style="font-size:12px;color:{COLORS["text_secondary"]};">${price:.2f}</span>'
                f'<span style="font-size:12px;color:#22C55E;font-weight:600;min-width:60px;text-align:right;">▲ {pct:+.2f}%</span></div></div>'
            )
        st.markdown(f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};border-radius:14px;padding:14px;"><div style="font-size:13px;font-weight:600;color:#22C55E;margin-bottom:8px;display:flex;align-items:center;gap:6px;"><span style="font-size:16px;">🟢</span> Top Gainers</div>{rows_html}</div>', unsafe_allow_html=True)

    with col2:
        rows_html = ""
        for i, l in enumerate(losers[:max_items]):
            sym = l.get("symbol", "")
            price = l.get("price", 0)
            pct = l.get("change_pct", 0)
            bg = f'{COLORS["card_hover"]}' if i % 2 == 0 else "transparent"
            rows_html += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:{bg};border-radius:6px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:11px;color:{COLORS["text_dim"]};width:16px;">{i+1}</span>'
                f'<span style="font-size:13px;color:{COLORS["text"]};font-weight:600;">{sym}</span></div>'
                f'<div style="display:flex;align-items:center;gap:12px;">'
                f'<span style="font-size:12px;color:{COLORS["text_secondary"]};">${price:.2f}</span>'
                f'<span style="font-size:12px;color:#EF4444;font-weight:600;min-width:60px;text-align:right;">▼ {pct:.2f}%</span></div></div>'
            )
        st.markdown(f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};border-radius:14px;padding:14px;"><div style="font-size:13px;font-weight:600;color:#EF4444;margin-bottom:8px;display:flex;align-items:center;gap:6px;"><span style="font-size:16px;">🔴</span> Top Losers</div>{rows_html}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  DATA FETCHING HELPERS
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_index_data() -> list[dict]:
    """Fetch current prices and daily changes for major indices."""
    try:
        import yfinance as yf
        results = []
        symbols = [s[1] for s in INDEX_SYMBOLS]
        names = [s[0] for s in INDEX_SYMBOLS]
        tickers = yf.Tickers(" ".join(symbols))
        for sym, name in zip(symbols, names):
            try:
                t = tickers.tickers.get(sym.replace("^", "").replace("=", "").replace("-", "").replace(".", ""), None)
                if t is None:
                    # Try direct
                    t = yf.Ticker(sym)
                import math
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    close = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2])
                    if not math.isnan(close) and not math.isnan(prev) and prev > 0:
                        pct = ((close - prev) / prev) * 100
                        results.append({"name": name, "price": close, "change_pct": round(pct, 2)})
                elif len(hist) == 1:
                    close = float(hist["Close"].iloc[-1])
                    if not math.isnan(close):
                        results.append({"name": name, "price": close, "change_pct": 0})
            except Exception:
                pass
        return results
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sector_performance() -> list[dict]:
    """Fetch sector ETF performance and map tickers."""
    try:
        import yfinance as yf
        results = []
        etf_symbols = list(SECTOR_ETFS.values())
        sector_names = list(SECTOR_ETFS.keys())

        for name, etf in zip(sector_names, etf_symbols):
            try:
                t = yf.Ticker(etf)
                import math
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    close = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2])
                    if not math.isnan(close) and not math.isnan(prev) and prev > 0:
                        pct = ((close - prev) / prev) * 100
                    else:
                        pct = 0
                else:
                    pct = 0
                results.append({
                    "sector": name,
                    "change_pct": round(pct, 2),
                    "etf": etf,
                    "tickers": [],
                })
            except Exception:
                results.append({"sector": name, "change_pct": 0, "etf": etf, "tickers": []})

        return results
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_gainers_losers() -> tuple[list[dict], list[dict]]:
    """Fetch top gainers and losers from the stock universe."""
    try:
        import yfinance as yf
        from config import settings

        # Use a subset to keep it fast
        universe = settings.TICKER_UNIVERSE[:40]
        all_data = []
        tickers_str = " ".join(universe)
        data = yf.download(tickers_str, period="2d", group_by="ticker", progress=False, threads=True)

        for sym in universe:
            try:
                if len(universe) > 1:
                    sym_data = data[sym] if sym in data.columns.get_level_values(0) else None
                else:
                    sym_data = data

                if sym_data is not None and len(sym_data) >= 2:
                    import math
                    close = float(sym_data["Close"].iloc[-1])
                    prev = float(sym_data["Close"].iloc[-2])
                    if prev > 0 and not math.isnan(close) and not math.isnan(prev):
                        pct = ((close - prev) / prev) * 100
                        if not math.isnan(pct):
                            all_data.append({"symbol": sym, "price": round(close, 2), "change_pct": round(pct, 2)})
            except Exception:
                pass

        all_data.sort(key=lambda x: x["change_pct"], reverse=True)
        gainers = all_data[:8]
        losers = list(reversed(all_data[-8:])) if len(all_data) >= 8 else list(reversed(all_data))
        return gainers, losers
    except Exception:
        return [], []

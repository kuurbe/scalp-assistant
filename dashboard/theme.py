"""
Clean light dashboard design tokens — inspired by the soft card-based reference UI.
Light background, white cards with soft shadows, pastel gradients, rounded corners.
"""

# ─── Color Palette (Light Theme) ───
COLORS = {
    "bg": "#F0F2F5",
    "bg_secondary": "#E8EAF0",
    "bg_elevated": "#FFFFFF",
    "card": "#FFFFFF",
    "card_solid": "#FFFFFF",
    "card_hover": "#F5F6FA",
    "accent": "#4A6CF7",
    "accent_hover": "#3D5BD9",
    "accent_light": "rgba(74,108,247,0.08)",
    "text": "#1A1D29",
    "text_secondary": "#5A607F",
    "text_muted": "#8B91A8",
    "text_dim": "#B0B5C9",
    "success": "#22C55E",
    "success_bg": "rgba(34,197,94,0.10)",
    "danger": "#EF4444",
    "danger_bg": "rgba(239,68,68,0.10)",
    "warning": "#F59E0B",
    "warning_bg": "rgba(245,158,11,0.10)",
    "info": "#3B82F6",
    "border": "rgba(0,0,0,0.06)",
    "border_light": "rgba(0,0,0,0.04)",
    "divider": "rgba(0,0,0,0.06)",
}

FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif"

# ─── Reusable CSS Classes ───
# Single-line to avoid Streamlit markdown HTML parsing issues (CARD_CSS MUST be single-line!)
CARD_CSS = "background:#FFFFFF;border:1px solid rgba(0,0,0,0.06);border-radius:20px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);"

# Gradient card styles for Simple mode (soft pastel backgrounds like reference design)
CARD_GRADIENT_GREEN = "background:linear-gradient(135deg, #E8FFF0 0%, #F0FFF4 50%, #FFFFFF 100%);border:1px solid rgba(34,197,94,0.12);border-radius:20px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);"

CARD_GRADIENT_RED = "background:linear-gradient(135deg, #FFF0F0 0%, #FFF5F5 50%, #FFFFFF 100%);border:1px solid rgba(239,68,68,0.12);border-radius:20px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);"

CARD_GRADIENT_BLUE = "background:linear-gradient(135deg, #EBF0FF 0%, #F0F4FF 50%, #FFFFFF 100%);border:1px solid rgba(74,108,247,0.12);border-radius:20px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);"

CARD_GRADIENT_ORANGE = "background:linear-gradient(135deg, #FFF6E5 0%, #FFFAF0 50%, #FFFFFF 100%);border:1px solid rgba(245,158,11,0.12);border-radius:20px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);"

PILL_BUTTON_CSS = f"""
    background: {COLORS['accent']};
    color: white;
    border: none;
    border-radius: 980px;
    padding: 10px 24px;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
"""

# ─── Full Page CSS Override for Streamlit ───
GLOBAL_CSS = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Root overrides */
    .stApp {{
        background-color: {COLORS['bg']} !important;
        color: {COLORS['text']} !important;
        font-family: {FONT} !important;
    }}

    /* Main content area */
    .main .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px !important;
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background-color: #FFFFFF !important;
        border-right: 1px solid {COLORS['border']} !important;
    }}
    [data-testid="stSidebar"] .stRadio label {{
        color: {COLORS['text_secondary']} !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        padding: 8px 16px !important;
        border-radius: 10px !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stSidebar"] .stRadio label:hover {{
        color: {COLORS['text']} !important;
        background: {COLORS['bg']} !important;
    }}
    [data-testid="stSidebar"] .stRadio [data-checked="true"] label {{
        color: {COLORS['accent']} !important;
        background: {COLORS['accent_light']} !important;
        font-weight: 500 !important;
    }}

    /* Headers */
    h1, h2, h3, h4, h5, h6 {{
        color: {COLORS['text']} !important;
        font-family: {FONT} !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }}
    h1 {{ font-size: 34px !important; font-weight: 700 !important; }}
    h2 {{ font-size: 28px !important; }}
    h3 {{ font-size: 22px !important; }}

    /* Metric cards */
    [data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid {COLORS['border']};
        border-radius: 20px;
        padding: 24px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    [data-testid="stMetricValue"] {{
        font-size: 36px !important;
        font-weight: 300 !important;
        letter-spacing: -0.02em !important;
        color: {COLORS['text']} !important;
    }}
    [data-testid="stMetricLabel"] {{
        font-size: 13px !important;
        color: {COLORS['text_muted']} !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }}
    [data-testid="stMetricDelta"] > div {{
        font-size: 14px !important;
    }}

    /* DataFrames / Tables */
    .stDataFrame {{
        border-radius: 16px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .stDataFrame table {{
        background: #FFFFFF !important;
        color: {COLORS['text']} !important;
    }}
    .stDataFrame thead tr th {{
        background: {COLORS['bg']} !important;
        color: {COLORS['text_muted']} !important;
        font-size: 12px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        font-weight: 500 !important;
        border-bottom: 1px solid {COLORS['border']} !important;
    }}
    .stDataFrame tbody tr td {{
        border-bottom: 1px solid {COLORS['border_light']} !important;
        font-size: 14px !important;
    }}
    .stDataFrame tbody tr:hover td {{
        background: {COLORS['card_hover']} !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px !important;
        background: transparent !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {COLORS['text_muted']} !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        border-radius: 10px !important;
        padding: 8px 20px !important;
        background: transparent !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: {COLORS['accent']} !important;
        background: {COLORS['accent_light']} !important;
        font-weight: 500 !important;
    }}

    /* Expanders */
    .streamlit-expanderHeader {{
        background: #FFFFFF !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 16px !important;
        color: {COLORS['text']} !important;
        font-size: 15px !important;
    }}

    /* Selectbox / inputs */
    .stSelectbox > div > div {{
        background: #FFFFFF !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 12px !important;
        color: {COLORS['text']} !important;
    }}

    /* Buttons — Primary (default) */
    .stButton > button {{
        background: {COLORS['accent']} !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 10px 24px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        letter-spacing: -0.01em !important;
        transition: background 0.2s ease, box-shadow 0.2s ease !important;
        box-shadow: 0 1px 3px rgba(74,108,247,0.20);
        cursor: pointer !important;
        min-height: 40px !important;
    }}
    .stButton > button:hover {{
        background: {COLORS['accent_hover']} !important;
        box-shadow: 0 3px 10px rgba(74,108,247,0.30);
    }}
    .stButton > button:active {{
        background: #3350C4 !important;
        box-shadow: 0 1px 2px rgba(74,108,247,0.15);
    }}
    .stButton > button:focus-visible {{
        outline: 2px solid {COLORS['accent']} !important;
        outline-offset: 2px !important;
    }}

    /* Buttons — Secondary (type="secondary") */
    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="baseButton-secondary"] {{
        background: {COLORS['card']} !important;
        color: {COLORS['text']} !important;
        border: 1px solid {COLORS['border']} !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    }}
    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="baseButton-secondary"]:hover {{
        background: {COLORS['card_hover']} !important;
        border-color: rgba(0,0,0,0.12) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06) !important;
    }}

    /* Toggle / radio pill buttons */
    .stRadio > div {{
        gap: 4px !important;
    }}
    .stRadio > div > label {{
        border-radius: 10px !important;
        transition: background 0.15s ease !important;
    }}

    /* Glass card helper class */
    .glass-card {{
        {CARD_CSS}
    }}

    /* Score colors */
    .score-high {{ color: {COLORS['success']}; font-weight: 600; }}
    .score-mid {{ color: {COLORS['warning']}; font-weight: 500; }}
    .score-low {{ color: {COLORS['danger']}; font-weight: 400; }}

    /* Gain/Loss colors */
    .gain {{ color: {COLORS['success']}; }}
    .loss {{ color: {COLORS['danger']}; }}

    /* Divider */
    hr {{
        border: none !important;
        border-top: 1px solid {COLORS['divider']} !important;
        margin: 24px 0 !important;
    }}

    /* Hide Streamlit branding but keep sidebar toggle */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{
        background: {COLORS['bg']} !important;
    }}

    /* Plotly chart background override */
    .js-plotly-plot .plotly .main-svg {{
        background: transparent !important;
    }}

    /* ─── Responsive: Mobile & Tablet ─── */
    @media (max-width: 768px) {{
        .main .block-container {{
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            max-width: 100% !important;
        }}
        h1 {{ font-size: 24px !important; }}
        h2 {{ font-size: 20px !important; }}
        h3 {{ font-size: 17px !important; }}
        [data-testid="stMetricValue"] {{
            font-size: 24px !important;
        }}
        [data-testid="stMetric"] {{
            padding: 14px !important;
            border-radius: 14px;
        }}
        .stDataFrame thead tr th {{
            font-size: 10px !important;
        }}
        .stDataFrame tbody tr td {{
            font-size: 12px !important;
        }}
        .stButton > button {{
            padding: 8px 18px !important;
            font-size: 13px !important;
        }}
        [data-testid="stSidebar"] {{
            min-width: 200px !important;
            max-width: 200px !important;
        }}
    }}

    @media (max-width: 480px) {{
        .main .block-container {{
            padding-left: 0.25rem !important;
            padding-right: 0.25rem !important;
        }}
        h1 {{ font-size: 20px !important; }}
        [data-testid="stMetricValue"] {{
            font-size: 20px !important;
        }}
    }}

    /* ─── Smooth transitions for all cards ─── */
    [data-testid="stMetric"],
    .glass-card {{
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }}

    /* ─── Tooltip styles for glossary ─── */
    .tip {{
        position: relative;
        display: inline;
        border-bottom: 1px dotted {COLORS['text_muted']};
        cursor: help;
    }}
    .tip .tiptext {{
        visibility: hidden;
        width: 260px;
        background: #FFFFFF;
        color: {COLORS['text_secondary']};
        font-size: 12px;
        line-height: 1.4;
        border-radius: 10px;
        padding: 12px;
        position: absolute;
        z-index: 999;
        bottom: 125%;
        left: 50%;
        margin-left: -130px;
        border: 1px solid {COLORS['border']};
        box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        pointer-events: none;
    }}
    .tip:hover .tiptext {{
        visibility: visible;
    }}

    /* ─── Loading shimmer for cards ─── */
    @keyframes shimmer {{
        0% {{ background-position: -200px 0; }}
        100% {{ background-position: 200px 0; }}
    }}
    .loading-card {{
        background: linear-gradient(90deg, #F0F2F5 0%, #FFFFFF 50%, #F0F2F5 100%);
        background-size: 400px 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 20px;
        height: 100px;
    }}
</style>
"""


def score_color(score: float) -> str:
    """Return the appropriate color for a score value."""
    if score >= 70:
        return COLORS["success"]
    elif score >= 50:
        return COLORS["warning"]
    return COLORS["danger"]


def change_color(pct: float) -> str:
    """Return green for positive change, red for negative."""
    return COLORS["success"] if pct >= 0 else COLORS["danger"]


def urgency_color(urgency: str) -> str:
    """Return color for urgency level."""
    return {
        "HIGH": COLORS["danger"],
        "MEDIUM": COLORS["warning"],
        "LOW": COLORS["success"],
    }.get(urgency, COLORS["text_muted"])

"""
Sefirot dashboard page — Tree of Life behavioral finance visualization.
Simple mode: 3 energy cards + narrative.
Advanced mode: Full Tree of Life SVG + per-ticker selector.
"""
import streamlit as st
from dashboard.theme import COLORS, CARD_CSS, FONT


def render():
    """Main render entry point."""
    simple = st.session_state.get("view_mode", "Simple") == "Simple"

    st.markdown(f"""
    <div style="margin-bottom:24px;">
        <div style="font-size:26px;font-weight:700;color:{COLORS['text']};letter-spacing:-0.02em;font-family:{FONT};">
            Sefirot
        </div>
        <div style="font-size:13px;color:{COLORS['text_secondary']};margin-top:4px;">
            Tree of Life behavioral finance — crowd psychology mapped to Kabbalistic emanations
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Get scored tickers from session state
    scored = st.session_state.get("scored_tickers", [])

    if not scored:
        st.markdown(f"""
        <div style="{CARD_CSS}text-align:center;padding:60px 28px;color:{COLORS['text_dim']};">
            Run a market scan first to populate Sefirot data.
        </div>
        """, unsafe_allow_html=True)
        return

    # Ticker selector
    tickers = [s.ticker for s in scored]
    selected = st.selectbox("Select Ticker", tickers, key="sefirot_ticker")

    pick = next((s for s in scored if s.ticker == selected), scored[0])

    # Compute Tree of Life state
    try:
        from analysis.sefirot_mapper import map_sefirot_state, get_dominant_pillar, get_sefirot_narrative, get_sefirot_score
        state = map_sefirot_state(pick)
        pillar = get_dominant_pillar(state)
        narrative = get_sefirot_narrative(state, pick.ticker)
        tree_score = get_sefirot_score(state)
    except Exception:
        state = {}
        pillar = "Unknown"
        narrative = "Sefirot data not available — run a scan with sefirot features enabled."
        tree_score = 0

    if simple:
        _render_simple(pick, state, pillar, narrative, tree_score)
    else:
        _render_advanced(pick, state, pillar, narrative, tree_score)


def _render_simple(pick, state: dict, pillar: str, narrative: str, tree_score: float):
    """Simple mode: 3 energy cards + narrative."""

    # Score card
    score_color = COLORS["success"] if tree_score >= 60 else (COLORS["warning"] if tree_score >= 40 else COLORS["danger"])
    st.markdown(f"""
    <div style="{CARD_CSS}margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">
                    Tree of Life Score
                </div>
                <div style="font-size:36px;font-weight:700;color:{score_color};margin-top:4px;">
                    {tree_score:.0f}
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;">
                    Dominant Pillar
                </div>
                <div style="font-size:15px;font-weight:600;color:{COLORS['text']};margin-top:4px;">
                    {pillar}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 3 energy cards
    cols = st.columns(3)

    # Card 1: Market Energy (Chesed/Gevurah)
    chesed = state.get("Chesed", {}).get("level", 0)
    gevurah = state.get("Gevurah", {}).get("level", 0)
    energy_label = "Expansion" if chesed > gevurah else ("Contraction" if gevurah > chesed else "Neutral")
    energy_val = chesed - gevurah
    energy_color = COLORS["success"] if energy_val > 0 else (COLORS["danger"] if energy_val < 0 else COLORS["text_muted"])

    with cols[0]:
        st.markdown(f"""
        <div style="{CARD_CSS}text-align:center;">
            <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">
                Market Energy
            </div>
            <div style="font-size:11px;color:{COLORS['text_dim']};margin-top:2px;">
                Chesed / Gevurah
            </div>
            <div style="font-size:28px;font-weight:700;color:{energy_color};margin-top:12px;">
                {energy_label}
            </div>
            <div style="display:flex;justify-content:center;gap:20px;margin-top:12px;">
                <div>
                    <div style="font-size:10px;color:{COLORS['text_dim']};">Chesed</div>
                    <div style="font-size:16px;font-weight:600;color:{COLORS['success']};">{chesed}</div>
                </div>
                <div>
                    <div style="font-size:10px;color:{COLORS['text_dim']};">Gevurah</div>
                    <div style="font-size:16px;font-weight:600;color:{COLORS['danger']};">{gevurah}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Card 2: Balance State (Tiferet)
    tiferet = state.get("Tiferet", {}).get("level", 0)
    tif_color = COLORS["accent"] if tiferet >= 50 else COLORS["warning"]
    tif_label = state.get("Tiferet", {}).get("label", "Unknown")

    with cols[1]:
        st.markdown(f"""
        <div style="{CARD_CSS}text-align:center;">
            <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">
                Balance State
            </div>
            <div style="font-size:11px;color:{COLORS['text_dim']};margin-top:2px;">
                Tiferet
            </div>
            <div style="font-size:28px;font-weight:700;color:{tif_color};margin-top:12px;">
                {tiferet}
            </div>
            <div style="font-size:13px;color:{COLORS['text_secondary']};margin-top:4px;">
                {tif_label}
            </div>
            <div style="margin-top:10px;width:100%;height:6px;border-radius:3px;background:{COLORS['border']};">
                <div style="width:{tiferet}%;height:100%;border-radius:3px;background:{tif_color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Card 3: Signal Clarity (Hod)
    hod = state.get("Hod", {}).get("level", 0)
    hod_color = COLORS["success"] if hod >= 60 else (COLORS["warning"] if hod >= 35 else COLORS["text_muted"])
    hod_label = state.get("Hod", {}).get("label", "Unknown")

    with cols[2]:
        st.markdown(f"""
        <div style="{CARD_CSS}text-align:center;">
            <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">
                Signal Clarity
            </div>
            <div style="font-size:11px;color:{COLORS['text_dim']};margin-top:2px;">
                Hod
            </div>
            <div style="font-size:28px;font-weight:700;color:{hod_color};margin-top:12px;">
                {hod}
            </div>
            <div style="font-size:13px;color:{COLORS['text_secondary']};margin-top:4px;">
                {hod_label}
            </div>
            <div style="margin-top:10px;width:100%;height:6px;border-radius:3px;background:{COLORS['border']};">
                <div style="width:{hod}%;height:100%;border-radius:3px;background:{hod_color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Narrative card
    st.markdown(f"""
    <div style="{CARD_CSS}margin-top:16px;">
        <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;margin-bottom:8px;">
            Behavioral Reading
        </div>
        <div style="font-size:14px;color:{COLORS['text']};line-height:1.6;">
            {narrative}
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_advanced(pick, state: dict, pillar: str, narrative: str, tree_score: float):
    """Advanced mode: Full Tree of Life SVG + all 10 Sefirot details."""

    # Tree of Life SVG
    svg = _build_tree_svg(state, pillar)
    st.markdown(f"""
    <div style="{CARD_CSS}text-align:center;margin-bottom:16px;">
        <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;margin-bottom:16px;">
            Tree of Life — {pick.ticker}
        </div>
        {svg}
        <div style="font-size:13px;color:{COLORS['text_secondary']};margin-top:16px;">
            Dominant: <strong>{pillar}</strong> | Score: <strong>{tree_score:.0f}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Narrative
    st.markdown(f"""
    <div style="{CARD_CSS}margin-bottom:16px;">
        <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;margin-bottom:8px;">
            Behavioral Reading
        </div>
        <div style="font-size:14px;color:{COLORS['text']};line-height:1.6;">{narrative}</div>
    </div>
    """, unsafe_allow_html=True)

    # All 10 Sefirot detail table
    _render_sefirot_table(state)


def _build_tree_svg(state: dict, pillar: str) -> str:
    """Build an SVG of the Tree of Life with colored nodes."""

    # Traditional Tree of Life layout (x, y positions for each Sefirah)
    # Normalized to a 300x440 viewBox
    positions = {
        "Keter":    (150, 30),
        "Chokhmah": (230, 90),
        "Binah":    (70, 90),
        "Chesed":   (230, 180),
        "Gevurah":  (70, 180),
        "Tiferet":  (150, 230),
        "Netzach":  (230, 310),
        "Hod":      (70, 310),
        "Yesod":    (150, 360),
        "Malkuth":  (150, 420),
    }

    # Paths (connections between Sefirot)
    paths = [
        ("Keter", "Chokhmah"), ("Keter", "Binah"),
        ("Chokhmah", "Binah"), ("Chokhmah", "Chesed"), ("Chokhmah", "Tiferet"),
        ("Binah", "Gevurah"), ("Binah", "Tiferet"),
        ("Chesed", "Gevurah"), ("Chesed", "Tiferet"), ("Chesed", "Netzach"),
        ("Gevurah", "Tiferet"), ("Gevurah", "Hod"),
        ("Tiferet", "Netzach"), ("Tiferet", "Hod"), ("Tiferet", "Yesod"),
        ("Netzach", "Hod"), ("Netzach", "Yesod"),
        ("Hod", "Yesod"),
        ("Yesod", "Malkuth"),
    ]

    # Pillar colors
    right_sefirot = {"Chokhmah", "Chesed", "Netzach"}
    left_sefirot = {"Binah", "Gevurah", "Hod"}

    def _node_color(name: str, level: int) -> str:
        if level >= 65:
            if name in right_sefirot:
                return COLORS["success"]
            elif name in left_sefirot:
                return COLORS["danger"]
            return COLORS["accent"]
        elif level >= 35:
            return COLORS["warning"]
        return COLORS["text_dim"]

    svg_lines = [
        '<svg width="300" height="450" viewBox="0 0 300 450" xmlns="http://www.w3.org/2000/svg">',
    ]

    # Draw paths
    for s1, s2 in paths:
        x1, y1 = positions[s1]
        x2, y2 = positions[s2]
        svg_lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{COLORS["border"]}" stroke-width="1.5" opacity="0.5"/>'
        )

    # Draw nodes
    for name, (cx, cy) in positions.items():
        info = state.get(name, {"level": 0, "label": "", "state": "dormant"})
        level = info["level"]
        color = _node_color(name, level)
        radius = 22

        # Glow for active nodes
        if info["state"] == "active":
            svg_lines.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius + 6}" fill="{color}" opacity="0.15"/>'
            )

        svg_lines.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="white" stroke="{color}" stroke-width="2.5"/>'
        )
        # Level number
        svg_lines.append(
            f'<text x="{cx}" y="{cy + 1}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="12" font-weight="700" fill="{color}">{level}</text>'
        )
        # Name label below
        svg_lines.append(
            f'<text x="{cx}" y="{cy + radius + 14}" text-anchor="middle" '
            f'font-size="9" fill="{COLORS["text_muted"]}">{name}</text>'
        )

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)


def _render_sefirot_table(state: dict):
    """Render a detail table of all 10 Sefirot."""
    rows_html = ""
    meanings = {
        "Keter": "Crown — system confidence",
        "Chokhmah": "Wisdom — pattern recognition",
        "Binah": "Understanding — analytical strength",
        "Chesed": "Mercy — expansion force",
        "Gevurah": "Severity — contraction force",
        "Tiferet": "Beauty — emotional balance",
        "Netzach": "Victory — trend persistence",
        "Hod": "Splendor — signal clarity",
        "Yesod": "Foundation — execution readiness",
        "Malkuth": "Kingdom — predicted outcome",
    }

    for name in ["Keter", "Chokhmah", "Binah", "Chesed", "Gevurah",
                  "Tiferet", "Netzach", "Hod", "Yesod", "Malkuth"]:
        info = state.get(name, {"level": 0, "label": "—", "state": "dormant"})
        level = info["level"]
        label = info["label"]
        st_state = info["state"]
        meaning = meanings.get(name, "")

        if st_state == "active":
            state_color = COLORS["success"]
            state_bg = COLORS["success_bg"]
        elif st_state == "neutral":
            state_color = COLORS["warning"]
            state_bg = COLORS["warning_bg"]
        else:
            state_color = COLORS["text_dim"]
            state_bg = "rgba(0,0,0,0.04)"

        bar_color = state_color

        rows_html += f"""
        <div style="display:flex;align-items:center;padding:10px 16px;border-bottom:1px solid {COLORS['border']};">
            <div style="min-width:90px;font-weight:600;font-size:13px;color:{COLORS['text']};">{name}</div>
            <div style="min-width:180px;font-size:11px;color:{COLORS['text_dim']};">{meaning}</div>
            <div style="min-width:50px;font-weight:600;font-size:14px;color:{state_color};text-align:center;">{level}</div>
            <div style="flex:1;padding:0 12px;">
                <div style="width:100%;height:6px;border-radius:3px;background:{COLORS['border']};">
                    <div style="width:{level}%;height:100%;border-radius:3px;background:{bar_color};"></div>
                </div>
            </div>
            <div style="min-width:80px;">
                <span style="background:{state_bg};color:{state_color};padding:2px 10px;border-radius:6px;font-size:10px;font-weight:700;text-transform:uppercase;">
                    {label}
                </span>
            </div>
        </div>
        """

    st.markdown(f"""
    <div style="{CARD_CSS}overflow:hidden;padding:0;">
        <div style="padding:16px 16px 8px 16px;">
            <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">
                All Sefirot
            </div>
        </div>
        {rows_html}
    </div>
    """, unsafe_allow_html=True)

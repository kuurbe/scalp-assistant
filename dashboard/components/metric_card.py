"""
Metric card component — clean card-based design matching reference UI.
Features: icon circle, large hero number, inline sparkline, delta badge.
"""
import streamlit as st
from dashboard.theme import COLORS

# ─── Icon SVG Paths (simple, clean line icons) ───
_ICONS = {
    "earnings": '<path d="M12 2v20M2 12h20M7 7l5-5 5 5M7 17l5 5 5-5"/>',
    "dollar": '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
    "chart": '<path d="M3 3v18h18M7 16l4-4 4 4 5-6"/>',
    "users": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
    "alert": '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/>',
    "trending": '<path d="M23 6l-9.5 9.5-5-5L1 18M17 6h6v6"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10"/>',
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "bar": '<path d="M18 20V10M12 20V4M6 20v-6"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    "default": '<circle cx="12" cy="12" r="10"/>',
}


def _icon_svg(icon_name: str, color: str = None) -> str:
    """Return an SVG icon wrapped in a circle background."""
    c = color or COLORS["text_muted"]
    path = _ICONS.get(icon_name, _ICONS["default"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
        f'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{path}</svg>'
    )


def _delta_badge(delta: str, delta_color: str = None, vs_label: str = "") -> str:
    """Render a rounded delta badge like the reference design."""
    if delta is None:
        return ""
    is_positive = not str(delta).lstrip().startswith("-")
    dc = delta_color or (COLORS["success"] if is_positive else COLORS["danger"])
    bg = dc.replace(")", ",0.10)").replace("rgb", "rgba") if "rgb" in dc else f"rgba({int(dc[1:3],16)},{int(dc[3:5],16)},{int(dc[5:7],16)},0.10)"
    arrow = "↑" if is_positive else "↓"
    vs_text = f'<span style="color:{COLORS["text_muted"]};font-size:12px;margin-left:6px;">{vs_label}</span>' if vs_label else ""
    return (
        f'<div style="display:flex;align-items:center;margin-top:10px;">'
        f'<span style="background:{bg};color:{dc};padding:3px 10px;border-radius:6px;'
        f'font-size:12px;font-weight:600;">{arrow} {delta}</span>'
        f'{vs_text}'
        f'</div>'
    )


def _mini_sparkline_svg(values: list, color: str, width: int = 80, height: int = 36) -> str:
    """Render a tiny inline SVG sparkline."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    points = []
    for i, v in enumerate(values):
        x = i / (len(values) - 1) * width
        y = height - ((v - mn) / rng * (height - 4) + 2)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def metric_card(label: str, value: str, delta: str = None,
                delta_color: str = None, prefix: str = "", suffix: str = "",
                icon: str = None, sparkline_data: list = None,
                vs_label: str = "", subtitle: str = ""):
    """Render a metric card matching the reference design.

    Args:
        label: Small uppercase label (e.g., "Earning")
        value: Large hero number (e.g., "$128k")
        delta: Change text (e.g., "36.8%")
        delta_color: Color for delta badge
        prefix: Text before value
        suffix: Text after value
        icon: Icon name from _ICONS dict
        sparkline_data: List of floats for inline mini chart
        vs_label: Text after delta badge (e.g., "vs last year")
        subtitle: Small text below label
    """
    # Icon circle
    icon_html = ""
    if icon:
        icon_color = delta_color or COLORS["text_muted"]
        icon_bg = icon_color.replace(")", ",0.08)").replace("rgb", "rgba") if "rgb" in icon_color else f"rgba({int(icon_color[1:3],16)},{int(icon_color[3:5],16)},{int(icon_color[5:7],16)},0.08)"
        icon_html = (
            f'<div style="width:44px;height:44px;border-radius:50%;background:{icon_bg};'
            f'display:flex;align-items:center;justify-content:center;margin-bottom:14px;">'
            f'{_icon_svg(icon, icon_color)}'
            f'</div>'
        )

    # Subtitle
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<div style="font-size:11px;color:{COLORS["text_dim"]};margin-top:2px;">{subtitle}</div>'

    # Sparkline
    spark_html = ""
    if sparkline_data and len(sparkline_data) >= 2:
        spark_color = delta_color or (COLORS["success"] if sparkline_data[-1] >= sparkline_data[0] else COLORS["danger"])
        spark_html = (
            f'<div style="position:absolute;right:20px;bottom:50px;">'
            f'{_mini_sparkline_svg(sparkline_data, spark_color, width=90, height=40)}'
            f'</div>'
        )

    # Delta badge
    delta_html = _delta_badge(delta, delta_color, vs_label)

    html = (
        f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
        f'border-radius:20px;padding:24px;position:relative;overflow:hidden;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.04);transition:transform 0.15s ease,box-shadow 0.15s ease;">'
        f'{icon_html}'
        f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:8px;">{label}</div>'
        f'{subtitle_html}'
        f'<div style="font-size:38px;font-weight:300;color:{COLORS["text"]};'
        f'letter-spacing:-0.02em;line-height:1.1;">{prefix}{value}{suffix}</div>'
        f'{spark_html}'
        f'{delta_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def mini_metric(label: str, value: str, color: str = None):
    """Smaller inline metric."""
    c = color or COLORS["text"]
    html = (
        f'<div style="padding:12px 0;">'
        f'<span style="font-size:11px;color:{COLORS["text_muted"]};text-transform:uppercase;'
        f'letter-spacing:0.05em;">{label}</span><br>'
        f'<span style="font-size:24px;font-weight:300;color:{c};">{value}</span>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def overview_card(title: str, cards_data: list):
    """Render a grouped 'Overview' card containing multiple metrics side-by-side.

    Args:
        title: Card group title (e.g., "Overview")
        cards_data: List of dicts with keys: label, value, delta, delta_color, icon, sparkline_data, vs_label
    """
    inner_html = ""
    for i, card in enumerate(cards_data):
        icon_name = card.get("icon", "default")
        icon_color = card.get("delta_color") or COLORS["text_muted"]
        icon_bg = f"rgba({int(icon_color[1:3],16)},{int(icon_color[3:5],16)},{int(icon_color[5:7],16)},0.08)" if icon_color.startswith("#") else "rgba(139,145,168,0.08)"

        icon_html = (
            f'<div style="width:40px;height:40px;border-radius:50%;background:{icon_bg};'
            f'display:flex;align-items:center;justify-content:center;margin-bottom:12px;">'
            f'{_icon_svg(icon_name, icon_color)}'
            f'</div>'
        )

        spark_html = ""
        spark_data = card.get("sparkline_data")
        if spark_data and len(spark_data) >= 2:
            sc = card.get("delta_color") or COLORS["success"]
            spark_html = f'<div style="margin-top:6px;">{_mini_sparkline_svg(spark_data, sc, width=70, height=30)}</div>'

        delta_html = _delta_badge(card.get("delta"), card.get("delta_color"), card.get("vs_label", ""))

        border_right = f"border-right:1px solid {COLORS['border']};" if i < len(cards_data) - 1 else ""

        inner_html += (
            f'<div style="flex:1;padding:0 20px;{border_right}">'
            f'{icon_html}'
            f'<div style="font-size:12px;color:{COLORS["text_muted"]};text-transform:uppercase;'
            f'letter-spacing:0.06em;margin-bottom:6px;">{card.get("label", "")}</div>'
            f'<div style="display:flex;align-items:flex-end;gap:12px;">'
            f'<div style="font-size:34px;font-weight:300;color:{COLORS["text"]};'
            f'letter-spacing:-0.02em;line-height:1.1;">{card.get("prefix", "")}{card.get("value", "—")}{card.get("suffix", "")}</div>'
            f'{spark_html}'
            f'</div>'
            f'{delta_html}'
            f'</div>'
        )

    html = (
        f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
        f'border-radius:20px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
        f'<div style="font-size:18px;font-weight:600;color:{COLORS["text"]};margin-bottom:20px;">{title}</div>'
        f'<div style="display:flex;align-items:flex-start;">'
        f'{inner_html}'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

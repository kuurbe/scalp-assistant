"""
Plotly chart helpers with Apple-style dark theme.
Transparent backgrounds, thin lines, minimal gridlines.
"""
import plotly.graph_objects as go
from dashboard.theme import COLORS


def apple_layout(title: str = "", height: int = 300, show_legend: bool = False) -> dict:
    """Base Plotly layout matching Apple design."""
    return dict(
        title=dict(text=title, font=dict(size=16, color=COLORS["text"], family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color=COLORS["text_muted"], size=12),
        height=height,
        margin=dict(l=40, r=20, t=40 if title else 20, b=30),
        showlegend=show_legend,
        xaxis=dict(
            gridcolor=COLORS["border_light"],
            zerolinecolor=COLORS["border"],
            tickfont=dict(size=11, color=COLORS["text_dim"]),
        ),
        yaxis=dict(
            gridcolor=COLORS["border_light"],
            zerolinecolor=COLORS["border"],
            tickfont=dict(size=11, color=COLORS["text_dim"]),
        ),
    )


def sparkline(values: list, color: str = None, height: int = 60) -> go.Figure:
    """Minimal sparkline chart — no axes, no labels."""
    if not values:
        values = [0]
    if color is None:
        color = COLORS["success"] if values[-1] >= values[0] else COLORS["danger"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=values,
        mode="lines",
        line=dict(color=color, width=2, shape="spline"),
        fill="tozeroy",
        fillcolor=color.replace(")", ",0.08)").replace("rgb", "rgba") if "rgb" in color
                  else f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
        hoverinfo="skip",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def score_gauge(score: float, label: str = "Score", height: int = 200) -> go.Figure:
    """Thin arc/ring gauge for 0-100 scores."""
    if score >= 70:
        color = COLORS["success"]
    elif score >= 50:
        color = COLORS["warning"]
    else:
        color = COLORS["danger"]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(font=dict(size=36, color=COLORS["text"], family="Inter"), suffix=""),
        title=dict(text=label, font=dict(size=13, color=COLORS["text_muted"])),
        gauge=dict(
            axis=dict(range=[0, 100], visible=False),
            bar=dict(color=color, thickness=0.3),
            bgcolor=COLORS["bg_elevated"],
            borderwidth=0,
            shape="angular",
            threshold=dict(line=dict(color=color, width=2), thickness=0.8, value=score),
        ),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=20, r=20, t=30, b=10),
        font=dict(family="Inter, -apple-system, sans-serif"),
    )
    return fig


def price_chart(dates, prices, title: str = "", height: int = 300) -> go.Figure:
    """Area chart with Apple-style gradient fill."""
    color = COLORS["accent"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor="rgba(0,113,227,0.08)",
        hovertemplate="%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(**apple_layout(title, height))
    return fig


def bar_chart(labels, values, title: str = "", height: int = 300,
              colors: list = None) -> go.Figure:
    """Bar chart with rounded appearance."""
    if colors is None:
        colors = [COLORS["accent"]] * len(labels)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        marker_line_width=0,
        hovertemplate="%{x}: %{y:.1f}<extra></extra>",
    ))
    fig.update_layout(**apple_layout(title, height))
    return fig


def donut_chart(labels, values, title: str = "", height: int = 250,
                colors: list = None) -> go.Figure:
    """Donut chart for distribution visualization."""
    if colors is None:
        colors = [COLORS["accent"], COLORS["success"], COLORS["warning"],
                  COLORS["danger"], COLORS["info"], COLORS["text_dim"]]

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels, values=values,
        hole=0.65,
        marker=dict(colors=colors[:len(labels)], line=dict(width=0)),
        textfont=dict(size=12, color=COLORS["text"]),
        hovertemplate="%{label}: %{value}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=True,
        legend=dict(font=dict(size=11, color=COLORS["text_muted"]), bgcolor="rgba(0,0,0,0)"),
        title=dict(text=title, font=dict(size=14, color=COLORS["text"])),
        font=dict(family="Inter, -apple-system, sans-serif"),
    )
    return fig

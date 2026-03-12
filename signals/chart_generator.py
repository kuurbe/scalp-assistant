"""
Chart generator for Telegram alerts — creates clean mini price charts
with entry/stop/target levels and energy overlay.
"""
import io
import logging
import numpy as np

logger = logging.getLogger(__name__)


def generate_alert_chart(
    ticker: str,
    prices: list,
    entry: float = None,
    stop: float = None,
    target: float = None,
    score: float = None,
    phase: str = None,
    energy_regime: str = None,
) -> bytes | None:
    """
    Generate a clean mini chart as PNG bytes for Telegram.
    Returns None if matplotlib unavailable or data insufficient.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        if not prices or len(prices) < 10:
            return None

        prices = [float(p) for p in prices if p is not None]
        n = len(prices)

        # ── Dark theme ──
        fig, ax = plt.subplots(1, 1, figsize=(8, 3.5), facecolor="#0E1117")
        ax.set_facecolor("#0E1117")

        x = np.arange(n)

        # Price line with gradient fill
        ax.plot(x, prices, color="#4C7BF4", linewidth=2, alpha=0.9)
        ax.fill_between(x, prices, min(prices) * 0.998, alpha=0.15, color="#4C7BF4")

        # Current price dot
        ax.scatter([n - 1], [prices[-1]], color="#4C7BF4", s=40, zorder=5)

        # ── Entry / Stop / Target lines ──
        if entry and entry > 0:
            ax.axhline(y=entry, color="#4C7BF4", linestyle="--", linewidth=1, alpha=0.7)
            ax.text(n + 0.5, entry, f"Entry ${entry:.2f}", fontsize=8, color="#4C7BF4",
                    va="center", fontfamily="monospace")
        if stop and stop > 0:
            ax.axhline(y=stop, color="#FF4757", linestyle="--", linewidth=1, alpha=0.7)
            ax.text(n + 0.5, stop, f"Stop ${stop:.2f}", fontsize=8, color="#FF4757",
                    va="center", fontfamily="monospace")
        if target and target > 0:
            ax.axhline(y=target, color="#2ED573", linestyle="--", linewidth=1, alpha=0.7)
            ax.text(n + 0.5, target, f"Target ${target:.2f}", fontsize=8, color="#2ED573",
                    va="center", fontfamily="monospace")

        # ── Title bar ──
        pct_change = ((prices[-1] - prices[0]) / prices[0]) * 100
        pct_color = "#2ED573" if pct_change >= 0 else "#FF4757"
        pct_str = f"+{pct_change:.1f}%" if pct_change >= 0 else f"{pct_change:.1f}%"

        title_parts = [f"{ticker}  ${prices[-1]:.2f}"]
        if score is not None:
            title_parts.append(f"Score: {score:.0f}")
        if phase:
            title_parts.append(phase)
        if energy_regime:
            title_parts.append(f"Energy: {energy_regime}")

        ax.set_title(
            "  |  ".join(title_parts),
            fontsize=11, color="#E1E1E1", fontweight="bold",
            fontfamily="monospace", loc="left", pad=10,
        )

        # Pct change badge
        ax.text(0.98, 0.95, pct_str, transform=ax.transAxes,
                fontsize=12, color=pct_color, fontweight="bold",
                ha="right", va="top", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=pct_color + "18", edgecolor="none"))

        # ── Styling ──
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#333")
        ax.spines["left"].set_color("#333")
        ax.tick_params(colors="#666", labelsize=8)
        ax.yaxis.set_major_formatter(plt.FormatStrFormatter("$%.2f"))
        ax.set_xlim(-1, n + 8)  # Room for level labels

        # Grid
        ax.grid(True, axis="y", alpha=0.1, color="#444")
        ax.set_xlabel("")
        ax.set_xticks([])

        # Watermark
        ax.text(0.02, 0.05, "Scalp Assistant v5", transform=ax.transAxes,
                fontsize=7, color="#444", fontfamily="monospace", alpha=0.5)

        plt.tight_layout(pad=0.5)

        # Export to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception:
        logger.debug("Chart generation failed", exc_info=True)
        return None


def generate_summary_chart(tickers_data: list) -> bytes | None:
    """
    Generate a summary bar chart showing top scored tickers.
    tickers_data: list of (ticker, score, pct_change) tuples.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not tickers_data or len(tickers_data) < 2:
            return None

        tickers_data = tickers_data[:10]  # Max 10
        tickers = [t[0] for t in tickers_data]
        scores = [t[1] for t in tickers_data]
        pcts = [t[2] for t in tickers_data]

        fig, ax = plt.subplots(1, 1, figsize=(8, 3), facecolor="#0E1117")
        ax.set_facecolor("#0E1117")

        # Color bars by score
        colors = []
        for s in scores:
            if s >= 70:
                colors.append("#2ED573")
            elif s >= 55:
                colors.append("#4C7BF4")
            elif s >= 45:
                colors.append("#FFA502")
            else:
                colors.append("#FF4757")

        bars = ax.barh(range(len(tickers)), scores, color=colors, alpha=0.85, height=0.6)

        # Labels
        for i, (bar, ticker, score, pct) in enumerate(zip(bars, tickers, scores, pcts)):
            pct_color = "#2ED573" if pct >= 0 else "#FF4757"
            pct_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
            ax.text(score + 1, i, f"{score:.0f}  {pct_str}", va="center",
                    fontsize=9, color="#E1E1E1", fontfamily="monospace")

        ax.set_yticks(range(len(tickers)))
        ax.set_yticklabels(tickers, fontsize=10, color="#E1E1E1",
                          fontweight="bold", fontfamily="monospace")
        ax.set_xlim(0, 110)
        ax.invert_yaxis()

        ax.set_title("Top Scored Setups", fontsize=12, color="#E1E1E1",
                     fontweight="bold", fontfamily="monospace", loc="left")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#333")
        ax.spines["left"].set_color("#333")
        ax.tick_params(colors="#666", labelsize=8)
        ax.grid(True, axis="x", alpha=0.1, color="#444")

        plt.tight_layout(pad=0.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception:
        logger.debug("Summary chart generation failed", exc_info=True)
        return None

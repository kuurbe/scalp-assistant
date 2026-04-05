"""
Six-Formula Quant Engine + Whale Detection.

Implements the six quantitative formulas that run on every scored ticker:
1. LMSR Pricing — detect mispricing vs historical base rate
2. Kelly Criterion — optimal position sizing (capped at quarter-Kelly)
3. EV Gap Detection — expected value vs implied market return
4. KL Divergence — distribution consistency check
5. Bayesian Updates — real-time posterior probability
6. Stoikov Execution — reservation price for optimal entry

Plus Unusual Whales-inspired detection:
- Unusual volume (std devs from mean)
- Sweep patterns (consecutive high-volume bars)
- Golden sweep equivalent (extreme volume + momentum)
- Block detection (large dollar-volume bars)

All formulas use existing ScoredTicker fields + ML predictions.
Zero new API calls. Pure math. Negligible compute.
"""

import math
import json
import os
from dataclasses import dataclass, field
from config import settings

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


@dataclass
class QuantSignal:
    # Six formulas
    lmsr_mispricing: float = 0.0       # Log-likelihood ratio vs base rate
    kelly_fraction: float = 0.0        # Optimal position size (0-0.25)
    ev_gap: float = 0.0                # Expected value gap (%)
    kl_divergence: float = 0.0         # Distribution divergence
    bayesian_posterior: float = 0.5    # Updated probability of profit
    stoikov_reservation: float = 0.0   # Optimal entry price
    # Formula agreement
    lmsr_agrees: bool = False
    kelly_agrees: bool = False
    ev_agrees: bool = False
    kl_agrees: bool = False
    bayes_agrees: bool = False
    stoikov_agrees: bool = False
    # Whale detection
    whale_volume_sigma: float = 0.0    # How many std devs above mean
    whale_sweep_detected: bool = False
    whale_golden_sweep: bool = False
    whale_block_detected: bool = False
    whale_score: float = 0.0           # 0-100 whale activity score
    # Composite
    quant_score: float = 0.0           # 0-100 average of normalized formulas
    quant_aligned: bool = False        # True if >= QUANT_ALIGNMENT_MIN agree
    n_agreeing: int = 0                # Number of formulas agreeing
    formula_details: dict = field(default_factory=dict)


def compute_quant_signals(
    scored_ticker,
    ml_pred: dict = None,
    daily_df=None,
    intraday_df=None,
) -> QuantSignal:
    """Compute all six quant formulas + whale detection for a scored ticker.

    Args:
        scored_ticker: ScoredTicker with composite_score, price, atr, direction, etc.
        ml_pred: Dict from predict_ticker() with predicted_return, bull_prob, pred_std, etc.
        daily_df: Daily OHLCV DataFrame (for whale volume analysis).
        intraday_df: Intraday OHLCV DataFrame (for sweep/block detection).

    Returns:
        QuantSignal with all computed values.
    """
    signal = QuantSignal()
    ml_pred = ml_pred or {}

    try:
        # Load model metadata for base rates
        meta = _load_model_meta()
        pred_history = _load_pred_history()

        bull_prob = ml_pred.get("bull_prob", 0.5)
        predicted_return = ml_pred.get("predicted_return", 0.0)
        pred_std = ml_pred.get("pred_std", 0.2)
        composite = scored_ticker.composite_score
        price = scored_ticker.price
        atr = scored_ticker.atr
        direction = scored_ticker.direction

        # ── 1. LMSR Pricing ──────────────────────────────────────
        signal.lmsr_mispricing = _compute_lmsr(bull_prob, meta)
        signal.lmsr_agrees = signal.lmsr_mispricing > 0.05

        # ── 2. Bayesian Update (compute before Kelly, which depends on it) ─
        signal.bayesian_posterior = _compute_bayesian(composite, meta)
        signal.bayes_agrees = signal.bayesian_posterior > 0.55

        # ── 3. Kelly Criterion ────────────────────────────────────
        signal.kelly_fraction = _compute_kelly(signal.bayesian_posterior, composite)
        signal.kelly_agrees = signal.kelly_fraction > 0.01

        # ── 4. EV Gap Detection ──────────────────────────────────
        signal.ev_gap = _compute_ev_gap(predicted_return, meta)
        signal.ev_agrees = signal.ev_gap > settings.QUANT_EV_GAP_THRESHOLD

        # ── 5. KL Divergence ─────────────────────────────────────
        signal.kl_divergence = _compute_kl_divergence(
            predicted_return, pred_std, meta, pred_history
        )
        signal.kl_agrees = signal.kl_divergence < settings.QUANT_KL_MAX_STABLE

        # ── 6. Stoikov Reservation Price ─────────────────────────
        signal.stoikov_reservation = _compute_stoikov(price, atr, direction)
        if direction == "LONG":
            signal.stoikov_agrees = price <= signal.stoikov_reservation * 1.005
        else:
            signal.stoikov_agrees = price >= signal.stoikov_reservation * 0.995

        # ── Whale Detection ──────────────────────────────────────
        whale = _detect_whale_activity(daily_df, intraday_df, price)
        signal.whale_volume_sigma = whale["volume_sigma"]
        signal.whale_sweep_detected = whale["sweep_detected"]
        signal.whale_golden_sweep = whale["golden_sweep"]
        signal.whale_block_detected = whale["block_detected"]
        signal.whale_score = whale["whale_score"]

        # ── Composite ────────────────────────────────────────────
        agreements = [
            signal.lmsr_agrees, signal.kelly_agrees, signal.ev_agrees,
            signal.kl_agrees, signal.bayes_agrees, signal.stoikov_agrees,
        ]
        signal.n_agreeing = sum(agreements)
        signal.quant_aligned = signal.n_agreeing >= settings.QUANT_ALIGNMENT_MIN

        # Normalize each to 0-100 and average
        scores = [
            _normalize_lmsr(signal.lmsr_mispricing),
            _normalize_kelly(signal.kelly_fraction),
            _normalize_ev(signal.ev_gap),
            _normalize_kl(signal.kl_divergence),
            _normalize_bayes(signal.bayesian_posterior),
            _normalize_stoikov(signal.stoikov_agrees, price, signal.stoikov_reservation),
        ]
        signal.quant_score = round(sum(scores) / len(scores), 1)

        # Detail dict for advanced view
        signal.formula_details = {
            "LMSR": {"value": round(signal.lmsr_mispricing, 4), "agrees": signal.lmsr_agrees,
                      "desc": f"Log-likelihood ratio: {signal.lmsr_mispricing:+.4f}"},
            "Kelly": {"value": round(signal.kelly_fraction, 4), "agrees": signal.kelly_agrees,
                       "desc": f"Position size: {signal.kelly_fraction*100:.1f}% of bankroll"},
            "EV Gap": {"value": round(signal.ev_gap, 4), "agrees": signal.ev_agrees,
                        "desc": f"Expected value: {signal.ev_gap:+.2f}%"},
            "KL Div": {"value": round(signal.kl_divergence, 4), "agrees": signal.kl_agrees,
                        "desc": f"Distribution divergence: {signal.kl_divergence:.4f}"},
            "Bayesian": {"value": round(signal.bayesian_posterior, 4), "agrees": signal.bayes_agrees,
                          "desc": f"Posterior probability: {signal.bayesian_posterior*100:.1f}%"},
            "Stoikov": {"value": round(signal.stoikov_reservation, 2), "agrees": signal.stoikov_agrees,
                         "desc": f"Reservation price: ${signal.stoikov_reservation:.2f}"},
        }

    except Exception:
        pass

    return signal


# ── Formula implementations ───────────────────────────────────────────────


def _compute_lmsr(bull_prob: float, meta: dict) -> float:
    """LMSR: Log-Market Scoring Rule mispricing detection.

    Compares ML classifier probability to historical base rate.
    Positive = ML sees higher probability than history suggests.
    """
    base_rate = meta.get("wf_hit_rate", 50) / 100
    base_rate = max(0.01, min(0.99, base_rate))
    bull_prob = max(0.01, min(0.99, bull_prob))
    return math.log(bull_prob) - math.log(base_rate)


def _compute_kelly(posterior: float, composite: float) -> float:
    """Kelly Criterion: Optimal position sizing.

    f* = (p - c) / (1 - c)
    p = Bayesian posterior probability
    c = cost proxy from composite score (higher score = lower cost/risk)
    """
    p = max(0.01, min(0.99, posterior))
    # Cost proxy: inverse of composite score strength
    # High composite = low cost (good setup), low composite = high cost
    c = max(0.01, min(0.99, 1.0 - (composite / 100)))
    kelly = (p - c) / (1 - c)
    # Cap at quarter-Kelly for safety
    return max(0.0, min(settings.KELLY_MAX_FRACTION, kelly))


def _compute_ev_gap(predicted_return: float, meta: dict) -> float:
    """EV Gap: Expected value vs implied market return.

    Implied market return derived from model's training distribution.
    Positive gap = ML model sees alpha above baseline.
    """
    # Use training mean as the baseline expected return
    implied_return = meta.get("pred_mean", 0.0)
    return predicted_return - implied_return


def _compute_kl_divergence(
    predicted_return: float, pred_std: float, meta: dict, pred_history: list
) -> float:
    """KL Divergence: Gaussian KL between current prediction and training distribution.

    KL(P || Q) for two Gaussians:
    ln(sigma_q/sigma_p) + (sigma_p^2 + (mu_p - mu_q)^2) / (2*sigma_q^2) - 0.5

    Low KL = consistent with training (stable signal).
    High KL = regime change (prediction is unusual).
    """
    mu_p = predicted_return
    sigma_p = max(pred_std, 0.001)

    # Training distribution from model metadata
    mu_q = meta.get("pred_mean", 0.0)
    sigma_q = meta.get("pred_std", 0.2)
    sigma_q = max(sigma_q, 0.001)

    kl = (math.log(sigma_q / sigma_p)
          + (sigma_p**2 + (mu_p - mu_q)**2) / (2 * sigma_q**2)
          - 0.5)
    return max(0.0, kl)


def _compute_bayesian(composite: float, meta: dict) -> float:
    """Bayesian Update: Prior from walk-forward hit rate, likelihood from signal strength.

    P(profit | signal) = P(signal | profit) * P(profit) / P(signal)
    Simplified: posterior = (L * prior) / (L * prior + (1-L) * (1-prior))
    """
    prior = meta.get("wf_hit_rate", 50) / 100
    prior = max(0.01, min(0.99, prior))

    # Likelihood = signal strength from composite score
    likelihood = max(0.01, min(0.99, composite / 100))

    numerator = likelihood * prior
    denominator = numerator + (1 - likelihood) * (1 - prior)
    if denominator <= 0:
        return 0.5

    return numerator / denominator


def _compute_stoikov(price: float, atr: float, direction: str) -> float:
    """Stoikov/Avellaneda-Stoikov reservation price for optimal entry.

    r = mid - q * gamma * sigma^2 * T - (1/gamma) * ln(1 + gamma/kappa)

    Simplified for directional trading:
    r = price - q * gamma * sigma^2 * T

    q = +1 for LONG (willing to pay slightly more), -1 for SHORT
    gamma = risk aversion
    sigma = volatility (ATR-based)
    T = 1/252 (one trading day)
    """
    if price <= 0:
        return 0.0

    gamma = settings.STOIKOV_RISK_AVERSION
    sigma = atr / price if price > 0 else 0.02  # Annualized vol proxy
    T = 1.0 / 252.0  # One trading day

    q = 1.0 if direction == "LONG" else -1.0

    # Reservation price: slight discount for longs, slight premium for shorts
    reservation = price - q * gamma * sigma**2 * T * price
    return reservation


# ── Whale Detection ───────────────────────────────────────────────────────


def _detect_whale_activity(daily_df, intraday_df, price: float) -> dict:
    """Detect unusual activity inspired by Unusual Whales methodology.

    Uses volume data to approximate:
    - Unusual volume (standard deviations from mean)
    - Sweep patterns (consecutive high-volume bars)
    - Golden sweep (extreme volume + strong momentum)
    - Block trades (large dollar-volume bars)
    """
    result = {
        "volume_sigma": 0.0,
        "sweep_detected": False,
        "golden_sweep": False,
        "block_detected": False,
        "whale_score": 0.0,
    }

    try:
        # ── Daily volume analysis ──
        if daily_df is not None and len(daily_df) > 20 and "Volume" in daily_df.columns:
            vol = daily_df["Volume"]
            recent_vol = vol.iloc[-21:-1]  # Last 20 days excluding today
            today_vol = float(vol.iloc[-1])
            mean_vol = float(recent_vol.mean())
            std_vol = float(recent_vol.std())

            if std_vol > 0 and mean_vol > 0:
                sigma = (today_vol - mean_vol) / std_vol
                result["volume_sigma"] = round(sigma, 2)

                # Block detection: dollar volume threshold
                dollar_vol = today_vol * price
                if dollar_vol >= settings.WHALE_BLOCK_MIN_DOLLAR:
                    result["block_detected"] = True

        # ── Intraday sweep/golden sweep detection ──
        if intraday_df is not None and len(intraday_df) > 10 and "Volume" in intraday_df.columns:
            intra_vol = intraday_df["Volume"]
            intra_close = intraday_df["Close"]
            mean_iv = float(intra_vol.mean())
            std_iv = float(intra_vol.std()) if len(intra_vol) > 1 else mean_iv * 0.5

            if mean_iv > 0 and std_iv > 0:
                # Sweep: consecutive bars with volume > 2 std devs above mean
                threshold = mean_iv + 2 * std_iv
                high_vol_bars = intra_vol > threshold
                consecutive = 0
                max_consecutive = 0
                for is_high in high_vol_bars:
                    if is_high:
                        consecutive += 1
                        max_consecutive = max(max_consecutive, consecutive)
                    else:
                        consecutive = 0

                if max_consecutive >= settings.WHALE_SWEEP_CONSECUTIVE:
                    result["sweep_detected"] = True

                # Golden sweep: extreme volume + strong directional momentum
                if len(intra_close) > 5:
                    last_5_return = (float(intra_close.iloc[-1]) - float(intra_close.iloc[-6])) / float(intra_close.iloc[-6]) * 100
                    last_5_vol_ratio = float(intra_vol.iloc[-5:].mean()) / mean_iv if mean_iv > 0 else 0

                    if (last_5_vol_ratio >= settings.WHALE_GOLDEN_VOLUME_MULT
                            and abs(last_5_return) > 1.0):
                        result["golden_sweep"] = True

        # ── Composite whale score ──
        score = 0
        sigma = result["volume_sigma"]
        if sigma >= settings.WHALE_VOLUME_SIGMA:
            score += 40  # Unusual volume
        elif sigma >= 1.5:
            score += 20
        elif sigma >= 1.0:
            score += 10

        if result["sweep_detected"]:
            score += 25
        if result["golden_sweep"]:
            score += 25  # On top of sweep
        if result["block_detected"]:
            score += 10

        result["whale_score"] = min(100, score)

    except Exception:
        pass

    return result


# ── Normalization helpers (each formula → 0-100) ─────────────────────────


def _normalize_lmsr(lmsr: float) -> float:
    """LMSR mispricing to 0-100. Higher positive = more mispriced in our favor."""
    return max(0, min(100, 50 + lmsr * 100))


def _normalize_kelly(kelly: float) -> float:
    """Kelly fraction to 0-100. 0.25 (max) = 100."""
    return min(100, kelly / settings.KELLY_MAX_FRACTION * 100) if settings.KELLY_MAX_FRACTION > 0 else 0


def _normalize_ev(ev: float) -> float:
    """EV gap to 0-100. +2% gap = 100, -2% = 0."""
    return max(0, min(100, 50 + ev * 25))


def _normalize_kl(kl: float) -> float:
    """KL divergence to 0-100. Low KL (stable) = high score."""
    # 0 KL = 100 (perfect consistency), 2+ KL = 0 (regime break)
    return max(0, min(100, 100 - kl * 50))


def _normalize_bayes(posterior: float) -> float:
    """Bayesian posterior to 0-100."""
    return max(0, min(100, posterior * 100))


def _normalize_stoikov(agrees: bool, price: float, reservation: float) -> float:
    """Stoikov agreement to 0-100. Favorable entry = high score."""
    if agrees:
        return 80
    # Partial credit: how close is current price to reservation?
    if price > 0 and reservation > 0:
        ratio = abs(price - reservation) / price
        return max(0, 80 - ratio * 500)
    return 30


# ── Data loaders (cached — read once per scan, not per ticker) ────────────

_cached_model_meta = None
_cached_pred_history = None


def _load_model_meta() -> dict:
    """Load model metadata (base rates, training distribution). Cached after first call."""
    global _cached_model_meta
    if _cached_model_meta is not None:
        return _cached_model_meta
    meta_file = os.path.join(MODEL_DIR, "meta_universal.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                _cached_model_meta = json.load(f)
                return _cached_model_meta
        except Exception:
            pass
    _cached_model_meta = {"wf_hit_rate": 50, "pred_mean": 0.0, "pred_std": 0.2}
    return _cached_model_meta


def _load_pred_history() -> list:
    """Load prediction history for KL divergence computation. Cached after first call."""
    global _cached_pred_history
    if _cached_pred_history is not None:
        return _cached_pred_history
    hist_file = os.path.join(MODEL_DIR, "pred_history.json")
    if os.path.exists(hist_file):
        try:
            with open(hist_file) as f:
                _cached_pred_history = json.load(f)
                return _cached_pred_history
        except Exception:
            pass
    _cached_pred_history = []
    return _cached_pred_history

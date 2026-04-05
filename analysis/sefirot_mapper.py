"""
Sefirot State Mapper — Maps scored ticker data to Tree of Life states.

The 10 Sefirot (divine emanations) map to trading behavioral functions:
  Keter    → Overall system confidence (crown)
  Chokhmah → Pattern recognition / intuitive signal (wisdom)
  Binah    → Analytical signal strength (understanding)
  Chesed   → Expansion / risk-on force (mercy)
  Gevurah  → Contraction / discipline force (severity)
  Tiferet  → Market emotional balance (beauty)
  Netzach  → Trend conviction / persistence (victory)
  Hod      → Technical signal clarity (splendor)
  Yesod    → Execution readiness / phase alignment (foundation)
  Malkuth  → Realized / predicted outcome (kingdom)

Three Pillars:
  Right (Mercy):  Chokhmah, Chesed, Netzach  — expansion, growth, persistence
  Left (Severity): Binah, Gevurah, Hod       — analysis, discipline, clarity
  Middle (Balance): Keter, Tiferet, Yesod, Malkuth — integration, balance
"""


def map_sefirot_state(scored_ticker) -> dict:
    """Map a ScoredTicker to a full Tree of Life state.

    Returns dict of 10 Sefirot, each with:
      - level: 0-100 intensity
      - label: current state description
      - state: 'active' / 'neutral' / 'dormant'
    """
    _g = lambda attr, default=0: getattr(scored_ticker, attr, default) or default

    composite = _g("composite_score")
    quality = _g("quality_factor", 1.0)
    phase = _g("kinematic_phase", "")
    ml_score = _g("ml_score")
    predicted_ret = _g("predicted_return")
    statistical = _g("statistical_score")
    cg_balance = _g("sefirot_balance")
    equilibrium = _g("sefirot_equilibrium")
    hod_clarity = _g("hod_technical_clarity", 0)
    phase_align = _g("sefirot_phase_alignment", 0)

    def _level_state(level):
        if level >= 65:
            return "active"
        elif level >= 35:
            return "neutral"
        return "dormant"

    def _label(name, level):
        labels = {
            "Keter": {True: "Strong Crown", False: "Dim Crown"},
            "Chokhmah": {True: "Pattern Firing", False: "Scanning"},
            "Binah": {True: "Clear Analysis", False: "Uncertain"},
            "Chesed": {True: "Expansion", False: "Reserved"},
            "Gevurah": {True: "Discipline Active", False: "Relaxed"},
            "Tiferet": {True: "Balanced", False: "Imbalanced"},
            "Netzach": {True: "Strong Conviction", False: "Weak Conviction"},
            "Hod": {True: "Signals Aligned", False: "Signals Mixed"},
            "Yesod": {True: "Ready to Execute", False: "Not Ready"},
            "Malkuth": {True: "Favorable Outcome", False: "Uncertain Outcome"},
        }
        return labels.get(name, {}).get(level >= 50, "—")

    # ── Compute each Sefirah ──

    # Keter: overall system confidence
    keter = min(max(composite * quality, 0), 100)

    # Chokhmah: active when ignition/strong trend phases detected
    ignition_phases = ("IGNITION", "STRONG_TREND", "BREAKOUT")
    chokhmah = 85 if any(p in phase.upper() for p in ignition_phases) else min(composite * 0.6, 60)

    # Binah: analytical signal = hod_clarity + statistical_score blend
    binah = min((hod_clarity * 50 + statistical * 0.5), 100)

    # Chesed: expansion force (positive side of balance)
    chesed = max(cg_balance * 100, 0)  # 0-100, only positive

    # Gevurah: contraction force (negative side of balance)
    gevurah = max(-cg_balance * 100, 0)  # 0-100, only when negative

    # Tiferet: equilibrium state
    tiferet = min(equilibrium * 100, 100)

    # Netzach: persistence (from scored ticker or approximate from composite)
    netzach_raw = _g("netzach_persistence", 0)
    netzach = min(netzach_raw * 100, 100) if netzach_raw else min(composite * 0.5, 50)

    # Hod: technical clarity
    hod = min(hod_clarity * 100, 100)

    # Yesod: phase alignment / execution readiness
    yesod = min(max(abs(phase_align) * 50, 0), 100)

    # Malkuth: realized outcome from ML
    if ml_score > 0 and predicted_ret > 0:
        malkuth = min(ml_score + predicted_ret * 10, 100)
    elif ml_score > 0:
        malkuth = ml_score * 0.8
    else:
        malkuth = 30  # baseline uncertainty

    sefirot = {}
    for name, level in [
        ("Keter", keter), ("Chokhmah", chokhmah), ("Binah", binah),
        ("Chesed", chesed), ("Gevurah", gevurah), ("Tiferet", tiferet),
        ("Netzach", netzach), ("Hod", hod), ("Yesod", yesod), ("Malkuth", malkuth),
    ]:
        lv = min(max(round(level), 0), 100)
        sefirot[name] = {
            "level": lv,
            "label": _label(name, lv),
            "state": _level_state(lv),
        }

    return sefirot


def get_dominant_pillar(state: dict) -> str:
    """Determine which pillar of the Tree is dominant.

    Right Pillar (Mercy):  Chokhmah + Chesed + Netzach
    Left Pillar (Severity): Binah + Gevurah + Hod
    Middle Pillar (Balance): Keter + Tiferet + Yesod + Malkuth
    """
    right = sum(state[s]["level"] for s in ("Chokhmah", "Chesed", "Netzach")) / 3
    left = sum(state[s]["level"] for s in ("Binah", "Gevurah", "Hod")) / 3
    middle = sum(state[s]["level"] for s in ("Keter", "Tiferet", "Yesod", "Malkuth")) / 4

    if right > left and right > middle:
        return "Right Pillar (Mercy)"
    elif left > right and left > middle:
        return "Left Pillar (Severity)"
    return "Middle Pillar (Balance)"


def get_sefirot_narrative(state: dict, ticker: str) -> str:
    """Generate a 1-2 sentence behavioral reading from the Tree state."""
    pillar = get_dominant_pillar(state)
    keter = state["Keter"]["level"]
    tiferet = state["Tiferet"]["level"]
    chesed = state["Chesed"]["level"]
    gevurah = state["Gevurah"]["level"]
    yesod = state["Yesod"]["level"]

    parts = []

    # Overall energy
    if keter >= 70:
        parts.append(f"{ticker} shows strong overall energy (Keter {keter})")
    elif keter <= 30:
        parts.append(f"{ticker} has low system confidence (Keter {keter})")
    else:
        parts.append(f"{ticker} at moderate energy (Keter {keter})")

    # Pillar dynamics
    if "Mercy" in pillar:
        parts.append("with expansion forces dominating — crowd psychology favors risk-on")
    elif "Severity" in pillar:
        parts.append("with analytical discipline prevailing — contraction pressure active")
    else:
        parts.append("in a balanced state between expansion and contraction")

    # Execution readiness
    if yesod >= 65:
        parts.append("Phase alignment supports execution.")
    elif yesod <= 30:
        parts.append("Phase alignment is weak — wait for better setup.")

    # Balance warning
    if tiferet >= 75:
        parts.append("Market is highly balanced — breakout direction unclear.")
    elif tiferet <= 25:
        parts.append("Strong imbalance detected — momentum move likely.")

    return " ".join(parts[:3])  # Keep it concise


def get_sefirot_score(state: dict) -> float:
    """Compute a 0-100 composite behavioral score from the Tree state.

    Weighted by relevance to trading decision-making:
    - Keter (confidence): 20%
    - Yesod (readiness): 20%
    - Netzach (conviction): 15%
    - Hod (clarity): 15%
    - Chesed-Gevurah spread: 15%
    - Malkuth (outcome): 15%
    """
    keter = state["Keter"]["level"]
    yesod = state["Yesod"]["level"]
    netzach = state["Netzach"]["level"]
    hod = state["Hod"]["level"]
    chesed = state["Chesed"]["level"]
    gevurah = state["Gevurah"]["level"]
    malkuth = state["Malkuth"]["level"]

    # Chesed-Gevurah: higher when there's clear directional bias
    cg_spread = abs(chesed - gevurah)

    score = (
        keter * 0.20
        + yesod * 0.20
        + netzach * 0.15
        + hod * 0.15
        + cg_spread * 0.15
        + malkuth * 0.15
    )
    return round(min(max(score, 0), 100), 1)

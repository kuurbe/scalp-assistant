"""
Multi-method level agreement scoring.
Determines how many independent methods agree on a given price level.
"""


def score_confluence(levels_data: dict) -> dict:
    """
    Score the quality of S/R levels based on confluence count.
    Returns: {strong_resistance: list, strong_support: list,
              confluence_quality: "HIGH"/"MEDIUM"/"LOW"}
    """
    resistance = levels_data.get("resistance", [])
    support = levels_data.get("support", [])

    strong_r = [r for r in resistance if r.get("confluence", 0) >= 2]
    strong_s = [s for s in support if s.get("confluence", 0) >= 2]

    max_confluence = max(
        [r.get("confluence", 0) for r in resistance] +
        [s.get("confluence", 0) for s in support] +
        [0]
    )

    if max_confluence >= 3:
        quality = "HIGH"
    elif max_confluence >= 2:
        quality = "MEDIUM"
    else:
        quality = "LOW"

    return {
        "strong_resistance": strong_r,
        "strong_support": strong_s,
        "confluence_quality": quality,
        "max_confluence": max_confluence,
    }

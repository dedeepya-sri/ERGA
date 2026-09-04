"""
Deterministic rubric scoring (Section 13):

    Criterion assessment -> Scoring rule -> Criterion marks -> Sum -> Final mark

NLI produces a status, not a mark (Section 12: "Don't let NLI directly
decide marks"). This module is the only place a status becomes a number,
and the mapping is entirely config-driven (Section 52 Rule 5: same input +
same rubric + same model/config must reproduce the same score).
"""
from __future__ import annotations

from config.settings import Config, ThresholdsConfig
from services.nli import STATUS_MISSING, STATUS_SUPPORTED


def compute_criterion_marks(
    status: str,
    composite_score: float,
    max_marks: float,
    config: Config,
) -> float:
    scoring = config.scoring
    if scoring.mode == "proportional":
        fraction = _proportional_fraction(status, composite_score, config.thresholds)
    else:
        fraction = scoring.fixed_fractions[status]
    return round(max_marks * fraction, scoring.round_ndigits)


def _proportional_fraction(status: str, composite_score: float, th: ThresholdsConfig) -> float:
    """
    Alternative to the flat 0.5-for-any-partial rule: interpolate within the
    partial-credit band so two PARTIALLY_SUPPORTED criteria with different
    composite scores don't necessarily receive identical credit. Still
    fully deterministic — the same composite score always yields the same
    fraction, and the interpolation floor/ceiling (0.15 / 0.85) keep a
    partial answer from ever being scored as either 0 or full marks.
    """
    if status == STATUS_SUPPORTED:
        return 1.0
    if status == STATUS_MISSING:
        return 0.0
    sup, part = th.nli_supported_min, th.nli_partial_min
    span = max(sup - part, 1e-6)
    position = min(max((composite_score - part) / span, 0.0), 1.0)
    return round(0.15 + 0.70 * position, 4)


def total_marks(criterion_marks: list[float], round_ndigits: int = 2) -> float:
    """The final score. Always a plain sum — no curve, no hidden adjustment (Section 13)."""
    return round(sum(criterion_marks), round_ndigits)

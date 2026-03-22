"""
Pure helpers for idle PWM samples vs calibration neutral.

- **Drift**: ``mean(samples) - cal_neutral`` — trim change or stale cal; re-run rc_calibrate if large.
- **Noise vs live mean**: fraction of samples with ``abs(v - mean) > band`` — idle wander around *today's* center.
"""
from __future__ import annotations

from statistics import mean, pstdev


def idle_mean_pstdev_span(
    vals: list[int],
) -> tuple[float, float, int, int, int] | None:
    """Return (mean, pstdev, min, max, span) or None if fewer than 2 samples."""
    n = len(vals)
    if n < 2:
        return None
    m = mean(vals)
    sd = pstdev(vals)
    lo, hi = min(vals), max(vals)
    return (m, sd, lo, hi, hi - lo)


def drift_us(sample_mean: float, cal_neutral: float) -> float:
    """Signed difference: measured mean minus stored calibration neutral (µs)."""
    return sample_mean - cal_neutral


def count_outside_band(vals: list[int], center: float, band: int) -> tuple[int, float]:
    """Count samples with abs(v - center) > band; return (count, percent)."""
    if not vals:
        return 0, 0.0
    outside = sum(1 for v in vals if abs(v - center) > band)
    return outside, 100.0 * outside / len(vals)


def drift_warning(abs_drift: float, band: int) -> str | None:
    """Return a short hint if drift is large relative to band, else None."""
    if abs_drift > float(2 * band):
        return "large drift vs cal — re-run rc_calibrate.py (idle, hands off)"
    if abs_drift > float(band):
        return "noticeable drift vs cal — consider re-running rc_calibrate.py"
    return None

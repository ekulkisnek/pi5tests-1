"""
Post-load checks for rc_pass_calibration.json (endpoints vs neutral).

Used by rc_walkthrough after suite cal and by pytest (no GPIO).
"""
from __future__ import annotations

from typing import Any


def validate_calibration_consistency(
    data: dict[str, Any],
    *,
    min_steer_span_us: float = 50.0,
    min_throttle_span_us: float = 50.0,
) -> list[str]:
    """
    Return a list of human-readable issues; empty list means OK for endpoint sanity.

    Does not replace validate_calibration_dict (required keys for pass_through).
    """
    errors: list[str] = []

    smin, smax = data.get("steer_min_us"), data.get("steer_max_us")
    if smin is not None and smax is not None:
        try:
            span = float(smax) - float(smin)
        except (TypeError, ValueError):
            errors.append("steer_min_us / steer_max_us are not numeric")
        else:
            if abs(span) < min_steer_span_us:
                errors.append(
                    "steering endpoint span %.1f µs < %.0f µs (re-run rc_calibrate.py --suite with full L/R throws)"
                    % (abs(span), min_steer_span_us)
                )

    tmin, tmax = data.get("throttle_min_us"), data.get("throttle_max_us")
    if tmin is not None and tmax is not None:
        try:
            tspan = float(tmax) - float(tmin)
        except (TypeError, ValueError):
            errors.append("throttle_min_us / throttle_max_us are not numeric")
        else:
            if abs(tspan) < min_throttle_span_us:
                errors.append(
                    "throttle endpoint span %.1f µs < %.0f µs (re-run rc_calibrate.py --suite with full rev/fwd)"
                    % (abs(tspan), min_throttle_span_us)
                )

    sn = data.get("steer_neutral_us")
    if smin is not None and smax is not None and sn is not None:
        try:
            lo, hi = float(smin), float(smax)
            if lo > hi:
                lo, hi = hi, lo
            sfloat = float(sn)
            slack = 100.0
            if not (lo - slack <= sfloat <= hi + slack):
                errors.append(
                    "steer_neutral_us (%.1f) is far outside steer_min/max range — check calibration"
                    % sfloat
                )
        except (TypeError, ValueError):
            pass

    return errors

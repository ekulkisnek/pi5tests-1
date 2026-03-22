"""Unit tests for rc_idle_metrics (no GPIO)."""
from __future__ import annotations

import pytest

from rc_idle_metrics import (
    count_outside_band,
    drift_us,
    drift_warning,
    idle_mean_pstdev_span,
)


def test_idle_mean_pstdev_span_constant() -> None:
    vals = [1540] * 20
    st = idle_mean_pstdev_span(vals)
    assert st is not None
    m, sd, lo, hi, span = st
    assert m == 1540.0
    assert sd == 0.0
    assert lo == hi == 1540
    assert span == 0


def test_idle_mean_pstdev_span_too_few() -> None:
    assert idle_mean_pstdev_span([]) is None
    assert idle_mean_pstdev_span([1500]) is None


def test_drift_trim_offset() -> None:
    """Stale cal: all samples ~1540, cal says 1561 — high drift, zero noise vs mean."""
    vals = [1540] * 100
    cal_neutral = 1561.0
    band = 6
    st = idle_mean_pstdev_span(vals)
    assert st is not None
    m = st[0]
    assert drift_us(m, cal_neutral) == pytest.approx(-21.0)
    oc, pct_c = count_outside_band(vals, cal_neutral, band)
    assert oc == 100
    assert pct_c == 100.0
    om, pct_m = count_outside_band(vals, m, band)
    assert om == 0
    assert pct_m == 0.0


def test_drift_small_noise_low() -> None:
    vals = [1560, 1562, 1561, 1561, 1560]
    cal_neutral = 1561.0
    band = 6
    st = idle_mean_pstdev_span(vals)
    assert st is not None
    m = st[0]
    assert abs(drift_us(m, cal_neutral)) < 1.0
    oc, _ = count_outside_band(vals, cal_neutral, band)
    om, _ = count_outside_band(vals, m, band)
    assert oc == 0
    assert om == 0


def test_count_outside_band_empty() -> None:
    assert count_outside_band([], 1500.0, 6) == (0, 0.0)


def test_drift_warning_thresholds() -> None:
    assert drift_warning(3.0, 6) is None
    assert drift_warning(7.0, 6) is not None  # > band
    assert "consider" in (drift_warning(7.0, 6) or "").lower()
    assert drift_warning(15.0, 6) is not None  # > 2*band
    assert "re-run" in (drift_warning(15.0, 6) or "").lower()

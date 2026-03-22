"""rc_calibration_validate.validate_calibration_consistency (pure dict checks)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rc_calibration_validate import validate_calibration_consistency

REPO = Path(__file__).resolve().parent.parent


def test_consistency_good_spans() -> None:
    d = {
        "steer_neutral_us": 1500.0,
        "steer_min_us": 1200.0,
        "steer_max_us": 1800.0,
        "throttle_min_us": 1300.0,
        "throttle_max_us": 1700.0,
    }
    assert validate_calibration_consistency(d) == []


def test_consistency_bad_steer_span() -> None:
    d = {
        "steer_neutral_us": 1500.0,
        "steer_min_us": 1494.0,
        "steer_max_us": 1500.0,
        "throttle_min_us": 1300.0,
        "throttle_max_us": 1700.0,
    }
    errs = validate_calibration_consistency(d, min_steer_span_us=50.0)
    assert len(errs) >= 1
    assert "steering endpoint span" in errs[0]


def test_consistency_fixture_valid_json() -> None:
    p = REPO / "tests" / "fixtures" / "calibration_valid_endpoints.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert validate_calibration_consistency(data) == []


def test_consistency_fixture_bad_steer_span() -> None:
    p = REPO / "tests" / "fixtures" / "calibration_bad_steer_span.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    errs = validate_calibration_consistency(data)
    assert len(errs) >= 1

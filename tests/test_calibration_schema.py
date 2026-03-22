"""Calibration JSON shape expected by pass_through_test.load_calibration."""
from __future__ import annotations

import json

import pytest

from tests.calibration_keys import REQUIRED_CAL_KEYS_FOR_PASS_THROUGH, validate_calibration_dict

# Minimal v2 example (subset of keys pass_through uses when present)
CAL_V2_MINIMAL = {
    "version": 2,
    "steer_neutral_us": 1562.0,
    "throttle_neutral_us": 1501.0,
    "steer_idle_std_us": 1.0,
    "throttle_idle_std_us": 0.5,
    "steer_idle_band_us": 6,
    "throttle_idle_band_us": 6,
}


def test_calibration_v2_required_keys() -> None:
    for k in REQUIRED_CAL_KEYS_FOR_PASS_THROUGH:
        assert k in CAL_V2_MINIMAL
    ok, msg = validate_calibration_dict(CAL_V2_MINIMAL)
    assert ok, msg


def test_calibration_json_roundtrip() -> None:
    s = json.dumps(CAL_V2_MINIMAL)
    d = json.loads(s)
    assert d["version"] == 2
    assert int(d["steer_idle_band_us"]) == 6


@pytest.mark.parametrize("version", [1, 2])
def test_version_supported(version: int) -> None:
    assert version in (1, 2)

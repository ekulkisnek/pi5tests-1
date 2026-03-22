"""Keys required in rc_pass_calibration.json when used by pass_through_test.load_calibration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# pass_through uses these when cal is present (see pass_through_test.py main).
REQUIRED_CAL_KEYS_FOR_PASS_THROUGH = (
    "steer_neutral_us",
    "throttle_neutral_us",
    "steer_idle_band_us",
    "throttle_idle_band_us",
)

SUPPORTED_VERSIONS = frozenset({1, 2})


def validate_calibration_dict(data: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, message)."""
    ver = data.get("version")
    if ver not in SUPPORTED_VERSIONS:
        return False, "unknown or missing version %r (expected %s)" % (ver, sorted(SUPPORTED_VERSIONS))
    for k in REQUIRED_CAL_KEYS_FOR_PASS_THROUGH:
        if k not in data:
            return False, "missing key: %s" % k
    return True, "ok"


def validate_calibration_file(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "file not found: %s" % path
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return False, str(e)
    if not isinstance(data, dict):
        return False, "root must be a JSON object"
    return validate_calibration_dict(data)

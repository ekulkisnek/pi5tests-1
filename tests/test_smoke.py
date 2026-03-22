"""Smoke tests: repo layout and optional Pi-only imports."""
from __future__ import annotations

import pathlib

import pytest

REQUIRED_FILES = (
    "pass_through_test.py",
    "rc_calibrate.py",
    "rc_idle_metrics.py",
    "rc_motion_windows.py",
    "rc_calibration_validate.py",
    "rc_jitter_test.py",
    "rc_interactive_suite.py",
    "rc_walkthrough.py",
    "gpio_diag_gpiod.py",
    "esc_output_test.py",
    "rc_signal_probe.py",
    "rc_pass_ab_test.sh",
    "rc_twitch_ab_test.sh",
    "run_all_rc_tests.sh",
    "requirements-dev.txt",
    "WALKTHROUGH.md",
    "TWITCH_REDUCTION.md",
)


def test_required_scripts_exist(repo_root: pathlib.Path) -> None:
    missing = [f for f in REQUIRED_FILES if not (repo_root / f).is_file()]
    assert not missing, f"Missing files: {missing}"


def test_gpiod_import() -> None:
    pytest.importorskip("gpiod")


def test_lgpio_import() -> None:
    pytest.importorskip("lgpio")

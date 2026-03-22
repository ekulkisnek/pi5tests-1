"""rc_walkthrough.py --dry-run exits 0 (no GPIO)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_walkthrough_dry_run_step1() -> None:
    r = subprocess.run(
        [sys.executable, "-u", str(REPO / "rc_walkthrough.py"), "--dry-run", "--to-step", "1"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "STEP 1 / 5" in r.stdout
    assert "pytest" in r.stdout


def test_walkthrough_help() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO / "rc_walkthrough.py"), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "--dry-run" in r.stdout
    assert "--skip-suite-cal" in r.stdout


def test_walkthrough_dry_run_step2_includes_suite_cal() -> None:
    r = subprocess.run(
        [sys.executable, "-u", str(REPO / "rc_walkthrough.py"), "--dry-run", "--from-step", "2", "--to-step", "2"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "STEP 2 / 5" in r.stdout
    assert "rc_calibrate.py" in r.stdout and "--suite" in r.stdout

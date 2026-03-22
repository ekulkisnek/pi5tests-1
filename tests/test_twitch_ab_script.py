"""rc_twitch_ab_test.sh dry-run exits 0 and lists segments."""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_twitch_ab_dry_run() -> None:
    r = subprocess.run(
        ["bash", str(REPO / "rc_twitch_ab_test.sh")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "RC_TWITCH_DRY_RUN": "1"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "h50_idle_hold" in r.stdout
    assert "RC_OUTPUT_HZ" in r.stdout
    assert "RC_EDGE_POLL_SLEEP" in r.stdout

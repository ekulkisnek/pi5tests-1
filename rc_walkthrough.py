#!/usr/bin/env python3
"""
Ordered walkthrough: pytest → **suite calibration** (``rc_calibrate.py --suite``) + validation →
rc_jitter_test → interactive suite (skips A/B/C motion if suite cal was used) → manual next steps
(including rc_twitch_ab_test.sh / TWITCH_REDUCTION.md for output twitch experiments).

Run on the Pi from repo root (TTY recommended for steps 3–4):

  ssh -t pi5-1@192.168.1.193 'cd ~/pi5tests-1 && python3 -u rc_walkthrough.py'

On the Pi directly (after: python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements-dev.txt):

  python3 -u rc_walkthrough.py
  # or: .venv/bin/python -u rc_walkthrough.py
  python3 -u rc_walkthrough.py --dry-run
  python3 -u rc_walkthrough.py --skip-suite-cal   # validate JSON only; full motion in step 4
  python3 -u rc_walkthrough.py --from-step 1 --to-step 2
  RC_WALKTHROUGH_PAUSE=0 python3 -u rc_walkthrough.py

See WALKTHROUGH.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from rc_calibration_validate import validate_calibration_consistency
from tests.calibration_keys import validate_calibration_file

TOTAL_STEPS = 5


def _banner(step: int, name: str) -> None:
    print("\n" + "═" * 72)
    print(" STEP %d / %d  %s" % (step, TOTAL_STEPS, name))
    print("═" * 72 + "\n")


def _pause() -> None:
    if os.environ.get("RC_WALKTHROUGH_PAUSE", "1").lower() in ("0", "false", "no"):
        return
    if sys.stdin.isatty():
        input("Press ENTER to continue to the next step… ")


def _cal_path() -> Path:
    return Path(
        os.path.expanduser(
            os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
        )
    )


def _python_having_pytest() -> str:
    """Use repo .venv if it has pytest; else current interpreter if pytest works."""
    venv_py = ROOT / ".venv" / "bin" / "python"
    for py in ([str(venv_py)] if venv_py.is_file() else []) + [sys.executable]:
        r = subprocess.run(
            [py, "-c", "import pytest"],
            cwd=str(ROOT),
            capture_output=True,
        )
        if r.returncode == 0:
            return py
    return sys.executable


def _pytest_install_hint() -> None:
    print(
        "pytest not found. On the Pi from ~/pi5tests-1 run:\n"
        "  python3 -m venv --system-site-packages .venv\n"
        "  .venv/bin/pip install -r requirements-dev.txt\n"
        "Then:  .venv/bin/python -u rc_walkthrough.py\n",
        file=sys.stderr,
    )


def run_pytest(dry_run: bool, py: str) -> bool:
    cmd = [py, "-m", "pytest", str(ROOT / "tests"), "-q"]
    if dry_run:
        print("Would run:", " ".join(cmd))
        return True
    chk = subprocess.run([py, "-c", "import pytest"], cwd=str(ROOT), capture_output=True)
    if chk.returncode != 0:
        _pytest_install_hint()
        return False
    r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode == 0


def run_calibration_check(dry_run: bool, require_cal: bool) -> bool:
    """Validate existing JSON only (required keys + endpoint consistency)."""
    path = _cal_path()
    if dry_run:
        print("Would validate calibration file:", path)
        return True
    ok, msg = validate_calibration_file(path)
    if not ok:
        print("Calibration:", msg, file=sys.stderr)
        if require_cal:
            return False
        print("  (Continuing — run rc_calibrate.py --suite when ready. Use --require-cal to fail here.)")
        return True
    print("Calibration OK:", path)
    print(" ", msg)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errs = validate_calibration_consistency(data)
    if errs:
        for line in errs:
            print("  Consistency:", line, file=sys.stderr)
        if require_cal:
            return False
        print("  (Continuing — re-run rc_calibrate.py --suite or fix JSON.)")
        return True
    print("  Consistency: endpoint spans OK")
    return True


def run_suite_calibration(dry_run: bool, py: str) -> bool:
    """Interactive ``rc_calibrate.py --suite`` (fails closed on bad motion)."""
    script = ROOT / "rc_calibrate.py"
    cmd = [py, "-u", str(script), "--suite"]
    if dry_run:
        print("Would run:", " ".join(cmd))
        return True
    if not sys.stdin.isatty():
        print("SKIP suite calibration: stdin is not a TTY (use ssh -t).", file=sys.stderr)
        return False
    r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode == 0


def run_jitter(dry_run: bool, py: str) -> bool:
    script = ROOT / "rc_jitter_test.py"
    cmd = [py, "-u", str(script)]
    if dry_run:
        print("Would run:", " ".join(cmd))
        return True
    if not sys.stdin.isatty():
        print("SKIP idle jitter: stdin is not a TTY (use ssh -t for interactive prompts).")
        return True
    r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode == 0


def run_interactive_suite(dry_run: bool, py: str, skip_input_motion: bool) -> bool:
    script = ROOT / "rc_interactive_suite.py"
    cmd = [py, "-u", str(script)]
    if dry_run:
        extra = " RC_SUITE_SKIP_INPUT_MOTION=1" if skip_input_motion else ""
        print("Would run:%s %s" % (extra, " ".join(cmd)))
        return True
    if not sys.stdin.isatty():
        print("SKIP interactive suite: stdin is not a TTY (use ssh -t).")
        return True
    env = os.environ.copy()
    if skip_input_motion:
        env["RC_SUITE_SKIP_INPUT_MOTION"] = "1"
    r = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return r.returncode == 0


def print_manual_tail() -> None:
    print("\n" + "═" * 72)
    print(" STEP 5 / %d  Manual next steps (not auto-started)" % TOTAL_STEPS)
    print("═" * 72)
    print(
        "  • Twitch reduction matrix (RC_OUTPUT_HZ, profiles, latch, edge poll):\n"
        "      ./rc_twitch_ab_test.sh\n"
        "    Dry-run plan:  RC_TWITCH_DRY_RUN=1 ./rc_twitch_ab_test.sh\n"
        "    Fast segments: RC_TWITCH_SECS=10 ./rc_twitch_ab_test.sh\n"
        "    See TWITCH_REDUCTION.md (pass_through uses lgpio + RC_OUTPUT_HZ, not pigpio).\n"
        "  • Hardware checklist (470µF 5V/GND, BEC vs Pi 5V, common ground): TWITCH_REDUCTION.md\n"
        "  • A/B/C pass-through profiles only (~90s):\n"
        "      ./rc_pass_ab_test.sh\n"
        "  • Pass-through until Ctrl+C:\n"
        "      python3 -u pass_through_test.py\n"
        "  • Re-calibrate (overwrites calibration JSON):\n"
        "      python3 -u rc_calibrate.py --suite\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="RC Pi verification walkthrough")
    ap.add_argument("--dry-run", action="store_true", help="Print commands only")
    ap.add_argument("--from-step", type=int, default=1, metavar="N", help="First step (1–5)")
    ap.add_argument("--to-step", type=int, default=5, metavar="N", help="Last step (1–5)")
    ap.add_argument("--require-cal", action="store_true", help="Fail if calibration JSON missing/invalid")
    ap.add_argument("--skip-jitter", action="store_true", help="Skip rc_jitter_test step")
    ap.add_argument("--skip-interactive", action="store_true", help="Skip rc_interactive_suite step")
    ap.add_argument(
        "--continue-on-fail",
        action="store_true",
        help="Continue after a failed step (default: stop on first failure)",
    )
    ap.add_argument(
        "--skip-suite-cal",
        action="store_true",
        help="Step 2: do not run rc_calibrate.py --suite; only validate existing JSON (+ consistency)",
    )
    args = ap.parse_args()

    py = _python_having_pytest()
    if subprocess.run([py, "-c", "import pytest"], cwd=str(ROOT), capture_output=True).returncode != 0:
        print("Using %s — pytest not installed (step 1 will fail until venv is set up; see WALKTHROUGH.md)" % py)
    else:
        print("Using Python for subprocesses: %s" % py)
    lo = max(1, min(TOTAL_STEPS, args.from_step))
    hi = max(1, min(TOTAL_STEPS, args.to_step))
    if lo > hi:
        lo, hi = hi, lo

    failed = False

    def should_run(step: int) -> bool:
        return lo <= step <= hi

    def maybe_pause_after(step: int) -> None:
        if args.dry_run:
            return
        if step < hi and step < TOTAL_STEPS:
            _pause()

    if should_run(1):
        _banner(1, "Automated pytest (repo + imports)")
        ok = run_pytest(args.dry_run, py)
        if not ok:
            failed = True
            if not args.continue_on_fail:
                return 1
        maybe_pause_after(1)

    if should_run(2) and not (failed and not args.continue_on_fail):
        _banner(
            2,
            "Calibration JSON validation only (--skip-suite-cal)"
            if args.skip_suite_cal
            else "Suite calibration + JSON validation",
        )
        if not args.skip_suite_cal:
            ok = run_suite_calibration(args.dry_run, py)
            if not ok:
                failed = True
                if not args.continue_on_fail:
                    return 1
        ok = run_calibration_check(args.dry_run, args.require_cal)
        if not ok:
            failed = True
            if not args.continue_on_fail:
                return 1
        maybe_pause_after(2)

    if should_run(3) and not (failed and not args.continue_on_fail):
        _banner(3, "Idle input jitter (hands off)")
        if args.skip_jitter:
            print("Skipped (--skip-jitter)")
        else:
            ok = run_jitter(args.dry_run, py)
            if not ok:
                failed = True
                if not args.continue_on_fail:
                    return 1
        maybe_pause_after(3)

    if should_run(4) and not (failed and not args.continue_on_fail):
        _banner(4, "Interactive hardware suite (motion + optional ESC + pass-through smoke)")
        if args.skip_interactive:
            print("Skipped (--skip-interactive)")
        else:
            ok = run_interactive_suite(args.dry_run, py, skip_input_motion=not args.skip_suite_cal)
            if not ok:
                failed = True
                if not args.continue_on_fail:
                    return 1
        maybe_pause_after(4)

    if should_run(5) and not (failed and not args.continue_on_fail):
        print_manual_tail()

    print("\nWalkthrough finished.", "FAIL" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

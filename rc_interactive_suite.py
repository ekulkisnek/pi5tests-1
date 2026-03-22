#!/usr/bin/env python3
"""
Interactive RC hardware suite for Pi 5 — run from repo root on the Pi.

Phases: triple-Enter safety ack, 10s steer-only / throttle-only / both motion windows
(with “at least 3 full cycles” instructions), optional hands-off idle snapshot vs cal,
optional esc_output_test, pass-through smoke with explicit RC_CALIB_PATH when cal exists.

Env:
  RC_SUITE_WINDOW_SEC=10       Sample window per motion phase
  RC_SUITE_MIN_SPAN_STEER=80    Min max-min on steering (µs) to PASS steer/both
  RC_SUITE_MIN_SPAN_THR=80      Min max-min on throttle (µs) to PASS thr/both
  RC_SUITE_MIN_SAMPLES=80       Min pulse samples per channel (enough data)
  RC_SUITE_STRICT_CENTER=0      If 1, steer-only fails if throttle span > 40 µs (etc.)
  RC_SUITE_SKIP_ESC=0           If 1, skip esc_output offer
  RC_SUITE_SKIP_PASS=0          If 1, skip pass-through smoke
  RC_SUITE_RUN_CALIB=0          If 1, print reminder only (does not auto-run calibrate)
  RC_SUITE_IDLE_CHECK_SEC=5     Hands-off idle sample after motion (0 = skip). Compares to cal bands.
  RC_SUITE_PASS_TIMEOUT=6       pass_through smoke timeout (seconds)
  RC_SUITE_SKIP_INPUT_MOTION=0  If 1, skip Phase A/B/C (use after rc_calibrate.py --suite)

Non-tty: exits with error (use SSH -t).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rc_calibrate import PIN_STEER, PIN_THROTTLE, collect_pulses
from rc_motion_windows import countdown, phase_motion, pulse_span, triple_enter_ack
from rc_idle_metrics import (
    count_outside_band,
    drift_us,
    drift_warning,
    idle_mean_pstdev_span,
)


def calibration_path() -> Path:
    return Path(
        os.path.expanduser(
            os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
        )
    )


def load_calibration_json() -> tuple[Path, dict | None]:
    path = calibration_path()
    if not path.is_file():
        return path, None
    try:
        with open(path, encoding="utf-8") as f:
            return path, json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("  WARNING: could not read calibration:", e, file=sys.stderr)
        return path, None


def print_calibration_banner(path: Path, data: dict | None, title: str = "[Calibration]") -> None:
    print("\n%s" % title)
    print("  RC_CALIB_PATH (effective): %s" % path)
    if os.environ.get("RC_CALIB", "").lower() in ("0", "false", "no"):
        print("  RC_CALIB=0 — pass-through will ignore calibration even if file exists.")
        return
    if data is None:
        print("  File: MISSING")
        print("  Effect: pass-through uses defaults 1500/1500 µs and env/default bands (see cal=none).")
        print("  Next:   python3 -u rc_calibrate.py")
        return
    ver = data.get("version", "?")
    print("  File: present  version=%s" % ver)
    sn = data.get("steer_neutral_us")
    tn = data.get("throttle_neutral_us")
    sb = data.get("steer_idle_band_us")
    tb = data.get("throttle_idle_band_us")
    print("  steer_neutral_us=%s  throttle_neutral_us=%s" % (sn, tn))
    print("  steer_idle_band_us=%s  throttle_idle_band_us=%s" % (sb, tb))
    smin, smax = data.get("steer_min_us"), data.get("steer_max_us")
    tmin, tmax = data.get("throttle_min_us"), data.get("throttle_max_us")
    if smin is not None and smax is not None:
        span = abs(float(smax) - float(smin))
        flag = " (check: full L/R throws?)" if span < 50 else ""
        print("  steer endpoints: min=%s max=%s  span≈%.0f µs%s" % (smin, smax, span, flag))
    if tmin is not None and tmax is not None:
        span = abs(float(tmax) - float(tmin))
        flag = " (check: full rev/fwd?)" if span < 50 else ""
        print("  throttle endpoints: min=%s max=%s  span≈%.0f µs%s" % (tmin, tmax, span, flag))


def _print_idle_channel_compare(name: str, vals: list[int], neutral: float, band: int) -> None:
    st = idle_mean_pstdev_span(vals)
    if st is None:
        print("  %s: too few samples for drift/noise lines" % name)
        return
    m, _sd, _lo, _hi, _sp = st
    d = drift_us(m, neutral)
    outside_cal, pct_cal = count_outside_band(vals, neutral, band)
    outside_mean, pct_mean = count_outside_band(vals, m, band)
    print("  %s: drift from cal %+.1f µs (stored neutral %.1f µs)" % (name, d, neutral))
    hint = drift_warning(abs(d), band)
    if hint:
        print("     → %s" % hint)
    print(
        "     vs cal ±%d µs: %d outside (%.1f%%); vs measured mean ±%d µs (noise): %d outside (%.1f%%)"
        % (band, outside_cal, pct_cal, band, outside_mean, pct_mean)
    )


def phase_idle_hands_off(seconds: float, _path: Path, data: dict | None) -> bool:
    print("\n" + "─" * 72)
    print("Phase — HANDS-OFF idle snapshot (RX noise check)")
    print("─" * 72)
    print(
        "For %.1f seconds: do **not** touch steering or throttle. Car + RX + TX stay on.\n"
        "This mimics rc_jitter_test.py in miniature." % seconds
    )
    input("Press ENTER when ready to start idle capture… ")
    print(">>> Hands off now…\n", flush=True)
    steer_vals, thr_vals = collect_pulses(seconds)
    ns, nt = len(steer_vals), len(thr_vals)
    ss = pulse_span(steer_vals)
    ts = pulse_span(thr_vals)
    print("  GPIO%d steer: n=%d  span=%d µs" % (PIN_STEER, ns, ss))
    print("  GPIO%d thr:  n=%d  span=%d µs" % (PIN_THROTTLE, nt, ts))
    if data and "steer_neutral_us" in data:
        sn = float(data["steer_neutral_us"])
        sb = int(data["steer_idle_band_us"])
        _print_idle_channel_compare("steer", steer_vals, sn, sb)
    if data and "throttle_neutral_us" in data:
        tn = float(data["throttle_neutral_us"])
        tb = int(data["throttle_idle_band_us"])
        _print_idle_channel_compare("throttle", thr_vals, tn, tb)
    print("  RESULT: PASS (informational)")
    print(
        "  Low noise % (vs measured mean) + small span/pstdev = clean RX; large drift vs cal = re-run rc_calibrate. "
        "Twitch with clean input is often **output** PWM."
    )
    return True


def phase0_smoke() -> bool:
    print("\n[Phase 0] Imports and /dev/gpiochip0")
    ok = True
    try:
        import gpiod  # noqa: F401

        import lgpio  # noqa: F401
    except ImportError as e:
        print("  FAIL: missing module:", e)
        return False
    chip = Path("/dev/gpiochip0")
    if not chip.exists():
        print("  FAIL: %s not found (not a Pi / no gpiochip?)" % chip)
        ok = False
    else:
        print("  OK  %s present" % chip)
    print("  OK  gpiod + lgpio import")
    return ok


def run_esc_output() -> bool:
    script = ROOT / "esc_output_test.py"
    if not script.is_file():
        print("  SKIP: %s missing" % script)
        return True
    print("Running esc_output_test.py …")
    r = subprocess.run(
        [sys.executable, "-u", str(script)],
        cwd=str(ROOT),
    )
    return r.returncode == 0


def run_pass_through_smoke(timeout_sec: float, cal_path: Path) -> bool:
    script = ROOT / "pass_through_test.py"
    if not script.is_file():
        print("  SKIP: %s missing" % script)
        return True
    env = os.environ.copy()
    if cal_path.is_file() and env.get("RC_CALIB", "").lower() not in ("0", "false", "no"):
        env["RC_CALIB_PATH"] = str(cal_path.resolve())
    print(
        "Pass-through smoke (%.0fs timeout, expect TimeoutExpired) — child inherits RC_CALIB_PATH if cal exists…"
        % timeout_sec
    )
    try:
        subprocess.run(
            [sys.executable, "-u", str(script)],
            cwd=str(ROOT),
            env=env,
            timeout=timeout_sec,
        )
        print("  FAIL: pass_through exited normally (expected timeout)")
        return False
    except subprocess.TimeoutExpired:
        print("  OK  stopped by timeout (pass_through running)")
        print("  Check banner above for: neutral µs from cal, Profile=idle_hold when cal loaded, cal= path")
        return True
    except OSError as e:
        print("  FAIL:", e)
        return False


def print_final_diagnostics(path: Path, data: dict | None, results: list[tuple[str, bool]]) -> None:
    print("\n" + "=" * 72)
    print("DIAGNOSTICS (for tuning)")
    print("=" * 72)
    print_calibration_banner(path, data, title="[Calibration file]")
    ok = all(r[1] for r in results)
    print("\n  Suite motion tests:", "all PASS" if ok else "some FAIL — fix wiring/motion first")
    if data is None:
        print("  Twitch tuning: run `python3 -u rc_calibrate.py` then compare pass-through with cal loaded.")
    else:
        print("  Twitch still bad with cal + idle_hold? Likely software PWM on GPIO out — try hardware PWM / PCA9685.")
    print("  Deep input noise: `python3 -u rc_jitter_test.py`")
    print("  Profile compare:   `./rc_pass_ab_test.sh`")
    print("=" * 72)


def main() -> int:
    if not sys.stdin.isatty():
        print("This suite must be run in an interactive terminal (use: ssh -t pi5-1@192.168.1.193 'cd ~/pi5tests-1 && python3 -u rc_interactive_suite.py')", file=sys.stderr)
        return 1

    window = float(os.environ.get("RC_SUITE_WINDOW_SEC", "10"))
    min_span_s = int(os.environ.get("RC_SUITE_MIN_SPAN_STEER", "80"))
    min_span_t = int(os.environ.get("RC_SUITE_MIN_SPAN_THR", "80"))
    min_samples = int(os.environ.get("RC_SUITE_MIN_SAMPLES", "80"))
    strict = os.environ.get("RC_SUITE_STRICT_CENTER", "0").lower() in ("1", "true", "yes")
    skip_esc = os.environ.get("RC_SUITE_SKIP_ESC", "0").lower() in ("1", "true", "yes")
    skip_pass = os.environ.get("RC_SUITE_SKIP_PASS", "0").lower() in ("1", "true", "yes")
    skip_input_motion = os.environ.get("RC_SUITE_SKIP_INPUT_MOTION", "0").lower() in ("1", "true", "yes")
    idle_check_sec = float(os.environ.get("RC_SUITE_IDLE_CHECK_SEC", "5"))
    pass_timeout = float(os.environ.get("RC_SUITE_PASS_TIMEOUT", "6"))

    print(
        "╔══════════════════════════════════════════════════════════════════════╗\n"
        "║  RC interactive suite — Pi 5, GPIO 17/27 in, 18/13 out                 ║\n"
        "║  Car + RX + TX on; common GND; wheels safe; prop clear.                ║\n"
        "╚══════════════════════════════════════════════════════════════════════╝"
    )
    print(
        "Window=%.1fs  min_span_steer=%d  min_span_thr=%d  min_samples=%d  strict_center=%s  skip_input_motion=%s\n"
        % (window, min_span_s, min_span_t, min_samples, strict, skip_input_motion)
    )

    if not phase0_smoke():
        return 1

    cal_path, cal_data = load_calibration_json()
    print_calibration_banner(cal_path, cal_data)

    results: list[tuple[str, bool]] = []

    if not skip_input_motion:
        triple_enter_ack(
            "Safety — INPUT phases",
            "You will move the transmitter sticks during timed windows.\n"
            "Keep wheels off the ground or vehicle safe. RX powered from car; Pi GND tied to RX/car.\n"
            "Each motion window is ~%.0f seconds — perform at least THREE full back-and-forth cycles\n"
            "for the channel(s) asked (slow is fine)." % window,
        )

        ok_s, _, _ = phase_motion(
            "Phase A — STEERING only",
            "For the next window: move STEERING full left ↔ full right at least 3 complete cycles.\n"
            "Keep THROTTLE centered / hands off throttle.",
            window,
            "steer",
            min_samples,
            min_span_s,
            min_span_t,
            strict,
        )
        results.append(("steer_only", ok_s))

        ok_t, _, _ = phase_motion(
            "Phase B — THROTTLE only",
            "For the next window: move THROTTLE full reverse ↔ full forward at least 3 complete cycles.\n"
            "Keep STEERING centered / hands off steering.",
            window,
            "thr",
            min_samples,
            min_span_s,
            min_span_t,
            strict,
        )
        results.append(("thr_only", ok_t))

        ok_b, _, _ = phase_motion(
            "Phase C — BOTH channels",
            "For the next window: move BOTH steering and throttle together (any pattern), at least 3 cycles each.",
            window,
            "both",
            min_samples,
            min_span_s,
            min_span_t,
            False,
        )
        results.append(("both", ok_b))
    else:
        print("\n[Phase A/B/C] SKIPPED (RC_SUITE_SKIP_INPUT_MOTION=1 — motion already done in suite calibration)")

    if idle_check_sec > 0:
        results.append(
            (
                "idle_hands_off",
                phase_idle_hands_off(idle_check_sec, cal_path, cal_data),
            )
        )
    else:
        print("\n[Idle snapshot] SKIPPED (RC_SUITE_IDLE_CHECK_SEC=0)")

    if not skip_esc:
        triple_enter_ack(
            "Safety — OUTPUT test (optional)",
            "Next step can RUN esc_output_test.py — it drives GPIO 13 (ESC) and 18 (steer).\n"
            "Wheels OFF ground; clear prop; ESC/servo powered. You may skip.",
        )
        ans = input("Type YES in capitals to run esc_output_test, or press Enter to skip: ").strip()
        if ans == "YES":
            results.append(("esc_output", run_esc_output()))
        else:
            print("  SKIPPED esc_output_test")
    else:
        print("\n[Phase D] SKIPPED esc (RC_SUITE_SKIP_ESC=1)")

    cal_path, cal_data = load_calibration_json()
    print_calibration_banner(cal_path, cal_data, title="[Calibration — before pass-through smoke]")

    if not skip_pass:
        results.append(("pass_through_smoke", run_pass_through_smoke(pass_timeout, cal_path)))
    else:
        print("\n[Phase E] SKIPPED pass_through (RC_SUITE_SKIP_PASS=1)")

    print("\n" + "=" * 72)
    print("SUMMARY")
    for name, ok in results:
        print("  %-20s %s" % (name, "PASS" if ok else "FAIL"))
    print("=" * 72)

    print_final_diagnostics(cal_path, cal_data, results)

    if os.environ.get("RC_SUITE_RUN_CALIB", "0").lower() in ("1", "true", "yes"):
        print(
            "\nRC_SUITE_RUN_CALIB=1 set — run calibration manually (overwrites ~/.config/rc_pass_calibration.json):\n"
            "  python3 -u rc_calibrate.py\n"
        )
    print(
        "\nManual follow-ups (not auto-run):\n"
        "  python3 -u rc_jitter_test.py          # hands off both sticks\n"
        "  python3 -u rc_calibrate.py --suite    # recommended: idle + motion endpoint capture\n"
        "  ./rc_pass_ab_test.sh                  # A/B/C pass-through modes\n"
    )

    if all(ok for _, ok in results):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Measure idle PWM on GPIO 17 & 27 (hands off sticks) and optional steering/throttle endpoints.

Writes JSON for pass_through_test.py (default: ~/.config/rc_pass_calibration.json).

**Suite mode (recommended):** ``python3 rc_calibrate.py --suite`` uses the same long
motion windows as ``rc_interactive_suite`` (min/max over full window) and **refuses
to write** if steering or throttle span is below RC_CALIB_MIN_SPAN_* (default 80 µs).

Legacy mode (default): short per-position samples (RC_ENDPOINT_SECS, default 2 s).

Usage:
  python3 rc_calibrate.py --suite
  python3 rc_calibrate.py
  RC_IDLE_SECS=5 python3 rc_calibrate.py
  RC_CALIB_ENDPOINTS=0 python3 rc_calibrate.py          # idle only
  RC_CALIB_THROTTLE_ENDPOINTS=0 python3 rc_calibrate.py   # idle + steer endpoints only
  RC_CALIB_PATH=/tmp/cal.json python3 rc_calibrate.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import timedelta
from statistics import mean, pstdev

import gpiod
from gpiod import LineSettings
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge

CHIP_PATH = "/dev/gpiochip0"
PIN_STEER = 17
PIN_THROTTLE = 27

CLAMP_LO = 800
CLAMP_HI = 2200


def collect_pulses(seconds: float) -> tuple[list[int], list[int]]:
    """Return lists of pulse widths (µs) per channel over ``seconds`` wall time."""
    in_cfg = LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
    )
    req = gpiod.request_lines(
        CHIP_PATH,
        consumer="rc_calibrate",
        config={PIN_STEER: in_cfg, PIN_THROTTLE: in_cfg},
        event_buffer_size=2048,
    )

    pulse_us = {PIN_STEER: 1500, PIN_THROTTLE: 1500}
    last_rise_ns: dict[int, int | None] = {PIN_STEER: None, PIN_THROTTLE: None}
    steer_vals: list[int] = []
    thr_vals: list[int] = []

    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        if req.wait_edge_events(timedelta(seconds=0.05)):
            for ev in req.read_edge_events():
                off = ev.line_offset
                if off not in last_rise_ns:
                    continue
                if ev.event_type == EdgeEvent.Type.RISING_EDGE:
                    last_rise_ns[off] = ev.timestamp_ns
                elif ev.event_type == EdgeEvent.Type.FALLING_EDGE:
                    t0 = last_rise_ns[off]
                    if t0 is None:
                        continue
                    span_us = (ev.timestamp_ns - t0) / 1000.0
                    last_rise_ns[off] = None
                    if 500 <= span_us <= 2500:
                        v = int(round(span_us))
                        pulse_us[off] = v
                        if off == PIN_STEER:
                            steer_vals.append(v)
                        else:
                            thr_vals.append(v)
        else:
            time.sleep(0.0005)

    req.release()
    return steer_vals, thr_vals


def stats(vals: list[int]) -> tuple[float, float]:
    if not vals:
        return (1500.0, 0.0)
    if len(vals) < 2:
        return (float(vals[0]), 0.0)
    return (mean(vals), pstdev(vals))


def suite_main() -> int:
    """Interactive suite-style calibration: idle + steer window + throttle window; gates on span."""
    if not sys.stdin.isatty():
        print("rc_calibrate.py --suite requires an interactive TTY (e.g. ssh -t).", file=sys.stderr)
        return 1

    from rc_calibration_validate import validate_calibration_consistency
    from rc_motion_windows import motion_window_collect, triple_enter_ack

    idle_secs = float(os.environ.get("RC_IDLE_SECS", "5"))
    window = float(os.environ.get("RC_SUITE_WINDOW_SEC", "10"))
    min_span_s = int(
        os.environ.get(
            "RC_CALIB_MIN_SPAN_STEER",
            os.environ.get("RC_SUITE_MIN_SPAN_STEER", "80"),
        )
    )
    min_span_t = int(
        os.environ.get(
            "RC_CALIB_MIN_SPAN_THR",
            os.environ.get("RC_SUITE_MIN_SPAN_THR", "80"),
        )
    )
    min_samples = int(os.environ.get("RC_SUITE_MIN_SAMPLES", "80"))
    strict = os.environ.get("RC_SUITE_STRICT_CENTER", "0").lower() in ("1", "true", "yes")
    out_path = os.path.expanduser(
        os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
    )

    print(
        "RC calibration **suite mode** — car + RX + TX on, wheels safe.\n"
        "Idle sample, then STEERING-only and THROTTLE-only motion windows (same as interactive suite).\n"
        "File is written only if motion passes and endpoint spans ≥ %d / %d µs.\n"
        % (min_span_s, min_span_t)
    )

    input("Press ENTER when ready for IDLE (hands off both sticks)... ")
    print("IDLE: do not touch steering or throttle for %.1f seconds..." % idle_secs)
    time.sleep(0.5)
    s_idle, t_idle = collect_pulses(idle_secs)
    if len(s_idle) < 10 or len(t_idle) < 10:
        print(
            "ERROR: too few idle samples (steer=%d, thr=%d). Check wiring."
            % (len(s_idle), len(t_idle)),
            file=sys.stderr,
        )
        return 1

    sn, ss = stats(s_idle)
    tn, ts = stats(t_idle)
    steer_band = max(6, int(3 * ss + 0.999))
    thr_band = max(6, int(3 * ts + 0.999))

    triple_enter_ack(
        "Safety — motion windows",
        "You will move sticks during timed windows (~%.0f s each).\n"
        "Keep wheels off the ground; Pi GND tied to RX/car.\n"
        "Perform at least THREE full back-and-forth cycles per phase (slow is fine)." % window,
    )

    ok_s, steer_vals_s, _thr_s = motion_window_collect(
        "STEERING only (endpoint capture)",
        "Move STEERING full left ↔ full right at least 3 complete cycles.\n"
        "Keep THROTTLE centered / hands off throttle.",
        window,
        "steer",
        min_samples,
        min_span_s,
        min_span_t,
        strict,
    )
    if not ok_s:
        print("ERROR: steering motion window failed. Calibration file NOT written.", file=sys.stderr)
        return 1

    steer_min = float(min(steer_vals_s))
    steer_max = float(max(steer_vals_s))
    s_span = steer_max - steer_min
    if s_span < float(min_span_s):
        print(
            "ERROR: steering endpoint span %.1f µs < %d µs. Calibration file NOT written."
            % (s_span, min_span_s),
            file=sys.stderr,
        )
        return 1

    ok_t, _steer_t, thr_vals_t = motion_window_collect(
        "THROTTLE only (endpoint capture)",
        "Move THROTTLE full reverse ↔ full forward at least 3 complete cycles.\n"
        "Keep STEERING centered / hands off steering.",
        window,
        "thr",
        min_samples,
        min_span_s,
        min_span_t,
        strict,
    )
    if not ok_t:
        print("ERROR: throttle motion window failed. Calibration file NOT written.", file=sys.stderr)
        return 1

    throttle_min = float(min(thr_vals_t))
    throttle_max = float(max(thr_vals_t))
    t_span = throttle_max - throttle_min
    if t_span < float(min_span_t):
        print(
            "ERROR: throttle endpoint span %.1f µs < %d µs. Calibration file NOT written."
            % (t_span, min_span_t),
            file=sys.stderr,
        )
        return 1

    data = {
        "version": 2,
        "steer_neutral_us": round(sn, 1),
        "throttle_neutral_us": round(tn, 1),
        "steer_idle_std_us": round(ss, 3),
        "throttle_idle_std_us": round(ts, 3),
        "steer_idle_band_us": steer_band,
        "throttle_idle_band_us": thr_band,
        "steer_min_us": steer_min,
        "steer_max_us": steer_max,
        "throttle_min_us": throttle_min,
        "throttle_max_us": throttle_max,
        "samples_idle_steer": len(s_idle),
        "samples_idle_throttle": len(t_idle),
    }

    consistency = validate_calibration_consistency(
        data,
        min_steer_span_us=float(min_span_s),
        min_throttle_span_us=float(min_span_t),
    )
    if consistency:
        for line in consistency:
            print("ERROR:", line, file=sys.stderr)
        print("Calibration file NOT written.", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(out_path) or ".", mode=0o755, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("\nWrote %s (suite mode)" % out_path)
    print(json.dumps(data, indent=2))
    print("\nUse: python3 -u pass_through_test.py")
    print("Next: rc_walkthrough.py step 4 can use RC_SUITE_SKIP_INPUT_MOTION=1")
    return 0


def legacy_main() -> int:
    idle_secs = float(os.environ.get("RC_IDLE_SECS", "5"))
    endpoint_secs = float(os.environ.get("RC_ENDPOINT_SECS", "2"))
    out_path = os.path.expanduser(
        os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
    )
    do_endpoints = os.environ.get("RC_CALIB_ENDPOINTS", "1") not in ("0", "false", "no")
    do_thr_endpoints = do_endpoints and (
        os.environ.get("RC_CALIB_THROTTLE_ENDPOINTS", "1") not in ("0", "false", "no")
    )

    print(
        "RC calibration — car + RX + TX on, wheels safe.\n"
        "You will be asked to keep hands OFF sticks, then optional full steering"
        + (" + throttle" if do_thr_endpoints else "")
        + " throws.\n"
    )

    input("Press ENTER when ready for IDLE (hands off both sticks)... ")
    print("IDLE: do not touch steering or throttle for %.1f seconds..." % idle_secs)
    time.sleep(0.5)
    s_idle, t_idle = collect_pulses(idle_secs)
    if len(s_idle) < 10 or len(t_idle) < 10:
        print(
            "Warning: few samples (steer=%d, thr=%d). Check wiring / RX power."
            % (len(s_idle), len(t_idle)),
            file=sys.stderr,
        )

    sn, ss = stats(s_idle)
    tn, ts = stats(t_idle)
    steer_band = max(6, int(3 * ss + 0.999))
    thr_band = max(6, int(3 * ts + 0.999))

    steer_min: float | None = None
    steer_max: float | None = None
    throttle_min: float | None = None
    throttle_max: float | None = None

    if do_endpoints:
        input("Press ENTER, then move STEERING full LEFT and hold (~%.1fs)..." % endpoint_secs)
        print("Sampling STEER LEFT...")
        s_left, _ = collect_pulses(endpoint_secs)
        input("Press ENTER, then move STEERING full RIGHT and hold...")
        print("Sampling STEER RIGHT...")
        s_right, _ = collect_pulses(endpoint_secs)
        input("Press ENTER, then center steering (hands off or neutral)...")
        print("Sampling STEER center snapshot...")
        _, _ = collect_pulses(1.5)
        if s_left:
            steer_min = float(min(s_left))
        if s_right:
            steer_max = float(max(s_right))
        print(
            "Endpoints: steer_min≈%s steer_max≈%s (informational)"
            % (steer_min, steer_max)
        )
        if steer_min is not None and steer_max is not None:
            span = steer_max - steer_min
            if span < 50:
                print(
                    "WARNING: steering endpoint span is only %.0f µs — full left/right were probably not held "
                    "during sampling (expect hundreds of µs). Re-run and hold full throw until each sample finishes."
                    % span,
                    file=sys.stderr,
                )

    if do_thr_endpoints:
        input(
            "Press ENTER, then move THROTTLE full REVERSE (brake/rev) and hold (~%.1fs)..."
            % endpoint_secs
        )
        print("Sampling THROTTLE reverse...")
        _, t_rev = collect_pulses(endpoint_secs)
        input("Press ENTER, then move THROTTLE full FORWARD and hold...")
        print("Sampling THROTTLE forward...")
        _, t_fwd = collect_pulses(endpoint_secs)
        input("Press ENTER, then return throttle to neutral (hands off)...")
        print("Sampling THROTTLE neutral snapshot...")
        _, _ = collect_pulses(1.5)
        if t_rev:
            throttle_min = float(min(t_rev))
        if t_fwd:
            throttle_max = float(max(t_fwd))
        print(
            "Endpoints: throttle_min≈%s throttle_max≈%s (informational)"
            % (throttle_min, throttle_max)
        )
        if throttle_min is not None and throttle_max is not None:
            tspan = throttle_max - throttle_min
            if tspan < 50:
                print(
                    "WARNING: throttle endpoint span is only %.0f µs — full reverse/forward were probably not held."
                    % tspan,
                    file=sys.stderr,
                )

    os.makedirs(os.path.dirname(out_path) or ".", mode=0o755, exist_ok=True)
    data = {
        "version": 2,
        "steer_neutral_us": round(sn, 1),
        "throttle_neutral_us": round(tn, 1),
        "steer_idle_std_us": round(ss, 3),
        "throttle_idle_std_us": round(ts, 3),
        "steer_idle_band_us": steer_band,
        "throttle_idle_band_us": thr_band,
        "steer_min_us": steer_min,
        "steer_max_us": steer_max,
        "throttle_min_us": throttle_min,
        "throttle_max_us": throttle_max,
        "samples_idle_steer": len(s_idle),
        "samples_idle_throttle": len(t_idle),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("\nWrote %s" % out_path)
    print(json.dumps(data, indent=2))
    print("\nUse: python3 -u pass_through_test.py  (loads this file by default if present)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="RC PWM calibration for pass_through_test.py")
    ap.add_argument(
        "--suite",
        action="store_true",
        help="Use interactive-suite motion windows for endpoints (recommended; fails closed on bad span)",
    )
    args = ap.parse_args()
    if args.suite:
        return suite_main()
    return legacy_main()


if __name__ == "__main__":
    raise SystemExit(main())

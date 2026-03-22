"""
Shared motion-window helpers for rc_calibrate (suite mode) and rc_interactive_suite.

Uses collect_pulses() from rc_calibrate (gpiod edge sampling).
"""
from __future__ import annotations

import sys
import time

from rc_calibrate import PIN_STEER, PIN_THROTTLE, collect_pulses


def pulse_span(vals: list[int]) -> int:
    if len(vals) < 2:
        return 0
    return max(vals) - min(vals)


def countdown(seconds: int = 3) -> None:
    for t in range(seconds, 0, -1):
        print("  %d…" % t, flush=True)
        time.sleep(1.0)


def triple_enter_ack(title: str, body: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(body)
    print()
    for i in range(1, 4):
        input("Press ENTER (%d/3) to confirm you read the above… " % i)


def motion_window_collect(
    label: str,
    instruction: str,
    window_sec: float,
    focus: str,
    min_samples: int,
    min_span_steer: int,
    min_span_thr: int,
    strict_center: bool,
) -> tuple[bool, list[int], list[int]]:
    """
    Run one timed motion window; return (passed, steer_samples, throttle_samples).

    ``focus`` is ``"steer"``, ``"thr"``, or ``"both"`` (same semantics as interactive suite).
    """
    print("\n" + "─" * 72)
    print(label)
    print("─" * 72)
    print(instruction)
    print("Starting after countdown — window = %.1f s\n" % window_sec)
    countdown(3)
    print(">>> GO — move now…\n", flush=True)
    steer_vals, thr_vals = collect_pulses(window_sec)

    ss, ts = pulse_span(steer_vals), pulse_span(thr_vals)
    ns, nt = len(steer_vals), len(thr_vals)
    print("  GPIO%d (steer): %d samples  span=%d µs" % (PIN_STEER, ns, ss))
    print("  GPIO%d (thr):  %d samples  span=%d µs" % (PIN_THROTTLE, nt, ts))

    ok = True
    if focus in ("steer", "both"):
        if ns < min_samples:
            print("  FAIL: not enough steering samples (%d < %d)" % (ns, min_samples))
            ok = False
        if ss < min_span_steer:
            print(
                "  FAIL: steering span %d µs < %d µs — did you move steering full range (≥3 cycles)?"
                % (ss, min_span_steer)
            )
            ok = False
    if focus in ("thr", "both"):
        if nt < min_samples:
            print("  FAIL: not enough throttle samples (%d < %d)" % (nt, min_samples))
            ok = False
        if ts < min_span_thr:
            print(
                "  FAIL: throttle span %d µs < %d µs — did you move throttle full reverse/forward (≥3 cycles)?"
                % (ts, min_span_thr)
            )
            ok = False
    if strict_center and focus == "steer" and ts > 40:
        print(
            "  FAIL: throttle moved too much (span %d µs) — keep throttle centered for steer-only test."
            % ts
        )
        ok = False
    if strict_center and focus == "thr" and ss > 40:
        print(
            "  FAIL: steering moved too much (span %d µs) — keep steering centered for throttle-only test."
            % ss
        )
        ok = False

    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok, steer_vals, thr_vals


def phase_motion(
    label: str,
    instruction: str,
    window_sec: float,
    focus: str,
    min_samples: int,
    min_span_steer: int,
    min_span_thr: int,
    strict_center: bool,
) -> tuple[bool, list[int], list[int]]:
    """Alias for interactive suite — same as motion_window_collect."""
    return motion_window_collect(
        label,
        instruction,
        window_sec,
        focus,
        min_samples,
        min_span_steer,
        min_span_thr,
        strict_center,
    )

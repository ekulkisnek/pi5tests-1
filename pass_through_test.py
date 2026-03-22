#!/usr/bin/env python3
"""
RC PWM pass-through for Pi 5 (Raspberry Pi OS / Debian trixie).

Reads servo PWM on GPIO 17 & 27 via libgpiod edge timestamps, regenerates pulses
on GPIO 18 & 13 with lgpio tx_servo (software-timed — some jitter is normal).

Wiring (BCM):
  GPIO 17 (pin 11)  <- steering from receiver
  GPIO 27 (pin 13)  <- throttle from receiver
  GPIO 18 (pin 12)  -> steering servo signal
  GPIO 13 (pin 33)  -> ESC signal
  GND               -> common ground with RX / servo / ESC

Calibration (recommended):
  Run:  python3 -u rc_calibrate.py
  Writes ~/.config/rc_pass_calibration.json with measured neutral and idle noise.
  Pass-through loads it unless RC_CALIB_PATH=... or RC_CALIB=0.
  Input jitter check:  python3 -u rc_jitter_test.py  (hands off; compares to cal bands)

  RC_EDGE_POLL_SLEEP: inner wait when polling edges (default 0.0005 s). Try 0.001–0.002 in
  rc_twitch_ab_test.sh matrix if you want less busy-wait CPU use (see TWITCH_REDUCTION.md).

Idle latch:
  When steering stays near calibrated neutral for RC_IDLE_LATCH_MS, output is held
  at that neutral (reduces hunting from micro-updates). Throttle is not latched.

Hardware limit:
  For minimum idle twitch, use hardware PWM or a PCA9685 / servo driver on the
  steering line; Pi GPIO software PWM cannot match a receiver chip perfectly.

Do not stop with kill -9; use Ctrl+C so GPIO lines are released.

If wheels never move:
  1) python3 -u gpio_diag_gpiod.py
  2) Wheels up: python3 -u esc_output_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from datetime import timedelta
from statistics import median

import gpiod
import lgpio
from gpiod import LineSettings
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge

CHIP_PATH = "/dev/gpiochip0"
PIN_IN_STEER = 17
PIN_IN_THROTTLE = 27
PIN_OUT_STEER = 18
PIN_OUT_THROTTLE = 13

CENTER_US = 1500
CLAMP_LO = 800
CLAMP_HI = 2200

OUTPUT_HZ = float(os.environ.get("RC_OUTPUT_HZ", "50"))
OUTPUT_PERIOD = 1.0 / OUTPUT_HZ
# Inner loop sleep while waiting for gpiod edges (lower = snappier polling; higher = less CPU).
EDGE_POLL_SLEEP = float(os.environ.get("RC_EDGE_POLL_SLEEP", "0.0005"))


def load_calibration() -> dict | None:
    if os.environ.get("RC_CALIB", "").lower() in ("0", "false", "no"):
        return None
    path = os.path.expanduser(
        os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
    )
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") not in (1, 2):
            print("Warning: unknown calibration version", data.get("version"), file=sys.stderr)
        return data
    except OSError as e:
        print("Warning: could not read calibration:", e, file=sys.stderr)
        return None


def apply_deadband(raw: int, center: int, band: int) -> int:
    if abs(raw - center) <= band:
        return center
    return raw


def apply_steer_step_limit(previous: float, target: float, max_step: float) -> float:
    if max_step <= 0:
        return target
    delta = target - previous
    if abs(delta) <= max_step:
        return target
    return previous + (max_step if delta > 0 else -max_step)


def resolve_profile(cal: dict | None) -> str:
    p = os.environ.get("RC_PASS_PROFILE")
    if p:
        return p.strip().lower()
    if cal:
        return "idle_hold"
    return "baseline"


def main() -> int:
    debug = os.environ.get("RC_DEBUG", "")
    cal = load_calibration()

    steer_neutral = int(round(cal["steer_neutral_us"])) if cal else CENTER_US
    thr_neutral = int(round(cal["throttle_neutral_us"])) if cal else CENTER_US
    steer_idle_band = int(cal["steer_idle_band_us"]) if cal else int(os.environ.get("RC_STEER_IDLE_BAND_US", "8"))
    thr_idle_band = int(cal["throttle_idle_band_us"]) if cal else int(os.environ.get("RC_THR_IDLE_BAND_US", "10"))

    dead_steer = steer_idle_band if cal else int(os.environ.get("RC_STEER_DEADBAND_US", "8"))
    dead_thr = thr_idle_band if cal else int(os.environ.get("RC_THROTTLE_DEADBAND_US", "10"))

    profile = resolve_profile(cal)
    if profile == "baseline":
        idle_hold = os.environ.get("RC_IDLE_HOLD", "0").lower() in ("1", "true", "yes")
        steer_median_len = int(os.environ.get("RC_STEER_MEDIAN_LEN", "0"))
        steer_quant = int(os.environ.get("RC_STEER_QUANT_US", "0"))
        steer_max_step = int(os.environ.get("RC_STEER_MAX_STEP_US", "0"))
        steer_active_smooth = float(os.environ.get("RC_STEER_ACTIVE_SMOOTH", "0.5"))
    elif profile == "hold_only":
        idle_hold = True
        steer_median_len = int(os.environ.get("RC_STEER_MEDIAN_LEN", "0"))
        steer_quant = int(os.environ.get("RC_STEER_QUANT_US", "0"))
        steer_max_step = int(os.environ.get("RC_STEER_MAX_STEP_US", "0"))
        steer_active_smooth = float(os.environ.get("RC_STEER_ACTIVE_SMOOTH", "0.5"))
    else:
        # idle_hold (default when calibration exists)
        idle_hold = os.environ.get("RC_IDLE_HOLD", "1").lower() not in ("0", "false", "no")
        steer_median_len = int(os.environ.get("RC_STEER_MEDIAN_LEN", "3"))
        steer_quant = int(os.environ.get("RC_STEER_QUANT_US", "0"))
        steer_max_step = int(os.environ.get("RC_STEER_MAX_STEP_US", "0"))
        steer_active_smooth = float(os.environ.get("RC_STEER_ACTIVE_SMOOTH", "0.45"))

    throttle_smooth = float(os.environ.get("RC_THROTTLE_SMOOTH", "0.45"))
    latch_ms = float(os.environ.get("RC_IDLE_LATCH_MS", "150")) / 1000.0

    in_cfg = LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
    )
    req = gpiod.request_lines(
        CHIP_PATH,
        consumer="rc_pass_through",
        config={
            PIN_IN_STEER: in_cfg,
            PIN_IN_THROTTLE: in_cfg,
        },
        event_buffer_size=256,
    )

    h = lgpio.gpiochip_open(0)
    if h < 0:
        print("lgpio gpiochip_open failed:", h, file=sys.stderr)
        req.release()
        return 1

    for pin in (PIN_OUT_STEER, PIN_OUT_THROTTLE):
        e = lgpio.gpio_claim_output(h, pin, level=0)
        if e < 0:
            print("lgpio gpio_claim_output GPIO%d failed: %d" % (pin, e), file=sys.stderr)
            req.release()
            lgpio.gpiochip_close(h)
            return 1

    pulse_us = {PIN_IN_STEER: steer_neutral, PIN_IN_THROTTLE: thr_neutral}
    last_rise_ns: dict[int, int | None] = {PIN_IN_STEER: None, PIN_IN_THROTTLE: None}
    edge_count = 0
    pulse_updates = 0

    smooth_s = float(steer_neutral)
    smooth_t = float(thr_neutral)
    steer_stepped = float(steer_neutral)
    next_out = time.monotonic()
    steer_hist: deque[int] = deque(
        maxlen=max(steer_median_len, 3) if steer_median_len > 0 else 3
    )

    steer_latched = False
    inside_since: float | None = None

    cal_path = os.path.expanduser(
        os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
    )
    print("Pass-through (gpiod in + lgpio out). Ctrl+C to stop. RC_DEBUG=1 for stats.")
    print(
        "IN steer=%d throttle=%d  OUT steer=%d throttle=%d"
        % (PIN_IN_STEER, PIN_IN_THROTTLE, PIN_OUT_STEER, PIN_OUT_THROTTLE)
    )
    print(
        "Profile=%s  idle_hold=%s  neutral steer/thr=%d/%d µs  latch_window=%.0f ms"
        % (profile, idle_hold, steer_neutral, thr_neutral, latch_ms * 1000)
    )
    print(
        "Bands ±%d/%d µs  active_smooth=%.2f  median=%s  quant=%s  max_step=%s  cal=%s"
        % (
            dead_steer,
            dead_thr,
            steer_active_smooth,
            steer_median_len if steer_median_len > 0 else "off",
            steer_quant if steer_quant > 0 else "off",
            steer_max_step if steer_max_step > 0 else "off",
            cal_path if cal else "none",
        )
    )
    print("Output Hz=%.1f (period=%.4f s)  RC_EDGE_POLL_SLEEP=%.4f s" % (OUTPUT_HZ, OUTPUT_PERIOD, EDGE_POLL_SLEEP))

    try:
        while True:
            now = time.monotonic()
            while now < next_out:
                if req.wait_edge_events(timedelta(seconds=0)):
                    for ev in req.read_edge_events():
                        edge_count += 1
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
                                pulse_us[off] = int(round(span_us))
                                pulse_updates += 1
                                if debug and (pulse_updates % 75 == 0):
                                    print("pulse", off, pulse_us[off], "us")
                else:
                    time.sleep(EDGE_POLL_SLEEP)
                now = time.monotonic()

            s_sample = max(CLAMP_LO, min(CLAMP_HI, pulse_us[PIN_IN_STEER]))
            t_raw = max(CLAMP_LO, min(CLAMP_HI, pulse_us[PIN_IN_THROTTLE]))

            if steer_median_len > 0:
                steer_hist.append(s_sample)
                s_med = int(round(median(steer_hist)))
            else:
                s_med = s_sample

            s_raw = apply_deadband(s_med, steer_neutral, dead_steer)
            t_raw = apply_deadband(t_raw, thr_neutral, dead_thr)

            inside = abs(s_med - steer_neutral) <= steer_idle_band
            if idle_hold:
                if inside:
                    if inside_since is None:
                        inside_since = now
                    if not steer_latched and inside_since is not None and (now - inside_since) >= latch_ms:
                        steer_latched = True
                else:
                    inside_since = None
                    steer_latched = False
            else:
                steer_latched = False
                inside_since = None

            if steer_latched:
                out_s = steer_neutral
                smooth_s = float(out_s)
                steer_stepped = float(out_s)
            else:
                smooth_s = steer_active_smooth * s_raw + (1.0 - steer_active_smooth) * smooth_s
                steer_stepped = apply_steer_step_limit(
                    steer_stepped, smooth_s, float(steer_max_step)
                )
                out_s = int(round(steer_stepped))
                if steer_quant > 0:
                    q = steer_quant
                    out_s = int(q * round(out_s / q))
                out_s = max(CLAMP_LO, min(CLAMP_HI, out_s))

            smooth_t = throttle_smooth * t_raw + (1.0 - throttle_smooth) * smooth_t
            out_t = int(round(smooth_t))

            r1 = lgpio.tx_servo(h, PIN_OUT_STEER, out_s)
            r2 = lgpio.tx_servo(h, PIN_OUT_THROTTLE, out_t)
            if r1 < 0 or r2 < 0:
                print("tx_servo warning:", r1, r2, file=sys.stderr)

            next_out += OUTPUT_PERIOD
            if next_out < now:
                next_out = now + OUTPUT_PERIOD

    except KeyboardInterrupt:
        print("\nNeutral outputs... edges=%d pulses=%d" % (edge_count, pulse_updates))
        lgpio.tx_servo(h, PIN_OUT_STEER, steer_neutral)
        lgpio.tx_servo(h, PIN_OUT_THROTTLE, thr_neutral)
        time.sleep(0.25)
    finally:
        req.release()
        for pin in (PIN_OUT_STEER, PIN_OUT_THROTTLE):
            try:
                lgpio.gpio_free(h, pin)
            except Exception:
                pass
        lgpio.gpiochip_close(h)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

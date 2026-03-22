#!/usr/bin/env python3
"""
ESC / servo OUTPUT sanity check on GPIO 13 (throttle) and GPIO 18 (steer).

Run with wheels OFF THE GROUND and prop/motor safe. Sends known PWM widths via
lgpio tx_servo so you can hear ESC beeps or see steering twitch.

Sequence: hold neutral, full forward pulse, full reverse pulse, neutral.
"""
from __future__ import annotations

import sys
import time

import lgpio

PIN_ESC = 13
PIN_STEER = 18


def main() -> int:
    h = lgpio.gpiochip_open(0)
    if h < 0:
        print("gpiochip_open failed:", h, file=sys.stderr)
        return 1

    for p in (PIN_ESC, PIN_STEER):
        e = lgpio.gpio_claim_output(h, p, level=0)
        if e < 0:
            print("claim output GPIO%d failed: %d" % (p, e), file=sys.stderr)
            lgpio.gpiochip_close(h)
            return 1

    print("ESC output test: GPIO%d  Steer test: GPIO%d" % (PIN_ESC, PIN_STEER))
    print("Neutral 1.5ms for 2s...")
    lgpio.tx_servo(h, PIN_ESC, 1500)
    lgpio.tx_servo(h, PIN_STEER, 1500)
    time.sleep(2.0)

    print("ESC ~2000us 1.0s (expect forward/beep depending on ESC)...")
    lgpio.tx_servo(h, PIN_ESC, 2000)
    time.sleep(1.0)

    print("ESC ~1000us 1.0s...")
    lgpio.tx_servo(h, PIN_ESC, 1000)
    time.sleep(1.0)

    print("Steer sweep 1000–2000us while ESC neutral...")
    lgpio.tx_servo(h, PIN_ESC, 1500)
    for pw in (1200, 1500, 1800, 1500):
        print("  steer", pw, "us")
        lgpio.tx_servo(h, PIN_STEER, pw)
        time.sleep(0.7)

    print("Back to neutral. Done.")
    lgpio.tx_servo(h, PIN_ESC, 1500)
    lgpio.tx_servo(h, PIN_STEER, 1500)
    time.sleep(0.3)

    for p in (PIN_ESC, PIN_STEER):
        lgpio.gpio_free(h, p)
    lgpio.gpiochip_close(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

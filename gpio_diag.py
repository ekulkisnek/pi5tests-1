#!/usr/bin/env python3
"""Quick GPIO PWM diagnostic for Pi 5 + lgpio (run while moving TX sticks)."""
from __future__ import annotations

import sys
import time

import lgpio

PINS = (17, 27)


def main() -> int:
    h = lgpio.gpiochip_open(0)
    if h < 0:
        print("gpiochip_open failed:", h, file=sys.stderr)
        return 1

    n_events = 0
    n_pulse = {17: 0, 27: 0}
    last_rise: dict[int, int | None] = {17: None, 27: None}

    def cbf(chip: int, gpio: int, level: int, tick: int) -> None:
        nonlocal n_events
        n_events += 1
        if n_events <= 12:
            print("raw_evt chip=%d gpio=%d level=%d tick=%d" % (chip, gpio, level, tick))
        if gpio not in last_rise:
            return
        if level == 1:
            last_rise[gpio] = tick
            return
        if level != 0:
            return
        t0 = last_rise[gpio]
        if t0 is None:
            return
        span_us = (tick - t0) / 1000.0
        last_rise[gpio] = None
        if 500 <= span_us <= 2500:
            n_pulse[gpio] += 1
            if n_pulse[gpio] <= 8 or n_pulse[gpio] % 25 == 0:
                print("pulse_us gpio%d = %.0f" % (gpio, span_us))

    for pin in PINS:
        e = lgpio.gpio_claim_alert(h, pin, lgpio.BOTH_EDGES)
        print("claim_alert GPIO%d -> %d" % (pin, e))
        if e < 0:
            return 1

    cbs = [lgpio.callback(h, p, lgpio.BOTH_EDGES, cbf) for p in PINS]
    print("Listening 6s — move steering and throttle on the transmitter...")
    time.sleep(6)
    for cb in cbs:
        cb.cancel()
    for pin in PINS:
        lgpio.gpio_free(h, pin)
    lgpio.gpiochip_close(h)

    print("--- summary ---")
    print("total_edge_events:", n_events)
    print("valid_pulses GPIO17:", n_pulse[17], " GPIO27:", n_pulse[27])
    if n_events == 0:
        print(
            "No edges: wiring/pin mismatch, receiver unpowered, or wrong GPIO chip index for lgpio callbacks."
        )
    elif n_pulse[17] == 0 and n_pulse[27] == 0:
        print("Edges seen but no 500–2500us pulses: check tick scaling or signal integrity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

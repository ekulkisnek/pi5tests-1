#!/usr/bin/env python3
"""Count PWM edges/pulses on GPIO 17 & 27 using libgpiod (receiver must be powered)."""
from __future__ import annotations

import sys
import time
from datetime import timedelta

import gpiod
from gpiod import LineSettings
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge

CHIP = "/dev/gpiochip0"
PINS = (17, 27)
SECS = 6


def main() -> int:
    ls = LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
    )
    cfg = {p: ls for p in PINS}
    req = gpiod.request_lines(
        CHIP,
        consumer="rc_diag",
        config=cfg,
        event_buffer_size=512,
    )

    last_rise: dict[int, int | None] = {p: None for p in PINS}
    edges = 0
    pulses = {p: 0 for p in PINS}

    print("Watching GPIO 17 & 27 for %ds — power RX + TX, move sticks..." % SECS)
    deadline = time.monotonic() + SECS
    while time.monotonic() < deadline:
        if req.wait_edge_events(timedelta(seconds=0.2)):
            for ev in req.read_edge_events():
                edges += 1
                off = ev.line_offset
                if off not in last_rise:
                    continue
                if ev.event_type == EdgeEvent.Type.RISING_EDGE:
                    last_rise[off] = ev.timestamp_ns
                elif ev.event_type == EdgeEvent.Type.FALLING_EDGE:
                    t0 = last_rise[off]
                    if t0 is None:
                        continue
                    us = (ev.timestamp_ns - t0) / 1000.0
                    last_rise[off] = None
                    if 500 <= us <= 2500:
                        pulses[off] += 1
                        if pulses[off] <= 6:
                            print("  pulse GPIO%d ~%.0fus" % (off, us))

    req.release()
    print("---")
    print("total_edges:", edges)
    print("valid_pulses GPIO17:", pulses[17], " GPIO27:", pulses[27])
    if edges == 0:
        print(
            "No edges: receiver not powered, signal not on BCM17/27, or ground missing from Pi to car."
        )
    elif pulses[17] == 0 and pulses[27] == 0:
        print("Edges but no clean 500–2500us pulses — noise, wrong voltage, or timing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

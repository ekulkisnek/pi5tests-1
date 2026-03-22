#!/usr/bin/env python3
"""
Quick RC line probes — standard hobby signal is 50 Hz frame, ~1–2 ms HIGH pulse.

What we learned from the suite: if edge counts stay 0, the Pi GPIO is not seeing
transitions (wiring / common ground / RX power / wrong BCM pin / voltage levels).

This script does NOT move the car; it only listens. Power the receiver and move
sticks during each window when prompted.
"""
from __future__ import annotations

import sys
import time
from datetime import timedelta

import gpiod
from gpiod import LineSettings
from gpiod.line import Bias, Direction, Edge

CHIP = "/dev/gpiochip0"
PINS = (17, 27)


def count_edges(
    offset: int,
    seconds: float,
    bias: Bias,
    debounce_us: int = 0,
) -> int:
    debounce = timedelta(microseconds=debounce_us) if debounce_us else timedelta()
    ls = LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=bias,
        debounce_period=debounce,
    )
    req = gpiod.request_lines(
        CHIP,
        consumer="rc_signal_probe",
        config={offset: ls},
        event_buffer_size=2048,
    )
    n = 0
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        wait = min(0.05, t_end - time.monotonic())
        if wait <= 0:
            break
        if req.wait_edge_events(timedelta(seconds=wait)):
            n += len(req.read_edge_events())
    req.release()
    return n


def print_tx_instructions() -> None:
    print(
        """
╔══════════════════════════════════════════════════════════════════════════════╗
║  WHAT TO DO ON THE TRANSMITTER (read this once)                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  BEFORE STARTING:                                                             ║
║    • Car battery ON  →  receiver must have power (LED on RX if it has one).  ║
║    • Transmitter ON and already bound/paired to the car (normal driving mode).║
║                                                                               ║
║  YOU SHOULD MOVE ONLY THESE TWO CONTROLS (continuously during each BEEP):    ║
║    1) STEERING  — the wheel or left stick that turns the front wheels.      ║
║       → This should match the white/yellow signal wire you put on Pi GPIO17   ║
║          (physical pin 11). Slow full left ↔ full right, repeat.              ║
║    2) THROTTLE  — trigger or right stick that makes the motor go FWD/REV.     ║
║       → Matches the wire on Pi GPIO27 (physical pin 13).                      ║
║          Slowly full reverse ↔ neutral ↔ full forward, repeat.               ║
║                                                                               ║
║  DO NOT rely on these for this test (they usually do NOT generate PWM edges   ║
║  on CH1/CH2 signal wires):                                                    ║
║    • Trim buttons / knobs  • Bind / range check  • Rate / EPA / DR / mode     ║
║    • Any “turbo” or “LED” or menu buttons unless you know they move CH1/2     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    )


def countdown_prepare(phase: str, seconds: int = 5) -> None:
    print("\n>>> %s" % phase)
    for i in range(seconds, 0, -1):
        print(
            ">>>  %d …  NOW: rock STEERING wheel/stick + THROTTLE trigger back & forth"
            % i,
            flush=True,
        )
        time.sleep(1.0)
    print(">>>  MEASURING — keep moving both until the next line appears.\n", flush=True)


def main() -> int:
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    print("RC signal probe — gpiod edge counts (50 Hz PWM ⇒ expect many edges if wiring is good)")
    print("Each sample window: %.1fs of listening after the countdown.\n" % dur)
    print_tx_instructions()
    if sys.stdin.isatty():
        input("Press ENTER when car + TX are on and you’re ready… ")
    else:
        print("(Non-interactive: 10s — put car+RX on, TX on, hands on STEERING + THROTTLE.)\n")
        time.sleep(10.0)

    # PULL_DOWN first: that bias matched your throttle line best last time.
    biases: list[tuple[str, Bias]] = [
        ("PULL_DOWN (try this first — matches many RX outputs)", Bias.PULL_DOWN),
        ("AS_IS (leave bias)", Bias.AS_IS),
        ("PULL_UP", Bias.PULL_UP),
    ]

    for label, bias in biases:
        print("\n" + "=" * 72)
        print("PHASE: %s" % label)
        print("=" * 72)
        for pin in PINS:
            role = "STEERING input (GPIO17 / pin 11)" if pin == 17 else "THROTTLE input (GPIO27 / pin 13)"
            countdown_prepare("Next sample: %s — %s" % (label, role), seconds=5)
            n = count_edges(pin, dur, bias)
            print("  RESULT: GPIO%d edges in %.1fs: %d" % (pin, dur, n))
        print()

    print("Interpretation:")
    print("  • All zeros: no transitions seen → check signal wire on BCM 17/27, common GND, RX power.")
    print("  • Non-zero only with PULL_UP/DOWN: weak/open-drain output; may still work for pass-through.")
    print("  • Hundreds+ per second on one pin only: likely correct CH1/CH2 mapping swap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

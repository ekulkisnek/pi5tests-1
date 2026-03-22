#!/usr/bin/env python3
"""
Measure RX pulse jitter on GPIO 17 (steer) and 27 (throttle) — hands-off window.

Compares raw spread to ~/.config/rc_pass_calibration.json (if present) so you can
see whether idle noise fits inside calibrated bands. Does not drive outputs.

Usage (on Pi, car + RX + TX on, hands off sticks during sample):
  python3 -u rc_jitter_test.py
  RC_JITTER_SECS=10 python3 -u rc_jitter_test.py
  RC_CALIB_PATH=/path/to/cal.json python3 -u rc_jitter_test.py

This measures **input** jitter only. Remaining twitch at the servo can still come
from software PWM on the output (see pass_through_test.py docstring).

Interpreting lines vs calibration:
  - **Drift** (mean − cal neutral): trim changed or cal is stale — re-run rc_calibrate if large.
  - **vs cal neutral ±band**: how many samples sit outside the *stored* idle window (misleading if drift is large).
  - **vs measured mean ±band**: idle **noise** around today's center (small % = stable RX).
"""
from __future__ import annotations

import json
import os
import sys

from rc_calibrate import collect_pulses
from rc_idle_metrics import (
    count_outside_band,
    drift_us,
    drift_warning,
    idle_mean_pstdev_span,
)


def load_cal(path: str) -> dict | None:
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        print("Warning: could not read calibration:", e, file=sys.stderr)
        return None


def summarize(name: str, vals: list[int], neutral: float | None, band: int | None) -> None:
    n = len(vals)
    if n < 2:
        print(f"  {name}: too few samples ({n})")
        return
    stats = idle_mean_pstdev_span(vals)
    if stats is None:
        print(f"  {name}: too few samples ({n})")
        return
    m, sd, lo, hi, span = stats
    print(f"  {name}: n={n}  mean={m:.1f} µs  pstdev={sd:.3f} µs  min={lo} max={hi} span={span} µs")
    if neutral is not None and band is not None:
        d = drift_us(m, neutral)
        outside_cal, pct_cal = count_outside_band(vals, neutral, band)
        outside_mean, pct_mean = count_outside_band(vals, m, band)
        print(
            f"         drift from cal: {d:+.1f} µs  "
            f"(stored neutral {neutral:.1f} µs)"
        )
        hint = drift_warning(abs(d), band)
        if hint:
            print(f"         → {hint}")
        print(
            f"         vs cal neutral ±{band} µs: "
            f"{outside_cal} samples outside ({pct_cal:.1f}%)"
        )
        print(
            f"         vs measured mean ±{band} µs (noise): "
            f"{outside_mean} samples outside ({pct_mean:.1f}%)"
        )


def main() -> int:
    secs = float(os.environ.get("RC_JITTER_SECS", "8"))
    cal_path = os.path.expanduser(
        os.environ.get("RC_CALIB_PATH", os.path.join("~", ".config", "rc_pass_calibration.json"))
    )
    cal = load_cal(cal_path)

    print(
        "RC jitter test — INPUT only (GPIO 17 / 27).\n"
        "Hands OFF both sticks for the whole sample window.\n"
        f"Sampling {secs:.1f} s...\n"
    )
    input("Press ENTER when ready (then do not touch sticks)... ")
    s_vals, t_vals = collect_pulses(secs)

    print("\n── Results ──")
    sn = cal.get("steer_neutral_us") if cal else None
    sb = cal.get("steer_idle_band_us") if cal else None
    tn = cal.get("throttle_neutral_us") if cal else None
    tb = cal.get("throttle_idle_band_us") if cal else None
    if cal:
        print(f"Calibration file: {cal_path} (version {cal.get('version', '?')})")
    else:
        print(f"No calibration at {cal_path} — bands line omitted.")

    summarize("Steer ", s_vals, float(sn) if sn is not None else None, int(sb) if sb is not None else None)
    summarize("Throttle", t_vals, float(tn) if tn is not None else None, int(tb) if tb is not None else None)

    print(
        "\nInterpret: low pstdev/span with hands off is good RX + wiring. "
        "If values look fine here but wheels still twitch, suspect output PWM / servo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

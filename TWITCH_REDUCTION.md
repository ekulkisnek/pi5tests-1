# Twitch reduction (pass-through)

Use this **after** the main [`rc_walkthrough.py`](rc_walkthrough.py) steps ([`WALKTHROUGH.md`](WALKTHROUGH.md)) (pytest → **`rc_calibrate.py --suite`** → jitter → lighter interactive suite) so wiring and RX idle are already validated.

## What actually runs the servos

[`pass_through_test.py`](pass_through_test.py) reads PWM with **gpiod** and writes with **`lgpio.tx_servo`** (software-timed on the Pi). It is **not** pigpio. Community notes about `time.sleep(0.005)` in a “200 Hz loop” do **not** map line-for-line to this repo.

The knobs that **do** map:

| Idea (community / Donkey-style) | This repo |
|----------------------------------|-----------|
| Lower / raise output update rate | **`RC_OUTPUT_HZ`** — output period is `1 / RC_OUTPUT_HZ` seconds. Default **50 Hz** ≈ **20 ms** per `tx_servo` tick. **67 Hz** ≈ **15 ms**; **100 Hz** ≈ **10 ms**; **40 Hz** ≈ **25 ms**. |
| Less busy-wait while polling RX edges | **`RC_EDGE_POLL_SLEEP`** — inner sleep when no edge (default **0.0005** s). Try **0.001** or **0.002** if you want to reduce tight polling load (may slightly affect input responsiveness). |
| Deadband / neutral | **`rc_calibrate.py --suite`** (recommended) → JSON; **`RC_PASS_PROFILE`**, **`RC_IDLE_LATCH_MS`**, idle bands in JSON / env. |
| Profile comparison | [`rc_pass_ab_test.sh`](rc_pass_ab_test.sh) — baseline vs idle_hold vs hold_only. |
| Full matrix (Hz + profile + latch + poll) | [`rc_twitch_ab_test.sh`](rc_twitch_ab_test.sh) — see below. |

## Acceptance (software-only)

Automated tests can enforce **valid calibration JSON** and **reasonable endpoint spans**; they **cannot** certify **zero mechanical twitch** on `lgpio` outputs. Use this doc + [`rc_twitch_ab_test.sh`](rc_twitch_ab_test.sh) for subjective output tuning; use a **PCA9685** or hardware PWM if you need the last bit of smoothness.

## Recommended order

1. **Calibration** — `python3 -u rc_calibrate.py --suite` when trim or RX changes (walkthrough step 2 runs this by default).
2. **Input jitter** — `python3 -u rc_jitter_test.py` (hands off) to confirm RX idle is reasonable.
3. **Twitch matrix** (subjective) — run `./rc_twitch_ab_test.sh` on the Pi; note which segment wins.
4. **Hardware** (manual) — see checklist below; cannot be automated.
5. **Optional external** — [Donkey Car](https://docs.donkeycar.com/) or a **PCA9685** hat are separate stacks; not required for this repo’s pass-through.

## `rc_twitch_ab_test.sh`

Runs **eight** timed segments (default **30 s** each) with different env combinations. After each segment, note **twitch 1–5** (1 = none) and steering feel.

```bash
cd ~/pi5tests-1
./rc_twitch_ab_test.sh
```

Fast **dry run** (prints segment list only, no GPIO):

```bash
RC_TWITCH_DRY_RUN=1 ./rc_twitch_ab_test.sh
```

Shorter segments for a quick pass:

```bash
RC_TWITCH_SECS=10 ./rc_twitch_ab_test.sh
```

At the end, run [`pass_through_test.py`](pass_through_test.py) with the **same** environment variables as the winning segment, e.g.:

```bash
RC_OUTPUT_HZ=67 RC_PASS_PROFILE=idle_hold python3 -u pass_through_test.py
```

Startup prints `Output Hz=…`, `RC_EDGE_POLL_SLEEP=…`, and profile — use these to confirm settings.

## Hardware checklist (manual)

| Item | Notes |
|------|--------|
| **470 µF (or similar) across 5 V and GND** at the Pi | Electrolytic: + to 5 V, − to GND. Can reduce noise-related jitter; verify polarity. |
| **Servo / ESC power** | Prefer **BEC** or ESC 5 V for heavy loads; **avoid** powering large servos only from the Pi’s 5 V pin. |
| **Common ground** | Pi, RX, ESC, servo signal ground must share reference. |
| **PCA9685 / servo HAT** (optional) | Dedicated PWM chip; **not** wired in this repo’s default scripts — future hardware upgrade. |

## What this repo does not install

- **Donkey Car** — separate project; install from [Donkey docs](https://docs.donkeycar.com/) if you want that stack.
- **pigpio** output path — `pass_through_test.py` uses **lgpio** for outputs today.

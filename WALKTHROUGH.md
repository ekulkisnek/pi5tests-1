# RC Pi verification walkthrough

Single ordered entry point: [`rc_walkthrough.py`](rc_walkthrough.py). Run from the **repo root** on the Raspberry Pi (GPIO scripts require Pi + `gpiod` / `lgpio`).

## Push repo from your Mac (required path is on the Mac, not on the Pi)

Run **on the Mac** where this repo lives (`rsync` cannot use `/Users/...` when executed on the Pi):

```bash
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '.venv' \
  /Users/Contributor/coding/pi5tests-1/ pi5-1@192.168.1.193:~/pi5tests-1/
```

Adjust the source path if your clone is elsewhere.

## One-time Pi setup (pytest + system `gpiod` in venv)

**On the Pi:**

```bash
cd ~/pi5tests-1
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.txt
```

[`rc_walkthrough.py`](rc_walkthrough.py) prefers `.venv/bin/python` when it can `import pytest`, so step 1 works without a global `pip install pytest`.

## Quick start (SSH with TTY)

From your Mac (or any machine that can reach the Pi on the LAN):

```bash
ssh -t pi5-1@192.168.1.193 'cd ~/pi5tests-1 && python3 -u rc_walkthrough.py'
```

Replace `192.168.1.193` if your Pi uses another IP or hostname. Steps 3–4 need a **terminal** (prompts). Use **`ssh -t`**, not plain `ssh`.

## Pi venv (pytest sees system `gpiod`)

```bash
cd ~/pi5tests-1
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -u rc_walkthrough.py
```

## Unified flow (default)

```mermaid
flowchart LR
  pytest[Step1 pytest]
  cal[Step2 rc_calibrate --suite]
  val[validate JSON + endpoints]
  jitter[Step3 rc_jitter_test]
  suite[Step4 interactive suite]
  pytest --> cal --> val --> jitter --> suite
```

Step **2** runs **[`rc_calibrate.py --suite`](rc_calibrate.py)** (idle + 10 s steer-only + 10 s throttle-only windows, same thresholds as the interactive suite). It **does not write** JSON if motion span is too small. Step **2** then validates required keys and **endpoint consistency** (min/max span).

Step **4** runs [`rc_interactive_suite.py`](rc_interactive_suite.py) with **`RC_SUITE_SKIP_INPUT_MOTION=1`** so Phase A/B/C motion is **not** repeated — only idle snapshot (optional), ESC (optional), and pass-through smoke. Use **`--skip-suite-cal`** on the walkthrough if you only want to validate an existing file and run the **full** interactive suite including motion phases.

## Steps (what each proves)

| Step | Name | What it checks | Pass | Typical failure |
|------|------|----------------|------|-----------------|
| 1 | pytest | Repo files, optional `gpiod`/`lgpio` import | Exit 0 | Missing script; wrong cwd |
| 2 | Suite cal + validation | [`rc_calibrate.py --suite`](rc_calibrate.py) then schema + endpoint span | OK | Bad motion; span &lt; threshold; missing file |
| 3 | Idle jitter | [`rc_jitter_test.py`](rc_jitter_test.py) — hands off | User completes window | Not TTY → skipped |
| 4 | Interactive suite | Idle + optional ESC + pass smoke (input motion skipped after suite cal) | All phases PASS | Wiring / thresholds |
| 5 | Manual | Prints commands only | — | — |

**Re-run suite calibration** when trim/RX changes or drift vs cal returns in jitter tests.

After steps 1–4 pass, use **[`TWITCH_REDUCTION.md`](TWITCH_REDUCTION.md)** for subjective **output** twitch experiments (`RC_OUTPUT_HZ`, profiles, [`rc_twitch_ab_test.sh`](rc_twitch_ab_test.sh)) and a **hardware checklist** (capacitor, BEC, ground). That is separate from the numbered walkthrough so you can iterate without re-running pytest.

## Useful flags

| Flag | Meaning |
|------|---------|
| `--dry-run` | Print what would run; no GPIO |
| `--from-step N` / `--to-step N` | Run subset (1–5) |
| `--require-cal` | Fail step 2 if calibration missing/invalid |
| `--skip-suite-cal` | Step 2: only validate existing JSON; step 4 runs **full** motion phases |
| `--skip-jitter` / `--skip-interactive` | Skip steps 3–4 |
| `--continue-on-fail` | Continue after a failed step |
| `RC_WALKTHROUGH_PAUSE=0` | No “Press ENTER” between steps |

## Related scripts

- [`run_all_rc_tests.sh`](run_all_rc_tests.sh) — pytest + interactive suite (no jitter / no walkthrough ordering)
- [`rc_pass_ab_test.sh`](rc_pass_ab_test.sh) — A/B/C pass-through profiles (~30 s each)
- [`rc_twitch_ab_test.sh`](rc_twitch_ab_test.sh) — twitch matrix: `RC_OUTPUT_HZ`, profiles, latch, `RC_EDGE_POLL_SLEEP` ([`TWITCH_REDUCTION.md`](TWITCH_REDUCTION.md))
- [`pass_through_test.py`](pass_through_test.py) — normal driving

## macOS / dev machine

`pytest` file checks OK; GPIO steps only run meaningfully on the Pi.

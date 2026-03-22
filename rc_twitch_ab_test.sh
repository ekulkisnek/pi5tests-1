#!/bin/bash
# Twitch-reduction matrix for pass_through_test.py — timed segments, vary RC_OUTPUT_HZ,
# RC_PASS_PROFILE, RC_IDLE_LATCH_MS, RC_EDGE_POLL_SLEEP. Rate twitch after each segment.
# Prereq: rc_calibrate.py (recommended) so calibration JSON exists.
# Uses Python subprocess timeout (no GNU coreutils `timeout` required).
#
# Env:
#   RC_TWITCH_SECS   Segment duration (default: 30). Use 1 for a quick dry run of flow.
#   RC_TWITCH_DRY_RUN=1  Print planned segments and exit without GPIO.
#   RC_PASS_SCRIPT   Override path to pass_through_test.py
#   RC_PYTHON        Python to use (default: python3)
set -euo pipefail
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEG_SEC="${RC_TWITCH_SECS:-30}"
PY="${RC_PYTHON:-python3}"
PASS="${RC_PASS_SCRIPT:-$SCRIPT_DIR/pass_through_test.py}"
if [[ ! -f "$PASS" ]]; then
  PASS="${HOME}/pass_through_test.py"
fi
if [[ ! -f "$PASS" ]]; then
  echo "pass_through_test.py not found. Set RC_PASS_SCRIPT=/path/to/pass_through_test.py"
  exit 1
fi

if [[ "${RC_TWITCH_DRY_RUN:-}" == "1" ]]; then
  echo "RC_TWITCH_DRY_RUN=1 — planned segments (${SEG_SEC}s each if run):"
  echo "  1) h50_idle_hold      RC_OUTPUT_HZ=50   RC_PASS_PROFILE=idle_hold"
  echo "  2) h67_idle_hold      RC_OUTPUT_HZ=67   RC_PASS_PROFILE=idle_hold   (~15ms period)"
  echo "  3) h100_idle_hold     RC_OUTPUT_HZ=100  RC_PASS_PROFILE=idle_hold  (stress)"
  echo "  4) h40_idle_hold      RC_OUTPUT_HZ=40   RC_PASS_PROFILE=idle_hold  (slower updates)"
  echo "  5) h50_hold_only      RC_OUTPUT_HZ=50   RC_PASS_PROFILE=hold_only"
  echo "  6) h50_baseline       RC_OUTPUT_HZ=50   RC_PASS_PROFILE=baseline + median/quant off"
  echo "  7) h50_latch250       RC_OUTPUT_HZ=50   RC_PASS_PROFILE=idle_hold RC_IDLE_LATCH_MS=250"
  echo "  8) h50_poll2ms        RC_OUTPUT_HZ=50   RC_EDGE_POLL_SLEEP=0.002   (coarser edge poll)"
  echo "Done (dry run)."
  exit 0
fi

echo "══════════════════════════════════════════════════════════════════════"
echo " RC twitch-reduction matrix  (${SEG_SEC}s each segment)"
echo " After each: note twitch 1-5 (1=none), steering feel (sluggish?)."
echo " Car + RX + TX on, wheels safe. Ctrl+C aborts."
echo " See TWITCH_REDUCTION.md for mapping vs community advice (RC_OUTPUT_HZ, etc.)."
echo "══════════════════════════════════════════════════════════════════════"
echo

run_seg() {
  local name="$1"
  shift
  echo ""
  echo ">>> SEGMENT: $name  (${SEG_SEC}s) — hands off idle + small steer/throttle as needed."
  echo ">>> Then note twitch (1-5) and whether steering felt slow or mushy."
  sleep 2
  env RC_AB_CHILD="$PASS" RC_AB_SEG="$SEG_SEC" "$@" \
    "$PY" -c '
import os, subprocess, sys
p = os.environ["RC_AB_CHILD"]
t = float(os.environ["RC_AB_SEG"])
try:
    subprocess.run([sys.executable, "-u", p], env=os.environ, timeout=t)
except subprocess.TimeoutExpired:
    pass
'
  echo "--- end $name (timed stop) ---"
  echo ""
  read -r -p "Press ENTER for next segment... " || true
}

run_seg "h50_idle_hold" \
  RC_OUTPUT_HZ=50 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1

run_seg "h67_idle_hold" \
  RC_OUTPUT_HZ=67 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1

run_seg "h100_idle_hold" \
  RC_OUTPUT_HZ=100 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1

run_seg "h40_idle_hold" \
  RC_OUTPUT_HZ=40 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1

run_seg "h50_hold_only" \
  RC_OUTPUT_HZ=50 RC_PASS_PROFILE=hold_only RC_IDLE_HOLD=1

run_seg "h50_baseline" \
  RC_OUTPUT_HZ=50 RC_PASS_PROFILE=baseline RC_IDLE_HOLD=0 \
  RC_STEER_MEDIAN_LEN=0 RC_STEER_QUANT_US=0 RC_STEER_MAX_STEP_US=0

run_seg "h50_latch250" \
  RC_OUTPUT_HZ=50 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1 RC_IDLE_LATCH_MS=250

run_seg "h50_poll2ms" \
  RC_OUTPUT_HZ=50 RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1 RC_EDGE_POLL_SLEEP=0.002

echo "Done. Pick the best segment and run pass_through with the same env, e.g.:"
echo "  RC_OUTPUT_HZ=67 RC_PASS_PROFILE=idle_hold ${PY} -u ${PASS}"
echo "  # or with longer idle latch:"
echo "  RC_IDLE_LATCH_MS=250 RC_OUTPUT_HZ=50 RC_PASS_PROFILE=idle_hold ${PY} -u ${PASS}"

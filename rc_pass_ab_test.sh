#!/bin/bash
# A/B/C comparison for pass_through_test.py — same duration per segment, you rate twitch + feel.
# Prereq: run rc_calibrate.py once so ~/.config/rc_pass_calibration.json exists (recommended).
# Uses Python subprocess timeout (works on GNU/Linux and macOS; no GNU coreutils `timeout` required).
set -euo pipefail
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEG_SEC="${RC_AB_SECS:-30}"
PY="${RC_PYTHON:-python3}"
PASS="${RC_PASS_SCRIPT:-$SCRIPT_DIR/pass_through_test.py}"
if [[ ! -f "$PASS" ]]; then
  PASS="${HOME}/pass_through_test.py"
fi
if [[ ! -f "$PASS" ]]; then
  echo "pass_through_test.py not found. Set RC_PASS_SCRIPT=/path/to/pass_through_test.py"
  exit 1
fi

echo "══════════════════════════════════════════════════════════════════════"
echo " RC pass-through A/B/C  (${SEG_SEC}s each segment)"
echo " After each segment, note: twitch 1-5 (1=none), steering feel (sluggish?)"
echo " Car + RX + TX on, wheels safe. Ctrl+C aborts."
echo "══════════════════════════════════════════════════════════════════════"
echo

run_seg() {
  local name="$1"
  shift
  echo ""
  echo ">>> SEGMENT: $name  (${SEG_SEC}s) — move steering + throttle like normal driving."
  echo ">>> Then write down twitch (1-5) and whether steering felt slow."
  sleep 2
  # Caller passes VAR=value ... for the pass-through child only.
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

# A: baseline — no idle latch, responsive smoothing
run_seg "A_baseline" \
  RC_PASS_PROFILE=baseline RC_IDLE_HOLD=0 \
  RC_STEER_MEDIAN_LEN=0 RC_STEER_QUANT_US=0 RC_STEER_MAX_STEP_US=0

# B: idle_hold — calibration + latch (default profile when cal file exists)
run_seg "B_idle_hold" \
  RC_PASS_PROFILE=idle_hold RC_IDLE_HOLD=1

# C: hold_only — latch, no median/quant extras
run_seg "C_hold_only" \
  RC_PASS_PROFILE=hold_only RC_IDLE_HOLD=1

echo "Done. Pick the profile that felt best and run pass_through with:"
echo "  RC_PASS_PROFILE=baseline|idle_hold|hold_only ${PY} -u ${PASS}"

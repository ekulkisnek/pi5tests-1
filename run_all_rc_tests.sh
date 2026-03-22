#!/bin/bash
# RC full suite: pytest smoke + optional interactive Pi runner.
# Run on the Pi from the repo:  ./run_all_rc_tests.sh
# Pi venv (so pytest sees system gpiod/lgpio):  python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements-dev.txt
# Env: RC_SUITE_ONLY_PYTEST=1  → pytest only (no interactive suite)
#      RC_SUITE_ONLY_INTERACTIVE=1  → skip pytest, run rc_interactive_suite.py only
set -euo pipefail
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PY=python3
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PY="$SCRIPT_DIR/.venv/bin/python"
fi

echo "═══════════════════════════════════════════════════════════════════"
echo " RC full test suite  (repo: $SCRIPT_DIR)"
echo "═══════════════════════════════════════════════════════════════════"
echo

ONLY_PT="${RC_SUITE_ONLY_PYTEST:-0}"
ONLY_INT="${RC_SUITE_ONLY_INTERACTIVE:-0}"

run_pytest() {
  if "$PY" -c "import pytest" 2>/dev/null; then
    "$PY" -m pytest "$SCRIPT_DIR/tests" -q
    echo "[pytest] OK  ($PY)"
    return 0
  fi
  echo "[pytest] SKIP — pip install -r requirements-dev.txt (use a venv on macOS)"
  return 0
}

if [[ "$ONLY_INT" == "1" ]]; then
  echo "[interactive] RC_SUITE_ONLY_INTERACTIVE=1"
  exec "$PY" -u "$SCRIPT_DIR/rc_interactive_suite.py"
fi

run_pytest
echo

if [[ "$ONLY_PT" == "1" ]]; then
  echo "RC_SUITE_ONLY_PYTEST=1 — skipping interactive suite."
  echo " Full walkthrough:  python3 -u $SCRIPT_DIR/rc_walkthrough.py  (see WALKTHROUGH.md)"
  echo "═══════════════════════════════════════════════════════════════════"
  exit 0
fi

echo "───────────────────────────────────────────────────────────────────"
echo " Interactive hardware suite (triple Enter prompts, 10s motion windows)"
echo " Requires TTY — use:  ssh -t pi5-1@192.168.1.193 'cd ~/pi5tests-1 && ./run_all_rc_tests.sh'"
echo " Or pytest-only:     RC_SUITE_ONLY_PYTEST=1 ./run_all_rc_tests.sh"
echo "───────────────────────────────────────────────────────────────────"
echo

if [[ ! -t 0 ]]; then
  echo "Stdin is not a TTY; skipping rc_interactive_suite.py (non-interactive)."
  echo "Run on the Pi in a terminal, or:  ssh -t pi5-1@192.168.1.193 'cd ~/pi5tests-1 && python3 -u rc_interactive_suite.py'"
  echo "═══════════════════════════════════════════════════════════════════"
  exit 0
fi

"$PY" -u "$SCRIPT_DIR/rc_interactive_suite.py"
echo "═══════════════════════════════════════════════════════════════════"
echo " Full ordered walkthrough (pytest → cal → jitter → interactive):"
echo "   python3 -u $SCRIPT_DIR/rc_walkthrough.py"
echo "   See WALKTHROUGH.md"
echo "═══════════════════════════════════════════════════════════════════"

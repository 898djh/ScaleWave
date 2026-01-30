#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Pretty logging helpers
# -----------------------------
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
CYAN="\033[36m"

log()    { echo -e "${BLUE}[INFO]${RESET} $*"; }
ok()     { echo -e "${GREEN}[OK]${RESET}   $*"; }
warn()   { echo -e "${YELLOW}[WARN]${RESET} $*"; }
step()   { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }
die()    { echo -e "${RED}[ERROR]${RESET} $*" 1>&2; exit 1; }

banner() {
  echo -e "${BOLD}${CYAN}"
  echo "============================================================"
  echo "  Evaluation Node Setup"
  echo "============================================================"
  echo -e "${RESET}"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

run() {
  log "${DIM}$*${RESET}"
  "$@"
}

banner

# -----------------------------
# Config
# -----------------------------
VENV_DIR="$HOME/sw_eval_env"
REQ_FILE="$HOME/ScaleWave/evaluations/scripts/requirements.txt"
TARGET_NOFILE="65535"

# -----------------------------
# Pre-flight checks
# -----------------------------
step "Pre-flight checks"
need_cmd sudo
need_cmd bash
need_cmd uname

if [[ ! -f "$REQ_FILE" ]]; then
  die "Requirements file not found: $REQ_FILE
Make sure the ScaleWave repo exists at: $HOME/ScaleWave"
fi

ok "Pre-flight checks passed."
log "Requirements: $REQ_FILE"
log "Venv dir:      $VENV_DIR"

# -----------------------------
# System dependencies
# -----------------------------
step "Installing system dependencies (apt + python venv)"
need_cmd apt
need_cmd apt-get

run cd "$HOME"
run sudo apt -y update
run sudo apt-get -y update

# Install python3-pip and python3-venv (Python minor version package name can vary)
run sudo apt install -y python3-pip python3-venv git curl wget unzip

ok "System dependencies installed."

# -----------------------------
# Virtual environment setup
# -----------------------------
step "Setting up Python virtual environment"

need_cmd python3
need_cmd pip3

if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating venv at: $VENV_DIR"
  run python3 -m venv "$VENV_DIR"
else
  log "Venv already exists at: $VENV_DIR (reusing)"
fi

# shellcheck disable=SC1090
run source "$VENV_DIR/bin/activate"

# Ensure pip is up-to-date inside venv (helps avoid build/install issues)
run python -m pip install --upgrade pip wheel setuptools

step "Installing Python requirements"
run pip install -r "$REQ_FILE"
ok "Python environment ready (venv active + requirements installed)."

# -----------------------------
# Increase file descriptor limit
# -----------------------------
step "Increasing open file descriptor limit (ulimit -n)"
CURRENT_NOFILE="$(ulimit -n || true)"
log "Current ulimit -n: ${CURRENT_NOFILE:-unknown}"

# Try to set it; if it fails, warn instead of crashing
if ulimit -n "$TARGET_NOFILE" 2>/dev/null; then
  ok "Updated ulimit -n to $TARGET_NOFILE (current shell session)."
else
  warn "Could not set ulimit -n to $TARGET_NOFILE (may require root limits config).
Continuing anyway."
fi

log "New ulimit -n: $(ulimit -n || echo unknown)"

# Copying and unzipping trace files
step "Copying and unzipping trace files"
cp "$HOME/ScaleWave/evaluations/dataset/trace.zip" "$HOME/ScaleWave/evaluations/scripts/simulation/trace.zip"
cd "$HOME/ScaleWave/evaluations/scripts/simulation/"
unzip "$HOME/ScaleWave/evaluations/scripts/simulation/trace.zip"
rm "$HOME/ScaleWave/evaluations/scripts/simulation/trace.zip"

# -----------------------------
# Final summary
# -----------------------------
echo -e "\n${BOLD}${GREEN}============================================================${RESET}"
echo -e "${BOLD}${GREEN}✅ Evaluation node setup complete${RESET}"
echo -e "Run evaluations using: $HOME/ScaleWave/sw_eval_env/bin/python $HOME/ScaleWave/evaluations/scripts/simulation/send_requests.py --manager_node_ip <MANAGER_NODE_IP> --route <ROUTE_URL> --c <CONCURRENCY>"
echo -e "${BOLD}${GREEN}============================================================${RESET}"

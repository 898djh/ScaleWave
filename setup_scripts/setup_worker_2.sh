#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# Pretty logging helpers
# ----------------------------
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; NC=''
fi

log()  { echo -e "${BLUE}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR ]${NC} $*" >&2; }

usage() {
  cat <<EOF
Usage: $0 <manager_ip> <interface> <token>

Example:
  $0 192.168.1.10 eth0 K10f2b...::server:...
EOF
}

# ----------------------------
# Args
# ----------------------------
MANAGER_IP="${1:-}"
WORKER_INTERFACE="${2:-}"
K3S_TOKEN_VALUE="${3:-}"

if [[ -z "$MANAGER_IP" || -z "$WORKER_INTERFACE" || -z "$K3S_TOKEN_VALUE" ]]; then
  err "Missing required arguments."
  usage
  exit 1
fi

# Export so other scripts/child processes can reuse in this session
export MANAGER_IP
export WORKER_INTERFACE
export K3S_TOKEN_VALUE

# Safety: basic check for kubectl/k3s reachable later
log "Starting worker node setup (join K3s cluster)"
log "Manager IP     : ${BOLD}${MANAGER_IP}${NC}"
log "Worker iface   : ${BOLD}${WORKER_INTERFACE}${NC}"
log "Token provided : ${BOLD}(received)${NC}"

# ----------------------------
# Original commands (kept intact, only templated values)
# ----------------------------
log "Updating apt package lists (1/2)..."
sudo apt -y update

log "Updating apt package lists (2/2)..."
sudo apt-get -y update
sudo apt install wget

log "Installing & joining K3s worker to https://${MANAGER_IP}:6443 using iface '${WORKER_INTERFACE}'..."
curl -sfL https://get.k3s.io | K3S_TOKEN="${K3S_TOKEN_VALUE}" K3S_URL="https://${MANAGER_IP}:6443" INSTALL_K3S_EXEC="--flannel-iface=${WORKER_INTERFACE}" sh -

log "Verifying k3s-agent service status (best-effort)..."
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl --no-pager --full status k3s-agent || true
else
  warn "systemctl not found; skipping service status check."
fi

echo "Successfully joined cluster"

# ----------------------------
# Final highlighted summary
# ----------------------------
NODE_NAME="$(hostname 2>/dev/null || true)"

printf "\n${BOLD}${GREEN}============================================================${NC}\n"
printf "${BOLD}${GREEN}  WORKER JOIN COMPLETE${NC}\n"
printf "${BOLD}${GREEN}============================================================${NC}\n"
printf "${BOLD}Manager IP:${NC}      ${YELLOW}%s${NC}\n" "${MANAGER_IP}"
printf "${BOLD}Interface:${NC}       ${YELLOW}%s${NC}\n" "${WORKER_INTERFACE}"
if [[ -n "${NODE_NAME}" ]]; then
  printf "${BOLD}Worker Node:${NC}     ${YELLOW}%s${NC}\n" "${NODE_NAME}"
fi
printf "${BOLD}Token:${NC}           ${YELLOW}%s${NC}\n" "${K3S_TOKEN_VALUE}"
printf "${BOLD}${GREEN}============================================================${NC}\n\n"

log "Tip: On the manager, run: kubectl get nodes -o wide"

#!/usr/bin/env bash
# ScaleWave run script (starts Prometheus port-forward + observer in background)
# - Robust logging
# - PID files + log files
# - No destroy/cleanup logic (we will add a separate stop script later)

set -Eeuo pipefail

TS() { date '+%Y-%m-%d %H:%M:%S %Z'; }
log()  { echo "[$(TS)] [INFO] $*"; }
warn() { echo "[$(TS)] [WARN] $*" >&2; }
err()  { echo "[$(TS)] [ERROR] $*" >&2; }
die()  { err "$*"; exit 1; }

# -----------------------------
# Defaults (override via env or flags)
# -----------------------------
STATE_DIR="${STATE_DIR:-$HOME/.local/state/scalewave}"
ENV_FILE="${ENV_FILE:-$HOME/.scalewave_env.sh}"

PYTHON_BIN="${PYTHON_BIN:-}"
WORKING_DIR="${WORKING_DIR:-$HOME/ScaleWave/implementation/components}"
MANAGER_NODE_IP="${MANAGER_NODE_IP:-}"

PF_NAMESPACE="${PF_NAMESPACE:-observability}"
PF_SERVICE="${PF_SERVICE:-prometheus-operated}"
PF_LOCAL_PORT="${PF_LOCAL_PORT:-9090}"
PF_REMOTE_PORT="${PF_REMOTE_PORT:-9090}"

# -----------------------------
# Usage
# -----------------------------
usage() {
  cat <<USAGE
Usage:
  $(basename "$0") --master-node-ip <ip> --c <concurrency_value> [options]

Required:
  --manager-node-ip <ip>     Manager node IP to pass to observer.py
  --c <concurrency_value>    Concurrency value

Optional:
  --working-dir <path>      Directory containing observer.py (default: $WORKING_DIR)
  --python <path>           Python interpreter path (default: auto-detect python3/python or $HOME/swenv/bin/python if it exists)
  --env-file <path>         Shell env file to source (default: $ENV_FILE)

  --pf-namespace <ns>       Port-forward namespace (default: $PF_NAMESPACE)
  --pf-service <name>       Port-forward service name (default: $PF_SERVICE)
  --pf-local <port>         Local port (default: $PF_LOCAL_PORT)
  --pf-remote <port>        Remote port (default: $PF_REMOTE_PORT)

  -h, --help                Show help

Environment overrides:
  MANAGER_NODE_IP, WORKING_DIR, PYTHON_BIN, ENV_FILE, STATE_DIR,
  PF_NAMESPACE, PF_SERVICE, PF_LOCAL_PORT, PF_REMOTE_PORT

Outputs:
  Logs and PID files are written under:
    $STATE_DIR

Notes:
  - This script only STARTS processes.
  - We'll create a separate destroy/stop script later.
USAGE
}

# -----------------------------
# Arg parsing
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manager-node-ip) MANAGER_NODE_IP="${2:-}"; shift 2;;
    --c) CONCURRENCY="${2:-}"; shift 2;;
    --working-dir) WORKING_DIR="${2:-}"; shift 2;;
    --python) PYTHON_BIN="${2:-}"; shift 2;;
    --env-file) ENV_FILE="${2:-}"; shift 2;;
    --pf-namespace) PF_NAMESPACE="${2:-}"; shift 2;;
    --pf-service) PF_SERVICE="${2:-}"; shift 2;;
    --pf-local) PF_LOCAL_PORT="${2:-}"; shift 2;;
    --pf-remote) PF_REMOTE_PORT="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) die "Unknown option: $1 (run with --help)";;
  esac
done

# tagging/ labeling the manager node
mapfile -t NODES < <(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
# Safety: need at least 2 nodes
if [ "${#NODES[@]}" -lt 2 ]; then
  echo "Not enough nodes to label (found ${#NODES[@]})."
  exit 0
fi
FIRST_NODE="${NODES[0]}"
echo "Skipping first node: $FIRST_NODE"
for node in "${NODES[@]:1}"; do
  echo "Labeling $node as role=worker"
  kubectl label node "$node" node-role.kubernetes.io/worker=true
  kubectl label node "$node" role=worker --overwrite
done

# -----------------------------
# Preflight + logging
# -----------------------------
mkdir -p "$STATE_DIR"
RUN_LOG="$STATE_DIR/run.log"

# Tee all output to the run log (still shows on terminal)
exec > >(tee -a "$RUN_LOG") 2>&1

log "ScaleWave run script starting"
log "State dir: $STATE_DIR"
log "Run log:  $RUN_LOG"

if [[ -f "$ENV_FILE" ]]; then
  log "Sourcing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  warn "Env file not found (skipping): $ENV_FILE"
fi

# MANAGER_NODE_IP might be set by env file; validate now
[[ -n "$MANAGER_NODE_IP" ]] || die "MANAGER_NODE_IP is required. Provide --manager-node-ip <ip> or set MANAGER_NODE_IP env var."

# Validate kubectl
command -v kubectl >/dev/null 2>&1 || die "kubectl not found in PATH"

# Validate WORKING_DIR / observer
if [[ ! -d "$WORKING_DIR" ]]; then
  die "WORKING_DIR does not exist: $WORKING_DIR"
fi
OBSERVER_PY="$HOME/ScaleWave/implementation/components/observer.py"
[[ -f "$OBSERVER_PY" ]] || die "observer.py not found at: $OBSERVER_PY"

# Determine python if not provided
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$HOME/swenv/bin/python" ]]; then
    PYTHON_BIN="$HOME/swenv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    die "No python interpreter found (set --python or PYTHON_BIN)"
  fi
fi

log "Using python: $PYTHON_BIN"
log "Observer: $OBSERVER_PY"
log "Master node IP: $MANAGER_NODE_IP"
log "Port-forward: namespace=$PF_NAMESPACE service=$PF_SERVICE ${PF_LOCAL_PORT}:${PF_REMOTE_PORT}"

# Confirm cluster connectivity (non-fatal)
if kubectl get nodes -A -o wide >/dev/null 2>&1; then
  log "kubectl connectivity: OK"
  log "Cluster nodes:"
  kubectl get nodes -A -o wide || true
else
  warn "kubectl get nodes failed; port-forward may fail if kubeconfig/context isn't set."
fi

# -----------------------------
# Helpers to start background processes
# -----------------------------
is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

start_bg() {
  local name="$1"; shift
  local pidfile="$1"; shift
  local logfile="$1"; shift

  if [[ -f "$pidfile" ]]; then
    local oldpid
    oldpid="$(cat "$pidfile" 2>/dev/null || true)"
    if is_pid_running "$oldpid"; then
      warn "$name already running (pid=$oldpid). Skipping start."
      warn "Log: $logfile"
      return 0
    else
      warn "$name pidfile exists but process not running; overwriting pidfile."
      rm -f "$pidfile"
    fi
  fi

  log "Starting $name in background..."
  log "  Log -> $logfile"
  nohup "$@" >>"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" > "$pidfile"
  disown || true
  log "  Started $name (pid=$pid)"
}

# -----------------------------
# Start Prometheus port-forward
# -----------------------------
PF_LOG="$STATE_DIR/prometheus-portforward.log"
PF_PID="$STATE_DIR/prometheus-portforward.pid"

start_bg "prometheus port-forward" "$PF_PID" "$PF_LOG" \
  kubectl port-forward -n "$PF_NAMESPACE" "svc/$PF_SERVICE" "${PF_LOCAL_PORT}:${PF_REMOTE_PORT}"

cleanup() {
  # Best-effort: stop port-forward when you exit (prevents orphaned background process).
  if [[ -f "$PF_PID" ]]; then
    local ppid
    ppid="$(cat "$PF_PID" 2>/dev/null || true)"
    if [[ -n "$ppid" ]] && kill -0 "$ppid" >/dev/null 2>&1; then
      warn "Stopping prometheus port-forward (pid=$ppid)"
      kill "$ppid" >/dev/null 2>&1 || true
    fi
  fi
  warn "Exiting."
}
trap cleanup INT TERM

# -----------------------------
# Run observer in FOREGROUND (Ctrl+C stops it and exits this script)
# -----------------------------
OBS_LOG="$STATE_DIR/observer.log"
log "Starting ScaleWave in foreground (Ctrl+C to stop)..."
log "  Log -> $OBS_LOG"
log "  Command: $PYTHON_BIN $OBSERVER_PY --manager_node_ip $MANAGER_NODE_IP --c $CONCURRENCY"

"$PYTHON_BIN" "$OBSERVER_PY" --manager_node_ip "$MANAGER_NODE_IP" --c "$CONCURRENCY" \
  2>&1 | tee -a "$OBS_LOG"

# If observer exits normally, cleanup too.
log "All requested processes have been started (or were already running)."
log "PID files:"
log "  $PF_PID"
log "  $OBS_PID"
log "Log files:"
log "  $PF_LOG"
log "  $OBS_LOG"
log "Run log:"
log "  $RUN_LOG"
log "Done."

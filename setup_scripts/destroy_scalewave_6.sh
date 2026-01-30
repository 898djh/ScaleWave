#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# ScaleWave destroy script
# - Stops Prometheus port-forward (kubectl)
# - Stops observer.py and its optimizer.py child process
# - Optionally flushes Redis (off by default)

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/scalewave"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/destroy.log"

log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $*" | tee -a "$LOG_FILE" >/dev/null
}

die() {
  log "ERROR: $*"
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --flush-redis            Run: redis-cli flushall (DANGEROUS)
  --redis-host HOST        Redis host (default: 127.0.0.1)
  --redis-port PORT        Redis port (default: 6379)
  --state-dir DIR          Where PID/log files live (default: $LOG_DIR)
  --help                   Show this help

This script attempts to stop processes using PID files if present; if not,
it falls back to safe pattern matching for the specific commands.

Logs: $LOG_FILE
USAGE
}

FLUSH_REDIS=0
REDIS_HOST="127.0.0.1"
REDIS_PORT="6379"
STATE_DIR="$LOG_DIR"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --flush-redis)
      FLUSH_REDIS=1; shift ;;
    --redis-host)
      REDIS_HOST="${2:-}"; [[ -n "$REDIS_HOST" ]] || die "--redis-host requires a value"; shift 2 ;;
    --redis-port)
      REDIS_PORT="${2:-}"; [[ -n "$REDIS_PORT" ]] || die "--redis-port requires a value"; shift 2 ;;
    --state-dir)
      STATE_DIR="${2:-}"; [[ -n "$STATE_DIR" ]] || die "--state-dir requires a value"; shift 2 ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      die "Unknown option: $1 (use --help)" ;;
  esac
done

mkdir -p "$STATE_DIR"

is_running_pid() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

# Send TERM, wait, then KILL if needed.
kill_pid_gracefully() {
  local pid="$1"
  local label="$2"
  local timeout_s="${3:-10}"

  if ! is_running_pid "$pid"; then
    log "$label: pid $pid is not running"
    return 0
  fi

  log "$label: sending SIGTERM to pid $pid"
  kill -TERM "$pid" >/dev/null 2>&1 || true

  local waited=0
  while is_running_pid "$pid" && [[ $waited -lt $timeout_s ]]; do
    sleep 1
    waited=$((waited + 1))
  done

  if is_running_pid "$pid"; then
    log "$label: still running after ${timeout_s}s; sending SIGKILL to pid $pid"
    kill -KILL "$pid" >/dev/null 2>&1 || true
  else
    log "$label: stopped (pid $pid)"
  fi
}

kill_children_of() {
  local ppid="$1"
  local label="$2"

  # If pkill exists, this is the cleanest way to target child procs.
  if have_cmd pkill; then
    log "$label: sending SIGTERM to children of pid $ppid"
    pkill -TERM -P "$ppid" >/dev/null 2>&1 || true
    sleep 1
    log "$label: sending SIGKILL to remaining children of pid $ppid (if any)"
    pkill -KILL -P "$ppid" >/dev/null 2>&1 || true
  else
    # Fallback: try to find direct children via ps
    local kids
    kids=$(ps -o pid= --ppid "$ppid" 2>/dev/null | awk '{print $1}' | tr '\n' ' ' || true)
    if [[ -n "$kids" ]]; then
      log "$label: found children of pid $ppid: $kids"
      for k in $kids; do
        kill_pid_gracefully "$k" "$label child" 5
      done
    else
      log "$label: no children found for pid $ppid"
    fi
  fi
}

kill_from_pidfile() {
  local pidfile="$1"
  local label="$2"

  if [[ ! -f "$pidfile" ]]; then
    return 1
  fi

  local pid
  pid="$(tr -d ' \t\n\r' < "$pidfile" || true)"
  if [[ -z "$pid" ]]; then
    log "$label: pidfile $pidfile is empty; removing"
    rm -f "$pidfile" || true
    return 0
  fi

  if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    log "$label: pidfile $pidfile contains non-numeric pid '$pid'; removing"
    rm -f "$pidfile" || true
    return 0
  fi

  log "$label: using pidfile $pidfile (pid=$pid)"
  kill_children_of "$pid" "$label"
  kill_pid_gracefully "$pid" "$label" 10

  # Cleanup pidfile after attempting
  rm -f "$pidfile" || true
  return 0
}

kill_by_pattern() {
  local pattern="$1"
  local label="$2"

  if ! have_cmd pgrep; then
    log "$label: pgrep not found; cannot pattern-kill '$pattern'"
    return 0
  fi

  local pids
  pids=$(pgrep -f "$pattern" || true)
  if [[ -z "$pids" ]]; then
    log "$label: no processes match pattern: $pattern"
    return 0
  fi

  log "$label: matched pids: $(echo "$pids" | tr '\n' ' ')"
  # TERM first
  for pid in $pids; do
    kill_pid_gracefully "$pid" "$label" 5
  done
}

echo "=== ScaleWave destroy started ==="
echo "state_dir=$STATE_DIR"

# 1) Stop prometheus port-forward
echo "Stopping Prometheus port-forward..."
# Prefer pidfiles if your run script wrote them; support both common locations
kill_from_pidfile "$STATE_DIR/prometheus-portforward.pid" "prometheus-portforward" || true
kill_from_pidfile "/tmp/prometheus-portforward.pid" "prometheus-portforward" || true

# Fallback pattern (very specific command)
kill_by_pattern "kubectl port-forward -n observability svc/prometheus-operated 9090:9090" "prometheus-portforward" || true

# 2) Stop observer (and thus optimizer child)
echo "Stopping observer (and optimizer child)..."
kill_from_pidfile "$STATE_DIR/observer.pid" "observer" || true
kill_from_pidfile "/tmp/observer.pid" "observer" || true

# Fallback patterns (still fairly specific)
kill_by_pattern "python(3)? .*observer\.py" "observer" || true

# 3) Cleanup any leftover optimizer if it survived (rare, but possible)
# This is intentionally specific to optimizer.py; if you run other optimizer.py scripts elsewhere,
# consider tightening the pattern or relying on PID files.
kill_by_pattern "python(3)? .*optimizer\.py" "optimizer" || true

# 4) Optional redis flush
if [[ "$FLUSH_REDIS" -eq 1 ]]; then
  if have_cmd redis-cli; then
    echo "Flushing Redis via redis-cli flushall (host=$REDIS_HOST port=$REDIS_PORT)..."
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" flushall | tee -a "$LOG_FILE" >/dev/null || true
    echo "Redis flushall completed (check output above)"
  else
    log "redis-cli not found; skipping Redis flush"
  fi
else
  log "Redis flush skipped (use --flush-redis to enable)"
fi

echo "=== ScaleWave destroy finished ==="

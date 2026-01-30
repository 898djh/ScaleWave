#!/usr/bin/env bash
set -euo pipefail

# -------------------------
# Logging helpers
# -------------------------
ts() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo -e "[${1}] $(ts) ${2}"; }
info() { log "INFO" "$1"; }
warn() { log "WARN" "$1" >&2; }
err() { log "ERROR" "$1" >&2; }

on_err() { err "Script failed at line $1 while running: ${BASH_COMMAND}"; err "Hint: re-run with: bash -x $0 <cloud_ip>"; }
trap 'on_err $LINENO' ERR

# -------------------------
# Inputs
# -------------------------
CLOUD_IP="${1:-}"
if [[ -z "$CLOUD_IP" ]]; then
  err "Usage: $0 <cloud_ip>"
  exit 1
fi
CONCURRENCY="${2:-}"
if [[ -z "$CONCURRENCY" ]]; then
  err "Usage: $0 <cloud_ip>"
  exit 1
fi

# -------------------------
# Pre-flight checks
# -------------------------
info "Starting app deployment. Using CLOUD_IP=${CLOUD_IP} CONCURRENCY=${CONCURRENCY}"
for bin in kubectl kn sed; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    err "Missing required command: $bin"
    exit 1
  fi
done

for f in "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/cloud_based_eqv.yaml" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/edge_cpu_based_eqv.yaml" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/hybrid_based_eqv.yaml"; do
  if [[ ! -f "$f" ]]; then
    err "Required file not found in current directory: $f"
    err "Run this script from the directory that contains the YAMLs, or cd there first."
    exit 1
  fi
done

SERVICE_NAME="face-recognition-oblique"
info "Deleting if existing...."
if kn service describe "$SERVICE_NAME" >/dev/null 2>&1; then
  info "Found Knative service '$SERVICE_NAME'. Deleting..."
  kn service delete "$SERVICE_NAME"
  info "Waiting 5s for deletion to propagate..."
  sleep 10
else
  info "Knative service '$SERVICE_NAME' not found. Skipping delete."
fi

info "kubectl context: $(kubectl config current-context 2>/dev/null || echo "<unknown>")"
info "Cluster nodes (if accessible):"
kubectl get nodes -o wide || warn "Could not list nodes (cluster may still be coming up or credentials missing). Continuing..."

# -------------------------
# Apply manifests (commands preserved)
# -------------------------
info "Applying standalone cloud-based face recognition equivalent (cloud_based_eqv.yaml)..."
sed -e "s/{CLOUD_IP}/${CLOUD_IP}/g" -e "s/{CONCURRENCY_VALUE}/${CONCURRENCY}/g" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/cloud_based_eqv.yaml" | kubectl apply -f -
info "Sleeping 30s to allow resources to start..."
sleep 30

info "Applying standalone edge CPU-based face recognition equivalent (edge_cpu_based_eqv.yaml)..."
sed "s/{CONCURRENCY_VALUE}/${CONCURRENCY}/g" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/edge_cpu_based_eqv.yaml" | kubectl apply -f -
# kubectl apply -f "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/edge_cpu_based_eqv.yaml" 
info "Sleeping 50s to allow resources to start..."
sleep 50

info "Applying hybrid-based face recognition equivalent (hybrid_based_eqv.yaml)..."
sed -e "s/{CLOUD_IP}/${CLOUD_IP}/g" -e "s/{CONCURRENCY_VALUE}/${CONCURRENCY}/g" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/hybrid_based_eqv.yaml" | kubectl apply -f -
info "Sleeping 40s to allow resources to start..."
sleep 40

info "GPU variant is currently disabled in this script (commented out). If you enable it, ensure GPU node/runtime is ready."
# Only enable if GPU used
# sed "s/{CONCURRENCY_VALUE}/${CONCURRENCY}/g" "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/edge_gpu_based_eqv.yaml" | kubectl apply -f -
# kubectl apply -f "$HOME/ScaleWave/config/apps_config/face-recognition/equivalent/edge_gpu_based_eqv.yaml"
# sleep 40 

# -------------------------
# Post checks (commands preserved + extra helpful status)
# -------------------------
info "Checking Knative Services and Revisions..."
kn service list
kn revision list

info "Extra status: routes/endpoints (best-effort)..."
kubectl get ksvc,revision,route,configuration -A 2>/dev/null || true

# Best-effort: pick a URL to highlight (prefer ksvc.status.url)
HIGHLIGHT_URL="$(
  kubectl get ksvc -A -o jsonpath='{range .items[*]}{.status.url}{"\n"}{end}' 2>/dev/null \
  | awk 'NF{print; exit}'
)"

# Fallback: if no ksvc URL found, try route.status.url
if [ -z "$HIGHLIGHT_URL" ]; then
  HIGHLIGHT_URL="$(
    kubectl get route -A -o jsonpath='{range .items[*]}{.status.url}{"\n"}{end}' 2>/dev/null \
    | awk 'NF{print; exit}'
  )"
fi

info "Deployment complete."
echo ""
echo "============================================================"
echo "✅  APPLICATION SERVICES DEPLOYED"

if [ -n "$HIGHLIGHT_URL" ]; then
  echo "   ROUTE URL:  '$HIGHLIGHT_URL'"
else
  echo "   ROUTE URL:  (not found yet — try again in ~10-30s)"
fi

echo ""
echo "============================================================"

#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Helpers: logging + safety
# -----------------------------
TS() { date +"%Y-%m-%d %H:%M:%S"; }
log() { printf "[%s] %s\n" "$(TS)" "$*"; }
section() {
  echo
  echo "============================================================"
  log "$*"
  echo "============================================================"
}
warn() { printf "[%s] [WARN] %s\n" "$(TS)" "$*" >&2; }
die()  { printf "[%s] [ERROR] %s\n" "$(TS)" "$*" >&2; exit 1; }

cleanup() {
  # Add any cleanup steps if you want (currently none).
  true
}
trap cleanup EXIT

# -----------------------------
# Args / env
# -----------------------------
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <cloud_ip> <interface>"
  echo "Example: $0 192.168.1.50 eth0"
  exit 1
fi

CLOUD_IP="$1"
IFACE="$2"
export CLOUD_IP IFACE

# -----------------------------
# Pre-flight checks
# -----------------------------
section "Pre-flight checks"

command -v curl >/dev/null 2>&1 || die "curl is required but not found."
command -v sudo >/dev/null 2>&1 || die "sudo is required but not found."

# Ensure required local files exist (these are referenced later)
[[ -f "$HOME/ScaleWave/setup_scripts/cloud_setup/standalone_cloud.yaml" ]] || die "Missing file: standalone_cloud.yaml (expected in current directory: $HOME/ScaleWave/setup_scripts/cloud_setup/)"
[[ -f "$HOME/ScaleWave/setup_scripts/cloud_setup/hybrid_cloud.yaml" ]] || die "Missing file: hybrid_cloud.yaml (expected in current directory: $HOME/ScaleWave/setup_scripts/cloud_setup/)"
[[ -f "$HOME/ScaleWave/setup_scripts/cloud_setup/two_people.jpg" ]] || die "Missing file: two_people.jpg (expected in current directory: $HOME/ScaleWave/setup_scripts/cloud_setup/)"

log "CLOUD_IP = ${CLOUD_IP}"
log "IFACE    = ${IFACE}"
log "Working directory: $HOME/ScaleWave/setup_scripts/cloud_setup/"

# Define kubectl shim for robustness:
# - If kubectl exists, use it.
# - Otherwise, if k3s exists, fallback to 'sudo k3s kubectl'.
# This lets your existing 'kubectl ...' lines work unchanged.
_kubectl_impl() {
  if command -v kubectl >/dev/null 2>&1; then
    command kubectl "$@"
  elif command -v k3s >/dev/null 2>&1; then
    sudo k3s kubectl "$@"
  else
    die "kubectl not found (and k3s not installed yet)."
  fi
}
kubectl() { _kubectl_impl "$@"; }

# -----------------------------
# install dependencies
# -----------------------------
section "Installing dependencies"
log "Updating apt package index (apt -y update)"
sudo apt -y update

log "Updating apt package index (apt-get -y update)"
sudo apt-get -y update

log "Installing iproute2 (needed for tc/netem)."
# Keeping your original command unchanged:
sudo apt install git curl iproute2

# -----------------------------
# add delay to emulate cloud traversal latency
# -----------------------------
section "Configuring network delay with tc/netem"

# Make it idempotent: if qdisc already exists, delete it first.
# (This does not change your original command; it adds a safe pre-step.)
if sudo tc qdisc show dev "$IFACE" 2>/dev/null | grep -q "netem"; then
  warn "Existing netem qdisc found on $IFACE; deleting it first to avoid 'File exists' errors."
  sudo tc qdisc del dev "$IFACE" root || true
fi

log "Adding netem delay on interface $IFACE: 200ms +/- 20ms"
# Keeping your original command unchanged:
sudo tc qdisc add dev "$IFACE" root netem delay 200ms 20ms

# -----------------------------
# k3s and knative
# -----------------------------
section "Installing k3s and Knative (Serving + Kourier)"

log "Installing k3s (this may take a few minutes)"
# Keeping your original command unchanged:
curl -sfL https://get.k3s.io  | INSTALL_K3S_EXEC="--disable=traefik --write-kubeconfig-mode 644 --bind-address=$CLOUD_IP --node-external-ip=$CLOUD_IP --flannel-iface=$IFACE" sh -

# Ensure kubectl can talk to the cluster before applying Knative manifests
# (We add this early export; your later exports remain unchanged.)
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

log "Waiting for Kubernetes API to become reachable..."
for i in {1..60}; do
  if kubectl version --request-timeout=5s >/dev/null 2>&1; then
    log "Kubernetes API is reachable."
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    die "Kubernetes API did not become reachable in time."
  fi
done

log "Applying Knative Serving CRDs"
# Keeping your original command unchanged:
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.20.1/serving-crds.yaml

log "Applying Knative Serving core"
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.20.1/serving-core.yaml

log "Applying Kourier networking layer"
kubectl apply -f https://github.com/knative-extensions/net-kourier/releases/download/knative-v1.20.0/kourier.yaml

log "Setting Knative ingress class to Kourier"
kubectl patch configmap/config-network   --namespace knative-serving   --type merge   --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'

log "Applying Knative default domain configuration"
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.20.1/serving-default-domain.yaml

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
mkdir -p ~/.kube
sudo k3s kubectl config view --raw | tee ~/.kube/config
chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config

# -----------------------------
# apply the standalone and hybrid cloud face recognition apps
# -----------------------------
section "Deploying face recognition apps (standalone + hybrid)"
sleep 15

log "Applying standalone_cloud.yaml"
kubectl apply -f "$HOME/ScaleWave/setup_scripts/cloud_setup/standalone_cloud.yaml"
sleep 40

log "Applying hybrid_cloud.yaml"
kubectl apply -f "$HOME/ScaleWave/setup_scripts/cloud_setup/hybrid_cloud.yaml"
sleep 40

# -----------------------------
# confirm everything works
# -----------------------------
section "Cluster status & Knative routes"

log "Listing pods across all namespaces"
kubectl get pods -A

log "Listing Knative routes"
kubectl get routes

# -----------------------------
# curl request to confirm
# -----------------------------
section "Sending test request to the standalone cloud service (curl)"

CURL_CMD='curl -X POST "http://face-recognition-standalone-cloud.default.'"${CLOUD_IP}"'.sslip.io/recognize"   -H "Host: face-recognition-standalone-cloud.default.'"${CLOUD_IP}"'.sslip.io"   -F "image=@$HOME/ScaleWave/setup_scripts/cloud_setup/two_people.jpg"'
log "Executing:"
echo "$CURL_CMD"
sleep 15

# Keeping your original command unchanged:
curl -X POST "http://face-recognition-standalone-cloud.default.${CLOUD_IP}.sslip.io/recognize"   -H "Host: face-recognition-standalone-cloud.default.${CLOUD_IP}.sslip.io"   -F "image=@$HOME/ScaleWave/setup_scripts/cloud_setup/two_people.jpg"

# -----------------------------
# Final highlighted summary
# -----------------------------
echo
echo "######################################################################"
echo "#  IMPORTANT"
echo "######################################################################"
echo "#  CLOUD_IP   : ${CLOUD_IP}"
echo "#  IFACE      : ${IFACE}"
echo "#"
echo "#  Knative Route(s):"
kubectl get routes || true
echo "######################################################################"
echo

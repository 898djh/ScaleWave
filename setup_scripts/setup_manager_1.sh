#!/usr/bin/env bash
set -euo pipefail

MANAGER_IP="${1:-}"
IFACE="${2:-}"

# Export early so any child processes (and later scripts invoked from this script)
# can access these values.
export MANAGER_IP
export IFACE

if [[ -z "$MANAGER_IP" || -z "$IFACE" ]]; then
  echo "Usage: $0 <manager_node_ip> <interface>"
  echo "Example: $0 192.168.1.10 eth0"
  exit 1
fi

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
  echo "  ScaleWave / K3s + Knative Manager Node Setup"
  echo "============================================================"
  echo -e "${RESET}"
}

banner
log "Manager IP: ${MANAGER_IP}"
log "Flannel interface: ${IFACE}"
warn "This script requires sudo privileges and will install packages, K3s, and Knative."

# system dependencies
step "Installing system dependencies (apt + python venv + redis)"
cd
sudo apt -y update
sudo apt-get -y update
sudo apt install -y python3-pip python3.12-venv redis-server git curl wget
python -m venv swenv
source swenv/bin/activate
ok "System dependencies installed and virtual environment activated."

# k3s and knative
step "Installing K3s (manager) and applying Knative Serving + Kourier manifests"
log "Installing K3s with bind-address/node-external-ip set to ${MANAGER_IP} and flannel-iface set to ${IFACE}"
curl -sfL https://get.k3s.io  | INSTALL_K3S_EXEC="--disable=traefik --write-kubeconfig-mode 644 --bind-address=${MANAGER_IP} --node-external-ip=${MANAGER_IP} --flannel-iface=${IFACE}" sh -
ok "K3s installed."

log "Applying Knative Serving CRDs"
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.2/serving-crds.yaml
log "Applying Knative Serving core"
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.2/serving-core.yaml
log "Applying Kourier networking layer"
kubectl apply -f https://github.com/knative/net-kourier/releases/download/knative-v1.18.0/kourier.yaml
log "Setting Knative ingress-class to Kourier"
kubectl patch configmap/config-network   --namespace knative-serving   --type merge   --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
log "Applying Knative default domain config"
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.18.2/serving-default-domain.yaml
log "Setting config-domain example.com entry"
kubectl patch configmap/config-domain --namespace knative-serving --type merge --patch '{"data":{"example.com":""}}'

step "Configuring kubeconfig for kubectl/kn"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
mkdir -p ~/.kube
sudo k3s kubectl config view --raw | tee ~/.kube/config
chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
ok "Kubeconfig written to ~/.kube/config"

# Ensure kubeconfig is also available to child processes.
export KUBECONFIG

step "Installing Knative CLI (kn)"
wget https://github.com/knative/client/releases/download/knative-v1.20.0/kn-linux-amd64
mv kn-linux-amd64 kn
chmod +x kn
sudo mv kn /usr/local/bin
ok "kn installed to /usr/local/bin/kn"

# tagging/ labeling the manager node
step "Labeling this node as manager/master"
log "Detecting node name from the cluster"
NODE_NAME="$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')"
if [[ -z "$NODE_NAME" ]]; then
  echo "No nodes found."
  exit 1
fi
log "Detected node: ${NODE_NAME}"
export NODE_NAME
kubectl label nodes "$NODE_NAME" node-role.kubernetes.io/manager=true
kubectl label nodes "$NODE_NAME" node-role.kubernetes.io/master=true
kubectl label nodes "$NODE_NAME" role=manager
ok "Node labels applied."

# update default knative configs
step "Updating Knative defaults (enable podspec nodeselector + pin control-plane components)"
kubectl patch configmap config-features -n knative-serving   --type merge   -p '{"data":{"kubernetes.podspec-nodeselector":"enabled"}}'
kubectl patch deployment activator -n knative-serving   --type strategic   -p '{"spec":{"template":{"spec":{"nodeSelector":{"role":"manager"}}}}}'
kubectl patch deployment autoscaler -n knative-serving   --type strategic   -p '{"spec":{"template":{"spec":{"nodeSelector":{"role":"manager"}}}}}'
kubectl patch deployment controller -n knative-serving   --type strategic   -p '{"spec":{"template":{"spec":{"nodeSelector":{"role":"manager"}}}}}'
kubectl patch deployment webhook -n knative-serving   --type strategic   -p '{"spec":{"template":{"spec":{"nodeSelector":{"role":"manager"}}}}}'
kubectl patch deployment net-kourier-controller -n knative-serving  --type strategic  -p '{"spec":{"template":{"spec":{"nodeSelector":{"role":"manager"}}}}}'
ok "Knative configuration patches applied."

# clone the repo and update Knative default config
step "Cloning ScaleWave repository"
log "Cloning repo into: $(pwd)"
REPO_PARENT_DIR="$(pwd)"
export REPO_PARENT_DIR
#git clone https://github.com/898djh/ScaleWave.git
source swenv/bin/activate
WORKING_DIR="$(cd "${REPO_PARENT_DIR}/ScaleWave" && pwd)"
export WORKING_DIR
pip install -r "$WORKING_DIR/implementation/requirements.txt"
ok "ScaleWave working directory: ${WORKING_DIR}"

# Persist key environment variables for future shells/scripts.
# - /etc/profile.d/... makes them available system-wide on login shells
# - ~/.scalewave_env.sh is a user-scoped fallback
step "Persisting environment variables for future scripts"
ENV_FILE_USER="$HOME/.scalewave_env.sh"
ENV_FILE_SYSTEM="/etc/profile.d/scalewave_env.sh"

log "Writing user env file: ${ENV_FILE_USER}"
cat > "${ENV_FILE_USER}" <<EOF
# Generated by ScaleWave manager setup on $(date)
export MANAGER_IP="${MANAGER_IP}"
export IFACE="${IFACE}"
export NODE_NAME="${NODE_NAME}"
export REPO_PARENT_DIR="${REPO_PARENT_DIR}"
export WORKING_DIR="${WORKING_DIR}"
export KUBECONFIG="${KUBECONFIG}"
EOF
chmod 600 "${ENV_FILE_USER}"

log "Attempting to write system-wide env file: ${ENV_FILE_SYSTEM} (requires sudo)"
sudo bash -lc "cat > '${ENV_FILE_SYSTEM}' <<'EOF'
# Generated by ScaleWave manager setup on $(date)
export MANAGER_IP='${MANAGER_IP}'
export IFACE='${IFACE}'
export NODE_NAME='${NODE_NAME}'
export REPO_PARENT_DIR='${REPO_PARENT_DIR}'
export WORKING_DIR='${WORKING_DIR}'
export KUBECONFIG='${KUBECONFIG}'
EOF
chmod 644 '${ENV_FILE_SYSTEM}'" || warn "Could not write ${ENV_FILE_SYSTEM}. You can still use: source ${ENV_FILE_USER}"

log "Loading variables into current shell session (for this script run)"
set +u
source "${ENV_FILE_USER}"
set -u
ok "Environment variables persisted. New shells will load them automatically if ${ENV_FILE_SYSTEM} exists; otherwise run: source ${ENV_FILE_USER}"

# prometheus and observer
step "Installing Helm and setting up Prometheus stack (observability namespace)"
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
chmod 700 get_helm.sh && ./get_helm.sh
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
# ensure clean observability namespace (delete if it already exists)
step "Checking for existing observability namespace"
if kubectl get namespace observability >/dev/null 2>&1; then
  warn "Namespace 'observability' already exists. Deleting it to ensure a clean install..."
  kubectl delete namespace observability
  # Wait until the namespace is fully deleted (avoid "AlreadyExists" on create)
  for i in $(seq 1 120); do
    if ! kubectl get namespace observability >/dev/null 2>&1; then
      ok "Namespace 'observability' deleted."
      break
    fi
    sleep 2
  done
  if kubectl get namespace observability >/dev/null 2>&1; then
    warn "Namespace 'observability' is still terminating after waiting. Proceeding to next step; creation may fail until deletion completes."
  fi
else
  ok "Namespace 'observability' does not exist. Continuing..."
fi

kubectl create namespace observability
ok "Helm installed and observability namespace created."

# prometheus monitoring updates
step "Installing kube-prometheus-stack via Helm (this can take a few minutes)"
helm install prometheus prometheus-community/kube-prometheus-stack -n observability --values "${WORKING_DIR}/config/observer_config/prometheus_stack/prometheus_stack.values"
ok "Prometheus stack installed."

# display necessary info
step "Final checks and cluster info"
kn version
kubectl get nodes -A -o wide

step "K3s node token (use this to join agent/worker nodes)"
sudo cat /var/lib/rancher/k3s/server/node-token

# Highlight token again (without changing the original command above)
TOKEN="$(sudo cat /var/lib/rancher/k3s/server/node-token || true)"
if [[ -n "${TOKEN}" ]]; then
  echo -e "\n${BOLD}${YELLOW}==================== IMPORTANT ====================${RESET}"
  echo -e "${BOLD}${GREEN}K3S NODE TOKEN:${RESET} ${BOLD}${YELLOW}${TOKEN}${RESET}"
  echo -e "${DIM}Save this token securely. Workers/agents will need it to join the cluster.${RESET}"
  echo -e "${BOLD}${YELLOW}===================================================${RESET}\n"
else
  warn "Could not read node-token for highlighting. The command output above should still show it."
fi

ok "Manager node setup complete."

# expose prometheus
#kubectl port-forward -n observability svc/prometheus-operated 9090:9090

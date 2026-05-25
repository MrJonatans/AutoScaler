#!/bin/bash

# AutoScaler Deployment Script
# Hybrid mode: deploys app + prometheus + adapter via Helm,
# predictor runs locally on the host and is scraped by Prometheus.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
DEPLOY_METHOD="${DEPLOY_METHOD:-helm}"          # helm or kubectl
IMAGE_TAG="${IMAGE_TAG:-latest}"
NAMESPACE="${NAMESPACE:-autoscaling-ns}"
RELEASE_NAME="${RELEASE_NAME:-autoscaler}"
HELM_CHART_PATH="${HELM_CHART_PATH:-$PROJECT_ROOT/helm/autoscaler}"

# Hybrid mode defaults
CLUSTER_IP="${CLUSTER_IP:-192.168.31.41}"
SSH_USER="${SSH_USER:-pepe}"
PREDICTOR_PORT="${PREDICTOR_PORT:-8001}"
PREDICTOR_CONTAINER_NAME="${PREDICTOR_CONTAINER_NAME:-autoscaler-predictor}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"   # docker or containerd (k3s with --docker uses docker)
BUILD_PREDICTOR="${BUILD_PREDICTOR:-false}"        # set to true only if you want to deploy predictor inside the cluster

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -m, --method METHOD       Deployment method: helm or kubectl (default: helm)"
    echo "  -t, --tag TAG             Docker image tag (default: latest)"
    echo "  -n, --namespace NS        Kubernetes namespace (default: autoscaling-ns)"
    echo "  -r, --release NAME        Helm release name (default: autoscaler)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Environment variables (hybrid mode):"
    echo "  CLUSTER_IP                Target k3s node IP (default: 192.168.31.41)"
    echo "  SSH_USER                  SSH user for image transfer (default: pepe)"
    echo "  IMAGE_TAG                 Same as --tag"
    echo "  NAMESPACE                 Same as --namespace"
    echo "  RELEASE_NAME              Same as --release"
    echo "  CONTAINER_RUNTIME         docker or containerd (default: docker - because your k3s uses Docker)"
    echo "  BUILD_PREDICTOR           true/false - transfer predictor image to cluster (build always happens for local use) (default: false)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Full hybrid deployment (recommended)"
    echo "  CLUSTER_IP=192.168.31.50 $0           # Deploy to different node"
    echo "  $0 -m kubectl                         # Legacy kubectl deployment"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--method)
            DEPLOY_METHOD="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate deploy method
if [[ "$DEPLOY_METHOD" != "helm" && "$DEPLOY_METHOD" != "kubectl" ]]; then
    echo "Error: Invalid deploy method '$DEPLOY_METHOD'. Use 'helm' or 'kubectl'."
    exit 1
fi

echo "=========================================="
echo "AutoScaler Hybrid Deployment"
echo "=========================================="
echo "Method:       $DEPLOY_METHOD"
echo "Image tag:    $IMAGE_TAG"
echo "Namespace:    $NAMESPACE"
if [[ "$DEPLOY_METHOD" == "helm" ]]; then
    echo "Release:      $RELEASE_NAME"
    echo "Chart:        $HELM_CHART_PATH"
    echo "Cluster IP:   $CLUSTER_IP"
    echo "SSH user:     $SSH_USER"
    echo "Container runtime: $CONTAINER_RUNTIME"
    echo "Transfer predictor to cluster: $BUILD_PREDICTOR"
fi
echo "=========================================="
echo ""

# ==========================================
# Auto-detect kubeconfig (for hybrid/Helm mode)
# ==========================================
if [[ "$DEPLOY_METHOD" == "helm" ]]; then
    if [[ -z "${KUBECONFIG:-}" ]]; then
        if [[ -f "$PROJECT_ROOT/kubeconfigs/config_dev_k3s" ]]; then
            export KUBECONFIG="$PROJECT_ROOT/kubeconfigs/config_dev_k3s"
            echo ">>> Using project kubeconfig: $KUBECONFIG"
        else
            echo ">>> KUBECONFIG not set and no local config found — using default kubectl context"
        fi
    else
        echo ">>> Using KUBECONFIG from environment: $KUBECONFIG"
    fi

    # Verify connectivity
    echo ">>> Checking connection to Kubernetes cluster..."
    if ! kubectl cluster-info &>/dev/null; then
        echo ""
        echo "ERROR: kubectl cannot connect to any Kubernetes cluster."
        echo "Please ensure:"
        echo "  - The cluster is running (192.168.31.41 or your CLUSTER_IP)"
        echo "  - You have a valid kubeconfig (or the file kubeconfigs/config_dev_k3s exists)"
        echo "  - You can run: kubectl get nodes"
        echo ""
        exit 1
    fi
    echo ">>> Connected to cluster successfully."
    echo ""
fi

# ==========================================
# Prepare training data (real or synthetic)
# ==========================================
echo ">>> Checking for training data..."
MODEL_FILE="$PROJECT_ROOT/model.pth"
DATA_FILE="$PROJECT_ROOT/data.csv"

if [[ ! -f "$MODEL_FILE" ]]; then
    echo "Model file 'model.pth' not found. Preparing data and training..."

    if [[ ! -f "$DATA_FILE" ]]; then
        # Try real Azure dataset first
        if command -v datacentertracesdatasets-cli &> /dev/null; then
            echo "Real Azure dataset CLI available — downloading..."
            if [[ ! -f azure_trace.csv ]]; then
                cd "$PROJECT_ROOT" && datacentertracesdatasets-cli -trace azure_v2 -file azure_trace.csv
            fi
            echo "Extracting 1 week (Mon-Sun) of CPU data..."
            cd "$PROJECT_ROOT" && python scripts/prepare_azure_data.py
        else
            echo "No real dataset CLI found. Generating synthetic training data..."
            cd "$PROJECT_ROOT" && python scripts/generate_data.py
        fi
    fi

    # Train the model
    echo "Training ML model (this may take a few minutes)..."
    cd "$PROJECT_ROOT" && python -m src.ml.train

    if [[ -f "$MODEL_FILE" ]]; then
        echo "Model trained and saved to model.pth"
    else
        echo "ERROR: Model training failed!"
        exit 1
    fi
else
    echo "Model file found: model.pth"
fi

# ==========================================
# Build images
# ==========================================
echo ">>> Building images..."

echo "Building autoscaler-app:${IMAGE_TAG}..."
docker build -t "autoscaler-app:${IMAGE_TAG}" "$PROJECT_ROOT"

# Always build predictor image (needed for local docker run in hybrid mode)
echo "Building autoscaler-predictor:${IMAGE_TAG}... (for local use on host)"
docker build -f "$PROJECT_ROOT/Dockerfile.predictor" \
    -t "autoscaler-predictor:${IMAGE_TAG}" "$PROJECT_ROOT"

echo "Images built successfully."
echo ""

# ==========================================
# HELM DEPLOYMENT (Hybrid)
# ==========================================
if [[ "$DEPLOY_METHOD" == "helm" ]]; then

    echo ">>> Deploying with Helm (hybrid mode)..."

    # Check prerequisites
    if ! command -v helm &> /dev/null; then
        echo "Error: Helm is not installed."
        exit 1
    fi

    if ! command -v kubectl &> /dev/null; then
        echo "Error: kubectl is not installed."
        exit 1
    fi

    if [[ ! -d "$HELM_CHART_PATH" ]]; then
        echo "Error: Helm chart not found at $HELM_CHART_PATH"
        exit 1
    fi

    # Transfer images to the remote k3s node
    echo ""
    echo ">>> Transferring images to cluster ($CLUSTER_IP)..."
    echo "You may be prompted for the SSH password for user '$SSH_USER'."

    if [[ "$CONTAINER_RUNTIME" == "docker" ]]; then
        echo "Transferring autoscaler-app:${IMAGE_TAG} (via docker load)..."
        docker save "autoscaler-app:${IMAGE_TAG}" | \
            ssh "${SSH_USER}@${CLUSTER_IP}" "docker load"

        if [[ "$BUILD_PREDICTOR" == "true" ]]; then
            echo "Transferring autoscaler-predictor:${IMAGE_TAG} (via docker load)..."
            docker save "autoscaler-predictor:${IMAGE_TAG}" | \
                ssh "${SSH_USER}@${CLUSTER_IP}" "docker load"
        else
            echo "Skipping predictor image transfer (BUILD_PREDICTOR=false)"
        fi
    else
        echo "Transferring autoscaler-app:${IMAGE_TAG} (via k3s ctr)..."
        docker save "autoscaler-app:${IMAGE_TAG}" | \
            ssh "${SSH_USER}@${CLUSTER_IP}" "sudo k3s ctr images import -"

        if [[ "$BUILD_PREDICTOR" == "true" ]]; then
            echo "Transferring autoscaler-predictor:${IMAGE_TAG} (via k3s ctr)..."
            docker save "autoscaler-predictor:${IMAGE_TAG}" | \
                ssh "${SSH_USER}@${CLUSTER_IP}" "sudo k3s ctr images import -"
        else
            echo "Skipping predictor image transfer (BUILD_PREDICTOR=false)"
        fi
    fi

    echo "Images transferred successfully."
    echo ""

    # Deploy with Helm (predictor disabled - runs locally)
    echo ">>> Deleting deployment to avoid HPA conflict..."
    kubectl delete deployment --namespace "$NAMESPACE" "$RELEASE_NAME-app" --ignore-not-found=true --wait=true

    echo ">>> Installing/upgrading Helm release..."
    helm upgrade --install "$RELEASE_NAME" "$HELM_CHART_PATH" \
        --namespace "$NAMESPACE" \
        --create-namespace \
        --set global.namespace="$NAMESPACE" \
        --set app.image.repository="autoscaler-app" \
        --set app.image.tag="$IMAGE_TAG" \
        --set predictor.enabled=false \
        --wait \
        --timeout 10m
    echo ""
    echo "Helm deployment complete."

    # ==========================================
    # Start predictor locally
    # ==========================================
    echo ""
    echo ">>> Starting predictor locally on host..."

    # Stop old container if exists
    docker rm -f "$PREDICTOR_CONTAINER_NAME" 2>/dev/null || true

    docker run -d \
        --name "$PREDICTOR_CONTAINER_NAME" \
        -p "${PREDICTOR_PORT}:8001" \
        --restart unless-stopped \
        "autoscaler-predictor:${IMAGE_TAG}"

    echo "Predictor started locally:"
    echo "  Container: $PREDICTOR_CONTAINER_NAME"
    echo "  Port:      $PREDICTOR_PORT"
    echo "  Image:     autoscaler-predictor:${IMAGE_TAG}"
    echo ""

    # Final instructions
    echo "=========================================="
    echo "Hybrid deployment finished successfully!"
    echo "=========================================="

    echo ""
    echo "Next steps:"
    echo "  1. Check pods in cluster:"
    echo "     kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  2. Check that predictor is running locally:"
    echo "     docker ps | grep $PREDICTOR_CONTAINER_NAME"
    echo "     curl http://localhost:$PREDICTOR_PORT/health  # if health endpoint exists"
    echo ""
    echo "  3. Verify Prometheus is scraping the external predictor:"
    echo "     kubectl port-forward -n $NAMESPACE svc/prometheus 9090:9090"
    echo "     # then open http://localhost:9090/targets"
    echo ""
    echo "  4. Watch HPA:"
    echo "     kubectl get hpa -n $NAMESPACE -w"
    echo ""
    echo "To stop the local predictor:"
    echo "  docker stop $PREDICTOR_CONTAINER_NAME"
    echo ""
    echo "To uninstall everything:"
    echo "  helm uninstall $RELEASE_NAME -n $NAMESPACE"
    echo "  docker rm -f $PREDICTOR_CONTAINER_NAME"

# ==========================================
# LEGACY KUBECTL DEPLOYMENT
# ==========================================
else
    echo ">>> Deploying with kubectl (legacy mode)..."

    # Note: legacy mode still uses the old deployment/ folder
    # which may contain an in-cluster predictor. Hybrid mode is recommended.
    echo "WARNING: Legacy mode deploys everything from deployment/ folder."
    echo "         For the new hybrid architecture use the default Helm method."

    kubectl apply -f "$PROJECT_ROOT/deployment/"

    echo ""
    echo "Legacy deployment complete."
    echo "Check status with: kubectl get pods -n $NAMESPACE"
fi

echo ""
echo "Deployment script finished."
#!/usr/bin/env bash
set -euo pipefail

echo "==> [1/3] Starting local Docker registry on port 5001..."
if ! docker ps --format '{{.Names}}' | grep -q '^kind-registry$'; then
  docker run -d -p 5001:5000 --restart=always --name kind-registry registry:2
  echo "    Registry started."
else
  echo "    Registry already running."
fi

echo "==> [2/3] Creating kind cluster (chaos-demo)..."
cat <<EOF | kind create cluster --name chaos-demo --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
      [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5001"]
        endpoint = ["http://kind-registry:5001"]
EOF

echo "==> [3/3] Connecting registry to kind network..."
docker network connect kind kind-registry 2>/dev/null || echo "    Already connected."

kubectl cluster-info --context kind-chaos-demo
echo ""
echo "Cluster ready. Run: bash setup/02-install-openfaas.sh"

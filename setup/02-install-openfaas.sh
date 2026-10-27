#!/usr/bin/env bash
set -euo pipefail

echo "==> [1/4] Creating namespaces..."
kubectl create namespace openfaas      --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace openfaas-fn   --dry-run=client -o yaml | kubectl apply -f -

echo "==> [2/4] Adding OpenFaaS Helm chart..."
helm repo add openfaas https://openfaas.github.io/faas-netes/ --force-update
helm repo update

echo "==> [3/4] Installing OpenFaaS..."
helm upgrade --install openfaas openfaas/openfaas \
  --namespace openfaas \
  --set functionNamespace=openfaas-fn \
  --set generateBasicAuth=true \
  --set serviceType=NodePort \
  --set gateway.nodePort=31112 \
  --wait --timeout=5m

echo "==> [4/4] Logging in faas-cli..."
kubectl rollout status -n openfaas deploy/gateway --timeout=3m

PASSWORD=$(kubectl get secret -n openfaas basic-auth \
  -o jsonpath="{.data.basic-auth-password}" | base64 --decode)

echo "    OpenFaaS admin password: $PASSWORD"

# Port-forward gateway in background
pkill -f "kubectl port-forward.*gateway" 2>/dev/null || true
kubectl port-forward -n openfaas svc/gateway 8080:8080 &
sleep 3

faas-cli login \
  --username admin \
  --password "$PASSWORD" \
  --gateway http://127.0.0.1:8080

echo ""
echo "OpenFaaS ready at http://127.0.0.1:8080"
echo "UI: http://127.0.0.1:8080/ui/"
echo ""
echo "Run: bash setup/03-deploy-functions.sh"

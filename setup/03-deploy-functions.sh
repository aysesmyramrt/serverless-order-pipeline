#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> [1/4] Pulling python3-http template..."
faas-cli template store pull python3-http

echo "==> [2/4] Building function images..."
faas-cli build -f stack.yml

echo "==> [3/4] Pushing images to local registry..."
faas-cli push -f stack.yml

echo "==> [4/4] Deploying to OpenFaaS..."
PASSWORD=$(kubectl get secret -n openfaas basic-auth \
  -o jsonpath="{.data.basic-auth-password}" | base64 --decode)

faas-cli deploy -f stack.yml \
  --gateway http://127.0.0.1:8080 \
  --username admin \
  --password "$PASSWORD"

echo ""
echo "Waiting for functions to become ready..."
sleep 10

faas-cli list --gateway http://127.0.0.1:8080

echo ""
echo "All functions deployed. Run chaos experiments:"
echo "  python3 chaos/runner.py"

#!/usr/bin/env bash
# ============================================================
#  SUNUM DEMO — Chaos Engineering Framework
#  Çalıştırmak için: bash sunum.sh
# ============================================================

GATEWAY="http://127.0.0.1:8080"
USER="admin"
PASS="${OPENFAAS_PASSWORD:?OPENFAAS_PASSWORD ortam degiskenini ayarla}"
PROJECT="$(cd "$(dirname "$0")" && pwd)"

divider() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }
pause()   { echo; read -rp "  ▶  Devam için ENTER'a bas..." _; echo; }

clear
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   Chaos Engineering Framework for Serverless Apps   ║"
echo "  ║   Project 17 · Cloud Computing Module 2025-2026     ║"
echo "  ╚══════════════════════════════════════════════════════╝"
pause

# ── ADIM 1: Kubernetes pod'larını göster ─────────────────────
divider
echo "  [1/5]  Kubernetes üzerinde çalışan fonksiyonlar"
divider
kubectl get pods -n openfaas-fn
pause

# ── ADIM 2: Normal pipeline testi ────────────────────────────
divider
echo "  [2/5]  Normal sipariş isteği gönderiliyor..."
echo "         order-ingestion → payment-processing → inventory-management → shipping-dispatch"
divider
curl -s -X POST "$GATEWAY/function/order-ingestion" \
  -H "Content-Type: application/json" \
  -u "$USER:$PASS" \
  -d '{
    "order_id":   "ORD-SUNUM-01",
    "customer_id":"CUST-42",
    "items": [{"sku":"LAPTOP","qty":1,"price":999.99}]
  }' | python3 -m json.tool
pause

# ── ADIM 3: Latency injection ─────────────────────────────────
divider
echo "  [3/5]  FAULT 1 — Latency Injection"
echo "         payment-processing'e 2 saniyelik yapay gecikme ekleniyor..."
divider
kubectl set env deployment/payment-processing \
  CHAOS_LATENCY_MS=2000 -n openfaas-fn --quiet
kubectl rollout status deployment/payment-processing -n openfaas-fn --timeout=60s
echo
echo "  İstek gönderiliyor — yanıt ~2 saniye gecikmeli gelecek:"
time curl -s -X POST "$GATEWAY/function/order-ingestion" \
  -H "Content-Type: application/json" \
  -u "$USER:$PASS" \
  -d '{
    "order_id":   "ORD-SUNUM-02",
    "customer_id":"CUST-42",
    "items": [{"sku":"LAPTOP","qty":1,"price":999.99}]
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print('  status:', d.get('status','ERROR'))"
echo
echo "  ✦ Baseline: ~33ms  →  Latency injection sonrası: ~2042ms"
pause

# ── Latency sıfırla ───────────────────────────────────────────
kubectl set env deployment/payment-processing \
  CHAOS_LATENCY_MS=0 -n openfaas-fn --quiet
kubectl rollout status deployment/payment-processing -n openfaas-fn --timeout=60s --quiet 2>/dev/null

# ── ADIM 4: Error Rate injection ─────────────────────────────
divider
echo "  [4/5]  FAULT 2 — Error Rate Manipulation"
echo "         inventory-management'e %40 HTTP 500 hata oranı enjekte ediliyor..."
divider
kubectl set env deployment/inventory-management \
  CHAOS_ERROR_RATE=0.4 -n openfaas-fn --quiet
kubectl rollout status deployment/inventory-management -n openfaas-fn --timeout=60s
echo
echo "  5 istek gönderiliyor — bazıları hata alacak:"
for i in 1 2 3 4 5; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$GATEWAY/function/order-ingestion" \
    -H "Content-Type: application/json" \
    -u "$USER:$PASS" \
    -d "{\"order_id\":\"ORD-ERR-0$i\",\"customer_id\":\"CUST-42\",\"items\":[{\"sku\":\"ITEM\",\"qty\":1,\"price\":9.99}]}")
  if [ "$STATUS" = "200" ]; then
    echo "    İstek $i → ✅ $STATUS OK"
  else
    echo "    İstek $i → ❌ $STATUS HATA"
  fi
  sleep 0.3
done
echo
echo "  ✦ %40 ayarladık → gerçek deneyde %46.7 hata oranı ölçüldü (30 istek)"
pause

# ── Error rate sıfırla ────────────────────────────────────────
kubectl set env deployment/inventory-management \
  CHAOS_ERROR_RATE=0.0 -n openfaas-fn --quiet
kubectl rollout status deployment/inventory-management -n openfaas-fn --timeout=60s --quiet 2>/dev/null

# ── ADIM 5: Downstream failure ────────────────────────────────
divider
echo "  [5/5]  FAULT 3 — Downstream Service Failure"
echo "         payment-processing tamamen devre dışı bırakılıyor..."
divider
kubectl set env deployment/payment-processing \
  CHAOS_DOWNSTREAM_FAIL=true -n openfaas-fn --quiet
kubectl rollout status deployment/payment-processing -n openfaas-fn --timeout=60s
echo
echo "  İstek gönderiliyor — downstream servis çöktü:"
curl -s -X POST "$GATEWAY/function/order-ingestion" \
  -H "Content-Type: application/json" \
  -u "$USER:$PASS" \
  -d '{
    "order_id":   "ORD-SUNUM-03",
    "customer_id":"CUST-42",
    "items": [{"sku":"LAPTOP","qty":1,"price":999.99}]
  }' | python3 -m json.tool
echo
echo "  ✦ Sonuç: %100 hata — tüm pipeline etkilendi"
pause

# ── Reset ─────────────────────────────────────────────────────
divider
echo "  Tüm fonksiyonlar baseline'a sıfırlanıyor..."
divider
for fn in order-ingestion payment-processing inventory-management shipping-dispatch; do
  kubectl set env deployment/$fn \
    CHAOS_LATENCY_MS=0 CHAOS_ERROR_RATE=0.0 CHAOS_DOWNSTREAM_FAIL=false \
    -n openfaas-fn --quiet
done
echo "  ✅ Sistem normal duruma döndü."
divider
echo
echo "  Sonuçlar için dashboard açılıyor..."
open "$PROJECT/results/dashboard.html"
echo

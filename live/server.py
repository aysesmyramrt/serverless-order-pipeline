#!/usr/bin/env python3
"""
Live Chaos Dashboard - Backend
Sunum sırasında canlı güncellenen arayüz
"""

import base64
import json
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

import requests
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

GATEWAY  = "http://127.0.0.1:8080"
USER     = "admin"
PASS     = os.environ.get("OPENFAAS_PASSWORD", "")  # kubectl get secret -n openfaas basic-auth
INTERVAL = 1.5   # saniyede kaç istek

# ── State ──────────────────────────────────────────────────────
state = {
    "faults": {
        "order-ingestion":     {"latency": 0, "error_rate": 0.0, "downstream": False},
        "payment-processing":  {"latency": 0, "error_rate": 0.0, "downstream": False},
        "inventory-management":{"latency": 0, "error_rate": 0.0, "downstream": False},
        "shipping-dispatch":   {"latency": 0, "error_rate": 0.0, "downstream": False},
    },
    "log":    deque(maxlen=30),
    "stats":  {"total": 0, "success": 0, "errors": 0, "latencies": deque(maxlen=50)},
    "running": True,
}
lock = threading.Lock()
req_counter = 0

# ── Background request loop ────────────────────────────────────
def send_loop():
    global req_counter
    while state["running"]:
        req_counter += 1
        order = {
            "order_id":    f"ORD-LIVE-{req_counter:04d}",
            "customer_id": "CUST-42",
            "items": [{"sku": "ITEM-A", "qty": 1, "price": 29.99}]
        }
        t0 = time.time()
        try:
            resp = requests.post(
                f"{GATEWAY}/function/order-ingestion",
                json=order,
                auth=(USER, PASS),
                timeout=12
            )
            ms  = round((time.time() - t0) * 1000, 1)
            ok  = resp.status_code == 200
            code = resp.status_code
        except Exception as e:
            ms   = round((time.time() - t0) * 1000, 1)
            ok   = False
            code = 0

        entry = {
            "id":   f"ORD-LIVE-{req_counter:04d}",
            "ms":   ms,
            "ok":   ok,
            "code": code,
            "ts":   datetime.now().strftime("%H:%M:%S"),
        }
        with lock:
            state["log"].appendleft(entry)
            state["stats"]["total"]   += 1
            state["stats"]["latencies"].append(ms)
            if ok:
                state["stats"]["success"] += 1
            else:
                state["stats"]["errors"]  += 1

        time.sleep(INTERVAL)

threading.Thread(target=send_loop, daemon=True).start()

# ── Kubectl helpers ────────────────────────────────────────────
def apply_env(fn, latency=0, error_rate=0.0, downstream=False):
    subprocess.run([
        "kubectl", "set", "env",
        f"deployment/{fn}",
        f"CHAOS_LATENCY_MS={latency}",
        f"CHAOS_ERROR_RATE={error_rate}",
        f"CHAOS_DOWNSTREAM_FAIL={'true' if downstream else 'false'}",
        "-n", "openfaas-fn"
    ], capture_output=True)
    subprocess.Popen([
        "kubectl", "rollout", "status",
        f"deployment/{fn}",
        "-n", "openfaas-fn", "--timeout=60s"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ── Routes ────────────────────────────────────────────────────
@app.route("/")
def index():
    return open(__file__.replace("server.py", "index.html")).read()

@app.route("/api/status")
def api_status():
    with lock:
        lats = list(state["stats"]["latencies"])
        s    = state["stats"]
        err_pct = round(s["errors"] / s["total"] * 100, 1) if s["total"] else 0
        p50 = sorted(lats)[len(lats)//2] if lats else 0
        return jsonify({
            "faults": state["faults"],
            "log":    list(state["log"])[:20],
            "stats": {
                "total":   s["total"],
                "success": s["success"],
                "errors":  s["errors"],
                "err_pct": err_pct,
                "p50":     p50,
                "mean":    round(sum(lats)/len(lats), 1) if lats else 0,
            }
        })

@app.route("/api/fault", methods=["POST"])
def inject_fault():
    data = request.json
    fn   = data.get("function")
    kind = data.get("kind")   # latency | error_rate | downstream

    with lock:
        f = state["faults"][fn]
        if kind == "latency":
            f["latency"]     = data.get("value", 2000)
        elif kind == "error_rate":
            f["error_rate"]  = data.get("value", 0.4)
        elif kind == "downstream":
            f["downstream"]  = True
        apply_env(fn, f["latency"], f["error_rate"], f["downstream"])

    return jsonify({"ok": True})

@app.route("/api/reset", methods=["POST"])
def reset_fault():
    fn = request.json.get("function")
    fns = [fn] if fn else list(state["faults"].keys())
    with lock:
        for f in fns:
            state["faults"][f] = {"latency": 0, "error_rate": 0.0, "downstream": False}
            apply_env(f)
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("✅ Live Dashboard → http://127.0.0.1:6060")
    app.run(host="0.0.0.0", port=6060, debug=False)

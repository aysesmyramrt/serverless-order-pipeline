#!/usr/bin/env python3
"""
Chaos Engineering Experiment Runner
Project 17 - Cloud Computing Module 2025-2026
Pipeline: order-ingestion -> payment-processing -> inventory-management -> shipping-dispatch
"""

import base64
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime

import requests

GATEWAY = os.getenv("OPENFAAS_GATEWAY", "http://127.0.0.1:8080")
N = int(os.getenv("CHAOS_N", "30"))          # requests per experiment
DELAY = float(os.getenv("CHAOS_DELAY", "0.3"))  # seconds between requests

SAMPLE_ORDER = {
    "order_id": "ORD-TEMPLATE",
    "customer_id": "CUST-42",
    "items": [
        {"sku": "ITEM-A", "qty": 2, "price": 29.99},
        {"sku": "ITEM-B", "qty": 1, "price": 49.99},
    ],
}

_password: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_password() -> str:
    result = subprocess.run(
        ["kubectl", "get", "secret", "-n", "openfaas", "basic-auth",
         "-o", "jsonpath={.data.basic-auth-password}"],
        capture_output=True, text=True, check=True,
    )
    return base64.b64decode(result.stdout.strip()).decode()


def _set_env(function_name: str, latency_ms: int = 0,
             error_rate: float = 0.0, downstream_fail: bool = False) -> None:
    subprocess.run(
        ["kubectl", "set", "env",
         f"deployment/{function_name}",
         f"CHAOS_LATENCY_MS={latency_ms}",
         f"CHAOS_ERROR_RATE={error_rate}",
         f"CHAOS_DOWNSTREAM_FAIL={'true' if downstream_fail else 'false'}",
         "-n", "openfaas-fn"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["kubectl", "rollout", "status",
         f"deployment/{function_name}",
         "-n", "openfaas-fn",
         "--timeout=90s"],
        check=True, capture_output=True,
    )
    time.sleep(2)


def _reset_all() -> None:
    print("  Resetting all functions to baseline...")
    for fn in ("order-ingestion", "payment-processing",
               "inventory-management", "shipping-dispatch"):
        _set_env(fn)


def _send(seq: int) -> dict:
    order = dict(SAMPLE_ORDER)
    order["order_id"] = f"ORD-{seq:04d}"
    t0 = time.time()
    try:
        resp = requests.post(
            f"{GATEWAY}/function/order-ingestion",
            json=order,
            auth=("admin", _password),
            timeout=15,
        )
        ms = (time.time() - t0) * 1000
        return {"status": resp.status_code, "ms": ms, "ok": resp.status_code == 200}
    except requests.exceptions.Timeout:
        ms = (time.time() - t0) * 1000
        return {"status": 504, "ms": ms, "ok": False}
    except Exception as exc:
        ms = (time.time() - t0) * 1000
        return {"status": -1, "ms": ms, "ok": False, "exc": str(exc)}


def _percentile(data: list, p: float) -> float:
    s = sorted(data)
    idx = max(0, int(len(s) * p / 100) - 1)
    return round(s[idx], 1)


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(name: str, setup_fn) -> dict:
    bar = "=" * 62
    print(f"\n{bar}")
    print(f"  {name}")
    print(bar)

    setup_fn()
    print(f"  Sending {N} requests  (delay={DELAY}s each)...\n")

    results = []
    for i in range(1, N + 1):
        r = _send(i)
        results.append(r)
        tag = "OK " if r["ok"] else f"ERR-{r['status']}"
        print(f"    [{i:2d}/{N}]  {tag:<12}  {r['ms']:8.1f} ms")
        time.sleep(DELAY)

    latencies = [r["ms"] for r in results]
    errors = [r for r in results if not r["ok"]]

    summary = {
        "experiment": name,
        "n": N,
        "errors": len(errors),
        "error_pct": round(len(errors) / N * 100, 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
    }

    print(f"\n  --- Results ---")
    print(f"  Success  : {N - len(errors)}/{N}  ({100 - summary['error_pct']:.1f}%)")
    print(f"  Errors   : {len(errors)}  ({summary['error_pct']}%)")
    print(f"  Mean     : {summary['mean_ms']} ms")
    print(f"  p50      : {summary['p50_ms']} ms")
    print(f"  p95      : {summary['p95_ms']} ms")
    print(f"  p99      : {summary['p99_ms']} ms")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _password
    print("=" * 62)
    print("  Chaos Engineering Framework - Order Processing Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Gateway : {GATEWAY}")
    print(f"  N       : {N} requests per experiment")
    print("=" * 62)

    try:
        _password = _get_password()
    except subprocess.CalledProcessError:
        sys.exit("ERROR: Could not retrieve OpenFaaS password from kubectl.")

    all_results = []

    # ------------------------------------------------------------------
    # Experiment 1 — Baseline
    # ------------------------------------------------------------------
    all_results.append(run_experiment(
        "Baseline (no faults)",
        _reset_all,
    ))

    # ------------------------------------------------------------------
    # Experiment 2 — Latency injection on payment-processing (+2 s)
    # ------------------------------------------------------------------
    all_results.append(run_experiment(
        "Latency Injection: payment-processing +2000 ms",
        lambda: _set_env("payment-processing", latency_ms=2000),
    ))

    # ------------------------------------------------------------------
    # Experiment 3 — Error rate 40 % on inventory-management
    # ------------------------------------------------------------------
    all_results.append(run_experiment(
        "Error Rate: inventory-management 40 % failure",
        lambda: (_reset_all(),
                 _set_env("inventory-management", error_rate=0.4)),
    ))

    # ------------------------------------------------------------------
    # Experiment 4 — Downstream failure: payment-processing unreachable
    # ------------------------------------------------------------------
    all_results.append(run_experiment(
        "Downstream Failure: payment-processing unavailable",
        lambda: (_reset_all(),
                 _set_env("payment-processing", downstream_fail=True)),
    ))

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    print(f"\n{'='*62}")
    _reset_all()

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    print(f"\n{'='*62}")
    print("  EXPERIMENT SUMMARY")
    print(f"{'='*62}")
    hdr = f"  {'Experiment':<46} {'Err%':>5} {'p50':>6} {'p95':>6} {'p99':>6}"
    print(hdr)
    print(f"  {'-'*58}")
    for r in all_results:
        print(
            f"  {r['experiment']:<46} "
            f"{r['error_pct']:>4.1f}% "
            f"{r['p50_ms']:>6} "
            f"{r['p95_ms']:>6} "
            f"{r['p99_ms']:>6}"
        )
    print()

    # ------------------------------------------------------------------
    # Save JSON report
    # ------------------------------------------------------------------
    os.makedirs("results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/experiment_{ts}.json"
    with open(out, "w") as fh:
        json.dump(all_results, fh, indent=2)
    print(f"  Report saved → {out}")


if __name__ == "__main__":
    main()

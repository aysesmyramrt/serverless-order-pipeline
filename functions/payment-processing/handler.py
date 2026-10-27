import os
import time
import random
import json
import requests


def handle(event, context):
    latency_ms = int(os.getenv("CHAOS_LATENCY_MS", "0"))
    error_rate = float(os.getenv("CHAOS_ERROR_RATE", "0.0"))
    downstream_fail = os.getenv("CHAOS_DOWNSTREAM_FAIL", "false").lower() == "true"

    if latency_ms > 0:
        time.sleep(latency_ms / 1000.0)

    if random.random() < error_rate:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "injected fault",
                "stage": "payment-processing"
            })
        }

    try:
        order = json.loads(event.body)
    except Exception:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "invalid payload"})
        }

    total = sum(
        item.get("qty", 1) * item.get("price", 0.0)
        for item in order.get("items", [])
    )
    order["payment"] = {
        "transaction_id": f"TXN-{int(time.time() * 1000)}",
        "amount": round(total, 2),
        "currency": "USD",
        "status": "authorized"
    }
    order["pipeline"].append("payment-processing")

    if downstream_fail:
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "downstream service unavailable",
                "stage": "payment-processing"
            })
        }

    gateway = os.getenv("OPENFAAS_URL", "http://gateway.openfaas.svc.cluster.local:8080")
    try:
        resp = requests.post(
            f"{gateway}/function/inventory-management",
            json=order,
            timeout=12
        )
        return {"statusCode": resp.status_code, "body": resp.text}
    except requests.exceptions.Timeout:
        return {
            "statusCode": 504,
            "body": json.dumps({"error": "timeout calling inventory-management"})
        }
    except Exception as exc:
        return {
            "statusCode": 502,
            "body": json.dumps({"error": str(exc)})
        }

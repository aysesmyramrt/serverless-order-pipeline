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
                "stage": "inventory-management"
            })
        }

    try:
        order = json.loads(event.body)
    except Exception:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "invalid payload"})
        }

    reservations = []
    for item in order.get("items", []):
        reservations.append({
            "sku": item.get("sku"),
            "qty_reserved": item.get("qty", 1),
            "warehouse": "WH-EU-01"
        })

    order["inventory"] = {
        "reservations": reservations,
        "reserved_at": time.time()
    }
    order["pipeline"].append("inventory-management")

    if downstream_fail:
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "downstream service unavailable",
                "stage": "inventory-management"
            })
        }

    gateway = os.getenv("OPENFAAS_URL", "http://gateway.openfaas.svc.cluster.local:8080")
    try:
        resp = requests.post(
            f"{gateway}/function/shipping-dispatch",
            json=order,
            timeout=12
        )
        return {"statusCode": resp.status_code, "body": resp.text}
    except requests.exceptions.Timeout:
        return {
            "statusCode": 504,
            "body": json.dumps({"error": "timeout calling shipping-dispatch"})
        }
    except Exception as exc:
        return {
            "statusCode": 502,
            "body": json.dumps({"error": str(exc)})
        }

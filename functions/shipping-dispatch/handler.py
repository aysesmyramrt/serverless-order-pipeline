import os
import time
import random
import json


def handle(event, context):
    latency_ms = int(os.getenv("CHAOS_LATENCY_MS", "0"))
    error_rate = float(os.getenv("CHAOS_ERROR_RATE", "0.0"))

    if latency_ms > 0:
        time.sleep(latency_ms / 1000.0)

    if random.random() < error_rate:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "injected fault",
                "stage": "shipping-dispatch"
            })
        }

    try:
        order = json.loads(event.body)
    except Exception:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "invalid payload"})
        }

    order["shipping"] = {
        "tracking_id": f"TRACK-{order.get('order_id', 'UNKNOWN')}-{int(time.time())}",
        "carrier": "FastShip",
        "estimated_days": 3,
        "dispatched_at": time.time()
    }
    order["pipeline"].append("shipping-dispatch")
    order["status"] = "completed"

    return {
        "statusCode": 200,
        "body": json.dumps(order)
    }

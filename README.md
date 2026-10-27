# Serverless Order Pipeline: Chaos Engineering on OpenFaaS

A chaos-engineering testbed for a serverless order-processing pipeline. Four Python functions run on OpenFaaS on a local Kubernetes (kind) cluster. Fault injection is controlled through environment variables, an experiment runner measures how the pipeline behaves under each fault, and a small Flask dashboard lets you inject faults live while traffic flows.

Built as a Cloud Computing course project (2025-2026).

## Pipeline

```
client ──► order-ingestion ──► payment-processing ──► inventory-management ──► shipping-dispatch
```

Each function forwards the enriched order to the next one through the OpenFaaS gateway:

| Function | What it does |
| --- | --- |
| `order-ingestion` | Validates the JSON payload (`order_id`, `customer_id` and `items` are required) and starts the `pipeline` trace |
| `payment-processing` | Computes the order total and attaches a mock authorized transaction |
| `inventory-management` | Adds a stock reservation for each item (mock warehouse) |
| `shipping-dispatch` | Attaches a tracking ID and carrier, then marks the order `completed` |

Payment, inventory and shipping are simulated. No real payment provider or database is involved.

## Fault injection

Every function reads three environment variables on each request:

| Variable | Effect |
| --- | --- |
| `CHAOS_LATENCY_MS` | Sleeps for the given number of milliseconds before processing |
| `CHAOS_ERROR_RATE` | Returns HTTP 500 with this probability (0.0 to 1.0) |
| `CHAOS_DOWNSTREAM_FAIL` | When `true`, returns HTTP 503 instead of calling the next function |

Faults are applied with `kubectl set env deployment/<fn> ... -n openfaas-fn`, which triggers a rollout. Calls to the next function have a 12 s timeout. A timeout comes back as 504 and any other call failure as 502.

## Experiments

`chaos/runner.py` runs four experiments in sequence. Each experiment sends `CHAOS_N` requests (30 by default) to `order-ingestion` and records the error rate and the mean, p50, p95 and p99 latency:

1. Baseline, with no faults
2. Latency injection: +2000 ms on `payment-processing`
3. Error rate: 40% on `inventory-management`
4. Downstream failure: `payment-processing` stops forwarding

Results are saved as `results/experiment_<timestamp>.json`. The repository includes three recorded runs. In the 2026-06-14 run, the baseline p50 was about 35 ms and latency injection raised it to about 2128 ms. The 40% fault produced a 43.3% observed error rate over 30 requests, and the downstream failure caused 100% errors. `results/dashboard.html` is a static Chart.js page that presents the experiment results.

## Live dashboard

`live/server.py` is a Flask app on port 6060. It sends a test order every 1.5 s and exposes:

- `GET /api/status`: fault state per function, recent requests, success/error counts, error %, p50 and mean latency
- `POST /api/fault`: inject `latency`, `error_rate` or `downstream` on a function
- `POST /api/reset`: reset one function or all of them

`live/index.html` is the browser UI for these endpoints.

## Tech stack

Python 3, OpenFaaS (`python3-http` template), Kubernetes via kind, Helm, faas-cli, Docker, Flask, requests, Chart.js

## Project structure

```
serverless-order-pipeline/
├── functions/            # the four OpenFaaS function handlers + requirements.txt
├── stack.yml             # OpenFaaS stack definition (images, env vars)
├── setup/
│   ├── 01-create-cluster.sh    # local registry (port 5001) + kind cluster "chaos-demo"
│   ├── 02-install-openfaas.sh  # OpenFaaS via Helm, port-forward gateway to :8080, faas-cli login
│   ├── 03-deploy-functions.sh  # faas-cli build / push / deploy
│   └── manifests.yaml          # plain Kubernetes Deployments/Services (alternative to faas-cli deploy)
├── chaos/runner.py       # automated experiment runner
├── live/                 # Flask live dashboard (server.py + index.html)
├── results/              # experiment JSON outputs + static results dashboard
├── template/             # OpenFaaS Python templates pulled by faas-cli
└── sunum.sh              # step-by-step presentation demo script
```

## Running

Prerequisites: Docker, kind, kubectl, Helm, faas-cli, Python 3 with `requests` (and `flask` for the live dashboard).

```bash
bash setup/01-create-cluster.sh
bash setup/02-install-openfaas.sh
bash setup/03-deploy-functions.sh

# automated experiments
python3 chaos/runner.py            # optional: OPENFAAS_GATEWAY, CHAOS_N, CHAOS_DELAY

# live dashboard
python3 live/server.py             # then open http://127.0.0.1:6060
```

The image names in `stack.yml` point to `ttl.sh`, an anonymous registry whose images expire after 24 hours. Change them to your own registry, or to the local `localhost:5001` registry, before you build and push. The runner reads the gateway password from the `basic-auth` secret with `kubectl`. `live/server.py` and `sunum.sh` take the gateway credentials as constants at the top of the file, so set these for your own cluster.

Example request:

```bash
curl -X POST http://127.0.0.1:8080/function/order-ingestion \
  -u admin:<password> -H "Content-Type: application/json" \
  -d '{"order_id":"ORD-1","customer_id":"CUST-42","items":[{"sku":"LAPTOP","qty":1,"price":999.99}]}'
```

## Author

Ayşe Sümeyra Mert, Computer Engineering student

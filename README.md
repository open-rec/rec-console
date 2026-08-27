# OpenRec Console

[![CI](https://github.com/open-rec/rec-console/actions/workflows/ci.yml/badge.svg)](https://github.com/open-rec/rec-console/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-20-5FA04E?logo=nodedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/frontend-React-61DAFB?logo=react&logoColor=black)

Management and control plane for OpenRec. The first module owns the lifecycle of versioned recall
indexes: staging-index creation, document-count validation, atomic active-alias switching, retention,
version listing, explicit switching, and emergency rollback. Online rec-server instances only read
the active alias. A React and TypeScript control interface is served from `/`; its navigation is
structured for recommendation DAG, monitoring, Airflow automation, and rank-model modules.

> The console can publish serving graphs, recall indexes, workflow configuration, and rank models.
> Authentication is not implemented yet. The example publishes port 8095 for local evaluation;
> restrict it to a trusted network and replace the example `SERVING_GRAPH_TOKEN` in shared
> environments.

The Serving Graph module reads the currently active graph from `rec-server`, renders its node and
edge topology, and edits each node's enable flag, timeout, and typed `content` JSON independently.
Publishing always assembles and submits one complete graph snapshot. The server validates Java node
classes and DAG structure before atomically switching new requests; the console records the accepted
snapshot for explicit rollback.

The DAG module integrates with Airflow 3 through its authenticated public REST API. It lists DAGs,
pauses or enables them, triggers runs, shows DagRun/TaskInstance state and task logs, and never uses
the Docker socket. The daily recall editor publishes validated, versioned JSON consumed by the
read-only Airflow DAG template and supports configuration rollback.

```text
POST /api/recall/releases/prepare
POST /api/recall/releases/activate
POST /api/recall/releases/rollback
POST /api/recall/releases/switch
GET  /api/recall/releases/{algorithm}

GET   /api/airflow/dags
PATCH /api/airflow/dags/{dag_id}
POST  /api/airflow/dags/{dag_id}/runs
GET   /api/airflow/dags/{dag_id}/runs
GET   /api/airflow/dags/{dag_id}/runs/{run_id}/tasks
GET   /api/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs

GET  /api/dag-configs/openrec_daily_recall
POST /api/dag-configs/openrec_daily_recall/publish
POST /api/dag-configs/openrec_daily_recall/rollback

GET  /api/serving-graph
POST /api/serving-graph/publish
POST /api/serving-graph/rollback

GET  /api/models/releases/{scene}
POST /api/models/releases/publish
POST /api/models/releases/rollback

GET  /api/analytics/business?date_from=...&date_to=...&scene=...

GET  /api/entities/users/{user_id}
GET  /api/entities/items/{item_id}
GET  /api/entities/events?user_id=...&scene=...&event_type=...
```

Build and run the complete console on the `openrec-bigdata` network:

```shell
docker compose -f docker-compose.cluster.yml up -d --build --wait
```

For standalone mode, start the reduced console after monitoring and rec-server are running:

```shell
docker compose -f docker-compose.standalone.yml up -d --build --wait
```

`OPENREC_MODE=standalone` keeps monitoring, entity diagnostics, and Serving Graph enabled. Recall
index management, offline DAG, data analysis, Airflow automation, and Rank Model remain visible as
disabled cluster-only modules. The same capability checks protect their backend APIs. Entity
diagnostics retain the shared online Redis query path through rec-server in both modes.

The UI is exposed on `http://<host>:8095/`, API documentation is under `/docs`, and `/health`
checks the dependencies enabled for the selected mode. Cluster checks Elasticsearch, authenticated
Airflow API access, and rec-server; standalone checks rec-server only.
This management port is reachable from the host network; the warning above applies to both modes.

Cluster Compose mounts the Airflow Simple Auth password file read-only, a persistent console
history volume, and the shared `openrec-dag-config` publication volume. Supported daily recall
fields are cron schedule, the ordered six-algorithm recall pipeline, default revision, index retention, retry count,
and retry delay. Airflow remains the execution and run-state source of truth.

`SERVING_GRAPH_TOKEN` must have the same value in rec-console and rec-server. The Compose defaults
are intended only for the example environment; override the value for a shared deployment.

The Rank Model module can submit LR or FM training through `openrec_rank_model`, then lists
evaluated immutable releases and their model type, AUC, sample count, feature dimension, and gate
result. The DAG deploys releases that pass the gate; manual publish asks rank-engine to load the complete artifact before updating
the console's active record; rollback uses the same atomic activation path and retains activation
history under the console data volume.

New releases also expose the model-specific Feature Set, catalog version, fitted input dimension,
and FeatureSpace SHA-256. Publish and rollback validate the sidecar checksum, declared model type,
and dimension before activation. The console and rank-engine consume only the fitted sidecar stored
with that model release; the training-time global catalog is not an online dependency.

The Data Analysis module submits a four-core Spark aggregation over the selected Hive event
partitions and caches identical queries for five minutes. It reports PV/UV CTR, PV/UV CVR, active
items, GMV, their underlying counts, and a daily trend. GMV requires `buy.extFields.quantity` and
`buy.extFields.price`; malformed or missing values contribute zero and are excluded from the
displayed valid-GMV-order count. Date ranges are limited to 366 days.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENREC_MODE` | `cluster` | Enable `cluster` or reduced `standalone` capabilities |
| `REC_SERVER_URL` | `http://rec-server:13579` | Entity diagnostics and Serving Graph API |
| `SERVING_GRAPH_TOKEN` | example value | Shared token for graph-management calls |
| `ES_HOST`, `ES_USER`, `ES_PASSWORD` | example Elasticsearch service | Recall release store |
| `ES_VERIFY_CERTS` | `false` | Verify Elasticsearch TLS certificates |
| `AIRFLOW_URL`, `AIRFLOW_USERNAME` | example Airflow service, `admin` | Airflow public API |
| `AIRFLOW_PASSWORD`, `AIRFLOW_PASSWORD_FILE` | unset | Airflow Simple Auth credential source |
| `RANK_ENGINE_URL` | `http://rank-engine:8123` | Model activation and rollback |
| `REC_CONSOLE_DATA_DIR` | `/var/lib/rec-console` | Graph, model, and activation history |
| `ANALYTICS_CACHE_SECONDS` | `300` | Business-query cache lifetime |
| `GRAFANA_URL` | `http://grafana:3000` | Embedded monitoring endpoint |

Compose files define the remaining artifact and DAG-publication paths. Do not enable certificate
verification until the configured CA is available inside the container.

## Development and test

Run backend tests from the repository root; they use fakes and temporary directories rather than a
live cluster:

```shell
python -m pip install -r requirements.txt pytest
python -m pytest -q test
```

Build or run the React/TypeScript frontend separately:

```shell
cd frontend
npm ci
npm run build
npm run dev
```

The production Dockerfile builds the frontend first and serves its static output from the FastAPI
application. CI tests Python 3.12 and builds the frontend with Node.js 22; the runtime build stage
currently uses Node.js 20.

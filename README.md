# rec-console

Management and control plane for OpenRec. The first module owns the lifecycle of versioned recall
indexes: staging-index creation, document-count validation, atomic active-alias switching, retention,
version listing, explicit switching, and emergency rollback. Online rec-server instances only read
the active alias. A React and TypeScript control interface is served from `/`; its navigation is
structured for recommendation DAG, monitoring, Airflow automation, and rank-model modules.

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

GET  /api/entities/users/{user_id}
GET  /api/entities/items/{item_id}
GET  /api/entities/events?user_id=...&scene=...&event_type=...
```

Build and run the complete console on the `openrec-bigdata` network:

```shell
docker compose -f docker-compose.cluster.yml up -d --build --wait
```

The UI is exposed on `http://<host>:8095/`, API documentation is under `/docs`, and `/health`
checks Elasticsearch, authenticated Airflow API access, and the rec-server Serving Graph endpoint.
This management port is reachable from the host network;
restrict it with the deployment firewall until console authentication is introduced.

Cluster Compose mounts the Airflow Simple Auth password file read-only, a persistent console
history volume, and the shared `openrec-dag-config` publication volume. Supported daily recall
fields are cron schedule, ordered hot/new/i2i jobs, default revision, index retention, retry count,
and retry delay. Airflow remains the execution and run-state source of truth.

`SERVING_GRAPH_TOKEN` must have the same value in rec-console and rec-server. The Compose defaults
are intended only for the example environment; override the value for a shared deployment.

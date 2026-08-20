# rec-console

Management and control plane for OpenRec. The first module owns the lifecycle of versioned recall
indexes: staging-index creation, document-count validation, atomic active-alias switching, retention,
version listing, explicit switching, and emergency rollback. Online rec-server instances only read
the active alias. A React and TypeScript control interface is served from `/`; its navigation is
structured for upcoming recommendation DAG, monitoring, Airflow automation, and rank-model modules.

```text
POST /api/recall/releases/prepare
POST /api/recall/releases/activate
POST /api/recall/releases/rollback
POST /api/recall/releases/switch
GET  /api/recall/releases/{algorithm}
```

Build and run the complete console on the `openrec-bigdata` network:

```shell
docker compose -f docker-compose.cluster.yml up -d --build --wait
```

The UI is exposed on `http://<host>:8095/`, API documentation is under `/docs`, and `/health`
checks the Elasticsearch connection. This management port is reachable from the host network;
restrict it with the deployment firewall until console authentication is introduced.

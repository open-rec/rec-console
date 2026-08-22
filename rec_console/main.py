"""HTTP API for OpenRec operational controls."""

import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rec_console.airflow_client import AirflowClient, AirflowError
from rec_console.analytics import AnalyticsClient, AnalyticsError
from rec_console.config import console_config
from rec_console.dag_configs import DagConfigStore
from rec_console.entity_queries import EntityQueryClient, EntityQueryError
from rec_console.recall_indexes import RecallIndexManager
from rec_console.model_releases import ModelReleaseStore
from rec_console.serving_graphs import RecServerError, ServingGraphStore


def _manager():
    verify = os.environ.get("ES_VERIFY_CERTS", "false").lower() == "true"
    client = Elasticsearch(
        [os.environ.get("ES_HOST", "https://elasticsearch:9200")],
        basic_auth=(os.environ.get("ES_USER", "elastic"),
                    os.environ.get("ES_PASSWORD", "openrec-es-password")),
        verify_certs=verify,
    )
    return RecallIndexManager(client)


app = FastAPI(title="OpenRec Console", version="0.1.0")


FEATURE_PATHS = {
    "/api/recall/": "recall",
    "/api/entities/": "entities",
    "/api/serving-graph": "serving",
    "/api/dag-configs/": "dag",
    "/api/airflow/": "airflow",
    "/api/analytics/": "analytics",
    "/api/models/": "model",
    "/grafana/": "monitor",
}


@app.middleware("http")
async def reject_disabled_features(request: Request, call_next):
    features = console_config()["features"]
    for prefix, feature in FEATURE_PATHS.items():
        if request.url.path.startswith(prefix) and not features[feature]:
            return Response(
                content='{"detail":"feature is only supported in cluster mode"}',
                status_code=404,
                media_type="application/json",
            )
    return await call_next(request)


@app.get("/api/config")
def config():
    return console_config()


class PrepareRequest(BaseModel):
    algorithm: str
    business_date: str
    revision: str = "r001"


class ActivateRequest(BaseModel):
    algorithm: str
    index: str
    expected_documents: int = Field(gt=0)
    max_index_versions: int = Field(default=2, ge=2)


class RollbackRequest(BaseModel):
    algorithm: str
    target_index: str | None = None


class SwitchRequest(BaseModel):
    algorithm: str
    target_index: str


class DagStateRequest(BaseModel):
    is_paused: bool


class DagTriggerRequest(BaseModel):
    conf: dict = Field(default_factory=dict)


class DailyRecallConfigRequest(BaseModel):
    schedule: str
    algorithms: list[str]
    default_revision: str = "r001"
    max_index_versions: int = 2
    retries: int = 1
    retry_delay_minutes: int = 5


class ConfigRollbackRequest(BaseModel):
    version: str | None = None


class ServingGraphPublishRequest(BaseModel):
    graph: dict


class ModelPublishRequest(BaseModel):
    scene: str
    version: str


class ModelRollbackRequest(BaseModel):
    scene: str
    target_version: str | None = None


@app.get("/api/analytics/business")
def business_analytics(date_from: date, date_to: date, scene: str = "", refresh: bool = False):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=400, detail="date range must not exceed 366 days")
    try:
        return AnalyticsClient().query(date_from.isoformat(), date_to.isoformat(),
                                       scene.strip(), refresh)
    except AnalyticsError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _call(method, *args):
    manager = _manager()
    try:
        return getattr(manager, method)(*args)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        manager.client.close()


@app.get("/health")
def health():
    config = console_config()
    manager = _manager() if config["features"]["recall"] else None
    try:
        if manager:
            manager.client.info()
        if config["features"]["airflow"]:
            AirflowClient().dags()
        ServingGraphStore().client.current()
        dependencies = {"rec_server": "ready"}
        if manager:
            dependencies["elasticsearch"] = "ready"
        if config["features"]["airflow"]:
            dependencies["airflow"] = "ready"
        return {"status": "ok", "mode": config["mode"], **dependencies}
    except Exception as error:
        raise HTTPException(status_code=503, detail="Console dependency is unavailable: %s" % error) \
            from error
    finally:
        if manager:
            manager.client.close()


@app.post("/api/recall/releases/prepare")
def prepare(request: PrepareRequest):
    return _call("prepare", request.algorithm, request.business_date, request.revision)


@app.post("/api/recall/releases/activate")
def activate(request: ActivateRequest):
    return _call("activate", request.algorithm, request.index,
                 request.expected_documents, request.max_index_versions)


@app.post("/api/recall/releases/rollback")
def rollback(request: RollbackRequest):
    return _call("rollback", request.algorithm, request.target_index)


@app.post("/api/recall/releases/switch")
def switch_release(request: SwitchRequest):
    return _call("switch", request.algorithm, request.target_index)


@app.get("/api/recall/releases/{algorithm}")
def releases(algorithm: str):
    return _call("list_indexes", algorithm)


@app.get("/api/models/releases/{scene}")
def model_releases(scene: str):
    return ModelReleaseStore().list(scene)


@app.post("/api/models/releases/publish")
def publish_model(request: ModelPublishRequest):
    try:
        return ModelReleaseStore().publish(request.scene, request.version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/models/releases/rollback")
def rollback_model(request: ModelRollbackRequest):
    try:
        return ModelReleaseStore().rollback(request.scene, request.target_version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _entity_query(method, *args):
    try:
        result = getattr(EntityQueryClient(), method)(*args)
    except EntityQueryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="entity was not found")
    return result


@app.get("/api/entities/users/{user_id}")
def query_user(user_id: str):
    return _entity_query("user", user_id)


@app.get("/api/entities/items/{item_id}")
def query_item(item_id: str):
    return _entity_query("item", item_id)


@app.get("/api/entities/events")
def query_events(user_id: str, scene: str, event_type: str):
    return {"user_id": user_id, "scene": scene, "event_type": event_type,
            "events": _entity_query("events", user_id, scene, event_type)}


def _airflow(method, *args):
    try:
        return getattr(AirflowClient(), method)(*args)
    except AirflowError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/airflow/dags")
def airflow_dags():
    return _airflow("dags")


@app.get("/api/airflow/dags/{dag_id}")
def airflow_dag(dag_id: str):
    dag = _airflow("dag", dag_id)
    tasks = _airflow("dag_tasks", dag_id)
    config = DagConfigStore().current() if dag_id == "openrec_daily_recall" else None
    return {"dag": dag, "tasks": tasks.get("tasks", []), "config": config}


@app.patch("/api/airflow/dags/{dag_id}")
def airflow_dag_state(dag_id: str, request: DagStateRequest):
    return _airflow("update_dag", dag_id, request.is_paused)


@app.post("/api/airflow/dags/{dag_id}/runs")
def airflow_trigger(dag_id: str, request: DagTriggerRequest):
    return _airflow("trigger", dag_id, request.conf)


@app.get("/api/airflow/dags/{dag_id}/runs")
def airflow_runs(dag_id: str, limit: int = 20):
    return _airflow("runs", dag_id, min(max(limit, 1), 100))


@app.get("/api/airflow/dags/{dag_id}/runs/{run_id}/tasks")
def airflow_tasks(dag_id: str, run_id: str):
    return _airflow("tasks", dag_id, run_id)


@app.get("/api/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs")
def airflow_task_logs(dag_id: str, run_id: str, task_id: str, try_number: int = 1):
    return _airflow("logs", dag_id, run_id, task_id, max(try_number, 1))


@app.get("/api/dag-configs/openrec_daily_recall")
def daily_recall_config():
    return DagConfigStore().current()


@app.post("/api/dag-configs/openrec_daily_recall/publish")
def publish_daily_recall_config(request: DailyRecallConfigRequest):
    try:
        result = DagConfigStore().publish(request.model_dump())
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        AirflowClient().reparse("openrec_daily_recall")
        result["airflow_reparse"] = "requested"
    except AirflowError as error:
        result["airflow_reparse"] = "pending"
        result["warning"] = str(error)
    return result


@app.post("/api/dag-configs/openrec_daily_recall/rollback")
def rollback_daily_recall_config(request: ConfigRollbackRequest):
    try:
        result = DagConfigStore().rollback(request.version)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        AirflowClient().reparse("openrec_daily_recall")
        result["airflow_reparse"] = "requested"
    except AirflowError as error:
        result["airflow_reparse"] = "pending"
        result["warning"] = str(error)
    return result


@app.get("/api/serving-graph")
def serving_graph():
    try:
        return ServingGraphStore().current()
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/serving-graph/publish")
def publish_serving_graph(request: ServingGraphPublishRequest):
    try:
        return ServingGraphStore().publish(request.graph)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RecServerError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/serving-graph/rollback")
def rollback_serving_graph(request: ConfigRollbackRequest):
    try:
        return ServingGraphStore().rollback(request.version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RecServerError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.api_route("/grafana/{path:path}", methods=["GET", "POST"])
async def grafana_proxy(path: str, request: Request):
    """Expose Grafana through the console origin so remote browsers never use loopback URLs."""
    base = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
    query = ("?" + request.url.query) if request.url.query else ""
    body = await request.body()
    upstream = urllib.request.Request(
        "%s/grafana/%s%s" % (base, path, query),
        data=body or None,
        method=request.method,
        headers={"Accept": request.headers.get("accept", "*/*"),
                 "Content-Type": request.headers.get("content-type", "application/json")},
    )
    try:
        with urllib.request.urlopen(upstream, timeout=30) as result:
            headers = {name: value for name, value in result.headers.items()
                       if name.lower() in ("content-type", "cache-control", "location")}
            return Response(result.read(), status_code=result.status, headers=headers)
    except urllib.error.HTTPError as error:
        return Response(error.read(), status_code=error.code,
                        media_type=error.headers.get_content_type())
    except urllib.error.URLError as error:
        raise HTTPException(status_code=502, detail="Grafana is unavailable: %s" % error) from error


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="console-ui")

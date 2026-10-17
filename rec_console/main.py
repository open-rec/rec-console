"""Assemble the OpenRec console application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from rec_console.config.middleware import reject_disabled_features
from rec_console.config.router import router as config_router
from rec_console.module.airflow.router import router as airflow_router
from rec_console.module.analytics.router import router as analytics_router
from rec_console.module.dag.router import router as dag_router
from rec_console.module.entities.router import router as entities_router
from rec_console.module.model.router import router as model_router
from rec_console.module.monitor.router import router as monitor_router
from rec_console.module.recall.router import router as recall_router
from rec_console.module.serving.router import router as serving_router

app = FastAPI(title="OpenRec Console", version="0.1.0")
app.middleware("http")(reject_disabled_features)

for router in (
    config_router,
    recall_router,
    model_router,
    entities_router,
    airflow_router,
    dag_router,
    serving_router,
    analytics_router,
    monitor_router,
):
    app.include_router(router)


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount(
        "/", StaticFiles(directory=STATIC_DIR, html=True), name="console-ui"
    )

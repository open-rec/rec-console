"""HTTP API for OpenRec operational controls."""

import os
from pathlib import Path

from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rec_console.recall_indexes import RecallIndexManager


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
    manager = _manager()
    try:
        manager.client.info()
        return {"status": "ok", "elasticsearch": "ready"}
    except Exception as error:
        raise HTTPException(status_code=503, detail="Elasticsearch is unavailable") from error
    finally:
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


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="console-ui")

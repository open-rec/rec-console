"""Exercise router registration and deployment gates without live services."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from rec_console.main import app
from rec_console.module.entities import router as entities
from rec_console.module.monitor import router as monitor


def get(path):
    async def request():
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http", "asgi": {"version": "3.0"},
                "http_version": "1.1", "method": "GET", "scheme": "http",
                "path": path, "raw_path": path.encode(), "query_string": b"",
                "root_path": "", "headers": [],
                "server": ("test", 80), "client": ("test", 1234),
            },
            receive,
            send,
        )
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, json.loads(body)

    return asyncio.run(asyncio.wait_for(request(), timeout=5))


@pytest.mark.parametrize("mode", ["standalone", "cluster"])
def test_config_route_exposes_current_mode(monkeypatch, mode):
    monkeypatch.setenv("OPENREC_MODE", mode)
    status, body = get("/api/config")
    assert status == 200
    assert body["mode"] == mode
    assert body["features"]["model"] == (mode == "cluster")


@pytest.mark.parametrize("path", [
    "/api/recall/releases/hot", "/api/models/features",
    "/api/dag-configs/openrec_daily_recall", "/api/airflow/dags",
    "/api/analytics/business",
])
def test_standalone_blocks_cluster_routes_before_dependencies(monkeypatch, path):
    monkeypatch.setenv("OPENREC_MODE", "standalone")
    status, body = get(path)
    assert status == 404
    assert body == {"detail": "feature is only supported in cluster mode"}


@pytest.mark.parametrize("mode", ["standalone", "cluster"])
def test_entity_router_dispatches_and_preserves_not_found(monkeypatch, mode):
    monkeypatch.setenv("OPENREC_MODE", mode)
    monkeypatch.setattr(entities, "EntityQueryClient", lambda: SimpleNamespace(
        user=lambda user_id: {"id": user_id} if user_id == "known" else None,
    ))
    assert get("/api/entities/users/known") == (200, {"id": "known"})
    assert get("/api/entities/users/missing") == (404, {"detail": "entity was not found"})


@pytest.mark.parametrize("mode", ["standalone", "cluster"])
def test_health_checks_only_enabled_dependencies_and_closes_client(monkeypatch, mode):
    monkeypatch.setenv("OPENREC_MODE", mode)
    calls = []
    monkeypatch.setattr(monitor, "create_manager", lambda: SimpleNamespace(
        client=SimpleNamespace(info=lambda: calls.append("es"), close=lambda: calls.append("close")),
    ))
    monkeypatch.setattr(monitor, "AirflowClient", lambda: SimpleNamespace(dags=lambda: calls.append("airflow")))
    monkeypatch.setattr(monitor, "ServingGraphStore", lambda: SimpleNamespace(
        client=SimpleNamespace(current=lambda: calls.append("rec_server")),
    ))
    status, body = get("/health")
    assert status == 200
    assert body["mode"] == mode
    assert calls == (["es", "airflow", "rec_server", "close"] if mode == "cluster" else ["rec_server"])


def test_health_dependency_failure_preserves_status_and_closes_client(monkeypatch):
    monkeypatch.setenv("OPENREC_MODE", "cluster")
    closed = []

    def fail():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(monitor, "create_manager", lambda: SimpleNamespace(
        client=SimpleNamespace(info=fail, close=lambda: closed.append(True)),
    ))
    assert get("/health") == (503, {"detail": "Console dependency is unavailable: unavailable"})
    assert closed == [True]


def test_all_module_routes_are_included_in_openapi():
    paths = app.openapi()["paths"]
    for path in (
        "/api/recall/releases/prepare", "/api/entities/users/{user_id}",
        "/api/serving-graph", "/api/dag-configs/openrec_daily_recall",
        "/grafana/{path}", "/api/analytics/business", "/api/airflow/dags",
        "/api/models/training",
    ):
        assert path in paths

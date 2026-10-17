"""HTTP routes for the monitor module."""

import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from rec_console.config import console_config
from rec_console.infrastructure.airflow_client import AirflowClient
from rec_console.module.recall.service import create_manager
from rec_console.module.serving.service import ServingGraphStore

router = APIRouter()


@router.get("/health")
def health():
    config = console_config()
    manager = create_manager() if config["features"]["recall"] else None
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
        raise HTTPException(
            status_code=503,
            detail="Console dependency is unavailable: %s" % error,
        ) from error
    finally:
        if manager:
            manager.client.close()


@router.api_route("/grafana/{path:path}", methods=["GET", "POST"])
async def grafana_proxy(path: str, request: Request):
    """
    Expose Grafana through the console origin so remote browsers never use
    loopback URLs.
    """
    base = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
    query = ("?" + request.url.query) if request.url.query else ""
    body = await request.body()
    upstream = urllib.request.Request(
        "%s/grafana/%s%s" % (base, path, query),
        data=body or None,
        method=request.method,
        headers={
            "Accept": request.headers.get("accept", "*/*"),
            "Content-Type": request.headers.get(
                "content-type", "application/json"
            ),
        },
    )
    try:
        with urllib.request.urlopen(upstream, timeout=30) as result:
            headers = {
                name: value
                for name, value in result.headers.items()
                if name.lower()
                in ("content-type", "cache-control", "location")
            }
            return Response(
                result.read(), status_code=result.status, headers=headers
            )
    except urllib.error.HTTPError as error:
        return Response(
            error.read(),
            status_code=error.code,
            media_type=error.headers.get_content_type(),
        )
    except urllib.error.URLError as error:
        raise HTTPException(
            status_code=502, detail="Grafana is unavailable: %s" % error
        ) from error

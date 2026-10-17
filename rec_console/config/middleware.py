"""Enforce deployment capabilities for all console API modules."""

from fastapi import Request
from fastapi.responses import Response

from rec_console.config import console_config

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


async def reject_disabled_features(request: Request, call_next):
    features = console_config()["features"]
    for prefix, feature in FEATURE_PATHS.items():
        if request.url.path.startswith(prefix) and not features[feature]:
            return Response(
                content=(
                    '{"detail":"feature is only supported in cluster mode"}'
                ),
                status_code=404,
                media_type="application/json",
            )
    return await call_next(request)

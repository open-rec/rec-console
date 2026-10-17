"""HTTP routes for the serving module."""

from fastapi import APIRouter, HTTPException

from rec_console.config.schemas import ConfigRollbackRequest
from rec_console.module.serving.schemas import (
    ServingGraphExperimentRequest,
    ServingGraphExperimentStateRequest,
    ServingGraphPublishRequest,
    ServingGraphRoutingRequest,
)
from rec_console.module.serving.service import (
    RecServerError,
    ServingGraphStore,
)

router = APIRouter()


@router.get("/api/serving-graph")
def serving_graph(experiment: str = "default"):
    try:
        return ServingGraphStore().current(experiment)
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/api/serving-graph/publish")
def publish_serving_graph(request: ServingGraphPublishRequest):
    try:
        return ServingGraphStore().publish(request.graph, request.experiment)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RecServerError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/api/serving-graph/rollback")
def rollback_serving_graph(request: ConfigRollbackRequest):
    try:
        return ServingGraphStore().rollback(
            request.version, getattr(request, "experiment", "default")
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RecServerError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.put("/api/serving-graph/routing")
def configure_serving_graph_routing(request: ServingGraphRoutingRequest):
    try:
        return ServingGraphStore().client.configure_routing(
            request.model_dump()
        )
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/api/serving-graph/experiments")
def create_serving_graph_experiment(request: ServingGraphExperimentRequest):
    try:
        return ServingGraphStore().client.create_experiment(request.name)
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.put("/api/serving-graph/experiments/{experiment}/enabled")
def set_serving_graph_experiment_enabled(
    experiment: str, request: ServingGraphExperimentStateRequest
):
    try:
        return ServingGraphStore().set_experiment_enabled(
            experiment, request.enabled
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.delete("/api/serving-graph/experiments/{experiment}")
def delete_serving_graph_experiment(experiment: str):
    try:
        return ServingGraphStore().client.delete_experiment(experiment)
    except RecServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

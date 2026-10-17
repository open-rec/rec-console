"""HTTP routes for the model module."""

from fastapi import APIRouter, HTTPException

from rec_console.module.model.releases import ModelReleaseStore
from rec_console.module.model.schemas import (
    ModelPublishRequest,
    ModelRollbackRequest,
    ModelTrainingRequest,
)
from rec_console.module.model.training import ModelTraining

router = APIRouter()


@router.get("/api/models/releases/{scene}")
def model_releases(scene: str, target_type: str = "item"):
    try:
        return ModelReleaseStore().list(scene, target_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _model_training(method, *args):
    try:
        return getattr(ModelTraining(), method)(*args)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/api/models/features")
def model_features():
    return _model_training("catalog")


@router.get("/api/models/runtime")
def model_runtime():
    return _model_training("runtime")


@router.post("/api/models/training")
def model_training(request: ModelTrainingRequest):
    return _model_training("submit", request.model_dump(mode="json"))


@router.get("/api/models/training")
def model_training_runs():
    return _model_training("runs")


@router.post("/api/models/releases/publish")
def publish_model(request: ModelPublishRequest):
    try:
        return ModelReleaseStore().publish(
            request.scene, request.version, request.target_type
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/api/models/releases/rollback")
def rollback_model(request: ModelRollbackRequest):
    try:
        return ModelReleaseStore().rollback(
            request.scene, request.target_version, request.target_type
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

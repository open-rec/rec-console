"""HTTP routes for the dag module."""

from fastapi import APIRouter, HTTPException

from rec_console.config.schemas import ConfigRollbackRequest
from rec_console.infrastructure.airflow_client import (
    AirflowClient,
    AirflowError,
)
from rec_console.module.dag.schemas import (
    DailyRecallConfigRequest,
)
from rec_console.module.dag.service import DagConfigStore

router = APIRouter()


@router.get("/api/dag-configs/openrec_daily_recall")
def daily_recall_config():
    return DagConfigStore().current()


@router.post("/api/dag-configs/openrec_daily_recall/publish")
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


@router.post("/api/dag-configs/openrec_daily_recall/rollback")
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


@router.get("/api/dag-configs/openrec_daily_user_recall")
def daily_user_recall_config():
    return DagConfigStore(dag_id="openrec_daily_user_recall").current()


@router.post("/api/dag-configs/openrec_daily_user_recall/publish")
def publish_daily_user_recall_config(request: DailyRecallConfigRequest):
    try:
        result = DagConfigStore(dag_id="openrec_daily_user_recall").publish(
            request.model_dump()
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        AirflowClient().reparse("openrec_daily_user_recall")
        result["airflow_reparse"] = "requested"
    except AirflowError as error:
        result["airflow_reparse"] = "pending"
        result["warning"] = str(error)
    return result


@router.post("/api/dag-configs/openrec_daily_user_recall/rollback")
def rollback_daily_user_recall_config(request: ConfigRollbackRequest):
    try:
        result = DagConfigStore(dag_id="openrec_daily_user_recall").rollback(
            request.version
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        AirflowClient().reparse("openrec_daily_user_recall")
        result["airflow_reparse"] = "requested"
    except AirflowError as error:
        result["airflow_reparse"] = "pending"
        result["warning"] = str(error)
    return result

"""HTTP routes for the airflow module."""

from fastapi import APIRouter, HTTPException

from rec_console.infrastructure.airflow_client import (
    AirflowClient,
    AirflowError,
)
from rec_console.module.airflow.schemas import (
    DagStateRequest,
    DagTriggerRequest,
)
from rec_console.module.dag.service import DagConfigStore

router = APIRouter()


def _airflow(method, *args):
    try:
        return getattr(AirflowClient(), method)(*args)
    except AirflowError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/api/airflow/dags")
def airflow_dags():
    return _airflow("dags")


@router.get("/api/airflow/dags/{dag_id}")
def airflow_dag(dag_id: str):
    dag = _airflow("dag", dag_id)
    tasks = _airflow("dag_tasks", dag_id)
    config = (
        DagConfigStore(dag_id=dag_id).current()
        if dag_id in ("openrec_daily_recall", "openrec_daily_user_recall")
        else None
    )
    return {"dag": dag, "tasks": tasks.get("tasks", []), "config": config}


@router.patch("/api/airflow/dags/{dag_id}")
def airflow_dag_state(dag_id: str, request: DagStateRequest):
    return _airflow("update_dag", dag_id, request.is_paused)


@router.post("/api/airflow/dags/{dag_id}/runs")
def airflow_trigger(dag_id: str, request: DagTriggerRequest):
    return _airflow("trigger", dag_id, request.conf)


@router.get("/api/airflow/dags/{dag_id}/runs")
def airflow_runs(dag_id: str, limit: int = 20):
    return _airflow("runs", dag_id, min(max(limit, 1), 100))


@router.get("/api/airflow/dags/{dag_id}/runs/{run_id}/tasks")
def airflow_tasks(dag_id: str, run_id: str):
    return _airflow("tasks", dag_id, run_id)


@router.get("/api/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs")
def airflow_task_logs(
    dag_id: str, run_id: str, task_id: str, try_number: int = 1
):
    return _airflow("logs", dag_id, run_id, task_id, max(try_number, 1))

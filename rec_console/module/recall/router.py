"""HTTP routes for the recall module."""

from fastapi import APIRouter, HTTPException

from rec_console.module.recall.schemas import (
    ActivateRequest,
    PrepareRequest,
    RollbackRequest,
    SwitchRequest,
)
from rec_console.module.recall.service import create_manager

router = APIRouter()


def _call(method, *args):
    manager = create_manager()
    try:
        return getattr(manager, method)(*args)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        manager.client.close()


@router.post("/api/recall/releases/prepare")
def prepare(request: PrepareRequest):
    return _call(
        "prepare", request.algorithm, request.business_date, request.revision
    )


@router.post("/api/recall/releases/activate")
def activate(request: ActivateRequest):
    return _call(
        "activate",
        request.algorithm,
        request.index,
        request.expected_documents,
        request.max_index_versions,
    )


@router.post("/api/recall/releases/rollback")
def rollback(request: RollbackRequest):
    return _call("rollback", request.algorithm, request.target_index)


@router.post("/api/recall/releases/switch")
def switch_release(request: SwitchRequest):
    return _call("switch", request.algorithm, request.target_index)


@router.get("/api/recall/releases/{algorithm}")
def releases(algorithm: str):
    return _call("list_indexes", algorithm)

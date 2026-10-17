"""HTTP routes for the entities module."""

from fastapi import APIRouter, HTTPException

from rec_console.module.entities.client import (
    EntityQueryClient,
    EntityQueryError,
)

router = APIRouter()


def _entity_query(method, *args):
    try:
        result = getattr(EntityQueryClient(), method)(*args)
    except EntityQueryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="entity was not found")
    return result


@router.get("/api/entities/users/{user_id}")
def query_user(user_id: str):
    return _entity_query("user", user_id)


@router.get("/api/entities/items/{item_id}")
def query_item(item_id: str):
    return _entity_query("item", item_id)


@router.get("/api/entities/events")
def query_events(user_id: str, scene: str, event_type: str):
    return {
        "user_id": user_id,
        "scene": scene,
        "event_type": event_type,
        "events": _entity_query("events", user_id, scene, event_type),
    }

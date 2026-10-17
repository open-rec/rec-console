"""Expose console configuration to the frontend."""

from fastapi import APIRouter

from rec_console.config import console_config

router = APIRouter()


@router.get("/api/config")
def config():
    return console_config()

"""Airflow API request models."""

from pydantic import BaseModel, Field


class DagStateRequest(BaseModel):
    is_paused: bool


class DagTriggerRequest(BaseModel):
    conf: dict = Field(default_factory=dict)

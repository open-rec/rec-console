"""Serving API request models."""

from pydantic import BaseModel, Field


class ServingGraphPublishRequest(BaseModel):
    graph: dict
    experiment: str = "default"


class ServingGraphRoutingRequest(BaseModel):
    param: str = "ab"
    defaultExperiment: str = "default"
    routes: dict[str, str] = Field(default_factory=dict)


class ServingGraphExperimentRequest(BaseModel):
    name: str


class ServingGraphExperimentStateRequest(BaseModel):
    enabled: bool

"""Recall API request models."""

from pydantic import BaseModel, Field


class PrepareRequest(BaseModel):
    algorithm: str
    business_date: str
    revision: str = "r001"


class ActivateRequest(BaseModel):
    algorithm: str
    index: str
    expected_documents: int = Field(gt=0)
    max_index_versions: int = Field(default=2, ge=2)


class RollbackRequest(BaseModel):
    algorithm: str
    target_index: str | None = None


class SwitchRequest(BaseModel):
    algorithm: str
    target_index: str

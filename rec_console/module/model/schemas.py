"""Model API request models."""

from datetime import date

from pydantic import BaseModel, Field


class ModelPublishRequest(BaseModel):
    model_config = {"extra": "forbid"}
    scene: str
    version: str
    target_type: str = Field(default="item", pattern="^(item|user)$")


class ModelTrainingRequest(BaseModel):
    model_config = {"extra": "forbid"}
    business_date: date
    revision: str = Field(pattern="^r[0-9]{3,}$")
    scene: str = Field(default="global", pattern="^[A-Za-z0-9_-]+$")
    model_type: str = Field(default="lr", pattern="^(lr|fm|lightgbm)$")
    target_type: str = Field(default="item", pattern="^(item|user)$")
    epochs: int = Field(default=5, ge=1, le=100)
    batch_size: int = Field(default=256, ge=1, le=65536)
    validation_ratio: float = Field(default=0.2, gt=0, lt=1)
    factor_dim: int = Field(default=8, ge=1, le=256)
    min_auc: float = Field(default=0, ge=0, le=1)
    feature_selection: dict[str, list[str]]


class ModelRollbackRequest(BaseModel):
    scene: str
    target_version: str | None = None
    target_type: str = Field(default="item", pattern="^(item|user)$")

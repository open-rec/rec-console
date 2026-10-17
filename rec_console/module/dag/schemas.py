"""Dag API request models."""

from pydantic import BaseModel


class DailyRecallConfigRequest(BaseModel):
    schedule: str
    algorithms: list[str]
    default_revision: str = "r001"
    max_index_versions: int = 2
    retries: int = 1
    retry_delay_minutes: int = 5

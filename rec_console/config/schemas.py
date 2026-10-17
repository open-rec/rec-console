"""Request shared by versioned configuration rollback APIs."""

from pydantic import BaseModel


class ConfigRollbackRequest(BaseModel):
    version: str | None = None
    experiment: str = "default"

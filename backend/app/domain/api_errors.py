from typing import Any

from pydantic import Field

from app.domain.models import StrictModel


class ApiErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorBody(StrictModel):
    error: ApiErrorDetail

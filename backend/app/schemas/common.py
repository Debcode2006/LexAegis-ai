"""Shared response schemas."""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    service: str
    version: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class DataResponse(BaseModel, Generic[T]):
    data: T
    request_id: Optional[str] = None

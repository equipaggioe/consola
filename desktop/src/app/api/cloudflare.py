"""Cloudflare's API: the calls `update_cloudflare` makes."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.api import http

API = "https://api.cloudflare.com/client/v4"


class Answer(BaseModel):
    """What every answer carries, successful or not."""

    success: bool
    errors: list[dict[str, Any]]


class Zone(BaseModel):
    """A DNS zone."""

    id: str


class DnsRecord(BaseModel):
    """A DNS record."""

    id: str
    content: str
    proxied: bool


class Zones(Answer):
    """The zones of a domain."""

    result: list[Zone]


class DnsRecords(Answer):
    """The records of a zone."""

    result: list[DnsRecord]


class RejectedError(Exception):
    """Cloudflare answered, and rejected the request."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        """Keep the errors Cloudflare gave."""
        super().__init__(f"Cloudflare rejected the request: {errors}")
        self.errors = errors


def call[A: Answer](
    token: str, method: str, path: str, shape: type[A], body: Mapping[str, Any] | None = None
) -> A:
    """Call the API and read the answer with `shape`.

    Raises `OSError` without an answer, `RejectedError` when Cloudflare
    rejects it and `ValidationError` when it does not have the shape.
    """
    raw = http.request(
        f"{API}{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        body=json.dumps(body).encode("utf-8") if body is not None else None,
    )
    # A rejected answer does not bring the `result` of `shape`.
    answer = Answer.model_validate_json(raw)
    if not answer.success:
        raise RejectedError(answer.errors)
    return shape.model_validate_json(raw)

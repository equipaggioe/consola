"""The answers of Cloudflare's API that `update_cloudflare` reads."""

from typing import Any

from pydantic import BaseModel


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


class Zones(Answer):
    """The zones of a domain."""

    result: list[Zone]


class DnsRecords(Answer):
    """The records of a zone."""

    result: list[DnsRecord]

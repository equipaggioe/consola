"""The index of Flutter's published releases."""

from pydantic import BaseModel

from app.api import http

RELEASES_URL = "https://storage.googleapis.com/flutter_infra_release/releases/"


class Current(BaseModel):
    """The release each channel points to."""

    stable: str


class Release(BaseModel):
    """A published release."""

    hash: str
    version: str
    archive: str
    sha256: str


class Index(BaseModel):
    """The whole index of a system."""

    current_release: Current
    releases: list[Release]


def index(filename: str) -> Index:
    """Return a system's index.

    Raises `OSError` without an answer, and `ValidationError` when it
    does not have the shape of `Index`.
    """
    raw = http.request(RELEASES_URL + filename, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    return Index.model_validate_json(raw)

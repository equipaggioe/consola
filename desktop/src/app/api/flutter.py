"""The index of Flutter's published releases."""

from pydantic import BaseModel


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

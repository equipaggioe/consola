"""The thread that fills the axes that ask for their values."""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QObject, QThread, Signal

from app.services.catalog import (
    preview_checks,
    queried_values,
)
from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.registry import Capability


class AxesLoader(QThread):
    """Read in the background the catalogs a capability asks for.

    Asking the SDK which devices and system images exist takes seconds
    to a minute the first time; then it stays cached in
    `services/cache.py`. Doing it in the interface thread would freeze
    the window each time the emulator's tab opens, so the panel draws
    with empty lists and fills when this ends.

    The same holds even more for the repo's VPS: asking which services
    it has is an SSH round trip against a machine that may be off. So
    the loader receives the project's config, which says which VPS to
    ask, and not only the capability.
    """

    ready = Signal(dict)

    def __init__(
        self,
        capability: Capability,
        config: Config,
        root: str = "",
        refresh: bool = False,
        parent: QObject | None = None,
    ) -> None:
        """Keep what the query needs."""
        super().__init__(parent)
        self._capability = capability
        self._config = config
        # The repo's root: the backups axis asks for it, since its
        # folder can be declared relative to it
        # (`services/catalog.py::_backup_files`).
        self._root = root
        self._refresh = refresh

    @override
    def run(self) -> None:
        resolved: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for axis in self._capability.axes:
            if not axis.is_queried:
                continue
            try:
                resolved[axis.name] = queried_values(
                    axis.source, refresh=self._refresh, config=self._config, root=self._root
                )
            except TaskError as exc:
                # The axis stays empty and the panel says why
                # (ADR-0076).
                resolved[axis.name] = ([], {})
                errors[axis.name] = str(exc)
        if self._capability.live_state:
            try:
                resolved[LIVE] = queried_values(
                    self._capability.live_state, config=self._config, root=self._root
                )
            except TaskError as exc:
                no_values: tuple[list[str], dict[str, str]] = ([], {})
                resolved[LIVE] = no_values
                errors[LIVE] = str(exc)
        if self._capability.preview:
            try:
                resolved[PREVIEW] = preview_checks(
                    self._capability.preview, config=self._config, root=self._root
                )
            except TaskError as exc:
                nothing: tuple[list[str], list[str]] = ([], [])
                resolved[PREVIEW] = nothing
                errors[PREVIEW] = str(exc)
        resolved[ERRORS] = errors
        self.ready.emit(resolved)


# The key the inventory of «what is running» travels under in the
# loader's result. It is not an axis: it is not chosen, it is looked at
# and stopped.
LIVE = "@live"
# And that of what running will do (`Capability.preview`).
PREVIEW = "@preview"
# And that of the axes whose query failed, each with its reason.
ERRORS = "@errors"

"""The errors a capability can raise."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication


class TaskError(RuntimeError):
    """An expected failure: the tab turns red and the app keeps running.

    Level 0 never prints or exits the process: it reports and returns.
    """


class Cancelled(RuntimeError):
    """The user stopped the task.

    Not an error: the tab stays gray, not red.
    """


class MissingConfig(TaskError):
    """Keys missing from `.consola/config.env` for the task to run.

    It differs from a plain TaskError so the UI can offer the Settings
    gear filtered to `keys` instead of a loose message (ADR-0064).
    """

    def __init__(self, keys: list[str]) -> None:
        """Keep the missing keys and name them in the message."""
        self.keys = list(keys)
        from app.services.settings import names

        missing = names(self.keys)
        # The tab shows the message, so it goes through Linguist.
        super().__init__(
            QCoreApplication.translate("MissingConfig", "Falta configurar: {0}").format(missing)
        )

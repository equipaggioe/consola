from __future__ import annotations
from dataclasses import dataclass
from typing import Any

class Level:
    INFO = 'info'
    OK = 'ok'
    WARN = 'warn'
    ERROR = 'error'

@dataclass
class TaskContext:
    """Placeholder context for stub capabilities."""
    capability_id: str
    log_callback: Any = None  # will be Callable[[str, str], None]
    
    def log(self, msg: str, level: str = Level.INFO) -> None:
        if self.log_callback:
            self.log_callback(msg, level)

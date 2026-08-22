from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any

@dataclass
class AxisDef:
    """An axis that generates buttons/menu/field from values."""
    name: str
    values: list[str]
    expand: str  # 'buttons' | 'menu' | 'field' | 'scope'
    danger: set[str] = field(default_factory=set)
    label: str = ''

@dataclass
class Capability:
    """A registered capability that maps to one or more UI buttons."""
    id: str
    name: str
    group: str
    section: str
    kind: str  # 'live' | 'once' | 'destructive' | 'interactive' | 'view' | 'background'
    axes: list[AxisDef] = field(default_factory=list)
    composed_of: list[str] = field(default_factory=list)
    icon: str = ''
    stub: bool = True
    func: Callable[..., Any] | None = None

GROUP_ICONS = {
    'Launchers': '🚀',
    'Builders': '🔨',
    'Emulators': '📱',
    'VPS · ops': '⚙️',
    'VPS · server': '🖥️',
    'VPS · setup': '🔧',
    'Base de datos': '🗄️',
    'Utils': '🧰',
}

class Registry:
    """Global registry of all capabilities."""
    def __init__(self):
        self._capabilities: dict[str, Capability] = {}
        self._group_order: list[str] = []
    
    def register(self, cap: Capability) -> None:
        if cap.group and cap.group not in self._group_order:
            self._group_order.append(cap.group)
        self._capabilities[cap.id] = cap

    def get_all(self) -> list[Capability]:
        return list(self._capabilities.values())
        
    def get_groups(self) -> dict[str, list[Capability]]:
        groups: dict[str, list[Capability]] = {group: [] for group in self._group_order}
        for cap in self._capabilities.values():
            if cap.group in groups:
                groups[cap.group].append(cap)
        return groups
        
    def get_capability(self, cap_id: str) -> Capability | None:
        return self._capabilities.get(cap_id)
        
    def get_group_icon(self, group: str) -> str:
        return GROUP_ICONS.get(group, '')

# Module-level singleton
registry = Registry()

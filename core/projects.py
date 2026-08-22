from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Project:
    name: str
    path: str
    color: str  # hex
    icon: str   # emoji

MOCK_PROJECTS = [
    Project('navetta', 'E:/Git/navetta', '#58a6ff', '🚢'),
    Project('cadenza', 'E:/Git/cadenza', '#bc8cff', '🎵'),
    Project('forziere', 'E:/Git/forziere', '#3fb950', '🔐'),
    Project('vettore', 'E:/Git/vettore', '#d29922', '📦'),
    Project('parametri', 'E:/Git/parametri', '#f47067', '⚙️'),
    Project('presenze', 'E:/Git/presenze', '#a5d6ff', '👥'),
    Project('spazio', 'E:/Git/spazio', '#ffa657', '🌌'),
    Project('banditore', 'E:/Git/banditore', '#ff7b72', '📢'),
]

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any

@dataclass
class AxisDef:
    """Un eje que genera opciones en el panel de parametros.

    `select` es la decision importante (docs/panel-de-parametros.md §2):
    'many' = casillas (tiene sentido pedir dos a la vez: panel + backoffice),
    'one'  = segmentado (pedir dos es un absurdo: start + stop).
    """
    name: str
    values: list[str]
    expand: str  # 'checks' | 'buttons' | 'menu' | 'field' | 'scope'
    danger: set[str] = field(default_factory=set)
    label: str = ''
    select: str = 'one'  # 'one' | 'many'
    checked_by_default: bool = True  # solo para select='many': todas marcadas, o ninguna
    allow_empty: bool = False  # solo para select='many': ninguna marcada es una eleccion valida,
                                # no "olvidaste elegir" (ej. 'Pesados' en clean_artifacts)

    @property
    def is_multi(self) -> bool:
        return self.select == 'many'

    @property
    def display(self) -> str:
        return self.label or self.name.replace('_', ' ').capitalize()


@dataclass
class Step:
    """Un paso de una capacidad compuesta, con casilla propia en el panel.

    `optional=False` se dibuja marcado y deshabilitado: un 'Build Vite' sin
    build no es una variante, es un error.
    """
    id: str
    label: str
    optional: bool = True
    default: bool = True
    requires_env: set[str] = field(default_factory=set)


@dataclass
class Capability:
    """Una capacidad registrada. Genera UN boton en el rail; sus variantes
    y pasos viven en el panel de parametros, no en filas duplicadas."""
    id: str
    name: str
    group: str
    section: str
    kind: str  # 'live' | 'once' | 'destructive' | 'interactive' | 'view' | 'background'
    axes: list[AxisDef] = field(default_factory=list)
    composed_of: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    icon: str = ''
    description: str = ''  # una linea: que hace el boton, en tooltip y cabecera
    level: str = ''        # 'A' | 'C'; vacio = se deduce de steps/composed_of
    hidden: bool = False   # capacidad atomica: existe como paso, no como boton
    stub: bool = True
    func: Callable[..., Any] | None = None

    @property
    def multi_axes(self) -> list[AxisDef]:
        return [a for a in self.axes if a.is_multi]

    @property
    def single_axes(self) -> list[AxisDef]:
        return [a for a in self.axes if not a.is_multi]

    @property
    def is_composite(self) -> bool:
        """Compuesta = encadena varias atomicas (docs/catalogo-funciones.md).

        Lo normal es que se note sola: si declara `steps` o `composed_of`, es
        compuesta. Pero varias compuestas reales (`bootstrap_db`,
        `start_emulator`...) no publican sus pasos en el panel, y ahi el
        catalogo lo dice con `level='C'`. Lo explicito manda.
        """
        if self.level:
            return self.level.upper().startswith('C')
        return bool(self.steps or self.composed_of)

    @property
    def level_label(self) -> str:
        return 'Compuesta' if self.is_composite else 'Atómica'


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


def _prettify(cap_id: str) -> str:
    return cap_id.replace('_', ' ').capitalize()


class Registry:
    """Registro global de capacidades."""
    def __init__(self):
        self._capabilities: dict[str, Capability] = {}
        self._group_order: list[str] = []

    def register(self, cap: Capability) -> None:
        if cap.group and cap.group not in self._group_order:
            self._group_order.append(cap.group)
        self._capabilities[cap.id] = cap

    def bind(self, cap_id: str, func: Callable[..., Any]) -> Callable[..., Any]:
        """Le da cuerpo real a una capacidad declarada en el catalogo.

        El catalogo (`core/catalog.py`) declara la forma: grupo, seccion, ejes,
        pasos. `core/tasks/` la implementa. Mientras nadie llame a `bind`, la
        capacidad sigue siendo un stub y la UI la dibuja como tal.
        """
        cap = self._capabilities.get(cap_id)
        if cap is None:
            raise KeyError(f'No hay ninguna capacidad registrada con id {cap_id!r}')
        cap.func = func
        cap.stub = False
        return func

    def implemented(self) -> list[Capability]:
        return [c for c in self._capabilities.values() if not c.stub]

    def get_all(self) -> list[Capability]:
        return list(self._capabilities.values())

    def get_groups(self, include_hidden: bool = False) -> dict[str, list[Capability]]:
        groups: dict[str, list[Capability]] = {group: [] for group in self._group_order}
        for cap in self._capabilities.values():
            if cap.hidden and not include_hidden:
                continue
            if cap.group in groups:
                groups[cap.group].append(cap)
        return {g: caps for g, caps in groups.items() if caps}

    def get_capability(self, cap_id: str) -> Capability | None:
        return self._capabilities.get(cap_id)

    def get_group_icon(self, group: str) -> str:
        return GROUP_ICONS.get(group, '')

    def resolve_steps(self, cap: Capability) -> list[Step]:
        """Pasos efectivos de una capacidad.

        Si los declara, se usan tal cual (permite poner el paso nucleo en su
        orden real: bump -> build -> subida). Si no, se derivan de
        `composed_of`, con el nucleo primero y el resto opcional.
        """
        if cap.steps:
            return cap.steps
        if not cap.composed_of:
            return [Step(cap.id, cap.name, optional=False)]
        # Un orquestador puro no tiene nucleo aparte: la composicion es la
        # capacidad. Sus pasos son exactamente lo que encadena.
        derived = []
        for sub_id in cap.composed_of:
            sub = self._capabilities.get(sub_id)
            derived.append(Step(sub_id, sub.name if sub else _prettify(sub_id)))
        return derived


# Singleton a nivel de modulo
registry = Registry()

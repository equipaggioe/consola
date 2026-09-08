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
    expand: str  # 'checks' | 'buttons' | 'menu' | 'field' | 'scope' | 'pick'
    danger: set[str] = field(default_factory=set)
    label: str = ''
    select: str = 'one'  # 'one' | 'many'
    checked_by_default: bool = True  # solo para select='many': todas marcadas, o ninguna.
                                # Es el caso degenerado de `defaults`: cuando el default es
                                # "todas" o "ninguna" no hace falta enumerarlas.
    defaults: set[str] = field(default_factory=set)  # solo para select='many': cuales arrancan
                                # marcadas cuando no son ni todas ni ninguna (los cinco paquetes
                                # base de nueve). Declarar el default como dato evita partir un
                                # eje en dos secciones solo para expresarlo: la division
                                # base/opcional no es una propiedad del dominio (`postgis` es
                                # base en un repo con datos geograficos), es este default.
    allow_empty: bool = False  # solo para select='many': ninguna marcada es una eleccion valida,
                                # no "olvidaste elegir" (ej. 'Pesados' en clean_artifacts)
    discover: tuple[str, ...] = ()  # tipos de `core/targets.py` cuyos nombres son los valores
    source: str = ''            # catalogo de la MAQUINA que llena este eje
                                # (`core/catalog.py::machine_values`): el
                                # dispositivo o la maquina virtual no salen de
                                # mirar el repo abierto, salen de preguntarle al
                                # SDK. Se resuelve igual que `discover`, pero
                                # contra la maquina y no contra la carpeta.
    labels: dict = field(default_factory=dict)  # valor -> como se lee. Para las
                                # listas largas de `expand='pick'`, donde el
                                # valor real es un id feo
                                # (`system-images;android-36;google_apis;x86_64`)
                                # y lo que se elige es "Android 36 | Google APIs".
    placeholder: str = ''       # solo expand='field': marca de agua del campo. Para cuando el
                                # ejemplo ayuda a escribir el valor pero no es un default que
                                # convenga dejar puesto (las rutas a copiar cambian por repo).
    multiline: bool = False     # solo expand='field': caja de varios renglones, un valor por
                                # linea. Para listas cortas que se escriben a mano (las rutas
                                # a copiar): en una sola linea no se ve donde termina cada una.
    combine: set[str] = field(default_factory=set)  # solo select='one': valores que se marcan
                                # aparte del grupo excluyente y stackean con el (ej. 'build' en
                                # bump_mode: patch|minor|major|none son excluyentes, 'build' suma)
    default: str = ''           # solo select='one': valor excluyente marcado al inicio;
                                # vacio = el primero que no este en `combine`
    truthy: str = ''            # solo select='one' de dos valores: cual significa True.
                                # Un segmentado de dos ('simulacro'/'borrar') es un booleano
                                # con dos rotulos legibles: sin esto, quien lee el payload
                                # tiene que comparar la cadena a mano y el catalogo pierde el
                                # control de como se lee su propio eje.
    join: str = ''              # solo con `combine`: como se unen el valor excluyente y los
                                # combinados en la cadena que espera la funcion
                                # ('patch' + 'build' -> 'patch+build')

    @property
    def exclusive_values(self) -> list[str]:
        return [v for v in self.values if v not in self.combine]

    @property
    def initial(self) -> str:
        """El valor excluyente que arranca marcado."""
        opciones = self.exclusive_values
        if self.default in opciones:
            return self.default
        return opciones[0] if opciones else ''

    @property
    def is_multi(self) -> bool:
        return self.select == 'many'

    def starts_checked(self, value: str) -> bool:
        """Si esta casilla arranca marcada. Sin `defaults`, manda el booleano global."""
        if self.defaults:
            return value in self.defaults
        return self.checked_by_default

    @property
    def is_from_machine(self) -> bool:
        """Sus valores salen de preguntarle al SDK, no del catalogo ni del repo."""
        return bool(self.source)

    @property
    def is_discovered(self) -> bool:
        """Sus valores salen de mirar el repo abierto, no del catalogo (PLAN.md 2.4).

        El catalogo se carga una sola vez al arrancar y el repo cambia con el
        selector, asi que un eje descubierto se declara vacio aca y lo llena
        `catalog.for_project()` cada vez que se arma un panel.
        """
        return bool(self.discover) or bool(self.source)

    @property
    def display(self) -> str:
        return self.label or self.name.replace('_', ' ').capitalize()

    def text_of(self, value: str) -> str:
        """Como se lee un valor. Sin etiqueta declarada, el valor tal cual."""
        return self.labels.get(value, value)


@dataclass
class Step:
    """Un paso de una capacidad compuesta, con casilla propia en el panel.

    `optional=False` se dibuja marcado y deshabilitado: un 'Build binario' sin
    build no es una variante, es un error. Los builders que si dejan desmarcar
    su compilacion (APK, Vite) lo hacen porque sin ella queda un modo con
    sentido: subir el artefacto que ya esta en disco.
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
    scope: str = 'repo'    # 'repo' | 'machine': ver `is_machine_wide`
    hidden: bool = False   # capacidad atomica: existe como paso, no como boton
    view: str = ''         # segunda vista de la pestana, ademas de la consola:
                           # 'web' = navegador embebido apuntado al endpoint que
                           # la tarea publica con `ctx.serve()`. El log de un
                           # launcher es el subproducto; lo que entrega es una
                           # URL (docs/launchers.md 2.3).
    fanout: str = ''       # solo kind='live': nombre del eje `select='many'`
                           # cuyos valores NO se corren en un bucle sino en una
                           # pestana cada uno. Marcar panel + backoffice son dos
                           # dev servers vivos a la vez, no dos pasos en fila
                           # (docs/launchers.md 2.1).
    concurrent: bool = False  # compuesta concurrente: sus pasos son capacidades
                           # que se lanzan en paralelo, una pestana cada una, y
                           # ninguna termina. No tiene `func`: su cuerpo es el
                           # despachador de la interfaz, porque "N pestanas" no
                           # significa nada en `core/` (docs/launchers.md 2.5).
    live_state: str = ''   # inventario que el panel muestra como cabecera de
                           # estado, con su boton de apagar por fila
                           # (`core/catalog.py::machine_values`). Es lo que
                           # reemplaza al boton "Apagar emulador": lo que corre
                           # se ve donde se elige, y se apaga desde ahi.
    stub: bool = True
    func: Callable[..., Any] | None = None

    @property
    def multi_axes(self) -> list[AxisDef]:
        return [a for a in self.axes if a.is_multi]

    @property
    def pick_axes(self) -> list[AxisDef]:
        """Ejes de lista larga y cerrada: se eligen buscando, no marcando.

        Un catalogo de cien dispositivos o de trescientas system images no entra
        en casillas ni en un segmentado — pero tampoco es texto libre, porque
        los valores validos son exactamente esos.
        """
        return [a for a in self.axes if a.expand == 'pick']

    @property
    def single_axes(self) -> list[AxisDef]:
        """Ejes de eleccion unica que se dibujan como opciones excluyentes.

        Los de `expand='field'` quedan fuera: tambien son de valor unico, pero
        el valor se escribe (una ruta de instalacion, un API level) en vez de
        elegirse de una lista cerrada.
        """
        return [a for a in self.axes
                if not a.is_multi and a.expand not in ('field', 'pick')]

    @property
    def field_axes(self) -> list[AxisDef]:
        """Ejes que se escriben a mano. `values[0]` es el valor por defecto."""
        return [a for a in self.axes if a.expand == 'field']

    @property
    def has_web_view(self) -> bool:
        return self.view == 'web'

    @property
    def is_composite(self) -> bool:
        """Compuesta = encadena varias atomicas (docs/catalogo-funciones.md).

        Lo normal es que se note sola: si declara `steps` o `composed_of`, es
        compuesta. Pero varias compuestas reales (`bootstrap_db`,
        `teardown_db`...) no publican sus pasos en el panel, y ahi el
        catalogo lo dice con `level='C'`. Lo explicito manda.
        """
        if self.level:
            return self.level.upper().startswith('C')
        return bool(self.steps or self.composed_of)

    @property
    def level_label(self) -> str:
        return 'Compuesta' if self.is_composite else 'Atómica'

    def kwargs_from(self, payload: dict) -> dict:
        """Los keyword-arguments de la funcion, leidos de lo que marco el panel.

        Es el reemplazo generico de `ui/task_adapters.py`: no hay una tabla por
        capacidad porque no hace falta, la capacidad ya se declara a si misma.
        El contrato que lo permite (docs/contrato-de-nombres.md) es que el `name`
        de un eje y el `id` de un paso SEAN el nombre del parametro; la etiqueta
        que lee el humano vive aparte, en `label`/`labels`.

        Los pasos derivados de `composed_of` no entran: son documentacion de que
        botones encadena este boton, no casillas con un booleano detras. Quien
        quiere una casilla por paso declara `steps=`.
        """
        marcados = set(payload.get('steps') or ())
        kwargs = {axis.name: self._axis_value(axis, payload) for axis in self.axes}
        kwargs.update({step.id: step.id in marcados for step in self.steps})
        return kwargs

    def _axis_value(self, axis: AxisDef, payload: dict):
        """El valor de un eje, buscado en el balde donde el panel lo dejo.

        `ParamsPanel.payload()` agrupa por tipo de control y no por significado
        (`variants` las casillas, `options` lo excluyente, `fields` lo escrito,
        `picks` las listas largas), asi que hay que saber en cual cayo cada eje
        — y eso es justo lo que dicen su `expand` y su `select`.
        """
        if axis.expand == 'field':
            # Vacio es una eleccion valida: quien borro el campo pide el valor
            # por defecto de la funcion, no el del catalogo.
            escrito = (payload.get('fields') or {}).get(axis.name, '')
            # Una caja de varios renglones ES una lista: un valor por linea. Lo
            # que la separa es el salto de linea, no una coma que despues haya
            # que explicar en un placeholder.
            if axis.multiline:
                return [ln.strip() for ln in escrito.splitlines() if ln.strip()]
            return escrito
        if axis.expand == 'pick':
            return (payload.get('picks') or {}).get(axis.name, '')
        if axis.is_multi:
            marcados = list((payload.get('variants') or {}).get(axis.name) or ())
            # El eje de `fanout` ya viene repartido: `TabPanel._run_fanout` abre
            # una pestana por valor, asi que aca llega uno solo, no la lista.
            if axis.name and axis.name == self.fanout:
                return marcados[0] if marcados else ''
            return marcados
        crudo = (payload.get('options') or {}).get(axis.name)
        if axis.combine:
            # Un eje con `combine` puede traer dos marcas (`['patch', 'build']`).
            # El orden de la cadena lo fija el catalogo, no el orden en que el
            # panel las devolvio: primero el excluyente, despues los combinados.
            marcados = [crudo] if isinstance(crudo, str) else list(crudo or ())
            base = next((v for v in marcados if v not in axis.combine), axis.initial)
            extra = [v for v in axis.values if v in axis.combine and v in marcados]
            return axis.join.join([base, *extra]) if axis.join else base
        # Ausente o vacio = el eje no se dibujo (un preset guardado antes de que
        # existiera, o un repo con un solo valor que descubrir): vale el default
        # declarado, que es lo que el panel habria mostrado.
        valor = crudo or axis.initial
        return valor == axis.truthy if axis.truthy else valor

    @property
    def is_machine_wide(self) -> bool:
        """Si la accion le pasa a la maquina y no al repo abierto.

        Instalar un SDK no es una decision de un repositorio: el directorio
        elegido vale para todos. Por eso sus parametros se guardan una sola vez
        (`ui/params_store.py`) en vez de por repo, y no tiene sentido que la
        accion dependa de que haya un proyecto abierto.
        """
        return self.scope == 'machine'


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
        """Pasos efectivos de una capacidad: los que declara, o ella misma.

        `composed_of` NO deriva pasos. Es documentacion —de que botones esta
        hecho este boton— y sus entradas son ids de CAPACIDAD, que jamas van a
        coincidir con el nombre de un parametro (`generate_remote_keypair`
        contra `generate`). Derivar de ahi producia casillas cuyo id no le
        correspondia a nada, y por eso once capacidades ya declaraban `steps=`
        a mano para taparlo (docs/contrato-de-nombres.md §2, causa C).

        Quien quiere una casilla por paso la declara. Sin `steps`, la capacidad
        es un solo paso obligatorio y el panel no dibuja la seccion.
        """
        return cap.steps or [Step(cap.id, cap.name, optional=False)]


# Singleton a nivel de modulo
registry = Registry()

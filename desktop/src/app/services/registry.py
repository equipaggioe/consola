"""The capabilities: their shape, axes, steps and registry."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QCoreApplication


@dataclass(frozen=True)
class Facet:
    """A feature of a composite value, with its own list in the panel.

    A `pick` axis offers whole values; its `facets` say the value is
    made of parts chosen separately. The saved value does not change,
    still the full id the tool understands; what changes is how one gets
    to it.

    It comes from the SDK's system images. The catalog brings several
    hundred packages (`system-images;android-36;google_apis;x86_64`)
    that are really the combination of three things: Android version,
    variant and architecture. One list with all three permuted forces
    reading three hundred almost equal labels to find the one that
    changes in a single field. Three short lists trimming each other
    answer the question one comes with («I want 36 with Play Store») in
    three glances.

    `part` is the index inside the value split by `AxisDef.facet_sep`.
    """

    name: str
    label: str
    part: int


@dataclass
class AxisDef:
    """An axis that generates options in the parameters panel.

    `select` is the important decision (ADR-0004): 'many' = checkboxes
    (asking for two at once makes sense: panel + backoffice), 'one' =
    segmented (asking for two is absurd: start + stop).
    """

    name: str
    values: list[str]
    # 'checks' | 'buttons' | 'menu' | 'field' | 'scope' | 'pick'
    expand: str
    danger: set[str] = field(default_factory=set)
    label: str = ""
    select: str = "one"  # 'one' | 'many'
    # only for select='many': all checked, or none. It is the degenerate
    # case of `defaults`: when the default is «all» or «none» there is
    # no need to enumerate them.
    checked_by_default: bool = True
    # only for select='many': which start checked when neither all nor
    # none (five base packages of nine). Declaring the default as data
    # avoids splitting an axis in two sections just to express it: the
    # base/optional division is no property of the domain (`postgis` is
    # base in a repo with geographic data), it is this default.
    defaults: set[str] = field(default_factory=set)
    # choosing nothing is a valid choice, not «you forgot to choose». In
    # select='many', no box checked ('Pesados' in clean_artifacts). In
    # expand='pick', the list brings a first empty entry and choosing it
    # means «let the function decide»: the emulator of 'App móvil' is
    # not chosen unless two are alive, and requiring it would leave the
    # button amber when there is none.
    allow_empty: bool = False
    # types of `services/targets.py` whose names are the values
    discover: tuple[str, ...] = ()
    # QUERIED catalog that fills this axis
    # (`services/catalog.py::queried_values`): the device or the virtual
    # machine do not come from looking at the open repo but from asking
    # the SDK; systemd services, from asking the repo's VPS. It resolves
    # like `discover`, but against that source and not the folder.
    source: str = ""
    # why the queried source did not answer, when what it said is what
    # has to be fixed (the repo's camera, ADR-0054). The panel fills it;
    # it wins over «there is none».
    query_error: str = ""
    # value -> how it reads. For the long lists of `expand='pick'`,
    # where the real value is an ugly id
    # (`system-images;android-36;google_apis;x86_64`) and what is chosen
    # is «Android 36 | Google APIs».
    labels: dict[str, str] = field(default_factory=dict)
    # only expand='field': a multi-line box, one value per line. For
    # short lists written by hand (the paths to copy): on one line one
    # cannot see where each ends.
    multiline: bool = False
    # only expand='field': leaving it empty is NOT a choice. Consola's
    # fields are almost all «empty = the function's default» (the
    # build's folder, the migration's message) so they do not block; the
    # URL of a repo to clone has no possible default, and without this
    # the button could be pressed to die on the task's first line.
    required: bool = False
    # only expand='field': 'int' when what is written is a number. A
    # field returns text and six parameters are integers (the backend's
    # port, the journal's lines, Cloudflare's TTL): without this the
    # panel passed '8000' to a function doing arithmetic with it. The
    # type is part of the axis's shape, so it is declared with it and
    # not fixed in the function.
    cast: str = ""
    # only select='one': values checked apart from the exclusive group
    # that stack with it ('build' in bump_mode: patch, minor, major and
    # none are exclusive, 'build' adds)
    combine: set[str] = field(default_factory=set)
    # only select='one': exclusive value checked at the start; empty =
    # the first not in `combine`
    default: str = ""
    # only select='one' of two values: which one means True. A two-way
    # segment ('dry_run'/'delete') is a boolean with two readable
    # labels: without this, whoever reads the payload has to compare the
    # string by hand and the catalog loses control of how its own axis
    # reads.
    truthy: str = ""
    # only with `combine`: how the exclusive value and the combined ones
    # join in the string the function expects
    join: str = ""
    # ('patch' + 'build' -> 'patch+build')
    requires_env: dict[str, set[str]] = field(
        default_factory=dict
        # value -> config.env keys choosing it requires. The `remote`
        # scope asks for the VPS's IP and key and `local` does not:
        # requiring them on the capability left a repo without a VPS's
        # local database amber.
    )

    facets: tuple[Facet, ...] = field(
        default_factory=tuple
        # only expand='pick': the features each value breaks into
        # (`Facet`). With this the panel draws one short list per
        # feature instead of a long one with all the combinations.
    )
    facet_sep: str = ";"  # what splits the value to get its features

    uses_env: dict[str, set[str]] = field(
        default_factory=dict
        # value -> config.env keys choosing it uses, without requiring
        # them. They only filter the settings panel: the web build's
        # folder has nothing to do on screen if Web is not checked.
    )

    def keys_for(self, chosen: Iterable[str]) -> set[str]:
        """Return the keys the chosen values require."""
        return set().union(*(self.requires_env.get(v, set()) for v in chosen))

    # --- features ---
    #
    # All that follows is pure logic on `values`: the panel only draws
    # what these four return, so the cascade can be read and tested
    # without an open window.

    def facet_of(self, value: str, facet: Facet) -> str:
        """Return what this feature says in this value."""
        parts = value.split(self.facet_sep)
        return parts[facet.part] if facet.part < len(parts) else ""

    def _upstream(self, name: str) -> list[Facet]:
        """Return the features declared BEFORE this one."""
        names = [f.name for f in self.facets]
        return list(self.facets[: names.index(name)]) if name in names else []

    def facet_values(self, facet: Facet, chosen: dict[str, str]) -> list[str]:
        """Return what this feature can take given what is chosen above.

        It is a cascade and not a cross filter: each list trims with
        those BEFORE it, never those below. So the order features are
        declared in is the order they are decided in: first the Android
        version, then which variant exists for it, then which
        architectures for that combination.

        Also trimming upward seems smarter and leaves the first list
        with no way out: with «Play Store» checked, versions not
        publishing it vanish from the versions list, and there is no way
        to reach them from the one control that should be able to change
        everything.

        Options keep the order of `values`, already sorted by what is
        almost always chosen: the first is the good default.
        """
        output: list[str] = []
        above = self._upstream(facet.name)
        for value in self.values:
            if any(
                chosen.get(f.name) and self.facet_of(value, f) != chosen[f.name] for f in above
            ):
                continue
            part = self.facet_of(value, facet)
            if part and part not in output:
                output.append(part)
        return output

    def resolve_facets(self, chosen: dict[str, str]) -> dict[str, str]:
        """Return what is chosen in each feature, corrected to exist.

        Changing one above can leave those below on an impossible value
        (no Wear OS on Android 36): they fall to their best available
        option instead of pointing at a combination the SDK does not
        publish. Those above are never touched, which makes the cascade
        predictable: what one just chose does not move by itself.
        """
        resolved: dict[str, str] = {}
        for facet in self.facets:
            options = self.facet_values(facet, resolved)
            current = chosen.get(facet.name, "")
            resolved[facet.name] = (
                current if current in options else (options[0] if options else "")
            )
        return resolved

    def value_for(self, chosen: dict[str, str]) -> str:
        """Return the catalog value that meets all the features."""
        return next(
            (
                v
                for v in self.values
                if all(self.facet_of(v, f) == chosen.get(f.name) for f in self.facets)
            ),
            "",
        )

    def facets_of(self, value: str) -> dict[str, str]:
        """Return what to mark, from a saved value: the reverse path."""
        return {f.name: self.facet_of(value, f) for f in self.facets}

    @property
    def exclusive_values(self) -> list[str]:
        """Return the values not in `combine`."""
        return [v for v in self.values if v not in self.combine]

    @property
    def initial(self) -> str:
        """Return the exclusive value that starts checked."""
        options = self.exclusive_values
        if self.default in options:
            return self.default
        return options[0] if options else ""

    @property
    def is_multi(self) -> bool:
        """Return whether it allows several values."""
        return self.select == "many"

    def starts_checked(self, value: str) -> bool:
        """Return whether this box starts checked.

        `defaults` wins over the flag.
        """
        if self.defaults:
            return value in self.defaults
        return self.checked_by_default

    @property
    def is_queried(self) -> bool:
        """Return whether its values come from asking.

        They come from the SDK or the VPS, not the catalog or the repo.
        """
        return bool(self.source)

    @property
    def query_place(self) -> str:
        """Return where what this axis lists lives.

        It is the phrase the panel explains an empty axis with: «no hay
        servicio en este VPS» says what to look at, and «en esta
        máquina» would send one to the wrong side.
        """
        if self.source.startswith("vps"):
            return QCoreApplication.translate("AxisDef", "en este VPS")
        # Backups are on this machine, but saying so would send one to
        # the SDK: what has to be looked at is the folder BACKUP_DIR
        # declares, which need not even be inside the repo.
        if self.source.startswith("backup"):
            return QCoreApplication.translate("AxisDef", "en la carpeta de respaldos")
        if self.source.startswith("shots"):
            return QCoreApplication.translate("AxisDef", "en la cámara del repo")
        # Apps are in the repo, but not all: only those that say where
        # their icon goes. «En este repo» would send one to look for an
        # app that is there.
        if self.source.startswith("icon"):
            return QCoreApplication.translate("AxisDef", "con ícono a cargo de Consola")
        if self.source.startswith("releases"):
            return QCoreApplication.translate("AxisDef", "firmado en GitHub")
        return QCoreApplication.translate("AxisDef", "en esta máquina")

    @property
    def is_discovered(self) -> bool:
        """Return whether its values come from looking at the open repo.

        They do not come from the catalog (ADR-0006). The catalog loads
        once at startup and the repo changes with the selector, so a
        discovered axis is declared empty here and
        `catalog.for_project()` fills it each time a panel builds.
        """
        return bool(self.discover) or bool(self.source)

    @property
    def display(self) -> str:
        """Return the label the panel shows."""
        return self.label or self.name.replace("_", " ").capitalize()

    def text_of(self, value: str) -> str:
        """Return how a value reads: its label, or the value as is."""
        return self.labels.get(value, value)


@dataclass
class Step:
    """A step of a composite capability, with its own checkbox.

    `optional=False` draws checked and disabled: a «Compilar ejecutable»
    without a build is not a variant but an error. Builders that let one
    uncheck compiling (APK, Vite) do so because a meaningful mode
    remains without it: uploading the artifact already on disk.
    """

    id: str
    label: str
    optional: bool = True
    default: bool = True
    requires_env: set[str] = field(default_factory=set)
    # repo feature without which the step does not exist
    # (`services/targets.py`: MIGRATIONS). It differs from
    # `requires_env`, which leaves the box in view in amber because what
    # is missing can be loaded: here no datum is missing but the object
    # to act on. A repo that does not version its schema does not have
    # «ejecutar migraciones» turned off, it does not have it.
    requires_repo: str = ""
    # The values of the `scope` axis where the step exists; empty, all.
    # Emptying the VPS's database is another act than deleting the local
    # tables, and with the other scope the step neither draws nor runs.
    scopes: frozenset[str] = frozenset()

    def applies(self, scope: str) -> bool:
        """Return whether the step exists with that scope."""
        return not self.scopes or scope in self.scopes


@dataclass
class Capability:
    """A registered capability.

    It generates ONE button in the rail; its variants and steps live in
    the parameters panel, not in duplicate rows.
    """

    id: str
    name: str
    group: str
    # 'live' | 'once' | 'destructive' | 'interactive' | 'background'
    kind: str
    axes: list[AxisDef] = field(default_factory=list)
    composed_of: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    icon: str = ""
    # one line: what the button does, in the tooltip and header
    description: str = ""
    level: str = ""  # 'A' | 'C'; empty = deduced from steps/composed_of
    scope: str = "repo"  # 'repo' | 'machine': ver `is_machine_wide`
    # atomic capability: it exists as a step, not a button in the menu,
    # a line right above this button. It is not a section with a dim
    # label: it has no name, groups nothing and nobody asks which
    # stretch a button belongs to. It declares an edge and nothing else,
    # where the menu stops speaking of one thing. The line of
    # destructive buttons is not declared here: it comes by itself from
    hidden: bool = False
    # `kind` (ADR-0043).
    cut: bool = False
    # the same as in `Step`, for the whole button: a capability whose
    # steps ALL need that feature does not stay empty, it disappears
    # (ADR-0007).
    requires_repo: str = ""
    # what the task delivers is a repo folder: the window opens it as a
    # tab at the end. It is all that has to be declared for cloning to
    # end where it should, without the interface knowing the cloning
    # button's id.
    opens_repo: bool = False
    # the tab's second view, besides the console: 'web' = embedded
    # browser pointed at the endpoint the task publishes with
    # `ctx.serve()`. A launcher's log is the by-product; it delivers a
    # URL (ADR-0008). 'db' = database explorer on the connection
    # `explore_db` publishes (ADR-0015).
    view: str = ""
    # only kind='live': name of the `select='many'` axis whose values do
    # NOT run in a loop but in one tab each. Checking panel + backoffice
    # is two live dev servers at once, not two steps in a row
    fanout: str = ""
    # (ADR-0010).
    # concurrent composite: its steps are capabilities launched in
    # parallel, one tab each, and none ends. It has no `func`: its body
    # is the interface's dispatcher, because «N tabs» means nothing in
    # `services/` (ADR-0011).
    concurrent: bool = False
    # inventory the panel shows as a status header, with a stop button
    # per row (`services/catalog.py::queried_values`). It replaces a
    # «stop emulator» button: what runs shows where one chooses, and
    # stops from there.
    live_state: str = ""
    # what running will do, shown on top of the parameters before
    # running: the packages canone installs for this repo
    # (`services/catalog.py::preview_lines`)
    preview: str = ""
    stub: bool = True
    func: Callable[..., Any] | None = None

    @property
    def multi_axes(self) -> list[AxisDef]:
        """Return the axes with several values."""
        return [a for a in self.axes if a.is_multi]

    @property
    def pick_axes(self) -> list[AxisDef]:
        """Return the long, closed list axes, chosen by searching.

        A catalog of a hundred devices or three hundred system images
        fits no checkboxes or segment, but it is no free text either,
        because the valid values are exactly those.
        """
        return [a for a in self.axes if a.expand == "pick"]

    @property
    def single_axes(self) -> list[AxisDef]:
        """Return the single-choice axes that draw as exclusive options.

        Those of `expand='field'` stay out: also single-valued, but the
        value is written (an install path, an API level) instead of
        chosen from a closed list.
        """
        return [a for a in self.axes if not a.is_multi and a.expand not in ("field", "pick")]

    @property
    def field_axes(self) -> list[AxisDef]:
        """Return the axes written by hand; `values[0]` is default."""
        return [a for a in self.axes if a.expand == "field"]

    @property
    def has_web_view(self) -> bool:
        """Return whether it has the browser view."""
        return self.view == "web"

    @property
    def has_db_view(self) -> bool:
        """Return whether it has the explorer view."""
        return self.view == "db"

    @property
    def is_composite(self) -> bool:
        """Return whether it chains several atomic capabilities.

        ADR-0004. Normally it shows by itself: declaring `steps` or
        `composed_of` makes it composite. But several real composites
        (`bootstrap_db`, `teardown_db`) do not publish their steps in
        the panel, and there the catalog says so with `level='C'`. What
        is explicit wins.
        """
        if self.level:
            return self.level.upper().startswith("C")
        return bool(self.steps or self.composed_of)

    @property
    def level_label(self) -> str:
        """Return the level's label."""
        return (
            QCoreApplication.translate("Capability", "Compuesta")
            if self.is_composite
            else QCoreApplication.translate("Capability", "Atómica")
        )

    def kwargs_from(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the function's kwargs from what the panel checked.

        No table per capability is needed, since the capability declares
        itself. The contract that allows this (ADR-0003) is that an
        axis's `name` and a step's `id` ARE the parameter's name; the
        label people read lives apart, in `label` and `labels`.

        Steps derived from `composed_of` do not enter: they document
        which buttons this one chains, not checkboxes with a boolean
        behind. Whoever wants a checkbox per step declares `steps=`.
        """
        checked = set(payload.get("steps") or ())
        kwargs = {axis.name: self._axis_value(axis, payload) for axis in self.axes}
        scope = kwargs.get("scope", "")
        kwargs.update({step.id: step.id in checked and step.applies(scope) for step in self.steps})
        return kwargs

    def _axis_value(self, axis: AxisDef, payload: dict[str, Any]) -> Any:
        """Return an axis's value, from the panel's bucket for it.

        `ParamsPanel.payload()` groups by control type and not meaning
        (`variants` the checkboxes, `options` the exclusive, `fields`
        the written, `picks` the long lists), so one has to know which
        each axis fell in, which is what its `expand` and `select` say.
        """
        if axis.expand == "field":
            # Empty is a valid choice: whoever cleared the field asks
            # for the function's default, not the catalog's.
            written = (payload.get("fields") or {}).get(axis.name, "")
            # A multi-line box IS a list: one value per line. The line
            # break separates it, not a comma that would have to be
            # explained next to the field.
            if axis.multiline:
                return [ln.strip() for ln in written.splitlines() if ln.strip()]
            if axis.cast == "int":
                # An empty field asks for the declared default, as
                # above: clearing the port means «the usual», not «port
                # zero».
                text = written.strip()
                return int(text) if text.lstrip("-").isdigit() else int(axis.values[0] or 0)
            return written
        if axis.expand == "pick":
            return (payload.get("picks") or {}).get(axis.name, "")
        if axis.is_multi:
            checked = list((payload.get("variants") or {}).get(axis.name) or ())
            # The `fanout` axis comes already split:
            # `TabPanel._run_fanout` opens one tab per value, so one
            # arrives here, not the list.
            if axis.name and axis.name == self.fanout:
                return checked[0] if checked else ""
            return checked
        raw = (payload.get("options") or {}).get(axis.name)
        if axis.combine:
            # A `combine` axis can bring two marks (`['patch',
            # 'build']`). The catalog sets the string's order, not the
            # order the panel returned them in: first the exclusive,
            # then the combined.
            checked = [raw] if isinstance(raw, str) else list(raw or ())
            base = next((v for v in checked if v not in axis.combine), axis.initial)
            extra = [v for v in axis.values if v in axis.combine and v in checked]
            return axis.join.join([base, *extra]) if axis.join else base
        # Absent or empty = the axis did not draw (a preset saved before
        # it existed, or a repo with one value to discover): the
        # declared default holds, what the panel would have shown.
        value = raw or axis.initial
        return value == axis.truthy if axis.truthy else value

    def applies_to(self, features: Collection[str]) -> bool:
        """Return whether it fits a repo with those features."""
        return not self.requires_repo or self.requires_repo in features

    def steps_for(self, features: Collection[str]) -> list[Step]:
        """Return the steps left in a repo with those features."""
        return [s for s in self.steps if not s.requires_repo or s.requires_repo in features]

    @property
    def is_machine_wide(self) -> bool:
        """Return whether it happens to the machine, not the open repo.

        Installing an SDK is no repository's decision: the chosen folder
        holds for all. So its parameters save once
        (`services/params_store.py`) instead of per repo, and the action
        does not depend on an open project.
        """
        return self.scope == "machine"


GROUP_ICONS = {
    "Ejecutar": "🚀",
    "Compilar": "🔨",
    "Imágenes": "🖼️",
    "Repositorio": "🐙",
    "Base de datos": "🗄️",
    "Despliegue": "🖥️",
    "VPS": "🔧",
    "Emuladores": "📱",
    "SDKs": "🧰",
}


class Registry:
    """The global registry of capabilities."""

    def __init__(self) -> None:
        """Start empty."""
        self._capabilities: dict[str, Capability] = {}
        self._group_order: list[str] = []

    def register(self, cap: Capability) -> None:
        """Register a capability."""
        if cap.group and cap.group not in self._group_order:
            self._group_order.append(cap.group)
        self._capabilities[cap.id] = cap

    def bind(self, cap_id: str, func: Callable[..., Any]) -> Callable[..., Any]:
        """Give a real body to a capability declared in the catalog.

        The catalog (`services/catalog.py`) declares the shape: group,
        axes, steps. `services/tasks/` implements it. While nobody calls
        `bind`, the capability stays a stub and the UI draws it as one.
        """
        cap = self._capabilities.get(cap_id)
        if cap is None:
            raise KeyError(f"No capability is registered with id {cap_id!r}")
        cap.func = func
        cap.stub = False
        return func

    def implemented(self) -> list[Capability]:
        """Return the capabilities that are not stubs."""
        return [c for c in self._capabilities.values() if not c.stub]

    def get_all(self) -> list[Capability]:
        """Return all capabilities."""
        return list(self._capabilities.values())

    def get_groups(self, include_hidden: bool = False) -> dict[str, list[Capability]]:
        """Return the capabilities by group."""
        groups: dict[str, list[Capability]] = {group: [] for group in self._group_order}
        for cap in self._capabilities.values():
            if cap.hidden and not include_hidden:
                continue
            if cap.group in groups:
                groups[cap.group].append(cap)
        return {g: caps for g, caps in groups.items() if caps}

    def get_capability(self, cap_id: str) -> Capability | None:
        """Return the capability with that id."""
        return self._capabilities.get(cap_id)

    def get_group_icon(self, group: str) -> str:
        """Return the group's icon."""
        return GROUP_ICONS.get(group, "")

    def resolve_steps(self, cap: Capability) -> list[Step]:
        """Return a capability's steps: those declared, or itself.

        `composed_of` does NOT derive steps. It documents which buttons
        this one is made of, and its entries are CAPABILITY ids, which
        never match a parameter's name (ADR-0003).

        Whoever wants a checkbox per step declares it. Without `steps`,
        the capability is one required step and the panel does not draw
        the section.
        """
        return cap.steps or [Step(cap.id, cap.name, optional=False)]


# Module-level singleton
registry = Registry()

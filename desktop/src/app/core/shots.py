"""Publishable screenshots: the repo camera's contract and development.

The camera is a script of the repo (ADR-0049): Consola runs it with the
selection as arguments and then reads what it left. Everything that is
not running processes lives here: where raw shots go, what they are
called, what the script receives and how each raw shot converts for each
destination.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import targets
from app.core.errors import TaskError

THEMES = ("claro", "oscuro")

# The app types that can be photographed: what has a screen. The server
# and desktop apps stay out until someone needs them.
SHOT_KINDS = (targets.SPA_VITE, *targets.MOBILE_APP)

# <app>/<screen>.<theme>.<language>.png. All four segments are required:
# a name that does not fit is not guessed, it stops the development.
_RAW_NAME = re.compile(r"^(?P<screen>[^.]+)\.(?P<theme>[^.]+)\.(?P<language>[^.]+)\.png$")

PRESETS_FILE = Path(__file__).with_name("shots_presets.json")
# The plumbing cameras share (ADR-0051). It travels in `--kit`.
KIT = Path(__file__).resolve().parents[1] / "camera" / "index.mjs"
MANIFEST = "capturas.json"


@dataclass(frozen=True)
class Shot:
    """A raw screenshot, already read from its name."""

    app: str
    kind: str
    screen: str
    theme: str
    language: str
    path: Path

    @property
    def stem(self) -> str:
        """Return the name without its extension."""
        return f"{self.screen}.{self.theme}.{self.language}"


def resolve_dir(root: Path, value: str) -> Path:
    """Return a config folder.

    Relative hangs from the repo, absolute stays.
    """
    declared = Path(value)
    return declared if declared.is_absolute() else root / declared


def camera_args(
    apps: Iterable[str],
    themes: Iterable[str],
    languages: Iterable[str],
    output: Path,
    device: str = "",
) -> list[str]:
    """Return the arguments Consola adds to `SHOTS_CMD`.

    ADR-0049 and ADR-0051.
    """
    args = [
        "--apps",
        ",".join(apps),
        "--themes",
        ",".join(themes),
        "--languages",
        ",".join(languages),
        "--output",
        str(output),
        "--kit",
        str(KIT),
    ]
    if device:
        args += ["--device", device]
    return args


def parse_supported(text: str) -> dict[str, dict[str, Any]]:
    """Return what the camera says it can capture, from `--supported`.

    The kit checks it before printing it (ADR-0054); this checks what
    Consola uses from it, because a camera written without the kit can
    also answer.
    """
    try:
        declared = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TaskError(f"La cámara no contestó JSON a --supported: {text[:200]!r}") from exc
    if not isinstance(declared, dict) or not declared:
        raise TaskError("La cámara no declara ninguna app.")
    for app, spec in declared.items():
        themes = spec.get("themes") if isinstance(spec, dict) else None
        languages = spec.get("languages") if isinstance(spec, dict) else None
        if (
            not themes
            or not isinstance(themes, list)
            or not languages
            or not isinstance(languages, list)
        ):
            raise TaskError(f"La cámara declara {app} sin temas o sin idiomas.")
        foreign = [t for t in themes if t not in THEMES]
        if foreign:
            raise TaskError(
                f"La cámara declara para {app} temas fuera del contrato: {', '.join(foreign)}."
            )
    return declared


def supported_values(declared: dict[str, dict[str, Any]], axis: str) -> list[str]:
    """Return the values of a camera axis.

    Its apps, or all the themes or languages any has. Themes in the
    contract's order; the rest as the camera wrote it.
    """
    if axis == "apps":
        return list(declared)
    seen = [v for spec in declared.values() for v in spec[axis]]
    if axis == "themes":
        return [t for t in THEMES if t in seen]
    return list(dict.fromkeys(seen))


def clear_raw(
    raw: Path, apps: Iterable[str], themes: Iterable[str], languages: Iterable[str]
) -> int:
    """Delete the raw shots of the combinations about to be taken again.

    Without this, a screen the script stopped capturing would stay in
    the folder and the development would publish it as new. Only the
    requested combinations are touched: taking English does not delete
    Spanish.
    """
    deleted = 0
    for app in apps:
        for theme in themes:
            for language in languages:
                for old in (raw / app).glob(f"*.{theme}.{language}.png"):
                    old.unlink()
                    deleted += 1
    return deleted


def collect(root: Path, raw: Path, apps: Iterable[str] | None = None) -> list[Shot]:
    """Return the validated raw shots. `apps` limits to those folders.

    It stops with an error on a folder that is not an app of the repo or
    a file outside the agreed name: half a development would leave the
    landing with a mix of runs.
    """
    if not raw.is_dir():
        raise TaskError(f"No existe la carpeta de capturas crudas: {raw}")
    kinds = {t.name: t.kind for t in targets.by_kinds(root, SHOT_KINDS)}
    folders = (
        [raw / a for a in apps]
        if apps is not None
        else sorted(p for p in raw.iterdir() if p.is_dir())
    )

    shots: list[Shot] = []
    for folder in folders:
        if folder.name not in kinds:
            raise TaskError(
                f"{folder} no corresponde a ninguna app del repo "
                f"({', '.join(sorted(kinds)) or 'no hay ninguna'})."
            )
        if not folder.is_dir():
            continue
        for file in sorted(folder.iterdir()):
            name = _RAW_NAME.match(file.name)
            if not file.is_file() or name is None:
                raise TaskError(f"{file} no sigue el nombre <pantalla>.<tema>.<idioma>.png.")
            if name["theme"] not in THEMES:
                raise TaskError(f'{file}: el tema "{name["theme"]}" no es {" ni ".join(THEMES)}.')
            shots.append(
                Shot(
                    app=folder.name,
                    kind=kinds[folder.name],
                    screen=name["screen"],
                    theme=name["theme"],
                    language=name["language"],
                    path=file,
                )
            )
    return shots


def missing_combinations(
    shots: list[Shot], apps: Iterable[str], themes: Iterable[str], languages: Iterable[str]
) -> list[str]:
    """Return the requested combinations the camera left no shot for."""
    done = {(s.app, s.theme, s.language) for s in shots}
    return [
        f"{a} · {t} · {lang}"
        for a in apps
        for t in themes
        for lang in languages
        if (a, t, lang) not in done
    ]


def load_presets() -> dict[str, Any]:
    """Return the destinations' presets."""
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def render_landing(shot: Shot, preset: dict[str, Any], out_dir: Path) -> "Derived":
    """Turn a raw shot into the landing's .webp, never enlarging it.

    The preset's width is a cap: a narrower shot stays as is, because
    enlarging it only blurs it.
    """
    from PIL import Image

    widths = preset["max_width"]
    if shot.kind not in widths:
        raise TaskError(
            f"El preset de la landing no tiene ancho para {shot.kind} ({PRESETS_FILE.name})."
        )
    target = out_dir / shot.app / f"{shot.stem}.webp"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(shot.path) as image:
        cap = widths[shot.kind]
        if image.width > cap:
            height = round(image.height * cap / image.width)
            image = image.resize((cap, height), Image.Resampling.LANCZOS)
        image.save(target, "WEBP", quality=preset["quality"])
        return Derived(shot, "landing", target, image.width, image.height)


@dataclass(frozen=True)
class Derived:
    """A file the development left, with what the manifest needs."""

    shot: Shot
    destination: str
    path: Path
    width: int
    height: int
    # the ZIP that holds it, if the destination is an archive
    archive: str = ""


def aspect_crop(width: int, height: int, target_w: int, target_h: int) -> float:
    """Return the image fraction lost going to the target proportion."""
    current, target = width / height, target_w / target_h
    return 1 - min(current, target) / max(current, target)


def plan(
    destination: str, preset: dict[str, Any], raws: list[Shot]
) -> list[tuple[Shot, dict[str, Any] | None]]:
    """Return the (raw shot, size) pairs of a destination.

    `None` is the native size.

    - `kinds` says which raw shots the destination takes: a desktop shot
      does not become a phone one.
    - `limits` (Play) does not change the size: the raw shot has to meet
      them.
    - `sizes` are exact sizes. Each raw shot goes to those whose
      proportion it reaches cropping at most `max_crop`; so a phone goes
      to iPhone's and a tablet to iPad's without the contract saying
      which is which.

    It stops if no raw shot suits the destination, or if one fits no
    size: cropping too much eats the app's bar or navigation.
    """
    from PIL import Image

    kinds = preset.get("kinds")
    own = [s for s in raws if not kinds or s.kind in kinds]
    if not own:
        raise TaskError(
            f"{destination}: ninguna captura es de un tipo que le sirva "
            f"({', '.join(kinds or ())})."
        )
    if "sizes" not in preset and "limits" not in preset:
        return [(s, None) for s in own]

    pairs: list[tuple[Shot, dict[str, Any] | None]] = []
    outside: list[str] = []
    for shot in own:
        with Image.open(shot.path) as image:
            width, height = image.size
        if "limits" in preset:
            fails = _outside_limits(width, height, preset["limits"])
            if fails:
                outside.append(f"{shot.app}/{shot.stem} ({width}×{height}): {fails}")
            else:
                pairs.append((shot, None))
            continue
        fit = [
            m
            for m in preset["sizes"]
            if (not m.get("kinds") or shot.kind in m["kinds"])
            and aspect_crop(width, height, m["width"], m["height"]) <= preset["max_crop"]
        ]
        if not fit:
            sizes = ", ".join(f"{m['width']}×{m['height']}" for m in preset["sizes"])
            outside.append(
                f"{shot.app}/{shot.stem} ({width}×{height}) no llega a {sizes} "
                f"recortando como mucho {preset['max_crop']:.0%}"
            )
        pairs.extend((shot, m) for m in fit)
    if outside:
        raise TaskError(
            f"{destination}: capturas que no sirven tal como se sacaron. "
            "Sácalas con un dispositivo de otra proporción o desmarca el "
            "destino.\n  " + "\n  ".join(outside)
        )
    return pairs


def _outside_limits(width: int, height: int, limits: dict[str, Any]) -> str:
    short, length = sorted((width, height))
    if short < limits["min_side"]:
        return f"el lado corto es menor que {limits['min_side']} px"
    if length > limits["max_side"]:
        return f"el lado largo pasa de {limits['max_side']} px"
    if length > short * limits["max_ratio"]:
        return f"la proporción {length / short:.2f}:1 pasa de {limits['max_ratio']}:1"
    return ""


def render_sized(
    shot: Shot, size: dict[str, Any] | None, out_dir: Path, destination: str
) -> Derived:
    """Turn a raw shot into a PNG without alpha, native or exact-sized.

    Stores reject PNGs with alpha. With a size, it scales until covering
    it (here it does enlarge: the size is exact) and crops the excess
    from the center, which `plan` already limited to `max_crop`.
    """
    from PIL import Image

    with Image.open(shot.path) as original:
        image = original.convert("RGB")
    if size is None:
        name = f"{shot.screen}.{shot.theme}.png"
    else:
        width, height = size["width"], size["height"]
        scale = max(width / image.width, height / image.height)
        image = image.resize(
            (max(width, round(image.width * scale)), max(height, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        left = (image.width - width) // 2
        above = (image.height - height) // 2
        image = image.crop((left, above, left + width, above + height))
        name = f"{shot.screen}.{shot.theme}.{size['name']}.png"
    # Stores group by language: one batch per language folder.
    target = out_dir / shot.language / shot.app / name
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG", optimize=True)
    return Derived(shot, destination, target, image.width, image.height)


def render_archive(raws: list[Shot], out_dir: Path, destination: str) -> list[Derived]:
    """Pack the raw shots as they are, uncompressed, in a ZIP.

    Press kit.
    """
    from PIL import Image

    file = out_dir / "capturas.zip"
    file.parent.mkdir(parents=True, exist_ok=True)
    derived = []
    with zipfile.ZipFile(file, "w", zipfile.ZIP_STORED) as zip_:
        for shot in raws:
            member = f"{shot.app}/{shot.stem}.png"
            zip_.write(shot.path, member)
            with Image.open(shot.path) as image:
                derived.append(
                    Derived(shot, destination, file, image.width, image.height, archive=member)
                )
    return derived


@dataclass(frozen=True)
class Changes:
    """What changed between a destination's old manifest.

    And the new one.
    """

    changed: list[str]
    added: list[str]
    removed: list[str]


def write_manifest(out_dir: Path, destination: str, derived: list[Derived]) -> Changes:
    """Write the destination's `capturas.json` and say what changed.

    The landing and the manual index it instead of writing paths by
    hand. Undated and sorted: two equal runs give the same file, and
    comparing each entry's hash with the last run's is the visual
    regression.
    """
    items = []
    for d in derived:
        item = {
            "app": d.shot.app,
            "screen": d.shot.screen,
            "theme": d.shot.theme,
            "language": d.shot.language,
            "file": d.path.relative_to(out_dir).as_posix(),
            "width": d.width,
            "height": d.height,
            "sha256": hashlib.sha256(
                (d.shot.path if d.archive else d.path).read_bytes()
            ).hexdigest(),
        }
        if d.archive:
            item["member"] = d.archive
        items.append(item)
    items.sort(key=lambda i: (i["app"], i["screen"], i["theme"], i["language"], i["file"]))

    output = out_dir / MANIFEST
    before = (
        {_entry(i): i["sha256"] for i in json.loads(output.read_text(encoding="utf-8"))["items"]}
        if output.is_file()
        else {}
    )
    now = {_entry(i): i["sha256"] for i in items}
    output.write_text(
        json.dumps({"destination": destination, "items": items}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return Changes(
        changed=sorted(k for k in now.keys() & before.keys() if now[k] != before[k]),
        added=sorted(now.keys() - before.keys()),
        removed=sorted(before.keys() - now.keys()),
    )


def _entry(item: dict[str, Any]) -> str:
    return item.get("member") or item["file"]

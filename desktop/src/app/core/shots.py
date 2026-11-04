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

"""
Capturas publicables: el contrato con la camara del repo y el revelado.

La camara es un script del repo (ADR-0049): Consola lo corre con la seleccion
como argumentos y despues lee lo que dejo. Aca vive todo lo que no es correr
procesos: donde van los crudos, como se llaman, que se le pasa al script y como
se convierte cada crudo para cada destino.
"""

THEMES = ("claro", "oscuro")

# Los tipos de app que se pueden fotografiar: lo que tiene pantalla. El servidor
# y las apps de escritorio quedan fuera hasta que alguien las necesite.
SHOT_KINDS = (targets.SPA_VITE, *targets.MOBILE_APP)

# <app>/<pantalla>.<tema>.<idioma>.png. Los cuatro segmentos son obligatorios:
# un nombre que no calza no se adivina, corta el revelado.
_RAW_NAME = re.compile(r"^(?P<screen>[^.]+)\.(?P<theme>[^.]+)\.(?P<language>[^.]+)\.png$")

PRESETS_FILE = Path(__file__).with_name("shots_presets.json")
# La plomeria que comparten las camaras (ADR-0051). Viaja en `--kit`.
KIT = Path(__file__).resolve().parents[1] / "camara" / "index.mjs"
MANIFEST = "capturas.json"


@dataclass(frozen=True)
class Shot:
    """Una captura cruda, ya leida de su nombre."""

    app: str
    kind: str
    screen: str
    theme: str
    language: str
    path: Path

    @property
    def stem(self) -> str:
        return f"{self.screen}.{self.theme}.{self.language}"


def resolve_dir(root: Path, value: str) -> Path:
    """Una carpeta de la configuracion: relativa cuelga del repo, absoluta va tal cual."""
    declared = Path(value)
    return declared if declared.is_absolute() else root / declared


def camera_args(
    apps: Iterable[str],
    themes: Iterable[str],
    languages: Iterable[str],
    output: Path,
    device: str = "",
) -> list[str]:
    """Los argumentos que Consola le agrega a `SHOTS_CMD` (ADR-0049, ADR-0051)."""
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
    """Lo que la camara dice que sabe capturar, leido de su `--supported` (ADR-0054).

    El kit ya lo revisa antes de imprimirlo; esto revisa lo que Consola usa de
    ahi, porque una camara escrita sin el kit tambien puede contestar.
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
    """Los valores de un eje de la camara: sus apps, o todos los temas o idiomas
    que tiene alguna. Los temas en el orden del contrato; lo demas, como lo
    escribio la camara.
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
    """Borra los crudos de las combinaciones que se van a volver a sacar.

    Sin esto, una pantalla que el script dejo de capturar seguiria en la
    carpeta y el revelado la publicaria como si fuera nueva. Solo se tocan las
    combinaciones pedidas: sacar el ingles no borra el espanol.
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
    """Las capturas crudas, validadas. `apps` limita a esas carpetas.

    Corta con error ante una carpeta que no es una app del repo o un archivo
    que no sigue el nombre acordado: revelar a medias dejaria la landing con
    una mezcla de corridas.
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
    """Las combinaciones pedidas para las que la camara no dejo ninguna captura."""
    done = {(s.app, s.theme, s.language) for s in shots}
    return [
        f"{a} · {t} · {l}"
        for a in apps
        for t in themes
        for l in languages
        if (a, t, l) not in done
    ]


def load_presets() -> dict[str, Any]:
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def render_landing(shot: Shot, preset: dict[str, Any], out_dir: Path) -> "Derived":
    """Un crudo -> el .webp de la landing, sin agrandarlo nunca.

    El ancho del preset es un tope: una captura mas angosta que el se deja
    como esta, porque agrandarla solo la desenfoca.
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
    """Un archivo que dejo el revelado, con lo que el manifiesto necesita."""

    shot: Shot
    destination: str
    path: Path
    width: int
    height: int
    archive: str = ""  # el ZIP que lo contiene, si el destino es un archivo


def aspect_crop(width: int, height: int, target_w: int, target_h: int) -> float:
    """La fraccion de la imagen que se pierde al llevarla a la proporcion destino."""
    current, target = width / height, target_w / target_h
    return 1 - min(current, target) / max(current, target)


def plan(
    destination: str, preset: dict[str, Any], raws: list[Shot]
) -> list[tuple[Shot, dict[str, Any] | None]]:
    """Los pares (crudo, medida) que produce un destino; `None` es la medida nativa.

    - `kinds` dice de que crudos sale el destino: una captura de escritorio no
      se convierte en una de telefono.
    - `limits` (Play) no cambia la medida: el crudo tiene que cumplirlos.
    - `sizes` son medidas exactas. Cada crudo va a las medidas cuya proporcion
      se alcanza recortando como mucho `max_crop`; asi un telefono va a la de
      iPhone y una tablet a la de iPad sin que el contrato diga que es cada uno.

    Corta si al destino no le sirve ningun crudo, o si un crudo no cabe en
    ninguna medida: recortar de mas se come la barra o la navegacion de la app.
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
    """Un crudo -> un PNG sin canal alfa, nativo o de la medida exacta del destino.

    Las tiendas rechazan PNG con alfa. Con medida, se escala hasta cubrirla
    (aqui si se agranda: la medida es exacta) y se recorta del centro lo que
    sobra, que `plan` ya limito a `max_crop`.
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
    # Las tiendas agrupan por idioma: una tanda por carpeta de idioma.
    target = out_dir / shot.language / shot.app / name
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG", optimize=True)
    return Derived(shot, destination, target, image.width, image.height)


def render_archive(raws: list[Shot], out_dir: Path, destination: str) -> list[Derived]:
    """Los crudos, tal cual y sin comprimir, en un ZIP (press kit)."""
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
    """Lo que cambio entre el manifiesto anterior de un destino y el nuevo."""

    changed: list[str]
    added: list[str]
    removed: list[str]


def write_manifest(out_dir: Path, destination: str, derived: list[Derived]) -> Changes:
    """Escribe `capturas.json` del destino y dice que cambio respecto del anterior.

    Es lo que la landing y el manual indexan en vez de escribir rutas a mano.
    Sin fecha y ordenado: dos corridas iguales dan el mismo archivo, y comparar
    el hash de cada entrada con el de la corrida anterior es la regresion visual.
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

from __future__ import annotations
from dataclasses import dataclass, field

"""
Descripciones largas de los comandos, para la seccion de ayuda del panel derecho.

La `description` de una `Capability` es una linea — lo justo para el tooltip del
rail y la cabecera. Aca vive el texto largo: que hace el comando, cuando usarlo y
que pasos ejecuta en orden. Es opcional: un comando sin entrada aca cae en su
descripcion de una linea hasta que se le escriba la suya.

Por ahora solo `build_apk`. El resto se ira sumando cuando haga falta.
"""


@dataclass(frozen=True)
class CommandDoc:
    summary: str                                     # que hace y cuando usarlo
    steps: list[str] = field(default_factory=list)   # que ejecuta, en orden
    notes: list[str] = field(default_factory=list)   # advertencias / casos borde


DOCS: dict[str, CommandDoc] = {
    'build_apk': CommandDoc(
        summary=(
            'Publica una versión nueva de una app móvil del repo: le sube el '
            'número de versión, compila el APK y, si se marca, lo deja subido al '
            'VPS junto con su manifiesto para que el instalador lo vea.\n\n'
            'Un solo botón para Flutter y para Flet — el framework sale de la '
            'carpeta de la app, no se elige. Si el repo tiene una sola app '
            'móvil, el selector «App móvil» ni se dibuja.'
        ),
        steps=[
            'Bump versión — sube el número en pubspec.yaml / pyproject.toml '
            'según el modo elegido (patch, minor, major, +build o ninguno). '
            'El manifiesto se toca de forma reversible: si algo falla después, '
            'la versión vuelve a lo que era.',
            'Compilar APK — build de Flutter o Flet sobre esa app. Resuelve '
            'dependencias solo, sin un paso de pub get aparte. Paso '
            'desmarcable: sin él, se toma el APK que ya está en disco (para '
            'retomar una subida cortada sin repetir diez minutos de build).',
            'Subir al VPS — copia el APK y su manifiesto al servidor por SSH. '
            'Desmarcado por defecto: solo corre si se pide explícitamente.',
        ],
        notes=[
            'El modo +build solo aplica a Flutter (pubspec.yaml). En una app '
            'Flet falla con ese mensaje.',
            'Sin compilar y sin subir no hay nada que hacer: la corrida se '
            'rechaza.',
            'Subir sin compilar ignora el bump: el APK en disco ya tiene su '
            'versión y anunciarlo con otra sería mentir sobre qué se instala.',
        ],
    ),
}


def get(capability_id: str) -> CommandDoc | None:
    return DOCS.get(capability_id)

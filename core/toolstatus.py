from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from . import android
from .errors import TaskError
from .process import which_any

"""
Que herramientas de desarrollo tiene esta maquina, mirando el disco.

Alimenta los indicadores de la barra de estado. Es a proposito la version
barata de la pregunta: solo comprueba que el binario exista y donde, sin
lanzar `java -version` ni `flutter doctor`. Preguntarselo a cada herramienta
cuesta segundos y bloquearia la interfaz cada vez que se refresca; y para lo
que el indicador tiene que decir —esta o no esta— alcanza con el archivo.

Por eso tampoco hay un boton de "estado del entorno": esto se chequea solo al
abrir el espacio de trabajo y despues de cada instalacion, no cuando alguien
se acuerda de apretarlo.
"""


@dataclass(frozen=True)
class Tool:
    """Una herramienta buscada, con el resultado de la busqueda."""
    key: str
    label: str
    path: str = ''    # vacio = no se encontro
    hint: str = ''    # que hacer al respecto, para el tooltip

    @property
    def found(self) -> bool:
        return bool(self.path)

    @property
    def detail(self) -> str:
        return self.path if self.found else (self.hint or 'No encontrado.')


def _binary(name: str) -> list[str]:
    """Los nombres que puede tener un ejecutable segun el sistema."""
    if os.name != 'nt':
        return [name]
    return [f'{name}.exe', f'{name}.bat', f'{name}.cmd']


def _under(home: str, *parts: str) -> str:
    """Busca el ejecutable dentro de un directorio declarado por variable.

    Se mira antes que el PATH porque una instalacion recien hecha escribe la
    variable en el mismo momento que la ruta, y asi el indicador se pone en
    verde sin que haga falta reiniciar Consola.
    """
    raiz = (os.environ.get(home) or '').strip()
    if not raiz:
        return ''
    for nombre in _binary(parts[-1]):
        candidato = Path(raiz).joinpath(*parts[:-1], nombre)
        if candidato.is_file():
            return str(candidato)
    return ''


def _java() -> Tool:
    ruta = _under('JAVA_HOME', 'bin', 'java') or (which_any(_binary('java')) or '')
    return Tool('java', 'Java', ruta,
                hint='Instala un JDK 17 o superior: sdkmanager no corre sin el.')


def _git() -> Tool:
    return Tool('git', 'Git', which_any(_binary('git')) or '',
                hint='Flutter necesita Git para actualizarse.')


def _android() -> Tool:
    try:
        ruta = android.resolve_sdk().tool('sdkmanager')
    except TaskError:
        ruta = ''
    return Tool('android', 'SDK Android', ruta,
                hint='Corre "Herramientas Android" para instalarlo.')


def _flutter() -> Tool:
    ruta = _under('FLUTTER_HOME', 'bin', 'flutter') or (which_any(_binary('flutter')) or '')
    return Tool('flutter', 'Flutter', ruta,
                hint='Corre "SDK Flutter" para instalarlo.')


def detect() -> list[Tool]:
    """El estado de las cuatro herramientas, en el orden en que dependen entre si."""
    return [_java(), _git(), _android(), _flutter()]

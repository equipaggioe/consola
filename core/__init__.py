from __future__ import annotations

"""Nivel 0 de Consola: la plomeria que usan por dentro las capacidades.

Nada de esto es un boton. Cada modulo resuelve una sola clase de problema y no
importa Qt, no imprime a stdout, no lee de stdin y no sale del proceso: informa
por el `TaskContext` que recibe y levanta `TaskError` cuando no puede seguir
(PLAN.md 2.1).

    errors      TaskError, Cancelled, MissingConfig
    context     TaskContext: log, run, confirm, ask, note, cancelacion
    process     ejecutar binarios externos: streaming, captura, matar el arbol
    envfile     .consola/config.env: leer, escribir y acceso tipado (Config)
    settings    esquema de claves de configuracion
    files       comparar, copiar, borrar y revertir archivos
    ports       elegir un puerto libre
    ssh         Remote, comandos remotos, scp, tuneles, llaves
    vps         rutas del despliegue, systemd, journal, paquetes
    database    resolver la base local o la remota por tunel (eje scope)
    runner      donde corre el codigo del proyecto: venv de aca o venv del VPS
    versioning  leer y subir la version de un manifiesto
    github      llaves SSH de la cuenta de GitHub
    toolchain   flutter, flet, npm, venv y deteccion de framework
    android     SDK, AVDs, system images y emuladores
    targets     descubrir subproyectos dentro del repo abierto
    registry    catalogo de capacidades
    projects    el dataclass Project (la lista la maneja la UI)
"""

from .errors import Cancelled, MissingConfig, TaskError
from .context import Level, TaskContext
from .envfile import Config
from .projects import Project
from .registry import AxisDef, Capability, Registry, Step, registry
from .ssh import Remote

__all__ = [
    'Cancelled', 'MissingConfig', 'TaskError',
    'Level', 'TaskContext', 'Config',
    'Project',
    'Registry', 'registry', 'Capability', 'AxisDef', 'Step',
    'Remote',
]

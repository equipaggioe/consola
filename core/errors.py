from __future__ import annotations


class TaskError(RuntimeError):
    """Falla esperable de una capacidad: marca la pestana en rojo, no tumba la app.

    Reemplaza el `print("[ERROR] ...") + raise SystemExit(1)` que repetian todos
    los scripts. Nivel 0 nunca imprime ni sale del proceso: informa y devuelve.
    """


class Cancelled(RuntimeError):
    """El usuario detuvo la tarea. No es un error: la pestana queda gris, no roja."""


class MissingConfig(TaskError):
    """Faltan claves de `.consola/config.env` para poder correr.

    Se distingue de TaskError comun para que la UI pueda ofrecer el engranaje
    de Configuracion filtrado a `keys` en vez de un mensaje suelto (PLAN.md §9).
    """

    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)
        faltan = ', '.join(self.keys)
        super().__init__(f"Falta configurar: {faltan}")

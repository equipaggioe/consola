# Consola

Aplicación de escritorio (PySide6) que ejecuta las operaciones de desarrollo y despliegue de los repositorios que se le abren como pestañas. Arranca con `python main.py`.

## Documentación

- `docs/` sigue `docs/README.md`: `arquitectura/` (cómo es hoy; pendientes en el documento 30),
  `adr/` (por qué) y `planes/` (solo trabajo sin terminar).
- Antes de afirmar que algo está hecho o pendiente, verificarlo contra el código.
- No crear bitácoras, registros de cambios ni planes terminados.
- Un cambio de comportamiento actualiza `arquitectura/` en el mismo commit; una decisión nueva es un ADR nuevo.
- Solo se escribe `Aceptada` cuando la decisión se confirmó explícitamente.
- Nunca borrar un plan que tenga trabajo pendiente.

Orden de lectura para ubicarse: [`docs/arquitectura/README.md`](docs/arquitectura/README.md).

## Reglas del código

- **El nombre de un eje y el id de un paso son el nombre del parámetro de la función** ([ADR-0003](docs/adr/0003-contrato-de-nombres.md)). No hay capa que traduzca.
- **`core/` no importa Qt, no imprime, no lee stdin y no sale del proceso**: informa por el `TaskContext` y levanta `TaskError` ([ADR-0005](docs/adr/0005-todo-pasa-por-taskcontext.md)).
- **El único `subprocess` es a un binario externo real.** Nada invoca otro script de Consola ([ADR-0001](docs/adr/0001-reimplementar-no-ejecutar-scripts.md)).
- **Datos en `.consola/config.env`, decisiones en `.consola/params.json`, lo de la máquina en QSettings** ([ADR-0017](docs/adr/0017-datos-en-el-env-decisiones-en-el-json.md)).
- Una capacidad destructiva declara qué rompe en `core/protection.py::RULES` ([ADR-0018](docs/adr/0018-seguro-por-repo-y-objetivo.md)).
- Un comentario que explica un porqué cita su ADR (`# ADR-0010: una pestaña por dev server`), nunca un plan ni un número de apartado de la arquitectura.
- El código y los mensajes están en español. `scripts/` es la especificación de los scripts originales: no se ejecuta ni se importa.

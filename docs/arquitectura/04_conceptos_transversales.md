# 04 · Conceptos transversales

Reglas que valen para todo el código, no para un dominio. Cada una se puede comprobar en el archivo que la nombra.

## 1. El nivel 0 no habla con nadie más que con su contexto

Nada de `core/` (fuera de `core/tasks/`) importa Qt, imprime a stdout, lee de stdin ni sale del proceso. Informa por el `TaskContext` que recibe y levanta `TaskError` cuando no puede seguir. Es lo que permite que la misma función sirva para la consola de una pestaña, para un paso interno de una compuesta y para un test sin ventana ([ADR-0005](../adr/0005-todo-pasa-por-taskcontext.md)).

- `print` + `SystemExit(1)` se reemplazó por `TaskError` (`core/errors.py`).
- `input()` se reemplazó por `ctx.ask` / `ctx.confirm`, que abren el diálogo que corresponde.
- `subprocess.run` se reemplazó por `ctx.run` / `ctx.capture`, que transmiten en vivo y atienden la cancelación.

## 2. El único `subprocess` es a un binario externo real

`flutter`, `npm`, `git`, `ssh`, `scp`, `adb`, `emulator`, `sdkmanager`, `psql`, `pyinstaller`, `uvicorn`. Ninguna capacidad lanza otro script de Consola como proceso: si necesita lo que hace otra, la llama como función con `ctx.child(...)` ([ADR-0001](../adr/0001-reimplementar-no-ejecutar-scripts.md)).

La excepción declarada son los **payloads** (`core/tasks/payloads.py`): programas Python cortos que viajan por `-c` al intérprete del proyecto —el de acá o el del VPS— porque necesitan importar `app.` y `seeders.` del repo administrado. No se copia ningún archivo al otro lado.

## 3. El contrato de nombres

El `name` de un eje y el `id` de un paso **son** el nombre del parámetro de la función. Con eso, `Capability.kwargs_from(payload)` arma los kwargs de cualquier capacidad sin una tabla de adaptadores por botón. Lo que lee el humano vive aparte, en `label` y `labels` ([ADR-0003](../adr/0003-contrato-de-nombres.md)).

Consecuencia práctica: renombrar un parámetro de una función de `core/tasks/` obliga a renombrar su eje en `core/catalog.py`, y al revés. No hay ninguna capa que traduzca entre los dos.

## 4. Detectar antes de actuar, y mostrar antes de escribir

- Lo que ya está no se rehace: `install_packages` saltea lo instalado, `ensure_local_keypair` no pisa una llave existente, `create_database` solo cambia el dueño si la base ya existe.
- Lo que se sobrescribe se compara primero: `core/files.py::compare` devuelve `NEW`/`DIFF`/`SAME` y alimenta los modos simulacro; `core/vps.py::write_config` imprime un `diff` unificado y no escribe si el contenido es idéntico.
- Un archivo que no cambió no reinicia nada: `write_config` devuelve si hubo cambio, y `bring_up_service` usa eso para elegir entre `restart` y `start` ([ADR-0039](../adr/0039-mostrar-antes-de-escribir.md)).

## 5. Los secretos no se ven ni se escriben

`ctx.guard(valor)` marca un valor y `ctx.mask` lo reemplaza por `******` en todo lo que pase por el log. Lo usan las contraseñas de base, el secreto de TURN y lo que se pide con `ask(secret=True)`. Una contraseña de SSH viaja por el entorno de un helper `SSH_ASKPASS`, nunca por la línea de comandos ni por disco (`core/ssh.py::password_env`).

## 6. Cancelar es parte del contrato

Cada `TaskContext` tiene un `threading.Event`. `ctx.run` lo consulta antes de arrancar y `core/process.py::stream` mientras transmite. Cancelar corre primero los ganchos de apagado limpio registrados con `on_cancel` —el emulador se cierra por `adb`, no a golpes— y después mata el árbol de procesos de abajo hacia arriba.

Una compuesta comparte contexto con sus pasos (`ctx.child`), así que hay un solo log, una sola cancelación y una sola memoria de respuestas (`ask_once`).

## 7. Un solo lugar para cada dato

- Lo que la tarea **lee** es configuración: va a `.consola/config.env` y se declara en `core/settings.py`.
- Lo que se **elige al apretar** es un parámetro: va al eje del panel y se guarda en `.consola/params.json`.
- Lo que es de la **máquina** y no del repo va a `QSettings`.

La regla completa, con sus casos límite, está en [13](13_configuracion_y_persistencia.md) y en [ADR-0017](../adr/0017-datos-en-el-env-decisiones-en-el-json.md).

## 8. Errores que dicen qué hacer

`TaskError` se levanta con la frase que resuelve el problema, no con el síntoma: «Corre "Publicar codigo" antes de instalar el servicio», «Corre "Software base" con el grupo "Coturn" marcado», «Hay mas de un spa-vite en X: panel, backoffice. Elige uno». `MissingConfig` es aparte para que la interfaz pueda abrir la configuración filtrada a las claves que faltan en vez de mostrar un texto suelto.

## 9. Idioma y forma del código

- El código, los comentarios y los mensajes están en español. Los identificadores del dominio conservan el nombre técnico (`remote`, `scope`, `payload`).
- Los comentarios explican **por qué** una decisión es como es, no qué hace la línea siguiente; los que cargan una decisión citan su ADR.
- Los nombres de archivo y de símbolo se citan tal cual; nunca números de línea.

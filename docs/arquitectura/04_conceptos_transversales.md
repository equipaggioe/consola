# 04 · Conceptos transversales

Reglas que valen para todo el código, no para un dominio. Cada una se puede comprobar en el archivo que la nombra.

## 1. El nivel 0 no habla con nadie más que con su contexto

Nada de `services/` importa QtWidgets ni QtNetwork —ruff lo prohíbe con `services/ruff.toml`—, imprime a stdout, lee de stdin ni sale del proceso. Qt entra en `services/` en cuatro usos: QtCore para los dos hilos (`task_runner.py` y `db_worker.py`), para lo que se guarda en `QSettings` (`favorites.py`, `section_visibility.py`, `params_store.py` y `project_store.py`) y para el `QLocale` con el que `files.human_size` y `db_explorer.human_count` escriben un número —el del widget que lo muestra, o `QLocale()` en el mensaje de una tarea—, y QtGui y QtSvg en `services/tasks/raster.py`, como biblioteca de imágenes para rasterizar el logo ([ADR-0055](../adr/0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md)). Todo HTTP va por `api/`: ruff prohíbe QtNetwork fuera de él. `api/http.py` hace HTTP con el único `QNetworkAccessManager` de la app, que `main.py` crea en el hilo de la interfaz: la tarea le manda la petición por una señal encolada y espera las partes de la respuesta en una cola, bloqueando su propio hilo. Una llamada desde el hilo de la interfaz es un `RuntimeError`. Un fallo de red, un 502, un 503 o un 504 se reintenta hasta 3 veces, con espera exponencial y jitter, salvo un `POST`, y una descarga cortada empieza de cero ([ADR-0089](../adr/0089-http-va-por-un-solo-manager-en-el-hilo-de-la-interfaz-y-reintenta.md)). Informa por el `TaskContext` que recibe y levanta `TaskError` cuando no puede seguir. Es lo que permite que la misma función sirva para la consola de una pestaña, para un paso interno de una compuesta y para un test sin ventana ([ADR-0005](../adr/0005-todo-pasa-por-taskcontext.md)).

- `print` + `SystemExit(1)` se reemplazó por `TaskError` (`services/errors.py`).
- `input()` se reemplazó por `ctx.ask` / `ctx.confirm`, que abren el diálogo que corresponde.
- `subprocess.run` se reemplazó por `ctx.run` / `ctx.capture`, que transmiten en vivo y atienden la cancelación.

Todo lo que ejecuta algo es una capacidad, aunque lo dispare un ícono de la interfaz: corre por el mismo runner, con el mismo log, los mismos errores y la misma cancelación. Si no tiene sentido como botón, se declara `hidden=True` y declara sus ejes igual. La interfaz no importa `subprocess` ni módulos de herramientas: pide una capacidad por id.

## 2. El único `subprocess` es a un binario externo real o a un programa de canone

`flutter`, `pnpm`, `git`, `ssh`, `scp`, `adb`, `emulator`, `sdkmanager`, `psql`, `pyinstaller`, `uvicorn`, o un programa de canone. Ninguna capacidad lanza otro script de Consola como proceso: si necesita lo que hace otra, la llama como función con `ctx.child(...)` ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)).

La excepción declarada son los **payloads** (`services/tasks/payloads.py`): programas Python cortos que viajan por `-c` al intérprete del proyecto —el de aquí o el del VPS— porque necesitan importar `app.` y `seeders.` del repo administrado. No se copia ningún archivo al otro lado.

## 3. El contrato de nombres

El `name` de un eje y el `id` de un paso **son** el nombre del parámetro de la función. Con eso, `Capability.kwargs_from(payload)` arma los kwargs de cualquier capacidad sin una tabla de adaptadores por botón. Lo que lee el humano vive aparte, en `label` y `labels` ([ADR-0003](../adr/0003-contrato-de-nombres.md)).

Consecuencia práctica: renombrar un parámetro de una función de `services/tasks/` obliga a renombrar su eje en `services/catalog.py`, y al revés. No hay ninguna capa que traduzca entre los dos.

## 4. Detectar antes de actuar, y mostrar antes de escribir

- Lo que ya está no se rehace: `install_packages` saltea lo instalado, `ensure_local_keypair` no pisa una llave existente, `create_database` solo cambia el dueño si la base ya existe.
- Lo que se sobrescribe se compara primero: `services/files.py::compare` devuelve `NEW`/`DIFF`/`SAME` y alimenta los modos simulacro ([ADR-0039](../adr/0039-mostrar-antes-de-escribir.md)).

## 5. Los secretos no se ven ni se escriben

`ctx.guard(valor)` marca un valor y `ctx.mask` lo reemplaza por `******` en todo lo que pase por el log. Lo usan las contraseñas de base y de `sudo`, los tokens, las credenciales y lo que se pide con `ask(secret=True)`. Lo que va por stdin (`ctx.run(..., stdin_text=...)`, `ctx.converse`) no pasa por el log.

## 6. Cancelar es parte del contrato

Cada `TaskContext` tiene un `threading.Event`. `ctx.run` lo consulta antes de arrancar y `services/process.py::stream` mientras transmite. Cancelar corre primero los ganchos de apagado limpio registrados con `on_cancel` —el emulador se cierra por `adb`, no a golpes— y después mata el árbol de procesos de abajo hacia arriba.

Una compuesta comparte contexto con sus pasos (`ctx.child`), así que hay un solo log, una sola cancelación y una sola memoria de respuestas (`ask_once`).

## 7. Un solo lugar para cada dato

- Lo que la tarea **lee** es configuración: va a `.consola/config.env` y se declara en `services/settings.py`.
- Lo que se **elige al apretar** es un parámetro: va al eje del panel y se guarda en `.consola/params.json`.
- Lo que es de la **máquina** y no del repo va a `QSettings`.

La regla completa, con sus casos límite, está en [13](13_configuracion_y_persistencia.md) y en [ADR-0064](../adr/0064-consola-se-ignora-con-su-propio-gitignore.md).

## 8. Errores que dicen qué hacer

`TaskError` se levanta con la frase que resuelve el problema, no con el síntoma: «La cuenta que administra todavía no existe: corre «Configurar VPS» con «Instalar infraestructura» primero», «Hay mas de un spa-vite en X: panel, backoffice. Elige uno». `MissingConfig` es aparte para que la interfaz pueda abrir la configuración filtrada a las claves que faltan en vez de mostrar un texto suelto.

## 9. Idioma y forma del código

- El código, los comentarios y los mensajes están en español. Los identificadores del dominio conservan el nombre técnico (`remote`, `scope`, `payload`).
- Los comentarios explican **por qué** una decisión es como es, no qué hace la línea siguiente; los que cargan una decisión citan su ADR.
- Los nombres de archivo y de símbolo se citan tal cual; nunca números de línea.

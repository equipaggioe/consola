# Consola — Plan de desarrollo

App de escritorio (PySide6) que reemplaza los scripts sueltos de `navetta/scripts/` por
**botones que ejecutan funciones**, con selector de proyectos, consolas en vivo por pestaña
y una bitácora persistente por repo.

**Principio rector: no se disparan scripts ni se copian — se analiza qué hace cada uno y se
reimplementa su comportamiento como funciones nativas de Consola, limpias, organizadas en tres
niveles (detalle completo en §2).**

0. **Funciones comunes.** Las rutinas que hoy están copiadas y pegadas, casi idénticas, en una
   docena de scripts distintos — cargar `.env`, resolver llave y target SSH, derivar el nombre del
   repo desde `GIT_REPO_URL`, subir un directorio por `scp` — se centralizan una sola vez:
   `load_env_file()`, `resolve_ssh_target()`, `bump_semver()`, `upload_dir_via_scp()`. Nunca son un
   botón; las usan por dentro las funciones de los niveles 1 y 2.
1. **Funciones atómicas.** Cada operación con una sola responsabilidad que hoy hace un script (o un
   fragmento de script) se re-escribe como una función Python chica, construida sobre las funciones
   comunes: `bump_version()`, `upload_to_vps()`, `systemd_action()`. Estas funciones no dependen de
   Qt, no imprimen a `stdout` directamente y no llaman a `python scripts/x/y.py` por subproceso — el
   único `subprocess` permitido es a binarios externos reales (`flutter`, `ssh`, `adb`, `uvicorn`).
   Cada una produce uno o varios botones, según sus ejes (§2.4).
2. **Funciones compuestas.** Los scripts que hoy encadenan varios pasos en un solo archivo —
   "levantar backend + terminal + frontend", "preparar VPS desde cero", "actualizar el remoto
   completo" — se reimplementan como funciones que **orquestan varias funciones atómicas**, igual
   que hace hoy el script original, pero como composición explícita de piezas reutilizables en vez
   de un archivo monolítico. Una compuesta no duplica lógica: llama a las mismas funciones atómicas
   que ya tienen su propio botón — y agrega el botón "todo junto" además, no en su lugar.

Nada de esto se logra invocando `python scripts/x/y.py` como subproceso, ni pegando el archivo
`.py` original dentro de la app: eso sería copiar el script, no reimplementarlo — y el código actual
de `navetta/scripts/` viene de años de parches sueltos, no es algo que convenga trasladar tal cual.
Los scripts en `navetta/scripts/` siguen intactos y no se tocan — son la especificación de
comportamiento a leer y analizar, no código a ejecutar ni a trasladar tal cual.

Fecha de esta versión: 2026-08-18. Basado en el estado de `navetta/scripts/` auditado el 2026-08-17.

**Referencia visual** → [Propuesta de UI (Artifact)](https://claude.ai/code/artifact/2f6393a1-a1d6-4c66-92e9-3cba9dc5b0e9)

**Scripts de referencia** → copiados a `../scripts/` para auditoría y análisis sin tocar `navetta/scripts/`.
Estos mismos scripts son la especificación de comportamiento que cada función debe reimplementar.

---

## 0. La app (mockup del artifact)

Tres zonas fijas, visibles en la [propuesta de UI](https://claude.ai/code/artifact/2f6393a1-a1d6-4c66-92e9-3cba9dc5b0e9):

- **Rail de acciones (izquierda)** — selector de proyecto arriba (`consola ▼`), debajo la lista de
  acciones agrupada por categoría (Launchers, Builders, VPS, …) y, aparte, la entrada a **Base de
  datos** (§6) — no es una acción que dispara una consola, abre su propia pestaña de exploración.
  Cada fila de acción tiene un LED: apagado si no corre, verde si es una acción "en vivo" activa.
- **Panel de pestañas (centro)** — una pestaña por ejecución en curso o reciente, con su propio LED
  (verde = corriendo, gris = inactiva). Debajo, la consola de esa pestaña: texto tipo terminal con
  niveles coloreados (`[INFO]`, `[OK]`, `[ERROR]`) y cursor parpadeante mientras el proceso sigue vivo.
  Una pestaña de **Base de datos** es distinta: en vez de texto de consola tiene árbol de esquema +
  grilla de resultados (§6), pero comparte el mismo panel y el mismo pie de pestañas secundarias —
  **Consola / Bitácora / Historial / Configuración** — con contador de tareas activas y tiempo
  transcurrido.
- **Barra de estado (abajo)** — indicador permanente de **servicios de fondo** (p. ej. el túnel
  Postgres), independiente del panel de pestañas: sigue vivo aunque cierres su pestaña o cambies
  de proyecto.

Ejemplo de consola en vivo (acción "Backend"):

```
[INFO]  Iniciando servidor backend…
[INFO]  App: app.main:app
[INFO]  Host: 0.0.0.0   Puerto: 8000
[INFO]  TLS: habilitado (certs/cert.pem)
[OK]    SERVER_PORT=8000 escrito en .env
INFO:     Uvicorn running on https://0.0.0.0:8000
INFO:     Started reloader process [24188]
INFO:     Application startup complete.
INFO:     172.19.0.4:51224 - "GET /api/routes" 200
▍
```

---

## 1. Qué reemplaza

46 archivos en `navetta/scripts/`, agrupados en 8 carpetas temáticas, se convierten en un catálogo
que **ya no se cuenta en acciones fijas**, sino en **capacidades** (§2). Una capacidad es una
función; el número de botones que produce depende de sus ejes y del proyecto abierto — por eso no
hay un número único como el "36 acciones" de la versión anterior de este plan. Lo que sí es estable
es el número de capacidades: alrededor de 20, agrupadas en dos tipos:

- **Atómicas** — hacen una sola cosa. `bump_version`, `upload_to_vps`, `systemd_action`,
  `git_sync_remote`. Producen uno o varios botones según sus ejes (§2).
- **Compuestas (recetas)** — encadenan capacidades atómicas en el mismo orden que hoy encadena el
  script original, sin duplicar su lógica. Producen un botón propio *además* de los botones de cada
  paso — no en su lugar. Ver §7, caso 7.

Confirmado contra el código fuente de cada script (no solo su docstring), tres simplificaciones
se sostienen igual que antes:

- `run_emulator_1/2/3.py` llaman los tres a la misma función `run()` de `android_emulator.py` con
  tres constantes distintas (`pixel_4`, `pixel_8`, `resizable`) → una capacidad `start_emulator` con
  eje `preset`, `expand="buttons"`.
- `run_panel.py`, `run_backoffice.py` (raíz de `scripts/`) y `launchers/run_landing.py` resultan ser,
  leyendo el código, el mismo flujo que `launchers/run_vite.py` — `run_landing.py` incluso lo llama
  directamente (`run_vite.main()` con `sys.argv=["landing"]`); `run_panel.py`/`run_backoffice.py` son
  una copia literal con el prefijo de variable de entorno cambiado (`PANEL_*` / `BACKOFFICE_*` en vez
  de leer el prefijo por parámetro). Los tres, más cualquier SPA nueva que aparezca en el repo, caen
  en **una** capacidad `serve_vite_app` con eje `target` **descubierto** (§2) — no hay que confirmar
  nada a mano, esto resuelve el punto 2 del pendiente original (antes §11.2).
- `view_logs.py` es un wrapper de una línea sobre `run_systemd_action.py logs` → se absorbe como
  valor del eje `action` de `systemd_action`, no como capacidad propia.
- `sync_projects.py` + `verify_projects.py` se funden en una sola capacidad (`--check` como valor de
  un eje `mode`, no como script aparte).

Dos scripts quedan fuera del catálogo por completo (ver abajo), sin cambios respecto a la versión
anterior de este plan.

### Scripts descartados (no se portan a Consola)

Estos no entran al catálogo — no por falta de tiempo, sino porque el problema que resolvían deja
de existir una vez que Consola es la herramienta:

- **`sync/sync_projects.py`** y **`sync/verify_projects.py`**, únicamente en la parte que copiaba y
  verificaba la carpeta `scripts/` entre los repos gestionados (`banditore`, `cadenza`, `forziere`,
  `navetta`, `parametri`, `presenze`, `spazio`, `vettore`) para que todos tuvieran los mismos scripts
  sueltos. Con Consola ya no hay una carpeta `scripts/` que mantener igual en cada repo: la lógica
  vive una sola vez en la app y se aplica a cualquier proyecto gestionado a través del selector.

  El resto de lo que hacían — sincronizar código compartido que **no** es scripts (`server/alembic/env.py`,
  `server/app/models/base.py`, `.gitignore`, `server/alembic.ini`) — es un problema distinto, ajeno a
  Consola, y no desaparece solo porque los scripts se reimplementen. Se porta como acción propia,
  separada: **Sync · archivos comunes** (grupo Utils, ver §5), con su propia lista de rutas
  (`COMMON_PATHS` menos `scripts/`) y el mismo simulacro `NEW`/`DIFF` que tenía el original antes de
  aplicar. `verify_projects.py` se absorbe como modo de esa misma acción (`--check`, sin escribir),
  no como acción aparte — hoy es un archivo que solo reexpone lo que ya calcula `sync_projects.py`.

- **`get_route_data.py`** — script de inspección puntual de la base de datos (imprime rutas,
  segmentos y paradas). Está pensado para editarse a mano antes de cada corrida (`route_id_to_check`,
  `tenant_id_to_check` hardcodeados, con un aviso de "CAMBIA ESTE VALOR"). No es una operación
  atómica ni repetible con parámetros fijos, sino un script de diagnóstico ad-hoc — no encaja en el
  modelo de "botón que ejecuta función". Queda fuera del catálogo; se sigue usando manualmente si
  hace falta.

Los `.pyc` en `scripts/sync/__pycache__/` desaparecen junto con los `.py` que los generaron.

---

## 2. Modelo: tres niveles de función + ejes

La versión anterior de este plan mapeaba **un script → una función → un botón**. Al auditar los 46
archivos, leyendo el código y no solo el docstring de cada uno, aparecen dos problemas que ese
mapeo 1:1 no resuelve — y un tercer hallazgo que reorganiza todo el modelo:

- **Variación por constante.** Varios scripts son el mismo flujo repetido con una constante distinta
  (`run_emulator_1/2/3.py`, `run_panel.py`/`run_backoffice.py`/`run_landing.py`, los tres modos de
  `install_base_software.py`). Un botón por script duplica UI en vez de exponer la variación.
- **Pasos internos empaquetados.** Varios scripts son *un solo archivo* que hace varias cosas en
  secuencia y no expone ningún paso suelto (`update_remote.py`, `setup_ssh_key.py`,
  `install_systemd_service.py`, `run_scripts.py`, `build_apk.py`). Un botón por script esconde pasos
  que a veces se piden solos — "solo copiar los certificados", "solo reinstalar dependencias" —
  sin repetir el resto.
- **Un mismo puñado de rutinas se repite, copiada y pegada, en al menos una docena de scripts** —
  cargar `.env`, resolver la llave y el target SSH, derivar el nombre del repo desde
  `GIT_REPO_URL`, subir un directorio por `scp`. Hoy no existe un archivo que las centralice: cada
  script trae su propia copia de `_load_env_file`. Por eso el catálogo no puede tener solo dos
  niveles ("la función" y "el botón") — necesita un nivel debajo de ambos que no es botón de nadie.

Por eso el modelo tiene **tres niveles de función**, más un mecanismo transversal que aplica a los
dos niveles que sí producen botón:

| Nivel | Qué es | ¿Produce botón? | Vive en |
|---|---|---|---|
| **0 — Comunes** | Rutina compartida por varias funciones de nivel 1/2. No es un paso de negocio, es plomería. | No, nunca. | `core/envfile.py`, `core/ssh.py`, `core/vps.py`, `core/android.py` |
| **1 — Atómicas** | Una responsabilidad, construida sobre funciones comunes. | Sí — uno o varios, según sus ejes. | `core/tasks/*.py` |
| **2 — Compuestas** | Encadena varias atómicas en un orden fijo, igual que hoy encadena el script original. No reimplementa la lógica de ninguna atómica, la llama. | Sí — el botón "todo junto", además de los botones de cada atómica que usa. | `core/tasks/*.py` |

Los botones no se declaran uno por uno: se **derivan** del producto de (función atómica o
compuesta) × ejes (§2.4). Nivel 0 nunca aparece en el rail — es la única capa de este modelo que es
puramente interna.

### 2.1 Nivel 0 — Funciones comunes

Esto es, literalmente, el `common.py` que los scripts actuales nunca llegaron a tener. Hoy cada una
de estas rutinas está copiada y pegada, casi idéntica, en varios archivos distintos:

| Función común | Reemplaza la copia duplicada en… |
|---|---|
| `load_env_file(path)` / `require(name)` | 12+ scripts: `run_server.py`, `run_terminal.py`, `run_vite.py`, `run_panel.py`, `run_backoffice.py`, todos los `vps_ops/*.py`, `vps_server/*.py`, `vps_setup/*.py` — cada uno trae su propio `_load_env_file` / `_require_env` casi carácter por carácter |
| `resolve_ssh_target(vps_ip, vps_user, vps_key_name)` → identity file + `user@ip` | `ssh_login.py`, `run_command.py`, `run_scripts.py`, `ssh_tunnel_postgres.py`, `revoke_ssh_key.py`, `install_base_software.py`, `refresh_known_host.py`, `setup_ssh_key.py`, `update_remote.py`, `install_systemd_service.py`, `run_systemd_action.py` |
| `repo_name_from_git_url(url)` | `run_systemd_action.py`, `build_vite.py`, `install_systemd_service.py`, `update_remote.py` |
| `bump_semver(text, field, mode)` | el núcleo regex que comparten `build_apk.py` (`pubspec.yaml`), `build_vite.py` (`package.json`) y `build_executable.py` (`pyproject.toml`) — cada uno reimplementa el mismo incremento X.Y.Z con su propia regex |
| `upload_dir_via_scp(local, remote, ssh_target)` | `build_apk.py`, `build_vite.py`, `build_executable.py` |
| `find_project_root()` (busca `.git` subiendo directorios) | `build_vite.py`, `build_executable.py` y variantes menores en el resto |

Ninguna de estas seis tiene botón propio. Un botón que "solo" ejecuta `resolve_ssh_target` no tiene
sentido para nadie — es la que usan por dentro `ssh_login`, `run_command`, `backup_database` y una
decena más de capacidades de nivel 1 y 2.

### 2.2 Nivel 1 — Funciones atómicas

Una responsabilidad, construida sobre funciones comunes. Ejemplo — dos atómicas que hoy están
enterradas dentro de `build_apk.py` sin existir como algo invocable por separado:

```python
@capability(group="Builders", section="Versión")
def bump_version(ctx: TaskContext, p: BumpParams) -> tuple[str, str]:
    """Incrementa X.Y[.Z] en el archivo indicado (pubspec.yaml / package.json / pyproject.toml)."""
    return bump_semver(p.file.read_text(), field=p.field, mode=p.mode)  # nivel 0

@capability(group="VPS · ops", section="Subir artefacto")
def upload_to_vps(ctx: TaskContext, p: UploadParams) -> str:
    """Sube un directorio o archivo al VPS por la misma ruta relativa del repo."""
    target = resolve_ssh_target(ctx.project)               # nivel 0
    return upload_dir_via_scp(p.local, p.remote_dir, target)  # nivel 0
```

Cada una es un botón por sí sola (útil para re-subir un artefacto sin reconstruirlo, o para
incrementar versión sin buildear todavía) — y a la vez son las piezas con las que se arma el nivel 2.

### 2.3 Nivel 2 — Funciones compuestas

Encadenan atómicas en el orden del script original. `build_apk.py` no es una función nueva que
reimplementa el flujo completo — es la orquestación de las atómicas de arriba más `flutter pub get`
y `flutter build apk` (que no ameritan botón propio: nadie pide "hacé pub get y nada más"):

```python
@capability(group="Builders", section="Build APK", kind="once", composed_of=[bump_version, upload_to_vps])
def build_apk(ctx: TaskContext, p: ApkParams) -> None:
    """Compuesta: bump_version(pubspec) → flutter pub get → flutter build apk → upload_to_vps."""
    flutter = find_flutter(ctx)
    old, new = bump_version(ctx, BumpParams(p.project_dir / "pubspec.yaml", "version", p.bump_mode))
    try:
        ctx.run([flutter, "pub", "get"], cwd=p.project_dir)
        ctx.run([flutter, "build", "apk", "--release"], cwd=p.project_dir, env=api_base_env(p))
        if p.copy_to_vps:
            upload_to_vps(ctx, UploadParams(apk_output_path(p), p.remote_dir))
    except (TaskError, Cancelled):
        restore_version(p.project_dir / "pubspec.yaml", old)
        raise
```

El resultado en el rail: la sección "Build APK" muestra el botón compuesto grande ("Build APK
completo") y, si el usuario los quiere sueltos, los botones de sus atómicas quedan disponibles en la
sección "Versión" y en "VPS · ops → Subir artefacto" — sin que exista una segunda copia de la lógica
en ningún lado. Este es el patrón que se aplica también a `update_remote.py`, `setup_ssh_key.py`,
`setup_github_ssh.py`, `install_systemd_service.py`, `run_scripts.py` y los otros dos builders — el
detalle de cada uno está en §5 y la regla para decidir qué atómica se separa está en §7, caso 7.

`subprocess` no desaparece: `flutter`, `ssh`, `adb`, `uvicorn` son binarios externos y se siguen
invocando. Lo que desaparece es la capa `python scripts/builders/build_apk.py` — la orquestación
vive en la función, dentro de la app, analizada desde el comportamiento del script, no transcrita de
su código (que hoy está desprolijo por los años de parches sueltos — ver intro de este documento).

### 2.4 Ejes: de constante a botones

Un eje declara los valores posibles de un parámetro y **cómo se muestra**:

```python
axis("action", of=systemd_action,
     values=["start", "stop", "restart", "status", "logs"],
     expand="buttons",                  # un botón por valor, en la sección
     danger={"stop"})

axis("action", of=systemd_action,
     values=["enable", "disable", "reload", "is-active", "is-enabled"],
     expand="menu")                     # el resto, en el ⋯ de la misma sección
```

Tres modos de `expand`:

- **`buttons`** — un botón por valor, visible en la sección. Para lo que se usa seguido.
- **`menu`** — al ⋯ de la sección. Para lo que existe pero no merece ocupar espacio a diario.
- **`field`** — campo del formulario (el comportamiento de siempre, §9). Para lo que no es una
  elección discreta chica (`bump_mode`, un puerto, una ruta).

Un eje puede repartirse entre modos (arriba: 5 botones + 5 en el menú) porque la lista completa de
valores de `run_systemd_action.py` es larga pero solo una parte se usa seguido.

**Ejes descubiertos, no declarados.** `serve_vite_app` no lista `panel|backoffice|landing` a mano:

```python
axis("target", of=serve_vite_app,
     values=discover(kind="spa-vite"),   # carpeta con package.json + vite.config.*
     expand="buttons")
```

`core/targets.py` recorre el repo abierto y devuelve *targets* tipados (`spa-vite`, `flutter-app`,
`fastapi-server`) según marcadores de archivo. Una capacidad declara `applies_to="spa-vite"` y la UI
arma un botón por target encontrado — en `navetta` salen tres (`panel`, `backoffice`, `landing`), en
un repo con solo `panel/` sale uno, y un subproyecto nuevo aparece solo, sin tocar el catálogo. Esto
resuelve de verdad el punto 4 del pendiente original (antes §11.4): no hace falta enumerar a mano qué
subproyecto tiene cada uno de los 8 repos gestionados.

**El selector local/remoto es un eje de encabezado.** `expand="scope"` se renderiza una vez, arriba
de la sección, como segmentado, y afecta a todos los botones debajo — no se repite por botón:

```python
axis("where", of=run_setup_scripts, values=["local", "remoto"], expand="scope",
     requires={"remoto": ["VPS_IP", "VPS_USER", "VPS_KEY_NAME"]})
```

`requires` es por *valor de eje*, no por capacidad entera (contraste con el `required_by` de §9): el
segmentado "remoto" se muestra en ámbar con lo que falta mientras "local" queda perfectamente usable.

---

## 3. Arquitectura

```
consola/
├── core/                    — sin imports de Qt, testeable solo
│   ├── context.py           TaskContext, TaskError, Cancelled
│   ├── runner.py            pool de workers, cancelación, árbol de PIDs
│   ├── registry.py          @capability + axis() → catálogo de secciones/botones (§2)
│   ├── recipes.py           receta = lista de (capacidad, valores de eje) → botón compuesto (§7.7)
│   ├── targets.py           descubre subproyectos por marcador de archivo (§2.4)
│   ├── params.py            dataclass tipado → especificación de widgets
│   ├── projects.py          los proyectos gestionados, detección, validación
│   ├── config.py            esquema de settings: tipos, grupos, requires por valor de eje (§9)
│   ├── envfile.py           lee/escribe .consola/config.env; lee (nunca escribe) server/.env
│   ├── store.py             SQLite: preferencias de la app, bitácora, historial, presets
│   ├── ssh.py               resolución de llave + target SSH (hoy repetido en 12 scripts)
│   ├── android.py           SDK paths, AVD, system images (reimplementa android_emulator.py)
│   └── tasks/
│       ├── launchers.py     builders.py     emulators.py
│       ├── vps_ops.py       vps_server.py   vps_setup.py
│       └── utils.py
├── ui/
│   ├── main_window.py       rail de acciones | pestañas | barra de estado
│   ├── console_view.py      QPlainTextEdit + parser ANSI + búsqueda
│   ├── param_form.py        formulario generado desde params.py
│   ├── notes_view.py        bitácora markdown
│   ├── history_view.py      ejecuciones pasadas, con su log
│   └── settings_view.py     Configuración: formulario tipado + procedencia por campo
└── main.py
```

`core/` deduplica dos patrones que hoy están copiados literalmente en múltiples scripts:

- **Carga de `.env`** (`_load_env_file`, `_require_env`, `_require_int_env`, `_require_bool_env`):
  presente en `launchers/run_server.py`, `launchers/run_terminal.py`, `vps_ops/run_scripts.py`,
  `vps_ops/ssh_login.py`, `vps_ops/ssh_tunnel_postgres.py` y otros → `core/envfile.py`, una vez.
- **Resolución de sesión SSH** (llave en `~/.ssh/<VPS_KEY_NAME>`, target `user@ip`): presente en
  `vps_ops/ssh_login.py`, `vps_ops/run_scripts.py`, `vps_ops/ssh_tunnel_postgres.py`,
  `vps_server/*.py` → `core/ssh.py`, una vez.

---

## 4. TaskContext

Pieza central. Cada función de acción recibe un `TaskContext` que reemplaza los tres patrones
que se repiten en todos los scripts originales:

| Patrón original | En Plancia | Comportamiento |
|---|---|---|
| `print("[INFO] …")` | `ctx.log(msg, level)` | Va a la consola de su pestaña, coloreado, con timestamp |
| `subprocess.run(cmd)` | `ctx.run(cmd, cwd=, env=)` | Streaming línea a línea, cancelable, PID registrado |
| `raise SystemExit(1)` | `raise TaskError(msg)` | Marca la pestaña en rojo sin tumbar la app |
| `input("¿seguro? ")` | `ctx.confirm(msg, danger=)` | Diálogo modal; destructivos exigen escribir el nombre |
| `os.environ[k] = v` | `ctx.project.env` | Entorno aislado por tarea, no el del proceso global |

```python
class TaskContext:
    def log(self, msg: str, level: Level = "info") -> None: ...
    def run(self, cmd: list[str], *, cwd: Path | None = None,
            env: dict | None = None, check: bool = True) -> int: ...
    def confirm(self, question: str, *, danger: bool = False) -> bool: ...
    def ask(self, prompt: str, *, secret: bool = False) -> str: ...
    def progress(self, done: int, total: int, label: str = "") -> None: ...
    def note(self, entry: str) -> None: ...       # escribe en la bitácora del proyecto

    project: Project      # raíz, .env aislado, nombre
    cancelled: bool        # se chequea en bucles largos (polling, watch de archivos)
```

`confirm()` y `ask()` se disparan desde el worker thread pero el diálogo vive en el hilo de UI
(señal Qt + `QEventLoop` local que bloquea solo esa tarea; las demás pestañas siguen corriendo).

---

## 5. Catálogo de capacidades

Ya no es una lista de botones — es una lista de **capacidades**, con los ejes que cada una produce
y, donde el script original empaqueta varios pasos en un solo archivo, la **descomposición**: qué
pasos se vuelven botón atómico propio y cuál es el botón compuesto que los encadena (patrón general
en §7, caso 7). "🧩" marca una capacidad compuesta.

| Grupo | Capacidad | Ejes → botones que produce | Tipo |
|---|---|---|---|
| Launchers | Backend (`run_server.py`) | — (una instancia por proyecto) | en vivo |
| Launchers | Servir SPA Vite (`run_vite`+`run_panel`+`run_backoffice`+`run_landing`) | `target` **descubierto** (`panel`, `backoffice`, `landing`, …) → 1 botón por SPA encontrada | en vivo |
| Launchers | Flutter (`run_flutter.py`) | — | en vivo |
| Launchers | Terminal (`run_terminal.py`) | — (vigilante + hijo, caso 6) | en vivo |
| Builders 🧩 | **Build APK** (`build_apk.py`) — compuesta de: `bump_version(pubspec)`, `flutter pub get`, `flutter build apk`, `upload_to_vps` | `bump_mode` campo; `copy_to_vps` scope local/con-subida | una vez |
| Builders 🧩 | **Build Vite** (`build_vite.py`) — compuesta de: `bump_version(package.json)`, `npm ci`, `npm run build`, `upload_to_vps` | `target` descubierto (igual que el launcher) × `copy_to_vps` scope | una vez |
| Builders 🧩 | **Build ejecutable** (`build_executable.py`) — compuesta de: `bump_version(pyproject)`, `pyinstaller`, `upload_to_vps` opcional | `entrypoint` campo | una vez |
| Builders | Promote app (`promote_app.py`) | — (un solo paso: copia `app_web_ultima` → `app_web_estable`, no hay nada que descomponer) | una vez / destructivo |
| Emulators | Arrancar emulador (`android_emulator.py` + `run_emulator_1/2/3.py`) | `preset` → botones `pixel_4` \| `pixel_8` \| `resizable` | en vivo |
| Emulators | Gestor de AVD (`emulator_manager.py`) | — (vista propia, no consola) | vista |
| Emulators | Purgar AVD / Purgar imágenes de sistema | — | destructivo |
| VPS · ops | Sesión SSH (`ssh_login.py`) | — | interactivo |
| VPS · ops | Túnel Postgres (`ssh_tunnel_postgres.py`) | — | servicio de fondo |
| VPS · ops | Backup DB / Health check / Comando remoto | — | una vez |
| VPS · ops 🧩 | **Correr setup remoto** (`run_scripts.py`) — compuesta de: `run_remote_script(script)` por cada entrada de `SETUP_SCRIPTS` | `script` → 1 botón por entrada de la lista (config, no hardcode) + botón compuesto "Correr todos, en orden" | una vez |
| VPS · ops | Revocar llave SSH (`revoke_ssh_key.py`) | — (ya es un solo paso: VPS + archivos locales) | destructivo |
| VPS · ops 🧩 | **Revocar GitHub SSH** (`revoke_github_ssh.py`) — compuesta de: `remove_remote_ssh_key_files`, `revoke_github_key_by_title` | — | destructivo |
| VPS · server | Acción systemd (`run_systemd_action.py` + `view_logs.py`) | `action` → botones `start`\|`stop`\|`restart`\|`status`\|`logs`, menú `enable`\|`disable`\|`reload`\|`is-active`\|`is-enabled` | en vivo (`logs`) / una vez |
| VPS · server 🧩 | **Instalar servicio systemd** (`install_systemd_service.py`) — compuesta de: `write_systemd_unit` + reusa `systemd_action(reload)`, `systemd_action(enable)`, `systemd_action(start)` | — | una vez |
| VPS · server 🧩 | **Actualizar remoto** (`update_remote.py`) — compuesta de: `git_sync_remote`, `ensure_remote_venv`, `install_remote_deps`, `copy_env_to_remote`, `copy_certs_to_remote`, `copy_firebase_credentials` | cada paso también es botón suelto (ej.: "solo copiar certificados" sin rehacer el resto) | en vivo |
| VPS · setup 🧩 | **Software base** (`install_base_software.py`) — compuesta de: `apt_update`, `apt_upgrade`, `apt_install(grupo)` | `grupo` (`python`\|`git`\|`node`\|…) → botones, ya es selección hoy (`PACKAGES`) | una vez |
| VPS · setup | Refrescar known_host | — | una vez |
| VPS · setup 🧩 | **Configurar llave SSH** (`setup_ssh_key.py`) — compuesta de: `ensure_remote_user`, `configure_sudo_nopasswd`, `ensure_local_ssh_keypair`, `install_pubkey_remote`, `test_ssh_login` | — | una vez |
| VPS · setup 🧩 | **Configurar GitHub SSH** (`setup_github_ssh.py`) — compuesta de: `generate_remote_keypair`, `register_github_key`, `test_github_ssh` | — | una vez |
| Utils | Limpiar artefactos (`clean_artifacts.py` absorbe `clean_pycache.py` como subconjunto de patrones) | `dry_run` scope simulacro/borrado | destructivo |
| Utils | Instalar SDK Android / Instalar SDK Flutter | — | una vez |
| Utils | Actualizar Cloudflare | `ip_mode` campo (`detect`\|`vps`\|`static`) | una vez |
| Utils | **Sync · archivos comunes** (`sync_projects.py` + `verify_projects.py`, sin la parte de `scripts/`) | `mode` scope simulacro (`--check`) / aplicar | destructivo |

**Tipos de comportamiento** (sin cambios respecto a la versión anterior):

- **en vivo** — la pestaña queda abierta con LED verde y botón Detener mientras el proceso corre.
- **una vez** — la pestaña se cierra sola al terminar; la entrada queda en el historial.
- **destructivo** — pide confirmación escrita del nombre del objetivo antes de habilitar el botón.
- **interactivo** — no se embebe en la app; abre una terminal externa con la sesión ya armada.
- **vista** — no corre en una pestaña de consola; abre su propia vista (como Base de datos, §6).

Regla para saber si un paso interno se vuelve botón atómico o queda escondido dentro de la
compuesta: ver §7, caso 7.

---

## 6. Explorador de base de datos (fusión de Exploratore)

`e:\Git\exploratore` deja de desarrollarse como app aparte y se funde en Consola. No es una migración
forzada: es un buen encaje. Exploratore ya es PySide6, ya separa una capa de datos sin imports de Qt
(`core/db/postgres_service.py`), y su propio documento de diseño (`docs/descripcion.md`) ya proponía
una "interfaz tipo API" — `list_tables`, `describe_table`, `preview_table`, `run_select`, `run_sql` —
exactamente el mismo patrón de función-que-hace-una-cosa que ya define TaskContext (§4). No hay que
rediseñar nada, hay que trasplantar.

### Qué se trae y dónde cae

| De Exploratore | Pasa a | Cambia |
|---|---|---|
| `core/db/postgres_service.py` | `core/db.py` | nada — ya es Qt-free, ya recibe los datos por parámetro |
| `core/models.py` (`DatabaseConnection`, `TableEntry`, `ColumnEntry`, `QueryExecutionResult`) | `core/models.py` de Consola | se le saca `ssl_mode`/host público del formulario visible (ver abajo) |
| `LocalStore` (`connections`, `table_folders`) | dos tablas más en el SQLite de Consola (§8) | se agrega `project_id`: una conexión pertenece a un proyecto gestionado, no es global |
| `views/pages` (Explorer, Query Runner, tabla) | una pestaña nueva dentro del panel de pestañas (§0) | dejan de ser ventana propia, son una vista más |

### Transporte: siempre localhost por túnel, nunca IP pública

Acá está la decisión que pediste, y no encuentro una idea mejor que la que propusiste: **cada
`DatabaseConnection` en Consola apunta siempre a `127.0.0.1:<puerto>`, nunca a la IP del VPS.** No
hay campo de host público en el formulario — no existe la opción de conectar directo. Conectar a la
base de un proyecto es:

1. Asegurarse de que el servicio de fondo **Túnel Postgres** de ese proyecto esté corriendo (§7,
   punto 2) — si no está, Consola lo arranca antes de abrir el Explorer.
2. `postgres_service.py` conecta con psycopg a ese `127.0.0.1:<puerto>`, como si la base fuera local.

La alternativa sería ejecutar `psql` remoto por SSH en cada consulta — se pierde conexión persistente,
tipado real de filas (`dict_row`) y hay que parsear texto de vuelta en vez de usar el driver, todo
para no reutilizar un túnel que igual hay que construir para VPS·ops (§5). El túnel gana sin competencia.

### Credenciales: no se inventa un lugar nuevo

`ssh_tunnel_postgres.py` ya lee `server/.env` en modo solo-lectura para sugerir la `DATABASE_URL`
con el túnel aplicado, enmascarando el password al imprimirla (§9: esa lectura puntual sigue
permitida, escribir sigue prohibido). El formulario de nueva conexión en el Explorer reutiliza
exactamente ese mismo dato: si el proyecto tiene `DATABASE_URL` en `server/.env`, host/puerto/base/
usuario salen completados solos. El password **no se persiste en ningún lado** — ni en el SQLite de
Consola ni en `.consola/config.env` — se pide al conectar, igual que ya documentaba Exploratore como
plan de MVP ("no persistir el password y pedirlo al conectar"). Es la opción que menos superficie
nueva agrega: no hace falta decidir un tercer lugar para guardar secretos de base de datos.

### Alcance que se porta

Del MVP de Exploratore (`docs/descripcion.md`): listar esquemas/tablas/vistas con PK/FK, vista previa
de tabla con límite y orden, ejecutar consultas de lectura y escritura, organización visual de tablas
en carpetas. Motor único por ahora: PostgreSQL (es lo único que hay en los 8 repos gestionados). Fuera
de alcance, igual que en Exploratore: migraciones, administración de roles, multiusuario.

---

## 7. Siete casos que definen la arquitectura

El resto de las capacidades es rutina de reimplementación directa. Estos siete obligan a decisiones
de diseño explícitas:

1. **Sesión SSH interactiva** (`ssh_login.py`). Necesita TTY real: prompts, contraseña, señales.
   No se embebe — el botón abre una terminal externa (`wt.exe ssh -i …`) con la sesión ya armada,
   y Plancia solo registra que se abrió.

2. **Procesos que sobreviven a su pestaña** (`ssh_tunnel_postgres.py`). El túnel debe seguir vivo
   aunque cambies de pestaña o de proyecto. Se modela como categoría separada — **servicio de
   fondo** — con indicador permanente en la barra de estado, independiente del panel de pestañas.

3. **El emulador se desprende del proceso padre** (`android_emulator.py` / `run_emulator_*.py`).
   `emulator.exe` no muere si matas el proceso que lo lanzó. El estado se sondea con
   `adb devices`, no se infiere del PID; detener significa `adb -s <serial> emu kill`.

4. **Acoplamiento vía `.env`** (`run_server.py` escribe `SERVER_PORT`, `run_terminal.py` y
   `run_panel.py` lo leen para construir `SERVER_URL` / `VITE_SERVER_URL`). Hoy funciona por
   casualidad de orden de ejecución, y se persiste a disco solo porque son procesos separados sin
   otro canal. `SERVER_PORT` **no es configuración: es estado de sesión** — el puerto que el backend
   consiguió en esta corrida. Dentro de Consola vive en memoria, lo publica la acción Backend al
   arrancar, y las acciones lanzadas después lo leen de ahí. No se escribe a ningún archivo
   (ver §9: lo configurable es `server.preferred_port`, no el puerto resultante).

5. **Destructivos que hoy no preguntan** (`purge_avds.py` borra AVDs, `purge_system_images.py`
   borra imágenes descargadas, `revoke_ssh_key.py` saca una llave del VPS). A un clic de distancia,
   eso es un accidente esperando. Simulacro obligatorio: se muestra la lista exacta de lo que se va
   a borrar o revocar **antes** de habilitar Aplicar, y recién ahí se pide la confirmación escrita.
   Mismo patrón para `rebuild_db`, para **Sync · archivos comunes** (`NEW`/`DIFF` por proyecto antes
   de sobrescribir, igual que hacía `sync_projects.py`) y para la importación de configuración (§9).

6. **El launcher que se reinicia solo** (`run_terminal.py` vigila archivos y mata/relanza a su
   hijo). Como función eso son dos niveles de proceso: cancelar la tarea debe matar al hijo actual
   *y* parar el vigilante. `ctx.run()` lleva el árbol de PIDs y termina de abajo hacia arriba
   (`terminate`, luego `kill` a los 5s) para no dejar procesos zombis ocupando puertos.

7. **Scripts que hoy son un solo archivo con varios pasos internos, no una llamada a otro script**
   (`update_remote.py`, `setup_ssh_key.py`, `setup_github_ssh.py`, `install_systemd_service.py`,
   `run_scripts.py`, los tres builders). A diferencia de una acción de bootstrap clásica (§0, la que
   ya orquesta funciones básicas ya separadas), estos scripts nunca expusieron sus pasos como algo
   invocable por separado — están en secuencia dentro de la misma función `main()`. Reimplementarlos
   como una sola capacidad monolítica repetiría el problema original: si solo necesitás recopiar los
   certificados al VPS, tenés que rehacer el `git pull`, el `venv` y el `pip install` completos de
   nuevo, porque no hay manera de pedir un paso solo.

   La solución es partir cada uno en **capacidades atómicas** (una por paso con sentido fuera de la
   secuencia) más **una capacidad compuesta** que las encadena en el mismo orden del script original
   — y que reusa esas mismas funciones atómicas, no una copia de su lógica. `update_remote.py` da
   seis capacidades atómicas (`git_sync_remote`, `ensure_remote_venv`, `install_remote_deps`,
   `copy_env_to_remote`, `copy_certs_to_remote`, `copy_firebase_credentials`) más el botón compuesto
   **Actualizar remoto** que las corre todas. `install_systemd_service.py` da una capacidad nueva
   (`write_systemd_unit`) que se combina con la capacidad `systemd_action` que *ya* existe (caso de
   arriba en la tabla de §5) — la compuesta no reimplementa `enable`/`start`, los reusa.

   **Regla para decidir qué paso se vuelve botón propio:** un paso se separa si tiene sentido
   re-ejecutarlo solo, sin repetir el resto — "solo copiar certificados", "solo probar el login SSH",
   "solo correr `rebuild_db.py`" son operaciones que se piden sueltas en la vida real. Un paso *no* se
   separa si no tiene sentido aislado del resto — revertir `pubspec.yaml` en `build_apk.py` no es un
   botón, es un detalle interno de la capacidad `build_apk`; nadie pide "revertime el pubspec" fuera
   del contexto de un build que falló. Esta misma regla decide la fila 🧩 de cada capacidad en §5.

---

## 8. Memoria por proyecto

SQLite en `%LOCALAPPDATA%\Consola\`, fuera de los repos gestionados: es historia de la máquina, no
del proyecto, y así todos los repos comparten una sola base con búsqueda global. Los logs completos
van a archivos aparte; en la base solo queda el índice.

Distinto de la configuración (§9), que sí vive dentro del repo porque describe cómo se opera *ese*
proyecto y conviene que viaje con él.

| Tabla | Guarda | Se ve en |
|---|---|---|
| `projects` | ruta, nombre, color, último uso | Selector |
| `runs` | acción, parámetros, inicio, fin, código de salida, ruta del log | Historial |
| `notes` | fecha, título, markdown, etiquetas | Bitácora |
| `presets` | combinaciones de parámetros guardadas, con `project_id` — incluye valores de eje como el último `scope` (local/remoto) usado por proyecto (§9) | Formularios |
| `db_connections` | conexión de base por proyecto: host local, puerto, base, usuario — **nunca password** (§6) | Base de datos |
| `db_table_folders` | organización visual de tablas en carpetas, por conexión (de Exploratore) | Base de datos |

La bitácora mezcla entradas manuales con entradas automáticas que las funciones dejan vía
`ctx.note()` (ej.: `Build APK v1.4.22+318 ✓ 4m12s`). Búsqueda global sobre todos los proyectos
gestionados, y exportación a markdown.

---

## 9. Configuración por proyecto

**Regla de una sola pregunta para decidir dónde vive cada valor:** ¿este dato le hace falta a
Consola para *alcanzar* un sistema real fuera de la app — un VPS, una base, GitHub, Cloudflare, un
certificado en disco — y no tiene un valor razonable sin que vos lo hayas puesto ahí? Si sí, es
**secreto/config de proyecto**, va al `.env` del repo. Si no — si es una preferencia de cómo correr
algo, con un default sensato que la mayoría de las veces sirve tal cual (buscar puerto libre o no,
modo de bump, `dry_run`, qué paquetes de `apt` instalar) — **no es config de archivo, es un
parámetro de la capacidad** (§2), con su default en el código, editable en el formulario (⚙) de esa
capacidad, y recordable como preset en SQLite si lo repetís seguido (§8). Antes esto no estaba
resuelto: la versión anterior de este documento metía todo en un solo archivo grande porque no
existía la distinción. Con capacidades que ya tienen forma y default propio (§2), la mayoría de lo
que hoy es una constante hardcodeada en un `.py` deja de necesitar persistencia en absoluto — la
propia app es la que antes obligaba a editar el archivo a mano, y ese motivo desaparece.

Dos dominios, cada uno con un solo dueño y un solo archivo — nada de repartir entre tres lugares:

| Dominio | Vive en | Qué guarda |
|---|---|---|
| **Secretos y config de proyecto** | un archivo dentro de cada repo | solo lo que hace falta para *alcanzar* un sistema real: credenciales, identificadores de VPS/BD/GitHub/Cloudflare, rutas de certificados, el entrypoint del server. Ver lista cerrada abajo. |
| **Preferencias de la app** | SQLite en `%LOCALAPPDATA%\Consola\` (§8), tabla `presets` con `project_id` | último proyecto abierto, tamaño de ventana, y **presets de parámetros por proyecto** — el default de un formulario que quedó guardado porque lo tocaste y confirmaste "recordar". Nunca hace falta para que un botón corra: si no hay preset, corre con el default del código. |

Nada de Credential Manager ni de ninguna otra API específica de un sistema operativo. Consola tiene
que poder correr en Windows, Linux o Mac sin que el modelo de datos cambie — así que todo lo que
persiste es un archivo de texto (por repo) o una base SQLite (de la app), portables los dos.

### El archivo de configuración es un `.env`, como hoy — pero mucho más chico

Nada de TOML: mismo formato que `scripts/.env`, mismo parser que ya centraliza `scripts/common.py`
(`load_env_file`, `require_env`, `require_port_env`, `require_bool_env` — hoy ya viven una sola vez
ahí, en vez de copiadas por script; en Consola pasa a `core/envfile.py`, nivel 0 de §2.1). Vive en
`.consola/config.env`, dentro del repo: una carpeta propia en vez de tirar el archivo suelto en la
raíz, para no chocar con el `.env` que ya pueda tener el proyecto y para que sea obvio qué es de
Consola y qué no. `.consola/` se agrega al `.gitignore` del repo — igual que hoy `.env` nunca se
commitea. No hay separación entre "configuración" y "secreto" *dentro de este archivo*: es un solo
archivo, como el que ya usás — la separación real es entre este archivo y todo lo que **no** entra
en él (arriba).

Confirmado el 2026-08-21 sobre el `.env` real del repo: esta es la lista completa que sobrevive —

```env
# .consola/config.env — generado/editado por Consola, no a mano

# Server
API_URL=https://equipaggio.net:443

# Cloudflare
CF_API_TOKEN=
CF_DOMAIN_NAME=
CF_RECORD_NAME=

VPS_PYTHON=server/.venv/bin/python

# VPS
VPS_IP=
ROOT_USER=
VPS_USER=
VPS_KEY_NAME=
DB_NAME=
DB_PASSWORD=
PG_SUPERUSER=
PG_PASSWORD=

# GitHub
GIT_REPO_URL=
GITHUB_TOKEN=
GITHUB_KEY_TITLE=
VPS_DEPLOY_DIR=

# Systemd (fallback si las constantes de install_systemd_service quedan vacías)
SERVER_DIR=server
CERT_FILE_PATH=server/certs/cert.pem
KEY_FILE_PATH=server/certs/key.pem
UVICORN_APP=app.main:app
```

Todo lo demás que tenía el `.env` viejo (`SERVER_HOST`, `SERVER_PORT_SEARCH`, `PANEL_*`,
`BACKOFFICE_*`, `LANDING_*`, `RUN_REMOTE`, `TERMINAL_DEV_AUTO_LOGIN`, `SETUP_SCRIPTS`) sale del
archivo y pasa a ser parámetro de capacidad:

| Ya no vive en `.env` | Pasa a ser | Por qué ya no hace falta persistirlo a mano |
|---|---|---|
| `SERVER_HOST`, `*_PREFERRED_PORT`, `*_PORT_SEARCH` | campos de `serve_backend` / `serve_vite_app` (§5), con default | son preferencias de cómo levantar el proceso, no datos para alcanzar algo externo |
| `RUN_REMOTE` (hoy en `common.py`: un solo flag que decide local vs. VPS para media docena de scripts vía `maybe_dispatch_remote()`) | el eje `scope` (`local`/`remoto`) de §2.4, con el último valor usado recordado como preferencia por proyecto | es exactamente el patrón que §2.4 ya anticipaba con el segmentado de encabezado — `common.py` termina de confirmarlo, no lo contradice |
| `SETUP_SCRIPTS` (lista de scripts de `database/`: `bootstrap_db.py`, `rebuild_db.py`, …) | el eje `script` descubierto de `run_remote_script` (§5, fila 🧩 "Correr setup remoto") — se lista sola desde `database/`, no hace falta escribirla | ya no es una constante a mano: es descubrimiento de archivos, igual que `target` en §2.4 |
| `TERMINAL_DEV_AUTO_LOGIN` | campo de `open_terminal` | preferencia de un launcher, no dato para alcanzar un sistema externo |
| `CERT_FILE_PATH`/`KEY_FILE_PATH` (duplicados hoy entre systemd fallback y backend) | quedan **una sola vez**, en la lista de arriba — `serve_backend` los lee de ahí, no de una segunda copia | evita la duplicación que tenía el `.env` viejo entre configuración de systemd y de backend |

### El esquema es una sola declaración con dos consumidores

Cada clave del `.env` reducido se declara una vez, junto a su tipo, su grupo y qué acciones la
necesitan — la lista es más corta que antes, así que el esquema también:

```python
setting("VPS_IP", group="VPS", label="IP del servidor", type=str,
        required_by=["ssh_login", "run_remote_script", "update_remote", …])
setting("DB_PASSWORD", group="VPS", type=str, secret=True,
        required_by=["ensure_remote_venv", "backup_database"])
setting("CF_API_TOKEN", group="Cloudflare", label="API token", type=str,
        secret=True, required_by=["update_cloudflare"])
```

De esa declaración salen dos cosas (no tres — acá no hay "consumidor" de Credential Manager):

1. **El formulario de Configuración** — mismo motor tipo→widget que ya genera los formularios de
   parámetros (§2): `bool` → switch, puerto → spinner con rango, ruta → selector de carpeta,
   `secret=True` → campo enmascarado con botón de revelar.
2. **Validación previa.** Consola sabe qué necesita cada acción *antes* de ejecutarla: un botón con
   configuración incompleta se muestra en ámbar y lista lo que falta, en vez de morir a mitad de
   flujo con `[ERROR] Falta variable de entorno: VPS_IP` como hoy. `secret=True` además enmascara
   el valor en la consola y en el log guardado.

`required_by` es por **capacidad completa** — sirve para settings que toda la capacidad necesita
sin importar qué botón se apriete (`VPS_USER` lo necesita cualquier valor de `run_remote_script`).
Cuando la necesidad depende de *qué botón* dentro de la misma capacidad (el segmentado local/remoto
de §2.4), se declara con `requires` en el eje, no acá — son dos niveles del mismo mecanismo, no dos
mecanismos distintos.

### La vista de Configuración

Reemplaza a la pestaña `.env` del mockup (§0). No es un editor de texto: es el formulario generado,
agrupado por categoría — pero sigue editando el mismo `.consola/config.env`, nada más que sin
obligarte a abrirlo a mano. Cada campo muestra si tiene valor o si falta, y cada acción tiene un
engranaje que abre la Configuración filtrada a sus propias claves.

### Importación desde `scripts/.env`

Para los repos que ya lo tienen: Consola lee `scripts/.env`, mapea las claves conocidas a
`.consola/config.env`, muestra el resultado y recién entonces escribe — mismo patrón de simulacro
que los destructivos (§7, punto 5). Para un repo sin nada, Consola detecta la forma del proyecto
(`panel/package.json`, `app/pubspec.yaml`, `server/`) y propone un archivo inicial para revisar y
guardar.

### `server/.env` no se toca

Sigue siendo, como hoy, del servidor: lo escribe y lo lee su propio código, no Consola. Dos acciones
ya necesitan leerlo hoy (`ssh_tunnel_postgres.py` para `DATABASE_URL`, `backup_database.py` para
`POSTGRES_DB`) y eso se mantiene igual — pero **solo lectura, nunca escritura**. Si `core/envfile.py`
alguna vez necesita abrir `server/.env`, es exclusivamente para leer esas dos claves puntuales, nunca
para modificarlo. Una falla en Consola puede en el peor caso corromper `.consola/config.env` (texto
plano, recuperable, y ni siquiera commiteado) o el índice SQLite de preferencias (solo caché) — nunca
`server/.env`, porque no hay ningún camino de escritura hacia ese archivo en todo el diseño.

---

## 10. Etapas de desarrollo

No se porta el catálogo completo de una vez, y **la UI se construye antes que la funcionalidad real**
— es la etapa 1, no un subproducto de "hacer que algo funcione primero". La razón: el catálogo de
capacidades + ejes (§2, §5) es una hipótesis sobre cómo se agrupan y varían las 20 y pico capacidades,
y esa hipótesis se revisa mejor mirando el rail completo, con secciones, botones y formularios reales
en pantalla, que leyendo una tabla en este documento. Corregir "esto debería ser un botón en el menú,
no uno grande" es barato antes de escribir la función real; es caro después.

1. **UI completa, sin backend real** — `main_window.py` (rail | pestañas | barra de estado),
   `console_view.py`, `param_form.py`, `settings_view.py`, y `core/registry.py` con **todo** el
   catálogo de §5 declarado como metadata (grupo, sección, ejes, `expand`, `kind`) pero con el cuerpo
   de cada función reemplazado por un *stub*: abre una pestaña, escribe
   `[INFO] <capacidad> — aún no implementada` y cierra. Ningún `subprocess`, ningún archivo tocado.
   Esta etapa valida el catálogo entero de un vistazo: cuántas secciones entran en el rail sin
   scrollear demasiado, si el eje `target` descubierto realmente arma 1/2/3 botones según el repo
   abierto (probado con datos de proyecto reales, aunque el botón no ejecute nada), si "acción
   systemd" se lee bien con 5 botones + menú, si el segmentado local/remoto de `scope` no estorba.
   *Sale: la app se puede recorrer entera — clic en cualquier botón, cualquier proyecto — y se ve,
   sin que nada corra de verdad todavía. Es el punto para ajustar el catálogo antes de programarlo.*

2. **Núcleo funcional** — `TaskContext`, runner con cancelación, árbol de PIDs, `core/envfile.py`,
   esquema de configuración real (§9), SQLite. Se reemplazan los stubs de dos o tres capacidades de
   prueba (nivel 0 + nivel 1) por implementación real, validando streaming, cancelación y que un eje
   `expand="buttons"` sigue funcionando igual ahora que el botón hace algo de verdad.
   *Sale: la app abre, se configura un proyecto sin tocar archivos, corre algo y se puede cancelar.*

3. **Launchers + Utils** — primeras capacidades de nivel 0/1 reales fuera de las de prueba: valida
   los dos modos base (en vivo / una vez), el eje `target` descubierto de `serve_vite_app` (§2.4), el
   traspaso de `SERVER_PORT` como estado de sesión entre backend y terminal (§7, punto 4), y la
   importación de `scripts/.env` a `.consola/config.env`.
   *Sale: uso diario para levantar el entorno de desarrollo.*

4. **VPS completo** — `vps_ops`, `vps_server`, `vps_setup`, más `core/ssh.py` y `core/recipes.py`.
   Es la etapa que más ejercita el patrón de nivel 0→1→2 (§2, caso 7 en §7): `update_remote`,
   `setup_ssh_key`, `setup_github_ssh`, `install_systemd_service` y `run_scripts` reemplazan sus
   stubs por atómicas reales + compuesta real, reusando las funciones comunes de `core/ssh.py` en vez
   de repetir la resolución de llave/target en cada una. Valida confirmaciones, destructivos, logs
   infinitos, salida a terminal externa.
   *Sale: operación del VPS sin salir de la app.*

5. **Builders + Emulators** — lo más pesado: los tres builders reemplazan su stub por las atómicas
   reales (`bump_version`, build, `upload_to_vps`) + compuesta con rollback si falla cualquier paso;
   preset de emulador vía eje `expand="buttons"`; seguimiento por `adb`.
   *Sale: ciclo completo de build y prueba.*

6. **Base de datos** (§6) — depende de la etapa 4, porque el Explorer se conecta a través del
   servicio de fondo Túnel Postgres. Trasplante de `postgres_service.py` casi sin cambios, tablas
   `db_connections`/`db_table_folders`, pestaña con árbol de esquema + grilla de resultados.
   *Sale: Exploratore deja de ser una app aparte.*

7. **Acabado** — bitácora completa con búsqueda global sobre todos los proyectos, historial con
   logs, exportación a markdown, empaquetado a `.exe` con PyInstaller.
   *Sale: Consola.exe, con ícono, en la barra de tareas.*

---

## 11. Pendiente antes de empezar a codear

1. ~~Scripts desactualizados~~ — **en curso**: reemplazados el 2026-08-21 (`scripts/` en este repo,
   no `navetta/scripts/`). Cambios grandes respecto a la auditoría de este documento, a re-auditar
   antes de tocar §5: apareció `scripts/common.py` (917 líneas) que **ya es**, en el código real, el
   nivel 0 de §2.1 — confirma el diseño en vez de contradecirlo, y trae de regalo el patrón
   `RUN_REMOTE` + `maybe_dispatch_remote()` que valida el eje `scope` de §2.4. Se sumaron
   `database/` (`bootstrap_db.py`, `teardown_db.py`, `rebuild_db.py`, `migrate_db.py`,
   `inspect_db.py`, `run_seeders.py`, `run_mock_seeders.py`, `ssh_tunnel_postgres.py` — antes suelto
   en `vps_ops/`), `launchers/run_flet.py`, `builders/build_binary.py`, `vps_setup/bootstrap_vps.py`,
   `vps_setup/install_coturn.py`, `vps_ops/clean_vps.py`; se borraron los duplicados de raíz
   (`run_server.py`, `run_terminal.py`, `run_panel.py`, `run_backoffice.py` — tal como predecía §1),
   `clean_pycache.py`, `get_route_data.py` y `vps_ops/backup_database.py` (movido a `database/`).
   **Pendiente real:** repetir la lectura de código de §1/§5/§7 contra este `scripts/` actualizado —
   la tabla de capacidades sigue describiendo el inventario viejo en varios puntos.
2. ~~`run_panel.py` y `run_backoffice.py` sin confirmar~~ — **resuelto**: leyendo el código (no solo
   el docstring), ambos son el mismo flujo que `launchers/run_vite.py` con el prefijo de variable de
   entorno cambiado; `run_landing.py` incluso lo llama directo. Los tres caen en la capacidad
   `serve_vite_app` con eje `target` descubierto (§1, §2.4).
3. **Prioridad real de uso** — de las capacidades del catálogo (§5), cuáles se usan a diario vs. rara
   vez, para reordenar las etapas. Sigue pendiente — importa además para decidir qué pasos de una
   compuesta (caso 7, §7) merecen botón atómico propio: la regla de "se pide suelto en la vida real"
   depende de uso real, no solo de lectura de código.
4. ~~Alcance multi-proyecto sin resolver~~ — **resuelto**: con el eje `target` descubierto por
   `core/targets.py` (§2.4) no hace falta enumerar a mano qué subproyecto tiene cada uno de los 8
   repos gestionados — se detecta al abrir el proyecto. Sigue quedando por confirmar únicamente qué
   *tipos* de target hacen falta más allá de `spa-vite`/`flutter-app`/`fastapi-server` (¿hay algún
   repo con una forma de subproyecto distinta a las que ya cubre `find_project_root()` en los scripts
   auditados?).
5. **Descomposición de compuestas (caso 7, §7) por confirmar contra uso real.** La lista de qué paso
   se separa se armó leyendo el código (`update_remote.py` → 6 pasos, `setup_ssh_key.py` → 5,
   `install_systemd_service.py` → 1 + reuso de `systemd_action`, `run_scripts.py` → N según
   `SETUP_SCRIPTS`). Falta confirmar con el usuario cuáles de esos pasos sueltos realmente se piden
   solos hoy (por ejemplo: ¿alguna vez recopiás certificados sin hacer `git pull`?) — si ninguno se
   usa suelto, ese script se queda como capacidad única y el botón atómico sobra.
6. **`exploratore/` como repo.** Confirmar qué pasa con el repo original una vez fusionado: si se
   archiva, se borra, o queda como referencia histórica sin desarrollo activo (igual que se hizo con
   `navetta/scripts/`, ver §1).
7. **Otros motores además de Postgres.** Exploratore ya declaraba MySQL/SQL Server/SQLite como
   posibles a futuro. Confirmar si algún repo de los 8 gestionados los usa antes de diseñar el punto
   de extensión en `core/db.py`, o si por ahora alcanza con Postgres únicamente.

# Plancia — Plan de desarrollo

App de escritorio (PySide6) que reemplaza los scripts sueltos de `navetta/scripts/` por
**botones que ejecutan funciones**, con selector de proyectos, consolas en vivo por pestaña
y una bitácora persistente por repo.

**Principio rector: no se copian scripts, se reimplementa su comportamiento como funciones.**
Cada acción de este documento describe *qué hace* el script original (su flujo, sus validaciones,
sus efectos secundarios) para que se re-escriba como función Python nativa de Plancia — no como
una llamada a `python scripts/x/y.py` ni como el archivo pegado dentro de la app. Los scripts en
`navetta/scripts/` siguen intactos y no se tocan.

Fecha de esta versión: 2026-08-18. Basado en el estado de `navetta/scripts/` auditado el 2026-08-17.

**Referencia visual** → [Propuesta de UI (Artifact)](https://claude.ai/code/artifact/2f6393a1-a1d6-4c66-92e9-3cba9dc5b0e9)

**Scripts de referencia** → copiados a `../scripts/` para auditoría y análisis sin tocar `navetta/scripts/`.
Estos mismos scripts son la especificación de comportamiento que cada función debe reimplementar.

---

## 1. Qué reemplaza

46 archivos en `navetta/scripts/`, agrupados en 8 carpetas temáticas, se convierten en
**34 acciones** (funciones + metadata de UI). El número baja porque:

- `run_emulator_1/2/3.py` son el mismo flujo con 4 constantes distintas → 1 acción con presets.
- `view_logs.py` es un wrapper de una línea sobre `run_systemd_action.py logs` → se absorbe como
  argumento de esa acción, no como acción propia.
- Los duplicados legacy en la raíz de `scripts/` (`run_server.py`, `run_terminal.py`,
  `clean_pycache.py`) ya existen equivalentes en `launchers/` y `utils/` → una sola función cada uno.

Dos huecos detectados que hay que resolver al re-implementar (ver §6, punto 4):
`scripts/run_panel.py` y `scripts/run_backoffice.py` en la raíz no tienen equivalente en
`launchers/` — son candidatos a función propia, a confirmar con el usuario qué hacen realmente
(el análisis original no llegó a abrirlos).

---

## 2. Modelo: de script a función

Cada script de referencia se lee para extraer:

1. **Flujo** (los pasos numerados que casi todos documentan en su docstring).
2. **Validaciones y variables requeridas** (`_require_env`, `_require_int_env`, etc.).
3. **Efectos secundarios** (qué archivos escribe, qué procesos lanza, qué revierte si falla).
4. **Constantes hardcodeadas** que hoy se editan a mano en el archivo — estas se convierten en
   parámetros tipados de la función, y la UI genera el formulario (checkbox, combo, texto, ruta)
   a partir del tipo.

Ejemplo — comportamiento de `builders/build_apk.py` reimplementado como función:

```python
@action(group="Builders", name="Build APK", kind="once")
def build_apk(ctx: TaskContext, p: ApkParams) -> None:
    """
    Reimplementación del flujo de build_apk.py:
    1) Localiza Flutter (antes: FLUTTER_BIN).
    2) Incrementa versión en pubspec.yaml según bump_mode (antes: VERSION_BUMP_MODE).
    3) flutter pub get.
    4) flutter build apk --release, pasando API_BASE_URL desde app/config.json.
    5) Si copy_to_vps: sube APK + pubspec.yaml al VPS por la misma ruta relativa.
    Si cualquier paso falla, revierte el cambio de pubspec.yaml (comportamiento original).
    """
    flutter = find_flutter(ctx)
    ctx.log("Incrementando versión…")
    prev_pubspec = bump_version(p.project_dir / "pubspec.yaml", p.bump_mode)
    try:
        ctx.run([flutter, "pub", "get"], cwd=p.project_dir)
        ctx.run([flutter, "build", "apk", "--release"], cwd=p.project_dir, env=api_base_env(p))
        if p.copy_to_vps:
            upload_to_vps(ctx, local=apk_output_path(p), remote=p.remote_dir)
    except (TaskError, Cancelled):
        restore_pubspec(p.project_dir / "pubspec.yaml", prev_pubspec)
        raise
```

```python
@dataclass
class ApkParams:
    project_dir:  Path     = Path("app")        # antes: FLUTTER_PROJECT_DIR (constante)
    bump_mode:    BumpMode = "patch+build"       # antes: VERSION_BUMP_MODE (constante)
    copy_to_vps:  bool     = True                # antes: COPY_TO_VPS (constante)
    remote_dir:   str      = "/srv"              # antes: VPS_REMOTE_DIR (constante)
```

`subprocess` no desaparece: `flutter`, `ssh`, `adb`, `uvicorn` son binarios externos y se siguen
invocando. Lo que desaparece es la capa `python scripts/builders/build_apk.py` — la orquestación
vive en la función, dentro de la app.

---

## 3. Arquitectura

```
plancia/
├── core/                    — sin imports de Qt, testeable solo
│   ├── context.py           TaskContext, TaskError, Cancelled
│   ├── runner.py            pool de workers, cancelación, árbol de PIDs
│   ├── registry.py          @action → catálogo de botones
│   ├── params.py            dataclass tipado → especificación de widgets
│   ├── projects.py          los proyectos gestionados, detección, validación
│   ├── envfile.py           lee/escribe .env por proyecto, notifica cambios
│   ├── store.py             SQLite: bitácora, historial, presets
│   ├── ssh.py               resolución de llave + target SSH (hoy repetido en 12 scripts)
│   ├── android.py           SDK paths, AVD, system images (reimplementa android_emulator.py)
│   └── tasks/
│       ├── launchers.py     builders.py     emulators.py
│       ├── vps_ops.py       vps_server.py   vps_setup.py
│       └── sync.py          utils.py
├── ui/
│   ├── main_window.py       rail de acciones | pestañas | barra de estado
│   ├── console_view.py      QPlainTextEdit + parser ANSI + búsqueda
│   ├── param_form.py        formulario generado desde params.py
│   ├── notes_view.py        bitácora markdown
│   ├── history_view.py      ejecuciones pasadas, con su log
│   └── env_view.py          editor de .env por proyecto
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

## 5. Catálogo de acciones (34)

Agrupado igual que hoy, con el tipo de comportamiento que cada función necesita en la UI.

| Grupo | N | Acciones (reimplementan el comportamiento de…) | Tipo |
|---|---|---|---|
| Launchers | 7 | Backend (`run_server.py`), Vite (`run_vite.py`), Panel (`run_panel.py`), Backoffice (`run_backoffice.py`), Landing (`run_landing.py`), Flutter (`run_flutter.py`), Terminal (`run_terminal.py`) | en vivo |
| Builders | 4 | Build APK, Build ejecutable, Build Vite, Promote app | una vez |
| Emulators | 4 | Arrancar emulador (presets: 1/2/3), Gestor de AVD, Purgar AVD, Purgar imágenes de sistema | en vivo / destructivo |
| VPS · ops | 8 | Sesión SSH, Túnel Postgres, Backup DB, Health check, Comando remoto, Correr setup remoto, Revocar llave SSH, Revocar GitHub SSH | interactivo / destructivo |
| VPS · server | 3 | Instalar servicio systemd, Acción systemd (start/stop/restart/status/**logs**), Actualizar remoto | en vivo |
| VPS · setup | 4 | Software base, Refrescar known_host, Configurar llave SSH, Configurar GitHub SSH | una vez |
| Sync | 2 | Sincronizar proyectos, Verificar proyectos | destructivo |
| Utils | 5 | Limpiar artefactos, Limpiar pycache, Instalar SDK Android, Instalar SDK Flutter, Actualizar Cloudflare | una vez |

**Tipos de comportamiento:**

- **en vivo** — la pestaña queda abierta con LED verde y botón Detener mientras el proceso corre.
- **una vez** — la pestaña se cierra sola al terminar; la entrada queda en el historial.
- **destructivo** — pide confirmación escrita del nombre del objetivo antes de habilitar el botón.
- **interactivo** — no se embebe en la app; abre una terminal externa con la sesión ya armada.

---

## 6. Seis casos que definen la arquitectura

El resto de las 34 acciones es rutina de reimplementación directa. Estos seis obligan a decisiones
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

4. **Acoplamiento vía `.env`** (`run_server.py` escribe `SERVER_PORT`, `run_terminal.py` lo lee
   para construir `SERVER_URL`). Hoy funciona por casualidad de orden de ejecución.
   `core/envfile.py` es la única fuente de verdad: mantiene el archivo en memoria, emite un evento
   al escribir, y las funciones lanzadas después ven el valor nuevo.

5. **Destructivos sobre múltiples proyectos a la vez** (`sync_projects.py` reescribe archivos en
   los repos gestionados sin preguntar). Con un botón a un clic, eso es un accidente esperando.
   Simulacro obligatorio: se muestra la lista `NEW` / `DIFF` por proyecto antes de habilitar
   Aplicar. Mismo patrón para `purge_avds`, `revoke_ssh_key`, `rebuild_db`.

6. **El launcher que se reinicia solo** (`run_terminal.py` vigila archivos y mata/relanza a su
   hijo). Como función eso son dos niveles de proceso: cancelar la tarea debe matar al hijo actual
   *y* parar el vigilante. `ctx.run()` lleva el árbol de PIDs y termina de abajo hacia arriba
   (`terminate`, luego `kill` a los 5s) para no dejar procesos zombis ocupando puertos.

---

## 7. Memoria por proyecto

SQLite en `%LOCALAPPDATA%\Plancia\`, fuera de los repos gestionados (para que `sync_projects`
nunca la toque, y para que todos los proyectos compartan una sola base). Los logs completos van
a archivos aparte; en la base solo queda el índice.

| Tabla | Guarda | Se ve en |
|---|---|---|
| `projects` | ruta, nombre, color, último uso | Selector |
| `runs` | acción, parámetros, inicio, fin, código de salida, ruta del log | Historial |
| `notes` | fecha, título, markdown, etiquetas | Bitácora |
| `presets` | combinaciones de parámetros guardadas | Formularios |

La bitácora mezcla entradas manuales con entradas automáticas que las funciones dejan vía
`ctx.note()` (ej.: `Build APK v1.4.22+318 ✓ 4m12s`). Búsqueda global sobre todos los proyectos
gestionados, y exportación a markdown.

---

## 8. Etapas de desarrollo

No se porta el catálogo completo de una vez. Cada etapa deja algo usable.

1. **Núcleo** — `TaskContext`, runner con cancelación, registro de acciones, generador de
   formularios, consola con ANSI, selector de proyectos, SQLite. Dos acciones de prueba para
   validar streaming y cancelación.
   *Sale: la app abre, corre algo, se puede cancelar.*

2. **Launchers + Utils** (10 acciones) — valida los dos modos base (en vivo / una vez), el
   acoplamiento por `.env` entre backend y terminal, y el árbol de PIDs.
   *Sale: uso diario para levantar el entorno de desarrollo.*

3. **VPS completo** (15 acciones) — `vps_ops`, `vps_server`, `vps_setup`, más `core/ssh.py`.
   Valida confirmaciones, destructivos, logs infinitos, salida a terminal externa.
   *Sale: operación del VPS sin salir de la app.*

4. **Builders + Emulators** (8 acciones) — lo más pesado: builds largos con rollback, artefactos,
   presets de emulador, seguimiento por `adb`.
   *Sale: ciclo completo de build y prueba.*

5. **Sync y acabado** — las 2 de sincronización con simulacro, bitácora completa con búsqueda
   global, historial con logs, exportación, empaquetado a `.exe` con PyInstaller.
   *Sale: Plancia.exe, con ícono, en la barra de tareas.*

---

## 9. Pendiente antes de empezar a codear

1. **Scripts actualizados.** El usuario indicó que `navetta/scripts/` está desactualizado respecto
   a lo que realmente usa — hay que reimplementar desde la versión vigente, no desde la auditada.
2. **`run_panel.py` y `run_backoffice.py`** de la raíz de `scripts/` no se llegaron a abrir en el
   análisis original — confirmar su flujo antes de reimplementarlos como funciones.
3. **Prioridad real de uso** — de las 34 acciones, cuáles se usan a diario vs. rara vez, para
   reordenar las etapas.
4. **Alcance multi-proyecto** — si el catálogo de acciones es idéntico para todos los repos
   gestionados o si cada proyecto habilita un subconjunto (`build_apk` asume una carpeta `app/`
   que no todos los repos tienen).

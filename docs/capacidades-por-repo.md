# Capacidades por repo — qué se muestra, con qué variantes y qué se persiste

Complementa `PLAN.md` §2.4 (ejes), §8 (memoria) y §9 (configuración). Responde tres preguntas que
quedaron abiertas al pasar los repos a pestañas de primer nivel:

1. ¿Cómo se decide **qué botones** mostrar para un repo?
2. ¿Dónde se **persiste el icono** (y el color) de cada repo?
3. ¿Cómo se decide **qué variantes de eje** existen en cada repo?

Fecha: 2026-08-23.

---

## 0. Una sola pieza resuelve las tres: el perfil del repo

Al abrir (o reescanear) un repo, Consola arma un `RepoProfile` en `core/profile.py`. Todo lo que la
UI necesita para decidir sale de ahí — el rail nunca consulta el disco por su cuenta.

```python
@dataclass(frozen=True)
class Target:
    id: str        # 'panel', 'app_repartidor'  — nombre de carpeta
    kind: str      # 'spa-vite' | 'flutter-app' | 'flet-app' | 'fastapi-server' | 'android-app'
    path: str      # relativa a la raíz del repo
    label: str     # para el botón; por defecto == id

@dataclass(frozen=True)
class RepoProfile:
    project: Project
    targets: tuple[Target, ...]     # escaneo de archivos      (§3)
    env_keys: frozenset[str]        # claves con valor en .consola/config.env
    tools: frozenset[str]           # binarios presentes: flutter, adb, ssh, psql…
    hidden_targets: frozenset[str]  # ocultados a mano por el usuario
```

Tres fuentes, tres dueños distintos, y ninguna se mete en el terreno de la otra:

| Fuente | Responde | Vive en |
|---|---|---|
| Escaneo de marcadores | *qué hay* en el repo | el repo (solo se lee) |
| `.consola/config.env` | *a qué sistemas externos alcanza* | el repo (§9) |
| SQLite `%LOCALAPPDATA%\Consola\` | *cómo lo quiero ver y operar yo* | la app (§8) |

---

## 1. Qué botones se muestran

**La capacidad declara sus condiciones; la UI solo las evalúa.** El rail no tiene una sola línea de
`if repo == 'navetta'`. Se extiende `Capability` con tres campos declarativos:

```python
Capability(
    id='serve_vite', name='Servir SPA', group='Launchers',
    applies_to='spa-vite',                       # un botón por target de ese tipo
    requires_tool={'node'},                      # binarios que deben existir
    requires_env=set(),                          # claves de config que deben tener valor
)

Capability(
    id='update_remote', name='Actualizar remoto', group='VPS · server',
    requires_env={'VPS_IP', 'VPS_USER', 'VPS_KEY_NAME'},
    requires_tool={'ssh'},
)
```

De ahí salen **tres estados**, y la distinción entre los dos primeros es la decisión importante:

| Estado | Cuándo | Cómo se ve |
|---|---|---|
| **Inaplicable** | `applies_to` no encontró ningún target | **Oculto.** No hay nada que construir; el botón sería mentira. |
| **Incompleto** | Hay target, pero falta config o herramienta | **Visible, en ámbar, deshabilitado**, con el faltante en el tooltip y clic → Configuración (o → la capacidad que lo instala, ej. `install_flutter_sdk`). |
| **Disponible** | Todo resuelto | Normal. |

Que "incompleto" siga visible es deliberado: si se oculta lo que falta configurar, el usuario no
tiene forma de descubrir que existe ni de saber qué le falta. Es el mismo criterio que ya usa
`PLAN.md` §2.4 para `requires` por valor de eje (el segmentado "remoto" en ámbar mientras "local"
funciona), aplicado a la capacidad entera.

Una sección del rail cuyas capacidades quedaron todas inaplicables no se dibuja. Un repo que es solo
un server FastAPI no muestra el grupo Emulators, y eso limpia el rail sin configurar nada.

**Override manual.** Encima de todo, el usuario puede ocultar o fijar capacidades por repo (menú
contextual del botón → "Ocultar en este repo"). Va a SQLite, tabla `project_capabilities
(project_id, capability_id, hidden, pinned)`, y siempre hay un "Mostrar todo" en el pie del rail —
una preferencia que no se puede revertir es una trampa.

### Marcadores de detección

`core/targets.py` recorre la raíz y un nivel de subcarpetas (no el árbol entero: es rápido y los 8
repos gestionados tienen esa forma):

| `kind` | Marcador |
|---|---|
| `spa-vite` | `package.json` + `vite.config.{js,ts,mjs}` |
| `flutter-app` | `pubspec.yaml` con `flutter:` en `dependencies` |
| `flet-app` | `pyproject.toml`/`requirements.txt` que mencione `flet` |
| `fastapi-server` | módulo con `FastAPI(` + `.venv`/`requirements.txt` hermano |
| `android-app` | `android/build.gradle` o `settings.gradle` |

Agregar un tipo nuevo es agregar una fila a esta tabla, no tocar el catálogo ni la UI.

---

## 2. Iconos y colores de repo — dónde se persisten

**Van a SQLite, tabla `projects`, junto a ruta/nombre/color/último uso que ya define §8.** Se agrega
una columna `icon`.

El razonamiento, aplicando la regla de §9 ("¿hace falta para alcanzar un sistema real?"):

- **No van a `.consola/config.env`.** Ese archivo es para lo que permite alcanzar un VPS, una base,
  GitHub. Un emoji no alcanza nada. Y hay un argumento que cierra el caso: `.consola/` está en el
  `.gitignore` del repo, así que **poner el icono ahí no lo haría viajar a otra máquina** — se
  ganaría cero portabilidad a cambio de ensuciar el archivo de secretos.
- **No van a un archivo nuevo commiteable.** Sería el único archivo que Consola pide commitear, y
  para decidir un emoji. El costo de "ahora todo repo gestionado tiene un archivo de Consola
  versionado" no lo paga el beneficio.
- **Sí van a la app**, porque son exactamente eso: preferencia de presentación de esta máquina, del
  mismo tipo que el orden de las pestañas o el último repo abierto.

**Nunca arrancan vacíos.** Al añadir un repo con `+`, el escaneo (§0) ya sabe qué hay dentro, así que
el icono se siembra por stack dominante y el color sale de la paleta rotativa:

| Stack dominante | Semilla |
|---|---|
| `flutter-app` | 🦋 |
| `spa-vite` | 🌐 |
| `fastapi-server` | 🐍 |
| `flet-app` | 📱 |
| varios tipos | 📦 |
| ninguno reconocido | 📁 |

**Se editan** desde el menú contextual de la pestaña del repo → "Icono y color…": un selector de
emoji con búsqueda + la paleta de colores. Se guarda al confirmar, se aplica en caliente.

Dónde se ve el icono: cabecera del rail, pantalla de bienvenida y barra de estado. **No en la
pestaña** — ahí compite con el nombre y con la X de cerrar, y el color del contorno ya identifica el
repo mejor que un emoji de 14px.

---

## 3. Qué variantes de eje existen en cada repo

**Regla de decisión, una sola pregunta:**

> ¿El valor existe por **lo que hay en este repo**, o por **lo que la herramienta sabe hacer**?

| Origen | Ejemplo | Cómo se declara |
|---|---|---|
| Lo que hay en el repo | `panel` \| `backoffice` \| `landing`; `app_cliente` \| `app_repartidor` | `values=discover(kind='spa-vite')` — descubierto |
| Lo que la herramienta sabe hacer | `start` \| `stop` \| `restart`; `patch` \| `minor` \| `major`; `local` \| `remoto` | lista literal — universal del dominio |

`systemd` acepta `start|stop|restart` en cualquier repo, así que enumerarlo es correcto. Ningún repo
"tiene" un `landing` por definición, así que enumerarlo sería adivinar. Los dos casos que preguntas
caen del lado descubierto y se resuelven solos:

```python
# repo sin landing → discover devuelve 2 targets → 2 botones
axis('target', of=serve_vite, values=discover(kind='spa-vite'), expand='buttons')

# repo con dos apps Flutter → 2 targets → 2 botones, nombrados por carpeta
axis('app', of=run_mobile, values=discover(kind='flutter-app'), expand='buttons')
```

Reglas de render, para que el resultado no quede raro en los extremos:

- **0 valores** → la capacidad entera queda *inaplicable* y no se dibuja (§1).
- **1 valor** → un botón **sin sufijo**: "Servir SPA", no "Servir SPA panel". El sufijo existe para
  desambiguar; con un solo target no desambigua nada, solo hace ruido.
- **2–4 valores** → `expand='buttons'`, uno por valor.
- **5 o más** → el primero como botón y el resto al menú `⋯` de la sección, ordenados por uso
  reciente (que ya está en la tabla `runs` de §8). Un rail con nueve botones de Flutter deja de ser
  navegable.

**Corregir el descubrimiento sin inventar un archivo.** El escaneo se puede equivocar (una carpeta
`docs/` con `package.json` que no es una SPA, o una app que vive fuera del patrón). La corrección va
a SQLite, tabla `project_targets (project_id, target_id, hidden, manual_kind, label)`, editable desde
"Reescanear…" en el menú del repo: una lista con casilla por target detectado, más un botón para
agregar uno a mano. Otra vez, no toca `.consola/config.env`: ocultar un target es preferencia, no
credencial.

**Cuándo se escanea.** Al abrir el repo por primera vez en la sesión, y a pedido con "Reescanear".
El resultado se cachea en `project_targets` con el `mtime` de los marcadores; si cambió, se
reescanea solo. No hay watcher de filesystem: agregar una SPA nueva es algo que pasa una vez cada
varios meses y un botón explícito cuesta menos que un observador corriendo siempre.

---

## 4. Qué hay que tocar en el código actual

| Archivo | Cambio |
|---|---|
| `core/targets.py` | **nuevo** — marcadores, escaneo, `discover(kind=...)` |
| `core/profile.py` | **nuevo** — `RepoProfile`, resolución de estado por capacidad |
| `core/registry.py` | `Capability` gana `applies_to`, `requires_env`, `requires_tool`; `AxisDef.values` acepta `list[str] \| TargetQuery` |
| `core/store.py` | **nuevo** — SQLite: `projects.icon`, `project_capabilities`, `project_targets` |
| `core/catalog.py` | los ejes de `serve_vite`, `run_mobile`, `build_vite` pasan a `discover(...)`; el resto queda literal |
| `ui/rail.py` | `populate(profile)` en vez de `populate()`; estado ámbar para *incompleto* |
| `ui/project_tabs.py` | menú contextual: "Icono y color…", "Reescanear…" |

Nada de esto rompe el esqueleto actual: hoy `populate()` ya arma botones a partir de los ejes, solo
que los ejes son listas literales. Cambiar la fuente de esos valores no cambia el código que dibuja.

# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-18).** Canone sacó `qt.md` de desarrollo (`461d857` y `e6b3d0b` de
> canone): ahora rige entera, salvo su sección «Tema», que sigue en desarrollo. Con canone en `main`
> (`ff38d25`, que comprueba el árbol, ADR-0188 y ADR-0189 de canone), `verificar.py --repo .` da 1
> incumplimiento: `ui/`, que falta repartir (§2.2). En Windows, `ruff format --check`, `ruff check`,
> `pyrefly check` en las dos plataformas y `deptry` dan 0, y pasan 1014 pruebas, con 3 saltadas.
> Ya hecho: el código en inglés, `ruff` con las reglas de `plantilla/qt/`, las versiones de
> `stack.md`, los tipos, `@override`, los enums con su clase, `IniFormat`, HTTP con un solo
> `QNetworkAccessManager` y reintentos
> ([ADR-0089](../adr/0089-http-va-por-un-solo-manager-en-el-hilo-de-la-interfaz-y-reintenta.md)),
> `release.yml` ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)) y `api/`
> ([ADR-0080](../adr/0080-las-respuestas-http-se-leen-con-modelos-en-api.md)). El objetivo sale del
> [ADR-0075](../adr/0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md); lo
> que hay está en [arquitectura](../arquitectura/README.md), y si este plan no coincide con ella, manda
> ella.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/python.md`, `canone/plataformas/qt.md` y este plan.

## 1. Cómo se comprueba

Desde `desktop/`, lo mismo que corre el CI:

```bash
uv run ruff format --check
uv run ruff check
uv run pyrefly check
uv run pyrefly check --python-platform linux
uv run deptry .
QT_QPA_PLATFORM=offscreen PYTHONDEVMODE=1 PYTHONWARNDEFAULTENCODING=1 uv run pytest
```

Desde la raíz: `python ../canone/scripts/verificar.py --repo .`

Las pruebas no tocan la ventana entera. Después de mover archivos o conexiones hay que abrirla sin
pantalla y apretar sus señales.

## 2. Lo que falta

Rige desde que `qt.md` salió de desarrollo. En este orden: cada etapa deja el repo en verde y lleva
su commit. Los conteos salen de buscar en el código (2026-11-17); lo de accesibilidad no se probó con
la app.

### 2.2 Estructura de `ui/`

Ya hecho, sin commit: `core/` es `services/`; `api/` tiene `http.py` y un módulo por servicio
(`cloudflare.py`, `flutter.py`, `android_studio.py` e `ip.py`); `assets/` tiene las imágenes, los
presets de las capturas y el kit de la cámara; `favorites`, `section_visibility`, `project_store`,
`params_store`, `readiness`, `task_runner` y `db_worker` están en `services/`; están los dos
`ruff.toml` de `plantilla/qt/`, y `pyproject.toml` prohíbe `PySide6.QtNetwork` fuera de `api/`.
`palettes.py` está en `services/`, y `parts.py` es la última sección de `theme.py`, «The parts of
the window» (pregunta 8).
`verificar.py` da 1 incumplimiento: `ui/` fuera del árbol.

Falta repartir `ui/`. `qt.md` pide `windows/`, `dialogs/`, `widgets/` y `models/`, y cada módulo de
las tres últimas declara una sola clase pública, con su nombre en snake_case. Hoy `ui/` tiene 49
clases en 28 archivos.

| Destino | Qué va |
|---|---|
| `windows/` | `MainWindow` y `_EdgeGrip` |
| `dialogs/` | `guard_dialog.py`, partido en `GuardDialog`, `BlockedDialog` y `ReminderDialog` |
| `models/` | `RowsModel`, hoy en `db_explorer_view.py` |
| `widgets/` | Los demás widgets, un archivo por clase pública. Se parten `tab_panel.py`, `title_bar.py`, `project_tabs.py`, `env_panel.py`, `params_panel.py`, `db_explorer_view.py`, `widgets/accordion.py`, `widgets/action_row.py` y `widgets/tab_reorder.py`, y `widgets/led.py` pasa a `led_indicator.py` y `menu_bar.py` a `action_menu_bar.py` |
| `services/` | `AxesLoader`, un `QThread` de `params_panel.py`, y `RepoLogo`, que no es un widget |

### 2.3 Almacenamiento

- `main.py` ya pone `IniFormat`. Falta `setOrganizationDomain`.
- La ventana principal no lee su geometría ni su estado al crearse, ni los guarda en `closeEvent()`.
- `ui/project_store.py` borra `_LEGACY_ORDER_KEY`, una clave vieja: es compatibilidad hacia atrás, y
  sale.
- **Sin verificar:** un INI devuelve texto. Los favoritos ya tratan `"true"` y una lista de un
  elemento, pero `params_store.py` y `project_store.py` no se probaron con la app.

### 2.4 PySide6, widgets, diálogos y Model/View

| Pide `qt.md` | Hoy |
|---|---|
| `@Slot` en todo método conectado a una señal | Ningún `@Slot`; unas 73 conexiones a métodos |
| Fechas y números con el `locale()` del widget | `ui/console_view.py` (`strftime`), `ui/db_explorer_view.py` (miles con `replace`) y `ui/tab_panel.py` (la RAM) |
| Un diálogo modal se abre con `open()`, nunca con `exec()` | `ui/tab_panel.py`: `BlockedDialog`, `ReminderDialog` y un `QMessageBox`. También `QFileDialog.getOpenFileName` y `getExistingDirectory`, y dos `QInputDialog.getText`, que corren `exec()` por dentro (lectura propia) |
| Vista con modelo, sin `QTreeWidget` ni `QTableWidget` | Los dos en `ui/db_explorer_view.py` |

### 2.5 Accesibilidad

- El `data()` de `RowsModel` responde `ToolTipRole`, pero no `AccessibleTextRole` ni
  `AccessibleDescriptionRole`.
- Hay 9 `paintEvent` y ninguna `QAccessibleInterface`. Falta ver cuáles dibujan contenido y cuáles
  solo decoran.
- No hay ningún `setAccessibleName` ni `setAccessibleDescription`.
- **Sin verificar:** el nivel AA de `transversal.md`, con los objetivos de 48 × 48.

### 2.7 Icono, recursos y empaquetado

- `src/app/icon.png` de 1024 × 1024 px no existe. Sale de rasterizar el rombo de la marca, el que
  pinta `ui/title_bar.py::Diamond` (pregunta 6).
- `src/app/resources.qrc` no existe. Lleva el icono y las traducciones compiladas. `rc_resources.py`
  y `*.qm` ya están en `desktop/.gitignore`.
- `desktop/pysidedeploy.spec` no existe. Sale de `plantilla/qt/`, con `title = Consola`, el `mode` en
  `onefile` y `packages = Nuitka,imageio`.
- El job `desktop` de `release.yml` sigue fallando en un tag sin el `.spec`. Contra la plantilla le
  faltan `--no-editable` en `uv sync` y en `uv run`, `--no-install` en `pyside6-deploy`, el paso que
  pone el `dumpbin` de MSVC en el `PATH` de Windows y el paso de traducciones del §2.8. Solo se
  prueba con un tag en GitHub.
- `transversal.md`, «Distribución», pide las variables de GitHub `RELEASE_DESKTOP_LINUX`,
  `RELEASE_DESKTOP_MACOS` y `RELEASE_DESKTOP_WINDOWS`. Decidido: `true`, `false` y `true`. El
  repositorio no tiene ninguna; `ci.yml` le pasa `--variables "$VARIABLES"` a `verificar.py`, con
  `toJSON(vars)`, y `release.yml` arma la matriz del job `desktop` con ellas, como la plantilla.

### 2.8 Qt Linguist

Hoy no hay ninguna llamada a `tr` ni a `translate`. Conteo por script, aproximado:

| Dónde | Textos |
|---|---|
| Llamadas directas de la interfaz (`setText`, `QLabel`…) | 118 |
| Mensajes de las tareas (`ctx.info`, `TaskError`…) | 416 |
| Declaraciones de `catalog.py`, `settings.py` y `protection.py` | 499 |
| `core/command_docs.py` | 854 líneas |

- Decidido (pregunta 5): Linguist cubre también los mensajes de `core/` y `command_docs.py`, con
  `QCoreApplication.translate`. Lleva un ADR que amplía la excepción de `core/` que no importa Qt.
- Las declaraciones se evalúan al importar, antes de instalar el traductor: necesitan
  `QT_TRANSLATE_NOOP` y traducirse al mostrarse.
- El idioma que elige el usuario se guarda en `QSettings`, y `main.py` lo aplica con
  `QLocale.setDefault()` y su `QTranslator`. Hasta que elige, es el de `QLocale.system()`.
- Los textos se extraen con `pyside6-lupdate -extensions py src/app` a `src/app/translations/`.
- El job `desktop` de `ci.yml` y el de `release.yml` compilan cada `.ts` con `pyside6-lrelease`,
  copian el `qtbase_<locale>.qm` de Qt y arman `rc_resources.py` con `pyside6-rcc`, como en la
  plantilla.
- Es la etapa más grande.

### 2.9 Lo que no aplica

El `README.md` de canone dice: «Cada proyecto elige las tecnologías que utiliza y consulta
únicamente las convenciones correspondientes. Canone responde a la pregunta "si se usa X, ¿cómo se
usa?", sin convertir su catálogo en una lista de requisitos universales». Consola no tiene
`server/` ni cuenta. Por eso quedan fuera «OpenAPI y clientes», `datamodel-code-generator`,
`api/client.py`, `api/models.py`, keyring, «Versión mínima de cliente», WebSocket y «Código de
autorización».

Tampoco rige «Tema», mientras siga en desarrollo (`plataformas/README.md`, «En desarrollo»).

## 3. Preguntas

«Dónde» dice quién lo resuelve: canone, cuando la duda es qué pide una página, y Consola cuando la
duda es cómo cumplirla.

### Decididas (2026-11-18)

| # | Pregunta | Dónde | Decisión |
|---|---|---|---|
| 1 | El árbol de `qt.md` no tenía `core/` ni `ui/`. ¿Dónde va el código que no es de Qt? | Canone | En `services/`: lo que no es interfaz ni HTTP. Ya está en `qt.md` y `flet.md` (ADR-0186 de canone). En Consola van ahí `core/` y los módulos sin widget, incluidos los dos `QThread` (§2.2). Dónde va `palettes.py` es la pregunta 8 |
| 3 | «Un solo `QNetworkAccessManager`» chocaba con el ADR-0079: cada tarea bloqueaba su hilo con su propio manager | Consola | Un solo manager en el hilo principal, y las tareas siguen bloqueando su hilo. Hecho (ADR-0089) |
| 4 | `api/client.py` y `api/models.py` suponían la API propia de un servidor. Consola habla con Cloudflare y con el índice de Flutter | Canone | `api/` es todo lo que habla HTTP, con `api/<servicio>.py` para cada servicio externo. Con un servicio externo, un campo desconocido se ignora y los que se leen se validan enteros, y «Reintentos» le aplica. Ya está en `qt.md`, `flet.md` y `transversal.md` (ADR-0186 de canone). En Consola: §2.2; los reintentos ya están (ADR-0089) |
| 5 | ¿Linguist cubre también los mensajes de `core/` y `command_docs.py`? | Consola | Sí, con `QCoreApplication.translate` (§2.8) |
| 6 | ¿De dónde sale el icono de 1024 px? | Consola | Del rombo de la marca, rasterizado (§2.7) |
| 7 | El árbol de `qt.md` no tenía lugar para lo que no es código | Canone | En `src/app/assets/`: las imágenes entran en `resources.qrc`, y lo que otro programa lee del disco se queda como archivo (ADR-0189 de canone) |
| 8 | `palettes.py` y `parts.py` no tenían lugar en el árbol | Consola | `palettes.py` en `services/`, y `parts.py` como sección de `theme.py`, donde se ubican y cambian los colores de cada parte (§2.2) |

### Abiertas

| # | Pregunta | Dónde | Recomendación |
|---|---|---|---|
| 2 | `qt.md` pide copiar `tests/test_theme.py` sin editar, pero prueba reglas de «Tema», que sigue en desarrollo. Consola tiene 169 `setStyleSheet` fuera de `theme.py` y no tiene `colors.py`, así que fallaría | Canone | Que `qt.md` diga lo mismo que `flet.md`: «`theme.py` y `tests/test_theme.py` … en desarrollo como esta sección: no se copian», con las filas de Fusion y de la hoja única marcadas como de «Tema». Pendiente por decisión del usuario |

## 4. Sin verificar

- `core/http.py` y `api/cloudflare.py` contra el servicio real: leer necesita un token y escribir cambia
  el DNS. Se probó contra un servidor local y con respuestas simuladas.

## 5. Al terminar

Las decisiones pasan a ADR, el resultado a `arquitectura/`, sale la fila del 30 y se borra este plan.

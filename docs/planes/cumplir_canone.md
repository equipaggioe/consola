# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-17).** La rama `cumplir-canone` ya está en `main`. Canone sacó
> `qt.md` de desarrollo (`461d857` y `e6b3d0b` de canone): ahora rige entera, salvo su sección
> «Tema», que sigue en desarrollo. Con canone en `java-ci` (`0a33150`, más cambios sin commitear en
> `qt.md` y `transversal.md`), `verificar.py --repo .` da 10 incumplimientos, todos de versión
> (§2.1). En Windows, `ruff check` da un error (W505 en `ui/parts.py`), `pyrefly check` da 0 y pasan
> 1008 pruebas, con 3 saltadas, corridas desde `.venv`: con uv 0.13.9 instalado, `uv run` se niega
> mientras `pyproject.toml` pida la 0.13.7. Ya hecho: el código en inglés, `ruff`, los tipos,
> `@override`, los enums con su clase, `IniFormat`, HTTP con `QNetworkAccessManager`
> ([ADR-0079](../adr/0079-http-bloquea-el-hilo-de-la-tarea.md), propuesta), `release.yml`
> ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)) y `api/`
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

### 2.1 Versiones y `pyproject.toml`

Lo que pide `stack.md` y `verificar.py` marca:

| Paquete | Hoy | Pide |
|---|---|---|
| uv y `uv_build` | 0.13.7 | 0.13.9 |
| pyside6 | 6.11 | 6.12.0 |
| pillow | 12.0 | 13.0.0 |
| pyrefly | 1.4.0 | 1.4.1 |
| ruff | 0.17.3 | 0.17.5 |
| pytest-qt | 4.5 | 4.5.0 |
| imageio | 2.38 | 2.38.2 |
| nuitka | 4.1 | 4.3.5 |
| patchelf | 0.19 | 0.19.3.0 |

Contra `plantilla/qt/pyproject.toml`:

- Faltan las reglas `B012`, `B904`, `PYI061`, `RET501`, `RET502` y `RET503`. Hoy no dan ningún error.
- Falta `http.client` en `banned-api`.
- Sobra `S502`, que la plantilla no lleva.
- Corregir el W505 de `ui/parts.py`.

### 2.2 Estructura de `ui/`

`qt.md` pide `windows/`, `dialogs/`, `widgets/` y `models/`, con un archivo por clase, y su árbol no
tiene `core/` ni `ui/` (pregunta 1). Hoy `ui/` tiene 43 clases de Qt en 28 archivos. El cambio toca
64 líneas de import, 63 líneas de código que citan `ui/<archivo>.py` y 23 citas en
`docs/arquitectura/`.

| Destino | Qué va |
|---|---|
| `windows/` | `MainWindow` y `_EdgeGrip` |
| `dialogs/` | `guard_dialog.py` |
| `models/` | `RowsModel`, hoy en `db_explorer_view.py` |
| `widgets/` | Los demás widgets. `tab_panel.py`, `title_bar.py`, `project_tabs.py`, `env_panel.py` y `params_panel.py` se parten por clase |
| Sin decidir | Lo que no es un widget, y `core/` (pregunta 1) |

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

### 2.6 Red

`qt.md` pide un solo `QNetworkAccessManager` con `setAutoDeleteReplies(True)`. `core/http.py` crea
uno por petición, en el hilo de la tarea, y libera la respuesta con `deleteLater()`. Depende de la
pregunta 3.

### 2.7 Icono, recursos y empaquetado

- `src/app/icon.png` de 1024 × 1024 px no existe (pregunta 6).
- `src/app/resources.qrc` no existe. Lleva el icono y las traducciones compiladas. `rc_resources.py`
  y `*.qm` ya están en `desktop/.gitignore`.
- `desktop/pysidedeploy.spec` no existe. Sale de `plantilla/qt/`, con `title = Consola`, el `mode` en
  `onefile` y `packages = Nuitka,imageio`.
- El job `desktop` de `release.yml` sigue fallando en un tag sin el `.spec`. Contra la plantilla le
  faltan `--no-editable` en `uv sync` y en `uv run`, `--no-install` en `pyside6-deploy`, el paso que
  pone el `dumpbin` de MSVC en el `PATH` de Windows y el paso de traducciones del §2.8. Solo se
  prueba con un tag en GitHub.

### 2.8 Qt Linguist

Hoy no hay ninguna llamada a `tr` ni a `translate`. Conteo por script, aproximado:

| Dónde | Textos |
|---|---|
| Llamadas directas de la interfaz (`setText`, `QLabel`…) | 118 |
| Mensajes de las tareas (`ctx.info`, `TaskError`…) | 416 |
| Declaraciones de `catalog.py`, `settings.py` y `protection.py` | 499 |
| `core/command_docs.py` | 854 líneas |

- Las declaraciones se evalúan al importar, antes de instalar el traductor: necesitan
  `QT_TRANSLATE_NOOP` y traducirse al mostrarse.
- El idioma que elige el usuario se guarda en `QSettings`, y `main.py` lo aplica con
  `QLocale.setDefault()` y su `QTranslator`. Hasta que elige, es el de `QLocale.system()`.
- Los textos se extraen con `pyside6-lupdate -extensions py src/app` a `src/app/translations/`.
- El job `desktop` de `ci.yml` y el de `release.yml` compilan cada `.ts` con `pyside6-lrelease`,
  copian el `qtbase_<locale>.qm` de Qt y arman `rc_resources.py` con `pyside6-rcc`, como en la
  plantilla.
- Es la etapa más grande y la que más toca `core/` (pregunta 5).

### 2.9 Lo que no aplica

Es lectura propia, sin confirmar con canone. Consola no tiene `server/` ni cuenta. Por eso quedan
fuera «OpenAPI y clientes», `datamodel-code-generator`, keyring, «Versión mínima de cliente»,
WebSocket y «Código de autorización». Tampoco «Tema», mientras siga en desarrollo.

## 3. Preguntas abiertas

Nada de esto está decidido; las recomendaciones son propuestas. «Dónde» dice quién lo resuelve:
canone, cuando la duda es qué pide una página, y Consola cuando la duda es cómo cumplirla.

| # | Pregunta | Dónde | Recomendación |
|---|---|---|---|
| 1 | El árbol de `qt.md` no tiene `core/` ni `ui/`, y canone muestra el árbol completo como la regla. ¿Dónde van `core/` y los módulos sin widget (`favorites`, `section_visibility`, `project_store`, `params_store`, `readiness`, `palettes`, `task_runner`, `db_worker`)? | Canone | Que `qt.md` diga dónde va el código que no es de Qt. Sin eso: `state/` para los cuatro primeros, `palettes.py` junto a `theme.py`, y los dos hilos en `core/` |
| 2 | `qt.md` pide copiar `tests/test_theme.py` sin editar, pero prueba reglas de «Tema», que sigue en desarrollo. Consola tiene 169 `setStyleSheet` fuera de `theme.py` y no tiene `colors.py`, así que fallaría | Canone | Que `test_theme.py` se exija recién cuando «Tema» salga de desarrollo. `verificar.py` ya no lo exige |
| 3 | «Un solo `QNetworkAccessManager`» choca con el ADR-0079: cada tarea bloquea su propio hilo con un manager, y un manager vale solo en el hilo que lo creó. ¿Se confirma el ADR-0079, y entonces canone admite un manager por hilo, o HTTP pasa a señales en el hilo principal? | Consola, y canone si queda una excepción | Sin recomendación: confirmar el ADR-0079 deja las tareas legibles de arriba abajo, pero pide una excepción en `qt.md` |
| 4 | `api/client.py` y `api/models.py` suponen la API propia de un servidor. Consola tiene `api/cloudflare.py` y `api/flutter.py`, que hablan con APIs externas | Canone | Que `qt.md` diga dónde va el cliente de una API externa |
| 5 | ¿Linguist cubre también los mensajes de `core/` y `command_docs.py`? `core/` no importa Qt, salvo excepciones | Consola | Sí, con `QCoreApplication.translate`: `transversal.md` pide un producto multilingüe. Exige un ADR que amplíe la excepción de `core/` |
| 6 | ¿De dónde sale el icono de 1024 px? Solo hay `ui/assets/equipaggio.png`, de 400 × 400, y agrandarlo lo deja borroso | Consola | Que lo entregues tú, o rasterizar el rombo de la marca si es el icono que quieres |

## 4. Sin verificar

- `core/http.py` y `api/cloudflare.py` contra el servicio real: leer necesita un token y escribir cambia
  el DNS. Se probó contra un servidor local y con respuestas simuladas.

## 5. Al terminar

Las decisiones pasan a ADR, el resultado a `arquitectura/`, sale la fila del 30 y se borra este plan.

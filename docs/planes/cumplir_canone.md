# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-04).** En la rama `cumplir-canone`, sin empujar. Hecho: `ruff format`,
> `ruff check`, los tipos de Pyrefly con `@override`, y el código en inglés, con la redacción de los
> docstrings revisada. HTTP pasó a
> `QNetworkAccessManager` ([ADR-0079](../adr/0079-http-bloquea-el-hilo-de-la-tarea.md), propuesta). La
> sección «Tema» no se implementa porque canone la declara en desarrollo (ADR-0116 de canone); lo
> recuerda su fila en el [30](../arquitectura/30_riesgos_y_pendientes.md). También están `release.yml`
> ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)) y `api/`
> ([ADR-0080](../adr/0080-las-respuestas-http-se-leen-con-modelos-en-api.md)). Falta lo de la §2. El
> objetivo sale del
> [ADR-0075](../adr/0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md); lo
> que hay está en [arquitectura](../arquitectura/README.md), y si este plan no coincide con ella, manda
> ella.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/python.md`, `canone/plataformas/qt.md` y este plan. Lo primero es contestar las
> preguntas de la §3.

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

El 2026-11-04 lo de `desktop/` pasó en Windows: 422 pruebas, 419 aprobadas y 3 saltadas. El job
`desktop` del CI pasó entero en Debian 13 dentro de WSL, con `pip-audit`: 422 aprobadas, ninguna
saltada. No es el runner de GitHub: las bibliotecas de Qt, git y Node se agregaron a mano. Las pruebas no tocan la
ventana entera. Después de mover archivos o conexiones hay que abrirla sin pantalla y apretar sus
señales.

## 2. Lo que falta

En este orden: cada etapa deja el repo en verde y lleva su commit.

### 2.1 Estructura de `ui/`

`qt.md` pide `windows/`, `dialogs/`, `widgets/` y `models/`, con un archivo por clase. Hoy `ui/` tiene
43 clases de Qt en 28 archivos. El cambio toca 64 líneas de import, 63 líneas de código que citan
`ui/<archivo>.py` y 23 citas en `docs/arquitectura/`.

| Destino | Qué va |
|---|---|
| `windows/` | `MainWindow` y `_EdgeGrip` |
| `dialogs/` | `guard_dialog.py` |
| `models/` | `RowsModel`, hoy en `db_explorer_view.py` |
| `widgets/` | Los demás widgets. `tab_panel.py`, `title_bar.py`, `project_tabs.py`, `env_panel.py` y `params_panel.py` se parten por clase |
| Sin decidir | Lo que no es un widget: pregunta 1 |

### 2.2 `IniFormat`

Hay 15 llamadas a `QSettings` y todas usan el constructor por defecto, así que basta
`QSettings.setDefaultFormat(QSettings.Format.IniFormat)` en `main.py`, antes del primer uso.

- **Se pierde lo guardado en el registro:** la lista de pestañas, los favoritos, las secciones ocultas
  y los datos de máquina. No se migra (`principios.md`, «En desarrollo»). Se dice al entregarlo.
- **Hay que probarlo con la app:** un INI devuelve texto. Los favoritos ya tratan `"true"` y una lista de
  un elemento, pero `params_store.py` y `project_store.py` no se probaron con ese formato.

### 2.3 Icono, recursos y empaquetado

- `src/app/icon.png` de 1024 × 1024 px no existe (pregunta 3).
- `src/app/resources.qrc` no existe. Lleva el icono y las traducciones compiladas. `rc_resources.py` ya está
  en `desktop/.gitignore`; faltan los `.qm`.
- `desktop/pysidedeploy.spec` no existe. Sale de `plantilla/qt/`, con `title = Consola`. `desktop/pyproject.toml`
  ya tiene el grupo `deploy`.
- `.github/workflows/release.yml` ya existe y necesita `pysidedeploy.spec`. Solo se prueba con un tag en
  GitHub.

### 2.4 Qt Linguist

Hoy no hay ninguna llamada a `tr` ni a `translate`. Conteo por script, aproximado:

| Dónde | Textos |
|---|---|
| Llamadas directas de la interfaz (`setText`, `QLabel`…) | 118 |
| Mensajes de las tareas (`ctx.info`, `TaskError`…) | 416 |
| Declaraciones de `catalog.py`, `settings.py` y `protection.py` | 499 |
| `core/command_docs.py` | 854 líneas |

- Las declaraciones se evalúan al importar, antes de instalar el traductor: necesitan
  `QT_TRANSLATE_NOOP` y traducirse al mostrarse.
- Los textos se extraen con `pyside6-lupdate -extensions py src/app`, y hay que instalar el `QTranslator`
  en `main.py`.
- Es la etapa más grande y la que más toca `core/` (pregunta 2).

## 3. Preguntas abiertas

Nada de esto está decidido; las recomendaciones son propuestas.

| # | Pregunta | Recomendación |
|---|---|---|
| 1 | ¿Dónde van los módulos sin widget: `favorites`, `section_visibility`, `project_store`, `params_store`, `readiness`, `palettes`, `task_runner`, `db_worker`? `qt.md` no lo dice | Una carpeta `state/` para los cuatro primeros y `palettes.py` junto a `theme.py`, con los dos hilos en `core/`, si canone no prefiere otra cosa |
| 2 | ¿Linguist cubre también los mensajes de `core/` y `command_docs.py`? `core/` no importa Qt salvo excepciones | Sí, con `QCoreApplication.translate`: `transversal.md` pide un producto multilingüe. Exige un ADR que amplíe la excepción de `core/` |
| 3 | ¿De dónde sale el icono de 1024 px? Solo hay `ui/assets/equipaggio.png` de 400 × 400, y agrandarlo lo deja borroso | Que lo entregues tú, o rasterizar el rombo de la marca si es el icono que quieres |
| 6 | ¿Se confirma el ADR-0079 (HTTP bloqueando el hilo de la tarea, en vez de señales)? | Sí: las tareas se leen de arriba abajo |
| 7 | ¿Se confirma el punto 2 del ADR-0116 de canone (`verificar.py` deja de exigir `tests/test_theme.py`)? | Sí: exigirla deja en rojo el CI de Consola y le impide publicar un release, porque `release.yml` corre primero `ci.yml` |

## 4. Antes de empujar

1. **Canone primero, y en `master`.** El job `canone` del CI clona canone desde GitHub, que todavía exige
   `tests/test_theme.py`. El ADR-0116 está en la rama local `sveltekit-3`, que lleva commits sin empujar y
   donde hay otra sesión trabajando. Sin decidir cuándo pasa a `master`.
2. Sin decidir: empujar `cumplir-canone`, abrir un PR y mirar el CI. Esta rama nunca corrió en él, y
   `ci.yml` solo corre con un push a `main`, con un PR, con `workflow_call` y por el cron.

## 5. Sin verificar

- `core/http.py` y `api/cloudflare.py` contra el servicio real: leer necesita un token y escribir cambia
  el DNS. Se probó contra un servidor local y con respuestas simuladas.

## 6. Al terminar

Las decisiones pasan a ADR, el resultado a `arquitectura/`, sale la fila del 30 y se borra este plan.

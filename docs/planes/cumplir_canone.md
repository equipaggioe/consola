# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-19).** Canone sacó `qt.md` de desarrollo (`461d857` y `e6b3d0b` de
> canone): ahora rige entera, salvo su sección «Tema», que sigue en desarrollo. Con canone en `main`
> (`8856ea4`, que comprueba el árbol, ADR-0188 y ADR-0189 de canone), `verificar.py --repo .` da 0
> incumplimientos con las tres variables `RELEASE_DESKTOP_*`. En Windows, `ruff format --check`,
> `ruff check`, `pyrefly check` en las dos plataformas y `deptry` dan 0, y pasan 1027 pruebas, con 3
> saltadas. En Linux (distro `Testing`), los pasos del job `desktop` de `ci.yml` dan 0 y pasan 1030.
> Ya hecho: el código en inglés, `ruff` con las reglas de `plantilla/qt/`, las versiones de
> `stack.md`, el árbol de `qt.md`
> ([ADR-0090](../adr/0090-el-codigo-sigue-el-arbol-de-qt-de-canone.md)), los tipos, `@override`,
> los enums con su clase, `@Slot` en los 69 métodos conectados a una señal, las fechas y los
> números con el `locale()` del widget, los diálogos con `open()`, el explorador con
> `QTreeView` y `QTableView` sobre `models/`, la accesibilidad de `qt.md`, el icono,
> `resources.qrc`, `pysidedeploy.spec`, el job `desktop` de `release.yml`, Qt Linguist
> ([ADR-0091](../adr/0091-los-textos-se-escriben-en-espanol-y-linguist-los-traduce.md)),
> `IniFormat`, HTTP con un solo
> `QNetworkAccessManager` y reintentos
> ([ADR-0089](../adr/0089-http-va-por-un-solo-manager-en-el-hilo-de-la-interfaz-y-reintenta.md)),
> `release.yml` ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)) y `api/`
> ([ADR-0080](../adr/0080-las-respuestas-http-se-leen-con-modelos-en-api.md)). El objetivo sale del
> [ADR-0075](../adr/0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md); lo
> que hay está en [arquitectura](../arquitectura/README.md), y si este plan no coincide con ella, manda
> ella.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/python.md`, `canone/plataformas/qt.md` y este plan. Falta crear las variables
> de GitHub (§2.7), el selector de idioma con el segundo idioma (§2.8) y lo que espera una decisión:
> el nivel AA (§2.5) y el §3, «Abiertas». Lo que canone tendría que cambiar está en el §4.

## 1. Cómo se comprueba

Desde `desktop/`, lo mismo que corre el CI, después de compilar las traducciones y los recursos
como dice el §1 de [03](../arquitectura/03_ejecucion_y_despliegue.md):

```bash
uv run ruff format --check
uv run ruff check
uv run pyrefly check
uv run pyrefly check --python-platform linux
uv run deptry .
QT_QPA_PLATFORM=offscreen PYTHONDEVMODE=1 PYTHONWARNDEFAULTENCODING=1 uv run pytest
```

Desde la raíz: `python ../canone/scripts/verificar.py --repo . --variables '{"RELEASE_DESKTOP_LINUX":
"true", "RELEASE_DESKTOP_MACOS": "false", "RELEASE_DESKTOP_WINDOWS": "true"}'`, como `ci.yml` con
las variables del repositorio.

Las pruebas no tocan la ventana entera. Después de mover archivos o conexiones hay que abrirla sin
pantalla y apretar sus señales.

## 2. Lo que falta

Rige desde que `qt.md` salió de desarrollo. En este orden: cada etapa deja el repo en verde y lleva
su commit. Los conteos salen de buscar en el código (2026-11-17); lo de accesibilidad no se probó con
la app.

### 2.5 Accesibilidad

Hecho: lo que pide la sección «Accesibilidad» de `qt.md`, también los atajos (pregunta 10). Está en
[12](../arquitectura/12_interfaz.md), §10.

Medido el 2026-11-19 con un script sobre la ventana abierta sin pantalla, con un repo y cuatro
pestañas de acción: 39 controles visibles. **El nivel AA no se cumple.** Lo que falla pide decisiones
de diseño:

| Criterio | Qué falla | Decisión que pide |
|---|---|---|
| 1.4.3, contraste del texto | `TEXT_MUTED` (#6b7484) da de 2,5 a 4,0 contra los cinco fondos neutros; `ERROR` da 3,6 a 4,4 sobre `SURFACE`, `SURFACE_ALT` y `CHROME`. `RUN_BUTTON_OFF` da 2,54, pero es un componente inactivo y está exento | Los colores son de «Tema», en desarrollo en canone (pregunta 13) |
| 1.4.11, contraste de lo que no es texto | `BORDER` da de 1,3 a 2,0 y `BORDER_LIGHT`, de 1,7 a 2,6 contra los fondos: el borde de un campo no llega a 3:1 | La misma |
| 2.5.8, objetivo de 24 × 24 | 16 controles: los `×` de las pestañas (18 × 18), el `✕` de apagar (20 × 20), el botón de borrar de los campos (22 × 18), los cinco candados (12 de alto), los chips de 22 de alto y dos casillas de 17 de alto | Tamaños: «Tema» pone los tamaños en `theme.py`. Y si el 48 × 48 de `transversal.md` rige en el escritorio (pregunta 14) |
| 2.1.1, todo con el teclado | 11 controles no reciben el foco: las pestañas de acción (con Ctrl+PgDown y Ctrl+PgUp), las de repo (con Ctrl+Tab y Ctrl+1 a 9), el «+» (con Ctrl+T), la estrella de favorita, los tres botones de la ventana y el botón de borrar de los campos | Si cada pestaña y cada botón de glifo reciben el foco, o bastan los atajos |
| 2.4.7, foco visible | 26 controles cambian de foco sin cambiar de aspecto: los botones y las casillas que tienen hoja de estilo propia | El aspecto del foco: «Tema» |
| 2.2.2, lo que se mueve | El cursor de la consola parpadea sin fin, y el LED verde pulsa mientras un servicio está vivo; ninguno se puede detener | Si se quitan o se pueden pausar |

Lo demás de AA no se midió: el texto al 200 %, el orden del foco, los mensajes de estado y el
idioma de la pantalla, que llega con el §2.8.

### 2.7 Icono, recursos y empaquetado

Hecho: `icon.png`, `resources.qrc`, `pysidedeploy.spec`, el job `desktop` de `release.yml` como el
de la plantilla, con el job `systems`, y `ci.yml` con `--variables`. Está en
[02](../arquitectura/02_bloques.md), §5, y [03](../arquitectura/03_ejecucion_y_despliegue.md), §1.
El 2026-11-19 los pasos de Linux armaron en la distro `Testing` un `Consola.bin` que abre la
ventana; nada corrió en GitHub ni en Windows ([30](../arquitectura/30_riesgos_y_pendientes.md),
«Sin verificar»).

Falta:

- Crear en GitHub las variables `RELEASE_DESKTOP_LINUX`, `RELEASE_DESKTOP_MACOS` y
  `RELEASE_DESKTOP_WINDOWS`, con `true`, `false` y `true` (decidido). Hasta entonces el job `canone`
  de `ci.yml` falla.
- El paso de traducciones de `ci.yml` y `release.yml`, con el §2.8.

Elegido al implementar, sin confirmar *(propuestas)*:

- El rombo del icono va en el acento (`Colors.ACCENT`), como el icono de ventana que había, sobre
  fondo transparente. Lo pinta `desktop/scripts/icon.py` con el mismo `_Diamond` de la barra.
- Con `RELEASE_DESKTOP_MACOS` en `true`, el job `systems` falla en vez de armar una fila de macOS:
  el ADR-0081 lo deja fuera y el job no tiene los pasos de firma de la plantilla.
- `shots_presets.json` se queda como archivo, junto al kit de la cámara: no es una imagen, y el
  ADR-0189 de canone solo pone las imágenes en `resources.qrc`.
- El job `desktop` de `release.yml` instala la app después de compilar `resources.qrc`, distinto de
  la plantilla (§4, punto 1).

### 2.8 Qt Linguist

Hecho: los 1449 textos de la interfaz, de las tareas, del catálogo, de las claves, del seguro y de
`command_docs.py` pasan por `QCoreApplication.translate` o `QT_TRANSLATE_NOOP`, en
`translations/es.ts`. `main.py` aplica el idioma, `api/http.py` lo manda en `Accept-Language`, y
`ci.yml` y `release.yml` compilan las traducciones como la plantilla. La fecha del respaldo sale de
`QLocale`. Está en [04](../arquitectura/04_conceptos_transversales.md), §10, y en el
[ADR-0091](../adr/0091-los-textos-se-escriben-en-espanol-y-linguist-los-traduce.md).

Decidido el 2026-11-19: el texto fuente en español, solo `es.ts`, y sin selector mientras haya un
solo idioma. Los puntos 4 a 9 del ADR-0091 son propuestas.

Falta:

- El selector de idioma y su clave de `QSettings`, que pide `qt.md`: llegan con el segundo idioma.

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

### Decididas (2026-11-18 y 2026-11-19)

| # | Pregunta | Dónde | Decisión |
|---|---|---|---|
| 1 | El árbol de `qt.md` no tenía `core/` ni `ui/`. ¿Dónde va el código que no es de Qt? | Canone | En `services/`: lo que no es interfaz ni HTTP. Ya está en `qt.md` y `flet.md` (ADR-0186 de canone). En Consola van ahí `core/` y los módulos sin widget, incluidos los dos `QThread`. Hecho (ADR-0090) |
| 3 | «Un solo `QNetworkAccessManager`» chocaba con el ADR-0079: cada tarea bloqueaba su hilo con su propio manager | Consola | Un solo manager en el hilo principal, y las tareas siguen bloqueando su hilo. Hecho (ADR-0089) |
| 4 | `api/client.py` y `api/models.py` suponían la API propia de un servidor. Consola habla con Cloudflare y con el índice de Flutter | Canone | `api/` es todo lo que habla HTTP, con `api/<servicio>.py` para cada servicio externo. Con un servicio externo, un campo desconocido se ignora y los que se leen se validan enteros, y «Reintentos» le aplica. Ya está en `qt.md`, `flet.md` y `transversal.md` (ADR-0186 de canone). En Consola: hecho (ADR-0089 y ADR-0090) |
| 5 | ¿Linguist cubre también los mensajes de `services/` y `command_docs.py`? | Consola | Sí, con `QCoreApplication.translate` (§2.8) |
| 6 | ¿De dónde sale el icono de 1024 px? | Consola | Del rombo de la marca, rasterizado (§2.7) |
| 7 | El árbol de `qt.md` no tenía lugar para lo que no es código | Canone | En `src/app/assets/`: las imágenes entran en `resources.qrc`, y lo que otro programa lee del disco se queda como archivo (ADR-0189 de canone) |
| 8 | `palettes.py` y `parts.py` no tenían lugar en el árbol | Consola | `palettes.py` en `services/`, y `parts.py` como sección de `theme.py`, donde se ubican y cambian los colores de cada parte. Hecho (ADR-0090) |
| 9 | ¿Qué dominio declara `setOrganizationDomain`? | Canone | Ninguno: `qt.md` ya no lo pide (ADR-0192 de canone). La organización es `Equipaggio` |
| 10 | `qt.md` pide un atajo para cada función de uso frecuente: faltaban Ejecutar, Simulacro y pasar de una pestaña de acción a otra | Consola | Ctrl+Enter, Ctrl+Shift+Enter, y Ctrl+PgDown y Ctrl+PgUp, como en un navegador. Cerrar una pestaña no tiene atajo: detiene su proceso con un solo gesto. Hecho |
| 11 | «Los widgets se ubican con layouts», pero tres flotan sobre otros: la lista del buscador, la búsqueda de la consola y los bordes de la ventana | Canone | `qt.md` exceptúa lo que flota encima de otros: va con `setGeometry()` y su tamaño sale de `sizeHint()` (ADR-0195 de canone). En Consola, la búsqueda de la consola ya toma su alto de `sizeHint()` |
| 12 | «Un diálogo modal se abre con `open()`». ¿Rige para los menús contextuales, que se abren con `exec()`? | Canone | No: un `QMenu` no es un diálogo, y Qt documenta `exec()` como su uso común; la nota que pide `open()` está solo en `QDialog::exec()`. `qt.md` no cambia |

### Abiertas

| # | Pregunta | Dónde | Recomendación |
|---|---|---|---|
| 2 | `qt.md` pide copiar `tests/test_theme.py` sin editar, pero prueba reglas de «Tema», que sigue en desarrollo. Consola tiene 169 `setStyleSheet` fuera de `theme.py` y no tiene `colors.py`, así que fallaría | Canone | Que `qt.md` diga lo mismo que `flet.md`: «`theme.py` y `tests/test_theme.py` … en desarrollo como esta sección: no se copian», con las filas de Fusion y de la hoja única marcadas como de «Tema». Pendiente por decisión del usuario |
| 13 | Los colores de texto y de borde no llegan al contraste de AA (§2.5), y son de «Tema», que sigue en desarrollo | Canone | Que «Tema» fije roles de texto y de borde que cumplan 4.5:1 y 3:1 contra cada fondo, como ya pide `transversal.md` para `brand/tokens/`; Consola los toma al implementarlo |
| 14 | `transversal.md` pide 48 × 48 a «cada objetivo táctil». Una app de escritorio se usa con el puntero: no está claro si rige, o si basta el 24 × 24 de AA (WCAG 2.5.8) | Canone | Que diga «objetivo táctil o de puntero» y fije el valor del escritorio |

## 4. Cambios que le hacen falta a canone

Comprobados al implementar el §2.7 y el §2.8. Consola ya los rodea; canone los arregla para todo
repositorio con Qt.

1. **El orden del job `desktop` de `plantilla/.github/workflows/release.yml`.** Instala la app con
   `--no-editable` y después compila las traducciones y `resources.qrc`. Nuitka compila la copia
   instalada, que no tiene `rc_resources.py`: el binario de Linux se armó y al abrirse falló con
   `ModuleNotFoundError: No module named 'app.rc_resources'` (distro `Testing`, 2026-11-19).
   Cambio: `uv sync --locked --group deploy --no-install-project`, el paso de traducciones y
   `pyside6-rcc` con `uv run --no-sync`, y después `uv sync --locked --group deploy --no-editable`,
   como el `release.yml` de Consola.
2. **El icono en Linux, en «Entrega» de `qt.md`.** Dice que Nuitka convierte `icon.png` al formato
   de cada sistema, pero con `mode = onefile` avisa que `--linux-app-icon` no tiene efecto fuera de
   `--mode=app`. Cambio: decir que el icono va en el `.exe` de Windows y en el `.app` de macOS, y
   que en Linux solo lo pone la ventana con `setWindowIcon`.
3. **La extracción de textos, en «Idiomas» de `qt.md`.** `pyside6-lupdate -extensions py src/app`
   6.12.0 termina con un fallo de acceso a memoria si existe `src/app/rc_resources.py`, que está en
   ese árbol. Cambio: extraer sin `rc_resources.py`, por ejemplo borrándolo antes, y decirlo.
4. **Cómo se marca lo que se arma al importar, en «Idiomas» de `qt.md`.** Una declaración
   evaluada al importar necesita `QT_TRANSLATE_NOOP`, y en los stubs de PySide6 6.12.0 devuelve
   `object`: Pyrefly strict rechaza usarlo como `str`. Cambio: un `QT_TRANSLATE_NOOP(context: str,
   text: str) -> str` propio en la plantilla, como el de `services/language.py` de Consola;
   `pyside6-lupdate` lo reconoce por el nombre.
5. **El texto fuente, en «Idiomas» de `qt.md`.** No dice en qué idioma va. Cambio: «el texto
   fuente es el del idioma base», como `app_es.arb` en Flutter.
6. **`self.tr()`, en «Idiomas» de `qt.md`.** En PySide6 busca con el nombre de la clase del
   objeto: un método heredado no encuentra el texto que lupdate guardó con la clase donde está
   escrito. Cambio: los textos van con `QCoreApplication.translate("<contexto>", ...)`, y un valor
   entra con `.format()` después de traducir, nunca en un f-string.
7. **El idioma sin traducción, en «Idiomas» de `qt.md`.** Dice «hasta que elige, es el de
   `QLocale.system()`», pero no qué pasa si el sistema está en un idioma que la app no trae.
   Cambio: el primero de `QLocale.system().uiLanguages()` con traducción, o el base, como el
   `supported_locales` de `flet.md`.

## 5. Sin verificar

- `api/http.py` y `api/cloudflare.py` contra el servicio real: leer necesita un token y escribir cambia
  el DNS. Se probó contra un servidor local y con respuestas simuladas.

## 6. Al terminar

Las decisiones pasan a ADR, el resultado a `arquitectura/`, sale la fila del 30 y se borra este plan.

# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-21).** Canone sacó `qt.md` de desarrollo (`461d857` y `e6b3d0b` de
> canone), y después la sección «Tema» de `transversal.md` y de cada cliente (`e03dedd`, ADR-0198 y
> ADR-0201 de canone): ahora `qt.md` rige entera. Con canone en `main` (`0f2ea6b`, que trae el
> `tokens.py` del ADR-0211, ya copiado), `verificar.py --repo .` da 0 con las tres variables
> `RELEASE_DESKTOP_*`. En Windows, `ruff format --check`, `ruff check`, `pyrefly check` en las dos
> plataformas, `deptry` y `pip-audit` dan 0, y pasan 859 pruebas, con 3 saltadas. En Linux (distro
> `Testing`, 2026-11-21) los pasos del job `desktop` de `ci.yml` dan 0 y pasan 862.
> Ya hecho: el código en inglés, `ruff` con las reglas de `plantilla/qt/`, las versiones de
> `stack.md`, el árbol de `qt.md`
> ([ADR-0090](../adr/0090-el-codigo-sigue-el-arbol-de-qt-de-canone.md)), los tipos, `@override`,
> los enums con su clase, `@Slot` en los 69 métodos conectados a una señal, las fechas y los
> números con el `locale()` del widget, los diálogos con `open()`, el explorador con
> `QTreeView` y `QTableView` sobre `models/`, la accesibilidad de `qt.md`, el icono,
> `resources.qrc`, `pysidedeploy.spec`, el job `desktop` de `release.yml`, Qt Linguist
> ([ADR-0091](../adr/0091-los-textos-se-escriben-en-espanol-y-linguist-los-traduce.md)),
> `brand/tokens/`, `scripts/tokens.py` y `colors.py`
> ([ADR-0092](../adr/0092-el-tema-de-color-se-elige-por-repo-y-viaja-con-el.md) y
> [ADR-0093](../adr/0093-los-colores-son-los-roles-de-material-en-brand-tokens-solo-en-modo-oscuro.md)),
> `Style` sobre Fusion y ninguna hoja de estilo
> ([ADR-0094](../adr/0094-cada-parte-da-sus-colores-en-una-qpalette-y-style-dibuja-lo-demas.md)), `IniFormat`, HTTP con un solo
> `QNetworkAccessManager` y reintentos
> ([ADR-0089](../adr/0089-http-va-por-un-solo-manager-en-el-hilo-de-la-interfaz-y-reintenta.md)),
> `release.yml` ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)), las filas
> 2.1.1, 2.4.3, 2.2.2, 1.4.4, 4.1.3, 2.4.7, 1.4.11 y 2.5.8 (24 × 24) del nivel AA
> ([ADR-0095](../adr/0095-tab-sigue-el-orden-de-lectura-ver-detiene-lo-que-se-mueve-y-los-cambios-se-anuncian.md))
> y `api/`
> ([ADR-0080](../adr/0080-las-respuestas-http-se-leen-con-modelos-en-api.md)). El objetivo sale del
> [ADR-0075](../adr/0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md); lo
> que hay está en [arquitectura](../arquitectura/README.md), y si este plan no coincide con ella, manda
> ella.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/python.md`, `canone/plataformas/qt.md`, «Tema» y «Accesibilidad» de
> `canone/plataformas/transversal.md` y este plan. Falta el selector de idioma, que llega con el
> segundo idioma (§2.8), la prueba de `release.yml` con un tag (§4), el 48 × 48 del §2.5, que espera
> la pregunta 14 y el §3, «Abiertas».

## 1. Cómo se comprueba

Desde `desktop/`, lo mismo que corre el CI, después de compilar las traducciones y los recursos
como dice el §1 de [03](../arquitectura/03_ejecucion_y_despliegue.md):

```bash
uv run ruff format --check
uv run ruff check
uv run pyrefly check
uv run pyrefly check --python-platform linux
uv run deptry .
uv export --locked --no-emit-project --format requirements.txt -o "${TMPDIR:-/tmp}/req.txt"
uv run pip-audit --disable-pip --require-hashes -r "${TMPDIR:-/tmp}/req.txt"
QT_QPA_PLATFORM=offscreen PYTHONDEVMODE=1 PYTHONWARNDEFAULTENCODING=1 uv run pytest
```

La accesibilidad la mide `tests/test_accessibility.py`, con las demás pruebas
([12](../arquitectura/12_interfaz.md), §10).

Desde la raíz: `python ../canone/scripts/verificar.py --repo . --variables '{"RELEASE_DESKTOP_LINUX":
"true", "RELEASE_DESKTOP_MACOS": "false", "RELEASE_DESKTOP_WINDOWS": "true"}'`, como `ci.yml` con
las variables del repositorio.

Las pruebas no tocan la ventana entera. Después de mover archivos o conexiones hay que abrirla sin
pantalla y apretar sus señales.

## 2. Lo que falta

Rige desde que `qt.md` salió de desarrollo. En este orden: cada etapa deja el repo en verde, salvo
el job `canone` durante el §2.10, y lleva su commit. Los conteos salen de buscar en el código (2026-11-17); lo de accesibilidad no se probó con
la app.

### 2.5 Accesibilidad

Hecho: lo que pide la sección «Accesibilidad» de `qt.md`, también los atajos (pregunta 10). Está en
[12](../arquitectura/12_interfaz.md), §10.

Medido el 2026-11-21 con `tests/test_accessibility.py`, sin pantalla, en Windows y en Linux (distro
`Testing`), con un repo y cuatro pestañas de acción
([ADR-0095](../adr/0095-tab-sigue-el-orden-de-lectura-ver-detiene-lo-que-se-mueve-y-los-cambios-se-anuncian.md),
aceptado el 2026-11-21). Lo que el script no ve se probó en Windows con teclas reales enviadas desde otro
proceso y con un cliente de UI Automation:

| Criterio | Qué falla | Decisión que pide |
|---|---|---|
| 1.4.3, contraste del texto | Nada | — |
| 1.4.11, contraste de lo que no es texto | Nada: el `»` de la barra de menú, los glifos de los botones y las líneas de la barra entre secciones y del separador dan 3:1 o más | — |
| 2.5.8, objetivo de 24 × 24 | Nada a 1400 × 860 ni a 960 × 500 | Si el 48 × 48 de `transversal.md` rige en el escritorio (pregunta 14) |
| 2.1.1, todo con el teclado | Nada: todo lo que responde al ratón recibe el foco, y la marca abre el menú que mueve y redimensiona la ventana. Bajo Wayland, «Mover» no hace nada | — |
| 2.1.2, sin trampas | Nada: Tab sale de los 55 controles | — |
| 2.4.3, orden del foco | Nada: Tab recorre los 55 controles por bandas y por líneas | — |
| 2.4.7, foco visible | Nada: la consola y las áreas con desplazamiento muestran el foco | — |
| 2.2.2, lo que se mueve | Nada: el cursor, el pulso del LED y la RAM se detienen u ocultan desde Ver | — |
| 1.4.4, texto al 200 % | Nada a 960 × 500 px de Qt, con la escala de pantalla del sistema, también con las fuentes de Linux. El «Tamaño del texto» de Windows no agranda la app | — |
| 4.1.3, mensajes de estado | Nada: un cliente de UI Automation recibe las notificaciones. Sin escuchar un lector concreto (NVDA o Narrador) | — |

Las mediciones del 2026-11-19 al 2026-11-21 anteriores a esa prueba corrieron sin pantalla y sin las
fuentes del sistema: cada texto medía el doble de ancho, así que los tamaños de entonces no valen.
Los colores, sí.

Falta medir el idioma de la pantalla (3.1.1), que llega con el §2.8.

### 2.7 Icono, recursos y empaquetado

Hecho: `icon.png`, `resources.qrc`, `pysidedeploy.spec`, el job `desktop` de `release.yml` como el
de la plantilla, con el job `systems`, y `ci.yml` con `--variables`. Está en
[02](../arquitectura/02_bloques.md), §5, y [03](../arquitectura/03_ejecucion_y_despliegue.md), §1.
El 2026-11-19 los pasos de Linux armaron en la distro `Testing` un `Consola.bin` que abre la
ventana; nada corrió en GitHub ni en Windows ([30](../arquitectura/30_riesgos_y_pendientes.md),
«Sin verificar»).

Las variables `RELEASE_DESKTOP_LINUX`, `RELEASE_DESKTOP_MACOS` y `RELEASE_DESKTOP_WINDOWS` están
creadas en GitHub con `true`, `false` y `true` (2026-11-19).

Elegido al implementar y aceptado el 2026-11-21:

- El rombo del icono va en el acento (`Colors.ACCENT`), como el icono de ventana que había, sobre
  fondo transparente. Lo pinta `desktop/scripts/icon.py` con el mismo `_Diamond` de la barra.
- Con `RELEASE_DESKTOP_MACOS` en `true`, el job `systems` falla en vez de armar una fila de macOS:
  el ADR-0081 lo deja fuera y el job no tiene los pasos de firma de la plantilla.
- `shots_presets.json` se queda como archivo, junto al kit de la cámara: no es una imagen, y el
  ADR-0189 de canone solo pone las imágenes en `resources.qrc`.

### 2.8 Qt Linguist

Hecho: los 1450 textos de la interfaz, de las tareas, del catálogo, de las claves, del seguro y de
`command_docs.py` pasan por `QCoreApplication.translate` o `QT_TRANSLATE_NOOP`, en
`translations/es.ts`. `main.py` aplica el idioma, `api/http.py` lo manda en `Accept-Language`, y
`ci.yml` y `release.yml` compilan las traducciones como la plantilla. La fecha del respaldo sale de
`QLocale`. Está en [04](../arquitectura/04_conceptos_transversales.md), §10, y en el
[ADR-0091](../adr/0091-los-textos-se-escriben-en-espanol-y-linguist-los-traduce.md).

Decidido el 2026-11-19: el texto fuente en español, solo `es.ts`, y sin selector mientras haya un
solo idioma. Los puntos 4 a 9 del ADR-0091 se aceptaron el 2026-11-21.

Falta:

- El selector de idioma y su clave de `QSettings`, que pide `qt.md`: llegan con el segundo idioma.

### 2.9 Lo que no aplica

El `README.md` de canone dice: «Cada proyecto elige las tecnologías que utiliza y consulta
únicamente las convenciones correspondientes. Canone responde a la pregunta "si se usa X, ¿cómo se
usa?", sin convertir su catálogo en una lista de requisitos universales». Consola no tiene
`server/` ni cuenta. Por eso quedan fuera «OpenAPI y clientes», `datamodel-code-generator`,
`api/client.py`, `api/models.py`, keyring, «Versión mínima de cliente», WebSocket y «Código de
autorización».

### 2.10 Tema

Hecho el 2026-11-21: `brand/tokens/` con los 46 roles de Material, `success` y `warning`, en nueve
temas y solo en `dark`; `scripts/tokens.py` y `colors.py` generado; `Style` sobre Fusion; ninguna
hoja de estilo en `src/app/`, con cada parte como una `QPalette`, y `tests/test_theme.py` copiado.
Está en [12](../arquitectura/12_interfaz.md), §2, y en los ADR
[0092](../adr/0092-el-tema-de-color-se-elige-por-repo-y-viaja-con-el.md),
[0093](../adr/0093-los-colores-son-los-roles-de-material-en-brand-tokens-solo-en-modo-oscuro.md) y
[0094](../adr/0094-cada-parte-da-sus-colores-en-una-qpalette-y-style-dibuja-lo-demas.md). Cambiar
de pestaña de repo con ocho abiertos, sin pantalla, bajó de 0,78 s a 0,06 s.

`desktop/scripts/swatches.py` tampoco tiene hojas de estilo, y las claves foráneas del explorador
toman el acento del repo. El §2.5 se volvió a medir después.

## 3. Preguntas

«Dónde» dice quién lo resuelve: canone, cuando la duda es qué pide una página, y Consola cuando la
duda es cómo cumplirla.

### Decididas (2026-11-18 a 2026-11-21)

| # | Pregunta | Dónde | Decisión |
|---|---|---|---|
| 1 | El árbol de `qt.md` no tenía `core/` ni `ui/`. ¿Dónde va el código que no es de Qt? | Canone | En `services/`: lo que no es interfaz ni HTTP. Ya está en `qt.md` y `flet.md` (ADR-0186 de canone). En Consola van ahí `core/` y los módulos sin widget, incluidos los dos `QThread`. Hecho (ADR-0090) |
| 2 | `qt.md` pedía copiar `tests/test_theme.py` sin editar, pero probaba reglas de «Tema», que estaba en desarrollo | Canone | «Tema» salió de desarrollo y `verificar.py` exige la copia (ADR-0198 de canone). Va en el §2.10 |
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
| 13 | Los colores de texto y de borde no llegan al contraste de AA (§2.5) | Canone | `transversal.md` pide el contraste a cada rol de texto y a `outline` en cada tema y cada modo, y `tokens.py --check` lo hace cumplir. Consola lo cumple al pasar sus colores a `brand/tokens/` (§2.10) |
| 15 | Las paletas de Consola son por repo y viajan con él. En «Tema», el tema lo elige el usuario como preferencia de cada dispositivo, en la clave `theme` de `QSettings` | Consola | Una excepción en Consola, y no un cambio en canone: ningún otro producto lo necesita hoy. Las ocho paletas pasan a ser ocho temas de `brand/tokens/`, el tema se elige por repo y se guarda en `.consola/params.json`, y cada espacio de trabajo toma la `palette()` de su tema. Va en un ADR que reemplaza el punto 1 del ADR-0075 solo para esto. Si otro producto llega a necesitarlo, como una marca por cliente o un color por entorno, se propone a canone |
| 16 | Los roles de Consola no son los de Material: dos escaleras de fondos (teñida y gris), cuatro grises de texto, cuatro bordes y colores de estado (`SUCCESS`, `WARNING`, los LED) que el `ColorScheme` no tiene. `tokens.py` falla con un rol de más y `test_theme.py` con un literal fuera de `colors.py` | Consola, y canone los estados | Consola adopta los 46 roles de Material, sin nombres propios, y conserva el aspecto de hoy (comparado en capturas con fondos grises y con un tinte leve). Los cinco fondos grises van en `surface*`, iguales en los ocho temas; `CHROME`, la banda teñida de las cabeceras y la pestaña de acción activa, en `primaryContainer`; `SURFACE_ALT`, la de la fila del menú, la pestaña del repo y el buscador, en `secondaryContainer`. Los menús desplegados y las pestañas de acción inactivas (`PANEL`) pasan a gris, y `ACCENT_PURPLE` va en `tertiary`. `SUCCESS` y `WARNING` no se agregan en Consola: se pide a canone que adopte los *custom colors* de Material, que `material-color-utilities` define en `theme_utils.ts` (`CustomColor`, con la familia `color`, `onColor`, `colorContainer` y `onColorContainer` en cada modo), como regla para todo producto que muestre estados. Canone los adoptó (ADR-0209). Hecho (ADR-0093). Aceptado el 2026-11-21, con el detalle de los puntos 7 a 13 del ADR-0093: el texto en `onSurface` y `onSurfaceVariant`, lo inactivo al 38 % que genera `colors.py`, los cuatro bordes en `outline` y `outlineVariant`, el hover como capa de estado y no como rol, y los LED en los colores de estado. |
| 17 | ¿Consola tiene solo el modo oscuro o los dos? | Consola | Solo el oscuro, como hoy. `colors.resolver.json` tiene solo `dark` en `mode`, la app lo usa siempre, y `theme.py` no tiene la elección del modo ni la clave `mode` |
| 18 | ¿Cómo se ven las 39 partes sin hoja de estilo? | Consola | Cada espacio de trabajo aplica la `palette()` de su tema, y cada parte (`Look`) da su fondo y su texto como una `QPalette` que su widget aplica con `setPalette()`; los hijos la heredan. Lo que una paleta no expresa, como los bordes y el foco, lo dibuja `Style`, y los botones con relleno de acento usan la propiedad `variant` en `primary`, como pide `qt.md`. La tabla de partes de `theme.py` sigue siendo el único lugar donde se cambia un tono |
| 19 | La ventana no tiene marco del sistema, y moverla o redimensionarla era solo con el ratón (§2.5, 2.1.1). ¿Entra en «toda función se puede usar con el teclado»? | Consola | Sí: el usuario pidió resolverlo el 2026-11-21. La marca abre un menú de la ventana con Mover y Tamaño (ADR-0095). Hecho |
| 20 | `desktop/scripts/aa.py` medía lo que pide «Accesibilidad» de `transversal.md`, y casi todo era de Qt y no de Consola. ¿Lo da canone? | Canone | Sí, decidido por el usuario el 2026-11-21: `tests/test_accessibility.py` es canónico y Consola da su ventana en `tests/conftest.py` (ADR-0216 de canone). Salió `aa.py`. Hecho |

### Abiertas

| # | Pregunta | Dónde | Recomendación |
|---|---|---|---|
| 14 | `transversal.md` pide 48 × 48 a «cada objetivo táctil». Una app de escritorio se usa con el puntero: no está claro si rige, o si basta el 24 × 24 de AA (WCAG 2.5.8) | Canone | Que diga «objetivo táctil o de puntero» y fije el valor del escritorio |

## 4. Sin verificar

- `api/http.py` y `api/cloudflare.py` contra el servicio real: leer necesita un token y escribir cambia
  el DNS. Se probó contra un servidor local y con respuestas simuladas.
- `release.yml` con un tag: nunca corrió en GitHub. Sus pasos de Linux armaron en la distro `Testing`
  un binario que abre la ventana; en Windows no se armó ([30](../arquitectura/30_riesgos_y_pendientes.md)).

## 5. Al terminar

Las decisiones pasan a ADR, el resultado a `arquitectura/`, sale la fila del 30 y se borra este plan.

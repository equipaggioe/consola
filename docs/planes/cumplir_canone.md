# Plan — que Consola cumpla canone entera

> **Estado (verificado 2026-11-21).** Canone sacó `qt.md` de desarrollo (`461d857` y `e6b3d0b` de
> canone), y después la sección «Tema» de `transversal.md` y de cada cliente (`e03dedd`, ADR-0198 y
> ADR-0201 de canone): ahora `qt.md` rige entera. Canone agregó los custom colors `success` y
> `warning` (`3d120e3`, ADR-0209), y con eso se hizo la etapa 1 del §2.10. Con canone en `main`
> (`3d120e3`), `verificar.py --repo .` da 1 incumplimiento con las tres variables
> `RELEASE_DESKTOP_*`: falta `desktop/tests/test_theme.py`, que llega en la etapa 4 del §2.10. El job
> `canone` de `ci.yml` falla hasta entonces. En Windows, `ruff format --check`, `ruff check`,
> `pyrefly check` en las dos plataformas, `deptry` y `pip-audit` dan 0, y pasan 811 pruebas, con 3
> saltadas (eran 1028: `test_palettes.py` dejó las de contraste, que hace `tokens.py --check`).
> En Linux, los pasos del job `desktop` de `ci.yml` no se corrieron sobre la etapa 1 del §2.10.
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
> [ADR-0093](../adr/0093-los-colores-son-los-roles-de-material-en-brand-tokens-solo-en-modo-oscuro.md)), `IniFormat`, HTTP con un solo
> `QNetworkAccessManager` y reintentos
> ([ADR-0089](../adr/0089-http-va-por-un-solo-manager-en-el-hilo-de-la-interfaz-y-reintenta.md)),
> `release.yml` ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)) y `api/`
> ([ADR-0080](../adr/0080-las-respuestas-http-se-leen-con-modelos-en-api.md)). El objetivo sale del
> [ADR-0075](../adr/0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md); lo
> que hay está en [arquitectura](../arquitectura/README.md), y si este plan no coincide con ella, manda
> ella.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/python.md`, `canone/plataformas/qt.md`, «Tema» y «Accesibilidad» de
> `canone/plataformas/transversal.md` y este plan. Falta «Tema» (§2.10), desde la etapa 2, el
> selector de idioma, que llega con el segundo idioma (§2.8), la prueba de
> `release.yml` con un tag (§4) y lo que espera una decisión: el nivel AA (§2.5) y el §3,
> «Abiertas».

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

Medido el 2026-11-19 con un script sobre la ventana abierta sin pantalla, con un repo y cuatro
pestañas de acción: 39 controles visibles. **El nivel AA no se cumple.** Lo que falla pide decisiones
de diseño:

| Criterio | Qué falla | Decisión que pide |
|---|---|---|
| 1.4.3, contraste del texto | `TEXT_MUTED` (#6b7484) da de 2,5 a 4,0 contra los cinco fondos neutros; `ERROR` da 3,6 a 4,4 sobre `SURFACE`, `SURFACE_ALT` y `CHROME`. `RUN_BUTTON_OFF` da 2,54, pero es un componente inactivo y está exento | Resuelto en los roles (etapa 1 del §2.10): `TEXT_MUTED` y `TEXT_DIM` van en `onSurfaceVariant` (`#9aa4b2`, 4,75:1 o más) y `error` es `#ff7b72` (4,75:1 o más), y `tokens.py --check` lo comprueba. Se vuelve a medir con la app al cerrar el §2.10 |
| 1.4.11, contraste de lo que no es texto | `BORDER` da de 1,3 a 2,0 y `BORDER_LIGHT`, de 1,7 a 2,6 contra los fondos: el borde de un campo no llega a 3:1 | En la etapa 1 del §2.10, `outline` es `#7a8392` (3,13:1 o más contra cada superficie), y las hojas de estilo de los campos, los botones con borde, las casillas y las pestañas ya lo usan. En la etapa 2, `Style` dibuja en él el marco de los campos. Se vuelve a medir al cerrar el §2.10 |
| 2.5.8, objetivo de 24 × 24 | 16 controles: los `×` de las pestañas (18 × 18), el `✕` de apagar (20 × 20), el botón de borrar de los campos (22 × 18), los cinco candados (12 de alto), los chips de 22 de alto y dos casillas de 17 de alto | Los tamaños, que van en `theme.py`, y si el 48 × 48 de `transversal.md` rige en el escritorio (pregunta 14) |
| 2.1.1, todo con el teclado | 11 controles no reciben el foco: las pestañas de acción (con Ctrl+PgDown y Ctrl+PgUp), las de repo (con Ctrl+Tab y Ctrl+1 a 9), el «+» (con Ctrl+T), la estrella de favorita, los tres botones de la ventana y el botón de borrar de los campos | Si cada pestaña y cada botón de glifo reciben el foco, o bastan los atajos |
| 2.4.7, foco visible | 26 controles cambian de foco sin cambiar de aspecto: los botones y las casillas que tienen hoja de estilo propia | Se vuelve a medir al cerrar el §2.10: `Style` dibuja el foco de campos y paneles en 2 px de `primary`, y el de botones y casillas queda en manos de Fusion, sin probar en Consola |
| 2.2.2, lo que se mueve | El cursor de la consola parpadea sin fin, y el LED verde pulsa mientras un servicio está vivo; ninguno se puede detener | Si se quitan o se pueden pausar |
| 1.4.4, texto al 200 % | Los 70 controles con texto visibles fijan su tamaño en píxeles (la fuente de la app, de 15 px, en `apply_theme`, y las hojas de estilo): al duplicar la fuente de la app no crece ninguno, así que no siguen el tamaño de texto del sistema. Solo la escala de pantalla los agranda, y al 200 % el tamaño mínimo de la ventana, 1000 × 650, pide 2000 × 1300 px: no entra en una pantalla de 1920 × 1080 | Si la fuente sigue la del sistema. Los tamaños van en `theme.py` |
| 2.4.3, orden del foco | Tab recorre los 38 controles que reciben el foco y vuelve al buscador, pero no en el orden de lectura: buscador → panel de configuración (abajo a la derecha) → los `×` de las pestañas de acción (arriba) → consola → pasos (arriba a la derecha) → Limpiar → `×` del repo (arriba a la izquierda) → candados (abajo) | El orden que se quiere. Depende de la fila 2.1.1: si las pestañas reciben el foco, entran en él |
| 4.1.3, mensajes de estado | Ningún widget manda `QAccessibleAnnouncementEvent`: un cambio de estado cambia el nombre o la descripción de un widget, que un lector anuncia solo si tiene el foco. Se ven sin foco el LED y el estado de una vista («Estado del endpoint»), los servicios y la RAM de la barra de estado, y el error de una tarea en la consola. Buscado en el código; sin probar con un lector | Qué mensajes se anuncian |

Medido el 2026-11-20 con otro script sobre la ventana sin pantalla, con un repo y cuatro pestañas
de acción: las tres filas de arriba. En la misma medición se arreglaron dos fallos que no pedían
decisión: Tab no salía de un campo de varias líneas (`EnvRow` y `ParamsPanel`) y los cuatro `×` de
las pestañas de acción se llamaban «Cerrar pestaña», sin decir cuál
([12](../arquitectura/12_interfaz.md), §10).

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

Elegido al implementar, sin confirmar *(propuestas)*:

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

### 2.10 Tema

Rige desde `e03dedd` de canone (2026-11-20). Lo que pide «Tema» de `transversal.md` y de `qt.md`:

| Pieza | Qué pide |
|---|---|
| `brand/tokens/` | `colors.resolver.json` con dos modificadores: `theme`, un contexto por tema con el inicial en `default`, y `mode`, con `light`, `dark` o los dos. Un archivo de tema solo tiene `palette`, y uno de modo, solo `color`. Los roles son los 46 del `ColorScheme` de Flutter: cada modo los asigna todos, y `tokens.py` falla con uno de más |
| `scripts/tokens.py` | La copia canónica. `verificar.py` corre su comprobación: el contraste, las partes de DTCG y lo generado al día |
| `desktop/src/app/colors.py` | Generado y commiteado: el enum `ColorTheme`, con un esquema por modo, `INITIAL` y `palette()` |
| `desktop/src/app/theme.py` | Punto de partida de la plantilla: `Style`, un `QProxyStyle` sobre Fusion, que dibuja el marco de campos, spin boxes, combo boxes y paneles en `outline`, y en 2 px de `primary` con el foco, la grilla en `outlineVariant`, y los botones con la propiedad `variant` en `primary` o `danger`. La elección va en `QSettings`, en las claves `mode` y `theme`. Los tamaños, solo aquí |
| `desktop/tests/test_theme.py` | Canónico, sin editar: ningún literal de color fuera de `colors.py`, ningún `setStyleSheet` y el estilo sobre Fusion |

Lo que hay, contado en el código el 2026-11-21:

| Qué | Hoy |
|---|---|
| Colores | En `brand/tokens/`: los 46 roles y `success` y `warning`, en nueve temas (los ocho de los repos y `neutral`, el inicial) y solo en `dark`. `scripts/tokens.py` genera `desktop/src/app/colors.py`, y `tokens.py --check` da 0 |
| Roles y partes | `Role` de `theme.py` nombra 15 roles de Material, y las 39 partes (`Look`) los toman, o una capa de estado (`Layer`). `services/palettes.py` toma cada tema de `colors.py` |
| Literales de color fuera de `colors.py` (la expresión de `test_theme.py`) | Ninguno. `test_colors_only_generated` de la plantilla de canone pasa |
| Hojas de estilo | 169 `setStyleSheet` en 27 archivos, sin cambios. Nombran los colores fijos por `theme.Colors`, que los toma del tema `neutral` con los nombres de antes |
| Estilo | El de la plataforma: nada llama a `setStyle` ni nombra Fusion |
| Dibujo propio | 10 `paintEvent`, que pintan con los colores de su parte |

Etapas:

1. Hecha el 2026-11-21: los ADR
   [0092](../adr/0092-el-tema-de-color-se-elige-por-repo-y-viaja-con-el.md),
   [0093](../adr/0093-los-colores-son-los-roles-de-material-en-brand-tokens-solo-en-modo-oscuro.md)
   y [0094](../adr/0094-cada-parte-da-sus-colores-en-una-qpalette-y-style-dibuja-lo-demas.md),
   `brand/tokens/`, `scripts/tokens.py`, `colors.py` generado, y `theme.py` y
   `services/palettes.py` con los colores de `colors.py`. Los widgets y los modelos pasan los colores
   a Qt como texto o en un `QBrush`, sin construir un `QColor`.
2. `Style` sobre Fusion y la paleta de la app desde `colors.py`. Sale la hoja global. Las tooltips de
   `palette()` van en `inverseSurface`, claras: decidir si se conservan oscuras.
3. Cada parte sin hoja de estilo, en los 27 archivos (pregunta 18). Sale `theme.Colors`, y cada widget
   toma sus colores de la paleta de su parte. Sale también la hoja que
   `MainWindow._apply_window_border` pone en el `centralWidget`, que se lleva 0,63 de los 0,7 s de
   cambiar de pestaña de repo ([30](../arquitectura/30_riesgos_y_pendientes.md), «Reportados en
   uso»). La flecha de las listas, `assets/chevron-down.svg`, lleva el color `#9aa4b2` escrito: la
   dibuja `Style`, o el SVG deja de llevar color.
4. `tests/test_theme.py` copiado y `verificar.py` en 0. Se vuelve a medir el §2.5.

Las etapas 1 a 3 dejan en verde el job `desktop`; el job `canone` sigue fallando hasta la 4.

Elegido al implementar la etapa 1 y aceptado el 2026-11-21 (puntos 7 a 13 del ADR-0093 y punto 4
del ADR-0092): qué superficie va en cada rol `surface*`; el rótulo de un campo en `onSurface`; los
resúmenes y las pistas en `onSurfaceVariant` (`#9aa4b2`); el texto inactivo al 38 %; las líneas que
dividen en `outlineVariant` y el contorno de un control en `outline` (`#7a8392`); el hover como capa
de estado al 8 %, y la fila elegida en `secondaryContainer`; los LED en los colores de estado, el
apagado en `outline`; `error` en `#ff7b72`; los colores de los roles que Consola no usa, y el tema
`neutral` para la ventana sin repo.

En canone, `test_theme.py` deja fuera `rc_resources.py` (2026-11-21, sin commitear en canone): lo
genera `pyside6-rcc`, git lo ignora, y el job `desktop` lo compila antes de `pytest`. Con la versión
anterior, `test_colors_only_generated` fallaba en Consola con dos líneas suyas: el `stroke="#9aa4b2"`
de `chevron-down.svg` y `#A77` dentro de los bytes de una imagen. Con la nueva pasa. El job `canone`
de `ci.yml` toma canone de GitHub: hasta que el cambio llegue allí, la copia de la etapa 4 no
coincide con la de GitHub.

## 3. Preguntas

«Dónde» dice quién lo resuelve: canone, cuando la duda es qué pide una página, y Consola cuando la
duda es cómo cumplirla.

### Decididas (2026-11-18 a 2026-11-20)

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

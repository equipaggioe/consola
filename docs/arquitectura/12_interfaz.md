# 12 · Interfaz

## 1. Tres niveles

```
barra de título   marca ◇ · pestañas de REPOS · minimizar / maximizar / cerrar
barra de menú     catálogo por grupo · Ver · buscador
─────────────────────────────────────────────┬──────────────────────────────
 pestañas de EJECUCIÓN del repo activo       │ Acción
 CONSOLA (nombre de la vista) · URL         │ Seguridad
 consola  |  segunda vista (navegador | base)│ Parámetros
                                             │ Configuración del repo
                                             ├──────────────────────────────
                                             │ Limpiar · ☆ · Simulacro · Ejecutar
─────────────────────────────────────────────┴──────────────────────────────
barra de estado   candados del repo                    herramientas · RAM
```

Un repositorio abierto es lo que una pestaña de navegador: el contexto entero de lo que se ve debajo. Por eso comparten fila con los botones de ventana, y por eso la ventana es sin marco (`Qt.FramelessWindowHint`), con agarres propios en los bordes ([ADR-0031](../adr/0031-la-ventana-como-navegador.md)).

Cada repo tiene su propio `TabPanel`, indexado por la ruta normalizada de su carpeta —no por la identidad del objeto, que CPython reusa—. Sus pestañas de ejecución nunca se mezclan con las de otro.

## 2. El color del repo

Cada repo tiene un **tema** y un **logo**. El tema es una clave (`blue`, `indigo`, `violet`, `pink`, `coral`, `amber`, `green`, `cyan`) y de él sale la paleta entera de su espacio de trabajo (`services/palettes.py`, [ADR-0042](../adr/0042-una-paleta-por-repo.md)). Se elige con el clic derecho sobre la pestaña del repo, donde los ocho colores van sueltos en el menú, cada uno con su muestra: un cuadro del tamaño y el radio de una casilla, pintado con el acento del tema, y el del tema elegido lleva la palomita dentro (`project_tabs.swatch`); al añadir un repo se le da el primer tema libre. El tema se guarda **en el repo** (`.consola/params.json`), así que el color viaja con él a cualquier máquina.

Una paleta es un acento más la escalera de fondos que se deriva de él: el tono del acento a una saturación fija por rol, del 38 % al 55 % en HSL. Teñir **no cambia la luminosidad** del neutro de partida: el color dice de qué repo es la pantalla y la luminosidad dice qué panel se mira.

**La distribución de colores no está definida por el momento.** Qué rol pinta cada parte se ajusta a prueba en la sección «The parts of the window» de `theme.py`, que es la única fuente. Los roles que nombra este documento pueden no estar al día: manda `theme.py`.

La saturación es absoluta, no una fracción de la del acento. Si fuera una fracción, un repo con un acento apagado (el verde) quedaría gris y uno con un acento saturado (el azul) no, sin que eso signifique nada.

Los ocho acentos son claros: el acento va **encima** de los fondos —la barra de título, el rombo de la marca, los filetes, el texto de enlace— y tiene que despegarse de ellos.

Los **roles** son los colores entre los que se elige (`Role` en `theme.py`):

| Rol | Qué es |
|---|---|
| `accent` | El color del repo |
| `on_accent` | Lo legible sobre el acento (`on_color`) |
| `chrome` | La banda más saturada de la escalera |
| `bg` | El escalón más oscuro |
| `panel`, `surface`, `surface_hover`, `surface_alt` | Los escalones siguientes, de más oscuro a más claro |
| `border`, `border_light` | Separadores y marcos |
| `GRAY_BG`, `GRAY_PANEL`, `GRAY_SURFACE`, `GRAY_SURFACE_HOVER`, `GRAY_SURFACE_ALT`, `GRAY_BORDER`, `GRAY_BORDER_LIGHT` | Los mismos escalones sin teñir: los neutros de `theme.py`, iguales en los ocho temas |
| `TEXT`, `TEXT_LABEL`, `TEXT_DIM`, `TEXT_MUTED` | Los grises del texto, de más claro a más apagado: texto corrido, rótulo de un campo, resúmenes de sección, pistas cortas y rutas |

Las **partes** son las zonas de la ventana: barra de título, fila del menú, menú desplegado, cabecera y cuerpo de sección, campo, pie, barra de estado… Qué rol pinta cada una lo dice **una sola tabla**, `theme.py`: cada parte es un `Look` que da un `Role` a cada ranura que pinta —`bg` (fondo), `fg` (texto), `border` (contorno), `hover` (fondo bajo el cursor o fila elegida) y `focus` (borde con el foco)—. Ningún widget nombra un rol: pide su parte (`theme.SECTION_HEADER.on(pal)`) y lee la ranura, y pedir una ranura que la parte no declara lanza `LookupError`. Para cambiar el tono de una parte se cambia su rol en esa tabla; al escribir `Role.` el editor lista los roles. `tests/test_palettes.py` comprueba que cada parte resuelve en los ocho temas y en `NEUTRAL`, y que su texto se lee sobre su fondo a 3:1 (salvo Ejecutar apagado: WCAG no le pide contraste a un control deshabilitado).

Los roles que nombra el resto de esta sección son los que hoy tiene `theme.py`.

Una casilla marcada de Parámetros o de Seguridad se rellena con `CHECK`, hoy el acento del repo: el panel repite las reglas de la hoja global (`theme.check_css`) con su paleta, y por estar más cerca de la casilla gana. Deshabilitada va en `TEXT_MUTED`, salvo las de la vista previa (`previewCheck`), que llevan el relleno de `CHECK` porque muestran lo que la corrida va a tomar, no una opción apagada. La casilla sin marcar sigue en los neutros de la hoja global, con el fondo y el borde de un campo (`GRAY_SURFACE_ALT` y `GRAY_BORDER`). El texto de una casilla va en `TEXT_LABEL` y a 13 px, como el rótulo de un campo y lo que se escribe en él, en Parámetros, en Configuración del repo, en Máquina y en Seguridad.

Lo que **no** se tiñe: los grises del texto y los colores de estado (`SUCCESS`, `WARNING`, `ERROR`, los LED). Un error tiene que verse igual en los ocho temas, y un gris de texto corrido hacia el tono de su fondo pierde contraste en vez de ganarlo.

La pestaña de ejecución activa (`RUN_TAB_ACTIVE`) toma el fondo de la cabecera «CONSOLA», que tiene debajo, con el nombre en negrita: rompe la línea de la barra, y esa abertura es lo que la une a su contenido. Las demás (`RUN_TAB`) llevan contorno y el escalón de la barra en el tono del repo (`panel` sobre `GRAY_PANEL`): es el tinte lo que las separa de la barra gris; su relleno se detiene una fila antes del borde inferior, así que la línea de la barra sigue de largo debajo de ellas.

Debajo de las pestañas de ejecución va una barra que nombra la vista (`TabView._build_header`, parte `CONSOLE_HEADER`): «CONSOLA», o «NAVEGADOR» o «EXPLORADOR» cuando se ve la segunda vista. Después del nombre lleva el endpoint que publicó la tarea —LED, estado y URL— y, a la derecha, Copiar, «Abrir ↗» y el botón que cambia de vista; todo eso aparece y desaparece con la URL. Hace en la columna izquierda lo que las cabeceras de sección hacen en la derecha: es la misma parte (`CONSOLE_HEADER = SECTION_HEADER`), así que se pinta igual y cambia con ellas, con las mismas medidas (30 px de alto, mayúsculas de 12 px en negrita), pero no se pliega.

Las pestañas de repo **no seleccionadas** llevan de fondo el acento del repo activo —el color con el que queda pintada la barra de título— y el contorno de `on_accent`, el mismo del «+», que es lo único que las recorta; el hover lo sube de 90 a 150 de alfa. La **seleccionada** se pinta de `surface_alt`, la banda de la fila del menú (`MENU_BAR`), que es la que va justo debajo: la pestaña queda conectada con el contenido que abre, como en un navegador, con el nombre en el acento del repo y sin contorno. El «+» es una pestaña más, la que todavía no tiene repo. Cambiar el color del repo activo repinta la fila entera.

El menú del clic derecho sobre una pestaña es la ruta y los ocho colores: quitar el repo es la × de la pestaña, y repetirlo en el menú no agregaba un camino, agregaba una lista más larga.

«Roles y partes» no se abre desde la aplicación: es `desktop/scripts/swatches.py`, que se corre aparte desde `desktop/` con `uv run python scripts/swatches.py <tema>`. Solo muestra: una grilla con cada `Role` en los ocho temas (muestra y hex, con el tema dado en negrita) y una fila por parte de `theme.py`, con una muestra «Aa» pintada como la pinta la parte y cada ranura con su rol, en el tema dado. Lo lee del código al abrirse; lo que cambia un color sigue siendo editar `theme.py`.

El **logo** es `BRAND_ICON`, el mismo SVG del que salen los íconos de las apps del repo ([19](19_imagenes.md)), leído de su `config.env` (`services/repo_logo.py`, [ADR-0058](../adr/0058-el-logo-del-repo-en-la-interfaz.md)). Un repo sin `BRAND_ICON` lleva la marca de Equipaggio (`assets/equipaggio.png`); uno cuyo `BRAND_ICON` no existe, no es SVG o Qt no lo lee muestra ⚠, con el error en el tooltip.

| Dónde | Lado |
|---|---|
| Pestaña del repo, a la izquierda del nombre | 18 px |
| Bienvenida del repo, sin pestañas de ejecución | 64 px |
| Tarjeta del repo en los avisos del seguro ([14](14_seguro_de_destructivos.md)) | 18 px |

El logo se recorta a lo que dibuja y llena el cuadrado por su lado largo: el margen transparente es del diseño del logo (el de vettore deja 4 de 64 unidades por lado para los íconos de app), y sin recortarlo ese logo y la marca de Equipaggio salían más chicos que los demás. Se rasteriza a 256 px, se recorta donde el alfa pasa de 8 y se escala con `SmoothTransformation` a la densidad del monitor. Se relee al guardar o recargar `config.env` en Configuración del repo; la pestaña lo recibe de su `TabPanel` por `logo_changed`.

**Ningún fondo es negro.** La marca se apoya directamente en la barra de título, en `on_accent`, sin placa: su rombo se **pinta** con trazo de 2.2 px y el nombre va en negro de imprenta, que es lo que la sostiene sin una placa debajo. El casi negro `#0a0b10` sobrevive solo como tinta (`Colors.INK`, lo que `on_color` pone sobre un fondo claro), nunca como fondo. El contorno de la ventana sin foco es `border`.

Los tres botones de ventana se **pintan** —trazo de 1.6 px en `on_accent`—, no se escriben: como caracteres («─», «□», «✕») eran trazos de un píxel que se perdían contra el acento, y la negrita no engorda un carácter de dibujo de caja. El fondo del hover sale del mismo `on_accent` al 16 %, salvo el de cerrar, que es rojo.

El campo del buscador tiene las medidas de un campo de «Configuración del repo»: borde (`GRAY_BORDER`), alto (28 px), radio, cuerpo de letra (13 px) y foco (`accent`). El fondo es otro: los campos (`FIELD`) van en `GRAY_SURFACE_ALT` y el buscador (`SEARCH_FIELD`), que está en la fila del menú, en `surface_alt`, el color del repo. Los campos de «Parámetros» miden 30 px de alto. La flecha de una lista cerrada de «Parámetros» es un SVG propio (`assets/chevron-down.svg`) dentro del relleno: con el borde estilado, Qt deja encima su caja de la flecha y corta el borde derecho, y estilar `::drop-down` para sacar esa caja borra también la flecha. La lista abierta tiene el ancho del campo y cae alineada bajo él, con el texto de cada entrada a la misma x que el del campo; una entrada más larga que el campo se corta con «…».

Los menús desplegados de la barra y la lista del buscador son del repo abierto: fondo `panel` —por debajo de la fila de la que cuelgan, para que el popup se recorte contra ella—, borde `border_light`, el ítem bajo el cursor en `surface_hover` con el nombre en el acento del repo, y el título del menú abierto en la barra del mismo `panel` que el popup, para que se lean como una sola pieza. En Ver, la palomita de cada casilla va a 13 px del borde y el texto a 33, en vez de los 5 y 41 que Qt pone por defecto.

Sin ningún repo abierto no hay de quién tomar el tono: la paleta `NEUTRAL` repite los neutros pelados de `theme.py`, con la misma escalera y sin teñir.

## 3. Encontrar una acción

| Superficie | Qué hace |
|---|---|
| Barra de menú | El catálogo entero por grupo, a un recorrido de hover. Un clic **abre** la pestaña |
| Buscador | Filtra sobre todas las acciones, con teclado (Ctrl+L lo enfoca; flechas, Enter, Ctrl+Enter). Cada fila trae su filete de favorita, la marca de nivel (`◈` compuesta, `◦` atómica), la de alcance (`⌂` es de la máquina) y un **▶** que corre de una |
| «Solo favoritos», en el menú Ver | Poda los menús. **No** poda el buscador: buscar es ir por algo puntual, y esconder justo lo que se busca sería un chiste cruel |

Los menús de acciones son los grupos del catálogo, en el orden en que `services/catalog.py` los declara, y dentro las acciones en ese mismo orden: el del uso real, de preparar a usar a mirar. Cada acción va por su nombre, sin el emoji; una destructiva lleva `⚠` al final. Una favorita se marca con el filete de su fila en el buscador o con la estrella del pie, junto a Ejecutar ([§5](#5-la-columna-derecha)).

Después va **Ver**, que tiene «Solo favoritos» y una casilla por sección de la columna derecha: las dos son preferencias de la aplicación, no del repo.

Dentro de un menú **no hay encabezados de sección**: los tramos se cortan con rayas. Una raya sale de `Capability.cut` —el catálogo declara que ese botón abre un tramo— o de ser el primer destructivo del grupo, que va siempre al fondo detrás de una raya sin que nadie lo declare ([ADR-0043](../adr/0043-un-menu-sin-secciones.md)). Un menú que se quedó sin acciones aplicables desaparece de la barra, y cada raya se dibuja solo si quedó algo visible de los dos lados.

Abrir una pestaña no ejecuta nada. Ejecutar es apretar Ejecutar, o el ▶ del buscador, que corre con los parámetros guardados para ese botón en ese repo ([ADR-0032](../adr/0032-abrir-no-es-ejecutar.md)).

El ▶ solo aparece en lo que puede correr ya: `services/readiness.py` mira exactamente lo que esos parámetros guardados van a correr, así que un paso apagado no reclama sus claves.

El recuento se **pide**, no se hace en el acto: `windows/main_window.py::_refresh_readiness` arranca un temporizador de 200 ms y la pasada corre una sola vez cuando se detiene la ráfaga. Quien lo dispara es, entre otros, cada tecla de un campo de texto —del panel de parámetros y del de configuración—, y la pasada resuelve las 61 acciones contra el repo. Esa pasada comparte además un único recorrido del repo entre todas (`services/targets.py::one_scan`) en vez de recorrerlo una vez por acción; el recorrido se suelta al terminar, así que cada pasada sigue mirando el disco de nuevo.

## 4. La pestaña de ejecución

Las pestañas de ejecución son de carpeta, como las de repo en la barra de título: la activa se pinta del fondo de la cabecera «CONSOLA», llega hasta la línea de abajo de la barra y la tapa, así que se abre hacia la consola y la columna derecha, que se leen como su contenido. Lleva el nombre en negrita. Las demás llevan contorno, que el hover sube de 110 a 200 de alfa ([§2](#2-el-color-del-repo)). Llevan el nombre de la acción, sin el emoji.

`TabView` tiene la consola y, si la capacidad lo declara, una segunda vista: el navegador embebido (`view='web'`) o el explorador de base (`view='db'`). La cabecera de la vista muestra la URL que publicó la tarea con su estado ([ADR-0008](../adr/0008-un-launcher-entrega-un-endpoint.md)).

La pestaña **«Configuración del repo»** no es del catálogo: la abren Guardar e importar en esa sección, y guarda lo que hicieron. No tiene parámetros; mostrándola, la sección Configuración enseña el archivo entero, sin filtrar. No se reabre al arrancar (`TabPanel._open_config_tab`).

Las pestañas se reordenan arrastrando (`widgets/reorderable_tab.py`) y **se reabren al arrancar**: qué botones quedaron a mano es una decisión sobre ese repo, y va a su `params.json` ([ADR-0033](../adr/0033-que-es-de-la-app-y-que-del-repo.md)). Reabrirlas no corre nada.

## 5. La columna derecha

Un acordeón de cinco secciones («Acción», «Seguridad», «Parámetros», «Configuración del repo», «Configuración de la máquina»), no pestañas: se leen juntas —un bloqueo de Parámetros puede decir «faltan claves» y la respuesta está en Configuración, debajo—.

| Sección | Qué muestra |
|---|---|
| Acción | La ficha larga del comando: qué hace y qué pasos ejecuta, de `services/command_docs.py`. Sin texto largo, cae en la descripción de una línea más las etiquetas de los pasos |
| Seguridad | Los seis interruptores del seguro del repo ([14](14_seguro_de_destructivos.md)) |
| Parámetros | Los ejes y los pasos de la acción abierta |
| Configuración del repo | `.consola/config.env` del repo, **filtrado** a lo que la acción puede llegar a mirar con lo que está marcado ahora. Sin las claves de máquina |
| Configuración de la máquina | Todas las claves `scope='machine'`, sin filtrar, con Recargar y Guardar (`widgets/machine_panel.py`): el único lugar donde se editan. Empieza oculta: se muestra desde el menú Ver. Abierta, se le reserva el alto de todas sus filas |

La columna no tiene cabecera propia: empieza por la primera sección visible. La cabecera de cada sección se ve siempre, esté abierta o cerrada. El reparto de alto es automático y se puede forzar arrastrando la barra fina entre dos secciones abiertas, que lleva el color del cuerpo de la sección y se aclara con el hover (`SECTION_GRIP`); doble clic vuelve al automático. El pie con Recargar y Guardar de las dos configuraciones tiene alto fijo: una sección corta achica el formulario, no los botones. Qué secciones se ocultan es preferencia global de la aplicación, no del repo: se elige en el menú Ver o con el clic derecho sobre la cabecera de una sección. Mientras no hay nada guardado, la única oculta es «Configuración de la máquina» (`section_visibility.HIDDEN_BY_DEFAULT`).

En Parámetros, un campo de texto o una lista va a la derecha de su rótulo, como en Configuración del repo: la columna de rótulos tiene el ancho de la de Configuración (`EnvPanel.label_width`) y los dos cuerpos tienen los mismos márgenes, así que los campos de las dos secciones empiezan en la misma x y tienen el mismo ancho. Un rótulo más largo que la columna se parte en dos líneas. Las casillas (componentes, pasos, opciones) siguen en columna bajo su título, y los campos de texto van al final, debajo de ellas: «Otra IP» de Cloudflare queda bajo la opción que la pide.

El pie con **Limpiar · ☆ · Simulacro · Ejecutar** vive fuera del acordeón, fijo al fondo: el botón no se pliega con su sección ni hay que bajar hasta él. La estrella marca o desmarca como favorita la acción abierta, y se pone al día cuando se marca desde el buscador. «Simulacro» solo aparece cuando la acción tiene un eje excluyente con el valor `simulacro`, y fuerza ese valor en el payload de esa corrida sin tocar lo guardado.

## 6. Cuándo se relee lo consultado

Los ejes que salen de preguntarle al SDK o al VPS se releen **al mostrar la pestaña** (`reload_catalogs`), respetando la caché: lo que caduca en un minuto —los AVD, los servicios del VPS— se vuelve a preguntar de verdad, y los dos catálogos grandes del SDK no. No hay botón de recargar: abrir la pestaña es el momento en que se mira la lista ([ADR-0034](../adr/0034-refrescar-al-abrir.md)).

El camino forzado, que saltea la caché, lo usan dos cosas: el botón Recargar de Configuración (que además puede haber cambiado **a qué VPS** se pregunta) y el final de una tarea de máquina.

Mientras la consulta corre, el panel se dibuja con las listas vacías y el botón Ejecutar dice «leyendo el catálogo…».

## 7. Cuando un eje queda vacío

Un eje descubierto sin valores no es «olvidaste elegir»: es que el repo —o la máquina, o el VPS— no tiene eso. El panel lo dice con esas palabras («no hay AVD en esta máquina», «no hay servicio en este VPS») y el botón se bloquea con ese motivo, salvo que el eje admita estar vacío.

Un eje consultado cuya fuente falla —el SDK, el VPS, la cámara o GitHub— no se dibuja vacío: el panel muestra lo que dijo la fuente en su lugar (`AxisDef.query_error`) y el botón se bloquea con ese mensaje.

## 8. La barra de estado

Una sola, de borde a borde, fuera de los `TabPanel`. A la izquierda, lo del repo activo: sus candados, uno por objetivo del seguro; un clic en un candado salta a la sección Seguridad. A la derecha, lo de la máquina, que vale para cualquier repo: el estado de Java, Git, Android y Flutter (mirando el disco, sin lanzar `flutter doctor`) y, tras una raya, la RAM disponible. Sin repo abierto, la izquierda queda vacía.

El LED verde **pulsa** solo cuando algo está vivo ahora mismo; un hecho estático —una herramienta instalada— es el mismo verde sin animación.

## 9. El explorador de base

Árbol de esquemas y relaciones a la izquierda, y a la derecha Datos o Estructura. Corre sobre su propio `DbWorker`, así que una consulta lenta no congela el árbol; las páginas se piden al desplazar y entran cuando la respuesta llega. Detalle en [16](16_base_de_datos.md).

## 10. Accesibilidad

Lo que recibe un lector de pantalla, comprobado con UI Automation en Windows el 2026-11-19:

| Qué | Cómo |
|---|---|
| Widgets de Qt | Su propia interfaz accesible. Un botón que muestra un glifo (`×`, `▶`, `‹`, `☆`) lleva un `accessibleName` en palabras; un campo lo toma de su etiqueta con `setBuddy` (`EnvRow`, `ParamsPanel._labeled`) o de su propósito (el buscador, el filtro del explorador, la búsqueda de la consola). La consola se llama «Consola», y el botón de borrar de un `QLineEdit` lleva texto en la acción `_q_qlineeditclearaction` de Qt, que no lo trae |
| Widgets que se dibujan | Cada módulo trae su `QAccessibleWidget` y lo instala con `QAccessible.installFactory`: las pestañas de los dos niveles (`ReorderableTab`) son `PageTab`, seleccionadas si están activas y con la acción de pulsar; el «+» y cada fila del buscador (`ActionRow`) son `Button`; el LED es `Indicator`, y el logo, `Graphic`. El rombo de la marca queda invisible: `CONSOLA`, a su lado, ya la nombra |
| Lo que solo se ve | El LED dice su estado en palabras («encendido», «activo», «con error»…) y quien lo pone le da el nombre; una fila del buscador dice en su descripción si es compuesta, de la máquina, destructiva o favorita; el logo que no se pudo leer se llama «Logo no válido» y describe el error |
| Cambios | `setAccessibleName` y `setAccessibleDescription` avisan solos; una pestaña que se activa o se deja manda su `QAccessibleStateChangeEvent` |
| Modelos | `RowsModel`, `TablesModel` y `StructureModel` responden `ToolTipRole`, `AccessibleTextRole` y `AccessibleDescriptionRole`. El texto accesible va sin las marcas `✕ ≠ +` ni los glifos, y la descripción dice en palabras el tipo, las particiones y el estado contra los modelos |
| Atajos | Ctrl+T añade un repo, Ctrl+L enfoca el buscador, Ctrl+Tab y Ctrl+Shift+Tab pasan de repo, Ctrl+1 a Ctrl+9 eligen uno, y Ctrl+F abre la búsqueda de la consola. Todos son `QShortcut` |

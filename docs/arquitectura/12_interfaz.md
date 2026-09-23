# 12 · Interfaz

## 1. Tres niveles

```
barra de título   marca ◇ · pestañas de REPOS · minimizar / maximizar / cerrar
barra de menú     catálogo por grupo · buscador · «solo favoritos»
─────────────────────────────────────────────┬──────────────────────────────
 pestañas de EJECUCIÓN del repo activo       │ Acción
 consola  |  segunda vista (navegador | base)│ Seguridad
                                             │ Parámetros
                                             │ Configuración del repo
                                             ├──────────────────────────────
                                             │ Limpiar · Simulacro · Ejecutar
─────────────────────────────────────────────┴──────────────────────────────
barra de estado   repo · herramientas · RAM · candados
```

Un repositorio abierto es lo que una pestaña de navegador: el contexto entero de lo que se ve debajo. Por eso comparten fila con los botones de ventana, y por eso la ventana es sin marco (`Qt.FramelessWindowHint`), con agarres propios en los bordes ([ADR-0031](../adr/0031-la-ventana-como-navegador.md)).

Cada repo tiene su propio `TabPanel`, indexado por la ruta normalizada de su carpeta —no por la identidad del objeto, que CPython reusa—. Sus pestañas de ejecución nunca se mezclan con las de otro.

## 2. El color del repo

Cada repo tiene un **tema** y un icono. El tema es una clave (`azul`, `indigo`, `violeta`, `rosa`, `coral`, `ambar`, `verde`, `cian`) y de él sale la paleta entera de su espacio de trabajo (`ui/palettes.py`, [ADR-0042](../adr/0042-una-paleta-por-repo.md)). Se elige con el clic derecho sobre la pestaña del repo, donde los ocho colores van sueltos en el menú; al añadir un repo se le da el primer tema libre. El tema se guarda **en el repo** (`.consola/params.json`), así que el color viaja con él a cualquier máquina.

Una paleta es un acento más la escalera de fondos que se deriva de él. Los fondos son **color, no gris**: el tono del acento a una saturación fija por rol, del 38 % al 55 % en HSL. Teñir **no cambia la luminosidad** del neutro de partida: el color dice de qué repo es la pantalla y la luminosidad dice qué panel se mira.

La saturación es absoluta, no una fracción de la del acento. Si fuera una fracción, un repo con un acento apagado (el verde) quedaría gris y uno con un acento saturado (el azul) no, sin que eso signifique nada.

Los ocho acentos son claros: el acento va **encima** de los fondos —la barra de título, el rombo de la marca, los filetes, el texto de enlace— y tiene que despegarse de ellos.

| Rol | Dónde |
|---|---|
| `accent` | Barra de título, borde de contorno de la ventana (solo con el foco), subrayado de la pestaña de ejecución activa, botón Ejecutar, foco de los campos, candados cerrados |
| `on_accent` | Lo que va **sobre** la barra de título: la marca, el nombre, el contorno y la × de las pestañas no seleccionadas, el «+», los botones de ventana |
| `chrome` | Fila de la barra de menú y pestaña del repo seleccionado: la banda más clara y más saturada de la escalera |
| `bg` | Consola y lienzo izquierdo: el escalón más oscuro del contenido, el que se lee |
| `panel` | Cuerpo de las secciones de la columna derecha |
| `surface` | Cabeceras de sección, cabecera derecha, pie y barra de estado |
| `surface_alt` | Campos, listas y chips |
| `border` | Separadores y marcos |

Los grises del texto, de más claro a más apagado: `TEXT` (texto corrido), `TEXT_LABEL` (rótulo de un campo y del interruptor «solo favoritos»), `TEXT_DIM` (resúmenes de sección) y `TEXT_MUTED` (pistas cortas y rutas).

Lo que **no** sale de la paleta: los grises del texto, los colores de estado (`SUCCESS`, `WARNING`, `ERROR`, los LED) y el fondo de la barra de pestañas de acciones, que va en el gris neutro `Colors.SURFACE` en los ocho temas (su línea de abajo sí es `border` del repo). Un error tiene que verse igual en los ocho temas, y un gris de texto corrido hacia el tono de su fondo pierde contraste en vez de ganarlo.

Las pestañas de repo **no seleccionadas** llevan de fondo el acento del repo activo —el color con el que queda pintada la barra de título— y el contorno de `on_accent`, el mismo del «+», que es lo único que las recorta; el hover lo sube de 90 a 150 de alfa. La **seleccionada** se pinta de `chrome`, la banda de la fila del menú, que es la que va justo debajo: la pestaña queda conectada con el contenido que abre, como en un navegador, con el nombre en el acento del repo y sin contorno. El «+» es una pestaña más, la que todavía no tiene repo. Cambiar el color del repo activo repinta la fila entera.

El menú del clic derecho sobre una pestaña es la ruta y los ocho colores, nada más: quitar el repo es la × de la pestaña, y repetirlo en el menú no agregaba un camino, agregaba una lista más larga.

**Ningún fondo es negro.** La marca se apoya directamente en la barra de título, en `on_accent`, sin placa: su rombo se **pinta** con trazo de 2.2 px y el nombre va en negro de imprenta, que es lo que la sostiene sin una placa debajo. El casi negro `#0a0b10` sobrevive solo como tinta (`Colors.INK`, lo que `on_color` pone sobre un fondo claro), nunca como fondo. El contorno de la ventana sin foco es `border`.

Los tres botones de ventana se **pintan** —trazo de 1.6 px en `on_accent`—, no se escriben: como caracteres («─», «□», «✕») eran trazos de un píxel que se perdían contra el acento, y la negrita no engorda un carácter de dibujo de caja. El fondo del hover sale del mismo `on_accent` al 16 %, salvo el de cerrar, que es rojo.

El campo del buscador es un campo de «Configuración del repo» y nada más: mismo fondo (`surface_alt`), borde (`border`), alto (28 px), radio, cuerpo de letra (12 px) y foco (`accent`). Los campos de «Parámetros» son otra medida: 30 px y 13 px de letra.

Los menús desplegados de la barra y la lista del buscador son del repo abierto: fondo `panel` —dos escalones por debajo de la fila de la que cuelgan, porque sobre `chrome` un popup queda a 1.06:1 y no se recorta—, borde `border_light`, el ítem bajo el cursor en `surface_hover` con el nombre en el acento del repo, y el título del menú abierto en la barra del mismo `panel` que el popup, para que se lean como una sola pieza. La leyenda del menú Ayuda, que es un ítem que no se puede apretar, queda en `TEXT_MUTED`, que no se tiñe.

Sin ningún repo abierto no hay de quién tomar el tono: la paleta `NEUTRAL` repite los neutros pelados de `ui/theme.py`, con la misma escalera y sin teñir.

## 3. Encontrar una acción

| Superficie | Qué hace |
|---|---|
| Barra de menú | El catálogo entero por grupo, a un recorrido de hover. Un clic **abre** la pestaña |
| Buscador | Filtra sobre todas las acciones, con teclado (flechas, Enter, Ctrl+Enter). Cada fila trae su filete de favorita, la marca de nivel (`◈` compuesta, `◦` atómica), la de alcance (`⌂` es de la máquina) y un **▶** que corre de una |
| «Solo favoritos» | Poda los menús. **No** poda el buscador: buscar es ir por algo puntual, y esconder justo lo que se busca sería un chiste cruel |

Los ocho menús de la barra son los grupos del catálogo, en el orden en que `core/catalog.py` los declara, y dentro las acciones en ese mismo orden: el del uso real, de preparar a usar a mirar.

Dentro de un menú **no hay encabezados de sección**: los tramos se cortan con rayas. Una raya sale de `Capability.cut` —el catálogo declara que ese botón abre un tramo— o de ser el primer destructivo del grupo, que va siempre al fondo detrás de una raya sin que nadie lo declare ([ADR-0043](../adr/0043-un-menu-sin-secciones.md)). Un menú que se quedó sin acciones aplicables desaparece de la barra, y cada raya se dibuja solo si quedó algo visible de los dos lados.

Abrir una pestaña no ejecuta nada. Ejecutar es apretar Ejecutar, o el ▶ del buscador, que corre con los parámetros guardados para ese botón en ese repo ([ADR-0032](../adr/0032-abrir-no-es-ejecutar.md)).

El ▶ solo aparece en lo que puede correr ya: `ui/readiness.py` mira exactamente lo que esos parámetros guardados van a correr, así que un paso apagado no reclama sus claves.

El recuento se **pide**, no se hace en el acto: `ui/main_window.py::_refresh_readiness` arranca un temporizador de 200 ms y la pasada corre una sola vez cuando se detiene la ráfaga. Quien lo dispara es, entre otros, cada tecla de un campo de texto —del panel de parámetros y del de configuración—, y la pasada resuelve las 61 acciones contra el repo. Esa pasada comparte además un único recorrido del repo entre todas (`core/targets.py::one_scan`) en vez de recorrerlo una vez por acción; el recorrido se suelta al terminar, así que cada pasada sigue mirando el disco de nuevo.

## 4. La pestaña de ejecución

`TabView` tiene la consola y, si la capacidad lo declara, una segunda vista: el navegador embebido (`view='web'`) o el explorador de base (`view='db'`). La barra de la pestaña muestra la URL que publicó la tarea con su estado ([ADR-0008](../adr/0008-un-launcher-entrega-un-endpoint.md)).

Las pestañas se reordenan arrastrando (`ui/widgets/tab_reorder.py`) y **se reabren al arrancar**: qué botones quedaron a mano es una decisión sobre ese repo, y va a su `params.json` ([ADR-0033](../adr/0033-que-es-de-la-app-y-que-del-repo.md)). Reabrirlas no corre nada.

## 5. La columna derecha

Un acordeón de cuatro secciones («Acción», «Seguridad», «Parámetros», «Configuración del repo»), no pestañas: se leen juntas —un bloqueo de Parámetros puede decir «faltan claves» y la respuesta está en Configuración, debajo—.

| Sección | Qué muestra |
|---|---|
| Acción | La ficha larga del comando: qué hace y qué pasos ejecuta, de `core/command_docs.py`. Sin texto largo, cae en la descripción de una línea más las etiquetas de los pasos |
| Seguridad | Los seis interruptores del seguro del repo ([14](14_seguro_de_destructivos.md)) |
| Parámetros | Los ejes y los pasos de la acción abierta |
| Configuración del repo | `.consola/config.env` del repo, **filtrado** a lo que la acción puede llegar a mirar con lo que está marcado ahora |

La cabecera de cada sección se ve siempre, esté abierta o cerrada. El reparto de alto es automático y se puede forzar arrastrando la barra fina entre dos secciones abiertas; doble clic vuelve al automático. Qué secciones se ocultan es preferencia global de la aplicación, no del repo.

El pie con **Limpiar · Simulacro · Ejecutar** vive fuera del acordeón, fijo al fondo: el botón no se pliega con su sección ni hay que bajar hasta él. «Simulacro» solo aparece cuando la acción tiene un eje excluyente con el valor `simulacro`, y fuerza ese valor en el payload de esa corrida sin tocar lo guardado.

## 6. Cuándo se relee lo consultado

Los ejes que salen de preguntarle al SDK o al VPS se releen **al mostrar la pestaña** (`reload_catalogs`), respetando la caché: lo que caduca en un minuto —los AVD, los servicios del VPS— se vuelve a preguntar de verdad, y los dos catálogos grandes del SDK no. No hay botón de recargar: abrir la pestaña es el momento en que se mira la lista ([ADR-0034](../adr/0034-refrescar-al-abrir.md)).

El camino forzado, que saltea la caché, lo usan dos cosas: el botón Recargar de Configuración (que además puede haber cambiado **a qué VPS** se pregunta) y el final de una tarea de máquina.

Mientras la consulta corre, el panel se dibuja con las listas vacías y el botón Ejecutar dice «leyendo el catálogo…».

## 7. Cuando un eje queda vacío

Un eje descubierto sin valores no es «olvidaste elegir»: es que el repo —o la máquina, o el VPS— no tiene eso. El panel lo dice con esas palabras («no hay AVD en esta máquina», «no hay servicio en este VPS») y el botón se bloquea con ese motivo, salvo que el eje admita estar vacío.

## 8. La barra de estado

Una sola, de borde a borde, fuera de los `TabPanel`. Muestra el repo activo, el estado de Java, Git, Android y Flutter (mirando el disco, sin lanzar `flutter doctor`), la RAM disponible, y los candados del repo. Un clic en un candado salta a la sección Seguridad.

El LED verde **pulsa** solo cuando algo está vivo ahora mismo; un hecho estático —una herramienta instalada— es el mismo verde sin animación.

## 9. El explorador de base

Árbol de esquemas y relaciones a la izquierda, y a la derecha Datos o Estructura. Corre sobre su propio `DbWorker`, así que una consulta lenta no congela el árbol; las páginas se piden al desplazar y entran cuando la respuesta llega. Detalle en [16](16_base_de_datos.md).

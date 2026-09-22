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

Cada repo tiene un **tema** y un icono. El tema es una clave (`azul`, `cian`, `verde`, `lima`, `ambar`, `coral`, `rosa`, `violeta`) y de él sale la paleta entera de su espacio de trabajo (`ui/palettes.py`, [ADR-0042](../adr/0042-una-paleta-por-repo.md)). Se elige con el clic derecho sobre la pestaña del repo → «Color del repositorio»; al añadir un repo se le da el primer tema libre.

Una paleta es un acento más la escalera de fondos que se deriva de él. Teñir **no cambia la luminosidad** del gris de partida: el color dice de qué repo es la pantalla y la luminosidad dice qué panel se mira.

| Rol | Dónde |
|---|---|
| `accent` | Barra de título, borde de contorno de la ventana (solo con el foco), subrayado de la pestaña de ejecución activa, botón Ejecutar, foco de los campos, candados cerrados |
| `chrome` | Fila de la barra de menú |
| `bg` | Consola y lienzo izquierdo: el escalón más oscuro, el que se lee |
| `panel` | Cuerpo de las secciones de la columna derecha |
| `surface` | Sub-barra de ejecuciones, cabeceras de sección, cabecera derecha, pie y barra de estado |
| `surface_alt` | Campos, listas y chips |
| `border` | Separadores y marcos |

Lo que **no** sale de la paleta: los grises del texto y los colores de estado (`SUCCESS`, `WARNING`, `ERROR`, los LED). Un error tiene que verse igual en los ocho temas, y un gris de texto corrido hacia el tono de su fondo pierde contraste en vez de ganarlo.

La pestaña activa del repo se funde con la barra de título; las demás son placas oscuras con su nombre en **su** color. Cambiar de tema repinta el espacio de trabajo de ese repo aunque no sea el activo.

Fuera del espacio de trabajo quedan en gris el buscador y la barra de menú: son de la aplicación, no de un repo.

## 3. Encontrar una acción

| Superficie | Qué hace |
|---|---|
| Barra de menú | El catálogo entero por grupo y sección, a un recorrido de hover. Un clic **abre** la pestaña |
| Buscador | Filtra sobre todas las acciones, con teclado (flechas, Enter, Ctrl+Enter). Cada fila trae su filete de favorita, la marca de nivel (`◈` compuesta, `◦` atómica), la de alcance (`⌂` es de la máquina) y un **▶** que corre de una |
| «Solo favoritos» | Poda los menús. **No** poda el buscador: buscar es ir por algo puntual, y esconder justo lo que se busca sería un chiste cruel |

Abrir una pestaña no ejecuta nada. Ejecutar es apretar Ejecutar, o el ▶ del buscador, que corre con los parámetros guardados para ese botón en ese repo ([ADR-0032](../adr/0032-abrir-no-es-ejecutar.md)).

El ▶ solo aparece en lo que puede correr ya: `ui/readiness.py` mira exactamente lo que esos parámetros guardados van a correr, así que un paso apagado no reclama sus claves.

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

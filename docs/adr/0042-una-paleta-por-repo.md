# ADR-0042 · El color de un repo es una paleta, y se elige

- **Estado:** Propuesta
- **Fecha:** 2026-09-22
- **Alcance:** ui/palettes.py, ui/theme.py, ui/title_bar.py, tests/test_palettes.py, core/projects.py, ui/project_store.py, ui/project_tabs.py, ui/main_window.py, ui/tab_panel.py, ui/params_panel.py, ui/env_panel.py, ui/security_panel.py, ui/command_info_panel.py, ui/console_view.py, ui/tab_view.py, ui/browser_view.py, ui/db_explorer_view.py, ui/guard_dialog.py, ui/widgets/accordion.py

## Contexto

Cada repo guardaba **un hex suelto** que le tocaba en suerte al añadirlo (`PALETTE[len(tabs) % 10]`), sin forma de cambiarlo, y que solo pintaba el borde del chrome: barra de título, contorno de la ventana, foco de los campos. Todo lo demás eran siete grises fijos.

Eso deja dos problemas juntos. El color del repo se ve poco, y el espacio de trabajo se lee como una sola mancha: la columna derecha usaba el mismo gris para el cuerpo de una sección que para su cabecera, y el mismo que el lienzo de la consola.

## Decisión

1. **Un repo guarda un tema, no un color, y lo guarda él.** `Project.theme` es una clave (`azul`, `coral`, …) de `ui/palettes.py`; el hex se resuelve en la UI. Guardar la clave deja afinar la receta sin repintar a mano cada repo ya guardado. Vive en `<repo>/.consola/params.json` bajo `@theme`, junto a los seguros y las pestañas abiertas: es una decisión de la consola sobre ESE repo, así que viaja con él y no con la máquina. En `config.env` no va, porque ninguna tarea lo lee ([ADR-0017](0017-datos-en-el-env-decisiones-en-el-json.md)).
2. **Una paleta se deriva, no se escribe.** De un acento sale la escalera entera de fondos: `brand`, `chrome`, `bg`, `panel`, `surface`, `surface_hover`, `surface_alt`, `border`, `border_light`.
3. **Los fondos son color, no gris.** La saturación es absoluta —del 38 % (lienzo) al 55 % (placa de la marca) en HSL—, igual para los ocho temas, y no una fracción de la del acento: con una fracción, el repo del acento más apagado quedaba gris y el del acento más saturado no, sin que la diferencia significara nada.
4. **Teñir conserva la luminancia** del neutro de partida (WCAG, por bisección sobre la L de HSL). El color dice de qué repo es; la luminosidad dice qué panel es. Así el contraste de todo lo que va encima es el mismo en los ocho temas que en el neutro original.
5. **Un solo fondo casi negro: `brand`.** Es la placa de la marca `◇ CONSOLA` y la de las pestañas de repo inactivas, ambas sobre la barra de título pintada del acento. La marca pide un sitio fijo donde apoyarse: sobre el acento, el mismo texto cambiaba de peso con cada tema.
6. **La fila de la barra de menú no es negra**: es `chrome`, la banda más clara y más saturada de la escalera, por encima de las cabeceras de sección. Una barra negra sobre fondos de color lee como un tema oscuro con el color pegado encima, no como un tema de ese color.
7. **El texto no se tiñe.** Los grises de texto se quedan en `ui/theme.py`. Corridos hacia el mismo tono que su fondo se le acercan en vez de despegarse.
8. **Los colores semánticos tampoco.** `SUCCESS`, `WARNING`, `ERROR` y los LED son globales: un éxito y un error tienen que distinguirse igual en un repo verde que en uno rojo.
9. **Un tono por panel, no por sección.** Las secciones del acordeón se separan por elevación (cuerpo en `panel`, cabecera en `surface`) y por borde. Un tono propio por sección anularía la señal del repo y gastaría los pocos escalones que un fondo oscuro admite.
10. **El color se elige**: clic derecho en la pestaña del repo, con los ocho colores sueltos en el menú —no en un submenú, porque el menú no tiene nada más que ofrecer—. Al añadir un repo se le da el **primer tema libre**, determinista y sin repetir mientras queden. «Quitar repositorio» sale del menú: para eso está la × de la pestaña.
11. **Los acentos son claros.** El acento es lo que va **encima** de los fondos: la barra de título, la marca, los filetes, el texto de enlace. De él sale el tono; la fuerza con la que se tiñe cada fondo la pone la receta, no su saturación.
12. **La escalera de neutros se ensancha** para que la elevación exista: se añade `PANEL` (el gris donde estaba `SURFACE`) y `SURFACE` sube un escalón. El techo lo pone `TEXT_MUTED`, que sobre una cabecera más clara que `#232935` cae por debajo de 3:1.

## Consecuencias

- Cambiar de color repinta el espacio de trabajo entero, no solo el acento: cada panel guarda la hoja de estilo que se le dictó al construirse, así que la paleta viaja por una cadena de `set_palette` y cada widget se vuelve a dictar la suya.
- Ocho temas es el tope antes de repetir color. Con nueve repos abiertos, el noveno nace con el color del primero y se cambia a mano.
- `tests/test_palettes.py` comprueba contraste, escalones y oscuridad en los ocho temas: tocar una receta falla ahí antes que en la pantalla.
- Las entradas guardadas con el formato viejo (hex en `color`) siguen abriendo: la lista de `QSettings` ya no lleva color, y el tema se le pregunta al repo. El hex viejo se ignora y queda muerto en `QSettings` hasta el próximo guardado de la lista.

## Descartado

- **Interpolar el gris hacia el acento (mezcla RGB).** Los acentos son claros: aclaraba los fondos y bajaba el contraste del texto — `TEXT_MUTED` sobre una cabecera pasaba de 3.4:1 a 2.5:1.
- **Fijar la «L» de HSL en vez de la luminancia.** Un verde y un violeta con la misma L no pesan igual: el verde se iba de contraste por arriba y el violeta aplanaba los escalones por abajo.
- **Un tono por sección del acordeón.** Ver el punto 9.
- **Teñir al 10–26 % de la saturación del acento** (la primera receta). Sobre la pantalla no se distinguía de un gris: los fondos salían con una saturación efectiva del 5 % al 15 % y la ventana entera se leía gris con la barra de título de color.
- **Dejar el color solo en el acento y los fondos en pizarra neutra**, o concentrarlo en una banda sobre un lienzo común. Las dos renuncian a que el repo se reconozca por el fondo, que es lo que se buscaba.
- **Una variable global con la paleta actual, consultada desde `Colors`.** Más barata, pero los estilos ya aplicados no se recalculan al cambiar de repo y dos espacios de trabajo vivos no podrían tener paletas distintas — que es exactamente el caso de esta aplicación.

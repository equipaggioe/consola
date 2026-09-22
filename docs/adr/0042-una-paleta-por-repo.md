# ADR-0042 · El color de un repo es una paleta, y se elige

- **Estado:** Propuesta
- **Fecha:** 2026-09-22
- **Alcance:** ui/palettes.py, ui/theme.py, ui/title_bar.py, ui/action_search.py, ui/menu_bar.py, tests/test_palettes.py, core/projects.py, ui/project_store.py, ui/project_tabs.py, ui/main_window.py, ui/tab_panel.py, ui/params_panel.py, ui/env_panel.py, ui/security_panel.py, ui/command_info_panel.py, ui/console_view.py, ui/tab_view.py, ui/browser_view.py, ui/db_explorer_view.py, ui/guard_dialog.py, ui/widgets/accordion.py, ui/widgets/switch.py

## Contexto

Cada repo guardaba **un hex suelto** que le tocaba en suerte al añadirlo (`PALETTE[len(tabs) % 10]`), sin forma de cambiarlo, y que solo pintaba el borde del chrome: barra de título, contorno de la ventana, foco de los campos. Todo lo demás eran siete grises fijos.

Eso deja dos problemas juntos. El color del repo se ve poco, y el espacio de trabajo se lee como una sola mancha: la columna derecha usaba el mismo gris para el cuerpo de una sección que para su cabecera, y el mismo que el lienzo de la consola.

## Decisión

1. **Un repo guarda un tema, no un color, y lo guarda él.** `Project.theme` es una clave (`azul`, `coral`, …) de `ui/palettes.py`; el hex se resuelve en la UI. Guardar la clave deja afinar la receta sin repintar a mano cada repo ya guardado. Vive en `<repo>/.consola/params.json` bajo `@theme`, junto a los seguros y las pestañas abiertas: es una decisión de la consola sobre ESE repo, así que viaja con él y no con la máquina. En `config.env` no va, porque ninguna tarea lo lee ([ADR-0017](0017-datos-en-el-env-decisiones-en-el-json.md)).
2. **Una paleta se deriva, no se escribe.** De un acento sale la escalera entera de fondos: `chrome`, `bg`, `panel`, `surface`, `surface_hover`, `surface_alt`, `border`, `border_light`.
3. **Los fondos son color, no gris.** La saturación es absoluta —del 38 % (lienzo) al 50 % (fila del menú) en HSL—, igual para los ocho temas, y no una fracción de la del acento: con una fracción, el repo del acento más apagado quedaba gris y el del acento más saturado no, sin que la diferencia significara nada.
4. **Teñir conserva la luminancia** del neutro de partida (WCAG, por bisección sobre la L de HSL). El color dice de qué repo es; la luminosidad dice qué panel es. Así el contraste de todo lo que va encima es el mismo en los ocho temas que en el neutro original.
5. **Ningún fondo es negro, en ninguna parte.** La marca se apoya en la barra de título, en `on_accent`, sin placa; lo que la sostiene es el peso — el rombo se pinta con trazo propio y el nombre va en negro de imprenta. El casi negro `#0a0b10` se queda solo como tinta (`Colors.INK`), que es lo que `on_color` pone sobre un fondo claro. El contorno de la ventana sin foco es `border`, no una línea negra.
6. **Las pestañas no seleccionadas llevan de fondo el acento del repo activo**, que es el color con el que queda pintada la barra de título, con el nombre en `on_accent` y el contorno del «+» — lo único que las recorta. La **seleccionada** se pinta de `chrome`, la banda de la fila del menú que va justo debajo, con el nombre en el acento y sin contorno: queda conectada con el contenido que abre, como en un navegador. Alto 44 px: a 38 el nombre quedaba pegado al borde de abajo. Alto 44 px: a 38 el nombre quedaba pegado al borde de abajo.
7. **La fila de la barra de menú no es negra**: es `chrome`, la banda más clara y más saturada de la escalera, por encima de las cabeceras de sección. Una barra negra sobre fondos de color lee como un tema oscuro con el color pegado encima, no como un tema de ese color.
8. **El texto no se tiñe.** Los grises de texto se quedan en `ui/theme.py`. Corridos hacia el mismo tono que su fondo se le acercan en vez de despegarse.
9. **Los colores semánticos tampoco.** `SUCCESS`, `WARNING`, `ERROR` y los LED son globales: un éxito y un error tienen que distinguirse igual en un repo verde que en uno rojo.
10. **Un tono por panel, no por sección.** Las secciones del acordeón se separan por elevación (cuerpo en `panel`, cabecera en `surface`) y por borde. Un tono propio por sección anularía la señal del repo y gastaría los pocos escalones que un fondo oscuro admite.
11. **El color se elige**: clic derecho en la pestaña del repo, con los ocho colores sueltos en el menú —no en un submenú, porque el menú no tiene nada más que ofrecer—. Al añadir un repo se le da el **primer tema libre**, determinista y sin repetir mientras queden. «Quitar repositorio» sale del menú: para eso está la × de la pestaña.
12. **Los acentos son claros.** El acento es lo que va **encima** de los fondos: la barra de título, la marca, los filetes, el texto de enlace. De él sale el tono; la fuerza con la que se tiñe cada fondo la pone la receta, no su saturación.
13. **Un gris de rótulo propio, `TEXT_LABEL`.** Los rótulos de los campos y el del interruptor «solo favoritos» estaban en los dos grises de abajo (`TEXT_DIM`, `TEXT_MUTED`), pensados para resúmenes y pistas. Un rótulo se lee de corrido o no sirve.
14. **El campo del buscador no tiene ni una excepción** respecto de un campo de «Configuración del repo»: mismo fondo (`surface_alt`), borde, alto, radio, cuerpo de letra y foco. Que sobre `chrome` se recorte menos que allá sobre `panel` no lo convierte en otra cosa.
15. **Los botones de ventana se pintan, no se escriben.** Trazo de 1.6 px en `on_accent`. Como caracteres («─», «□», «✕») eran trazos de un píxel sobre un fondo claro, y la negrita no engorda un carácter de dibujo de caja.
16. **La escalera de neutros se ensancha** para que la elevación exista: se añade `PANEL` (el gris donde estaba `SURFACE`) y `SURFACE` sube un escalón. El techo lo pone `TEXT_MUTED`, que sobre una cabecera más clara que `#232935` cae por debajo de 3:1.
17. **La barra de pestañas de acciones no se tiñe.** Va en el gris neutro `Colors.SURFACE` en los ocho temas; solo su línea de abajo es `border` del repo. Es la excepción a la escalera: el color del repo ya lo dicen la barra de título, la fila del menú y los paneles que la rodean.
18. **Los menús desplegados también son del repo.** Popup en `panel`, ítem bajo el cursor en `surface_hover` con el nombre en el acento del repo, y el título del menú abierto en la barra del mismo `panel` que el popup, para que se lean como una sola pieza. Antes se quedaban en los neutros globales y el nombre del ítem bajo el cursor salía en el azul fijo de `Colors.ACCENT`, que es el acento de OTRO tema. La lista del buscador se pinta igual: cuelga de la misma fila.

## Consecuencias

- Cambiar de color repinta el espacio de trabajo entero, no solo el acento: cada panel guarda la hoja de estilo que se le dictó al construirse, así que la paleta viaja por una cadena de `set_palette` y cada widget se vuelve a dictar la suya.
- Ocho temas es el tope antes de repetir color. Con nueve repos abiertos, el noveno nace con el color del primero y se cambia a mano.
- El popup no puede ir en `chrome`, la banda de la que cuelga: queda a 1.06:1 de ella y deja de recortarse, y el escalón de hover que le sigue (`surface_hover`) queda a 1.07:1 del popup.
- `tests/test_palettes.py` comprueba contraste, escalones y oscuridad en los ocho temas: tocar una receta falla ahí antes que en la pantalla.
- Las entradas guardadas con el formato viejo (hex en `color`) siguen abriendo: la lista de `QSettings` ya no lleva color, y el tema se le pregunta al repo. El hex viejo se ignora y queda muerto en `QSettings` hasta el próximo guardado de la lista.

## Descartado

- **Interpolar el gris hacia el acento (mezcla RGB).** Los acentos son claros: aclaraba los fondos y bajaba el contraste del texto — `TEXT_MUTED` sobre una cabecera pasaba de 3.4:1 a 2.5:1.
- **Fijar la «L» de HSL en vez de la luminancia.** Un verde y un violeta con la misma L no pesan igual: el verde se iba de contraste por arriba y el violeta aplanaba los escalones por abajo.
- **Un tono por sección del acordeón.** Ver el punto 10.
- **La seleccionada del mismo acento que la barra** (la sexta receta): fundida del todo, dejaba de leerse como pestaña.
- **Cada pestaña pintada de su propio acento** (la cuarta receta) y **las de atrás sobre el `chrome` del activo** (la quinta). La primera convertía la barra en un mosaico de bloques saturados que le quitaba protagonismo a la activa; la segunda metía en la barra una segunda escalera de fondos que no le tocaba.
- **Una placa casi negra bajo la marca y bajo las pestañas inactivas** (la segunda receta). Separaba bien, pero reintroducía el negro en la esquina superior izquierda, que es lo primero que se mira.
- **El campo del buscador en `bg`**, hundido para despegarlo de `chrome` (1.38:1 contra 1.15:1 de `surface_alt`). Separaba más, pero dejaba de ser el mismo campo que los de «Configuración del repo», que es lo que tiene que ser.
- **El popup del menú en `chrome`**, la banda de la que cuelga. A 1.06:1 de ella no se recorta, y el hover que le seguiría (`surface_hover`) queda a 1.07:1 del popup.
- **Teñir al 10–26 % de la saturación del acento** (la primera receta). Sobre la pantalla no se distinguía de un gris: los fondos salían con una saturación efectiva del 5 % al 15 % y la ventana entera se leía gris con la barra de título de color.
- **Dejar el color solo en el acento y los fondos en pizarra neutra**, o concentrarlo en una banda sobre un lienzo común. Las dos renuncian a que el repo se reconozca por el fondo, que es lo que se buscaba.
- **Una variable global con la paleta actual, consultada desde `Colors`.** Más barata, pero los estilos ya aplicados no se recalculan al cambiar de repo y dos espacios de trabajo vivos no podrían tener paletas distintas — que es exactamente el caso de esta aplicación.

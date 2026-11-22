# ADR-0095 · Tab sigue el orden de lectura, Ver detiene lo que se mueve y los cambios de estado se anuncian

- **Estado:** Aceptada. El usuario la confirmó el 2026-11-21 entera, para revisarla en la app y
  cambiar lo que no le guste. `transversal.md` de canone pide los criterios de WCAG; cómo se
  cumplen en Consola, cada punto de abajo, se eligió al implementar
- **Fecha:** 2026-11-21
- **Alcance:** `desktop/src/app/windows/main_window.py`, `desktop/src/app/widgets/`,
  `desktop/src/app/services/motion.py`, `desktop/src/app/services/announce.py`,
  `desktop/src/app/theme.py`

## Contexto

`transversal.md` de canone pide, en «Accesibilidad», que toda función se use con el teclado
(WCAG 2.1.1), que el foco recorra los componentes en un orden que conserve su sentido (2.4.3), que
lo que se mueve más de 5 segundos se pueda pausar, detener u ocultar, y lo que se actualiza solo,
también o cambiar de frecuencia (2.2.2), que el texto crezca hasta el 200 % sin perder contenido
(1.4.4) y que un mensaje de estado llegue a las tecnologías de apoyo sin mover el foco (4.1.3). No
dice cómo.

Medido el 2026-11-21 con `desktop/scripts/aa.py`, sin pantalla, antes del cambio: 16 controles que
responden al ratón no recibían el foco (las pestañas, el «+», los botones de ventana, la estrella,
las cabeceras de sección, la barra entre secciones y el separador de columnas); Tab iba del buscador
a la columna derecha, a las pestañas y volvía arriba; el cursor de la consola parpadeaba, el LED
verde pulsaba y la RAM se refrescaba cada 5 s sin forma de detenerlos; ningún cambio de estado se
anunciaba, y la ventana no bajaba de 1000 × 650, más que los 960 × 500 px de Qt que deja una pantalla
de 1920 × 1080 al 200 %.

Qt 6.12 no lee el «Tamaño del texto» de Windows: `QWindowsTheme::refreshFonts` toma las fuentes de
`NONCLIENTMETRICS` y no consulta `TextScaleFactor` (leído en `qwindowstheme.cpp` de qtbase v6.12.0;
sin probar cambiando el ajuste). La escala de pantalla sí agranda todo, texto incluido, porque Qt
mide en píxeles independientes del dispositivo.

## Decisión

1. **Tab sigue el orden de lectura.** `MainWindow.focusNextPrevChild` recorre la ventana por bandas,
   de arriba abajo, y en cada una por líneas, de izquierda a derecha: cada widget antes que sus hijos
   (`_reading`, `_lines`). Una línea junta a los hermanos cuyo centro cae en la altura del primero.
2. **Todo lo que responde al ratón recibe el foco de Tab**, con `Qt.FocusPolicy.TabFocus`: un clic
   no se lo da. Space o Enter lo pulsan. Las pestañas de los dos niveles se mueven un lugar con
   Ctrl+Shift+PgUp y Ctrl+Shift+PgDown, las teclas que mueven una pestaña en un navegador. La tecla
   de menú abre el menú de una pestaña de repo y el de una cabecera de sección. Las flechas mueven
   16 px la barra entre secciones y el separador de columnas (`Metrics.KEY_STEP`), y Enter devuelve
   la barra al reparto automático, como el doble clic.
3. **Lo que se pinta solo dibuja su foco** con `theme.ring`, 2 px; un botón de glifo lo dibuja en el
   color de su glifo, que contrasta con su fondo aunque el fondo sea el acento.
4. **«Animaciones» y «RAM disponible», en el menú Ver**, detienen el cursor de la consola y el pulso
   del LED, y ocultan la RAM de la barra de estado. Son preferencias de la app en `QSettings`
   (`ui/animations`, `ui/ram`) y empiezan encendidas.
5. **Se anuncian con `QAccessibleAnnouncementEvent`** el comienzo y el final de una tarea, el estado
   de un endpoint y lo que hicieron Guardar e importar en «Configuración del repo». Un error y un
   endpoint caído interrumpen al lector; lo demás espera a que termine.
6. **El texto crece con la escala de pantalla del sistema.** La ventana no fija un tamaño mínimo:
   el mínimo sale de los layouts, y la barra de menú se achica y pasa los últimos menús a «»». Se
   comprueba a 960 × 500 px de Qt.
7. Un rótulo de «Configuración del repo» más largo que su columna se parte en dos líneas, como en
   Parámetros, y el nombre de una pestaña de acción que no cabe se acorta con «…», con el entero en
   su tooltip.
8. **La marca de la barra de título abre el menú de la ventana** (`WindowMenu`): Restaurar, Mover,
   Tamaño, Minimizar, Maximizar y Cerrar. En «Mover» y «Tamaño» las flechas mueven 16 px la
   ventana o su esquina de abajo a la derecha, Enter termina y Escape la devuelve.
9. **Lo que se apunta mide 24 px** (`Metrics.TARGET`): los `×` de las pestañas, las casillas, el
   botón de borrar de un campo, el `»` de la barra de menú, la barra entre secciones y los
   separadores. La barra y el separador se ven como una línea de `outline` en el medio.
10. **Un área con desplazamiento sin marco muestra el foco** en 2 px de `Highlight`
    (`theme.focus_frame`), y el `»` de la barra de menú se dibuja en el texto de la barra.

## Consecuencias

- Tab recorre 55 controles en vez de 38: la marca, las pestañas, las cabeceras y los separadores
  se suman.
- Un widget nuevo que responde al ratón tiene que recibir el foco y dibujarlo; `tests/test_accessibility.py` lo
  detecta por su rol accesible o por su cursor.
- Un panel nuevo entra solo en el orden de Tab, por su lugar en pantalla.
- El «Tamaño del texto» de Windows no agranda la app.
- La barra entre secciones ocupa 24 px de alto en vez de 7, y el separador de columnas, 24 de ancho.
- Alt+Espacio sigue abriendo el menú del sistema que Qt muestra en Windows, cuyo «Mover» no mueve
  la ventana.
- Bajo Wayland, «Mover» no hace nada: el sistema no deja que una ventana se ubique sola.
- El 48 × 48 de `transversal.md` para un objetivo táctil no se aplica: espera la pregunta 14 del plan.

## Descartado

- **Ordenar la cadena de foco con `setTabOrder`:** las pestañas y los paneles se crean y se borran
  en marcha, y cada uno nuevo queda al final de la cadena.
- **Que cada animación se detenga sola a los 5 segundos:** el pulso del LED dice que algo está vivo
  ahora; detenido solo, no se distingue de una herramienta instalada.
- **Seguir la preferencia de movimiento del sistema** (`QAccessibilityHints.motionPreference`) en
  vez de Ver, o además de Ver: con las dos, no se sabe de dónde vino que algo no se mueva.
- **Un zoom propio de la app con `QT_SCALE_FACTOR`:** Qt lo lee solo al arrancar, así que cambiarlo
  pide reiniciar, y repite lo que ya hace la escala de pantalla.
- **Abrir `WindowMenu` con Alt+Espacio:** Qt toma la tecla en Windows y muestra el menú del
  sistema (`QWindowsKeyMapper`, `showSystemMenu`). Interceptar los mensajes en `nativeEvent`
  abrió el menú, pero Qt igual entrega una pulsación de Alt que lo cierra. Probado con teclas reales
  el 2026-11-21.
- **El «Mover» del menú del sistema de Windows:** con la ventana sin marco no la mueve (probado con
  teclas reales el 2026-11-21).
- **Que la barra entre secciones y el separador sigan finos y su objetivo de 24 px se superponga a
  lo de al lado:** le quita esos píxeles a la cabecera de la sección, que quedaría por debajo de 24.
- **Que cada pestaña y cada botón de glifo queden fuera de Tab y basten los atajos:** el color del
  repo, el orden de las pestañas, plegar una sección y la estrella no tenían atajo.

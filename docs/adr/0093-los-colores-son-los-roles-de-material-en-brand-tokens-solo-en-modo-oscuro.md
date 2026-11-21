# ADR-0093 · Los colores son los roles de Material en `brand/tokens/`, solo en modo oscuro

- **Estado:** Aceptada. El usuario confirmó los puntos 1 a 6 el 2026-11-20 (preguntas 16 y 17 del plan
  `cumplir_canone.md`), y los puntos 7 a 13, que se eligieron al implementar, el 2026-11-21
- **Fecha:** 2026-11-21
- **Alcance:** `brand/tokens/`, `scripts/tokens.py`, `desktop/src/app/colors.py`,
  `desktop/src/app/theme.py`

## Contexto

«Tema» de `transversal.md` de canone pide los colores en `brand/tokens/`, con los 46 roles del
`ColorScheme` de Flutter y los custom colors del producto, y `scripts/tokens.py`, que falla con un
rol de más y con un rol de texto bajo 4.5:1 o `outline` bajo 3:1 contra una superficie. Consola
tenía sus propios roles en `theme.py`: dos escaleras de fondos, la teñida y la gris, cuatro grises
de texto, cuatro bordes y `SUCCESS`, `WARNING`, `ERROR`, `ACCENT_PURPLE`, `INK`, `INACTIVE` y los
LED. Medido el 2026-11-19, `TEXT_MUTED` daba de 2,5 a 4,0 contra los fondos, `ERROR` 3,57 sobre el
fondo de los campos, y los bordes de 1,3 a 2,6.

El aspecto se comparó en capturas con los fondos grises y con un tinte leve antes de decidir. El
ADR-0209 de canone agregó los custom colors de Material, y con ellos `success` y `warning`.

## Decisión

1. **Consola usa los 46 roles de Material, sin nombres propios, y conserva el aspecto de hoy.** Los
   colores están en `brand/tokens/`, y `scripts/tokens.py`, copiado de canone, genera
   `desktop/src/app/colors.py`. `theme.py` los nombra con su enum `Role`.
2. **Los cinco fondos grises van en los roles `surface*`, iguales en los nueve temas.**
3. **`CHROME`, la banda teñida de las cabeceras y de la pestaña de acción activa, va en
   `primaryContainer`, y `SURFACE_ALT` teñido, el de la fila del menú, la pestaña del repo y el
   buscador, en `secondaryContainer`.**
4. **Los menús desplegados y las pestañas de acción inactivas pasan a gris, y `ACCENT_PURPLE` va en
   `tertiary`.**
5. **El éxito y la advertencia son los custom colors `success` y `warning` de canone.**
6. **Solo el modo oscuro.** `colors.resolver.json` tiene solo `dark` en `mode`, y la app lo usa
   siempre.
7. **Los fondos, por rol:** `surface`, `surfaceDim` y `surfaceContainerLowest` son el
   lienzo (`#0d1117`); `surfaceContainerLow`, el cuerpo de las secciones y los menús (`#1c212b`);
   `surfaceContainer`, las barras y los pies (`#232935`); `surfaceContainerHigh`, la barra de
   estado (`#2b3240`), y `surfaceContainerHighest` y `surfaceBright`, los campos (`#2f3745`).
8. **El texto, en dos roles:** el corrido y el rótulo de un campo en `onSurface`
   (`#f0f4f8`), y los resúmenes, las pistas y las rutas en `onSurfaceVariant` (`#9aa4b2`, el
   antiguo `TEXT_DIM`, que da 4,75:1 sobre el fondo más claro). El texto inactivo es `onSurface` al
   38 %, como en Material.
9. **Una línea que divide va en `outlineVariant` (`#3d4657`), y el contorno de un
   control, un campo, un botón con borde, un menú o una pestaña, en `outline` (`#7a8392`)**, que da
   3,13:1 sobre el fondo más claro. El contorno de un campo vacío de «Configuración del repo» va en
   `onSurfaceVariant`, más claro que el de uno con valor.
10. **El hover es una capa de estado y no un rol**: el color del contenido al 8 % sobre
    su fondo (`Layer` en `theme.py`). La fila elegida de una tabla va en `secondaryContainer`.
11. **Los LED van en los colores de estado**, y el apagado en `outline`.
12. **`error` pasa de `#f85149` a `#ff7b72`** para dar 4,75:1 sobre el fondo de los
    campos. Lo que va sobre él es `onError`, la tinta oscura: el glifo de cerrar la ventana con el
    puntero encima.
13. **Los roles que Consola no usa** toman colores que ya están: los contenedores de
    `tertiary`, `error`, `success` y `warning` son el gris de los campos con el color como texto;
    los `*Fixed` y `*FixedDim`, el color mismo con la tinta encima; `inversePrimary`, la banda de
    las cabeceras; `inverseSurface`, el texto con la tinta encima, y `shadow` y `scrim`, la tinta
    (`#0a0b10`).

## Consecuencias

- `scripts/` vuelve a la raíz solo con `tokens.py`, que canone pide copiar sin editar. Reemplaza el
  punto 3 del
  [ADR-0075](0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md) en eso.
- Los bordes de los campos, de los botones y de las pestañas se ven más claros, y las pistas, más
  claras que antes: es lo que pide el contraste de AA.
- El rótulo de un campo se ve igual que el texto corrido: Material no tiene un tercer gris.
- Las tooltips de la paleta generada van en `inverseSurface`, claras, como en Material.

## Descartado

- **Conservar los roles propios y mapearlos al generar.** `tokens.py` falla con un rol de más, y
  se copia sin editar.
- **`SUCCESS` y `WARNING` como roles de Consola.** Lo resolvió canone para todo producto que
  muestre estados.
- **Los dos modos.** Consola nunca tuvo modo claro, y nadie lo pidió.
- **`TEXT_MUTED` (`#6b7484`) en `onSurfaceVariant`.** Da 2,54:1 sobre el fondo de los campos.

# ADR-0092 · El tema de color se elige por repo y viaja con él

- **Estado:** Aceptada. El usuario confirmó los puntos 1 a 3 el 2026-11-20 (pregunta 15 del plan
  `cumplir_canone.md`), y el punto 4, que se eligió al implementar, el 2026-11-21
- **Fecha:** 2026-11-21
- **Alcance:** `brand/tokens/`, `desktop/src/app/services/palettes.py`,
  `desktop/src/app/services/params_store.py`, `desktop/src/app/widgets/project_tab.py`

## Contexto

«Tema» de `transversal.md` de canone, que salió de desarrollo el 2026-11-20 (ADR-0198 de canone),
hace del tema una preferencia del usuario en cada dispositivo, guardada en la clave `theme` de
`QSettings`. En Consola el color no es una preferencia: dice en qué repo se está, y cada repo
abierto pinta su espacio de trabajo con el suyo. Lo guardaba el repo, en `.consola/params.json`,
para que viajara con él a otra máquina ([ADR-0042](0042-una-paleta-por-repo.md), punto 1), y lo
derivaba en tiempo de ejecución de un acento: el tono del acento en la escalera de fondos, a una
saturación fija por rol y con la luminancia del gris de partida (puntos 2 a 4 del mismo ADR).

Ningún otro producto necesita hoy un tema por recurso en vez de por dispositivo.

## Decisión

1. **Consola es una excepción a «Tema», y no un cambio en canone.** Reemplaza el punto 1 del
   [ADR-0075](0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md) solo
   para esto. Si otro producto llega a necesitarlo, como una marca por cliente o un color por
   entorno, se propone a canone.
2. **Las ocho paletas son ocho temas de `brand/tokens/`**: `blue`, `indigo`, `violet`, `pink`,
   `coral`, `amber`, `green` y `cyan`, con los colores que derivaba la receta del ADR-0042. Cada
   tema es un archivo con el grupo `palette.theme`: el acento, la banda de las cabeceras y la de la
   fila del menú.
3. **El tema se elige por repo y se guarda en su `.consola/params.json`**, bajo `@theme`, con la
   clave del tema. Cada espacio de trabajo toma los colores de su tema. `theme.py` no tiene la
   clave `theme` de `QSettings`.
4. **Un noveno tema, `neutral`, es el inicial y no se elige**: pinta la ventana
   mientras no hay ningún repo abierto, con las bandas en gris. Su acento es el de `blue`.

## Consecuencias

- Un color nuevo, o un cambio de tono, se edita en `brand/tokens/` y se regenera `colors.py` con
  `scripts/tokens.py`; la app ya no tiñe nada al arrancar.
- `tokens.py --check` comprueba el contraste de cada rol en los nueve temas, lo que antes hacía
  `tests/test_palettes.py`. Esa prueba comprueba lo propio de Consola: que un tema cambia solo el
  tono, que el tono se ve y que cada parte se lee.
- Un repo guardado con una clave que no es de ningún tema recibe el primer tema libre al cargarse,
  como antes.

## Descartado

- **El tema como preferencia del dispositivo, como pide canone.** Dos repos abiertos tendrían el
  mismo color, y el color dejaría de decir en qué repo se está.
- **Llevar a canone el tema por recurso.** Ningún otro producto lo necesita hoy.
- **Derivar los temas en tiempo de ejecución.** Canone pide que `brand/tokens/` sea la única
  fuente de los colores, y lo generado se commitea.

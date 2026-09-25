# ADR-0054 · Lo que se ofrece capturar lo dice la cámara

- **Estado:** Propuesta
- **Fecha:** 2026-09-25
- **Alcance:** los ejes `apps`, `themes` y `languages` de «Sacar capturas» y «Capturar y publicar», `camara/index.mjs::parseArgs`; reemplaza el punto de [ADR-0049](0049-la-camara-de-capturas-es-un-script-del-repo.md) sobre `SHOTS_LANGS`

## Contexto

Los ejes de la cámara salían de tres fuentes distintas: `apps` de mirar el repo (toda SPA Vite y toda app móvil), `themes` fijo (`claro`, `oscuro`) y `languages` de `SHOTS_LANGS` en `config.env`. Todo arrancaba marcado.

Lo que la cámara sabe capturar lo declara ella en `parseArgs`, y rechaza lo demás. Con lo que venía marcado, la corrida fallaba en los dos repos que tienen cámara: en vettore por `backoffice`, `landing` y el tema claro; en banditore por `background_gps`, `landing` y el tema claro. Había que desmarcarlos a mano cada vez que cambiaba la selección guardada. Los idiomas estaban escritos dos veces: en `SHOTS_LANGS` y en `parseArgs`.

## Decisión

1. **Consola le pregunta a la cámara.** Corre `SHOTS_CMD --supported --kit <kit>` desde la raíz del repo; `parseArgs` del kit imprime lo que la cámara declara como JSON y termina, antes de que la cámara levante nada. Por eso una cámara llama a `parseArgs` primero.
2. **Los tres ejes salen de esa respuesta:** `apps` son las apps que declara, `themes` y `languages` los que tiene alguna de ellas. Se cachea un minuto por repo, como los AVD, y se lee fuera del hilo de la interfaz.
3. **Si la cámara no contesta, el panel muestra lo que dijo** en lugar de las casillas, y el botón queda bloqueado con ese mensaje. Un eje vacío sin explicación escondería un error del repo.
4. **`SHOTS_LANGS` desaparece.**

## Consecuencias

- Solo se ofrece lo que la cámara captura; con lo que viene marcado, la corrida no falla por la selección.
- Una combinación puede seguir fallando si las apps no comparten temas o idiomas: marcar el tema claro con dos apps, cuando solo una lo tiene. Lo rechaza la cámara nombrando la app.
- Abrir la pestaña arranca node la primera vez en el minuto: de medio segundo a un segundo, sin bloquear la ventana.
- Un cambio en lo que declara la cámara se ve al minuto, o con Recargar.

## Descartado

- **Declarar apps, temas e idiomas en `config.env`** (`SHOTS_APPS`, `SHOTS_THEMES` junto a `SHOTS_LANGS`). Es una segunda copia de `parseArgs` que puede quedar distinta.
- **Un JSON en el repo que lean la cámara y Consola.** Deja una sola fuente, pero saca la declaración del código que la usa y agrega una clave para encontrar el archivo.

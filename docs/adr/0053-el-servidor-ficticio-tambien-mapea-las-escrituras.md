# ADR-0053 · El servidor ficticio también mapea las escrituras

- **Estado:** Propuesta
- **Fecha:** 2026-09-24
- **Alcance:** `camara/index.mjs::startFakeServer`, las rutas de cada cámara; amplía [ADR-0050](0050-las-capturas-no-tocan-la-base.md)

## Contexto

El servidor ficticio del kit contestaba 204 sin cuerpo a todo POST, PUT, PATCH o DELETE. Venía de vettore, cuyos clientes no leen la respuesta de lo que escriben.

En banditore sí la leen. Para empezar la venta, la app de vendedor manda `POST /vendors/me/online` y lee el perfil que vuelve. Con el 204 fallaba con un `TypeError` que la app no espera, así que la venta en curso no se podía capturar. Es la misma clase de fallo que el punto 3 de ADR-0050 prohíbe para las lecturas: una respuesta inventada que rompe la pantalla sin que nadie se entere.

Al volverlo estricto aparecieron tres escrituras que el panel de vettore hacía al arrancar y que nadie sabía que existían.

## Decisión

1. **Las rutas llevan método**: `[método, ruta exacta o RegExp, handler]`. El handler recibe el cuerpo del pedido ya leído y contesta como el servidor de verdad. `reply(204)` contesta sin cuerpo.
2. **Un pedido sin ruta, sea del método que sea, contesta 500 y hace fallar la corrida**, igual que una lectura sin mapear. Solo el `OPTIONS` del CORS se contesta sin ruta.
3. **Un handler que falla** (lanza o no devuelve nada) también hace fallar la corrida, no el proceso.

## Consecuencias

- La cámara de cada repo nombra todas las escrituras que sus clientes hacen durante la captura. En vettore son tres: `POST /auth/mobile/device-link/init`, `POST /auth/me/foreground` y `POST /auth/mobile/prekeys/republish`.
- Se pueden capturar pantallas a las que se llega escribiendo, como la venta en curso de banditore.
- Una escritura nueva de un cliente rompe la próxima corrida, que es lo buscado (ADR-0050).

## Descartado

- **Mapear las escrituras que se quieran y seguir contestando 204 al resto.** Sostiene el fallo silencioso que motivó el cambio.

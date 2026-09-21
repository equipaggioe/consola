# ADR-0040 · Una regla de publicación es un host más una ruta, y cada pieza va en su propio host

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/settings.py, core/tasks/vps_setup.py

## Contexto

El [ADR-0019](0019-tabla-de-rutas-publicas.md) definió `PUBLIC_ROUTES` como reglas
`<patrón> <tipo> <destino>`, donde el patrón es siempre una ruta y el host es uno solo,
implícito en `PUBLIC_HOST`. `_caddyfile` emitía por eso un único bloque de sitio.

Eso no alcanza para un repo cuyas piezas tienen que vivir en orígenes separados, y la
separación no es una preferencia estética. Dos aplicaciones bajo un mismo host comparten
`localStorage`, cookies, IndexedDB y el scope del service worker: la sesión de una pisa a la
de la otra. Un repo con una app de cliente y una de vendedor no se puede publicar por rutas
sin romperse.

Además, servir una SPA bajo `/admin` obliga a compilarla sabiendo bajo qué prefijo vive
—`base`, `base href`, el router del framework—, que es una fuente de fallos que no existe
cuando cada pieza cuelga de la raíz de su host.

## Decisión

1. **Una regla es host más ruta, y las dos partes van escritas.** El patrón empieza con el
   host: `api.ejemplo.net/*`, `api.ejemplo.net/v1/*`, o `api.ejemplo.net` como atajo de `/*`.
2. **Un patrón sin host corta.** Deducirlo de otra clave ahorraba teclas y a cambio hacía que
   una tabla incompleta pareciera completa: no fallaba al escribirla, fallaba después y en el
   sitio equivocado. Las tablas que estaban escritas así se reescribieron.
3. **`PUBLIC_HOST` deja de leerla Caddy.** Le quedó coturn, que la usa de realm.
   `CADDY_ROUTES`, el nombre viejo de la clave, deja de leerse.
4. **Un bloque de sitio por host**, en el orden en que cada host aparece en la tabla, con sus
   reglas adentro y en el orden escrito. Publicar todo bajo un host es el caso de un bloque,
   no un camino distinto: `_caddyfile` no tiene dos ramas.
5. **El catch-all `*` va último de su host, no último de la tabla.** Modifica el punto 6 del
   ADR-0019. Con un host por pieza casi todas las reglas son el catch-all del suyo, y la
   regla vieja las volvía imposibles de escribir.
6. **`CSP` es por sitio**, una tabla `<host> <política>` con `*` para los que no tengan la
   suya. Una sola política para todos los sitios de un repo termina siendo la más permisiva
   de todas, que no protege a ninguno. El host va escrito también aquí: una política pelada se
   aplicaba callada a todos, y con eso una fila con el host mal escrito no se notaba.
7. **Los destinos se indexan por identidad de la regla, no por su patrón.** Con un host por
   pieza, `*` es el patrón de casi todas y un diccionario por patrón las pisaba entre sí.
8. **La forma recomendada es un host por pieza**, incluso cuando el repo publica una sola.
   Un host extra cuesta un registro DNS y el certificado sale solo; empezar por rutas y
   después necesitar orígenes separados cuesta cambiar URLs, romper enlaces guardados y
   volver a registrar service workers.

   Varias rutas bajo un mismo host siguen siendo expresables, porque hay dos casos que no son
   piezas separadas: los archivos estáticos de una API, que son suyos y no una aplicación con
   su propio almacenamiento, y un repo sin proxy cuyo backend monta sus SPA bajo rutas.

## Consecuencias

- `spa_base` devuelve vacío para una pieza con host propio, que pasa a ser el caso normal: el
  build deja de tener que saber bajo qué prefijo vive.
- La gramática del patrón tiene ahora dos formas, y el error de una fila mal escrita tiene
  que distinguirlas: por eso `split_pattern` valida el host y nombra cuál de las dos esperaba.
- El punto 7 del ADR-0019 decía que `parse_routes` y `_caddyfile` son lo único que se puede
  probar sin un VPS, y no había ninguna prueba escrita. Este cambio las trae: `tests/`
  comprueba las dos topologías, la CSP por sitio y el catch-all por host.
- Una tabla con varios hosts necesita que los registros DNS existan antes de recargar Caddy,
  o el certificado de ese sitio no sale.
- Una SPA que queda sola en su host deja de compilarse con `base`, así que el valor con el que
  llama a la API tiene que pasar a ser absoluto: deja de alcanzarla por ruta relativa.

## Descartado

- **Una clave aparte para «modo subdominio».** Serían dos caminos en el generador y dos
  formas de leer la tabla, para expresar lo mismo que un campo del patrón.
- **Seguir leyendo `CADDY_ROUTES`, el host implícito y la CSP pelada.** Los tres hacían que una
  tabla a medio escribir produjera un archivo válido, y el error apareciera en producción y en
  otro lado. Reescribir cuatro tablas se hace una vez; buscar ese error se hace cada vez.
- **Comodines en el host (`*.ejemplo.net`).** Servirían cualquier subdominio con la misma
  configuración, que es lo contrario de lo que la tabla existe para decir.
- **Dejar `CSP` como valor único.** Es la cabecera que más cambia entre piezas del mismo
  repo; mantenerla única obligaba a escribir la unión de todas las excepciones.

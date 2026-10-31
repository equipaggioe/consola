# ADR-0065 · Cada SPA se compila para la raíz de su host, y la tabla de rutas públicas sale

- **Estado:** Propuesta
- **Fecha:** 2026-10-31
- **Alcance:** core/tasks/builders.py, core/vps.py, core/settings.py

## Contexto

`PUBLIC_ROUTES` decía bajo qué ruta se publicaba cada cosa ([ADR-0019](0019-tabla-de-rutas-publicas.md), [ADR-0020](0020-ruta-publica-no-implica-proxy.md), [ADR-0040](0040-una-regla-es-host-mas-ruta.md)). La leían «Configurar Caddy», que salió con el [ADR-0059](0059-desplegar-con-los-programas-de-canone.md), y el build, que escribía `base.generated.js` y comprobaba el HTML compilado.

En un VPS de canone, `install.py` instala un sitio de Caddy por pieza, cada una en su host: `app.<dominio>`, `panel.<dominio>` y la landing en el dominio. Ninguna se publica bajo una ruta.

## Decisión

1. **`PUBLIC_ROUTES` sale**, y con ella `vps.spa_base` y el análisis de la tabla.
2. **Una SPA se compila para la raíz de su host.** `compile_spa` corre `npm run build` sin escribirle nada al repo, y `compile_flutter` no pasa `--base-href` ni `--base-url`.
3. **`create_spa` escribe una config sin base.**
4. Reemplaza también el punto 6 del ADR-0059: Consola ya no escribe `base.generated.js`.

## Consecuencias

- Un repo que tenga `base.generated.js` lo conserva con el último valor escrito, y su config lo sigue importando.
- Publicar una SPA bajo una ruta deja de ser algo que Consola sepa armar.

## Descartado

- **Dejar la tabla para los repos que no siguen a canone.** No queda nada en Consola que publique bajo una ruta.

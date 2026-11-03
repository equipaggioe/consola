# ADR-0072 · Las SPA corren con pnpm, y una nueva parte de la plantilla de canone

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/toolchain.py, core/tasks/builders.py, core/tasks/launchers.py, core/canone.py, core/settings.py

## Contexto

`sveltekit.md` de canone dice que pnpm maneja las dependencias, y `release.yml` construye con `pnpm install --frozen-lockfile` y `pnpm build`. Consola instalaba, compilaba y levantaba las SPA con npm.

«Crear SPA SvelteKit» escribía `fallback: 'index.html'`, y `Caddyfile` de canone sirve `/200.html`: las rutas internas no habrían respondido en el VPS. Tampoco declaraba `packageManager`, que `verificar.py` exige. canone pasó a SvelteKit 3 con su ADR-0112.

## Decisión

1. **Los botones de SPA usan pnpm**, y no queda un camino con npm: `pnpm install`, `pnpm run build` y `pnpm run dev --port <puerto>`, sin el `--` que pnpm le pasaría a Vite tal cual. Reemplaza el `npm run build` del punto 2 del [ADR-0065](0065-cada-spa-va-en-la-raiz-de-su-host.md).
2. **`create_spa` copia de `plantilla/sveltekit/` `vite.config.ts`, `uno.config.ts`, `.gitignore` y `.prettierrc`**, de `CANONE_DIR`, y formatea la SPA con Prettier. Reemplaza la config del punto 3 del ADR-0065.
3. **`create_spa` deja los colores que pide `uno.config.ts`:** corre `scripts/tokens.py`, y si el repo no lo tiene, copia antes ese archivo y `brand/tokens/` de la plantilla.
4. **Declara en `packageManager` la versión de pnpm que corre**, y agrega Prettier y ESLint, que pide `sveltekit.md`.
5. *(propuesta)* **Genera con `sv@1.2.0`**, una versión exacta: `sv@latest` cambió de SvelteKit 2 a 3 sin aviso.

## Consecuencias

- Hace falta pnpm en el PATH de esta máquina (`corepack enable pnpm`). Sin él, los botones de SPA cortan.
- «Crear SPA» pide `CANONE_DIR`.

## Descartado

- **Elegir npm o pnpm según el lockfile de cada SPA.** Son dos caminos para lo mismo, y conserva el que canone no admite.

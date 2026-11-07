# ADR-0082 · Contra el VPS, los botones de base corren `database.py` de canone y leen como `<app>_read`

- **Estado:** Aceptada
- **Fecha:** 2026-11-07
- **Alcance:** core/tasks/database.py, core/database.py, core/canone.py, core/catalog.py, core/registry.py, core/settings.py, core/protection.py, ui/params_panel.py, ui/readiness.py

## Contexto

El [ADR-0078](0078-contra-un-vps-de-canone-la-base-no-se-migra-por-tunel.md) dejó cortando el ámbito remoto de los botones de base hasta que canone trajera cómo resolverlo. Canone trae ahora `database.py`, con `empty`, `migrate` y `seed [--mock]`; la marca `/etc/<app>/development`, que deja `install.py --development` y sin la cual `empty` y `seed --mock` fallan; y el rol `<app>_read`, que la cuenta que administra usa por `peer`, también por un túnel al socket (ADR-0127 y ADR-0128 de canone).

Este ADR reemplaza el punto 3 del ADR-0078.

## Decisión

1. **«Reconstruir base» contra el VPS corre `empty` → `migrate` → `seed` → `seed --mock`**, con una casilla por paso. Los seeders corren dos veces, en `migrate` y en `seed`: son idempotentes.
2. **El estado del `README.md` es la única fuente** para saber si el repo está en desarrollo. «Configurar VPS» pasa `--development` si dice `Estado: en desarrollo`, y sin la línea `Estado:` corta. `config.env` no tiene un campo para eso.
3. **Consola corta antes de llegar al VPS si el README dice `Estado: en producción`**, en el paso «Vaciar» de «Reconstruir base».
4. **Juntar las migraciones no tiene botón:** se hace con «Reiniciar historial», un commit, «Publicar versión» sin desplegar, «Reconstruir base» solo con «Vaciar» y «Desplegar versión».
5. «Correr seeders» y «Correr mock seeders» contra el VPS corren `seed` y `seed --mock`, y «Correr mock seeders» también corta antes si el README dice `en producción`.
6. «Explorar datos» y «Abrir túnel a Postgres» entran como `<app>_read`, sin contraseña, por un túnel al socket `/run/postgresql/.s.PGSQL.5432`, a la base `<app>`. El túnel prueba primero el puerto local 5432.
7. «Borrar base y rol», «Reiniciar historial de migraciones» y «Habilitar extensiones» pierden el ámbito remoto: los roles y las extensiones del VPS son de `install.py`, y vaciar su base es el paso «Vaciar» de «Reconstruir base».
8. Un paso puede existir solo con un valor del eje `scope` (`Step.scopes`). El panel lo oculta con el otro, `Capability.kwargs_from` lo pasa como `False`, y la casilla se guarda igual.

## Consecuencias

- Consola no corre Alembic, seeders ni SQL de superusuario en el VPS: `runner.resolve`, el canal remoto de `database.Admin`, `database.vps_url`, `vps.remote_python` y `VPS_PYTHON` salen.
- Un VPS instalado antes de este cambio no tiene la marca: hay que correr otra vez «Configurar VPS» con «Instalar infraestructura».
- Pasar el README a `en producción` y reinstalar quita la marca. Mientras tanto, Consola ya bloquea.
- «Levantar backend» con ámbito remoto sigue por el túnel al puerto, con `DB_USER` y su contraseña (H8 del 30).

## Descartado

- **Un campo en `config.env` para la marca de desarrollo.** Sería una segunda fuente del estado, que puede contradecir al README, y `config.env` es de cada computadora: está en el `.gitignore`.
- **Una casilla en «Configurar VPS».** Se decidiría en cada corrida, sin quedar escrita.
- **`empty` → `migrate` → `mock`, sin el `seed` aparte.** Se eligió conservar el paso de los seeders.
- **Un botón compuesto para juntar las migraciones.** No se construye por ahora; queda en el 30.

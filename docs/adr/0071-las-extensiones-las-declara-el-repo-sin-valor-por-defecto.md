# ADR-0071 · Las extensiones de Postgres las declara el repo, sin valor por defecto

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/settings.py, core/canone.py, core/tasks/database.py, core/command_docs.py

## Contexto

El [ADR-0014](0014-extensiones-declaradas.md) le daba a `DB_EXTENSIONS` el valor `postgis` por defecto. Antes de canone solo afectaba a la base local. Con el [ADR-0066](0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md), esa clave decide también el paquete `postgresql-17-postgis-3` y `install.py --extension`, y una clave vacía tomaba el valor por defecto: todo VPS recibía PostGIS, y no había forma de pedir ninguna. `despliegue.md` de canone lo instala solo «si la app usa PostGIS». `equipaggio` no lo usa.

Además, si el sistema no tenía la extensión, la tarea avisaba y seguía, contra «Sin fallbacks» de `principios.md`. El error aparecía después, en una migración.

Este ADR reemplaza al 0014 y conserva lo demás.

## Decisión

1. **`DB_EXTENSIONS` no tiene valor por defecto.** Vacía significa ninguna: no se crea ninguna extensión, y `canone.packages` y `canone.install_args` no las nombran.
2. **Una extensión declarada que el sistema no tiene corta la tarea**, nombrándola.
3. **La lista se declara en `DB_EXTENSIONS`:** es un dato que la tarea lee, no una elección de la corrida (del ADR-0014).
4. **Crearlas es un paso aparte de las migraciones**, con el canal de superusuario: `CREATE EXTENSION` de una extensión *untrusted* lo exige (del ADR-0014).
5. **La casilla «Habilitar extensiones» arranca desmarcada** (del ADR-0014).

## Consecuencias

- Un repo con columnas geográficas tiene que escribir `postgis` en su `config.env`; si no, sus migraciones fallan.
- Un VPS ya instalado conserva el paquete y la extensión: `install.py` no los quita.
- `plantilla/.github/workflows/ci.yml` de canone crea `postgis` siempre; eso es del CI y no cambia aquí.

## Descartado

- **Dejar el valor por defecto y usar una palabra para «ninguna».** Sigue instalando PostGIS en el repo que no la escriba.
- **Deducirla de `geoalchemy2` en el `pyproject.toml`.** Una extensión como `pg_trgm` no deja esa señal, y `banditore` y `concordia` declaran más de una.

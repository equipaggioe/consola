# ADR-0014 · Qué extensiones de Postgres necesita el esquema se declara; no sale de ningún catálogo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/settings.py, core/tasks/database.py

## Contexto

Las extensiones se intentaron deducir de los `CREATE EXTENSION` de las migraciones, y no puede funcionar en ninguna de las dos direcciones: `alembic revision --autogenerate` nunca escribe uno —un modelo con columnas `Geometry` no deja rastro—, así que la lista salía vacía justo cuando hacía falta; y una migración que sí lo declarara sería la que necesita la extensión **ya creada** para poder aplicarse.

Tampoco lo dicen los catálogos de Postgres: `pg_available_extensions` dice lo que se **puede** crear —cientos con contrib— y `pg_extension` lo que **ya está** creado.

## Decisión

1. La lista se **declara** en `DB_EXTENSIONS`, una clave de configuración del repo, con `postgis` por defecto.
2. Es un dato que la tarea lee, no una elección de la corrida: no cambia entre dos veces que se aprieta el botón. Por eso no tiene eje.
3. Crearlas es un paso **aparte de las migraciones**, con el canal de superusuario: `CREATE EXTENSION` de una extensión *untrusted* lo exige, y Alembic corre como el rol de la aplicación.
4. La casilla «Habilitar extensiones» arranca **desmarcada**, por la misma razón por la que `postgis` no está entre los paquetes por defecto: el paquete de sistema no se instala salvo que se pida.
5. Antes de crear cada una se mira `pg_available_extensions`: si el paquete no está, se avisa y se sigue.

## Consecuencias

- Un repo que necesita otra extensión la agrega a una lista, sin tocar código.
- La lista se escribe a mano una vez por repo, y nada avisa si falta hasta que una migración falle.

## Descartado

- **Deducirlas de las migraciones.** No aparecen en el autogenerate, y si aparecieran sería demasiado tarde.
- **Correr `enable_extensions` siempre, sin casilla.** Prometía una extensión que el VPS no tenía instalada.

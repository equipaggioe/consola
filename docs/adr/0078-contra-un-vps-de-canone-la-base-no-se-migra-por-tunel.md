# ADR-0078 · Contra un VPS de canone la base no se migra por túnel, y el ámbito remoto espera a canone

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/runner.py, core/database.py, core/tasks/database.py

## Contexto

Los ADR [0012](0012-el-eje-scope.md), [0013](0013-generar-en-local-aplicar-donde-este-la-base.md) y [0016](0016-siempre-por-tunel.md) hacían llegar los botones de base al VPS por túnel o con el Python del repo desplegado. En un VPS de canone no hay repo desplegado en esa ruta, los roles entran por `peer` y sin contraseña, y `Settings` lee solo sus credenciales. Comprobado el 2026-11-02: esos botones cortan.

Este ADR reemplaza la parte del VPS de esos tres.

## Decisión

1. **En un VPS de canone migra `deploy.py`**, como el dueño del esquema, y Consola no corre Alembic ahí.
2. **Generar una migración corre siempre en esta máquina, y aplicarla sobre la base local** (del ADR-0013).
3. **El ámbito remoto de «Reconstruir base», «Borrar base y rol», «Reiniciar historial de migraciones», los seeders, «Habilitar extensiones», «Explorar datos» y «Abrir túnel a Postgres» queda como está:** contra un VPS de canone corta, y su solución se busca primero en canone (pregunta 15 del plan de despliegue, [ADR-0074](0074-lo-que-cambia-un-vps-y-canone-no-hace-va-primero-a-canone.md)).

## Consecuencias

- Hasta entonces, esos botones solo sirven con el ámbito local.
- Sigue en el 30 como incumplimiento abierto.

## Descartado

- **Dar contraseña a los roles para que el túnel se autentique.** El ADR-0083 de canone los deja sin contraseña, por `peer`.

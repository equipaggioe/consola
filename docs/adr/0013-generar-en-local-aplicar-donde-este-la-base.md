# ADR-0013 · Las migraciones se generan en esta máquina y se aplican del lado que diga el ámbito

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/tasks/database.py, core/runner.py, core/tasks/vps_server.py

## Contexto

`alembic revision --autogenerate` deja un archivo en `alembic/versions/` que hay que revisar y comitear. Generado en el VPS, ese archivo cae en el repo desplegado, donde el `git reset --hard` del próximo despliegue se lo lleva puesto. El script de despliegue, además, generaba contra la base de producción a partir de un modelo que quizá ni se había commiteado.

## Decisión

1. **Generar** corre siempre en esta máquina (`runner.here`), aunque el ámbito sea remoto. La base remota la alcanza por el túnel, como cualquier otro proceso local.
2. **Aplicar** corre del lado que diga el ámbito (`runner.resolve`): no toca archivos, así que conviene que corra donde está la base.
3. El paso de migraciones de «Actualizar remoto» **solo aplica** las que llegaron con el código.
4. Generar y aplicar son dos casillas sueltas de «Migrar», porque se piden sueltas: generar para revisar el diff antes de tocar nada, aplicar para poner al día una base atrasada.

## Consecuencias

- Las revisiones se escriben en local, se comitean y se despliegan; en el VPS solo se corren.
- `runner.here` y `runner.resolve` existen las dos, y elegir mal es un error silencioso hasta el próximo despliegue.

## Descartado

- **Generar contra la base del VPS desde el despliegue.** Autogenera revisiones en producción y deja al servidor con migraciones que el repo no tiene.

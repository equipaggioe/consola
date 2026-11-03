# ADR-0069 · Un repo de canone corre en desarrollo con sus credenciales, escritas desde `config.env`

- **Estado:** Aceptada. La carpeta del punto 5 la reemplaza el [ADR-0070](0070-las-credenciales-del-dueno-van-dentro-de-credentials.md)
- **Fecha:** 2026-11-02
- **Alcance:** core/canone.py, core/runner.py, core/settings.py, core/targets.py, core/tasks/launchers.py, core/tasks/database.py, core/tasks/utils.py

## Contexto

`Settings` de canone lee solo los archivos de `CREDENTIALS_DIRECTORY`. Consola le pasaba a un servidor `DATABASE_URL` por el entorno, y eso no es solo inútil: probado el 2026-11-02 con `equipaggio`, tanto `import app.main` como `alembic current` mueren con `KeyError: 'CREDENTIALS_DIRECTORY'`. Además, el servidor de la plantilla vive en `src/app/main.py`, y Consola no lo descubría como servidor.

## Decisión

1. **El launcher `backend` escribe `<servidor>/credentials/`**, un archivo `app_<campo>` por campo de `Settings`, y arranca con `CREDENTIALS_DIRECTORY` apuntando ahí (pregunta 8 del plan de despliegue).
2. **Los valores son los de `config.env`, los mismos de producción**, salvo `database_url`, que es `DATABASE_URL` de `config.env`, la base local. Un token firmado en local también vale en producción, y se acepta así (pregunta 8).
3. **`sync_server_env` sale**, con `upsert_value`: no hay `.env` en el servidor que igualar. Reemplaza al [ADR-0037](0037-sincronizar-solo-las-claves-compartidas.md).
4. **Lo reconoce por `Settings`:** un servidor con la clase en `src/app/config.py` es de canone. Los demás siguen recibiendo `DATABASE_URL`, hasta que sigan a canone.
5. **Alembic corre con `<servidor>/credentials-migrate/`**: los mismos archivos, con `app_database_url` como `<rol>_owner`, el dueño del esquema de `install.py`. Vale para «Correr migraciones» y para generar una revisión.
6. **Corta si git no ignora la carpeta**, antes de escribir un secreto.
7. **El entorno del backend es el `.env` del servidor más `CREDENTIALS_DIRECTORY`**: de ahí sale, por ejemplo, `STATE_DIRECTORY`. Consola lo lee y no lo escribe.
8. **Un repo de canone levanta su backend solo contra la base local:** sus roles no tienen contraseña en el VPS, y un túnel no tendría con qué autenticarse.
9. **Consola descubre el servidor también en `src/app/main.py`.**

## Consecuencias

- Las dos carpetas se sobrescriben en cada arranque: lo que se edite a mano ahí se pierde, y un `app_*` que no sea campo de `Settings` se borra.
- Con las llaves de `config.env`, lo cifrado en la base local con llaves anteriores deja de leerse.
- Un repo de canone guarda la base local dos veces: `DATABASE_URL` y `DB_USER`, `DB_NAME` y `DB_PASSWORD`, que siguen pidiendo «Levantar backend» y «Correr migraciones» en el panel, y que leen los demás botones de base.
- `credentials-migrate/` no está en `plantilla/.gitignore` de canone: un repo nuevo tiene que agregarla.

## Descartado

- **Seguir pasando `DATABASE_URL` también a un repo de canone.** `Settings` no lee el entorno, a propósito: un valor sale de un solo lugar.
- **Escribir `credentials/` solo si no existe.** Quedaría discrepando con `config.env` sin avisar, que es lo que `sync_server_env` intentaba arreglar.
- **Usar `credentials/` también para Alembic.** El rol del servidor no tiene DDL.

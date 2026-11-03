# ADR-0070 · Las credenciales de desarrollo del dueño del esquema van en `credentials/migrate/`

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/runner.py

## Contexto

El punto 5 del [ADR-0069](0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md) puso las credenciales con las que corre Alembic en `<servidor>/credentials-migrate/`. `plantilla/.gitignore` y `plantilla/python/.gitignore` de canone ignoran `credentials/`, no esa carpeta: Consola cortaba en cada repo hasta que se le agregara una línea a su `.gitignore`.

El ADR-0086 de canone pide que las migraciones entren como el dueño con su propia carpeta de credenciales, y no fija cómo se llama ni dónde va en desarrollo.

## Decisión

1. **Alembic corre con `<servidor>/credentials/migrate/`.** Reemplaza la carpeta del punto 5 del ADR-0069; lo demás de ese punto sigue como estaba.
2. **Consola no pide ninguna línea en el `.gitignore` de un repo:** la que trae de canone ya ignora esa carpeta.

## Consecuencias

- Las dos carpetas viven juntas: si falta `credentials/`, la crea quien escriba primero.
- `Settings` lee los archivos `app_*` de `credentials/` y no entra en `migrate/`.
- Consola no lee ni limpia una `credentials-migrate/` anterior: guarda credenciales en claro, y se borra a mano.

## Descartado

- **Agregar `credentials-migrate/` a las plantillas de canone.** Cambia dos plantillas de canone por una carpeta que solo necesita quien corre Alembic en desarrollo, y canone ya ignora una carpeta que la puede contener.

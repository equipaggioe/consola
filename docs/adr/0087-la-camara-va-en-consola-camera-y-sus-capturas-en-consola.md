# ADR-0087 · La cámara del repo va en `.consola/camera/`, y sus capturas en `.consola/screenshots/` y `.consola/publishable/`

- **Estado:** Aceptada
- **Fecha:** 2026-11-12
- **Alcance:** core/envfile.py, core/settings.py
- **Modifica:** el punto 5 del [ADR-0064](0064-consola-se-ignora-con-su-propio-gitignore.md)

## Contexto

La cámara de capturas de un repo solo corre con el kit de Consola, que recibe en `--kit`
([ADR-0051](0051-el-kit-de-la-camara-viaja-en-un-argumento.md)). canone la ponía en
`scripts/screenshots/`, con lo que genera al lado, y Consola tomaba eso por omisión. Pero
`scripts/` es para los programas del repositorio, y canone no fija la herramienta que corre sus
programas: la cámara es de Consola. Además, con `*`, `.consola/.gitignore` ignoraba la carpeta
entera.

## Decisión

1. **La cámara va en `.consola/camera/` del repo, versionada**, con su escenario y su
   `package.json`.
2. **Los crudos van en `.consola/screenshots/` y los demás destinos en `.consola/publishable/`**:
   son los valores por omisión de `SHOTS_RAW` y `SHOTS_DIST`. Los que revela el destino `landing`
   siguen en `landing/static/screenshots/`.
3. **`.consola/.gitignore` ignora `config.env`, `params.json`, `screenshots/` y `publishable/`**, en
   vez de `*`. `envfile.ensure_ignored` agrega las líneas que falten, conserva las demás y quita el
   `*`. Reemplaza el punto 5 del ADR-0064, salvo que sigue fallando si no puede escribirlo.

## Consecuencias

- Las capturas se revisan desde el árbol del repo, junto a la cámara.
- Un archivo nuevo en `.consola/` que no esté en esa lista entra a git: hoy el único con secretos
  es `config.env`.
- Un repo que tenga `.consola/` en su `.gitignore` sigue sin versionar la cámara hasta quitar esa
  línea: Consola no toca ese archivo.

## Descartado

- **La cámara en `scripts/screenshots/`.** `scripts/` es para los programas del repositorio, y la
  cámara no corre sin Consola.
- **Las capturas fuera del repo.** Para revisarlas habría que buscar una ruta fuera de la carpeta
  del proyecto, y ninguna otra salida de los repos vive así.
- **Seguir con `*` y una excepción `!camera/`.** Deja una carpeta versionada dentro de una ignorada.

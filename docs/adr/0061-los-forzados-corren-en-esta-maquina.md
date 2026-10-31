# ADR-0061 · Los forzados de git corren solo en esta máquina

- **Estado:** Aceptada
- **Fecha:** 2026-10-31
- **Alcance:** core/catalog.py, core/protection.py, core/tasks/git.py

## Contexto

El [ADR-0044](0044-el-lado-que-gana-es-un-eje.md) juntó cuatro forzados contra GitHub en dos botones con un eje `side`: con `vps`, el mismo comando de git corría dentro del clon del repo en el VPS. Desde el [ADR-0059](0059-desplegar-con-los-programas-de-canone.md) el VPS no tiene clon: `deploy.py` de canone instala un `.tar.gz` del release.

## Decisión

1. *(propuesta)* **«VPS» es la máquina; «Despliegue» es el código del repo corriendo en ella.** La prueba: un botón que seguiría teniendo sentido en un VPS sin ningún repo desplegado es de «VPS» (del ADR-0044).
2. **`git_force_push` y `git_force_reset` no tienen eje `side`**: corren en esta máquina.
3. **El objetivo de protección es fijo**: `git_force_push` reescribe `origin`, y `git_force_reset` descarta commits y archivos de esta máquina (`local`).
4. **`git_force_reset` pregunta si hay cambios sin commitear**, salvo con `discard_changes` en «Descartar».

## Consecuencias

- `force_push_from_vps` y `sync_repository` salen de `core/tasks/vps_server.py`, y `core/tasks/git.py` no importa nada del despliegue.
- El valor guardado del eje `side` queda en `params.json` sin que nadie lo lea.

## Descartado

- **Dejar el eje con un solo valor.** Un eje que no deja elegir nada ocupa lugar en el panel y no dice nada.

# ADR-0047 · Restaurar es un destructivo del seguro por repositorio, y el respaldo se elige de una lista que se mira al abrir

- **Estado:** Propuesta
- **Fecha:** 2026-09-23
- **Alcance:** core/catalog.py, core/protection.py, core/registry.py, core/tasks/database.py, ui/params_panel.py

## Contexto

Había botón para respaldar y no para restaurar: los volcados se acumulaban en una carpeta y no existía `pg_restore` en ninguna parte de `core/`. La mitad que importa cuando algo sale mal era la que faltaba.

## Decisión

1. **`restore_db` es `kind='destructive'` y entra en `protection.RULES` con la misma forma que sus hermanas**: `always=('db',)` más `vps` cuando el ámbito es `remoto`. Con el seguro por omisión queda bloqueado hasta que se abra el candado en la sección Seguridad, igual que `teardown_db` y `rebuild_db`.
2. **Sin confirmación escrita propia.** Hoy la usa una sola capacidad, `purge_emulators`, y por un motivo que acá no aplica: queda fuera del seguro por repositorio por ser de la máquina. Agregarle una a un botón que el seguro ya cubre sería endurecer de más.
3. **El respaldo se elige con un eje `pick`**, no escribiendo una ruta. Sus valores salen de mirar `BACKUP_DIR`, que puede estar fuera del árbol de trabajo, así que no sirve `discover` —que enumera subproyectos del repositorio— y hace falta una fuente consultada nueva, `BACKUP_FILES`.
4. **Esa fuente no se cachea**, por lo mismo que `ANDROID_RUNNING`: es estado, no catálogo. Una lista vieja ofrecería restaurar un dump que la rotación acaba de borrar.
5. **La lista va del más nuevo al más viejo**, para que el preseleccionado sea el último respaldo, que es el que se quiere casi siempre. El valor real es el nombre del archivo; lo que se lee es la fecha con la hora y el tamaño, porque un sello pegado (`20260923-143052`) es ilegible en una lista.
6. **`pg_restore` corre con `--clean --if-exists --no-owner --exit-on-error`**, conectando como el rol de la aplicación. Restaura sobre la base que ya existe borrando cada objeto antes de recrearlo, así que no hace falta cortar conexiones ni abrir el canal de superusuario; `--no-owner` porque el dueño que trae el dump es el del otro lado; y `--exit-on-error` porque un restore a medias que termina diciendo «38 errores» es exactamente el degradado silencioso que este repositorio no quiere.
7. **No tiene pasos.** Es atómica: una casilla «vaciar antes» sería código que no llama nadie, porque `--clean` ya lo hace.

## Consecuencias

- Las extensiones tienen que existir antes de restaurar: `CREATE EXTENSION` pide superusuario y tiene su propio botón. Si falta alguna, `--exit-on-error` corta en la primera línea que la necesite.
- `queried_values` pasa a recibir la raíz del repositorio además de la configuración, y `AxesLoader` se la pasa. Es el único eje consultado que la necesita: los demás preguntan al SDK o al VPS, que no dependen de dónde esté el repositorio.
- Con la carpeta vacía el botón no se deja apretar y el panel lo explica: «no hay respaldo en la carpeta de respaldos». Para eso `AxisDef.query_place` gana un caso; decir «en esta máquina» mandaría a buscar al SDK.
- Restaurar sobre una base cuyo esquema no coincide con el del dump deja la base como estaba en el dump, incluidas las tablas que hoy no existen. Es lo que se pide al restaurar, pero conviene no confundirlo con «volver atrás una migración».

## Descartado

- **Un campo de texto con la ruta del archivo.** Obliga a saber el nombre exacto de un archivo con sello de fecha y no avisa de un error de tipeo hasta que la tarea ya corrió.
- **Confirmación escrita con el nombre del repositorio**, como la que el [ADR-0018](0018-seguro-por-repo-y-objetivo.md) describe para verificar identidad. El seguro ya bloquea, y el bloqueo no tiene escape por diseño: sumar un texto que escribir encima de un candado cerrado no agrega comprobación, agrega gesto.
- **Borrar y recrear la base antes de restaurar.** Necesita el canal de superusuario y cortar las conexiones vivas, y no compra nada frente a `--clean --if-exists`.
- **Restaurar en la base que diga el dump** en vez de en la que dice `DB_NAME`. El formato custom no ata el nombre, y usar el del archivo haría que el botón escriba en una base que el repositorio no declaró.

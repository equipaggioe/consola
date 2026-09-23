# ADR-0045 · Dónde caen los respaldos y cuántos sobreviven son configuración del repo, no ejes del botón

- **Estado:** Aceptada
- **Fecha:** 2026-09-23
- **Alcance:** core/settings.py, core/tasks/database.py

## Contexto

`backup_database` tenía las dos decisiones clavadas en el código: la carpeta en una constante `BACKUP_DIR = '.backups'` y el conteo en un argumento `keep: int = 7` que el catálogo nunca declaró como eje. El hallazgo H5 del documento 30 lo registraba como «no deja elegir cuántos respaldos conservar».

El síntoma del conteo no es teórico: la rotación **borra sola**. Quien respalda antes de una migración riesgosa y después aprieta el botón siete veces más pierde ese respaldo, y lo único que lo dice es un renglón `Backup rotado: ...` en el log de una corrida que ya pasó.

El de la carpeta tampoco: `.backups/` no está en el `.gitignore` de este repositorio ni tiene por qué estarlo en el repositorio gestionado, así que un volcado con datos reales queda dentro del árbol de trabajo, listo para comitearse.

## Decisión

1. **Las dos son claves de `config.env`**, `BACKUP_DIR` y `BACKUP_KEEP`, y no ejes del panel. El criterio es el que ya fijó `DB_EXTENSIONS`: es un dato que la tarea lee, no una decisión de la corrida. Cuántos respaldos conserva un proyecto, y dónde los deja, no cambia entre dos veces que se aprieta el botón.
2. **Se declaran con `used_by`, no con `required_by`.** Las dos tienen `default`, y una clave con default nunca cuenta como faltante (`Config.get`): exigirlas no dejaría ningún botón en ámbar y solo agregaría ruido. `used_by` alcanza para que aparezcan en el panel de configuración filtrado de esos botones.
3. **`BACKUP_DIR` admite ruta absoluta.** Relativa cuelga de la raíz del repo; absoluta se usa tal cual. Es lo que permite sacar los volcados del árbol de trabajo.
4. **`BACKUP_KEEP` falla ruidosamente.** Un valor que no sea un entero de 1 o más corta con `TaskError` nombrando la clave y lo que dice. No cae en 7 en silencio: un default silencioso escondería el error justo donde se decide cuántos archivos se borran para siempre.
5. **La rotación filtra por el nombre de la base** (`<DB_NAME>-*.dump`), no por `*.dump`. Es lo que vuelve correcta la decisión 3: en cuanto la carpeta puede ser compartida entre repositorios, un glob a secas borra los respaldos de las otras bases al rotar los propios.

## Consecuencias

- El hallazgo H5 queda resuelto y sale del documento 30.
- Un repositorio que ya tenga volcados en `.backups/` los sigue viendo: el patrón nuevo es más estrecho que el viejo, no distinto.
- La rotación pasa a depender de una clave que se puede escribir mal, y por eso la decisión 4 no es opcional.
- `list_backups` y `backup_dir` reciben `config` y `root` sueltos en vez del contexto de la corrida, porque el eje `dump` de `restore_db` tiene que llenar su lista antes de que exista ninguna corrida.

## Descartado

- **Un eje `keep` en el panel.** Sería preguntar en cada corrida algo que se responde una vez por proyecto, y el panel ya tiene el eje que de verdad varía.
- **No rotar nunca**, dejando que la carpeta crezca y se limpie a mano. Ahorra una clave y elimina el borrado automático, pero deja el crecimiento sin techo en el único lugar de la aplicación que escribe archivos grandes.
- **`scope='machine'` para `BACKUP_DIR`**, como si la carpeta de respaldos fuera de esta computadora y no del proyecto. Con la decisión 5 una carpeta compartida funciona, pero el valor por omisión útil —`.backups` al lado del código— es del repositorio, y una clave de máquina no puede tener un default relativo a un repositorio.

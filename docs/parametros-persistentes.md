# Parámetros persistentes — por repositorio y por botón

## 1. El problema

El panel de parámetros armaba sus casillas desde el catálogo cada vez que se abría una pestaña:
todas las variantes marcadas, los pasos con su `default`, la primera opción de cada eje. Apagar el
paso de subida en `build_apk`, cerrar la pestaña y volver te devolvía la subida encendida. Y el
botón ▶ del rail —que corre sin abrir la pestaña— arrancaba siempre desde esos valores de fábrica.

## 2. Dónde vive: en el repo, no en la máquina

Lo que marcas en el panel es una decisión sobre **ese** repo. El mismo `build_apk` en dos proyectos
casi nunca quiere los mismos pasos. Por eso se guarda **dentro del repo**, en
`.consola/params.json`, al lado de `config.env` (`ui/params_store.py`):

```json
{
  "@protection": { "vps": true, "db": true, "otros_repos": true, "publicacion": true, "local": false },
  "build_apk": { "steps": ["bump", "compile_apk"], "variants": {"app": ["cliente"]} },
  "update_remote": { "steps": ["pull", "restart"], "options": {} }
}
```

La clave `@protection` son los seguros del repo (`docs/seguro-destructivos.md`). Comparte archivo
con los parámetros de los botones porque comparte naturaleza —una decisión de la consola sobre este
repo, no un dato que ninguna tarea lea— y así comparte también el cache, la escritura atómica y el
temporizador. El `@` la mantiene fuera del espacio de nombres de los `capability_id`, que son
identificadores de Python y no pueden llevarlo.

Antes vivía en `QSettings`, bajo `params/<sha1-de-la-ruta>/<capability_id>`. Esa clave tenía tres
problemas que el archivo resuelve solos:

- **Mover o renombrar la carpeta perdía todo**, porque la huella era de la ruta vieja. Ahora los
  parámetros viajan con la carpeta.
- **Borrar el repo dejaba su basura en el registro** de Windows para siempre.
- **No había forma de mirar ni editar** lo guardado.

`.consola/` está en el `.gitignore` (`core/envfile.py::ensure_gitignored`), así que el archivo no se
commitea: sigue siendo preferencia de esta máquina, solo que guardada donde corresponde. Dos
checkouts del mismo repo tienen cada uno los suyos.

**Excepción — `Capability.scope='machine'`:** instalar un SDK no es una decisión del repo desde el
que se abrió el panel, es de la máquina entera. Un repo no puede opinar sobre dónde va el SDK de
Android, así que esas siguen en `QSettings` bajo `params/machine/<capability_id>`. La regla completa
es **decisión del repo → archivo del repo; decisión de la máquina → `QSettings`**. Por eso la lista
de repos abiertos en pestañas también se queda en `QSettings` (`ui/project_store.py`): un repo no
puede saber que está en tu barra.

`_is_machine()` decide mirando `registry.get_capability(id).is_machine_wide`. Ver
`docs/catalogo-funciones.md §5`.

### Migración automática

La primera vez que se lee un repo que todavía no tiene `params.json`, el store barre las claves
viejas de `QSettings` de ese repo y las adopta (`_adopt_legacy`); el primer guardado las baja al
archivo. Las claves viejas **no se borran**: volver a una versión anterior de Consola sigue
encontrando lo elegido.

### Cache y escrituras agrupadas

Dos accesos dominan y los dos son calientes:

- `ui/rail.py::_missing_keys` llama a `stored_steps` **una vez por capacidad** cada vez que cambias
  de repo — decenas de lecturas seguidas.
- `ParamsPanel._refresh_summary` llama a `save` **en cada tecla** de un campo de texto.

Con una clave por botón en `QSettings` eso lo amortiguaba Qt. Con un archivo hay que hacerlo a mano:
el archivo se lee entero **una vez por repo** a un cache en memoria, y las escrituras se juntan en un
temporizador de 500 ms. Veinte pulsaciones seguidas son **una** bajada a disco; guardar un estado
idéntico al que ya está no escribe nada. `flush()` fuerza la bajada y la llama
`MainWindow.closeEvent`, para que marcar una casilla y cerrar enseguida no pierda el cambio.

La escritura es atómica (temporal + `os.replace`): ahora es un archivo por repo y no una clave por
botón, así que un corte a mitad de escritura se llevaría *todos* los parámetros del repo. Si el
disco no deja escribir (unidad desconectada, solo lectura), lo elegido sigue en el cache y vale para
la sesión — nunca tumba la interfaz.

## 3. Cuándo se guarda y cuándo se lee

- **Se guarda** en cada cambio de casilla: `ParamsPanel._refresh_summary` ya corría con cada señal,
  así que ahí mismo persiste. Un `_restoring` bloquea el guardado mientras el panel se arma y
  mientras se aplica lo guardado, para no escribir los valores de fábrica encima de lo bueno.
- **Se lee** al construir el panel, después de armar las casillas: lo guardado pisa a los valores por
  defecto. Si el catálogo cambió, lo que ya no existe se ignora y los ejes nuevos se quedan con su
  valor por defecto — nunca falla por un preset viejo.

## 4. El botón ▶ del rail corre con esos parámetros

`quick_run` abre (o reusa) la pestaña y aprieta Ejecutar. Como la pestaña recién abierta ya nace con
lo guardado aplicado, el ▶ corre **exactamente** lo que muestra el panel. Si algo lo impide, ya no
falla en silencio: los motivos salen en la consola de esa misma pestaña.

Además, el ámbar del ▶ mira los pasos guardados: un paso apagado no puede reclamar claves de
configuración. Apagar la subida en `build_apk` habilita el ▶ aunque falten las claves del VPS, y
volver a encenderla lo apaga (`ui/rail.py::_missing_keys`). El rail se entera porque el panel emite
`params_changed` y `MainWindow` recalcula.

## 5. Crear el `.consola/config.env` de un repo

El panel de configuración tiene abajo una barra fija con el estado del archivo y un botón:

- **Crear archivo** cuando no existe: lo escribe con **todas** las claves del esquema —las que
  cualquier control puede llegar a pedir— agrupadas por categoría, con un comentario por clave
  (para qué sirve, si es secreta, su ejemplo o su valor por defecto) y **todos los valores en
  blanco**. Es el esqueleto completo para llenar a mano o desde la app.
- **Regenerar archivo** cuando ya existe: la misma estructura, conservando los valores que tenga.
  Sirve cuando el esquema gana claves nuevas.

No destruye nada: lo que esté escrito en el formulario (tecleado o importado) se conserva. Al
escribir, `.consola/` se agrega al `.gitignore` del repo si no estaba.

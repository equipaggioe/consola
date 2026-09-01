# Parámetros persistentes — por repositorio y por botón

## 1. El problema

El panel de parámetros armaba sus casillas desde el catálogo cada vez que se abría una pestaña:
todas las variantes marcadas, los pasos con su `default`, la primera opción de cada eje. Apagar el
paso de subida en `build_apk`, cerrar la pestaña y volver te devolvía la subida encendida. Y el
botón ▶ del rail —que corre sin abrir la pestaña— arrancaba siempre desde esos valores de fábrica.

## 2. La clave lleva las dos cosas: repo y botón

Lo que marcas en el panel es una decisión sobre **ese** repo. El mismo `build_apk` en dos proyectos
casi nunca quiere los mismos pasos. Por eso la clave de guardado es `params/<huella-de-la-ruta>/
<capability_id>` (`ui/params_store.py`), y la huella es un sha1 corto de la ruta normalizada: en
`QSettings` la barra separa grupos, y en Windows la ruta trae además `:` y mayúsculas inestables.

**Excepción — `Capability.scope='machine'`:** instalar un SDK no es una decisión del repo desde el
que se abrió el panel, es de la máquina entera. Esas capacidades guardan bajo
`params/machine/<capability_id>` en vez de por repo: el directorio que elegiste para el SDK de
Android en un proyecto es el mismo directorio en cualquier otro. `_key()` decide cuál de las dos
claves usar mirando `registry.get_capability(id).is_machine_wide`; todo lo demás (cuándo se guarda,
cuándo se lee, qué hace el rail) es idéntico a lo de abajo. Ver
`docs/catalogo-funciones.md §5`.

Va a `QSettings`, no a `.consola/config.env`. El archivo del repo es configuración que el repo
necesita para funcionar; esto es *cómo dejaste la pantalla la última vez* — el mismo criterio que el
orden de pestañas (`ui/project_tabs.py`) y los favoritos (`ui/favorites.py`).

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

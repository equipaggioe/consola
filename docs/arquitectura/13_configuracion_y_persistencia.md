# 13 · Configuración y persistencia

## 1. La regla de reparto

Tres archivos, y de quién es la decisión decide en cuál cae ([ADR-0064](../adr/0064-consola-se-ignora-con-su-propio-gitignore.md), [ADR-0033](../adr/0033-que-es-de-la-app-y-que-del-repo.md)):

| Dónde | Qué | Por qué ahí |
|---|---|---|
| `<repo>/.consola/config.env` | **Datos que las tareas leen**: la IP, el usuario, los argumentos de `install.py` y las credenciales | Es lo que un paso consume para hacer su trabajo |
| `<repo>/.consola/params.json` | **Decisiones de la consola sobre ese repo**: lo marcado en cada botón, los seguros, las pestañas abiertas | Ningún paso lee un `PROTECT_*` ni una casilla; son decisiones, no datos |
| `QSettings` | **Decisiones de esta máquina**: qué repos están en pestañas, las favoritas, las secciones ocultas, los parámetros de las acciones `scope='machine'` | Un repo no puede opinar sobre dónde va el SDK de Android ni sobre qué hay en tu barra |

`.consola/.gitignore`, con `*`, ignora la carpeta entera. Lo escribe `core/envfile.py::ensure_ignored` la primera vez que se escribe en `.consola/`, y si no puede, el guardado falla: sin él, `config.env` queda listo para commitearse. El `.gitignore` del repo no se toca ([ADR-0064](../adr/0064-consola-se-ignora-con-su-propio-gitignore.md)).

## 2. El esquema de claves

`core/settings.py` declara cada clave una sola vez, con dos consumidores: el formulario de Configuración y la validación previa que deja un botón en ámbar.

| Campo | Qué dice |
|---|---|
| `group` | En qué bloque del formulario aparece |
| `secret` | Se enmascara al mostrarla y en el log |
| `default` | El mismo valor para cualquier repo (`ROOT_USER=root`) |
| `default_hint` | El default existe pero lo pone otro (la carpeta de build de cada framework): se muestra de marca de agua |
| `kind='list'` | Campo multilínea; en el archivo se guarda separado por comas |
| `scope` | `repo` (va al archivo) o `machine` (va a `QSettings`) |
| `required_by` | Sin ella, esas acciones no pueden correr |
| `used_by` | Esas acciones la miran, pero corren igual sin ella |

La distinción entre las dos últimas es la que evita un ámbar falso: `backend` nunca lee `API_URL` —quien la lee es el build de Flutter, que la exige—, así que exigirla dejaba el Backend bloqueado por una clave que jamás iba a mirar.

### Las tres fuentes de una clave

Cada línea de `config.env` es de una de tres fuentes ([ADR-0063](../adr/0063-las-lineas-de-config-env-se-clasifican-por-fuente.md)):

| Fuente | Qué claves | Adónde van |
|---|---|---|
| Los campos de `Settings` del repo | Uno por campo de `<SERVER_DIR>/src/app/config.py`, en mayúsculas, salvo `database_url` y `turn_secret`. Los lee `core/fields.py` con `ast` | A `credentials.py` |
| Nombre fijo | `RESTIC_PASSWORD` y `GITHUB_TOKEN` | A `credentials.py` |
| El registro de `core/settings.py` | Los argumentos de `install.py` y las claves propias de Consola | A `install.py`, o las lee Consola |

El formulario muestra las dos primeras en el grupo «Credenciales». Los campos se leen al abrir el repo; un campo que se llame como una clave del registro corta, y un `config.py` sin la clase `Settings` se avisa arriba del formulario.

## 3. Defaults: fijos y dinámicos

`Config.get` resuelve en orden: el valor escrito, el `default` del esquema, y el default dinámico que depende de **este** repo. Una clave con cualquiera de los dos nunca cuenta como faltante, porque igual se va a resolver sola.

| Clave | Default dinámico |
|---|---|
| `DB_USER` | El nombre de la carpeta del repo |
| `DB_NAME` | `<repo>_db` |
| `DOMAIN` | `CF_DOMAIN_NAME` |

`VPS_USER` no tiene default: es la cuenta que administra el VPS, y canone no deja que se llame como la app.

`Config` además tipa: `port()` valida el rango, `flag()` acepta las formas usuales de sí/no, `rel_path()` resuelve contra la raíz del repo y `missing()` es lo que alimenta el ámbar.

Un default fijo tiene un efecto que conviene tener presente: **una clave con default nunca queda en ámbar**, así que declararla `required_by` no agrega nada. Es el caso de `BACKUP_DIR` (`.backups`) y `BACKUP_KEEP` (`7`), que van con `used_by` por eso ([ADR-0045](../adr/0045-la-carpeta-y-el-conteo-de-respaldos-son-configuracion.md)). Que no bloqueen no las vuelve inofensivas: `BACKUP_KEEP` decide cuántos archivos se borran, y por eso la tarea corta con error si lo escrito no es un entero de 1 o más, en vez de caer en el default.

## 4. El archivo `config.env`

Se **regenera** entero desde el esquema al guardar: encabezado, un bloque por grupo, y un comentario por clave que dice para qué sirve y cuál es su default. Las claves ajenas que hubiera en el archivo se conservan al final, bajo «Otras claves»; las de máquina no se escriben aunque vengan en los valores.

Leerlo nunca toca `os.environ`: una tarea no puede pisarle el entorno a las otras pestañas que corren a la vez.

`upsert_value` es la otra escritura posible —reemplaza una sola clave conservando el resto— y la usa «Sincronizar env» ([ADR-0037](../adr/0037-sincronizar-solo-las-claves-compartidas.md)).

## 5. Los repos en pestañas

`QSettings` guarda en `projects/list` la lista de repos abiertos, en orden: ruta y nombre (`ui/project_store.py`). Añadir, quitar y reordenar sobreviven al reinicio. Va aquí y no en un repo porque un repo no puede saber que está en tu barra.

El **color no está en esa lista**: es una decisión sobre ese repo, así que vive en su `params.json` bajo `@theme` y viaja con él. Se guarda la clave de la paleta (`ui/palettes.py`, [ADR-0042](../adr/0042-una-paleta-por-repo.md)), no un hex, para poder afinar la receta sin repintar a mano lo ya guardado. Un repo sin tema guardado —recién clonado, o abierto antes de que hubiera temas— recibe al cargar el primer tema libre y se le escribe en el acto.

La identidad de un repo es su ruta normalizada (`identity`): la misma carpeta escrita con otras barras o con otra caja es un solo repo, y con esa clave se indexan también su espacio de trabajo y su caché de parámetros.

## 6. `params.json`

Un solo archivo por repo, con tres clases de entrada:

```json
{
  "@theme":     { "key": "azul" },
  "@tabs":      { "open": ["build_vite", "backend"] },
  "@protection":{ "vps": true, "db": true, "local": false },
  "build_vite": { "variants": {...}, "options": {...},
                     "fields": {...}, "picks": {...}, "steps": [...] }
}
```

Las dos claves con `@` no chocan con ningún `capability_id`, porque un id es un identificador de Python. Comparten archivo porque comparten naturaleza —decisiones de la consola sobre este repo— y así comparten también la caché, la escritura atómica y el temporizador.

Dos accesos dominan el rendimiento y los dos son calientes: `readiness` lee los pasos guardados de cada capacidad al cambiar de repo, y el panel guarda en cada tecla de un campo. Por eso el archivo se lee entero una vez por repo a una caché en memoria, y las escrituras se juntan en 500 ms. `flush()` las baja; la llama el cierre de la ventana. La escritura es atómica: se arma al lado y se renombra encima.

Un archivo roto a mano se trata como si no hubiera nada, y el primer guardado lo rehace.

## 7. Reponer lo guardado

`ParamsPanel.apply_state` tolera un catálogo que cambió: los valores que ya no existen se ignoran y los ejes nuevos se quedan con su default. Un AVD borrado no fuerza una selección imposible; una cadena vacía guardada en un campo **sí** es una elección válida (significa «el default de la función»), y por eso se distingue de un eje que nunca existió.

## 8. Cachés

`core/cache.py` guarda en `%LOCALAPPDATA%\Consola\cache` (o `~/.cache/consola`) lo que es **catálogo** —listas publicadas por una herramienta, que no cambian en una sesión— y nunca lo que es **estado**:

| Entrada | Edad máxima |
|---|---|
| `android-devices`, `android-images` | Un mes (el default) |
| `android-installed`, `android-avds` | 60 s |
| `vps-services-<host>` | 60 s, y la clave lleva el host: dos repos son casi siempre dos VPS |
| Emuladores vivos | No se cachea nunca |

Una caché ilegible es una caché vacía, nunca un error que corte una tarea. Al terminar una tarea de máquina, `forget_machine_cache()` olvida lo instalado y lo creado.

## 9. El `.env` del servidor

Consola **no escribe** el `.env` de la aplicación administrada, con una excepción explícita: el botón «Sincronizar env», que iguala los valores de las claves que los dos archivos **ya** tienen, en la dirección elegida y con simulacro previo. No crea claves ni vuelca un archivo sobre el otro: cada uno sigue decidiendo qué le corresponde ([ADR-0037](../adr/0037-sincronizar-solo-las-claves-compartidas.md)).

La otra lectura permitida es `database.server_url`, que lee `DATABASE_URL` de `server/.env` para precargar el explorador.

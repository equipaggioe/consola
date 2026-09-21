# 13 · Configuración y persistencia

## 1. La regla de reparto

Tres archivos, y de quién es la decisión decide en cuál cae ([ADR-0017](../adr/0017-datos-en-el-env-decisiones-en-el-json.md), [ADR-0033](../adr/0033-que-es-de-la-app-y-que-del-repo.md)):

| Dónde | Qué | Por qué ahí |
|---|---|---|
| `<repo>/.consola/config.env` | **Datos que las tareas leen**: la IP, el usuario, el token, las rutas, la tabla de rutas públicas | Es lo que un paso consume para hacer su trabajo |
| `<repo>/.consola/params.json` | **Decisiones de la consola sobre ese repo**: lo marcado en cada botón, los seguros, las pestañas abiertas | Ningún paso lee un `PROTECT_*` ni una casilla; son decisiones, no datos |
| `QSettings` | **Decisiones de esta máquina**: qué repos están en pestañas, las favoritas, las secciones ocultas, los parámetros de las acciones `scope='machine'` | Un repo no puede opinar sobre dónde va el SDK de Android ni sobre qué hay en tu barra |

`.consola/` se agrega al `.gitignore` del repo la primera vez que se escribe (`core/envfile.py::ensure_gitignored`). Un fallo al tocar el `.gitignore` nunca rompe el guardado.

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

La distinción entre las dos últimas es la que evita un ámbar falso: `backend` nunca lee `API_URL` —quien la lee es el build de Flutter, y ese ya la pide por paso—, así que exigirla dejaba el Backend bloqueado por una clave que jamás iba a mirar.

## 3. Defaults: fijos y dinámicos

`Config.get` resuelve en orden: el valor escrito, el `default` del esquema, y el default dinámico que depende de **este** repo. Una clave con cualquiera de los dos nunca cuenta como faltante, porque igual se va a resolver sola.

| Clave | Default dinámico |
|---|---|
| `VPS_USER` | El nombre de la carpeta del repo |
| `DB_USER` | `VPS_USER` ya resuelto |
| `DB_NAME` | `<VPS_USER>_db` |
| `GITHUB_KEY_TITLE` | `<repo>-vps`. Se deriva del repo y no del VPS: cambiar de servidor dejaría huérfana la llave vieja en la cuenta |
| `PUBLIC_HOST` | `CF_RECORD_NAME`, si no `CF_DOMAIN_NAME`, si no `VPS_IP` |
| `BACKEND_HOST` | `127.0.0.1` si la tabla de rutas tiene alguna regla `proxy`, si no `0.0.0.0` ([ADR-0020](../adr/0020-ruta-publica-no-implica-proxy.md)) |

`Config` además tipa: `port()` valida el rango, `flag()` acepta las formas usuales de sí/no, `rel_path()` resuelve contra la raíz del repo y `missing()` es lo que alimenta el ámbar.

## 4. El archivo `config.env`

Se **regenera** entero desde el esquema al guardar: encabezado, un bloque por grupo, y un comentario por clave que dice para qué sirve y cuál es su default. Las claves ajenas que hubiera en el archivo se conservan al final, bajo «Otras claves»; las de máquina no se escriben aunque vengan en los valores.

Leerlo nunca toca `os.environ`: una tarea no puede pisarle el entorno a las otras pestañas que corren a la vez.

`upsert_value` es la otra escritura posible —reemplaza una sola clave conservando el resto— y la usa «Sincronizar env» ([ADR-0037](../adr/0037-sincronizar-solo-las-claves-compartidas.md)).

## 5. `params.json`

Un solo archivo por repo, con tres clases de entrada:

```json
{
  "@tabs":      { "open": ["update_remote", "backend"] },
  "@protection":{ "vps": true, "db": true, "local": false },
  "update_remote": { "variants": {...}, "options": {...},
                     "fields": {...}, "picks": {...}, "steps": [...] }
}
```

Las dos claves con `@` no chocan con ningún `capability_id`, porque un id es un identificador de Python. Comparten archivo porque comparten naturaleza —decisiones de la consola sobre este repo— y así comparten también la caché, la escritura atómica y el temporizador.

Dos accesos dominan el rendimiento y los dos son calientes: `readiness` lee los pasos guardados de cada capacidad al cambiar de repo, y el panel guarda en cada tecla de un campo. Por eso el archivo se lee entero una vez por repo a una caché en memoria, y las escrituras se juntan en 500 ms. `flush()` las baja; la llama el cierre de la ventana. La escritura es atómica: se arma al lado y se renombra encima.

Un archivo roto a mano se trata como si no hubiera nada, y el primer guardado lo rehace.

## 6. Reponer lo guardado

`ParamsPanel.apply_state` tolera un catálogo que cambió: los valores que ya no existen se ignoran y los ejes nuevos se quedan con su default. Un AVD borrado no fuerza una selección imposible; una cadena vacía guardada en un campo **sí** es una elección válida (significa «el default de la función»), y por eso se distingue de un eje que nunca existió.

## 7. Cachés

`core/cache.py` guarda en `%LOCALAPPDATA%\Consola\cache` (o `~/.cache/consola`) lo que es **catálogo** —listas publicadas por una herramienta, que no cambian en una sesión— y nunca lo que es **estado**:

| Entrada | Edad máxima |
|---|---|
| `android-devices`, `android-images` | Un mes (el default) |
| `android-installed`, `android-avds` | 60 s |
| `vps-services-<host>` | 60 s, y la clave lleva el host: dos repos son casi siempre dos VPS |
| Emuladores vivos | No se cachea nunca |

Una caché ilegible es una caché vacía, nunca un error que corte una tarea. Al terminar una tarea de máquina, `forget_machine_cache()` olvida lo instalado y lo creado.

## 8. El `.env` del servidor

Consola **no escribe** el `.env` de la aplicación administrada, con una excepción explícita: el botón «Sincronizar env», que iguala los valores de las claves que los dos archivos **ya** tienen, en la dirección elegida y con simulacro previo. No crea claves ni vuelca un archivo sobre el otro: cada uno sigue decidiendo qué le corresponde ([ADR-0037](../adr/0037-sincronizar-solo-las-claves-compartidas.md)).

La otra lectura permitida es `database.server_url`, que lee `DATABASE_URL` de `server/.env` para precargar el explorador.

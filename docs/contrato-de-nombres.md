# El contrato de nombres — un botón, una declaración

Plan de reestructuración de la capa que va del catálogo a la función. No cambia los niveles 0, 1 y 2
([nivel-0.md](nivel-0.md), [atomicas.md](atomicas.md)): cambia **cómo se nombra lo que ya existe**, y
con eso desaparece una capa entera.

---

## 1. El problema medido

Hoy el identificador de cada paso y de cada eje se escribe **tres veces, en tres archivos**:

| Dónde | Qué declara | Ejemplo |
|---|---|---|
| `core/catalog.py` | id + etiqueta + default | `Step('bump_version', 'Subir el número de versión')` |
| `ui/task_adapters.py` | el mismo id, re-tipeado | `'bump': 'bump_version' in steps` |
| `core/tasks/builders.py` | el id como parámetro | `def build_apk(ctx, *, bump=True, ...)` |

Números sobre el catálogo actual:

```
capacidades registradas                     53
con cuerpo real (bind)                      52
con entrada en ADAPTERS                     32
→ con cuerpo pero corriendo como STUB       20
listas de pasos en el catálogo              13
listas de ids repetidas en el adaptador     13   (6 tuplas + 7 literales sueltos)
```

**Las 20 de la tercera línea son el hallazgo.** `TabPanel._run` exige *las dos cosas* para correr de
verdad:

```python
adapter = ADAPTERS.get(capability.id)
if capability.func is None or adapter is None:
    self._run_stub(console, payload)      # simula
```

`health_check`, `ssh_login`, `ssh_tunnel`, `inspect_db`, `run_seeders`, `teardown_db`,
`backup_db`, `view_logs`, `sync_common_files`, `systemd_action`… tienen cuerpo escrito y probado, y
la interfaz los simula porque **falta una línea en un diccionario**. Tres de ellos ni siquiera
reciben parámetros: les alcanzaría con `lambda payload: {}`.

El adaptador no es solo duplicación. Es una **compuerta**, y hay 20 capacidades apagadas detrás.

---

## 2. Por qué existe el adaptador

Comparé, para las 32 capacidades conectadas, los ids que declara el catálogo contra la firma real de
la función:

```
DIRECTOS  (el id YA es el nombre del parámetro)   19
TRADUCEN  (hay desalineación real)                13
```

Los 13 que traducen lo hacen por **tres causas**, y ninguna es fundamental:

### Causa A — divergencia gratuita de nombres

Dos archivos nombrando la misma cosa distinto. No hay razón detrás.

| Capacidad | Catálogo dice | La función espera |
|---|---|---|
| `build_apk` | `bump_version`, `apk_build`, `upload_to_vps`, eje `app` | `bump`, `build`, `upload`, `directory` |
| `build_vite` | `bump_version`, `vite_build`, `upload_to_vps`, eje `target` | `bump`, `build`, `upload`, `directories` |
| `build_binary` | `bump_version`, `binary_build`, `binary_checksum` | `bump`, `build`, `checksum` |
| `publish_code` | `push_repo`, `git_pull`, `install_deps`, `upload_secrets` | `push`, `pull`, `deps`, `upload` |
| `update_remote` | + `apply_migrations`, `restart_service` | + `migrate`, `restart` |
| `setup_ssh_key` | `deploy_access`, `sudo_rules`, `verify_login` | `access`, `sudo`, `verify` |
| `run_mobile` / `terminal` | eje `app` | `target` |

### Causa B — un segmentado de dos valores que en realidad es un booleano

El catálogo sabe cuál de los dos valores significa "sí", pero hoy **no tiene dónde decirlo**, así que
lo dice el adaptador con una comparación de cadenas.

| Eje | Comparación escrita a mano | Parámetro |
|---|---|---|
| `dry_run` `['simulacro','borrar']` | `== 'borrar'` | `apply` |
| `mode` `['simulacro','aplicar']` | `== 'aplicar'` | `apply` |
| `boot` `['normal','borrar datos']` | `== 'borrar datos'` | `wipe` |
| `window` `['consola','ventana']` | `== 'ventana'` | `windowed` |
| `packaging` `['un archivo','carpeta']` | `!= 'carpeta'` | `onefile` |
| `vps_dirty` `['preguntar','descartar']` | `== 'descartar'` | `discard_changes` |
| `auto_login` `['no','sí']` | `== 'sí'` | `auto_login` |

### Causa C — `composed_of` deriva pasos cuyos ids son ids de capacidad

`registry.resolve_steps()` inventa un `Step` por cada entrada de `composed_of` cuando no hay `steps=`.
Esos ids son nombres de *botones* (`generate_remote_keypair`), y jamás van a coincidir con un nombre
de parámetro (`generate`). Afecta a 5 capacidades: `setup_github_ssh`, `install_android_sdk`,
`revoke_github_ssh`, `install_systemd`, `run_setup_scripts`.

Ya se corrigió a mano en 11 capacidades declarando `steps=` explícitos — el catálogo lo documenta
como error repetido. Queda formalizarlo.

### Lo único irreducible

`_bump_mode`: el eje `bump_mode` combina un componente SemVer excluyente con `build` opcional y
produce la cadena `'patch+build'`. Eso es cómputo real, no un nombre mal puesto. **Un caso de 53.**

---

## 3. El contrato

> **El catálogo declara los nombres que la función usa. `label` y `labels` llevan lo que lee el
> humano. No hay un segundo vocabulario.**

Tres reglas:

1. **`Step.id` es el nombre del keyword-argument.** Si la función recibe `bump=True`, el paso se
   llama `bump`. La etiqueta visible vive en `Step.label` y puede cambiar sin tocar nada más.
2. **`AxisDef.name` es el nombre del keyword-argument.** Si la función recibe `directory`, el eje se
   llama `directory` aunque el rótulo diga "App móvil".
3. **`composed_of` no genera pasos.** Es documentación: de qué botones está hecho este botón. Quien
   necesita casillas declara `steps=`.

Con eso, leer el payload deja de necesitar conocimiento por capacidad y pasa a ser una operación
sobre la declaración: **`Capability.kwargs_from(payload)`**.

### Por qué eso hoy no se puede

El payload viene agrupado por **cómo dibujó el panel**, no por qué significa:

```python
{'variants': {...},   # ejes select='many'      → casillas
 'options':  {...},   # ejes select='one'       → segmentado / menú / botones
 'fields':   {...},   # expand='field'          → texto escrito
 'picks':    {...},   # expand='pick'           → lista larga con búsqueda
 'steps':    [ids]}   # las casillas de pasos
```

Por eso el adaptador tiene `_option()`, `_field()`, `_pick()`, `_variant()`: hay que saber en qué
balde cayó cada eje. Pero **la capacidad ya sabe** el `expand` y el `select` de cada uno de sus ejes.
El genérico consulta su propia declaración y elige el balde solo.

### Lo que hay que agregar al modelo

Un solo campo, para la causa B:

```python
@dataclass
class AxisDef:
    ...
    truthy: str = ''   # solo select='one' con dos valores: cuál significa True.
                       # Convierte el eje en un booleano para la funcion sin que
                       # nadie compare cadenas fuera del catalogo.
```

```python
# antes                                          # despues
AxisDef('dry_run', ['simulacro','borrar'],       AxisDef('apply', ['simulacro','borrar'],
        'scope')                                         'scope', truthy='borrar')
# + en el adaptador:
#   apply = payload['options']['dry_run'] == 'borrar'
```

El botón **Simulacro** sigue funcionando: `ParamsPanel._dry_run_axis` detecta el eje por el *valor*
`'simulacro'`, no por el nombre ([params_panel.py:512](../ui/params_panel.py#L512)).

---

## 4. La formación de un botón, capa por capa

Lo que sigue es el recorrido completo de una pulsación, marcando qué cambia y qué no.

```
  ┌─ Nivel 0 · plomería ──────────────────────── core/*.py
  │   ssh.run()  db.Connection  files.remove()  process.capture()
  │   No conoce ctx. No es una capacidad. NO CAMBIA.
  ↓
  ┌─ Nivel 1 · atómica ───────────────────────── core/tasks/<grupo>.py
  │   def create_role(ctx, scope='local') -> str
  │   Un paso del dominio, idempotente, recibe ctx. NO CAMBIA.
  ↓
  ┌─ Nivel 2 · compuesta ─────────────────────── core/tasks/<grupo>.py
  │   def bootstrap_db(ctx, scope, *, role=True, database=True, ...)
  │   Encadena atómicas. Sus keyword-args SON el contrato. NO CAMBIA.
  ↓
  ┌─ Forma · catálogo ────────────────────────── core/catalog.py
  │   Capability(id=..., axes=[AxisDef(...)], steps=[Step(...)])
  │   ► CAMBIA: los ids pasan a ser los nombres de los kwargs.
  ↓
  ┌─ Puente · registro ───────────────────────── core/registry.py
  │   registry.bind('bootstrap_db', bootstrap_db)
  │   ► GANA: Capability.kwargs_from(payload)
  ↓
  ┌─ Panel ───────────────────────────────────── ui/params_panel.py
  │   dibuja ejes y casillas → payload{variants,options,fields,picks,steps}
  │   No cambia. Sigue agrupando por tipo de control.
  ↓
  ┌─ Traducción ──────────────────────────────── ui/task_adapters.py
  │   ADAPTERS[cap.id](payload) → kwargs
  │   ► DESAPARECE. Lo reemplaza cap.kwargs_from(payload).
  ↓
  └─ Corrida ─────────────────────────────────── ui/task_runner.py
      TaskRunner(cap.id, project, cap.func, kwargs) → cap.func(ctx, **kwargs)
      No cambia.
```

**Los tres niveles del dominio no se tocan.** Ni una función de `core/`, y de `core/tasks/` una sola
firma (§5, causa D). El cambio vive entero entre el catálogo y el runner.

### El mismo botón, antes y después

```python
# ── ANTES ──────────────────────────────────────────────────────────────────
# core/catalog.py
BUILD_APK_STEPS = [
    Step('bump_version', 'Subir el número de versión'),
    Step('apk_build', 'Compilar el APK', requires_env={'API_URL'}),
    Step('upload_to_vps', 'Subir el APK al VPS', default=False, requires_env=_VPS_KEYS),
]
axes=[AxisDef('app', [], 'scope', label='App móvil', discover=targets.MOBILE_APP), _BUMP_AXIS()]

# ui/task_adapters.py
def _build_apk_kwargs(payload: dict) -> dict:
    steps = set(payload.get('steps') or [])
    return {'directory': _option(payload, 'app'),
            'bump_mode': _bump_mode(payload),
            'bump': 'bump_version' in steps,
            'build': 'apk_build' in steps,
            'upload': 'upload_to_vps' in steps}
ADAPTERS = {..., 'build_apk': _build_apk_kwargs, ...}

# core/tasks/builders.py
def build_apk(ctx, directory='', bump_mode='patch', *, bump=True, build=True, upload=False)

# ── DESPUÉS ────────────────────────────────────────────────────────────────
# core/catalog.py                      (los ids son los parámetros)
BUILD_APK_STEPS = [
    Step('bump', 'Subir el número de versión'),
    Step('build', 'Compilar el APK', requires_env={'API_URL'}),
    Step('upload', 'Subir el APK al VPS', default=False, requires_env=_VPS_KEYS),
]
axes=[AxisDef('directory', [], 'scope', label='App móvil', discover=targets.MOBILE_APP), _BUMP_AXIS()]

# ui/task_adapters.py                  → no hay entrada; el genérico lo arma

# core/tasks/builders.py               → idéntica, sin tocar
def build_apk(ctx, directory='', bump_mode='patch', *, bump=True, build=True, upload=False)
```

Un botón nuevo pasa de **4 declaraciones en 3 archivos** a **1 declaración en 1 archivo**.

### Dónde queda lo irreducible

`bump_mode` sigue necesitando cómputo. No vuelve una tabla por capacidad: es una propiedad del eje.

```python
AxisDef('bump_mode', BUMP_MODES, 'scope', combine={'build'}, default='patch',
        join='+')   # los valores marcados se unen con '+': 'patch+build'
```

Si aparece un caso que ni `truthy` ni `join` cubren, la salida es un `derive=` opcional en `AxisDef`
—una función que recibe lo marcado y devuelve el valor— **no** un diccionario global de excepciones.
La regla es que la excepción viva pegada al eje que la causa.

---

## 5. Los pasos

Cada uno deja el árbol corriendo y es verificable solo.

| # | Paso | Alcance | Verificación |
|---|---|---|---|
| 1 | `Capability.kwargs_from()` en `core/registry.py`, conviviendo con `ADAPTERS` | — | Un script compara, para las 32 conectadas, `kwargs_from(payload)` contra `ADAPTERS[id](payload)`. Deben coincidir en las 19 directas. |
| 2 | `AxisDef.truthy` + `join` | 7 ejes | Las 6 comparaciones de cadena salen del adaptador. |
| 3 | Causa A: renombrar ids en el catálogo | 8 capacidades | Las 8 pasan a "directas" en el script del paso 1. |
| 4 | Causa C: `steps=` explícitos; `resolve_steps` deja de derivar de `composed_of` | 5 capacidades | Las 5 pasan a directas. |
| 5 | Borrar `ui/task_adapters.py`; `TabPanel._run` usa `cap.kwargs_from` | — | Las 32 siguen corriendo igual. |
| 6 | Conectar las 20 apagadas: declarar sus ejes y pasos faltantes | 20 capacidades | Dejan de simular. |
| 7 | `ctx.step('role')` resuelve la etiqueta del catálogo | 13 compuestas | La etiqueta se escribe una sola vez; se acaba la deriva de acentos. |
| 8 | `rebuild_db` delega en `bootstrap_db`; se borra `populate_db` | 2 funciones | El tramo compartido deja de estar duplicado. |

Los pasos 1–5 son la reestructuración. El 6 es la cosecha: es donde se ven las 20 capacidades que hoy
están escritas y apagadas. El 7 y el 8 son la limpieza que habilita el contrato.

### Resultado del paso 1

`Capability.kwargs_from()` está en [core/registry.py](../core/registry.py), conviviendo con `ADAPTERS`
sin reemplazarlo todavía. El script de verificación corre las 32 capacidades conectadas contra 31
payloads cada una —el de los defaults más 30 con marcas al azar— y compara las dos lecturas:

```
DIRECTAS  18   kwargs_from ya devuelve exactamente lo que devuelve su adaptador
TRADUCEN  14   hay desalineación real
APAGADAS  20   con cuerpo y sin adaptador (el conteo del §1 se confirma)
```

Estimé 19/13 leyendo el código; medido son 18/14. La diferencia y una sorpresa:

- **`stop_emulator` no era directa.** No declara ningún eje: el `serial` se lo pasa el ✕ de la
  cabecera de estado en un payload fabricado a mano. `kwargs_from` devuelve `{}` y pierde el serial.
  Se arregla declarando `AxisDef('serial', [], 'pick')`, que es cierto aunque no se dibuje ningún
  panel. Va con el paso 6.
- **`clean_artifacts` traduce con dos tablas de etiquetas**, no con un renombre: los valores del eje
  son texto legible (`'Gradle/Android'`) y el adaptador los mapea a las claves reales (`'gradle'`).
  Es la causa A con otra forma, y no necesita nada nuevo: `AxisDef.labels` ya existe y el panel ya
  dibuja las casillas con `text_of()` ([params_panel.py:404](../ui/params_panel.py#L404)). Los
  valores pasan a ser las claves y `labels=` lleva lo que se lee. Las dos tablas del adaptador se
  borran sin reemplazo.

#### La única enmienda al plan: una causa D

`install_android_sdk` es la única compuesta de las 13 que **no** recibe un booleano por paso, sino la
lista de ids:

```python
def install_android_sdk(ctx, install_dir='', components=None, api_level='', build_tools='',
                        steps: list[str] | None = None)
```

El contrato no la puede expresar, y hacerle un hueco a `steps=` sería devolver la excepción por
capacidad que este plan viene a sacar. La salida es alinearla con las otras doce compuestas —
`tools=True, packages=True, hypervisor=True`— cambiando el `in activos` por el booleano. Es la única
firma de `core/tasks/` que se toca en todo el plan, y se toca porque el contrato la delata como la
rara, no por comodidad de la interfaz. Va con el paso 4.

### Sobre el paso 6

No todas las 20 se encienden solas. Se reparten así:

- **Alcanza con declarar que no llevan parámetros** (3): `health_check`, `ssh_login`, `ssh_tunnel`.
- **Les falta el eje en el catálogo** (9): `inspect_db`, `run_seeders`, `run_mock_seeders` y otras
  reciben `scope` en la función pero el catálogo nunca les dio el eje. El arreglo está en el
  catálogo, que es donde corresponde.
- **Les falta `steps=`** (4): `teardown_db` es `level='C'` sin pasos; sus dos booleanos no tienen
  casilla.
- **Tienen desalineación de las causas A/B** (4): `run_setup_scripts` (eje `where` → param `scope`),
  `sync_common_files` (eje `mode` → param `apply`), `view_logs`, `systemd_action`.

### Resultado de los pasos 2 a 8

El oráculo cambió a mitad de camino, y tenía que cambiar: mientras existió el adaptador se podía
comparar `kwargs_from` contra él, pero apenas se renombra un id el adaptador queda viejo y deja de
ser autoridad. **La firma de la función no.** La verificación final contrasta, para las 52
capacidades con cuerpo, lo que `kwargs_from` produce contra `inspect.signature(cap.func)`:

```
CUMPLEN   51   los kwargs entran en la firma, sin sobrar ni faltar
FALLA      1   upload_to_vps
ctx.step() que no resuelve      ninguno
paneles que se arman y emiten un payload válido    48 de 48 probados
```

La que falla es correcta que falle: `upload_to_vps` está bindeada a `upload_artifact(ctx, local:
Path, ...)`, cuyo primer argumento es una ruta que calcula quien la llama. Es una atómica oculta que
existe para que los tres builders la nombren en `composed_of`; **no hay panel que pueda producir un
`Path`**, y por eso no tiene botón. El contrato la delata en vez de taparla, que es lo que se le
pide.

Tres cosas que aparecieron al ejecutar y no estaban previstas:

- **`systemd_action` tenía dos ejes para un solo parámetro.** `action` (start/stop/restart/status) y
  `action_ext` (enable/disable/…), contra una función que recibe un `action`. La partición ni
  siquiera existía en el panel: `expand='buttons'` y `expand='menu'` se dibujan igual, nadie los
  distingue. Quedó un eje con los nueve valores, y su default pasó a `status` —el de la firma— y no
  `start`: el valor que arranca marcado es el que corre si alguien aprieta Ejecutar sin mirar.
- **`view_logs.follow` era un `expand='field'` con valores `['sí','no']`**: un booleano dibujado como
  campo de texto libre, que además nunca llegaba a la función. Ahora es un segmentado con `truthy`.
- **`ctx.step()` obligó a `ctx.child()` en las compuestas anidadas.** Si la etiqueta se resuelve
  contra `ctx.capability_id`, una compuesta que llama a otra pasándole su propio `ctx` hace que los
  pasos de la de adentro se busquen en la de afuera. `bootstrap_vps`, `clean_vps` y
  `run_setup_scripts` ahora le dan `ctx.child('bootstrap_db')` a lo que encadenan. La excepción
  deliberada es `update_remote → publish_code`, que **sí** comparte `ctx` porque declara los cuatro
  pasos de la de adentro como propios: el panel muestra las seis casillas planas.

---

## 6. Qué se deshace de lo ya hecho

| Cambio reciente | Destino |
|---|---|
| `populate_db` en `core/tasks/database.py` | **Queda** (desviación del plan, ver abajo). |
| `_MIGRATE_DB_STEPS` y los otros 5 tuplas de ids | **Se borran** con el archivo entero. |
| `_migrate_db_kwargs` y los 3 adaptadores gemelos de base de datos | **Se borran.** Eran la misma función copiada cuatro veces. |
| Las etiquetas de pasos reescritas (verbo + objeto) | **Quedan.** Pasan a ser la única fuente: `ctx.step` las lee del catálogo (paso 7). |
| `MIGRATE_DB_STEPS` con `generate` / `apply` | **Queda.** Los ids ya coinciden con los parámetros de `migrate_db`; es una de las 19 directas. |
| Extensiones descubiertas desde el repo | **Queda.** Es lógica de dominio, ajena a este contrato. |

### Los parámetros guardados

`ui/params_store.py` guarda por repo y por botón el estado del panel, con los ids como claves. Al
renombrar ids (pasos 3 y 4), lo guardado para esas 13 capacidades queda obsoleto y vuelve a los
defaults del catálogo. `ParamsPanel.apply_state` ya tolera un catálogo cambiado: ignora lo que no
existe y deja los ejes nuevos en su default ([params_panel.py:614](../ui/params_panel.py#L614)).

**No se escribe ningún puente al formato viejo.** Es un cambio limpio: se pierden las marcas
guardadas de esos botones, una vez.

### La desviación del paso 8

El plan decía borrar `populate_db` y que `rebuild_db` llamara a `bootstrap_db` con los cuatro pasos
de creación en `False`, copiando el patrón de `update_remote → publish_code`. Al escribirlo se ve que
el patrón no aplica:

- `publish_code` **no emite `ctx.note()`**, por eso `update_remote` lo puede envolver sin ensuciar el
  log. `bootstrap_db` sí lo emite, y termina con «Bootstrap de base completado» — una línea falsa al
  final de una reconstrucción.
- `bootstrap_db(role=False, database=False, privileges=False, extensions=False)` es, literalmente,
  «un bootstrap que no crea nada». Eso ya tiene nombre, y es `populate_db`. Reemplazar un helper con
  nombre por cuatro banderas apagadas esconde el tramo compartido en vez de mostrarlo.

`populate_db` no era el parche: el parche era **creer que alcanzaba con eso**. Su problema era estar
solo, no existir. Con el contrato puesto, es lo que es: la cola compartida de los dos caminos, con
nombre propio y sin botón, y sus `ctx.step()` resuelven bien desde las dos porque `bootstrap_db` y
`rebuild_db` declaran los mismos cuatro ids.

---

## 7. Qué NO cambia

- **Nivel 0.** Ni una función de `core/*.py`.
- **Nivel 1 y 2.** Son ellas las que definen los nombres buenos; el catálogo se acomoda a ellas, no
  al revés. La única firma que se tocó es `install_android_sdk`, que recibía la lista de pasos en vez
  de un booleano por paso y era la única de las 13 compuestas fuera de la norma (§5, causa D).
- **El criterio de qué es atómica y qué compuesta.** Sigue siendo la pregunta de
  [atomicas.md §1](atomicas.md): *¿tiene sentido re-ejecutar esto solo?*
- **La separación forma / cuerpo.** `registry.bind()` sigue siendo el único puente. El catálogo
  declara nombres, no funciones: por eso **no** se adopta un `Step(run=create_role)`, que crearía un
  ciclo de imports (`core/tasks/utils.py` ya importa `catalog`) y borraría la razón de ser de `bind`.
- **El panel.** Sigue agrupando el payload por tipo de control. Lo que cambia es quién sabe leerlo.

# Panel de parámetros — de "un botón por variante" a "una acción con estado"

Complementa `PLAN.md` §2.4 (ejes), §9 (configuración) y `capacidades-por-repo.md` §3
(descubrimiento de variantes). Fecha: 2026-08-23.

---

## 1. El cambio de fondo

Hoy cada valor de eje genera **su propio botón** en el rail: `Servir SPA panel`,
`Servir SPA backoffice`, `Servir SPA landing`. Son tres filas para una sola acción, y no hay forma de
correr las tres de un toque.

La propuesta invierte eso: **el botón es la acción, los valores son estado del panel**. Una fila
`Build Vite`, y las apps pasan a casillas. Consecuencias, en orden de importancia:

1. **Una sola ejecución cubre varias variantes** — el pedido original. Marcas `panel` y
   `backoffice`, un toque, corren las dos.
2. **El rail se achica.** De 55 botones a 43 — las filas duplicadas por eje desaparecen y las
   capacidades atómicas (`bump_version`, `upload_to_vps`) dejan de ser botones para ser pasos. El rail vuelve a ser una lista navegable de un vistazo.
3. **Los pasos de una acción compuesta se vuelven visibles.** Hoy `build_apk` hace bump + build +
   subida y no hay manera de saberlo mirando la UI, mucho menos de saltarse la subida.

Lo que se pierde: el toque único desde el rail para *una* variante puntual. Lo compensa el gesto del
§5 — la pestaña queda abierta con su selección hecha, así que repetir es un clic en la pestaña y otro
en Ejecutar, sin volver a marcar nada.

---

## 2. No todos los ejes son casillas

Es la decisión que hay que acertar. `panel|backoffice|landing` son un **conjunto**: correr dos tiene
sentido. `start|stop|restart` son **alternativas**: correr dos es un absurdo (¿arrancar y parar?).
Meterlos a los dos en casillas produciría una UI que permite pedir cosas imposibles.

Así que `AxisDef` gana un campo de cardinalidad:

```python
AxisDef('target', discover(kind='spa-vite'), expand='checks', select='many')
AxisDef('action', ['start','stop','restart','status'], expand='buttons', select='one')
```

Cómo queda el catálogo actual:

| Eje | Capacidad | `select` | Se ve como |
|---|---|---|---|
| `target` (apps Vite) | `serve_vite`, `build_vite` | **many** | casillas |
| `app` (apps Flutter) | `run_mobile`, `build_apk` | **many** | casillas |
| `avds` / `images` (limpieza) | `purge_emulators` | **many** | casillas |
| `device` / `image` / `avd` | `create_avd`, `install_system_image`, `launch_emulator` | one | lista larga con búsqueda (`pick`) |
| `action` (systemd) | `systemd_action` | one | segmentado |
| `bump_mode` | `build_apk` (con `+build`), `build_vite` / `build_binary` (SemVer pelado) | one | segmentado |
| `packaging` / `window` | `build_binary` | one | segmentado |
| `entrypoint` / `name` / `icon` | `build_binary` | one | campo escrito (vacío = se deduce) |
| `scope` (local/remoto) | `bootstrap_db`, `migrate_db`, … | one | segmentado |
| `dry_run` (simulacro/borrar) | `clean_artifacts`, `sync_common_files` | one | segmentado |
| `follow` (sí/no) | `view_logs` | one | switch |

Regla para los que vengan: **¿tiene sentido pedir dos a la vez?** Sí → `many`. No → `one`.
Los `many` casi siempre son targets descubiertos del repo; los `one` casi siempre son modos de la
herramienta. Es la misma frontera de `capacidades-por-repo.md` §3, vista desde otro ángulo.

**Un cuarto tipo, agregado con los instaladores de SDK:** `expand='field'` es para un eje que no se
elige de una lista, se escribe — un directorio de instalación, un API level. `values[0]` es el
valor por defecto (lo que la función usa si el campo queda vacío), y se dibuja como un `QLineEdit`,
no como casillas ni segmentado. `Capability.field_axes` los separa del resto; ver el detalle de
implementación en `docs/catalogo-funciones.md §7.1`.

---

## 3. Los pasos también son casillas

`composed_of` deja de ser metadato invisible y pasa a ser la sección **Pasos** del panel. Cada paso
declara si se puede desmarcar:

```python
Capability(
    id='build_binary', name='Build binario',
    steps=[
        Step('bump_version',    'Bump versión',      optional=True, default=True),
        Step('binary_build',    'Compilar binario',  optional=True, default=True),
        Step('binary_checksum', 'Checksum SHA-256',  optional=True, default=True),
        Step('upload_to_vps',   'Subir al VPS',      optional=True, default=False,
             requires_env={'VPS_IP','VPS_USER','VPS_KEY_NAME'}),
    ],
)
```

`optional=False` se dibuja marcado y deshabilitado: existe para el paso núcleo que sin él deja a la
capacidad sin significado. Y un paso puede tener sus propios requisitos de config — de ahí sale la
advertencia contextual del §5.

**`binary_build` era ese caso y dejó de serlo** (ver `atomicas.md §4.5`). Se declaraba
`optional=False` con el argumento de que «PyInstaller no deja nada re-subible sin volver a
empaquetar», y eso era falso: `dist/` conserva el ejecutable, y el script original traía un flag
`BUILD_BINARY=false` para subirlo sin recompilar. Los tres builders comparten hoy la misma economía:
retomar un `scp` cortado no debería costar otro build — ni, en el caso de Vite, otro `npm install`,
ni, en el del binario, otro análisis completo de dependencias.

Esto absorbe el eje `copy_to_vps=['local','con subida']` que hoy tienen `build_apk` y `build_vite`:
deja de ser un eje y pasa a ser la casilla del paso `upload_to_vps`, que es lo que siempre fue.

---

## 4. Anatomía del panel

```
┌─ PARÁMETROS ─────────────────────────┐
│ 🏗️  Build Vite                        │
│ navetta · 2 apps × 3 pasos            │
├───────────────────────────────────────┤
│ APPS                  todas · ninguna │
│  ☑ panel                              │
│  ☑ backoffice                         │
│  ☐ landing                            │
├───────────────────────────────────────┤
│ PASOS                                 │
│  ☑ Bump versión           patch  ▾    │
│  ☑ Build Vite                         │
│  ☑ Subir al VPS                       │
├───────────────────────────────────────┤
│ OPCIONES                              │
│  Destino        ( local │ remoto )    │
├───────────────────────────────────────┤
│ ⚠  Falta VPS_IP para "Subir al VPS"   │
│    → Configurar                       │
├───────────────────────────────────────┤
│                        ▶  Ejecutar    │
└───────────────────────────────────────┘
```

La línea `2 apps × 3 pasos` es la que hace legible el costo de lo que estás por lanzar **antes** de
apretar. Sin ella, marcar tres apps y tres pasos es un compromiso invisible de varios minutos.

**Dónde va:** columna derecha, en un `QSplitter` horizontal contra la consola, con el panel de
configuración del repo apilado debajo en un `QSplitter` vertical. Izquierda = *qué puedo correr*,
centro = *qué está pasando*, derecha = *con qué parámetros y con qué configuración*. Ambos divisores
se arrastran y se colapsan, así que la repartición 460/420 es solo el punto de partida.

---

## 5. El gesto: la pestaña ES la instancia de la acción

El clic en una fila del rail **abre o enfoca la pestaña de esa acción — no ejecuta nada.** La
pestaña de segundo nivel deja de ser "una ejecución pasada" y pasa a ser la *instancia viva* de la
acción: tiene su consola y su panel de parámetros, los dos suyos.

| Gesto | Qué hace |
|---|---|
| Clic en la fila del rail | Abre la pestaña de la acción (o la enfoca si ya existe). El panel se llena con sus parámetros. |
| Clic en la pestaña | Vuelve a esa acción: reaparecen sus parámetros tal como los dejaste, y su consola con lo que ya corrió |
| `▶ Ejecutar` en el panel | Corre con lo que está marcado. Se puede repetir cuantas veces quieras sin reabrir nada |

Esto resuelve el riesgo de "configurar antes de correr agrega un paso": el paso se paga **una vez al
abrir la acción**, no en cada ejecución. La segunda, tercera y décima corrida del día son un clic en
la pestaña y otro en Ejecutar, con todo ya marcado.

El estado vive en el panel de cada pestaña, así que dos acciones abiertas no se pisan, y dos repos
tampoco: cada repo tiene su propio `TabPanel` con sus propias pestañas. (La persistencia entre
sesiones — la tabla `presets` de `PLAN.md` §8 — es el paso siguiente; hoy el estado dura lo que dura
la pestaña.)

**Nada corre solo.** Ninguna acción se dispara al abrir la pestaña, ni siquiera las inofensivas.
Para las destructivas eso importa el doble: `Limpiar VPS` abre su panel con los pasos a la vista, y
recién ahí decides.

---

## 6. El `.env`: panel apilado debajo, no vista aparte

**Decisión tomada:** el panel de configuración del repo va apilado bajo el de parámetros, en la
misma columna derecha. Se descartó llevarlo a la vista de Configuración del pie.

El argumento en contra era el espacio vertical, y sigue siendo real. Lo que lo compensa es que los
dos paneles tienen *ritmos distintos*: el de arriba cambia con cada pestaña de acción, el de abajo
es del repo y no se mueve. Verlos juntos hace visible la relación que importa — "este paso necesita
esta clave, y la clave está ahí mismo" — sin cambiar de vista ni perder de vista lo que ibas a
correr. Las mitigaciones concretas:

- Los dos divisores son arrastrables y colapsables: el panel de `.env` se puede dejar en cero
  mientras trabajas y recuperarlo cuando lo necesites.
- El aviso de faltantes del panel de arriba tiene un botón **Configurar** que, además de expandir el
  panel de abajo si estaba colapsado, **resalta en ámbar solo las claves que esa acción reclama** y
  pone el foco en la primera. No hay que buscar entre veinte campos cuál era.
- No es un editor de texto: es el formulario generado del esquema `setting(...)` de `PLAN.md` §9,
  agrupado por categoría, con los secretos enmascarados y un ojo para revelarlos.

**Lo que el panel hace además del alta manual:** si el repo todavía no tiene `.consola/config.env`
pero sí el `scripts/.env` viejo, ofrece importarlo — trae solo las claves que sobreviven al esquema,
las muestra para revisar, y **no escribe hasta que le des Guardar** (el mismo patrón de simulacro que
`PLAN.md` §7 exige para lo destructivo). Al guardar, `.consola/` se agrega al `.gitignore` del repo
si no estaba.

Queda pendiente decidir qué hace la cuarta pestaña del pie (`Configuración`), que ahora se queda sin
su contenido previsto.

## 7. Estado de implementación

| Archivo | Estado |
|---|---|
| `core/registry.py` | ✅ `AxisDef.select`, `Step`, `Capability.steps`/`hidden`, `resolve_steps()` |
| `core/catalog.py` | ✅ ejes marcados `many`; `copy_to_vps` → paso; atómicas ocultas del rail |
| `core/settings.py` | ✅ esquema de las 21 claves de `PLAN.md` §9, con `required_by` |
| `core/envfile.py` | ✅ leer/escribir `.consola/config.env`, importar `scripts/.env`, `.gitignore` |
| `ui/params_panel.py` | ✅ variantes, pasos, opciones, campos de texto (`expand='field'`), aviso de faltantes, resumen, Ejecutar |
| `ui/env_panel.py` | ✅ formulario agrupado, secretos enmascarados, importar, guardar |
| `ui/widgets/segmented.py` | ✅ control segmentado para ejes `select='one'` |
| `ui/tab_panel.py` | ✅ splitters, panel por pestaña; ejecuta de verdad las capacidades con adaptador (`ui/task_adapters.py`), simula el resto |
| `ui/rail.py` | ✅ un botón por capacidad (48 implementadas hoy) |
| `ui/params_store.py` | ✅ persistir la selección por repo y por botón (`QSettings`); `scope='machine'` guarda una sola vez para todos los repos — ver `docs/parametros-persistentes.md` |
| ejecución real | ⏳ conectada capacidad por capacidad vía `ui/task_runner.py` + `ADAPTERS`; ver `docs/catalogo-funciones.md §7` |

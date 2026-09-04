# Emuladores — tres actividades, dos catálogos

Cómo quedó organizado el grupo **Emulators** y por qué. Continúa
[atomicas.md](atomicas.md) (§1, el criterio de corte) y [PLAN.md §2](PLAN.md) (los tres niveles de
función).

---

## 1. El punto de partida: qué se rompió

El grupo venía de `android_emulator.py`, un `run()` que hacía cuatro cosas en fila —descargar la
system image, crear el AVD, parchear su `config.ini`, arrancar— con tres wrappers
(`run_emulator_1/2/3.py`) que solo cambiaban una constante: `pixel_4`, `pixel_8`, `resizable`.

La primera reimplementación siguió esa forma: cuatro atómicas y una compuesta `start_emulator` con
las tres primeras como casillas, y un eje `preset` con esas mismas tres constantes. Funcionaba como
traducción del script, pero arrastraba su límite: **el catálogo de dispositivos de Android tiene 88
entradas y el de system images, 317** — y ese modelo dejaba ver tres.

Con los catálogos reales a la vista, la compuesta deja de tener sentido:

> Un paso deja de caber en una casilla cuando gana opciones propias.

Instalar una máquina virtual se hace una vez cada varios meses y hay que elegir entre 317. Crear un
AVD se hace una vez por modelo y hay que elegir entre 88 dispositivos. Arrancar se hace veinte veces
por día y solo hay que elegir entre los AVD que ya existen. Encadenarlos obligaría a contestar tres
catálogos cada vez que se quiere lo tercero.

Por eso `start_emulator` desaparece y quedan **tres actividades separadas**, más una de limpieza.

---

## 2. Los botones

| Botón | Nivel | kind | Ejes |
|---|---|---|---|
| **Instalar máquina** (`install_system_image`) | A | once · machine | `image` — catálogo completo de system images |
| **Crear AVD** (`create_avd`) | A | once · machine | `device` — catálogo de dispositivos · `image` — solo las instaladas · `name` — campo opcional |
| **Emulador** (`launch_emulator`) | A | live · machine | `avd` — los ya creados · `boot` — normal \| borrar datos |
| **Liberar disco** (`purge_emulators`) | A | destructive · machine | `avds` · `images` (casillas) · `dry_run` |

Las cuatro son **`scope='machine'`**: un AVD no es de un repositorio, sirve para cualquiera. Igual
que los instaladores de SDK, sus parámetros se guardan una sola vez para toda la máquina, en
`QSettings` y no en el `.consola/params.json` de ningún repo (`ui/params_store.py`): no dependen
del proyecto abierto.

Ninguna es compuesta. El grupo entero es de nivel 1 sobre la plomería de `core/android.py`, que es
donde vive el trabajo real — cada atómica son entre 5 y 20 líneas.

### Lo que no es botón

- **`await_emulator`** — "esperá el boot" no se pide suelto. Es una función que usa `run_mobile`
  antes de instalar el APK, porque `flutter run` contra un dispositivo que todavía no acepta
  comandos falla sin explicar por qué.
- **`stop_emulator`** — ver §5.
- **`delete_avd` / `delete_system_image`** — borrar uno suelto es marcar una casilla en Liberar
  disco, no otro botón. Dos capacidades menos por aplicar ejes en vez de multiplicar botones, el
  mismo movimiento que hizo `serve_vite_app` con `run_panel`/`run_backoffice`/`run_landing`.

---

## 3. Los dos catálogos

Salen de las propias herramientas del SDK, no de una lista escrita a mano:

| Catálogo | Comando | Tamaño real | Se ve como |
|---|---|---|---|
| Dispositivos | `avdmanager list device` | 88 entradas | `Pixel 4  \|  Google` |
| Máquinas virtuales | `sdkmanager --list` | 317 entradas | `Android 36  \|  Google APIs + Play Store  \|  x86_64` |

**Orden.** Alfabético, el catálogo abre en "Android TV · arm64", que no quiere casi nadie. El orden
real es API nueva primero, después variante de teléfono antes que TV/reloj/auto, y dentro de eso la
arquitectura de la máquina antes que la emulada (`Image.order`).

**Caché.** Las dos consultas tardan unos 6 segundos cada una y el catálogo cambia cuando se
actualiza el SDK, no durante una sesión de trabajo: se guardan en
`%LOCALAPPDATA%\Consola\cache` por un mes (`core/cache.py`). La segunda lectura tarda 9 ms. El
botón **↻ Catálogo** del pie del panel es el único modo de enterarse de una API nueva sin reiniciar.

Lo que **no** se cachea igual: las imágenes instaladas y los AVD creados duran un minuto (cambian
cuando alguien instala o borra, y el panel los relee solo al terminar cualquier tarea del grupo), y
los emuladores vivos no se cachean nunca — eso es estado, no catálogo, y una respuesta vieja ahí
ofrecería apagar algo que ya no existe.

**Nada de esto corre en el hilo de la interfaz.** El panel se dibuja con las listas vacías
("leyendo el catálogo del SDK…", con Ejecutar deshabilitado) y `MachineAxesLoader` las completa
desde un hilo aparte.

---

## 4. Una cuarta forma en el panel: `expand='pick'`

El panel tenía tres formas y las tres asumen listas cortas: `checks` (casillas), `scope`
(segmentado) y `field` (texto libre). Un catálogo de 317 entradas no entra en ninguna —pero tampoco
es texto libre, porque los valores válidos son exactamente esos.

`expand='pick'` es una lista cerrada, larga, con búsqueda: se escribe para filtrar y se elige. El
valor que se guarda es el id (`system-images;android-36;google_apis;x86_64`) y lo que se lee es su
etiqueta, vía `AxisDef.labels`.

Y una fuente nueva de valores, hermana de `discover`: **`source`**. `discover` llena un eje mirando
el repo abierto (`core/targets.py`, PLAN.md §2.4); `source` lo llena preguntándole al SDK
(`core/catalog.py::machine_values`). Misma mecánica, otra fuente — el dispositivo no está en el
repo, está en la máquina.

---

## 5. Apagar es cerrar la pestaña

No hay botón "Apagar emulador" en el rail, y es a propósito:

- **El caso normal.** Si el emulador lo arrancó Consola, la pestaña es su dueña: cerrarla lo apaga.
  Pero no matándole el proceso — `TaskContext.on_cancel()` registra un apagado limpio que le pide
  `adb emu kill`, y así el AVD guarda su estado en vez de quedar a medio escribir. `kill_tree` sigue
  detrás, y casi siempre encuentra el proceso ya terminado.
- **Los huérfanos.** Un emulador de una sesión anterior de Consola, o arrancado desde Android
  Studio, está vivo y no tiene pestaña. Para esos, el panel de **Emulador** lleva arriba una
  cabecera **Corriendo ahora** con una fila por emulador y su ✕ — que es el lugar donde ya estás
  mirando para decidir si hace falta lanzar otro. El ✕ corre la capacidad oculta `stop_emulator`
  como cualquier otra tarea, con su log en la consola de la pestaña.

Es lo que declara `Capability.live_state`: un inventario que el panel muestra como estado, no como
eje. No se elige, se mira y se apaga.

---

## 6. Varios emuladores a la vez

`launch_emulator` puede lanzar otro con uno ya corriendo. Tres cosas lo hacen posible:

1. **El puerto se elige antes de arrancar** (`android.free_port` → `-port 5556`), así el serial
   (`emulator-5556`) se conoce desde el principio. Sin eso no hay forma de saber cuál de los
   emuladores vivos es el de esta pestaña —y sin serial no hay ni apagado limpio ni handoff a la
   app móvil.
2. **Una pestaña ocupada no se reusa.** `TabPanel.open_tab` abre `Emulador 2` en vez de esperar a
   que se cierre la primera, para las capacidades `kind='live'`.
3. **El mismo AVD dos veces va en `-read-only`.** El emulador toma un lock sobre la carpeta del AVD
   y el segundo arranque muere con "another emulator instance is running". Si el AVD elegido ya
   aparece corriendo, el flag se agrega solo y se dice en la consola: la segunda copia no escribe
   cambios en el disco del AVD, que es justo lo que se quiere al abrir dos para probar algo entre
   ellos.

El serial del último emulador arrancado se publica en `core/session.py` bajo el ámbito `@machine`, y
`run_mobile` lo prefiere antes que "el primero que conteste" — con dos emuladores vivos, el primero
es una lotería. Es el mismo patrón de `SERVER_PORT` (PLAN.md §7, caso 4), pero de la máquina y no de
un repo: el emulador no es de ningún proyecto en particular.

---

## 7. Lo que cambió en el resto del código

| Archivo | Qué |
|---|---|
| `core/cache.py` | **Nuevo.** Caché en disco para catálogos caros, con TTL e invalidación. |
| `core/android.py` | `Preset`/`PRESETS` → `Device`, `Image`, `AvdSpec` + los dos catálogos, `running()`, `free_port()`, `stop_quiet()`; `start()` toma `port`, `read_only` y `wipe`. |
| `core/context.py` | `on_cancel()` — apagado limpio antes de matar el proceso. |
| `core/catalog.py` | `machine_values()`, `for_machine()`, `forget_machine_cache()` + el grupo Emulators. |
| `core/registry.py` | `AxisDef.source`, `AxisDef.labels`, `expand='pick'`, `Capability.live_state`. |
| `ui/params_panel.py` | Widget `pick` con búsqueda, `MachineAxesLoader`, cabecera *Corriendo ahora*, botón ↻. |
| `ui/tab_panel.py` | Cerrar la pestaña detiene su tarea; segunda pestaña para lo que corre en vivo; relectura de catálogos al terminar una tarea de máquina. |
| `ui/task_runner.py` | `cancel()` corre los ganchos en un hilo: apagar un emulador no congela la ventana. |
| `core/tasks/launchers.py` | `run_mobile` prefiere el emulador que arrancó esta sesión. |

**Un arreglo que vino de arriba:** hasta ahora cerrar una pestaña dejaba su tarea corriendo y
destruía la consola a la que esa tarea seguía escribiendo. Ahora se desconectan las señales y se
cancela. No era un problema del emulador, pero era el emulador el que lo hacía inevitable.

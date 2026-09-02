# Launchers — lo que entregan es una URL, no un log

Cómo quedó organizado el grupo **Launchers** y por qué. Continúa
[atomicas.md](atomicas.md) (§0, qué **no** es una atómica) y [emuladores.md](emuladores.md)
(un paso deja de caber en una casilla cuando gana su propio catálogo), y agrega al modelo de
[PLAN.md §2](PLAN.md) una forma de compuesta que ahí no existía: la **concurrente**.

Estado: los cinco botones del grupo están conectados (adaptador real en
[`ui/task_adapters.py`](../ui/task_adapters.py)), incluida la compuesta.

---

## 1. Qué se rompió al mirar el grupo con la lupa de `atomicas.md`

Los cuatro launchers ya tenían cuerpo en `core/tasks/launchers.py` desde la primera pasada, pero
ninguno tenía adaptador: seguían simulando. Al ir a conectarlos aparecieron tres cosas.

**a) Tres funciones estaban etiquetadas como atómicas y no lo son.** `resolve_server_port`,
`backend_url` y `resolve_tls` figuraban en la lista de atómicas del módulo, y el docstring de la
primera decía *«botón propio poco frecuente, pero atómica muy usada»*. Por el criterio corregido
del [§0 de atomicas.md](atomicas.md), ninguna lo es: **nadie pide «elige un puerto y nada más»**.
Son el `_download` / `_extract` de este grupo — plomería dentro de una actividad, no la actividad.

Lo que sí es una atómica es `serve_backend`, y es el mismo caso que `install_android_tools`:

> **una** actividad reconocible del dominio, hecha por dentro de **cinco** funciones
> (`resolve_server_port` + `resolve_tls` + `venv_python` + `db.connect` + `ctx.run`).

La pregunta de corte nunca fue «¿esto es una función aparte?». Es «¿tiene sentido re-ejecutar
**esto** solo?», aplicada a la granularidad de la actividad y no a la de la función.

**b) Un eje `many` contra una función que toma uno solo.** El catálogo declaraba las SPA como
casillas múltiples y `serve_spa` resolvía una sola vía `targets.pick`. Marcar `panel` +
`backoffice` no tenía semántica definida. Ver §2.1.

**c) El resultado de un launcher no es su log.** Todo lo conectado hasta ahora es `once` /
`destructive` —donde el log *es* el entregable— o `live` de máquina, donde la ventana la dibuja
Android. Un launcher entrega un **endpoint**: una URL. La consola es el subproducto. De ahí sale
todo lo demás de este documento.

---

## 2. Las cinco decisiones

### 2.1 El eje `many` se resuelve por `kind`, no por capacidad

Una regla, dos comportamientos, ninguna excepción escrita a mano:

| `kind` | Eje `select='many'` con N marcados | Por qué |
|---|---|---|
| `once` — `build_vite` | **bucle en una pestaña**: N builds en fila, un solo log | son tareas que terminan; verlas en orden es lo correcto |
| `live` — `serve_vite` | **N pestañas**, una por valor | cada dev server tiene su puerto, su consola, su navegador y su ✕ |

Se declara con `Capability.fanout`, que nombra el eje que se reparte:

```python
Capability(id='serve_vite', kind='live', view='web', fanout='target', ...)
```

El primer valor se queda en la pestaña desde la que se apretó Ejecutar y **solo cambia de nombre**
(`Servir SPA Vite` → `Servir SPA Vite panel`), así el caso normal —un repo con una sola SPA— se ve
exactamente igual que antes, sin una pestaña de más. El resto abre pestaña propia.

`serve_spa` no cambió: sigue tomando **un** target. El reparto es de la interfaz, que es donde
existen las pestañas.

### 2.2 Un launcher publica un endpoint: `ctx.serve()`

Es la pieza nueva del `TaskContext`, y paga tres cosas de una sola vez:

```python
puerto = ports.resolve_port(preferred_port, label=f'puerto de {spa.name}')
ctx.serve(f'http://localhost:{puerto}', key=f'spa:{spa.name}', label=spa.name)
ctx.run([...])                     # bloquea hasta que el proceso muera
```

1. **La barra de endpoint** de la pestaña: LED, `arrancando` → `listo` → `caído`, la URL, *Copiar*,
   *Abrir ↗*.
2. **La vista de navegador** (§2.3), que así sabe adónde ir.
3. **La señal de «listo»** que esperan los launchers que dependen de este (§2.5).

Se llama **antes** de arrancar el proceso, y puede: el puerto lo elige Consola con
`ports.resolve_port`, así que la URL se conoce sin olfatear la salida de vite ni la de uvicorn.

**Puerto elegido ≠ servidor contestando.** Entre las dos cosas hay un `npm run dev` que tarda dos
segundos o un uvicorn que tarda diez, y navegar antes de tiempo muestra un error que no es tal. Por
eso `ctx.serve()` levanta un hilo que sondea el puerto (`ports.wait_until_serving`) y recién
entonces marca `listo`. Aparte, porque quien llamó sigue derecho a `ctx.run()`, que no vuelve hasta
que el proceso muere: con la espera en línea, la URL nunca pasaría de «arrancando».

Detalles que importan:

- **La URL que se anuncia no es la de escucha.** El backend escucha en `0.0.0.0`; se entra por
  `localhost`. Un navegador apuntado a `0.0.0.0` no llega a ningún lado.
- **`localhost` se sondea como `127.0.0.1`** (`ports.split_host_port`): resolver `localhost` puede
  dar `::1` primero, y un servidor que solo escucha IPv4 se leería como caído.
- **Los endpoints se sueltan al terminar la corrida**, en `TaskRunner._done` y no en el `finally` de
  cada launcher: quien publicó la URL fue el contexto, y una URL que ya no sirve nada no debe seguir
  ofrecida a la SPA que arranque después.

### 2.3 El navegador es una segunda vista de la misma pestaña, no un botón del rail

Es el mismo movimiento que mató al botón «Apagar emulador» ([emuladores.md §5](emuladores.md)):
*lo que corre se ve donde se lanzó*.

Un botón «Abrir navegador» en el rail sería una capacidad que no ejecuta nada, no registra nada y no
tiene parámetros — rompe la definición de botón. En cambio, el contenido de una pestaña dejó de ser
una consola suelta y pasó a ser una caja con dos vistas (`ui/tab_view.py`):

```
┌─ Servir SPA Vite panel ─────── ● panel · listo ─ http://localhost:5173 ─ [Copiar] [Abrir ↗] [Navegador] ─┐
│                                                                                                          │
│   (la consola, o la página — el conmutador cambia cuál se ve)                                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Lo declara `Capability.view='web'`. **Esto no es solo para los launchers**: es exactamente lo que
[PLAN.md §0](PLAN.md) pide para la pestaña de Base de datos (*«comparte el mismo panel y el mismo
pie de pestañas secundarias»*) y lo que su `kind='view'` anticipa sin implementar. Por eso el
conmutador se llama «vista» y no «navegador», y por eso construirlo acá lo paga dos veces.

Tres decisiones dentro de la vista:

- **Perezosa.** El `QWebEngineView` se crea la primera vez que hace falta. Abrir tres SPA no debe
  arrancar tres motores de navegador hasta que alguien mire alguna.
- **Al llegar a `listo`, la pestaña muestra la página.** Lo que se pidió fue levantar algo que se
  mira en un navegador; mostrarlo es terminar el trabajo, no una sorpresa. La consola queda a un
  clic — y si el proceso se cae, la pestaña vuelve sola a la consola, que es donde está el motivo.
- **Sin QtWebEngine se degrada, no falla.** El import va protegido: si falta, la vista es un cartel
  con un botón que abre el navegador del sistema.

> **Empaquetado.** QtWebEngine viaja en `PySide6-Addons` (el metapaquete `PySide6` lo trae; una
> instalación `PySide6-Essentials` no) y suma ~150 MB al `.exe` de la etapa 7 de PLAN.md.

### 2.4 El grupo, por lo que cada launcher te entrega

Las secciones agrupan por eso, que es lo mismo que decide si la pestaña tiene segunda vista:

| Sección | Botón | `kind` | Ejes | Segunda vista |
|---|---|---|---|---|
| Servidor | **Backend** | live | `scope` local \| remoto | Navegador |
| Web | **Servir SPA Vite** | live | `target` descubierto, `many` → N pestañas | **Navegador** |
| Dispositivo | **App móvil** | live | `app` descubierto | — (la dibuja el emulador) |
| Escritorio | **Terminal** | live | `app` descubierto · `auto_login` | — |
| Todo junto | **Entorno de desarrollo** 🧩 | live | los tres launchers como pasos | — (cada paso tiene la suya) |

Dos correcciones que caen del mismo criterio:

- **La terminal dejó de tener su carpeta fija en el código.** `open_terminal(directory='terminal')`
  era justo lo que [PLAN.md §2.4](PLAN.md) dice que no hay que hacer. `core/targets.py` ganó el tipo
  `python-app` (carpeta con `src/main.py`), así que ahora es un eje descubierto como el de las SPA.
- **`ssh_login` se queda en VPS · ops.** Es `interactive` y abre terminal externa: no comparte nada
  con este grupo salvo la palabra «abrir».

### 2.5 La compuesta del grupo es **concurrente**, no secuencial

[PLAN.md §0](PLAN.md) menciona *«levantar backend + terminal + frontend»* como compuesta y nunca
llegó al catálogo. Al escribirla aparece que no es una compuesta como las que ya existen:

| | Secuencial (`update_remote`, `rebuild_db`) | Concurrente (**Entorno de desarrollo**) |
|---|---|---|
| Pasos | uno tras otro, cada uno termina | todos vivos a la vez |
| Consola | una, plana, con `ctx.step()` por paso | una por proceso |
| Pestañas | una | N |
| Falla un paso | corta la receta | los demás siguen |
| Orden | fijo, es la receta | solo por **dependencia** |

Se declara con `Capability.concurrent=True` y **no tiene `func` ni adaptador**: su cuerpo es el
despachador de `ui/tab_panel.py::_run_concurrent`, que abre una pestaña por paso y corre cada
capacidad con los parámetros que ya tiene guardadas para ese repo — o sea, reusa `quick_run`, lo
mismo que hace el botón de correr del rail. Es la única capacidad del catálogo cuyo cuerpo vive en
la interfaz, y es deliberado: **«N pestañas» no significa nada dentro de `core/`**.

**La dependencia no se resuelve con un `sleep` de la interfaz.** La SPA y la terminal necesitan la
URL del backend, y hasta ahora eso funcionaba *por casualidad de orden de ejecución* — el mismo
defecto que [PLAN.md §7 caso 4](PLAN.md) le criticaba al `.env`, solo que en memoria en vez de en
disco. Ahora esperan el endpoint desde adentro:

```python
api = backend_url(ctx, wait=BACKEND_WAIT, required=False)   # serve_spa
entorno = {'SERVER_URL': backend_url(ctx, wait=BACKEND_WAIT)}  # open_terminal
```

`backend_url` contesta al instante si el backend ya está arriba, espera si está arrancando en otra
pestaña, y para la SPA devuelve vacío si no hay backend en absoluto — que no es un error, es
arrancar con la configuración propia de la SPA. Para la terminal sí lo es. La consecuencia buena:
esto funciona igual lanzando los tres botones a mano, en cualquier orden, sin pasar por la
compuesta.

---

## 3. Un bug que apareció de paso: la clave que bloqueaba sin usarse

`API_URL` estaba declarada `required_by=('backend',)`, y **`serve_backend` nunca la lee** — quien la
lee es `compile_apk`, que ya la pide por paso, y `run_mobile`, que cae en la URL del backend de esta
sesión si está vacía. El botón Backend quedaba en ámbar por una clave que jamás iba a mirar, y con
él la compuesta entera, que hereda los requisitos de sus pasos.

Es la misma familia del arreglo del [§4.4 de atomicas.md](atomicas.md) («un default con el que la
acción igual puede correr ya no bloquea el botón»), pero por otra causa: no un default mal leído,
sino un requisito que nunca existió. `Setting` ganó `used_by` para separar las dos cosas:

- `required_by` — sin esto la acción no corre: su botón queda en ámbar.
- `used_by` — la acción puede llegar a mirarla; aparece en el panel de configuración filtrado de
  esa acción y **no bloquea nada**.

Que `API_URL` no bloquee al Backend no quiere decir que no sea el lugar donde uno la busca teniendo
esa pestaña abierta: por eso `relevant_keys_for()` (el filtro del panel) suma las dos, y
`required_keys_for()` (la validación previa) sigue mirando solo la primera.

---

## 4. Lo que cambió en el resto del código

| Archivo | Qué |
|---|---|
| `core/ports.py` | `is_serving()`, `wait_until_serving()`, `split_host_port()` |
| `core/session.py` | `Endpoint` + registro por proyecto: `publish_endpoint`, `mark_endpoint`, `wait_for_endpoint`, `forget_endpoint` |
| `core/context.py` | `ctx.serve()`, `ctx.endpoint()`, `ctx.release_endpoints()`, `ServeSink` |
| `core/registry.py` | `Capability.view`, `.fanout`, `.concurrent`, `.has_web_view` |
| `core/targets.py` | tipo `python-app` |
| `core/settings.py` | `Setting.used_by`, `relevant_keys_for()`; `API_URL` deja de bloquear (§3) |
| `core/catalog.py` | grupo Launchers reorganizado, `DEV_ENV_STEPS`, la capacidad `dev_env` |
| `core/tasks/launchers.py` | `ctx.serve()` en los tres launchers con endpoint; `backend_url(wait=, required=)`; terminal con target descubierto |
| **`ui/browser_view.py`** | **nuevo** — navegador embebido con import protegido y degradación |
| **`ui/tab_view.py`** | **nuevo** — barra de endpoint + conmutador consola/vista |
| `ui/task_runner.py` | señal `serve_requested`; `_done()` suelta los endpoints |
| `ui/tab_panel.py` | pestaña = `TabView`; `_open()`, `_retitle()`, `_run_fanout()`, `_run_concurrent()`; `current_console()` por pestaña y no por widget visible |
| `ui/task_adapters.py` | adaptadores de `backend`, `serve_vite`, `run_mobile`, `terminal` |

**Un arreglo que vino de arriba:** `current_console()` resolvía la consola por el widget visible del
stack (`isinstance(w, ConsoleView)`). Con el navegador arriba habría devuelto `None` y el rail
habría quedado sin dónde escribir sus avisos. Ahora se resuelve por la pestaña activa, que es de
quien la consola realmente depende.

---

## 5. Verificado

Con un repo sintético (dos SPA Vite, una app móvil, una `python-app`, un `server/`) y los launchers
reemplazados por funciones que sirven de verdad en un socket local:

- el eje `target` descubre las dos SPA y **abre una pestaña por cada una**, con los títulos
  correctos, dos tareas vivas en paralelo;
- las dos publican su endpoint, pasan a `listo` y la pestaña muestra la página (`QWebEngineView`
  real, disponible en el PySide6 6.8.2.1 instalado);
- `dev_env` despacha **backend primero** y la SPA y la terminal ven su URL esperando el endpoint,
  no un `sleep`;
- la terminal no publica endpoint y su barra queda oculta;
- cerrar una pestaña cancela su tarea y **suelta su endpoint**: no quedan URLs de procesos muertos;
- los cuatro adaptadores producen los kwargs correctos sin bloqueos en un repo sin `.env`.

**Sin verificar contra procesos reales:** `npm run dev` y `uvicorn` de verdad. Los tiempos de
arranque, el `--port` que Vite respeta o no, y el comportamiento del navegador embebido contra el
HMR de Vite son lo único que estas pruebas no tocan.

---

## 6. Pendiente

1. **Un «Navegador» suelto** (`kind='view'`) para URLs que no arrancó ningún launcher: el sitio del
   VPS, `API_URL`. Útil, pero es una app dentro de la app y no urge.
2. **`BACKEND_WAIT = 90 s`** es un número puesto a ojo para un uvicorn con `--reload` y base remota
   por túnel. Falta uso real para saber si sobra o falta.
3. **La barra de estado** (`WorkspaceStatusBar.add_service`) ya tiene lugar para servicios de fondo
   y hoy los endpoints no llegan ahí. Si un launcher pasa a sobrevivir a su pestaña, ese es su sitio.
4. **`API_URL` en `run_mobile`**: hoy tiene prioridad sobre el backend de la sesión. Con un backend
   local corriendo y `API_URL` apuntando al VPS, la app del emulador va al VPS. Es lo que hacía el
   script original, pero conviene confirmar que sigue siendo lo que se quiere.

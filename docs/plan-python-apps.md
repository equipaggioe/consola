# Plan — apps Python al estilo Vite

Plan para continuar en otro chat. Objetivo: que las aplicaciones **Python** se descubran en el
repo y se manejen con un eje de parámetros, igual que las SPA de Vite, en vez de tener un botón
por aplicación y rutas escritas a mano.

Cubre los **dos casos**, que hoy están rotos de formas distintas: **correrlas** (Launchers) y
**compilar su binario** (Builders).

---

## 1. La asimetría que hay que cerrar

Vite ya tiene las dos mitades y son simétricas. Python no tiene ninguna de las dos.

| | Vite (el modelo a copiar) | Python (hoy) |
|---|---|---|
| **Correr** | `serve_vite` · `kind='live'` · eje `target` descubierto `select='many'` · `fanout='target'` | `backend` (sin eje: lee `SERVER_DIR` del `.env`) **+** `terminal` (eje `one`) — dos botones distintos |
| **Compilar** | `build_vite` · `kind='once'` · eje `target` descubierto `select='many'` · sin fanout (bucle) | `build_binary` — campo de **texto libre** `entrypoint` + adivinanza en `_ENTRYPOINTS` |

Síntomas concretos en el código actual:

- `core/targets.py` define `FASTAPI` como tipo, pero **no lo usa nadie**: `serve_backend` ignora
  el descubrimiento y resuelve por `ctx.config.get('SERVER_DIR', 'server')`.
- `core/tasks/builders.py:226` lanza *«Hay más de una app Python: escribe el punto de entrada»*.
  Ese error es exactamente el problema: con un eje descubierto se marcarían casillas.
- `PYTHON_APP` se detecta solo por `src/main.py`, el marcador más débil de todos
  (`core/targets.py:56`).

---

## 2. Por qué Python no sale gratis como Vite

Una app Vite es uniforme: `package.json` + `vite.config.*` → `npm run dev` → sirve HTTP en un
puerto. Una regla de detección, un comando, una forma de salida. Por eso un botón con un eje
descubierto alcanza — y por eso `vite.config.*` **es** la declaración de la app: npm ya la
estandarizó.

En Python varían tres cosas **independientes** que no se deducen de un solo archivo:

1. **De dónde sale el intérprete** — `.venv` propio, uno en la raíz del repo, poetry, uv, sistema.
2. **Cómo arranca** — `python -m uvicorn app.main:app`, `python main.py`, `flet run`, un
   `console_script`.
3. **Qué entrega** — un endpoint HTTP (`ctx.serve()`, vista de navegador), una ventana de
   escritorio (sin URL), un CLI que termina.

**Conclusión de diseño:** no se llega a "un botón, N casillas" solo detectando. Hay que hacer que
la app **se declare**, y descubrir la declaración.

---

## 3. Fundación común: `core/targets.py`

Las dos pistas dependen de esto. Hacerlo primero.

### 3.1 `Target` pasa de tipo a receta

Hoy es `(name, kind, path)` y quien llama hace `switch` sobre `kind`. Agregar lo que de verdad
varía:

```python
@dataclass(frozen=True)
class PythonApp:
    name: str
    path: Path
    venv: Path          # dónde está el intérprete
    argv: list[str]     # cómo arranca
    kind: str           # 'server' | 'desktop' | 'cli'
    port_env: str = ''  # cómo recibe el puerto, si sirve
    reload: str = ''    # '' | 'uvicorn' | 'watch'  (ver §4.2)
    entrypoint: Path | None = None   # para PyInstaller (ver §5)
```

### 3.2 Tres niveles de precedencia

1. **Declarado** — tabla `[tool.consola]` en el `pyproject.toml` de la propia app. Es el que
   escala: la app dice qué es, en su repo, versionado con ella, sin nada que mantener sincronizado
   del lado de Consola.

   ```toml
   [tool.consola]
   kind = "server"
   start = "uvicorn app.main:app"
   port-env = "PORT"
   reload = "uvicorn"
   entrypoint = "app/main.py"
   ```

2. **Inferido** — las heurísticas actuales de `_detect` como respaldo para lo que no declaró nada:
   `app/main.py` + `alembic.ini` → `server`; `pyproject.toml` con `flet` → `desktop`;
   `src/main.py` → `desktop`.

3. **Sobrescrito** — el campo de texto libre que `build_binary` ya tiene, degradado a escape hatch
   para el caso raro.

### 3.3 Decisión pendiente: el repo que es su propia app

`core/tasks/builders.py:212` documenta un caso real: un repo que se empaqueta **desde su raíz**
(la propia Consola) no tiene ningún `python-app` que descubrir, y un eje descubierto vacío deja el
botón en ámbar. Dos salidas, hay que elegir una:

- **(a)** `_detect` reconoce la raíz del repo como app cuando tiene manifiesto + entrypoint. Más
  limpio, hace que el eje nunca esté vacío para un repo Python.
- **(b)** Conservar el campo `entrypoint` como eje secundario de override. Más conservador, deja
  dos mecanismos conviviendo.

Recomendación: **(a)**, con (b) como red.

---

## 4. Pista A — correr las apps (`Launchers`)

### 4.1 Un solo botón, como `serve_vite`

`backend` + `terminal` se funden en **`run_python`**:

```python
Capability(
    id='run_python', name='App Python', group='Launchers', section='Servidor',
    kind='live', icon='🐍', view='web', fanout='app',
    axes=[AxisDef('app', [], 'checks', select='many', label='Apps',
                  discover=(targets.PYTHON_APP,)),
          AxisDef('scope', ['local', 'remoto'], 'scope')],  # base, solo para kind='server'
)
```

Por qué encaja con las reglas que el proyecto ya tiene:

- `select='many'` + `kind='live'` → **una pestaña por app**, por la regla de
  [launchers.md §2.1](launchers.md). Es exactamente lo que se quiere para levantar backend y
  terminal a la vez, y hoy lo hace `dev_env` enumerando pasos a mano.
- `view='web'` **no molesta** a las apps de escritorio: la barra de endpoint solo aparece cuando
  la tarea llama a `ctx.serve()` (`ui/tab_view.py:113`). No hace falta volver `has_web_view`
  dinámico. *(Verificado.)*
- `dev_env` se simplifica a `[run_python(...), serve_vite(...)]` en vez de tres pasos nombrados.

### 4.2 La arruga honesta: la recarga

`open_terminal` implementa su propio bucle de recarga (`_snapshot` + relanzar), mientras que el
backend la obtiene de `uvicorn --reload`. "Correr" solo es una acción uniforme si la receta carga
también la estrategia de recarga — de ahí el campo `reload` en §3.1. Si esto se complica más de la
cuenta, es la señal de que `run_python` debe partirse en dos otra vez; conviene decidirlo con el
código a la vista, no ahora.

### 4.3 Atómicas de esta pista

Aplicando el criterio de [atomicas.md §1](atomicas.md) (*¿tiene sentido re-ejecutar esto solo?*):

| Función | ¿Atómica con botón? | Por qué |
|---|---|---|
| `resolve_python_app` | **No** | Plomería, como `resolve_server_port`. Nadie pide "solo resolver la app". |
| `install_python_deps` | **Sí** | Crear el venv e instalar `requirements.txt`/`pyproject`. Se re-ejecuta sola cada vez que cambian las dependencias. Hoy **falta**: solo existe `install_remote_deps` (VPS). Es el hermano local de `install_node_modules`, que sí existe del lado Vite. |
| `run_python` | **Sí** | El launcher. |

`install_python_deps` es un hallazgo del plan, no un capricho: la simetría con Vite lo pedía y no
estaba.

---

## 5. Pista B — compilar el binario (`Builders`)

### 5.1 Lo que cambia es *solo el eje*

Los pasos actuales de `build_binary` ya son correctos por el criterio de atómicas y **no se
tocan**:

```
bump · build · checksum · upload
```

Lo único que cambia es cómo se elige qué compilar:

```python
# antes
AxisDef('entrypoint', [''], 'field', label='Punto de entrada',
        placeholder='se deduce: src/main.py de la app Python del repo')

# después — igual que build_vite
AxisDef('app', [], 'checks', select='many', label='Apps',
        discover=(targets.PYTHON_APP,))
```

### 5.2 Lo que eso desbloquea

- `select='many'` + `kind='once'` → **bucle en una sola consola**, N binarios en fila, por la misma
  regla de [launchers.md §2.1](launchers.md) que gobierna `build_vite`. Hoy es imposible: hay que
  correr el botón una vez por app, escribiendo la ruta cada vez.
- El error *«Hay más de una app Python: escribe el punto de entrada»* desaparece.
- `resolve_entrypoint` se simplifica: el entrypoint sale de `PythonApp.entrypoint` (declarado o
  inferido), no de la lista `_ENTRYPOINTS` ni de un campo escrito.
- `_binary_app()` (que sube desde el entrypoint buscando un manifiesto) se vuelve innecesario:
  `PythonApp.path` **ya es** la carpeta de la app.

### 5.3 Simetría final

Con las dos pistas hechas, la tabla del §1 queda así:

| | Vite | Python |
|---|---|---|
| **Correr** | `serve_vite` · `live` · `many` · `fanout` | `run_python` · `live` · `many` · `fanout` |
| **Compilar** | `build_vite` · `once` · `many` · bucle | `build_binary` · `once` · `many` · bucle |
| **Dependencias** | `install_node_modules` | `install_python_deps` |

---

## 6. Orden de trabajo

1. **Fundación** (§3) — `PythonApp`, lectura de `[tool.consola]`, `_detect` reforzado, decisión
   §3.3. Sin esto no se puede hacer ninguna de las dos pistas.
2. **Pista B primero** (§5). Es la más barata y la de menor riesgo: cambia un eje, los pasos ya
   están bien, y no toca ningún proceso vivo. Sirve de prueba de que la fundación es correcta.
3. **`install_python_deps`** (§4.3) — atómica nueva, independiente y pequeña.
4. **Pista A** (§4). La más invasiva: funde dos capacidades, toca `dev_env`, y arrastra la
   decisión de recarga del §4.2.
5. **Limpieza** — `SERVER_DIR` deja de ser cómo se ubica el backend local. Puede seguir existiendo
   para las rutas del VPS, que es otra cosa; hay que revisar cada uso.

## 7. Archivos que se tocan

| Archivo | Qué |
|---|---|
| `core/targets.py` | `PythonApp`, `[tool.consola]`, `_detect` reforzado |
| `core/catalog.py` | ejes de `build_binary`; `run_python` reemplaza `backend` + `terminal`; `dev_env` |
| `core/tasks/builders.py` | `resolve_entrypoint`, `_binary_app`, `_ENTRYPOINTS`, `_NOMBRES_GENERICOS` |
| `core/tasks/launchers.py` | `serve_backend` + `open_terminal` → `run_python`; `install_python_deps` |
| `ui/task_adapters.py` | adaptadores de las capacidades nuevas o renombradas |
| `docs/catalogo-funciones.md`, `docs/launchers.md` | catálogo y reglas |

## 8. Verificación

- Un repo con **una sola** app Python se ve igual que hoy (un valor en el eje, sin pestaña de más)
  — el mismo criterio que `serve_vite` ya cumple para un repo con una sola SPA.
- Un repo con backend + terminal levanta las dos con un botón, dos pestañas.
- Un repo que se empaqueta desde su raíz sigue compilando su binario (decisión §3.3).
- `dev_env` sigue levantando todo, con menos declaración.

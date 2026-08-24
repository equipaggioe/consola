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
2. **El rail se achica casi a la mitad.** De ~55 botones a ~30, porque desaparecen las filas
   duplicadas por eje. El rail vuelve a ser una lista navegable de un vistazo.
3. **Los pasos de una acción compuesta se vuelven visibles.** Hoy `build_apk` hace bump + build +
   subida y no hay manera de saberlo mirando la UI, mucho menos de saltarse la subida.

Lo que se pierde: el toque único para *una* variante puntual. Se compensa con dos cosas — el botón
muestra su selección actual como subtítulo (`Build Vite · panel, backoffice`), así que nunca corres a
ciegas, y el menú `⋯` de la fila ofrece "solo panel" para el caso de una vez.

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
| `preset` (AVDs) | `start_emulator` | **many** | casillas |
| `action` (systemd) | `systemd_action` | one | segmentado |
| `bump_mode` | `build_apk`, `build_vite` | one | desplegable |
| `scope` (local/remoto) | `bootstrap_db`, `migrate_db`, … | one | segmentado |
| `dry_run` (simulacro/borrar) | `clean_artifacts`, `sync_common_files` | one | segmentado |
| `follow` (sí/no) | `view_logs` | one | switch |

Regla para los que vengan: **¿tiene sentido pedir dos a la vez?** Sí → `many`. No → `one`.
Los `many` casi siempre son targets descubiertos del repo; los `one` casi siempre son modos de la
herramienta. Es la misma frontera de `capacidades-por-repo.md` §3, vista desde otro ángulo.

---

## 3. Los pasos también son casillas

`composed_of` deja de ser metadato invisible y pasa a ser la sección **Pasos** del panel. Cada paso
declara si se puede desmarcar:

```python
Capability(
    id='build_vite', name='Build Vite',
    steps=[
        Step('bump_version', 'Bump versión', optional=True,  default=True),
        Step('vite_build',   'Build Vite',   optional=False),              # el núcleo
        Step('upload_to_vps','Subir al VPS', optional=True,  default=False,
             requires_env={'VPS_IP','VPS_USER','VPS_KEY_NAME'}),
    ],
)
```

`optional=False` se dibuja marcado y deshabilitado: un `Build Vite` sin build no es una variante, es
un error. Y un paso puede tener sus propios requisitos de config — de ahí sale la advertencia
contextual del §5.

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
│  ◼ Build Vite            obligatorio  │
│  ☑ Subir al VPS                       │
├───────────────────────────────────────┤
│ OPCIONES                              │
│  Destino        ( local │ remoto )    │
├───────────────────────────────────────┤
│ ⚠  Falta VPS_IP para "Subir al VPS"   │
│    → Configurar                       │
├───────────────────────────────────────┤
│  Preset ▾              ▶  Ejecutar    │
└───────────────────────────────────────┘
```

La línea `2 apps × 3 pasos` es la que hace legible el costo de lo que estás por lanzar **antes** de
apretar. Sin ella, marcar tres apps y tres pasos es un compromiso invisible de varios minutos.

**Dónde va:** columna derecha, entre la consola y el borde, con `QSplitter` para redimensionar y un
gesto para colapsarla. Izquierda = *qué puedo correr*, centro = *qué está pasando*, derecha = *con
qué parámetros*. Ancho por defecto ~300px, igual que el rail, para que la ventana quede simétrica.

**No debajo del rail:** compartir la columna izquierda le quita al rail justo lo que necesita —
altura — y deja el panel de parámetros en una franja donde no entra ni una sección.

---

## 5. El gesto: cómo se llena el panel sin perder el toque único

El riesgo obvio de este diseño: si cada acción hay que configurarla antes de correrla, se agrega un
paso a las veinte veces al día que solo querías apretar y ver el log.

Solución en dos gestos sobre la misma fila del rail:

| Gesto | Qué hace |
|---|---|
| Clic en el cuerpo del botón | **Ejecuta ya** con los parámetros actuales, y el panel salta a mostrarlos |
| Clic en el `⚙` de la fila | **Solo enfoca** el panel en esa acción, sin ejecutar |

El panel siempre refleja "la acción en foco". El estado no se pierde: cada combinación se guarda por
**repo + capacidad** en la tabla `presets` de `PLAN.md` §8, así que el segundo toque del día ya sale
con lo que dejaste. Un repo puede tener marcadas `panel`+`backoffice` y otro solo su única app, sin
interferencia.

Primera vez que se abre una acción: marcadas **todas** las variantes descubiertas y los pasos con
`default=True`. Para un repo con una sola app, eso significa que el comportamiento por defecto es
idéntico al de hoy — apretar y correr.

---

## 6. El `.env`: no es un segundo panel

Aquí discrepo con la idea de apilar un editor abajo, y el motivo no es de gusto: **`PLAN.md` §9 ya
decidió que la edición de `.consola/config.env` es la vista de Configuración** — que además ya existe
como cuarta pestaña del pie (`Consola / Bitácora / Historial / Configuración`) y hoy no hace nada. Es
un formulario generado del esquema `setting(...)`, no un editor de texto, y necesita el ancho
completo del área central para ~15 campos agrupados por categoría.

Apilar dos paneles en la columna derecha tendría tres costos concretos:

1. Parte por la mitad el espacio vertical de los dos, y el panel de parámetros ya es el que más
   crece (un repo con cinco apps y cuatro pasos llena esa altura solo).
2. Duplica el lugar donde se edita lo mismo: ¿el `.env` se edita en el panelito o en Configuración?
   Dos caminos hacia el mismo archivo es cómo se corrompe un archivo.
3. Se consulta con frecuencias opuestas: los parámetros, cada ejecución; el `.env`, al dar de alta
   el repo y casi nunca más.

**Lo que sí va en el panel de parámetros** es la tira contextual del mockup: cuando un paso marcado
necesita una clave que falta, se muestra ahí, nombrando *solo* esa clave y con un enlace que abre
Configuración **filtrada a las claves de esa acción** — que es exactamente el engranaje por acción
que §9 ya describe. Resuelve "me falta algo para lo que voy a correr" sin mover el editor de lugar.

---

## 7. Qué se toca

| Archivo | Cambio |
|---|---|
| `core/registry.py` | `AxisDef.select` (`'one'`/`'many'`); nueva dataclass `Step`; `Capability.steps` reemplaza a `composed_of` |
| `core/catalog.py` | marcar `select` en cada eje; `composed_of` → `steps`; eliminar el eje `copy_to_vps` |
| `core/presets.py` | **nuevo** — leer/guardar la selección por `(project, capability)` en SQLite |
| `ui/params_panel.py` | **nuevo** — el panel: secciones, casillas, resumen, tira de faltantes |
| `ui/widgets/action_button.py` | subtítulo con la selección actual; `⚙` para enfocar sin ejecutar |
| `ui/rail.py` | un botón por capacidad (deja de expandir `buttons` por valor de eje) |
| `ui/main_window.py` | `QSplitter` horizontal: rail │ workspace │ panel |

El orden importa: `registry` + `catalog` primero (son datos, no dibujan nada), después el panel, y el
rail al final — porque hasta que el panel no exista, quitarle los botones expandidos al rail deja
variantes inalcanzables.

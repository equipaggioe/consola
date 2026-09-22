# 10 · Catálogo de capacidades

Cómo se declara un botón, de qué está hecho y cómo llega lo elegido a la función que corre. Es el documento que toca cualquier cambio en `core/catalog.py` o `core/registry.py`.

## 1. Declarar y vincular

`main.py` llama primero a `load_catalog()`, que registra las 62 `Capability` con `stub=True`, y después a `bind_all()`, que recorre los nueve módulos de `core/tasks/` y llama a `Registry.bind(id, func)`. Vincular hace dos cosas: le pone `func` y baja `stub`. Lo que nadie vincule sigue siendo un stub y la interfaz lo simula ([ADR-0002](../adr/0002-catalogo-declara-tareas-implementan.md)).

Hoy están vinculadas las 62 menos `dev_env`, que declara `stub=False` a mano porque su cuerpo no es una función: es el despachador de la interfaz ([ADR-0011](../adr/0011-compuesta-concurrente-sin-cuerpo.md)).

## 2. Qué declara una `Capability`

| Campo | Para qué |
|---|---|
| `id` | Clave del registro, de los parámetros guardados y de las reglas del seguro |
| `name`, `icon`, `description` | Lo que se lee: pestaña, menú, tooltip y cabecera. `description` es una línea, en presente |
| `group` | En qué menú de la barra aparece, y bajo qué encabezado en el buscador |
| `cut` | En el menú, una raya justo encima de este botón: abre un tramo. Sin nombre y sin agrupar nada |
| `kind` | `live` \| `once` \| `destructive` \| `interactive` \| `background` |
| `axes` | Los ejes: lo que se elige en cada corrida |
| `steps` | Las casillas de una compuesta. Sin `steps`, la capacidad es un paso obligatorio y no se dibuja la sección |
| `composed_of` | **Documentación**: de qué botones está hecho este botón. No deriva casillas |
| `level` | `'C'` a mano cuando una compuesta no publica sus pasos; si no, se deduce de `steps`/`composed_of` |
| `scope` | `repo` o `machine` ([ADR-0017](../adr/0017-datos-en-el-env-decisiones-en-el-json.md)) |
| `hidden` | Existe como paso o como acción de la interfaz, no como botón |
| `requires_repo` | Sin esa característica del repo, el botón no existe |
| `opens_repo` | Lo que entrega es una carpeta de repo: la ventana la abre como pestaña ([ADR-0035](../adr/0035-clonar-abre-el-repo.md)) |
| `view` | Segunda vista de la pestaña: `web` (navegador) o `db` (explorador) |
| `fanout` | Nombre del eje `many` que se reparte en pestañas en vez de recorrerse en bucle |
| `concurrent` | Compuesta cuyos pasos se lanzan en paralelo, uno por pestaña |
| `live_state` | Inventario que el panel muestra como cabecera de estado, con su ✕ por fila |

## 3. Los ejes

`AxisDef.expand` decide con qué control se dibuja y `select` si tiene sentido pedir dos valores a la vez.

| `expand` | Control | Cuándo |
|---|---|---|
| `checks` | Casillas | `select='many'`: pedir dos es legítimo (panel + backoffice) |
| `scope` / `buttons` / `menu` | Segmentado | `select='one'`: pedir dos es un absurdo (start + stop) |
| `field` | Campo de texto | El valor se escribe: una ruta, un puerto, una URL. `values[0]` es el default |
| `pick` | Lista larga con búsqueda | Catálogo cerrado de cientos de valores: dispositivos, system images, AVD |

Modificadores que resuelven casos concretos:

| Campo | Qué resuelve |
|---|---|
| `labels` | El valor es un id feo (`system-images;android-36;google_apis;x86_64`) y lo que se elige es una frase |
| `defaults` / `checked_by_default` | Cuáles arrancan marcadas. Declarar el default como dato evita partir un eje en dos secciones |
| `allow_empty` | No elegir nada es una elección válida, no un olvido |
| `required` | Solo en `field`: vacío **no** es una elección (la URL a clonar) |
| `cast='int'` | El campo devuelve texto y la función hace aritmética |
| `truthy` | Un segmentado de dos valores que en realidad es un booleano ([ADR-0003](../adr/0003-contrato-de-nombres.md)) |
| `combine` + `join` | Un valor que se suma al excluyente: `patch` + `build` → `patch+build` |
| `requires_env` / `uses_env` | Claves que ese valor exige, o que solo hacen que aparezcan en el formulario filtrado |
| `facets` + `facet_sep` | El valor se compone de partes que se eligen por separado ([ADR-0027](../adr/0027-emuladores-tres-actividades.md)) |

### 3.1 Ejes que no se enumeran

Dos familias se declaran vacías y se llenan más tarde, porque el catálogo se arma una sola vez al arrancar y lo que listan cambia ([ADR-0006](../adr/0006-ejes-descubiertos-y-consultados.md)):

- **Descubiertos** (`discover=`): sus valores salen de mirar el repo abierto (`core/targets.py`). Los llena `catalog.for_project(cap, root)` justo antes de dibujar el panel, sobre una **copia** de la capacidad.
- **Consultados** (`source=`): salen de preguntarle al SDK (dispositivos, imágenes publicadas, imágenes instaladas, AVD, emuladores vivos) o al VPS del repo (servicios systemd que existen). Los resuelve `catalog.queried_values()` en el hilo de `AxesLoader`, y casi todos se cachean.

`ANDROID_RUNNING` es el único que nunca se cachea: es estado, no catálogo, y una respuesta vieja ofrecería apagar un emulador que ya no existe.

## 4. Los pasos

Un `Step` es una casilla de una compuesta, y su `id` es el nombre del booleano de la función. `optional=False` se dibuja marcado y deshabilitado: un «Build binario» sin build no es una variante, es un error.

- `requires_env` deja la casilla a la vista, en ámbar, porque lo que falta se puede cargar.
- `requires_repo` la hace **desaparecer**: no falta un dato, falta el objeto sobre el que actuar ([ADR-0007](../adr/0007-lo-inaplicable-desaparece.md)).

`composed_of` no deriva pasos. Sus entradas son ids de capacidad (`generate_remote_keypair`) y jamás coinciden con el nombre de un parámetro (`generate`); derivar de ahí producía casillas cuyo id no le correspondía a nada y funciones que corrían siempre con sus defaults.

## 5. De lo marcado a los kwargs

`ParamsPanel.payload()` agrupa por tipo de control, no por significado:

```
{'capability_id', 'project',
 'variants': {eje: [valores]},     # casillas
 'options':  {eje: valor|[valores]},# excluyentes
 'fields':   {eje: texto},          # escritos
 'picks':    {eje: valor},          # listas largas
 'steps':    [ids marcados],
 'missing_env': [claves]}
```

`Capability.kwargs_from(payload)` sabe en qué balde cayó cada eje por su `expand` y su `select`, aplica `multiline`, `cast`, `truthy`, `combine`/`join`, y suma un booleano por paso. Un eje ausente vale su default declarado, que es lo que el panel habría mostrado.

## 6. Qué se ve en cada repo

| Pregunta | Quién la contesta |
|---|---|
| ¿Este botón existe acá? | `catalog.applicable_ids(root)` → `Capability.applies_to(features)`. Hoy la única característica es `migrations` |
| ¿Qué valores tiene su eje? | `catalog.for_project` con `targets.names_of` |
| ¿Qué pasos quedan? | `Capability.steps_for(features)`, sobre la copia que mira el panel |
| ¿Puede correr ya? | `ui/params_panel.py::_blockers` y, sin abrir la pestaña, `ui/readiness.py` |

Un paso que el panel no dibujó no viene marcado en el payload, así que llega a la función en `False`: queda apagado, no «sin decidir».

## 7. Reglas al agregar o cambiar un botón

1. El `name` del eje y el `id` del paso son el nombre del parámetro. Sin excepciones.
2. Una variación que solo cambia una constante es un eje, no un botón nuevo ([ADR-0004](../adr/0004-un-boton-por-capacidad.md)).
3. Un dato que la tarea lee y que no cambia entre dos corridas es configuración, no eje ([ADR-0017](../adr/0017-datos-en-el-env-decisiones-en-el-json.md)).
4. Un dato distinto en cada corrida y sin default posible se pregunta al correr con `ctx.ask`, no se guarda.
5. Si la capacidad es destructiva, hay que declarar qué rompe en `core/protection.py::RULES` ([14](14_seguro_de_destructivos.md)).
6. Un botón nuevo entra en la tabla de [20](20_referencia_datos.md) y, si merece texto largo, en `core/command_docs.py`.

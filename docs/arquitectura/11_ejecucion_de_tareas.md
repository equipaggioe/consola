# 11 · Ejecución de tareas

Qué recibe una capacidad, cómo llega su salida a la pantalla y qué pasa cuando se la detiene.

## 1. `TaskContext`: lo único que recibe una capacidad

```
ctx.log / info / ok / warn / error     escribir en la consola de la pestaña
ctx.step(id)                           encabezado de un paso, con la etiqueta del catálogo
ctx.run / capture / detach             binarios externos: streaming, consulta corta, proceso suelto
ctx.serve / endpoint / publish         publicar una URL o un valor para otra tarea
ctx.confirm / ask / ask_once           preguntar; `expect` exige escribir un texto exacto
ctx.guard / mask                       enmascarar secretos
ctx.require_config                     fallar antes de empezar si falta una clave
ctx.progress / note                    avance y bitácora (ver 30: hoy no llegan a ningún lado / se muestran en el log)
ctx.cancel / cancelled / on_cancel     cancelación y apagado limpio
ctx.child(id)                          contexto de un paso interno: misma consola, misma cancelación
ctx.root / path(...)                   la carpeta del repo abierto
```

Los cinco `*_sink` son funciones que pone quien corre la tarea. En la aplicación los pone `ui/task_runner.py`; en un test no hace falta ninguno, y entonces `confirm` contesta lo seguro (`not danger`) y `ask` levanta `TaskError` en vez de colgarse ([ADR-0005](../adr/0005-todo-pasa-por-taskcontext.md)).

## 2. `TaskRunner`: el puente con la interfaz

Un `QThread` por corrida. Tres canales van de ida como señales (`logged`, `noted`, `serve_requested`) y uno es de ida y vuelta: `ask_requested`.

Ese cuarto es el que obliga a la maquinaria. Un diálogo de Qt solo se abre en el hilo de la interfaz, pero quien pregunta es el hilo de la tarea: `_ask` emite la señal y duerme sobre un `Event` en tandas de 0,1 s hasta que la interfaz llame a `provide_answer`. Las tandas cortas son para que `cancel()` pueda cortar también con el diálogo abierto; después de despertar se vuelve a mirar la cancelación, porque si no una corrida detenida se leería como un «no».

`TaskRunner` atrapa `Cancelled` (pestaña gris), `TaskError`/`MissingConfig` (pestaña roja) y cualquier otra excepción, para que el hilo nunca muera en silencio. En el cierre único llama a `ctx.release_endpoints()`: una URL que ya no sirve nada no debe seguir ofrecida.

Guarda además lo que la función devolvió en `self.result`. Casi ninguna capacidad lo usa —lo que entregan es su log o su endpoint—, pero las que declaran `opens_repo` devuelven la carpeta que dejaron en disco.

## 3. Los cuatro diálogos

`ui/tab_panel.py::_answer_task` elige por lo que la tarea espera de vuelta, no por cómo se ve la pregunta (`core/context.py::ASK_*`):

| Caso | Diálogo |
|---|---|
| `expect` no vacío | Campo de texto: hay que escribir exactamente eso. La fricción es el punto |
| `ASK_SECRET` | Campo con eco oculto |
| `ASK_TEXT` | Campo normal. Cerrarlo devuelve `ASK_CANCELLED`, que no es lo mismo que responder vacío |
| Resto | Sí/No, con el botón peligroso sin ser el predeterminado |

La distinción entre cancelar y responder vacío importa: en `create_avd` el vacío significa «usa el nombre derivado», así que un Escape creaba el AVD igual.

## 4. Procesos externos

`core/process.py` unifica lo que en los scripts eran tres funciones casi iguales:

| Función | Para |
|---|---|
| `stream` | Un proceso largo, línea a línea, cancelable |
| `capture` | Una consulta corta; no toca el log |
| `feed` | La excepción: `sdkmanager --licenses` pregunta una por una y no tiene bandera para aceptar |
| `spawn` + `bind_to_app` | Un proceso que sobrevive a su `ctx.run` pero no a la aplicación |
| `kill_tree` | Terminar el árbol de abajo hacia arriba |

Tres detalles que se pagaron caros y están fijados en el código: `stdin` va siempre a `DEVNULL` (un handle heredado deja colgada a la GUI), los shims `.bat`/`.cmd` de Windows se envuelven en `cmd /c`, y el nivel de cada línea se adivina por su propia etiqueta (`[ERROR]`, `warn`, `success`).

## 5. Lo que una tarea le deja a otra

`core/session.py` guarda en memoria, por proyecto, lo que una tarea publica: el puerto del backend, la URL con contraseña que necesita el explorador, el serial del último emulador arrancado (ámbito `@machine`). Nada de esto toca disco ([ADR-0009](../adr/0009-estado-de-sesion-en-memoria.md)).

Los **endpoints** son la parte que la interfaz mira todo el tiempo:

```
ctx.serve(url, key=..., label=..., web=True, wait=90)
```

Hace tres cosas de una vez: publica el endpoint en la sesión, emite la señal que dibuja la barra de la pestaña (y el navegador embebido si la capacidad declara `view='web'`), y lanza un hilo que sondea el puerto hasta que conteste, marcándolo `ready` o `down`. Se llama **antes** de `ctx.run()`, que bloquea hasta que el proceso muera; el puerto ya se eligió, así que la URL se conoce sin olfatear la salida de vite o de uvicorn ([ADR-0008](../adr/0008-un-launcher-entrega-un-endpoint.md)).

`ctx.endpoint(key, wait=...)` es el otro lado: la SPA espera a que el backend conteste de verdad en vez de confiar en el orden en que se apretaron los botones.

## 6. Cómo corre lo que se apretó

`ui/tab_panel.py::_run` es el punto único: por acá pasan el botón Ejecutar y el ▶ del buscador. En orden:

1. **Seguro.** `_guard_ok` clasifica la corrida con `core/protection.decide` ([14](14_seguro_de_destructivos.md)). Está acá y no en el panel porque este es el único camino común a las dos formas de ejecutar.
2. **Concurrente.** Si la capacidad es `concurrent`, reparte sus pasos en pestañas y termina; no hay `func` que llamar.
3. **Sin cuerpo.** Sin `func`, corre la simulación que reporta exactamente lo que correría.
4. **Reparto.** Si es `live` y tiene `fanout`, una pestaña por valor marcado; el primero se queda en la pestaña desde la que se apretó, solo cambiando de nombre.
5. **Real.** `_run_real` crea el `TaskRunner`, conecta sus señales y arranca.

Al terminar: la URL deja de ofrecerse, el botón Ejecutar vuelve a su estado, una capacidad con `opens_repo` hace que la ventana abra la carpeta como pestaña, y una `scope='machine'` invalida la caché de los catálogos que pudo haber cambiado y avisa a la barra de estado.

## 7. Detener

No hay botón «Detener». Se detiene **cerrando la pestaña**, y hay dos gestos más acotados:

| Gesto | Qué hace |
|---|---|
| Cerrar la pestaña | Desconecta las señales (la consola se destruye antes que la tarea) y cancela |
| Limpiar | Vacía el log y, solo si la tarea tiene un túnel SSH vivo, la detiene |
| ✕ en la cabecera de estado | Corre `stop_emulator` con ese serial, como una tarea más, sin adueñarse de la pestaña |

`ctx.on_cancel` registra apagados limpios que corren **antes** de `kill_tree`: al emulador se le pide `adb emu kill` y se le da un momento, o el AVD queda a medio escribir.

## 8. Pestañas y concurrencia

Una pestaña es una instancia de la acción, con sus parámetros y su consola. Abrir la misma acción dos veces la reusa, **salvo** que sea `live` y esté ocupada: ahí se abre otra numerada (`Emulador 2`), que es lo que permite dos emuladores o tres dev servers a la vez.

# ADR-0008 · Lo que un launcher entrega es una URL, no su log

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/context.py, core/session.py, core/ports.py, ui/tab_view.py

## Contexto

Los launchers se trataban como cualquier tarea: su producto era el texto que escupían. Pero nadie levanta un dev server para leer su log — lo levanta para abrir una URL, que hasta entonces había que buscar entre las líneas de salida de vite o de uvicorn.

## Decisión

1. Un launcher llama a **`ctx.serve(url, key=..., label=..., web=...)`** apenas conoce su puerto, **antes** de arrancar el proceso: el puerto ya se eligió (`ports.resolve_port`), así que la URL se conoce sin olfatear nada. `ctx.run` bloquea hasta que el proceso muere.
2. `serve()` hace tres cosas de una vez: publica el endpoint en la sesión del proyecto, emite la señal que dibuja la barra de la pestaña, y lanza un hilo que **sondea el puerto** hasta que conteste, marcándolo `ready` o `down`.
3. El navegador embebido es la **segunda vista de la misma pestaña** (`view='web'`), apuntada a ese endpoint. No es un botón del rail.
4. La URL que se anuncia no es la de escucha: `0.0.0.0` es dónde escucha, `localhost` es por dónde se entra.
5. Cuando la tarea termina, `release_endpoints()` borra lo que publicó.

## Consecuencias

- Un launcher que depende de otro espera su endpoint (`ctx.endpoint(key, wait=...)`) en vez de un `sleep` o del orden en que se apretaron los botones.
- El sondeo necesita su propio hilo, y `split_host_port` traduce `localhost` a `127.0.0.1` porque abre un socket IPv4.
- El explorador usa el mismo mecanismo con `web=False`: publica su conexión, no una URL para navegar.

## Descartado

- **Un botón «abrir navegador» en el rail.** Sería una capacidad que no ejecuta nada, no registra nada y no tiene parámetros.
- **Adivinar el puerto leyendo la salida del proceso.** Cada herramienta lo imprime a su manera, y llega tarde.

# ADR-0005 · El nivel 0 no imprime, no lee stdin y no sale del proceso: informa por su contexto

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/, core/tasks/, ui/task_runner.py

## Contexto

Los scripts tenían cuatro canales implícitos y globales: `print` para informar, `subprocess.run` para ejecutar, `SystemExit(1)` para fallar e `input()` para preguntar. Ninguno de los cuatro funciona dentro de una ventana: no hay consola donde imprimir, no hay teclado que leer, y salir del proceso se lleva puesta la aplicación entera.

## Decisión

1. Una capacidad recibe **un solo objeto**, `TaskContext`, y todo pasa por ahí: log, ejecución, preguntas, avance, endpoints, cancelación y configuración.
2. Nada de `core/` importa Qt, imprime a stdout, lee de stdin ni sale del proceso. Falla levantando `TaskError`.
3. Los `*_sink` son funciones que pone quien corre la tarea. Sin ninguno, la misma función sirve para un test: `confirm` contesta lo seguro (`not danger`) y `ask` levanta `TaskError` en vez de colgarse.
4. `MissingConfig` es una subclase aparte para que la interfaz pueda abrir la configuración **filtrada a las claves que faltan**.
5. Una compuesta llama a sus pasos con `ctx.child(id)`: misma consola, misma cancelación, misma memoria de respuestas. Un solo log plano, con un encabezado por paso.
6. La cancelación es parte del contrato: `ctx.run` la consulta, `on_cancel` registra apagados limpios que corren antes de matar el árbol de procesos.

## Consecuencias

- La misma función corre en una pestaña, como paso interno de una compuesta y en un test sin ventana.
- Preguntar desde un hilo que no es el de la interfaz obliga a un puente con espera (`ui/task_runner.py`), que es la parte más delicada de la ejecución.
- El botón de Detener todavía no existe en la interfaz, aunque la cancelación sí: se detiene cerrando la pestaña.

## Descartado

- **Pasarle a cada función los canales sueltos** (un logger, un runner, un asker). Son siempre los mismos cinco y viajan juntos a todas partes.

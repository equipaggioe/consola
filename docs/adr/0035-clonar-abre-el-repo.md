# ADR-0035 · Clonar termina con el repositorio abierto como pestaña

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/registry.py, core/tasks/git.py, ui/tab_panel.py, ui/main_window.py

## Contexto

Clonar un repositorio para después tener que añadir la carpeta a mano con «+» deja la acción a mitad de camino: el clon no se hace para tener una carpeta, se hace para trabajar ahí.

## Decisión

1. La capacidad declara **`opens_repo=True`**. Es lo único que hace falta declarar.
2. La tarea **devuelve la carpeta** donde dejó el repo. No sabe nada de pestañas.
3. La ventana abre esa carpeta como pestaña cuando la corrida termina bien. En la interfaz no hay ningún id de botón escrito: reacciona a la declaración.
4. `clone_repo` es `scope='machine'`, porque no le pasa al repo abierto sino a uno que todavía no existe: sus campos se guardan una sola vez.
5. Carpeta destino vacía significa «al lado de los repos que ya tengo abiertos», que es el único default que no hay que inventar.
6. Nunca escribe sobre una carpeta que ya existe: eso no sería clonar sino mezclar dos repos.

## Consecuencias

- Cualquier capacidad futura que deje un repo en disco hereda el comportamiento declarando el mismo campo.
- Devolver un valor es parte del contrato de esa capacidad, y `TaskRunner` lo guarda para eso.

## Descartado

- **Que la interfaz reconozca el id `clone_repo`.** Ata la ventana a un botón concreto.

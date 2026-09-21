# ADR-0017 · En `config.env` van los datos que las tareas leen; las decisiones van a `params.json` o a QSettings

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/settings.py, ui/params_store.py, ui/project_store.py

## Contexto

Con tres lugares donde guardar algo —el `.env` del repo, un archivo propio del repo y los ajustes de la máquina— hace falta una regla, o cada dato nuevo se decide por costumbre. Los seguros de los destructivos vivieron un tiempo en el formulario del `.env`, donde ninguna tarea los leía.

## Decisión

1. **`.consola/config.env`**: los **datos** que una tarea consume para trabajar. Si ningún paso lo lee, no va acá.
2. **`.consola/params.json`**: las **decisiones de la consola sobre ese repo** — lo marcado en cada botón, los seguros, las pestañas abiertas —. Comparten archivo porque comparten naturaleza, bajo claves con `@` que ningún id puede tener.
3. **`QSettings`**: las decisiones de **esta máquina** — qué repos están en pestañas, las favoritas, las secciones ocultas, y los parámetros y claves con `scope='machine'` —. Un repo no puede opinar sobre dónde va el SDK de Android.
4. Los parámetros viven **en el repo** y no en una tabla global indexada por ruta: esa se rompe si se mueve o se renombra la carpeta, deja basura al borrar el repo y no se puede mirar ni editar a mano.
5. `.consola/` se agrega al `.gitignore` la primera vez que se escribe: sigue siendo preferencia de esta máquina, solo que guardada donde corresponde.
6. Un dato distinto en cada corrida y sin default posible **no se guarda**: se pregunta al correr (`ctx.ask`).

## Consecuencias

- La pregunta «¿dónde va esto?» tiene una respuesta mecánica: ¿lo lee un paso? ¿es del repo o de la máquina?
- Un repo copiado a otra máquina se lleva su configuración y sus parámetros, pero no las favoritas ni la lista de pestañas.
- `params.json` se lee entero a una caché y se escribe agrupado cada 500 ms, porque hay dos accesos calientes: la revisión de qué puede correr y el guardado por tecla.

## Descartado

- **Todo en `QSettings`.** Una tabla global indexada por ruta, que se desincroniza al mover una carpeta.
- **Los seguros en `config.env`.** Ningún paso lee un `PROTECT_*`: no es un dato, es una decisión.

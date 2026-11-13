# ADR-0064 · En `config.env` van los datos que las tareas leen, y `.consola/` se ignora con su propio `.gitignore`

- **Estado:** Aceptada
- **Modificada por:** [ADR-0087](0087-la-camara-va-en-consola-camera-y-sus-capturas-en-consola.md), que reemplaza el punto 5
- **Fecha:** 2026-10-31
- **Alcance:** core/envfile.py, core/settings.py, ui/params_store.py, ui/project_store.py

## Contexto

El [ADR-0017](0017-datos-en-el-env-decisiones-en-el-json.md) fijó dónde va cada dato y agregaba `.consola/` al `.gitignore` del repo. Ese archivo ahora es de la plantilla de canone, que ya no ignora `.consola/` (ADR-0107 de canone), y escribirle una línea es tocar un archivo que no es de Consola. Este ADR reemplaza al 0017 y conserva lo demás.

## Decisión

1. **`.consola/config.env`**: los **datos** que una tarea consume para trabajar. Si ningún paso lo lee, no va acá (del ADR-0017).
2. **`.consola/params.json`**: las **decisiones de la consola sobre ese repo** — lo marcado en cada botón, los seguros, las pestañas abiertas —, bajo claves con `@` que ningún id puede tener (del ADR-0017).
3. **`QSettings`**: las decisiones de **esta máquina** — qué repos están en pestañas, las favoritas, las secciones ocultas, y los parámetros y claves con `scope='machine'` — (del ADR-0017).
4. Los parámetros viven **en el repo** y no en una tabla global indexada por ruta (del ADR-0017).
5. **`.consola/.gitignore`, con `*`, ignora la carpeta entera.** Lo escribe Consola la primera vez que escribe en `.consola/` (`envfile.ensure_ignored`), y no toca el `.gitignore` del repo. Si no puede escribirlo, falla: guardar sin él deja `config.env`, con sus secretos, listo para commitearse.
6. Un dato distinto en cada corrida y sin default posible **no se guarda**: se pregunta al correr (`ctx.ask`) (del ADR-0017).

## Consecuencias

- Los repos que ya tienen `.consola/` en su `.gitignore` la conservan; Consola no la quita.
- Copiar `.consola/` a otro repo se lleva también su `.gitignore`.

## Descartado

- **Seguir agregando `.consola/` al `.gitignore` del repo.** Escribe en un archivo de la plantilla de canone.
- **Que un fallo al escribir el `.gitignore` no rompa el guardado**, como antes. Es el degradado silencioso que deja los secretos a un `git add` de distancia.
- **Todo en `QSettings`** (del ADR-0017). Una tabla global indexada por ruta, que se desincroniza al mover una carpeta.

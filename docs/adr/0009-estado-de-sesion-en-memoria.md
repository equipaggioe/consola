# ADR-0009 · Lo que una tarea le deja a otra vive en memoria, no en un archivo del repo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/session.py, core/ports.py

## Contexto

El script del backend escribía `SERVER_PORT` en el `.env` para que los de la terminal y las SPA lo leyeran después. Funcionaba por casualidad de orden de ejecución y ensuciaba el repo con un dato que no es configuración: es el puerto que el backend consiguió **en esa corrida**.

## Decisión

1. Lo que una tarea publica para otra vive en **memoria**, con alcance por proyecto, y desaparece al cerrar la aplicación (`core/session.py`).
2. Hay un ámbito `@machine` para lo que no es de ningún repo: el serial del emulador recién arrancado sirve igual desde cualquier proyecto.
3. Los **endpoints** son la parte de ese estado que la interfaz mira todo el tiempo, y tienen su propio ciclo de vida con estados `starting`/`ready`/`down`.
4. `ctx.publish` es la otra mitad, para lo que no se puede mostrar: la URL con contraseña que el explorador necesita. Se borra sola cuando la tarea termina.
5. Nada de esto se escribe a disco, y `DATABASE_URL` viaja por el entorno del subproceso, nunca a un archivo.

## Consecuencias

- El repo deja de ensuciarse con datos de una corrida.
- El estado no sobrevive a reiniciar la aplicación, y no tiene por qué: describe procesos vivos.
- Quien lea un endpoint tiene que aceptar que no exista: sin backend, la SPA arranca con su propia configuración en vez de fallar.

## Descartado

- **Un archivo de estado en `.consola/`.** Sería un dato de proceso vivo escrito en disco, que sobrevive a lo que describe.

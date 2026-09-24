# ADR-0051 · La plomería de las cámaras es un kit de Consola que la cámara recibe en `--kit`

- **Estado:** Aceptada
- **Fecha:** 2026-09-24
- **Alcance:** `camara/`, `core/shots.py`, `core/tasks/images.py`

## Contexto

Con los datos en un escenario servido por un servidor ficticio ([ADR-0050](0050-las-capturas-no-tocan-la-base.md)), toda cámara repite la misma plomería: leer los argumentos del contrato ([ADR-0049](0049-la-camara-de-capturas-es-un-script-del-repo.md)) y nombrar los crudos, el servidor ficticio con su WebSocket, levantar Vite apuntado a él, preparar la página (tema, idioma, zona horaria, reloj), reintentar cuando Vite recarga, y en Android el reloj del emulador y `flutter drive`. En vettore eran unas 225 líneas de JS entre `capturar.mjs` y `servidor.mjs`.

Copiada en cada repo, cada copia se desalinea por su cuenta, y el lado del contrato que vive en la cámara cambia sin que Consola se entere.

## Decisión

1. **El kit vive en el repo de Consola**, en `camara/index.mjs`, porque Consola define el contrato: un cambio de argumentos o de nombres cambia las dos puntas en el mismo commit.
2. **Consola le pasa la ruta del kit a la cámara en `--kit`**, junto con los demás argumentos. La cámara lo importa desde ahí. Se ve en el comando, y la cámara usa siempre el kit de la Consola que la corre.
3. **El kit no tiene dependencias.** Vive fuera del repo y no resuelve sus `node_modules`: lo que necesita Playwright recibe el navegador de la cámara.
4. **Lo propio del repo se queda en el repo**: el escenario, el mapa de rutas del servidor ficticio, el protocolo de su tiempo real, lo que se siembra en el cliente y la navegación.

## Consecuencias

- La cámara no corre sin `--kit`. A mano, se le pasa la ruta de `camara/index.mjs`.
- Con una app móvil marcada, Consola pone en el PATH de la cámara el `adb` del SDK que encontró, que es el que usa el kit.
- El kit se prueba con `node --test`, y `tests/test_camara.py` lo corre dentro de pytest.
- La parte Dart (bajar el escenario, esperar el reloj, el driver que nombra los PNG) no entra: se compila dentro de la prueba y no puede recibir una ruta al correr. Si va en un paquete de Consola o se copia en cada app Flutter no está decidido.

## Descartado

- **Una dependencia `file:../consola/camara` en el `package.json` de cada repo**: exige que los repos estén clonados uno al lado del otro en cada máquina.
- **Copiar la plomería en cada repo**: una copia por repo que se desalinea sola.

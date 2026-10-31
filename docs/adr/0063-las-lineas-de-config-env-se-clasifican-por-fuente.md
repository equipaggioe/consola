# ADR-0063 · Las líneas de `config.env` se clasifican por la fuente que declara cada clave

- **Estado:** Aceptada
- **Fecha:** 2026-10-31
- **Alcance:** core/settings.py, core/fields.py, core/envfile.py, ui/env_panel.py

## Contexto

Con canone, `config.env` junta tres clases de datos que van a destinos distintos: los argumentos de `install.py` (el dominio, la memoria de Valkey, `--private`, `--turn`…), las credenciales que se pasan a `credentials.py` (un archivo por campo de `Settings`, más `restic_password` y `github_token`), y lo que lee Consola para alcanzar el VPS. canone fija lo que recibe cada programa, pero no cómo Consola junta y guarda sus datos (ADR-0107 de canone).

## Decisión

1. **Una clave es de una de tres fuentes**, y se sabe de cuál por quién la declara:
   - **Los campos de `Settings` del repo.** Se leen con `ast` de `<SERVER_DIR>/src/app/config.py`, que es quien los declara. La clave es el nombre del campo en mayúsculas (`health_token` → `HEALTH_TOKEN`). Salen `database_url` y `turn_secret`, que escribe `install.py`.
   - **Las dos con nombre fijo** de `credentials.py`: `RESTIC_PASSWORD` y `GITHUB_TOKEN`.
   - **El registro de `core/settings.py`**: los argumentos de `install.py` y las claves propias de Consola.
2. **Una clave que cae en dos fuentes corta**: un campo de `Settings` que se llame como una clave del registro no se sabría a quién mandarlo.
3. **Los campos de `Settings` se ven en el formulario de Configuración**, en el grupo «Credenciales» con las dos de nombre fijo, y `config.env` los escribe en ese grupo.
4. **Sin `config.py` no hay campos**: el repo no sigue la plantilla de canone. Con el archivo y sin la clase `Settings`, el formulario lo dice.
5. *(propuesta)* **La llave pública guardada fuera (`OFFLINE_KEY`), `LOGS` y `LOGS_KEY` son de la máquina** (`scope='machine'`): son las mismas para todos los VPS.

## Consecuencias

- Antes de enviar nada a `credentials.py`, quien envía puede comprobar que cada línea cae en una fuente y que ningún campo está vacío.
- Un campo nuevo en `config.py` aparece en el formulario al volver a abrir el repo.
- Las claves de `config.env` que no caen en ninguna fuente siguen bajo «Otras claves».

## Descartado

- **Declarar en Consola la lista de credenciales de cada repo.** Sería una segunda copia de lo que ya declara `config.py`, y se desincronizaría al agregar un campo.
- **Importar `config.py`.** Pide el venv del repo, y el módulo lee `CREDENTIALS_DIRECTORY` al cargarse.

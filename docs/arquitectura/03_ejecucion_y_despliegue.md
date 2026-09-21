# 03 · Ejecución y despliegue

## 1. Cómo se corre

```
pip install -r requirements.txt
python main.py
```

No hay instalador ni empaquetado propio: Consola se ejecuta desde el repositorio. Puede empaquetarse a sí misma con su botón «Build binario», que deduce `main.py` en la raíz cuando el repo no tiene ninguna app Python que descubrir (`core/tasks/builders.py::resolve_entrypoint`).

## 2. Hilos y procesos

| Quién | Dónde corre | Por qué |
|---|---|---|
| Interfaz | Hilo principal de Qt | Único lugar donde se puede abrir un diálogo |
| Una capacidad | `TaskRunner(QThread)`, uno por corrida | Un build o un `ssh` no pueden bloquear la ventana |
| Catálogos consultados | `AxesLoader(QThread)`, uno por panel | Preguntarle al SDK tarda segundos; al VPS, una vuelta de SSH |
| Consultas del explorador | `DbWorker`, propio de cada vista | Una consulta lenta no congela el árbol |
| Sondeo de un endpoint | Hilo suelto que lanza `ctx.serve()` | Quien sirvió sigue derecho a `ctx.run()`, que no vuelve hasta que el proceso muere |
| Vigilante de fuentes | Hilo suelto de `run_python_app` | Mira las marcas de tiempo cada 0,5 s y mata al hijo cuando cambian |
| Binarios externos | Subprocesos | `core/process.py`: salida unificada, `stdin` a `DEVNULL`, cancelables |

Varias tareas conviven: cada pestaña de ejecución tiene la suya, y un repo puede tener varias pestañas vivas a la vez (dos emuladores, tres dev servers).

## 3. Qué pasa al cerrar

`MainWindow.closeEvent` baja a disco los parámetros pendientes (`params_store.flush`) y llama a `TabPanel.shutdown()` de cada repo. Ese apagado cancela cada tarea como lo haría cerrar su pestaña —con sus ganchos limpios, por ejemplo `adb emu kill`— y espera hasta 5 s.

Lo que no alcance a cerrarse lo mata el sistema: en Windows cada proceso lanzado con `detach`/`spawn` entra en un **Job Object** con `KILL_ON_JOB_CLOSE` (`core/process.py::bind_to_app`), así que un túnel `ssh -L` no sobrevive a la aplicación ni cuando esta se cae.

## 4. Dónde queda el estado

| Dónde | Qué | Sobrevive a |
|---|---|---|
| `<repo>/.consola/config.env` | Los datos que las tareas leen | Todo. Es del repo, está en su `.gitignore` |
| `<repo>/.consola/params.json` | Parámetros de cada botón, seguros y pestañas abiertas | Todo |
| `<repo>/.consola/Caddyfile.generado` | Copia de referencia del último Caddyfile escrito | Todo |
| `QSettings` (`Consola/Consola`) | Repos abiertos, favoritas, secciones ocultas, parámetros de las acciones de máquina | Reinstalar el repo |
| `%LOCALAPPDATA%\Consola\cache` o `~/.cache/consola` | Catálogos del SDK y servicios del VPS | La sesión; caducan por edad |
| Memoria (`core/session.py`) | Endpoints publicados, puerto del backend, serial del emulador | Nada: muere con el proceso |

Detalle de cada formato en [20](20_referencia_datos.md); el reparto entre repo y máquina, en [13](13_configuracion_y_persistencia.md).

## 5. Qué toca fuera de la máquina

| Destino | Con qué | Qué escribe |
|---|---|---|
| VPS | `ssh`, `scp`, túneles `-L` | `/etc/systemd/system/<repo>.service`, `/etc/tmpfiles.d/<repo>.conf`, `/etc/turnserver.conf`, `/etc/caddy/Caddyfile`, el repo clonado bajo `VPS_DEPLOY_DIR`, su venv, los artefactos y los archivos de `SECRET_FILES` |
| GitHub | `git` y la API v3 | Empuja ramas; da de alta y de baja llaves de despliegue por título |
| Cloudflare | API v4 | Un registro A |
| Esta máquina | `~/.ssh`, entorno del usuario | Pares de llaves, `known_hosts`, `HKCU\Environment` o el perfil del shell |

Consola nunca escribe a nivel sistema en la máquina local: el PATH y las variables de los SDK van al usuario ([ADR-0029](../adr/0029-entorno-a-nivel-usuario.md)).

## 6. Requisitos según lo que se use

| Para | Hace falta |
|---|---|
| Abrir un repo y ver el catálogo | Nada más que Python y PySide6 |
| Backend, seeders, migraciones locales | El venv del servidor del repo (`<SERVER_DIR>/.venv`) |
| SPA | Node y `npm` |
| App móvil y builds | Flutter o Flet, y el SDK de Android para emular |
| Binario | PyInstaller, preferido del venv de la app |
| Todo lo del VPS | `ssh`/`scp` en el PATH y las claves `VPS_*` cargadas |
| Base local | Postgres instalado; en Windows se busca `psql.exe` bajo `C:\Program Files\PostgreSQL` |
| Explorador | `psycopg`; la importación es diferida, así que su ausencia solo rompe ese botón |

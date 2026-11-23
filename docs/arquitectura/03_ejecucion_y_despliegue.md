# 03 · Ejecución y despliegue

## 1. Cómo se corre

```
cd desktop
uv sync
for locale in en es; do
  uv run pyside6-lrelease src/app/translations/$locale.ts -qm src/app/translations/$locale.qm
  uv run python -c "import shutil, sys; from PySide6.QtCore import QLibraryInfo as L; shutil.copy(f'{L.path(L.LibraryPath.TranslationsPath)}/qtbase_{sys.argv[1]}.qm', 'src/app/translations')" $locale
done
uv run pyside6-rcc src/app/resources.qrc -o src/app/rc_resources.py
uv run python -m app.main
```

Consola se ejecuta desde el repositorio. Los `.qm` y `rc_resources.py` se generan y no van en git, como en el job `desktop` de `ci.yml`. `main.py` importa `rc_resources.py`, así que sin él no arranca, y se vuelven a generar cuando cambia una imagen de `resources.qrc` o una traducción ([02](02_bloques.md) §5).

Los textos se extraen a `translations/es.ts` y a `translations/en.ts` de los `.py` que git no ignora, como pide `qt.md` de canone: `uv run pyside6-lupdate $(git ls-files --cached --others --exclude-standard 'src/app/*.py') -ts src/app/translations/<locale>.ts`, con `-no-obsolete` para que no queden los que ya no están. `tests/test_language.py` falla si un texto del catálogo no está en `es.ts`, o si uno de `en.ts` no tiene su inglés ([04](04_conceptos_transversales.md) §10).

Con cada tag, `.github/workflows/release.yml` corre `ci.yml`, crea el release en borrador y construye con `pyside6-deploy`, desde `desktop/pysidedeploy.spec`, un binario por cada sistema cuya variable de GitHub vale `true`: `desktop-linux.bin` con `RELEASE_DESKTOP_LINUX` y `desktop-windows.exe` con `RELEASE_DESKTOP_WINDOWS`. Con `RELEASE_DESKTOP_MACOS` en `true`, el job `systems` falla: Consola no se publica para macOS ([ADR-0081](../adr/0081-consola-se-publica-para-windows-y-linux.md)). El job `canone` de `ci.yml` le pasa las variables a `verificar.py`, que falla si falta alguna. El release se publica cuando tiene su `.sha256`.

El job `desktop` instala primero las dependencias, después compila las traducciones y `resources.qrc`, y al final instala la app, sin modo editable: Nuitka compila la copia instalada, y una instalada antes de compilar los recursos no tiene `rc_resources.py`. El binario lleva aparte `assets/shots_presets.json` y `assets/camera/index.mjs`, que se leen del disco. Lo que falta probar está en [30](30_riesgos_y_pendientes.md).

Puede empaquetarse a sí misma con su botón «Build binario», que deduce `main.py` en la raíz cuando el repo no tiene ninguna app Python que descubrir (`services/tasks/builders.py::resolve_entrypoint`).

## 2. Hilos y procesos

| Quién | Dónde corre | Por qué |
|---|---|---|
| Interfaz | Hilo principal de Qt | Único lugar donde se puede abrir un diálogo |
| Una capacidad | `TaskRunner(QThread)`, uno por corrida | Un build o un `ssh` no pueden bloquear la ventana |
| Catálogos consultados | `AxesLoader(QThread)`, uno por panel | Preguntarle al SDK tarda segundos; al VPS, una vuelta de SSH |
| Consultas del explorador | `DbWorker`, propio de cada vista | Una consulta lenta no congela el árbol |
| Sondeo de un endpoint | Hilo suelto que lanza `ctx.serve()` | Quien sirvió sigue derecho a `ctx.run()`, que no vuelve hasta que el proceso muere |
| Vigilante de fuentes | Hilo suelto de `run_python_app` | Mira las marcas de tiempo cada 0,5 s y mata al hijo cuando cambian |
| Binarios externos | Subprocesos | `services/process.py`: salida unificada, `stdin` a `DEVNULL`, cancelables |

Varias tareas conviven: cada pestaña de ejecución tiene la suya, y un repo puede tener varias pestañas vivas a la vez (dos emuladores, tres dev servers).

## 3. Qué pasa al cerrar

`MainWindow.closeEvent` baja a disco los parámetros pendientes (`params_store.flush`) y llama a `TabPanel.shutdown()` de cada repo. Ese apagado cancela cada tarea como lo haría cerrar su pestaña —con sus ganchos limpios, por ejemplo `adb emu kill`— y espera hasta 5 s.

Lo que no alcance a cerrarse lo mata el sistema, solo en Windows: un túnel `ssh -L` entra en un **Job Object** con `KILL_ON_JOB_CLOSE` (`services/host.py::WindowsHost.bind_to_app`) y no sobrevive a la aplicación ni cuando esta se cae. En Linux no hay equivalente todavía: si Consola se cae de golpe, el túnel sigue vivo ([30](30_riesgos_y_pendientes.md)).

## 4. Dónde queda el estado

| Dónde | Qué | Sobrevive a |
|---|---|---|
| `<repo>/.consola/config.env` | Los datos que las tareas leen | Todo. Es del repo, está en `.consola/.gitignore` |
| `<repo>/.consola/params.json` | Parámetros de cada botón, seguros y pestañas abiertas | Todo |
| `QSettings` (`Equipaggio/Consola`), en `%APPDATA%\Equipaggio\Consola.ini` o `~/.config/Equipaggio/Consola.ini` | Repos abiertos, valores de las claves de máquina, favoritas, secciones ocultas, parámetros de las acciones de máquina | Reinstalar el repo |
| `%LOCALAPPDATA%\Consola\cache` o `~/.cache/consola` | Catálogos del SDK y servicios del VPS | La sesión; caducan por edad |
| Memoria (`services/session.py`) | Endpoints publicados, puerto del backend, serial del emulador | Nada: muere con el proceso |

Detalle de cada formato en [20](20_referencia_datos.md); el reparto entre repo y máquina, en [13](13_configuracion_y_persistencia.md).

## 5. Qué toca fuera de la máquina

| Destino | Con qué | Qué escribe |
|---|---|---|
| VPS | `ssh`, `scp`, túneles `-L` | Lo que instalan `packages.py`, `swap.py`, `uv.py`, `install.py` y `credentials.py`, y el ejecutable de «Compilar ejecutable» con sus manifiestos bajo `VPS_DEPLOY_DIR`. No escribe configuración de servicios ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)) |
| GitHub | `git` | Empuja ramas y clona repos |
| Cloudflare | API v4 | El registro A de cada host de la app, sin proxy |
| Esta máquina | `~/.ssh`, entorno del usuario | Pares de llaves, `known_hosts`, `HKCU\Environment` o el perfil del shell |

Consola nunca escribe a nivel sistema en la máquina local: el PATH y las variables de los SDK van al usuario ([ADR-0029](../adr/0029-entorno-a-nivel-usuario.md)).

## 6. Requisitos según lo que se use

| Para | Hace falta |
|---|---|
| Abrir un repo y ver el catálogo | Nada más que Python y PySide6 |
| Backend, seeders, migraciones locales | El venv del servidor del repo (`<SERVER_DIR>/.venv`) |
| SPA | Node y `pnpm` |
| App móvil y builds | Flutter o Flet, y el SDK de Android para emular |
| Binario | PyInstaller, preferido del venv de la app |
| Todo lo del VPS | `ssh`/`scp` en el PATH y las claves `VPS_*` cargadas |
| Base local, respaldo y restauración | Postgres instalado en esta máquina: la versión más nueva bajo `C:\Program Files\PostgreSQL` en Windows o `/usr/lib/postgresql` en Linux (`services/host.py::pg_tool`) |
| Sesión SSH interactiva | Windows Terminal (`wt.exe`) en Windows; `x-terminal-emulator` en Linux |
| Explorador | `psycopg`; la importación es diferida, así que su ausencia solo rompe ese botón |

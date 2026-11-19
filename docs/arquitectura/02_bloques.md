# 02 · Estrategia y bloques

## 1. Tres capas y una regla de dirección

```mermaid
flowchart TD
    MAIN[main.py] --> CAT[core/catalog.py<br/>declara la forma]
    MAIN --> BIND[core/tasks/bind_all<br/>le da cuerpo]
    MAIN --> UI[ui/ · PySide6]
    UI --> REG[core/registry.py<br/>Registry · Capability · AxisDef · Step]
    CAT --> REG
    BIND --> REG
    UI -- "TaskRunner (QThread)" --> T[core/tasks/<br/>niveles 1 y 2]
    T --> N0[core/ nivel 0<br/>plomería]
    N0 --> EXT([binarios externos<br/>git · ssh · flutter · pnpm · adb · psql])
```

| Nivel | Qué es | ¿Botón? | Dónde vive |
|---|---|---|---|
| **0 — plomería** | Resuelve una clase de problema y no es un paso del dominio: leer un `.env`, armar un `argv` de SSH, elegir un puerto libre | Nunca | `core/*.py` |
| **1 — atómicas** | Una responsabilidad, construida sobre el nivel 0. Casi todas son de tres a diez líneas | Sí, si alguien la pide sola | `core/tasks/*.py` |
| **2 — compuestas** | Encadenan atómicas en un orden fijo. No reimplementan nada: llaman | Sí, además del botón de cada paso | `core/tasks/*.py` |

`api/` guarda los modelos de Pydantic de las respuestas HTTP que se leen (Cloudflare y el índice de Flutter); lo usa `core/tasks/utils.py` y no importa nada de Consola. Toda respuesta HTTP de un tercero se lee con su modelo, y una que no coincide detiene la tarea con `TaskError`.

La dirección es estricta: `ui/` importa de `core/`, `core/tasks/` importa de `core/`, y `core/` no importa ni de `ui/` ni de `core/tasks/`. La excepción es una importación diferida dentro de una función, no de módulo: `core/context.py` pide el registro para traducir el id de un paso a su etiqueta.

## 2. Qué hay en `core/` (nivel 0)

| Módulo | Qué resuelve |
|---|---|
| `errors.py` | `TaskError`, `Cancelled`, `MissingConfig`. Nadie imprime ni sale del proceso |
| `context.py` | `TaskContext`: log, ejecutar, preguntar, publicar un endpoint, cancelar |
| `process.py` | Correr binarios externos: streaming, captura, alimentar stdin, contestar preguntas, matar el árbol, atar al proceso |
| `envfile.py` | `.consola/config.env`: leer, regenerar, y `Config` con acceso tipado y defaults |
| `settings.py` | El esquema de claves: quién las exige y quién solo las usa |
| `fields.py` | Los campos de `Settings` del repo administrado, leídos con `ast` |
| `http.py` | HTTP con el único `QNetworkAccessManager`, en el hilo de la interfaz, bloqueando el hilo de la tarea que llama, con reintentos |
| `canone.py` | Lo que se le pasa a los programas de canone: opciones de `packages.py` y la lista que devuelve con `--list`, argumentos de `install.py`, líneas de `credentials.py` |
| `registry.py` | `Registry`, `Capability`, `AxisDef`, `Facet`, `Step`, y el puente a los kwargs |
| `catalog.py` | La declaración de las 54 capacidades y la resolución de ejes contra el repo o contra una fuente consultada |
| `targets.py` | Qué subproyectos y qué características tiene el repo abierto |
| `toolchain.py` | Ubicar `flutter`, `flet`, `pnpm`, `pyinstaller` y el Python de un venv; las plataformas de build |
| `ssh.py` | `Remote`, ejecución remota con o sin stdin, `scp`, túneles, llaves |
| `vps.py` | Rutas del repo desplegado, los servicios systemd y su journal |
| `database.py` | Resolver la base local o la remota por túnel, y el canal de superusuario |
| `runner.py` | Corre el código del repo con el venv de aquí, contra la base local |
| `db_explorer.py` | Introspección de solo lectura sobre `pg_catalog` |
| `db_models.py` | Los modelos del repo, importados con su propio Python, para comparar contra la base |
| `versioning.py` | Leer y subir la versión de `pubspec.yaml`, `package.json` o `pyproject.toml` |
| `android.py` | SDK, catálogos de dispositivos e imágenes, AVD, arranque y apagado de emuladores |
| `shots.py` | Capturas: argumentos de la cámara, nombre y validación de los crudos, revelado (`shots_presets.json`) |
| `icons.py` | Íconos: qué apps toman el suyo del logo y qué capa va a cada archivo que declaran (pubspec, `icon.png` de Flet, `<link>` y manifest de PWA de una SPA) |
| `userenv.py` | Variables y PATH persistentes a nivel usuario, sin administrador |
| `host.py` | Lo que cambia entre Windows y Linux en esta máquina: nombres de ejecutables, venv, procesos, terminal, Postgres local, entorno, RAM, caché |
| `toolstatus.py`, `sysinfo.py` | Qué herramientas hay en la máquina y cuánta RAM queda, para la barra de estado |
| `cache.py` | Caché en disco de los catálogos caros |
| `session.py` | Estado de sesión en memoria: endpoints y valores que una tarea publica para otra |
| `ports.py` | Elegir un puerto libre y esperar a que algo conteste en él |
| `files.py` | Comparar, copiar, borrar, revertir, descomprimir, huella |
| `protection.py` | Qué rompe cada acción destructiva y qué hace la consola con eso |
| `command_docs.py` | El texto largo de cada comando, para la ficha del panel derecho |
| `projects.py` | El `dataclass Project`. La lista la maneja la interfaz |

## 3. Qué hay en `core/tasks/` (niveles 1 y 2)

Un módulo por grupo del catálogo. `bind_all()` recorre los diez y reemplaza cada stub por su función.

| Módulo | Capacidades |
|---|---|
| `launchers.py` | `backend`, `serve_vite`, `run_mobile`, `run_python`, `ssh_login` |
| `builders.py` | `build_flutter`, `build_vite`, `build_binary`, `create_spa`, `bump_version`, `upload_to_vps` |
| `images.py` | `generate_icons`, `shoot_screens`, `render_shots`, `screenshots` |
| `raster.py` | No es un grupo: el SVG como PNG o como ICO, con QtSvg y Pillow. Lo usan `images.py` y `builders.py` |
| `emulators.py` | `install_system_image`, `create_avd`, `launch_emulator`, `stop_emulator`, `purge_emulators` |
| `git.py` | `git_force_push`, `git_force_reset`, `clone_repo` |
| `vps_ops.py` | `health_check`, `view_events`, `run_command`, `revoke_ssh` |
| `vps_server.py` | `systemd_action`, `view_logs` |
| `vps_setup.py` | `refresh_known_host`, `install_software`, `load_credentials`, `bootstrap_vps` |
| `vps_release.py` | `publish_release`, `deploy_version` |
| `database.py` | Los doce del grupo Base de datos |
| `utils.py` | Limpieza, Cloudflare, sincronización y los cinco de SDK |
| `payloads.py` | La excepción deliberada: programas Python que viajan por `-c` al intérprete del proyecto |

## 4. Qué hay en `ui/`

| Bloque | Archivos | Qué hace |
|---|---|---|
| Ventana | `main_window.py`, `title_bar.py`, `project_tabs.py`, `repo_logo.py`, `assets/` | Ventana sin marco, repos como pestañas de nivel 1, acento y logo por repo |
| Catálogo a la vista | `menu_bar.py`, `action_search.py`, `widgets/action_row.py`, `favorites.py` | El catálogo entero en una barra de menú y un buscador con ▶ |
| Espacio de trabajo | `tab_panel.py`, `tab_view.py`, `console_view.py`, `browser_view.py` | Pestañas de ejecución de un repo, consola, segunda vista |
| Panel derecho | `params_panel.py`, `env_panel.py`, `security_panel.py`, `command_info_panel.py`, `widgets/accordion.py` | Parámetros, configuración, seguros y ficha, en un acordeón |
| Ejecución | `task_runner.py`, `guard_dialog.py` | Corre la capacidad en un hilo y puentea sus canales; los dos avisos del seguro |
| Explorador | `db_explorer_view.py`, `db_worker.py` | Árbol, datos y estructura, sobre su propio hilo |
| Persistencia | `params_store.py`, `project_store.py`, `section_visibility.py` | `.consola/params.json` del repo y `QSettings` de la máquina |
| Apoyo | `theme.py`, `readiness.py`, `widgets/*` | Colores y tipografía, qué puede correr ya, controles propios |


## 6. `camera/`

El kit de las cámaras de capturas: JS sin dependencias que no corre dentro de Consola, sino dentro del script de cámara de cada repo, que lo recibe en `--kit` ([19](19_imagenes.md) §6, [ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).

## 7. Arranque

`main.py` hace cinco cosas, en orden: fija el escalado de alta densidad, crea la `QApplication`, llama a `load_catalog()` y a `bind_all()`, aplica el tema y muestra la ventana. El catálogo se arma una sola vez por proceso; lo que depende del repo se resuelve después, cada vez que se dibuja un panel ([10](10_catalogo_de_capacidades.md)).

# 14 · El seguro de los destructivos

## 1. Qué problema resuelve

No es apretar un botón sin querer: es apretarlo **en el repo equivocado**. Y no todo lo destructivo pesa igual —vaciar la carpeta de artefactos de un repo de juguete se rehace con un build; borrar la base del VPS de producción, no— ([ADR-0018](../adr/0018-seguro-por-repo-y-objetivo.md)).

## 2. El seguro es por tipo de objetivo, no por botón

Lo que importa es el radio de daño. Un mismo botón puede tocar dos objetivos (`clean_vps` borra la base además del servidor) y un mismo botón puede tocar objetivos distintos según sus parámetros (`teardown_db` contra `local` no sale de esta máquina; contra `remoto` alcanza al VPS).

| Objetivo | Se lee | Protegido por defecto | Por qué |
|---|---|---|---|
| `vps` | el VPS | sí | Alcanza a una máquina remota y no hay deshacer |
| `db` | la base de datos | sí | Los datos borrados no vuelven sin un backup |
| `otros_repos` | otros repositorios | sí | Escribe fuera de este repo, en carpetas que no estás mirando |
| `publicacion` | el canal de publicación | sí | Lo que se promueve queda a la vista de los usuarios |
| `local` | archivos de este repo | **no** | Un artefacto borrado se rehace con un build |
| `origin` | origin en GitHub | **no** | Reescribe el historial que ven quienes clonaron, pero no toca esta máquina ni el VPS |

Un objetivo que no figura en el `params.json` cae en su default: agregar uno nuevo no puede dejar desprotegidos a los repos que ya existen.

## 3. Qué rompe cada acción

`core/protection.py::RULES` declara, por capacidad, los objetivos fijos (`always`), los que dependen de un eje (`when`) y los valores con los que la acción no destruye nada (`dry_run`).

| Acción | Objetivos |
|---|---|
| `clean_vps` | `vps` + `db` |
| `revoke_ssh`, `revoke_github_ssh` | `vps` |
| `teardown_db`, `rebuild_db` | `db`, y `vps` si el ámbito es `remoto` |
| `reinit_migrations` | `db` + `local`, y `vps` si el ámbito es `remoto` |
| `promote_app` | `publicacion` |
| `clean_artifacts`, `sync_server_env` | `local`, salvo en simulacro |
| `sync_common_files` | `otros_repos`, salvo en simulacro |
| `git_force_push`, `git_force_origin_from_vps` | `origin` |
| `git_force_reset` | `local` |
| `git_force_vps` | `vps` |

`purge_emulators` no está en la tabla: es `scope='machine'` —borra AVD e imágenes del SDK, que no son de ningún repo— así que un interruptor por repositorio no tendría a qué repositorio pertenecer. Se queda con su propia confirmación escrita.

Un simulacro no dispara nada, y por eso no pregunta nada: pedir confirmación ahí sería el ruido que gasta la señal del aviso de verdad.

## 4. Las tres respuestas

`protection.decide(state, capability_id, payload)` clasifica la corrida:

| Decisión | Cuándo | Qué pasa |
|---|---|---|
| `ALLOW` | No rompe nada con estos parámetros, o es un simulacro | Corre sin preguntar |
| `REMIND` | Rompe algo, pero este repo no protege ninguno de esos objetivos | Recordatorio con el repo a la vista: Cancelar o Continuar. Ni palabra escrita ni nombre de repo |
| `BLOCK` | Toca un objetivo protegido en este repo | No corre. El aviso **no ofrece forma de saltarlo** |

El bloqueo no tiene escape por diseño: el seguro se quita en la sección Seguridad, una vez, con la cabeza fría. Los dos diálogos viven en `ui/guard_dialog.py`, y `BlockedDialog` ni siquiera hereda de algo que tenga botón de aceptar.

## 5. Dónde se aplica y dónde se decide

- **Se aplica** en `ui/tab_panel.py::_run`, que es el único punto por el que pasan las dos formas de ejecutar —el botón Ejecutar y el ▶ del buscador—. Ponerlo en el panel de parámetros dejaría el segundo camino sin red.
- **Se decide** en la sección Seguridad del panel derecho, no entre los parámetros: un seguro que se quita en el mismo gesto con el que se aprieta Ejecutar se vuelve parte del gesto, y a las dos semanas se quita sin leerlo.
- **Se ve** en la barra de estado: un candado por objetivo, abierto o cerrado, y un clic salta a la sección. El indicador lee el panel, la misma fuente que consulta el guard, para que no puedan decir cosas distintas.

## 6. La confirmación escrita

`ctx.confirm(..., expect="TEXTO")` abre un campo de texto en vez de un sí/no: hay que escribir exactamente eso para que la acción corra ([11](11_ejecucion_de_tareas.md) §3). Hoy la usa **una sola** capacidad, `purge_emulators`, con la palabra `BORRAR` — que es justamente la que se queda fuera del seguro por repo, por ser de la máquina.

El resto de los destructivos no pide escribir nada: o quedan bloqueados, o muestran el recordatorio con el repo a la vista.

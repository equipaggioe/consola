# El seguro de los destructivos — por repo y por tipo de objetivo

## 1. El error que se busca atajar

No es "apreté un botón sin querer". Es **apreté el botón correcto en el repo equivocado**.

La interfaz se ve igual en todos los repos. La identidad del repositorio activo vive en una pestaña
pequeña arriba y en un nombre en la barra de estado, y cuando estás metido en el trabajo no vuelves
a leer ninguna de las dos. Ese es el fallo real.

## 2. Dos respuestas, según el seguro del repo

El seguro no pide escribir nada — ni una palabra mágica, ni el nombre del repo. Hace una de dos
cosas, y cuál depende de si el objetivo que la acción va a tocar está protegido **en este repo**:

| Estado del objetivo | Qué pasa | Diálogo |
|---|---|---|
| **Protegido** | La acción **no corre**. Se explica qué objetivo la frena y por qué. No hay botón para continuar igual. | `BlockedDialog` |
| **No protegido** | Recordatorio de sobre qué repo se está trabajando. `Cancelar` / `Continuar`, y `Continuar` no es el predeterminado. | `ReminderDialog` |
| **Simulacro / nada que romper** | Corre sin preguntar. | — |

> Un seguro que se puede quitar en el mismo gesto con el que se aprieta Ejecutar no es un seguro. Por
> eso, cuando el objetivo está protegido, el diálogo **informa y cierra** — para levantarlo hay que
> ir a la sección Seguridad, una vez, con la cabeza fría.

La versión anterior pedía teclear el nombre del repo para continuar. Se descartó: cualquier
confirmación escrita que se repite entrena un reflejo, y un reflejo que se puede ejecutar sin pensar
no comprueba nada. Si el objetivo importa lo bastante como para pedir permiso, importa lo bastante
como para bloquearlo hasta que se desactive el seguro aparte.

## 3. Qué se protege: el objetivo, no el botón

El interruptor no es por acción sino por **tipo de objetivo** (`core/protection.py`), porque el
radio de daño es lo que importa y no coincide con los botones:

| Objetivo | Clave | Por defecto | Por qué |
|---|---|---|---|
| VPS | `vps` | protegido | alcanza una máquina remota, no hay deshacer |
| Base de datos | `db` | protegido | los datos borrados no vuelven sin backup |
| Otros repositorios | `otros_repos` | protegido | escribe fuera de este repo, en carpetas que no miras |
| Publicación | `publicacion` | protegido | lo promovido queda a la vista de los usuarios |
| Archivos locales | `local` | **libre** | un artefacto borrado se rehace con un build |

Dos cosas que un seguro por botón no podría expresar:

- **Un botón toca varios objetivos.** `clean_vps` borra el servidor **y** la base.
- **Un botón cambia de objetivo según sus parámetros.** `teardown_db` contra `local` no sale de esta
  máquina; contra `remoto` alcanza al VPS. El mismo botón, dos radios de daño.

**Un simulacro no dispara nada.** `clean_artifacts` en modo `simulacro` y `sync_common_files` en modo
`simulacro` no destruyen. `targets_of()` devuelve vacío y la acción corre sin diálogo.

`purge_emulators` queda fuera: es `scope='machine'` (borra AVDs e imágenes del SDK, que no son de
ningún repo), así que un interruptor por repositorio no tendría a qué repositorio pertenecer.
Conserva su propia confirmación escrita (`ctx.confirm(expect='BORRAR')`).

## 4. Dónde vive el interruptor, y por qué ahí

En su **propia sección del panel derecho**, **no** en el panel de parámetros de la acción.

Es la decisión de diseño que sostiene todo lo demás. Un seguro que se quita con el mismo gesto con el
que se aprieta Ejecutar —una casilla "desbloquear" al lado del botón— se vuelve parte del gesto, y a
las dos semanas se quita sin leerlo. Aquí se decide **una vez**, cuando das de alta el repo.

### Y en qué archivo: `params.json`, no `config.env`

Estuvieron un tiempo en `.consola/config.env`, como cinco claves `PROTECT_*` del esquema de
`core/settings.py`. Estaba mal y se corrigió: **`config.env` son los datos que las tareas necesitan
para trabajar** —la IP del VPS, el usuario, el token, las rutas de los certificados— y **ningún paso
lee jamás un seguro**. Quien los mira es la consola, antes de dejar correr. Son de la misma familia
que los pasos que quedan marcados en el panel de una acción, así que viven en el mismo archivo que
ellos: `.consola/params.json`, bajo la clave `@protection` (`ui/params_store.py::load_protection`,
`docs/parametros-persistentes.md §2`).

Eso arregla además algo visible: la sección Seguridad **no tiene botón Guardar**, porque tocar una
casilla la guarda, igual que en el panel de parámetros.

Se dibujan como **casillas** y no como campos de texto: escribir `1` a mano en un seguro es pedir que
se escriba mal. Sin texto explicativo al lado — la etiqueta ya dice qué protege y el detalle vive en
el tooltip.

## 5. Dónde se aplica

En `TabPanel._guard_ok`, llamado desde `TabPanel._run`. Ese es el **único** punto por el que pasan
las dos formas de ejecutar: el botón Ejecutar del panel y el botón ▶ del rail (`quick_run`). Ponerlo
en `ParamsPanel` habría dejado el segundo camino sin red.

La decisión la toma `core/protection.py`:

```python
decision, targets = protection.decide(security_panel.state(), capability.id, payload)
if decision == protection.Decision.BLOCK:
    BlockedDialog(project, capability.name, targets).exec()   # informa y cierra
    return False
if decision == protection.Decision.REMIND:
    return ReminderDialog(project, capability.name, targets).exec() == Accepted
return True   # ALLOW
```

Las compuestas destructivas (`rebuild_db`, `teardown_db`, `reinit_migrations`, `clean_vps`,
`promote_app`, `revoke_ssh`, `sync_common_files`) **ya no llevan su propia** `ctx.confirm(expect=...)`:
la única puerta es el guard de la consola. Correrlas sin UI (un test, un `TaskContext` sin
`ask_sink`) ya no las frena — frenarlas es trabajo de quien las lanza.

## 6. Los diálogos

Los dos muestran la identidad del repo en grande, con su color, su icono y **su ruta completa** — el
dato exacto que se da por sabido cuando uno se equivoca de pestaña.

- **`BlockedDialog`** — dice qué se iba a destruir, lista cada objetivo protegido con el motivo de su
  default, y termina en un solo botón `Entendido` que cierra. No hay forma de continuar. La nota al
  pie dice dónde se quita el seguro.
- **`ReminderDialog`** — dice qué se va a destruir y sobre qué repo. `Cancelar` es el botón
  predeterminado; `Continuar` nunca lo es, para que un Enter de más no destruya nada.

## 7. Encontrar los interruptores: el indicador de la barra de estado

Los cinco seguros viven en la sección Seguridad del panel derecho (§4).

- **Seguridad es una sección propia del acordeón del panel derecho** (`ui/widgets/accordion.py`),
  hermana de Parámetros y de Configuración. Se puede plegar, y plegada sigue diciendo lo suyo: su
  cabecera lleva el resumen «*n* de 5 protegidos».
- **La barra de estado inferior** lleva un indicador con lo que el repo activo tiene protegido ahora
  mismo: `🔒 VPS · BD · otros repos` o, si no protege nada, `🔓 sin seguros` en ámbar.
- **Un widget propio, `ui/security_panel.py`**, con su propio archivo detrás.

El indicador y el guard leen **la misma fuente**, `SecurityPanel.state()`, vía la señal `changed`. Un
clic en el indicador llama a `TabPanel.reveal_security()`, que despliega la sección.

## 8. Archivos

| Archivo | Qué hace |
|---|---|
| `core/protection.py` | los objetivos, qué rompe cada acción, cómo lo modulan sus ejes, `decide()`, `state_from()` y `repo_protections()` |
| `ui/security_panel.py` | las cinco casillas de la sección Seguridad; guarda al tocarlas |
| `ui/params_store.py` | `load_protection()` / `save_protection()`: la clave `@protection` de `params.json` |
| `ui/widgets/accordion.py` | la sección plegable con su cabecera y su resumen |
| `ui/guard_dialog.py` | `BlockedDialog` (informa y cierra) y `ReminderDialog` (Cancelar / Continuar) |
| `ui/tab_panel.py` | `TabPanel._guard_ok` en el punto único de ejecución; el acordeón del panel derecho; `WorkspaceStatusBar` lleva el indicador |
| `ui/main_window.py` | conecta el indicador al repo activo y al clic (`_refresh_protection`, `_on_security_clicked`) |

Añadir un objetivo nuevo es una fila en `TARGETS` y una en `RULES`.

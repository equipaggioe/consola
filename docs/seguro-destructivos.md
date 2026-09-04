# El seguro de los destructivos — por repo y por tipo de objetivo

## 1. El error que se busca atajar

No es "apreté un botón sin querer". Es **apreté el botón correcto en el repo equivocado**.

La interfaz se ve igual en todos los repos. La identidad del repositorio activo vive en una pestaña
pequeña arriba y en un nombre en la barra de estado, y cuando estás metido en el trabajo no vuelves
a leer ninguna de las dos. Ese es el fallo real, y define qué tiene que hacer el seguro: **no
frenarte, sino comprobar que sabes dónde estás.**

## 2. Por qué una palabra mágica no sirve

Consola ya pedía confirmación escrita en tres sitios, de dos maneras distintas, y solo una funciona:

```python
# core/tasks/emulators.py — no comprueba NADA
ctx.confirm('Escribe BORRAR para eliminar...', expect='BORRAR')

# core/tasks/database.py — sí comprueba
ctx.confirm(f'Escribe {name} para reconstruir la base', expect=name)
```

La diferencia:

> Un seguro cuya respuesta correcta **es la misma siempre** entrena un reflejo que siempre acierta.
> Un seguro cuya respuesta correcta **depende de dónde estás** entrena un reflejo que solo acierta si
> estás donde crees.

Teclear `BORRAR` es correcto en cualquier repositorio: el automatismo nunca falla, así que la
comprobación no comprueba nada. Teclear `navetta` solo es correcto en navetta — si te confundiste de
pestaña, tus dedos escriben el nombre del repo que **crees** tener abierto y la acción no corre.

**El reflejo no degrada esta comprobación: el reflejo es lo que la hace funcionar.** Es la respuesta
al miedo razonable de que todo seguro acaba siendo mecánico.

## 3. Qué se protege: el objetivo, no el botón

El interruptor no es por acción sino por **tipo de objetivo** (`core/protection.py`), porque el
radio de daño es lo que importa y no coincide con los botones:

| Objetivo | Clave | Por defecto | Por qué |
|---|---|---|---|
| VPS | `PROTECT_VPS` | protegido | alcanza una máquina remota, no hay deshacer |
| Base de datos | `PROTECT_DB` | protegido | los datos borrados no vuelven sin backup |
| Otros repositorios | `PROTECT_OTHER_REPOS` | protegido | escribe fuera de este repo, en carpetas que no miras |
| Publicación | `PROTECT_RELEASE` | protegido | lo promovido queda a la vista de los usuarios |
| Archivos locales | `PROTECT_LOCAL` | **libre** | un artefacto borrado se rehace con un build |

Dos cosas que un seguro por botón no podría expresar:

- **Un botón toca varios objetivos.** `clean_vps` borra el servidor **y** la base.
- **Un botón cambia de objetivo según sus parámetros.** `teardown_db` contra `local` no sale de esta
  máquina; contra `remoto` alcanza al VPS. El mismo botón, dos radios de daño.

**Un simulacro no dispara nada.** `clean_artifacts` en modo `simulacro` y `sync_common_files` en modo
`simulacro` no destruyen. Preguntarles sería justo el ruido que gasta la señal del aviso de verdad.

`purge_emulators` queda fuera: es `scope='machine'` (borra AVDs e imágenes del SDK, que no son de
ningún repo), así que un interruptor por repositorio no tendría a qué repositorio pertenecer.

## 4. Dónde vive el interruptor, y por qué ahí

En **la configuración del repo** (`.consola/config.env`, sección Seguridad del panel), **no** en el
panel de parámetros.

Es la decisión de diseño que sostiene todo lo demás. Un seguro que se quita con el mismo gesto con el
que se aprieta Ejecutar —una casilla "desbloquear" al lado del botón— se vuelve parte del gesto, y a
las dos semanas se quita sin leerlo. Un reflejo necesita repetición para formarse.

Aquí se decide **una vez**, cuando das de alta el repo, y queda escrito en un archivo que puedes
`grep`ear. Un interruptor que se toca cada varios meses no llega a ser reflejo. Lo que **sí** se
repite es la confirmación escrita, y esa verifica identidad.

Se dibujan como interruptores y no como campos de texto (`Setting.kind='bool'`,
`ui/env_panel.py`): escribir `1` a mano en una casilla de seguridad es pedir que se escriba mal.

## 5. Dónde se aplica

En `TabPanel._guard_ok`, llamado desde `TabPanel._run`. Ese es el **único** punto por el que pasan
las dos formas de ejecutar: el botón Ejecutar del panel y el botón ▶ del rail (`quick_run`). Ponerlo
en `ParamsPanel` habría dejado el segundo camino sin red.

La pregunta que se hace no es "¿es destructivo?" sino "¿qué rompe **con estos parámetros**, y está
protegido **en este repo**?":

```python
config  = envfile.Config(self.env_panel.values(), repo_name=...)
targets = protection.protected(config, capability.id, payload)
if targets:
    # GuardDialog: pide el nombre del repo
```

## 6. El diálogo

- Dice **qué** se destruye ("Limpiar VPS va a destruir el VPS y la base de datos").
- Muestra el repo con su color, su icono y **su ruta completa** — el dato exacto que se da por sabido
  cuando uno se equivoca de pestaña.
- El campo arranca vacío, sin autocompletado, y **no repite el nombre que hay que escribir**: si se
  pudiera copiar de la propia caja, volvería a ser una palabra mágica.
- El botón destructivo **nunca es el predeterminado**: un Enter de más no destruye nada.
- Si escribes el nombre de **otra pestaña abierta**, lo dice: *«navetta es otra pestaña. Esta acción
  corre sobre vettore.»* Es el aviso más útil del diálogo — no dice "te equivocaste de palabra", dice
  "te equivocaste de repositorio", que es el error que todo esto existe para atajar.

## 7. Archivos

| Archivo | Qué hace |
|---|---|
| `core/protection.py` | los objetivos, qué rompe cada acción y cómo lo modulan sus ejes |
| `core/settings.py` | `_protection_settings()` deriva un `Setting` por objetivo; `kind='bool'` |
| `ui/env_panel.py` | los `kind='bool'` se dibujan como interruptor |
| `ui/guard_dialog.py` | la confirmación escrita |
| `ui/tab_panel.py` | `_guard_ok`, en el punto único de ejecución |

Añadir un objetivo nuevo es una fila en `TARGETS` y una en `RULES`: la clave de configuración, su
valor por defecto y qué acciones lo tocan salen todos de la misma tabla.

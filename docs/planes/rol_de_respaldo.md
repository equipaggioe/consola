# Plan — preparar cada VPS para los respaldos del monitor de Equipaggio

> **Estado (verificado 2026-09-28).** No hay nada construido.
>
> **Decidido el 2026-09-28:** el monitor de Equipaggio respalda las bases de todos los repos
> (plan `respaldos.md` de `equipaggio`) con un rol propio de solo lectura. Consola lo crea, con el
> mismo nombre y la misma contraseña en todos los repos. Lo demás es propuesta.

## 1. Qué hace

Un botón «Preparar respaldo del monitor» que deja el VPS del repo listo para que el monitor lo
respalde. Corre por los canales de siempre: `database.Admin` para el rol
([16](../arquitectura/16_base_de_datos.md), §1) y SSH para la llave.

| Paso | Qué hace |
|---|---|
| Rol | Crea el rol de respaldo si falta y le fija la contraseña, como `create_role` con el rol de la aplicación |
| Permisos | Le da `pg_read_all_data` *(propuesta)*: lee todas las tablas, también las que agreguen las migraciones de después, sin volver a correr el botón |
| Llave del monitor | Agrega la llave pública del monitor al VPS, limitada al túnel hacia Postgres y a consultar el disco *(propuesta)* |

## 2. Configuración *(propuesta)*

Las tres claves son iguales para todos los repos, así que van con `scope='machine'` en `QSettings`,
no en el `config.env` de cada repo ([13](../arquitectura/13_configuracion_y_persistencia.md), §1):

| Clave | Qué dice |
|---|---|
| `BACKUP_ROLE` | Nombre del rol de respaldo |
| `BACKUP_ROLE_PASSWORD` | Su contraseña. `secret` |
| `MONITOR_SSH_PUBLIC_KEY` | La llave pública con la que entra el monitor |

Ninguna tiene valor por omisión: sin ellas el botón queda en ámbar.

## 3. Borrado

`teardown_db` no borra el rol de respaldo: no es dueño de nada, y `pg_read_all_data` lo hace servir
a cualquier base de ese servidor *(propuesta)*.

## 4. Preguntas abiertas

1. **¿El botón va también dentro de `bootstrap_db`?** Una base creada sin él no se respalda hasta
   que alguien lo presiona.

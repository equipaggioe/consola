# Plan — los botones de base contra un VPS de canone en desarrollo

> **Estado (verificado 2026-11-07).** Decidido: las decisiones están en el §6. Las fases 1 a 3 están
> en `main` de canone (ADR-0127 y ADR-0128 de canone); `deploy.sh`,
> `install.sh` y `backup.sh` pasan en un Debian 13 con `systemd-nspawn`.
> Falta la fase 4. Hoy el ámbito
> remoto de «Reconstruir base», «Borrar base y rol», «Reiniciar historial de migraciones», los
> seeders, «Habilitar extensiones», «Explorar datos» y «Abrir túnel a Postgres» corta contra un VPS de
> canone ([30](../arquitectura/30_riesgos_y_pendientes.md), «Decididos y sin construir»). Lo que hay está en
> [16](../arquitectura/16_base_de_datos.md) y [15](../arquitectura/15_vps_y_despliegue.md); si este
> plan no coincide con ellos, mandan ellos.
>
> **Para retomar en otro chat:** leer `canone/principios.md`, `canone/documentacion.md`,
> `canone/plataformas/despliegue.md` («PostgreSQL», «Versiones») y este plan. Lo que sigue es construir
> la fase 4.

## 1. Objetivo

- En desarrollo, el esquema cambia mucho y las migraciones se acumulan. De vez en cuando se juntan
  todas en una inicial, también en el VPS de desarrollo.
- Producción arranca con una sola migración inicial: ninguna intermedia que nunca protegió datos.
- Los botones de base sirven también contra el VPS de desarrollo.
- Ninguno puede borrar una base de producción.

## 2. Por qué hoy no funciona

Lo dice el [15](../arquitectura/15_vps_y_despliegue.md) §2: lo que deja un cambio permanente en un VPS
lo hace un programa de canone. Para la base, canone solo trae `install.py`, que la crea, y `deploy.py`,
que migra. Además:

| Botón | Qué hace hoy en remoto | Por qué no sirve en un VPS de canone |
|---|---|---|
| Reconstruir base (`rebuild_db`) | Borra tablas, migra y siembra con el Python de `VPS_DEPLOY_DIR` | Esa carpeta no existe. Si existiera, las tablas quedarían de otro rol y `<app>` sin permisos *(sin confirmar)* |
| Borrar base y rol (`teardown_db`) | `DROP DATABASE` y `DROP ROLE` de `DB_USER` | Los roles los crea `install.py`. Con la base borrada, `deploy.py` no migra la versión activa y el servidor queda sin tablas *(sin confirmar)* |
| Reiniciar historial (`reinit_migrations`) | Vacía la base del ámbito y reescribe `alembic/versions/` | La base del VPS conserva en `alembic_version` una revisión que deja de existir: el próximo despliegue con migraciones falla *(sin confirmar)* |
| Seeders | Corre `seeders.` con el Python del repo desplegado | Igual que «Reconstruir base», y la plantilla de canone no tiene seeders |
| Habilitar extensiones | `CREATE EXTENSION` como superusuario por `sudo -n` | `install.py --extension` ya lo hace, y `sudo -n` pide contraseña |
| Explorar datos, Abrir túnel | Túnel TCP al 5432 con contraseña | Los roles entran por `peer` y no tienen contraseña |

## 3. Lo que se agrega a canone

Un programa nuevo que `install.py` instala junto a `deploy.py`, por ejemplo
`/usr/local/lib/<app>/database.py`, con su prueba en `infra.yml`.

| Comando | Qué hace |
|---|---|
| `database.py empty` | Detiene `<app>.service`, borra la base y la crea otra vez como `install.py`: dueño `<app>_owner`, permisos de `<app>`, las mismas extensiones. La deja **vacía y sin migrar** |
| `database.py migrate` | Migra la versión activa con `<app>-migrate@<versión>` y arranca el servidor |
| `database.py seed [--mock]` | Corre los seeders como el dueño del esquema, en una unidad como la de las migraciones. Sin `--mock`, lo que tiene que haber en todo entorno; con `--mock`, los datos de ejemplo, y falla sin la marca de desarrollo (pregunta 1) |

Y en `install.py`, un rol de solo lectura:

- `<app>_read`, con `SELECT` sobre lo que crea `<app>_owner` (`ALTER DEFAULT PRIVILEGES`).
- Un mapa de `pg_ident.conf` que deja entrar a la cuenta que administra solo como `<app>_read`, por
  `peer`.

`empty` no migra porque, al juntar las migraciones, la versión activa todavía tiene el historial
viejo: migrarla dejaría `alembic_version` en una revisión que la versión nueva no conoce, y su
despliegue fallaría, como pasó en el CI de canone el 2026-11-06 con `v1.2.0`.

## 4. Lo que cambia en Consola

| Botón | Contra el VPS de desarrollo |
|---|---|
| Reconstruir base | `empty` → `migrate` → `seed`, con una casilla por paso |
| Borrar base y rol | Sin ámbito remoto: `empty` cubre el caso, y los roles son de `install.py` |
| Reiniciar historial | Solo en local, sin ámbito |
| Habilitar extensiones | Sin ámbito remoto |
| Correr seeders | `seed` |
| Correr mock seeders | `seed --mock` |
| Explorar datos, Abrir túnel | Túnel al socket del VPS (`ssh -L <puerto>:/run/postgresql/.s.PGSQL.5432`), entrando como `<app>_read` |

Los comandos de `database.py` corren por `vps_setup.Access`, con `sudo -S`, como `deploy.py`.

### Juntar las migraciones

1. En local, «Reiniciar historial».
2. Commit, a mano.
3. «Publicar versión», sin el paso de desplegar.
4. En el VPS, `database.py empty`.
5. «Desplegar versión»: los heads cambiaron, así que `deploy.py` migra desde la base vacía.
6. `database.py seed`, si se quiere.

Los pasos 3 a 6 pueden ser una compuesta; el 1 y el 2 no, porque el commit es de quien desarrolla.

### Entrar a producción

En una máquina nueva, `install.py` crea la base vacía y el primer despliegue aplica la inicial y
corre los seeders (pregunta 6). Si el VPS de desarrollo pasa a producción, se junta el historial con el flujo de
arriba y después se quita la marca de desarrollo (pregunta 4).

## 5. Fases

1. **Canone:** `database.py` con `empty` y `migrate`, la marca de desarrollo y su prueba en `infra.yml`.
2. **Canone:** el rol `<app>_read` y su mapa, con su prueba.
3. **Canone:** la convención de los seeders, `seed`, y que `deploy.py` los corra después de migrar,
   en la misma transacción: un seeder que falla deshace las migraciones y vuelve la versión anterior
   (pregunta 7).
4. **Consola:** los botones del §4 y el flujo de juntar migraciones. El 16 y el 30 se actualizan en el
   mismo commit.

## 6. Decisiones

Las preguntas 1 a 6 son del 2026-11-06, y la 7, del 2026-11-07.

| # | Pregunta | Decisión |
|---|---|---|
| 1 | ¿Cómo impide `empty` borrar una base de producción? El VPS no conoce el estado del `README.md`, y el seguro de Consola es por repo: abierto para trabajar en desarrollo, no distingue el VPS de desarrollo del de producción, ni cubre a quien corre el programa por `ssh` | `install.py --development` deja una marca en `/etc/<app>/`, y `empty` y `seed --mock` fallan sin ella. Es lo que hace Rails desde la versión 5: guarda el entorno junto a la base y sus tareas destructivas se niegan en producción. Además, Consola bloquea el botón si el `README.md` dice `Estado: en producción` |
| 2 | ¿`empty` borra los archivos subidos? | Sí, `/var/lib/<app>/files/` también, porque los archivos apuntan a filas que dejan de existir |
| 3 | ¿Dónde viven los datos que hoy siembran los seeders? Hoy son una convención de Consola (`seeders.` y `mock_data/`), y la plantilla de canone no tiene ninguno | En seeders, como en Rails y Laravel, separados en dos. Los **seeders**: lo que tiene que haber en todo entorno, idempotentes (volver a correrlos no duplica filas), también en producción. Los **mock seeders**: datos de ejemplo, solo en desarrollo, frenados por la marca de la pregunta 1. Fuera de las migraciones, porque juntar el historial los borraría; Django es el único que pone los datos iniciales en migraciones |
| 4 | ¿Cómo se quita la marca al pasar a producción? | `install.py` sin `--development` la borra |
| 5 | ¿Un programa aparte o comandos de `deploy.py`? | Aparte: `deploy.py` instala versiones, y vaciar la base es otra intención |
| 6 | ¿Quién corre `seed` en producción? | `deploy.py`, después de migrar, ya que los seeders son idempotentes. Así una máquina nueva no queda sin los datos que necesita |
| 7 | ¿Qué hace `deploy.py` si un seeder falla? | Los seeders corren en la transacción de las migraciones (`python -m app.tasks migrate`): un seeder que falla las deshace, y `deploy.py` borra la versión y vuelve la anterior, como cuando falla una migración |

## 7. Sin verificar

- Que `peer` funcione por un túnel al socket en un VPS real. En `systemd-nspawn` funciona: el
  `deploy.sh` de canone entra como `<app>_read` por `ssh -L` al socket, y como `<app>_owner` no.

## 8. Al terminar

Las decisiones pasan a ADR en canone y en Consola, el resultado al 16 y al
[15](../arquitectura/15_vps_y_despliegue.md), salen los puntos del 30 y se borra este plan.

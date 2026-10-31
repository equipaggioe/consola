# ADR-0062 · «Vaciar VPS» sale hasta que canone traiga el programa que desinstala

- **Estado:** Propuesta
- **Fecha:** 2026-10-31
- **Alcance:** core/catalog.py, core/tasks/vps_ops.py, core/protection.py, core/settings.py

## Contexto

«Vaciar VPS» deshacía lo que ponía el despliegue propio. Después del [ADR-0059](0059-desplegar-con-los-programas-de-canone.md) le quedaban cinco pasos, y contra un VPS instalado con canone ninguno sirve:

| Paso | En un VPS de canone |
|---|---|
| Borrar base de datos | Busca `DB_NAME`, que por omisión es `<repo>_db`, y canone crea `<app>`. Entra por SSH como `postgres` a una base que no es la suya |
| Borrar repo desplegado | No hay clon: no hace nada |
| Revocar llave de GitHub | No hay deploy key: no hace nada |
| Purgar paquetes apt | Quita `postgresql`, `caddy` y `coturn` y deja a medias lo que instaló `install.py` |
| Borrar usuario de despliegue | Borra `VPS_USER`, que es la cuenta de `--admin`. Root no entra por SSH: la máquina queda sin entrada |

En un VPS con el despliegue propio, como el de `pze`, todavía funcionaría, pero ese VPS ya no tiene botones de despliegue, y dejar una máquina «como recién formateada» lo hace mejor el proveedor reinstalando la imagen.

## Decisión

1. **«Vaciar VPS» (`clean_vps`) sale**, con sus atómicas: `remove_deployed_repo`, `uninstall_packages`, `remove_vps_user`, `remove_remote_key_files` y `revoke_github_key`, y `core/github.py`.
2. **Sale `GITHUB_KEY_TITLE`**, que solo leía el paso de la llave de GitHub.
3. **El reemplazo espera a que canone traiga un programa que desinstale** lo que instala `install.py`. Ese botón no borra la cuenta que administra ni `00-<app>.conf`.

## Consecuencias

- Desarmar un VPS es reinstalarlo desde el panel del proveedor.
- El objetivo `vps` del seguro lo siguen tocando «Quitar acceso SSH» y el ámbito remoto de «Reconstruir base» y «Borrar base y rol».

## Descartado

- **Dejarlo sin los pasos que dañan.** Quedarían tres pasos que en un VPS de canone no hacen nada, bajo un nombre que promete vaciar la máquina.
- **Adaptarlo a canone en Consola.** Sería reimplementar la reversa de `install.py`, que el ADR-0059 deja a canone.

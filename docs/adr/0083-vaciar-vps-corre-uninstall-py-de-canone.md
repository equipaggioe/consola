# ADR-0083 · «Vaciar VPS» vuelve y corre `uninstall.py` de canone, en tres niveles

- **Estado:** Aceptada
- **Fecha:** 2026-11-09
- **Alcance:** core/catalog.py, core/tasks/vps_setup.py, core/protection.py, core/settings.py,
  core/command_docs.py

## Contexto

El [ADR-0062](0062-vaciar-vps-sale.md) quitó «Vaciar VPS» porque reimplementaba la reversa de
`install.py` y dañaba un VPS de canone, y dejó el reemplazo para cuando canone trajera el programa
que desinstala. Canone lo trae: `uninstall.py` (ADR-0134 de canone).

## Decisión

1. «Vaciar VPS» (`clean_vps`) sube `plantilla/infra/` de `CANONE_DIR` y corre
   `uninstall.py <app> <nivel>`. Consola no borra nada por su cuenta.
2. El nivel es un eje: «La base» (`database`), «La app» (`app`) y «La máquina»
   (`machine`). Cada uno incluye al anterior, y el valor por defecto es el menor.
3. Es un destructivo con los objetivos `vps` y `db` del seguro, y su simulacro corre
   `uninstall.py --dry-run`, que lista lo que haría.
4. Entra por la cuenta que administra, con `sudo`: ningún nivel la toca y `root`
   sigue bloqueado.

## Consecuencias

- Volver a empezar un VPS ya no pide reinstalarlo desde el proveedor: «Vaciar VPS» con «La
  máquina» y después «Configurar VPS», que no reinstala los paquetes. Para dejarlo como lo entrega
  el proveedor, se reinstala desde su panel y después «Configurar VPS».
- Después de «La base», el servidor queda detenido hasta volver a correr «Configurar VPS».

## Descartado

- **Reimplementar la reversa en Consola:** es lo que el ADR-0062 quitó; un cambio permanente en el
  VPS lo hace un programa de canone.
- **Purgar los paquetes:** se llevaba paquetes de la imagen que arman la red y dejan bajar de apt
  (ADR-0134 de canone).

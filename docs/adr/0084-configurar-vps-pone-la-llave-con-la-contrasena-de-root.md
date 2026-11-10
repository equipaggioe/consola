# ADR-0084 · «Configurar VPS» pone la llave con la contraseña de root

- **Estado:** Aceptada
- **Fecha:** 2026-11-09
- **Alcance:** core/tasks/vps_setup.py, core/ssh.py, core/host.py, core/catalog.py, core/settings.py,
  core/command_docs.py

## Contexto

«Configurar VPS» entraba como root con la llave `VPS_KEY_NAME` y la creaba recién en «Instalar
infraestructura», después de los pasos que ya la usaban. Un VPS recién creado que solo acepta la
contraseña de root del proveedor no se podía configurar sin crear la llave y copiarla a mano.

## Decisión

1. «Configurar VPS» empieza por «Poner la llave» (`install_key`): crea `~/.ssh/<VPS_KEY_NAME>` si
   falta y, si la llave no entra ni como `VPS_USER` ni como root, entra una vez como root con su
   contraseña, sube `authorize.py` de canone y lo corre con la llave (ADR-0135 de canone).
2. La contraseña sale de `ROOT_PASSWORD` de `config.env` y, si está vacía, se pide.
3. `scp` y `ssh` la reciben por `SSH_ASKPASS`, con `SSH_ASKPASS_REQUIRE=force`: un script que la
   imprime desde el entorno (`HOST.askpass`). No va en un argumento, en un archivo ni en el log.

## Consecuencias

- Un VPS nuevo se configura con su IP, la contraseña de root y «Configurar VPS».
- Después de `install.py`, root no entra y `ROOT_PASSWORD` deja de servir.

## Descartado

- **Que Consola escriba `authorized_keys` por su cuenta:** lo que deja un cambio permanente en el
  VPS lo hace un programa de canone (ADR-0074).
- **`sshpass` o paramiko:** uno no está en Windows y el otro es una dependencia nueva para una sola
  conexión; `SSH_ASKPASS` funciona en el OpenSSH de Windows 9.5 y en el de Linux.
- **`echo %VARIABLE%` en el `.cmd`:** cmd expande `%`, `^`, `&` y `!` de la contraseña.

# ADR-0066 · «Configurar VPS» prepara la máquina y corre `install.py`; root entra solo la primera vez

- **Estado:** Aceptada
- **Fecha:** 2026-10-31
- **Alcance:** core/tasks/vps_setup.py, core/canone.py, core/process.py, core/ssh.py, core/catalog.py, core/settings.py

## Contexto

canone deja a quien prepara la máquina sus paquetes, uv y tanto swap como memoria; `install.py` falla si faltan (despliegue.md de canone, «Máquina»). La primera vez `install.py` corre como root, crea la cuenta que administra, pide su contraseña dos veces por consola y deja a root sin entrada por SSH. Después se corre con `sudo` desde esa cuenta, que pide la contraseña (ADR-0084 y 0087 de canone). `credentials.py` no lo instala `install.py`.

El aprovisionamiento propio de Consola creaba una cuenta con `sudo` sin contraseña y entraba como root con contraseña por `SSH_ASKPASS` (`setup_ssh_key`). Contra canone las dos cosas sobran o chocan.

## Decisión

1. **«Configurar VPS» encadena paquetes y uv → swap → `install.py` → credenciales.** Cada paso detecta lo que ya está, así que se puede volver a correr para reinstalar (ADR-0106 de canone). «Instalar paquetes base» y «Cargar credenciales» tienen además botón propio.
2. **Se entra por la cuenta de `VPS_USER` si la llave ya la deja entrar; si no, por root** con la misma llave, `VPS_KEY_NAME`, puesta al crear el VPS (`vps_setup.access`).
3. **Con la cuenta, todo lo que pide root va por `sudo -S`**, con la contraseña por stdin. Sale de `SUDO_PASSWORD` o se pide una vez por sesión y vive solo en memoria (`core/session.py`).
4. **La primera corrida de `install.py` va por `ssh -tt`, y la contraseña se escribe recién cuando aparece cada pregunta** («Password of», «Again»): escrita antes, la terminal remota la repite en el log y `getpass` la descarta (`process.converse`).
5. **Los argumentos de `install.py` salen de `config.env` y del repo** (`canone.install_args`): `--owner` y `<app>` de `git remote get-url origin`, `--desktop` de cada `desktop-<sistema>` del `release.yml`, `--without` de las carpetas `web/`, `panel/` y `landing/` que faltan, y las dos llaves —la de `VPS_KEY_NAME` y `OFFLINE_KEY`— como `--key` y `--signer`.
6. **Los paquetes salen del repo, sin eje**: los de la máquina de canone, más PostGIS si `DB_EXTENSIONS` la nombra, coturn con `TURN` y lo del journal con `LOGS`.
7. **El swap es un `/swapfile`** con lo que falta para igualar la memoria, en `/etc/fstab`.
8. **Los programas se suben de la copia local de canone** (`CANONE_DIR`, de la máquina) a `/tmp/consola-canone`, que se borra al terminar.
9. **Sale «Crear usuario y acceso SSH» (`setup_ssh_key`)** con el `sudo` sin contraseña y la contraseña de root por `SSH_ASKPASS`.

## Consecuencias

- Hace falta la segunda llave antes de la primera corrida: con una sola, `install.py` no crea la cuenta.
- La contraseña de la cuenta queda en `config.env` si se escribe en `SUDO_PASSWORD`: quien se lleve esta máquina tiene la llave y la contraseña.
- Que `sudo -S` deje a `credentials.py` el resto de stdin está sin confirmar contra un VPS.

## Descartado

- **Seguir con `setup_ssh_key`.** Crea la cuenta con `sudo` sin contraseña, que el ADR-0084 de canone prohíbe, y deja de servir en cuanto root no entra.
- **Escribir la contraseña de `install.py` antes de que la pida.** Probado el 2026-10-31: la salida la muestra dos veces y el programa queda esperando.

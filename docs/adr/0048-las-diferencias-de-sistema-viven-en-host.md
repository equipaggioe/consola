# ADR-0048 · Las diferencias entre Windows y Linux viven en un solo módulo, con una clase por sistema

- **Estado:** Propuesta
- **Fecha:** 2026-09-23
- **Alcance:** core/host.py, core/process.py, core/ssh.py, core/database.py, core/userenv.py, core/sysinfo.py, core/cache.py, core/catalog.py, core/files.py, core/android.py, core/toolchain.py, core/toolstatus.py, core/db_models.py, core/tasks/utils.py, core/tasks/builders.py, ui/theme.py, ui/console_view.py, ui/db_explorer_view.py, tests/test_host.py

## Contexto

Consola se declaraba para Windows y Linux, y las diferencias estaban repartidas en 32 `if os.name == 'nt'` por trece archivos. Nada corría el código en Linux, así que una pieza escrita solo para Windows entraba sin que nadie lo notara. Leyendo el código aparecieron tres que rompían Linux:

- **Detener una tarea cerraba Consola.** Los hijos de `ctx.run` compartían el grupo de procesos de Consola, y `kill_tree` le mandaba `SIGTERM` a ese grupo. Con «App Python», cada archivo guardado disparaba el relanzado y con él la señal.
- **`pg_tool` solo miraba `C:\Program Files\PostgreSQL`.** El canal de superusuario local, el respaldo y la restauración —estos dos también contra la base remota, porque el volcado corre de este lado ([ADR-0046](0046-el-volcado-corre-de-este-lado.md))— no tenían con qué correr.
- **«SSH Login» no abría ninguna terminal.** En Windows usaba `wt.exe`; en Linux lanzaba `ssh` sin TTY y con `stdin` cerrado.

## Decisión

1. **`core/host.py` es el único lugar que pregunta por el sistema.** `Host` declara cada diferencia como abstracta y `WindowsHost` y `PosixHost` la implementan. `HOST` es la instancia del sistema que corre. A una clase con un abstracto sin implementar no se la puede instanciar en ninguna máquina, así que `tests/test_host.py` detecta desde Windows la pieza de Linux que falta, y al revés.
2. **Una prueba prohíbe `os.name`, `sys.platform` y `platform.system()` fuera de `core/host.py`.** Sin ella la regla dura hasta el próximo `if` escrito deprisa.
3. **Donde un módulo tiene dos implementaciones enteras** —el entorno del usuario, la aceleración del emulador— el host da una clave (`env_store`, `emulator_acceleration`) y el módulo despacha con un diccionario. Las dos implementaciones siguen junto a su lógica, y la elección la sigue tomando el host.
4. **En Linux cada proceso arranca en su propia sesión**, no solo los desacoplados: `kill_tree` mata el grupo del proceso y ese grupo ya no es el de Consola.
5. **Postgres en Linux se busca con las rutas de Debian y Ubuntu**: los binarios en `/usr/lib/postgresql/<versión>/bin` y el puerto en `/etc/postgresql/<versión>/main/postgresql.conf`. Las versiones se ordenan por número en los dos sistemas: como texto, `9.6` quedaba antes que `17`.
6. **La terminal de Linux es `x-terminal-emulator -e`.** Es la alternativa de Debian y la política de Debian obliga a que acepte `-e programa argumentos…`.
7. **La fuente de ancho fijo pide el tipo además de las familias** (`ui/theme.py::mono`), para que una máquina sin Cascadia ni Consolas no caiga en una fuente proporcional.

## Consecuencias

- Agregar algo que difiere entre sistemas es agregar un abstracto a `Host` y las dos implementaciones. No se puede agregar una sola.
- En Linux, `Ctrl+C` en la terminal desde la que se lanzó Consola ya no llega a los hijos. Los apaga el cierre de Consola, como en Windows.
- Un Linux que no sea Debian ni Ubuntu no encuentra Postgres, y lo dice con la ruta que buscó.
- En Linux el canal de superusuario local sigue entrando por TCP con `PG_PASSWORD`. El usuario `postgres` de Debian no trae contraseña, así que hay que ponerle una antes.
- `bind_to_app` no tiene equivalente en Linux todavía: si Consola se cae de golpe, un túnel sigue vivo ([30](../arquitectura/30_riesgos_y_pendientes.md)).
- Nada de esto se corrió en Linux. Las pruebas que necesitan el sistema de verdad se saltan en Windows y quedan listas para correr allí.

## Descartado

- **Arreglar las tres fallas en su lugar.** Es menos código, pero deja las diferencias repartidas y la próxima pieza escrita solo para Windows vuelve a entrar sin aviso.
- **Buscar `psql` también en el PATH.** Dos fuentes para el mismo binario: si falla, no se sabe cuál se usó. En Debian el `psql` del PATH es además un envoltorio que elige la versión por su cuenta.
- **`PR_SET_PDEATHSIG` para que el túnel muera con Consola.** La señal salta cuando termina el hilo que lanzó el proceso, no el proceso entero, y los túneles se lanzan desde el hilo de una tarea: morirían al terminar la tarea. Hace falta lanzarlos desde un hilo que viva lo que vive la aplicación, y eso es otro diseño.

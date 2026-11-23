# Secciones informativas

**Estado (verificado 2026-11-23):** construidas «Deducido» en la columna derecha (paquetes, opciones
fijas y claves por defecto) y, debajo de la consola, «Errores y avisos» y «Comandos»
([12](../arquitectura/12_interfaz.md)). Falta lo de abajo: cada punto necesita datos que hoy no
existen y una decisión.

## Lo que falta

| # | Qué | De dónde saldría | Qué hay que decidir |
|---|---|---|---|
| 1 | En Deducido, el nombre de la app y el dueño | `git remote get-url origin`, como ya lo saca la instalación del VPS | Si se muestra en toda acción del VPS o solo en las que lo usan |
| 2 | En Deducido, la carpeta de despliegue (`vps.deploy_root`) | La configuración, sin consultar nada | Nada: falta saber qué acciones la usan |
| 3 | En Deducido, la memoria de Valkey | `VALKEY_MEMORY`, o la parte de la RAM del VPS que da `VALKEY_PERCENT` | Con porcentaje hay que preguntarle la RAM al VPS por SSH: ¿se pregunta al abrir la pestaña o se muestra solo el porcentaje? |
| 4 | Historial de corridas: fecha, duración, resultado y parámetros | Hoy nada lo guarda | Dónde: `params.json` es del repo y viaja con él; `QSettings` es de la máquina. Cuántas corridas se guardan |
| 5 | Artefactos: ruta, tamaño y abrir la carpeta | Hoy cada tarea escribe la ruta en la consola como texto | Que cada tarea declare lo que deja, con un método nuevo del contexto (`ctx.artifact(path)`) |
| 6 | Procesos vivos: PID, puerto y tiempo arriba | El puerto ya está en el endpoint; el PID no se publica hoy | Si va en la cabecera de la consola, junto al endpoint, o en una sección |

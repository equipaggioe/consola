# Registros de decisión (ADR)

Por qué Consola es como es. Las reglas —cuándo se escribe un ADR, los estados, el formato— están en [`docs/README.md`](../README.md#adr).

La serie se escribió de una vez, al reconstruir la documentación desde el código (2026-09-21): la fecha de cada registro es la de su escritura, no la del día en que se tomó la decisión. Cada punto de cada ADR se puede verificar en el archivo y el símbolo que nombra.

## Índice

| # | Decisión |
|---|---|
| [0001](0001-reimplementar-no-ejecutar-scripts.md) | Los scripts se reimplementan como funciones; el único subproceso es un binario externo |
| [0002](0002-catalogo-declara-tareas-implementan.md) | El catálogo declara la forma de un botón y `core/tasks/` le da cuerpo |
| [0003](0003-contrato-de-nombres.md) | El nombre de un eje y el id de un paso son el nombre del parámetro de la función |
| [0004](0004-un-boton-por-capacidad.md) | Una variación que solo cambia una constante es un eje del panel, no otro botón |
| [0005](0005-todo-pasa-por-taskcontext.md) | El nivel 0 no imprime, no lee stdin y no sale del proceso: informa por su contexto |
| [0006](0006-ejes-descubiertos-y-consultados.md) | Los valores de un eje pueden salir de mirar el repo o de preguntarle a una herramienta |
| [0007](0007-lo-inaplicable-desaparece.md) | Lo que no aplica a este repo desaparece; lo que solo espera un dato queda en ámbar |
| [0008](0008-un-launcher-entrega-un-endpoint.md) | Lo que un launcher entrega es una URL, no su log |
| [0009](0009-estado-de-sesion-en-memoria.md) | Lo que una tarea le deja a otra vive en memoria, no en un archivo del repo |
| [0010](0010-fanout-o-bucle-segun-kind.md) | Un eje de varios valores se reparte en pestañas si la tarea vive, y se recorre en bucle si termina |
| [0011](0011-compuesta-concurrente-sin-cuerpo.md) | La compuesta que levanta un entorno entero no tiene función: su cuerpo es el despachador de la interfaz |
| [0012](0012-el-eje-scope.md) | El ámbito local/remoto cambia contra qué base se apunta, no dónde corre el script |
| [0013](0013-generar-en-local-aplicar-donde-este-la-base.md) | Las migraciones se generan en esta máquina y se aplican del lado que diga el ámbito |
| [0014](0014-extensiones-declaradas.md) | Qué extensiones de Postgres necesita el esquema se declara; no sale de ningún catálogo |
| [0015](0015-explorador-de-solo-lectura.md) | El explorador es de solo lectura, garantizado por el servidor, y vive como tarea viva |
| [0016](0016-siempre-por-tunel.md) | A la base del VPS se llega siempre por un túnel SSH, nunca por su IP pública |
| [0017](0017-datos-en-el-env-decisiones-en-el-json.md) | En `config.env` van los datos que las tareas leen; las decisiones van a `params.json` o a QSettings |
| [0018](0018-seguro-por-repo-y-objetivo.md) | El seguro de los destructivos es por repositorio y por tipo de objetivo, no por botón |
| [0019](0019-tabla-de-rutas-publicas.md) | Bajo qué ruta se publica cada cosa es una tabla ordenada de reglas, y es un dato del despliegue |
| [0020](0020-ruta-publica-no-implica-proxy.md) | Declarar una ruta pública no significa que haya un reverse proxy delante |
| [0021](0021-configuracion-en-etc-no-en-el-repo.md) | La configuración de los servicios se escribe en `/etc` del VPS; en el repo solo queda una copia de referencia |
| [0022](0022-instalar-y-configurar-son-dos-botones.md) | Instalar un paquete y configurar su servicio son dos acciones distintas |
| [0023](0023-los-servicios-son-un-eje.md) | Los tres servicios systemd del VPS son un eje, no tres botones |
| [0024](0024-publicar-escribe-un-manifiesto-de-release.md) | Un artefacto nunca se sube solo: va con su manifiesto de versión y con un manifiesto de release |
| [0025](0025-bump-reversible.md) | Si el build falla, la versión vuelve a lo que era |
| [0026](0026-compilar-es-desmarcable.md) | Se puede subir el artefacto que ya está en disco, sin volver a compilarlo |
| [0027](0027-emuladores-tres-actividades.md) | Instalar la máquina virtual, crear el AVD y arrancarlo son tres botones con dos catálogos |
| [0028](0028-apagar-es-cerrar-la-pestana.md) | Apagar un emulador es cerrar su pestaña; el inventario del panel es para los huérfanos |
| [0029](0029-entorno-a-nivel-usuario.md) | Las variables y el PATH se escriben a nivel usuario, en un bloque delimitado |
| [0030](0030-cache-de-catalogo-no-de-estado.md) | Se cachea lo que una herramienta publica, nunca lo que cambia solo |
| [0031](0031-la-ventana-como-navegador.md) | Un repositorio abierto es una pestaña de la barra de título; las ejecuciones son el segundo nivel |
| [0032](0032-abrir-no-es-ejecutar.md) | Un clic en una acción abre su pestaña; ejecutar es un gesto aparte |
| [0033](0033-que-es-de-la-app-y-que-del-repo.md) | Las favoritas y las secciones son de la aplicación; las pestañas abiertas son del repo |
| [0034](0034-refrescar-al-abrir.md) | Lo que se consulta se relee al mostrar la pestaña, sin botón de recargar |
| [0035](0035-clonar-abre-el-repo.md) | Clonar termina con el repositorio abierto como pestaña |
| [0036](0036-la-interfaz-no-toca-binarios.md) | Todo lo que ejecuta algo es una capacidad, incluso lo que dispara un ícono de la interfaz |
| [0037](0037-sincronizar-solo-las-claves-compartidas.md) | Sincronizar env iguala solo los valores de las claves que los dos archivos ya tienen |
| [0038](0038-una-compuesta-reusa-otra-entera.md) | Una compuesta reusa a otra solo si quiere todos sus pasos |
| [0039](0039-mostrar-antes-de-escribir.md) | Nada se sobrescribe a ciegas: primero se muestra qué va a cambiar |
| [0040](0040-una-regla-es-host-mas-ruta.md) | Una regla de publicación es un host más una ruta, y cada pieza va en su propio host |

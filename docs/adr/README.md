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
| [0041](0041-un-repo-declara-sus-servicios.md) | Un repo declara sus servicios en una tabla; uno solo es el caso de una fila |
| [0042](0042-una-paleta-por-repo.md) | El color de un repo es una paleta entera, se elige, y tiñe sin cambiar la luminosidad |
| [0043](0043-un-menu-sin-secciones.md) | Un menú es un grupo sin secciones, y el nombre de un botón nombra lo que corre |
| [0044](0044-el-lado-que-gana-es-un-eje.md) | El menú separa la máquina del código que corre en ella, y el lado que gana un forzado es un eje |
| [0045](0045-la-carpeta-y-el-conteo-de-respaldos-son-configuracion.md) | Dónde caen los respaldos y cuántos sobreviven son configuración del repo, no ejes del botón |
| [0046](0046-el-volcado-corre-de-este-lado.md) | El volcado y la restauración corren de este lado y alcanzan la base remota por el túnel |
| [0047](0047-restaurar-es-un-destructivo-del-seguro-por-repo.md) | Restaurar es un destructivo del seguro por repositorio, y el respaldo se elige de una lista que se mira al abrir |
| [0048](0048-las-diferencias-de-sistema-viven-en-host.md) | Las diferencias entre Windows y Linux viven en un solo módulo, con una clase por sistema |
| [0049](0049-la-camara-de-capturas-es-un-script-del-repo.md) | La cámara de capturas es un script del repo que Consola corre con argumentos |
| [0050](0050-las-capturas-no-tocan-la-base.md) | Las capturas no tocan la base: los datos salen de un escenario servido por un servidor ficticio |
| [0051](0051-el-kit-de-la-camara-viaja-en-un-argumento.md) | La plomería de las cámaras es un kit de Consola que la cámara recibe en `--kit` |
| [0052](0052-la-camara-dice-que-apps-necesitan-emulador.md) | Qué apps necesitan emulador lo dice la cámara, no el tipo de la app |
| [0053](0053-el-servidor-ficticio-tambien-mapea-las-escrituras.md) | El servidor ficticio también mapea las escrituras |
| [0054](0054-la-camara-dice-que-sabe-capturar.md) | Lo que se ofrece capturar lo dice la cámara |
| [0055](0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md) | Los íconos salen del logo del repo, los rasteriza Qt y van donde cada app declara |
| [0056](0056-cada-tecnologia-declara-donde-va-su-icono.md) | Cada tecnología declara dónde va su ícono, y todos salen de `brand/` |
| [0057](0057-el-manifest-de-la-pwa-es-un-archivo-estatico.md) | El manifest de la PWA es un archivo estático que la app enlaza |
| [0058](0058-el-logo-del-repo-en-la-interfaz.md) | La interfaz muestra el logo del repo, y un repo sin logo lleva la marca de Equipaggio |
| [0059](0059-desplegar-con-los-programas-de-canone.md) | Consola despliega con los programas de canone y no reimplementa el despliegue |
| [0060](0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md) | Crear, migrar, respaldar y restaurar actúan solo sobre la base local |
| [0061](0061-los-forzados-corren-en-esta-maquina.md) | Los forzados de git corren solo en esta máquina |
| [0062](0062-vaciar-vps-sale.md) | «Vaciar VPS» sale hasta que canone traiga el programa que desinstala |
| [0063](0063-las-lineas-de-config-env-se-clasifican-por-fuente.md) | Las líneas de `config.env` se clasifican por la fuente que declara cada clave |
| [0064](0064-consola-se-ignora-con-su-propio-gitignore.md) | En `config.env` van los datos que las tareas leen, y `.consola/` se ignora con su propio `.gitignore` |
| [0065](0065-cada-spa-va-en-la-raiz-de-su-host.md) | Cada SPA se compila para la raíz de su host, y la tabla de rutas públicas sale |
| [0066](0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md) | «Configurar VPS» prepara la máquina y corre `install.py`; root entra solo la primera vez |
| [0067](0067-publicar-version-sube-el-ultimo-tag-de-origin.md) | «Publicar versión» sube el último tag de origin, y «Desplegar versión» elige entre los releases firmados |
| [0068](0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md) | El eje de servicios sale de las unidades de canone, y operarlas pide la contraseña de `sudo` |
| [0069](0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md) | Un repo de canone corre en desarrollo con sus credenciales, escritas desde `config.env` |
| [0070](0070-las-credenciales-del-dueno-van-dentro-de-credentials.md) | Las credenciales de desarrollo del dueño del esquema van en `credentials/migrate/` |
| [0071](0071-las-extensiones-las-declara-el-repo-sin-valor-por-defecto.md) | Las extensiones de Postgres las declara el repo, sin valor por defecto |
| [0072](0072-las-spa-usan-pnpm-y-la-plantilla-de-canone.md) | Las SPA corren con pnpm, y una nueva parte de la plantilla de canone |
| [0073](0073-el-respaldo-no-se-arranca-desde-control-del-servicio.md) | El respaldo no se arranca desde «Control del servicio» |
| [0074](0074-lo-que-cambia-un-vps-y-canone-no-hace-va-primero-a-canone.md) | Lo que deja un cambio permanente en un VPS y ningún programa de canone hace va primero a canone |
| [0075](0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md) | Consola sigue las convenciones de canone como cualquier repositorio |
| [0076](0076-un-fallo-al-consultar-o-al-guardar-en-cache-se-dice.md) | Un fallo al consultar o al guardar en caché se dice, y no se esconde |
| [0077](0077-el-eje-de-servicios-pregunta-al-vps-que-unidades-existen.md) | El eje de servicios le pregunta al VPS qué unidades existen |
| [0078](0078-contra-un-vps-de-canone-la-base-no-se-migra-por-tunel.md) | Contra un VPS de canone la base no se migra por túnel, y el ámbito remoto espera a canone |
| [0079](0079-http-bloquea-el-hilo-de-la-tarea.md) | HTTP va por QNetworkAccessManager y bloquea el hilo de la tarea |

from __future__ import annotations
from dataclasses import dataclass, field

"""
Descripciones largas de los comandos, para la seccion de ayuda del panel derecho.

La `description` de una `Capability` es una linea — lo justo para el tooltip del
rail y la cabecera. Aca vive el texto largo: que hace el comando y que pasos
ejecuta, en orden.

Solo lo que el boton hace. Los `steps` son el rastro exacto de la corrida, en el
orden real en que ocurre: una operacion por linea, y una linea por cada rama que
el codigo toma. No son las casillas del panel de parametros —una casilla abstrae
varias operaciones— sino la plomeria: que se lee del disco, que se manda por SSH,
que binario se invoca y con que banderas. Leer la lista de arriba abajo tiene que
alcanzar para decir si falta un paso, si sobra, o si estan en el orden
equivocado.

El texto se dibuja como texto plano (`ui/command_info_panel.py`), asi que no
lleva marcado: nada de backticks ni de etiquetas.
"""


@dataclass(frozen=True)
class CommandDoc:
    summary: str                                     # que hace
    steps: list[str] = field(default_factory=list)   # que ejecuta, en orden


DOCS: dict[str, CommandDoc] = {

    # --- Ejecutar ---------------------------------------------------------

    'backend': CommandDoc(
        summary=(
            'Levanta con uvicorn el servidor FastAPI del repo y publica su URL '
            'para el resto de la sesión. El ámbito elige la base: la de esta '
            'máquina, o la del VPS por un túnel SSH que se cierra al detener la '
            'pestaña.'
        ),
        steps=[
            'Ubica el servidor elegido: la carpeta cuyo app/main.py o main.py '
            'crea FastAPI(, o que tiene alembic.ini y app/main.py. Toma el '
            'intérprete de su venv.',
            'Toma el puerto preferido, o el siguiente libre si está ocupado.',
            'Publica ese puerto en la sesión del repo.',
            'Arma la línea de uvicorn con el módulo donde se encontró la app '
            '(app.main:app o main:app), --host y --port, y le agrega --reload '
            'si está marcado.',
            'Busca certs/cert.pem y certs/key.pem en la carpeta del servidor; '
            'si los dos existen, agrega --ssl-certfile y --ssl-keyfile.',
            'Abre la base del ámbito: local arma la URL contra 127.0.0.1 y el '
            'puerto del Postgres de esta máquina; remoto pregunta el puerto '
            'real al Postgres del VPS, abre el túnel SSH y arma la URL contra '
            'el extremo local del túnel.',
            'Anuncia como endpoint de la pestaña http://localhost:PUERTO, o '
            'https si hay certificados.',
            'Corre uvicorn desde la carpeta del servidor, con DATABASE_URL en '
            'el entorno.',
            'Al terminar, olvida el puerto publicado y cierra el túnel.',
        ],
    ),

    'serve_vite': CommandDoc(
        summary=(
            'Arranca el dev server de Vite de una SPA del repo, apuntado al '
            'backend de esta sesión. Marcar varias apps abre una pestaña por '
            'cada una.'
        ),
        steps=[
            'Ubica la carpeta de la SPA elegida.',
            'Toma el puerto preferido, o el siguiente libre si está ocupado.',
            'Espera hasta 90 segundos el endpoint del backend de esta sesión, y '
            'sigue igual si no aparece.',
            'Anuncia http://localhost:PUERTO como endpoint de la pestaña.',
            'Corre npm run dev con --port desde la carpeta de la SPA, con '
            'VITE_SERVER_URL puesto en la URL del backend cuando la hay.',
        ],
    ),

    'run_mobile': CommandDoc(
        summary=(
            'Corre la app móvil del repo sobre un emulador vivo. El framework '
            'sale de la carpeta de la app.'
        ),
        steps=[
            'Ubica la app móvil elegida.',
            'Detecta si es Flutter o Flet por su manifiesto.',
            'Elige el emulador, en este orden: el indicado a mano, el que lanzó '
            'la pestaña Emulador de esta sesión, y el primero que conteste por '
            'adb.',
            'Corta si no hay ningún emulador vivo.',
            'Resuelve la URL de la API: API_URL de la configuración, o el '
            'endpoint del backend de esta sesión esperándolo hasta 90 '
            'segundos.',
            'Si es Flutter, corre flutter run -d SERIAL con '
            '--dart-define=API_BASE_URL desde la carpeta de la app.',
            'Si es Flet, corre flet run --android desde esa carpeta, con '
            'API_BASE_URL en el entorno.',
        ],
    ),

    'run_python': CommandDoc(
        summary=(
            'Arranca una app Python del repo que no sea el servidor (PySide6, '
            'Flet de escritorio, un bot). Marcar varias apps abre una pestaña '
            'por cada una.'
        ),
        steps=[
            'Ubica la app elegida y su punto de entrada: src/main.py, y si no '
            'main.py.',
            'Toma el intérprete del venv de la app; si no tiene, el del venv de '
            'la raíz del repo; si tampoco, el Python del PATH.',
            'Espera hasta 90 segundos el endpoint del backend y, si aparece, lo '
            'pone en SERVER_URL; si no, sigue sin él.',
            'Agrega TERMINAL_DEV_AUTO_LOGIN al entorno si la casilla de '
            'auto-login está marcada.',
            'Sin la casilla "Relanzar al detectar cambios": corre python '
            'main.py una sola vez, desde la carpeta del punto de entrada.',
            'Con ella (el default): corre python main.py y, en paralelo, '
            'compara cada medio segundo las fechas de modificación de los .py '
            'y .qss de esa carpeta, sin venv ni artefactos.',
            'Si algún fuente cambió, mata el proceso y su árbol y lo relanza.',
            'Si el proceso termina solo, informa el código de salida y cierra.',
        ],
    ),

    'dev_env': CommandDoc(
        summary=(
            'Lanza backend, SPA y apps Python a la vez, cada uno en su propia '
            'pestaña, con los parámetros que cada botón tiene guardados para '
            'este repo.'
        ),
        steps=[
            'Recorre los pasos marcados y busca cada uno como capacidad del '
            'catálogo.',
            'Lanza Backend en su propia pestaña.',
            'Lanza SPA Vite en la suya, sin esperar al anterior.',
            'Lanza App Python en la suya, sin esperar al anterior.',
            'Informa en la consola cuáles quedaron lanzados.',
        ],
    ),

    # --- Compilar ----------------------------------------------------------

    'build_flutter': CommandDoc(
        summary=(
            'Compila la app Flutter o Flet del repo para las plataformas '
            'marcadas (APK, AAB, web, escritorio, iOS).'
        ),
        steps=[
            'Ubica la app elegida.',
            'Detecta si la app es Flutter o Flet y lee API_URL de la '
            'configuración.',
            'Por cada plataforma corre flutter build <plataforma> --release, o '
            'flet build <plataforma>, con --dart-define=API_BASE_URL.',
            'Busca el build donde lo deja el framework y, si BUILD_OUT_<PLATAFORMA> '
            'tiene una carpeta, lo copia ahí.',
        ],
    ),

    'build_vite': CommandDoc(
        summary=(
            'Deja compiladas las SPA marcadas del repo. Las recorre de a una, en '
            'un solo log.'
        ),
        steps=[
            'Ubica la carpeta de la primera SPA marcada.',
            'Corre npm install en la carpeta de la SPA.',
            'Corre npm run build.',
            'Busca la salida en dist/ o en build/.',
            'Vuelve al primer paso con la siguiente SPA marcada.',
        ],
    ),

    'build_binary': CommandDoc(
        summary=(
            'Empaqueta una app Python del repo como ejecutable con PyInstaller, '
            'con su versión al día, su huella SHA-256 y su publicación en el '
            'VPS.'
        ),
        steps=[
            'Resuelve el punto de entrada: el escrito, o src/main.py de la '
            'única app Python del repo, o un main.py en la raíz.',
            'Sube desde el entrypoint hasta la primera carpeta con manifiesto, y '
            'escribe ahí un pyproject.toml en 0.0.0 si no hay ninguno.',
            'Si el paso de compilar está desmarcado, toma el binario que ya está '
            'en dist/ y salta al checksum y la subida.',
            'Abre una copia reversible del manifiesto.',
            'Escribe la versión nueva en el manifiesto, según el modo elegido.',
            'Arma la etiqueta del ejecutable: el nombre escrito o el de la app, '
            'más sistema y arquitectura.',
            'Si hay BRAND_ICON, lo rasteriza como build/icon.ico con los lados '
            'de 16 a 256.',
            'Corre pyinstaller con --noconfirm, --name, --specpath build, '
            '--onefile y --windowed según los ejes, e --icon si hay BRAND_ICON, '
            'desde la carpeta de la app.',
            'Comprueba que el artefacto haya quedado en dist/ y corta si no '
            'está.',
            'Calcula su SHA-256 y lo escribe al lado como .sha256, en formato '
            'sha256sum.',
            'Copia por scp el binario con chmod 755, después el manifiesto y '
            'después el checksum.',
        ],
    ),

    # --- Imágenes -----------------------------------------------------------

    'generate_icons': CommandDoc(
        summary=(
            'Deja el logo del repo, BRAND_ICON, como ícono de cada app marcada, '
            'con la capa frontal de Android y la maskable de PWA donde la app '
            'las pida. Se ofrecen las apps que declaran dónde va su ícono: '
            'Flutter con sección flutter_launcher_icons, Flet con '
            'src/assets/icon.png, y SPA con un <link rel="icon"> o '
            '"apple-touch-icon", o con un <link rel="manifest"> a su manifest.'
        ),
        steps=[
            'Corta si BRAND_ICON, o una capa escrita (BRAND_ICON_FOREGROUND, '
            'BRAND_ICON_MASKABLE), no es un SVG que exista.',
            'Por cada app marcada, antes de escribir nada, junta sus archivos '
            'de ícono. Flutter: las rutas image_path y adaptive_icon_foreground '
            'del pubspec.yaml; corta si falta el paquete en dev_dependencies, si '
            'no declara image_path o si pide otra imagen. Flet: '
            'src/assets/icon.png. SPA: el <link> del +layout.svelte cuando '
            'importa de $lib/, los de app.html e index.html resueltos en static/ '
            'o public/, y los íconos del manifest que enlaza <link '
            'rel="manifest">, leído como JSON. Corta si el plugin de PWA genera '
            'el manifest desde vite.config (le falta manifest: false).',
            'Un PNG sin sizes="NxN", o no cuadrado, corta. Un ícono del '
            'manifest con purpose maskable lleva la capa maskable; uno que es '
            'any y maskable a la vez corta.',
            'Corta si la app pide una capa que no está configurada, y abre la '
            'configuración en esa clave.',
            'Escribe cada archivo según su extensión: .svg copia la capa tal '
            'cual; .png la rasteriza con Qt al lado declarado (1024 en Flutter '
            'y Flet); .ico la rasteriza con los lados de 16 a 256. Corta si el '
            'SVG no es cuadrado.',
            'Escribe cada archivo solo si cambió, y dice si es nuevo, '
            'actualizado o sin cambios.',
            'Flutter: corre dart run flutter_launcher_icons desde la carpeta de '
            'la app, que reparte el ícono en cada plataforma.',
        ],
    ),

    'shoot_screens': CommandDoc(
        summary=(
            'Corre la cámara del repo, el script de SHOTS_CMD, con las apps, '
            'temas e idiomas marcados, y comprueba que dejó una captura por '
            'cada combinación.'
        ),
        steps=[
            'Ubica cada app marcada entre las SPA y las apps móviles del repo.',
            'Si hay una app móvil marcada y no se eligió emulador, corta antes '
            'de empezar.',
            'Borra de SHOTS_RAW las capturas de las combinaciones que se van a '
            'volver a sacar.',
            'Si hay una app móvil: usa el AVD elegido si ya está encendido; si '
            'no, lo enciende y espera a que termine de arrancar.',
            'Corre SHOTS_CMD desde la raíz del repo, agregándole --apps, '
            '--themes, --languages, --output, --kit con la ruta del kit de '
            'la cámara y, con app móvil, --device. Con app móvil, el adb del '
            'SDK va primero en el PATH de la cámara.',
            'Si encendió el emulador, lo apaga por adb.',
            'Lee SHOTS_RAW y corta si un archivo no se llama '
            '<pantalla>.<tema>.<idioma>.png o si falta alguna combinación.',
        ],
    ),

    'render_shots': CommandDoc(
        summary=(
            'Convierte las capturas crudas de SHOTS_RAW al formato de cada '
            'destino marcado y deja un manifiesto por destino.'
        ),
        steps=[
            'Corta si algún destino marcado no tiene preset en '
            'core/shots_presets.json, si ninguna captura es de un tipo que le '
            'sirva, o si una captura no cumple sus reglas (Play) o no cabe en '
            'ninguna de sus medidas sin recortar de más (App Store). Lo revisa '
            'para todos los destinos antes de convertir nada.',
            'Lee SHOTS_RAW y corta ante una carpeta que no es una app del repo '
            'o un archivo con otro nombre.',
            'Landing: por cada captura, la achica al ancho tope de su tipo de '
            'app (nunca la agranda) y la guarda como .webp en SHOTS_PUBLISH, '
            'con el mismo nombre.',
            'Play y Manual: PNG a resolución nativa, sin canal alfa, en '
            'SHOTS_DIST.',
            'App Store, Open Graph y Redes sociales: escala hasta cubrir la '
            'medida exacta del preset y recorta del centro, en SHOTS_DIST.',
            'Press kit: los crudos sin comprimir en un ZIP.',
            'Escribe un capturas.json por destino con el hash de cada archivo, '
            'y dice qué archivos cambiaron, cuáles son nuevos y cuáles ya no '
            'están respecto de la corrida anterior.',
        ],
    ),

    'screenshots': CommandDoc(
        summary=(
            'Saca las capturas de las apps del repo y las revela para los '
            'destinos marcados, en un solo log.'
        ),
        steps=[
            'Si Sacar capturas está marcado, corre la cámara del repo como el '
            'botón Sacar capturas.',
            'Si Revelar capturas está marcado, convierte lo que haya en '
            'SHOTS_RAW como el botón Revelar capturas.',
        ],
    ),

    # --- Emuladores ---------------------------------------------------------

    'install_system_image': CommandDoc(
        summary=(
            'Descarga del SDK la máquina virtual (system image) sobre la que '
            'después corre un AVD.'
        ),
        steps=[
            'Resuelve el SDK de Android por ANDROID_SDK_ROOT, ANDROID_HOME o '
            'las rutas habituales.',
            'Lee del id del paquete la API, la variante y la arquitectura, y las '
            'informa.',
            'Consulta sdkmanager --list_installed y termina si la máquina ya '
            'está.',
            'Corre sdkmanager con el id del paquete y sigue su salida hasta el '
            'final.',
            'Olvida la caché de imágenes instaladas.',
        ],
    ),

    'create_avd': CommandDoc(
        summary=(
            'Crea un dispositivo virtual a partir de un modelo del catálogo del '
            'SDK y de una máquina virtual instalada.'
        ),
        steps=[
            'Resuelve el SDK de Android.',
            'Pregunta el nombre del AVD, mostrando el derivado del dispositivo '
            'y la API; vacío usa ese derivado, saneado a lo que acepta '
            'avdmanager.',
            'Si ya existe un AVD con ese nombre, salta la creación.',
            'Comprueba que la máquina virtual elegida esté instalada y corta si '
            'no lo está.',
            'Corre avdmanager create avd con el nombre, el paquete de la imagen '
            'y el perfil del dispositivo.',
            'Escribe hw.keyboard=yes en el config.ini del AVD.',
            'Olvida la caché de AVD.',
        ],
    ),

    'launch_emulator': CommandDoc(
        summary=(
            'Arranca uno de los AVD ya creados y sigue su salida hasta que se '
            'cierra.'
        ),
        steps=[
            'Resuelve el SDK y comprueba que el AVD exista en emulator '
            '-list-avds.',
            'Consulta los emuladores vivos; si ese mismo AVD ya corre, marca '
            'esta copia como -read-only.',
            'Arma la lista de flags: los de siempre (-no-boot-anim, -netdelay '
            'none, -netspeed full), los de las casillas marcadas, el -gpu '
            'elegido y el campo libre partido en tokens.',
            'Toma un puerto libre y arma con él el serial (emulator-5554).',
            'Publica ese serial en la sesión de la máquina.',
            'Engancha el cierre de la pestaña a adb emu kill sobre ese serial.',
            'Corre emulator -avd con ese puerto y esos flags, más -read-only y '
            '-wipe-data si corresponden, y sigue su salida.',
            'Al cerrarse, olvida el serial publicado.',
        ],
    ),

    'purge_emulators': CommandDoc(
        summary=(
            'Borra los AVD y las máquinas virtuales marcados. En simulacro los '
            'lista con su tamaño.'
        ),
        steps=[
            'Resuelve el SDK y termina si no hay nada marcado.',
            'Mide la carpeta .avd de cada AVD marcado y lo lista con su tamaño.',
            'Lista las máquinas marcadas con su etiqueta legible.',
            'En modo simulacro, termina.',
            'Pide escribir BORRAR y cancela si no coincide.',
            'Corre avdmanager delete avd por cada AVD marcado.',
            'Corre sdkmanager --uninstall por cada máquina marcada.',
            'Olvida las cachés de AVD y de imágenes instaladas.',
        ],
    ),

    # --- Despliegue y VPS ---------------------------------------------------------

    'ssh_login': CommandDoc(
        summary=(
            'Abre una sesión SSH interactiva contra el VPS del repo, en una '
            'terminal del sistema.'
        ),
        steps=[
            'Resuelve el destino VPS_USER en VPS_IP y la identidad VPS_KEY_NAME '
            'de ~/.ssh.',
            'Arma la línea de ssh con esa identidad y sus opciones de conexión.',
            'La lanza en una terminal externa y devuelve el control.',
        ],
    ),

    'health_check': CommandDoc(
        summary=(
            'Informa el estado del VPS: acceso, servicio, uptime, disco, '
            'memoria, carga y últimos errores del journal.'
        ),
        steps=[
            'Resuelve el destino SSH y el nombre del servicio del repo.',
            'Prueba el acceso SSH y termina ahí si no contesta.',
            'Corre systemctl cat y systemctl is-active del servicio.',
            'Corre uptime -p.',
            'Corre df -h de la raíz y free -h.',
            'Corre uptime y se queda con la carga promedio.',
            'Corre journalctl -u SERVICIO -p err -n 10.',
            'Vuelca cada dato en la consola con su nombre.',
        ],
    ),

    'run_command': CommandDoc(
        summary='Corre un comando suelto en el VPS y trae su salida a la pestaña.',
        steps=[
            'Corta si el campo del comando está vacío.',
            'Resuelve el destino SSH del repo.',
            'Manda el comando tal cual por SSH.',
            'Vuelca su salida en la consola a medida que llega.',
        ],
    ),

    'revoke_ssh': CommandDoc(
        summary=(
            'Saca del VPS la clave pública con la que entra esta máquina y borra '
            'el par local.'
        ),
        steps=[
            'Lee VPS_KEY_NAME y ubica el par en ~/.ssh; corta si falta la '
            'privada.',
            'Deriva la clave pública y la muestra recortada.',
            'Reescribe ~/.ssh/authorized_keys del VPS sin esa línea exacta, '
            'pasando por un temporal que después reemplaza al original.',
            'Borra en esta máquina la clave privada y su .pub.',
        ],
    ),

    # --- Despliegue ------------------------------------------------------

    'publish_release': CommandDoc(
        summary=(
            'Publica una versión: crea el tag siguiente, espera a que release.yml '
            'publique el release, firma su .sha256 en esta máquina y lo despliega '
            'con deploy.py de canone.'
        ),
        steps=[
            'Corta si hay cambios sin commitear, si la rama no tiene rama en '
            'origin o si tiene commits que origin no tiene.',
            'Lee con git ls-remote los tags v* de origin y sube el más alto según '
            'el eje: major, minor o patch. Sin ninguno, sube desde v0.0.0.',
            'Crea el tag anotado y lo empuja a origin.',
            'Busca con gh run list la corrida de release.yml del tag, cada 5 '
            'segundos durante un minuto.',
            'Pregunta con gh run view su estado cada 15 segundos hasta que '
            'termina. Si no termina bien, muestra el log de los pasos que '
            'fallaron y corta.',
            'Sin «Crear tag», toma el último release publicado de GitHub.',
            'Lee con gh release view los archivos del release. Si ya tiene '
            '<app>-<tag>.sha256.sig, no lo vuelve a firmar; sin .sha256, corta.',
            'Baja el .sha256 con gh release download a una carpeta temporal.',
            'Lo firma con ssh-keygen -Y sign -n deploy y la llave VPS_KEY_NAME.',
            'Sube la firma con gh release upload.',
            'Corre los pasos de «Desplegar versión» con ese tag.',
        ],
    ),

    'deploy_version': CommandDoc(
        summary='Instala en el VPS un release ya firmado, con deploy.py de canone.',
        steps=[
            'Lista con gh api los releases del repo que tienen su '
            '<app>-<tag>.sha256.sig.',
            'Entra como VPS_USER, con la contraseña de sudo de SUDO_PASSWORD o '
            'pedida una vez por sesión. Corta si la cuenta todavía no existe.',
            'Corre sudo python3 /usr/local/lib/<app>/deploy.py <tag>, que baja '
            'el release, comprueba la firma, migra, cambia current y espera la '
            'salud; si no responde y no hubo migraciones, vuelve a la anterior.',
        ],
    ),

    'systemd_action': CommandDoc(
        summary=(
            'Manda una acción de systemd al servicio elegido del VPS: el del '
            'repo, coturn o Caddy.'
        ),
        steps=[
            'Traduce el servicio elegido al nombre real de la unidad.',
            'Comprueba con systemctl cat que la unidad exista y corta si no '
            'está.',
            'Corre por SSH sudo -n systemctl ACCIÓN UNIDAD; daemon-reload va sin '
            'unidad.',
            'Vuelca la salida en la consola.',
        ],
    ),

    'view_logs': CommandDoc(
        summary=(
            'Muestra el journal del servicio elegido, de una o siguiéndolo en '
            'vivo.'
        ),
        steps=[
            'Traduce el servicio elegido al nombre real de la unidad.',
            'Arma el journalctl con la cantidad de líneas, -f si es en vivo, y '
            'los filtros de fecha, prioridad y patrón que estén cargados.',
            'Lo corre por SSH con sudo -n y vuelca la salida a medida que llega.',
        ],
    ),

    # --- VPS -------------------------------------------------------

    'bootstrap_vps': CommandDoc(
        summary=(
            'Deja el VPS listo con los programas de canone: paquetes y uv, swap, '
            'install.py con los datos del repo, las credenciales y el último '
            'release.'
        ),
        steps=[
            'Si está marcado, borra del known_hosts la huella vieja del VPS.',
            'Corre los pasos de «Instalar paquetes base».',
            'Si el swap no llega a la memoria, crea /swapfile con lo que falta, lo '
            'activa y lo agrega a /etc/fstab.',
            'Lee de git remote el dueño y el nombre del repo en GitHub.',
            'Arma los argumentos de install.py: DOMAIN, VALKEY_MEMORY, --owner, '
            '--admin VPS_USER, las dos llaves (VPS_KEY_NAME y OFFLINE_KEY) como '
            '--key y --signer, --private, --desktop del release.yml, --without '
            'por las piezas que faltan, --allow, --extension, --turn y --logs.',
            'Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone.',
            'La primera vez corre install.py como root por ssh -tt y escribe la '
            'contraseña de la cuenta cuando la pide, dos veces; después, con sudo '
            'desde VPS_USER.',
            'Corre los pasos de «Cargar credenciales».',
            'Borra /tmp/consola-canone.',
            'Toma el último release publicado de GitHub y corta si no tiene su '
            '.sha256.sig. Si /srv/<app>/current ya es ese release, no hace nada; '
            'si no, lo instala con deploy.py.',
        ],
    ),

    'install_software': CommandDoc(
        summary='Instala en el VPS los paquetes que canone pide para este repo, y uv.',
        steps=[
            'Entra como VPS_USER si la llave ya lo deja entrar, con la contraseña de sudo de SUDO_PASSWORD o pedida una vez por sesión; si no, como root con la '
            'misma llave.',
            'Arma la lista: los de la máquina de canone, más PostGIS si '
            'DB_EXTENSIONS la nombra, coturn con TURN y lo del journal con LOGS.',
            'Corre apt-get update y apt-get install -y con DEBIAN_FRONTEND='
            'noninteractive.',
            'Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone y corre '
            'uv.py, que instala la versión de uv que fija canone.',
            'Borra /tmp/consola-canone.',
        ],
    ),

    'load_credentials': CommandDoc(
        summary='Pasa las credenciales de config.env a credentials.py de canone.',
        steps=[
            'Lee los campos de Settings de server/src/app/config.py.',
            'Corta si config.env tiene una clave que no es de Consola ni un '
            'campo, o si falta el valor de un campo o de RESTIC_PASSWORD (y de '
            'GITHUB_TOKEN con PRIVATE).',
            'Entra como VPS_USER si la llave ya lo deja entrar, con la contraseña de sudo de SUDO_PASSWORD o pedida una vez por sesión; si no, como root con la '
            'misma llave.',
            'Corta si todavía no existe la cuenta que administra.',
            'Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone.',
            'Corre sudo python3 credentials.py <app> y le pasa por stdin una '
            'línea campo=valor por credencial; nada de eso va al log.',
            'Borra /tmp/consola-canone.',
        ],
    ),

    'refresh_known_host': CommandDoc(
        summary='Borra del known_hosts de esta máquina la huella vieja del VPS.',
        steps=[
            'Lee VPS_IP de la configuración del repo.',
            'Corre ssh-keygen -R contra ese host.',
        ],
    ),

    # --- Base de datos -----------------------------------------------------

    'bootstrap_db': CommandDoc(
        summary=(
            'Deja la base local usable desde cero: rol, base, permisos, '
            'extensiones, migraciones, particiones y datos. Lo que crea objetos '
            'va por psql como superusuario.'
        ),
        steps=[
            'Abre el canal de superusuario local.',
            'Crea el rol de la aplicación si no existe.',
            'Corre ALTER ROLE con la contraseña de la configuración.',
            'Crea la base con ese rol como dueño, o le cambia el dueño si ya '
            'existe.',
            'Corre GRANT ALL PRIVILEGES sobre la base y GRANT ALL sobre el '
            'esquema public.',
            'Por cada nombre de DB_EXTENSIONS consulta pg_available_extensions y '
            'corre CREATE EXTENSION IF NOT EXISTS, salteando las que el sistema '
            'no tiene.',
            'Corre alembic upgrade head.',
            'Corre el mantenimiento de particiones del proyecto con el python de '
            'su venv.',
            'Ejecuta en orden las funciones seed_ del paquete seeders/, con un '
            'solo commit al final.',
            'Ejecuta las del paquete mock_data/, si está marcado.',
        ],
    ),

    'enable_extensions': CommandDoc(
        summary=(
            'Crea en la base las extensiones de Postgres que declara '
            'DB_EXTENSIONS, por el canal de superusuario.'
        ),
        steps=[
            'Lee DB_EXTENSIONS, descarta repetidos y termina si queda vacía.',
            'Abre el canal de superusuario del ámbito: psql local, o sudo -u '
            'postgres psql por SSH.',
            'Consulta pg_available_extensions por cada nombre y saltea con aviso '
            'las que el sistema no tiene.',
            'Corre CREATE EXTENSION IF NOT EXISTS sobre la base de la '
            'aplicación.',
        ],
    ),

    'teardown_db': CommandDoc(
        summary='Borra la base de la aplicación y su rol.',
        steps=[
            'Abre el canal de superusuario del ámbito elegido.',
            'Corre pg_terminate_backend sobre las conexiones vivas de esa base.',
            'Corre DROP DATABASE IF EXISTS.',
            'Corre DROP ROLE IF EXISTS del rol de la aplicación.',
        ],
    ),

    'migrate_db': CommandDoc(
        summary='Genera con Alembic la revisión pendiente y la aplica en la base local.',
        steps=[
            'Anota qué archivos hay en alembic/versions.',
            'Abre la base local.',
            'Corre alembic revision --autogenerate con el python del venv del '
            'servidor.',
            'Compara los archivos de alembic/versions e informa la revisión '
            'generada, o que el modelo no cambió.',
            'Corre alembic upgrade head.',
        ],
    ),

    'rebuild_db': CommandDoc(
        summary=(
            'Vacía las tablas de la base y la vuelve a llenar: migraciones, '
            'particiones y seeders.'
        ),
        steps=[
            'Abre el canal de superusuario del ámbito elegido.',
            'Lista las tablas del esquema public, salvo spatial_ref_sys, e '
            'informa cuántas son.',
            'Corre DROP TABLE IF EXISTS CASCADE sobre todas.',
            'Corre alembic upgrade head.',
            'Corre el mantenimiento de particiones del proyecto.',
            'Ejecuta las funciones seed_ del paquete seeders/.',
            'Ejecuta las del paquete mock_data/.',
        ],
    ),

    'reinit_migrations': CommandDoc(
        summary=(
            'Vacía la base, borra el historial de alembic/versions y escribe una '
            'migración inicial nueva.'
        ),
        steps=[
            'Lista las tablas del esquema public y las borra con DROP TABLE '
            'CASCADE.',
            'Borra uno por uno los .py de alembic/versions, nombrando cada uno.',
            'Corre alembic revision --autogenerate con el mensaje '
            'initial_migration, en esta máquina.',
        ],
    ),

    'run_seeders': CommandDoc(
        summary=(
            'Ejecuta las funciones seed_ del paquete seeders/ del proyecto, con '
            'el python de su venv.'
        ),
        steps=[
            'Elige el lado según el ámbito: el venv del repo contra la base '
            'local, o el venv del VPS contra la base de ahí.',
            'Lanza por -c el programa de seeders, sin escribir nada en disco.',
            'Recorre el paquete seeders/ y junta todas las funciones que '
            'empiezan con seed_.',
            'Las ejecuta en orden dentro de una sesión, nombrando cada una.',
            'Hace rollback y corta si alguna falla, o un solo commit si todas '
            'pasan.',
        ],
    ),

    'run_mock_seeders': CommandDoc(
        summary=(
            'Ejecuta las funciones seed_ del paquete mock_data/ del proyecto, '
            'con el python de su venv.'
        ),
        steps=[
            'Elige el lado según el ámbito, igual que los seeders base.',
            'Lanza por -c el mismo programa, apuntado al paquete mock_data/.',
            'Recorre el paquete y junta sus funciones seed_.',
            'Las ejecuta en orden y commitea una sola vez al final.',
        ],
    ),

    'backup_db': CommandDoc(
        summary=(
            'Deja un volcado de la base local, en formato custom de pg_dump, y '
            'rota los respaldos viejos.'
        ),
        steps=[
            'Resuelve la carpeta de respaldos de BACKUP_DIR: relativa cuelga de '
            'la raíz del repo, absoluta se usa tal cual.',
            'Abre la conexión a la base local.',
            'Busca pg_dump en la instalación local de PostgreSQL y corta si su '
            'versión es más vieja que la del servidor, nombrando las dos.',
            'Corre pg_dump -Fc como el rol de la aplicación, escribiendo directo '
            'en el archivo local, con la fecha y hora en el nombre.',
            'Ordena los respaldos de esta base por fecha, deja los BACKUP_KEEP '
            'más nuevos y borra los que sobran, nombrando cada uno.',
        ],
    ),

    'restore_db': CommandDoc(
        summary=(
            'Carga uno de los respaldos guardados sobre la base local, '
            'reemplazando lo que haya.'
        ),
        steps=[
            'Comprueba que el respaldo elegido exista en la carpeta de respaldos.',
            'Abre la conexión a la base local.',
            'Busca pg_restore en la instalación local de PostgreSQL y corta si su '
            'versión es más vieja que la del servidor.',
            'Corre pg_restore como el rol de la aplicación, borrando cada objeto '
            'antes de recrearlo y cortando en el primer error.',
        ],
    ),

    'ssh_tunnel': CommandDoc(
        summary=(
            'Abre un túnel SSH al Postgres del VPS y lo deja levantado como '
            'servicio de fondo.'
        ),
        steps=[
            'Resuelve el destino SSH del repo.',
            'Le pregunta al Postgres del VPS en qué puerto escucha.',
            'Toma ese mismo número de este lado, o el siguiente libre.',
            'Levanta el reenvío de puertos por SSH.',
            'Informa el extremo local al que apuntar el cliente.',
        ],
    ),

    'explore_db': CommandDoc(
        summary=(
            'Abre la base del ámbito en solo lectura y la muestra en la pestaña: '
            'esquemas y tablas a la izquierda, datos y estructura a la derecha. '
            'Queda conectada hasta que cierras la pestaña.'
        ),
        steps=[
            'Abre la base del ámbito con el rol de la app: local contra '
            '127.0.0.1, remoto por un túnel SSH.',
            'Se conecta en solo lectura: el servidor rechaza cualquier escritura.',
            'Muestra en la consola el servidor, la base, su tamaño y las tablas '
            'con su estimado de filas.',
            'Publica la conexión y cambia a la vista del explorador.',
            'Espera hasta que cierres la pestaña; si el túnel se cae, termina '
            'con error.',
        ],
    ),

    # --- Utils -------------------------------------------------------------

    'clean_artifacts': CommandDoc(
        summary=(
            'Borra las cachés y la basura de build del repo abierto. En '
            'simulacro las lista con su tamaño.'
        ),
        steps=[
            'Recorre el repo una sola vez, salteando .git, .consola y las '
            'carpetas pesadas que no se marcaron.',
            'Anota como una unidad las carpetas pesadas marcadas: node_modules, '
            '.venv, build o dist, .dart_tool.',
            'Anota, según las familias marcadas, las carpetas __pycache__, '
            '.gradle, .kotlin y .cxx, los archivos .pyc y .pyo, los residuos de '
            'Flutter y los volcados de crash.',
            'Termina si no encontró nada.',
            'Muestra hasta cuarenta rutas y dice cuántas quedaron sin listar.',
            'Suma el tamaño total en disco y lo informa.',
            'En modo simulacro, termina.',
            'Borra todo lo listado e informa cuánto se liberó.',
        ],
    ),

    'install_android_tools': CommandDoc(
        summary=(
            'Instala las command-line tools del SDK de Android y las deja en el '
            'entorno del usuario.'
        ),
        steps=[
            'Comprueba que el sistema sea Windows o Linux y que haya Java en el '
            'PATH.',
            'Salta la descarga si ya hay un sdkmanager en el directorio '
            'elegido.',
            'Lee la página de Android Studio y saca el nombre del zip publicado '
            'y su SHA-1.',
            'Descarga el zip informando el avance y atendiendo al botón de '
            'detener.',
            'Verifica el SHA-1 del archivo bajado.',
            'Descomprime y reacomoda el contenido para que quede en '
            'cmdline-tools/latest.',
            'Crea la carpeta avd/ dentro del SDK.',
            'Escribe ANDROID_SDK_ROOT, ANDROID_HOME y ANDROID_AVD_HOME en el '
            'entorno del usuario.',
            'Agrega al PATH platform-tools, emulator y el bin de las '
            'herramientas, sacando las entradas de instalaciones anteriores.',
        ],
    ),

    'install_android_packages': CommandDoc(
        summary=(
            'Acepta las licencias e instala en el SDK los paquetes marcados que '
            'falten.'
        ),
        steps=[
            'Traduce los componentes marcados a ids de sdkmanager, armando '
            'build-tools y platform con la versión y el API level escritos.',
            'Resuelve el sdkmanager instalado y la raíz de su SDK.',
            'Corre sdkmanager --licenses respondiendo que sí a cada licencia.',
            'Consulta sdkmanager --list_installed y descarta lo que ya está.',
            'Termina si no falta ninguno.',
            'Enumera lo que falta y lo instala en una sola corrida de '
            'sdkmanager.',
        ],
    ),

    'install_android_hypervisor': CommandDoc(
        summary=(
            'Deja lista la aceleración por hardware del emulador: instala el '
            'driver en Windows y verifica /dev/kvm en Linux.'
        ),
        steps=[
            'En Windows, consulta el servicio gvm y termina si el driver ya está '
            'instalado.',
            'Descarga el driver con sdkmanager y comprueba que aparezca su '
            'silent_install.bat.',
            'Lanza ese instalador pidiendo elevación, en una ventana aparte.',
            'En Linux, comprueba que exista /dev/kvm y corta explicando la '
            'virtualización de la BIOS y el módulo del kernel si falta.',
            'Comprueba que este usuario tenga lectura y escritura sobre '
            '/dev/kvm, y escribe el usermod exacto si no las tiene.',
        ],
    ),

    'install_android_sdk': CommandDoc(
        summary=(
            'Deja esta máquina lista para compilar y emular Android: '
            'herramientas, paquetes y aceleración.'
        ),
        steps=[
            'Descarga y verifica las command-line tools, las deja en '
            'cmdline-tools/latest y escribe las variables y el PATH del '
            'usuario.',
            'Acepta las licencias e instala los componentes marcados que falten, '
            'con el API level y el build-tools escritos.',
            'Instala el driver del hipervisor en Windows, o verifica /dev/kvm en '
            'Linux.',
        ],
    ),

    'install_flutter_sdk': CommandDoc(
        summary=(
            'Instala el SDK de Flutter del canal stable y lo deja en el entorno '
            'del usuario.'
        ),
        steps=[
            'Comprueba que haya Git en el PATH.',
            'Salta la descarga si ya hay un flutter en el directorio elegido.',
            'Consulta el índice oficial de releases y saca el archivo y el '
            'SHA-256 del canal stable.',
            'Descarga el paquete informando el avance.',
            'Verifica su SHA-256.',
            'Descomprime y renombra la carpeta que trae el zip si el destino '
            'tiene otro nombre.',
            'Escribe FLUTTER_HOME y agrega su bin al PATH del usuario, sacando '
            'las entradas de instalaciones anteriores.',
            'Corre flutter --version.',
            'Corre flutter doctor.',
        ],
    ),

    'update_cloudflare': CommandDoc(
        summary=(
            'Apunta el registro A de Cloudflare a la IP elegida: la del VPS, la '
            'pública detectada, o una escrita.'
        ),
        steps=[
            'Resuelve la IP según el modo: VPS_IP, la detectada preguntándole a '
            'un servicio externo, o la escrita.',
            'Busca en Cloudflare la zona de CF_DOMAIN_NAME con el token de la '
            'API.',
            'Busca el registro A de CF_RECORD_NAME dentro de esa zona.',
            'Termina si ese registro ya apunta a la misma IP.',
            'Manda el PUT con la IP nueva, el TTL y el estado de proxy.',
            'Deja en el log el cambio de una IP a la otra.',
        ],
    ),

    'sync_common_files': CommandDoc(
        summary=(
            'Copia los archivos compartidos de este repo a los otros repos '
            'indicados. En simulacro muestra las diferencias.'
        ),
        steps=[
            'Corta si no hay ningún repo destino.',
            'Toma la lista de archivos escrita, o los archivos comunes del '
            'catálogo si está vacía.',
            'Saltea con aviso los destinos que no existen como carpeta.',
            'Compara cada archivo contra su par en cada destino y se queda con '
            'los que faltan o difieren.',
            'Termina si no hay diferencias.',
            'Lista cada diferencia con su estado y su repo.',
            'En modo simulacro, termina.',
            'Copia archivo por archivo, nombrando cada uno.',
        ],
    ),

    'sync_server_env': CommandDoc(
        summary=(
            'Iguala los valores de las claves que .consola/config.env y el .env '
            'del server ya tienen los dos. No crea claves nuevas en ninguno de '
            'los dos archivos.'
        ),
        steps=[
            'Ubica .consola/config.env y el .env de la carpeta SERVER_DIR, y '
            'corta si falta cualquiera de los dos.',
            'Elige origen y destino según la dirección marcada.',
            'Lee los dos archivos y se queda con las claves que están en ambos.',
            'Termina con un aviso si no comparten ninguna clave.',
            'Lista por nombre las claves cuyo valor difiere, sin imprimir los '
            'valores: la mitad son secretos.',
            'En modo simulacro, termina.',
            'Escribe en el destino clave por clave, conservando sus comentarios '
            'y las claves que no viajan.',
        ],
    ),

    'clone_repo': CommandDoc(
        summary=(
            'Clona un repositorio de GitHub en una carpeta nueva y lo abre como '
            'pestaña de Consola.'
        ),
        steps=[
            'Corta si no hay URL o si no hay git en el PATH.',
            'Toma la carpeta destino escrita; vacía, usa la carpeta que '
            'contiene al repo abierto.',
            'Deriva el nombre de la carpeta del último tramo de la URL, sin '
            '.git.',
            'Corta si esa carpeta ya existe: clonar encima sería mezclar dos '
            'repos.',
            'Corre git clone, con --branch si se escribió una rama.',
            'Lee el commit corto del clon y lo deja en el log.',
            'Devuelve la carpeta, que la ventana abre como pestaña nueva.',
        ],
    ),
}


def get(capability_id: str) -> CommandDoc | None:
    return DOCS.get(capability_id)

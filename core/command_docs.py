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

    # --- Launchers ---------------------------------------------------------

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

    # --- Builders ----------------------------------------------------------

    'build_flutter': CommandDoc(
        summary=(
            'Compila la app Flutter o Flet del repo para las plataformas '
            'marcadas (APK, AAB, web, escritorio, iOS), con el número de versión '
            'al día y publicada en el VPS junto a su manifiesto.'
        ),
        steps=[
            'Ubica la app elegida y su manifiesto de versión (pubspec.yaml o '
            'pyproject.toml).',
            'Si el paso de compilar está desmarcado, toma los builds que ya están '
            'en disco y salta directo a la subida.',
            'Abre una copia reversible del manifiesto, que se restaura si algo '
            'falla antes de terminar los builds.',
            'Escribe la versión nueva en el manifiesto, una sola vez para todas '
            'las plataformas: patch, minor, major, +build o ninguno.',
            'Detecta si la app es Flutter o Flet y lee API_URL de la '
            'configuración.',
            'Por cada plataforma corre flutter build <plataforma> --release, o '
            'flet build <plataforma>, con --dart-define=API_BASE_URL. En web '
            'agrega la ruta bajo la que el proxy sirve la app.',
            'Busca el build donde lo deja el framework y, si BUILD_OUT_<PLATAFORMA> '
            'tiene una carpeta, lo copia ahí.',
            'Copia por scp cada build al VPS, a la misma ruta relativa que tiene '
            'en el repo.',
            'Copia por scp el manifiesto de versión a su ruta relativa.',
        ],
    ),

    'build_vite': CommandDoc(
        summary=(
            'Deja compiladas las SPA marcadas del repo, con su versión al día y '
            'publicadas en el VPS. Las recorre de a una, en un solo log.'
        ),
        steps=[
            'Ubica la carpeta y el package.json de la primera SPA marcada.',
            'Si el paso de compilar está desmarcado, toma la carpeta dist/ o '
            'build/ que ya está en disco y salta a la subida.',
            'Abre una copia reversible del package.json.',
            'Corre npm install en la carpeta de la SPA.',
            'Escribe la versión nueva en el package.json, según el modo '
            'elegido.',
            'Escribe base.generated.js con la ruta pública que PUBLIC_ROUTES le '
            'asigna a esa app.',
            'Corre npm run build.',
            'Busca la salida en dist/ o en build/.',
            'Lee el index.html compilado y compara sus href y src contra esa '
            'ruta pública; corta si el build pide sus assets en la raíz del '
            'dominio.',
            'Copia por scp la carpeta compilada y después el package.json, a '
            'sus rutas relativas en el VPS.',
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
            'Corre pyinstaller con --noconfirm, --name, --specpath build y, '
            'según los ejes, --onefile, --windowed e --icon, desde la carpeta de '
            'la app.',
            'Comprueba que el artefacto haya quedado en dist/ y corta si no '
            'está.',
            'Calcula su SHA-256 y lo escribe al lado como .sha256, en formato '
            'sha256sum.',
            'Copia por scp el binario con chmod 755, después el manifiesto y '
            'después el checksum.',
        ],
    ),

    'promote_app': CommandDoc(
        summary=(
            'Reemplaza la carpeta estable del repo con la de la última versión '
            'publicada.'
        ),
        steps=[
            'Ubica las dos carpetas dentro del repo y corta si la de origen no '
            'existe.',
            'Compara árbol contra árbol y termina si son idénticas.',
            'Informa qué carpeta va a ser reemplazada y con qué diferencia.',
            'Borra la carpeta estable entera.',
            'Copia la carpeta de origen en su lugar.',
        ],
    ),

    # --- Emulators ---------------------------------------------------------

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

    # --- VPS · ops ---------------------------------------------------------

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

    'revoke_github_ssh': CommandDoc(
        summary=(
            'Borra la deploy key del disco del VPS y la da de baja en la cuenta '
            'de GitHub.'
        ),
        steps=[
            'Borra en el VPS ~/.ssh/id_ed25519 y su .pub.',
            'Busca en GitHub, con GITHUB_TOKEN, la llave cuyo título sea '
            'GITHUB_KEY_TITLE.',
            'La elimina por su id.',
        ],
    ),

    'clean_vps': CommandDoc(
        summary=(
            'Deja el VPS como recién formateado: saca el servicio, la base, el '
            'repo desplegado, la deploy key, los paquetes y el usuario de '
            'despliegue.'
        ),
        steps=[
            'Servicio: borra /etc/tmpfiles.d/<servicio>.conf (las carpetas se '
            'quedan), comprueba que la unidad exista, corre systemctl stop y '
            'disable, borra el archivo .service y corre daemon-reload.',
            'Base: corta las conexiones vivas y corre DROP DATABASE y DROP ROLE '
            'contra el Postgres del VPS.',
            'Repo: comprueba que la carpeta de despliegue exista y corre rm -rf '
            'sobre ella.',
            'Llaves: borra ~/.ssh/id_ed25519 del VPS y da de baja esa llave en '
            'GitHub.',
            'Paquetes: consulta con dpkg -s cuáles de la lista están, los '
            'informa, corre apt-get purge -y sobre ellos y después '
            'apt-get autoremove -y.',
            'Usuario: como root, mata sus procesos, corre userdel -r y borra su '
            'archivo de /etc/sudoers.d.',
        ],
    ),

    # --- VPS · server ------------------------------------------------------

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

    'configure_service': CommandDoc(
        summary=(
            'Escribe la unidad systemd del backend del repo en el VPS y lo deja '
            'corriendo.'
        ),
        steps=[
            'Comprueba que en el VPS existan la carpeta del servidor y el python '
            'de su venv, y corta si falta alguno.',
            'Si SERVICE_DIRS tiene carpetas, escribe /etc/tmpfiles.d/<servicio>.conf '
            '(mostrando el diff) y corre systemd-tmpfiles --create: crea las que '
            'faltan y corrige dueño y modo. Si está vacía, borra ese archivo.',
            'Lee BACKEND_HOST y BACKEND_PORT, y comprueba si el certificado está '
            'en el VPS cuando el backend escucha fuera de loopback.',
            'Arma la unidad con el usuario de despliegue, WorkingDirectory en la '
            'carpeta del servidor y un ExecStart que corre uvicorn con el python '
            'del venv, más --ssl-certfile y --ssl-keyfile si corresponde.',
            'Lee la unidad que ya está en el VPS y muestra el diff contra la '
            'nueva.',
            'Si cambió, la escribe con tee y corre systemctl daemon-reload.',
            'Si el backend escucha fuera de loopback, abre su puerto en ufw.',
            'Corre systemctl enable.',
            'Corre systemctl restart si la unidad cambió, o systemctl start si '
            'quedó igual.',
            'Consulta systemctl is-active y corta si el servicio no quedó '
            'activo.',
            'Informa en qué dirección y puerto quedó escuchando el backend.',
        ],
    ),

    'publish_code': CommandDoc(
        summary=(
            'Deja en el VPS el código de la rama abierta, sus dependencias y los '
            'archivos que no viajan por git.'
        ),
        steps=[
            'Comprueba que haya git en el PATH y que la carpeta abierta sea un '
            'repo.',
            'Lee la rama actual e informa los cambios sin commitear, sin '
            'commitearlos.',
            'Corre git fetch y compara la rama local con su upstream.',
            'Corre git push, o git push -u origin RAMA si la rama no tiene '
            'upstream, y salta el push si ya estaba al día.',
            'Pregunta al VPS, en una sola conexión, si el repo está clonado y '
            'qué tiene sin commitear.',
            'Si no está clonado, crea la carpeta de despliegue a nombre del '
            'usuario y corre git clone de GIT_REPO_URL.',
            'Si está clonado y sucio, muestra la lista de archivos y pregunta '
            'antes de descartarlos.',
            'Corre en el VPS, en un solo comando, el git reset --hard y '
            'git clean -fd aceptados, el git fetch --all y el git reset --hard '
            'al upstream.',
            'Crea el venv del servidor con python3 -m venv si no existe.',
            'Comprueba que requirements.txt esté en el VPS y corre el pip de ese '
            'venv con -r.',
            'Copia por scp cada ruta de SECRET_FILES que exista en el repo a la '
            'misma ruta relativa del VPS, con chmod 600.',
        ],
    ),

    'update_remote': CommandDoc(
        summary=(
            'Deja corriendo en el VPS el código de la rama abierta, con la base '
            'al día y el servicio reiniciado.'
        ),
        steps=[
            'Comprueba git y la rama, informa los cambios sin commitear y corre '
            'git fetch y git push.',
            'Pregunta al VPS si el repo está clonado y qué tiene sin commitear.',
            'Clona GIT_REPO_URL, o corre git fetch --all y git reset --hard al '
            'upstream, descartando antes los cambios locales del VPS si se '
            'aceptó.',
            'Crea el venv del servidor si falta y corre su pip install -r '
            'requirements.txt.',
            'Copia por scp los archivos de SECRET_FILES con chmod 600.',
            'Corre alembic upgrade head en el VPS, con el python de su venv y la '
            'base vista desde ahí.',
            'Comprueba que la unidad exista y corre systemctl restart del '
            'servicio del repo.',
        ],
    ),

    'upload_secret_files': CommandDoc(
        summary=(
            'Copia al VPS los archivos que no viajan por git: el .env, los '
            'certificados, las credenciales.'
        ),
        steps=[
            'Resuelve el destino SSH del repo.',
            'Lee SECRET_FILES de la configuración y termina si está vacía.',
            'Recorre las rutas una por una y saltea con aviso las que no existen '
            'en el repo.',
            'Copia por scp cada una a la misma ruta relativa del VPS, con chmod '
            '600.',
            'Informa cuántos de los archivos pedidos viajaron.',
        ],
    ),

    # --- VPS · setup -------------------------------------------------------

    'install_software': CommandDoc(
        summary='Instala en el VPS los paquetes apt de los grupos marcados.',
        steps=[
            'Traduce los grupos marcados a nombres de paquete apt y corta si '
            'alguno es desconocido.',
            'Consulta con dpkg -s cuáles ya están instalados y los informa.',
            'Termina si no falta ninguno.',
            'Corre apt-get update con DEBIAN_FRONTEND=noninteractive.',
            'Corre apt-get install -y con los paquetes que faltan.',
        ],
    ),

    'refresh_known_host': CommandDoc(
        summary='Borra del known_hosts de esta máquina la huella vieja del VPS.',
        steps=[
            'Lee VPS_IP de la configuración del repo.',
            'Corre ssh-keygen -R contra ese host.',
        ],
    ),

    'setup_ssh_key': CommandDoc(
        summary=(
            'Crea en el VPS la cuenta de despliegue, le instala la clave de esta '
            'máquina y le deja sudo sin contraseña.'
        ),
        steps=[
            'Genera con ssh-keygen -t ed25519 el par local de VPS_KEY_NAME si no '
            'existe, con el nombre del repo como comentario.',
            'Pide la contraseña de root una vez y se conecta como root.',
            'En esa misma conexión: crea el usuario si no existe, lo agrega al '
            'grupo sudo, prepara su ~/.ssh en 700, agrega la clave pública a '
            'authorized_keys si no estaba, y deja el archivo en 600 a nombre del '
            'usuario.',
            'Arma la regla de sudo según el modo elegido: todos los comandos, '
            'solo los que Consola usa, o ninguna regla.',
            'Escribe esa regla en /etc/sudoers.d, la deja en 440 y la valida con '
            'visudo -cf.',
            'Prueba el login con la clave e informa el resultado.',
        ],
    ),

    'setup_github_ssh': CommandDoc(
        summary=(
            'Genera la deploy key en el VPS y la registra en la cuenta de '
            'GitHub.'
        ),
        steps=[
            'Comprueba si el VPS ya tiene ~/.ssh/id_ed25519.pub.',
            'Si falta, prepara ~/.ssh en 700 y corre ssh-keygen -t ed25519 sin '
            'passphrase.',
            'Lee la clave pública del VPS.',
            'Busca en GitHub una llave con el título GITHUB_KEY_TITLE.',
            'La deja como está si coincide, la borra y la vuelve a crear si '
            'difiere, o la crea si no existe.',
            'Corre ssh -T contra github.com desde el VPS y confirma que la '
            'respuesta diga que autenticó.',
        ],
    ),

    'configure_coturn': CommandDoc(
        summary=(
            'Escribe /etc/turnserver.conf con el realm, los puertos y el secreto '
            'del repo, abre sus puertos y deja coturn corriendo.'
        ),
        steps=[
            'Comprueba que el paquete coturn esté instalado en el VPS y corta si '
            'no está.',
            'Toma el realm de PUBLIC_HOST, el puerto de TURN_PORT y el rango de '
            'TURN_RELAY_RANGE, y corta si el rango está invertido.',
            'Toma TURN_SECRET de la configuración del repo, o lo genera y lo '
            'guarda ahí.',
            'Arma el turnserver.conf con el puerto de escucha, fingerprint, '
            'use-auth-secret con ese secreto, el realm, el rango de relay y la '
            'IP pública como external-ip.',
            'Si se pidió TLS, comprueba el certificado y la clave en el VPS y '
            'agrega tls-listening-port 5349 con cert y pkey.',
            'Muestra el diff contra el archivo actual y lo escribe con tee si '
            'cambió.',
            'Descomenta TURNSERVER_ENABLED en /etc/default/coturn.',
            'Abre en ufw el puerto de escucha en TCP y UDP, el rango de relay en '
            'UDP y el 5349 si hay TLS.',
            'Corre systemctl enable de coturn.',
            'Corre systemctl restart si la configuración cambió, o systemctl '
            'start si quedó igual.',
            'Consulta systemctl is-active y corta si coturn no quedó activo.',
            'Imprime las URLs turn: para cargar en el backend.',
        ],
    ),

    'configure_caddy': CommandDoc(
        summary=(
            'Escribe /etc/caddy/Caddyfile desde la tabla PUBLIC_ROUTES, abre el 80 '
            'y el 443 y deja Caddy sirviendo con HTTPS automático.'
        ),
        steps=[
            'Comprueba que el paquete caddy esté instalado en el VPS y que haya '
            'PUBLIC_HOST.',
            'Lee PUBLIC_ROUTES y resuelve el destino de cada regla: la dirección '
            'de un proxy, la ruta de subida del build para una SPA, la carpeta '
            'declarada para un estático. Cada $CLAVE se reemplaza por su valor.',
            'Comprueba que existan en el VPS las carpetas de las reglas '
            'estáticas y corta si falta alguna.',
            'Agrupa las reglas por host y arma un bloque de sitio por cada uno, '
            'con la compresión, las cabeceras de seguridad, la CSP de ese sitio '
            'si está cargada, y un handle por regla en el orden de la tabla.',
            'Guarda una copia de referencia en .consola/.',
            'Corre mkdir -p /etc/caddy.',
            'Si /etc/caddy/Caddyfile es un symlink, lo informa y lo borra.',
            'Muestra el diff contra el archivo actual y lo escribe con tee si '
            'cambió.',
            'Corre caddy validate sobre el archivo, si cambió.',
            'Abre 80/tcp, 443/tcp y 443/udp en ufw.',
            'Corre systemctl enable de caddy.',
            'Corre systemctl restart si el archivo cambió, o systemctl start si '
            'quedó igual.',
            'Consulta systemctl is-active y corta si Caddy no quedó activo.',
            'Imprime qué URL termina en qué app.',
        ],
    ),

    'bootstrap_vps': CommandDoc(
        summary=(
            'Lleva un VPS recién creado hasta la app del repo sirviendo: acceso, '
            'software, deploy key, código, base y servicio.'
        ),
        steps=[
            'Corre ssh-keygen -R contra VPS_IP.',
            'Crea la cuenta de despliegue como root, le instala la clave, '
            'escribe su regla de sudo y prueba el login.',
            'Instala con apt los paquetes de los grupos marcados.',
            'Genera la llave del VPS, la registra en GitHub y comprueba el '
            'acceso con ssh -T.',
            'Publica el código: git push local, clon o git reset --hard en el '
            'VPS, venv con dependencias y archivos de SECRET_FILES.',
            'Crea la base contra el VPS: rol, base, permisos, extensiones, '
            'alembic upgrade, particiones y seeders.',
            'Escribe la unidad systemd, abre el puerto si corresponde, corre '
            'enable y restart, y comprueba is-active.',
        ],
    ),

    # --- Base de datos -----------------------------------------------------

    'bootstrap_db': CommandDoc(
        summary=(
            'Deja una base usable desde cero: rol, base, permisos, extensiones, '
            'migraciones, particiones y datos. Lo que crea objetos va por el '
            'canal de superusuario: psql local, o sudo -u postgres psql por SSH '
            'contra el VPS.'
        ),
        steps=[
            'Abre el canal de superusuario del ámbito elegido.',
            'Crea el rol de la aplicación si no existe.',
            'Corre ALTER ROLE con la contraseña de la configuración.',
            'Crea la base con ese rol como dueño, o le cambia el dueño si ya '
            'existe.',
            'Corre GRANT ALL PRIVILEGES sobre la base y GRANT ALL sobre el '
            'esquema public.',
            'Por cada nombre de DB_EXTENSIONS consulta pg_available_extensions y '
            'corre CREATE EXTENSION IF NOT EXISTS, salteando las que el sistema '
            'no tiene.',
            'Corre alembic upgrade head, del lado que diga el ámbito.',
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
        summary='Genera con Alembic la revisión pendiente y la aplica.',
        steps=[
            'Anota qué archivos hay en alembic/versions.',
            'Abre la base del ámbito, con túnel SSH si es la del VPS.',
            'Corre alembic revision --autogenerate en esta máquina, con el '
            'python del venv del servidor.',
            'Compara los archivos de alembic/versions e informa la revisión '
            'generada, o que el modelo no cambió.',
            'Corre alembic upgrade head, en esta máquina o en el VPS según el '
            'ámbito.',
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
            'Trae a esta máquina un volcado de la base del VPS en formato custom '
            'de pg_dump, y rota los respaldos viejos.'
        ),
        steps=[
            'Resuelve el destino SSH y las credenciales de la base.',
            'Comprueba que el VPS tenga pg_dump y corta si falta.',
            'Le pregunta al Postgres del VPS en qué puerto escucha.',
            'Corre pg_dump -Fc en el VPS contra 127.0.0.1 como el rol de la '
            'aplicación, dejando el archivo en /tmp con la fecha y hora en el '
            'nombre.',
            'Lo baja por scp a la carpeta .backups del repo.',
            'Borra el archivo temporal del VPS.',
            'Ordena los respaldos por fecha, deja los más nuevos y borra los que '
            'sobran, nombrando cada uno.',
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

    'inspect_db': CommandDoc(
        summary='Lista las tablas de la base con su cantidad de filas.',
        steps=[
            'Abre el canal de superusuario del ámbito elegido.',
            'Consulta pg_stat_user_tables ordenando por filas vivas.',
            'Vuelca el resultado en la consola, una tabla por línea.',
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

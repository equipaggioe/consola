"""Long descriptions of the commands.

For the right panel's help section.

A `Capability`'s `description` is one line: enough for the rail's
tooltip and the header. The long text lives here: what the command does
and which steps it runs, in order.

Only what the button does. The `steps` are the exact trail of the run,
in the real order: one operation per line and one line per branch the
code takes. They are not the panel's checkboxes, since one checkbox
abstracts several operations, but the plumbing: what is read from disk,
what goes over SSH, which binary runs and with which flags. Reading the
list from top to bottom has to be enough to tell whether a step is
missing, extra or out of order.

The text draws as plain text (`widgets/command_info_panel.py`), so it
carries no markup: no backticks or tags.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication

from app.services.language import QT_TRANSLATE_NOOP


@dataclass(frozen=True)
class CommandDoc:
    """The long text of one command."""

    summary: str  # what it does
    # what it runs, in order
    steps: list[str] = field(default_factory=list)


DOCS: dict[str, CommandDoc] = {
    # --- Run ---
    "backend": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Levanta con uvicorn el servidor FastAPI del repo y publica su URL para "
            "el resto de la sesión. El ámbito elige la base: la de esta máquina, o "
            "la del VPS por un túnel SSH que se cierra al detener la pestaña.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Ubica el servidor elegido: la carpeta cuyo app/main.py o main.py crea "
                "FastAPI(, o que tiene alembic.ini y app/main.py. Toma el intérprete de "
                "su venv.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Toma el puerto preferido, o el siguiente libre si está ocupado."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Publica ese puerto en la sesión del repo."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma la línea de uvicorn con el módulo donde se encontró la app "
                "(app.main:app o main:app), --host y --port, y le agrega --reload si "
                "está marcado.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca certs/cert.pem y certs/key.pem en la carpeta del servidor; si los "
                "dos existen, agrega --ssl-certfile y --ssl-keyfile.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Abre la base del ámbito: local arma la URL contra 127.0.0.1 y el puerto "
                "del Postgres de esta máquina; remoto pregunta el puerto real al "
                "Postgres del VPS, abre el túnel SSH y arma la URL contra el extremo "
                "local del túnel.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Anuncia como endpoint de la pestaña http://localhost:PUERTO, o https si "
                "hay certificados.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre uvicorn desde la carpeta del servidor, con DATABASE_URL en el entorno.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Al terminar, olvida el puerto publicado y cierra el túnel."
            ),
        ],
    ),
    "serve_vite": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Arranca el dev server de Vite de una SPA del repo, apuntado al backend "
            "de esta sesión. Marcar varias apps abre una pestaña por cada una.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Ubica la carpeta de la SPA elegida."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Toma el puerto preferido, o el siguiente libre si está ocupado."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Espera hasta 90 segundos el endpoint del backend de esta sesión, y "
                "sigue igual si no aparece.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Anuncia http://localhost:PUERTO como endpoint de la pestaña."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre pnpm run dev con --port desde la carpeta de la SPA, con "
                "VITE_SERVER_URL puesto en la URL del backend cuando la hay.",
            ),
        ],
    ),
    "run_mobile": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Corre la app móvil del repo sobre un emulador vivo. El framework sale "
            "de la carpeta de la app.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Ubica la app móvil elegida."),
            QT_TRANSLATE_NOOP("command_docs", "Detecta si es Flutter o Flet por su manifiesto."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Elige el emulador, en este orden: el indicado a mano, el que lanzó la "
                "pestaña Emulador de esta sesión, y el primero que conteste por adb.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corta si no hay ningún emulador vivo."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve la URL de la API: API_URL de la configuración, o el endpoint "
                "del backend de esta sesión esperándolo hasta 90 segundos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si es Flutter, corre flutter run -d SERIAL con "
                "--dart-define=API_BASE_URL desde la carpeta de la app.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si es Flet, corre flet run --android desde esa carpeta, con "
                "API_BASE_URL en el entorno.",
            ),
        ],
    ),
    "run_python": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Arranca una app Python del repo que no sea el servidor (PySide6, Flet "
            "de escritorio, un bot). Marcar varias apps abre una pestaña por cada "
            "una.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Ubica la app elegida y su punto de entrada: src/main.py, y si no main.py.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Toma el intérprete del venv de la app; si no tiene, el del venv de la "
                "raíz del repo; si tampoco, el Python del PATH.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Espera hasta 90 segundos el endpoint del backend y, si aparece, lo pone "
                "en SERVER_URL; si no, sigue sin él.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Agrega TERMINAL_DEV_AUTO_LOGIN al entorno si la casilla de auto-login "
                "está marcada.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                'Sin la casilla "Relanzar al detectar cambios": corre python main.py una '
                "sola vez, desde la carpeta del punto de entrada.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Con ella (el default): corre python main.py y, en paralelo, compara "
                "cada medio segundo las fechas de modificación de los .py y .qss de esa "
                "carpeta, sin venv ni artefactos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Si algún fuente cambió, mata el proceso y su árbol y lo relanza."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Si el proceso termina solo, informa el código de salida y cierra."
            ),
        ],
    ),
    "dev_env": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Lanza backend, SPA y apps Python a la vez, cada uno en su propia "
            "pestaña, con los parámetros que cada botón tiene guardados para este "
            "repo.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Recorre los pasos marcados y busca cada uno como capacidad del catálogo.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Lanza Backend en su propia pestaña."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lanza SPA Vite en la suya, sin esperar al anterior."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lanza App Python en la suya, sin esperar al anterior."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Informa en la consola cuáles quedaron lanzados."),
        ],
    ),
    # --- Build ---
    "build_flutter": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Compila la app Flutter o Flet del repo para las plataformas marcadas "
            "(APK, AAB, web, escritorio, iOS).",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Ubica la app elegida."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Detecta si la app es Flutter o Flet y lee API_URL de la configuración.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Por cada plataforma corre flutter build <plataforma> --release, o flet "
                "build <plataforma>, con --dart-define=API_BASE_URL.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca el build donde lo deja el framework y, si BUILD_OUT_<PLATAFORMA> "
                "tiene una carpeta, lo copia ahí.",
            ),
        ],
    ),
    "build_vite": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja compiladas las SPA marcadas del repo. Las recorre de a una, en un solo log.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Ubica la carpeta de la primera SPA marcada."),
            QT_TRANSLATE_NOOP("command_docs", "Corre pnpm install en la carpeta de la SPA."),
            QT_TRANSLATE_NOOP("command_docs", "Corre pnpm run build."),
            QT_TRANSLATE_NOOP("command_docs", "Busca la salida en dist/ o en build/."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Vuelve al primer paso con la siguiente SPA marcada."
            ),
        ],
    ),
    "build_binary": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Empaqueta una app Python del repo como ejecutable con PyInstaller, con "
            "su versión al día, su huella SHA-256 y su publicación en el VPS.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve el punto de entrada: el escrito, o src/main.py de la única app "
                "Python del repo, o un main.py en la raíz.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Sube desde el entrypoint hasta la primera carpeta con manifiesto, y "
                "escribe ahí un pyproject.toml en 0.0.0 si no hay ninguno.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si el paso de compilar está desmarcado, toma el binario que ya está en "
                "dist/ y salta al checksum y la subida.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Abre una copia reversible del manifiesto."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Escribe la versión nueva en el manifiesto, según el modo elegido."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma la etiqueta del ejecutable: el nombre escrito o el de la app, más "
                "sistema y arquitectura.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si hay BRAND_ICON, lo rasteriza como build/icon.ico con los lados de 16 a 256.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre pyinstaller con --noconfirm, --name, --specpath build, --onefile "
                "y --windowed según los ejes, e --icon si hay BRAND_ICON, desde la "
                "carpeta de la app.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba que el artefacto haya quedado en dist/ y corta si no está.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Calcula su SHA-256 y lo escribe al lado como .sha256, en formato sha256sum.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Copia por scp el binario con chmod 755, después el manifiesto y después "
                "el checksum.",
            ),
        ],
    ),
    # --- Images ---
    "generate_icons": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja el logo del repo, BRAND_ICON, como ícono de cada app marcada, con "
            "la capa frontal de Android y la maskable de PWA donde la app las pida. "
            "Se ofrecen las apps que declaran dónde va su ícono: Flutter con sección "
            "flutter_launcher_icons, Flet con src/assets/icon.png, y SPA con un "
            '<link rel="icon"> o "apple-touch-icon", o con un <link rel="manifest"> '
            "a su manifest.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si BRAND_ICON, o una capa escrita (BRAND_ICON_FOREGROUND, "
                "BRAND_ICON_MASKABLE), no es un SVG que exista.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Por cada app marcada, antes de escribir nada, junta sus archivos de "
                "ícono. Flutter: las rutas image_path y adaptive_icon_foreground del "
                "pubspec.yaml; corta si falta el paquete en dev_dependencies, si no "
                "declara image_path o si pide otra imagen. Flet: src/assets/icon.png. "
                "SPA: el <link> del +layout.svelte cuando importa de $lib/, los de "
                "app.html e index.html resueltos en static/ o public/, y los íconos del "
                'manifest que enlaza <link rel="manifest">, leído como JSON. Corta si el '
                "plugin de PWA genera el manifest desde vite.config (le falta manifest: "
                "false).",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                'Un PNG sin sizes="NxN", o no cuadrado, corta. Un ícono del manifest con '
                "purpose maskable lleva la capa maskable; uno que es any y maskable a la "
                "vez corta.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si la app pide una capa que no está configurada, y abre la "
                "configuración en esa clave.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Escribe cada archivo según su extensión: .svg copia la capa tal cual; "
                ".png la rasteriza con Qt al lado declarado (1024 en Flutter y Flet); "
                ".ico la rasteriza con los lados de 16 a 256. Corta si el SVG no es "
                "cuadrado.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Escribe cada archivo solo si cambió, y dice si es nuevo, actualizado o "
                "sin cambios.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Flutter: corre dart run flutter_launcher_icons desde la carpeta de la "
                "app, que reparte el ícono en cada plataforma.",
            ),
        ],
    ),
    "shoot_screens": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Corre la cámara del repo, el script de SHOTS_CMD, con las apps, temas e "
            "idiomas marcados, y comprueba que dejó una captura por cada combinación.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs", "Ubica cada app marcada entre las SPA y las apps móviles del repo."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si hay una app móvil marcada y no se eligió emulador, corta antes de empezar.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Borra de SHOTS_RAW las capturas de las combinaciones que se van a "
                "volver a sacar.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si hay una app móvil: usa el AVD elegido si ya está encendido; si no, "
                "lo enciende y espera a que termine de arrancar.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre SHOTS_CMD desde la raíz del repo, agregándole --apps, --themes, "
                "--languages, --output, --kit con la ruta del kit de la cámara y, con "
                "app móvil, --device. Con app móvil, el adb del SDK va primero en el "
                "PATH de la cámara.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Si encendió el emulador, lo apaga por adb."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee SHOTS_RAW y corta si un archivo no se llama "
                "<pantalla>.<tema>.<idioma>.png o si falta alguna combinación.",
            ),
        ],
    ),
    "render_shots": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Convierte las capturas crudas de SHOTS_RAW al formato de cada destino "
            "marcado y deja un manifiesto por destino.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si algún destino marcado no tiene preset en "
                "assets/shots_presets.json, si ninguna captura es de un tipo que le "
                "sirva, o si una captura no cumple sus reglas (Play) o no cabe en "
                "ninguna de sus medidas sin recortar de más (App Store). Lo revisa para "
                "todos los destinos antes de convertir nada.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee SHOTS_RAW y corta ante una carpeta que no es una app del repo o un "
                "archivo con otro nombre.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Landing: por cada captura, la achica al ancho tope de su tipo de app "
                "(nunca la agranda) y la guarda como .webp en SHOTS_PUBLISH, con el "
                "mismo nombre.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Play y Manual: PNG a resolución nativa, sin canal alfa, en SHOTS_DIST.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "App Store, Open Graph y Redes sociales: escala hasta cubrir la medida "
                "exacta del preset y recorta del centro, en SHOTS_DIST.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Press kit: los crudos sin comprimir en un ZIP."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Escribe un screenshots.json por destino con el hash de cada archivo, y "
                "dice qué archivos cambiaron, cuáles son nuevos y cuáles ya no están "
                "respecto de la corrida anterior.",
            ),
        ],
    ),
    "screenshots": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Saca las capturas de las apps del repo y las revela para los destinos "
            "marcados, en un solo log.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si Sacar capturas está marcado, corre la cámara del repo como el botón "
                "Sacar capturas.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si Revelar capturas está marcado, convierte lo que haya en SHOTS_RAW "
                "como el botón Revelar capturas.",
            ),
        ],
    ),
    # --- Emulators ---
    "install_system_image": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Descarga del SDK la máquina virtual (system image) sobre la que después "
            "corre un AVD.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve el SDK de Android por ANDROID_SDK_ROOT, ANDROID_HOME o las "
                "rutas habituales.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee del id del paquete la API, la variante y la arquitectura, y las informa.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Consulta sdkmanager --list_installed y termina si la máquina ya está.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sdkmanager con el id del paquete y sigue su salida hasta el final.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Olvida la caché de imágenes instaladas."),
        ],
    ),
    "create_avd": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Crea un dispositivo virtual a partir de un modelo del catálogo del SDK "
            "y de una máquina virtual instalada.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Resuelve el SDK de Android."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Pregunta el nombre del AVD, mostrando el derivado del dispositivo y la "
                "API; vacío usa ese derivado, saneado a lo que acepta avdmanager.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Si ya existe un AVD con ese nombre, salta la creación."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba que la máquina virtual elegida esté instalada y corta si no lo está.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre avdmanager create avd con el nombre, el paquete de la imagen y el "
                "perfil del dispositivo.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Escribe hw.keyboard=yes en el config.ini del AVD."),
            QT_TRANSLATE_NOOP("command_docs", "Olvida la caché de AVD."),
        ],
    ),
    "launch_emulator": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Arranca uno de los AVD ya creados y sigue su salida hasta que se cierra.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve el SDK y comprueba que el AVD exista en emulator -list-avds.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Consulta los emuladores vivos; si ese mismo AVD ya corre, marca esta "
                "copia como -read-only.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma la lista de flags: los de siempre (-no-boot-anim, -netdelay none, "
                "-netspeed full), los de las casillas marcadas, el -gpu elegido y el "
                "campo libre partido en tokens.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Toma un puerto libre y arma con él el serial (emulator-5554)."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Publica ese serial en la sesión de la máquina."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Engancha el cierre de la pestaña a adb emu kill sobre ese serial."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre emulator -avd con ese puerto y esos flags, más -read-only y "
                "-wipe-data si corresponden, y sigue su salida.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Al cerrarse, olvida el serial publicado."),
        ],
    ),
    "purge_emulators": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Borra los AVD y las máquinas virtuales marcados. En simulacro los lista "
            "con su tamaño.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Resuelve el SDK y termina si no hay nada marcado."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Mide la carpeta .avd de cada AVD marcado y lo lista con su tamaño.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lista las máquinas marcadas con su etiqueta legible."
            ),
            QT_TRANSLATE_NOOP("command_docs", "En modo simulacro, termina."),
            QT_TRANSLATE_NOOP("command_docs", "Pide escribir BORRAR y cancela si no coincide."),
            QT_TRANSLATE_NOOP("command_docs", "Corre avdmanager delete avd por cada AVD marcado."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre sdkmanager --uninstall por cada máquina marcada."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Olvida las cachés de AVD y de imágenes instaladas."
            ),
        ],
    ),
    # --- Deployment and VPS ---
    "ssh_login": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Abre una sesión SSH interactiva contra el VPS del repo, en una terminal del sistema.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve el destino VPS_USER en VPS_IP y la identidad VPS_KEY_NAME de ~/.ssh.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma la línea de ssh con esa identidad y sus opciones de conexión.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "La lanza en una terminal externa y devuelve el control."
            ),
        ],
    ),
    "health_check": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Informa el estado del VPS: acceso, servicio, GET /api/health, uptime, "
            "carga, disco, memoria y últimos errores del journal. Falla si la API no "
            "responde 204.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra por la cuenta que administra o por root, y corta si no entra.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre systemctl cat y systemctl is-active del servicio."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Pide GET /api/health al 8000, por loopback."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre uptime -p, uptime para la carga, df -h de la raíz y free -h.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre journalctl -u SERVICIO -p err -n 10 con sudo -S."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Vuelca cada dato en la consola con su nombre."),
        ],
    ),
    "view_events": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Muestra lo que el servidor dice que hay que vigilar: el último evento, "
            "el último crítico, el último respaldo y el disco.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Lee HEALTH_TOKEN de la configuración."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Pide GET /api/health/events al 8000 por loopback, con el token por stdin.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corta si no responde 200."),
            QT_TRANSLATE_NOOP("command_docs", "Vuelca cada dato en la consola con su nombre."),
        ],
    ),
    "run_command": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs", "Corre un comando suelto en el VPS y trae su salida a la pestaña."
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Corta si el campo del comando está vacío."),
            QT_TRANSLATE_NOOP("command_docs", "Resuelve el destino SSH del repo."),
            QT_TRANSLATE_NOOP("command_docs", "Manda el comando tal cual por SSH."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Vuelca su salida en la consola a medida que llega."
            ),
        ],
    ),
    "revoke_ssh": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Saca del VPS la clave pública con la que entra esta máquina y borra el par local.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee VPS_KEY_NAME y ubica el par en ~/.ssh; corta si falta la privada.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Deriva la clave pública y la muestra recortada."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Reescribe ~/.ssh/authorized_keys del VPS sin esa línea exacta, pasando "
                "por un temporal que después reemplaza al original. Corta si no entra, "
                "si la línea no está o si es la última.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Borra en esta máquina la clave privada y su .pub, solo si lo anterior "
                "salió bien.",
            ),
        ],
    ),
    "clean_vps": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deshace en el VPS lo que instaló canone, con uninstall.py de canone. "
            "Cada nivel incluye al anterior.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra por la cuenta que administra, con sudo, y sube plantilla/infra/ de canone.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "La base: detiene el servidor y sus timers, y borra la base, sus roles, "
                "sus credenciales, su línea de pg_hba y los archivos de los usuarios.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "La app: además, cada unidad, sitio, credencial, cuenta y carpeta de la app.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "La máquina: además el swap, uv, el túnel del journal y los archivos que "
                "install.py escribe para toda la máquina. Los paquetes quedan: dejarlo "
                "como lo entrega el proveedor es reinstalarlo desde su panel.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Ningún nivel toca la cuenta que administra, sus llaves ni el sshd, y "
                "root sigue bloqueado. En simulacro solo lista lo que haría.",
            ),
        ],
    ),
    # --- Deployment ---
    "publish_release": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Publica una versión: crea el tag siguiente, espera a que release.yml "
            "publique el release, firma su .sha256 en esta máquina y lo despliega "
            "con deploy.py de canone.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si hay cambios sin commitear, si la rama no tiene rama en origin "
                "o si tiene commits que origin no tiene.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee con git ls-remote los tags v* de origin y sube el más alto según el "
                "eje: major, minor o patch. Sin ninguno, sube desde v0.0.0.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Crea el tag anotado y lo empuja a origin."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca con gh run list la corrida de release.yml del tag, cada 5 "
                "segundos durante un minuto.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Pregunta con gh run view su estado cada 15 segundos hasta que termina. "
                "Si no termina bien, muestra el log de los pasos que fallaron y corta.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Sin «Crear tag», toma el último release publicado de GitHub."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee con gh release view los archivos del release. Si ya tiene "
                "<app>-<tag>.sha256.sig hecha con VPS_KEY_NAME, no lo vuelve a firmar; "
                "si la hizo otra llave, lo firma de nuevo y reemplaza la firma; sin "
                ".sha256, corta.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Baja el .sha256 con gh release download a una carpeta temporal."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lo firma con ssh-keygen -Y sign -n deploy y la llave VPS_KEY_NAME.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Sube la firma con gh release upload --clobber."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre los pasos de «Desplegar versión» con ese tag."
            ),
        ],
    ),
    "deploy_version": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs", "Instala en el VPS un release ya firmado, con deploy.py de canone."
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lista con gh api los releases del repo que tienen su <app>-<tag>.sha256.sig.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER, con la contraseña de sudo de SUDO_PASSWORD o "
                "pedida una vez por sesión. Corta si la cuenta todavía no existe.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Baja la firma del release y lee /etc/<app>/allowed_signers del VPS. "
                "Si la llave que firmó no está, corta y dice si se agrega con "
                "«Instalar infraestructura» o se firma de nuevo.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo /usr/local/sbin/<app>-deploy <tag>, que baja el release, "
                "comprueba la firma, migra, cambia current y espera la salud; si no "
                "responde y no hubo migraciones, vuelve a la anterior.",
            ),
        ],
    ),
    "systemd_action": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Manda una acción de systemd a la unidad elegida del VPS: una de las que "
            "instaló canone, Caddy o coturn.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si se pide arrancar o reiniciar el respaldo: lo pide la receptora.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Traduce el servicio elegido al nombre real de la unidad."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba con systemctl cat que la unidad exista y corta si no está.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre por SSH sudo -S systemctl ACCIÓN UNIDAD, con la contraseña de la "
                "cuenta por stdin; daemon-reload va sin unidad.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Vuelca la salida en la consola."),
        ],
    ),
    "view_logs": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Muestra el journal del servicio elegido, de una o siguiéndolo en vivo.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs", "Traduce el servicio elegido al nombre real de la unidad."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma el journalctl con la cantidad de líneas, -f si es en vivo, y los "
                "filtros de fecha, prioridad y patrón que estén cargados.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lo corre por SSH con sudo -S, con la contraseña de la cuenta por stdin, "
                "y vuelca la salida a medida que llega.",
            ),
        ],
    ),
    # --- VPS -------------------------------------------------------
    "bootstrap_vps": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja el VPS listo con los programas de canone: paquetes y uv, swap, "
            "install.py con los datos del repo, las credenciales y el último release.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs", "Si está marcado, borra del known_hosts la huella vieja del VPS."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Crea la llave VPS_KEY_NAME en ~/.ssh si falta. Si no entra al VPS, "
                "entra una vez como root con su contraseña (ROOT_PASSWORD, o la pide), "
                "sube authorize.py de canone y lo corre, que la agrega a su "
                "authorized_keys.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre los pasos de «Instalar paquetes base»."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si el swap no llega a la memoria, crea /swapfile con lo que falta, lo "
                "activa y lo agrega a /etc/fstab.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lee de git remote el dueño y el nombre del repo en GitHub."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si VALKEY_MEMORY está vacía, lee la RAM del VPS y la calcula con VALKEY_PERCENT.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma los argumentos de install.py: DOMAIN, la memoria de Valkey, "
                "--owner, --admin VPS_USER, las dos llaves (VPS_KEY_NAME y OFFLINE_KEY) "
                "como --key y --signer, --private, --desktop y --mobile del release.yml, "
                "--without por las piezas que faltan, --allow por cada línea de "
                "permissions, --extension, --turn si Settings declara turn_secret, y "
                "--logs.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "La primera vez corre install.py como root por ssh -tt y escribe la "
                "contraseña de la cuenta cuando la pide, dos veces; después, con sudo "
                "desde VPS_USER.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre los pasos de «Cargar credenciales»."),
            QT_TRANSLATE_NOOP("command_docs", "Borra /tmp/consola-canone."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Toma el último release publicado de GitHub y corta si no tiene su "
                ".sha256.sig. Si /srv/<app>/current ya es ese release, no hace nada; si "
                "no, corta si el VPS no acepta la llave que lo firmó, y lo instala con "
                "deploy.py.",
            ),
        ],
    ),
    "install_software": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs", "Instala en el VPS los paquetes que canone pide para este repo, y uv."
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER si la llave ya lo deja entrar, con la contraseña de "
                "sudo de SUDO_PASSWORD o pedida una vez por sesión; si no, como root con "
                "la misma llave.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Arma la lista: los de la máquina de canone, más PostGIS si "
                "DB_EXTENSIONS la nombra, coturn si Settings declara turn_secret y lo "
                "del journal con LOGS.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre apt-get update y apt-get install -y con DEBIAN_FRONTEND=noninteractive.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone y corre "
                "uv.py, que instala la versión de uv que fija canone.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Borra /tmp/consola-canone."),
        ],
    ),
    "load_credentials": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs", "Pasa las credenciales de config.env a credentials.py de canone."
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs", "Lee los campos de Settings de server/src/app/config.py."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Si Settings declara setup_code y SETUP_CODE está vacío, genera uno de 6 "
                "dígitos, lo guarda en config.env y lo muestra.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si config.env tiene una clave que no es de Consola ni un campo, o "
                "si falta el valor de un campo o de RESTIC_PASSWORD (y de GITHUB_TOKEN "
                "con PRIVATE).",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER si la llave ya lo deja entrar, con la contraseña de "
                "sudo de SUDO_PASSWORD o pedida una vez por sesión; si no, como root con "
                "la misma llave.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corta si todavía no existe la cuenta que administra."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo python3 credentials.py <app> y le pasa por stdin una línea "
                "campo=valor por credencial; nada de eso va al log.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Borra /tmp/consola-canone."),
        ],
    ),
    "load_setup_code": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Carga en el VPS el código con que se registra el superadministrador; "
            "si está vacío, genera uno y lo muestra.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Toma SETUP_CODE de la configuración del repo. Si está vacío, genera uno de "
                "6 dígitos, lo guarda ahí y lo muestra en el log.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER y sube plantilla/infra/ de CANONE_DIR a /tmp/consola-canone.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo python3 credentials.py <app> con la sola línea setup_code=…; "
                "credentials.py la cifra y reinicia el servidor.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Borra /tmp/consola-canone."),
        ],
    ),
    "refresh_known_host": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs", "Borra del known_hosts de esta máquina la huella vieja del VPS."
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Lee VPS_IP de la configuración del repo."),
            QT_TRANSLATE_NOOP("command_docs", "Corre ssh-keygen -R contra ese host."),
        ],
    ),
    # --- Database ---
    "bootstrap_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja la base local usable desde cero: rol, base, permisos, extensiones, "
            "migraciones, particiones y datos. Lo que crea objetos va por psql como "
            "superusuario.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Abre el canal de superusuario local."),
            QT_TRANSLATE_NOOP("command_docs", "Crea el rol de la aplicación si no existe."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre ALTER ROLE con la contraseña de la configuración."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Crea la base con ese rol como dueño, o le cambia el dueño si ya existe.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre GRANT ALL PRIVILEGES sobre la base y GRANT ALL sobre el esquema public.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Por cada nombre de DB_EXTENSIONS consulta pg_available_extensions y "
                "corre CREATE EXTENSION IF NOT EXISTS; corta si el sistema no la tiene.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre alembic upgrade head."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre el mantenimiento de particiones del proyecto con el python de su venv.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Ejecuta en orden las funciones seed_ del paquete seeders/, con un solo "
                "commit al final.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Ejecuta las del paquete mock_data/, si está marcado."
            ),
        ],
    ),
    "enable_extensions": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Crea en la base local las extensiones de Postgres que declara "
            "DB_EXTENSIONS, por el canal de superusuario. En el VPS las crea "
            "install.py.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs", "Lee DB_EXTENSIONS, descarta repetidos y termina si queda vacía."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Abre el canal de superusuario local con psql."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Consulta pg_available_extensions por cada nombre y corta si el sistema "
                "no la tiene.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre CREATE EXTENSION IF NOT EXISTS sobre la base de la aplicación.",
            ),
        ],
    ),
    "teardown_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Borra la base local de la aplicación y su rol. En el VPS los roles son "
            "de install.py, y la base se vacía con «Reconstruir base».",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Abre el canal de superusuario local."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre pg_terminate_backend sobre las conexiones vivas de esa base.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre DROP DATABASE IF EXISTS."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre DROP ROLE IF EXISTS del rol de la aplicación."
            ),
        ],
    ),
    "migrate_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Genera con Alembic la revisión pendiente y la aplica en la base local.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Anota qué archivos hay en alembic/versions."),
            QT_TRANSLATE_NOOP("command_docs", "Abre la base local."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre alembic revision --autogenerate con el python del venv del servidor.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Compara los archivos de alembic/versions e informa la revisión "
                "generada, o que el modelo no cambió.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre alembic upgrade head."),
        ],
    ),
    "rebuild_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Vacía la base y la vuelve a llenar: migraciones y seeders. En local "
            "borra las tablas; en el VPS corre database.py de canone, paso a paso.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "En local:"),
            QT_TRANSLATE_NOOP("command_docs", "Abre el canal de superusuario local."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lista las tablas del esquema public, salvo spatial_ref_sys, e informa "
                "cuántas son.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre DROP TABLE IF EXISTS CASCADE sobre todas."),
            QT_TRANSLATE_NOOP("command_docs", "Corre alembic upgrade head."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre el mantenimiento de particiones del proyecto."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Ejecuta las funciones seed_ del paquete seeders/."),
            QT_TRANSLATE_NOOP("command_docs", "Ejecuta las del paquete mock_data/."),
            QT_TRANSLATE_NOOP("command_docs", "En el VPS:"),
            QT_TRANSLATE_NOOP("command_docs", "Corta si el README dice Estado: en producción."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER, con la contraseña de sudo de SUDO_PASSWORD o "
                "pedida una vez por sesión; corta si todavía no existe la cuenta que "
                "administra.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo /usr/local/sbin/<app>-database empty: detiene el servidor y "
                "borra la base y los archivos subidos; la crea otra vez vacía.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre database.py migrate: las migraciones y los seeders de la versión "
                "activa, y arranca el servidor.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre database.py seed: los seeders otra vez."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre database.py seed --mock: el paquete mock_data/."
            ),
        ],
    ),
    "reinit_migrations": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Vacía la base local, borra el historial de alembic/versions y escribe "
            "una migración inicial nueva.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lista las tablas del esquema public y las borra con DROP TABLE CASCADE.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Borra uno por uno los .py de alembic/versions, nombrando cada uno.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre alembic revision --autogenerate con el mensaje initial_migration, "
                "en esta máquina.",
            ),
        ],
    ),
    "run_seeders": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Ejecuta las funciones seed_ del paquete seeders/ del proyecto: en local "
            "con el python de su venv, en el VPS con database.py seed.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "En local:"),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lanza por -c el programa de seeders, sin escribir nada en disco."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Recorre el paquete seeders/ y junta todas las funciones que empiezan con seed_.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Las ejecuta en orden dentro de una sesión, nombrando cada una."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Hace rollback y corta si alguna falla, o un solo commit si todas pasan.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "En el VPS:"),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER, con la contraseña de sudo de SUDO_PASSWORD o "
                "pedida una vez por sesión; corta si todavía no existe la cuenta que "
                "administra.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo /usr/local/sbin/<app>-database seed: los seeders de la "
                "versión activa.",
            ),
        ],
    ),
    "run_mock_seeders": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Ejecuta las funciones seed_ del paquete mock_data/ del proyecto: en "
            "local con el python de su venv, en el VPS con database.py seed --mock.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "En local:"),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lanza por -c el mismo programa de los seeders, apuntado al paquete mock_data/.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Recorre el paquete y junta sus funciones seed_."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Las ejecuta en orden y commitea una sola vez al final."
            ),
            QT_TRANSLATE_NOOP("command_docs", "En el VPS:"),
            QT_TRANSLATE_NOOP("command_docs", "Corta si el README dice Estado: en producción."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Entra como VPS_USER, con la contraseña de sudo de SUDO_PASSWORD o "
                "pedida una vez por sesión; corta si todavía no existe la cuenta que "
                "administra.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre sudo /usr/local/sbin/<app>-database seed --mock, que falla en una "
                "máquina sin la marca de desarrollo.",
            ),
        ],
    ),
    "backup_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja un volcado de la base local, en formato custom de pg_dump, y rota "
            "los respaldos viejos.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve la carpeta de respaldos de BACKUP_DIR: relativa cuelga de la "
                "raíz del repo, absoluta se usa tal cual.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Abre la conexión a la base local."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca pg_dump en la instalación local de PostgreSQL y corta si su "
                "versión es más vieja que la del servidor, nombrando las dos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre pg_dump -Fc como el rol de la aplicación, escribiendo directo en "
                "el archivo local, con la fecha y hora en el nombre.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Ordena los respaldos de esta base por fecha, deja los BACKUP_KEEP más "
                "nuevos y borra los que sobran, nombrando cada uno.",
            ),
        ],
    ),
    "restore_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Carga uno de los respaldos guardados sobre la base local, reemplazando lo que haya.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba que el respaldo elegido exista en la carpeta de respaldos.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Abre la conexión a la base local."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca pg_restore en la instalación local de PostgreSQL y corta si su "
                "versión es más vieja que la del servidor.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corre pg_restore como el rol de la aplicación, borrando cada objeto "
                "antes de recrearlo y cortando en el primer error.",
            ),
        ],
    ),
    "ssh_tunnel": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Abre un túnel SSH al Postgres del VPS y lo deja levantado como servicio "
            "de fondo. Entra como <app>_read: lee y no cambia nada.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Resuelve el destino SSH del repo."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Toma el puerto 5432 de este lado, o el siguiente libre."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Levanta el reenvío por SSH al socket /run/postgresql/.s.PGSQL.5432 del VPS.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Informa el extremo local, el rol <app>_read, sin contraseña, y la base <app>.",
            ),
        ],
    ),
    "explore_db": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Abre la base del ámbito en solo lectura y la muestra en la pestaña: "
            "esquemas y tablas a la izquierda, datos y estructura a la derecha. "
            "Queda conectada hasta que cierras la pestaña.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Abre la base del ámbito: la local con el rol de la app contra "
                "127.0.0.1; la del VPS como <app>_read, por un túnel SSH a su socket.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Se conecta en solo lectura: el servidor rechaza cualquier escritura.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Muestra en la consola el servidor, la base, su tamaño y las tablas con "
                "su estimado de filas.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Publica la conexión y cambia a la vista del explorador."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Espera hasta que cierres la pestaña; si el túnel se cae, termina con error.",
            ),
        ],
    ),
    # --- Utils ---
    "clean_artifacts": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Borra las cachés y la basura de build del repo abierto. En simulacro "
            "las lista con su tamaño.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Recorre el repo una sola vez, salteando .git, .consola y las carpetas "
                "pesadas que no se marcaron.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Anota como una unidad las carpetas pesadas marcadas: node_modules, "
                ".venv, build o dist, .dart_tool.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Anota, según las familias marcadas, las carpetas __pycache__, .gradle, "
                ".kotlin y .cxx, los archivos .pyc y .pyo, los residuos de Flutter y los "
                "volcados de crash.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Termina si no encontró nada."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Muestra hasta cuarenta rutas y dice cuántas quedaron sin listar."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Suma el tamaño total en disco y lo informa."),
            QT_TRANSLATE_NOOP("command_docs", "En modo simulacro, termina."),
            QT_TRANSLATE_NOOP("command_docs", "Borra todo lo listado e informa cuánto se liberó."),
        ],
    ),
    "install_android_tools": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Instala las command-line tools del SDK de Android y las deja en el "
            "entorno del usuario.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba que el sistema sea Windows o Linux y que haya Java en el PATH.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Salta la descarga si ya hay un sdkmanager en el directorio elegido.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Lee la página de Android Studio y saca el nombre del zip publicado y su SHA-256.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Descarga el zip informando el avance y atendiendo al botón de detener.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Verifica el SHA-256 del archivo bajado."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Descomprime y reacomoda el contenido para que quede en cmdline-tools/latest.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Crea la carpeta avd/ dentro del SDK."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Escribe ANDROID_SDK_ROOT, ANDROID_HOME y ANDROID_AVD_HOME en el entorno "
                "del usuario.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Agrega al PATH platform-tools, emulator y el bin de las herramientas, "
                "sacando las entradas de instalaciones anteriores.",
            ),
        ],
    ),
    "install_android_packages": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Acepta las licencias e instala en el SDK los paquetes marcados que falten.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Traduce los componentes marcados a ids de sdkmanager, armando "
                "build-tools y platform con la versión y el API level escritos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Resuelve el sdkmanager instalado y la raíz de su SDK."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre sdkmanager --licenses respondiendo que sí a cada licencia."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Consulta sdkmanager --list_installed y descarta lo que ya está."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Termina si no falta ninguno."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Enumera lo que falta y lo instala en una sola corrida de sdkmanager.",
            ),
        ],
    ),
    "install_android_hypervisor": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja lista la aceleración por hardware del emulador: instala el driver "
            "en Windows y verifica /dev/kvm en Linux.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "En Windows, consulta el servicio gvm y termina si el driver ya está instalado.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Descarga el driver con sdkmanager y comprueba que aparezca su "
                "silent_install.bat.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Lanza ese instalador pidiendo elevación, en una ventana aparte."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "En Linux, comprueba que exista /dev/kvm y corta explicando la "
                "virtualización de la BIOS y el módulo del kernel si falta.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Comprueba que este usuario tenga lectura y escritura sobre /dev/kvm, y "
                "escribe el usermod exacto si no las tiene.",
            ),
        ],
    ),
    "install_android_sdk": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Deja esta máquina lista para compilar y emular Android: herramientas, "
            "paquetes y aceleración.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Descarga y verifica las command-line tools, las deja en "
                "cmdline-tools/latest y escribe las variables y el PATH del usuario.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Acepta las licencias e instala los componentes marcados que falten, con "
                "el API level y el build-tools escritos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Instala el driver del hipervisor en Windows, o verifica /dev/kvm en Linux.",
            ),
        ],
    ),
    "install_flutter_sdk": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Instala el SDK de Flutter del canal stable y lo deja en el entorno del usuario.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Comprueba que haya Git en el PATH."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Salta la descarga si ya hay un flutter en el directorio elegido."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Consulta el índice oficial de releases y saca el archivo y el SHA-256 "
                "del canal stable.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Descarga el paquete informando el avance."),
            QT_TRANSLATE_NOOP("command_docs", "Verifica su SHA-256."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Descomprime y renombra la carpeta que trae el zip si el destino tiene "
                "otro nombre.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Escribe FLUTTER_HOME y agrega su bin al PATH del usuario, sacando las "
                "entradas de instalaciones anteriores.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Corre flutter --version."),
            QT_TRANSLATE_NOOP("command_docs", "Corre flutter doctor."),
        ],
    ),
    "update_cloudflare": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Apunta a la IP elegida, sin el proxy de Cloudflare, el registro A de "
            "cada host de la app: DOMAIN para landing/, app.DOMAIN para web/ y "
            "panel.DOMAIN para panel/.",
        ),
        steps=[
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Resuelve la IP según el modo: VPS_IP, la detectada preguntándole a un "
                "servicio externo, o la escrita.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Arma los hosts con las piezas web que el repo tiene en su raíz."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Busca en Cloudflare la zona de CF_DOMAIN_NAME con el token de la API.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Por cada host, crea su registro A si falta, lo deja como está si ya "
                "apunta a esa IP sin proxy, o lo cambia con un PUT.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Deja en el log cada cambio."),
        ],
    ),
    "sync_common_files": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Copia los archivos compartidos de este repo a los otros repos "
            "indicados. En simulacro muestra las diferencias.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Corta si no hay ningún repo destino."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Toma la lista de archivos escrita, o los archivos comunes del catálogo "
                "si está vacía.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Saltea con aviso los destinos que no existen como carpeta."
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Compara cada archivo contra su par en cada destino y se queda con los "
                "que faltan o difieren.",
            ),
            QT_TRANSLATE_NOOP("command_docs", "Termina si no hay diferencias."),
            QT_TRANSLATE_NOOP("command_docs", "Lista cada diferencia con su estado y su repo."),
            QT_TRANSLATE_NOOP("command_docs", "En modo simulacro, termina."),
            QT_TRANSLATE_NOOP("command_docs", "Copia archivo por archivo, nombrando cada uno."),
        ],
    ),
    "clone_repo": CommandDoc(
        summary=QT_TRANSLATE_NOOP(
            "command_docs",
            "Clona un repositorio de GitHub en una carpeta nueva y lo abre como "
            "pestaña de Consola.",
        ),
        steps=[
            QT_TRANSLATE_NOOP("command_docs", "Corta si no hay URL o si no hay git en el PATH."),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Toma la carpeta destino escrita; vacía, usa la carpeta que contiene al "
                "repo abierto.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Deriva el nombre de la carpeta del último tramo de la URL, sin .git.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs",
                "Corta si esa carpeta ya existe: clonar encima sería mezclar dos repos.",
            ),
            QT_TRANSLATE_NOOP(
                "command_docs", "Corre git clone, con --branch si se escribió una rama."
            ),
            QT_TRANSLATE_NOOP("command_docs", "Lee el commit corto del clon y lo deja en el log."),
            QT_TRANSLATE_NOOP(
                "command_docs", "Devuelve la carpeta, que la ventana abre como pestaña nueva."
            ),
        ],
    ),
}


def get(capability_id: str) -> CommandDoc | None:
    """Return the command's long text, if it has one.

    In the interface language: `DOCS` builds on import, before the
    translator exists.
    """
    doc = DOCS.get(capability_id)
    if doc is None:
        return None
    return CommandDoc(
        QCoreApplication.translate("command_docs", doc.summary),
        [QCoreApplication.translate("command_docs", step) for step in doc.steps],
    )

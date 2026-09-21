# 18 · Android y emuladores

## 1. Tres actividades, no una

Un emulador no es un botón: son tres cosas que se hacen en momentos distintos y se repiten con frecuencias distintas ([ADR-0027](../adr/0027-emuladores-tres-actividades.md)).

| Botón | Qué hace | Cada cuánto |
|---|---|---|
| `install_system_image` | Baja la máquina virtual del catálogo del SDK | Una vez cada varios meses; son varios GB |
| `create_avd` | Crea el dispositivo virtual con un modelo y una imagen ya bajada | Cuando hace falta otro dispositivo |
| `launch_emulator` | Arranca un AVD y sigue su salida | Todos los días |

Los cuatro botones del grupo (con `purge_emulators`) son `scope='machine'`: un AVD sirve para cualquier proyecto, igual que el SDK, así que sus parámetros se guardan una sola vez y no por repo.

Antes eran tres constantes escritas a mano (`pixel_4`, `pixel_8`, `resizable`) en tres scripts. Esas constantes escondían los catálogos reales del SDK —un centenar de perfiles de dispositivo y varios cientos de system images—, así que un eje `preset` no habría sido una simplificación sino una amputación.

## 2. Los dos catálogos

| Fuente | Qué da | Caché |
|---|---|---|
| `avdmanager list device` | Perfiles de dispositivo | Un mes |
| `sdkmanager --list` | System images publicadas | Un mes |
| `sdkmanager --list_installed` | Imágenes ya bajadas | 60 s |
| `avdmanager list avd` | AVD creados | 60 s |
| `adb devices` + consola del emulador | Emuladores vivos | **Nunca** |

Lo que cambia mientras Consola está abierta se cachea por un minuto: alcanza para no repetir la consulta al abrir tres pestañas seguidas, y no alcanza para mentir después de una instalación. Lo que es estado no se cachea nunca.

Las dos consultas grandes tardan de segundos a decenas de segundos, así que corren fuera del hilo de la interfaz ([12](12_interfaz.md) §6).

## 3. La imagen se elige por característica

El id del SDK trae tres cosas permutadas en un solo paquete: `system-images;android-36;google_apis;x86_64`. Una lista con todas las combinaciones es la misma pregunta hecha trescientas veces.

`AxisDef.facets` declara que ese valor se compone de versión, variante y arquitectura. El panel dibuja **tres listas cortas que se recortan entre sí**, y el valor que se guarda sigue siendo el paquete entero.

El recorte es una cascada, no un filtro cruzado: cada lista se acota con las que están **antes**, nunca con las de abajo. Recortar también hacia arriba parece más listo y deja la primera lista sin salida — con «Play Store» marcado, las versiones que no lo publican desaparecen, y no queda forma de llegar a ellas desde el único control que debería poder cambiarlo todo.

Cambiar una de arriba puede dejar a las de abajo en un valor imposible; esas caen en su mejor opción disponible (`resolve_facets`). Las de arriba no se tocan nunca: lo que uno acaba de elegir no se mueve solo.

`create_avd` **no** usa facetas para su lista de imágenes: ahí solo están las ya bajadas, casi siempre una o dos. Partir dos entradas en tres listas no ahorra ninguna lectura y haría creer que hay un catálogo detrás.

## 4. Arrancar

Tres cosas que el script original no hacía:

- **El puerto se elige antes de arrancar** (`-port`), así el serial (`emulator-5554`) se conoce desde el principio. Sin eso no hay forma de saber cuál de los emuladores vivos es el de esta pestaña, ni de apagarlo limpio, ni de decirle a la app móvil contra cuál correr.
- **Si ese AVD ya está corriendo, la segunda copia va en `-read-only`.** El emulador toma un lock sobre la carpeta del AVD, y sin ese flag el segundo arranque muere con «another emulator instance is running».
- **Detener la pestaña le pide al emulador que se cierre por adb**, no le mata el proceso ([ADR-0028](../adr/0028-apagar-es-cerrar-la-pestana.md)).

Los flags llegan por tres caminos que se **suman**, nunca se reemplazan: los de siempre de `android.DEFAULT_FLAGS`, las casillas del panel (cuyo valor **es** el flag, así que no hace falta una tabla que traduzca) y el campo libre para lo que no esté arriba (`-memory 4096`). El campo se parte en tokens como lo haría una shell.

El nombre de un AVD se pregunta al correr: dos AVD no pueden llamarse igual, así que un nombre guardado solo sirve la primera vez. Vacío es la respuesta normal —se deriva del dispositivo y la API (`pixel_4_api36`)— y se pregunta igual, no solo cuando hay colisión, porque el derivado se muestra ahí mismo: se ve con qué nombre va a quedar antes de que exista.

## 5. Apagar

No hay botón «Apagar emulador» en el menú: cerrar la pestaña ya lo apaga. Para los huérfanos —uno de una sesión anterior, o arrancado desde Android Studio— está el ✕ de la cabecera de estado del panel, que es donde se ven ([ADR-0028](../adr/0028-apagar-es-cerrar-la-pestana.md)).

`stop_emulator` sigue siendo una capacidad, oculta: la corre el mismo runner que a todas las demás, con su log en la consola, en vez de que la interfaz toque `adb` por su cuenta ([ADR-0036](../adr/0036-la-interfaz-no-toca-binarios.md)). Corre con `track=False`, para que cerrar la pestaña no detenga el apagado en vez del emulador.

`live_state` es lo que dibuja ese inventario: la capacidad declara qué fuente consultada se muestra como cabecera de estado, y el panel pone un ✕ por fila.

## 6. Liberar disco

Un solo botón para las dos cosas que ocupan: el AVD pesa cientos de MB y la imagen, varios GB. Se eligen con casillas, se ve la lista con su tamaño, y el modo `simulacro` es el default. Borrar de verdad pide escribir `BORRAR`.

Es el único destructivo que no entra en el seguro por repo, porque no es de ningún repo ([14](14_seguro_de_destructivos.md) §3).

## 7. Instalar el SDK

La instalación se parte en tres atómicas, y cada una tiene su botón además del compuesto:

| Atómica | Por qué va aparte |
|---|---|
| `install_android_tools` | Baja las command-line tools y escribe el entorno. Pasa una vez |
| `install_android_packages` | Es lo que se repite: una API nueva, otro build-tools. No tiene por qué arrastrar la descarga del SDK ni tocar el PATH |
| `install_android_hypervisor` | Es lo único que necesita permisos elevados, y lo que se rompe solo: una actualización del sistema deja el emulador lentísimo sin que el resto haya cambiado |

La URL y el hash de las cmdline-tools **no** son constantes: se leen de la página oficial, porque Google le cambia el número de build a cada versión y una constante vieja falla con un 404 que no explica nada. Lo mismo con el canal stable de Flutter, que se lee de su índice de releases. Las dos descargas informan el avance, atienden a Detener y verifican la huella publicada antes de descomprimir.

En Linux la aceleración no se instala: se **verifica** y, si falta, se explica el comando exacto. Meter la mano con sudo desde una interfaz gráfica sería peor, y además el cambio de grupo no surte efecto hasta reingresar. En Windows se lanza el instalador pidiendo elevación, con un solo aviso de UAC, en vez de exigir que Consola entera corra como administrador.

## 8. El entorno del usuario

`core/userenv.py` escribe `ANDROID_SDK_ROOT`, `ANDROID_HOME`, `ANDROID_AVD_HOME` y el PATH a nivel **usuario**: un bloque delimitado dentro del perfil del shell en POSIX, `HKCU\Environment` en Windows. Nunca a nivel sistema ([ADR-0029](../adr/0029-entorno-a-nivel-usuario.md)).

- El bloque se reescribe entero cada vez, así que reinstalar no deja exports duplicados ni rutas viejas colgando. Se lee antes de escribir porque el bloque es compartido: si Android lo reescribiera sin mirar, borraría lo que dejó Flutter.
- `path_drop` descarta las entradas de una instalación anterior, para poder reinstalar en otro directorio.
- Se aplican también al proceso vivo, así los indicadores de la barra de estado se ponen en verde al terminar y no al siguiente arranque.
- En Windows se avisa si el PATH **del sistema** tiene rutas viejas que le ganan a las nuevas: Windows lo pone primero, así que una entrada dejada por un `setx /M` de antes se impone sobre la que se acaba de escribir.

## 9. Correr la app móvil

`run_mobile` elige el emulador en este orden: el que se pidió a mano, el que arrancó la pestaña «Emulador» de esta sesión (`session.MACHINE`), y recién después el primero que conteste — con dos vivos, «el primero» es una lotería. Sin ninguno lo dice y no intenta arrancar contra el escritorio, que era el modo más fácil de perder diez minutos con `flutter run`.

El eje del emulador admite vacío y arranca vacío: la función ya elige sola, y un eje que obligara a elegir dejaría el botón en ámbar justo cuando no hay ninguno, que es cuando el mensaje útil es el de la función.

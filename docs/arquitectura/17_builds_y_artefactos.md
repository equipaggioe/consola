# 17 · Builds y artefactos

## 1. Un esqueleto, tres builders

Los tres builders son la misma secuencia con un paso propio en el medio:

```
bump del manifiesto → compilar → (checksum) → subir artefacto + manifiesto
```

| Builder | Manifiesto | Paso propio | Eje del objetivo |
|---|---|---|---|
| `build_flutter` | `pubspec.yaml` | `flutter build` o `flet build`, una vez por plataforma marcada | `directory`: una app móvil |
| `build_vite` | `package.json` | `npm install` + `npm run build` | `directories`: varias SPA, en bucle |
| `build_binary` | `pyproject.toml` | PyInstaller | Campos: punto de entrada y nombre |

El bump y la subida son **atómicas compartidas** (`bump_version`, `upload_artifact`), no tres copias. Lo único propio de cada builder es cómo compila.

## 2. El bump es reversible

Todo el tramo que toca el manifiesto va dentro de `files.reversible(manifiesto)`: si el build revienta después de subir la versión, el archivo vuelve a lo que era y el repo no queda marcado con un número que nunca se publicó ([ADR-0025](../adr/0025-bump-reversible.md)).

Un solo bump por corrida por más plataformas que se marquen: el APK y la web de la misma corrida son la misma versión. En `build_vite`, cada SPA es reversible por separado: si la tercera falla, las dos que ya se publicaron conservan la versión con la que salieron.

`versioning.bump` entiende dos partes combinables: el componente SemVer (`major`/`minor`/`patch`/`none`) y, con `+build`, el build number de Flutter (`1.4.22+318`). El `+N` solo existe en `pubspec.yaml`, así que Vite y el binario usan un eje SemVer pelado: ofrecer ahí la casilla `build` sería ofrecer una elección que siempre termina en error.

## 3. Compilar es desmarcable

Sin el paso «Compilar», el builder **sube lo que ya está en disco**. Es el `BUILD_APP=false` / `BUILD_SPA=false` / `BUILD_BINARY=false` de los scripts originales, y la razón es económica: retomar un `scp` cortado no debería costar otro build entero ([ADR-0026](../adr/0026-compilar-es-desmarcable.md)).

En ese modo el bump se ignora con un aviso: lo que hay en disco se compiló con la versión que ya tiene el manifiesto, y subirlo cambiado lo anunciaría como otra cosa. Sin compilar y sin subir no queda nada por hacer, y el botón lo dice.

## 4. Un artefacto nunca viaja solo

Cada `_publish*` sube el artefacto **y** su manifiesto, y después escribe el manifiesto de release. Van todos o no va ninguno: un APK o una carpeta web no dicen de qué versión son, y del lado del VPS el manifiesto es lo único que los identifica ([ADR-0024](../adr/0024-publicar-escribe-un-manifiesto-de-release.md)).

`releases/<app>/<plataforma>.json` es lo que lee una app para saber si hay algo nuevo: app, plataforma, versión, build, nombre del artefacto, `sha256` si es un archivo, y fecha. Se escribe uno por plataforma, porque el APK y el build web se publican por separado y pueden ir en versiones distintas.

No es una fuente de verdad nueva: se deriva del manifiesto del subproyecto en el momento de publicar. Es la convención de siempre para actualizaciones —el appcast de Sparkle, el `latest.yml` de electron-updater, el `version.json` que Flutter ya emite para web—.

## 5. Flutter y Flet son el mismo botón

El framework es una propiedad de la carpeta, no una elección de quien aprieta: `toolchain.detect_app_kind` lo lee del `pubspec.yaml` o del `pyproject.toml` con `flet`. El eje nombra **cuál** app del repo, no con qué está escrita.

`toolchain.BUILD_PLATFORMS` declara las siete plataformas con su subcomando en cada framework y dónde deja cada uno su salida. El eje solo ofrece las que **esta máquina** puede compilar (`host_platforms`): ofrecer Windows en Linux sería ofrecer una casilla que siempre termina en error.

La URL de la API se inyecta por `--dart-define` desde la configuración, la misma fuente que usa el launcher de debug, para que release y debug no apunten a servidores distintos por descuido. Flet no tiene `--dart-define` propio: se lo pasa a su `flutter build` de abajo con `--flutter-build-args`.

`BUILD_OUT_<PLATAFORMA>` mueve el build a una carpeta elegida. Se **copia** y no se le pide al framework que compile ahí: Flutter solo acepta `--output` en web, y así las siete funcionan igual en los dos frameworks.

## 6. La ruta pública de una SPA

Bajo qué ruta vive cada SPA lo dice `PUBLIC_ROUTES` — la misma tabla que lee `configure_caddy` ([15](15_vps_y_despliegue.md)). El proxy y el build tienen que decir lo mismo, y el desacuerdo **no da error**: el proxy sirve la app, el navegador pide sus assets en la raíz del dominio —donde vive la otra app— y lo que se ve es una página en blanco.

Por eso hay dos pasos y no uno:

1. **Escribir** `<spa>/base.generated.js`, un módulo con la base como literal, que la config del repo importa. No viaja por el entorno del build porque el repo tiene que poder compilarse sin Consola; es un archivo propio y no un parche sobre `svelte.config.js`, porque Consola no edita código que no escribió ella.
2. **Comprobar** el HTML compilado: se buscan los `href`/`src` absolutos y, si alguno no cuelga de la base, se corta con el mensaje que explica qué se va a ver. Se mira el resultado y no la config, porque cómo resuelve cada repo su base es asunto suyo y parsear JS sería adivinar.

Los dos pasos son de los repos **con tabla**. `vps.spa_base` devuelve `None` cuando no hay ninguna, y entonces Consola compila y no le deja nada adentro al repo ([ADR-0020](../adr/0020-ruta-publica-no-implica-proxy.md)).

En web, `compile_flutter` usa la misma base con `--base-href` (Flutter) o `--base-url` (Flet).

## 7. El binario

`build_binary` es el único cuyo objetivo se escribe en vez de elegirse de una lista descubierta: un eje descubierto vacío deja el botón en ámbar, y un repo que se empaqueta desde su raíz —el caso de la propia Consola— no tiene ningún `python-app` que descubrir.

Vacío no es «falta un dato»: `resolve_entrypoint` prueba `src/main.py`, `main.py` y `app/main.py` de la única app Python del repo, y si no hay ninguna, de la raíz. Con más de una app corta y pide que se escriba cuál.

| Detalle | Por qué |
|---|---|
| La carpeta de la app se busca **subiendo** hasta un manifiesto | Quedarse con `entrypoint.parent` daba `src/`, y ahí se creaba un `pyproject.toml` paralelo con su propia versión que nadie más leía |
| Si no hay manifiesto, se crea en `0.0.0` | Un script suelto que se empieza a distribuir no tiene por qué traer uno escrito de antemano |
| PyInstaller se prefiere del venv de la app | Congela el entorno desde el que corre: el global no ve las dependencias del proyecto y deja un binario que muere al primer import |
| `--specpath build` | El `.spec` es derivado; en la raíz aparecía como cambio sin commitear después de cada compilación |
| Sin `--clean` | Borra la caché y vuelve a analizar todo en cada corrida. Para el build limpio de verdad está «Limpiar artefactos» |
| El nombre lleva sistema y arquitectura | PyInstaller no compila cruzado, y sin la etiqueta el de Windows y el de Linux se pisan en la misma ruta del VPS |
| El nombre **no** lleva la versión | La URL de descarga se mantiene estable; qué versión es lo dice el manifiesto que se publica al lado |
| Se sube con `chmod 755` | `scp` no conserva el bit de ejecución, y del otro lado quedaba un ejecutable que no se podía ejecutar |

El checksum SHA-256 es propio de este builder: un ejecutable que alguien descarga no se puede mirar por dentro. Solo aplica al empaquetado en un archivo; con `--onefile` desactivado el paso se saltea con un aviso en vez de tirar un build que ya se pagó.

## 8. SPA nueva

`create_spa` levanta el esqueleto con `sv create` —el generador oficial de Svelte: TypeScript, runas y adaptador estático— y escribe encima lo que falta para dejarla lista: UnoCSS, `ssr = false`, y, **solo si el repo tiene tabla de rutas**, la base leída de `base.generated.js`. Sin tabla, esa parte de la config sobra y no se escribe.

El nombre de la carpeta se pregunta al correr (`ctx.ask`), no se guarda: es distinto en cada corrida, así que como parámetro guardado la segunda arrancaba con el nombre de la primera — o sea, con una carpeta que ya existe.

## 9. Promover

`promote_app` copia lo último publicado sobre el canal estable. Es destructivo —pisa la carpeta anterior entera— así que compara antes, avisa si ya eran idénticas y queda bajo el objetivo `publicacion` del seguro ([14](14_seguro_de_destructivos.md)).

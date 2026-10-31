# 17 · Builds y artefactos

## 1. Tres builders

| Builder | Paso propio | Eje del objetivo |
|---|---|---|
| `build_flutter` | `flutter build` o `flet build`, una vez por plataforma marcada | `directory`: una app móvil |
| `build_vite` | `npm install` + `npm run build` | `directories`: varias SPA, en bucle |
| `build_binary` | PyInstaller | Campos: punto de entrada y nombre |

`build_flutter` y `build_vite` compilan y nada más: no suben la versión del manifiesto ni publican en el VPS ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)). `build_binary` es el único que recorre la secuencia entera:

```
bump del manifiesto → compilar → checksum → subir artefacto + manifiesto
```

El bump y la subida son atómicas (`bump_version`, `upload_artifact`) que hoy usa solo él.

## 2. El bump es reversible

Todo el tramo que toca el manifiesto va dentro de `files.reversible(manifiesto)`: si el build revienta después de subir la versión, el archivo vuelve a lo que era y el repo no queda marcado con un número que nunca se publicó ([ADR-0025](../adr/0025-bump-reversible.md)).

El eje `bump_mode` ofrece el componente SemVer (`major`/`minor`/`patch`/`none`). `versioning.bump` entiende además `+build`, el build number de Flutter (`1.4.22+318`), que ningún botón ofrece.

## 3. Compilar es desmarcable

Sin el paso «Compilar binario», `build_binary` **sube lo que ya está en disco**. Es el `BUILD_BINARY=false` del script original, y la razón es económica: retomar un `scp` cortado no debería costar otro empaquetado entero ([ADR-0026](../adr/0026-compilar-es-desmarcable.md)).

En ese modo el bump se ignora con un aviso: lo que hay en disco se compiló con la versión que ya tiene el manifiesto, y subirlo cambiado lo anunciaría como otra cosa. Sin compilar y sin subir no queda nada por hacer, y el botón lo dice.

## 4. Un artefacto nunca viaja solo

`_publish_binary` sube el binario **y** su manifiesto, el checksum si se generó, y después escribe el manifiesto de release. Van todos o no va ninguno: el ejecutable no dice de qué versión es, y del lado del VPS el manifiesto es lo único que lo identifica ([ADR-0024](../adr/0024-publicar-escribe-un-manifiesto-de-release.md)).

`releases/<app>/<plataforma>.json` es lo que lee una app para saber si hay algo nuevo: app, plataforma, versión, build, nombre del artefacto, `sha256` si es un archivo, y fecha.

No es una fuente de verdad nueva: se deriva del manifiesto del subproyecto en el momento de publicar. Es la convención de siempre para actualizaciones —el appcast de Sparkle, el `latest.yml` de electron-updater—.

## 5. Flutter y Flet son el mismo botón

El framework es una propiedad de la carpeta, no una elección de quien aprieta: `toolchain.detect_app_kind` lo lee del `pubspec.yaml` o del `pyproject.toml` con `flet`. El eje nombra **cuál** app del repo, no con qué está escrita.

`toolchain.BUILD_PLATFORMS` declara las siete plataformas con su subcomando en cada framework y dónde deja cada uno su salida. El eje solo ofrece las que **esta máquina** puede compilar (`host_platforms`): ofrecer Windows en Linux sería ofrecer una casilla que siempre termina en error.

La URL de la API se inyecta por `--dart-define` desde la configuración, la misma fuente que usa el launcher de debug, para que release y debug no apunten a servidores distintos por descuido. Flet no tiene `--dart-define` propio: se lo pasa a su `flutter build` de abajo con `--flutter-build-args`.

`BUILD_OUT_<PLATAFORMA>` mueve el build a una carpeta elegida. Se **copia** y no se le pide al framework que compile ahí: Flutter solo acepta `--output` en web, y así las siete funcionan igual en los dos frameworks.

## 6. Cada SPA va en la raíz de su host

`compile_spa` corre `npm run build` y no le deja nada adentro al repo, y `compile_flutter` no pasa ninguna base: en un VPS de canone cada pieza tiene su host (`app.<dominio>`, `panel.<dominio>`, la landing en el dominio), así que ninguna se publica bajo una ruta ([ADR-0065](../adr/0065-cada-spa-va-en-la-raiz-de-su-host.md)).

## 7. El binario

`build_binary` es el único cuyo objetivo se escribe en vez de elegirse de una lista descubierta: un eje descubierto vacío deja el botón en ámbar, y un repo que se empaqueta desde su raíz —el caso de la propia Consola— no tiene ningún `python-app` que descubrir.

Vacío no es «falta un dato»: `resolve_entrypoint` prueba `src/main.py`, `main.py` y `app/main.py` de la única app Python del repo, y si no hay ninguna, de la raíz. Con más de una app corta y pide que se escriba cuál.

| Detalle | Por qué |
|---|---|
| La carpeta de la app se busca **subiendo** hasta un manifiesto | Quedarse con `entrypoint.parent` daba `src/`, y ahí se creaba un `pyproject.toml` paralelo con su propia versión que nadie más leía |
| Si no hay manifiesto, se crea en `0.0.0` | Un script suelto que se empieza a distribuir no tiene por qué traer uno escrito de antemano |
| PyInstaller se prefiere del venv de la app | Congela el entorno desde el que corre: el global no ve las dependencias del proyecto y deja un binario que muere al primer import |
| `--specpath build` | El `.spec` es derivado; en la raíz aparecía como cambio sin commitear después de cada compilación |
| El ícono es `BRAND_ICON`, como `build/icon.ico` | Es el mismo logo que el de las otras apps del repo; un campo propio era una segunda fuente ([ADR-0056](../adr/0056-cada-tecnologia-declara-donde-va-su-icono.md)). Va a `build/` porque es derivado. Sin la clave, sale sin ícono |
| Sin `--clean` | Borra la caché y vuelve a analizar todo en cada corrida. Para el build limpio de verdad está «Limpiar artefactos» |
| El nombre lleva sistema y arquitectura | PyInstaller no compila cruzado, y sin la etiqueta el de Windows y el de Linux se pisan en la misma ruta del VPS |
| El nombre **no** lleva la versión | La URL de descarga se mantiene estable; qué versión es lo dice el manifiesto que se publica al lado |
| Se sube con `chmod 755` | `scp` no conserva el bit de ejecución, y del otro lado quedaba un ejecutable que no se podía ejecutar |

El checksum SHA-256 es propio de este builder: un ejecutable que alguien descarga no se puede mirar por dentro. Solo aplica al empaquetado en un archivo; con `--onefile` desactivado el paso se saltea con un aviso en vez de tirar un build que ya se pagó.

## 8. SPA nueva

`create_spa` levanta el esqueleto con `sv create` —el generador oficial de Svelte: TypeScript, runas y adaptador estático— y escribe encima lo que falta para dejarla lista: UnoCSS y `ssr = false`.

El nombre de la carpeta se pregunta al correr (`ctx.ask`), no se guarda: es distinto en cada corrida, así que como parámetro guardado la segunda arrancaba con el nombre de la primera — o sea, con una carpeta que ya existe.

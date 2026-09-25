# 19 · Imágenes

El grupo **Imágenes** produce el material gráfico de las apps de un repo: sus íconos (§7) y sus capturas publicables (§1–§6).

## 1. El corte: el repo pone la cámara, Consola el revelado

| Parte | Quién | Dónde |
|---|---|---|
| El escenario, las rutas del servidor ficticio, entrar sin login, navegar | el script del repo | lo que declara `SHOTS_CMD` |
| Leer el contrato, servidor ficticio, Vite, página, reintentos, emulador | el kit de Consola, que corre dentro de la cámara | `camara/index.mjs` (§6) |
| Elegir apps, temas, idiomas y emulador; encender el emulador | Consola | `core/tasks/images.py::shoot_screens` |
| Validar lo que dejó la cámara | Consola | `core/shots.py::collect`, `missing_combinations` |
| Convertir cada crudo para cada destino y escribir el manifiesto | Consola | `core/shots.py` (`render_*`, `write_manifest`), `core/shots_presets.json` |

La cámara es código del repo porque solo el repo sabe navegar su app ([ADR-0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md)). Los datos salen de un escenario servido por un servidor ficticio, nunca de una base ([ADR-0050](../adr/0050-las-capturas-no-tocan-la-base.md)), y la plomería que comparten todas las cámaras es un kit de Consola ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).

## 2. Los botones

| Botón | Qué hace |
|---|---|
| `shoot_screens` · Sacar capturas | Corre la cámara y comprueba lo que dejó |
| `render_shots` · Revelar capturas | Convierte los crudos para cada destino marcado |
| `screenshots` · Capturar y publicar | Compuesta: los dos anteriores, cada uno desmarcable |

Ejes de `shoot_screens` (y del paso `shoot` de la compuesta):

| Eje | Valores | Argumento |
|---|---|---|
| `apps` | las que declara la cámara (fuente consultada `SHOTS_APPS`) | `--apps` |
| `themes` | los que tiene alguna de ellas, en el orden `claro`, `oscuro` (`SHOTS_THEMES`) | `--themes` |
| `languages` | los que tiene alguna de ellas (`SHOTS_LANGUAGES`) | `--languages` |
| `avd` | AVD creados, o ninguno. Si una app lo necesita lo dice la cámara (ADR-0052) | `--device` con el serial, solo si se eligió uno |

Los tres primeros salen de preguntarle a la cámara con `--supported` (`tasks/images.py::camera_supported`), con caché de un minuto por repo. Si no contesta, el panel muestra lo que dijo en lugar de las casillas y el botón queda bloqueado. Un eje consultado que está vacío, leyendo o con error, conserva lo elegido la última vez (`ui/params_panel.py::_persist`).

Eje de `render_shots` y de la compuesta: `destinations` (`landing`, `play`, `appstore`, `manual`, `og`, `social`, `presskit`). Un destino sin preset, o sin ningún crudo de un tipo que le sirva, corta la corrida antes de convertir nada.

## 3. La corrida de la cámara

1. Comprueba que cada app marcada sea una app del repo con pantalla. No mira si hace falta emulador: eso lo decide la cámara (ADR-0052), que corta antes de la primera foto si una app lo necesita y no llegó `--device`.
2. Borra de `SHOTS_RAW` los crudos de las combinaciones pedidas (`clear_raw`): una pantalla que el script dejó de sacar no sobrevive a la corrida siguiente. Las combinaciones no pedidas no se tocan.
3. Con un AVD elegido: si ya está encendido, usa su serial; si no, lo enciende en un hilo aparte con un puerto elegido de antemano, espera el arranque, y lo apaga por adb al terminar. De su salida solo pasan al log los avisos y los errores.
4. Corre `SHOTS_CMD` desde la raíz del repo con los argumentos de §2, `--output` con `SHOTS_RAW` absoluta y `--kit` con la ruta de `camara/index.mjs` (`shots.KIT`). El primer token se resuelve en el PATH; el resto va tal cual. Con un AVD elegido, la carpeta del `adb` del SDK va primera en el PATH de la cámara.
5. Lee los crudos de las apps pedidas y corta si un archivo no sigue el nombre, o si alguna combinación app × tema × idioma quedó sin captura.

## 4. El nombre de los crudos

```
<SHOTS_RAW>/<app>/<pantalla>.<tema>.<idioma>.png
```

`<app>` tiene que ser una app del repo con pantalla (SPA Vite o app móvil), y su tipo decide cómo se revela. `<tema>` tiene que ser `claro` u `oscuro`. Cualquier otro archivo en esas carpetas corta la lectura: revelar a medias dejaría una mezcla de corridas.

## 5. El revelado

Los presets viven en `core/shots_presets.json`, no en el código: las medidas de cada destino cambian por la tienda, no por Consola.

| Destino | Qué hace | Salida |
|---|---|---|
| `landing` | Achica al ancho tope del tipo de app (SPA 1920, móvil 540) con Lanczos, **nunca agranda**, y guarda `.webp` calidad 82 | `<SHOTS_PUBLISH>/<app>/<pantalla>.<tema>.<idioma>.webp` |
| `play` | Solo crudos móviles. No cambia la medida: el crudo tiene que tener el lado corto ≥ 320 px, el largo ≤ 3840 px y una proporción ≤ 2:1 | `<SHOTS_DIST>/play/<idioma>/<app>/<pantalla>.<tema>.png` |
| `appstore` | Solo crudos móviles. Medida exacta: 1290×2796 (iPhone 6.9") o 2064×2752 (iPad 13"), la que se alcance recortando como mucho un 3 % | `<SHOTS_DIST>/appstore/<idioma>/<app>/<pantalla>.<tema>.{iphone,ipad}.png` |
| `og` | Solo crudos SPA. 1200×630, recortando lo que haga falta | `<SHOTS_DIST>/og/<idioma>/<app>/<pantalla>.<tema>.og.png` |
| `social` | Cuadrado 1080×1080 de todo crudo; historia 1080×1920 solo de móviles. Recorta lo que haga falta | `<SHOTS_DIST>/social/<idioma>/<app>/<pantalla>.<tema>.{square,story}.png` |
| `manual` | PNG a resolución nativa | `<SHOTS_DIST>/manual/<idioma>/<app>/<pantalla>.<tema>.png` |
| `presskit` | Los crudos tal cual, sin comprimir, en un ZIP | `<SHOTS_DIST>/presskit/capturas.zip` (`<app>/<pantalla>.<tema>.<idioma>.png` dentro) |

`core/shots.py::plan` decide qué sale de cada crudo, con los datos del preset:

- `kinds`: de qué tipos de app sale el destino. Si ningún crudo es de esos tipos, corta.
- `limits`: reglas que el crudo tiene que cumplir tal cual. Si uno no las cumple, corta y lo nombra.
- `sizes` con `max_crop`: medidas exactas. Cada crudo va a las medidas cuya proporción alcanza recortando como mucho `max_crop` de la imagen. Así un teléfono va a iPhone y una tablet a iPad sin que el contrato con la cámara diga qué dispositivo es. Si un crudo no cabe en ninguna, corta y lo nombra: recortar de más se come la barra superior o la navegación de la app.

Las medidas fijas se obtienen escalando hasta cubrir (aquí **sí** se agranda: la medida es exacta) y recortando del centro. Todo PNG de estos destinos sale sin canal alfa, que las dos tiendas rechazan.

Un teléfono 1080×2400 sirve para App Store (recorta 2,5 %) y no para Play (2,22:1). Uno 1080×2160 sirve para Play y no para App Store (recortaría 7,7 %). **Ninguna proporción de teléfono sirve para las dos**: son dos tandas, sacadas con dispositivos distintos.

Cada destino deja un `capturas.json` en su carpeta: `{destination, items}` con app, pantalla, tema, idioma, archivo, medida y `sha256` de cada archivo (en el press kit, el del crudo, con su `member` dentro del ZIP). Sin fecha y ordenado: dos corridas iguales dan el mismo archivo. Antes de reescribirlo se compara con el anterior, y el log dice qué archivos **cambiaron**, cuáles son **nuevos** y cuáles **ya no están**. Esa es la regresión visual.

Se planean todos los destinos marcados antes de convertir ninguno. El revelado no borra nada de lo que ya hay en `SHOTS_PUBLISH` ni en `SHOTS_DIST`: un archivo de una pantalla que ya no existe queda ahí hasta que alguien lo borre, y el manifiesto es la lista de lo vigente.

La conversión usa Pillow.

## 6. El kit de la cámara

`camara/index.mjs`, JS sin dependencias. La cámara lo importa desde la ruta que recibe en `--kit` y le pasa lo que necesite de Playwright.

| Export | Qué hace |
|---|---|
| `parseArgs(argv, soportado)` | Lee `--apps`, `--themes`, `--languages`, `--output`, `--device` y `--kit`. `soportado` dice, por app, qué temas e idiomas tiene y si es móvil. Un argumento desconocido o faltante, una app, tema o idioma no soportado, o una app móvil sin `--device` son error: la cámara termina sin sacar nada. Con `--supported` imprime `soportado` como JSON y termina: es lo que Consola ofrece en los ejes (ADR-0054) |
| `checkSupported(soportado)` | Revisa lo que declara la cámara: al menos una app, y en cada una temas del contrato, idiomas y `mobile` booleano. `parseArgs` lo llama siempre |
| `combinations(args)` | Cada par tema × idioma pedido |
| `shotPath(output, app, pantalla, tema, idioma)` | `<output>/<app>/<pantalla>.<tema>.<idioma>.png`, creando la carpeta. Una pantalla con punto o barra es error |
| `main(fn)` | Corre la cámara; un error se imprime y sale con código 1 |
| `startFakeServer({port, routes, scenario, onScenario, websockets})` | El servidor ficticio. Las rutas son `[método, ruta exacta o RegExp, handler]`, lecturas y escrituras por igual (ADR-0053); el handler recibe `(url, match, req, cuerpo)`, con el cuerpo JSON ya leído. `reply(status, cuerpo)` contesta otro estado y `reply(204)`, sin cuerpo. Solo el `OPTIONS` del CORS se contesta sin ruta. Entrega el escenario en `/__demo/scenario` y llama a `onScenario` después. Un pedido o un WebSocket sin ruta contesta 500 y queda anotado, igual que un handler que falla o no devuelve nada; `assertComplete()` falla nombrándolos |
| `startVite({appDir, port, env, readyPath})` | El `vite.js` del repo con el mismo Node, sin `VSCODE_CWD`, hasta que `readyPath` contesta |
| `openPage(browser, {theme, language, timezoneId, now, viewport})` | Un contexto con `colorScheme` del tema (`claro` → `light`, `oscuro` → `dark`), `locale`, zona horaria y el reloj puesto en `now` |
| `retryOnReload(page, fn)`, `visit(page, url, listo)` | Reintentan cuando Vite recarga la página en frío |
| `shoot(page, ruta, esperaMs)` | Espera y guarda la captura |
| `android(device)` | `adb` sobre el dispositivo: zona horaria, `root`, reloj fijo y restaurarlo |
| `flutterDrive({...})` | `flutter drive` para un tema e idioma. A la prueba le pasa `SHOTS_THEME` y `SHOTS_LANGUAGE` por `--dart-define`; al driver, `SHOTS_DIR` y `SHOTS_SUFFIX` en el entorno, para que guarde `<SHOTS_DIR>/<pantalla>.<SHOTS_SUFFIX>.png` |

Las pruebas del kit están en `camara/index.test.mjs` (`node --test`), y `tests/test_camara.py` las corre dentro de pytest.

## 7. Los íconos

`generate_icons` · Generar íconos deja el logo del repo, y sus capas, como ícono de cada app marcada. El repo pone los SVG y cada app dice dónde va su ícono ([ADR-0055](../adr/0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md), [ADR-0056](../adr/0056-cada-tecnologia-declara-donde-va-su-icono.md), [ADR-0057](../adr/0057-el-manifest-de-la-pwa-es-un-archivo-estatico.md)). Por convención los SVG viven en `brand/`.

| Clave | Capa | Qué es |
|---|---|---|
| `BRAND_ICON` | `logo` | El logo, SVG cuadrado, relativo a la raíz. Sin ella el botón queda en ámbar |
| `BRAND_ICON_FOREGROUND` | `foreground` | La capa frontal del ícono adaptativo de Android |
| `BRAND_ICON_MASKABLE` | `maskable` | El ícono maskable de una PWA: fondo a sangre y el dibujo dentro del círculo central del 80 % |

Las dos últimas se exigen al correr, solo sobre una app que las pide, y faltar abre la configuración en esa clave.

El eje `apps` es consultado contra el repo (`catalog.ICON_APPS`, `core/icons.py::icon_apps`), sin caché. Ofrece las apps con al menos un lugar declarado (`icons.places`):

| Tipo | Lugares | Capa |
|---|---|---|
| Flutter | Cada `image_path` de la sección `flutter_launcher_icons:` del `pubspec.yaml` (también `image_path_android`, `image_path_ios` y los anidados en `web`, `windows`, `macos`), a 1024 | `logo` |
| | `adaptive_icon_foreground`, a 1024 | `foreground` |
| Flet | `src/assets/icon.png`, si existe, a 1024 | `logo` |
| SPA | Cada `<link rel="icon">` y `rel="apple-touch-icon"` del `src/routes/+layout.svelte`. Si el `href` es una variable, cuenta cuando se importa de `$lib/`; si se importa de otro lado, la app ya lee el logo de la fuente | `logo` |
| | Los mismos `<link>` de `src/app.html` e `index.html`. `%sveltekit.assets%/x` y `/x` van a `static/x` en SvelteKit (paquete `@sveltejs/kit`) y a `public/x` si no | `logo` |
| | Cada ícono de `icons` del manifest que enlaza el `<link rel="manifest">` de `src/app.html` o `index.html`, leído como JSON. Un `src` relativo cuelga de la carpeta del manifest; uno con `/`, de `static/` o `public/` | `maskable` si su `purpose` es `maskable`, `logo` si es `any` o no tiene |

El formato sale de la extensión: `.svg` recibe la capa tal cual, `.png` se rasteriza al lado de su `sizes`, `.ico` lleva los lados de 16 a 256 (`raster.ICO_SIZES`). Si un archivo aparece dos veces, se deja uno; dos tamaños o dos capas distintas cortan.

Una app se ofrece aunque su declaración esté rota: la corrida dice qué tiene mal. La corrida planea todas las apps marcadas antes de escribir ninguna (`icons.plan`) y corta si:

- Una capa escrita no es un `.svg` que exista.
- Una app Flutter no tiene `flutter_launcher_icons` en `dev_dependencies`, no declara ningún `image_path` o pide una imagen en otra clave (`adaptive_icon_monochrome`, `image_path_ios_dark_transparent`…).
- Un PNG no tiene `sizes="NxN"` o no es cuadrado; un ícono apunta a otro dominio; un archivo no es `.svg`, `.png` ni `.ico`.
- El plugin de PWA (`VitePWA(` o `SvelteKitPWA(` en `vite.config.*`) genera el manifest, porque no tiene `manifest: false`; el manifest enlazado no existe o no es JSON; un ícono del manifest no tiene `src`, o su `purpose` no es solo `any` o solo `maskable`.
- Un SVG a rasterizar no es cuadrado: Qt estira el `viewBox` hasta llenar la imagen.

Cada archivo se escribe solo si cambia, y el log dice si es nuevo, actualizado o sin cambios. `flutter_launcher_icons` corre siempre en las apps Flutter marcadas: reparte el ícono por plataforma, y Consola no compara esos archivos.

Rasteriza `core/tasks/raster.py` con QtSvg (`QSvgRenderer` sobre un `QImage` con antialiasing), sin aplicación Qt; el `.ico` lo arma Pillow a partir del PNG de 256. QtSvg implementa SVG Tiny 1.2: filtros, máscaras o CSS saldrían distintos que en el navegador.

El ejecutable de «Compilar ejecutable» toma el mismo logo: con `BRAND_ICON`, `compile_binary` escribe `build/icon.ico` y lo pasa en `--icon` ([17](17_builds_y_artefactos.md)).

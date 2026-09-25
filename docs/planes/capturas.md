# Plan — capturas publicables de las apps de un repo

> **Estado (verificado 2026-09-24).** Construido en Consola: `shoot_screens`, `render_shots` con
> los siete destinos, el manifiesto con la comparación contra la corrida anterior, la compuesta
> `screenshots` y el kit de la cámara (`camara/`, [ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
> Lo construido se describe en [arquitectura 19](../arquitectura/19_imagenes.md), que manda sobre
> este plan. Vettore y banditore corren de punta a punta con el kit (§6).
>
> Pendiente en Consola: los marcos de dispositivo, sin especificar (qué destinos, qué aspecto), y
> decidir dónde viven las partes Dart y Flet del kit. Pendiente en vettore: la landing leyendo el
> manifiesto (resto de la 5); banditore ya lo lee. Sin verificar
> ([30](../arquitectura/30_riesgos_y_pendientes.md)): una tanda subida de verdad a una tienda.
>
> **El corte cambió el 2026-09-23.** La versión anterior de este plan ponía la cámara en Consola:
> un guion `demo/capturas.json` con rutas y gestos, y Playwright manejado desde Python. Se
> descartó porque el único caso real, `vettore/demo/capturar.mjs`, no entra en ese contrato (§2.1).
> Ahora el repo pone la cámara y Consola pone el revelado.
>
> Las decisiones marcadas *(propuesta)* no están confirmadas. Donde este plan y el código no
> coincidan, manda [`docs/arquitectura/`](../arquitectura/README.md).

---

## 1. Para qué se sacan estas capturas

No es una prueba de regresión ni un diagnóstico. Es **material publicable**, y cada destino
impone su propio formato:

| Destino | Qué exige | Prioridad |
|---|---|---|
| Landing del producto | ancho grande, `.webp`, peso bajo | alta |
| Google Play | teléfono y tablet en medidas exactas, gráfico destacado, **una tanda por idioma** | alta |
| App Store | medidas exactas por tamaño de pantalla (6.9", 6.5", iPad), una tanda por idioma | alta |
| Manual de usuario / docs | PNG nítido, la misma pantalla estable entre versiones | alta |
| README del repo | ancho medio, tema claro y oscuro | media |
| Open Graph / Twitter card | 1200×630, un recorte legible en miniatura | media |
| Social preview de GitHub | 1280×640 | baja |
| Redes sociales | 1080×1080 y 1080×1920 | media |
| Press kit | PNG a resolución nativa, sin comprimir, en un ZIP | baja |
| Microsoft Store / F-Droid | solo si el repo publica escritorio o APK fuera de Play | baja |
| Regresión visual | **subproducto**: la misma corrida comparada contra la anterior | — |

De la tabla salen dos reglas:

1. **La salida es una matriz**: pantalla × tema × idioma × destino. Cuatro pantallas, dos temas,
   tres idiomas y cinco destinos son 120 imágenes.
2. **Las medidas son dato, no código.** Play y App Store cambian sus requisitos sin avisar. Viven
   en un archivo de presets (§5), no en constantes de un `.py`.

---

## 2. El corte: el repo pone la cámara, Consola pone el revelado

| Parte | Quién | Por qué |
|---|---|---|
| Sembrar los datos ficticios | repo | solo el repo sabe qué es una "sala" o un "recorrido" |
| Entrar sin login, navegar, hacer los gestos, sacar el PNG | repo | es código de la app: importa sus módulos, conoce sus selectores y sus trampas |
| Correr la cámara desde un botón | Consola | un solo lugar para lanzarla, con la salida en la pestaña |
| Escalar, recortar y convertir para cada destino | Consola | es idéntico en todos los repos |
| Marcos de dispositivo, press kit, manifiesto | Consola | ídem |
| Presets de medidas de cada tienda | Consola | cambian por la tienda, no por el repo |

### 2.1 Por qué no una cámara genérica

Evidencia de `vettore/demo/`, el único caso escrito:

| Hallazgo | Dónde |
|---|---|
| El panel se siembra **dentro de la página**: `page.evaluate` importa `identity.ts`, `repository.ts` y `schema.ts` del propio panel para escribir IndexedDB con el mismo sellado que en producción, y reintenta si Vite recarga a mitad de la siembra. Un comando de shell no puede hacer eso. | `capturar.mjs` → `sembrarPanel` |
| El interceptor de red del navegador (`page.route`) no sirve para la app Flutter, que le pega a `10.0.2.2:8787`. El servidor ficticio tiene que existir como proceso. | `capturar.mjs` → `capturarApp` |
| El servidor ficticio además **sincroniza**: avisa (`alEntregarSembrado`) cuándo mover el reloj del emulador por `adb`, porque moverlo antes rompe `flutter drive`. | `servidor.mjs` |
| La navegación de la app móvil son 295 líneas de Dart que importan las entrañas de la app. | `app/integration_test/capturas_test.dart` |

Un guion declarativo habría necesitado primitivas nuevas desde el primer repo, que es la señal de
que el contrato está mal. Para navegar, el lenguaje correcto es el del propio repo (Playwright o
Dart), no un JSON que termina siendo un lenguaje de programación.

Lo que sí se repite entre cámaras es la plomería, y va en un kit compartido (§8).

---

## 3. El contrato entre el repo y Consola

### 3.1 Claves de `config.env` *(propuesta)*

Son datos que las tareas leen ([ADR-0017](../adr/0017-datos-en-el-env-decisiones-en-el-json.md)):

| Clave | Por defecto | Qué es |
|---|---|---|
| `SHOTS_CMD` | — | el comando que corre la cámara del repo, desde su raíz. En vettore: `node demo/capturar.mjs` |
| `SHOTS_RAW` | `demo/capturas` | dónde deja la cámara los PNG crudos |
| `SHOTS_PUBLISH` | `landing/static/capturas` | dónde deja el revelado los derivados de la landing |
| `SHOTS_DIST` | `demo/publicables` | dónde deja el revelado los demás destinos, una carpeta por destino. Clave y valor por defecto elegidos al implementar |

Sin `SHOTS_CMD`, `shoot_screens` y el paso `shoot` de la compuesta quedan en ámbar
([ADR-0007](../adr/0007-lo-inaplicable-desaparece.md)). `render_shots` no lo necesita: se puede
revelar lo que ya está en `SHOTS_RAW`.

### 3.2 El nombre de los crudos *(propuesta)*

```
<SHOTS_RAW>/<app>/<pantalla>.<tema>.<idioma>.png
```

- `<app>` es el nombre de un target de `core/targets.py` (`panel`, `app`). De ahí sale su tipo
  (`SPA_VITE` o `FLUTTER_APP`), y el tipo dice para qué destinos sirve el crudo (§5.1).
- Los cuatro segmentos son obligatorios. Un archivo que no coincide con el patrón, o cuya `<app>`
  no es un target, **corta el revelado con error**. Nada se adivina.
- Los crudos se sacan **a resolución nativa, una sola vez**. Todo lo demás es recorte y escalado
  sobre ese PNG.

### 3.3 Qué recibe la cámara ([ADR-0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md))

Consola corre `SHOTS_CMD` desde la raíz del repo y le añade los argumentos de lo que se marcó en
el botón. Van como argumentos y no como variables de entorno ni como un archivo: son valores
simples, se ven en el comando y el script se puede probar a mano.

```
node demo/capturar.mjs --apps panel,app --themes oscuro --languages es \
                       --output E:/Git/vettore/demo/capturas \
                       --kit E:/Git/consola/camara/index.mjs --device emulator-5554
```

| Argumento | Obligatorio | Contenido | De dónde sale |
|---|---|---|---|
| `--apps` | sí | nombres de carpeta separados por coma | eje `apps`: las que declara la cámara ([ADR-0054](../adr/0054-la-camara-dice-que-sabe-capturar.md)) |
| `--themes` | sí | `claro` y/o `oscuro` | eje `themes` |
| `--languages` | sí | los idiomas marcados | eje `languages`, con los que declara la cámara |
| `--output` | sí | ruta absoluta de la carpeta de crudos | `SHOTS_RAW` resuelta contra la raíz del repo |
| `--kit` | sí | ruta absoluta del kit de la cámara | `camara/index.mjs` de la Consola que corre ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)) |
| `--device` | solo con app móvil | serial del emulador, ya encendido | eje `avd`: Consola arranca ese AVD si no está vivo |

Reglas para el script:

- Captura exactamente esas combinaciones de app, tema e idioma.
- Guarda como `<output>/<app>/<pantalla>.<tema>.<idioma>.png` (§3.2).
- Si no soporta algo de lo pedido, termina con código distinto de cero. No lo ignora en silencio.

El emulador **no** lo busca el script: lo elige quien aprieta el botón y lo enciende Consola, que
ya sabe arrancar AVD (`launch_emulator`). Si una app lo necesita lo dice la cámara, no el tipo de
la app ([ADR-0052](../adr/0052-la-camara-dice-que-apps-necesitan-emulador.md)): sin `--device`,
corta antes de sacar la primera foto. Las apps Flet de banditore se capturan sin emulador.

Lo que Consola **no** puede elegir son las pantallas: solo el script sabe cuáles existen, así que
capturar una sola pantalla se hace desde el script.

### 3.4 ¿Choca con ADR-0001?

[ADR-0001](../adr/0001-reimplementar-no-ejecutar-scripts.md) prohíbe que Consola delegue **su
propia** lógica en scripts copiados; el único subproceso permitido es un binario externo. Aquí el
subproceso es `node` o `flutter`, y el script es código del repo administrado, igual que los
payloads que importan `seeders.` (la excepción que ese ADR declara) o el `npm run build` de
`build_vite`. Decidido en [ADR-0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md).

---

## 4. Las capacidades

Grupo **Imágenes** (`🖼️`), entre Compilar y Repositorio, compartido con `generate_icons`
([ADR-0055](../adr/0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md)), con el corte de [ADR-0004](../adr/0004-un-boton-por-capacidad.md).

| id | Nombre | kind | Qué hace | Por qué sola |
|---|---|---|---|---|
| `shoot_screens` | Sacar capturas | `once` | corre `SHOTS_CMD` con los ejes como argumentos y comprueba que dejó crudos con nombres válidos | cambió una pantalla |
| `render_shots` | Revelar capturas | `once` | de los crudos saca los derivados de cada destino marcado y el manifiesto | cambió la medida de una tienda, no la app |
| `screenshots` | Capturar y publicar | `once`, `level='C'` | pasos `shoot` → `render`, los dos desmarcables | el botón que se aprieta de verdad |

Eje `destinations` de `render_shots` y `screenshots` (va a `params.json`), `checks`, `select='many'`:

| Valor | Etiqueta | Arranca marcado |
|---|---|---|
| `landing` | Landing | sí |
| `play` | Google Play | no |
| `appstore` | App Store | no |
| `manual` | Manual | no |
| `og` | Open Graph | no |
| `social` | Redes sociales | no |
| `presskit` | Press kit | no |

El paso `shoot` de la compuesta exige `SHOTS_CMD`: sin él queda en ámbar, y se puede desmarcar para
revelar lo que ya está en disco.

Ejes de `shoot_screens` y del paso `shoot` de `screenshots` (los argumentos de §3.3), todos
`checks` salvo `avd`:

| Eje | Valores | Arranca |
|---|---|---|
| `apps` | las que declara la cámara con `--supported` (ADR-0054) | todas marcadas |
| `themes` | los que tiene alguna de ellas | todos marcados |
| `languages` | los que tiene alguna de ellas | todos marcados |
| `avd` | AVD creados (`pick`); vacío = ninguno, y la cámara dice si hacía falta (ADR-0052) | vacío |

---

## 5. El revelado

```
crudos (del repo)                         derivados (de Consola)
────────────────────────────────          ──────────────────────────────
<app>/<pantalla>.<tema>.<idioma>.png ─┬─► landing/   <app>/<pantalla>.<tema>.<idioma>.webp → SHOTS_PUBLISH
                                      ├─► play/      medidas de Play
                                      ├─► appstore/  medidas de App Store
                                      ├─► manual/    PNG 2x
                                      ├─► og/        1200×630
                                      └─► presskit/  ZIP nativo
                                                 + manifiesto (capturas.json)
```

El **manifiesto** lista cada derivado con su pantalla, tema, idioma, destino, medida y hash. Sirve
para que la landing y el manual indexen las imágenes en vez de escribir las rutas a mano, y para la
regresión visual (comparar hashes entre corridas).

### 5.1 Los presets de destino

Un archivo de datos de Consola (`core/shots_presets.json`). Lo construido está en
[arquitectura 19](../arquitectura/19_imagenes.md) §5. La propuesta original, reemplazada por las
reglas de las fichas oficiales (Play no pide medida exacta sino proporción ≤ 2:1; App Store sí):

```jsonc
{
  "play":     { "kinds": ["flutter-app"], "sizes": [[1080,1920],[1920,1200]], "format": "png" },
  "appstore": { "kinds": ["flutter-app"], "sizes": [[1290,2796],[2048,2732]], "format": "png" },
  "og":       { "kinds": ["spa-vite"], "sizes": [[1200,630]], "crop": "center", "format": "png" }
}
```

`kinds` dice de qué crudos sale cada destino: una captura de escritorio no se convierte en una de
teléfono. Si un destino marcado no tiene ningún crudo de su tipo, el revelado lo dice y termina con
error; no deja la carpeta vacía en silencio.

**Las medidas de Play y App Store se verifican contra la ficha vigente antes de cada
publicación.** Por eso son dato: se corrigen editando el JSON, sin tocar código.

---

## 6. Vettore al contrato

Hecho en vettore (`1d7a28d`) y corrido de punta a punta con «Capturar y publicar»: panel y app,
tema oscuro, español, destino landing, en el AVD `capturas`. Salieron 12 capturas, la landing las
sirve con los nombres nuevos y `capturas.json`.

| Pieza | Dónde |
|---|---|
| Cámara | `demo/camara/capturar.mjs` (`SHOTS_CMD=node demo/camara/capturar.mjs`) |
| Rutas y WebSocket del servidor ficticio | `demo/camara/servidor.mjs` |
| Escenario | `demo/escenario.json` y `demo/sembrado.mjs` |
| Prueba y driver de la app | `app/integration_test/capturas_kit_test.dart`, `app/test_driver/capturas_kit.dart` |

La cámara anterior (`demo/capturar.mjs`, `demo/servidor.mjs`, `capturas_test.dart`,
`test_driver/capturas.dart`) sigue en vettore sin que nadie la corra.

**Banditore** (2026-09-24), el segundo repo y el primero con apps Flet. «Capturar y publicar»
no se apretó desde Consola: la cámara se corrió con los mismos argumentos y el revelado de la
landing con las funciones de `core/shots.py`. Salieron 17 capturas (panel, app de cliente y app
de vendedor, tema oscuro, español), y la landing muestra una en inicio leyendo `capturas.json`.

| Pieza | Dónde |
|---|---|
| Cámara | `demo/camera/shoot.mjs` (`SHOTS_CMD=node demo/camera/shoot.mjs`) |
| Rutas del servidor ficticio, lecturas y escrituras | `demo/camera/routes.mjs` |
| Escenario | `demo/scenario.json` y `demo/scenario.mjs` |
| Apps Flet | `demo/camera/flet_camera.py` y un recorrido por app (`tour_customer.py`, `tour_vendor.py`) |

**Navetta** (2026-09-25), el tercero: apps Flutter sin `android/` versionado. La cámara corrió con
las tareas de Consola (`shoot_screens` y `render_shots` llamadas desde Python, sin la ventana).
Salieron 18 capturas: 4 del panel `web` en oscuro, y 4 y 3 de las dos apps en claro y oscuro; la
landing muestra cuatro en su showroom. Al correrla apareció que Consola no veía ninguna SPA llamada
`web` en la raíz del repo: saltaba esa carpeta pensando en la de una app Flutter.

| Pieza | Dónde |
|---|---|
| Cámara | `demo/camera/shoot.mjs` (`SHOTS_CMD=node demo/camera/shoot.mjs`) |
| Rutas del servidor ficticio | `demo/camera/routes.mjs` |
| Escenario | `demo/scenario.json` y `demo/scenario.mjs` |
| Apps Flutter | Su `flutter build web`, servida por la cámara; el recorrido va en `shoot.mjs` |

---

## 7. Guía para escribir la cámara de un repo

Esto no lo construye Consola: es lo que aprendió vettore y le ahorra trabajo al próximo repo. La
cámara de vettore (`demo/camara/`) es el ejemplo a copiar.

Pasos, en orden:

1. **Escenario**: un JSON del repo con los datos de las pantallas, con ids escritos a mano.
2. **Rutas del servidor ficticio**: una función que devuelva `[ruta, handler]` con la forma de los
   esquemas del backend, y el WebSocket si el cliente lo usa. Empezar vacío: la primera corrida
   falla nombrando cada ruta que el cliente pide, y se agregan una por una.
3. **Cámara**: `capturar.mjs` importa el kit desde `--kit`, declara qué temas e idiomas tiene cada
   app en `parseArgs`, levanta el servidor ficticio y, por cada combinación, siembra lo local,
   navega y llama a `shoot` con `shotPath`. Termina con `servidor.assertComplete()`.
4. **App móvil**, según el framework:
   - **Flutter**: una prueba de integración que baja el escenario de `/__demo/scenario`, siembra
     la base local y navega; y un driver que guarda en `SHOTS_DIR` con `SHOTS_SUFFIX`. Hoy se
     copian de vettore ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
   - **Flet**: la app corre en modo web con su propio `main` y su `.venv`, y la cámara abre la
     página en Chromium a 360 × 720. Un recorrido en Python toca por texto con el despacho de
     eventos de Flet y guarda con `page.take_screenshot` a 3x. No hace falta emulador. Hoy se
     copia de banditore (`flet_camera.py`).
   - **Flutter sin proyecto Android**: `flutter build web` y Chromium a 360 × 720 a 3x. Se prende
     la accesibilidad de Flutter (clic en `flt-semantics-placeholder`) y se toca con
     `getByRole`. Un `IconButton` sin `tooltip` no tiene nombre: se le pone uno. Hoy se copia de
     navetta.
5. **`config.env`**: `SHOTS_CMD`. Las apps, temas e idiomas que Consola ofrece los toma de
   `parseArgs` con `--supported` (ADR-0054): la cámara lo llama antes de levantar nada.
6. **Landing**: que lea `capturas.json` para encontrar cada imagen y falle al compilar si falta
   una (banditore: `landing/src/lib/screenshots.ts`). Si la landing tiene un presupuesto de
   peso, elegir una pantalla que entre: en banditore el mapa pesaba 116 KB y no entraba.
7. Correr «Capturar y publicar». Si alguna app necesita emulador, en un AVD dedicado: imagen
   Google APIs (la de Google Play no permite `adb root`) y una pantalla de 2:1 como máximo, o
   Play rechaza las capturas. El de vettore es `capturas`: Pixel 3, 1080×2160, Android 36.

| Tema | Qué hacer |
|---|---|
| Entrar sin login | de menos a más robusto: sembrar la sesión antes de navegar (vettore: JWT ficticio en IndexedDB; banditore: `localStorage` en el panel y `SecureTokenStore` antes de llamar al `main` de la app Flet) · falsear el endpoint de login · un modo demo en la app (`VITE_DEMO=1`) |
| Escrituras | se mapean como las lecturas ([ADR-0053](../adr/0053-el-servidor-ficticio-tambien-mapea-las-escrituras.md)): la primera corrida falla nombrando las que el cliente hace al arrancar. Contestar lo que contesta el servidor de verdad; `reply(204)` si no tiene cuerpo |
| Varios clientes, un servidor | un token ficticio distinto por cliente, y `/auth/me` contesta el usuario de ese token |
| Ids fijos | una ruta `/chats/<uuid>` no se puede escribir si el sembrado usa `uuid4()`. `escenario.json` los trae escritos a mano |
| Selectores | `data-captura="..."` en los contenedores que se tocan, no clases de Tailwind (`.relative.h-8.cursor-pointer` se rompe en el próximo retoque) |
| Esperar | por `data-captura`, no por texto: `"Recorrido en curso"` no aparece en el segundo idioma. En Flet no hay DOM: se espera por texto en el árbol de controles, lo que obliga a un recorrido por idioma |
| Escribir en Flutter web | `fill` no llega a Flutter, y lo que se teclea antes de que el campo se conecte se pierde sin que el DOM avise. Navetta teclea un carácter hasta que queda, lo borra y escribe |
| Datos ficticios | **nunca en la base** ([ADR-0050](../adr/0050-las-capturas-no-tocan-la-base.md)): un escenario JSON del repo, servido por el servidor ficticio del kit. Los clientes de verdad apuntan a ese servidor (web: `VITE_SERVER_URL`; emulador: `10.0.2.2`). Lo que el cliente guarda localmente (IndexedDB, base del teléfono) se siembra aparte, como en vettore |
| Ruta no mapeada | el servidor ficticio la anota y la cámara termina con error nombrándola ([ADR-0050](../adr/0050-las-capturas-no-tocan-la-base.md)). En vettore encontró dos que el servidor anterior contestaba 404 en silencio |
| Reloj y zona horaria | web: `openPage` con `timezoneId` y `now` · Android: `android(device)` del kit, que necesita `adb root` |

Trampas ya pagadas en vettore:

- **En frío, Vite optimiza dependencias y recarga la página** a mitad de la carga o de la siembra:
  hay que reintentar sobre la página recargada.
- **Con `VSCODE_CWD` en el entorno, UnoCSS no carga los iconos locales**: el dev server que
  levante la cámara no debe heredar esa variable.
- **El reloj del emulador se mueve después de que la app arrancó**: un salto antes confunde a
  `flutter drive`, que busca el puerto de la VM en el logcat por hora.
- **`adb reverse` se colgaba** en el equipo de desarrollo; `10.0.2.2` funciona en el emulador.
- **La captura móvil borra la base local y la sesión** del dispositivo: siempre un emulador
  dedicado, nunca uno con una cuenta que importe.

---

## 8. Las partes genéricas de la cámara

Con los datos en un escenario y un servidor ficticio (ADR-0050), toda cámara tiene la misma
plomería. Inventario, contado sobre `vettore/demo/` y `app/test_driver/`:

| Pieza | Qué hace | Líneas hoy en vettore |
|---|---|---|
| Lado cliente del contrato | leer `--apps`, `--themes`, `--languages`, `--output`, `--device`; fallar ante lo que no soporta; nombrar `<output>/<app>/<pantalla>.<tema>.<idioma>.png` | no existe (§6) |
| Esqueleto del servidor ficticio | HTTP, CORS, `OPTIONS`, JSON, lecturas y escrituras por ruta (ADR-0053), `/__demo/sembrado` para el emulador con su aviso, ruta no mapeada → error | ~50 de `servidor.mjs` |
| Vite apuntado al servidor | lanzar el `vite.js` del repo con el mismo Node, sin `VSCODE_CWD`, esperar la URL, matarlo | ~35 |
| Página | viewport, escala, `colorScheme` por tema, `locale`, zona horaria, `clock.install` | ~15 |
| Navegar y fotografiar | ir a una ruta y reintentar si Vite recargó; esperar y guardar con el nombre del contrato | ~30 |
| Emulador | zona horaria y reloj por `adb` después de entregar el escenario; restaurar `auto_time`; `flutter drive` con `API_BASE_URL` | ~45 |
| Lado Dart | bajar el escenario con reintentos, esperar el reloj, driver que guarda en `--output` con el nombre del contrato | ~50 de Dart |

Lo propio de cada repo: el escenario, el mapa de rutas del servidor ficticio, lo que se siembre en
el cliente, el truco para entrar sin login y la navegación.

La parte JS está construida en `camara/index.mjs` y la cámara la recibe en `--kit`
([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md), [arquitectura 19](../arquitectura/19_imagenes.md) §6).

Sin decidir: la parte Dart. Se compila dentro de la prueba y no puede recibir una ruta al correr:
o es un paquete de Consola con una dependencia `path:` en cada `pubspec.yaml` (exige los repos
clonados uno al lado del otro), o se copia en cada app Flutter (vettore, las dos de navetta, la
terminal de posta). Hoy vive en vettore.

Sin decidir también: la parte Flet (`flet_camera.py`). Se importa desde la app, que corre con su
propio `.venv`, así que tiene la misma disyuntiva: una dependencia `path:` en cada `pyproject.toml`
o una copia por app. Hoy vive en banditore.

---

## 9. Lo que la v1 no hace

**Video y GIF** de un flujo, **anotaciones de manual** (flechas y globos), **subir a las tiendas**
(una API por tienda, con credenciales) y **traducir los textos de la app**: los idiomas se
recorren, no se generan.

---

## 10. Plan por etapas

| # | Etapa | Entregable verificable | Esfuerzo |
|---|---|---|---|
| 1 | ~~**`shoot_screens`**~~ | construida | — |
| 2 | ~~Vettore al contrato~~ (hecho, §6) | en vettore, «Capturar y publicar» deja la landing con las pantallas nuevas | — |
| 3 | ~~**`render_shots` para la landing**~~ | construida | — |
| 4 | ~~**Compuesta `screenshots`**~~ | construida | — |
| 5 | ~~Manifiesto~~ (construido) y **landing que lo consume** (del repo) | una captura nueva aparece en la landing sin tocar `capturas.ts` | medio día |
| 6 | ~~Presets de tienda, tablet/iPad y press kit~~ (construidos); **marcos de dispositivo** pendientes | sale la tanda para Play, verificada contra la ficha vigente | 1 día |
| 7 | ~~Kit genérico~~ (construido, JS) y ~~segundo repo~~ (banditore, §6) | el segundo repo usa el kit; sus capturas en su landing | — |
| 8 | ~~Regresión visual~~ (construida): diff de hashes contra la corrida anterior | avisa qué pantalla cambió entre dos versiones | medio día |

Las etapas 1 a 4 reemplazan a lo que hoy hace `publicar()`: la conversión a la landing deja de
estar copiada en el repo. La etapa 2 es la que lo verifica contra un repo real. Las etapas 5 y 6 tienen
síntoma solo cuando haya que publicar en una tienda o mantener un manual; conviene no empezarlas
antes.

### Preguntas abiertas

- El eje `avd` se dibuja también en repos sin app móvil. `Step.requires_repo` oculta pasos, pero
  no hay nada equivalente para un eje.

---

## 11. Riesgos

**Las medidas de las tiendas se desactualizan.** §5.1 lo mitiga, pero igual hay que verificarlas
antes de cada publicación.

**La cámara de cada repo se pudre sola.** Ningún test la corre, y un cambio de interfaz la rompe
sin que nadie se entere hasta la próxima publicación. Los selectores `data-captura` (§7) reducen el
riesgo; no lo eliminan.

**El mapa de rutas del servidor ficticio se desalinea con la API.** Una pantalla que empieza a
pedir un endpoint nuevo rompe la próxima corrida (ADR-0050): se entera quien captura, no quien ve la
landing.

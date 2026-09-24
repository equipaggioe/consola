# Plan — capturas publicables de las apps de un repo

> **Estado (verificado 2026-09-24).** Construido en Consola: `shoot_screens`, `render_shots` con
> los siete destinos, el manifiesto con la comparación contra la corrida anterior, la compuesta
> `screenshots` y el kit de la cámara (`camara/`, [ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
> Lo construido se describe en [arquitectura 19](../arquitectura/19_imagenes.md), que manda sobre
> este plan. La cámara de vettore ya usa el kit, y su panel se capturó y reveló de verdad.
>
> Pendiente en Consola: los marcos de dispositivo, sin especificar (qué destinos, qué aspecto), y
> decidir dónde vive la parte Dart del kit. Pendiente en vettore: correr la app en un emulador y
> publicar en la landing (§6). Pendiente en los repos: la landing leyendo el manifiesto (resto de
> la 5) y el segundo repo (7). Sin verificar ([30](../arquitectura/30_riesgos_y_pendientes.md)): el
> camino con app móvil y una tanda subida de verdad a una tienda.
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
| `SHOTS_LANGS` | — | los idiomas que la app soporta y la cámara sabe capturar. Consola no puede descubrirlos: llenan el eje `languages` |
| `SHOTS_RAW` | `demo/capturas` | dónde deja la cámara los PNG crudos |
| `SHOTS_PUBLISH` | `landing/static/capturas` | dónde deja el revelado los derivados de la landing |
| `SHOTS_DIST` | `demo/publicables` | dónde deja el revelado los demás destinos, una carpeta por destino. Clave y valor por defecto elegidos al implementar |

Sin `SHOTS_CMD` o sin `SHOTS_LANGS`, `shoot_screens` y el paso `shoot` de la compuesta quedan en ámbar
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
| `--apps` | sí | nombres de carpeta separados por coma | eje `apps`: SPA Vite y apps móviles de `core/targets.py` |
| `--themes` | sí | `claro` y/o `oscuro` | eje `themes` |
| `--languages` | sí | los idiomas marcados | eje `languages`, con valores de `SHOTS_LANGS` |
| `--output` | sí | ruta absoluta de la carpeta de crudos | `SHOTS_RAW` resuelta contra la raíz del repo |
| `--kit` | sí | ruta absoluta del kit de la cámara | `camara/index.mjs` de la Consola que corre ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)) |
| `--device` | solo con app móvil | serial del emulador, ya encendido | eje `avd`: Consola arranca ese AVD si no está vivo |

Reglas para el script:

- Captura exactamente esas combinaciones de app, tema e idioma.
- Guarda como `<output>/<app>/<pantalla>.<tema>.<idioma>.png` (§3.2).
- Si no soporta algo de lo pedido, termina con código distinto de cero. No lo ignora en silencio.

El emulador **no** lo busca el script: lo elige quien aprieta el botón y lo enciende Consola, que
ya sabe arrancar AVD (`launch_emulator`). Si se marcó una app móvil y no se eligió emulador, la
corrida corta antes de sacar la primera foto.

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
([marca.md](marca.md)), con el corte de [ADR-0004](../adr/0004-un-boton-por-capacidad.md).

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
| `apps` | descubiertos: SPA Vite y apps móviles del repo | todas marcadas |
| `themes` | Claro · Oscuro | todos marcados |
| `languages` | los de `SHOTS_LANGS` | todos marcados |
| `avd` | AVD creados (`pick`); vacío = ninguno, solo vale sin apps móviles marcadas | vacío |

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

Hecho (sin commitear en vettore):

| Archivo | Cambio |
|---|---|
| `demo/capturar.mjs` | lee el contrato con el kit (`--apps`, `--themes`, `--languages`, `--output`, `--kit`, `--device`); declara que panel y app solo tienen `oscuro` y `es`; nombra los crudos `<pantalla>.<tema>.<idioma>.png`; no busca el emulador; sin `publicar()` |
| `demo/servidor.mjs` | solo quedan las rutas y el protocolo del WebSocket; el servidor es el del kit. Se agregó `/auth/mobile/prekeys`, que el panel pedía y el servidor viejo contestaba 404 en silencio |
| `demo/package.json` | sale `sharp` y salen los scripts |
| `app/test_driver/capturas.dart` | guarda en `SHOTS_DIR` con `SHOTS_SUFFIX`, que pone `flutterDrive` del kit |
| `app/integration_test/capturas_test.dart` | baja el escenario de `/__demo/scenario` |
| `landing/src/lib/content/capturas.ts` | rutas `/capturas/<app>/<pantalla>.oscuro.es.webp` |
| `.consola/config.env` | `SHOTS_CMD=node demo/capturar.mjs` y `SHOTS_LANGS=es` |

Verificado: el panel se capturó con los argumentos que arma Consola y se reveló con `render_shots`
(landing, OG, redes, manual), todo en carpetas temporales.

Falta:

- Renombrar una vez a mano los crudos de la app en `demo/capturas/app/` (`chat.png` →
  `chat.oscuro.es.png`: son oscuros y en español) y borrar los del panel, que se vuelven a sacar.
- Borrar los `.webp` viejos de `landing/static/capturas/` y revelar con «Capturar y publicar».
- Correr la app en un emulador dedicado: la parte Android del kit y el driver no se probaron.

---

## 7. Guía para escribir la cámara de un repo

Esto no lo construye Consola: es lo que aprendió vettore y le ahorra trabajo al próximo repo.

| Tema | Qué hacer |
|---|---|
| Entrar sin login | de menos a más robusto: sembrar la sesión antes de navegar (vettore: JWT ficticio en IndexedDB) · falsear el endpoint de login · un modo demo en la app (`VITE_DEMO=1`) |
| Ids fijos | una ruta `/chats/<uuid>` no se puede escribir si el sembrado usa `uuid4()`. `escenario.json` los trae escritos a mano |
| Selectores | `data-captura="..."` en los contenedores que se tocan, no clases de Tailwind (`.relative.h-8.cursor-pointer` se rompe en el próximo retoque) |
| Esperar | por `data-captura`, no por texto: `"Recorrido en curso"` no aparece en el segundo idioma |
| Datos ficticios | **nunca en la base** ([ADR-0050](../adr/0050-las-capturas-no-tocan-la-base.md)): un escenario JSON del repo, servido por un servidor ficticio que la cámara levanta. Los clientes de verdad apuntan a ese servidor (web: `VITE_SERVER_URL`; emulador: `10.0.2.2`). Lo que el cliente guarda localmente (IndexedDB, base del teléfono) se siembra aparte, como en vettore |
| Ruta no mapeada | el servidor ficticio la anota y la cámara termina con error nombrándola ([ADR-0050](../adr/0050-las-capturas-no-tocan-la-base.md)). Nunca un 404: la pantalla saldría vacía sin aviso |
| Reloj y zona horaria | web: `page.clock.install` y `timezoneId` · Android: `adb` (necesita `adb root`) |

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
| Esqueleto del servidor ficticio | HTTP, CORS, `OPTIONS`, JSON, escrituras → 204, `/__demo/sembrado` para el emulador con su aviso, ruta no mapeada → error | ~50 de `servidor.mjs` |
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
| 2 | **Vettore al contrato** (§6): hecho y verificado el panel; faltan la app y publicar | en vettore, «Capturar y publicar» deja la landing con las pantallas nuevas | 1 h |
| 3 | ~~**`render_shots` para la landing**~~ | construida | — |
| 4 | ~~**Compuesta `screenshots`**~~ | construida | — |
| 5 | ~~Manifiesto~~ (construido) y **landing que lo consume** (del repo) | una captura nueva aparece en la landing sin tocar `capturas.ts` | medio día |
| 6 | ~~Presets de tienda, tablet/iPad y press kit~~ (construidos); **marcos de dispositivo** pendientes | sale la tanda para Play, verificada contra la ficha vigente | 1 día |
| 7 | ~~Kit genérico~~ (construido, JS) y **segundo repo** con escenario y servidor ficticio | el segundo repo usa el kit; sus capturas en su landing | 1 día |
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

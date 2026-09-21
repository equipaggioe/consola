# Plan — capturas publicables de las apps de un repo

> **Estado (verificado 2026-09-21): nada de esto está construido.** No hay ninguna capacidad de
> capturas en `core/catalog.py`, ningún módulo que hable de Playwright o de Pillow, y
> `requirements.txt` solo trae PySide6 y psycopg. Lo que sí existe y este plan da por dado son los
> launchers que publican un endpoint ([ADR-0008](../adr/0008-un-launcher-entrega-un-endpoint.md),
> [arquitectura 11](../arquitectura/11_ejecucion_de_tareas.md)) y el criterio de qué es una atómica
> ([ADR-0004](../adr/0004-un-boton-por-capacidad.md)).
>
> Origen: `vettore/demo/capturar.mjs` ya hace esto para un repo. Este documento decide qué parte de
> ese script es del dominio —y por lo tanto de Consola— y qué parte es de vettore y se queda ahí.

---

## 1. Para qué se sacan estas capturas

No es una prueba de regresión ni un diagnóstico. Es **material publicable**, y cada destino
impone su propio formato. Esta es la lista completa que conviene tener en cabeza antes de
diseñar, porque es la que explica por qué la salida es una matriz y no un archivo:

| Destino | Qué exige | Prioridad |
|---|---|---|
| Landing del producto | ancho grande, `.webp`, peso bajo | alta |
| Google Play | capturas de teléfono y tablet en medidas exactas, gráfico destacado, **una tanda por idioma** | alta |
| App Store | medidas exactas por tamaño de pantalla (6.9", 6.5", iPad), una tanda por idioma | alta |
| Manual de usuario / docs | PNG nítido, la misma pantalla estable entre versiones | alta |
| README del repo | ancho medio, tema claro y oscuro | media |
| Open Graph / Twitter card | 1200×630, un recorte con texto legible en miniatura | media |
| Social preview de GitHub | 1280×640 | baja |
| Redes sociales | 1080×1080 y 1080×1920 | media |
| Press kit | PNG a resolución nativa, sin comprimir, en un ZIP | baja |
| Microsoft Store / F-Droid | solo si el repo publica escritorio o APK fuera de Play | baja |
| Regresión visual | **subproducto gratis**: la misma corrida, comparada contra la anterior | — |

Dos cosas se derivan de la tabla y mandan sobre todo el diseño:

1. **La salida es una matriz**, no un archivo: pantalla × tema × idioma × destino. Cuatro
   pantallas en dos temas y tres idiomas contra cinco destinos son 120 imágenes. Hacerlo a mano
   es exactamente el motivo por el que las capturas de una landing envejecen mal.
2. **Las medidas son dato, no código.** Play y App Store cambian sus requisitos; una constante en
   un `.py` obliga a tocar Consola cuando cambian. Viven en un archivo de presets (§5) y se
   verifican contra la ficha vigente de cada tienda antes de una publicación.

---

## 2. El corte: el repo pone el modo demo, Consola pone la cámara

El dato ficticio siempre es del repo — nadie más sabe qué es una "sala" o un "recorrido". Eso no
impide la genericidad, porque **hay solo tres maneras de meter datos falsos**, y dos ya las tiene
Consola:

| De dónde lee la app | Cómo se le meten datos falsos | ¿Genérico? |
|---|---|---|
| Postgres | `run_mock_seeders` | ✅ ya existe |
| API HTTP | interceptar la red en el navegador y responder JSON de `demo/respuestas/` | ✅ genérico |
| Base local del cliente (IndexedDB, base cifrada) | solo el código de la app puede escribirla | ❌ propio del repo |

La fila del medio es la que ahorra más trabajo: el interceptor de Playwright (`page.route`)
reemplaza a un servidor ficticio escrito a mano. `vettore/demo/servidor.mjs` son 8 KB de Node que
no harían falta en un repo nuevo.

La tercera fila es irreductible, y de ahí sale el contrato. El repo declara **un comando de
sembrado**; Consola lo invoca y no pregunta qué hace por dentro. Para vettore ese comando es el
sembrado que ya existe; para un repo con datos en Postgres es `run_mock_seeders`; para uno que
lee de la API, ninguno.

### 2.1 El contrato: `demo/capturas.json`

Un archivo por repo, versionado, al lado de las fixtures. Es la única cosa que un repo tiene que
escribir para entrar:

```jsonc
{
  "sembrado": "node demo/sembrar.mjs",      // opcional: comando o vacío
  "respuestas": "demo/respuestas",          // opcional: carpeta de JSON por ruta
  "reloj": "2026-03-14T10:20:00",           // hora fija: capturas reproducibles
  "idiomas": ["es", "en"],
  "temas": ["oscuro", "claro"],
  "pantallas": [
    {
      "nombre": "chat",
      "app": "panel",                        // un target de core/targets.py
      "ruta": "/chats/primero",
      "espera": "Recorrido en curso",        // texto que confirma que cargó
      "pausa_ms": 4000,
      "gestos": [
        { "click_rol": "button", "nombre": "Ver historial" },
        { "click_fraccion": ".card-base .barra", "x": 0.45 }
      ]
    }
  ]
}
```

`gestos` es la parte que no se puede evitar: una captura interesante casi nunca es una ruta recién
cargada. Con tres primitivas —`click_rol`, `click_fraccion`, `scroll_a`— entran las cuatro
pantallas que vettore captura hoy. Si aparece una primitiva nueva por cada repo, el contrato está
mal y hay que volver a mirarlo; si aparece una cada diez pantallas, está bien.

**Por qué `demo/` y no `.consola/`:** el guion es contenido del repo, como `escenario.json`. Se
versiona con las fixtures que describe y viaja con ellas. En `.consola/` va lo que Consola
escribe, no lo que el repo declara.

### 2.2 Qué tiene que adaptar cada repo

"Un archivo y nada más" es cierto solo para el repo que ya está preparado. Estos son los cinco
niveles reales, de lo que le toca a todos a lo que le toca a pocos.

**Nivel 0 — todos, sin tocar código.** Escribir `demo/capturas.json` (§2.1): unas veinte líneas.
Media hora.

**Nivel 1 — entrar sin pasar por el login.** Es la adaptación que de verdad decide si el repo
entra o no. Una ruta interna no se alcanza sin sesión, y una captura no puede escribir una
contraseña en un formulario de producción. Hay tres salidas, de menos a más invasiva:

| Salida | Qué cuesta |
|---|---|
| Sembrar la sesión antes de navegar (token en `localStorage` / almacén seguro) | lo que ya hace `capturar.mjs` con su JWT ficticio: el repo declara dónde va el token |
| Falsear el endpoint de login con el interceptor | nada, si los datos vienen de la API |
| Un modo demo en la app (`VITE_DEMO=1`) que entra sola | una línea en el arranque, y es lo más robusto |

**Nivel 2 — que la pantalla sea alcanzable y estable.** Tres detalles que parecen menores y son
los que rompen las corridas:

- **Ids fijos en los datos falsos.** Una ruta `/chats/<uuid>` no se puede escribir en el guion si
  el sembrado genera ids al azar. `escenario.json` de vettore ya los trae escritos a mano; un
  sembrado que usa `uuid4()` hay que fijarlo con una semilla.
- **Selectores estables.** `capturar.mjs` localiza la barra de reproducción con
  `.relative.h-8.cursor-pointer` — clases de Tailwind. Eso se rompe con el próximo retoque de
  estilo. Un `data-captura="barra-recorrido"` en los dos o tres contenedores que el guion toca
  cuesta cinco minutos y le da años de vida al guion.
- **Esperar por testid, no por texto.** `espera: "Recorrido en curso"` deja de funcionar al
  cambiar una palabra del copy, y **nunca** funciona en el segundo idioma. Con `data-captura` el
  guion es independiente del idioma, que es justo lo que la matriz de §1 necesita.

**Nivel 3 — de dónde salen los datos falsos.** Según la tabla de §2:

- *Postgres*: el repo necesita tener su seeder mock. Si ya lo tiene, cero trabajo.
- *API HTTP*: escribir `demo/respuestas/<ruta>.json`. No se escriben a mano — se **graban**: una
  pasada con el HAR de Playwright contra un backend de desarrollo deja los archivos, y después se
  editan los nombres y los datos sensibles. Esto es una etapa de Consola, no trabajo del repo.
- *Base local del cliente*: el repo escribe su propio sembrado, como vettore. Irreductible.

**Nivel 4 — solo si se captura la app móvil.** Acá está el grueso y conviene decirlo sin
adornos: la prueba de integración que navega la app es código del repo que importa las entrañas
del repo. En vettore son **295 líneas de Dart** (`integration_test/capturas_test.dart`) más 16 del
driver, y tocan `local_chat_db`, `geofence_store` y las mismas opciones de `FlutterSecureStorage`
que usa `SessionStore`. Nada de eso se puede generar desde afuera. Consola puede repartir una
**plantilla** de esos dos archivos —el esqueleto es siempre igual— pero el recorrido y el sembrado
los escribe el repo. Un día por app, la primera vez.

**Nivel 5 — opcional.** Que la landing consuma el manifiesto (§4) en vez de rutas escritas a
mano. En vettore eso sería cambiar `landing/src/lib/content/capturas.ts`. Media hora, y a partir
de ahí una captura nueva aparece en la landing sin tocar código.

### 2.3 Lo que el repo NO tiene que tocar

Para que el balance sea honesto, esto es responsabilidad de Consola y ningún repo debe ocuparse:
congelar animaciones y transiciones (inyectando `prefers-reduced-motion`), esperar a que carguen
las fuentes y las imágenes, fijar el reloj y la zona horaria, el tema cuando la app respeta
`prefers-color-scheme`, el escalado y el recorte para cada destino, los marcos de dispositivo, y
el nombrado y el manifiesto de salida.

El tema es el único con letra chica: si la app guarda la preferencia en `localStorage` en vez de
mirar el sistema, el guion declara la clave y el valor, y Consola la escribe antes de cargar. Una
línea en el JSON, ninguna en el repo.

---

## 3. Las capacidades

Grupo nuevo **Capturas** (`📸`). Tres atómicas y una compuesta, con el corte de
[ADR-0004](../adr/0004-un-boton-por-capacidad.md): cada una tiene sentido re-ejecutarla sola.

| id | kind | Qué hace | Por qué sola |
|---|---|---|---|
| `shoot_screens` | `once` | recorre el guion contra la app viva y deja PNG crudos | es lo que se repite al cambiar una pantalla |
| `render_shots` | `once` | de los PNG crudos produce los derivados de cada destino | cambió la medida de una tienda, no la app |
| `frame_shots` | `once` | pone el marco de dispositivo y arma el press kit | oculta: es un paso de `render_shots` |
| `capturas` | `once`, `level='C'` | sembrar → fotografiar → derivar → publicar | el botón que se aprieta de verdad |

`shoot_screens` **no levanta nada**: se engancha al endpoint que otra pestaña ya publicó
(`ctx.endpoint('spa:panel')`, como hace `backend_url` en `launchers.py`). Levantar la app ya es un
botón, y duplicarlo acá sería un segundo dev server compitiendo por el puerto. La compuesta
`capturas` sí puede arrancarla, igual que `dev_env` arranca a sus pasos.

### 3.1 Ejes (van a `params.json`: son decisiones de la corrida)

| Eje | `expand` | Notas |
|---|---|---|
| `target` | `scope`, `discover=(SPA_VITE,) + MOBILE_APP` | qué app se fotografía |
| `pantallas` | `checks`, `select='many'`, `source=SHOTS_SCREENS` | llenado leyendo el guion; permite recapturar una sola |
| `temas` | `checks` | `claro` / `oscuro`, los que declare el guion |
| `idiomas` | `checks` | ídem |
| `destinos` | `checks` | landing · play · appstore · manual · og · redes · presskit |
| `device` | `pick`, `source=ANDROID_RUNNING` | solo para la app móvil; vacío = el que esté corriendo |
| `preferred_port` | `field`, `cast='int'` | igual que en los launchers |

`SHOTS_SCREENS` es una fuente consultada nueva en `core/catalog.py::queried_values`, hermana de
`VPS_SERVICES`: sus valores no salen del catálogo ni de mirar carpetas, salen de leer el guion del
repo. Sin caché — es un archivo local y cambiarlo debe verse al abrir la pestaña
([arquitectura 10](../arquitectura/10_catalogo_de_capacidades.md)).

### 3.2 Claves de `config.env` (datos que la tarea lee)

| Clave | Por defecto |
|---|---|
| `SHOTS_FILE` | `demo/capturas.json` |
| `SHOTS_RAW` | `demo/capturas` |
| `SHOTS_PUBLISH` | `landing/static/capturas` |

Nada más. Los temas, los idiomas y las pantallas **no** van acá: son del guion, que es del repo y
se versiona. Las medidas de cada destino tampoco: son de Consola (§5).

---

## 4. El pipeline

```
sembrado           crudo                          derivados
─────────          ──────────────────────         ──────────────────────────────
seeders   ─┐
respuestas ┼─► PNG a resolución nativa  ─┬─► landing/   <nombre>.webp
comando   ─┘   <pantalla>.<tema>.<idioma>.png  ├─► play/      1080×1920
                                          ├─► appstore/  1290×2796
                                          ├─► manual/    PNG 2x
                                          ├─► og/        1200×630
                                          └─► presskit/  ZIP nativo
                                                     + capturas.json (manifiesto)
```

**Se fotografía una sola vez, a resolución nativa.** Todo lo demás es recorte y escalado sobre ese
PNG. Volver a manejar el navegador por cada destino multiplicaría por cinco lo único lento del
proceso, y las cinco imágenes podrían salir distintas entre sí.

El **manifiesto** (`capturas.json` de salida: nombre, pantalla, tema, idioma, destino, medida,
hash) es lo que permite que la landing y el manual indexen las imágenes en vez de referenciarlas a
mano — y lo que hace posible la regresión visual, comparando hashes entre corridas.

---

## 5. Los presets de destino

Un archivo de datos de Consola (`core/shots_presets.json`), no constantes en el código:

```jsonc
{
  "play": { "medidas": [[1080,1920],[1920,1200]], "formato": "png", "marco": false },
  "appstore": { "medidas": [[1290,2796],[2048,2732]], "formato": "png", "marco": false },
  "landing": { "ancho": 1920, "formato": "webp", "calidad": 82 },
  "og": { "medidas": [[1200,630]], "recorte": "centro", "formato": "png" }
}
```

**Las medidas exactas de Play y App Store hay que verificarlas contra la ficha vigente antes de
cada publicación**: las dos tiendas las cambian y ninguna avisa. Son dato justamente por eso — se
corrigen editando el JSON, sin tocar Consola. Un repo puede pisar un preset desde su guion cuando
publica algo raro.

---

## 6. Lo que la v1 no hace

Escrito para que no se cuele por la ventana: **video y GIF** de un flujo (Playwright los graba, y
es otra conversación), **anotaciones de manual** (flechas y globos sobre la captura), **subir a
las tiendas** (es una API por tienda, con credenciales, y no es una captura), y **traducir los
textos de la app** — los idiomas se recorren, no se generan.

---

## 7. Plan por etapas

Cada etapa termina con algo que se puede apretar y mirar. Las horas son de esfuerzo, no de
calendario.

| # | Etapa | Entregable verificable | Esfuerzo |
|---|---|---|---|
| 1 | **Dependencias**: `playwright` + `Pillow` en `requirements.txt`, `playwright install chromium` como paso de `core/toolchain.py`, con su chequeo de disponibilidad | el botón aparece en ámbar cuando falta chromium, y en verde después de instalarlo | 3 h |
| 2 | **`shoot_screens` mínimo**: lee el guion, se engancha a un endpoint vivo, recorre rutas, espera texto, saca PNG | con `serve_vite` en otra pestaña, salen los PNG de un repo real | 1 día |
| 3 | **Gestos**: `click_rol`, `click_fraccion`, `scroll_a`; reloj y zona horaria fijos | las cuatro pantallas de vettore salen iguales que con `capturar.mjs` | medio día |
| 4 | **`render_shots` + manifiesto**: `.webp` para la landing y `capturas.json` de salida | la landing consume el manifiesto en vez de rutas escritas a mano | medio día |
| 5 | **Matriz** tema × idioma: el guion las declara, el eje las marca | una corrida deja las dos tandas de idioma que pide Play | medio día |
| 6 | **Datos falsos sin servidor**: interceptor desde `demo/respuestas/`, y comando de sembrado declarado | un repo con API captura sin backend levantado | 1 día |
| 7 | **Presets de tienda + marcos de dispositivo + press kit** | sale la tanda completa lista para subir a Play | 1 día |
| 8 | **App móvil**: emulador, `adb` (zona horaria y reloj), `flutter drive` con el driver del repo | la app en el emulador entra en la misma matriz | 1,5 días |
| 9 | **Compuesta `capturas`** con sus pasos, y la entrada en `docs/` | un botón, de repo limpio a carpeta publicable | medio día |
| 10 | **Regresión visual** (opcional): diff contra la corrida anterior usando los hashes del manifiesto | avisa qué pantalla cambió entre dos versiones | medio día |

**Corte natural en la etapa 5.** De la 1 a la 5 es una herramienta completa y útil para landing,
README y manual, y son unos tres días. De la 6 a la 8 está la complejidad real —el sembrado sin
servidor y el emulador— y conviene empezarlas recién cuando la 5 esté en uso y haya un segundo
repo pidiéndolas: es la única manera de saber si el contrato del guion aguanta más de un caso.

---

## 8. Riesgos

**El guion se convierte en un lenguaje de programación.** Es el riesgo real. Cada primitiva nueva
es una señal; si un repo necesita una cuarta forma de gesto, la respuesta correcta puede ser que
ese repo exponga una ruta de demo que ya muestre la pantalla en el estado que hay que fotografiar
— es más barato que un `gesto: { esperar_websocket: ... }`.

**Las medidas de las tiendas se pudren.** Mitigado con §5, pero hay que verificarlas antes de cada
publicación igual.

**La app móvil es frágil.** `flutter drive` con el reloj movido ya dio problemas en vettore: hay
que tocar la hora **después** de que la app arrancó, o el driver se queda con un puerto viejo del
logcat. Ese conocimiento se porta tal cual; no conviene redescubrirlo.

**Un emulador dedicado.** La captura de la app móvil borra la base local y la sesión del
dispositivo. Vale la misma advertencia que en `capturar.mjs`: nunca contra un emulador con una
cuenta que importe.

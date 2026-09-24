# Plan — capturas publicables de las apps de un repo

> **Estado (verificado 2026-09-24).** Construidas las etapas 1, 3 y 4 de §10: `shoot_screens`,
> `render_shots` (solo el destino `landing`) y la compuesta `screenshots`, en
> `core/tasks/images.py` y `core/shots.py`. Lo construido se describe en
> [arquitectura 19](../arquitectura/19_imagenes.md), que manda sobre este plan.
>
> Pendiente: la etapa 2 (la cámara de vettore al contrato), y de la 5 en adelante. Sin verificar:
> el camino con app móvil, que enciende el emulador ([30](../arquitectura/30_riesgos_y_pendientes.md)).
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

La cámara genérica puede volver a tener sentido para los repos web cuyos datos vienen de Postgres
o de una API. Eso se evalúa en §8, con datos.

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
el botón. Van como argumentos y no como variables de entorno ni como un archivo: son cinco valores
simples, se ven en el comando y el script se puede probar a mano.

```
node demo/capturar.mjs --apps panel,app --themes oscuro,claro --languages es \
                       --output E:/Git/vettore/demo/capturas --device emulator-5554
```

| Argumento | Obligatorio | Contenido | De dónde sale |
|---|---|---|---|
| `--apps` | sí | nombres de carpeta separados por coma | eje `apps`: SPA Vite y apps móviles de `core/targets.py` |
| `--themes` | sí | `claro` y/o `oscuro` | eje `themes` |
| `--languages` | sí | los idiomas marcados | eje `languages`, con valores de `SHOTS_LANGS` |
| `--output` | sí | ruta absoluta de la carpeta de crudos | `SHOTS_RAW` resuelta contra la raíz del repo |
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

Un archivo de datos de Consola (`core/shots_presets.json`):

Hoy solo tiene `landing` (`max_width` por tipo de app y `quality`). Los demás destinos, propuesta:

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

## 6. Qué cambia en vettore

| Archivo | Cambio |
|---|---|
| `demo/capturar.mjs` | lee `--apps`, `--themes`, `--languages`, `--output` y `--device` en vez del objetivo posicional; nombra los crudos `<pantalla>.<tema>.<idioma>.png`; deja de buscar el emulador; se borra `publicar()` y el objetivo `publicar` |
| `demo/package.json` | sale `sharp` |
| `landing/src/lib/content/capturas.ts` | las rutas pasan a `/capturas/<app>/<pantalla>.oscuro.es.webp`, porque el revelado conserva tema e idioma en el nombre; pasa a leer el manifiesto en la etapa 5 |
| `landing/static/capturas/` | se borran los `.webp` viejos, con el nombre sin tema ni idioma |
| `.consola/config.env` | `SHOTS_CMD=node demo/capturar.mjs` y `SHOTS_LANGS=es` |

El ancho por app de `publicar()` (`{ app: 540, panel: 1920 }`) ya está en el preset `landing`, por
tipo de app.

---

## 7. Guía para escribir la cámara de un repo

Esto no lo construye Consola: es lo que aprendió vettore y le ahorra trabajo al próximo repo.

| Tema | Qué hacer |
|---|---|
| Entrar sin login | de menos a más robusto: sembrar la sesión antes de navegar (vettore: JWT ficticio en IndexedDB) · falsear el endpoint de login · un modo demo en la app (`VITE_DEMO=1`) |
| Ids fijos | una ruta `/chats/<uuid>` no se puede escribir si el sembrado usa `uuid4()`. `escenario.json` los trae escritos a mano |
| Selectores | `data-captura="..."` en los contenedores que se tocan, no clases de Tailwind (`.relative.h-8.cursor-pointer` se rompe en el próximo retoque) |
| Esperar | por `data-captura`, no por texto: `"Recorrido en curso"` no aparece en el segundo idioma |
| Datos ficticios | Postgres → `run_mock_seeders` · API → interceptor `page.route` (solo web) o servidor ficticio (web y móvil) · base local del cliente → sembrado propio |
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

## 8. Cuándo volver a mirar la cámara genérica

Hoy hay un solo script de capturas, y no se puede medir qué se repite entre repos. Candidatos para
el segundo: los paneles y backoffices de banditore, cadenza, concordia, navetta y presenze. Ninguno
usa IndexedDB, así que sus datos vienen de Postgres o de la API.

Con dos scripts escritos:

1. Contar las líneas que se repiten entre los dos, separando la navegación (propia de cada app) de
   la plomería (levantar Vite, esperar, reintentar, fijar el reloj).
2. Si lo repetido es plomería, extraer un helper compartido.
3. Si también se repite la **forma** de la navegación (ruta → esperar → gesto → foto), evaluar el
   guion JSON de la versión anterior de este plan (en el historial de git), pero solo para esos
   repos. Vettore queda con su script.

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
| 2 | **Vettore al contrato** (§6) | en vettore, «Capturar y publicar» deja la landing con las pantallas nuevas | 2 h |
| 3 | ~~**`render_shots` para la landing**~~ | construida | — |
| 4 | ~~**Compuesta `screenshots`**~~ | construida | — |
| 5 | **Manifiesto** y landing que lo consume | una captura nueva aparece en la landing sin tocar `capturas.ts` | medio día |
| 6 | **Presets de tienda, marcos de dispositivo y press kit** | sale la tanda para Play, verificada contra la ficha vigente | 1 día |
| 7 | **Segundo repo** con cámara propia (§8) | sus capturas en su landing; la medición de §8 escrita | 1 día |
| 8 | **Regresión visual** (opcional): diff de hashes contra la corrida anterior | avisa qué pantalla cambió entre dos versiones | medio día |

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

**Plomería copiada entre repos.** Levantar Vite, esperar y reintentar se va a repetir en cada
cámara web. §8 fija cuándo medirlo y extraerlo.

# Plan — íconos de las apps a partir del logo del repo

> **Estado (verificado 2026-09-24): solo está el botón, sin cuerpo.** `core/catalog.py` declara
> `generate_icons` como stub (sin `bind`) en el grupo **Marca y capturas**, y `core/settings.py`
> las claves `BRAND_ICON` y `BRAND_ICON_FOREGROUND`. Nada las implementa.
>
> Origen: `vettore/brand/generate.py`. Este plan decide qué parte de ese script pasa a Consola.
> Las capturas, que viven en el mismo grupo del menú, tienen su propio plan:
> [capturas.md](capturas.md).
>
> Las decisiones marcadas *(propuesta)* no están confirmadas. Donde este plan y el código no
> coincidan, manda [`docs/arquitectura/`](../arquitectura/README.md).

---

## 1. El síntoma

| Repo | App | Favicon o ícono hoy |
|---|---|---|
| vettore | `panel` | **el logo de Svelte** (el `favicon.svg` que deja la plantilla) |
| banditore | `backoffice` | el logo de Svelte |
| cadenza | `backoffice` | el logo de Svelte |
| navetta | `panel` | el logo de Svelte |
| presenze | `panel` | el logo de Svelte |
| posta | `backoffice` | el logo de Svelte |
| vettore | `backoffice` | una copia a mano de `brand/logomark.svg`, que se desactualiza si cambia el logo |
| vettore | `landing` | importa `brand/logomark.svg` directo (`$brand`): correcto |
| vettore | `app` (Flutter) | `brand/generate.py` rasteriza los SVG y corre `flutter_launcher_icons`: correcto, pero solo existe en este repo |
| posta | `terminal` (Flutter) | `flutter_launcher_icons` desde un PNG suelto, sin SVG de origen |

Seis SPA muestran el logo de Svelte en la pestaña del navegador. El generador que sí funciona
está en un solo repo y solo cubre Flutter: su propio docstring deja los favicons "para otra pasada".

Solo vettore tiene hoy un logo en SVG. En los demás repos el botón queda en ámbar hasta que
alguien le dé un logo; eso es trabajo de diseño, no de Consola.

---

## 2. Por qué es un botón aparte de las capturas

| | Capturas | Íconos |
|---|---|---|
| Entrada | la app corriendo | el SVG del logo |
| Salida | material para publicar | archivos que se compilan con la app |
| Frecuencia | cada vez que cambia una pantalla | cuando cambia el logo |
| ¿Script del repo? | sí ([ADR-0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md)) | **no**: el repo solo pone el SVG |

La última fila decide el diseño. `generate.py` no conoce nada propio de vettore salvo dónde están
los SVG, así que se reimplementa como función de Consola, igual que el resto de los scripts
([ADR-0001](../adr/0001-reimplementar-no-ejecutar-scripts.md)).

Comparten grupo porque las dos cosas son la imagen del producto, y porque el revelado de capturas
va a leer el logo para el gráfico destacado de Play y las tarjetas Open Graph
([capturas.md](capturas.md) §5).

---

## 3. El contrato con el repo *(propuesta)*

### 3.1 Claves de `config.env`

| Clave | Por defecto | Qué es |
|---|---|---|
| `BRAND_ICON` | — | el logo cuadrado en SVG, relativo a la raíz. En vettore: `brand/logomark.svg` |
| `BRAND_ICON_FOREGROUND` | — | la capa de adelante del ícono adaptativo de Android, en SVG. En vettore: `brand/android_foreground.svg` |

Sin `BRAND_ICON` el botón queda en ámbar. `BRAND_ICON_FOREGROUND` solo se exige al correr, y solo
para una app Flutter cuyo pubspec declare `adaptive_icon_foreground`: ahí falta es error.

La capa adaptativa es un archivo aparte y no se genera sola a partir del logo: lleva el mismo
dibujo reescalado a la zona segura de 66 dp sobre el lienzo de 108 dp, y decidir cuánto margen
deja es diseño.

### 3.2 Qué hace por tipo de app

| Tipo | Qué genera | Dónde lo deja |
|---|---|---|
| Flutter | `BRAND_ICON` → PNG 1024×1024, y `BRAND_ICON_FOREGROUND` → PNG 1024×1024; después corre `dart run flutter_launcher_icons` en la carpeta de la app | en las rutas que la sección `flutter_launcher_icons:` del `pubspec.yaml` declara en `image_path` y `adaptive_icon_foreground` |
| SPA Vite | copia `BRAND_ICON` tal cual | `<app>/src/lib/assets/favicon.svg`, que es el que importa el `+layout.svelte` de la plantilla (y el que escribe `create_spa`) |

Las rutas de Flutter se leen del pubspec y no de otra clave: ese archivo ya es la fuente de verdad
de qué PNG consume el paquete, y declararlas dos veces sería una segunda fuente que se desfasa.

Falla con error, sin adivinar:

- Una app Flutter sin sección `flutter_launcher_icons:` en su pubspec, o sin el paquete en
  `dev_dependencies`.
- Una SPA sin `src/lib/assets/favicon.svg`. Es la señal de que esa app toma el ícono de otro lado
  (la landing de vettore importa `$brand` directo), y hay que desmarcarla.

### 3.3 El eje

| Eje | `expand` | Valores |
|---|---|---|
| `apps` | `checks`, `select='many'` | descubiertos: apps Flutter y SPA Vite del repo |

---

## 4. Rasterizar sin dependencias nuevas

`generate.py` usa `resvg-py`. Consola ya trae PySide6, que incluye `QtSvg`.

**Verificado el 2026-09-24:** `QSvgRenderer` con antialiasing, sobre `brand/logomark.svg` y
`brand/android_foreground.svg` de vettore a 1024×1024, da un PNG visualmente igual al que
`generate.py` dejó en `app/assets/launcher_icon/`. Diferencia media por canal: 0,24 de 255; solo
el 0,3 % de los canales difiere en más de 8, todos en los bordes del antialiasing.

Límite conocido: `QtSvg` implementa SVG Tiny 1.2. Un logo con filtros, máscaras o CSS se vería
distinto. Si aparece uno, la decisión es cambiar a `resvg-py`, no mantener los dos.

---

## 5. Lo que la v1 no hace

- **Apps Flet** (los `customer` y `vendor` de banditore): `flet build` toma el ícono de
  `src/assets/icon.png`. Entran cuando un repo con logo SVG tenga una app Flet.
- **Íconos PWA y `apple-touch-icon`** de las SPA: solo `posta/clientes` es PWA hoy.
- **Imágenes del logo dentro de la app** (`vettore/app/assets/brand/logomark.png` y `logo.png`,
  que usan las pantallas de bloqueo y registro). No se sabe si alguien las regenera; si no, se
  desactualizan igual que el favicon del backoffice. *(Sin confirmar.)*
- **Escritorio** (Windows, macOS, Linux).

---

## 6. Etapas

| # | Etapa | Entregable verificable | Esfuerzo |
|---|---|---|---|
| 1 | **SPA**: copiar el logo a `src/lib/assets/favicon.svg` | el panel de vettore muestra su logo en la pestaña | 2 h |
| 2 | **Flutter**: rasterizar con `QtSvg`, leer las rutas del pubspec, correr `flutter_launcher_icons` | el ícono de la app de vettore sale igual que con `generate.py` | medio día |
| 3 | En vettore: `BRAND_ICON` y `BRAND_ICON_FOREGROUND` en su `config.env`; se borra `brand/generate.py` y el comentario del pubspec que lo nombra | `generate.py` ya no existe y los íconos se regeneran desde Consola | 1 h |
| 4 | `docs/arquitectura/` al día | — | 1 h |

### Preguntas abiertas

- ¿El nombre del grupo, **Marca y capturas**, queda así?
- ¿Las imágenes del logo dentro de la app Flutter (§5) entran en este botón?

# ADR-0056 · Cada tecnología declara dónde va su ícono, y todos salen de `brand/`

- **Estado:** Aceptada
- **Modificada por:** [ADR-0057](0057-el-manifest-de-la-pwa-es-un-archivo-estatico.md), que lee el manifest de la PWA de un archivo estático y no de `vite.config`. Cambia el punto 1 en lo que hace al manifest y el punto 3 en el archivo `any` y `maskable`; el resto sigue en pie.
- **Fecha:** 2026-09-25
- **Alcance:** `core/icons.py`, `core/tasks/raster.py`, `core/tasks/images.py::generate_icons`, `core/tasks/builders.py::compile_binary`, la clave `BRAND_ICON_MASKABLE`; extiende [ADR-0055](0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md) y quita el campo `icon` de «Compilar ejecutable»

## Contexto

ADR-0055 cubría dos formas: la app Flutter con `flutter_launcher_icons:` y la SPA con el `favicon.svg` de la plantilla. Medido en los 17 repos el 2026-09-25, las apps toman su ícono de más lugares:

| Forma | Apps |
|---|---|
| `<link rel="icon">` en `app.html` hacia `static/favicon.svg` | las landings de cadenza, concordia, navetta y presenze; navetta/web |
| `<link rel="icon">` en `index.html` hacia `public/` (Svelte sin Kit) | spazio/frontend |
| `<link>` del `+layout.svelte` con un import de `$lib/` que no es `favicon.svg` | banditore/landing (`logo-icon.svg`), cassetti/web (`logomark.svg`) |
| Manifest de `VitePWA` o `SvelteKitPWA`, con íconos `maskable` | concordia/web, posta/clientes |
| `src/assets/icon.png`, que toma `flet build` | banditore/mobile_customer y mobile_vendor, con el logo de Flet que deja la plantilla |
| El campo `icon` de «Compilar ejecutable», vacío en todos | las ocho apps Python de escritorio |

Solo vettore tenía sus SVG en `brand/`. En los demás, el logo vivía dentro de una de las apps: en `landing/static/favicon.svg` o en `landing/src/lib/assets/`.

Un ícono maskable de PWA no es el logo: Android lo recorta con su propia máscara y solo respeta el círculo central del 80 %, así que lleva el fondo a sangre y el dibujo más adentro.

## Decisión

1. **La app declara, Consola llena.** Además de lo de ADR-0055:
   - Una SPA declara cada `<link rel="icon">` y `rel="apple-touch-icon"` de su `+layout.svelte` (si importa de `$lib/`), de su `src/app.html` o de su `index.html`, y cada ícono del manifest de su PWA en `vite.config`. Una ruta absoluta va a `static/` en SvelteKit (lo dice el paquete `@sveltejs/kit`) y a `public/` en Vite.
   - Una app Flet declara `src/assets/icon.png`.
2. **El formato sale de la extensión.** Un `.svg` recibe la capa tal cual. Un `.png` se rasteriza al lado de su `sizes`: sin `sizes`, o con un `sizes` no cuadrado, corta. Un `.ico` lleva los lados de 16 a 256. Flutter y Flet, a 1024.
3. **Tercera capa, `BRAND_ICON_MASKABLE`.** Es un SVG del repo, como la capa frontal de Android, y va a todo archivo que el manifest declara `maskable`. Si el mismo archivo se declara `any` y `maskable`, lleva la maskable, que sirve para los dos usos. La exige solo la app que la pide.
4. **El ejecutable toma el logo.** «Compilar ejecutable» deja de tener el campo `icon`: con `BRAND_ICON` escribe `build/icon.ico` y lo pasa en `--icon`. Sin `BRAND_ICON`, el ejecutable sale sin ícono.
5. **Los SVG de un repo viven en `brand/`**: `logomark.svg`, y cuando hacen falta `android_foreground.svg` y `maskable.svg`. Las copias que hay dentro de cada app son salidas de «Generar íconos».

## Consecuencias

- Una app que no declara dónde va su ícono no aparece en la lista. Hoy son banditore/panel y posta/backoffice (tienen el `favicon.svg` de la plantilla, pero nada lo usa), concordia/panel, las tres apps Flutter de navetta y banditore/background_gps.
- Una declaración que Consola no sabe llenar hace que la app aparezca igual, y la corrida dice qué falta. Por ejemplo, posta/clientes tiene un `<link rel="icon">` a un PNG sin `sizes`.
- El manifest de la PWA se lee de un archivo TypeScript con expresiones regulares: el `src` y los `sizes` tienen que estar escritos como texto. Un `${...}` al principio de la ruta se ignora.
- Cambiar el logo de un repo es editar `brand/` y apretar un botón.

## Descartado

- **Leer el manifest de la PWA ejecutando `vite.config`.** Exigiría levantar Node con las dependencias de la app para leer cuatro rutas.
- **Deducir el ícono maskable del logo con un margen fijo.** Cuánto margen deja es diseño, igual que en la capa frontal de Android.
- **Dejar el logo donde estaba y apuntar `BRAND_ICON` a la landing.** Sería una app que depende de otra. vettore y banditore ya renombraron sus apps una vez, y cada renombre habría roto la clave.
- **Conservar el campo `icon` de «Compilar ejecutable».** Sería una segunda fuente del ícono, que se desfasa del logo.

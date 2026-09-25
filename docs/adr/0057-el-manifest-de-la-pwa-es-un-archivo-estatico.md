# ADR-0057 · El manifest de la PWA es un archivo estático que la app enlaza

- **Estado:** Propuesta
- **Fecha:** 2026-09-25
- **Alcance:** `core/icons.py::_manifest_places`; reemplaza la parte del punto 1 de [ADR-0056](0056-cada-tecnologia-declara-donde-va-su-icono.md) que lee el manifest de `vite.config`, y su regla de que un archivo `any` y `maskable` lleva la maskable

## Contexto

ADR-0056 leía los íconos del manifest de la PWA dentro de la llamada a `VitePWA(` o `SvelteKitPWA(` de `vite.config`, con expresiones regulares sobre TypeScript. Esa lectura deja de ver un manifest escrito de otra forma: una constante, un `import`, un `src` armado con una función. Y un ícono que Consola no ve se queda viejo sin que nadie lo note.

El manifest de una PWA es, en la especificación del W3C, un archivo JSON que la página enlaza con `<link rel="manifest">`. `vite-plugin-pwa` lo genera desde su configuración, pero acepta `manifest: false` y entonces no lo genera ni inyecta el `<link>`.

concordia/web declaraba el mismo `icon-512.png` como `any` y como `maskable`. Un ícono maskable lleva el dibujo dentro del círculo central del 80 % para que Android lo recorte; visto entero, como `any`, queda chico. Por eso la guía de web.dev pide un archivo para cada propósito.

## Decisión

1. **El manifest de una PWA es un archivo de `static/` (SvelteKit) o `public/` (Vite)** que la app enlaza con `<link rel="manifest">` en `src/app.html` o `index.html`. El plugin de PWA va con `manifest: false`.
2. **Consola lee ese archivo como JSON.** Un `src` relativo se resuelve contra la carpeta del manifest, como en el navegador; uno que empieza por `/`, contra `static/` o `public/`.
3. **Si el plugin de PWA genera el manifest**, porque falta `manifest: false`, la corrida corta y dice dónde va.
4. **Cada ícono tiene un solo propósito:** `any` (o ninguno) lleva el logo, `maskable` lleva la capa maskable. Un `purpose` con los dos, o con otro valor, corta.

## Consecuencias

- Consola ya no lee TypeScript para las PWA: `json.loads` sobre el archivo que nombra el `<link>`.
- Las rutas del manifest son relativas y no llevan el prefijo del proxy: `start_url: "./"` y `icons/icon-192.png` sirven con y sin él. En concordia/web, `vite.config.ts` deja de importar `base.generated.js`.
- El plugin ya no suma el manifest a la lista de precarga del service worker; la app lo pide en `globPatterns` (`webmanifest`).
- Un manifest en JSON no admite comentarios.
- posta/clientes sigue con el manifest dentro de `vite.config`: la corrida sobre ella corta hasta que se mueva.

## Descartado

- **Seguir leyendo `vite.config` con expresiones regulares.** Es la lectura frágil que motiva este ADR.
- **Leer el manifest ejecutando `vite.config`.** Exigiría levantar Node con las dependencias de la app ([ADR-0056](0056-cada-tecnologia-declara-donde-va-su-icono.md)).
- **`@vite-pwa/assets-generator`.** Genera los íconos de la PWA desde el SVG, pero suma un paquete de Node y un paso de compilación a cada PWA, y deja sus íconos fuera de «Generar íconos».
- **Que un archivo `any maskable` lleve la maskable**, como decía ADR-0056. Sirve a Android y achica el ícono en todos los demás lados.

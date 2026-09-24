# ADR-0049 · La cámara de capturas es un script del repo que Consola corre con argumentos

- **Estado:** Aceptada
- **Fecha:** 2026-09-24
- **Alcance:** core/catalog.py, core/settings.py

## Contexto

Las capturas publicables de un repo (landing, tiendas, redes) tienen dos mitades. Sacar la foto exige conocer la app: sembrar sus datos ficticios, entrar sin login, navegar y hacer los gestos. Convertir cada foto a las medidas de cada destino es igual en todos los repos.

El único caso escrito, `vettore/demo/capturar.mjs`, siembra el panel dentro de la página importando sus propios módulos y coordina un servidor ficticio con el reloj del emulador. Un guion declarativo manejado por Consola no alcanzaba ese caso sin volverse un lenguaje de programación.

[ADR-0001](0001-reimplementar-no-ejecutar-scripts.md) prohíbe que Consola lance scripts como subprocesos, y correr la cámara del repo podría leerse como una violación.

## Decisión

1. **La cámara es código del repo.** Consola la corre con el comando que declara `SHOTS_CMD` en `config.env`, desde la raíz del repo, y no pregunta qué hace por dentro.
2. **No contradice ADR-0001.** Ese ADR prohíbe que Consola delegue **su propia** lógica en scripts copiados. Aquí el subproceso es un binario externo (`node`, `flutter`) y lo que ejecuta es código del repo administrado, igual que los payloads que importan `seeders.` o el `npm run build` de `build_vite`.
3. **Consola elige qué capturar y se lo dice al script por argumentos**, no por variables de entorno ni por un archivo: `--apps`, `--themes`, `--languages`, `--output` y `--device` cuando hay una app móvil. Son valores simples, se ven en el comando y el script se puede probar a mano.
4. **El script falla ruidoso.** Si no soporta algo de lo pedido, termina con código distinto de cero; no lo ignora.
5. **El emulador lo elige quien aprieta el botón y lo enciende Consola**, que ya sabe arrancar AVD. El script recibe el serial en `--device` y no busca uno por su cuenta. Si se marcó una app móvil sin emulador, la corrida corta antes de la primera foto.
6. Las pantallas no se eligen desde Consola: solo el script sabe cuáles existen.

## Consecuencias

- Cada repo que quiera capturas escribe su propia cámara, en su lenguaje (Playwright, Dart), y lee cinco argumentos.
- Lo que se repite entre cámaras (levantar Vite, esperar, reintentar) queda copiado en cada repo hasta que haya dos para comparar.
- Los idiomas no se pueden descubrir mirando el repo: se declaran en `SHOTS_LANGS`.

## Descartado

- **Una cámara genérica en Consola con un guion JSON de rutas y gestos.** No alcanzaba el único caso real: la siembra dentro de la página y la coordinación con el emulador exigían primitivas nuevas desde el primer repo.
- **Pasar la selección por variables de entorno o por un archivo JSON.** Las variables son invisibles en el comando; el archivo obliga al script a buscarlo y a Consola a escribirlo antes de cada corrida. Con cinco valores simples, los argumentos bastan.

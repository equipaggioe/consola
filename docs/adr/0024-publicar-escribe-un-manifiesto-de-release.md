# ADR-0024 · Un artefacto nunca se sube solo: va con su manifiesto de versión y con un manifiesto de release

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/tasks/builders.py

## Contexto

Un APK, una carpeta web o un ejecutable no dicen de qué versión son. Del lado del VPS, el manifiesto del subproyecto es lo único que los identifica, y el script original lo subía solo en su rama de re-subida: el build normal dejaba al servidor anunciando la versión anterior.

Aparte, qué versión está publicada se tenía como variable de entorno del backend: anunciar un build pedía editar un `.env`, subirlo y reiniciar el servicio — tres pasos que no tienen nada que ver con compilar, y que se saltean solos.

## Decisión

1. Cada publicación sube el artefacto **y** su manifiesto de versión. Van los dos o no va ninguno.
2. Además se escribe `releases/<app>/<plataforma>.json` con app, plataforma, versión, build, nombre del artefacto, `sha256` y fecha, y se sube al lado.
3. Lo escribe **quien construye**, que es el único que sabe la versión en el momento exacto en que deja de ser una intención.
4. Un manifiesto **por plataforma**: el APK y el build web se publican por separado y pueden ir en versiones distintas.
5. No es una fuente de verdad nueva: se deriva del manifiesto del subproyecto al publicar, así que no hay nada que mantener sincronizado a mano.
6. El `sha256` solo va cuando el artefacto es un archivo: un build web es un árbol, y un hash por archivo no es lo que nadie va a verificar.

## Consecuencias

- Una app puede consultar si hay algo nuevo sin que el servidor tenga que saber nada.
- Es la convención de siempre para actualizaciones: el appcast de Sparkle, el `latest.yml` de electron-updater, el `version.json` que Flutter ya emite para web.
- El repo gana una carpeta `releases/` versionada.

## Descartado

- **Anunciar la versión con una variable de entorno del backend.** Exige tres pasos ajenos a compilar, y se saltea en cuanto alguien publica sin acordarse.

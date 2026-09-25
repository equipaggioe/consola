# ADR-0055 · Los íconos salen del logo del repo, los rasteriza Qt y van donde cada app declara

- **Estado:** Propuesta
- **Fecha:** 2026-09-25
- **Alcance:** `core/icons.py`, `core/tasks/images.py::generate_icons`, el eje `apps` de «Generar íconos»; exceptúa `core/tasks/` del punto 2 de [ADR-0005](0005-todo-pasa-por-taskcontext.md) para Qt como biblioteca de imágenes

## Contexto

Seis SPA de cinco repos mostraban el logo de Svelte en la pestaña del navegador, y el panel de vettore llevaba una copia a mano de su logo. El único generador que funcionaba era `vettore/brand/generate.py`: rasterizaba dos SVG con `resvg-py` y corría `flutter_launcher_icons`, solo para Flutter y solo en ese repo. Ese script no sabía nada de vettore salvo dónde estaban los SVG.

Rasterizar pedía elegir una biblioteca. Pillow no lee SVG. `resvg-py` sería una dependencia más. Consola ya trae PySide6, que incluye QtSvg, pero [01](../arquitectura/01_contexto.md) decía que el núcleo no importa PySide6 y [04](../arquitectura/04_conceptos_transversales.md) exceptuaba `core/tasks/`: las dos no coincidían.

Probado el 2026-09-25 con los SVG de vettore a 1024×1024 desde un hilo sin aplicación Qt: `QSvgRenderer` con antialiasing da el mismo PNG que `resvg-py`, con una diferencia media de 0,24 sobre 255 por canal, toda en los bordes del antialiasing.

Una SPA sin `src/lib/assets/favicon.svg` toma su ícono de otro lado: la landing de vettore importa el logo directo. Ofrecerla marcada era fallar en cada corrida hasta desmarcarla, el mismo problema que llevó a [ADR-0054](0054-la-camara-dice-que-sabe-capturar.md).

## Decisión

1. **El repo pone el SVG; el resto es de Consola.** `BRAND_ICON` es el logo y `BRAND_ICON_FOREGROUND` la capa frontal del ícono adaptativo de Android. `generate_icons` reimplementa lo que hacía `generate.py` ([ADR-0001](0001-reimplementar-no-ejecutar-scripts.md)).
2. **Rasteriza QtSvg, solo desde `core/tasks/`.** Ahí se permite `QtGui` y `QtSvg` como biblioteca de imágenes, sin aplicación Qt, sin widgets y sin señales. El resto de `core/` sigue sin importar Qt: lo que no es rasterizar vive en `core/icons.py`.
3. **Cada app dice dónde va su ícono.** En una app Flutter lo dice la sección `flutter_launcher_icons:` del `pubspec.yaml`. Las claves `image_path` llevan el logo y `adaptive_icon_foreground` la capa frontal. Cualquier otra clave que apunte a una imagen corta la corrida. En una SPA, el destino es `src/lib/assets/favicon.svg`, que recibe el logo tal cual.
4. **El eje ofrece solo esas apps.** Es un eje consultado contra el repo (`ICON_APPS`): apps Flutter con esa sección y SPA con ese archivo.

## Consecuencias

- Ninguna dependencia nueva. La contracara: QtSvg implementa SVG Tiny 1.2, así que un logo con filtros, máscaras o CSS saldría distinto que en el navegador, y la corrida no lo detecta.
- Un SVG que no es cuadrado corta la corrida: Qt estira el `viewBox` hasta llenar la imagen.
- Una app que no declara dónde va su ícono no aparece en la lista. Para que aparezca hay que agregarle la sección o el archivo.
- La sección vieja `flutter_icons:` no se lee. `posta/terminal` la usa, y no tiene logo SVG.
- `vettore/brand/generate.py` se borró.

## Descartado

- **`resvg-py`.** Es el renderizador que usaba vettore, pero sería una dependencia más para el mismo resultado medido.
- **Ofrecer toda SPA y toda app Flutter y fallar con las que no toman el ícono.** Obligaba a desmarcar la landing de vettore antes de cada corrida.
- **Declarar las rutas de Flutter en `config.env`.** El pubspec ya dice qué PNG consume el paquete; una segunda copia se desfasa.

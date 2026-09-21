# ADR-0027 · Instalar la máquina virtual, crear el AVD y arrancarlo son tres botones con dos catálogos

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/android.py, core/registry.py, core/catalog.py, core/tasks/emulators.py

## Contexto

Tres scripts arrancaban tres emuladores con tres constantes escritas a mano (`pixel_4`, `pixel_8`, `resizable`). Esas constantes escondían los catálogos reales del SDK: un centenar de perfiles de dispositivo y varios cientos de system images. Un eje `preset` con las tres habría sido una amputación, no una simplificación.

## Decisión

1. Son **tres capacidades**, no una con un eje: instalar la máquina virtual (varios GB, una vez cada varios meses), crear el AVD, y arrancarlo (todos los días). Un paso con catálogo propio de opciones ya no entra en una casilla.
2. Los cuatro botones del grupo son `scope='machine'`: un AVD sirve para cualquier proyecto.
3. La system image se elige **por característica**, no de una lista de cientos: `Facet` declara que el id se compone de versión, variante y arquitectura, y el panel dibuja tres listas cortas que se recortan entre sí. El valor guardado sigue siendo el paquete entero.
4. El recorte es una **cascada**: cada lista se acota con las que están antes, nunca con las de abajo. Cambiar una de arriba corrige las de abajo a su mejor opción disponible; las de arriba no se tocan nunca.
5. «Crear AVD» **no** usa facetas para su lista de imágenes: ahí solo están las ya bajadas, casi siempre una o dos, y partir dos entradas en tres listas haría creer que hay un catálogo detrás.
6. El puerto se elige antes de arrancar (`-port`), así el serial se conoce desde el principio. Una segunda copia del mismo AVD va en `-read-only`.
7. El nombre del AVD se pregunta al correr: dos no pueden llamarse igual, así que un nombre guardado solo sirve la primera vez.

## Consecuencias

- El orden en que se declaran las facetas es el orden en que se deciden, y es parte de la declaración.
- Recortar solo hacia abajo deja combinaciones marcadas que no existen hasta que se corrigen; recortar en las dos direcciones dejaría la primera lista sin salida.
- Los dos catálogos grandes se cachean por un mes; lo instalado y lo creado, por un minuto.

## Descartado

- **Un eje `preset` con las tres constantes.** Esconde los catálogos reales.
- **Una lista con las combinaciones permutadas.** Es la misma pregunta hecha trescientas veces.
- **Recortar también hacia arriba.** Con «Play Store» marcado, las versiones que no lo publican desaparecen y no hay forma de volver a ellas.

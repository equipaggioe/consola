# ADR-0025 · Si el build falla, la versión vuelve a lo que era

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/files.py, core/tasks/builders.py

## Contexto

Los builders suben el número de versión antes de compilar, porque el número tiene que estar adentro del artefacto. Si la compilación falla después, el repo queda marcado con una versión que nunca se publicó, y la siguiente corrida arranca desde ahí.

## Decisión

1. El tramo que toca el manifiesto va dentro de `files.reversible(manifiesto)`: si el bloque falla o se cancela, el archivo vuelve a su contenido anterior.
2. Un solo bump por corrida por más plataformas que se marquen: el APK y la web de la misma corrida son la misma versión.
3. En «Build Vite», cada SPA es reversible **por separado**: si la tercera revienta, las dos que ya se publicaron conservan la versión con la que salieron.
4. En el modo re-subida el bump se **ignora con un aviso**: lo que hay en disco se compiló con la versión que ya tiene el manifiesto, y subirlo cambiado lo anunciaría como otra cosa.

## Consecuencias

- Una corrida fallida no deja rastro en el repo.
- El rollback es del archivo entero, así que un cambio hecho a mano en el manifiesto durante el build también se pierde.

## Descartado

- **Bumpear al final, después de compilar.** El número tiene que estar dentro del artefacto.

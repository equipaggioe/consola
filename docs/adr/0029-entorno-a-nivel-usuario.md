# ADR-0029 · Las variables y el PATH se escriben a nivel usuario, en un bloque delimitado

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/userenv.py, core/tasks/utils.py

## Contexto

Los scripts escribían el entorno con `setx /M` y en `HKLM`: exige una consola elevada, ensucia la máquina entera para una instalación que en la práctica es de un solo usuario, y obliga a correr toda la herramienta como administrador solo para escribir dos variables. Además borraban entradas viejas del PATH línea por línea, lo que dejaba exports duplicados y rutas colgando tras cada reinstalación.

## Decisión

1. El entorno se escribe **a nivel usuario**: `HKCU\Environment` en Windows, un bloque delimitado dentro del perfil del shell en POSIX. Nunca a nivel sistema.
2. El bloque se **reescribe entero** cada vez, y se lee antes de escribir porque es compartido: si Android lo reescribiera sin mirar, borraría lo que dejó Flutter.
3. `path_drop` declara qué entradas viejas se descartan, para poder reinstalar en otro directorio sin que quede apuntando al anterior.
4. Se aplican también al **proceso vivo**, así los indicadores de la barra se ponen en verde al terminar y no al siguiente arranque.
5. En Windows se avisa a las ventanas nuevas del cambio, y se advierte si el PATH del sistema tiene rutas viejas que le ganan a las nuevas: Windows lo pone primero.
6. Lo único que necesita permisos elevados es el driver de aceleración del emulador, y por eso es una atómica aparte, con un solo aviso de UAC.

## Consecuencias

- Consola no necesita correr como administrador.
- En Linux la aceleración no se instala: se verifica y se explica el comando exacto, porque además el cambio de grupo no surte efecto hasta reingresar.
- Un PATH del sistema con rutas viejas gana igual, y lo único que se puede hacer es avisarlo.

## Descartado

- **`setx /M` y `HKLM`.** Exigen elevación para todo y ensucian la máquina entera.
- **Borrar las entradas viejas línea por línea.** Es lo que dejaba duplicados tras cada reinstalación.

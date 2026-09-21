# ADR-0018 · El seguro de los destructivos es por repositorio y por tipo de objetivo, no por botón

- **Estado:** Aceptada, salvo el punto 8, marcado *(propuesta)*: no se confirmó ni se construyó
- **Fecha:** 2026-09-21
- **Alcance:** core/protection.py, ui/guard_dialog.py, ui/tab_panel.py, ui/security_panel.py

## Contexto

El error que importa no es apretar un botón sin querer: es apretarlo **en el repo equivocado**. Y no todos los destructivos pesan igual — vaciar la carpeta de artefactos de un repo de juguete se rehace con un build; borrar la base del VPS de producción, no.

Un seguro por botón tampoco alcanza: un mismo botón puede tocar dos cosas (`clean_vps` borra la base además del servidor) y un mismo botón puede tocar cosas distintas según sus parámetros (`teardown_db` contra `local` no sale de esta máquina).

## Decisión

1. El seguro es **por tipo de objetivo**: `vps`, `db`, `otros_repos`, `publicacion`, `local`, `origin`. Protegidos por defecto todos menos `local` y `origin`.
2. Qué rompe cada acción se declara en una tabla (`RULES`), con objetivos fijos, objetivos que dependen de un eje, y valores con los que la acción no destruye nada.
3. **Un simulacro no dispara nada**, así que no pregunta nada: pedir confirmación ahí sería el ruido que gasta la señal del aviso de verdad.
4. Tres respuestas: `ALLOW` (no rompe nada), `REMIND` (rompe algo que este repo no protege: recordatorio con el repo a la vista, Cancelar o Continuar) y `BLOCK` (toca algo protegido: **no corre, y el aviso no ofrece forma de saltarlo**).
5. El interruptor vive en su **propia sección**, no entre los parámetros: un seguro que se quita en el mismo gesto con el que se aprieta Ejecutar se vuelve parte del gesto.
6. El guard se aplica en el punto único por el que pasan las dos formas de ejecutar.
7. Un objetivo que no figura en el archivo cae en su default: agregar uno nuevo no puede dejar desprotegidos a los repos que ya existen.
8. *(Propuesta, sin construir)* La confirmación escrita de un destructivo debería ser **el nombre del repo** y no una palabra fija: escribir `BORRAR` es correcto en cualquier repo, así que el automatismo siempre acierta y la comprobación no comprueba nada.

## Consecuencias

- Declarar una capacidad destructiva obliga a declarar también qué rompe, o queda sin seguro.
- `purge_emulators` queda fuera: es `scope='machine'`, así que un interruptor por repositorio no tendría a qué repositorio pertenecer. Se queda con su propia confirmación escrita.
- El indicador de la barra de estado lee el panel, la misma fuente que consulta el guard, para que no puedan decir cosas distintas.

## Descartado

- **Un interruptor por botón.** No cubre los botones que tocan dos cosas ni los que cambian de radio según sus parámetros.
- **Ofrecer «continuar igual» en el bloqueo.** Convierte el seguro en un paso más del gesto.

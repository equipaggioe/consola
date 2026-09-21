# Documentación: arquitectura, ADR y planes

Cómo se documenta este repositorio. El método no depende del proyecto: este archivo se puede copiar tal cual a otro repositorio.

## El problema que resuelve

Los planes, las bitácoras, los registros de cambios y las listas de pendientes se acumulan. Cada uno fue cierto el día que se escribió, nadie los actualiza cuando el código cambia y terminan contradiciéndose. Quien los lee, sea una persona o un asistente de IA, no puede saber cuál rige, y decide con información vieja.

La solución es que **cada pregunta tenga un solo lugar donde se responde** y que ese lugar tenga una regla clara sobre cuándo cambia.

## Tres carpetas y nada más

| Carpeta | Pregunta que responde | Cómo cambia |
|---|---|---|
| `arquitectura/` | **Cómo es hoy** el sistema y **qué falta** | Se reescribe en el mismo commit que el código. Nunca describe el pasado ni el futuro |
| `adr/` | **Por qué es así**: qué se decidió, qué se descartó y a qué costo | Solo se agregan registros. Uno viejo no se edita para cambiar de opinión |
| `planes/` | **Cómo se va a construir** algo diseñado y sin terminar | Se borra cuando el trabajo termina |

### Lo que no existe, y dónde va en su lugar

| Documento habitual | Por qué no | Dónde va lo que contenía |
|---|---|---|
| Bitácora, registro de cambios | Repite lo que ya dicen los commits y envejece | Commits. La lección que deja un error va a la arquitectura (regla o riesgo) o a un ADR |
| Carpeta de planes terminados | Describe un estado que ya no existe | Las decisiones a `adr/`, el resultado a `arquitectura/`, y el plan se borra |
| Lista suelta de pendientes | Nadie la limpia y se desincroniza | «Pendientes abiertos» del documento 30 de la pieza |
| Roadmap, lista de ideas | Mezcla lo aprobado con lo imaginado | Lo decidido y sin construir: pendiente en el 30 con su ADR. Las ideas sin aprobar: un archivo en `planes/` con su estado verificado |

## `arquitectura/`

### Estructura

Plantilla **arc42** con diagramas al estilo **C4**, en dos niveles:

| Nivel | Qué responde | C4 | Archivo |
|---|---|---|---|
| Sistema | Qué piezas lo forman, cómo se hablan, qué ve cada una, cómo se despliega | Contexto (1) y contenedores (2) | `00_sistema.md` |
| Contenedor | Cómo está construida cada pieza por dentro | Componentes (3) | Una carpeta por pieza (`servidor/`, `app/`…) |

Cada carpeta de contenedor tiene un `README.md` con su índice y usa la misma numeración:

| # | Contenido |
|---|---|
| 01 | Contexto y alcance de esa pieza |
| 02 | Estrategia y bloques |
| 03 | Ejecución y despliegue |
| 04 | Conceptos transversales (reglas que valen para todo el código de la pieza) |
| 10–19 | Un documento por dominio. Cierra con una sección de lo que comparte con las otras piezas |
| 20 | Referencia de datos (tablas, formatos, claves de almacenamiento) |
| 30 | Riesgos, deuda, hallazgos, pendientes y glosario |

- **Si un dominio existe en varias piezas, lleva el mismo número en todas** (por ejemplo, 11 es mensajería en el servidor y en el cliente). Así se encuentra el otro lado del protocolo sin buscar.
- **Repositorio de una sola pieza:** no hay `00_sistema.md` ni carpetas; los documentos 01–30 van directo en `arquitectura/`.
- El `README.md` de `arquitectura/` lista las series con la fecha en que cada una se verificó contra el código, el orden de lectura y las reglas de mantenimiento.

### El documento 30

Es el único lugar donde vive lo que falta. Secciones, en este orden:

1. **Marcado como provisional en el código:** lo que el propio código declara incompleto.
2. **Hallazgos de la verificación:** defectos encontrados al leer el código. Se escriben **sin confirmar** hasta que alguien los confirme, y no se reportan como hechos.
3. **Pendientes abiertos**, en subgrupos:
   - Reportados en uso (fallos vistos por el usuario, con fecha).
   - Pedidos concretos sin hacer.
   - Decididos y sin construir: tabla con enlace al ADR y, si existe, al plan.
   - Sin decidir.
   - Sin verificar (construido pero nunca probado en condiciones reales).
4. **Deuda estructural declarada.**
5. **Glosario.**

Un pendiente se **borra** de aquí en el commit que lo resuelve. No se tacha ni se marca como hecho.

### Reglas

- Describe **solo lo implementado**. Lo que falta va en el 30; lo que se piensa construir, en `planes/`.
- **Si el documento y el código no coinciden, manda el código.** Se corrige el documento.
- Un cambio que altere un flujo, una tabla, un endpoint, un evento o un formato de intercambio **actualiza en el mismo commit** el documento del dominio en todas las piezas afectadas.
- Una pieza nueva, o una forma nueva de comunicarse entre piezas, actualiza `00_sistema.md`.
- Se cita el código por archivo y símbolo (`servicio.py`, `enviarOrden`), no por número de línea, que envejece con cualquier edición.

## `adr/`

### Reglas

1. **Un ADR por decisión con consecuencias**, no por tarea. Va un ADR si leer el código no basta para saber por qué es así, o si alguien podría «arreglarlo» y romper algo.
2. **Un ADR no se edita para cambiar de opinión.** Una decisión que reemplaza a otra es un ADR nuevo; en el viejo solo cambia el estado a «Reemplazada por ADR-NNNN», con enlace. Nadie lee como vigente una regla que ya no rige.
3. **Estados:** `Propuesta` · `Aceptada` · `En evaluación` · `Reemplazada por ADR-NNNN` · `Descartada`. **El estado es de la decisión, no de la implementación.** «Aceptada y sin construir» es normal: lo que falta construir va en el 30, nunca en el ADR.
4. **`Aceptada` solo si la persona que decide la confirmó explícitamente.** Lo que se eligió al implementar sin preguntar va como `Propuesta`, o como un punto marcado *(propuesta)* dentro de un ADR aceptado. Que algo «siga la misma lógica» que otra decisión confirmada no lo convierte en confirmado.
5. **Numeración correlativa**, `NNNN-titulo-corto.md`. Los números no se reutilizan.
6. El `README.md` de `adr/` es un índice: número, título y nada más.

### Formato

```markdown
# ADR-NNNN · Título que enuncia la decisión, no el tema

- **Estado:** Aceptada
- **Fecha:** AAAA-MM-DD
- **Alcance:** piezas afectadas

## Contexto
Solo si hace falta: qué problema había y qué se sabía. Las decisiones viejas que
esta reemplazó se resumen aquí.

## Decisión
Lista numerada. Cada punto es una regla que se puede verificar en el código.

## Consecuencias
Lo que se gana, lo que cuesta y lo que obliga a hacer en otro lado.

## Descartado
Cada alternativa con el motivo concreto. Evita que alguien vuelva a proponerla
sin saber por qué se rechazó.
```

Título mal: «Geocerca». Título bien: «La geocerca dispara por el estado que encuentra al armar».

## `planes/`

- Existe solo para **trabajo sin terminar cuyo diseño no cabe en un ADR**: pantallas, fases, contratos entre piezas, preguntas abiertas.
- Empieza con un encabezado **Estado (verificado AAAA-MM-DD)** que dice qué está construido y qué falta, comprobado contra el código, y enlaza el ADR y la arquitectura. Si el plan describe algo ya construido y no coincide con el código, el encabezado lo advierte: manda la arquitectura.
- Cada pendiente del 30 que dependa de un plan lo enlaza.
- **Al terminar el trabajo:** las decisiones pasan a `adr/`, el resultado a `arquitectura/`, y el plan se borra en ese commit.
- **Un plan con trabajo pendiente no se borra**, aunque sus decisiones ya estén en un ADR. Un ADR guarda el porqué en pocas líneas; no conserva pantallas, fases ni contratos.

## Comentarios de código

- Un comentario que explica un porqué cita el ADR: `// ADR-0033: una cadena por cola de consumo`.
- **Nunca cita un plan**: los planes se borran y el enlace queda roto.
- No cita secciones de la arquitectura por número de apartado; si hace falta, cita el archivo.

## Ciclo de un cambio

1. Idea o problema. Si el diseño es grande, se escribe un plan en `planes/`.
2. Se confirman las decisiones y se escriben los ADR (`Propuesta` hasta que se confirmen).
3. Se implementa. En el mismo commit se actualiza `arquitectura/` y, si algo queda sin hacer o sin verificar, se anota en el 30.
4. Cuando el plan no tiene nada pendiente, se borra.

## Migrar un repositorio que ya tiene documentación

1. **Inventario:** listar todos los documentos existentes (planes, bitácoras, README, notas).
2. **Verificar contra el código** lo que dice cada uno. No confiar en encabezados como «hecho» o «pendiente»: se escribieron a mitad de camino.
3. Escribir `arquitectura/` a partir del código, no de los documentos viejos.
4. Pasar cada decisión vigente a un ADR. Las reemplazadas se resumen en el «Contexto» o el «Descartado» del ADR vigente, no en archivos aparte.
5. Pasar cada pendiente real al 30 de su pieza.
6. **Antes de borrar, separar los documentos con trabajo sin terminar**: se mueven a `planes/` con su encabezado de estado verificado. Solo se borra lo que ya está terminado o descartado.
7. Reescribir las referencias en los comentarios de código para que citen ADR.
8. Borrar los documentos viejos, comprobar que todos los enlaces de `docs/` resuelven y buscar en el código referencias a los archivos borrados.

Lo borrado sigue en el historial de git (`git show <commit>^:docs/archivo.md`) si hace falta recuperar algo.

## Para asistentes de IA

Agregar al archivo de instrucciones del repositorio (`CLAUDE.md` u otro):

```markdown
## Documentación
- `docs/` sigue `docs/README.md`: `arquitectura/` (cómo es hoy; pendientes en cada documento 30),
  `adr/` (por qué) y `planes/` (solo trabajo sin terminar).
- Antes de afirmar que algo está hecho o pendiente, verificarlo contra el código.
- No crear bitácoras, registros de cambios ni planes terminados.
- Un cambio de comportamiento actualiza `arquitectura/` en el mismo commit; una decisión nueva es un ADR nuevo.
- Solo se escribe `Aceptada` cuando la decisión se confirmó explícitamente.
- Nunca borrar un plan que tenga trabajo pendiente.
```

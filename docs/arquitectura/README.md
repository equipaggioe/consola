# Arquitectura de Consola

Descripción de **lo que está implementado** en este repositorio. La estructura (arc42 y C4, numeración de documentos, contenido del documento 30) y las reglas de mantenimiento están en [`docs/README.md`](../README.md#arquitectura).

Consola es **una sola pieza**: una aplicación de escritorio. No hay `00_sistema.md` ni carpetas por contenedor; los documentos 01–30 van directo acá.

## Serie

| # | Documento | Verificado |
|---|---|---|
| 01 | [Contexto y alcance](01_contexto.md) | 2026-09-21 |
| 02 | [Estrategia y bloques](02_bloques.md) | 2026-09-21 |
| 03 | [Ejecución y despliegue](03_ejecucion_y_despliegue.md) | 2026-09-21 |
| 04 | [Conceptos transversales](04_conceptos_transversales.md) | 2026-09-21 |
| 10 | [Catálogo de capacidades](10_catalogo_de_capacidades.md) | 2026-09-21 |
| 11 | [Ejecución de tareas](11_ejecucion_de_tareas.md) | 2026-09-21 |
| 12 | [Interfaz](12_interfaz.md) | 2026-09-21 |
| 13 | [Configuración y persistencia](13_configuracion_y_persistencia.md) | 2026-09-21 |
| 14 | [Seguro de los destructivos](14_seguro_de_destructivos.md) | 2026-09-21 |
| 15 | [VPS y despliegue](15_vps_y_despliegue.md) | 2026-09-21 |
| 16 | [Base de datos](16_base_de_datos.md) | 2026-09-21 |
| 17 | [Builds y artefactos](17_builds_y_artefactos.md) | 2026-09-21 |
| 18 | [Android y emuladores](18_android_y_emuladores.md) | 2026-09-21 |
| 20 | [Referencia de datos](20_referencia_datos.md) | 2026-09-21 |
| 30 | [Riesgos, deuda y pendientes](30_riesgos_y_pendientes.md) | 2026-09-21 |

## Orden de lectura

1. [01](01_contexto.md) y [02](02_bloques.md) para ubicar las piezas y las tres capas.
2. [04](04_conceptos_transversales.md): las reglas que valen para todo el código.
3. [10](10_catalogo_de_capacidades.md) y [11](11_ejecucion_de_tareas.md): cómo se declara un botón y cómo corre. Cualquier cambio en el catálogo pasa por los dos.
4. El documento del dominio que se va a tocar (13–18).
5. [20](20_referencia_datos.md) si el cambio agrega o mueve una clave de configuración, un archivo o un formato.

## Mantenimiento

- Un cambio de comportamiento actualiza el documento de su dominio **en el mismo commit**.
- Un botón nuevo, un eje nuevo o una clave nueva tocan además [10](10_catalogo_de_capacidades.md) y [20](20_referencia_datos.md).
- Lo que quede sin hacer o sin verificar se anota en [30](30_riesgos_y_pendientes.md), y se borra de ahí en el commit que lo resuelve.
- El código se cita por archivo y símbolo (`core/vps.py`, `write_config`), nunca por número de línea.

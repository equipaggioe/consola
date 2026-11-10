# ADR-0086 · La memoria de Valkey sale de un valor, o de un porcentaje de la RAM del VPS

- **Estado:** Aceptada
- **Fecha:** 2026-11-10
- **Alcance:** core/canone.py, core/settings.py, core/catalog.py, core/tasks/vps_setup.py

## Contexto

`install.py` de canone recibe el `maxmemory` de Valkey y no fija cómo elegirlo: depende de cuánto guarda la app y de qué más corre en la máquina. `VALKEY_MEMORY` era obligatoria y sin valor por defecto.

## Decisión

1. **`VALKEY_MEMORY` manda.** Con valor, es el `maxmemory` que recibe `install.py`.
2. **Vacía, «Configurar VPS» la calcula:** lee `MemTotal` de `/proc/meminfo` del VPS y toma el `VALKEY_PERCENT`, en MB enteros. El log dice el valor y el porcentaje.
3. **`VALKEY_PERCENT` vale 12.5 por defecto**, un octavo. *Valkey setup tips* no fija una parte de la máquina: pide margen para el overhead y advierte que al guardar el `.rdb` puede usar el doble. Con un octavo, llega a un cuarto.
4. **La regla vive en Consola, no en canone:** no vale para todos los casos, como una máquina con varias apps.

## Consecuencias

- «Instalar infraestructura» ya no exige `VALKEY_MEMORY`.
- Un `VALKEY_PERCENT` que no es un número de 0 a 100 corta antes de correr `install.py`.

## Descartado

- **El cálculo en `install.py` de canone, con `--memory` opcional:** un porcentaje fijo no sirve para todas las máquinas, y lo que va en canone vale para todos.
- **Un solo campo que acepte `256mb` o `12%`:** dos formatos para el mismo dato.

# `scripts/` es referencia, no código de la aplicación

Estos 51 archivos son los scripts originales que la Consola reemplazó. Se conservan
como **especificación de comportamiento**: son contra lo que se compara cada
reimplementación, y por eso se leen cuando hay que decidir qué debe hacer un botón.

No forman parte del programa:

- **Nada del código los importa.** La Consola es `core/` (nivel 0) más `ui/`; ningún
  módulo hace `import scripts`.
- **No se ejecutan.** Tampoco desde la Consola: ADR-0001 decidió reimplementar cada
  script como función en vez de lanzarlo como subproceso.
- **No se mantienen.** No se corrigen sus errores ni se actualizan cuando cambia el
  comportamiento de la Consola. Si un script y la Consola no coinciden, manda el
  código de la Consola, y lo que corresponde revisar es si la reimplementación dejó
  algo afuera.

El porqué está en [ADR-0001](../docs/adr/0001-reimplementar-no-ejecutar-scripts.md). Lo
que la Consola hace hoy está en [`docs/arquitectura/`](../docs/arquitectura/).

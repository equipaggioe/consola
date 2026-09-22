# ADR-0043 · Un menú es un grupo sin secciones, y el nombre de un botón es un verbo y su objeto

- **Estado:** Propuesta
- **Fecha:** 2026-09-22
- **Alcance:** core/catalog.py, core/registry.py, ui/menu_bar.py

## Contexto

La barra tenía nueve menús con un segundo nivel dentro (`Capability.section`), dibujado como un ítem deshabilitado que hacía de encabezado. Al contarlo: de las 24 secciones, 11 tenían un solo botón, varias repetían el nombre del menú (`Builders ▸ Build Flutter ▸ Build Flutter`) y `Utils` era un cajón con SDKs de la máquina, DNS, sincronización entre repos y limpieza de artefactos. Tres menús (`VPS · ops`, `VPS · server`, `VPS · setup`) partían la misma máquina por el linaje de los scripts originales, no por lo que uno va a hacer.

Los nombres venían de los scripts: mitad en inglés (`Launchers`, `Builders`, `Build Flutter`, `Health check`, `Promote app`, `Backup DB`, `Teardown DB`) en una interfaz que es en español, y mezclando sustantivos sueltos (`Backend`, `Emulador`) con frases verbales (`Clonar de GitHub`).

## Decisión

1. **Un menú es un grupo y no tiene secciones.** `Capability.section` desaparece del registro. El segundo nivel existía porque los menús eran largos y heterogéneos; con el catálogo reorganizado en ocho grupos por objeto —Ejecutar, Compilar, Repositorio, Base de datos, Despliegue, VPS, Emuladores, SDKs— ninguno pasa de doce ítems.
2. **El orden de declaración en `core/catalog.py` es el orden del menú**, y es el del uso real: preparar, usar, mirar.
3. **La única raya de un menú separa lo que borra.** Es una división de seguridad, no una taxonomía: debajo van las `kind='destructive'`, que el catálogo declara al final de cada grupo.
4. **El nombre de un botón es un verbo en infinitivo y su objeto**, con el verbo salido de un léxico corto (Levantar, Compilar, Crear, Instalar, Configurar, Publicar, Actualizar, Copiar, Igualar, Ver, Listar, Explorar, Abrir, Ejecutar, Probar, Respaldar, Migrar, Quitar, Borrar, Vaciar, Sobrescribir, Reconstruir).
5. **El botón no repite el nombre de su menú**: dentro de «Base de datos» es `Migrar esquema`, no `Migrar DB`.
6. **Sin anglicismo donde hay palabra en español** (build, deploy, seeder, backup, bootstrap, teardown, health check, promote, sync). Se conserva el nombre propio de la herramienta cuando la herramienta *es* la elección: Flutter, Vite, Caddy, coturn, Postgres, GitHub.
7. **Lo que varía entre dos corridas no va en el nombre**: es un eje ([ADR-0004](0004-un-boton-por-capacidad.md)). Por eso `Acción systemd` pasa a ser `Controlar el servicio`.
8. **Un botón destructivo nombra lo que se pierde**, no el mecanismo: `Borrar base y rol`, no `Teardown DB`.

## Consecuencias

- Los ítems de una misma familia quedan pegados porque empiezan por el mismo verbo: el encabezado que los rotulaba ya no hace falta.
- Los `id` no cambian, así que favoritos, parámetros guardados por repo y `composed_of` quedan intactos.
- Cambia dónde se busca por costumbre: «Limpiar artefactos» está ahora en Compilar, los dos `sync` en Repositorio y el DNS en VPS. El buscador (Ctrl+L) amortigua el cambio, pero el primer día se nota.
- «Base de datos» sigue con doce ítems. Es el único menú largo; partirlo en «Base de datos» y «Datos remotos» agregaría un menú a una barra que a 1000 px ya desborda.

## Descartado

- **Submenús.** Un clic de más para llegar a una acción, y la mitad de las secciones tenían un solo ítem.
- **Rayas sin rótulo entre secciones.** Conserva la taxonomía, invisible: si el orden es bueno la raya sobra, y si es malo la raya no lo arregla.

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
3. **Los menús largos se cortan con rayas, nunca con encabezados.** Una raya no tiene nombre, no agrupa y nadie pregunta a qué tramo pertenece un botón: declara un borde, y con eso alcanza para que el ojo vea dónde el menú deja de hablar de una cosa y empieza a hablar de otra. Un encabezado además obligaba a inventarle nombre a los tramos de un solo botón, que eran once de veinticuatro.
4. **Dos fuentes para las rayas, y solo dos.** `Capability.cut` dice que ese botón abre un tramo; y lo que borra (`kind='destructive'`) va al fondo detrás de una raya que no declara nadie, porque es una división de seguridad y no una taxonomía.
5. **El nombre de un botón es un verbo en infinitivo y su objeto**, con el verbo salido de un léxico corto (Levantar, Compilar, Crear, Instalar, Configurar, Publicar, Actualizar, Copiar, Igualar, Ver, Listar, Explorar, Abrir, Ejecutar, Probar, Respaldar, Migrar, Quitar, Borrar, Vaciar, Sobrescribir, Reconstruir).
6. **El botón no repite el nombre de su menú**: dentro de «Base de datos» es `Migrar esquema`, no `Migrar DB`.
7. **Sin anglicismo donde hay palabra en español** (build, deploy, seeder, backup, bootstrap, teardown, health check, promote, sync). Se conserva el nombre propio de la herramienta cuando la herramienta *es* la elección: Flutter, Vite, Caddy, coturn, Postgres, GitHub.
8. **Lo que varía entre dos corridas no va en el nombre**: es un eje ([ADR-0004](0004-un-boton-por-capacidad.md)). Por eso `Acción systemd` pasa a ser `Controlar el servicio`.
9. **Un botón destructivo nombra lo que se pierde**, no el mecanismo: `Borrar base y rol`, no `Teardown DB`.

## Consecuencias

- Los ítems de una misma familia quedan pegados porque empiezan por el mismo verbo, y la raya marca dónde termina la familia: el encabezado que los rotulaba ya no hace falta.
- Los `id` no cambian, así que favoritos, parámetros guardados por repo y `composed_of` quedan intactos.
- Cambia dónde se busca por costumbre: «Limpiar artefactos» está ahora en Compilar, los dos `sync` en Repositorio y el DNS en VPS. El buscador (Ctrl+L) amortigua el cambio, pero el primer día se nota.
- «Base de datos» sigue con doce ítems y «VPS» con once. Son los dos menús largos, y las rayas internas los hacen legibles sin partirlos: un menú más en una barra que a 1000 px ya desborda cuesta más que un menú de doce.

## Descartado

- **Submenús.** Un clic de más para llegar a una acción, y la mitad de las secciones tenían un solo ítem.
- **Un solo tramo por menú, sin ninguna raya interna.** Con doce ítems seguidos —«Base de datos», «VPS»— el verbo compartido no alcanza a marcar el borde, y la lista se lee como un bloque único.
- **`section` con el rótulo apagado.** Es la misma taxonomía, con el costo de nombrarla y sin nada a la vista.

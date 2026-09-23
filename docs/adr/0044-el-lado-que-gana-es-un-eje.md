# ADR-0044 · El menú separa la máquina del código que corre en ella, y el lado que gana un forzado es un eje

- **Estado:** Propuesta
- **Fecha:** 2026-09-23
- **Alcance:** core/catalog.py, core/protection.py, core/tasks/git.py, core/tasks/vps_server.py

## Contexto

El [ADR-0043](0043-un-menu-sin-secciones.md) partió los tres menús de VPS en dos —«VPS» y «Despliegue»— pero repartió los botones por el módulo del que venían, no por lo que hacen. Quedaron en «Despliegue» dos que no son de ningún despliegue: `run_command` corre cualquier comando en la máquina y `ssh_login` abre una terminal en ella. Ninguno sabe que el repo existe.

Aparte, el grupo Repositorio tenía **cuatro** botones de forzado contra GitHub: `git_force_push`, `git_force_reset`, `git_force_vps` y `git_force_origin_from_vps`. Son dos acciones —push y reset— repetidas para dos lados, y entre una y otra lo único que cambia es dónde corre el mismo comando de git. Cuatro nombres de cuatro palabras (`Sobrescribir origin con el VPS`) para describir una matriz de 2×2 que nadie dibujaba.

## Decisión

1. **«VPS» es la máquina; «Despliegue» es el código del repo corriendo en ella.** La prueba: un botón que seguiría teniendo sentido en un VPS sin ningún repo desplegado es de «VPS».
2. **`run_command` y `ssh_login` pasan a «VPS»**, detrás de `health_check`, que abre ahí el tramo de diagnóstico y acceso. `run_command` además pierde el «en el VPS» del nombre, que era el del menú (regla 6 del ADR-0043).
3. **Lo que escribe la configuración de un paquete del VPS se queda en «VPS»**, aunque su contenido salga del repo: `configure_caddy` y `configure_coturn` configuran servicios de la máquina, y separarlos rompería el par que forman.
4. **Los cuatro forzados son dos botones con un eje `side`** (`Esta máquina` / `El VPS`), que es lo que el [ADR-0004](0004-un-boton-por-capacidad.md) ya pedía: lo que varía entre dos corridas es un eje, no otro botón. Los ids `git_force_vps` y `git_force_origin_from_vps` desaparecen.
5. **Las funciones no se duplican.** Con `side='vps'`, `force_push` llama a `force_push_from_vps` y `force_reset` a `sync_repository`, las dos ya escritas en `vps_server.py`, que es donde viven porque son la otra mitad del despliegue.
6. **El objetivo de protección sale del eje.** `git_force_push` reescribe `origin` con cualquier lado —no deja distinta ninguna de las dos máquinas—, mientras que `git_force_reset` descarta commits y archivos del lado elegido, así que su objetivo es `local` o `vps` según `side`. Es el mismo mecanismo que `teardown_db` ya usaba con su ámbito ([ADR-0018](0018-seguro-por-repo-y-objetivo.md)).
7. **`discard_changes` vale para los dos lados.** Un eje que solo hiciera algo con el VPS elegido sería una opción que a veces no hace nada, y eso es exactamente lo que esconde un error.

## Consecuencias

- **El forzado local ahora pregunta** si esta máquina tiene cambios sin commitear. Antes los descartaba sin avisar, que era la asimetría con el lado del VPS: el mismo botón, dos criterios.
- **Se pierden los parámetros guardados y los favoritos de los dos ids que desaparecen.** No hay migración: los dos botones nuevos arrancan con su eje en el valor por omisión.
- El grupo «VPS» pasa a catorce ítems y «Despliegue» baja a seis. Es el menú más largo de la barra, con cuatro tramos separados por rayas; parte de lo que lo hace largo es que la mitad son cosas que se corren una sola vez por máquina.
- «Force push» y «Force reset» ya no dicen en su nombre contra qué máquina corren. El eje está a la vista en el panel apenas se abre la pestaña, y es el primero de los dos.

## Descartado

- **Mover `configure_caddy` a «Despliegue»** porque su contenido sale de `PUBLIC_ROUTES`, que es un dato del repo. Con ese criterio también se mudaría `configure_coturn`, y «VPS» se quedaría sin el paso que hace que a la máquina se llegue desde internet.
- **Un solo botón de forzado con un eje `push`/`reset`.** Son las dos acciones con consecuencias opuestas —una pierde lo de allá, la otra lo de acá— y meterlas en un eje deja la decisión más peligrosa como un radio más del formulario.
- **Dejar `discard_changes` solo en el lado del VPS**, con el eje ignorado en local. Ver el punto 7.

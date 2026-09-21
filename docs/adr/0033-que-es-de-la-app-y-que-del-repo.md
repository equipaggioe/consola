# ADR-0033 · Las favoritas y las secciones son de la aplicación; las pestañas abiertas son del repo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** ui/favorites.py, ui/section_visibility.py, ui/params_store.py, ui/project_store.py

## Contexto

Tres preferencias de la interfaz parecen del mismo tipo y no lo son: qué acciones son favoritas, qué secciones de la columna derecha se ven, y qué pestañas de acción quedaron abiertas.

## Decisión

1. **Favoritas**: de la aplicación. Una acción existe igual para todos los repos, y marcarla es una preferencia de uso. Van a `QSettings`.
2. **Secciones visibles**: de la aplicación. Se elige desde un repo y vale para todos, así que al cambiarla se avisa a los demás espacios de trabajo abiertos.
3. **Pestañas abiertas**: del **repo**. Qué botones dejaste a mano es una decisión sobre ese repo, y va a su `params.json` bajo `@tabs`.
4. Favorita se puede marcar desde tres superficies —el filete de la fila del buscador, la estrella de la cabecera de parámetros y el podado de los menús—: quien marca lo guarda, y desde la ventana se avisa al resto.
5. «Solo favoritos» poda los menús pero **no** el buscador: buscar es ir por algo puntual, y esconder justo lo que se busca por no estar marcado sería un chiste cruel.

## Consecuencias

- La lista de pestañas guardada se reescribe ya limpia al restaurar: si el catálogo perdió un botón, su id no vuelve a arrastrarse.
- Tres superficies para el mismo conjunto obligan a una señal que las sincronice.

## Descartado

- **Favoritas por repo.** La acción es la misma en todos; marcarla es una preferencia de uso, no del proyecto.
- **Pestañas abiertas en `QSettings`.** Son de ese repo, y al quitarlo dejarían basura global.

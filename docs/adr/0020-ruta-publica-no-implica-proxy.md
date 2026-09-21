# ADR-0020 · Declarar una ruta pública no significa que haya un reverse proxy delante

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/envfile.py, core/tasks/builders.py

## Contexto

«¿Hay tabla de rutas?» se estaba usando para contestar dos preguntas distintas, y de ahí salía que un repo sin proxy tampoco tuviera rutas públicas. El resultado: sus builds salían apuntando a la raíz, y su backend escuchaba en loopback sin que nadie lo alcanzara — el único repo con proxy decidiendo por todos los demás.

## Decisión

1. **`declares_routes`** — ¿el repo declaró su tabla? Es lo que decide si hay una ruta pública que escribirle al build.
2. **`uses_proxy`** — ¿hay alguna regla `proxy`? Una regla `proxy` es, por definición, alguien adelante que reenvía al backend. Es lo que decide dónde escucha el backend: con proxy, loopback; sin nadie adelante, en todas las interfaces.
3. `spa_base` devuelve tres cosas distintas, y las tres importan: `None` si el repo no declaró tabla (no hay nada que escribirle), `''` si la SPA cuelga de la raíz, y el prefijo si tiene regla propia.
4. El default de `BACKEND_HOST` se deriva de `uses_proxy`, no es fijo.
5. En un repo sin tabla, Consola **compila y no le deja nada adentro**: no escribe `base.generated.js` ni comprueba el HTML.

## Consecuencias

- Un repo que sirve sus propias estáticas puede declarar sus rutas públicas igual, y sigue escuchando afuera.
- `None` y `''` son valores distintos y hay que tratarlos distinto en cada llamador.

## Descartado

- **Tratar «hay tabla» como «hay proxy».** Dejaba al repo sin proxy sin dónde declarar su ruta pública, y a su backend sin contestarle a nadie.

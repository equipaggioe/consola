# ADR-0058 · La interfaz muestra el logo del repo, y un repo sin logo lleva la marca de Equipaggio

- **Estado:** Propuesta
- **Fecha:** 2026-09-26
- **Alcance:** `ui/repo_logo.py`, la pestaña del repo, la cabecera de la columna derecha, la bienvenida y la tarjeta del aviso del seguro; quita `Project.icon`

## Contexto

Cada repo llevaba un emoji en `Project.icon`, guardado en `projects/list` de QSettings. Era 📁 para todos: `open_path` lo fijaba al añadir el repo y no había forma de cambiarlo. Aparecía en la cabecera de la columna derecha, en la bienvenida y en el aviso del seguro, y no distinguía un repo de otro. La pestaña del repo no llevaba nada.

El logo del repo ya existe en la configuración: `BRAND_ICON`, el SVG del que salen los íconos de sus apps y de su ejecutable ([ADR-0055](0055-los-iconos-salen-del-logo-y-los-rasteriza-qt.md)). De los ocho repos, seis lo declaran; consola y posta no.

## Decisión

1. **El logo de un repo en la interfaz es su `BRAND_ICON`**, leído de `.consola/config.env`. No se busca en otro lado (`favicon.svg`, pubspec, `assets/`): sería otra fuente para el mismo dato.
2. **Un repo sin `BRAND_ICON` lleva la marca de Equipaggio**, `ui/assets/equipaggio.png`.
3. **Un `BRAND_ICON` que no se puede leer se muestra como ⚠**, con el error en el tooltip. La marca de Equipaggio diría que no hay logo, cuando lo que hay es una ruta rota.
4. **Va en la pestaña del repo, a la izquierda del nombre**; a la derecha está la ×, y el logo pegado a ella se leería como otro botón. También en la cabecera de la columna derecha cuando no hay acción abierta, en la bienvenida y en la tarjeta del aviso del seguro.
5. **Se relee al guardar o recargar `config.env`**, desde Configuración del repo.

## Consecuencias

- `Project` pierde `icon`, y `projects/list` guarda solo ruta y nombre.
- Declarar `BRAND_ICON` cambia lo que se ve en la barra de pestañas, no solo lo que genera «Generar íconos».
- La marca de Equipaggio existe solo como PNG de 400 × 400; se dibuja escalada, y no hay SVG de la marca.

## Descartado

- **Dejar el emoji y permitir elegirlo.** Sería un segundo ícono del repo, distinto del de sus apps.
- **El rombo de Consola para los repos sin logo.** Es la marca de la aplicación, que ya está en la barra de título.

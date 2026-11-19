# ADR-0090 · El código sigue el árbol de `qt.md` de canone

- **Estado:** Aceptada. El usuario eligió lo recomendado en cada punto: `services/` para lo que no es
  interfaz, `api/` para todo HTTP, `assets/` para lo que no es código, `palettes.py` en `services/`,
  las partes dentro de `theme.py` y una clase pública por módulo (2026-11-18)
- **Fecha:** 2026-11-18
- **Alcance:** `desktop/src/app/`

## Contexto

`qt.md` de canone dejó de estar en desarrollo, y `verificar.py` comprueba su árbol (ADR-0186,
ADR-0188 y ADR-0189 de canone). Consola tenía `core/`, `ui/` y `camera/`. Los ADR anteriores a
este nombran esas rutas; donde quedó cada una está en el punto 1.

## Decisión

1. Las rutas cambian así:

   | Antes | Ahora |
   |---|---|
   | `core/` | `services/` |
   | `core/http.py` | `api/http.py` |
   | Las llamadas a Cloudflare, al índice de Flutter, a la página de Android Studio y a la IP pública, en `core/tasks/utils.py` | `api/cloudflare.py`, `api/flutter.py`, `api/android_studio.py` y `api/ip.py` |
   | `camera/`, `ui/assets/` y `core/shots_presets.json` | `assets/` |
   | `ui/favorites.py`, `section_visibility.py`, `params_store.py`, `project_store.py`, `readiness.py`, `task_runner.py`, `db_worker.py` y `palettes.py` | `services/` |
   | `RepoLogo` y `AxesLoader` | `services/repo_logo.py` y `services/axes_loader.py` |
   | `ui/parts.py` | La sección «The parts of the window» de `theme.py` |
   | `ui/main_window.py` | `windows/main_window.py` |
   | `ui/guard_dialog.py` | `dialogs/guard_dialog.py`, `blocked_dialog.py` y `reminder_dialog.py` |
   | `RowsModel` | `models/rows_model.py` |
   | Los demás módulos de `ui/` y `ui/widgets/` | `widgets/`, uno por clase pública |

2. `services/` importa QtCore para sus hilos y para `QSettings`, y QtGui y QtSvg como biblioteca de
   imágenes, pero no QtWidgets ni QtNetwork.
3. Las partes de la ventana van en `theme.py`, junto a los colores neutros: es el único lugar donde
   se cambia qué color pinta cada parte. `theme.py` nombra `Palette` solo en sus anotaciones,
   porque `services/palettes.py` importa `theme.py`.
4. Una clase que solo ayuda a la pública de su módulo es privada y va con ella, como `_SubTabButton`
   en `widgets/tab_panel.py`.

## Consecuencias

- `theme.py` tiene unas 500 líneas.
- `GuardDialog` y `join_words` pasan a ser públicos: los usan los dos avisos, cada uno en su módulo.

## Descartado

- **Conservar `core/` y `ui/`:** `verificar.py` falla con ellos.
- **`parts.py` en `services/`:** son colores de la interfaz, y quedarían lejos de los neutros.

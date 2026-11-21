# ADR-0094 · Cada parte da sus colores en una `QPalette`, y `Style` dibuja lo demás

- **Estado:** Aceptada. El usuario la confirmó el 2026-11-20 (pregunta 18 del plan
  `cumplir_canone.md`)
- **Fecha:** 2026-11-21
- **Alcance:** `desktop/src/app/theme.py`, `desktop/src/app/widgets/`, `desktop/src/app/dialogs/`,
  `desktop/src/app/windows/`

## Contexto

`qt.md` de canone pide que la app use Fusion a través de `Style`, un `QProxyStyle`, sin ninguna
hoja de estilo, y que `tests/test_theme.py` lo compruebe. Consola pintaba sus 39 partes (`Look` en
`theme.py`) con hojas de estilo: 169 `setStyleSheet` en 27 archivos, contados el 2026-11-20. Cada
espacio de trabajo tiene su propio tema ([ADR-0092](0092-el-tema-de-color-se-elige-por-repo-y-viaja-con-el.md)),
así que una sola paleta de la app no alcanza.

## Decisión

1. **Cada espacio de trabajo aplica la `palette()` de su tema**, generada en `colors.py`.
2. **Cada parte da su fondo y su texto como una `QPalette`, que su widget aplica con
   `setPalette()`**; los hijos la heredan.
3. **Lo que una paleta no expresa, como los bordes y el foco, lo dibuja `Style`.**
4. **Un botón con relleno de acento lleva la propiedad `variant` en `primary`**, como pide
   `qt.md`.
5. **La tabla de partes de `theme.py` sigue siendo el único lugar donde se cambia un tono.**

## Consecuencias

- Sale la hoja de estilo que `MainWindow._apply_window_border` pone en el `centralWidget`, que se
  lleva 0,63 de los 0,7 s de cambiar de pestaña de repo.

## Descartado

- **Hojas de estilo locales.** `qt.md` no deja ninguna, y Qt pide no cambiar de tema con ellas.
- **Una sola paleta en la `QApplication`.** Dos espacios de trabajo vivos tienen temas distintos.

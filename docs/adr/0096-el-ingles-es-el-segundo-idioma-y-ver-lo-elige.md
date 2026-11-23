# ADR-0096 · El inglés es el segundo idioma, y Ver lo elige

- **Estado:** Aceptada en parte. El usuario pidió el inglés el 2026-11-22 (punto 1). Los puntos 2
  a 5 se eligieron al implementar y esperan su revisión en la app
- **Fecha:** 2026-11-22
- **Alcance:** `desktop/src/app/translations/`, `desktop/src/app/widgets/action_menu_bar.py`,
  `desktop/tests/`

## Contexto

El [ADR-0091](0091-los-textos-se-escriben-en-espanol-y-linguist-los-traduce.md) dejó el español
como texto fuente, solo `es.ts`, y ningún selector mientras hubiera un solo idioma. `qt.md` de canone
pide guardar la elección del usuario en `QSettings`, bajo `language.KEY`, y aplicarla con
`language.install()` antes de crear un widget. No dice dónde se elige ni cuándo se aplica.

`services/language.py` es una copia sin editar de la plantilla de canone, y `verificar.py` la
compara: lo que el selector necesita va fuera de ese módulo.

## Decisión

1. `translations/en.ts` traduce al inglés los 1473 textos.
2. Ver tiene «Idioma», con «El del sistema» y un idioma por traducción. Cada idioma va con su nombre
   en ese idioma, «English» y «Español»: quien no lee el idioma de la ventana encuentra el suyo. Los
   nombres salen de `LANGUAGE_NAMES`, en `action_menu_bar.py`, y no de
   `QLocale.nativeLanguageName()`, que nombra también la región por omisión: «español de España» y
   «American English».
3. La elección vale desde la próxima vez que se abre Consola, y un mensaje lo dice: cada widget pone
   sus textos al construirse, después de `install()`. «El del sistema» borra la clave.
4. `tests/test_language.py` falla si un texto de `en.ts` no tiene traducción o pierde un `{…}`, y
   el `screen` de `tests/conftest.py` abre la ventana una vez en cada idioma, así que
   `test_accessibility.py` mide los dos.
5. Cinco textos nombraban acciones que ya no existen («Instalar maquina», «Entorno de desarrollo»,
   «Herramientas Android» y «SDK Flutter»): ahora nombran las del catálogo.

## Consecuencias

- Un texto nuevo necesita su inglés: sin él, `test_language.py` falla.
- Un tercer idioma agrega su `.ts`, su nombre en `LANGUAGE_NAMES` y su `qtbase_<locale>.qm` en
  `resources.qrc`.
- Cambiar de idioma necesita volver a abrir Consola.
- La prueba de accesibilidad tarda el doble.

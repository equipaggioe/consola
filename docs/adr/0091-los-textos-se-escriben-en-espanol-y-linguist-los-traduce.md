# ADR-0091 · Los textos de la interfaz se escriben en español y Qt Linguist los traduce

- **Estado:** Aceptada. El usuario confirmó los puntos 1, 2 y 3 el 2026-11-19, y los puntos 4 a 9, que
  se eligieron al implementar, el 2026-11-21. Los puntos 4, 5 y 6 y la extracción sin
  `rc_resources.py` los reemplaza el ADR-0197 de canone, que los lleva a `qt.md` y hace canónico
  `services/language.py`
- **Fecha:** 2026-11-19
- **Alcance:** `desktop/src/app/`

## Contexto

`qt.md` de canone pide Qt Linguist, el idioma guardado en `QSettings` y aplicado con
`QLocale.setDefault()` y un `QTranslator`, y `QLocale.system()` hasta que el usuario elige. No dice
en qué idioma va el texto fuente. En Flutter, la plantilla de traducciones es la del idioma base,
`app_es.arb`. Consola tenía unos 1450 textos sin marcar, la mitad declarados al importar: el
catálogo, las claves de configuración, los objetivos del seguro y los textos largos de cada
comando.

Se comprobó con PySide6 6.12.0:

- `pyside6-lupdate` reconoce `translate(...)` y `QT_TRANSLATE_NOOP(...)` por el nombre de la
  función, venga de donde venga.
- `self.tr()` busca con el nombre de la clase del objeto: un método heredado no encuentra el
  contexto donde lupdate guardó el texto.
- En los stubs de PySide6, `QT_TRANSLATE_NOOP` devuelve `object`.
- `pyside6-lupdate -extensions py src/app` termina con un fallo de acceso a memoria
  (`3221225477`) si `src/app/rc_resources.py` existe.

## Decisión

1. El texto fuente de `QCoreApplication.translate` es el español, el idioma base.
2. Consola trae solo `translations/es.ts`. Otro idioma se agrega con su `.ts`.
3. Mientras haya un solo idioma no hay selector: rige `QLocale.system()`, como pide `qt.md` hasta
   que el usuario elige. El selector y su clave de `QSettings` llegan con el segundo idioma.
4. El idioma es el primero de `QLocale.system().uiLanguages()` que tiene traducción,
   comparado sin mayúsculas y recortando subetiquetas (`es-AR` encuentra `es`), o el base
   (`services/language.py::resolve`).
5. Todo texto se traduce con `QCoreApplication.translate`, con la clase como contexto
   o, fuera de una clase, el módulo. Los valores van como `{0}` y `.format()`, nunca en un
   f-string.
6. Lo que se arma al importar se marca con `QT_TRANSLATE_NOOP` de
   `services/language.py`, que devuelve `str`, y se traduce donde se muestra. El catálogo marca
   todas sus declaraciones y `load_catalog()` las traduce al terminar, salvo el grupo.
7. Un texto que también es clave, como el grupo de una capacidad o de una clave de
   configuración, se guarda sin traducir y se traduce al mostrarse.
8. No se traducen los comentarios que `envfile.py` escribe en `config.env`, porque el
   archivo es del repo, ni los mensajes en inglés de los errores de programación.
9. Un plural se elige en el código con dos textos. Con `%n` hace falta una traducción
   que elija la forma, y el idioma base no la tiene.

## Consecuencias

- Agregar un idioma es crear su `.ts` con `pyside6-lupdate`, traducirlo, listar su `.qm` y su
  `qtbase_<locale>.qm` en `resources.qrc`, y agregar el selector.
- Hasta entonces, `es.qm` sale vacío de `pyside6-lrelease`: todas las entradas quedan sin
  terminar, y `translate` devuelve el texto fuente.
- `tests/test_language.py` instala un traductor que marca cada texto y comprueba que el catálogo,
  los textos largos y las claves salen traducidos, y que cada texto del catálogo está en `es.ts`.
- `es.ts` lleva las líneas de cada texto, y cambia con cualquier edición de esas líneas.
- `pyside6-lupdate` se corre sin `rc_resources.py`: con él, falla.

## Descartado

- **El texto fuente en inglés:** obligaba a reescribir los 1450 textos y a traducirlos todos al
  español en el mismo cambio.
- **`self.tr()`:** en un método heredado busca con el contexto de la subclase y no encuentra el
  texto.
- **El `QT_TRANSLATE_NOOP` de PySide6:** devuelve `object` en sus stubs, y Pyrefly rechaza pasarlo
  como `str`.
- **Instalar el traductor antes de importar los módulos:** dependería del orden de los imports de
  `main.py`, y las pruebas importan los módulos sin `main.py`.

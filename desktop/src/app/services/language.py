"""The language of the interface.

The texts are written in Spanish, the base language, and Qt Linguist
translates them with `translations/<tag>.qm`, compiled into the
resources with Qt's own `qtbase_<tag>.qm`. The user does not choose
yet: the language is the first of the system's that has a translation,
or the base one.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, QDir, QLocale, QTranslator

BASE = "es"
TRANSLATIONS = ":/translations"


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802
    """Mark a text that is translated where it is shown.

    A declaration evaluated on import is built before the translator
    exists: it keeps the source text, and `pyside6-lupdate` finds it by
    this name. Qt's own returns `object` in PySide6's stubs.
    """
    del context
    return text


def offered() -> list[str]:
    """Return the tags of the app's compiled translations."""
    names = QDir(TRANSLATIONS).entryList(["*.qm"], QDir.Filter.Files)
    return sorted(n.removesuffix(".qm") for n in names if not n.startswith("qtbase_"))


def resolve(preferred: Sequence[str], available: Sequence[str]) -> str:
    """Return the first preferred tag with a translation, or the base.

    A tag also matches by its prefix (`es-AR` finds `es`), and tags
    compare without case (RFC 5646 §2.1.1).
    """
    by_lower = {tag.lower(): tag for tag in available}
    for tag in preferred:
        parts = tag.replace("_", "-").split("-")
        while parts:
            found = by_lower.get("-".join(parts).lower())
            if found is not None:
                return found
            parts.pop()
    return BASE


def install(app: QCoreApplication) -> str:
    """Apply the language to the app and return its tag.

    The default `QLocale` formats dates and numbers in it, and two
    translators, the app's and Qt's, translate the texts.
    """
    tag = resolve(QLocale.system().uiLanguages(), offered())
    QLocale.setDefault(QLocale(tag))
    for name in (tag, f"qtbase_{tag.replace('-', '_')}"):
        translator = QTranslator(app)
        path = f"{TRANSLATIONS}/{name}.qm"
        if not translator.load(path):
            raise RuntimeError(f"Qt could not load {path}")
        app.installTranslator(translator)
    return tag

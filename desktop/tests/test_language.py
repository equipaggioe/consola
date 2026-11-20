"""The interface language: which applies, and what gets translated."""

from collections.abc import Iterator
from pathlib import Path
from typing import override
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QTranslator
from pytestqt.qtbot import QtBot

# The translations are in the compiled resources.
import app.rc_resources  # noqa: F401
from app.services import catalog, command_docs, language, settings
from app.services.registry import Registry

TS = Path(language.__file__).parents[1] / "translations" / "es.ts"


class _Marking(QTranslator):
    """Translate every text to itself between marks."""

    @override
    def translate(
        self, context: str, source: str, disambiguation: str | None = None, n: int = -1
    ) -> str:
        return f"⟦{source}⟧" if source else ""


@pytest.fixture
def marking(qtbot: QtBot) -> Iterator[None]:
    """Install the marking translator while the test runs."""
    del qtbot
    translator = _Marking()
    QCoreApplication.installTranslator(translator)
    yield
    QCoreApplication.removeTranslator(translator)


@pytest.mark.parametrize(
    ("preferred", "chosen"),
    [
        (["es-AR", "en-US"], "es"),
        (["ES"], "es"),
        (["en-US", "fr"], "es"),
        ([], "es"),
    ],
)
def test_the_language_is_the_first_with_a_translation(preferred: list[str], chosen: str) -> None:
    """The first system language with a translation, or the base."""
    assert language.resolve(preferred, ["es"]) == chosen


def test_the_saved_choice_goes_before_the_system() -> None:
    """The saved choice goes first: it wins if it has a translation."""
    assert language.resolve(["pt", "es-AR"], ["es", "pt"]) == "pt"


def test_a_longer_tag_wins_over_its_prefix() -> None:
    """`pt-BR` finds `pt-BR` before `pt`."""
    assert language.resolve(["pt-BR"], ["pt", "pt-BR"]) == "pt-BR"


def test_the_resources_offer_the_base_language() -> None:
    """The compiled resources carry the base language's translation."""
    assert language.offered() == ["es"]


def test_install_applies_the_language_and_both_translators(qtbot: QtBot) -> None:
    """`install` sets the default locale and loads both translators."""
    del qtbot
    app = QCoreApplication.instance()
    assert app is not None
    before = QLocale()
    try:
        assert language.install(app) == "es"
        assert QLocale().bcp47Name() == "es"
        assert len(app.findChildren(QTranslator)) == 2
    finally:
        for translator in app.findChildren(QTranslator):
            QCoreApplication.removeTranslator(translator)
            translator.deleteLater()
        QLocale.setDefault(before)


def test_the_catalog_translates_its_declarations(
    marking: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Names, descriptions, axes and steps translate, but not the group.

    The group keys the menu's order and icons: the menu translates it
    when showing it.
    """
    del marking
    fresh = Registry()
    monkeypatch.setattr(catalog, "registry", fresh)
    catalog.load_catalog()
    for cap in fresh.get_all():
        assert cap.name.startswith("⟦"), cap.id
        assert not cap.description or cap.description.startswith("⟦"), cap.id
        assert not cap.group.startswith("⟦"), cap.id
        for axis in cap.axes:
            assert not axis.label or axis.label.startswith("⟦"), (cap.id, axis.name)
            for label in axis.labels.values():
                assert label.startswith("⟦"), (cap.id, axis.name, label)
            for facet in axis.facets:
                assert facet.label.startswith("⟦"), (cap.id, axis.name, facet.name)
        for step in cap.steps:
            assert step.label.startswith("⟦"), (cap.id, step.id)


def test_the_long_texts_are_translated(marking: None) -> None:
    """A command's long text comes translated."""
    del marking
    doc = command_docs.get("backend")
    assert doc is not None
    assert doc.summary.startswith("⟦")
    assert all(step.startswith("⟦") for step in doc.steps)


def test_a_key_reads_translated(marking: None) -> None:
    """A configuration key reads with its translated label and hint."""
    del marking
    setting = settings.get_setting("API_URL")
    assert setting is not None
    assert setting.display.startswith("⟦")


def _extracted(context: str) -> set[str]:
    # The source texts `translations/es.ts` holds for a context.
    tree = ElementTree.parse(TS)
    return {
        source.text or ""
        for node in tree.getroot().iter("context")
        if node.findtext("name") == context
        for source in node.iter("source")
    }


def test_the_catalog_texts_are_in_the_translations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every text the catalog declares is in `es.ts`.

    A text without its mark stays out of the translations, and nothing
    else says so.
    """
    fresh = Registry()
    monkeypatch.setattr(catalog, "registry", fresh)
    catalog.load_catalog()
    texts = set()
    for cap in fresh.get_all():
        texts |= {cap.name, cap.description, cap.group}
        texts |= {step.label for step in cap.steps}
        for axis in cap.axes:
            texts |= {axis.label, *axis.labels.values()}
            texts |= {facet.label for facet in axis.facets}
    texts.discard("")
    assert texts - _extracted("catalog") == set()

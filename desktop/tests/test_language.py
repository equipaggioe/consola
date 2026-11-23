"""The interface language: which applies, and what gets translated."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import override
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

# The translations are in the compiled resources.
import app.rc_resources  # noqa: F401
from app.services import catalog, command_docs, language, settings
from app.services.registry import Registry
from app.widgets.action_menu_bar import (
    LANGUAGE_NAMES,
    ActionMenuBar,
    choose_language,
    chosen_language,
)

TRANSLATIONS = Path(language.__file__).parents[1] / "translations"
TS = TRANSLATIONS / "es.ts"


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


@pytest.fixture
def stored(tmp_path: Path) -> Iterator[None]:
    """Keep `QSettings` in a temporary folder while the test runs."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    yield
    QSettings().clear()


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


def test_the_resources_offer_every_translation() -> None:
    """The compiled resources carry the base language and English."""
    assert language.offered() == ["en", "es"]


@pytest.mark.parametrize("tag", ["en", "es"])
def test_install_applies_the_language_and_both_translators(
    qtbot: QtBot, stored: None, tag: str
) -> None:
    """`install` sets the chosen locale and loads both translators."""
    del qtbot, stored
    app = QCoreApplication.instance()
    assert app is not None
    before = QLocale()
    choose_language(tag)
    # An earlier test's wait for `deleteLater` until the loop runs.
    earlier = set(app.findChildren(QTranslator))
    try:
        assert language.install(app) == tag
        assert QLocale().bcp47Name() == tag
        assert len(set(app.findChildren(QTranslator)) - earlier) == 2
        assert QCoreApplication.translate("ActionMenuBar", "Ver") == (
            "View" if tag == "en" else "Ver"
        )
    finally:
        for translator in set(app.findChildren(QTranslator)) - earlier:
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


def test_the_choice_is_saved_and_forgotten(stored: None) -> None:
    """A tag is saved under `KEY`, and "" goes back to the system's."""
    del stored
    choose_language("en")
    assert chosen_language() == "en"
    choose_language("")
    assert chosen_language() == ""
    assert not QSettings().contains(language.KEY)


def test_each_language_is_named_in_itself() -> None:
    """«English» and «Español», whatever language is on."""
    assert LANGUAGE_NAMES == {"en": "English", "es": "Español"}
    assert set(LANGUAGE_NAMES) == set(language.offered())


def test_the_view_menu_chooses_the_language(qtbot: QtBot, stored: None) -> None:
    """«Idioma» lists the system's and each translation, and saves."""
    del stored
    bar = ActionMenuBar()
    qtbot.addWidget(bar)
    assert list(bar.language_actions) == ["", "en", "es"]
    assert bar.language_actions[""].isChecked()
    bar.language_actions["en"].trigger()
    assert chosen_language() == "en"
    assert bar.language_actions["en"].isChecked()
    for dialog in bar.window().findChildren(QMessageBox):
        dialog.close()


def test_every_text_has_its_english(qtbot: QtBot) -> None:
    """`en.ts` translates every text, with the same `{…}` fields.

    A field lost in the translation raises on `.format()` only when that
    text shows.
    """
    del qtbot
    fields = re.compile(r"\{[^{}]*\}")
    tree = ElementTree.parse(TRANSLATIONS / "en.ts")
    assert tree.getroot().get("language") == "en"
    for message in tree.getroot().iter("message"):
        source = message.findtext("source") or ""
        translation = message.find("translation")
        assert translation is not None, source
        assert translation.get("type") is None, source
        assert translation.text, source
        assert sorted(fields.findall(source)) == sorted(fields.findall(translation.text)), source

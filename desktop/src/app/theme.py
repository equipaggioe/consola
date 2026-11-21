"""The style, the palette, the sizes and the parts of the app.

The colors come from `colors.py`, generated from `brand/tokens/`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleHintReturn,
    QStyleOption,
    QStyleOptionComplex,
    QStyleOptionMenuItem,
    QStyleOptionSlider,
    QToolTip,
    QWidget,
)

from app.colors import INITIAL, palette

if TYPE_CHECKING:
    # Only for the annotations: `services/palettes.py` imports this
    # module.
    from app.services.palettes import Palette

# The scheme of the theme without a repo. What is the same in every
# theme, the surfaces, the text and the states, is read from it.
SCHEME = INITIAL.dark

# The opacities of the state layers of Material.
HOVER = 0.08
DISABLED = 0.38


def blend(over: str, base: str, opacity: float) -> str:
    """Return `over` laid on `base` at that opacity, as #rrggbb.

    It is how Material paints a state layer: the color of the content,
    faint, on its container.
    """
    mixed = (
        round(int(over[i : i + 2], 16) * opacity + int(base[i : i + 2], 16) * (1 - opacity))
        for i in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


class Colors:
    """The roles that are the same in every theme.

    By the names the style sheets of the widgets still give them.
    """

    INK = SCHEME["on_primary"]
    CHROME = SCHEME["primary_container"]
    BG = SCHEME["surface"]
    PANEL = SCHEME["surface_container_low"]
    SURFACE = SCHEME["surface_container"]
    SURFACE_HOVER = SCHEME["surface_container_high"]
    SURFACE_ALT = SCHEME["surface_container_highest"]
    BORDER = SCHEME["outline_variant"]
    BORDER_LIGHT = SCHEME["outline"]
    TEXT = SCHEME["on_surface"]
    TEXT_LABEL = SCHEME["on_surface"]
    TEXT_DIM = SCHEME["on_surface_variant"]
    TEXT_MUTED = SCHEME["on_surface_variant"]
    # Disabled text, on the body of a section.
    TEXT_DISABLED = blend(SCHEME["on_surface"], SCHEME["surface_container_low"], DISABLED)
    ACCENT = SCHEME["primary"]
    ACCENT_PURPLE = SCHEME["tertiary"]
    SUCCESS = SCHEME["success"]
    WARNING = SCHEME["warning"]
    ERROR = SCHEME["error"]
    ON_ERROR = SCHEME["on_error"]
    INACTIVE = SCHEME["outline"]


class Fonts:
    """The font families and sizes."""

    FAMILY = '"Inter", "Segoe UI", "Helvetica Neue", sans-serif'
    MONO = '"Cascadia Code", "Fira Code", "Consolas", monospace'
    SIZE_XS = 12
    SIZE_SM = 13
    SIZE_BASE = 15
    SIZE_LG = 17
    SIZE_XL = 21
    SIZE_XXL = 30
    SIZE_MONO = 15


class Spacing:
    """The spacing steps."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    """The corner radii."""

    SM = 4
    MD = 8
    LG = 12
    XL = 16


def tint(hex_color: str, alpha: float) -> str:
    """Return a #rrggbb at that opacity, as #aarrggbb, for halos."""
    return f"#{round(alpha * 255):02x}{hex_color[1:]}"


def mono(font: QFont) -> QFont:
    """Return `font` with the theme's fixed-width family (`Fonts.MONO`).

    All the families go, in order, with the kind as the last word: on a
    machine that has none of them, such as a Linux without Cascadia or
    Consolas, Qt picks another fixed-width font instead of falling back
    to the default proportional one.
    """
    families = [f.strip().strip('"') for f in Fonts.MONO.split(",")]
    font.setFamilies([f for f in families if f != "monospace"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class Metrics:
    """The sizes that `Style` gives Fusion."""

    SCROLL_BAR = 8
    SCROLL_HANDLE_MIN = 24
    SPLITTER = 1
    CHECK_BOX = 15
    CHECK_SPACING = 9
    TOOL_TIP_MARGIN = Spacing.SM
    MENU_ITEM = 32


class Style(QProxyStyle):
    """Fusion, with frames, check boxes and scroll bars that show.

    Fusion darkens the window color for its frames and grooves, and on a
    dark window they do not show.
    """

    def __init__(self) -> None:
        """Wrap Fusion."""
        super().__init__("Fusion")

    @override
    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw frames in the outline and check boxes in the palette."""
        if element in (
            QStyle.PrimitiveElement.PE_FrameLineEdit,
            QStyle.PrimitiveElement.PE_Frame,
            QStyle.PrimitiveElement.PE_FrameMenu,
        ):
            frame(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            check_box(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_PanelMenu:
            menu_panel(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    @override
    def drawComplexControl(
        self,
        control: QStyle.ComplexControl,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw a thin scroll bar, and frame a spin or a combo box."""
        if control == QStyle.ComplexControl.CC_ScrollBar and isinstance(
            option, QStyleOptionSlider
        ):
            scroll_bar(self, option, painter, widget)
            return
        super().drawComplexControl(control, option, painter, widget)
        if control in (QStyle.ComplexControl.CC_SpinBox, QStyle.ComplexControl.CC_ComboBox):
            frame(option, painter)

    @override
    def drawControl(
        self,
        element: QStyle.ControlElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw splitters, menu separators and the hovered menu item.

        A splitter and a separator are a line in the outline variant,
        and the item under the cursor a state layer.
        """
        colors = cast(QPalette, option.palette)
        if element == QStyle.ControlElement.CE_Splitter:
            painter.fillRect(cast(QRect, option.rect), colors.color(QPalette.ColorRole.Mid))
            return
        if element == QStyle.ControlElement.CE_MenuItem and isinstance(
            option, QStyleOptionMenuItem
        ):
            shown = menu_item(option, painter)
            if shown is None:
                return
            option = shown
        super().drawControl(element, option, painter, widget)

    @override
    def sizeFromContents(
        self,
        kind: QStyle.ContentsType,
        option: QStyleOption,
        size: QSize,
        widget: QWidget | None = None,
    ) -> QSize:
        """Give a menu item the height of `Metrics.MENU_ITEM`."""
        found = self.baseStyle().sizeFromContents(kind, option, size, widget)
        if (
            kind == QStyle.ContentsType.CT_MenuItem
            and isinstance(option, QStyleOptionMenuItem)
            and option.menuItemType != QStyleOptionMenuItem.MenuItemType.Separator
        ):
            found.setHeight(max(found.height(), Metrics.MENU_ITEM))
        return found

    @override
    def subControlRect(
        self,
        control: QStyle.ComplexControl,
        option: QStyleOptionComplex,
        sub: QStyle.SubControl,
        widget: QWidget | None = None,
    ) -> QRect:
        """Lay out a scroll bar with no arrows."""
        if control == QStyle.ComplexControl.CC_ScrollBar and isinstance(
            option, QStyleOptionSlider
        ):
            return scroll_part(option, sub)
        return self.baseStyle().subControlRect(control, option, sub, widget)

    @override
    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Give the sizes of `Metrics`."""
        sizes = {
            QStyle.PixelMetric.PM_ScrollBarExtent: Metrics.SCROLL_BAR,
            QStyle.PixelMetric.PM_ScrollBarSliderMin: Metrics.SCROLL_HANDLE_MIN,
            QStyle.PixelMetric.PM_SplitterWidth: Metrics.SPLITTER,
            QStyle.PixelMetric.PM_IndicatorWidth: Metrics.CHECK_BOX,
            QStyle.PixelMetric.PM_IndicatorHeight: Metrics.CHECK_BOX,
            QStyle.PixelMetric.PM_CheckBoxLabelSpacing: Metrics.CHECK_SPACING,
            QStyle.PixelMetric.PM_ToolTipLabelFrameWidth: Metrics.TOOL_TIP_MARGIN,
        }
        if metric in sizes:
            return sizes[metric]
        return super().pixelMetric(metric, option, widget)

    @override
    def styleHint(
        self,
        hint: QStyle.StyleHint,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
        returnData: QStyleHintReturn | None = None,
    ) -> int:
        """Draw the grid of a table in the outline variant."""
        if hint == QStyle.StyleHint.SH_Table_GridLineColor and option is not None:
            # An opaque QRgb, as the signed int that styleHint returns.
            mid = cast(QPalette, option.palette).color(QPalette.ColorRole.Mid)
            return mid.rgb() - (1 << 32)
        return super().styleHint(hint, option, widget, returnData)


def has(option: QStyleOption, flag: QStyle.StateFlag) -> bool:
    """Return whether the state of a style option has that flag."""
    # PySide types the fields of a style option as an ellipsis.
    return bool(cast(QStyle.StateFlag, option.state) & flag)


def frame(option: QStyleOption, painter: QPainter) -> None:
    """Draw a frame in Dark, the outline, or in Highlight with focus."""
    focus = has(option, QStyle.StateFlag.State_HasFocus)
    width = 2 if focus else 1
    role = QPalette.ColorRole.Highlight if focus else QPalette.ColorRole.Dark
    inset = width / 2
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(cast(QPalette, option.palette).color(role), width))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    rect = QRectF(cast(QRect, option.rect)).adjusted(inset, inset, -inset, -inset)
    painter.drawRoundedRect(rect, 2, 2)
    painter.restore()


def check_box(option: QStyleOption, painter: QPainter) -> None:
    """Draw a check box: a field, or filled with Highlight if checked.

    With focus, its outline goes in Highlight and 2 px, like a field's.
    """
    colors = cast(QPalette, option.palette)
    checked = has(option, QStyle.StateFlag.State_On)
    focus = has(option, QStyle.StateFlag.State_HasFocus)
    if checked:
        fill = edge = colors.color(QPalette.ColorRole.Highlight)
    else:
        fill = colors.color(QPalette.ColorRole.Base)
        edge = colors.color(QPalette.ColorRole.Dark)
    if not has(option, QStyle.StateFlag.State_Enabled):
        edge = colors.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        if checked:
            fill = edge
    if focus:
        edge = colors.color(QPalette.ColorRole.Highlight)
    width = 2 if focus else 1
    inset = width / 2
    rect = QRectF(cast(QRect, option.rect)).adjusted(inset, inset, -inset, -inset)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(edge, width))
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, Radius.SM, Radius.SM)
    if checked:
        pen = QPen(colors.color(QPalette.ColorRole.HighlightedText), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        side = rect.width()
        left, top = rect.left(), rect.top()
        painter.drawPolyline(
            [
                QPointF(left + side * 0.25, top + side * 0.52),
                QPointF(left + side * 0.43, top + side * 0.70),
                QPointF(left + side * 0.76, top + side * 0.32),
            ]
        )
    painter.restore()


def menu_panel(option: QStyleOption, painter: QPainter) -> None:
    """Fill a menu with AlternateBase, framed in Dark, the outline.

    AlternateBase is the body of a section, as in the menus of a repo.
    """
    colors = cast(QPalette, option.palette)
    rect = QRectF(cast(QRect, option.rect)).adjusted(0.5, 0.5, -0.5, -0.5)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(colors.color(QPalette.ColorRole.Dark), 1))
    painter.setBrush(colors.color(QPalette.ColorRole.AlternateBase))
    painter.drawRoundedRect(rect, Radius.SM, Radius.SM)
    painter.restore()


def menu_item(option: QStyleOptionMenuItem, painter: QPainter) -> QStyleOptionMenuItem | None:
    """Draw what Fusion does not show of a menu item.

    A separator is a line in Mid, the outline variant, and there is
    nothing left to draw. The item under the cursor gets a state layer
    of the text, and the option that Fusion draws on it, with the text
    in Highlight and no fill of its own.
    """
    colors = cast(QPalette, option.palette)
    rect = cast(QRect, option.rect)
    if option.menuItemType == QStyleOptionMenuItem.MenuItemType.Separator:
        middle = rect.center().y()
        painter.fillRect(
            QRect(rect.left() + Spacing.SM, middle, rect.width() - 2 * Spacing.SM, 1),
            colors.color(QPalette.ColorRole.Mid),
        )
        return None
    selected = has(option, QStyle.StateFlag.State_Selected)
    if not selected or not has(option, QStyle.StateFlag.State_Enabled):
        return option
    text = colors.color(QPalette.ColorRole.Text).name()
    base = colors.color(QPalette.ColorRole.AlternateBase).name()
    painter.fillRect(rect, blend(text, base, HOVER))
    plain = QStyleOptionMenuItem(option)
    # PySide types the fields of a style option as an ellipsis.
    plain.state = cast(QStyle.StateFlag, option.state) & ~QStyle.StateFlag.State_Selected  # pyrefly: ignore[bad-assignment]
    shown = QPalette(colors)
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        shown.setColor(role, colors.color(QPalette.ColorRole.Highlight))
    plain.palette = shown  # pyrefly: ignore[bad-assignment]
    return plain


def scroll_part(option: QStyleOptionSlider, sub: QStyle.SubControl) -> QRect:
    """Return a part of a scroll bar with no arrows.

    The handle, and the track on each side of it.
    """
    rect = cast(QRect, option.rect)
    horizontal = cast(Qt.Orientation, option.orientation) == Qt.Orientation.Horizontal
    length = rect.width() if horizontal else rect.height()
    if sub in (QStyle.SubControl.SC_ScrollBarAddLine, QStyle.SubControl.SC_ScrollBarSubLine):
        return QRect()
    if sub == QStyle.SubControl.SC_ScrollBarGroove:
        return rect
    minimum, maximum = cast(int, option.minimum), cast(int, option.maximum)
    span = maximum - minimum
    page = cast(int, option.pageStep)
    handle = (
        length if span <= 0 else max(Metrics.SCROLL_HANDLE_MIN, length * page // (span + page))
    )
    handle = min(handle, length)
    start = QStyle.sliderPositionFromValue(
        minimum,
        maximum,
        cast(int, option.sliderPosition),
        length - handle,
        cast(bool, option.upsideDown),
    )
    if sub == QStyle.SubControl.SC_ScrollBarSlider:
        first, size = start, handle
    elif sub == QStyle.SubControl.SC_ScrollBarSubPage:
        first, size = 0, start
    elif sub == QStyle.SubControl.SC_ScrollBarAddPage:
        first, size = start + handle, length - start - handle
    else:
        return QRect()
    if horizontal:
        return QRect(rect.left() + first, rect.top(), size, rect.height())
    return QRect(rect.left(), rect.top() + first, rect.width(), size)


def scroll_bar(
    style: QStyle, option: QStyleOptionSlider, painter: QPainter, widget: QWidget | None
) -> None:
    """Draw only the handle of a scroll bar.

    In Dark, the outline, and in PlaceholderText under the cursor.
    """
    if cast(int, option.maximum) <= cast(int, option.minimum):
        return
    handle = style.subControlRect(
        QStyle.ComplexControl.CC_ScrollBar, option, QStyle.SubControl.SC_ScrollBarSlider, widget
    )
    hovered = has(option, QStyle.StateFlag.State_MouseOver) and bool(
        cast(QStyle.SubControl, option.activeSubControls) & QStyle.SubControl.SC_ScrollBarSlider
    )
    role = QPalette.ColorRole.PlaceholderText if hovered else QPalette.ColorRole.Dark
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cast(QPalette, option.palette).color(role))
    painter.drawRoundedRect(QRectF(handle), Radius.SM, Radius.SM)
    painter.restore()


def apply(app: QApplication) -> None:
    """Set the style, the fonts and the palette of the initial theme."""
    app.setStyle(Style())
    app.setPalette(palette(SCHEME))
    font = QFont()
    font.setFamilies([f.strip().strip('"') for f in Fonts.FAMILY.split(",")][:-1])
    font.setPixelSize(Fonts.SIZE_BASE)
    app.setFont(font)
    small = QFont(font)
    small.setPixelSize(Fonts.SIZE_SM)
    # The stubs type the class name as bytes; PySide only takes a str.
    app.setFont(small, "QCheckBox")  # pyrefly: ignore[bad-argument-type]
    QToolTip.setFont(small)


def check_css(fill: str, border: str) -> str:
    """Return the rules of a marked check box, filled with `fill`.

    A panel of a repo paints its check boxes with its palette's
    (`theme.py::CHECK`). The disabled one goes along: a closer
    `:checked` would also paint it, and disabled it is gray.
    """
    return f"""
    QCheckBox::indicator:checked {{
        background: {fill};
        border: 1px solid {border};
        image: none;
    }}
    QCheckBox::indicator:checked:disabled {{
        background: {Colors.TEXT_DISABLED};
        border: 1px solid {Colors.TEXT_DISABLED};
    }}
    """


# --- The parts of the window -----------------------------------------
#
# Which role of the color scheme paints each part of the window.
#
# The ONE place to change it. A widget never names a role: it asks for
# its part (`theme.SECTION_HEADER.on(pal)`) and reads the slot it paints
# (`.bg`, `.fg`, `.border`, `.hover`, `.focus`). To repaint a part,
# change the role here.
#
# The roles are those of the ColorScheme of Material, the names of
# `colors.py`, and a `Role` member and not a loose string: typing
# `Role.` the editor lists them, and a role that does not exist fails on
# import, not on screen. A slot can also take a `Layer`: a role laid
# faint on another, as Material paints the hover.
#
# Slots:
#
# - `bg`: the background.
# - `fg`: the text (or the glyph) over that background.
# - `border`: the outline or the dividing line.
# - `hover`: the background under the cursor (for a list, the selected
#   row).
# - `focus`: the border with focus (for the window, its outline while
#   active).
#
# A part declares only the slots it paints; asking for another raises.
# `tests/test_palettes.py` checks that every part resolves in every
# theme and that its text reads over its background.


class Role(Enum):
    """A role of the color scheme that the parts take.

    `primary` and the two containers change with the theme; the others
    are the same in all of them.
    """

    PRIMARY = "primary"
    ON_PRIMARY = "on_primary"
    PRIMARY_CONTAINER = "primary_container"
    ON_PRIMARY_CONTAINER = "on_primary_container"
    SECONDARY_CONTAINER = "secondary_container"
    ON_SECONDARY_CONTAINER = "on_secondary_container"
    SURFACE = "surface"
    SURFACE_CONTAINER_LOW = "surface_container_low"
    SURFACE_CONTAINER = "surface_container"
    SURFACE_CONTAINER_HIGH = "surface_container_high"
    SURFACE_CONTAINER_HIGHEST = "surface_container_highest"
    ON_SURFACE = "on_surface"
    ON_SURFACE_VARIANT = "on_surface_variant"
    OUTLINE = "outline"
    OUTLINE_VARIANT = "outline_variant"


@dataclass(frozen=True)
class Layer:
    """A role laid on another at an opacity, as a state layer."""

    over: Role
    base: Role
    opacity: float = HOVER


def color(slot: Role | Layer, pal: Palette) -> str:
    """Return the hex of that role, or that layer, in that palette."""
    if isinstance(slot, Layer):
        return blend(pal.colors[slot.over.value], pal.colors[slot.base.value], slot.opacity)
    return pal.colors[slot.value]


@dataclass(frozen=True)
class Look:
    """The roles of one part, slot by slot."""

    bg: Role | Layer | None = None
    fg: Role | Layer | None = None
    border: Role | Layer | None = None
    hover: Role | Layer | None = None
    focus: Role | Layer | None = None

    def on(self, pal: Palette) -> Paint:
        """Return this part's colors in that palette."""
        return Paint(self, pal)

    def slots(self) -> dict[str, Role | Layer]:
        """Return the slots it declares."""
        return {f.name: role for f in fields(self) if (role := getattr(self, f.name)) is not None}


@dataclass(frozen=True)
class Paint:
    """A part's colors already resolved against one palette."""

    look: Look
    pal: Palette

    def _slot(self, slot: str) -> str:
        role = getattr(self.look, slot)
        if role is None:
            raise LookupError(f"{self.look} does not declare «{slot}»")
        return color(role, self.pal)

    @property
    def bg(self) -> str:
        """Return the background."""
        return self._slot("bg")

    @property
    def fg(self) -> str:
        """Return the text."""
        return self._slot("fg")

    @property
    def border(self) -> str:
        """Return the outline."""
        return self._slot("border")

    @property
    def hover(self) -> str:
        """Return the background under the cursor."""
        return self._slot("hover")

    @property
    def focus(self) -> str:
        """Return the border with focus."""
        return self._slot("focus")


# Bands and headers carry the repo's color: the title bar, the menu row
# and the section headers. The bodies where one reads and types
# (console, section bodies, menus, fields, tables, footers, status bar)
# go in the surfaces, gray in every theme, so the window does not read
# as one tinted wash. A divider goes in `OUTLINE_VARIANT`, and the
# outline of a control, which has to show, in `OUTLINE`.

# --- top of the window ------------------------------------------------

# The whole first row: the brand, the window buttons.
TITLE_BAR = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY)
# The repo tabs that are not selected, painted with the ACTIVE repo's
# palette.
REPO_TAB = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY, border=Role.ON_PRIMARY)
# The selected repo tab, with its own palette: it joins the menu row
# (`MENU_BAR`, below).
REPO_TAB_SELECTED = Look(bg=Role.SECONDARY_CONTAINER, fg=Role.PRIMARY)
# The «+» that adds a repo.
ADD_TAB = Look(fg=Role.ON_PRIMARY, border=Role.ON_PRIMARY)

# What is behind everything, and the outline of the frameless window.
WINDOW = Look(bg=Role.SURFACE, border=Role.OUTLINE_VARIANT, focus=Role.PRIMARY)
# The menu row; `hover` is the title of the open menu, in the popup's
# color.
MENU_BAR = Look(
    bg=REPO_TAB_SELECTED.bg,
    fg=Role.ON_SECONDARY_CONTAINER,
    border=Role.OUTLINE_VARIANT,
    hover=Role.SURFACE_CONTAINER_LOW,
)
# A popup of the menu bar; `border` is also its separators.
MENU = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE, border=Role.OUTLINE)
# The item under the cursor in a menu.
MENU_ITEM = Look(bg=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_LOW), fg=Role.PRIMARY)
# The action search's field, on the menu row: in the repo's color, not
# in the gray of the other fields.
SEARCH_FIELD = Look(
    bg=Role.SECONDARY_CONTAINER,
    fg=Role.ON_SECONDARY_CONTAINER,
    border=Role.OUTLINE,
    focus=Role.PRIMARY,
)
# The action search's list; `border` is also its scroll bar.
SEARCH_LIST = Look(bg=Role.SURFACE_CONTAINER_LOW, border=Role.OUTLINE)

# --- headers ----------------------------------------------------------

# The clickable bar with a section's name. «CONSOLA» is the same part.
SECTION_HEADER = Look(
    bg=Role.PRIMARY_CONTAINER,
    fg=Role.ON_PRIMARY_CONTAINER,
    border=Role.OUTLINE_VARIANT,
    hover=Layer(Role.ON_PRIMARY_CONTAINER, Role.PRIMARY_CONTAINER),
)
# The bar under the run tabs that names the view («CONSOLA») and
# carries the endpoint the task published.
CONSOLE_HEADER = SECTION_HEADER

# --- left: runs -------------------------------------------------------

# The bar with the run tabs.
RUN_BAR = Look(bg=Role.SURFACE_CONTAINER_LOW, border=Role.OUTLINE_VARIANT)
# A run tab that is not active: its outline sets it apart from the bar.
RUN_TAB = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE_VARIANT, border=Role.OUTLINE)
# The active run tab, open into the header below it: the same `bg`.
RUN_TAB_ACTIVE = Look(
    bg=CONSOLE_HEADER.bg, fg=Role.ON_PRIMARY_CONTAINER, border=Role.OUTLINE_VARIANT
)
# Behind the console and the second view.
CANVAS = Look(bg=Role.SURFACE)
# The output of a run.
CONSOLE = Look(bg=Role.SURFACE, fg=Role.ON_SURFACE_VARIANT)
# The strip above the browser and the database.
TOOL_BAR = Look(bg=Role.SURFACE_CONTAINER, border=Role.OUTLINE_VARIANT)
# The small buttons of those bars.
CHIP = Look(bg=Role.SURFACE_CONTAINER_HIGHEST, fg=Role.ON_SURFACE_VARIANT)

# --- left: database ---------------------------------------------------

# The grid and the tree; `border` is the grid lines, `hover` the
# selected row.
TABLE = Look(
    bg=Role.SURFACE,
    fg=Role.ON_SURFACE,
    border=Role.SURFACE_CONTAINER,
    hover=Role.SECONDARY_CONTAINER,
)
# Every other row of the grid.
TABLE_ALT_ROW = Look(bg=Role.SURFACE_CONTAINER_LOW)
# The column titles.
TABLE_HEADER = Look(
    bg=Role.SURFACE_CONTAINER, fg=Role.ON_SURFACE_VARIANT, border=Role.OUTLINE_VARIANT
)
# The tree's column, left of the grid.
TABLE_TREE = Look(bg=Role.SURFACE, border=Role.OUTLINE_VARIANT)
# The tab of the explorer that is open (Datos, Columnas…).
TABLE_TAB = Look(fg=Role.ON_SURFACE, border=Role.PRIMARY)

# --- right: sections --------------------------------------------------

# What a section holds, with its scroll bar.
SECTION_BODY = Look(bg=Role.SURFACE_CONTAINER_LOW)
# The bar to drag between two open sections: the body's color, so it
# only shows on hover.
SECTION_GRIP = Look(
    bg=SECTION_BODY.bg,
    border=Role.OUTLINE_VARIANT,
    hover=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_LOW),
)
# The bottom strip of a panel: Limpiar · Ejecutar, Guardar · Recargar.
FOOTER = Look(bg=Role.SURFACE_CONTAINER, border=Role.OUTLINE_VARIANT)
# Text fields and closed lists.
FIELD = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    focus=Role.PRIMARY,
)
# A field of «Configuración del repo» whose key has no value: an outline
# lighter than a field's.
FIELD_EMPTY = Look(border=Role.ON_SURFACE_VARIANT)
# The open list of a combo; `hover` is the selected entry.
COMBO_LIST = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    hover=Role.PRIMARY,
)
# The fill of a marked check box.
CHECK = Look(bg=Role.PRIMARY, border=Role.PRIMARY)
# Ejecutar, when it can run.
RUN_BUTTON = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY)
# Ejecutar, when it cannot: disabled text.
RUN_BUTTON_OFF = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_HIGHEST, DISABLED),
)
# Outlined buttons: Limpiar, Simulacro, Cancelar.
BUTTON = Look(
    fg=Role.ON_SURFACE_VARIANT,
    border=Role.OUTLINE,
    hover=Layer(Role.ON_SURFACE_VARIANT, Role.SURFACE_CONTAINER),
)
# Outlined buttons in the accent: Crear, Importar, Guardar, Recargar.
ACCENT_BUTTON = Look(
    fg=Role.PRIMARY,
    border=Role.PRIMARY,
    hover=Layer(Role.PRIMARY, Role.SURFACE_CONTAINER),
)
# Filled buttons: «Entendido», «Abrir en el navegador del sistema».
FILLED_BUTTON = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    hover=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_HIGHEST),
)

# --- bottom and dialogs -----------------------------------------------

# The bottom bar with padlocks, tools and RAM.
STATUS_BAR = Look(bg=Role.SURFACE_CONTAINER_HIGH, border=Role.OUTLINE_VARIANT)
# A closed padlock (the open one is red in every theme).
PADLOCK = Look(fg=Role.PRIMARY)
# The notices of the destructive guard.
DIALOG = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE)
# The repo's card in those notices: the one tinted plate in them.
REPO_CARD = Look(bg=Role.SECONDARY_CONTAINER, fg=Role.PRIMARY, border=Role.PRIMARY)

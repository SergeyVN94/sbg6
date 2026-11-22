"""Dark theme for the G6 control app."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

from ..assets import asset_path
from ..i18n import get_language

BG = "#101317"
BG_ALT = "#0b0d10"
CARD = "#181d24"
CARD_HOVER = "#1e242d"
BORDER = "#29313c"
TEXT = "#e7edf4"
MUTED = "#8c99a9"
DIM = "#5d6a79"
ACCENT = "#ff4d5f"
ACCENT_DARK = "#c9313f"
TEAL = "#4fd1c5"
BLUE = "#3b82f6"
OK = "#43d17a"
WARN = "#f0b429"

#: Colour used for the equalizer curve gradient.
CURVE_TOP = QColor("#4fd1c5")
CURVE_BOTTOM = QColor("#3b82f6")


CHECK_ICON = asset_path("check.svg").as_posix()


def apply(app) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_ALT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(CARD))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(CARD))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(DIM))
    app.setPalette(palette)

    font = QFont()
    if get_language().startswith("zh"):
        # Qt's per-glyph fallback is unreliable for CJK here; the Droid
        # fallback face covers both Han and Latin/Cyrillic, so lead with it.
        families = ["Droid Sans Fallback"]
    else:
        families = ["Inter", "Noto Sans", "DejaVu Sans"]
    font.setFamilies(families)
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QToolTip {{
    background: {CARD_HOVER};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------------------------------------------------------------- cards -- */
QFrame#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#effectCard {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#effectCard[active="true"] {{
    border-color: {ACCENT_DARK};
    background: #221b1e;
}}
QLabel#cardTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#sectionTitle {{
    font-size: 11px;
    font-weight: 700;
    color: {MUTED};
    letter-spacing: 1px;
}}
QLabel#muted {{
    color: {MUTED};
    font-size: 9pt;
}}
QLabel#dim {{
    color: {DIM};
    font-size: 9pt;
}}
QLabel#value {{
    color: {TEAL};
    font-size: 10pt;
    font-weight: 600;
}}
QLabel#bigValue {{
    font-size: 20pt;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#heroTitle {{
    font-size: 17pt;
    font-weight: 600;
}}
QLabel#badge {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 2px 9px;
    color: {MUTED};
    font-size: 9pt;
}}

/* --------------------------------------------------------------- buttons -- */
QPushButton {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    border-color: {DIM};
    background: #262e39;
}}
QPushButton:pressed {{
    background: #2d3643;
}}
QPushButton:disabled {{
    color: {DIM};
    background: {CARD};
}}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: #ff5f70;
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {MUTED};
    padding: 5px 8px;
}}
QPushButton#ghost:hover {{
    color: {TEXT};
    border-color: {BORDER};
}}
QPushButton#seg {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 6px 14px;
    color: {MUTED};
}}
QPushButton#seg:hover {{
    color: {TEXT};
}}
QPushButton#seg:checked {{
    background: {CARD};
    color: {TEXT};
    font-weight: 600;
}}

/* ----------------------------------------------------------- nav sidebar -- */
QFrame#sidebar {{
    background: {BG_ALT};
    border-right: 1px solid {BORDER};
}}
QPushButton#nav {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 9px 12px;
    text-align: left;
    color: {MUTED};
    font-size: 10pt;
}}
QPushButton#nav:hover {{
    background: {CARD};
    color: {TEXT};
}}
QPushButton#nav:checked {{
    background: #241a1d;
    color: #ffffff;
    font-weight: 600;
    border-left: 3px solid {ACCENT};
}}

/* ---------------------------------------------------------------- combos -- */
QComboBox {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
}}
QComboBox:hover {{
    border-color: {DIM};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {ACCENT};
}}

/* --------------------------------------------------------------- sliders -- */
QSlider:horizontal {{
    min-height: 26px;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: #2a323d;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {TEAL}, stop:1 {BLUE});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #eef4fb;
    border: none;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: #ffffff;
}}
QSlider::groove:horizontal:disabled {{
    background: #20262e;
}}
QSlider::sub-page:horizontal:disabled {{
    background: #39424e;
}}
QSlider::handle:horizontal:disabled {{
    background: #4c5663;
}}

/* -------------------------------------------------------------- scrolls -- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2f3844;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3c4756;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* -------------------------------------------------------------- checkbox -- */
QCheckBox {{
    spacing: 9px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {DIM};
    background: {BG_ALT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{CHECK_ICON}");
}}

QMenu {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
"""

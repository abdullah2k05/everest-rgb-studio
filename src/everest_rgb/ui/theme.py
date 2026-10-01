"""Dark application theme (QSS) and shared palette."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Palette -------------------------------------------------------------------
BG = "#141619"          # window background
BG_PANEL = "#1B1E23"    # side panel / cards
BG_INPUT = "#22262C"    # inputs, buttons
BG_HOVER = "#2A2F36"
BORDER = "#2E333A"
FG = "#D7DCE2"          # primary text
FG_DIM = "#8A929C"      # secondary text
ACCENT = "#00A8FF"      # interactive accent
ACCENT_HOVER = "#33BBFF"
DANGER = "#E5484D"
SUCCESS = "#46C86E"
KEY_BG = "#262A30"
KEY_BORDER = "#33383F"
KEY_LABEL = "#9AA3AD"
SELECTED_BORDER = "#FFB020"

SIDEBAR_WIDTH = 168


def palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG))
    p.setColor(QPalette.ColorRole.WindowText, QColor(FG))
    p.setColor(QPalette.ColorRole.Base, QColor(BG_INPUT))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_PANEL))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_INPUT))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(FG))
    p.setColor(QPalette.ColorRole.Text, QColor(FG))
    p.setColor(QPalette.ColorRole.Button, QColor(BG_INPUT))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(FG))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#0B0D10"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(FG_DIM))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(FG_DIM))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(FG_DIM))
    return p


STYLESHEET = f"""
* {{
    font-family: "Inter", "SF Pro Text", "Cantarell", "Noto Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {FG}; }}
QLabel {{ background: transparent; }}
QLabel#heading {{ font-size: 17px; font-weight: 600; }}
QLabel#subheading {{ color: {FG_DIM}; font-size: 12px; }}
QLabel#dim {{ color: {FG_DIM}; }}
QLabel#statusDot {{ font-size: 14px; font-weight: 600; }}

QFrame#sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER};
}}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {FG_DIM};
    padding: 9px 14px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#navButton:hover {{ background: {BG_HOVER}; color: {FG}; }}
QPushButton#navButton:checked {{
    background: #24303B;
    color: {ACCENT};
    font-weight: 600;
}}

QPushButton {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    color: {FG};
}}
QPushButton:hover {{ background: {BG_HOVER}; border-color: #3B424B; }}
QPushButton:pressed {{ background: #1D2127; }}
QPushButton:disabled {{ color: {FG_DIM}; background: {BG_PANEL}; }}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #06121C;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#tool {{
    padding: 4px 9px;
    font-size: 12px;
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {FG_DIM}; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    selection-background-color: #24303B;
    selection-color: {FG};
    outline: none;
}}

QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #EDF1F5; width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: white; }}

QListWidget, QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: #24303B; color: {FG}; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
    background: {BG_PANEL};
}}
QTabBar::tab {{
    background: transparent; color: {FG_DIM};
    padding: 7px 16px; border: none;
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}

QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #454C55; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}

QStatusBar {{ background: {BG_PANEL}; border-top: 1px solid {BORDER}; color: {FG_DIM}; }}
QToolTip {{
    background: {BG_INPUT}; color: {FG}; border: 1px solid {BORDER};
    padding: 4px 6px;
}}
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 8px;
    margin-top: 14px; padding-top: 8px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {FG_DIM};
}}
QMessageBox {{ background: {BG_PANEL}; }}
QSplitter::handle {{ background: {BORDER}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setPalette(palette())
    app.setStyleSheet(STYLESHEET)


def luminance(color: tuple[int, int, int]) -> float:
    r, g, b = color
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def label_color(color: tuple[int, int, int]) -> str:
    return "#101317" if luminance(color) > 0.55 else "#E6EBF0"

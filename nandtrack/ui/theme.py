"""Visual language.

The palette is cold and instrument-like: a blue-black chassis with two signal
colours that carry meaning rather than decoration. Rising prices read warm
(copper, the colour of everything getting more expensive) and falling prices
read cool mint - deliberately the opposite of a stock ticker, because on this
screen a rising line is the bad news.

Prices and percentages are set in a tabular monospace so decimal points line up
down a column; everything else uses the system UI face.
"""

from __future__ import annotations

from typing import Dict

DARK: Dict[str, str] = {
    "bg": "#0F131A",
    "panel": "#161C25",
    "panel_hi": "#1D2530",
    "line": "#2A3441",
    "line_soft": "#212A36",
    "ink": "#E7ECF3",
    "ink_dim": "#8996A8",
    "ink_faint": "#5F6B7C",
    "rise": "#F2994A",
    "fall": "#3ECFB0",
    "flat": "#8996A8",
    "focus": "#6C8CFF",
    "grid": "#1F2733",
    "select": "#22303F",
}

LIGHT: Dict[str, str] = {
    "bg": "#F1F3F7",
    "panel": "#FFFFFF",
    "panel_hi": "#F7F9FC",
    "line": "#DCE2EA",
    "line_soft": "#E7ECF2",
    "ink": "#121924",
    "ink_dim": "#5D6B7E",
    "ink_faint": "#8A97A8",
    "rise": "#C0651A",
    "fall": "#128C72",
    "flat": "#5D6B7E",
    "focus": "#3D63E0",
    "grid": "#E4E9F0",
    "select": "#E3EBF6",
}

UI_FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif'
NUM_FONT = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'


def palette(theme: str) -> Dict[str, str]:
    return DARK if theme == "dark" else LIGHT


def change_colour(theme: str, value) -> str:
    c = palette(theme)
    if value is None or abs(value) < 0.05:
        return c["flat"]
    return c["rise"] if value > 0 else c["fall"]


def stylesheet(theme: str) -> str:
    c = palette(theme)
    return f"""
QWidget {{
    background: {c['bg']};
    color: {c['ink']};
    font-family: {UI_FONT};
    font-size: 13px;
}}
QToolTip {{
    background: {c['panel_hi']};
    color: {c['ink']};
    border: 1px solid {c['line']};
    padding: 6px 8px;
}}

/* ---- left navigation rail ---- */
#NavRail {{
    background: {c['panel']};
    border-right: 1px solid {c['line']};
}}
#NavRail QPushButton {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    padding: 9px 14px;
    text-align: left;
    color: {c['ink_dim']};
    font-size: 13.5px;
}}
#NavRail QPushButton:hover {{
    background: {c['panel_hi']};
    color: {c['ink']};
}}
#NavRail QPushButton:checked {{
    background: {c['select']};
    color: {c['ink']};
    border-left: 3px solid {c['focus']};
    font-weight: 600;
}}
#WordMark {{ font-size: 17px; font-weight: 700; letter-spacing: 0.2px; }}
#WordMarkSub {{ color: {c['ink_faint']}; font-size: 11.5px; }}
#NavGroup {{ color: {c['ink_faint']}; font-size: 11.5px; padding: 14px 14px 4px 17px; }}

/* ---- cards and panels ---- */
#Card, #Panel {{
    background: {c['panel']};
    border: 1px solid {c['line']};
    border-radius: 8px;
}}
#CardTitle {{ color: {c['ink_dim']}; font-size: 12.5px; }}
#CardValue {{ font-family: {NUM_FONT}; font-size: 26px; font-weight: 600; }}
#CardFoot {{ color: {c['ink_faint']}; font-size: 11.5px; }}
#Heading {{ font-size: 19px; font-weight: 650; }}
#SubHeading {{ color: {c['ink_dim']}; font-size: 12.5px; }}
#Numeral {{ font-family: {NUM_FONT}; }}

/* ---- tables ---- */
QTableView {{
    background: {c['panel']};
    alternate-background-color: {c['panel_hi']};
    gridline-color: {c['line_soft']};
    border: 1px solid {c['line']};
    border-radius: 8px;
    selection-background-color: {c['select']};
    selection-color: {c['ink']};
    font-size: 12.5px;
}}
QTableView::item {{ padding: 5px 8px; }}
QHeaderView::section {{
    background: {c['panel']};
    color: {c['ink_dim']};
    border: none;
    border-bottom: 1px solid {c['line']};
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
}}
QTableCornerButton::section {{ background: {c['panel']}; border: none; }}

/* ---- controls ---- */
QPushButton {{
    background: {c['panel_hi']};
    border: 1px solid {c['line']};
    border-radius: 6px;
    padding: 6px 12px;
    color: {c['ink']};
}}
QPushButton:hover {{ border-color: {c['focus']}; }}
QPushButton:pressed {{ background: {c['select']}; }}
QPushButton:disabled {{ color: {c['ink_faint']}; border-color: {c['line_soft']}; }}
QPushButton#Primary {{
    background: {c['focus']};
    border-color: {c['focus']};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Ghost {{ background: transparent; border-color: {c['line']}; }}

QComboBox, QSpinBox, QLineEdit, QDoubleSpinBox {{
    background: {c['panel_hi']};
    border: 1px solid {c['line']};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 18px;
    selection-background-color: {c['focus']};
}}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus, QDoubleSpinBox:focus {{
    border-color: {c['focus']};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {c['panel_hi']};
    border: 1px solid {c['line']};
    selection-background-color: {c['select']};
    outline: none;
}}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {c['line']};
    border-radius: 4px;
    background: {c['panel_hi']};
}}
QCheckBox::indicator:checked {{ background: {c['focus']}; border-color: {c['focus']}; }}

QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 7px;
    border: 1px solid {c['line']}; background: {c['panel_hi']};
}}
QRadioButton::indicator:checked {{ background: {c['focus']}; border-color: {c['focus']}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['ink_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['line']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QScrollArea {{ border: none; background: transparent; }}

/* ---- status strip ---- */
#StatusStrip {{
    background: {c['panel']};
    border-top: 1px solid {c['line']};
}}
#StatusText {{ color: {c['ink_dim']}; font-size: 12px; }}
#StatusDot {{ font-size: 12px; }}

QSplitter::handle {{ background: {c['line_soft']}; }}
QGroupBox {{
    border: 1px solid {c['line']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {c['ink_dim']}; }}
"""

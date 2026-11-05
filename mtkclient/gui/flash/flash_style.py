#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Stylesheet for the flashing window, in a light and a dark variant."""

_COMMON = """
QWidget {{ font-size: 13px; color: {text}; }}
QMainWindow, #Root {{ background-color: {bg}; }}
#Card {{
    background-color: {card};
    border: 1px solid {border};
    border-radius: 10px;
}}
#Title {{ font-size: 20px; font-weight: 600; color: {text}; }}
#SectionLabel {{ font-size: 11px; font-weight: 600; color: {muted};
                 text-transform: uppercase; letter-spacing: 1px; }}
#Hint {{ color: {muted}; font-size: 12px; }}
#StatusPill {{
    padding: 4px 12px; border-radius: 11px;
    background-color: {pill_bg}; color: {pill_fg};
    font-size: 12px; font-weight: 600;
}}
QLineEdit {{
    background-color: {input_bg}; border: 1px solid {border};
    border-radius: 6px; padding: 6px 9px; selection-background-color: {accent};
}}
QLineEdit:focus {{ border: 1px solid {accent}; }}
QLineEdit:read-only {{ color: {muted}; }}
QComboBox {{
    background-color: {input_bg}; border: 1px solid {border};
    border-radius: 6px; padding: 5px 9px; min-width: 90px;
}}
QComboBox QAbstractItemView {{
    background-color: {card}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: #ffffff;
}}
QPushButton {{
    background-color: {btn_bg}; border: 1px solid {border};
    border-radius: 6px; padding: 6px 14px; color: {text};
}}
QPushButton:hover {{ background-color: {btn_hover}; }}
QPushButton:disabled {{ color: {muted}; background-color: {card}; }}
#Primary {{
    background-color: {accent}; border: none; color: #ffffff;
    font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 8px;
}}
#Primary:hover {{ background-color: {accent_hover}; }}
#Primary:disabled {{ background-color: {border}; color: {muted}; }}
#Danger {{ background-color: transparent; border: 1px solid {danger};
           color: {danger}; border-radius: 8px; padding: 10px 16px; }}
#Danger:hover {{ background-color: {danger}; color: #ffffff; }}
QTableWidget {{
    background-color: {card}; border: 1px solid {border};
    border-radius: 8px; gridline-color: transparent;
    selection-background-color: {sel_bg}; selection-color: {text};
}}
QHeaderView::section {{
    background-color: {header_bg}; color: {muted};
    border: none; border-bottom: 1px solid {border};
    padding: 7px 8px; font-size: 11px; font-weight: 600;
}}
QTableWidget::item {{ padding: 5px 8px; border-bottom: 1px solid {row_line}; }}
QProgressBar {{
    background-color: {track}; border: none; border-radius: 5px;
    height: 10px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background-color: {accent}; border-radius: 5px; }}
#OverallBar::chunk {{ background-color: {ok}; }}
QPlainTextEdit {{
    background-color: {log_bg}; border: 1px solid {border};
    border-radius: 8px; color: {log_fg};
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px;
}}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {border}; background-color: {input_bg};
}}
QCheckBox::indicator:checked {{
    background-color: {accent}; border: 1px solid {accent};
    image: url(data:image/svg+xml;base64,{tick});
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px;
                               min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

# A white check mark, inlined so the stylesheet needs no asset files.
_TICK = ("PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAx"
         "NiAxNiI+PHBhdGggZmlsbD0ibm9uZSIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIu"
         "MiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBkPSJN"
         "MyA4LjVsMy41IDMuNUwxMyA0Ii8+PC9zdmc+")

LIGHT = dict(
    bg="#f0f0f3", text="#1d1d1f", muted="#86868b", card="#ffffff", border="#d6d6db",
    input_bg="#ffffff", btn_bg="#f5f5f7", btn_hover="#ebebf0",
    accent="#0071e3", accent_hover="#0077ed", danger="#d70015", ok="#1c8c3c",
    track="#e8e8ed", header_bg="#fafafc", row_line="#f0f0f3",
    sel_bg="#e5f1fd", log_bg="#fafafc", log_fg="#3a3a3c",
    pill_bg="#f0f0f3", pill_fg="#6e6e73",
)

DARK = dict(
    bg="#1c1c1e", text="#f5f5f7", muted="#98989d", card="#2c2c2e", border="#3a3a3c",
    input_bg="#1c1c1e", btn_bg="#3a3a3c", btn_hover="#48484a",
    accent="#0a84ff", accent_hover="#409cff", danger="#ff453a", ok="#32d74b",
    track="#3a3a3c", header_bg="#242426", row_line="#323234",
    sel_bg="#0a3a66", log_bg="#1c1c1e", log_fg="#c7c7cc",
    pill_bg="#3a3a3c", pill_fg="#c7c7cc",
)

# Status pill colours per phase: (background, foreground)
PILL_COLORS = {
    "waiting": ("#8e8e93", "#ffffff"),
    "connected": ("#0071e3", "#ffffff"),
    "flashing": ("#f09000", "#ffffff"),
    "done": ("#1c8c3c", "#ffffff"),
    "failed": ("#d70015", "#ffffff"),
}


def stylesheet(dark: bool = False) -> str:
    palette = dict(DARK if dark else LIGHT)
    palette["tick"] = _TICK
    return _COMMON.format(**palette)

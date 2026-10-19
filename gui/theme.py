"""Theme management and modern professional stylesheets for C3D Explorer."""

from typing import Dict, Any, List


def build_theme_qss(
    bg: str,
    panel_bg: str,
    card_bg: str,
    header_bg: str,
    border: str,
    border_light: str,
    text: str,
    text_muted: str,
    text_bright: str,
    accent: str,
    accent_hover: str,
    accent_pressed: str,
    table_bg: str,
    table_grid: str,
    input_bg: str,
    selection_bg: str,
    selection_text: str,
    scrollbar_bg: str,
    scrollbar_handle: str,
    dock_title_bg: str,
    alternate_bg: str = ""
) -> str:
    """Generate a comprehensive, consistent Qt stylesheet for the entire workstation."""
    if not alternate_bg:
        alternate_bg = card_bg

    return f"""
/* Base Application Styling */
QMainWindow, QDialog, QWidget {{
    background-color: {bg};
    color: {text};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}}

/* Menu Bar */
QMenuBar {{
    background-color: {header_bg};
    color: {text};
    border-bottom: 1px solid {border};
    padding: 3px 6px;
    font-size: 13px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {panel_bg};
    color: {accent};
}}
QMenu {{
    background-color: {card_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: #FFFFFF;
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 6px;
}}

/* ToolBar */
QToolBar {{
    background-color: {panel_bg};
    border-bottom: 1px solid {border};
    padding: 4px;
    spacing: 6px;
}}
QToolButton {{
    background-color: {card_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 5px 10px;
    font-weight: 500;
}}
QToolButton:hover {{
    background-color: {header_bg};
    border-color: {accent};
    color: {accent};
}}
QToolButton:pressed {{
    background-color: {accent_pressed};
    color: #FFFFFF;
}}
QToolButton:checked {{
    background-color: {accent};
    border-color: {accent};
    color: #FFFFFF;
}}

/* Push Buttons */
QPushButton {{
    background-color: {card_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {header_bg};
    border-color: {accent};
    color: {accent};
}}
QPushButton:pressed {{
    background-color: {accent_pressed};
    color: #FFFFFF;
}}
QPushButton:disabled {{
    background-color: {panel_bg};
    color: {text_muted};
    border-color: {border};
}}
QPushButton#primaryBtn {{
    background-color: {accent};
    color: #FFFFFF;
    border: 1px solid {accent};
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{
    background-color: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#primaryBtn:pressed {{
    background-color: {accent_pressed};
}}

/* Dock Widgets */
QDockWidget {{
    color: {text};
    font-weight: 600;
    font-size: 12px;
    titlebar-close-icon: url(none);
    titlebar-normal-icon: url(none);
}}
QDockWidget::title {{
    background-color: {dock_title_bg};
    padding: 7px 10px;
    border-bottom: 1px solid {border};
    font-weight: 600;
    letter-spacing: 0.5px;
}}

/* Splitters */
QSplitter::handle {{
    background-color: {border};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:vertical {{
    height: 3px;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {border};
    background-color: {panel_bg};
    border-radius: 4px;
}}
QTabBar::tab {{
    background-color: {header_bg};
    color: {text_muted};
    padding: 8px 14px;
    border: 1px solid transparent;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {panel_bg};
    color: {accent};
    border-bottom: 2px solid {accent};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background-color: {card_bg};
    color: {text};
}}

/* Tree and Table Views */
QTreeView, QTableView, QTableWidget, QListWidget {{
    background-color: {table_bg};
    alternate-background-color: {alternate_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    gridline-color: {table_grid};
    outline: none;
}}
QTreeView::item, QTableView::item, QTableWidget::item, QListWidget::item {{
    background-color: {table_bg};
    color: {text};
    padding: 3px 6px;
}}
QTreeView::item:alternate, QTableView::item:alternate, QTableWidget::item:alternate, QListWidget::item:alternate {{
    background-color: {alternate_bg};
    color: {text};
}}
QTreeView::item:selected, QTableView::item:selected, QTableWidget::item:selected, QListWidget::item:selected,
QTreeView::item:selected:active, QTableView::item:selected:active, QTableWidget::item:selected:active, QListWidget::item:selected:active,
QTreeView::item:selected:!active, QTableView::item:selected:!active, QTableWidget::item:selected:!active, QListWidget::item:selected:!active {{
    background-color: {selection_bg};
    color: {selection_text};
}}
QTreeView::item:hover:!selected, QTableView::item:hover:!selected, QTableWidget::item:hover:!selected, QListWidget::item:hover:!selected {{
    background-color: {card_bg};
}}
QHeaderView::section {{
    background-color: {header_bg};
    color: {text};
    padding: 6px;
    border: 1px solid {border};
    font-weight: 600;
}}
QTableCornerButton::section {{
    background-color: {header_bg};
    border: 1px solid {border};
}}

/* Line Edit / Search Box */
QLineEdit {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 5px 8px;
}}
QLineEdit:focus {{
    border: 1px solid {accent};
}}
QTableView QLineEdit, QTableWidget QLineEdit {{
    background-color: {input_bg};
    color: {accent};
    border: 1.5px solid {accent};
    border-radius: 3px;
    padding: 2px 4px;
    font-weight: 600;
    selection-background-color: {accent};
    selection-color: #FFFFFF;
}}

/* Combo Box */
QComboBox {{
    background-color: {card_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 5px 10px;
    min-width: 70px;
}}
QComboBox:hover {{
    border-color: {accent};
}}
QComboBox QAbstractItemView {{
    background-color: {card_bg};
    color: {text};
    selection-background-color: {accent};
    selection-color: #FFFFFF;
    border: 1px solid {border};
}}

/* Spin Boxes */
QSpinBox, QDoubleSpinBox {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 6px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}

/* Status Bar */
QStatusBar {{
    background-color: {header_bg};
    color: {text_muted};
    border-top: 1px solid {border};
    font-size: 12px;
}}
QStatusBar QLabel {{
    color: {text};
    padding: 2px 6px;
}}

/* Scroll Bars */
QScrollBar:vertical {{
    border: none;
    background: {scrollbar_bg};
    width: 9px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    min-height: 25px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {accent};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: {scrollbar_bg};
    height: 9px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {scrollbar_handle};
    min-width: 25px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {accent};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Checkbox */
QCheckBox {{
    color: {text};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {border};
    background: {input_bg};
}}
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}

/* Group Box */
QGroupBox {{
    border: 1px solid {border};
    border-radius: 6px;
    margin-top: 14px;
    font-weight: 600;
    color: {text};
    padding-top: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {accent};
}}
"""


# -------------------------------------------------------------
# 5 Professional Built-In Theme Definitions
# -------------------------------------------------------------
THEMES: Dict[str, Dict[str, Any]] = {
    "Biomech Dark (Obsidian & Cyan)": {
        "name": "Biomech Dark (Obsidian & Cyan)",
        "is_dark": True,
        "accent": "#00ADB5",
        "viewport_bg": "#151720",
        "plot_bg": "#151720",
        "plot_axis_color": "#ECEFF4",
        "grid_color": (80, 90, 110, 80),
        "qss": build_theme_qss(
            bg="#16181F",
            panel_bg="#1C1F2B",
            card_bg="#242838",
            header_bg="#121319",
            border="#2E344A",
            border_light="#3B4252",
            text="#ECEFF4",
            text_muted="#8C96AB",
            text_bright="#FFFFFF",
            accent="#00ADB5",
            accent_hover="#00C4CE",
            accent_pressed="#007982",
            table_bg="#181A24",
            table_grid="#242838",
            input_bg="#12141C",
            selection_bg="#00ADB5",
            selection_text="#FFFFFF",
            scrollbar_bg="#14161F",
            scrollbar_handle="#32384D",
            dock_title_bg="#1A1D27",
            alternate_bg="#1E2231"
        )
    },
    "Clinical Light (Clean Medical White)": {
        "name": "Clinical Light (Clean Medical White)",
        "is_dark": False,
        "accent": "#0284C7",
        "viewport_bg": "#EDF2F7",
        "plot_bg": "#FFFFFF",
        "plot_axis_color": "#2D3748",
        "grid_color": (180, 190, 205, 120),
        "qss": build_theme_qss(
            bg="#F3F4F6",
            panel_bg="#FFFFFF",
            card_bg="#F9FAFB",
            header_bg="#E5E7EB",
            border="#D1D5DB",
            border_light="#E5E7EB",
            text="#1F2937",
            text_muted="#6B7280",
            text_bright="#111827",
            accent="#0284C7",
            accent_hover="#0369A1",
            accent_pressed="#075985",
            table_bg="#FFFFFF",
            table_grid="#E5E7EB",
            input_bg="#F9FAFB",
            selection_bg="#0284C7",
            selection_text="#FFFFFF",
            scrollbar_bg="#F3F4F6",
            scrollbar_handle="#CBD5E1",
            dock_title_bg="#E5E7EB",
            alternate_bg="#F8FAFC"
        )
    },
    "Nordic Midnight (Arctic Deep Blue)": {
        "name": "Nordic Midnight (Arctic Deep Blue)",
        "is_dark": True,
        "accent": "#88C0D0",
        "viewport_bg": "#1E222A",
        "plot_bg": "#1E222A",
        "plot_axis_color": "#ECEFF4",
        "grid_color": (90, 110, 140, 85),
        "qss": build_theme_qss(
            bg="#1E222A",
            panel_bg="#242933",
            card_bg="#2E3440",
            header_bg="#171A21",
            border="#3B4252",
            border_light="#4C566A",
            text="#ECEFF4",
            text_muted="#8892B0",
            text_bright="#FFFFFF",
            accent="#88C0D0",
            accent_hover="#81A1C1",
            accent_pressed="#5E81AC",
            table_bg="#21252E",
            table_grid="#2C323E",
            input_bg="#191C23",
            selection_bg="#5E81AC",
            selection_text="#ECEFF4",
            scrollbar_bg="#1A1D24",
            scrollbar_handle="#3B4252",
            dock_title_bg="#21252E",
            alternate_bg="#282D38"
        )
    },
    "Graphite Slate (Monochrome Titanium)": {
        "name": "Graphite Slate (Monochrome Titanium)",
        "is_dark": True,
        "accent": "#F39C12",
        "viewport_bg": "#161718",
        "plot_bg": "#161718",
        "plot_axis_color": "#E4E6EB",
        "grid_color": (90, 90, 95, 80),
        "qss": build_theme_qss(
            bg="#18191A",
            panel_bg="#242526",
            card_bg="#303134",
            header_bg="#141516",
            border="#3A3B3C",
            border_light="#4E4F50",
            text="#E4E6EB",
            text_muted="#B0B3B8",
            text_bright="#FFFFFF",
            accent="#F39C12",
            accent_hover="#E67E22",
            accent_pressed="#D35400",
            table_bg="#202122",
            table_grid="#2A2B2C",
            input_bg="#141516",
            selection_bg="#E67E22",
            selection_text="#FFFFFF",
            scrollbar_bg="#141516",
            scrollbar_handle="#3A3B3C",
            dock_title_bg="#202122",
            alternate_bg="#26282B"
        )
    },
    "Cyber Amber (Navy & Gold)": {
        "name": "Cyber Amber (Navy & Gold)",
        "is_dark": True,
        "accent": "#FFB703",
        "viewport_bg": "#090F16",
        "plot_bg": "#090F16",
        "plot_axis_color": "#F0F4F8",
        "grid_color": (65, 90, 125, 85),
        "qss": build_theme_qss(
            bg="#0A1118",
            panel_bg="#101A24",
            card_bg="#172433",
            header_bg="#060B10",
            border="#1E2E40",
            border_light="#2A3D54",
            text="#F0F4F8",
            text_muted="#7E93A8",
            text_bright="#FFFFFF",
            accent="#FFB703",
            accent_hover="#FB8500",
            accent_pressed="#D97706",
            table_bg="#0D151F",
            table_grid="#162331",
            input_bg="#080E14",
            selection_bg="#FFB703",
            selection_text="#0A1118",
            scrollbar_bg="#070C12",
            scrollbar_handle="#1E2E40",
            dock_title_bg="#0D151F",
            alternate_bg="#131C28"
        )
    }

}

DEFAULT_THEME_NAME = "Biomech Dark (Obsidian & Cyan)"
DARK_THEME_QSS = THEMES[DEFAULT_THEME_NAME]["qss"]


def get_theme_names() -> List[str]:
    """Return ordered list of built-in theme names."""
    return list(THEMES.keys())


def get_theme(name: str) -> Dict[str, Any]:
    """Retrieve theme dictionary by name, falling back to default."""
    return THEMES.get(name, THEMES[DEFAULT_THEME_NAME])


def create_theme_palette(theme_dict: Dict[str, Any]):
    """Create a matching QPalette so native widgets and item delegates have proper dark/light colors."""
    from PySide6.QtGui import QPalette, QColor
    pal = QPalette()
    is_dark = theme_dict.get("is_dark", True)

    bg_col = QColor("#16181F" if is_dark else "#F3F4F6")
    text_col = QColor("#ECEFF4" if is_dark else "#1F2937")
    panel_col = QColor("#1C1F2B" if is_dark else "#FFFFFF")
    accent_col = QColor(theme_dict.get("accent", "#00ADB5" if is_dark else "#0284C7"))
    table_col = QColor("#181A24" if is_dark else "#FFFFFF")
    alt_col = QColor("#1E2231" if is_dark else "#F8FAFC")
    sel_text_col = QColor("#FFFFFF")

    pal.setColor(QPalette.Window, bg_col)
    pal.setColor(QPalette.WindowText, text_col)
    pal.setColor(QPalette.Base, table_col)
    pal.setColor(QPalette.AlternateBase, alt_col)
    pal.setColor(QPalette.ToolTipBase, panel_col)
    pal.setColor(QPalette.ToolTipText, text_col)
    pal.setColor(QPalette.Text, text_col)
    pal.setColor(QPalette.Button, panel_col)
    pal.setColor(QPalette.ButtonText, text_col)
    pal.setColor(QPalette.Highlight, accent_col)
    pal.setColor(QPalette.HighlightedText, sel_text_col)
    return pal

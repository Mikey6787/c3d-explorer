from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QGroupBox, QFormLayout, QColorDialog
)

from gui.theme import THEMES, get_theme, get_theme_names, DEFAULT_THEME_NAME
from gui.toggle_switch import ToggleSwitch



class SettingsDialog(QDialog):
    """Configuration dialog for visual appearance, coordinate systems, display themes, and playback."""
    settingsApplied = Signal(dict)

    def __init__(self, current_settings: dict, parent=None, initial_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Settings & Visual Configurations")
        self.resize(540, 530)
        self.settings = dict(current_settings)
        self._initial_tab = initial_tab if isinstance(initial_tab, int) else 0

        # Check theme brightness
        cur_theme_name = self.settings.get("theme", DEFAULT_THEME_NAME)
        theme_dict = get_theme(cur_theme_name)
        is_dark = theme_dict.get("is_dark", True)

        # Default marker color: if light theme and no explicit marker color was passed, default to black
        if "marker_color" in self.settings:
            raw_c = self.settings["marker_color"]
            self._marker_color_rgba = tuple(raw_c) if isinstance(raw_c, (list, tuple)) else (1.0, 1.0, 1.0, 1.0)
        elif not is_dark:
            self._marker_color_rgba = (0.0, 0.0, 0.0, 1.0)
        else:
            self._marker_color_rgba = (1.0, 1.0, 1.0, 1.0)

        self._marker_color_qcolor = QColor.fromRgbF(
            self._marker_color_rgba[0],
            self._marker_color_rgba[1],
            self._marker_color_rgba[2],
            1.0
        )

        # Ground Reaction Force (GRF) vector color setup
        if "grf_color" in self.settings:
            raw_gc = self.settings["grf_color"]
            self._grf_color_rgba = tuple(raw_gc) if isinstance(raw_gc, (list, tuple)) else (1.0, 0.35, 0.08, 1.0)
        else:
            self._grf_color_rgba = (1.0, 0.35, 0.08, 1.0)

        self._grf_color_qcolor = QColor.fromRgbF(
            self._grf_color_rgba[0],
            self._grf_color_rgba[1],
            self._grf_color_rgba[2],
            1.0
        )
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tabs = self.tabs = QTabWidget()

        # -------------------------------------------------------------
        # Tab 1: Display & Themes (New tab requested by user)
        # -------------------------------------------------------------
        tab_display = QWidget()
        d_layout = QVBoxLayout(tab_display)
        d_layout.setSpacing(12)

        # Group 1: Application Theme
        grp_theme = QGroupBox("Application Theme & Styling")
        form_theme = QFormLayout(grp_theme)
        form_theme.setSpacing(10)

        self.combo_theme = QComboBox()
        theme_names = get_theme_names()
        self.combo_theme.addItems(theme_names)
        cur_theme = self.settings.get("theme", DEFAULT_THEME_NAME)
        if cur_theme in theme_names:
            self.combo_theme.setCurrentText(cur_theme)
        self.combo_theme.currentTextChanged.connect(self._on_theme_changed)
        form_theme.addRow("Theme Preset:", self.combo_theme)

        self.combo_viewport_bg = QComboBox()
        self.combo_viewport_bg.addItems([
            "Theme Default",
            "Deep Charcoal (#151720)",
            "Pure Black (#000000)",
            "Slate Grey (#222733)",
            "Laboratory Light (#EDF2F7)",
            "Pure White (#FFFFFF)"
        ])
        cur_vp_bg = self.settings.get("viewport_bg_choice", "Theme Default")
        if cur_vp_bg in [self.combo_viewport_bg.itemText(i) for i in range(self.combo_viewport_bg.count())]:
            self.combo_viewport_bg.setCurrentText(cur_vp_bg)
        form_theme.addRow("3D Viewport Background:", self.combo_viewport_bg)
        d_layout.addWidget(grp_theme)

        # Group 2: Ground Grid
        grp_grid = QGroupBox("Ground Grid")
        form_grid = QFormLayout(grp_grid)
        form_grid.setSpacing(10)

        self.chk_show_grid = ToggleSwitch("Show Ground Reference Grid")
        self.chk_show_grid.setChecked(self.settings.get("show_grid", True))
        form_grid.addRow(self.chk_show_grid)

        self.combo_grid_spacing = QComboBox()
        self.combo_grid_spacing.addItems(["250 mm", "500 mm (Default)", "1000 mm (1 m)", "2000 mm (2 m)"])
        cur_spacing = self.settings.get("grid_spacing", 500.0)
        spacing_map = {250.0: "250 mm", 500.0: "500 mm (Default)", 1000.0: "1000 mm (1 m)", 2000.0: "2000 mm (2 m)"}
        self.combo_grid_spacing.setCurrentText(spacing_map.get(cur_spacing, "500 mm (Default)"))
        form_grid.addRow("Grid Cell Spacing:", self.combo_grid_spacing)
        d_layout.addWidget(grp_grid)

        # Group 3: Primary Visual Elements
        grp_elements = QGroupBox("Primary Scene Elements Visibility")
        form_elem = QFormLayout(grp_elements)
        form_elem.setSpacing(8)

        self.chk_show_markers = ToggleSwitch("Show Optical Markers")
        self.chk_show_markers.setChecked(self.settings.get("show_markers", True))
        form_elem.addRow(self.chk_show_markers)

        self.chk_show_force_plates = ToggleSwitch("Show Force Platforms")
        self.chk_show_force_plates.setChecked(self.settings.get("show_force_plates", True))
        form_elem.addRow(self.chk_show_force_plates)

        self.chk_show_grf = ToggleSwitch("Show Ground Reaction Force (GRF) 3D Vectors")
        self.chk_show_grf.setChecked(self.settings.get("show_grf_vectors", True))
        form_elem.addRow(self.chk_show_grf)
        d_layout.addWidget(grp_elements)

        # Group 4: 2D Signal & Analog Plot Performance
        grp_plot_perf = QGroupBox("2D Signals & Plot Performance")
        form_perf = QFormLayout(grp_plot_perf)
        form_perf.setSpacing(8)

        self.chk_plot_antialias = ToggleSwitch("Enable Antialiasing on 2D Curves (Slower for >10k points)")
        self.chk_plot_antialias.setChecked(self.settings.get("plot_antialias", False))
        form_perf.addRow(self.chk_plot_antialias)
        d_layout.addWidget(grp_plot_perf)

        d_layout.addStretch()
        tabs.addTab(tab_display, "Display")

        # -------------------------------------------------------------
        # Tab 2: Coordinate System (Enhanced with axis thickness & visibility)
        # -------------------------------------------------------------
        tab_coord = QWidget()
        c_layout = QVBoxLayout(tab_coord)
        c_layout.setSpacing(12)

        # Group 1: Global Coordinate System Triad
        grp_global_axes = QGroupBox("Global Coordinate System (Lab Origin)")
        form_ga = QFormLayout(grp_global_axes)
        form_ga.setSpacing(10)

        self.chk_show_global_axes = ToggleSwitch("Show Global Coordinate System Triad (X, Y, Z)")
        self.chk_show_global_axes.setChecked(self.settings.get("show_global_axes", True))
        form_ga.addRow(self.chk_show_global_axes)

        self.spin_axis_thickness = QDoubleSpinBox()
        self.spin_axis_thickness.setRange(0.5, 12.0)
        self.spin_axis_thickness.setSingleStep(0.5)
        self.spin_axis_thickness.setValue(self.settings.get("axis_line_width", 2.0))
        self.spin_axis_thickness.setSuffix(" px")
        form_ga.addRow("Axes Line Thickness:", self.spin_axis_thickness)

        self.spin_axis_length = QDoubleSpinBox()
        self.spin_axis_length.setRange(100.0, 1000.0)
        self.spin_axis_length.setSingleStep(20.0)
        self.spin_axis_length.setValue(self.settings.get("axis_length", 320.0))
        self.spin_axis_length.setSuffix(" mm")
        form_ga.addRow("Axes Shaft Length:", self.spin_axis_length)
        c_layout.addWidget(grp_global_axes)

        # Group 2: Force Platform Local Coordinate Systems
        grp_plate_axes = QGroupBox("Force Platform Coordinate Systems")
        form_pa = QFormLayout(grp_plate_axes)
        form_pa.setSpacing(10)

        self.chk_show_plate_axes = ToggleSwitch("Show Force Plate Local Axes (X, Y, Z)")
        self.chk_show_plate_axes.setChecked(self.settings.get("show_plate_axes", True))
        form_pa.addRow(self.chk_show_plate_axes)
        c_layout.addWidget(grp_plate_axes)

        # Group 3: Orientation & Up Axis
        grp_orient = QGroupBox("Orientation & Gravity Axis")
        form_orient = QFormLayout(grp_orient)
        form_orient.setSpacing(10)

        self.combo_up_axis = QComboBox()
        self.combo_up_axis.addItems(["Z-Up (Standard C3D)", "Y-Up"])
        self.combo_up_axis.setCurrentIndex(0 if self.settings.get("z_up", True) else 1)
        form_orient.addRow("Global Up Axis:", self.combo_up_axis)

        self.combo_rotation = QComboBox()
        self.combo_rotation.addItems(["0° (Default)", "90°", "180°", "270°"])
        cur_rot = int(self.settings.get("ground_rotation", 0))
        rot_map = {0: "0° (Default)", 90: "90°", 180: "180°", 270: "270°"}
        if cur_rot in rot_map:
            self.combo_rotation.setCurrentText(rot_map[cur_rot])
        form_orient.addRow("Ground Orientation Rotation:", self.combo_rotation)
        c_layout.addWidget(grp_orient)

        c_layout.addStretch()
        tabs.addTab(tab_coord, "Coordinate System")

        # -------------------------------------------------------------
        # Tab 3: 3D Visuals (Marker Size, Color, GRF Parameters)
        # -------------------------------------------------------------
        tab_visual = QWidget()
        v_layout = QVBoxLayout(tab_visual)
        v_layout.setSpacing(12)

        grp_markers = QGroupBox("Optical Markers")
        form_m = QFormLayout(grp_markers)
        form_m.setSpacing(10)

        self.spin_marker_size = QDoubleSpinBox()
        self.spin_marker_size.setRange(2.0, 40.0)
        self.spin_marker_size.setSingleStep(1.0)
        self.spin_marker_size.setValue(self.settings.get("marker_size", 10.0))
        self.spin_marker_size.setSuffix(" px")
        form_m.addRow("Marker Point Size:", self.spin_marker_size)

        # Marker Color Controls with Color Picker
        color_layout = QHBoxLayout()
        color_layout.setSpacing(8)

        self.combo_marker_color = QComboBox()
        self.combo_marker_color.addItems([
            "Pure White", "Pitch Black", "Vivid Cyan", "Gold / Yellow",
            "Neon Coral", "Lime Green", "Custom Color..."
        ])
        cur_color_name = self.settings.get("marker_color_name")
        if not cur_color_name:
            cur_color_name = "Pitch Black" if self._marker_color_rgba[:3] == (0.0, 0.0, 0.0) else "Pure White"
        if cur_color_name in [self.combo_marker_color.itemText(i) for i in range(self.combo_marker_color.count())]:
            self.combo_marker_color.setCurrentText(cur_color_name)
        else:
            self.combo_marker_color.setCurrentText("Custom Color...")
        self.combo_marker_color.currentTextChanged.connect(self._on_marker_color_combo_changed)
        color_layout.addWidget(self.combo_marker_color, 1)

        self.btn_marker_swatch = QPushButton()
        self.btn_marker_swatch.setFixedSize(36, 26)
        self.btn_marker_swatch.setCursor(Qt.PointingHandCursor)
        self.btn_marker_swatch.setToolTip("Click to choose custom marker color")
        self.btn_marker_swatch.clicked.connect(self._pick_custom_marker_color)
        color_layout.addWidget(self.btn_marker_swatch)

        self.btn_pick_marker_color = QPushButton("Pick Color...")
        self.btn_pick_marker_color.setToolTip("Open color picker dialog")
        self.btn_pick_marker_color.clicked.connect(self._pick_custom_marker_color)
        color_layout.addWidget(self.btn_pick_marker_color)

        self._update_swatch_button()
        form_m.addRow("Default Marker Color:", color_layout)
        v_layout.addWidget(grp_markers)

        grp_grf = QGroupBox("Ground Reaction Force (GRF) Vectors")
        form_g = QFormLayout(grp_grf)
        form_g.setSpacing(10)

        self.spin_grf_scale = QDoubleSpinBox()
        self.spin_grf_scale.setRange(0.05, 10.0)
        self.spin_grf_scale.setSingleStep(0.1)
        self.spin_grf_scale.setValue(self.settings.get("grf_vector_scale", 0.8))
        self.spin_grf_scale.setSuffix(" mm / N")
        form_g.addRow("GRF Vector Scale:", self.spin_grf_scale)

        self.spin_grf_threshold = QDoubleSpinBox()
        self.spin_grf_threshold.setRange(1.0, 100.0)
        self.spin_grf_threshold.setSingleStep(2.0)
        self.spin_grf_threshold.setValue(self.settings.get("grf_threshold_n", 15.0))
        self.spin_grf_threshold.setSuffix(" N")
        form_g.addRow("Min Vertical Force Threshold:", self.spin_grf_threshold)

        # GRF Vector Color Controls with Color Picker
        grf_color_layout = QHBoxLayout()
        grf_color_layout.setSpacing(8)

        self.combo_grf_color = QComboBox()
        self.combo_grf_color.addItems([
            "Amber Orange (Default)", "Crimson Red", "Vivid Cyan",
            "Electric Yellow", "Neon Green", "Hot Magenta", "Custom Color..."
        ])
        cur_grf_name = self.settings.get("grf_color_name")
        if not cur_grf_name:
            cur_grf_name = "Amber Orange (Default)"
        if cur_grf_name in [self.combo_grf_color.itemText(i) for i in range(self.combo_grf_color.count())]:
            self.combo_grf_color.setCurrentText(cur_grf_name)
        else:
            self.combo_grf_color.setCurrentText("Custom Color...")
        self.combo_grf_color.currentTextChanged.connect(self._on_grf_color_combo_changed)
        grf_color_layout.addWidget(self.combo_grf_color, 1)

        self.btn_grf_swatch = QPushButton()
        self.btn_grf_swatch.setFixedSize(36, 26)
        self.btn_grf_swatch.setCursor(Qt.PointingHandCursor)
        self.btn_grf_swatch.setToolTip("Click to choose custom GRF vector color")
        self.btn_grf_swatch.clicked.connect(self._pick_custom_grf_color)
        grf_color_layout.addWidget(self.btn_grf_swatch)

        self.btn_pick_grf_color = QPushButton("Pick Color...")
        self.btn_pick_grf_color.setToolTip("Open color picker dialog for GRF vectors")
        self.btn_pick_grf_color.clicked.connect(self._pick_custom_grf_color)
        grf_color_layout.addWidget(self.btn_pick_grf_color)

        self._update_grf_swatch_button()
        form_g.addRow("GRF Vector Color:", grf_color_layout)
        v_layout.addWidget(grp_grf)

        v_layout.addStretch()
        tabs.addTab(tab_visual, "3D Visuals")

        # -------------------------------------------------------------
        # Tab 4: Playback
        # -------------------------------------------------------------
        tab_play = QWidget()
        p_layout = QVBoxLayout(tab_play)
        p_layout.setSpacing(12)

        grp_playback = QGroupBox("Playback Preferences")
        form_p = QFormLayout(grp_playback)
        form_p.setSpacing(10)

        self.combo_default_speed = QComboBox()
        self.combo_default_speed.addItems(["0.1x", "0.25x", "0.5x", "1.0x (Real-time)", "1.5x", "2.0x"])
        self.combo_default_speed.setCurrentText(self.settings.get("default_speed", "1.0x (Real-time)"))
        form_p.addRow("Default Playback Speed:", self.combo_default_speed)

        self.chk_loop = ToggleSwitch("Automatically loop playback when reaching end")
        self.chk_loop.setChecked(self.settings.get("loop", True))
        form_p.addRow(self.chk_loop)
        p_layout.addWidget(grp_playback)

        p_layout.addStretch()
        tabs.addTab(tab_play, "Playback")

        tabs.setCurrentIndex(max(0, min(tabs.count() - 1, self._initial_tab)))
        self.tabs = tabs
        layout.addWidget(tabs)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self._apply_settings)
        btn_box.addWidget(btn_apply)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.clicked.connect(self._ok_clicked)
        btn_box.addWidget(btn_ok)

        layout.addLayout(btn_box)

    PRESET_MARKER_COLORS = {
        "Pure White": (1.0, 1.0, 1.0, 1.0),
        "Pitch Black": (0.0, 0.0, 0.0, 1.0),
        "Vivid Cyan": (0.0, 0.85, 0.95, 1.0),
        "Gold / Yellow": (1.0, 0.84, 0.0, 1.0),
        "Neon Coral": (1.0, 0.35, 0.35, 1.0),
        "Lime Green": (0.2, 1.0, 0.4, 1.0),
    }

    PRESET_GRF_COLORS = {
        "Amber Orange (Default)": (1.0, 0.35, 0.08, 1.0),
        "Crimson Red": (0.95, 0.15, 0.15, 1.0),
        "Vivid Cyan": (0.0, 0.85, 0.95, 1.0),
        "Electric Yellow": (1.0, 0.85, 0.0, 1.0),
        "Neon Green": (0.1, 0.95, 0.3, 1.0),
        "Hot Magenta": (0.95, 0.1, 0.8, 1.0),
    }

    def _update_grf_swatch_button(self):
        hex_color = self._grf_color_qcolor.name()
        border_col = "#555555" if self._grf_color_qcolor.lightnessF() > 0.5 else "#888888"
        self.btn_grf_swatch.setStyleSheet(
            f"background-color: {hex_color}; border: 2px solid {border_col}; border-radius: 4px;"
        )

    def _set_grf_color(self, qcolor: QColor, name: Optional[str] = None):
        self._grf_color_qcolor = qcolor
        self._grf_color_rgba = (qcolor.redF(), qcolor.greenF(), qcolor.blueF(), 1.0)
        self._update_grf_swatch_button()

        if name is not None:
            self.combo_grf_color.blockSignals(True)
            idx = self.combo_grf_color.findText(name)
            if idx >= 0:
                self.combo_grf_color.setCurrentIndex(idx)
            else:
                self.combo_grf_color.setCurrentText("Custom Color...")
            self.combo_grf_color.blockSignals(False)
        else:
            matched_name = None
            for p_name, p_rgba in self.PRESET_GRF_COLORS.items():
                if (abs(p_rgba[0] - self._grf_color_rgba[0]) < 0.03 and
                    abs(p_rgba[1] - self._grf_color_rgba[1]) < 0.03 and
                    abs(p_rgba[2] - self._grf_color_rgba[2]) < 0.03):
                    matched_name = p_name
                    break
            self.combo_grf_color.blockSignals(True)
            self.combo_grf_color.setCurrentText(matched_name or "Custom Color...")
            self.combo_grf_color.blockSignals(False)

    def _on_grf_color_combo_changed(self, text: str):
        if text in self.PRESET_GRF_COLORS:
            rgba = self.PRESET_GRF_COLORS[text]
            qcol = QColor.fromRgbF(rgba[0], rgba[1], rgba[2], 1.0)
            self._grf_color_qcolor = qcol
            self._grf_color_rgba = rgba
            self._update_grf_swatch_button()
        elif text == "Custom Color...":
            self._pick_custom_grf_color()

    def _pick_custom_grf_color(self):
        col = QColorDialog.getColor(self._grf_color_qcolor, self, "Select Ground Reaction Force Color")
        if col.isValid():
            self._set_grf_color(col, name="Custom Color...")

    def _update_swatch_button(self):
        hex_color = self._marker_color_qcolor.name()
        border_col = "#555555" if self._marker_color_qcolor.lightnessF() > 0.5 else "#888888"
        self.btn_marker_swatch.setStyleSheet(
            f"background-color: {hex_color}; border: 2px solid {border_col}; border-radius: 4px;"
        )

    def _set_marker_color(self, qcolor: QColor, name: Optional[str] = None):
        self._marker_color_qcolor = qcolor
        self._marker_color_rgba = (qcolor.redF(), qcolor.greenF(), qcolor.blueF(), 1.0)
        self._update_swatch_button()

        if name is not None:
            self.combo_marker_color.blockSignals(True)
            idx = self.combo_marker_color.findText(name)
            if idx >= 0:
                self.combo_marker_color.setCurrentIndex(idx)
            else:
                self.combo_marker_color.setCurrentText("Custom Color...")
            self.combo_marker_color.blockSignals(False)
        else:
            matched_name = None
            for p_name, p_rgba in self.PRESET_MARKER_COLORS.items():
                if (abs(p_rgba[0] - self._marker_color_rgba[0]) < 0.03 and
                    abs(p_rgba[1] - self._marker_color_rgba[1]) < 0.03 and
                    abs(p_rgba[2] - self._marker_color_rgba[2]) < 0.03):
                    matched_name = p_name
                    break
            self.combo_marker_color.blockSignals(True)
            self.combo_marker_color.setCurrentText(matched_name or "Custom Color...")
            self.combo_marker_color.blockSignals(False)

    def _on_marker_color_combo_changed(self, text: str):
        if text in self.PRESET_MARKER_COLORS:
            rgba = self.PRESET_MARKER_COLORS[text]
            qcol = QColor.fromRgbF(rgba[0], rgba[1], rgba[2], 1.0)
            self._marker_color_qcolor = qcol
            self._marker_color_rgba = rgba
            self._update_swatch_button()
        elif text == "Custom Color...":
            self._pick_custom_marker_color()

    def _pick_custom_marker_color(self):
        col = QColorDialog.getColor(self._marker_color_qcolor, self, "Select Marker Color")
        if col.isValid():
            self._set_marker_color(col, name="Custom Color...")

    def _on_theme_changed(self, new_theme_name: str):
        theme_dict = get_theme(new_theme_name)
        is_dark = theme_dict.get("is_dark", True)
        if not is_dark:
            # Change marker color to black automatically when user chooses a light theme
            self._set_marker_color(QColor(0, 0, 0), name="Pitch Black")
        else:
            # If marker was black, restore to pure white for dark theme
            if self._marker_color_rgba[:3] == (0.0, 0.0, 0.0):
                self._set_marker_color(QColor(255, 255, 255), name="Pure White")

    def _collect_settings(self) -> dict:
        spacing_map = {
            "250 mm": 250.0,
            "500 mm (Default)": 500.0,
            "1000 mm (1 m)": 1000.0,
            "2000 mm (2 m)": 2000.0,
        }
        bg_choice = self.combo_viewport_bg.currentText()
        bg_color_map = {
            "Deep Charcoal (#151720)": "#151720",
            "Pure Black (#000000)": "#000000",
            "Slate Grey (#222733)": "#222733",
            "Laboratory Light (#EDF2F7)": "#EDF2F7",
            "Pure White (#FFFFFF)": "#FFFFFF",
        }

        return {
            # Display & Theme
            "theme": self.combo_theme.currentText(),
            "viewport_bg_choice": bg_choice,
            "viewport_bg": bg_color_map.get(bg_choice, None),  # None means use theme default
            "show_grid": self.chk_show_grid.isChecked(),
            "grid_spacing": spacing_map.get(self.combo_grid_spacing.currentText(), 500.0),
            "show_markers": self.chk_show_markers.isChecked(),
            "show_force_plates": self.chk_show_force_plates.isChecked(),
            "show_grf_vectors": self.chk_show_grf.isChecked(),
            "plot_antialias": self.chk_plot_antialias.isChecked(),

            # Coordinate System
            "show_global_axes": self.chk_show_global_axes.isChecked(),
            "axis_line_width": self.spin_axis_thickness.value(),
            "axis_length": self.spin_axis_length.value(),
            "show_plate_axes": self.chk_show_plate_axes.isChecked(),
            "z_up": self.combo_up_axis.currentIndex() == 0,
            "ground_rotation": [0.0, 90.0, 180.0, 270.0][max(0, min(3, self.combo_rotation.currentIndex()))],

            # 3D Visuals
            "marker_size": self.spin_marker_size.value(),
            "marker_color_name": self.combo_marker_color.currentText(),
            "marker_color": self._marker_color_rgba,
            "grf_vector_scale": self.spin_grf_scale.value(),
            "grf_threshold_n": self.spin_grf_threshold.value(),
            "grf_color_name": self.combo_grf_color.currentText(),
            "grf_color": self._grf_color_rgba,

            # Playback
            "default_speed": self.combo_default_speed.currentText(),
            "loop": self.chk_loop.isChecked(),
        }

    def _apply_settings(self):
        self.settings = self._collect_settings()
        self.settingsApplied.emit(self.settings)

    def _ok_clicked(self):
        self._apply_settings()
        self.accept()

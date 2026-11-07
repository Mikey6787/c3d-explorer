"""
Force Plate Configuration & Ground Reaction Force (GRF) Calculation Dialog.

Provides two modes for calculating Ground Reaction Forces (Fx, Fy, Fz),
Moments (Mx, My, Mz), and Center of Pressure (COP) from analog channels:
1. Automatic Calculation (Shimba 1984):
   Uses embedded C3D force platform parameters and analog channels automatically.
2. Custom / Manual Configuration:
   Allows specifying the 4 force plate corners, the center/origin offset (in X, Y, Z,
   including shifting the coordinate system to one corner of the force plate),
   the 6x6 calibration matrix (with diagonal Fx, Fy, Fz, Mx, My, Mz), and analog
   channel mappings to calculate new forces from the analog data.
"""

from typing import Dict, List, Optional, Tuple, Any
import os
import csv
import json
import numpy as np

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QRadioButton, QButtonGroup, QComboBox, QDoubleSpinBox,
    QAbstractSpinBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QCheckBox, QScrollArea, QWidget, QFrame, QFileDialog,
    QMessageBox, QStackedWidget
)

from core.data_models import C3DTrial, ForcePlatformData
from core.grw_calculator import (
    compute_ground_reaction_wrenches,
    compute_single_plate_grw,
    extract_plate_analog_matrix
)


MATRIX_LABELS_6 = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]
CHANNEL_LABELS_8 = ["Fx12", "Fx34", "Fy14", "Fy23", "Fz1", "Fz2", "Fz3", "Fz4"]


class NumericLineEdit(QLineEdit):
    """Clean numeric text input without spinbox up/down buttons, compatible with QDoubleSpinBox API."""
    valueChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_val: float = -1e9
        self._max_val: float = 1e9
        self._decimals: int = 2
        self._step: float = 1.0
        self._suffix: str = ""
        self._value: float = 0.0
        self._formatting: bool = False
        self._update_display_text()
        self.textEdited.connect(self._on_text_edited)
        self.editingFinished.connect(self._on_editing_finished)

    def setButtonSymbols(self, _symbols):
        pass

    def setRange(self, minimum: float, maximum: float):
        self._min_val = float(minimum)
        self._max_val = float(maximum)

    def setDecimals(self, decimals: int):
        self._decimals = max(0, int(decimals))
        self._update_display_text()

    def setSingleStep(self, step: float):
        self._step = float(step)

    def setSuffix(self, suffix: str):
        self._suffix = str(suffix)

    def value(self) -> float:
        txt = self.text().strip().replace(",", ".")
        if self._suffix and txt.endswith(self._suffix.strip()):
            txt = txt[: -len(self._suffix.strip())].strip()
        try:
            v = float(txt)
            return float(np.clip(v, self._min_val, self._max_val))
        except ValueError:
            return self._value

    def setValue(self, val: float):
        clamped = float(np.clip(float(val), self._min_val, self._max_val))
        changed = abs(clamped - self._value) > 1e-9
        self._value = clamped
        self._update_display_text()
        if changed:
            self.valueChanged.emit(self._value)

    def _update_display_text(self):
        self._formatting = True
        try:
            self.setText(f"{self._value:.{self._decimals}f}")
        finally:
            self._formatting = False

    def _on_text_edited(self, txt: str):
        if self._formatting:
            return
        clean = txt.strip().replace(",", ".")
        try:
            v = float(clean)
            self._value = float(np.clip(v, self._min_val, self._max_val))
            self.valueChanged.emit(self._value)
        except ValueError:
            pass

    def _on_editing_finished(self):
        self._value = self.value()
        self._update_display_text()
        self.valueChanged.emit(self._value)


class ForcePlateDialog(QDialog):
    """
    Interactive Force Plate Configuration and Calculation Window.
    Accessible via Tools -> Force Plate...
    """

    forcePlatesChanged = Signal(list, list, str, dict)
    # Emits (old_force_platforms, new_force_platforms, description, pipeline_params)

    def __init__(self, trial: C3DTrial, parent=None):
        super().__init__(parent)
        self.trial = trial
        self.setWindowTitle("Force Plate Configuration & Calculation")
        self.resize(880, 760)

        self._updating_ui = True
        self._current_loaded_plate_idx: int = -1
        self._plate_ui_states: Dict[str, Dict[str, Any]] = {}

        if self.trial and not hasattr(self.trial, "_c3d_default_force_platforms"):
            self.trial._c3d_default_force_platforms = [
                fp.clone() for fp in (self.trial.force_platforms or [])
            ]

        self._initial_snapshots: List[ForcePlatformData] = [
            fp.clone() for fp in (self.trial.force_platforms if self.trial else [])
        ]

        try:
            self._load_persisted_state_dict()
            self._setup_ui()
            self._populate_plate_selector()
            self._restore_mode_and_plate_selection()
        finally:
            self._updating_ui = False

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Top Bar: Force Plate Selector
        top_group = QGroupBox("Target Force Platform")
        top_layout = QHBoxLayout(top_group)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(10)

        top_layout.addWidget(QLabel("<b>Select Force Plate:</b>"))
        self.combo_plate = QComboBox()
        self.combo_plate.setMinimumWidth(240)
        self.combo_plate.currentIndexChanged.connect(self._on_plate_selection_changed)
        top_layout.addWidget(self.combo_plate, stretch=1)

        main_layout.addWidget(top_group)

        # 2. Calculation Mode Selection (Option 1 vs Option 2)
        mode_group = QGroupBox("Calculation Method")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(10, 8, 10, 8)
        mode_layout.setSpacing(6)

        self.mode_btn_group = QButtonGroup(self)
        self.rb_auto = QRadioButton("Automatic calculation (Shimba 1984)")
        self.rb_auto.setStyleSheet("font-weight: 600;")
        self.rb_custom = QRadioButton("Manual calculation")
        self.rb_custom.setStyleSheet("font-weight: 600;")

        self.mode_btn_group.addButton(self.rb_auto, 0)
        self.mode_btn_group.addButton(self.rb_custom, 1)
        self.rb_auto.setChecked(True)

        self.rb_auto.toggled.connect(self._on_mode_toggled)
        self.rb_custom.toggled.connect(self._on_mode_toggled)

        mode_layout.addWidget(self.rb_auto)
        mode_layout.addWidget(self.rb_custom)
        main_layout.addWidget(mode_group)

        # 3. Stacked / Scrollable Content Area for Option 1 and Option 2
        self.stack = QStackedWidget(self)

        # --- Page 0: Option 1 (Automatic Shimba Calculation) ---
        self.page_auto = QWidget()
        self._setup_auto_page(self.page_auto)
        self.stack.addWidget(self.page_auto)

        # --- Page 1: Option 2 (Custom Corners, Offset, Calibration Matrix) ---
        self.page_custom_scroll = QScrollArea()
        self.page_custom_scroll.setWidgetResizable(True)
        self.page_custom_scroll.setFrameShape(QFrame.NoFrame)
        self.page_custom = QWidget()
        self._setup_custom_page(self.page_custom)
        self.page_custom_scroll.setWidget(self.page_custom)
        self.stack.addWidget(self.page_custom_scroll)

        main_layout.addWidget(self.stack, stretch=1)

        # 4. Dialog Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        self.btn_reset_c3d = QPushButton("Reset to C3D Defaults")
        self.btn_reset_c3d.setToolTip("Reload original C3D parameters for this force plate")
        self.btn_reset_c3d.clicked.connect(self._reset_current_plate_to_c3d)
        footer_layout.addWidget(self.btn_reset_c3d)

        footer_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_close)

        self.btn_calculate = QPushButton("Calculate && Apply Forces")
        self.btn_calculate.setObjectName("primaryBtn")
        self.btn_calculate.setMinimumWidth(190)
        self.btn_calculate.setFixedHeight(34)
        self.btn_calculate.clicked.connect(self.apply_calculation)
        footer_layout.addWidget(self.btn_calculate)

        main_layout.addLayout(footer_layout)

    def _setup_auto_page(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        self.spin_auto_threshold = NumericLineEdit()
        self.spin_auto_threshold.setRange(0.0, 500.0)
        self.spin_auto_threshold.setDecimals(1)
        self.spin_auto_threshold.setSingleStep(1.0)
        self.spin_auto_threshold.setValue(10.0)

        self.chk_auto_all_plates = QCheckBox()
        self.chk_auto_all_plates.setChecked(True)

        self.lbl_auto_plate_info = QLabel("")

    def _setup_custom_page(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        unit = getattr(self.trial, "marker_units", "mm") if self.trial else "mm"

        # --- Section A: Force Plate Type & Threshold ---
        type_group = QGroupBox("1. Force Plate Type && Analog Channels")
        type_vlayout = QVBoxLayout(type_group)
        type_vlayout.setSpacing(8)

        type_top_row = QHBoxLayout()
        type_top_row.addWidget(QLabel("<b>Force Plate Type:</b>"))
        self.combo_type = QComboBox()
        self.combo_type.addItem("Type 4 — 6×6 Calibration Matrix (Fx, Fy, Fz, Mx, My, Mz)", 4)
        self.combo_type.addItem("Type 2 — 6-Channel Strain Gauge (Fx, Fy, Fz, Mx, My, Mz)", 2)
        self.combo_type.addItem("Type 3 — 8-Channel Kistler Piezoelectric", 3)
        self.combo_type.addItem("Type 1 — 6-Channel (Fx, Fy, Fz, Px, Py, Mz)", 1)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        type_top_row.addWidget(self.combo_type, stretch=1)

        type_top_row.addSpacing(12)
        type_top_row.addWidget(QLabel("<b>COP Threshold (N):</b>"))
        self.spin_custom_threshold = NumericLineEdit()
        self.spin_custom_threshold.setRange(0.0, 500.0)
        self.spin_custom_threshold.setDecimals(1)
        self.spin_custom_threshold.setValue(10.0)
        self.spin_custom_threshold.setSuffix(" N")
        self.spin_custom_threshold.setMaximumWidth(90)
        self.spin_custom_threshold.valueChanged.connect(self._on_any_manual_field_changed)
        type_top_row.addWidget(self.spin_custom_threshold)
        type_vlayout.addLayout(type_top_row)

        # Analog Channel Selectors (6 or 8 channels)
        ch_grid = QGridLayout()
        ch_grid.setSpacing(6)
        self.channel_labels: List[QLabel] = []
        self.channel_combos: List[QComboBox] = []
        analog_names = list(self.trial.analogs.keys()) if (self.trial and self.trial.analogs) else []

        for i in range(8):
            lbl_text = MATRIX_LABELS_6[i] if i < 6 else CHANNEL_LABELS_8[i]
            lbl = QLabel(f"<b>{lbl_text}:</b>")
            combo = QComboBox()
            combo.addItem("-- None --", "")
            for a_name in analog_names:
                combo.addItem(a_name, a_name)
            combo.currentIndexChanged.connect(self._on_any_manual_field_changed)
            r = i // 4
            c = (i % 4) * 2
            ch_grid.addWidget(lbl, r, c)
            ch_grid.addWidget(combo, r, c + 1)
            self.channel_labels.append(lbl)
            self.channel_combos.append(combo)

        type_vlayout.addLayout(ch_grid)
        layout.addWidget(type_group)

        # --- Section B: Force Plate Corners (4 Corners in 3D) ---
        corners_group = QGroupBox(f"2. Force Plate Corners (Global X, Y, Z in {unit})")
        corners_layout = QVBoxLayout(corners_group)
        corners_layout.setSpacing(6)

        corners_grid = QGridLayout()
        corners_grid.setSpacing(6)
        corners_grid.addWidget(QLabel("<b>Corner</b>"), 0, 0)
        corners_grid.addWidget(QLabel(f"<b>X ({unit})</b>"), 0, 1)
        corners_grid.addWidget(QLabel(f"<b>Y ({unit})</b>"), 0, 2)
        corners_grid.addWidget(QLabel(f"<b>Z ({unit})</b>"), 0, 3)

        corner_titles = [
            "Corner 1 (+X, +Y):",
            "Corner 2 (-X, +Y):",
            "Corner 3 (-X, -Y):",
            "Corner 4 (+X, -Y):"
        ]
        self.corner_spins: List[List[NumericLineEdit]] = []
        for c_idx in range(4):
            corners_grid.addWidget(QLabel(corner_titles[c_idx]), c_idx + 1, 0)
            row_spins = []
            for ax_idx in range(3):
                sp = NumericLineEdit()
                sp.setRange(-100000.0, 100000.0)
                sp.setDecimals(2)
                sp.setSingleStep(10.0)
                sp.valueChanged.connect(self._on_corners_edited)
                corners_grid.addWidget(sp, c_idx + 1, ax_idx + 1)
                row_spins.append(sp)
            self.corner_spins.append(row_spins)

        corners_layout.addLayout(corners_grid)

        self.lbl_geometric_center = QLabel("Geometric Center: [0.00, 0.00, 0.00] | Size: 0.0 × 0.0")
        self.lbl_geometric_center.setStyleSheet("color: #00ADB5; font-weight: 600; font-size: 11px;")
        corners_layout.addWidget(self.lbl_geometric_center)
        layout.addWidget(corners_group)

        # --- Section C: Center / Origin Offset ---
        offset_group = QGroupBox(f"3. Force Plate Center / Origin Offset (X, Y, Z in {unit})")
        offset_layout = QVBoxLayout(offset_group)
        offset_layout.setSpacing(6)

        offset_spin_row = QHBoxLayout()
        offset_spin_row.setSpacing(10)

        self.spin_offset_x = NumericLineEdit()
        self.spin_offset_x.setRange(-100000.0, 100000.0)
        self.spin_offset_x.setDecimals(2)
        self.spin_offset_x.setSingleStep(5.0)
        self.spin_offset_x.setSuffix(f" {unit}")
        self.spin_offset_x.valueChanged.connect(self._on_any_manual_field_changed)

        self.spin_offset_y = NumericLineEdit()
        self.spin_offset_y.setRange(-100000.0, 100000.0)
        self.spin_offset_y.setDecimals(2)
        self.spin_offset_y.setSingleStep(5.0)
        self.spin_offset_y.setSuffix(f" {unit}")
        self.spin_offset_y.valueChanged.connect(self._on_any_manual_field_changed)

        self.spin_offset_z = NumericLineEdit()
        self.spin_offset_z.setRange(-100000.0, 100000.0)
        self.spin_offset_z.setDecimals(2)
        self.spin_offset_z.setSingleStep(1.0)
        self.spin_offset_z.setSuffix(f" {unit}")
        self.spin_offset_z.valueChanged.connect(self._on_any_manual_field_changed)

        offset_spin_row.addWidget(QLabel("<b>Offset X:</b>"))
        offset_spin_row.addWidget(self.spin_offset_x, stretch=1)
        offset_spin_row.addWidget(QLabel("<b>Offset Y:</b>"))
        offset_spin_row.addWidget(self.spin_offset_y, stretch=1)
        offset_spin_row.addWidget(QLabel("<b>Offset Z (Depth):</b>"))
        offset_spin_row.addWidget(self.spin_offset_z, stretch=1)

        offset_layout.addLayout(offset_spin_row)
        layout.addWidget(offset_group)

        # --- Section D: Calibration Matrix (6x6 Matrix with Diagonal Fx, Fy, Fz, Mx, My, Mz) ---
        self.cal_group = QGroupBox("4. Calibration Matrix (6×6 — Diagonal: Fx, Fy, Fz, Mx, My, Mz)")
        cal_layout = QVBoxLayout(self.cal_group)
        cal_layout.setSpacing(8)

        # Full 6x6 Matrix Table
        self.table_cal_matrix = QTableWidget(6, 6)
        self.table_cal_matrix.setHorizontalHeaderLabels(MATRIX_LABELS_6)
        self.table_cal_matrix.setVerticalHeaderLabels(MATRIX_LABELS_6)
        self.table_cal_matrix.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_cal_matrix.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_cal_matrix.setMinimumHeight(195)
        self.table_cal_matrix.itemChanged.connect(self._on_any_manual_field_changed)
        cal_layout.addWidget(self.table_cal_matrix)

        layout.addWidget(self.cal_group)

        # Initialize 6x6 matrix to identity
        self.set_calibration_matrix(np.eye(6, dtype=np.float64))

    # ------------------------------------------------------------------
    # Data Population & State Synchronization
    # ------------------------------------------------------------------
    def _should_use_qsettings(self) -> bool:
        if self.trial and getattr(self.trial, "_persist_qsettings", False):
            return True
        return os.environ.get("QT_QPA_PLATFORM") != "offscreen"

    def _load_persisted_state_dict(self):
        """Load saved Force Plate dialog settings from trial memory or QSettings."""
        self._saved_mode: str = "auto"
        self._saved_plate_idx: int = 0
        self._plate_ui_states = {}

        state = getattr(self.trial, "_fp_dialog_state", None) if self.trial else None
        if state is None and self._should_use_qsettings():
            try:
                settings = QSettings("C3DExplorer", "C3DExplorer")
                raw_json = settings.value("force_plate/user_settings_json", "")
                if raw_json and isinstance(raw_json, str):
                    state = json.loads(raw_json)
            except Exception:
                state = None

        if isinstance(state, dict):
            self._saved_mode = str(state.get("mode", "auto"))
            try:
                self._saved_plate_idx = int(state.get("selected_plate_idx", 0))
            except (ValueError, TypeError):
                self._saved_plate_idx = 0
            plates_dict = state.get("plates", {})
            if isinstance(plates_dict, dict):
                self._plate_ui_states = {str(k): dict(v) for k, v in plates_dict.items() if isinstance(v, dict)}

    def _restore_mode_and_plate_selection(self):
        """Restore the previously selected calculation mode and target force plate."""
        was_updating = self._updating_ui
        self._updating_ui = True
        try:
            if self._saved_mode == "manual":
                self.rb_custom.setChecked(True)
                self.stack.setCurrentIndex(1)
            else:
                self.rb_auto.setChecked(True)
                self.stack.setCurrentIndex(0)

            if self.trial and self.trial.force_platforms:
                target_idx = max(0, min(len(self.trial.force_platforms) - 1, self._saved_plate_idx))
                self.combo_plate.setCurrentIndex(target_idx)
        finally:
            self._updating_ui = was_updating

        if self.trial and self.trial.force_platforms:
            target_idx = max(0, min(len(self.trial.force_platforms) - 1, self._saved_plate_idx))
            self._load_plate_into_ui(target_idx)

    def _capture_current_plate_ui_state(self):
        """Record the current UI input values for the currently loaded force plate."""
        if self._updating_ui or not self.trial or not self.trial.force_platforms:
            return
        idx = self._current_loaded_plate_idx
        if idx < 0 or idx >= len(self.trial.force_platforms):
            idx = self.get_current_plate_index()
        if idx < 0 or idx >= len(self.trial.force_platforms):
            return

        fp = self.trial.force_platforms[idx]
        self._plate_ui_states[str(fp.id)] = {
            "type": int(self.combo_type.currentData() or 4),
            "threshold": float(self.spin_custom_threshold.value()),
            "corners": self.get_corners_array().tolist(),
            "offset": self.get_origin_offset().tolist(),
            "cal_matrix": self.get_calibration_matrix().tolist(),
            "channel_names": self.get_selected_channel_names(),
        }

    def _save_persisted_state_dict(self):
        """Persist the Force Plate dialog settings in trial memory and QSettings."""
        if self._updating_ui:
            return
        self._capture_current_plate_ui_state()
        state = {
            "mode": "manual" if self.rb_custom.isChecked() else "auto",
            "selected_plate_idx": max(0, self.get_current_plate_index()),
            "plates": self._plate_ui_states,
        }
        if self.trial is not None:
            self.trial._fp_dialog_state = state
        if self._should_use_qsettings():
            try:
                settings = QSettings("C3DExplorer", "C3DExplorer")
                settings.setValue("force_plate/user_settings_json", json.dumps(state))
                settings.sync()
            except Exception:
                pass

    def _on_any_manual_field_changed(self, *_args):
        if self._updating_ui:
            return
        self._save_persisted_state_dict()

    def done(self, result: int):
        self._save_persisted_state_dict()
        super().done(result)

    def closeEvent(self, event):
        self._save_persisted_state_dict()
        super().closeEvent(event)

    def _populate_plate_selector(self):
        was_updating = self._updating_ui
        self._updating_ui = True
        try:
            self.combo_plate.clear()
            if self.trial and self.trial.force_platforms:
                for i, fp in enumerate(self.trial.force_platforms):
                    self.combo_plate.addItem(f"Force Platform #{fp.id} (Type {fp.type})", i)
            else:
                self.combo_plate.addItem("No Force Platforms in Trial", -1)
        finally:
            self._updating_ui = was_updating

        if self.trial and self.trial.force_platforms:
            self._load_plate_into_ui(0)
        else:
            self._update_auto_info_label(None)

    def get_current_plate_index(self) -> int:
        if not self.trial or not self.trial.force_platforms:
            return -1
        idx = self.combo_plate.currentData()
        if idx is None or idx < 0 or idx >= len(self.trial.force_platforms):
            return 0
        return int(idx)

    def get_current_plate(self) -> Optional[ForcePlatformData]:
        idx = self.get_current_plate_index()
        if 0 <= idx < len(self.trial.force_platforms):
            return self.trial.force_platforms[idx]
        return None

    def _on_plate_selection_changed(self, _index: int):
        if self._updating_ui:
            return
        self._capture_current_plate_ui_state()
        fp_idx = self.get_current_plate_index()
        if fp_idx >= 0:
            self._load_plate_into_ui(fp_idx)
        self._save_persisted_state_dict()

    def _on_mode_toggled(self):
        if self.rb_auto.isChecked():
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)
        if not self._updating_ui:
            self._save_persisted_state_dict()

    def _on_type_changed(self):
        fp_type = int(self.combo_type.currentData() or 4)
        is_8ch = (fp_type == 3)
        for i in range(8):
            if i < 6:
                lbl_txt = CHANNEL_LABELS_8[i] if is_8ch else MATRIX_LABELS_6[i]
                self.channel_labels[i].setText(f"<b>{lbl_txt}:</b>")
                self.channel_labels[i].setVisible(True)
                self.channel_combos[i].setVisible(True)
            else:
                self.channel_labels[i].setVisible(is_8ch)
                self.channel_combos[i].setVisible(is_8ch)
        if not self._updating_ui:
            self._save_persisted_state_dict()

    def _load_plate_into_ui(self, fp_idx: int):
        if not self.trial or fp_idx < 0 or fp_idx >= len(self.trial.force_platforms):
            return

        fp = self.trial.force_platforms[fp_idx]
        saved_plate = self._plate_ui_states.get(str(fp.id))
        self._current_loaded_plate_idx = fp_idx
        was_updating = self._updating_ui
        self._updating_ui = True
        try:
            # 1. Type selector & Threshold
            target_type = int(saved_plate.get("type", fp.type)) if saved_plate else int(fp.type)
            type_idx = self.combo_type.findData(target_type)
            if type_idx >= 0:
                self.combo_type.setCurrentIndex(type_idx)
            else:
                self.combo_type.setCurrentIndex(0)  # Default Type 4
            self._on_type_changed()

            if saved_plate and "threshold" in saved_plate:
                self.spin_custom_threshold.setValue(float(saved_plate["threshold"]))

            # 2. Corners (shape 3x4)
            if saved_plate and "corners" in saved_plate:
                corners = np.asarray(saved_plate["corners"], dtype=np.float64).reshape(3, 4)
            else:
                corners = fp.corners if (fp.corners is not None and fp.corners.shape == (3, 4)) else np.zeros((3, 4))
            for c_idx in range(4):
                for ax_idx in range(3):
                    self.corner_spins[c_idx][ax_idx].setValue(float(corners[ax_idx, c_idx]))

            # 3. Origin / Center Offset
            if saved_plate and "offset" in saved_plate and len(saved_plate["offset"]) >= 3:
                off_arr = saved_plate["offset"]
                self.spin_offset_x.setValue(float(off_arr[0]))
                self.spin_offset_y.setValue(float(off_arr[1]))
                self.spin_offset_z.setValue(float(off_arr[2]))
            else:
                origin = fp.origin if (fp.origin is not None and len(fp.origin) >= 3) else np.zeros(3)
                c_off = getattr(fp, "coord_offset", None)
                if c_off is not None and len(c_off) >= 3:
                    self.spin_offset_x.setValue(float(c_off[0]))
                    self.spin_offset_y.setValue(float(c_off[1]))
                    self.spin_offset_z.setValue(float(c_off[2]))
                else:
                    self.spin_offset_x.setValue(float(origin[0]))
                    self.spin_offset_y.setValue(float(origin[1]))
                    self.spin_offset_z.setValue(float(origin[2]))

            # 4. Calibration Matrix (6x6)
            if saved_plate and "cal_matrix" in saved_plate:
                self.set_calibration_matrix(np.asarray(saved_plate["cal_matrix"], dtype=np.float64))
            elif fp.cal_matrix is not None and fp.cal_matrix.shape[0] >= 6 and fp.cal_matrix.shape[1] >= 6:
                self.set_calibration_matrix(fp.cal_matrix[:6, :6])
            else:
                self.set_calibration_matrix(np.eye(6, dtype=np.float64))

            # 5. Analog Channels mapping
            _, resolved_names = extract_plate_analog_matrix(self.trial, fp)
            if saved_plate and saved_plate.get("channel_names"):
                saved_ch = [str(c) for c in saved_plate["channel_names"]]
                if any(c in (self.trial.analogs or {}) for c in saved_ch if c):
                    resolved_names = saved_ch
            analog_keys = list(self.trial.analogs.keys()) if self.trial.analogs else []
            for i, combo in enumerate(self.channel_combos):
                if i < len(resolved_names) and resolved_names[i] in analog_keys:
                    idx = combo.findData(resolved_names[i])
                    combo.setCurrentIndex(max(0, idx))
                elif i < len(analog_keys):
                    combo.setCurrentIndex(0)
                else:
                    combo.setCurrentIndex(0)

            self._update_geometric_center_label()
            self._update_auto_info_label(fp)
        finally:
            self._updating_ui = was_updating

    def _update_auto_info_label(self, fp: Optional[ForcePlatformData]):
        if fp is None:
            self.lbl_auto_plate_info.setText("No force platform currently defined in trial.")
            return
        unit = getattr(self.trial, "marker_units", "mm") if self.trial else "mm"
        c = fp.center
        has_cal = fp.cal_matrix is not None and not np.all(fp.cal_matrix == 0)
        cal_str = f"{fp.cal_matrix.shape[0]}×{fp.cal_matrix.shape[1]} Matrix" if has_cal else "Identity / Unscaled"
        _, ch_names = extract_plate_analog_matrix(self.trial, fp)
        ch_str = ", ".join(ch_names) if ch_names else "None"
        self.lbl_auto_plate_info.setText(
            f"<b>Force Platform #{fp.id}</b> &nbsp;|&nbsp; <b>Type:</b> {fp.type} &nbsp;|&nbsp; "
            f"<b>Calibration:</b> {cal_str}<br>"
            f"<b>Size:</b> {fp.width:.1f} × {fp.length:.1f} {unit} &nbsp;|&nbsp; "
            f"<b>Geometric Center:</b> [{c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f}] {unit}<br>"
            f"<b>Origin / Offset:</b> [{fp.origin[0]:.2f}, {fp.origin[1]:.2f}, {fp.origin[2]:.2f}] {unit}<br>"
            f"<b>Mapped Analog Channels:</b> {ch_str}"
        )

    # ------------------------------------------------------------------
    # Corners & Coordinate Offset Helpers
    # ------------------------------------------------------------------
    def get_corners_array(self) -> np.ndarray:
        """Return (3, 4) float32 array of the 4 corners from the UI spinboxes."""
        corners = np.zeros((3, 4), dtype=np.float32)
        for c_idx in range(4):
            for ax_idx in range(3):
                corners[ax_idx, c_idx] = float(self.corner_spins[c_idx][ax_idx].value())
        return corners

    def set_corners_array(self, corners: np.ndarray):
        """Set the 4 corner spinboxes from a (3, 4) array."""
        c_arr = np.asarray(corners, dtype=np.float64).reshape(3, 4)
        was_updating = self._updating_ui
        self._updating_ui = True
        try:
            for c_idx in range(4):
                for ax_idx in range(3):
                    self.corner_spins[c_idx][ax_idx].setValue(float(c_arr[ax_idx, c_idx]))
        finally:
            self._updating_ui = was_updating
        self._update_geometric_center_label()
        if not self._updating_ui:
            self._save_persisted_state_dict()

    def _on_corners_edited(self):
        if self._updating_ui:
            return
        self._update_geometric_center_label()
        self._save_persisted_state_dict()

    def _update_geometric_center_label(self):
        corners = self.get_corners_array()
        center = np.mean(corners, axis=1)
        width = float(np.linalg.norm(corners[:, 1] - corners[:, 0]))
        length = float(np.linalg.norm(corners[:, 2] - corners[:, 1]))
        unit = getattr(self.trial, "marker_units", "mm") if self.trial else "mm"
        self.lbl_geometric_center.setText(
            f"Geometric Center: [{center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f}] {unit}  |  "
            f"Dimensions: {width:.1f} × {length:.1f} {unit}"
        )

    def apply_corner_offset_preset(self, corner_number: int):
        """
        Compute and set the X and Y offset in the force plate's local coordinate system
        to place the origin at the Plate Center (0) or at Corner 1, 2, 3, or 4.
        """
        if corner_number == 0:
            self.spin_offset_x.setValue(0.0)
            self.spin_offset_y.setValue(0.0)
            return

        corners = self.get_corners_array().astype(np.float64)
        c0, c1, c2, c3 = corners[:, 0], corners[:, 1], corners[:, 2], corners[:, 3]
        center = np.mean(corners, axis=1)

        # Local unit vectors matching Shimba / force plate local frame
        r0 = c0 - c1
        n0 = np.linalg.norm(r0)
        r0 = r0 / n0 if n0 > 1e-6 else np.array([1.0, 0.0, 0.0])

        r2 = np.cross(r0, c0 - c3)
        n2 = np.linalg.norm(r2)
        r2 = r2 / n2 if n2 > 1e-6 else np.array([0.0, 0.0, 1.0])

        r1 = np.cross(r2, r0)

        idx = max(0, min(3, corner_number - 1))
        vec_from_center = corners[:, idx] - center
        local_x_offset = float(np.dot(vec_from_center, r0))
        local_y_offset = float(np.dot(vec_from_center, r1))

        self.spin_offset_x.setValue(local_x_offset)
        self.spin_offset_y.setValue(local_y_offset)

    def get_origin_offset(self) -> np.ndarray:
        """Return (3,) float32 array [offset_x, offset_y, offset_z]."""
        return np.array([
            float(self.spin_offset_x.value()),
            float(self.spin_offset_y.value()),
            float(self.spin_offset_z.value())
        ], dtype=np.float32)

    def set_origin_offset(self, ox: float, oy: float, oz: float = 0.0):
        """Programmatically set the X, Y, Z center/origin offset spinboxes."""
        self.spin_offset_x.setValue(float(ox))
        self.spin_offset_y.setValue(float(oy))
        self.spin_offset_z.setValue(float(oz))

    # ------------------------------------------------------------------
    # 6x6 Calibration Matrix Helpers
    # ------------------------------------------------------------------
    def set_calibration_matrix(self, matrix: np.ndarray):
        """Populate the 6x6 calibration matrix table."""
        mat = np.zeros((6, 6), dtype=np.float64)
        src = np.asarray(matrix, dtype=np.float64)
        r = min(6, src.shape[0])
        c = min(6, src.shape[1])
        mat[:r, :c] = src[:r, :c]

        was_updating = self._updating_ui
        self._updating_ui = True
        try:
            self.table_cal_matrix.blockSignals(True)
            for i in range(6):
                for j in range(6):
                    val_str = f"{mat[i, j]:.6g}"
                    item = self.table_cal_matrix.item(i, j)
                    if item is None:
                        item = QTableWidgetItem(val_str)
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        self.table_cal_matrix.setItem(i, j, item)
                    else:
                        item.setText(val_str)

                    if i == j:
                        # Highlight diagonal (Fx, Fy, Fz, Mx, My, Mz)
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)
                        item.setForeground(QBrush(QColor("#00E5FF")))
                        item.setToolTip(f"Diagonal sensitivity for {MATRIX_LABELS_6[i]}")
                    else:
                        font = QFont()
                        font.setBold(False)
                        item.setFont(font)
                        item.setToolTip(f"Cross-talk ({MATRIX_LABELS_6[i]}, {MATRIX_LABELS_6[j]})")
            self.table_cal_matrix.blockSignals(False)
        finally:
            self._updating_ui = was_updating
        if not self._updating_ui:
            self._save_persisted_state_dict()

    def get_calibration_matrix(self) -> np.ndarray:
        """Read and return the 6x6 calibration matrix from the UI table."""
        mat = np.zeros((6, 6), dtype=np.float64)
        for i in range(6):
            for j in range(6):
                item = self.table_cal_matrix.item(i, j)
                if item is not None:
                    txt = item.text().strip().replace(",", ".")
                    try:
                        mat[i, j] = float(txt)
                    except ValueError:
                        mat[i, j] = 1.0 if i == j else 0.0
                else:
                    mat[i, j] = 1.0 if i == j else 0.0
        return mat

    def set_calibration_diagonal(self, diag_values: List[float]):
        """Set the 6 diagonal values (Fx, Fy, Fz, Mx, My, Mz) of the 6x6 calibration matrix."""
        mat = self.get_calibration_matrix()
        for i in range(min(6, len(diag_values))):
            mat[i, i] = float(diag_values[i])
        self.set_calibration_matrix(mat)

    def set_identity_calibration_matrix(self):
        """Reset the 6x6 calibration matrix to Identity (diagonal = 1, off-diagonal = 0)."""
        self.set_calibration_matrix(np.eye(6, dtype=np.float64))

    def clear_off_diagonal_matrix(self):
        """Zero all off-diagonal terms while preserving the diagonal (Fx, Fy, Fz, Mx, My, Mz)."""
        mat = self.get_calibration_matrix()
        diag = np.diag(np.diag(mat))
        self.set_calibration_matrix(diag)

    def _import_matrix_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import 6×6 Calibration Matrix",
            "",
            "Matrix Files (*.csv *.txt *.tsv);;All Files (*)"
        )
        if not path or not os.path.isfile(path):
            return
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.replace(";", ",").replace("\t", ",").split(",") if p.strip()]
                    if len(parts) < 6:
                        parts = line.split()
                    nums = []
                    for p in parts:
                        try:
                            nums.append(float(p))
                        except ValueError:
                            pass
                    if len(nums) >= 6:
                        rows.append(nums[:6])
            if len(rows) < 6:
                QMessageBox.warning(self, "Import Calibration Matrix", f"Expected at least 6 numeric rows of 6 columns, found {len(rows)}.")
                return
            mat = np.array(rows[:6], dtype=np.float64)
            self.set_calibration_matrix(mat)
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to parse calibration matrix:\n{e}")

    # ------------------------------------------------------------------
    # Adding New Force Plate / Resetting
    # ------------------------------------------------------------------
    def _on_add_new_plate(self):
        if not self.trial:
            return
        new_id = len(self.trial.force_platforms) + 1
        default_corners = np.array([
            [500.0, 0.0, 0.0, 500.0],
            [600.0, 600.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0]
        ], dtype=np.float32)
        default_origin = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        analog_keys = list(self.trial.analogs.keys()) if self.trial.analogs else []
        ch_names = analog_keys[:6]
        ch_map = {f"Ch_{i+1}": self.trial.analogs[k] for i, k in enumerate(ch_names)}

        new_fp = ForcePlatformData(
            id=new_id,
            type=4,
            corners=default_corners,
            origin=default_origin,
            channels=ch_map,
            cal_matrix=np.eye(6, dtype=np.float32),
            channel_names=ch_names
        )
        self.trial.force_platforms.append(new_fp)
        self._populate_plate_selector()
        self.combo_plate.setCurrentIndex(len(self.trial.force_platforms) - 1)
        self.rb_custom.setChecked(True)

    def _reset_current_plate_to_c3d(self):
        idx = self.get_current_plate_index()
        defaults = getattr(self.trial, "_c3d_default_force_platforms", None)
        if defaults and 0 <= idx < len(defaults):
            restored = defaults[idx].clone()
        elif 0 <= idx < len(self._initial_snapshots):
            restored = self._initial_snapshots[idx].clone()
        else:
            return
        self.trial.force_platforms[idx] = restored
        self._plate_ui_states.pop(str(restored.id), None)
        self._load_plate_into_ui(idx)
        self._save_persisted_state_dict()

    def get_selected_channel_names(self) -> List[str]:
        fp_type = int(self.combo_type.currentData() or 4)
        n_req = 8 if fp_type == 3 else 6
        names = []
        for i in range(n_req):
            ch = self.channel_combos[i].currentData()
            names.append(str(ch) if ch else "")
        return names

    # ------------------------------------------------------------------
    # Core Calculation Execution (Option 1 & Option 2)
    # ------------------------------------------------------------------
    def apply_calculation(self) -> bool:
        """
        Execute the selected force plate calculation mode (Automatic Shimba or Custom Configuration)
        and update the trial's force platform data.
        """
        if not self.trial:
            return False

        old_plates = [fp.clone() for fp in self._initial_snapshots]

        if self.rb_auto.isChecked():
            # OPTION 1: Automatic Calculation (Shimba 1984)
            thresh = float(self.spin_auto_threshold.value())
            apply_all = self.chk_auto_all_plates.isChecked()
            cur_idx = self.get_current_plate_index()

            if not self.trial.force_platforms:
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.information(
                        self,
                        "Automatic Force Calculation",
                        "No force platforms are currently defined in this trial. "
                        "Use '+ Add New Force Plate' and Option 2 to configure one from analog channels."
                    )
                return False

            target_indices = (
                list(range(len(self.trial.force_platforms)))
                if apply_all or cur_idx < 0
                else [cur_idx]
            )

            # Also check if original ezc3d handle is available for pure C3D parameter fallback
            c_grw = []
            if getattr(self.trial, "btk_handle", None) is not None:
                try:
                    c_grw = compute_ground_reaction_wrenches(self.trial.btk_handle, threshold=thresh)
                except Exception:
                    c_grw = []

            peak_fz = 0.0
            for i in target_indices:
                fp = self.trial.force_platforms[i]
                V, resolved_names = extract_plate_analog_matrix(self.trial, fp)
                if V.size > 0 and np.any(V != 0):
                    grw = compute_single_plate_grw(
                        analog_signals=V,
                        fp_type=fp.type,
                        corners=fp.corners,
                        origin=fp.origin,
                        cal_matrix=fp.cal_matrix,
                        threshold=thresh,
                        custom_offset=False
                    )
                    fp.forces = grw['F']
                    fp.moments = grw['M']
                    fp.cop = grw['P']
                    if resolved_names:
                        fp.channel_names = resolved_names
                elif i < len(c_grw):
                    fp.forces = c_grw[i]['F']
                    fp.moments = c_grw[i]['M']
                    fp.cop = c_grw[i]['P']

                if fp.forces is not None and len(fp.forces) > 0:
                    peak_fz = max(peak_fz, float(np.max(np.abs(fp.forces[:, 2]))))

            new_plates = [fp.clone() for fp in self.trial.force_platforms]
            self._initial_snapshots = [fp.clone() for fp in self.trial.force_platforms]
            self._save_persisted_state_dict()

            desc = f"Calculated Force Plate GRF automatically (Shimba 1984, Threshold {thresh:.1f} N)"
            pipeline_params = {
                "Mode": "Automatic (Shimba 1984)",
                "Threshold_N": thresh,
                "Scope": "All" if apply_all else f"Plate #{self.trial.force_platforms[cur_idx].id}",
                "PlatesCount": len(target_indices)
            }
            self.forcePlatesChanged.emit(old_plates, new_plates, desc, pipeline_params)
            return True

        else:
            # OPTION 2: Custom Configuration (Corners, Center/Origin Offset, Calibration Matrix)
            if not self.trial.force_platforms:
                self._on_add_new_plate()

            cur_idx = self.get_current_plate_index()
            if cur_idx < 0 or cur_idx >= len(self.trial.force_platforms):
                return False

            fp = self.trial.force_platforms[cur_idx]
            fp_type = int(self.combo_type.currentData() or 4)
            thresh = float(self.spin_custom_threshold.value())
            corners = self.get_corners_array()
            origin_offset = self.get_origin_offset()
            cal_mat = self.get_calibration_matrix()

            selected_ch = self.get_selected_channel_names()
            valid_ch = [c for c in selected_ch if c and c in self.trial.analogs]

            # Update plate metadata
            fp.type = fp_type
            fp.corners = corners.copy()
            fp.origin = origin_offset.copy()
            fp.coord_offset = origin_offset.copy()
            fp.cal_matrix = cal_mat.astype(np.float32)
            if valid_ch:
                fp.channel_names = selected_ch
                fp.channels = {
                    f"Ch_{i+1}": self.trial.analogs[ch]
                    for i, ch in enumerate(selected_ch)
                    if ch in self.trial.analogs
                }

            V, resolved_names = extract_plate_analog_matrix(
                self.trial, fp, channel_names=selected_ch if any(selected_ch) else None
            )

            grw = compute_single_plate_grw(
                analog_signals=V,
                fp_type=fp_type,
                corners=corners,
                origin=origin_offset,
                cal_matrix=cal_mat,
                threshold=thresh,
                custom_offset=True
            )

            fp.forces = grw['F']
            fp.moments = grw['M']
            fp.cop = grw['P']

            peak_fz = float(np.max(np.abs(fp.forces[:, 2]))) if (fp.forces is not None and len(fp.forces) > 0) else 0.0
            self._update_auto_info_label(fp)

            new_plates = [p.clone() for p in self.trial.force_platforms]
            self._initial_snapshots = [p.clone() for p in self.trial.force_platforms]
            self._save_persisted_state_dict()

            diag_vals = [round(float(cal_mat[i, i]), 6) for i in range(6)]
            desc = (
                f"Configured Force Plate #{fp.id} (Type {fp_type}, "
                f"Offset [{origin_offset[0]:.1f}, {origin_offset[1]:.1f}, {origin_offset[2]:.1f}], "
                f"6×6 Calibration Matrix)"
            )
            pipeline_params = {
                "Mode": "Custom",
                "PlateID": fp.id,
                "Type": fp_type,
                "Threshold_N": thresh,
                "Corners": corners.tolist(),
                "OriginOffset": origin_offset.tolist(),
                "CalibrationMatrix": cal_mat.tolist(),
                "CalibrationDiagonal": diag_vals,
                "AnalogChannels": resolved_names,
            }
            self.forcePlatesChanged.emit(old_plates, new_plates, desc, pipeline_params)
            return True


# Alias for naming consistency with AnalogToolsDialog
ForcePlateToolsDialog = ForcePlateDialog


"""Marker analysis and measurement tools: Average Marker, Distance, and Angle."""

import os
import csv
import numpy as np
from typing import Optional, List, Dict, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPushButton, QLabel, QGroupBox, QCheckBox,
    QMessageBox, QColorDialog, QInputDialog, QFileDialog,
    QRadioButton, QDoubleSpinBox, QWidget
)
from gui.toggle_switch import ToggleSwitch

from core.data_models import C3DTrial
from gui.measurement_plot_window import MeasurementPlotWindow



def compute_distance_trajectory(m1_data: np.ndarray, m2_data: np.ndarray) -> np.ndarray:
    """Compute frame-by-frame Euclidean distance between two marker trajectories."""
    diff = m1_data - m2_data
    dist = np.linalg.norm(diff, axis=1)
    # Mask invalid frames (where marker is 0,0,0)
    invalid = np.all(m1_data == 0, axis=1) | np.all(m2_data == 0, axis=1) | np.isnan(dist)
    dist[invalid] = np.nan
    return dist


def compute_angle_trajectory(a_data: np.ndarray, b_data: np.ndarray, c_data: np.ndarray) -> np.ndarray:
    """
    Compute frame-by-frame 3D angle (degrees) ABC with vertex at B:
    angle between vectors (A - B) and (C - B).
    """
    v1 = a_data - b_data
    v2 = c_data - b_data

    # Norms
    norm1 = np.linalg.norm(v1, axis=1)
    norm2 = np.linalg.norm(v2, axis=1)

    # Dot products
    dot = np.sum(v1 * v2, axis=1)
    denom = norm1 * norm2

    # Protect against division by zero
    valid = (denom > 1e-6) & ~np.all(a_data == 0, axis=1) & ~np.all(b_data == 0, axis=1) & ~np.all(c_data == 0, axis=1)
    cos_angle = np.zeros(len(a_data), dtype=np.float32)
    cos_angle[valid] = np.clip(dot[valid] / denom[valid], -1.0, 1.0)
    
    angles = np.full(len(a_data), np.nan, dtype=np.float32)
    angles[valid] = np.degrees(np.arccos(cos_angle[valid]))
    return angles


class CreateAverageMarkerDialog(QDialog):
    """Dialog to create a virtual/average marker between two existing markers."""
    markerCreated = Signal(str, np.ndarray)  # Emits (new_marker_name, trajectory_data)

    def __init__(self, trial: C3DTrial, preselected: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Average Marker")
        self.resize(400, 220)
        self.trial = trial
        self.preselected = preselected or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        marker_names = sorted(list(self.trial.markers.keys()))

        self.combo_m1 = QComboBox()
        self.combo_m1.addItems(marker_names)
        form.addRow("Marker 1:", self.combo_m1)

        self.combo_m2 = QComboBox()
        self.combo_m2.addItems(marker_names)
        form.addRow("Marker 2:", self.combo_m2)

        # Set default selections if provided
        if len(self.preselected) >= 1 and self.preselected[0] in marker_names:
            self.combo_m1.setCurrentText(self.preselected[0])
        if len(self.preselected) >= 2 and self.preselected[1] in marker_names:
            self.combo_m2.setCurrentText(self.preselected[1])
        elif len(marker_names) > 1:
            self.combo_m2.setCurrentIndex(1)

        self.txt_name = QLineEdit()
        self._update_default_name()
        form.addRow("New Marker Name:", self.txt_name)

        self.combo_m1.currentTextChanged.connect(self._update_default_name)
        self.combo_m2.currentTextChanged.connect(self._update_default_name)

        layout.addLayout(form)

        info_lbl = QLabel("Computes the midpoint (M1 + M2) / 2 across all trial frames.")
        info_lbl.setStyleSheet("color: #8C96AB; font-size: 11px;")
        layout.addWidget(info_lbl)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_create = QPushButton("Create Marker")
        btn_create.setObjectName("primaryBtn")
        btn_create.clicked.connect(self._create_marker)
        btn_box.addWidget(btn_create)

        layout.addLayout(btn_box)

    def _update_default_name(self):
        m1 = self.combo_m1.currentText()
        m2 = self.combo_m2.currentText()
        if m1 and m2:
            self.txt_name.setText(f"Avg_{m1}_{m2}")

    def _create_marker(self):
        m1 = self.combo_m1.currentText()
        m2 = self.combo_m2.currentText()
        name = self.txt_name.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid marker name.")
            return

        if name in self.trial.markers:
            res = QMessageBox.question(
                self, "Overwrite Marker", f"Marker '{name}' already exists. Overwrite?"
            )
            if res != QMessageBox.Yes:
                return

        d1 = self.trial.markers[m1]
        d2 = self.trial.markers[m2]
        avg_data = (d1 + d2) / 2.0

        # Handle frames where either marker is missing
        m1_missing = np.all(d1 == 0, axis=1) | np.isnan(d1).any(axis=1)
        m2_missing = np.all(d2 == 0, axis=1) | np.isnan(d2).any(axis=1)
        both_missing = m1_missing & m2_missing
        avg_data[both_missing] = 0.0
        avg_data[m1_missing & ~m2_missing] = d2[m1_missing & ~m2_missing]
        avg_data[m2_missing & ~m1_missing] = d1[m2_missing & ~m1_missing]

        self.markerCreated.emit(name, avg_data)
        self.accept()


class MeasureDistanceDialog(QDialog):
    """Interactive tool to measure 3D distance between two markers."""
    plotRequested = Signal(str, np.ndarray)  # Emits (label, y_trajectory)
    openPlotWindowRequested = Signal(str, np.ndarray, str, str)  # Emits (title, y_data, unit, curve_type)
    visualize3DRequested = Signal(str, str, bool)  # Emits (m1, m2, enabled)

    def __init__(
        self,
        trial: C3DTrial,
        current_frame: int = 0,
        preselected: Optional[List[str]] = None,
        trim_range: Optional[Tuple[int, int]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Measure Distance Between Markers")
        self.resize(440, 320)
        self.trial = trial
        self.current_frame = current_frame
        self.preselected = preselected or []
        self._distance_trajectory: Optional[np.ndarray] = None
        n_pts = trial.point_frame_count if trial else 0
        if trim_range is not None:
            s_f = max(0, min(max(0, n_pts - 1), int(trim_range[0])))
            e_f = max(s_f, min(max(0, n_pts - 1), int(trim_range[1])))
            self.trim_range: Tuple[int, int] = (s_f, e_f)
        else:
            self.trim_range: Tuple[int, int] = (0, max(0, n_pts - 1))

        self._setup_ui()
        self._recompute()

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Update ROI trim range and recompute statistics."""
        n = len(self._distance_trajectory) if self._distance_trajectory is not None else (self.trial.point_frame_count if self.trial else 0)
        start_f = max(0, min(max(0, n - 1), int(start_frame)))
        end_f = max(start_f, min(max(0, n - 1), int(end_frame)))
        self.trim_range = (start_f, end_f)
        self._update_stats()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        marker_names = sorted(list(self.trial.markers.keys()))

        self.combo_m1 = QComboBox()
        self.combo_m1.addItems(marker_names)
        form.addRow("Marker 1:", self.combo_m1)

        self.combo_m2 = QComboBox()
        self.combo_m2.addItems(marker_names)
        form.addRow("Marker 2:", self.combo_m2)

        if len(self.preselected) >= 1 and self.preselected[0] in marker_names:
            self.combo_m1.setCurrentText(self.preselected[0])
        if len(self.preselected) >= 2 and self.preselected[1] in marker_names:
            self.combo_m2.setCurrentText(self.preselected[1])
        elif len(marker_names) > 1:
            self.combo_m2.setCurrentIndex(1)

        layout.addLayout(form)

        # Statistics Group Box
        box = QGroupBox("Distance Measurements")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(6)

        self.lbl_cur_dist = QLabel("Current Distance: --- mm")
        self.lbl_cur_dist.setStyleSheet("font-size: 14px; font-weight: 700; color: #00ADB5;")
        box_layout.addWidget(self.lbl_cur_dist)

        self.lbl_stats = QLabel("Mean: --- | Min: --- | Max: ---")
        self.lbl_stats.setStyleSheet("color: #D8DEE9; font-size: 12px;")
        box_layout.addWidget(self.lbl_stats)

        layout.addWidget(box)

        # 3D Overlay Toggle
        self.chk_3d = ToggleSwitch("Show 3D Measurement Line in Viewport")
        self.chk_3d.setChecked(True)
        self.chk_3d.toggled.connect(self._on_3d_toggle)
        layout.addWidget(self.chk_3d)

        # Action Buttons
        btn_plot = QPushButton("Plot")
        btn_plot.setObjectName("primaryBtn")
        btn_plot.setToolTip("Plot distance curve in a dedicated pop-up window")
        btn_plot.clicked.connect(self._send_to_plot)
        layout.addWidget(btn_plot)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        self.combo_m1.currentTextChanged.connect(self._recompute)
        self.combo_m2.currentTextChanged.connect(self._recompute)

    def update_frame(self, frame_idx: int):
        """Called by MainWindow when playback advances."""
        self.current_frame = frame_idx
        if self._distance_trajectory is not None and frame_idx < len(self._distance_trajectory):
            d = self._distance_trajectory[frame_idx]
            if np.isnan(d):
                self.lbl_cur_dist.setText(f"Frame {frame_idx} Distance: Missing / Untracked")
            else:
                self.lbl_cur_dist.setText(f"Frame {frame_idx} Distance: {d:.2f} mm")

    def _recompute(self):
        m1 = self.combo_m1.currentText()
        m2 = self.combo_m2.currentText()
        if not m1 or not m2 or m1 == m2:
            self.lbl_cur_dist.setText("Current Distance: 0.00 mm")
            self.lbl_stats.setText("Please select two distinct markers.")
            return

        d1 = self.trial.markers[m1]
        d2 = self.trial.markers[m2]
        self._distance_trajectory = compute_distance_trajectory(d1, d2)
        self._update_stats()
        self.update_frame(self.current_frame)
        self._on_3d_toggle(self.chk_3d.isChecked())

    def _update_stats(self):
        if self._distance_trajectory is None:
            return
        n = len(self._distance_trajectory)
        if n == 0:
            self.lbl_stats.setText("No data available.")
            return

        start_f = max(0, min(n - 1, self.trim_range[0]))
        end_f = max(start_f, min(n - 1, self.trim_range[1]))
        roi_slice = self._distance_trajectory[start_f : end_f + 1]
        valid = roi_slice[~np.isnan(roi_slice)]
        is_trimmed = (start_f > 0 or end_f < n - 1)
        prefix = f"ROI [F{start_f}–{end_f}]: " if is_trimmed else ""

        if len(valid) > 0:
            mean_d = float(np.mean(valid))
            min_d = float(np.min(valid))
            max_d = float(np.max(valid))
            std_d = float(np.std(valid))
            self.lbl_stats.setText(
                f"{prefix}Mean: {mean_d:.2f} ± {std_d:.2f} mm | Min: {min_d:.2f} mm | Max: {max_d:.2f} mm"
            )
        else:
            self.lbl_stats.setText(f"{prefix}No valid tracking data in range.")

    def _on_3d_toggle(self, checked: bool):
        m1 = self.combo_m1.currentText()
        m2 = self.combo_m2.currentText()
        self.visualize3DRequested.emit(m1, m2, checked)

    def _send_to_plot(self):
        m1 = self.combo_m1.currentText()
        m2 = self.combo_m2.currentText()
        if self._distance_trajectory is not None:
            lbl = f"Dist_{m1}_{m2}"
            self.plotRequested.emit(lbl, self._distance_trajectory)
            title = f"Distance: {m1} ↔ {m2}"
            self.openPlotWindowRequested.emit(title, self._distance_trajectory, "mm", "Distance")
            if not self.parent():
                rate = self.trial.point_rate if self.trial else 100.0
                self._plot_window = MeasurementPlotWindow(
                    title=title,
                    y_data=self._distance_trajectory,
                    point_rate=rate,
                    unit="mm",
                    curve_type="Distance",
                    current_frame=self.current_frame,
                    trim_range=self.trim_range,
                    parent=None
                )
                self._plot_window.show()

    def closeEvent(self, event):
        # Clear 3D visualization when dialog is closed
        self.visualize3DRequested.emit("", "", False)
        super().closeEvent(event)


class MeasureAngleDialog(QDialog):
    """Interactive tool to measure 3D angle between three markers (vertex at B)."""
    plotRequested = Signal(str, np.ndarray)  # Emits (label, y_trajectory)
    openPlotWindowRequested = Signal(str, np.ndarray, str, str)  # Emits (title, y_data, unit, curve_type)
    visualize3DRequested = Signal(str, str, str, bool)  # Emits (mA, mB, mC, enabled)

    def __init__(
        self,
        trial: C3DTrial,
        current_frame: int = 0,
        preselected: Optional[List[str]] = None,
        trim_range: Optional[Tuple[int, int]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Measure Angle Between 3 Markers")
        self.resize(460, 350)
        self.trial = trial
        self.current_frame = current_frame
        self.preselected = preselected or []
        self._angle_trajectory: Optional[np.ndarray] = None
        n_pts = trial.point_frame_count if trial else 0
        if trim_range is not None:
            s_f = max(0, min(max(0, n_pts - 1), int(trim_range[0])))
            e_f = max(s_f, min(max(0, n_pts - 1), int(trim_range[1])))
            self.trim_range: Tuple[int, int] = (s_f, e_f)
        else:
            self.trim_range: Tuple[int, int] = (0, max(0, n_pts - 1))

        self._setup_ui()
        self._recompute()

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Update ROI trim range and recompute statistics."""
        n = len(self._angle_trajectory) if self._angle_trajectory is not None else (self.trial.point_frame_count if self.trial else 0)
        start_f = max(0, min(max(0, n - 1), int(start_frame)))
        end_f = max(start_f, min(max(0, n - 1), int(end_frame)))
        self.trim_range = (start_f, end_f)
        self._update_stats()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        marker_names = sorted(list(self.trial.markers.keys()))

        self.combo_ma = QComboBox()
        self.combo_ma.addItems(marker_names)
        form.addRow("Marker A (Start):", self.combo_ma)

        self.combo_mb = QComboBox()
        self.combo_mb.addItems(marker_names)
        form.addRow("Marker B (Vertex):", self.combo_mb)

        self.combo_mc = QComboBox()
        self.combo_mc.addItems(marker_names)
        form.addRow("Marker C (End):", self.combo_mc)

        if len(self.preselected) >= 1 and self.preselected[0] in marker_names:
            self.combo_ma.setCurrentText(self.preselected[0])
        if len(self.preselected) >= 2 and self.preselected[1] in marker_names:
            self.combo_mb.setCurrentText(self.preselected[1])
        if len(self.preselected) >= 3 and self.preselected[2] in marker_names:
            self.combo_mc.setCurrentText(self.preselected[2])
        elif len(marker_names) > 2:
            self.combo_mb.setCurrentIndex(1)
            self.combo_mc.setCurrentIndex(2)

        layout.addLayout(form)

        # Angle Results Box
        box = QGroupBox("Angle Measurements")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(6)

        self.lbl_cur_angle = QLabel("Current Angle: ---°")
        self.lbl_cur_angle.setStyleSheet("font-size: 15px; font-weight: 700; color: #00ADB5;")
        box_layout.addWidget(self.lbl_cur_angle)

        self.lbl_stats = QLabel("Mean: ---° | Min: ---° | Max: ---°")
        self.lbl_stats.setStyleSheet("color: #D8DEE9; font-size: 12px;")
        box_layout.addWidget(self.lbl_stats)

        layout.addWidget(box)

        # 3D Overlay Toggle
        self.chk_3d = ToggleSwitch("Show 3D Measurement Angle in Viewport")
        self.chk_3d.setChecked(True)
        self.chk_3d.toggled.connect(self._on_3d_toggle)
        layout.addWidget(self.chk_3d)

        # Action Buttons
        btn_plot = QPushButton("Plot")
        btn_plot.setObjectName("primaryBtn")
        btn_plot.setToolTip("Plot angle curve in a dedicated pop-up window")
        btn_plot.clicked.connect(self._send_to_plot)
        layout.addWidget(btn_plot)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        self.combo_ma.currentTextChanged.connect(self._recompute)
        self.combo_mb.currentTextChanged.connect(self._recompute)
        self.combo_mc.currentTextChanged.connect(self._recompute)

    def update_frame(self, frame_idx: int):
        self.current_frame = frame_idx
        if self._angle_trajectory is not None and frame_idx < len(self._angle_trajectory):
            a = self._angle_trajectory[frame_idx]
            if np.isnan(a):
                self.lbl_cur_angle.setText(f"Frame {frame_idx} Angle: Missing / Untracked")
            else:
                self.lbl_cur_angle.setText(f"Frame {frame_idx} Angle: {a:.2f}°")

    def _recompute(self):
        ma = self.combo_ma.currentText()
        mb = self.combo_mb.currentText()
        mc = self.combo_mc.currentText()

        if len({ma, mb, mc}) < 3:
            self.lbl_cur_angle.setText("Current Angle: ---°")
            self.lbl_stats.setText("Please select three distinct markers.")
            return

        da = self.trial.markers[ma]
        db = self.trial.markers[mb]
        dc = self.trial.markers[mc]

        self._angle_trajectory = compute_angle_trajectory(da, db, dc)
        self._update_stats()
        self.update_frame(self.current_frame)
        self._on_3d_toggle(self.chk_3d.isChecked())

    def _update_stats(self):
        if self._angle_trajectory is None:
            return
        n = len(self._angle_trajectory)
        if n == 0:
            self.lbl_stats.setText("No data available.")
            return

        start_f = max(0, min(n - 1, self.trim_range[0]))
        end_f = max(start_f, min(n - 1, self.trim_range[1]))
        roi_slice = self._angle_trajectory[start_f : end_f + 1]
        valid = roi_slice[~np.isnan(roi_slice)]
        is_trimmed = (start_f > 0 or end_f < n - 1)
        prefix = f"ROI [F{start_f}–{end_f}]: " if is_trimmed else ""

        if len(valid) > 0:
            mean_a = float(np.mean(valid))
            min_a = float(np.min(valid))
            max_a = float(np.max(valid))
            std_a = float(np.std(valid))
            self.lbl_stats.setText(
                f"{prefix}Mean: {mean_a:.1f}° ± {std_a:.1f}° | Min: {min_a:.1f}° | Max: {max_a:.1f}°"
            )
        else:
            self.lbl_stats.setText(f"{prefix}No valid tracking data in range.")

    def _on_3d_toggle(self, checked: bool):
        ma = self.combo_ma.currentText()
        mb = self.combo_mb.currentText()
        mc = self.combo_mc.currentText()
        self.visualize3DRequested.emit(ma, mb, mc, checked)

    def _send_to_plot(self):
        ma = self.combo_ma.currentText()
        mb = self.combo_mb.currentText()
        mc = self.combo_mc.currentText()
        if self._angle_trajectory is not None:
            lbl = f"Angle_{ma}_{mb}_{mc}"
            self.plotRequested.emit(lbl, self._angle_trajectory)
            title = f"Angle: {ma} - {mb} - {mc}"
            self.openPlotWindowRequested.emit(title, self._angle_trajectory, "°", "Angle")
            if not self.parent():
                rate = self.trial.point_rate if self.trial else 100.0
                self._plot_window = MeasurementPlotWindow(
                    title=title,
                    y_data=self._angle_trajectory,
                    point_rate=rate,
                    unit="°",
                    curve_type="Angle",
                    current_frame=self.current_frame,
                    trim_range=self.trim_range,
                    parent=None
                )
                self._plot_window.show()

    def closeEvent(self, event):
        self.visualize3DRequested.emit("", "", "", False)
        super().closeEvent(event)


def parse_coordinates_file(filepath: str, expected_frames: int) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """
    Parse an Excel (.xlsx), CSV (.csv), or Text (.txt, .tsv) file containing frame-by-frame 3D coordinates.
    Returns (data_array, error_message).
    If error_message is not None, parsing failed or frame count did not match.
    """
    if not filepath or not os.path.isfile(filepath):
        return None, "File does not exist or invalid path specified."

    ext = os.path.splitext(filepath)[1].lower()
    raw_rows = []

    try:
        if ext in [".xlsx", ".xlsm"]:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if row is None or all(c is None or str(c).strip() == "" for c in row):
                    continue
                raw_rows.append(list(row))
            wb.close()
        elif ext == ".xls":
            try:
                import xlrd
                wb = xlrd.open_workbook(filepath)
                ws = wb.sheet_by_index(0)
                for r in range(ws.nrows):
                    row = [ws.cell_value(r, c) for c in range(ws.ncols)]
                    if any(c != "" and c is not None for c in row):
                        raw_rows.append(row)
            except ImportError:
                return None, "Older .xls files require 'xlrd'. Please save your file as modern Excel (.xlsx) or CSV (.csv)."
        else:
            with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()

            sample = content[:4096]
            delim = ","
            if "\t" in sample:
                delim = "\t"
            elif ";" in sample:
                delim = ";"
            elif "," in sample:
                delim = ","
            else:
                delim = None

            if delim is not None:
                reader = csv.reader(content.splitlines(), delimiter=delim)
                for row in reader:
                    if row and any(c.strip() for c in row):
                        raw_rows.append([c.strip() for c in row])
            else:
                for line in content.splitlines():
                    p = line.strip().split()
                    if p:
                        raw_rows.append(p)

    except Exception as e:
        return None, f"Failed to read file:\n{e}"

    if not raw_rows:
        return None, "The selected file is empty."

    # Parse numeric values and detect/skip text header rows
    numeric_rows = []
    for row in raw_rows:
        nums = []
        for val in row:
            if val is None or str(val).strip() == "":
                continue
            try:
                nums.append(float(str(val).replace(",", ".")))
            except (ValueError, TypeError):
                pass
        if len(nums) >= 3:
            numeric_rows.append(nums)

    if not numeric_rows:
        return None, (
            "No valid 3D coordinate rows found in file.\n"
            "Each row must contain at least 3 numeric values for X, Y, Z coordinates."
        )

    # Determine which 3 columns correspond to X, Y, Z
    first_row = numeric_rows[0]
    if len(first_row) == 3:
        arr = np.array([r[:3] for r in numeric_rows], dtype=np.float32)
    elif len(first_row) >= 4:
        col0 = [r[0] for r in numeric_rows]
        is_frame_idx = False
        if len(col0) > 1:
            diffs = np.diff(col0)
            if np.allclose(diffs, 1.0) or (col0[0] in (0.0, 1.0) and np.all(diffs > 0)):
                is_frame_idx = True

        if is_frame_idx:
            arr = np.array([r[1:4] for r in numeric_rows], dtype=np.float32)
        else:
            arr = np.array([r[:3] for r in numeric_rows], dtype=np.float32)
    else:
        return None, "File rows must contain at least 3 numeric coordinates (X, Y, Z)."

    # Verify frame count matches active trial
    loaded_frames = arr.shape[0]
    if loaded_frames != expected_frames:
        return None, (
            f"Frame count mismatch!\n\n"
            f"The selected file contains {loaded_frames} frames (rows), "
            f"but the active trial requires {expected_frames} frames.\n\n"
            f"The length of the frames must match other markers in this trial."
        )

    return arr, None


class AddMarkerDialog(QDialog):
    """
    Dialog to add a new 3D marker to the trial.
    Allows specifying marker name, custom display color, and either importing
    frame coordinates from file (.txt, .csv, .xlsx) or specifying a default position.
    """
    markerAdded = Signal(str, np.ndarray, object)  # (name, data, QColor)

    def __init__(self, trial: C3DTrial, parent=None):
        super().__init__(parent)
        self.trial = trial
        self.expected_frames = trial.point_frame_count if trial else 0
        self.selected_color: QColor = QColor("#00ADB5")
        self._parsed_data: Optional[np.ndarray] = None
        self._last_parsed_path: Optional[str] = None

        self.setWindowTitle("Add Marker")
        self.resize(520, 460)
        self._setup_ui()

    def _get_unique_default_name(self) -> str:
        if not self.trial or not self.trial.markers:
            return "Marker_1"
        idx = 1
        while f"Marker_{idx}" in self.trial.markers:
            idx += 1
        return f"Marker_{idx}"

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header info
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        lbl_title = QLabel("Add New 3D Marker")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        header_layout.addWidget(lbl_title)

        self.lbl_frames_info = QLabel(
            f"Active trial frame count: <b>{self.expected_frames} frames</b>"
            f" ({self.trial.point_rate:.1f} Hz)" if self.trial else "No trial loaded"
        )
        self.lbl_frames_info.setStyleSheet("font-size: 12px;")
        header_layout.addWidget(self.lbl_frames_info)
        layout.addLayout(header_layout)

        # Group 1: Marker Properties (Name & Color)
        grp_props = QGroupBox("Marker Properties")
        form_props = QFormLayout(grp_props)
        form_props.setSpacing(10)

        self.txt_name = QLineEdit(self._get_unique_default_name())
        self.txt_name.setPlaceholderText("e.g. R_KNEE, V_HIP, CUSTOM_1")
        form_props.addRow("Marker Name:", self.txt_name)

        # Color picker row
        color_row = QHBoxLayout()
        color_row.setSpacing(8)

        self.btn_color_swatch = QPushButton()
        self.btn_color_swatch.setFixedSize(36, 26)
        self.btn_color_swatch.setCursor(Qt.PointingHandCursor)
        self.btn_color_swatch.setToolTip("Click to select custom marker color")
        self.btn_color_swatch.clicked.connect(self._pick_color)
        color_row.addWidget(self.btn_color_swatch)

        self.btn_pick_color = QPushButton("Choose Color...")
        self.btn_pick_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.btn_pick_color)

        self.lbl_color_hex = QLabel(self.selected_color.name().upper())
        self.lbl_color_hex.setStyleSheet("color: #8C96AB; font-family: monospace;")
        color_row.addWidget(self.lbl_color_hex)
        color_row.addStretch()

        form_props.addRow("Display Color:", color_row)
        layout.addWidget(grp_props)
        self._update_color_swatch()

        # Group 2: Coordinates Source
        grp_coords = QGroupBox("Trajectory Coordinates")
        coords_layout = QVBoxLayout(grp_coords)
        coords_layout.setSpacing(8)

        self.radio_file = QRadioButton("Import Coordinates from File (.txt, .csv, .xlsx)")
        self.radio_file.setChecked(True)
        self.radio_file.toggled.connect(self._on_source_toggled)
        coords_layout.addWidget(self.radio_file)

        # File options container
        self.container_file = QWidget()
        file_box = QVBoxLayout(self.container_file)
        file_box.setContentsMargins(16, 2, 0, 4)
        file_box.setSpacing(6)

        file_browse_row = QHBoxLayout()
        file_browse_row.setSpacing(6)
        self.txt_file = QLineEdit()
        self.txt_file.setPlaceholderText("Select or enter path to .txt, .csv, or .xlsx file...")
        self.txt_file.textChanged.connect(self._on_file_text_changed)
        file_browse_row.addWidget(self.txt_file)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_file)
        file_browse_row.addWidget(self.btn_browse)
        file_box.addLayout(file_browse_row)

        self.lbl_file_status = QLabel(
            f"ℹ Expects {self.expected_frames} rows with columns X, Y, Z"
        )
        self.lbl_file_status.setStyleSheet("color: #8C96AB; font-size: 11px;")
        self.lbl_file_status.setWordWrap(True)
        file_box.addWidget(self.lbl_file_status)

        coords_layout.addWidget(self.container_file)

        # Radio 2: Fixed Position
        self.radio_fixed = QRadioButton("Initialize with Default Fixed Position")
        self.radio_fixed.toggled.connect(self._on_source_toggled)
        coords_layout.addWidget(self.radio_fixed)

        self.container_fixed = QWidget()
        fixed_box = QHBoxLayout(self.container_fixed)
        fixed_box.setContentsMargins(16, 2, 0, 4)
        fixed_box.setSpacing(10)

        fixed_box.addWidget(QLabel("X (mm):"))
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-100000.0, 100000.0)
        self.spin_x.setValue(0.0)
        fixed_box.addWidget(self.spin_x)

        fixed_box.addWidget(QLabel("Y (mm):"))
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-100000.0, 100000.0)
        self.spin_y.setValue(0.0)
        fixed_box.addWidget(self.spin_y)

        fixed_box.addWidget(QLabel("Z (mm):"))
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-100000.0, 100000.0)
        self.spin_z.setValue(0.0)
        fixed_box.addWidget(self.spin_z)
        fixed_box.addStretch()

        self.container_fixed.setEnabled(False)
        coords_layout.addWidget(self.container_fixed)

        layout.addWidget(grp_coords)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_add = QPushButton("Add Marker")
        self.btn_add.setObjectName("primaryBtn")
        self.btn_add.setStyleSheet(
            "background-color: #00ADB5; color: white; font-weight: bold; padding: 6px 18px;"
        )
        self.btn_add.clicked.connect(self._on_add_clicked)
        btn_box.addWidget(self.btn_add)

        layout.addLayout(btn_box)

    def _update_color_swatch(self):
        c_hex = self.selected_color.name()
        self.btn_color_swatch.setStyleSheet(
            f"background-color: {c_hex}; border: 1px solid #666; border-radius: 4px;"
        )
        self.lbl_color_hex.setText(c_hex.upper())

    def _pick_color(self):
        col = QColorDialog.getColor(self.selected_color, self, "Select Marker Color")
        if col.isValid():
            self.selected_color = col
            self._update_color_swatch()

    def _on_source_toggled(self):
        is_file = self.radio_file.isChecked()
        self.container_file.setEnabled(is_file)
        self.container_fixed.setEnabled(not is_file)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Coordinate File",
            "",
            "Coordinate Files (*.txt *.csv *.tsv *.xlsx *.xls);;Text Files (*.txt *.tsv);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if path:
            self.txt_file.setText(path)
            self._validate_file(path)

    def _on_file_text_changed(self, text: str):
        path = text.strip()
        if os.path.isfile(path):
            self._validate_file(path)
        else:
            self._parsed_data = None
            self._last_parsed_path = None
            if not path:
                self.lbl_file_status.setText(f"ℹ Expects {self.expected_frames} rows with columns X, Y, Z")
                self.lbl_file_status.setStyleSheet("color: #8C96AB; font-size: 11px;")
            else:
                self.lbl_file_status.setText("⚠ File does not exist")
                self.lbl_file_status.setStyleSheet("color: #FF6B6B; font-size: 11px;")

    def _validate_file(self, path: str):
        arr, err = parse_coordinates_file(path, self.expected_frames)
        if err:
            self._parsed_data = None
            self._last_parsed_path = None
            self.lbl_file_status.setText(f"⚠ {err}")
            self.lbl_file_status.setStyleSheet("color: #FF6B6B; font-weight: bold; font-size: 11px;")
        else:
            self._parsed_data = arr
            self._last_parsed_path = path
            self.lbl_file_status.setText(f"✓ Valid: {arr.shape[0]} frames loaded from {os.path.basename(path)}")
            self.lbl_file_status.setStyleSheet("color: #4ECCA3; font-weight: bold; font-size: 11px;")

    def _on_add_clicked(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Marker name cannot be empty.")
            self.txt_name.setFocus()
            return

        if self.trial and name in self.trial.markers:
            QMessageBox.warning(
                self,
                "Marker Exists",
                f"A marker named '{name}' already exists in this trial.\nPlease choose a unique name."
            )
            self.txt_name.setFocus()
            return

        if self.radio_file.isChecked():
            filepath = self.txt_file.text().strip()
            if not filepath:
                QMessageBox.warning(self, "Missing File", "Please select a coordinate file (.txt, .csv, or .xlsx).")
                self.txt_file.setFocus()
                return

            if self._parsed_data is not None and self._last_parsed_path == filepath:
                data = self._parsed_data
            else:
                arr, err = parse_coordinates_file(filepath, self.expected_frames)
                if err:
                    QMessageBox.critical(self, "Invalid Coordinate File", err)
                    return
                data = arr
        else:
            # Fixed coordinate position across all frames
            x = self.spin_x.value()
            y = self.spin_y.value()
            z = self.spin_z.value()
            data = np.tile([x, y, z], (self.expected_frames, 1)).astype(np.float32)

        self.markerAdded.emit(name, data, self.selected_color)
        self.accept()


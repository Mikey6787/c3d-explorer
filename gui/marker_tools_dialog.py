"""Marker analysis and measurement tools: Average Marker, Distance, and Angle."""

import numpy as np
from typing import Optional, List, Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPushButton, QLabel, QGroupBox, QCheckBox,
    QMessageBox, QColorDialog, QInputDialog
)

from core.data_models import C3DTrial


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
    visualize3DRequested = Signal(str, str, bool)  # Emits (m1, m2, enabled)

    def __init__(self, trial: C3DTrial, current_frame: int = 0, preselected: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measure Distance Between Markers")
        self.resize(440, 320)
        self.trial = trial
        self.current_frame = current_frame
        self.preselected = preselected or []
        self._distance_trajectory: Optional[np.ndarray] = None

        self._setup_ui()
        self._recompute()

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
        self.chk_3d = QCheckBox("Show 3D Measurement Line in Viewport")
        self.chk_3d.setChecked(True)
        self.chk_3d.toggled.connect(self._on_3d_toggle)
        layout.addWidget(self.chk_3d)

        # Action Buttons
        btn_plot = QPushButton("Plot Distance vs Time in Signal Panel")
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

        valid = self._distance_trajectory[~np.isnan(self._distance_trajectory)]
        if len(valid) > 0:
            mean_d = np.mean(valid)
            min_d = np.min(valid)
            max_d = np.max(valid)
            std_d = np.std(valid)
            self.lbl_stats.setText(
                f"Mean: {mean_d:.2f} ± {std_d:.2f} mm | Min: {min_d:.2f} mm | Max: {max_d:.2f} mm"
            )
        else:
            self.lbl_stats.setText("No valid overlapping frames.")

        self.update_frame(self.current_frame)
        self._on_3d_toggle(self.chk_3d.isChecked())

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
            QMessageBox.information(self, "Plotted", f"Distance curve '{lbl}' added to Signal Panel!")

    def closeEvent(self, event):
        # Clear 3D visualization when dialog is closed
        self.visualize3DRequested.emit("", "", False)
        super().closeEvent(event)


class MeasureAngleDialog(QDialog):
    """Interactive tool to measure 3D angle between three markers (vertex at B)."""
    plotRequested = Signal(str, np.ndarray)  # Emits (label, y_trajectory)
    visualize3DRequested = Signal(str, str, str, bool)  # Emits (mA, mB, mC, enabled)

    def __init__(self, trial: C3DTrial, current_frame: int = 0, preselected: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measure Angle Between 3 Markers")
        self.resize(460, 350)
        self.trial = trial
        self.current_frame = current_frame
        self.preselected = preselected or []
        self._angle_trajectory: Optional[np.ndarray] = None

        self._setup_ui()
        self._recompute()

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
        self.chk_3d = QCheckBox("Show 3D Measurement Angle in Viewport")
        self.chk_3d.setChecked(True)
        self.chk_3d.toggled.connect(self._on_3d_toggle)
        layout.addWidget(self.chk_3d)

        # Action Buttons
        btn_plot = QPushButton("Plot Angle vs Time in Signal Panel")
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

        valid = self._angle_trajectory[~np.isnan(self._angle_trajectory)]
        if len(valid) > 0:
            mean_a = np.mean(valid)
            min_a = np.min(valid)
            max_a = np.max(valid)
            std_a = np.std(valid)
            self.lbl_stats.setText(
                f"Mean: {mean_a:.1f}° ± {std_a:.1f}° | Min: {min_a:.1f}° | Max: {max_a:.1f}°"
            )
        else:
            self.lbl_stats.setText("No valid overlapping frames.")

        self.update_frame(self.current_frame)
        self._on_3d_toggle(self.chk_3d.isChecked())

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
            QMessageBox.information(self, "Plotted", f"Angle curve '{lbl}' added to Signal Panel!")

    def closeEvent(self, event):
        self.visualize3DRequested.emit("", "", "", False)
        super().closeEvent(event)

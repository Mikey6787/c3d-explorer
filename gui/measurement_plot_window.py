"""Dedicated modern pop-up window for visualizing measurement curves (e.g. Distance, Angle).

Features:
- Instant pop-up on Plot action
- Dynamic live stats chips (Mean, SD, Min, Max, and Live value at playhead) calculated strictly on trimmed ROI range
- Visual highlighting of the curve section inside the user-defined ROI range
- Interactive ROI linear region overlay (draggable on plot to update cut/trim range across app)
- "Fit ROI" and "Fit Full" one-click horizontal zoom options
- "Crop to ROI" toggle (view full trial with ROI highlighted vs viewing only the trimmed ROI)
- Synchronized vertical playback cursor (scrubs the 3D trial interactively)
- X-axis toggle between Time (s) and Frames
- Export to CSV (with ROI flags) and high-res image (PNG)
- Hover crosshair coordinate readout with ROI indicator
"""

from typing import Optional, Tuple
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QButtonGroup, QFileDialog, QMessageBox,
    QFrame, QSizePolicy
)
import pyqtgraph as pg
import pyqtgraph.exporters


class MeasurementPlotWindow(QMainWindow):
    """Sleek, dedicated pop-up curve window for distance and angle measurements."""
    timeCursorMoved = Signal(float)       # Emitted when user drags cursor on the plot (seconds)
    trimRangeChanged = Signal(int, int)   # Emitted when user drags ROI bounds on the plot (start_frame, end_frame)
    windowClosed = Signal()               # Emitted when the measurement window is closed

    def __init__(
        self,
        title: str,
        y_data: np.ndarray,
        point_rate: float = 100.0,
        unit: str = "mm",
        curve_type: str = "Distance",
        current_frame: int = 0,
        trim_range: Optional[Tuple[int, int]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"{title} - Curve Plot")
        self.resize(920, 560)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.curve_title = title
        self.y_data = np.asarray(y_data, dtype=float)
        self.point_rate = max(1.0, float(point_rate))
        self.unit = unit
        self.curve_type = curve_type
        self.current_frame = max(0, int(current_frame))
        self.x_axis_mode = "time"  # "time" or "frame"
        self.crop_to_roi: bool = False  # False = highlight ROI inside full curve; True = crop display to ROI only

        # Initialize trim range (ROI)
        n_points = len(self.y_data)
        if trim_range is not None:
            s_f = max(0, min(max(0, n_points - 1), int(trim_range[0])))
            e_f = max(s_f, min(max(0, n_points - 1), int(trim_range[1])))
            self.trim_range: Tuple[int, int] = (s_f, e_f)
        else:
            self.trim_range: Tuple[int, int] = (0, max(0, n_points - 1))

        # Precompute X axes
        self.x_frames = np.arange(n_points, dtype=float)
        self.x_times = self.x_frames / self.point_rate

        self._init_ui()
        self._update_stats()
        self._plot_curve()
        self.update_frame(self.current_frame)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # Top Header Bar: Title, Live Stats Chips & Controls
        # -------------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # Title badge
        lbl_title = QLabel(self.curve_title)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #00ADB5;")
        top_bar.addWidget(lbl_title)

        # ROI summary stats chip (Mean, SD, Min, Max computed strictly for trimmed range)
        self.lbl_stats = QLabel("Calculating...")
        self.lbl_stats.setStyleSheet(
            "background: #1E2433; border: 1px solid #333F54; border-radius: 12px; "
            "padding: 4px 12px; color: #E2E8F0; font-size: 12px; font-weight: 500;"
        )
        top_bar.addWidget(self.lbl_stats)

        # Live current frame value chip
        self.lbl_current_val = QLabel(f"Current: --- {self.unit}")
        self.lbl_current_val.setStyleSheet(
            "background: #0D2833; border: 1px solid #00ADB5; border-radius: 12px; "
            "padding: 4px 12px; color: #00E5FF; font-size: 12px; font-weight: 600;"
        )
        top_bar.addWidget(self.lbl_current_val)

        top_bar.addStretch()

        # X-Axis Mode Buttons (Time vs Frames)
        btn_time = QPushButton("Time (s)")
        btn_time.setCheckable(True)
        btn_time.setChecked(True)
        btn_time.setCursor(Qt.PointingHandCursor)

        btn_frame = QPushButton("Frames")
        btn_frame.setCheckable(True)
        btn_frame.setCursor(Qt.PointingHandCursor)

        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.addButton(btn_time, 0)
        self.btn_group_mode.addButton(btn_frame, 1)
        self.btn_group_mode.idClicked.connect(self._on_axis_mode_changed)

        top_bar.addWidget(btn_time)
        top_bar.addWidget(btn_frame)

        # Fit ROI button
        btn_fit_roi = QPushButton("Fit ROI")
        btn_fit_roi.setCursor(Qt.PointingHandCursor)
        btn_fit_roi.setToolTip("Auto-fit horizontal and vertical zoom to trimmed ROI range")
        btn_fit_roi.clicked.connect(self.fit_roi)
        top_bar.addWidget(btn_fit_roi)

        # Auto Range / Fit Full
        btn_fit = QPushButton("Fit Full")
        btn_fit.setCursor(Qt.PointingHandCursor)
        btn_fit.setToolTip("Auto-fit horizontal and vertical zoom to entire trial")
        btn_fit.clicked.connect(self.auto_range)
        top_bar.addWidget(btn_fit)

        # Crop to ROI Toggle button
        self.btn_crop_roi = QPushButton("Crop to ROI")
        self.btn_crop_roi.setCheckable(True)
        self.btn_crop_roi.setChecked(False)
        self.btn_crop_roi.setCursor(Qt.PointingHandCursor)
        self.btn_crop_roi.setToolTip("Toggle between Highlighting the ROI on full curve vs Plotting only the trimmed ROI")
        self.btn_crop_roi.toggled.connect(self._on_crop_toggled)
        top_bar.addWidget(self.btn_crop_roi)

        # Export CSV
        btn_csv = QPushButton("Export CSV")
        btn_csv.setCursor(Qt.PointingHandCursor)
        btn_csv.clicked.connect(self.export_csv)
        top_bar.addWidget(btn_csv)

        # Export PNG
        btn_png = QPushButton("Export Image")
        btn_png.setCursor(Qt.PointingHandCursor)
        btn_png.clicked.connect(self.export_image)
        top_bar.addWidget(btn_png)

        main_layout.addLayout(top_bar)

        # -------------------------------------------------------------
        # PyQtGraph Plot Area
        # -------------------------------------------------------------
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#151720")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)

        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.setMenuEnabled(True)

        # Styling axes
        axis_font = QFont()
        axis_font.setPointSize(10)
        self.plot_item.getAxis("bottom").setStyle(tickFont=axis_font)
        self.plot_item.getAxis("left").setStyle(tickFont=axis_font)
        self.plot_item.setLabel("bottom", "Time", units="s")
        self.plot_item.setLabel("left", self.curve_type, units=self.unit)

        # Colors: vivid highlight for ROI, dimmed pen for outside ROI
        self.accent_color = "#00E5FF" if "dist" in self.curve_type.lower() else "#FF7043"

        # 1. Background Curve Item (plotted for whole trial outside ROI, dimmed style)
        dim_color = QColor(70, 88, 110, 150)
        self.full_curve_item = self.plot_widget.plot(
            self.x_times,
            self.y_data,
            pen=pg.mkPen(color=dim_color, width=1.6, cosmetic=True),
            name="Outside ROI"
        )

        # 2. Shaded ROI Region Band (interactive, can drag boundaries or body)
        t_start = self.trim_range[0] / self.point_rate
        t_end = self.trim_range[1] / self.point_rate
        self.roi_region = pg.LinearRegionItem(
            values=[t_start, t_end],
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(0, 173, 181, 28),
            pen=pg.mkPen(color="#00ADB5", width=1.5, style=Qt.DashLine),
            hoverPen=pg.mkPen(color="#00E5FF", width=2.2, style=Qt.SolidLine),
            movable=True
        )
        self.roi_region.setZValue(-10)
        self.roi_region.sigRegionChanged.connect(self._on_roi_region_dragged)
        self.plot_widget.addItem(self.roi_region)

        # 3. Vivid ROI Curve Item (high-contrast, full-strength highlight)
        self.roi_curve_item = self.plot_widget.plot(
            self.x_times,
            self.y_data,
            pen=pg.mkPen(color=self.accent_color, width=2.6, cosmetic=True),
            name="ROI Range"
        )
        # Compatibility alias
        self.curve_item = self.roi_curve_item

        # 4. Interactive Vertical Time Cursor
        self.time_cursor = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=True,
            pen=pg.mkPen(color="#FFD740", width=1.8, style=Qt.DashLine),
            hoverPen=pg.mkPen(color="#FFF", width=2.2)
        )
        self.time_cursor.setCursor(Qt.SizeHorCursor)
        self.time_cursor.sigDragged.connect(self._on_cursor_dragged)
        self.plot_widget.addItem(self.time_cursor)

        # Hover readout crosshair / label
        self.lbl_hover_readout = QLabel("")
        self.lbl_hover_readout.setStyleSheet(
            "color: #94A3B8; font-size: 11px; padding: 2px 6px; background: transparent;"
        )
        main_layout.addWidget(self.plot_widget, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addWidget(self.lbl_hover_readout)
        bottom_bar.addStretch()
        lbl_hint = QLabel("Drag yellow line to scrub | Drag cyan region to adjust ROI | Click 'Fit ROI' to zoom ROI")
        lbl_hint.setStyleSheet("color: #64748B; font-size: 11px;")
        bottom_bar.addWidget(lbl_hint)
        main_layout.addLayout(bottom_bar)

        # Connect mouse hover tracker
        self.proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=40,
            slot=self._on_mouse_moved
        )

    def _update_stats(self):
        """Compute summary stats (Mean, SD, Min, Max) strictly on the trimmed ROI range."""
        n = len(self.y_data)
        if n == 0:
            self.lbl_stats.setText("No data")
            return

        start_f, end_f = self.trim_range
        start_f = max(0, min(n - 1, start_f))
        end_f = max(start_f, min(n - 1, end_f))
        roi_slice = self.y_data[start_f : end_f + 1]
        valid = roi_slice[~np.isnan(roi_slice)]
        is_trimmed = (start_f > 0 or end_f < n - 1)

        if len(valid) > 0:
            mean_v = float(np.mean(valid))
            std_v = float(np.std(valid))
            min_v = float(np.min(valid))
            max_v = float(np.max(valid))

            if is_trimmed:
                t_start = start_f / self.point_rate
                t_end = end_f / self.point_rate
                stats_str = (
                    f"ROI [F{start_f}–{end_f} | {t_start:.2f}s–{t_end:.2f}s]: "
                    f"Mean: {mean_v:.2f} {self.unit}  |  "
                    f"SD: ±{std_v:.2f}  |  "
                    f"Min: {min_v:.2f}  |  "
                    f"Max: {max_v:.2f}"
                )
                self.lbl_stats.setStyleSheet(
                    "background: #142838; border: 1px solid #00ADB5; border-radius: 12px; "
                    "padding: 4px 12px; color: #E2E8F0; font-size: 12px; font-weight: 500;"
                )
            else:
                stats_str = (
                    f"Full Trial: Mean: {mean_v:.2f} {self.unit}  |  "
                    f"SD: ±{std_v:.2f}  |  "
                    f"Min: {min_v:.2f}  |  "
                    f"Max: {max_v:.2f}"
                )
                self.lbl_stats.setStyleSheet(
                    "background: #1E2433; border: 1px solid #333F54; border-radius: 12px; "
                    "padding: 4px 12px; color: #E2E8F0; font-size: 12px; font-weight: 500;"
                )
        else:
            prefix = f"ROI [F{start_f}–{end_f}]: " if is_trimmed else ""
            stats_str = f"{prefix}No valid tracking data in range"
            self.lbl_stats.setStyleSheet(
                "background: #1E2433; border: 1px solid #333F54; border-radius: 12px; "
                "padding: 4px 12px; color: #94A3B8; font-size: 12px; font-weight: 500;"
            )

        self.lbl_stats.setText(stats_str)

    def _plot_curve(self):
        """Update plotted X and Y data based on current x_axis_mode and ROI highlight state."""
        n = len(self.y_data)
        if n == 0:
            return

        x_data = self.x_times if self.x_axis_mode == "time" else self.x_frames
        start_f, end_f = self.trim_range
        start_f = max(0, min(n - 1, start_f))
        end_f = max(start_f, min(n - 1, end_f))
        is_trimmed = (start_f > 0 or end_f < n - 1)

        # Update LinearRegionItem bounds
        if hasattr(self, 'roi_region') and self.roi_region is not None:
            self.roi_region.blockSignals(True)
            if self.x_axis_mode == "time":
                self.roi_region.setRegion([start_f / self.point_rate, end_f / self.point_rate])
            else:
                self.roi_region.setRegion([float(start_f), float(end_f)])
            self.roi_region.setVisible(is_trimmed)
            self.roi_region.blockSignals(False)

        roi_x = x_data[start_f : end_f + 1]
        roi_y = self.y_data[start_f : end_f + 1]

        if self.crop_to_roi and is_trimmed:
            # Show ONLY the trimmed ROI section
            self.full_curve_item.clear()
            self.roi_curve_item.setData(roi_x, roi_y)
        elif is_trimmed:
            # Highlight ROI section within full curve (full curve outside ROI is dimmed)
            self.full_curve_item.setData(x_data, self.y_data)
            self.roi_curve_item.setData(roi_x, roi_y)
        else:
            # Full trial, not trimmed
            self.full_curve_item.clear()
            self.roi_curve_item.setData(x_data, self.y_data)

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Update ROI range programmatically (e.g. from timeline synchronization)."""
        n = len(self.y_data)
        start_f = max(0, min(n - 1, start_frame))
        end_f = max(start_f, min(n - 1, end_frame))
        if (start_f, end_f) == self.trim_range:
            return
        self.trim_range = (start_f, end_f)
        self._update_stats()
        self._plot_curve()
        self.update_frame(self.current_frame)

    def _on_roi_region_dragged(self):
        """Called when user drags ROI shaded region or handles on the plot."""
        if not hasattr(self, 'roi_region') or self.roi_region is None:
            return
        bounds = self.roi_region.getRegion()
        if self.x_axis_mode == "time":
            start_f = int(round(bounds[0] * self.point_rate))
            end_f = int(round(bounds[1] * self.point_rate))
        else:
            start_f = int(round(bounds[0]))
            end_f = int(round(bounds[1]))

        n = len(self.y_data)
        start_f = max(0, min(n - 1, start_f))
        end_f = max(start_f, min(n - 1, end_f))

        self.trim_range = (start_f, end_f)
        self._update_stats()

        x_data = self.x_times if self.x_axis_mode == "time" else self.x_frames
        roi_x = x_data[start_f : end_f + 1]
        roi_y = self.y_data[start_f : end_f + 1]
        self.roi_curve_item.setData(roi_x, roi_y)

        self.update_frame(self.current_frame)
        self.trimRangeChanged.emit(start_f, end_f)

    def _on_crop_toggled(self, checked: bool):
        """Toggle between highlighting ROI vs displaying ROI only."""
        self.crop_to_roi = checked
        if checked:
            self.btn_crop_roi.setText("Showing ROI Only")
            self.btn_crop_roi.setStyleSheet("background: #00ADB5; color: #000; font-weight: 700;")
            self.fit_roi()
        else:
            self.btn_crop_roi.setText("Crop to ROI")
            self.btn_crop_roi.setStyleSheet("")
        self._plot_curve()

    def fit_roi(self):
        """Auto fit horizontal and vertical view strictly to the trimmed ROI bounds."""
        n = len(self.y_data)
        if n == 0:
            return
        start_f, end_f = self.trim_range
        x_data = self.x_times if self.x_axis_mode == "time" else self.x_frames
        x_min = float(x_data[start_f])
        x_max = float(x_data[end_f])
        span = max(1.0 / self.point_rate, x_max - x_min)
        self.plot_item.setXRange(x_min - span * 0.04, x_max + span * 0.04, padding=0.0)

        roi_slice = self.y_data[start_f : end_f + 1]
        valid = roi_slice[~np.isnan(roi_slice)]
        if len(valid) > 0:
            y_min = float(np.min(valid))
            y_max = float(np.max(valid))
            y_span = max(1.0, y_max - y_min)
            self.plot_item.setYRange(y_min - y_span * 0.08, y_max + y_span * 0.08, padding=0.0)
        else:
            self.plot_item.autoRange()

    def auto_range(self):
        """Auto fit view to full curve bounds."""
        x_data = self.x_times if self.x_axis_mode == "time" else self.x_frames
        if len(x_data) > 0:
            x_min, x_max = float(x_data[0]), float(x_data[-1])
            self.plot_item.setXRange(x_min, x_max, padding=0.03)

        valid = self.y_data[~np.isnan(self.y_data)]
        if len(valid) > 0:
            y_min, y_max = float(np.min(valid)), float(np.max(valid))
            span = y_max - y_min
            pad = max(1.0, span * 0.08)
            self.plot_item.setYRange(y_min - pad, y_max + pad, padding=0.0)
        else:
            self.plot_item.autoRange()

    def _on_axis_mode_changed(self, mode_id: int):
        self.x_axis_mode = "time" if mode_id == 0 else "frame"
        if self.x_axis_mode == "time":
            self.plot_item.setLabel("bottom", "Time", units="s")
        else:
            self.plot_item.setLabel("bottom", "Frame Index", units="")

        self._plot_curve()
        self.update_frame(self.current_frame)
        if self.crop_to_roi:
            self.fit_roi()
        else:
            self.auto_range()

    def update_frame(self, frame_idx: int):
        """Called dynamically during playback advances."""
        self.current_frame = frame_idx
        n = len(self.y_data)
        if n == 0:
            return

        clamped_idx = max(0, min(n - 1, frame_idx))
        val = self.y_data[clamped_idx]
        start_f, end_f = self.trim_range
        in_roi = (start_f <= clamped_idx <= end_f)
        roi_tag = "" if (start_f == 0 and end_f == n - 1) else (" (In ROI)" if in_roi else " (Outside ROI)")

        # Update live value chip
        if np.isnan(val):
            self.lbl_current_val.setText(f"Frame {clamped_idx}: Untracked{roi_tag}")
        else:
            self.lbl_current_val.setText(f"Frame {clamped_idx}: {val:.2f} {self.unit}{roi_tag}")

        # Update cursor line position
        cursor_x = (clamped_idx / self.point_rate) if self.x_axis_mode == "time" else float(clamped_idx)
        self.time_cursor.blockSignals(True)
        self.time_cursor.setValue(cursor_x)
        self.time_cursor.blockSignals(False)

    def _on_cursor_dragged(self):
        pos_val = float(self.time_cursor.value())
        if self.x_axis_mode == "time":
            time_s = max(0.0, pos_val)
            frame_idx = int(round(time_s * self.point_rate))
        else:
            frame_idx = int(round(pos_val))
            time_s = frame_idx / self.point_rate

        clamped_f = max(0, min(len(self.y_data) - 1, frame_idx))
        val = self.y_data[clamped_f]
        start_f, end_f = self.trim_range
        in_roi = (start_f <= clamped_f <= end_f)
        roi_tag = "" if (start_f == 0 and end_f == len(self.y_data) - 1) else (" (In ROI)" if in_roi else " (Outside ROI)")

        if not np.isnan(val):
            self.lbl_current_val.setText(f"Frame {clamped_f}: {val:.2f} {self.unit}{roi_tag}")

        self.timeCursorMoved.emit(time_s)

    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_item.vb.mapSceneToView(pos)
            x_val = mouse_point.x()
            y_val = mouse_point.y()
            start_f, end_f = self.trim_range

            if self.x_axis_mode == "time":
                f_idx = int(round(x_val * self.point_rate))
                in_roi = (start_f <= f_idx <= end_f)
                roi_str = " [In ROI]" if in_roi else " [Outside ROI]"
                self.lbl_hover_readout.setText(
                    f"Hover: Time = {x_val:.3f} s (Frame {f_idx}){roi_str} | Value = {y_val:.2f} {self.unit}"
                )
            else:
                f_idx = int(round(x_val))
                t_val = f_idx / self.point_rate
                in_roi = (start_f <= f_idx <= end_f)
                roi_str = " [In ROI]" if in_roi else " [Outside ROI]"
                self.lbl_hover_readout.setText(
                    f"Hover: Frame = {x_val:.1f} ({t_val:.3f} s){roi_str} | Value = {y_val:.2f} {self.unit}"
                )

    def export_csv(self):
        """Export measurement data to a CSV file (honoring ROI range)."""
        default_name = self.curve_title.replace(" ", "_").replace(":", "_").replace("↔", "to") + ".csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Curve Data to CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return

        start_f, end_f = self.trim_range
        row_range = range(start_f, end_f + 1) if self.crop_to_roi else range(len(self.y_data))

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Frame,Time_s,{self.curve_title} ({self.unit}),In_ROI\n")
                for i in row_range:
                    t = i / self.point_rate
                    val_str = f"{self.y_data[i]:.4f}" if not np.isnan(self.y_data[i]) else ""
                    in_roi_str = "1" if (start_f <= i <= end_f) else "0"
                    f.write(f"{i},{t:.5f},{val_str},{in_roi_str}\n")
            QMessageBox.information(self, "Export Successful", f"Saved curve data to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")

    def export_image(self):
        """Export high-res plot image."""
        default_name = self.curve_title.replace(" ", "_").replace(":", "_").replace("↔", "to") + ".png"
        path, _ = QFileDialog.getSaveFileName(self, "Save Plot Image", default_name, "PNG Image (*.png);;JPEG Image (*.jpg)")
        if not path:
            return

        try:
            exporter = pyqtgraph.exporters.ImageExporter(self.plot_item)
            exporter.export(path)
            QMessageBox.information(self, "Saved", f"Plot image saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save image:\n{e}")

    def closeEvent(self, event):
        self.windowClosed.emit()
        super().closeEvent(event)

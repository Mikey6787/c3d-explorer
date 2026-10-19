"""Synchronized 2D plotting panel for analog channels, ground reaction forces, and events."""

from typing import Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QComboBox, QCheckBox,
    QLineEdit, QFrame, QSizePolicy, QButtonGroup
)
import pyqtgraph as pg

from core.data_models import C3DTrial, C3DEvent
from gui.plotter_window import enable_axis_wheel_zoom


# Distinct color cycle for multi-curve plotting
PLOT_COLORS = [
    "#00E5FF",  # Cyan
    "#FF5252",  # Vivid Red
    "#69F0AE",  # Mint Green
    "#FFD740",  # Amber Yellow
    "#E040FB",  # Purple
    "#40C4FF",  # Sky Blue
    "#FF6E40",  # Coral Orange
    "#EEFF41",  # Lime
    "#B388FF",  # Violet
    "#FFAB40"   # Tangerine
]


class PlotPanel(QWidget):
    """
    High-performance 2D plotting panel for:
    - Ground reaction forces (Fx, Fy, Fz)
    - Ground reaction moments (Mx, My, Mz)
    - Analog EMG / transducer channels
    - Synchronized playback time cursor
    - Event indicators (vertical dashed lines)
    """
    timeCursorMoved = Signal(float)       # Emitted when user drags cursor on plot
    trimRangeChanged = Signal(int, int)   # Emitted when user drags ROI bounds on plot

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trial: Optional[C3DTrial] = None
        self.current_time: float = 0.0
        self.current_frame: int = 0
        self.x_axis_mode: str = "frame"  # "frame" (default) or "time"
        self.trim_range: Optional[Tuple[int, int]] = None
        self.roi_region: Optional[pg.LinearRegionItem] = None
        self.active_curves: Dict[str, pg.PlotDataItem] = {}
        self.event_lines: List[pg.InfiniteLine] = []
        self._color_counter: int = 0

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Top Control Bar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(8)

        lbl_title = QLabel("Time-Series Signals:")
        lbl_title.setStyleSheet("font-weight: 600; color: #ECEFF4;")
        ctrl_bar.addWidget(lbl_title)

        # Quick preset buttons
        btn_forces = QPushButton("Forces (Fz / F)")
        btn_forces.clicked.connect(self._preset_forces)
        ctrl_bar.addWidget(btn_forces)

        btn_moments = QPushButton("Moments (M)")
        btn_moments.clicked.connect(self._preset_moments)
        ctrl_bar.addWidget(btn_moments)

        btn_analogs = QPushButton("Analog Channels")
        btn_analogs.clicked.connect(self._preset_analogs)
        ctrl_bar.addWidget(btn_analogs)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._clear_selected_channels)
        ctrl_bar.addWidget(btn_clear)

        ctrl_bar.addSpacing(8)

        # Horizontal Axis Mode (Frame vs Time, Frame is default)
        self.btn_mode_frame = QPushButton("Frame")
        self.btn_mode_frame.setCheckable(True)
        self.btn_mode_frame.setChecked(True)
        self.btn_mode_frame.setCursor(Qt.PointingHandCursor)
        self.btn_mode_frame.setToolTip("Display horizontal axis by Frame number (default)")

        self.btn_mode_time = QPushButton("Time (s)")
        self.btn_mode_time.setCheckable(True)
        self.btn_mode_time.setChecked(False)
        self.btn_mode_time.setCursor(Qt.PointingHandCursor)
        self.btn_mode_time.setToolTip("Display horizontal axis by Time (seconds)")

        self.btn_group_axis = QButtonGroup(self)
        self.btn_group_axis.addButton(self.btn_mode_frame, 0)
        self.btn_group_axis.addButton(self.btn_mode_time, 1)
        self.btn_group_axis.idClicked.connect(self._on_axis_mode_changed)

        ctrl_bar.addWidget(self.btn_mode_frame)
        ctrl_bar.addWidget(self.btn_mode_time)

        ctrl_bar.addStretch()

        btn_fit_roi = QPushButton("Fit ROI")
        btn_fit_roi.setCursor(Qt.PointingHandCursor)
        btn_fit_roi.setToolTip("Auto-fit horizontal and vertical zoom to trimmed Region of Interest (ROI)")
        btn_fit_roi.clicked.connect(self.fit_roi)
        ctrl_bar.addWidget(btn_fit_roi)

        btn_autorange = QPushButton("Fit Full")
        btn_autorange.setCursor(Qt.PointingHandCursor)
        btn_autorange.setToolTip("Auto-fit horizontal and vertical zoom to entire trial")
        btn_autorange.clicked.connect(self.auto_range)
        ctrl_bar.addWidget(btn_autorange)

        ctrl_bar.addSpacing(6)
        self.lbl_roi_status = QLabel("ROI: Full Trial")
        self.lbl_roi_status.setStyleSheet(
            "background: #1E2433; border: 1px solid #333F54; border-radius: 10px; "
            "padding: 3px 8px; color: #94A3B8; font-size: 11px;"
        )
        ctrl_bar.addWidget(self.lbl_roi_status)

        main_layout.addLayout(ctrl_bar)

        # Splitter: Left channel selector | Right PyQtGraph PlotWidget
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(4)

        # --- Left Channel Selector Widget ---
        selector_widget = QWidget()
        sel_layout = QVBoxLayout(selector_widget)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(4)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter channels...")
        self.search_box.textChanged.connect(self._filter_channel_list)
        sel_layout.addWidget(self.search_box)

        self.channel_list = QListWidget()
        self.channel_list.itemChanged.connect(self._on_channel_item_changed)
        sel_layout.addWidget(self.channel_list)

        selector_widget.setMaximumWidth(260)
        selector_widget.setMinimumWidth(180)
        splitter.addWidget(selector_widget)

        # --- Right PyQtGraph Plot Widget ---
        pg.setConfigOptions(antialias=False)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#151720")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("bottom", "Frame", units="")
        self.plot_widget.setLabel("left", "Amplitude / Force", units="N / V")
        self.plot_widget.addLegend(offset=(10, 10))
        enable_axis_wheel_zoom(self.plot_widget)

        # Vertical Time / Frame Scrubber Cursor (starts at Frame 1)
        self.time_cursor = pg.InfiniteLine(
            pos=1.0,
            angle=90,
            movable=True,
            pen=pg.mkPen(color="#00ADB5", width=2, style=Qt.SolidLine)
        )
        self.time_cursor.sigPositionChanged.connect(self._on_cursor_dragged)
        self.plot_widget.addItem(self.time_cursor)

        # On-curve hover indicator dot & floating label (added directly to ViewBox with ignoreBounds)
        self.hover_dot = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen("#FFFFFF", width=1.5),
            brush=pg.mkBrush("#00E5FF")
        )
        self.hover_dot.setZValue(120)
        self.hover_dot.hide()
        self.plot_widget.getViewBox().addItem(self.hover_dot, ignoreBounds=True)

        self.hover_label = pg.TextItem(anchor=(0.5, 1.2))
        self.hover_label.setZValue(121)
        self.hover_label.hide()
        self.plot_widget.getViewBox().addItem(self.hover_label, ignoreBounds=True)

        # Hide hover items when mouse leaves plot widget
        orig_leave = self.plot_widget.leaveEvent
        def _on_plot_leave(event):
            if hasattr(self, "hover_dot"):
                self.hover_dot.hide()
            if hasattr(self, "hover_label"):
                self.hover_label.hide()
            orig_leave(event)
        self.plot_widget.leaveEvent = _on_plot_leave

        self.mouse_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=40,
            slot=self._on_mouse_moved
        )

        splitter.addWidget(self.plot_widget)
        splitter.setSizes([200, 800])
        main_layout.addWidget(splitter)

    # ---------------------------------------------------------
    # Data Loading
    # ---------------------------------------------------------
    def load_trial(self, trial: C3DTrial):
        """Populate available channel list and draw event lines."""
        self.trial = trial
        self.current_time = 0.0
        self.current_frame = 0

        # Remove existing curves
        for curve in list(self.active_curves.values()):
            self.plot_widget.removeItem(curve)
        self.active_curves.clear()

        # Remove existing event lines
        for line in self.event_lines:
            self.plot_widget.removeItem(line)
        self.event_lines.clear()

        # Re-add time cursor line
        if self.time_cursor not in self.plot_widget.getPlotItem().items:
            self.plot_widget.addItem(self.time_cursor)
        self.time_cursor.setValue(1.0 if self.x_axis_mode == "frame" else 0.0)

        # Ensure hover dot and label are present in the ViewBox
        vb = self.plot_widget.getViewBox()
        if hasattr(self, "hover_dot"):
            if self.hover_dot not in vb.addedItems:
                vb.addItem(self.hover_dot, ignoreBounds=True)
            self.hover_dot.hide()

        if hasattr(self, "hover_label"):
            if self.hover_label not in vb.addedItems:
                vb.addItem(self.hover_label, ignoreBounds=True)
            self.hover_label.hide()

        # Draw vertical lines for events
        self._build_event_lines()

        # Initialize trim range to full trial
        self.trim_range = (0, self.trial.point_frame_count - 1)
        self.set_trim_range(0, self.trial.point_frame_count - 1)

        # Populate Channel List
        self.channel_list.blockSignals(True)
        self.channel_list.clear()

        # 1. Force plates channels (Forces & Moments)
        for fp in self.trial.force_platforms:
            if fp.forces is not None:
                for axis_idx, axis_name in enumerate(["Fx", "Fy", "Fz"]):
                    item = QListWidgetItem(f"FP{fp.id}_{axis_name}")
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    item.setData(Qt.UserRole, ("force", fp.id - 1, axis_idx))
                    self.channel_list.addItem(item)

            if fp.moments is not None:
                for axis_idx, axis_name in enumerate(["Mx", "My", "Mz"]):
                    item = QListWidgetItem(f"FP{fp.id}_{axis_name}")
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    item.setData(Qt.UserRole, ("moment", fp.id - 1, axis_idx))
                    self.channel_list.addItem(item)

        # 2. General Analog Channels
        for ch_name in sorted(list(self.trial.analogs.keys())):
            item = QListWidgetItem(ch_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, ("analog", ch_name))
            self.channel_list.addItem(item)

        self.channel_list.blockSignals(False)

        # By default, check vertical force (Fz) of available plates
        self._preset_forces()

    def _build_event_lines(self):
        """Draw vertical dashed lines at event timestamps."""
        for line in self.event_lines:
            self.plot_widget.removeItem(line)
        self.event_lines.clear()
        if not self.trial:
            return

        for ev in self.trial.events:
            line_pos = (ev.frame + 1) if self.x_axis_mode == "frame" else ev.time
            line = pg.InfiniteLine(
                pos=line_pos,
                angle=90,
                movable=False,
                pen=pg.mkPen(color=ev.icon_color, width=1.5, style=Qt.DashLine)
            )
            line.setZValue(5)
            line.setToolTip(f"{ev.display_name} | Frame {ev.frame + 1} ({ev.time:.3f} s)")
            self.plot_widget.addItem(line)
            self.event_lines.append(line)

    def reload_events(self):
        """Rebuild event vertical marker lines on the plot."""
        self._build_event_lines()

    def _filter_channel_list(self, text: str):
        text_lower = text.strip().lower()
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            item.setHidden(text_lower not in item.text().lower())

    def _preset_forces(self):
        """Quick check Fz (and Fx/Fy) across all force plates."""
        self.channel_list.blockSignals(True)
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            txt = item.text()
            if "Fz" in txt or "_F" in txt:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self.channel_list.blockSignals(False)
        self._replot_active_channels()

    def _preset_moments(self):
        """Quick check moments across all force plates."""
        self.channel_list.blockSignals(True)
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            item.setCheckState(Qt.Checked if "_M" in item.text() else Qt.Unchecked)
        self.channel_list.blockSignals(False)
        self._replot_active_channels()

    def _preset_analogs(self):
        """Quick check first 6 analog channels."""
        self.channel_list.blockSignals(True)
        analog_checked = 0
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            role = item.data(Qt.UserRole)
            if role and role[0] == "analog" and analog_checked < 6:
                item.setCheckState(Qt.Checked)
                analog_checked += 1
            else:
                item.setCheckState(Qt.Unchecked)
        self.channel_list.blockSignals(False)
        self._replot_active_channels()

    def _clear_selected_channels(self):
        self.channel_list.blockSignals(True)
        for i in range(self.channel_list.count()):
            self.channel_list.item(i).setCheckState(Qt.Unchecked)
        self.channel_list.blockSignals(False)
        if hasattr(self, "hover_dot"):
            self.hover_dot.hide()
            self.hover_label.hide()
        self._replot_active_channels()

    def _toggle_downsampling(self, enabled: bool):
        self.set_downsampling(enabled)

    def set_downsampling(self, enabled: bool):
        plot_item = self.plot_widget.getPlotItem()
        if enabled:
            plot_item.setDownsampling(ds=True, auto=True, mode='peak')
            plot_item.setClipToView(True)
        else:
            plot_item.setDownsampling(ds=False, auto=False)
            plot_item.setClipToView(False)
        if hasattr(self, 'chk_fast_render') and self.chk_fast_render.isChecked() != enabled:
            self.chk_fast_render.blockSignals(True)
            self.chk_fast_render.setChecked(enabled)
            self.chk_fast_render.blockSignals(False)
        self.plot_widget.replot()

    def set_antialias(self, enabled: bool):
        pg.setConfigOptions(antialias=enabled)
        self.plot_widget.replot()

    def _on_channel_item_changed(self, item: QListWidgetItem):
        """Differentially add or remove only the toggled channel curve for instant responsiveness."""
        if not self.trial:
            return
        ch_key = item.text()
        if item.checkState() == Qt.Checked:
            if ch_key not in self.active_curves:
                self._add_single_channel_curve(item)
                self.auto_range()
        else:
            if ch_key in self.active_curves:
                curve = self.active_curves.pop(ch_key)
                self.plot_widget.removeItem(curve)

    def _add_single_channel_curve(self, item: QListWidgetItem):
        ch_key = item.text()
        role_data = item.data(Qt.UserRole)
        if not role_data:
            return

        y_data = None
        time_vec = None
        kind = role_data[0]

        if kind == "force":
            fp_idx, axis_idx = role_data[1], role_data[2]
            if fp_idx < len(self.trial.force_platforms):
                fp = self.trial.force_platforms[fp_idx]
                if fp.forces is not None:
                    y_data = fp.forces[:, axis_idx]
                    rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
                    p_rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
                    if self.x_axis_mode == "frame":
                        subsamples = max(1, int(round(rate / p_rate)))
                        time_vec = 1.0 + np.arange(len(y_data), dtype=np.float32) * (1.0 / subsamples)
                    else:
                        time_vec = np.arange(len(y_data), dtype=np.float32) / rate

        elif kind == "moment":
            fp_idx, axis_idx = role_data[1], role_data[2]
            if fp_idx < len(self.trial.force_platforms):
                fp = self.trial.force_platforms[fp_idx]
                if fp.moments is not None:
                    y_data = fp.moments[:, axis_idx]
                    rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
                    p_rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
                    if self.x_axis_mode == "frame":
                        subsamples = max(1, int(round(rate / p_rate)))
                        time_vec = 1.0 + np.arange(len(y_data), dtype=np.float32) * (1.0 / subsamples)
                    else:
                        time_vec = np.arange(len(y_data), dtype=np.float32) / rate

        elif kind == "analog":
            ch_name = role_data[1]
            if ch_name in self.trial.analogs:
                y_data = self.trial.analogs[ch_name]
                rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
                p_rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
                if self.x_axis_mode == "frame":
                    subsamples = max(1, int(round(rate / p_rate)))
                    time_vec = 1.0 + np.arange(len(y_data), dtype=np.float32) * (1.0 / subsamples)
                else:
                    time_vec = np.arange(len(y_data), dtype=np.float32) / rate

        elif kind == "custom":
            y_data = role_data[1]
            rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
            if self.x_axis_mode == "frame":
                time_vec = 1.0 + np.arange(len(y_data), dtype=np.float32)
            else:
                time_vec = np.arange(len(y_data), dtype=np.float32) / rate

        if y_data is not None and time_vec is not None:
            col = PLOT_COLORS[self._color_counter % len(PLOT_COLORS)]
            self._color_counter += 1
            curve = self.plot_widget.plot(
                time_vec,
                y_data,
                pen=pg.mkPen(color=col, width=1.8, cosmetic=True),
                name=ch_key
            )
            self.active_curves[ch_key] = curve

    def _replot_active_channels(self):
        """Refresh curves according to checked channels in channel_list."""
        if not self.trial:
            return

        # Remove existing curves
        for curve in self.active_curves.values():
            self.plot_widget.removeItem(curve)
        self.active_curves.clear()

        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            if item.checkState() == Qt.Checked:
                self._add_single_channel_curve(item)

        self.auto_range()

    def add_custom_curve(self, label: str, y_data: np.ndarray):
        """Add a custom signal (e.g. measured distance or angle) and plot it."""
        self.channel_list.blockSignals(True)
        found = False
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            if item.text() == label:
                item.setData(Qt.UserRole, ("custom", y_data))
                item.setCheckState(Qt.Checked)
                found = True
                break

        if not found:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, ("custom", y_data))
            self.channel_list.insertItem(0, item)

        self.channel_list.blockSignals(False)
        self._replot_active_channels()

    def plot_marker(self, marker_name: str, marker_data: np.ndarray):
        """Add marker coordinates (X, Y, Z) to 2D plot panel."""
        for comp_name, comp_idx in [("X", 0), ("Y", 1), ("Z", 2)]:
            lbl = f"{marker_name} ({comp_name})"
            self.add_custom_curve(lbl, marker_data[:, comp_idx])

    def plot_markers(self, markers: Dict[str, np.ndarray]):
        """Add multiple markers' coordinates (X, Y, Z) to 2D plot panel."""
        for name, data in markers.items():
            self.plot_marker(name, data)

    # ---------------------------------------------------------
    # Cursor Synchronization
    # ---------------------------------------------------------
    def set_frame(self, frame_idx: int):
        self.current_frame = frame_idx
        rate = self.trial.point_rate if (self.trial and self.trial.point_rate > 0) else 100.0
        self.current_time = frame_idx / rate
        if self.time_cursor is not None:
            self.time_cursor.blockSignals(True)
            cur_pos = float(frame_idx + 1) if self.x_axis_mode == "frame" else self.current_time
            self.time_cursor.setValue(cur_pos)
            self.time_cursor.blockSignals(False)

    def set_time(self, time_s: float):
        """Update synchronized vertical time cursor without emitting signals."""
        self.current_time = time_s
        rate = self.trial.point_rate if (self.trial and self.trial.point_rate > 0) else 100.0
        self.current_frame = int(round(time_s * rate))
        if self.time_cursor is not None:
            self.time_cursor.blockSignals(True)
            cur_pos = float(self.current_frame + 1) if self.x_axis_mode == "frame" else time_s
            self.time_cursor.setValue(cur_pos)
            self.time_cursor.blockSignals(False)

    def _on_cursor_dragged(self):
        if self.time_cursor is not None:
            pos_val = float(self.time_cursor.value())
            rate = self.trial.point_rate if (self.trial and self.trial.point_rate > 0) else 100.0
            if self.x_axis_mode == "frame":
                new_time = max(0.0, (pos_val - 1.0) / rate)
            else:
                new_time = max(0.0, pos_val)
            self.timeCursorMoved.emit(new_time)

    def _on_axis_mode_changed(self, mode_id: int):
        self.x_axis_mode = "frame" if mode_id == 0 else "time"
        if self.x_axis_mode == "frame":
            self.plot_widget.setLabel("bottom", "Frame", units="")
        else:
            self.plot_widget.setLabel("bottom", "Time", units="s")
        if hasattr(self, "hover_dot"):
            self.hover_dot.hide()
            self.hover_label.hide()
        self._build_event_lines()
        self._replot_active_channels()
        if hasattr(self, 'current_frame'):
            self.set_frame(self.current_frame)
        if self.trim_range:
            self.set_trim_range(*self.trim_range)
        self.auto_range()

    def _on_mouse_moved(self, evt):
        """Called when mouse moves over the plot. If hovering over a curve, shows label and dot."""
        if not self.active_curves:
            if hasattr(self, "hover_dot"):
                self.hover_dot.hide()
                self.hover_label.hide()
            return

        pos = evt[0] if isinstance(evt, (tuple, list)) else evt
        vb = self.plot_widget.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            if hasattr(self, "hover_dot"):
                self.hover_dot.hide()
                self.hover_label.hide()
            return

        view_pt = vb.mapSceneToView(pos)
        mouse_x = view_pt.x()
        scene_x = pos.x()
        scene_y = pos.y()

        best_curve_label = None
        best_dist_px = float("inf")
        best_snap_x = 0.0
        best_snap_y = 0.0
        best_curve = None
        best_idx = 0

        HOVER_PIXEL_THRESHOLD = 25.0

        for label, curve in self.active_curves.items():
            x_data = (
                curve.xData
                if hasattr(curve, "xData") and curve.xData is not None
                else (curve.getData()[0] if curve.getData() is not None else None)
            )
            y_data = (
                curve.yData
                if hasattr(curve, "yData") and curve.yData is not None
                else (curve.getData()[1] if curve.getData() is not None else None)
            )
            if x_data is None or y_data is None or len(x_data) < 2:
                continue

            idx = int(np.clip(np.searchsorted(x_data, mouse_x), 0, len(x_data) - 1))
            cand_indices = range(max(0, idx - 2), min(len(x_data), idx + 3))

            for i in cand_indices:
                xi = x_data[i]
                yi = y_data[i]
                if np.isnan(yi):
                    continue

                pt_scene = vb.mapViewToScene(QPointF(float(xi), float(yi)))
                d_pt = np.hypot(scene_x - pt_scene.x(), scene_y - pt_scene.y())
                if d_pt < best_dist_px:
                    best_dist_px = d_pt
                    best_curve_label = label
                    best_curve = curve
                    best_snap_x = float(xi)
                    best_snap_y = float(yi)
                    best_idx = i

                if i + 1 < len(x_data):
                    x_next = x_data[i + 1]
                    y_next = y_data[i + 1]
                    if not np.isnan(y_next):
                        pt_next = vb.mapViewToScene(QPointF(float(x_next), float(y_next)))
                        vx = pt_next.x() - pt_scene.x()
                        vy = pt_next.y() - pt_scene.y()
                        len_sq = vx * vx + vy * vy
                        if len_sq > 1e-4:
                            wx = scene_x - pt_scene.x()
                            wy = scene_y - pt_scene.y()
                            t = max(0.0, min(1.0, (wx * vx + wy * vy) / len_sq))
                            proj_x = pt_scene.x() + t * vx
                            proj_y = pt_scene.y() + t * vy
                            d_seg = np.hypot(scene_x - proj_x, scene_y - proj_y)
                            if d_seg < best_dist_px:
                                best_dist_px = d_seg
                                best_curve_label = label
                                best_curve = curve
                                if t < 0.5:
                                    best_snap_x = float(xi)
                                    best_snap_y = float(yi)
                                    best_idx = i
                                else:
                                    best_snap_x = float(x_next)
                                    best_snap_y = float(y_next)
                                    best_idx = i + 1

        if best_curve_label is not None and best_dist_px <= HOVER_PIXEL_THRESHOLD and best_curve is not None:
            # Color from curve pen
            try:
                pen_color = best_curve.opts['pen'].color().name()
            except Exception:
                pen_color = "#00ADB5"

            # Determine unit
            unit = ""
            if "FP" in best_curve_label:
                if "_F" in best_curve_label or any(best_curve_label.endswith(k) for k in ["_Fx", "_Fy", "_Fz"]):
                    unit = "N"
                elif "_M" in best_curve_label or any(best_curve_label.endswith(k) for k in ["_Mx", "_My", "_Mz"]):
                    unit = "N·mm"
            elif self.trial and hasattr(self.trial, "analog_units") and best_curve_label in self.trial.analog_units:
                unit = self.trial.analog_units[best_curve_label]
            elif "dist" in best_curve_label.lower():
                unit = "mm"
            elif "angle" in best_curve_label.lower():
                unit = "°"

            val_text = f"{best_snap_y:.2f}"
            unit_str = f" {unit}" if unit else ""

            # Frame & time string
            p_rate = self.trial.point_rate if (self.trial and self.trial.point_rate > 0) else 100.0
            if self.x_axis_mode == "frame":
                f_num = best_snap_x
                t_s = max(0.0, (f_num - 1.0) / p_rate)
                frame_time_str = f"Frame {f_num:.1f} • {t_s:.3f} s" if (f_num % 1 != 0) else f"Frame {int(f_num)} • {t_s:.3f} s"
            else:
                t_s = best_snap_x
                f_num = 1.0 + t_s * p_rate
                frame_time_str = f"Frame {f_num:.1f} • {t_s:.3f} s" if (f_num % 1 != 0) else f"Frame {int(round(f_num))} • {t_s:.3f} s"

            # Dynamic anchor positioning
            view_range_x = vb.viewRange()[0]
            view_range_y = vb.viewRange()[1]
            x_span = max(1e-9, view_range_x[1] - view_range_x[0])
            y_span = max(1e-9, view_range_y[1] - view_range_y[0])
            x_frac = (best_snap_x - view_range_x[0]) / x_span
            y_frac = (best_snap_y - view_range_y[0]) / y_span

            anchor_y = -0.2 if y_frac > 0.80 else 1.25
            if x_frac > 0.85:
                anchor_x = 1.05
            elif x_frac < 0.15:
                anchor_x = -0.05
            else:
                anchor_x = 0.5

            html = (
                f'<div style="background-color: rgba(18, 24, 38, 0.94); '
                f'border: 1.5px solid {pen_color}; border-radius: 6px; '
                f'padding: 4px 8px; color: #FFFFFF; font-family: sans-serif; font-size: 11px; line-height: 1.3;">'
                f'<span style="color: {pen_color}; font-weight: 600;">{best_curve_label}</span><br/>'
                f'<span style="color: #FFFFFF; font-size: 13px; font-weight: bold;">{val_text}{unit_str}</span><br/>'
                f'<span style="color: #94A3B8; font-size: 10px;">{frame_time_str}</span>'
                f'</div>'
            )

            self.hover_dot.setData([best_snap_x], [best_snap_y])
            self.hover_dot.setBrush(pg.mkBrush(pen_color))
            self.hover_dot.show()

            self.hover_label.setAnchor((anchor_x, anchor_y))
            self.hover_label.setHtml(html)
            self.hover_label.setPos(best_snap_x, best_snap_y)
            self.hover_label.show()
        else:
            self.hover_dot.hide()
            self.hover_label.hide()

    def auto_range(self):
        """Fit plot view to active curves."""
        self.plot_widget.autoRange()

    def apply_theme(self, theme_dict: dict):
        """Update 2D plot background and axis pens to match theme."""
        bg = theme_dict.get("plot_bg", "#151720")
        axis_col = theme_dict.get("plot_axis_color", "#ECEFF4")
        accent = theme_dict.get("accent", "#00ADB5")
        self.plot_widget.setBackground(bg)
        try:
            self.plot_widget.getPlotItem().getAxis('bottom').setTextPen(axis_col)
            self.plot_widget.getPlotItem().getAxis('left').setTextPen(axis_col)
            if self.time_cursor is not None:
                self.time_cursor.setPen(pg.mkPen(color=accent, width=2, style=Qt.SolidLine))
        except Exception:
            pass

    # ---------------------------------------------------------
    # ROI & Trim Synchronization
    # ---------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        main_win = self.window()
        if hasattr(main_win, 'timeline') and hasattr(main_win.timeline, 'trim_start_frame'):
            self.set_trim_range(main_win.timeline.trim_start_frame, main_win.timeline.trim_end_frame)
        if hasattr(main_win, 'playback') and hasattr(main_win.playback, 'current_frame'):
            self.set_frame(main_win.playback.current_frame)

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Update ROI Region of Interest shading on the 2D plot."""
        if not self.trial:
            return
        n = self.trial.point_frame_count
        start_f = max(0, min(n - 1, start_frame))
        end_f = max(start_f, min(n - 1, end_frame))
        self.trim_range = (start_f, end_f)

        rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0
        is_trimmed = (start_f > 0 or end_f < n - 1)

        if self.x_axis_mode == "frame":
            r_start = float(start_f + 1)
            r_end = float(end_f + 1)
        else:
            r_start = start_f / rate
            r_end = end_f / rate

        if self.roi_region is None:
            self.roi_region = pg.LinearRegionItem(
                values=[r_start, r_end],
                orientation=pg.LinearRegionItem.Vertical,
                brush=pg.mkBrush(0, 173, 181, 28),
                pen=pg.mkPen(color="#00ADB5", width=1.5, style=Qt.DashLine),
                hoverPen=pg.mkPen(color="#00E5FF", width=2.0, style=Qt.SolidLine),
                movable=True
            )
            self.roi_region.setZValue(-10)
            self.roi_region.sigRegionChanged.connect(self._on_roi_region_dragged)
            self.plot_widget.addItem(self.roi_region)
        else:
            self.roi_region.blockSignals(True)
            self.roi_region.setRegion([r_start, r_end])
            self.roi_region.blockSignals(False)

        self.roi_region.setVisible(is_trimmed)

        if hasattr(self, 'lbl_roi_status'):
            if is_trimmed:
                t_s = start_f / rate
                t_e = end_f / rate
                self.lbl_roi_status.setText(f"ROI: F{start_f + 1}–{end_f + 1} ({t_s:.2f}s–{t_e:.2f}s)")
                self.lbl_roi_status.setStyleSheet(
                    "background: #142838; border: 1px solid #00ADB5; border-radius: 10px; "
                    "padding: 3px 8px; color: #00E5FF; font-size: 11px; font-weight: 600;"
                )
            else:
                self.lbl_roi_status.setText("ROI: Full Trial")
                self.lbl_roi_status.setStyleSheet(
                    "background: #1E2433; border: 1px solid #333F54; border-radius: 10px; "
                    "padding: 3px 8px; color: #94A3B8; font-size: 11px;"
                )

    def _on_roi_region_dragged(self):
        if not self.roi_region or not self.trial:
            return
        bounds = self.roi_region.getRegion()
        n = self.trial.point_frame_count
        rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0

        if self.x_axis_mode == "frame":
            start_f = int(round(bounds[0])) - 1
            end_f = int(round(bounds[1])) - 1
        else:
            start_f = int(round(bounds[0] * rate))
            end_f = int(round(bounds[1] * rate))

        start_f = max(0, min(n - 1, start_f))
        end_f = max(start_f, min(n - 1, end_f))
        self.trim_range = (start_f, end_f)
        self.trimRangeChanged.emit(start_f, end_f)

    def fit_roi(self):
        """Fit horizontal and vertical zoom strictly to trimmed ROI range."""
        if not self.trial:
            self.auto_range()
            return

        # Query parent main window timeline if self.trim_range is not set yet
        main_win = self.window()
        if hasattr(main_win, 'timeline') and hasattr(main_win.timeline, 'trim_start_frame'):
            start_f = main_win.timeline.trim_start_frame
            end_f = main_win.timeline.trim_end_frame
            self.trim_range = (start_f, end_f)
        elif self.trim_range:
            start_f, end_f = self.trim_range
        else:
            start_f, end_f = (0, max(0, self.trial.point_frame_count - 1))
            self.trim_range = (start_f, end_f)

        rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0
        if self.x_axis_mode == "frame":
            x_min = float(start_f + 1)
            x_max = float(end_f + 1)
        else:
            x_min = start_f / rate
            x_max = end_f / rate

        span = max(0.01, x_max - x_min)
        self.plot_widget.setXRange(x_min - span * 0.04, x_max + span * 0.04, padding=0.0)

        # Scale vertical Y-axis strictly to the active signals within the ROI bounds
        all_y_min, all_y_max = float("inf"), float("-inf")
        for curve in self.active_curves.values():
            data = curve.getData()
            if data is not None and len(data) == 2 and data[0] is not None and data[1] is not None:
                x_data, y_data = data
                if len(x_data) > 0:
                    mask = (x_data >= (x_min - 1e-4)) & (x_data <= (x_max + 1e-4))
                    if not np.any(mask):
                        i0 = max(0, np.searchsorted(x_data, x_min) - 1)
                        i1 = min(len(x_data), np.searchsorted(x_data, x_max) + 1)
                        roi_y = y_data[i0:i1]
                    else:
                        roi_y = y_data[mask]
                    valid = roi_y[~np.isnan(roi_y)]
                    if len(valid) > 0:
                        all_y_min = min(all_y_min, float(np.min(valid)))
                        all_y_max = max(all_y_max, float(np.max(valid)))

        if all_y_min <= all_y_max and not np.isinf(all_y_min):
            y_span = all_y_max - all_y_min
            pad_y = max(1.0, y_span * 0.08) if y_span > 0 else 1.0
            self.plot_widget.getPlotItem().setYRange(all_y_min - pad_y, all_y_max + pad_y, padding=0.0)

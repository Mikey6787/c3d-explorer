"""Universal Biomechanics Plotter window for plotting markers, forces, and analog signals."""

from typing import Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton, QRadioButton,
    QButtonGroup, QLineEdit, QLabel, QFileDialog, QMessageBox,
    QToolBar, QFrame, QMenu, QCheckBox
)
import pyqtgraph as pg
import pyqtgraph.exporters

from core.data_models import C3DTrial


PLOT_COLORS = [
    "#00E5FF",  # Vivid Cyan
    "#FF5252",  # Vivid Red
    "#69F0AE",  # Mint Green
    "#FFD740",  # Amber Yellow
    "#E040FB",  # Electric Purple
    "#40C4FF",  # Sky Blue
    "#FF6E40",  # Coral Orange
    "#EEFF41",  # Neon Lime
    "#B388FF",  # Soft Violet
    "#FFAB40",  # Tangerine
    "#18FFFF",  # Bright Turquoise
    "#FF4081",  # Pink
]


class UniversalPlotterWindow(QMainWindow):
    """
    Dedicated biomechanics signal and trajectory plotter.
    Allows plotting:
    - Optical markers (X, Y, Z coordinates and 3D resultant norms)
    - Ground reaction forces (Fx, Fy, Fz, Ftotal)
    - Ground reaction moments (Mx, My, Mz)
    - Center of pressure (COPx, COPy, COPz)
    - All analog channels (EMG, transducers)
    - Custom signals (distances, angles)
    Supports switching between Time (s) and Frame index on the horizontal axis.
    """
    timeCursorMoved = Signal(float)  # Emitted when user drags cursor on plot

    def __init__(self, trial: Optional[C3DTrial] = None, current_frame: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("C3D Signal & Marker Plotter")
        self.resize(1100, 680)

        self.trial: Optional[C3DTrial] = trial
        self.current_frame: int = current_frame
        self.x_axis_mode: str = "time"  # "time" or "frame"

        # Signal storage: item_id -> {"x": np.ndarray, "y": np.ndarray, "label": str, "unit": str, "rate": float, "subsamples": int}
        self.active_curves: Dict[str, pg.PlotDataItem] = {}
        self.curve_data: Dict[str, dict] = {}
        self.color_map: Dict[str, str] = {}
        self._next_color_idx: int = 0

        self._setup_ui()
        if self.trial:
            self.load_trial(self.trial)

    def _setup_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top Controls Toolbar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # X-Axis Mode Radio Buttons
        x_group = QGroupBox("Horizontal Axis (X):") if False else None
        top_bar.addWidget(QLabel("<b>Horizontal Axis:</b>"))
        self.rb_time = QRadioButton("Time (seconds)")
        self.rb_time.setChecked(True)
        self.rb_time.toggled.connect(self._on_x_axis_mode_changed)
        top_bar.addWidget(self.rb_time)

        self.rb_frame = QRadioButton("Frame Number")
        self.rb_frame.toggled.connect(self._on_x_axis_mode_changed)
        top_bar.addWidget(self.rb_frame)

        top_bar.addSpacing(16)

        btn_fit = QPushButton("Auto Range / Fit")
        btn_fit.clicked.connect(self.auto_range)
        top_bar.addWidget(btn_fit)

        btn_clear = QPushButton("Clear All Curves")
        btn_clear.clicked.connect(self.clear_all_curves)
        top_bar.addWidget(btn_clear)

        top_bar.addStretch()

        btn_export_csv = QPushButton("Export Plotted to CSV...")
        btn_export_csv.clicked.connect(self.export_plotted_csv)
        top_bar.addWidget(btn_export_csv)

        btn_export_img = QPushButton("Save Image...")
        btn_export_img.clicked.connect(self.export_plot_image)
        top_bar.addWidget(btn_export_img)

        layout.addLayout(top_bar)

        # --- Main Splitter (Left: Tree Selector | Right: Plot) ---
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(4)

        # Left Panel: Search box + Tree of all signals
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter signals (marker, force, emg)...")
        self.search_box.textChanged.connect(self._filter_tree)
        left_layout.addWidget(self.search_box)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Available Signals"])
        self.tree.header().setVisible(False)
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        left_layout.addWidget(self.tree)

        left_widget.setMinimumWidth(260)
        left_widget.setMaximumWidth(360)
        splitter.addWidget(left_widget)

        # Right Panel: PyQtGraph PlotWidget
        pg.setConfigOptions(antialias=False)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#151720")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Value / Amplitude")
        self.plot_widget.addLegend(offset=(10, 10))

        # Vertical Synchronized Time / Frame Cursor
        self.time_cursor = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=True,
            pen=pg.mkPen(color="#00ADB5", width=2, style=Qt.SolidLine),
            label="t={value:.3f}s",
            labelOpts={"color": "#FFFFFF", "fill": "#00ADB5", "position": 0.95}
        )
        self.time_cursor.sigPositionChanged.connect(self._on_cursor_dragged)
        self.plot_widget.addItem(self.time_cursor)

        splitter.addWidget(self.plot_widget)
        splitter.setSizes([300, 800])
        layout.addWidget(splitter)

    # ---------------------------------------------------------
    # Populate Signal Tree
    # ---------------------------------------------------------
    def load_trial(self, trial: C3DTrial):
        """Populate tree with all available signals from the trial."""
        self.trial = trial
        self.clear_all_curves()
        self.tree.blockSignals(True)
        self.tree.clear()

        if not self.trial:
            self.tree.blockSignals(False)
            return

        # 1. 📁 Markers Group
        markers_root = QTreeWidgetItem(["Markers (Trajectory Data)"])
        markers_root.setForeground(0, QColor("#00ADB5"))
        self.tree.addTopLevelItem(markers_root)

        for name in sorted(list(self.trial.markers.keys())):
            m_item = QTreeWidgetItem([name])
            markers_root.addChild(m_item)

            # Components: X, Y, Z, 3D Magnitude
            for comp_name, comp_idx in [("X", 0), ("Y", 1), ("Z", 2), ("3D Norm", -1)]:
                c_item = QTreeWidgetItem([f"{name} ({comp_name})"])
                c_item.setFlags(c_item.flags() | Qt.ItemIsUserCheckable)
                c_item.setCheckState(0, Qt.Unchecked)
                c_item.setData(0, Qt.UserRole, ("marker", name, comp_idx, comp_name))
                m_item.addChild(c_item)

        # 2. 📁 Force Plates Group
        if self.trial.force_platforms:
            fp_root = QTreeWidgetItem(["Force Platforms (Forces & Moments)"])
            fp_root.setForeground(0, QColor("#FF9800"))
            self.tree.addTopLevelItem(fp_root)

            for fp in self.trial.force_platforms:
                fp_item = QTreeWidgetItem([f"Force Platform #{fp.id}"])
                fp_root.addChild(fp_item)

                # Forces
                if fp.forces is not None:
                    for f_name, f_idx in [("Fx", 0), ("Fy", 1), ("Fz", 2), ("F_total", -1)]:
                        c_item = QTreeWidgetItem([f"FP{fp.id}_{f_name} (N)"])
                        c_item.setFlags(c_item.flags() | Qt.ItemIsUserCheckable)
                        c_item.setCheckState(0, Qt.Unchecked)
                        c_item.setData(0, Qt.UserRole, ("force", fp.id - 1, f_idx, f_name))
                        fp_item.addChild(c_item)

                # Moments
                if fp.moments is not None:
                    for m_name, m_idx in [("Mx", 0), ("My", 1), ("Mz", 2)]:
                        c_item = QTreeWidgetItem([f"FP{fp.id}_{m_name} (N.mm)"])
                        c_item.setFlags(c_item.flags() | Qt.ItemIsUserCheckable)
                        c_item.setCheckState(0, Qt.Unchecked)
                        c_item.setData(0, Qt.UserRole, ("moment", fp.id - 1, m_idx, m_name))
                        fp_item.addChild(c_item)

                # Center of Pressure (COP)
                if fp.cop is not None:
                    for cop_name, cop_idx in [("COP_x", 0), ("COP_y", 1), ("COP_z", 2)]:
                        c_item = QTreeWidgetItem([f"FP{fp.id}_{cop_name} (mm)"])
                        c_item.setFlags(c_item.flags() | Qt.ItemIsUserCheckable)
                        c_item.setCheckState(0, Qt.Unchecked)
                        c_item.setData(0, Qt.UserRole, ("cop", fp.id - 1, cop_idx, cop_name))
                        fp_item.addChild(c_item)

        # 3. 📁 Analog Channels Group
        if self.trial.analogs:
            analog_root = QTreeWidgetItem(["Analog Channels"])
            analog_root.setForeground(0, QColor("#69F0AE"))
            self.tree.addTopLevelItem(analog_root)

            for ch_name in sorted(list(self.trial.analogs.keys())):
                u = self.trial.analog_units.get(ch_name, "V")
                c_item = QTreeWidgetItem([f"{ch_name} ({u})"])
                c_item.setFlags(c_item.flags() | Qt.ItemIsUserCheckable)
                c_item.setCheckState(0, Qt.Unchecked)
                c_item.setData(0, Qt.UserRole, ("analog", ch_name, u))
                analog_root.addChild(c_item)

        # Expand top level categories by default
        markers_root.setExpanded(True)
        if self.trial.force_platforms:
            fp_root.setExpanded(True)

        self.tree.blockSignals(False)

        # Update cursor position to current frame
        self.update_frame(self.current_frame)

    # ---------------------------------------------------------
    # Tree Interaction & Filter
    # ---------------------------------------------------------
    def _filter_tree(self, text: str):
        t_low = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            match = t_low in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_match = True
            is_visible = match or child_match or not t_low
            item.setHidden(not is_visible)
            if child_match and t_low:
                item.setExpanded(True)
            return is_visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        role_data = item.data(0, Qt.UserRole)
        if not role_data:
            return

        label = item.text(0)
        is_checked = (item.checkState(0) == Qt.Checked)

        if is_checked:
            self._add_signal(label, role_data)
        else:
            self._remove_signal(label)

    # ---------------------------------------------------------
    # Curve Adding & Removing
    # ---------------------------------------------------------
    def _add_signal(self, label: str, role_data: tuple):
        if not self.trial:
            return

        kind = role_data[0]
        y_data = None
        rate = 100.0
        subsamples = 1

        if kind == "marker":
            m_name, comp_idx, _ = role_data[1], role_data[2], role_data[3]
            if m_name in self.trial.markers:
                m_arr = self.trial.markers[m_name]
                if comp_idx == -1:
                    y_data = np.linalg.norm(m_arr, axis=1)
                else:
                    y_data = m_arr[:, comp_idx]
                rate = self.trial.point_rate
                subsamples = 1

        elif kind == "force":
            fp_idx, f_idx, _ = role_data[1], role_data[2], role_data[3]
            if fp_idx < len(self.trial.force_platforms):
                fp = self.trial.force_platforms[fp_idx]
                if fp.forces is not None:
                    if f_idx == -1:
                        y_data = np.linalg.norm(fp.forces, axis=1)
                    else:
                        y_data = fp.forces[:, f_idx]
                    rate = self.trial.analog_rate
                    subsamples = max(1, self.trial.analog_subsamples)

        elif kind == "moment":
            fp_idx, m_idx, _ = role_data[1], role_data[2], role_data[3]
            if fp_idx < len(self.trial.force_platforms):
                fp = self.trial.force_platforms[fp_idx]
                if fp.moments is not None:
                    y_data = fp.moments[:, m_idx]
                    rate = self.trial.analog_rate
                    subsamples = max(1, self.trial.analog_subsamples)

        elif kind == "cop":
            fp_idx, cop_idx, _ = role_data[1], role_data[2], role_data[3]
            if fp_idx < len(self.trial.force_platforms):
                fp = self.trial.force_platforms[fp_idx]
                if fp.cop is not None:
                    y_data = fp.cop[:, cop_idx]
                    rate = self.trial.analog_rate
                    subsamples = max(1, self.trial.analog_subsamples)

        elif kind == "analog":
            ch_name, _ = role_data[1], role_data[2]
            if ch_name in self.trial.analogs:
                y_data = self.trial.analogs[ch_name]
                rate = self.trial.analog_rate
                subsamples = max(1, self.trial.analog_subsamples)

        if y_data is None:
            return

        # Store data
        self.curve_data[label] = {
            "y": y_data,
            "rate": rate if rate > 0 else 100.0,
            "subsamples": subsamples
        }

        # Assign color
        if label not in self.color_map:
            self.color_map[label] = PLOT_COLORS[self._next_color_idx % len(PLOT_COLORS)]
            self._next_color_idx += 1
        col = self.color_map[label]

        # Compute X vector
        x_vec = self._compute_x_vec(len(y_data), rate, subsamples)

        # Plot curve
        curve = self.plot_widget.plot(
            x_vec,
            y_data,
            pen=pg.mkPen(color=col, width=2.0),
            name=label
        )
        self.active_curves[label] = curve
        self.auto_range()

    def _remove_signal(self, label: str):
        if label in self.active_curves:
            curve = self.active_curves.pop(label)
            self.plot_widget.removeItem(curve)
        self.curve_data.pop(label, None)

    def clear_all_curves(self):
        """Uncheck all tree items and clear the plot."""
        self.tree.blockSignals(True)

        def uncheck_item(item: QTreeWidgetItem):
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(0, Qt.Unchecked)
            for i in range(item.childCount()):
                uncheck_item(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            uncheck_item(self.tree.topLevelItem(i))

        self.tree.blockSignals(False)

        for curve in self.active_curves.values():
            self.plot_widget.removeItem(curve)
        self.active_curves.clear()
        self.curve_data.clear()

    # ---------------------------------------------------------
    # X-Axis Mode (Time vs Frame)
    # ---------------------------------------------------------
    def _compute_x_vec(self, n_points: int, rate: float, subsamples: int) -> np.ndarray:
        if self.x_axis_mode == "frame":
            if subsamples > 1:
                return np.arange(n_points) / float(subsamples)
            return np.arange(n_points, dtype=np.float32)
        else:
            return np.arange(n_points) / float(rate)

    def _on_x_axis_mode_changed(self):
        self.x_axis_mode = "frame" if self.rb_frame.isChecked() else "time"
        if self.x_axis_mode == "frame":
            self.plot_widget.setLabel("bottom", "Frame Number", units="")
            if hasattr(self.time_cursor, "label") and self.time_cursor.label:
                self.time_cursor.label.setFormat("Frame {value:.1f}")
        else:
            self.plot_widget.setLabel("bottom", "Time", units="s")
            if hasattr(self.time_cursor, "label") and self.time_cursor.label:
                self.time_cursor.label.setFormat("t={value:.3f}s")

        # Refresh all plotted curves with new X coordinates
        for label, curve in self.active_curves.items():
            info = self.curve_data.get(label)
            if info:
                y = info["y"]
                x = self._compute_x_vec(len(y), info["rate"], info["subsamples"])
                curve.setData(x, y)

        self.update_frame(self.current_frame)
        self.auto_range()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_frame(self.current_frame)

    # ---------------------------------------------------------
    # Synchronization & Cursor
    # ---------------------------------------------------------
    def update_frame(self, frame_idx: int):
        """Update synchronized playback cursor line when trial advances."""
        self.current_frame = frame_idx
        if not self.trial:
            return

        if self.x_axis_mode == "frame":
            val = float(frame_idx)
            text_str = f"Frame {frame_idx}"
        else:
            val = self.trial.frame_to_time(frame_idx)
            text_str = f"t={val:.3f}s"

        self.time_cursor.blockSignals(True)
        self.time_cursor.setValue(val)
        self.time_cursor.blockSignals(False)

        # Explicitly update floating label text & position because blockSignals suppresses auto-update
        if hasattr(self.time_cursor, "label") and self.time_cursor.label is not None:
            try:
                self.time_cursor.label.setPlainText(text_str)
                self.time_cursor.label.updatePosition()
            except Exception:
                try:
                    self.time_cursor.label.valueChanged()
                except Exception:
                    pass

    def _on_cursor_dragged(self):
        val = float(self.time_cursor.value())
        if self.x_axis_mode == "frame":
            t = val / self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 0.0
            self.current_frame = int(round(val))
            if hasattr(self.time_cursor, "label") and self.time_cursor.label is not None:
                self.time_cursor.label.setPlainText(f"Frame {self.current_frame}")
                self.time_cursor.label.updatePosition()
        else:
            t = val
            self.current_frame = int(round(val * self.trial.point_rate)) if self.trial and self.trial.point_rate > 0 else 0
            if hasattr(self.time_cursor, "label") and self.time_cursor.label is not None:
                self.time_cursor.label.setPlainText(f"t={t:.3f}s")
                self.time_cursor.label.updatePosition()
        self.timeCursorMoved.emit(t)

    def auto_range(self):
        """Fit plot to curves."""
        self.plot_widget.autoRange()

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

    # Alias for playback synchronization
    set_current_frame = update_frame

    # ---------------------------------------------------------
    # Exporters
    # ---------------------------------------------------------
    def export_plotted_csv(self):
        """Export all currently displayed curves into a clean CSV file."""
        if not self.curve_data:
            QMessageBox.information(self, "Export CSV", "No curves are currently plotted.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Signals to CSV", "", "CSV Files (*.csv)")
        if not path:
            return

        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            # Find maximum points
            labels = sorted(list(self.curve_data.keys()))
            max_len = max(len(self.curve_data[lbl]["y"]) for lbl in labels)

            header = ["Index", "Time_s", "Frame"] + labels
            rows = []

            ref_lbl = labels[0]
            ref_rate = self.curve_data[ref_lbl]["rate"]
            ref_sub = self.curve_data[ref_lbl]["subsamples"]

            for i in range(max_len):
                t = i / ref_rate
                f = i / float(ref_sub) if ref_sub > 1 else i
                row = [str(i), f"{t:.5f}", f"{f:.2f}"]
                for lbl in labels:
                    y = self.curve_data[lbl]["y"]
                    val = f"{y[i]:.4f}" if i < len(y) else ""
                    row.append(val)
                rows.append(",".join(row))

            with open(path, "w", encoding="utf-8") as file:
                file.write(",".join(header) + "\n")
                file.write("\n".join(rows) + "\n")

            QMessageBox.information(self, "Export Successful", f"Saved {len(labels)} signals to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")

    def export_plot_image(self):
        """Save plot snapshot to PNG/JPEG."""
        path, _ = QFileDialog.getSaveFileName(self, "Save Plot Image", "", "PNG Image (*.png);;JPEG Image (*.jpg)")
        if not path:
            return
        try:
            exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
            exporter.export(path)
            QMessageBox.information(self, "Saved", f"Plot image saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save image:\n{e}")

    def apply_theme(self, theme_dict: dict):
        """Update 2D plot background and axis pens to match theme."""
        bg = theme_dict.get("plot_bg", "#151720")
        axis_col = theme_dict.get("plot_axis_color", "#ECEFF4")
        accent = theme_dict.get("accent", "#00ADB5")
        self.plot_widget.setBackground(bg)
        try:
            self.plot_widget.getPlotItem().getAxis('bottom').setTextPen(axis_col)
            self.plot_widget.getPlotItem().getAxis('left').setTextPen(axis_col)
            self.time_cursor.setPen(pg.mkPen(color=accent, width=2, style=Qt.SolidLine))
        except Exception:
            pass

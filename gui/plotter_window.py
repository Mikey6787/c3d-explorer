"""Universal Biomechanics Plotter window for plotting markers, forces, and analog signals."""

from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from PySide6.QtCore import Qt, Signal, QObject, QEvent, QPointF
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

# Prevent pyqtgraph AttributeError: 'ScatterPlotItem' object has no attribute 'setAlpha'
if not hasattr(pg.ScatterPlotItem, "setAlpha"):
    pg.ScatterPlotItem.setAlpha = lambda self, alpha, auto=False: None


class PlotAxisZoomFilter(QObject):
    """
    Event filter installed on a PyQtGraph PlotWidget viewport.
    Enables single-axis scaling and zooming without moving/panning:
    - Grabbing (click & drag) on the bottom X-axis scales ONLY the X-axis (in place, centered).
    - Grabbing (click & drag) on the left Y-axis scales ONLY the Y-axis (in place, centered).
    - Scrolling mouse wheel over the bottom X-axis scales ONLY the X-axis (in place, centered).
    - Scrolling mouse wheel over the left Y-axis scales ONLY the Y-axis (in place, centered).
    - Shift + Scroll inside plot scales the X-axis.
    - Ctrl / Cmd / Alt + Scroll inside plot scales the Y-axis.
    - Updates mouse hover cursor to SizeHorCursor on X-axis and SizeVerCursor on Y-axis.
    """

    def __init__(self, plot_widget: pg.PlotWidget):
        super().__init__(plot_widget)
        self.plot_widget = plot_widget
        self.plot_item = plot_widget.getPlotItem()
        self.view_box = self.plot_item.getViewBox()
        self.axis_bottom = self.plot_item.getAxis("bottom")
        self.axis_left = self.plot_item.getAxis("left")
        self._custom_cursor_set = False
        self._drag_axis: Optional[str] = None
        self._last_drag_pos = None

    def zoom_axis(
        self,
        axis_name: str,
        scene_pos: QPointF,
        delta: float,
        use_center: bool = False,
        scale_factor: Optional[float] = None
    ):
        """Scale a single axis (x or y). If use_center=True, scales symmetrically around range center so axis does not move."""
        if scale_factor is None:
            if delta == 0:
                return
            scale_factor = 0.88 ** (delta / 120.0)

        vb = self.view_box
        if axis_name == "x":
            x_min, x_max = vb.viewRange()[0]
            if use_center:
                cx = 0.5 * (x_min + x_max)
            else:
                view_pt = vb.mapSceneToView(scene_pos)
                cx = float(view_pt.x())
            new_xmin = cx - (cx - x_min) * scale_factor
            new_xmax = cx + (x_max - cx) * scale_factor
            span = new_xmax - new_xmin
            if 1e-6 < span < 1e9:
                vb.setXRange(new_xmin, new_xmax, padding=0.0)
        elif axis_name == "y":
            y_min, y_max = vb.viewRange()[1]
            if use_center:
                cy = 0.5 * (y_min + y_max)
            else:
                view_pt = vb.mapSceneToView(scene_pos)
                cy = float(view_pt.y())
            new_ymin = cy - (cy - y_min) * scale_factor
            new_ymax = cy + (y_max - cy) * scale_factor
            span = new_ymax - new_ymin
            if 1e-6 < span < 1e9:
                vb.setYRange(new_ymin, new_ymax, padding=0.0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.ContextMenu:
            event.accept()
            return True

        vb_rect = self.view_box.mapRectToScene(self.view_box.rect())
        axis_b_rect = self.axis_bottom.mapRectToScene(self.axis_bottom.rect())
        axis_l_rect = self.axis_left.mapRectToScene(self.axis_left.rect())

        if event.type() == QEvent.MouseButtonPress:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            scene_pos = self.plot_widget.mapToScene(pos)

            over_x = axis_b_rect.contains(scene_pos) or (
                scene_pos.y() >= vb_rect.bottom() - 2 and
                vb_rect.left() <= scene_pos.x() <= vb_rect.right()
            )
            over_y = axis_l_rect.contains(scene_pos) or (
                scene_pos.x() <= vb_rect.left() + 2 and
                vb_rect.top() <= scene_pos.y() <= vb_rect.bottom()
            )

            if over_x:
                self._drag_axis = "x"
                self._last_drag_pos = pos
                self.plot_widget.viewport().setCursor(Qt.SizeHorCursor)
                self._custom_cursor_set = True
                return True
            elif over_y:
                self._drag_axis = "y"
                self._last_drag_pos = pos
                self.plot_widget.viewport().setCursor(Qt.SizeVerCursor)
                self._custom_cursor_set = True
                return True

        elif event.type() == QEvent.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

            if self._drag_axis is not None and self._last_drag_pos is not None:
                dx = pos.x() - self._last_drag_pos.x()
                dy = pos.y() - self._last_drag_pos.y()
                self._last_drag_pos = pos

                if self._drag_axis == "x":
                    diff = dx - dy if (abs(dx) > 0 and abs(dy) > 0) else (dx if abs(dx) >= abs(dy) else -dy)
                    if diff != 0:
                        scale_factor = 0.988 ** diff
                        self.zoom_axis("x", scene_pos=QPointF(0, 0), delta=0, use_center=True, scale_factor=scale_factor)
                    self.plot_widget.viewport().setCursor(Qt.SizeHorCursor)
                    return True
                elif self._drag_axis == "y":
                    diff = -dy + dx if (abs(dx) > 0 and abs(dy) > 0) else (-dy if abs(dy) >= abs(dx) else dx)
                    if diff != 0:
                        scale_factor = 0.988 ** diff
                        self.zoom_axis("y", scene_pos=QPointF(0, 0), delta=0, use_center=True, scale_factor=scale_factor)
                    self.plot_widget.viewport().setCursor(Qt.SizeVerCursor)
                    return True

            scene_pos = self.plot_widget.mapToScene(pos)
            over_x = axis_b_rect.contains(scene_pos) or (
                scene_pos.y() >= vb_rect.bottom() - 2 and
                vb_rect.left() <= scene_pos.x() <= vb_rect.right()
            )
            over_y = axis_l_rect.contains(scene_pos) or (
                scene_pos.x() <= vb_rect.left() + 2 and
                vb_rect.top() <= scene_pos.y() <= vb_rect.bottom()
            )

            if over_x:
                self.plot_widget.viewport().setCursor(Qt.SizeHorCursor)
                self._custom_cursor_set = True
            elif over_y:
                self.plot_widget.viewport().setCursor(Qt.SizeVerCursor)
                self._custom_cursor_set = True
            elif self._custom_cursor_set:
                self.plot_widget.viewport().unsetCursor()
                self._custom_cursor_set = False

        elif event.type() == QEvent.MouseButtonRelease:
            if self._drag_axis is not None:
                self._drag_axis = None
                self._last_drag_pos = None
                return True

        elif event.type() == QEvent.Leave:
            if self._custom_cursor_set and self._drag_axis is None:
                self.plot_widget.viewport().unsetCursor()
                self._custom_cursor_set = False

        elif event.type() == QEvent.Wheel:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            scene_pos = self.plot_widget.mapToScene(pos)

            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y() if hasattr(event, "pixelDelta") else 0
            if delta == 0:
                delta = event.angleDelta().x()

            if delta == 0:
                return False

            over_x = axis_b_rect.contains(scene_pos) or (
                scene_pos.y() >= vb_rect.bottom() - 2 and
                vb_rect.left() <= scene_pos.x() <= vb_rect.right()
            )
            over_y = axis_l_rect.contains(scene_pos) or (
                scene_pos.x() <= vb_rect.left() + 2 and
                vb_rect.top() <= scene_pos.y() <= vb_rect.bottom()
            )

            modifiers = event.modifiers()
            shift_pressed = bool(modifiers & Qt.ShiftModifier)
            ctrl_pressed = bool(modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))

            if over_x:
                self.zoom_axis("x", scene_pos, delta, use_center=True)
                event.accept()
                return True
            elif over_y:
                self.zoom_axis("y", scene_pos, delta, use_center=True)
                event.accept()
                return True
            elif shift_pressed and vb_rect.contains(scene_pos):
                self.zoom_axis("x", scene_pos, delta, use_center=False)
                event.accept()
                return True
            elif ctrl_pressed and vb_rect.contains(scene_pos):
                self.zoom_axis("y", scene_pos, delta, use_center=False)
                event.accept()
                return True

        return super().eventFilter(watched, event)


def enable_axis_wheel_zoom(plot_widget: pg.PlotWidget) -> PlotAxisZoomFilter:
    """
    Configure a PlotWidget so that grabbing/dragging or scrolling on the X-axis
    zooms only horizontally (in place, without moving/panning), and grabbing/dragging
    or scrolling on the Y-axis zooms only vertically.
    Also provides hover indicators and tooltips on both axes.
    """
    plot_widget.setContextMenuPolicy(Qt.NoContextMenu)
    plot_item = plot_widget.getPlotItem()
    plot_item.setMenuEnabled(False)
    plot_item.ctrlMenu = None
    plot_item.contextMenuEvent = lambda ev: ev.accept()
    vb = plot_item.getViewBox()
    vb.setMenuEnabled(False)
    vb.menu = None
    vb.raiseContextMenu = lambda ev: None

    filt = PlotAxisZoomFilter(plot_widget)
    plot_widget.viewport().installEventFilter(filt)
    axis_b = plot_item.getAxis("bottom")
    axis_l = plot_item.getAxis("left")

    axis_b.setToolTip("Grab & drag or scroll wheel to scale X-axis (Shift+Scroll in plot)")
    axis_l.setToolTip("Grab & drag or scroll wheel to scale Y-axis (Ctrl+Scroll in plot)")

    def _on_bottom_axis_wheel(ev):
        delta = ev.delta() if hasattr(ev, "delta") else ev.angleDelta().y()
        if delta == 0 and hasattr(ev, "pixelDelta"):
            delta = ev.pixelDelta().y()
        if delta == 0 and hasattr(ev, "angleDelta"):
            delta = ev.angleDelta().x()
        if delta != 0:
            scene_pos = ev.scenePos() if hasattr(ev, "scenePos") else plot_item.getViewBox().mapViewToScene(
                QPointF(plot_item.getViewBox().viewRange()[0][0], 0)
            )
            filt.zoom_axis("x", scene_pos, delta, use_center=True)
        ev.accept()

    def _on_left_axis_wheel(ev):
        delta = ev.delta() if hasattr(ev, "delta") else ev.angleDelta().y()
        if delta == 0 and hasattr(ev, "pixelDelta"):
            delta = ev.pixelDelta().y()
        if delta != 0:
            scene_pos = ev.scenePos() if hasattr(ev, "scenePos") else plot_item.getViewBox().mapViewToScene(
                QPointF(0, plot_item.getViewBox().viewRange()[1][0])
            )
            filt.zoom_axis("y", scene_pos, delta, use_center=True)
        ev.accept()

    def _on_bottom_axis_drag(ev):
        ev.accept()
        delta = ev.screenPos() - ev.lastScreenPos()
        dx = delta.x()
        dy = delta.y()
        diff = dx - dy if (abs(dx) > 0 and abs(dy) > 0) else (dx if abs(dx) >= abs(dy) else -dy)
        if diff != 0:
            scale_factor = 0.988 ** diff
            filt.zoom_axis("x", scene_pos=QPointF(0, 0), delta=0, use_center=True, scale_factor=scale_factor)

    def _on_left_axis_drag(ev):
        ev.accept()
        delta = ev.screenPos() - ev.lastScreenPos()
        dx = delta.x()
        dy = delta.y()
        diff = -dy + dx if (abs(dx) > 0 and abs(dy) > 0) else (-dy if abs(dy) >= abs(dx) else dx)
        if diff != 0:
            scale_factor = 0.988 ** diff
            filt.zoom_axis("y", scene_pos=QPointF(0, 0), delta=0, use_center=True, scale_factor=scale_factor)

    axis_b.wheelEvent = _on_bottom_axis_wheel
    axis_l.wheelEvent = _on_left_axis_wheel
    axis_b.mouseDragEvent = _on_bottom_axis_drag
    axis_l.mouseDragEvent = _on_left_axis_drag

    plot_widget._axis_zoom_filter = filt
    return filt


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


class UniversalPlotter(QWidget):
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
    Can be used standalone or embedded in a QDockWidget (dockable/detachable panel).
    """
    timeCursorMoved = Signal(float)       # Emitted when user drags cursor on plot
    trimRangeChanged = Signal(int, int)   # Emitted when user drags ROI bounds on plot

    def __init__(self, trial: Optional[C3DTrial] = None, current_frame: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("C3D Signal & Marker Plotter")
        self.resize(1100, 680)

        self.trial: Optional[C3DTrial] = trial
        self.current_frame: int = current_frame
        self.x_axis_mode: str = "frame"  # "frame" (default) or "time"
        self.trim_range: Optional[Tuple[int, int]] = None
        self.roi_region: Optional[pg.LinearRegionItem] = None
        self.event_lines: List[pg.InfiniteLine] = []
        self.dock_widget: Optional[QWidget] = None

        # Signal storage: item_id -> {"x": np.ndarray, "y": np.ndarray, "label": str, "unit": str, "rate": float, "subsamples": int}
        self.active_curves: Dict[str, pg.PlotDataItem] = {}
        self.curve_data: Dict[str, dict] = {}
        self.color_map: Dict[str, str] = {}
        self._next_color_idx: int = 0

        self._setup_ui()
        if self.trial:
            self.load_trial(self.trial)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top Controls Toolbar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # X-Axis Mode Radio Buttons
        top_bar.addWidget(QLabel("<b>Horizontal Axis:</b>"))
        self.rb_frame = QRadioButton("Frame Number")
        self.rb_frame.setChecked(True)
        self.rb_frame.toggled.connect(self._on_x_axis_mode_changed)
        top_bar.addWidget(self.rb_frame)

        self.rb_time = QRadioButton("Time (seconds)")
        self.rb_time.setChecked(False)
        self.rb_time.toggled.connect(self._on_x_axis_mode_changed)
        top_bar.addWidget(self.rb_time)

        top_bar.addSpacing(16)

        btn_fit_roi = QPushButton("Fit ROI")
        btn_fit_roi.setCursor(Qt.PointingHandCursor)
        btn_fit_roi.setToolTip("Auto-fit horizontal and vertical zoom to trimmed Region of Interest (ROI)")
        btn_fit_roi.clicked.connect(self.fit_roi)
        top_bar.addWidget(btn_fit_roi)

        btn_fit = QPushButton("Fit Full")
        btn_fit.setCursor(Qt.PointingHandCursor)
        btn_fit.setToolTip("Auto-fit horizontal and vertical zoom to entire trial")
        btn_fit.clicked.connect(self.auto_range)
        top_bar.addWidget(btn_fit)

        btn_clear = QPushButton("Clear All Curves")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_all_curves)
        top_bar.addWidget(btn_clear)

        top_bar.addSpacing(8)
        self.lbl_roi_status = QLabel("ROI: Full Trial")
        self.lbl_roi_status.setStyleSheet(
            "background: #1E2433; border: 1px solid #333F54; border-radius: 10px; "
            "padding: 3px 8px; color: #94A3B8; font-size: 11px;"
        )
        top_bar.addWidget(self.lbl_roi_status)

        top_bar.addStretch()

        btn_export_csv = QPushButton("Export Plotted to CSV...")
        btn_export_csv.clicked.connect(self.export_plotted_csv)
        top_bar.addWidget(btn_export_csv)

        btn_export_img = QPushButton("Save Image...")
        btn_export_img.clicked.connect(self.export_plot_image)
        top_bar.addWidget(btn_export_img)

        # Dock / Undock toggle button (active when attached to a QDockWidget)
        self.btn_dock_toggle = QPushButton("Detach Window")
        self.btn_dock_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_dock_toggle.setToolTip("Detach Plotter into an independent floating window")
        self.btn_dock_toggle.setStyleSheet(
            "QPushButton { font-weight: 600; padding: 4px 10px; border-radius: 4px; "
            "background-color: #2D3748; color: #E2E8F0; border: 1px solid #4A5568; } "
            "QPushButton:hover { background-color: #38A169; color: #FFFFFF; border-color: #48BB78; }"
        )
        self.btn_dock_toggle.clicked.connect(self._toggle_dock_floating)
        self.btn_dock_toggle.hide()
        top_bar.addWidget(self.btn_dock_toggle)

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
        self.tree.setContextMenuPolicy(Qt.NoContextMenu)
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
        self.plot_widget.setContextMenuPolicy(Qt.NoContextMenu)
        _pi = self.plot_widget.getPlotItem()
        _pi.setMenuEnabled(False)
        _pi.ctrlMenu = None
        _pi.contextMenuEvent = lambda ev: ev.accept()
        _vb = _pi.getViewBox()
        _vb.setMenuEnabled(False)
        _vb.menu = None
        _vb.raiseContextMenu = lambda ev: None

        self.plot_widget.setBackground("#151720")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("bottom", "Frame", units="")
        self.plot_widget.setLabel("left", "Value / Amplitude")
        self.plot_widget.addLegend(offset=(-20, 20))
        enable_axis_wheel_zoom(self.plot_widget)

        # Vertical Synchronized Time / Frame Cursor (starts in Frame mode)
        init_cur_val = float(self.current_frame + 1)
        self.time_cursor = pg.InfiniteLine(
            pos=init_cur_val,
            angle=90,
            movable=True,
            pen=pg.mkPen(color="#00ADB5", width=2, style=Qt.SolidLine),
            label="Frame {value:.0f}",
            labelOpts={"color": "#FFFFFF", "fill": "#00ADB5", "position": 0.95}
        )
        self.time_cursor.setZValue(100)
        self.time_cursor.sigPositionChanged.connect(self._on_cursor_dragged)
        self.plot_widget.addItem(self.time_cursor)
        # On-curve hover indicator dot & floating label
        self.hover_dot = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen("#FFFFFF", width=1.5),
            brush=pg.mkBrush("#00E5FF")
        )
        self.hover_dot.setZValue(120)
        self.hover_dot.hide()
        self.plot_widget.addItem(self.hover_dot)

        self.hover_label = pg.TextItem(anchor=(0.5, 1.2))
        self.hover_label.setZValue(121)
        self.hover_label.hide()
        self.plot_widget.addItem(self.hover_label)

        self.mouse_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=40,
            slot=self._on_mouse_moved
        )

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
            m_item.setFlags(m_item.flags() | Qt.ItemIsUserCheckable)
            m_item.setCheckState(0, Qt.Unchecked)
            m_item.setData(0, Qt.UserRole, ("marker_parent", name))
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

        # Draw vertical dashed lines at event timestamps like the analog panel
        self._build_event_lines()

        # Ensure synchronized playhead time cursor is present and visible
        if self.time_cursor not in self.plot_widget.getPlotItem().items:
            self.plot_widget.addItem(self.time_cursor)
        self.time_cursor.show()

        # Update cursor position to current frame
        self.update_frame(self.current_frame)

    def _build_event_lines(self):
        """Draw vertical dashed lines at event timestamps like the analog panel."""
        for line in self.event_lines:
            try:
                self.plot_widget.removeItem(line)
            except Exception:
                pass
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
        if getattr(self, "_is_updating_tree", False):
            return

        role_data = item.data(0, Qt.UserRole)
        if not role_data:
            return

        kind = role_data[0]
        cur_state = item.checkState(0)

        if kind == "marker_parent":
            # User checked/unchecked a parent marker item directly -> check/uncheck all 4 components
            self._is_updating_tree = True
            try:
                target_state = Qt.Checked if cur_state == Qt.Checked else Qt.Unchecked
                item.setCheckState(0, target_state)
                if target_state == Qt.Checked:
                    item.setExpanded(True)
                for i in range(item.childCount()):
                    c_item = item.child(i)
                    c_role = c_item.data(0, Qt.UserRole)
                    c_lbl = c_item.text(0)
                    c_item.setCheckState(0, target_state)
                    if target_state == Qt.Checked:
                        if c_role and c_lbl not in self.active_curves:
                            self._add_signal(c_lbl, c_role)
                    else:
                        if c_lbl in self.active_curves:
                            self._remove_signal(c_lbl)
            finally:
                self._is_updating_tree = False
            return

        label = item.text(0)
        is_checked = (cur_state == Qt.Checked)

        if is_checked:
            self._add_signal(label, role_data)
        else:
            self._remove_signal(label)

        # Update parent marker item checkbox state if this is a marker component
        parent = item.parent()
        if parent:
            p_role = parent.data(0, Qt.UserRole)
            if p_role and p_role[0] == "marker_parent":
                total = parent.childCount()
                checked_count = sum(1 for i in range(total) if parent.child(i).checkState(0) == Qt.Checked)
                self._is_updating_tree = True
                try:
                    if checked_count == total:
                        parent.setCheckState(0, Qt.Checked)
                    elif checked_count == 0:
                        parent.setCheckState(0, Qt.Unchecked)
                    else:
                        parent.setCheckState(0, Qt.PartiallyChecked)
                finally:
                    self._is_updating_tree = False

    # ---------------------------------------------------------
    # Curve Adding & Removing
    # ---------------------------------------------------------
    def _add_signal(self, label: str, role_data: tuple):
        if not self.trial or label in self.active_curves:
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

        elif kind == "distance":
            m1, m2 = role_data[1], role_data[2]
            if len(role_data) > 3 and role_data[3] is not None:
                y_data = role_data[3]
            elif self.trial and m1 in self.trial.markers and m2 in self.trial.markers:
                from gui.marker_tools_dialog import compute_distance_trajectory
                y_data = compute_distance_trajectory(self.trial.markers[m1], self.trial.markers[m2])
            rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
            subsamples = 1

        elif kind == "custom":
            y_data = role_data[1]
            unit = role_data[2] if len(role_data) > 2 and role_data[2] else ""
            rate = self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0
            subsamples = 1

        if y_data is None:
            return

        unit = ""
        if kind == "marker":
            unit = getattr(self.trial, "marker_units", "mm") if self.trial else "mm"
        elif kind == "force":
            unit = "N"
        elif kind == "moment":
            unit = "N·mm"
        elif kind == "cop":
            unit = "mm"
        elif kind == "analog":
            unit = self.trial.analog_units.get(role_data[1], "V") if self.trial and hasattr(self.trial, "analog_units") and self.trial.analog_units else "V"
        elif kind == "distance":
            unit = "mm"
        elif kind == "angle":
            unit = "deg"
        elif kind == "custom":
            unit = role_data[2] if len(role_data) > 2 and role_data[2] else ""

        # Store data
        self.curve_data[label] = {
            "y": y_data,
            "rate": rate if rate > 0 else 100.0,
            "subsamples": subsamples,
            "unit": unit
        }

        # Assign color
        if label not in self.color_map:
            if kind == "marker" and len(role_data) > 3 and role_data[3] in ("X", "Y", "Z", "3D Norm"):
                comp_name = role_data[3]
                is_dark = getattr(self, "is_dark", True)
                if comp_name == "X":
                    self.color_map[label] = "#FF5252" if is_dark else "#EF4444"
                elif comp_name == "Y":
                    self.color_map[label] = "#00E676" if is_dark else "#16A34A"
                elif comp_name == "Z":
                    self.color_map[label] = "#40C4FF" if is_dark else "#0284C7"
                else:
                    self.color_map[label] = "#FFD740" if is_dark else "#D97706"
            elif kind == "distance":
                self.color_map[label] = "#E040FB" if getattr(self, "is_dark", True) else "#A855F7"
            else:
                self.color_map[label] = PLOT_COLORS[self._next_color_idx % len(PLOT_COLORS)]
                self._next_color_idx += 1
        col = self.color_map[label]

        # Compute X vector
        x_vec = self._compute_x_vec(len(y_data), rate, subsamples)

        # Plot curve
        curve = self.plot_widget.plot(
            x_vec,
            y_data,
            pen=pg.mkPen(color=col, width=2.0, cosmetic=True),
            name=label
        )
        self.active_curves[label] = curve
        self.auto_range()

    def _remove_signal(self, label: str):
        if label in self.active_curves:
            curve = self.active_curves.pop(label)
            self.plot_widget.removeItem(curve)
        self.curve_data.pop(label, None)
        if hasattr(self, "hover_dot"):
            self.hover_dot.hide()
            self.hover_label.hide()

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
        if hasattr(self, "hover_dot"):
            self.hover_dot.hide()
            self.hover_label.hide()

    # ---------------------------------------------------------
    # Programmatic Marker Plotting
    # ---------------------------------------------------------
    def plot_marker_coordinates(
        self,
        marker_name: str,
        components: Tuple[str, ...] = ("X", "Y", "Z"),
        clear_others: bool = True
    ):
        """
        Immediately plot the requested coordinates (default X, Y, Z) for the given marker.
        Expands the marker node in the tree, checks the corresponding component items,
        and auto-ranges the plot view.
        """
        if not self.trial or marker_name not in self.trial.markers:
            return

        if clear_others:
            self.clear_all_curves()

        if self.search_box.text():
            self.search_box.clear()

        # Find the marker item in the tree
        markers_root = None
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if "Markers" in item.text(0):
                markers_root = item
                break

        target_m_item = None
        if markers_root:
            markers_root.setExpanded(True)
            for i in range(markers_root.childCount()):
                c = markers_root.child(i)
                if c.text(0) == marker_name:
                    target_m_item = c
                    break

        if target_m_item:
            target_m_item.setExpanded(True)
            self.tree.scrollToItem(target_m_item)
            for j in range(target_m_item.childCount()):
                sub_item = target_m_item.child(j)
                role_data = sub_item.data(0, Qt.UserRole)
                if role_data and role_data[0] == "marker":
                    comp_name = role_data[3]
                    if comp_name in components:
                        lbl = sub_item.text(0)
                        sub_item.setCheckState(0, Qt.Checked)
                        if lbl not in self.active_curves:
                            self._add_signal(lbl, role_data)
        else:
            # Direct addition fallback if tree not yet populated
            for comp_name, comp_idx in [("X", 0), ("Y", 1), ("Z", 2)]:
                if comp_name in components:
                    lbl = f"{marker_name} ({comp_name})"
                    if lbl not in self.active_curves:
                        self._add_signal(lbl, ("marker", marker_name, comp_idx, comp_name))

        self.auto_range()
        self.show()
        self.raise_()
        self.activateWindow()

    def plot_markers_coordinates(
        self,
        marker_names: List[str],
        components: Tuple[str, ...] = ("X", "Y", "Z"),
        clear_others: bool = True
    ):
        """Immediately plot coordinates for multiple selected markers."""
        if not self.trial or not marker_names:
            return

        if clear_others:
            self.clear_all_curves()

        for name in marker_names:
            if name in self.trial.markers:
                self.plot_marker_coordinates(name, components=components, clear_others=False)

        self.auto_range()
        self.show()
        self.raise_()
        self.activateWindow()

    def plot_analog_channel(self, channel_name: str, clear_others: bool = False):
        """Immediately activate and plot the requested analog channel in the Universal Plotter."""
        self.plot_analog_channels([channel_name], clear_others=clear_others)

    def plot_analog_channels(self, channel_names: List[str], clear_others: bool = False):
        """
        Immediately activate and plot multiple analog channels in the Universal Plotter.
        Finds each channel item under the 'Analog Channels' group in the tree,
        checks it (activating the signal), expands the group, scrolls to the first item,
        and auto-ranges the plot view.
        """
        if not self.trial or not channel_names:
            return

        if clear_others:
            self.clear_all_curves()

        if self.search_box.text():
            self.search_box.clear()

        # Find Analog Channels root in tree
        analog_root = None
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if "Analog" in item.text(0):
                analog_root = item
                break

        if not analog_root:
            analog_root = QTreeWidgetItem(["Analog Channels"])
            analog_root.setForeground(0, QColor("#69F0AE"))
            self.tree.addTopLevelItem(analog_root)

        analog_root.setExpanded(True)

        first_target = None
        for ch_name in channel_names:
            if ch_name not in self.trial.analogs:
                continue

            target_item = None
            for i in range(analog_root.childCount()):
                c = analog_root.child(i)
                role_data = c.data(0, Qt.UserRole)
                if role_data and role_data[0] == "analog" and role_data[1] == ch_name:
                    target_item = c
                    break

            if not target_item:
                # Create item if not already in tree
                u = self.trial.analog_units.get(ch_name, "V")
                target_item = QTreeWidgetItem([f"{ch_name} ({u})"])
                target_item.setFlags(target_item.flags() | Qt.ItemIsUserCheckable)
                target_item.setCheckState(0, Qt.Unchecked)
                target_item.setData(0, Qt.UserRole, ("analog", ch_name, u))
                analog_root.addChild(target_item)

            if first_target is None:
                first_target = target_item

            target_item.setCheckState(0, Qt.Checked)
            lbl = target_item.text(0)
            role_data = target_item.data(0, Qt.UserRole)
            if lbl not in self.active_curves:
                self._add_signal(lbl, role_data)

        if first_target:
            self.tree.scrollToItem(first_target)

        self.auto_range()
        self.show()
        self.raise_()
        self.activateWindow()

    def plot_distance(
        self,
        m1: str,
        m2: str,
        dist_data: Optional[np.ndarray] = None,
        clear_others: bool = True
    ):
        """Immediately plot the Euclidean distance trajectory between two markers."""
        if not self.trial or m1 not in self.trial.markers or m2 not in self.trial.markers:
            return

        if clear_others:
            self.clear_all_curves()

        if dist_data is None:
            from gui.marker_tools_dialog import compute_distance_trajectory
            dist_data = compute_distance_trajectory(self.trial.markers[m1], self.trial.markers[m2])

        label = f"Distance: {m1} ↔ {m2} (mm)"

        # Check if Measurements category exists in tree
        meas_root = None
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if "Measurements" in it.text(0):
                meas_root = it
                break

        if not meas_root:
            meas_root = QTreeWidgetItem(["Measurements (Distances)"])
            meas_root.setForeground(0, QColor("#E040FB"))
            self.tree.addTopLevelItem(meas_root)

        meas_root.setExpanded(True)

        target_item = None
        for i in range(meas_root.childCount()):
            c = meas_root.child(i)
            if c.text(0) == label:
                target_item = c
                break

        if not target_item:
            target_item = QTreeWidgetItem([label])
            target_item.setFlags(target_item.flags() | Qt.ItemIsUserCheckable)
            target_item.setData(0, Qt.UserRole, ("distance", m1, m2, dist_data))
            meas_root.addChild(target_item)
        else:
            target_item.setData(0, Qt.UserRole, ("distance", m1, m2, dist_data))

        target_item.setCheckState(0, Qt.Checked)
        if label not in self.active_curves:
            self._add_signal(label, ("distance", m1, m2, dist_data))

        self.auto_range()
        if self.dock_widget and not self.dock_widget.isVisible():
            self.dock_widget.show()
        elif not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def add_custom_curve(self, label: str, y_data: np.ndarray, unit: str = ""):
        """Add a custom signal (e.g. measured distance, angle, custom curve) and plot it."""
        cat_name = "Custom & Measurements"
        cat_root = None
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if "Custom" in it.text(0) or "Measurements" in it.text(0):
                cat_root = it
                break

        if not cat_root:
            cat_root = QTreeWidgetItem([cat_name])
            cat_root.setForeground(0, QColor("#E040FB"))
            self.tree.addTopLevelItem(cat_root)

        cat_root.setExpanded(True)

        target_item = None
        for i in range(cat_root.childCount()):
            c = cat_root.child(i)
            if c.text(0) == label:
                target_item = c
                break

        role_data = ("custom", y_data, unit)
        if not target_item:
            target_item = QTreeWidgetItem([label])
            target_item.setFlags(target_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cat_root.addChild(target_item)

        target_item.setData(0, Qt.UserRole, role_data)
        target_item.setCheckState(0, Qt.Checked)
        if label not in self.active_curves:
            self._add_signal(label, role_data)

        self.auto_range()
        if self.dock_widget and not self.dock_widget.isVisible():
            self.dock_widget.show()
            self.dock_widget.raise_()
        elif not self.isVisible():
            self.show()
            self.raise_()

    def plot_marker(self, marker_name: str, marker_data: Optional[np.ndarray] = None):
        """Immediately plot marker coordinates (X, Y, Z)."""
        self.plot_marker_coordinates(marker_name, components=("X", "Y", "Z"), clear_others=False)

    def plot_markers(self, markers: Union[List[str], Dict[str, np.ndarray]]):
        """Immediately plot multiple markers' coordinates (X, Y, Z)."""
        if isinstance(markers, dict):
            names = list(markers.keys())
        else:
            names = list(markers)
        self.plot_markers_coordinates(names, components=("X", "Y", "Z"), clear_others=False)

    # ---------------------------------------------------------
    # X-Axis Mode (Time vs Frame)
    # ---------------------------------------------------------
    def _compute_x_vec(self, n_points: int, rate: float, subsamples: int) -> np.ndarray:
        if self.x_axis_mode == "frame":
            if subsamples > 1:
                return 1.0 + np.arange(n_points) / float(subsamples)
            return 1.0 + np.arange(n_points, dtype=np.float32)
        else:
            return np.arange(n_points) / float(rate)

    def _on_x_axis_mode_changed(self):
        self.x_axis_mode = "frame" if self.rb_frame.isChecked() else "time"
        if self.x_axis_mode == "frame":
            self.plot_widget.setLabel("bottom", "Frame", units="")
            if hasattr(self.time_cursor, "label") and self.time_cursor.label:
                self.time_cursor.label.setFormat("Frame {value:.0f}")
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

        # Synchronize ROI region bounds for new axis mode
        if self.roi_region is not None and self.trim_range is not None and self.trial:
            start_f, end_f = self.trim_range
            rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0
            self.roi_region.blockSignals(True)
            if self.x_axis_mode == "frame":
                self.roi_region.setRegion([float(start_f), float(end_f)])
            else:
                self.roi_region.setRegion([start_f / rate, end_f / rate])
            self.roi_region.blockSignals(False)

        # Rebuild event lines to switch between frame positions and time positions
        self._build_event_lines()

        if hasattr(self, "hover_dot"):
            self.hover_dot.hide()
            self.hover_label.hide()

        self.update_frame(self.current_frame)
        self.auto_range()

    def _on_mouse_moved(self, evt):
        """Called when mouse moves over the plot. If hovering over a curve, shows label and dot."""
        if not self.active_curves:
            self.hover_dot.hide()
            self.hover_label.hide()
            return

        pos = evt[0] if isinstance(evt, (tuple, list)) else evt
        vb = self.plot_widget.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
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
        best_idx = 0

        # Max pixel distance from curve to trigger hover label
        HOVER_PIXEL_THRESHOLD = 25.0

        for label, curve in self.active_curves.items():
            curve_pts = curve.getData()
            if curve_pts is None or len(curve_pts) < 2:
                continue
            x_data, y_data = curve_pts[0], curve_pts[1]
            if x_data is None or y_data is None or len(x_data) == 0:
                continue

            # Binary search to find nearest index in sorted x_data
            idx = int(np.clip(np.searchsorted(x_data, mouse_x), 0, len(x_data) - 1))
            cand_indices = range(max(0, idx - 2), min(len(x_data), idx + 3))

            for i in cand_indices:
                xi = x_data[i]
                yi = y_data[i]
                if np.isnan(yi):
                    continue

                # Point distance in screen pixels
                pt_scene = vb.mapViewToScene(QPointF(float(xi), float(yi)))
                d_pt = np.hypot(scene_x - pt_scene.x(), scene_y - pt_scene.y())
                if d_pt < best_dist_px:
                    best_dist_px = d_pt
                    best_curve_label = label
                    best_snap_x = float(xi)
                    best_snap_y = float(yi)
                    best_idx = i

                # Segment projection to next point in screen pixels
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
                                if t < 0.5:
                                    best_snap_x = float(xi)
                                    best_snap_y = float(yi)
                                    best_idx = i
                                else:
                                    best_snap_x = float(x_next)
                                    best_snap_y = float(y_next)
                                    best_idx = i + 1

        if best_curve_label is not None and best_dist_px <= HOVER_PIXEL_THRESHOLD:
            col = self.color_map.get(best_curve_label, "#00E5FF")
            info = self.curve_data.get(best_curve_label, {})
            unit = info.get("unit", "")
            rate = info.get("rate", 100.0)
            subsamples = info.get("subsamples", 1)

            # Format value with unit
            val_text = f"{best_snap_y:.2f}"
            unit_str = f" {unit}" if unit else ""

            # Frame and time indexing (frames start at 1, time starts at 0.0s)
            if subsamples > 1:
                f_val = 1.0 + best_idx / float(subsamples)
                time_s = best_idx / float(rate)
                frame_time_str = f"Frame {f_val:.1f} • {time_s:.3f} s"
            else:
                f_val = best_idx + 1
                time_s = best_idx / float(rate)
                frame_time_str = f"Frame {f_val} • {time_s:.3f} s"

            # Dynamic anchor positioning so label never goes outside viewport
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
                f'border: 1.5px solid {col}; border-radius: 6px; '
                f'padding: 4px 8px; color: #FFFFFF; font-family: sans-serif; font-size: 11px; line-height: 1.3;">'
                f'<span style="color: {col}; font-weight: 600;">{best_curve_label}</span><br/>'
                f'<span style="color: #FFFFFF; font-size: 13px; font-weight: bold;">{val_text}{unit_str}</span><br/>'
                f'<span style="color: #94A3B8; font-size: 10px;">{frame_time_str}</span>'
                f'</div>'
            )

            self.hover_dot.setData([best_snap_x], [best_snap_y])
            self.hover_dot.setBrush(pg.mkBrush(col))
            self.hover_dot.show()

            self.hover_label.setAnchor((anchor_x, anchor_y))
            self.hover_label.setHtml(html)
            self.hover_label.setPos(best_snap_x, best_snap_y)
            self.hover_label.show()
        else:
            self.hover_dot.hide()
            self.hover_label.hide()

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Update ROI Region of Interest on UniversalPlotterWindow."""
        if not self.trial:
            return
        n = self.trial.point_frame_count
        start_f = max(0, min(n - 1, start_frame))
        end_f = max(start_f, min(n - 1, end_frame))
        self.trim_range = (start_f, end_f)

        rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0
        is_trimmed = (start_f > 0 or end_f < n - 1)

        if self.x_axis_mode == "frame":
            reg_start = float(start_f + 1)
            reg_end = float(end_f + 1)
        else:
            reg_start = start_f / rate
            reg_end = end_f / rate

        if self.roi_region is None:
            self.roi_region = pg.LinearRegionItem(
                values=[reg_start, reg_end],
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
            self.roi_region.setRegion([reg_start, reg_end])
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
        rate = self.trial.point_rate if self.trial.point_rate > 0 else 100.0
        if self.x_axis_mode == "frame":
            start_f = int(round(bounds[0])) - 1
            end_f = int(round(bounds[1])) - 1
        else:
            start_f = int(round(bounds[0] * rate))
            end_f = int(round(bounds[1] * rate))

        n = self.trial.point_frame_count
        start_f = max(0, min(n - 1, start_f))
        end_f = max(start_f, min(n - 1, end_f))
        self.trim_range = (start_f, end_f)
        self.trimRangeChanged.emit(start_f, end_f)

    def fit_roi(self):
        """Fit horizontal and vertical zoom strictly to trimmed ROI range."""
        if not self.trial:
            self.auto_range()
            return

        n = self.trial.point_frame_count
        start_f, end_f = self.trim_range if self.trim_range else (0, max(0, n - 1))
        is_trimmed = (start_f > 0 or end_f < n - 1)

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
        for label in self.active_curves.keys():
            info = self.curve_data.get(label)
            if info:
                y = info["y"]
                subsamples = info.get("subsamples", 1)
                s_idx = max(0, start_f * subsamples)
                e_idx = min(len(y), (end_f + 1) * subsamples)
                if e_idx > s_idx:
                    roi_slice = y[s_idx : e_idx]
                    valid = roi_slice[~np.isnan(roi_slice)]
                    if len(valid) > 0:
                        all_y_min = min(all_y_min, float(np.min(valid)))
                        all_y_max = max(all_y_max, float(np.max(valid)))

        if all_y_min < all_y_max:
            y_span = all_y_max - all_y_min
            pad_y = max(1.0, y_span * 0.08)
            self.plot_widget.getPlotItem().setYRange(all_y_min - pad_y, all_y_max + pad_y, padding=0.0)
        elif not is_trimmed:
            self.auto_range()

    def showEvent(self, event):
        super().showEvent(event)
        main_win = self.window()
        if hasattr(main_win, 'timeline') and hasattr(main_win.timeline, 'trim_start_frame'):
            self.set_trim_range(main_win.timeline.trim_start_frame, main_win.timeline.trim_end_frame)
        if hasattr(main_win, 'playback') and hasattr(main_win.playback, 'current_frame'):
            self.update_frame(main_win.playback.current_frame)
        elif self.time_cursor:
            if self.time_cursor not in self.plot_widget.getPlotItem().items:
                self.plot_widget.addItem(self.time_cursor)
            self.time_cursor.show()
            self.update_frame(self.current_frame)

    def set_dock_widget(self, dock_widget: Optional[QWidget]):
        """Attach to a QDockWidget to support dynamic docking/floating status."""
        self.dock_widget = dock_widget
        if self.dock_widget is not None:
            self.btn_dock_toggle.show()
            self._update_dock_toggle_button(self.dock_widget.isFloating())
            if hasattr(self.dock_widget, "topLevelChanged"):
                self.dock_widget.topLevelChanged.connect(self._update_dock_toggle_button)
        else:
            self.btn_dock_toggle.hide()

    def _update_dock_toggle_button(self, is_floating: bool):
        """Update button label and tooltip depending on whether the dock is detached/floating."""
        if is_floating:
            self.btn_dock_toggle.setText("Attach to App")
            self.btn_dock_toggle.setToolTip("Dock Plotter panel back into the main application window")
        else:
            self.btn_dock_toggle.setText("Detach Window")
            self.btn_dock_toggle.setToolTip("Detach Plotter into an independent floating window")

    def _toggle_dock_floating(self):
        """Toggle floating state of the dock widget."""
        if self.dock_widget:
            if not self.dock_widget.isVisible():
                self.dock_widget.show()
            if hasattr(self.dock_widget, "isFloating") and hasattr(self.dock_widget, "setFloating"):
                self.dock_widget.setFloating(not self.dock_widget.isFloating())
                if self.dock_widget.isFloating():
                    self.dock_widget.raise_()
                    self.dock_widget.activateWindow()

    # ---------------------------------------------------------
    # Synchronization & Cursor
    # ---------------------------------------------------------
    def set_frame(self, frame_idx: int):
        """Update synchronized playback cursor line when trial advances."""
        self.update_frame(frame_idx)

    def set_current_frame(self, frame_idx: int):
        """Update synchronized playback cursor line when trial advances."""
        self.update_frame(frame_idx)

    def set_time(self, time_s: float):
        """Update cursor using timestamp in seconds."""
        if self.trial and self.trial.point_rate > 0:
            frame_idx = int(round(time_s * self.trial.point_rate))
            self.update_frame(frame_idx)

    def update_frame(self, frame_idx: int):
        """Update synchronized playback cursor line when trial advances."""
        self.current_frame = frame_idx
        if not self.trial:
            return

        if self.x_axis_mode == "frame":
            val = float(frame_idx + 1)
            text_str = f"Frame {frame_idx + 1}"
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
            self.current_frame = max(0, min(self.trial.point_frame_count - 1, int(round(val)) - 1)) if self.trial else 0
            t = self.trial.frame_to_time(self.current_frame) if self.trial else 0.0
            if hasattr(self.time_cursor, "label") and self.time_cursor.label is not None:
                self.time_cursor.label.setPlainText(f"Frame {self.current_frame + 1}")
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
        if not self.active_curves or not self.curve_data:
            self.plot_widget.autoRange()
            return

        all_x_min, all_x_max = float("inf"), float("-inf")
        all_y_min, all_y_max = float("inf"), float("-inf")

        for label in self.active_curves.keys():
            info = self.curve_data.get(label)
            if info:
                y = info["y"]
                valid = y[~np.isnan(y)]
                if len(valid) > 0:
                    all_y_min = min(all_y_min, float(np.min(valid)))
                    all_y_max = max(all_y_max, float(np.max(valid)))
                n_pts = len(y)
                if n_pts > 0:
                    x = self._compute_x_vec(n_pts, info["rate"], info["subsamples"])
                    all_x_min = min(all_x_min, float(x[0]))
                    all_x_max = max(all_x_max, float(x[-1]))

        if all_x_min < all_x_max and all_y_min < all_y_max:
            self.plot_widget.getPlotItem().setXRange(all_x_min, all_x_max, padding=0.03)
            y_span = all_y_max - all_y_min
            pad_y = max(1.0, y_span * 0.08)
            self.plot_widget.getPlotItem().setYRange(all_y_min - pad_y, all_y_max + pad_y, padding=0.0)
        else:
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


# Backward compatibility aliases
UniversalPlotterWindow = UniversalPlotter


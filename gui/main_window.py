"""Main application window for C3D Explorer."""

import os
import subprocess
import sys
import numpy as np
from typing import Optional, List, Tuple
from PySide6.QtCore import Qt, QSettings, QFileInfo, QUrl, QPoint, QSize
from PySide6.QtGui import (
    QAction, QActionGroup, QKeySequence, QIcon, QDesktopServices,
    QDragEnterEvent, QDropEvent, QColor, QUndoStack, QImage, QPixmap, QPainter
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QDockWidget, QToolBar, QComboBox,
    QPushButton, QLabel, QStatusBar, QMenu
)

from gui.theme import THEMES, get_theme, get_theme_names, DEFAULT_THEME_NAME, create_theme_palette

from core.data_models import C3DTrial, C3DEvent
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
import pyqtgraph as pg
from gui.viewer_3d import Viewer3D
from gui.timeline_widget import TimelineWidget
from gui.playback_controller import PlaybackController
from gui.side_panel import SidePanel
from gui.settings_dialog import SettingsDialog
from gui.marker_tools_dialog import (
    CreateAverageMarkerDialog, MeasureDistanceDialog, MeasureAngleDialog, AddMarkerDialog,
    FilterMarkersDialog, filter_marker_array
)
from gui.plotter_window import UniversalPlotter, UniversalPlotterWindow
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.analog_dialog import AnalogToolsDialog
from gui.about_dialog import AboutDialog
from gui.undo_commands import (
    AddEventCommand, DeleteEventCommand, DeleteEventsCommand, EditEventCommand,
    ClearEventsCommand, EventsBatchCommand, RenameMarkerCommand,
    AddMarkerCommand, DeleteMarkerCommand, DeleteMarkersCommand, ChangeMarkerColorCommand,
    FilterMarkersCommand
)


class MainWindow(QMainWindow):
    """
    Main Biomechanics Workstation Window.
    Provides complete C3D inspection, 3D visualization, timeline scrubber with events,
    multi-channel time series plotting, and file export capabilities.
    """

    MAX_RECENT_FILES = 10

    def __init__(self):
        super().__init__()
        self.setWindowTitle("C3D explorer")
        self.resize(1440, 920)
        self.setAcceptDrops(True)

        self.trial: Optional[C3DTrial] = None
        self.current_file_path: Optional[str] = None
        self.settings = QSettings("Biomech", "C3D explorer")
        self.undo_stack = QUndoStack(self)
        self._is_undo_redo_running: bool = False

        self.dist_dialog: Optional[MeasureDistanceDialog] = None
        self.angle_dialog: Optional[MeasureAngleDialog] = None
        self.analog_dialog: Optional[AnalogToolsDialog] = None
        self.plotter_widget = UniversalPlotter(parent=self)
        self.plotter_window = self.plotter_widget  # Maintain reference for compatibility
        self.plot_panel = self.plotter_widget      # Alias for backwards compatibility
        self.current_theme_name: str = DEFAULT_THEME_NAME

        # Playback Controller
        self.playback = PlaybackController(self)
        self.playback.frameChanged.connect(self._on_frame_changed)
        self.playback.playbackStateChanged.connect(self._on_playback_state_changed)

        # Core Components
        self.viewer_3d = Viewer3D(self)
        self.timeline = TimelineWidget(self)
        self.side_panel = SidePanel(self)

        self._setup_layout()
        self._setup_menus()
        self._setup_playback_bar()
        self._setup_status_bar()
        self._connect_signals()
        self._update_recent_files_menu()
        self._load_saved_settings()
        self.apply_theme(self.current_theme_name)

    def _setup_layout(self):
        """Construct dockable, responsive workstation layout."""
        # Central Container: 3D Viewport on top, Timeline Scrubber underneath
        central_container = QWidget(self)
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(2)

        # 3D Viewport
        central_layout.addWidget(self.viewer_3d, stretch=1)

        # Playback Controls Bar
        self.playback_bar_widget = QWidget(self)
        central_layout.addWidget(self.playback_bar_widget)

        # Timeline Scrubber Widget (with integrated C3D events)
        central_layout.addWidget(self.timeline)

        self.setCentralWidget(central_container)

        # --- Left Dock: Data Explorer Panel (Markers, Force Plates, Events) ---
        self.dock_side = QDockWidget("Data Explorer", self)
        self.dock_side.setObjectName("DockDataExplorer")
        self.dock_side.setWidget(self.side_panel)
        self.dock_side.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_side)

        # --- Bottom Dock: Universal Plotter Panel ---
        self.dock_plotter = QDockWidget("Plotter", self)
        self.dock_plotter.setObjectName("DockPlotter")
        self.plotter_widget.set_dock_widget(self.dock_plotter)
        self.dock_plotter.setWidget(self.plotter_widget)
        self.dock_plotter.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_plotter)
        self.dock_plot = self.dock_plotter  # Alias for backward compatibility
        self.dock_plotter.visibilityChanged.connect(self._on_plotter_dock_visibility_changed)
        self.dock_plotter.hide()  # By default, Plotter panel is deactivated/hidden on launch

    def _setup_playback_bar(self):
        """Build the playback toolbar positioned above the timeline."""
        layout = QHBoxLayout(self.playback_bar_widget)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # Step backward 1 frame
        self.btn_step_back = QPushButton()
        self.btn_step_back.setToolTip("Step Backward 1 Frame (Left Arrow)")
        self.btn_step_back.setFixedSize(36, 32)
        self.btn_step_back.setStyleSheet("padding: 4px;")
        self.btn_step_back.setIconSize(QSize(18, 18))
        self.btn_step_back.clicked.connect(self.playback.step_backward)
        layout.addWidget(self.btn_step_back)

        # Play / Pause
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setObjectName("primaryBtn")
        self.btn_play_pause.setToolTip("Play / Pause (Spacebar)")
        self.btn_play_pause.setFixedSize(46, 32)
        self.btn_play_pause.setStyleSheet("padding: 4px;")
        self.btn_play_pause.setIconSize(QSize(18, 18))
        self.btn_play_pause.clicked.connect(self.playback.toggle_play_pause)
        layout.addWidget(self.btn_play_pause)

        # Step forward 1 frame
        self.btn_step_fwd = QPushButton()
        self.btn_step_fwd.setToolTip("Step Forward 1 Frame (Right Arrow)")
        self.btn_step_fwd.setFixedSize(36, 32)
        self.btn_step_fwd.setStyleSheet("padding: 4px;")
        self.btn_step_fwd.setIconSize(QSize(18, 18))
        self.btn_step_fwd.clicked.connect(self.playback.step_forward)
        layout.addWidget(self.btn_step_fwd)

        self._update_playback_icons()

        layout.addSpacing(12)

        # Speed Selector
        layout.addWidget(QLabel("Speed:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.1x", "0.25x", "0.5x", "1.0x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.currentTextChanged.connect(self._on_speed_changed)
        layout.addWidget(self.combo_speed)

        # Loop Toggle
        self.btn_loop = QPushButton("Loop: ON")
        self.btn_loop.setCheckable(True)
        self.btn_loop.setChecked(True)
        self.btn_loop.clicked.connect(self._on_loop_toggled)
        layout.addWidget(self.btn_loop)

        # Time / Frame Mode Toggle (Positioned next to Loop: ON, default: Frame)
        self.btn_timeline_unit = QPushButton("Frame")
        self.btn_timeline_unit.setToolTip("Switch timeline ruler between Frame index and Time (seconds) [Shortcut: U]")
        self.btn_timeline_unit.setCursor(Qt.PointingHandCursor)
        self.btn_timeline_unit.setFixedHeight(32)
        self.btn_timeline_unit.setStyleSheet("font-weight: 600; padding: 2px 14px;")
        self.btn_timeline_unit.clicked.connect(self.timeline.toggle_display_mode)
        layout.addWidget(self.btn_timeline_unit)

        layout.addSpacing(16)

        # Frame and Time Status Indicators (Frame active by default)
        self.lbl_frame_info = QLabel("Frame: 1 / 1")
        self.lbl_frame_info.setCursor(Qt.PointingHandCursor)
        self.lbl_frame_info.setToolTip("Click to display Timeline ruler in Frame index")
        self.lbl_frame_info.mousePressEvent = lambda e: self.timeline.set_display_mode("frame")
        self.lbl_frame_info.setStyleSheet("color: #00ADB5; font-weight: 700;")
        layout.addWidget(self.lbl_frame_info)

        self.lbl_time_info = QLabel("Time: 0.000 s / 0.000 s")
        self.lbl_time_info.setCursor(Qt.PointingHandCursor)
        self.lbl_time_info.setToolTip("Click to display Timeline ruler in Time (seconds)")
        self.lbl_time_info.mousePressEvent = lambda e: self.timeline.set_display_mode("time")
        self.lbl_time_info.setStyleSheet("color: #8C96AB; font-weight: 500;")
        layout.addWidget(self.lbl_time_info)

        layout.addStretch()

        # Rates readout
        self.lbl_rates = QLabel("Point: --- Hz | Analog: --- Hz")
        self.lbl_rates.setStyleSheet("color: #8C96AB; font-size: 11px;")
        layout.addWidget(self.lbl_rates)

    def _get_tinted_icon(self, icon_name: str, color_hex: str) -> QIcon:
        """Load an icon PNG from assets/icons/ and tint its alpha silhouette with color_hex."""
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons", f"{icon_name}.png")
        if not os.path.exists(icon_path):
            return QIcon()
        img = QImage(icon_path)
        if img.isNull():
            return QIcon()
        tinted = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawImage(0, 0, img)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color_hex))
        painter.end()
        return QIcon(QPixmap.fromImage(tinted))

    def _update_playback_icons(self):
        """Update playback toolbar button icons and tints according to the current theme."""
        theme_dict = get_theme(self.current_theme_name)
        is_dark = theme_dict.get("is_dark", True)
        primary_color = "#FFFFFF"
        step_color = "#ECEFF4" if is_dark else "#1C274C"

        if hasattr(self, 'btn_step_back'):
            self.btn_step_back.setIcon(self._get_tinted_icon("previous", step_color))
        if hasattr(self, 'btn_step_fwd'):
            self.btn_step_fwd.setIcon(self._get_tinted_icon("next", step_color))
        if hasattr(self, 'btn_play_pause'):
            is_playing = getattr(self.playback, "is_playing", False) if hasattr(self, 'playback') else False
            play_icon = "pause" if is_playing else "play"
            self.btn_play_pause.setIcon(self._get_tinted_icon(play_icon, primary_color))

    def _setup_menus(self):
        """Construct File, Edit, View, Tools, Help menus."""
        menubar = self.menuBar()

        # ---------------- FILE MENU ----------------
        file_menu = menubar.addMenu("&File")

        act_open = QAction("&Open C3D...", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_file_dialog)
        file_menu.addAction(act_open)

        self.recent_menu = QMenu("Open Recent", self)
        file_menu.addMenu(self.recent_menu)

        act_open_loc = QAction("Open File Location", self)
        act_open_loc.triggered.connect(self.open_file_location)
        file_menu.addAction(act_open_loc)

        file_menu.addSeparator()

        act_save = QAction("&Save", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self.save_file)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As...", self)
        act_save_as.setShortcut(QKeySequence.SaveAs)
        act_save_as.triggered.connect(self.save_as_file)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        # Export Submenu
        export_menu = file_menu.addMenu("Export")

        act_exp_c3d = QAction("Export C3D...", self)
        act_exp_c3d.triggered.connect(self.export_c3d_dialog)
        export_menu.addAction(act_exp_c3d)

        act_exp_stl = QAction("Export 3D Geometry as STL...", self)
        act_exp_stl.triggered.connect(self.export_stl_dialog)
        export_menu.addAction(act_exp_stl)

        act_exp_csv_markers = QAction("Export Marker Trajectories to CSV...", self)
        act_exp_csv_markers.triggered.connect(self.export_markers_csv_dialog)
        export_menu.addAction(act_exp_csv_markers)

        act_exp_csv_analogs = QAction("Export Analog & Force Signals to CSV...", self)
        act_exp_csv_analogs.triggered.connect(self.export_analogs_csv_dialog)
        export_menu.addAction(act_exp_csv_analogs)

        file_menu.addSeparator()

        file_menu.addSeparator()

        # Settings Action (opens main settings window directly with no submenus)
        act_settings = QAction("&Settings...", self)
        act_settings.setMenuRole(QAction.NoRole)
        act_settings.setShortcut(QKeySequence.Preferences)
        act_settings.setStatusTip("Open the main settings configuration window")
        act_settings.triggered.connect(lambda: self.open_settings_dialog(0))
        file_menu.addAction(act_settings)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)


        # ---------------- EDIT MENU ----------------
        # Use invisible zero-width space on macOS so AppKit does not inject AutoFill or other system items
        edit_title = "&Edit\u200b" if sys.platform == "darwin" else "&Edit"
        edit_menu = menubar.addMenu(edit_title)

        if sys.platform == "darwin":
            from gui.macos_utils import clean_macos_edit_menu
            edit_menu.aboutToShow.connect(clean_macos_edit_menu)

        self.act_undo = self.undo_stack.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(self.act_undo)

        self.act_redo = self.undo_stack.createRedoAction(self, "&Redo")
        self.act_redo.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Y")])
        edit_menu.addAction(self.act_redo)

        edit_menu.addSeparator()

        act_summary = QAction("Export Summary Report...", self)
        act_summary.triggered.connect(self.export_summary_report)
        edit_menu.addAction(act_summary)


        # ---------------- VIEW MENU ----------------
        view_menu = menubar.addMenu("&View")

        act_fit = QAction("Fit View / Reset Camera", self)
        act_fit.setShortcut("R")
        act_fit.triggered.connect(self.viewer_3d.fit_view_to_data)
        view_menu.addAction(act_fit)

        view_menu.addSeparator()

        act_iso = QAction("Isometric View", self)
        act_iso.setShortcut("1")
        act_iso.triggered.connect(self.viewer_3d.set_camera_isometric)
        view_menu.addAction(act_iso)

        act_top = QAction("Top View", self)
        act_top.setShortcut("2")
        act_top.triggered.connect(self.viewer_3d.set_camera_top)
        view_menu.addAction(act_top)

        act_front = QAction("Front View", self)
        act_front.setShortcut("3")
        act_front.triggered.connect(self.viewer_3d.set_camera_front)
        view_menu.addAction(act_front)

        act_side = QAction("Side View", self)
        act_side.setShortcut("4")
        act_side.triggered.connect(self.viewer_3d.set_camera_side)
        view_menu.addAction(act_side)

        view_menu.addSeparator()

        # Toggles
        act_toggle_markers = QAction("Show Markers", self, checkable=True)
        act_toggle_markers.setChecked(True)
        act_toggle_markers.toggled.connect(self.viewer_3d.set_show_markers)
        view_menu.addAction(act_toggle_markers)

        act_toggle_plates = QAction("Show Force Plates", self, checkable=True)
        act_toggle_plates.setChecked(True)
        act_toggle_plates.toggled.connect(self.viewer_3d.set_show_force_plates)
        view_menu.addAction(act_toggle_plates)

        act_toggle_p_axes = QAction("Show Force Plate Coordinate Systems", self, checkable=True)
        act_toggle_p_axes.setChecked(True)
        act_toggle_p_axes.toggled.connect(self.viewer_3d.set_show_plate_axes)
        view_menu.addAction(act_toggle_p_axes)

        act_toggle_g_axes = QAction("Show Global Motion Capture Axes", self, checkable=True)
        act_toggle_g_axes.setChecked(True)
        act_toggle_g_axes.toggled.connect(self.viewer_3d.set_show_global_axes)
        view_menu.addAction(act_toggle_g_axes)

        act_toggle_grid = QAction("Show Ground Grid", self, checkable=True)
        act_toggle_grid.setChecked(True)
        act_toggle_grid.toggled.connect(self.viewer_3d.set_show_grid)
        view_menu.addAction(act_toggle_grid)

        act_toggle_grf = QAction("Show Ground Reaction Force (GRF) Vectors", self, checkable=True)
        act_toggle_grf.setChecked(True)
        act_toggle_grf.toggled.connect(self.viewer_3d.set_show_grf_vectors)
        view_menu.addAction(act_toggle_grf)

        view_menu.addSeparator()

        # Panels Submenu (contains exclusively Markers and Analog toggles)
        panels_menu = view_menu.addMenu("&Panels")

        act_toggle_side = self.dock_side.toggleViewAction()
        act_toggle_side.setText("Data Explorer")
        panels_menu.addAction(act_toggle_side)

        act_toggle_plot = self.dock_plotter.toggleViewAction()
        act_toggle_plot.setText("Plotter")
        panels_menu.addAction(act_toggle_plot)

        # Theme Submenu (Direct Theme Switching)
        theme_menu = view_menu.addMenu("&Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_actions = {}
        for t_name in get_theme_names():
            act_t = QAction(t_name, self, checkable=True)
            if t_name == self.current_theme_name:
                act_t.setChecked(True)
            act_t.triggered.connect(lambda checked, name=t_name: self.apply_theme(name))
            self.theme_action_group.addAction(act_t)
            theme_menu.addAction(act_t)
            self.theme_actions[t_name] = act_t


        # ---------------- TOOLS MENU ----------------
        tools_menu = menubar.addMenu("&Tools")

        act_plotter = QAction("&Plotter...", self)
        act_plotter.setShortcut("Ctrl+P")
        act_plotter.setStatusTip("Open Universal Plotter to plot markers, force plates, and analog channels")
        act_plotter.triggered.connect(self.open_plotter_window)
        tools_menu.addAction(act_plotter)

        act_analog = QAction("&Analog...", self)
        act_analog.setStatusTip("Manage and filter analog channels (rename, delete, import, Butterworth/RMS filters)")
        act_analog.triggered.connect(self.open_analog_tools_dialog)
        tools_menu.addAction(act_analog)

        # Events Submenu
        event_menu = tools_menu.addMenu("&Events")

        act_add_ev = QAction("&Add Event at Current Frame...", self)
        act_add_ev.setShortcut("Ctrl+E")
        act_add_ev.setStatusTip("Add a discrete C3D event at the current active frame")
        act_add_ev.triggered.connect(lambda: self.add_event_dialog(self.playback.current_frame))
        event_menu.addAction(act_add_ev)

        act_manage_ev = QAction("&Manage Events...", self)
        act_manage_ev.setStatusTip("Open full event manager dialog")
        act_manage_ev.triggered.connect(self.manage_events_dialog)
        event_menu.addAction(act_manage_ev)

        event_menu.addSeparator()

        act_clear_ev = QAction("&Clear All Events", self)
        act_clear_ev.setStatusTip("Remove all events from the trial")
        act_clear_ev.triggered.connect(self.clear_all_events)
        event_menu.addAction(act_clear_ev)

        tools_menu.addSeparator()

        marker_menu = tools_menu.addMenu("&Marker")

        act_add_marker = QAction("&Add Marker...", self)
        act_add_marker.setStatusTip("Add a new marker with custom coordinates, txt/csv/excel file, and color")
        act_add_marker.triggered.connect(self.open_add_marker_dialog)
        marker_menu.addAction(act_add_marker)

        act_avg_marker = QAction("Create &Average Marker...", self)
        act_avg_marker.triggered.connect(self.open_average_marker_dialog)
        marker_menu.addAction(act_avg_marker)

        act_meas_dist = QAction("Measure &Distance Between 2 Markers...", self)
        act_meas_dist.triggered.connect(self.open_measure_distance_dialog)
        marker_menu.addAction(act_meas_dist)

        act_meas_angle = QAction("Measure &Angle Between 3 Markers...", self)
        act_meas_angle.triggered.connect(self.open_measure_angle_dialog)
        marker_menu.addAction(act_meas_angle)

        act_filter_markers = QAction("&Filter...", self)
        act_filter_markers.setStatusTip("Apply Butterworth low-pass filter to all marker trajectories")
        act_filter_markers.triggered.connect(self.open_filter_markers_dialog)
        marker_menu.addAction(act_filter_markers)

        marker_menu.addSeparator()

        act_rename_marker = QAction("&Rename Selected Marker...", self)
        act_rename_marker.triggered.connect(self.side_panel._action_rename_marker)
        marker_menu.addAction(act_rename_marker)

        act_color_marker = QAction("Change Marker &Color...", self)
        act_color_marker.triggered.connect(self.side_panel._action_change_marker_color)
        marker_menu.addAction(act_color_marker)

        # ---------------- HELP MENU ----------------
        help_menu = menubar.addMenu("&Help")

        act_about = QAction("About C3D explorer", self)
        act_about.setMenuRole(QAction.AboutRole)
        act_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(act_about)

        # On macOS, customize and clean the application menu & Edit menu directly in Cocoa
        if sys.platform == "darwin":
            from PySide6.QtCore import QTimer
            from gui.macos_utils import clean_macos_menus
            QTimer.singleShot(0, lambda: clean_macos_menus("C3D explorer"))
            QTimer.singleShot(150, lambda: clean_macos_menus("C3D explorer"))

    def _setup_status_bar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)

        self.lbl_status_file = QLabel("Ready — Open a C3D file to begin")
        self.status.addWidget(self.lbl_status_file, 1)

        self.lbl_status_stats = QLabel("")
        self.status.addPermanentWidget(self.lbl_status_stats)

    def _connect_signals(self):
        """Cross-connect widgets to achieve seamless synchronization."""
        # Timeline -> Playback & 3D & 2D Plot
        self.timeline.frameChanged.connect(self.playback.set_frame)
        self.timeline.eventClicked.connect(self._on_event_selected)
        self.timeline.addEventRequested.connect(self.add_event_dialog)
        self.timeline.editEventRequested.connect(self.edit_event_dialog)
        self.timeline.deleteEventRequested.connect(self.delete_event)
        self.timeline.displayModeChanged.connect(self._on_timeline_mode_changed)

        # Plotter time cursor dragged -> Playback frame
        self.plotter_widget.timeCursorMoved.connect(self._on_plot_cursor_moved)

        # Side panel interactions
        self.side_panel.markerVisibilityChanged.connect(self.viewer_3d.toggle_marker_visibility)
        self.side_panel.markersSelected.connect(self.viewer_3d.select_markers)
        self.side_panel.addMarkerRequested.connect(self.open_add_marker_dialog)
        self.side_panel.markerRenamed.connect(self._on_marker_renamed)
        self.side_panel.deleteMarkerRequested.connect(self.delete_marker)
        self.side_panel.deleteMarkersRequested.connect(self.delete_marker)
        self.side_panel.plotMarkerRequested.connect(self.plot_marker)
        self.side_panel.plotMarkersRequested.connect(self.plot_markers)
        self.side_panel.plotDistanceRequested.connect(self.plot_marker_distance)
        self.side_panel.markersColorChanged.connect(self._on_markers_color_changed)
        self.side_panel.eventSelected.connect(self._on_event_selected)
        self.side_panel.addEventRequested.connect(lambda: self.add_event_dialog(self.playback.current_frame))
        self.side_panel.editEventRequested.connect(self.edit_event_dialog)
        self.side_panel.deleteEventRequested.connect(self.delete_event)
        self.side_panel.deleteEventsRequested.connect(self.delete_event)

        # Timeline Trim / Cut range synchronization
        self.timeline.trimRangeChanged.connect(self._on_trim_range_changed)
        self.plotter_widget.trimRangeChanged.connect(self._on_plot_roi_changed)

        # 3D Viewer interactive picking -> Side panel synchronization
        self.viewer_3d.markersSelected.connect(self._on_3d_markers_selected)
        self.viewer_3d.markerContextMenuRequested.connect(self._on_3d_marker_context_menu)

    def _on_trim_range_changed(self, start_f: int, end_f: int):
        if not self.trial:
            return
        is_trimmed = (start_f > 0 or end_f < self.trial.point_frame_count - 1)
        if is_trimmed:
            cnt = end_f - start_f + 1
            sec = cnt / self.trial.point_rate if self.trial.point_rate > 0 else 0.0
            self.status.showMessage(f"Cut / ROI region: Frames {start_f + 1} to {end_f + 1} ({cnt} frames, {sec:.3f}s) — Export will include this range only.", 3000)
        else:
            self.status.showMessage("Cut / ROI region reset to full trial", 2000)

        # Synchronize active measurement dialogs with new ROI range
        if self.dist_dialog and self.dist_dialog.isVisible():
            self.dist_dialog.set_trim_range(start_f, end_f)
        if self.angle_dialog and self.angle_dialog.isVisible():
            self.angle_dialog.set_trim_range(start_f, end_f)

        # Synchronize Universal Plotter
        if self.plotter_widget:
            self.plotter_widget.set_trim_range(start_f, end_f)

    def _on_plotter_dock_visibility_changed(self, visible: bool):
        if visible and self.trial:
            if hasattr(self, 'timeline'):
                self.plotter_widget.set_trim_range(self.timeline.trim_start_frame, self.timeline.trim_end_frame)
            if hasattr(self, 'playback'):
                self.plotter_widget.update_frame(self.playback.current_frame)

    # Alias for backward compatibility
    _on_analog_dock_visibility_changed = _on_plotter_dock_visibility_changed

    def _on_plot_roi_changed(self, start_f: int, end_f: int):
        """Synchronize timeline trim when ROI is dragged on a plot window or panel."""
        if hasattr(self, 'timeline'):
            self.timeline.set_trim_range(start_f, end_f)

    # ---------------------------------------------------------
    # Frame & Time Synchronization
    # ---------------------------------------------------------
    def _on_frame_changed(self, frame_idx: int):
        """Synchronize all views when current frame advances."""
        if not self.trial:
            return

        cur_time = self.trial.frame_to_time(frame_idx)

        # 1. Update 3D Viewport
        self.viewer_3d.set_frame(frame_idx)

        # 2. Update Timeline Slider
        self.timeline.set_current_frame(frame_idx)

        # 3. Update Side Panel Live Readouts
        self.side_panel.update_live_values(frame_idx)

        # 4. Update Active Measurement Dialogs & Plotter
        if self.dist_dialog and self.dist_dialog.isVisible():
            self.dist_dialog.update_frame(frame_idx)
        if self.angle_dialog and self.angle_dialog.isVisible():
            self.angle_dialog.update_frame(frame_idx)
        if self.plotter_widget and (self.plotter_widget.isVisible() or self.dock_plotter.isVisible()):
            self.plotter_widget.update_frame(frame_idx)

        # 6. Update Playback Toolbar Labels
        self.lbl_frame_info.setText(f"Frame: {frame_idx + 1} / {self.trial.point_frame_count}")
        self.lbl_time_info.setText(f"Time: {cur_time:.3f} s / {self.trial.duration_seconds:.3f} s")

    def _on_playback_state_changed(self, is_playing: bool):
        play_icon = "pause" if is_playing else "play"
        self.btn_play_pause.setIcon(self._get_tinted_icon(play_icon, "#FFFFFF"))
        self.btn_play_pause.setToolTip("Pause (Spacebar)" if is_playing else "Play / Pause (Spacebar)")

    def _on_plot_cursor_moved(self, time_s: float):
        if self.trial:
            frame = self.trial.time_to_frame(time_s)
            self.playback.set_frame(frame)

    def _on_event_selected(self, event: C3DEvent):
        """Jump playback directly to selected event."""
        if event and self.trial:
            self.playback.pause()
            self.playback.set_frame(event.frame)
            self.status.showMessage(f"Jumped to event: {event.name} ({event.time:.3f}s)", 3000)

    def _on_speed_changed(self, text: str):
        speed_map = {"0.1x": 0.1, "0.25x": 0.25, "0.5x": 0.5, "1.0x": 1.0, "1.5x": 1.5, "2.0x": 2.0}
        val = speed_map.get(text, 1.0)
        self.playback.set_speed(val)
        self._default_speed = text
        self._save_settings({"default_speed": text})

    def _on_loop_toggled(self):
        is_loop = self.btn_loop.isChecked()
        self.btn_loop.setText("Loop: ON" if is_loop else "Loop: OFF")
        self.playback.set_loop(is_loop)
        self._save_settings({"loop": is_loop})

    def _on_timeline_mode_changed(self, mode: str):
        """Update playback toolbar unit toggle button and highlight active format."""
        if hasattr(self, 'btn_timeline_unit'):
            self.btn_timeline_unit.setText("Frame" if mode == "frame" else "Time")
        self._update_time_frame_labels_style()
        self._save_settings({"timeline_display_mode": mode})

    def _update_time_frame_labels_style(self):
        """Highlight active format (Frame vs Time) with accent color and subtle mute for inactive."""
        theme_dict = get_theme(self.current_theme_name)
        is_dark = theme_dict.get("is_dark", True)
        accent = theme_dict.get("accent", "#00ADB5" if is_dark else "#0284C7")
        muted = "#8C96AB" if is_dark else "#6B7280"
        mode = getattr(self.timeline, "display_mode", "frame")

        if hasattr(self, 'lbl_frame_info'):
            if mode == "frame":
                self.lbl_frame_info.setStyleSheet(f"color: {accent}; font-weight: 700;")
            else:
                self.lbl_frame_info.setStyleSheet(f"color: {'#ECEFF4' if is_dark else '#2E3440'}; font-weight: 500;")

        if hasattr(self, 'lbl_time_info'):
            if mode == "time":
                self.lbl_time_info.setStyleSheet(f"color: {accent}; font-weight: 700;")
            else:
                self.lbl_time_info.setStyleSheet(f"color: {muted}; font-weight: 500;")

    # ---------------------------------------------------------
    # Marker Tools & Measurements
    # ---------------------------------------------------------
    def _on_marker_renamed(self, old_name: str, new_name: str):
        if getattr(self, '_is_undo_redo_running', False):
            return
        cmd = RenameMarkerCommand(self, self.trial, old_name, new_name)
        self.undo_stack.push(cmd)

    def _on_marker_color_changed(self, marker_name: str, qcolor):
        self._on_markers_color_changed([marker_name], qcolor)

    def _on_markers_color_changed(self, marker_names: List[str], qcolor):
        if not marker_names or getattr(self, '_is_undo_redo_running', False):
            return
        old_colors = {m: self.viewer_3d.custom_marker_colors.get(m, None) for m in marker_names}
        rgba = (qcolor.redF(), qcolor.greenF(), qcolor.blueF(), qcolor.alphaF()) if qcolor is not None else None
        cmd = ChangeMarkerColorCommand(self, marker_names, old_colors, rgba)
        self.undo_stack.push(cmd)

    def _on_3d_markers_selected(self, names: List[str]):
        """Synchronize marker selection from 3D viewport to side panel and status bar."""
        self.side_panel.select_markers(names)
        if names:
            if len(names) == 1:
                self.status.showMessage(f"Selected marker: {names[0]}", 3000)
            else:
                self.status.showMessage(f"Selected markers ({len(names)}): {', '.join(names)}", 3000)
        else:
            self.status.showMessage("Cleared marker selection", 2000)

    def _on_3d_marker_context_menu(self, global_pos: QPoint, marker_names: List[str]):
        """Forward 3D viewport right-click marker context menu request to side panel."""
        self.side_panel.show_marker_context_menu(global_pos, marker_names)

    def open_add_marker_dialog(self):
        """Open dialog to add a new marker with custom coordinates/file and color."""
        if not self.trial:
            QMessageBox.information(self, "Add Marker", "Please load a C3D trial first.")
            return

        dlg = AddMarkerDialog(self.trial, parent=self)
        dlg.markerAdded.connect(self._on_marker_added)
        dlg.exec()

    def _on_marker_added(self, name: str, data: np.ndarray, color: Optional[QColor]):
        rgba = (color.redF(), color.greenF(), color.blueF(), color.alphaF()) if color else None
        cmd = AddMarkerCommand(self, self.trial, name, data, rgba)
        self.undo_stack.push(cmd)

    def open_filter_markers_dialog(self):
        """Open dialog to configure Butterworth low-pass filter parameters for all markers."""
        if not self.trial or not self.trial.markers:
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                QMessageBox.information(self, "Filter Markers", "Please load a C3D trial with markers first.")
            return

        dlg = FilterMarkersDialog(self.trial, parent=self)
        if dlg.exec() == QDialog.Accepted:
            order = dlg.spin_order.value()
            cutoff = dlg.spin_cutoff.value()
            self.filter_all_markers(order, cutoff)

    def filter_all_markers(self, order: int, cutoff: float):
        """Filter all marker trajectories with the given order and cutoff frequency."""
        if not self.trial or not self.trial.markers:
            return

        fs = float(self.trial.point_rate) if self.trial.point_rate > 0 else 100.0
        old_markers = {name: arr.copy() for name, arr in self.trial.markers.items()}
        new_markers = {name: filter_marker_array(arr, fs, order, cutoff) for name, arr in self.trial.markers.items()}

        cmd = FilterMarkersCommand(self, self.trial, order, cutoff, old_markers, new_markers)
        self.undo_stack.push(cmd)

    def open_average_marker_dialog(self):
        if not self.trial or not self.trial.markers:
            QMessageBox.information(self, "Marker Tool", "Please load a C3D trial first.")
            return
        selected = self.side_panel.get_selected_markers()
        if not selected and hasattr(self.viewer_3d, 'selected_markers'):
            selected = list(self.viewer_3d.selected_markers)
        dlg = CreateAverageMarkerDialog(self.trial, preselected=selected, parent=self)
        dlg.markerCreated.connect(self._on_average_marker_created)
        dlg.exec()

    def _on_average_marker_created(self, name: str, data: np.ndarray):
        cmd = AddMarkerCommand(self, self.trial, name, data)
        self.undo_stack.push(cmd)

    def open_measure_distance_dialog(self):
        if not self.trial or not self.trial.markers:
            QMessageBox.information(self, "Marker Tool", "Please load a C3D trial first.")
            return
        selected = self.side_panel.get_selected_markers()
        if not selected and hasattr(self.viewer_3d, 'selected_markers'):
            selected = list(self.viewer_3d.selected_markers)
        trim_rng = (self.timeline.trim_start_frame, self.timeline.trim_end_frame) if hasattr(self, 'timeline') else None
        self.dist_dialog = MeasureDistanceDialog(
            self.trial, current_frame=self.playback.current_frame,
            preselected=selected, trim_range=trim_rng, parent=self
        )
        self.dist_dialog.visualize3DRequested.connect(self.viewer_3d.set_distance_measurement)
        self.dist_dialog.plotRequested.connect(self._on_plot_custom_curve_requested)
        self.dist_dialog.show()

    def open_measure_angle_dialog(self):
        if not self.trial or not self.trial.markers:
            QMessageBox.information(self, "Marker Tool", "Please load a C3D trial first.")
            return
        selected = self.side_panel.get_selected_markers()
        if not selected and hasattr(self.viewer_3d, 'selected_markers'):
            selected = list(self.viewer_3d.selected_markers)
        trim_rng = (self.timeline.trim_start_frame, self.timeline.trim_end_frame) if hasattr(self, 'timeline') else None
        self.angle_dialog = MeasureAngleDialog(
            self.trial, current_frame=self.playback.current_frame,
            preselected=selected, trim_range=trim_rng, parent=self
        )
        self.angle_dialog.visualize3DRequested.connect(self.viewer_3d.set_angle_measurement)
        self.angle_dialog.plotRequested.connect(self._on_plot_custom_curve_requested)
        self.angle_dialog.show()

    def show_measurement_plot(
        self,
        title: str,
        y_data: np.ndarray,
        unit: str = "mm",
        curve_type: str = "Distance",
        trim_range: Optional[Tuple[int, int]] = None
    ):
        """Plot measurement curve directly into Universal Plotter without a separate pop-up window."""
        self.open_plotter_window()
        self.plotter_widget.add_custom_curve(title, y_data, unit=unit)
        self.status.showMessage(f"Plotted {title} in Universal Plotter", 3000)

    def open_plotter_window(self):
        """Open or bring to focus the Universal Plotter panel (docked or floating)."""
        if self.trial and self.plotter_widget.trial != self.trial:
            self.plotter_widget.load_trial(self.trial)
        elif self.trial:
            self.plotter_widget.reload_events()
        if hasattr(self, 'timeline'):
            self.plotter_widget.set_trim_range(self.timeline.trim_start_frame, self.timeline.trim_end_frame)
        self.dock_plotter.show()
        self.dock_plotter.raise_()
        if self.dock_plotter.isFloating():
            self.dock_plotter.activateWindow()
        if self.trial:
            self.plotter_widget.update_frame(self.playback.current_frame)

    def open_analog_tools_dialog(self):
        """Open the Analog Channels Manager & Signal Processing dialog."""
        if not self.trial:
            QMessageBox.information(self, "Analog Tools", "Please load a C3D trial first.")
            return

        self.analog_dialog = AnalogToolsDialog(self.trial, parent=self)
        self.analog_dialog.analogsChanged.connect(self._on_analogs_changed)
        self.analog_dialog.plotChannelRequested.connect(self._on_plot_analog_channel_requested)
        self.analog_dialog.plotChannelsRequested.connect(self._on_plot_analog_channels_requested)
        self.analog_dialog.show()
        self.analog_dialog.raise_()
        self.analog_dialog.activateWindow()

    def _on_plot_analog_channel_requested(self, ch_name: str):
        """Activate the analog channel under Analog Channels in Universal Plotter and plot it."""
        self._on_plot_analog_channels_requested([ch_name])

    def _on_plot_analog_channels_requested(self, ch_names: List[str]):
        """Activate multiple analog channels under Analog Channels in Universal Plotter and plot them."""
        self.open_plotter_window()
        self.plotter_widget.plot_analog_channels(ch_names)
        if len(ch_names) == 1:
            self.status.showMessage(f"Plotted analog channel '{ch_names[0]}' in Universal Plotter", 3000)
        else:
            self.status.showMessage(f"Plotted {len(ch_names)} analog channels in Universal Plotter", 3000)

    def _on_analogs_changed(self):
        """Called when analog channels are modified (renamed, deleted, added, filtered)."""
        if self.trial and hasattr(self, 'plotter_widget'):
            self.plotter_widget.load_trial(self.trial)
        self._update_status_stats()

    def _on_plot_custom_curve_requested(self, label: str, y_data: np.ndarray):
        """Slot for custom curve plot requests (e.g. from distance or angle dialogs)."""
        self.open_plotter_window()
        self.plotter_widget.add_custom_curve(label, y_data)

    def plot_marker(self, marker_name: str):
        """Immediately open plotter and plot X, Y, Z coordinates of marker."""
        if not self.trial or not marker_name or marker_name not in self.trial.markers:
            return

        self.open_plotter_window()
        self.plotter_widget.plot_marker_coordinates(marker_name, components=("X", "Y", "Z"), clear_others=True)
        self.status.showMessage(f"Plotted coordinates for marker: {marker_name} (X, Y, Z)", 3000)

    def plot_markers(self, marker_names: List[str]):
        """Immediately open plotter and plot X, Y, Z coordinates of multiple markers."""
        if not self.trial or not marker_names:
            return
        valid_markers = [m for m in marker_names if m in self.trial.markers]
        if not valid_markers:
            return

        self.open_plotter_window()
        self.plotter_widget.plot_markers_coordinates(valid_markers, components=("X", "Y", "Z"), clear_others=True)
        self.status.showMessage(f"Plotted coordinates for {len(valid_markers)} markers (X, Y, Z)", 3000)

    def plot_marker_distance(self, m1: str, m2: str):
        """Calculate frame-by-frame Euclidean distance between two markers and plot it."""
        if not self.trial or not m1 or not m2:
            return
        if m1 not in self.trial.markers or m2 not in self.trial.markers:
            return

        from gui.marker_tools_dialog import compute_distance_trajectory
        d1 = self.trial.markers[m1]
        d2 = self.trial.markers[m2]
        dist_traj = compute_distance_trajectory(d1, d2)

        # Clear any 3D measurement line in 3D viewer (no connecting line)
        if hasattr(self, 'viewer_3d'):
            self.viewer_3d.set_distance_measurement("", "", False)

        # Update Universal Plotter directly (no separate pop-up window, no 3D line)
        self.open_plotter_window()
        self.plotter_widget.plot_distance(m1, m2, dist_traj, clear_others=False)

        self.status.showMessage(f"Plotted Euclidean distance between {m1} and {m2}", 3000)

    # ---------------------------------------------------------
    # Event Management
    # ---------------------------------------------------------
    def _refresh_event_views(self):
        """Update timeline, 2D plotter, and side panel when events change."""
        if not self.trial:
            return
        self.trial.events.sort(key=lambda e: e.time)
        self.timeline.set_trial_data(self.trial.point_frame_count, self.trial.point_rate, self.trial.events)
        self.timeline.set_current_frame(self.playback.current_frame)
        self.plotter_widget.reload_events()
        self.side_panel._populate_events()
        self._update_status_stats()

    def _update_status_stats(self):
        """Update permanent status bar stats widget."""
        if not self.trial:
            self.lbl_status_stats.setText("")
            return
        self.lbl_status_stats.setText(
            f"Markers: {len(self.trial.markers)} | Analogs: {len(self.trial.analogs)} | "
            f"Force Plates: {len(self.trial.force_platforms)} | Events: {len(self.trial.events)} | "
            f"Frames: {self.trial.point_frame_count}"
        )

    def add_event_dialog(self, frame: Optional[int] = None):
        """Prompt user to add an event at the specified frame or current playhead."""
        if not self.trial:
            QMessageBox.information(self, "Add Event", "Please load a C3D trial first.")
            return

        target_frame = frame if frame is not None else self.playback.current_frame
        dlg = EventEditDialog(trial=self.trial, current_frame=target_frame, parent=self)
        if dlg.exec():
            new_ev = dlg.get_event()
            cmd = AddEventCommand(self, self.trial, new_ev)
            self.undo_stack.push(cmd)

    def edit_event_dialog(self, event: C3DEvent):
        """Prompt user to edit an existing event."""
        if not self.trial or event not in self.trial.events:
            return

        dlg = EventEditDialog(trial=self.trial, current_frame=event.frame, event_to_edit=event, parent=self)
        if dlg.exec():
            updated_ev = dlg.get_event()
            cmd = EditEventCommand(self, self.trial, event, updated_ev)
            self.undo_stack.push(cmd)

    def delete_event(self, event_or_events):
        """Confirm and delete one or multiple discrete events."""
        if not self.trial:
            return

        if isinstance(event_or_events, (list, tuple)):
            events = [e for e in event_or_events if e in self.trial.events]
        else:
            events = [event_or_events] if event_or_events in self.trial.events else []

        if not events:
            return

        if len(events) == 1:
            title = "Delete Event"
            prompt = f"Are you sure you want to delete event '{events[0].display_name}' at frame {events[0].frame}?"
        else:
            title = "Delete Events"
            prompt = f"Are you sure you want to delete all {len(events)} selected events?"

        confirm = QMessageBox.question(
            self,
            title,
            prompt,
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            if len(events) == 1:
                cmd = DeleteEventCommand(self, self.trial, events[0])
            else:
                cmd = DeleteEventsCommand(self, self.trial, events)
            self.undo_stack.push(cmd)

    def delete_marker(self, marker_or_markers, confirm: bool = True):
        """Confirm and delete one or multiple markers with full undo/redo."""
        if not self.trial or not self.trial.markers:
            return

        if isinstance(marker_or_markers, (list, tuple, set)):
            markers = [m for m in marker_or_markers if m in self.trial.markers]
        else:
            markers = [marker_or_markers] if marker_or_markers in self.trial.markers else []

        if not markers:
            return

        if len(markers) == 1:
            title = "Delete Marker"
            prompt = f"Are you sure you want to delete marker '{markers[0]}'?"
        else:
            title = "Delete Markers"
            prompt = f"Are you sure you want to delete all {len(markers)} selected markers?"

        if confirm:
            res = QMessageBox.question(
                self,
                title,
                prompt,
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return

        if len(markers) == 1:
            cmd = DeleteMarkerCommand(self, self.trial, markers[0])
        else:
            cmd = DeleteMarkersCommand(self, self.trial, markers)
        self.undo_stack.push(cmd)

    def manage_events_dialog(self):
        """Open full table Event Manager dialog."""
        if not self.trial:
            QMessageBox.information(self, "Event Manager", "Please load a C3D trial first.")
            return

        initial_events = [e.clone() for e in self.trial.events]
        dlg = EventManagerDialog(self.trial, current_frame=self.playback.current_frame, parent=self)
        dlg.eventListChanged.connect(self._refresh_event_views)
        dlg.seekRequested.connect(self.playback.set_frame)
        dlg.exec()
        self._refresh_event_views()
        new_events = [e.clone() for e in self.trial.events]
        if [(e.name, e.frame, round(e.time, 4)) for e in initial_events] != [(e.name, e.frame, round(e.time, 4)) for e in new_events]:
            cmd = EventsBatchCommand(self, self.trial, initial_events, new_events)
            self.undo_stack.push(cmd)

    def clear_all_events(self):
        """Remove all events from the active trial."""
        if not self.trial or not self.trial.events:
            QMessageBox.information(self, "Clear Events", "No events to clear.")
            return

        confirm = QMessageBox.question(
            self,
            "Clear All Events",
            f"Are you sure you want to remove all {len(self.trial.events)} events from this trial?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            saved = list(self.trial.events)
            cmd = ClearEventsCommand(self, self.trial, saved)
            self.undo_stack.push(cmd)

    # ---------------------------------------------------------
    # File Operations
    # ---------------------------------------------------------
    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open C3D File", "", "C3D Motion Capture Files (*.c3d);;All Files (*)"
        )
        if path:
            self.load_c3d_file(path)

    def load_c3d_file(self, file_path: str):
        """Parse and load a C3D file."""
        try:
            self.status.showMessage(f"Loading {os.path.basename(file_path)}...")
            trial = C3DReader.read(file_path)
            self.trial = trial
            self.current_file_path = file_path
            self.undo_stack.clear()

            # Configure Playback Controller
            self.playback.set_trial(trial.point_frame_count, trial.point_rate)

            # Update Timeline
            self.timeline.set_trial_data(trial.point_frame_count, trial.point_rate, trial.events)

            # Update 3D Viewport
            self.viewer_3d.load_trial(trial)

            # Update Universal Plotter
            self.plotter_widget.load_trial(trial)
            self.plotter_widget.set_trim_range(self.timeline.trim_start_frame, self.timeline.trim_end_frame)

            # Update Side Inspector Panel
            self.side_panel.load_trial(trial)

            # Update Toolbar & Status
            self.lbl_rates.setText(f"Point: {round(trial.point_rate):.0f} Hz | Analog: {round(trial.analog_rate):.0f} Hz")
            self.lbl_status_file.setText(f"Loaded: {file_path}")
            self.lbl_status_stats.setText(
                f"Markers: {len(trial.markers)} | Analogs: {len(trial.analogs)} | "
                f"Force Plates: {len(trial.force_platforms)} | Events: {len(trial.events)} | "
                f"Frames: {trial.point_frame_count}"
            )
            self.setWindowTitle(f"C3D explorer — {os.path.basename(file_path)}")

            self._add_recent_file(file_path)
            self.status.showMessage(f"Successfully loaded {os.path.basename(file_path)}", 4000)

        except Exception as e:
            QMessageBox.critical(self, "Error Opening C3D", f"Failed to load C3D file:\n{e}")
            self.status.showMessage("Failed to load file", 4000)

    def save_file(self):
        if not self.trial or not self.current_file_path:
            QMessageBox.information(self, "Save C3D", "No C3D file is currently open.")
            return
        try:
            start_f = getattr(self.timeline, 'trim_start_frame', 0)
            end_f = getattr(self.timeline, 'trim_end_frame', self.trial.point_frame_count - 1)
            is_trimmed = (start_f > 0 or end_f < self.trial.point_frame_count - 1)
            C3DWriter.save_c3d(self.trial, self.current_file_path, start_frame=start_f, end_frame=end_f)
            trim_msg = f" (Trimmed: frames {start_f}–{end_f})" if is_trimmed else ""
            self.status.showMessage(f"Saved: {self.current_file_path}{trim_msg}", 3000)
            if is_trimmed:
                self.load_c3d_file(self.current_file_path)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save C3D:\n{e}")

    def save_as_file(self):
        if not self.trial:
            QMessageBox.information(self, "Save As", "No C3D file is currently open.")
            return
        default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else ""
        default_filename = os.path.basename(self.current_file_path) if self.current_file_path else "export.c3d"
        default_path = os.path.join(default_dir, default_filename) if default_dir else default_filename
        path, _ = QFileDialog.getSaveFileName(
            self, "Save C3D As", default_path, "C3D Motion Capture Files (*.c3d)"
        )
        if path:
            if not path.lower().endswith(".c3d"):
                path += ".c3d"
            try:
                start_f = getattr(self.timeline, 'trim_start_frame', 0)
                end_f = getattr(self.timeline, 'trim_end_frame', self.trial.point_frame_count - 1)
                is_trimmed = (start_f > 0 or end_f < self.trial.point_frame_count - 1)
                C3DWriter.save_c3d(self.trial, path, start_frame=start_f, end_frame=end_f)
                trim_msg = f" (Trimmed: frames {start_f}–{end_f})" if is_trimmed else ""
                n_ev = len([e for e in self.trial.events if start_f <= (e.frame if e.frame is not None else int(round(e.time * self.trial.point_rate))) <= end_f])
                self.status.showMessage(f"Saved as: {path} ({n_ev} events){trim_msg}", 3000)
                self.load_c3d_file(path)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save C3D:\n{e}")

    def export_c3d_dialog(self):
        """Export the active C3D trial and events to a separate C3D file."""
        if not self.trial:
            QMessageBox.information(self, "Export C3D", "No C3D file is currently open.")
            return
        default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else ""
        base = os.path.splitext(os.path.basename(self.current_file_path))[0] if self.current_file_path else "export"
        default_name = f"{base}_exported.c3d"
        default_path = os.path.join(default_dir, default_name) if default_dir else default_name
        path, _ = QFileDialog.getSaveFileName(
            self, "Export C3D File", default_path, "C3D Motion Capture Files (*.c3d)"
        )
        if path:
            if not path.lower().endswith(".c3d"):
                path += ".c3d"
            try:
                start_f = getattr(self.timeline, 'trim_start_frame', 0)
                end_f = getattr(self.timeline, 'trim_end_frame', self.trial.point_frame_count - 1)
                C3DWriter.save_c3d(self.trial, path, start_frame=start_f, end_frame=end_f)
                trim_msg = f" (Trimmed: frames {start_f}–{end_f})" if (start_f > 0 or end_f < self.trial.point_frame_count - 1) else ""
                n_ev = len([e for e in self.trial.events if start_f <= (e.frame if e.frame is not None else int(round(e.time * self.trial.point_rate))) <= end_f])
                self.status.showMessage(f"Exported C3D to: {path} ({n_ev} events){trim_msg}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export C3D:\n{e}")

    def open_file_location(self):
        """Reveal active file in OS file manager (Finder on Mac, Explorer on Windows)."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            QMessageBox.information(self, "File Location", "No active file loaded.")
            return
        folder = os.path.dirname(os.path.abspath(self.current_file_path))
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", self.current_file_path])
        elif sys.platform == "win32":
            subprocess.run(["explorer", f"/select,{self.current_file_path}"])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def export_stl_dialog(self):
        """Export 3D geometry of force plates and markers as binary STL."""
        if not self.trial:
            QMessageBox.information(self, "Export STL", "No trial loaded.")
            return
        default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else ""
        base = os.path.splitext(os.path.basename(self.current_file_path))[0] if self.current_file_path else "export"
        default_stl = os.path.join(default_dir, f"{base}.stl") if default_dir else f"{base}.stl"
        path, _ = QFileDialog.getSaveFileName(self, "Export 3D Geometry to STL", default_stl, "STL Files (*.stl)")
        if path:
            if not path.lower().endswith(".stl"):
                path += ".stl"
            try:
                C3DWriter.export_stl(self.trial, path, self.playback.current_frame)
                QMessageBox.information(self, "Export Complete", f"STL exported successfully:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export STL:\n{e}")

    def export_markers_csv_dialog(self):
        if not self.trial:
            QMessageBox.information(self, "Export CSV", "No trial loaded.")
            return
        default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else ""
        base = os.path.splitext(os.path.basename(self.current_file_path))[0] if self.current_file_path else "export"
        default_csv = os.path.join(default_dir, f"{base}_markers.csv") if default_dir else f"{base}_markers.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Markers to CSV", default_csv, "CSV Files (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            try:
                start_f = getattr(self.timeline, 'trim_start_frame', 0)
                end_f = getattr(self.timeline, 'trim_end_frame', self.trial.point_frame_count - 1)
                C3DWriter.export_markers_csv(self.trial, path, start_frame=start_f, end_frame=end_f)
                trim_msg = f" (Frames {start_f}–{end_f})" if (start_f > 0 or end_f < self.trial.point_frame_count - 1) else ""
                QMessageBox.information(self, "Export Complete", f"Markers CSV exported successfully{trim_msg}:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")

    def export_analogs_csv_dialog(self):
        if not self.trial:
            QMessageBox.information(self, "Export CSV", "No trial loaded.")
            return
        default_dir = os.path.dirname(self.current_file_path) if self.current_file_path else ""
        base = os.path.splitext(os.path.basename(self.current_file_path))[0] if self.current_file_path else "export"
        default_csv = os.path.join(default_dir, f"{base}_analogs.csv") if default_dir else f"{base}_analogs.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Analogs to CSV", default_csv, "CSV Files (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            try:
                start_f = getattr(self.timeline, 'trim_start_frame', 0)
                end_f = getattr(self.timeline, 'trim_end_frame', self.trial.point_frame_count - 1)
                C3DWriter.export_analogs_csv(self.trial, path, start_frame=start_f, end_frame=end_f)
                trim_msg = f" (Frames {start_f}–{end_f})" if (start_f > 0 or end_f < self.trial.point_frame_count - 1) else ""
                QMessageBox.information(self, "Export Complete", f"Analogs CSV exported successfully{trim_msg}:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")

    def export_summary_report(self):
        """Export text summary report."""
        if not self.trial:
            QMessageBox.information(self, "Summary Report", "No trial loaded.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Summary Report", "", "Text Files (*.txt)")
        if path:
            try:
                lines = [
                    "=" * 60,
                    f"C3D TRIAL SUMMARY REPORT: {os.path.basename(self.trial.file_path)}",
                    "=" * 60,
                    f"File Path: {self.trial.file_path}",
                    f"Point Frame Count: {self.trial.point_frame_count}",
                    f"Point Frequency: {round(self.trial.point_rate):.0f} Hz",
                    f"Analog Frame Count: {self.trial.analog_frame_count}",
                    f"Analog Frequency: {round(self.trial.analog_rate):.0f} Hz",
                    f"Duration: {self.trial.duration_seconds:.3f} s",
                    f"Marker Units: {self.trial.marker_units}",
                    "",
                    f"Markers ({len(self.trial.markers)}):",
                    ", ".join(sorted(self.trial.markers.keys())),
                    "",
                    f"Force Platforms ({len(self.trial.force_platforms)}):",
                ]
                for fp in self.trial.force_platforms:
                    lines.append(f"  Plate #{fp.id}: Type {fp.type}, {fp.width:.1f}x{fp.length:.1f} mm, Origin: {fp.origin}")
                lines.append("")
                lines.append(f"Events ({len(self.trial.events)}):")
                for ev in self.trial.events:
                    lines.append(f"  {ev.name}: {ev.time:.3f} s (Frame {ev.frame}) [{ev.context}]")

                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                QMessageBox.information(self, "Report Exported", f"Summary saved:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export report:\n{e}")

    # ---------------------------------------------------------
    # Settings & Dialogs
    # ---------------------------------------------------------
    def apply_theme(self, theme_name: str):
        """Apply one of the 5 built-in professional themes across entire application."""
        theme_dict = get_theme(theme_name)
        theme_name = theme_dict["name"]
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme_dict["qss"])
            app.setPalette(create_theme_palette(theme_dict))
        self.viewer_3d.apply_theme(theme_dict)
        self.plotter_widget.apply_theme(theme_dict)
        self.side_panel.apply_theme(theme_dict)
        if hasattr(self, 'timeline'):
            self.timeline.apply_theme(theme_dict)
        self.current_theme_name = theme_name
        is_dark = theme_dict.get("is_dark", True)
        if not is_dark:
            self.side_panel.set_default_marker_color(QColor("#000000"))
        else:
            if getattr(self.viewer_3d, "marker_color", None) and self.viewer_3d.marker_color[:3] == (1.0, 1.0, 1.0):
                self.side_panel.set_default_marker_color(QColor("#FFFFFF"))
        if hasattr(self, 'lbl_rates'):
            self.lbl_rates.setStyleSheet(f"color: {'#8C96AB' if is_dark else '#6B7280'}; font-size: 11px;")
        self._update_time_frame_labels_style()
        self._update_playback_icons()
        if hasattr(self, 'theme_actions') and theme_name in self.theme_actions:
            self.theme_actions[theme_name].setChecked(True)
        self.status.showMessage(f"Applied theme: {theme_name}", 3000)
        self._save_settings({"theme": theme_name})

    def _collect_current_app_settings(self) -> dict:
        """Collect all current user settings into a clean dictionary."""
        antialias_val = False
        if 'pg' in globals() and hasattr(pg, 'getConfigOption'):
            try:
                antialias_val = pg.getConfigOption("antialias")
            except Exception:
                antialias_val = False

        bg_choice = getattr(self, '_viewport_bg_choice', "Theme Default")
        return {
            "theme": self.current_theme_name,
            "viewport_bg_choice": bg_choice,
            "viewport_bg": getattr(self, '_viewport_bg', None),
            "show_grid": self.viewer_3d.show_grid,
            "grid_spacing": getattr(self.viewer_3d, 'grid_spacing', 500.0),
            "show_markers": self.viewer_3d.show_markers,
            "show_force_plates": self.viewer_3d.show_force_plates,
            "show_grf_vectors": self.viewer_3d.show_grf_vectors,
            "show_global_axes": self.viewer_3d.show_global_axes,
            "axis_line_width": getattr(self.viewer_3d, 'axis_line_width', 2.0),
            "axis_length": getattr(self.viewer_3d, 'axis_length', 320.0),
            "show_plate_axes": self.viewer_3d.show_plate_axes,
            "z_up": getattr(self.viewer_3d, 'z_up', True),
            "ground_rotation": getattr(self.viewer_3d, 'ground_rotation', 0.0),
            "marker_size": self.viewer_3d.marker_size,
            "marker_color": list(getattr(self.viewer_3d, 'marker_color', (1.0, 1.0, 1.0, 1.0))),
            "marker_color_name": getattr(self, '_marker_color_name', None),
            "grf_vector_scale": self.viewer_3d.grf_vector_scale,
            "grf_threshold_n": self.viewer_3d.grf_threshold_n,
            "grf_color": list(getattr(self.viewer_3d, 'grf_color', (1.0, 0.35, 0.08, 1.0))),
            "grf_color_name": getattr(self, '_grf_color_name', None),
            "default_speed": getattr(self, '_default_speed', "1.0x (Real-time)"),
            "loop": self.playback.is_looping,
            "plot_antialias": antialias_val,
            "timeline_display_mode": getattr(self.timeline, "display_mode", "frame"),
        }

    def open_settings_dialog(self, initial_tab: int = 0):
        current_cfg = self._collect_current_app_settings()
        tab_idx = initial_tab if isinstance(initial_tab, int) else 0
        dlg = SettingsDialog(current_cfg, self, initial_tab=tab_idx)
        dlg.settingsApplied.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, cfg: dict, save_to_disk: bool = True):
        if "theme" in cfg and cfg["theme"] != self.current_theme_name:
            self.apply_theme(cfg["theme"])
        if "viewport_bg_choice" in cfg:
            self._viewport_bg_choice = cfg["viewport_bg_choice"]
        if "viewport_bg" in cfg:
            self._viewport_bg = cfg["viewport_bg"]
            if cfg["viewport_bg"]:
                self.viewer_3d.set_viewport_bg(cfg["viewport_bg"])
            else:
                theme_dict = get_theme(self.current_theme_name)
                self.viewer_3d.set_viewport_bg(theme_dict.get("viewport_bg", "#151720"))
        if "axis_line_width" in cfg:
            self.viewer_3d.set_axis_line_width(cfg["axis_line_width"])
        if "axis_length" in cfg:
            self.viewer_3d.set_axis_length(cfg["axis_length"])
        if "show_global_axes" in cfg:
            self.viewer_3d.set_show_global_axes(cfg["show_global_axes"])
        if "show_plate_axes" in cfg:
            self.viewer_3d.set_show_plate_axes(cfg["show_plate_axes"])
        if "z_up" in cfg:
            self.viewer_3d.set_z_up(cfg["z_up"])
        if "ground_rotation" in cfg:
            self.viewer_3d.set_ground_rotation(cfg["ground_rotation"])
        if "show_grid" in cfg:
            self.viewer_3d.set_show_grid(cfg["show_grid"])
        if "grid_spacing" in cfg:
            self.viewer_3d.set_grid_spacing(cfg["grid_spacing"])
        if "show_markers" in cfg:
            self.viewer_3d.set_show_markers(cfg["show_markers"])
        if "show_force_plates" in cfg:
            self.viewer_3d.set_show_force_plates(cfg["show_force_plates"])
        if "show_grf_vectors" in cfg:
            self.viewer_3d.set_show_grf_vectors(cfg["show_grf_vectors"])
        if "marker_size" in cfg:
            self.viewer_3d.set_marker_size(cfg["marker_size"])
        if "marker_color" in cfg:
            self._marker_color_name = cfg.get("marker_color_name", "")
            self.viewer_3d.set_marker_color(cfg["marker_color"])
            c_rgba = cfg["marker_color"]
            qcol = QColor.fromRgbF(c_rgba[0], c_rgba[1], c_rgba[2], 1.0)
            self.side_panel.set_default_marker_color(qcol)
        if "grf_vector_scale" in cfg:
            self.viewer_3d.set_grf_vector_scale(cfg["grf_vector_scale"])
        if "grf_threshold_n" in cfg:
            self.viewer_3d.grf_threshold_n = cfg["grf_threshold_n"]
        if "grf_color" in cfg:
            self._grf_color_name = cfg.get("grf_color_name", "")
            self.viewer_3d.set_grf_color(cfg["grf_color"])
        if "loop" in cfg:
            self.playback.set_loop(cfg["loop"])
            self.btn_loop.setChecked(cfg["loop"])
            self.btn_loop.setText("Loop: ON" if cfg["loop"] else "Loop: OFF")
        if "default_speed" in cfg:
            self._default_speed = cfg["default_speed"]
            spd_clean = cfg["default_speed"].replace(" (Real-time)", "")
            idx = self.combo_speed.findText(spd_clean)
            if idx >= 0:
                self.combo_speed.setCurrentIndex(idx)
        if "plot_antialias" in cfg:
            aa = cfg["plot_antialias"]
            if 'pg' in globals() and hasattr(pg, 'setConfigOptions'):
                try:
                    pg.setConfigOptions(antialias=aa)
                except Exception:
                    pass
            if hasattr(self, 'plotter_widget'):
                self.plotter_widget.set_antialias(aa)
        if "timeline_display_mode" in cfg and hasattr(self, 'timeline'):
            self.timeline.set_display_mode(cfg["timeline_display_mode"])
        elif hasattr(self, 'timeline'):
            self.timeline.set_display_mode("frame")

        if save_to_disk:
            self._save_settings(cfg)

    def _save_settings(self, cfg: Optional[dict] = None):
        """Save settings to QSettings so they persist across application restarts."""
        try:
            import json
            raw = self.settings.value("user_settings_json", None)
            data = json.loads(raw) if raw and isinstance(raw, str) else {}

            if cfg is not None:
                for k, v in cfg.items():
                    if isinstance(v, (tuple, list)):
                        data[k] = list(v)
                    elif isinstance(v, (str, int, float, bool)) or v is None:
                        data[k] = v
            else:
                current = self._collect_current_app_settings()
                for k, v in current.items():
                    if isinstance(v, (tuple, list)):
                        data[k] = list(v)
                    elif isinstance(v, (str, int, float, bool)) or v is None:
                        data[k] = v

            self.settings.setValue("user_settings_json", json.dumps(data))
            self.settings.sync()
        except Exception as e:
            print(f"Warning: Failed to persist user settings: {e}")

    def _load_saved_settings(self):
        """Load user settings from QSettings on startup and set them as active defaults."""
        try:
            import json
            raw = self.settings.value("user_settings_json", None)
            if raw and isinstance(raw, str):
                saved_cfg = json.loads(raw)
                if isinstance(saved_cfg, dict) and saved_cfg:
                    self._apply_settings(saved_cfg, save_to_disk=False)
        except Exception as e:
            print(f"Warning: Failed to load saved user settings: {e}")

    def show_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()

    # ---------------------------------------------------------
    # Drag & Drop Support
    # ---------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".c3d"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".c3d"):
                self.load_c3d_file(path)
                event.acceptProposedAction()
                return

    # ---------------------------------------------------------
    # Recent Files Handling
    # ---------------------------------------------------------
    def _add_recent_file(self, file_path: str):
        recent = self.settings.value("recent_files", []) or []
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        recent = recent[:self.MAX_RECENT_FILES]
        self.settings.setValue("recent_files", recent)
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("recent_files", []) or []
        if not recent:
            act = QAction("No recent files", self)
            act.setEnabled(False)
            self.recent_menu.addAction(act)
            return

        for path in recent:
            if os.path.exists(path):
                act = QAction(os.path.basename(path), self)
                act.setToolTip(path)
                act.triggered.connect(lambda checked, p=path: self.load_c3d_file(p))
                self.recent_menu.addAction(act)

    def closeEvent(self, event):
        if self.plotter_window:
            self.plotter_window.close()
        super().closeEvent(event)


"""Main application window for C3D Explorer."""

import os
import subprocess
import sys
import numpy as np
from typing import Optional, List
from PySide6.QtCore import Qt, QSettings, QFileInfo, QUrl
from PySide6.QtGui import (
    QAction, QActionGroup, QKeySequence, QIcon, QDesktopServices,
    QDragEnterEvent, QDropEvent
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QDockWidget, QToolBar, QComboBox,
    QPushButton, QLabel, QStatusBar, QMenu
)

from gui.theme import THEMES, get_theme, get_theme_names, DEFAULT_THEME_NAME

from core.data_models import C3DTrial, C3DEvent
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
import pyqtgraph as pg
from gui.viewer_3d import Viewer3D
from gui.timeline_widget import TimelineWidget
from gui.playback_controller import PlaybackController
from gui.plot_panel import PlotPanel
from gui.side_panel import SidePanel
from gui.settings_dialog import SettingsDialog
from gui.marker_tools_dialog import CreateAverageMarkerDialog, MeasureDistanceDialog, MeasureAngleDialog
from gui.plotter_window import UniversalPlotterWindow
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.about_dialog import AboutDialog


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

        self.dist_dialog: Optional[MeasureDistanceDialog] = None
        self.angle_dialog: Optional[MeasureAngleDialog] = None
        self.plotter_window: Optional[UniversalPlotterWindow] = None
        self.current_theme_name: str = DEFAULT_THEME_NAME

        # Playback Controller
        self.playback = PlaybackController(self)
        self.playback.frameChanged.connect(self._on_frame_changed)
        self.playback.playbackStateChanged.connect(self._on_playback_state_changed)

        # Core Components
        self.viewer_3d = Viewer3D(self)
        self.timeline = TimelineWidget(self)
        self.plot_panel = PlotPanel(self)
        self.side_panel = SidePanel(self)

        self._setup_layout()
        self._setup_menus()
        self._setup_playback_bar()
        self._setup_status_bar()
        self._connect_signals()
        self._update_recent_files_menu()

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

        # --- Left Dock: Markers Panel (Markers, Force Plates, Events) ---
        self.dock_side = QDockWidget("Markers", self)
        self.dock_side.setObjectName("DockMarkers")
        self.dock_side.setWidget(self.side_panel)
        self.dock_side.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_side)

        # --- Bottom Dock: Analog Panel ---
        self.dock_plot = QDockWidget("Analog", self)
        self.dock_plot.setObjectName("DockAnalog")
        self.dock_plot.setWidget(self.plot_panel)
        self.dock_plot.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_plot)
        self.dock_plot.hide()  # By default, Analog panel is deactivated/hidden on launch

    def _setup_playback_bar(self):
        """Build the playback toolbar positioned above the timeline."""
        layout = QHBoxLayout(self.playback_bar_widget)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # Jump to start
        self.btn_jump_start = QPushButton("|<")
        self.btn_jump_start.setToolTip("Jump to Start (Home)")
        self.btn_jump_start.setFixedWidth(36)
        self.btn_jump_start.clicked.connect(self.playback.jump_to_start)
        layout.addWidget(self.btn_jump_start)

        # Step backward 1 frame
        self.btn_step_back = QPushButton("<")
        self.btn_step_back.setToolTip("Step Backward 1 Frame (Left Arrow)")
        self.btn_step_back.setFixedWidth(36)
        self.btn_step_back.clicked.connect(self.playback.step_backward)
        layout.addWidget(self.btn_step_back)

        # Play / Pause
        self.btn_play_pause = QPushButton("Play")
        self.btn_play_pause.setObjectName("primaryBtn")
        self.btn_play_pause.setToolTip("Play / Pause (Spacebar)")
        self.btn_play_pause.setFixedWidth(80)
        self.btn_play_pause.clicked.connect(self.playback.toggle_play_pause)
        layout.addWidget(self.btn_play_pause)

        # Step forward 1 frame
        self.btn_step_fwd = QPushButton(">")
        self.btn_step_fwd.setToolTip("Step Forward 1 Frame (Right Arrow)")
        self.btn_step_fwd.setFixedWidth(36)
        self.btn_step_fwd.clicked.connect(self.playback.step_forward)
        layout.addWidget(self.btn_step_fwd)

        # Jump to end
        self.btn_jump_end = QPushButton(">|")
        self.btn_jump_end.setToolTip("Jump to End (End)")
        self.btn_jump_end.setFixedWidth(36)
        self.btn_jump_end.clicked.connect(self.playback.jump_to_end)
        layout.addWidget(self.btn_jump_end)

        # Stop
        self.btn_stop = QPushButton("■")
        self.btn_stop.setToolTip("Stop and Return to Start")
        self.btn_stop.setFixedWidth(36)
        self.btn_stop.clicked.connect(self.playback.stop)
        layout.addWidget(self.btn_stop)

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

        layout.addSpacing(16)

        # Frame and Time Status Indicators
        self.lbl_frame_info = QLabel("Frame: 0 / 0")
        self.lbl_frame_info.setStyleSheet("font-weight: 600; color: #ECEFF4;")
        layout.addWidget(self.lbl_frame_info)

        self.lbl_time_info = QLabel("Time: 0.000 s / 0.000 s")
        self.lbl_time_info.setStyleSheet("color: #00ADB5; font-weight: 600;")
        layout.addWidget(self.lbl_time_info)

        layout.addStretch()

        # Rates readout
        self.lbl_rates = QLabel("Point: --- Hz | Analog: --- Hz")
        self.lbl_rates.setStyleSheet("color: #8C96AB; font-size: 11px;")
        layout.addWidget(self.lbl_rates)

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
        act_exp_c3d.triggered.connect(self.save_as_file)
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

        # Settings Submenu (under File menu)
        settings_menu = file_menu.addMenu("&Settings")
        settings_menu.menuAction().setMenuRole(QAction.NoRole)

        # Playback speed submenu
        speed_menu = settings_menu.addMenu("Playback Speed")
        speed_menu.menuAction().setMenuRole(QAction.NoRole)
        for spd_txt in ["0.1x", "0.25x", "0.5x", "1.0x", "1.5x", "2.0x"]:
            act_s = QAction(spd_txt, self)
            act_s.setMenuRole(QAction.NoRole)
            act_s.triggered.connect(lambda checked, s=spd_txt: self.combo_speed.setCurrentText(s))
            speed_menu.addAction(act_s)

        act_visual_conf = QAction("&Visual Configurations...", self)
        act_visual_conf.setMenuRole(QAction.NoRole)
        act_visual_conf.triggered.connect(lambda: self.open_settings_dialog(0))
        settings_menu.addAction(act_visual_conf)

        act_ground_conf = QAction("&Ground Reaction & Orientation...", self)
        act_ground_conf.setMenuRole(QAction.NoRole)
        act_ground_conf.triggered.connect(lambda: self.open_settings_dialog(1))
        settings_menu.addAction(act_ground_conf)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ---------------- EDIT MENU ----------------
        edit_menu = menubar.addMenu("&Edit")
        if sys.platform == "darwin":
            from gui.macos_utils import clean_macos_edit_menu
            edit_menu.aboutToShow.connect(clean_macos_edit_menu)

        act_undo = QAction("&Undo", self)
        act_undo.setShortcut(QKeySequence.Undo)
        act_undo.setEnabled(False)
        edit_menu.addAction(act_undo)

        act_redo = QAction("&Redo", self)
        act_redo.setShortcut(QKeySequence.Redo)
        act_redo.setEnabled(False)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_cut = QAction("Cu&t", self)
        act_cut.setShortcut(QKeySequence.Cut)
        act_cut.setEnabled(False)
        edit_menu.addAction(act_cut)

        act_copy = QAction("&Copy", self)
        act_copy.setShortcut(QKeySequence.Copy)
        edit_menu.addAction(act_copy)

        act_paste = QAction("&Paste", self)
        act_paste.setShortcut(QKeySequence.Paste)
        act_paste.setEnabled(False)
        edit_menu.addAction(act_paste)

        act_sel_all = QAction("Select &All", self)
        act_sel_all.setShortcut(QKeySequence.SelectAll)
        edit_menu.addAction(act_sel_all)

        edit_menu.addSeparator()

        act_options = QAction("&Options...", self)
        act_options.triggered.connect(self.open_settings_dialog)
        edit_menu.addAction(act_options)

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
        act_toggle_side.setText("Markers")
        panels_menu.addAction(act_toggle_side)

        act_toggle_plot = self.dock_plot.toggleViewAction()
        act_toggle_plot.setText("Analog")
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

        act_avg_marker = QAction("Create &Average Marker...", self)
        act_avg_marker.triggered.connect(self.open_average_marker_dialog)
        marker_menu.addAction(act_avg_marker)

        act_meas_dist = QAction("Measure &Distance Between 2 Markers...", self)
        act_meas_dist.triggered.connect(self.open_measure_distance_dialog)
        marker_menu.addAction(act_meas_dist)

        act_meas_angle = QAction("Measure &Angle Between 3 Markers...", self)
        act_meas_angle.triggered.connect(self.open_measure_angle_dialog)
        marker_menu.addAction(act_meas_angle)

        marker_menu.addSeparator()

        act_rename_marker = QAction("&Rename Selected Marker...", self)
        act_rename_marker.triggered.connect(self.side_panel._action_rename_marker)
        marker_menu.addAction(act_rename_marker)

        act_color_marker = QAction("Change Marker &Color...", self)
        act_color_marker.triggered.connect(self.side_panel._action_change_marker_color)
        marker_menu.addAction(act_color_marker)

        tools_menu.addSeparator()

        act_summary = QAction("Export Summary Report...", self)
        act_summary.triggered.connect(self.export_summary_report)
        tools_menu.addAction(act_summary)

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

        # 2D Plot time cursor dragged -> Playback frame
        self.plot_panel.timeCursorMoved.connect(self._on_plot_cursor_moved)

        # Side panel interactions
        self.side_panel.markerVisibilityChanged.connect(self.viewer_3d.toggle_marker_visibility)
        self.side_panel.markersSelected.connect(self.viewer_3d.select_markers)
        self.side_panel.markerRenamed.connect(self._on_marker_renamed)
        self.side_panel.markersColorChanged.connect(self._on_markers_color_changed)
        self.side_panel.eventSelected.connect(self._on_event_selected)
        self.side_panel.addEventRequested.connect(lambda: self.add_event_dialog(self.playback.current_frame))
        self.side_panel.editEventRequested.connect(self.edit_event_dialog)
        self.side_panel.deleteEventRequested.connect(self.delete_event)

        # Timeline Trim / Cut range synchronization
        self.timeline.trimRangeChanged.connect(self._on_trim_range_changed)

        # 3D Viewer interactive picking -> Side panel synchronization
        self.viewer_3d.markersSelected.connect(self._on_3d_markers_selected)

    def _on_trim_range_changed(self, start_f: int, end_f: int):
        if not self.trial:
            return
        is_trimmed = (start_f > 0 or end_f < self.trial.point_frame_count - 1)
        if is_trimmed:
            cnt = end_f - start_f + 1
            sec = cnt / self.trial.point_rate if self.trial.point_rate > 0 else 0.0
            self.status.showMessage(f"Cut region: Frames {start_f} to {end_f} ({cnt} frames, {sec:.3f}s) — Export will include this range only.", 3000)
        else:
            self.status.showMessage("Cut region reset to full trial", 2000)

    # ---------------------------------------------------------
    # Frame & Time Synchronization
    # ---------------------------------------------------------
    def _on_frame_changed(self, frame_idx: int):
        """Synchronize all views when current frame advances."""
        if not self.trial:
            return

        # 1. Update 3D Viewport
        self.viewer_3d.set_frame(frame_idx)

        # 2. Update Timeline Slider
        self.timeline.set_current_frame(frame_idx)

        # 3. Update 2D Plot Time Cursor
        cur_time = self.trial.frame_to_time(frame_idx)
        if hasattr(self, 'plot_panel') and self.plot_panel.isVisible():
            self.plot_panel.set_time(cur_time)

        # 4. Update Side Panel Live Readouts
        self.side_panel.update_live_values(frame_idx)

        # 5. Update Active Measurement Dialogs & Plotter
        if self.dist_dialog and self.dist_dialog.isVisible():
            self.dist_dialog.update_frame(frame_idx)
        if self.angle_dialog and self.angle_dialog.isVisible():
            self.angle_dialog.update_frame(frame_idx)
        if self.plotter_window and (self.plotter_window.isVisible() or not self.plotter_window.isHidden()):
            self.plotter_window.update_frame(frame_idx)

        # 6. Update Playback Toolbar Labels
        self.lbl_frame_info.setText(f"Frame: {frame_idx} / {self.trial.point_frame_count - 1}")
        self.lbl_time_info.setText(f"Time: {cur_time:.3f} s / {self.trial.duration_seconds:.3f} s")

    def _on_playback_state_changed(self, is_playing: bool):
        self.btn_play_pause.setText("Pause" if is_playing else "Play")

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

    def _on_loop_toggled(self):
        is_loop = self.btn_loop.isChecked()
        self.btn_loop.setText("Loop: ON" if is_loop else "Loop: OFF")
        self.playback.set_loop(is_loop)

    # ---------------------------------------------------------
    # Marker Tools & Measurements
    # ---------------------------------------------------------
    def _on_marker_renamed(self, old_name: str, new_name: str):
        if self.trial and old_name in self.trial.markers:
            self.trial.markers[new_name] = self.trial.markers.pop(old_name)
            self.viewer_3d.rename_marker(old_name, new_name)
            if self.plotter_window and self.plotter_window.isVisible():
                self.plotter_window.load_trial(self.trial)
            self.status.showMessage(f"Renamed marker '{old_name}' -> '{new_name}'", 3000)

    def _on_marker_color_changed(self, marker_name: str, qcolor):
        self._on_markers_color_changed([marker_name], qcolor)

    def _on_markers_color_changed(self, marker_names: List[str], qcolor):
        if not marker_names:
            return
        if qcolor is None:
            self.viewer_3d.set_markers_custom_colors(marker_names, None)
            if len(marker_names) == 1:
                self.status.showMessage(f"Reset color for marker '{marker_names[0]}'", 3000)
            else:
                self.status.showMessage(f"Reset color for {len(marker_names)} markers", 3000)
        else:
            rgba = (qcolor.redF(), qcolor.greenF(), qcolor.blueF(), qcolor.alphaF())
            self.viewer_3d.set_markers_custom_colors(marker_names, rgba)
            hex_color = qcolor.name().upper()
            if len(marker_names) == 1:
                self.status.showMessage(f"Changed color for marker '{marker_names[0]}' to {hex_color}", 3000)
            else:
                self.status.showMessage(f"Changed color for {len(marker_names)} markers to {hex_color}", 3000)

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
        if self.trial:
            self.trial.markers[name] = data
            self.side_panel.add_marker_entry(name)
            self.viewer_3d.set_frame(self.playback.current_frame)
            self.status.showMessage(f"Created average marker '{name}' successfully", 4000)

    def open_measure_distance_dialog(self):
        if not self.trial or not self.trial.markers:
            QMessageBox.information(self, "Marker Tool", "Please load a C3D trial first.")
            return
        selected = self.side_panel.get_selected_markers()
        if not selected and hasattr(self.viewer_3d, 'selected_markers'):
            selected = list(self.viewer_3d.selected_markers)
        self.dist_dialog = MeasureDistanceDialog(
            self.trial, current_frame=self.playback.current_frame,
            preselected=selected, parent=self
        )
        self.dist_dialog.visualize3DRequested.connect(self.viewer_3d.set_distance_measurement)
        self.dist_dialog.plotRequested.connect(self.plot_panel.add_custom_curve)
        self.dist_dialog.show()

    def open_measure_angle_dialog(self):
        if not self.trial or not self.trial.markers:
            QMessageBox.information(self, "Marker Tool", "Please load a C3D trial first.")
            return
        selected = self.side_panel.get_selected_markers()
        if not selected and hasattr(self.viewer_3d, 'selected_markers'):
            selected = list(self.viewer_3d.selected_markers)
        self.angle_dialog = MeasureAngleDialog(
            self.trial, current_frame=self.playback.current_frame,
            preselected=selected, parent=self
        )
        self.angle_dialog.visualize3DRequested.connect(self.viewer_3d.set_angle_measurement)
        self.angle_dialog.plotRequested.connect(self.plot_panel.add_custom_curve)
        self.angle_dialog.show()

    def open_plotter_window(self):
        """Open or bring to focus the Universal Plotter Window."""
        if self.plotter_window is None:
            cur_f = self.playback.current_frame if self.trial else 0
            self.plotter_window = UniversalPlotterWindow(self.trial, current_frame=cur_f, parent=None)
            self.plotter_window.timeCursorMoved.connect(self._on_plot_cursor_moved)
        else:
            if self.trial and self.plotter_window.trial != self.trial:
                self.plotter_window.load_trial(self.trial)
        self.plotter_window.show()
        self.plotter_window.raise_()
        self.plotter_window.activateWindow()
        if self.trial:
            self.plotter_window.update_frame(self.playback.current_frame)

    # ---------------------------------------------------------
    # Event Management
    # ---------------------------------------------------------
    def _refresh_event_views(self):
        """Update timeline, 2D plot panel, and side panel when events change."""
        if not self.trial:
            return
        self.trial.events.sort(key=lambda e: e.time)
        self.timeline.set_trial_data(self.trial.point_frame_count, self.trial.point_rate, self.trial.events)
        self.timeline.set_current_frame(self.playback.current_frame)
        self.plot_panel.reload_events()
        self.side_panel._populate_events()
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
            self.trial.events.append(new_ev)
            self._refresh_event_views()
            self.status.showMessage(f"Added event '{new_ev.display_name}' at frame {new_ev.frame}", 3500)

    def edit_event_dialog(self, event: C3DEvent):
        """Prompt user to edit an existing event."""
        if not self.trial or event not in self.trial.events:
            return

        dlg = EventEditDialog(trial=self.trial, current_frame=event.frame, event_to_edit=event, parent=self)
        if dlg.exec():
            idx = self.trial.events.index(event)
            updated_ev = dlg.get_event()
            self.trial.events[idx] = updated_ev
            self._refresh_event_views()
            self.status.showMessage(f"Updated event '{updated_ev.display_name}'", 3500)

    def delete_event(self, event: C3DEvent):
        """Confirm and delete a discrete event."""
        if not self.trial or event not in self.trial.events:
            return

        confirm = QMessageBox.question(
            self,
            "Delete Event",
            f"Are you sure you want to delete event '{event.display_name}' at frame {event.frame}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.trial.events.remove(event)
            self._refresh_event_views()
            self.status.showMessage(f"Deleted event '{event.display_name}'", 3500)

    def manage_events_dialog(self):
        """Open full table Event Manager dialog."""
        if not self.trial:
            QMessageBox.information(self, "Event Manager", "Please load a C3D trial first.")
            return

        dlg = EventManagerDialog(self.trial, current_frame=self.playback.current_frame, parent=self)
        dlg.eventListChanged.connect(self._refresh_event_views)
        dlg.seekRequested.connect(self.playback.set_frame)
        dlg.exec()
        self._refresh_event_views()

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
            self.trial.events.clear()
            self._refresh_event_views()
            self.status.showMessage("Cleared all events from trial", 3500)

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

            # Configure Playback Controller
            self.playback.set_trial(trial.point_frame_count, trial.point_rate)

            # Update Timeline
            self.timeline.set_trial_data(trial.point_frame_count, trial.point_rate, trial.events)

            # Update 3D Viewport
            self.viewer_3d.load_trial(trial)

            # Update 2D Plot Panel
            self.plot_panel.load_trial(trial)

            # Update Side Inspector Panel
            self.side_panel.load_trial(trial)

            # Update Universal Plotter Window if active
            if self.plotter_window:
                self.plotter_window.load_trial(trial)

            # Update Toolbar & Status
            self.lbl_rates.setText(f"Point: {trial.point_rate:.1f} Hz | Analog: {trial.analog_rate:.1f} Hz")
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
            C3DWriter.save_c3d(self.trial, self.current_file_path, start_frame=start_f, end_frame=end_f)
            trim_msg = f" (Trimmed: frames {start_f}–{end_f})" if (start_f > 0 or end_f < self.trial.point_frame_count - 1) else ""
            self.status.showMessage(f"Saved: {self.current_file_path}{trim_msg}", 3000)
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
                C3DWriter.save_c3d(self.trial, path, start_frame=start_f, end_frame=end_f)
                self.current_file_path = path
                self.setWindowTitle(f"C3D explorer — {os.path.basename(path)}")
                self._add_recent_file(path)
                trim_msg = f" (Trimmed: frames {start_f}–{end_f})" if (start_f > 0 or end_f < self.trial.point_frame_count - 1) else ""
                self.status.showMessage(f"Saved as: {path}{trim_msg}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save C3D:\n{e}")

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
                    f"Point Frequency: {self.trial.point_rate} Hz",
                    f"Analog Frame Count: {self.trial.analog_frame_count}",
                    f"Analog Frequency: {self.trial.analog_rate} Hz",
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
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme_dict["qss"])
        self.viewer_3d.apply_theme(theme_dict)
        self.plot_panel.apply_theme(theme_dict)
        if self.plotter_window:
            self.plotter_window.apply_theme(theme_dict)
        self.current_theme_name = theme_name
        if hasattr(self, 'theme_actions') and theme_name in self.theme_actions:
            self.theme_actions[theme_name].setChecked(True)
        self.status.showMessage(f"Applied theme: {theme_name}", 3000)

    def open_settings_dialog(self, initial_tab: int = 0):
        antialias_val = False
        if 'pg' in globals() and hasattr(pg, 'getConfigOption'):
            try:
                antialias_val = pg.getConfigOption("antialias")
            except Exception:
                antialias_val = False

        current_cfg = {
            "theme": self.current_theme_name,
            "show_grid": self.viewer_3d.show_grid,
            "grid_spacing": getattr(self.viewer_3d, 'grid_spacing', 500.0),
            "show_markers": self.viewer_3d.show_markers,
            "show_force_plates": self.viewer_3d.show_force_plates,
            "show_grf_vectors": self.viewer_3d.show_grf_vectors,
            "show_global_axes": self.viewer_3d.show_global_axes,
            "axis_line_width": getattr(self.viewer_3d, 'axis_line_width', 2.0),
            "axis_length": getattr(self.viewer_3d, 'axis_length', 320.0),
            "show_plate_axes": self.viewer_3d.show_plate_axes,
            "marker_size": self.viewer_3d.marker_size,
            "grf_vector_scale": self.viewer_3d.grf_vector_scale,
            "grf_threshold_n": self.viewer_3d.grf_threshold_n,
            "loop": self.playback.is_looping,
            "plot_antialias": antialias_val,
        }
        tab_idx = initial_tab if isinstance(initial_tab, int) else 0
        dlg = SettingsDialog(current_cfg, self, initial_tab=tab_idx)
        dlg.settingsApplied.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, cfg: dict):
        if "theme" in cfg and cfg["theme"] != self.current_theme_name:
            self.apply_theme(cfg["theme"])
        if "viewport_bg" in cfg and cfg["viewport_bg"]:
            self.viewer_3d.set_viewport_bg(cfg["viewport_bg"])
        if "axis_line_width" in cfg:
            self.viewer_3d.set_axis_line_width(cfg["axis_line_width"])
        if "axis_length" in cfg:
            self.viewer_3d.set_axis_length(cfg["axis_length"])
        if "show_global_axes" in cfg:
            self.viewer_3d.set_show_global_axes(cfg["show_global_axes"])
        if "show_plate_axes" in cfg:
            self.viewer_3d.set_show_plate_axes(cfg["show_plate_axes"])
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
            self.viewer_3d.marker_color = cfg["marker_color"]
            self.viewer_3d.set_frame(self.playback.current_frame)
        if "grf_vector_scale" in cfg:
            self.viewer_3d.set_grf_vector_scale(cfg["grf_vector_scale"])
        if "grf_threshold_n" in cfg:
            self.viewer_3d.grf_threshold_n = cfg["grf_threshold_n"]
        if "loop" in cfg:
            self.playback.set_loop(cfg["loop"])
            self.btn_loop.setChecked(cfg["loop"])
            self.btn_loop.setText("Loop: ON" if cfg["loop"] else "Loop: OFF")
        if "plot_antialias" in cfg:
            aa = cfg["plot_antialias"]
            if hasattr(self, 'plot_panel'):
                self.plot_panel.set_antialias(aa)
            if self.plotter_window:
                self.plotter_window.set_antialias(aa)

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


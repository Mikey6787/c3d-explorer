"""GUI package for C3D Explorer."""

from gui.main_window import MainWindow
from gui.viewer_3d import Viewer3D
from gui.timeline_widget import TimelineWidget
from gui.plot_panel import PlotPanel
from gui.side_panel import SidePanel
from gui.playback_controller import PlaybackController
from gui.marker_tools_dialog import CreateAverageMarkerDialog, MeasureDistanceDialog, MeasureAngleDialog
from gui.plotter_window import UniversalPlotterWindow
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.theme import DARK_THEME_QSS

__all__ = [
    "MainWindow",
    "Viewer3D",
    "TimelineWidget",
    "PlotPanel",
    "SidePanel",
    "PlaybackController",
    "CreateAverageMarkerDialog",
    "MeasureDistanceDialog",
    "MeasureAngleDialog",
    "UniversalPlotterWindow",
    "EventEditDialog",
    "EventManagerDialog",
    "DARK_THEME_QSS"
]

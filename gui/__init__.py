"""GUI package for C3D Explorer."""

from gui.main_window import MainWindow
from gui.viewer_3d import Viewer3D
from gui.timeline_widget import TimelineWidget
from gui.playback_controller import PlaybackController
from gui.marker_tools_dialog import (
    CreateAverageMarkerDialog, MeasureDistanceDialog, MeasureAngleDialog,
    FilterMarkersDialog, filter_marker_array
)
from gui.plotter_window import UniversalPlotter, UniversalPlotterWindow
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.analog_dialog import AnalogToolsDialog
from gui.theme import DARK_THEME_QSS

__all__ = [
    "MainWindow",
    "Viewer3D",
    "TimelineWidget",
    "SidePanel",
    "PlaybackController",
    "CreateAverageMarkerDialog",
    "MeasureDistanceDialog",
    "MeasureAngleDialog",
    "FilterMarkersDialog",
    "filter_marker_array",
    "UniversalPlotter",
    "UniversalPlotterWindow",
    "EventEditDialog",
    "EventManagerDialog",
    "AnalogToolsDialog",
    "DARK_THEME_QSS"
]

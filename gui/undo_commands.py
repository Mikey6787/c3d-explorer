"""Undo/Redo command classes for C3D Explorer using QUndoCommand."""

from typing import Optional, List, Dict, Any, Tuple
import copy
import numpy as np
from PySide6.QtGui import QUndoCommand, QColor
from core.data_models import C3DTrial, C3DEvent


class AddEventCommand(QUndoCommand):
    """Command to add a C3D event."""

    def __init__(self, main_window, trial: C3DTrial, event: C3DEvent):
        super().__init__(f"Add Event '{event.display_name}'")
        self.mw = main_window
        self.trial = trial
        self.event = event

    def redo(self):
        if self.trial and self.event not in self.trial.events:
            self.trial.events.append(self.event)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Added event '{self.event.display_name}' at frame {self.event.frame}", 3000)

    def undo(self):
        if self.trial and self.event in self.trial.events:
            self.trial.events.remove(self.event)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Undid adding event '{self.event.display_name}'", 3000)


class DeleteEventCommand(QUndoCommand):
    """Command to delete a C3D event."""

    def __init__(self, main_window, trial: C3DTrial, event: C3DEvent):
        super().__init__(f"Delete Event '{event.display_name}'")
        self.mw = main_window
        self.trial = trial
        self.event = event
        self.original_index = trial.events.index(event) if (trial and event in trial.events) else -1

    def redo(self):
        if self.trial and self.event in self.trial.events:
            self.trial.events.remove(self.event)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Deleted event '{self.event.display_name}'", 3000)

    def undo(self):
        if self.trial and self.event not in self.trial.events:
            if 0 <= self.original_index <= len(self.trial.events):
                self.trial.events.insert(self.original_index, self.event)
            else:
                self.trial.events.append(self.event)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Restored event '{self.event.display_name}'", 3000)


class DeleteEventsCommand(QUndoCommand):
    """Command to batch delete multiple C3D events with full undo/redo."""

    def __init__(self, main_window, trial: C3DTrial, events: List[C3DEvent]):
        count = len(events)
        super().__init__(f"Delete {count} Events" if count > 1 else f"Delete Event '{events[0].display_name}'")
        self.mw = main_window
        self.trial = trial
        self.events = list(events)
        self.saved_entries = [
            (trial.events.index(e), e) for e in events if (trial and e in trial.events)
        ]

    def redo(self):
        if self.trial:
            for _, ev in self.saved_entries:
                if ev in self.trial.events:
                    self.trial.events.remove(ev)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Deleted {len(self.saved_entries)} events", 3000)

    def undo(self):
        if self.trial:
            for idx, ev in sorted(self.saved_entries, key=lambda x: x[0]):
                if ev not in self.trial.events:
                    if 0 <= idx <= len(self.trial.events):
                        self.trial.events.insert(idx, ev)
                    else:
                        self.trial.events.append(ev)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Restored {len(self.saved_entries)} events", 3000)



class EditEventCommand(QUndoCommand):
    """Command to edit an existing C3D event."""

    def __init__(self, main_window, trial: C3DTrial, old_event: C3DEvent, new_event: C3DEvent):
        super().__init__(f"Edit Event '{new_event.display_name}'")
        self.mw = main_window
        self.trial = trial
        self.old_event = old_event
        self.new_event = new_event

    def redo(self):
        if self.trial:
            if self.old_event in self.trial.events:
                idx = self.trial.events.index(self.old_event)
                self.trial.events[idx] = self.new_event
            elif self.new_event not in self.trial.events:
                self.trial.events.append(self.new_event)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Updated event '{self.new_event.display_name}'", 3000)

    def undo(self):
        if self.trial:
            if self.new_event in self.trial.events:
                idx = self.trial.events.index(self.new_event)
                self.trial.events[idx] = self.old_event
            elif self.old_event not in self.trial.events:
                self.trial.events.append(self.old_event)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Reverted event '{self.old_event.display_name}'", 3000)


class ClearEventsCommand(QUndoCommand):
    """Command to clear all events."""

    def __init__(self, main_window, trial: C3DTrial, saved_events: List[C3DEvent]):
        super().__init__("Clear All Events")
        self.mw = main_window
        self.trial = trial
        self.saved_events = list(saved_events)

    def redo(self):
        if self.trial:
            self.trial.events.clear()
        self.mw._refresh_event_views()
        self.mw.status.showMessage("Cleared all events from trial", 3000)

    def undo(self):
        if self.trial:
            self.trial.events.clear()
            self.trial.events.extend(self.saved_events)
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage(f"Restored {len(self.saved_events)} events", 3000)


class EventsBatchCommand(QUndoCommand):
    """Command for batch changes from EventManagerDialog."""

    def __init__(self, main_window, trial: C3DTrial, old_events: List[C3DEvent], new_events: List[C3DEvent]):
        super().__init__("Event Manager Changes")
        self.mw = main_window
        self.trial = trial
        self.old_events = [e.clone() for e in old_events]
        self.new_events = [e.clone() for e in new_events]

    def redo(self):
        if self.trial:
            self.trial.events = [e.clone() for e in self.new_events]
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()

    def undo(self):
        if self.trial:
            self.trial.events = [e.clone() for e in self.old_events]
            self.trial.events.sort(key=lambda e: e.time)
        self.mw._refresh_event_views()
        self.mw.status.showMessage("Reverted Event Manager changes", 3000)


class RenameMarkerCommand(QUndoCommand):
    """Command to rename a marker."""

    def __init__(self, main_window, trial: C3DTrial, old_name: str, new_name: str):
        super().__init__(f"Rename Marker '{old_name}' \u2192 '{new_name}'")
        self.mw = main_window
        self.trial = trial
        self.old_name = old_name
        self.new_name = new_name

    def redo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial and self.old_name in self.trial.markers:
                self.trial.markers[self.new_name] = self.trial.markers.pop(self.old_name)
            self.mw.viewer_3d.rename_marker(self.old_name, self.new_name)
            self.mw.side_panel.rename_marker_entry(self.old_name, self.new_name)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            self.mw.status.showMessage(f"Renamed marker '{self.old_name}' \u2192 '{self.new_name}'", 3000)
        finally:
            self.mw._is_undo_redo_running = False

    def undo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial and self.new_name in self.trial.markers:
                self.trial.markers[self.old_name] = self.trial.markers.pop(self.new_name)
            self.mw.viewer_3d.rename_marker(self.new_name, self.old_name)
            self.mw.side_panel.rename_marker_entry(self.new_name, self.old_name)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            self.mw.status.showMessage(f"Restored marker name '{self.old_name}'", 3000)
        finally:
            self.mw._is_undo_redo_running = False


class AddMarkerCommand(QUndoCommand):
    """Command to add a newly created/average/custom marker."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        name: str,
        data: np.ndarray,
        color_rgba: Optional[tuple] = None,
        source_type: str = "manual",
        source_file: str = "",
        parent_markers: Optional[Tuple[str, str]] = None,
        default_coords: Optional[Tuple[float, float, float]] = None
    ):
        super().__init__(f"Add Marker '{name}'")
        self.mw = main_window
        self.trial = trial
        self.name = name
        self.data = data
        self.color_rgba = color_rgba
        self.source_type = source_type
        self.source_file = source_file
        self.parent_markers = parent_markers
        self.default_coords = default_coords

    def redo(self):
        if self.trial:
            self.trial.markers[self.name] = self.data
            self.mw.side_panel.add_marker_entry(self.name)
            if self.color_rgba is not None:
                self.mw.viewer_3d.set_markers_custom_colors([self.name], self.color_rgba)
                qcol = QColor.fromRgbF(*self.color_rgba)
                self.mw.side_panel.set_markers_color_entries([self.name], qcol)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            self.mw.status.showMessage(f"Added marker '{self.name}' successfully", 3500)

    def undo(self):
        if self.trial and self.name in self.trial.markers:
            del self.trial.markers[self.name]
            self.mw.side_panel.remove_marker_entry(self.name)
            self.mw.viewer_3d.remove_marker(self.name)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            self.mw.status.showMessage(f"Undid marker '{self.name}'", 3000)


class DeleteMarkerCommand(QUndoCommand):
    """Command to delete a single marker with full undo/redo."""

    def __init__(self, main_window, trial: C3DTrial, marker_name: str):
        super().__init__(f"Delete Marker '{marker_name}'")
        self.mw = main_window
        self.trial = trial
        self.name = marker_name
        self.data = trial.markers.get(marker_name) if (trial and marker_name in trial.markers) else None
        self.color_rgba = (
            main_window.viewer_3d.custom_marker_colors.get(marker_name, None)
            if (hasattr(main_window, 'viewer_3d') and hasattr(main_window.viewer_3d, 'custom_marker_colors'))
            else None
        )

    def redo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial and self.name in self.trial.markers:
                del self.trial.markers[self.name]
            self.mw.side_panel.remove_marker_entry(self.name)
            self.mw.viewer_3d.remove_marker(self.name)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            self.mw.status.showMessage(f"Deleted marker '{self.name}'", 3000)
        finally:
            self.mw._is_undo_redo_running = False

    def undo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial and self.data is not None:
                self.trial.markers[self.name] = self.data
                self.mw.side_panel.add_marker_entry(self.name)
                if self.color_rgba is not None:
                    self.mw.viewer_3d.set_markers_custom_colors([self.name], self.color_rgba)
                    qcol = QColor.fromRgbF(*self.color_rgba)
                    self.mw.side_panel.set_markers_color_entries([self.name], qcol)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            self.mw.status.showMessage(f"Restored marker '{self.name}'", 3000)
        finally:
            self.mw._is_undo_redo_running = False


class DeleteMarkersCommand(QUndoCommand):
    """Command to batch delete multiple markers with full undo/redo."""

    def __init__(self, main_window, trial: C3DTrial, marker_names: List[str]):
        count = len(marker_names)
        super().__init__(f"Delete {count} Markers" if count > 1 else f"Delete Marker '{marker_names[0]}'")
        self.mw = main_window
        self.trial = trial
        self.marker_names = list(marker_names)
        self.saved_markers: Dict[str, np.ndarray] = {}
        self.saved_colors: Dict[str, Any] = {}
        if trial:
            for name in marker_names:
                if name in trial.markers:
                    self.saved_markers[name] = trial.markers[name]
                    if hasattr(main_window, 'viewer_3d') and hasattr(main_window.viewer_3d, 'custom_marker_colors'):
                        col = main_window.viewer_3d.custom_marker_colors.get(name, None)
                        if col is not None:
                            self.saved_colors[name] = col

    def redo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial:
                for name in self.saved_markers.keys():
                    if name in self.trial.markers:
                        del self.trial.markers[name]
                    self.mw.side_panel.remove_marker_entry(name)
                    self.mw.viewer_3d.remove_marker(name)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            count = len(self.saved_markers)
            msg = f"Deleted marker '{list(self.saved_markers.keys())[0]}'" if count == 1 else f"Deleted {count} markers"
            self.mw.status.showMessage(msg, 3000)
        finally:
            self.mw._is_undo_redo_running = False

    def undo(self):
        self.mw._is_undo_redo_running = True
        try:
            if self.trial:
                for name, data in self.saved_markers.items():
                    self.trial.markers[name] = data
                    self.mw.side_panel.add_marker_entry(name)
                    if name in self.saved_colors:
                        rgba = self.saved_colors[name]
                        self.mw.viewer_3d.set_markers_custom_colors([name], rgba)
                        qcol = QColor.fromRgbF(*rgba)
                        self.mw.side_panel.set_markers_color_entries([name], qcol)
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
            if self.mw.plotter_window and self.mw.plotter_window.isVisible():
                self.mw.plotter_window.load_trial(self.trial)
            if hasattr(self.mw, '_update_status_stats'):
                self.mw._update_status_stats()
            count = len(self.saved_markers)
            msg = f"Restored marker '{list(self.saved_markers.keys())[0]}'" if count == 1 else f"Restored {count} markers"
            self.mw.status.showMessage(msg, 3000)
        finally:
            self.mw._is_undo_redo_running = False



class ChangeMarkerColorCommand(QUndoCommand):
    """Command to change custom colors of markers."""

    def __init__(self, main_window, marker_names: List[str], old_colors: Dict[str, Any], new_rgba: Optional[tuple]):
        desc = (
            f"Reset Color ({len(marker_names)} markers)" if new_rgba is None
            else f"Change Color ({len(marker_names)} markers)"
        ) if len(marker_names) > 1 else (
            f"Reset Color '{marker_names[0]}'" if new_rgba is None
            else f"Change Color '{marker_names[0]}'"
        )
        super().__init__(desc)
        self.mw = main_window
        self.marker_names = list(marker_names)
        self.old_colors = dict(old_colors)
        self.new_rgba = new_rgba

    def redo(self):
        self.mw._is_undo_redo_running = True
        try:
            self.mw.viewer_3d.set_markers_custom_colors(self.marker_names, self.new_rgba)
            new_qcol = QColor.fromRgbF(*self.new_rgba) if self.new_rgba is not None else None
            self.mw.side_panel.set_markers_color_entries(self.marker_names, new_qcol)
            if self.new_rgba is None:
                msg = f"Reset color for {len(self.marker_names)} markers" if len(self.marker_names) > 1 else f"Reset color for marker '{self.marker_names[0]}'"
            else:
                msg = f"Changed color for {len(self.marker_names)} markers" if len(self.marker_names) > 1 else f"Changed color for marker '{self.marker_names[0]}'"
            self.mw.status.showMessage(msg, 2500)
        finally:
            self.mw._is_undo_redo_running = False

    def undo(self):
        self.mw._is_undo_redo_running = True
        try:
            for m in self.marker_names:
                old_rgba = self.old_colors.get(m, None)
                self.mw.viewer_3d.set_markers_custom_colors([m], old_rgba)
                old_qcol = QColor.fromRgbF(*old_rgba) if old_rgba is not None else None
                self.mw.side_panel.set_markers_color_entries([m], old_qcol)
            msg = f"Restored previous color for {len(self.marker_names)} markers" if len(self.marker_names) > 1 else f"Restored previous color for marker '{self.marker_names[0]}'"
            self.mw.status.showMessage(msg, 2500)
        finally:
            self.mw._is_undo_redo_running = False


class FilterMarkersCommand(QUndoCommand):
    """Command to apply a Butterworth low-pass filter to all marker trajectories."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        order: int,
        cutoff: float,
        old_markers: Dict[str, np.ndarray],
        new_markers: Dict[str, np.ndarray],
        fs: float = 100.0,
        zero_phase: bool = True
    ):
        super().__init__(f"Filter Markers (Order {order}, {cutoff:.1f} Hz)")
        self.mw = main_window
        self.trial = trial
        self.order = order
        self.cutoff = cutoff
        self.old_markers = {k: v.copy() for k, v in old_markers.items()}
        self.new_markers = {k: v.copy() for k, v in new_markers.items()}
        self.fs = fs
        self.zero_phase = zero_phase

    def redo(self):
        if not self.trial:
            return
        for name, arr in self.new_markers.items():
            self.trial.markers[name] = arr.copy()
        self._refresh()
        self.mw.status.showMessage(
            f"Filtered {len(self.new_markers)} markers (Butterworth Order {self.order}, {self.cutoff:.1f} Hz)",
            3500
        )

    def undo(self):
        if not self.trial:
            return
        for name, arr in self.old_markers.items():
            self.trial.markers[name] = arr.copy()
        self._refresh()
        self.mw.status.showMessage(
            "Undid marker filter, restored original trajectories",
            3500
        )

    def _refresh(self):
        if hasattr(self.mw, 'viewer_3d') and self.mw.viewer_3d:
            self.mw.viewer_3d.set_frame(self.mw.playback.current_frame)
        if hasattr(self.mw, 'plotter_widget') and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "update_data"):
                self.mw.plotter_widget.update_data()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class FilterAnalogChannelCommand(QUndoCommand):
    """Command to apply/overwrite a filter to an existing analog channel."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        channel_name: str,
        old_data: np.ndarray,
        new_data: np.ndarray,
        analog_dialog: Optional[Any] = None,
        filter_method: str = "Butterworth",
        filter_order: Optional[int] = None,
        cutoff: Optional[Any] = None
    ):
        super().__init__(f"Filter Analog Channel '{channel_name}'")
        self.mw = main_window
        self.trial = trial
        self.channel_name = channel_name
        self.old_data = old_data.copy()
        self.new_data = new_data.copy()
        self.analog_dialog = analog_dialog
        self.filter_method = filter_method
        self.filter_order = filter_order
        self.cutoff = cutoff

    def redo(self):
        if not self.trial:
            return
        self.trial.analogs[self.channel_name] = self.new_data.copy()
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(
                f"Overwrote analog channel '{self.channel_name}' with filtered signal",
                3500
            )

    def undo(self):
        if not self.trial:
            return
        self.trial.analogs[self.channel_name] = self.old_data.copy()
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(
                f"Undid filter for analog channel '{self.channel_name}', restored original signal",
                3500
            )

    def _refresh(self):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            dlg._update_filter_preview()
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()

        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "update_data"):
                self.mw.plotter_widget.update_data()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class AddAnalogChannelCommand(QUndoCommand):
    """Command to add a new analog channel (e.g. filtered or imported)."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        channel_name: str,
        data: np.ndarray,
        unit: str = "V",
        analog_dialog: Optional[Any] = None,
        source_type: str = "manual",
        source_file: str = "",
        filter_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(f"Add Analog Channel '{channel_name}'")
        self.mw = main_window
        self.trial = trial
        self.channel_name = channel_name
        self.data = data.copy()
        self.unit = unit
        self.analog_dialog = analog_dialog
        self.source_type = source_type
        self.source_file = source_file
        self.filter_details = filter_details

    def redo(self):
        if not self.trial:
            return
        self.trial.analogs[self.channel_name] = self.data.copy()
        self.trial.analog_units[self.channel_name] = self.unit
        self._refresh(is_add=True)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Added analog channel '{self.channel_name}'", 3500)

    def undo(self):
        if not self.trial:
            return
        self.trial.analogs.pop(self.channel_name, None)
        self.trial.analog_units.pop(self.channel_name, None)
        self._refresh(is_add=False)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Undid adding analog channel '{self.channel_name}'", 3500)

    def _refresh(self, is_add: bool):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            dlg._populate_filter_channels(self.channel_name if is_add else None)
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()

        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_analogs"):
                self.mw.plotter_widget.refresh_analogs()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class DeleteAnalogChannelsCommand(QUndoCommand):
    """Command to delete one or more analog channels."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        channel_names: List[str],
        analog_dialog: Optional[Any] = None
    ):
        desc = f"Delete Analog Channel '{channel_names[0]}'" if len(channel_names) == 1 else f"Delete {len(channel_names)} Analog Channels"
        super().__init__(desc)
        self.mw = main_window
        self.trial = trial
        self.channel_names = list(channel_names)
        self.deleted_data = {ch: trial.analogs[ch].copy() for ch in channel_names if ch in trial.analogs}
        self.deleted_units = {ch: trial.analog_units.get(ch, "V") for ch in channel_names}
        self.analog_dialog = analog_dialog

    def redo(self):
        if not self.trial:
            return
        for ch in self.channel_names:
            self.trial.analogs.pop(ch, None)
            self.trial.analog_units.pop(ch, None)
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Deleted {len(self.channel_names)} analog channel(s)", 3500)

    def undo(self):
        if not self.trial:
            return
        for ch, arr in self.deleted_data.items():
            self.trial.analogs[ch] = arr.copy()
            self.trial.analog_units[ch] = self.deleted_units.get(ch, "V")
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Restored {len(self.deleted_data)} deleted analog channel(s)", 3500)

    def _refresh(self):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            dlg._populate_filter_channels()
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()

        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_analogs"):
                self.mw.plotter_widget.refresh_analogs()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class RenameAnalogChannelCommand(QUndoCommand):
    """Command to rename an analog channel."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        old_name: str,
        new_name: str,
        analog_dialog: Optional[Any] = None
    ):
        super().__init__(f"Rename Analog Channel '{old_name}' \u2192 '{new_name}'")
        self.mw = main_window
        self.trial = trial
        self.old_name = old_name
        self.new_name = new_name
        self.analog_dialog = analog_dialog

    def redo(self):
        if not self.trial or self.old_name not in self.trial.analogs:
            return
        self.trial.analogs[self.new_name] = self.trial.analogs.pop(self.old_name)
        if self.old_name in self.trial.analog_units:
            self.trial.analog_units[self.new_name] = self.trial.analog_units.pop(self.old_name)
        self._refresh(self.new_name)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Renamed analog channel '{self.old_name}' \u2192 '{self.new_name}'", 3500)

    def undo(self):
        if not self.trial or self.new_name not in self.trial.analogs:
            return
        self.trial.analogs[self.old_name] = self.trial.analogs.pop(self.new_name)
        if self.new_name in self.trial.analog_units:
            self.trial.analog_units[self.old_name] = self.trial.analog_units.pop(self.new_name)
        self._refresh(self.old_name)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Restored analog channel name '{self.old_name}'", 3500)

    def _refresh(self, active_ch: str):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            dlg._populate_filter_channels(active_ch)
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()

        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_analogs"):
                self.mw.plotter_widget.refresh_analogs()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class FilterMultipleAnalogChannelsCommand(QUndoCommand):
    """Command to filter or overwrite multiple analog channels simultaneously."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        old_data_dict: Dict[str, np.ndarray],
        new_data_dict: Dict[str, np.ndarray],
        analog_dialog: Optional[Any] = None,
        description: str = "Filter Multiple Analog Channels",
        method: str = "",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(description)
        self.mw = main_window
        self.trial = trial
        self.old_data = {k: v.copy() for k, v in old_data_dict.items()}
        self.new_data = {k: v.copy() for k, v in new_data_dict.items()}
        self.analog_dialog = analog_dialog
        self.channels = list(new_data_dict.keys())
        self.method = method
        self.details = details or {}

    def redo(self):
        if not self.trial:
            return
        for k, v in self.new_data.items():
            self.trial.analogs[k] = v.copy()
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(
                f"Applied filter to {len(self.new_data)} analog channels",
                3500
            )

    def undo(self):
        if not self.trial:
            return
        for k, v in self.old_data.items():
            self.trial.analogs[k] = v.copy()
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(
                f"Undid filter on {len(self.old_data)} analog channels, restored original signals",
                3500
            )

    def _refresh(self):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            if hasattr(dlg, "_update_filter_preview"):
                dlg._update_filter_preview()
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()
        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "update_data"):
                self.mw.plotter_widget.update_data()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class AddMultipleAnalogChannelsCommand(QUndoCommand):
    """Command to add multiple new analog channels simultaneously."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        channel_dict: Dict[str, np.ndarray],
        unit_dict: Optional[Dict[str, str]] = None,
        analog_dialog: Optional[Any] = None,
        description: str = "Add Multiple Analog Channels"
    ):
        super().__init__(description)
        self.mw = main_window
        self.trial = trial
        self.channel_dict = {k: v.copy() for k, v in channel_dict.items()}
        self.unit_dict = dict(unit_dict or {})
        self.analog_dialog = analog_dialog
        self.channels = list(channel_dict.keys())

    def redo(self):
        if not self.trial:
            return
        for k, v in self.channel_dict.items():
            self.trial.analogs[k] = v.copy()
            if k in self.unit_dict:
                self.trial.analog_units[k] = self.unit_dict[k]
        self._refresh(is_add=True)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Added {len(self.channel_dict)} new analog channels", 3500)

    def undo(self):
        if not self.trial:
            return
        for k in self.channel_dict.keys():
            self.trial.analogs.pop(k, None)
            self.trial.analog_units.pop(k, None)
        self._refresh(is_add=False)
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(f"Undid adding {len(self.channel_dict)} analog channels", 3500)

    def _refresh(self, is_add: bool):
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg and hasattr(dlg, "_populate_channel_table"):
            dlg._populate_channel_table()
            if hasattr(dlg, "_populate_filter_channels"):
                dlg._populate_filter_channels()
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()
        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_analogs"):
                self.mw.plotter_widget.refresh_analogs()
            else:
                self.mw.plotter_widget.load_trial(self.trial)


class ConfigureForcePlateCommand(QUndoCommand):
    """Command to calculate or update force platform parameters and ground reaction wrenches."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        old_platforms: List[Any],
        new_platforms: List[Any],
        description: str = "Configure Force Plate",
        pipeline_params: Optional[Dict[str, Any]] = None
    ):
        super().__init__(description)
        self.mw = main_window
        self.trial = trial
        self.old_platforms = [fp.clone() for fp in old_platforms]
        self.new_platforms = [fp.clone() for fp in new_platforms]
        self.description = description
        self.pipeline_params = dict(pipeline_params or {})

    def redo(self):
        if not self.trial:
            return
        self.trial.force_platforms = [fp.clone() for fp in self.new_platforms]
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage(self.description, 3500)

    def undo(self):
        if not self.trial:
            return
        self.trial.force_platforms = [fp.clone() for fp in self.old_platforms]
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage("Undid force plate configuration, restored previous forces", 3500)

    def _refresh(self):
        if not self.mw:
            return
        cur_frame = getattr(self.mw.playback, "current_frame", 0) if hasattr(self.mw, "playback") else 0
        if hasattr(self.mw, "viewer_3d") and self.mw.viewer_3d:
            self.mw.viewer_3d._rebuild_force_plates()
            self.mw.viewer_3d.set_frame(cur_frame)
        if hasattr(self.mw, "side_panel") and self.mw.side_panel:
            self.mw.side_panel._populate_force_plates()
            self.mw.side_panel.update_live_values(cur_frame)
        if hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_force_plates"):
                self.mw.plotter_widget.refresh_force_plates()
            elif hasattr(self.mw.plotter_widget, "update_data"):
                self.mw.plotter_widget.update_data()
            else:
                self.mw.plotter_widget.load_trial(self.trial)
        if hasattr(self.mw, "_update_status_stats"):
            self.mw._update_status_stats()


class UpdateAnalogSpecificationsCommand(QUndoCommand):
    """Command to update analog global parameters (GEN_SCALE, RATE) and channel specifications (SCALE, OFFSET, UNITS)."""

    def __init__(
        self,
        main_window,
        trial: C3DTrial,
        old_analogs: Dict[str, np.ndarray],
        new_analogs: Dict[str, np.ndarray],
        old_units: Dict[str, str],
        new_units: Dict[str, str],
        old_meta: Dict[str, Any],
        new_meta: Dict[str, Any],
        old_rate: float,
        new_rate: float,
        old_subsamples: int,
        new_subsamples: int,
        old_force_platforms: Optional[List[Any]] = None,
        new_force_platforms: Optional[List[Any]] = None,
        analog_dialog: Optional[Any] = None,
        description: str = "Update Analog Specifications"
    ):
        super().__init__(description)
        self.mw = main_window
        self.trial = trial
        self.old_analogs = {k: v.copy() for k, v in old_analogs.items()}
        self.new_analogs = {k: v.copy() for k, v in new_analogs.items()}
        self.old_units = dict(old_units)
        self.new_units = dict(new_units)
        self.old_meta = copy.deepcopy(old_meta) if old_meta else {}
        self.new_meta = copy.deepcopy(new_meta) if new_meta else {}
        self.old_rate = float(old_rate)
        self.new_rate = float(new_rate)
        self.old_subsamples = int(old_subsamples)
        self.new_subsamples = int(new_subsamples)
        self.old_fp = [fp.clone() for fp in old_force_platforms] if old_force_platforms else []
        self.new_fp = [fp.clone() for fp in new_force_platforms] if new_force_platforms else []
        self.analog_dialog = analog_dialog

    def redo(self):
        if not self.trial:
            return
        self.trial.analogs = {k: v.copy() for k, v in self.new_analogs.items()}
        self.trial.analog_units = dict(self.new_units)
        self.trial.analog_rate = self.new_rate
        self.trial.analog_subsamples = self.new_subsamples
        if "ANALOG" in self.trial.metadata:
            self.trial.metadata["ANALOG"] = copy.deepcopy(self.new_meta)
        if self.new_fp:
            self.trial.force_platforms = [fp.clone() for fp in self.new_fp]
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage("Applied updated analog specifications", 3500)

    def undo(self):
        if not self.trial:
            return
        self.trial.analogs = {k: v.copy() for k, v in self.old_analogs.items()}
        self.trial.analog_units = dict(self.old_units)
        self.trial.analog_rate = self.old_rate
        self.trial.analog_subsamples = self.old_subsamples
        if "ANALOG" in self.trial.metadata:
            self.trial.metadata["ANALOG"] = copy.deepcopy(self.old_meta)
        if self.old_fp:
            self.trial.force_platforms = [fp.clone() for fp in self.old_fp]
        self._refresh()
        if self.mw and hasattr(self.mw, "status"):
            self.mw.status.showMessage("Undid analog specifications update", 3500)

    def _refresh(self):
        cur_frame = getattr(self.mw.playback, "current_frame", 0) if (self.mw and hasattr(self.mw, "playback")) else 0
        dlg = self.analog_dialog or (getattr(self.mw, "analog_dialog", None) if self.mw else None)
        if dlg:
            if hasattr(dlg, "_populate_channel_table"):
                dlg._populate_channel_table()
            if hasattr(dlg, "_populate_filter_channels"):
                dlg._populate_filter_channels()
            if hasattr(dlg, "_populate_info_tab"):
                dlg._populate_info_tab()
            if hasattr(dlg, "_update_footer_info"):
                dlg._update_footer_info()
            if hasattr(dlg, "_update_undo_redo_actions"):
                dlg._update_undo_redo_actions()
        if self.mw and hasattr(self.mw, "plotter_widget") and self.mw.plotter_widget:
            if hasattr(self.mw.plotter_widget, "refresh_analogs"):
                self.mw.plotter_widget.refresh_analogs()
            else:
                self.mw.plotter_widget.load_trial(self.trial)
        if self.mw and hasattr(self.mw, "viewer_3d") and self.mw.viewer_3d:
            self.mw.viewer_3d._rebuild_force_plates()
            self.mw.viewer_3d.set_frame(cur_frame)
        if self.mw and hasattr(self.mw, "side_panel") and self.mw.side_panel:
            self.mw.side_panel._populate_force_plates()
            self.mw.side_panel.update_live_values(cur_frame)
        if self.mw and hasattr(self.mw, "_update_status_stats"):
            self.mw._update_status_stats()




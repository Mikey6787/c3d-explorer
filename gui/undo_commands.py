"""Undo/Redo command classes for C3D Explorer using QUndoCommand."""

from typing import Optional, List, Dict, Any
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

    def __init__(self, main_window, trial: C3DTrial, name: str, data: np.ndarray, color_rgba: Optional[tuple] = None):
        super().__init__(f"Add Marker '{name}'")
        self.mw = main_window
        self.trial = trial
        self.name = name
        self.data = data
        self.color_rgba = color_rgba

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

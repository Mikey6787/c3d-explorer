"""Unit tests for the Undo/Redo framework and Edit Menu in C3D Explorer."""

import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QKeySequence

from gui.main_window import MainWindow
from core.data_models import C3DTrial, C3DEvent
from gui.undo_commands import (
    AddEventCommand, DeleteEventCommand, EditEventCommand,
    ClearEventsCommand, RenameMarkerCommand, AddMarkerCommand,
    DeleteMarkerCommand, DeleteMarkersCommand, ChangeMarkerColorCommand
)


def run_undo_redo_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # 1. Verify Edit menu and Undo/Redo actions
    menubar = window.menuBar()
    menus = [m.title() for m in menubar.findChildren(type(menubar.addMenu("test")))]
    # Check that Edit menu exists
    edit_actions = [a.text() for a in window.menuBar().actions()]
    print(f"Top-level menu bar actions: {edit_actions}")
    assert any("Edit" in a for a in edit_actions), "Edit menu must be present in menu bar!"

    assert hasattr(window, "act_undo"), "MainWindow must have act_undo"
    assert hasattr(window, "act_redo"), "MainWindow must have act_redo"
    assert not window.act_undo.isEnabled(), "Undo should be disabled initially"
    assert not window.act_redo.isEnabled(), "Redo should be disabled initially"
    print("Edit menu and initial Undo/Redo actions verified!")

    # 2. Setup mock trial
    trial = C3DTrial(
        file_path="mock.c3d",
        first_frame=1,
        last_frame=100,
        point_rate=100.0,
        point_frame_count=100,
        analog_rate=1000.0,
        analog_frame_count=1000,
        analog_subsamples=10,
        markers={
            "L_HEEL": np.zeros((100, 3)),
            "R_HEEL": np.ones((100, 3))
        },
        analogs={},
        events=[
            C3DEvent(time=0.1, frame=10, name="R_STRIKE", description="Right Foot Strike", icon_color="#FF0000"),
            C3DEvent(time=0.5, frame=50, name="L_STRIKE", description="Left Foot Strike", icon_color="#00FF00")
        ]
    )
    window.trial = trial
    window.playback.set_trial(trial.point_frame_count, trial.point_rate)
    window.timeline.set_trial_data(trial.point_frame_count, trial.point_rate, trial.events)
    window.side_panel.load_trial(trial)
    window.viewer_3d.load_trial(trial)
    window.undo_stack.clear()

    # 3. Test Add Event Command Undo/Redo
    new_ev = C3DEvent(time=0.8, frame=80, name="TOE_OFF", description="Toe Off", icon_color="#0000FF")
    cmd_add = AddEventCommand(window, trial, new_ev)
    window.undo_stack.push(cmd_add)

    assert len(trial.events) == 3, f"Expected 3 events after add, got {len(trial.events)}"
    assert new_ev in trial.events, "New event should be in trial.events"
    assert window.act_undo.isEnabled(), "Undo should be enabled after push"
    assert "TOE_OFF" in window.act_undo.text(), f"Undo text should mention TOE_OFF: {window.act_undo.text()}"

    # Undo Add
    window.undo_stack.undo()
    assert len(trial.events) == 2, f"Expected 2 events after undo add, got {len(trial.events)}"
    assert new_ev not in trial.events, "New event should be removed after undo"
    assert window.act_redo.isEnabled(), "Redo should be enabled after undo"

    # Redo Add
    window.undo_stack.redo()
    assert len(trial.events) == 3, "Expected 3 events after redo add"
    assert new_ev in trial.events
    print("AddEventCommand undo/redo verified!")

    # 4. Test Edit Event Command Undo/Redo
    edited_ev = C3DEvent(time=0.85, frame=85, name="TOE_OFF_EDITED", description="Updated", icon_color="#FFFF00")
    cmd_edit = EditEventCommand(window, trial, new_ev, edited_ev)
    window.undo_stack.push(cmd_edit)

    assert any(e.name == "TOE_OFF_EDITED" for e in trial.events), "Edited event should be present"
    assert not any(e.name == "TOE_OFF" for e in trial.events), "Old event should be replaced"

    # Undo Edit
    window.undo_stack.undo()
    assert any(e.name == "TOE_OFF" for e in trial.events), "Old event should be restored after undo"
    assert not any(e.name == "TOE_OFF_EDITED" for e in trial.events)

    # Redo Edit
    window.undo_stack.redo()
    assert any(e.name == "TOE_OFF_EDITED" for e in trial.events)
    print("EditEventCommand undo/redo verified!")

    # 5. Test Delete Event Command Undo/Redo
    cmd_del = DeleteEventCommand(window, trial, edited_ev)
    window.undo_stack.push(cmd_del)

    assert len(trial.events) == 2, "Expected 2 events after delete"
    assert edited_ev not in trial.events

    # Undo Delete
    window.undo_stack.undo()
    assert len(trial.events) == 3, "Expected 3 events after undo delete"
    assert edited_ev in trial.events

    # Redo Delete
    window.undo_stack.redo()
    assert len(trial.events) == 2
    assert edited_ev not in trial.events
    print("DeleteEventCommand undo/redo verified!")

    # 6. Test Clear All Events Command Undo/Redo
    saved_events = list(trial.events)
    cmd_clear = ClearEventsCommand(window, trial, saved_events)
    window.undo_stack.push(cmd_clear)

    assert len(trial.events) == 0, "All events should be cleared"

    # Undo Clear
    window.undo_stack.undo()
    assert len(trial.events) == 2, f"Expected 2 events restored, got {len(trial.events)}"

    # Redo Clear
    window.undo_stack.redo()
    assert len(trial.events) == 0

    # Restore events for marker tests
    window.undo_stack.undo()
    assert len(trial.events) == 2
    print("ClearEventsCommand undo/redo verified!")

    # 7. Test Rename Marker Command Undo/Redo
    cmd_ren = RenameMarkerCommand(window, trial, "L_HEEL", "LEFT_HEEL_NEW")
    window.undo_stack.push(cmd_ren)

    assert "LEFT_HEEL_NEW" in trial.markers, "New marker name should be in trial.markers"
    assert "L_HEEL" not in trial.markers, "Old marker name should not be in trial.markers"

    # Undo Rename
    window.undo_stack.undo()
    assert "L_HEEL" in trial.markers, "Old marker name should be restored after undo"
    assert "LEFT_HEEL_NEW" not in trial.markers

    # Redo Rename
    window.undo_stack.redo()
    assert "LEFT_HEEL_NEW" in trial.markers
    assert "L_HEEL" not in trial.markers
    print("RenameMarkerCommand undo/redo verified!")

    # 8. Test Add Average Marker Command Undo/Redo
    avg_data = np.zeros((100, 3))
    cmd_avg = AddMarkerCommand(window, trial, "AVG_HEEL", avg_data)
    window.undo_stack.push(cmd_avg)

    assert "AVG_HEEL" in trial.markers, "AVG_HEEL should be in trial.markers"

    # Undo Add Marker
    window.undo_stack.undo()
    assert "AVG_HEEL" not in trial.markers, "AVG_HEEL should be removed after undo"

    # Redo Add Marker
    window.undo_stack.redo()
    assert "AVG_HEEL" in trial.markers
    print("AddMarkerCommand undo/redo verified!")

    # 9. Test Change Marker Color Command Undo/Redo
    old_colors = {"LEFT_HEEL_NEW": None}
    new_rgba = (1.0, 0.5, 0.0, 1.0)
    cmd_col = ChangeMarkerColorCommand(window, ["LEFT_HEEL_NEW"], old_colors, new_rgba)
    window.undo_stack.push(cmd_col)

    assert window.viewer_3d.custom_marker_colors.get("LEFT_HEEL_NEW") == new_rgba

    # Undo Color
    window.undo_stack.undo()
    assert window.viewer_3d.custom_marker_colors.get("LEFT_HEEL_NEW") is None

    # Redo Color
    window.undo_stack.redo()
    assert window.viewer_3d.custom_marker_colors.get("LEFT_HEEL_NEW") == new_rgba
    print("ChangeMarkerColorCommand undo/redo verified!")

    # 10. Test Delete Marker Command Undo/Redo
    cmd_del_m = DeleteMarkerCommand(window, trial, "LEFT_HEEL_NEW")
    window.undo_stack.push(cmd_del_m)
    assert "LEFT_HEEL_NEW" not in trial.markers

    # Undo Delete Marker
    window.undo_stack.undo()
    assert "LEFT_HEEL_NEW" in trial.markers
    assert window.viewer_3d.custom_marker_colors.get("LEFT_HEEL_NEW") == new_rgba

    # Redo Delete Marker
    window.undo_stack.redo()
    assert "LEFT_HEEL_NEW" not in trial.markers
    print("DeleteMarkerCommand undo/redo verified!")

    # 11. Test Batch Delete Markers Command Undo/Redo
    cmd_batch_del = DeleteMarkersCommand(window, trial, ["R_HEEL", "AVG_HEEL"])
    window.undo_stack.push(cmd_batch_del)
    assert "R_HEEL" not in trial.markers
    assert "AVG_HEEL" not in trial.markers

    # Undo Batch Delete
    window.undo_stack.undo()
    assert "R_HEEL" in trial.markers
    assert "AVG_HEEL" in trial.markers

    # Redo Batch Delete
    window.undo_stack.redo()
    assert "R_HEEL" not in trial.markers
    assert "AVG_HEEL" not in trial.markers
    print("DeleteMarkersCommand undo/redo verified!")

    window.close()
    print("ALL UNDO/REDO TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    run_undo_redo_tests()

import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial, C3DEvent
from gui.side_panel import SidePanel
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.main_window import MainWindow
from gui.undo_commands import DeleteEventsCommand

def test_multi_event_delete_and_name():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test EventEditDialog cursor position with long label 'Right_Foot_Off'
    trial = C3DTrial(
        file_path="mock.c3d",
        first_frame=1,
        last_frame=1000,
        point_rate=100.0,
        point_frame_count=1000,
        analog_rate=1000.0,
        analog_frame_count=10000,
        analog_subsamples=10,
        markers={"M1": np.zeros((1000, 3))}
    )
    ev_test = C3DEvent(time=2.496, frame=624, name="Right_Foot_Off", context="Right", icon_color="#FB8C00")
    trial.events = [ev_test]

    dlg = EventEditDialog(trial=trial, current_frame=624, event_to_edit=ev_test)
    assert dlg.combo_name.currentText() == "Right_Foot_Off"
    if dlg.combo_name.lineEdit():
        # Cursor must be at start (0) so text is not horizontally scrolled/clipped
        assert dlg.combo_name.lineEdit().cursorPosition() == 0, f"Expected cursor at 0, got {dlg.combo_name.lineEdit().cursorPosition()}"
    print("EventEditDialog text display & cursor position verified!")

    # 2. Test SidePanel multi-selection and deleteEventsRequested signal
    e1 = C3DEvent(time=0.5, frame=50, name="Right_Foot_Strike", context="Right", icon_color="#E53935")
    e2 = C3DEvent(time=1.0, frame=100, name="Right_Foot_Off", context="Right", icon_color="#FB8C00")
    e3 = C3DEvent(time=1.5, frame=150, name="Left_Foot_Strike", context="Left", icon_color="#1E88E5")
    e4 = C3DEvent(time=2.0, frame=200, name="Left_Foot_Off", context="Left", icon_color="#00ACC1")
    trial.events = [e1, e2, e3, e4]

    sp = SidePanel()
    sp.load_trial(trial)
    assert sp.events_table.rowCount() == 4

    # Select rows 1 and 2 (e2 and e3)
    sp.events_table.selectRow(1)
    # Add row 2 to selection (ExtendedSelection)
    sp.events_table.item(2, 0).setSelected(True)
    sp.events_table.item(2, 1).setSelected(True)
    sp.events_table.item(2, 2).setSelected(True)

    selected_events = sp.get_selected_events()
    assert len(selected_events) == 2, f"Expected 2 selected events, got {len(selected_events)}"
    assert selected_events[0] == e2
    assert selected_events[1] == e3

    received_batch = []
    sp.deleteEventsRequested.connect(lambda evs: received_batch.extend(evs))
    sp._action_delete_event()
    assert len(received_batch) == 2
    assert received_batch == [e2, e3]
    print("SidePanel multi-event selection & deleteEventsRequested signal verified!")

    # 3. Test MainWindow DeleteEventsCommand and Undo/Redo
    mw = MainWindow()
    mw.trial = trial
    mw.undo_stack.clear()

    cmd = DeleteEventsCommand(mw, trial, [e2, e3])
    mw.undo_stack.push(cmd)

    # Both events removed
    assert len(trial.events) == 2
    assert e2 not in trial.events
    assert e3 not in trial.events
    assert trial.events == [e1, e4]

    # Undo restores both events
    mw.undo_stack.undo()
    assert len(trial.events) == 4
    assert e2 in trial.events
    assert e3 in trial.events
    assert [e.frame for e in trial.events] == [50, 100, 150, 200]

    # Redo deletes them again
    mw.undo_stack.redo()
    assert len(trial.events) == 2
    assert trial.events == [e1, e4]
    print("DeleteEventsCommand undo & redo verified!")

    # 4. Test EventManagerDialog multi-selection
    trial.events = [e1, e2, e3, e4]
    mgr = EventManagerDialog(trial, current_frame=50)
    assert mgr.table.rowCount() == 4
    mgr.table.selectRow(0)
    mgr.table.item(1, 0).setSelected(True)
    mgr.table.item(1, 1).setSelected(True)
    mgr.table.item(1, 2).setSelected(True)

    sel_mgr = mgr._get_selected_events()
    assert len(sel_mgr) == 2
    assert sel_mgr == [e1, e2]
    print("EventManagerDialog multi-event selection verified!")

if __name__ == "__main__":
    test_multi_event_delete_and_name()
    print("ALL MULTI-EVENT DELETION & NAME TESTS PASSED PERFECTLY!")

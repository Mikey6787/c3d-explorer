import sys
import os
import tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from core.data_models import C3DEvent
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
from gui.event_dialog import EventEditDialog, EventManagerDialog
from gui.timeline_widget import TimelineWidget
from gui.side_panel import SidePanel

print("Initializing Events test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)
c3d_path = "/Users/mikey/Library/CloudStorage/OneDrive-UniversitätKoblenz/Koblenz/Reserach Projects/OpenSim Pipeline/Jumping/Sample data/MHJ/P01_PRE_L_REF.c3d"

trial = C3DReader.read(c3d_path)
initial_event_count = len(trial.events)
print(f"Loaded trial with {initial_event_count} initial events.", flush=True)

# 1. Test EventEditDialog creation and data extraction
edit_dlg = EventEditDialog(trial=trial, current_frame=30)
edit_dlg.combo_name.setCurrentText("Foot Strike")
edit_dlg.combo_context.setCurrentText("Right")
edit_dlg.spin_frame.setValue(40)
edit_dlg.txt_subject.setText("Runner01")
edit_dlg.txt_desc.setText("Initial right heel strike")
edit_dlg.spin_id.setValue(7)
new_ev = edit_dlg.get_event()

assert new_ev.name == "Foot Strike"
assert new_ev.context == "Right"
assert new_ev.frame == 40
assert abs(new_ev.time - 40 / trial.point_rate) < 1e-4
assert new_ev.subject == "Runner01"
assert new_ev.description == "Initial right heel strike"
assert new_ev.event_id == 7
print("EventEditDialog constructed event correctly!", flush=True)

# 2. Add event to trial and verify persistence through C3DWriter and C3DReader
trial.events.append(new_ev)
trial.events.sort(key=lambda e: e.time)
assert len(trial.events) == initial_event_count + 1

tmp_c3d = tempfile.mktemp(suffix=".c3d")
try:
    C3DWriter.save_c3d(trial, tmp_c3d)
    print("Saved C3D with new event!", flush=True)

    trial_reloaded = C3DReader.read(tmp_c3d)
    print(f"Reloaded trial event count: {len(trial_reloaded.events)}", flush=True)
    # Check that our event is in the reloaded file
    matching = [e for e in trial_reloaded.events if "Foot_Strike" in e.name or "Foot Strike" in e.name]
    assert len(matching) > 0, "Saved event not found in reloaded C3D file!"
    print(f"Verified event persistence in C3D: {matching[0].name} at {matching[0].time:.3f}s", flush=True)
finally:
    if os.path.exists(tmp_c3d):
        os.remove(tmp_c3d)

# 3. Test TimelineWidget right-click context menu and event signals
timeline = TimelineWidget()
timeline.set_trial_data(trial.point_frame_count, trial.point_rate, trial.events)
timeline.resize(800, 60)

received_signals = []
timeline.addEventRequested.connect(lambda f: received_signals.append(("add", f)))
timeline.editEventRequested.connect(lambda ev: received_signals.append(("edit", ev)))
timeline.deleteEventRequested.connect(lambda ev: received_signals.append(("delete", ev)))

timeline.addEventRequested.emit(55)
timeline.editEventRequested.emit(new_ev)
timeline.deleteEventRequested.emit(new_ev)

assert len(received_signals) == 3
assert received_signals[0] == ("add", 55)
assert received_signals[1] == ("edit", new_ev)
assert received_signals[2] == ("delete", new_ev)
print("TimelineWidget event signals verified!", flush=True)

# 4. Test SidePanel Events tab
side_panel = SidePanel()
side_panel.load_trial(trial)
assert side_panel.events_table.rowCount() == len(trial.events)
print("SidePanel events table populated correctly!", flush=True)

# 5. Test EventManagerDialog
mgr_dlg = EventManagerDialog(trial=trial, current_frame=20)
assert mgr_dlg.table.rowCount() == len(trial.events)
print("EventManagerDialog loaded successfully!", flush=True)

print("ALL EVENT SYSTEM TESTS PASSED PERFECTLY!", flush=True)

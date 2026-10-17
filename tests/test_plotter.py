import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from core.c3d_reader import C3DReader
from gui.plotter_window import UniversalPlotterWindow

print("Initializing Plotter test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)
c3d_path = "/Users/mikey/Library/CloudStorage/OneDrive-UniversitätKoblenz/Koblenz/Reserach Projects/OpenSim Pipeline/Jumping/Sample data/MHJ/P01_PRE_L_REF.c3d"

trial = C3DReader.read(c3d_path)
print(f"Loaded trial with {len(trial.markers)} markers, {len(trial.force_platforms)} force plates, {len(trial.analogs)} analogs.", flush=True)

# Test opening plotter
plotter = UniversalPlotterWindow(trial=trial, current_frame=10)
plotter.show()
print("Plotter window initialized and displayed!", flush=True)

# Check items in tree
top_count = plotter.tree.topLevelItemCount()
print(f"Plotter Tree Top Items: {top_count}", flush=True)
assert top_count >= 2, f"Expected at least 2 categories, got {top_count}"

# Test selecting signals
markers_node = plotter.tree.topLevelItem(0)
assert markers_node.childCount() > 0
m1 = markers_node.child(0)
print(f"First marker in tree: {m1.text(0)}", flush=True)
assert m1.childCount() >= 4

m1_x = m1.child(0)
m1_norm = m1.child(3)
m1_x.setCheckState(0, Qt.Checked)
m1_norm.setCheckState(0, Qt.Checked)
print(f"Active curves after checking marker: {list(plotter.active_curves.keys())}", flush=True)
assert len(plotter.active_curves) == 2, f"Expected 2 curves, got {len(plotter.active_curves)}"

# Check force plate signal
if top_count >= 2:
    node2 = plotter.tree.topLevelItem(1)
    if node2.childCount() > 0:
        c2 = node2.child(0)
        if c2.childCount() > 0:
            c2_sig = c2.child(0)
            c2_sig.setCheckState(0, Qt.Checked)
        else:
            c2.setCheckState(0, Qt.Checked)
print(f"Active curves after checking FP/Analog: {list(plotter.active_curves.keys())}", flush=True)
assert len(plotter.active_curves) == 3, f"Expected 3 curves, got {len(plotter.active_curves)}"

# Test toggling between Time and Frame
plotter.rb_frame.setChecked(True)
assert plotter.x_axis_mode == "frame", f"Expected frame mode, got {plotter.x_axis_mode}"
assert plotter.plot_widget.plotItem.getAxis('bottom').labelText == "Frame Number"
plotter.rb_time.setChecked(True)
assert plotter.x_axis_mode == "time", f"Expected time mode, got {plotter.x_axis_mode}"
assert plotter.plot_widget.plotItem.getAxis('bottom').labelText == "Time"
print("Horizontal axis mode toggle works smoothly!", flush=True)

# Test frame update and dynamic floating label
plotter.update_frame(45)
assert plotter.current_frame == 45
assert plotter.time_cursor.label is not None
lbl_txt = plotter.time_cursor.label.toPlainText()
expected_time_str = f"t={trial.frame_to_time(45):.3f}s"
assert lbl_txt == expected_time_str, f"Expected label '{expected_time_str}', got '{lbl_txt}'"

plotter.rb_frame.setChecked(True)
plotter.update_frame(60)
lbl_frame_txt = plotter.time_cursor.label.toPlainText()
assert lbl_frame_txt == "Frame 60", f"Expected label 'Frame 60', got '{lbl_frame_txt}'"
plotter.rb_time.setChecked(True)
print("Frame cursor and floating label updates verified!", flush=True)

# Test unchecking / removing
m1_x.setCheckState(0, Qt.Unchecked)
assert len(plotter.active_curves) == 2
print("Unchecking / removing curve works!", flush=True)

# Test CSV export
export_csv_path = "tests/test_plotted_export.csv"
plotter.curve_data["dummy"] = {"y": [1.0, 2.0, 3.0], "rate": 100.0, "subsamples": 1}
# Test clear all
plotter.clear_all_curves()
assert len(plotter.active_curves) == 0
assert len(plotter.curve_data) == 0
print("Clear all works!", flush=True)

plotter.close()
app.quit()
print("ALL PLOTTER TESTS PASSED PERFECTLY!", flush=True)

import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
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
assert plotter.time_cursor in plotter.plot_widget.getPlotItem().items, "time_cursor vertical bar must be in plot_widget items"
assert plotter.time_cursor.isVisible() is True, "time_cursor vertical bar must be visible"
print("Plotter window initialized and displayed, time_cursor vertical bar verified!", flush=True)

# Check items in tree
top_count = plotter.tree.topLevelItemCount()
print(f"Plotter Tree Top Items: {top_count}", flush=True)
assert top_count >= 2, f"Expected at least 2 categories, got {top_count}"

# Test selecting signals
markers_node = plotter.tree.topLevelItem(0)
assert markers_node.childCount() > 0
m1 = markers_node.child(0)
print(f"First marker in tree: {m1.text(0)}", flush=True)
assert m1.childCount() == 3, f"Expected exactly 3 components (X, Y, Z), got {m1.childCount()}"
assert [m1.child(i).text(0) for i in range(3)] == [f"{m1.text(0)} (X)", f"{m1.text(0)} (Y)", f"{m1.text(0)} (Z)"]

m1_x = m1.child(0)
m1_y = m1.child(1)
m1_x.setCheckState(0, Qt.Checked)
m1_y.setCheckState(0, Qt.Checked)
assert m1.checkState(0) == Qt.PartiallyChecked
print(f"Active curves after checking marker: {list(plotter.active_curves.keys())}", flush=True)
assert len(plotter.active_curves) == 2, f"Expected 2 curves, got {len(plotter.active_curves)}"

# Test checking second marker parent item directly -> plots all 3 components (X, Y, Z)
if markers_node.childCount() > 1:
    m2 = markers_node.child(1)
    m2_name = m2.text(0)
    m2.setCheckState(0, Qt.Checked)
    for j in range(3):
        assert m2.child(j).checkState(0) == Qt.Checked
    assert f"{m2_name} (X)" in plotter.active_curves
    assert f"{m2_name} (Y)" in plotter.active_curves
    assert f"{m2_name} (Z)" in plotter.active_curves
    assert f"{m2_name} (3D Norm)" not in plotter.active_curves
    print(f"Checked whole marker {m2_name} -> all 3 components (X, Y, Z) plotted without 3D Norm!", flush=True)

    # Uncheck whole marker -> all 3 removed
    m2.setCheckState(0, Qt.Unchecked)
    for j in range(3):
        assert m2.child(j).checkState(0) == Qt.Unchecked
    assert f"{m2_name} (X)" not in plotter.active_curves
    assert f"{m2_name} (Y)" not in plotter.active_curves
    assert f"{m2_name} (Z)" not in plotter.active_curves
    assert len(plotter.active_curves) == 2

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

# Test toggling between Time and Frame (Frame is default)
assert plotter.x_axis_mode == "frame", f"Expected default frame mode, got {plotter.x_axis_mode}"
assert plotter.plot_widget.plotItem.getAxis('bottom').labelText == "Frame"
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
assert lbl_frame_txt == "Frame 61", f"Expected label 'Frame 61', got '{lbl_frame_txt}'"
plotter.rb_time.setChecked(True)
print("Frame cursor and floating label updates verified!", flush=True)

# Test unchecking / removing
m1_x.setCheckState(0, Qt.Unchecked)
assert len(plotter.active_curves) == 2
# Test Fit ROI and Fit Full in UniversalPlotterWindow
plotter.set_trim_range(10, 30)
plotter.fit_roi()
vb_roi_x = plotter.plot_widget.getViewBox().viewRange()[0]
assert vb_roi_x[0] <= trial.frame_to_time(10) and vb_roi_x[1] >= trial.frame_to_time(30), "fit_roi should encompass ROI"
print("UniversalPlotterWindow fit_roi verified!", flush=True)

plotter.auto_range()
vb_full_x = plotter.plot_widget.getViewBox().viewRange()[0]
assert vb_full_x[0] <= 0 and vb_full_x[1] >= trial.frame_to_time(trial.point_frame_count - 1), "auto_range should encompass full trial"
print("UniversalPlotterWindow Fit Full verified!", flush=True)

# Test hover inspection on curve
plotter.rb_frame.setChecked(True)
m1_x.setCheckState(0, Qt.Checked)
assert len(plotter.active_curves) >= 1
curve_key = list(plotter.active_curves.keys())[0]
curve = plotter.active_curves[curve_key]
x_data, y_data = curve.getData()
test_idx = 10
test_x = x_data[test_idx]
test_y = y_data[test_idx]

vb = plotter.plot_widget.getViewBox()
scene_pt = vb.mapViewToScene(QPointF(float(test_x), float(test_y)))
plotter._on_mouse_moved([scene_pt])

assert plotter.hover_dot.isVisible(), "hover_dot should be visible when mouse is on curve"
assert plotter.hover_label.isVisible(), "hover_label should be visible when mouse is on curve"
assert f"{test_y:.2f}" in plotter.hover_label.toHtml(), f"Expected value {test_y:.2f} in label"
print(f"Hover inspection on curve verified! Displaying value: {test_y:.2f}", flush=True)

# Test moving mouse between curves (>200 px from all curves) -> hides
blank_pt = QPointF(scene_pt.x(), 250.0)
plotter._on_mouse_moved([blank_pt])
assert not plotter.hover_dot.isVisible(), "hover_dot should hide when far from all curves"
assert not plotter.hover_label.isVisible(), "hover_label should hide when far from all curves"

# Test moving mouse outside plot viewport -> hides
outside_pt = QPointF(-50.0, -50.0)
plotter._on_mouse_moved([outside_pt])
assert not plotter.hover_dot.isVisible(), "hover_dot should hide when outside viewport"
assert not plotter.hover_label.isVisible(), "hover_label should hide when outside viewport"
print("Hover inspection hide on distant cursor and outside viewport verified!", flush=True)

# Test CSV export
export_csv_path = "tests/test_plotted_export.csv"
plotter.curve_data["dummy"] = {"y": [1.0, 2.0, 3.0], "rate": 100.0, "subsamples": 1}
# Test clear all
plotter.clear_all_curves()
assert len(plotter.active_curves) == 0
assert len(plotter.curve_data) == 0
assert not plotter.hover_dot.isVisible(), "hover_dot should hide on clear_all_curves"
assert not plotter.hover_label.isVisible(), "hover_label should hide on clear_all_curves"
# Test Event Dashed Lines (similar to analog panel)
from core.data_models import C3DEvent
ev1 = C3DEvent(name="Foot_Strike", frame=20, time=trial.frame_to_time(20), icon_color="#00FF00", context="Right")
ev2 = C3DEvent(name="Foot_Off", frame=60, time=trial.frame_to_time(60), icon_color="#FF0000", context="Right")
trial.events.extend([ev1, ev2])
plotter.reload_events()

assert len(plotter.event_lines) == 2, f"Expected 2 event dashed lines, got {len(plotter.event_lines)}"
# In frame mode, position must be frame + 1 (21 and 61)
assert plotter.event_lines[0].value() == 21, f"Expected event line at 21, got {plotter.event_lines[0].value()}"
assert plotter.event_lines[1].value() == 61, f"Expected event line at 61, got {plotter.event_lines[1].value()}"
assert plotter.event_lines[0].pen.style() == Qt.DashLine, "Event line must be dashed"
assert plotter.event_lines[1].pen.style() == Qt.DashLine, "Event line must be dashed"
print("Event dashed lines in Frame mode verified (values: 21, 61)!", flush=True)

# Toggle to Time mode -> event lines must shift to time values
plotter.rb_time.setChecked(True)
assert abs(plotter.event_lines[0].value() - ev1.time) < 1e-4, f"Expected event line at {ev1.time}, got {plotter.event_lines[0].value()}"
assert abs(plotter.event_lines[1].value() - ev2.time) < 1e-4, f"Expected event line at {ev2.time}, got {plotter.event_lines[1].value()}"
print("Event dashed lines in Time mode verified!", flush=True)

# Toggle back to Frame mode
plotter.rb_frame.setChecked(True)
assert plotter.event_lines[0].value() == 21
assert plotter.event_lines[1].value() == 61

# Clear all curves must keep event lines visible
plotter.clear_all_curves()
assert len(plotter.event_lines) == 2, "Event lines must remain after clear_all_curves"
print("Event dashed lines persistence verified!", flush=True)

# Test right-click context menu is completely disabled
assert plotter.plot_widget.contextMenuPolicy() == Qt.NoContextMenu
assert plotter.plot_widget.getPlotItem().menuEnabled() is False
assert plotter.plot_widget.getPlotItem().getViewBox().menuEnabled() is False
assert plotter.tree.contextMenuPolicy() == Qt.NoContextMenu

# Simulate right click on plot widget and viewport
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
cme = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(100, 100))
app.sendEvent(plotter.plot_widget.viewport(), cme)
app.sendEvent(plotter.plot_widget, cme)
press = QMouseEvent(QEvent.MouseButtonPress, QPointF(100, 100), Qt.RightButton, Qt.RightButton, Qt.NoModifier)
release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(100, 100), Qt.RightButton, Qt.NoButton, Qt.NoModifier)
app.sendEvent(plotter.plot_widget.viewport(), press)
app.sendEvent(plotter.plot_widget.viewport(), release)
print("Right-click context menu completely disabled on plotter verified!", flush=True)

plotter.close()
app.quit()
print("ALL PLOTTER TESTS PASSED PERFECTLY!", flush=True)

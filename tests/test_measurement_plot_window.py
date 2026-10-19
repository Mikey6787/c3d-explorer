import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication, QPushButton
from app import MainWindow
from core.data_models import C3DTrial
from gui.marker_tools_dialog import MeasureDistanceDialog, MeasureAngleDialog
from gui.measurement_plot_window import MeasurementPlotWindow

print("Initializing Measurement Plot Window test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# Create a mock trial with 2 markers
n_frames = 200
rate = 100.0
m1_data = np.zeros((n_frames, 3))
m1_data[:, 0] = np.linspace(0, 100, n_frames)
m2_data = np.zeros((n_frames, 3))
m2_data[:, 0] = np.linspace(300, 450, n_frames)

trial = C3DTrial(
    file_path="mock.c3d",
    first_frame=1,
    last_frame=n_frames,
    point_rate=rate,
    point_frame_count=n_frames,
    analog_rate=1000.0,
    analog_frame_count=n_frames * 10,
    analog_subsamples=10,
    markers={"L_ACR": m1_data, "R_ACR": m2_data, "V_ACR": m1_data + 50.0},
    analogs={},
    force_platforms=[],
    events=[]
)

# 1. Test MeasureDistanceDialog
dist_dlg = MeasureDistanceDialog(trial, current_frame=50, preselected=["L_ACR", "R_ACR"])
plot_buttons = [b for b in dist_dlg.findChildren(QPushButton) if b.text() == "Plot"]
assert len(plot_buttons) == 1, f"Expected button with text 'Plot', found {[b.text() for b in dist_dlg.findChildren(QPushButton)]}"
btn_plot = plot_buttons[0]
print("Verified MeasureDistanceDialog has 'Plot' button.")

# Test clicking 'Plot'
opened_windows = []
dist_dlg.openPlotWindowRequested.connect(lambda title, data, unit, ctype: opened_windows.append((title, data, unit, ctype)))
btn_plot.click()

assert len(opened_windows) == 1
title, data, unit, ctype = opened_windows[0]
assert "Distance: L_ACR ↔ R_ACR" in title
assert len(data) == n_frames
assert unit == "mm"
assert ctype == "Distance"
print("Verified MeasureDistanceDialog clicking 'Plot' emits openPlotWindowRequested immediately without blocking.")

# 2. Test MeasureAngleDialog
angle_dlg = MeasureAngleDialog(trial, current_frame=50, preselected=["L_ACR", "R_ACR", "V_ACR"])
angle_plot_btns = [b for b in angle_dlg.findChildren(QPushButton) if b.text() == "Plot"]
assert len(angle_plot_btns) == 1, f"Expected angle button 'Plot', found {[b.text() for b in angle_dlg.findChildren(QPushButton)]}"
print("Verified MeasureAngleDialog has 'Plot' button.")

# 3. Test MeasurementPlotWindow functionality
win = MeasurementPlotWindow(
    title="Distance: L_ACR ↔ R_ACR",
    y_data=data,
    point_rate=rate,
    unit="mm",
    curve_type="Distance",
    current_frame=50
)
win.show()

# Test cursor update
win.update_frame(80)
assert win.current_frame == 80
assert "Frame 80" in win.lbl_current_val.text()

# Test time/frame mode switch
win._on_axis_mode_changed(1)  # switch to frames
assert win.x_axis_mode == "frame"
win._on_axis_mode_changed(0)  # switch to time
assert win.x_axis_mode == "time"

# Test cursor dragged signal
cursor_times = []
win.timeCursorMoved.connect(lambda t: cursor_times.append(t))
win.time_cursor.setValue(0.5)
win._on_cursor_dragged()
assert len(cursor_times) > 0
assert abs(cursor_times[0] - 0.5) < 1e-4

print("MeasurementPlotWindow verified completely!")

# 4. Test MainWindow Integration
main_win = MainWindow()
main_win.trial = trial
main_win.playback.total_frames = n_frames
main_win.playback.point_rate = rate

main_win.show_measurement_plot("Distance: L_ACR ↔ R_ACR", data, "mm", "Distance")
assert len(main_win.measurement_plot_windows) == 1
assert main_win.measurement_plot_windows[0].isVisible()

# Advance frame in MainWindow and verify synchronized update
main_win._on_frame_changed(120)
assert main_win.measurement_plot_windows[0].current_frame == 120

print("MainWindow measurement plot window synchronization verified!")
print("ALL TESTS PASSED SUCCESSFULLY!")

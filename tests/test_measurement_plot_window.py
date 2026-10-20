import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication, QPushButton
from app import MainWindow
from core.data_models import C3DTrial
from gui.marker_tools_dialog import MeasureDistanceDialog, MeasureAngleDialog

print("Initializing Measurement Plotting (in Universal Plotter) test...", flush=True)
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

# Test clicking 'Plot' emits plotRequested to plotter (no popup window)
plot_requests = []
dist_dlg.plotRequested.connect(lambda label, data: plot_requests.append((label, data)))
btn_plot.click()

assert len(plot_requests) == 1
label, data = plot_requests[0]
assert label == "Dist_L_ACR_R_ACR"
assert len(data) == n_frames
print("Verified MeasureDistanceDialog clicking 'Plot' emits plotRequested directly without opening separate window.")

# 2. Test MeasureAngleDialog
angle_dlg = MeasureAngleDialog(trial, current_frame=50, preselected=["L_ACR", "R_ACR", "V_ACR"])
angle_plot_btns = [b for b in angle_dlg.findChildren(QPushButton) if b.text() == "Plot"]
assert len(angle_plot_btns) == 1, f"Expected angle button 'Plot', found {[b.text() for b in angle_dlg.findChildren(QPushButton)]}"

angle_requests = []
angle_dlg.plotRequested.connect(lambda label, data: angle_requests.append((label, data)))
angle_plot_btns[0].click()

assert len(angle_requests) == 1
assert angle_requests[0][0] == "Angle_L_ACR_R_ACR_V_ACR"
print("Verified MeasureAngleDialog clicking 'Plot' emits plotRequested directly without opening separate window.")

# 3. Test MainWindow Integration
main_win = MainWindow()
main_win.show()
QApplication.processEvents()
main_win.trial = trial
main_win.playback.total_frames = n_frames
main_win.playback.point_rate = rate
main_win.plotter_widget.load_trial(trial)

# Test show_measurement_plot plots directly into Universal Plotter
main_win.show_measurement_plot("Distance: L_ACR ↔ R_ACR", data, "mm", "Distance")
assert "Distance: L_ACR ↔ R_ACR" in main_win.plotter_widget.active_curves
assert hasattr(main_win, "measurement_plot_windows") is False or len(getattr(main_win, "measurement_plot_windows", [])) == 0

# Test plot_marker_distance plots directly into Universal Plotter
main_win.plot_marker_distance("L_ACR", "R_ACR")
expected_dist_label = "Distance: L_ACR ↔ R_ACR (mm)"
assert expected_dist_label in main_win.plotter_widget.active_curves

# Advance frame in MainWindow and verify synchronized update in plotter
main_win._on_frame_changed(120)
assert main_win.plotter_widget.current_frame == 120

print("MainWindow distance measurement in Universal Plotter synchronization verified!")
print("ALL TESTS PASSED SUCCESSFULLY!")

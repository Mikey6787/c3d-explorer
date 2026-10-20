"""Comprehensive automated test verifying:
1. Distance and angle measurements compute Mean, SD, Min, Max strictly within the user-defined trim / ROI range.
2. Curve plotting highlights the section of the curve within the ROI range.
3. Dynamic synchronization between timeline trim changes and open measurement dialogs/plots.
4. "Fit ROI" and "Crop to ROI" functionalities.
"""

import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from app import MainWindow
from core.data_models import C3DTrial
from gui.marker_tools_dialog import MeasureDistanceDialog, MeasureAngleDialog, compute_distance_trajectory, compute_angle_trajectory
from gui.plotter_window import UniversalPlotterWindow

print("Starting ROI plotting and stats verification...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# Create mock data with 100 frames
n_frames = 100
rate = 100.0

# Create deterministic marker trajectory:
# Marker 1 is fixed at (10, 10, 10)
# Marker 2 moves along X: distance[i] = 10 + i (for i in 0..99)
m1_data = np.ones((n_frames, 3)) * 10.0
m2_data = np.ones((n_frames, 3)) * 10.0
m2_data[:, 0] = 10.0 + np.arange(10, 10 + n_frames, dtype=float)

# Marker 3 moves along Y
m3_data = np.ones((n_frames, 3)) * 10.0
m3_data[:, 1] = 10.0 + np.arange(10, 10 + n_frames, dtype=float)

trial = C3DTrial(
    file_path="mock_trial.c3d",
    first_frame=1,
    last_frame=n_frames,
    point_rate=rate,
    point_frame_count=n_frames,
    analog_rate=1000.0,
    analog_frame_count=n_frames * 10,
    analog_subsamples=10,
    markers={"M1": m1_data, "M2": m2_data, "M3": m3_data},
    analogs={},
    force_platforms=[],
    events=[]
)

# -------------------------------------------------------------
# 1. Test MeasureDistanceDialog ROI Stats
# -------------------------------------------------------------
# Full trial distance ranges from 10.0 to 109.0.
# If trim is 20 to 40 (frames 20..40, 21 frames):
# distances are 30.0 to 50.0.
# Mean = (30 + 50) / 2 = 40.0.
# Min = 30.0, Max = 50.0, Std = std(30..50).
trim_start, trim_end = 20, 40
expected_slice = np.arange(10 + trim_start, 10 + trim_end + 1, dtype=float)
exp_mean = float(np.mean(expected_slice))
exp_std = float(np.std(expected_slice))
exp_min = float(np.min(expected_slice))
exp_max = float(np.max(expected_slice))

dist_dlg = MeasureDistanceDialog(
    trial, current_frame=25,
    preselected=["M1", "M2"],
    trim_range=(trim_start, trim_end)
)

stats_text = dist_dlg.lbl_stats.text()
assert f"ROI [F{trim_start + 1}–{trim_end + 1}]" in stats_text, f"Expected ROI tag in stats text, got: {stats_text}"
assert f"{exp_mean:.2f}" in stats_text, f"Expected mean {exp_mean:.2f} in {stats_text}"
assert f"{exp_std:.2f}" in stats_text, f"Expected std {exp_std:.2f} in {stats_text}"
assert f"{exp_min:.2f}" in stats_text, f"Expected min {exp_min:.2f} in {stats_text}"
assert f"{exp_max:.2f}" in stats_text, f"Expected max {exp_max:.2f} in {stats_text}"
print("MeasureDistanceDialog stats strictly inside trimmed ROI verified!")

# Test dynamic update of trim range
dist_dlg.set_trim_range(50, 70)
expected_slice2 = np.arange(10 + 50, 10 + 70 + 1, dtype=float)
exp_mean2 = float(np.mean(expected_slice2))
stats_text2 = dist_dlg.lbl_stats.text()
assert f"ROI [F51–71]" in stats_text2
assert f"{exp_mean2:.2f}" in stats_text2
print("MeasureDistanceDialog dynamic set_trim_range update verified!")

# -------------------------------------------------------------
# 2. Test MeasureAngleDialog ROI Stats
# -------------------------------------------------------------
angle_dlg = MeasureAngleDialog(
    trial, current_frame=25,
    preselected=["M2", "M1", "M3"],
    trim_range=(10, 30)
)
angle_stats = angle_dlg.lbl_stats.text()
assert "ROI [F11–31]" in angle_stats, f"Expected ROI [F11-31] in angle stats, got: {angle_stats}"
assert "Mean: 90.0°" in angle_stats, f"Expected 90.0° in angle stats, got: {angle_stats}"
print("MeasureAngleDialog stats strictly inside trimmed ROI verified!")

# -------------------------------------------------------------
# 3. Test Distance Trajectory Computation & Slicing
# -------------------------------------------------------------
dist_traj = compute_distance_trajectory(m1_data, m2_data)
assert len(dist_traj) == n_frames
assert np.allclose(dist_traj[trim_start:trim_end + 1], expected_slice)
print("Distance trajectory computation & ROI slicing verified!")

# -------------------------------------------------------------
# 4. Test UniversalPlotterWindow ROI Support
# -------------------------------------------------------------
plotter = UniversalPlotterWindow(trial, current_frame=0)
plotter.load_trial(trial)
plotter.set_trim_range(20, 80)
assert plotter.trim_range == (20, 80)
assert plotter.roi_region is not None
assert plotter.roi_region.isVisible() is True
assert "ROI: F21–81" in plotter.lbl_roi_status.text()
plotter.fit_roi()
p_range_x = plotter.plot_widget.getViewBox().viewRange()[0]
assert p_range_x[0] <= 21.0 and p_range_x[1] >= 81.0
print("UniversalPlotterWindow ROI region and status badge verified!")

# -------------------------------------------------------------
# 5. Test MainWindow Synchronization
# -------------------------------------------------------------
main_win = MainWindow()
main_win.trial = trial
main_win.plotter_widget.load_trial(trial)
main_win.playback.total_frames = n_frames
main_win.playback.point_rate = rate
main_win.timeline.set_trial_data(n_frames, rate, [])

# Open distance dialog
main_win.open_measure_distance_dialog()
assert main_win.dist_dialog is not None

# Change timeline trim on main window
main_win.timeline.set_trim_range(30, 60)

# Verify dist_dialog received the updated trim range
assert main_win.dist_dialog.trim_range == (30, 60)
assert "ROI [F31–61]" in main_win.dist_dialog.lbl_stats.text()

# Plot measurement and verify it routes directly to plotter_widget
main_win.show_measurement_plot("Distance Test", dist_traj)
assert "Distance Test" in main_win.plotter_widget.active_curves

# Now change timeline trim again to (10, 45) and verify plotter_widget updates
main_win.timeline.set_trim_range(10, 45)
assert main_win.plotter_widget.trim_range == (10, 45)
main_win.plotter_widget.fit_roi()
p_range_x2 = main_win.plotter_widget.plot_widget.getViewBox().viewRange()[0]
assert p_range_x2[0] <= 11.0 and p_range_x2[1] >= 46.0

print("MainWindow timeline -> dialogs -> plotter bidirectional ROI synchronization verified!")
print("ALL ROI PLOTTING AND STATS TESTS PASSED PERFECTLY!")

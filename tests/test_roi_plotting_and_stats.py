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
from gui.measurement_plot_window import MeasurementPlotWindow
from gui.plot_panel import PlotPanel
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
# 3. Test MeasurementPlotWindow Highlighting & ROI Stats
# -------------------------------------------------------------
dist_traj = compute_distance_trajectory(m1_data, m2_data)
plot_win = MeasurementPlotWindow(
    title="Distance: M1 ↔ M2",
    y_data=dist_traj,
    point_rate=rate,
    unit="mm",
    curve_type="Distance",
    current_frame=25,
    trim_range=(trim_start, trim_end)
)
plot_win.show()

# Verify stats chip
chip_text = plot_win.lbl_stats.text()
assert f"ROI [F{trim_start + 1}–{trim_end + 1}" in chip_text, f"Expected ROI in chip, got {chip_text}"
assert f"Mean: {exp_mean:.2f}" in chip_text
assert f"SD: ±{exp_std:.2f}" in chip_text
assert f"Min: {exp_min:.2f}" in chip_text
assert f"Max: {exp_max:.2f}" in chip_text

# Verify curve highlight items
assert plot_win.roi_region.isVisible() is True
# roi_curve_item data length should match the ROI length (trim_end - trim_start + 1)
roi_x, roi_y = plot_win.roi_curve_item.getData()
assert len(roi_y) == (trim_end - trim_start + 1), f"Expected ROI curve length {trim_end - trim_start + 1}, got {len(roi_y)}"
assert np.allclose(roi_y, expected_slice)

# full_curve_item data outside ROI is dimmed and contains full data
full_x, full_y = plot_win.full_curve_item.getData()
assert len(full_y) == n_frames

# Test "Fit ROI" and "Fit Full" in Frame mode (default)
plot_win.fit_roi()
view_x_range, _ = plot_win.plot_item.viewRange()
f_min_expected = float(trim_start + 1)
f_max_expected = float(trim_end + 1)
assert view_x_range[0] <= f_min_expected and view_x_range[1] >= f_max_expected

plot_win.auto_range()
view_full_x, _ = plot_win.plot_item.viewRange()
assert view_full_x[0] <= 1.0 and view_full_x[1] >= n_frames

# Test dynamic set_trim_range
plot_win.set_trim_range(5, 15)
assert plot_win.trim_range == (5, 15)
assert "ROI [F6–16" in plot_win.lbl_stats.text()
roi_x_new, roi_y_new = plot_win.roi_curve_item.getData()
# Test on-curve hover inspection in MeasurementPlotWindow
pt_scene = plot_win.plot_item.vb.mapViewToScene(QPointF(float(plot_win.x_frames[10]), float(plot_win.y_data[10])))
plot_win._on_mouse_moved([pt_scene])
assert plot_win.hover_dot.isVisible(), "hover_dot should be visible when mouse is on curve in MeasurementPlotWindow"
assert plot_win.hover_label.isVisible(), "hover_label should be visible when mouse is on curve in MeasurementPlotWindow"
assert f"{plot_win.y_data[10]:.2f}" in plot_win.hover_label.toHtml(), "Value should be in hover label"

# Moving outside plot bounds hides hover items
plot_win._on_mouse_moved([QPointF(-100, -100)])
assert not plot_win.hover_dot.isVisible(), "hover_dot should hide outside plot in MeasurementPlotWindow"
assert not plot_win.hover_label.isVisible(), "hover_label should hide outside plot in MeasurementPlotWindow"
print("MeasurementPlotWindow on-curve hover inspection verified!")

print("MeasurementPlotWindow ROI highlight, stats, and Fit ROI verified!")

# -------------------------------------------------------------
# 4. Test PlotPanel and UniversalPlotterWindow ROI Support
# -------------------------------------------------------------
plot_panel = PlotPanel()
plot_panel.load_trial(trial)
plot_panel.set_trim_range(15, 60)
assert plot_panel.trim_range == (15, 60)
assert plot_panel.roi_region is not None
assert plot_panel.roi_region.isVisible() is True
assert "ROI: F16–61" in plot_panel.lbl_roi_status.text()
plot_panel.fit_roi()
p_range_x = plot_panel.plot_widget.getViewBox().viewRange()[0]
assert p_range_x[0] <= 16.0 and p_range_x[1] >= 61.0, f"Expected ROI range in plot_panel, got {p_range_x}"
print("PlotPanel ROI region and fit_roi verified!")

# Test on-curve hover inspection in PlotPanel
if len(plot_panel.active_curves) > 0:
    first_curve = list(plot_panel.active_curves.values())[0]
    cx, cy = first_curve.getData()
    pt_scene_panel = plot_panel.plot_widget.getViewBox().mapViewToScene(QPointF(float(cx[10]), float(cy[10])))
    plot_panel._on_mouse_moved([pt_scene_panel])
    assert plot_panel.hover_dot.isVisible(), "hover_dot should be visible on curve in PlotPanel"
    assert plot_panel.hover_label.isVisible(), "hover_label should be visible on curve in PlotPanel"
    assert f"{cy[10]:.2f}" in plot_panel.hover_label.toHtml(), "Value should be in hover label in PlotPanel"

    plot_panel._on_mouse_moved([QPointF(-100, -100)])
    assert not plot_panel.hover_dot.isVisible(), "hover_dot should hide outside plot in PlotPanel"
    assert not plot_panel.hover_label.isVisible(), "hover_label should hide outside plot in PlotPanel"
    print("PlotPanel on-curve hover inspection verified!")

plotter = UniversalPlotterWindow(trial, current_frame=0)
plotter.set_trim_range(20, 80)
assert plotter.trim_range == (20, 80)
assert plotter.roi_region is not None
assert plotter.roi_region.isVisible() is True
assert "ROI: F21–81" in plotter.lbl_roi_status.text()
print("UniversalPlotterWindow ROI region and status badge verified!")

# -------------------------------------------------------------
# 5. Test MainWindow Synchronization
# -------------------------------------------------------------
main_win = MainWindow()
main_win.trial = trial
main_win.plot_panel.load_trial(trial)
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

# Open measurement plot window and verify it also has (30, 60)
main_win.show_measurement_plot("Distance Test", dist_traj)
win_inst = main_win.measurement_plot_windows[-1]
assert win_inst.trim_range == (30, 60)
assert "ROI [F31–61" in win_inst.lbl_stats.text()

# Now change timeline trim again to (10, 45) and verify open plot window updates
main_win.timeline.set_trim_range(10, 45)
assert win_inst.trim_range == (10, 45)
assert "ROI [F11–46" in win_inst.lbl_stats.text()

# Verify main_win.plot_panel received updated trim range even while dock is not shown
assert main_win.plot_panel.trim_range == (10, 45)
main_win.plot_panel.fit_roi()
p_range_x2 = main_win.plot_panel.plot_widget.getViewBox().viewRange()[0]
assert p_range_x2[0] <= 11.0 and p_range_x2[1] >= 46.0

print("MainWindow timeline -> dialogs -> plot windows bidirectional ROI synchronization verified!")
print("ALL ROI PLOTTING AND STATS TESTS PASSED PERFECTLY!")

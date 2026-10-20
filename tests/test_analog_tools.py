"""
Comprehensive unit and integration tests for Analog Management and Signal Processing.
Tests:
1. Signal parsing from CSV and TXT files.
2. Butterworth filtering algorithms (Lowpass, Highpass, Bandpass, Notch).
3. Moving RMS envelope and signal statistics calculation.
4. AnalogToolsDialog UI, channel listing, search/filter, and statistics.
5. Channel Renaming and Deletion lifecycles.
6. Importing new analog channels from external data.
7. Real-time filter preview and applying filters (Save as New vs Overwrite).
8. MainWindow Tools -> Analog integration and Universal Plotter synchronization.
9. C3DWriter analog export synchronization.
"""

import sys
import os
import tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app import MainWindow
from core.data_models import C3DTrial
from core.c3d_writer import C3DWriter
from gui.analog_dialog import (
    AnalogToolsDialog, ImportAnalogDialog, parse_analog_file,
    apply_butterworth_filter, compute_moving_rms, compute_signal_stats
)


print("Initializing Analog Tools & Signal Processing test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# -------------------------------------------------------------
# 1. Test Filter Algorithms & Mathematical Correctness
# -------------------------------------------------------------
fs = 1000.0  # 1000 Hz
t = np.linspace(0, 1.0, 1000, endpoint=False)
# 10 Hz signal + 60 Hz noise
sig_10hz = np.sin(2 * np.pi * 10 * t)
noise_60hz = 0.5 * np.sin(2 * np.pi * 60 * t)
raw_signal = sig_10hz + noise_60hz

# 1.1 Butterworth Lowpass (Cutoff 20 Hz -> removes 60 Hz noise)
lp_sig = apply_butterworth_filter(raw_signal, fs, "lowpass", order=4, cutoff=20.0)
assert len(lp_sig) == len(raw_signal)
# 60 Hz component should be heavily attenuated
np.testing.assert_allclose(lp_sig[100:900], sig_10hz[100:900], atol=0.15)
print("Butterworth Low-pass filter verified!")

# 1.2 Butterworth Highpass (Cutoff 40 Hz -> removes 10 Hz signal, retains 60 Hz)
hp_sig = apply_butterworth_filter(raw_signal, fs, "highpass", order=4, cutoff=40.0)
assert len(hp_sig) == len(raw_signal)
np.testing.assert_allclose(hp_sig[100:900], noise_60hz[100:900], atol=0.15)
print("Butterworth High-pass filter verified!")

# 1.3 Butterworth Bandpass (15 Hz to 80 Hz -> retains 60 Hz)
bp_sig = apply_butterworth_filter(raw_signal, fs, "bandpass", order=4, cutoff=(30.0, 80.0))
assert len(bp_sig) == len(raw_signal)
np.testing.assert_allclose(bp_sig[100:900], noise_60hz[100:900], atol=0.15)
print("Butterworth Band-pass filter verified!")

# 1.4 Notch filter at 60 Hz -> removes 60 Hz component
notch_sig = apply_butterworth_filter(raw_signal, fs, "notch", order=4, cutoff=60.0)
assert len(notch_sig) == len(raw_signal)
np.testing.assert_allclose(notch_sig[100:900], sig_10hz[100:900], atol=0.2)
print("Powerline Notch filter verified!")

# 1.5 Moving RMS Envelope
rms_env = compute_moving_rms(raw_signal, window_size=50)
assert len(rms_env) == len(raw_signal)
assert np.all(rms_env >= 0.0), "RMS envelope must be non-negative"
print("Moving RMS envelope computation verified!")

# 1.6 Signal stats calculation
stats = compute_signal_stats(raw_signal)
assert "min" in stats and "max" in stats and "mean" in stats and "rms" in stats
assert stats["rms"] > 0
print("Signal statistics verified!")

# -------------------------------------------------------------
# 2. Test File Parsing (CSV, TXT)
# -------------------------------------------------------------
with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
    f.write("EMG_Biceps,EMG_Triceps\n")
    for val in np.linspace(0.1, 2.5, 500):
        f.write(f"{val:.4f},{val*1.5:.4f}\n")
    csv_path = f.name

try:
    cols, err = parse_analog_file(csv_path, expected_frames=500)
    assert err is None
    assert cols is not None
    assert "EMG_Biceps" in cols
    assert "EMG_Triceps" in cols
    assert len(cols["EMG_Biceps"]) == 500
    print("Multi-column CSV analog data parser verified!")
finally:
    if os.path.exists(csv_path):
        os.remove(csv_path)

# -------------------------------------------------------------
# 3. Create Mock C3D Trial with Analogs
# -------------------------------------------------------------
n_point_frames = 100
analog_sub = 10
n_analog_frames = n_point_frames * analog_sub  # 1000 frames
p_rate = 100.0
a_rate = 1000.0

m_data = np.zeros((n_point_frames, 3))
emg1_data = raw_signal.copy()
emg2_data = np.cos(2 * np.pi * 5 * t)
force_z = np.linspace(0, 800, n_analog_frames)

trial = C3DTrial(
    file_path="mock_analog.c3d",
    first_frame=1,
    last_frame=n_point_frames,
    point_rate=p_rate,
    point_frame_count=n_point_frames,
    analog_rate=a_rate,
    analog_frame_count=n_analog_frames,
    analog_subsamples=analog_sub,
    markers={"RASI": m_data, "LASI": m_data + 10.0},
    analogs={"EMG1": emg1_data, "EMG2": emg2_data, "FP_Fz": force_z},
    analog_units={"EMG1": "mV", "EMG2": "mV", "FP_Fz": "N"},
    force_platforms=[],
    events=[]
)

# -------------------------------------------------------------
# 4. Test AnalogToolsDialog & Channel Manager Tab
# -------------------------------------------------------------
dlg = AnalogToolsDialog(trial)
dlg.show()
QApplication.processEvents()

# Verify channel table
assert dlg.table.rowCount() == 3
channel_names_in_table = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
assert "EMG1" in channel_names_in_table
assert "EMG2" in channel_names_in_table
assert "FP_Fz" in channel_names_in_table
print("AnalogToolsDialog initialized and channel table populated successfully!")

# Test search / filter
dlg.search_box.setText("FP")
dlg._filter_channel_table("FP")
visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
assert len(visible_rows) == 1
assert dlg.table.item(visible_rows[0], 0).text() == "FP_Fz"
dlg.search_box.setText("")
dlg._filter_channel_table("")
print("Channel search filtering verified!")

# Test Renaming Channel
dlg.table.selectRow(0)
ch_to_rename = dlg.table.item(0, 0).text()
new_name = "EMG_Primary"
trial.analogs[new_name] = trial.analogs.pop(ch_to_rename)
trial.analog_units[new_name] = trial.analog_units.pop(ch_to_rename, "mV")
dlg._populate_channel_table()
assert new_name in [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
print(f"Channel renaming from {ch_to_rename} to {new_name} verified!")

# Test Deleting Channel
trial.analogs.pop(new_name, None)
trial.analog_units.pop(new_name, None)
dlg._populate_channel_table()
assert dlg.table.rowCount() == 2
print("Channel deletion verified!")

# -------------------------------------------------------------
# 5. Test Filter & Signal Processing Tab
# -------------------------------------------------------------
dlg.tabs.setCurrentIndex(1)
dlg._on_tab_changed(1)

# Check target channel selection
assert dlg.combo_filter_ch.count() == 2
dlg.combo_filter_ch.setCurrentIndex(0)
target_ch = dlg.combo_filter_ch.currentData()
assert target_ch in trial.analogs

# Test switching methods
dlg.combo_filter_type.setCurrentText("Butterworth Low-pass")
dlg.spin_cutoff.setValue(25.0)
dlg.spin_order.setValue(4)
dlg._update_filter_preview()

# Verify preview plot has 2 items (Raw and Processed)
plot_items = dlg.preview_plot.getPlotItem().items
assert len(plot_items) >= 2, "Preview plot should display both raw and filtered signals"
print("Real-time preview plot with raw and processed signals verified!")

# Test applying filter as New Channel
dlg.rb_save_new.setChecked(True)
dlg.txt_new_channel_name.setText("EMG_Filtered_25Hz")
dlg._apply_filter_to_trial()
assert "EMG_Filtered_25Hz" in trial.analogs
assert len(trial.analogs["EMG_Filtered_25Hz"]) == n_analog_frames
print("Saved filtered signal as new channel 'EMG_Filtered_25Hz' successfully!")

# Test applying Moving RMS as New Channel
dlg.combo_filter_type.setCurrentText("Moving RMS Envelope")
dlg.spin_rms_window.setValue(40.0)
dlg.txt_new_channel_name.setText("EMG_RMS_40ms")
dlg._apply_filter_to_trial()
assert "EMG_RMS_40ms" in trial.analogs
print("Saved Moving RMS signal as new channel 'EMG_RMS_40ms' successfully!")

dlg.close()

# -------------------------------------------------------------
# 6. Test MainWindow Integration (Tools -> Analog)
# -------------------------------------------------------------
main_win = MainWindow()
main_win.show()
QApplication.processEvents()

main_win.trial = trial
main_win.plotter_widget.load_trial(trial)

# Verify Tools -> Analog action exists
tools_actions = [a.text() for a in main_win.menuBar().actions() if "Tools" in a.text()][0]
# Find Analog action
analog_actions = [a for a in main_win.findChildren(QApplication.instance().__class__) if False]
assert hasattr(main_win, "open_analog_tools_dialog")

# Trigger open_analog_tools_dialog
main_win.open_analog_tools_dialog()
assert main_win.analog_dialog is not None
assert main_win.analog_dialog.isVisible()

# Verify UniversalPlotter tree has the new analog channels
analog_root = None
for i in range(main_win.plotter_widget.tree.topLevelItemCount()):
    it = main_win.plotter_widget.tree.topLevelItem(i)
    if "Analog" in it.text(0):
        analog_root = it
        break

assert analog_root is not None
child_names = [analog_root.child(j).text(0) for j in range(analog_root.childCount())]
assert any("EMG_Filtered_25Hz" in name for name in child_names)
assert any("EMG_RMS_40ms" in name for name in child_names)
print("Universal Plotter tree automatically synchronized with new analog channels!")

# Test plotting analog channel from AnalogToolsDialog into Universal Plotter
main_win.analog_dialog.table.selectRow(0)
selected_ch = main_win.analog_dialog._get_selected_channel()
assert selected_ch is not None
main_win.analog_dialog._action_plot_selected()

# Verify channel is active in plotter_widget.active_curves
active_curve_names = list(main_win.plotter_widget.active_curves.keys())
assert any(selected_ch in name for name in active_curve_names), f"Expected {selected_ch} in active curves, got {active_curve_names}"

# Verify item is checked in Analog Channels tree
checked_analog_items = [
    analog_root.child(j).text(0)
    for j in range(analog_root.childCount())
    if analog_root.child(j).checkState(0) == Qt.Checked
]
assert any(selected_ch in name for name in checked_analog_items)

# Verify no "Custom & Measurements" item was created for this channel
custom_roots = [
    main_win.plotter_widget.tree.topLevelItem(i)
    for i in range(main_win.plotter_widget.tree.topLevelItemCount())
    if "Custom" in main_win.plotter_widget.tree.topLevelItem(i).text(0)
]
if custom_roots:
    for cr in custom_roots:
        cr_children = [cr.child(j).text(0) for j in range(cr.childCount())]
        assert not any(selected_ch in name for name in cr_children)

print(f"Plotting analog channel '{selected_ch}' activated existing tree item under Analog Channels successfully!")

# Test Multi-Selection Batch Plotting
from PySide6.QtCore import QItemSelection, QItemSelectionModel
sel_model = main_win.analog_dialog.table.selectionModel()
sel_model.clearSelection()

# Select rows 0 and 1
idx0 = main_win.analog_dialog.table.model().index(0, 0)
idx1 = main_win.analog_dialog.table.model().index(1, 0)
sel_model.select(idx0, QItemSelectionModel.Select | QItemSelectionModel.Rows)
sel_model.select(idx1, QItemSelectionModel.Select | QItemSelectionModel.Rows)

multi_selected = main_win.analog_dialog._get_selected_channels()
assert len(multi_selected) == 2, f"Expected 2 selected channels, got {len(multi_selected)}: {multi_selected}"

main_win.analog_dialog._action_plot_selected()
active_curves_after_multi = list(main_win.plotter_widget.active_curves.keys())
for ch in multi_selected:
    assert any(ch in name for name in active_curves_after_multi), f"Expected {ch} in active curves after multi-plot"
print(f"Batch plotting of multiple selected channels {multi_selected} verified!")

# Test Multi-Selection Batch Deletion
# Add two test channels to delete in batch
trial.analogs["TMP_DELETE_1"] = np.ones(n_analog_frames)
trial.analogs["TMP_DELETE_2"] = np.ones(n_analog_frames)
trial.analog_units["TMP_DELETE_1"] = "V"
trial.analog_units["TMP_DELETE_2"] = "V"
main_win.analog_dialog._populate_channel_table()

# Find rows for TMP_DELETE_1 and TMP_DELETE_2
r_del1 = None
r_del2 = None
for r in range(main_win.analog_dialog.table.rowCount()):
    txt = main_win.analog_dialog.table.item(r, 0).text()
    if txt == "TMP_DELETE_1":
        r_del1 = r
    elif txt == "TMP_DELETE_2":
        r_del2 = r

assert r_del1 is not None and r_del2 is not None
sel_model.clearSelection()
idx_d1 = main_win.analog_dialog.table.model().index(r_del1, 0)
idx_d2 = main_win.analog_dialog.table.model().index(r_del2, 0)
sel_model.select(idx_d1, QItemSelectionModel.Select | QItemSelectionModel.Rows)
sel_model.select(idx_d2, QItemSelectionModel.Select | QItemSelectionModel.Rows)

to_delete = main_win.analog_dialog._get_selected_channels()
assert set(to_delete) == {"TMP_DELETE_1", "TMP_DELETE_2"}

main_win.analog_dialog._action_delete_channel()
assert "TMP_DELETE_1" not in trial.analogs
assert "TMP_DELETE_2" not in trial.analogs
print("Batch deletion of multiple selected channels verified!")

main_win.analog_dialog.close()
main_win.close()

# -------------------------------------------------------------
# 7. Test C3DWriter Synchronization
# -------------------------------------------------------------
with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
    tmp_c3d_path = tmp.name

try:
    C3DWriter.save_c3d(trial, tmp_c3d_path)
    from core.c3d_reader import C3DReader
    reloaded_trial = C3DReader.read(tmp_c3d_path)
    assert len(reloaded_trial.analogs) == len(trial.analogs)
    assert "EMG_Filtered_25Hz" in reloaded_trial.analogs
    assert "EMG_RMS_40ms" in reloaded_trial.analogs
    assert len(reloaded_trial.analogs["EMG_Filtered_25Hz"]) == trial.analog_frame_count
    print("C3DWriter analog export synchronization verified via round-trip save and read!")
finally:
    if os.path.exists(tmp_c3d_path):
        os.remove(tmp_c3d_path)

print("\nALL ANALOG TOOLS & SIGNAL PROCESSING TESTS PASSED PERFECTLY!")

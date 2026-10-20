"""
Comprehensive tests for 3D Marker Trajectory Filtering.
Tests:
1. Mathematical correctness of filter_marker_array:
   - Attenuation of high-frequency noise on 3D coordinates.
   - Preservation of true low-frequency motion.
   - Robustness to NaNs and missing marker frames.
2. FilterMarkersDialog UI components, parameter validation, and signal emission.
3. MainWindow Tools -> Marker -> Filter... action integration.
4. Filtering all markers across a C3D trial.
5. Undo and Redo lifecycle (restoring raw data and reapplying filtered data).
6. C3D export round-trip preserving filtered markers.
"""

import sys
import os
import tempfile
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app import MainWindow
from core.data_models import C3DTrial
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
from gui.marker_tools_dialog import FilterMarkersDialog, filter_marker_array


print("Initializing Marker Filtering test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# -------------------------------------------------------------
# 1. Test Filter Algorithm & Mathematical Correctness
# -------------------------------------------------------------
fs = 100.0  # 100 Hz MoCap sampling rate
n_frames = 200
t = np.linspace(0, 2.0, n_frames, endpoint=False)

# Pure 2 Hz biomechanical motion + 25 Hz tremor / noise
sig_2hz = 100.0 * np.sin(2 * np.pi * 2.0 * t)
noise_25hz = 15.0 * np.sin(2 * np.pi * 25.0 * t)

raw_x = sig_2hz + noise_25hz
raw_y = sig_2hz * 0.5 + noise_25hz * 0.7
raw_z = sig_2hz * 1.5

raw_marker_data = np.column_stack([raw_x, raw_y, raw_z])

# 1.1 Apply low-pass filter (order=4, cutoff=6.0 Hz)
filtered_data = filter_marker_array(raw_marker_data, fs=fs, order=4, cutoff=6.0)
assert filtered_data.shape == raw_marker_data.shape

# 25 Hz noise on X should be heavily suppressed
np.testing.assert_allclose(filtered_data[20:180, 0], sig_2hz[20:180], atol=3.0)
print("filter_marker_array noise attenuation verified!")

# 1.2 Test handling of NaNs (gap interpolation and restoration)
nan_marker_data = raw_marker_data.copy()
nan_marker_data[50:60, :] = np.nan
filtered_nan_data = filter_marker_array(nan_marker_data, fs=fs, order=4, cutoff=6.0)
assert np.all(np.isnan(filtered_nan_data[50:60, :])), "NaN gaps should be preserved in filtered output"
assert not np.any(np.isnan(filtered_nan_data[10:45, :])), "Valid segments should remain non-NaN"
print("filter_marker_array NaN preservation verified!")

# -------------------------------------------------------------
# 2. Test FilterMarkersDialog UI & Parameter Validation
# -------------------------------------------------------------
trial = C3DTrial(
    file_path="mock_filter_test.c3d",
    first_frame=1,
    last_frame=n_frames,
    point_rate=fs,
    point_frame_count=n_frames,
    analog_rate=1000.0,
    analog_frame_count=1000,
    analog_subsamples=10,
    markers={
        "RASI": raw_marker_data.copy(),
        "LASI": raw_marker_data.copy() + 50.0,
        "RPSI": raw_marker_data.copy() - 30.0
    },
    analogs={},
    analog_units={},
    force_platforms=[],
    events=[]
)

dlg = FilterMarkersDialog(trial)
dlg.show()
QApplication.processEvents()

assert dlg.spin_order.value() == 4
assert dlg.spin_cutoff.value() == 6.0
assert dlg.spin_cutoff.maximum() < (fs * 0.5), "Cutoff max must be strictly less than Nyquist"

# Test signal emission
emitted_params = []
dlg.filterApplied.connect(lambda o, c: emitted_params.append((o, c)))
dlg.spin_order.setValue(5)
dlg.spin_cutoff.setValue(8.5)
dlg._on_apply_clicked()

assert len(emitted_params) == 1
assert emitted_params[0] == (5, 8.5)
dlg.close()
print("FilterMarkersDialog parameter configuration and signal emission verified!")

# -------------------------------------------------------------
# 3. Test MainWindow Menu Action & Full Filtering Workflow
# -------------------------------------------------------------
main_win = MainWindow()
main_win.show()
QApplication.processEvents()

main_win.trial = trial
main_win.plotter_widget.load_trial(trial)

# Verify Tools -> Marker -> Filter action exists
tools_menu_action = [a for a in main_win.menuBar().actions() if "Tools" in a.text()][0]
tools_menu = tools_menu_action.menu()
marker_menu = [m for m in tools_menu.actions() if "Marker" in m.text()][0].menu()

filter_action = [a for a in marker_menu.actions() if "Filter" in a.text()]
assert len(filter_action) == 1, "Expected 'Filter...' action in Tools -> Marker menu"
print("Tools -> Marker -> Filter... menu action verified!")

# Record raw marker copies before filtering
orig_markers = {name: trial.markers[name].copy() for name in trial.markers}

# Execute filter_all_markers via MainWindow (Order=4, Cutoff=6.0 Hz)
main_win.filter_all_markers(order=4, cutoff=6.0)

# Verify all markers in trial are filtered
for m_name in ("RASI", "LASI", "RPSI"):
    assert not np.array_equal(trial.markers[m_name], orig_markers[m_name]), \
        f"Marker {m_name} should be modified by the filter"
    # Noise should be attenuated
    np.testing.assert_allclose(
        trial.markers[m_name][20:180, 0],
        sig_2hz[20:180] + (50.0 if m_name == "LASI" else -30.0 if m_name == "RPSI" else 0.0),
        atol=3.0
    )

print("Filtering all markers across trial verified!")

# -------------------------------------------------------------
# 4. Test Undo / Redo Lifecycle
# -------------------------------------------------------------
# Test Undo
main_win.undo_stack.undo()
for m_name in ("RASI", "LASI", "RPSI"):
    np.testing.assert_array_equal(trial.markers[m_name], orig_markers[m_name])
print("Undoing marker filter restores exact raw coordinates verified!")

# Test Redo
main_win.undo_stack.redo()
for m_name in ("RASI", "LASI", "RPSI"):
    assert not np.array_equal(trial.markers[m_name], orig_markers[m_name])
    np.testing.assert_allclose(
        trial.markers[m_name][20:180, 0],
        sig_2hz[20:180] + (50.0 if m_name == "LASI" else -30.0 if m_name == "RPSI" else 0.0),
        atol=3.0
    )
print("Redoing marker filter reapplies filtered coordinates verified!")

# -------------------------------------------------------------
# 5. Test C3D Export Synchronization with Filtered Markers
# -------------------------------------------------------------
with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
    tmp_c3d_path = tmp.name

try:
    C3DWriter.save_c3d(trial, tmp_c3d_path)
    reloaded_trial = C3DReader.read(tmp_c3d_path)
    assert len(reloaded_trial.markers) == len(trial.markers)
    np.testing.assert_allclose(
        reloaded_trial.markers["RASI"],
        trial.markers["RASI"],
        atol=1e-3
    )
    print("C3DWriter export and reload of filtered markers verified!")
finally:
    if os.path.exists(tmp_c3d_path):
        os.remove(tmp_c3d_path)

main_win.close()

print("\nALL MARKER FILTERING TESTS PASSED PERFECTLY!")

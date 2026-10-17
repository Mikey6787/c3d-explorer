import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from core.data_models import C3DTrial
from gui.side_panel import SidePanel

# Mock QMessageBox.warning to prevent blocking modal in headless automated test
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok

print("Initializing Marker Rename test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

trial = C3DTrial(
    file_path="mock.c3d",
    first_frame=1,
    last_frame=10,
    point_rate=100.0,
    point_frame_count=10,
    analog_rate=1000.0,
    analog_frame_count=100,
    analog_subsamples=10,
    markers={
        "LASI": np.zeros((10, 3)),
        "RASI": np.zeros((10, 3)),
        "LPSI": np.zeros((10, 3)),
    }
)

panel = SidePanel()
panel.load_trial(trial)

renamed = []
panel.markerRenamed.connect(lambda old_n, new_n: renamed.append((old_n, new_n)))

# Verify rows
assert panel.markers_table.rowCount() == 3
print("Markers table row count verified.", flush=True)

# 1. Trigger double click & rename in place
item = panel.markers_table.item(0, 0) # "LASI"
assert item.text() == "LASI"
panel._on_marker_double_clicked(item)

item.setText("LASI_EDITED")
assert ("LASI", "LASI_EDITED") in renamed, f"Rename signal not received: {renamed}"
assert item.data(Qt.UserRole) == "LASI_EDITED"
print("In-place rename signal and UserRole verified.", flush=True)

# Simulate trial dictionary update
trial.markers["LASI_EDITED"] = trial.markers.pop("LASI")

# 2. Verify duplicate prevention: attempt to rename to existing "RASI"
renamed.clear()
item.setText("RASI")
assert len(renamed) == 0, "Duplicate rename should have been rejected"
assert item.text() == "LASI_EDITED", f"Expected revert to LASI_EDITED, got {item.text()}"
print("Duplicate prevention verified.", flush=True)

# 3. Verify empty string prevention
renamed.clear()
item.setText("   ")
assert len(renamed) == 0, "Empty rename should have been rejected"
assert item.text() == "LASI_EDITED", f"Expected revert to LASI_EDITED, got {item.text()}"
print("Empty string prevention verified.", flush=True)

# 4. Verify rename_marker_entry helper
panel.rename_marker_entry("LASI_EDITED", "LASI_FINAL")
assert item.text() == "LASI_FINAL"
assert item.data(Qt.UserRole) == "LASI_FINAL"
print("rename_marker_entry helper verified.", flush=True)

print("ALL MARKER RENAME TESTS PASSED SUCCESSFULLY!", flush=True)

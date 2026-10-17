import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QVector4D

from core.data_models import C3DTrial
from gui.side_panel import SidePanel
from gui.viewer_3d import Viewer3D
from gui.marker_tools_dialog import CreateAverageMarkerDialog

print("Initializing Multi-Select & 3D Picking test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# Create mock trial with 4 markers
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
        "LASI": np.full((10, 3), [100.0, 50.0, 800.0]),
        "RASI": np.full((10, 3), [-100.0, 50.0, 800.0]),
        "LPSI": np.full((10, 3), [80.0, -80.0, 810.0]),
        "RPSI": np.full((10, 3), [-80.0, -80.0, 810.0]),
    }
)

viewer = Viewer3D()
viewer.resize(800, 600)
viewer.load_trial(trial)

side_panel = SidePanel()
side_panel.load_trial(trial)

# Connect bidirectional selection
side_panel.markersSelected.connect(viewer.select_markers)
viewer.markersSelected.connect(side_panel.select_markers)

# 1. Test SidePanel table multi-selection
side_panel.select_markers(["LASI", "RASI"], emit_signal=True)
assert viewer.selected_markers == ["LASI", "RASI"], f"Viewer didn't receive multi-selection: {viewer.selected_markers}"
assert side_panel.get_selected_markers() == ["LASI", "RASI"], f"SidePanel didn't return selected: {side_panel.get_selected_markers()}"
print("SidePanel multi-selection -> 3D Viewport synchronization verified.")

# 2. Test 3D screen projection & picking
w, h = viewer.gl_view.width(), viewer.gl_view.height()
proj = viewer.gl_view.projectionMatrix((0, 0, w, h), (0, 0, w, h))
view = viewer.gl_view.viewMatrix()
mvp = proj * view

def get_screen_pos(m_name):
    pos3d = trial.markers[m_name][0]
    pt4 = QVector4D(float(pos3d[0]), float(pos3d[1]), float(pos3d[2]), 1.0)
    clip = mvp.map(pt4)
    ndc_x = clip.x() / clip.w()
    ndc_y = clip.y() / clip.w()
    sx = int((ndc_x + 1.0) * 0.5 * w)
    sy = int((1.0 - ndc_y) * 0.5 * h)
    return sx, sy

# Click LPSI in 3D without modifier -> single select
sx_lpsi, sy_lpsi = get_screen_pos("LPSI")
viewer.handle_3d_click(sx_lpsi, sy_lpsi, modifiers=Qt.NoModifier)
assert viewer.selected_markers == ["LPSI"], f"Expected ['LPSI'], got {viewer.selected_markers}"
assert side_panel.get_selected_markers() == ["LPSI"]
print("3D single-click picking verified.")

# Click RPSI in 3D with Option / Alt modifier -> multi-select
sx_rpsi, sy_rpsi = get_screen_pos("RPSI")
viewer.handle_3d_click(sx_rpsi, sy_rpsi, modifiers=Qt.AltModifier)
assert set(viewer.selected_markers) == {"LPSI", "RPSI"}, f"Expected ['LPSI', 'RPSI'], got {viewer.selected_markers}"
assert set(side_panel.get_selected_markers()) == {"LPSI", "RPSI"}
print("3D multi-select with Option/Alt modifier verified.")

# Click empty space without modifier -> deselect all
viewer.handle_3d_click(10, 10, modifiers=Qt.NoModifier)
assert len(viewer.selected_markers) == 0, f"Expected empty selection, got {viewer.selected_markers}"
assert len(side_panel.get_selected_markers()) == 0
print("3D empty space click deselection verified.")

# 3. Test CreateAverageMarkerDialog with multi-selection
side_panel.select_markers(["LASI", "RASI"])
selected = side_panel.get_selected_markers()
dlg = CreateAverageMarkerDialog(trial, preselected=selected)
assert dlg.combo_m1.currentText() == "LASI", f"Expected LASI, got {dlg.combo_m1.currentText()}"
assert dlg.combo_m2.currentText() == "RASI", f"Expected RASI, got {dlg.combo_m2.currentText()}"
assert dlg.txt_name.text() == "Avg_LASI_RASI", f"Expected Avg_LASI_RASI, got {dlg.txt_name.text()}"
print("CreateAverageMarkerDialog auto-population with selected markers verified.")

print("ALL MULTI-SELECT & 3D PICKING TESTS PASSED PERFECTLY!", flush=True)

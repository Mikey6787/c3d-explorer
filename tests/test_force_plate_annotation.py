import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial, ForcePlatformData
from gui.viewer_3d import Viewer3D

def test_force_plate_annotations():
    app = QApplication.instance() or QApplication(sys.argv)

    # Construct mock trial with 2 force platforms
    trial = C3DTrial(
        file_path="mock_fp.c3d",
        first_frame=1,
        last_frame=10,
        point_rate=100.0,
        point_frame_count=10,
        analog_rate=1000.0,
        analog_frame_count=100,
        analog_subsamples=10,
        markers={"LASI": np.zeros((10, 3)), "RASI": np.zeros((10, 3))}
    )

    # FP 1
    fp1 = ForcePlatformData(
        id=1,
        type=2,
        corners=np.array([
            [0, 500, 500, 0],
            [0, 0, 600, 600],
            [0, 0, 0, 0]
        ], dtype=float),
        origin=np.array([250, 300, 0], dtype=float)
    )
    # FP 2
    fp2 = ForcePlatformData(
        id=2,
        type=2,
        corners=np.array([
            [600, 1100, 1100, 600],
            [0, 0, 600, 600],
            [0, 0, 0, 0]
        ], dtype=float),
        origin=np.array([850, 300, 0], dtype=float)
    )
    trial.force_platforms = [fp1, fp2]

    # Initialize Viewer3D
    viewer = Viewer3D()
    viewer.load_trial(trial)

    # Verify plate labels created
    assert len(viewer.plate_label_items) == 2, f"Expected 2 plate label items, got {len(viewer.plate_label_items)}"
    assert viewer.plate_label_items[0].text == "FP 1", f"Expected 'FP 1', got '{viewer.plate_label_items[0].text}'"
    assert viewer.plate_label_items[1].text == "FP 2", f"Expected 'FP 2', got '{viewer.plate_label_items[1].text}'"

    # Verify colors have full alpha (255) so they are crisp and visible
    col0 = viewer.plate_label_items[0].color
    if isinstance(col0, QColor):
        assert col0.alpha() == 255, f"Expected alpha 255, got {col0.alpha()}"
    print("Force plate annotation labels and colors verified!")

    # Verify visibility toggling
    viewer.set_show_force_plates(False)
    for lbl in viewer.plate_label_items:
        assert not lbl.visible(), "Plate label should be hidden when force plates are hidden"
    for mesh in viewer.plate_mesh_items:
        assert not mesh.visible(), "Plate mesh should be hidden when force plates are hidden"

    viewer.set_show_force_plates(True)
    for lbl in viewer.plate_label_items:
        assert lbl.visible(), "Plate label should be visible when force plates are shown"
    for mesh in viewer.plate_mesh_items:
        assert mesh.visible(), "Plate mesh should be visible when force plates are shown"

    # Verify independent toggle from plate coordinate axes
    viewer.set_show_plate_axes(False)
    for lbl in viewer.plate_label_items:
        assert lbl.visible(), "Plate label should remain visible even if plate axes are toggled off"
    for axis_item in viewer.plate_axis_items:
        assert not axis_item.visible(), "Plate axis item should be hidden when plate axes are off"

    viewer.set_show_plate_axes(True)
    for axis_item in viewer.plate_axis_items:
        assert axis_item.visible(), "Plate axis item should be visible when plate axes are on"

    print("Force plate visibility logic verified successfully!")

if __name__ == "__main__":
    test_force_plate_annotations()
    print("ALL FORCE PLATE ANNOTATION TESTS PASSED PERFECTLY!")

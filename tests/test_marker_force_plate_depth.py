import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial, ForcePlatformData
from gui.viewer_3d import Viewer3D


def test_marker_force_plate_depth_hierarchy():
    app = QApplication.instance() or QApplication(sys.argv)
    viewer = Viewer3D()

    n_point = 10
    n_analog = 100

    fp = ForcePlatformData(
        id=1,
        type=2,
        corners=np.array([[0, 400, 400, 0], [0, 0, 600, 600], [0, 0, 0, 0]], dtype=float),
        origin=np.array([200, 300, 0], dtype=float),
        channels={"Ch1": np.zeros(n_analog)},
        forces=np.zeros((n_analog, 3), dtype=float)
    )

    trial = C3DTrial(
        file_path="mock_fp.c3d",
        first_frame=1,
        last_frame=10,
        point_rate=100.0,
        point_frame_count=n_point,
        analog_rate=1000.0,
        analog_frame_count=n_analog,
        analog_subsamples=10,
        markers={"LASI": np.zeros((10, 3))},
        force_platforms=[fp]
    )

    viewer.load_trial(trial)

    # 1. Check marker scatter depthValue
    marker_depth = viewer.marker_scatter.depthValue()
    assert marker_depth >= 200, f"Marker scatter depthValue should be >= 200, got {marker_depth}"

    # 2. Check force plate mesh depth values
    assert len(viewer.plate_mesh_items) > 0, "Force plate mesh items should be created"
    for item in viewer.plate_mesh_items:
        plate_depth = item.depthValue()
        assert plate_depth < marker_depth, (
            f"Force plate item depth ({plate_depth}) must be LESS than marker depth ({marker_depth}) "
            "so the plate renders first and does not alpha-blend on top of markers!"
        )

    # 3. Check force plate labels
    for lbl in viewer.plate_label_items:
        assert lbl.depthValue() < marker_depth, "Force plate label depth must be less than marker depth"

    # 4. Check GRF vector items
    for grf in viewer.grf_vector_items:
        assert grf.depthValue() < marker_depth, "GRF vector items must be rendered below markers"

    # 5. Check measurement items
    assert viewer.meas_line1.depthValue() < marker_depth
    assert viewer.meas_line2.depthValue() < marker_depth
    assert viewer.meas_label.depthValue() < marker_depth

    print("ALL MARKER AND FORCE PLATE DEPTH HIERARCHY TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_marker_force_plate_depth_hierarchy()

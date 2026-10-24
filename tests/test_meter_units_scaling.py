"""Unit test for meter vs millimeter scaling in 3D Viewport and analysis tools."""

import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial, ForcePlatformData
from gui.viewer_3d import Viewer3D
from gui.side_panel import SidePanel
from gui.marker_tools_dialog import MeasureDistanceDialog


def test_meter_units_scaling():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Create a mock trial with coordinates in METERS
    # Subject height ~1.8 m, distance between markers ~0.45 m
    n_frames = 10
    markers_m = {
        "LASI": np.tile(np.array([0.15, 0.80, 0.95]), (n_frames, 1)),
        "RASI": np.tile(np.array([-0.15, 0.80, 0.95]), (n_frames, 1)),
        "SACR": np.tile(np.array([0.00, 0.65, 0.98]), (n_frames, 1)),
    }
    # Force platform in meters: 0.60m x 0.40m
    corners_m = np.array([
        [-0.20,  0.20,  0.20, -0.20],
        [ 0.50,  0.50,  1.10,  1.10],
        [ 0.00,  0.00,  0.00,  0.00]
    ], dtype=float)

    fp_m = ForcePlatformData(
        id=1,
        type=2,
        corners=corners_m,
        origin=np.array([0.0, 0.8, 0.0], dtype=float),
        forces=np.tile(np.array([10.0, 5.0, 750.0]), (n_frames * 10, 1)),
        cop=np.tile(np.array([0.0, 0.8, 0.0]), (n_frames * 10, 1))
    )

    trial_meter = C3DTrial(
        file_path="mock_meter.c3d",
        first_frame=1,
        last_frame=10,
        point_rate=100.0,
        point_frame_count=n_frames,
        analog_rate=1000.0,
        analog_frame_count=n_frames * 10,
        analog_subsamples=10,
        markers=markers_m,
        marker_units="m",
        force_platforms=[fp_m]
    )

    viewer = Viewer3D()
    viewer.load_trial(trial_meter)

    # Verify unit scale is 0.001 (meter mode)
    assert viewer.unit_scale == 0.001, f"Expected unit_scale 0.001 for meter trial, got {viewer.unit_scale}"
    print("Unit scale for meter trial verified (0.001)!")

    # Verify camera framing in meters (distance should be ~2-5 meters, NOT 2600+ mm)
    cam_dist = viewer.gl_view.opts['distance']
    assert 2.0 <= cam_dist <= 15.0, f"Camera distance should be scaled for meters (~2.6-10.0), got {cam_dist}"
    print(f"Camera distance in meters correctly scaled: {cam_dist:.2f} m")

    # Verify 3D distance measurement in meters
    viewer.set_distance_measurement("LASI", "RASI", True)
    viewer.set_frame(0)
    assert viewer.meas_line1.visible()
    assert viewer.meas_label.visible()
    label_text = viewer.meas_label.text
    assert "0.300 m" in label_text, f"Expected 0.300 m, got {label_text}"
    print(f"3D distance label in meters verified: '{label_text}'")

    # Verify SidePanel force plate specs for meters
    panel = SidePanel()
    panel.load_trial(trial_meter)
    _, lbl_specs, lbl_data = panel.fp_widgets[0]
    assert "m" in lbl_specs.text()
    assert "0.600" in lbl_specs.text() or "0.400" in lbl_specs.text()
    print("SidePanel force plate specs in meters verified!")

    # 2. Switch to a mock trial with coordinates in MILLIMETERS
    markers_mm = {
        "LASI": np.tile(np.array([150.0, 800.0, 950.0]), (n_frames, 1)),
        "RASI": np.tile(np.array([-150.0, 800.0, 950.0]), (n_frames, 1)),
        "SACR": np.tile(np.array([0.0, 650.0, 980.0]), (n_frames, 1)),
    }
    corners_mm = corners_m * 1000.0
    fp_mm = ForcePlatformData(
        id=1,
        type=2,
        corners=corners_mm,
        origin=np.array([0.0, 800.0, 0.0], dtype=float),
        forces=np.tile(np.array([10.0, 5.0, 750.0]), (n_frames * 10, 1)),
        cop=np.tile(np.array([0.0, 800.0, 0.0]), (n_frames * 10, 1))
    )

    trial_mm = C3DTrial(
        file_path="mock_mm.c3d",
        first_frame=1,
        last_frame=10,
        point_rate=100.0,
        point_frame_count=n_frames,
        analog_rate=1000.0,
        analog_frame_count=n_frames * 10,
        analog_subsamples=10,
        markers=markers_mm,
        marker_units="mm",
        force_platforms=[fp_mm]
    )

    viewer.load_trial(trial_mm)

    # Verify unit scale is 1.0 (millimeter mode)
    assert viewer.unit_scale == 1.0, f"Expected unit_scale 1.0 for mm trial, got {viewer.unit_scale}"
    cam_dist_mm = viewer.gl_view.opts['distance']
    assert cam_dist_mm >= 2500.0, f"Camera distance should be in mm (>2500), got {cam_dist_mm}"
    print(f"Unit scale for mm trial verified (1.0), camera distance: {cam_dist_mm:.1f} mm")

    viewer.set_distance_measurement("LASI", "RASI", True)
    viewer.set_frame(0)
    label_text_mm = viewer.meas_label.text
    assert "300.0 mm" in label_text_mm, f"Expected 300.0 mm, got {label_text_mm}"
    print(f"3D distance label in mm verified: '{label_text_mm}'")

    print("\nALL METER UNITS SCALING TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_meter_units_scaling()

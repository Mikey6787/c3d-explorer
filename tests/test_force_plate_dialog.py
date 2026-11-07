"""Unit tests for the Force Plate tool dialog (Option 1: Automatic Shimba 1984, Option 2: Custom Corners, Offset & 6x6 Calibration Matrix)."""

import os
import sys
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from core.data_models import C3DTrial, ForcePlatformData
from gui.main_window import MainWindow
from gui.force_plate_dialog import ForcePlateDialog


def test_force_plate_menu_and_dialog():
    app = QApplication.instance() or QApplication(sys.argv)

    n_point = 20
    n_analog = 200
    analogs = {
        "Fx1": np.full(n_analog, 2.0, dtype=np.float32),
        "Fy1": np.full(n_analog, -1.5, dtype=np.float32),
        "Fz1": np.full(n_analog, 100.0, dtype=np.float32),
        "Mx1": np.full(n_analog, 50.0, dtype=np.float32),
        "My1": np.full(n_analog, -40.0, dtype=np.float32),
        "Mz1": np.full(n_analog, 10.0, dtype=np.float32),
    }

    corners = np.array([
        [400.0, 0.0, 0.0, 400.0],
        [600.0, 600.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0]
    ], dtype=np.float32)

    fp1 = ForcePlatformData(
        id=1,
        type=4,
        corners=corners,
        origin=np.array([0.0, 0.0, -40.0], dtype=np.float32),
        channels={f"Ch_{i+1}": analogs[k] for i, k in enumerate(["Fx1", "Fy1", "Fz1", "Mx1", "My1", "Mz1"])},
        cal_matrix=np.eye(6, dtype=np.float32),
        channel_names=["Fx1", "Fy1", "Fz1", "Mx1", "My1", "Mz1"]
    )

    trial = C3DTrial(
        file_path="test_fp_tool.c3d",
        first_frame=1,
        last_frame=n_point,
        point_rate=100.0,
        point_frame_count=n_point,
        analog_rate=1000.0,
        analog_frame_count=n_analog,
        analog_subsamples=10,
        markers={"RASI": np.zeros((n_point, 3), dtype=np.float32)},
        analogs=analogs,
        analog_units={k: "V" for k in analogs},
        force_platforms=[fp1]
    )

    mw = MainWindow()
    mw.trial = trial
    mw.viewer_3d.load_trial(trial)
    mw.side_panel.load_trial(trial)
    mw.plotter_widget.load_trial(trial)

    # 1. Verify 'Force Plate...' option exists in Tools menu
    tools_actions = [a.text() for m in mw.menuBar().actions() if "Tools" in m.text() for a in m.menu().actions()]
    assert any("Force Plate" in t for t in tools_actions), f"Expected 'Force Plate' under Tools, found: {tools_actions}"

    # 2. Open ForcePlateDialog and test Option 1: Automatic Calculation (Shimba 1984)
    mw.open_force_plate_dialog()
    dlg = mw.force_plate_dialog
    assert dlg is not None
    assert dlg.rb_auto.isChecked()
    assert dlg.apply_calculation() is True
    assert mw.trial.force_platforms[0].forces is not None
    assert mw.trial.force_platforms[0].forces.shape == (n_analog, 3)
    auto_fz = float(mw.trial.force_platforms[0].forces[0, 2])
    assert abs(auto_fz - 100.0) < 1e-3, f"Expected Fz ~ 100.0 N with identity matrix, got {auto_fz}"

    # 3. Test Option 2: Custom Configuration (Corners, Center/Corner Offset, and 6x6 Calibration Matrix)
    dlg.rb_custom.setChecked(True)

    # Set custom corners (500 x 800 mm plate)
    custom_corners = np.array([
        [500.0, 0.0, 0.0, 500.0],
        [800.0, 800.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0]
    ], dtype=np.float32)
    dlg.set_corners_array(custom_corners)

    # Shift coordinate system offset to Corner 1 using preset
    dlg.apply_corner_offset_preset(1)
    offset_vec = dlg.get_origin_offset()
    assert abs(offset_vec[0]) == 250.0 and abs(offset_vec[1]) == 400.0, f"Unexpected corner 1 offset: {offset_vec}"

    # Set 6x6 calibration matrix diagonal (Fx, Fy, Fz, Mx, My, Mz) to [2, 3, 5, 10, 10, 10]
    dlg.set_calibration_diagonal([2.0, 3.0, 5.0, 10.0, 10.0, 10.0])
    cal_mat = dlg.get_calibration_matrix()
    assert cal_mat.shape == (6, 6)
    assert np.allclose(np.diag(cal_mat), [2.0, 3.0, 5.0, 10.0, 10.0, 10.0])

    assert dlg.apply_calculation() is True
    updated_fp = mw.trial.force_platforms[0]
    assert np.allclose(updated_fp.corners, custom_corners)
    assert np.allclose(np.diag(updated_fp.cal_matrix), [2.0, 3.0, 5.0, 10.0, 10.0, 10.0])
    # Since Fz1 = 100.0 and Fz diagonal scale = 5.0, new Fz should be 500.0 N
    custom_fz = float(updated_fp.forces[0, 2])
    assert abs(custom_fz - 500.0) < 1e-2, f"Expected scaled Fz = 500.0 N, got {custom_fz}"

    # 4. Verify Undo / Redo works cleanly
    mw.undo_stack.undo()
    reverted_fz = float(mw.trial.force_platforms[0].forces[0, 2])
    assert abs(reverted_fz - 100.0) < 1e-2, f"Expected undo to revert Fz to 100.0 N, got {reverted_fz}"

    mw.undo_stack.redo()
    redone_fz = float(mw.trial.force_platforms[0].forces[0, 2])
    assert abs(redone_fz - 500.0) < 1e-2, f"Expected redo to restore Fz to 500.0 N, got {redone_fz}"

    # 5. Verify closing and reopening ForcePlateDialog remembers Manual calculation & user settings
    mw.trial._persist_qsettings = True
    dlg.spin_custom_threshold.setValue(25.5)
    dlg.set_origin_offset(12.5, -34.0, -45.0)
    dlg.close()

    # Reopen in same session
    mw.open_force_plate_dialog()
    dlg2 = mw.force_plate_dialog
    assert dlg2.rb_custom.isChecked(), "Expected Manual calculation mode to be remembered on reopen"
    assert abs(dlg2.spin_custom_threshold.value() - 25.5) < 1e-3
    assert np.allclose(dlg2.get_corners_array(), custom_corners)
    assert np.allclose(dlg2.get_origin_offset(), [12.5, -34.0, -45.0])
    assert np.allclose(np.diag(dlg2.get_calibration_matrix()), [2.0, 3.0, 5.0, 10.0, 10.0, 10.0])
    dlg2.close()

    # Simulate closing the app and reopening with a fresh C3DTrial loaded from disk
    fresh_fp1 = ForcePlatformData(
        id=1,
        type=4,
        corners=corners.copy(),
        origin=np.array([0.0, 0.0, -40.0], dtype=np.float32),
        channels={f"Ch_{i+1}": analogs[k] for i, k in enumerate(["Fx1", "Fy1", "Fz1", "Mx1", "My1", "Mz1"])},
        cal_matrix=np.eye(6, dtype=np.float32),
        channel_names=["Fx1", "Fy1", "Fz1", "Mx1", "My1", "Mz1"]
    )
    fresh_trial = C3DTrial(
        file_path="test_fp_tool.c3d",
        first_frame=1,
        last_frame=n_point,
        point_rate=100.0,
        point_frame_count=n_point,
        analog_rate=1000.0,
        analog_frame_count=n_analog,
        analog_subsamples=10,
        markers={"RASI": np.zeros((n_point, 3), dtype=np.float32)},
        analogs=analogs,
        analog_units={k: "V" for k in analogs},
        force_platforms=[fresh_fp1]
    )
    fresh_trial._persist_qsettings = True
    dlg3 = ForcePlateDialog(fresh_trial)
    assert dlg3.rb_custom.isChecked(), "Expected Manual calculation mode to be remembered across app restarts"
    assert abs(dlg3.spin_custom_threshold.value() - 25.5) < 1e-3
    assert np.allclose(dlg3.get_corners_array(), custom_corners)
    assert np.allclose(dlg3.get_origin_offset(), [12.5, -34.0, -45.0])
    assert np.allclose(np.diag(dlg3.get_calibration_matrix()), [2.0, 3.0, 5.0, 10.0, 10.0, 10.0])

    # Clean up test QSettings key so future runs start clean
    from PySide6.QtCore import QSettings
    QSettings("C3DExplorer", "C3DExplorer").remove("force_plate/user_settings_json")

    print("ALL FORCE PLATE DIALOG & CALCULATION TESTS PASSED!")


if __name__ == "__main__":
    test_force_plate_menu_and_dialog()


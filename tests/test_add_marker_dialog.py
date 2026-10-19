"""Tests for Add Marker dialog, coordinate file parsing (.txt, .csv, .xlsx), and Undo/Redo."""

import os
import sys
import tempfile
import numpy as np
import openpyxl
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from core.data_models import C3DTrial
from gui.marker_tools_dialog import parse_coordinates_file, AddMarkerDialog
from gui.main_window import MainWindow


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test coordinate file parsing across formats (.csv, .txt, .xlsx)
    with tempfile.TemporaryDirectory() as tmpdir:
        expected_frames = 50

        # A) Standard CSV without header
        csv_path = os.path.join(tmpdir, "markers_raw.csv")
        data_50 = np.random.randn(expected_frames, 3) * 100.0
        with open(csv_path, "w") as f:
            for row in data_50:
                f.write(f"{row[0]:.4f},{row[1]:.4f},{row[2]:.4f}\n")

        arr, err = parse_coordinates_file(csv_path, expected_frames)
        assert err is None, f"Failed parsing raw CSV: {err}"
        assert arr.shape == (50, 3)
        assert np.allclose(arr, data_50, atol=1e-3)
        print("Raw CSV parsing verified!")

        # B) CSV with header and European comma decimals
        csv_header_path = os.path.join(tmpdir, "markers_header.csv")
        with open(csv_header_path, "w") as f:
            f.write("X; Y; Z\n")
            for row in data_50:
                f.write(f"{str(row[0]).replace('.', ',')}; {str(row[1]).replace('.', ',')}; {str(row[2]).replace('.', ',')}\n")

        arr, err = parse_coordinates_file(csv_header_path, expected_frames)
        assert err is None, f"Failed parsing CSV with header & semicolon: {err}"
        assert arr.shape == (50, 3)
        print("CSV with header & semicolon verified!")

        # C) Text file with whitespace separation
        txt_path = os.path.join(tmpdir, "markers_space.txt")
        with open(txt_path, "w") as f:
            for row in data_50:
                f.write(f"{row[0]:.4f}  {row[1]:.4f}  {row[2]:.4f}\n")

        arr, err = parse_coordinates_file(txt_path, expected_frames)
        assert err is None, f"Failed parsing space-separated TXT: {err}"
        assert arr.shape == (50, 3)
        print("Space-separated TXT verified!")

        # D) Excel (.xlsx) file
        xlsx_path = os.path.join(tmpdir, "markers_excel.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Coord_X", "Coord_Y", "Coord_Z"])
        for row in data_50:
            ws.append([float(row[0]), float(row[1]), float(row[2])])
        wb.save(xlsx_path)

        arr, err = parse_coordinates_file(xlsx_path, expected_frames)
        assert err is None, f"Failed parsing Excel file: {err}"
        assert arr.shape == (50, 3)
        print("Excel (.xlsx) parsing verified!")

        # E) Frame count mismatch error check
        wrong_frames = 30
        arr, err = parse_coordinates_file(csv_path, wrong_frames)
        assert arr is None, "Should fail when frame count does not match"
        assert "Frame count mismatch" in err
        assert "50 frames" in err
        assert "30 frames" in err
        print("Frame count mismatch error verified!")

    # 2. Test AddMarkerDialog with a loaded trial
    trial = C3DTrial(
        file_path="mock.c3d",
        first_frame=1,
        last_frame=50,
        point_rate=100.0,
        point_frame_count=50,
        analog_rate=1000.0,
        analog_frame_count=500,
        analog_subsamples=10,
        markers={
            "L_HEEL": np.zeros((50, 3)),
            "R_HEEL": np.ones((50, 3))
        }
    )

    dlg = AddMarkerDialog(trial)
    assert dlg.expected_frames == 50
    assert dlg.txt_name.text() == "Marker_1"

    # Test color selection
    custom_color = QColor("#FF007F")
    dlg.selected_color = custom_color
    dlg._update_color_swatch()
    assert "#FF007F" in dlg.btn_color_swatch.styleSheet().upper()

    # Test fixed position creation
    dlg.radio_fixed.setChecked(True)
    dlg.spin_x.setValue(123.4)
    dlg.spin_y.setValue(567.8)
    dlg.spin_z.setValue(910.1)

    received = []
    dlg.markerAdded.connect(lambda name, data, col: received.append((name, data, col)))
    dlg._on_add_clicked()

    assert len(received) == 1, "Signal markerAdded should be emitted"
    name, data, col = received[0]
    assert name == "Marker_1"
    assert data.shape == (50, 3)
    assert np.allclose(data[0], [123.4, 567.8, 910.1])
    assert col.name().upper() == "#FF007F"
    dlg.close()
    print("AddMarkerDialog fixed position creation verified!")

    # 3. Test MainWindow integration and SidePanel Add button
    win = MainWindow()
    win.show()
    win.trial = trial
    win.playback.set_trial(trial.point_frame_count, trial.point_rate)
    win.side_panel.load_trial(trial)
    win.viewer_3d.load_trial(trial)
    win.undo_stack.clear()

    # Check SidePanel has Add button
    assert hasattr(win.side_panel, "btn_add"), "SidePanel must have btn_add button"
    assert win.side_panel.btn_add.text() == "Add..."
    assert not hasattr(win.side_panel, "btn_reset_color"), "btn_reset_color should be removed"

    # Trigger marker creation via MainWindow handler
    new_data = np.ones((50, 3), dtype=np.float32) * 50.0
    win._on_marker_added("TEST_CUSTOM", new_data, custom_color)

    assert "TEST_CUSTOM" in trial.markers, "New marker should be in trial.markers"
    assert win.viewer_3d.custom_marker_colors.get("TEST_CUSTOM") is not None
    assert win.undo_stack.canUndo(), "Undo stack should have Add Marker action"
    assert "TEST_CUSTOM" in win.undo_stack.undoText()

    # Test Undo
    win.undo_stack.undo()
    assert "TEST_CUSTOM" not in trial.markers, "Marker should be removed after undo"
    assert win.viewer_3d.custom_marker_colors.get("TEST_CUSTOM") is None

    # Test Redo
    win.undo_stack.redo()
    assert "TEST_CUSTOM" in trial.markers, "Marker should be restored after redo"
    assert win.viewer_3d.custom_marker_colors.get("TEST_CUSTOM") is not None

    win.close()
    print("MainWindow integration and Undo/Redo for added marker verified!")
    print("ALL ADD MARKER TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    run_tests()

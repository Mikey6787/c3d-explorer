import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QMenu
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QKeyEvent

# Mock modal QMenu.exec to prevent blocking in automated test
QMenu.exec = lambda *args, **kwargs: None

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial
from gui.side_panel import SidePanel
from gui.main_window import MainWindow
from gui.viewer_3d import Viewer3D
from gui.undo_commands import DeleteMarkerCommand, DeleteMarkersCommand


def test_marker_delete_flow():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Prepare Mock Trial
    markers = {
        "RASI": np.ones((50, 3)) * 10.0,
        "LASI": np.ones((50, 3)) * 20.0,
        "RPSI": np.ones((50, 3)) * 30.0,
        "LPSI": np.ones((50, 3)) * 40.0,
        "KNEE": np.ones((50, 3)) * 50.0,
    }
    trial = C3DTrial(
        file_path="mock.c3d",
        first_frame=1,
        last_frame=50,
        point_rate=100.0,
        point_frame_count=50,
        analog_rate=1000.0,
        analog_frame_count=500,
        analog_subsamples=10,
        markers=markers
    )

    # 2. Test SidePanel table setup and delete signals
    sp = SidePanel()
    sp.load_trial(trial)
    assert sp.markers_table.rowCount() == 5
    assert hasattr(sp, 'btn_delete'), "SidePanel must have a Delete button for markers"

    # Select single marker (row 0: KNEE or LASI, depending on sorting)
    sp.markers_table.selectRow(0)
    selected_single = sp.get_selected_markers()
    assert len(selected_single) == 1
    target_single = selected_single[0]

    single_received = []
    sp.deleteMarkerRequested.connect(lambda name: single_received.append(name))
    # Test clicking the Delete button directly
    sp.btn_delete.click()
    assert single_received == [target_single], f"Expected [{target_single}], got {single_received}"
    print("SidePanel single marker deletion via btn_delete.click() verified!")

    # Select multiple markers
    sp.markers_table.clearSelection()
    sp.select_markers(["RASI", "LASI"])
    selected_multi = sp.get_selected_markers()
    assert set(selected_multi) == {"RASI", "LASI"}

    multi_received = []
    sp.deleteMarkersRequested.connect(lambda names: multi_received.extend(names))
    # Test clicking the Delete button directly for multiple markers
    sp.btn_delete.click()
    assert set(multi_received) == {"RASI", "LASI"}
    print("SidePanel multi-marker deletion via btn_delete.click() verified!")

    # Test Delete keypress on markers table
    sp.markers_table.clearSelection()
    sp.select_markers(["RPSI"])
    single_received.clear()
    key_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    sp.markers_table.keyPressEvent(key_event)
    assert single_received == ["RPSI"]
    print("Markers table Key_Delete shortcut verified!")

    # 3. Test MainWindow Single Marker Delete Command & Undo/Redo
    mw = MainWindow()
    mw.trial = trial
    mw.side_panel.load_trial(trial)
    mw.viewer_3d.load_trial(trial)
    mw.undo_stack.clear()

    # Set custom color on RASI
    rasi_color = (1.0, 0.0, 0.5, 1.0)
    mw.viewer_3d.set_markers_custom_colors(["RASI"], rasi_color)
    mw.side_panel.set_markers_color_entries(["RASI"], QColor.fromRgbF(*rasi_color))

    # Single delete without confirmation popup
    mw.delete_marker("RASI", confirm=False)
    assert "RASI" not in trial.markers, "RASI should be deleted from trial.markers"
    assert mw.side_panel.markers_table.rowCount() == 4
    assert "RASI" not in [mw.side_panel.markers_table.item(r, 0).text() for r in range(mw.side_panel.markers_table.rowCount())]
    assert "RASI" not in mw.viewer_3d.custom_marker_colors

    # Undo single delete
    mw.undo_stack.undo()
    assert "RASI" in trial.markers, "RASI should be restored after undo"
    assert np.allclose(trial.markers["RASI"], 10.0), "Original coordinates restored"
    assert mw.side_panel.markers_table.rowCount() == 5
    assert mw.viewer_3d.custom_marker_colors.get("RASI") == rasi_color, "Custom color restored"

    # Redo single delete
    mw.undo_stack.redo()
    assert "RASI" not in trial.markers
    assert mw.side_panel.markers_table.rowCount() == 4
    print("Single marker DeleteMarkerCommand Undo/Redo verified!")

    # 4. Test MainWindow Batch Marker Delete Command & Undo/Redo
    mw.delete_marker(["LASI", "LPSI"], confirm=False)
    assert "LASI" not in trial.markers
    assert "LPSI" not in trial.markers
    assert len(trial.markers) == 2  # remaining: KNEE, RPSI
    assert mw.side_panel.markers_table.rowCount() == 2

    # Undo batch delete
    mw.undo_stack.undo()
    assert "LASI" in trial.markers
    assert "LPSI" in trial.markers
    assert len(trial.markers) == 4
    assert mw.side_panel.markers_table.rowCount() == 4

    # Redo batch delete
    mw.undo_stack.redo()
    assert "LASI" not in trial.markers
    assert "LPSI" not in trial.markers
    assert len(trial.markers) == 2
    print("Batch DeleteMarkersCommand Undo/Redo verified!")

    # 5. Test 3D Viewport Right-Click Picking and Context Menu Signal
    viewer = mw.viewer_3d
    viewer_cm_received = []
    # Disconnect MainWindow handler during test so modal menu.exec doesn't block headless execution
    viewer.markerContextMenuRequested.disconnect(mw._on_3d_marker_context_menu)
    viewer.markerContextMenuRequested.connect(lambda pos, names: viewer_cm_received.append((pos, names)))

    # Mock pick_marker_at returning 'KNEE'
    original_pick = viewer.pick_marker_at
    viewer.pick_marker_at = lambda x, y: "KNEE"

    click_point = QPoint(150, 200)
    viewer.handle_3d_right_click(150, 200, click_point)

    assert len(viewer_cm_received) == 1
    assert viewer_cm_received[0][0] == click_point
    assert viewer_cm_received[0][1] == ["KNEE"]
    assert viewer.selected_markers == ["KNEE"]
    print("3D Viewer right-click picking & context menu request verified!")

    viewer.pick_marker_at = original_pick

    mw.close()
    sp.close()
    print("ALL MARKER DELETION TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_marker_delete_flow()

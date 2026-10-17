import sys
import os
import tempfile
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent

from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
from core.data_models import C3DTrial, C3DEvent
from gui.timeline_widget import TimelineWidget
from gui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

def test_full_export_and_synchronization():
    print("Testing marker additions, renames, and events full synchronization...", flush=True)
    c3d_path = "/Users/mikey/Library/CloudStorage/OneDrive-UniversitätKoblenz/Koblenz/Reserach Projects/OpenSim Pipeline/Jumping/Sample data/MHJ/P01_PRE_L_REF.c3d"
    trial = C3DReader.read(c3d_path)
    
    # 1. Add a newly created marker
    new_marker_data = np.ones((trial.point_frame_count, 3)) * 555.5
    trial.markers["AVG_KNEE_NEW"] = new_marker_data
    
    # 2. Rename a marker
    old_name = "C07"
    assert old_name in trial.markers
    trial.markers["C07_RENAMED"] = trial.markers.pop(old_name)
    assert old_name not in trial.markers
    
    # 3. Add an event
    new_ev = C3DEvent(name="Contact", frame=45, time=45 / trial.point_rate, icon_color="#00FF00", context="Right")
    trial.events.append(new_ev)
    
    # Export full trial
    tmp_out = tempfile.mktemp(suffix=".c3d")
    try:
        C3DWriter.save_c3d(trial, tmp_out)
        
        # Read back
        reloaded = C3DReader.read(tmp_out)
        assert "AVG_KNEE_NEW" in reloaded.markers, "New marker not saved to C3D!"
        assert np.allclose(reloaded.markers["AVG_KNEE_NEW"][0], [555.5, 555.5, 555.5]), "New marker coordinates wrong!"
        assert "C07_RENAMED" in reloaded.markers, "Renamed marker not saved to C3D!"
        assert "C07" not in reloaded.markers, "Old marker name still present in C3D!"
        
        ev_names = [e.name for e in reloaded.events]
        assert any("Contact" in e for e in ev_names), f"Added event not in reloaded C3D events: {ev_names}"
        assert len(reloaded.force_platforms) == len(trial.force_platforms), f"Force platforms missing: expected {len(trial.force_platforms)}, got {len(reloaded.force_platforms)}"
        print("Full C3D export with new markers, renames, events, and force platforms passed!", flush=True)
    finally:
        if os.path.exists(tmp_out):
            os.remove(tmp_out)

def test_trimmed_c3d_export():
    print("Testing trimmed C3D export...", flush=True)
    c3d_path = "/Users/mikey/Library/CloudStorage/OneDrive-UniversitätKoblenz/Koblenz/Reserach Projects/OpenSim Pipeline/Jumping/Sample data/MHJ/P01_PRE_L_REF.c3d"
    trial = C3DReader.read(c3d_path)
    
    # Add newly created marker
    trial.markers["CUSTOM_MARKER"] = np.ones((trial.point_frame_count, 3)) * 888.0
    # Rename marker
    trial.markers["C07_EDITED"] = trial.markers.pop("C07")
    
    # Add an event inside trim range (frame 40) and outside (frame 120)
    ev_inside = C3DEvent(name="InsideEvent", frame=40, time=40 / trial.point_rate, icon_color="#00FF00")
    ev_outside = C3DEvent(name="OutsideEvent", frame=120, time=120 / trial.point_rate, icon_color="#FF0000")
    trial.events = [ev_inside, ev_outside]
    
    # Trim to frame 20 -> 69 (50 frames)
    trim_start = 20
    trim_end = 69
    expected_frames = trim_end - trim_start + 1  # 50
    nsf = max(1, trial.analog_subsamples)
    expected_analogs = expected_frames * nsf     # 500
    
    tmp_trimmed = tempfile.mktemp(suffix=".c3d")
    try:
        C3DWriter.save_c3d(trial, tmp_trimmed, start_frame=trim_start, end_frame=trim_end)
        
        reloaded = C3DReader.read(tmp_trimmed)
        assert reloaded.point_frame_count == expected_frames, f"Expected {expected_frames} frames, got {reloaded.point_frame_count}"
        assert reloaded.analog_frame_count == expected_analogs, f"Expected {expected_analogs} analog samples, got {reloaded.analog_frame_count}"
        assert "CUSTOM_MARKER" in reloaded.markers, "New marker missing from trimmed C3D!"
        assert "C07_EDITED" in reloaded.markers, "Renamed marker missing from trimmed C3D!"
        assert "C07" not in reloaded.markers, "Old marker should not be in trimmed C3D!"
        
        # Check event filtering and re-timing
        ev_names = [e.name for e in reloaded.events]
        assert any("InsideEvent" in e for e in ev_names), f"InsideEvent missing from trimmed C3D: {ev_names}"
        assert not any("OutsideEvent" in e for e in ev_names), f"OutsideEvent should have been excluded from trimmed C3D: {ev_names}"
        
        # Check Force Platforms in trimmed file
        assert len(reloaded.force_platforms) == len(trial.force_platforms), f"Force platforms missing from trimmed C3D: expected {len(trial.force_platforms)}, got {len(reloaded.force_platforms)}"
        assert reloaded.force_platforms[0].corners.shape == (3, 4)
        
        print("Trimmed C3D export with force platforms passed perfectly!", flush=True)
    finally:
        if os.path.exists(tmp_trimmed):
            os.remove(tmp_trimmed)

def test_timeline_trim_handles_and_ui():
    print("Testing timeline trim handles and mouse dragging...", flush=True)
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    timeline.set_trial_data(total_frames=100, point_rate=100.0, events=[])
    
    assert timeline.trim_start_frame == 0
    assert timeline.trim_end_frame == 99
    
    # 1. When main slider handler is at the same position as start handler (frame 0),
    # clicking on it must default to selecting the main playhead handler.
    assert timeline.current_frame == 0
    start_pt = timeline._trim_start_rect().center()
    press_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        start_pt, start_pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mousePressEvent(press_ev)
    assert timeline._drag_mode == 'playhead', f"Expected default selection 'playhead' when overlapping at frame 0, got {timeline._drag_mode}"
    timeline.mouseReleaseEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, start_pt, start_pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
    ))

    # Same check for end handle: when playhead is at frame 99 (same as trim_end)
    timeline.set_current_frame(99)
    end_pt = timeline._trim_end_rect().center()
    press_end_ov = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        end_pt, end_pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mousePressEvent(press_end_ov)
    assert timeline._drag_mode == 'playhead', f"Expected default selection 'playhead' when overlapping at frame 99, got {timeline._drag_mode}"
    timeline.mouseReleaseEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, end_pt, end_pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
    ))

    # 2. When playhead is moved away (e.g. frame 50), trim start handle can be dragged freely
    timeline.set_current_frame(50)
    timeline.mousePressEvent(press_ev)
    assert timeline._drag_mode == 'trim_start'
    
    target_start_x = timeline._frame_to_x(25)
    move_ev = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(target_start_x, start_pt.y()), QPointF(target_start_x, start_pt.y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseMoveEvent(move_ev)
    assert timeline.trim_start_frame == 25, f"Expected trim_start 25, got {timeline.trim_start_frame}"
    
    release_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(target_start_x, start_pt.y()), QPointF(target_start_x, start_pt.y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseReleaseEvent(release_ev)
    assert timeline._drag_mode is None
    
    # 3. Drag Trim End Handle from frame 99 to frame 75 (playhead is at frame 50)
    timeline.mousePressEvent(press_end_ov)
    assert timeline._drag_mode == 'trim_end'
    
    target_end_x = timeline._frame_to_x(75)
    move_end = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(target_end_x, end_pt.y()), QPointF(target_end_x, end_pt.y()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseMoveEvent(move_end)
    assert timeline.trim_end_frame == 75, f"Expected trim_end 75, got {timeline.trim_end_frame}"
    
    timeline.mouseReleaseEvent(release_ev)
    
    # Test shortcuts
    timeline.set_current_frame(30)
    key_i = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_I, Qt.KeyboardModifier.NoModifier, "i")
    timeline.keyPressEvent(key_i)
    assert timeline.trim_start_frame == 30, f"Expected trim_start 30 after Key_I, got {timeline.trim_start_frame}"
    
    timeline.set_current_frame(70)
    key_o = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_O, Qt.KeyboardModifier.NoModifier, "o")
    timeline.keyPressEvent(key_o)
    assert timeline.trim_end_frame == 70, f"Expected trim_end 70 after Key_O, got {timeline.trim_end_frame}"
    
    # Test reset
    timeline.reset_trim_range()
    assert timeline.trim_start_frame == 0
    assert timeline.trim_end_frame == 99
    print("Timeline trim handles and UI interactions verified!", flush=True)

if __name__ == "__main__":
    test_full_export_and_synchronization()
    test_trimmed_c3d_export()
    test_timeline_trim_handles_and_ui()
    print("ALL TESTS IN test_trim_and_export.py PASSED SUCCESSFULLY!", flush=True)

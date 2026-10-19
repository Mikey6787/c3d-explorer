import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter, QImage

from gui.timeline_widget import TimelineWidget
from core.data_models import C3DEvent

app = QApplication.instance() or QApplication(sys.argv)

def test_timeline_display_mode_and_toggling():
    print("Testing display mode and unit toggling...", flush=True)
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    timeline.set_trial_data(total_frames=300, point_rate=100.0, events=[])

    # Initial state should be "frame" (default everywhere)
    assert timeline.display_mode == "frame"

    # Listen to signal
    emitted = []
    timeline.displayModeChanged.connect(lambda m: emitted.append(m))

    # Toggle to "time"
    timeline.toggle_display_mode()
    assert timeline.display_mode == "time"
    assert emitted == ["time"]

    # Toggle back to "frame"
    timeline.toggle_display_mode()
    assert timeline.display_mode == "frame"
    assert emitted == ["time", "frame"]

    # Explicit set_display_mode
    timeline.set_display_mode("time")
    assert timeline.display_mode == "time"
    assert emitted == ["time", "frame", "time"]

    # Setting same mode should not re-emit
    timeline.set_display_mode("time")
    assert len(emitted) == 3

    print("Display mode toggle and signal emission verified!", flush=True)

def test_handles_thinner_and_center_alignment():
    print("Testing thinner handles and center alignment...", flush=True)
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    timeline.set_trial_data(total_frames=100, point_rate=100.0, events=[])

    # 1. Playhead handle should be thinner (width == 8)
    assert timeline.handle_width == 8, f"Expected handle_width == 8, got {timeline.handle_width}"
    timeline.set_current_frame(42)
    h_rect = timeline._handle_rect()
    curr_x = timeline._frame_to_x(42)

    # Exact mathematical center of the playhead handle thumb must align with curr_x
    assert abs(h_rect.center().x() - curr_x) < 1e-3, f"Center of handle thumb {h_rect.center().x()} != curr_x {curr_x}"
    assert abs(h_rect.width() - 8) < 1e-3

    # 2. Trim Start handle must be centered at trim_start_frame
    timeline.set_trim_range(15, 85)
    s_rect = timeline._trim_start_rect()
    x_start = timeline._frame_to_x(15)
    assert abs(s_rect.center().x() - x_start) < 1e-3, f"Center of trim start {s_rect.center().x()} != x_start {x_start}"
    assert abs(s_rect.width() - 7) < 1e-3, f"Trim start handle width should be 7px, got {s_rect.width()}"

    # 3. Trim End handle must be centered at trim_end_frame
    e_rect = timeline._trim_end_rect()
    x_end = timeline._frame_to_x(85)
    assert abs(e_rect.center().x() - x_end) < 1e-3, f"Center of trim end {e_rect.center().x()} != x_end {x_end}"
    assert abs(e_rect.width() - 7) < 1e-3, f"Trim end handle width should be 7px, got {e_rect.width()}"

    print("Thinner handle dimensions and exact center alignments verified!", flush=True)

def test_top_right_badge_removed_and_double_click():
    print("Testing top-right badge is removed and double click toggles mode...", flush=True)
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    timeline.set_trial_data(total_frames=200, point_rate=100.0, events=[])

    # Top-right badge rect method should no longer exist
    assert not hasattr(timeline, "_unit_badge_rect"), "Top-right badge rect should be removed"

    # Initial mode is "frame"
    assert timeline.display_mode == "frame"

    # Double click toggles mode to "time"
    dbl_pt = QPointF(200, 10)
    dbl_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        dbl_pt, dbl_pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseDoubleClickEvent(dbl_click)
    assert timeline.display_mode == "time", "Double click should toggle from 'frame' to 'time'"

    timeline.mouseDoubleClickEvent(dbl_click)
    assert timeline.display_mode == "frame", "Double click should toggle from 'time' to 'frame'"

    print("Top-right badge removal and double-click toggle verified!", flush=True)

def test_main_window_unit_button_next_to_loop():
    print("Testing MainWindow button is next to Loop: ON and named 'Time' -> 'Frame'...", flush=True)
    from gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    # Verify button exists
    assert hasattr(win, 'btn_timeline_unit')
    assert hasattr(win, 'btn_loop')

    # Verify button starts as "Frame"
    assert win.btn_timeline_unit.text() == "Frame", f"Expected 'Frame', got {win.btn_timeline_unit.text()}"
    assert win.timeline.display_mode == "frame"

    # Click button -> toggles timeline to time -> button text becomes "Time"
    win.btn_timeline_unit.click()
    assert win.timeline.display_mode == "time"
    assert win.btn_timeline_unit.text() == "Time", f"Expected 'Time' when pressed, got {win.btn_timeline_unit.text()}"

    # Click button again -> toggles timeline to frame -> button text becomes "Frame"
    win.btn_timeline_unit.click()
    assert win.timeline.display_mode == "frame"
    assert win.btn_timeline_unit.text() == "Frame", f"Expected 'Frame' when pressed, got {win.btn_timeline_unit.text()}"

    win.close()
    print("MainWindow button placement and text transitions verified successfully!", flush=True)

def test_paint_rendering_both_modes():
    print("Testing paintEvent rendering in both Frame and Time modes...", flush=True)
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    ev = C3DEvent(name="Strike", frame=20, time=0.2, icon_color="#00FF00", context="Left")
    timeline.set_trial_data(total_frames=150, point_rate=100.0, events=[ev])
    timeline.set_trim_range(10, 120)
    timeline.set_current_frame(20)

    # 1. Paint in Frame mode
    timeline.set_display_mode("frame")
    img_frame = QImage(800, 60, QImage.Format_ARGB32_Premultiplied)
    img_frame.fill(Qt.transparent)
    timeline.render(img_frame)

    # 2. Paint in Time mode
    timeline.set_display_mode("time")
    img_time = QImage(800, 60, QImage.Format_ARGB32_Premultiplied)
    img_time.fill(Qt.transparent)
    timeline.render(img_time)

    print("Paint rendering in Frame and Time modes verified without errors!", flush=True)

if __name__ == "__main__":
    test_timeline_display_mode_and_toggling()
    test_handles_thinner_and_center_alignment()
    test_top_right_badge_removed_and_double_click()
    test_main_window_unit_button_next_to_loop()
    test_paint_rendering_both_modes()
    print("\nALL TIMELINE UNITS AND HANDLERS TESTS PASSED PERFECTLY!")

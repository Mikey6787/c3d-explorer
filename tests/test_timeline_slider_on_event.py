import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from gui.timeline_widget import TimelineWidget
from core.data_models import C3DEvent

app = QApplication.instance() or QApplication(sys.argv)

def test_slider_on_event():
    timeline = TimelineWidget()
    timeline.resize(800, 60)
    
    # Create test events
    ev1 = C3DEvent(name="Event1", frame=50, time=0.5, icon_color="#FF0000", context="General")
    timeline.set_trial_data(total_frames=100, point_rate=100.0, events=[ev1])
    
    # 1. Position the slider EXACTLY on event frame (50)
    timeline.set_current_frame(50)
    assert timeline.current_frame == 50
    
    # Handle coordinates
    handle_rect = timeline._handle_rect()
    center_pt = handle_rect.center()
    
    # Verify handle hit test works
    assert timeline._is_on_handle(center_pt) is True, "Handle hit test failed on its own center"
    
    # 2. Simulate mouse press directly on the handle when it is exactly on the event
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        center_pt,
        center_pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    timeline.mousePressEvent(press_event)
    
    # Verify dragging is activated!
    assert timeline._is_dragging is True, "Dragging must be True when clicking handle on an event!"
    
    # 3. Simulate dragging to another frame (e.g. frame 80)
    target_x = timeline._frame_to_x(80)
    drag_pt = QPointF(target_x, center_pt.y())
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        drag_pt,
        drag_pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseMoveEvent(move_event)
    
    assert timeline.current_frame == 80, f"Expected current_frame == 80 after drag, got {timeline.current_frame}"
    
    # 4. Release mouse
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        drag_pt,
        drag_pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    timeline.mouseReleaseEvent(release_event)
    assert timeline._is_dragging is False, "Dragging must be False after release"
    
    # 5. Test clicking on the top event badge (y <= 22) at frame 50
    ev_x = timeline._frame_to_x(50)
    badge_pt = QPointF(ev_x, 10)  # y=10 is on the top badge
    badge_clicked = []
    timeline.eventClicked.connect(lambda ev: badge_clicked.append(ev))
    
    badge_press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        badge_pt,
        badge_pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    timeline.mousePressEvent(badge_press)
    assert len(badge_clicked) == 1, "Clicking top badge should emit eventClicked"
    assert badge_clicked[0] == ev1
    assert timeline.current_frame == 50
    assert timeline._is_dragging is True, "Dragging should also be active after clicking badge so user can drag away"

    # 6. Test right-click on an event on the slider bar to Set Trim Start and Set Trim End
    ev_fs = C3DEvent(name="Foot_Strike", frame=25, time=0.25, icon_color="#00FF00", context="Right")
    ev_fo = C3DEvent(name="Foot_Off", frame=75, time=0.75, icon_color="#0000FF", context="Right")
    timeline.set_trial_data(total_frames=100, point_rate=100.0, events=[ev_fs, ev_fo])

    # Initial trim is full trial (0 to 99)
    assert timeline.trim_start_frame == 0
    assert timeline.trim_end_frame == 99

    # Right-click on Foot_Strike on slider bar track (y=32), with slight mouse click jitter of +3 pixels
    x_fs = timeline._frame_to_x(25)
    click_pos_fs = QPointF(x_fs + 3.0, 32.0).toPoint()
    menu_fs = timeline.create_context_menu(click_pos_fs)
    
    # Find Trim Start action
    trim_in_action = None
    for action in menu_fs.actions():
        if "Set Trim Start Here" in action.text():
            trim_in_action = action
            break
    assert trim_in_action is not None, "Set Trim Start Here action not found in context menu"
    assert "Frame 26" in trim_in_action.text(), f"Expected Frame 26 (1-based for frame 25), got: {trim_in_action.text()}"
    
    # Trigger the action
    trim_in_action.trigger()
    assert timeline.trim_start_frame == 25, f"Expected trim_start_frame == 25, got {timeline.trim_start_frame}"

    # Right-click on Foot_Off on slider bar track (y=30), with slight mouse click jitter of -4 pixels
    x_fo = timeline._frame_to_x(75)
    click_pos_fo = QPointF(x_fo - 4.0, 30.0).toPoint()
    menu_fo = timeline.create_context_menu(click_pos_fo)

    trim_out_action = None
    for action in menu_fo.actions():
        if "Set Trim End Here" in action.text():
            trim_out_action = action
            break
    assert trim_out_action is not None, "Set Trim End Here action not found in context menu"
    assert "Frame 76" in trim_out_action.text(), f"Expected Frame 76 (1-based for frame 75), got: {trim_out_action.text()}"

    # Trigger the action
    trim_out_action.trigger()
    assert timeline.trim_end_frame == 75, f"Expected trim_end_frame == 75, got {timeline.trim_end_frame}"

    # Verify both trim start and trim end exactly match events
    assert timeline.trim_start_frame == ev_fs.frame == 25
    assert timeline.trim_end_frame == ev_fo.frame == 75

    print("ALL SLIDER ON EVENT TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_slider_on_event()

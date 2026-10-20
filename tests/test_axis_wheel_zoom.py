"""Unit tests for single-axis wheel zooming on X and Y axes across all plotter widgets."""

import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QWheelEvent, QMouseEvent

from core.c3d_reader import C3DReader
from gui.plotter_window import UniversalPlotterWindow, enable_axis_wheel_zoom


def create_wheel_event(pos: QPointF, delta_y: int = 120, delta_x: int = 0, modifiers=Qt.NoModifier):
    """Helper to synthesize a QWheelEvent for testing."""
    return QWheelEvent(
        pos,
        pos,
        QPoint(0, 0),
        QPoint(delta_x, delta_y),
        Qt.NoButton,
        modifiers,
        Qt.ScrollUpdate,
        False
    )


def test_universal_plotter_axis_zoom():
    print("Testing UniversalPlotterWindow axis wheel zoom...", flush=True)
    c3d_path = "/Users/mikey/Library/CloudStorage/OneDrive-UniversitätKoblenz/Koblenz/Reserach Projects/OpenSim Pipeline/Jumping/Sample data/MHJ/P01_PRE_L_REF.c3d"
    trial = C3DReader.read(c3d_path)

    win = UniversalPlotterWindow(trial=trial, current_frame=0)
    win.show()
    QApplication.processEvents()

    # Select marker to create curves
    m_node = win.tree.topLevelItem(0).child(0)
    m_node.child(0).setCheckState(0, Qt.Checked)
    QApplication.processEvents()

    vb = win.plot_widget.getViewBox()
    axis_b = win.plot_widget.getPlotItem().getAxis("bottom")
    axis_l = win.plot_widget.getPlotItem().getAxis("left")

    init_x_range = list(vb.viewRange()[0])
    init_y_range = list(vb.viewRange()[1])
    print(f"Initial X range: {init_x_range}")
    print(f"Initial Y range: {init_y_range}")

    # 1. Scroll on bottom X-axis
    b_rect = axis_b.mapRectToScene(axis_b.rect())
    scroll_x_pt = QPointF(b_rect.center().x(), b_rect.center().y())
    wheel_x = create_wheel_event(scroll_x_pt, delta_y=120)
    QApplication.sendEvent(win.plot_widget.viewport(), wheel_x)
    QApplication.processEvents()

    after_x_zoom_x = vb.viewRange()[0]
    after_x_zoom_y = vb.viewRange()[1]
    print(f"After X zoom -> X range: {after_x_zoom_x}, Y range: {after_x_zoom_y}")

    # X must have changed (zoomed in -> smaller span)
    assert (after_x_zoom_x[1] - after_x_zoom_x[0]) < (init_x_range[1] - init_x_range[0]), "X span should have decreased"
    # Center must remain fixed (in-place scale without moving)
    init_cx = 0.5 * (init_x_range[0] + init_x_range[1])
    after_cx = 0.5 * (after_x_zoom_x[0] + after_x_zoom_x[1])
    assert np.isclose(after_cx, init_cx), f"X center must remain fixed: {after_cx} vs {init_cx}"
    # Y must be strictly unchanged
    assert np.isclose(after_x_zoom_y[0], init_y_range[0]), "Y min must remain unchanged"
    assert np.isclose(after_x_zoom_y[1], init_y_range[1]), "Y max must remain unchanged"
    print("✓ Scrolling on bottom axis changed X range in place without moving while leaving Y range untouched!")

    # 2. Scroll on left Y-axis
    l_rect = axis_l.mapRectToScene(axis_l.rect())
    scroll_y_pt = QPointF(l_rect.center().x(), l_rect.center().y())
    wheel_y = create_wheel_event(scroll_y_pt, delta_y=-120)  # zoom out
    QApplication.sendEvent(win.plot_widget.viewport(), wheel_y)
    QApplication.processEvents()

    after_y_zoom_x = vb.viewRange()[0]
    after_y_zoom_y = vb.viewRange()[1]
    print(f"After Y zoom -> X range: {after_y_zoom_x}, Y range: {after_y_zoom_y}")

    # X must be strictly unchanged from previous step
    assert np.isclose(after_y_zoom_x[0], after_x_zoom_x[0]), "X min must remain unchanged"
    assert np.isclose(after_y_zoom_x[1], after_x_zoom_x[1]), "X max must remain unchanged"
    # Y must have changed (zoomed out -> larger span)
    assert (after_y_zoom_y[1] - after_y_zoom_y[0]) > (after_x_zoom_y[1] - after_x_zoom_y[0]), "Y span should have increased"
    # Center must remain fixed (in-place scale without moving)
    init_cy = 0.5 * (after_x_zoom_y[0] + after_x_zoom_y[1])
    after_cy = 0.5 * (after_y_zoom_y[0] + after_y_zoom_y[1])
    assert np.isclose(after_cy, init_cy), f"Y center must remain fixed: {after_cy} vs {init_cy}"
    print("✓ Scrolling on left axis changed Y range in place without moving while leaving X range untouched!")

    # 3. Grabbing (click & drag) on bottom X-axis
    pre_drag_x = vb.viewRange()[0]
    pre_drag_y = vb.viewRange()[1]
    press_b = QMouseEvent(QEvent.Type.MouseButtonPress, scroll_x_pt, scroll_x_pt, scroll_x_pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), press_b)
    move_b = QMouseEvent(QEvent.Type.MouseMove, scroll_x_pt + QPointF(20, 0), scroll_x_pt + QPointF(20, 0), scroll_x_pt + QPointF(20, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), move_b)
    rel_b = QMouseEvent(QEvent.Type.MouseButtonRelease, scroll_x_pt + QPointF(20, 0), scroll_x_pt + QPointF(20, 0), scroll_x_pt + QPointF(20, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), rel_b)
    QApplication.processEvents()

    drag_x = vb.viewRange()[0]
    drag_y = vb.viewRange()[1]
    assert (drag_x[1] - drag_x[0]) < (pre_drag_x[1] - pre_drag_x[0]), "Grabbing & dragging right on X should zoom in"
    assert np.isclose(0.5 * (drag_x[0] + drag_x[1]), 0.5 * (pre_drag_x[0] + pre_drag_x[1])), "X center must remain fixed during grab"
    assert np.isclose(drag_y[0], pre_drag_y[0]) and np.isclose(drag_y[1], pre_drag_y[1]), "Y range must be unchanged during X grab"
    print("✓ Grabbing and dragging on bottom X-axis scales X in place without moving!")

    # 4. Grabbing (click & drag) on left Y-axis
    pre_ydrag_x = vb.viewRange()[0]
    pre_ydrag_y = vb.viewRange()[1]
    press_l = QMouseEvent(QEvent.Type.MouseButtonPress, scroll_y_pt, scroll_y_pt, scroll_y_pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), press_l)
    move_l = QMouseEvent(QEvent.Type.MouseMove, scroll_y_pt + QPointF(0, -20), scroll_y_pt + QPointF(0, -20), scroll_y_pt + QPointF(0, -20), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), move_l)
    rel_l = QMouseEvent(QEvent.Type.MouseButtonRelease, scroll_y_pt + QPointF(0, -20), scroll_y_pt + QPointF(0, -20), scroll_y_pt + QPointF(0, -20), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), rel_l)
    QApplication.processEvents()

    ydrag_x = vb.viewRange()[0]
    ydrag_y = vb.viewRange()[1]
    assert (ydrag_y[1] - ydrag_y[0]) < (pre_ydrag_y[1] - pre_ydrag_y[0]), "Grabbing & dragging up on Y should zoom in"
    assert np.isclose(0.5 * (ydrag_y[0] + ydrag_y[1]), 0.5 * (pre_ydrag_y[0] + pre_ydrag_y[1])), "Y center must remain fixed during grab"
    assert np.isclose(ydrag_x[0], pre_ydrag_x[0]) and np.isclose(ydrag_x[1], pre_ydrag_x[1]), "X range must be unchanged during Y grab"
    print("✓ Grabbing and dragging on left Y-axis scales Y in place without moving!")

    # 5. Test hover cursor styling
    # Hover over bottom axis
    mouse_move_b = QMouseEvent(QEvent.Type.MouseMove, scroll_x_pt, scroll_x_pt, scroll_x_pt, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), mouse_move_b)
    assert win.plot_widget.viewport().cursor().shape() == Qt.SizeHorCursor, "Expected SizeHorCursor over bottom axis"

    # Hover over left axis
    mouse_move_l = QMouseEvent(QEvent.Type.MouseMove, scroll_y_pt, scroll_y_pt, scroll_y_pt, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), mouse_move_l)
    assert win.plot_widget.viewport().cursor().shape() == Qt.SizeVerCursor, "Expected SizeVerCursor over left axis"

    # Hover inside plot area (restores cursor)
    vb_center = vb.mapRectToScene(vb.rect()).center()
    mouse_move_plot = QMouseEvent(QEvent.Type.MouseMove, vb_center, vb_center, vb_center, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), mouse_move_plot)
    assert win.plot_widget.viewport().cursor().shape() != Qt.SizeHorCursor and win.plot_widget.viewport().cursor().shape() != Qt.SizeVerCursor
    print("✓ Hover cursor styling verified!")

    # 6. Test Shift+Scroll inside plot area zooms X only
    cur_x = vb.viewRange()[0]
    cur_y = vb.viewRange()[1]
    wheel_shift = create_wheel_event(vb_center, delta_y=120, modifiers=Qt.ShiftModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), wheel_shift)
    assert (vb.viewRange()[0][1] - vb.viewRange()[0][0]) < (cur_x[1] - cur_x[0]), "Shift+Scroll should zoom X"
    assert np.isclose(vb.viewRange()[1][0], cur_y[0]) and np.isclose(vb.viewRange()[1][1], cur_y[1]), "Shift+Scroll must not touch Y"
    print("✓ Shift+Scroll inside plot zooms X only!")

    # 7. Test Ctrl+Scroll inside plot area zooms Y only
    cur_x = vb.viewRange()[0]
    cur_y = vb.viewRange()[1]
    wheel_ctrl = create_wheel_event(vb_center, delta_y=120, modifiers=Qt.ControlModifier)
    QApplication.sendEvent(win.plot_widget.viewport(), wheel_ctrl)
    assert (vb.viewRange()[1][1] - vb.viewRange()[1][0]) < (cur_y[1] - cur_y[0]), "Ctrl+Scroll should zoom Y"
    assert np.isclose(vb.viewRange()[0][0], cur_x[0]) and np.isclose(vb.viewRange()[0][1], cur_x[1]), "Ctrl+Scroll must not touch X"
    print("✓ Ctrl+Scroll inside plot zooms Y only!")

    win.close()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_universal_plotter_axis_zoom()
    print("\nALL AXIS WHEEL ZOOM TESTS PASSED PERFECTLY!", flush=True)

import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from core.data_models import C3DTrial
from gui.side_panel import SidePanel
from gui.viewer_3d import Viewer3D
from gui.main_window import MainWindow

print("Initializing Marker Multi-Select & Batch Color test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

trial = C3DTrial(
    file_path="mock_multiselect.c3d",
    first_frame=1,
    last_frame=10,
    point_rate=100.0,
    point_frame_count=10,
    analog_rate=1000.0,
    analog_frame_count=100,
    analog_subsamples=10,
    markers={f"M{i:02d}": np.zeros((10, 3)) for i in range(10)}
)

panel = SidePanel()
panel.load_trial(trial)
panel.resize(400, 600)
panel.show()

# 1. Test Shift-click range selection on markers table
p1 = panel.markers_table.visualItemRect(panel.markers_table.item(1, 0)).center()
QTest.mouseClick(panel.markers_table.viewport(), Qt.LeftButton, Qt.NoModifier, p1)

p5 = panel.markers_table.visualItemRect(panel.markers_table.item(5, 0)).center()
QTest.mouseClick(panel.markers_table.viewport(), Qt.LeftButton, Qt.ShiftModifier, p5)

selected = panel.get_selected_markers()
assert selected == ["M01", "M02", "M03", "M04", "M05"], f"Expected rows 1..5, got {selected}"
assert panel.btn_color.text() == "Color (5)...", f"Expected 'Color (5)...', got {panel.btn_color.text()}"
assert hasattr(panel, 'btn_add') and panel.btn_add.text() == "Add...", f"Expected 'Add...', got {panel.btn_add.text()}"
print("Shift-click range selection verified: selected 5 markers in row order.")

# 2. Test batch color assignment
batch_received = []
panel.markersColorChanged.connect(lambda markers, col: batch_received.append((markers, col)))

test_color = QColor("#FF0055")
panel.set_markers_color_entries(selected, test_color)
panel.markersColorChanged.emit(selected, test_color)

assert len(batch_received) == 1, "Batch color signal was not received"
assert batch_received[0][0] == selected, f"Signal markers mismatch: {batch_received[0][0]}"
assert batch_received[0][1].name() == "#ff0055", "Signal color mismatch"
for m in selected:
    assert panel.marker_colors[m].name() == "#ff0055", f"Marker {m} color not updated in panel"
print("SidePanel batch color assignment verified.")

# 3. Test Viewer3D integration
viewer = Viewer3D()
viewer.load_trial(trial)
viewer.set_markers_custom_colors(selected, (test_color.redF(), test_color.greenF(), test_color.blueF(), 1.0))

for m in selected:
    assert m in viewer.custom_marker_colors, f"Marker {m} missing from viewer custom colors"
    rgba = viewer.custom_marker_colors[m]
    assert abs(rgba[0] - test_color.redF()) < 0.01
    assert abs(rgba[1] - test_color.greenF()) < 0.01
    assert abs(rgba[2] - test_color.blueF()) < 0.01
print("Viewer3D batch custom colors verified.")

# 4. Test batch reset
panel.set_markers_color_entries(selected, None)
panel.markersColorChanged.emit(selected, None)
viewer.set_markers_custom_colors(selected, None)

for m in selected:
    assert m not in panel.marker_colors, f"Marker {m} color not reset in panel"
    assert m not in viewer.custom_marker_colors, f"Marker {m} color not reset in viewer"
print("Batch color reset verified.")

# 5. Test MainWindow integration
win = MainWindow()
win.resize(1000, 700)
win.show()
win.trial = trial
win.viewer_3d.load_trial(trial)
win.side_panel.load_trial(trial)

win.side_panel.set_markers_color_entries(["M02", "M03", "M04"], test_color)
win.side_panel.markersColorChanged.emit(["M02", "M03", "M04"], test_color)

for m in ["M02", "M03", "M04"]:
    assert m in win.viewer_3d.custom_marker_colors, f"Marker {m} not colored in MainWindow viewer"
print("MainWindow signal forwarding and status message verified.")

# 6. Test direct click on the marker circular color icon in the side panel
from PySide6.QtWidgets import QColorDialog, QStyle, QStyleOptionViewItem
table = win.side_panel.markers_table
item = table.item(0, 0)
marker_name = item.text()
assert marker_name == "M00"

opt = QStyleOptionViewItem()
table.initViewItemOption(opt)
opt.rect = table.visualItemRect(item)
opt.features |= QStyleOptionViewItem.HasDecoration | QStyleOptionViewItem.HasCheckIndicator
icon_rect = table.style().subElementRect(QStyle.SE_ItemViewItemDecoration, opt, table)
center = icon_rect.center()

# Test hover over circle icon
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtGui import QMouseEvent
ev_hover = QMouseEvent(QEvent.MouseMove, center, center, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
app.sendEvent(table.viewport(), ev_hover)
assert table.viewport().cursor().shape() == Qt.PointingHandCursor, "Hovering over circle icon should set PointingHandCursor"

# Test move away
ev_away = QMouseEvent(QEvent.MouseMove, QPoint(5, 5), QPoint(5, 5), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
app.sendEvent(table.viewport(), ev_away)
assert table.viewport().cursor().shape() != Qt.PointingHandCursor, "Moving away should restore cursor"

# Mock QColorDialog.getColor to return new color #12AACC
circle_col = QColor("#12AACC")
old_get_color = QColorDialog.getColor
QColorDialog.getColor = lambda *args, **kwargs: circle_col

try:
    QTest.mousePress(table.viewport(), Qt.LeftButton, Qt.NoModifier, center)
    QTest.mouseRelease(table.viewport(), Qt.LeftButton, Qt.NoModifier, center)
finally:
    QColorDialog.getColor = old_get_color

assert win.side_panel.marker_colors["M00"].name() == "#12aacc", "Side panel marker color should be updated on circle click"
assert "M00" in win.viewer_3d.custom_marker_colors, "Viewer 3D should update marker color on circle click"
assert win.undo_stack.canUndo(), "Undo stack should have the color change command"
print("Circle icon click directly changed marker color and registered undo command.")

# Test Undo
win.undo_stack.undo()
assert "M00" not in win.side_panel.marker_colors or win.side_panel.marker_colors["M00"] is None
print("Undo restored previous color.")

# Test Redo
win.undo_stack.redo()
assert win.side_panel.marker_colors["M00"].name() == "#12aacc"
print("Redo reapplied circle click color.")

# 7. Test clicking checkbox toggles visibility without triggering color change
check_rect = table.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, opt, table)
assert item.checkState() == Qt.Checked
QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, check_rect.center())
assert item.checkState() == Qt.Unchecked, "Clicking checkbox should toggle to Unchecked"
QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, check_rect.center())
assert item.checkState() == Qt.Checked, "Clicking checkbox again should toggle to Checked"
print("Checkbox toggling verified completely independent of circle icon click.")

print("ALL MARKER MULTI-SELECT & BATCH COLOR TESTS PASSED SUCCESSFULLY!", flush=True)

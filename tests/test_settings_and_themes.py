import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from app import MainWindow
from gui.theme import get_theme_names, get_theme
from gui.settings_dialog import SettingsDialog

print("Initializing Settings and Themes test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

win = MainWindow()
win.resize(1000, 700)

# 1. Test 5 Themes availability and switching
theme_names = get_theme_names()
assert len(theme_names) == 5, f"Expected 5 themes, got {len(theme_names)}: {theme_names}"
print(f"5 Built-in themes found: {theme_names}")

for name in theme_names:
    theme_dict = get_theme(name)
    assert "qss" in theme_dict
    assert "viewport_bg" in theme_dict
    assert "plot_bg" in theme_dict
    win.apply_theme(name)
    assert win.current_theme_name == name
    print(f"Successfully applied theme: {name}")

# Revert to default Biomech Dark
win.apply_theme("Biomech Dark (Obsidian & Cyan)")

# 2. Test Coordinate System Axis Thickness & Visibility
viewer = win.viewer_3d
viewer.set_axis_line_width(4.5)
assert viewer.axis_line_width == 4.5
print("Set coordinate axis thickness to 4.5px verified.")

viewer.set_axis_length(450.0)
assert viewer.axis_length == 450.0
print("Set coordinate axis length to 450.0mm verified.")

# Test Global Axes Visibility Toggle
viewer.set_show_global_axes(False)
assert viewer.show_global_axes is False
for item in viewer.global_axis_items:
    assert item.visible() is False
print("Global axes hiding verified.")

viewer.set_show_global_axes(True)
assert viewer.show_global_axes is True
for item in viewer.global_axis_items:
    assert item.visible() is True
print("Global axes showing verified.")

# 3. Test SettingsDialog UI & collecting settings
cfg = {
    "theme": "Clinical Light (Clean Medical White)",
    "show_grid": True,
    "grid_spacing": 1000.0,
    "show_markers": True,
    "show_force_plates": True,
    "show_grf_vectors": True,
    "show_global_axes": True,
    "axis_line_width": 3.5,
    "axis_length": 400.0,
    "show_plate_axes": True,
    "marker_size": 8.0,
    "grf_vector_scale": 1.2,
    "grf_threshold_n": 20.0,
    "loop": False,
}
dlg = SettingsDialog(cfg, parent=win)
collected = dlg._collect_settings()

assert collected["theme"] == "Clinical Light (Clean Medical White)"
assert collected["axis_line_width"] == 3.5
assert collected["axis_length"] == 400.0
assert collected["show_global_axes"] is True
assert collected["marker_size"] == 8.0
assert collected["loop"] is False
print("SettingsDialog configuration collection verified.")

# 4. Test applying settings to MainWindow
win._apply_settings(collected)
assert win.current_theme_name == "Clinical Light (Clean Medical White)"
assert win.viewer_3d.axis_line_width == 3.5
assert win.viewer_3d.axis_length == 400.0
assert win.viewer_3d.marker_size == 8.0
assert win.playback.is_looping is False
print("MainWindow settings application verified.")

# 5. Test open_settings_dialog execution with initial_tab
from PySide6.QtCore import QTimer

def close_active_modal():
    for widget in app.topLevelWidgets():
        if isinstance(widget, SettingsDialog) and widget.isVisible():
            widget.accept()

# Test opening tab 0 (Visual Configurations)
QTimer.singleShot(100, close_active_modal)
win.open_settings_dialog(0)
print("open_settings_dialog(0) executed successfully.")

# Test opening tab 1 (Ground Reaction & Orientation)
QTimer.singleShot(100, close_active_modal)
win.open_settings_dialog(1)
print("open_settings_dialog(1) executed successfully.")

win.close()
print("ALL SETTINGS & THEMES TESTS PASSED SUCCESSFULLY!", flush=True)

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
    assert win.timeline.is_dark == theme_dict.get("is_dark", True)
    if not theme_dict.get("is_dark", True):
        assert win.timeline.bg_color.name().lower() == "#ffffff"
    print(f"Successfully applied theme: {name}")

# Revert to default Biomech Dark
win.apply_theme("Biomech Dark")

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
    "theme": "Clinical Light",
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
    "loop": False,
    "z_up": False,
    "ground_rotation": 90.0,
}
dlg = SettingsDialog(cfg, parent=win)
collected = dlg._collect_settings()

assert collected["theme"] == "Clinical Light"
assert collected["axis_line_width"] == 3.5
assert collected["axis_length"] == 400.0
assert collected["show_global_axes"] is True
assert collected["marker_size"] == 8.0
assert collected["loop"] is False
assert collected["z_up"] is False
assert collected["ground_rotation"] == 90.0
print("SettingsDialog configuration collection verified.")

# 4. Test applying settings to MainWindow
win._apply_settings(collected)
assert win.current_theme_name == "Clinical Light"
assert win.viewer_3d.axis_line_width == 3.5
assert win.viewer_3d.axis_length == 400.0
assert win.viewer_3d.marker_size == 8.0
assert win.playback.is_looping is False
assert win.viewer_3d.z_up is False
assert win.viewer_3d.ground_rotation == 90.0
# In Y-Up with 0 deg, Y points up [0, 0, 1]. With 90 deg rotation, Y points up [0, 0, 1] while X and Z rotate in horizontal plane
y_trans = win.viewer_3d.transform_point([0, 1, 0])
assert abs(y_trans[2] - 1.0) < 1e-3, f"Expected Y to point Up (Z=1), got {y_trans}"
print("MainWindow settings application & Y-Up orientation verified.")

# 5. Test Marker Color auto-switch on Theme change
# Applying light theme should automatically change default marker color to black
win.apply_theme("Clinical Light")
assert win.viewer_3d.marker_color == (0.0, 0.0, 0.0, 1.0), f"Expected black marker color on light theme, got {win.viewer_3d.marker_color}"
assert win.side_panel.default_marker_color.name().upper() == "#000000"
print("Light theme auto-switch marker to black verified.")

# Applying dark theme should revert black markers back to white
win.apply_theme("Biomech Dark")
assert win.viewer_3d.marker_color == (1.0, 1.0, 1.0, 1.0), f"Expected white marker color on dark theme, got {win.viewer_3d.marker_color}"
assert win.side_panel.default_marker_color.name().upper() == "#FFFFFF"
print("Dark theme auto-revert marker to white verified.")

# 6. Test SettingsDialog marker color picker and theme interaction
from PySide6.QtGui import QColor

dlg_custom = SettingsDialog({"theme": "Biomech Dark"}, parent=win)
# Test custom color setting
custom_purple = QColor(180, 50, 220)
dlg_custom._set_marker_color(custom_purple)
assert dlg_custom.combo_marker_color.currentText() == "Custom Color..."
assert abs(dlg_custom._marker_color_rgba[0] - custom_purple.redF()) < 1e-3
assert abs(dlg_custom._marker_color_rgba[1] - custom_purple.greenF()) < 1e-3
assert abs(dlg_custom._marker_color_rgba[2] - custom_purple.blueF()) < 1e-3
collected_custom = dlg_custom._collect_settings()
assert collected_custom["marker_color_name"] == "Custom Color..."
assert abs(collected_custom["marker_color"][0] - custom_purple.redF()) < 1e-3
print("SettingsDialog custom color picker verified.")

# Test GRF color presets and custom color picker
custom_teal = QColor(0, 220, 210)
dlg_custom._set_grf_color(custom_teal)
assert dlg_custom.combo_grf_color.currentText() == "Custom Color..."
assert abs(dlg_custom._grf_color_rgba[0] - custom_teal.redF()) < 1e-3
assert abs(dlg_custom._grf_color_rgba[1] - custom_teal.greenF()) < 1e-3
assert abs(dlg_custom._grf_color_rgba[2] - custom_teal.blueF()) < 1e-3
collected_custom = dlg_custom._collect_settings()
assert collected_custom["grf_color_name"] == "Custom Color..."
assert abs(collected_custom["grf_color"][0] - custom_teal.redF()) < 1e-3
print("SettingsDialog GRF custom color picker verified.")

# Test dialog theme change to light theme auto-switches marker to black
dlg_custom.combo_theme.setCurrentText("Clinical Light")
assert dlg_custom._marker_color_rgba[:3] == (0.0, 0.0, 0.0)
assert dlg_custom.combo_marker_color.currentText() == "Pitch Black"
print("SettingsDialog theme change to light auto-switches marker to black verified.")

# Test applying GRF color to MainWindow and Viewer3D
win._apply_settings({"grf_color": (0.95, 0.15, 0.15, 1.0), "grf_color_name": "Crimson Red"})
assert win.viewer_3d.grf_color == (0.95, 0.15, 0.15, 1.0)
print("MainWindow Viewer3D GRF color application verified.")

# 7. Test open_settings_dialog execution with initial_tab
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

# 8. Test settings persistence across application restarts
persist_test_cfg = {
    "theme": "Nordic Midnight",
    "marker_size": 14.0,
    "axis_line_width": 4.0,
    "z_up": False,
    "ground_rotation": 180.0,
    "loop": False,
    "default_speed": "0.5x",
    "marker_color": [0.0, 0.85, 0.95, 1.0],
    "grf_color": [1.0, 0.85, 0.0, 1.0],
}
win._apply_settings(persist_test_cfg, save_to_disk=True)
saved_raw = win.settings.value("user_settings_json")
assert saved_raw is not None, "Expected settings to be saved to QSettings"
print("Saved settings to QSettings verified.")

# Create a second MainWindow instance simulating user launching the app next time
win2 = MainWindow()
assert win2.current_theme_name == "Nordic Midnight", f"Expected Nordic Midnight, got {win2.current_theme_name}"
assert win2.viewer_3d.marker_size == 14.0
assert win2.viewer_3d.axis_line_width == 4.0
assert win2.viewer_3d.z_up is False
assert win2.viewer_3d.ground_rotation == 180.0
assert win2.playback.is_looping is False
assert win2.viewer_3d.marker_color == (0.0, 0.85, 0.95, 1.0)
assert win2.viewer_3d.grf_color == (1.0, 0.85, 0.0, 1.0)
print("Startup restoration of saved user settings as new default verified successfully!")

# Clean up settings key to restore factory defaults
win2.settings.remove("user_settings_json")
win2.close()

win.close()
print("ALL SETTINGS & THEMES TESTS PASSED SUCCESSFULLY!", flush=True)

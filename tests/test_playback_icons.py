"""Unit tests for custom playback toolbar icons and theme tinting."""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from gui.main_window import MainWindow

def test_playback_bar_icons():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()

    print("Verifying initial playback buttons and icons...")
    assert not window.btn_step_back.icon().isNull(), "btn_step_back should have a valid icon"
    assert not window.btn_play_pause.icon().isNull(), "btn_play_pause should have a valid icon"
    assert not window.btn_step_fwd.icon().isNull(), "btn_step_fwd should have a valid icon"

    # Verify button dimensions and properties
    assert window.btn_step_back.width() == 36
    assert window.btn_play_pause.width() == 46
    assert window.btn_step_fwd.width() == 36

    print("Verifying playback state change icon toggling...")
    # Simulate playing state
    window._on_playback_state_changed(True)
    assert not window.btn_play_pause.icon().isNull(), "Pause icon should be non-null"
    assert "Pause" in window.btn_play_pause.toolTip()

    # Simulate paused state
    window._on_playback_state_changed(False)
    assert not window.btn_play_pause.icon().isNull(), "Play icon should be non-null"
    assert "Play" in window.btn_play_pause.toolTip()

    print("Verifying theme switching updates icons...")
    # Apply Clinical Light theme
    window.apply_theme("Clinical Light (Clean Medical White)")
    assert not window.btn_step_back.icon().isNull(), "Icon should be valid in Clinical Light"
    assert not window.btn_play_pause.icon().isNull(), "Icon should be valid in Clinical Light"
    assert not window.btn_step_fwd.icon().isNull(), "Icon should be valid in Clinical Light"

    # Apply Biomech Dark theme
    window.apply_theme("Biomech Dark (Obsidian & Cyan)")
    assert not window.btn_step_back.icon().isNull(), "Icon should be valid in Biomech Dark"
    assert not window.btn_play_pause.icon().isNull(), "Icon should be valid in Biomech Dark"
    assert not window.btn_step_fwd.icon().isNull(), "Icon should be valid in Biomech Dark"

    window.close()
    print("ALL PLAYBACK ICON TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_playback_bar_icons()

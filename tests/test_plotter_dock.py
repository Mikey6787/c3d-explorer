import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication, QDockWidget
from PySide6.QtCore import Qt

from core.data_models import C3DTrial, ForcePlatformData
from gui.main_window import MainWindow
from gui.plotter_window import UniversalPlotter, UniversalPlotterWindow


def test_plotter_dock_functionality():
    print("Initializing Plotter Dock & Panel integration test...", flush=True)
    app = QApplication.instance() or QApplication(sys.argv)

    # Prepare mock trial
    n_frames = 80
    t = np.linspace(0, 1.0, n_frames)
    markers = {
        "RASI": np.column_stack([np.sin(2 * np.pi * t) * 50.0, np.cos(2 * np.pi * t) * 30.0, t * 100.0]),
        "LASI": np.column_stack([np.cos(2 * np.pi * t) * 45.0, np.sin(2 * np.pi * t) * 25.0, t * 90.0]),
    }
    trial = C3DTrial(
        file_path="mock_dock_test.c3d",
        first_frame=1,
        last_frame=n_frames,
        point_rate=100.0,
        point_frame_count=n_frames,
        analog_rate=1000.0,
        analog_frame_count=n_frames * 10,
        analog_subsamples=10,
        markers=markers
    )

    # 1. Initialize MainWindow
    mw = MainWindow()
    mw.show()
    mw.trial = trial
    mw.timeline.set_trial_data(n_frames, 100.0, [])
    mw.plotter_widget.load_trial(trial)

    # Verify dock structure
    assert hasattr(mw, "dock_plotter"), "MainWindow must have dock_plotter"
    assert mw.dock_plotter.windowTitle() == "Plotter"
    assert isinstance(mw.dock_plotter.widget(), UniversalPlotter), "Dock widget must be UniversalPlotter"
    assert mw.plotter_widget.dock_widget == mw.dock_plotter, "Plotter widget must reference dock_plotter"
    print("MainWindow Plotter dock initialization verified!")

    # 2. Test Detach Window (Float) and Attach to App (Dock)
    # Initially docked
    assert not mw.dock_plotter.isFloating()
    assert mw.plotter_widget.btn_dock_toggle.text() == "Detach Window"

    # Click Detach Window button
    mw.plotter_widget.btn_dock_toggle.click()
    assert mw.dock_plotter.isFloating(), "Clicking Detach Window should float the dock"
    assert mw.plotter_widget.btn_dock_toggle.text() == "Attach to App"
    print("Detach Window button successfully detached plotter into a floating window!")

    # Click Attach to App button
    mw.plotter_widget.btn_dock_toggle.click()
    assert not mw.dock_plotter.isFloating(), "Clicking Attach to App should re-dock the plotter"
    assert mw.plotter_widget.btn_dock_toggle.text() == "Detach Window"
    print("Attach to App button successfully re-docked plotter into the main window!")

    # 3. Test open_plotter_window reveals dock
    mw.dock_plotter.hide()
    assert not mw.dock_plotter.isVisible()
    mw.open_plotter_window()
    assert mw.dock_plotter.isVisible(), "open_plotter_window must show dock_plotter"
    print("open_plotter_window successfully revealed plotter dock!")

    # 4. Test marker plotting in Plotter dock
    mw.plot_marker("RASI")
    assert "RASI (X)" in mw.plotter_widget.active_curves
    assert "RASI (Y)" in mw.plotter_widget.active_curves
    assert "RASI (Z)" in mw.plotter_widget.active_curves
    print("Plotting marker RASI in Plotter dock verified!")

    # 5. Test multi-marker plotting in Plotter dock
    mw.plot_markers(["RASI", "LASI"])
    assert len(mw.plotter_widget.active_curves) == 6
    print("Plotting multiple markers in Plotter dock verified!")

    # 6. Test custom curve plotting in Plotter dock
    custom_y = np.linspace(10, 50, n_frames)
    mw._on_plot_custom_curve_requested("Test Custom Angle", custom_y)
    assert "Test Custom Angle" in mw.plotter_widget.active_curves
    print("Custom curve plotting in Plotter dock verified!")

    # 7. Test distance plotting in Plotter dock
    mw.plot_marker_distance("RASI", "LASI")
    assert any("Distance" in k for k in mw.plotter_widget.active_curves.keys())
    print("Distance curve plotting in Plotter dock verified!")

    # 8. Test frame cursor synchronization
    mw.playback.set_frame(25)
    assert mw.plotter_widget.current_frame == 25
    print("Frame synchronization between timeline/playback and Plotter dock verified!")

    # 9. Test theme application
    mw.apply_theme("Biomech Dark (Obsidian & Cyan)")
    bg = mw.plotter_widget.plot_widget.backgroundBrush().color().name().upper()
    assert bg in ("#151720", "#1E222D", "#0F172A", "#18181B")
    print("Theme styling on Plotter dock verified!")

    # Cleanup
    mw.dock_plotter.close()
    mw.close()
    print("\nALL PLOTTER DOCK & PANEL TESTS PASSED PERFECTLY!", flush=True)


if __name__ == "__main__":
    test_plotter_dock_functionality()

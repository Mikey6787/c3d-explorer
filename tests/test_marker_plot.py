import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial
from gui.side_panel import SidePanel
from gui.main_window import MainWindow
from gui.plotter_window import UniversalPlotterWindow


def test_marker_plot_flow():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Prepare Mock Trial
    n_frames = 100
    t = np.linspace(0, 1.0, n_frames)
    markers = {
        "RASI": np.column_stack([np.sin(2 * np.pi * t) * 50.0, np.cos(2 * np.pi * t) * 30.0, t * 100.0]),
        "LASI": np.column_stack([np.cos(2 * np.pi * t) * 45.0, np.sin(2 * np.pi * t) * 25.0, t * 90.0]),
        "RPSI": np.column_stack([np.sin(4 * np.pi * t) * 20.0, np.cos(4 * np.pi * t) * 15.0, t * 80.0]),
    }
    trial = C3DTrial(
        file_path="mock_plot.c3d",
        first_frame=1,
        last_frame=n_frames,
        point_rate=100.0,
        point_frame_count=n_frames,
        analog_rate=1000.0,
        analog_frame_count=n_frames * 10,
        analog_subsamples=10,
        markers=markers
    )

    # 2. Test SidePanel Context Menu Creation & Plot Action
    sp = SidePanel()
    sp.load_trial(trial)
    assert sp.markers_table.rowCount() == 3

    # Test 2a: Single marker context menu creation and plot trigger
    sp.markers_table.selectRow(0)
    selected = sp.get_selected_markers()
    assert len(selected) == 1
    target_name = selected[0]

    single_plot_requested = []
    sp.plotMarkerRequested.connect(lambda name: single_plot_requested.append(name))

    menu1, actions1 = sp.create_marker_context_menu([target_name], target_name)
    assert menu1 is not None
    action_texts1 = [a.text() for a in menu1.actions() if a.text()]
    assert any(t.startswith(f"Plot '{target_name}' (X, Y, Z)") for t in action_texts1), \
        f"Expected Plot action in {action_texts1}"
    assert "act_plot" in actions1
    assert actions1["act_plot"].text() == f"Plot '{target_name}' (X, Y, Z)"

    # Trigger action choice directly
    sp._handle_marker_context_menu_choice(actions1["act_plot"], actions1)
    assert single_plot_requested == [target_name], f"Expected [{target_name}], got {single_plot_requested}"
    print(f"SidePanel single marker plot action for '{target_name}' verified!")

    # Test 2b: Multi-marker context menu creation and plot trigger
    sp.select_markers(["RASI", "LASI"])
    multi_plot_requested = []
    distance_requested = []
    sp.plotMarkersRequested.connect(lambda names: multi_plot_requested.extend(names))
    sp.plotDistanceRequested.connect(lambda m1, m2: distance_requested.append((m1, m2)))

    menu2, actions2 = sp.create_marker_context_menu(["RASI", "LASI"])
    assert menu2 is not None
    action_texts2 = [a.text() for a in menu2.actions() if a.text()]
    assert any("Plot Selected Markers (2) (X, Y, Z)" in t for t in action_texts2), \
        f"Expected multi-marker plot action in {action_texts2}"
    assert "act_plot" in actions2
    assert "act_distance" in actions2, f"Expected 'act_distance' in actions when 2 markers selected, got {actions2.keys()}"
    assert actions2["act_distance"].text() == "Distance (RASI ↔ LASI)"

    # Trigger action choice directly for Distance
    sp._handle_marker_context_menu_choice(actions2["act_distance"], actions2)
    assert distance_requested == [("RASI", "LASI")], f"Expected [('RASI', 'LASI')], got {distance_requested}"
    print("SidePanel 2-marker Distance action verified!")

    # Test 2c: 3 markers selected -> Distance action should NOT appear
    menu3, actions3 = sp.create_marker_context_menu(["RASI", "LASI", "RPSI"])
    assert "act_distance" not in actions3, "Distance option should only appear when exactly 2 markers are selected"
    print("3-marker selection correctly omits Distance option!")

    # 3. Test MainWindow Signal Wiring & UniversalPlotterWindow Plotting
    mw = MainWindow()
    mw.trial = trial
    mw.side_panel.load_trial(trial)
    mw.viewer_3d.load_trial(trial)

    # Call mw.plot_marker('RASI') directly
    mw.plot_marker("RASI")
    assert mw.plotter_window is not None, "plotter_window must be created"
    pw: UniversalPlotterWindow = mw.plotter_window

    # Verify curves for RASI X, Y, Z are plotted
    active_keys = set(pw.active_curves.keys())
    assert "RASI (X)" in active_keys, f"RASI (X) missing in {active_keys}"
    assert "RASI (Y)" in active_keys, f"RASI (Y) missing in {active_keys}"
    assert "RASI (Z)" in active_keys, f"RASI (Z) missing in {active_keys}"
    assert len(active_keys) == 3, f"Expected exactly 3 curves (clear_others=True), got {active_keys}"

    # Verify coordinate semantic colors
    assert pw.color_map["RASI (X)"] in ("#FF5252", "#EF4444"), f"Incorrect X color: {pw.color_map['RASI (X)']}"
    assert pw.color_map["RASI (Y)"] in ("#00E676", "#16A34A"), f"Incorrect Y color: {pw.color_map['RASI (Y)']}"
    assert pw.color_map["RASI (Z)"] in ("#40C4FF", "#0284C7"), f"Incorrect Z color: {pw.color_map['RASI (Z)']}"
    print("MainWindow.plot_marker correctly plotted RASI X, Y, Z with coordinate colors!")

    # 4. Test Multi-marker plotting in UniversalPlotterWindow
    mw.plot_markers(["RASI", "LASI"])
    active_keys_multi = set(pw.active_curves.keys())
    for comp in ["(X)", "(Y)", "(Z)"]:
        assert f"RASI {comp}" in active_keys_multi
        assert f"LASI {comp}" in active_keys_multi
    assert len(active_keys_multi) == 6
    print("MainWindow.plot_markers correctly plotted multi-marker coordinates!")

    # 5. Test Distance Calculation & Universal Plotter Display
    dist_label = "Distance: RASI ↔ LASI (mm)"
    mw.plot_marker_distance("RASI", "LASI")
    assert dist_label in pw.active_curves, f"Expected {dist_label} in plotter active curves: {list(pw.active_curves.keys())}"
    plot_data_y = pw.active_curves[dist_label].getData()[1]
    assert len(plot_data_y) == n_frames

    # Verify Euclidean distance calculation correctness
    expected_dist = np.linalg.norm(trial.markers["RASI"] - trial.markers["LASI"], axis=1)
    np.testing.assert_allclose(plot_data_y, expected_dist, rtol=1e-5)
    print("Euclidean distance computation matches np.linalg.norm perfectly in Universal Plotter!")

    # Verify NO 3D line overlay in viewer_3d
    assert mw.viewer_3d.active_measurement is None or mw.viewer_3d.active_measurement.get("m1") == ""
    print("3D Viewport distance measurement connecting line correctly omitted!")

    # 6. Test 3D Viewer right-click context menu signal forwarding
    single_plot_received = []
    distance_from_3d = []
    mw.side_panel.plotMarkerRequested.connect(lambda name: single_plot_received.append(name))
    mw.side_panel.plotDistanceRequested.connect(lambda m1, m2: distance_from_3d.append((m1, m2)))

    # Simulate 3D right-click on RPSI without blocking modal exec
    menu_3d, actions_3d = mw.side_panel.show_marker_context_menu(QPoint(100, 100), ["RPSI"], _exec=False)
    assert menu_3d is not None
    assert "act_plot" in actions_3d
    assert actions_3d["act_plot"].text() == "Plot 'RPSI' (X, Y, Z)"

    mw.side_panel._handle_marker_context_menu_choice(actions_3d["act_plot"], actions_3d)
    assert single_plot_received == ["RPSI"], f"Expected ['RPSI'], got {single_plot_received}"

    # Simulate 3D right-click when two markers are selected
    menu_3d_2, actions_3d_2 = mw.side_panel.show_marker_context_menu(QPoint(100, 100), ["RASI", "LASI"], _exec=False)
    assert "act_distance" in actions_3d_2
    assert actions_3d_2["act_distance"].text() == "Distance (RASI ↔ LASI)"
    mw.side_panel._handle_marker_context_menu_choice(actions_3d_2["act_distance"], actions_3d_2)
    assert distance_from_3d == [("RASI", "LASI")]
    print("3D Viewer right-click 2-marker Distance option verified!")

    # Clean up
    if mw.plotter_window:
        mw.plotter_window.close()
    mw.close()
    sp.close()
    print("All marker plotting and distance tests passed successfully!")


if __name__ == "__main__":
    test_marker_plot_flow()

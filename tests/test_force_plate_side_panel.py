"""Unit test for Force Plates tab detailed readouts (Fx, Fy, Fz, Moments, COP, and raw channels)."""

import sys
import os
import numpy as np
from PySide6.QtWidgets import QApplication

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.data_models import C3DTrial, ForcePlatformData
from gui.side_panel import SidePanel
from gui.theme import get_theme


def test_force_plate_tab_detailed_display():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Create a 10-frame mock trial with an 8-channel Kistler force plate (Type 3)
    n_analog = 100
    n_point = 10

    forces = np.zeros((n_analog, 3), dtype=float)
    forces[:, 0] = np.linspace(10, 20, n_analog)     # Fx
    forces[:, 1] = np.linspace(-5, 5, n_analog)      # Fy
    forces[:, 2] = np.linspace(500, 800, n_analog)   # Fz

    moments = np.zeros((n_analog, 3), dtype=float)
    moments[:, 0] = np.linspace(-2, -1, n_analog)    # Mx
    moments[:, 1] = np.linspace(15, 25, n_analog)    # My
    moments[:, 2] = np.linspace(-1000, -500, n_analog) # Mz

    cop = np.zeros((n_analog, 3), dtype=float)
    cop[:, 0] = np.linspace(200, 250, n_analog)      # Px
    cop[:, 1] = np.linspace(150, 180, n_analog)      # Py

    channels = {
        f"Fx{i+1}": np.ones(n_analog) * (i + 1) * 10.0 for i in range(8)
    }

    fp1 = ForcePlatformData(
        id=1,
        type=3, # Kistler
        corners=np.array([[0, 400, 400, 0], [0, 0, 600, 600], [0, 0, 0, 0]], dtype=float),
        origin=np.array([200, 300, 0], dtype=float),
        channels=channels,
        forces=forces,
        moments=moments,
        cop=cop
    )

    # Plate 2: Type 2 plate without moments or cop (minimal test)
    fp2 = ForcePlatformData(
        id=2,
        type=2,
        corners=np.array([[500, 900, 900, 500], [0, 0, 600, 600], [0, 0, 0, 0]], dtype=float),
        origin=np.array([700, 300, 0], dtype=float),
        channels={"Ch_A": np.zeros(n_analog), "Ch_B": np.ones(n_analog)},
        forces=forces * 0.5
    )

    trial = C3DTrial(
        file_path="mock_fp.c3d",
        first_frame=1,
        last_frame=10,
        point_rate=100.0,
        point_frame_count=n_point,
        analog_rate=1000.0,
        analog_frame_count=n_analog,
        analog_subsamples=10,
        markers={"LASI": np.zeros((10, 3))},
        force_platforms=[fp1, fp2]
    )

    panel = SidePanel()
    panel.load_trial(trial)

    assert len(panel.fp_widgets) == 2, f"Expected 2 force platform cards, got {len(panel.fp_widgets)}"
    print("Force platform cards created successfully!")

    # Verify initial frame HTML content
    fp_obj, lbl_specs, lbl_data = panel.fp_widgets[0]
    html_text = lbl_data.text()

    # Check for Fx, Fy, Fz on separate lines
    assert "<b>Fx:</b>" in html_text, "Fx should be rendered"
    assert "<b>Fy:</b>" in html_text, "Fy should be rendered"
    assert "<b>Fz:</b>" in html_text, "Fz should be rendered"
    assert "<b>|F|:</b>" in html_text, "Total force |F| should be rendered"

    # Check for Moments
    assert "MOMENTS" in html_text, "MOMENTS header should be rendered"
    assert "<b>Mx:</b>" in html_text, "Mx should be rendered"
    assert "<b>My:</b>" in html_text, "My should be rendered"
    assert "<b>Mz:</b>" in html_text, "Mz should be rendered"

    # Check for COP
    assert "CENTER OF PRESSURE (COP)" in html_text, "COP header should be rendered"
    assert "<b>Px:</b>" in html_text, "Px should be rendered"
    assert "<b>Py:</b>" in html_text, "Py should be rendered"

    # Verify raw platform channels section is removed
    assert "PLATFORM CHANNELS" not in html_text, "Raw platform channels section should not be rendered"

    print("Plate 1 initial frame content verified!")

    # Check Plate 2 (only forces, no moments or cop or platform channels)
    _, _, lbl_data2 = panel.fp_widgets[1]
    html_text2 = lbl_data2.text()
    assert "<b>Fx:</b>" in html_text2
    assert "MOMENTS" not in html_text2, "Plate 2 has no moments, should not render moments section"
    assert "CENTER OF PRESSURE" not in html_text2, "Plate 2 has no COP, should not render COP section"
    assert "PLATFORM CHANNELS" not in html_text2, "Plate 2 should not render platform channels section"
    print("Plate 2 conditional sections verified!")

    # Test update_live_values
    panel.update_live_values(5) # frame index 5 -> analog index 50
    updated_html = lbl_data.text()
    # At index 50, Fx is 15.1, Fy is 0.1, Fz is 651.5
    assert "15.1 N" in updated_html or "15.0 N" in updated_html, f"Expected updated Fx, got {updated_html}"
    print("Live values frame update verified!")

    # Test theme application
    dark_theme = get_theme("Biomech Dark (Obsidian & Cyan)")
    panel.apply_theme(dark_theme)
    assert panel.is_dark is True

    light_theme = get_theme("Clinical Light (Clean Medical White)")
    panel.apply_theme(light_theme)
    assert panel.is_dark is False
    light_html = lbl_data.text()
    assert "#111827" in light_html, "Light theme text color should be present in HTML"
    print("Theme adaptation verified!")

    print("ALL FORCE PLATE TAB DETAILED DISPLAY TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_force_plate_tab_detailed_display()

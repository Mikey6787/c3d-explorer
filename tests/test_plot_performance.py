import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
import pyqtgraph as pg

from core.data_models import C3DTrial, ForcePlatformData
from gui.plotter_window import UniversalPlotterWindow, UniversalPlotter
from gui.settings_dialog import SettingsDialog
from gui.main_window import MainWindow

print("Initializing Plot Performance & Analog Optimization test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# Create mock trial with high-sample-rate analog data (100,000 points per channel at 2000 Hz)
N_ANALOG = 100000
trial = C3DTrial(
    file_path="mock_analog.c3d",
    first_frame=1,
    last_frame=50,
    point_rate=100.0,
    point_frame_count=50,
    analog_rate=2000.0,
    analog_frame_count=N_ANALOG,
    analog_subsamples=20,
    markers={"LASI": np.zeros((50, 3)), "RASI": np.zeros((50, 3))},
    analogs={
        "EMG_Tibialis": np.sin(np.linspace(0, 50, N_ANALOG)) + np.random.normal(0, 0.1, N_ANALOG),
        "EMG_Gastrocnemius": np.cos(np.linspace(0, 50, N_ANALOG)) + np.random.normal(0, 0.1, N_ANALOG),
        "EMG_Soleus": np.sin(np.linspace(0, 25, N_ANALOG)) + np.random.normal(0, 0.1, N_ANALOG),
    },
    force_platforms=[
        ForcePlatformData(
            id=1,
            type=2,
            corners=np.array([[0,0,0],[500,0,0],[500,500,0],[0,500,0]]).T,
            origin=np.array([250, 250, 0]),
            forces=np.zeros((N_ANALOG, 3)),
            moments=np.zeros((N_ANALOG, 3))
        )
    ]
)

# 1. Test UniversalPlotterWindow raw rendering & differential updates
plotter = UniversalPlotterWindow()
plotter.load_trial(trial)
plotter.resize(800, 500)
plotter.show()

plotter_item = plotter.plot_widget.getPlotItem()
assert plotter_item.downsampleMode()[1] is False, "Plotter downsampling should be disabled by default"
assert hasattr(plotter, "set_current_frame"), "Plotter should have set_current_frame alias"

plotter._add_signal("EMG_Tibialis", ("analog", "EMG_Tibialis", 0))
assert "EMG_Tibialis" in plotter.active_curves
p_curve = plotter.active_curves["EMG_Tibialis"]
px, py = p_curve.getData()
assert len(py) == N_ANALOG, f"Expected full {N_ANALOG} raw samples, got {len(py)}"
print(f"Verified 100% raw samples plotted without decimation ({len(py)} points).")

# Differential signal removal
plotter._remove_signal("EMG_Tibialis")
assert "EMG_Tibialis" not in plotter.active_curves, "Differential curve removal failed"
print("Differential curve add/remove verified.")

# 2. Test on-curve hover data value inspection on UniversalPlotterWindow
plotter._add_signal("EMG_Soleus", ("analog", "EMG_Soleus", 0))
assert "EMG_Soleus" in plotter.active_curves
plotter.auto_range()
app.processEvents()

vb = plotter.plot_widget.getViewBox()
c_soleus = plotter.active_curves["EMG_Soleus"]
sx = c_soleus.xData
sy = c_soleus.yData
target_x = float(sx[100])
target_y = float(sy[100])

scene_pos = vb.mapViewToScene(QPointF(target_x, target_y))
plotter._on_mouse_moved([scene_pos])

assert plotter.hover_dot.isVisible(), "UniversalPlotter hover_dot should be visible when hovering over curve"
assert plotter.hover_label.isVisible(), "UniversalPlotter hover_label should be visible when hovering over curve"
html = plotter.hover_label.toHtml()
assert "EMG_Soleus" in html, f"Expected 'EMG_Soleus' in hover label, got: {html}"
assert f"{target_y:.2f}" in html or f"{target_y:.1f}" in html, f"Expected value {target_y:.2f} in hover label"
print("UniversalPlotter on-curve hover inspection verified successfully!")

# Verify moving mouse away hides the indicator and label
plotter._on_mouse_moved([QPointF(-1000.0, -1000.0)])
assert not plotter.hover_dot.isVisible(), "UniversalPlotter hover_dot should be hidden when mouse moves away"
assert not plotter.hover_label.isVisible(), "UniversalPlotter hover_label should be hidden when mouse moves away"
print("UniversalPlotter hover hide on distant mouse position verified.")

print("ALL PLOT PERFORMANCE & ANALOG OPTIMIZATION TESTS PASSED PERFECTLY!", flush=True)

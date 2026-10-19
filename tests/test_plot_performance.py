import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import pyqtgraph as pg

from core.data_models import C3DTrial, ForcePlatformData
from gui.plot_panel import PlotPanel
from gui.plotter_window import UniversalPlotterWindow
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

# 1. Test PlotPanel raw rendering & differential updates
panel = PlotPanel()
panel.load_trial(trial)
panel.resize(800, 400)
panel.show()

# Verify that downsampling is disabled by default (100% full raw points)
plot_item = panel.plot_widget.getPlotItem()
assert plot_item.downsampleMode()[1] is False, "Downsampling should be disabled by default"
print("PlotPanel raw full-resolution default verified.")

# Check EMG_Tibialis
for i in range(panel.channel_list.count()):
    it = panel.channel_list.item(i)
    if it.text() == "EMG_Tibialis":
        it.setCheckState(Qt.Checked)
        break

assert "EMG_Tibialis" in panel.active_curves
curve = panel.active_curves["EMG_Tibialis"]
raw_x, raw_y = curve.getData()
assert len(raw_y) == N_ANALOG, f"Expected full {N_ANALOG} raw samples, got {len(raw_y)}"
print(f"Verified 100% raw samples plotted without decimation ({len(raw_y)} points).")

# Test differential uncheck
for i in range(panel.channel_list.count()):
    it = panel.channel_list.item(i)
    if it.text() == "EMG_Tibialis":
        it.setCheckState(Qt.Unchecked)
        break
assert "EMG_Tibialis" not in panel.active_curves, "Differential curve removal failed"
print("Differential curve add/remove verified.")

# 2. Test UniversalPlotterWindow raw rendering
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
assert len(py) == N_ANALOG, f"Expected {N_ANALOG} raw points in plotter, got {len(py)}"
print("UniversalPlotterWindow raw full-resolution verified.")

# 4. Test PlotPanel on-curve hover data value inspection
from PySide6.QtCore import QPointF
for i in range(panel.channel_list.count()):
    it = panel.channel_list.item(i)
    if it.text() == "EMG_Soleus":
        it.setCheckState(Qt.Checked)
        break

assert "EMG_Soleus" in panel.active_curves
panel.auto_range()
app.processEvents()

vb = panel.plot_widget.getViewBox()
c_soleus = panel.active_curves["EMG_Soleus"]
sx = c_soleus.xData
sy = c_soleus.yData
target_x = float(sx[100])
target_y = float(sy[100])

scene_pos = vb.mapViewToScene(QPointF(target_x, target_y))
panel._on_mouse_moved(scene_pos)

assert panel.hover_dot.isVisible(), "PlotPanel hover_dot should be visible when hovering over curve"
assert panel.hover_label.isVisible(), "PlotPanel hover_label should be visible when hovering over curve"
html = panel.hover_label.toHtml()
assert "EMG_Soleus" in html, f"Expected 'EMG_Soleus' in hover label, got: {html}"
assert f"{target_y:.2f}" in html or f"{target_y:.1f}" in html, f"Expected value {target_y:.2f} in hover label"
print("PlotPanel on-curve hover inspection verified successfully!")

# Verify moving mouse away hides the indicator and label
panel._on_mouse_moved(QPointF(-1000.0, -1000.0))
assert not panel.hover_dot.isVisible(), "PlotPanel hover_dot should be hidden when mouse moves away"
assert not panel.hover_label.isVisible(), "PlotPanel hover_label should be hidden when mouse moves away"
print("PlotPanel hover hide on distant mouse position verified.")

print("ALL PLOT PERFORMANCE & ANALOG OPTIMIZATION TESTS PASSED PERFECTLY!", flush=True)

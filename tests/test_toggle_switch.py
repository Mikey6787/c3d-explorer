import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QImage, QColor
from gui.toggle_switch import ToggleSwitch

print("Initializing ToggleSwitch test...", flush=True)
app = QApplication.instance() or QApplication(sys.argv)

# 1. Test Instantiation and default off state
toggle = ToggleSwitch("Show Optical Markers")
assert toggle.isChecked() is False
assert toggle.offset == 0.0
assert toggle.text() == "Show Optical Markers"
print("ToggleSwitch default state verified.")

# 2. Test programmatically setting checked
toggle.setChecked(True)
assert toggle.isChecked() is True
assert toggle.offset == 1.0
print("ToggleSwitch setChecked(True) verified.")

# 3. Test toggle signal emission
emitted = []
toggle.toggled.connect(lambda s: emitted.append(s))
toggle.toggle()
assert toggle.isChecked() is False
assert emitted == [False]
assert toggle.offset == 0.0

toggle.toggle()
assert toggle.isChecked() is True
assert emitted == [False, True]
assert toggle.offset == 1.0
print("ToggleSwitch toggled signal verified.")

# 4. Test offscreen paint event
img = QImage(240, 40, QImage.Format_ARGB32)
img.fill(0)
toggle.resize(240, 40)
toggle.render(img)
assert not img.isNull()
print("ToggleSwitch rendering verified.")

# 5. Test Hit testing
assert toggle.hitButton(QPointF(10, 10)) is True
assert toggle.hitButton(QPointF(350, 50)) is False
print("ToggleSwitch hit testing verified.")

# 6. Test Custom active color
toggle.set_active_color(QColor("#FF9800"))
assert toggle._active_color.name() == "#ff9800"
print("ToggleSwitch custom active color verified.")

print("ALL TOGGLE SWITCH TESTS PASSED SUCCESSFULLY!")

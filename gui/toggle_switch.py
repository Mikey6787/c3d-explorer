"""Modern animated pill toggle switch widget for PySide6.

Provides a sleek, modern alternative to standard square checkboxes,
styled with an iOS/macOS-inspired capsule track and smooth animated sliding thumb.
Subclasses QCheckBox for 100% API compatibility with isChecked(), setChecked(),
and the toggled signal.
"""

from typing import Optional
from PySide6.QtCore import (
    Qt, Property, QPropertyAnimation, QEasingCurve,
    QRectF, QPointF, QSize
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFontMetrics, QPainterPath
)
from PySide6.QtWidgets import QCheckBox, QWidget, QSizePolicy


class ToggleSwitch(QCheckBox):
    """Modern iOS/macOS-style capsule toggle switch with smooth sliding animation."""

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        active_color: Optional[QColor] = None,
        track_width: int = 38,
        track_height: int = 20,
    ):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_Hover, True)

        self._track_width = track_width
        self._track_height = track_height
        self._thumb_margin = 2.0
        self._thumb_size = self._track_height - (self._thumb_margin * 2.0)

        # Active accent color (default modern vibrant cyan)
        self._active_color = active_color or QColor("#00ADB5")

        # Offset: 0.0 = fully OFF (left), 1.0 = fully ON (right)
        self._offset = 1.0 if self.isChecked() else 0.0

        # Animation setup
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(130)  # Snappy, tactile response (130ms)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.toggled.connect(self._on_toggled)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, val: float):
        self._offset = max(0.0, min(1.0, float(val)))
        self.update()

    offset = Property(float, get_offset, set_offset)

    def _on_toggled(self, checked: bool):
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self._offset = target
            self.update()
            return

        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(target)
        self._anim.start()

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        if not self.isVisible():
            self._offset = 1.0 if checked else 0.0
            self.update()

    def set_active_color(self, color: QColor):
        """Update active switch color."""
        self._active_color = color
        self.update()

    def hitButton(self, pos: QPointF) -> bool:
        """Allow clicking anywhere on the track or label."""
        return self.rect().contains(pos.toPoint() if hasattr(pos, "toPoint") else pos)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def sizeHint(self) -> QSize:
        spacing = 10 if self.text() else 0
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        total_w = self._track_width + spacing + text_w + 4
        total_h = max(self._track_height, fm.height()) + 6
        return QSize(total_w, total_h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # Detect light vs dark theme
        is_light = self.palette().window().color().lightnessF() > 0.5
        is_hovered = self.underMouse()
        is_enabled = self.isEnabled()

        h = self.height()
        track_y = (h - self._track_height) / 2.0
        track_rect = QRectF(2.0, track_y, self._track_width, self._track_height)
        radius = self._track_height / 2.0

        # Interpolate track background color based on _offset (0.0 -> off, 1.0 -> on)
        if is_light:
            off_bg = QColor("#D1D5DB") if not is_hovered else QColor("#9CA3AF")
            border_col = QColor("#9CA3AF") if not is_hovered else QColor("#6B7280")
        else:
            off_bg = QColor("#2A3245") if not is_hovered else QColor("#364058")
            border_col = QColor("#3E4B66") if not is_hovered else QColor("#526385")

        on_bg = self._active_color
        if is_hovered:
            on_bg = on_bg.lighter(108)

        # Blend colors according to offset
        r = int(off_bg.red() + (on_bg.red() - off_bg.red()) * self._offset)
        g = int(off_bg.green() + (on_bg.green() - off_bg.green()) * self._offset)
        b = int(off_bg.blue() + (on_bg.blue() - off_bg.blue()) * self._offset)
        current_bg = QColor(r, g, b)

        if not is_enabled:
            current_bg.setAlpha(120)

        # Draw track
        p.setPen(QPen(border_col if self._offset < 0.2 else current_bg, 1.0))
        p.setBrush(QBrush(current_bg))
        p.drawRoundedRect(track_rect, radius, radius)

        # Calculate thumb (knob) center position
        thumb_min_x = track_rect.x() + self._thumb_margin
        thumb_max_x = track_rect.right() - self._thumb_margin - self._thumb_size
        thumb_x = thumb_min_x + (thumb_max_x - thumb_min_x) * self._offset
        thumb_y = track_rect.y() + self._thumb_margin
        thumb_rect = QRectF(thumb_x, thumb_y, self._thumb_size, self._thumb_size)

        # Draw thumb subtle drop shadow
        if is_enabled:
            shadow_rect = QRectF(thumb_x + 0.5, thumb_y + 1.0, self._thumb_size, self._thumb_size)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 45)))
            p.drawEllipse(shadow_rect)

        # Draw thumb knob
        thumb_color = QColor("#FFFFFF")
        if not is_enabled:
            thumb_color = QColor("#E2E8F0")
            thumb_color.setAlpha(180)

        p.setPen(QPen(QColor(0, 0, 0, 20), 0.5))
        p.setBrush(QBrush(thumb_color))
        p.drawEllipse(thumb_rect)

        # Draw label text if present
        text = self.text()
        if text:
            fm = QFontMetrics(self.font())
            text_x = track_rect.right() + 10.0
            text_y = (h - fm.height()) / 2.0 + fm.ascent()

            text_color = self.palette().text().color()
            if not is_enabled:
                text_color.setAlpha(100)
            elif is_hovered:
                # Slightly brighten or emphasize on hover
                text_color = text_color.lighter(115) if not is_light else text_color.darker(115)

            p.setPen(QPen(text_color))
            p.setFont(self.font())
            p.drawText(QPointF(text_x, text_y), text)

        # Draw focus outline if keyboard focused
        if self.hasFocus():
            focus_pen = QPen(self._active_color, 1.5, Qt.DashLine)
            p.setPen(focus_pen)
            p.setBrush(Qt.NoBrush)
            focus_rect = track_rect.adjusted(-2, -2, 2, 2)
            p.drawRoundedRect(focus_rect, radius + 2, radius + 2)

        p.end()

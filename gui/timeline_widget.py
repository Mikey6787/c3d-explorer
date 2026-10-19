"""Interactive custom timeline slider with integrated C3D event markers."""

from typing import List, Optional, Union
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QPaintEvent, QPolygonF
from PySide6.QtWidgets import QWidget, QToolTip, QMenu

from core.data_models import C3DEvent


class TimelineWidget(QWidget):
    """
    High-precision biomechanics timeline scrubber.
    Displays:
    - Frame and time graduation ticks
    - Color-coded C3D event markers (Foot strikes, Foot offs, general events)
    - Interactive playhead scrubber
    - Hover tooltips for events
    - Right-click context menu to add, edit, or delete events directly on the timeline
    """
    frameChanged = Signal(int)
    eventClicked = Signal(object)  # Emits C3DEvent
    addEventRequested = Signal(int)  # Emits frame index
    editEventRequested = Signal(object)  # Emits C3DEvent
    deleteEventRequested = Signal(object)  # Emits C3DEvent
    trimRangeChanged = Signal(int, int)  # Emits (start_frame, end_frame)
    displayModeChanged = Signal(str)  # Emits "frame" or "time"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setMaximumHeight(68)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.total_frames: int = 100
        self.current_frame: int = 0
        self.point_rate: float = 100.0
        self.events: List[C3DEvent] = []

        # Display mode: "frame" or "time" (default: "frame")
        self.display_mode: str = "frame"

        # Trim / Cut range markers
        self.trim_start_frame: int = 0
        self.trim_end_frame: int = 99

        self._drag_mode: Optional[str] = None  # None, 'playhead', 'trim_start', 'trim_end'
        self._hovered_event: Optional[C3DEvent] = None
        self._handle_hovered: bool = False
        self._trim_start_hovered: bool = False
        self._trim_end_hovered: bool = False

        # Layout parameters (thinner, high-precision biomechanics handles)
        self.track_margin_x = 20
        self.track_height = 10
        self.track_y = 30
        self.handle_width = 8   # Thinner handle thumb (reduced from 12px)
        self.handle_height = 24

        # Theme colors (adaptive to light/dark themes)
        self.is_dark: bool = True
        self.bg_color: QColor = QColor("#161822")
        self.border_color: QColor = QColor("transparent")
        self.tick_color: QColor = QColor("#6A738A")
        self.track_border_color: QColor = QColor("#252A3D")
        self.track_bg_color: QColor = QColor("#151824")
        self.track_active_color: QColor = QColor("#1C2030")
        self.track_trimmed_color: QColor = QColor("#1E273C")
        self.accent_color: QColor = QColor("#00ADB5")
        self.accent_hover_color: QColor = QColor("#00E5FF")
        self.text_muted_color: QColor = QColor("#A3ADC2")
        self.dim_color: QColor = QColor(10, 12, 18, 180)
        self.handle_bg_color: QColor = QColor("#F0F4F8")

    @property
    def _is_dragging(self) -> bool:
        return self._drag_mode is not None

    @_is_dragging.setter
    def _is_dragging(self, val: bool):
        if val:
            self._drag_mode = 'playhead'
        else:
            self._drag_mode = None

    def set_display_mode(self, mode: str):
        """Switch timeline ruler and readouts between 'frame' and 'time'."""
        mode = mode.lower()
        if mode in ("frame", "time") and mode != self.display_mode:
            self.display_mode = mode
            self.update()
            self.displayModeChanged.emit(self.display_mode)

    def toggle_display_mode(self):
        """Toggle between 'frame' and 'time' display modes."""
        self.set_display_mode("time" if self.display_mode == "frame" else "frame")

    def set_trial_data(self, total_frames: int, point_rate: float, events: List[C3DEvent]):
        """Update timeline with new trial information."""
        self.total_frames = max(1, total_frames)
        self.point_rate = max(1.0, point_rate)
        self.events = events
        self.current_frame = 0
        self.trim_start_frame = 0
        self.trim_end_frame = self.total_frames - 1
        self.update()
        self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)

    def set_current_frame(self, frame: int):
        """Update current active frame without triggering feedback loops."""
        frame = max(0, min(self.total_frames - 1, frame))
        if frame != self.current_frame:
            self.current_frame = frame
            self.update()

    def set_trim_range(self, start_frame: int, end_frame: int):
        """Programmatically set the cut/trim range."""
        start_frame = max(0, min(self.total_frames - 1, start_frame))
        end_frame = max(start_frame, min(self.total_frames - 1, end_frame))
        if start_frame != self.trim_start_frame or end_frame != self.trim_end_frame:
            self.trim_start_frame = start_frame
            self.trim_end_frame = end_frame
            self.update()
            self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)

    def set_trim_start_here(self):
        """Set the trim start (In Point) to the current active playhead frame."""
        self.set_trim_range(self.current_frame, max(self.current_frame, self.trim_end_frame))

    def set_trim_end_here(self):
        """Set the trim end (Out Point) to the current active playhead frame."""
        self.set_trim_range(min(self.current_frame, self.trim_start_frame), self.current_frame)

    def reset_trim_range(self):
        """Reset the cut/trim range to the entire trial."""
        self.set_trim_range(0, self.total_frames - 1)

    def apply_theme(self, theme_dict: dict):
        """Update timeline styling according to the active application theme."""
        self.is_dark = theme_dict.get("is_dark", True)
        accent_hex = theme_dict.get("accent", "#00ADB5" if self.is_dark else "#0284C7")
        accent_hover_hex = theme_dict.get("accent_hover", "#00E5FF" if self.is_dark else "#0369A1")

        self.accent_color = QColor(accent_hex)
        self.accent_hover_color = QColor(accent_hover_hex)

        if self.is_dark:
            self.bg_color = QColor("#161822")
            self.border_color = QColor("transparent")
            self.tick_color = QColor("#6A738A")
            self.track_border_color = QColor("#252A3D")
            self.track_bg_color = QColor("#151824")
            self.track_active_color = QColor("#1C2030")
            self.track_trimmed_color = QColor("#1E273C")
            self.text_muted_color = QColor("#A3ADC2")
            self.dim_color = QColor(10, 12, 18, 180)
            self.handle_bg_color = QColor("#F0F4F8")
        else:
            self.bg_color = QColor("#FFFFFF")
            self.border_color = QColor(theme_dict.get("border", "#D1D5DB"))
            self.tick_color = QColor(theme_dict.get("text_muted", "#6B7280"))
            self.track_border_color = QColor(theme_dict.get("border", "#D1D5DB"))
            self.track_bg_color = QColor("#E5E7EB")
            self.track_active_color = QColor("#F3F4F6")
            self.track_trimmed_color = QColor("#E0F2FE")
            self.text_muted_color = QColor(theme_dict.get("text_muted", "#4B5563"))
            self.dim_color = QColor(220, 225, 235, 170)
            self.handle_bg_color = QColor("#FFFFFF")

        self.update()

    def _track_rect(self) -> QRectF:
        w = max(10, self.width() - 2 * self.track_margin_x)
        return QRectF(self.track_margin_x, self.track_y, w, self.track_height)

    def _handle_rect(self) -> QRectF:
        track = self._track_rect()
        curr_x = self._frame_to_x(self.current_frame)
        handle_y = track.center().y()
        return QRectF(
            curr_x - self.handle_width / 2.0,
            handle_y - self.handle_height / 2.0,
            self.handle_width,
            self.handle_height
        )

    def _trim_start_rect(self) -> QRectF:
        track = self._track_rect()
        x = self._frame_to_x(self.trim_start_frame)
        handle_y = track.center().y()
        return QRectF(x - 3.5, handle_y - 13, 7, 26)

    def _trim_end_rect(self) -> QRectF:
        track = self._track_rect()
        x = self._frame_to_x(self.trim_end_frame)
        handle_y = track.center().y()
        return QRectF(x - 3.5, handle_y - 13, 7, 26)

    def _is_on_handle(self, pos: QPointF) -> bool:
        rect = self._handle_rect()
        hit_rect = rect.adjusted(-6, -6, 6, 6)
        return hit_rect.contains(pos)

    def _is_on_trim_start(self, pos: QPointF) -> bool:
        rect = self._trim_start_rect()
        hit_rect = rect.adjusted(-6, -6, 6, 6)
        return hit_rect.contains(pos)

    def _is_on_trim_end(self, pos: QPointF) -> bool:
        rect = self._trim_end_rect()
        hit_rect = rect.adjusted(-6, -6, 6, 6)
        return hit_rect.contains(pos)

    def _find_event_badge_at_pos(self, pos: Union[QPoint, QPointF]) -> Optional[C3DEvent]:
        """Check if pos is specifically on an event marker badge at the top of the timeline."""
        if pos.y() > 24:
            return None
        best_ev = None
        best_dist = 12.0
        for ev in self.events:
            ev_x = self._frame_to_x(ev.frame)
            dist = abs(ev_x - pos.x())
            if dist <= best_dist:
                best_dist = dist
                best_ev = ev
        return best_ev

    def _frame_to_x(self, frame: int) -> float:
        track = self._track_rect()
        if self.total_frames <= 1:
            return track.left()
        ratio = frame / (self.total_frames - 1)
        return track.left() + ratio * track.width()

    def _x_to_frame(self, x: float) -> int:
        track = self._track_rect()
        if track.width() <= 0:
            return 0
        ratio = (x - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        return int(round(ratio * (self.total_frames - 1)))

    def _draw_graduations(self, painter: QPainter, track: QRectF):
        """Draw graduation ticks and numeric labels according to active display_mode (frame or time)."""
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(self.tick_color)

        track_w = track.width()
        if track_w <= 0:
            return

        if self.display_mode == "frame":
            # Target ~8-14 ticks across timeline width
            target_ticks = max(4, min(14, int(track_w / 65)))
            raw_step = max(1, self.total_frames / target_ticks)

            candidates = [
                1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500,
                1000, 2000, 2500, 5000, 10000, 25000, 50000
            ]
            step_frames = candidates[-1]
            for c in candidates:
                if c >= raw_step:
                    step_frames = c
                    break

            # Minor sub-ticks
            sub_step = 0
            if step_frames >= 5:
                if step_frames % 5 == 0:
                    sub_step = step_frames // 5
                elif step_frames % 2 == 0:
                    sub_step = step_frames // 2

            if sub_step > 0:
                sub_pen = QPen(self.tick_color, 0.8)
                sub_pen.setColor(QColor(self.tick_color.red(), self.tick_color.green(), self.tick_color.blue(), 90))
                painter.setPen(sub_pen)
                cur_sub = sub_step
                while cur_sub <= self.total_frames:
                    if cur_sub % step_frames != 0 and cur_sub > 1:
                        xs = self._frame_to_x(cur_sub - 1)
                        painter.drawLine(QPointF(xs, 17), QPointF(xs, 20))
                    cur_sub += sub_step

            # Major ticks and labels (starts from Frame 1)
            painter.setPen(self.tick_color)
            x_first = self._frame_to_x(0)
            painter.drawLine(QPointF(x_first, 13), QPointF(x_first, 20))
            lbl_rect = QRectF(x_first - 28, 0, 56, 14)
            painter.drawText(lbl_rect, Qt.AlignCenter, "1")

            cur_f = step_frames
            while cur_f <= self.total_frames:
                if cur_f > 1:
                    x = self._frame_to_x(cur_f - 1)
                    if x - x_first > 34:
                        painter.drawLine(QPointF(x, 13), QPointF(x, 20))
                        lbl_rect = QRectF(x - 28, 0, 56, 14)
                        painter.drawText(lbl_rect, Qt.AlignCenter, f"{cur_f}")
                cur_f += step_frames

        else:  # "time" (seconds)
            total_seconds = self.total_frames / self.point_rate if self.point_rate > 0 else 1.0
            target_ticks = max(4, min(14, int(track_w / 75)))
            raw_step_sec = total_seconds / target_ticks

            candidates = [
                0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0,
                10.0, 20.0, 30.0, 60.0, 120.0, 300.0
            ]
            step_sec = candidates[-1]
            for c in candidates:
                if c >= raw_step_sec:
                    step_sec = c
                    break

            # Minor sub-ticks
            sub_sec = step_sec / 5.0 if step_sec >= 0.05 else (step_sec / 2.0)
            if sub_sec * self.point_rate >= 1.0:
                sub_pen = QPen(self.tick_color, 0.8)
                sub_pen.setColor(QColor(self.tick_color.red(), self.tick_color.green(), self.tick_color.blue(), 90))
                painter.setPen(sub_pen)
                t_sub = 0.0
                while t_sub <= total_seconds + 1e-5:
                    f_sub = int(round(t_sub * self.point_rate))
                    if f_sub < self.total_frames:
                        xs = self._frame_to_x(f_sub)
                        painter.drawLine(QPointF(xs, 17), QPointF(xs, 20))
                    t_sub += sub_sec

            # Major ticks and labels
            painter.setPen(self.tick_color)
            t = 0.0
            while t <= total_seconds + 1e-5:
                f_major = int(round(t * self.point_rate))
                if f_major >= self.total_frames:
                    break
                x = self._frame_to_x(f_major)
                painter.drawLine(QPointF(x, 13), QPointF(x, 20))

                if step_sec < 0.1:
                    lbl = f"{t:.2f}s"
                elif step_sec < 1.0:
                    lbl = f"{t:.1f}s"
                elif t.is_integer():
                    lbl = f"{int(t)}s"
                else:
                    lbl = f"{t:.1f}s"

                lbl_rect = QRectF(x - 28, 0, 56, 14)
                painter.drawText(lbl_rect, Qt.AlignCenter, lbl)
                t += step_sec

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()
        width = self.width()

        # 1. Background ruler / tick area
        if not self.is_dark and self.border_color != Qt.transparent:
            painter.setPen(QPen(self.border_color, 1))
            bg_rect = self.rect().adjusted(0, 0, -1, -1)
        else:
            painter.setPen(Qt.NoPen)
            bg_rect = self.rect()
        painter.setBrush(self.bg_color)
        painter.drawRoundedRect(bg_rect, 4, 4)

        # 2. Graduation marks (Frame or Time)
        self._draw_graduations(painter, track)

        # 3. Track Groove (Base + Active Cut Region)
        x_start = self._frame_to_x(self.trim_start_frame)
        x_end = self._frame_to_x(self.trim_end_frame)
        curr_x = self._frame_to_x(self.current_frame)
        is_trimmed = (self.trim_start_frame > 0 or self.trim_end_frame < self.total_frames - 1)

        # Base Track Groove
        groove_pen = QPen(self.track_border_color, 1)
        painter.setPen(groove_pen)
        painter.setBrush(self.track_bg_color)
        painter.drawRoundedRect(track, 5, 5)

        # Active Trimmed Region on Track
        active_rect = QRectF(x_start, track.top(), max(0.0, x_end - x_start), track.height())
        painter.setPen(QPen(self.accent_color, 1) if is_trimmed else Qt.NoPen)
        painter.setBrush(self.track_trimmed_color if is_trimmed else self.track_active_color)
        painter.drawRect(active_rect)

        # Dim excluded regions outside the cut range
        if self.trim_start_frame > 0:
            dim_left = QRectF(track.left(), track.top(), max(0.0, x_start - track.left()), track.height())
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.dim_color)
            painter.drawRect(dim_left)

        if self.trim_end_frame < self.total_frames - 1:
            dim_right = QRectF(x_end, track.top(), max(0.0, track.right() - x_end), track.height())
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.dim_color)
            painter.drawRect(dim_right)

        # 5. Event Markers
        for ev in self.events:
            ev_x = self._frame_to_x(ev.frame)
            ev_color = QColor(ev.icon_color)

            # Draw vertical event line through track
            painter.setPen(QPen(ev_color, 2))
            painter.drawLine(QPointF(ev_x, 18), QPointF(ev_x, track.bottom() + 4))

            # Draw top event flag/marker badge
            badge_poly = QPolygonF([
                QPointF(ev_x, 18),
                QPointF(ev_x - 5, 11),
                QPointF(ev_x - 5, 6),
                QPointF(ev_x + 5, 6),
                QPointF(ev_x + 5, 11),
            ])
            painter.setBrush(ev_color)
            painter.drawPolygon(badge_poly)

            # Highlight if hovered
            if self._hovered_event == ev:
                painter.setPen(QPen(QColor("#FFFFFF") if self.is_dark else QColor("#1F2937"), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(ev_x, 24), 6, 6)

        # 6. Trim Start Handle [ (In Point) - Thinner, semi-transparent, with center hairline
        start_rect = self._trim_start_rect()
        is_start_act = self._trim_start_hovered or self._drag_mode == 'trim_start'
        s_fill = QColor("#FFA726" if is_start_act else "#E69500")
        s_fill.setAlpha(185 if is_start_act else 145)
        painter.setPen(QPen(QColor("#FFE082" if is_start_act else "#FFB74D"), 1.2))
        painter.setBrush(s_fill)
        painter.drawRoundedRect(start_rect, 2.5, 2.5)

        # Pointer tab pointing right into active region
        flag_s = QPolygonF([
            QPointF(start_rect.right(), start_rect.top() - 2),
            QPointF(start_rect.right() + 4, start_rect.top() + 3),
            QPointF(start_rect.right(), start_rect.top() + 8)
        ])
        painter.drawPolygon(flag_s)

        # Center vertical hairline down the exact frame position
        painter.setPen(QPen(QColor("#FFF3E0" if is_start_act else "#FFE082"), 1.0))
        painter.drawLine(QPointF(x_start, start_rect.top() + 1), QPointF(x_start, start_rect.bottom() - 1))
        painter.drawLine(QPointF(x_start, track.top() - 2), QPointF(x_start, track.bottom() + 2))

        # 7. Trim End Handle ] (Out Point) - Thinner, semi-transparent, with center hairline
        end_rect = self._trim_end_rect()
        is_end_act = self._trim_end_hovered or self._drag_mode == 'trim_end'
        e_fill = QColor("#FF5722" if is_end_act else "#E64A19")
        e_fill.setAlpha(185 if is_end_act else 145)
        painter.setPen(QPen(QColor("#FFCCBC" if is_end_act else "#FF8A65"), 1.2))
        painter.setBrush(e_fill)
        painter.drawRoundedRect(end_rect, 2.5, 2.5)

        # Pointer tab pointing left into active region
        flag_e = QPolygonF([
            QPointF(end_rect.left(), end_rect.top() - 2),
            QPointF(end_rect.left() - 4, end_rect.top() + 3),
            QPointF(end_rect.left(), end_rect.top() + 8)
        ])
        painter.drawPolygon(flag_e)

        # Center vertical hairline down the exact frame position
        painter.setPen(QPen(QColor("#FBE9E7" if is_end_act else "#FFCCBC"), 1.0))
        painter.drawLine(QPointF(x_end, end_rect.top() + 1), QPointF(x_end, end_rect.bottom() - 1))
        painter.drawLine(QPointF(x_end, track.top() - 2), QPointF(x_end, track.bottom() + 2))

        # 8. Playhead Scrubber Handle (Drawn on top) - Thinner, semi-transparent, with center frame hairline
        handle_x = curr_x
        handle_rect = self._handle_rect()
        is_active = (self._drag_mode == 'playhead' or self._handle_hovered)
        playhead_col = self.accent_hover_color if is_active else self.accent_color

        # Scrubber vertical hairline extending through track and toward ruler ticks
        hairline_pen = QPen(playhead_col, 1.2)
        painter.setPen(hairline_pen)
        painter.drawLine(QPointF(handle_x, 15), QPointF(handle_x, track.bottom() + 3))

        # Scrubber handle thumb - semi-transparent glass body
        thumb_bg = QColor(self.handle_bg_color)
        thumb_bg.setAlpha(185 if is_active else 145)
        painter.setBrush(thumb_bg)
        painter.setPen(QPen(playhead_col, 1.2))
        painter.drawRoundedRect(handle_rect, 3, 3)

        # Sharp vertical hairline right down the middle so user knows exactly which frame they are on
        center_hairline_col = QColor("#FFFFFF") if is_active else (QColor("#00E5FF") if self.is_dark else QColor("#0284C7"))
        painter.setPen(QPen(center_hairline_col, 1.0))
        painter.drawLine(
            QPointF(handle_x, handle_rect.top() + 1),
            QPointF(handle_x, handle_rect.bottom() - 1)
        )

        # 9. Bottom frame / time readout with Cut/Trim info (Active format highlighted)
        cur_t = self.current_frame / self.point_rate if self.point_rate > 0 else 0.0
        total_seconds = self.total_frames / self.point_rate if self.point_rate > 0 else 1.0
        trim_len = self.trim_end_frame - self.trim_start_frame + 1
        trim_sec = trim_len / self.point_rate if self.point_rate > 0 else 0.0
        trim_str = f"  |  ✂ Cut: [{self.trim_start_frame + 1}–{self.trim_end_frame + 1}] ({trim_len} f, {trim_sec:.3f}s)" if is_trimmed else ""
        left_text = f"Frame: {self.current_frame + 1} / {self.total_frames}{trim_str}"
        right_text = f"Time: {cur_t:.3f} s / {total_seconds:.3f} s"

        if self.display_mode == "frame":
            painter.setPen(self.accent_color)
            painter.drawText(QRectF(track.left(), track.bottom() + 6, 450, 14), Qt.AlignLeft, left_text)
            painter.setPen(self.text_muted_color)
            painter.drawText(QRectF(track.right() - 200, track.bottom() + 6, 200, 14), Qt.AlignRight, right_text)
        else:
            painter.setPen(self.text_muted_color)
            painter.drawText(QRectF(track.left(), track.bottom() + 6, 450, 14), Qt.AlignLeft, left_text)
            painter.setPen(self.accent_color)
            painter.drawText(QRectF(track.right() - 200, track.bottom() + 6, 200, 14), Qt.AlignRight, right_text)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            pos = event.position()

            # 1. Main playhead handle takes priority (especially when overlapping with trim handles)
            if self._is_on_handle(pos):
                self._drag_mode = 'playhead'
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
                return

            # 2. Trim Start handle [ takes priority if clicking on it
            if self._is_on_trim_start(pos):
                self._drag_mode = 'trim_start'
                self.setCursor(Qt.SizeHorCursor)
                self.update()
                return

            # 3. Trim End handle ] takes priority if clicking on it
            if self._is_on_trim_end(pos):
                self._drag_mode = 'trim_end'
                self.setCursor(Qt.SizeHorCursor)
                self.update()
                return

            # 4. Check if clicked directly on an event marker badge at the top
            clicked_badge_ev = self._find_event_badge_at_pos(pos)
            if clicked_badge_ev:
                self._drag_mode = 'playhead'
                self.setCursor(Qt.ClosedHandCursor)
                self.set_current_frame(clicked_badge_ev.frame)
                self.frameChanged.emit(self.current_frame)
                self.eventClicked.emit(clicked_badge_ev)
                self.update()
                return

            # 5. Otherwise, clicking anywhere on the track/timeline scrubs to that frame
            self._drag_mode = 'playhead'
            self.setCursor(Qt.ClosedHandCursor)
            new_frame = self._x_to_frame(pos.x())
            self.set_current_frame(new_frame)
            self.frameChanged.emit(self.current_frame)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double clicking toggles display mode between Frame and Time."""
        if event.button() == Qt.LeftButton:
            self.toggle_display_mode()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        pos_x = pos.x()

        if self._drag_mode == 'playhead':
            new_frame = self._x_to_frame(pos_x)
            self.set_current_frame(new_frame)
            self.frameChanged.emit(self.current_frame)
            cur_t = self.current_frame / self.point_rate if self.point_rate > 0 else 0.0
            if self.display_mode == "frame":
                tip = f"<b>Frame: {self.current_frame + 1}</b><br>{cur_t:.3f} s"
            else:
                tip = f"<b>Time: {cur_t:.3f} s</b><br>Frame: {self.current_frame + 1}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        elif self._drag_mode == 'trim_start':
            new_frame = self._x_to_frame(pos_x)
            for ev in self.events:
                ev_x = self._frame_to_x(ev.frame)
                if abs(ev_x - pos_x) <= 8:
                    new_frame = ev.frame
                    break
            new_frame = max(0, min(self.trim_end_frame - 1, new_frame))
            if new_frame != self.trim_start_frame:
                self.trim_start_frame = new_frame
                self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)
                self.update()
            t_val = self.trim_start_frame / self.point_rate if self.point_rate > 0 else 0.0
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>Trim Start (In Point) [</b><br>Frame: {self.trim_start_frame + 1}<br>Time: {t_val:.3f} s",
                self
            )
        elif self._drag_mode == 'trim_end':
            new_frame = self._x_to_frame(pos_x)
            for ev in self.events:
                ev_x = self._frame_to_x(ev.frame)
                if abs(ev_x - pos_x) <= 8:
                    new_frame = ev.frame
                    break
            new_frame = max(self.trim_start_frame + 1, min(self.total_frames - 1, new_frame))
            if new_frame != self.trim_end_frame:
                self.trim_end_frame = new_frame
                self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)
                self.update()
            t_val = self.trim_end_frame / self.point_rate if self.point_rate > 0 else 0.0
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>Trim End (Out Point) ]</b><br>Frame: {self.trim_end_frame + 1}<br>Time: {t_val:.3f} s",
                self
            )
        else:
            on_handle = self._is_on_handle(pos)
            on_trim_start = self._is_on_trim_start(pos)
            on_trim_end = self._is_on_trim_end(pos)

            # When overlapping with playhead, prioritize playhead
            if on_handle:
                on_trim_start = False
                on_trim_end = False

            if (on_handle != self._handle_hovered or
                on_trim_start != self._trim_start_hovered or
                on_trim_end != self._trim_end_hovered):
                self._handle_hovered = on_handle
                self._trim_start_hovered = on_trim_start
                self._trim_end_hovered = on_trim_end
                self.update()

            if on_handle:
                self.setCursor(Qt.SizeHorCursor)
                if self._hovered_event is not None:
                    self._hovered_event = None
                    self.update()
                cur_t = self.current_frame / self.point_rate if self.point_rate > 0 else 0.0
                total_t = self.total_frames / self.point_rate if self.point_rate > 0 else 0.0
                if self.display_mode == "frame":
                    tip_txt = f"<b>Playhead</b><br>Frame: {self.current_frame + 1} / {self.total_frames}<br>Time: {cur_t:.3f} s / {total_t:.3f} s"
                else:
                    tip_txt = f"<b>Playhead</b><br>Time: {cur_t:.3f} s / {total_t:.3f} s<br>Frame: {self.current_frame + 1} / {self.total_frames}"
                QToolTip.showText(event.globalPosition().toPoint(), tip_txt, self)
            elif on_trim_start:
                self.setCursor(Qt.SizeHorCursor)
                if self._hovered_event is not None:
                    self._hovered_event = None
                    self.update()
                t_val = self.trim_start_frame / self.point_rate if self.point_rate > 0 else 0.0
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"<b>Trim Start Handle [</b><br>Frame: {self.trim_start_frame + 1} ({t_val:.3f}s)<br><i>Drag to adjust cut start</i>",
                    self
                )
            elif on_trim_end:
                self.setCursor(Qt.SizeHorCursor)
                if self._hovered_event is not None:
                    self._hovered_event = None
                    self.update()
                t_val = self.trim_end_frame / self.point_rate if self.point_rate > 0 else 0.0
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"<b>Trim End Handle ]</b><br>Frame: {self.trim_end_frame + 1} ({t_val:.3f}s)<br><i>Drag to adjust cut end</i>",
                    self
                )
            else:
                # Hovering over top event badge or event column
                ev = self._find_event_badge_at_pos(pos) or self._find_event_at_x(pos_x)
                if ev != self._hovered_event:
                    self._hovered_event = ev
                    self.update()

                if ev:
                    self.setCursor(Qt.PointingHandCursor)
                    t_str = f"{ev.time:.3f} s"
                    ctx_str = f" [{ev.context}]" if ev.context else ""
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"<b>{ev.name}</b>{ctx_str}<br>Time: {t_str}<br>Frame: {ev.frame + 1}",
                        self
                    )
                else:
                    self.setCursor(Qt.ArrowCursor)
                    QToolTip.hideText()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_mode = None
            pos = event.position()
            if self._is_on_handle(pos):
                self._handle_hovered = True
                self._trim_start_hovered = False
                self._trim_end_hovered = False
                self.setCursor(Qt.SizeHorCursor)
            elif self._is_on_trim_start(pos):
                self._handle_hovered = False
                self._trim_start_hovered = True
                self._trim_end_hovered = False
                self.setCursor(Qt.SizeHorCursor)
            elif self._is_on_trim_end(pos):
                self._handle_hovered = False
                self._trim_start_hovered = False
                self._trim_end_hovered = True
                self.setCursor(Qt.SizeHorCursor)
            elif self._find_event_at_x(pos.x()):
                self._handle_hovered = False
                self._trim_start_hovered = False
                self._trim_end_hovered = False
                self.setCursor(Qt.PointingHandCursor)
            else:
                self._handle_hovered = False
                self._trim_start_hovered = False
                self._trim_end_hovered = False
                self.setCursor(Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        if self._drag_mode is None:
            self._hovered_event = None
            self._handle_hovered = False
            self._trim_start_hovered = False
            self._trim_end_hovered = False
            self.setCursor(Qt.ArrowCursor)
            QToolTip.hideText()
            self.update()
        super().leaveEvent(event)

    def _find_event_at_x(self, x: float) -> Optional[C3DEvent]:
        """Find event closest to the given x coordinate (within 12 pixels)."""
        best_ev = None
        best_dist = 12.0
        for ev in self.events:
            ev_x = self._frame_to_x(ev.frame)
            dist = abs(ev_x - x)
            if dist <= best_dist:
                best_dist = dist
                best_ev = ev
        return best_ev

    def create_context_menu(self, pos: Union[QPoint, QPointF]) -> QMenu:
        """Construct the context menu for a given position on the timeline."""
        pos_x = pos.x()
        click_frame = self._x_to_frame(pos_x)
        # Prioritize event directly under click coordinates (badge or track vertical line)
        clicked_ev = self._find_event_badge_at_pos(pos) or self._find_event_at_x(pos_x) or self._hovered_event

        menu = QMenu(self)
        if clicked_ev:
            act_edit = menu.addAction(f"Edit Event '{clicked_ev.display_name}'...")
            act_edit.triggered.connect(lambda checked=False, ev=clicked_ev: self.editEventRequested.emit(ev))

            act_del = menu.addAction(f"Delete Event '{clicked_ev.display_name}'")
            act_del.triggered.connect(lambda checked=False, ev=clicked_ev: self.deleteEventRequested.emit(ev))

            act_jump = menu.addAction(f"Jump to Event Frame ({clicked_ev.frame + 1})")
            act_jump.triggered.connect(lambda checked=False, f=clicked_ev.frame: (self.set_current_frame(f), self.frameChanged.emit(f)))

            menu.addSeparator()

        t_val = click_frame / self.point_rate if self.point_rate > 0 else 0.0
        act_add_here = menu.addAction(f"Add Event at Frame {click_frame + 1} ({t_val:.3f} s)...")
        act_add_here.triggered.connect(lambda checked=False, f=click_frame: self.addEventRequested.emit(f))

        if self.current_frame != click_frame:
            cur_t = self.current_frame / self.point_rate if self.point_rate > 0 else 0.0
            act_add_playhead = menu.addAction(f"Add Event at Playhead (Frame {self.current_frame + 1}, {cur_t:.3f} s)...")
            act_add_playhead.triggered.connect(lambda checked=False, f=self.current_frame: self.addEventRequested.emit(f))

        # Timeline Display Units (Frame vs Time)
        menu.addSeparator()
        act_unit_frame = menu.addAction("Show Units in Frames")
        act_unit_frame.setCheckable(True)
        act_unit_frame.setChecked(self.display_mode == "frame")
        act_unit_frame.triggered.connect(lambda: self.set_display_mode("frame"))

        act_unit_time = menu.addAction("Show Units in Time (seconds)")
        act_unit_time.setCheckable(True)
        act_unit_time.setChecked(self.display_mode == "time")
        act_unit_time.triggered.connect(lambda: self.set_display_mode("time"))

        # Trim / Cut range options (matches clicked event exact frame if clicking on an event)
        menu.addSeparator()
        trim_target_frame = clicked_ev.frame if clicked_ev is not None else click_frame
        act_trim_in = menu.addAction(f"Set Trim Start Here [ (Frame {trim_target_frame + 1})")
        act_trim_in.triggered.connect(lambda checked=False, f=trim_target_frame: self.set_trim_range(f, max(f, self.trim_end_frame)))

        act_trim_out = menu.addAction(f"Set Trim End Here ] (Frame {trim_target_frame + 1})")
        act_trim_out.triggered.connect(lambda checked=False, f=trim_target_frame: self.set_trim_range(min(f, self.trim_start_frame), f))

        if self.trim_start_frame > 0 or self.trim_end_frame < self.total_frames - 1:
            act_reset_trim = menu.addAction(f"Reset Trim Range to Full (1–{self.total_frames})")
            act_reset_trim.triggered.connect(self.reset_trim_range)

        return menu

    def contextMenuEvent(self, event):
        """Right-click context menu to add, edit, or remove events, switch units, and manage trim markers."""
        menu = self.create_context_menu(event.pos())
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        """Keyboard navigation: Arrow keys, Home/End, I/O for Trim In/Out, and U to toggle Units."""
        if event.key() == Qt.Key_Left:
            self.set_current_frame(self.current_frame - 1)
            self.frameChanged.emit(self.current_frame)
        elif event.key() == Qt.Key_Right:
            self.set_current_frame(self.current_frame + 1)
            self.frameChanged.emit(self.current_frame)
        elif event.key() == Qt.Key_Home:
            self.set_current_frame(0)
            self.frameChanged.emit(self.current_frame)
        elif event.key() == Qt.Key_End:
            self.set_current_frame(self.total_frames - 1)
            self.frameChanged.emit(self.current_frame)
        elif event.key() == Qt.Key_I:
            self.set_trim_start_here()
        elif event.key() == Qt.Key_O:
            self.set_trim_end_here()
        elif event.key() == Qt.Key_U:
            self.toggle_display_mode()
        elif event.key() == Qt.Key_R and (event.modifiers() & Qt.AltModifier):
            self.reset_trim_range()
        else:
            super().keyPressEvent(event)


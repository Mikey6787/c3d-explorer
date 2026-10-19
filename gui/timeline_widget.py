"""Interactive custom timeline slider with integrated C3D event markers."""

from typing import List, Optional
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
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

        # Trim / Cut range markers
        self.trim_start_frame: int = 0
        self.trim_end_frame: int = 99

        self._drag_mode: Optional[str] = None  # None, 'playhead', 'trim_start', 'trim_end'
        self._hovered_event: Optional[C3DEvent] = None
        self._handle_hovered: bool = False
        self._trim_start_hovered: bool = False
        self._trim_end_hovered: bool = False

        # Layout parameters
        self.track_margin_x = 20
        self.track_height = 10
        self.track_y = 30
        self.handle_width = 12
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
            curr_x - self.handle_width / 2,
            handle_y - self.handle_height / 2,
            self.handle_width,
            self.handle_height
        )

    def _trim_start_rect(self) -> QRectF:
        track = self._track_rect()
        x = self._frame_to_x(self.trim_start_frame)
        handle_y = track.center().y()
        return QRectF(x - 9, handle_y - 13, 10, 26)

    def _trim_end_rect(self) -> QRectF:
        track = self._track_rect()
        x = self._frame_to_x(self.trim_end_frame)
        handle_y = track.center().y()
        return QRectF(x - 1, handle_y - 13, 10, 26)

    def _is_on_handle(self, pos: QPointF) -> bool:
        rect = self._handle_rect()
        hit_rect = rect.adjusted(-4, -4, 4, 4)
        return hit_rect.contains(pos)

    def _is_on_trim_start(self, pos: QPointF) -> bool:
        rect = self._trim_start_rect()
        hit_rect = rect.adjusted(-4, -4, 4, 4)
        return hit_rect.contains(pos)

    def _is_on_trim_end(self, pos: QPointF) -> bool:
        rect = self._trim_end_rect()
        hit_rect = rect.adjusted(-4, -4, 4, 4)
        return hit_rect.contains(pos)

    def _find_event_badge_at_pos(self, pos: QPointF) -> Optional[C3DEvent]:
        """Check if pos is specifically on an event marker badge at the top of the timeline."""
        if pos.y() > 22:
            return None
        for ev in self.events:
            ev_x = self._frame_to_x(ev.frame)
            if abs(ev_x - pos.x()) <= 8:
                return ev
        return None

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

        # 2. Time & Frame graduation marks
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(self.tick_color)

        # Determine tick intervals based on total frames
        total_seconds = self.total_frames / self.point_rate
        if total_seconds > 20:
            step_sec = 5.0
        elif total_seconds > 5:
            step_sec = 1.0
        elif total_seconds > 2:
            step_sec = 0.5
        else:
            step_sec = 0.2

        step_frames = max(1, int(round(step_sec * self.point_rate)))
        cur_f = 0
        while cur_f < self.total_frames:
            x = self._frame_to_x(cur_f)
            t = cur_f / self.point_rate
            # Tick mark
            painter.drawLine(QPointF(x, 14), QPointF(x, 20))
            # Text label
            lbl = f"{t:.1f}s"
            painter.drawText(QRectF(x - 25, 0, 50, 14), Qt.AlignCenter, lbl)
            cur_f += step_frames

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

        # 4. Event Markers
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

        # 5. Trim Start Handle [ (In Point)
        start_rect = self._trim_start_rect()
        is_start_act = self._trim_start_hovered or self._drag_mode == 'trim_start'
        painter.setPen(QPen(QColor("#FFE082" if is_start_act else "#FFB74D"), 1.5))
        painter.setBrush(QColor("#FFA726" if is_start_act else "#E69500"))
        painter.drawRoundedRect(start_rect, 3, 3)
        # Top pointer tab pointing right into active region
        flag_s = QPolygonF([
            QPointF(start_rect.right(), start_rect.top() - 3),
            QPointF(start_rect.right() + 5, start_rect.top() + 3),
            QPointF(start_rect.right(), start_rect.top() + 9)
        ])
        painter.drawPolygon(flag_s)

        # 6. Trim End Handle ] (Out Point)
        end_rect = self._trim_end_rect()
        is_end_act = self._trim_end_hovered or self._drag_mode == 'trim_end'
        painter.setPen(QPen(QColor("#FFCCBC" if is_end_act else "#FF8A65"), 1.5))
        painter.setBrush(QColor("#FF5722" if is_end_act else "#E64A19"))
        painter.drawRoundedRect(end_rect, 3, 3)
        # Top pointer tab pointing left into active region
        flag_e = QPolygonF([
            QPointF(end_rect.left(), end_rect.top() - 3),
            QPointF(end_rect.left() - 5, end_rect.top() + 3),
            QPointF(end_rect.left(), end_rect.top() + 9)
        ])
        painter.drawPolygon(flag_e)

        # 7. Playhead Scrubber Handle (Drawn on top)
        handle_x = curr_x
        handle_rect = self._handle_rect()
        is_active = (self._drag_mode == 'playhead' or self._handle_hovered)

        # Scrubber vertical playhead line through the track
        playhead_col = self.accent_hover_color if is_active else self.accent_color
        painter.setPen(QPen(playhead_col, 2))
        painter.drawLine(QPointF(handle_x, track.top() - 2), QPointF(handle_x, track.bottom() + 2))

        # Scrubber handle thumb
        painter.setPen(QPen(playhead_col, 2))
        painter.setBrush(self.handle_bg_color)
        painter.drawRoundedRect(handle_rect, 4, 4)

        # Scrubber inner detail line
        painter.setPen(QPen(playhead_col, 2))
        painter.drawLine(
            QPointF(handle_x, handle_rect.top() + 4),
            QPointF(handle_x, handle_rect.bottom() - 4)
        )

        # 9. Bottom frame / time readout with Cut/Trim info
        painter.setPen(self.text_muted_color)
        cur_t = self.current_frame / self.point_rate
        trim_len = self.trim_end_frame - self.trim_start_frame + 1
        trim_sec = trim_len / self.point_rate
        trim_str = f"  |  ✂ Cut: [{self.trim_start_frame}–{self.trim_end_frame}] ({trim_len} f, {trim_sec:.3f}s)" if is_trimmed else ""
        left_text = f"Frame: {self.current_frame} / {self.total_frames - 1}{trim_str}"
        right_text = f"Time: {cur_t:.3f} s / {total_seconds:.3f} s"
        painter.drawText(QRectF(track.left(), track.bottom() + 6, 450, 14), Qt.AlignLeft, left_text)
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

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        pos_x = pos.x()

        if self._drag_mode == 'playhead':
            new_frame = self._x_to_frame(pos_x)
            self.set_current_frame(new_frame)
            self.frameChanged.emit(self.current_frame)
        elif self._drag_mode == 'trim_start':
            new_frame = self._x_to_frame(pos_x)
            new_frame = max(0, min(self.trim_end_frame - 1, new_frame))
            if new_frame != self.trim_start_frame:
                self.trim_start_frame = new_frame
                self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)
                self.update()
            t_val = self.trim_start_frame / self.point_rate
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>Trim Start (In Point) [</b><br>Frame: {self.trim_start_frame}<br>Time: {t_val:.3f} s",
                self
            )
        elif self._drag_mode == 'trim_end':
            new_frame = self._x_to_frame(pos_x)
            new_frame = max(self.trim_start_frame + 1, min(self.total_frames - 1, new_frame))
            if new_frame != self.trim_end_frame:
                self.trim_end_frame = new_frame
                self.trimRangeChanged.emit(self.trim_start_frame, self.trim_end_frame)
                self.update()
            t_val = self.trim_end_frame / self.point_rate
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>Trim End (Out Point) ]</b><br>Frame: {self.trim_end_frame}<br>Time: {t_val:.3f} s",
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
                QToolTip.showText(event.globalPosition().toPoint(), f"Playhead: Frame {self.current_frame}", self)
            elif on_trim_start:
                self.setCursor(Qt.SizeHorCursor)
                if self._hovered_event is not None:
                    self._hovered_event = None
                    self.update()
                t_val = self.trim_start_frame / self.point_rate
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"<b>Trim Start Handle [</b><br>Frame: {self.trim_start_frame} ({t_val:.3f}s)<br><i>Drag to adjust cut start</i>",
                    self
                )
            elif on_trim_end:
                self.setCursor(Qt.SizeHorCursor)
                if self._hovered_event is not None:
                    self._hovered_event = None
                    self.update()
                t_val = self.trim_end_frame / self.point_rate
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"<b>Trim End Handle ]</b><br>Frame: {self.trim_end_frame} ({t_val:.3f}s)<br><i>Drag to adjust cut end</i>",
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
                        f"<b>{ev.name}</b>{ctx_str}<br>Time: {t_str}<br>Frame: {ev.frame}",
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
        """Find event near the given x coordinate (within 8 pixels)."""
        for ev in self.events:
            ev_x = self._frame_to_x(ev.frame)
            if abs(ev_x - x) <= 8:
                return ev
        return None

    def contextMenuEvent(self, event):
        """Right-click context menu to add, edit, or remove events and manage trim markers."""
        pos_x = event.pos().x()
        click_frame = self._x_to_frame(pos_x)
        clicked_ev = self._find_event_at_x(pos_x)

        menu = QMenu(self)
        if clicked_ev:
            act_edit = menu.addAction(f"Edit Event '{clicked_ev.display_name}'...")
            act_edit.triggered.connect(lambda: self.editEventRequested.emit(clicked_ev))

            act_del = menu.addAction(f"Delete Event '{clicked_ev.display_name}'")
            act_del.triggered.connect(lambda: self.deleteEventRequested.emit(clicked_ev))

            act_jump = menu.addAction(f"Jump to Event Frame ({clicked_ev.frame})")
            act_jump.triggered.connect(lambda: (self.set_current_frame(clicked_ev.frame), self.frameChanged.emit(clicked_ev.frame)))

            menu.addSeparator()

        t_val = click_frame / self.point_rate if self.point_rate > 0 else 0.0
        act_add_here = menu.addAction(f"Add Event at Frame {click_frame} ({t_val:.3f} s)...")
        act_add_here.triggered.connect(lambda: self.addEventRequested.emit(click_frame))

        if self.current_frame != click_frame:
            cur_t = self.current_frame / self.point_rate if self.point_rate > 0 else 0.0
            act_add_playhead = menu.addAction(f"Add Event at Playhead (Frame {self.current_frame}, {cur_t:.3f} s)...")
            act_add_playhead.triggered.connect(lambda: self.addEventRequested.emit(self.current_frame))

        # Trim / Cut range options
        menu.addSeparator()
        act_trim_in = menu.addAction(f"Set Trim Start Here [ (Frame {click_frame})")
        act_trim_in.triggered.connect(lambda: self.set_trim_range(click_frame, max(click_frame, self.trim_end_frame)))

        act_trim_out = menu.addAction(f"Set Trim End Here ] (Frame {click_frame})")
        act_trim_out.triggered.connect(lambda: self.set_trim_range(min(click_frame, self.trim_start_frame), click_frame))

        if self.trim_start_frame > 0 or self.trim_end_frame < self.total_frames - 1:
            act_reset_trim = menu.addAction(f"Reset Trim Range to Full (0–{self.total_frames - 1})")
            act_reset_trim.triggered.connect(self.reset_trim_range)

        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        """Keyboard navigation: Arrow keys, Home/End, and I/O for Trim In/Out."""
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
        elif event.key() == Qt.Key_R and (event.modifiers() & Qt.AltModifier):
            self.reset_trim_range()
        else:
            super().keyPressEvent(event)


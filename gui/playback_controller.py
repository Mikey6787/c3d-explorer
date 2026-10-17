"""Playback controller managing animation timing and frame progression using wall-clock time."""

import time
from PySide6.QtCore import QObject, QTimer, Signal


class PlaybackController(QObject):
    """
    Controls motion capture animation playback using high-precision wall-clock timing.
    Ensures true real-time and variable speed multipliers regardless of point rate (e.g. 50Hz, 220Hz, 1000Hz).
    """
    frameChanged = Signal(int)
    playbackStateChanged = Signal(bool)  # True = playing, False = paused/stopped

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_frames: int = 100
        self.current_frame: int = 0
        self.point_rate: float = 100.0
        self.speed: float = 1.0
        self.is_looping: bool = True
        self.is_playing: bool = False

        self._start_perf_time: float = 0.0
        self._start_frame: int = 0

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 Hz GUI refresh
        self._timer.timeout.connect(self._on_timer_tick)

    def set_trial(self, total_frames: int, point_rate: float):
        """Configure controller for a new trial."""
        self.pause()
        self.total_frames = max(1, total_frames)
        self.point_rate = max(1.0, point_rate)
        self.current_frame = 0

    def set_speed(self, speed: float):
        """Set playback speed multiplier (e.g. 0.1, 0.25, 0.5, 1.0, 2.0)."""
        new_speed = max(0.01, speed)
        if self.is_playing:
            # Re-anchor reference point to current frame so speed change is instantaneous
            self._start_perf_time = time.perf_counter()
            self._start_frame = self.current_frame
        self.speed = new_speed

    def set_loop(self, loop: bool):
        """Set whether playback loops automatically when reaching the end."""
        self.is_looping = loop

    def set_frame(self, frame: int):
        """Directly set active frame."""
        frame = max(0, min(self.total_frames - 1, frame))
        if frame != self.current_frame:
            self.current_frame = frame
            self.frameChanged.emit(self.current_frame)
        if self.is_playing:
            self._start_perf_time = time.perf_counter()
            self._start_frame = self.current_frame

    def play(self):
        """Start animation playback."""
        if self.is_playing:
            return
        if self.current_frame >= self.total_frames - 1:
            self.current_frame = 0
            self.frameChanged.emit(self.current_frame)

        self._start_perf_time = time.perf_counter()
        self._start_frame = self.current_frame
        self.is_playing = True
        self._timer.start()
        self.playbackStateChanged.emit(True)

    def pause(self):
        """Pause playback."""
        if not self.is_playing:
            return
        self.is_playing = False
        self._timer.stop()
        self.playbackStateChanged.emit(False)

    def stop(self):
        """Stop playback and return to first frame."""
        self.pause()
        self.set_frame(0)

    def toggle_play_pause(self):
        """Toggle between play and pause."""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def step_forward(self):
        """Advance by 1 frame."""
        self.pause()
        next_frame = (self.current_frame + 1) % self.total_frames
        self.set_frame(next_frame)

    def step_backward(self):
        """Go backward by 1 frame."""
        self.pause()
        prev_frame = (self.current_frame - 1 + self.total_frames) % self.total_frames
        self.set_frame(prev_frame)

    def jump_to_start(self):
        """Jump to frame 0."""
        self.set_frame(0)

    def jump_to_end(self):
        """Jump to final frame."""
        self.set_frame(self.total_frames - 1)

    def _on_timer_tick(self):
        if not self.is_playing or self.total_frames <= 1:
            return

        now = time.perf_counter()
        elapsed = now - self._start_perf_time
        frames_advanced = int(elapsed * self.point_rate * self.speed)

        next_frame = self._start_frame + frames_advanced

        if next_frame >= self.total_frames:
            if self.is_looping:
                self._start_perf_time = now
                self._start_frame = 0
                next_frame = 0
            else:
                self.current_frame = self.total_frames - 1
                self.frameChanged.emit(self.current_frame)
                self.pause()
                return

        if next_frame != self.current_frame:
            self.current_frame = next_frame
            self.frameChanged.emit(self.current_frame)

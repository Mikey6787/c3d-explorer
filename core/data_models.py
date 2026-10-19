"""Data models representing C3D motion capture trial information."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np


@dataclass
class C3DEvent:
    """Represents a discrete event (e.g. Foot Strike, Foot Off) in the trial."""
    name: str
    time: float          # Time in seconds from first frame
    frame: int           # Frame index (0-based relative to first frame)
    subject: str = ""    # Subject name or ID
    context: str = ""    # Context (e.g. 'Right', 'Left', 'General')
    description: str = "" # Optional description
    event_id: int = 0    # Event ID
    icon_color: str = "#FF9800"

    def __post_init__(self):
        self.name = str(self.name) if self.name is not None else ""
        try:
            self.time = float(self.time)
        except (ValueError, TypeError):
            self.time = 0.0
        try:
            self.frame = int(round(float(self.frame)))
        except (ValueError, TypeError):
            self.frame = 0
        self.subject = str(self.subject) if self.subject is not None else ""
        self.context = str(self.context) if self.context is not None else ""
        self.description = str(self.description) if self.description is not None else ""
        try:
            self.event_id = int(self.event_id)
        except (ValueError, TypeError):
            self.event_id = 0
        self.icon_color = str(self.icon_color) if self.icon_color is not None else "#FF9800"

    def clone(self) -> "C3DEvent":
        """Return a clean, independent copy of this event."""
        return C3DEvent(
            name=self.name,
            time=self.time,
            frame=self.frame,
            subject=self.subject,
            context=self.context,
            description=self.description,
            event_id=self.event_id,
            icon_color=self.icon_color
        )

    @property
    def display_name(self) -> str:
        if self.context and not self.name.startswith(self.context):
            return f"{self.context}: {self.name}"
        return self.name


@dataclass
class ForcePlatformData:
    """Represents a force platform including geometric corners, origin, and signals."""
    id: int
    type: int
    corners: np.ndarray      # Shape (3, 4) - 3D coordinates of 4 corners (mm)
    origin: np.ndarray       # Shape (3,) - Origin offset (mm)
    channels: Dict[str, np.ndarray] = field(default_factory=dict)  # Channel name -> 1D array
    forces: Optional[np.ndarray] = None     # Shape (N, 3) - Fx, Fy, Fz (N)
    moments: Optional[np.ndarray] = None    # Shape (N, 3) - Mx, My, Mz (N.mm or N.m)
    cop: Optional[np.ndarray] = None        # Shape (N, 3) - Center of Pressure (mm)
    cal_matrix: Optional[np.ndarray] = None # Shape (6, 6) or (8, 8) calibration matrix

    @property
    def center(self) -> np.ndarray:
        """Calculate geometric center of the plate."""
        return np.mean(self.corners, axis=1)

    @property
    def width(self) -> float:
        """Dimension along corner 0 -> corner 1."""
        return float(np.linalg.norm(self.corners[:, 1] - self.corners[:, 0]))

    @property
    def length(self) -> float:
        """Dimension along corner 1 -> corner 2."""
        return float(np.linalg.norm(self.corners[:, 2] - self.corners[:, 1]))


@dataclass
class C3DTrial:
    """Complete dataset parsed from a C3D file."""
    file_path: str
    first_frame: int
    last_frame: int
    point_rate: float
    point_frame_count: int
    analog_rate: float
    analog_frame_count: int
    analog_subsamples: int
    
    # Markers: Name -> (N, 3) array
    markers: Dict[str, np.ndarray] = field(default_factory=dict)
    marker_units: str = "mm"
    
    # Analogs: Name -> (M,) array
    analogs: Dict[str, np.ndarray] = field(default_factory=dict)
    analog_units: Dict[str, str] = field(default_factory=dict)
    
    # Force plates
    force_platforms: List[ForcePlatformData] = field(default_factory=list)
    
    # Events
    events: List[C3DEvent] = field(default_factory=list)
    
    # Metadata tree: Group -> { 'description': str, 'parameters': { param: { 'values': any, 'description': str } } }
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Underlying BTK acquisition handle for saving/exporting
    btk_handle: Any = None

    @property
    def duration_seconds(self) -> float:
        if self.point_rate > 0:
            return self.point_frame_count / self.point_rate
        return 0.0

    def frame_to_time(self, frame_idx: int) -> float:
        """Convert relative frame index (0..point_frame_count-1) to time in seconds."""
        if self.point_rate > 0:
            return frame_idx / self.point_rate
        return 0.0

    def time_to_frame(self, time_s: float) -> int:
        """Convert time in seconds to frame index (clamped)."""
        if self.point_rate > 0:
            frame = int(round(time_s * self.point_rate))
            return max(0, min(self.point_frame_count - 1, frame))
        return 0

    def get_marker_positions_at_frame(self, frame_idx: int) -> Dict[str, np.ndarray]:
        """Return dict of marker_name -> [x, y, z] for the given frame index."""
        positions = {}
        if 0 <= frame_idx < self.point_frame_count:
            for name, data in self.markers.items():
                positions[name] = data[frame_idx]
        return positions

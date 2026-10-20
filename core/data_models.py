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


def are_duplicate_events(e1: C3DEvent, e2: C3DEvent, time_tol: float) -> bool:
    """Check if e1 and e2 represent duplicate events at the same timestamp/frame."""
    time_match = abs(e1.time - e2.time) <= time_tol
    frame_match = (e1.frame is not None and e2.frame is not None and e1.frame == e2.frame)
    if not (time_match or frame_match):
        return False

    norm1 = (e1.name or "").strip().lower()
    norm2 = (e2.name or "").strip().lower()
    ctx1 = (e1.context or "").strip().lower()
    ctx2 = (e2.context or "").strip().lower()
    gen1 = not ctx1 or ctx1 == "general"
    gen2 = not ctx2 or ctx2 == "general"

    # Exact name and context match
    if norm1 == norm2 and ctx1 == ctx2:
        return True

    # Both in same specific context (e.g. Left Foot strike vs Left Foot strike)
    if not gen1 and not gen2 and ctx1 == ctx2:
        if norm1 in norm2 or norm2 in norm1:
            return True

    # One general, one specific (e.g. LHS [General] vs Foot strike [Left], or LTO [General] vs Left foot off [Left])
    if (gen1 and not gen2) or (gen2 and not gen1):
        gen_norm = norm1 if gen1 else norm2
        spec_norm = norm2 if gen1 else norm1
        spec_ctx = ctx2 if gen1 else ctx1

        if gen_norm in spec_norm or spec_norm in gen_norm:
            return True

        gait_abbrevs = {
            "left": ("lhs", "lto", "lfs", "lfo", "fs", "fo", "strike", "off", "contact"),
            "right": ("rhs", "rto", "rfs", "rfo", "fs", "fo", "strike", "off", "contact"),
        }
        if spec_ctx in gait_abbrevs and gen_norm in gait_abbrevs[spec_ctx]:
            return True

    # Both in general context
    if gen1 and gen2:
        if norm1 in norm2 or norm2 in norm1:
            return True

    return False


def deduplicate_events(events: List[C3DEvent], point_rate: float = 100.0) -> List[C3DEvent]:
    """
    Remove duplicate events caused by dual header/parameter synchronization
    (e.g. 'Foot strike' in Left context and 'LHS' in General context at the same timestamp).
    Prefers specific leg context (Left/Right) over General context.
    """
    if len(events) <= 1:
        return list(events)

    time_tol = max(0.01, 1.0 / point_rate) if point_rate > 0 else 0.01

    cleaned: List[C3DEvent] = []
    # Sort primarily by approximate frame, placing specific contexts before general
    sorted_events = sorted(
        events,
        key=lambda e: (
            int(round(e.time * point_rate)) if point_rate > 0 else int(round(e.time * 100)),
            0 if (e.context and e.context.lower() not in ("general", "")) else 1,
            e.time
        )
    )

    for ev in sorted_events:
        ev_ctx = (ev.context or "").strip().lower()
        ev_is_gen = not ev_ctx or ev_ctx == "general"

        dup_idx = -1
        for idx, kept in enumerate(cleaned):
            if are_duplicate_events(ev, kept, time_tol):
                dup_idx = idx
                break

        if dup_idx == -1:
            cleaned.append(ev)
        else:
            kept = cleaned[dup_idx]
            kept_ctx = (kept.context or "").strip().lower()
            kept_is_gen = not kept_ctx or kept_ctx == "general"

            # If existing kept event is General but new event is Specific, replace it!
            if kept_is_gen and not ev_is_gen:
                cleaned[dup_idx] = ev
            # Otherwise, if both specific, keep the more descriptive/longer name
            elif not kept_is_gen and not ev_is_gen:
                if len(ev.name or "") > len(kept.name or ""):
                    cleaned[dup_idx] = ev

    cleaned.sort(key=lambda e: e.time)
    return cleaned


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

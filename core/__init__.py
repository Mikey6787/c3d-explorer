"""Core module for C3D Explorer."""

from core.data_models import C3DTrial, ForcePlatformData, C3DEvent
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter
from core.grw_calculator import compute_ground_reaction_wrenches

__version__ = "1.0.1"

__all__ = [
    "__version__",
    "C3DTrial",
    "ForcePlatformData",
    "C3DEvent",
    "C3DReader",
    "C3DWriter",
    "compute_ground_reaction_wrenches",
]

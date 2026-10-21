"""Resource and path resolution utilities for development and frozen bundles (PyInstaller)."""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to a resource, supporting both development mode
    and PyInstaller frozen executables (onefile and onedir modes).
    """
    # 1. PyInstaller onefile extracts to temporary directory in sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        candidate = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(candidate):
            return candidate

    # 2. PyInstaller onedir mode: relative to executable directory or _internal
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, relative_path)
        if os.path.exists(candidate):
            return candidate
        internal_candidate = os.path.join(exe_dir, "_internal", relative_path)
        if os.path.exists(internal_candidate):
            return internal_candidate

    # 3. Development mode: relative to repository root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dev_candidate = os.path.join(project_root, relative_path)
    return dev_candidate

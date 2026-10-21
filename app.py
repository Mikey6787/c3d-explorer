"""Application entry point for C3D Explorer."""

import sys
import os

# Ensure current workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.theme import DARK_THEME_QSS


from gui.macos_utils import setup_macos_app_name


def main():
    # Set macOS native process and bundle name so system menu bar shows "C3D explorer" instead of "Python"
    setup_macos_app_name("C3D explorer")

    # Set Windows native taskbar grouping & app icon identity
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("biomech.c3dexplorer.app")
        except Exception:
            pass

    # Set application identity
    from core import __version__
    QCoreApplication.setOrganizationName("Biomech")
    QCoreApplication.setApplicationName("C3D explorer")
    QCoreApplication.setApplicationVersion(__version__)

    # High DPI settings
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # Hardware Anti-Aliasing (4x MSAA) for OpenGL 3D Viewport
    from PySide6.QtGui import QSurfaceFormat
    gl_fmt = QSurfaceFormat()
    gl_fmt.setSamples(4)
    gl_fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(gl_fmt)

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("C3D explorer")
    app.setStyleSheet(DARK_THEME_QSS)

    from core.resource_utils import get_resource_path
    initial_icon = get_resource_path(os.path.join("assets", "icons", "AppIcon-Dark.png"))
    if os.path.exists(initial_icon):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(initial_icon))

    window = MainWindow()
    window.show()

    # Load initial file if provided on command line
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".c3d") and os.path.exists(sys.argv[1]):
        window.load_c3d_file(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

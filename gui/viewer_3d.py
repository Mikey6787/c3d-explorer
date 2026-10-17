"""3D Biomechanics visualization viewport using PyQtGraph OpenGL."""

from typing import Dict, List, Optional
import numpy as np
from OpenGL import GL
from PySide6.QtCore import Qt, QPoint, QRectF, Signal
from PySide6.QtGui import QVector3D, QVector4D, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QLabel, QFrame, QSizePolicy
)
import pyqtgraph.opengl as gl

from core.data_models import C3DTrial, ForcePlatformData


class InteractiveGLViewWidget(gl.GLViewWidget):
    """GLViewWidget with interactive mouse picking for 3D markers."""
    def __init__(self, viewer: 'Viewer3D', parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self._press_pos: Optional[QPoint] = None

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press_pos = ev.pos()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._press_pos is not None:
            dist = (ev.pos() - self._press_pos).manhattanLength()
            self._press_pos = None
            if dist < 6:
                # Clicked on viewport without camera drag -> pick marker in 3D
                self.viewer.handle_3d_click(ev.pos().x(), ev.pos().y(), ev.modifiers())
        super().mouseReleaseEvent(ev)

    def wheelEvent(self, ev):
        super().wheelEvent(ev)
        if hasattr(self.viewer, 'on_camera_zoomed'):
            self.viewer.on_camera_zoomed()


def get_cone_geometry(tip, direction, length=35.0, radius=10.0, n_segments=16):
    """Compute vertices and faces for a clean 3D cone pointing in direction."""
    d = np.array(direction, dtype=np.float32)
    norm = np.linalg.norm(d)
    if norm < 1e-6:
        return np.zeros((1, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.int32)
    d = d / norm

    # Orthogonal vectors
    if abs(d[0]) < 0.8:
        v1 = np.cross(d, [1, 0, 0])
    else:
        v1 = np.cross(d, [0, 1, 0])
    v1 = v1 / np.linalg.norm(v1)
    v2 = np.cross(d, v1)

    base_center = tip - d * length
    angles = np.linspace(0, 2 * np.pi, n_segments, endpoint=False)

    verts = [tip, base_center]
    for a in angles:
        p = base_center + radius * (np.cos(a) * v1 + np.sin(a) * v2)
        verts.append(p)
    verts = np.array(verts, dtype=np.float32)

    faces = []
    for i in range(n_segments):
        i1 = 2 + i
        i2 = 2 + ((i + 1) % n_segments)
        faces.append([0, i1, i2])      # Cone lateral surface
        faces.append([1, i2, i1])      # Cone base disk
    faces = np.array(faces, dtype=np.int32)
    return verts, faces


def make_cone_mesh(tip, direction, length=35.0, radius=10.0, color=(1, 0, 0, 1), n_segments=16):
    """Generate a clean 3D cone mesh for arrowhead visualization."""
    verts, faces = get_cone_geometry(tip, direction, length, radius, n_segments)
    if len(faces) == 0:
        return None
    mesh = gl.GLMeshItem(vertexes=verts, faces=faces, color=color, smooth=True, drawEdges=False)
    mesh.setGLOptions('opaque')
    mesh.setDepthValue(5)
    return mesh


class Viewer3D(QWidget):
    """
    3D biomechanics OpenGL viewport displaying:
    - Motion capture markers (3D point cloud with customizable styling)
    - Force plates (3D geometry, borders, local axes with X/Y/Z labels and arrowheads)
    - Ground Reaction Force (GRF) 3D vectors emanating from Center of Pressure (COP)
    - Prominent Global coordinate system triad with thick lines, arrowheads, and X/Y/Z labels
    - Ground grid with customizable scale
    - Camera presets (Top, Front, Side, Isometric, Fit/Reset)
    """

    markersSelected = Signal(list)  # Emits List[str] of selected marker names

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trial: Optional[C3DTrial] = None
        self.current_frame: int = 0
        self.hidden_markers: set = set()
        self.selected_marker: Optional[str] = None
        self.selected_markers: List[str] = []
        self.selected_marker_labels: Dict[str, gl.GLTextItem] = {}

        # Settings
        self.marker_size: float = 10.0
        self.marker_color = (1.0, 1.0, 1.0, 1.0)
        self.selected_color = (1.0, 0.84, 0.0, 1.0)
        self.axis_line_width: float = 2.0
        self.axis_length: float = 320.0
        self.grid_spacing: float = 500.0
        self.grf_vector_scale: float = 0.8  # mm per Newton
        self.grf_threshold_n: float = 15.0  # Min vertical force to display vector
        self.z_up: bool = True  # True: standard Z-up, False: Y-up

        # Item handles
        self.grid_item: Optional[gl.GLGridItem] = None
        self.global_axis_items: List[gl.GLGraphicsItem] = []
        self.marker_scatter: Optional[gl.GLScatterPlotItem] = None
        self.plate_mesh_items: List[gl.GLMeshItem] = []
        self.plate_axis_items: List[gl.GLGraphicsItem] = []
        self.grf_vector_items: List[gl.GLLinePlotItem] = []
        self.grf_cone_items: List[gl.GLMeshItem] = []

        # Measurement handles & individual marker styling
        self.custom_marker_colors: Dict[str, tuple] = {}
        self.active_measurement: Optional[dict] = None
        self.meas_line1: Optional[gl.GLLinePlotItem] = None
        self.meas_line2: Optional[gl.GLLinePlotItem] = None
        self.meas_label: Optional[gl.GLTextItem] = None

        # Toggles
        self.show_markers: bool = True
        self.show_force_plates: bool = True
        self.show_plate_axes: bool = True
        self.show_global_axes: bool = True
        self.show_grid: bool = True
        self.show_grf_vectors: bool = True

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # OpenGL 3D Viewport with interactive picking
        self.gl_view = InteractiveGLViewWidget(self, self)
        self.gl_view.setBackgroundColor(QColor("#151720"))
        layout.addWidget(self.gl_view)

        # Initialize Default 3D scene elements
        self._init_scene()

        # Floating Preset / Control Overlay Toolbar at top-left
        self._create_overlay_controls()

    def _init_scene(self):
        """Create ground grid, thick global coordinate triad, and marker cloud."""
        # 1. Ground Grid (spacing 500mm, 10x10 meters, placed at low depth)
        self.grid_item = gl.GLGridItem()
        self.grid_item.setSize(10000, 10000)
        self.grid_item.setSpacing(500, 500)
        self.grid_item.setColor((80, 90, 110, 80))
        self.grid_item.setDepthValue(-20)
        self.gl_view.addItem(self.grid_item)

        # 2. Prominent Global Lab Coordinate System (Thick lines, arrowheads, X/Y/Z labels)
        self._build_global_axes()

        # 3. Markers Scatter Plot Item
        # Highest depthValue and GL_DEPTH_TEST: False ensures markers are ALWAYS visible on top of plates!
        self.marker_scatter = gl.GLScatterPlotItem(
            pos=np.zeros((1, 3)),
            color=self.marker_color,
            size=self.marker_size,
            pxMode=True
        )
        self.marker_scatter.setDepthValue(100)
        self.marker_scatter.setGLOptions({
            'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
            GL.GL_DEPTH_TEST: False,
            GL.GL_BLEND: True
        })
        self.gl_view.addItem(self.marker_scatter)

        # 4. Measurement Overlay Items (lines and text labels)
        self.meas_line1 = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(1.0, 0.85, 0.0, 1.0), width=2.0)
        self.meas_line1.setDepthValue(50)
        self.meas_line1.setVisible(False)
        self.gl_view.addItem(self.meas_line1)

        self.meas_line2 = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(1.0, 0.85, 0.0, 1.0), width=2.0)
        self.meas_line2.setDepthValue(50)
        self.meas_line2.setVisible(False)
        self.gl_view.addItem(self.meas_line2)

        self.meas_label = gl.GLTextItem(pos=[0, 0, 0], text="", color=(1.0, 0.9, 0.1, 1.0), font=QFont("Arial", 13, QFont.Bold))
        self.meas_label.setDepthValue(60)
        self.meas_label.setVisible(False)
        self.gl_view.addItem(self.meas_label)

        # Default camera position & framing zoomed out pleasantly from global triad
        self.gl_view.opts['center'] = QVector3D(0, 0, 0)
        self.gl_view.opts['distance'] = 3200.0
        self.set_camera_isometric()

    def _build_global_axes(self):
        """Construct sleek, professional global coordinate triad with clean arrowheads."""
        for item in self.global_axis_items:
            self.gl_view.removeItem(item)
        self.global_axis_items.clear()

        axis_length = getattr(self, "axis_length", 320.0)
        cone_len = max(25.0, axis_length * 0.14)
        cone_radius = max(6.0, cone_len * 0.28)
        line_w = getattr(self, "axis_line_width", 2.0)

        c_x = (0.95, 0.22, 0.22, 1.0)  # Red
        c_y = (0.22, 0.85, 0.30, 1.0)  # Green
        c_z = (0.25, 0.60, 0.98, 1.0)  # Blue

        font = QFont("Arial", 11, QFont.Bold)

        # Shaft stops at the base of the cone so line does not overlap or swallow the cone!
        shaft_x = axis_length - cone_len
        lx = gl.GLLinePlotItem(pos=np.array([[0, 0, 0], [shaft_x, 0, 0]], dtype=np.float32), color=c_x, width=line_w)
        cone_x = make_cone_mesh([axis_length, 0, 0], [1, 0, 0], length=cone_len, radius=cone_radius, color=c_x)
        txt_x = gl.GLTextItem(pos=[axis_length + 18, 0, 0], text="X", color=c_x, font=font)

        shaft_y = axis_length - cone_len
        ly = gl.GLLinePlotItem(pos=np.array([[0, 0, 0], [0, shaft_y, 0]], dtype=np.float32), color=c_y, width=line_w)
        cone_y = make_cone_mesh([0, axis_length, 0], [0, 1, 0], length=cone_len, radius=cone_radius, color=c_y)
        txt_y = gl.GLTextItem(pos=[0, axis_length + 18, 0], text="Y", color=c_y, font=font)

        shaft_z = axis_length - cone_len
        lz = gl.GLLinePlotItem(pos=np.array([[0, 0, 0], [0, 0, shaft_z]], dtype=np.float32), color=c_z, width=line_w)
        cone_z = make_cone_mesh([0, 0, axis_length], [0, 0, 1], length=cone_len, radius=cone_radius, color=c_z)
        txt_z = gl.GLTextItem(pos=[0, 0, axis_length + 18], text="Z", color=c_z, font=font)

        items = [lx, cone_x, txt_x, ly, cone_y, txt_y, lz, cone_z, txt_z]
        for it in items:
            if it is not None:
                it.setDepthValue(10)
                it.setVisible(self.show_global_axes)
                self.gl_view.addItem(it)
                self.global_axis_items.append(it)

    def _create_overlay_controls(self):
        """Build translucent floating control buttons in top-left corner."""
        overlay = QWidget(self.gl_view)
        overlay.setAttribute(Qt.WA_NoSystemBackground)
        overlay.setStyleSheet("""
            QWidget {
                background: transparent;
            }
            QPushButton, QToolButton {
                background-color: rgba(28, 32, 46, 0.85);
                color: #ECEFF4;
                border: 1px solid rgba(60, 68, 92, 0.8);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover, QToolButton:hover {
                background-color: rgba(0, 173, 181, 0.9);
                color: #FFFFFF;
                border-color: #00ADB5;
            }
            QPushButton:pressed, QToolButton:pressed {
                background-color: #007982;
            }
        """)

        ov_layout = QHBoxLayout(overlay)
        ov_layout.setContentsMargins(10, 10, 10, 10)
        ov_layout.setSpacing(6)

        btn_fit = QPushButton("Fit View")
        btn_fit.clicked.connect(self.fit_view_to_data)
        ov_layout.addWidget(btn_fit)

        btn_iso = QPushButton("3D Iso")
        btn_iso.clicked.connect(self.set_camera_isometric)
        ov_layout.addWidget(btn_iso)

        btn_top = QPushButton("Top")
        btn_top.clicked.connect(self.set_camera_top)
        ov_layout.addWidget(btn_top)

        btn_front = QPushButton("Front")
        btn_front.clicked.connect(self.set_camera_front)
        ov_layout.addWidget(btn_front)

        btn_side = QPushButton("Side")
        btn_side.clicked.connect(self.set_camera_side)
        ov_layout.addWidget(btn_side)

        overlay.adjustSize()
        overlay.move(10, 10)

    # ---------------------------------------------------------
    # Camera Presets
    # ---------------------------------------------------------
    def set_camera_isometric(self):
        """Set 3D isometric perspective."""
        self.gl_view.setCameraPosition(elevation=28, azimuth=45)

    def set_camera_top(self):
        """View down along Z axis."""
        self.gl_view.setCameraPosition(elevation=90, azimuth=0)

    def set_camera_front(self):
        """View along Y axis."""
        self.gl_view.setCameraPosition(elevation=0, azimuth=0)

    def set_camera_side(self):
        """View along X axis."""
        self.gl_view.setCameraPosition(elevation=0, azimuth=90)

    def fit_view_to_data(self):
        """Center and frame the camera around active markers and force plates."""
        if not self.trial:
            self.gl_view.opts['center'] = QVector3D(0, 0, 0)
            self.gl_view.opts['distance'] = 3200.0
            self.gl_view.update()
            return

        all_points = []
        for name, data in self.trial.markers.items():
            if len(data) > 0:
                cur = data[self.current_frame]
                if not (np.all(cur == 0) or np.any(np.isnan(cur))):
                    all_points.append(cur)

        for fp in self.trial.force_platforms:
            all_points.extend(fp.corners.T)

        if not all_points:
            self.gl_view.opts['center'] = QVector3D(0, 0, 0)
            self.gl_view.opts['distance'] = 3200.0
            self.gl_view.update()
            return

        pts = np.array(all_points)
        min_b = np.min(pts, axis=0)
        max_b = np.max(pts, axis=0)
        center = (min_b + max_b) / 2.0
        span = np.linalg.norm(max_b - min_b)

        self.gl_view.opts['center'] = QVector3D(float(center[0]), float(center[1]), float(center[2]))
        # Provide a comfortable margin so global axes, subject, and plates are fully in view
        self.gl_view.opts['distance'] = max(2600.0, float(span) * 2.2)
        self.gl_view.update()

    def _get_effective_marker_size(self, base_size: Optional[float] = None) -> float:
        """
        Calculate perspective-aware marker size that scales naturally as the camera zooms.
        As the user zooms in closer to the markers, they enlarge naturally like physical 3D spheres.
        """
        if base_size is None:
            base_size = self.marker_size

        cur_dist = float(self.gl_view.opts.get('distance', 2500.0))
        cur_fov = float(self.gl_view.opts.get('fov', 60.0))

        # Relative scaling factor from 2500 mm reference distance and 60° FOV
        dist_factor = 2500.0 / max(350.0, cur_dist)
        fov_factor = 60.0 / max(10.0, cur_fov)
        scale = dist_factor * fov_factor

        # Scale with sublinear exponent (0.80) so markers scale realistically
        # but remain comfortably bounded between 3.5px and 45px.
        effective = base_size * (scale ** 0.80)
        return float(np.clip(effective, 3.5, 45.0))

    def on_camera_zoomed(self):
        """Called whenever the camera zooms or FOV changes to dynamically scale marker sizes."""
        if self.trial and self.show_markers and self.marker_scatter:
            self.set_frame(self.current_frame)

    # ---------------------------------------------------------
    # Trial Data Loading
    # ---------------------------------------------------------
    def load_trial(self, trial: C3DTrial):
        """Load and initialize 3D scene elements for a new trial."""
        self.trial = trial
        self.current_frame = 0
        self.hidden_markers.clear()
        self.selected_marker = None
        self.selected_markers.clear()
        for item in self.selected_marker_labels.values():
            self.gl_view.removeItem(item)
        self.selected_marker_labels.clear()

        # Rebuild Force Plates
        self._rebuild_force_plates()

        # Update Frame
        self.set_frame(0)
        self.fit_view_to_data()

    def _rebuild_force_plates(self):
        """Create 3D geometry and coordinate axes with X, Y, Z labels and arrowheads for force plates."""
        # Remove old plate items
        for item in self.plate_mesh_items:
            self.gl_view.removeItem(item)
        self.plate_mesh_items.clear()

        for item in self.plate_axis_items:
            self.gl_view.removeItem(item)
        self.plate_axis_items.clear()

        for item in self.grf_vector_items:
            self.gl_view.removeItem(item)
        self.grf_vector_items.clear()

        for item in self.grf_cone_items:
            self.gl_view.removeItem(item)
        self.grf_cone_items.clear()

        if not self.trial:
            return

        plate_font = QFont("Arial", 11, QFont.Bold)
        axis_font = QFont("Arial", 10, QFont.Bold)

        for fp in self.trial.force_platforms:
            c = fp.corners  # Shape (3, 4)
            p0, p1, p2, p3 = c[:, 0], c[:, 1], c[:, 2], c[:, 3]

            # 1. Plate Surface Mesh (translucent dark plate, slightly offset in Z to prevent z-fighting with foot markers)
            verts = np.array([p0, p1, p2, p3], dtype=np.float32)
            verts[:, 2] -= 2.0  # 2mm downward offset so markers resting on the surface are physically above
            faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
            mesh = gl.GLMeshItem(
                vertexes=verts,
                faces=faces,
                color=(0.14, 0.18, 0.26, 0.65),
                drawEdges=True,
                edgeColor=(0.0, 0.85, 0.95, 1.0),
                smooth=False
            )
            mesh.setGLOptions('translucent')
            mesh.setDepthValue(-5)  # Rendered before markers
            mesh.setVisible(self.show_force_plates)
            self.gl_view.addItem(mesh)
            self.plate_mesh_items.append(mesh)

            # 2. Plate Local Coordinate System Axes
            c_center = fp.center
            # Compute local unit vectors
            ux = p1 - p0
            ux_len = np.linalg.norm(ux)
            ux = ux / ux_len if ux_len > 1e-4 else np.array([1, 0, 0], dtype=np.float32)

            uy = p3 - p0
            uy_len = np.linalg.norm(uy)
            uy = uy / uy_len if uy_len > 1e-4 else np.array([0, 1, 0], dtype=np.float32)

            uz = np.cross(ux, uy)
            uz_len = np.linalg.norm(uz)
            uz = uz / uz_len if uz_len > 1e-4 else np.array([0, 0, 1], dtype=np.float32)

            axis_len = 130.0  # 130 mm sleek length
            p_cone_len = 22.0
            p_cone_rad = 7.0
            p_width = 1.8     # Thin, high-precision line width (never messy on zoom-out)

            col_px = (0.95, 0.25, 0.25, 1.0)  # Red
            col_py = (0.25, 0.85, 0.30, 1.0)  # Green
            col_pz = (0.30, 0.65, 0.98, 1.0)  # Blue

            # Local X Axis (line stops cleanly at cone base)
            shaft_px = c_center + ux * (axis_len - p_cone_len)
            tip_px = c_center + ux * axis_len
            lx = gl.GLLinePlotItem(pos=np.array([c_center, shaft_px], dtype=np.float32), color=col_px, width=p_width)
            cx = make_cone_mesh(tip_px, ux, length=p_cone_len, radius=p_cone_rad, color=col_px)
            tx = gl.GLTextItem(pos=c_center + ux * (axis_len + 14), text="X", color=col_px, font=axis_font)

            # Local Y Axis (line stops cleanly at cone base)
            shaft_py = c_center + uy * (axis_len - p_cone_len)
            tip_py = c_center + uy * axis_len
            ly = gl.GLLinePlotItem(pos=np.array([c_center, shaft_py], dtype=np.float32), color=col_py, width=p_width)
            cy = make_cone_mesh(tip_py, uy, length=p_cone_len, radius=p_cone_rad, color=col_py)
            ty = gl.GLTextItem(pos=c_center + uy * (axis_len + 14), text="Y", color=col_py, font=axis_font)

            # Local Z Axis (line stops cleanly at cone base)
            shaft_pz = c_center + uz * (axis_len - p_cone_len)
            tip_pz = c_center + uz * axis_len
            lz = gl.GLLinePlotItem(pos=np.array([c_center, shaft_pz], dtype=np.float32), color=col_pz, width=p_width)
            cz = make_cone_mesh(tip_pz, uz, length=p_cone_len, radius=p_cone_rad, color=col_pz)
            tz = gl.GLTextItem(pos=c_center + uz * (axis_len + 14), text="Z", color=col_pz, font=axis_font)

            # Plate ID Label at center
            lbl_fp = gl.GLTextItem(pos=c_center + np.array([0, 0, 12]), text=f"FP {fp.id}", color=(0.0, 0.9, 1.0, 1.0), font=plate_font)

            for item in (lx, cx, tx, ly, cy, ty, lz, cz, tz, lbl_fp):
                if item is not None:
                    item.setDepthValue(5)
                    item.setVisible(self.show_plate_axes)
                    self.gl_view.addItem(item)
                    self.plate_axis_items.append(item)

            # 3. Dynamic Ground Reaction Force Vector Line & Conical Arrowhead
            grf_color = (1.0, 0.35, 0.08, 1.0)  # Bright amber-orange
            grf_line = gl.GLLinePlotItem(
                pos=np.zeros((2, 3), dtype=np.float32),
                color=grf_color,
                width=2.0
            )
            grf_line.setDepthValue(20)
            grf_line.setVisible(False)
            self.gl_view.addItem(grf_line)
            self.grf_vector_items.append(grf_line)

            # Dynamic cone mesh for arrowhead
            grf_cone = gl.GLMeshItem(
                vertexes=np.zeros((3, 3), dtype=np.float32),
                faces=np.zeros((1, 3), dtype=np.int32),
                color=grf_color,
                smooth=True,
                drawEdges=False
            )
            grf_cone.setGLOptions('opaque')
            grf_cone.setDepthValue(25)
            grf_cone.setVisible(False)
            self.gl_view.addItem(grf_cone)
            self.grf_cone_items.append(grf_cone)

    # ---------------------------------------------------------
    # Frame Update
    # ---------------------------------------------------------
    def set_frame(self, frame_idx: int):
        """Update 3D scene to the given frame index."""
        if not self.trial:
            return

        self.current_frame = max(0, min(self.trial.point_frame_count - 1, frame_idx))

        # 1. Update Markers
        if self.show_markers:
            positions = []
            colors = []
            sizes = []
            selected_set = set(self.selected_markers)
            eff_marker_size = self._get_effective_marker_size(self.marker_size)
            eff_selected_size = eff_marker_size * 1.8

            for name, data in self.trial.markers.items():
                if name in self.hidden_markers:
                    continue
                if self.current_frame < len(data):
                    pos = data[self.current_frame]
                    if np.all(pos == 0) or np.any(np.isnan(pos)):
                        continue
                    positions.append(pos)
                    if name in selected_set:
                        colors.append(self.selected_color)
                        sizes.append(eff_selected_size)
                    elif name in self.custom_marker_colors:
                        colors.append(self.custom_marker_colors[name])
                        sizes.append(eff_marker_size)
                    else:
                        colors.append(self.marker_color)
                        sizes.append(eff_marker_size)

            if positions:
                self.marker_scatter.setData(
                    pos=np.array(positions, dtype=np.float32),
                    color=np.array(colors, dtype=np.float32),
                    size=np.array(sizes, dtype=np.float32),
                    pxMode=True
                )
                self.marker_scatter.setVisible(True)
            else:
                self.marker_scatter.setVisible(False)
        else:
            self.marker_scatter.setVisible(False)

        # 1b. Update 3D Floating Labels for Selected Markers
        self._update_selected_marker_labels()

        # 2. Update Ground Reaction Force Vectors (GRF)
        if self.show_grf_vectors:
            for i, fp in enumerate(self.trial.force_platforms):
                if i >= len(self.grf_vector_items):
                    break
                line_item = self.grf_vector_items[i]
                cone_item = self.grf_cone_items[i] if i < len(self.grf_cone_items) else None

                sub = max(1, self.trial.analog_subsamples)
                analog_idx = self.current_frame * sub

                if (fp.forces is not None and fp.cop is not None and
                    analog_idx < len(fp.forces) and analog_idx < len(fp.cop)):
                    
                    end_idx = min(len(fp.forces), analog_idx + sub)
                    f_vec = np.mean(fp.forces[analog_idx:end_idx], axis=0)
                    cop_pt = np.mean(fp.cop[analog_idx:end_idx], axis=0)

                    f_mag = float(np.linalg.norm(f_vec))
                    if abs(f_vec[2]) >= self.grf_threshold_n and f_mag > 1e-3 and not np.any(np.isnan(cop_pt)):
                        f_dir = f_vec / f_mag
                        scaled_len = f_mag * self.grf_vector_scale
                        end_pt = cop_pt + f_dir * scaled_len

                        # Arrowhead sizing proportional to vector length
                        cone_len = float(min(32.0, max(10.0, scaled_len * 0.22)))
                        cone_rad = float(cone_len * 0.35)

                        # Shaft stops cleanly at base of cone so cone is never swallowed!
                        shaft_end = end_pt - f_dir * cone_len if scaled_len > cone_len else cop_pt

                        line_item.setData(
                            pos=np.array([cop_pt, shaft_end], dtype=np.float32)
                        )
                        line_item.setVisible(True)

                        if cone_item:
                            verts, faces = get_cone_geometry(end_pt, f_dir, length=cone_len, radius=cone_rad, n_segments=14)
                            cone_item.setMeshData(vertexes=verts, faces=faces)
                            cone_item.setVisible(True)
                    else:
                        line_item.setVisible(False)
                        if cone_item:
                            cone_item.setVisible(False)
                else:
                    line_item.setVisible(False)
                    if cone_item:
                        cone_item.setVisible(False)
        else:
            for item in self.grf_vector_items:
                item.setVisible(False)
            for item in self.grf_cone_items:
                item.setVisible(False)

        # 3. Update 3D Measurements (Distance or Angle)
        if self.active_measurement and self.trial:
            meas_type = self.active_measurement.get("type")
            if meas_type == "distance":
                m1 = self.active_measurement.get("m1")
                m2 = self.active_measurement.get("m2")
                if m1 in self.trial.markers and m2 in self.trial.markers:
                    d1 = self.trial.markers[m1]
                    d2 = self.trial.markers[m2]
                    if self.current_frame < len(d1) and self.current_frame < len(d2):
                        p1, p2 = d1[self.current_frame], d2[self.current_frame]
                        valid = not (np.all(p1 == 0) or np.all(p2 == 0) or np.isnan(p1).any() or np.isnan(p2).any())
                        if valid:
                            dist = np.linalg.norm(p1 - p2)
                            self.meas_line1.setData(pos=np.array([p1, p2], dtype=np.float32))
                            self.meas_line1.setVisible(True)
                            self.meas_line2.setVisible(False)
                            mid = (p1 + p2) / 2.0 + np.array([0, 0, 15.0], dtype=np.float32)
                            self.meas_label.setData(pos=mid, text=f"{dist:.1f} mm")
                            self.meas_label.setVisible(True)
                        else:
                            self.meas_line1.setVisible(False)
                            self.meas_line2.setVisible(False)
                            self.meas_label.setVisible(False)
            elif meas_type == "angle":
                ma = self.active_measurement.get("ma")
                mb = self.active_measurement.get("mb")
                mc = self.active_measurement.get("mc")
                if ma in self.trial.markers and mb in self.trial.markers and mc in self.trial.markers:
                    da, db, dc = self.trial.markers[ma], self.trial.markers[mb], self.trial.markers[mc]
                    if (self.current_frame < len(da) and self.current_frame < len(db) and self.current_frame < len(dc)):
                        pa, pb, pc = da[self.current_frame], db[self.current_frame], dc[self.current_frame]
                        valid = not (np.all(pa == 0) or np.all(pb == 0) or np.all(pc == 0) or
                                     np.isnan(pa).any() or np.isnan(pb).any() or np.isnan(pc).any())
                        if valid:
                            self.meas_line1.setData(pos=np.array([pa, pb], dtype=np.float32))
                            self.meas_line2.setData(pos=np.array([pb, pc], dtype=np.float32))
                            self.meas_line1.setVisible(True)
                            self.meas_line2.setVisible(True)
                            v1 = pa - pb
                            v2 = pc - pb
                            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                            if n1 > 1e-4 and n2 > 1e-4:
                                cos_val = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
                                deg = np.degrees(np.arccos(cos_val))
                                self.meas_label.setData(pos=pb + np.array([0, 0, 20.0], dtype=np.float32), text=f"{deg:.1f}°")
                                self.meas_label.setVisible(True)
                        else:
                            self.meas_line1.setVisible(False)
                            self.meas_line2.setVisible(False)
                            self.meas_label.setVisible(False)
        else:
            if self.meas_line1:
                self.meas_line1.setVisible(False)
            if self.meas_line2:
                self.meas_line2.setVisible(False)
            if self.meas_label:
                self.meas_label.setVisible(False)

    # ---------------------------------------------------------
    # Visibility and Appearance Toggles
    # ---------------------------------------------------------
    def set_show_markers(self, show: bool):
        self.show_markers = show
        self.set_frame(self.current_frame)

    def set_show_force_plates(self, show: bool):
        self.show_force_plates = show
        for item in self.plate_mesh_items:
            item.setVisible(show)

    def set_show_plate_axes(self, show: bool):
        self.show_plate_axes = show
        for item in self.plate_axis_items:
            item.setVisible(show)

    def set_show_global_axes(self, show: bool):
        self.show_global_axes = show
        for item in self.global_axis_items:
            item.setVisible(show)

    def set_show_grid(self, show: bool):
        self.show_grid = show
        if self.grid_item:
            self.grid_item.setVisible(show)

    def set_show_grf_vectors(self, show: bool):
        self.show_grf_vectors = show
        if not show:
            for item in self.grf_vector_items:
                item.setVisible(False)
            for item in self.grf_cone_items:
                item.setVisible(False)
        else:
            self.set_frame(self.current_frame)

    def set_marker_size(self, size: float):
        self.marker_size = max(2.0, min(40.0, size))
        self.set_frame(self.current_frame)

    def set_grf_vector_scale(self, scale: float):
        self.grf_vector_scale = max(0.01, min(10.0, scale))
        self.set_frame(self.current_frame)

    def _update_selected_marker_labels(self):
        """Show floating text labels above currently selected markers."""
        needed = set(self.selected_markers)
        for name in list(self.selected_marker_labels.keys()):
            if name not in needed or not self.show_markers:
                item = self.selected_marker_labels.pop(name)
                self.gl_view.removeItem(item)

        if not self.show_markers or not self.trial:
            return

        lbl_font = QFont("Helvetica", 10, QFont.Bold)
        for name in self.selected_markers:
            if name in self.trial.markers and self.current_frame < len(self.trial.markers[name]):
                pos = self.trial.markers[name][self.current_frame]
                if np.all(pos == 0) or np.any(np.isnan(pos)):
                    if name in self.selected_marker_labels:
                        self.selected_marker_labels[name].setVisible(False)
                    continue
                offset = np.array([0.0, 0.0, 18.0], dtype=np.float32)
                lbl_pos = pos + offset
                if name not in self.selected_marker_labels:
                    txt_item = gl.GLTextItem(
                        pos=lbl_pos,
                        text=name,
                        color=(1.0, 0.88, 0.1, 1.0),
                        font=lbl_font
                    )
                    txt_item.setDepthValue(80)
                    self.gl_view.addItem(txt_item)
                    self.selected_marker_labels[name] = txt_item
                else:
                    self.selected_marker_labels[name].setData(pos=lbl_pos, text=name)
                    self.selected_marker_labels[name].setVisible(True)

    def handle_3d_click(self, mouse_x: int, mouse_y: int, modifiers):
        """Interactive 3D raycast/projection marker picking."""
        if not self.trial or not self.show_markers:
            return

        w = self.gl_view.width()
        h = self.gl_view.height()
        if w <= 0 or h <= 0:
            return

        proj = self.gl_view.projectionMatrix((0, 0, w, h), (0, 0, w, h))
        view = self.gl_view.viewMatrix()
        mvp = proj * view

        best_marker = None
        min_dist_px = float('inf')
        pick_radius = 24.0  # Screen pixel threshold

        for name, data in self.trial.markers.items():
            if name in self.hidden_markers:
                continue
            if self.current_frame >= len(data):
                continue
            pos3d = data[self.current_frame]
            if np.all(pos3d == 0) or np.any(np.isnan(pos3d)):
                continue

            pt4 = QVector4D(float(pos3d[0]), float(pos3d[1]), float(pos3d[2]), 1.0)
            clip = mvp.map(pt4)
            if clip.w() <= 0:
                continue

            ndc_x = clip.x() / clip.w()
            ndc_y = clip.y() / clip.w()
            if ndc_x < -1.3 or ndc_x > 1.3 or ndc_y < -1.3 or ndc_y > 1.3:
                continue

            sx = (ndc_x + 1.0) * 0.5 * w
            sy = (1.0 - ndc_y) * 0.5 * h

            dist = np.hypot(sx - mouse_x, sy - mouse_y)
            if dist < pick_radius and dist < min_dist_px:
                min_dist_px = dist
                best_marker = name

        is_multi = bool(modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.ShiftModifier))

        if best_marker is not None:
            if is_multi:
                if best_marker in self.selected_markers:
                    self.selected_markers.remove(best_marker)
                else:
                    self.selected_markers.append(best_marker)
            else:
                self.selected_markers = [best_marker]
        else:
            if not is_multi:
                self.selected_markers = []

        self.selected_marker = self.selected_markers[0] if self.selected_markers else None
        self.set_frame(self.current_frame)
        self.markersSelected.emit(list(self.selected_markers))

    def select_markers(self, marker_names: List[str]):
        """Highlight one or multiple markers in 3D."""
        if self.trial:
            self.selected_markers = [m for m in marker_names if m in self.trial.markers]
        else:
            self.selected_markers = list(marker_names)
        self.selected_marker = self.selected_markers[0] if self.selected_markers else None
        self.set_frame(self.current_frame)

    def select_marker(self, marker_name: Optional[str]):
        """Highlight a specific marker in 3D (single-marker compatibility)."""
        if marker_name:
            self.select_markers([marker_name])
        else:
            self.select_markers([])

    def toggle_marker_visibility(self, marker_name: str, visible: bool):
        """Show or hide a single marker by name."""
        if visible:
            self.hidden_markers.discard(marker_name)
        else:
            self.hidden_markers.add(marker_name)
        self.set_frame(self.current_frame)

    def set_marker_custom_color(self, marker_name: str, color_rgba: Optional[tuple]):
        """Set an individual color for a marker, or None to revert to default."""
        if color_rgba is None:
            self.custom_marker_colors.pop(marker_name, None)
        else:
            self.custom_marker_colors[marker_name] = color_rgba
        self.set_frame(self.current_frame)

    def set_markers_custom_colors(self, marker_names: List[str], color_rgba: Optional[tuple]):
        """Set an individual color for multiple markers in batch, or None to revert to default."""
        for name in marker_names:
            if color_rgba is None:
                self.custom_marker_colors.pop(name, None)
            else:
                self.custom_marker_colors[name] = color_rgba
        self.set_frame(self.current_frame)

    def rename_marker(self, old_name: str, new_name: str):
        """Update marker key in custom colors, selection, and hidden sets."""
        if old_name in self.custom_marker_colors:
            self.custom_marker_colors[new_name] = self.custom_marker_colors.pop(old_name)
        if old_name in self.selected_markers:
            idx = self.selected_markers.index(old_name)
            self.selected_markers[idx] = new_name
        if self.selected_marker == old_name:
            self.selected_marker = new_name
        if old_name in self.hidden_markers:
            self.hidden_markers.remove(old_name)
            self.hidden_markers.add(new_name)
        if old_name in self.selected_marker_labels:
            lbl = self.selected_marker_labels.pop(old_name)
            self.selected_marker_labels[new_name] = lbl
            lbl.setData(text=new_name)
        self.set_frame(self.current_frame)

    def set_distance_measurement(self, m1: str, m2: str, enabled: bool):
        """Enable or disable interactive 3D distance line between two markers."""
        if enabled and m1 and m2 and m1 != m2:
            self.active_measurement = {"type": "distance", "m1": m1, "m2": m2}
        else:
            self.active_measurement = None
        self.set_frame(self.current_frame)

    def set_angle_measurement(self, ma: str, mb: str, mc: str, enabled: bool):
        """Enable or disable interactive 3D angle between three markers."""
        if enabled and len({ma, mb, mc}) == 3:
            self.active_measurement = {"type": "angle", "ma": ma, "mb": mb, "mc": mc}
        else:
            self.active_measurement = None
        self.set_frame(self.current_frame)

    # ---------------------------------------------------------
    # Visual Configurations & Coordinate System Controls
    # ---------------------------------------------------------
    def set_axis_line_width(self, width: float):
        """Set line thickness for coordinate system axes (1.0 - 12.0 px)."""
        self.axis_line_width = max(0.5, min(12.0, float(width)))
        self._build_global_axes()
        if self.trial:
            self._rebuild_force_plates()

    def set_axis_length(self, length: float):
        """Set length for global coordinate system triad (100 - 1000 mm)."""
        self.axis_length = max(100.0, min(1000.0, float(length)))
        self._build_global_axes()

    def set_show_global_axes(self, show: bool):
        """Toggle global coordinate system triad visibility."""
        self.show_global_axes = show
        for item in self.global_axis_items:
            item.setVisible(show)

    def set_show_plate_axes(self, show: bool):
        """Toggle force plate local axes visibility."""
        self.show_plate_axes = show
        for item in self.plate_axis_items:
            item.setVisible(show)

    def set_show_grid(self, show: bool):
        """Toggle ground grid visibility."""
        self.show_grid = show
        if self.grid_item:
            self.grid_item.setVisible(show)

    def set_grid_spacing(self, spacing: float):
        """Set ground grid cell spacing in mm."""
        self.grid_spacing = float(spacing)
        if self.grid_item:
            self.grid_item.setSpacing(self.grid_spacing, self.grid_spacing)

    def set_viewport_bg(self, color_str: str):
        """Set 3D viewport background color."""
        self.gl_view.setBackgroundColor(QColor(color_str))

    def set_show_markers(self, show: bool):
        """Toggle 3D optical markers visibility."""
        self.show_markers = show
        if self.marker_scatter:
            self.marker_scatter.setVisible(show)
        self.set_frame(self.current_frame)

    def set_show_force_plates(self, show: bool):
        """Toggle force plate geometry visibility."""
        self.show_force_plates = show
        for item in self.plate_mesh_items:
            item.setVisible(show)

    def set_show_grf_vectors(self, show: bool):
        """Toggle ground reaction force vectors."""
        self.show_grf_vectors = show
        if not show:
            for item in self.grf_vector_items:
                item.setVisible(False)
            for item in self.grf_cone_items:
                item.setVisible(False)
        else:
            self.set_frame(self.current_frame)

    def apply_theme(self, theme_dict: dict):
        """Update 3D viewport background and grid color to match theme."""
        vp_bg = theme_dict.get("viewport_bg", "#151720")
        grid_col = theme_dict.get("grid_color", (80, 90, 110, 80))
        self.gl_view.setBackgroundColor(QColor(vp_bg))
        if self.grid_item:
            self.grid_item.setColor(grid_col)


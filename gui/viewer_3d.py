"""3D Biomechanics visualization viewport using PyQtGraph OpenGL."""

from typing import Dict, List, Optional
import numpy as np
from OpenGL import GL
from PySide6.QtCore import Qt, QPoint, QRectF, Signal
from PySide6.QtGui import QVector3D, QVector4D, QColor, QFont, QMatrix4x4, QImage, QPainter
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
        if ev.button() in (Qt.LeftButton, Qt.RightButton):
            self._press_pos = ev.pos()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._press_pos is not None:
            dist = (ev.pos() - self._press_pos).manhattanLength()
            self._press_pos = None
            if dist < 6:
                if ev.button() == Qt.LeftButton:
                    self.viewer.handle_3d_click(ev.pos().x(), ev.pos().y(), ev.modifiers())
                elif ev.button() == Qt.RightButton:
                    gpos = ev.globalPosition().toPoint() if hasattr(ev, 'globalPosition') else ev.globalPos()
                    self.viewer.handle_3d_right_click(ev.pos().x(), ev.pos().y(), gpos)
        super().mouseReleaseEvent(ev)

    def contextMenuEvent(self, ev):
        pos = ev.pos()
        gpos = ev.globalPos()
        marker = self.viewer.pick_marker_at(pos.x(), pos.y())
        if marker:
            self.viewer.handle_3d_right_click(pos.x(), pos.y(), gpos)
            ev.accept()
        else:
            super().contextMenuEvent(ev)

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


def get_cylinder_geometry(p1, p2, radius=4.0, n_segments=12):
    """Compute vertices and faces for a clean 3D solid cylinder between p1 and p2."""
    p1 = np.array(p1, dtype=np.float32)
    p2 = np.array(p2, dtype=np.float32)
    d = p2 - p1
    length = float(np.linalg.norm(d))
    if length < 1e-6:
        return np.zeros((1, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.int32)
    d = d / length

    if abs(d[0]) < 0.8:
        v1 = np.cross(d, [1, 0, 0])
    else:
        v1 = np.cross(d, [0, 1, 0])
    v1 = v1 / np.linalg.norm(v1)
    v2 = np.cross(d, v1)

    angles = np.linspace(0, 2 * np.pi, n_segments, endpoint=False)
    verts = [p1, p2]
    for a in angles:
        offset = radius * (np.cos(a) * v1 + np.sin(a) * v2)
        verts.append(p1 + offset)
    for a in angles:
        offset = radius * (np.cos(a) * v1 + np.sin(a) * v2)
        verts.append(p2 + offset)
    verts = np.array(verts, dtype=np.float32)

    faces = []
    for i in range(n_segments):
        b1 = 2 + i
        b2 = 2 + ((i + 1) % n_segments)
        t1 = 2 + n_segments + i
        t2 = 2 + n_segments + ((i + 1) % n_segments)
        faces.append([b1, b2, t2])
        faces.append([b1, t2, t1])
        faces.append([0, b2, b1])
        faces.append([1, t1, t2])
    faces = np.array(faces, dtype=np.int32)
    return verts, faces


def make_cylinder_mesh(p1, p2, radius=4.0, color=(1, 0, 0, 1), n_segments=12):
    """Generate a 3D cylinder mesh with opaque solid rendering."""
    verts, faces = get_cylinder_geometry(p1, p2, radius, n_segments)
    if len(faces) == 0:
        return None
    mesh = gl.GLMeshItem(vertexes=verts, faces=faces, color=color, smooth=True, drawEdges=False)
    mesh.setGLOptions('opaque')
    mesh.setDepthValue(5)
    return mesh


class GLPlateMeshItem(gl.GLMeshItem):
    """
    Custom GLMeshItem for transparent force plate surfaces.
    Disables depth buffer writes during rendering so underlying grid lines,
    local coordinate axes (especially the vertical Z axis), and opposing features
    remain fully visible through the transparent surface regardless of camera angle.
    """
    def paint(self):
        GL.glDepthMask(GL.GL_FALSE)
        try:
            super().paint()
        finally:
            GL.glDepthMask(GL.GL_TRUE)


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
    markerContextMenuRequested = Signal(object, list)  # Emits (QPoint global_pos, List[str] marker_names)

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
        self.grf_color: tuple = (1.0, 0.35, 0.08, 1.0)  # Bright amber-orange default
        self.is_dark: bool = True
        self.z_up: bool = True  # True: standard Z-up, False: Y-up
        self.ground_rotation: float = 0.0  # 0, 90, 180, 270 degrees
        self.orientation_matrix: np.ndarray = np.eye(3, dtype=np.float32)
        self._compute_orientation_matrix()

        # Item handles
        self.grid_item: Optional[gl.GLGridItem] = None
        self.global_axis_items: List[gl.GLGraphicsItem] = []
        self.marker_scatter: Optional[gl.GLScatterPlotItem] = None
        self.plate_mesh_items: List[gl.GLMeshItem] = []
        self.plate_axis_items: List[gl.GLGraphicsItem] = []
        self.plate_label_items: List[gl.GLGraphicsItem] = []
        self.grf_vector_items: List[gl.GLLinePlotItem] = []
        self.grf_shaft_items: List[gl.GLMeshItem] = []
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
        # High depthValue (200) ensures markers are rendered AFTER force plates and stay 100% opaque
        self.marker_scatter = gl.GLScatterPlotItem(
            pos=np.zeros((1, 3)),
            color=self.marker_color,
            size=self.marker_size,
            pxMode=True
        )
        self.marker_scatter.setDepthValue(200)
        self.marker_scatter.setGLOptions({
            'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
            GL.GL_DEPTH_TEST: False,
            GL.GL_BLEND: True
        })
        self.gl_view.addItem(self.marker_scatter)

        # 4. Measurement Overlay Items (lines and text labels)
        self.meas_line1 = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(1.0, 0.85, 0.0, 1.0), width=2.0)
        self.meas_line1.setGLOptions('opaque')
        self.meas_line1.setDepthValue(180)
        self.meas_line1.setVisible(False)
        self.gl_view.addItem(self.meas_line1)

        self.meas_line2 = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(1.0, 0.85, 0.0, 1.0), width=2.0)
        self.meas_line2.setGLOptions('opaque')
        self.meas_line2.setDepthValue(180)
        self.meas_line2.setVisible(False)
        self.gl_view.addItem(self.meas_line2)

        self.meas_label = gl.GLTextItem(pos=[0, 0, 0], text="", color=(1.0, 0.9, 0.1, 1.0), font=QFont("Arial", 13, QFont.Bold))
        self.meas_label.setDepthValue(185)
        self.meas_label.setVisible(False)
        self.gl_view.addItem(self.meas_label)

        # Default camera position & framing zoomed out pleasantly from global triad
        self.gl_view.opts['center'] = QVector3D(0, 0, 0)
        self.gl_view.opts['distance'] = 3200.0
        self.set_camera_isometric()

    def _compute_orientation_matrix(self):
        """Compute 3x3 orientation matrix based on z_up and ground_rotation."""
        if self.z_up:
            R_base = np.eye(3, dtype=np.float32)
        else:
            # Map Y -> Z (Up), Z -> -Y, X -> X (proper rotation around X by -90 deg)
            R_base = np.array([
                [1.0,  0.0,  0.0],
                [0.0,  0.0, -1.0],
                [0.0,  1.0,  0.0]
            ], dtype=np.float32)

        rad = np.radians(self.ground_rotation)
        c, s = float(np.cos(rad)), float(np.sin(rad))
        R_yaw = np.array([
            [c, -s, 0.0],
            [s,  c, 0.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float32)

        self.orientation_matrix = (R_yaw @ R_base).astype(np.float32)

    def transform_point(self, pt) -> np.ndarray:
        """Transform a 3D coordinate vector [x, y, z] by current orientation."""
        arr = np.asarray(pt, dtype=np.float32)
        return self.orientation_matrix @ arr

    def transform_points(self, pts: np.ndarray) -> np.ndarray:
        """Transform an (N, 3) coordinate array by current orientation."""
        arr = np.asarray(pts, dtype=np.float32)
        return arr @ self.orientation_matrix.T

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

        u_x = self.transform_point(np.array([1, 0, 0], dtype=np.float32))
        u_y = self.transform_point(np.array([0, 1, 0], dtype=np.float32))
        u_z = self.transform_point(np.array([0, 0, 1], dtype=np.float32))

        # Shaft stops at the base of the cone so shaft does not overlap or swallow the cone!
        ax_radius = max(2.5, line_w * 1.5)
        zero_pt = np.zeros(3, dtype=np.float32)

        shaft_x = u_x * (axis_length - cone_len)
        tip_x = u_x * axis_length
        lx = make_cylinder_mesh(zero_pt, shaft_x, radius=ax_radius, color=c_x)
        cone_x = make_cone_mesh(tip_x, u_x, length=cone_len, radius=cone_radius, color=c_x)
        txt_x = gl.GLTextItem(pos=u_x * (axis_length + 18), text="X", color=QColor(245, 55, 55, 255), font=font)

        shaft_y = u_y * (axis_length - cone_len)
        tip_y = u_y * axis_length
        ly = make_cylinder_mesh(zero_pt, shaft_y, radius=ax_radius, color=c_y)
        cone_y = make_cone_mesh(tip_y, u_y, length=cone_len, radius=cone_radius, color=c_y)
        txt_y = gl.GLTextItem(pos=u_y * (axis_length + 18), text="Y", color=QColor(55, 220, 75, 255), font=font)

        shaft_z = u_z * (axis_length - cone_len)
        tip_z = u_z * axis_length
        lz = make_cylinder_mesh(zero_pt, shaft_z, radius=ax_radius, color=c_z)
        cone_z = make_cone_mesh(tip_z, u_z, length=cone_len, radius=cone_radius, color=c_z)
        txt_z = gl.GLTextItem(pos=u_z * (axis_length + 18), text="Z", color=QColor(65, 155, 250, 255), font=font)

        items = [lx, cone_x, txt_x, ly, cone_y, txt_y, lz, cone_z, txt_z]
        for it in items:
            if it is not None:
                it.setDepthValue(10)
                it.setVisible(self.show_global_axes)
                self.gl_view.addItem(it)
                self.global_axis_items.append(it)

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
                    all_points.append(self.transform_point(cur))

        for fp in self.trial.force_platforms:
            for pt in fp.corners.T:
                all_points.append(self.transform_point(pt))

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

        for item in self.plate_label_items:
            self.gl_view.removeItem(item)
        self.plate_label_items.clear()

        for item in self.grf_vector_items:
            self.gl_view.removeItem(item)
        self.grf_vector_items.clear()

        for item in getattr(self, "grf_shaft_items", []):
            self.gl_view.removeItem(item)
        if hasattr(self, "grf_shaft_items"):
            self.grf_shaft_items.clear()

        for item in self.grf_cone_items:
            self.gl_view.removeItem(item)
        self.grf_cone_items.clear()

        if not self.trial:
            return

        for fp in self.trial.force_platforms:
            c = fp.corners  # Shape (3, 4)
            p0 = self.transform_point(c[:, 0])
            p1 = self.transform_point(c[:, 1])
            p2 = self.transform_point(c[:, 2])
            p3 = self.transform_point(c[:, 3])

            # 1. Plate Surface Mesh (translucent plate, slightly offset in Z to prevent z-fighting with foot markers)
            is_dark = getattr(self, "is_dark", True)
            if is_dark:
                plate_color = (0.14, 0.18, 0.26, 0.35)
                edge_color = (0.0, 0.85, 0.95, 1.0)
                label_color = QColor(0, 235, 255, 255)
            else:
                # In light theme, delicate translucent tint ensures the floor grid and vertical axis are clearly visible through the plate
                plate_color = (0.12, 0.20, 0.35, 0.16)
                edge_color = (0.02, 0.55, 0.82, 0.95)
                label_color = QColor(2, 132, 199, 255)

            verts = np.array([p0, p1, p2, p3], dtype=np.float32)
            verts[:, 2] -= 2.0  # 2mm downward offset so markers resting on the surface are physically above
            faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
            mesh = GLPlateMeshItem(
                vertexes=verts,
                faces=faces,
                color=plate_color,
                drawEdges=False,
                smooth=False
            )
            mesh.setGLOptions('translucent')
            mesh.setDepthValue(30)  # Rendered after plate local axes (5) so axes remain visible through translucent surface
            mesh.setVisible(self.show_force_plates)
            self.gl_view.addItem(mesh)
            self.plate_mesh_items.append(mesh)

            # Clean rectangular border perimeter (no internal diagonal split line)
            border_pts = np.array([p0, p1, p2, p3, p0], dtype=np.float32)
            border_pts[:, 2] -= 1.8
            border_line = gl.GLLinePlotItem(
                pos=border_pts,
                color=edge_color,
                width=2.0,
                mode='line_strip'
            )
            border_line.setGLOptions('opaque')
            border_line.setDepthValue(35)
            border_line.setVisible(self.show_force_plates)
            self.gl_view.addItem(border_line)
            self.plate_mesh_items.append(border_line)

            # 2. Plate Local Coordinate System Axes
            c_center = self.transform_point(fp.center)
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
            p_cone_len = 24.0
            p_cone_rad = 7.5
            p_radius = 2.5     # Solid, visible cylinder radius

            col_px = (0.95, 0.20, 0.20, 1.0)  # Red
            col_py = (0.15, 0.78, 0.25, 1.0)  # Green
            col_pz = (0.08, 0.52, 0.95, 1.0)  # Rich vibrant Blue

            # Local X Axis (solid cylinder and cone)
            shaft_px = c_center + ux * (axis_len - p_cone_len)
            tip_px = c_center + ux * axis_len
            lx = make_cylinder_mesh(c_center, shaft_px, radius=p_radius, color=col_px)
            cx = make_cone_mesh(tip_px, ux, length=p_cone_len, radius=p_cone_rad, color=col_px)

            # Local Y Axis (solid cylinder and cone)
            shaft_py = c_center + uy * (axis_len - p_cone_len)
            tip_py = c_center + uy * axis_len
            ly = make_cylinder_mesh(c_center, shaft_py, radius=p_radius, color=col_py)
            cy = make_cone_mesh(tip_py, uy, length=p_cone_len, radius=p_cone_rad, color=col_py)

            # Local Z Axis (solid cylinder and cone)
            shaft_pz = c_center + uz * (axis_len - p_cone_len)
            tip_pz = c_center + uz * axis_len
            lz = make_cylinder_mesh(c_center, shaft_pz, radius=p_radius, color=col_pz)
            cz = make_cone_mesh(tip_pz, uz, length=p_cone_len, radius=p_cone_rad, color=col_pz)

            # Plate Number / ID Annotation lying down flat on the force plate surface
            label_text = f"FP {fp.id}"
            w, h = 512, 256
            qimg = QImage(w, h, QImage.Format.Format_RGBA8888)
            qimg.fill(0)
            p = QPainter(qimg)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.setPen(label_color)
            p.setFont(QFont("Arial", 120, QFont.Bold))
            p.drawText(qimg.rect(), Qt.AlignCenter, label_text)
            p.end()

            # Pure numpy vertical flip + memory copy for independent texture
            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((h, w, 4))
            arr_flipped = arr[::-1, :, :].copy()
            img_data = np.transpose(arr_flipped, (1, 0, 2))

            # Plate edges and surface normal
            e01 = p1 - p0
            e01_norm = np.linalg.norm(e01)
            e01_unit = e01 / e01_norm if e01_norm > 1e-4 else np.array([1, 0, 0], dtype=np.float32)

            e03 = p3 - p0
            e03_norm = np.linalg.norm(e03)
            e03_unit = e03 / e03_norm if e03_norm > 1e-4 else np.array([0, 1, 0], dtype=np.float32)

            n = np.cross(e01_unit, e03_unit)
            n_norm = np.linalg.norm(n)
            n_unit = n / n_norm if n_norm > 1e-4 else np.array([0, 0, 1], dtype=np.float32)
            if n_unit[2] < 0:  # In viewer coordinates, +Z is always up
                n_unit = -n_unit

            # Align text reading direction along the plate edge closest to global X
            global_x = np.array([1, 0, 0], dtype=np.float32)
            cand1 = e01_unit if np.dot(e01_unit, global_x) >= 0 else -e01_unit
            cand3 = e03_unit if np.dot(e03_unit, global_x) >= 0 else -e03_unit
            tx = cand1 if abs(np.dot(cand1, global_x)) >= abs(np.dot(cand3, global_x)) else cand3

            ty = np.cross(n_unit, tx)
            ty_norm = np.linalg.norm(ty)
            ty = ty / ty_norm if ty_norm > 1e-4 else np.array([0, 1, 0], dtype=np.float32)

            # Physical size on plate: width 130mm, height 65mm
            phys_w, phys_h = 130.0, 65.0
            sx = phys_w / w
            sy = phys_h / h

            target_pos = p0 + (c_center - p0) * 0.35
            pos = target_pos - tx * (phys_w * 0.5) - ty * (phys_h * 0.5) + n_unit * 0.8

            m = QMatrix4x4(
                float(sx * tx[0]), float(sy * ty[0]), float(n_unit[0]), float(pos[0]),
                float(sx * tx[1]), float(sy * ty[1]), float(n_unit[1]), float(pos[1]),
                float(sx * tx[2]), float(sy * ty[2]), float(n_unit[2]), float(pos[2]),
                0.0,               0.0,               0.0,              1.0
            )

            lbl_fp = gl.GLImageItem(img_data, glOptions='translucent')
            lbl_fp.setTransform(m)
            lbl_fp.setDepthValue(40)
            lbl_fp.setVisible(self.show_force_plates)
            # Retain text and color properties for API compatibility and tests
            lbl_fp.text = label_text
            lbl_fp.color = label_color

            self.gl_view.addItem(lbl_fp)
            self.plate_label_items.append(lbl_fp)

            for item in (lx, cx, ly, cy, lz, cz):
                if item is not None:
                    item.setDepthValue(5)
                    item.setVisible(self.show_plate_axes)
                    self.gl_view.addItem(item)
                    self.plate_axis_items.append(item)

            # 3. Dynamic Ground Reaction Force Vector (3D Solid Cylinder Shaft, Cone Arrowhead, and Center Line)
            grf_color = self.grf_color
            grf_line = gl.GLLinePlotItem(
                pos=np.zeros((2, 3), dtype=np.float32),
                color=grf_color,
                width=2.0
            )
            grf_line.setGLOptions('opaque')
            grf_line.setDepthValue(60)
            grf_line.setVisible(False)
            self.gl_view.addItem(grf_line)
            self.grf_vector_items.append(grf_line)

            # Solid 3D Cylinder Shaft mesh
            grf_shaft = gl.GLMeshItem(
                vertexes=np.zeros((3, 3), dtype=np.float32),
                faces=np.zeros((1, 3), dtype=np.int32),
                color=grf_color,
                smooth=True,
                drawEdges=False
            )
            grf_shaft.setGLOptions('opaque')
            grf_shaft.setDepthValue(62)
            grf_shaft.setVisible(False)
            self.gl_view.addItem(grf_shaft)
            self.grf_shaft_items.append(grf_shaft)

            # Dynamic cone mesh for arrowhead
            grf_cone = gl.GLMeshItem(
                vertexes=np.zeros((3, 3), dtype=np.float32),
                faces=np.zeros((1, 3), dtype=np.int32),
                color=grf_color,
                smooth=True,
                drawEdges=False
            )
            grf_cone.setGLOptions('opaque')
            grf_cone.setDepthValue(65)
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
                pts = np.array(positions, dtype=np.float32)
                pts = self.transform_points(pts)
                self.marker_scatter.setData(
                    pos=pts,
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
                shaft_item = self.grf_shaft_items[i] if hasattr(self, "grf_shaft_items") and i < len(self.grf_shaft_items) else None
                cone_item = self.grf_cone_items[i] if i < len(self.grf_cone_items) else None

                sub = max(1, self.trial.analog_subsamples)
                analog_idx = self.current_frame * sub

                if (fp.forces is not None and fp.cop is not None and
                    analog_idx < len(fp.forces) and analog_idx < len(fp.cop)):
                    
                    end_idx = min(len(fp.forces), analog_idx + sub)
                    f_vec = np.mean(fp.forces[analog_idx:end_idx], axis=0)
                    cop_pt = np.mean(fp.cop[analog_idx:end_idx], axis=0)

                    f_vert = float(abs(f_vec[2]))
                    f_mag = float(np.linalg.norm(f_vec))
                    max_dist = float(max(getattr(fp, "width", 600.0), getattr(fp, "length", 600.0)) * 1.5)

                    if (f_vert >= self.grf_threshold_n and f_mag > 1e-3 and
                        not np.any(np.isnan(cop_pt)) and
                        np.linalg.norm(cop_pt - fp.center) <= max_dist):

                        cop_v = self.transform_point(cop_pt)
                        f_vec_v = self.transform_point(f_vec)
                        f_dir = f_vec_v / f_mag
                        scaled_len = f_mag * self.grf_vector_scale
                        end_pt = cop_v + f_dir * scaled_len

                        # Arrowhead sizing proportional to vector length
                        cone_len = float(min(32.0, max(10.0, scaled_len * 0.22)))
                        cone_rad = float(cone_len * 0.35)
                        shaft_rad = float(max(2.8, min(7.0, cone_rad * 0.42)))

                        # Shaft stops cleanly at base of cone so cone is never swallowed!
                        shaft_end = end_pt - f_dir * cone_len if scaled_len > cone_len else cop_v

                        line_item.setData(
                            pos=np.array([cop_v, shaft_end], dtype=np.float32),
                            color=self.grf_color
                        )
                        line_item.setVisible(True)

                        if shaft_item:
                            s_verts, s_faces = get_cylinder_geometry(cop_v, shaft_end, radius=shaft_rad, n_segments=12)
                            shaft_item.setMeshData(vertexes=s_verts, faces=s_faces, color=self.grf_color)
                            shaft_item.setVisible(True)

                        if cone_item:
                            verts, faces = get_cone_geometry(end_pt, f_dir, length=cone_len, radius=cone_rad, n_segments=14)
                            cone_item.setMeshData(vertexes=verts, faces=faces, color=self.grf_color)
                            cone_item.setVisible(True)
                    else:
                        line_item.setVisible(False)
                        if shaft_item:
                            shaft_item.setVisible(False)
                        if cone_item:
                            cone_item.setVisible(False)
                else:
                    line_item.setVisible(False)
                    if shaft_item:
                        shaft_item.setVisible(False)
                    if cone_item:
                        cone_item.setVisible(False)
        else:
            for item in self.grf_vector_items:
                item.setVisible(False)
            for item in getattr(self, "grf_shaft_items", []):
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
                            p1_v = self.transform_point(p1)
                            p2_v = self.transform_point(p2)
                            self.meas_line1.setData(pos=np.array([p1_v, p2_v], dtype=np.float32))
                            self.meas_line1.setVisible(True)
                            self.meas_line2.setVisible(False)
                            mid = (p1_v + p2_v) / 2.0 + np.array([0, 0, 15.0], dtype=np.float32)
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
                            pa_v = self.transform_point(pa)
                            pb_v = self.transform_point(pb)
                            pc_v = self.transform_point(pc)
                            self.meas_line1.setData(pos=np.array([pa_v, pb_v], dtype=np.float32))
                            self.meas_line2.setData(pos=np.array([pb_v, pc_v], dtype=np.float32))
                            self.meas_line1.setVisible(True)
                            self.meas_line2.setVisible(True)
                            v1 = pa - pb
                            v2 = pc - pb
                            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                            if n1 > 1e-4 and n2 > 1e-4:
                                cos_val = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
                                deg = np.degrees(np.arccos(cos_val))
                                self.meas_label.setData(pos=pb_v + np.array([0, 0, 20.0], dtype=np.float32), text=f"{deg:.1f}°")
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
        for item in self.plate_label_items:
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
            for item in getattr(self, "grf_shaft_items", []):
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
                pos_v = self.transform_point(pos)
                offset = np.array([0.0, 0.0, 18.0], dtype=np.float32)
                lbl_pos = pos_v + offset
                if name not in self.selected_marker_labels:
                    txt_item = gl.GLTextItem(
                        pos=lbl_pos,
                        text=name,
                        color=(1.0, 0.88, 0.1, 1.0),
                        font=lbl_font
                    )
                    txt_item.setDepthValue(210)
                    self.gl_view.addItem(txt_item)
                    self.selected_marker_labels[name] = txt_item
                else:
                    self.selected_marker_labels[name].setData(pos=lbl_pos, text=name)
                    self.selected_marker_labels[name].setVisible(True)

    def pick_marker_at(self, mouse_x: int, mouse_y: int) -> Optional[str]:
        """Find the nearest visible 3D marker within screen picking radius."""
        if not self.trial or not self.show_markers:
            return None

        w = self.gl_view.width()
        h = self.gl_view.height()
        if w <= 0 or h <= 0:
            return None

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

            pos_v = self.transform_point(pos3d)
            pt4 = QVector4D(float(pos_v[0]), float(pos_v[1]), float(pos_v[2]), 1.0)
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

        return best_marker

    def handle_3d_click(self, mouse_x: int, mouse_y: int, modifiers):
        """Interactive 3D raycast/projection marker picking."""
        best_marker = self.pick_marker_at(mouse_x, mouse_y)

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

    def handle_3d_right_click(self, mouse_x: int, mouse_y: int, global_pos: QPoint):
        """Handle right-click on 3D marker: select marker and request context menu."""
        marker = self.pick_marker_at(mouse_x, mouse_y)
        if marker:
            if marker not in self.selected_markers:
                self.selected_markers = [marker]
                self.selected_marker = marker
                self.set_frame(self.current_frame)
                self.markersSelected.emit(list(self.selected_markers))
            self.markerContextMenuRequested.emit(global_pos, list(self.selected_markers))

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

    def remove_marker(self, name: str):
        """Remove marker key from custom colors, selection, labels, and hidden sets."""
        self.custom_marker_colors.pop(name, None)
        if name in self.selected_markers:
            self.selected_markers.remove(name)
        if self.selected_marker == name:
            self.selected_marker = None
        self.hidden_markers.discard(name)
        if name in self.selected_marker_labels:
            lbl = self.selected_marker_labels.pop(name)
            try:
                self.gl_view.removeItem(lbl)
            except Exception:
                pass
        if self.active_measurement:
            if name in (
                self.active_measurement.get("m1"),
                self.active_measurement.get("m2"),
                self.active_measurement.get("ma"),
                self.active_measurement.get("mb"),
                self.active_measurement.get("mc")
            ):
                self.active_measurement = None
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
        qc = QColor(color_str)
        self.gl_view.setBackgroundColor(qc)
        lum = (qc.red() * 299 + qc.green() * 587 + qc.blue() * 114) / 1000
        new_is_dark = lum < 128
        if getattr(self, "is_dark", True) != new_is_dark:
            self.is_dark = new_is_dark
            self._build_global_axes()
            self._rebuild_force_plates()

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
        for item in self.plate_label_items:
            item.setVisible(show)

    def set_show_grf_vectors(self, show: bool):
        """Toggle ground reaction force vectors."""
        self.show_grf_vectors = show
        if not show:
            for item in self.grf_vector_items:
                item.setVisible(False)
            for item in getattr(self, "grf_shaft_items", []):
                item.setVisible(False)
            for item in self.grf_cone_items:
                item.setVisible(False)
        else:
            self.set_frame(self.current_frame)

    def set_marker_color(self, color_rgba: tuple):
        """Set default optical marker color (R, G, B, A)."""
        self.marker_color = tuple(color_rgba)
        self.set_frame(self.current_frame)

    def set_grf_color(self, color_rgba: tuple):
        """Set ground reaction force (GRF) vector color (R, G, B, A)."""
        self.grf_color = tuple(color_rgba)
        for line_item in self.grf_vector_items:
            try:
                line_item.setData(color=self.grf_color)
            except Exception:
                pass
        for shaft_item in getattr(self, "grf_shaft_items", []):
            try:
                shaft_item.setColor(self.grf_color)
            except Exception:
                pass
        for cone_item in self.grf_cone_items:
            try:
                cone_item.setColor(self.grf_color)
            except Exception:
                pass
        self.set_frame(self.current_frame)

    def set_z_up(self, z_up: bool):
        """Set whether global up axis is Z-Up (True) or Y-Up (False)."""
        new_val = bool(z_up)
        if self.z_up != new_val:
            self.z_up = new_val
            self._compute_orientation_matrix()
            self._build_global_axes()
            self._rebuild_force_plates()
            self.set_frame(self.current_frame)
            if self.trial:
                self.fit_view_to_data()

    def set_ground_rotation(self, rotation_deg: float):
        """Set ground orientation rotation in degrees (0, 90, 180, 270)."""
        rot_val = float(rotation_deg)
        if self.ground_rotation != rot_val:
            self.ground_rotation = rot_val
            self._compute_orientation_matrix()
            self._build_global_axes()
            self._rebuild_force_plates()
            self.set_frame(self.current_frame)
            if self.trial:
                self.fit_view_to_data()

    def apply_theme(self, theme_dict: dict):
        """Update 3D viewport background, grid, and auto-adjust marker and vector visibility for theme."""
        vp_bg = theme_dict.get("viewport_bg", "#151720")
        grid_col = theme_dict.get("grid_color", (80, 90, 110, 80))
        self.gl_view.setBackgroundColor(QColor(vp_bg))
        if self.grid_item:
            self.grid_item.setColor(grid_col)

        is_dark = theme_dict.get("is_dark", True)
        self.is_dark = is_dark
        if not is_dark:
            # Automatically switch marker color to black on light themes
            self.marker_color = (0.0, 0.0, 0.0, 1.0)
            # Ensure GRF vector is clearly visible on light themes
            if getattr(self, "grf_color", None) and np.mean(self.grf_color[:3]) > 0.85:
                self.grf_color = (1.0, 0.35, 0.08, 1.0)
        else:
            # Revert from black to white if returning to a dark theme
            if getattr(self, "marker_color", None) and self.marker_color[:3] == (0.0, 0.0, 0.0):
                self.marker_color = (1.0, 1.0, 1.0, 1.0)

        self._build_global_axes()
        self._rebuild_force_plates()
        self.set_frame(self.current_frame)


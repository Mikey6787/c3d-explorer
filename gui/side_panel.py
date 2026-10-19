"""Side panel widget containing Markers, Force Plates, and Events tabs."""

from typing import Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import Qt, Signal, QPoint, QEvent
from PySide6.QtGui import QColor, QBrush, QIcon, QPixmap, QPainter, QPen, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton, QLabel,
    QFrame, QScrollArea, QGroupBox, QMenu, QColorDialog, QInputDialog,
    QMessageBox, QAbstractItemView, QStyle, QStyleOptionViewItem, QToolTip
)

from core.data_models import C3DTrial, ForcePlatformData, C3DEvent


def make_color_icon(color: QColor) -> QIcon:
    """Create a clean circular color badge icon for the marker list."""
    pix = QPixmap(14, 14)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#4C566A"), 1))
    painter.setBrush(color)
    painter.drawEllipse(1, 1, 12, 12)
    painter.end()
    return QIcon(pix)


class SidePanel(QWidget):
    """
    Multi-tab inspector side panel:
    - Markers: Visibility toggles, search filter, individual color customization, rename support
    - Force Plates: Geometry, corner coordinates, live force readouts
    - Events: Interactive table of events with seek on click
    """
    markerVisibilityChanged = Signal(str, bool)
    markerSelected = Signal(str)
    markersSelected = Signal(list)                # Emits List[str] of selected marker names
    markerRenamed = Signal(str, str)              # Emits (old_name, new_name)
    markerColorChanged = Signal(str, object)      # Emits (marker_name, QColor or None)
    markersColorChanged = Signal(list, object)    # Emits (list_of_names, QColor or None)
    eventSelected = Signal(object)                # Emits C3DEvent
    addEventRequested = Signal()
    editEventRequested = Signal(object)           # Emits C3DEvent
    deleteEventRequested = Signal(object)         # Emits C3DEvent
    deleteEventsRequested = Signal(list)          # Emits List[C3DEvent]
    addMarkerRequested = Signal()
    deleteMarkerRequested = Signal(str)           # Emits marker name
    deleteMarkersRequested = Signal(list)         # Emits List[str] of marker names
    plotMarkerRequested = Signal(str)             # Emits marker name to plot (X, Y, Z)
    plotMarkersRequested = Signal(list)           # Emits List[str] of marker names to plot
    plotDistanceRequested = Signal(str, str)      # Emits (m1, m2) to plot Euclidean distance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trial: Optional[C3DTrial] = None
        self.current_frame: int = 0
        self.marker_colors: Dict[str, QColor] = {}
        self.default_marker_color: QColor = QColor("#FFFFFF")
        self.is_dark: bool = True
        self.current_theme_dict: Optional[dict] = None
        self._icon_press_marker: Optional[str] = None
        self._hovered_marker_icon: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        # Tab 1: Markers
        self.tab_markers = QWidget()
        self._setup_markers_tab()
        self.tabs.addTab(self.tab_markers, "Markers")

        # Tab 2: Force Plates
        self.tab_force_plates = QWidget()
        self._setup_force_plates_tab()
        self.tabs.addTab(self.tab_force_plates, "Force Plates")

        # Tab 3: Events
        self.tab_events = QWidget()
        self._setup_events_tab()
        self.tabs.addTab(self.tab_events, "Events")

    # ---------------------------------------------------------
    # TAB 1: MARKERS
    # ---------------------------------------------------------
    def _setup_markers_tab(self):
        layout = QVBoxLayout(self.tab_markers)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        # Filter box
        self.marker_search = QLineEdit()
        self.marker_search.setPlaceholderText("Search markers...")
        self.marker_search.textChanged.connect(self._filter_markers)
        layout.addWidget(self.marker_search)

        # Batch actions
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("Show All")
        btn_all.clicked.connect(lambda: self._set_all_markers_visibility(True))
        btn_layout.addWidget(btn_all)

        btn_none = QPushButton("Hide All")
        btn_none.clicked.connect(lambda: self._set_all_markers_visibility(False))
        btn_layout.addWidget(btn_none)
        layout.addLayout(btn_layout)

        # Table - Single column with checkboxes & color icons
        self.markers_table = QTableWidget()
        self.markers_table.setColumnCount(1)
        self.markers_table.setHorizontalHeaderLabels(["Marker Name"])
        self.markers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.markers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.markers_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.markers_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.markers_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.markers_table.customContextMenuRequested.connect(self._on_marker_context_menu)
        self.markers_table.itemChanged.connect(self._on_marker_item_changed)
        self.markers_table.itemDoubleClicked.connect(self._on_marker_double_clicked)
        self.markers_table.itemSelectionChanged.connect(self._on_marker_selection_changed)
        # Allow pressing Delete / Backspace key to delete selected markers
        old_markers_key = self.markers_table.keyPressEvent
        def _on_markers_key_press(event):
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self._action_delete_markers()
            else:
                old_markers_key(event)
        self.markers_table.keyPressEvent = _on_markers_key_press

        self.markers_table.setMouseTracking(True)
        self.markers_table.viewport().setMouseTracking(True)
        self.markers_table.viewport().installEventFilter(self)

        layout.addWidget(self.markers_table)

        # Quick action buttons for selected marker
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        self.btn_add = QPushButton("Add...")
        self.btn_add.setToolTip("Add a new marker with custom coordinates/file and color")
        self.btn_add.clicked.connect(self.addMarkerRequested.emit)
        action_layout.addWidget(self.btn_add)

        self.btn_color = QPushButton("Color...")
        self.btn_color.clicked.connect(self._action_change_marker_color)
        action_layout.addWidget(self.btn_color)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setToolTip("Delete selected marker(s)")
        self.btn_delete.clicked.connect(lambda checked=False: self._action_delete_markers())
        action_layout.addWidget(self.btn_delete)

        layout.addLayout(action_layout)

    # ---------------------------------------------------------
    # TAB 2: FORCE PLATES
    # ---------------------------------------------------------
    def _setup_force_plates_tab(self):
        layout = QVBoxLayout(self.tab_force_plates)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(6)

        self.fp_scroll = QScrollArea()
        self.fp_scroll.setWidgetResizable(True)
        self.fp_scroll_content = QWidget()
        self.fp_layout = QVBoxLayout(self.fp_scroll_content)
        self.fp_layout.setContentsMargins(4, 4, 4, 4)
        self.fp_layout.setSpacing(8)
        self.fp_scroll.setWidget(self.fp_scroll_content)
        layout.addWidget(self.fp_scroll)

    # ---------------------------------------------------------
    # TAB 3: EVENTS
    # ---------------------------------------------------------
    def _setup_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        self.events_table = QTableWidget()
        self.events_table.setColumnCount(3)
        self.events_table.setHorizontalHeaderLabels(["Event", "Time (s)", "Frame"])
        evt_header = self.events_table.horizontalHeader()
        evt_header.setSectionResizeMode(0, QHeaderView.Stretch)
        evt_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        evt_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        evt_header.setMinimumSectionSize(40)
        self.events_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.events_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.events_table.itemClicked.connect(self._on_event_clicked)
        self.events_table.itemDoubleClicked.connect(self._on_event_double_clicked)
        self.events_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.events_table.customContextMenuRequested.connect(self._on_event_context_menu)

        # Allow pressing Delete / Backspace key to delete selected events
        old_events_key = self.events_table.keyPressEvent
        def _on_events_key_press(event):
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self._action_delete_event()
            else:
                old_events_key(event)
        self.events_table.keyPressEvent = _on_events_key_press

        layout.addWidget(self.events_table)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        btn_add = QPushButton("+ Add")
        btn_add.setToolTip("Add new discrete C3D event")
        btn_add.clicked.connect(self.addEventRequested.emit)
        btn_layout.addWidget(btn_add)

        btn_edit = QPushButton("✎ Edit")
        btn_edit.setToolTip("Edit selected event")
        btn_edit.clicked.connect(self._action_edit_event)
        btn_layout.addWidget(btn_edit)

        btn_del = QPushButton("🗑 Delete")
        btn_del.setToolTip("Delete selected event")
        btn_del.clicked.connect(self._action_delete_event)
        btn_layout.addWidget(btn_del)

        layout.addLayout(btn_layout)

    # ---------------------------------------------------------
    # Populate Data
    # ---------------------------------------------------------
    def load_trial(self, trial: C3DTrial):
        """Populate all tabs with trial data."""
        self.trial = trial
        self.current_frame = 0
        self.marker_colors.clear()

        self._populate_markers()
        self._populate_force_plates()
        self._populate_events()

    def _populate_markers(self):
        self.markers_table.blockSignals(True)
        self.markers_table.setRowCount(0)
        if not self.trial:
            self.markers_table.blockSignals(False)
            return

        marker_names = sorted(list(self.trial.markers.keys()))
        self.markers_table.setRowCount(len(marker_names))

        for row, name in enumerate(marker_names):
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, name)
            name_item.setFlags(
                Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
            )
            name_item.setCheckState(Qt.Checked)

            col = self.marker_colors.get(name, self.default_marker_color)
            name_item.setIcon(make_color_icon(col))

            self.markers_table.setItem(row, 0, name_item)

        self.markers_table.blockSignals(False)

    def _populate_force_plates(self):
        while self.fp_layout.count():
            child = self.fp_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.trial or not self.trial.force_platforms:
            lbl = QLabel("No force platforms found in trial.")
            lbl.setStyleSheet("color: #8C96AB; font-style: italic; padding: 10px;")
            self.fp_layout.addWidget(lbl)
            self.fp_layout.addStretch()
            return

        self.fp_widgets = []
        is_dark = getattr(self, "is_dark", True)
        specs_color = "#8C96AB" if is_dark else "#6B7280"
        type_names = {1: "Type 1", 2: "Type 2", 3: "Type 3 (Kistler)", 4: "Type 4", 5: "Type 5 (Kistler)"}

        for fp in self.trial.force_platforms:
            box = QGroupBox(f"Force Platform #{fp.id}")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(6, 6, 6, 6)
            box_layout.setSpacing(4)

            type_label = type_names.get(fp.type, f"Type {fp.type}")
            specs = (
                f"<b>Type:</b> {type_label} &nbsp;|&nbsp; "
                f"<b>Size:</b> {fp.width:.0f} × {fp.length:.0f} mm<br>"
                f"<b>Origin:</b> [{fp.origin[0]:.1f}, {fp.origin[1]:.1f}, {fp.origin[2]:.1f}] mm"
            )
            lbl_specs = QLabel(specs)
            lbl_specs.setStyleSheet(f"color: {specs_color}; font-size: 11px; margin-bottom: 4px;")
            box_layout.addWidget(lbl_specs)

            lbl_data = QLabel()
            lbl_data.setText(self._render_force_plate_html(fp, 0))
            box_layout.addWidget(lbl_data)

            self.fp_layout.addWidget(box)
            self.fp_widgets.append((fp, lbl_specs, lbl_data))

        self.fp_layout.addStretch()

    def _render_force_plate_html(self, fp: ForcePlatformData, analog_idx: int) -> str:
        is_dark = getattr(self, "is_dark", True)
        accent = "#00ADB5" if is_dark else "#0284C7"
        text_color = "#ECEFF4" if is_dark else "#111827"
        label_color = "#88C0D0" if is_dark else "#374151"
        specs_color = "#8C96AB" if is_dark else "#6B7280"
        div_line = "#1E2230" if is_dark else "#E5E7EB"
        moments_color = "#88C0D0" if is_dark else "#0D9488"
        cop_color = "#A3BE8C" if is_dark else "#15803D"

        def fmt_val(v, unit="", dec=1):
            if v is None or np.isnan(v):
                return f"--- {unit}".strip()
            return f"{v:8.{dec}f} {unit}".strip()

        sections = []

        # 1. Ground Reaction Forces (Fx, Fy, Fz, Total)
        if fp.forces is not None:
            if analog_idx < len(fp.forces):
                fx = fp.forces[analog_idx, 0]
                fy = fp.forces[analog_idx, 1]
                fz = fp.forces[analog_idx, 2]
                f_tot = float(np.sqrt(fx * fx + fy * fy + fz * fz))
                fx_str = fmt_val(fx, "N", 1)
                fy_str = fmt_val(fy, "N", 1)
                fz_str = fmt_val(fz, "N", 1)
                ftot_str = fmt_val(f_tot, "N", 1)
            else:
                fx_str = fy_str = fz_str = ftot_str = "--- N"

            sections.append(f"""
              <div style="margin-top: 4px; padding-bottom: 2px; border-bottom: 1px solid {div_line}; color: {accent}; font-weight: bold; font-family: sans-serif; font-size: 10px; letter-spacing: 0.5px;">FORCES (GRF)</div>
              <table style="width: 100%; border-collapse: collapse; margin-top: 3px;">
                <tr><td style="color: {label_color}; width: 50px;"><b>Fx:</b></td><td style="text-align: right; color: {text_color};">{fx_str}</td></tr>
                <tr><td style="color: {label_color};"><b>Fy:</b></td><td style="text-align: right; color: {text_color};">{fy_str}</td></tr>
                <tr><td style="color: {label_color};"><b>Fz:</b></td><td style="text-align: right; color: {text_color};">{fz_str}</td></tr>
                <tr><td style="color: {specs_color};"><b>|F|:</b></td><td style="text-align: right; color: {accent}; font-weight: bold;">{ftot_str}</td></tr>
              </table>
            """)

        # 2. Moments (Mx, My, Mz)
        if fp.moments is not None:
            if analog_idx < len(fp.moments):
                mx = fp.moments[analog_idx, 0]
                my = fp.moments[analog_idx, 1]
                mz = fp.moments[analog_idx, 2]
                mx_str = fmt_val(mx, "N·mm", 1)
                my_str = fmt_val(my, "N·mm", 1)
                mz_str = fmt_val(mz, "N·mm", 1)
            else:
                mx_str = my_str = mz_str = "--- N·mm"

            sections.append(f"""
              <div style="margin-top: 8px; padding-bottom: 2px; border-bottom: 1px solid {div_line}; color: {moments_color}; font-weight: bold; font-family: sans-serif; font-size: 10px; letter-spacing: 0.5px;">MOMENTS</div>
              <table style="width: 100%; border-collapse: collapse; margin-top: 3px;">
                <tr><td style="color: {label_color}; width: 50px;"><b>Mx:</b></td><td style="text-align: right; color: {text_color};">{mx_str}</td></tr>
                <tr><td style="color: {label_color};"><b>My:</b></td><td style="text-align: right; color: {text_color};">{my_str}</td></tr>
                <tr><td style="color: {label_color};"><b>Mz:</b></td><td style="text-align: right; color: {text_color};">{mz_str}</td></tr>
              </table>
            """)

        # 3. Center of Pressure (COP) (Px, Py)
        if fp.cop is not None:
            if analog_idx < len(fp.cop):
                px = fp.cop[analog_idx, 0]
                py = fp.cop[analog_idx, 1]
                px_str = fmt_val(px, "mm", 1)
                py_str = fmt_val(py, "mm", 1)
            else:
                px_str = py_str = "--- mm"

            sections.append(f"""
              <div style="margin-top: 8px; padding-bottom: 2px; border-bottom: 1px solid {div_line}; color: {cop_color}; font-weight: bold; font-family: sans-serif; font-size: 10px; letter-spacing: 0.5px;">CENTER OF PRESSURE (COP)</div>
              <table style="width: 100%; border-collapse: collapse; margin-top: 3px;">
                <tr><td style="color: {label_color}; width: 50px;"><b>Px:</b></td><td style="text-align: right; color: {text_color};">{px_str}</td></tr>
                <tr><td style="color: {label_color};"><b>Py:</b></td><td style="text-align: right; color: {text_color};">{py_str}</td></tr>
              </table>
            """)

        if not sections:
            sections.append(f'<div style="color: {specs_color}; font-style: italic; margin-top: 6px;">No dynamic force signals recorded for this platform.</div>')

        body = "\n".join(sections)
        return f'<div style="font-family: monospace; font-size: 11px;">{body}</div>'

    def apply_theme(self, theme_dict: dict):
        """Update side panel theme styling and refresh force plate readouts."""
        self.current_theme_dict = theme_dict
        self.is_dark = theme_dict.get("is_dark", True)
        if hasattr(self, 'fp_widgets'):
            specs_color = "#8C96AB" if self.is_dark else "#6B7280"
            for fp, lbl_specs, lbl_data in self.fp_widgets:
                lbl_specs.setStyleSheet(f"color: {specs_color}; font-size: 11px; margin-bottom: 4px;")
        if hasattr(self, 'current_frame'):
            self.update_live_values(self.current_frame)

    def _populate_events(self):
        self.events_table.setRowCount(0)
        if not self.trial:
            return

        self.events_table.setRowCount(len(self.trial.events))
        for row, ev in enumerate(self.trial.events):
            name_item = QTableWidgetItem(ev.name)
            name_item.setToolTip(f"Event: {ev.name}\nContext: {ev.context}\nTime: {ev.time:.3f} s\nFrame: {ev.frame + 1}")
            name_item.setForeground(QBrush(QColor(ev.icon_color)))
            name_item.setData(Qt.UserRole, ev)
            self.events_table.setItem(row, 0, name_item)

            time_item = QTableWidgetItem(f"{ev.time:.3f}")
            time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.events_table.setItem(row, 1, time_item)

            frame_item = QTableWidgetItem(str(ev.frame + 1))
            frame_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.events_table.setItem(row, 2, frame_item)

    # ---------------------------------------------------------
    # Live Values Update
    # ---------------------------------------------------------
    def update_live_values(self, frame_idx: int):
        self.current_frame = frame_idx
        if not self.trial:
            return

        if hasattr(self, 'fp_widgets'):
            sub = max(1, self.trial.analog_subsamples)
            analog_idx = frame_idx * sub

            for fp, lbl_specs, lbl_data in self.fp_widgets:
                lbl_data.setText(self._render_force_plate_html(fp, analog_idx))

    # ---------------------------------------------------------
    # Marker Management (Rename, Color, Add)
    # ---------------------------------------------------------
    def get_selected_markers(self) -> List[str]:
        """Return list of all currently selected marker names in table (in row order)."""
        markers = []
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item and item.isSelected():
                name = item.data(Qt.UserRole) or item.text()
                if name and name not in markers:
                    markers.append(name)
        return markers

    def get_selected_marker(self) -> Optional[str]:
        items = self.get_selected_markers()
        return items[0] if items else None

    def add_marker_entry(self, name: str):
        """Add a newly created marker to the table."""
        self.markers_table.blockSignals(True)
        # Avoid duplicate row
        for r in range(self.markers_table.rowCount()):
            it = self.markers_table.item(r, 0)
            if it and (it.data(Qt.UserRole) == name or it.text() == name):
                self.markers_table.blockSignals(False)
                return

        row = self.markers_table.rowCount()
        self.markers_table.insertRow(row)

        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, name)
        name_item.setFlags(
            Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        )
        name_item.setCheckState(Qt.Checked)
        col = self.marker_colors.get(name, self.default_marker_color)
        name_item.setIcon(make_color_icon(col))
        self.markers_table.setItem(row, 0, name_item)
        self.markers_table.sortItems(0, Qt.AscendingOrder)
        self.markers_table.blockSignals(False)

    def remove_marker_entry(self, name: str):
        """Remove a marker entry from the table."""
        self.markers_table.blockSignals(True)
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item and (item.data(Qt.UserRole) == name or item.text() == name):
                self.markers_table.removeRow(row)
                self.marker_colors.pop(name, None)
                break
        self.markers_table.blockSignals(False)

    def rename_marker_entry(self, old_name: str, new_name: str):
        """Update display name in the table."""
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item and (item.data(Qt.UserRole) == old_name or item.text() == old_name):
                self.markers_table.blockSignals(True)
                item.setText(new_name)
                item.setData(Qt.UserRole, new_name)
                if old_name in self.marker_colors:
                    self.marker_colors[new_name] = self.marker_colors.pop(old_name)
                self.markers_table.blockSignals(False)
                break

    def set_marker_color_entry(self, name: str, color: Optional[QColor]):
        """Update color badge icon in the table for a single marker."""
        self.set_markers_color_entries([name], color)

    def set_markers_color_entries(self, names: List[str], color: Optional[QColor]):
        """Update color badge icons in the table for multiple markers efficiently."""
        name_set = set(names)
        display_col = color if color is not None else QColor("#FFFFFF")
        for name in names:
            if color is None:
                self.marker_colors.pop(name, None)
            else:
                self.marker_colors[name] = color

        icon = make_color_icon(display_col)
        self.markers_table.blockSignals(True)
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                m_name = item.data(Qt.UserRole) or item.text()
                if m_name in name_set:
                    item.setIcon(icon)
        self.markers_table.blockSignals(False)

    def set_default_marker_color(self, color: QColor):
        """Update the default marker color and refresh table icons for non-customized markers."""
        self.default_marker_color = color
        icon = make_color_icon(color)
        self.markers_table.blockSignals(True)
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                m_name = item.data(Qt.UserRole) or item.text()
                if m_name not in self.marker_colors:
                    item.setIcon(icon)
        self.markers_table.blockSignals(False)

    def _on_marker_context_menu(self, pos):
        clicked_item = self.markers_table.itemAt(pos)
        if not clicked_item:
            return

        clicked_name = clicked_item.data(Qt.UserRole) or clicked_item.text()
        selected_names = self.get_selected_markers()

        # If user right-clicked an item that is NOT in the current selection,
        # update selection to be just the right-clicked item.
        if clicked_name not in selected_names:
            self.markers_table.clearSelection()
            clicked_item.setSelected(True)
            selected_names = [clicked_name]

        global_pos = self.markers_table.viewport().mapToGlobal(pos)
        self.show_marker_context_menu(global_pos, selected_names, clicked_name)

    def create_marker_context_menu(
        self, selected_names: Optional[List[str]] = None, clicked_name: Optional[str] = None
    ) -> Tuple[Optional[QMenu], dict]:
        """Build and return the marker context menu and actions dictionary."""
        if not selected_names:
            selected_names = self.get_selected_markers()
        if not selected_names and clicked_name:
            selected_names = [clicked_name]
        if not selected_names:
            return None, {}

        if not clicked_name and selected_names:
            clicked_name = selected_names[0]

        # Make sure side panel table reflects the selection
        self.select_markers(selected_names)

        # Look up table item for single-marker visibility state
        clicked_item = None
        for row in range(self.markers_table.rowCount()):
            it = self.markers_table.item(row, 0)
            if it and (it.data(Qt.UserRole) == clicked_name or it.text() == clicked_name):
                clicked_item = it
                break

        count = len(selected_names)
        menu = QMenu(self)
        actions = {
            "count": count,
            "selected_names": selected_names,
            "clicked_name": clicked_name,
            "clicked_item": clicked_item
        }

        if count == 1:
            actions["act_plot"] = menu.addAction(f"Plot '{clicked_name}' (X, Y, Z)")
            menu.addSeparator()
            actions["act_color"] = menu.addAction(f"Change Color of '{clicked_name}'...")
            actions["act_reset"] = menu.addAction(f"Reset Color of '{clicked_name}' to Default")
            menu.addSeparator()
            actions["act_rename"] = menu.addAction(f"Rename '{clicked_name}'...")
            menu.addSeparator()
            is_checked = (clicked_item.checkState() == Qt.Checked) if clicked_item else True
            actions["is_checked"] = is_checked
            actions["act_toggle_vis"] = menu.addAction("Hide Marker" if is_checked else "Show Marker")
            menu.addSeparator()
            actions["act_delete"] = menu.addAction(f"Delete Marker '{clicked_name}'")
        else:
            actions["act_plot"] = menu.addAction(f"Plot Selected Markers ({count}) (X, Y, Z)")
            if count == 2:
                m1, m2 = selected_names[0], selected_names[1]
                actions["act_distance"] = menu.addAction(f"Distance ({m1} ↔ {m2})")
            menu.addSeparator()
            actions["act_color"] = menu.addAction(f"Change Color for {count} Selected Markers...")
            actions["act_reset"] = menu.addAction(f"Reset Color for {count} Selected Markers")
            menu.addSeparator()
            actions["act_show_selected"] = menu.addAction(f"Show Selected Markers ({count})")
            actions["act_hide_selected"] = menu.addAction(f"Hide Selected Markers ({count})")
            menu.addSeparator()
            actions["act_rename"] = menu.addAction(f"Rename '{clicked_name}'...")
            menu.addSeparator()
            actions["act_delete"] = menu.addAction(f"Delete {count} Selected Markers")

        return menu, actions

    def _handle_marker_context_menu_choice(self, chosen: QAction, actions: dict):
        """Execute selected context menu action."""
        count = actions["count"]
        clicked_name = actions["clicked_name"]
        selected_names = actions["selected_names"]
        clicked_item = actions.get("clicked_item")
        is_checked = actions.get("is_checked", True)

        if chosen == actions.get("act_plot"):
            if count == 1:
                self.plotMarkerRequested.emit(clicked_name)
            else:
                self.plotMarkersRequested.emit(selected_names)
        elif chosen == actions.get("act_distance"):
            if count == 2:
                self.plotDistanceRequested.emit(selected_names[0], selected_names[1])
        elif chosen == actions.get("act_color"):
            self._action_change_marker_color()
        elif chosen == actions.get("act_reset"):
            self._action_reset_marker_color()
        elif chosen == actions.get("act_rename"):
            self._action_rename_single_marker(clicked_name)
        elif chosen == actions.get("act_delete"):
            self._action_delete_markers(selected_names)
        elif count == 1 and chosen == actions.get("act_toggle_vis"):
            new_state = Qt.Unchecked if is_checked else Qt.Checked
            if clicked_item:
                clicked_item.setCheckState(new_state)
            self.markerVisibilityChanged.emit(clicked_name, new_state == Qt.Checked)
        elif count > 1 and chosen == actions.get("act_show_selected"):
            self._set_selected_markers_visibility(selected_names, True)
        elif count > 1 and chosen == actions.get("act_hide_selected"):
            self._set_selected_markers_visibility(selected_names, False)

    def show_marker_context_menu(
        self, global_pos: QPoint, selected_names: Optional[List[str]] = None, clicked_name: Optional[str] = None, _exec: bool = True
    ):
        menu, actions = self.create_marker_context_menu(selected_names, clicked_name)
        if not menu:
            return None, {}
        if _exec:
            chosen = menu.exec(global_pos)
            if chosen:
                self._handle_marker_context_menu_choice(chosen, actions)
        return menu, actions

    def _action_delete_markers(self, marker_names: Optional[List[str]] = None):
        if marker_names is not None and isinstance(marker_names, (list, tuple, set)):
            selected = list(marker_names)
        else:
            selected = self.get_selected_markers()
            if not selected:
                single = self.get_selected_marker()
                if single:
                    selected = [single]

        if selected:
            if len(selected) == 1:
                self.deleteMarkerRequested.emit(selected[0])
            else:
                self.deleteMarkersRequested.emit(selected)
        else:
            QMessageBox.information(self, "Delete Marker", "Please select one or more markers to delete.")

    def _action_rename_marker(self):
        cur_name = self.get_selected_marker()
        self._action_rename_single_marker(cur_name)

    def _action_rename_single_marker(self, cur_name: Optional[str]):
        if not cur_name or not self.trial:
            QMessageBox.information(self, "Rename Marker", "Please select a marker to rename.")
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Marker", f"Enter new name for marker '{cur_name}':", text=cur_name
        )
        if ok and new_name.strip() and new_name.strip() != cur_name:
            new_name = new_name.strip()
            if new_name in self.trial.markers:
                QMessageBox.warning(self, "Name Exists", f"Marker '{new_name}' already exists.")
                return

            self.rename_marker_entry(cur_name, new_name)
            self.markerRenamed.emit(cur_name, new_name)

    def _get_marker_icon_hit(self, pos: QPoint) -> Optional[Tuple[QTableWidgetItem, str]]:
        item = self.markers_table.itemAt(pos)
        if not item or item.column() != 0:
            return None
        if item.icon().isNull():
            return None
        opt = QStyleOptionViewItem()
        self.markers_table.initViewItemOption(opt)
        opt.rect = self.markers_table.visualItemRect(item)
        if not opt.rect.isValid():
            return None
        opt.features |= QStyleOptionViewItem.HasDecoration | QStyleOptionViewItem.HasCheckIndicator
        icon_rect = self.markers_table.style().subElementRect(
            QStyle.SE_ItemViewItemDecoration, opt, self.markers_table
        )
        if icon_rect.isEmpty():
            return None
        hit_rect = icon_rect.adjusted(-2, -2, 2, 2)
        if hit_rect.contains(pos):
            name = item.data(Qt.UserRole) or item.text()
            return item, name
        return None

    def eventFilter(self, watched, event):
        try:
            if hasattr(self, 'markers_table') and watched is self.markers_table.viewport():
                t = event.type()
                if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    hit = self._get_marker_icon_hit(pos)
                    if hit:
                        self._icon_press_marker = hit[1]
                        return True
                elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    if getattr(self, '_icon_press_marker', None) is not None:
                        marker = self._icon_press_marker
                        self._icon_press_marker = None
                        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                        hit = self._get_marker_icon_hit(pos)
                        if hit and hit[1] == marker:
                            self._action_change_marker_color_for(marker)
                        return True
                elif t == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    if self._get_marker_icon_hit(pos):
                        return True
                elif t == QEvent.MouseMove:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    hit = self._get_marker_icon_hit(pos)
                    if hit:
                        self.markers_table.viewport().setCursor(Qt.PointingHandCursor)
                        if self._hovered_marker_icon != hit[1]:
                            self._hovered_marker_icon = hit[1]
                            global_pos = (
                                event.globalPosition().toPoint()
                                if hasattr(event, "globalPosition")
                                else event.globalPos()
                            )
                            QToolTip.showText(
                                global_pos,
                                f"Click to change color for marker '{hit[1]}'",
                                self.markers_table.viewport(),
                            )
                    else:
                        self._hovered_marker_icon = None
                        if self.markers_table.viewport().cursor().shape() == Qt.PointingHandCursor:
                            self.markers_table.viewport().unsetCursor()
                            QToolTip.hideText()
                elif t == QEvent.Leave:
                    self._hovered_marker_icon = None
                    if self.markers_table.viewport().cursor().shape() == Qt.PointingHandCursor:
                        self.markers_table.viewport().unsetCursor()
                        QToolTip.hideText()
        except RuntimeError:
            pass
        return super().eventFilter(watched, event)

    def _action_change_marker_color(self, marker_names: Optional[List[str]] = None):
        if marker_names is not None and isinstance(marker_names, (list, tuple, set)):
            selected = list(marker_names)
        else:
            selected = self.get_selected_markers()
            if not selected:
                single = self.get_selected_marker()
                if single:
                    selected = [single]

        if not selected:
            QMessageBox.information(self, "Change Color", "Please select at least one marker to change its color.")
            return

        count = len(selected)
        if count == 1:
            initial_col = self.marker_colors.get(selected[0], self.default_marker_color)
            title = f"Select Color for Marker '{selected[0]}'"
        else:
            initial_col = self.marker_colors.get(selected[0], self.default_marker_color)
            title = f"Select Color for {count} Selected Markers"

        color = QColorDialog.getColor(initial_col, self, title)
        if color.isValid():
            self.set_markers_color_entries(selected, color)
            self.markersColorChanged.emit(selected, color)
            for name in selected:
                self.markerColorChanged.emit(name, color)

    def _action_change_marker_color_for(self, marker_name: str):
        selected = self.get_selected_markers()
        if marker_name in selected and len(selected) > 1:
            targets = selected
        else:
            targets = [marker_name]
            self.select_markers([marker_name], emit_signal=True)
        self._action_change_marker_color(targets)

    def _action_reset_marker_color(self):
        selected = self.get_selected_markers()
        if not selected:
            return

        self.set_markers_color_entries(selected, None)
        self.markersColorChanged.emit(selected, None)
        for name in selected:
            self.markerColorChanged.emit(name, None)

    def _set_selected_markers_visibility(self, names: List[str], visible: bool):
        name_set = set(names)
        state = Qt.Checked if visible else Qt.Unchecked
        self.markers_table.blockSignals(True)
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                m_name = item.data(Qt.UserRole) or item.text()
                if m_name in name_set:
                    item.setCheckState(state)
                    self.markerVisibilityChanged.emit(m_name, visible)
        self.markers_table.blockSignals(False)


    # ---------------------------------------------------------
    # Interactions
    # ---------------------------------------------------------
    def _filter_markers(self, text: str):
        t_low = text.strip().lower()
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                self.markers_table.setRowHidden(row, t_low not in item.text().lower())

    def _set_all_markers_visibility(self, visible: bool):
        self.markers_table.blockSignals(True)
        state = Qt.Checked if visible else Qt.Unchecked
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                item.setCheckState(state)
                self.markerVisibilityChanged.emit(item.text(), visible)
        self.markers_table.blockSignals(False)

    def _on_marker_double_clicked(self, item: QTableWidgetItem):
        if item:
            self.markers_table.editItem(item)

    def _on_marker_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0:
            return

        old_name = item.data(Qt.UserRole)
        new_name = item.text().strip()

        # Case 1: In-place text rename
        if old_name is not None and new_name != old_name:
            if not new_name:
                self.markers_table.blockSignals(True)
                item.setText(old_name)
                self.markers_table.blockSignals(False)
                QMessageBox.warning(self, "Rename Marker", "Marker name cannot be empty.")
                return

            if self.trial and new_name in self.trial.markers and new_name != old_name:
                self.markers_table.blockSignals(True)
                item.setText(old_name)
                self.markers_table.blockSignals(False)
                QMessageBox.warning(self, "Rename Marker", f"Marker '{new_name}' already exists.")
                return

            # Apply rename
            self.markers_table.blockSignals(True)
            item.setText(new_name)
            item.setData(Qt.UserRole, new_name)
            if old_name in self.marker_colors:
                self.marker_colors[new_name] = self.marker_colors.pop(old_name)
            self.markers_table.blockSignals(False)

            self.markerRenamed.emit(old_name, new_name)
            return

        # Case 2: Visibility checkbox toggle
        is_visible = (item.checkState() == Qt.Checked)
        marker_name = item.data(Qt.UserRole) or item.text()
        self.markerVisibilityChanged.emit(marker_name, is_visible)

    def _on_marker_selection_changed(self):
        names = self.get_selected_markers()
        count = len(names)
        if hasattr(self, 'btn_color'):
            if count > 1:
                self.btn_color.setText(f"Color ({count})...")
            else:
                self.btn_color.setText("Color...")

        self.markersSelected.emit(names)
        if names:
            self.markerSelected.emit(names[0])
        else:
            self.markerSelected.emit("")


    def select_markers(self, marker_names: List[str], emit_signal: bool = False):
        """Programmatically select the specified markers in the table."""
        self.markers_table.blockSignals(True)
        self.markers_table.clearSelection()
        name_set = set(marker_names)
        for row in range(self.markers_table.rowCount()):
            item = self.markers_table.item(row, 0)
            if item:
                name = item.data(Qt.UserRole) or item.text()
                if name in name_set:
                    item.setSelected(True)
        self.markers_table.blockSignals(False)
        if emit_signal:
            self._on_marker_selection_changed()

    def _on_event_clicked(self, item: QTableWidgetItem):
        row = item.row()
        name_item = self.events_table.item(row, 0)
        if name_item:
            ev = name_item.data(Qt.UserRole)
            if ev:
                self.eventSelected.emit(ev)

    def get_selected_event(self) -> Optional[C3DEvent]:
        sel = self.events_table.currentRow()
        if sel >= 0:
            item = self.events_table.item(sel, 0)
            if item:
                return item.data(Qt.UserRole)
        return None

    def get_selected_events(self) -> List[C3DEvent]:
        """Return list of all currently selected events from table rows."""
        rows = sorted(set(idx.row() for idx in self.events_table.selectedIndexes()))
        events: List[C3DEvent] = []
        for r in rows:
            item = self.events_table.item(r, 0)
            if item:
                ev = item.data(Qt.UserRole)
                if ev and ev not in events:
                    events.append(ev)
        return events

    def _action_edit_event(self):
        ev = self.get_selected_event()
        if ev:
            self.editEventRequested.emit(ev)
        else:
            QMessageBox.information(self, "Edit Event", "Please select an event from the table to edit.")

    def _action_delete_event(self):
        evs = self.get_selected_events()
        if not evs:
            # Fallback to single currentRow if selectionIndexes empty
            single = self.get_selected_event()
            if single:
                evs = [single]

        if evs:
            if len(evs) == 1:
                self.deleteEventRequested.emit(evs[0])
            else:
                self.deleteEventsRequested.emit(evs)
        else:
            QMessageBox.information(self, "Delete Event", "Please select one or more events from the table to delete.")

    def _on_event_double_clicked(self, item: QTableWidgetItem):
        ev = self.get_selected_event()
        if ev:
            self.editEventRequested.emit(ev)

    def _on_event_context_menu(self, pos):
        item = self.events_table.itemAt(pos)
        menu = QMenu(self)
        sel_evs = self.get_selected_events()
        if not sel_evs and item:
            single = self.get_selected_event()
            if single:
                sel_evs = [single]

        if sel_evs:
            if len(sel_evs) == 1:
                ev = sel_evs[0]
                act_edit = menu.addAction(f"Edit Event '{ev.display_name}'...")
                act_edit.triggered.connect(lambda: self.editEventRequested.emit(ev))
                act_del = menu.addAction(f"Delete Event '{ev.display_name}'")
                act_del.triggered.connect(self._action_delete_event)
                act_jump = menu.addAction(f"Jump to Event Frame ({ev.frame})")
                act_jump.triggered.connect(lambda: self.eventSelected.emit(ev))
                menu.addSeparator()
            else:
                act_del = menu.addAction(f"Delete {len(sel_evs)} Selected Events")
                act_del.triggered.connect(self._action_delete_event)
                menu.addSeparator()

        act_add = menu.addAction("Add New Event...")
        act_add.triggered.connect(self.addEventRequested.emit)
        menu.exec(self.events_table.viewport().mapToGlobal(pos))


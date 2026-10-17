"""Side panel widget containing Markers, Force Plates, and Events tabs."""

from typing import Dict, List, Optional
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QIcon, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton, QLabel,
    QFrame, QScrollArea, QGroupBox, QMenu, QColorDialog, QInputDialog,
    QMessageBox, QAbstractItemView
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trial: Optional[C3DTrial] = None
        self.current_frame: int = 0
        self.marker_colors: Dict[str, QColor] = {}
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
        layout.addWidget(self.markers_table)

        # Quick action buttons for selected marker
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        self.btn_rename = QPushButton("Rename...")
        self.btn_rename.clicked.connect(self._action_rename_marker)
        action_layout.addWidget(self.btn_rename)

        self.btn_color = QPushButton("Color...")
        self.btn_color.clicked.connect(self._action_change_marker_color)
        action_layout.addWidget(self.btn_color)

        self.btn_reset_color = QPushButton("Reset Color")
        self.btn_reset_color.clicked.connect(self._action_reset_marker_color)
        action_layout.addWidget(self.btn_reset_color)

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
        self.events_table.setColumnCount(4)
        self.events_table.setHorizontalHeaderLabels(["Event", "Context", "Time (s)", "Frame"])
        self.events_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.events_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.events_table.setSelectionMode(QTableWidget.SingleSelection)
        self.events_table.itemClicked.connect(self._on_event_clicked)
        self.events_table.itemDoubleClicked.connect(self._on_event_double_clicked)
        self.events_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.events_table.customContextMenuRequested.connect(self._on_event_context_menu)
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

            col = self.marker_colors.get(name, QColor("#FFFFFF"))
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
        for fp in self.trial.force_platforms:
            box = QGroupBox(f"Force Platform #{fp.id}")
            box_layout = QVBoxLayout(box)
            box_layout.setSpacing(4)

            specs = (
                f"<b>Type:</b> {fp.type} &nbsp;|&nbsp; "
                f"<b>Size:</b> {fp.width:.0f} × {fp.length:.0f} mm<br>"
                f"<b>Origin:</b> [{fp.origin[0]:.1f}, {fp.origin[1]:.1f}, {fp.origin[2]:.1f}] mm"
            )
            lbl_specs = QLabel(specs)
            lbl_specs.setStyleSheet("color: #D8DEE9; font-size: 11px;")
            box_layout.addWidget(lbl_specs)

            lbl_force = QLabel("Fx: 0.0 N  |  Fy: 0.0 N  |  Fz: 0.0 N")
            lbl_force.setStyleSheet("color: #00ADB5; font-weight: 600; font-family: monospace; font-size: 12px;")
            box_layout.addWidget(lbl_force)

            self.fp_layout.addWidget(box)
            self.fp_widgets.append((fp, lbl_force))

        self.fp_layout.addStretch()

    def _populate_events(self):
        self.events_table.setRowCount(0)
        if not self.trial:
            return

        self.events_table.setRowCount(len(self.trial.events))
        for row, ev in enumerate(self.trial.events):
            name_item = QTableWidgetItem(ev.name)
            name_item.setForeground(QBrush(QColor(ev.icon_color)))
            name_item.setData(Qt.UserRole, ev)
            self.events_table.setItem(row, 0, name_item)

            ctx_item = QTableWidgetItem(ev.context)
            self.events_table.setItem(row, 1, ctx_item)

            time_item = QTableWidgetItem(f"{ev.time:.3f}")
            time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.events_table.setItem(row, 2, time_item)

            frame_item = QTableWidgetItem(str(ev.frame))
            frame_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.events_table.setItem(row, 3, frame_item)

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

            for fp, lbl in self.fp_widgets:
                if fp.forces is not None and analog_idx < len(fp.forces):
                    fx = fp.forces[analog_idx, 0]
                    fy = fp.forces[analog_idx, 1]
                    fz = fp.forces[analog_idx, 2]
                    f_total = np.sqrt(fx*fx + fy*fy + fz*fz)
                    lbl.setText(f"Fx: {fx:6.1f} N | Fy: {fy:6.1f} N | Fz: {fz:6.1f} N (Total: {f_total:6.1f} N)")
                else:
                    lbl.setText("Fx: --- N | Fy: --- N | Fz: --- N")

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
        row = self.markers_table.rowCount()
        self.markers_table.insertRow(row)

        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, name)
        name_item.setFlags(
            Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        )
        name_item.setCheckState(Qt.Checked)
        name_item.setIcon(make_color_icon(QColor("#00ADB5")))
        self.markers_table.setItem(row, 0, name_item)
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

        count = len(selected_names)
        menu = QMenu(self)

        if count == 1:
            act_color = menu.addAction(f"Change Color of '{clicked_name}'...")
            act_reset = menu.addAction(f"Reset Color of '{clicked_name}' to Default")
            menu.addSeparator()
            act_rename = menu.addAction(f"Rename '{clicked_name}'...")
            menu.addSeparator()
            is_checked = clicked_item.checkState() == Qt.Checked
            act_toggle_vis = menu.addAction("Hide Marker" if is_checked else "Show Marker")
            act_show_selected = None
            act_hide_selected = None
        else:
            act_color = menu.addAction(f"Change Color for {count} Selected Markers...")
            act_reset = menu.addAction(f"Reset Color for {count} Selected Markers")
            menu.addSeparator()
            act_show_selected = menu.addAction(f"Show Selected Markers ({count})")
            act_hide_selected = menu.addAction(f"Hide Selected Markers ({count})")
            menu.addSeparator()
            act_rename = menu.addAction(f"Rename '{clicked_name}'...")
            act_toggle_vis = None

        chosen = menu.exec(self.markers_table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_color:
            self._action_change_marker_color()
        elif chosen == act_reset:
            self._action_reset_marker_color()
        elif chosen == act_rename:
            self._action_rename_single_marker(clicked_name)
        elif count == 1 and chosen == act_toggle_vis:
            new_state = Qt.Unchecked if is_checked else Qt.Checked
            clicked_item.setCheckState(new_state)
            self.markerVisibilityChanged.emit(clicked_name, new_state == Qt.Checked)
        elif count > 1 and chosen == act_show_selected:
            self._set_selected_markers_visibility(selected_names, True)
        elif count > 1 and chosen == act_hide_selected:
            self._set_selected_markers_visibility(selected_names, False)

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

    def _action_change_marker_color(self):
        selected = self.get_selected_markers()
        if not selected:
            QMessageBox.information(self, "Change Color", "Please select at least one marker to change its color.")
            return

        count = len(selected)
        if count == 1:
            initial_col = self.marker_colors.get(selected[0], QColor("#FFFFFF"))
            title = f"Select Color for Marker '{selected[0]}'"
        else:
            initial_col = self.marker_colors.get(selected[0], QColor("#FFFFFF"))
            title = f"Select Color for {count} Selected Markers"

        color = QColorDialog.getColor(initial_col, self, title)
        if color.isValid():
            self.set_markers_color_entries(selected, color)
            self.markersColorChanged.emit(selected, color)
            for name in selected:
                self.markerColorChanged.emit(name, color)

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
        if hasattr(self, 'btn_color') and hasattr(self, 'btn_reset_color'):
            if count > 1:
                self.btn_color.setText(f"Color ({count})...")
                self.btn_reset_color.setText(f"Reset ({count})")
            else:
                self.btn_color.setText("Color...")
                self.btn_reset_color.setText("Reset Color")

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

    def _action_edit_event(self):
        ev = self.get_selected_event()
        if ev:
            self.editEventRequested.emit(ev)
        else:
            QMessageBox.information(self, "Edit Event", "Please select an event from the table to edit.")

    def _action_delete_event(self):
        ev = self.get_selected_event()
        if ev:
            self.deleteEventRequested.emit(ev)
        else:
            QMessageBox.information(self, "Delete Event", "Please select an event from the table to delete.")

    def _on_event_double_clicked(self, item: QTableWidgetItem):
        ev = self.get_selected_event()
        if ev:
            self.editEventRequested.emit(ev)

    def _on_event_context_menu(self, pos):
        item = self.events_table.itemAt(pos)
        menu = QMenu(self)
        if item:
            ev = self.get_selected_event()
            if ev:
                act_edit = menu.addAction(f"Edit Event '{ev.display_name}'...")
                act_edit.triggered.connect(lambda: self.editEventRequested.emit(ev))
                act_del = menu.addAction(f"Delete Event '{ev.display_name}'")
                act_del.triggered.connect(lambda: self.deleteEventRequested.emit(ev))
                act_jump = menu.addAction(f"Jump to Event Frame ({ev.frame})")
                act_jump.triggered.connect(lambda: self.eventSelected.emit(ev))
                menu.addSeparator()

        act_add = menu.addAction("Add New Event...")
        act_add.triggered.connect(self.addEventRequested.emit)
        menu.exec(self.events_table.viewport().mapToGlobal(pos))


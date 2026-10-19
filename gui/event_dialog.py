"""C3D Event Dialogs for adding, editing, and managing discrete events."""

from typing import Optional, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton, QLabel,
    QMessageBox, QColorDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMenu
)

from core.data_models import C3DTrial, C3DEvent
from core.c3d_reader import get_event_color


class EventEditDialog(QDialog):
    """Dialog to create or edit a discrete C3D event with all parameters supported by the C3D format."""

    def __init__(
        self,
        trial: Optional[C3DTrial] = None,
        current_frame: int = 0,
        event_to_edit: Optional[C3DEvent] = None,
        parent=None
    ):
        super().__init__(parent)
        self.trial = trial
        self.current_frame = current_frame
        self.event_to_edit = event_to_edit

        self.point_rate = trial.point_rate if trial and trial.point_rate > 0 else 100.0
        self.max_frame = (trial.point_frame_count - 1) if trial and trial.point_frame_count > 0 else 999999
        self.max_time = (self.max_frame / self.point_rate) if self.point_rate > 0 else 9999.0

        is_edit = event_to_edit is not None
        self.setWindowTitle("Edit C3D Event" if is_edit else "Add C3D Event")
        self.resize(480, 370)

        # Active color
        if is_edit and event_to_edit.icon_color:
            self._color = QColor(event_to_edit.icon_color)
        else:
            self._color = QColor("#FF5252")

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        # 1. Event Name / Label
        self.combo_name = QComboBox()
        self.combo_name.setEditable(True)
        self.combo_name.setMinimumWidth(260)
        self.combo_name.addItems([
            "Foot Strike",
            "Foot Off",
            "Heel Strike",
            "Toe Off",
            "Initial Contact",
            "Event",
            "Start",
            "End"
        ])
        self.combo_name.currentTextChanged.connect(self._on_name_changed)
        form.addRow("<b>Event Label:</b>", self.combo_name)

        # 2. Context / Leg
        self.combo_context = QComboBox()
        self.combo_context.setEditable(True)
        self.combo_context.setMinimumWidth(260)
        self.combo_context.addItems(["Right", "Left", "General"])
        self.combo_context.currentTextChanged.connect(self._on_context_changed)
        form.addRow("<b>Context / Leg:</b>", self.combo_context)

        # 3. Frame Number (1-based for the user)
        self.spin_frame = QSpinBox()
        self.spin_frame.setRange(1, self.max_frame + 1)
        self.spin_frame.setValue(self.current_frame + 1)
        self.spin_frame.valueChanged.connect(self._on_frame_changed)
        form.addRow("<b>Frame:</b>", self.spin_frame)

        # 4. Time (seconds, starts from 0.0)
        self.spin_time = QDoubleSpinBox()
        self.spin_time.setRange(0.0, self.max_time)
        self.spin_time.setDecimals(4)
        self.spin_time.setSingleStep(1.0 / self.point_rate)
        self.spin_time.setSuffix(" s")
        self.spin_time.setValue(self.current_frame / self.point_rate)
        self.spin_time.valueChanged.connect(self._on_time_changed)
        form.addRow("<b>Time:</b>", self.spin_time)

        # 5. Subject
        self.txt_subject = QLineEdit()
        self.txt_subject.setPlaceholderText("Optional subject ID (e.g. Subject1)")
        form.addRow("Subject:", self.txt_subject)

        # 6. Description
        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("Optional description (e.g. Right Heel Strike)")
        form.addRow("Description:", self.txt_desc)

        # Internal Event ID (managed automatically in background according to C3D standard)
        self.spin_id = QSpinBox()
        self.spin_id.setRange(0, 9999)
        self.spin_id.setValue(0)

        # 7. Badge Color
        color_layout = QHBoxLayout()
        self.btn_color = QPushButton()
        self.btn_color.setFixedHeight(26)
        self._update_color_button()
        self.btn_color.clicked.connect(self._pick_color)
        color_layout.addWidget(self.btn_color)

        btn_auto_color = QPushButton("Auto Color")
        btn_auto_color.setToolTip("Pick color automatically based on Context (Red for Right, Cyan for Left, Amber for General)")
        btn_auto_color.clicked.connect(self._auto_pick_color)
        color_layout.addWidget(btn_auto_color)
        form.addRow("Badge Color:", color_layout)

        layout.addLayout(form)
        layout.addStretch()

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Save Event" if self.event_to_edit else "Add Event")
        btn_save.setDefault(True)
        btn_save.setStyleSheet("background-color: #00ADB5; color: white; font-weight: bold; padding: 6px 14px;")
        btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_data(self):
        if self.event_to_edit:
            ev = self.event_to_edit
            self.combo_name.setCurrentText(ev.name)
            if self.combo_name.lineEdit():
                self.combo_name.lineEdit().setCursorPosition(0)
            self.combo_context.setCurrentText(ev.context if ev.context else "General")
            if self.combo_context.lineEdit():
                self.combo_context.lineEdit().setCursorPosition(0)
            self.spin_frame.setValue(ev.frame + 1)
            self.spin_time.setValue(ev.time)
            self.txt_subject.setText(getattr(ev, "subject", "") or "")
            self.txt_desc.setText(getattr(ev, "description", "") or "")
            self.spin_id.setValue(getattr(ev, "event_id", 0) or 0)
            if ev.icon_color:
                self._color = QColor(ev.icon_color)
                self._update_color_button()
        else:
            # Prefill default subject if trial has existing events
            if self.trial and self.trial.events:
                existing_subjects = [e.subject for e in self.trial.events if e.subject]
                if existing_subjects:
                    self.txt_subject.setText(existing_subjects[0])
            self._auto_pick_color()

    def _on_frame_changed(self, frame: int):
        self.spin_time.blockSignals(True)
        self.spin_time.setValue(max(0.0, (frame - 1) / self.point_rate))
        self.spin_time.blockSignals(False)

    def _on_time_changed(self, t: float):
        self.spin_frame.blockSignals(True)
        f = int(round(t * self.point_rate))
        self.spin_frame.setValue(max(1, min(self.max_frame + 1, f + 1)))
        self.spin_frame.blockSignals(False)

    def _on_context_changed(self, ctx: str):
        # Only auto-pick color if user hasn't explicitly customized
        self._auto_pick_color()

    def _on_name_changed(self, name: str):
        self._auto_pick_color()
        if not self.event_to_edit:
            norm = name.strip().lower()
            if "strike" in norm or "contact" in norm or "hs" in norm:
                self.spin_id.setValue(1)
            elif "off" in norm or "to" in norm:
                self.spin_id.setValue(2)
            else:
                self.spin_id.setValue(0)

    def _auto_pick_color(self):
        ctx = self.combo_context.currentText().strip()
        lbl = self.combo_name.currentText().strip()
        hex_col = get_event_color(lbl, ctx)
        self._color = QColor(hex_col)
        self._update_color_button()

    def _pick_color(self):
        c = QColorDialog.getColor(self._color, self, "Select Event Badge Color")
        if c.isValid():
            self._color = c
            self._update_color_button()

    def _update_color_button(self):
        self.btn_color.setStyleSheet(
            f"background-color: {self._color.name()}; border: 1px solid #555; border-radius: 4px;"
        )

    def _on_save(self):
        lbl = self.combo_name.currentText().strip()
        if not lbl:
            QMessageBox.warning(self, "Invalid Name", "Please enter an event label.")
            return
        self.accept()

    def get_event(self) -> C3DEvent:
        """Construct C3DEvent object from dialog inputs."""
        lbl = self.combo_name.currentText().strip()
        ctx = self.combo_context.currentText().strip()
        f = self.spin_frame.value() - 1
        t = self.spin_time.value()
        subj = self.txt_subject.text().strip()
        desc = self.txt_desc.text().strip()
        ev_id = self.spin_id.value()
        color = self._color.name()

        return C3DEvent(
            name=lbl,
            time=t,
            frame=f,
            subject=subj,
            context=ctx,
            description=desc,
            event_id=ev_id,
            icon_color=color
        )


class EventManagerDialog(QDialog):
    """Full table event manager for reviewing, adding, editing, and deleting events."""
    eventListChanged = Signal()
    seekRequested = Signal(int)

    def __init__(self, trial: C3DTrial, current_frame: int = 0, parent=None):
        super().__init__(parent)
        self.trial = trial
        self.current_frame = current_frame

        self.setWindowTitle("C3D Event Manager")
        self.resize(750, 420)

        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header info
        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #00ADB5; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_info)

        # Events Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Event", "Time (s)", "Frame", "Subject", "Description"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(self._on_edit_selected)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        # Allow pressing Delete / Backspace key to delete selected events
        old_mgr_key = self.table.keyPressEvent
        def _on_mgr_key_press(event):
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self._on_delete_selected()
            else:
                old_mgr_key(event)
        self.table.keyPressEvent = _on_mgr_key_press

        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_add = QPushButton("+ Add Event...")
        btn_add.setStyleSheet("background-color: #00ADB5; color: white; font-weight: bold; padding: 5px 12px;")
        btn_add.clicked.connect(self._on_add_event)
        btn_layout.addWidget(btn_add)

        btn_edit = QPushButton("✎ Edit Selected...")
        btn_edit.clicked.connect(self._on_edit_selected)
        btn_layout.addWidget(btn_edit)

        btn_delete = QPushButton("🗑 Delete Selected")
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_layout.addWidget(btn_delete)

        btn_seek = QPushButton("Jump to Frame")
        btn_seek.clicked.connect(self._on_jump_to_event)
        btn_layout.addWidget(btn_seek)

        btn_layout.addStretch()

        btn_clear = QPushButton("Clear All Events")
        btn_clear.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(btn_clear)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _refresh_table(self):
        self.table.setRowCount(0)
        if not self.trial:
            self.lbl_info.setText("No trial loaded.")
            return

        self.lbl_info.setText(
            f"Total Events: {len(self.trial.events)}  |  Point Rate: {round(self.trial.point_rate):.0f} Hz  |  Current Frame: {self.current_frame + 1}"
        )

        self.table.setRowCount(len(self.trial.events))
        for row, ev in enumerate(self.trial.events):
            # Name with color badge
            name_item = QTableWidgetItem(ev.name)
            name_item.setForeground(QBrush(QColor(ev.icon_color)))
            name_item.setData(Qt.UserRole, ev)
            self.table.setItem(row, 0, name_item)

            # Time
            t_item = QTableWidgetItem(f"{ev.time:.4f}")
            t_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 1, t_item)

            # Frame
            f_item = QTableWidgetItem(str(ev.frame + 1))
            f_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, f_item)

            # Subject
            subj_item = QTableWidgetItem(getattr(ev, "subject", "") or "")
            self.table.setItem(row, 3, subj_item)

            # Description
            desc_item = QTableWidgetItem(getattr(ev, "description", "") or "")
            self.table.setItem(row, 4, desc_item)

    def _get_selected_event(self) -> Optional[C3DEvent]:
        sel = self.table.currentRow()
        if sel < 0 or sel >= len(self.trial.events):
            return None
        return self.trial.events[sel]

    def _on_add_event(self):
        dlg = EventEditDialog(trial=self.trial, current_frame=self.current_frame, parent=self)
        if dlg.exec():
            new_ev = dlg.get_event()
            self.trial.events.append(new_ev)
            self.trial.events.sort(key=lambda e: e.time)
            self._refresh_table()
            self.eventListChanged.emit()

    def _on_edit_selected(self):
        ev = self._get_selected_event()
        if not ev:
            QMessageBox.information(self, "Edit Event", "Please select an event to edit.")
            return

        dlg = EventEditDialog(trial=self.trial, current_frame=ev.frame, event_to_edit=ev, parent=self)
        if dlg.exec():
            idx = self.trial.events.index(ev)
            updated_ev = dlg.get_event()
            self.trial.events[idx] = updated_ev
            self.trial.events.sort(key=lambda e: e.time)
            self._refresh_table()
            self.eventListChanged.emit()

    def _get_selected_events(self) -> List[C3DEvent]:
        """Return list of all currently selected events from table rows."""
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        events: List[C3DEvent] = []
        for r in rows:
            item = self.table.item(r, 0)
            if item:
                ev = item.data(Qt.UserRole)
                if ev and ev not in events:
                    events.append(ev)
        return events

    def _on_delete_selected(self):
        evs = self._get_selected_events()
        if not evs:
            single = self._get_selected_event()
            if single:
                evs = [single]

        if not evs:
            QMessageBox.information(self, "Delete Event", "Please select one or more events to delete.")
            return

        if len(evs) == 1:
            msg = f"Are you sure you want to delete event '{evs[0].display_name}' at frame {evs[0].frame + 1}?"
        else:
            msg = f"Are you sure you want to delete all {len(evs)} selected events?"

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            msg,
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            for ev in evs:
                if ev in self.trial.events:
                    self.trial.events.remove(ev)
            self._refresh_table()
            self.eventListChanged.emit()

    def _on_jump_to_event(self):
        ev = self._get_selected_event()
        if ev:
            self.seekRequested.emit(ev.frame)

    def _on_clear_all(self):
        if not self.trial or not self.trial.events:
            return

        confirm = QMessageBox.question(
            self,
            "Clear All Events",
            f"Are you sure you want to remove all {len(self.trial.events)} events?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.trial.events.clear()
            self._refresh_table()
            self.eventListChanged.emit()

    def _on_context_menu(self, pos):
        item = self.table.itemAt(pos)
        menu = QMenu(self)
        sel_evs = self._get_selected_events()
        if not sel_evs and item:
            single = self._get_selected_event()
            if single:
                sel_evs = [single]

        if sel_evs:
            if len(sel_evs) == 1:
                ev = sel_evs[0]
                act_edit = menu.addAction(f"Edit '{ev.display_name}'...")
                act_edit.triggered.connect(self._on_edit_selected)
                act_del = menu.addAction(f"Delete '{ev.display_name}'")
                act_del.triggered.connect(self._on_delete_selected)
                act_jump = menu.addAction(f"Jump to Frame {ev.frame + 1}")
                act_jump.triggered.connect(self._on_jump_to_event)
                menu.addSeparator()
            else:
                act_del = menu.addAction(f"Delete {len(sel_evs)} Selected Events")
                act_del.triggered.connect(self._on_delete_selected)
                menu.addSeparator()

        act_add = menu.addAction("Add New Event...")
        act_add.triggered.connect(self._on_add_event)
        menu.exec(self.table.viewport().mapToGlobal(pos))

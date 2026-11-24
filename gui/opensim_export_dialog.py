"""OpenSim Export Dialog for exporting .trc, _grf.mot, and _grf.xml files (single trial & batch)."""

import copy
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QPushButton, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QWidget, QFileDialog,
    QMessageBox, QProgressBar, QTextEdit, QListWidget, QAbstractItemView
)

from core.data_models import C3DTrial
from core.c3d_reader import C3DReader
from core.opensim_exporter import (
    COORDINATE_PRESETS,
    ExternalForceConfig,
    build_axis_transform_matrix,
    default_external_forces_for_count,
    parse_external_loads_xml,
    export_trial_to_opensim,
)
from gui.toggle_switch import ToggleSwitch


AXIS_OPTIONS = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
COMMON_OPENSIM_BODIES = [
    "calcn_r", "calcn_l", "toes_r", "toes_l",
    "pelvis", "torso", "femur_r", "femur_l",
    "tibia_r", "tibia_l", "hand_r", "hand_l", "ground"
]


@dataclass
class BatchRule:
    """Conditional export rule matching trial filename substring -> GRF settings."""
    pattern: str = ""
    export_grf: bool = True
    external_forces: List[ExternalForceConfig] = field(default_factory=list)


def _centered_toggle(checked: bool = False) -> Tuple[QWidget, ToggleSwitch]:
    """Wrap a ToggleSwitch in a centered container widget for table cells."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignCenter)
    toggle = ToggleSwitch()
    toggle.setChecked(checked)
    layout.addWidget(toggle)
    return container, toggle


def _summarize_forces(forces: List[ExternalForceConfig]) -> str:
    if not forces:
        return "None"
    parts = []
    for cfg in forces:
        state = " (disabled)" if cfg.is_disabled else ""
        parts.append(f"P{cfg.plate_index + 1}: {cfg.applied_to_body}{state}")
    return ", ".join(parts)


class OpenSimBatchWorker(QThread):
    """Background worker for batch-exporting multiple C3D files to OpenSim formats."""
    progressChanged = Signal(int, int, str)
    fileFinished = Signal(str, bool, str)
    batchCompleted = Signal(int, int)

    def __init__(
        self,
        files: List[str],
        output_dir: str,
        same_as_input: bool,
        transform_matrix,
        trc_units: str,
        export_grf: bool,
        external_forces: List[ExternalForceConfig],
        rules: Optional[List[BatchRule]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.files = list(files)
        self.output_dir = output_dir
        self.same_as_input = same_as_input
        self.transform_matrix = transform_matrix
        self.trc_units = trc_units
        self.export_grf = export_grf
        self.external_forces = list(external_forces)
        self.rules = list(rules) if rules else []
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _resolve_settings_for_file(self, fname: str) -> Tuple[bool, List[ExternalForceConfig], Optional[str]]:
        fname_low = fname.lower()
        for rule in self.rules:
            pat = rule.pattern.strip()
            if pat and pat.lower() in fname_low:
                return rule.export_grf, copy.deepcopy(rule.external_forces), pat
        return self.export_grf, self.external_forces, None

    def run(self):
        reader = C3DReader()
        succeeded = 0
        failed = 0
        total = len(self.files)

        for idx, fpath in enumerate(self.files):
            if self._cancelled:
                break
            fname = os.path.basename(fpath)
            self.progressChanged.emit(idx, total, fname)
            try:
                trial = reader.read(fpath)
                base_name = os.path.splitext(fname)[0]
                target_dir = os.path.dirname(fpath) if self.same_as_input else self.output_dir
                use_grf, ef_cfg, matched_rule = self._resolve_settings_for_file(fname)

                out = export_trial_to_opensim(
                    trial=trial,
                    output_dir=target_dir,
                    base_name=base_name,
                    transform_matrix=self.transform_matrix,
                    trc_units=self.trc_units,
                    export_grf=use_grf,
                    external_forces=ef_cfg,
                )
                created = ", ".join(os.path.basename(p) for p in out.values())
                rule_tag = f"[Rule: '{matched_rule}'] " if matched_rule else ""
                self.fileFinished.emit(fname, True, f"{rule_tag}Exported: {created}")
                succeeded += 1
            except Exception as e:
                self.fileFinished.emit(fname, False, str(e))
                failed += 1

        self.progressChanged.emit(total, total, "Done")
        self.batchCompleted.emit(succeeded, failed)


class OpenSimExportDialog(QDialog):
    """
    Dialog for exporting motion capture (.trc) and ground reaction force (.mot + ExternalLoads .xml)
    files for OpenSim, supporting coordinate system mapping and conditional batch processing.
    """

    def __init__(
        self,
        trial: Optional[C3DTrial] = None,
        trim_range: Optional[Tuple[int, int]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.trial = trial
        self.trim_range = trim_range
        self._worker: Optional[OpenSimBatchWorker] = None
        self._syncing_preset = False

        self.setWindowTitle("Export for OpenSim (.trc, .mot, .xml)")
        self.resize(840, 760)
        self.setModal(False)
        self._setup_ui()
        self._populate_from_trial()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ---------------------------------------------------------
        # 1. Coordinate System & Marker Units
        # ---------------------------------------------------------
        coord_grp = QGroupBox("1. Coordinate System (Trial -> OpenSim) & Units")
        coord_grid = QGridLayout(coord_grp)
        coord_grid.setSpacing(8)

        coord_grid.addWidget(QLabel("<b>Preset Mapping:</b>"), 0, 0)
        self.combo_preset = QComboBox()
        for name in COORDINATE_PRESETS.keys():
            self.combo_preset.addItem(name)
        self.combo_preset.addItem("Custom")
        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        coord_grid.addWidget(self.combo_preset, 0, 1, 1, 5)

        coord_grid.addWidget(QLabel("<b>OpenSim +X (Forward) =</b>"), 1, 0)
        self.combo_ax_x = QComboBox()
        self.combo_ax_x.addItems(AXIS_OPTIONS)
        self.combo_ax_x.currentTextChanged.connect(self._on_axis_manual_changed)
        coord_grid.addWidget(self.combo_ax_x, 1, 1)

        coord_grid.addWidget(QLabel("<b>OpenSim +Y (Up) =</b>"), 1, 2)
        self.combo_ax_y = QComboBox()
        self.combo_ax_y.addItems(AXIS_OPTIONS)
        self.combo_ax_y.currentTextChanged.connect(self._on_axis_manual_changed)
        coord_grid.addWidget(self.combo_ax_y, 1, 3)

        coord_grid.addWidget(QLabel("<b>OpenSim +Z (Right) =</b>"), 1, 4)
        self.combo_ax_z = QComboBox()
        self.combo_ax_z.addItems(AXIS_OPTIONS)
        self.combo_ax_z.currentTextChanged.connect(self._on_axis_manual_changed)
        coord_grid.addWidget(self.combo_ax_z, 1, 5)

        coord_grid.addWidget(QLabel("<b>TRC Marker Units:</b>"), 2, 0)
        self.combo_trc_units = QComboBox()
        self.combo_trc_units.addItems(["mm", "m"])
        coord_grid.addWidget(self.combo_trc_units, 2, 1)

        lbl_mot_note = QLabel("GRF .mot outputs Forces (N), COP (m), and Free Moments (N·m) in OpenSim ground frame.")
        lbl_mot_note.setStyleSheet("color: #8C96AB; font-size: 11px;")
        coord_grid.addWidget(lbl_mot_note, 2, 2, 1, 4)

        root.addWidget(coord_grp)
        self._on_preset_changed(self.combo_preset.currentText())

        # ---------------------------------------------------------
        # 2. Ground Reaction Forces & ExternalLoads XML
        # ---------------------------------------------------------
        grf_grp = QGroupBox("2. Ground Reaction Forces (.mot) & ExternalLoads XML")
        grf_layout = QVBoxLayout(grf_grp)
        grf_layout.setSpacing(8)

        grf_top = QHBoxLayout()
        self.chk_export_grf = QCheckBox("Export Force Plate GRF (.mot) and ExternalLoads (.xml)")
        self.chk_export_grf.setChecked(True)
        self.chk_export_grf.toggled.connect(self._on_grf_toggled)
        grf_top.addWidget(self.chk_export_grf)
        grf_top.addStretch()

        self.btn_load_xml = QPushButton("Load Template XML...")
        self.btn_load_xml.clicked.connect(self._load_template_xml)
        grf_top.addWidget(self.btn_load_xml)

        self.btn_add_force = QPushButton("+ Add Force")
        self.btn_add_force.clicked.connect(self._add_external_force_row)
        grf_top.addWidget(self.btn_add_force)

        self.btn_remove_force = QPushButton("- Remove")
        self.btn_remove_force.clicked.connect(self._remove_external_force_row)
        grf_top.addWidget(self.btn_remove_force)

        grf_layout.addLayout(grf_top)

        self.table_forces = QTableWidget(0, 4)
        self.table_forces.setHorizontalHeaderLabels([
            "Plate #", "Name", "Applied To Body", "Disabled"
        ])
        self.table_forces.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_forces.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_forces.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_forces.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_forces.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_forces.verticalHeader().setDefaultSectionSize(32)
        self.table_forces.setMinimumHeight(115)
        self.table_forces.setMaximumHeight(160)
        grf_layout.addWidget(self.table_forces)

        root.addWidget(grf_grp)

        # ---------------------------------------------------------
        # 3. Export Mode Tabs: Current Trial vs Batch Processing
        # ---------------------------------------------------------
        self.tabs = QTabWidget()
        self.tab_single = QWidget()
        self.tab_batch = QWidget()
        self.tabs.addTab(self.tab_single, "Current Trial")
        self.tabs.addTab(self.tab_batch, "Batch Processing")
        self._setup_single_tab()
        self._setup_batch_tab()
        root.addWidget(self.tabs, stretch=1)

        # Bottom close bar
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _setup_single_tab(self):
        layout = QVBoxLayout(self.tab_single)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("<b>Base File Name:</b>"), 0, 0)
        self.txt_single_base = QLineEdit("trial")
        self.txt_single_base.textChanged.connect(self._update_single_preview)
        grid.addWidget(self.txt_single_base, 0, 1, 1, 2)

        grid.addWidget(QLabel("<b>Output Folder:</b>"), 1, 0)
        self.txt_single_dir = QLineEdit()
        grid.addWidget(self.txt_single_dir, 1, 1)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_single_dir)
        grid.addWidget(btn_browse, 1, 2)

        self.chk_use_roi = QCheckBox("Export only active Trim / ROI range")
        self.chk_use_roi.setChecked(False)
        grid.addWidget(self.chk_use_roi, 2, 0, 1, 3)

        layout.addLayout(grid)

        self.lbl_single_preview = QLabel()
        self.lbl_single_preview.setStyleSheet("color: #8C96AB; font-size: 11px;")
        self.lbl_single_preview.setWordWrap(True)
        layout.addWidget(self.lbl_single_preview)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_export_single = QPushButton("Export Current Trial")
        self.btn_export_single.setStyleSheet(
            "background-color: #00ADB5; color: #FFFFFF; font-weight: bold; padding: 8px 20px; border-radius: 4px;"
        )
        self.btn_export_single.clicked.connect(self._export_single_trial)
        btn_row.addWidget(self.btn_export_single)
        layout.addLayout(btn_row)
        layout.addStretch()

    def _setup_batch_tab(self):
        layout = QVBoxLayout(self.tab_batch)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # File Queue controls
        top_btns = QHBoxLayout()
        btn_add_files = QPushButton("+ Add C3D Files...")
        btn_add_files.clicked.connect(self._batch_add_files)
        top_btns.addWidget(btn_add_files)

        btn_add_folder = QPushButton("+ Add Folder...")
        btn_add_folder.clicked.connect(self._batch_add_folder)
        top_btns.addWidget(btn_add_folder)

        btn_rem = QPushButton("Remove Selected")
        btn_rem.clicked.connect(self._batch_remove_selected)
        top_btns.addWidget(btn_rem)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.list_batch_files.clear())
        top_btns.addWidget(btn_clear)
        top_btns.addStretch()
        layout.addLayout(top_btns)

        self.list_batch_files = QListWidget()
        self.list_batch_files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_batch_files.setMinimumHeight(75)
        self.list_batch_files.setMaximumHeight(110)
        layout.addWidget(self.list_batch_files)

        # Conditional Filename Rules
        rules_grp = QGroupBox("Conditional Rules (If filename contains text -> use custom GRF settings)")
        rules_layout = QVBoxLayout(rules_grp)
        rules_layout.setSpacing(6)

        rules_top = QHBoxLayout()
        lbl_hint = QLabel("Configure Section 2 above, then click '+ Add Rule' to capture those settings for matching filenames:")
        lbl_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        rules_top.addWidget(lbl_hint)
        rules_top.addStretch()

        self.btn_add_rule = QPushButton("+ Add Rule")
        self.btn_add_rule.clicked.connect(self._add_batch_rule)
        rules_top.addWidget(self.btn_add_rule)

        self.btn_remove_rule = QPushButton("- Remove Rule")
        self.btn_remove_rule.clicked.connect(self._remove_batch_rule)
        rules_top.addWidget(self.btn_remove_rule)
        rules_layout.addLayout(rules_top)

        self.table_rules = QTableWidget(0, 4)
        self.table_rules.setHorizontalHeaderLabels([
            "If Filename Contains", "Export GRF", "GRF Settings", "Actions"
        ])
        self.table_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table_rules.setColumnWidth(0, 150)
        self.table_rules.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_rules.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_rules.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_rules.setColumnWidth(3, 64)
        self.table_rules.verticalHeader().setDefaultSectionSize(36)
        self.table_rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_rules.setMinimumHeight(90)
        self.table_rules.setMaximumHeight(130)
        rules_layout.addWidget(self.table_rules)

        layout.addWidget(rules_grp)

        # Output folder row
        out_row = QHBoxLayout()
        self.chk_batch_same_dir = QCheckBox("Save next to each C3D file")
        self.chk_batch_same_dir.setChecked(True)
        self.chk_batch_same_dir.toggled.connect(self._on_batch_same_dir_toggled)
        out_row.addWidget(self.chk_batch_same_dir)

        self.txt_batch_dir = QLineEdit()
        self.txt_batch_dir.setEnabled(False)
        self.txt_batch_dir.setPlaceholderText("Select batch output folder...")
        out_row.addWidget(self.txt_batch_dir, stretch=1)

        self.btn_batch_browse = QPushButton("Browse...")
        self.btn_batch_browse.setEnabled(False)
        self.btn_batch_browse.clicked.connect(self._browse_batch_dir)
        out_row.addWidget(self.btn_batch_browse)
        layout.addLayout(out_row)

        self.progress_batch = QProgressBar()
        self.progress_batch.setValue(0)
        layout.addWidget(self.progress_batch)

        self.txt_batch_log = QTextEdit()
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setMaximumHeight(75)
        layout.addWidget(self.txt_batch_log)

        act_row = QHBoxLayout()
        self.btn_open_batch_dir = QPushButton("Open Output Folder")
        self.btn_open_batch_dir.clicked.connect(self._open_batch_output_folder)
        act_row.addWidget(self.btn_open_batch_dir)
        act_row.addStretch()

        self.btn_cancel_batch = QPushButton("Cancel")
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.clicked.connect(self._cancel_batch)
        act_row.addWidget(self.btn_cancel_batch)

        self.btn_start_batch = QPushButton("Start Batch Export")
        self.btn_start_batch.setStyleSheet(
            "background-color: #00ADB5; color: #FFFFFF; font-weight: bold; padding: 8px 20px; border-radius: 4px;"
        )
        self.btn_start_batch.clicked.connect(self._start_batch_export)
        act_row.addWidget(self.btn_start_batch)
        layout.addLayout(act_row)

    # ---------------------------------------------------------
    # Population & Helpers
    # ---------------------------------------------------------
    def _populate_from_trial(self):
        if not self.trial:
            self._set_external_forces(default_external_forces_for_count(2))
            self.btn_export_single.setEnabled(False)
            self.tabs.setCurrentIndex(1)
            return

        self.btn_export_single.setEnabled(True)
        if self.trial.file_path:
            base = os.path.splitext(os.path.basename(self.trial.file_path))[0]
            self.txt_single_base.setText(base)
            self.txt_single_dir.setText(os.path.dirname(os.path.abspath(self.trial.file_path)))
            self.txt_batch_dir.setText(os.path.dirname(os.path.abspath(self.trial.file_path)))
        else:
            self.txt_single_base.setText("trial")
            self.txt_single_dir.setText(os.getcwd())

        m_unit = str(getattr(self.trial, "marker_units", "mm")).strip().lower()
        self.combo_trc_units.setCurrentText("m" if m_unit in ("m", "meter", "meters") else "mm")

        n_frames = self.trial.point_frame_count
        if self.trim_range and (self.trim_range[0] > 0 or self.trim_range[1] < n_frames - 1):
            s_f, e_f = self.trim_range
            self.chk_use_roi.setText(f"Export only active Trim / ROI range (Frames {s_f + 1} – {e_f + 1})")
            self.chk_use_roi.setChecked(True)
            self.chk_use_roi.setEnabled(True)
        else:
            self.chk_use_roi.setText("Export only active Trim / ROI range (full trial currently active)")
            self.chk_use_roi.setChecked(False)
            self.chk_use_roi.setEnabled(False)

        n_plates = len(self.trial.force_platforms) if self.trial.force_platforms else 0
        has_forces = n_plates > 0 and any(fp.forces is not None for fp in self.trial.force_platforms)
        self.chk_export_grf.setChecked(has_forces)
        self._set_external_forces(default_external_forces_for_count(max(1, n_plates)))
        self._update_single_preview()

    def _on_preset_changed(self, preset_name: str):
        if preset_name not in COORDINATE_PRESETS:
            return
        self._syncing_preset = True
        try:
            ax, ay, az = COORDINATE_PRESETS[preset_name]
            self.combo_ax_x.setCurrentText(ax)
            self.combo_ax_y.setCurrentText(ay)
            self.combo_ax_z.setCurrentText(az)
        finally:
            self._syncing_preset = False

    def _on_axis_manual_changed(self):
        if self._syncing_preset:
            return
        cur = (self.combo_ax_x.currentText(), self.combo_ax_y.currentText(), self.combo_ax_z.currentText())
        for name, vals in COORDINATE_PRESETS.items():
            if vals == cur:
                self.combo_preset.blockSignals(True)
                self.combo_preset.setCurrentText(name)
                self.combo_preset.blockSignals(False)
                return
        self.combo_preset.blockSignals(True)
        self.combo_preset.setCurrentText("Custom")
        self.combo_preset.blockSignals(False)

    def get_transform_matrix(self):
        return build_axis_transform_matrix(
            self.combo_ax_x.currentText(),
            self.combo_ax_y.currentText(),
            self.combo_ax_z.currentText(),
        )

    def _on_grf_toggled(self, checked: bool):
        self.table_forces.setEnabled(checked)
        self.btn_load_xml.setEnabled(checked)
        self.btn_add_force.setEnabled(checked)
        self.btn_remove_force.setEnabled(checked)
        self._update_single_preview()

    def _set_external_forces(self, configs: List[ExternalForceConfig]):
        self.table_forces.setRowCount(0)
        for cfg in configs:
            self._append_force_row(cfg)

    def _append_force_row(self, cfg: ExternalForceConfig):
        r = self.table_forces.rowCount()
        self.table_forces.insertRow(r)

        item_plate = QTableWidgetItem(str(cfg.plate_index + 1))
        item_plate.setTextAlignment(Qt.AlignCenter)
        # Preserve optional custom identifiers (e.g. from XML template) in UserRole
        item_plate.setData(Qt.UserRole, (
            cfg.force_expressed_in_body,
            cfg.point_expressed_in_body,
            cfg.force_identifier,
            cfg.point_identifier,
            cfg.torque_identifier,
        ))
        self.table_forces.setItem(r, 0, item_plate)
        self.table_forces.setItem(r, 1, QTableWidgetItem(cfg.name))

        body_combo = QComboBox()
        body_combo.setEditable(True)
        body_combo.addItems(COMMON_OPENSIM_BODIES)
        body_combo.setCurrentText(cfg.applied_to_body)
        self.table_forces.setCellWidget(r, 2, body_combo)

        container, _toggle = _centered_toggle(cfg.is_disabled)
        self.table_forces.setCellWidget(r, 3, container)

    def _add_external_force_row(self):
        idx = self.table_forces.rowCount()
        cfg = default_external_forces_for_count(idx + 1)[-1]
        self._append_force_row(cfg)

    def _remove_external_force_row(self):
        rows = sorted({idx.row() for idx in self.table_forces.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table_forces.removeRow(r)

    def get_external_forces(self) -> List[ExternalForceConfig]:
        configs: List[ExternalForceConfig] = []
        for r in range(self.table_forces.rowCount()):
            plate_item = self.table_forces.item(r, 0)
            try:
                plate_num = int(plate_item.text().strip())
            except Exception:
                plate_num = r + 1

            meta = plate_item.data(Qt.UserRole) if plate_item else None
            if isinstance(meta, tuple) and len(meta) == 5:
                f_body, p_body, f_id, p_id, t_id = meta
            else:
                f_body, p_body = "ground", "ground"
                f_id = f"ground_force_{plate_num}_v"
                p_id = f"ground_force_{plate_num}_p"
                t_id = f"ground_torque_{plate_num}_"

            body_widget = self.table_forces.cellWidget(r, 2)
            body_txt = body_widget.currentText().strip() if isinstance(body_widget, QComboBox) else "calcn_r"

            dis_container = self.table_forces.cellWidget(r, 3)
            toggle = dis_container.findChild(ToggleSwitch) if dis_container else None
            is_dis = toggle.isChecked() if toggle else False

            configs.append(
                ExternalForceConfig(
                    name=self.table_forces.item(r, 1).text().strip() or f"ExternalForce_{r + 1}",
                    is_disabled=is_dis,
                    applied_to_body=body_txt or "calcn_r",
                    force_expressed_in_body=f_body,
                    point_expressed_in_body=p_body,
                    force_identifier=f_id,
                    point_identifier=p_id,
                    torque_identifier=t_id,
                    plate_index=max(0, plate_num - 1),
                )
            )
        return configs

    def _load_template_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load OpenSim ExternalLoads XML", "", "XML Files (*.xml);;All Files (*)"
        )
        if not path:
            return
        try:
            configs = parse_external_loads_xml(path)
            if not configs:
                QMessageBox.warning(self, "No ExternalForce Entries", "No <ExternalForce> entries were found in the XML file.")
                return
            self._set_external_forces(configs)
        except Exception as e:
            QMessageBox.critical(self, "XML Parse Error", f"Failed to parse XML template:\n{e}")

    def _update_single_preview(self):
        base = self.txt_single_base.text().strip() or "trial"
        files = [f"{base}.trc"]
        if self.chk_export_grf.isChecked():
            files.extend([f"{base}_grf.mot", f"{base}_grf.xml"])
        self.lbl_single_preview.setText("Files to create: " + ",  ".join(files))

    def _browse_single_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.txt_single_dir.text())
        if d:
            self.txt_single_dir.setText(d)

    def _export_single_trial(self):
        if not self.trial:
            return
        out_dir = self.txt_single_dir.text().strip()
        base = self.txt_single_base.text().strip()
        if not out_dir or not base:
            QMessageBox.warning(self, "Missing Path", "Please specify both an output folder and a base file name.")
            return

        s_f, e_f = (None, None)
        if self.chk_use_roi.isChecked() and self.trim_range:
            s_f, e_f = self.trim_range

        try:
            out = export_trial_to_opensim(
                trial=self.trial,
                output_dir=out_dir,
                base_name=base,
                transform_matrix=self.get_transform_matrix(),
                trc_units=self.combo_trc_units.currentText(),
                export_grf=self.chk_export_grf.isChecked(),
                external_forces=self.get_external_forces(),
                start_frame=s_f,
                end_frame=e_f,
            )
            created_list = "\n".join(f"• {os.path.basename(p)}" for p in out.values())
            QMessageBox.information(
                self,
                "OpenSim Export Complete",
                f"Exported to:\n{out_dir}\n\n{created_list}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export OpenSim files:\n{e}")

    # ---------------------------------------------------------
    # Batch Conditional Rules Helpers
    # ---------------------------------------------------------
    def _add_batch_rule(self, pattern: str = "", export_grf: Optional[bool] = None, forces: Optional[List[ExternalForceConfig]] = None):
        r = self.table_rules.rowCount()
        self.table_rules.insertRow(r)

        use_grf = self.chk_export_grf.isChecked() if export_grf is None else bool(export_grf)
        captured_forces = copy.deepcopy(forces) if forces is not None else self.get_external_forces()

        txt_pat = QLineEdit(pattern if isinstance(pattern, str) else "")
        txt_pat.setPlaceholderText("e.g. _L_ or _R_ or static")
        self.table_rules.setCellWidget(r, 0, txt_pat)

        container, _toggle = _centered_toggle(use_grf)
        self.table_rules.setCellWidget(r, 1, container)

        summary_item = QTableWidgetItem(_summarize_forces(captured_forces))
        summary_item.setFlags(summary_item.flags() & ~Qt.ItemIsEditable)
        summary_item.setData(Qt.UserRole, captured_forces)
        self.table_rules.setItem(r, 2, summary_item)

        act_widget = QWidget()
        act_layout = QHBoxLayout(act_widget)
        act_layout.setContentsMargins(2, 2, 2, 2)
        act_layout.setAlignment(Qt.AlignCenter)

        btn_set = QPushButton("Set")
        btn_set.setFixedSize(48, 22)
        btn_set.setStyleSheet("padding: 1px 6px; font-size: 11px;")
        btn_set.setToolTip("Save current Section 2 GRF table into this rule")
        btn_set.clicked.connect(lambda _chk=False, item=summary_item: self._capture_above_into_rule(item))

        act_layout.addWidget(btn_set)
        self.table_rules.setRowHeight(r, 36)
        self.table_rules.setCellWidget(r, 3, act_widget)

    def _capture_above_into_rule(self, summary_item: QTableWidgetItem):
        forces = self.get_external_forces()
        summary_item.setData(Qt.UserRole, forces)
        summary_item.setText(_summarize_forces(forces))

    def _load_rule_into_above(self, summary_item: QTableWidgetItem):
        forces = summary_item.data(Qt.UserRole)
        if forces:
            self._set_external_forces(copy.deepcopy(forces))

    def _remove_batch_rule(self):
        rows = sorted({idx.row() for idx in self.table_rules.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table_rules.removeRow(r)

    def get_batch_rules(self) -> List[BatchRule]:
        rules: List[BatchRule] = []
        for r in range(self.table_rules.rowCount()):
            pat_widget = self.table_rules.cellWidget(r, 0)
            pat = pat_widget.text().strip() if isinstance(pat_widget, QLineEdit) else ""

            grf_container = self.table_rules.cellWidget(r, 1)
            toggle = grf_container.findChild(ToggleSwitch) if grf_container else None
            use_grf = toggle.isChecked() if toggle else True

            summary_item = self.table_rules.item(r, 2)
            forces = summary_item.data(Qt.UserRole) if summary_item else []
            if pat:
                rules.append(BatchRule(pattern=pat, export_grf=use_grf, external_forces=copy.deepcopy(forces)))
        return rules

    # ---------------------------------------------------------
    # Batch Processing Actions
    # ---------------------------------------------------------
    def _batch_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select C3D Files for OpenSim Export", "", "C3D Files (*.c3d);;All Files (*)"
        )
        existing = {self.list_batch_files.item(i).text() for i in range(self.list_batch_files.count())}
        for f in files:
            if f not in existing:
                self.list_batch_files.addItem(f)

    def _batch_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing C3D Files")
        if not folder:
            return
        existing = {self.list_batch_files.item(i).text() for i in range(self.list_batch_files.count())}
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".c3d"):
                full = os.path.join(folder, fname)
                if full not in existing:
                    self.list_batch_files.addItem(full)

    def _batch_remove_selected(self):
        for item in self.list_batch_files.selectedItems():
            self.list_batch_files.takeItem(self.list_batch_files.row(item))

    def _on_batch_same_dir_toggled(self, checked: bool):
        self.txt_batch_dir.setEnabled(not checked)
        self.btn_batch_browse.setEnabled(not checked)

    def _browse_batch_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Batch Output Folder", self.txt_batch_dir.text())
        if d:
            self.txt_batch_dir.setText(d)

    def _open_batch_output_folder(self):
        target = self.txt_batch_dir.text().strip()
        if self.chk_batch_same_dir.isChecked() and self.list_batch_files.count() > 0:
            target = os.path.dirname(self.list_batch_files.item(0).text())
        if target and os.path.isdir(target):
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _start_batch_export(self):
        files = [self.list_batch_files.item(i).text() for i in range(self.list_batch_files.count())]
        if not files:
            QMessageBox.warning(self, "Empty Queue", "Please add at least one C3D file to the batch queue.")
            return
        same_dir = self.chk_batch_same_dir.isChecked()
        out_dir = self.txt_batch_dir.text().strip()
        if not same_dir and not out_dir:
            QMessageBox.warning(self, "Missing Output Folder", "Please select a batch output folder or enable 'Save next to each C3D file'.")
            return

        self.txt_batch_log.clear()
        self.progress_batch.setRange(0, len(files))
        self.progress_batch.setValue(0)
        self.btn_start_batch.setEnabled(False)
        self.btn_cancel_batch.setEnabled(True)

        self._worker = OpenSimBatchWorker(
            files=files,
            output_dir=out_dir,
            same_as_input=same_dir,
            transform_matrix=self.get_transform_matrix(),
            trc_units=self.combo_trc_units.currentText(),
            export_grf=self.chk_export_grf.isChecked(),
            external_forces=self.get_external_forces(),
            rules=self.get_batch_rules(),
            parent=self,
        )
        self._worker.progressChanged.connect(self._on_batch_progress)
        self._worker.fileFinished.connect(self._on_batch_file_finished)
        self._worker.batchCompleted.connect(self._on_batch_completed)
        self._worker.start()

    def _cancel_batch(self):
        if self._worker:
            self._worker.cancel()

    def _on_batch_progress(self, current: int, total: int, fname: str):
        self.progress_batch.setMaximum(max(1, total))
        self.progress_batch.setValue(current)

    def _on_batch_file_finished(self, fname: str, success: bool, msg: str):
        badge = "✓" if success else "✕"
        self.txt_batch_log.append(f"{badge} {fname}: {msg}")

    def _on_batch_completed(self, succeeded: int, failed: int):
        self.btn_start_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        self.txt_batch_log.append(f"\nBatch finished: {succeeded} succeeded, {failed} failed.")

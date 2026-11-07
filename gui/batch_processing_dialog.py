"""Batch Processing & Pipeline Automation Dialog for C3D Explorer.

Allows users to load an XML pipeline recipe (or use active trial modifications)
and execute the entire sequence across batches of 50, 100, or more C3D files,
with support for intrinsic operations and intelligent per-trial external file matching.
"""

import os
import sys
import time
import subprocess
import unicodedata
from typing import List, Dict, Any, Optional, Set

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QDesktopServices, QCursor
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QRadioButton, QCheckBox, QTextEdit, QFrame,
    QAbstractItemView, QMenu, QToolButton
)

from core.data_models import C3DTrial
from core.pipeline_executor import (
    PipelineExecutor, ExecutableOperation, TrialExecutionResult
)
from gui.toggle_switch import ToggleSwitch


def _canonical_path(path: str) -> str:
    """Normalize Unicode (NFC), resolve symlinks, case, and absolute path for cross-platform uniqueness."""
    if not path:
        return ""
    nfc = unicodedata.normalize("NFC", str(path))
    real = os.path.realpath(os.path.abspath(nfc))
    return unicodedata.normalize("NFC", real)


# ------------------------------------------------------------------------------
# Background Processing Worker
# ------------------------------------------------------------------------------

class BatchWorker(QThread):
    """Worker thread to execute pipeline on multiple C3D files asynchronously."""
    progressUpdated = Signal(int, int, str)  # (current_index, total, current_filename)
    fileCompleted = Signal(int, str, bool, list, list, float)  # (index, filename, success, warnings, errors, elapsed)
    logMessage = Signal(str, str)  # (message, level: 'info'|'warning'|'error'|'success')
    batchFinished = Signal(int, int, int, float)  # (succeeded, failed, warnings, total_seconds)

    def __init__(
        self,
        executor: PipelineExecutor,
        file_queue: List[str],
        output_dir: str,
        suffix: str = "",
        external_search_dirs: Optional[List[str]] = None,
        custom_file_maps: Optional[Dict[str, Dict[str, str]]] = None,
        apply_trim_roi: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.executor = executor
        self.file_queue = list(file_queue)
        self.output_dir = output_dir
        self.suffix = suffix
        self.external_search_dirs = external_search_dirs or []
        self.custom_file_maps = custom_file_maps or {}  # c3d_path -> {entity_name: ext_file_path}
        self.apply_trim_roi = apply_trim_roi
        self._is_cancelled = False

    def cancel(self):
        """Request cooperative cancellation."""
        self._is_cancelled = True

    def run(self):
        t_start = time.time()
        total_files = len(self.file_queue)
        succeeded = 0
        failed = 0
        total_warnings = 0

        self.logMessage.emit(f"Starting batch execution of {total_files} trial(s)...", "info")

        for idx, c3d_path in enumerate(self.file_queue):
            if self._is_cancelled:
                self.logMessage.emit("Batch processing cancelled by user.", "warning")
                break

            fname = os.path.basename(c3d_path)
            self.progressUpdated.emit(idx + 1, total_files, fname)
            self.logMessage.emit(f"[{idx + 1}/{total_files}] Processing: {fname}", "info")

            # Determine output file path
            base_no_ext, ext = os.path.splitext(fname)
            out_name = f"{base_no_ext}{self.suffix}{ext}" if self.suffix else fname
            out_path = os.path.join(self.output_dir, out_name)

            custom_map = self.custom_file_maps.get(c3d_path, None)

            # Execute pipeline on single file
            res: TrialExecutionResult = self.executor.execute_file(
                input_c3d_path=c3d_path,
                output_c3d_path=out_path,
                search_dirs=self.external_search_dirs,
                custom_file_map=custom_map,
                apply_trim_roi=self.apply_trim_roi
            )

            if res.success:
                succeeded += 1
                if res.warnings:
                    total_warnings += len(res.warnings)
                    for w in res.warnings:
                        self.logMessage.emit(f"  [WARN] {w}", "warning")
                    self.logMessage.emit(f"  Completed with {len(res.warnings)} warning(s) in {res.elapsed_seconds:.2f}s", "warning")
                else:
                    self.logMessage.emit(f"  Successfully processed in {res.elapsed_seconds:.2f}s", "success")
            else:
                failed += 1
                for err in res.errors:
                    self.logMessage.emit(f"  [ERROR] {err}", "error")

            self.fileCompleted.emit(
                idx, fname, res.success, res.warnings, res.errors, res.elapsed_seconds
            )

        total_elapsed = round(time.time() - t_start, 2)
        self.batchFinished.emit(succeeded, failed, total_warnings, total_elapsed)


# ------------------------------------------------------------------------------
# Batch Processing Dialog UI
# ------------------------------------------------------------------------------

class BatchProcessingDialog(QDialog):
    """
    Main Batch Processing & Pipeline Automation Dialog.
    Allows loading/configuring a pipeline recipe and running it over 50–100+ C3D trials.
    """

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent or main_window)
        self.mw = main_window
        self.setWindowTitle("Batch Processing")
        self.resize(1020, 740)
        self.setMinimumSize(860, 580)

        self.executor = PipelineExecutor()
        self.file_queue: List[str] = []
        self._canonical_file_set: Set[str] = set()
        self.external_dir: str = ""
        self.worker: Optional[BatchWorker] = None
        self.last_output_dir: str = ""

        self._setup_ui()
        self._init_defaults()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Splitter: Left (Settings & Queue) | Right (Operations & Console Log)
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(8)

        # --- LEFT PANEL: Pipeline Source, External Matching, Target Files ---
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(10)

        # 1. Pipeline Source Box
        grp_pipeline = QGroupBox("1. Pipeline Recipe Source", left_widget)
        grp_pipe_layout = QVBoxLayout(grp_pipeline)
        grp_pipe_layout.setSpacing(8)

        self.rb_pipe_xml = QRadioButton("Load from Pipeline XML file:", grp_pipeline)
        self.rb_pipe_xml.setChecked(True)
        self.rb_pipe_xml.toggled.connect(self._on_source_toggled)

        xml_box = QHBoxLayout()
        self.txt_xml_path = QLineEdit(grp_pipeline)
        self.txt_xml_path.setReadOnly(True)
        self.txt_xml_path.setPlaceholderText("Select exported pipeline XML file...")
        btn_browse_xml = QPushButton("Browse...", grp_pipeline)
        btn_browse_xml.clicked.connect(self._browse_pipeline_xml)
        xml_box.addWidget(self.txt_xml_path)
        xml_box.addWidget(btn_browse_xml)

        self.rb_pipe_active = QRadioButton("Use active open trial's recorded pipeline", grp_pipeline)
        self.rb_pipe_active.toggled.connect(self._on_source_toggled)

        grp_pipe_layout.addWidget(self.rb_pipe_xml)
        grp_pipe_layout.addLayout(xml_box)
        grp_pipe_layout.addWidget(self.rb_pipe_active)
        left_layout.addWidget(grp_pipeline)

        # 2. External Data Box
        self.grp_external = QGroupBox("2. Per-Trial External Data (CSV / Excel / TXT)", left_widget)
        grp_ext_layout = QVBoxLayout(self.grp_external)
        grp_ext_layout.setSpacing(8)

        self.lbl_ext_info = QLabel("No external file operations in current pipeline.", self.grp_external)
        self.lbl_ext_info.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grp_ext_layout.addWidget(self.lbl_ext_info)

        ext_box = QHBoxLayout()
        self.txt_ext_dir = QLineEdit(self.grp_external)
        self.txt_ext_dir.setPlaceholderText("Trial name_Marker name.xlsx/txt or csv")
        self.txt_ext_dir.textChanged.connect(self._rematch_external_files)
        btn_browse_ext = QPushButton("Browse Folder...", self.grp_external)
        btn_browse_ext.clicked.connect(self._browse_external_dir)
        ext_box.addWidget(self.txt_ext_dir)
        ext_box.addWidget(btn_browse_ext)
        grp_ext_layout.addLayout(ext_box)

        left_layout.addWidget(self.grp_external)

        # 3. Target C3D Files Queue
        grp_queue = QGroupBox("3. Target C3D Files to Process", left_widget)
        grp_queue_layout = QVBoxLayout(grp_queue)
        grp_queue_layout.setSpacing(8)

        # Queue Toolbar Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)
        btn_add_files = QPushButton("+ Add C3D Files...", grp_queue)
        btn_add_files.clicked.connect(self._add_files_dialog)
        btn_add_folder = QPushButton("+ Add Folder...", grp_queue)
        btn_add_folder.clicked.connect(self._add_folder_dialog)
        btn_remove = QPushButton("- Remove", grp_queue)
        btn_remove.clicked.connect(self._remove_selected_files)
        btn_clear = QPushButton("Clear All", grp_queue)
        btn_clear.clicked.connect(self._clear_queue)

        btn_bar.addWidget(btn_add_files)
        btn_bar.addWidget(btn_add_folder)
        btn_bar.addWidget(btn_remove)
        btn_bar.addWidget(btn_clear)
        btn_bar.addStretch()
        grp_queue_layout.addLayout(btn_bar)

        # Files Queue Table
        self.table_queue = QTableWidget(0, 4, grp_queue)
        self.table_queue.setHorizontalHeaderLabels(["C3D File", "Directory", "Matched External File", "Status"])
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_queue.setColumnWidth(0, 180)
        self.table_queue.setColumnWidth(2, 220)
        self.table_queue.setColumnWidth(3, 110)
        self.table_queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_queue.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_queue.setAlternatingRowColors(True)
        self.table_queue.setAcceptDrops(True)
        self.table_queue.dragEnterEvent = self._table_drag_enter
        self.table_queue.dragMoveEvent = self._table_drag_move
        self.table_queue.dropEvent = self._table_drop
        grp_queue_layout.addWidget(self.table_queue)

        # Queue Status Footer
        self.lbl_queue_stats = QLabel("Queued: 0 files", grp_queue)
        self.lbl_queue_stats.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grp_queue_layout.addWidget(self.lbl_queue_stats)

        left_layout.addWidget(grp_queue)
        splitter.addWidget(left_widget)

        # --- RIGHT PANEL: Operations Preview, Output Settings, Execution Log ---
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(10)

        # 4. Pipeline Recipe Operations Preview
        grp_ops = QGroupBox("Pipeline Recipe Operations", right_widget)
        grp_ops_layout = QVBoxLayout(grp_ops)
        grp_ops_layout.setSpacing(6)

        self.lbl_ops_badge = QLabel("No pipeline loaded", grp_ops)
        self.lbl_ops_badge.setStyleSheet("font-weight: bold; color: #8C96AB;")
        grp_ops_layout.addWidget(self.lbl_ops_badge)

        # Operations Action Toolbar
        ops_btn_box = QHBoxLayout()
        ops_btn_box.setSpacing(6)
        btn_add_op = QPushButton("+ Add Operation...", grp_ops)
        btn_add_op.setToolTip("Add an operation directly to the batch pipeline recipe (Filter Markers, EMG Custom Filter, etc.)")
        btn_add_op.clicked.connect(self._show_add_operation_menu)
        btn_remove_op = QPushButton("- Remove", grp_ops)
        btn_remove_op.setToolTip("Remove selected operation from pipeline recipe")
        btn_remove_op.clicked.connect(self._remove_selected_operation)
        btn_clear_ops = QPushButton("Clear All", grp_ops)
        btn_clear_ops.clicked.connect(self._clear_operations_preview)

        ops_btn_box.addWidget(btn_add_op)
        ops_btn_box.addWidget(btn_remove_op)
        ops_btn_box.addWidget(btn_clear_ops)
        ops_btn_box.addStretch()
        grp_ops_layout.addLayout(ops_btn_box)

        self.table_ops = QTableWidget(0, 3, grp_ops)
        self.table_ops.setHorizontalHeaderLabels(["#", "Action", "Details"])
        self.table_ops.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table_ops.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_ops.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_ops.setColumnWidth(0, 35)
        self.table_ops.setColumnWidth(1, 140)
        self.table_ops.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_ops.setAlternatingRowColors(True)
        self.table_ops.setMaximumHeight(180)
        grp_ops_layout.addWidget(self.table_ops)
        right_layout.addWidget(grp_ops)

        # 5. Output Destination Settings
        grp_output = QGroupBox("Output Destination & Options", right_widget)
        grp_out_layout = QVBoxLayout(grp_output)
        grp_out_layout.setSpacing(8)

        self.rb_out_folder = QRadioButton("Save to specific output folder:", grp_output)
        self.rb_out_folder.setChecked(True)
        out_box = QHBoxLayout()
        self.txt_out_dir = QLineEdit(grp_output)
        self.txt_out_dir.setPlaceholderText("Select output folder for processed C3D files...")
        btn_browse_out = QPushButton("Browse...", grp_output)
        btn_browse_out.clicked.connect(self._browse_output_dir)
        out_box.addWidget(self.txt_out_dir)
        out_box.addWidget(btn_browse_out)

        self.rb_out_alongside = QRadioButton("Save alongside original files with suffix:", grp_output)
        self.txt_suffix = QLineEdit("_processed", grp_output)
        self.txt_suffix.setMaximumWidth(120)
        along_box = QHBoxLayout()
        along_box.addWidget(self.rb_out_alongside)
        along_box.addWidget(self.txt_suffix)
        along_box.addStretch()

        self.chk_trim_roi = ToggleSwitch("Apply ROI", grp_output)
        self.chk_trim_roi.setChecked(True)

        grp_out_layout.addWidget(self.rb_out_folder)
        grp_out_layout.addLayout(out_box)
        grp_out_layout.addLayout(along_box)
        grp_out_layout.addWidget(self.chk_trim_roi)
        right_layout.addWidget(grp_output)

        # 6. Real-time Console Log
        grp_log = QGroupBox("Batch Execution Log", right_widget)
        grp_log_layout = QVBoxLayout(grp_log)
        grp_log_layout.setSpacing(6)

        self.txt_log = QTextEdit(grp_log)
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("font-family: Menlo, Monaco, Consolas, monospace; font-size: 11px;")
        grp_log_layout.addWidget(self.txt_log)
        right_layout.addWidget(grp_log)

        splitter.addWidget(right_widget)
        splitter.setSizes([540, 480])
        main_layout.addWidget(splitter, stretch=1)

        # Bottom Progress Bar & Action Controls
        bottom_frame = QFrame(self)
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        prog_layout = QHBoxLayout()
        self.progress_bar = QProgressBar(bottom_frame)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)
        prog_layout.addWidget(self.progress_bar)

        self.lbl_progress_status = QLabel("Ready.", bottom_frame)
        self.lbl_progress_status.setStyleSheet("color: #8C96AB; font-size: 12px; min-width: 220px;")
        prog_layout.addWidget(self.lbl_progress_status)
        bottom_layout.addLayout(prog_layout)

        btn_ctrl_layout = QHBoxLayout()
        btn_ctrl_layout.setSpacing(10)

        self.btn_open_out = QPushButton("Open Output Folder", bottom_frame)
        self.btn_open_out.setEnabled(False)
        self.btn_open_out.clicked.connect(self._open_output_folder)
        btn_ctrl_layout.addWidget(self.btn_open_out)

        self.btn_export_log = QPushButton("Export Log...", bottom_frame)
        self.btn_export_log.clicked.connect(self._export_log_file)
        btn_ctrl_layout.addWidget(self.btn_export_log)

        btn_ctrl_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", bottom_frame)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_batch)
        btn_ctrl_layout.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("Start Batch Processing", bottom_frame)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #00ADB5;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #00C4CC;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        self.btn_start.clicked.connect(self._start_batch)
        btn_ctrl_layout.addWidget(self.btn_start)

        self.btn_close = QPushButton("Close", bottom_frame)
        self.btn_close.clicked.connect(self.close)
        btn_ctrl_layout.addWidget(self.btn_close)

        bottom_layout.addLayout(btn_ctrl_layout)
        main_layout.addWidget(bottom_frame)

    def _init_defaults(self):
        """Populate dialog state from active main window if available."""
        if self.mw and hasattr(self.mw, 'trial') and self.mw.trial:
            c3d_file = getattr(self.mw, 'current_file_path', '')
            if c3d_file and os.path.isfile(c3d_file):
                default_out = os.path.join(os.path.dirname(c3d_file), "batch_processed")
                self.txt_out_dir.setText(default_out)

            # Check if active trial has recorded operations
            pm = getattr(self.mw, 'pipeline_manager', None)
            if pm:
                if hasattr(self.mw, 'undo_stack') and self.mw.undo_stack:
                    pm.sync_with_undo_stack(self.mw.undo_stack)
                if pm.operations:
                    self.rb_pipe_active.setText(f"Use active open trial's recorded pipeline ({len(pm.operations)} operations)")
                    self.rb_pipe_active.setEnabled(True)
                    self.rb_pipe_active.setChecked(True)
                    self._load_from_active_pipeline()
                else:
                    self.rb_pipe_active.setText("Use active open trial's recorded pipeline (0 operations)")
                    self.rb_pipe_active.setEnabled(False)
                    self.rb_pipe_xml.setChecked(True)
            else:
                self.rb_pipe_active.setEnabled(False)
                self.rb_pipe_xml.setChecked(True)
        else:
            self.rb_pipe_active.setEnabled(False)
            self.rb_pipe_xml.setChecked(True)

    def _show_add_operation_menu(self):
        menu = QMenu(self)
        act_filt_markers = menu.addAction("Filter Markers (Butterworth Low-pass)...")
        act_emg_custom = menu.addAction("EMG Custom Filter (Band-pass 20-400Hz + Rectification + LP 20Hz)...")
        act_filt_analog = menu.addAction("Filter Analog Channel(s)...")
        chosen = menu.exec(QCursor.pos())
        if chosen == act_filt_markers:
            self._prompt_add_filter_markers()
        elif chosen == act_emg_custom:
            self._prompt_add_emg_custom()
        elif chosen == act_filt_analog:
            self._prompt_add_filter_analog()

    def _prompt_add_filter_markers(self):
        from PySide6.QtWidgets import QInputDialog
        cutoff, ok = QInputDialog.getDouble(self, "Filter Markers", "Butterworth Cutoff Frequency (Hz):", 6.0, 0.1, 500.0, 1)
        if not ok:
            return
        order, ok = QInputDialog.getInt(self, "Filter Markers", "Butterworth Order:", 4, 1, 10, 1)
        if not ok:
            return

        next_id = len(self.executor.operations) + 1
        op = ExecutableOperation(
            id=next_id,
            action="FilterMarkers",
            description=f"Filtered marker trajectories (Butterworth Order {order}, Cutoff {cutoff:.1f} Hz)",
            parameters={
                "FilterType": "Butterworth Low-pass",
                "Order": order,
                "CutoffFrequency_Hz": cutoff,
                "ZeroPhase": True,
                "Target": "All"
            }
        )
        self.executor.operations.append(op)
        self._update_operations_ui()
        self._log(f"Added operation #{next_id}: FilterMarkers (Order {order}, {cutoff:.1f} Hz)", "info")

    def _prompt_add_emg_custom(self):
        next_id = len(self.executor.operations) + 1
        op = ExecutableOperation(
            id=next_id,
            action="EMGCustomFilter",
            description="EMG Custom: Band-pass (20-400 Hz) + Full-Wave Rectification & Low-pass (20 Hz)",
            parameters={
                "Action": "EMGCustomFilter",
                "BandpassLow_Hz": 20.0,
                "BandpassHigh_Hz": 400.0,
                "LowpassCutoff_Hz": 20.0,
                "Order": 4,
                "Overwrite": True,
                "Channels": "All"
            }
        )
        self.executor.operations.append(op)
        self._update_operations_ui()
        self._log(f"Added operation #{next_id}: EMG Custom Filter", "info")

    def _prompt_add_filter_analog(self):
        from PySide6.QtWidgets import QInputDialog
        ch_name, ok = QInputDialog.getText(self, "Filter Analog Channel", "Channel Name (or 'All' for all channels):", text="All")
        if not ok or not ch_name.strip():
            return
        cutoff, ok = QInputDialog.getDouble(self, "Filter Analog Channel", "Cutoff Frequency (Hz):", 20.0, 0.1, 5000.0, 1)
        if not ok:
            return

        next_id = len(self.executor.operations) + 1
        op = ExecutableOperation(
            id=next_id,
            action="FilterAnalogChannel",
            description=f"Filtered analog channel '{ch_name.strip()}' (Butterworth Low-pass {cutoff:.1f} Hz)",
            parameters={
                "ChannelName": ch_name.strip(),
                "Method": "Butterworth Low-pass",
                "Order": 4,
                "Cutoff": cutoff
            }
        )
        self.executor.operations.append(op)
        self._update_operations_ui()
        self._log(f"Added operation #{next_id}: FilterAnalogChannel '{ch_name.strip()}'", "info")

    def _remove_selected_operation(self):
        sel_rows = sorted(set(idx.row() for idx in self.table_ops.selectedIndexes()), reverse=True)
        if not sel_rows:
            return
        for r in sel_rows:
            if r < len(self.executor.operations):
                removed = self.executor.operations.pop(r)
                self._log(f"Removed operation #{removed.id}: {removed.action}", "info")
        for i, op in enumerate(self.executor.operations):
            op.id = i + 1
        self._update_operations_ui()

    # --------------------------------------------------------------------------
    # Pipeline Recipe Loading
    # --------------------------------------------------------------------------

    def _on_source_toggled(self):
        if self.rb_pipe_xml.isChecked():
            path = self.txt_xml_path.text().strip()
            if path and os.path.isfile(path):
                self._load_xml_file(path)
            else:
                self._clear_operations_preview()
        else:
            self._load_from_active_pipeline()

    def _browse_pipeline_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Pipeline XML Recipe", "", "XML Files (*.xml);;All Files (*)"
        )
        if path:
            self.txt_xml_path.setText(path)
            self.rb_pipe_xml.setChecked(True)
            self._load_xml_file(path)

    def _load_xml_file(self, path: str):
        try:
            self.executor.load_xml(path)
            self._update_operations_ui()
            self._log(f"Loaded Pipeline XML recipe: {os.path.basename(path)} ({len(self.executor.operations)} operations)", "info")
        except Exception as e:
            QMessageBox.critical(self, "Invalid Pipeline XML", f"Could not load XML file:\n{e}")
            self._clear_operations_preview()

    def _load_from_active_pipeline(self):
        if not self.mw or not hasattr(self.mw, 'pipeline_manager'):
            return
        pm = self.mw.pipeline_manager
        pm.sync_with_undo_stack(self.mw.undo_stack)
        try:
            xml_str = pm.to_xml_string(trial=self.mw.trial, settings=self.mw._collect_current_app_settings())
            self.executor.load_xml(xml_str)
            self._update_operations_ui()
            self._log(f"Loaded active trial pipeline ({len(self.executor.operations)} operations)", "info")
        except Exception as e:
            self._log(f"Error loading active pipeline: {e}", "error")

    def _clear_operations_preview(self):
        self.executor.operations.clear()
        self.table_ops.setRowCount(0)
        self.lbl_ops_badge.setText("No pipeline loaded")
        self.lbl_ops_badge.setStyleSheet("color: #8C96AB; font-weight: bold;")
        self.grp_external.setEnabled(False)
        self.lbl_ext_info.setText("No external file operations in current pipeline.")

    def _update_operations_ui(self):
        ops = self.executor.operations
        self.table_ops.setRowCount(len(ops))

        for row, op in enumerate(ops):
            item_id = QTableWidgetItem(str(op.id))
            item_id.setTextAlignment(Qt.AlignCenter)
            item_action = QTableWidgetItem(op.action)
            item_action.setFont(QFont("SF Pro Text", 12, QFont.Bold))
            item_desc = QTableWidgetItem(op.description)
            item_desc.setToolTip(str(op.parameters))

            self.table_ops.setItem(row, 0, item_id)
            self.table_ops.setItem(row, 1, item_action)
            self.table_ops.setItem(row, 2, item_desc)

        # Check for external file operations
        ext_reqs = self.executor.get_external_file_requirements()
        if ext_reqs:
            names = [f"'{r['name']}' ({r['type']})" for r in ext_reqs]
            self.lbl_ops_badge.setText(f"✓ {len(ops)} Operations | Requires Per-Trial External Data for: {', '.join(names)}")
            self.lbl_ops_badge.setStyleSheet("color: #FFB703; font-weight: bold;")
            self.grp_external.setEnabled(True)
            self.lbl_ext_info.setText(
                f"Auto-matching active for: {', '.join(names)}. "
                f"Place per-trial files in the directory below (e.g. {{trial}}_{ext_reqs[0]['name']}.csv)."
            )
        else:
            self.lbl_ops_badge.setText(f"✓ {len(ops)} Operations | Pure Intrinsic (Self-Contained in each C3D)")
            self.lbl_ops_badge.setStyleSheet("color: #2EC4B6; font-weight: bold;")
            self.grp_external.setEnabled(False)
            self.lbl_ext_info.setText("All operations are calculated from trial's internal markers/analogs. No external files needed.")

        self._rematch_external_files()

    # --------------------------------------------------------------------------
    # External Files Directory & Auto-Matching
    # --------------------------------------------------------------------------

    def _browse_external_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder Containing External Data Files")
        if d:
            self.txt_ext_dir.setText(d)
            self.external_dir = d
            self._rematch_external_files()

    def _rematch_external_files(self):
        """Update the Queue table with matching external files for each C3D file."""
        ext_reqs = self.executor.get_external_file_requirements()
        s_dirs = [self.txt_ext_dir.text().strip()] if self.txt_ext_dir.text().strip() else []

        for row in range(self.table_queue.rowCount()):
            c3d_path = self.file_queue[row] if row < len(self.file_queue) else ""
            if not c3d_path:
                continue

            if not ext_reqs:
                item_ext = QTableWidgetItem("None required (Intrinsic)")
                item_ext.setForeground(QColor("#2EC4B6"))
                self.table_queue.setItem(row, 2, item_ext)
                continue

            # Check matches for all required external entities
            matched_items = []
            all_matched = True

            for req in ext_reqs:
                entity_name = req["name"]

                found = self.executor.resolve_external_file_for_trial(
                    c3d_file_path=c3d_path,
                    entity_name=entity_name,
                    search_dirs=s_dirs,
                    original_fallback=""
                )
                if found:
                    matched_items.append(f"{entity_name} \u2192 {os.path.basename(found)}")
                else:
                    matched_items.append(f"{entity_name} \u2192 ⚠ Missing")
                    all_matched = False

            item_text = "; ".join(matched_items)
            item_ext = QTableWidgetItem(item_text)
            if all_matched:
                item_ext.setForeground(QColor("#2EC4B6"))  # Teal / Green
            else:
                item_ext.setForeground(QColor("#FFB703"))  # Amber / Warning
            self.table_queue.setItem(row, 2, item_ext)

    # --------------------------------------------------------------------------
    # Queue Management & Drag-and-Drop
    # --------------------------------------------------------------------------

    def _add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select C3D Motion Capture Files", "", "C3D Files (*.c3d);;All Files (*)"
        )
        count = 0
        for p in paths:
            if self._add_file_to_queue(p):
                count += 1
        self._update_queue_ui()
        if count > 0:
            self._log(f"Added {count} C3D file(s) to queue.", "info")

    def _add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing C3D Files")
        if folder:
            count = 0
            for root, _, files in os.walk(folder):
                for f in sorted(files):
                    if f.lower().endswith(".c3d"):
                        if self._add_file_to_queue(os.path.join(root, f)):
                            count += 1
            self._update_queue_ui()
            self._log(f"Added {count} C3D file(s) from folder: {folder}", "info")

    def _add_file_to_queue(self, path: str) -> bool:
        if not path or not path.lower().endswith(".c3d"):
            return False
        canon = _canonical_path(path)
        if not os.path.isfile(canon):
            return False
        key = canon.lower() if sys.platform in ("darwin", "win32") else canon
        if key in self._canonical_file_set:
            return False
        self._canonical_file_set.add(key)
        self.file_queue.append(canon)
        return True

    def _remove_selected_files(self):
        selected_rows = sorted(set(idx.row() for idx in self.table_queue.selectedIndexes()), reverse=True)
        for r in selected_rows:
            if r < len(self.file_queue):
                removed = self.file_queue.pop(r)
                canon = _canonical_path(removed)
                key = canon.lower() if sys.platform in ("darwin", "win32") else canon
                self._canonical_file_set.discard(key)
        self._update_queue_ui()

    def _clear_queue(self):
        self.file_queue.clear()
        self._canonical_file_set.clear()
        self._update_queue_ui()

    def _update_queue_ui(self):
        self.table_queue.setRowCount(len(self.file_queue))
        for row, path in enumerate(self.file_queue):
            fname = os.path.basename(path)
            fdir = os.path.dirname(path)

            item_name = QTableWidgetItem(fname)
            item_name.setToolTip(path)
            item_dir = QTableWidgetItem(fdir)
            item_dir.setToolTip(fdir)
            item_status = QTableWidgetItem("Queued")
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QColor("#8C96AB"))

            self.table_queue.setItem(row, 0, item_name)
            self.table_queue.setItem(row, 1, item_dir)
            self.table_queue.setItem(row, 3, item_status)

        self._rematch_external_files()
        self.lbl_queue_stats.setText(f"Queued: {len(self.file_queue)} file(s)")

        # Auto-propose output directory if empty
        if self.file_queue and not self.txt_out_dir.text().strip():
            first_dir = os.path.dirname(self.file_queue[0])
            self.txt_out_dir.setText(os.path.join(first_dir, "batch_processed"))

    def _table_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _table_drag_move(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _table_drop(self, event):
        count = 0
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if os.path.isfile(local_path) and local_path.lower().endswith(".c3d"):
                    if self._add_file_to_queue(local_path):
                        count += 1
                elif os.path.isdir(local_path):
                    for root, _, files in os.walk(local_path):
                        for f in sorted(files):
                            if f.lower().endswith(".c3d"):
                                if self._add_file_to_queue(os.path.join(root, f)):
                                    count += 1
            self._update_queue_ui()
            if count > 0:
                self._log(f"Dropped {count} new C3D file(s) into queue.", "info")
            event.acceptProposedAction()

    # --------------------------------------------------------------------------
    # Output Settings
    # --------------------------------------------------------------------------

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory for Processed C3D Files")
        if d:
            self.txt_out_dir.setText(d)

    # --------------------------------------------------------------------------
    # Batch Execution
    # --------------------------------------------------------------------------

    def _start_batch(self):
        if not self.file_queue:
            QMessageBox.warning(self, "No Files Queued", "Please add one or more C3D files to the queue.")
            return

        if not self.executor.operations:
            QMessageBox.warning(self, "No Pipeline Loaded", "Please select a Pipeline XML file or active pipeline with operations.")
            return

        # Determine output directory
        if self.rb_out_folder.isChecked():
            out_dir = self.txt_out_dir.text().strip()
            if not out_dir:
                QMessageBox.warning(self, "No Output Folder", "Please specify an output folder.")
                return
            suffix = ""
        else:
            out_dir = os.path.dirname(self.file_queue[0])
            suffix = self.txt_suffix.text().strip()

        os.makedirs(out_dir, exist_ok=True)
        self.last_output_dir = out_dir

        # Check for external file requirements & warnings
        ext_reqs = self.executor.get_external_file_requirements()
        if ext_reqs:
            s_dirs = [self.txt_ext_dir.text().strip()] if self.txt_ext_dir.text().strip() else []
            missing_count = 0
            for path in self.file_queue:
                for req in ext_reqs:
                    found = self.executor.resolve_external_file_for_trial(
                        path, req["name"], search_dirs=s_dirs,
                        original_fallback=""
                    )
                    if not found:
                        missing_count += 1
            if missing_count > 0:
                reply = QMessageBox.question(
                    self, "Missing External Files",
                    f"{missing_count} per-trial external data file(s) were not found for the queued trials.\n\n"
                    f"Do you want to proceed anyway? (Missing markers/channels will be skipped with a warning).",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

        # Prepare UI for processing
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_open_out.setEnabled(False)
        self.progress_bar.setValue(0)
        self.txt_log.clear()

        # Build custom file map
        s_dirs = [self.txt_ext_dir.text().strip()] if self.txt_ext_dir.text().strip() else []
        custom_maps = {}
        for c3d_path in self.file_queue:
            t_map = {}
            for req in ext_reqs:
                ename = req["name"]
                found = self.executor.resolve_external_file_for_trial(
                    c3d_path, ename, search_dirs=s_dirs,
                    original_fallback=""
                )
                if found:
                    t_map[ename] = found
            custom_maps[c3d_path] = t_map

        # Launch Worker Thread
        self.worker = BatchWorker(
            executor=self.executor,
            file_queue=self.file_queue,
            output_dir=out_dir,
            suffix=suffix,
            external_search_dirs=s_dirs,
            custom_file_maps=custom_maps,
            apply_trim_roi=self.chk_trim_roi.isChecked(),
            parent=self
        )
        self.worker.progressUpdated.connect(self._on_worker_progress)
        self.worker.fileCompleted.connect(self._on_file_completed)
        self.worker.logMessage.connect(self._log)
        self.worker.batchFinished.connect(self._on_batch_finished)
        self.worker.start()

    def _cancel_batch(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.lbl_progress_status.setText("Cancelling...")
            self.worker.cancel()

    def _on_worker_progress(self, current: int, total: int, fname: str):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_progress_status.setText(f"Processing ({current}/{total}): {fname}")

        # Highlight current row
        idx = current - 1
        if 0 <= idx < self.table_queue.rowCount():
            item_status = self.table_queue.item(idx, 3)
            if item_status:
                item_status.setText("Processing...")
                item_status.setForeground(QColor("#00ADB5"))

    def _on_file_completed(self, idx: int, fname: str, success: bool, warnings: list, errors: list, elapsed: float):
        if 0 <= idx < self.table_queue.rowCount():
            item_status = self.table_queue.item(idx, 3)
            if item_status:
                if success and not warnings:
                    item_status.setText(f"✓ Done ({elapsed:.1f}s)")
                    item_status.setForeground(QColor("#2EC4B6"))
                elif success and warnings:
                    item_status.setText(f"⚠ Warning ({elapsed:.1f}s)")
                    item_status.setForeground(QColor("#FFB703"))
                    item_status.setToolTip("\n".join(warnings))
                else:
                    item_status.setText("✕ Failed")
                    item_status.setForeground(QColor("#E63946"))
                    item_status.setToolTip("\n".join(errors))

    def _on_batch_finished(self, succeeded: int, failed: int, total_warnings: int, elapsed: float):
        self.progress_bar.setValue(100)
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_open_out.setEnabled(True)

        summary_msg = f"Finished in {elapsed:.2f}s | Succeeded: {succeeded} | Failed: {failed} | Warnings: {total_warnings}"
        self.lbl_progress_status.setText(summary_msg)
        self._log("=" * 60, "info")
        self._log(f"BATCH EXECUTION COMPLETE: {summary_msg}", "success" if failed == 0 else "warning")
        self._log(f"Output files saved to: {self.last_output_dir}", "info")
        self._log("=" * 60, "info")

        QMessageBox.information(
            self,
            "Batch Processing Complete",
            f"Batch execution finished in {elapsed:.2f} seconds.\n\n"
            f"• Succeeded: {succeeded}\n"
            f"• Failed: {failed}\n"
            f"• Warnings: {total_warnings}\n\n"
            f"Output Destination:\n{self.last_output_dir}"
        )

    def _open_output_folder(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            QDesktopServices.openUrl(f"file://{os.path.abspath(self.last_output_dir)}")

    def _export_log_file(self):
        text = self.txt_log.toPlainText()
        if not text:
            QMessageBox.information(self, "Export Log", "Log is currently empty.")
            return

        default_path = os.path.join(self.last_output_dir, "batch_processing_log.txt") if self.last_output_dir else "batch_log.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export Batch Processing Log", default_path, "Text Files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                QMessageBox.information(self, "Log Exported", f"Log successfully saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to save log:\n{e}")

    def _log(self, text: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        if level == "error":
            color = "#E63946"
        elif level == "warning":
            color = "#FFB703"
        elif level == "success":
            color = "#2EC4B6"
        else:
            color = "#8C96AB"

        html = f"<span style='color: #6C7A89;'>[{timestamp}]</span> <span style='color: {color};'>{text}</span>"
        self.txt_log.append(html)

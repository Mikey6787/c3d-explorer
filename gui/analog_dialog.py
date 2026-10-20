"""
Interactive Analog Channels Manager & Signal Processing Tool.
Allows renaming, deleting, adding/importing analog channels (from TXT, CSV, TSV, XLSX),
and applying Butterworth filters (Lowpass, Highpass, Bandpass, Bandstop, Notch),
Full-Wave Rectification, Moving RMS Envelopes, and EMG Linear Envelopes with live preview.
"""

from typing import Dict, List, Optional, Tuple, Union, Any
import os
import csv
import numpy as np
from scipy import signal

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QFont, QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QRadioButton, QButtonGroup, QGroupBox,
    QTabWidget, QSplitter, QHeaderView, QMessageBox, QFileDialog,
    QInputDialog, QWidget, QAbstractItemView, QFrame
)
import pyqtgraph as pg

from core.data_models import C3DTrial
from gui.undo_commands import (
    FilterAnalogChannelCommand,
    AddAnalogChannelCommand,
    DeleteAnalogChannelsCommand,
    RenameAnalogChannelCommand
)


def _safe_info(parent, title: str, text: str):
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    QMessageBox.information(parent, title, text)


def _safe_warning(parent, title: str, text: str):
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    QMessageBox.warning(parent, title, text)


def _safe_question(parent, title: str, text: str, default_yes: bool = True) -> int:
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return QMessageBox.Yes if default_yes else QMessageBox.No
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)



def parse_analog_file(filepath: str, expected_frames: int) -> Tuple[Optional[Dict[str, np.ndarray]], Optional[str]]:
    """
    Parse an Excel (.xlsx), CSV (.csv), TSV (.tsv), or Text (.txt) file containing analog channel data.
    Returns (dict_of_columns, error_message).
    dict_of_columns maps column name (e.g. "Column 1" or header name) -> 1D numpy array.
    """
    if not filepath or not os.path.isfile(filepath):
        return None, "File does not exist or invalid path specified."

    ext = os.path.splitext(filepath)[1].lower()
    raw_rows: List[List[Any]] = []

    try:
        if ext in [".xlsx", ".xlsm"]:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if row is None or all(c is None or str(c).strip() == "" for c in row):
                    continue
                raw_rows.append(list(row))
            wb.close()
        elif ext == ".xls":
            try:
                import xlrd
                wb = xlrd.open_workbook(filepath)
                ws = wb.sheet_by_index(0)
                for r in range(ws.nrows):
                    row = [ws.cell_value(r, c) for c in range(ws.ncols)]
                    if any(c != "" and c is not None for c in row):
                        raw_rows.append(row)
            except ImportError:
                return None, "Older .xls files require 'xlrd'. Please save file as modern Excel (.xlsx) or CSV (.csv)."
        else:
            with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()

            sample = content[:4096]
            delim = ","
            if "\t" in sample:
                delim = "\t"
            elif ";" in sample:
                delim = ";"
            elif "," in sample:
                delim = ","
            else:
                delim = None

            if delim is not None:
                reader = csv.reader(content.splitlines(), delimiter=delim)
                for row in reader:
                    if row and any(c.strip() for c in row):
                        raw_rows.append([c.strip() for c in row])
            else:
                for line in content.splitlines():
                    p = line.strip().split()
                    if p:
                        raw_rows.append(p)

    except Exception as e:
        return None, f"Failed to read file:\n{e}"

    if not raw_rows:
        return None, "The selected file is empty."

    # Inspect first row for column headers
    header_names: List[str] = []
    first_row = raw_rows[0]
    has_header = False
    try:
        float(str(first_row[0]).replace(",", "."))
    except (ValueError, TypeError):
        has_header = True
        header_names = [str(c).strip() if c is not None else f"Column {i+1}" for i, c in enumerate(first_row)]
        raw_rows = raw_rows[1:]

    # Parse numeric data column-wise
    parsed_columns: Dict[str, List[float]] = {}
    for row in raw_rows:
        col_idx = 0
        for val in row:
            if val is None or str(val).strip() == "":
                continue
            try:
                num = float(str(val).replace(",", "."))
                col_name = header_names[col_idx] if (has_header and col_idx < len(header_names)) else f"Column {col_idx+1}"
                if col_name not in parsed_columns:
                    parsed_columns[col_name] = []
                parsed_columns[col_name].append(num)
                col_idx += 1
            except (ValueError, TypeError):
                pass

    if not parsed_columns:
        return None, "No numeric channel data found in the selected file."

    result: Dict[str, np.ndarray] = {k: np.array(v, dtype=np.float64) for k, v in parsed_columns.items()}
    return result, None


def apply_butterworth_filter(
    data: np.ndarray,
    fs: float,
    filter_type: str,
    order: int = 4,
    cutoff: Union[float, Tuple[float, float]] = 20.0
) -> np.ndarray:
    """Zero-phase Butterworth filter (lowpass, highpass, bandpass, bandstop, notch)."""
    if len(data) == 0:
        return data.copy()
    nyq = 0.5 * fs
    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return data.copy()

    clean_data = data.copy()
    if not np.all(valid_mask):
        x = np.arange(len(data))
        clean_data[~valid_mask] = np.interp(x[~valid_mask], x[valid_mask], data[valid_mask])

    f_type = filter_type.lower()
    if "low" in f_type:
        c_val = cutoff if isinstance(cutoff, (int, float)) else cutoff[0]
        wn = min(max(c_val / nyq, 0.0001), 0.9999)
        b, a = signal.butter(order, wn, btype="low")
    elif "high" in f_type:
        c_val = cutoff if isinstance(cutoff, (int, float)) else cutoff[0]
        wn = min(max(c_val / nyq, 0.0001), 0.9999)
        b, a = signal.butter(order, wn, btype="high")
    elif "bandpass" in f_type:
        if isinstance(cutoff, (list, tuple)):
            low, high = cutoff
        else:
            low, high = 10.0, min(100.0, nyq * 0.9)
        wn = [min(max(low / nyq, 0.0001), 0.999), min(max(high / nyq, 0.0002), 0.9999)]
        b, a = signal.butter(order, wn, btype="bandpass")
    elif "notch" in f_type or "bandstop" in f_type or "stop" in f_type:
        if isinstance(cutoff, (list, tuple)):
            low, high = cutoff
            wn = [min(max(low / nyq, 0.0001), 0.999), min(max(high / nyq, 0.0002), 0.9999)]
            b, a = signal.butter(order, wn, btype="bandstop")
        else:
            # Notch filter around center frequency
            f0 = min(max(cutoff, 1.0), nyq - 1.0)
            q = 30.0  # Quality factor
            b, a = signal.iirnotch(f0, q, fs=fs)
    else:
        return data.copy()

    # Zero-phase digital filtering
    filtered = signal.filtfilt(b, a, clean_data)
    if not np.all(valid_mask):
        filtered[~valid_mask] = np.nan
    return filtered


def compute_moving_rms(data: np.ndarray, window_size: int) -> np.ndarray:
    """Compute moving RMS (Root Mean Square) envelope using a sliding window."""
    if len(data) == 0:
        return data.copy()
    w = max(1, min(len(data), int(window_size)))
    valid_mask = ~np.isnan(data)
    clean = data.copy()
    if not np.all(valid_mask):
        x = np.arange(len(data))
        clean[~valid_mask] = np.interp(x[~valid_mask], x[valid_mask], data[valid_mask])

    kernel = np.ones(w) / float(w)
    mean_sq = np.convolve(clean ** 2, kernel, mode="same")
    rms = np.sqrt(np.maximum(mean_sq, 0.0))
    if not np.all(valid_mask):
        rms[~valid_mask] = np.nan
    return rms


def compute_signal_stats(data: np.ndarray) -> Dict[str, float]:
    """Calculate basic signal metrics."""
    valid = data[~np.isnan(data)] if len(data) > 0 else np.array([])
    if len(valid) == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "rms": 0.0, "p2p": 0.0}
    return {
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "rms": float(np.sqrt(np.mean(valid ** 2))),
        "p2p": float(np.max(valid) - np.min(valid)),
    }


class ImportAnalogDialog(QDialog):
    """Dialog to import a new analog channel from an Excel, CSV, or Text file."""

    def __init__(self, trial: C3DTrial, parent=None):
        super().__init__(parent)
        self.trial = trial
        self.parsed_data: Optional[Dict[str, np.ndarray]] = None
        self.imported_data: Optional[np.ndarray] = None
        self.channel_name: str = ""
        self.channel_unit: str = "V"

        self.setWindowTitle("Import New Analog Channel")
        self.resize(520, 360)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # File Chooser
        file_box = QHBoxLayout()
        self.txt_path = QLineEdit()
        self.txt_path.setReadOnly(True)
        self.txt_path.setPlaceholderText("Select .csv, .txt, .tsv, or .xlsx file...")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_file)
        file_box.addWidget(self.txt_path)
        file_box.addWidget(btn_browse)
        form.addRow("Data File:", file_box)

        # Column Selector
        self.combo_col = QComboBox()
        self.combo_col.setEnabled(False)
        self.combo_col.currentIndexChanged.connect(self._on_column_changed)
        form.addRow("Column / Signal:", self.combo_col)

        # Channel Name
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. EMG_Tibialis, Force_Sensor_1")
        form.addRow("Channel Name:", self.txt_name)

        # Unit
        self.txt_unit = QLineEdit("V")
        self.txt_unit.setPlaceholderText("e.g. V, mV, N, deg")
        form.addRow("Physical Unit:", self.txt_unit)

        layout.addLayout(form)

        # Frame Status & Info Box
        self.lbl_info = QLabel(
            f"Expected frames: {self.trial.analog_frame_count} "
            f"({self.trial.analog_rate:.0f} Hz, {self.trial.duration_seconds:.2f} s)"
        )
        self.lbl_info.setStyleSheet("color: #8C96AB; font-size: 11px;")
        layout.addWidget(self.lbl_info)

        self.lbl_match = QLabel("Please select a file to import.")
        self.lbl_match.setStyleSheet("color: #00ADB5; font-weight: 600; font-size: 12px;")
        layout.addWidget(self.lbl_match)

        layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        self.btn_import = QPushButton("Import Channel")
        self.btn_import.setObjectName("primaryBtn")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._do_import)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_import)
        layout.addLayout(btn_row)

    def _browse_file(self):
        filters = "Data Files (*.csv *.txt *.tsv *.xlsx *.xlsm);;CSV Files (*.csv);;Text Files (*.txt *.tsv);;Excel Files (*.xlsx);;All Files (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Select Analog Data File", "", filters)
        if not path:
            return

        cols, err = parse_analog_file(path, self.trial.analog_frame_count)
        if err or not cols:
            _safe_warning(self, "Import Error", err or "Failed to extract numeric data from file.")
            return

        self.txt_path.setText(path)
        self.parsed_data = cols
        self.combo_col.clear()
        for k in sorted(cols.keys()):
            self.combo_col.addItem(f"{k} ({len(cols[k])} samples)", k)

        self.combo_col.setEnabled(True)
        base_name = os.path.splitext(os.path.basename(path))[0]
        self.txt_name.setText(base_name)
        self._on_column_changed()

    def _on_column_changed(self):
        if not self.parsed_data or self.combo_col.currentIndex() < 0:
            self.btn_import.setEnabled(False)
            return

        col_key = self.combo_col.currentData()
        if col_key not in self.parsed_data:
            return

        data = self.parsed_data[col_key]
        n_samples = len(data)
        exp = self.trial.analog_frame_count

        if n_samples == exp:
            self.lbl_match.setText(f"✓ Exact frame match: {n_samples} samples.")
            self.lbl_match.setStyleSheet("color: #00E676; font-weight: 600; font-size: 12px;")
        elif n_samples > exp:
            self.lbl_match.setText(f"Notice: File has {n_samples} samples (will be truncated to trial's {exp} samples).")
            self.lbl_match.setStyleSheet("color: #FFB703; font-weight: 600; font-size: 12px;")
        else:
            self.lbl_match.setText(f"Notice: File has {n_samples} samples (will be zero-padded to trial's {exp} samples).")
            self.lbl_match.setStyleSheet("color: #FFB703; font-weight: 600; font-size: 12px;")

        self.btn_import.setEnabled(True)

    def _do_import(self):
        name = self.txt_name.text().strip()
        if not name:
            _safe_warning(self, "Invalid Name", "Please enter a valid channel name.")
            return

        if name in self.trial.analogs:
            reply = _safe_question(
                self, "Channel Exists",
                f"An analog channel named '{name}' already exists. Overwrite it?",
                default_yes=True
            )
            if reply != QMessageBox.Yes:
                return

        col_key = self.combo_col.currentData()
        raw = self.parsed_data[col_key]
        exp = self.trial.analog_frame_count

        # Adapt row length to trial's analog frame count
        if len(raw) == exp:
            adapted = raw.copy()
        elif len(raw) > exp:
            adapted = raw[:exp].copy()
        else:
            adapted = np.zeros(exp, dtype=np.float64)
            adapted[:len(raw)] = raw

        self.imported_data = adapted
        self.channel_name = name
        self.channel_unit = self.txt_unit.text().strip() or "V"
        self.accept()


class AnalogToolsDialog(QDialog):
    """
    Comprehensive Analog Management & Signal Processing Dialog.
    Features:
    - Channel Listing, Statistics, Search, and Filtering
    - Channel Renaming and Deletion
    - Importing new analog channels from TXT/CSV/XLSX
    - Real-time Butterworth filtering (Lowpass, Highpass, Bandpass, Bandstop, Notch)
    - Moving RMS Envelopes and Signal Rectification
    - Embedded interactive PyQtGraph Preview Plot
    - Instant plotting to Universal Plotter
    """

    analogsChanged = Signal()          # Emitted when channels are renamed, deleted, added, or filtered
    plotChannelRequested = Signal(str) # Emitted with channel_name to activate under Analog Channels in Universal Plotter
    plotChannelsRequested = Signal(list) # Emitted with list of channel names to activate in Universal Plotter
    plotRequested = Signal(str, np.ndarray)  # Emitted to plot custom/filtered curve

    def __init__(self, trial: C3DTrial, parent=None, undo_stack: Optional[QUndoStack] = None):
        super().__init__(parent)
        self.trial = trial
        if undo_stack is not None:
            self.undo_stack = undo_stack
        elif parent is not None and hasattr(parent, "undo_stack"):
            self.undo_stack = parent.undo_stack
        else:
            self.undo_stack = QUndoStack(self)

        self._preview_curve: Optional[pg.PlotDataItem] = None
        self._raw_curve: Optional[pg.PlotDataItem] = None

        self.setWindowTitle("Analog Channels & Signal Processing")
        self.resize(1000, 680)
        self._setup_ui()
        self._populate_channel_table()
        self._populate_filter_channels()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # Tabs: 1. Channels Manager | 2. Filter & Signal Processing
        self.tabs = QTabWidget()
        self.tab_manager = QWidget()
        self.tab_filter = QWidget()

        self._setup_manager_tab()
        self._setup_filter_tab()

        self.tabs.addTab(self.tab_manager, "Channels Manager")
        self.tabs.addTab(self.tab_filter, "Filter & Signal Processing")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

        # Bottom Bar: Small subtle info on the left, Undo, Redo, and Close buttons on the right
        bottom_box = QHBoxLayout()
        bottom_box.setContentsMargins(4, 4, 4, 0)
        bottom_box.setSpacing(8)

        self.lbl_footer_info = QLabel()
        self.lbl_footer_info.setStyleSheet("color: #8F9BB3; font-size: 11px; background: transparent; border: none;")
        self.lbl_header_channels = self.lbl_footer_info  # alias for backwards compatibility
        self._update_footer_info()

        bottom_box.addWidget(self.lbl_footer_info)
        bottom_box.addStretch()

        self.btn_undo = QPushButton("↶ Undo")
        self.btn_undo.setToolTip("Undo last action (Ctrl+Z / Cmd+Z)")
        self.btn_undo.setFixedWidth(80)
        self.btn_undo.clicked.connect(self._action_undo)

        self.btn_redo = QPushButton("↷ Redo")
        self.btn_redo.setToolTip("Redo last undone action (Ctrl+Y / Cmd+Shift+Z)")
        self.btn_redo.setFixedWidth(80)
        self.btn_redo.clicked.connect(self._action_redo)

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)

        bottom_box.addWidget(self.btn_undo)
        bottom_box.addWidget(self.btn_redo)
        bottom_box.addWidget(btn_close)
        main_layout.addLayout(bottom_box)

        # Dialog-level keyboard shortcuts for Undo / Redo
        act_undo = QAction(self)
        act_undo.setShortcut(QKeySequence.Undo)
        act_undo.triggered.connect(self._action_undo)
        self.addAction(act_undo)

        act_redo = QAction(self)
        act_redo.setShortcut(QKeySequence.Redo)
        act_redo.triggered.connect(self._action_redo)
        self.addAction(act_redo)

        if self.undo_stack:
            self.undo_stack.canUndoChanged.connect(self._on_can_undo_changed)
            self.undo_stack.canRedoChanged.connect(self._on_can_redo_changed)
        self._update_undo_redo_actions()

    def _on_can_undo_changed(self, can_undo: bool):
        self._update_undo_redo_actions()

    def _on_can_redo_changed(self, can_redo: bool):
        self._update_undo_redo_actions()

    def _action_undo(self):
        try:
            if self.undo_stack and self.undo_stack.canUndo():
                self.undo_stack.undo()
        except Exception:
            pass

    def _action_redo(self):
        try:
            if self.undo_stack and self.undo_stack.canRedo():
                self.undo_stack.redo()
        except Exception:
            pass

    def _update_undo_redo_actions(self):
        try:
            if not hasattr(self, "btn_undo") or not hasattr(self, "btn_redo"):
                return
            if not self.undo_stack:
                return
            can_u = bool(self.undo_stack.canUndo())
            can_r = bool(self.undo_stack.canRedo())
            self.btn_undo.setEnabled(can_u)
            self.btn_redo.setEnabled(can_r)
            if can_u:
                self.btn_undo.setToolTip(f"Undo {self.undo_stack.undoText()} (Ctrl+Z / Cmd+Z)")
            else:
                self.btn_undo.setToolTip("Undo (Ctrl+Z / Cmd+Z)")
            if can_r:
                self.btn_redo.setToolTip(f"Redo {self.undo_stack.redoText()} (Ctrl+Y / Cmd+Shift+Z)")
            else:
                self.btn_redo.setToolTip("Redo (Ctrl+Y / Cmd+Shift+Z)")
        except (RuntimeError, AttributeError):
            pass

    def closeEvent(self, event):
        try:
            if self.undo_stack:
                try:
                    self.undo_stack.canUndoChanged.disconnect(self._on_can_undo_changed)
                except Exception:
                    pass
                try:
                    self.undo_stack.canRedoChanged.disconnect(self._on_can_redo_changed)
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(event)

    # ---------------------------------------------------------
    # TAB 1: Channel Manager
    # ---------------------------------------------------------
    def _setup_manager_tab(self):
        tab_layout = QVBoxLayout(self.tab_manager)
        tab_layout.setContentsMargins(8, 12, 8, 8)
        tab_layout.setSpacing(10)

        # Search Bar & Filter
        top_bar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter analog channels...")
        self.search_box.textChanged.connect(self._filter_channel_table)
        top_bar.addWidget(self.search_box)
        top_bar.addStretch()

        # Action Buttons
        btn_import = QPushButton("+ Import Channel...")
        btn_import.setObjectName("primaryBtn")
        btn_import.setToolTip("Import single-column or multi-column analog signal from TXT, CSV, or XLSX")
        btn_import.clicked.connect(self._action_import_channel)

        btn_rename = QPushButton("Rename...")
        btn_rename.clicked.connect(self._action_rename_channel)

        btn_delete = QPushButton("Delete")
        btn_delete.setStyleSheet("QPushButton { color: #EF4444; border-color: #7F1D1D; } QPushButton:hover { background-color: #7F1D1D; color: #FFFFFF; }")
        btn_delete.clicked.connect(self._action_delete_channel)

        btn_plot = QPushButton("Plot in Plotter")
        btn_plot.setToolTip("Send selected channel directly to the Universal Plotter")
        btn_plot.clicked.connect(self._action_plot_selected)

        top_bar.addWidget(btn_import)
        top_bar.addWidget(btn_rename)
        top_bar.addWidget(btn_delete)
        top_bar.addWidget(btn_plot)

        tab_layout.addLayout(top_bar)

        # Channels Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Channel Name", "Unit", "Rate (Hz)", "Frames", "Min", "Max", "Mean", "RMS"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 8):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._action_rename_channel)
        tab_layout.addWidget(self.table)

    def _populate_channel_table(self):
        self.table.setRowCount(0)
        channels = sorted(list(self.trial.analogs.keys()))
        self.table.setRowCount(len(channels))

        rate = self.trial.analog_rate
        for row, name in enumerate(channels):
            data = self.trial.analogs[name]
            unit = self.trial.analog_units.get(name, "V")
            stats = compute_signal_stats(data)

            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.UserRole, name)
            item_unit = QTableWidgetItem(unit)
            item_rate = QTableWidgetItem(f"{rate:.1f}")
            item_frames = QTableWidgetItem(str(len(data)))
            item_min = QTableWidgetItem(f"{stats['min']:.3f}")
            item_max = QTableWidgetItem(f"{stats['max']:.3f}")
            item_mean = QTableWidgetItem(f"{stats['mean']:.3f}")
            item_rms = QTableWidgetItem(f"{stats['rms']:.3f}")

            for c, it in enumerate([item_name, item_unit, item_rate, item_frames, item_min, item_max, item_mean, item_rms]):
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter if c < 2 else Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, c, it)

        self._update_footer_info()

    def _filter_channel_table(self, text: str):
        q = text.strip().lower()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            visible = (q in item.text().lower()) if item else True
            self.table.setRowHidden(r, not visible)

    def _update_footer_info(self):
        if not hasattr(self, "lbl_footer_info"):
            return
        n_ch = len(self.trial.analogs)
        rate = self.trial.analog_rate
        n_frames = self.trial.analog_frame_count
        dur = self.trial.duration_seconds
        sub = getattr(self.trial, "analog_subsamples", 1)
        self.lbl_footer_info.setText(
            f"Analog Channels: {n_ch}   |   Sampling Rate: {rate:.1f} Hz   |   Frames: {n_frames} ({dur:.2f} s)   |   Subsamples/Point: {sub}x"
        )

    def _update_header_stats(self):
        self._update_footer_info()

    def _get_selected_channel(self) -> Optional[str]:
        row = self.table.currentRow()
        if row >= 0:
            it = self.table.item(row, 0)
            if it:
                return it.data(Qt.UserRole) or it.text()
        return None

    def _get_selected_channels(self) -> List[str]:
        selected_rows = sorted(list(set(idx.row() for idx in self.table.selectedIndexes())))
        names = []
        for r in selected_rows:
            it = self.table.item(r, 0)
            if it:
                ch = it.data(Qt.UserRole) or it.text()
                if ch and ch in self.trial.analogs and ch not in names:
                    names.append(ch)
        if not names:
            single = self._get_selected_channel()
            if single and single in self.trial.analogs:
                names.append(single)
        return names

    def _action_rename_channel(self):
        ch_names = self._get_selected_channels()
        if not ch_names:
            _safe_info(self, "Rename Channel", "Please select an analog channel from the table to rename.")
            return

        if len(ch_names) > 1:
            _safe_info(self, "Rename Channel", "Please select a single analog channel to rename.")
            return

        old_name = ch_names[0]
        new_name, ok = QInputDialog.getText(
            self, "Rename Analog Channel",
            f"Enter new name for channel '{old_name}':",
            QLineEdit.Normal, old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        clean_new = new_name.strip()
        if clean_new in self.trial.analogs:
            _safe_warning(self, "Rename Channel", f"A channel named '{clean_new}' already exists.")
            return

        # Rename with Undo/Redo command
        cmd = RenameAnalogChannelCommand(
            main_window=self.parent(),
            trial=self.trial,
            old_name=old_name,
            new_name=clean_new,
            analog_dialog=self
        )
        if self.undo_stack:
            self.undo_stack.push(cmd)
        else:
            cmd.redo()
        self.analogsChanged.emit()

    def _action_delete_channel(self):
        ch_names = self._get_selected_channels()
        if not ch_names:
            _safe_info(self, "Delete Channel", "Please select one or more analog channels from the table to delete.")
            return

        if len(ch_names) == 1:
            title = "Delete Channel"
            prompt = f"Are you sure you want to delete analog channel '{ch_names[0]}'?"
        else:
            title = "Delete Channels"
            preview = ", ".join(ch_names[:4]) + ("..." if len(ch_names) > 4 else "")
            prompt = f"Are you sure you want to delete {len(ch_names)} analog channels ({preview})?"

        reply = _safe_question(
            self, title,
            f"{prompt}\nThis action can be undone.",
            default_yes=True
        )
        if reply == QMessageBox.Yes:
            cmd = DeleteAnalogChannelsCommand(
                main_window=self.parent(),
                trial=self.trial,
                channel_names=ch_names,
                analog_dialog=self
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()
            self.analogsChanged.emit()

    def _action_import_channel(self):
        dlg = ImportAnalogDialog(self.trial, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.imported_data is not None:
            name = dlg.channel_name
            cmd = AddAnalogChannelCommand(
                main_window=self.parent(),
                trial=self.trial,
                channel_name=name,
                data=dlg.imported_data,
                unit=dlg.channel_unit,
                analog_dialog=self
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()
            self.analogsChanged.emit()
            _safe_info(self, "Import Successful", f"Analog channel '{name}' ({len(dlg.imported_data)} frames) imported successfully.")

    def _action_plot_selected(self):
        ch_names = self._get_selected_channels()
        if not ch_names:
            _safe_info(self, "Plot Channel", "Please select one or more analog channels from the table to plot.")
            return

        self.plotChannelsRequested.emit(ch_names)
        for ch in ch_names:
            self.plotChannelRequested.emit(ch)
            if hasattr(self, "plotRequested"):
                data = self.trial.analogs.get(ch)
                if data is not None:
                    self.plotRequested.emit(f"{ch} ({self.trial.analog_units.get(ch, 'V')})", data)

    # ---------------------------------------------------------
    # TAB 2: Filter & Signal Processing
    # ---------------------------------------------------------
    def _setup_filter_tab(self):
        tab_layout = QHBoxLayout(self.tab_filter)
        tab_layout.setContentsMargins(8, 12, 8, 8)
        tab_layout.setSpacing(14)

        # Left Controls Column
        ctrl_card = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(10)

        # 1. Channel Selector
        grp_channel = QGroupBox("Target Channel")
        form_ch = QFormLayout(grp_channel)
        self.combo_filter_ch = QComboBox()
        self.combo_filter_ch.currentIndexChanged.connect(self._update_filter_preview)
        form_ch.addRow("Channel:", self.combo_filter_ch)
        ctrl_layout.addWidget(grp_channel)

        # 2. Filter Algorithm Selector
        grp_algo = QGroupBox("Processing Method")
        form_algo = QFormLayout(grp_algo)
        self.combo_filter_type = QComboBox()
        self.combo_filter_type.addItems([
            "Butterworth Low-pass",
            "Butterworth High-pass",
            "Butterworth Band-pass",
            "Butterworth Band-stop",
            "Notch Filter (Powerline 50Hz/60Hz)",
            "Moving RMS Envelope",
            "Full-Wave Rectification",
            "EMG Linear Envelope (Rectify + Low-pass)"
        ])
        self.combo_filter_type.currentIndexChanged.connect(self._on_filter_type_changed)
        form_algo.addRow("Method:", self.combo_filter_type)
        ctrl_layout.addWidget(grp_algo)

        # 3. Dynamic Filter Parameters
        self.grp_params = QGroupBox("Filter Parameters")
        self.form_params = QFormLayout(self.grp_params)
        self.form_params.setSpacing(8)

        # Nyquist & Sampling Rate Badge
        self.lbl_nyquist_info = QLabel("Sampling Rate: 1000 Hz | Nyquist Limit: 500 Hz")
        self.lbl_nyquist_info.setStyleSheet("color: #00ADB5; font-size: 11px; font-weight: 600;")
        self.form_params.addRow(self.lbl_nyquist_info)

        # Filter Order
        self.spin_order = QSpinBox()
        self.spin_order.setRange(1, 10)
        self.spin_order.setValue(4)
        self.spin_order.valueChanged.connect(self._update_filter_preview)
        self.lbl_order = QLabel("Filter Order:")
        self.form_params.addRow(self.lbl_order, self.spin_order)

        # Cutoff Frequency (Single)
        self.spin_cutoff = QDoubleSpinBox()
        self.spin_cutoff.setRange(0.1, 5000.0)
        self.spin_cutoff.setValue(20.0)
        self.spin_cutoff.setDecimals(1)
        self.spin_cutoff.setSuffix(" Hz")
        self.spin_cutoff.valueChanged.connect(self._update_filter_preview)
        self.lbl_cutoff = QLabel("Cutoff Frequency:")
        self.form_params.addRow(self.lbl_cutoff, self.spin_cutoff)

        # Bandpass Low Cutoff
        self.spin_low_cutoff = QDoubleSpinBox()
        self.spin_low_cutoff.setRange(0.1, 5000.0)
        self.spin_low_cutoff.setValue(10.0)
        self.spin_low_cutoff.setDecimals(1)
        self.spin_low_cutoff.setSuffix(" Hz")
        self.spin_low_cutoff.valueChanged.connect(self._update_filter_preview)
        self.lbl_low_cutoff = QLabel("Low Cutoff:")
        self.form_params.addRow(self.lbl_low_cutoff, self.spin_low_cutoff)

        # Bandpass High Cutoff
        self.spin_high_cutoff = QDoubleSpinBox()
        self.spin_high_cutoff.setRange(0.1, 5000.0)
        self.spin_high_cutoff.setValue(100.0)
        self.spin_high_cutoff.setDecimals(1)
        self.spin_high_cutoff.setSuffix(" Hz")
        self.spin_high_cutoff.valueChanged.connect(self._update_filter_preview)
        self.lbl_high_cutoff = QLabel("High Cutoff:")
        self.form_params.addRow(self.lbl_high_cutoff, self.spin_high_cutoff)

        # RMS Window Size (ms)
        self.spin_rms_window = QDoubleSpinBox()
        self.spin_rms_window.setRange(1.0, 5000.0)
        self.spin_rms_window.setValue(50.0)
        self.spin_rms_window.setDecimals(1)
        self.spin_rms_window.setSuffix(" ms")
        self.spin_rms_window.valueChanged.connect(self._update_filter_preview)
        self.lbl_rms_window = QLabel("Window Duration:")
        self.form_params.addRow(self.lbl_rms_window, self.spin_rms_window)

        ctrl_layout.addWidget(self.grp_params)

        # 4. Output Actions (Save as New or Overwrite)
        grp_output = QGroupBox("Output Mode")
        v_out = QVBoxLayout(grp_output)
        self.rb_save_new = QRadioButton("Save as New Channel")
        self.rb_save_new.setChecked(True)
        self.rb_overwrite = QRadioButton("Overwrite Current Channel")

        self.txt_new_channel_name = QLineEdit()
        self.txt_new_channel_name.setPlaceholderText("New channel name...")

        self.rb_save_new.toggled.connect(lambda chk: self.txt_new_channel_name.setEnabled(chk))

        v_out.addWidget(self.rb_save_new)
        v_out.addWidget(self.txt_new_channel_name)
        v_out.addWidget(self.rb_overwrite)
        ctrl_layout.addWidget(grp_output)

        # Apply Button
        self.btn_apply_filter = QPushButton("Apply Filter")
        self.btn_apply_filter.setObjectName("primaryBtn")
        self.btn_apply_filter.clicked.connect(self._apply_filter_to_trial)
        ctrl_layout.addWidget(self.btn_apply_filter)

        ctrl_layout.addStretch()
        ctrl_card.setMinimumWidth(320)
        ctrl_card.setMaximumWidth(380)
        tab_layout.addWidget(ctrl_card)

        # Right Preview Column (PyQtGraph)
        preview_card = QWidget()
        prev_layout = QVBoxLayout(preview_card)
        prev_layout.setContentsMargins(0, 0, 0, 0)
        prev_layout.setSpacing(6)

        # Plot Header & Metrics
        prev_header = QHBoxLayout()
        lbl_prev_title = QLabel("<b>Real-Time Signal Preview</b>")
        lbl_prev_title.setStyleSheet("font-size: 13px; color: #ECEFF4;")
        self.lbl_metrics = QLabel("Raw RMS: --- | Filtered RMS: ---")
        self.lbl_metrics.setStyleSheet("font-size: 11px; color: #00ADB5; font-weight: 600;")
        prev_header.addWidget(lbl_prev_title)
        prev_header.addStretch()
        prev_header.addWidget(self.lbl_metrics)
        prev_layout.addLayout(prev_header)

        # Embedded Preview Plot
        self.preview_plot = pg.PlotWidget()
        self.preview_plot.setBackground("#151720")
        self.preview_plot.showGrid(x=True, y=True, alpha=0.25)
        self.preview_plot.setLabel("bottom", "Samples", units="")
        self.preview_plot.setLabel("left", "Amplitude")
        self.preview_plot.setContextMenuPolicy(Qt.NoContextMenu)
        # Suppress pyqtgraph default menus
        _pi = self.preview_plot.getPlotItem()
        _pi.setMenuEnabled(False)
        _pi.ctrlMenu = None
        _vb = _pi.getViewBox()
        _vb.setMenuEnabled(False)
        _vb.menu = None
        _vb.raiseContextMenu = lambda ev: None

        self.preview_legend = self.preview_plot.addLegend(offset=(-10, 10))
        prev_layout.addWidget(self.preview_plot)

        tab_layout.addWidget(preview_card, stretch=1)

    def _populate_filter_channels(self, select_name: Optional[str] = None):
        self.combo_filter_ch.blockSignals(True)
        self.combo_filter_ch.clear()
        channels = sorted(list(self.trial.analogs.keys()))
        for ch in channels:
            u = self.trial.analog_units.get(ch, "V")
            self.combo_filter_ch.addItem(f"{ch} ({u})", ch)

        if select_name and select_name in channels:
            idx = channels.index(select_name)
            self.combo_filter_ch.setCurrentIndex(idx)
        elif self.combo_filter_ch.count() > 0:
            self.combo_filter_ch.setCurrentIndex(0)

        self.combo_filter_ch.blockSignals(False)
        self._on_filter_type_changed()

    def _on_tab_changed(self, index: int):
        if index == 1:
            # Switched to Filter tab -> refresh channels and preview
            sel = self._get_selected_channel()
            self._populate_filter_channels(sel)

    def _on_filter_type_changed(self):
        method = self.combo_filter_type.currentText()
        rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
        nyq = 0.5 * rate
        self.lbl_nyquist_info.setText(f"Sampling Rate: {rate:.0f} Hz | Nyquist Limit: {nyq:.0f} Hz")

        # Adjust maximum spinbox values based on Nyquist frequency
        self.spin_cutoff.setMaximum(max(1.0, nyq - 0.1))
        self.spin_low_cutoff.setMaximum(max(1.0, nyq - 0.2))
        self.spin_high_cutoff.setMaximum(max(1.0, nyq - 0.1))

        # Show / hide relevant parameter rows
        is_low_high = ("Low-pass" in method or "High-pass" in method)
        is_band = ("Band-pass" in method or "Band-stop" in method)
        is_notch = ("Notch" in method)
        is_rms = ("RMS" in method)
        is_rect = ("Rectification" in method)
        is_linear_env = ("Linear Envelope" in method)

        self.lbl_order.setVisible(is_low_high or is_band or is_linear_env)
        self.spin_order.setVisible(is_low_high or is_band or is_linear_env)

        self.lbl_cutoff.setVisible(is_low_high or is_notch or is_linear_env)
        self.spin_cutoff.setVisible(is_low_high or is_notch or is_linear_env)
        if is_notch:
            self.lbl_cutoff.setText("Notch Center Frequency:")
            self.spin_cutoff.setValue(50.0 if self.spin_cutoff.value() == 20.0 else self.spin_cutoff.value())
        elif is_linear_env:
            self.lbl_cutoff.setText("Lowpass Cutoff:")
            self.spin_cutoff.setValue(6.0)
        else:
            self.lbl_cutoff.setText("Cutoff Frequency:")

        self.lbl_low_cutoff.setVisible(is_band)
        self.spin_low_cutoff.setVisible(is_band)
        self.lbl_high_cutoff.setVisible(is_band)
        self.spin_high_cutoff.setVisible(is_band)

        self.lbl_rms_window.setVisible(is_rms)
        self.spin_rms_window.setVisible(is_rms)

        self._suggest_output_name()
        self._update_filter_preview()

    def _suggest_output_name(self):
        ch = self.combo_filter_ch.currentData()
        if not ch:
            return
        method = self.combo_filter_type.currentText()
        if "Low-pass" in method:
            suffix = f"LP{self.spin_cutoff.value():.0f}Hz"
        elif "High-pass" in method:
            suffix = f"HP{self.spin_cutoff.value():.0f}Hz"
        elif "Band-pass" in method:
            suffix = f"BP{self.spin_low_cutoff.value():.0f}_{self.spin_high_cutoff.value():.0f}Hz"
        elif "Band-stop" in method:
            suffix = f"BS{self.spin_low_cutoff.value():.0f}_{self.spin_high_cutoff.value():.0f}Hz"
        elif "Notch" in method:
            suffix = f"Notch{self.spin_cutoff.value():.0f}Hz"
        elif "RMS" in method:
            suffix = f"RMS{self.spin_rms_window.value():.0f}ms"
        elif "Rectification" in method:
            suffix = "Rectified"
        elif "Linear Envelope" in method:
            suffix = f"Env_LP{self.spin_cutoff.value():.0f}Hz"
        else:
            suffix = "Filtered"

        self.txt_new_channel_name.setText(f"{ch}_{suffix}")

    def _compute_filtered_signal(self) -> Optional[np.ndarray]:
        ch = self.combo_filter_ch.currentData()
        if not ch or ch not in self.trial.analogs:
            return None

        raw = self.trial.analogs[ch]
        rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
        method = self.combo_filter_type.currentText()
        order = self.spin_order.value()

        try:
            if "Low-pass" in method:
                return apply_butterworth_filter(raw, rate, "lowpass", order, self.spin_cutoff.value())
            elif "High-pass" in method:
                return apply_butterworth_filter(raw, rate, "highpass", order, self.spin_cutoff.value())
            elif "Band-pass" in method:
                low = self.spin_low_cutoff.value()
                high = self.spin_high_cutoff.value()
                if low >= high:
                    return raw.copy()
                return apply_butterworth_filter(raw, rate, "bandpass", order, (low, high))
            elif "Band-stop" in method:
                low = self.spin_low_cutoff.value()
                high = self.spin_high_cutoff.value()
                if low >= high:
                    return raw.copy()
                return apply_butterworth_filter(raw, rate, "bandstop", order, (low, high))
            elif "Notch" in method:
                return apply_butterworth_filter(raw, rate, "notch", order, self.spin_cutoff.value())
            elif "RMS" in method:
                win_samples = max(1, int(self.spin_rms_window.value() * rate / 1000.0))
                return compute_moving_rms(raw, win_samples)
            elif "Rectification" in method:
                return np.abs(raw)
            elif "Linear Envelope" in method:
                rect = np.abs(raw)
                return apply_butterworth_filter(rect, rate, "lowpass", order, self.spin_cutoff.value())
        except Exception:
            return raw.copy()

        return raw.copy()

    def _update_filter_preview(self):
        ch = self.combo_filter_ch.currentData()
        if not ch or ch not in self.trial.analogs:
            self.preview_plot.clear()
            self.lbl_metrics.setText("No channel selected.")
            return

        raw = self.trial.analogs[ch]
        filtered = self._compute_filtered_signal()
        if filtered is None:
            return

        x = np.arange(len(raw))

        # Clear existing curves
        self.preview_plot.clear()

        # 1. Plot Raw Signal (dim cyan)
        self.preview_plot.plot(
            x, raw,
            pen=pg.mkPen(color=QColor(0, 173, 181, 100), width=1.2),
            name=f"Raw ({ch})"
        )

        # 2. Plot Filtered / Processed Signal (vibrant orange/yellow)
        self.preview_plot.plot(
            x, filtered,
            pen=pg.mkPen(color=QColor("#FFB703"), width=2.0),
            name="Processed"
        )

        # Update metrics readout
        s_raw = compute_signal_stats(raw)
        s_filt = compute_signal_stats(filtered)
        self.lbl_metrics.setText(
            f"Raw RMS: {s_raw['rms']:.3f} | Proc RMS: {s_filt['rms']:.3f} | "
            f"Raw P2P: {s_raw['p2p']:.3f} | Proc P2P: {s_filt['p2p']:.3f}"
        )

    def _apply_filter_to_trial(self):
        ch = self.combo_filter_ch.currentData()
        if not ch or ch not in self.trial.analogs:
            return

        filtered = self._compute_filtered_signal()
        if filtered is None:
            return

        if self.rb_save_new.isChecked():
            new_name = self.txt_new_channel_name.text().strip()
            if not new_name:
                _safe_warning(self, "Invalid Name", "Please enter a valid channel name.")
                return

            if new_name in self.trial.analogs:
                reply = _safe_question(
                    self, "Channel Exists",
                    f"A channel named '{new_name}' already exists. Overwrite it?",
                    default_yes=True
                )
                if reply != QMessageBox.Yes:
                    return

            cmd = AddAnalogChannelCommand(
                main_window=self.parent(),
                trial=self.trial,
                channel_name=new_name,
                data=filtered,
                unit=self.trial.analog_units.get(ch, "V"),
                analog_dialog=self
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

            self.analogsChanged.emit()
            _safe_info(self, "Filter Applied", f"Successfully saved processed signal as new channel '{new_name}'.")

        else:
            # Overwrite current channel
            reply = _safe_question(
                self, "Confirm Overwrite",
                f"Are you sure you want to overwrite channel '{ch}' with the filtered signal?",
                default_yes=True
            )
            if reply != QMessageBox.Yes:
                return

            old_data = self.trial.analogs[ch].copy()
            cmd = FilterAnalogChannelCommand(
                main_window=self.parent(),
                trial=self.trial,
                channel_name=ch,
                old_data=old_data,
                new_data=filtered,
                analog_dialog=self
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

            self.analogsChanged.emit()
            _safe_info(self, "Filter Applied", f"Channel '{ch}' successfully updated with filtered signal.")

"""
Interactive Analog Channels Manager & Signal Processing Tool.
Allows renaming, deleting, adding/importing analog channels (from TXT, CSV, TSV, XLSX),
and applying Butterworth filters (Lowpass, Highpass, Bandpass, Bandstop, Notch),
Full-Wave Rectification, Moving RMS Envelopes, and EMG Linear Envelopes with live preview.
"""

from typing import Dict, List, Optional, Tuple, Union, Any
import copy
import os
import csv
import numpy as np
from scipy import signal

from PySide6.QtCore import Qt, Signal, QPointF, QEvent, QLocale
from PySide6.QtGui import (
    QColor, QFont, QAction, QKeySequence, QUndoStack,
    QStandardItemModel, QStandardItem
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QAbstractSpinBox, QRadioButton, QButtonGroup, QGroupBox,
    QTabWidget, QSplitter, QHeaderView, QMessageBox, QFileDialog,
    QInputDialog, QWidget, QAbstractItemView, QFrame,
    QListWidget, QListWidgetItem, QCheckBox, QListView
)
import pyqtgraph as pg

from core.data_models import C3DTrial
from core.grw_calculator import extract_plate_analog_matrix, compute_single_plate_grw
from core.pipeline_executor import apply_emg_custom_filter
from gui.undo_commands import (
    FilterAnalogChannelCommand,
    AddAnalogChannelCommand,
    DeleteAnalogChannelsCommand,
    RenameAnalogChannelCommand,
    FilterMultipleAnalogChannelsCommand,
    AddMultipleAnalogChannelsCommand,
    UpdateAnalogSpecificationsCommand
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


class CheckableComboBox(QComboBox):
    """
    Multi-selection Dropdown Combobox.
    Appears as a clean, standard-height dropdown menu showing a summary of selected channels.
    When expanded, presents a comfortable popup list with checkboxes for each channel.
    Clicking items toggles their check state without prematurely dismissing the popup.
    """
    selectionChanged = Signal()

    def __init__(self, parent=None, placeholder: str = "Select channels..."):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setModel(QStandardItemModel(self))
        list_view = QListView(self)
        list_view.setStyleSheet("""
            QListView {
                background-color: #1A1D27;
                border: 1px solid #3B4252;
                outline: none;
                padding: 4px;
            }
            QListView::item {
                min-height: 26px;
                padding: 2px 8px;
                color: #ECEFF4;
            }
            QListView::item:hover {
                background-color: #2E3440;
                border-radius: 3px;
            }
            QListView::item:selected {
                background-color: #3B4252;
                border-radius: 3px;
            }
        """)
        self.setView(list_view)
        self.view().viewport().installEventFilter(self)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().installEventFilter(self)
        self.lineEdit().setCursor(Qt.PointingHandCursor)
        self.setMaxVisibleItems(15)
        self.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                min-height: 28px;
                font-size: 12px;
            }
        """)
        self._update_display_text()

    def showPopup(self):
        super().showPopup()
        if self.view():
            self.view().setMinimumWidth(max(self.width(), 260))

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.MouseButtonRelease:
                if self.view().isVisible():
                    self.hidePopup()
                else:
                    self.showPopup()
                return True
        elif obj == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            idx = self.view().indexAt(event.pos())
            if idx.isValid():
                item = self.model().itemFromIndex(idx)
                if item:
                    item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                    self._update_display_text()
                    self.selectionChanged.emit()
                    return True
        return super().eventFilter(obj, event)

    def add_checkable_item(self, text: str, data: Any = None, checked: bool = False):
        item = QStandardItem(text)
        item.setData(data if data is not None else text, Qt.UserRole)
        item.setCheckable(True)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.model().appendRow(item)
        self._update_display_text()

    def set_all_checked(self, checked: bool):
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it:
                it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._update_display_text()
        self.selectionChanged.emit()

    def set_matching_checked(self, predicate_fn):
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it:
                val = it.data(Qt.UserRole)
                it.setCheckState(Qt.Checked if predicate_fn(val) else Qt.Unchecked)
        self._update_display_text()
        self.selectionChanged.emit()

    def get_checked_data(self) -> List[Any]:
        res = []
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it and it.checkState() == Qt.Checked:
                res.append(it.data(Qt.UserRole))
        return res

    def get_checked_items(self) -> List[str]:
        res = []
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it and it.checkState() == Qt.Checked:
                res.append(it.text())
        return res

    def _update_display_text(self):
        checked = self.get_checked_data()
        total = self.model().rowCount()
        if not checked:
            txt = self._placeholder
        elif len(checked) == 1:
            txt = str(checked[0])
        elif len(checked) == total:
            txt = f"All Channels Selected ({total})"
        elif len(checked) <= 3:
            txt = ", ".join(str(c) for c in checked)
        else:
            names = ", ".join(str(c) for c in checked[:2])
            suffix = f", +{len(checked)-2} more"
            txt = f"{len(checked)} Channels: {names}{suffix}"
        self.lineEdit().setText(txt)
        self.lineEdit().setToolTip("\n".join(str(c) for c in checked) if checked else self._placeholder)

    def count(self) -> int:
        return self.model().rowCount()

    def clear(self):
        self.model().clear()
        self._update_display_text()


def _is_probable_emg_channel(name: str) -> bool:
    """Check if channel name indicates an EMG signal."""
    n = name.lower().replace("_", "").replace("-", "").strip()
    emg_keys = [
        "emg", "tib", "gast", "vast", "rec", "bic", "glut", "sol",
        "peron", "delt", "trap", "pect", "lat", "ham", "semi",
        "tensor", "grac", "add", "abd", "ta", "mg", "lg", "rf",
        "vl", "vm", "bf", "st", "gm"
    ]
    return any(k in n for k in emg_keys)


class EMGCustomFilterDialog(QDialog):
    """
    Two-step EMG Custom Processing Window:
    Step 1: Butterworth Band-Pass Filter (default: 20 – 400 Hz).
    Step 2: Full-Wave Rectification (|x|) & Butterworth Low-Pass Filter (default cutoff: 20 Hz, linear envelope).
    Allows multi-channel selection with quick 'Select All EMG' / 'Select All' / 'Clear' buttons,
    real-time multi-curve preview (Raw, Bandpass, Envelope), and pipeline recording for batch execution.
    """

    analogsChanged = Signal()

    def __init__(self, trial: C3DTrial, parent=None, undo_stack: Optional[QUndoStack] = None):
        super().__init__(parent)
        self.trial = trial
        if undo_stack is not None:
            self.undo_stack = undo_stack
        elif parent is not None and hasattr(parent, "undo_stack"):
            self.undo_stack = parent.undo_stack
        else:
            self.undo_stack = None

        self.setWindowTitle("EMG custom")
        self.resize(960, 640)
        self._setup_ui()
        self._populate_channels()
        self._update_preview()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        rate = getattr(self.trial, "analog_rate", 1000.0) if self.trial else 1000.0
        nyq = 0.5 * rate

        # Main Splitter: Left Controls | Right Live Preview Plot
        splitter = QSplitter(Qt.Horizontal, self)

        # ----------------- LEFT CONTROLS COLUMN -----------------
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(10)

        # 1. Channel Selector Group (Multi-Select Dropdown)
        grp_ch = QGroupBox("Target Analog / EMG Channels", left_widget)
        v_ch = QVBoxLayout(grp_ch)
        v_ch.setSpacing(6)

        # Multi-select Dropdown Combobox
        self.combo_channels = CheckableComboBox(grp_ch, placeholder="Select EMG channels...")
        self.combo_channels.selectionChanged.connect(self._on_emg_selection_changed)
        v_ch.addWidget(self.combo_channels)
        self.list_channels = self.combo_channels  # alias for backwards compatibility

        # Quick selection buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)
        self.btn_all_emg = QPushButton("Select All EMG", grp_ch)
        self.btn_all_emg.setToolTip("Select all detected EMG channels")
        self.btn_all_emg.clicked.connect(self._select_all_emg)
        self.btn_all = QPushButton("Select All", grp_ch)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_clear = QPushButton("Clear", grp_ch)
        self.btn_clear.clicked.connect(self._clear_selection)

        btn_box.addWidget(self.btn_all_emg)
        btn_box.addWidget(self.btn_all)
        btn_box.addWidget(self.btn_clear)
        v_ch.addLayout(btn_box)

        # Preview channel picker
        row_prev = QHBoxLayout()
        lbl_pv = QLabel("Preview:", grp_ch)
        lbl_pv.setStyleSheet("color: #ECEFF4; font-size: 11px;")
        self.combo_preview_ch = QComboBox(grp_ch)
        self.combo_preview_ch.currentIndexChanged.connect(self._update_preview)
        row_prev.addWidget(lbl_pv)
        row_prev.addWidget(self.combo_preview_ch)
        v_ch.addLayout(row_prev)

        left_layout.addWidget(grp_ch)

        # 2. Step 1: Band-Pass Filter
        grp_step1 = QGroupBox("Step 1: Band-Pass Filter", left_widget)
        form_step1 = QFormLayout(grp_step1)
        form_step1.setSpacing(6)

        lbl_s1_info = QLabel("Butterworth Zero-Phase Band-Pass Filter")
        lbl_s1_info.setStyleSheet("color: #8C96AB; font-size: 11px;")
        form_step1.addRow(lbl_s1_info)

        self.spin_bp_low = QDoubleSpinBox(grp_step1)
        self.spin_bp_low.setRange(0.1, max(1.0, nyq - 1.0))
        self.spin_bp_low.setValue(20.0)
        self.spin_bp_low.setDecimals(1)
        self.spin_bp_low.setSuffix(" Hz")
        self.spin_bp_low.valueChanged.connect(self._update_preview)
        form_step1.addRow("Low Cutoff:", self.spin_bp_low)

        self.spin_bp_high = QDoubleSpinBox(grp_step1)
        self.spin_bp_high.setRange(1.0, max(2.0, nyq - 0.1))
        self.spin_bp_high.setValue(min(400.0, nyq - 1.0))
        self.spin_bp_high.setDecimals(1)
        self.spin_bp_high.setSuffix(" Hz")
        self.spin_bp_high.valueChanged.connect(self._update_preview)
        form_step1.addRow("High Cutoff:", self.spin_bp_high)

        self.spin_bp_order = QSpinBox(grp_step1)
        self.spin_bp_order.setRange(1, 10)
        self.spin_bp_order.setValue(4)
        self.spin_bp_order.valueChanged.connect(self._update_preview)
        form_step1.addRow("Filter Order:", self.spin_bp_order)

        left_layout.addWidget(grp_step1)

        # 3. Step 2: Full-Wave Rectification & Low-Pass Filter
        grp_step2 = QGroupBox("Step 2: Full-Wave Rectification & Low-Pass Filter", left_widget)
        form_step2 = QFormLayout(grp_step2)
        form_step2.setSpacing(6)

        lbl_s2_info = QLabel("Full-Wave Rectification |x| + Butterworth Low-Pass Filter")
        lbl_s2_info.setStyleSheet("color: #8C96AB; font-size: 11px;")
        form_step2.addRow(lbl_s2_info)

        self.spin_lp_cutoff = QDoubleSpinBox(grp_step2)
        self.spin_lp_cutoff.setRange(0.1, max(1.0, nyq - 1.0))
        self.spin_lp_cutoff.setValue(20.0)
        self.spin_lp_cutoff.setDecimals(1)
        self.spin_lp_cutoff.setSuffix(" Hz")
        self.spin_lp_cutoff.valueChanged.connect(self._update_preview)
        form_step2.addRow("Low-Pass Cutoff:", self.spin_lp_cutoff)

        self.spin_lp_order = QSpinBox(grp_step2)
        self.spin_lp_order.setRange(1, 10)
        self.spin_lp_order.setValue(4)
        self.spin_lp_order.valueChanged.connect(self._update_preview)
        form_step2.addRow("Filter Order:", self.spin_lp_order)

        left_layout.addWidget(grp_step2)

        # 4. Output Mode
        grp_out = QGroupBox("Output Mode", left_widget)
        v_out = QVBoxLayout(grp_out)
        v_out.setSpacing(6)

        self.rb_overwrite = QRadioButton("Overwrite Selected Channels", grp_out)
        self.rb_overwrite.setChecked(True)
        self.rb_new = QRadioButton("Save as New Channels (suffix: _EMG_env)", grp_out)

        v_out.addWidget(self.rb_overwrite)
        v_out.addWidget(self.rb_new)
        left_layout.addWidget(grp_out)

        # Bottom Buttons
        btn_act_row = QHBoxLayout()
        btn_act_row.setSpacing(8)

        btn_cancel = QPushButton("Cancel", left_widget)
        btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton("Apply EMG Custom Filter", left_widget)
        self.btn_apply.setObjectName("primaryBtn")
        self.btn_apply.setStyleSheet("""
            QPushButton#primaryBtn {
                background-color: #00ADB5;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 16px;
                border-radius: 4px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #00C4CC;
            }
        """)
        self.btn_apply.clicked.connect(self._do_apply)

        btn_act_row.addStretch()
        btn_act_row.addWidget(btn_cancel)
        btn_act_row.addWidget(self.btn_apply)
        left_layout.addLayout(btn_act_row)

        splitter.addWidget(left_widget)

        # ----------------- RIGHT PREVIEW PLOT COLUMN -----------------
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(6)

        # Header readout
        prev_head = QHBoxLayout()
        lbl_p_title = QLabel("<b>Interactive Signal Preview</b>", right_widget)
        lbl_p_title.setStyleSheet("font-size: 13px; color: #ECEFF4;")
        self.lbl_metrics = QLabel("Raw RMS: --- | BP RMS: --- | Env Peak: ---", right_widget)
        self.lbl_metrics.setStyleSheet("font-size: 11px; color: #00ADB5; font-weight: 600;")
        prev_head.addWidget(lbl_p_title)
        prev_head.addStretch()
        prev_head.addWidget(self.lbl_metrics)
        right_layout.addLayout(prev_head)

        # Plot Widget
        self.preview_plot = pg.PlotWidget(right_widget)
        self.preview_plot.setBackground("#151720")
        self.preview_plot.showGrid(x=True, y=True, alpha=0.25)
        self.preview_plot.setLabel("bottom", "Samples", units="")
        self.preview_plot.setLabel("left", "Amplitude")
        self.preview_plot.setContextMenuPolicy(Qt.NoContextMenu)

        # Suppress context menus
        _pi = self.preview_plot.getPlotItem()
        _pi.setMenuEnabled(False)
        _pi.ctrlMenu = None
        _vb = _pi.getViewBox()
        _vb.setMenuEnabled(False)
        _vb.menu = None
        _vb.raiseContextMenu = lambda ev: None

        self.preview_legend = self.preview_plot.addLegend(offset=(-10, 10))
        right_layout.addWidget(self.preview_plot)

        splitter.addWidget(right_widget)
        splitter.setSizes([400, 560])
        main_layout.addWidget(splitter, stretch=1)

    def _populate_channels(self):
        self.combo_channels.blockSignals(True)
        self.combo_preview_ch.blockSignals(True)
        self.combo_channels.clear()
        self.combo_preview_ch.clear()

        channels = sorted(list(self.trial.analogs.keys())) if (self.trial and self.trial.analogs) else []
        emg_found = False

        for ch in channels:
            unit = self.trial.analog_units.get(ch, "V")
            is_emg = _is_probable_emg_channel(ch)
            if is_emg:
                emg_found = True
            self.combo_channels.add_checkable_item(f"{ch} ({unit})", ch, checked=is_emg)
            self.combo_preview_ch.addItem(f"{ch} ({unit})", ch)

        # If no EMG channels detected automatically, check the first channel
        if not emg_found and self.combo_channels.count() > 0:
            it = self.combo_channels.model().item(0)
            if it:
                it.setCheckState(Qt.Checked)
            self.combo_channels._update_display_text()

        self.combo_channels.blockSignals(False)
        self.combo_preview_ch.blockSignals(False)
        self._sync_preview_selection()

    def _sync_preview_selection(self):
        checked = self.get_selected_channels()
        if checked:
            idx = self.combo_preview_ch.findData(checked[0])
            if idx >= 0:
                self.combo_preview_ch.setCurrentIndex(idx)

    def _on_emg_selection_changed(self):
        self._sync_preview_selection()
        self._update_preview()

    def _select_all_emg(self):
        self.combo_channels.set_matching_checked(_is_probable_emg_channel)
        self._sync_preview_selection()

    def _select_all(self):
        self.combo_channels.set_all_checked(True)
        self._sync_preview_selection()

    def _clear_selection(self):
        self.combo_channels.set_all_checked(False)

    def get_selected_channels(self) -> List[str]:
        return self.combo_channels.get_checked_data()

    def _update_preview(self):
        ch = self.combo_preview_ch.currentData()
        if not ch or not self.trial or ch not in self.trial.analogs:
            self.preview_plot.clear()
            self.lbl_metrics.setText("No channel selected.")
            return

        raw = self.trial.analogs[ch]
        rate = float(self.trial.analog_rate) if self.trial.analog_rate > 0 else 1000.0

        bp_low = self.spin_bp_low.value()
        bp_high = self.spin_bp_high.value()
        bp_order = self.spin_bp_order.value()
        lp_cutoff = self.spin_lp_cutoff.value()
        lp_order = self.spin_lp_order.value()

        if bp_low >= bp_high:
            self.lbl_metrics.setText("Warning: Bandpass Low Cutoff must be < High Cutoff.")
            return

        try:
            # Step 1: Band-Pass
            step1_bp = apply_butterworth_filter(raw, rate, "bandpass", bp_order, (bp_low, bp_high))
            # Step 2: Rectification & Low-Pass Linear Envelope
            rect = np.abs(step1_bp)
            step2_env = apply_butterworth_filter(rect, rate, "lowpass", lp_order, lp_cutoff)
        except Exception as e:
            self.lbl_metrics.setText(f"Filter error: {e}")
            return

        x = np.arange(len(raw))
        self.preview_plot.clear()

        # 1. Raw Signal (dim cyan)
        self.preview_plot.plot(
            x, raw,
            pen=pg.mkPen(color=QColor(0, 173, 181, 90), width=1.0),
            name=f"Raw ({ch})"
        )

        # 2. Step 1: Band-Pass (amber / yellow)
        self.preview_plot.plot(
            x, step1_bp,
            pen=pg.mkPen(color=QColor("#FFB703"), width=1.5),
            name=f"Step 1: Band-Pass ({bp_low:.0f}-{bp_high:.0f} Hz)"
        )

        # 3. Step 2: Linear Envelope (bright neon green / teal)
        self.preview_plot.plot(
            x, step2_env,
            pen=pg.mkPen(color=QColor("#06D6A0"), width=2.5),
            name=f"Step 2: Rectified + LP ({lp_cutoff:.0f} Hz Envelope)"
        )

        # Update metrics readout
        s_raw = compute_signal_stats(raw)
        s_bp = compute_signal_stats(step1_bp)
        s_env = compute_signal_stats(step2_env)
        self.lbl_metrics.setText(
            f"Raw RMS: {s_raw['rms']:.3f} | BP RMS: {s_bp['rms']:.3f} | "
            f"Env Peak: {s_env['max']:.3f} | Env Mean: {s_env['mean']:.3f}"
        )

    def _do_apply(self):
        channels = self.get_selected_channels()
        if not channels:
            _safe_warning(self, "No Channels Selected", "Please select one or more analog channels to filter.")
            return

        rate = float(self.trial.analog_rate) if self.trial.analog_rate > 0 else 1000.0
        bp_low = self.spin_bp_low.value()
        bp_high = self.spin_bp_high.value()
        bp_order = self.spin_bp_order.value()
        lp_cutoff = self.spin_lp_cutoff.value()
        lp_order = self.spin_lp_order.value()
        overwrite = self.rb_overwrite.isChecked()

        if bp_low >= bp_high:
            _safe_warning(self, "Invalid Cutoffs", "Band-pass Low Cutoff must be less than High Cutoff.")
            return

        old_dict = {}
        new_dict = {}
        unit_dict = {}

        for ch in channels:
            if ch not in self.trial.analogs:
                continue
            raw = self.trial.analogs[ch]
            filt = apply_emg_custom_filter(raw, rate, bp_low, bp_high, lp_cutoff, bp_order, lp_order)
            if overwrite:
                old_dict[ch] = raw.copy()
                new_dict[ch] = filt
            else:
                out_name = f"{ch}_EMG_env"
                new_dict[out_name] = filt
                unit_dict[out_name] = self.trial.analog_units.get(ch, "V")

        parent_mw = self.parent()
        while parent_mw and not hasattr(parent_mw, "pipeline_manager") and hasattr(parent_mw, "parent"):
            parent_mw = parent_mw.parent()

        if overwrite:
            cmd = FilterMultipleAnalogChannelsCommand(
                main_window=parent_mw,
                trial=self.trial,
                old_data_dict=old_dict,
                new_data_dict=new_dict,
                analog_dialog=self.parent(),
                description=f"EMG Custom Filter on {len(channels)} channels",
                method="EMG custom",
                details={
                    "Action": "EMGCustomFilter",
                    "Channels": channels,
                    "BandpassLow_Hz": bp_low,
                    "BandpassHigh_Hz": bp_high,
                    "LowpassCutoff_Hz": lp_cutoff,
                    "Order": bp_order,
                    "Overwrite": True
                }
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()
        else:
            cmd = AddMultipleAnalogChannelsCommand(
                main_window=parent_mw,
                trial=self.trial,
                channel_dict=new_dict,
                unit_dict=unit_dict,
                analog_dialog=self.parent(),
                description=f"Add EMG Linear Envelopes for {len(channels)} channels"
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

        # Record to pipeline manager for batch processing
        if parent_mw and hasattr(parent_mw, "pipeline_manager") and parent_mw.pipeline_manager:
            parent_mw.pipeline_manager.record_emg_custom_filter(
                channels=channels,
                bp_low=bp_low,
                bp_high=bp_high,
                lp_cutoff=lp_cutoff,
                order=bp_order,
                overwrite=overwrite
            )

        self.analogsChanged.emit()
        if hasattr(self.parent(), "analogsChanged"):
            self.parent().analogsChanged.emit()

        action_desc = "Overwrote" if overwrite else "Created new envelope channels for"
        _safe_info(
            self,
            "EMG Custom Filter Applied",
            f"Successfully applied 2-step EMG filter (BP {bp_low:.0f}-{bp_high:.0f} Hz, LP {lp_cutoff:.0f} Hz)!\n"
            f"{action_desc} {len(channels)} channel(s)."
        )
        self.accept()


class NumericLineEdit(QLineEdit):
    """
    Direct QLineEdit numeric input with clean high-contrast styling and no buttons.
    Fully compatible with QDoubleSpinBox API (value, setValue, valueChanged, setRange, setDecimals).
    """
    valueChanged = Signal(float)

    def __init__(self, parent=None, default_val: float = 0.0, decimals: int = 1):
        super().__init__(parent)
        self._min_val: float = -1e9
        self._max_val: float = 1e9
        self._decimals: int = max(0, int(decimals))
        self._value: float = float(default_val)
        self._formatting: bool = False
        self.setAlignment(Qt.AlignLeft)
        self._update_display_text()
        self.textEdited.connect(self._on_text_edited)
        self.editingFinished.connect(self._on_editing_finished)

    def setButtonSymbols(self, _symbols):
        pass

    def setSingleStep(self, _step):
        pass

    def setSuffix(self, _suffix: str):
        pass

    def setLocale(self, _loc):
        pass

    def setRange(self, minimum: float, maximum: float):
        self._min_val = float(minimum)
        self._max_val = float(maximum)
        self._value = float(np.clip(self._value, self._min_val, self._max_val))
        self._update_display_text()

    def setDecimals(self, decimals: int):
        self._decimals = max(0, int(decimals))
        self._update_display_text()

    def decimals(self) -> int:
        return self._decimals

    def buttonSymbols(self):
        return QAbstractSpinBox.NoButtons

    def value(self) -> float:
        txt = self.text().strip().replace(",", ".")
        try:
            v = float(txt)
            return float(np.clip(v, self._min_val, self._max_val))
        except ValueError:
            return self._value

    def setValue(self, val: float):
        try:
            clamped = float(np.clip(float(val), self._min_val, self._max_val))
        except (ValueError, TypeError):
            clamped = 0.0
        changed = abs(clamped - self._value) > 1e-9
        self._value = clamped
        self._update_display_text()
        if changed:
            self.valueChanged.emit(self._value)

    def _update_display_text(self):
        self._formatting = True
        try:
            self.setText(f"{self._value:.{self._decimals}f}")
        finally:
            self._formatting = False

    def _on_text_edited(self, txt: str):
        if self._formatting:
            return
        clean = txt.strip().replace(",", ".")
        try:
            v = float(clean)
            self._value = float(np.clip(v, self._min_val, self._max_val))
            self.valueChanged.emit(self._value)
        except ValueError:
            pass

    def _on_editing_finished(self):
        self._value = self.value()
        self._update_display_text()
        self.valueChanged.emit(self._value)


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

        # Tabs: 1. Channels Manager | 2. Filter & Signal Processing | 3. Info / Specifications
        self.tabs = QTabWidget()
        self.tab_manager = QWidget()
        self.tab_filter = QWidget()
        self.tab_info = QWidget()

        self._setup_manager_tab()
        self._setup_filter_tab()
        self._setup_info_tab()

        self.tabs.addTab(self.tab_manager, "Channels Manager")
        self.tabs.addTab(self.tab_filter, "Filter")
        self.tabs.addTab(self.tab_info, "Info")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

        # Bottom Bar: Small subtle info on the left, Close button on the right
        bottom_box = QHBoxLayout()
        bottom_box.setContentsMargins(4, 4, 4, 0)
        bottom_box.setSpacing(8)

        self.lbl_footer_info = QLabel()
        self.lbl_footer_info.setStyleSheet("color: #8F9BB3; font-size: 11px; background: transparent; border: none;")
        self.lbl_header_channels = self.lbl_footer_info  # alias for backwards compatibility
        self._update_footer_info()

        bottom_box.addWidget(self.lbl_footer_info)
        bottom_box.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)

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
            src_file = dlg.txt_path.text().strip() if hasattr(dlg, 'txt_path') else ""
            cmd = AddAnalogChannelCommand(
                main_window=self.parent(),
                trial=self.trial,
                channel_name=name,
                data=dlg.imported_data,
                unit=dlg.channel_unit,
                analog_dialog=self,
                source_type="file",
                source_file=src_file
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

            mw = self.parent()
            if mw and hasattr(mw, 'pipeline_manager') and mw.pipeline_manager:
                rate = getattr(self.trial, "analog_rate", 1000.0) if self.trial else 1000.0
                mw.pipeline_manager.record_add_analog_channel(
                    name=name,
                    unit=dlg.channel_unit,
                    sampling_rate=rate,
                    source_type="file",
                    source_file=src_file,
                    frame_count=len(dlg.imported_data)
                )

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

        # 1. Channel Selector (Multi-Select Dropdown Menu)
        grp_channel = QGroupBox("Target Channels")
        v_ch = QVBoxLayout(grp_channel)
        v_ch.setSpacing(6)

        # Multi-select Dropdown Combobox
        self.combo_filter_channels = CheckableComboBox(self, placeholder="Select channels to filter...")
        self.combo_filter_channels.selectionChanged.connect(self._on_filter_selection_changed)
        v_ch.addWidget(self.combo_filter_channels)
        self.list_filter_channels = self.combo_filter_channels  # alias for backwards compatibility

        # Quick selection buttons row
        btn_filt_box = QHBoxLayout()
        btn_filt_box.setSpacing(6)
        self.btn_filt_all_emg = QPushButton("All EMG")
        self.btn_filt_all_emg.setToolTip("Select all detected EMG channels")
        self.btn_filt_all_emg.clicked.connect(self._select_all_emg_filter)
        self.btn_filt_all = QPushButton("Select All")
        self.btn_filt_all.clicked.connect(self._select_all_filter)
        self.btn_filt_clear = QPushButton("Clear")
        self.btn_filt_clear.clicked.connect(self._clear_selection_filter)

        btn_filt_box.addWidget(self.btn_filt_all_emg)
        btn_filt_box.addWidget(self.btn_filt_all)
        btn_filt_box.addWidget(self.btn_filt_clear)
        v_ch.addLayout(btn_filt_box)

        # Live Preview Channel Picker
        row_preview_pick = QHBoxLayout()
        lbl_pv = QLabel("Preview:")
        lbl_pv.setStyleSheet("color: #ECEFF4; font-size: 11px;")
        self.combo_filter_ch = QComboBox()
        self.combo_filter_ch.currentIndexChanged.connect(self._update_filter_preview)
        row_preview_pick.addWidget(lbl_pv)
        row_preview_pick.addWidget(self.combo_filter_ch)
        v_ch.addLayout(row_preview_pick)

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
            "EMG Linear Envelope (Rectify + Low-pass)",
            "EMG custom"
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

    def open_emg_custom_dialog(self):
        """Open the dedicated 2-step EMG Custom Processing window."""
        dlg = EMGCustomFilterDialog(self.trial, parent=self, undo_stack=self.undo_stack)
        if dlg.exec() == QDialog.Accepted:
            self._populate_channel_table()
            self._populate_filter_channels()
            self._update_footer_info()
            self.analogsChanged.emit()

    def _select_all_emg_filter(self):
        self.combo_filter_channels.set_matching_checked(_is_probable_emg_channel)
        self._sync_filter_preview_selection()

    def _select_all_filter(self):
        self.combo_filter_channels.set_all_checked(True)
        self._sync_filter_preview_selection()

    def _clear_selection_filter(self):
        self.combo_filter_channels.set_all_checked(False)

    def _sync_filter_preview_selection(self):
        checked = self.get_selected_filter_channels()
        if checked:
            idx = self.combo_filter_ch.findData(checked[0])
            if idx >= 0:
                self.combo_filter_ch.setCurrentIndex(idx)

    def _on_filter_selection_changed(self):
        self._sync_filter_preview_selection()
        self._update_filter_preview()

    def get_selected_filter_channels(self) -> List[str]:
        return self.combo_filter_channels.get_checked_data()

    def _populate_filter_channels(self, select_name: Optional[str] = None):
        self.combo_filter_ch.blockSignals(True)
        self.combo_filter_channels.blockSignals(True)
        self.combo_filter_ch.clear()
        self.combo_filter_channels.clear()

        channels = sorted(list(self.trial.analogs.keys())) if (self.trial and self.trial.analogs) else []
        for ch in channels:
            u = self.trial.analog_units.get(ch, "V")
            self.combo_filter_ch.addItem(f"{ch} ({u})", ch)
            checked = bool(select_name and ch == select_name)
            self.combo_filter_channels.add_checkable_item(f"{ch} ({u})", ch, checked=checked)

        if select_name and select_name in channels:
            idx = channels.index(select_name)
            self.combo_filter_ch.setCurrentIndex(idx)
        elif self.combo_filter_ch.count() > 0:
            self.combo_filter_ch.setCurrentIndex(0)

        # Default check active item if none checked
        if not self.get_selected_filter_channels() and self.combo_filter_channels.count() > 0:
            idx = max(0, self.combo_filter_ch.currentIndex())
            it = self.combo_filter_channels.model().item(idx)
            if it:
                it.setCheckState(Qt.Checked)
            self.combo_filter_channels._update_display_text()

        self.combo_filter_ch.blockSignals(False)
        self.combo_filter_channels.blockSignals(False)
        self._on_filter_type_changed()

    def set_active_tab(self, index: int):
        """Programmatically switch active tab (0: Manager, 1: Filter, 2: Info)."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int):
        if index == 1:
            # Switched to Filter tab -> refresh channels and preview
            sel = self._get_selected_channel()
            self._populate_filter_channels(sel)
        elif index == 2:
            # Switched to Info / Specifications tab -> refresh specs
            self._populate_info_tab()

    def _on_filter_type_changed(self):
        method = self.combo_filter_type.currentText()
        if method == "EMG custom":
            # Revert to Butterworth Low-pass or previous after opening
            self.open_emg_custom_dialog()
            self.combo_filter_type.blockSignals(True)
            self.combo_filter_type.setCurrentIndex(0)
            self.combo_filter_type.blockSignals(False)
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

    def _get_filter_suffix(self) -> str:
        method = self.combo_filter_type.currentText()
        if "Low-pass" in method:
            return f"LP{self.spin_cutoff.value():.0f}Hz"
        elif "High-pass" in method:
            return f"HP{self.spin_cutoff.value():.0f}Hz"
        elif "Band-pass" in method:
            return f"BP{self.spin_low_cutoff.value():.0f}_{self.spin_high_cutoff.value():.0f}Hz"
        elif "Band-stop" in method:
            return f"BS{self.spin_low_cutoff.value():.0f}_{self.spin_high_cutoff.value():.0f}Hz"
        elif "Notch" in method:
            return f"Notch{self.spin_cutoff.value():.0f}Hz"
        elif "RMS" in method:
            return f"RMS{self.spin_rms_window.value():.0f}ms"
        elif "Rectification" in method:
            return "Rectified"
        elif "Linear Envelope" in method:
            return f"Env_LP{self.spin_cutoff.value():.0f}Hz"
        return "Filtered"

    def _suggest_output_name(self):
        ch = self.combo_filter_ch.currentData()
        if not ch:
            return
        suffix = self._get_filter_suffix()
        self.txt_new_channel_name.setText(f"{ch}_{suffix}")

    def _compute_channel_filter(self, raw: np.ndarray, method: str, order: int, cutoff: Any, rate: float) -> np.ndarray:
        try:
            if "Low-pass" in method:
                return apply_butterworth_filter(raw, rate, "lowpass", order, cutoff)
            elif "High-pass" in method:
                return apply_butterworth_filter(raw, rate, "highpass", order, cutoff)
            elif "Band-pass" in method:
                return apply_butterworth_filter(raw, rate, "bandpass", order, cutoff)
            elif "Band-stop" in method:
                return apply_butterworth_filter(raw, rate, "bandstop", order, cutoff)
            elif "Notch" in method:
                return apply_butterworth_filter(raw, rate, "notch", order, cutoff)
            elif "RMS" in method:
                win_samples = max(1, int(self.spin_rms_window.value() * rate / 1000.0))
                return compute_moving_rms(raw, win_samples)
            elif "Rectification" in method:
                return np.abs(raw)
            elif "Linear Envelope" in method:
                rect = np.abs(raw)
                return apply_butterworth_filter(rect, rate, "lowpass", order, cutoff)
        except Exception:
            return raw.copy()
        return raw.copy()

    def _compute_filtered_signal(self) -> Optional[np.ndarray]:
        ch = self.combo_filter_ch.currentData()
        if not ch or ch not in self.trial.analogs:
            return None

        raw = self.trial.analogs[ch]
        rate = self.trial.analog_rate if self.trial.analog_rate > 0 else 1000.0
        method = self.combo_filter_type.currentText()
        order = self.spin_order.value()
        if "Band" in method:
            cutoff = (self.spin_low_cutoff.value(), self.spin_high_cutoff.value())
            if cutoff[0] >= cutoff[1]:
                return raw.copy()
        else:
            cutoff = self.spin_cutoff.value()

        return self._compute_channel_filter(raw, method, order, cutoff, rate)

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
        method = self.combo_filter_type.currentText()
        if method == "EMG custom":
            self.open_emg_custom_dialog()
            return

        selected_channels = self.get_selected_filter_channels()
        if not selected_channels:
            active = self.combo_filter_ch.currentData()
            if active and active in self.trial.analogs:
                selected_channels = [active]
            else:
                _safe_warning(self, "No Channels Selected", "Please select one or more analog channels to filter.")
                return

        rate = getattr(self.trial, "analog_rate", 1000.0) if self.trial else 1000.0
        order = self.spin_order.value()
        if "Band" in method:
            cutoff = (self.spin_low_cutoff.value(), self.spin_high_cutoff.value())
            if cutoff[0] >= cutoff[1]:
                _safe_warning(self, "Invalid Cutoffs", "Low cutoff must be less than high cutoff.")
                return
        else:
            cutoff = self.spin_cutoff.value()

        # Compute filtered signals for each channel
        old_dict = {}
        new_dict = {}
        unit_dict = {}

        for ch in selected_channels:
            if ch not in self.trial.analogs:
                continue
            raw = self.trial.analogs[ch]
            filt = self._compute_channel_filter(raw, method, order, cutoff, rate)
            if self.rb_save_new.isChecked():
                if len(selected_channels) == 1:
                    new_n = self.txt_new_channel_name.text().strip() or f"{ch}_Filtered"
                else:
                    suffix = self._get_filter_suffix()
                    new_n = f"{ch}_{suffix}"
                new_dict[new_n] = filt
                unit_dict[new_n] = self.trial.analog_units.get(ch, "V")
            else:
                old_dict[ch] = raw.copy()
                new_dict[ch] = filt

        parent_mw = self.parent()
        while parent_mw and not hasattr(parent_mw, "pipeline_manager") and hasattr(parent_mw, "parent"):
            parent_mw = parent_mw.parent()

        if self.rb_save_new.isChecked():
            if not new_dict:
                return

            # Check if any new channel already exists
            existing = [k for k in new_dict.keys() if k in self.trial.analogs]
            if existing:
                reply = _safe_question(
                    self, "Channel Exists",
                    f"The following channel(s) already exist: {', '.join(existing)}.\nOverwrite them?",
                    default_yes=True
                )
                if reply != QMessageBox.Yes:
                    return

            cmd = AddMultipleAnalogChannelsCommand(
                main_window=parent_mw,
                trial=self.trial,
                channel_dict=new_dict,
                unit_dict=unit_dict,
                analog_dialog=self,
                description=f"Add {len(new_dict)} Filtered Analog Channels"
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

            if parent_mw and hasattr(parent_mw, "pipeline_manager") and parent_mw.pipeline_manager:
                for new_n in new_dict.keys():
                    parent_mw.pipeline_manager.record_add_analog_channel(
                        name=new_n,
                        unit=unit_dict.get(new_n, "V"),
                        sampling_rate=rate,
                        source_type="filtered",
                        frame_count=len(new_dict[new_n])
                    )

            self.analogsChanged.emit()
            _safe_info(self, "Filter Applied", f"Successfully created {len(new_dict)} filtered channel(s).")

        else:
            # Overwrite current channel(s)
            reply = _safe_question(
                self, "Confirm Overwrite",
                f"Are you sure you want to overwrite {len(selected_channels)} analog channel(s) with the filtered signal?",
                default_yes=True
            )
            if reply != QMessageBox.Yes:
                return

            cmd = FilterMultipleAnalogChannelsCommand(
                main_window=parent_mw,
                trial=self.trial,
                old_data_dict=old_dict,
                new_data_dict=new_dict,
                analog_dialog=self,
                description=f"Filter {len(selected_channels)} Analog Channels ({method})",
                method=method,
                details={
                    "Order": order,
                    "Cutoff": cutoff,
                    "SamplingRate_Hz": rate
                }
            )
            if self.undo_stack:
                self.undo_stack.push(cmd)
            else:
                cmd.redo()

            if parent_mw and hasattr(parent_mw, "pipeline_manager") and parent_mw.pipeline_manager:
                for ch in selected_channels:
                    parent_mw.pipeline_manager.record_filter_analog_channel(
                        channel_name=ch,
                        filter_method=method,
                        order=order,
                        cutoff=cutoff,
                        sampling_rate=rate
                    )

            self.analogsChanged.emit()
            _safe_info(self, "Filter Applied", f"Successfully updated {len(selected_channels)} channel(s) with filtered signal.")

    # ---------------------------------------------------------
    # TAB 3: Analog Info / Configuration
    # ---------------------------------------------------------
    def _setup_info_tab(self):
        tab_layout = QVBoxLayout(self.tab_info)
        tab_layout.setContentsMargins(18, 18, 18, 18)
        tab_layout.setSpacing(14)

        grid_params = QGridLayout()
        grid_params.setContentsMargins(0, 0, 0, 0)
        grid_params.setSpacing(12)
        grid_params.setColumnStretch(2, 1)

        # 1. SCALE Multiplier
        grid_params.addWidget(QLabel("<b>SCALE:</b>"), 0, 0)
        self.spin_scale = NumericLineEdit(default_val=1.0, decimals=1)
        self.spin_scale.setRange(-1e9, 1e9)
        self.spin_scale.setFixedWidth(90)
        grid_params.addWidget(self.spin_scale, 0, 1)

        lbl_scale_hint = QLabel("Per-channel calibration factor (e.g. invert sign to reverse all analog signals)")
        lbl_scale_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_scale_hint, 0, 2)

        # 2. GEN_SCALE Multiplier
        grid_params.addWidget(QLabel("<b>GEN_SCALE:</b>"), 1, 0)
        self.spin_gen_scale = NumericLineEdit(default_val=1.0, decimals=1)
        self.spin_gen_scale.setRange(-1e9, 1e9)
        self.spin_gen_scale.setFixedWidth(90)
        grid_params.addWidget(self.spin_gen_scale, 1, 1)

        lbl_gen_hint = QLabel("Global analog scale multiplier applied across all channels")
        lbl_gen_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_gen_hint, 1, 2)

        # 3. OFFSET Value
        grid_params.addWidget(QLabel("<b>OFFSET:</b>"), 2, 0)
        self.spin_offset = NumericLineEdit(default_val=0.0, decimals=1)
        self.spin_offset.setRange(-1e9, 1e9)
        self.spin_offset.setFixedWidth(90)
        grid_params.addWidget(self.spin_offset, 2, 1)

        lbl_off_hint = QLabel("Raw ADC baseline offset subtracted before scaling")
        lbl_off_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_off_hint, 2, 2)

        # 4. Sampling Rate (Hz)
        grid_params.addWidget(QLabel("<b>Sampling Rate (Hz):</b>"), 3, 0)
        self.spin_rate = NumericLineEdit(default_val=1000.0, decimals=1)
        self.spin_rate.setRange(1.0, 100000.0)
        self.spin_rate.setFixedWidth(90)
        grid_params.addWidget(self.spin_rate, 3, 1)

        lbl_rate_hint = QLabel("Analog sampling frequency (Hz)")
        lbl_rate_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_rate_hint, 3, 2)

        # 5. Engineering Units
        grid_params.addWidget(QLabel("<b>Units:</b>"), 4, 0)
        self.txt_units = QLineEdit("V")
        self.txt_units.setFixedWidth(90)
        grid_params.addWidget(self.txt_units, 4, 1)

        lbl_unit_hint = QLabel("Default physical engineering unit (e.g. V, mV, N)")
        lbl_unit_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_unit_hint, 4, 2)

        # 6. Combined Scale Readout
        grid_params.addWidget(QLabel("<b>Combined Scale:</b>"), 5, 0)
        self.lbl_combined_scale = QLabel("1.0")
        self.lbl_combined_scale.setStyleSheet("color: #00ADB5; font-weight: bold; font-size: 13px;")
        grid_params.addWidget(self.lbl_combined_scale, 5, 1)

        lbl_comb_hint = QLabel("Effective multiplier: SCALE × GEN_SCALE")
        lbl_comb_hint.setStyleSheet("color: #8C96AB; font-size: 11px;")
        grid_params.addWidget(lbl_comb_hint, 5, 2)

        tab_layout.addLayout(grid_params)

        # Connect spinboxes to update combined scale readout dynamically
        self.spin_scale.valueChanged.connect(self._update_combined_scale_readout)
        self.spin_gen_scale.valueChanged.connect(self._update_combined_scale_readout)

        # Apply & Reset Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_reset_info = QPushButton("Reset to C3D Defaults")
        self.btn_reset_info.setToolTip("Reload original C3D parameter values from the file")
        self.btn_reset_info.clicked.connect(self._reset_info_to_defaults)
        btn_row.addWidget(self.btn_reset_info)

        btn_row.addStretch()

        self.btn_apply_info = QPushButton("Apply")
        self.btn_apply_info.setObjectName("primaryBtn")
        self.btn_apply_info.setStyleSheet("""
            QPushButton#primaryBtn {
                background-color: #00ADB5;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 18px;
                border-radius: 4px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #00C4CC;
            }
        """)
        self.btn_apply_info.clicked.connect(self._apply_info_changes)
        btn_row.addWidget(self.btn_apply_info)

        tab_layout.addLayout(btn_row)
        tab_layout.addStretch()

        # Immediately populate current values from the C3D trial
        self._populate_info_tab()

    def _update_combined_scale_readout(self):
        s = self.spin_scale.value()
        g = self.spin_gen_scale.value()
        self.lbl_combined_scale.setText(f"{s * g:.1f}")

    def _populate_info_tab(self):
        """Extract and display current C3D ANALOG parameters (SCALE, OFFSET, GEN_SCALE, UNITS, RATE)."""
        if not self.trial:
            return

        # Backup default parameters if not already stored
        if not hasattr(self.trial, "_c3d_default_analog_meta"):
            if self.trial.metadata and "ANALOG" in self.trial.metadata:
                self.trial._c3d_default_analog_meta = copy.deepcopy(self.trial.metadata["ANALOG"])

        analog_meta: Dict[str, Any] = {}
        if self.trial.metadata:
            for g_name, g_val in self.trial.metadata.items():
                if str(g_name).upper() == "ANALOG":
                    if isinstance(g_val, dict) and "parameters" in g_val:
                        analog_meta = g_val["parameters"]
                    elif isinstance(g_val, dict):
                        analog_meta = g_val
                    break

        if not analog_meta and getattr(self.trial, "btk_handle", None) is not None:
            try:
                c = self.trial.btk_handle
                params = c.get("parameters", {}) if isinstance(c, dict) else {}
                for g_name, g_dict in params.items():
                    if str(g_name).upper() == "ANALOG" and isinstance(g_dict, dict):
                        for p_name, p_val in g_dict.items():
                            if isinstance(p_val, dict) and "value" in p_val:
                                analog_meta[p_name] = {"values": p_val["value"]}
            except Exception:
                pass

        def get_param_values(key: str) -> Any:
            target = key.upper()
            for p_name, p_val in analog_meta.items():
                if str(p_name).upper() == target:
                    if isinstance(p_val, dict) and "values" in p_val:
                        return p_val["values"]
                    elif isinstance(p_val, dict) and "value" in p_val:
                        return p_val["value"]
                    return p_val
            return None

        # 1. GEN_SCALE
        gen_scale = 1.0
        gen_scale_val = get_param_values("GEN_SCALE")
        if gen_scale_val is not None:
            try:
                arr = np.atleast_1d(gen_scale_val)
                if len(arr) > 0:
                    gen_scale = float(arr[0])
            except Exception:
                gen_scale = 1.0

        # 2. SCALE
        scale_val = 1.0
        scales_raw = get_param_values("SCALE")
        if scales_raw is not None:
            try:
                arr = np.atleast_1d(scales_raw)
                if len(arr) > 0:
                    scale_val = float(arr[0])
            except Exception:
                scale_val = 1.0

        # 3. OFFSET
        offset_val = 0.0
        offsets_raw = get_param_values("OFFSET")
        if offsets_raw is not None:
            try:
                arr = np.atleast_1d(offsets_raw)
                if len(arr) > 0:
                    offset_val = float(arr[0])
            except Exception:
                offset_val = 0.0

        # 4. RATE
        rate_val = getattr(self.trial, "analog_rate", 0.0)
        if rate_val <= 0:
            rate_raw = get_param_values("RATE")
            if rate_raw is not None:
                try:
                    rate_val = float(np.atleast_1d(rate_raw)[0])
                except Exception:
                    rate_val = 1000.0
            else:
                rate_val = 1000.0

        # 5. UNITS
        unit_val = "V"
        units_raw = get_param_values("UNITS")
        if units_raw is not None:
            try:
                arr = np.atleast_1d(units_raw)
                if len(arr) > 0 and str(arr[0]).strip():
                    unit_val = str(arr[0]).strip()
            except Exception:
                pass
        if (unit_val == "V" or not unit_val) and self.trial.analog_units:
            for u in self.trial.analog_units.values():
                if u and str(u).strip():
                    unit_val = str(u).strip()
                    break

        # Update input fields
        self.spin_scale.blockSignals(True)
        self.spin_gen_scale.blockSignals(True)
        self.spin_offset.blockSignals(True)
        self.spin_rate.blockSignals(True)

        self.spin_scale.setValue(scale_val)
        self.spin_gen_scale.setValue(gen_scale)
        self.spin_offset.setValue(offset_val)
        self.spin_rate.setValue(rate_val if rate_val > 0 else 1000.0)
        self.txt_units.setText(unit_val)

        self.spin_scale.blockSignals(False)
        self.spin_gen_scale.blockSignals(False)
        self.spin_offset.blockSignals(False)
        self.spin_rate.blockSignals(False)

        self._update_combined_scale_readout()

    def _reset_info_to_defaults(self):
        """Restore default C3D parameters for the trial."""
        if hasattr(self.trial, "_c3d_default_analog_meta"):
            meta = self.trial._c3d_default_analog_meta
            if "ANALOG" in self.trial.metadata:
                self.trial.metadata["ANALOG"] = copy.deepcopy(meta)
        self._populate_info_tab()

    def _apply_info_changes(self):
        """Apply modified analog specifications across all channels with full undo/redo."""
        if not self.trial or not self.trial.analogs:
            _safe_warning(self, "No Analogs", "No analog channels are present in this trial.")
            return

        new_scale = float(self.spin_scale.value())
        new_gen_scale = float(self.spin_gen_scale.value())
        new_offset = float(self.spin_offset.value())
        new_rate = float(self.spin_rate.value())
        new_unit = self.txt_units.text().strip() or "V"

        # Calculate previous parameters
        analog_meta: Dict[str, Any] = {}
        if self.trial.metadata and "ANALOG" in self.trial.metadata:
            analog_meta = self.trial.metadata["ANALOG"].get("parameters", {})

        old_gen_scale = 1.0
        if "GEN_SCALE" in analog_meta:
            try:
                old_gen_scale = float(np.atleast_1d(analog_meta["GEN_SCALE"].get("values", [1.0]))[0])
            except Exception:
                old_gen_scale = 1.0

        old_scale = 1.0
        if "SCALE" in analog_meta:
            try:
                old_scale = float(np.atleast_1d(analog_meta["SCALE"].get("values", [1.0]))[0])
            except Exception:
                old_scale = 1.0

        old_comb = old_scale * old_gen_scale
        new_comb = new_scale * new_gen_scale

        # Scaling ratio to transform channel values
        # e.g. If user changes SCALE from -1.0 to +1.0, scale_ratio is -1.0 so all channel values invert sign
        scale_ratio = 1.0
        if abs(old_comb) > 1e-12:
            scale_ratio = new_comb / old_comb
        elif abs(new_comb) > 1e-12:
            scale_ratio = new_comb

        old_analogs = {k: v.copy() for k, v in self.trial.analogs.items()}
        new_analogs = {k: (v * scale_ratio).astype(np.float32) for k, v in self.trial.analogs.items()}

        old_units = dict(self.trial.analog_units)
        new_units = {k: new_unit for k in self.trial.analogs.keys()}

        old_rate = float(self.trial.analog_rate)
        old_subsamples = int(self.trial.analog_subsamples)
        point_rate = float(self.trial.point_rate) if self.trial.point_rate > 0 else 100.0
        new_subsamples = max(1, int(round(new_rate / point_rate))) if point_rate > 0 else 1

        # Backup & update metadata tree
        old_meta = copy.deepcopy(self.trial.metadata.get("ANALOG", {}))
        new_meta = copy.deepcopy(old_meta)
        if "parameters" not in new_meta:
            new_meta["parameters"] = {}

        n_ch = len(self.trial.analogs)
        new_meta["parameters"]["GEN_SCALE"] = {"values": np.array([new_gen_scale], dtype=np.float32), "description": ""}
        new_meta["parameters"]["SCALE"] = {"values": np.full(n_ch, new_scale, dtype=np.float32), "description": ""}
        new_meta["parameters"]["OFFSET"] = {"values": np.full(n_ch, int(round(new_offset)), dtype=np.int32), "description": ""}
        new_meta["parameters"]["RATE"] = {"values": np.array([new_rate], dtype=np.float32), "description": ""}
        new_meta["parameters"]["UNITS"] = {"values": [new_unit] * n_ch, "description": ""}

        # Also recalculate force platforms if force plates are configured in this trial
        old_fp = [fp.clone() for fp in self.trial.force_platforms]
        new_fp = []
        if self.trial.force_platforms:
            for fp in self.trial.force_platforms:
                fp_clone = fp.clone()
                # Update channel references in fp_clone with newly scaled signals
                for ch_key in list(fp_clone.channels.keys()):
                    if ch_key in new_analogs:
                        fp_clone.channels[ch_key] = new_analogs[ch_key]
                # Recompute Ground Reaction Wrenches with updated analogs
                try:
                    # Extract analog matrix using updated new_analogs
                    temp_trial = copy.copy(self.trial)
                    temp_trial.analogs = new_analogs
                    V, resolved_names = extract_plate_analog_matrix(temp_trial, fp_clone)
                    if V.size > 0 and np.any(V != 0):
                        grw = compute_single_plate_grw(
                            analog_signals=V,
                            fp_type=fp_clone.type,
                            corners=fp_clone.corners,
                            origin=fp_clone.origin,
                            cal_matrix=fp_clone.cal_matrix,
                            threshold=10.0,
                            custom_offset=True
                        )
                        fp_clone.forces = grw['F']
                        fp_clone.moments = grw['M']
                        fp_clone.cop = grw['P']
                except Exception as e:
                    print(f"Warning updating force plate #{fp.id} on analog specs change: {e}")
                new_fp.append(fp_clone)

        parent_mw = self.parent()
        while parent_mw and not hasattr(parent_mw, "undo_stack") and hasattr(parent_mw, "parent"):
            parent_mw = parent_mw.parent()

        cmd = UpdateAnalogSpecificationsCommand(
            main_window=parent_mw,
            trial=self.trial,
            old_analogs=old_analogs,
            new_analogs=new_analogs,
            old_units=old_units,
            new_units=new_units,
            old_meta=old_meta,
            new_meta=new_meta,
            old_rate=old_rate,
            new_rate=new_rate,
            old_subsamples=old_subsamples,
            new_subsamples=new_subsamples,
            old_force_platforms=old_fp,
            new_force_platforms=new_fp,
            analog_dialog=self,
            description="Update Analog Specifications"
        )
        if self.undo_stack:
            self.undo_stack.push(cmd)
        else:
            cmd.redo()

        self.analogsChanged.emit()
        _safe_info(
            self,
            "Specifications Applied",
            f"Updated analog specifications successfully!\n"
            f"SCALE: {new_scale:.1f} | GEN_SCALE: {new_gen_scale:.1f} | Combined Scale: {new_comb:.1f}\n"
            f"Analog signals scaled by ratio {scale_ratio:.4g} across {n_ch} channels."
        )

"""Pipeline Execution Engine for Batch Processing in C3D Explorer.

Parses Pipeline XML recipes and executes operations sequentially across
target C3D trials (intrinsic operations and extrinsic per-trial file mapping).
"""

import os
import re
import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable
import numpy as np

from core.data_models import C3DTrial, C3DEvent
from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter


# ------------------------------------------------------------------------------
# Data Models for Pipeline Execution
# ------------------------------------------------------------------------------

@dataclass
class ExecutableOperation:
    """An executable step parsed from a Pipeline XML recipe."""
    id: int
    action: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class TrialExecutionResult:
    """Detailed result of executing a pipeline on a single C3D file."""
    input_path: str
    output_path: str = ""
    success: bool = False
    operations_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ------------------------------------------------------------------------------
# Helper Signal Processing & File Parsers
# ------------------------------------------------------------------------------

def filter_marker_array(data: np.ndarray, fs: float, order: int, cutoff: float) -> np.ndarray:
    """Apply zero-phase Butterworth low-pass filter to (N, 3) marker trajectory."""
    if data is None or len(data) == 0:
        return data.copy() if data is not None else data

    from scipy import signal
    nyq = 0.5 * fs
    wn = min(max(cutoff / nyq, 0.0001), 0.9999)
    b, a = signal.butter(order, wn, btype="low")

    filtered = np.zeros_like(data, dtype=np.float64)
    N = data.shape[0]

    for d in range(data.shape[1]):
        col = data[:, d].astype(np.float64)
        valid_mask = ~np.isnan(col) & (col != 0.0)
        valid_count = np.sum(valid_mask)

        if valid_count < 3 * max(len(b), len(a)):
            filtered[:, d] = col
            continue

        clean_col = col.copy()
        if not np.all(valid_mask):
            x_indices = np.arange(N)
            clean_col[~valid_mask] = np.interp(
                x_indices[~valid_mask],
                x_indices[valid_mask],
                col[valid_mask]
            )

        padlen = min(3 * max(len(b), len(a)), N - 1)
        filt_col = signal.filtfilt(b, a, clean_col, padlen=padlen)
        filt_col[~valid_mask] = col[~valid_mask]
        filtered[:, d] = filt_col

    return filtered.astype(np.float32)


def compute_harrington_hjc(
    lasi_data: np.ndarray,
    rasi_data: np.ndarray,
    lpsi_data: np.ndarray,
    rpsi_data: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hip Joint Center computation according to Harrington et al. (J. Biomech 2006).
    Estimates Right and Left Hip Joint Centers (RHJC, LHJC) from 4 pelvic markers
    (LASIS, RASIS, LPSIS, RPSIS).
    
    Formula (offsets relative to pelvis origin OP in mm):
      PW (pelvis width) = distance between ASIS markers
      PD (pelvis depth) = distance between ASIS midpoint and PSIS midpoint
      diff_ap = -0.24 * PD - 9.9
      diff_v  = -0.30 * PW - 10.9
      diff_ml =  0.33 * PW + 7.3
      
      RHJC = OP + diff_ml * IB + diff_ap * JB + diff_v * KB
      LHJC = OP - diff_ml * IB + diff_ap * JB + diff_v * KB
    """
    n_frames = min(len(lasi_data), len(rasi_data), len(lpsi_data), len(rpsi_data))
    rhjc = np.zeros((n_frames, 3), dtype=np.float32)
    lhjc = np.zeros((n_frames, 3), dtype=np.float32)

    def is_missing(p):
        return np.all(p == 0, axis=-1) | np.isnan(p).any(axis=-1)

    for t in range(n_frames):
        l_asi = lasi_data[t]
        r_asi = rasi_data[t]
        l_psi = lpsi_data[t]
        r_psi = rpsi_data[t]

        if is_missing(l_asi) or is_missing(r_asi) or is_missing(l_psi) or is_missing(r_psi):
            continue

        sacrum = (r_psi + l_psi) / 2.0
        op = (l_asi + r_asi) / 2.0

        provv_vec = r_asi - sacrum
        n_provv = np.linalg.norm(provv_vec)
        if n_provv < 1e-6:
            continue
        provv = provv_vec / n_provv

        ib_vec = r_asi - l_asi
        n_ib = np.linalg.norm(ib_vec)
        if n_ib < 1e-6:
            continue
        ib = ib_vec / n_ib  # Mediolateral axis pointing right

        kb_vec = np.cross(ib, provv)
        n_kb = np.linalg.norm(kb_vec)
        if n_kb < 1e-6:
            continue
        kb = kb_vec / n_kb  # Vertical axis pointing up

        jb_vec = np.cross(kb, ib)
        n_jb = np.linalg.norm(jb_vec)
        if n_jb < 1e-6:
            continue
        jb = jb_vec / n_jb  # Anteroposterior axis pointing anterior

        pw = n_ib
        pd = np.linalg.norm(sacrum - op)

        diff_ap = -0.24 * pd - 9.9
        diff_v = -0.30 * pw - 10.9
        diff_ml = 0.33 * pw + 7.3

        rhjc[t] = op + diff_ml * ib + diff_ap * jb + diff_v * kb
        lhjc[t] = op - diff_ml * ib + diff_ap * jb + diff_v * kb

    return rhjc, lhjc


def apply_analog_filter(
    data: np.ndarray,
    fs: float,
    method: str,
    order: int = 4,
    cutoff: Any = 20.0
) -> np.ndarray:
    """Zero-phase filtering for analog signals."""
    if data is None or len(data) == 0:
        return data.copy() if data is not None else data

    from scipy import signal
    nyq = 0.5 * fs
    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return data.copy()

    clean_data = data.copy()
    if not np.all(valid_mask):
        x = np.arange(len(data))
        clean_data[~valid_mask] = np.interp(x[~valid_mask], x[valid_mask], data[valid_mask])

    f_type = method.lower()
    if "low" in f_type:
        c_val = cutoff if isinstance(cutoff, (int, float)) else cutoff[0]
        wn = min(max(c_val / nyq, 0.0001), 0.9999)
        b, a = signal.butter(order, wn, btype="low")
    elif "high" in f_type:
        c_val = cutoff if isinstance(cutoff, (int, float)) else cutoff[0]
        wn = min(max(c_val / nyq, 0.0001), 0.9999)
        b, a = signal.butter(order, wn, btype="high")
    elif "bandpass" in f_type or ("band" in f_type and "stop" not in f_type):
        if isinstance(cutoff, (list, tuple)) and len(cutoff) >= 2:
            low, high = float(cutoff[0]), float(cutoff[1])
        else:
            low, high = 10.0, min(100.0, nyq * 0.9)
        wn = [min(max(low / nyq, 0.0001), 0.999), min(max(high / nyq, 0.0002), 0.9999)]
        b, a = signal.butter(order, wn, btype="bandpass")
    elif "notch" in f_type or "bandstop" in f_type or "stop" in f_type:
        if isinstance(cutoff, (list, tuple)) and len(cutoff) >= 2:
            low, high = float(cutoff[0]), float(cutoff[1])
            wn = [min(max(low / nyq, 0.0001), 0.999), min(max(high / nyq, 0.0002), 0.9999)]
            b, a = signal.butter(order, wn, btype="bandstop")
        else:
            c_val = cutoff if isinstance(cutoff, (int, float)) else 50.0
            f0 = min(max(float(c_val), 1.0), nyq - 1.0)
            b, a = signal.iirnotch(f0, 30.0, fs=fs)
    elif "rms" in f_type:
        win_ms = float(cutoff) if isinstance(cutoff, (int, float)) else 50.0
        win_samples = max(1, int(win_ms * fs / 1000.0))
        kernel = np.ones(win_samples) / float(win_samples)
        filtered = np.sqrt(np.convolve(clean_data ** 2, kernel, mode="same"))
        if not np.all(valid_mask):
            filtered[~valid_mask] = np.nan
        return filtered.astype(np.float32)
    elif "rectif" in f_type:
        return np.abs(data)
    elif "linear envelope" in f_type:
        rect = np.abs(clean_data)
        c_val = cutoff if isinstance(cutoff, (int, float)) else 6.0
        wn = min(max(float(c_val) / nyq, 0.0001), 0.9999)
        b, a = signal.butter(order, wn, btype="low")
        filtered = signal.filtfilt(b, a, rect)
        return filtered.astype(np.float32)
    elif "emg custom" in f_type or "emg_custom" in f_type:
        if isinstance(cutoff, dict):
            bp_l = float(cutoff.get("bp_low", 20.0))
            bp_h = float(cutoff.get("bp_high", 400.0))
            lp_c = float(cutoff.get("lp_cutoff", 20.0))
        elif isinstance(cutoff, (list, tuple)) and len(cutoff) >= 3:
            bp_l, bp_h, lp_c = float(cutoff[0]), float(cutoff[1]), float(cutoff[2])
        else:
            bp_l, bp_h, lp_c = 20.0, 400.0, 20.0
        return apply_emg_custom_filter(clean_data, fs, bp_low=bp_l, bp_high=bp_h, lp_cutoff=lp_c, bp_order=order, lp_order=order)
    else:
        return data.copy()

    padlen = min(3 * max(len(b), len(a)), len(clean_data) - 1)
    filtered = signal.filtfilt(b, a, clean_data, padlen=padlen)
    if not np.all(valid_mask):
        filtered[~valid_mask] = np.nan
    return filtered.astype(np.float32)


def apply_emg_custom_filter(
    data: np.ndarray,
    fs: float,
    bp_low: float = 20.0,
    bp_high: float = 400.0,
    lp_cutoff: float = 20.0,
    bp_order: int = 4,
    lp_order: int = 4
) -> np.ndarray:
    """
    Two-step EMG processing pipeline:
      Step 1: Zero-phase Butterworth band-pass filter (default 20 Hz – 400 Hz).
      Step 2: Full-wave rectification (|x|) followed by zero-phase Butterworth low-pass filter (default 20 Hz).
    """
    if data is None or len(data) == 0:
        return data.copy() if data is not None else np.array([], dtype=np.float32)

    from scipy import signal
    nyq = 0.5 * fs
    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return data.copy()

    clean_data = data.copy()
    if not np.all(valid_mask):
        x = np.arange(len(data))
        clean_data[~valid_mask] = np.interp(x[~valid_mask], x[valid_mask], data[valid_mask])

    # Step 1: Band-pass filter
    low = max(0.5, min(float(bp_low), nyq * 0.95))
    high = max(low + 1.0, min(float(bp_high), nyq * 0.99))
    wn_bp = [low / nyq, high / nyq]
    b_bp, a_bp = signal.butter(bp_order, wn_bp, btype="bandpass")
    pad_bp = min(3 * max(len(b_bp), len(a_bp)), len(clean_data) - 1)
    if pad_bp > 0:
        bandpassed = signal.filtfilt(b_bp, a_bp, clean_data, padlen=pad_bp)
    else:
        bandpassed = clean_data

    # Step 2: Full-wave rectification
    rectified = np.abs(bandpassed)

    # Step 2 continued: Low-pass filter (smoothing envelope)
    lp_c = max(0.1, min(float(lp_cutoff), nyq * 0.99))
    wn_lp = lp_c / nyq
    b_lp, a_lp = signal.butter(lp_order, wn_lp, btype="low")
    pad_lp = min(3 * max(len(b_lp), len(a_lp)), len(rectified) - 1)
    if pad_lp > 0:
        envelope = signal.filtfilt(b_lp, a_lp, rectified, padlen=pad_lp)
    else:
        envelope = rectified

    if not np.all(valid_mask):
        envelope[~valid_mask] = np.nan
    return envelope.astype(np.float32)


def read_external_marker_file(filepath: str, expected_frames: int) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """Load (N, 3) marker trajectory from CSV, TSV, TXT, or Excel."""
    if not os.path.isfile(filepath):
        return None, f"File not found: {filepath}"

    ext = os.path.splitext(filepath)[1].lower()
    raw_rows = []

    try:
        if ext in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    raw_rows.append(list(row))
            wb.close()
        else:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            delim = None
            if ext == ".csv" or "," in content.splitlines()[0]:
                delim = ","
            elif ext == ".tsv" or "\t" in content.splitlines()[0]:
                delim = "\t"
            elif ";" in content.splitlines()[0]:
                delim = ";"

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
        return None, f"Error reading external marker file: {e}"

    if not raw_rows:
        return None, "File is empty."

    numeric_rows = []
    for row in raw_rows:
        nums = []
        for val in row:
            if val is None or str(val).strip() == "":
                continue
            try:
                nums.append(float(str(val).replace(",", ".")))
            except (ValueError, TypeError):
                pass
        if len(nums) >= 3:
            numeric_rows.append(nums)

    if not numeric_rows:
        return None, "No numeric 3D coordinates found."

    first_row = numeric_rows[0]
    if len(first_row) >= 4:
        col0 = [r[0] for r in numeric_rows]
        is_idx = False
        if len(col0) > 1:
            diffs = np.diff(col0)
            if np.allclose(diffs, 1.0) or (col0[0] in (0.0, 1.0) and np.all(diffs > 0)):
                is_idx = True
        arr = np.array([r[1:4] if is_idx else r[:3] for r in numeric_rows], dtype=np.float32)
    else:
        arr = np.array([r[:3] for r in numeric_rows], dtype=np.float32)

    if arr.shape[0] != expected_frames:
        return None, f"Frame count mismatch (File has {arr.shape[0]} rows, trial requires {expected_frames})"

    return arr, None


def read_external_analog_file(filepath: str, expected_frames: int, target_col: Optional[str] = None) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """Load 1D analog signal from CSV, TSV, TXT, or Excel."""
    if not os.path.isfile(filepath):
        return None, f"File not found: {filepath}"

    from gui.analog_dialog import parse_analog_file
    channels, err = parse_analog_file(filepath, expected_frames)
    if err or not channels:
        return None, err or "Failed to parse analog file."

    if target_col and target_col in channels:
        return channels[target_col], None

    # Default to the first available channel
    first_key = list(channels.keys())[0]
    return channels[first_key], None


# ------------------------------------------------------------------------------
# Pipeline Executor Class
# ------------------------------------------------------------------------------

class PipelineExecutor:
    """
    Parses and executes pipeline recipes across single or batch C3D trials.
    Supports intelligent file resolution for per-trial external files.
    """

    SUPPORTED_EXTENSIONS = (".c3d", ".csv", ".xlsx", ".xls", ".txt", ".tsv")

    def __init__(self, xml_path_or_content: Optional[str] = None):
        self.operations: List[ExecutableOperation] = []
        self.metadata: Dict[str, Any] = {}
        self.workstation_settings: Dict[str, Any] = {}
        if xml_path_or_content:
            self.load_xml(xml_path_or_content)

    def load_xml(self, xml_source: str) -> bool:
        """Parse XML file or string into executable operations."""
        self.operations.clear()
        self.metadata.clear()
        self.workstation_settings.clear()

        try:
            if os.path.isfile(xml_source):
                tree = ET.parse(xml_source)
                root = tree.getroot()
            else:
                root = ET.fromstring(xml_source)

            self.metadata["version"] = root.attrib.get("version", "1.0")
            self.metadata["created"] = root.attrib.get("created", "")

            # Parse Operations
            ops_elem = root.find("PipelineOperations")
            if ops_elem is not None:
                for idx, op_node in enumerate(ops_elem.findall("Operation"), start=1):
                    action = op_node.attrib.get("action", "")
                    op_id = int(op_node.attrib.get("id", idx))
                    timestamp = op_node.attrib.get("timestamp", "")
                    desc_node = op_node.find("Description")
                    desc = desc_node.text.strip() if desc_node is not None and desc_node.text else action

                    params = {}
                    params_node = op_node.find("Parameters")
                    if params_node is not None:
                        params = self._xml_to_dict(params_node)

                    self.operations.append(ExecutableOperation(
                        id=op_id,
                        action=action,
                        description=desc,
                        parameters=params,
                        timestamp=timestamp
                    ))

            return True

        except Exception as e:
            self.operations.clear()
            raise ValueError(f"Failed to load Pipeline XML: {e}")

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Convert an XML element tree to a Python dictionary."""
        out: Dict[str, Any] = {}
        for child in element:
            tag = child.tag
            if len(child) > 0:
                # Nested children
                if all(c.tag == "Item" for c in child):
                    val = [c.text.strip() if c.text else "" for c in child]
                else:
                    val = self._xml_to_dict(child)
            else:
                text = child.text.strip() if child.text else ""
                val = self._parse_val(text)

            out[tag] = val
        return out

    @staticmethod
    def _parse_val(text: str) -> Any:
        """Parse primitive scalar value from string."""
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        if text.lower() in ("none", "null", ""):
            return None
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def get_external_file_requirements(self) -> List[Dict[str, Any]]:
        """
        Inspect operations to identify which steps require external data files per trial.
        Returns a list of descriptor dicts (entity type, name, original file).
        """
        reqs = []
        for op in self.operations:
            st = str(op.parameters.get("SourceType", "")).lower()
            if op.action == "AddMarker" and st == "file":
                reqs.append({
                    "action": op.action,
                    "type": "marker",
                    "name": op.parameters.get("MarkerName", ""),
                    "original_file": op.parameters.get("SourceFile", ""),
                    "op_id": op.id,
                })
            elif op.action == "AddAnalogChannel" and st == "file":
                reqs.append({
                    "action": op.action,
                    "type": "analog",
                    "name": op.parameters.get("ChannelName", ""),
                    "original_file": op.parameters.get("SourceFile", ""),
                    "op_id": op.id,
                })
        return reqs

    @staticmethod
    def resolve_external_file_for_trial(
        c3d_file_path: str,
        entity_name: str,
        search_dirs: Optional[List[str]] = None,
        original_fallback: str = ""
    ) -> Optional[str]:
        """
        Intelligently locate the corresponding external file (CSV, Excel, TXT)
        for a specific C3D trial and entity name (e.g. 'MTJ').
        
        Searches candidates such as:
        - {c3d_basename}_{entity_name}.*
        - {c3d_basename}-{entity_name}.*
        - {c3d_basename} {entity_name}.*
        - {c3d_basename}.*
        """
        c3d_dir = os.path.dirname(os.path.abspath(c3d_file_path))
        c3d_base = os.path.splitext(os.path.basename(c3d_file_path))[0]

        dirs_to_search = []
        if search_dirs:
            for d in search_dirs:
                if d and os.path.isdir(d):
                    dirs_to_search.append(os.path.abspath(d))
        if c3d_dir not in dirs_to_search:
            dirs_to_search.append(c3d_dir)

        # Build patterns in priority order
        patterns = [
            re.compile(rf"^{re.escape(c3d_base)}[_\-\s]+{re.escape(entity_name)}\.(csv|xlsx|xls|txt|tsv)$", re.IGNORECASE),
            re.compile(rf"^{re.escape(entity_name)}[_\-\s]+{re.escape(c3d_base)}\.(csv|xlsx|xls|txt|tsv)$", re.IGNORECASE),
            re.compile(rf"^{re.escape(c3d_base)}\.(csv|xlsx|xls|txt|tsv)$", re.IGNORECASE),
            re.compile(rf".*{re.escape(c3d_base)}.*{re.escape(entity_name)}.*\.(csv|xlsx|xls|txt|tsv)$", re.IGNORECASE),
        ]

        for s_dir in dirs_to_search:
            if not os.path.isdir(s_dir):
                continue

            try:
                filenames = os.listdir(s_dir)
            except Exception:
                continue

            for pattern in patterns:
                for fname in filenames:
                    if pattern.match(fname):
                        candidate = os.path.join(s_dir, fname)
                        if os.path.isfile(candidate):
                            return candidate

        # Fallback to original path if it exists
        if original_fallback and os.path.isfile(original_fallback):
            return original_fallback

        return None

    def execute_on_trial(
        self,
        trial: C3DTrial,
        c3d_file_path: str = "",
        search_dirs: Optional[List[str]] = None,
        custom_file_map: Optional[Dict[str, str]] = None
    ) -> TrialExecutionResult:
        """
        Execute all operations in this pipeline on an in-memory C3DTrial instance.
        """
        result = TrialExecutionResult(input_path=c3d_file_path)
        c3d_base = os.path.splitext(os.path.basename(c3d_file_path))[0] if c3d_file_path else "Trial"

        for op in self.operations:
            action = op.action
            p = op.parameters

            try:
                if action == "CreateAverageMarker":
                    new_name = str(p.get("NewMarkerName", "")).strip()
                    m1 = str(p.get("SourceMarker1", "")).strip()
                    m2 = str(p.get("SourceMarker2", "")).strip()
                    w1 = float(p.get("Weight1", 0.5))
                    w2 = float(p.get("Weight2", 0.5))

                    if not new_name:
                        result.warnings.append(f"Operation #{op.id}: Missing NewMarkerName for average marker")
                        continue

                    if m1 not in trial.markers or m2 not in trial.markers:
                        missing = [m for m in (m1, m2) if m not in trial.markers]
                        result.warnings.append(f"Operation #{op.id}: Cannot create '{new_name}', missing source marker(s): {', '.join(missing)}")
                        continue

                    d1 = trial.markers[m1]
                    d2 = trial.markers[m2]
                    avg_data = (d1 * w1) + (d2 * w2)

                    m1_missing = np.all(d1 == 0, axis=1) | np.isnan(d1).any(axis=1)
                    m2_missing = np.all(d2 == 0, axis=1) | np.isnan(d2).any(axis=1)
                    both = m1_missing & m2_missing
                    avg_data[both] = 0.0
                    avg_data[m1_missing & ~m2_missing] = d2[m1_missing & ~m2_missing]
                    avg_data[m2_missing & ~m1_missing] = d1[m2_missing & ~m1_missing]

                    trial.markers[new_name] = avg_data.astype(np.float32)
                    result.operations_count += 1
                    result.details.append(f"Created average marker '{new_name}' from '{m1}' and '{m2}'")

                elif action == "CreateCentroidMarker":
                    new_name = str(p.get("NewMarkerName", "")).strip()
                    src_str = str(p.get("SourceMarkers", "")).strip()
                    src_markers = [m.strip() for m in src_str.split(",") if m.strip()]

                    if not new_name:
                        result.warnings.append(f"Operation #{op.id}: Missing NewMarkerName for centroid marker")
                        continue

                    if not src_markers:
                        result.warnings.append(f"Operation #{op.id}: Missing SourceMarkers for centroid marker")
                        continue

                    valid_srcs = [m for m in src_markers if m in trial.markers]
                    if not valid_srcs:
                        result.warnings.append(f"Operation #{op.id}: Cannot create '{new_name}', none of the source markers exist in trial: {', '.join(src_markers)}")
                        continue

                    arrays = [trial.markers[m] for m in valid_srcs]
                    stacked = np.stack(arrays, axis=0)

                    is_missing = np.all(stacked == 0, axis=-1) | np.isnan(stacked).any(axis=-1)
                    masked = stacked.copy()
                    masked[is_missing] = np.nan

                    with np.errstate(invalid='ignore'):
                        centroid_data = np.nanmean(masked, axis=0)

                    all_missing = np.all(is_missing, axis=0)
                    centroid_data[all_missing] = 0.0

                    trial.markers[new_name] = centroid_data.astype(np.float32)
                    result.operations_count += 1
                    result.details.append(f"Created centroid marker '{new_name}' from {len(valid_srcs)} markers ({', '.join(valid_srcs)})")

                elif action in ("CalculateHipJointCenter", "CalculateHJC"):
                    rhjc_name = str(p.get("RightHJCName", "RHJC")).strip()
                    lhjc_name = str(p.get("LeftHJCName", "LHJC")).strip()
                    m_lasi = str(p.get("LASIMarker", "")).strip()
                    m_rasi = str(p.get("RASIMarker", "")).strip()
                    m_lpsi = str(p.get("LPSIMarker", "")).strip()
                    m_rpsi = str(p.get("RPSIMarker", "")).strip()

                    needed = [m_lasi, m_rasi, m_lpsi, m_rpsi]
                    missing = [m for m in needed if not m or m not in trial.markers]
                    if missing:
                        result.warnings.append(f"Operation #{op.id}: Cannot calculate HJC, missing pelvis marker(s): {', '.join(missing)}")
                        continue

                    rhjc_data, lhjc_data = compute_harrington_hjc(
                        trial.markers[m_lasi],
                        trial.markers[m_rasi],
                        trial.markers[m_lpsi],
                        trial.markers[m_rpsi]
                    )

                    trial.markers[rhjc_name] = rhjc_data
                    trial.markers[lhjc_name] = lhjc_data
                    result.operations_count += 2
                    result.details.append(f"Calculated HJC '{rhjc_name}' and '{lhjc_name}' via Harrington from {m_lasi}, {m_rasi}, {m_lpsi}, {m_rpsi}")

                elif action == "AddMarker":
                    name = str(p.get("MarkerName", "")).strip()
                    src_type = str(p.get("SourceType", "manual")).lower()

                    if not name:
                        result.warnings.append(f"Operation #{op.id}: Missing MarkerName")
                        continue

                    if src_type == "file":
                        ext_file = None
                        if custom_file_map and name in custom_file_map:
                            ext_file = custom_file_map[name]
                        else:
                            orig = str(p.get("SourceFile", ""))
                            ext_file = self.resolve_external_file_for_trial(
                                c3d_file_path=c3d_file_path,
                                entity_name=name,
                                search_dirs=search_dirs,
                                original_fallback=orig
                            )

                        if not ext_file or not os.path.isfile(ext_file):
                            result.warnings.append(f"Operation #{op.id}: No external file found for marker '{name}' on trial '{c3d_base}'")
                            continue

                        data, err = read_external_marker_file(ext_file, trial.point_frame_count)
                        if err or data is None:
                            result.warnings.append(f"Operation #{op.id}: Failed to load marker '{name}' from {os.path.basename(ext_file)}: {err}")
                            continue

                        trial.markers[name] = data
                        result.operations_count += 1
                        result.details.append(f"Added marker '{name}' from {os.path.basename(ext_file)}")

                    else:
                        coords = p.get("DefaultCoordinates", {})
                        if isinstance(coords, dict):
                            x = float(coords.get("X", 0.0))
                            y = float(coords.get("Y", 0.0))
                            z = float(coords.get("Z", 0.0))
                        else:
                            x, y, z = 0.0, 0.0, 0.0

                        arr = np.tile([x, y, z], (trial.point_frame_count, 1)).astype(np.float32)
                        trial.markers[name] = arr
                        result.operations_count += 1
                        result.details.append(f"Added custom marker '{name}' with coordinates ({x}, {y}, {z})")

                elif action in ("FilterMarkers", "FilterMarker", "Filter_Markers", "Filter_Marker", "Filter") or ("filter" in action.lower() and "marker" in action.lower()):
                    order = int(p.get("Order") or p.get("order") or 4)
                    cutoff = float(p.get("CutoffFrequency_Hz") or p.get("CutoffFrequency") or p.get("Cutoff") or p.get("cutoff") or 6.0)
                    fs = float(trial.point_rate if trial.point_rate > 0 else (p.get("SamplingRate_Hz") or 100.0))

                    if not trial.markers:
                        result.warnings.append(f"Operation #{op.id}: No markers present to filter")
                        continue

                    target_markers = p.get("TargetMarkers") or p.get("Markers") or list(trial.markers.keys())
                    if isinstance(target_markers, str):
                        target_markers = [target_markers] if target_markers != "All" else list(trial.markers.keys())

                    filtered_count = 0
                    for m_name in target_markers:
                        if m_name in trial.markers:
                            trial.markers[m_name] = filter_marker_array(trial.markers[m_name], fs, order, cutoff)
                            filtered_count += 1

                    result.operations_count += 1
                    result.details.append(f"Filtered {filtered_count} marker trajectories (Butterworth Order {order}, {cutoff:.1f} Hz)")

                elif action == "RenameMarker":
                    old_n = str(p.get("OldName", "")).strip()
                    new_n = str(p.get("NewName", "")).strip()

                    if old_n and new_n and old_n in trial.markers:
                        trial.markers[new_n] = trial.markers.pop(old_n)
                        result.operations_count += 1
                        result.details.append(f"Renamed marker '{old_n}' \u2192 '{new_n}'")
                    else:
                        result.warnings.append(f"Operation #{op.id}: Marker '{old_n}' not found to rename")

                elif action == "DeleteMarkers":
                    del_markers = p.get("DeletedMarkers", [])
                    if isinstance(del_markers, str):
                        del_markers = [del_markers]

                    deleted = []
                    for m in del_markers:
                        if m in trial.markers:
                            del trial.markers[m]
                            deleted.append(m)

                    if deleted:
                        result.operations_count += 1
                        result.details.append(f"Deleted {len(deleted)} marker(s): {', '.join(deleted)}")

                elif action == "AddAnalogChannel":
                    name = str(p.get("ChannelName", "")).strip()
                    unit = str(p.get("Unit", "V")).strip()
                    src_type = str(p.get("SourceType", "manual")).lower()

                    if not name:
                        result.warnings.append(f"Operation #{op.id}: Missing ChannelName")
                        continue

                    if src_type == "file":
                        ext_file = None
                        if custom_file_map and name in custom_file_map:
                            ext_file = custom_file_map[name]
                        else:
                            orig = str(p.get("SourceFile", ""))
                            ext_file = self.resolve_external_file_for_trial(
                                c3d_file_path=c3d_file_path,
                                entity_name=name,
                                search_dirs=search_dirs,
                                original_fallback=orig
                            )

                        if not ext_file or not os.path.isfile(ext_file):
                            result.warnings.append(f"Operation #{op.id}: No external file found for channel '{name}' on trial '{c3d_base}'")
                            continue

                        data, err = read_external_analog_file(ext_file, trial.analog_frame_count)
                        if err or data is None:
                            result.warnings.append(f"Operation #{op.id}: Failed to load channel '{name}' from {os.path.basename(ext_file)}: {err}")
                            continue

                        trial.analogs[name] = data
                        trial.analog_units[name] = unit
                        result.operations_count += 1
                        result.details.append(f"Added analog channel '{name}' from {os.path.basename(ext_file)}")

                    elif src_type == "filtered":
                        # Created from filtering an existing channel
                        proc = p.get("Processing", {})
                        src_ch = proc.get("SourceChannel", "")
                        if src_ch in trial.analogs:
                            meth = proc.get("Method", "Low-pass")
                            ordr = int(proc.get("Order", 4))
                            cut = proc.get("Cutoff", 20.0)
                            fs = trial.analog_rate if trial.analog_rate > 0 else 1000.0
                            filt = apply_analog_filter(trial.analogs[src_ch], fs, meth, ordr, cut)
                            trial.analogs[name] = filt
                            trial.analog_units[name] = unit
                            result.operations_count += 1
                            result.details.append(f"Created filtered channel '{name}' from '{src_ch}'")
                        else:
                            result.warnings.append(f"Operation #{op.id}: Source channel '{src_ch}' not found to filter into '{name}'")

                    else:
                        arr = np.zeros(trial.analog_frame_count, dtype=np.float32)
                        trial.analogs[name] = arr
                        trial.analog_units[name] = unit
                        result.operations_count += 1
                        result.details.append(f"Added custom analog channel '{name}'")

                elif action == "FilterAnalogChannel":
                    ch_name = str(p.get("ChannelName", "")).strip()
                    method = str(p.get("Method", "Butterworth Low-pass")).strip()
                    order = int(p.get("Order", 4))
                    cutoff = p.get("Cutoff", 20.0)

                    if ch_name not in trial.analogs:
                        result.warnings.append(f"Operation #{op.id}: Analog channel '{ch_name}' not found to filter")
                        continue

                    fs = float(p.get("SamplingRate_Hz", trial.analog_rate if trial.analog_rate > 0 else 1000.0))
                    raw_sig = trial.analogs[ch_name]
                    trial.analogs[ch_name] = apply_analog_filter(raw_sig, fs, method, order, cutoff)
                    result.operations_count += 1
                    result.details.append(f"Filtered analog channel '{ch_name}' ({method})")

                elif action in ("EMGCustomFilter", "EMG_Custom", "EMGCustom"):
                    raw_ch = p.get("Channels") or p.get("ChannelName") or []
                    if isinstance(raw_ch, str):
                        raw_ch = [raw_ch]
                    bp_low = float(p.get("BandpassLow_Hz", 20.0))
                    bp_high = float(p.get("BandpassHigh_Hz", 400.0))
                    lp_cutoff = float(p.get("LowpassCutoff_Hz", 20.0))
                    ordr = int(p.get("Order", 4))
                    overwrite = bool(p.get("Overwrite", True))
                    fs = float(trial.analog_rate if trial.analog_rate > 0 else 1000.0)

                    target_channels = raw_ch if raw_ch else list(trial.analogs.keys())
                    applied_count = 0
                    for ch in target_channels:
                        if ch in trial.analogs:
                            raw_sig = trial.analogs[ch]
                            filtered = apply_emg_custom_filter(raw_sig, fs, bp_low, bp_high, lp_cutoff, ordr, ordr)
                            if overwrite:
                                trial.analogs[ch] = filtered
                            else:
                                new_n = f"{ch}_EMG_env"
                                trial.analogs[new_n] = filtered
                                trial.analog_units[new_n] = trial.analog_units.get(ch, "V")
                            applied_count += 1
                        else:
                            result.warnings.append(f"Operation #{op.id}: Analog channel '{ch}' not found for EMG filter")

                    result.operations_count += 1
                    result.details.append(f"Applied EMG Custom Filter (BP {bp_low:.0f}-{bp_high:.0f} Hz, LP {lp_cutoff:.0f} Hz) to {applied_count} channels")

                elif action == "RenameAnalogChannel":
                    old_n = str(p.get("OldName", "")).strip()
                    new_n = str(p.get("NewName", "")).strip()

                    if old_n and new_n and old_n in trial.analogs:
                        trial.analogs[new_n] = trial.analogs.pop(old_n)
                        if old_n in trial.analog_units:
                            trial.analog_units[new_n] = trial.analog_units.pop(old_n)
                        result.operations_count += 1
                        result.details.append(f"Renamed analog channel '{old_n}' \u2192 '{new_n}'")
                    else:
                        result.warnings.append(f"Operation #{op.id}: Analog channel '{old_n}' not found to rename")

                elif action == "DeleteAnalogChannels":
                    del_channels = p.get("DeletedChannels", [])
                    if isinstance(del_channels, str):
                        del_channels = [del_channels]

                    deleted = []
                    for c in del_channels:
                        if c in trial.analogs:
                            del trial.analogs[c]
                            trial.analog_units.pop(c, None)
                            deleted.append(c)

                    if deleted:
                        result.operations_count += 1
                        result.details.append(f"Deleted {len(deleted)} analog channel(s): {', '.join(deleted)}")

                elif action == "ClearEvents":
                    trial.events.clear()
                    result.operations_count += 1
                    result.details.append("Cleared all events from trial")

                elif action in ("ConfigureForcePlate", "CalculateForcePlate"):
                    from core.grw_calculator import compute_single_plate_grw, extract_plate_analog_matrix
                    mode = str(p.get("Mode", "Automatic")).lower()
                    thresh = float(p.get("Threshold_N", 10.0))
                    if "custom" in mode and trial.force_platforms:
                        plate_id = int(p.get("PlateID", 1))
                        fp_idx = max(0, min(len(trial.force_platforms) - 1, plate_id - 1))
                        fp = trial.force_platforms[fp_idx]
                        fp_type = int(p.get("Type", fp.type))
                        corners_raw = p.get("Corners")
                        origin_raw = p.get("OriginOffset")
                        cal_raw = p.get("CalibrationMatrix")
                        diag_raw = p.get("CalibrationDiagonal")
                        ch_raw = p.get("AnalogChannels")

                        if corners_raw is not None:
                            fp.corners = np.asarray(corners_raw, dtype=np.float32).reshape(3, 4)
                        if origin_raw is not None:
                            fp.origin = np.asarray(origin_raw, dtype=np.float32).flatten()[:3]
                            fp.coord_offset = fp.origin.copy()
                        if cal_raw is not None:
                            fp.cal_matrix = np.asarray(cal_raw, dtype=np.float32).reshape(6, 6)
                        elif diag_raw is not None:
                            fp.cal_matrix = np.diag(np.asarray(diag_raw, dtype=np.float32)[:6])
                        fp.type = fp_type

                        ch_list = ch_raw if isinstance(ch_raw, list) else None
                        V, resolved_names = extract_plate_analog_matrix(trial, fp, channel_names=ch_list)
                        grw = compute_single_plate_grw(
                            analog_signals=V,
                            fp_type=fp.type,
                            corners=fp.corners,
                            origin=fp.origin,
                            cal_matrix=fp.cal_matrix,
                            threshold=thresh,
                            custom_offset=True
                        )
                        fp.forces = grw['F']
                        fp.moments = grw['M']
                        fp.cop = grw['P']
                        if resolved_names:
                            fp.channel_names = resolved_names
                        result.operations_count += 1
                        result.details.append(f"Configured Force Plate #{fp.id} (Custom mode)")
                    else:
                        for fp in trial.force_platforms:
                            V, resolved_names = extract_plate_analog_matrix(trial, fp)
                            grw = compute_single_plate_grw(
                                analog_signals=V,
                                fp_type=fp.type,
                                corners=fp.corners,
                                origin=fp.origin,
                                cal_matrix=fp.cal_matrix,
                                threshold=thresh,
                                custom_offset=False
                            )
                            fp.forces = grw['F']
                            fp.moments = grw['M']
                            fp.cop = grw['P']
                            if resolved_names:
                                fp.channel_names = resolved_names
                        result.operations_count += 1
                        result.details.append(f"Calculated Force Plate GRF automatically (Shimba 1984, {thresh:.1f} N)")

            except Exception as e:
                result.errors.append(f"Operation #{op.id} ({action}) failed: {e}")

        result.success = len(result.errors) == 0
        return result

    def execute_file(
        self,
        input_c3d_path: str,
        output_c3d_path: str,
        search_dirs: Optional[List[str]] = None,
        custom_file_map: Optional[Dict[str, str]] = None,
        apply_trim_roi: bool = False
    ) -> TrialExecutionResult:
        """
        Process a single C3D file on disk and write the result to output_c3d_path.
        """
        import time
        t0 = time.time()

        try:
            trial = C3DReader.read(input_c3d_path)
        except Exception as e:
            res = TrialExecutionResult(input_path=input_c3d_path, output_path=output_c3d_path)
            res.errors.append(f"Failed to read C3D file: {e}")
            res.elapsed_seconds = round(time.time() - t0, 3)
            return res

        # Execute operations
        res = self.execute_on_trial(
            trial=trial,
            c3d_file_path=input_c3d_path,
            search_dirs=search_dirs,
            custom_file_map=custom_file_map
        )
        res.output_path = output_c3d_path

        # Determine start/end frame for save
        start_f = 0
        end_f = trial.point_frame_count - 1
        if apply_trim_roi:
            # Check if any operation was SetRegionOfInterest
            for op in self.operations:
                if op.action == "SetRegionOfInterest":
                    start_f = max(0, int(op.parameters.get("StartFrame", 0)))
                    end_f = min(trial.point_frame_count - 1, int(op.parameters.get("EndFrame", trial.point_frame_count - 1)))
                    break

        # Save result
        try:
            out_dir = os.path.dirname(os.path.abspath(output_c3d_path))
            os.makedirs(out_dir, exist_ok=True)
            C3DWriter.save_c3d(trial, output_c3d_path, start_frame=start_f, end_frame=end_f)
        except Exception as e:
            res.errors.append(f"Failed to save processed C3D: {e}")
            res.success = False

        res.elapsed_seconds = round(time.time() - t0, 3)
        return res

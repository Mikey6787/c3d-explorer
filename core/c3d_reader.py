"""C3D file reader utilizing ezc3d and native GRW calculation."""

import os
from typing import Optional, List, Dict, Any
import numpy as np

try:
    import ezc3d
    EZC3D_AVAILABLE = True
except ImportError:
    EZC3D_AVAILABLE = False

from core.data_models import C3DTrial, ForcePlatformData, C3DEvent
from core.grw_calculator import compute_ground_reaction_wrenches


def get_event_color(label: str, context: str) -> str:
    """Return a color for an event based on context and label."""
    norm = (label + " " + context).lower()
    if "right" in norm or norm.startswith("r_"):
        if "strike" in norm or "contact" in norm or "hs" in norm:
            return "#E53935"  # Vivid Red (Right Foot Strike)
        elif "off" in norm or "to" in norm:
            return "#FB8C00"  # Orange (Right Foot Off)
        return "#FF7043"
    elif "left" in norm or norm.startswith("l_"):
        if "strike" in norm or "contact" in norm or "hs" in norm:
            return "#1E88E5"  # Vivid Blue (Left Foot Strike)
        elif "off" in norm or "to" in norm:
            return "#00ACC1"  # Cyan (Left Foot Off)
        return "#42A5F5"
    else:
        # General / Event
        if "start" in norm:
            return "#43A047"  # Green
        elif "end" in norm or "stop" in norm:
            return "#8E24AA"  # Purple
        return "#FDD835"      # Amber


class C3DReader:
    """Reads C3D files using ezc3d and builds C3DTrial models."""

    @staticmethod
    def is_available() -> bool:
        return EZC3D_AVAILABLE

    @classmethod
    def read(cls, file_path: str) -> C3DTrial:
        """Parse a C3D file from disk using ezc3d."""
        if not cls.is_available():
            raise RuntimeError(
                "ezc3d is not installed. Please install it with 'pip install ezc3d'."
            )

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read acquisition with force platform computation enabled
        try:
            c = ezc3d.c3d(file_path, extract_forceplat_data=True)
        except Exception:
            # Fallback if strict extraction fails on malformed files
            c = ezc3d.c3d(file_path, extract_forceplat_data=False, ignore_bad_formatting=True)

        if c is None:
            raise ValueError(f"Failed to load C3D acquisition from {file_path}")

        # Frame and sample rate properties
        first_frame = int(c['header']['points']['first_frame'])
        last_frame = int(c['header']['points']['last_frame'])
        point_rate = float(c['header']['points']['frame_rate'])

        # Points shape in ezc3d is (4, n_points, n_frames) -> (X, Y, Z, residual)
        points_data = c['data']['points']
        if points_data.ndim >= 3:
            point_frame_count = int(points_data.shape[2])
        else:
            point_frame_count = max(0, last_frame - first_frame + 1)

        # Analog properties
        analog_rate = 0.0
        analog_frame_count = 0
        if 'analogs' in c['header']:
            analog_rate = float(c['header']['analogs']['frame_rate'])
        if 'analogs' in c['data'] and c['data']['analogs'].ndim >= 3:
            analog_frame_count = int(c['data']['analogs'].shape[2])

        analog_subsamples = int(round(analog_rate / point_rate)) if point_rate > 0 and analog_rate > 0 else 0

        # Markers
        markers_dict: Dict[str, np.ndarray] = {}
        marker_units = "mm"
        try:
            if 'POINT' in c['parameters']:
                point_params = c['parameters']['POINT']
                labels = point_params.get('LABELS', {}).get('value', [])
                units_val = point_params.get('UNITS', {}).get('value', ['mm'])
                if isinstance(units_val, (list, tuple)) and len(units_val) > 0:
                    marker_units = str(units_val[0]).strip()
                elif isinstance(units_val, str):
                    marker_units = units_val.strip()

                for idx, lbl in enumerate(labels):
                    clean_name = str(lbl).strip()
                    if idx < points_data.shape[1]:
                        # Extract 3D coordinates (n_frames, 3)
                        markers_dict[clean_name] = np.ascontiguousarray(
                            points_data[:3, idx, :].T, dtype=np.float32
                        )
        except Exception as e:
            print(f"Warning parsing markers with ezc3d: {e}")

        # Analogs
        analogs_dict: Dict[str, np.ndarray] = {}
        analog_units: Dict[str, str] = {}
        try:
            if 'ANALOG' in c['parameters'] and 'analogs' in c['data'] and c['data']['analogs'].ndim >= 3:
                analog_params = c['parameters']['ANALOG']
                a_labels = analog_params.get('LABELS', {}).get('value', [])
                a_units = analog_params.get('UNITS', {}).get('value', [])
                a_data = c['data']['analogs'][0]  # shape (n_analogs, n_analog_frames)

                for idx, lbl in enumerate(a_labels):
                    clean_name = str(lbl).strip()
                    if idx < a_data.shape[0]:
                        analogs_dict[clean_name] = np.ascontiguousarray(a_data[idx, :], dtype=np.float32)
                        if isinstance(a_units, (list, tuple)) and idx < len(a_units):
                            analog_units[clean_name] = str(a_units[idx]).strip()
                        else:
                            analog_units[clean_name] = "V"
        except Exception as e:
            print(f"Warning parsing analogs with ezc3d: {e}")

        # Force Platforms & Ground Reaction Wrenches (Forces, Moments, Center of Pressure)
        force_platforms: List[ForcePlatformData] = []
        try:
            # Compute Ground Reaction Wrenches using Shimba (1984) algorithm with 10N threshold
            python_grw = compute_ground_reaction_wrenches(c, threshold=10.0)

            # Read parameters from FORCE_PLATFORM parameter group
            fp_params = c['parameters'].get('FORCE_PLATFORM', {})
            n_fp = int(fp_params.get('USED', {}).get('value', [0])[0]) if 'USED' in fp_params else len(python_grw)
            types = np.atleast_1d(fp_params.get('TYPE', {}).get('value', [1]))
            corners_all = fp_params.get('CORNERS', {}).get('value')
            origins_all = fp_params.get('ORIGIN', {}).get('value')
            channels_all = fp_params.get('CHANNEL', {}).get('value')
            cal_mats = fp_params.get('CAL_MATRIX', {}).get('value')

            for i in range(max(n_fp, len(python_grw))):
                fp_type = int(types[i]) if i < len(types) else (python_grw[i]['type'] if i < len(python_grw) else 1)

                # Corners
                if corners_all is not None:
                    corners = corners_all[:, :, i] if corners_all.ndim == 3 else corners_all
                elif i < len(python_grw) and 'corners' in python_grw[i]:
                    corners = python_grw[i]['corners']
                else:
                    corners = np.zeros((3, 4))

                # Origin
                if origins_all is not None:
                    origin = origins_all[:, i] if origins_all.ndim == 2 else origins_all
                elif i < len(python_grw) and 'origin' in python_grw[i]:
                    origin = python_grw[i]['origin']
                else:
                    origin = np.zeros(3)

                # Channel map
                chan_map = {}
                if channels_all is not None:
                    ch_col = channels_all[:, i] if channels_all.ndim == 2 else channels_all
                    for ch_idx, ch_num in enumerate(ch_col):
                        c_num_int = int(ch_num)
                        if 1 <= c_num_int <= len(analogs_dict):
                            ch_lbl = list(analogs_dict.keys())[c_num_int - 1]
                            chan_map[f"Ch_{ch_idx+1}"] = analogs_dict[ch_lbl]

                # Forces, Moments, COP from Shimba algorithm
                forces = None
                moments = None
                cop = None

                if i < len(python_grw):
                    grw = python_grw[i]
                    forces = grw['F']
                    moments = grw['M']
                    cop = grw['P']

                # Calibration Matrix
                cal_mat = None
                if cal_mats is not None:
                    if cal_mats.ndim == 3 and i < cal_mats.shape[2]:
                        cal_mat = cal_mats[:, :, i]
                    elif cal_mats.ndim == 2:
                        cal_mat = cal_mats

                force_platforms.append(ForcePlatformData(
                    id=i + 1,
                    type=fp_type,
                    corners=np.array(corners, dtype=np.float32),
                    origin=np.array(origin, dtype=np.float32),
                    channels=chan_map,
                    forces=forces,
                    moments=moments,
                    cop=cop,
                    cal_matrix=cal_mat
                ))
        except Exception as e:
            print(f"Warning parsing force platforms with ezc3d: {e}")

        # Events
        events_list: List[C3DEvent] = []
        try:
            if 'EVENT' in c['parameters']:
                ev_group = c['parameters']['EVENT']
                n_events = int(ev_group.get('USED', {}).get('value', [0])[0]) if 'USED' in ev_group else 0
                labels = ev_group.get('LABELS', {}).get('value', [])
                contexts = ev_group.get('CONTEXTS', {}).get('value', [])
                times_arr = ev_group.get('TIMES', {}).get('value', None)
                descs = ev_group.get('DESCRIPTIONS', {}).get('value', [])
                subjects = ev_group.get('SUBJECTS', {}).get('value', [])
                icon_ids = ev_group.get('ICON_IDS', {}).get('value', [])

                actual_n = min(n_events, len(labels)) if n_events > 0 else len(labels)
                for i in range(actual_n):
                    lbl_str = str(labels[i]).strip() if i < len(labels) else ""
                    ctx_str = str(contexts[i]).strip() if i < len(contexts) else ""
                    desc_str = str(descs[i]).strip() if i < len(descs) else ""
                    subj_str = str(subjects[i]).strip() if i < len(subjects) else ""
                    ev_id = int(icon_ids[i]) if i < len(icon_ids) else 0

                    # Time calculation: in C3D/ezc3d, TIMES is a 2xN array (row 0: min, row 1: sec)
                    t_val = 0.0
                    if times_arr is not None:
                        if times_arr.ndim == 2 and times_arr.shape[0] >= 2 and i < times_arr.shape[1]:
                            t_val = float(times_arr[0, i] * 60.0 + times_arr[1, i])
                        elif times_arr.ndim == 1 and i < len(times_arr):
                            t_val = float(times_arr[i])

                    # Calculate relative frame index (0-based)
                    frame_idx = int(round(t_val * point_rate)) if point_rate > 0 else 0
                    frame_idx = max(0, min(point_frame_count - 1, frame_idx))

                    # Context inference
                    if not ctx_str:
                        lower = lbl_str.lower()
                        if "right" in lower or lower.startswith("r_"):
                            ctx_str = "Right"
                        elif "left" in lower or lower.startswith("l_"):
                            ctx_str = "Left"
                        else:
                            ctx_str = "General"

                    # Infer standard event ID if 0
                    if ev_id == 0:
                        lower = lbl_str.lower()
                        if "strike" in lower or "contact" in lower or "hs" in lower:
                            ev_id = 1
                        elif "off" in lower or "to" in lower:
                            ev_id = 2

                    color = get_event_color(lbl_str, ctx_str)
                    events_list.append(C3DEvent(
                        name=lbl_str,
                        time=t_val,
                        frame=frame_idx,
                        subject=subj_str,
                        context=ctx_str,
                        description=desc_str,
                        event_id=ev_id,
                        icon_color=color
                    ))
        except Exception as e:
            print(f"Warning parsing events with ezc3d: {e}")

        # Sort events chronologically
        events_list.sort(key=lambda ev: ev.time)

        # Metadata tree
        metadata_tree: Dict[str, Any] = {}
        try:
            for g_name, grp in c['parameters'].items():
                if not g_name:
                    continue
                g_dict = {'description': grp.get('description', ''), 'parameters': {}}
                for p_name, param in grp.items():
                    if p_name in ('description', 'is_locked'):
                        continue
                    if isinstance(param, dict) and 'value' in param:
                        g_dict['parameters'][p_name] = {
                            'values': param['value'],
                            'description': param.get('description', '')
                        }
                metadata_tree[g_name] = g_dict
        except Exception as e:
            print(f"Warning parsing metadata with ezc3d: {e}")

        return C3DTrial(
            file_path=file_path,
            first_frame=first_frame,
            last_frame=last_frame,
            point_rate=point_rate,
            point_frame_count=point_frame_count,
            analog_rate=analog_rate,
            analog_frame_count=analog_frame_count,
            analog_subsamples=analog_subsamples,
            markers=markers_dict,
            marker_units=marker_units,
            analogs=analogs_dict,
            analog_units=analog_units,
            force_platforms=force_platforms,
            events=events_list,
            metadata=metadata_tree,
            btk_handle=c  # Stores ezc3d object reference for saving/exporting
        )

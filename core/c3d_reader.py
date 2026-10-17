"""C3D file reader utilizing moveck_bridge_btk."""

import os
from typing import Optional, List, Dict, Any
import numpy as np

try:
    import moveck_bridge_btk as btk
    BTK_AVAILABLE = True
except ImportError:
    try:
        import btk
        BTK_AVAILABLE = True
    except ImportError:
        BTK_AVAILABLE = False

from core.data_models import C3DTrial, ForcePlatformData, C3DEvent


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
    """Reads C3D files using moveck_bridge_btk and builds C3DTrial models."""

    @staticmethod
    def is_available() -> bool:
        return BTK_AVAILABLE

    @classmethod
    def read(cls, file_path: str) -> C3DTrial:
        """Parse a C3D file from disk."""
        if not cls.is_available():
            raise RuntimeError(
                "moveck_bridge_btk is not installed. Please install it with 'pip install moveck_bridge_btk'."
            )
        
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read acquisition
        acq = btk.btkReadAcquisition(file_path)
        if acq is None:
            raise ValueError(f"Failed to load C3D acquisition from {file_path}")

        # Frame and sample rate properties
        first_frame = int(btk.btkGetFirstFrame(acq))
        last_frame = int(btk.btkGetLastFrame(acq))
        point_rate = float(btk.btkGetPointFrequency(acq))
        point_frame_count = int(btk.btkGetPointFrameNumber(acq))
        
        # Analog properties
        try:
            analog_rate = float(btk.btkGetAnalogFrequency(acq))
            analog_frame_count = int(btk.btkGetAnalogFrameNumber(acq))
        except Exception:
            analog_rate = 0.0
            analog_frame_count = 0
            
        analog_subsamples = int(btk.btkGetAnalogSampleNumberPerFrame(acq)) if hasattr(btk, 'btkGetAnalogSampleNumberPerFrame') else 0
        if analog_subsamples <= 0 and point_rate > 0 and analog_rate > 0:
            analog_subsamples = int(round(analog_rate / point_rate))

        # Markers
        markers_dict: Dict[str, np.ndarray] = {}
        marker_units = "mm"
        try:
            raw_markers = btk.btkGetMarkers(acq)
            if isinstance(raw_markers, (list, tuple)) and len(raw_markers) > 0:
                if isinstance(raw_markers[0], dict):
                    markers_dict = raw_markers[0]
                if len(raw_markers) > 1 and isinstance(raw_markers[1], dict):
                    units_map = raw_markers[1].get('units', {})
                    if isinstance(units_map, dict):
                        marker_units = units_map.get('ALLMARKERS', marker_units)
                    elif isinstance(units_map, str):
                        marker_units = units_map
        except Exception as e:
            print(f"Warning parsing markers: {e}")

        # Analogs
        analogs_dict: Dict[str, np.ndarray] = {}
        analog_units: Dict[str, str] = {}
        try:
            raw_analogs = btk.btkGetAnalogs(acq)
            if isinstance(raw_analogs, (list, tuple)) and len(raw_analogs) > 0:
                if isinstance(raw_analogs[0], dict):
                    analogs_dict = raw_analogs[0]
                if len(raw_analogs) > 1 and isinstance(raw_analogs[1], dict):
                    analog_units = raw_analogs[1].get('units', {})
        except Exception as e:
            print(f"Warning parsing analogs: {e}")

        # Ground Reaction Wrenches (Forces, Moments, Center of Pressure)
        grw_list = []
        try:
            raw_grw = btk.btkGetGroundReactionWrenches(acq)
            if isinstance(raw_grw, (list, tuple, np.ndarray)):
                for item in raw_grw:
                    if isinstance(item, dict):
                        grw_list.append(item)
        except Exception as e:
            print(f"Warning calculating ground reaction wrenches: {e}")

        # Force Platforms
        force_platforms: List[ForcePlatformData] = []
        try:
            raw_fps = btk.btkGetForcePlatforms(acq)
            if isinstance(raw_fps, (list, tuple, np.ndarray)) and len(raw_fps) > 0:
                fp_items = raw_fps[0] if isinstance(raw_fps[0], (list, np.ndarray)) else raw_fps
                for i, fp_dict in enumerate(fp_items):
                    if not isinstance(fp_dict, dict):
                        continue
                    
                    corners = fp_dict.get('corners', np.zeros((3, 4)))
                    origin = fp_dict.get('origin', np.zeros((3,)))
                    fp_type = int(fp_dict.get('type', 1))
                    channels = fp_dict.get('channels', {})
                    
                    # Extract forces / moments / COP if available from GRW
                    forces = None
                    moments = None
                    cop = None
                    if i < len(grw_list):
                        forces = grw_list[i].get('F')
                        moments = grw_list[i].get('M')
                        cop = grw_list[i].get('P')

                    cal_mat = None
                    if len(raw_fps) > 1 and i < len(raw_fps[1]):
                        sub_dict = raw_fps[1][i]
                        if isinstance(sub_dict, list) and len(sub_dict) > 0:
                            sub_dict = sub_dict[0]
                        if isinstance(sub_dict, dict):
                            cal_mat = sub_dict.get('cal_matrix')

                    fp_data = ForcePlatformData(
                        id=i + 1,
                        type=fp_type,
                        corners=np.array(corners, dtype=np.float32),
                        origin=np.array(origin, dtype=np.float32),
                        channels=channels if isinstance(channels, dict) else {},
                        forces=forces,
                        moments=moments,
                        cop=cop,
                        cal_matrix=cal_mat
                    )
                    force_platforms.append(fp_data)
        except Exception as e:
            print(f"Warning parsing force platforms: {e}")

        # Events
        events_list: List[C3DEvent] = []
        try:
            subj_map = {}
            try:
                raw_ev = btk.btkGetEvents(acq)
                if isinstance(raw_ev, (list, tuple)) and len(raw_ev) > 1 and isinstance(raw_ev[1], dict):
                    subj_map = raw_ev[1].get("subject", {})
            except Exception:
                pass

            ev_values = btk.btkGetEventsValues(acq)
            if isinstance(ev_values, (list, tuple)) and len(ev_values) >= 2:
                labels = ev_values[1] if hasattr(ev_values[1], "__len__") else []
                raw_times = np.atleast_1d(ev_values[0]) if ev_values[0] is not None else np.array([])
                n_events = min(len(raw_times), len(labels))
                descriptions = ev_values[2] if len(ev_values) > 2 and hasattr(ev_values[2], "__len__") else [""] * n_events
                event_ids = ev_values[3] if len(ev_values) > 3 and hasattr(ev_values[3], "__len__") else [0] * n_events
                
                for i in range(n_events):
                    t_val = float(raw_times[i])
                    lbl_str = str(labels[i]).strip()
                    desc_str = str(descriptions[i]).strip() if i < len(descriptions) else ""
                    ev_id = int(event_ids[i]) if i < len(event_ids) else 0
                    subj_str = str(subj_map.get(lbl_str, "")).strip()
                    
                    # Compute relative frame (clamped)
                    frame_idx = int(round(t_val * point_rate)) if point_rate > 0 else 0
                    frame_idx = max(0, min(point_frame_count - 1, frame_idx))
                    
                    # Determine context (Right, Left, General)
                    context = ""
                    lower = lbl_str.lower()
                    if "right" in lower or lower.startswith("r_"):
                        context = "Right"
                    elif "left" in lower or lower.startswith("l_"):
                        context = "Left"
                    else:
                        context = "General"

                    # Infer Moveck standard event ID (1=Foot Strike, 2=Foot Off, 0=General) if unassigned
                    if ev_id == 0:
                        if "strike" in lower or "contact" in lower or "hs" in lower:
                            ev_id = 1
                        elif "off" in lower or "to" in lower:
                            ev_id = 2

                    color = get_event_color(lbl_str, context)
                    events_list.append(C3DEvent(
                        name=lbl_str,
                        time=t_val,
                        frame=frame_idx,
                        subject=subj_str,
                        context=context,
                        description=desc_str,
                        event_id=ev_id,
                        icon_color=color
                    ))
            else:
                # Fallback to btkGetEvents dict
                raw_events = btk.btkGetEvents(acq)
                if isinstance(raw_events, (list, tuple)) and len(raw_events) > 0 and isinstance(raw_events[0], dict):
                    for lbl, t_val in raw_events[0].items():
                        t_float = float(t_val)
                        frame_idx = int(round(t_float * point_rate)) if point_rate > 0 else 0
                        frame_idx = max(0, min(point_frame_count - 1, frame_idx))
                        lbl_lower = lbl.lower()
                        context = "Right" if "right" in lbl_lower else ("Left" if "left" in lbl_lower else "General")
                        ev_id = 0
                        if "strike" in lbl_lower or "contact" in lbl_lower or "hs" in lbl_lower:
                            ev_id = 1
                        elif "off" in lbl_lower or "to" in lbl_lower:
                            ev_id = 2
                        color = get_event_color(lbl, context)
                        events_list.append(C3DEvent(
                            name=lbl,
                            time=t_float,
                            frame=frame_idx,
                            subject="",
                            context=context,
                            event_id=ev_id,
                            icon_color=color
                        ))
        except Exception as e:
            print(f"Warning parsing events: {e}")

        # Sort events chronologically
        events_list.sort(key=lambda ev: ev.time)

        # Metadata
        metadata_tree: Dict[str, Any] = {}
        try:
            raw_meta = btk.btkGetMetaData(acq)
            if isinstance(raw_meta, dict):
                metadata_tree = raw_meta
        except Exception as e:
            print(f"Warning parsing metadata: {e}")

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
            btk_handle=acq
        )

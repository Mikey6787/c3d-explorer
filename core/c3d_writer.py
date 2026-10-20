"""Writers and exporters for C3D, CSV, and STL files utilizing ezc3d."""

import os
import struct
import copy
import re
from typing import List, Optional, Dict, Any
import numpy as np

try:
    import ezc3d
    EZC3D_AVAILABLE = True
except ImportError:
    EZC3D_AVAILABLE = False

from core.data_models import C3DTrial, deduplicate_events


def make_c3d_4char_label(name: str, context: str = "") -> str:
    """
    Generate a clean, standard 4-character C3D event label for header storage (Words 199-234).
    Uses standard biomechanics gait abbreviations (e.g. RHS, LTO, RFS, LFO)
    or cleanly formats arbitrary event labels into 4 characters.
    """
    clean_name = (name or "").strip()
    norm = clean_name.lower()
    norm_ctx = (context or "").strip().lower()

    # Determine context prefix ('R' or 'L')
    prefix = ""
    if "right" in norm_ctx or norm.startswith("r_") or norm.startswith("r ") or norm.startswith("right"):
        prefix = "R"
    elif "left" in norm_ctx or norm.startswith("l_") or norm.startswith("l ") or norm.startswith("left"):
        prefix = "L"

    tokens = set(re.split(r"[\s_\-]+", norm))
    is_strike = ("heel" in norm or "strike" in norm or "contact" in norm or
                 any(t in tokens for t in ("hs", "fs")))
    is_off = ("toe" in norm or "off" in norm or
              any(t in tokens for t in ("to", "fo")))

    if is_strike:
        return f"{prefix}HS " if prefix else "FS  "
    elif is_off:
        return f"{prefix}TO " if prefix else "FO  "
    elif "start" in tokens or "start" in norm:
        return "STRT"
    elif "stop" in tokens or "end" in tokens or "stop" in norm:
        return "STOP"

    # Strip context prefix if already present in name
    if prefix and (clean_name.upper().startswith(f"{prefix}_") or clean_name.upper().startswith(f"{prefix} ")):
        clean_name = clean_name[2:].strip()

    if len(clean_name) <= 4:
        return clean_name.ljust(4)

    if prefix:
        short = clean_name.replace(" ", "").replace("_", "")
        return f"{prefix}{short[:3]}".ljust(4)

    condensed = clean_name.replace(" ", "").replace("_", "")
    return (condensed[:4] if len(condensed) >= 4 else clean_name[:4]).ljust(4)


class C3DWriter:
    """Handles saving C3D trials and exporting to CSV and STL formats using ezc3d."""

    @classmethod
    def _sync_header_events(cls, file_path: str) -> None:
        """
        Ensure the C3D Header event table (Words 150-234, bytes 298-468) has Word 151 = 0.
        According to the C3D specification, when the modern EVENT parameter group is populated,
        Header Word 151 must be 0. This prevents dual-interpreting readers (such as BTK and Mokka)
        from instantiating duplicate 4-character abbreviation events in the 'General' context.
        """
        if not os.path.isfile(file_path):
            return

        try:
            with open(file_path, "r+b") as fp:
                # Seek to Word 150 (byte offset 298)
                fp.seek(298)

                # Word 150: Key value 12345 (0x3039) indicates support for 4-character event labels
                fp.write(struct.pack("<H", 12345))

                # Word 151: Set to 0 to prevent dual-interpreting readers (BTK/Mokka) from creating duplicate General-context events
                fp.write(struct.pack("<H", 0))

                # Word 152: Reserved (0)
                fp.write(struct.pack("<H", 0))

                # Words 153-188: 18 event times as 32-bit float (0.0)
                for _ in range(18):
                    fp.write(struct.pack("<f", 0.0))

                # Words 189-197: 18 event display flags (1 byte each, 0x00 = ON)
                for _ in range(18):
                    fp.write(b"\x00")

                # Word 198: Reserved (0)
                fp.write(struct.pack("<H", 0))

                # Words 199-234: 18 event labels (4 spaces each)
                for _ in range(18):
                    fp.write(b"    ")
        except Exception as e:
            print(f"Warning synchronizing C3D header events: {e}")

    @classmethod
    def save_c3d(
        cls,
        trial: C3DTrial,
        output_path: str,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None
    ) -> None:
        """
        Save acquisition back to C3D format using ezc3d.
        Supports:
        - Newly created markers (e.g. from average marker tools)
        - Renamed and modified markers
        - Discrete C3D events
        - Slicing and exporting trimmed frame ranges [start_frame, end_frame]
        - Force platform parameter and channel preservation
        """
        if not EZC3D_AVAILABLE:
            raise RuntimeError("ezc3d is required to write C3D files. Please install it with 'pip install ezc3d'.")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        total_frames = max(1, trial.point_frame_count)
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = total_frames - 1

        start_frame = max(0, min(total_frames - 1, start_frame))
        end_frame = max(start_frame, min(total_frames - 1, end_frame))
        trim_frames = end_frame - start_frame + 1

        # Check if we have an existing ezc3d handle or trial file
        if trial.btk_handle is not None and isinstance(trial.btk_handle, (ezc3d.c3d, dict)):
            c = copy.deepcopy(trial.btk_handle)
        elif trial.file_path and os.path.isfile(trial.file_path):
            c = ezc3d.c3d(trial.file_path)
        else:
            # Create a brand new C3D file
            c = ezc3d.c3d()
            c['header']['points']['frame_rate'] = float(trial.point_rate)
            c['parameters']['POINT']['RATE']['value'] = [float(trial.point_rate)]

        # 1. Synchronize Markers
        marker_names = list(trial.markers.keys())
        num_markers = len(marker_names)

        # Build 3D points array: shape (4, num_markers, trim_frames)
        new_pts = np.zeros((4, num_markers, trim_frames), dtype=np.float64)
        for idx, name in enumerate(marker_names):
            m_data = trial.markers[name]
            sliced = m_data[start_frame:end_frame + 1, :]
            new_pts[:3, idx, :] = sliced.T
            new_pts[3, idx, :] = 0.0  # Residual = 0 (valid marker point)

        c['data']['points'] = new_pts
        c['parameters']['POINT']['LABELS']['value'] = marker_names
        c['parameters']['POINT']['USED']['value'] = [num_markers]
        c['parameters']['POINT']['FRAMES']['value'] = [trim_frames]
        if 'meta_points' in c['data']:
            del c['data']['meta_points']

        # 2. Synchronize Analogs
        sub = max(1, trial.analog_subsamples)
        analog_start = start_frame * sub
        analog_end = (end_frame + 1) * sub
        trim_analog_frames = trim_frames * sub

        if trial.analogs:
            a_names = list(trial.analogs.keys())
            num_analogs = len(a_names)
            new_analogs = np.zeros((1, num_analogs, trim_analog_frames), dtype=np.float64)
            for idx, name in enumerate(a_names):
                a_data = trial.analogs[name]
                sliced_a = a_data[analog_start:min(len(a_data), analog_end)]
                new_analogs[0, idx, :len(sliced_a)] = sliced_a
            c['data']['analogs'] = new_analogs
            if 'ANALOG' in c['parameters']:
                if 'LABELS' in c['parameters']['ANALOG']:
                    c['parameters']['ANALOG']['LABELS']['value'] = a_names
                if 'USED' in c['parameters']['ANALOG']:
                    c['parameters']['ANALOG']['USED']['value'] = [num_analogs]
        elif 'analogs' in c['data'] and c['data']['analogs'].ndim >= 3 and c['data']['analogs'].shape[2] > 0:
            orig_analog_frames = c['data']['analogs'].shape[2]
            actual_end = min(orig_analog_frames, analog_end)
            actual_start = min(orig_analog_frames, analog_start)
            c['data']['analogs'] = c['data']['analogs'][:, :, actual_start:actual_end]

        # 3. Synchronize Frame Range in Header
        orig_first = trial.first_frame
        new_first_frame = int(orig_first + start_frame)
        new_last_frame = int(orig_first + end_frame)

        c['header']['points']['first_frame'] = new_first_frame
        c['header']['points']['last_frame'] = new_last_frame
        c['header']['points']['frame_rate'] = float(trial.point_rate)

        # Synchronize TRIAL group if present (read by BTK / Mokka to set first and last frames)
        if 'TRIAL' in c['parameters']:
            if 'ACTUAL_START_FIELD' in c['parameters']['TRIAL']:
                hsb = new_first_frame >> 16
                lsb = new_first_frame & 0xFFFF
                c['parameters']['TRIAL']['ACTUAL_START_FIELD']['value'] = [lsb, hsb]
            if 'ACTUAL_END_FIELD' in c['parameters']['TRIAL']:
                hsb = new_last_frame >> 16
                lsb = new_last_frame & 0xFFFF
                c['parameters']['TRIAL']['ACTUAL_END_FIELD']['value'] = [lsb, hsb]

        if 'POINT' in c['parameters']:
            c['parameters']['POINT']['FRAMES']['value'] = [trim_frames]
            if 'LONG_FRAMES' in c['parameters']['POINT']:
                c['parameters']['POINT']['LONG_FRAMES']['value'] = [float(trim_frames)]

        if 'PROCESSING' in c['parameters']:
            if 'Cropped Measurement Start Frame' in c['parameters']['PROCESSING']:
                c['parameters']['PROCESSING']['Cropped Measurement Start Frame']['value'] = [float(new_first_frame)]
            if 'Cropped Measurement End Frame' in c['parameters']['PROCESSING']:
                c['parameters']['PROCESSING']['Cropped Measurement End Frame']['value'] = [float(new_last_frame)]

        # 4. Synchronize Force Platform parameters if created from scratch
        if 'FORCE_PLATFORM' not in c['parameters'] and trial.force_platforms:
            num_fp = len(trial.force_platforms)
            c.add_parameter("FORCE_PLATFORM", "USED", [num_fp])
            c.add_parameter("FORCE_PLATFORM", "TYPE", [fp.type for fp in trial.force_platforms])
            c.add_parameter("FORCE_PLATFORM", "ZERO", [1, 0])
            corners_arr = np.zeros((3, 4, num_fp), dtype=np.float32)
            origins_arr = np.zeros((3, num_fp), dtype=np.float32)
            for i, fp in enumerate(trial.force_platforms):
                corners_arr[:, :, i] = fp.corners
                origins_arr[:, i] = fp.origin
            c.add_parameter("FORCE_PLATFORM", "CORNERS", corners_arr)
            c.add_parameter("FORCE_PLATFORM", "ORIGIN", origins_arr)

        # 5. Synchronize Events
        if 'EVENT' in c['parameters']:
            del c['parameters']['EVENT']

        # Remove duplicate events (e.g. redundant abbreviations or duplicate entries)
        trial.events = deduplicate_events(trial.events, trial.point_rate)

        for ev in trial.events:
            ev_frame = ev.frame if (ev.frame is not None and ev.frame >= 0) else int(round(ev.time * trial.point_rate))
            if start_frame <= ev_frame <= end_frame:
                rel_frame = ev_frame - start_frame

                # In C3D format (BTK, Mokka, Vicon Nexus):
                # An event's frame on the timeline ruler is: ruler_frame = new_first_frame + rel_frame
                # BTK / Mokka reconstructs the event frame as: frame = floor(time * point_rate + 1.5)
                # Therefore, time in C3D must be: time = (ruler_frame - 1) / point_rate
                # When new_first_frame > 1 (e.g. 1856, or 21 when 1-based trimmed):
                # c3d_event_time = (new_first_frame + rel_frame - 1) / point_rate
                # When new_first_frame <= 1 (e.g. 0-based indexing):
                # c3d_event_time = rel_frame / point_rate
                if new_first_frame > 1:
                    c3d_event_time = float(new_first_frame + rel_frame - 1) / trial.point_rate if trial.point_rate > 0 else 0.0
                else:
                    c3d_event_time = float(rel_frame) / trial.point_rate if trial.point_rate > 0 else 0.0

                ctx = ev.context.strip() if ev.context else "General"
                lbl = (ev.name or "").strip()
                if not lbl:
                    lbl = "Event"

                # Normalize label if redundant with context (e.g. "Left Foot Off" in "Left" context -> "Foot Off")
                if lbl.lower().startswith(ctx.lower()):
                    lbl_clean = lbl[len(ctx):].lstrip(" _-")
                    if lbl_clean:
                        lbl = lbl_clean

                # Non-empty description and subject to prevent ezc3d dimension collapsing
                desc = getattr(ev, "description", "") or " "
                subj = getattr(ev, "subject", "") or " "
                ev_id = getattr(ev, "event_id", 0) or 0

                minutes = int(c3d_event_time // 60)
                seconds = float(c3d_event_time % 60)
                c.add_event(
                    time=[minutes, seconds],
                    context=ctx,
                    label=lbl,
                    description=desc,
                    subject=subj,
                    icon_id=int(ev_id)
                )

        # Write out C3D
        c.write(output_path)

        # 6. Ensure Header Word 151 = 0 to prevent external readers (Mokka, BTK) from generating duplicate General-context events
        cls._sync_header_events(output_path)

    @classmethod
    def export_markers_csv(
        cls,
        trial: C3DTrial,
        output_path: str,
        start_frame: int = 0,
        end_frame: Optional[int] = None
    ) -> None:
        """Export 3D marker trajectories (optionally trimmed) to a standard CSV file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if end_frame is None:
            end_frame = trial.point_frame_count - 1
        start_frame = max(0, min(trial.point_frame_count - 1, start_frame))
        end_frame = max(start_frame, min(trial.point_frame_count - 1, end_frame))

        marker_names = sorted(list(trial.markers.keys()))
        header = ["Frame", "Time_s"]
        for name in marker_names:
            header.extend([f"{name}_X", f"{name}_Y", f"{name}_Z"])

        rows = []
        for i in range(start_frame, end_frame + 1):
            t = trial.frame_to_time(i)
            row = [str(i), f"{t:.4f}"]
            for name in marker_names:
                pos = trial.markers[name][i]
                row.extend([f"{pos[0]:.4f}", f"{pos[1]:.4f}", f"{pos[2]:.4f}"])
            rows.append(",".join(row))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(",".join(header) + "\n")
            f.write("\n".join(rows) + "\n")

    @classmethod
    def export_analogs_csv(
        cls,
        trial: C3DTrial,
        output_path: str,
        start_frame: int = 0,
        end_frame: Optional[int] = None
    ) -> None:
        """Export analog and force channel signals (optionally trimmed) to CSV."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if end_frame is None:
            end_frame = trial.point_frame_count - 1
        start_frame = max(0, min(trial.point_frame_count - 1, start_frame))
        end_frame = max(start_frame, min(trial.point_frame_count - 1, end_frame))

        channel_names = sorted(list(trial.analogs.keys()))
        header = ["Sample", "Time_s"] + channel_names

        nsf = max(1, trial.analog_subsamples)
        start_sample = start_frame * nsf
        end_sample = min(trial.analog_frame_count, (end_frame + 1) * nsf)

        dt = 1.0 / trial.analog_rate if trial.analog_rate > 0 else 0.001
        rows = []
        for i in range(start_sample, end_sample):
            t = i * dt
            row = [str(i), f"{t:.5f}"]
            for ch in channel_names:
                val = trial.analogs[ch][i] if i < len(trial.analogs[ch]) else 0.0
                row.append(f"{val:.4f}")
            rows.append(",".join(row))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(",".join(header) + "\n")
            f.write("\n".join(rows) + "\n")

    @classmethod
    def export_stl(cls, trial: C3DTrial, output_path: str, frame_idx: int = 0) -> None:
        """
        Export 3D geometry of force plates and markers at the selected frame as a binary STL file.
        Each rectangular force plate is exported as two triangles (or a box with thickness).
        Each marker is exported as a 3D octahedron / sphere approximation.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        triangles: List[np.ndarray] = []

        # 1. Force plates geometry (top surface and 25mm thickness box)
        thickness = 25.0  # 25 mm plate depth downward
        for fp in trial.force_platforms:
            c = fp.corners  # Shape (3, 4)
            p0, p1, p2, p3 = c[:, 0], c[:, 1], c[:, 2], c[:, 3]
            # Top face (two triangles)
            triangles.append(np.array([p0, p1, p2]))
            triangles.append(np.array([p0, p2, p3]))
            # Bottom face (extruded -Z)
            b0 = p0 - np.array([0, 0, thickness])
            b1 = p1 - np.array([0, 0, thickness])
            b2 = p2 - np.array([0, 0, thickness])
            b3 = p3 - np.array([0, 0, thickness])
            triangles.append(np.array([b0, b2, b1]))
            triangles.append(np.array([b0, b3, b2]))
            # Sides
            triangles.append(np.array([p0, b0, b1]))
            triangles.append(np.array([p0, b1, p1]))
            triangles.append(np.array([p1, b1, b2]))
            triangles.append(np.array([p1, b2, p2]))
            triangles.append(np.array([p2, b2, b3]))
            triangles.append(np.array([p2, b3, p3]))
            triangles.append(np.array([p3, b3, b0]))
            triangles.append(np.array([p3, b0, p0]))

        # 2. Markers as small octahedrons (radius 10mm)
        r = 10.0
        for name, data in trial.markers.items():
            if frame_idx < len(data):
                center = data[frame_idx]
                if np.all(center == 0) or np.any(np.isnan(center)):
                    continue
                # 6 vertices of an octahedron
                px = center + np.array([r, 0, 0])
                nx = center - np.array([r, 0, 0])
                py = center + np.array([0, r, 0])
                ny = center - np.array([0, r, 0])
                pz = center + np.array([0, 0, r])
                nz = center - np.array([0, 0, r])

                # 8 triangular faces
                triangles.append(np.array([pz, px, py]))
                triangles.append(np.array([pz, py, nx]))
                triangles.append(np.array([pz, nx, ny]))
                triangles.append(np.array([pz, ny, px]))
                triangles.append(np.array([nz, py, px]))
                triangles.append(np.array([nz, nx, py]))
                triangles.append(np.array([nz, ny, nx]))
                triangles.append(np.array([nz, px, ny]))

        # Write binary STL
        with open(output_path, "wb") as f:
            # 80-byte header
            header_bytes = b"C3D Explorer Binary STL Export - Force Plates & Markers"
            header_bytes = header_bytes.ljust(80, b" ")
            f.write(header_bytes)
            # Number of triangles (uint32)
            f.write(struct.pack("<I", len(triangles)))

            for tri in triangles:
                v1, v2, v3 = tri[0], tri[1], tri[2]
                # Compute normal
                norm = np.cross(v2 - v1, v3 - v1)
                n_len = np.linalg.norm(norm)
                if n_len > 1e-6:
                    norm = norm / n_len
                else:
                    norm = np.array([0.0, 0.0, 1.0])

                # 50 bytes per triangle: normal (3 floats) + 3 vertices (9 floats) + 2 bytes attribute
                data = struct.pack(
                    "<12fH",
                    float(norm[0]), float(norm[1]), float(norm[2]),
                    float(v1[0]), float(v1[1]), float(v1[2]),
                    float(v2[0]), float(v2[1]), float(v2[2]),
                    float(v3[0]), float(v3[1]), float(v3[2]),
                    0
                )
                f.write(data)

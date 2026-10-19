"""Writers and exporters for C3D, CSV, and STL files utilizing ezc3d."""

import os
import struct
import copy
from typing import List, Optional
import numpy as np

try:
    import ezc3d
    EZC3D_AVAILABLE = True
except ImportError:
    EZC3D_AVAILABLE = False

from core.data_models import C3DTrial


class C3DWriter:
    """Handles saving C3D trials and exporting to CSV and STL formats using ezc3d."""

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

        if 'analogs' in c['data'] and c['data']['analogs'].ndim >= 3 and c['data']['analogs'].shape[2] > 0:
            orig_analog_frames = c['data']['analogs'].shape[2]
            actual_end = min(orig_analog_frames, analog_end)
            actual_start = min(orig_analog_frames, analog_start)
            c['data']['analogs'] = c['data']['analogs'][:, :, actual_start:actual_end]
        elif trial.analogs:
            a_names = list(trial.analogs.keys())
            num_analogs = len(a_names)
            new_analogs = np.zeros((1, num_analogs, trim_analog_frames), dtype=np.float64)
            for idx, name in enumerate(a_names):
                a_data = trial.analogs[name]
                sliced_a = a_data[analog_start:min(len(a_data), analog_end)]
                new_analogs[0, idx, :len(sliced_a)] = sliced_a
            c['data']['analogs'] = new_analogs
            c['parameters']['ANALOG']['LABELS']['value'] = a_names
            c['parameters']['ANALOG']['USED']['value'] = [num_analogs]

        # 3. Synchronize Frame Range in Header
        orig_first = trial.first_frame
        c['header']['points']['first_frame'] = int(orig_first + start_frame)
        c['header']['points']['last_frame'] = int(orig_first + end_frame)
        c['header']['points']['frame_rate'] = float(trial.point_rate)

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

        for ev in trial.events:
            if start_frame <= ev.frame <= end_frame:
                rel_frame = ev.frame - start_frame
                rel_time = rel_frame / trial.point_rate if trial.point_rate > 0 else 0.0

                ctx = ev.context if ev.context else "General"
                lbl = ev.name
                if lbl.lower().startswith(ctx.lower()):
                    lbl_clean = lbl[len(ctx):].lstrip(" _-")
                    if lbl_clean:
                        lbl = lbl_clean

                desc = getattr(ev, "description", "") or ""
                subj = getattr(ev, "subject", "") or ""
                ev_id = getattr(ev, "event_id", 0) or 0

                minutes = int(rel_time // 60)
                seconds = float(rel_time % 60)
                c.add_event(
                    time=[minutes, seconds],
                    context=ctx,
                    label=lbl,
                    description=desc,
                    subject=subj,
                    icon_id=ev_id
                )

        # Write out C3D
        c.write(output_path)

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

"""Writers and exporters for C3D, CSV, and STL files."""

import os
import struct
from typing import List, Optional
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

from core.data_models import C3DTrial


class C3DWriter:
    """Handles saving C3D trials and exporting to CSV and STL formats."""

    @classmethod
    def save_c3d(
        cls,
        trial: C3DTrial,
        output_path: str,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None
    ) -> None:
        """
        Save acquisition back to C3D format using moveck_bridge_btk.
        Supports:
        - Newly created markers (e.g. from average marker tools)
        - Renamed and modified markers
        - Discrete C3D events
        - Slicing and exporting trimmed frame ranges [start_frame, end_frame]
        """
        if not BTK_AVAILABLE:
            raise RuntimeError("moveck_bridge_btk is required to write C3D files.")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        total_frames = max(1, trial.point_frame_count)
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = total_frames - 1

        start_frame = max(0, min(total_frames - 1, start_frame))
        end_frame = max(start_frame, min(total_frames - 1, end_frame))

        is_trimmed = (start_frame > 0 or end_frame < total_frames - 1)

        if not is_trimmed:
            # -------------------------------------------------------------
            # Full Trial Save / Export
            # -------------------------------------------------------------
            acq = trial.btk_handle
            if acq is None:
                raise ValueError("No BTK acquisition handle available.")

            # 1. Synchronize point labels and values
            existing_count = int(btk.btkGetPointNumber(acq))
            existing_labels = {}
            for i in range(existing_count):
                try:
                    _, info = btk.btkGetPoint(acq, i)
                    existing_labels[i] = info.get('label', f'Point_{i}')
                except Exception:
                    existing_labels[i] = f'Point_{i}'

            markers_handled = set()
            # Update existing points matching trial markers
            for i in range(existing_count):
                old_lbl = existing_labels[i]
                if old_lbl in trial.markers:
                    try:
                        btk.btkSetPointValues(acq, i, np.asarray(trial.markers[old_lbl], dtype=np.float64))
                        markers_handled.add(old_lbl)
                    except Exception as e:
                        print(f"Warning updating point {old_lbl}: {e}")

            # For existing points that were renamed:
            unhandled_trial_markers = [m for m in trial.markers.keys() if m not in markers_handled]
            for i in range(existing_count):
                old_lbl = existing_labels[i]
                if old_lbl not in trial.markers and unhandled_trial_markers:
                    new_lbl = unhandled_trial_markers.pop(0)
                    try:
                        btk.btkSetPointLabel(acq, i, new_lbl)
                        btk.btkSetPointValues(acq, i, np.asarray(trial.markers[new_lbl], dtype=np.float64))
                        markers_handled.add(new_lbl)
                    except Exception as e:
                        print(f"Warning renaming point {old_lbl} -> {new_lbl}: {e}")

            # Append any remaining newly created markers
            for name, arr in trial.markers.items():
                if name not in markers_handled:
                    try:
                        btk.btkAppendPoint(acq, 'marker', name, np.asarray(arr, dtype=np.float64))
                    except Exception as e:
                        print(f"Warning appending new marker {name}: {e}")

            # 2. Synchronize discrete C3D events
            try:
                btk.btkClearEvents(acq)
                for ev in trial.events:
                    ctx = ev.context if ev.context else "General"
                    lbl = ev.name
                    if lbl.lower().startswith(ctx.lower()):
                        lbl_clean = lbl[len(ctx):].lstrip(" _-")
                        if lbl_clean:
                            lbl = lbl_clean

                    desc = getattr(ev, "description", "") or ""
                    subj = getattr(ev, "subject", "") or ""
                    btk.btkAppendEvent(
                        acq,
                        lbl,
                        float(ev.time),
                        ctx,
                        subj,
                        desc
                    )
            except Exception as e:
                print(f"Warning synchronizing events before saving C3D: {e}")

            btk.btkWriteAcquisition(acq, output_path)

        else:
            # -------------------------------------------------------------
            # Trimmed Region Export: slice to [start_frame, end_frame]
            # -------------------------------------------------------------
            trim_frames = end_frame - start_frame + 1
            num_markers = len(trial.markers)
            num_analogs = len(trial.analogs)
            nsf = max(1, trial.analog_subsamples)

            new_acq = btk.btkNewAcquisition(num_markers, trim_frames, num_analogs, nsf)
            btk.btkSetFrequency(new_acq, float(trial.point_rate))

            orig_first_frame = 1
            if trial.btk_handle:
                try:
                    orig_first_frame = int(btk.btkGetFirstFrame(trial.btk_handle))
                except Exception:
                    orig_first_frame = 1
            btk.btkSetFirstFrame(new_acq, orig_first_frame + start_frame)

            # Copy general metadata groups (MANUFACTURER, PROCESSING, etc.)
            if trial.btk_handle:
                try:
                    md = btk.btkGetMetaData(trial.btk_handle)
                    for grp_name, grp_data in md.get('children', {}).items():
                        if grp_name in ['POINT', 'ANALOG']:
                            continue
                        if isinstance(grp_data, dict) and isinstance(grp_data.get('children'), dict):
                            for p_name, p_data in grp_data['children'].items():
                                if isinstance(p_data, dict) and isinstance(p_data.get('info'), dict):
                                    info = dict(p_data['info'])
                                    val = info.get('values')
                                    if hasattr(val, 'shape'):
                                        info['dims'] = np.array(val.shape, dtype=np.int32)
                                    else:
                                        info['dims'] = np.array([], dtype=np.int32)
                                    try:
                                        btk.btkAppendMetaData(new_acq, grp_name, p_name, info)
                                    except Exception:
                                        pass
                except Exception as e:
                    print(f"Warning copying metadata to trimmed acquisition: {e}")

            # Populate sliced markers
            for idx, (name, arr) in enumerate(trial.markers.items()):
                sliced_marker = np.asarray(arr[start_frame:end_frame + 1, :], dtype=np.float64)
                btk.btkSetPointLabel(new_acq, idx, name)
                btk.btkSetPointValues(new_acq, idx, sliced_marker)

            # Populate sliced analogs
            analog_start = start_frame * nsf
            analog_end = (end_frame + 1) * nsf
            for idx, (name, arr) in enumerate(trial.analogs.items()):
                sliced_analog = np.asarray(arr[analog_start:analog_end], dtype=np.float64)
                if sliced_analog.ndim == 1:
                    sliced_analog = sliced_analog[:, np.newaxis]
                btk.btkSetAnalogLabel(new_acq, idx, name)
                btk.btkSetAnalogValues(new_acq, idx, sliced_analog)

            # Populate events within trim range
            try:
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
                        btk.btkAppendEvent(
                            new_acq,
                            lbl,
                            float(rel_time),
                            ctx,
                            subj,
                            desc
                        )
            except Exception as e:
                print(f"Warning copying events to trimmed acquisition: {e}")

            btk.btkWriteAcquisition(new_acq, output_path)

        # Ensure force platform geometry & metadata are preserved in the exported C3D file
        if trial.force_platforms:
            cls._preserve_force_platforms(trial, output_path)

    @classmethod
    def _preserve_force_platforms(cls, trial: C3DTrial, output_path: str) -> None:
        """
        Ensure the exported C3D file at output_path preserves all force platform parameters
        (geometry, corners, origin, channel mappings, calibration matrices) from the original trial.
        """
        if not trial.force_platforms or not os.path.exists(output_path):
            return

        try:
            with open(output_path, "rb") as f:
                written_data = f.read()

            w_header = bytearray(written_data[:512])
            w_pblock = w_header[0]
            w_dblock = struct.unpack("<H", w_header[16:18])[0]
            w_pstart = (w_pblock - 1) * 512
            w_pend = (w_dblock - 1) * 512
            w_pdata = written_data[w_pstart:w_pend]
            data_section = written_data[w_pend:]

            idx = 4
            w_fp_gid = None
            kept_entries = []
            has_valid_fp = False

            while idx < len(w_pdata):
                if idx + 2 > len(w_pdata):
                    break
                entry_start = idx
                name_len = struct.unpack("b", w_pdata[idx:idx+1])[0]
                group_id = struct.unpack("b", w_pdata[idx+1:idx+2])[0]
                idx += 2
                if name_len == 0:
                    break
                abs_len = abs(name_len)
                name = w_pdata[idx:idx+abs_len].decode("ascii", errors="ignore").upper()
                idx += abs_len
                offset = struct.unpack("<h", w_pdata[idx:idx+2])[0]
                idx += 2
                entry_end = (idx - 2) + offset if offset != 0 else len(w_pdata)

                if group_id < 0:
                    gid = abs(group_id)
                    if name == "FORCE_PLATFORM":
                        w_fp_gid = gid
                    else:
                        kept_entries.append(w_pdata[entry_start:entry_end])
                else:
                    if group_id == w_fp_gid:
                        if name == "USED":
                            pdata_start = idx + 2 + w_pdata[idx+1]
                            val = struct.unpack("<h", w_pdata[pdata_start:pdata_start+2])[0]
                            if val > 0:
                                has_valid_fp = True
                    else:
                        kept_entries.append(w_pdata[entry_start:entry_end])

                if offset == 0:
                    break
                idx = entry_end

            if has_valid_fp:
                return

            new_fp_entries = []
            target_gid = w_fp_gid if w_fp_gid is not None else 5
            extracted = False

            if trial.file_path and os.path.exists(trial.file_path):
                try:
                    with open(trial.file_path, "rb") as f:
                        orig_data = f.read()
                    orig_header = orig_data[:512]
                    orig_pblock = orig_header[0]
                    orig_dblock = struct.unpack("<H", orig_header[16:18])[0]
                    orig_pdata = orig_data[(orig_pblock - 1) * 512: (orig_dblock - 1) * 512]

                    idx = 4
                    orig_fp_gid = None
                    orig_fp_params = []

                    while idx < len(orig_pdata):
                        if idx + 2 > len(orig_pdata):
                            break
                        entry_start = idx
                        name_len = struct.unpack("b", orig_pdata[idx:idx+1])[0]
                        group_id = struct.unpack("b", orig_pdata[idx+1:idx+2])[0]
                        idx += 2
                        if name_len == 0:
                            break
                        abs_len = abs(name_len)
                        name = orig_pdata[idx:idx+abs_len].decode("ascii", errors="ignore").upper()
                        idx += abs_len
                        offset = struct.unpack("<h", orig_pdata[idx:idx+2])[0]
                        idx += 2
                        entry_end = (idx - 2) + offset if offset != 0 else len(orig_pdata)

                        if group_id < 0:
                            if name == "FORCE_PLATFORM":
                                orig_fp_gid = abs(group_id)
                        else:
                            if group_id == orig_fp_gid:
                                orig_fp_params.append(orig_pdata[entry_start:entry_end])

                        if offset == 0:
                            break
                        idx = entry_end

                    if orig_fp_params:
                        grp_name = b"FORCE_PLATFORM"
                        grp_desc = b"Force platform parameters"
                        grp_offset = 2 + 1 + len(grp_desc)
                        grp_entry = struct.pack("bb", -len(grp_name), -target_gid) + grp_name + struct.pack("<h", grp_offset) + struct.pack("B", len(grp_desc)) + grp_desc
                        new_fp_entries.append(grp_entry)
                        for param_bytes in orig_fp_params:
                            p_mut = bytearray(param_bytes)
                            p_mut[1] = target_gid
                            new_fp_entries.append(bytes(p_mut))
                        extracted = True
                except Exception as e:
                    print(f"Warning reading original force platform parameters: {e}")

            if not extracted:
                grp_name = b"FORCE_PLATFORM"
                grp_desc = b"Force platform parameters"
                grp_offset = 2 + 1 + len(grp_desc)
                grp_entry = struct.pack("bb", -len(grp_name), -target_gid) + grp_name + struct.pack("<h", grp_offset) + struct.pack("B", len(grp_desc)) + grp_desc
                new_fp_entries.append(grp_entry)

                num_fp = len(trial.force_platforms)
                def make_param(pname, type_code, dims, data_bytes, pdesc=b""):
                    payload = struct.pack("bB", type_code, len(dims)) + bytes(dims) + data_bytes + struct.pack("B", len(pdesc)) + pdesc
                    offset = 2 + len(payload)
                    return struct.pack("bb", len(pname), target_gid) + pname.encode("ascii") + struct.pack("<h", offset) + payload

                new_fp_entries.append(make_param("USED", 2, [], struct.pack("<h", num_fp)))
                types = [fp.type for fp in trial.force_platforms]
                new_fp_entries.append(make_param("TYPE", 2, [num_fp], struct.pack(f"<{num_fp}h", *types)))
                new_fp_entries.append(make_param("ZERO", 2, [2], struct.pack("<2h", 1, 0)))
                corners_data = b"".join([fp.corners.astype(np.float32).tobytes(order='F') for fp in trial.force_platforms])
                new_fp_entries.append(make_param("CORNERS", 4, [3, 4, num_fp], corners_data))
                origin_data = b"".join([fp.origin.astype(np.float32).tobytes(order='F') for fp in trial.force_platforms])
                new_fp_entries.append(make_param("ORIGIN", 4, [3, num_fp], origin_data))

                all_channel_names = list(trial.analogs.keys())
                chan_cols = []
                for fp in trial.force_platforms:
                    ch_list = []
                    for ch_name in fp.channels.keys():
                        if ch_name in all_channel_names:
                            ch_list.append(all_channel_names.index(ch_name) + 1)
                    while len(ch_list) < 6:
                        ch_list.append(0)
                    chan_cols.append(ch_list[:8] if len(ch_list) >= 8 else ch_list[:6])
                n_ch = max(len(c) for c in chan_cols) if chan_cols else 6
                for c in chan_cols:
                    while len(c) < n_ch:
                        c.append(0)
                chan_mat = np.array(chan_cols, dtype=np.int16).T
                new_fp_entries.append(make_param("CHANNEL", 2, [n_ch, num_fp], chan_mat.tobytes(order='F')))

            all_entries = kept_entries + new_fp_entries
            relinked_data = bytearray(4)
            relinked_data[0] = 0
            relinked_data[1] = 0x50
            relinked_data[3] = 84

            for i, entry in enumerate(all_entries):
                entry_mut = bytearray(entry)
                name_len = abs(struct.unpack("b", entry_mut[:1])[0])
                offset_pos = 2 + name_len
                if i < len(all_entries) - 1:
                    next_offset = len(entry_mut) - offset_pos
                    struct.pack_into("<h", entry_mut, offset_pos, next_offset)
                else:
                    struct.pack_into("<h", entry_mut, offset_pos, 0)
                relinked_data.extend(entry_mut)

            pad_len = (512 - (len(relinked_data) % 512)) % 512
            if pad_len > 0:
                relinked_data.extend(b"\x00" * pad_len)

            total_param_blocks = len(relinked_data) // 512
            relinked_data[2] = total_param_blocks

            new_dblock = w_pblock + total_param_blocks
            struct.pack_into("<H", w_header, 16, new_dblock)

            with open(output_path, "wb") as f:
                f.write(w_header)
                f.write(relinked_data)
                f.write(data_section)
        except Exception as e:
            print(f"Warning preserving force platform metadata: {e}")

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

        # 1. Force plates geometry (top surface and 20mm thickness box)
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

"""OpenSim export utilities for generating .trc marker files, .mot GRF files, and ExternalLoads .xml configs."""

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from core.data_models import C3DTrial


AXIS_VECTORS: Dict[str, np.ndarray] = {
    "+X": np.array([1.0, 0.0, 0.0], dtype=np.float64),
    "-X": np.array([-1.0, 0.0, 0.0], dtype=np.float64),
    "+Y": np.array([0.0, 1.0, 0.0], dtype=np.float64),
    "-Y": np.array([0.0, -1.0, 0.0], dtype=np.float64),
    "+Z": np.array([0.0, 0.0, 1.0], dtype=np.float64),
    "-Z": np.array([0.0, 0.0, -1.0], dtype=np.float64),
}

COORDINATE_PRESETS: Dict[str, Tuple[str, str, str]] = {
    "Lab Z-Up, X-Forward (Vicon/Qualisys -> OpenSim Y-Up)": ("+X", "+Z", "-Y"),
    "Lab Z-Up, Y-Forward (Lab +Y Fwd -> OpenSim Y-Up)": ("+Y", "+Z", "+X"),
    "Lab Z-Up, -Y-Forward (Lab -Y Fwd -> OpenSim Y-Up)": ("-Y", "+Z", "-X"),
    "Lab Y-Up, X-Forward (Identity -> OpenSim Y-Up)": ("+X", "+Y", "+Z"),
}


@dataclass
class ExternalForceConfig:
    """Configuration for a single OpenSim ExternalForce entry."""
    name: str = "ExternalForce_1"
    is_disabled: bool = False
    applied_to_body: str = "calcn_r"
    force_expressed_in_body: str = "ground"
    point_expressed_in_body: str = "ground"
    force_identifier: str = "ground_force_1_v"
    point_identifier: str = "ground_force_1_p"
    torque_identifier: str = "ground_torque_1_"
    plate_index: int = 0


def build_axis_transform_matrix(map_x: str, map_y: str, map_z: str) -> np.ndarray:
    """
    Build a 3x3 transformation matrix R where row 0..2 correspond to OpenSim +X, +Y, +Z
    expressed in the C3D trial's coordinate axes (e.g. ('+X', '+Z', '-Y')).
    Applying `pts @ R.T` transforms (N, 3) trial vectors into OpenSim coordinates.
    """
    rx = AXIS_VECTORS.get(map_x, AXIS_VECTORS["+X"])
    ry = AXIS_VECTORS.get(map_y, AXIS_VECTORS["+Y"])
    rz = AXIS_VECTORS.get(map_z, AXIS_VECTORS["+Z"])
    return np.vstack([rx, ry, rz])


def default_external_forces_for_count(count: int) -> List[ExternalForceConfig]:
    """Generate sensible default ExternalForceConfig entries for `count` force plates."""
    bodies = ["calcn_r", "calcn_l"]
    configs: List[ExternalForceConfig] = []
    for i in range(max(0, count)):
        idx_1 = i + 1
        configs.append(
            ExternalForceConfig(
                name=f"ExternalForce_{idx_1}",
                is_disabled=False,
                applied_to_body=bodies[i % len(bodies)],
                force_expressed_in_body="ground",
                point_expressed_in_body="ground",
                force_identifier=f"ground_force_{idx_1}_v",
                point_identifier=f"ground_force_{idx_1}_p",
                torque_identifier=f"ground_torque_{idx_1}_",
                plate_index=i,
            )
        )
    return configs


def parse_external_loads_xml(xml_path: str) -> List[ExternalForceConfig]:
    """Parse ExternalForce definitions from an existing OpenSim ExternalLoads XML file."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    configs: List[ExternalForceConfig] = []

    for idx, ef in enumerate(root.findall(".//ExternalLoads/objects/ExternalForce")):
        def _txt(tag: str, default: str = "") -> str:
            el = ef.find(tag)
            return el.text.strip() if el is not None and el.text else default

        configs.append(
            ExternalForceConfig(
                name=ef.attrib.get("name", f"ExternalForce_{idx + 1}").strip(),
                is_disabled=_txt("isDisabled", "false").lower() == "true",
                applied_to_body=_txt("applied_to_body", "calcn_r"),
                force_expressed_in_body=_txt("force_expressed_in_body", "ground"),
                point_expressed_in_body=_txt("point_expressed_in_body", "ground"),
                force_identifier=_txt("force_identifier", f"ground_force_{idx + 1}_v"),
                point_identifier=_txt("point_identifier", f"ground_force_{idx + 1}_p"),
                torque_identifier=_txt("torque_identifier", f"ground_torque_{idx + 1}_"),
                plate_index=idx,
            )
        )
    return configs


def write_trc(
    trial: C3DTrial,
    output_path: str,
    transform_matrix: np.ndarray,
    target_units: str = "mm",
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
) -> str:
    """
    Export trial marker trajectories to an OpenSim .trc (Track Row Column) file.
    """
    if not trial.markers:
        raise ValueError("Trial contains no marker trajectories to export.")

    n_total = trial.point_frame_count
    s_f = 0 if start_frame is None else max(0, min(n_total - 1, int(start_frame)))
    e_f = (n_total - 1) if end_frame is None else max(s_f, min(n_total - 1, int(end_frame)))
    num_frames = e_f - s_f + 1
    rate = float(trial.point_rate) if trial.point_rate > 0 else 100.0

    src_is_meters = str(getattr(trial, "marker_units", "mm")).strip().lower() in ("m", "meter", "meters")
    dst_is_meters = str(target_units).strip().lower() in ("m", "meter", "meters")
    if src_is_meters and not dst_is_meters:
        unit_scale = 1000.0
    elif not src_is_meters and dst_is_meters:
        unit_scale = 0.001
    else:
        unit_scale = 1.0
    units_label = "m" if dst_is_meters else "mm"

    marker_names = list(trial.markers.keys())
    num_markers = len(marker_names)
    orig_start_frame = int(trial.first_frame) + s_f

    # Pre-transform marker arrays: shape (num_markers, num_frames, 3)
    transformed = []
    for name in marker_names:
        arr = np.asarray(trial.markers[name][s_f : e_f + 1], dtype=np.float64) * unit_scale
        transformed.append(arr @ transform_matrix.T)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        fname = os.path.basename(output_path)
        f.write(f"PathFileType\t4\t(X/Y/Z)\t{fname}\n")
        f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")
        f.write(
            f"{rate:.6g}\t{rate:.6g}\t{num_frames}\t{num_markers}\t{units_label}\t"
            f"{rate:.6g}\t{orig_start_frame}\t{num_frames}\n"
        )

        # Marker header row
        m_headers = ["Frame#", "Time"]
        coord_headers = ["", ""]
        for idx, m_name in enumerate(marker_names, start=1):
            m_headers.extend([m_name, "", ""])
            coord_headers.extend([f"X{idx}", f"Y{idx}", f"Z{idx}"])
        f.write("\t".join(m_headers) + "\n")
        f.write("\t".join(coord_headers) + "\n")
        f.write("\n")

        # Data rows
        for row_i in range(num_frames):
            frame_num = orig_start_frame + row_i
            time_s = (s_f + row_i) / rate
            row_vals = [str(frame_num), f"{time_s:.6f}"]
            for m_arr in transformed:
                x, y, z = m_arr[row_i]
                if np.isnan(x) or np.isnan(y) or np.isnan(z):
                    row_vals.extend(["", "", ""])
                else:
                    row_vals.extend([f"{x:.6f}", f"{y:.6f}", f"{z:.6f}"])
            f.write("\t".join(row_vals) + "\n")

    return output_path


def _compute_free_moment_z_nm(fp_forces: np.ndarray, fp_moments_nm: np.ndarray, fp_cop_m: np.ndarray) -> np.ndarray:
    """
    Compute the vertical free moment Tz (N.m) about the COP in lab coordinates:
    Tz = Mz - (px * Fy - py * Fx).
    """
    fx, fy = fp_forces[:, 0], fp_forces[:, 1]
    mz = fp_moments_nm[:, 2]
    px, py = fp_cop_m[:, 0], fp_cop_m[:, 1]
    return mz - (px * fy - py * fx)


def write_grf_mot(
    trial: C3DTrial,
    output_path: str,
    transform_matrix: np.ndarray,
    external_forces: List[ExternalForceConfig],
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
) -> str:
    """
    Export force platform ground reaction forces, COP (in meters), and free moments (in N.m)
    to an OpenSim-compatible .mot Storage file.
    """
    if not trial.force_platforms:
        raise ValueError("Trial contains no force platform data to export.")

    point_total = trial.point_frame_count
    s_f = 0 if start_frame is None else max(0, min(point_total - 1, int(start_frame)))
    e_f = (point_total - 1) if end_frame is None else max(s_f, min(point_total - 1, int(end_frame)))

    subsamples = max(1, int(trial.analog_subsamples))
    analog_rate = float(trial.analog_rate) if trial.analog_rate > 0 else (
        (float(trial.point_rate) if trial.point_rate > 0 else 100.0) * subsamples
    )

    s_a = s_f * subsamples
    e_a = (e_f + 1) * subsamples  # exclusive slice bound

    # Determine actual analog sample count from first valid platform
    n_analog_avail = 0
    for fp in trial.force_platforms:
        if fp.forces is not None:
            n_analog_avail = len(fp.forces)
            break
    if n_analog_avail == 0:
        raise ValueError("Force platforms have no computed GRF data.")

    s_a = max(0, min(n_analog_avail - 1, s_a))
    e_a = max(s_a + 1, min(n_analog_avail, e_a))
    n_rows = e_a - s_a

    # Units in C3DTrial: COP is mm unless marker_units == 'm'; moments are N.mm unless 'm'
    src_is_meters = str(getattr(trial, "marker_units", "mm")).strip().lower() in ("m", "meter", "meters")
    len_to_m = 1.0 if src_is_meters else 0.001

    active_configs = [cfg for cfg in external_forces if cfg.plate_index < len(trial.force_platforms)]
    if not active_configs:
        active_configs = default_external_forces_for_count(len(trial.force_platforms))

    columns: List[str] = ["time"]
    data_cols: List[np.ndarray] = [
        (np.arange(s_a, e_a, dtype=np.float64) / analog_rate)
    ]

    for cfg in active_configs:
        fp = trial.force_platforms[cfg.plate_index]
        forces_lab = np.zeros((n_rows, 3), dtype=np.float64)
        cop_lab_m = np.zeros((n_rows, 3), dtype=np.float64)
        torque_lab_nm = np.zeros((n_rows, 3), dtype=np.float64)

        if fp.forces is not None and len(fp.forces) >= e_a:
            forces_lab = np.nan_to_num(fp.forces[s_a:e_a].astype(np.float64), nan=0.0)
        if fp.cop is not None and len(fp.cop) >= e_a:
            cop_lab_m = np.nan_to_num(fp.cop[s_a:e_a].astype(np.float64), nan=0.0) * len_to_m
        if fp.moments is not None and len(fp.moments) >= e_a:
            moments_lab_nm = np.nan_to_num(fp.moments[s_a:e_a].astype(np.float64), nan=0.0) * len_to_m
            # Free moment about vertical lab axis (Z in Z-up lab; if moments are already pure free moment, Tz = Mz)
            tz = _compute_free_moment_z_nm(forces_lab, moments_lab_nm, cop_lab_m)
            torque_lab_nm[:, 2] = tz

        f_os = forces_lab @ transform_matrix.T
        p_os = cop_lab_m @ transform_matrix.T
        t_os = torque_lab_nm @ transform_matrix.T

        f_id = cfg.force_identifier.strip()
        p_id = cfg.point_identifier.strip()
        t_id = cfg.torque_identifier.strip()

        columns.extend([
            f"{f_id}x", f"{f_id}y", f"{f_id}z",
            f"{p_id}x", f"{p_id}y", f"{p_id}z",
            f"{t_id}x", f"{t_id}y", f"{t_id}z",
        ])
        for arr in (f_os, p_os, t_os):
            data_cols.extend([arr[:, 0], arr[:, 1], arr[:, 2]])

    matrix = np.column_stack(data_cols)
    n_cols = len(columns)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{os.path.basename(output_path)}\n")
        f.write("version=1\n")
        f.write(f"nRows={n_rows}\n")
        f.write(f"nColumns={n_cols}\n")
        f.write("inDegrees=no\n")
        f.write("endheader\n")
        f.write("\t".join(columns) + "\n")
        np.savetxt(f, matrix, delimiter="\t", fmt="%.6f")

    return output_path


def write_external_loads_xml(
    output_path: str,
    mot_filename: str,
    external_forces: List[ExternalForceConfig],
    loads_name: str = "ExternalLoads",
) -> str:
    """
    Generate an OpenSim ExternalLoads XML configuration file referencing `mot_filename`.
    Follows OpenSim ExternalLoads schema compatible with GRF_sample.xml and OpenSim 3.x/4.x.
    """
    doc = ET.Element("OpenSimDocument", {"Version": "40000"})
    ext_loads = ET.SubElement(doc, "ExternalLoads", {"name": loads_name})
    objects = ET.SubElement(ext_loads, "objects")

    for cfg in external_forces:
        ef = ET.SubElement(objects, "ExternalForce", {"name": cfg.name.strip() or "ExternalForce"})
        ET.SubElement(ef, "isDisabled").text = "true" if cfg.is_disabled else "false"
        ET.SubElement(ef, "applied_to_body").text = cfg.applied_to_body.strip() or "calcn_r"
        ET.SubElement(ef, "force_expressed_in_body").text = cfg.force_expressed_in_body.strip() or "ground"
        ET.SubElement(ef, "point_expressed_in_body").text = cfg.point_expressed_in_body.strip() or "ground"
        ET.SubElement(ef, "force_identifier").text = cfg.force_identifier.strip()
        ET.SubElement(ef, "point_identifier").text = cfg.point_identifier.strip()
        ET.SubElement(ef, "torque_identifier").text = cfg.torque_identifier.strip()
        ET.SubElement(ef, "data_source_name").text = "Unassigned"

    ET.SubElement(ext_loads, "groups")
    ET.SubElement(ext_loads, "datafile").text = os.path.basename(mot_filename)

    rough = ET.tostring(doc, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="\t", encoding="utf-8").decode("utf-8")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(pretty)

    return output_path


def export_trial_to_opensim(
    trial: C3DTrial,
    output_dir: str,
    base_name: str,
    transform_matrix: np.ndarray,
    trc_units: str = "mm",
    export_grf: bool = True,
    external_forces: Optional[List[ExternalForceConfig]] = None,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
) -> Dict[str, str]:
    """
    Export a C3DTrial into OpenSim-ready files (.trc, and optionally _grf.mot + _grf.xml).
    Returns dict mapping file type ('trc', 'mot', 'xml') to written file path.
    """
    os.makedirs(output_dir, exist_ok=True)
    outputs: Dict[str, str] = {}

    if trial.markers:
        trc_path = os.path.join(output_dir, f"{base_name}.trc")
        write_trc(
            trial,
            trc_path,
            transform_matrix=transform_matrix,
            target_units=trc_units,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        outputs["trc"] = trc_path

    if export_grf and trial.force_platforms:
        has_forces = any(fp.forces is not None and len(fp.forces) > 0 for fp in trial.force_platforms)
        if has_forces:
            ef_list = external_forces if external_forces else default_external_forces_for_count(len(trial.force_platforms))
            active_ef = [cfg for cfg in ef_list if cfg.plate_index < len(trial.force_platforms)]
            if not active_ef:
                active_ef = default_external_forces_for_count(len(trial.force_platforms))

            mot_filename = f"{base_name}_grf.mot"
            mot_path = os.path.join(output_dir, mot_filename)
            write_grf_mot(
                trial,
                mot_path,
                transform_matrix=transform_matrix,
                external_forces=active_ef,
                start_frame=start_frame,
                end_frame=end_frame,
            )
            outputs["mot"] = mot_path

            xml_path = os.path.join(output_dir, f"{base_name}_grf.xml")
            write_external_loads_xml(
                xml_path,
                mot_filename=mot_filename,
                external_forces=active_ef,
                loads_name=f"{base_name}_ExternalLoads",
            )
            outputs["xml"] = xml_path

    return outputs

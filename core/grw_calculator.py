"""Ground Reaction Wrenches (GRW) calculation module.

Calculates ground reaction forces (Fx, Fy, Fz), moments (Mx, My, Mz),
and Center of Pressure (COP / PWA) in the laboratory (global) coordinate system
from raw force platform geometry, calibration parameters, and analog channels.

Implements the exact algorithm from BTK (Shimba 1984, "An estimation of center
of gravity from force platform data", Journal of Biomechanics).
"""

from typing import Dict, List, Optional, Any, Tuple, Union
import numpy as np


def compute_ground_reaction_wrenches(
    c3d_obj: Any,
    threshold: float = 10.0
) -> List[Dict[str, np.ndarray]]:
    """
    Calculate ground reaction wrenches for all force platforms in an ezc3d object,
    matching BTK's GroundReactionWrenchFilter (Shimba 1984) algorithm with thresholding.

    Args:
        c3d_obj: ezc3d.c3d instance.
        threshold: Fz threshold in Newtons (default 10.0 N). When vertical force |Fz|
                   drops below this threshold (or sNF == 0), the force is treated as
                   zero noise, moments are zeroed, and COP is placed stably at the
                   geometric center of the plate to prevent wild vector jumping.

    Returns:
        List of dictionaries with keys:
            'F': np.ndarray of shape (N, 3) - Forces [Fx, Fy, Fz] (N) in global frame.
            'M': np.ndarray of shape (N, 3) - Moments [Mx, My, Mz] (N·mm) in global frame at the COP.
            'P': np.ndarray of shape (N, 3) - Center of Pressure [Px, Py, Pz] (mm) in global frame.
            'Tz': np.ndarray of shape (N, 1) - Free vertical torque (N·mm).
            'corners': np.ndarray of shape (3, 4) - Platform corners (mm).
            'origin': np.ndarray of shape (3,) - Platform origin offset (mm).
            'type': int - Force platform type.
    """
    results: List[Dict[str, np.ndarray]] = []

    if 'parameters' not in c3d_obj or 'FORCE_PLATFORM' not in c3d_obj['parameters']:
        return results

    fp_group = c3d_obj['parameters']['FORCE_PLATFORM']
    n_plates = int(fp_group['USED']['value'][0]) if 'USED' in fp_group else 0
    if n_plates <= 0:
        return results

    types = np.atleast_1d(fp_group['TYPE']['value'])
    corners_all = fp_group.get('CORNERS', {}).get('value')
    if corners_all is None:
        return results

    origins_all = fp_group.get('ORIGIN', {}).get('value', np.zeros((3, n_plates)))
    channels_all = fp_group.get('CHANNEL', {}).get('value')
    if channels_all is None:
        return results

    cal_mats = fp_group.get('CAL_MATRIX', {}).get('value', None)

    # Raw analog data from ezc3d: shape is (1, n_analogs, n_frames)
    if 'data' not in c3d_obj or 'analogs' not in c3d_obj['data']:
        return results

    raw_analogs = c3d_obj['data']['analogs']
    if raw_analogs.ndim == 3 and raw_analogs.shape[0] > 0:
        analog_data = raw_analogs[0]  # shape (n_analogs, n_frames)
    elif raw_analogs.ndim == 2:
        analog_data = raw_analogs
    else:
        return results

    n_analog_channels, n_frames = analog_data.shape
    if n_frames == 0:
        return results

    for i in range(n_plates):
        fp_type = int(types[i]) if i < len(types) else 1

        # Extract corners (3, 4)
        if corners_all.ndim == 3:
            corners = corners_all[:, :, i]
        else:
            corners = corners_all

        # Extract origin (3,)
        if origins_all.ndim == 2:
            origin = origins_all[:, i]
        elif origins_all.ndim == 1:
            origin = origins_all
        else:
            origin = np.zeros(3)

        # Extract channel indices for this platform (1-based in C3D parameter)
        if channels_all.ndim == 2:
            ch_list = channels_all[:, i]
        else:
            ch_list = channels_all

        # 0-based analog channel indices
        ch_indices = []
        for ch in ch_list:
            ch_idx = int(ch) - 1
            if 0 <= ch_idx < n_analog_channels:
                ch_indices.append(ch_idx)

        V = analog_data[ch_indices, :] if ch_indices else np.zeros((len(ch_list), n_frames))

        # -------------------------------------------------------------
        # 1. Force and Moment in local coordinate frame (ForcePlatformWrenchFilter)
        # -------------------------------------------------------------
        if fp_type == 3 and V.shape[0] >= 8:
            # Type 3: Kistler 8-channel force plates
            Fx = V[0] + V[1]
            Fy = V[2] + V[3]
            Fz = V[4] + V[5] + V[6] + V[7]

            ox = float(origin[0])
            oy = float(origin[1])
            oz = float(origin[2])
            if oz > 0:
                oz = -oz

            Mx = oy * (V[4] + V[5] - V[6] - V[7])
            My = ox * (V[5] + V[6] - V[4] - V[7])
            Mz = oy * (V[1] - V[0]) + ox * (V[2] - V[3])
            o_grw = np.array([0.0, 0.0, oz], dtype=np.float64)

        elif fp_type in (2, 4, 5) and V.shape[0] >= 6:
            # Type 2 & 5: Strain-gauge 6-channel platforms (AMTI, Bertec)
            cal = None
            if cal_mats is not None:
                if cal_mats.ndim == 3 and i < cal_mats.shape[2]:
                    cal = cal_mats[:, :, i]
                elif cal_mats.ndim == 2:
                    cal = cal_mats

            if cal is not None and not np.all(cal == 0) and cal.shape[0] >= 6 and cal.shape[1] >= 6:
                S = cal[:6, :6] @ V[:6, :]
            else:
                S = V[:6, :]

            Fx = S[0]
            Fy = S[1]
            Fz = S[2]
            Mx = S[3]
            My = S[4]
            Mz = S[5]

            o_grw = np.array(origin, dtype=np.float64)
            if o_grw[2] > 0:
                o_grw = -o_grw

        elif fp_type == 1 and V.shape[0] >= 6:
            # Type 1: 6 channels (Fx, Fy, Fz, Px, Py, Mz)
            Fx = V[0]
            Fy = V[1]
            Fz = V[2]
            Px_meas = V[3]
            Py_meas = V[4]
            Mz_meas = V[5]
            Mx = Py_meas * Fz
            My = -Px_meas * Fz
            Mz = Mz_meas
            o_grw = np.zeros(3, dtype=np.float64)

        else:
            Fx = V[0] if V.shape[0] > 0 else np.zeros(n_frames)
            Fy = V[1] if V.shape[0] > 1 else np.zeros(n_frames)
            Fz = V[2] if V.shape[0] > 2 else np.zeros(n_frames)
            Mx = np.zeros(n_frames, dtype=np.float64)
            My = np.zeros(n_frames, dtype=np.float64)
            Mz = np.zeros(n_frames, dtype=np.float64)
            o_grw = np.zeros(3, dtype=np.float64)

        # -------------------------------------------------------------
        # 2. FinishGRWComputation (Shimba 1984 algorithm)
        # -------------------------------------------------------------
        sNF = Fx**2 + Fy**2 + Fz**2

        # Correct moments for vertical origin offset: M_s = M_o + F x OS
        Mx += Fy * o_grw[2] - o_grw[1] * Fz
        My += Fz * o_grw[0] - o_grw[2] * Fx
        Mz += Fx * o_grw[1] - o_grw[0] * Fy

        # Point of Application (PWA / COP) calculation from Shimba (1984):
        # Px = (Fy * Mz - Fz * My) / sNF - (Fx^2 * My - Fx * (Fy * Mx)) / (sNF * Fz)
        # Py = (Fz * Mx - Fx * Mz) / sNF - (Fx * (Fy * My) - Fy^2 * Mx) / (sNF * Fz)
        denom = sNF * Fz
        safe_denom = np.where(np.abs(denom) > 1e-6, denom, 1.0)
        safe_sNF = np.where(sNF > 1e-6, sNF, 1.0)

        Px = (Fy * Mz - Fz * My) / safe_sNF - (Fx**2 * My - Fx * (Fy * Mx)) / safe_denom
        Py = (Fz * Mx - Fx * Mz) / safe_sNF - (Fx * (Fy * My) - Fy**2 * Mx) / safe_denom
        Pz = np.zeros_like(Px)

        # Thresholding: Suppress false PWA & force noise when |Fz| <= threshold
        below_thresh = (sNF < 1e-4) | (np.abs(Fz) <= threshold)
        Px[below_thresh] = 0.0
        Py[below_thresh] = 0.0
        Pz[below_thresh] = 0.0

        # Ground Reaction Wrench Moments at the COP:
        # M_pwa = M_s + F_s x PWA
        Mx += Fy * Pz - Py * Fz
        My += Fz * Px - Pz * Fx
        Mz += Fx * Py - Px * Fy

        # Zero out force & moment noise when foot is off plate
        Fx[below_thresh] = 0.0
        Fy[below_thresh] = 0.0
        Fz[below_thresh] = 0.0
        Mx[below_thresh] = 0.0
        My[below_thresh] = 0.0
        Mz[below_thresh] = 0.0

        # Free vertical torque Tz (Mz in local plate frame)
        Tz = Mz.copy()

        # -------------------------------------------------------------
        # 3. TransformToGlobal (matching TransformToGlobal)
        # -------------------------------------------------------------
        c0 = corners[:, 0]
        c1 = corners[:, 1]
        c2 = corners[:, 2]
        c3 = corners[:, 3]

        r0 = c0 - c1
        norm0 = np.linalg.norm(r0)
        r0 = r0 / norm0 if norm0 > 1e-6 else np.array([1.0, 0.0, 0.0])

        r2 = np.cross(r0, c0 - c3)
        norm2 = np.linalg.norm(r2)
        r2 = r2 / norm2 if norm2 > 1e-6 else np.array([0.0, 0.0, 1.0])

        r1 = np.cross(r2, r0)

        # Rotation matrix and plate surface center translation
        R = np.column_stack([r0, r1, r2])
        t = (c0 + c2) / 2.0

        F_local = np.column_stack([Fx, Fy, Fz])
        M_local = np.column_stack([Mx, My, Mz])
        P_local = np.column_stack([Px, Py, Pz])

        # Global forces, moments, and COP
        F_global = F_local @ R.T
        M_global = M_local @ R.T
        P_global = P_local @ R.T + t

        results.append({
            'F': F_global.astype(np.float32),          # (N, 3)
            'M': M_global.astype(np.float32),          # (N, 3)
            'P': P_global.astype(np.float32),          # (N, 3)
            'Tz': Tz[:, np.newaxis].astype(np.float32), # (N, 1)
            'corners': corners.astype(np.float32),
            'origin': origin.astype(np.float32),
            'type': fp_type
        })

    return results


def compute_single_plate_grw(
    analog_signals: np.ndarray,
    fp_type: int,
    corners: np.ndarray,
    origin: np.ndarray,
    cal_matrix: Optional[np.ndarray] = None,
    threshold: float = 10.0,
    custom_offset: bool = False
) -> Dict[str, np.ndarray]:
    """
    Compute Ground Reaction Wrenches (Forces, Moments, Center of Pressure) for a single
    force platform from its raw analog signals, geometry (4 corners), center/origin offset,
    and calibration matrix using the Shimba (1984) algorithm.

    Args:
        analog_signals: 2D array of shape (n_channels, n_frames) containing raw analog channels.
        fp_type: Force platform type (1, 2, 3, 4, 5).
        corners: 2D array of shape (3, 4) with 3D coordinates of the 4 corners [C1, C2, C3, C4].
        origin: 1D array of shape (3,) with origin/center offset [ox, oy, oz].
        cal_matrix: Optional 2D array of shape (6, 6) (or (8, 8)) calibration matrix.
                    For Type 4 force plates, the 6x6 matrix multiplies the 6 analog channels
                    (with diagonal corresponding to Fx, Fy, Fz, Mx, My, Mz).
        threshold: Vertical force threshold in Newtons (default 10.0 N).
        custom_offset: If True, treats origin[0] and origin[1] directly as user-specified X, Y
                       coordinate system offsets from the plate center without sign-flipping XY when oz > 0.

    Returns:
        Dictionary with keys:
            'F': (N, 3) float32 array of global forces [Fx, Fy, Fz] (N)
            'M': (N, 3) float32 array of global moments [Mx, My, Mz] (N·mm)
            'P': (N, 3) float32 array of global Center of Pressure [Px, Py, Pz] (mm)
            'Tz': (N, 1) float32 array of vertical free torque (N·mm)
            'F_local': (N, 3) float32 array of local plate forces [Fx, Fy, Fz]
            'M_local': (N, 3) float32 array of local plate moments [Mx, My, Mz]
            'P_local': (N, 3) float32 array of local plate COP [Px, Py, Pz]
    """
    V = np.asarray(analog_signals, dtype=np.float64)
    if V.ndim == 1:
        V = V[np.newaxis, :]
    n_channels, n_frames = V.shape
    corners = np.asarray(corners, dtype=np.float64).reshape(3, 4)
    origin = np.asarray(origin, dtype=np.float64).flatten()
    if len(origin) < 3:
        origin = np.pad(origin, (0, 3 - len(origin)), mode='constant')

    if n_frames == 0:
        empty3 = np.zeros((0, 3), dtype=np.float32)
        return {
            'F': empty3, 'M': empty3, 'P': empty3,
            'Tz': np.zeros((0, 1), dtype=np.float32),
            'F_local': empty3, 'M_local': empty3, 'P_local': empty3,
        }

    # 1. Local Forces & Moments
    if fp_type == 3 and n_channels >= 8:
        # Type 3: Kistler 8-channel force plate
        if cal_matrix is not None and not np.all(cal_matrix == 0) and cal_matrix.shape[0] >= 8 and cal_matrix.shape[1] >= 8:
            V_cal = cal_matrix[:8, :8] @ V[:8, :]
        elif cal_matrix is not None and not np.all(cal_matrix == 0) and cal_matrix.shape[0] >= 6 and cal_matrix.shape[1] >= 6:
            V_cal = V[:8, :].copy()
        else:
            V_cal = V[:8, :]

        Fx = V_cal[0] + V_cal[1]
        Fy = V_cal[2] + V_cal[3]
        Fz = V_cal[4] + V_cal[5] + V_cal[6] + V_cal[7]

        ox = float(origin[0])
        oy = float(origin[1])
        oz = float(origin[2])
        if oz > 0:
            oz = -oz

        Mx = oy * (V_cal[4] + V_cal[5] - V_cal[6] - V_cal[7])
        My = ox * (V_cal[5] + V_cal[6] - V_cal[4] - V_cal[7])
        Mz = oy * (V_cal[1] - V_cal[0]) + ox * (V_cal[2] - V_cal[3])
        o_grw = np.array([0.0, 0.0, oz], dtype=np.float64)

    elif fp_type in (2, 4, 5) and n_channels >= 6:
        # Type 2, 4, 5: 6-channel strain-gauge / calibration matrix force plates
        if cal_matrix is not None and not np.all(cal_matrix == 0) and cal_matrix.shape[0] >= 6 and cal_matrix.shape[1] >= 6:
            S = np.asarray(cal_matrix[:6, :6], dtype=np.float64) @ V[:6, :]
        else:
            S = V[:6, :].copy()

        Fx = S[0].copy()
        Fy = S[1].copy()
        Fz = S[2].copy()
        Mx = S[3].copy()
        My = S[4].copy()
        Mz = S[5].copy()

        o_grw = np.array(origin[:3], dtype=np.float64)
        if custom_offset:
            if o_grw[2] > 0:
                o_grw[2] = -o_grw[2]
        else:
            if o_grw[2] > 0:
                o_grw = -o_grw

    elif fp_type == 1 and n_channels >= 6:
        # Type 1: (Fx, Fy, Fz, Px, Py, Mz)
        if cal_matrix is not None and not np.all(cal_matrix == 0) and cal_matrix.shape[0] >= 6 and cal_matrix.shape[1] >= 6:
            S = np.asarray(cal_matrix[:6, :6], dtype=np.float64) @ V[:6, :]
        else:
            S = V[:6, :].copy()
        Fx = S[0].copy()
        Fy = S[1].copy()
        Fz = S[2].copy()
        Px_meas = S[3].copy()
        Py_meas = S[4].copy()
        Mz_meas = S[5].copy()
        Mx = Py_meas * Fz
        My = -Px_meas * Fz
        Mz = Mz_meas
        o_grw = np.array([origin[0], origin[1], 0.0], dtype=np.float64) if custom_offset else np.zeros(3, dtype=np.float64)

    else:
        if cal_matrix is not None and not np.all(cal_matrix == 0) and cal_matrix.shape[0] >= 6 and cal_matrix.shape[1] >= 6 and n_channels >= 6:
            S = np.asarray(cal_matrix[:6, :6], dtype=np.float64) @ V[:6, :]
        else:
            S = V
        Fx = S[0].copy() if S.shape[0] > 0 else np.zeros(n_frames, dtype=np.float64)
        Fy = S[1].copy() if S.shape[0] > 1 else np.zeros(n_frames, dtype=np.float64)
        Fz = S[2].copy() if S.shape[0] > 2 else np.zeros(n_frames, dtype=np.float64)
        Mx = S[3].copy() if S.shape[0] > 3 else np.zeros(n_frames, dtype=np.float64)
        My = S[4].copy() if S.shape[0] > 4 else np.zeros(n_frames, dtype=np.float64)
        Mz = S[5].copy() if S.shape[0] > 5 else np.zeros(n_frames, dtype=np.float64)
        o_grw = np.array(origin[:3], dtype=np.float64)
        if o_grw[2] > 0:
            o_grw[2] = -o_grw[2]

    # 2. Shimba (1984) Moment Transfer & Center of Pressure (PWA) Calculation
    sNF = Fx**2 + Fy**2 + Fz**2

    # Transfer moments for origin/center offset: M_s = M_o + F x o_grw
    Mx = Mx + (Fy * o_grw[2] - o_grw[1] * Fz)
    My = My + (Fz * o_grw[0] - o_grw[2] * Fx)
    Mz = Mz + (Fx * o_grw[1] - o_grw[0] * Fy)

    denom = sNF * Fz
    safe_denom = np.where(np.abs(denom) > 1e-6, denom, 1.0)
    safe_sNF = np.where(sNF > 1e-6, sNF, 1.0)

    Px = (Fy * Mz - Fz * My) / safe_sNF - (Fx**2 * My - Fx * (Fy * Mx)) / safe_denom
    Py = (Fz * Mx - Fx * Mz) / safe_sNF - (Fx * (Fy * My) - Fy**2 * Mx) / safe_denom
    Pz = np.zeros_like(Px)

    below_thresh = (sNF < 1e-4) | (np.abs(Fz) <= threshold)
    Px[below_thresh] = 0.0
    Py[below_thresh] = 0.0
    Pz[below_thresh] = 0.0

    # Moments at the COP: M_pwa = M_s + F_s x PWA
    Mx = Mx + (Fy * Pz - Py * Fz)
    My = My + (Fz * Px - Pz * Fx)
    Mz = Mz + (Fx * Py - Px * Fy)

    Fx[below_thresh] = 0.0
    Fy[below_thresh] = 0.0
    Fz[below_thresh] = 0.0
    Mx[below_thresh] = 0.0
    My[below_thresh] = 0.0
    Mz[below_thresh] = 0.0

    Tz = Mz.copy()

    # 3. Transform to Global Laboratory Coordinate System
    c0 = corners[:, 0]
    c1 = corners[:, 1]
    c2 = corners[:, 2]
    c3 = corners[:, 3]

    r0 = c0 - c1
    norm0 = np.linalg.norm(r0)
    r0 = r0 / norm0 if norm0 > 1e-6 else np.array([1.0, 0.0, 0.0])

    r2 = np.cross(r0, c0 - c3)
    norm2 = np.linalg.norm(r2)
    r2 = r2 / norm2 if norm2 > 1e-6 else np.array([0.0, 0.0, 1.0])

    r1 = np.cross(r2, r0)

    R = np.column_stack([r0, r1, r2])
    t = (c0 + c2) / 2.0

    F_local = np.column_stack([Fx, Fy, Fz])
    M_local = np.column_stack([Mx, My, Mz])
    P_local = np.column_stack([Px, Py, Pz])

    F_global = F_local @ R.T
    M_global = M_local @ R.T
    P_global = P_local @ R.T + t

    return {
        'F': F_global.astype(np.float32),
        'M': M_global.astype(np.float32),
        'P': P_global.astype(np.float32),
        'Tz': Tz[:, np.newaxis].astype(np.float32),
        'F_local': F_local.astype(np.float32),
        'M_local': M_local.astype(np.float32),
        'P_local': P_local.astype(np.float32),
        'corners': corners.astype(np.float32),
        'origin': origin.astype(np.float32),
        'type': int(fp_type)
    }


def extract_plate_analog_matrix(
    trial: Any,
    fp: Any,
    channel_names: Optional[List[str]] = None
) -> Tuple[np.ndarray, List[str]]:
    """
    Extract the (n_channels, n_frames) raw analog matrix for a ForcePlatformData instance
    from trial.analogs (preferring live analog channels so filtered/updated analogs apply).
    Returns (V_matrix, resolved_channel_names).
    """
    req_channels = 8 if getattr(fp, 'type', 2) == 3 else 6
    n_frames = getattr(trial, 'analog_frame_count', 0)
    if n_frames <= 0 and getattr(trial, 'analogs', None):
        first_arr = next(iter(trial.analogs.values()))
        n_frames = len(first_arr)
    if n_frames <= 0 and getattr(fp, 'channels', None):
        first_arr = next(iter(fp.channels.values()))
        n_frames = len(first_arr)

    resolved_names: List[str] = []
    if channel_names:
        resolved_names = [str(c) for c in channel_names if c]
    elif getattr(fp, 'channel_names', None):
        resolved_names = list(fp.channel_names)
    elif getattr(trial, 'btk_handle', None) is not None:
        try:
            c = trial.btk_handle
            fp_grp = c['parameters'].get('FORCE_PLATFORM', {})
            channels_all = fp_grp.get('CHANNEL', {}).get('value')
            if channels_all is not None:
                idx = max(0, getattr(fp, 'id', 1) - 1)
                ch_col = channels_all[:, idx] if (channels_all.ndim == 2 and idx < channels_all.shape[1]) else channels_all
                analog_keys = list(trial.analogs.keys())
                for ch_num in np.atleast_1d(ch_col):
                    c_int = int(ch_num)
                    if 1 <= c_int <= len(analog_keys):
                        resolved_names.append(analog_keys[c_int - 1])
        except Exception:
            pass

    rows = []
    if resolved_names and getattr(trial, 'analogs', None):
        for ch_name in resolved_names:
            if ch_name in trial.analogs:
                arr = np.asarray(trial.analogs[ch_name], dtype=np.float64)
                if n_frames == 0:
                    n_frames = len(arr)
                rows.append(arr)
            else:
                rows.append(np.zeros(max(1, n_frames), dtype=np.float64))

    if not rows and getattr(fp, 'channels', None):
        for ch_key, ch_arr in fp.channels.items():
            arr = np.asarray(ch_arr, dtype=np.float64)
            if n_frames == 0:
                n_frames = len(arr)
            rows.append(arr)
            resolved_names.append(ch_key)

    if not rows and getattr(trial, 'analogs', None):
        analog_keys = list(trial.analogs.keys())
        for ch_name in analog_keys[:req_channels]:
            arr = np.asarray(trial.analogs[ch_name], dtype=np.float64)
            if n_frames == 0:
                n_frames = len(arr)
            rows.append(arr)
            resolved_names.append(ch_name)

    if not rows:
        return np.zeros((req_channels, max(1, n_frames)), dtype=np.float64), resolved_names

    min_len = min(len(r) for r in rows) if rows else 0
    while len(rows) < req_channels:
        rows.append(np.zeros(min_len, dtype=np.float64))
    V = np.vstack([r[:min_len] for r in rows])
    return V, resolved_names




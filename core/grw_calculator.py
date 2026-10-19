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



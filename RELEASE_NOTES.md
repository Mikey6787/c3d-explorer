# C3D Explorer v1.2 — Release Notes

**C3D Explorer v1.2** introduces full **OpenSim Export (`.trc`, `_grf.mot`, `_grf.xml`)** with coordinate system transformation and conditional batch rules, **ROI-constrained playback**, **automatic proportional Y-axis scaling for analog/EMG channels**, and a complete **Visual User Manual** with annotated screenshots.

---

### 🚀 What's New in v1.2

#### 1. Export for OpenSim (`.trc`, `_grf.mot`, `_grf.xml`)
- **Single-Trial & Batch OpenSim Export** (`File → Export → Export for OpenSim (.trc, .mot, .xml)...`):
  - Generates standard OpenSim `.trc` marker files (`mm` or `m`), `_grf.mot` ground reaction force/COP/free-moment storage files (`N`, `m`, `N·m`), and `_grf.xml` `ExternalLoads` configuration files.
  - Supports loading existing OpenSim `ExternalLoads` XML templates and configuring `Plate #`, `Name`, `Applied To Body` (`calcn_r`, `calcn_l`, `pelvis`, etc.), and `Disabled` toggle switches.
- **Trial → OpenSim Coordinate System Mapping**:
  - Presets for standard motion capture labs (e.g., *Lab Z-Up, X-Forward → OpenSim Y-Up*) plus custom per-axis mapping applied uniformly to markers, forces, COP, and free moments.
- **Conditional Filename Batch Rules**:
  - Match filename substrings (e.g., `_L_`, `_R_`, `static`) in Batch Processing to automatically apply per-trial `ExternalLoads` or GRF enable/disable settings.

#### 2. ROI-Constrained Playback & Automatic Analog Plot Scaling
- **Trim / ROI Playback Bounds**: When the user limits the Region of Interest with **Trim Start `[`** and **Trim End `]`** handles, playback (`Play`, `Loop`, `Stop`, `Jump to Start/End`) operates strictly inside the active ROI.
- **Automatic Proportional Analog Scaling**: Plotting small-amplitude analog or EMG channels (e.g., `±0.002 V`) in the Universal Plotter now automatically scales the Y-axis proportionally to the signal amplitude instead of clamping to `±1.0`.

#### 3. Complete Visual Documentation
- Added [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) and standalone [`docs/USER_MANUAL.html`](docs/USER_MANUAL.html) (print-ready to PDF) featuring **10 annotated Clinical Light screenshots** covering the 3D Workspace, Universal Plotter, Force Plate GRW, Analog/EMG Filtering, Analog Info Specs, Hip Joint Center, Event Manager, OpenSim Export, Batch Processing, and Visual Settings.

---

### 📦 Downloads & Verification

| Platform | Package | Notes |
| :--- | :--- | :--- |
| **macOS (Apple Silicon)** | `C3D_Explorer_Mac.dmg` | Recommended for M1/M2/M3/M4 Macs |
| **macOS (Intel)** | `C3D_Explorer_Mac_Intel.dmg` | Recommended for Intel-based Macs (`x86_64`) |
| **Windows Installer** | `C3D_Explorer_Windows_Setup.exe` | Recommended for Windows 10/11 (64-bit) |
| **Windows Portable** | `C3D_Explorer_Windows_Portable.zip` | Standalone archive (no install required) |

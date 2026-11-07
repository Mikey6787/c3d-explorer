# C3D Explorer v1.1 — Release Notes

**C3D Explorer v1.1** introduces redesigned **Force Plate Ground Reaction Wrench (GRW)** workflows with persistent settings, unified **Analog Tools** with real-time specification tuning, batch pipeline processing, streamlined event styling, and enhanced 3D biomechanics visualization.

---

### 🚀 What's New in v1.1

#### 1. Redesigned Force Plate GRW Calculation
- **Automatic & Manual Calculation Modes**:
  - **Automatic Calculation (Shimba 1984)**: Standard biomechanics algorithm for strain gauge and piezoelectric plates (Types 1, 2, and 4).
  - **Manual Calculation**: Full manual control over calibration matrices (6x6), sensor offsets, corner coordinates, and channel mapping.
- **COP Threshold (N)**:
  - Renamed and simplified vertical force cutoff threshold to suppress noise during flight phases.
  - User adjustments in manual mode are automatically remembered and restored across sessions.
- **Enhanced 3D Labeling**: Larger, high-contrast force plate labels (FP1, FP2) in the 3D viewport.

#### 2. Streamlined Analog Tools & Specifications
- **Single Menu Entry**: Clean, unified entry under `Tools` → `Analog...`.
- **Dedicated "Info" Specifications Tab**:
  - Direct live editing of `SCALE`, `GEN_SCALE`, `OFFSET`, `Sampling Rate (Hz)`, and `Units`.
  - One-decimal numeric precision with spinner arrow buttons removed for direct keyboard entry.
  - Live **Combined Scale** readout (`SCALE × GEN_SCALE`).
  - Changing scale factors (e.g., `-1.0` to `+1.0`) immediately updates analog channel values, inverts polarities, updates C3D metadata, and recalculates connected force plates.
  - Complete **Undo / Redo** (`Ctrl+Z` / `Ctrl+Y`) integration.

#### 3. Automated Batch Processing Pipelines
- **Batch Processing Dialog**:
  - Apply automated processing across entire directories of C3D files.
  - Multi-step pipelines: Butterworth filtering (LP/HP/BP), EMG envelopes, rectification, marker gap smoothing, and force plate recalculation.
  - Export to C3D, CSV, and summary reports.

#### 4. Event System & Minimalist UI Enhancements
- **Consistent Event Context Coloring**:
  - **Red** for Right-side events (`Right Foot Strike`, `Right Foot Off`).
  - **Blue** for Left-side events (`Left Foot Strike`, `Left Foot Off`).
  - **Amber** for General events (`Start`, `End`, custom).
- **Minimalist Timeline Design**:
  - Subtle semi-transparent timeline trim handles.
  - Denser slider ticks for frame-accurate navigation.
  - Fast event creation, editing, and persistence to C3D.

#### 5. Marker Multi-Selection & Kinematics Tools
- Shift-click multi-selection in marker lists and 3D viewport picking.
- Batch color assignments and instant resetting.
- Create Average Marker and Centroid Marker calculations.

#### 6. Cross-Platform & Dark Theme Polish
- Native dark mode high-contrast text rendering across all input fields on macOS and Windows.
- 100% test pass rate across all unit and integration test suites.

---

### 📦 Downloads & Verification

| Platform | Package | SHA-256 / Verification |
| :--- | :--- | :--- |
| **macOS (Apple Silicon)** | `C3D_Explorer_Mac.dmg` | Recommended for M1/M2/M3/M4 Macs |
| **macOS (Intel)** | `C3D_Explorer_Mac_Intel.dmg` | Recommended for Intel-based Macs (x86_64) |
| **Windows Installer** | `C3D_Explorer_Windows_Setup.exe` | Recommended for Windows 10/11 (64-bit Intel/AMD) |
| **Windows Portable** | `C3D_Explorer_Windows_Portable.zip` | Standalone archive (no install required) |

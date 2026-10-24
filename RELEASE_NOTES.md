# C3D Explorer v1.0.2 — Release Notes

**C3D Explorer v1.0.2** adds native **macOS Intel (`x86_64`)** standalone application support alongside **Apple Silicon (`arm64`)**, introduces architecture-aware in-app updates, and delivers robust multi-unit scaling support across the 3D OpenGL viewport and signal plotter.

---

### 🚀 What's New in v1.0.2

#### 1. Native macOS Intel (`x86_64`) & Apple Silicon (`arm64`) Support
- **Dual macOS Builds**:
  - **`C3D_Explorer_Mac.dmg`**: Native ARM64 build optimized for Apple Silicon (M1, M2, M3, M4) Macs.
  - **`C3D_Explorer_Mac_Intel.dmg`**: Native x86_64 build for Intel-based Macs (macOS Catalina 10.15 through macOS Sequoia).
- **Universal Release Distribution**:
  - GitHub Actions matrix workflow builds on native runners (`macos-14`) to guarantee maximum performance and binary compatibility.
  - Automatically provisions both disk images as first-class GitHub Release assets.

#### 2. Architecture-Aware In-App Updater
- **Automated CPU Architecture Sensing**:
  - The in-app updater (`Help -> Check for Updates...`) detects the host system's CPU architecture (`platform.machine()`).
  - Users on Intel Macs automatically receive `C3D_Explorer_Mac_Intel.dmg`.
  - Users on Apple Silicon Macs automatically receive `C3D_Explorer_Mac.dmg`.
  - Windows users continue to receive the verified `C3D_Explorer_Windows_Setup.exe`.

#### 3. Robust Unit Scaling Support (Meters & Millimeters)
- **Automatic Unit Harmonization**:
  - Full support for C3D files recorded with length units in meters (`m`) or millimeters (`mm`).
  - Correctly auto-scales 3D marker coordinates, force plate corners, and ground reaction force vectors in the 3D viewport.
  - Coordinates in the Universal Plotter and Data Explorer panel reflect consistent, accurate physical dimensions.

---

### 📦 Downloads & Verification

| Platform | Package | SHA-256 / Verification |
| :--- | :--- | :--- |
| **macOS (Apple Silicon)** | `C3D_Explorer_Mac.dmg` | Recommended for M1/M2/M3/M4 Macs |
| **macOS (Intel)** | `C3D_Explorer_Mac_Intel.dmg` | Recommended for Intel-based Macs (x86_64) |
| **Windows Installer** | `C3D_Explorer_Windows_Setup.exe` | Recommended for Windows 10/11 (64-bit Intel/AMD) |
| **Windows Portable** | `C3D_Explorer_Windows_Portable.zip` | Standalone archive (no install required) |



# C3D Explorer v1.0.1 — Release Notes

**C3D Explorer v1.0.1** introduces an in-app updater system, dynamic theme-aware application icons, an unobstructed 3D viewport, critical Windows packaging fixes, and performance improvements.

---

### 🚀 What's New & Added Features

#### 1. Automated In-App "Check for Updates" System
- **Help Menu Action**: Added **`Help -> Check for Updates...`** to check GitHub for newer versions directly from the desktop menu bar.
- **About Dialog Integration**: Added a quick **"Check for Updates"** button inside the **About C3D Explorer** dialog.
- **Asynchronous Version Comparison**: Automatically queries the GitHub Releases API and compares semantic version numbers (`v1.0.1` vs remote releases) without blocking the user interface.
- **In-App Download & Update**:
  - Displays what's new and release changelogs directly inside the dialog.
  - **Windows**: One-click **"Download & Update Now"** downloads `C3D_Explorer_Windows_Setup.exe` with a live progress bar, launches the installer, and closes the running app to complete the update cleanly.
  - **macOS**: Downloads `C3D_Explorer_Mac.dmg` to `~/Downloads` and prompts to open the disk image to update Applications.

#### 2. Dynamic Theme Application & Window Icons
- **Theme-Aware Window & Taskbar Icons**:
  - When running in dark themes (*Biomech Dark*, *Nordic Midnight*, *Graphite Slate*, *Cyber Amber*), the app dynamically applies **`AppIcon-Dark.png`**.
  - When switching to the normal light theme (*Clinical Light*), the app dynamically applies **`AppIcon-Light.png`**.
- **Windows Standalone Icon (`app.ico`)**:
  - Embedded multi-resolution `app.ico` (from 16×16 to 256×256) into `C3DExplorer.exe` and `C3D_Explorer_Windows_Setup.exe`.
  - Registered `.c3d` file association with the official C3D Explorer logo in Windows File Explorer.
- **About Dialog Header**: Displays the official app icon alongside the version and developer information.

---

### 🎨 Cleanups & Removed Features

- **Removed 3D Viewport Overlay Buttons**:
  - Removed the floating camera preset buttons (`Fit View`, `3D Iso`, `Top`, `Front`, `Side`) from the top-left of the 3D OpenGL viewport for an unobstructed visualization experience.
  - All camera views remain instantly accessible via keyboard shortcuts (**`1`**, **`2`**, **`3`**, **`4`**, **`R`**) and the **`View`** menu.
- **Text Transparency Fix**:
  - Fixed dark highlighted rectangular boxes behind text labels inside cards and dialogs across dark and light themes.

---

### 🐛 Bug Fixes & Improvements

- **Fixed Missing `scipy` on Windows**:
  - Resolved `ModuleNotFoundError: No module named 'scipy'` on Windows installations by including `scipy>=1.10.0` in `requirements.txt` and packaging all required submodules (`scipy.signal`, `scipy.ndimage`, `scipy.special`).
  - Zero-phase Butterworth low-pass marker trajectory filtering and analog channel filtering now work out-of-the-box on all Windows systems.
- **macOS Font Alias Performance**:
  - Eliminated font family alias lookup latency on macOS by standardizing on native system font stacks (`SF Pro Text`, `Segoe UI`, `Roboto`).
- **CI/CD Build Automation**:
  - Updated GitHub Actions workflow (`build-windows.yml`) to automatically generate multi-resolution icon bundles and publish release assets with full changelogs.

---

### 📦 Downloads & Verification

| Platform | Package | SHA-256 / Verification |
| :--- | :--- | :--- |
| **Windows Installer** | `C3D_Explorer_Windows_Setup.exe` | Recommended for Windows 10/11 |
| **Windows Portable** | `C3D_Explorer_Windows_Portable.zip` | Standalone archive (no install required) |
| **macOS** | `C3D_Explorer_Mac.dmg` | Drag-and-drop disk image for macOS |

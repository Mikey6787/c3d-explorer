# C3D Explorer — Biomechanics & Motion Capture Workstation

[![Website](https://img.shields.io/badge/🌐%20Website-biomech--lab.pages.dev-007ACC.svg)](https://biomech-lab.pages.dev/)
[![Release](https://img.shields.io/badge/Release-v1.0.1-success.svg)](https://github.com/Mikey6787/c3d-explorer/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-555555.svg)]()
[![PySide6](https://img.shields.io/badge/GUI-Qt6%20%2F%20PySide6-41CD52.svg?logo=qt&logoColor=white)](https://wiki.qt.io/Qt_for_Python)
[![Windows Build](https://github.com/Mikey6787/c3d-explorer/actions/workflows/build-windows.yml/badge.svg)](https://github.com/Mikey6787/c3d-explorer/actions/workflows/build-windows.yml)
[![Buy Me a Coffee](https://img.shields.io/badge/☕%20Buy%20Me%20a%20Coffee-Donate%20€5-8D5B36.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=mohamadreza.kharazi%40live.com&currency_code=EUR&amount=5.00&item_name=Buy+Me+a+Coffee+-+C3D+Explorer)

**C3D Explorer** is a high-performance, open-source biomechanics and motion capture workstation designed for researchers, clinicians, and movement scientists. Built with **Python 3**, **Qt6 / PySide6**, **PyQtGraph**, and **ezc3d**, it offers an intuitive, fast, and modern desktop environment for 3D marker animation, multi-channel analog & force plate signal inspection, event detection, marker trajectory filtering, and standard `.c3d` file manipulation without relying on heavy proprietary software.

---

## Key Features

### 1. 3D OpenGL Biomechanics Viewport
- **3D Marker Visualization**: Real-time rendering of all optical markers with customizable size, color schemes, and selection highlighting.
- **Force Plate Geometry**: Renders 3D rectangular force platforms accurately positioned using C3D `CORNERS`.
- **Force Plate Coordinate Systems**: Renders local origin and coordinate axes (X Red, Y Green, Z Blue) for each force plate.
- **Ground Reaction Force (GRF) 3D Vectors**: Displays dynamic 3D vectors emanating from the Center of Pressure (COP) during stance phases when vertical force exceeds threshold.
- **Global Motion Capture Axes**: Lab origin coordinate system triad.
- **Ground Grid**: Configurable ground grid with millimeter/meter scale.
- **Camera Navigation & Presets**: Smooth mouse orbit (left drag), pan (middle/right drag), and zoom (wheel). Quick view buttons for **Isometric 3D**, **Top View**, **Front View**, **Side View**, and **Fit View**.

### 2. Interactive Timeline & Scrubber with Event Markers
- **Integrated C3D Events**: Discrete gait/motion events embedded directly into the timeline track:
  - **Right Foot** events (Red / Orange)
  - **Left Foot** events (Blue / Cyan)
  - **General** events (Amber / Gold)
- **Interactive Event Badges**: Hover over any event to view event name, timestamp (seconds), and exact frame number. Click any event badge to snap playback directly to it.
- **Right-Click Context Menu on Timeline Slider**:
  - Right-click anywhere on the scrubber bar to **"Add Event at Frame X..."** or **"Add Event at Playhead..."**.
  - Right-click directly on an event badge to **"Edit Event..."**, **"Delete Event"**, or jump directly to its frame.
- **Precision Playhead**: Smooth scrubbing across all frames.
- **Time & Frame Readout**: Shows current frame vs total frames, and elapsed time vs trial duration.

### 3. Playback Controls
- **Play / Pause** (Spacebar)
- **Step 1 Frame Forward** (Right Arrow)
- **Step 1 Frame Backward** (Left Arrow)
- **Jump to Start / End** (Home / End)
- **Variable Playback Speed**: `0.1x`, `0.25x`, `0.5x`, `1.0x (Real-time)`, `1.5x`, `2.0x`.
- **Loop Mode**: Toggleable continuous playback.

### 4. Synchronized Multi-Channel Time-Series Plotting
- **PyQtGraph 2D Curves**: Plotting of Ground Reaction Forces (Fx, Fy, Fz), Moments (Mx, My, Mz), and all analog EMG/transducer channels at 100% full raw sample resolution.
- **Full Resolution by Default**: Every raw data point and sample is rendered directly without downsampling or decimation.
- **Differential Curve Rendering**: Adding or removing a channel instantly updates only that specific curve instead of re-rendering all other signals from scratch.
- **Synchronized Time Cursor**: Vertical cursor line tracks the 3D playback in real time (< 1 ms per frame); drag or click the cursor on the plot to scrub the 3D animation.
- **Event Indicators**: Clean, color-coded vertical dashed lines at event timestamps without overlapping text labels (Red for Right leg, Cyan for Left leg, Amber for General).
- **Channel Selector & Search**: Filter channels and toggle individual signals on/off.

### 5. Multi-Tab Data Explorer Panel
- **Markers Tab**: Fast, single-column searchable marker checklist with visibility checkboxes, circular color indicators, individual color picker, and in-place renaming.
  - **Shift-Click & Multi-Selection**: Click any marker, hold <kbd>Shift</kbd>, and click another marker to select the entire range. Hold <kbd>Ctrl</kbd> / <kbd>Cmd</kbd> to toggle non-contiguous individual markers.
  - **Batch Color Assignment**: Right-click any selected group (or click `Color (N)...`) to choose a color that is applied simultaneously to all selected markers.
  - **Batch Visibility & Reset**: Right-click context menu options to Show Selected, Hide Selected, or Reset Color for all selected markers at once.
  - **In-Place Inline Renaming**: Double-click directly on any marker name (or press `Enter`/`F2`) to rename it immediately in place with validation and duplicate prevention.
  - **Context Menu / Action Buttons**: Right-click any marker or click `Rename...` to rename via standard dialog.
- **Force Plates Tab**: Detailed specs (dimensions, origin, type) and live force readouts (Fx, Fy, Fz, Total F) updating per frame.
- **Events Tab**: Chronological table of all trial events with context/leg, time, and frame (click to seek), plus action buttons (`+ Add`, `✎ Edit`, `🗑 Delete`) and right-click context menu.

### 6. Universal Signal & Marker Plotter
Under **`Tools -> Plotter...`** (`Ctrl+P` / `Cmd+P`):
- **Universal Multi-Curve Visualization**: Plot any data contained in the C3D file on a single synchronized chart:
  - **Individual Markers**: Trajectory components along the X, Y, and Z axes.
  - **Force Platforms**: Ground Reaction Forces ($F_x, F_y, F_z, F_{total}$), Moments ($M_x, M_y, M_z$), Center of Pressure ($COP_x, COP_y, COP_z$).
  - **Analog Channels**: EMG, accelerometers, load cells, and auxiliary transducers.
- **Time vs. Frame Number Axis**: Toggle instantly between **Time (seconds)** and **Frame Number** on the horizontal axis.
- **Synchronized Playback Cursor**: Real-time vertical playhead line synchronized with 3D playback and timeline scrubbing; drag or click to seek.
- **Dynamic Signal Filtering & Tree**: Fast search filter to find any marker or channel quickly with checkable items to easily add and remove curves.
- **Exporting**: One-click **Export Plotted to CSV** and **Save Image (PNG/JPEG)**.

### 7. Event Management & Creation
Under **`Tools -> Events`** (or timeline right-click):
- **Add Event at Current Frame (`Ctrl+E` / `Cmd+E`)**: Prompts an event creation dialog requesting all C3D parameters:
  - **Event Label**: Presets (`Foot Strike`, `Foot Off`, `Heel Strike`, `Toe Off`, `Initial Contact`, `Event`, `Start`, `End`) or custom input.
  - **Context / Leg**: `Right`, `Left`, `General`, or custom context.
  - **Synchronized Timing**: Edit by **Frame number** or **Time in seconds** with real-time conversion.
  - **Subject**: Subject or patient identifier.
  - **Description**: Detailed note or event annotation.
  - **Event ID**: Numeric index.
  - **Badge Color**: Auto-assigned or custom color picker.
- **Manage Events Dialog**: Full tabular event manager to review, edit, delete, or clear all events.
- **Export & Persistence**: All created, modified, or deleted events are automatically synchronized into the C3D acquisition structure and saved when exporting/saving C3D files.

### 8. Interactive 3D Marker Picking & Analysis Tools
- **Direct 3D Marker Picking**:
  - Click directly on any marker in the 3D animation / explorer window to select it.
  - **Multi-Selection in 3D**: Hold <kbd>Option</kbd> (macOS) or <kbd>Ctrl</kbd> (Windows/Linux) / <kbd>Shift</kbd> / <kbd>Cmd</kbd> while clicking markers to select multiple markers simultaneously.
  - Selected markers are highlighted with enlarged golden spheres and floating 3D text labels displaying their names.
  - Clicking empty 3D space deselects all markers.
- **Bi-Directional Synchronization**: Selecting markers in the 3D viewport immediately highlights them in the Data Explorer panel table, and selecting markers in the table immediately highlights them in the 3D viewport.
- **Tools with Auto-Populated Preselection**:
  - **Create Average Marker (`Tools -> Marker -> Create Average Marker...`)**: Automatically pre-populates Marker 1 and Marker 2 with the selected markers and suggests a default name `Avg_M1_M2`. Computes midpoint trajectory across all frames.
  - **Measure Distance between 2 Markers**: Automatically pre-populates Marker 1 and Marker 2 with selected markers, calculates Euclidean distance in real-time, displays live distance and statistics (Mean, SD, Min, Max) calculated strictly within the trimmed Region of Interest (ROI), interactive 3D line overlay, and 2D trajectory plotting with ROI curve highlighting, interactive ROI drag handles, and one-click "Fit ROI" / "Crop to ROI" options.
  - **Measure Angle between 3 Markers**: Pre-populates selected markers as A, B, and C, calculates 3D segment angle $\angle ABC$, with live angles, trial ROI statistics (Mean, SD, Min, Max computed between the trimmed positions), 3D angle ray overlays, and time-series plotting with ROI section highlighting.
- **Rename & Custom Colors**:
  - **Double-Click**: Instant in-place inline rename in the Markers panel table.
  - **Dialog / Menu**: Right-click any marker or use `Tools -> Marker -> Rename...` / side panel `Rename...` button.
  - **Individual Custom Colors**: Assign custom colors to specific markers (e.g. left limb blue, right limb red).

### 9. Visual Configurations & Settings
Under **`Settings -> Visual Configurations...`**:
- **Display Tab**:
  - **5 Professional Themes**:
    - `Biomech Dark`: Dark biomechanics workstation theme.
    - `Clinical Light`: Crisp high-contrast clinical laboratory theme.
    - `Nordic Midnight`: Nord frost teal and deep slate theme.
    - `Graphite Slate`: Industrial titanium and safety amber theme.
    - `Cyber Amber`: Deep aerospace navy and vibrant goldenrod theme.
  - **Quick Theme Switching**: Also accessible via **`View -> Theme`** in the main menu bar.
  - **3D Viewport Background**: Choice of Dark, Deep Slate, Pure Black, or Crisp White.
  - **Ground Grid**: Toggle ground grid visibility and set grid spacing in millimeters.
  - **Element Visibility**: Independent toggles for Markers, Force Platforms, and GRF Vectors.
- **Coordinate System Tab**:
  - **Global Coordinate System Visibility**: Show or hide the global origin triad.
  - **Axis Line Thickness**: Custom axis thickness slider/spinbox (`0.5 px` to `12.0 px`).
  - **Axis Length**: Configurable axis triad length (`100 mm` to `1000 mm`).
  - **Force Plate Local Axes**: Toggle visibility of local coordinate systems for individual force platforms.
  - **Global Orientation**: Set Up Axis (Z-up vs Y-up) and Ground plane orientation (XY vs XZ).
- **3D Visuals Tab**: Marker radius, default marker color, selection highlight color, GRF vector scale, and minimum vertical force threshold.
- **Playback Tab**: Default playback FPS and loop mode.

### 10. Menus & File I/O
- **File**: Open C3D (`Ctrl+O` / `Cmd+O`), Open Recent files list, Open File Location (Finder/Explorer), Save (`Ctrl+S`), Save As, Export C3D, Export as STL, Export CSV (Markers / Analogs), Exit.
- **Edit**: Undo (`Ctrl+Z`), Redo (`Ctrl+Y` / `Cmd+Shift+Z`), Export Summary Report.
- **View**: Reset View, Top, Front, Side, Iso views, Theme selection (`View -> Theme`), show/hide markers, plates, axes, grid, GRF vectors, and Panels submenu (`Data Explorer`, `Plotter`).
- **Settings**: Direct dialog for visual configurations (Display, Coordinate System, 3D Visuals, Playback).
- **Tools**: Plotter (`Ctrl+P`), Analog Channels & Signal Processing, Events (`Ctrl+E`), Marker submenu (Average, Distance, Angle, Rename, Color).
- **Drag & Drop**: Drag any `.c3d` file directly into the window.

---

## Installation & Downloads

### Download Standalone Packages (No Python Needed)
Pre-built standalone releases for **macOS** and **Windows** are available on **[GitHub Releases](https://github.com/Mikey6787/c3d-explorer/releases)** and the **[Biomech-Lab Website](https://biomech-lab.pages.dev/)**:

| Platform | Package | Description |
| :--- | :--- | :--- |
| **macOS** | [**`C3D_Explorer_Mac.dmg`**](https://github.com/Mikey6787/c3d-explorer/releases/latest/download/C3D_Explorer_Mac.dmg) | Drag-and-drop disk image for macOS. Open the DMG and drag **C3D Explorer** into your Applications folder. |
| **Windows Installer** | [**`C3D_Explorer_Windows_Setup.exe`**](https://github.com/Mikey6787/c3d-explorer/releases/latest/download/C3D_Explorer_Windows_Setup.exe) | Setup wizard for Windows 10/11. Installs to `Program Files`, adds Start Menu/Desktop shortcuts, and registers `.c3d` file association. |
| **Windows Portable** | [**`C3D_Explorer_Windows_Portable.zip`**](https://github.com/Mikey6787/c3d-explorer/releases/latest/download/C3D_Explorer_Windows_Portable.zip) | Standalone portable archive. Unzip anywhere and run `C3DExplorer.exe` directly without installation. |

---

### Run from Source (macOS, Windows, Linux)
#### Requirements
- Python 3.10, 3.11, 3.12, or 3.13
- Dependencies:
  ```bash
  pip install -r requirements.txt
  ```

#### Launching the Application
Run from the project directory:
```bash
python app.py
```
Or open a specific trial file directly:
```bash
python app.py /path/to/trial.c3d
```

### Building the Windows `.exe` Locally
If you are building on a physical Windows machine:
```cmd
packaging\build_windows.bat
```
This generates the standalone binary in `dist\C3DExplorer\C3DExplorer.exe` and the Inno Setup installer in `dist_installer\C3D_Explorer_Windows_Setup.exe`.

---

## Keyboard Shortcuts
| Shortcut | Action |
|---|---|
| `Space` | Play / Pause |
| `Right Arrow` | Step 1 Frame Forward |
| `Left Arrow` | Step 1 Frame Backward |
| `Home` | Jump to Start Frame |
| `End` | Jump to End Frame |
| `R` | Fit Camera to Data |
| `1` | 3D Isometric View |
| `2` | Top View |
| `3` | Front View |
| `4` | Side View |
| `Ctrl+O` / `Cmd+O` | Open C3D File |
| `Ctrl+S` / `Cmd+S` | Save C3D File |
| `Ctrl+P` / `Cmd+P` | Open Universal Signal & Marker Plotter |
| `Ctrl+E` / `Cmd+E` | Add C3D Event at Current Frame |
| `Ctrl+Q` / `Cmd+Q` | Quit Application |

---

## Author & Developer

**Dr. Mohamadreza Kharazi**  
*Researcher in Biomechanics & Movement Science*  
Universität Koblenz, Germany  

- 🌐 **Biomech-Lab Website:** [biomech-lab.pages.dev](https://biomech-lab.pages.dev/)
- 🔬 **Google Scholar:** [Mohamadreza Kharazi on Google Scholar](https://scholar.google.com/citations?view_op=search_authors&mauthors=Mohamadreza+Kharazi)
- 💼 **LinkedIn:** [mohamadreza-kharazi-23575285](https://www.linkedin.com/in/mohamadreza-kharazi-23575285)
- ☕ **Support the Project:** [Buy Me a Coffee (€5 via PayPal)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=mohamadreza.kharazi%40live.com&currency_code=EUR&amount=5.00&item_name=Buy+Me+a+Coffee+-+C3D+Explorer)

---

## Contributing & Feedback
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/Mikey6787/c3d-explorer/issues) if you want to contribute or report a bug.



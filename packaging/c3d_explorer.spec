# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for C3D Explorer."""

import os
import sys

block_cipher = None

# Locate project root (one level up from packaging/)
spec_dir = os.path.abspath(SPECPATH) if 'SPECPATH' in globals() else os.path.abspath('.')
if os.path.basename(spec_dir) == 'packaging':
    project_dir = os.path.dirname(spec_dir)
else:
    project_dir = spec_dir

# Asset data files to bundle
datas = [
    (os.path.join(project_dir, 'assets'), 'assets'),
]

# Hidden imports required for dynamic/lazy loaded modules
hidden_imports = [
    'ezc3d',
    'numpy',
    'scipy',
    'scipy.signal',
    'scipy.ndimage',
    'scipy.special',
    'OpenGL',
    'OpenGL.platform',
    'OpenGL.platform.win32',
    'OpenGL.arrays.numpymodule',
    'OpenGL.arrays.ctypesarrays',
    'OpenGL.arrays.ctypesparameters',
    'OpenGL.arrays.ctypespointers',
    'pyqtgraph',
    'pyqtgraph.opengl',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtNetwork',
]

a = Analysis(
    [os.path.join(project_dir, 'app.py')],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Detect version from core/__init__.py
version = '1.0.1'
try:
    with open(os.path.join(project_dir, 'core', '__init__.py'), 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                version = line.split('=')[1].strip().strip('"').strip("'")
                break
except Exception:
    pass

# Select appropriate icon for platform
if sys.platform == 'darwin':
    icon_path = os.path.join(project_dir, 'assets', 'icons', 'app.icns')
else:
    icon_path = os.path.join(project_dir, 'assets', 'icons', 'app.ico')

if not os.path.exists(icon_path):
    icon_path = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='C3DExplorer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True if sys.platform != 'darwin' else False,
    console=False,  # Set to False to prevent black terminal window on startup
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True if sys.platform != 'darwin' else False,
    upx_exclude=[],
    name='C3DExplorer',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='C3D Explorer.app',
        icon=icon_path,
        bundle_identifier='com.biomech.c3dexplorer',
        info_plist={
            'CFBundleDisplayName': 'C3D Explorer',
            'CFBundleName': 'C3D Explorer',
            'CFBundlePackageType': 'APPL',
            'CFBundleSignature': '????',
            'CFBundleShortVersionString': version,
            'CFBundleVersion': version,
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15.0',
            'NSRequiresAquaSystemAppearance': False,
        }
    )

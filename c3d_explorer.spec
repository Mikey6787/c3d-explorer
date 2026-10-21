# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for C3D Explorer."""

import os
import sys

block_cipher = None

# Project root directory: PyInstaller defines SPECPATH in globals during spec execution
project_dir = os.path.abspath(SPECPATH) if 'SPECPATH' in globals() else os.path.abspath('.')

# Asset data files to bundle
datas = [
    (os.path.join(project_dir, 'assets'), 'assets'),
]

# Hidden imports required for dynamic/lazy loaded modules
hidden_imports = [
    'ezc3d',
    'numpy',
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
]

a = Analysis(
    ['app.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='C3DExplorer',
)

# -*- mode: python ; coding: utf-8 -*-

import pkgutil
from pathlib import Path
sigmf_module = pkgutil.resolve_name( 'sigmf' )
sigmf_module_dir = Path(sigmf_module.__file__).parent
#print(f"{sigmf_module_dir=}")

sigmf_data_files = [ 
    ( str(sigmf_module_dir/'schema-collection.json'), 'sigmf' ),
    ( str(sigmf_module_dir/'schema-meta.json'), 'sigmf' ),
]

a = Analysis(
    ['outer_main.py'],
    pathex=[
        'src', 
        'subs/pyqtschema/src',      # need to include this because we vendor/subtree pyqtschema
    ],
    binaries=[],
    datas= sigmf_data_files,
    hiddenimports=[],
    hookspath=['build_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='specview',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

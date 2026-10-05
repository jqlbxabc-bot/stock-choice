# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

ak_datas, ak_bins, ak_hidden = collect_all('akshare')
pd_datas, pd_bins, pd_hidden = collect_all('pandas')
np_datas, np_bins, np_hidden = collect_all('numpy')

datas = ak_datas + pd_datas + np_datas + [
    ('config.yaml', '.'),
    ('realtime_selector.py', '.'),
    ('sync_dashboard.py', '.'),
    ('main.py', '.'),
    ('dashboard', 'dashboard'),
    ('docs', 'docs'),
]
binaries = ak_bins + pd_bins + np_bins
hiddenimports = ak_hidden + pd_hidden + np_hidden + [
    'yaml', 'requests', 'flask'
]

a = Analysis(
    ['assistant_launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='A股交易助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

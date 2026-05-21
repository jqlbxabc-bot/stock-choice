# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec文件 - 动态选股系统Web界面（多策略版本）
"""

block_cipher = None

# 添加数据文件
added_files = [
    ('templates', 'templates'),
    ('output', 'output'),
    ('data', 'data'),
    ('strategies', 'strategies'),
    ('utils', 'utils'),
    ('config.yaml', '.'),
    ('README.md', '.'),
]

# 分析启动器脚本
a = Analysis(
    ['启动器.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'flask',
        'web_app',
        'main',
        'pandas',
        'numpy',
        'akshare',
        'yaml',
        'json',
        'os',
        'datetime',
        'socket',
        'webbrowser',
        'threading',
        'time',
        'sys',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 创建PYZ归档
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 创建exe文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='动态选股Web系统-多策略版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件
)
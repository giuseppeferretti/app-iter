# PyInstaller spec — build em modo --onedir (pasta com .exe).
#
# Como rodar (no diretório c:\dev\app_anac\):
#   pip install pyinstaller
#   pyinstaller build.spec
#
# Resultado: dist\AppIter\AppIter.exe
# Inclui: Python runtime + Flet + Supabase + Playwright lib + Pandas + Openpyxl + Cryptography + Requests.
# NAO inclui: browser Chromium do Playwright (o app usa o navegador do usuario via CDP).

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Supabase / dotenv têm sub-módulos lazy que o PyInstaller não detecta sozinho.
hidden = []
for pkg in (
    "supabase",
    "supabase_auth",
    "gotrue",
    "postgrest",
    "storage3",
    "realtime",
    "supafunc",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    "websockets",
    "dotenv",
    "deprecation",
):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

hidden += [
    "flet",
    "pandas",
    "openpyxl",
    "playwright",
    "cryptography",
    "requests",
]

# Data files (templates, configs) das libs que precisam
datas = [
    ("app/assets", "app/assets"),
]
for pkg in ("supabase", "supabase_auth", "gotrue", "postgrest"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    ['app_iter_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AppIter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon='app/assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AppIter',
)

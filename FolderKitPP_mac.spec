# -*- mode: python ; coding: utf-8 -*-
# FolderKit++ 맥 앱(.app) 빌드 설정 [v51]
#
# 맥에서만 돌릴 수 있다(맥 앱은 맥에서만 만들어진다). 보통은 직접 돌리지 않고
# GitHub의 맥 빌드 서버(.github/workflows/build.yml)가 자동으로 돌린다.
#   pip install -r requirements.txt pyinstaller
#   pyinstaller --noconfirm FolderKitPP_mac.spec      → dist/FolderKitPP.app
#
# 윈도 빌드 설정(FolderKitPP.spec)과 다른 점
# - 한 파일(onefile) 대신 폴더형 앱(.app 번들) — 맥은 .app이 곧 "실행 파일 하나"처럼 보이고,
#   onefile은 켤 때마다 임시 폴더에 풀어서 느리고 맥 보안 검사와도 잘 안 맞는다.
# - 아이콘은 .icns
import os as _os
import re as _re
from PyInstaller.utils.hooks import collect_submodules


def _safe_submodules(name):
    try:
        return collect_submodules(name)
    except Exception:
        return []


_hidden = ["send2trash"]
for _optional in ("openpyxl", "xxhash", "pillow_heif", "cv2", "numpy"):
    _hidden += _safe_submodules(_optional)

_datas = [('assets', 'assets')]
if _os.path.isfile(_os.path.join('models', 'face_recognition_sface_2021dec.onnx')):
    _datas.append(('models', 'models'))

# 버전 번호는 src/styles.py의 APP_VERSION에서 읽는다(한 곳에서만 관리)
_ver = "0"
with open(_os.path.join('src', 'styles.py'), encoding='utf-8') as _f:
    _m = _re.search(r'APP_VERSION\s*=\s*"v?([0-9.]+)"', _f.read())
    if _m:
        _ver = _m.group(1)

a = Analysis(
    ['FolderKitPP.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 맥에서 빠진 기능의 무거운 의존성은 넣지 않는다
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FolderKitPP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FolderKitPP',
)

app = BUNDLE(
    coll,
    name='FolderKitPP.app',
    icon='assets/FolderKit_icon.icns',
    bundle_identifier='kr.hs.sunrint.folderkitpp',
    version=_ver,
    info_plist={
        'CFBundleName': 'FolderKit++',
        'CFBundleDisplayName': 'FolderKit++',
        'CFBundleShortVersionString': _ver,
        'CFBundleVersion': _ver,
        'NSHighResolutionCapable': True,          # 레티나 화면에서 선명하게
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '12.0',
        # 사진 폴더 등에 처음 접근할 때 맥이 묻는 창에 보일 설명
        'NSDesktopFolderUsageDescription': 'FolderKit++가 폴더를 정리·동기화하려면 접근이 필요합니다.',
        'NSDocumentsFolderUsageDescription': 'FolderKit++가 폴더를 정리·동기화하려면 접근이 필요합니다.',
        'NSDownloadsFolderUsageDescription': 'FolderKit++가 폴더를 정리·동기화하려면 접근이 필요합니다.',
        'NSRemovableVolumesUsageDescription': 'FolderKit++가 USB 등 외장 드라이브의 폴더를 다루려면 접근이 필요합니다.',
    },
)

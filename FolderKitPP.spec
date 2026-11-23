# -*- mode: python ; coding: utf-8 -*-


# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# [버그 수정] 카르노맵·학교 일정의 엑셀 입출력(openpyxl), 중복 찾기의
# 빠른 스캔(xxhash), 삭제 시 휴지통(send2trash), HEIC 이미지 지원
# (pillow_heif)은 모두 "선택 의존성"이라, 최상단이 아니라 함수 안이나
# try/except로 감싸서 필요할 때만 import한다 — 설치가 안 된 컴퓨터에서도
# 나머지 기능은 정상 동작하게 하려는 것이다. 그런데 PyInstaller의 정적
# 분석은 이렇게 조건부·지연되는 import를 놓치는 경우가 있어서, **빌드
# 컴퓨터에는 분명히 설치돼 있어도 완성된 exe 안에는 빠지는** 일이
# 생긴다(실제로 "라이브러리 없는 노트북에서 엑셀 다운로드가 안 된다"는
# 제보를 받았다 — 그 노트북 문제가 아니라 exe 자체에 안 들어가 있던
# 것이었다). hiddenimports에 명시적으로 적어야 확실히 포함된다.
#
# 빌드 컴퓨터에 아예 설치가 안 된 선택 라이브러리는(그 라이브러리가
# 관련된 기능만 빠진 채) 조용히 건너뛴다 — 지금까지와 같은 "선택
# 의존성" 정책 그대로다.
def _safe_submodules(name):
    try:
        return collect_submodules(name)
    except Exception:
        return []


_hidden = ["send2trash"]
# [v49] cv2·numpy — 인물별 사진첩(얼굴 엔진). 빌드 컴퓨터에 opencv가 있으면 exe에 함께 들어간다.
for _optional in ("openpyxl", "xxhash", "pillow_heif", "cv2", "numpy"):
    _hidden += _safe_submodules(_optional)

# [v49.4] 얼굴 모델(models 폴더)도 exe 안에 넣는다 — 받는 사람은 exe 하나만 있으면 된다.
# 프로젝트 폴더에 models 폴더가 없으면(받지 않았으면) 넣지 않고 넘어간다.
import os as _os
_datas = [('assets', 'assets')]
if _os.path.isfile(_os.path.join('models', 'face_recognition_sface_2021dec.onnx')):
    _datas.append(('models', 'models'))
    print("[FolderKitPP.spec] models 폴더(얼굴 모델)를 exe에 넣습니다.")
else:
    print("[FolderKitPP.spec] models 폴더가 없어 얼굴 모델 없이 빌드합니다(인물 분류는 꺼진 채).")

# [v49.4] 주의: opencv-python(일반판)은 자체 Qt 파일을 갖고 있어 PySide6와 같은 exe에 들어가면
# 실행 시 Qt 충돌이 날 수 있다. 빌드 PC에는 화면 기능을 뺀 opencv-python-headless를 권한다.
try:
    import cv2 as _cv2
    if _os.path.isdir(_os.path.join(_os.path.dirname(_cv2.__file__), 'qt')):
        print("[FolderKitPP.spec] 경고: opencv-python(일반판)이 설치돼 있습니다. PySide6와 충돌할 수 있으니 "
              "pip uninstall opencv-python 후 pip install opencv-python-headless 를 권합니다.")
except Exception:
    print("[FolderKitPP.spec] opencv가 없어 얼굴 엔진 없이 빌드합니다(인물 분류는 꺼진 채).")

a = Analysis(
    ['FolderKitPP.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
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
    name='FolderKitPP',
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
    icon=['assets\\FolderKit_icon.ico'],
)

# -*- coding: utf-8 -*-
"""
FolderKit — 아이콘 등 정적 자산(assets) 경로 해석.
개발 중 `python FolderKit.py`로 바로 실행해도, PyInstaller로 빌드한 exe로
실행해도(이때는 sys._MEIPASS 임시 폴더 기준) 항상 assets 폴더를 찾을 수 있도록 처리.
"""
import os
import sys

if getattr(sys, "frozen", False):
    _PROJECT_ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
else:
    # 이 파일(src/paths.py) 기준 한 단계 위 = 프로젝트 루트
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSETS_DIR = os.path.join(_PROJECT_ROOT, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "FolderKit_icon.ico")

# 얼굴 인식 모델(models 폴더)을 찾는 곳 — [v49] exe 옆, [v49.4] 없으면 exe 안.
# v49.4부터 models 폴더도 exe 안에 함께 넣어 배포한다(한 파일로 끝나게). 다만
# exe 옆에 models 폴더가 있으면 그쪽을 먼저 쓴다 — 모델만 바꿔 끼울 수 있게.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = _PROJECT_ROOT
EXTERNAL_MODELS_DIR = os.path.join(APP_DIR, "models")      # exe(또는 FolderKitPP.py) 옆
BUNDLED_MODELS_DIR = os.path.join(_PROJECT_ROOT, "models")  # exe 안(실행 중 임시 폴더)


def pick_models_dir(external=EXTERNAL_MODELS_DIR, bundled=BUNDLED_MODELS_DIR):
    if os.path.isdir(external) or not os.path.isdir(bundled):
        return external
    return bundled


MODELS_DIR = pick_models_dir()
GEO_DIR = os.path.join(ASSETS_DIR, "geo")

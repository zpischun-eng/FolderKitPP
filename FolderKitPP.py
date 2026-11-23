#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FolderKit++ 실행 진입점.
실제 코드는 src/ 패키지에 모듈별로 정리되어 있다 (styles/config/sync_core/
fs_model/rename_widgets/dialogs/common_widgets/image_edit/main_window/app,
그리고 유틸리티 미니앱들은 src/utils/).
이 파일은 `python FolderKitPP.py`로 바로 실행할 수 있게 해 주는 얇은 실행기다.

파일 이름에 '+' 문자를 쓰지 않은 이유: 명령줄·배치 파일·일부 빌드 도구에서
'+'가 특수 문자로 해석될 수 있어서다. 화면에 보이는 프로그램 이름은
styles.APP_NAME("FolderKit++")을 쓴다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _mac_cv2_path_fix():
    """[v51] 맥 앱(.app) 안에서 opencv(얼굴 엔진)가 "recursion is detected during loading
    of cv2 binary extensions"로 못 불러와지는 문제 우회.
    맥 앱에서는 cv2 패키지(설정 파일)와 실제 바이너리(cv2*.so)가 서로 다른 폴더
    (Resources/cv2 · Frameworks/cv2)에 놓여, opencv의 자체 로더가 바이너리를 못 찾고
    자기 자신을 다시 불러오다 멈춘다. 바이너리가 든 폴더를 import 경로 맨 앞에 두면
    `import cv2`가 그 바이너리를 바로 불러온다(로더를 거치지 않음)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    import glob
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    roots = {base, os.path.join(os.path.dirname(base), "Resources"), os.path.join(os.path.dirname(base), "Frameworks")}
    for root in roots:
        for so in glob.glob(os.path.join(root, "cv2", "**", "cv2*.so"), recursive=True):
            d = os.path.dirname(so)
            if d not in sys.path:
                sys.path.insert(0, d)
            os.environ["FOLDERKIT_CV2_SO"] = so      # 자가 시험 기록용
            return so
    return None


_mac_cv2_path_fix()

from src.app import main

if __name__ == "__main__":
    main()

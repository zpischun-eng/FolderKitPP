# -*- coding: utf-8 -*-
"""
FolderKit — 애플리케이션 진입점: 고정 팔레트 적용 + MainWindow 실행
"""
import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor, QIcon

from .styles import C
from .paths import ICON_PATH
from .main_window import MainWindow
# [v42] HEIC/HEIF 플러그인 등록은 .styles 모듈이 import되는 시점에 이미
# 끝난다 (위 import 문 자체가 그 시점) — 자세한 이유는 styles.py 참고.

# =============================================================================
def apply_fixed_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C.WINDOW_BG))
    pal.setColor(QPalette.WindowText, QColor(C.WINDOW_FG))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f0f2f4"))
    pal.setColor(QPalette.Text, QColor(C.WINDOW_FG))
    pal.setColor(QPalette.Button, QColor(C.WINDOW_BG))
    pal.setColor(QPalette.ButtonText, QColor(C.WINDOW_FG))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffdc"))
    pal.setColor(QPalette.ToolTipText, QColor("#000000"))
    pal.setColor(QPalette.Highlight, QColor(C.LEFT_MAIN))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#888888"))
    # 비활성 상태도 동일하게 고정
    for grp in (QPalette.Disabled, QPalette.Inactive, QPalette.Active):
        pal.setColor(grp, QPalette.Text, QColor(C.WINDOW_FG))
        pal.setColor(grp, QPalette.WindowText, QColor(C.WINDOW_FG))
        pal.setColor(grp, QPalette.Base, QColor("#ffffff"))
    app.setPalette(pal)
    # [v29] 버튼마다 스타일시트로 font-size를 다르게 주다 보니(14px/16px 등),
    # 그 버튼에 마우스를 올렸을 때 뜨는 롤오버 힌트(QToolTip)까지 버튼 글자
    # 크기를 그대로 물려받아 힌트마다 글자 크기가 들쭉날쭉해 보였다. 앱
    # 전체에 QToolTip 전용 스타일을 한 번 지정해, 어떤 버튼 위에서 띄우든
    # 힌트 글자 크기가 항상 12px로 동일하게 나오도록 고정한다.
    app.setStyleSheet(
        "QToolTip{font-size:12px;font-weight:normal;padding:4px 6px;"
        "background-color:#ffffdc;color:#000000;border:1px solid #999999;}")


def selftest(app, win):
    """[v51] 빌드 확인용 — `FolderKitPP --selftest`. 모든 화면과 미니앱을 한 번씩 열어 보고
    문제가 없으면 0, 있으면 1로 끝난다(GitHub의 맥·윈도 빌드 서버가 완성된 앱을 직접
    실행해 확인하는 데 쓴다 — 사람이 눌러 보기 전에 "켜지기는 하는지"를 거른다)."""
    import io
    import traceback
    from .styles import APP_VERSION
    from .platform_info import IS_MAC, IS_WIN
    # 창 없는 exe(윈도)는 print가 어디에도 안 나오므로 결과를 파일에도 적는다
    out = io.StringIO()
    import builtins
    _print = builtins.print

    def print(*a, **k):    # noqa: A001 — 이 함수 안에서만 화면 + 기록 둘 다
        k.pop("flush", None)
        _print(*a, **k, flush=True)
        _print(*a, **k, file=out)

    def _tb():
        out.write(traceback.format_exc())
        traceback.print_exc()
    ok = True
    try:
        win.show()
        app.processEvents()
        for mode in ("sync", "rename", "imgedit", "dupfind", "util", "sync"):
            try:
                win.switch_mode(mode)
                app.processEvents()
                print(f"[selftest] mode {mode}: ok", flush=True)
            except Exception:
                ok = False
                print(f"[selftest] mode {mode}: FAIL", flush=True)
                _tb()
        for app_id in list(win.util_panel.by_id):
            try:
                win.util_panel.open_app(app_id)
                app.processEvents()
                print(f"[selftest] app {app_id}: ok", flush=True)
            except Exception:
                ok = False
                print(f"[selftest] app {app_id}: FAIL", flush=True)
                _tb()
        try:
            from . import face_engine
            st = face_engine.status()
            print(f"[selftest] face engine: {st}", flush=True)
            if os.environ.get("FOLDERKIT_CV2_SO"):
                print(f"[selftest]   cv2 binary: {os.environ['FOLDERKIT_CV2_SO']}", flush=True)
            if st == face_engine.NO_CV2:          # 왜 못 불러오는지 그대로 남긴다
                try:
                    import cv2
                    print(f"[selftest]   cv2 {cv2.__version__} FaceDetectorYN="
                          f"{hasattr(cv2, 'FaceDetectorYN')}", flush=True)
                except BaseException as e:   # noqa: BLE001
                    print(f"[selftest]   import cv2 failed: {type(e).__name__}: {e}", flush=True)
        except Exception as e:
            print(f"[selftest] face engine check skipped: {e}", flush=True)
    except Exception:
        ok = False
        _tb()
    print(f"[selftest] {APP_VERSION} mac={IS_MAC} win={IS_WIN} -> {'PASS' if ok else 'FAIL'}", flush=True)
    log_path = os.environ.get("FOLDERKIT_SELFTEST_LOG")
    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(out.getvalue())
    return 0 if ok else 1


def main():
    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))   # 작업표시줄 아이콘까지 적용
    apply_fixed_palette(app)
    win = MainWindow()
    if "--selftest" in sys.argv:
        sys.exit(selftest(app, win))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

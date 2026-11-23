# -*- coding: utf-8 -*-
"""매뉴얼 제작용 화면 캡처 3차 — 본체 4모드(동기화/이름 변경/이미지 편집/중복 찾기).

[중요] 본체 모드는 실제 QThread(ScanThread 등)를 헤드리스 환경에서 돌리면
이벤트 루프가 영영 멈춘다(직접 재현해서 확인함) — 그래서 스레드를 실제로
띄우는 대신 스레드가 하는 일(스캔 함수)을 메인 스레드에서 동기 호출해
결과를 직접 화면에 꽂아 넣는다. 완료 후 뜨는 모달 확인창(QMessageBox)도
같은 이유로 "자동으로 예/확인을 누른 것"처럼 흉내 낸다.

[참고] PySide6에서는 같은 버튼(addButton으로 만든 QPushButton)이라도
`box.buttons()`로 다시 조회하면 매번 새 파이썬 래퍼 객체가 나올 수 있어
`is` 비교가 어긋난다 — addButton이 실제로 돌려준 파이썬 객체 자체를
기억해 두는 방식(_FakeMsgBox.addButton)으로 우회했다.
"""
import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox as _RealMsgBox

app = QApplication(sys.argv)
from src.main_window import MainWindow, PreviewDialog
from src.sync_core import scan, classify, plan_actions

OUT = os.path.join(_PROJECT_ROOT, "docs", "manual_captures")
DEMO = "/tmp/manual_demo"   # tools/prepare_manual_demo_data.py로 미리 만들어 둔다


def pump(n=10, delay=0.05):
    for _ in range(n):
        app.processEvents()
        time.sleep(delay)


def new_window():
    win = MainWindow()
    win.resize(1500, 950)
    win.show()
    pump(5)
    return win


def snap(widget, filename):
    pump(3)
    widget.grab().save(f"{OUT}/{filename}")
    print(f"저장: {filename}")


class _FakeMsgBox(_RealMsgBox):
    """확인 모달을 자동으로 "예/확인"(맨 처음 추가한 버튼)으로 눌러 준다."""

    def addButton(self, *a, **k):
        b = super().addButton(*a, **k)
        if not hasattr(self, "_added"):
            self._added = []
        self._added.append(b)
        return b

    def exec(self):
        self._auto_clicked = self._added[0] if getattr(self, "_added", None) else None
        return 0

    def clickedButton(self):
        return getattr(self, "_auto_clicked", None)


# ---------------------------------------------------------------- 15. 폴더 동기화(차이 미리보기)
win = new_window()
win.switch_mode("sync")
win.source_path = f"{DEMO}/source"
win.tree_source._full_path = win.source_path
win.dest_path = f"{DEMO}/dest"
win.tree_dest._full_path = win.dest_path
li = scan(win.source_path, True)
ri = scan(win.dest_path, True)
rows = classify(li, ri)
actions = plan_actions(rows, win.cfg.direction, win.cfg.mirror)
dlg = PreviewDialog(actions, win)
dlg.show()
snap(dlg, "15_sync_폴더동기화.png")
dlg.close()
win.close()

# ---------------------------------------------------------------- 16. 이름 변경
win = new_window()
win.switch_mode("rename")
win.source_path = f"{DEMO}/source/문서"
win.tree_source._full_path = win.source_path
win.load_rename_files(win.source_path)
pump(10)
snap(win, "16_rename_이름변경.png")
win.close()

# ---------------------------------------------------------------- 17. 이미지 편집
win = new_window()
win.switch_mode("imgedit")
win.source_path = f"{DEMO}/source/2026년사진/체육대회"
win.tree_source._full_path = win.source_path
win.load_imgedit_folder(win.source_path)
pump(60, 0.1)   # 썸네일 비동기 로딩 대기
snap(win, "17_imgedit_이미지편집.png")
win.close()

# ---------------------------------------------------------------- 18. 중복 찾기
win = new_window()
win.switch_mode("dupfind")
win.dupfind_add_folder(f"{DEMO}/dupfind_target")
pump(3)
with patch.object(_RealMsgBox, "question", return_value=_RealMsgBox.Yes):
    win.on_dupfind_scan_start(True)   # 정밀 스캔 — 이 스레드는 헤드리스에서도 정상 종료된다
for _ in range(30):
    app.processEvents()
    if win.dupfind_thread is None or not win.dupfind_thread.isRunning():
        break
    time.sleep(0.1)
pump(10)
snap(win, "18_dupfind_중복찾기.png")
win.close()

print("\n=== 본체 4모드 캡처 완료 ===")

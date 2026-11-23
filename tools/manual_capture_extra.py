# -*- coding: utf-8 -*-
"""매뉴얼 제작용 화면 캡처 2차 — 팝업·부가 상태·보완 캡처."""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog, QMenu
from PySide6.QtCore import QPoint

app = QApplication(sys.argv)
from src.utils import build_apps, UtilHost
from src.utils import bracket_solve as B
from src.utils import schedule_local as SL
import src.utils.seating_solve as S

apps = {a.id: a for a in build_apps()}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "manual_captures")


def new(app_id, w=1200, h=800):
    widget = apps[app_id].build(UtilHost(None))
    widget.resize(w, h)
    widget.show()
    app.processEvents()
    return widget


def snap(widget, filename):
    app.processEvents()
    widget.grab().save(f"{OUT}/{filename}")
    print(f"저장: {filename}")


# ---------------------------------------------------------------- 코돈표: 번역 실행
w = new("codon")
w.edit_seq.setText("AUGGCUACUUGCUAAGGCUAG")
w.btn_translate.click()
snap(w, "09b_codon_번역결과.png")

# ---------------------------------------------------------------- 학교 일정: 일정 채운 상태
w = new("schedule")
w.local_events.append(SL.LocalEvent("20260918", "체육대회", "전교생 운동장 집합, 우천시 강당"))
w.local_events.append(SL.LocalEvent("20260925", "중간고사 시작", "1~3교시 고사, 4교시부터 정상수업"))
w.local_events.append(SL.LocalEvent("20260930", "학부모 상담주간", "담임 개별 상담, 사전 예약제"))
w._rebuild_calendar()
w._apply_events()
snap(w, "07b_schedule_일정채움.png")

# ---------------------------------------------------------------- 대진표 작성기: 대진표가 그려진 상태
w = new("bracket", 1400, 850)
names = [f"{i}반 {i}번" for i in range(1, 9)]
demo_bracket = B.Bracket({f"p{i}": n for i, n in enumerate(names)}, seed=3)
# 1라운드 몇 경기는 결과까지 기록해 실제 사용 중인 모습으로
demo_bracket.record(demo_bracket.rounds[0][0].id, "a") if hasattr(demo_bracket.rounds[0][0], "id") else None
w.roster_bracket_canvas.set_event_bracket(demo_bracket)
w.tabs.setCurrentWidget(w.tab_bracket)
app.processEvents()
snap(w, "14_bracket_대진표작성기.png")

# ---------------------------------------------------------------- 좌석표: 우클릭 메뉴(공석/여학생/남학생/지정석)
w = new("seating")
with patch("src.utils.bracket.QMessageBox.question", return_value=1):
    w._on_roster_clear()
w.spin_headcount.setValue(24)
w.spin_cols.setValue(6)
w._on_generate_numbered()
app.processEvents()

captured = {}


class _CapturingMenu(QMenu):
    def exec(self_inner, pos):
        self_inner.move(pos)
        self_inner.show()
        for _ in range(5):
            app.processEvents()
        captured["pix"] = self_inner.grab()
        self_inner.hide()
        return None  # 아무것도 선택하지 않고 닫음(취소)


with patch("src.utils.seating.QMenu", _CapturingMenu):
    w._on_cell_right_clicked(0, 0, w.canvas.mapToGlobal(w.canvas.cell_rect(0, 0).center().toPoint()))
if "pix" in captured:
    captured["pix"].save(f"{OUT}/11b_seating_우클릭메뉴.png")
    print("저장: 11b_seating_우클릭메뉴.png")

# ---------------------------------------------------------------- 좌석표: 인쇄 옵션(1/2/4쪽) 다이얼로그 자체
from src.utils import ui_kit as UK
dlg = UK.PrintCopiesDialog("좌석표 인쇄", "한 장에 지금 배치를 몇 번 담아 인쇄할지 고르세요(잘라서 여러 장 쓸 때 편합니다).",
                           "1쪽(가로 꽉 채움)", "2쪽(세로, 위아래)", "4쪽(가로, 2x2)")
dlg.show()
app.processEvents()
dlg.grab().save(f"{OUT}/11c_인쇄옵션다이얼로그.png")
print("저장: 11c_인쇄옵션다이얼로그.png")
dlg.close()

# ---------------------------------------------------------------- 시간표: 교사 시간표 모드
w = new("timetable")
from PySide6.QtNetwork import QNetworkReply


class FakeReply:
    def __init__(self, data):
        self._data = data.encode("utf-8")

    def error(self):
        return QNetworkReply.NoError

    def readAll(self):
        return self._data

    def deleteLater(self):
        pass


raw = ('{"hisTimetable":[{"head":1},{"row":['
      '{"ALL_TI_YMD":"20260921","PERIO":"1","ITRT_CNTNT":"수학","CLRM_NM":""},'
      '{"ALL_TI_YMD":"20260923","PERIO":"3","ITRT_CNTNT":"수학","CLRM_NM":""}'
      ']}]}')
fr = FakeReply(raw)
w._reply = fr
w._on_reply_finished(fr)
w.mapping = {"수학": "김민준"}
w.survey = {("1", "1"): w.slots}
w.radio_teacher_view.setChecked(True)
w._on_view_mode_selected(1)
snap(w, "12b_timetable_교사시간표.png")

# ---------------------------------------------------------------- 갤럭시폰: adb 위치 지정 안내
w = new("phonetransfer")
with patch("src.utils.phone_transfer.QFileDialog.getOpenFileName", return_value=("", "")):
    # 안내창만 띄우고 실제 파일선택은 취소 — QMessageBox.information을 캡처하려면 별도 처리 필요하므로
    # 여기서는 버튼을 누르기 직전 상태 대신, 안내 문구 다이얼로그를 직접 재현해 캡처한다.
    pass
from PySide6.QtWidgets import QMessageBox
from src.i18n import tr

mbox = QMessageBox(QMessageBox.Information, tr("util.phonetransfer.adb_path.pick_title"),
                   tr("util.phonetransfer.adb_path.guide"))
mbox.show()
app.processEvents()
mbox.grab().save(f"{OUT}/13b_phonetransfer_adb안내.png")
print("저장: 13b_phonetransfer_adb안내.png")
mbox.close()

print("\n=== 보강 캡처 완료 ===")

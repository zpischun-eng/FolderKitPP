# -*- coding: utf-8 -*-
"""매뉴얼 제작용 화면 캡처 — 각 미니앱의 기본(대표) 화면."""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from src.utils import build_apps, UtilHost

apps = {a.id: a for a in build_apps()}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "manual_captures")

# 00. 홈 화면(전체 도구 모음) — 개별 미니앱이 아니라 MainWindow 전체를 통해야 한다
from src.main_window import MainWindow

_home_win = MainWindow()
_home_win.resize(1400, 900)
_home_win.show()
app.processEvents()
_home_win.switch_mode("util")
_home_win.util_panel.show_home()
app.processEvents()
_home_win.grab().save(f"{OUT}/00_home_전체도구목록.png")
print("저장: 00_home_전체도구목록.png")
_home_win.close()


def cap(app_id, filename, w=1200, h=800, setup=None):
    app_obj = apps[app_id]
    widget = app_obj.build(UtilHost(None))
    widget.resize(w, h)
    widget.show()
    app.processEvents()
    if setup:
        try:
            setup(widget)
        except Exception as e:
            print(f"  [경고] {app_id} setup 실패: {e}")
        app.processEvents()
    widget.grab().save(f"{OUT}/{filename}")
    print(f"저장: {filename}")
    return widget


# 01. 공학용 계산기 — 계산 이력이 쌓인 상태
def setup_calc(w):
    for expr in ["3*4+5", "sin(pi/2)", "sqrt(2)^2"]:
        w.expr.setText(expr)
        w.calculate()


cap("calc", "01_calc_공학용계산기.png", setup=setup_calc)

# 02. 함수 그래프 — 여러 함수를 겹쳐 그린 상태
def setup_graph(w):
    if w.rows:
        w.rows[0].edit.setText("sin(x)")
        w.rows[0].edit.editingFinished.emit()
    w._add_row_interactive()
    w.rows[-1].edit.setText("cos(x)")
    w.rows[-1].edit.editingFinished.emit()
    w._add_row_interactive()
    w.rows[-1].edit.setText("x^2/10")
    w.rows[-1].edit.editingFinished.emit()


cap("graph", "02_graph_함수그래프.png", setup=setup_graph)

# 03. 극좌표 그래프
def setup_polar(w):
    if hasattr(w, "rows") and w.rows:
        w.rows[0].edit.setText("2*sin(3*theta)")
        w.rows[0].edit.editingFinished.emit()


cap("polar", "03_polar_극좌표그래프.png", setup=setup_polar)

# 04. 카르노맵 — 곱의 합이 실제로 최소화되어 나타난 상태
def setup_kmap(w):
    w.minterm_field.setText("1,2,4,5,6,10")
    w.minterm_field.editingFinished.emit()


cap("kmap", "04_kmap_카르노맵.png", setup=setup_kmap)

# 05. CPU 스케줄링 — 기본 예제가 이미 계산·간트차트까지 채워져 있음
cap("cpusched", "05_cpusched_CPU스케줄링.png")

# 06. 오늘의 급식
cap("meal", "06_meal_오늘의급식.png")

# 07. 학교 일정
cap("schedule", "07_schedule_학교일정.png")

# 08. 나이스 글자수 계산기 — 유의 표현이 감지된 상태
def setup_neiscounter(w):
    w.view.setPlainText(
        "토익 900점을 획득하였고, 전국 수학경시대회에서 금상을 수상함. "
        "서울대학교 진학을 목표로 꾸준히 노력함."
    )


cap("neiscounter", "08_neiscounter_나이스글자수계산기.png", setup=setup_neiscounter)

# 09. 코돈표 계산기
cap("codon", "09_codon_코돈표계산기.png")

# 10. 코돈시뮬레이터 — 기본 예제 문제가 이미 채워져 있음
cap("codonsim", "10_codonsim_코돈시뮬.png")

# 11. 좌석표 — 번호 배치 완료 + 성별 지정
def setup_seating(w):
    import src.utils.seating_solve as S
    w.spin_headcount.setValue(24)
    w.spin_cols.setValue(6)
    w._on_generate_numbered()
    app.processEvents()
    S.set_seat_gender(w.chart, 0, 0, "F")
    S.set_seat_gender(w.chart, 0, 1, "F")
    S.set_seat_gender(w.chart, 1, 3, "vacant")
    w._reserve_seat(3, 5, "7")
    w._redraw()


cap("seating", "11_seating_좌석표.png", setup=setup_seating)

# 12. 시간표 — 학급 시간표(교사명 매핑 포함)
def setup_timetable(w):
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

    subjects = ["수학", "영어", "국어", "통합과학", "체육", "음악"]
    raw = '{"hisTimetable":[{"head":1},{"row":['
    parts = []
    days = ["20260921", "20260922", "20260923", "20260924", "20260925"]
    for i, sub in enumerate(subjects):
        d = days[i % 5]
        p = (i % 4) + 1
        parts.append(f'{{"ALL_TI_YMD":"{d}","PERIO":"{p}","ITRT_CNTNT":"{sub}","CLRM_NM":""}}')
    raw += ",".join(parts) + "]}]}"
    fr = FakeReply(raw)
    w._reply = fr
    w._on_reply_finished(fr)
    w.mapping = {"수학": "김민준", "영어": "이서연", "국어": "박지훈",
                "통합과학": "최수아", "체육": "정도윤", "음악": "강하은"}
    w._render()


cap("timetable", "12_timetable_학급시간표.png", setup=setup_timetable)

# 13. 갤럭시폰 사진 옮기기 — 기본(adb 없음) 안내 화면
cap("phonetransfer", "13_phonetransfer_기본화면.png")

print("\n=== 기본 상태 캡처 완료 ===")

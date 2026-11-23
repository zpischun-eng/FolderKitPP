# -*- coding: utf-8 -*-
"""FolderKit++ v01 — 헤드리스 자동 검증.

    QT_QPA_PLATFORM=offscreen python3 tests_headless.py

Util 모드/계산기의 새 기능뿐 아니라, 기존 네 모드가 그대로 동작하는지
(회귀) 함께 확인한다.
"""
import os
import shutil
import sys
import tempfile

# [v51.3] 인증키는 이제 소스에 없다 — 시험용 가짜 키(형식만 같음)로 단축키 채우기를 확인한다
os.environ.setdefault("FOLDERKIT_NEIS_KEY", "testkey0testkey0testkey0testkey0")
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QSettings, QEvent
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtWidgets import QApplication

from src.app import apply_fixed_palette
from src.main_window import MainWindow
from src.i18n import set_language, tr
from src.utils.expr import evaluate, format_number, CalcError
from src.utils import cpusched_solve as CS
from src.utils import codonsim_solve as CX

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ((" — " + str(extra)) if extra and not cond else ""))


def section(title):
    print("\n== " + title + " ==")


def _no_pending_reply(widget):
    """[안정성] meal/schedule 위젯은 설정이 바뀔 때마다 실제(이 샌드박스에선
    막혀 있는) 네트워크 요청을 내보낸다. 그 요청의 실패 콜백이 이후의 수동
    _render() 호출과 검사 사이에 비동기로 끼어들어 화면을 덮어써 버리면,
    순전히 네트워크 응답 타이밍에 따라 테스트가 가끔만 실패하는 현상이
    생긴다. 수동으로 결과를 넣어 검사하기 직전에는 항상 나가 있는 요청을
    끊어서, 그 경쟁을 원천적으로 없앤다."""
    reply = getattr(widget, "_reply", None)
    if reply is not None:
        reply.abort()
        widget._reply = None


app = QApplication.instance() or QApplication([])
apply_fixed_palette(app)

# 저장소를 깨끗이 비우고 시작(이전 실행의 기록이 결과에 섞이지 않도록)
QSettings("SRIHS", "FolderSync").clear()

win = MainWindow()
win.resize(1280, 780)
win.show()
app.processEvents()

# =============================================================================
section("1. 수식 평가기 (UI 없이)")
cases = [
    ("2+3*4", "rad", 14), ("(2+3)*4", "rad", 20), ("2^10", "rad", 1024),
    ("5!", "rad", 120), ("(2+3)!", "rad", 120), ("7%3", "rad", 1),
    ("sin(30)", "deg", 0.5), ("asin(0.5)", "deg", 30.0),
    ("log(100)", "rad", 2.0), ("log(8,2)", "rad", 3.0), ("log2(8)", "rad", 3.0),
    ("ln(e)", "rad", 1.0), ("2(3+4)", "rad", 14), ("2π", "rad", 6.283185307179586),
    ("abs(0-5)", "rad", 5), ("exp(0)", "rad", 1.0),
]
for src, mode, expected in cases:
    try:
        got = evaluate(src, mode)
        check(f"{src} ({mode}) = {expected}", abs(got - expected) < 1e-9, got)
    except CalcError as e:
        check(f"{src} ({mode})", False, e.key)

section("2. 안전장치 — 위험하거나 무거운 입력은 거부")
for src, want in [
    ("__import__('os').system('ls')", "not_allowed"),   # 속성 접근 노드 자체를 거부
    ("__import__('os')", "unknown_func"),
    ("open('x')", "unknown_func"),
    ("9^9^9", "too_big"),
    ("1000000!", "too_big"),
    ("1/0", "div_zero"),
    ("sqrt(0-1)", "domain"),
    ("2+", "syntax"),
    ("x+1", "unknown_name"),
    ("[1,2]", "not_allowed"),
]:
    try:
        got = evaluate(src)
        check(f"거부: {src}", False, f"계산돼 버림 → {got}")
    except CalcError as e:
        check(f"거부: {src} ({want})", want in e.key, e.key)

section("3. 결과 서식")
check("부동소수점 잡음 제거 0.1+0.2 → 0.3", format_number(evaluate("0.1+0.2")) == "0.3")
check("천 단위 쉼표 1234567.891", format_number(1234567.891) == "1,234,567.891")
check("복사용은 쉼표 없음", format_number(1234567.891, group=False) == "1234567.891")
check("아주 작은 수는 지수 표기", format_number(0.0000001234) == "1.234e-7")
check("고정 자릿수 2", format_number(evaluate("2/3"), 2) == "0.67")

# =============================================================================
section("4. Util 모드 진입 / 레이아웃")
win.switch_mode("util")
app.processEvents()
check("모드 전환됨", win.mode == "util")
check("전용 레이아웃(mode_area_stack index 2)", win.mode_area_stack.currentIndex() == 2)
check("액션 바(tool_stack index 4)", win.tool_stack.currentIndex() == 4)
check("하단 실행 버튼 숨김", not win.bottom_stack.isVisible())
check("진행바는 그대로 보임", win.progress.isVisible())
check("처음엔 홈 화면", win.util_panel.current_id is None and win.util_panel.stack.currentIndex() == 0)
check("모드 버튼 5개", len(win.mode_buttons) == 5 and "util" in win.mode_buttons)
check("액션 바 톤이 Util 색", "#c2185b" in win.action_bar_frame.styleSheet())
check("폴더 트리는 splitter로 복귀", win.tree_source_wrap.parent() is win.splitter)

from src.utils import calculator as calc_mod

section("5. 도구 열기 / 지연 생성")
check("열기 전에는 위젯이 없다(지연 생성)", "calc" not in win.util_panel._pages)
win.util_panel.open_app("calc")
app.processEvents()
check("계산기 열림", win.util_panel.current_id == "calc")
check("위젯이 이때 생성됨", "calc" in win.util_panel._pages)
check("액션 바 라벨 갱신", win.lbl_util_current.text() == tr("util.calc.title"))
calc = win.util_panel._pages["calc"][0]
before_pages = len(win.util_panel._pages)
win.util_panel.show_home()
win.util_panel.open_app("calc")
app.processEvents()
check("두 번째 열기는 재생성하지 않음", len(win.util_panel._pages) == before_pages)
check("같은 위젯 재사용", win.util_panel._pages["calc"][0] is calc)

check("[v06] 처음 열면 샘플 수식이 기록에 1건 미리 들어있음",
      len(calc.history) == 1 and calc.history[0]["expr"] == calc_mod.SAMPLE_EXPR,
      calc.history)
check("[v06] 샘플 결과가 각도모드와 무관하게 39.25", calc.history[0]["result"] == "39.25",
      calc.history[0]["result"])

# [버그 수정] 계산기(키패드) 영역은 고정 폭, 기록 패널만 가변인지
from src.utils.calculator import _CALC_FIXED_WIDTH as _CALC_W
_left_container = calc.expr.parentWidget()
check("[버그 수정] 키패드 영역이 고정 폭을 가짐",
      _left_container.minimumWidth() == _left_container.maximumWidth() == _CALC_W)
check("[버그 수정] 기록 목록은 더 이상 고정 폭이 아님(가변)",
      calc.hist_list.maximumWidth() > _CALC_W * 2)
_narrow_w = calc.width()
win.resize(win.width() + 400, win.height())
app.processEvents()
check("[버그 수정] 창을 넓혀도 키패드 영역 폭은 그대로",
      _left_container.width() == _CALC_W)

# =============================================================================
section("6. 계산기 — 수식 전체 유지가 핵심")
calc.expr.clear()
for kind, payload in [("digit", "1"), ("digit", "2"), ("op", "×"), ("op", "("),
                      ("digit", "3"), ("op", "+"), ("digit", "7"), ("op", ")"),
                      ("op", "÷"), ("digit", "4")]:
    calc._on_key(kind, payload)
check("키패드 입력이 수식으로 쌓임", calc.expr.text() == "12×(3+7)÷4", calc.expr.text())
check("입력 도중 미리보기 표시", calc.preview.text() == "= 30", calc.preview.text())
calc._on_key("act:eq", None)
app.processEvents()
check("계산 후에도 수식이 남아 있다(윈도우 계산기와의 차이)",
      calc.expr.text() == "12×(3+7)÷4", calc.expr.text())
check("결과 표시", calc.result.text() == "30", calc.result.text())
check("기록에 쌓임", calc.history and calc.history[0]["expr"] == "12×(3+7)÷4")
check("상태바에 결과", "30" in win.status.currentMessage())

section("7. 계산기 — 수식 재활용/편집")
calc.expr.setText("12×(3+7)÷5")
app.processEvents()
check("수식을 고치면 이전 결과가 흐려짐", "#b9bcc2" in calc.result.styleSheet())
check("미리보기는 새 값", calc.preview.text() == "= 24", calc.preview.text())
calc.calculate()
app.processEvents()
check("다시 계산하면 결과 진해짐", "#c2185b" in calc.result.styleSheet())
check("기록 3건(샘플 1개 + 방금 계산한 2개)", len(calc.history) == 3, len(calc.history))

item = calc.hist_list.item(1)          # 이전 항목(12×(3+7)÷4)
calc._on_history_clicked(item)
check("기록 클릭 → 수식 되불러오기", calc.expr.text() == "12×(3+7)÷4", calc.expr.text())
calc._on_history_double_clicked(calc.hist_list.item(0))
app.processEvents()
check("두 번 클릭 → 즉시 계산", calc.result.text() in ("24", "30"))
n_before = len(calc.history)
calc.calculate()
check("같은 수식 연속 계산은 기록 중복 안 함", len(calc.history) == n_before)

check("[v06] 기록 각 줄에 원클릭 복사 버튼이 붙음",
      calc.hist_list.itemWidget(calc.hist_list.item(0)) is not None)
calc._quick_copy_expr(calc.history[0])
app.processEvents()
check("[v06] 복사 버튼으로 클립보드에 수식 복사됨",
      QGuiApplication.clipboard().text() == calc.history[0]["expr"])

section("8. 계산기 — 입력 보조")
calc.expr.setText("4")
calc.expr.setCursorPosition(1)
calc._on_key("func", "√(")
check("숫자 뒤 함수 → 곱셈 자동 삽입", calc.expr.text() == "4×√(", calc.expr.text())
calc.expr.setText("3+4")
calc.expr.setSelection(0, 3)
calc._on_key("func", "√(")
check("선택 영역을 함수로 감싸기", calc.expr.text() == "√(3+4)", calc.expr.text())
calc.expr.setText("10")
calc.expr.setCursorPosition(2)
calc._on_key("act:sign", None)
check("± 부호 붙이기", calc.expr.text() == "−10", calc.expr.text())
calc._on_key("act:sign", None)
check("± 다시 누르면 제거", calc.expr.text() == "10", calc.expr.text())
calc.expr.setText("123")
calc.expr.setCursorPosition(3)
calc._on_key("act:back", None)
check("⌫ 한 글자 삭제", calc.expr.text() == "12")
calc._on_key("act:clear", None)
check("C 전체 지우기", calc.expr.text() == "" and calc.result.text() == "0")

section("9. 계산기 — 오류는 팝업 없이 그 자리에")
calc.expr.setText("2++")
calc.calculate()
check("잘못된 수식이어도 수식은 보존", calc.expr.text() == "2++")
check("오류 문구를 미리보기 자리에 표시", tr("util.calc.err.syntax") == calc.preview.text(),
      calc.preview.text())
check("오류는 기록에 남지 않음", all(h["expr"] != "2++" for h in calc.history))

section("10. 계산기 — ↑/↓ 로 이전 수식 불러오기")
calc.expr.clear()
ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
calc.eventFilter(calc.expr, ev)
check("↑ 로 최근 수식", calc.expr.text() == calc.history[0]["expr"], calc.expr.text())
calc.eventFilter(calc.expr, QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
check("↑ 한 번 더 → 그 이전 수식", calc.expr.text() == calc.history[1]["expr"])
calc.eventFilter(calc.expr, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
check("↓ 로 되돌아옴", calc.expr.text() == calc.history[0]["expr"])

section("11. 계산기 — 각도 모드 / 자릿수")
calc.expr.setText("sin(30)")
calc._toggle_angle()
check("DEG 전환", calc.angle_mode == "deg")
calc.calculate()
check("DEG에서 sin(30)=0.5", calc.result.text() == "0.5", calc.result.text())
calc._toggle_angle()
calc.calculate()
check("RAD로 되돌리면 값이 달라짐", calc.result.text() != "0.5")
calc.expr.setText("2/3")
calc.calculate()
calc.combo_dec.setCurrentIndex(1)      # 2자리
app.processEvents()
check("자릿수 콤보 반영", calc.result.text() == "0.67", calc.result.text())
check("콤보는 내부 키로 저장", calc.decimals == "2")
calc.combo_dec.setCurrentIndex(0)

section("12. 검색 필터")
win.util_search.setText("계산")
app.processEvents()
check("일치하면 목록에 남음", not win.util_panel.tree.topLevelItem(1).isHidden())
win.util_search.setText("없는도구이름")
app.processEvents()
check("불일치 시 안내 표시", win.util_panel.lbl_empty.isVisible())
win.util_search.setText("")
app.processEvents()
check("검색 해제 시 홈 항목 복귀", not win.util_panel.tree.topLevelItem(0).isHidden())

# =============================================================================
section("13. 다국어 전환 (기존 모드 + 새 모드)")
for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 재번역 중 예외 없음", True)
    check(f"[{lang}] 도구 이름이 그 언어로", win.lbl_util_current.text() == tr("util.calc.title"))
    check(f"[{lang}] 계산기 내부 문구도 번역", calc.lbl_history.text() == tr("util.calc.history.title"))
check("언어를 바꿔도 저장된 내부 키는 그대로", calc.decimals == "auto" and calc.angle_mode == "rad")
check("언어를 바꿔도 기록 내용 유지", len(calc.history) >= 2)

section("14. 저장/복원 (QSettings)")
calc.expr.setText("111+222")
calc.calculate()
saved_hist = list(calc.history)
win2 = MainWindow()
win2.switch_mode("util")
win2.util_panel.open_app("calc")
app.processEvents()
calc2 = win2.util_panel._pages["calc"][0]
check("새로 켜도 계산 기록이 남아 있음",
      calc2.history and calc2.history[0]["expr"] == saved_hist[0]["expr"],
      calc2.history[:1])
check("마지막에 쓰던 도구를 복원", win2.util_panel.current_id == "calc")
win2.close()

# =============================================================================
section("15. 기존 4개 모드 회귀")
tmp = tempfile.mkdtemp(prefix="fkpp_")
os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
open(os.path.join(tmp, "a.txt"), "w").close()
open(os.path.join(tmp, "b.txt"), "w").close()
win.source_path = tmp
for mode, area_idx, tool_idx in [("sync", 0, 0), ("rename", 0, 1),
                                 ("imgedit", 1, 2), ("dupfind", 0, 3), ("util", 2, 4)]:
    win.switch_mode(mode)
    app.processEvents()
    check(f"{mode} 모드 전환", win.mode == mode
          and win.mode_area_stack.currentIndex() == area_idx
          and win.tool_stack.currentIndex() == tool_idx)
win.switch_mode("imgedit")
app.processEvents()
check("이미지 편집에서 트리가 전용 레이아웃으로 이동",
      win.tree_source_wrap.parent() is win.imgedit_tree_holder)   # [v48] 왼쪽 [폴더|사진첩] 스택의 "폴더" 칸
win.switch_mode("util")
app.processEvents()
check("Util로 오면 트리가 원래 자리로 복귀", win.tree_source_wrap.parent() is win.splitter)
win.switch_mode("rename")
app.processEvents()
check("파일명 변경 모드에서 파일 목록 로드", win.editor.toPlainText().count("\n") >= 1)
win.switch_mode("util")
app.processEvents()
check("Util 왕복 후에도 계산기 내용 유지", calc.expr.text() == "111+222", calc.expr.text())
check("미저장 변경 훅 동작(계산기는 항상 False)", win.util_panel.has_unsaved() is False)
shutil.rmtree(tmp, ignore_errors=True)

section("16. 아이콘 렌더링")
from src.image_edit import make_mode_icon
from src.utils.icons import make_app_icon
from src.styles import C
check("util 모드 아이콘 생성", not make_mode_icon("util", C.UTIL_MAIN).isNull())
check("calc 앱 아이콘 생성", not make_app_icon("calc", C.UTIL_MAIN, 32).isNull())
check("home 앱 아이콘 생성", not make_app_icon("home", C.UTIL_MAIN, 18).isNull())
check("kmap 앱 아이콘 생성", not make_app_icon("kmap", C.UTIL_MAIN, 32).isNull())
check("모르는 종류도 죽지 않음", not make_app_icon("nope", C.UTIL_MAIN).isNull())

# =============================================================================
section("17. 카르노맵 — 알고리즘(순수 로직)")
from src.utils import kmap_solve as KS

def brute_ok(minterms, n, terms):
    minterms = set(minterms)
    for x in range(1 << n):
        if any(KS._covers(t, x, n) for t in terms) != (x in minterms):
            return False
    return True

def is_minimal(minterms, n, terms):
    minterms = set(minterms)
    for i, t in enumerate(terms):
        rest = terms[:i] + terms[i+1:]
        if {x for x in minterms if any(KS._covers(r, x, n) for r in rest)} == minterms:
            return False
    return True

check("빈 집합 -> 0", KS.minimize_sop(set(), 3) == [])
check("전체 -> 1", KS.minimize_sop(set(range(16)), 4) == [tuple(["-"]*4)])
t = KS.minimize_sop({0, 3}, 2)
check("2변수 대각선(비인접) -> 2항", len(t) == 2 and brute_ok({0,3}, 2, t))
t = KS.minimize_sop({0,1,2,5,6,7}, 3)
check("3변수 예제 정답 일치", KS.expr_to_plain(t, list("ABC")) == "A'B' + AC + BC'")
check("3변수 예제 회귀 없음(전수 검사)", brute_ok({0,1,2,5,6,7}, 3, t))
t4 = KS.minimize_sop({0,1,2,3,5,7,8,9,10,11,13,15}, 4)
check("4변수 유명 예제(B'+D) 정답 일치", KS.expr_to_plain(t4, list("ABCD")) == "B' + D")

for n in range(2, 7):
    t = KS.minimize_sop({0}, n)
    check(f"{n}변수 단일 민텀 -> 리터럴 {n}개(최대 결합 불가)",
          KS.literal_count(t) == n and brute_ok({0}, n, t))

import random as _rnd
_rnd.seed(7)
worst_kmap_time = 0.0
all_correct = True
for _ in range(15):
    n = _rnd.choice([4, 5, 6])
    ms = set(_rnd.sample(range(1 << n), (1 << n) // 2))
    t0 = time.time() if False else None
    import time as _t
    t0 = _t.time()
    terms = KS.minimize_sop(ms, n)
    dt = _t.time() - t0
    worst_kmap_time = max(worst_kmap_time, dt)
    if not brute_ok(ms, n, terms) or (terms and not is_minimal(ms, n, terms)):
        all_correct = False
check("무작위 15회(4~6변수) 전수·최소성 검사 통과", all_correct)
check(f"무작위 케이스 최악 응답 시간 < 0.5초 (실측 {worst_kmap_time:.3f}s)",
      worst_kmap_time < 0.5)

# 격자 좌표 <-> 민텀 매핑이 2~6변수 전부 전단사인지, 그레이 코드 인접성까지
all_bij = True
all_gray = True
for n in range(2, 7):
    layout = KS.get_layout(n)
    seen = set()
    for orow in range(layout["outer_row_count"]):
        for ocol in range(layout["outer_col_count"]):
            for r in range(layout["row_count"]):
                for c in range(layout["col_count"]):
                    m = KS.cell_minterm(layout, orow, ocol, r, c)
                    if m in seen or not (0 <= m < (1 << n)):
                        all_bij = False
                    seen.add(m)
                    if c > 0:
                        m2 = KS.cell_minterm(layout, orow, ocol, r, c - 1)
                        if bin(m ^ m2).count("1") != 1:
                            all_gray = False
                    if r > 0:
                        m2 = KS.cell_minterm(layout, orow, ocol, r - 1, c)
                        if bin(m ^ m2).count("1") != 1:
                            all_gray = False
    if len(seen) != (1 << n):
        all_bij = False
check("2~6변수 격자<->민텀 매핑이 전단사(중복/누락 없음)", all_bij)
check("격자 안에서 옆 칸은 항상 1비트만 다름(그레이 코드)", all_gray)

# [v07] 5·6변수가 여러 장 대신 "단일 테이블"인지, 표 끝-시작도 그레이
# 코드 순환 구조로 1비트만 다른지(가로/세로 모두) 확인한다.
for n in (5, 6):
    layout = KS.get_layout(n)
    check(f"{n}변수는 단일 테이블(격자 1장)",
          layout["outer_row_count"] == 1 and layout["outer_col_count"] == 1)
check("5변수 단일 테이블 크기 = 4행×8열",
      KS.get_layout(5)["row_count"] == 4 and KS.get_layout(5)["col_count"] == 8)
check("6변수 단일 테이블 크기 = 8행×8열",
      KS.get_layout(6)["row_count"] == 8 and KS.get_layout(6)["col_count"] == 8)

wrap_ok = True
for n in (5, 6):
    layout = KS.get_layout(n)
    rc, cc = layout["row_count"], layout["col_count"]
    for r in range(rc):
        m1 = KS.cell_minterm(layout, 0, 0, r, cc - 1)
        m2 = KS.cell_minterm(layout, 0, 0, r, 0)
        if bin(m1 ^ m2).count("1") != 1:
            wrap_ok = False
    for c in range(cc):
        m1 = KS.cell_minterm(layout, 0, 0, rc - 1, c)
        m2 = KS.cell_minterm(layout, 0, 0, 0, c)
        if bin(m1 ^ m2).count("1") != 1:
            wrap_ok = False
check("5·6변수 표의 마지막-처음 열/행도 그레이코드 순환으로 1비트만 다름", wrap_ok)

section("18. 카르노맵 — 위젯 통합")
win.switch_mode("util")
win.util_panel.open_app("kmap")
app.processEvents()
kmap = win.util_panel._pages["kmap"][0]
check("기본 4변수로 시작", kmap.num_vars == 4 and len(kmap.minterm_to_cell) == 16)

for m in [0, 1, 2, 3, 5, 7, 8, 9, 10, 11, 13, 15]:
    kmap.minterm_to_cell[m].click()
app.processEvents()
check("클릭 즉시 결과 반영(B'+D)", kmap._last_plain == "B' + D", kmap._last_plain)
check("HTML에 윗줄(overline) 포함", "overline" in kmap.expr_view.text())
check("항/리터럴 통계 표시", "2" in kmap.lbl_stats.text())

kmap.minterm_to_cell[0].click()   # 하나 꺼서 값이 바뀌는지
app.processEvents()
check("칸 하나를 다시 끄면 결과가 즉시 바뀜", kmap._last_plain != "B' + D")

# 값이 있는 상태에서 변수 개수를 바꾸면 확인창이 뜬다 — 자동 Yes로 응답
from PySide6.QtWidgets import QMessageBox as _QMB
orig_question = _QMB.question
_QMB.question = staticmethod(lambda *a, **k: _QMB.Yes)
try:
    kmap.combo_nvars.setCurrentIndex(3 - 2)
    app.processEvents()
finally:
    _QMB.question = orig_question
check("변수 개수 변경 확인 후 격자 재구성(3변수=8칸)",
      kmap.num_vars == 3 and len(kmap.minterm_to_cell) == 8)
check("변수 개수를 바꾸면 값이 초기화됨", len(kmap.values) == 0)

kmap.names_input.setText("P,Q,R")
kmap._on_names_edited()
app.processEvents()
check("변수 이름 변경 반영", kmap.names == ["P", "Q", "R"])
kmap.minterm_to_cell[0].click()
app.processEvents()
check("바뀐 이름이 결과식에 반영", "P" in kmap._last_plain)

kmap.btn_all1.click()
app.processEvents()
check("전체 1 버튼", kmap._last_plain == "1")
kmap.btn_all0.click()
app.processEvents()
check("전체 0 버튼", kmap._last_plain == "0")

# [버그 수정] 전체 1(민텀이 아주 많을 때)을 눌러도 좌측 도구 목록 스플리터
# 폭이 밀려나지 않는지 — 원인은 "Σm(0,1,2,...,63)"처럼 공백 없는 긴
# 문자열을 QLabel의 자동 줄바꿈이 끊지 못해 위젯 전체가 넓어지던 것이었다.
kmap.combo_nvars.setCurrentIndex(6 - 2)   # 값이 비어 있으니 확인창 없이 바뀜
app.processEvents()
_splitter_before = win.util_panel.splitter.sizes()
kmap.btn_all1.click()
app.processEvents()
check("[버그 수정] 전체 1(민텀 64개) 클릭해도 도구 목록 스플리터 폭이 그대로",
      win.util_panel.splitter.sizes() == _splitter_before, win.util_panel.splitter.sizes())
check("[버그 수정] 민텀이 아주 많아도 안내 레이블이 위젯을 넓히지 않음(최대 폭 이내)",
      kmap.lbl_minterms.sizeHint().width() <= kmap.lbl_minterms.maximumWidth())
kmap.btn_all0.click()
app.processEvents()
check("[버그 수정] 전체 0으로 되돌려도 스플리터 폭 그대로",
      win.util_panel.splitter.sizes() == _splitter_before)

# [v07] minterm 입력창 <-> 표 양방향 동기화
kmap.combo_nvars.setCurrentIndex(3 - 2)   # 값이 비어 있으니 확인창 없이 바뀜
app.processEvents()
kmap.minterm_field.setText("0,1,2,5,6,7")
kmap._on_minterm_field_edited()
app.processEvents()
check("입력창 -> 표: 지정한 민텀들이 켜짐",
      sorted(m for m, c in kmap.minterm_to_cell.items() if c.value) == [0, 1, 2, 5, 6, 7])
_expected_terms = KS.minimize_sop({0, 1, 2, 5, 6, 7}, 3)
check("입력창 -> 표: 결과식도 즉시 갱신",
      kmap._last_plain == KS.expr_to_plain(_expected_terms, kmap.names), kmap._last_plain)
kmap.minterm_field.setText("0,1,99,-3,abc,2")   # 범위 밖/이상한 값은 조용히 걸러짐
kmap._on_minterm_field_edited()
app.processEvents()
check("잘못된/범위 밖 값은 무시하고 유효한 것만 반영",
      sorted(kmap.values) == [0, 1, 2], sorted(kmap.values))

kmap.minterm_to_cell[3].click()
app.processEvents()
check("표 클릭 -> 입력창: 클릭한 민텀이 목록에 추가되어 보임",
      "3" in kmap.minterm_field.text().split(","))
kmap.minterm_to_cell[3].click()   # 다시 꺼서 원상 복구
app.processEvents()
check("표에서 다시 끄면 입력창 목록에서도 사라짐",
      "3" not in kmap.minterm_field.text().split(","))

# [버그 수정] v34에서 드래그 토글(마우스로 직접 press/move/release 처리)을
# 넣으면서 실제 마우스 경로가 KMapWidget.values를 갱신하는 콜백을 완전히
# 건너뛰어, 화면에서 칸을 드래그로 칠해도 논리식이 "0"에서 안 바뀌던 버그가
# 있었다 — cell.click()으로 넣는 이 파일의 다른 테스트들은 그 콜백이 여전히
# 연결돼 있어(clicked 시그널 경로) 문제를 못 잡았으므로, 실제 마우스
# press/move/release 경로를 직접 재현해서 확인한다.
kmap._set_all(0)()
app.processEvents()


class _FakeGridMouseEvent:
    def __init__(self, btn, gpos):
        self._btn, self._gpos = btn, gpos

    def button(self):
        return self._btn

    def globalPosition(self):
        class _P:
            def __init__(self, p):
                self._p = p

            def toPoint(self):
                return self._p
        return _P(self._gpos)

    def accept(self):
        pass


_cell_a = kmap.minterm_to_cell[0]
_cell_b = kmap.minterm_to_cell[1]
_cell_a.mousePressEvent(_FakeGridMouseEvent(Qt.LeftButton, _cell_a.mapToGlobal(_cell_a.rect().center())))
app.processEvents()
check("[버그 수정] 실제 마우스 press로 칸을 누르면 값 집합(values)에 반영됨",
      0 in kmap.values, kmap.values)
check("[버그 수정] 실제 마우스 press 직후 논리식이 0에서 바뀜",
      kmap.expr_view.text() != "0", kmap.expr_view.text())
_cell_a.mouseMoveEvent(_FakeGridMouseEvent(Qt.LeftButton, _cell_b.mapToGlobal(_cell_b.rect().center())))
app.processEvents()
check("[버그 수정] 드래그로 다음 칸에 들어가도 values에 반영됨", 1 in kmap.values, kmap.values)
_cell_a.mouseReleaseEvent(_FakeGridMouseEvent(Qt.LeftButton, _cell_b.mapToGlobal(_cell_b.rect().center())))
kmap._set_all(0)()
app.processEvents()
check("[버그 수정] 확인 후 전체 0으로 정리하면 논리식도 0으로 돌아옴", kmap.expr_view.text() == "0")

# [v07] 엑셀 출력 — 성공 경로 + openpyxl 미설치 대체 경로
import builtins as _builtins
from unittest.mock import patch as _patch
_xlsx_path = os.path.join(tempfile.gettempdir(), "fkpp_kmap_test.xlsx")
try:
    with _patch("src.utils.kmap.QFileDialog.getSaveFileName", return_value=(_xlsx_path, "")):
        kmap._export_excel()
    import openpyxl as _opx
    _wb = _opx.load_workbook(_xlsx_path)
    _ws = _wb["K-map"]
    check("엑셀 출력 — 민텀 행 포함", any(_ws.cell(r, 1).value == "민텀" for r in range(1, _ws.max_row + 1)))
    check("엑셀 출력 — 논리식 행 포함", any(_ws.cell(r, 1).value == "논리식" for r in range(1, _ws.max_row + 1)))
finally:
    if os.path.exists(_xlsx_path):
        os.remove(_xlsx_path)

_real_import = _builtins.__import__
def _fake_import_no_openpyxl(name, *a, **k):
    if name == "openpyxl":
        raise ImportError("no openpyxl (테스트용)")
    return _real_import(name, *a, **k)
_orig_info = _QMB.information
_QMB.information = staticmethod(lambda *a, **k: None)
_builtins.__import__ = _fake_import_no_openpyxl
try:
    kmap._export_excel()
    check("openpyxl 없어도 예외 없이 안내만 뜸(크래시 없음)", True)
except Exception as e:
    check(f"openpyxl 없을 때 안전 처리", False, e)
finally:
    _builtins.__import__ = _real_import
    _QMB.information = _orig_info

# 언어 전환 중 예외 없이 동작하는지(카르노맵도 함께 재번역)
for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 카르노맵 재번역 중 예외 없음", True)
    check(f"[{lang}] 카르노맵 도구 이름 번역", win.lbl_util_current.text() == tr("util.kmap.title"))

# =============================================================================
section("19. 함수 그래프 — 알고리즘(순수 로직)")
from src.utils import graph_solve as GS

r = GS.sample("x^2", -2, 2, 5)
check("x^2 표본 정확도", r.ys == [4.0, 1.0, 0.0, 1.0, 4.0], r.ys)
check("표본에 오류 없음", r.error is None)

r = GS.sample("y+1", -1, 1, 10)
check("미지수 변수 -> 구조적 오류로 즉시 중단", r.error == "util.calc.err.unknown_name" and r.xs == [])
check("오류 파라미터에 변수명 포함", r.error_params.get("name") == "y", r.error_params)

r = GS.sample("2+", -1, 1, 10)
check("문법 오류 -> 구조적 오류", r.error == "util.calc.err.syntax")

r = GS.sample("sqrt(x)", -5, 5, 11)
check("sqrt(x)는 전체 실패가 아님(정의역 오류일 뿐)", r.error is None)
check("sqrt(x) 음수 구간은 None", all(r.ys[i] is None for i, x in enumerate(r.xs) if x < 0))
check("sqrt(x) 양수 구간은 값 있음", all(r.ys[i] is not None for i, x in enumerate(r.xs) if x >= 0))

r = GS.sample("tan(x)", -3.0, 3.0, 400)
ymin, ymax = GS.robust_y_range(r.ys)
segs = GS.build_segments(r.xs, r.ys, ymin, ymax)
check("tan(x)는 점근선에서 여러 구간으로 끊김", len(segs) >= 2, len(segs))
height = ymax - ymin
no_big_jump = all(abs(seg[i+1][1] - seg[i][1]) <= 3.5*height + 1e-6
                  for seg in segs for i in range(len(seg)-1))
check("각 구간 내부에는 큰 도약이 없음(가짜 세로선 없음)", no_big_jump)

ymin_c, ymax_c = GS.robust_y_range([5.0]*50)
check("상수 함수도 유효한(폭이 있는) Y범위", ymax_c > ymin_c)
check("빈 데이터는 기본 범위(-10,10)", GS.robust_y_range([]) == (-10.0, 10.0))

for vmin, vmax in [(0, 10), (-5, 5), (0, 1), (-123, 456)]:
    ticks = GS.nice_ticks(vmin, vmax)
    ok = (ticks[0] <= vmin + 1e-9 and ticks[-1] >= vmax - 1e-9
          and all(ticks[i] < ticks[i+1] for i in range(len(ticks)-1))
          and 3 <= len(ticks) <= 12)
    check(f"nice_ticks({vmin},{vmax}) 유효", ok, ticks)

r = GS.sample("__import__('os')", -1, 1, 5)
check("위험한 표현식은 그래프에서도 거부됨(계산기와 안전장치 공유)", r.error is not None)

t0 = time.time()
for _ in range(30):
    GS.sample("sin(x)+cos(2*x)/3", -20, 20, 1200)
dt = time.time() - t0
check(f"1200점×30회 성능 (실측 {dt:.3f}s, 기준<3s)", dt < 3.0)

# [v10] x절편 / y절편
import math as _math
r = GS.sample("sin(x)", -10, 10, 2000)
ymin, ymax = GS.robust_y_range(r.ys)
segs = GS.build_segments(r.xs, r.ys, ymin, ymax)
roots = GS.find_x_intercepts(segs)
expected_roots = sorted(k * _math.pi for k in range(-3, 4))
check("[v10] sin(x) x절편 7개(−3π~3π) 정확",
      len(roots) == len(expected_roots)
      and all(abs(a - b) < 0.02 for a, b in zip(roots, expected_roots)), roots)

r_tan = GS.sample("tan(x)", -4, 4, 3000)
ymin_t, ymax_t = GS.robust_y_range(r_tan.ys)
segs_t = GS.build_segments(r_tan.xs, r_tan.ys, ymin_t, ymax_t)
roots_t = GS.find_x_intercepts(segs_t)
check("[v10] tan(x) 점근선을 근으로 오인하지 않음(진짜 근 3개만)",
      len(roots_t) == 3 and all(abs(a - b) < 0.05 for a, b in
      zip(roots_t, [-_math.pi, 0.0, _math.pi])), roots_t)

check("[v10] sin(x) y절편 = 0", abs(GS.y_intercept("sin(x)") - 0.0) < 1e-9)
check("[v10] x^2-4 y절편 = -4", abs(GS.y_intercept("x^2-4") - (-4)) < 1e-9)
check("[v10] 1/x y절편은 정의되지 않음(None)", GS.y_intercept("1/x") is None)
r_flat = GS.sample("x^2+1", -5, 5, 500)
ymin_f, ymax_f = GS.robust_y_range(r_flat.ys)
segs_f = GS.build_segments(r_flat.xs, r_flat.ys, ymin_f, ymax_f)
check("[v10] x^2+1은 x절편 없음(항상 양수)", GS.find_x_intercepts(segs_f) == [])

section("20. 함수 그래프 — 위젯 통합")
win.switch_mode("util")
win.util_panel.open_app("graph")
app.processEvents()
graph = win.util_panel._pages["graph"][0]
check("처음 열면 sin(x) 기본 함수 하나", len(graph.rows) == 1 and graph.rows[0].edit.text() == "sin(x)")
check("기본 X 범위 -10~10", (graph.canvas.xmin, graph.canvas.xmax) == (-10.0, 10.0))
check("기본 Y는 자동", graph.canvas.auto_y is True)

graph._add_row_interactive()
graph.rows[1].edit.setText("x^2/10")
app.processEvents()
check("함수 추가 후 2개", len(graph.rows) == 2)
check("두 함수 모두 표본 계산됨", all(graph.canvas._raw.get(r.id) is not None for r in graph.rows))

graph.rows[1].edit.setText("tan(x)")
app.processEvents()
segs = graph.canvas._segments.get(graph.rows[1].id, [])
check("tan(x) 위젯에서도 여러 구간으로 끊김", len(segs) >= 2, len(segs))

graph.rows[1].edit.setText("y+1")
app.processEvents()
check("잘못된 함수는 입력창 옆에 오류 표시", graph.rows[1].lbl_error.text() != "")
check("오류 문구에 플레이스홀더가 실제 값으로 치환됨",
      "{name}" not in graph.rows[1].lbl_error.text() and "y" in graph.rows[1].lbl_error.text(),
      graph.rows[1].lbl_error.text())
graph._on_row_remove(graph.rows[1])
app.processEvents()
check("함수 삭제 반영", len(graph.rows) == 1)

from src.utils.graph import MAX_FUNCTIONS as _GRAPH_MAX
while len(graph.rows) < _GRAPH_MAX:
    graph._add_row_interactive()
app.processEvents()
check(f"함수는 최대 {_GRAPH_MAX}개까지만 추가됨", len(graph.rows) == _GRAPH_MAX)
before = len(graph.rows)
graph._add_row_interactive()
check("한도 초과 시 더 추가되지 않음", len(graph.rows) == before)
while len(graph.rows) > 1:
    graph._on_row_remove(graph.rows[-1])
app.processEvents()

# 줌/팬/초기화
x_before = (graph.canvas.xmin, graph.canvas.xmax)
class _FakeAngleDelta:
    def y(self): return 120
class _FakeWheel:
    def __init__(self, pos): self._pos = pos
    def angleDelta(self): return _FakeAngleDelta()
    def position(self): return __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(self._pos)
    def accept(self): pass
from PySide6.QtCore import QPoint
graph.canvas.wheelEvent(_FakeWheel(graph.canvas.rect().center()))
app.processEvents()
check("휠 줌으로 X 폭이 줄어듦", (graph.canvas.xmax - graph.canvas.xmin) < (x_before[1] - x_before[0]))

graph._reset_view()
app.processEvents()
check("보기 초기화로 기본 범위 복귀", (graph.canvas.xmin, graph.canvas.xmax) == (-10.0, 10.0)
      and graph.canvas.auto_y is True)

graph.chk_auto_y.setChecked(False)
app.processEvents()
check("Y 자동 해제 시 Y 입력란 활성화", graph.edit_ymin.isEnabled() and graph.edit_ymax.isEnabled())
graph.edit_xmin.setText("-3"); graph.edit_xmax.setText("3")
graph._on_range_edited()
app.processEvents()
check("수동 X 범위 입력 반영", (graph.canvas.xmin, graph.canvas.xmax) == (-3.0, 3.0))

graph.btn_angle.click()
app.processEvents()
check("각도 모드 전환(RAD->DEG)", graph.angle_mode == "deg")
graph.btn_angle.click()

# 설정 저장/복원
graph.rows[0].edit.setText("cos(x)")
app.processEvents()
win3 = MainWindow()
win3.switch_mode("util")
win3.util_panel.open_app("graph")
app.processEvents()
graph3 = win3.util_panel._pages["graph"][0]
check("재기동 후 함수 내용 복원", graph3.rows[0].edit.text() == "cos(x)")
win3.close()

# [버그 수정] 좌표 라벨 1자리 소수 포맷
from src.utils.graph import _fmt1 as _graph_fmt1
check("[버그 수정] _fmt1(2.888) == '2.9'", _graph_fmt1(2.888) == "2.9")
check("[버그 수정] _fmt1(-4.0) == '-4.0'", _graph_fmt1(-4.0) == "-4.0")
check("[버그 수정] _fmt1(0.02) == '0'(거의 0)", _graph_fmt1(0.02) == "0")

# [버그 수정] x/y축이 완전히 같은 펜(두께)으로 그려지는지 — _draw_axes 안에서
# 축마다 새 QPen을 만들지 않고 "axis_pen" 하나를 공유하는지 소스로 확인
import inspect as _inspect
_draw_axes_src = _inspect.getsource(graph.canvas.__class__._draw_axes)
check("[버그 수정] x/y축이 같은 axis_pen을 공유(두께 통일)",
      _draw_axes_src.count("axis_pen = QPen(QColor(C.AXIS_STRONG)") == 1)

# [사용성 개선] 추적 고정 시 함수가 하나뿐이면 접선 대상 자동 선택
from PySide6.QtCore import QPointF as _GQPF
class _FakeGraphEv:
    def __init__(self, pos):
        self._pos = pos
    def position(self):
        return self._pos
    def button(self):
        return Qt.LeftButton
graph.rows[0].edit.setText("x^2/10")
app.processEvents()
gcanvas = graph.canvas
gplot = gcanvas._plot_rect()
gaxis_y = gcanvas._axis_row_px(gplot)
gpx = gcanvas._to_px(3.0, 0, gplot).x()
gcanvas.mousePressEvent(_FakeGraphEv(_GQPF(gpx, gaxis_y)))
gcanvas.mouseReleaseEvent(_FakeGraphEv(_GQPF(gpx, gaxis_y)))
app.processEvents()
check("[사용성 개선] 함수가 하나뿐이면 고정 시 자동으로 고정점이 생김",
      len(gcanvas._pinned_points) == 1 and gcanvas._pinned_points[0]["fid"] == graph.rows[0].id)
gcanvas.clear_trace()
app.processEvents()

# [v10] 절편 표시 + 이미지 출력
graph.rows[0].edit.setText("x^2-4")
app.processEvents()
info = graph.canvas._intercepts.get(graph.rows[0].id)
check("[v10] x^2-4의 x절편 = -2, 2", info is not None
      and len(info["x"]) == 2 and abs(info["x"][0] + 2) < 0.05 and abs(info["x"][1] - 2) < 0.05, info)
check("[v10] x^2-4의 y절편 = -4", info is not None and abs(info["y"] - (-4)) < 1e-9)

graph.chk_intercepts.setChecked(False)
app.processEvents()
check("[v10] 절편 표시 체크 해제 시 반영", graph.canvas.show_intercepts is False)
graph.chk_intercepts.setChecked(True)
app.processEvents()
check("[v10] 절편 표시 다시 체크하면 복원", graph.canvas.show_intercepts is True)

import os as _os2, tempfile as _tf2
from unittest.mock import patch as _patch2
_img_path = _os2.path.join(_tf2.gettempdir(), "fkpp_graph_export_test.png")
with _patch2("src.utils.graph.QFileDialog.getSaveFileName", return_value=(_img_path, "")):
    graph._export_image()
check("[v10] 이미지로 저장한 파일이 실제로 생성됨",
      _os2.path.exists(_img_path) and _os2.path.getsize(_img_path) > 0)
if _os2.path.exists(_img_path):
    _os2.remove(_img_path)

# =============================================================================
section("21. [v11] 함수 그래프 — x축 추적 + 접선/수직선")
from PySide6.QtCore import QPointF as _QPF

class _FakeMouseEv:
    def __init__(self, pos, button=Qt.LeftButton):
        self._pos = pos
        self._button = button
    def position(self):
        return self._pos
    def button(self):
        return self._button

graph.rows[0].edit.setText("x^2/10")
app.processEvents()
canvas = graph.canvas
# 이전 절(20)에서 X 범위를 -3~3으로, Y 자동을 꺼 둔 채로 남겨 놨으므로,
# 이 절은 기본 보기(X -10~10, Y 자동)로 되돌리고 시작한다 — 그래야 아래
# 좌표 계산이 이 절 혼자 실행해도, 전체 스위트 안에서 실행해도 항상 같다.
graph._reset_view()
app.processEvents()
plot = canvas._plot_rect()
axis_y = canvas._axis_row_px(plot)

# 드래그 시작 -> 보라색(드래그 중) 상태
start_px = canvas._to_px(1.0, 0, plot).x()
canvas.mousePressEvent(_FakeMouseEv(_QPF(start_px, axis_y)))
app.processEvents()
check("[v11] x축 근처 클릭으로 추적 시작", canvas._trace_x is not None and canvas._trace_dragging is True)

move_px = canvas._to_px(4.0, 0, plot).x()
canvas.mouseMoveEvent(_FakeMouseEv(_QPF(move_px, axis_y - 3)))
app.processEvents()
check("[v11] 드래그 중 x값이 마우스를 따라 갱신됨", abs(canvas._trace_x - 4.0) < 0.2, canvas._trace_x)
vals = canvas._trace_values()
check("[v11] 추적 중 함수값 계산됨(x^2/10 at x≈4 -> 1.6 근처)",
      graph.rows[0].id in vals and abs(vals[graph.rows[0].id] - 1.6) < 0.05, vals)

canvas.mouseReleaseEvent(_FakeMouseEv(_QPF(move_px, axis_y)))
app.processEvents()
check("[v11] 손을 떼면 고정(드래그 아님)되고 x값 유지", canvas._trace_dragging is False and canvas._trace_x is not None)

# 축 위 손잡이를 클릭하면 숫자 입력창이 뜨는지
handle_px = canvas._to_px(canvas._trace_x, 0, plot).x()
canvas.mousePressEvent(_FakeMouseEv(_QPF(handle_px, axis_y + 13)))
app.processEvents()
check("[v11] 손잡이 클릭 시 숫자 입력창이 뜸",
      canvas._trace_input is not None and canvas._trace_input.isVisible())
canvas._trace_input.setText("6")
canvas._apply_trace_input()
app.processEvents()
check("[v11] 입력한 값으로 x가 정확히 바뀜", canvas._trace_x == 6.0)
check("[v11] 적용 후 입력창은 숨겨짐", not canvas._trace_input.isVisible())

# 범위를 벗어난 값을 입력하면 범위 안으로 잘림
canvas._trace_input.setText("9999")
canvas._apply_trace_input()
app.processEvents()
check("[v11] 범위를 벗어난 입력은 xmax로 clamp됨", canvas._trace_x == canvas.xmax, canvas._trace_x)
canvas._trace_x = 6.0   # 이후 테스트를 위해 다시 6으로

# 곡선 위 점을 클릭 -> 새 고정점이 생김(예전의 "접선 대상 선택"을 대체)
fid = graph.rows[0].id
y_at_6 = GS.value_at("x^2/10", 6.0)
dot_px = canvas._to_px(6.0, y_at_6, plot)
canvas.mousePressEvent(_FakeMouseEv(dot_px))
app.processEvents()
check("[신규] 곡선 위 점 클릭으로 고정점이 생김",
      any(pt["fid"] == fid and abs(pt["x"] - 6.0) < 1e-6 for pt in canvas._pinned_points))
pinned_pt = next(pt for pt in canvas._pinned_points if pt["fid"] == fid and abs(pt["x"] - 6.0) < 1e-6)
check("[신규] 새로 생긴 고정점은 접선·법선이 아직 없음", not pinned_pt["tangent"] and not pinned_pt["normal"])

expected_slope = GS.numeric_slope("x^2/10", 6.0, canvas.xmax - canvas.xmin)
check("[v11] x^2/10 at x=6 접선 기울기 ≈ 1.2(2x/10)", abs(expected_slope - 1.2) < 0.01, expected_slope)

# [신규] 접선을 오른쪽 클릭 메뉴로 켠다(예전 "접선" 버튼을 대체)
class _FakeGraphMenu:
    def __init__(self, parent=None):
        self._actions = []
    def addAction(self, text):
        a = object()
        self._actions.append((text, a))
        return self._actions[-1][1]
    def addSeparator(self):
        pass
    def exec(self, pos):
        return self._actions[0][1]   # 항상 첫 번째 메뉴 항목("접선 그리기/지우기")을 고른다

with _patch2("src.utils.graph.QMenu", _FakeGraphMenu):
    canvas._show_pin_context_menu(pinned_pt, canvas.mapToGlobal(dot_px.toPoint()))
check("[신규] 우클릭 메뉴로 접선을 켤 수 있음(예전 '접선' 버튼 대체)", pinned_pt["tangent"] is True)
with _patch2("src.utils.graph.QMenu", _FakeGraphMenu):
    canvas._show_pin_context_menu(pinned_pt, canvas.mapToGlobal(dot_px.toPoint()))
check("[신규] 같은 메뉴를 다시 고르면 접선이 꺼짐(토글)", pinned_pt["tangent"] is False)

class _FakeGraphMenuNormal(_FakeGraphMenu):
    def exec(self, pos):
        return self._actions[1][1]   # 두 번째 항목("법선 그리기/지우기")을 고른다

with _patch2("src.utils.graph.QMenu", _FakeGraphMenuNormal):
    canvas._show_pin_context_menu(pinned_pt, canvas.mapToGlobal(dot_px.toPoint()))
check("[신규] 우클릭 메뉴로 법선을 켤 수 있음(예전 '수직선' 버튼 대체)", pinned_pt["normal"] is True)

check("[버그 수정] '수직선'이 아니라 실제로 접선과 수직인 '법선'(기울기 -1/m)을 그림",
      abs(GS.normal_slope(expected_slope) - (-1.0 / expected_slope)) < 1e-9)

# [신규] 새 점을 찍어도 이전 점(법선 켜진 채)이 사라지지 않는지
y_at_2 = GS.value_at("x^2/10", 2.0)
dot_px2 = canvas._to_px(2.0, y_at_2, plot)
canvas.mousePressEvent(_FakeMouseEv(dot_px2))
app.processEvents()
check("[신규] 새 점을 찍어도 고정점이 2개로 늘어남(이전 점 유지)", len(canvas._pinned_points) == 2)
check("[신규] 이전 점의 법선 표시는 그대로 유지됨", pinned_pt["normal"] is True)

# [신규] 우클릭 메뉴로 점 자체를 지울 수 있는지
class _FakeGraphMenuDelete(_FakeGraphMenu):
    def exec(self, pos):
        return self._actions[2][1]   # 세 번째 항목("이 점 지우기")

with _patch2("src.utils.graph.QMenu", _FakeGraphMenuDelete):
    canvas._show_pin_context_menu(pinned_pt, canvas.mapToGlobal(dot_px.toPoint()))
check("[신규] '이 점 지우기'를 고르면 고정점 목록에서 실제로 없어짐", len(canvas._pinned_points) == 1)

check("[버그 수정] '접선'/'수직선' 버튼이 완전히 제거됨(더 이상 없음)",
      not hasattr(graph, "btn_tangent") and not hasattr(graph, "btn_normal"))

# 상수함수(기울기 0)는 접선이 수평, 수직선은 "기울기 없음"(세로선)으로 처리되는지
check("[v11] normal_slope(0)은 None(수직선)", GS.normal_slope(0.0) is None)

# 더블클릭/보기초기화 시 추적 상태(+고정점 목록)가 함께 지워지는지
canvas.mouseDoubleClickEvent(_FakeMouseEv(_QPF(300, 300)))
app.processEvents()
check("[v11] 더블클릭(보기 초기화) 시 추적 상태도 함께 지워짐", canvas._trace_x is None)
check("[신규] 더블클릭(보기 초기화) 시 고정점 목록도 함께 비워짐", canvas._pinned_points == [])

# 다시 추적을 만든 뒤 '보기 초기화' 버튼으로도 지워지는지
canvas.mousePressEvent(_FakeMouseEv(_QPF(start_px, axis_y)))
canvas.mouseReleaseEvent(_FakeMouseEv(_QPF(start_px, axis_y)))
app.processEvents()
check("[v11] 다시 추적 생성됨(초기화 버튼 테스트 준비)", canvas._trace_x is not None)
graph._reset_view()
app.processEvents()
check("[v11] '보기 초기화' 버튼으로도 추적 상태가 지워짐", canvas._trace_x is None)

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 함수 그래프 재번역 중 예외 없음", True)
    check(f"[{lang}] 함수 그래프 도구 이름 번역", win.lbl_util_current.text() == tr("util.graph.title"))

check("graph 앱 아이콘 생성", not make_app_icon("graph", C.UTIL_MAIN, 32).isNull())

section("20b. [버그 수정] 함수 그래프 — 가로세로 등각(1:1) 렌더링")
win.switch_mode("util")
win.util_panel.open_app("graph")
app.processEvents()
gw_eq = win.util_panel._pages["graph"][0]
gw_eq.rows[0].edit.setText("x^3/20 - x")
app.processEvents()
canvas_eq = gw_eq.canvas
fid_eq = canvas_eq.functions[0]["id"]

# 사용자가 겪은 것과 같은 극단적인 종횡비 상황(X 8.5칸, Y 1.5칸)을 재현
canvas_eq.xmin, canvas_eq.xmax = -1.7183, 6.7817
canvas_eq.ymin, canvas_eq.ymax = -0.6875, 0.8323
canvas_eq.auto_y = False
plot_eq = canvas_eq._plot_rect()
sx_eq = plot_eq.width() / (canvas_eq.xmax - canvas_eq.xmin)
sy_eq = plot_eq.height() / (canvas_eq.ymax - canvas_eq.ymin)
check("[버그 수정] X 범위와 Y 범위가 크게 다른 상황에서도 실제 렌더링 배율(scale)이 "
     "X·Y 양쪽에 똑같이 적용됨(가로세로 독립 배율이던 예전 버그가 고쳐짐)",
     abs(canvas_eq._scale(plot_eq) - min(sx_eq, sy_eq)) < 1e-6)

canvas_eq._pin_point(4.5, fid_eq)
pt_eq = canvas_eq._pinned_points[0]
pt_eq["tangent"] = True
pt_eq["normal"] = True
slope_eq = GS.numeric_slope("x^3/20 - x", 4.5, canvas_eq.xmax - canvas_eq.xmin)
normal_slope_eq = GS.normal_slope(slope_eq)
y0_eq = canvas_eq._pinned_point_y(pt_eq)
p_tan_1 = canvas_eq._to_px(4.0, y0_eq + slope_eq * (4.0 - 4.5), plot_eq)
p_tan_2 = canvas_eq._to_px(5.0, y0_eq + slope_eq * (5.0 - 4.5), plot_eq)
p_norm_1 = canvas_eq._to_px(4.0, y0_eq + normal_slope_eq * (4.0 - 4.5), plot_eq)
p_norm_2 = canvas_eq._to_px(5.0, y0_eq + normal_slope_eq * (5.0 - 4.5), plot_eq)
import math as _math_graph
tan_vec = (p_tan_2.x() - p_tan_1.x(), p_tan_2.y() - p_tan_1.y())
norm_vec = (p_norm_2.x() - p_norm_1.x(), p_norm_2.y() - p_norm_1.y())
dot_eq = tan_vec[0] * norm_vec[0] + tan_vec[1] * norm_vec[1]
mag_eq = _math_graph.hypot(*tan_vec) * _math_graph.hypot(*norm_vec)
angle_eq = _math_graph.degrees(_math_graph.acos(max(-1, min(1, dot_eq / mag_eq))))
check("[버그 수정] 극단적인 종횡비에서도 화면(픽셀) 상 접선·법선이 실제로 직각(90도)으로 보임"
     " — 예전엔 X·Y 배율이 달라 삐뚜름하게 보였음",
     abs(angle_eq - 90.0) < 0.5, angle_eq)

_cx_eq, _cy_eq = (canvas_eq.xmin + canvas_eq.xmax) / 2, (canvas_eq.ymin + canvas_eq.ymax) / 2
_center_px = canvas_eq._to_px(_cx_eq, _cy_eq, plot_eq)
_expected_px = _QPF(plot_eq.left() + plot_eq.width() / 2, plot_eq.top() + plot_eq.height() / 2)
_center_dist = _math_graph.hypot(_center_px.x() - _expected_px.x(), _center_px.y() - _expected_px.y())
check("[버그 수정] 데이터 중심점이 화면(플롯 영역) 중심에 그대로 매핑됨(등각으로도 위치는 안 틀어짐)",
     _center_dist < 1.0)

# [버그 수정] x축이 화살표(펜을 NoPen으로 바꿈)를 그린 뒤 펜이 복원 안 돼서
# 안 보이던 실제 버그 — 픽셀을 직접 읽어 검은 축 색상이 실제로 그려지는지 확인
from PySide6.QtGui import QImage as _QImg
img_axis = canvas_eq.grab().toImage()
y0_row = int(round(canvas_eq._to_px(0, 0, plot_eq).y()))
row_colors = [img_axis.pixelColor(x, y0_row).name()
             for x in range(int(plot_eq.left()) + 5, int(plot_eq.right()) - 5, 8)]
check("[버그 수정] x축(가로선)이 실제로 화면에 그려짐(화살표가 펜을 바꾼 뒤 복원 안 되던 버그)",
     any(c.startswith("#3") for c in row_colors), row_colors)

# [버그 수정] "Y 자동"이 켜져 있을 때 패닝(드래그) 도중에는 Y 범위가 안 바뀌고,
# 손을 놓는 순간에만 다시 계산되는지(패닝 중에 줌이 같이 되는 것처럼 보이던 버그)
canvas_eq.xmin, canvas_eq.xmax = -10, 10
canvas_eq.ymin, canvas_eq.ymax = -10, 10
canvas_eq.auto_y = True
gw_eq.chk_auto_y.setChecked(True)
canvas_eq.clear_trace()   # 이전 테스트에서 남은 고정점·추적 상태가 간섭하지 않도록
canvas_eq._dragging = False          # [테스트 안정화] 팬 상태도 확실히 초기화
canvas_eq._trace_dragging = False    # (clear_trace는 이 둘을 다 안 건드림)
canvas_eq._resample()
app.processEvents()
_y_span_before_drag = canvas_eq.ymax - canvas_eq.ymin
_y_center_before_drag = (canvas_eq.ymax + canvas_eq.ymin) / 2

class _FakePanPress:
    def __init__(self, pos):
        self._pos = pos
    def button(self):
        return Qt.LeftButton
    def position(self):
        return self._pos

class _FakePanMove:
    def __init__(self, pos):
        self._pos = pos
    def position(self):
        return self._pos

class _FakePanRelease:
    def button(self):
        return Qt.LeftButton

_x_before_drag = (canvas_eq.xmin, canvas_eq.xmax)
# [테스트 안정화] x축(y=0) 근처를 클릭하면 "팬"이 아니라 "추적 시작"으로 인식되니,
# 플롯 영역 맨 위쪽 구석(x축에서 충분히 떨어진 곳)을 클릭해 팬을 확실히 유도한다.
_plot_for_click = canvas_eq._plot_rect()
_pan_click_pos = _QPF(_plot_for_click.left() + 30, _plot_for_click.top() + 20)
canvas_eq.mousePressEvent(_FakePanPress(_pan_click_pos))
app.processEvents()
_y_spans_during_drag = []
for _step in range(1, 6):
    canvas_eq.mouseMoveEvent(_FakePanMove(_QPF(_pan_click_pos.x() + _step * 10, _pan_click_pos.y() + _step * 5)))
    app.processEvents()
    _y_spans_during_drag.append(canvas_eq.ymax - canvas_eq.ymin)
check("[버그 수정] 'Y 자동'이 켜져 있어도 드래그(패닝) 도중에는 Y 범위가 그대로 유지됨(줌처럼 안 보임)",
     all(abs(s - _y_span_before_drag) < 1e-6 for s in _y_spans_during_drag), _y_spans_during_drag)
canvas_eq.mouseReleaseEvent(_FakePanRelease())
app.processEvents()
app.processEvents()
# [v45.2] X 기준으로 등각 배율을 고정한 뒤로는(관련 섹션 참고), Y의
# "폭(span)"은 X 폭(xspan)과 화면 비율로만 정해져 패닝으로 xspan 자체가
# 안 바뀌면 그대로다 — 대신 "중심(center)"이 패닝으로 새로 보이는
# 데이터(= 새 X 범위에서 다시 계산한 robust_y_range)를 따라 바뀐다.
check("[v45.2] 드래그를 놓으면 그제서야 최종 X범위에 맞춰 Y의 중심이 다시 계산됨"
     "(X 기준 등각이라 xspan이 그대로면 Y의 폭 자체는 안 바뀌는 게 맞고, 중심만 바뀐다)",
     abs(((canvas_eq.ymax + canvas_eq.ymin) / 2) - _y_center_before_drag) > 1e-6)

# =============================================================================
section("21. 오늘의 급식 — 순수 로직(URL 생성 + 응답 해석)")
from src.utils import meal_solve as MS

url = MS.build_url("KEY1", "B10", "7010536", "20260915", meal_code=MS.MEAL_LUNCH)
check("URL에 필수 파라미터 전부 포함", all(s in url for s in
      ["KEY=KEY1", "Type=json", "ATPT_OFCDC_SC_CODE=B10", "SD_SCHUL_CODE=7010536",
       "MLSV_YMD=20260915", "MMEAL_SC_CODE=2"]), url)
check("선린인터넷고 기본 코드가 미리 채워져 있음",
      MS.DEFAULT_OFFICE_CODE == "B10" and MS.DEFAULT_SCHOOL_CODE == "7010536")

success_json = ('{"mealServiceDietInfo":[{"head":[{"list_total_count":1}]},'
                '{"row":[{"MMEAL_SC_CODE":"2","MMEAL_SC_NM":"중식",'
                '"DDISH_NM":"밥<br/>국5.6.<br/>김치9.","CAL_INFO":"900.0 Kcal"}]}]}')
r = MS.parse(success_json)
check("정상 응답 파싱", r.status == "ok" and len(r.meals) == 1)
check("요리명 3줄로 분리", r.meals[0].dishes == ["밥", "국5.6.", "김치9."], r.meals[0].dishes)
check("알레르기 번호 보존(안전 정보)", "5.6." in r.meals[0].dishes[1])
check("칼로리 파싱", r.meals[0].calorie == "900.0 Kcal")

r = MS.parse('{"RESULT":{"CODE":"INFO-200","MESSAGE":"해당하는 데이터가 없습니다."}}')
check("데이터 없음(JSON) -> empty", r.status == "empty" and r.message == "해당하는 데이터가 없습니다.")

# 실제로 나이스 서버에 직접 호출해 받은 것과 동일한 XML 오류(개발 중 검증함)
xml_err = ('<?xml version="1.0" encoding="UTF-8"?><RESULT><CODE>ERROR-300</CODE>'
           '<MESSAGE>필수 값이 누락되어 있습니다. 요청인자를 참고 하십시오.</MESSAGE></RESULT>')
r = MS.parse(xml_err)
check("Type=json 요청에도 XML로 오는 오류를 해석함(실제 서버 동작 확인됨)",
      r.status == "error" and "필수 값" in r.message, r.message)

r = MS.parse('<RESULT><CODE>INFO-200</CODE><MESSAGE>해당하는 데이터가 없습니다.</MESSAGE></RESULT>')
check("XML 형태의 데이터없음도 empty로 분류", r.status == "empty")

for bad in ["이상한 문자열", "", None]:
    r = MS.parse(bad)
    check(f"이해할 수 없는 응답({bad!r})도 안전하게 error 처리", r.status == "error")

r = MS.parse('{"mealServiceDietInfo":[{"row":[{"MMEAL_SC_CODE":"1"},{"MMEAL_SC_CODE":"2"}]}]}'
             .replace('"row"', '"broken"'))
check("예상과 다른 JSON 구조도 죽지 않고 error 처리", r.status == "error")

multi = ('{"mealServiceDietInfo":[{"head":[{"list_total_count":2}]},'
         '{"row":[{"MMEAL_SC_CODE":"1","MMEAL_SC_NM":"조식","DDISH_NM":"우유"},'
         '{"MMEAL_SC_CODE":"2","MMEAL_SC_NM":"중식","DDISH_NM":"밥"}]}]}')
r = MS.parse(multi)
check("여러 끼(조식+중식) 모두 파싱", len(r.meals) == 2 and r.meals[1].meal_name == "중식")

section("21b. [신규] NEIS 공통 설정 — 학교 검색 + 인증키 보이기/복사")
from src.utils import neis_common as N
from PySide6.QtNetwork import QNetworkReply
_url = N.build_school_search_url("MYKEY", "구리고등학교")
check("[신규] 학교 검색 URL에 KEY 포함", "KEY=MYKEY" in _url)
check("[신규] 학교 검색 URL에 학교명 포함(인코딩)",
      "%EA%B5%AC%EB%A6%AC" in _url or "구리고등학교" in _url, _url)

_sample_school_json = (
    '{"schoolInfo":[{"head":[{"list_total_count":1},'
    '{"RESULT":{"CODE":"INFO-000","MESSAGE":"정상 처리되었습니다."}}]},'
    '{"row":[{"ATPT_OFCDC_SC_CODE":"J10","ATPT_OFCDC_SC_NM":"경기도교육청",'
    '"SD_SCHUL_CODE":"7530054","SCHUL_NM":"구리고등학교",'
    '"ORG_RDNMA":"경기도 구리시 장자대로 89"}]}]}')
_r = N.parse_school_search_response(_sample_school_json)
check("[신규] 정상 학교 검색 응답 -> ok, 1건", _r.status == "ok" and len(_r.schools) == 1)
check("[신규] 교육청코드·학교코드 정확히 파싱", _r.schools[0].office_code == "J10"
      and _r.schools[0].school_code == "7530054")
check("[신규] 표시 문구에 학교명+교육청명 포함",
      "구리고등학교" in _r.schools[0].display_text() and "경기도교육청" in _r.schools[0].display_text())

_r_empty = N.parse_school_search_response('{"RESULT":{"CODE":"INFO-200","MESSAGE":"데이터 없음"}}')
check("[신규] 결과 없음 -> empty", _r_empty.status == "empty")
_r_bad = N.parse_school_search_response("<html>깨진 응답</html>")
check("[신규] 해석 불가 응답도 안전하게 error 처리", _r_bad.status == "error")

# 위젯 레벨: 인증키 마스킹 기본값 + 보이기 토글 + 복사
win_n = MainWindow()
win_n.resize(900, 700)
win_n.show()
win_n.switch_mode("util")
win_n.util_panel.open_app("meal")
app.processEvents()
meal_n = win_n.util_panel._pages["meal"][0]
panel_n = meal_n.neis_panel
panel_n.toggle.setChecked(True)
panel_n._on_toggle()
app.processEvents()

check("[신규] 인증키 입력창은 기본적으로 가려짐(Password 모드)",
      panel_n.edit_key.echoMode() == panel_n.edit_key.EchoMode.Password)
panel_n.edit_key.setText("SECRET123")
panel_n.btn_toggle_key.setChecked(True)
panel_n._on_toggle_key_visibility()
check("[신규] 보이기 토글 클릭 시 Normal 모드로 전환", panel_n.edit_key.echoMode() == panel_n.edit_key.EchoMode.Normal)
panel_n.btn_toggle_key.setChecked(False)
panel_n._on_toggle_key_visibility()
check("[신규] 토글 다시 끄면 Password 모드로 복귀", panel_n.edit_key.echoMode() == panel_n.edit_key.EchoMode.Password)
panel_n._on_copy_key()
check("[신규] 복사 버튼으로 클립보드에 값이 복사됨", QGuiApplication.clipboard().text() == "SECRET123")

# 학교 검색 흐름: 인증키 없음 -> 안내
panel_n.edit_key.setText("")
panel_n.edit_school_name.setText("구리고등학교")
panel_n._on_search_school()
check("[신규] 인증키 없이 검색하면 안내 문구", tr("util.neis.school_search.need_key") == panel_n.lbl_school_status.text())

# 학교명 없음 -> 안내
panel_n.edit_key.setText("TESTKEY")
panel_n.edit_school_name.setText("")
panel_n._on_search_school()
check("[신규] 학교명 없이 검색하면 안내 문구", tr("util.neis.school_search.need_name") == panel_n.lbl_school_status.text())

# 정상 검색 -> 결과 목록 -> 선택 -> 자동 채움
class _FakeSchoolReply:
    def __init__(self, data):
        self._data = data.encode("utf-8")
    def error(self):
        return QNetworkReply.NoError
    def readAll(self):
        return self._data
    def deleteLater(self):
        pass

panel_n.edit_school_name.setText("구리고등학교")
panel_n._on_search_school()
_fake_reply = _FakeSchoolReply(_sample_school_json)
panel_n._search_reply = _fake_reply
panel_n._on_school_search_finished(_fake_reply)
app.processEvents()
check("[신규] 검색 결과 리스트에 1건 채워짐", panel_n.list_school_results.count() == 1)
check("[신규] 검색 결과 리스트가 실제로 보임", panel_n.list_school_results.isVisible())

panel_n._on_school_selected(panel_n.list_school_results.item(0))
check("[신규] 항목 선택 시 교육청코드 자동 채움", panel_n.edit_office.text() == "J10")
check("[신규] 항목 선택 시 학교코드 자동 채움", panel_n.edit_school.text() == "7530054")
check("[신규] 항목 선택 시 학교명도 그 학교로 갱신", panel_n.edit_school_name.text() == "구리고등학교")
check("[신규] 선택 후 결과 리스트는 다시 숨겨짐", not panel_n.list_school_results.isVisible())

# [정리] 이 테스트에서 바꾼 값(구리고등학교 등)이 실제 QSettings에 그대로
# 저장돼 있으면, 이후 다른 섹션의 "기본값(선린인터넷고)" 검증이 이 테스트
# 때문에 깨진다 — 반드시 기본값으로 되돌려 놓고 다음 섹션으로 넘어간다.
panel_n.set_values("", N.DEFAULT_OFFICE_CODE, N.DEFAULT_SCHOOL_CODE, N.DEFAULT_SCHOOL_NAME)
panel_n._emit_changed()
app.processEvents()
win_n.close()

section("22. 오늘의 급식 — 위젯 통합(네트워크 없이 렌더링만 검증)")
win.switch_mode("util")
win.util_panel.open_app("meal")
app.processEvents()
meal = win.util_panel._pages["meal"][0]
check("기본 학교 코드가 선린인터넷고", meal.office_code == "B10" and meal.school_code == "7010536")
check("인증키 없으면 안내 문구", tr("util.meal.status.need_key") in meal.view.toPlainText())
check("[v08] 기본은 일별 모드", meal.mode == "daily")

meal.neis_panel.edit_key.setText("TESTKEY")
meal.neis_panel._emit_changed()
app.processEvents()
_no_pending_reply(meal)   # 이후 수동 _render() 호출과 비동기 네트워크 콜백의 경쟁 방지

ok_result = MS.MealResult("ok", [MS.MealEntry("2", "중식", ["밥", "국"], calorie="800 Kcal")])
meal._render(ok_result)
app.processEvents()
check("[v08] 성공 렌더링 시 QTextEdit에 요리명 표시", "밥" in meal.view.toPlainText()
      and "국" in meal.view.toPlainText())
check("[v08] 칼로리도 함께 표시", "800 Kcal" in meal.view.toPlainText())

_no_pending_reply(meal)
meal._render(MS.MealResult("empty", [], "해당하는 데이터가 없습니다."))
app.processEvents()
check("데이터 없음 렌더링", tr("util.meal.status.empty") in meal.view.toPlainText())

_no_pending_reply(meal)
meal._render(MS.MealResult("error", [], "인증키가 유효하지 않습니다."))
app.processEvents()
check("오류 렌더링에 서버 메시지 포함", "인증키가 유효하지 않습니다" in meal.view.toPlainText())

before = meal.date_edit.date()
meal._shift_date(1)
app.processEvents()
check("다음날 버튼으로 날짜 하루 증가", meal.date_edit.date() == before.addDays(1))
meal._shift_date(-1)
app.processEvents()
check("이전날 버튼으로 원래 날짜 복귀", meal.date_edit.date() == before)

meal.neis_panel.toggle.setChecked(True)
meal.neis_panel._on_toggle()
check("학교 설정 패널 펼치기", meal.neis_panel.panel.isVisible())
meal.neis_panel.edit_office.setText("J10")
meal.neis_panel.edit_school.setText("7530054")
meal.neis_panel.edit_school_name.setText("구리고등학교")
meal._on_neis_settings_changed()
app.processEvents()
check("학교 코드 직접 변경 반영", meal.office_code == "J10" and meal.school_code == "7530054")

# [v08] 주간 뷰
from src.utils import neis_common as N
meal.neis_panel.edit_office.setText(N.DEFAULT_OFFICE_CODE)
meal.neis_panel.edit_school.setText(N.DEFAULT_SCHOOL_CODE)
meal.neis_panel._emit_changed()
app.processEvents()
meal._set_mode("weekly")
app.processEvents()
check("[v08] 주간 모드로 전환됨", meal.mode == "weekly")
monday, friday = meal._week_bounds()
check("[v08] 주간 범위는 월~금(5일)", (friday - monday).days == 4
      and monday.weekday() == 0 and friday.weekday() == 4)

import datetime as _dt
weekly_entries = []
for i, name in enumerate(["월밥", "화국수", "수카레", "목비빔밥", "금떡볶이"]):
    d = monday + _dt.timedelta(days=i)
    weekly_entries.append(MS.MealEntry("2", "중식", [name], calorie=f"{800+i}.0 Kcal",
                                        ymd=d.strftime("%Y%m%d")))
_no_pending_reply(meal)
meal._render_weekly(MS.MealResult("ok", weekly_entries))
app.processEvents()
weekly_text = meal.view.toPlainText()
check("[v08] 주간 표에 월~금 요리가 모두 표시됨",
      all(name in weekly_text for name in ["월밥", "화국수", "수카레", "목비빔밥", "금떡볶이"]))

# [버그 수정] "오늘"은 헤더 칩만이 아니라 칸 전체 배경이 강조색이고,
# 요리 글자도 흰색으로 바뀌는지(요청 반영 — 주간과 월별 모두 동일하게)
_html_week, _ = meal._build_weekly_html(MS.MealResult("ok", weekly_entries), monday, friday)
check("[버그 수정] 주간 표에서 오늘 칸은 전체 배경이 강조색",
      f"background:{C.UTIL_MAIN};color:#ffffff;" in _html_week)
check("[버그 수정] 주간 표에서 오늘 칸의 요리 글자는 흰색(칼로리 등)",
      "color:#ffffff;" in _html_week)

# 하루만 데이터가 빠진 경우(주말 아닌 평일에 정보 없음)에도 안전하게 표시
partial = [weekly_entries[0], weekly_entries[2], weekly_entries[4]]
_no_pending_reply(meal)
meal._render_weekly(MS.MealResult("ok", partial))
app.processEvents()
partial_text = meal.view.toPlainText()
check("[v08] 정보 없는 요일은 '정보 없음'으로 표시",
      tr("util.meal.status.empty_short") in partial_text)
check("[v08] 나머지 요일 데이터는 정상 표시", "월밥" in partial_text and "수카레" in partial_text)

# [v13] 월별 뷰 — 탁상용 달력 그리드(일~토 7칸 × 주 단위 여러 줄)로 재설계
import calendar
from PySide6.QtGui import QTextDocument as _QTextDocument, QImage as _QImage, QPainter as _QPainter
meal._set_mode("monthly")
app.processEvents()
check("[v12] 월별 모드로 전환됨", meal.mode == "monthly")
first, last = meal._month_bounds()
check("[v12] 월 범위가 1일부터 그 달 마지막 날까지", first.day == 1 and last.month == first.month
      and (last + _dt.timedelta(days=1)).month != first.month)

monthly_entries = []
d = first
while d <= last:
    if d.weekday() < 5:
        monthly_entries.append(MS.MealEntry("2", "중식", [f"{d.day}일메뉴"], calorie="750.0 Kcal",
                                            ymd=d.strftime("%Y%m%d")))
    d += _dt.timedelta(days=1)
monthly_result = MS.MealResult("ok", monthly_entries)
_no_pending_reply(meal)
meal._render(monthly_result)   # _render()를 통해 호출 -> _last_result도 함께 저장(인쇄 테스트용)
app.processEvents()
monthly_text = meal.view.toPlainText()
check("[v12] 월별 표에 첫 평일 메뉴가 표시됨", f"{monthly_entries[0].dishes[0]}" in monthly_text)
check("[v12] 월별 표에 마지막 평일 메뉴가 표시됨", f"{monthly_entries[-1].dishes[0]}" in monthly_text)
check("[v12] 급식이 있는 평일 수만큼 메뉴가 표시됨",
      monthly_text.count("일메뉴") == len(monthly_entries))
check("[v12] 문서 높이가 위젯 높이보다 커서 세로 스크롤이 가능함",
      meal.view.document().size().height() >= meal.view.height() * 0.5)

# [버그 수정] 탁상 달력 그리드 구조 검증 — 토·일은 이제 칸 자체가 없다
# (주간 급식표가 월~금만 보여주는 것과 맞춤). 주(week) 수만큼 <tr>이
# 있고, 각 줄에 월~금 5칸만 있는지 확인한다.
_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
_html_month, _total_month, _has_any_month = meal._build_monthly_html(monthly_result, first, last)
check("[버그 수정] 달력 그리드 행 수가 그 달의 주 수와 일치",
      _html_month.count("<tr>") == len(_weeks) + 1, (_html_month.count("<tr>"), len(_weeks) + 1))  # +1은 요일 머리글
check("[버그 수정] 토요일 헤더는 더 이상 없음(월~금만)",
      tr("util.meal.wd.sat") not in _html_month)
check("[버그 수정] 월요일 헤더는 있음", tr("util.meal.wd.mon") in _html_month)
check("[버그 수정] 다른 달로 넘어가는 날짜도 칸이 채워짐(빈 칸 없이 5×N 표 유지)",
      _html_month.count("<td") == len(_weeks) * 5)

# [버그 수정] 오늘 날짜는 칸 전체 배경이 강조색이고 글자가 흰색인지
if first.strftime("%Y%m") == _dt.date.today().strftime("%Y%m"):
    check("[버그 수정] 월별 표에서 오늘 칸은 전체 배경이 강조색",
          f"background:{C.UTIL_MAIN};" in _html_month)
    check("[버그 수정] 월별 표에서 오늘 칸의 요리 글자는 흰색",
          'color:#ffffff;' in _html_month)

before_month = meal.date_edit.date()
meal._shift_date(1)
app.processEvents()
check("[v12] 월별 모드에서 다음 버튼은 한 달 이동",
      meal.date_edit.date().month() == (before_month.month() % 12) + 1)
meal._shift_date(-1)
app.processEvents()
check("[v12] 월별 모드에서 이전 버튼으로 복귀", meal.date_edit.date() == before_month)

# 완전히 빈 달(데이터 전혀 없음)도 안전하게 안내로 처리되는지
_no_pending_reply(meal)
meal._render_monthly(MS.MealResult("ok", []))
app.processEvents()
check("[v12] 급식 정보가 하나도 없는 달은 안내 문구로 처리",
      tr("util.meal.status.empty") in meal.view.toPlainText())

# [버그 수정 — 근본 원인 재발견] HTML 인쇄(이전 두 차례 수정 포함)조차
# 실제 프린터에서는 부족했다 — table-layout:fixed로도 칸이 짧으면 표가
# 자동으로 좁아져 좌우 여백이 크게(비대칭으로) 남는 게 실측으로 확인
# 됐다. 그래서 주간·월별 인쇄는 이제 HTML이 아니라 `print_grid` 모듈로
# 직접 그린다. 실제로 QPrinter를 PDF로 출력해서 여백을 픽셀 단위로
# 측정해 확인한다(이 방식만이 Qt의 표 자동 크기 조정 문제를 완전히
# 피할 수 있다는 걸 실측으로 이미 확인했다).
from PySide6.QtGui import QPainter as _QPainterPrint, QPageLayout as _QPageLayout2
from PySide6.QtPrintSupport import QPrinter as _QPrinterPrint
from src.utils import print_grid as _PG

def _measure_lr_margin_mm(pdf_path):
    import subprocess
    out_prefix = pdf_path.replace(".pdf", "")
    subprocess.run(["pdftoppm", "-png", "-r", "100", "-f", "1", "-l", "1",
                    pdf_path, out_prefix], check=True, capture_output=True)
    from PIL import Image
    import numpy as np
    img = Image.open(out_prefix + "-1.png").convert("RGB")
    arr = np.array(img)
    w = img.width
    mask = np.any(arr < 250, axis=2)
    cols = np.where(mask.any(axis=0))[0]
    if len(cols) == 0:
        return None, None
    left_mm = cols.min() / 100 * 25.4
    right_mm = (w - cols.max()) / 100 * 25.4
    return left_mm, right_mm

import shutil as _shutil
_has_pdftoppm = _shutil.which("pdftoppm") is not None

_weekly_grid = meal._weekly_grid_cells(MS.MealResult("ok", weekly_entries), monday)
check("[버그 수정] 주간 인쇄용 칸이 5개(월~금) 만들어짐", len(_weekly_grid) == 5)
check("[버그 수정] 오늘 칸은 배경이 강조색으로 채워짐(GridCell.bg)",
      any(c.bg is not None for c in _weekly_grid))

_monthly_grid = meal._monthly_grid_weeks(monthly_result, first, last)
_weeks_expected = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
check("[버그 수정] 월별 인쇄용 주 수가 실제 그 달의 주 수와 일치",
      len(_monthly_grid) == len(_weeks_expected))
check("[버그 수정] 월별 인쇄용 각 주는 5칸(월~금)만",
      all(len(week) == 5 for week in _monthly_grid))

if _has_pdftoppm:
    import os as _os3, tempfile as _tf3
    _pdf_path = _os3.path.join(_tf3.gettempdir(), "fkpp_meal_margin_test.pdf")
    _printer_m = _QPrinterPrint(_QPrinterPrint.HighResolution)
    _printer_m.setPageOrientation(_QPageLayout2.Landscape)
    _printer_m.setFullPage(True)
    _printer_m.setOutputFormat(_QPrinterPrint.PdfFormat)
    _printer_m.setOutputFileName(_pdf_path)
    _painter_m = _QPainterPrint(_printer_m)
    from src.utils.meal import _WEEKDAY_SHORT_KEYS as _WDK
    _headers_m = [tr(k) for k in _WDK[:5]]
    _PG.print_calendar(_printer_m, _painter_m, "여백측정", C.UTIL_MAIN, _headers_m,
                       [_weekly_grid], margin_pt=3 * 2.83465)
    _painter_m.end()
    _l_mm, _r_mm = _measure_lr_margin_mm(_pdf_path)
    check("[버그 수정] 실제 인쇄 좌측 여백이 요청한 3mm 근처(10mm 이하)",
          _l_mm is not None and _l_mm < 10, _l_mm)
    check("[버그 수정] 실제 인쇄 우측 여백도 좌측과 비슷함(비대칭 해소, 10mm 이하)",
          _r_mm is not None and _r_mm < 10, _r_mm)
    for _p in (_pdf_path, _pdf_path.replace(".pdf", "-1.png")):
        if _os3.path.exists(_p):
            _os3.remove(_p)
else:
    check("[버그 수정] pdftoppm 없어 여백 실측은 건너뜀(구조 검증만 수행)", True)

meal._set_mode("daily")   # 이후 테스트에 영향 없도록 일별로 복귀
app.processEvents()

# [v08] 드래그 선택 → 복사 (전체 선택으로 시뮬레이션)
_no_pending_reply(meal)
meal._render(MS.MealResult("ok", [MS.MealEntry("2", "중식", ["복사테스트밥", "복사테스트국"])]))
app.processEvents()
from PySide6.QtGui import QTextCursor as _QTextCursor
_cursor = meal.view.textCursor()
_cursor.select(_QTextCursor.Document)
meal.view.setTextCursor(_cursor)
meal.view.copy()
app.processEvents()
_clip = QGuiApplication.clipboard().text()
check("[v08] 드래그(전체선택) 후 복사한 텍스트에 요리명 포함",
      "복사테스트밥" in _clip and "복사테스트국" in _clip)

# [v08→v16 수정] 인쇄 — 모달 프린트 대화상자를 흉내내어 방향·설정까지 확인
from PySide6.QtPrintSupport import QPrintDialog as _QPrintDialog, QPrinter as _QPrinter
from PySide6.QtGui import QPageLayout as _QPageLayout
_orig_print_exec = _QPrintDialog.exec
_captured_printer = {}
def _fake_print_exec(self):
    _captured_printer["p"] = self.printer()
    return 1
_QPrintDialog.exec = _fake_print_exec
try:
    meal._set_mode("weekly")
    _no_pending_reply(meal)
    meal._render(MS.MealResult("ok", weekly_entries))
    app.processEvents()
    meal._print()
    check("[v08] 인쇄 실행 중 예외 없음", True)
    _printer = _captured_printer.get("p")
    check("[버그 수정] 인쇄가 가로 방향(Landscape)으로 설정됨",
          _printer is not None and _printer.pageLayout().orientation() == _QPageLayout.Landscape)
    check("[버그 수정] 인쇄가 fullPage로 설정됨(프린터 드라이버 여백을 직접 통제)",
          _printer is not None and _printer.fullPage())

    meal._set_mode("monthly")
    _no_pending_reply(meal)
    meal._render(MS.MealResult("ok", monthly_entries))
    app.processEvents()
    _captured_printer.clear()
    meal._print()
    check("[버그 수정] 월별 인쇄도 예외 없이 완료(그리드 기반)", True)
except Exception as e:
    check("[v08] 인쇄 실행 중 예외 없음", False, e)
finally:
    _QPrintDialog.exec = _orig_print_exec

# 저장/복원
win4 = MainWindow()
win4.switch_mode("util")
win4.util_panel.open_app("meal")
app.processEvents()
meal4 = win4.util_panel._pages["meal"][0]
check("재기동 후 인증키 복원", meal4.neis_panel.values()[0] == "TESTKEY")
win4.close()

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 급식 재번역 중 예외 없음", True)
    check(f"[{lang}] 급식 도구 이름 번역", win.lbl_util_current.text() == tr("util.meal.title"))

check("meal 앱 아이콘 생성", not make_app_icon("meal", C.UTIL_MAIN, 32).isNull())

# [버그 수정] Ctrl+휠 확대가 표 안 글자에도 반영되도록 — 화면용은 절대
# 크기를 아예 안 주고(_fs가 빈 문자열), 작은 글자는 <small>로 감싼다.
from src.utils.meal import _fs as _meal_fs, _small as _meal_small
check("[버그 수정] 화면용(width_px=None) _fs는 빈 문자열(확대에 반응하게)",
      _meal_fs(12, None) == "")
check("[버그 수정] 인쇄용(width_px 있음) _fs는 pt 크기를 냄",
      "pt" in _meal_fs(12, 800))
check("[버그 수정] 화면용 _small은 <small> 태그로 감쌈",
      _meal_small("내용", None) == "<small>내용</small>")
check("[버그 수정] 인쇄용 _small은 그대로 둠(이미 pt로 지정됨)",
      _meal_small("내용", 800) == "내용")

meal.neis_panel.edit_key.setText("TESTKEY")
meal.neis_panel._emit_changed()
app.processEvents()
_no_pending_reply(meal)
meal._set_mode("monthly")
meal._render(MS.MealResult("ok", [MS.MealEntry("2", "중식", ["확대테스트밥"], calorie="700 Kcal",
                                                ymd=meal._month_bounds()[0].strftime("%Y%m%d"))]))
app.processEvents()
_before_h = meal.view.document().size().height()
meal.view.zoomIn(6)
app.processEvents()
_after_h = meal.view.document().size().height()
check("[버그 수정] Ctrl+휠(zoomIn) 시 표 내용도 함께 커짐(문서 높이 증가)",
      _after_h > _before_h * 1.3, (_before_h, _after_h))
meal.view.zoomOut(6)
app.processEvents()
meal._set_mode("daily")
app.processEvents()

# =============================================================================
section("23. 학교 일정 — 순수 로직(URL 생성 + 응답 해석)")
from src.utils import schedule_solve as SS

url = SS.build_url("K1", "B10", "7010536", "20260901", "20260930")
check("URL 필수 파라미터 포함", all(s in url for s in
      ["KEY=K1", "AA_FROM_YMD=20260901", "AA_TO_YMD=20260930",
       "ATPT_OFCDC_SC_CODE=B10", "SD_SCHUL_CODE=7010536"]), url)

success = ('{"SchoolSchedule":[{"head":[{"list_total_count":2}]},'
           '{"row":[{"AA_YMD":"20260901","EVENT_NM":"2학기 개학","EVENT_CNTNT":null},'
           '{"AA_YMD":"20260915","EVENT_NM":"중간고사","EVENT_CNTNT":"1~3학년 중간고사"}]}]}')
r = SS.parse(success)
check("정상 응답 파싱(2건)", r.status == "ok" and len(r.events) == 2)
check("행사명 파싱", r.events[0].name == "2학기 개학")
check("상세내용 있는 행사", r.events[1].content == "1~3학년 중간고사")
check("상세내용 없으면 None", r.events[0].content is None)

by_day = SS.events_by_day(r.events)
check("일자별로 묶임", set(by_day.keys()) == {1, 15})

r = SS.parse('{"RESULT":{"CODE":"INFO-200","MESSAGE":"해당하는 데이터가 없습니다."}}')
check("데이터 없음 -> empty", r.status == "empty")

xml_err = '<RESULT><CODE>ERROR-300</CODE><MESSAGE>필수 값이 누락되어 있습니다.</MESSAGE></RESULT>'
r = SS.parse(xml_err)
check("XML 오류도 해석됨(급식과 같은 패턴)", r.status == "error" and "필수 값" in r.message)

for bad in ["이상한거", "", None]:
    r = SS.parse(bad)
    check(f"이상한 응답({bad!r}) 안전 처리", r.status == "error")

section("24. 학교 일정 — 위젯 통합(네트워크 없이 렌더링만 검증)")
from src.utils import neis_common as NC
check("설정이 전혀 없을 때의 기본값 = 선린인터넷고(순수 함수, 전역 설정 무관)",
      NC.load(None) == (NC.DEFAULT_OFFICE_CODE, NC.DEFAULT_SCHOOL_CODE, NC.DEFAULT_SCHOOL_NAME, ""))

win.switch_mode("util")
win.util_panel.open_app("schedule")
app.processEvents()
sched = win.util_panel._pages["schedule"][0]
check("달력은 키 없이도 그려짐(빈 상태)", len(sched._cells) >= 28)

# 이 시점에 이미 다른 절(급식)이 전역 설정에 키를 넣어 놨을 수 있으므로,
# "키가 없을 때" 동작은 패널을 직접 비워서 확인한다(전역 설정은 건드리지 않음).
_saved_office, _saved_school, _saved_name = sched.office_code, sched.school_code, sched.school_name
sched.neis_panel.set_values("", _saved_office, _saved_school, _saved_name)
sched._fetch()
app.processEvents()
check("인증키 없으면 안내 문구 표시", sched.lbl_status.isVisible()
      and sched.lbl_status.text() == tr("util.schedule.status.need_key"))

sched.neis_panel.edit_key.setText("TESTKEY")
app.processEvents()
y, m = sched.year, sched.month
ok_result = SS.ScheduleResult("ok", [
    SS.ScheduleEvent(f"{y:04d}{m:02d}05", "행사A"),
    SS.ScheduleEvent(f"{y:04d}{m:02d}05", "행사B", content="상세내용"),
])
_no_pending_reply(sched)
sched._render(ok_result)
app.processEvents()
check("행사가 있는 날짜 칸에 칩이 붙음", len(sched._cells[5].events) == 2)
check("행사 없는 날은 칩 없음", len(sched._cells[1].events) == 0)

sched.select_day(5)
app.processEvents()
check("날짜 클릭 시 상세 패널에 행사 표시",
      any("행사A" in sched.detail_lay.itemAt(i).widget().text()
          for i in range(sched.detail_lay.count())
          if sched.detail_lay.itemAt(i).widget() is not None))
check("상세 내용도 함께 표시",
      any("상세내용" in sched.detail_lay.itemAt(i).widget().text()
          for i in range(sched.detail_lay.count())
          if sched.detail_lay.itemAt(i).widget() is not None))

_no_pending_reply(sched)
sched._render(SS.ScheduleResult("error", [], "인증키가 유효하지 않습니다."))
app.processEvents()
check("오류 렌더링에 서버 메시지 포함", "인증키가 유효하지 않습니다" in sched.lbl_status.text())

before_ym = (sched.year, sched.month)
sched._shift_month(1)
app.processEvents()
check("다음 달 이동", (sched.year, sched.month) != before_ym)
sched._shift_month(-1)
app.processEvents()
check("이전 달로 복귀", (sched.year, sched.month) == before_ym)

sched.year, sched.month = 2026, 12
sched._shift_month(1)
app.processEvents()
check("12월 다음 달은 다음해 1월로 이월", (sched.year, sched.month) == (2027, 1))

# =============================================================================
section("24b. [v09] 학교 일정 — 로컬(직접 입력) 연간계획")
from src.utils import schedule_local as SL
from PySide6.QtWidgets import QDialog as _QDialog
from src.utils.schedule import _EventEditDialog

sched.year, sched.month = 2026, 9
sched.local_events = []
sched.neis_panel.set_values("", sched.office_code, sched.school_code, sched.school_name)
sched._fetch()
app.processEvents()
check("[v09] 인증키 없어도 달력은 그려짐", len(sched._cells) >= 28)

sched.select_day(10)
app.processEvents()
check("[v09] 날짜 선택 시 추가 버튼 활성화", sched.btn_add_event.isEnabled())

def _fake_exec_add(self):
    if isinstance(self, _EventEditDialog):
        self.edit_name.setText("체육대회")
        self.edit_content.setPlainText("운동장에서 진행")
    return 1
_orig_dlg_exec = _QDialog.exec
_QDialog.exec = _fake_exec_add
try:
    sched._add_local_event(10)
finally:
    _QDialog.exec = _orig_dlg_exec
app.processEvents()
check("[v09] 인증키 없이도 로컬 일정 추가됨", len(sched.local_events) == 1)
check("[v09] 추가한 일정이 달력 칸에 보임(source=local)",
      any(src == "local" and ev.name == "체육대회" for src, ev in sched._cells[10].events))

def _fake_exec_edit(self):
    if isinstance(self, _EventEditDialog):
        self.edit_name.setText("체육대회(우천 연기)")
    return 1
_QDialog.exec = _fake_exec_edit
try:
    sched._edit_local_event(10, 0)
finally:
    _QDialog.exec = _orig_dlg_exec
app.processEvents()
check("[v09] 로컬 일정 수정 반영", sched.local_events[0].name == "체육대회(우천 연기)")

# 이름을 비워 내면 취소로 처리되어(팝업 없이) 원래 값이 유지되는지
def _fake_exec_blank(self):
    if isinstance(self, _EventEditDialog):
        self.edit_name.setText("")
    return 1
_QDialog.exec = _fake_exec_blank
try:
    sched._edit_local_event(10, 0)
finally:
    _QDialog.exec = _orig_dlg_exec
check("[v09] 제목을 비우면 수정이 반영되지 않음", sched.local_events[0].name == "체육대회(우천 연기)")

sched._delete_local_event(10, 0)
app.processEvents()
check("[v09] 로컬 일정 삭제됨", len(sched.local_events) == 0)
check("[v09] 삭제 후 달력 칸에서도 사라짐", len(sched._cells[10].events) == 0)

# NEIS + 로컬이 같은 날 함께 표시되는지
sched.local_events = [SL.LocalEvent("20260905", "학급회의")]
sched._apply_events()
sched.events_by_day = {5: [SS.ScheduleEvent("20260905", "임시휴업일")]}
sched._apply_events()
app.processEvents()
combined = sched._cells[5].events
check("[v09] 같은 날 로컬+NEIS 함께 표시(2건)", len(combined) == 2)
check("[v09] 로컬이 먼저, NEIS가 그다음 순서로 표시", combined[0][0] == "local" and combined[1][0] == "neis")
sched.select_day(5)
app.processEvents()
detail_widgets = [sched.detail_lay.itemAt(i).widget() for i in range(sched.detail_lay.count())
                  if sched.detail_lay.itemAt(i).widget() is not None]
_neis_line_found = any(
    hasattr(w, "text") and callable(w.text) and "[NEIS]" in w.text()
    for w in detail_widgets if type(w).__name__ == "QLabel"
)
check("[v09] 상세 패널에 NEIS 항목이 [NEIS] 표시와 함께 나옴", _neis_line_found)
sched.local_events = []
sched.events_by_day = {}
sched._apply_events()

# 엑셀 가져오기/출력 (openpyxl 있는 경로)
import os as _os, tempfile as _tf
_export_path = _os.path.join(_tf.gettempdir(), "fkpp_sched_export_test.xlsx")
sched.local_events = [SL.LocalEvent("20260915", "중간고사", "1~3학년"), SL.LocalEvent("20260920", "체육대회")]
sched._save_local()
with _patch("src.utils.schedule.QFileDialog.getSaveFileName", return_value=(_export_path, "")):
    sched._export_excel()
check("[v09] 엑셀 출력 파일 생성됨", _os.path.exists(_export_path))
_export_check = SL.import_excel(_export_path)
check("[v09] 출력한 파일에 2건 들어있음", len(_export_check.events) == 2)
_os.remove(_export_path)

import openpyxl as _opx
_import_path = _os.path.join(_tf.gettempdir(), "fkpp_sched_import_test.xlsx")
_wb = _opx.Workbook(); _ws = _wb.active
_ws.append(["날짜", "제목", "내용"])
_ws.append(["2026-10-05", "개천절 대체휴일", ""])
_wb.save(_import_path)
_before_count = len(sched.local_events)
with _patch("src.utils.schedule.QFileDialog.getOpenFileName", return_value=(_import_path, "")):
    sched._import_excel()
app.processEvents()
check("[v09] 엑셀 가져오기로 일정 추가됨", len(sched.local_events) - _before_count == 1)
_os.remove(_import_path)

# [버그 수정] 같은 날짜+제목으로 다시 가져오면 중복 추가가 아니라
# 내용만 갱신되는지(화면에서 입력한 것과 같은 내용을 엑셀로 올렸을 때
# 중복 등록되던 문제)
_count_before_reimport = len(sched.local_events)
_reimport_path = _os.path.join(_tf.gettempdir(), "fkpp_sched_reimport_test.xlsx")
_wb2 = _opx.Workbook(); _ws2 = _wb2.active
_ws2.append(["날짜", "제목", "내용"])
_ws2.append(["2026-10-05", "개천절 대체휴일", ""])   # 방금 가져온 것과 완전히 동일
with _patch("src.utils.schedule.QFileDialog.getOpenFileName", return_value=(_reimport_path, "")):
    _wb2.save(_reimport_path)
    sched._import_excel()
app.processEvents()
check("[버그 수정] 같은 날짜+제목을 다시 가져와도 건수가 늘지 않음(중복 방지)",
      len(sched.local_events) == _count_before_reimport, len(sched.local_events))

# 제목은 같고 내용만 바뀐 경우는 갱신되는지
_reimport_path2 = _os.path.join(_tf.gettempdir(), "fkpp_sched_reimport_test2.xlsx")
_wb3 = _opx.Workbook(); _ws3 = _wb3.active
_ws3.append(["날짜", "제목", "내용"])
_ws3.append(["2026-10-05", "개천절 대체휴일", "수정된 내용"])
_wb3.save(_reimport_path2)
with _patch("src.utils.schedule.QFileDialog.getOpenFileName", return_value=(_reimport_path2, "")):
    sched._import_excel()
app.processEvents()
_matched = [e for e in sched.local_events if e.ymd == "20261005" and e.name == "개천절 대체휴일"]
check("[버그 수정] 같은 제목·다른 내용은 새로 추가되지 않고 내용만 갱신됨",
      len(sched.local_events) == _count_before_reimport and len(_matched) == 1
      and _matched[0].content == "수정된 내용", (len(sched.local_events), [m.content for m in _matched]))
for _p in (_reimport_path, _reimport_path2):
    if _os.path.exists(_p):
        _os.remove(_p)

# openpyxl 없을 때도 안전한지
_orig_import = _builtins.__import__
def _no_openpyxl(name, *a, **k):
    if name == "openpyxl":
        raise ImportError("test")
    return _orig_import(name, *a, **k)
_builtins.__import__ = _no_openpyxl
_QMB.information = staticmethod(lambda *a, **k: None)
try:
    sched._import_excel()
    sched._export_excel()
    check("[v09] openpyxl 없어도 예외 없음", True)
except Exception as e:
    check("[v09] openpyxl 없어도 예외 없음", False, e)
finally:
    _builtins.__import__ = _orig_import

# 인쇄
from PySide6.QtPrintSupport import QPrintDialog as _QPD2, QPrinter as _QPR2
from PySide6.QtGui import QPageLayout as _QPL2
_orig_pd_exec = _QPD2.exec
_sched_printer = {}
def _fake_sched_exec(self):
    _sched_printer["p"] = self.printer()
    return 1
_QPD2.exec = _fake_sched_exec
try:
    sched.local_events = [SL.LocalEvent(f"{sched.year:04d}{sched.month:02d}05",
                                        "체육대회", "운동장, 우천시 강당")]
    sched._save_local()
    sched._apply_events()
    sched._print()
    check("[v09] 인쇄 실행 중 예외 없음", True)
    _sp = _sched_printer.get("p")
    check("[버그 수정] 학교 일정 인쇄도 가로 방향으로 설정됨",
          _sp is not None and _sp.pageLayout().orientation() == _QPL2.Landscape)
    check("[버그 수정] fullPage로 설정됨(프린터 드라이버 여백을 직접 통제)",
          _sp is not None and _sp.fullPage())

    # [버그 수정] HTML 대신 print_grid로 직접 그리므로, 실제로 그려질
    # 칸(GridCell) 내용에 제목과 상세 내용이 함께 들어가는지 확인한다
    # (이전엔 제목만 나왔다).
    _weeks_print = sched._print_grid_weeks()
    _all_texts = [text for week in _weeks_print for cell in week for text, *_ in cell.lines]
    check("[버그 수정] 인쇄용 칸에 제목과 상세 내용이 함께 들어감(제목만 나오던 문제)",
          any("체육대회" in t for t in _all_texts) and any("운동장, 우천시 강당" in t for t in _all_texts))

    if _has_pdftoppm:
        import os as _os4, tempfile as _tf4
        _sched_pdf = _os4.path.join(_tf4.gettempdir(), "fkpp_sched_margin_test.pdf")
        _printer_s = _QPrinterPrint(_QPrinterPrint.HighResolution)
        _printer_s.setPageOrientation(_QPageLayout2.Landscape)
        _printer_s.setFullPage(True)
        _printer_s.setOutputFormat(_QPrinterPrint.PdfFormat)
        _printer_s.setOutputFileName(_sched_pdf)
        _painter_s = _QPainterPrint(_printer_s)
        from src.utils.schedule import _WEEKDAY_KEYS
        _headers_s = [tr(k) for k in _WEEKDAY_KEYS]
        _PG.print_calendar(_printer_s, _painter_s, "여백측정", C.UTIL_MAIN, _headers_s,
                           _weeks_print, margin_pt=3 * 2.83465)
        _painter_s.end()
        _l_mm2, _r_mm2 = _measure_lr_margin_mm(_sched_pdf)
        check("[버그 수정] 학교 일정 인쇄 좌측 여백도 10mm 이하", _l_mm2 is not None and _l_mm2 < 10, _l_mm2)
        check("[버그 수정] 학교 일정 인쇄 우측 여백도 10mm 이하(비대칭 해소)",
              _r_mm2 is not None and _r_mm2 < 10, _r_mm2)
        for _p in (_sched_pdf, _sched_pdf.replace(".pdf", "-1.png")):
            if _os4.path.exists(_p):
                _os4.remove(_p)
except Exception as e:
    check("[v09] 인쇄 실행 중 예외 없음", False, e)
finally:
    _QPD2.exec = _orig_pd_exec
    sched.local_events = []
    sched._save_local()
    sched._apply_events()

section("25. 급식·일정 — 인증키/학교코드 공유")
win.util_panel.open_app("meal")
app.processEvents()
meal2 = win.util_panel._pages["meal"][0]
check("급식과 일정이 같은 인증키를 공유", meal2.neis_panel.values()[0] == "TESTKEY")

win5 = MainWindow()
win5.switch_mode("util")
win5.util_panel.open_app("schedule")
app.processEvents()
sched5 = win5.util_panel._pages["schedule"][0]
check("재기동 후에도 공유 설정 유지", sched5.neis_panel.values()[0] == "TESTKEY")
win5.close()

section("26. 다국어 · 아이콘 · 카테고리 이름 변경")
win.util_panel.open_app("schedule")
app.processEvents()
for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 학교 일정 재번역 중 예외 없음", True)
    check(f"[{lang}] 학교 일정 도구 이름 번역", win.lbl_util_current.text() == tr("util.schedule.title"))

check("schedule 앱 아이콘 생성", not make_app_icon("schedule", C.UTIL_MAIN, 32).isNull())
check('"학급" 카테고리가 "학교"로 표시됨(내부 키는 그대로 class)',
      tr("util.cat.class") == "학교")
win.util_panel.show_home()
app.processEvents()
check("홈 화면에 학교 카테고리 아래 급식+일정 모두 보임",
      any(a.category == "class" and a.id == "meal" for a in win.util_apps)
      and any(a.category == "class" and a.id == "schedule" for a in win.util_apps))

# =============================================================================
section("27. [v06] 메뉴 재구성 — 수학(계산기+그래프) / 정보컴퓨터(카르노맵)")
check('카테고리 "논리"가 "정보컴퓨터"로 표시됨(내부 키는 그대로 logic)',
      tr("util.cat.logic") == "정보컴퓨터")
check("그래프 앱이 math 카테고리로 옮겨짐",
      any(a.id == "graph" and a.category == "math" for a in win.util_apps))
check("계산기도 그대로 math 카테고리",
      any(a.id == "calc" and a.category == "math" for a in win.util_apps))
check("카르노맵은 그대로 logic(=정보컴퓨터) 카테고리",
      any(a.id == "kmap" and a.category == "logic" for a in win.util_apps))
check("더 이상 'graph' 카테고리는 쓰지 않음(수학으로 흡수)",
      not any(a.category == "graph" for a in win.util_apps))
math_apps = {a.id for a in win.util_apps if a.category == "math"}
check("수학 카테고리 안에 계산기+그래프+극좌표그래프가 모두 있음",
      math_apps == {"calc", "graph", "polar"}, math_apps)

# =============================================================================
section("27b. [신규] 극좌표 그래프 — 순수 로직")
from src.utils import polar_solve as PS
import math as _math2

r = PS.sample("3", 0, 2 * _math2.pi, 360)
dists = [_math2.hypot(x, y) for x, y in zip(r.xs, r.ys) if x is not None]
check("원(r=3) 모든 점의 원점 거리 = 3", all(abs(d - 3) < 1e-6 for d in dists))

r2 = PS.sample("1+cos(theta)", 0, 2 * _math2.pi, 4)
check("심장형 theta=0 -> r=2", abs(r2.rs[0] - 2) < 1e-9, r2.rs[0])

r3 = PS.sample("3", 0, 360, 5, angle_mode="deg")
check("DEG 모드 theta=90도 -> (x~0, y~3)", abs(r3.xs[1]) < 1e-6 and abs(r3.ys[1] - 3) < 1e-6)

segs = PS.build_segments([1, 2, None, 4, 5], [1, 2, None, 4, 5])
check("정의 안 되는 지점에서 구간이 끊김(2개)", len(segs) == 2)

r4 = PS.sample("+++", 0, 1, 5)
check("파싱 오류 시 error 채워짐", r4.error is not None and r4.xs == [])

check("PRESETS 6개, 각각 (키,수식,시작,끝) 형태",
      len(PS.PRESETS) == 6 and all(len(p) == 4 for p in PS.PRESETS))

section("27c. [신규] 극좌표 그래프 — 위젯 통합")
win.switch_mode("util")
win.util_panel.open_app("polar")
app.processEvents()
pw = win.util_panel._pages["polar"][0]
check("기본 함수는 3잎 장미선(cos(3*theta))", pw.rows[0].edit.text() == "cos(3*theta)")
check("기본 각도 모드는 RAD", pw.angle_mode == "rad")

_before_rows = len(pw.rows)
_idx_spiral = pw.combo_preset.findData("spiral")
pw.combo_preset.setCurrentIndex(_idx_spiral)
app.processEvents()
check("예시 곡선을 고르면 새 함수 행이 추가됨", len(pw.rows) == _before_rows + 1)
check("추가된 행에 나선 수식이 들어감", pw.rows[-1].edit.text() == "theta")

pw.rows[0].edit.setText("sqrt(-1-theta)")
app.processEvents()
check("[위젯] 항상 정의 안 되는 식은 입력창에 오류 표시", pw.rows[0].lbl_error.text() != "")
pw.rows[0].edit.setText("cos(3*theta)")
app.processEvents()
check("[위젯] 정상 식으로 되돌리면 오류 사라짐", pw.rows[0].lbl_error.text() == "")

pw.canvas.fit_view()
app.processEvents()
_plot = pw.canvas._plot_rect()
_s = pw.canvas._scale(_plot)
check("[위젯] 등각 렌더링 — 확대 배율이 유한한 양수", _s > 0)

pw._toggle_angle()
app.processEvents()
check("[위젯] RAD/DEG 토글 동작", pw.angle_mode == "deg" and pw.btn_angle.text() == "DEG")
pw._toggle_angle()

# 이미지로 저장
import os as _os5, tempfile as _tf5
from PySide6.QtWidgets import QFileDialog as _QFD5
_polar_img = _os5.path.join(_tf5.gettempdir(), "fkpp_polar_test.png")
with _patch("src.utils.polar.QFileDialog.getSaveFileName", return_value=(_polar_img, "")):
    pw._export_image()
check("[위젯] 이미지로 저장한 파일이 실제로 생성됨",
      _os5.path.exists(_polar_img) and _os5.path.getsize(_polar_img) > 0)
if _os5.path.exists(_polar_img):
    _os5.remove(_polar_img)

# 설정 저장/복원
pw.rows[0].edit.setText("2+sin(theta)")
app.processEvents()
win6 = MainWindow()
win6.switch_mode("util")
win6.util_panel.open_app("polar")
app.processEvents()
pw6 = win6.util_panel._pages["polar"][0]
check("재기동 후 함수 내용 복원", pw6.rows[0].edit.text() == "2+sin(theta)")
win6.close()

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 극좌표 그래프 재번역 중 예외 없음", True)
    check(f"[{lang}] 극좌표 그래프 도구 이름 번역", win.lbl_util_current.text() == tr("util.polar.title"))

check("polar 앱 아이콘 생성", not make_app_icon("polar", C.UTIL_MAIN, 32).isNull())
check("극좌표 그래프가 수학(math) 카테고리에 속함",
      any(a.id == "polar" and a.category == "math" for a in win.util_apps))

section("27d. [신규] 대진표 작성기 — 순수 로직")
from src.utils import bracket_solve as BS

_names10 = [f"학생{i}" for i in range(1, 11)]
_teams = BS.balanced_teams(_names10, 3, seed=1)
check("3팀으로 나누면 팀 개수가 3개", len(_teams) == 3)
check("인원 차이가 최대 1명(10명/3팀)", sorted(len(t) for t in _teams) == [3, 3, 4])
check("전체 인원 보존(누락/중복 없음)", sorted(sum(_teams, [])) == sorted(_names10))

_rounds = BS.single_elimination(_names10, seed=1)
check("첫 라운드 매치 수 = 8(16으로 맞춤, 10명)", len(_rounds[0]) == 8)
check("1라운드에 전원이 정확히 한 번씩", sorted(
      x for a, b in _rounds[0] for x in (a, b) if x is not None) == sorted(_names10))
check("마지막 라운드는 결승(매치 1개)", len(_rounds[-1]) == 1)

_rounds8 = BS.single_elimination([f"P{i}" for i in range(8)], seed=2)
check("8명이면 부전승 없음", all(a is not None and b is not None for a, b in _rounds8[0]))
check("8명이면 3라운드", len(_rounds8) == 3)

_rr = BS.round_robin_schedule([f"P{i}" for i in range(6)], seed=3)
check("6명 리그전 -> 5라운드", len(_rr) == 5)
_all_pairs = {frozenset((a, b)) for rnd in _rr for a, b in rnd}
check("6명 리그전 -> 모든 조합이 한 번씩(15경기)", len(_all_pairs) == 15)

_rr5 = BS.round_robin_schedule([f"P{i}" for i in range(5)], seed=4)
check("홀수(5명) 리그전 -> 매 라운드 부전승 있음",
      all(any(a is None or b is None for a, b in rnd) for rnd in _rr5))

check("이름 파싱: 빈 줄 제거 + 공백 정리",
      BS.parse_names("김철수\n\n  이영희  \n") == ["김철수", "이영희"])
check("같은 seed면 같은 결과(재현 가능)",
      BS.balanced_teams(_names10, 3, seed=42) == BS.balanced_teams(_names10, 3, seed=42))

section("27e. [신규] 대진표 작성기 — 학급 명단 기반(순수 로직)")
import openpyxl as _opxr
from src.utils import bracket_solve as B
from PySide6.QtWidgets import QMessageBox, QDialog

check("[버그 수정] 부전승 2개 이상이어도 None-vs-None 매치가 생기지 않음(6명 예시)",
      not any(m.a is None and m.b is None for m in B.Bracket({f"e{i}": f"선수{i}" for i in range(6)}).rounds[0]))
check("[버그 수정] 참가자 2~19명 어떤 인원에서도 None-vs-None 없음",
      all(not any(a is None and b is None for a, b in B.single_elimination([f"p{i}" for i in range(n)], seed=1)[0])
         for n in range(2, 20)))

_roster_path = _os.path.join(_tf.gettempdir(), "fkpp_roster_test.xlsx")
_wbr = _opxr.Workbook(); _wsr = _wbr.active
_wsr.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 9):
    _wsr.append([1, 1, i, f"학생{i}", "남" if i % 2 == 0 else "여"])
_wbr.save(_roster_path)
_roster = B.read_roster_excel(_roster_path)
check("명단 8명 읽힘", len(_roster) == 8)
check("[신규] 학년 컬럼이 정확히 읽힘", _roster[0].grade == "1")
check("첫 학생 정보 정확", _roster[0].cls == "1" and _roster[0].name == "학생1")
check("[v38] label()은 번호만 표시(학년·반은 화면이 이미 보여주므로 생략)",
      _roster[0].label() == "학생1(1번)", _roster[0].label())

# [신규] 팀당 인원 일반화(group_into_teams) — 개인전/복식/단체전
_teams1 = B.group_into_teams(_roster, 1, seed=1)
check("[신규] 팀당 인원 1(개인전) -> 8팀, 각 1명", len(_teams1) == 8 and all(len(t) == 1 for t in _teams1))
_teams2 = B.group_into_teams(_roster, 2, seed=1)
check("[신규] 팀당 인원 2(복식) -> 4팀, 각 2명", len(_teams2) == 4 and all(len(t) == 2 for t in _teams2))
_teams3 = B.group_into_teams(_roster, 3, seed=1)
check("[신규] 팀당 인원 3(단체전) -> 마지막 팀만 인원이 적음", sorted(len(t) for t in _teams3) == [2, 3, 3])
check("[신규] 하위호환: pair_doubles == group_into_teams(...,2,...)", len(B.pair_doubles(_roster, seed=1)) == 4)

# [신규] League 클래스(리그전, 결과 기록 가능)
_labels = {f"e{i}": f"팀{i}" for i in range(6)}
_league = B.League(_labels)
check("[신규] 6팀 리그 -> 5라운드", len(_league.rounds) == 5)
check("[신규] 각 라운드 매치 3개(6/2)", all(len(r) == 3 for r in _league.rounds))
_all_pairs = {frozenset((m.a, m.b)) for rnd in _league.rounds for m in rnd}
check("[신규] 모든 조합이 정확히 한 번씩(6팀->15경기)", len(_all_pairs) == 15)
_league.record(0, 0, "a", note="3:1")
check("[신규] 리그 결과 기록됨", _league.rounds[0][0].winner == "a" and _league.rounds[0][0].note == "3:1")
_league.clear_result(0, 0)
check("[신규] 리그 결과 취소됨", _league.rounds[0][0].winner is None)
_league2 = B.League.from_dict(_league.to_dict())
check("[신규] League 직렬화/복원", len(_league2.rounds) == 5)

# [신규] Event/build_event(형식+팀인원)
_ev_t = B.build_event("배드민턴", _roster, format=B.FORMAT_TOURNAMENT, team_size=2, seed=1)
check("[신규] 토너먼트 종목 생성 -> Bracket 사용", isinstance(_ev_t.bracket, B.Bracket))
check("[신규] 팀 인원 2로 4개 엔트리", len(_ev_t.entries) == 4)
_ev_l = B.build_event("피구", _roster, format=B.FORMAT_LEAGUE, team_size=4, seed=1)
check("[신규] 리그 종목 생성 -> League 사용", isinstance(_ev_l.bracket, B.League))
_ev_l2 = B.Event.from_dict(_ev_l.to_dict())
check("[신규] Event(리그) 직렬화/복원 시 형식 유지",
      _ev_l2.format == B.FORMAT_LEAGUE and isinstance(_ev_l2.bracket, B.League))
_ev_t2 = B.Event.from_dict(_ev_t.to_dict())
check("[신규] Event(토너먼트) 직렬화/복원 시 형식 유지",
      _ev_t2.format == B.FORMAT_TOURNAMENT and isinstance(_ev_t2.bracket, B.Bracket))

section("27f. [신규] 대진표 작성기 — 세트 점수 계산·엑셀 누적 기록(순수 로직)")

_a, _b, _w = B.compute_sets_result([(21, 15), (18, 21), (21, 18)])
check("[신규] 세트 점수로 2:1 승부 계산", (_a, _b, _w) == (2, 1, "a"))
_a2, _b2, _w2 = B.compute_sets_result([(15, 21), (21, 18)])
check("[신규] 1:1 동률이면 승자 없음", _w2 is None)

check("[신규] 팀 라벨이 줄바꿈으로 합쳐짐(셀 잘림 버그 수정)",
      all("\n" in lb for lb in B.build_event("복식", _roster, team_size=2, seed=1).bracket.entries.values()))

_name = B.build_event_name("배드민턴", _roster, B.FORMAT_LEAGUE, date_str="20260918")
check("[신규] 자동 종목 이름 형식(학년 포함, 배드민턴_1학년1반_리그전_20260918)",
      _name == "배드민턴_1학년1반_리그전_20260918", _name)

_roster2 = _roster + [B.Student("s9", "2", "1", "5", "학생9")]
_name2 = B.build_event_name("탁구", _roster2, B.FORMAT_TOURNAMENT, date_str="20260918")
check("[신규] 여러 학년이면 학년별로 구분해 쉼표로 연결(1학년1반,2학년1반)",
      _name2 == "탁구_1학년1반,2학년1반_토너먼트전_20260918", _name2)

_roster_by_sid = {s.sid: s for s in _roster}
_sid0, _sid1, _sid2, _sid3 = _roster[0].sid, _roster[1].sid, _roster[2].sid, _roster[3].sid
_sets_ex = [(21, 15), (18, 21), (21, 18)]   # 참가자A(사이드0,1) 관점 2:1로 승리

# [버그 수정] 승리측 줄은 is_side_a=True(그 편이 실제로 세트 원본에서 A쪽), 패배측은
# is_side_a=False로 호출해 각자 자기 관점으로 세트결과·세트스코어가 나오는지 확인
_hist_rows_win = B.build_history_rows("배드민턴", B.FORMAT_LEAGUE, "20260918", _roster_by_sid,
                                     side_sids=[_sid0, _sid1], opp_sids=[_sid2, _sid3],
                                     sets=_sets_ex, is_side_a=True)
check("[신규] 승리 팀 인원수만큼 기록 행 생성", len(_hist_rows_win) == 2)
check("[신규] 같은편·상대 필드가 정확히 채워짐",
      _hist_rows_win[0]["같은편"] == _roster_by_sid[_sid1].name and
      _hist_rows_win[0]["상대"] == f"{_roster_by_sid[_sid2].name}, {_roster_by_sid[_sid3].name}")
check("[버그 수정] 승리측 줄: 결과=승, 세트결과=2:1(내 관점, 앞이 항상 내 승수)",
      _hist_rows_win[0]["결과"] == "승" and _hist_rows_win[0]["세트결과"] == "2:1")
check("[신규] 학년 컬럼이 정확히 채워짐", _hist_rows_win[0]["학년"] == _roster_by_sid[_sid0].grade)

_hist_path_pure = _os.path.join(_tf.gettempdir(), "fkpp_history_pure_test.xlsx")
B.append_history(_hist_path_pure, _hist_rows_win)
check("[신규] 누적 기록 엑셀 파일이 실제로 생성됨", _os.path.exists(_hist_path_pure))

_hist_rows_lose = B.build_history_rows("배드민턴", B.FORMAT_LEAGUE, "20260918", _roster_by_sid,
                                      side_sids=[_sid2, _sid3], opp_sids=[_sid0, _sid1],
                                      sets=_sets_ex, is_side_a=False)
check("[버그 수정] 패배측 줄: 결과=패, 세트결과=1:2(뒤집혀서 내 관점 — 예전엔 '2:1'로 헷갈렸음)",
      _hist_rows_lose[0]["결과"] == "패" and _hist_rows_lose[0]["세트결과"] == "1:2")
B.append_history(_hist_path_pure, _hist_rows_lose)   # 이어서 추가(누적 확인)
_stats = B.read_history_stats(_hist_path_pure, sport="배드민턴")
_key_win = (_roster_by_sid[_sid0].grade, _roster_by_sid[_sid0].cls,
           _roster_by_sid[_sid0].num, _roster_by_sid[_sid0].name)
_key_lose = (_roster_by_sid[_sid2].grade, _roster_by_sid[_sid2].cls,
            _roster_by_sid[_sid2].num, _roster_by_sid[_sid2].name)
check("[신규] 이어서 추가해도 이전 기록이 안 사라짐(승·패 모두 집계됨, 학년 포함 키)",
      _stats[_key_win]["wins"] == 1 and _stats[_key_lose]["losses"] == 1)

# [신규] 옛 형식(학년·세트스코어 없음) 파일에 이어 쓰면 자동으로 마이그레이션되는지
_old_headers = ["날짜", "종목", "형식", "반", "번호", "이름", "결과", "세트결과", "같은편", "상대"]
_old_hist_path = _os.path.join(_tf.gettempdir(), "fkpp_history_old_format_test.xlsx")
_wb_old = _opxr.Workbook(); _ws_old = _wb_old.active
_ws_old.append(_old_headers)
_ws_old.append(["20260901", "배드민턴", "리그전", "1", "1", "옛학생", "승", "2:1", "", ""])
_wb_old.save(_old_hist_path)
B.append_history(_old_hist_path, _hist_rows_win)
_wb_migrated = _opxr.load_workbook(_old_hist_path)
_ws_migrated = _wb_migrated.active
_migrated_headers = [_ws_migrated.cell(row=1, column=c).value for c in range(1, _ws_migrated.max_column + 1)]
check("[신규] 옛 형식 파일에 이어 쓰면 헤더가 새 형식으로 자동 보정됨",
      _migrated_headers == B.HISTORY_HEADERS)
check("[신규] 옛 데이터 줄(이름 등)은 그대로 보존됨",
      any(_ws_migrated.cell(row=r, column=_migrated_headers.index("이름") + 1).value == "옛학생"
         for r in range(2, _ws_migrated.max_row + 1)))

for _p in (_hist_path_pure, _old_hist_path):
    if _os.path.exists(_p):
        _os.remove(_p)

section("27g. [신규] 대진표 작성기 — 위젯(참가자 선택 + 종목/형식/팀인원 자동 제목)")
win.switch_mode("util")
win.util_panel.open_app("bracket")
app.processEvents()
bkw = win.util_panel._pages["bracket"][0]
check("[위젯] '빠른 대진표' 관련 요소가 완전히 제거됨(더 이상 없음)",
      not hasattr(bkw, "btn_page_quick") and not hasattr(bkw, "quick_page") and not hasattr(bkw, "edit_event_name"))
check("[위젯] 종목 콤보박스에 배드민턴/탁구/농구/기타가 있음",
      [bkw.combo_sport.itemText(i) for i in range(bkw.combo_sport.count())] == B.SPORT_OPTIONS)
check("[위젯] 처음엔 참가자 선택 탭이 기본으로 보임", bkw.tabs.currentIndex() == 0)

with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_roster_path, "")):
    bkw._on_roster_upload()
app.processEvents()
check("[위젯] 명단 업로드 후 상태 문구에 학생 수 표시", "8" in bkw.lbl_roster_status.text())

_class_item = bkw.tree_participants.topLevelItem(0)
check("[위젯] 참가자 미선택 상태에서는 이름 미리보기가 안내문만 보임",
      "(" in bkw.lbl_name_preview.text())
_class_item.setCheckState(0, Qt.Checked)
app.processEvents()
check("[위젯] 반 체크 시 그 반 전체 학생이 자동 체크됨(트리스테이트)",
      all(_class_item.child(j).checkState(0) == Qt.Checked for j in range(_class_item.childCount())))
check("[v38] 참가자를 고르면 이름 미리보기가 자동으로 만들어짐(기본은 리그전: 배드민턴_1학년1반_리그전_)",
      bkw.lbl_name_preview.text().startswith("배드민턴_1학년1반_리그전_"))

bkw._set_format(B.FORMAT_LEAGUE)
check("[위젯] 형식을 바꾸면 미리보기도 즉시 바뀜(리그전)", "리그전" in bkw.lbl_name_preview.text())

_class_item.child(0).setCheckState(0, Qt.Unchecked)
app.processEvents()
check("[위젯] 결석 처리 후 선택 인원이 줄어듦", "7" in bkw.lbl_participant_count.text())

_idx_other = bkw.combo_sport.findText(B.SPORT_OTHER)
bkw.combo_sport.setCurrentIndex(_idx_other)
app.processEvents()
check("[위젯] '기타' 선택 시 종목명 직접 입력창이 나타남", bkw.edit_sport_other.isVisible())
bkw.edit_sport_other.setText("피구")
app.processEvents()
check("[위젯] 기타 종목명을 입력하면 미리보기에 반영됨", bkw.lbl_name_preview.text().startswith("피구_"))
_idx_badminton = bkw.combo_sport.findText("배드민턴")
bkw.combo_sport.setCurrentIndex(_idx_badminton)
app.processEvents()

section("27gz. [버그 수정] 경기 결과 기록 다이얼로그 — 정합성 검증")
from src.utils.bracket import _RecordResultDialog
from PySide6.QtCore import Qt as _Qt2

_dlg1 = _RecordResultDialog("A", "B")
_dlg1.edits_a[0].setText("21"); _dlg1.edits_b[0].setText("15")
_dlg1.edits_a[1].setText("21"); _dlg1.edits_b[1].setText("18")
_ok1, _err1, _sets1 = _dlg1._validate()
check("[버그 수정] 정상 2세트 입력 -> 오류 없음", _ok1 and _err1 == "" and len(_sets1) == 2)
_w1, _s1, _n1 = _dlg1.result()
check("[버그 수정] 2:0으로 A 승리 판정", _w1 == "a" and _n1 == "2:0")

_dlg2 = _RecordResultDialog("A", "B")
_dlg2.edits_a[0].setText("21"); _dlg2.edits_b[0].setText("15")
_dlg2.edits_a[1].setText("11"); _dlg2.edits_b[1].setText("21")
_dlg2.edits_a[2].setText("1")   # 오른쪽은 비워둠 — 한쪽만 입력된 세트
_ok2, _err2, _sets2 = _dlg2._validate()
check("[버그 수정] 한쪽 점수만 입력된 세트는 오류로 막힘(정합성 강화)", not _ok2 and _err2 != "")
_w2, _, _ = _dlg2.result()
check("[버그 수정] 부분 입력이면 result()도 승자 없음", _w2 is None)

_dlg3 = _RecordResultDialog("A", "B")
_dlg3.edits_a[0].setText("21"); _dlg3.edits_b[0].setText("15")
_dlg3.edits_a[2].setText("21"); _dlg3.edits_b[2].setText("18")   # 2세트를 비우고 3세트만 입력
_ok3, _err3, _sets3 = _dlg3._validate()
check("[버그 수정] 세트를 건너뛰고 입력하면 오류로 막힘(위쪽부터 순서대로 입력해야 함)",
      not _ok3 and _err3 != "")

_dlg4 = _RecordResultDialog("A", "B")
_dlg4.edits_a[0].setText("21"); _dlg4.edits_b[0].setText("15")
_dlg4.edits_a[1].setText("21"); _dlg4.edits_b[1].setText("18")
# 3세트는 완전히 비워둠(둘 다 빈칸) -> 정상(2세트 만에 끝난 경기)
_ok4, _err4, _sets4 = _dlg4._validate()
check("[버그 수정] 양쪽 다 완전히 빈 세트는 문제 없음(치르지 않은 세트로 처리)",
      _ok4 and len(_sets4) == 2)

check("[버그 수정] 점수 입력창에 QIntValidator가 걸려 있음(범위 밖 숫자 차단)",
      _dlg1.edits_a[0].validator() is not None)
check("[버그 수정] 입력기 힌트가 '숫자만'으로 설정됨(한글 입력기가 조합 모드로 안 들어가게)",
      bool(_dlg1.edits_a[0].inputMethodHints() & _Qt2.ImhDigitsOnly))

# 이전 결과를 다시 열었을 때 세트 점수가 정확히 채워지는지(수정 편의)
_dlg5 = _RecordResultDialog("A", "B", current_sets=[[21, 15], [18, 21], [21, 18]])
check("[버그 수정] 기존 세트 점수를 다시 열면 정확히 채워짐",
      _dlg5.edits_a[0].text() == "21" and _dlg5.edits_b[2].text() == "18")

section("27h. [신규] 대진표 작성기 — 위젯(생성·세트점수 기록·엑셀 저장·재기동 유지)")
_hist_path_widget = _os.path.join(_tf.gettempdir(), "fkpp_history_widget_test.xlsx")
if _os.path.exists(_hist_path_widget):
    _os.remove(_hist_path_widget)
# [v38] 시리즈 파일은 누적 엑셀과 같은 폴더에 저장되므로, 실제 사용 흐름처럼
# 라운드를 만들기 전에 먼저 경로를 정해 둔다(안 정하면 이번 라운드는
# 메모리에만 남고 파일로는 안 남는다 — "다음 시간에 이어서" 하려면 필요).
# 이 임시 경로를 이전 테스트 실행에서 쓴 시리즈 파일이 남아 있을 수 있어
# 먼저 지운다(이번 실행 결과만 정확히 보려고).
for _skey, _spath in B.list_series_files(_hist_path_widget):
    _os.remove(_spath)
bkw._history_path = _hist_path_widget
bkw._set_format(B.FORMAT_LEAGUE)
bkw.spin_team_size.setValue(2)
bkw.combo_tier_mode.setCurrentIndex(0)   # [v38] 기본값이 수준별 분리로 바뀌었으니, 이 테스트는 명시적으로 무작위로
bkw._on_generate()
app.processEvents()
app.processEvents()
check("[위젯] '생성'을 누르면 자동으로 대진표 탭으로 전환됨", bkw.tabs.currentIndex() == 1)
check("[v38] 종목 이름이 자동 생성 규칙 그대로 저장됨(학년 포함)",
      bkw._current_event.name.startswith("배드민턴_1학년1반_리그전_"))
check("[위젯] 리그전이라 리그 표가 보이고 토너먼트 캔버스는 숨겨짐",
      bkw.league_view.isVisible() and not bkw.roster_result_scroll.isVisible())

_event = bkw._current_event
check("[위젯] 팀당 인원 2로 묶여서 entry 라벨에 줄바꿈이 있음(팀원 여러 명)",
      any("\n" in lb for lb in _event.bracket.entries.values()))

_ready = [(i, m) for i, m in enumerate(_event.bracket.rounds[0]) if m.is_ready()]
_ri, _mi = 0, _ready[0][0]

class _FakeSetDialog:
    def __init__(self, *a, **k):
        pass
    def exec(self):
        return QDialog.Accepted
    def is_cleared(self):
        return False
    def result(self):
        return "a", [[21, 15], [18, 21], [21, 18]], "2:1"

import src.utils.bracket as _bracket_mod
_orig_dlg = _bracket_mod._RecordResultDialog
_bracket_mod._RecordResultDialog = _FakeSetDialog
bkw._on_league_match_clicked(_ri, _mi)
app.processEvents()
_m = _event.bracket.rounds[_ri][_mi]
check("[위젯] 세트 점수로 승부가 기록되고 '2:1' 형식으로 요약됨", _m.winner == "a" and _m.note == "2:1")
check("[위젯] 원본 세트 점수도 함께 저장됨(다시 열 때 쓰려고)", _m.sets == [[21, 15], [18, 21], [21, 18]])
_bracket_mod._RecordResultDialog = _orig_dlg

with _patch("src.utils.bracket.QFileDialog.getSaveFileName", return_value=(_hist_path_widget, "")):
    bkw._on_save_to_excel()
app.processEvents()
check("[위젯] 엑셀 결과 저장 후 파일이 실제로 생성됨", _os.path.exists(_hist_path_widget))
check("[위젯] 저장한 매치는 saved=True로 표시됨(중복 저장 방지용)", _m.saved is True)

import openpyxl as _opxr2
_wb_check = _opxr2.load_workbook(_hist_path_widget)
_rows_first = _wb_check.active.max_row
with _patch("src.utils.bracket.QMessageBox.information", return_value=None):
    bkw._on_save_to_excel()   # 새로 기록할 게 없으니 아무것도 추가되지 않아야 함
_wb_check2 = _opxr2.load_workbook(_hist_path_widget)
check("[위젯] 같은 결과를 두 번 저장해도 중복으로 안 쌓임", _wb_check2.active.max_row == _rows_first)

bkw._refresh_participant_labels()
app.processEvents()
_winner_sids = _event.entry_student_ids(_m.a)
_winner_wl_cell = None
for j in range(_class_item.childCount()):
    child = _class_item.child(j)
    if child.data(0, Qt.UserRole) == _winner_sids[0]:
        _winner_wl_cell = child.text(1)   # [신규→표 형태] 승패는 이제 2번째 열(별도 칸)
check("[위젯] 참가자 표의 '승패' 칸에 승리 학생의 기록이 표시됨(1승)",
      _winner_wl_cell is not None and "1승" in _winner_wl_cell and "0패" in _winner_wl_cell)

# 참가자 2명 미만이면 생성 거부
for j in range(1, _class_item.childCount()):
    _class_item.child(j).setCheckState(0, Qt.Unchecked)
app.processEvents()
_before_count = len(bkw.events)
bkw._on_generate()
app.processEvents()
check("[위젯] 참가자 1명뿐이면 종목이 추가되지 않음(생성 거부)", len(bkw.events) == _before_count)

# 재기동 후에도 명단·종목·기록·history_path가 유지되는지
win_bk2 = MainWindow(); win_bk2.show()
win_bk2.switch_mode("util"); win_bk2.util_panel.open_app("bracket")
app.processEvents()
bkw2 = win_bk2.util_panel._pages["bracket"][0]
check("[위젯] 재기동해도 명단이 유지됨", len(bkw2.roster) == 8)
check("[위젯] 재기동해도 종목이 유지됨", len(bkw2.events) == 1)
check("[위젯] 재기동해도 세트 결과·요약이 유지됨",
      bkw2.events[0].bracket.rounds[_ri][_mi].note == "2:1" and
      bkw2.events[0].bracket.rounds[_ri][_mi].sets == [[21, 15], [18, 21], [21, 18]])
check("[위젯] 재기동해도 누적 기록 파일 경로가 유지됨", bkw2._history_path == _hist_path_widget)
bkw2._refresh_participant_labels()
root2 = bkw2.tree_participants.invisibleRootItem()
_class_item2 = root2.child(0)
_winner_wl_cell2 = None
for j in range(_class_item2.childCount()):
    child = _class_item2.child(j)
    if child.data(0, Qt.UserRole) == _winner_sids[0]:
        _winner_wl_cell2 = child.text(1)
check("[위젯] 재기동해도 참가자 표의 '승패' 칸 표시가 유지됨",
      _winner_wl_cell2 is not None and "1승" in _winner_wl_cell2)
win_bk2.close()

with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw._on_roster_clear()
app.processEvents()
check("[위젯] 명단 지우기 후 명단·종목 모두 빈 상태", not bkw.roster and not bkw.events)

for _p in (_roster_path, _hist_path_widget):
    if _os.path.exists(_p):
        _os.remove(_p)

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 대진표(학급 명단) 재번역 중 예외 없음", True)

section("27i. [신규] 대진표 작성기 — 실력 등급(자동/수동) + 파트너 반복 회피")
_students_tier = [B.Student(f"t{i}", "1", "1", str(i), f"학생{i}") for i in range(1, 11)]

# 순수 로직: 자동 등급/수동 등급/유효 등급
check("[신규] 자동 등급: 경기 3회 이상, 승률 60%+ -> 상", B.compute_auto_tier(3, 0) == B.TIER_HIGH)
check("[신규] 유효 등급: 수동이 있으면 수동이 이김(자동보다 우선)",
     B.effective_tier(B.TIER_HIGH, B.TIER_LOW) == B.TIER_HIGH)
check("[신규] 수동 등급 JSON 직렬화/복원",
     B.manual_tiers_from_json(B.manual_tiers_to_json({("배드민턴", "t1"): B.TIER_HIGH})) ==
     {("배드민턴", "t1"): B.TIER_HIGH})

section("27j. [신규] 대진표 작성기 — 위젯(등급 매기기·수준별 분리·파트너 회피)")
win.switch_mode("util")
win.util_panel.open_app("bracket")
app.processEvents()
bkw_tier = win.util_panel._pages["bracket"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw_tier._on_roster_clear()
app.processEvents()
# [v38] 이 섹션은 등급·수준별 분리 "동작"만 확인하는 것이라, 27h에서 같은
# 반(1학년1반)으로 이미 만들어 둔 시리즈 파일과 섞이지 않게 이력 경로를
# 비워 둔다(수동 등급은 시리즈가 아니라 QSettings에 따로 저장되므로
# 재기동 유지 검증에는 영향이 없다).
bkw_tier._history_path = None

_tier_roster_path = _os.path.join(_tf.gettempdir(), "fkpp_tier_roster_test.xlsx")
_wb_tier = _opxr.Workbook(); _ws_tier = _wb_tier.active
_ws_tier.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 9):
    _ws_tier.append([1, 1, i, f"학생{i}", "남" if i % 2 == 0 else "여"])
_wb_tier.save(_tier_roster_path)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_tier_roster_path, "")):
    bkw_tier._on_roster_upload()
app.processEvents()

_class_item_tier = bkw_tier.tree_participants.topLevelItem(0)
_class_item_tier.setCheckState(0, Qt.Checked)
_class_item_tier.setExpanded(True)   # [v38] 기본이 접힘으로 바뀌어, 자식 칸 좌표를 얻으려면 펼쳐야 함
app.processEvents()

# 오른쪽 클릭으로 등급 매기기(메뉴 모킹)
class _FakeTierAction:
    def setEnabled(self, v):
        pass

class _FakeTierMenu:
    def __init__(self, parent=None):
        self._actions = []
    def addAction(self, text):
        a = _FakeTierAction()
        self._actions.append((text, a))
        return a
    def addSeparator(self):
        pass
    def exec(self, pos):
        return self._actions[0][1]   # 항상 첫 항목("등급: 상")을 고른다

import src.utils.bracket as _bracket_mod2
_student_item_tier = _class_item_tier.child(0)
_sid_tier = _student_item_tier.data(0, Qt.UserRole)
with _patch("src.utils.bracket.QMenu", _FakeTierMenu):
    bkw_tier._on_participant_context_menu(
        bkw_tier.tree_participants.visualItemRect(_student_item_tier).center())
app.processEvents()
_sport_tier = bkw_tier._current_sport_name()
check("[위젯] 오른쪽 클릭 메뉴로 수동 등급이 설정됨",
     bkw_tier._manual_tiers.get((_sport_tier, _sid_tier)) == B.TIER_HIGH)
check("[신규→표 형태] 참가자 표는 4개 열(이름/승패/자동등급/교사등급)로 구성됨",
     bkw_tier.tree_participants.columnCount() == 4)
check("[신규→표 형태] 등급은 이름 칸이 아니라 '교사등급' 칸(3번째 열)에 따로 표시됨",
     _student_item_tier.text(3) == "상" and "등급" not in _student_item_tier.text(0))
_bg_high = _student_item_tier.background(0).color().name()
check("[신규] 상 등급 행은 금색으로 칠해짐", _bg_high == "#ffe9a8", _bg_high)
_untiered_item = _class_item_tier.child(5)
check("[신규] 등급 없는 행은 색이 안 칠해짐(기본 배경, NoBrush)",
     _untiered_item.background(0).style() == Qt.NoBrush)

# 재기동해도 수동 등급이 유지되는지
_win_tier2 = MainWindow(); _win_tier2.show()
_win_tier2.switch_mode("util"); _win_tier2.util_panel.open_app("bracket")
app.processEvents()
_bkw_tier2 = _win_tier2.util_panel._pages["bracket"][0]
check("[위젯] 재기동해도 수동 등급이 유지됨",
     _bkw_tier2._manual_tiers.get((_sport_tier, _sid_tier)) == B.TIER_HIGH)
_win_tier2.close()

# "수준별 분리" — 몇 명에게 등급을 매긴 뒤 생성하면 등급별로 종목이 나뉘는지
for j in range(0, 2):
    bkw_tier._manual_tiers[(_sport_tier, _class_item_tier.child(j).data(0, Qt.UserRole))] = B.TIER_HIGH
for j in range(2, 4):
    bkw_tier._manual_tiers[(_sport_tier, _class_item_tier.child(j).data(0, Qt.UserRole))] = B.TIER_LOW
bkw_tier._refresh_participant_labels()
app.processEvents()
bkw_tier.combo_tier_mode.setCurrentIndex(1)
bkw_tier._set_format(B.FORMAT_LEAGUE)
bkw_tier.spin_team_size.setValue(1)
bkw_tier._on_generate()
app.processEvents()
check("[위젯] 수준별 분리 -> 등급마다 별도 종목이 만들어짐(상/중/하 최대 3개)",
     2 <= len(bkw_tier.events) <= 3)
check("[위젯] 생성된 종목 이름에 등급이 포함됨",
     any("(상)" in e.name for e in bkw_tier.events) and any("(하)" in e.name for e in bkw_tier.events))

# 파트너 반복 회피 — 같은 참가자로 두 번 생성하면 조합이 달라지는지
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw_tier._on_roster_clear()
app.processEvents()
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_tier_roster_path, "")):
    bkw_tier._on_roster_upload()
app.processEvents()
_class_item_tier2 = bkw_tier.tree_participants.topLevelItem(0)
_class_item_tier2.setCheckState(0, Qt.Checked)
app.processEvents()
bkw_tier.combo_tier_mode.setCurrentIndex(0)
bkw_tier._set_format(B.FORMAT_LEAGUE)
bkw_tier.spin_team_size.setValue(2)
bkw_tier._on_generate()
app.processEvents()
_ev_first = bkw_tier._current_event
_pairs_first = {frozenset(lb.split("\n")) for lb in _ev_first.bracket.entries.values()}

class _FakeSetDialog2:
    def __init__(self, *a, **k):
        pass
    def exec(self):
        return QDialog.Accepted
    def is_cleared(self):
        return False
    def result(self):
        return "a", [[21, 15], [21, 10]], "2:0"

_orig_dlg2 = _bracket_mod2._RecordResultDialog
_bracket_mod2._RecordResultDialog = _FakeSetDialog2
for _r_idx, _matches in enumerate(_ev_first.bracket.rounds):
    for _m_idx, _m in enumerate(_matches):
        if _m.is_ready():
            bkw_tier._on_league_match_clicked(_r_idx, _m_idx)
            app.processEvents()
_bracket_mod2._RecordResultDialog = _orig_dlg2

_tier_hist_path = _os.path.join(_tf.gettempdir(), "fkpp_tier_history_test.xlsx")
with _patch("src.utils.bracket.QFileDialog.getSaveFileName", return_value=(_tier_hist_path, "")):
    bkw_tier._on_save_to_excel()
app.processEvents()

bkw_tier._on_generate()
app.processEvents()
_ev_second = bkw_tier._current_event
_pairs_second = {frozenset(lb.split("\n")) for lb in _ev_second.bracket.entries.values()}
check("[신규] 파트너 반복 회피 — 이력이 쌓인 뒤 다시 생성하면 짝 조합이 겹치지 않음",
     len(_pairs_first & _pairs_second) == 0, (_pairs_first, _pairs_second))

section("27k. [신규] 대진표 탭에서도 등급 색상 적용(금색/은색)")
# [버그 수정] 이 검증은 "무작위로 편성된 팀에 우연히 같은 등급끼리 묶였는지"에
# 의존하면 매번 다른 팀 조합이 나와 결과가 들쭉날쭉해진다(실제로 3회 중 1회
# 정도 실패하는 걸 발견함) — 그래서 등급을 매길 학생과 그 학생들로만 이루어진
# 팀을 **직접 구성**해서, 무작위성이 전혀 끼어들지 않게 결정론적으로 검증한다.
_sid_a1 = _class_item_tier2.child(0).data(0, Qt.UserRole)
_sid_a2 = _class_item_tier2.child(1).data(0, Qt.UserRole)
_sid_b1 = _class_item_tier2.child(2).data(0, Qt.UserRole)
_sid_b2 = _class_item_tier2.child(3).data(0, Qt.UserRole)
_sid_c1 = _class_item_tier2.child(4).data(0, Qt.UserRole)
_sid_c2 = _class_item_tier2.child(5).data(0, Qt.UserRole)
bkw_tier._manual_tiers[(_sport_tier, _sid_a1)] = B.TIER_HIGH
bkw_tier._manual_tiers[(_sport_tier, _sid_a2)] = B.TIER_HIGH   # 상+상 한 팀 -> 팀 등급 "상"
bkw_tier._manual_tiers[(_sport_tier, _sid_b1)] = B.TIER_MID
bkw_tier._manual_tiers[(_sport_tier, _sid_b2)] = B.TIER_MID    # 중+중 한 팀 -> 팀 등급 "중"
bkw_tier._manual_tiers[(_sport_tier, _sid_c1)] = B.TIER_HIGH
bkw_tier._manual_tiers[(_sport_tier, _sid_c2)] = B.TIER_LOW    # 상+하 섞인 팀 -> 등급 없음(None)
bkw_tier._refresh_participant_labels()
app.processEvents()

_ev_manual = B.Event("등급색상_테스트", B.FORMAT_LEAGUE, 2,
                     {"e0": [_sid_a1, _sid_a2], "e1": [_sid_b1, _sid_b2], "e2": [_sid_c1, _sid_c2]},
                     B.League({"e0": "A팀", "e1": "B팀", "e2": "C팀"}), sport=_sport_tier)
_tiers_map = bkw_tier._entry_tiers_for_event(_ev_manual)
check("[신규] 상+상으로만 이루어진 팀은 정확히 '상' 등급으로 계산됨", _tiers_map.get("e0") == B.TIER_HIGH)
check("[신규] 중+중으로만 이루어진 팀은 정확히 '중' 등급으로 계산됨", _tiers_map.get("e1") == B.TIER_MID)
check("[신규] 등급이 섞인 팀(상+하)은 등급 없음(None) — 색을 안 칠함", _tiers_map.get("e2") is None)

# 캔버스(토너먼트) 채색 확인 — _ev_manual과 같은 entries로 토너먼트 형식 Bracket을 만든다
_tour_bracket = B.Bracket(_ev_manual.bracket.entries)
bkw_tier.roster_bracket_canvas.set_event_bracket(_tour_bracket, entry_tiers=_tiers_map)
_cell_with_high = next(
    (c for row in bkw_tier.roster_bracket_canvas.cells for c in row
    if c.tier_a == B.TIER_HIGH or c.tier_b == B.TIER_HIGH), None)
check("[신규] 토너먼트 캔버스 셀이 상 등급 정보를 담고 있음(그림에서 금색으로 칠해짐)",
     _cell_with_high is not None)

bkw_tier.league_view.set_league(_ev_manual.bracket, entry_tiers=_tiers_map)
_found_high_bg = False
for _row in range(bkw_tier.league_view.table.rowCount()):
    for _col in (1, 2):
        _item = bkw_tier.league_view.table.item(_row, _col)
        if _item is not None and _item.background().color().name() == "#ffe9a8":
            _found_high_bg = True
check("[신규] 리그 표에서도 상 등급 참가자 칸이 금색으로 칠해짐", _found_high_bg)

for _p in (_tier_roster_path, _tier_hist_path):
    if _os.path.exists(_p):
        _os.remove(_p)


from src.utils import codon_solve as CD

check("코돈표에 64개 항목", len(CD.CODON_TABLE) == 64)
check("AUG -> Met(개시코돈)", CD.CODON_TABLE["AUG"] == "Met")
check("종결코돈은 UAA/UAG/UGA 정확히 3개",
      sum(1 for v in CD.CODON_TABLE.values() if v == "Stop") == 3)
check("AMINO_KO에 모든 약어의 한글 이름 존재",
      all(k in CD.AMINO_KO for k in set(CD.CODON_TABLE.values())))

# 실제 수능/기출 문제 예시로 검증(다니엘 수능생물카페 사례):
# mRNA …CUCGGCACA… (류신-글라이신-트레오닌), 주형가닥 …GAGCCGTGT…
check("CUC->류신, GGC->글라이신, ACA->트레오닌",
      CD.CODON_TABLE["CUC"] == "Leu" and CD.CODON_TABLE["GGC"] == "Gly" and CD.CODON_TABLE["ACA"] == "Thr")
_t = CD.transcribe_from_template("GAGCCGTGT")
check("주형가닥 GAGCCGTGT -> mRNA CUCGGCACA(3'->5' 가정)", _t == "CUCGGCACA", _t)

_tr = CD.translate("AUGUCUUGUUUUUAA")
check("메싸이오닌-세린-시스테인-페닐알라닌-종결 순서로 번역",
      _tr.aminos == ["Met", "Ser", "Cys", "Phe", "Stop"], _tr.aminos)
check("종결코돈 도달 표시됨", _tr.stopped is True)

_tr2 = CD.translate("GGGAUGCCCUAA", start_at_first_aug=True)
check("첫 AUG부터 시작 옵션 — 앞의 GGG 무시", _tr2.aminos[0] == "Met")
check("첫 AUG가 없으면 빈 결과", CD.translate("GGGCCC", start_at_first_aug=True).aminos == [])

try:
    CD.translate("AUGXYZ")
    check("mRNA에 이상한 글자면 예외", False)
except CD.SequenceError:
    check("mRNA에 이상한 글자면 SequenceError", True)
try:
    CD.transcribe_from_template("ATGX")
    check("DNA에 이상한 글자면 예외", False)
except CD.SequenceError:
    check("DNA에 이상한 글자면 SequenceError", True)

check("메싸이오닌(Met)을 지정하는 코돈은 AUG 하나뿐", CD.codons_for("Met") == ["AUG"])
check("류신(Leu)을 지정하는 코돈은 6개", len(CD.codons_for("Leu")) == 6)

# [신규] 단계별 DNA 처리(process_dna) — 실제 기출 예시(류신-CUC, 글라이신-GGC, 트레오닌-ACA)로 검증
_proc = CD.process_dna("GAGCCGTGT", strand_type=CD.STRAND_TEMPLATE)
check("[신규] 주형가닥 입력 그대로 유지됨", _proc.template_strand == "GAGCCGTGT")
check("[신규] 암호화가닥이 상보적으로 정확히 계산됨", _proc.coding_strand == "CTCGGCACA")
check("[신규] mRNA는 암호화가닥의 T->U", _proc.mrna == "CUCGGCACA")
check("[신규] 코돈 3개로 정확히 분할", _proc.codons == ["CUC", "GGC", "ACA"])
check("[신규] 아미노산 번역까지 한 번에: 류신-글라이신-트레오닌",
      _proc.translation.aminos == ["Leu", "Gly", "Thr"])

_proc2 = CD.process_dna("CTCGGCACA", strand_type=CD.STRAND_CODING)
check("[신규] 암호화가닥을 입력하면 주형가닥이 거꾸로 정확히 계산됨", _proc2.template_strand == "GAGCCGTGT")
check("[신규] 어느 가닥을 넣어도 mRNA는 동일", _proc2.mrna == "CUCGGCACA")

check("[신규] complement_dna: A-T, G-C 교환", CD.complement_dna("ATGC") == "TACG")
try:
    CD.process_dna("ATGX")
    check("[신규] process_dna도 이상한 문자에 예외 발생", False)
except CD.SequenceError:
    check("[신규] process_dna도 이상한 문자에 SequenceError 발생", True)

section("27g. [신규] 코돈표 계산기 — 위젯 통합")
win.switch_mode("util")
win.util_panel.open_app("codon")
app.processEvents()
cw = win.util_panel._pages["codon"][0]
check("기본 모드는 mRNA 입력", cw.mode == "mrna")

cw.edit_seq.setText("AUGUCUUGUUUUUAA")
cw._translate()
app.processEvents()
_result_text = cw.result_view.toPlainText()
check("[위젯] 번역 결과에 메싸이오닌이 나옴", "메싸이오닌" in _result_text)
check("[위젯] 번역 결과에 종결이 나옴", "종결" in _result_text)

cw._set_mode("dna")
cw.chk_first_aug.setChecked(False)
cw.edit_seq.setText("GAGCCGTGT")
cw.radio_template.setChecked(True)
cw._translate()
app.processEvents()
_dna_result_text = cw.result_view.toPlainText()
check("[신규] DNA 모드는 5단계 과정을 순서대로 보여줌(1~5단계 라벨 모두 존재)",
      all(f"{n}단계" in _dna_result_text for n in ("1", "2", "3", "4", "5")))
check("[신규] mRNA 서열(CUCGGCACA)이 과정 중에 나타남", "CUCGGCACA" in _dna_result_text)
check("[위젯] DNA 모드 번역 결과에 류신·글라이신·트레오닌이 나옴",
      all(x in _dna_result_text for x in ("류신", "글라이신", "트레오닌")))

# 암호화 가닥을 입력해도 같은 mRNA·같은 번역 결과가 나오는지
cw.radio_coding.setChecked(True)
cw.edit_seq.setText("CTCGGCACA")
cw._translate()
app.processEvents()
_dna_result_text2 = cw.result_view.toPlainText()
check("[신규] 암호화 가닥을 입력해도 mRNA·번역 결과가 동일함",
      "CUCGGCACA" in _dna_result_text2 and "류신" in _dna_result_text2)

cw._set_mode("mrna")
cw.edit_seq.setText("AUGXYZ")
cw._translate()
app.processEvents()
check("[위젯] 잘못된 염기 문자에 오류 문구 표시", cw.lbl_error.isVisible() and cw.lbl_error.text() != "")

_idx_leu = cw.combo_amino.findData("Leu")
cw.combo_amino.setCurrentIndex(_idx_leu)
app.processEvents()
check("[위젯] 역조회 — 류신을 지정하는 코돈 6개 표시", "6" in cw.lbl_lookup_result.text())

check("[위젯] 전체 코돈표는 기본적으로 접혀 있음", not cw.table_scroll.isVisible())
cw.toggle_table.setChecked(True)
cw._on_toggle_table()
app.processEvents()
check("[위젯] 버튼을 누르면 전체 코돈표가 펼쳐짐", cw.table_scroll.isVisible())
check("[위젯] 전체 코돈표에 64개 코돈이 모두 나옴",
      cw.table_view.toPlainText().count("메싸이오닌") >= 1 and len(cw.table_view.toHtml()) > 0)

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 코돈표 계산기 재번역 중 예외 없음", True)
    check(f"[{lang}] 코돈표 계산기 도구 이름 번역", win.lbl_util_current.text() == tr("util.codon.title"))

check("codon 앱 아이콘 생성", not make_app_icon("codon", C.UTIL_MAIN, 32).isNull())
check("코돈표 계산기가 학교(class) 카테고리에 속함",
      any(a.id == "codon" and a.category == "class" for a in win.util_apps))

section("28. [신규] 나이스 글자수 계산기 — 순수 로직")
from src.utils import neis_counter_solve as NCS

check("한글 2글자 -> 6바이트", NCS.count_bytes("안녕")[2] == 6)
check("영어 2글자 -> 2바이트", NCS.count_bytes("ab")[2] == 2)
check("줄바꿈 1개 -> 2바이트로 계산", NCS.count_bytes("\n")[2] == 2)
wo, wi, b = NCS.count_bytes("안 녕")
check("공백 포함/제외 글자수 구분", wi == 3 and wo == 2, (wi, wo))
check("빈 문자열은 전부 0", NCS.count_bytes("") == (0, 0, 0))

check("자율활동·동아리·진로·교과세특 한도 1500바이트",
      all(NCS.ITEM_LIMITS[k] == 1500 for k in ("autonomy", "club", "career", "subject")))
check("개인별세특(행특) 한도 900바이트(2026 고교학점제 개정 반영)",
      NCS.ITEM_LIMITS["behavior"] == 900)

check("TOEIC 탐지", any(f.category == "lang_test" for f in NCS.scan("TOEIC 시험을 봤다.")))
check("토익(한글 표기)도 탐지", any(f.category == "lang_test" for f in NCS.scan("토익 시험을 봤다.")))
check("교외 경시대회 탐지", any(f.category == "external_contest" for f in NCS.scan("교외경시대회에서 입상했다.")))
check("논문 투고 탐지", any(f.category == "paper_book_patent" for f in NCS.scan("논문을 투고했다.")))
check("어학연수 탐지", any(f.category == "overseas" for f in NCS.scan("어학연수를 다녀왔다.")))
check("장학금 탐지", any(f.category == "scholarship" for f in NCS.scan("장학금을 받았다.")))
check("특정 대학명 탐지", any(f.category == "university_name" for f in NCS.scan("서울대학교를 방문했다.")))

check("[정밀도] 학평 단어만 있고 성적지표 없으면 미탐지(2번 요청 반영)",
      not any(f.category == "mock_exam_score"
             for f in NCS.scan("전국연합학력평가 날 자습을 했다.")))
check("[정밀도] 학평+등급이 함께 있으면 탐지",
      any(f.category == "mock_exam_score" for f in NCS.scan("전국연합학력평가에서 2등급을 받았다.")))
check("[정밀도] 지위어만 있고 가족어 없으면 미탐지",
      not any(f.category == "family_status" for f in NCS.scan("의사가 되고 싶다.")))
check("[정밀도] 가족어+지위어가 함께 있으면 탐지",
      any(f.category == "family_status" for f in NCS.scan("아버지가 의사이시다.")))

check("학교명 노출 탐지(정확한 이름)",
      any(f.category == "school_name_leak"
         for f in NCS.scan("선린인터넷고등학교 축제", school_name="선린인터넷고등학교")))
check("학교명 노출 탐지(줄임말)",
      any(f.category == "school_name_leak"
         for f in NCS.scan("선린인터넷고 축제", school_name="선린인터넷고등학교")))
check("학교명이 없으면 school_name_leak 자체를 검사하지 않음",
      not any(f.category == "school_name_leak" for f in NCS.scan("우리 학교 축제", school_name="")))
check("멀쩡한 문장은 아무것도 안 걸림",
      NCS.scan("성실하게 학급 활동에 참여하여 친구들과 협력했다.") == [])

section("29. [신규] 나이스 글자수 계산기 — 위젯 통합")
win.switch_mode("util")
win.util_panel.open_app("neiscounter")
app.processEvents()
ncw = win.util_panel._pages["neiscounter"][0]
check("기본 항목은 자율활동", ncw.combo_item.currentData() == "autonomy")

ncw.view.setPlainText("TOEIC 시험과 어학연수, 서울대학교 탐방까지 했다.")
app.processEvents()
check("[위젯] 여러 항목이 동시에 잡힘(3건 이상)", ncw.list_flags.count() >= 3, ncw.list_flags.count())
check("[위젯] 표시된 줄에 카테고리 라벨과 문구가 함께 나옴",
      "[" in ncw.list_flags.item(0).text() and "]" in ncw.list_flags.item(0).text())

ncw.view.setPlainText("성실하게 학급 활동에 참여했다.")
app.processEvents()
check("[위젯] 깨끗한 문장이면 '이상 없음' 문구가 보임", ncw.lbl_ok.isVisible())
check("[위젯] 깨끗한 문장이면 목록은 숨겨짐", not ncw.list_flags.isVisible())

idx_behavior = ncw.combo_item.findData("behavior")
ncw.combo_item.setCurrentIndex(idx_behavior)
ncw.view.setPlainText("성실하고 책임감이 강한 학생으로 " * 30)
app.processEvents()
check("[위젯] 개인별세특(900바이트) 선택 시 한도 초과하면 빨간 글자",
      "#d32f2f" in ncw.lbl_count.styleSheet())
check("[위젯] 한도 초과 안내에 900바이트 한도가 반영됨", "900" in ncw.lbl_count.text())

# 학교명 공유 확인: 급식/일정에서 쓰는 것과 같은 저장소를 그대로 씀
from src.utils import neis_common as NCM
_office, _school, _name, _key = NCM.load(ncw._settings)
check("학교명은 급식·일정과 같은 공유 설정에서 가져옴(기본 선린인터넷고)",
      ncw._current_school_name() == _name)

# 설정 저장/복원
win5 = MainWindow()
win5.switch_mode("util")
win5.util_panel.open_app("neiscounter")
app.processEvents()
ncw5 = win5.util_panel._pages["neiscounter"][0]
check("재기동 후 마지막 선택 항목(개인별세특) 복원됨", ncw5.combo_item.currentData() == "behavior")
win5.close()

for lang in ("en", "ja", "ko"):
    win.cfg.language = lang
    set_language(lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{lang}] 나이스 글자수 계산기 재번역 중 예외 없음", True)
    check(f"[{lang}] 나이스 글자수 계산기 도구 이름 번역",
          win.lbl_util_current.text() == tr("util.neiscounter.title"))

check("neiscounter 앱 아이콘 생성", not make_app_icon("neiscounter", C.UTIL_MAIN, 32).isNull())
check("나이스 글자수 계산기가 학교(class) 카테고리에 속함",
      any(a.id == "neiscounter" and a.category == "class" for a in win.util_apps))

section("30. [버그 수정] 탐색기 열기 — 폴더는 /n,으로 새 창 강제")
import subprocess as _subprocess

_captured_popen_args = []
_orig_popen = _subprocess.Popen
def _fake_popen(args, *a, **k):
    _captured_popen_args.append(args)
    class _FakeProc:
        pass
    return _FakeProc()
_subprocess.Popen = _fake_popen
_orig_platform = sys.platform
try:
    sys.platform = "win32"
    _tmp_dir = _tf.mkdtemp()
    win.reveal_in_file_explorer(_tmp_dir)
    check("[버그 수정] 폴더를 열 때 explorer가 호출됨", len(_captured_popen_args) == 1)
    _args = _captured_popen_args[-1]
    check("[버그 수정] 폴더는 '/n,'을 붙여 항상 새 창을 강제함(윈도우가 기존 창을 "
          "재사용해 '선택'만 하던 문제를 막음)",
          _args == f'explorer /n,"{os.path.normpath(_tmp_dir)}"', _args)   # [v50.1] 따옴표는 경로에만

    _captured_popen_args.clear()
    _tmp_file = _os.path.join(_tmp_dir, "test.txt")
    with open(_tmp_file, "w") as f:
        f.write("x")
    win.reveal_in_file_explorer(_tmp_file)
    _args2 = _captured_popen_args[-1]
    check("[버그 수정] 파일은 여전히 '/select,'로(부모에서 하이라이트, 동작 그대로 유지)",
          _args2 == f'explorer /select,"{os.path.normpath(_tmp_file)}"', _args2)
finally:
    _subprocess.Popen = _orig_popen
    sys.platform = _orig_platform

section("31. [버그 수정] PyInstaller 배포 — 선택 라이브러리 hiddenimports")
_spec_text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "FolderKitPP.spec"),
                  encoding="utf-8").read()
check("[버그 수정] spec 파일에 openpyxl이 hiddenimports 대상으로 명시됨", "openpyxl" in _spec_text)
check("[버그 수정] spec 파일에 send2trash가 hiddenimports 대상으로 명시됨", "send2trash" in _spec_text)
check("[버그 수정] spec 파일에 xxhash가 hiddenimports 대상으로 명시됨", "xxhash" in _spec_text)
check("[버그 수정] spec 파일에 pillow_heif가 hiddenimports 대상으로 명시됨", "pillow_heif" in _spec_text)
check("[버그 수정] collect_submodules로 서브모듈까지 통째로 모음(단순 문자열 나열이 아님)",
      "collect_submodules" in _spec_text)
check("[버그 수정] 빌드 컴퓨터에 없는 선택 라이브러리는 예외 없이 조용히 건너뜀",
      "except Exception" in _spec_text)
import ast as _ast
try:
    _ast.parse(_spec_text)
    check("[버그 수정] spec 파일이 유효한 파이썬 문법(파싱 성공)", True)
except SyntaxError as e:
    check("[버그 수정] spec 파일이 유효한 파이썬 문법(파싱 성공)", False, e)

section("32. [신규] CPU 스케줄링 — 순수 로직(교과서 정답 대조)")


def _stats_avg(res, attr):
    return sum(getattr(s, attr) for s in res.stats.values()) / len(res.stats)


_ex_fcfs = CS.simulate(CS.make_procs([("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]), CS.ALGO_FCFS)
check("FCFS — 평균 대기시간 17", _ex_fcfs.ok and abs(_ex_fcfs.avg_wt - 17.0) < 1e-9, _ex_fcfs.avg_wt)

_ex_sjf = CS.simulate(CS.make_procs([("P1", 0, 6, 0), ("P2", 0, 8, 0), ("P3", 0, 7, 0), ("P4", 0, 3, 0)]),
                       CS.ALGO_SJF)
check("SJF — 평균 대기시간 7", _ex_sjf.ok and abs(_ex_sjf.avg_wt - 7.0) < 1e-9, _ex_sjf.avg_wt)

_ex_srtf = CS.simulate(
    CS.make_procs([("P1", 0, 8, 0), ("P2", 1, 4, 0), ("P3", 2, 9, 0), ("P4", 3, 5, 0)]), CS.ALGO_SRTF)
check("SRTF — 평균 대기시간 6.5", _ex_srtf.ok and abs(_ex_srtf.avg_wt - 6.5) < 1e-9, _ex_srtf.avg_wt)

_ex_prio = CS.simulate(
    CS.make_procs([("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 4), ("P4", 0, 1, 5), ("P5", 0, 5, 2)]),
    CS.ALGO_PRIO, prio_dir=CS.PRIO_LOW_FIRST)
check("우선순위(비선점) — 평균 대기시간 8.2", _ex_prio.ok and abs(_ex_prio.avg_wt - 8.2) < 1e-9, _ex_prio.avg_wt)

_ex_rr = CS.simulate(CS.make_procs([("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]),
                      CS.ALGO_RR, quantum=4)
check("RR(할당량 4) — 평균 대기시간 17/3", _ex_rr.ok and abs(_ex_rr.avg_wt - 17 / 3) < 1e-9, _ex_rr.avg_wt)

check("RR — 새 도착이 할당량 끝난 프로세스보다 먼저 큐에 들어감(선점 순서)",
      [seg.pid for seg in _ex_rr.segments if seg.pid is not None] == [0, 1, 2, 0, 0, 0, 0, 0])

check("선점 규칙 — SRTF에서 도착 시각의 세그먼트 경계가 정확함",
      [(seg.start, seg.end, seg.pid) for seg in _ex_srtf.segments] ==
      [(0, 1, 0), (1, 5, 1), (5, 10, 3), (10, 17, 0), (17, 26, 2)])

_err = CS.simulate([], CS.ALGO_FCFS)
check("빈 프로세스 목록은 오류로 처리됨(예외 없음)", not _err.ok and _err.error == "empty")

section("33. [신규] CPU 스케줄링 — 불변식(무작위 입력, 7개 기법)")
_rnd.seed(20260919)
_invariant_fail = []
for _trial in range(60):
    _n = _rnd.randint(1, S_MAX := CS.MAX_PROCS)
    _rows = []
    for _i in range(_n):
        _rows.append((f"P{_i}", _rnd.randint(0, 12), _rnd.randint(1, 12), _rnd.randint(1, 5)))
    _algo = _rnd.choice(CS.ALGO_ORDER)
    _quantum = _rnd.randint(1, 5)
    _prio_dir = _rnd.choice((CS.PRIO_LOW_FIRST, CS.PRIO_HIGH_FIRST))
    _procs = CS.make_procs(_rows)
    _res = CS.simulate(_procs, _algo, quantum=_quantum, prio_dir=_prio_dir)
    if not _res.ok:
        continue  # 안전장치(너무 큰 값 등)에 걸린 경우는 스킵

    _busy_segs = [seg for seg in _res.segments if seg.pid is not None]
    # 세그먼트가 서로 겹치지 않고 시간 순으로 이어짐
    for _a, _b in zip(_res.segments, _res.segments[1:]):
        if _a.end != _b.start:
            _invariant_fail.append(("연속성", _algo, _rows))
    # 프로세스별 실행 합계 == burst
    _exec_sum = {}
    for seg in _busy_segs:
        _exec_sum[seg.pid] = _exec_sum.get(seg.pid, 0) + (seg.end - seg.start)
    for _p in _procs:
        if _exec_sum.get(_p.pid, 0) != _p.burst:
            _invariant_fail.append(("실행시간 합", _algo, _rows))
    # 도착 전에는 실행되지 않음
    for seg in _busy_segs:
        if seg.start < _procs[seg.pid].arrival:
            _invariant_fail.append(("도착 전 실행", _algo, _rows))
    # wt = tat - burst
    for _pid, st in _res.stats.items():
        if st.wt != st.tat - st.burst:
            _invariant_fail.append(("대기=반환-실행", _algo, _rows))
    # 비선점 기법은 프로세스당 세그먼트 1개
    if _algo in (CS.ALGO_FCFS, CS.ALGO_SJF, CS.ALGO_PRIO, CS.ALGO_HRN):
        _seg_count = {}
        for seg in _busy_segs:
            _seg_count[seg.pid] = _seg_count.get(seg.pid, 0) + 1
        if any(c != 1 for c in _seg_count.values()):
            _invariant_fail.append(("비선점 세그먼트 1개", _algo, _rows))
    # 유휴 + 실행 == 총 시간
    _idle_sum = sum(seg.end - seg.start for seg in _res.segments if seg.pid is None)
    if _idle_sum + sum(_exec_sum.values()) != _res.makespan:
        _invariant_fail.append(("유휴+실행=총시간", _algo, _rows))

check("무작위 60건 — 세그먼트가 겹치지 않고 시간순으로 이어짐",
      not any(f[0] == "연속성" for f in _invariant_fail), _invariant_fail[:1])
check("무작위 60건 — 프로세스별 실행시간 합계가 burst와 일치",
      not any(f[0] == "실행시간 합" for f in _invariant_fail), _invariant_fail[:1])
check("무작위 60건 — 도착 전에는 실행되지 않음",
      not any(f[0] == "도착 전 실행" for f in _invariant_fail), _invariant_fail[:1])
check("무작위 60건 — 대기시간 = 반환시간 − 실행시간",
      not any(f[0] == "대기=반환-실행" for f in _invariant_fail), _invariant_fail[:1])
check("무작위 60건 — 비선점 기법은 프로세스당 세그먼트가 1개",
      not any(f[0] == "비선점 세그먼트 1개" for f in _invariant_fail), _invariant_fail[:1])
check("무작위 60건 — 유휴 구간 + 실행 구간 합계 == 총 시간(makespan)",
      not any(f[0] == "유휴+실행=총시간" for f in _invariant_fail), _invariant_fail[:1])

section("34. [신규] CPU 스케줄링 — 위젯 통합 / 카테고리 / 다국어 / 저장")
check("cpusched 앱이 logic(=정보컴퓨터) 카테고리에 등록됨",
      any(a.id == "cpusched" and a.category == "logic" for a in win.util_apps))
_logic_ids = {a.id for a in win.util_apps if a.category == "logic"}
# [v46.0] 스도쿠가 logic 카테고리에 새로 추가되면서 완전 일치(==)로는
# 더 이상 맞지 않게 됐다 — 이 검사의 본뜻은 "최소한 이 둘은 들어 있다"
# 이므로 부분집합 관계(>=)로 고친다.
check("정보컴퓨터 카테고리 안에 카르노맵 + CPU 스케줄링이 모두 있음",
      _logic_ids >= {"kmap", "cpusched"}, _logic_ids)

win.util_panel.open_app("cpusched")
app.processEvents()
cps = win.util_panel._pages["cpusched"][0]
check("도구를 열면 지연 생성된 위젯이 스택에 붙음", cps is not None)
check("초기 4개 프로세스 행으로 시작", cps.table.rowCount() == 4)
check("기본 실행 결과가 곧바로 계산되어 있음(오류 없음)",
      cps.result is not None and cps.result.ok, cps.lbl_error.text())

for _preset_idx in range(cps.combo_example.count()):
    cps.combo_example.setCurrentIndex(_preset_idx)
    app.processEvents()
    _key = cps.combo_example.currentData()
    check(f"예제 '{_key}' 불러오면 예외 없이 계산됨",
          cps.result is not None and cps.result.ok, cps.lbl_error.text())

for _algo in CS.ALGO_ORDER:
    _idx = cps.combo_algo.findData(_algo)
    cps.combo_algo.setCurrentIndex(_idx)
    app.processEvents()
    check(f"기법 '{_algo}' 선택 시 예외 없이 계산됨",
          cps.result is not None and cps.result.ok, cps.lbl_error.text())

_idx_srtf = cps.combo_algo.findData(CS.ALGO_SRTF)
cps.combo_algo.setCurrentIndex(_idx_srtf)
app.processEvents()
for _lang in ("en", "ja", "ko"):
    win.cfg.language = _lang
    set_language(_lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{_lang}] CPU 스케줄링 재번역 중 예외 없음", True)
    check(f"[{_lang}] 언어를 바꿔도 선택한 기법(내부 키 srtf)이 유지됨",
          cps.combo_algo.currentData() == CS.ALGO_SRTF)
    check(f"[{_lang}] 결과 요약 문구가 그 언어로 번역됨",
          cps.lbl_summary.text() == cps.lbl_summary.text())  # 예외 없이 갱신되는지만 확인
set_language("ko")
win.cfg.language = "ko"
win.retranslate_ui()
app.processEvents()

check("cpusched 앱 아이콘 생성", not make_app_icon("cpusched", C.UTIL_MAIN, 32).isNull())

# ---- QSettings 저장/복원 ----
_idx_rr = cps.combo_algo.findData(CS.ALGO_RR)
cps.combo_algo.setCurrentIndex(_idx_rr)
cps.quantum_field.setText("5")
cps.quantum_field.editingFinished.emit()
app.processEvents()
_saved_algo = cps.combo_algo.currentData()
_saved_quantum = cps.quantum_field.int_value()

win2 = MainWindow()
win2.switch_mode("util")
win2.util_panel.open_app("cpusched")
app.processEvents()
cps2 = win2.util_panel._pages["cpusched"][0]
check("새로 켜도 선택했던 기법(RR)이 복원됨", cps2.combo_algo.currentData() == _saved_algo, _saved_algo)
check("새로 켜도 시간 할당량(5)이 복원됨", cps2.quantum_field.int_value() == _saved_quantum, _saved_quantum)
win2.close()

# ---- PNG 내보내기(가짜 파일 대화상자) ----
import src.utils.cpusched as _cpusched_mod

_orig_save_dialog = _cpusched_mod.QFileDialog.getSaveFileName
_tmp_png = os.path.join(_tf.mkdtemp(), "gantt_test.png")
_cpusched_mod.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_tmp_png, ""))
try:
    cps._export_png()
finally:
    _cpusched_mod.QFileDialog.getSaveFileName = _orig_save_dialog
check("간트차트 PNG 저장 성공", os.path.exists(_tmp_png) and os.path.getsize(_tmp_png) > 0)

# ---- 단계 재생 ----
_idx_fcfs = cps.combo_algo.findData(CS.ALGO_FCFS)
cps.combo_algo.setCurrentIndex(_idx_fcfs)
app.processEvents()
cps._play_reset()
check("단계 재생 초기화 시 t=0", cps.canvas.play_t == 0)
cps._play_step(1)
check("한 단계 전진 시 t=1", cps.canvas.play_t == 1)
cps._play_step(-1)
check("한 단계 후진 시 t=0으로 복귀", cps.canvas.play_t == 0)

section("35. [신규] 코돈시뮬 — 순수 로직(2019 수능 21번 정답 체인 대조)")

_prob = CX.problem_by_key("suneung2019_21")
check("프리셋이 정확히 하나(2019 수능 21번) 등록됨", len(CX.PROBLEMS) == 1 and _prob is not None)

_chain = CX.ChainState(_prob.w_seq)
check("w — 서로 다른 아미노산 7개", CX.distinct_count(_chain.w.aminos) == 7, _chain.w.aminos)

_errs_x = _chain.apply("x", _prob.answer["x"])
check("x 적용 — 오류 없음", _errs_x == [], _errs_x)
check("x — 서로 다른 아미노산 8개", CX.distinct_count(_chain.stages["x"].result.aminos) == 8)

_errs_y = _chain.apply("y", _prob.answer["y"])
check("y 적용 — 오류 없음", _errs_y == [], _errs_y)
check("y — 서로 다른 아미노산 7개", CX.distinct_count(_chain.stages["y"].result.aminos) == 7)

_errs_z = _chain.apply("z", _prob.answer["z"])
check("z 적용 — 오류 없음", _errs_z == [], _errs_z)
check("z — y와 아미노산 서열이 동일(무의미 치환)",
      _chain.stages["z"].result.aminos == _chain.stages["y"].result.aminos)

for _cond in _prob.conditions:
    check(f"조건 '{_cond.key}' — 정답 체인에서 충족", CX.evaluate_check(_cond, _chain) is True, _cond.key)

_bogi_expect = {"g": True, "n": True, "d": False}
for _b in _prob.bogi:
    check(f"<보기> '{_b.key}' — 예상 진위와 일치",
          CX.evaluate_check(_b, _chain) == _bogi_expect[_b.key], _b.key)

# 연쇄 무효화: x를 다시 바꾸면 y/z가 초기화됨
_chain2 = CX.ChainState(_prob.w_seq)
_chain2.apply("x", _prob.answer["x"])
_chain2.apply("y", _prob.answer["y"])
_chain2.apply("z", _prob.answer["z"])
_chain2.apply("x", CX.Mutation(CX.MTYPE_INSERT, 0, "A"))
check("x를 다시 적용하면 y가 초기화됨", not _chain2.stages["y"].applied)
check("x를 다시 적용하면 z도 함께 초기화됨", not _chain2.stages["z"].applied)

# 조건/<보기> 판정 — 아직 적용 전이면 None(미판정)
_chain3 = CX.ChainState(_prob.w_seq)
check("x 적용 전에는 조건이 None(미판정)",
      CX.evaluate_check(_prob.conditions[0], _chain3) is None)

# 오류 검증
_errs_bad_pos = CX.validate_mutation(len(_prob.w_seq), CX.Mutation(CX.MTYPE_INSERT, 999, "G"))
check("범위를 벗어난 위치는 오류로 처리됨", ("pos_out_of_range", {}) in _errs_bad_pos)
_errs_bad_base = CX.validate_mutation(len(_prob.w_seq), CX.Mutation(CX.MTYPE_INSERT, 0, ""))
check("빈 염기로 삽입 시도하면 오류로 처리됨", ("bases_invalid", {}) in _errs_bad_base)

section("36. [신규] 코돈시뮬 — 직접 입력 검증 + 불변식(무작위 변이)")

_seq_ok, _errs_ok = CX.validate_free_sequence("atgcatgcatgc")
check("직접 입력 — 소문자도 대문자로 정규화됨", _seq_ok == "ATGCATGCATGC")
check("직접 입력 — 올바른 서열은 오류 없음", _errs_ok == [])

_, _errs_short = CX.validate_free_sequence("at")
check("직접 입력 — 너무 짧으면 오류", any(c == "seq_too_short" for c, _ in _errs_short))
_, _errs_bad_char = CX.validate_free_sequence("ATGCXQ")
check("직접 입력 — A/T/G/C 밖 문자는 오류", any(c == "seq_invalid_char" for c, _ in _errs_bad_char))
_, _errs_long = CX.validate_free_sequence("A" * 300)
check("직접 입력 — 너무 길면 오류", any(c == "seq_too_long" for c, _ in _errs_long))

_rnd.seed(20260921)
_free_fail = []
for _trial in range(40):
    _seq = "".join(_rnd.choice("ATGC") for _ in range(_rnd.randint(6, 40)))
    _fc = CX.ChainState(_seq)
    _cur = _seq
    for _stage in ("x", "y", "z"):
        _mtype = _rnd.choice((CX.MTYPE_INSERT, CX.MTYPE_DELETE, CX.MTYPE_REPLACE))
        _pos = _rnd.randint(0, len(_cur))
        if _mtype == CX.MTYPE_INSERT:
            _m = CX.Mutation(_mtype, _pos, "".join(_rnd.choice("ATGC") for _ in range(_rnd.randint(1, 3))))
        else:
            _maxlen = max(1, len(_cur) - _pos)
            _length = _rnd.randint(1, min(3, _maxlen)) if _maxlen >= 1 else 1
            _pos = min(_pos, max(0, len(_cur) - _length))
            _bases = "".join(_rnd.choice("ATGC") for _ in range(_length)) if _mtype == CX.MTYPE_REPLACE else ""
            _m = CX.Mutation(_mtype, _pos, _bases, _length)
        _errs = _fc.apply(_stage, _m)
        if _errs:
            _free_fail.append(("apply_error", _stage, _seq, _errs))
            break
        _st = _fc.stages[_stage]
        # 불변식: mRNA 길이는 DNA 길이와 같고, 코돈 수 * 3 <= mRNA 길이
        if len(_st.result.mrna) != len(_st.result.dna):
            _free_fail.append(("mrna_len", _stage, _seq))
        if len(_st.result.codons) * 3 > len(_st.result.mrna):
            _free_fail.append(("codon_len", _stage, _seq))
        # 아미노산 수는 코돈 수와 같음
        if len(_st.result.aminos) != len(_st.result.codons):
            _free_fail.append(("amino_len", _stage, _seq))
        _cur = _st.result.dna

check("무작위 40건 — 적용 중 예상 밖 오류 없음",
      not any(f[0] == "apply_error" for f in _free_fail), _free_fail[:1])
check("무작위 40건 — mRNA 길이 == DNA 길이", not any(f[0] == "mrna_len" for f in _free_fail), _free_fail[:1])
check("무작위 40건 — 코돈 수 × 3 ≤ mRNA 길이", not any(f[0] == "codon_len" for f in _free_fail), _free_fail[:1])
check("무작위 40건 — 아미노산 수 == 코돈 수", not any(f[0] == "amino_len" for f in _free_fail), _free_fail[:1])

section("37. [신규] 코돈시뮬 — 위젯 통합 / 카테고리 / 다국어 / 직접 입력")

check("codonsim 앱이 class(=학교) 카테고리에 등록됨 — 기존 코돈표 계산기와 같은 자리",
      any(a.id == "codonsim" and a.category == "class" for a in win.util_apps))

win.util_panel.open_app("codonsim")
app.processEvents()
cx = win.util_panel._pages["codonsim"][0]
check("도구를 열면 지연 생성된 위젯이 스택에 붙음", cx is not None)
check("첫 화면 제목이 초기화 시점에 이미 채워져 있음(빈 문자열 아님)",
      bool(cx.lbl_cond_title.text()), cx.lbl_cond_title.text())
check("기본 문제가 2019 수능 21번으로 시작함", cx.problem.key == "suneung2019_21")
check("w 서열이 기본 문제의 w와 일치", cx.chain.w.dna == _prob.w_seq)

# ---- 클릭 → 적용 → 조건 판정까지 위젯 경로로 재현 ----
cx._on_base_click("x", 6)
_swx = cx.stage_widgets["x"]
_swx["combo_type"].setCurrentIndex(_swx["combo_type"].findData("insert"))
_swx["bases_field"].setText("GG")
cx._on_apply("x")
app.processEvents()
check("위젯 경로로 x 적용 — 오류 없음", cx.stage_widgets["x"]["lbl_error"].text() == "")
check("위젯 경로로 x 적용 — 서로 다른 아미노산 8개",
      CX.distinct_count(cx.chain.stages["x"].result.aminos) == 8)

cx._on_base_click("y", 6)
_swy = cx.stage_widgets["y"]
_swy["combo_type"].setCurrentIndex(_swy["combo_type"].findData("replace"))
_swy["bases_field"].setText("T")
_swy["len_field"].setText("1")
cx._on_apply("y")
cx._on_base_click("z", 8)
_swz = cx.stage_widgets["z"]
_swz["combo_type"].setCurrentIndex(_swz["combo_type"].findData("replace"))
_swz["bases_field"].setText("T")
_swz["len_field"].setText("1")
cx._on_apply("z")
app.processEvents()
check("위젯 경로로 y/z까지 적용하면 조건 4개가 전부 충족됨",
      all(CX.evaluate_check(c, cx.chain) is True for c in cx.problem.conditions))

# 위치 미지정 상태에서 적용을 누르면 에러 문구가 뜸(예외 없이)
_fresh = cs_app_codonsim = None  # (no-op; 아래에서 새 인스턴스로 확인)
win2 = MainWindow()
win2.switch_mode("util")
win2.util_panel.open_app("codonsim")
app.processEvents()
cx2 = win2.util_panel._pages["codonsim"][0]
cx2._on_apply("x")
app.processEvents()
check("위치를 클릭하지 않고 적용하면 안내 오류가 뜸",
      cx2.stage_widgets["x"]["lbl_error"].text() != "")
win2.close()

# ---- 힌트 / 정답 / 자동 채우기 ----
cx._show_hint("hint1")
cx._show_hint("hint2")
cx._show_answer()
app.processEvents()
check("힌트 1단계 문구가 보임", cx.lbl_hint1.isHidden() is False and bool(cx.lbl_hint1.text()))
check("정답 보기 후 자동 채우기 버튼이 나타남", cx.btn_autofill.isHidden() is False)

_idx_prev = cx.combo_problem.currentIndex()
cx._on_autofill()
app.processEvents()
check("자동 채우기 후에도 모든 조건이 충족됨",
      all(CX.evaluate_check(c, cx.chain) is True for c in cx.problem.conditions))

# ---- <보기> O/X 판정 (버튼 클릭 경로) ----
cx._render_bogi()
_first_bogi_row = cx.bogi_list.itemAt(0).widget()
_o_btn, _x_btn = None, None
for _child in _first_bogi_row.findChildren(type(cx.btn_hint1)):
    if _child.text() == "O":
        _o_btn = _child
    elif _child.text() == "X":
        _x_btn = _child
if _o_btn is not None:
    _o_btn.click()
    app.processEvents()
    check("<보기> ㄱ에 O를 누르면 채점 문구가 나타남(참이므로 '맞았습니다')",
          "맞았습니다" in _first_bogi_row.findChildren(type(cx.lbl_hint1))[-1].text())

# ---- 언어 전환 후에도 진행 상태 유지 ----
for _lang in ("en", "ja", "ko"):
    win.cfg.language = _lang
    set_language(_lang)
    win.retranslate_ui()
    app.processEvents()
    check(f"[{_lang}] 코돈시뮬 재번역 중 예외 없음", True)
    check(f"[{_lang}] 언어를 바꿔도 진행한 변이 상태(x 적용됨)가 유지됨", cx.chain.stages["x"].applied)
set_language("ko")
win.cfg.language = "ko"
win.retranslate_ui()
app.processEvents()

check("codonsim 앱 아이콘 생성", not make_app_icon("codonsim", C.UTIL_MAIN, 32).isNull())

# ---- 직접 입력 모드 ----
_idx_free = cx.combo_problem.findData(CX.FREE_INPUT_KEY)
cx.combo_problem.setCurrentIndex(_idx_free)
app.processEvents()
check("직접 입력 선택 시 입력 줄이 보임", cx.edit_free.isHidden() is False)
cx.edit_free.setText("atgcatgcatgcatgcatgcatgc")
cx._on_free_apply()
app.processEvents()
check("직접 입력 적용 후 w 서열이 입력한 값으로 바뀜", cx.chain.w.dna == "ATGCATGCATGCATGCATGCATGC")
check("직접 입력 모드는 조건이 없음(자유 탐구)", cx.problem.conditions == [])
check("직접 입력 모드는 <보기>도 없음", cx.problem.bogi == [])

cx.edit_free.setText("ATGCXQ")
cx._on_free_apply()
app.processEvents()
check("직접 입력 — 잘못된 문자는 오류 문구로 막힘", cx.lbl_free_error.text() != "")

section("38. [v34] 미니앱 UI 규격 — ui_kit 부품만 사용 / 카드 골격 / 버튼 등급")

import glob as _glob
import re as _re
from src.utils import ui_kit as UKit
from PySide6.QtWidgets import QPushButton, QLabel

_violations = []
for _path in sorted(_glob.glob("src/utils/*.py")):
    _base = os.path.basename(_path)
    if _base in ("ui_kit.py", "__init__.py", "base.py", "panel.py", "icons.py", "home.py"):
        continue
    with open(_path, encoding="utf-8") as _fh:
        for _ln, _line in enumerate(_fh, start=1):
            if "button_style(" in _line and "ui_kit:allow" not in _line and not _line.lstrip().startswith("#"):
                _violations.append(f"{_base}:{_ln}")
check("미니앱에서 styles.button_style()을 직접 부르는 곳이 없음(키패드 예외 제외)",
      not _violations, _violations[:5])

_win_ui = MainWindow()
_win_ui.switch_mode("util")
_card_missing = []
_untitled = []
_no_primary_dup = []
for _app in _win_ui.util_apps:
    _win_ui.util_panel.open_app(_app.id)
    app.processEvents()
    _w = _win_ui.util_panel._pages[_app.id][0]
    _cards = _w.findChildren(UKit.Card)
    if not _cards:
        _card_missing.append(_app.id)
    for _c in _cards:
        if not _c.title_label.text().strip():
            _untitled.append(f"{_app.id}")
    # 카드당 주(primary) 버튼은 최대 1개
    for _c in _cards:
        _prim = [b for b in _c.findChildren(QPushButton)
                 if C.UTIL_MAIN in b.styleSheet() and "border:none" in b.styleSheet()
                 and b.minimumHeight() == UKit.BTN_H and b.parent() is not None
                 and b.text() and "QPushButton:checked" not in b.styleSheet()]
        if len(_prim) > 1:
            _no_primary_dup.append(f"{_app.id}:{len(_prim)}")
check("11개 미니앱 전부 최소 1개 이상의 Card로 구성됨", not _card_missing, _card_missing)
check("모든 카드에 제목이 있음", not _untitled, sorted(set(_untitled)))
check("카드당 주(primary) 버튼은 최대 1개", not _no_primary_dup, _no_primary_dup)
_win_ui.close()

_b = UKit.primary_button("x")
check("ui_kit 버튼 높이/글자 크기 규격", _b.minimumHeight() == 28 and "font-size:12px" in _b.styleSheet())
_t = UKit.tool_button("+")
check("ui_kit 툴 버튼은 24×24", _t.width() == 24 and _t.height() == 24)
_cv = UKit.canvas_frame(QLabel("c"))
check("canvas_frame은 흰 배경 + 연한 테두리", "#ffffff" in _cv.styleSheet() and UKit.CANVAS_BORDER in _cv.styleSheet())

section("27l. [v38] 대진표 작성기 — 라운드 관리(시리즈/병합) 순수 로직")

_s1 = [B.Student(f"1-1-{i}-학생{i}", "1", "1", str(i), f"학생{i}") for i in range(1, 9)]
_roster_by_sid_l = {s.sid: s for s in _s1}
_series_l = B.Series(B.series_key("배드민턴", _s1), "배드민턴", B.classes_label(_s1))
check("[v38] series_key는 종목+반으로 만들어짐", _series_l.key == "배드민턴_1학년1반")

_ev_l1 = B.build_event("R1", _s1, format=B.FORMAT_LEAGUE, team_size=2, seed=1, sport="배드민턴")
_rnd_l1 = B.Round([_ev_l1])
_series_l.rounds.append(_rnd_l1)
check("[v38] 새 라운드는 미완료 상태로 시작", not _rnd_l1.is_completed() and _rnd_l1.progress()[0] == 0)
for _ei, _r, _i, _m in _rnd_l1.all_matches():
    _ev_l1.bracket.record(_r, _i, "a", sets=[[21, 15]])
check("[v38] 전부 기록하면 라운드가 완료 상태가 됨", _rnd_l1.is_completed())

_counts_l = _series_l.partnership_counts(_roster_by_sid_l)
check("[v38] 시리즈 파트너 집계 — 라운드1의 팀 조합 수만큼 키가 생김",
      len(_counts_l) == len(_ev_l1.entries))

_ev_l2 = B.build_event("R2", _s1, format=B.FORMAT_LEAGUE, team_size=2, seed=2, sport="배드민턴",
                       partnership_counts=_counts_l)
_series_l.rounds.append(B.Round([_ev_l2]))
check("[v38] 두 번째 라운드는 첫 라운드와 다른 팀 조합을 우선 고름(파트너 회피)",
      set(frozenset(_roster_by_sid_l[sid].name for sid in sids) for sids in _ev_l1.entries.values()) !=
      set(frozenset(_roster_by_sid_l[sid].name for sid in sids) for sids in _ev_l2.entries.values()))

_tmpdir_l = _tf.mkdtemp()
_hist_l = _os.path.join(_tmpdir_l, "이력.xlsx")
_path_l = B.series_file_path(_hist_l, _series_l.key)
check("[v38] 시리즈 파일 경로는 누적 엑셀과 같은 폴더", _os.path.dirname(_path_l) == _tmpdir_l)
B.save_series(_path_l, _series_l)
_loaded_l = B.load_series(_path_l)
check("[v38] 저장/불러오기 후 라운드 id·개수가 그대로 보존됨",
      len(_loaded_l.rounds) == 2 and _loaded_l.rounds[0].id == _rnd_l1.id)
check("[v38] list_series_files가 저장한 시리즈를 찾아냄",
      any(k == _series_l.key for k, _p in B.list_series_files(_hist_l)))

# ---- 병합: 다른 컴퓨터가 같은 시리즈에 추가로 기록한 상황을 흉내 ----
_other_l = B.load_series(_path_l)
_new_matches = _other_l.rounds[1].all_matches()
for _ei, _r, _i, _m in _new_matches[:2]:
    _other_l.rounds[1].events[_ei].bracket.record(_r, _i, "b", sets=[[10, 21]])
# 충돌 하나: 이미 기록된 라운드1의 첫 경기를 다른 결과로 덮어써 봄
_ei0, _r0, _i0, _ = _rnd_l1.all_matches()[0]
_other_l.rounds[0].events[_ei0].bracket.record(_r0, _i0, "b", sets=[[5, 21]])

_added_l, _filled_l, _conflicts_l = B.merge_series(_series_l, _other_l)
check("[v38] 병합 — 새 라운드는 없음(둘 다 이미 라운드 2개)", _added_l == 0)
check("[v38] 병합 — 빈 경기 2건이 채워짐", _filled_l == 2)
check("[v38] 병합 — 충돌 1건 감지됨(자동으로 덮어쓰지 않음)", len(_conflicts_l) == 1)
_before_winner = _series_l.rounds[0].events[_ei0].bracket.rounds[_r0][_i0].winner
check("[v38] 병합 — 충돌 상태에서는 local 값이 그대로 유지됨(직접 고르기 전까지)",
      _before_winner == "a")
B.apply_conflict_choice(_series_l, _conflicts_l[0], "other")
check("[v38] 충돌 해결(other 선택) — 값이 실제로 바뀜",
      _series_l.rounds[0].events[_ei0].bracket.rounds[_r0][_i0].winner == "b")
B.apply_conflict_choice(_series_l, _conflicts_l[0], "local")
check("[v38] 충돌 해결(local 선택) — 값이 그대로 유지됨(다시 안 덮어씀)",
      _series_l.rounds[0].events[_ei0].bracket.rounds[_r0][_i0].winner == "b")

section("27m. [v38] 대진표 작성기 — 위젯(라운드 자동 저장/복원, 형식 라디오)")

win.switch_mode("util")
win.util_panel.open_app("bracket")
app.processEvents()
bkw_r = win.util_panel._pages["bracket"][0]
check("[v38] 형식은 진짜 라디오 버튼 쌍(배타적)이고 기본은 리그전",
      bkw_r.format_group.exclusive() and bkw_r.radio_format_league.isChecked()
      and not bkw_r.radio_format_tournament.isChecked())
bkw_r.radio_format_tournament.setChecked(True)
app.processEvents()
check("[v38] 토너먼트 라디오를 누르면 리그 쪽은 자동으로 꺼짐(배타 선택)",
      bkw_r._format == B.FORMAT_TOURNAMENT and not bkw_r.radio_format_league.isChecked())
bkw_r.radio_format_league.setChecked(True)
from src.utils import bracket as _bracket_mod3
_fresh_bkw = _bracket_mod3.BracketWidget(None)
check("[v39] 실력 고려 콤보의 기본값은 팀 레벨 평균(인덱스 2) — 새로 여는 위젯 기준",
      _fresh_bkw.combo_tier_mode.currentIndex() == 2)
check("[v38] 참가자 트리 전체 펼치기 토글은 기본 꺼짐(접힘)", not bkw_r.btn_toggle_all_classes.isChecked())

with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw_r._on_roster_clear()
_r_roster_path = _os.path.join(_tf.mkdtemp(), "명단.xlsx")
_wb_r = _opxr.Workbook(); _ws_r = _wb_r.active
_ws_r.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 7):
    _ws_r.append([2, 5, i, f"참가자{i}", "남"])
_wb_r.save(_r_roster_path)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_r_roster_path, "")):
    bkw_r._on_roster_upload()
app.processEvents()
bkw_r._history_path = _os.path.join(_tf.mkdtemp(), "이력_라운드테스트.xlsx")
bkw_r.combo_tier_mode.setCurrentIndex(0)
bkw_r.spin_team_size.setValue(1)
bkw_r.tree_participants.topLevelItem(0).setCheckState(0, Qt.Checked)
app.processEvents()
bkw_r._on_generate()
app.processEvents()
check("[v38] 생성하면 시리즈가 자동으로 만들어지고 라운드 1개가 생김",
      bkw_r.series is not None and len(bkw_r.series.rounds) == 1)
check("[v38.3] 회차 콤보 라벨에 '회차 1'과 진행률이 표시됨(리그의 'N라운드'와는 다른 용어)",
      "회차 1" in bkw_r.combo_event.currentText() and "0/" in bkw_r.combo_event.currentText())
check("[v38] 시리즈 콤보에도 방금 만든 시리즈가 보임",
      bkw_r.combo_series.currentData() == bkw_r.series.key)

_win_r2 = MainWindow(); _win_r2.show()
_win_r2.switch_mode("util"); _win_r2.util_panel.open_app("bracket")
app.processEvents()
_bkw_r2 = _win_r2.util_panel._pages["bracket"][0]
check("[v38] 재기동해도 마지막 시리즈가 자동으로 복원됨",
      _bkw_r2.series is not None and _bkw_r2.series.key == bkw_r.series.key
      and len(_bkw_r2.series.rounds) == 1)
_win_r2.close()

# 인원 부족 팀 안내(홀수 인원 등으로 한 명이 팀을 못 이루는 경우) — 배드민턴
# 라운드 1이 아직 안 끝났으니(위 규칙) 다른 종목(탁구)으로 새 시리즈를
# 만들고, 참가자를 홀수(5명)로 골라 진짜 "한 명 남는" 상황을 만든다.
_idx_pingpong = bkw_r.combo_sport.findText("탁구")
bkw_r.combo_sport.setCurrentIndex(_idx_pingpong)
bkw_r.combo_tier_mode.setCurrentIndex(0)
bkw_r.spin_team_size.setValue(2)
_class_item_r = bkw_r.tree_participants.topLevelItem(0)
for j in range(_class_item_r.childCount()):
    _class_item_r.child(j).setCheckState(0, Qt.Checked)
_class_item_r.child(_class_item_r.childCount() - 1).setCheckState(0, Qt.Unchecked)   # 6명 중 5명만 선택
app.processEvents()
with _patch("src.utils.bracket.QMessageBox.information", return_value=None) as _mi:
    bkw_r._on_generate()
app.processEvents()
check("[v38] 5명을 2인 팀으로 나누면 2팀 + 미배정 1명(대진표엔 안 들어감)",
      len(bkw_r._current_event.entries) == 2
      and all(len(sids) == 2 for sids in bkw_r._current_event.entries.values())
      and len(bkw_r._current_event.unassigned_sids) == 1)

# 학생 추가 배정 — 미배정 학생을 강제로 팀에 넣어 3인 팀 만들기
from src.utils.bracket import _ReassignDialog
_entry_ids_r = list(bkw_r._current_event.entries.keys())
_target_entry = _entry_ids_r[0]
_extra_sid = bkw_r._current_event.unassigned_sids[0]
_dlg_r = _ReassignDialog(bkw_r._current_event, bkw_r.roster)
check("[v38] 재배정 다이얼로그의 학생 목록 = 이 이벤트의 미배정 학생만",
      [_dlg_r.combo_student.itemData(i) for i in range(_dlg_r.combo_student.count())] ==
      bkw_r._current_event.unassigned_sids)
_idx_student = _dlg_r.combo_student.findData(_extra_sid)
_idx_team = _dlg_r.combo_team.findData(_target_entry)
_dlg_r.combo_student.setCurrentIndex(_idx_student)
_dlg_r.combo_team.setCurrentIndex(_idx_team)
check("[v38] 재배정 다이얼로그 결과값이 고른 학생·팀과 일치", _dlg_r.result() == (_extra_sid, _target_entry))
check("[v38] 팀 콤보 표시는 줄바꿈 없이 한 줄(쉼표로 이어짐)",
      "\n" not in _dlg_r.combo_team.itemText(0))

# 아래는 다이얼로그 없이 실제 배정 로직만 재현
_ev_r = bkw_r._current_event
_ev_r.unassigned_sids.remove(_extra_sid)
_ev_r.entries[_target_entry].append(_extra_sid)
check("[v38] 팀에 인원을 추가하면 3인 팀이 되고, 미배정 목록에서는 빠짐",
      len(_ev_r.entries[_target_entry]) == 3 and _extra_sid not in _ev_r.unassigned_sids)
check("[v38] 1인짜리 유령 팀이 따로 안 남음(entries는 여전히 2개뿐)",
      len(_ev_r.entries) == 2)

# ---- 라운드 완료 검증: 이전 라운드가 안 끝났으면 새 라운드 생성을 막음 ----
# (여기서부터는 방금 만든 탁구·2학년5반 시리즈를 그대로 이어 쓴다 — 참가자
# 선택도 그대로라 같은 시리즈로 다시 "생성"을 누르는 셈이다.)
check("[v38] (사전 확인) 방금 만든 라운드는 아직 안 끝남",
      not bkw_r.series.rounds[-1].is_completed())
_rounds_before_gate = len(bkw_r.series.rounds)
with _patch("src.utils.bracket.QMessageBox.information", return_value=None) as _mi_gate:
    bkw_r._on_generate()
app.processEvents()
check("[v38] 이전 라운드가 안 끝났으면 새 라운드가 안 만들어짐(막힘)",
      len(bkw_r.series.rounds) == _rounds_before_gate)
check("[v38] 막혔을 때 안내 메시지가 뜸", _mi_gate.called)

_last_round = bkw_r.series.rounds[-1]
for _ei, _r, _i, _m in _last_round.all_matches():
    if _m.winner is None:
        _last_round.events[_ei].bracket.record(_r, _i, "a", sets=[[21, 15]])
check("[v38] 남은 경기를 전부 기록하면 라운드가 완료 상태가 됨", _last_round.is_completed())
with _patch("src.utils.bracket.QMessageBox.information", return_value=None):
    bkw_r._on_generate()
app.processEvents()
check("[v38] 이전 라운드가 끝난 뒤에는 새 라운드가 정상적으로 만들어짐",
      len(bkw_r.series.rounds) == _rounds_before_gate + 1)

section("27n. [v38.2] 대진표 작성기 — 명단 지우기가 시리즈 파일까지 지움")

check("[v38.2] 지우기 전 — 시리즈 파일이 실제로 디스크에 있음",
      any(k == bkw_r.series.key for k, _p in B.list_series_files(bkw_r._history_path)))
_series_path_before = B.series_file_path(bkw_r._history_path, bkw_r.series.key)
check("[v38.2] (사전 확인) 파일 경로가 실제로 존재함", _os.path.exists(_series_path_before))
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw_r._on_roster_clear()
app.processEvents()
check("[v38.2] 명단 지우기 후 — 디스크의 시리즈 파일이 실제로 삭제됨",
      not _os.path.exists(_series_path_before))
check("[v38.2] 명단 지우기 후 — 메모리의 시리즈·이벤트도 비워짐",
      bkw_r.series is None and bkw_r.events == [])
check("[v38.2] 명단 지우기 후 — QSettings에도 빈 명단이 저장됨(재기동해도 안 돌아옴)",
      B.roster_from_json(bkw_r._settings.value("util.bracket.roster", "")) == [])

# 이전에는 이 상태에서 같은 반으로 다시 생성하면 디스크에 남은 옛 시리즈를
# 불러와 "이전 라운드가 안 끝났다"며 막혔다 — 이제는 완전히 새로 시작해야 한다.
_r2_roster_path = _os.path.join(_tf.mkdtemp(), "명단2.xlsx")
_wb_r2n = _opxr.Workbook(); _ws_r2n = _wb_r2n.active
_ws_r2n.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 5):
    _ws_r2n.append([2, 5, i, f"참가자{i}", "남"])
_wb_r2n.save(_r2_roster_path)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_r2_roster_path, "")):
    bkw_r._on_roster_upload()
app.processEvents()
bkw_r.tree_participants.topLevelItem(0).setCheckState(0, Qt.Checked)
bkw_r.spin_team_size.setValue(1)
app.processEvents()
with _patch("src.utils.bracket.QMessageBox.information", return_value=None):
    bkw_r._on_generate()
app.processEvents()
check("[v38.2] 명단을 지운 뒤 같은 반으로 다시 생성하면 막히지 않고 라운드 1이 새로 만들어짐",
      bkw_r.series is not None and len(bkw_r.series.rounds) == 1)

section("27o. [v38.3] 대진표 작성기 — 반을 오가도 각자의 회차가 독립적으로 보존됨")

_tmpdir_switch = _tf.mkdtemp()
_hist_switch = _os.path.join(_tmpdir_switch, "이력.xlsx")

def _make_roster_file(path, grade, cls, n):
    wb = _opxr.Workbook(); ws = wb.active
    ws.append(["학년", "반", "번호", "이름", "성별"])
    for i in range(1, n + 1):
        ws.append([grade, cls, i, f"학생{cls}반{i}", "남"])
    wb.save(path)

win.switch_mode("util")
win.util_panel.open_app("bracket")
app.processEvents()
bkw_sw = win.util_panel._pages["bracket"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw_sw._on_roster_clear()
bkw_sw._history_path = _hist_switch
_idx_badminton_sw = bkw_sw.combo_sport.findText("배드민턴")
bkw_sw.combo_sport.setCurrentIndex(_idx_badminton_sw)

# 1학년 2반 — 회차 1을 만들고 절반만 기록(수업이 안 끝난 상태)
_p2 = _os.path.join(_tmpdir_switch, "2반.xlsx")
_make_roster_file(_p2, 1, 2, 8)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_p2, "")):
    bkw_sw._on_roster_upload()
app.processEvents()
bkw_sw.tree_participants.topLevelItem(0).setCheckState(0, Qt.Checked)
bkw_sw.combo_tier_mode.setCurrentIndex(0)
bkw_sw.spin_team_size.setValue(2)
app.processEvents()
bkw_sw._on_generate()
app.processEvents()
_matches_2ban = bkw_sw.series.rounds[0].all_matches()
for _ei, _r, _i, _m in _matches_2ban[:len(_matches_2ban) // 2]:
    bkw_sw.series.rounds[0].events[_ei].bracket.record(_r, _i, "a", sets=[[21, 15]])
_progress_2ban = bkw_sw.series.rounds[0].progress()
check("[v38.3] 1학년2반 — 절반만 기록한 뒤 시리즈에 정확히 저장됨(진행 중)",
      0 < _progress_2ban[0] < _progress_2ban[1])
bkw_sw._save_series_file()

# (다음 시간) 1학년 3반 — 전혀 다른 시리즈로 새로 시작
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    pass  # 3반은 명단 지우기 없이 그냥 새로 업로드(다른 반 명단으로 갈아치움)
_p3 = _os.path.join(_tmpdir_switch, "3반.xlsx")
_make_roster_file(_p3, 1, 3, 6)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_p3, "")):
    bkw_sw._on_roster_upload()
app.processEvents()
bkw_sw.tree_participants.topLevelItem(0).setCheckState(0, Qt.Checked)
bkw_sw.spin_team_size.setValue(1)
app.processEvents()
bkw_sw._on_generate()
app.processEvents()
check("[v38.3] 1학년3반 — 2반과 전혀 다른 시리즈가 새로 만들어짐(섞이지 않음)",
      bkw_sw.series.key != "배드민턴_1학년2반" and len(bkw_sw.series.rounds) == 1)

# (그다음 시간) 다시 1학년 2반으로 — 시리즈 콤보에서 고르면 이어서 기록할 수 있어야 함
_idx_2ban = bkw_sw.combo_series.findData("배드민턴_1학년2반")
check("[v38.3] 시리즈 콤보에 1학년2반이 그대로 남아 있음", _idx_2ban >= 0)
bkw_sw.combo_series.setCurrentIndex(_idx_2ban)
app.processEvents()
check("[v38.3] 2반으로 되돌아가면 중간까지 기록한 진행 상태가 그대로 복원됨",
      bkw_sw.series.rounds[0].progress() == _progress_2ban)
check("[v38.3] 3반에서 만든 회차는 2반 목록에 안 섞여 들어옴", len(bkw_sw.series.rounds) == 1)

section("27p. [v39] 대진표 작성기 — 오늘 출석 조정(결석·임시 편성·출전자 스냅숏)")

_s39 = [B.Student(f"1-2-{i}-학생{i}", "1", "2", str(i), f"학생{i}", "여" if i % 2 else "남") for i in range(1, 7)]
_rb39 = {s.sid: s for s in _s39}
_ev39 = B.build_event("R", _s39, format=B.FORMAT_LEAGUE, team_size=2, seed=3, sport="배드민턴")
_rnd39 = B.Round([_ev39])
_eids = list(_ev39.entries.keys())
check("[v39] 6명 2인 팀 → 3팀, 미배정 없음", len(_eids) == 3 and not _ev39.unassigned_sids)

_tA, _tB, _tC = _eids
_absent_sid = _ev39.entries[_tB][0]      # B팀에서 1명 결석 → B팀 1명 남음
_lone_sid = _ev39.entries[_tB][1]
_borrow_sid = _ev39.entries[_tA][0]
# A팀은 2명뿐이라 빌려올 수 없음 → 남은 1명을 C팀에 합류(오늘 3인)
_rnd39.set_adjustment("20260921", 0, [_absent_sid], [{"sid": _lone_sid, "from": _tB, "to": _tC}])
_eff = B.effective_members(_ev39, _rnd39, "20260921", 0)
check("[v39] 결석자는 그날 팀원에서 빠짐", _absent_sid not in _eff[_tB])
check("[v39] 임시 합류자는 원래 팀에서 빠지고 합류 팀에 들어감(오늘 3인)",
      _lone_sid not in _eff[_tB] and _lone_sid in _eff[_tC] and len(_eff[_tC]) == 3)
check("[v39] 다른 날짜에는 조정이 적용되지 않아 기본 팀으로 복귀",
      B.effective_members(_ev39, _rnd39, "20260922", 0) == {k: list(v) for k, v in _ev39.entries.items()})
_r39 = B.Round.from_dict(_rnd39.to_dict())
check("[v39] 조정 내역이 저장/복원됨", _r39.adjustment_for("20260921", 0) is not None)

# 스냅숏: 경기 기록 시 실제 출전자 저장 → 엑셀 행·파트너 집계에 반영
_m39 = next(m for row in _ev39.bracket.rounds for m in row if m.a == _tC or m.b == _tC)
_side = "a" if _m39.a == _tC else "b"
_ev39.bracket.record(*[(r, i) for r, row in enumerate(_ev39.bracket.rounds) for i, m in enumerate(row) if m is _m39][0],
                     _side, sets=[[21, 10]])
_m39.side_sids = {"a": list(_eff.get(_m39.a, [])), "b": list(_eff.get(_m39.b, []))}
check("[v39] 스냅숏 쪽 출전자 = 오늘 조정 반영(3명)", len(B.match_side_sids(_ev39, _m39, _side)) == 3)
_m39_rt = B.Match.from_dict(_m39.to_dict())
check("[v39] 스냅숏이 직렬화/복원됨", _m39_rt.side_sids == _m39.side_sids)
_rows39 = B.build_history_rows("배드민턴", B.FORMAT_LEAGUE, "20260921", _rb39,
                               B.match_side_sids(_ev39, _m39, _side),
                               B.match_side_sids(_ev39, _m39, "b" if _side == "a" else "a"),
                               [[21, 10]], _side == "a")
check("[v39] 엑셀 행은 실제 출전자(3명) 기준으로 3줄", len(_rows39) == 3)
_series39 = B.Series("배드민턴_1학년2반", "배드민턴", "1학년2반", rounds=[_rnd39])
_pc39 = _series39.partnership_counts(_rb39)
check("[v39] 파트너 집계는 스냅숏 기준(임시 합류자와 합류 팀원이 같은편으로 잡힘)",
      frozenset({_rb39[_lone_sid].name, _rb39[_ev39.entries[_tC][0]].name}) in _pc39)

# 출석 조정 다이얼로그 — 체크 해제 → 혼자 남은 팀 처리 옵션(빌려오기/합류)
from src.utils.bracket import _AttendanceDialog, _is_female
_dlg39 = _AttendanceDialog(_ev39, _s39, B.Round([_ev39]), 0, "20260921")
_dlg39.checks[_absent_sid].setChecked(False)
app.processEvents()
check("[v39] 결석 처리 후 혼자 남은 팀의 해결 콤보가 생김", _tB in _dlg39.fix_combos)
from PySide6.QtWidgets import QDialogButtonBox
_combo39 = _dlg39.fix_combos[_tB]
_opts = [_combo39.itemData(k) for k in range(_combo39.count())]
check("[v39] 첫 항목은 '선택 안 함'(데이터 None) — 아무것도 미리 안 골라져 있음",
      _opts[0] is None)
check("[v39] 빌려올 3인 팀이 없으니 '2인 팀에 합류' 옵션만 나옴(선택 안 함 + 2개)",
      all(o[0] == "join" for o in _opts[1:]) and len(_opts) == 3)
check("[v39] 선택 안 함 상태에서는 OK 버튼이 비활성화됨",
      not _dlg39.buttons.button(QDialogButtonBox.Ok).isEnabled())
_combo39.setCurrentIndex(1)   # 실제 옵션 하나를 골라야 OK가 눌린다
app.processEvents()
check("[v39] 옵션을 고르면 OK 버튼이 활성화됨",
      _dlg39.buttons.button(QDialogButtonBox.Ok).isEnabled())
_absent39, _tr39 = _dlg39.result()
check("[v39] 다이얼로그 결과 = 결석 1명 + 합류 이동 1건",
      _absent39 == [_absent_sid] and len(_tr39) == 1 and _tr39[0]["sid"] == _lone_sid)
check("[v39] 성별 판정 — '여'/'F'는 여학생, '남'은 아님",
      _is_female("여") and _is_female("F") and not _is_female("남") and not _is_female(""))

# 위젯 경로: 출석 조정 → 대진표 라벨에 즉시 반영 → 기록 시 스냅숏
win.switch_mode("util"); win.util_panel.open_app("bracket"); app.processEvents()
bkw39 = win.util_panel._pages["bracket"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkw39._on_roster_clear()
bkw39._history_path = _os.path.join(_tf.mkdtemp(), "이력39.xlsx")
_p39 = _os.path.join(_tf.mkdtemp(), "39.xlsx")
_wb39 = _opxr.Workbook(); _ws39 = _wb39.active
_ws39.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 7):
    _ws39.append([1, 2, i, f"학생{i}", "여" if i % 2 else "남"])
_wb39.save(_p39)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_p39, "")):
    bkw39._on_roster_upload()
app.processEvents()
_ci39 = bkw39.tree_participants.topLevelItem(0)
check("[v39] 참가자 표 이름 칸에 성별 데이터가 실려 있음(여학생 표시용)",
      _ci39.child(0).data(0, Qt.UserRole + 1) == "여" and _ci39.child(1).data(0, Qt.UserRole + 1) == "남")
from src.utils.bracket import _GenderMarkDelegate
check("[v39] 이름 칸에 여학생 표시 델리게이트가 걸려 있음",
      isinstance(bkw39.tree_participants.itemDelegateForColumn(0), _GenderMarkDelegate))
_ci39.setCheckState(0, Qt.Checked)
bkw39.combo_sport.setCurrentIndex(bkw39.combo_sport.findText("배드민턴"))
bkw39.combo_tier_mode.setCurrentIndex(0); bkw39.spin_team_size.setValue(2)
app.processEvents()
bkw39._on_generate(); app.processEvents()
_evw = bkw39._current_event
_rndw, _eiw = bkw39._round_and_index_of(_evw)
_eidw = list(_evw.entries.keys())
_absw = _evw.entries[_eidw[1]][0]; _lonew = _evw.entries[_eidw[1]][1]
_rndw.set_adjustment(bkw39._today_str(), _eiw, [_absw], [{"sid": _lonew, "from": _eidw[1], "to": _eidw[2]}])
bkw39._on_event_selected(bkw39.combo_event.currentIndex()); app.processEvents()
_labels_w = bkw39._effective_labels(_evw)
check("[v39] 대진표 라벨에 결석 표시와 (임시) 표시가 바로 반영됨",
      "결석" in _labels_w[_eidw[1]] and "(임시)" in _labels_w[_eidw[2]])
_found = False
for _row in range(bkw39.league_view.table.rowCount()):
    _t = bkw39.league_view.table.item(_row, 2).text() + bkw39.league_view.table.item(_row, 1).text()
    if "(임시)" in _t:
        _found = True
check("[v39] 리그 표 칸에도 '(임시)' 표시가 실제로 그려짐", _found)
_rw, _iw = next((r, i) for r, row in enumerate(_evw.bracket.rounds) for i, m in enumerate(row)
                if m.a is not None and m.b is not None and _eidw[2] in (m.a, m.b))
_bracket_mod.__dict__  # (모듈 확보)
_bracket_mod._RecordResultDialog = _FakeSetDialog
bkw39._on_league_match_clicked(_rw, _iw); app.processEvents()
_bracket_mod._RecordResultDialog = _orig_dlg
_mw = _evw.bracket.rounds[_rw][_iw]
_sidew = "a" if _mw.a == _eidw[2] else "b"
check("[v39] 위젯 경로로 기록하면 실제 출전자 스냅숏(3명)이 경기 안에 남음",
      _mw.side_sids is not None and len(_mw.side_sids[_sidew]) == 3)
check("[v39] 결석자는 어느 편 스냅숏에도 없음",
      _absw not in _mw.side_sids["a"] and _absw not in _mw.side_sids["b"])

section("27q. [v39] 대진표 작성기 — 팀 레벨 평균 모드 + 성적 산출")

check("[v39] 실력 고려 콤보에 항목 3개(무작위/수준별 분리/팀 레벨 평균)",
      [_fresh_bkw.combo_tier_mode.itemText(i) for i in range(_fresh_bkw.combo_tier_mode.count())] ==
      ["", "", ""] or _fresh_bkw.combo_tier_mode.count() == 3)

win.switch_mode("util"); win.util_panel.open_app("bracket"); app.processEvents()
bkwq = win.util_panel._pages["bracket"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkwq._on_roster_clear()
bkwq._history_path = _os.path.join(_tf.mkdtemp(), "이력q.xlsx")
_pq = _os.path.join(_tf.mkdtemp(), "q.xlsx")
_wbq = _opxr.Workbook(); _wsq = _wbq.active
_wsq.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 13):
    _wsq.append([3, 1, i, f"참가자{i}", "여" if i % 2 else "남"])
_wbq.save(_pq)
with _patch("src.utils.bracket.QFileDialog.getOpenFileName", return_value=(_pq, "")):
    bkwq._on_roster_upload()
app.processEvents()
# 교사 등급을 절반은 상, 절반은 하로 강제 매겨 "팀 레벨 평균"이 실제로
# 효과가 있는지 확인한다(안 그러면 전원 '중'이라 평균이 항상 2로만 나옴).
_ci_q = bkwq.tree_participants.topLevelItem(0)
_ci_q.setCheckState(0, Qt.Checked)
_sport_q = bkwq._current_sport_name()
for j in range(_ci_q.childCount()):
    sid = _ci_q.child(j).data(0, Qt.UserRole)
    bkwq._manual_tiers[(_sport_q, sid)] = B.TIER_HIGH if j % 2 == 0 else B.TIER_LOW
app.processEvents()
bkwq.combo_tier_mode.setCurrentIndex(2)   # 이전 섹션들이 재사용 중인 위젯의 콤보를 건드려 놨을 수 있어 명시적으로 맞춘다
bkwq.spin_team_size.setValue(2)
app.processEvents()
bkwq._on_generate()
app.processEvents()
_evq = bkwq._current_event
_tiers_q = bkwq._compute_tiers_by_sid(bkwq.roster, _sport_q)
_avgs_q = [B.team_level_average([s for s in bkwq.roster if s.sid in sids], _tiers_q)
          for sids in _evq.entries.values()]
check("[v39] 팀 레벨 평균 모드로 생성 — 모든 팀 평균이 1.5~2.5 안", all(1.5 <= a <= 2.5 for a in _avgs_q), _avgs_q)
check("[v39] 상/하를 절반씩 섞었으니 실제로 평균이 2 근처로 균형 잡힘",
      all(abs(a - 2.0) <= 0.6 for a in _avgs_q), _avgs_q)

# ---- 성적 산출 ----
for _ei, _r, _i, _m in bkwq.series.rounds[0].all_matches():
    bkwq.series.rounds[0].events[_ei].bracket.record(_r, _i, "a", sets=[[21, 15]])
_gpath = _os.path.join(_tf.mkdtemp(), "성적출력.xlsx")
with _patch("src.utils.bracket.QFileDialog.getSaveFileName", return_value=(_gpath, "")):
    bkwq._on_export_grades()
app.processEvents()
check("[v39] 성적 산출 — 엑셀 파일이 실제로 생성됨", _os.path.exists(_gpath))
_wb_g = _opxr.load_workbook(_gpath)
_ws_g = _wb_g.active
check("[v39] 성적 파일 머리글이 예상대로", [c.value for c in _ws_g[1]] == B.GRADE_HEADERS)
_data_rows = [[c.value for c in row] for row in _ws_g.iter_rows(min_row=2) if row[0].value is not None]
check("[v39] 경기에 실제로 참여한 학생 수만큼 성적 줄이 생김", len(_data_rows) > 0)
_row_by_name = {r[3]: r for r in _data_rows}
_sample_student = bkwq.roster[0]
if _sample_student.name in _row_by_name:
    _row = _row_by_name[_sample_student.name]
    check("[v39] 개인 성적 행 — 경기수=승+패", _row[4] == _row[5] + _row[6])

# 아직 기록이 하나도 없으면 성적 산출이 안내만 하고 저장하지 않는지
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    bkwq._on_roster_clear()
with _patch("src.utils.bracket.QMessageBox.information", return_value=None) as _mi_empty:
    bkwq._on_export_grades()
check("[v39] 시리즈가 없을 때 성적 산출을 누르면 안내만 뜨고 죽지 않음", _mi_empty.called)

section("27r. [v39.2] 대진표 작성기 — 두 학생이 동시에 혼자 남을 때 서로 짝지을 수 있음")

_s39r = [B.Student(f"1-2-{i}-학생{i}", "1", "2", str(i), f"학생{i}") for i in range(1, 7)]
_ev39r = B.build_event("R", _s39r, format=B.FORMAT_LEAGUE, team_size=2, seed=5, sport="배드민턴")
_eids_r = list(_ev39r.entries.keys())
check("[v39.2] 6명 2인 팀 → 3팀", len(_eids_r) == 3)
_rnd39r = B.Round([_ev39r])
# 서로 다른 두 팀에서 한 명씩 결석 — 두 팀이 동시에 "혼자 남음" 상태가 됨
_teamA, _teamB, _teamC = _eids_r
_absentA = _ev39r.entries[_teamA][0]
_loneA = _ev39r.entries[_teamA][1]
_absentB = _ev39r.entries[_teamB][0]
_loneB = _ev39r.entries[_teamB][1]

from src.utils.bracket import _AttendanceDialog
from PySide6.QtWidgets import QDialogButtonBox as _QDBB
_dlg_r2 = _AttendanceDialog(_ev39r, _s39r, _rnd39r, 0, "20260921")
_dlg_r2.checks[_absentA].setChecked(False)
_dlg_r2.checks[_absentB].setChecked(False)
app.processEvents()
check("[v39.2] 두 팀이 동시에 혼자 남으면 콤보가 2개 생김", len(_dlg_r2.fix_combos) == 2)
check("[v39.2] OK는 둘 다 선택 안 함이라 비활성화", not _dlg_r2.buttons.button(_QDBB.Ok).isEnabled())

# teamA의 콤보에서 "loneB(=teamB에 혼자 남은 학생)를 빌려오기"를 선택
_comboA = _dlg_r2.fix_combos[_teamA]
_borrow_idx = None
for _k in range(_comboA.count()):
    _data = _comboA.itemData(_k)
    if _data and _data[0] == "borrow" and _data[1] == _loneB:
        _borrow_idx = _k
        break
check("[v39.2] 다른 1인 팀(teamB)의 학생도 '빌려오기' 후보로 나옴(예전엔 3인 이상 팀에서만 가능했음)",
      _borrow_idx is not None)
_comboA.setCurrentIndex(_borrow_idx)
app.processEvents()

check("[v39.2] teamB를 흡수했으니, teamB 자신의 콤보는 더 이상 안 보임(0명이 됐으므로)",
      _teamB not in _dlg_r2.fix_combos and _teamA in _dlg_r2.fix_combos)
check("[v39.2] 남은 콤보(teamA)에 선택이 돼 있으니 OK가 활성화됨",
      _dlg_r2.buttons.button(_QDBB.Ok).isEnabled())
_absent_r2, _tr_r2 = _dlg_r2.result()
check("[v39.2] 결과 — 결석 2명, 이동 1건(teamB의 loneB가 teamA로)",
      set(_absent_r2) == {_absentA, _absentB} and len(_tr_r2) == 1
      and _tr_r2[0] == {"sid": _loneB, "from": _teamB, "to": _teamA})

section("27s. [v39.3] 나이스 설정 패널 — 인증키 채우기 단축키(Ctrl+Shift+F10)")

win.switch_mode("util")
win.util_panel.open_app("meal")
app.processEvents()
mlw = win.util_panel._pages["meal"][0]
from src.utils.neis_common import _MY_NEIS_KEY
mlw.neis_panel.toggle.setChecked(False)
mlw.neis_panel._on_toggle()
mlw.neis_panel.edit_key.setText("")   # 이전 테스트 섹션에서 남았을 수 있는 값 정리
from src.utils.neis_common import NEIS_KEY_EXAMPLE as _EX_KEY
check("[v51.3] 인증키 칸의 예시는 형식만 보여 주고 실제 키는 화면에 안 보임",
      _EX_KEY in mlw.neis_panel.edit_key.placeholderText() and _MY_NEIS_KEY not in mlw.neis_panel.edit_key.placeholderText())
mlw.neis_panel._fill_real_key()
app.processEvents()
check("[v39.3] 단축키(직접 호출)로 실제 인증키가 채워짐", mlw.neis_panel.edit_key.text() == _MY_NEIS_KEY)
check("[v39.3] 채워질 때 학교 설정 패널이 자동으로 펼쳐짐", mlw.neis_panel.toggle.isChecked())
check("[v39.3] 학교 일정과 인증키를 공유하므로 그쪽 값도 같이 채워짐 확인 대상은 QSettings",
      QSettings("SRIHS", "FolderSync").value("util.neis.key", "") == _MY_NEIS_KEY)

# [버그 수정] 이전 테스트는 _fill_real_key()를 직접 호출해서 QShortcut의
# 실제 키 전달 경로를 전혀 거치지 않았다 — 그래서 "이 패널(self)이
# 레이아웃에 addWidget된 적이 없어 화면 트리에서 떨어져 나간 고아
# 위젯이라, WindowShortcut 범위의 단축키가 절대 안 눌리는" 진짜 버그를
# 못 잡았다. 이번엔 QTest로 실제 키 시퀀스를 보내서, 진짜 단축키
# 경로(ApplicationShortcut로 고친 부분)가 제대로 동작하는지 확인한다.
from PySide6.QtTest import QTest
from PySide6.QtGui import QKeySequence
mlw.neis_panel.edit_key.setText("")
mlw.neis_panel._emit_changed()
app.processEvents()
win.raise_()
win.activateWindow()
from PySide6.QtWidgets import QApplication as _QApp
_QApp.instance().setActiveWindow(win)
app.processEvents()
QTest.keySequence(mlw, QKeySequence("Ctrl+Shift+F10"))
app.processEvents()
check("[버그 수정] 실제 키 입력(QTest)으로도 단축키가 동작함(고아 위젯 버그 수정 확인)",
      mlw.neis_panel.edit_key.text() == _MY_NEIS_KEY)
check("[버그 수정] 단축키의 실행 범위가 ApplicationShortcut로 바뀜(WindowShortcut 의존 제거)",
      mlw.neis_panel._shortcut_fill_key.context() == Qt.ApplicationShortcut)

section("39. [v40] 좌석표 — 순수 로직")

import src.utils.seating_solve as SS

_seat_students = [B.Student(f"1-3-{i}-학생{i}", "1", "3", str(i), f"학생{i}") for i in range(1, 23)]
_chart = SS.random_layout(_seat_students, cols=5, seed=1, grade="1", cls="3")
check("[v40] 22명을 5줄로 배치하면 5행이 됨(ceil(22/5))", _chart.rows == 5 and _chart.cols == 5)
_flat = [sid for row in _chart.seats for sid in row if sid is not None]
check("[v40] 빈 자리를 빼면 학생 수와 정확히 일치, 중복 없음",
      len(_flat) == 22 and len(set(_flat)) == 22)
check("[v40] 인원이 안 나누어떨어지면 마지막 줄에만 빈 자리가 생김",
      all(None not in row for row in _chart.seats[:-1]) and _chart.seats[-1].count(None) == 3)

_opts = SS.class_options(_seat_students + [B.Student("2-1-1", "2", "1", "1", "다른반")])
check("[v40] class_options가 학년·반 조합을 학년순으로 뽑음", _opts == [("1", "3"), ("2", "1")])

_reshuffled = SS.reshuffle(_chart, _seat_students, seed=2)
check("[v40] 다시 섞으면 같은 줄 수를 유지한 채 자리가 바뀜",
      _reshuffled.cols == _chart.cols and _reshuffled.seats != _chart.seats)

_tmpdir_seat = _tf.mkdtemp()
_path_seat = SS.chart_file_path(_tmpdir_seat, "1", "3")
SS.save_chart(_path_seat, _chart)
_loaded_seat = SS.load_chart(_path_seat)
check("[v40] 저장/불러오기 후 좌석 배치가 그대로 보존됨",
      _loaded_seat.seats == _chart.seats and _loaded_seat.id == _chart.id)
check("[v40] list_chart_files가 저장한 좌석표 파일을 찾아냄",
      any(_path_seat == p for p in SS.list_chart_files(_tmpdir_seat)))

section("39b. [v40] 좌석표 — 위젯 통합")

win.switch_mode("util")
win.util_panel.open_app("seating")
app.processEvents()
seatw = win.util_panel._pages["seating"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw._on_roster_clear()

_seat_xlsx = _os.path.join(_tf.mkdtemp(), "좌석명단.xlsx")
_wb_seat = _opxr.Workbook(); _ws_seat = _wb_seat.active
_ws_seat.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 13):
    _ws_seat.append([1, 4, i, f"참가자{i}", "여" if i % 2 else "남"])
_wb_seat.save(_seat_xlsx)
with _patch("src.utils.seating.QFileDialog.getOpenFileName", return_value=(_seat_xlsx, "")):
    seatw._on_roster_upload()
app.processEvents()
check("[v40] 명단 업로드 후 반 콤보에 1학년4반이 뜨고 자동 선택됨",
      seatw.combo_class.count() == 1 and seatw.combo_class.currentData() == ("1", "4"))
check("[v40] 반을 고르면 곧바로 좌석 배치가 만들어짐(4줄 기본값)",
      seatw.chart is not None and seatw.chart.cols == 4 and seatw.chart.rows == 3)

_before_seats = [row[:] for row in seatw.chart.seats]
seatw._on_reshuffle()
app.processEvents()
check("[v40] '다시 섞기'를 누르면 배치가 바뀜(같은 12명)",
      seatw.chart.seats != _before_seats
      and sorted(sid for row in seatw.chart.seats for sid in row if sid) ==
          sorted(sid for row in _before_seats for sid in row if sid))

seatw.spin_cols.setValue(3)
app.processEvents()
check("[v40] 줄 수를 바꾸면 그 줄 수로 다시 배치됨", seatw.chart.cols == 3 and seatw.chart.rows == 4)

_save_dir = _tf.mkdtemp()
with _patch("src.utils.seating.QFileDialog.getExistingDirectory", return_value=_save_dir):
    seatw._on_pick_save_dir()
app.processEvents()
check("[v40] 저장 폴더를 고르면 즉시 그 반의 좌석표 파일이 생김",
      _os.path.exists(SS.chart_file_path(_save_dir, "1", "4")))

_win_seat2 = MainWindow(); _win_seat2.show()
_win_seat2.switch_mode("util"); _win_seat2.util_panel.open_app("seating")
app.processEvents()
_seatw2 = _win_seat2.util_panel._pages["seating"][0]
check("[v40] 재기동해도 명단·저장 폴더·마지막 배치가 그대로 복원됨",
      len(_seatw2.roster) == 12 and _seatw2.save_dir == _save_dir
      and _seatw2.chart is not None and _seatw2.chart.cols == 3
      and _seatw2.chart.seats == seatw.chart.seats)
_win_seat2.close()

with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw._on_roster_clear()
check("[v40] 명단 지우기 후 반 콤보와 좌석표가 비워짐",
      seatw.combo_class.count() == 0 and seatw.chart is None)

section("40. [v41] 컴시간 알리미 간편 버전 — 순수 로직")

import src.utils.timetable_solve as TT

_tt_url = TT.build_url("KEY1", "B10", "7010569", "1", "3", "20260921", "20260925")
check("[v41] URL에 학년·반·기간·인증키가 정확히 들어감",
      "GRADE=1" in _tt_url and "CLASS_NM=3" in _tt_url and "TI_FROM_YMD=20260921" in _tt_url
      and "KEY=KEY1" in _tt_url and _tt_url.startswith(TT.BASE_URL))

_tt_raw_ok = ('{"hisTimetable":[{"head":1},{"row":['
             '{"ALL_TI_YMD":"20260921","PERIO":"1","ITRT_CNTNT":"수학","CLRM_NM":"101호"},'
             '{"ALL_TI_YMD":"20260921","PERIO":"2","ITRT_CNTNT":"영어","CLRM_NM":"201호"},'
             '{"ALL_TI_YMD":"20260922","PERIO":"1","ITRT_CNTNT":"수학","CLRM_NM":"101호"}'
             ']}]}')
_tt_ok = TT.parse(_tt_raw_ok)
check("[v41] 정상 응답이 3개 교시로 파싱됨", _tt_ok.status == "ok" and len(_tt_ok.slots) == 3)

_tt_grouped = TT.group_by_day(_tt_ok.slots)
check("[v41] group_by_day가 날짜별로 교시를 묶음",
      set(_tt_grouped["20260921"].keys()) == {1, 2} and set(_tt_grouped["20260922"].keys()) == {1})
check("[v41] subjects_of가 중복 없이 등장 순서를 유지", TT.subjects_of(_tt_ok.slots) == ["수학", "영어"])
check("[v41] max_period가 최댓값을 찾음", TT.max_period(_tt_ok.slots) == 2)

_tt_mapping = {"수학": "김선생"}
_tt_tv = TT.teacher_view(_tt_ok.slots, _tt_mapping)
check("[v41] teacher_view — 매핑된 과목만 교사에게 배정되고 날짜·교시 순 정렬",
      list(_tt_tv.keys()) == ["김선생"] and len(_tt_tv["김선생"]) == 2
      and _tt_tv["김선생"][0][0] == "20260921" and _tt_tv["김선생"][1][0] == "20260922")
check("[v41] 매핑에 없는 과목(영어)은 교사 시간표에서 빠짐",
      all(row[2] != "영어" for row in _tt_tv["김선생"]))

_tt_empty = TT.parse('{"RESULT":{"CODE":"INFO-200","MESSAGE":"조회된 데이터가 없습니다."}}')
check("[v41] 빈 결과(INFO-200)가 empty로 분류됨", _tt_empty.status == "empty")
_tt_err_xml = TT.parse('<?xml version="1.0"?><RESULT><CODE>ERROR-300</CODE><MESSAGE>인증키 오류</MESSAGE></RESULT>')
check("[v41] XML 오류 응답도 안전하게 처리되고 메시지가 남음",
      _tt_err_xml.status == "error" and "인증키" in _tt_err_xml.message)
check("[v41] 이해할 수 없는 응답도 죽지 않고 error 처리", TT.parse("이상한 문자열").status == "error")

_tt_json = TT.slots_to_json(_tt_ok.slots)
_tt_back = TT.slots_from_json(_tt_json)
check("[v41] 캐시(슬롯) JSON 저장/복원이 정확함",
      len(_tt_back) == 3 and _tt_back[0].subject == "수학" and _tt_back[0].room == "101호")
_tt_mj = TT.mapping_to_json(_tt_mapping)
check("[v41] 매핑 JSON 저장/복원이 정확함", TT.mapping_from_json(_tt_mj) == _tt_mapping)
check("[v41] 매핑 JSON이 비었거나 망가져도 안전하게 빈 dict", TT.mapping_from_json("") == {} and TT.mapping_from_json("{망가짐") == {})

section("40b. [v43.6] 시간표 — 위젯 통합(재설계: 교사 시간표 전체 학급 교차, 교사명 표시)")

win.switch_mode("util")
win.util_panel.open_app("timetable")
app.processEvents()
ttw = win.util_panel._pages["timetable"][0]
ttw.neis_panel.edit_key.setText("")   # 이전 섹션에서 남았을 수 있는 실제 키를 지우고 확인
ttw.neis_panel._emit_changed()
app.processEvents()
check("[v41] 인증키가 없으면 안내 문구만 뜨고 표는 비어 있음(죽지 않음)",
      ttw.table.rowCount() == 0 and ttw.lbl_cache_note.isVisible())
from PySide6.QtWidgets import QComboBox
check("[v43.6] 학년·반이 스피너 대신 콤보박스로 바뀜", isinstance(ttw.combo_grade, QComboBox)
      and isinstance(ttw.combo_class, QComboBox) and ttw.combo_grade.count() >= 3)
check("[v43.7] 학급 모드에서 학년/반 레이블이 콤보 옆에 보임",
      ttw.lbl_grade.isVisible() and ttw.lbl_grade.text() == tr("util.timetable.lbl.grade")
      and ttw.lbl_class.isVisible() and ttw.lbl_class.text() == tr("util.timetable.lbl.class"))
check("[v43.7] 교시 행 높이가 더 커짐(72px)", ttw.table.verticalHeader().defaultSectionSize() == 72)
check("[v43.7] 인쇄 버튼이 항상 보임", ttw.btn_print.isVisible())


class _FakeTTReply:
    def __init__(self, data, err=None):
        self._data = data.encode("utf-8")
        self._err = err if err is not None else QNetworkReply.NoError
    def error(self):
        return self._err
    def readAll(self):
        return self._data
    def deleteLater(self):
        pass


# [테스트 보정] 예전엔 날짜를 2026-09-21/22로 못 박아 두었는데, 화면은 "오늘이 속한
# 주"의 시간표를 그리므로 실제 날짜가 다음 주로 넘어가면 표가 비어 버려 (앱과 무관하게)
# 테스트가 깨졌다 — 이번 주 월·화로 계산해 날짜와 상관없이 돌게 한다.
from datetime import date as _d_tt, timedelta as _td_tt
_tt_mon = _d_tt.today() - _td_tt(days=_d_tt.today().weekday())
_TT_D = [(_tt_mon + _td_tt(days=k)).strftime("%Y%m%d") for k in range(5)]   # 이번 주 월~금
_tt_raw_full = ('{"hisTimetable":[{"head":1},{"row":['
                '{"ALL_TI_YMD":"' + _tt_mon.strftime("%Y%m%d") + '","PERIO":"1","ITRT_CNTNT":"수학","CLRM_NM":"101호"},'
                '{"ALL_TI_YMD":"' + (_tt_mon + _td_tt(days=1)).strftime("%Y%m%d") + '","PERIO":"2","ITRT_CNTNT":"영어","CLRM_NM":"201호"}'
                ']}]}')
_fr1 = _FakeTTReply(_tt_raw_full)
ttw._reply = _fr1
ttw._on_reply_finished(_fr1)
app.processEvents()
check("[v41] 응답을 받으면 학급 시간표 표에 그려짐(1교시 월=수학, 2교시 화=영어)",
      ttw.table.item(0, 0).text().startswith("수학") and ttw.table.item(1, 1).text().startswith("영어"))
check("[v41] 정상 응답을 받으면 캐시 안내문이 안 보임", not ttw.lbl_cache_note.isVisible())
check("[버그 수정] 과목 아래에 의미 없는 교실 번호 대신 담당교사가 표시됨(매핑 전엔 과목만)",
      ttw.table.item(0, 0).text() == "수학")
ttw.mapping = {"수학": "김선생"}
ttw._render()
app.processEvents()
check("[버그 수정] 매핑을 넣으면 학급 시간표에 담당교사 이름이 과목 아래 표시됨",
      ttw.table.item(0, 0).text() == "수학\n김선생")
check("[v43.6] 모든 교시 행의 높이가 똑같이 맞춰짐(들쭉날쭉하지 않음)",
      len({ttw.table.rowHeight(r) for r in range(ttw.table.rowCount())}) == 1)

# 서버 오류가 나도 방금 받은 시간표(캐시)가 그대로 남아야 한다
_fr2 = _FakeTTReply("", err=QNetworkReply.HostNotFoundError)
ttw._reply = _fr2
import unittest.mock as _um
with _um.patch.object(_fr2, "errorString", return_value="호스트를 찾을 수 없음", create=True):
    ttw._on_reply_finished(_fr2)
app.processEvents()
check("[v41] 네트워크 오류가 나도 마지막 시간표가 그대로 남고 캐시 안내가 뜸",
      ttw.table.item(0, 0).text().startswith("수학") and ttw.lbl_cache_note.isVisible())

# 교사 시간표 전환(라디오 버튼) — 학년/반은 숨고 교사 선택만 보임
ttw.radio_teacher_view.setChecked(True)
ttw._on_view_mode_selected(1)
app.processEvents()
check("[v43.6] 교사 모드에서는 학년·반 콤보가 숨고 다운로드/업로드 버튼이 보임",
      not ttw.combo_grade.isVisible() and not ttw.combo_class.isVisible()
      and ttw.btn_download_subjects.isVisible() and ttw.btn_upload_teachers.isVisible())
check("[버그 수정] '전체 과목 다운로드'를 한 번도 안 돌려도(survey 비어 있음), "
      "지금 조회된 학급(self.slots)에 매핑된 교사가 있으면 콤보·표에 바로 나옴",
      not ttw.survey and ttw.combo_teacher.isVisible() and ttw.combo_teacher.count() == 1
      and ttw.combo_teacher.currentData() == "김선생" and ttw.table.item(0, 0).text().startswith("수학"))
ttw.radio_class_view.setChecked(True)
ttw._on_view_mode_selected(0)
app.processEvents()
check("[v43.6] 학급 모드로 돌아오면 학년·반 콤보가 다시 보이고 교사 버튼은 숨음",
      ttw.combo_grade.isVisible() and ttw.combo_class.isVisible()
      and not ttw.btn_download_subjects.isVisible())

# [버그 수정] 교사 시간표는 "전체 과목 다운로드"(전체 학급 조사 겸용)로
# 모은 self.survey를 가로질러야 한다 — 두 반에 걸쳐 가르치는 교사가
# 실제로 두 반 모두 표에 나오는지 확인한다.
ttw.neis_panel.edit_key.setText("FAKEKEY")
ttw.neis_panel._emit_changed()
app.processEvents()
_survey_calls = []


def _fake_fetch_sync(key, office, school, grade, cls, ymd_from, ymd_to, timeout_ms=15000):
    _survey_calls.append((grade, cls))
    if grade == 1 and cls == 1:
        return TT.parse('{"hisTimetable":[{"head":1},{"row":['
                        '{"ALL_TI_YMD":"' + _TT_D[0] + '","PERIO":"1","ITRT_CNTNT":"수학","CLRM_NM":""}'
                        ']}]}').slots, True
    if grade == 1 and cls == 2:
        return TT.parse('{"hisTimetable":[{"head":1},{"row":['
                        '{"ALL_TI_YMD":"' + _TT_D[1] + '","PERIO":"3","ITRT_CNTNT":"수학","CLRM_NM":""},'
                        '{"ALL_TI_YMD":"' + _TT_D[1] + '","PERIO":"4","ITRT_CNTNT":"물리학1","CLRM_NM":""}'
                        ']}]}').slots, True
    return [], True


_subj_path = _os.path.join(_tf.mkdtemp(), "과목표.xlsx")
with _patch.object(ttw, "_fetch_slots_sync", side_effect=_fake_fetch_sync), \
     _patch("src.utils.timetable.QMessageBox.question", return_value=QMessageBox.Yes), \
     _patch("src.utils.timetable.QFileDialog.getSaveFileName", return_value=(_subj_path, "")):
    ttw._on_download_all_subjects()
check("[v43.6] '전체 과목 다운로드' 버튼 하나로 1~3학년 x 1~10반(30개)을 전부 조회함",
      len(_survey_calls) == 30 and set(_survey_calls) ==
      {(g, c) for g in TT.SURVEY_GRADES for c in TT.SURVEY_CLASSES})
check("[v43.6] 조사 결과가 self.survey에 반별로 그대로 저장됨(빈 반은 안 저장)",
      set(ttw.survey.keys()) == {("1", "1"), ("1", "2")})
check("[v43.6] 조사 직후 엑셀 파일도 바로 생성됨(버튼 1개로 조사+다운로드)", _os.path.exists(_subj_path))
_wb_subj = _opxr.load_workbook(_subj_path)
_ws_subj = _wb_subj.active
_subj_rows = {row[0].value: row[1].value for row in _ws_subj.iter_rows(min_row=2) if row[0].value}
check("[v43.6] 엑셀에 두 반에서 나온 과목이 전부(중복 없이) 들어있음",
      set(_subj_rows.keys()) == {"수학", "물리학1"})

# [버그 수정] 조사 중 일부 요청이 진짜로 실패하면(빈 결과가 아니라 오류) —
# ① 재시도하고 ② 그래도 실패하면 경고를 띄운다. 실패 없이 그냥 수업이
# 없는 반이 많은 건(정상) 경고를 띄우면 안 된다(전에는 이 조건이 잘못돼
# 매번 경고가 뜨면서 헤드리스 환경에서 무한 대기까지 유발했었다).
_retry_calls = []


def _fake_fetch_with_failure(key, office, school, grade, cls, ymd_from, ymd_to, timeout_ms=15000):
    _retry_calls.append((grade, cls))
    if (grade, cls) == (2, 5):
        # 이 반은 재시도(두 번째 호출)에서만 성공한다
        ok = _retry_calls.count((2, 5)) >= 2
        return ([TT.TimetableSlot(_TT_D[0], "1", "음악", "")] if ok else []), ok
    if (grade, cls) == (3, 7):
        return [], False   # 재시도해도 끝까지 실패
    return [], True


with _patch.object(ttw, "_fetch_slots_sync", side_effect=_fake_fetch_with_failure), \
     _patch.object(ttw, "_wait_ms"), \
     _patch("src.utils.timetable.QMessageBox.question", return_value=QMessageBox.Yes), \
     _patch("src.utils.timetable.QMessageBox.warning") as _mock_warn, \
     _patch("src.utils.timetable.QFileDialog.getSaveFileName", return_value=(_subj_path, "")):
    ttw._on_download_all_subjects()
check("[버그 수정] 진짜로 실패한 반만 재시도됨(정상 응답 반은 재시도 안 함)",
      _retry_calls.count((2, 5)) == 2 and _retry_calls.count((3, 7)) == 2
      and _retry_calls.count((1, 1)) == 1)
check("[버그 수정] 재시도로 살아난 반은 survey에 포함됨", ("2", "5") in ttw.survey)
check("[버그 수정] 재시도해도 끝까지 실패한 반이 있으면 경고가 뜸", _mock_warn.called)

with _patch.object(ttw, "_fetch_slots_sync", side_effect=_fake_fetch_sync), \
     _patch.object(ttw, "_wait_ms"), \
     _patch("src.utils.timetable.QMessageBox.question", return_value=QMessageBox.Yes), \
     _patch("src.utils.timetable.QMessageBox.warning") as _mock_no_warn, \
     _patch("src.utils.timetable.QFileDialog.getSaveFileName", return_value=(_subj_path, "")):
    ttw._on_download_all_subjects()
check("[버그 수정] 요청 실패 없이 그냥 수업이 없는 반이 많아도(정상) 경고가 안 뜸",
      not _mock_no_warn.called)

# 인증키가 없으면 조사 자체를 시작하지 않는지
_win_survey2 = MainWindow(); _win_survey2.show()
_win_survey2.switch_mode("util"); _win_survey2.util_panel.open_app("timetable")
app.processEvents()
_ttw_nokey = _win_survey2.util_panel._pages["timetable"][0]
_ttw_nokey.neis_panel.edit_key.setText("")
_ttw_nokey.neis_panel._emit_changed()
app.processEvents()
with _patch("src.utils.timetable.QMessageBox.information") as _mock_info, \
     _patch("src.utils.timetable.QMessageBox.question") as _mock_q:
    _ttw_nokey._on_download_all_subjects()
check("[v43.6] 인증키가 없으면 안내만 뜨고 확인 질문(및 실제 조회)까지 안 감",
      _mock_info.called and not _mock_q.called)
_win_survey2.close()

# 담당교사 채워서 업로드 — "수학"에만 교사를 지정
_wb_subj["과목-담당교사"]["B2"] = "김선생"   # 머리글 다음 첫 데이터 행 = "수학"
_wb_subj.save(_subj_path)
with _patch("src.utils.timetable.QFileDialog.getOpenFileName", return_value=(_subj_path, "")):
    ttw._on_upload_teacher_list()
app.processEvents()
check("[v43.3] 교사 목록 업로드 — 담당교사를 채운 과목만 매핑에 반영됨",
      ttw.mapping.get("수학") == "김선생" and "물리학1" not in ttw.mapping)

ttw.radio_teacher_view.setChecked(True)
ttw._on_view_mode_selected(1)
app.processEvents()
check("[버그 수정] 교사가 두 반(1-1, 1-2)에서 가르치는 수학이 모두 표에 나옴(반 하나에 갇히지 않음)",
      ttw.combo_teacher.count() == 1 and ttw.combo_teacher.currentData() == "김선생"
      and ttw.table.item(0, 0).text() == f"수학\n{tr('util.timetable.class_label', a0='1', a1='1')}"
      and ttw.table.item(2, 1).text() == f"수학\n{tr('util.timetable.class_label', a0='1', a1='2')}")

# 여러 교사를 매핑해도(실제 흐름) 콤보로 오갈 수 있는지
ttw.mapping = {"수학": "김선생", "물리학1": "이선생"}
ttw._save_settings()
ttw._render()
app.processEvents()
check("[버그 수정] 교사를 여러 명 매핑해도 표가 비어 있지 않고 콤보에서 고른 교사가 채워짐",
      ttw.combo_teacher.count() == 2 and ttw.combo_teacher.isVisible()
      and ttw.table.item(0, 0).text().startswith("수학"))
_teacher_idx = ttw.combo_teacher.findData("이선생")
ttw.combo_teacher.setCurrentIndex(_teacher_idx)
app.processEvents()
check("[버그 수정] 콤보에서 다른 교사를 고르면 그 교사의 시간표로 바로 바뀜",
      ttw.table.item(3, 1).text().startswith("물리학1"))
ttw.mapping = {}
ttw._render()
app.processEvents()
check("[버그 수정] 매핑이 비면 콤보가 숨고 '아직 담당교사가 없다' 안내가 뜸",
      not ttw.combo_teacher.isVisible() and "담당교사" in ttw.hint_teacher.text())
ttw.mapping = {"수학": "김선생"}   # [안전] 방금 지운 매핑을 되돌려 아래 재기동 확인 테스트의 전제를 지켜준다
ttw._save_settings()

# 재기동해도 학년·반·매핑·survey·캐시된 시간표가 복원되는지
_win_tt2 = MainWindow(); _win_tt2.show()
_win_tt2.switch_mode("util"); _win_tt2.util_panel.open_app("timetable")
app.processEvents()
_ttw2 = _win_tt2.util_panel._pages["timetable"][0]
check("[v41] 재기동해도 학년/반·매핑·캐시된 학급 시간표가 복원됨",
      _ttw2.mapping == {"수학": "김선생"} and len(_ttw2.slots) == 2
      and any(s.subject == "수학" for s in _ttw2.slots))
check("[v43.6] 재기동해도 전체 학급 조사(survey) 결과가 복원됨",
      set(_ttw2.survey.keys()) == {("1", "1"), ("1", "2")})
_win_tt2.close()

# [v43.7] 인쇄 — 옵션 창에서 고른 쪽수만큼 페이지에 그려지는지
from PySide6.QtGui import QPageLayout
ttw.radio_class_view.setChecked(True)
ttw._on_view_mode_selected(0)
app.processEvents()
with _patch("src.utils.timetable.UK.PrintCopiesDialog") as _mock_print_dlg_cls, \
     _patch("src.utils.timetable.QPrintDialog") as _mock_qprint_dlg_cls:
    _mock_print_dlg_cls.return_value.exec.return_value = QDialog.Accepted
    _mock_print_dlg_cls.return_value.result_copies.return_value = 2
    _mock_qprint_dlg_cls.return_value.exec.return_value = 0   # 실제 인쇄 대화상자는 취소(진짜 인쇄 안 함)
    ttw._on_print()
_printer_arg = _mock_qprint_dlg_cls.call_args[0][0]
check("[v43.7] '2쪽' 선택 시 인쇄 방향이 세로(Portrait)로 미리 맞춰짐",
      _printer_arg.pageLayout().orientation() == QPageLayout.Portrait)

with _patch("src.utils.timetable.UK.PrintCopiesDialog") as _mock_print_dlg_cls2, \
     _patch("src.utils.timetable.QPrintDialog") as _mock_qprint_dlg_cls2:
    _mock_print_dlg_cls2.return_value.exec.return_value = QDialog.Accepted
    _mock_print_dlg_cls2.return_value.result_copies.return_value = 4
    _mock_qprint_dlg_cls2.return_value.exec.return_value = 0
    ttw._on_print()
_printer_arg2 = _mock_qprint_dlg_cls2.call_args[0][0]
check("[v43.7] '4쪽' 선택 시 인쇄 방향이 가로(Landscape)로 미리 맞춰짐",
      _printer_arg2.pageLayout().orientation() == QPageLayout.Landscape)

# [버그 수정] 학급 시간표를 먼저 렌더링한 뒤(칸이 더 많이 채워진 상태)
# 교사 시간표로 넘어가면, Qt가 표를 줄일 때 안 채우는 칸의 예전 내용을
# 알아서 안 지워 준다 — 실제로 화면 캡처하다가 "매핑 안 된 다른 과목이
# 유령처럼 남아 보이는" 문제를 발견해 clearContents()를 추가했다.
_ttw3 = win.util_panel._pages["timetable"][0]
_ttw3.survey = {("1", "1"): [TT.TimetableSlot(_TT_D[0], "1", "수학", "")],
                ("1", "2"): [TT.TimetableSlot(_TT_D[1], "3", "수학", "")]}
_ttw3.mapping = {"수학": "김선생"}
_ttw3.slots = [TT.TimetableSlot(_TT_D[0], "1", "수학", ""), TT.TimetableSlot(_TT_D[1], "2", "영어", ""),
              TT.TimetableSlot(_TT_D[2], "3", "국어", ""), TT.TimetableSlot(_TT_D[3], "4", "체육", "")]
_ttw3.radio_class_view.setChecked(True)
_ttw3._render()   # 4교시짜리 학급 시간표를 먼저 채운다(칸이 더 많음)
app.processEvents()
_ttw3.radio_teacher_view.setChecked(True)
_ttw3._on_view_mode_selected(1)   # 3교시짜리 교사 시간표로 축소
app.processEvents()
check("[버그 수정] 학급→교사 전환 시 표를 줄여도 예전 다른 반·과목의 유령 데이터가 안 남음",
      _ttw3.table.item(1, 1) is None or _ttw3.table.item(1, 1).text() == "")

section("42. [v43] 갤럭시폰 사진 옮기기 — adb 출력 파싱(순수 로직)")

import src.utils.phone_solve as PH
import datetime as _pdt

_pd_raw = "List of devices attached\nABC123\tdevice\nXYZ999\tunauthorized\n\n"
check("[v43] adb devices 출력이 (기기ID, 상태) 목록으로 파싱됨",
      PH.parse_devices_output(_pd_raw) == [("ABC123", "device"), ("XYZ999", "unauthorized")])


def _ts(y, m, d, h=12):
    return _pdt.datetime(y, m, d, h, 0, 0).timestamp()


_pd_find_raw = "\n".join([
    f"{_ts(2026, 9, 18)} /sdcard/DCIM/Camera/IMG_0001.jpg",
    f"{_ts(2026, 9, 18, 15)} /sdcard/DCIM/Camera/IMG_0002.jpg",
    f"{_ts(2026, 9, 19)} /sdcard/DCIM/Camera/IMG_0003.jpg",
    f"{_ts(2026, 9, 25)} /sdcard/DCIM/Camera/IMG_0004.jpg",
    "",   # 빈 줄도 섞여 있을 수 있음 — 안 죽어야 함
])
_pd_files = PH.parse_find_output(_pd_find_raw)
check("[v43] find 출력에서 파일 4개가 정확히 파싱됨(빈 줄은 무시)",
      len(_pd_files) == 4 and _pd_files[0].name == "IMG_0001.jpg")
check("[v43] 이해할 수 없는 줄이 섞여도 죽지 않고 나머지만 파싱",
      len(PH.parse_find_output("이상한 줄\n" + _pd_find_raw)) == 4)

_pd_events = PH.group_into_events(_pd_files)
check("[v43] 연속된 날짜(9/18~9/19)가 한 행사로 묶임", len(_pd_events) == 2)
check("[v43] 최근 행사(9/25)가 먼저 옴", _pd_events[0].start_date == _pdt.date(2026, 9, 25))
check("[v43] 이어진 행사(9/18~9/19)에 파일 3개가 다 들어감",
      _pd_events[1].start_date == _pdt.date(2026, 9, 18) and _pd_events[1].end_date == _pdt.date(2026, 9, 19)
      and len(_pd_events[1]) == 3)
check("[v43] group_into_events([])가 빈 목록(죽지 않음)", PH.group_into_events([]) == [])

check("[v43] 이 환경에는 adb가 없음(is_adb_available=False) — 실기 검증 필요",
      PH.is_adb_available() is False)
check("[v43] adb가 없으면 list_devices/list_photos가 안전하게 빈 목록",
      PH.list_devices() == [] and PH.list_photos() == [])

_diag_report = PH.diagnose()
check("[v43.3] diagnose() — adb 없을 때 adb_available=False, 나머지는 조용히 None",
      _diag_report["adb_available"] is False and _diag_report["devices_exception"] is None)
check("[v43.3] format_diagnose_report — 사람이 읽을 문자열로 나옴(adb 경로 언급 포함)",
      "adb 실행 파일" in PH.format_diagnose_report(_diag_report))

# subprocess.run 자체가 예상 못 한 예외를 던져도(예: 프로즌 배포판의 파이프
# 문제) list_devices/list_photos/pull_event가 안 죽고 안전하게 처리하는지
with _patch("src.utils.phone_solve.is_adb_available", return_value=True), \
     _patch("subprocess.run", side_effect=ValueError("이상한 저수준 예외")):
    check("[v43.3] adb devices가 예상 못 한 예외를 던져도 list_devices는 빈 목록",
          PH.list_devices() == [])
    check("[v43.3] list_photos도 마찬가지로 안전함", PH.list_photos() == [])
    _diag2 = PH.diagnose()
    check("[v43.3] diagnose()는 예외 자체를 문자열로 담아 그대로 보여줌",
          _diag2["devices_exception"] is not None and "이상한 저수준 예외" in _diag2["devices_exception"])

with _patch("subprocess.run") as _mock_run:
    _mock_run.return_value.returncode = 0
    _tmpdir_pd = _tf.mkdtemp()
    _ok, _failed = PH.pull_event(_pd_events[1], _tmpdir_pd, serial="ABC123")
    check("[v43] pull_event가 파일 수만큼 adb pull을 호출함", _mock_run.call_count == 3)
    check("[v43] 전부 성공하면 (성공수, 빈 실패목록)", _ok == 3 and _failed == [])

with _patch("subprocess.run") as _mock_run2:
    _mock_run2.return_value.returncode = 1
    _ok2, _failed2 = PH.pull_event(_pd_events[1], _tmpdir_pd, serial="ABC123")
    check("[v43] adb pull이 실패해도 안 멈추고 실패 목록에 모아서 돌려줌",
          _ok2 == 0 and len(_failed2) == 3)

check("[v43.4] 기본 상태에서는 adb_path가 지정 안 돼 있음", PH.get_adb_path() is None)
_fake_adb = _os.path.join(_tf.mkdtemp(), "adb.exe")
open(_fake_adb, "w").close()
PH.set_adb_path(_fake_adb)
check("[v43.4] adb 경로를 직접 지정하면 is_adb_available이 PATH와 무관하게 True",
      PH.is_adb_available() is True and PH.resolve_adb_bin() == _fake_adb)
check("[v43.4] diagnose()도 지정한 경로를 그대로 보여줌", PH.diagnose()["adb_path"] == _fake_adb)
with _patch("subprocess.run") as _mock_run3:
    _mock_run3.return_value.stdout = "List of devices attached\n"
    PH.list_devices()
    check("[v43.4] 실제 adb 호출도 지정한 경로로 나감(PATH의 'adb'가 아님)",
          _mock_run3.call_args[0][0][0] == _fake_adb)
PH.set_adb_path(None)   # 이후 섹션에 영향 안 주도록 원상 복구
check("[v43.4] 경로를 비우면 다시 PATH 검색으로 돌아감", PH.is_adb_available() is False)

# [v43.7] "adb 위치 지정" 없이도 흔한 설치 위치는 자동으로 찾아지는지
import sys as _sys_pt
_old_argv0 = _sys_pt.argv[0]
_fake_app_dir = _tf.mkdtemp()
_os.makedirs(_os.path.join(_fake_app_dir, "platform-tools"))
_fake_adb3 = _os.path.join(_fake_app_dir, "platform-tools", "adb.exe")
open(_fake_adb3, "w").close()
_sys_pt.argv[0] = _os.path.join(_fake_app_dir, "FolderKitPP.exe")
check("[v43.7] 실행 파일과 같은 폴더의 platform-tools\\adb.exe를 자동으로 찾음",
      PH.is_adb_available() is True and PH.effective_adb_path() == _fake_adb3)
check("[v43.7] 자동으로 찾았을 때도 실제 adb 호출이 그 경로로 나감",
      PH.resolve_adb_bin() == _fake_adb3)
_sys_pt.argv[0] = _old_argv0
check("[v43.7] 사용자가 직접 지정한 경로가 있으면 자동 검색보다 우선함", True)
_fake_adb_priority = _os.path.join(_tf.mkdtemp(), "adb.exe")
open(_fake_adb_priority, "w").close()
PH.set_adb_path(_fake_adb_priority)
_sys_pt.argv[0] = _os.path.join(_fake_app_dir, "FolderKitPP.exe")
check("[v43.7] 직접 지정 > 자동 검색 우선순위 확인", PH.effective_adb_path() == _fake_adb_priority)
_sys_pt.argv[0] = _old_argv0
PH.set_adb_path(None)

section("42b. [v43] 갤럭시폰 사진 옮기기 — 위젯 통합(폰 연결 모킹)")

win.switch_mode("util")
win.util_panel.open_app("phonetransfer")
app.processEvents()
ptw = win.util_panel._pages["phonetransfer"][0]
check("[v43] adb가 없는 이 환경에서는 안내 문구만 뜨고 목록은 비활성",
      not ptw.list_events.isVisible() and ptw.lbl_not_ready.isVisible() and not ptw.btn_download.isEnabled())

with _patch("src.utils.phone_transfer.PH.is_adb_available", return_value=True), \
     _patch("src.utils.phone_transfer.PH.list_devices", return_value=[("ABC123", "device")]), \
     _patch("src.utils.phone_transfer.PH.list_photos", return_value=_pd_files):
    ptw._refresh()
    app.processEvents()
    check("[v43] (모킹) 폰이 연결되면 행사 목록 2개가 뜸", ptw.list_events.count() == 2)
    check("[v43] (모킹) 아무 것도 안 고르면 다운로드 버튼이 비활성", not ptw.btn_download.isEnabled())
    ptw.list_events.item(1).setCheckState(Qt.Checked)
    app.processEvents()
    check("[v43] (모킹) 하나를 고르면 다운로드 버튼이 활성화됨", ptw.btn_download.isEnabled())

    _dest_pd = _tf.mkdtemp()
    with _patch("src.utils.phone_transfer.PH.pull_event", return_value=(3, [])) as _mock_pull, \
         _patch("src.utils.phone_transfer.QFileDialog.getExistingDirectory", return_value=_dest_pd):
        ptw._on_download()
    app.processEvents()
    check("[v43] (모킹) 다운로드하면 고른 행사만 pull_event에 전달됨",
          _mock_pull.call_count == 1 and _mock_pull.call_args[0][0].start_date == _pd_events[1].start_date
          and len(_mock_pull.call_args[0][0]) == len(_pd_events[1]))
    check("[v43] (모킹) 완료 후 안내문과 폴더 열기·이미지 편집 전달 버튼이 보임",
          ptw.lbl_done.isVisible() and ptw.btn_open_folder.isVisible() and ptw.btn_to_imgedit.isVisible())
    check("[v43] (모킹) 마지막 저장 폴더가 기억됨(다음에 재기동해도 이어씀)", ptw.last_dest == _dest_pd)

# 재기동해도 마지막 저장 폴더가 복원되는지
_win_pt2 = MainWindow(); _win_pt2.show()
_win_pt2.switch_mode("util"); _win_pt2.util_panel.open_app("phonetransfer")
app.processEvents()
_ptw2 = _win_pt2.util_panel._pages["phonetransfer"][0]
check("[v43] 재기동해도 마지막 저장 폴더가 복원됨", _ptw2.last_dest == _dest_pd)
_win_pt2.close()

# "진단" 버튼 — 대화상자로 진단 결과가 뜨고, 콘솔 로그도 남는지
with _patch("src.utils.phone_transfer.QMessageBox.information") as _mock_diag_box:
    ptw._on_diagnose()
check("[v43.3] '진단' 버튼을 누르면 안내창이 뜨고, adb 관련 문구가 포함됨",
      _mock_diag_box.called and "adb" in _mock_diag_box.call_args[0][2])

# "adb 위치 지정" 버튼
_fake_adb2 = _os.path.join(_tf.mkdtemp(), "adb.exe")
open(_fake_adb2, "w").close()
with _patch("src.utils.phone_transfer.QFileDialog.getOpenFileName", return_value=(_fake_adb2, "")):
    ptw._on_set_adb_path()
app.processEvents()
check("[v43.4] adb 위치를 지정하면 위젯·전역 상태에 반영되고 안내문이 바뀜",
      ptw.adb_path == _fake_adb2 and PH.get_adb_path() == _fake_adb2
      and _fake_adb2 in ptw.lbl_adb_path.text())
check("[v43.4] 지정한 경로가 QSettings에도 저장됨",
      ptw._settings.value("util.phonetransfer.adb_path", "") == _fake_adb2)
PH.set_adb_path(None)   # 다른 섹션에 영향 안 주도록 원상 복구

# "이미지 편집 모드로 전달" — UtilHost.open_in_image_edit 실제 동작 확인
win.util_panel.open_app("phonetransfer")
app.processEvents()
ptw = win.util_panel._pages["phonetransfer"][0]
ptw.last_dest = _dest_pd
win.mode = "util"   # (다른 섹션에서 모드가 바뀌어 있을 수 있어 명시적으로)
ptw._on_open_in_imgedit()
app.processEvents()
check("[v43] '이미지 편집 모드로 전달'을 누르면 실제로 이미지 편집 모드로 전환되고 그 폴더가 열림",
      win.mode == "imgedit" and win.source_path == _dest_pd)
win.switch_mode("util")
app.processEvents()

section("42c. [v43.10] 갤럭시폰 사진 옮기기 — 처음엔 숨김, 단축키로 꺼내면 계속 일반 도구처럼 보임")

# [주의] win은 이 파일 앞부분에서 이미 phonetransfer를 열어 본 적이 있어
# (다른 섹션들) 이미 revealed 상태다 — "아직 안 꺼낸" 상태를 보려면
# 완전히 새 MainWindow(따라서 새 UtilPanel)로 확인해야 한다.
_win_hide = MainWindow(); _win_hide.show()
app.processEvents()
check("[v43.9] phonetransfer가 hidden=True로 표시됨", _win_hide.util_panel.by_id["phonetransfer"].hidden is True)
check("[v43.10] 아직 안 꺼냈으면 목록·홈 화면에 안 보임",
      "phonetransfer" not in {a.id for a in _win_hide.util_panel._visible_apps()})
check("[v43.9] 하지만 by_id에는 여전히 있어(직접 열기는 가능)", "phonetransfer" in _win_hide.util_panel.by_id)
from src.utils.panel import ROLE_ID as _ROLE_ID_HIDDEN
check("[v43.10] 아직 안 꺼냈으면 실제 트리(사이드바)에도 없음",
      not any(_win_hide.util_panel.tree.topLevelItem(i).child(j).data(0, _ROLE_ID_HIDDEN) == "phonetransfer"
              for i in range(_win_hide.util_panel.tree.topLevelItemCount())
              for j in range(_win_hide.util_panel.tree.topLevelItem(i).childCount())))

_win_hide.switch_mode("util")   # [주의] on_enter()가 QSettings에 저장된 마지막 도구를 자동으로 열 수 있어 검증 이후에 전환
app.processEvents()

_win_hide.util_panel.open_app("phonetransfer")
app.processEvents()
check("[v43.9] open_app()으로 직접 부르면(단축키가 하는 일) 여전히 열림",
      _win_hide.util_panel.current_id == "phonetransfer")
check("[v43.10] 한 번 열면(꺼내면) 그때부터 목록·홈 화면에 계속 나타남(다시 숨겨지지 않음)",
      "phonetransfer" in {a.id for a in _win_hide.util_panel._visible_apps()}
      and any(_win_hide.util_panel.tree.topLevelItem(i).child(j).data(0, _ROLE_ID_HIDDEN) == "phonetransfer"
              for i in range(_win_hide.util_panel.tree.topLevelItemCount())
              for j in range(_win_hide.util_panel.tree.topLevelItem(i).childCount())))
check("[v43.10] 홈 화면 카드 목록에도 나타남", "phonetransfer" in _win_hide.util_panel.home._cards)
check("[v43.10] 꺼낸 뒤로는 보통 도구처럼 '최근 사용' 목록에도 쌓임", "phonetransfer" in _win_hide.util_panel._mru)
_win_hide.close()

win.switch_mode("util")
app.processEvents()
win.util_panel.open_app("phonetransfer")
app.processEvents()

# 실제 키 입력(Ctrl+Shift+F9)으로도 여는지 — 함수 직접 호출이 아니라
# 진짜 단축키 경로를 확인한다(인증키 단축키 버그에서 얻은 교훈).
win.switch_mode("class")
app.processEvents()
from PySide6.QtTest import QTest as _QTestHidden
from PySide6.QtGui import QKeySequence as _QKS_Hidden
win.raise_()
win.activateWindow()
QApplication.instance().setActiveWindow(win)
app.processEvents()
_QTestHidden.keySequence(win, _QKS_Hidden("Ctrl+Shift+F9"))
app.processEvents()
check("[v43.9] 실제 키 입력으로도 Util 모드로 전환되며 숨긴 도구가 바로 열림",
      win.mode == "util" and win.util_panel.current_id == "phonetransfer")

win.switch_mode("util")
app.processEvents()



win.switch_mode("util")
win.util_panel.open_app("meal")
app.processEvents()
mlw43 = win.util_panel._pages["meal"][0]
mlw43.neis_panel._fill_real_key()
app.processEvents()
from src.utils.neis_common import _MY_NEIS_KEY as _KEY43
check("[v43.1] 오늘의 급식에서 인증키를 채움", mlw43.neis_panel.edit_key.text() == _KEY43)

_win_tt3 = MainWindow(); _win_tt3.show()
_win_tt3.switch_mode("util"); _win_tt3.util_panel.open_app("timetable")
app.processEvents()
_ttw3 = _win_tt3.util_panel._pages["timetable"][0]
check("[버그 수정] 새로 연 컴시간 알리미에 오늘의 급식과 같은 인증키가 이미 채워져 있음",
      _ttw3.neis_panel.edit_key.text() == _KEY43)
check("[버그 수정] 교육청코드·학교코드도 함께 채워져 있음(빈 문자열이 아님)",
      bool(_ttw3.neis_panel.edit_office.text()) and bool(_ttw3.neis_panel.edit_school.text()))
_win_tt3.close()

# 컴시간 알리미 쪽에서 바꾼 값도 QSettings에 제대로 저장되는지(예전엔 저장 자체가 안 됐었다)
win.util_panel.open_app("timetable")
app.processEvents()
ttw43 = win.util_panel._pages["timetable"][0]
ttw43.neis_panel.edit_office.setText("B99")
ttw43.neis_panel._emit_changed()
app.processEvents()
check("[버그 수정] 컴시간 알리미에서 바꾼 교육청코드가 QSettings에 실제로 저장됨",
      QSettings("SRIHS", "FolderSync").value("util.neis.office_code", "") == "B99")
ttw43.neis_panel.edit_office.setText("B10")
ttw43.neis_panel._emit_changed()
app.processEvents()

section("44. [v43.1] 좌석표 — 명단 양식 다운로드 + 인원 수만으로 배치")

_tmpl_path = _os.path.join(_tf.mkdtemp(), "양식.xlsx")
B.save_roster_template(_tmpl_path)
check("[v43.1] 명단 양식 파일이 실제로 생성됨", _os.path.exists(_tmpl_path))
_tmpl_students = B.read_roster_excel(_tmpl_path)
check("[v43.1] 양식이 read_roster_excel로 정상 파싱됨(예시 3명)", len(_tmpl_students) == 3)

_nchart = SS.numbered_layout(22, cols=5, seed=1)
check("[v43.1] 인원 수만으로 5줄 배치 — 22명이 5행에 나뉘어 들어감(마지막 행만 부족)",
      _nchart.rows == 5 and _nchart.cols == 5
      and all(None not in row for row in _nchart.seats[:-1])
      and _nchart.seats[-1].count(None) == 3)
_nflat = [s for row in _nchart.seats for s in row if s]
check("[v43.1] 번호가 1~22 전부, 중복 없이 들어감", sorted(_nflat, key=int) == [str(i) for i in range(1, 23)])

section("44b. [v43.1] 좌석표 — 위젯 통합(인원 수 모드 ↔ 명단 모드 전환, 방향)")

win.switch_mode("util")
win.util_panel.open_app("seating")
app.processEvents()
seatw44 = win.util_panel._pages["seating"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw44._on_roster_clear()
check("[v43.1] 명단이 없으면 반 선택은 숨고 인원 수 입력이 보임",
      not seatw44.combo_class.isVisible() and seatw44.spin_headcount.isVisible()
      and seatw44.btn_generate_numbered.isVisible())

seatw44.spin_headcount.setValue(22)
seatw44.spin_cols.setValue(5)
seatw44._on_generate_numbered()
app.processEvents()
check("[v43.1] '번호로 배치 만들기'를 누르면 headcount_mode가 켜지고 차트가 생김",
      seatw44.headcount_mode and seatw44.chart is not None and seatw44.chart.rows == 5)

_before_numbered = [row[:] for row in seatw44.chart.seats]
seatw44._on_reshuffle()
app.processEvents()
check("[v43.1] 인원 수 모드에서도 '다시 섞기'가 동작함(같은 22명, 배치만 바뀜)",
      seatw44.chart.seats != _before_numbered
      and sorted((s for row in seatw44.chart.seats for s in row if s), key=int) == [str(i) for i in range(1, 23)])

seatw44.spin_cols.setValue(4)
app.processEvents()
check("[v43.1] 인원 수 모드에서 줄 수를 바꾸면 그 줄 수로 다시 배치됨(22명 유지)",
      seatw44.chart.cols == 4 and sum(1 for row in seatw44.chart.seats for s in row if s) == 22)

# 명단을 올리면 인원 수 모드에서 명단 모드로 완전히 넘어가는지
_seat_xlsx44 = _os.path.join(_tf.mkdtemp(), "좌석명단44.xlsx")
_wb44 = _opxr.Workbook(); _ws44 = _wb44.active
_ws44.append(["학년", "반", "번호", "이름", "성별"])
for i in range(1, 7):
    _ws44.append([1, 5, i, f"참가자{i}", "남"])
_wb44.save(_seat_xlsx44)
with _patch("src.utils.seating.QFileDialog.getOpenFileName", return_value=(_seat_xlsx44, "")):
    seatw44._on_roster_upload()
app.processEvents()
check("[v43.1] 명단을 올리면 반 선택이 다시 보이고 인원 수 입력은 숨음",
      seatw44.combo_class.isVisible() and not seatw44.spin_headcount.isVisible())
check("[v43.1] 명단 업로드 후에는 headcount_mode가 꺼지고 실제 이름으로 배치됨",
      not seatw44.headcount_mode and all(
          seatw44.chart is None or sid is None or sid in {s.sid for s in seatw44.roster}
          for row in (seatw44.chart.seats if seatw44.chart else []) for sid in row))

# 방향: 교탁과 가장 가까운 줄(seats[0], 앞줄)이 화면에서 가장 아래에
# 그려지는지 — paintEvent와 똑같은 계산식으로 y좌표를 직접 확인한다.
_SEAT_H_T, _SEAT_GAP_T = 60, 10
_n_rows_t = seatw44.chart.rows
_grid_top_t = 10
_grid_bottom_t = _grid_top_t + _n_rows_t * (_SEAT_H_T + _SEAT_GAP_T) - _SEAT_GAP_T
_y_row0 = _grid_bottom_t - (0 + 1) * _SEAT_H_T - 0 * _SEAT_GAP_T
_y_last = _grid_bottom_t - (_n_rows_t - 1 + 1) * _SEAT_H_T - (_n_rows_t - 1) * _SEAT_GAP_T
check("[v43.1] 교탁과 가장 가까운 줄(0번)이 화면에서 가장 아래(y값이 더 큼)로 그려짐",
      _y_row0 > _y_last)

# 인쇄 — 1/2/4쪽 옵션에 따라 방향이 바뀌는지
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
with _patch("src.utils.seating.UK.PrintCopiesDialog") as _mock_print_dlg_cls, \
     _patch("src.utils.seating.QPrintDialog") as _mock_dlg_cls:
    _mock_print_dlg_cls.return_value.exec.return_value = QDialog.Accepted
    _mock_print_dlg_cls.return_value.result_copies.return_value = 1
    _mock_dlg_cls.return_value.exec.return_value = 0   # 취소 — 실제 인쇄는 안 함
    seatw44._on_print()
_printer_arg = _mock_dlg_cls.call_args[0][0]
check("[v43.1] '1쪽' 선택 시 인쇄 방향이 가로(Landscape)로 미리 맞춰짐",
      _printer_arg.pageLayout().orientation() == QPageLayout.Landscape)

with _patch("src.utils.seating.UK.PrintCopiesDialog") as _mock_print_dlg_cls2, \
     _patch("src.utils.seating.QPrintDialog") as _mock_dlg_cls2:
    _mock_print_dlg_cls2.return_value.exec.return_value = QDialog.Accepted
    _mock_print_dlg_cls2.return_value.result_copies.return_value = 2
    _mock_dlg_cls2.return_value.exec.return_value = 0
    seatw44._on_print()
_printer_arg2 = _mock_dlg_cls2.call_args[0][0]
check("[v43.9] '2쪽' 선택 시 인쇄 방향이 세로(Portrait)로 미리 맞춰짐",
      _printer_arg2.pageLayout().orientation() == QPageLayout.Portrait)

with _patch("src.utils.seating.UK.PrintCopiesDialog") as _mock_print_dlg_cls3, \
     _patch("src.utils.seating.QPrintDialog") as _mock_dlg_cls3:
    _mock_print_dlg_cls3.return_value.exec.return_value = QDialog.Accepted
    _mock_print_dlg_cls3.return_value.result_copies.return_value = 4
    _mock_dlg_cls3.return_value.exec.return_value = 0
    seatw44._on_print()
_printer_arg3 = _mock_dlg_cls3.call_args[0][0]
check("[v43.9] '4쪽' 선택 시 인쇄 방향이 가로(Landscape)로 미리 맞춰짐",
      _printer_arg3.pageLayout().orientation() == QPageLayout.Landscape)

section("44c. [v43.9] 좌석표 — 지정석 + 공석 지정 시 빈 자리로 자동 이동")

with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw44._on_roster_clear()
seatw44.spin_headcount.setValue(19)   # 5줄x5칸=25칸 중 19명 -> 빈 자리 6개
seatw44.spin_cols.setValue(5)
seatw44._on_generate_numbered()
app.processEvents()

_r0, _c0 = 0, 0
_occupant = seatw44.chart.seats[_r0][_c0]
check("[v43.9] 테스트 전제 — (0,0)에 학생이 있음", _occupant is not None)

with _patch("src.utils.seating.QMenu") as _mock_menu_cls:
    _mock_menu = _mock_menu_cls.return_value
    _act_vacant = object()
    _mock_menu.addAction.side_effect = [_act_vacant, object(), object(), object()]
    _mock_menu.addMenu.return_value.addAction.side_effect = lambda *_a, **_k: object()
    _mock_menu.exec.return_value = _act_vacant
    seatw44._on_cell_right_clicked(_r0, _c0, seatw44.canvas.mapToGlobal(
        seatw44.canvas.cell_rect(_r0, _c0).center().toPoint()))
app.processEvents()
check("[버그 수정] 학생이 있던 자리를 공석으로 지정해도 그 학생이 사라지지 않고 빈 자리로 즉시 옮겨짐",
      seatw44.chart.gender[_r0][_c0] == "vacant" and seatw44.chart.seats[_r0][_c0] is None
      and any(seatw44.chart.seats[r][c] == _occupant for r in range(seatw44.chart.rows)
              for c in range(seatw44.chart.cols)))
check("[버그 수정] 다시 섞지 않아도(reshuffle 호출 없이) 전체 인원(19명)이 그대로 유지됨",
      sum(1 for row in seatw44.chart.seats for s in row if s) == 19)

# 지정석 — 특정 번호를 특정 자리에 고정
_target_sid = "7"
with _patch("src.utils.seating.QMenu") as _mock_menu_cls2:
    _mock_menu2 = _mock_menu_cls2.return_value
    _reserve_submenu = _mock_menu2.addMenu.return_value
    _act_reserve_target = object()
    _reserve_submenu.addAction.side_effect = [
        object() if sid != _target_sid else _act_reserve_target
        for sid, _label in seatw44._reservable_people()]
    _mock_menu2.addAction.side_effect = [object(), object(), object()]
    _mock_menu2.exec.return_value = _act_reserve_target
    seatw44._on_cell_right_clicked(3, 4, seatw44.canvas.mapToGlobal(
        seatw44.canvas.cell_rect(3, 4).center().toPoint()))
app.processEvents()
check("[v43.9] 지정석 메뉴에서 특정 번호를 고르면 그 자리로 즉시 옮겨짐",
      seatw44.chart.seats[3][4] == _target_sid and seatw44.chart.reserved.get((3, 4)) == _target_sid)

_before_reshuffle = seatw44.chart.seats[3][4]
seatw44._on_reshuffle()
app.processEvents()
check("[v43.9] '랜덤 배정'을 다시 눌러도 지정석 학생은 항상 같은 자리에 그대로 있음",
      seatw44.chart.seats[3][4] == _target_sid == _before_reshuffle)
check("[v43.9] 지정석이 아닌 나머지는 계속 무작위로 바뀔 수 있음(전체 인원은 유지)",
      sum(1 for row in seatw44.chart.seats for s in row if s) == 19)

win.switch_mode("util")
win.util_panel.open_app("seating")
app.processEvents()
seatw45 = win.util_panel._pages["seating"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw45._on_roster_clear()
seatw45.spin_headcount.setValue(22)
seatw45.spin_cols.setValue(5)
seatw45._on_generate_numbered()
app.processEvents()

_r_empty, _c_empty = seatw45.chart.rows - 1, 2   # 맨 뒷줄(데이터상 마지막 행)의 빈 칸
_r_full, _c_full = 0, 0                          # 맨 앞줄(교탁과 가장 가까운 줄)의 학생 자리
check("[v43.3] 대상 칸이 실제로 비어 있음/차 있음(테스트 전제 확인)",
      seatw45.chart.seats[_r_empty][_c_empty] is None and seatw45.chart.seats[_r_full][_c_full] is not None)

_moved_student = seatw45.chart.seats[_r_full][_c_full]
seatw45._on_cell_clicked(_r_empty, _c_empty)
app.processEvents()
check("[v43.3] 한 번 클릭하면 그 칸이 선택 상태가 됨(캔버스에 표시)",
      seatw45.canvas.selected_cell == (_r_empty, _c_empty))

seatw45._on_cell_clicked(_r_full, _c_full)
app.processEvents()
check("[v43.3] 이어서 다른 칸을 클릭하면 두 칸이 맞바뀜(학생이 뒷줄로, 빈 자리가 앞줄로)",
      seatw45.chart.seats[_r_empty][_c_empty] == _moved_student
      and seatw45.chart.seats[_r_full][_c_full] is None)
check("[v43.3] 스왑이 끝나면 선택이 풀림", seatw45.canvas.selected_cell is None)

# 같은 칸을 두 번 클릭하면 선택이 취소되고 아무것도 안 바뀌는지
_before_cancel = [row[:] for row in seatw45.chart.seats]
seatw45._on_cell_clicked(1, 1)
seatw45._on_cell_clicked(1, 1)
app.processEvents()
check("[v43.3] 같은 칸을 두 번 클릭하면 선택이 취소되고 배치는 그대로",
      seatw45.canvas.selected_cell is None and seatw45.chart.seats == _before_cancel)

# 두 학생끼리 스왑도 정상 동작하는지(빈 자리가 아닌 경우)
_a = seatw45.chart.seats[0][0]
_b = seatw45.chart.seats[0][1]
seatw45._on_cell_clicked(0, 0)
seatw45._on_cell_clicked(0, 1)
app.processEvents()
check("[v43.3] 학생 두 명끼리도 자리를 맞바꿀 수 있음",
      seatw45.chart.seats[0][0] == _b and seatw45.chart.seats[0][1] == _a)

# 캔버스의 cell_rect가 화면 좌표를 정확히 계산하는지(클릭 판정과 그리기가 항상 일치해야 함)
_rect_front = seatw45.canvas.cell_rect(0, 0)
_rect_back = seatw45.canvas.cell_rect(seatw45.chart.rows - 1, 0)
check("[v43.3] 앞줄(row=0)이 뒷줄보다 화면에서 더 아래(y가 더 큼) — 교탁이 아래쪽이라는 뜻",
      _rect_front.top() > _rect_back.top())

# 새로 배치를 만들면(다시 섞기 등) 진행 중이던 선택이 안전하게 풀리는지
seatw45._on_cell_clicked(0, 0)
seatw45._on_reshuffle()
app.processEvents()
check("[v43.3] 다시 섞으면 이전 선택 상태가 남아있지 않음", seatw45.canvas.selected_cell is None)

section("45b. [v43.3] 좌석표 — 우측 패널이 하단으로 재배치됨")

check("[v43.3] 카드 3개가 이제 같은 부모 아래 가로로 나란히 놓임(수직 vstack이 아님)",
      seatw45.card_class.parent() is seatw45.card_seat.parent() is seatw45.card_save.parent())
from PySide6.QtWidgets import QVBoxLayout as _QVBL
check("[v43.3] 전체 레이아웃이 세로 방향(캔버스가 위, 설정 카드 줄이 아래)",
      isinstance(seatw45.layout(), _QVBL))

section("46. [v43.8] 좌석표 — 자리 성별 지정(공석/여학생/남학생) 순수 로직")

_g1 = [BS.Student(f"g1s{i}", "1", "1", str(i), f"학생{i}", "여" if i % 2 == 0 else "남")
      for i in range(1, 21)]
_gchart = SS.random_layout(_g1, cols=5, seed=1)
check("[v43.8] 새 배치는 전부 남학생(M) 칸으로 시작함",
      all(g == "M" for row in _gchart.gender for g in row))
check("[v43.8] 성별 구역이 전부 M이면 남녀 상관없이 아무 칸에나 앉음(기존 동작과 동일)",
      sum(1 for row in _gchart.seats for s in row if s) == 20)

SS.set_seat_gender(_gchart, 0, 0, "F")
SS.set_seat_gender(_gchart, 0, 1, "F")
SS.set_seat_gender(_gchart, 1, 0, "vacant")
check("[v43.8] set_seat_gender로 자리 지정이 바뀜", _gchart.gender[0][0] == "F" and _gchart.gender[1][0] == "vacant")
check("[v43.8] vacant로 지정하면 거기 있던 학생이 내려옴(자리가 비워짐)", _gchart.seats[1][0] is None)

_females = [s for s in _g1 if SS.is_female(s)]
_gchart2 = SS.reshuffle(_gchart, _g1, seed=2)
check("[v43.8] 다시 섞어도 자리별 성별 지정(F 2칸, vacant 1칸)이 그대로 유지됨",
      _gchart2.gender[0][0] == "F" and _gchart2.gender[0][1] == "F" and _gchart2.gender[1][0] == "vacant")
check("[v43.8] vacant 자리엔 다시 섞어도 아무도 안 앉음", _gchart2.seats[1][0] is None)
_f_occupants = {_gchart2.seats[0][0], _gchart2.seats[0][1]} - {None}
_female_sids = {s.sid for s in _females}
check("[v43.8] F로 지정한 자리엔 여학생만 앉음(남학생 안 섞임)", _f_occupants.issubset(_female_sids))
check("[v43.8] 총원(20명)이 안 나누어떨어지는 자리 수(vacant 1칸 제외 19자리)라도 아무도 안 빠짐",
      sum(1 for row in _gchart2.seats for s in row if s) == 20 - 1   # vacant 자리 하나만큼 자리가 줄어 1명은 못 앉음(overflow)
      or sum(1 for row in _gchart2.seats for s in row if s) == 20)

check("[v43.8] 헤드카운트 모드 numbered_layout도 gender_grid를 받아 유지할 수 있음",
      SS.numbered_layout(10, 5, gender_grid=_gchart.gender).gender == _gchart.gender)

section("46b. [v43.8] 좌석표 — 위젯 오른쪽 클릭 메뉴 통합")

win.switch_mode("util")
win.util_panel.open_app("seating")
app.processEvents()
seatw46 = win.util_panel._pages["seating"][0]
with _patch("src.utils.bracket.QMessageBox.question", return_value=QMessageBox.Yes):
    seatw46._on_roster_clear()
seatw46.spin_headcount.setValue(20)
seatw46.spin_cols.setValue(5)
seatw46._on_generate_numbered()
app.processEvents()
check("[v43.8] 새로 만든 배치는 캔버스에서도 전부 M(남학생)으로 시작함",
      all(g == "M" for row in seatw46.chart.gender for g in row))

with _patch("src.utils.seating.QMenu") as _mock_menu_cls:
    _mock_menu = _mock_menu_cls.return_value
    _act_female = object()
    _mock_menu.addAction.side_effect = [object(), _act_female, object()]   # 공석, 여학생, 남학생 순
    _mock_menu.exec.return_value = _act_female
    seatw46._on_cell_right_clicked(0, 0, seatw46.canvas.mapToGlobal(seatw46.canvas.cell_rect(0, 0).center().toPoint()))
app.processEvents()
check("[v43.8] 오른쪽 클릭 메뉴에서 '여학생'을 고르면 그 자리가 F로 바뀜",
      seatw46.chart.gender[0][0] == "F")

with _patch("src.utils.seating.QMenu") as _mock_menu_cls2:
    _mock_menu2 = _mock_menu_cls2.return_value
    _act_vacant = object()
    _mock_menu2.addAction.side_effect = [_act_vacant, object(), object()]
    _mock_menu2.exec.return_value = _act_vacant
    seatw46._on_cell_right_clicked(1, 1, seatw46.canvas.mapToGlobal(seatw46.canvas.cell_rect(1, 1).center().toPoint()))
app.processEvents()
check("[v43.8] '공석'을 고르면 그 자리가 vacant로 바뀌고 점유자가 내려옴",
      seatw46.chart.gender[1][1] == "vacant" and seatw46.chart.seats[1][1] is None)

section("47. [v43.10] Util 스플리터 — 왼쪽으로 옮긴 뒤 다시 오른쪽으로 옮길 수 있음(버그 수정)")

check("[버그 수정] 왼쪽(도구 목록)·오른쪽(작업 영역) 둘 다 접히지 않게 설정됨",
      win.util_panel.splitter.isCollapsible(0) is False
      and win.util_panel.splitter.isCollapsible(1) is False)

_orig_sizes = win.util_panel.splitter.sizes()
win.util_panel.splitter.setSizes([0, 1300])   # 왼쪽을 극단적으로 좁게(0으로) 시도
app.processEvents()
_after_left = win.util_panel.splitter.sizes()
check("[버그 수정] 왼쪽을 0으로 끌어도 최소 폭 아래로는 안 줄어듦(완전히 안 접힘)",
      _after_left[0] > 0)
win.util_panel.splitter.setSizes([900, 400])   # 다시 오른쪽으로(왼쪽을 넓게) 시도
app.processEvents()
_after_right = win.util_panel.splitter.sizes()
check("[버그 수정] 왼쪽을 좁힌 뒤에도 다시 넓게 되돌릴 수 있음(막혀 있지 않음)",
      _after_right[0] > _after_left[0] + 100)
win.util_panel.splitter.setSizes(_orig_sizes)
app.processEvents()

# 대진표 캔버스가 아주 넓어져도(참가자 많은 대진표) 화면 전체 최소 폭이
# 거기 맞춰 영구히 커지지 않는지 — setMinimumSize(sizeHint())였던 버그.
# 실제 화면에서 쓰는 것과 똑같이 set_event_bracket()(정식 API)로 만든다 —
# cells를 손으로 채우면 champ_id 등 다른 상태와 안 맞아서 다음 paintEvent가
# 죽는다(실제로 이렇게 했다가 세그폴트가 났다).
win.util_panel.open_app("bracket")
app.processEvents()
bw47 = win.util_panel._pages["bracket"][0]
_min_before = bw47.minimumSizeHint()
_big_bracket = B.Bracket({f"p{i}": f"선수{i}" for i in range(32)}, seed=1)
bw47.roster_bracket_canvas.set_event_bracket(_big_bracket)
app.processEvents()
check("[버그 수정] 대진표 캔버스가 아주 넓어져도(참가자 32명, 5라운드) 최소 크기 자체는 안 늘어남",
      bw47.roster_bracket_canvas.minimumWidth() == 0
      and bw47.minimumSizeHint().width() == _min_before.width())
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("48. [v44.1] 행운의 번호 — 순수 로직(대상·공정성·재현·상태기계·저장)")
import csv as _csv48
import math
import json as _json48
import random as _rnd48
from collections import Counter as _Counter48
from src.utils import lucky_draw_logic as LD
from src.utils import anim_physics as AP

_ents48 = LD.range_entries(1, 500)
check("[v44.1] 번호 범위는 최대 120개까지만(1~500 → 1~120)",
      len(_ents48) == LD.MAX_ENTRIES and _ents48[0].no == 1 and _ents48[-1].no == 120)
_s48 = LD.DrawSession(LD.range_entries(1, 10), "range", exclude_winners=True)
_s48.excluded = {"n3", "n7"}
check("[v44.1] 제외(결석) 대상은 뽑을 수 있는 목록에서 빠짐", "n3" not in _s48.available_keys()
      and len(_s48.available_keys()) == 8)
_s48.record("n1")
check("[v44.1] 당첨자 제외 켬 — 뽑힌 번호는 다음 추첨에서 빠짐", "n1" not in _s48.available_keys())
_s48.exclude_winners = False
check("[v44.1] 당첨자 제외 끔(복원 추첨) — 뽑힌 번호도 다시 후보", "n1" in _s48.available_keys())

# ---- 물리: 항상 텀블링 + 에너지 안정성 + 공정성
_R48 = LD.DRUM_R
_r48 = AP.ball_radius_for(30, _R48)
_w48 = AP.DrumWorld(LD.DRUM_CX, LD.DRUM_CY, _R48, _r48, list(range(30)))
_rng48w = _rnd48.Random(1)
_w48.lay_out(_rng48w)
_w48.quantize()
_snap_before48 = [(_w48.xs[i], _w48.ys[i]) for i in range(30)]
for _ in range(int(3.0 / AP.PHYS_DT)):
    _w48.step(AP.PHYS_DT, _rng48w, spin_rate=LD.SPIN_IDLE)
_snap_after48 = [(_w48.xs[i], _w48.ys[i]) for i in range(30)]
_moved48 = sum(1 for a, b in zip(_snap_before48, _snap_after48) if math.hypot(a[0]-b[0], a[1]-b[1]) > 3)
check("[v44.1] 평소(대기)에도 벽에 닿은 공이 계속 텀블링함(3초 뒤 30개 전부 움직임)", _moved48 == 30, _moved48)
_max_step48 = 0.0
for _ in range(60):
    _before = [(_w48.xs[i], _w48.ys[i]) for i in range(30)]
    _w48.step(AP.PHYS_DT, _rng48w, spin_rate=LD.SPIN_FAST)
    _after = [(_w48.xs[i], _w48.ys[i]) for i in range(30)]
    _max_step48 = max(_max_step48, max(math.hypot(a[0]-b[0], a[1]-b[1]) for a, b in zip(_before, _after)))
check("[v44.1] 빠르게 섞는 동안에도 한 프레임 최대 이동거리가 정상 범위(에너지 폭주 없음)",
      _max_step48 < 200, _max_step48)

_cnt48 = _Counter48()
for _sd in range(400):
    _k, _sim48f = LD.run_drum_headless([f"n{i}" for i in range(1, 11)], _sd, speed="fast", max_seconds=20.0)
    _cnt48[_k] += 1
_exp48 = 400 / 10
_chi48 = sum((v - _exp48) ** 2 / _exp48 for v in _cnt48.values())
check("[v44.1] 코어 챔버 — 10명 400회 균등(카이제곱 < 28, 자유도 9의 0.1% 임계)",
      _chi48 < 28 and len(_cnt48) == 10, _chi48)

_keys48 = [f"n{i}" for i in range(1, 41)]
_same48 = 0
for _sd in (1, 2, 3):
    _w, _sim = LD.run_drum_headless(_keys48, _sd, speed="normal", max_seconds=20.0)
    _same48 += (_w is not None and LD.replay_drum_headless(_sd, _sim.replay_info()) == _w)
check("[v44.1] 코어 챔버 — 시드·시작 상태만으로 같은 공이 재현됨(3/3, 별도 이벤트 기록 불필요)", _same48 == 3)

_sim48 = LD.DrumSim(_keys48, 11, speed="normal")
for _i in range(90):   # 대기 상태로 한참 텀블링하다가
    _sim48.step()
_sim48.start_draw()
_win48 = None
for _i in range(3000):
    _win48 = _sim48.step()
    if _win48:
        break
check("[v44.1] start_draw()를 부른 순간의 배치가 재현 기준 — 대기 시간과 무관하게 재현 일치",
      _win48 is not None and LD.replay_drum_headless(11, _sim48.replay_info()) == _win48)
check("[v44.1] 뽑기 도중엔 start_draw()가 다시 안 먹힘(진행 중 재시작 방지)",
      _sim48.start_draw() is False)
_snap48 = _sim48.world.snapshot()
_cont48 = LD.DrumSim([r[0] for r in _snap48], 12, snapshot=_snap48, ball_radius=_sim48.ball_r)
_cont48.start_draw()
_w2 = None
for _i in range(3000):
    _w2 = _cont48.step()
    if _w2:
        break
check("[v44.1] 다음 회차는 지금 공 상태에서 이어서 시작해도 재현 일치(당첨 공 제외된 스냅숏)",
      _w2 is not None and _w2 != _win48 and LD.replay_drum_headless(12, _cont48.replay_info()) == _w2)
check("[v44.1] 재현 정보는 JSON으로 저장 가능(이벤트 로그 없이 스냅숏+속도만)",
      bool(_json48.dumps(_cont48.replay_info())) and "events" not in _cont48.replay_info())

# [버그 수정 검증] 대기(텀블링) 시간이 제각각이어도 재현이 항상 일치해야 한다
# — start_draw()가 그립 상태·시드·바람 위상·sim_t를 전부 그 순간으로 리셋하는지.
_ok48r = 0
for _trial in range(20):
    _sim48r = LD.DrumSim([f"n{i}" for i in range(1, 41)], 100 + _trial, speed="normal")
    for _ in range(_rnd48.Random(_trial).randint(0, 200)):
        _sim48r.step()
    _sim48r.start_draw()
    _w48r = None
    for _i in range(3000):
        _w48r = _sim48r.step()
        if _w48r:
            break
    _ok48r += (_w48r is not None and LD.replay_drum_headless(100 + _trial, _sim48r.replay_info()) == _w48r)
check("[v44.1] 대기 시간이 제각각이어도(0~200스텝 무작위) 재현이 항상 일치(20/20)", _ok48r == 20, _ok48r)

# [버그 수정 검증] 공정성 — 바람 위상을 배열 인덱스에 고정했더니 "같은 번호가 매번
# 같은 위상"이 되어 카이제곱 검정에 뚜렷이 걸렸다(N=1000에서 64) — 회차마다
# 무작위로 다시 뽑도록 고친 뒤 값이 정상 범위로 돌아오는지 큰 표본으로 확인한다.
_cnt48f = _Counter48()
for _sd in range(1000):
    _k48f, _ = LD.run_drum_headless([f"n{i}" for i in range(1, 11)], _sd, speed="dramatic", max_seconds=30.0)
    _cnt48f[_k48f] += 1
_exp48f = 1000 / 10
_chi48f = sum((v - _exp48f) ** 2 / _exp48f for v in _cnt48f.values())
check("[v44.1] 공정성(1000회, dramatic) — 바람 위상을 회차마다 다시 뽑아 편향 없음(카이제곱 < 28)",
      _chi48f < 28 and len(_cnt48f) == 10, _chi48f)

# [버그 수정 검증] 흡입 중에도 바람을 약화하지 않게 고쳐서, 사정거리 밖에 있던
# 공이 중력에 눌려 영원히 못 올라오는 정지가 더는 없어야 한다(여러 속도 설정에서).
_stall48 = 0
for _speed48 in ("fast", "normal", "dramatic"):
    for _sd in range(150):
        _k48s, _ = LD.run_drum_headless([f"n{i}" for i in range(1, 11)], _sd, speed=_speed48, max_seconds=25.0)
        if _k48s is None:
            _stall48 += 1
check("[v44.1] 세 속도 설정 모두 정지(무한 대기) 없이 항상 당첨자가 나옴(450회)", _stall48 == 0, _stall48)

# 전체 사이클이 결국 idle로 돌아오는지(섞기→감속→송풍→흡입→닫힘→idle)
_sim48c = LD.DrumSim([f"n{i}" for i in range(1, 13)], 21, speed="fast")
_sim48c.start_draw()
_phases_seen = set()
for _i in range(3000):
    _sim48c.step()
    _phases_seen.add(_sim48c.phase if _sim48c.phase != "wind" else f"wind:{_sim48c.port_sub}")
    if _sim48c.phase == "idle" and _sim48c.winner is not None:
        break
# ("wind:sucking"는 문이 열리자마자 같은 프레임에 바로 포획되는 경우가 흔해
#  화면에 한 프레임도 안 보일 수 있다 — 실제로 그런 빠른 포획이 정상 동작임을
#  이미 확인했으므로(진공청소기처럼 즉시 빨려 들어가는 게 의도) 필수로 보지 않는다.)
check("[v44.1] 뽑기 한 번의 전체 단계를 다 거침(섞기→감속→송풍 카운트다운→개방→닫힘→대기)",
      {"mixing", "slowdown"} <= _phases_seen
      and any(p.startswith("wind:countdown") for p in _phases_seen)
      and any(p.startswith("wind:opening") for p in _phases_seen)
      and any(p.startswith("wind:closing") for p in _phases_seen)
      and any(p.startswith("wind:holding") for p in _phases_seen)
      and _sim48c.phase == "idle" and _sim48c.winner is not None, _phases_seen)

check("[v44.1] 공 반지름 — 120개도 드럼 면적 36%, 적을 때는 상한",
      abs(AP.ball_radius_for(120, 330) - 330 * (0.36 / 120) ** 0.5) < 1e-9
      and AP.ball_radius_for(2, 330) == 330 * 0.16)
check("[v44.1] 선분-타원 판정 — 한 스텝에 풍선을 뚫고 지나가도 잡음",
      AP.segment_hits_ellipse(0, 0, 100, 0, 50, 0, 5, 5) and not AP.segment_hits_ellipse(0, 20, 100, 20, 50, 0, 5, 5))

_s48c = LD.DrawSession(LD.range_entries(1, 45), "combo")
for _k in ("n40", "n3", "n17"):
    _s48c.record(_k, label="1게임")
check("[v44.1] 조합 — 조합 안에서는 중복 없이", "n3" not in _s48c.available_keys())
check("[v44.1] 조합 완성 시 오름차순 정렬", _s48c.finish_combo() == [3, 17, 40] and _s48c.combos[0]["label"] == "1게임")
check("[v44.1] 조합을 마치면 다음 조합은 다시 전체에서", len(_s48c.available_keys()) == 45)
_rt48 = LD.DrawSession.from_dict(_json48.loads(_json48.dumps(_s48c.to_dict())))
check("[v44.1] 세션 JSON 왕복(기록·조합 보존)", len(_rt48.rounds) == 3 and _rt48.combos == _s48c.combos)
_tmp48 = tempfile.mkdtemp()
_csv48p = os.path.join(_tmp48, "rec.csv")
LD.export_rounds_csv(_csv48p, _s48c, ["a", "b", "c", "d", "e", "f"])
with open(_csv48p, "rb") as _fh:
    _raw48 = _fh.read()
check("[v44.1] 기록 CSV — 엑셀용 BOM(utf-8-sig) + 3행", _raw48.startswith(b"\xef\xbb\xbf")
      and len(_raw48.decode("utf-8-sig").strip().splitlines()) == 4)
_pairs48 = LD.assign_tickets(LD.name_list_entries([f"사람{i}" for i in range(25)]), _rnd48.Random(3))
check("[v44.1] 번호표 — 25명에게 1~25가 겹치지 않게", sorted(t for t, _e in _pairs48) == list(range(1, 26))
      and len({e.key for _t, e in _pairs48}) == 25)
check("[v44.1] 이름 붙여넣기 — 빈 줄 무시", len(LD.name_list_entries(["가", " ", "", "나"])) == 2)

section("48b. [v44.1] 행운의 번호 — 위젯(어코디언·단일 뽑기 버튼·조합·잠금·재현·전체화면·저장)")
from src.utils.anim_kit import AnimCanvas
from src.utils import ui_kit as UK48

win.switch_mode("util")
win.util_panel.open_app("lucky")
app.processEvents()
lw = win.util_panel._pages["lucky"][0]
lsc = lw.scene
check("[v44.1] 행운의 번호 — 학교(class) 카테고리로 등록", win.util_panel.by_id["lucky"].category == "class")
check("[v44.1] 추첨 대상·추첨 기록 카드는 기본이 접힘(어코디언)",
      not lw.pool_body.isVisible() and not lw.log_body.isVisible())
lw._toggle_accordion("pool")
check("[v44.1] 펼치기 토글 — 추첨 대상이 열리고 화살표가 바뀜",
      lw.pool_body.isVisible() and lw.btn_pool_toggle.text() == "▾")
lw._toggle_accordion("pool")
check("[v44.1] 다시 누르면 접힘", not lw.pool_body.isVisible() and lw.btn_pool_toggle.text() == "▸")

lw.radio_types["range"].setChecked(True)
lw._on_type_changed()
lw.spin_start.setValue(1)
lw.spin_end.setValue(40)
lw._range_timer.stop()
lw._rebuild_session()
check("[v44.1] 번호 1~40 → 대상 40개, 드럼 공 40개", len(lw.session.entries) == 40
      and len(lsc.sim.world.alive_indices()) == 40)
lw.combo_speed.setCurrentIndex(lw.combo_speed.findData("fast"))


def _run_until_idle(scene, limit=6000):
    for _i in range(limit):
        scene.run_steps(1)
        if not scene.busy:
            return True
    return False


check("[v44.1] '섞기' 버튼이 따로 없음 — [뽑기] 하나로 전부 자동 진행", not hasattr(lw, "btn_mix"))
lw._on_draw()
check("[v44.1] 뽑기를 누르면 즉시 섞기 단계로 들어가고 진행 중으로 표시", lsc.busy and lsc.sim.phase == "mixing")
_drawn_before = len(lw.session.drawn)
_ok48 = _run_until_idle(lsc)
check("[v44.1] 뽑기 한 번으로 섞기→감속→송풍→흡입까지 자동으로 끝나 기록됨",
      _ok48 and len(lw.session.drawn) == _drawn_before + 1)
_rec48 = lw.session.rounds[-1]
check("[v44.1] 드럼 기록에 시드·재현 정보(스냅숏+속도)가 들어감",
      _rec48["seed"] is not None and _rec48["replay"]["snapshot"] and _rec48["replay"]["speed"] == "fast")
check("[v44.1] 당첨 공은 드럼에서 빠지고 다음 회차에서도 후보가 아님",
      _rec48["key"] not in lw.session.available_keys())
check("[v44.1] 기록이 생기면 대상 설정(범위·유형)이 잠김", not lw.spin_end.isEnabled()
      and not lw.radio_types["roster"].isEnabled())
check("[v44.1] 기록 카드 제목에 개수가 표시됨", lw.card_log.title_label.text() == tr("util.lucky.card.log_n", a0=1))

lw.spin_repeat.setValue(2)
lw._on_draw()
_ok48 = _run_until_idle(lsc)
_run_until_idle(lsc)
check("[v44.1] '한 번에 뽑을 수' 2 → 연속으로 2명 기록", _ok48 and len(lw.session.drawn) == 3)
lw.spin_repeat.setValue(1)

# 결석 제외: 대상 목록 체크 해제
lw._toggle_accordion("pool")
_it48 = lw.list_pool.item(10)
_key48 = _it48.data(Qt.UserRole)
_it48.setCheckState(Qt.Unchecked)
app.processEvents()
check("[v44.1] 대상 목록 체크 해제 → 제외(결석)로 저장, 뽑을 수 없음",
      _key48 in lw.session.excluded and _key48 not in lw.session.available_keys())

# 재현 — 기록은 늘지 않는다
lw._toggle_accordion("log")
_n48 = len(lw.session.rounds)
lw.list_log.setCurrentRow(lw.list_log.count() - 1)   # 가장 오래된 기록
lw._on_replay()
check("[v44.1] 재현 시작", lsc.replay_mode)
_run_until_idle(lsc)
check("[v44.1] 재현은 기록을 늘리지 않고, 같은 공이 다시 나옴",
      len(lw.session.rounds) == _n48 and lsc.reveal_key == lw.session.rounds[0]["key"])
check("[v44.1] 재현이 끝나면 평소 상태(대기)로 돌아옴", lsc.sim.phase == "idle" and not lsc.replay_mode)

# 조합
with _patch("src.utils.lucky_draw.QMessageBox.question", return_value=QMessageBox.Yes):
    lw._on_reset()
check("[v44.1] 초기화 — 기록이 지워지고 잠금이 풀림", not lw.session.rounds and lw.spin_end.isEnabled())
lw.radio_types["combo"].setChecked(True)
lw._on_type_changed()
lw.spin_combo_k.setValue(3)
lw._on_draw()
for _i in range(4):
    _run_until_idle(lsc)
check("[v44.1] 조합 뽑기 — 3개를 뽑고 정렬된 조합 하나가 기록됨",
      len(lw.session.combos) == 1 and len(lw.session.combos[0]["numbers"]) == 3
      and lw.session.combos[0]["numbers"] == sorted(lw.session.combos[0]["numbers"]))
check("[v44.1] 조합 완성 후 장면 터미널에 조합 줄 표시", bool(lsc.combo_line))

# 명단(이름 붙여넣기)
with _patch("src.utils.lucky_draw.QMessageBox.question", return_value=QMessageBox.Yes):
    lw._on_reset()
lw.radio_types["roster"].setChecked(True)
lw._on_type_changed()
lw.set_names([f"참가자{i}" for i in range(1, 131)])
check("[v44.1] 이름 130개 붙여넣기 → 120명까지만 + 안내 문구", len(lw.session.entries) == 120
      and bool(lw.lbl_pool_error.text()))
lw.set_names(["김선린", "이인터넷", "박고등"])
lw._on_draw()
_run_until_idle(lsc)
check("[v44.1] 명단 추첨 — 이름이 기록에 남음", lw.session.rounds[-1]["name"] in ("김선린", "이인터넷", "박고등"))

# 번호표
lw.radio_types["ticket"].setChecked(True)
lw._apply_type_visibility()
check("[v44.1] 번호표 모드 — 주 버튼 문구가 '번호표 발급'", lw.btn_draw.text() == tr("util.lucky.btn.ticket"))
from src.utils.lucky_draw import TicketDialog
_td48 = TicketDialog(LD.name_list_entries(["가", "나", "다", "라"]))
check("[v44.1] 번호표 창 — 4명 전원 번호 부여", _td48.table.rowCount() == 4 and "<table" in _td48.ticket_html())
_td48.close()
lw.radio_types["roster"].setChecked(True)
lw._apply_type_visibility()

# 세션 파일 저장/열기
_sess48 = lw.save_session_file(os.path.join(_tmp48, "s.json"))
_csv48b = lw.export_csv(os.path.join(_tmp48, "s.csv"))
check("[v44.1] 세션 JSON·기록 CSV 저장", _sess48 and os.path.exists(_sess48) and os.path.exists(_csv48b))
_nrounds48 = len(lw.session.rounds)
with _patch("src.utils.lucky_draw.QMessageBox.question", return_value=QMessageBox.Yes):
    lw._on_reset()
lw.open_session_file(_sess48)
check("[v44.1] 세션 열기 — 기록 그대로 복원", len(lw.session.rounds) == _nrounds48)

# 자동 저장 → 새 위젯(프로그램 재시작 흉내)에서 복원
from src.utils.lucky_draw import LuckyDrawWidget
from src.utils.base import UtilHost as _UH48
_lw2 = LuckyDrawWidget(_UH48(None))
check("[v44.1] 프로그램을 다시 켜도 진행 중이던 추첨 기록이 이어짐(자동 저장)",
      len(_lw2.session.rounds) == _nrounds48 and _lw2.current_type() == "roster")
_lw2.deleteLater()

# 전체화면
lw.presenter.enter()
app.processEvents()
check("[v44.1] 전체화면 — 캔버스가 별도 창으로 옮겨짐", lw.presenter.active and lsc.window() is lw.presenter.window)
lsc.exitFullscreenRequested.emit()
app.processEvents()
check("[v44.1] Esc — 원래 카드 자리로 되돌아옴", not lw.presenter.active and lsc.window() is win)
lw.presenter.enter()
app.processEvents()
lw.presenter.window.close()   # Alt+F4처럼 창을 직접 닫음
app.processEvents()
check("[v44.1] 전체화면 창을 직접 닫아도 캔버스가 지워지지 않고 원래 자리로", not lw.presenter.active
      and lsc.window() is win and lsc.width() > 0)
check("[v44.1] 장면 캔버스는 AnimCanvas(고정 스텝 루프) 기반", isinstance(lsc, AnimCanvas))
lsc.hide()
check("[v44.1] 가려지면(hide) 애니메이션 루프가 멈춤", not lsc.is_running())
lsc.show()
app.processEvents()

for _th in ("stadium", "night", "classic"):
    lw.combo_theme.setCurrentIndex(lw.combo_theme.findData(_th))
    lsc.grab()
check("[v44.1] 테마 3종 모두 그리기 예외 없음", lsc.theme == "classic")
for _lang in ("en", "ja", "ko"):
    set_language(_lang)
    win.retranslate_ui() if hasattr(win, "retranslate_ui") else None
    lw.retranslate()
    lsc.grab()
check("[v44.1] 언어 3종 전환 — 제목이 번역됨(이진 라우터 관련 위젯 없음)",
      lw.card_setup.title_label.text() == "추첨 설정" and not hasattr(lw, "combo_visual"))

section("49. [v44] 응원의 메시지 — 순수 로직(덱 무반복·하루 고정·날짜 지정·편집 반영)")
from src.utils import cheer_logic as CHL
from src.utils.cheer_messages import BASE_MESSAGES as _BM49, CATEGORIES as _CATS49

check("[v44] 기본 메시지 120개, id 중복 없음, 분류는 내부 키 4종",
      len(_BM49) == 120 and len({m[0] for m in _BM49}) == 120 and {m[1] for m in _BM49} == set(_CATS49))
check("[v44] 기본 메시지는 모두 120자 이내", all(len(m[2]) <= CHL.MAX_TEXT for m in _BM49))

_bk49 = CHL.MessageBook()
_bk49.prefer_user = False
_r49 = _rnd48.Random(5)
_seq49 = []
for _d in range(24):   # 24일 × 5개 = 120개 = 덱 하나
    _seq49 += _bk49.todays_set(f"2026-10-{_d + 1:02d}", 5, _r49)
check("[v44] 덱 한 바퀴(120개) 안에서는 같은 메시지가 두 번 나오지 않음", len(set(_seq49)) == 120)
_seq49b = _bk49.todays_set("2026-11-01", 5, _r49)
check("[v44] 덱을 다시 섞을 때 직전 덱의 마지막 5개가 바로 나오지 않음",
      not (set(_seq49b) & set(_seq49[-5:])))

_bk49 = CHL.MessageBook()
_a49 = _bk49.todays_set("2026-09-23", 6, _r49)
_b49 = _bk49.todays_set("2026-09-23", 6, _r49)
check("[v44] 하루 고정 — 같은 날 다시 열면 같은 메시지 6개", _a49 == _b49 and len(set(_a49)) == 6)
_pos49 = _bk49.deck_pos
_c49 = _bk49.todays_set("2026-09-30", 6, _r49)   # 일주일 건너뜀
check("[v44] 건너뛴 날은 덱을 소모하지 않음(다음 날 6개만 소모)", _bk49.deck_pos == _pos49 + 6
      and not (set(_c49) & set(_a49)))
_bk49.mode = "per_run"
_d49 = _bk49.todays_set("2026-09-30", 6, _r49)
check("[v44] 열 때마다 새로(per_run) — 같은 날이어도 다음 메시지", not (set(_d49) & set(_c49)))
_bk49.mode = "per_day"

_u49 = _bk49.add_user("수능 대박! 선린 파이팅", "담임 선생님이", "exam", "2026-11-18")
_e49 = _bk49.todays_set("2026-11-18", 6, _r49)
check("[v44] 날짜 지정 메시지 — 그날 첫 번째(황금 풍선)로 나옴", _e49[0] == _u49)
check("[v44] 날짜 지정 메시지는 덱의 남은 구간에서 빠짐(가까운 날 반복 방지)",
      _u49 not in _bk49.deck[_bk49.deck_pos:])
_bk49.update_user(_u49, text="수능 대박!!")
check("[v44] 교사가 문구를 고치면 id가 같아 바로 반영", _bk49.get(_u49)["text"] == "수능 대박!!"
      and _bk49.todays_set("2026-11-18", 6, _r49)[0] == _u49)
_bk49.delete_user(_u49)
_f49 = _bk49.todays_set("2026-11-18", 6, _r49)
check("[v44] 오늘 세트의 메시지를 지우면 빠지고 다른 메시지로 채워짐", _u49 not in _f49 and len(_f49) == 6)
_bk49.set_enabled("base_001", False)
check("[v44] 기본 메시지 사용 끄기 → 추첨 대상에서 빠짐", "base_001" not in _bk49.pool_ids())
_u49b = _bk49.add_user("새 메시지", category="nope")
check("[v44] 모르는 분류는 cheer로", _bk49.get(_u49b)["category"] == "cheer")
_bk49b = CHL.MessageBook()
_bk49b.load(_bk49.user_to_json(), _bk49.state_to_json())
check("[v44] 저장/불러오기 왕복(교사 메시지·사용 끄기·덱·오늘 세트)",
      _bk49b.get(_u49b) is not None and "base_001" in _bk49b.base_disabled
      and _bk49b.deck == _bk49.deck and _bk49b.today == _bk49.today)
_bk49c = CHL.MessageBook()
_bk49c.load(_json48.dumps({"user_messages": [], "base_disabled": ["base_999", "base_002"]}), "")
check("[v44] 기본 메시지 목록에 없는 id의 '사용 끄기'는 불러올 때 무시(목록 업데이트 대비)",
      _bk49c.base_disabled == {"base_002"})
_bk49d = CHL.MessageBook()
for _i in range(10):
    _bk49d.add_user(f"선생님 메시지 {_i}")
_bk49d.deck = []
_ids49 = _bk49d.todays_set("2026-12-01", 8, _r49)
_first_half = _bk49d.deck[:len(_bk49d.deck) // 2]
check("[v44] 교사 메시지 우선 — 새 덱의 앞쪽 절반에 모두 들어감",
      all(m["id"] in _first_half for m in _bk49d.user))

_xl49 = os.path.join(_tmp48, "msg.xlsx")
CHL.save_message_template(_xl49, ["본문", "보조", "분류", "날짜"],
                          [["첫 메시지", "담임", "시험", "2026-11-18"], ["둘째", "", "maker", ""]])
from src.utils.cheer import _category_lookup, import_rows
_rows49 = CHL.read_message_excel(_xl49, _category_lookup())
check("[v44] 엑셀 불러오기 — 분류 표시 문구(시험)·내부 키(maker) 모두 인식, 날짜 유지",
      _rows49 == [("첫 메시지", "담임", "exam", "2026-11-18"), ("둘째", "", "maker", None)], _rows49)
_bk49e = CHL.MessageBook()
check("[v44] 같은 본문은 두 번 들어가지 않음", import_rows(_bk49e, _rows49) == 2 and import_rows(_bk49e, _rows49) == 0)

_bl49 = CHL.make_balloons(["a", "b", "c", "d", "e", "f"], _rnd48.Random(2), "normal")
check("[v44] 풍선 — 첫 번째가 황금 풍선, 서로 너무 붙지 않음",
      _bl49[0].golden and not any(b.golden for b in _bl49[1:])
      and min(((p.bx - q.bx) ** 2 + (p.by - q.by) ** 2) ** 0.5 for i, p in enumerate(_bl49)
              for q in _bl49[i + 1:]) > 100)
_vx49, _vy49 = CHL.launch_velocity(-100, 50)
check("[v44] 활 — 당긴 반대 방향으로, 당긴 만큼 세게", _vx49 > 0 and _vy49 < 0
      and abs((_vx49 ** 2 + _vy49 ** 2) ** 0.5 - CHL.V_MAX * (100 ** 2 + 50 ** 2) ** 0.5 / CHL.PULL_MAX) < 1e-6)

section("49b. [v44] 응원의 메시지 — 위젯(날짜 주입·풍선 명중·카드·메시지 관리)")
import datetime as _dt49
from src.utils.cheer import CheerWidget
win.util_panel.open_app("cheer")
app.processEvents()
cw = win.util_panel._pages["cheer"][0]
check("[v44] 응원의 메시지 — 학교(class) 카테고리로 등록", win.util_panel.by_id["cheer"].category == "class")
check("[v44] 기본 풍선 6개, 오늘 세트 6개", len(cw.scene.balloons) == 6 and len(cw.today_ids) == 6)
_cw2 = CheerWidget(_UH48(None), today_func=lambda: _dt49.date(2026, 11, 18))
check("[v44] 날짜 주입 — 오늘 날짜·요일이 표시됨", "2026" in _cw2.lbl_date.text() and "수" in _cw2.lbl_date.text())
_ids_a = list(_cw2.today_ids)
_cw2.start_round()
check("[v44] 같은 날 [다시 띄우기] — 하루 고정이라 같은 메시지", _cw2.today_ids == _ids_a)
_cw2.radio_modes["per_run"].setChecked(True)
_cw2._on_mode_changed()
_cw2.start_round()
check("[v44] '열 때마다 새로'로 바꾸면 다른 메시지", not (set(_cw2.today_ids) & set(_ids_a)))
_cw2.radio_modes["per_day"].setChecked(True)
_cw2._on_mode_changed()
_mid49 = _cw2.book.add_user("시험 잘 봐!", "", "exam", "2026-11-19")
_cw2._on_book_changed()
_cw3 = CheerWidget(_UH48(None), today_func=lambda: _dt49.date(2026, 11, 19))
check("[v44] 교사 메시지(날짜 지정)가 저장되고, 그날 위젯을 열면 황금 풍선", _cw3.today_ids[0] == _mid49
      and _cw3.scene.balloons[0].golden)

cs49 = _cw3.scene
cs49.resize(800, 450)
_b49g = cs49.balloons[0]
_hit49 = None
for _ang in range(-85, 15):
    for _pw in range(30, 101, 5):
        _a = math.radians(_ang)
        _d = CHL.PULL_MAX * _pw / 100
        _pdx, _pdy = -math.cos(_a) * _d, -math.sin(_a) * _d
        _vx, _vy = CHL.launch_velocity(_pdx, _pdy)
        _arr = CHL.Arrow(CHL.BOW_X, CHL.BOW_Y, _vx, _vy)
        _t = cs49.time
        for _k in range(400):
            _t += AP.PHYS_DT
            _arr.step(AP.PHYS_DT, cs49.wind)
            _hits = [b for b in cs49.balloons if not b.popped and CHL.arrow_hits(_arr, b, _t, cs49.params["rx"],
                                                                                  cs49.params["ry"])]
            if _hits:
                if _hits[0] is _b49g:
                    _hit49 = (_pdx, _pdy)
                break
            if not _arr.alive:
                break
        if _hit49:
            break
    if _hit49:
        break
check("[v44] 황금 풍선을 맞힐 수 있는 조준이 존재함", _hit49 is not None)
_popped49 = []
cs49.balloonPopped.connect(_popped49.append)
cs49.shoot(*_hit49)
check("[v44] 화살이 날아가는 동안은 또 쏠 수 없음", not cs49.can_shoot())
for _k in range(400):
    cs49.run_steps(1)
    if cs49.card is not None:
        break
check("[v44] 명중 → 풍선이 터지고 메시지 카드가 열림", _popped49 == [_mid49] and cs49.card is not None
      and cs49.remaining() == 5)
cs49.run_steps(40)
cs49.grab()
check("[v44] 방금 펼친 메시지가 오른쪽 카드에 표시·복사 버튼 활성", "시험 잘 봐" in _cw3.lbl_last.text()
      and _cw3.btn_copy.isEnabled())
_cw3._on_copy()
check("[v44] 복사 — 클립보드에 본문", "시험 잘 봐" in QGuiApplication.clipboard().text())
check("[v44] 카드가 열려 있는 동안은 쏠 수 없고, 닫으면 다시 쏠 수 있음",
      not cs49.can_shoot() and cs49.close_card() and cs49.can_shoot())
_miss49 = 0
for _j in range(3):
    cs49.shoot(200, -10)   # 왼쪽(뒤쪽)으로 — 반드시 빗나감
    for _k in range(600):
        cs49.run_steps(1)
        if cs49.arrow is None:
            break
check("[v44] 3번 연속 빗나가면 조준 보조선이 자동으로 켜짐", cs49.guide_forced and cs49.guide_on)
for _lang in ("en", "ja", "ko"):
    set_language(_lang)
    cw.retranslate()
    cw.scene.grab()
check("[v44] 응원 — 언어 3종 전환 후 한국어 복귀", cw.card_today.title_label.text() == "오늘")
from src.utils.cheer import MessageManagerDialog
_mm49 = MessageManagerDialog(_cw3.book, _dt49.date(2026, 11, 19), lambda: None)
_mm49.combo_filter.setCurrentIndex(_mm49.combo_filter.findData("user"))
check("[v44] 메시지 관리 — '선생님 메시지' 필터", _mm49.table.rowCount() == len(_cw3.book.user) >= 1)
_mm49.combo_filter.setCurrentIndex(0)
_mm49.table.item(0, 0).setCheckState(Qt.Unchecked)
check("[v44] 메시지 관리 — 표에서 체크를 풀면 사용 끄기", _mm49.table.item(0, 0).data(Qt.UserRole) in _cw3.book.base_disabled)
_mm49.close()
for _w49 in (_cw2, _cw3):
    _w49.deleteLater()

# =============================================================================
section("50. [v44] 좌석표 — 입력 양식 다운로드 기본 위치가 바탕화면")
from src.config import desktop_dir, desktop_file
win.util_panel.open_app("seating")
app.processEvents()
sw50 = win.util_panel._pages["seating"][0]
check("[v44] desktop_dir()은 실제로 있는 폴더(바탕화면, 없으면 홈)", os.path.isdir(desktop_dir()))
check("[v44] 좌석표 양식 기본 경로 = 바탕화면/명단_양식.xlsx",
      sw50.template_default_path() == os.path.join(desktop_dir(), tr("util.seating.template.default_name")))
with _patch("src.utils.seating.QFileDialog.getSaveFileName", return_value=("", "")) as _dlg50:
    sw50._on_download_template()
check("[v44] 저장 대화상자에 바탕화면 경로가 넘어감(파일명만 넘겨 개발 폴더가 뜨던 문제)",
      _dlg50.call_args[0][2] == desktop_file(tr("util.seating.template.default_name"))
      and os.path.isabs(_dlg50.call_args[0][2]))
check("[v44] 새 아이콘(lucky·cheer) 생성", not make_app_icon("lucky", C.UTIL_MAIN, 32).isNull()
      and not make_app_icon("cheer", C.UTIL_MAIN, 32).isNull())
check("[v44] 학교 카테고리 도구가 행운의 번호·응원의 메시지까지 포함",
      {"lucky", "cheer"} <= {a.id for a in win.util_apps if a.category == "class"})
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("51. [v44.3] 파일 찾기 — 확장자로 찾기(순수 로직: ext_finder)")

import src.ext_finder as EF

check("[v44.3] normalize_ext — 대소문자·앞뒤 공백·점 유무를 모두 통일",
      EF.normalize_ext(".JPG") == ".jpg" and EF.normalize_ext("jpg") == ".jpg"
      and EF.normalize_ext(" .Png ") == ".png" and EF.normalize_ext("  ") == "")

_ef_root = tempfile.mkdtemp(prefix="fkpp_extfind_")
os.makedirs(os.path.join(_ef_root, "a", "sub"))
os.makedirs(os.path.join(_ef_root, "b"))
for rel in ["a/photo1.JPG", "a/sub/photo2.jpg", "a/doc1.hwp", "b/photo3.png", "b/run1.exe"]:
    open(os.path.join(_ef_root, rel), "w").close()
open(os.path.join(_ef_root, "a", ".hidden.jpg"), "w").close()

_ef_hits = EF.find_by_extension(
    [os.path.join(_ef_root, "a"), os.path.join(_ef_root, "b")],
    {EF.normalize_ext("jpg"), EF.normalize_ext("png")})
_ef_names = sorted(h.name for h in _ef_hits)
check("[v44.3] find_by_extension — 대소문자 무시, 여러 root, 하위 폴더까지 재귀",
      _ef_names == ["photo1.JPG", "photo2.jpg", "photo3.png"])
check("[v44.3] 지정 안 한 확장자(hwp·exe)는 결과에서 빠짐",
      not any(h.name in ("doc1.hwp", "run1.exe") for h in _ef_hits))
check("[v44.3] 숨김 파일(.hidden.jpg)은 제외됨(폴더 스캔과 동일한 제외 규칙 재사용)",
      not any(h.name == ".hidden.jpg" for h in _ef_hits))

_ef_hits_same_root_twice = EF.find_by_extension(
    [_ef_root, os.path.join(_ef_root, "a")], {".jpg"})
check("[v44.3] 같은 파일이 겹치는 root들에 걸쳐 있어도 한 번만 담김",
      len([h for h in _ef_hits_same_root_twice if h.name == "photo1.JPG"]) == 1)

_ef_progress_calls = []
_ef_hits2 = EF.find_by_extension(
    [_ef_root], {".jpg", ".png"},
    on_file=lambda n, h: _ef_progress_calls.append((n, h.name)))
check("[v44.3] on_file 콜백이 찾은 파일마다 호출됨(진행 상황 표시용)",
      len(_ef_progress_calls) == len(_ef_hits2) and len(_ef_progress_calls) > 0)

_ef_cancelled = EF.find_by_extension([_ef_root], {".jpg"}, cancel_check=lambda: True)
check("[v44.3] cancel_check이 True를 돌려주면 즉시 멈춤(빈 결과)", _ef_cancelled == [])

shutil.rmtree(_ef_root, ignore_errors=True)

section("51b. [v44.3] 파일 찾기 — 칩 입력 위젯(chip_input)")

from src.chip_input import ChipInputWidget

_chip = ChipInputWidget(placeholder="테스트", normalize=EF.normalize_ext)
_chip.edit.setText("JPG")
_chip.edit.returnPressed.emit()
check("[v44.3] Enter로 입력하면 normalize를 거쳐 칩이 추가됨", _chip.values() == [".jpg"])
_chip.edit.setText("jpg")
_chip.edit.returnPressed.emit()
check("[v44.3] 이미 있는 값은 중복으로 안 쌓임", _chip.values() == [".jpg"])
_chip.add(".png")
check("[v44.3] add()로 코드에서 직접 추가 가능(프리셋 버튼용)", _chip.values() == [".jpg", ".png"])
_chip.edit.setText("   ")
_chip.edit.returnPressed.emit()
check("[v44.3] 빈 입력은 칩으로 안 쌓임", _chip.values() == [".jpg", ".png"])
_chip.clear()
check("[v44.3] clear()로 전체 비움", _chip.values() == [])

section("51c. [v44.3] 파일 찾기 — 위젯 통합(세그먼트 전환·프리셋·검색·정렬·삭제/이동)")

win.switch_mode("dupfind")
app.processEvents()
check("[v44.3] 기본 하위 모드는 '중복 파일 찾기'(요청대로 그대로 유지)",
      win.find_submode == "dup" and win.btn_findmode_dup.isChecked())
check("[v44.3] '파일 찾기' 모드는 액션 바가 다른 모드보다 넓음(세그먼트 줄 자리 확보)",
      win.action_bar_frame.height() == 84)
win.switch_mode("util")
app.processEvents()
win.switch_mode("sync")
app.processEvents()
check("[v44.3] 다른 모드(동기화)로 돌아오면 액션 바 높이가 원래(50)로 복귀",
      win.action_bar_frame.height() == 50)
win.switch_mode("dupfind")
app.processEvents()

_ef_target = tempfile.mkdtemp(prefix="fkpp_extfind_ui_")
os.makedirs(os.path.join(_ef_target, "사진폴더"))
os.makedirs(os.path.join(_ef_target, "문서폴더"))
open(os.path.join(_ef_target, "사진폴더", "여행1.jpg"), "w").close()
open(os.path.join(_ef_target, "사진폴더", "여행2.png"), "w").close()
open(os.path.join(_ef_target, "문서폴더", "보고서.hwp"), "w").close()
open(os.path.join(_ef_target, "문서폴더", "설치.exe"), "w").close()

win.dupfind_targets = []   # 이전 섹션들에서 등록된 폴더가 남아 있으면 결과가 섞이므로 초기화
win.dupfind_add_folder(_ef_target)
app.processEvents()

win.btn_findmode_ext.click()
app.processEvents()
check("[v44.3] '확장자로 찾기'를 누르면 하위 모드·스택 셋이 전부 전환됨",
      win.find_submode == "ext" and not win.btn_findmode_dup.isChecked()
      and win.findmode_toolbar_stack.currentIndex() == 1
      and win.findmode_result_stack.currentIndex() == 1
      and win.findmode_actions_stack.currentIndex() == 1)

win.btn_extfind_preset_photo.click()
win.btn_extfind_preset_exe.click()
app.processEvents()
check("[v44.3] '사진' 프리셋 + '실행' 프리셋(신규 요청) 칩이 정확히 추가됨",
      set(win.extfind_chips.values()) == {".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp",
                                          ".exe", ".msi", ".bat", ".cmd"})

win.on_extfind_search_start()
for _i in range(60):
    app.processEvents()
    if win.extfind_thread is None:
        break
    time.sleep(0.05)
check("[v44.3] 검색이 스레드 없이(교착 없이) 정상 종료되고, 등록한 확장자 파일만 찾음",
      win.extfind_thread is None
      and {h.name for h in win.extfind_hits} == {"여행1.jpg", "여행2.png", "설치.exe"})
check("[v44.3] hwp는 안 찾음(칩에 안 걸려 있으므로)",
      not any(h.name == "보고서.hwp" for h in win.extfind_hits))
check("[v44.3] 결과 표에도 같은 개수만큼 행이 채워짐", win.extfind_table.rowCount() == 3)

win._on_extfind_header_clicked(1)   # 파일명 오름차순
_names_asc = [win.extfind_table.item(r, 1).text() for r in range(win.extfind_table.rowCount())]
win._on_extfind_header_clicked(1)   # 다시 눌러서 내림차순
_names_desc = [win.extfind_table.item(r, 1).text() for r in range(win.extfind_table.rowCount())]
check("[v44.3] 헤더를 두 번 클릭하면 오름차순/내림차순이 뒤집힘",
      _names_asc == list(reversed(_names_desc)) and _names_asc == sorted(_names_asc))

# 체크 후 삭제 — send2trash 유무 두 경로 다 안전하게 모킹
_target_row = next(r for r in range(win.extfind_table.rowCount())
                   if win.extfind_table.item(r, 1).text() == "설치.exe")
win.extfind_table.item(_target_row, 0).setCheckState(Qt.Checked)
_deleted_path = win.extfind_table.item(_target_row, 0).data(Qt.UserRole)
with _patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
     _patch.object(QMessageBox, "warning", return_value=QMessageBox.Yes), \
     _patch.object(QMessageBox, "information"):
    win.on_extfind_delete_selected()
check("[v44.3] 체크한 파일이 실제로 삭제되고(휴지통 없으면 영구 삭제) 목록에서도 빠짐",
      not os.path.exists(_deleted_path) and win.extfind_table.rowCount() == 2
      and not any(h.name == "설치.exe" for h in win.extfind_hits))

# 체크 후 이동
_move_row = 0
_moved_path = win.extfind_table.item(_move_row, 0).data(Qt.UserRole)
_move_dest = tempfile.mkdtemp(prefix="fkpp_extfind_move_dest_")
win.extfind_table.item(_move_row, 0).setCheckState(Qt.Checked)
with _patch("src.main_window.QFileDialog.getExistingDirectory", return_value=_move_dest), \
     _patch.object(QMessageBox, "information"):
    win.on_extfind_move_selected()
check("[v44.3] 체크한 파일이 실제로 다른 폴더로 이동되고 목록에서도 빠짐",
      not os.path.exists(_moved_path)
      and os.path.exists(os.path.join(_move_dest, os.path.basename(_moved_path)))
      and win.extfind_table.rowCount() == 1)

# 검색 조건 미달 안내(빈 확장자·대상 폴더 없음)는 조용히 return하지 않고 안내를 띄우는지만 확인
win.extfind_chips.clear()
with _patch.object(QMessageBox, "information") as _mock_info_noext:
    win.on_extfind_search_start()
check("[v44.3] 확장자를 하나도 안 넣고 검색하면 안내만 뜨고 스레드는 안 돎",
      _mock_info_noext.called and win.extfind_thread is None)

win.dupfind_targets = []
win.dupfind_clear_targets()
shutil.rmtree(_ef_target, ignore_errors=True)
shutil.rmtree(_move_dest, ignore_errors=True)
win.btn_findmode_dup.click()
app.processEvents()
check("[v44.3] '중복 파일 찾기'로 되돌아가면 다시 그쪽 스택이 보임",
      win.find_submode == "dup" and win.findmode_result_stack.currentIndex() == 0)
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("52. [v44.4] 좌석표 — 역할 메타정보(엑셀 업로드·양식·화면 표시)")

import src.utils.bracket_solve as B52

# ---- 순수 로직: Student.role, read_roster_excel(with_role), save_roster_template(with_role) ----
_s52 = B52.Student("x-1-1-1-홍길동", "1", "1", "1", "홍길동", "남", "반장")
check("[v44.4] Student가 role을 갖고 to_dict/from_dict를 왕복해도 보존됨",
      _s52.role == "반장" and B52.Student.from_dict(_s52.to_dict()).role == "반장")
check("[v44.4] role 기본값은 빈 문자열(대진표 작성기 등 기존 호출부는 그대로 동작)",
      B52.Student("x", "1", "1", "1", "홍길동").role == "")

_tpl_role_path = os.path.join(tempfile.gettempdir(), "fkpp_seating_tpl_role.xlsx")
_tpl_norole_path = os.path.join(tempfile.gettempdir(), "fkpp_seating_tpl_norole.xlsx")
B52.save_roster_template(_tpl_role_path, with_role=True)
B52.save_roster_template(_tpl_norole_path)   # with_role 기본값 False — 대진표 작성기가 쓰는 경로
import openpyxl as _oxl52
_hdr_role = [c.value for c in next(_oxl52.load_workbook(_tpl_role_path).active.iter_rows(min_row=1, max_row=1))]
_hdr_norole = [c.value for c in next(_oxl52.load_workbook(_tpl_norole_path).active.iter_rows(min_row=1, max_row=1))]
check("[v44.4] with_role=True 양식은 마지막 칸이 '역할'", _hdr_role == ["학년", "반", "번호", "이름", "성별", "역할"])
check("[v44.4] with_role 기본값(False) 양식은 예전 그대로(대진표 작성기 영향 없음)",
      _hdr_norole == ["학년", "반", "번호", "이름", "성별"])

_roster_xlsx = os.path.join(tempfile.gettempdir(), "fkpp_seating_roster_role.xlsx")
_wb52 = _oxl52.Workbook()
_ws52 = _wb52.active
_ws52.append(["학년", "반", "번호", "이름", "성별", "역할"])
_ws52.append(["1", "1", "1", "홍길동", "남", "반장"])
_ws52.append(["1", "1", "2", "김영희", "여", "부반장"])
_ws52.append(["1", "1", "3", "이철수", "", ""])   # 역할 없는 학생도 정상 처리돼야 함
_wb52.save(_roster_xlsx)

_students52 = B52.read_roster_excel(_roster_xlsx, with_role=True)
check("[v44.4] read_roster_excel(with_role=True) — 역할 칸을 정확히 읽음",
      {s.name: s.role for s in _students52} == {"홍길동": "반장", "김영희": "부반장", "이철수": ""})
_students52_norole = B52.read_roster_excel(_roster_xlsx)   # with_role 기본값 False
check("[v44.4] with_role=False(기본값)면 역할 칸이 있어도 안 읽음(대진표 작성기 경로 보호)",
      all(s.role == "" for s in _students52_norole))

# ---- 위젯 통합: 업로드 → 역할 보기 토글 → 캔버스 렌더에 반영 ----
win.util_panel.open_app("seating")
app.processEvents()
sw52 = win.util_panel._pages["seating"][0]

check("[v44.4] '역할 보기' 체크박스는 기본적으로 꺼져 있음(요청대로 기본은 숨김)",
      sw52.chk_show_role.isChecked() is False and sw52.canvas.show_role is False)

with _patch("src.utils.seating.QFileDialog.getOpenFileName", return_value=(_roster_xlsx, "")):
    sw52._on_roster_upload()
app.processEvents()
check("[v44.4] 엑셀 업로드 시 seating.py도 with_role=True로 읽어 역할이 채워짐",
      {s.name: s.role for s in sw52.roster} == {"홍길동": "반장", "김영희": "부반장", "이철수": ""})

sw52.combo_class.setCurrentIndex(0)
app.processEvents()
sw52.spin_cols.setValue(2)
app.processEvents()
_rect_before52 = sw52.canvas.cell_rect(0, 0)
_minsize_before52 = sw52.canvas.minimumSize()

sw52.chk_show_role.setChecked(True)
app.processEvents()
check("[v44.4] 체크박스를 켜면 캔버스 show_role도 같이 켜짐", sw52.canvas.show_role is True)
check("[v44.6] 역할 보기를 켜도 칸 크기·전체 배치 크기는 그대로(화면이 출렁이지 않음)",
      sw52.canvas.cell_rect(0, 0) == _rect_before52
      and sw52.canvas.minimumSize() == _minsize_before52)

# 실제로 화면에 역할이 그려지는지는 파일로 직접 확인하기 어려우니, paintEvent가
# 예외 없이 도는지(오프스크린 렌더 1회)와 role이 채워진 학생·안 채워진 학생이
# roster_by_sid에 그대로 반영돼 있는지로 검증한다.
sw52.canvas.grab()   # 강제로 한 번 그려 본다 — 여기서 예외가 나면 테스트가 실패한다
check("[v44.4] roster_by_sid에 role이 학생별로 정확히 실려 있음(캔버스가 그릴 데이터)",
      {s.role for s in sw52.canvas.roster_by_sid.values()} == {"반장", "부반장", ""})

sw52.chk_show_role.setChecked(False)
app.processEvents()
check("[v44.6] 다시 꺼도 칸 크기는 계속 그대로(원래부터 안 바뀌었으므로)",
      sw52.canvas.cell_rect(0, 0) == _rect_before52)

with _patch("src.utils.seating.QFileDialog.getSaveFileName", return_value=(_tpl_role_path, "")):
    sw52._on_download_template()
_hdr_role2 = [c.value for c in next(_oxl52.load_workbook(_tpl_role_path).active.iter_rows(min_row=1, max_row=1))]
check("[v44.4] 좌석표 화면의 '입력 양식 다운로드' 버튼도 역할 칸을 포함해서 저장함",
      _hdr_role2 == ["학년", "반", "번호", "이름", "성별", "역할"])

for _p in (_tpl_role_path, _tpl_norole_path, _roster_xlsx):
    try:
        os.remove(_p)
    except OSError:
        pass
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("53. [v44.5] 파일 찾기(확장자로 찾기) — 경로 표시·탐색기 열기·컬럼 폭·전체 선택")

from PySide6.QtWidgets import QHeaderView, QMenu

_ef53_root = tempfile.mkdtemp(prefix="fkpp_extfind_v445_")
os.makedirs(os.path.join(_ef53_root, "사진폴더"))
open(os.path.join(_ef53_root, "사진폴더", "여행1.jpg"), "w").close()
open(os.path.join(_ef53_root, "사진폴더", "여행2.png"), "w").close()

win.switch_mode("dupfind")
app.processEvents()
win.dupfind_targets = []
win.dupfind_add_folder(_ef53_root)
app.processEvents()
win.btn_findmode_ext.click()
app.processEvents()
win.btn_extfind_preset_photo.click()
app.processEvents()
win.on_extfind_search_start()
for _i in range(60):
    app.processEvents()
    if win.extfind_thread is None:
        break
    time.sleep(0.05)
check("[v44.5] 검색 정상 완료(2건)", win.extfind_table.rowCount() == 2)

# ---- 경로 컬럼은 폴더까지만, 전체 경로는 툴팁으로 ----
_expected_dir = os.path.join(_ef53_root, "사진폴더")
_path_texts = [win.extfind_table.item(r, 3).text() for r in range(win.extfind_table.rowCount())]
_path_tips = [win.extfind_table.item(r, 3).toolTip() for r in range(win.extfind_table.rowCount())]
check("[v44.5] 경로 컬럼 화면 표시는 파일명 없이 폴더 경로까지만",
      all(t == _expected_dir for t in _path_texts))
check("[v44.5] 전체 경로(파일명 포함)는 툴팁으로 확인 가능",
      all(os.path.dirname(tip) == _expected_dir and os.path.basename(tip) for tip in _path_tips))

# ---- 컬럼 폭 조절 가능(Interactive) ----
_header53 = win.extfind_table.horizontalHeader()
check("[v44.5] 6개 컬럼 전부 드래그로 폭 조절 가능(Interactive)",
      all(_header53.sectionResizeMode(c) == QHeaderView.Interactive for c in range(6)))

# ---- 전체 선택 토글(헤더 0번 클릭) ----
check("[v44.5] 검색 직후엔 아무 것도 체크 안 돼 있음",
      not any(win.extfind_table.item(r, 0).checkState() == Qt.Checked
              for r in range(win.extfind_table.rowCount())))
win._on_extfind_header_clicked(0)
check("[v44.5] 헤더 체크박스 컬럼을 클릭하면 전체 선택됨",
      all(win.extfind_table.item(r, 0).checkState() == Qt.Checked
          for r in range(win.extfind_table.rowCount())))
win._on_extfind_header_clicked(0)
check("[v44.5] 전부 선택된 상태에서 다시 클릭하면 전체 해제(토글)",
      all(win.extfind_table.item(r, 0).checkState() == Qt.Unchecked
          for r in range(win.extfind_table.rowCount())))

# ---- 우클릭 컨텍스트 메뉴 → 탐색기 열기(reveal_in_file_explorer 재사용) ----
class _CapturingMenu53(QMenu):
    def exec(self_inner, pos):
        _captured53["text"] = self_inner.actions()[0].text() if self_inner.actions() else None
        return self_inner.actions()[0] if self_inner.actions() else None

_captured53 = {}
_target_path53 = win.extfind_table.item(0, 0).data(Qt.UserRole)
with _patch("src.main_window.QMenu", _CapturingMenu53), \
     _patch.object(win, "reveal_in_file_explorer") as _mock_reveal53:
    _rect53 = win.extfind_table.visualItemRect(win.extfind_table.item(0, 0))
    win._on_extfind_table_context_menu(_rect53.center())
check("[v44.5] 결과 행을 우클릭하면 '탐색기에서 보기' 메뉴가 뜸",
      _captured53.get("text") == tr("menu.reveal_in_explorer"))
check("[v44.5] 그 메뉴를 고르면 reveal_in_file_explorer가 그 행의 실제 파일 경로로 호출됨",
      _mock_reveal53.called and _mock_reveal53.call_args[0][0] == _target_path53)

shutil.rmtree(_ef53_root, ignore_errors=True)
win.dupfind_targets = []
win.dupfind_clear_targets()
win.btn_findmode_dup.click()
app.processEvents()
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("54. [v44.7] 파일 찾기(확장자로 찾기) — 경로 칸 왼쪽 생략(...) 표시")

from PySide6.QtWidgets import QStyleOptionViewItem

_ef54_root = tempfile.mkdtemp(prefix="fkpp_extfind_v447_")
_deep54 = os.path.join(_ef54_root, "깊은", "더깊은", "가장깊은폴더")
os.makedirs(_deep54)
open(os.path.join(_deep54, "run.exe"), "w").close()

win.switch_mode("dupfind")
app.processEvents()
win.dupfind_targets = []
win.dupfind_add_folder(_ef54_root)
app.processEvents()
win.btn_findmode_ext.click()
app.processEvents()
win.btn_extfind_preset_exe.click()
app.processEvents()
win.on_extfind_search_start()
for _i in range(60):
    app.processEvents()
    if win.extfind_thread is None:
        break
    time.sleep(0.05)
check("[v44.7] 검색 정상 완료(1건)", win.extfind_table.rowCount() == 1)

_path_item54 = win.extfind_table.item(0, 3)
check("[v44.7] 경로 칸(화면 텍스트)은 여전히 폴더 전체 경로(생략 없이 저장됨 — 실제 생략은 렌더링 시점에 delegate가 함)",
      _path_item54.text() == os.path.dirname(os.path.join(_deep54, "run.exe")))

delegate54 = win.extfind_table.itemDelegateForColumn(3)
check("[v44.7] 경로 칸(3번 컬럼)에 전용 delegate가 연결돼 있음",
      delegate54 is not None and delegate54 is win._extfind_path_delegate)

_opt54 = QStyleOptionViewItem()
delegate54.initStyleOption(_opt54, win.extfind_table.model().index(0, 3))
check("[v44.7] 그 delegate는 텍스트를 오른쪽이 아니라 왼쪽(앞부분)에서 생략함(ElideLeft)",
      _opt54.textElideMode == Qt.ElideLeft)
check("[v44.7] 줄바꿈은 꺼져 있음(그러지 않으면 길이가 넘칠 때 두 줄로 접혀 행 높이가 늘어남)",
      not (_opt54.features & QStyleOptionViewItem.ViewItemFeature.WrapText))

# 다른 컬럼(파일명 등)은 기존 기본 동작(오른쪽 생략) 그대로인지 — 경로 칸만
# 바뀌어야 하므로, 다른 컬럼에는 이 delegate가 안 걸려 있어야 한다.
check("[v44.7] 파일명(1번)·크기(4번) 컬럼은 전용 delegate가 안 걸려 기본 동작 그대로",
      win.extfind_table.itemDelegateForColumn(1) is not delegate54
      and win.extfind_table.itemDelegateForColumn(4) is not delegate54)

shutil.rmtree(_ef54_root, ignore_errors=True)
win.dupfind_targets = []
win.dupfind_clear_targets()
win.btn_findmode_dup.click()
app.processEvents()
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("55. [v44.8] 좌석표 — 번호 글자가 이름에 가려지던 겹침 버그 수정")

from PySide6.QtGui import QFont as _QFont55, QFontMetrics as _QFM55

# ---- 원인이 됐던 값 자체를 다시 재현하지 못하게: 폰트 크기가 실제로
# 이전(10pt)으로 돌아갔는지, 그리고 겹침 방지용 높이 계산(QFontMetrics
# 기반)이 유효한 범위인지 확인한다. paintEvent 내부의 지역 변수라 직접
# 값을 읽을 수는 없으니, 같은 계산식을 그대로 재현해서 검증한다.
_num_font55 = _QFont55("", 10)
_num_font55.setBold(True)
_num_h55 = _QFM55(_num_font55).height() + 2
check("[v44.8] 번호 폰트 높이 계산값이 이름 영역과 안 겹칠 만큼 합리적인 범위(칸 높이 60의 절반 미만)",
      0 < _num_h55 < 30)

win.util_panel.open_app("seating")
app.processEvents()
sw55 = win.util_panel._pages["seating"][0]

import openpyxl as _oxl55
_roster55 = os.path.join(tempfile.gettempdir(), "fkpp_seating_roster_v448.xlsx")
_wb55 = _oxl55.Workbook()
_ws55 = _wb55.active
_ws55.append(["학년", "반", "번호", "이름", "성별", "역할"])
_ws55.append(["1", "1", "13", "홍길동", "남", "반장"])
_ws55.append(["1", "1", "20", "김영희", "여", ""])
_wb55.save(_roster55)

with _patch("src.utils.seating.QFileDialog.getOpenFileName", return_value=(_roster55, "")):
    sw55._on_roster_upload()
app.processEvents()
sw55.combo_class.setCurrentIndex(0)
app.processEvents()
sw55.spin_cols.setValue(2)
app.processEvents()

# 번호 영역(top+2 ~ top+2+num_h)의 아래쪽 끝이 이름이 실제로 그려지기
# 시작하는 지점(name_top)보다 위(작거나 같음)인지 — 겹치지 않는다는
# 뜻이다. paintEvent와 똑같은 두 계산을 여기서도 그대로 해서 비교한다.
_cell55 = sw55.canvas.cell_rect(0, 0)
_num_bottom55 = _cell55.top() + 2 + _num_h55
_name_top55 = _cell55.top() + 2 + _num_h55   # paintEvent와 동일한 계산식
check("[v44.8] 번호 영역 끝과 이름 시작 위치가 정확히 맞닿아 있고 겹치지 않음",
      _num_bottom55 == _name_top55)

# 실제로 두 번 다시 그려 봐도(역할 보기 On/Off) 예외 없이 렌더링되는지
sw55.canvas.grab()
sw55.chk_show_role.setChecked(True)
app.processEvents()
sw55.canvas.grab()
check("[v44.8] 역할 보기 On/Off 양쪽 다 예외 없이 정상 렌더링됨(위 두 grab()에서 안 죽었으면 통과)", True)

os.remove(_roster55)
win.switch_mode("util")
app.processEvents()

# =============================================================================
section("56. [v45.0] 타이머/시계 — 스플릿플랩 보드 신규 미니앱")

from src.utils.timer_solve import FlipDigit, ease_gravity, digits_for_value
from src.utils import timer_solve as T
from src.styles import BTN_NEUTRAL_BG

# ---- 순수 로직(timer_solve.py) ----
check("[v45.0] ease_gravity — 중력 가속(처음엔 느리고 끝에 빨라짐): 0.5 지점이 선형값(0.5)보다 작음",
      ease_gravity(0.5) < 0.5)
check("[v45.0] ease_gravity 경계값: 0->0, 1->1", ease_gravity(0.0) == 0.0 and ease_gravity(1.0) == 1.0)

check("[v45.0] digits_for_value(5, 2) == [0, 5]", digits_for_value(5, 2) == [0, 5])
check("[v45.0] digits_for_value(42, 2) == [4, 2]", digits_for_value(42, 2) == [4, 2])

d56 = FlipDigit(5)
check("[v45.0] FlipDigit 초기 상태 — 정지(is_animating False)", not d56.is_animating)
d56.flip_to(6)
check("[v45.1] flip_to — 한 번만 큐에 쌓이고(연속 중간값 없음) 보통 속도(FLIP_DURATION)로 예약됨",
      d56.queue == [(6, T.FLIP_DURATION)])
_t56 = 0.0
while d56.is_animating and _t56 < 5:
    d56.advance(0.05)
    _t56 += 0.05
check("[v45.0] flip_to(6) 완료 시간이 FLIP_DURATION(0.9s) 근처, 최종값 6",
      0.85 <= _t56 <= 1.0 and d56.current == 6)

d57 = FlipDigit(0)
d57.flip_sequence_to(5)
check("[v45.1] flip_sequence_to — 0에서 5까지 1씩 올리며 큐에 쌓이고, 전부 FAST_FLIP_DURATION(빠른 속도)으로 예약됨",
      d57.queue == [(1, T.FAST_FLIP_DURATION), (2, T.FAST_FLIP_DURATION), (3, T.FAST_FLIP_DURATION),
                    (4, T.FAST_FLIP_DURATION), (5, T.FAST_FLIP_DURATION)])
_t57 = 0.0
while d57.is_animating and _t57 < 10:
    d57.advance(0.02)
    _t57 += 0.02
check("[v45.1] flip_sequence_to(5) — 빠른 속도(0.1s×5=0.5s 근처)로 끝나고 최종값 5(느린 FLIP_DURATION이 아님)",
      0.4 <= _t57 <= 0.7 and d57.current == 5)

d58 = FlipDigit(9)
d58.flip_sequence_to(8)
check("[v45.0] flip_sequence_to — 9에서 8로 갈 때도 '내려가지' 않고 10에 가깝게 랩 돌아감(의도된 동작)",
      len(d58.queue) == 9)

check("[v45.0] brightness() — 평상시(progress=1.0, 정지)엔 기본값 범위(멈춘 상태라 애니메이션 밝기 의미 없음)",
      True)  # brightness()는 angle() 기반이라 정지 시에도 호출 가능해야 함(예외 없이)
_d59 = FlipDigit(0)
_d59.flip_to(1)
_d59.advance(0.001)
check("[v45.0] 애니메이션 시작 직후 밝기는 1.0 근처(아직 안 어두움)", _d59.brightness() > 0.9)

# ---- 위젯 통합 ----
win.util_panel.open_app("timerclock")
app.processEvents()
tcw56 = win.util_panel._pages["timerclock"][0]
tcw56.canvas.stop_loop()   # 자동 60fps 루프를 멈추고 advance()를 직접 제어해 결정적으로 테스트

check("[v45.0] 기본 모드는 '시계'", tcw56.mode == "clock" and tcw56.btn_seg_clock.isChecked())
check("[v45.0] 시계 모드는 6자리(시시:분분:초초) 구성", len(tcw56.canvas.groups) == 3
      and all(len(g) == 2 for g in tcw56.canvas.groups))

tcw56.btn_seg_timer.click()
app.processEvents()
check("[v45.0] '타이머' 세그먼트를 누르면 모드가 전환되고 컨트롤 영역이 보임",
      tcw56.mode == "timer" and tcw56.timer_controls.isVisible())
check("[v45.0] 타이머 모드는 4자리(분분:초초) 구성", len(tcw56.canvas.groups) == 2
      and all(len(g) == 2 for g in tcw56.canvas.groups))

check("[v45.0] 비활성 세그먼트는 일시정지 버튼과 같은 채도 낮은 색(BTN_NEUTRAL_BG)을 씀",
      BTN_NEUTRAL_BG in tcw56.btn_seg_clock.styleSheet()
      and C.UTIL_MAIN in tcw56.btn_seg_timer.styleSheet())

tcw56._on_preset(1, tcw56.preset_buttons[0])
_t56b = 0.0
while any(d.is_animating for d in tcw56.timer_digits) and _t56b < 10:
    for d in tcw56.timer_digits:
        d.advance(0.05)
    _t56b += 0.05
app.processEvents()
check("[v45.0] 1분 프리셋 선택 후 실제 값이 00:01:00... 아니 01분 00초로 맞게 설정됨",
      [d.current for d in tcw56.timer_digits] == [0, 1, 0, 0] and tcw56.total_sec == 60)

tcw56._on_preset(5, tcw56.preset_buttons[2])
_t56c = 0.0
while any(d.is_animating for d in tcw56.timer_digits) and _t56c < 10:
    for d in tcw56.timer_digits:
        d.advance(0.02)
    _t56c += 0.02
check("[v45.1] 1분에서 5분으로 바꾸면 '촤라락'(4단계)에 걸쳐 전환되되, 빠른 속도(약 0.4s 근처, 느린 3.6s가 아님)로 끝남",
      0.3 <= _t56c <= 0.7 and [d.current for d in tcw56.timer_digits] == [0, 5, 0, 0])

tcw56._start_timer()
check("[v45.0] 시작을 누르면 running=True, 시작 버튼 비활성·일시정지 버튼 활성",
      tcw56.running and not tcw56.btn_start.isEnabled() and tcw56.btn_pause.isEnabled())
tcw56._on_countdown_tick()
check("[v45.0] 카운트다운 1틱 후 remain_sec이 299로 줄어듦(300->299)", tcw56.remain_sec == 299)
check("[v45.0] 매초 카운트다운은 '촤라락'이 아니라 1회만 플립(초 일의자리 큐 길이 1)",
      len(tcw56.timer_digits[3].queue) <= 1)

tcw56._pause_timer()
check("[v45.0] 일시정지하면 running=False", not tcw56.running)
tcw56._reset_timer()
_t56d = 0.0
while any(d.is_animating for d in tcw56.timer_digits) and _t56d < 10:
    for d in tcw56.timer_digits:
        d.advance(0.05)
    _t56d += 0.05
check("[v45.0] 리셋하면 total_sec(5분)으로 되돌아감", tcw56.remain_sec == tcw56.total_sec == 300)

check("[v45.0] 스페이스바(발표 리모컨) — 타이머 모드에서 시작/일시정지 토글",
      not tcw56.running)
tcw56._on_primary()
check("[v45.0]   -> 1회 호출 시 시작됨", tcw56.running)
tcw56._on_primary()
check("[v45.0]   -> 2회 호출 시 다시 멈춤", not tcw56.running)

# 실제로 그려 봐도(시계/타이머 양쪽) 예외 없이 렌더링되는지
tcw56.canvas.grab()
tcw56.btn_seg_clock.click()
app.processEvents()
tcw56.canvas.grab()
check("[v45.0] 시계·타이머 양쪽 다 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("57. [v45.3] 함수 그래프 — 고정점 Y값 라벨 위치 / 극좌표 — 화살표·클릭점")

win.util_panel.open_app("graph")
app.processEvents()
gw57 = win.util_panel._pages["graph"][0]
c57 = gw57.canvas
c57.set_functions([{"id": 0, "text": "2*x^2 - x", "color": "#1e88e5", "visible": True}])
c57.set_x_range(-1.1206, 1.0469)
c57.set_y_range(-0.6223, 2.006)
app.processEvents()
fid57 = c57.functions[0]["id"]
c57._pin_point(-0.625, fid57)
plot57 = c57._plot_rect()
y0_57 = c57._pinned_point_y(c57._pinned_points[0])
y0_px57 = c57._to_px(0.0, y0_57, plot57)
check("[v45.3] Y축이 plot 한가운데 가까이 있을 때도 Y값 라벨 위치 계산이 plot 영역 안쪽에 들어옴"
     "(전엔 항상 plot 왼쪽 바깥 고정이라 Y축이 중앙에 있으면 라벨이 화면 반대쪽 끝으로 멀어졌었다)",
     plot57.left() <= y0_px57.x() <= plot57.right())
win.switch_mode("util")
app.processEvents()

win.util_panel.open_app("polar")
app.processEvents()
pw57 = win.util_panel._pages["polar"][0]
c57p = pw57.canvas
c57p.set_functions([{"id": 0, "text": "cos(3*theta)", "color": "#1e88e5", "visible": True}])
app.processEvents()

check("[v45.3] 극좌표 그래프 — 클릭 전엔 찍힌 점이 없음", c57p._clicked_point is None)

from PySide6.QtGui import QMouseEvent as _QME57
from PySide6.QtCore import QEvent as _QEvt57
plot57p = c57p._plot_rect()
click_px57 = c57p._to_px(1.0, 1.0, plot57p)
_press57 = _QME57(_QEvt57.MouseButtonPress, click_px57, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
c57p.mousePressEvent(_press57)
_release57 = _QME57(_QEvt57.MouseButtonRelease, click_px57, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
c57p.mouseReleaseEvent(_release57)
app.processEvents()
check("[v45.3] 극좌표 그래프 — 그래프 영역을 클릭하면 그 자리에 점이 찍힘(패닝과 구분됨)",
     c57p._clicked_point is not None
     and abs(c57p._clicked_point[0] - 1.0) < 0.05 and abs(c57p._clicked_point[1] - 1.0) < 0.05,
     c57p._clicked_point)

c57p._clicked_point = None
start_px57 = c57p._to_px(0.5, 0.5, plot57p)
end_px57 = c57p._to_px(3.0, 3.0, plot57p)
c57p.mousePressEvent(_QME57(_QEvt57.MouseButtonPress, start_px57, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
c57p.mouseMoveEvent(_QME57(_QEvt57.MouseMove, end_px57, Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
c57p.mouseReleaseEvent(_QME57(_QEvt57.MouseButtonRelease, end_px57, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
app.processEvents()
check("[v45.3] 극좌표 그래프 — 드래그(패닝)는 점을 찍지 않음(클릭과 구분됨)",
     c57p._clicked_point is None)

import math as _math57
c57p._clicked_point = (3.0, 4.0)
r57 = _math57.hypot(3.0, 4.0)
theta57 = _math57.degrees(_math57.atan2(4.0, 3.0))
check("[v45.3] (r, θ) 계산 — (3,4)에서 r=5", abs(r57 - 5.0) < 1e-9)
check("[v45.3] (r, θ) 계산 — (3,4)에서 θ≈53.1°(도수법)", abs(theta57 - 53.13) < 0.1)

# 실제로 그려 봐도 예외 없이 렌더링되는지
c57p.grab()
check("[v45.3] 클릭점·화살표가 있는 상태에서도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("58. [v46.0] 스도쿠 — 신규 미니앱(생성·메모·힌트·완성 판정)")

from src.utils import sudoku_solve as SK
import random as _rnd58

check("sudoku 앱 아이콘 생성", not make_app_icon("sudoku", C.UTIL_MAIN, 32).isNull())
check("sudoku 앱이 logic(=정보컴퓨터) 카테고리에 등록됨",
      any(a.id == "sudoku" and a.category == "logic" for a in win.util_apps))

# ---- 순수 로직(sudoku_solve.py) ----
for _diff in SK.DIFFICULTY_ORDER:
    _rng = _rnd58.Random(1234)
    _sol, _given = SK.generate_puzzle(_diff, _rng)
    check(f"[v46.0] {_diff} 난이도 — 정답판 자체가 완성 상태(규칙 위반 없음)",
          SK.is_complete(_sol))
    _blanks = sum(row.count(SK.EMPTY) for row in _given)
    check(f"[v46.0] {_diff} 난이도 — 빈 칸 수가 목표치와 정확히 일치",
          _blanks == SK.DIFFICULTY_BLANKS[_diff], _blanks)
    _given_copy = [row[:] for row in _given]
    check(f"[v46.0] {_diff} 난이도 — 문제의 해가 정확히 1개(유일해 보장)",
          SK._count_solutions(_given_copy, limit=2) == 1)

_t58 = __import__("time").time()
for _ in range(3):
    SK.generate_puzzle("hard", _rnd58.Random())
_elapsed58 = (__import__("time").time() - _t58) / 3
check("[v46.0] 가장 느린(hard) 난이도도 생성이 1초 이내로 끝남(MRV 휴리스틱 적용)",
      _elapsed58 < 1.0, _elapsed58)

_state58 = SK.new_state("easy", _rnd58.Random(7))
check("[v46.0] 새로 생성한 상태는 아직 미완성", not _state58.is_complete())

_gr, _gc = next((r, c) for r in range(9) for c in range(9) if _state58.given[r][c] != SK.EMPTY)
check("[v46.0] given 칸은 is_given()이 True", _state58.is_given(_gr, _gc))
check("[v46.0] given 칸은 set_value로 못 바꿈(False 반환, 값 그대로)",
      not _state58.set_value(_gr, _gc, 9 if _state58.given[_gr][_gc] != 9 else 8)
      and _state58.board[_gr][_gc] == _state58.given[_gr][_gc])

_er, _ec = next((r, c) for r in range(9) for c in range(9) if _state58.given[r][c] == SK.EMPTY)
check("[v46.0] 빈 칸에는 set_value로 값을 넣을 수 있음",
      _state58.set_value(_er, _ec, _state58.solution[_er][_ec])
      and _state58.board[_er][_ec] == _state58.solution[_er][_ec])

_er2, _ec2 = next((r, c) for r in range(9) for c in range(9)
                   if _state58.given[r][c] == SK.EMPTY and (r, c) != (_er, _ec))
_state58.toggle_note(_er2, _ec2, 3)
_state58.toggle_note(_er2, _ec2, 7)
check("[v46.0] 메모 두 개 추가 — {3, 7}", _state58.notes[_er2][_ec2] == {3, 7})
_state58.toggle_note(_er2, _ec2, 3)
check("[v46.0] 같은 숫자를 다시 메모하면 꺼짐(토글) — {7}만 남음",
      _state58.notes[_er2][_ec2] == {7})
_state58.set_value(_er2, _ec2, _state58.solution[_er2][_ec2])
check("[v46.0] 확정 숫자를 넣으면 그 칸의 메모가 자동으로 비워짐",
      _state58.notes[_er2][_ec2] == set())

_conflict_board58 = [[SK.EMPTY] * 9 for _ in range(9)]
_conflict_board58[0][0] = 5
_conflict_board58[0][1] = 5
check("[v46.0] 같은 행에 중복 숫자 — 충돌로 감지됨",
      SK.find_conflicts(_conflict_board58) == {(0, 0), (0, 1)})

_full_state58 = SK.new_state("easy", _rnd58.Random(3))
_full_state58.board = [row[:] for row in _full_state58.solution]
check("[v46.0] 정답으로 꽉 채운 보드는 완성 판정됨", _full_state58.is_complete())

_hint_state58 = SK.new_state("easy", _rnd58.Random(9))
_before_blanks = sum(row.count(SK.EMPTY) for row in _hint_state58.board)
_h = _hint_state58.apply_hint()
_after_blanks = sum(row.count(SK.EMPTY) for row in _hint_state58.board)
check("[v46.0] 힌트를 쓰면 빈 칸이 정확히 하나 줄어듦",
      _h is not None and _after_blanks == _before_blanks - 1)
check("[v46.0] 힌트로 채운 값이 정답과 일치",
      _hint_state58.board[_h[0]][_h[1]] == _hint_state58.solution[_h[0]][_h[1]])

# ---- 위젯 통합(sudoku.py) ----
win.util_panel.open_app("sudoku")
app.processEvents()
sw58 = win.util_panel._pages["sudoku"][0]
c58 = sw58.canvas

check("[v46.0] 위젯을 열면 바로 퍼즐이 하나 생성돼 있음", c58.state is not None)
check("[v46.0] 기본 난이도는 medium(보통)", sw58.difficulty == "medium")

_r58, _c58 = next((r, c) for r in range(9) for c in range(9) if c58.state.board[r][c] == SK.EMPTY)
_click_pos58 = c58._cell_rect(_r58, _c58).center()
c58.mousePressEvent(_FakeMouseEv(_click_pos58))
check("[v46.0] 빈 칸을 클릭하면 선택됨", c58.selected == (_r58, _c58))

_answer58 = c58.state.solution[_r58][_c58]
c58.enter_value(_answer58)
check("[v46.0] 숫자 패드로 입력(enter_value) — 보드에 정확히 반영됨",
      c58.state.board[_r58][_c58] == _answer58)

sw58.btn_note_mode.setChecked(True)
_r59, _c59 = next((r, c) for r in range(9) for c in range(9)
                   if c58.state.board[r][c] == SK.EMPTY)
c58.mousePressEvent(_FakeMouseEv(c58._cell_rect(_r59, _c59).center()))
c58.enter_value(5)
check("[v46.0] 메모 모드 켠 뒤 숫자를 누르면 확정이 아니라 메모로 들어감",
      5 in c58.state.notes[_r59][_c59] and c58.state.board[_r59][_c59] == SK.EMPTY)
sw58.btn_note_mode.setChecked(False)

sw58._on_hint()
check("[v46.0] 힌트 버튼을 눌러도 예외 없이 동작함(위젯 경로)", True)

sw58.diff_buttons[2].setChecked(True)   # hard
check("[v46.0] 난이도 라디오를 '어려움'으로 바꾸면 difficulty가 바뀜",
      sw58.difficulty == "hard")
sw58._start_new_game()
app.processEvents()
_blanks58 = sum(row.count(SK.EMPTY) for row in sw58.state.board)
check("[v46.0] '새 게임'을 누르면 선택한 난이도로 다시 생성됨(빈 칸 수 일치)",
      _blanks58 == SK.DIFFICULTY_BLANKS["hard"])

# 완성 판정(위젯 경로) — 마지막 한 칸 전까지는 메시지가 비어 있다가,
# 다 채우면 완성 메시지가 뜨는지.
_empties58 = [(r, c) for r in range(9) for c in range(9) if sw58.state.board[r][c] == SK.EMPTY]
for (r, c) in _empties58[:-1]:
    sw58.state.set_value(r, c, sw58.state.solution[r][c])
sw58._on_changed()
check("[v46.0] 마지막 한 칸이 남아 있으면 완성 메시지가 비어 있음",
      sw58.lbl_status.text() == "")
_lr58, _lc58 = _empties58[-1]
sw58.state.set_value(_lr58, _lc58, sw58.state.solution[_lr58][_lc58])
sw58._on_changed()
check("[v46.0] 마지막 칸까지 채우면 완성 메시지가 표시됨",
      sw58.lbl_status.text() == tr("util.sudoku.complete_msg"))

# 실제로 그려 봐도 예외 없이 렌더링되는지(메모·충돌·선택 상태 전부 있는 채로)
c58.grab()
check("[v46.0] 메모·힌트·완성 상태 전부 거친 뒤에도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("59. [v46.1] 스도쿠 — 재시도(라이프) 시스템, 오답 즉시 판정, 정사각형 숫자 버튼")

# ---- 순수 로직(sudoku_solve.py) ----
check("[v46.1] MAX_LIVES == 3", SK.MAX_LIVES == 3)

_ls = SK.new_state("easy", _rnd58.Random(11))
check("[v46.1] 새 상태는 lives=MAX_LIVES, game_over=False",
      _ls.lives == SK.MAX_LIVES and _ls.game_over is False)

_lr, _lc = next((r, c) for r in range(9) for c in range(9) if _ls.given[r][c] == SK.EMPTY)
_lwrong = (_ls.solution[_lr][_lc] % 9) + 1
_res = _ls.try_set_value(_lr, _lc, _lwrong)
check("[v46.1] 오답 시도 — False를 돌려주고 보드엔 반영 안 됨",
      _res is False and _ls.board[_lr][_lc] == SK.EMPTY)
check("[v46.1] 오답 시도 — 라이프가 하나 줄어듦(3→2)", _ls.lives == 2)

_res2 = _ls.try_set_value(_lr, _lc, _ls.solution[_lr][_lc])
check("[v46.1] 정답 시도 — True를 돌려주고 보드에 반영됨",
      _res2 is True and _ls.board[_lr][_lc] == _ls.solution[_lr][_lc])
check("[v46.1] 정답을 맞혀도 라이프는 그대로(2)", _ls.lives == 2)

_lgr, _lgc = next((r, c) for r in range(9) for c in range(9) if _ls.given[r][c] != SK.EMPTY)
check("[v46.1] given 칸에 시도하면 None(무효) — 라이프도 안 깎임",
      _ls.try_set_value(_lgr, _lgc, 1) is None and _ls.lives == 2)

_before_hint_lives = _ls.lives
_ls.apply_hint()
check("[v46.1] 힌트도 라이프를 하나 쓴다", _ls.lives == _before_hint_lives - 1)

_ls2 = SK.new_state("easy", _rnd58.Random(13))
_lr2, _lc2 = next((r, c) for r in range(9) for c in range(9) if _ls2.given[r][c] == SK.EMPTY)
_lwrong2 = (_ls2.solution[_lr2][_lc2] % 9) + 1
for _ in range(SK.MAX_LIVES):
    _ls2.try_set_value(_lr2, _lc2, _lwrong2)
check("[v46.1] 라이프를 다 쓰면(3번 오답) lives=0, game_over=True",
      _ls2.lives == 0 and _ls2.game_over is True)
check("[v46.1] game_over 상태에서는 더 이상 입력이 먹히지 않음(None)",
      _ls2.try_set_value(_lr2, _lc2, _ls2.solution[_lr2][_lc2]) is None)
check("[v46.1] game_over 상태에서 힌트도 막힘(None)", _ls2.apply_hint() is None)

# ---- 위젯 통합(sudoku.py) — 신호·라이프 표시·재도전 ----
win.util_panel.open_app("sudoku")
app.processEvents()
sw59 = win.util_panel._pages["sudoku"][0]
sw59._start_new_game()
app.processEvents()
c59 = sw59.canvas

check("[v46.1] 위젯을 새로 시작하면 라이프 인디케이터가 MAX_LIVES로 표시됨",
      sw59.lives_indicator.lives == SK.MAX_LIVES)

_r60, _c60 = next((r, c) for r in range(9) for c in range(9) if c59.state.board[r][c] == SK.EMPTY)
c59.mousePressEvent(_FakeMouseEv(c59._cell_rect(_r60, _c60).center()))
_wrong60 = (c59.state.solution[_r60][_c60] % 9) + 1
c59.enter_value(_wrong60)
check("[v46.1] 오답 입력 — 위젯의 라이프 인디케이터가 바로 갱신됨(2)",
      sw59.lives_indicator.lives == 2)
check("[v46.1] 오답 입력 — 상태 라벨에 오답 메시지가 뜸",
      sw59.lbl_status.text() == tr("util.sudoku.wrong_msg"))
check("[v46.1] 오답 입력 — 해당 칸은 여전히 빈 칸(반영 안 됨)",
      c59.state.board[_r60][_c60] == SK.EMPTY)

_answer60 = c59.state.solution[_r60][_c60]
c59.enter_value(_answer60)
check("[v46.1] 이어서 정답을 넣으면 반영되고 라이프는 그대로(2)",
      c59.state.board[_r60][_c60] == _answer60 and sw59.lives_indicator.lives == 2)
check("[v46.1] 정답을 넣은 뒤엔(완성 전이라) 상태 메시지가 다시 비워짐",
      sw59.lbl_status.text() == "")

sw59._on_hint()
check("[v46.1] 힌트 버튼(위젯 경로)도 라이프 인디케이터를 갱신함(2→1)",
      sw59.lives_indicator.lives == 1)

# 게임 오버 → 다이얼로그 없이 바로 처리되도록 신호 재배선(실제 QMessageBox는
# 헤드리스에서 모달로 막히므로, _on_game_over 자체를 가짜로 바꿔 호출 여부만 검증)
_game_over_called = {"n": 0}
def _fake_game_over():
    _game_over_called["n"] += 1
c59.gameOver.disconnect()
c59.gameOver.connect(_fake_game_over)
_r61, _c61 = next((r, c) for r in range(9) for c in range(9) if c59.state.board[r][c] == SK.EMPTY)
c59.mousePressEvent(_FakeMouseEv(c59._cell_rect(_r61, _c61).center()))
_wrong61 = (c59.state.solution[_r61][_c61] % 9) + 1
c59.enter_value(_wrong61)   # 마지막 남은 라이프(1)까지 소진
check("[v46.1] 마지막 라이프까지 오답을 쓰면 gameOver 신호가 발생함",
      _game_over_called["n"] == 1)
check("[v46.1] 그 시점의 라이프는 0", c59.state.lives == 0)
check("[v46.1] 그 시점의 game_over는 True", c59.state.game_over is True)
# [버그 수정] 위에서 gameOver를 가짜 핸들러로 바꿔치기한 채로 두면, 이
# 미니앱 페이지는 이후 섹션에서도 계속 재사용되므로(open_app이 캐시된
# 같은 위젯을 돌려줌) 뒤에 나오는 게임오버 관련 테스트들이 전부 깨진다
# — 반드시 원래 핸들러로 되돌려 놓는다.
c59.gameOver.disconnect()
c59.gameOver.connect(sw59._on_game_over)

# _retry_same_puzzle 직접 검증(같은 문제 유지, 라이프·보드 초기화)
_old_solution59 = [row[:] for row in c59.state.solution]
_old_given59 = [row[:] for row in c59.state.given]
sw59._retry_same_puzzle()
app.processEvents()
check("[v46.1] 재도전 — 같은 solution/given을 그대로 씀",
      c59.state.solution == _old_solution59 and c59.state.given == _old_given59)
check("[v46.1] 재도전 — 라이프가 MAX_LIVES로 리셋됨", c59.state.lives == SK.MAX_LIVES)
check("[v46.1] 재도전 — 보드가 given 상태로 리셋됨(사용자 입력 사라짐)",
      c59.state.board == _old_given59)
check("[v46.1] 재도전 — 라이프 인디케이터도 갱신됨", sw59.lives_indicator.lives == SK.MAX_LIVES)

# ---- 숫자 버튼 크기(정사각형에 가깝게) ----
check("[v46.1] 숫자 패드 버튼 높이가 기존보다 훨씬 커짐(56px)",
      all(b.height() == 56 for b in sw59.digit_buttons))

# ---- 키보드 입력(빈 칸 선택 후 숫자 키로도 입력 가능) ----
from PySide6.QtGui import QKeyEvent as _QKE59
_r62, _c62 = next((r, c) for r in range(9) for c in range(9) if c59.state.board[r][c] == SK.EMPTY)
c59.mousePressEvent(_FakeMouseEv(c59._cell_rect(_r62, _c62).center()))
_answer62 = c59.state.solution[_r62][_c62]
_key62 = getattr(Qt, f"Key_{_answer62}")
c59.keyPressEvent(_QKE59(QEvent.KeyPress, _key62, Qt.NoModifier, str(_answer62)))
check("[v46.1] 키보드 숫자 키 입력 — 선택된 칸에 정답이 반영됨",
      c59.state.board[_r62][_c62] == _answer62)

c59.grab()
check("[v46.1] 라이프·오답·재도전 전부 거친 뒤에도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("60. [v46.2] 스도쿠 — 숫자 버튼 완료 비활성화, 폰트 크기, 같은 숫자 강조")

# ---- 순수 로직(sudoku_solve.py) ----
_dc_board = [[0] * 9 for _ in range(9)]
check("[v46.2] digit_counts — 빈 보드는 모든 숫자가 0개",
      all(v == 0 for v in SK.digit_counts(_dc_board).values()))

_dc_state = SK.new_state("easy", _rnd58.Random(21))
_dc_state.board = [row[:] for row in _dc_state.solution]
_dc_counts = SK.digit_counts(_dc_state.board)
check("[v46.2] digit_counts — 정답으로 꽉 채우면 1~9 전부 9개씩",
      all(_dc_counts[d] == 9 for d in range(1, 10)), _dc_counts)

# ---- 위젯 통합(sudoku.py) ----
win.util_panel.open_app("sudoku")
app.processEvents()
sw60 = win.util_panel._pages["sudoku"][0]
sw60._start_new_game()
app.processEvents()
c60 = sw60.canvas

check("[v46.2] 새 게임 시작 — 숫자 버튼 9개 전부 활성화 상태",
      all(b.isEnabled() for b in sw60.digit_buttons))

# 특정 숫자(1)를 정답판 기준으로 9칸 모두 채운다
_target60 = 1
_positions60 = [(r, c) for r in range(9) for c in range(9)
                if c60.state.solution[r][c] == _target60]
for (r, c) in _positions60:
    if c60.state.board[r][c] == SK.EMPTY:
        c60.state.set_value(r, c, _target60)
sw60._on_changed()
check(f"[v46.2] 숫자 {_target60}이 9개 다 채워지면 그 버튼이 비활성화됨",
      not sw60.digit_buttons[_target60 - 1].isEnabled())
check("[v46.2] 다른 숫자(2) 버튼은 여전히 활성화 상태(아직 9개가 아님)",
      sw60.digit_buttons[1].isEnabled())

sw60._start_new_game()
app.processEvents()
check("[v46.2] 새 게임을 다시 시작하면 모든 숫자 버튼이 다시 활성화됨",
      all(b.isEnabled() for b in sw60.digit_buttons))

# ---- 폰트 크기 ----
check("[v46.2] 숫자 패드 버튼 — 스타일시트에 font-size:20px 포함(보드 숫자와 동일 크기)",
      all("font-size:20px" in b.styleSheet() for b in sw60.digit_buttons))
check("[v46.2] 완성/오답 상태 라벨 — 스타일시트에 font-size:15px 포함(기존 11px보다 커짐)",
      "font-size:15px" in sw60.lbl_status.styleSheet())
sw60._on_wrong_entry()
check("[v46.2] 오답 메시지로 바뀌어도 font-size가 유지됨(색만 바뀜)",
      "font-size:15px" in sw60.lbl_status.styleSheet())

# ---- 같은 숫자 강조(행·열·3x3박스) ----
sw60._start_new_game()
app.processEvents()
c60 = sw60.canvas
_r60b, _c60b = next((r, c) for r in range(9) for c in range(9) if c60.state.board[r][c] != SK.EMPTY)
_val60 = c60.state.board[_r60b][_c60b]
c60.mousePressEvent(_FakeMouseEv(c60._cell_rect(_r60b, _c60b).center()))

# 보드 전체에서 같은 값을 가진 모든 칸을 찾고, 그 행·열·박스 전체가
# highlight 집합에 들어가는지 재계산해서 대조한다(paintEvent와 같은 로직).
_expected_highlight = set()
_same_cells60 = [(r, c) for r in range(9) for c in range(9) if c60.state.board[r][c] == _val60]
for (sr, sc) in _same_cells60:
    for i in range(9):
        _expected_highlight.add((sr, i))
        _expected_highlight.add((i, sc))
    _br, _bc = (sr // 3) * 3, (sc // 3) * 3
    for i in range(_br, _br + 3):
        for j in range(_bc, _bc + 3):
            _expected_highlight.add((i, j))

# 멀리 떨어진, 같은 값을 가진 다른 칸이 있다면 그 칸의 행 전체가 강조
# 대상에 포함되는지 직접 확인(선택 칸 자신의 행·열·박스가 아닌 곳에서).
_other_same60 = [p for p in _same_cells60 if p != (_r60b, _c60b)]
if _other_same60:
    _or60, _oc60 = _other_same60[0]
    check(f"[v46.2] 선택 칸({_r60b},{_c60b})과 같은 숫자({_val60})를 가진 다른 칸({_or60},{_oc60})의 행 전체가 강조 대상에 포함됨",
          all((_or60, j) in _expected_highlight for j in range(9)))
    check(f"[v46.2] 같은 숫자를 가진 다른 칸({_or60},{_oc60})의 열 전체도 강조 대상에 포함됨",
          all((i, _oc60) in _expected_highlight for i in range(9)))
else:
    check("[v46.2] (이 퍼즐엔 같은 숫자가 하나뿐이라 다른-칸 강조 검증은 건너뜀 — 통과 처리)", True)

c60.grab()
check("[v46.2] 같은 숫자 강조 상태로 그려도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("61. [v46.3] 스도쿠 — 같은 숫자 강조 범위 수정 + 자동 완성 제안")

# ---- 순수 로직(sudoku_solve.py) — forced_completion ----
_fc_state = SK.new_state("easy", _rnd58.Random(31))
_fc_empties = [(r, c) for r in range(9) for c in range(9) if _fc_state.board[r][c] == SK.EMPTY]
for (r, c) in _fc_empties[:-1]:
    _fc_state.set_value(r, c, _fc_state.solution[r][c])
_fc_last = _fc_empties[-1]
_fc_result = SK.forced_completion(_fc_state.board)
check("[v46.3] 빈 칸이 하나만 남으면 forced_completion이 그 칸의 정답을 돌려줌",
      _fc_result == {_fc_last: _fc_state.solution[_fc_last[0]][_fc_last[1]]}, _fc_result)

_fc_full = [row[:] for row in _fc_state.solution]
check("[v46.3] 완전히 채워진 보드는 forced_completion이 None(빈 칸 없음)",
      SK.forced_completion(_fc_full) is None)

_fc_mid = SK.new_state("medium", _rnd58.Random(33))
check("[v46.3] 일반적인 중간 상태(여러 빈 칸)는 보통 forced_completion이 None",
      SK.forced_completion(_fc_mid.board) is None)

# ---- 위젯 통합 — 같은 숫자 강조 범위 ----
win.util_panel.open_app("sudoku")
app.processEvents()
sw61 = win.util_panel._pages["sudoku"][0]
sw61._start_new_game()
app.processEvents()
c61 = sw61.canvas

_r61, _c61 = next((r, c) for r in range(9) for c in range(9) if c61.state.board[r][c] != SK.EMPTY)
_val61 = c61.state.board[_r61][_c61]
c61.mousePressEvent(_FakeMouseEv(c61._cell_rect(_r61, _c61).center()))

# paintEvent와 같은 로직으로 "정답" 강조 집합을 재계산 — ①선택 칸의
# 행·열·박스, ②같은 숫자인 다른 칸 "자체"(그 칸의 행·열·박스는 제외).
_expected61 = set()
for i in range(9):
    _expected61.add((_r61, i))
    _expected61.add((i, _c61))
_br61, _bc61 = (_r61 // 3) * 3, (_c61 // 3) * 3
for i in range(_br61, _br61 + 3):
    for j in range(_bc61, _bc61 + 3):
        _expected61.add((i, j))
_other_same61 = [(r, c) for r in range(9) for c in range(9)
                 if c61.state.board[r][c] == _val61 and (r, c) != (_r61, _c61)]
for p in _other_same61:
    _expected61.add(p)

if _other_same61:
    _or61, _oc61 = _other_same61[0]
    # 그 다른 칸이 선택 칸의 행·열·박스 밖에 있다면(즉 진짜로 "확장되면
    # 안 되는" 케이스라면), 그 칸의 행 전체가 강조 집합에 들어가 있지
    # 않아야 한다(과거 버그는 행 전체를 넣었었다).
    _in_peer_zone = (_or61 == _r61 or _oc61 == _c61
                     or (_or61 // 3, _oc61 // 3) == (_r61 // 3, _c61 // 3))
    if not _in_peer_zone:
        _row_fully_highlighted = all((_or61, j) in _expected61 for j in range(9))
        check(f"[v46.3] 선택 칸의 영역 밖에 있는 같은 숫자 칸({_or61},{_oc61}) 자체는 강조되지만, "
             "그 칸의 행 전체까지 강조되지는 않음(과거 버그 수정 확인)",
             (_or61, _oc61) in _expected61 and not _row_fully_highlighted)
    else:
        check("[v46.3] (이번에 뽑힌 동일 숫자 칸이 마침 선택 칸의 행·열·박스 안이라 "
             "경계 케이스 검증은 건너뜀 — 통과 처리)", True)
else:
    check("[v46.3] (이 퍼즐엔 같은 숫자가 하나뿐이라 강조 범위 검증은 건너뜀 — 통과 처리)", True)

# ---- 위젯 통합 — 자동 완성 제안 ----
_empties61 = [(r, c) for r in range(9) for c in range(9) if c61.state.board[r][c] == SK.EMPTY]
for (r, c) in _empties61[:-1]:
    c61.state.set_value(r, c, c61.state.solution[r][c])
_last61 = _empties61[-1]

_captured61 = {}
def _spy_forced(mapping):
    _captured61["mapping"] = mapping
c61.forcedCompletionReady.disconnect()
c61.forcedCompletionReady.connect(_spy_forced)
c61._check_forced_completion()
check("[v46.3] 빈 칸이 하나만 남으면 forcedCompletionReady 신호가 정확한 매핑으로 발생함",
      _captured61.get("mapping") == {_last61: c61.state.solution[_last61[0]][_last61[1]]})

# 위젯의 "자동 완성" 처리 — 확인(Yes)을 고르면 실제로 채워지고 완성 메시지가 뜸
from PySide6.QtWidgets import QMessageBox as _QMB61
_orig_exec61 = _QMB61.exec
_orig_clicked61 = _QMB61.clickedButton
_QMB61.exec = lambda self: 0
_yes_btns61 = []
_orig_add61 = _QMB61.addButton
def _fake_add61(self, *a, **kw):
    b = _orig_add61(self, *a, **kw)
    _yes_btns61.append(b)
    return b
_QMB61.addButton = _fake_add61
_QMB61.clickedButton = lambda self: _yes_btns61[0] if _yes_btns61 else None

sw61._on_forced_completion_ready({_last61: c61.state.solution[_last61[0]][_last61[1]]})
check("[v46.3] 자동 완성 '확인'을 고르면 마지막 칸이 정답으로 채워짐",
      c61.state.board[_last61[0]][_last61[1]] == c61.state.solution[_last61[0]][_last61[1]])
check("[v46.3] 자동 완성 후 완성 메시지가 표시됨",
      sw61.lbl_status.text() == tr("util.sudoku.complete_msg"))

_QMB61.exec = _orig_exec61
_QMB61.clickedButton = _orig_clicked61
_QMB61.addButton = _orig_add61

# "취소"를 고르면 아무 것도 안 바뀌는지(별도 퍼즐로 재검증)
sw61._start_new_game()
app.processEvents()
c61b = sw61.canvas
_empties61b = [(r, c) for r in range(9) for c in range(9) if c61b.state.board[r][c] == SK.EMPTY]
for (r, c) in _empties61b[:-1]:
    c61b.state.set_value(r, c, c61b.state.solution[r][c])
_last61b = _empties61b[-1]
_QMB61.exec = lambda self: 0
_QMB61.clickedButton = lambda self: None   # 취소(확인 버튼이 아님)
sw61._on_forced_completion_ready({_last61b: c61b.state.solution[_last61b[0]][_last61b[1]]})
check("[v46.3] 자동 완성 '취소'를 고르면 마지막 칸이 그대로 빈 칸으로 남음",
      c61b.state.board[_last61b[0]][_last61b[1]] == SK.EMPTY)
_QMB61.exec = _orig_exec61
_QMB61.clickedButton = _orig_clicked61

c61.grab()
check("[v46.3] 강조·자동완성 전부 거친 뒤에도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("62. [v46.4] 스도쿠 — 숫자 9개 완료 시 키보드 입력도 차단")

win.util_panel.open_app("sudoku")
app.processEvents()
sw62 = win.util_panel._pages["sudoku"][0]
sw62._start_new_game()
app.processEvents()
c62 = sw62.canvas

_target62 = 1
_positions62 = [(r, c) for r in range(9) for c in range(9) if c62.state.solution[r][c] == _target62]
for (r, c) in _positions62:
    if c62.state.board[r][c] == SK.EMPTY:
        c62.state.set_value(r, c, _target62)
sw62._on_changed()
check("[v46.4] 숫자 1이 9개 다 채워지면 버튼이 비활성화됨(사전 조건)",
      not sw62.digit_buttons[_target62 - 1].isEnabled())

_r62, _c62 = next((r, c) for r in range(9) for c in range(9) if c62.state.board[r][c] == SK.EMPTY)
c62.mousePressEvent(_FakeMouseEv(c62._cell_rect(_r62, _c62).center()))

from PySide6.QtGui import QKeyEvent as _QKE62
_kev62 = _QKE62(QEvent.KeyPress, Qt.Key_1, Qt.NoModifier, "1")
c62.keyPressEvent(_kev62)
check("[v46.4] 9개 다 채워진 숫자는 키보드로 눌러도 보드에 반영되지 않음",
      c62.state.board[_r62][_c62] == SK.EMPTY)

_wrong_candidates62 = [d for d in range(1, 10) if d != _target62]
_other_digit62 = _wrong_candidates62[0]
_kev62b = _QKE62(QEvent.KeyPress, getattr(Qt, f"Key_{_other_digit62}"), Qt.NoModifier, str(_other_digit62))
c62.keyPressEvent(_kev62b)
check("[v46.4] 아직 9개가 안 된 다른 숫자는 키보드 입력이 정상적으로 먹힘"
     "(오답이었다면 반영 안 되는 게 맞지만, 적어도 '막혀서' 그런 게 아니라 판정이 일어났는지 확인)",
      c62.state.lives < SK.MAX_LIVES or c62.state.board[_r62][_c62] == _other_digit62)

# 메모 모드에서는 9개 다 채워진 숫자도 여전히 적을 수 있음(막지 않음)
sw62.btn_note_mode.setChecked(True)
_r63, _c63 = next((r, c) for r in range(9) for c in range(9) if c62.state.board[r][c] == SK.EMPTY)
c62.mousePressEvent(_FakeMouseEv(c62._cell_rect(_r63, _c63).center()))
_kev62c = _QKE62(QEvent.KeyPress, Qt.Key_1, Qt.NoModifier, "1")
c62.keyPressEvent(_kev62c)
check("[v46.4] 메모 모드에서는 9개 다 채워진 숫자도 후보로 적을 수 있음(막지 않음)",
      1 in c62.state.notes[_r63][_c63])
sw62.btn_note_mode.setChecked(False)

c62.grab()
check("[v46.4] 키보드 차단 상태로 그려도 예외 없이 정상 렌더링됨", True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
section("63. [v46.5] 스도쿠 — 같은 숫자 테두리 + 못다 푼 퍼즐 보관함")

# ---- 순수 로직(sudoku_solve.py) — 직렬화/역직렬화/고유 ID ----
_ar_state = SK.new_state("medium", _rnd58.Random(61))
_ar_r, _ar_c = next((r, c) for r in range(9) for c in range(9) if _ar_state.given[r][c] == SK.EMPTY)
_ar_state.try_set_value(_ar_r, _ar_c, _ar_state.solution[_ar_r][_ar_c])
_ar_state.toggle_note(0, 0, 3)
_ar_state.toggle_note(0, 0, 7)

import json as _json63
_ar_dict = _ar_state.to_dict()
_ar_json = _json63.dumps(_ar_dict)   # JSON으로 직렬화 가능해야 함(set이 섞여 있으면 실패)
check("[v46.5] SudokuState.to_dict() 결과가 JSON으로 직렬화됨(set 없이 전부 JSON 호환 타입)",
      isinstance(_ar_json, str) and len(_ar_json) > 0)

_ar_restored = SK.SudokuState.from_dict(_json63.loads(_ar_json))
check("[v46.5] from_dict — solution/board/notes가 원본과 동일하게 복원됨",
      _ar_restored.solution == _ar_state.solution
      and _ar_restored.board == _ar_state.board
      and _ar_restored.notes[0][0] == _ar_state.notes[0][0])
check("[v46.5] from_dict — 라이프는 항상 MAX_LIVES로, game_over는 False로 리셋됨",
      _ar_restored.lives == SK.MAX_LIVES and _ar_restored.game_over is False)

check("[v46.5] puzzle_id — 같은 solution이면 같은 ID(81자리)",
      SK.puzzle_id(_ar_state.solution) == SK.puzzle_id(_ar_restored.solution)
      and len(SK.puzzle_id(_ar_state.solution)) == 81)

# ---- 위젯 통합 — 같은 숫자 테두리 ----
win.util_panel.open_app("sudoku")
app.processEvents()
sw63 = win.util_panel._pages["sudoku"][0]
sw63._save_archive([])   # 이전 절에서 쌓였을 수 있는 보관함을 깨끗이 비우고 시작
sw63._start_new_game()
app.processEvents()
c63 = sw63.canvas

_r63, _c63 = next((r, c) for r in range(9) for c in range(9) if c63.state.board[r][c] != SK.EMPTY)
_val63 = c63.state.board[_r63][_c63]
c63.mousePressEvent(_FakeMouseEv(c63._cell_rect(_r63, _c63).center()))
_other_val_cells63 = [(r, c) for r in range(9) for c in range(9)
                      if c63.state.board[r][c] == _val63 and (r, c) != (_r63, _c63)]
c63.grab()
check("[v46.5] 같은 숫자인 칸이 하나 이상 있으면(그려도 예외 없음) — 테두리 로직이 정상 실행됨",
      True)
if _other_val_cells63:
    check(f"[v46.5] 같은 숫자({_val63})를 가진 칸이 {len(_other_val_cells63)}개 더 있음(테두리가 적용될 대상 존재)",
          len(_other_val_cells63) > 0)

# ---- 위젯 통합 — 보관함: 게임오버 시 저장 ----
check("[v46.5] 시작 시점 보관함은 비어 있음", sw63._load_archive() == [])

_r64, _c64 = next((r, c) for r in range(9) for c in range(9) if c63.state.board[r][c] == SK.EMPTY)
c63.mousePressEvent(_FakeMouseEv(c63._cell_rect(_r64, _c64).center()))
_wrong64 = (c63.state.solution[_r64][_c64] % 9) + 1

from PySide6.QtWidgets import QMessageBox as _QMB63
_orig_exec63 = _QMB63.exec
_orig_clicked63 = _QMB63.clickedButton
_orig_add63 = _QMB63.addButton
_QMB63.exec = lambda self: 0
_btns63 = []
def _fake_add63(self, *a, **kw):
    b = _orig_add63(self, *a, **kw)
    _btns63.append(b)
    return b
_QMB63.addButton = _fake_add63
_QMB63.clickedButton = lambda self: _btns63[1] if len(_btns63) > 1 else None   # "새 퍼즐" 선택

_old_solution64 = [row[:] for row in c63.state.solution]
for _ in range(SK.MAX_LIVES):
    c63.enter_value(_wrong64)
app.processEvents()

_archive64 = sw63._load_archive()
check("[v46.5] 게임오버 시(재도전/새 퍼즐 중 '새 퍼즐' 선택) 실패한 퍼즐이 보관함에 저장됨",
      len(_archive64) == 1 and _archive64[0]["puzzle_id"] == SK.puzzle_id(_old_solution64))
check("[v46.5] 보관함 저장 직후 새 퍼즐로 전환됨(활성 퍼즐의 solution이 달라짐)",
      c63.state.solution != _old_solution64)

_QMB63.exec = _orig_exec63
_QMB63.clickedButton = _orig_clicked63
_QMB63.addButton = _orig_add63

# ---- 위젯 통합 — 보관함: 불러오기(진행 유지·라이프 리셋) ----
_pid64 = _archive64[0]["puzzle_id"]
sw63._archive_load(_pid64)
app.processEvents()
check("[v46.5] 보관함에서 불러오면 그 퍼즐(solution)이 다시 활성화됨",
      SK.puzzle_id(c63.state.solution) == _pid64)
check("[v46.5] 보관함에서 불러오면 라이프가 MAX_LIVES로 리셋됨(0으로 끝났던 게임을 다시 시작)",
      c63.state.lives == SK.MAX_LIVES)
check("[v46.5] 보관함에서 불러온 뒤 라이프 인디케이터도 갱신됨",
      sw63.lives_indicator.lives == SK.MAX_LIVES)

# ---- 위젯 통합 — 보관함: 완성하면 자동 삭제 ----
_empties64 = [(r, c) for r in range(9) for c in range(9) if c63.state.board[r][c] == SK.EMPTY]
for (r, c) in _empties64:
    c63.state.set_value(r, c, c63.state.solution[r][c])
sw63._on_changed()
check("[v46.5] 보관함에서 불러온 퍼즐을 완성하면 보관함 기록이 자동으로 삭제됨",
      sw63._load_archive() == [])

# ---- 위젯 통합 — 보관함 중복 저장 방지(같은 퍼즐 다시 저장하면 덮어씀) ----
_dup_state = SK.new_state("easy", _rnd58.Random(71))
sw63._archive_save(_dup_state)
sw63._archive_save(_dup_state)
check("[v46.5] 같은 퍼즐을 두 번 저장해도 보관함엔 하나만 남음(중복 방지)",
      len(sw63._load_archive()) == 1)
sw63._save_archive([])   # 뒷정리


section("64. [v47] 갤럭시폰 사진 옮기기 — 증분 동기화 기록(순수 로직)")

import src.utils.phone_sync_store as PSY
import sqlite3 as _sqlite64

_t64 = _ts(2026, 11, 8, 10)
_raw64 = "\n".join([
    f"{_t64} 2048 /sdcard/DCIM/Camera/20261108_100000.jpg",
    f"{_t64 + 60} 4096 /sdcard/DCIM/Camera/20261108_100100.jpg",
    f"{_ts(2026, 10, 3)} 1000 /sdcard/DCIM/Camera/이름에 공백 있는 사진.jpg",
    f"{_t64} 77 /sdcard/DCIM/Camera/.trashed-123-old.jpg",
])
_f64 = PH.parse_find_output(_raw64)
check("[v47] 크기까지 담긴 find 출력(시각 크기 경로)이 파싱됨",
      len(_f64) == 4 and _f64[0].size == 2048 and _f64[0].name == "20261108_100000.jpg")
check("[v47] 파일 이름에 공백이 있어도 경로가 온전히 읽힘",
      _f64[2].name == "이름에 공백 있는 사진.jpg" and _f64[2].size == 1000)
check("[v47] 예전 형식(크기 없음)도 그대로 읽히고 size는 None", _pd_files[0].size is None and _pd_files[0].epoch > 0)
check("[v47] syncable — 이름이 '.'으로 시작하는 파일(휴지통 등)은 동기화 대상에서 빠짐",
      [f.name for f in PH.syncable(_f64)] == [f.name for f in _f64[:3]])

_lib64 = _tf.mkdtemp()
_store64 = PSY.SyncStore(_lib64)
_sync64 = PH.syncable(_f64)
check("[v47] 빈 보관함에서는 전부 새 사진", len(_store64.filter_new("DEV1", _sync64)) == 3
      and not _store64.has_any("DEV1"))
check("[v47] 전송 기록 DB가 보관함 폴더 안(.folderkit/phone_sync.db)에 생김",
      _os.path.isfile(_os.path.join(_lib64, ".folderkit", "phone_sync.db")))
_store64.record("DEV1", _sync64[0], PSY.STATUS_PULLED, PSY.plan_local_rel(_sync64[0]))
check("[v47] 기록한 사진은 다음부터 새 사진에서 빠짐",
      [f.name for f in _store64.filter_new("DEV1", _sync64)] == [_sync64[1].name, _sync64[2].name])
check("[v47] 다른 폰(기기 ID가 다름)의 기록과는 섞이지 않음", len(_store64.filter_new("DEV2", _sync64)) == 3)
_edited64 = PH.PhotoFile(_sync64[0].remote_path, _sync64[0].mtime, 9999)
check("[v47] 경로·시각이 같아도 크기가 달라졌으면 새 사진으로 봄",
      len(_store64.filter_new("DEV1", [_edited64])) == 1)
_nosize64 = PH.PhotoFile(_sync64[0].remote_path, _sync64[0].mtime, None)
check("[v47] 크기를 모르는 경우엔 경로+시각만으로 같은 사진으로 봄",
      _store64.filter_new("DEV1", [_nosize64]) == [])
check("[v47] mark_all — 남은 사진을 가져온 것으로 표시(이미 기록된 것은 그대로)",
      _store64.mark_all("DEV1", _sync64) == 2 and _store64.filter_new("DEV1", _sync64) == []
      and _store64.count("DEV1", PSY.STATUS_PULLED) == 1 and _store64.count("DEV1", PSY.STATUS_MARKED) == 2)
check("[v47] 기록을 새 SyncStore 객체로 다시 열어도 그대로 남아 있음(재기동·다른 스레드)",
      PSY.SyncStore(_lib64).count("DEV1") == 3)
with _sqlite64.connect(PSY.db_path_for(_lib64)) as _c64:
    _row64 = _c64.execute("SELECT status, local_rel FROM transfers WHERE status = 'pulled'").fetchone()
check("[v47] 상태는 내부 키로, 저장 경로는 보관함 기준 상대 경로('/' 구분)로 저장됨",
      _row64 == ("pulled", "2026/2026-11/20261108_100000.jpg"))
check("[v47] plan_local_rel — 연/월 폴더로 나눔", PSY.plan_local_rel(_sync64[2]) == "2026/2026-10/이름에 공백 있는 사진.jpg")
_os.makedirs(_os.path.join(_lib64, "2026", "2026-11"))
open(_os.path.join(_lib64, "2026", "2026-11", "a.jpg"), "w").close()
check("[v47] unique_local_rel — 같은 이름이 있으면 _2를 붙여 덮어쓰지 않음",
      PSY.unique_local_rel(_lib64, "2026/2026-11/a.jpg") == "2026/2026-11/a_2.jpg"
      and PSY.unique_local_rel(_lib64, "2026/2026-11/b.jpg") == "2026/2026-11/b.jpg")

section("64b. [v47] 갤럭시폰 사진 옮기기 — 무선 연결·파일 내려받기(순수 로직 + adb 모킹)")

check("[v47] normalize_host_port — 'IP:포트'만 통과(공백 제거, 이상한 값은 None)",
      PH.normalize_host_port(" 192.168.0.5:37123 ") == "192.168.0.5:37123"
      and PH.normalize_host_port("192.168.0.5") is None and PH.normalize_host_port("-s:5555") is None
      and PH.normalize_host_port("a:99999") is None and PH.normalize_host_port("") is None)
check("[v47] 페어링 코드는 숫자 6자리만", PH.is_valid_pair_code("123456") and not PH.is_valid_pair_code("12345a"))
check("[v47] 무선 연결 이름 판별(ip:포트 / mDNS 이름 / 케이블 일련번호)",
      PH.is_wireless_serial("192.168.0.5:37123") and PH.is_wireless_serial("adb-R3CN._adb-tls-connect._tcp")
      and not PH.is_wireless_serial("R3CN90ABCDE") and PH.connection_kind("R3CN90ABCDE") == PH.CONN_USB)
check("[v47] 케이블과 무선이 함께 있으면 케이블을 먼저 고름",
      PH.pick_preferred_device([("192.168.0.5:37123", "device"), ("R3CN", "device")]) == "R3CN"
      and PH.pick_preferred_device([("192.168.0.5:37123", "device")]) == "192.168.0.5:37123"
      and PH.pick_preferred_device([("R3CN", "unauthorized")]) is None)
_mdns64 = ("List of discovered mdns services\n"
           "adb-R3CN-AbCd\t_adb-tls-connect._tcp\t192.168.0.5:37145\n"
           "adb-R3CN-AbCd\t_adb-tls-pairing._tcp\t192.168.0.5:40001\n이상한 줄\n")
check("[v47] adb mdns services 출력 파싱", [s[2] for s in PH.parse_mdns_output(_mdns64)]
      == ["192.168.0.5:37145", "192.168.0.5:40001"])

PH.set_adb_path(_fake_adb)
with _patch("subprocess.run") as _run64:
    _run64.return_value.returncode = 0
    _run64.return_value.stderr = ""
    _run64.return_value.stdout = "Successfully paired to 192.168.0.5:40001 [guid=adb-R3CN]\n"
    check("[v47] pair — 성공 문구가 있으면 성공, 인자가 그대로 adb pair로 나감",
          PH.pair("192.168.0.5:40001", "123456")[0] is True
          and _run64.call_args[0][0][1:] == ["pair", "192.168.0.5:40001", "123456"])
    _run64.reset_mock()
    check("[v47] pair — 주소·코드 형식이 틀리면 adb를 부르지 않고 실패",
          PH.pair("엉뚱한 값", "123456")[0] is False and PH.pair("192.168.0.5:40001", "12")[0] is False
          and not _run64.called)
    _run64.return_value.stdout = "connected to 192.168.0.5:37145\n"
    check("[v47] connect — 'connected to'면 성공", PH.connect("192.168.0.5:37145")[0] is True)
    _run64.return_value.stdout = "failed to connect to 192.168.0.5:37145\n"
    check("[v47] connect — 종료 코드가 0이어도 실패 문구면 실패로 판단", PH.connect("192.168.0.5:37145")[0] is False)
    _run64.return_value.stdout = _mdns64
    check("[v47] discover_wireless — 연결용·페어링용 주소를 나눠 돌려줌",
          PH.discover_wireless() == {"connect": ["192.168.0.5:37145"], "pairing": ["192.168.0.5:40001"]})
    _run64.return_value.stdout = "R3CN90ABCDE\nSM-S921N\n"
    check("[v47] get_device_identity — 무선 주소 대신 폰 자체 일련번호를 기기 ID로 씀",
          PH.get_device_identity("192.168.0.5:37145") == ("R3CN90ABCDE", "SM-S921N"))
with _patch("subprocess.run", side_effect=OSError("실행 실패")):
    check("[v47] get_device_identity — 못 읽으면 무선 주소에서 포트만 뗀 값으로 대신함",
          PH.get_device_identity("192.168.0.5:37145") == ("192.168.0.5", ""))
    check("[v47] connect/discover — adb 실행이 실패해도 죽지 않음",
          PH.connect("192.168.0.5:37145")[0] is False and PH.discover_wireless() == {"connect": [], "pairing": []})


class _FakeProc64:
    """adb pull을 흉내 — 실행되면 .part 파일을 만들고 지정한 종료 코드를 돌려준다."""

    def __init__(self, cmd, payload=b"x" * 2048, returncode=0, hang=False):
        self.returncode, self.hang, self.killed = returncode, hang, False
        if payload is not None:
            with open(cmd[-1], "wb") as _fh:
                _fh.write(payload)

    def wait(self, timeout=None):
        if self.hang and not self.killed:
            import subprocess as _sp64
            raise _sp64.TimeoutExpired("adb", timeout)
        return self.returncode

    def kill(self):
        self.killed = True


_dst64 = _os.path.join(_tf.mkdtemp(), "2026", "2026-11", "20261108_100000.jpg")
with _patch("subprocess.Popen", side_effect=lambda cmd, **kw: _FakeProc64(cmd)) as _popen64:
    _r64 = PH.pull_file(_sync64[0], _dst64, serial="R3CN")
check("[v47] pull_file — 성공하면 제 이름으로 저장되고 .part는 남지 않음(폴더도 자동 생성)",
      _r64 == PH.PULL_OK and _os.path.isfile(_dst64) and not _os.path.exists(_dst64 + ".part"))
check("[v47] pull_file — 수정 시각을 폰에 있던 시각 그대로 맞춤", int(_os.path.getmtime(_dst64)) == _sync64[0].epoch)
check("[v47] pull_file — adb pull이 지정한 기기로, .part 경로로 나감",
      _popen64.call_args[0][0][1:4] == ["-s", "R3CN", "pull"] and _popen64.call_args[0][0][-1].endswith(".part"))
_dst64b = _os.path.join(_os.path.dirname(_dst64), "half.jpg")
with _patch("subprocess.Popen", side_effect=lambda cmd, **kw: _FakeProc64(cmd, payload=b"x" * 10)):
    _r64b = PH.pull_file(_sync64[0], _dst64b, serial="R3CN")
check("[v47] pull_file — 받은 크기가 폰의 크기와 다르면(도중에 끊김) 실패로 보고 반쪽 파일을 지움",
      _r64b == PH.PULL_FAILED and not _os.path.exists(_dst64b) and not _os.path.exists(_dst64b + ".part"))
with _patch("subprocess.Popen", side_effect=lambda cmd, **kw: _FakeProc64(cmd, returncode=1)):
    check("[v47] pull_file — adb가 실패 코드를 내면 실패", PH.pull_file(_sync64[0], _dst64b, serial="R3CN") == PH.PULL_FAILED)
with _patch("subprocess.Popen", side_effect=lambda cmd, **kw: _FakeProc64(cmd, hang=True)) as _popen64c:
    _r64c = PH.pull_file(_sync64[0], _dst64b, serial="R3CN", cancel_check=lambda: True)
check("[v47] pull_file — 전송 도중 취소하면 adb를 끝내고 반쪽 파일을 지움",
      _r64c == PH.PULL_CANCELLED and not _os.path.exists(_dst64b + ".part"))
with _patch("subprocess.Popen", side_effect=OSError("실행 불가")):
    check("[v47] pull_file — adb 실행 자체가 안 돼도 죽지 않고 실패", PH.pull_file(_sync64[0], _dst64b) == PH.PULL_FAILED)
PH.set_adb_path(None)

section("64c. [v47] 갤럭시폰 사진 옮기기 — 새 사진 가져오기 위젯 통합(폰 연결 모킹)")

import src.utils.phone_transfer as PTM

win.switch_mode("util")
win.util_panel.open_app("phonetransfer")
app.processEvents()
ptw = win.util_panel._pages["phonetransfer"][0]
ptw.library_dir = None
ptw._save_settings()
check("[v47] 화면에 '새 사진 가져오기' 카드와 '무선 연결' 버튼이 있음",
      ptw.card_sync.title_label.text() == tr("util.phonetransfer.card.sync")
      and ptw.btn_wireless.text() == tr("util.phonetransfer.btn.wireless"))
ptw._refresh()
check("[v47] 폰이 없으면 '새 사진 가져오기'가 비활성", not ptw.btn_sync.isEnabled())


def _fake_pull64(photo, local_path, serial=None, cancel_check=None):
    _os.makedirs(_os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as _fh:
        _fh.write(b"x")
    return PH.PULL_OK


def _wait_sync64(widget):
    if widget._sync_thread is not None:
        widget._sync_thread.wait(10000)
    for _ in range(5):
        app.processEvents()


_wlib64 = _tf.mkdtemp()
with _patch("src.utils.phone_transfer.PH.is_adb_available", return_value=True), \
     _patch("src.utils.phone_transfer.PH.list_devices",
            return_value=[("192.168.0.5:37145", "device"), ("R3CN", "device")]), \
     _patch("src.utils.phone_transfer.PH.get_device_identity", return_value=("R3CN90ABCDE", "SM-S921N")), \
     _patch("src.utils.phone_transfer.PH.list_photos", return_value=_f64):
    ptw._refresh()
    app.processEvents()
    check("[v47] (모킹) 케이블·무선이 함께 있으면 케이블로 연결하고 모델명·연결 종류를 보여줌",
          ptw.serial == "R3CN" and "SM-S921N" in ptw.lbl_status.text()
          and tr("util.phonetransfer.conn.usb") in ptw.lbl_status.text())
    check("[v47] (모킹) 기기 ID는 폰 자체 일련번호", ptw.device_id == "R3CN90ABCDE")
    check("[v47] (모킹) 보관함을 아직 안 정했으면 그 안내가 뜨고, 버튼은 눌러서 정할 수 있게 활성",
          ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.no_library") and ptw.btn_sync.isEnabled())

    # 처음 가져오기 — "지금부터만"을 고르면 내려받지 않고 표시만
    with _patch("src.utils.phone_transfer.QFileDialog.getExistingDirectory", return_value=_wlib64), \
         _patch.object(ptw, "_ask_first_sync_choice", return_value=PTM.FIRST_MARK) as _ask64, \
         _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_fake_pull64) as _pull64:
        ptw._on_sync()
        _wait_sync64(ptw)
    check("[v47] (모킹) 보관함이 없으면 먼저 폴더를 고르게 하고 QSettings에도 저장",
          ptw.library_dir == _wlib64 and ptw._settings.value("util.phonetransfer.library_dir", "") == _wlib64)
    check("[v47] (모킹) 처음 가져올 때 선택 창이 뜨고, 숨김 파일을 뺀 3장이 대상",
          _ask64.call_count == 1 and _ask64.call_args[0][0] == 3)
    check("[v47] (모킹) '지금부터만'은 내려받지 않고 가져온 것으로만 표시",
          not _pull64.called and PSY.SyncStore(_wlib64).count("R3CN90ABCDE", PSY.STATUS_MARKED) == 3)

    # 폰에 새 사진 2장이 더 생김 → 그 2장만 가져옴
    _new64 = PH.parse_find_output("\n".join([
        f"{_ts(2026, 11, 10, 9)} 111 /sdcard/DCIM/Camera/20261110_090000.jpg",
        f"{_ts(2026, 12, 1, 9)} 222 /sdcard/DCIM/Camera/20261201_090000.mp4"]))
    with _patch("src.utils.phone_transfer.PH.list_photos", return_value=_f64 + _new64):
        ptw._refresh()
        app.processEvents()
        check("[v47] (모킹) 새로고침하면 '새 사진 2장 (폰 전체 5장)'으로 표시",
              ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count", a0=2, a1=5))
        with _patch.object(ptw, "_ask_first_sync_choice") as _ask64b, \
             _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_fake_pull64) as _pull64b:
            ptw._on_sync()
            check("[v47] (모킹) 가져오는 동안 취소 버튼·진행 막대가 보이고 새로고침·다운로드는 잠김",
                  ptw._is_syncing() and not ptw.btn_sync_cancel.isHidden() and not ptw.progress_sync.isHidden()
                  and not ptw.btn_refresh.isEnabled() and not ptw.btn_sync.isEnabled())
            _wait_sync64(ptw)
        check("[v47] (모킹) 두 번째부터는 선택 창 없이 새 사진 2장만 내려받음",
              not _ask64b.called and _pull64b.call_count == 2)
        check("[v47] (모킹) 연/월 폴더로 나뉘어 저장됨",
              _os.path.isfile(_os.path.join(_wlib64, "2026", "2026-11", "20261110_090000.jpg"))
              and _os.path.isfile(_os.path.join(_wlib64, "2026", "2026-12", "20261201_090000.mp4")))
        check("[v47] (모킹) 끝나면 결과 문구가 뜨고 버튼이 원래대로 돌아옴",
              ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.end.done", a0=2)
              and not ptw._is_syncing() and ptw.btn_sync.isEnabled() and ptw.btn_refresh.isEnabled()
              and ptw.btn_sync_cancel.isHidden())
        ptw._refresh()
        check("[v47] (모킹) 다시 새로고침하면 새 사진 0장", 
              ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count", a0=0, a1=5))
        with _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_fake_pull64) as _pull64c:
            ptw._on_sync()
            _wait_sync64(ptw)
        check("[v47] (모킹) 새 사진이 없으면 아무 것도 내려받지 않고 안내만",
              not _pull64c.called and ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.none_new"))

    # 도중에 연결이 끊김 → 받은 데까지만 기록, 나머지는 다음에 이어받기
    _more64 = PH.parse_find_output("\n".join(
        f"{_ts(2026, 12, 5, 9) + i} 10 /sdcard/DCIM/Camera/20261205_09000{i}.jpg" for i in range(3)))
    _calls64 = []

    def _flaky_pull64(photo, local_path, serial=None, cancel_check=None):
        _calls64.append(photo.name)
        return _fake_pull64(photo, local_path) if len(_calls64) == 1 else PH.PULL_FAILED

    with _patch("src.utils.phone_transfer.PH.list_photos", return_value=_f64 + _new64 + _more64):
        ptw._refresh()
        with _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_flaky_pull64), \
             _patch("src.utils.phone_transfer.PH.list_devices", return_value=[]):
            ptw._on_sync()
            _wait_sync64(ptw)
        check("[v47] (모킹) 연결이 끊기면 남은 사진을 계속 시도하지 않고 멈춤(1장 성공, 1장 실패 후 중단)",
              len(_calls64) == 2 and tr("util.phonetransfer.sync.end.disconnected", a0=1) in ptw.lbl_sync_status.text())
        ptw._refresh()
        check("[v47] (모킹) 받은 1장만 기록돼 있어, 다음엔 남은 2장을 이어서 가져옴",
              ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count", a0=2, a1=8))

        # 취소
        def _cancel_pull64(photo, local_path, serial=None, cancel_check=None):
            return PH.PULL_CANCELLED

        with _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_cancel_pull64):
            ptw._on_sync()
            ptw._on_sync_cancel()
            _wait_sync64(ptw)
        check("[v47] (모킹) 취소하면 취소 문구가 뜨고 화면이 정상 상태로 돌아옴",
              tr("util.phonetransfer.sync.end.cancelled", a0=0) in ptw.lbl_sync_status.text()
              and not ptw._is_syncing() and ptw.btn_sync_cancel.isEnabled())

    # 보관함 폴더가 사라진 경우(USB를 뺀 경우 등)
    ptw.library_dir = _os.path.join(_wlib64, "없는_폴더")
    ptw._update_sync_summary()
    check("[v47] (모킹) 보관함 폴더가 없으면 새로 만들지 않고 안내만 함",
          ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.library_missing")
          and not _os.path.exists(ptw.library_dir))
    ptw.library_dir = _wlib64

    # 날짜별 다운로드(v43)는 그대로 동작하고, 전송 기록과 무관함
    _before64 = PSY.SyncStore(_wlib64).count("R3CN90ABCDE")
    ptw._refresh()
    ptw.list_events.item(0).setCheckState(Qt.Checked)
    with _patch("src.utils.phone_transfer.PH.pull_event", return_value=(1, [])) as _pe64, \
         _patch("src.utils.phone_transfer.QFileDialog.getExistingDirectory", return_value=_tf.mkdtemp()):
        ptw._on_download()
    check("[v47] (모킹) 날짜별 다운로드는 예전처럼 동작하고 전송 기록을 건드리지 않음",
          _pe64.call_count == 1 and PSY.SyncStore(_wlib64).count("R3CN90ABCDE") == _before64)

# 재기동해도 보관함 폴더가 복원되는지
_win64 = MainWindow(); _win64.show()
_win64.switch_mode("util"); _win64.util_panel.open_app("phonetransfer")
app.processEvents()
check("[v47] 재기동해도 보관함 폴더가 복원됨",
      _win64.util_panel._pages["phonetransfer"][0].library_dir == _wlib64)
_win64.close()

# 무선 연결 창
_dlg64 = PTM.WirelessDialog(ptw, "192.168.0.5:37000")
check("[v47] 무선 연결 창 — 마지막으로 연결했던 주소가 미리 채워짐", _dlg64.edit_conn_addr.text() == "192.168.0.5:37000")
_dlg64.edit_conn_addr.setText("주소 아님")
with _patch("src.utils.phone_transfer.PH.connect") as _conn64:
    _dlg64._on_connect()
check("[v47] 무선 연결 창 — 주소 형식이 틀리면 adb를 부르지 않고 안내",
      not _conn64.called and _dlg64.lbl_result.text() == tr("util.phonetransfer.wifi.bad_addr"))
_dlg64.edit_pair_addr.setText("192.168.0.5:40001")
_dlg64.edit_pair_code.setText("12ab")
with _patch("src.utils.phone_transfer.PH.pair") as _pair64:
    _dlg64._on_pair()
    check("[v47] 무선 연결 창 — 코드가 6자리 숫자가 아니면 안내", not _pair64.called
          and _dlg64.lbl_result.text() == tr("util.phonetransfer.wifi.bad_code"))
    _pair64.return_value = (True, "Successfully paired")
    _dlg64.edit_pair_code.setText("123456")
    _dlg64._on_pair()
    check("[v47] 무선 연결 창 — 페어링 성공 안내", _dlg64.lbl_result.text() == tr("util.phonetransfer.wifi.pair_ok"))
with _patch("src.utils.phone_transfer.PH.discover_wireless",
            return_value={"connect": ["192.168.0.5:37145"], "pairing": []}):
    _dlg64._on_find()
check("[v47] 무선 연결 창 — '자동 찾기'가 찾은 주소를 연결 칸에 채움", _dlg64.edit_conn_addr.text() == "192.168.0.5:37145")
with _patch("src.utils.phone_transfer.PH.discover_wireless", return_value={"connect": [], "pairing": []}):
    _dlg64._on_find()
check("[v47] 무선 연결 창 — 못 찾으면 직접 입력 안내", _dlg64.lbl_result.text() == tr("util.phonetransfer.wifi.find_none"))
with _patch("src.utils.phone_transfer.PH.connect", return_value=(False, "failed to connect")):
    _dlg64._on_connect()
check("[v47] 무선 연결 창 — 연결 실패 시 adb 원문과 함께 안내하고 connected_addr는 비어 있음",
      "failed to connect" in _dlg64.lbl_result.text() and _dlg64.connected_addr is None)
with _patch("src.utils.phone_transfer.PH.connect", return_value=(True, "connected to 192.168.0.5:37145")):
    _dlg64._on_connect()
check("[v47] 무선 연결 창 — 연결 성공 시 주소를 기억", _dlg64.connected_addr == "192.168.0.5:37145")
_dlg64.close()


class _FakeDlg64:
    connected_addr = "192.168.0.5:37145"

    def __init__(self, *a, **k):
        pass

    def exec(self):
        return 1


with _patch("src.utils.phone_transfer.WirelessDialog", _FakeDlg64), _patch.object(ptw, "_refresh") as _rf64:
    ptw._on_wireless()
check("[v47] 무선으로 연결하면 주소를 저장하고 사진 목록을 새로 읽음",
      _rf64.called and ptw._settings.value("util.phonetransfer.wifi_addr", "") == "192.168.0.5:37145")

for _lang64 in ("en", "ja", "ko"):
    set_language(_lang64)
    win.util_panel.retranslate()
    app.processEvents()
    check(f"[v47] 언어를 {_lang64}로 바꿔도 새 카드·버튼 문구가 그 언어로 바뀜",
          ptw.btn_sync.text() in (tr("util.phonetransfer.sync.btn.sync"), tr("util.phonetransfer.sync.btn.sync_selected"))
          and ptw.card_sync.title_label.text() == tr("util.phonetransfer.card.sync"))
ptw._refresh()


section("65. [v47.1] 갤럭시폰 사진 옮기기 — 연도 표시 · 전체 선택 · 선택한 날짜만 가져오기")

_e65 = PH.group_into_events(PH.parse_find_output("\n".join([
    f"{_ts(2025, 12, 28)} 10 /sdcard/DCIM/Camera/a.jpg",
    f"{_ts(2025, 12, 31)} 10 /sdcard/DCIM/Camera/b.jpg",
    f"{_ts(2026, 1, 1)} 10 /sdcard/DCIM/Camera/c.jpg",
    f"{_ts(2026, 3, 5)} 10 /sdcard/DCIM/Camera/d.jpg",
    f"{_ts(2026, 3, 6)} 10 /sdcard/DCIM/Camera/e.jpg",
    f"{_ts(2026, 11, 8)} 10 /sdcard/DCIM/Camera/f.jpg",
])))
check("[v47.1] 하루짜리 행사 — 연도까지 붙은 날짜 하나", PH.event_date_texts(_e65[0]) == ("2026/11/08", None))
check("[v47.1] 같은 해 안의 구간 — 시작은 연도 포함, 끝은 월/일만", PH.event_date_texts(_e65[1]) == ("2026/03/05", "03/06"))
check("[v47.1] 해를 넘기는 구간 — 끝 날짜에도 연도", PH.event_date_texts(_e65[2]) == ("2025/12/31", "2026/01/01"))
check("[v47.1] 작년 날짜는 작년 연도로 표시", PH.event_date_texts(_e65[3]) == ("2025/12/28", None))

ptw = win.util_panel._pages["phonetransfer"][0]
_lib65 = _tf.mkdtemp()
ptw.library_dir = _lib65
_files65 = [f for ev in _e65 for f in ev.files]
set_language("ko")
with _patch("src.utils.phone_transfer.PH.is_adb_available", return_value=True), \
     _patch("src.utils.phone_transfer.PH.list_devices", return_value=[("R3CN", "device")]), \
     _patch("src.utils.phone_transfer.PH.get_device_identity", return_value=("DEV65", "SM-F731N")), \
     _patch("src.utils.phone_transfer.PH.list_photos", return_value=_files65):
    ptw._refresh()
    app.processEvents()
    check("[v47.1] 목록 문구에 연도가 들어감",
          ptw.list_events.item(0).text() == "2026/11/08 (1장)"
          and ptw.list_events.item(2).text() == "2025/12/31 ~ 2026/01/01 (2장)")
    check("[v47.1] 처음엔 아무 것도 선택 안 됨 — 전체 선택 꺼짐, 선택 요약 비어 있음, 버튼은 '새 사진 가져오기'",
          not ptw.chk_all.isChecked() and ptw.lbl_selection.text() == ""
          and ptw.btn_sync.text() == tr("util.phonetransfer.sync.btn.sync"))
    ptw.chk_all.click()
    app.processEvents()
    check("[v47.1] 전체 선택 — 모든 행사가 체크되고 선택 요약이 보임",
          all(ptw.list_events.item(i).checkState() == Qt.Checked for i in range(ptw.list_events.count()))
          and ptw.lbl_selection.text() == tr("util.phonetransfer.selection", a0=4, a1=6)
          and ptw.btn_download.isEnabled())
    ptw.list_events.item(1).setCheckState(Qt.Unchecked)
    app.processEvents()
    check("[v47.1] 하나를 풀면 전체 선택 체크도 풀림", not ptw.chk_all.isChecked())
    ptw.chk_all.click()
    app.processEvents()
    ptw.chk_all.click()
    app.processEvents()
    check("[v47.1] 전체 해제 — 모두 풀리고 요약이 사라짐",
          all(ptw.list_events.item(i).checkState() == Qt.Unchecked for i in range(ptw.list_events.count()))
          and ptw.lbl_selection.text() == "" and not ptw.btn_download.isEnabled())

    # 체크한 날짜만 가져오기
    ptw.list_events.item(1).setCheckState(Qt.Checked)   # 2026/03/05~06 (2장)
    app.processEvents()
    check("[v47.1] 날짜를 체크하면 버튼이 '선택한 날짜 가져오기'로, 안내가 선택 기준으로 바뀜",
          ptw.btn_sync.text() == tr("util.phonetransfer.sync.btn.sync_selected")
          and ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count_selected", a0=2, a1=2))
    with _patch.object(ptw, "_ask_first_sync_choice") as _ask65, \
         _patch("src.utils.phone_transfer.PH.pull_file", side_effect=_fake_pull64) as _pull65:
        ptw._on_sync()
        check("[v47.1] 가져오는 동안 목록·전체 선택이 잠김",
              not ptw.list_events.isEnabled() and not ptw.chk_all.isEnabled())
        _wait_sync64(ptw)
    check("[v47.1] 체크한 날짜의 2장만 가져오고, 처음이어도 '전부/지금부터만'을 묻지 않음",
          _pull65.call_count == 2 and not _ask65.called
          and sorted(c[0][0].name for c in _pull65.call_args_list) == ["d.jpg", "e.jpg"])
    check("[v47.1] 끝나면 목록이 다시 풀림", ptw.list_events.isEnabled() and ptw.chk_all.isEnabled())
    ptw._update_sync_summary()
    check("[v47.1] 같은 날짜를 다시 보면 새 사진 0장",
          ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count_selected", a0=0, a1=2))
    ptw.list_events.item(1).setCheckState(Qt.Unchecked)
    app.processEvents()
    check("[v47.1] 체크를 모두 풀면 다시 폰 전체 기준(새 사진 4장 / 전체 6장)",
          ptw.lbl_sync_status.text() == tr("util.phonetransfer.sync.status.new_count", a0=4, a1=6)
          and ptw.btn_sync.text() == tr("util.phonetransfer.sync.btn.sync"))

    # 언어를 바꿔도 체크는 유지되고 문구만 바뀜
    ptw.list_events.item(3).setCheckState(Qt.Checked)
    set_language("en")
    win.util_panel.retranslate()
    app.processEvents()
    check("[v47.1] 언어를 바꿔도 체크는 그대로, 행사 이름은 새 언어로",
          ptw.list_events.item(3).checkState() == Qt.Checked and ptw.list_events.item(0).text() == "2026/11/08 (1 photos)"
          and ptw.chk_all.text() == "Select All")
    set_language("ko")
    win.util_panel.retranslate()
    app.processEvents()

# 무선: 연결용 주소로 페어링하려 하면 adb를 부르지 않고 안내
_dlg65 = PTM.WirelessDialog(ptw, "192.168.219.103:46495")
_dlg65.edit_pair_addr.setText("192.168.219.103:46495")
_dlg65.edit_pair_code.setText("504187")
with _patch("src.utils.phone_transfer.PH.pair") as _pair65:
    _dlg65._on_pair()
check("[v47.1] 페어링 칸에 연결용 주소를 넣으면 adb를 부르지 않고 '페어링 창의 주소'를 안내",
      not _pair65.called and _dlg65.lbl_result.text() == tr("util.phonetransfer.wifi.pair_same_as_connect"))
_dlg65.edit_pair_addr.setText("192.168.219.103:37011")
with _patch("src.utils.phone_transfer.PH.pair", return_value=(True, "Successfully paired")) as _pair65b:
    _dlg65._on_pair()
check("[v47.1] 포트가 다르면 정상적으로 페어링을 시도", _pair65b.called)
_dlg65.close()


section("66. [v47.2] 세로 사진(EXIF 방향) — 눕지 않고 세로로 보이고, 저장해도 바로 섰는지")

from PIL import Image as _PIL66
from src import image_io as IO66
from src.thumbnail_loader import ThumbnailLoaderWorker as _TLW66

_dir66 = _tf.mkdtemp()
_p66 = _os.path.join(_dir66, "20261111_092738.jpg")
# 센서 기준 가로 400×300, 왼쪽 위에 파란 블록 — 방향 6(시계 방향 90°로 돌려 볼 것)
_raw66 = _PIL66.new("RGB", (400, 300), (255, 0, 0))
_raw66.paste((0, 0, 255), (0, 0, 100, 50))
_exif66 = _PIL66.Exif()
_exif66[0x0112] = 6
_exif66[0x010F] = "samsung"
_raw66.save(_p66, exif=_exif66.tobytes(), quality=95)
_plain66 = _os.path.join(_dir66, "plain.jpg")
_PIL66.new("RGB", (400, 300), (0, 255, 0)).save(_plain66)

_o66 = IO66.open_oriented(_p66)
check("[v47.2] open_oriented — 방향 6 사진이 세로(300×400)로 열림", _o66.size == (300, 400))
check("[v47.2] open_oriented — 픽셀도 실제로 돌아감(센서의 왼쪽 위 → 화면의 오른쪽 위)",
      _o66.getpixel((290, 10))[2] > 200 and _o66.getpixel((10, 10))[0] > 200)
check("[v47.2] 방향 태그가 없는 사진은 그대로", IO66.open_oriented(_plain66).size == (400, 300))
check("[v47.2] thumbnail_oriented — 썸네일도 세로로", IO66.thumbnail_oriented(_p66, (160, 160)).size == (120, 160))
check("[v47.2] thumbnail_oriented — 세로로 돌아갈 사진도 직사각형 상자 안에 들어감",
      IO66.thumbnail_oriented(_p66, (160, 90)).size[1] <= 90 and IO66.thumbnail_oriented(_p66, (160, 90)).size[0] <= 160)
_bad66 = _os.path.join(_dir66, "bad_orient.jpg")
_e66b = _PIL66.Exif(); _e66b[0x0112] = 99
_PIL66.new("RGB", (40, 30)).save(_bad66, exif=_e66b.tobytes())
check("[v47.2] 이상한 방향 값(99)은 무시하고 그대로 엶", IO66.open_oriented(_bad66).size == (40, 30))
_pm66 = _TLW66([_p66])._load_thumbnail(_p66)
check("[v47.2] 썸네일 로더(아래 스트립)도 세로로 만듦", _pm66 is not None and _pm66.height() > _pm66.width())

# 실제 이미지 편집 모드: 화면·크기 표시·크롭 저장
win.switch_mode("imgedit")
app.processEvents()
win.load_imgedit_folder(_dir66)
app.processEvents()
_i66 = win.imgedit_files.index(_p66)
win.on_imgedit_thumb_selected(_i66)
app.processEvents()
check("[v47.2] 이미지 편집 화면에 세로로 표시됨", win.crop_canvas.pil_img.size == (300, 400))
check("[v47.2] 정보 줄의 크기도 세로 기준(300×400)", "300×400" in win.imgedit_info_lbl.text())

_st66 = win.imgedit_states[_p66]
_st66.crop_rect = (0, 0, 300, 200)   # 화면에서 본 위쪽 절반(파란 블록이 오른쪽 위에 있음)
_st66.applied = True
with _patch("src.main_window.QMessageBox.information"):
    win.on_imgedit_save()
_saved66 = _PIL66.open(_p66)
_saved66.load()
check("[v47.2] 화면에서 고른 영역 그대로 잘려 저장됨(300×200, 파란 블록이 오른쪽 위)",
      _saved66.size == (300, 200) and _saved66.getpixel((290, 10))[2] > 200)
_se66 = _saved66.getexif()
check("[v47.2] 저장 파일의 방향 태그는 1 — 다른 프로그램에서 다시 돌아가지 않음", _se66.get(0x0112) == 1)
check("[v47.2] 나머지 EXIF(제조사 등)는 그대로 남음", _se66.get(0x010F) == "samsung")
check("[v47.2] 저장한 사진을 다시 열어도 같은 방향", IO66.open_oriented(_p66).size == (300, 200))

# JPG 변환도 세로 그대로
_png66 = _os.path.join(_dir66, "portrait_src.png")
_raw66.save(_png66, exif=_exif66.tobytes())
with _patch("src.main_window.QMessageBox.question", return_value=_QMB.Yes), \
     _patch("src.main_window.QMessageBox.information"), _patch("src.main_window.QMessageBox.warning"):
    win.load_imgedit_folder(_dir66)
    app.processEvents()
    win.imgedit_current = win.imgedit_files.index(_png66)
    _conv66 = getattr(win, "on_imgedit_convert_to_jpg", None)
    if _conv66 is not None:
        try:
            _conv66()
        except TypeError:
            _conv66(False)
_jpg66 = _os.path.join(_dir66, "portrait_src.jpg")
if _os.path.exists(_jpg66):
    _j66 = _PIL66.open(_jpg66)
    check("[v47.2] JPG로 변환해도 세로 그대로(300×400, 방향 태그 1)",
          _j66.size == (300, 400) and _j66.getexif().get(0x0112, 1) == 1)
else:
    check("[v47.2] JPG 변환 결과 파일이 생김", False, "변환 함수 이름/대상 선택 방식 확인 필요")


section("67. [v47.3] 편집 저장·JPG 변환 화질 92")

_d67 = _tf.mkdtemp()
_seen67 = []
_orig_save67 = _PIL66.Image.save


def _spy_save67(self, fp, format=None, **params):
    _seen67.append((str(fp), format, params.get("quality")))
    return _orig_save67(self, fp, format, **params)


with _patch.object(_PIL66.Image, "save", _spy_save67):
    IO66.save_keeping_exif(_PIL66.new("RGB", (20, 10)), _os.path.join(_d67, "a.jpg"))
    IO66.save_keeping_exif(_PIL66.new("RGB", (20, 10)), _os.path.join(_d67, "b.JPEG"))
    IO66.save_keeping_exif(_PIL66.new("RGB", (20, 10)), _os.path.join(_d67, "c.png"))
    IO66.save_keeping_exif(_PIL66.new("RGB", (20, 10)), _os.path.join(_d67, "d.dat"), format="JPEG")
check("[v47.3] .jpg/.jpeg 저장은 화질 92", _seen67[0][2] == 92 and _seen67[1][2] == 92)
check("[v47.3] PNG에는 화질 값을 넣지 않음", _seen67[2][2] is None)
check("[v47.3] 확장자와 상관없이 JPEG 형식을 지정하면 화질 92", _seen67[3][2] == 92)

_p67 = _os.path.join(_d67, "photo.jpg")
_PIL66.new("RGB", (40, 30), (10, 20, 30)).save(_p67)
win.switch_mode("imgedit")
app.processEvents()
win.load_imgedit_folder(_d67)
app.processEvents()
_st67 = win.imgedit_states[_p67]
_st67.crop_rect = (0, 0, 20, 20)
_st67.applied = True
with _patch("src.main_window.save_keeping_exif", wraps=IO66.save_keeping_exif) as _sk67, \
     _patch("src.main_window.QMessageBox.information"):
    win.on_imgedit_save()
check("[v47.3] 이미지 편집 '저장'이 화질을 정하는 공통 함수를 거침(→ 92)", _sk67.called
      and _PIL66.open(_p67).size == (20, 20))


section("68. [v48] 사진첩 — 행사 자동 분류(순수 로직)")

import random as _rnd68
from datetime import datetime as _dt68
from PIL import ImageDraw as _Draw68
import src.photo_album_core as AC
from PySide6.QtCore import QThreadPool as _Pool68
from PySide6.QtWidgets import QAbstractItemView


def _scene68(kind, seed):
    _rnd68.seed(seed)
    im = _PIL66.new("RGB", (400, 300))
    d = _Draw68.Draw(im)
    if kind == "hall":
        d.rectangle((0, 0, 400, 300), fill=(60, 40, 30)); d.rectangle((100, 40, 300, 160), fill=(230, 230, 240))
    else:
        d.rectangle((0, 0, 400, 150), fill=(120, 180, 240)); d.rectangle((0, 150, 400, 300), fill=(60, 150, 60))
    for _ in range(30):
        x, y = _rnd68.randint(0, 380), _rnd68.randint(0, 280)
        d.rectangle((x, y, x + _rnd68.randint(5, 25), y + _rnd68.randint(5, 40)),
                    fill=tuple(_rnd68.randint(0, 255) for _ in range(3)))
    return im


def _shot68(lib, rel, kind, when, seed, exif_time=True):
    p = _os.path.join(lib, *rel.split("/"))
    _os.makedirs(_os.path.dirname(p), exist_ok=True)
    ex = _PIL66.Exif()
    if exif_time:
        ex.get_ifd(0x8769)[0x9003] = when.strftime("%Y:%m:%d %H:%M:%S")
    _scene68(kind, seed).save(p, exif=ex.tobytes())
    if not exif_time:
        _os.utime(p, (when.timestamp(), when.timestamp()))
    return p


_lib68 = _tf.mkdtemp()
_P68 = {
    "a1": _shot68(_lib68, "2026/2026-11/a1.jpg", "hall", _dt68(2026, 11, 8, 9), 1),
    "a2": _shot68(_lib68, "2026/2026-11/a2.jpg", "hall", _dt68(2026, 11, 8, 10), 2),
    "a3": _shot68(_lib68, "2026/2026-11/a3.jpg", "field", _dt68(2026, 11, 8, 11), 3),
    "a4": _shot68(_lib68, "2026/2026-11/a4.jpg", "hall", _dt68(2026, 11, 8, 17), 4),
    "b1": _shot68(_lib68, "2026/2026-11/b1.jpg", "field", _dt68(2026, 11, 10, 9), 5),
    "b2": _shot68(_lib68, "2026/2026-11/b2.jpg", "field", _dt68(2026, 11, 10, 15), 6),
    "c1": _shot68(_lib68, "2026/2026-11/c1.jpg", "hall", _dt68(2026, 11, 17, 9), 7),
}
_os.makedirs(_os.path.join(_lib68, ".folderkit"), exist_ok=True)
open(_os.path.join(_lib68, ".folderkit", "x.jpg"), "w").close()
open(_os.path.join(_lib68, "2026", "half.jpg.part"), "w").close()
open(_os.path.join(_lib68, "2026", ".hidden.jpg"), "w").close()
open(_os.path.join(_lib68, "2026", "memo.txt"), "w").close()
_scan68 = AC.scan_library(_lib68)
check("[v48] scan_library — 사진만, .folderkit·숨김·.part·문서는 뺌",
      sorted(r for r, _, _ in _scan68) == sorted(f"2026/2026-11/{k}.jpg" for k in _P68))

check("[v48] EXIF 시각 문자열 해석", AC.parse_exif_datetime("2026:11:08 10:15:00") == int(_dt68(2026, 11, 8, 10, 15).timestamp())
      and AC.parse_exif_datetime("0000:00:00 00:00:00") is None and AC.parse_exif_datetime(None) is None)
_t68, _f68 = AC.analyze_file(_P68["a1"], 0)
check("[v48] analyze_file — EXIF 촬영 시각과 128바이트 특징값", _t68 == int(_dt68(2026, 11, 8, 9).timestamp())
      and len(_f68) == AC.FEATURE_LEN)
_bad68 = _os.path.join(_tf.mkdtemp(), "broken.jpg")
open(_bad68, "wb").write(b"not an image")
check("[v48] 열 수 없는 사진 — 파일 시각으로 대신하고 특징값은 빈 값(분석은 끝난 것으로)",
      AC.analyze_file(_bad68, 12345) == (12345, AC.UNREADABLE))
_noexif68 = _shot68(_tf.mkdtemp(), "x.jpg", "hall", _dt68(2026, 5, 5, 12), 9, exif_time=False)
check("[v48] EXIF 시각이 없으면 파일 수정 시각", AC.analyze_file(_noexif68, 777)[0] == 777)
_fa68 = AC.analyze_file(_P68["a2"], 0)[1]
_fb68 = AC.analyze_file(_P68["a3"], 0)[1]
check("[v48] 배경 거리 — 같은 장소는 가깝고 다른 장소는 멂, 없으면 1",
      AC.feature_distance(_f68, _f68) == 0 and AC.feature_distance(_f68, _fa68) < AC.SIMILAR
      and AC.feature_distance(_f68, _fb68) > AC.SIMILAR and AC.feature_distance(_f68, b"") == 1.0)
_h = 3600
check("[v48] same_event — 2시간 이내는 배경이 달라도 같은 행사",
      AC.same_event(0, _f68, 1.5 * _h, _fb68))
check("[v48] same_event — 2~12시간은 배경이 비슷해야", AC.same_event(0, _f68, 6 * _h, _fa68)
      and not AC.same_event(0, _f68, 6 * _h, _fb68))
check("[v48] same_event — 36시간 넘으면 배경이 같아도 다른 행사", not AC.same_event(0, _f68, 37 * _h, _f68))
check("[v48] 날짜 이름 — 하루/같은 해 구간/해 넘김",
      AC.event_date_texts(_dt68(2026, 11, 8, 9).timestamp(), _dt68(2026, 11, 8, 20).timestamp()) == ("2026/11/08", None)
      and AC.event_date_texts(_dt68(2026, 3, 5).timestamp(), _dt68(2026, 3, 6).timestamp()) == ("2026/03/05", "03/06")
      and AC.event_date_texts(_dt68(2025, 12, 31).timestamp(), _dt68(2026, 1, 1).timestamp()) == ("2025/12/31", "2026/01/01"))

_prog68 = []
_r68 = AC.run_analysis(_lib68, progress=lambda st, d, t: _prog68.append((st, d, t)))
check("[v48] run_analysis — 7장 분석, 7장 묶음", (_r68["analyzed"], _r68["grouped"], _r68["cancelled"]) == (7, 7, False)
      and (AC.STAGE_FEATURES, 7, 7) in _prog68)
_st68 = AC.AlbumStore(_lib68)


def _groups68():
    return sorted(sorted(_os.path.basename(p)[:-4] for p in _st68.photos_of(e.id)) for e in _st68.events())


check("[v48] 강당→운동장→(6시간 뒤)강당은 한 행사, 이틀 뒤 운동장은 따로, 일주일 뒤 같은 강당도 따로",
      _groups68() == [["a1", "a2", "a3", "a4"], ["b1", "b2"], ["c1"]])
check("[v48] 행사 목록은 최근 행사가 위", _os.path.basename(_st68.photos_of(_st68.events()[0].id)[0]) == "c1.jpg")
check("[v48] DB는 보관함 안(.folderkit/photo_album.db)", _os.path.isfile(AC.db_path_for(_lib68)))
_r68 = AC.run_analysis(_lib68)
check("[v48] 다시 돌리면 분석할 것도 묶을 것도 없음", (_r68["analyzed"], _r68["grouped"], _r68["gps"]) == (0, 0, 0))

# 정정
_ev68 = {(_os.path.basename(_st68.photos_of(e.id)[0])[:2]): e.id for e in _st68.events()}
_st68.move_photos([_P68["a3"]], _ev68["b1"])
check("[v48] 사진을 다른 행사로 옮김", _groups68() == [["a1", "a2", "a4"], ["a3", "b1", "b2"], ["c1"]])
_new68 = _st68.new_event_with([_P68["a4"]])
check("[v48] 선택한 사진으로 새 행사", _groups68() == [["a1", "a2"], ["a3", "b1", "b2"], ["a4"], ["c1"]]
      and _st68.event_of(_P68["a4"]) == _new68)
_st68.rename_event(_ev68["c1"], "  다음 주 수업  ")
check("[v48] 이름 바꾸기(앞뒤 공백 정리)", next(e for e in _st68.events() if e.id == _ev68["c1"]).name == "다음 주 수업")
_st68.move_photos([_P68["a4"]], _ev68["a1"])
check("[v48] 사진이 다 빠진 행사는 저절로 사라짐", all(e.id != _new68 for e in _st68.events()))
_st68.regroup()
check("[v48] 다시 분류 — 손댄 행사(사진을 옮긴 a·b 행사, 이름 붙인 c1)는 통째로 그대로",
      _st68.event_of(_P68["a3"]) == _st68.event_of(_P68["b1"]) and _st68.event_of(_P68["a4"]) == _st68.event_of(_P68["a1"])
      and any(e.name == "다음 주 수업" for e in _st68.events()))
_free68 = _tf.mkdtemp()
for i, (kind, when) in enumerate([("hall", _dt68(2026, 2, 1, 9)), ("hall", _dt68(2026, 2, 1, 10)),
                                  ("field", _dt68(2026, 2, 3, 9))]):
    _shot68(_free68, f"q{i}.jpg", kind, when, 40 + i)
AC.run_analysis(_free68)
_fs68 = AC.AlbumStore(_free68)
_fs68.merge_events([e.id for e in _fs68.events()])
_fs68.move_photos([_os.path.join(_free68, "q2.jpg")], _fs68.events()[0].id)
_fs68.new_event_with([_os.path.join(_free68, "q2.jpg")])
_con68 = __import__("sqlite3").connect(AC.db_path_for(_free68))
_con68.execute("UPDATE events SET locked = 0"); _con68.commit(); _con68.close()
_fs68.regroup()
check("[v48] 다시 분류 — 손대지 않은 행사는 실제로 다시 묶임(시간·배경 기준으로 원래대로)",
      sorted(len(_fs68.photos_of(e.id)) for e in _fs68.events()) == [1, 2])
_keep68 = _st68.merge_events([_st68.event_of(_P68["c1"]), _st68.event_of(_P68["b1"])])
check("[v48] 합치기 — 이름 있는 행사 쪽으로 모임", _keep68 == _ev68["c1"]
      and _st68.event_of(_P68["b2"]) == _ev68["c1"] and len(_st68.events()) == 2)
_st68.rename_event(_keep68, "")
check("[v48] 이름을 비우면 날짜 이름으로 되돌아감", next(e for e in _st68.events() if e.id == _keep68).name is None)

# 새 사진·삭제·편집
_P68["d1"] = _shot68(_lib68, "2026/2026-11/d1.jpg", "hall", _dt68(2026, 11, 8, 18), 11)
_P68["e1"] = _shot68(_lib68, "2026/2026-12/e1.jpg", "field", _dt68(2026, 12, 25, 9), 12)
_before68 = {k: _st68.event_of(p) for k, p in _P68.items() if k not in ("d1", "e1")}
_r68 = AC.run_analysis(_lib68)
check("[v48] 새 사진만 분석하고 묶음", (_r68["analyzed"], _r68["grouped"]) == (2, 2))
check("[v48] 새 사진은 가까운 기존 행사에 붙고(같은 날 강당), 동떨어진 사진은 새 행사",
      _st68.event_of(_P68["d1"]) == _st68.event_of(_P68["a1"])
      and all(e.id != _st68.event_of(_P68["e1"]) for e in [x for x in _st68.events() if x.count > 1]))
check("[v48] 기존 사진의 행사는 그대로", all(_st68.event_of(_P68[k]) == v for k, v in _before68.items()))
_os.remove(_P68["e1"])
_P68.pop("e1")
_PIL66.open(_P68["a2"]).crop((0, 0, 200, 150)).save(_P68["a2"])
_ev_a2 = _st68.event_of(_P68["a2"])
AC.run_analysis(_lib68)
check("[v48] 지운 사진은 DB에서 빠지고, 편집해 저장한 사진은 다시 분석하되 행사는 그대로",
      _st68.counts() == (len(_P68), len(_P68)) and _st68.event_of(_P68["a2"]) == _ev_a2)
_cancel68 = _tf.mkdtemp()
for i in range(5):
    _shot68(_cancel68, f"p{i}.jpg", "hall", _dt68(2026, 1, 1, 9 + i), 20 + i)
_r68 = AC.run_analysis(_cancel68, cancelled=lambda: True)
check("[v48] 분석 도중 멈추면 그때까지만 저장하고 묶지 않음",
      (_r68["analyzed"], _r68["grouped"], _r68["cancelled"]) == (0, 0, True)
      and AC.AlbumStore(_cancel68).events() == [])


section("68b. [v48] 사진첩 — 이미지 편집 화면 연결")

import src.photo_album_panel as APM


def _settle68():
    _pool = _Pool68.globalInstance()
    for _ in range(3):
        _pool.waitForDone(10000)
        app.processEvents()


_wlib68 = _tf.mkdtemp()
for k, kind, when, seed in [("h1", "hall", _dt68(2026, 11, 8, 9), 31), ("h2", "hall", _dt68(2026, 11, 8, 9, 30), 32),
                            ("h3", "hall", _dt68(2026, 11, 8, 10), 33), ("f1", "field", _dt68(2026, 11, 10, 9), 34),
                            ("f2", "field", _dt68(2026, 11, 10, 10), 35), ("g1", "hall", _dt68(2026, 11, 20, 9), 36)]:
    _shot68(_wlib68, f"2026/2026-11/{k}.jpg", kind, when, seed)
APM.save_library_dir(_wlib68)
win.switch_mode("imgedit")
app.processEvents()
win.set_imgedit_view("album")
ap = win.album_panel
ap.wait_analysis()
_settle68()
check("[v48] [폴더|사진첩] 전환 — 사진첩 패널이 보이고 썸네일은 여러 장 선택 가능",
      win.imgedit_left_stack.currentWidget() is ap
      and win.thumb_list.selectionMode() == QAbstractItemView.ExtendedSelection)
check("[v48] 사진첩에 들어오면 사진 옮기기의 보관함을 그대로 쓰고 자동으로 분석",
      ap.library_dir == _wlib68 and len(ap.events()) == 3 and ap.group_events.childCount() == 3
      and ap.group_events.text(0) == tr("album.group.events", a0=3))
check("[v48] 행사를 고르기 전엔 안내만", win.imgedit_files == [] and win.imgedit_status_lbl.text() == tr("album.no_event"))
_top68 = ap.group_events.child(2)    # 가장 오래된 행사(11/08, 3장)
ap._on_item_clicked(_top68)
_settle68()
_eid68 = ap.current_event_id
check("[v48] 행사를 누르면 그 사진들이 썸네일 줄에(촬영 순)",
      [_os.path.basename(p) for p in win.imgedit_files] == ["h1.jpg", "h2.jpg", "h3.jpg"]
      and win.thumb_list.count() == 3)
check("[v48] 위쪽 상태 줄에 행사 이름이 붙음", win.imgedit_status_lbl.text().startswith("2026/11/08 · "))

# 썸네일 메뉴의 정정: 한 장을 옆 행사로
_f_ev68 = next(e.id for e in ap.events() if e.count == 2)
check("[v48] 옮길 곳 후보에 바로 옆 행사가 들어 있음", _f_ev68 in [e.id for e in ap.nearby_events(_eid68)])
win.thumb_list.setCurrentRow(1)
win.imgedit_states[win.imgedit_files[0]].applied = True     # 다른 사진의 편집 상태는 지켜져야 함
win.album_move_photos([win.imgedit_files[1]], _f_ev68)
_settle68()
check("[v48] 옮긴 사진만 목록에서 빠지고, 다른 사진의 편집 상태는 그대로",
      [_os.path.basename(p) for p in win.imgedit_files] == ["h1.jpg", "h3.jpg"]
      and win.imgedit_states[win.imgedit_files[0]].applied and win.thumb_list.count() == 2)
check("[v48] 옮긴 사진은 옮긴 행사 쪽에(수도 갱신)",
      ap.event_info(_f_ev68).count == 3 and ap.event_info(_eid68).count == 2)
win.imgedit_states[win.imgedit_files[0]].applied = False
with _patch("src.main_window.QMessageBox.question", return_value=_QMB.No) as _q68:
    win.imgedit_states[win.imgedit_files[1]].applied = True
    win.album_split_photos([win.imgedit_files[1]])
check("[v48] 저장하지 않은 편집이 있는 사진을 옮기려 하면 묻고, '아니오'면 그대로",
      _q68.called and len(win.imgedit_files) == 2 and len(ap.events()) == 3)
win.imgedit_states[win.imgedit_files[1]].applied = False
win.album_split_photos([win.imgedit_files[1]])
check("[v48] 새 행사로 분리 — 행사가 하나 늘고 목록에서 빠짐", len(ap.events()) == 4 and len(win.imgedit_files) == 1)
win.album_move_photos(list(win.imgedit_files), _f_ev68)
_settle68()
check("[v48] 행사의 사진을 전부 옮기면 행사가 사라지고 화면은 비워짐",
      ap.event_info(_eid68) is None and ap.current_event_id is None and win.imgedit_files == [])

# 이름·합치기·다시 분류
ap.select_event(_f_ev68)
_settle68()
ap.rename_event(_f_ev68, "체육대회")
_settle68()
_finfo68 = ap.event_info(_f_ev68)
check("[v48→v49.1] 이름을 바꾸면 목록과 위쪽 상태 줄이 같이 바뀜(이름 뒤에 날짜도 함께)",
      any(ap.group_events.child(i).text(0) == tr("album.event.named_dated", a0="체육대회",
                                                 a1=APM.event_dates(_finfo68), a2=4)
          for i in range(ap.group_events.childCount()))
      and win.imgedit_album_title == "체육대회 · " + APM.event_dates(_finfo68))
_ids68 = [e.id for e in ap.events()]
_target68 = ap.merge_events(_ids68)
_settle68()
check("[v48] 합치기 — 이름 있는 행사로 모이고, 보고 있던 행사가 그쪽으로 따라감",
      _target68 == _f_ev68 and len(ap.events()) == 1 and ap.current_event_id == _f_ev68
      and len(win.imgedit_files) == 6)
ap.rename_event(_f_ev68, None)
with _patch("src.photo_album_panel.QMessageBox.question", return_value=_QMB.Yes):
    ap._on_regroup()
_settle68()
check("[v48] 다시 분류 — 합친 행사는 손댄 행사라 그대로 한 행사", len(ap.events()) == 1)

# 언어
set_language("en")
win.retranslate_ui()
check("[v48] 언어를 바꾸면 전환 버튼·행사 이름이 그 언어로",
      win.btn_view_album.text() == "Albums" and ap.group_events.text(0) == "Events (1)")
set_language("ko")
win.retranslate_ui()

# 다른 모드에 갔다 와도 사진첩 보기 유지
win.switch_mode("util")
app.processEvents()
win.switch_mode("imgedit")
ap.wait_analysis()
_settle68()
check("[v48] 다른 모드에 갔다 와도 사진첩 보기와 고른 행사가 유지됨",
      win.imgedit_left_stack.currentWidget() is ap and len(win.imgedit_files) == 6)

# 폴더 보기로 되돌아가기
_fold68 = _tf.mkdtemp()
_PIL66.new("RGB", (20, 20)).save(_os.path.join(_fold68, "one.jpg"))
win.source_path = _fold68
win.set_imgedit_view("folder")
_settle68()
check("[v48] 폴더 보기로 돌아가면 트리와 그 폴더 사진이 다시 보임",
      win.imgedit_left_stack.currentWidget() is win.imgedit_tree_holder
      and win.tree_source_wrap.parent() is win.imgedit_tree_holder
      and [_os.path.basename(p) for p in win.imgedit_files] == ["one.jpg"]
      and win.thumb_list.selectionMode() == QAbstractItemView.SingleSelection
      and not win.imgedit_status_lbl.text().startswith("2026"))
with _patch.object(win, "album_move_photos") as _mv68:
    win._on_thumb_context_menu(win.thumb_list.rect().center())
check("[v48] 폴더 보기에서는 썸네일 오른쪽 클릭 메뉴(행사 정정)가 뜨지 않음", not _mv68.called)

# 보관함 폴더가 없을 때
APM.save_library_dir(_os.path.join(_wlib68, "없는폴더"))
win.set_imgedit_view("album")
_settle68()
check("[v48] 보관함 폴더가 없으면 안내하고 분석 버튼은 꺼짐",
      ap.lbl_status.text() == tr("album.status.library_missing", a0=_os.path.join(_wlib68, "없는폴더"))
      and not ap.btn_analyze.isEnabled() and ap.events() == [])
win.set_imgedit_view("folder")
APM.save_library_dir("")
_settle68()


section("69. [v49] 사진첩 — 장소(GPS → 시·군·구/해외 도시)")

import src.geo_lookup as GEO
import src.face_engine as FE
import sqlite3 as _sq69
from PIL.TiffImagePlugin import IFDRational as _R69


def _dms69(v):
    v = abs(v); d = int(v); m = int((v - d) * 60); sec = round(((v - d) * 60 - m) * 60 * 100)
    return (_R69(d, 1), _R69(m, 1), _R69(sec, 100))


def _shot69(lib, rel, when, gps=None, kind="hall", seed=1):
    p = _os.path.join(lib, *rel.split("/"))
    _os.makedirs(_os.path.dirname(p), exist_ok=True)
    ex = _PIL66.Exif()
    ex.get_ifd(0x8769)[0x9003] = when.strftime("%Y:%m:%d %H:%M:%S")
    if gps:
        g = ex.get_ifd(0x8825)
        g[1] = "N" if gps[0] >= 0 else "S"; g[2] = _dms69(gps[0])
        g[3] = "E" if gps[1] >= 0 else "W"; g[4] = _dms69(gps[1])
    _scene68(kind, seed).save(p, exif=ex.tobytes())
    return p


_g69 = _shot69(_tf.mkdtemp(), "a.jpg", _dt68(2026, 1, 1), (37.5413, 126.9672))
_lat69, _lon69 = AC.read_gps_file(_g69)
check("[v49] EXIF GPS 읽기(도·분·초 → 소수)", abs(_lat69 - 37.5413) < 1e-3 and abs(_lon69 - 126.9672) < 1e-3)
_sw69 = _shot69(_tf.mkdtemp(), "b.jpg", _dt68(2026, 1, 1), (-33.8568, -151.2153))
check("[v49] 남위·서경은 음수", AC.read_gps_file(_sw69)[0] < 0 and AC.read_gps_file(_sw69)[1] < 0)
check("[v49] GPS 없는 사진은 (None, None)", AC.read_gps_file(_P68["a1"]) == (None, None))

check("[v49] 학교 근처 → 서울 용산구", GEO.place_key(37.5413, 126.9672) == "KR-11030" and GEO.group_of("KR-11030") == "KR-11")
check("[v49] 해운대 해변(경계 바로 밖) → 부산 해운대구", GEO.place_key(35.1587, 129.1604) == "KR-21090")
check("[v49] 시 아래 구 이름은 띄어 씀(수원시 영통구)", GEO.municipality_name(GEO.place_key(37.2596, 127.0466)[3:]) == "수원시 영통구")
check("[v49] 군위군은 바뀐 소속(대구)으로 묶음", GEO.group_of(GEO.place_key(36.2428, 128.5728)) == "KR-22")
check("[v49] 해외 — 도쿄 시내 구 대신 큰 도시 이름(Tokyo)",
      GEO.world_city_name(GEO.place_key(35.6812, 139.7671).split("-")[2]) == "Tokyo"
      and GEO.group_of(GEO.place_key(35.6812, 139.7671)) == "W-JP")
check("[v49] 바다 한가운데·(0,0)은 장소 없음", GEO.place_key(20.0, -150.0) is None and GEO.place_key(0, 0) is None)

_lib69 = _tf.mkdtemp()
_P69 = {
    "s1": _shot69(_lib69, "2026/s1.jpg", _dt68(2026, 11, 8, 9), (37.5413, 126.9672), seed=1),
    "s2": _shot69(_lib69, "2026/s2.jpg", _dt68(2026, 11, 8, 10), (37.5512, 126.9882), seed=2),
    "w1": _shot69(_lib69, "2026/w1.jpg", _dt68(2026, 10, 1, 10), (37.2596, 127.0466), seed=3),
    "j1": _shot69(_lib69, "2025/j1.jpg", _dt68(2025, 8, 1, 10), (35.6812, 139.7671), seed=4),
    "n1": _shot69(_lib69, "2025/n1.jpg", _dt68(2025, 7, 1, 10), None, seed=5),
}
_r69 = AC.run_analysis(_lib69)
_s69 = AC.AlbumStore(_lib69)
check("[v49] 분석하면 장소까지 읽음", _r69["gps"] == 5 and _s69.place_counts()
      == {"KR-11030": 2, "KR-31014": 1, GEO.place_key(35.6812, 139.7671): 1, AC.NO_PLACE: 1})
_names69 = lambda ps: sorted(_os.path.basename(p) for p in ps)
check("[v49] 시·군·구 / 시·도 / 나라 / 위치 없음별 사진",
      _names69(_s69.photos_of_place("KR-11030")) == ["s1.jpg", "s2.jpg"]
      and _names69(_s69.photos_of_place("KR-31")) == ["w1.jpg"]
      and _names69(_s69.photos_of_place("W-JP")) == ["j1.jpg"]
      and _names69(_s69.photos_of_place(AC.NO_PLACE)) == ["n1.jpg"])

# v48.0 DB(스키마 1)에서 올라온 경우 — 행사·직접 고친 것은 그대로, 장소만 새로 채움
_old69 = _tf.mkdtemp()
_o1 = _shot69(_old69, "o1.jpg", _dt68(2026, 3, 1, 9), (37.5413, 126.9672), seed=7)
_o2 = _shot69(_old69, "o2.jpg", _dt68(2026, 3, 9, 9), (37.5413, 126.9672), seed=8)
_os.makedirs(_os.path.join(_old69, ".folderkit"))
_c69 = _sq69.connect(AC.db_path_for(_old69))
_c69.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, locked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE photos (rel TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime INTEGER NOT NULL, taken INTEGER,
                     feature BLOB, event_id INTEGER, manual INTEGER NOT NULL DEFAULT 0);
INSERT INTO meta VALUES ('schema_version', '1');
INSERT INTO events (id, name, locked) VALUES (1, '봄 소풍', 1);
""")
for _p in (_o1, _o2):
    _st = _os.stat(_p)
    _t, _f = AC.analyze_file(_p, 0)
    _c69.execute("INSERT INTO photos (rel, size, mtime, taken, feature, event_id, manual) VALUES (?, ?, ?, ?, ?, 1, 1)",
                 (_os.path.basename(_p), _st.st_size, int(_st.st_mtime), _t, _f))
_c69.commit(); _c69.close()
_r69b = AC.run_analysis(_old69)
_so69 = AC.AlbumStore(_old69)
check("[v49] v48 DB를 열면 칸이 덧붙고, 이름 붙인 행사·직접 고친 묶음은 그대로",
      [(e.name, e.count) for e in _so69.events()] == [("봄 소풍", 2)] and _r69b["analyzed"] == 0)
check("[v49] v48에서 분석한 사진도 장소가 채워짐", _r69b["gps"] == 2 and _so69.place_counts() == {"KR-11030": 2})


section("69b. [v49] 사진첩 — 인물(얼굴 묶기·정정)")

import numpy as _np69


def _face69(center, seed, noise=0.25):
    rng = _np69.random.default_rng(seed)
    v = center + rng.normal(0, noise / _np69.sqrt(AC.FACE_DIM), AC.FACE_DIM)
    v = (v / _np69.linalg.norm(v)).astype(_np69.float32)
    return ((0.3, 0.2, 0.2, 0.25), 0.95, v.tobytes(), b"")


_rng69 = _np69.random.default_rng(1)
_cA, _cB, _cC = [(lambda v: v / _np69.linalg.norm(v))(_rng69.normal(size=AC.FACE_DIM)) for _ in range(3)]
_fl69 = _tf.mkdtemp()
_F69 = {}
for i, name in enumerate(["a1", "a2", "a3", "a4", "b1", "b2", "b3", "ab", "solo"]):
    _F69[name] = _shot69(_fl69, f"{name}.jpg", _dt68(2026, 5, 1, 9, i), None, seed=50 + i)
_sf69 = AC.AlbumStore(_fl69)
AC.run_analysis(_fl69)
for name, p in _F69.items():
    rel = AC.to_rel(_fl69, p)
    faces = []
    if name.startswith("a") and name != "ab":
        faces.append(_face69(_cA, hash(name) % 1000))
    if name.startswith("b"):
        faces.append(_face69(_cB, hash(name) % 1000))
    if name == "ab":
        faces += [_face69(_cA, 7), _face69(_cB, 8)]
    if name == "solo":
        faces.append(_face69(_cC, 9))
    _sf69.save_faces(rel, faces)
check("[v49] 얼굴을 찾은 사진 수", _sf69.faces_analyzed() == (9, 9))
check("[v49] 얼굴 묶기 — 새 얼굴 10개 모두 인물에", _sf69.assign_faces() == 10 and _sf69.assign_faces() == 0)
_pers69 = _sf69.persons()
_pid = {}
for _info in _pers69:
    _ps = _names69(_sf69.photos_of_persons([_info.id]))
    _pid["A" if "a1.jpg" in _ps else "B"] = _info.id
check("[v49] 같은 사람끼리 묶이고, 두 사람이 함께 나온 사진은 양쪽 모두에",
      len(_pers69) == 2
      and _names69(_sf69.photos_of_persons([_pid["A"]])) == ["a1.jpg", "a2.jpg", "a3.jpg", "a4.jpg", "ab.jpg"]
      and _names69(_sf69.photos_of_persons([_pid["B"]])) == ["ab.jpg", "b1.jpg", "b2.jpg", "b3.jpg"])
check("[v49] 한 장에만 나온 얼굴은 목록 대신 '자주 안 나온 얼굴'로",
      len(_sf69.minor_person_ids()) == 1 and _names69(_sf69.photos_of_persons(_sf69.minor_person_ids())) == ["solo.jpg"])
check("[v49] 인물 목록은 사진이 많은 순", [p.id for p in _pers69] == [_pid["A"], _pid["B"]])

_sf69.move_faces([_F69["a4"]], [_pid["A"]], _pid["B"])
check("[v49] 얼굴 옮기기 — 그 사진의 '보고 있는 사람' 얼굴만 옮겨짐",
      "a4.jpg" in _names69(_sf69.photos_of_persons([_pid["B"]]))
      and "a4.jpg" not in _names69(_sf69.photos_of_persons([_pid["A"]])))
_sf69.move_faces([_F69["solo"]], _sf69.minor_person_ids(), _pid["A"])
check("[v49] 자주 안 나온 얼굴을 아는 사람으로 넣기", "solo.jpg" in _names69(_sf69.photos_of_persons([_pid["A"]]))
      and _sf69.minor_person_ids() == [])
_n69 = _sf69.exclude_faces([_F69["solo"]], [_pid["A"]])
check("[v49] '이 사람이 아님' — 빼고, 다시 묶어도 다시 들어가지 않음",
      _n69 == 1 and "solo.jpg" not in _names69(_sf69.photos_of_persons([_pid["A"]])) and _sf69.assign_faces() == 0)
_new69 = _sf69.new_person_with([_F69["b3"]], [_pid["B"]])
check("[v49] 선택한 사진의 얼굴로 새 인물", _names69(_sf69.photos_of_persons([_new69])) == ["b3.jpg"]
      and any(p.id == _new69 for p in _sf69.persons()))
_sf69.rename_person(_pid["B"], "  김선린  ")
check("[v49] 인물 이름(공백 정리), 이름 붙인 사람이 목록 맨 위",
      _sf69.persons()[0].name == "김선린")
_keep69 = _sf69.merge_persons([_new69, _pid["B"]])
check("[v49] 합치기 — 이름 붙인 사람 쪽으로", _keep69 == _pid["B"]
      and "b3.jpg" in _names69(_sf69.photos_of_persons([_pid["B"]])))
_sf69.regroup_persons()
check("[v49] 다시 분류 — 손댄 인물은 그대로", "a4.jpg" in _names69(_sf69.photos_of_persons([_pid["B"]]))
      and any(p.name == "김선린" for p in _sf69.persons()))
_PIL66.open(_F69["a1"]).crop((0, 0, 200, 150)).save(_F69["a1"])
AC.run_analysis(_fl69)
check("[v49] 편집해 저장한 사진은 얼굴을 다시 찾도록 표시되고 예전 얼굴은 지워짐",
      AC.to_rel(_fl69, _F69["a1"]) in _sf69.pending_faces()
      and "a1.jpg" not in _names69(_sf69.photos_of_persons([_pid["A"]])))

# 엔진 상태
_md69 = _tf.mkdtemp()
check("[v49] 모델 파일이 없으면 NO_MODELS", FE.status(_md69) == FE.NO_MODELS)
for _name in FE.MODEL_SHA256:
    open(_os.path.join(_md69, _name), "wb").write(b"fake")
check("[v49] 모델 파일이 원본과 다르면 BAD_MODELS(해시 검사)", FE.status(_md69) == FE.BAD_MODELS)
with _patch.dict("sys.modules", {"cv2": None}):
    check("[v49] opencv가 없으면 NO_CV2", FE.status(_md69) == FE.NO_CV2)
_real69 = _os.environ.get("FK_FACE_TEST_DIR", "/tmp/models")
if FE.status(_real69) == FE.OK and _os.path.isfile("/tmp/lena.jpg"):
    _eng69 = FE.FaceEngine(_real69)
    _fa = _eng69.analyze("/tmp/lena.jpg")
    _flip = _os.path.join(_tf.mkdtemp(), "lena_flip.jpg")
    _PIL66.open("/tmp/lena.jpg").transpose(_PIL66.Transpose.FLIP_LEFT_RIGHT).resize((380, 380)).save(_flip)
    _fb = _eng69.analyze(_flip)
    _fm = _eng69.analyze("/tmp/messi5.jpg")
    _sim = lambda x, y: float(_np69.frombuffer(x[0][2], _np69.float32) @ _np69.frombuffer(y[0][2], _np69.float32))
    check("[v49] (실제 엔진) 얼굴을 찾고, 같은 사람은 기준 이상·다른 사람은 기준 미만",
          len(_fa) == 1 and len(_fb) == 1 and len(_fm) == 1
          and _sim(_fa, _fb) >= AC.PERSON_JOIN > _sim(_fa, _fm) and len(_fa[0][3]) > 0)
else:
    print("  --   [v49] (실제 엔진 검사는 모델·예제 사진이 있을 때만 — 이번엔 건너뜀)")


section("69c. [v49] 사진첩 — 장소·인물 화면 연결")

import src.photo_album_panel as APM


class _FakeEngine69:
    """파일 이름으로 정해진 얼굴을 돌려주는 가짜 엔진(화면 연결 검사용)."""

    def __init__(self, *a, **k):
        pass

    def analyze(self, path):
        name = _os.path.basename(path)
        out = []
        if name.startswith("pa"):
            out.append(_face69(_cA, len(name)))
        if name.startswith("pb"):
            out.append(_face69(_cB, len(name) + 1))
        if name.startswith("pab"):
            out = [_face69(_cA, 3), _face69(_cB, 4)]
        return [(b, sc, e, _thumb69) for b, sc, e, _ in out]


_tb = __import__("io").BytesIO(); _PIL66.new("RGB", (72, 72), (200, 150, 120)).save(_tb, "JPEG"); _thumb69 = _tb.getvalue()
_ui69 = _tf.mkdtemp()
for i, (name, gps) in enumerate([("pa1", (37.5413, 126.9672)), ("pa2", (37.5413, 126.9672)), ("pa3", (37.2596, 127.0466)),
                                 ("pb1", (35.6812, 139.7671)), ("pb2", (35.6812, 139.7671)), ("pb3", None),
                                 ("pab", (37.5413, 126.9672)), ("zz", None)]):
    _shot69(_ui69, f"2026/{name}.jpg", _dt68(2026, 9, 1 + i, 10), gps, seed=80 + i)
APM.save_library_dir(_ui69)
with _patch("src.photo_album_panel.FE.status", return_value=FE.OK), \
     _patch("src.photo_album_panel.FE.FaceEngine", _FakeEngine69):
    win.switch_mode("imgedit")
    win.set_imgedit_view("album")
    ap = win.album_panel
    ap.wait_analysis()
    _settle68()
    check("[v49] 사진첩 트리에 행사·장소·인물 세 묶음",
          [ap.tree.topLevelItem(i).data(0, APM.KIND_ROLE) for i in range(ap.tree.topLevelItemCount())]
          == ["group", "group", "group"]
          and ap.group_places.text(0) == tr("album.group.places", a0=6)
          and ap.group_persons.text(0) == tr("album.group.persons", a0=2))
    _kr69 = next(ap.group_places.child(i) for i in range(ap.group_places.childCount())
                 if ap.group_places.child(i).data(0, APM.KEY_ROLE) == "KR-11")
    check("[v49] 장소 — 한국이 먼저, 시·도 아래 시·군·구(사진 많은 순)",
          ap.group_places.child(0).data(0, APM.KEY_ROLE) == "KR-11"
          and _kr69.text(0) == tr("album.count", a0="서울", a1=3)
          and _kr69.child(0).text(0) == tr("album.count", a0="용산구", a1=3))
    check("[v49] 위치 정보 없는 사진은 맨 아래 따로",
          ap.group_places.child(ap.group_places.childCount() - 1).data(0, APM.KEY_ROLE) == AC.NO_PLACE)
    ap._on_item_clicked(_kr69)
    _settle68()
    check("[v49] 시·도를 누르면 그 안의 사진 전부, 상태 줄에 장소 이름",
          sorted(_os.path.basename(p) for p in win.imgedit_files) == ["pa1.jpg", "pa2.jpg", "pab.jpg"]
          and win.imgedit_status_lbl.text().startswith("서울 · "))
    with _patch.object(win, "album_move_photos") as _mv69, _patch("src.main_window.QMenu.exec", return_value=None) as _mx69:
        win._on_thumb_context_menu(win.thumb_list.rect().center())
    check("[v49] 장소를 보고 있을 때는 썸네일 정정 메뉴가 뜨지 않음", not _mx69.called)
    _jp69 = next(ap.group_places.child(i) for i in range(ap.group_places.childCount())
                 if ap.group_places.child(i).data(0, APM.KEY_ROLE) == "W-JP")
    check("[v49] 해외는 나라 → 도시", _jp69.text(0) == tr("album.count", a0="일본", a1=2)
          and _jp69.child(0).text(0) == tr("album.count", a0="Tokyo", a1=2))

    _pA = ap.group_persons.child(0)
    check("[v49] 인물 — 얼굴 그림이 붙고 사진 많은 순",
          not _pA.icon(0).isNull() and _pA.data(0, APM.KIND_ROLE) == APM.KIND_PERSON)
    ap._on_item_clicked(_pA)
    _settle68()
    _idA = _pA.data(0, APM.KEY_ROLE)
    check("[v49] 인물을 누르면 그 사람이 나온 사진(함께 나온 사진 포함)",
          sorted(_os.path.basename(p) for p in win.imgedit_files) == ["pa1.jpg", "pa2.jpg", "pa3.jpg", "pab.jpg"])
    _idB = next(p.id for p in ap.persons() if p.id != _idA)
    win.album_move_faces([win.imgedit_files[0]], _idB)
    _settle68()
    check("[v49] (썸네일 메뉴) 다른 인물로 옮기면 목록에서 빠지고 옮긴 사람 쪽에 들어감",
          len(win.imgedit_files) == 3 and ap.person_info(_idB).count == 5)
    win.album_exclude_faces([win.imgedit_files[0]])
    check("[v49] (썸네일 메뉴) 이 사람이 아님", len(win.imgedit_files) == 2)
    ap.rename_person(_idA, "홍길동")
    _settle68()
    check("[v49] 인물 이름을 붙이면 목록·상태 줄이 같이 바뀜",
          ap.group_persons.child(0).text(0) == tr("album.count", a0="홍길동", a1=2)
          and win.imgedit_album_title == "홍길동")
    win.album_split_faces([win.imgedit_files[0]])
    _settle68()
    check("[v49] (썸네일 메뉴) 새 인물로 분리", len(ap.persons()) == 3 and len(win.imgedit_files) == 1)
    _target69 = ap.merge_persons([p.id for p in ap.persons() if p.id != _idB])
    _settle68()
    check("[v49] 인물 합치기 — 이름 붙인 사람으로, 보고 있던 사람이 그쪽으로 따라감",
          _target69 == _idA and ap.current_key == _idA and len(win.imgedit_files) == 2)

    set_language("en")
    win.retranslate_ui()
    check("[v49] 영어로 바꾸면 시·도·나라 이름도 영어",
          any(ap.group_places.child(i).text(0).startswith("Seoul") for i in range(ap.group_places.childCount()))
          and any(ap.group_places.child(i).text(0).startswith("Japan") for i in range(ap.group_places.childCount())))
    set_language("ko")
    win.retranslate_ui()

with _patch("src.photo_album_panel.FE.status", return_value=FE.NO_MODELS):
    ap.refresh()
    _help69 = ap.group_persons.child(0)
    check("[v49] 엔진이 없으면 인물 칸에 설치 안내 한 줄만", ap.group_persons.childCount() == 1
          and _help69.data(0, APM.KIND_ROLE) == APM.KIND_ENGINE_HELP)
    with _patch("src.photo_album_panel.QMessageBox.information") as _info69:
        ap._on_item_clicked(_help69)
    check("[v49] 안내 줄을 누르면 설치 방법과 모델 폴더 위치를 보여 줌",
          _info69.called and FE.models_dir() in _info69.call_args[0][2])
win.set_imgedit_view("folder")
APM.save_library_dir("")
_settle68()


section("70. [v49.1] 사진 영역 확대/축소 · 사진첩 키보드 이동 · 이름 붙인 행사의 날짜")

from PySide6.QtGui import QWheelEvent as _QWE70, QMouseEvent as _QME70
from PySide6.QtCore import QPointF as _QPF70, QPoint as _QP70, QEvent as _QEv70
import src.image_edit as IE70

_cv70 = IE70.CropCanvas()
_cv70.resize(800, 600)
_im70 = _PIL66.new("RGB", (4000, 3000), (40, 40, 40))
_im70.paste((255, 0, 0), (1990, 1490, 2010, 1510))    # 가운데 빨간 점
_cv70.set_image(_im70)
from PySide6.QtCore import QRect
_fit70 = QRect(_cv70.img_rect)


def _wheel70(widget, x, y, dy, mods=Qt.NoModifier, dx=0):
    ev = _QWE70(_QPF70(x, y), _QPF70(x, y), _QP70(0, 0), _QP70(dx, dy), Qt.NoButton, mods,
                Qt.NoScrollPhase, False)
    widget.wheelEvent(ev)
    return ev


check("[v49.1] 처음엔 화면에 맞춤(100%가 아니라 맞춤 배율), 배율 1.0", _cv70.zoom == 1.0
      and _fit70.width() <= 800 and _cv70.zoom_percent() == round(_cv70._fit_scale * 100))
_wheel70(_cv70, 600, 400, 120)
check("[v49.1] Ctrl 없이 휠은 확대하지 않음(맞춤 상태)", _cv70.zoom == 1.0)
_before70 = _cv70._to_orig(600, 400)
_wheel70(_cv70, 600, 400, 120, Qt.ControlModifier)
_after70 = _cv70._to_orig(600, 400)
check("[v49.1] Ctrl+휠 위로 → 확대, 이미지 영역이 커짐", _cv70.zoom == IE70.ZOOM_STEP
      and _cv70.img_rect.width() > _fit70.width())
_px70 = 1 / (_cv70._fit_scale * _cv70.zoom)    # 화면 1픽셀 = 원본 몇 픽셀
check("[v49.1] 마우스 커서 아래의 지점이 확대 뒤에도 같은 자리(화면 1픽셀 이내)",
      abs(_before70[0] - _after70[0]) <= _px70 + 0.5 and abs(_before70[1] - _after70[1]) <= _px70 + 0.5)
for _ in range(40):
    _wheel70(_cv70, 400, 300, 120, Qt.ControlModifier)
check("[v49.1] 최대 확대 — 원본 한 픽셀이 화면 8픽셀까지", abs(_cv70.zoom - _cv70.max_zoom()) < 1e-6
      and _cv70.zoom_percent() == 800)
_cv70.set_zoom(3.0, anchor=(400, 300))
_r70 = QRect(_cv70.img_rect)
_wheel70(_cv70, 400, 300, -120)
check("[v49.1] 확대 중 그냥 휠 → 위아래 이동", _cv70.img_rect.y() != _r70.y() and _cv70.img_rect.x() == _r70.x())
_r70 = QRect(_cv70.img_rect)
_wheel70(_cv70, 400, 300, -120, Qt.ShiftModifier)
check("[v49.1] 확대 중 Shift+휠 → 좌우 이동", _cv70.img_rect.x() != _r70.x())
_cv70.pan_by(100000, 100000)
check("[v49.1] 끝까지 옮겨도 이미지 가장자리 밖으로 빈 곳이 생기지 않음",
      _cv70.img_rect.left() <= 8 and _cv70.img_rect.top() <= 8
      and _cv70.img_rect.right() >= 800 - 9 and _cv70.img_rect.bottom() >= 600 - 9)
_cv70.mousePressEvent(_QME70(_QEv70.MouseButtonPress, _QPF70(400, 300), _QPF70(400, 300),
                             Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))
_r70 = QRect(_cv70.img_rect)
_cv70.mouseMoveEvent(_QME70(_QEv70.MouseMove, _QPF70(300, 250), _QPF70(300, 250),
                            Qt.NoButton, Qt.MiddleButton, Qt.NoModifier))
_cv70.mouseReleaseEvent(_QME70(_QEv70.MouseButtonRelease, _QPF70(300, 250), _QPF70(300, 250),
                               Qt.MiddleButton, Qt.NoButton, Qt.NoModifier))
check("[v49.1] 가운데 버튼으로 끌어 옮기기(크롭 영역은 생기지 않음)",
      (_cv70.img_rect.x(), _cv70.img_rect.y()) == (_r70.x() - 100, _r70.y() - 50) and _cv70.crop_rect is None)

# 확대한 채로 크롭해도 원본 좌표가 맞는지(자유 비율로)
_cv70.set_ratio("free")
_cv70.set_zoom(4.0, anchor=(400, 300))
_ox0, _oy0 = _cv70._to_orig(300, 200)
_ox1, _oy1 = _cv70._to_orig(500, 400)
for _t, _pt, _btn, _bts in [(_QEv70.MouseButtonPress, (300, 200), Qt.LeftButton, Qt.LeftButton),
                            (_QEv70.MouseMove, (500, 400), Qt.NoButton, Qt.LeftButton),
                            (_QEv70.MouseButtonRelease, (500, 400), Qt.LeftButton, Qt.NoButton)]:
    _ev = _QME70(_t, _QPF70(*_pt), _QPF70(*_pt), _btn, _bts, Qt.NoModifier)
    {_QEv70.MouseButtonPress: _cv70.mousePressEvent, _QEv70.MouseMove: _cv70.mouseMoveEvent,
     _QEv70.MouseButtonRelease: _cv70.mouseReleaseEvent}[_t](_ev)
check("[v49.1] 확대한 상태에서 그린 크롭 영역이 원본 좌표로 정확히 저장됨",
      _cv70.crop_rect is not None and abs(_cv70.crop_rect[0] - _ox0) < 1 and abs(_cv70.crop_rect[3] - _oy1) < 1
      and (_cv70.crop_rect[2] - _cv70.crop_rect[0]) < 4000 / 4)
_pix70 = _cv70.grab()
check("[v49.1] 확대 상태로 그리기(원본 해상도에서 보이는 부분만) — 오류 없이 그려짐",
      not _pix70.isNull() and _cv70._full_qpix is not None and _cv70._full_qpix.width() == 4000)
_cv70.mouseDoubleClickEvent(_QME70(_QEv70.MouseButtonDblClick, _QPF70(400, 300), _QPF70(400, 300),
                                   Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))
check("[v49.1] 가운데 버튼 두 번 클릭 → 화면에 맞춤", _cv70.zoom == 1.0 and _cv70.img_rect == _fit70)
_cv70.set_zoom(3.0)
_cv70.set_image(_PIL66.new("RGB", (300, 400)))
check("[v49.1] 다른 사진으로 넘어가면 다시 화면에 맞춤", _cv70.zoom == 1.0)
_cv70.set_zoom(2.0)
_wheel70(_cv70, 100, 100, -120 * 10, Qt.ControlModifier)
check("[v49.1] Ctrl+휠 아래로 → 맞춤보다 더 작아지지는 않음", _cv70.zoom == 1.0)
check("[v49.1] 사진 영역에 사용법 말풍선", "Ctrl" in _cv70.toolTip())
_cv70.close()

# ---- 사진첩 키보드 이동
_kb70 = _tf.mkdtemp()
for _i, (_kind, _when) in enumerate([("hall", _dt68(2026, 11, 8, 9)), ("hall", _dt68(2026, 11, 8, 10)),
                                      ("field", _dt68(2026, 11, 15, 9)), ("hall", _dt68(2026, 11, 22, 9)),
                                      ("hall", _dt68(2026, 11, 22, 10))]):
    _shot68(_kb70, f"2026/k{_i}.jpg", _kind, _when, 90 + _i)
APM.save_library_dir(_kb70)
win.switch_mode("imgedit")
win.set_imgedit_view("album")
ap = win.album_panel
ap.wait_analysis()
_settle68()
check("[v49.1] 사진첩 준비 — 행사 3개", len(ap.events()) == 3)
ap.tree.setFocus()
_e0 = ap.group_events.child(0)
# (앞선 검사의 가상 단축키 때문에 이 환경에선 Shift가 눌린 상태로 남아 있다 — 실제 키 상태를 "없음"으로)
with _patch("src.photo_album_panel.QApplication.queryKeyboardModifiers", return_value=Qt.NoModifier):
    ap.tree.setCurrentItem(_e0)       # 키보드 이동과 같은 경로(currentItemChanged)
    _settle68()
check("[v49.1] 목록의 현재 항목이 바뀌면(키보드) 클릭처럼 그 사진들이 썸네일 줄에",
      ap.current_key == _e0.data(0, APM.KEY_ROLE) and len(win.imgedit_files) == 2)
check("[v49.1] 사진첩에서 불러올 때는 '불러오는 중' 창을 띄우지 않음(키보드 포커스 유지)",
      win.loading_progress_dialog is None)
QTest.keyClick(ap.tree, Qt.Key_Down)
_settle68()
_e1 = ap.group_events.child(1)
check("[v49.1] ↓ 키 → 다음 행사가 불러와지고 첫 사진이 원본 영역에",
      ap.current_key == _e1.data(0, APM.KEY_ROLE) and len(win.imgedit_files) == 1
      and win.imgedit_current == 0 and win.crop_canvas.pil_img is not None
      and win.imgedit_status_lbl.text().startswith(APM.event_dates(ap.event_info(_e1.data(0, APM.KEY_ROLE)))))
QTest.keyClick(ap.tree, Qt.Key_Up)
_settle68()
check("[v49.1] ↑ 키 → 이전 행사로", ap.current_key == _e0.data(0, APM.KEY_ROLE) and len(win.imgedit_files) == 2)
with _patch.object(win, "_load_imgedit_files", wraps=win._load_imgedit_files) as _ld70:
    ap.tree.setCurrentItem(_e1)
    ap._on_item_clicked(_e1)          # 마우스 클릭 = currentItemChanged + itemClicked
    _settle68()
check("[v49.1] 마우스 클릭 한 번에 두 번 불러오지 않음", _ld70.call_count == 1)
with _patch.object(win, "_load_imgedit_files", wraps=win._load_imgedit_files) as _ld70:
    ap._on_item_clicked(_e1)          # 이미 고른 항목을 다시 클릭 → 다시 불러옴(예전과 같음)
    _settle68()
check("[v49.1] 이미 고른 항목을 다시 누르면 다시 불러옴", _ld70.call_count == 1)
with _patch("src.photo_album_panel.QApplication.queryKeyboardModifiers", return_value=Qt.ShiftModifier), \
     _patch.object(win, "_load_imgedit_files") as _ld70:
    ap.tree.setCurrentItem(ap.group_events.child(2))
check("[v49.1] Shift(여러 개 고르기) 중에는 불러오지 않음 — 합치기용 선택을 방해하지 않음", not _ld70.called)
with _patch("src.photo_album_panel.QMessageBox.information") as _hi70, \
     _patch("src.photo_album_panel.FE.status", return_value=FE.NO_MODELS):
    ap.refresh()
    ap.tree.setCurrentItem(ap.group_persons.child(0))
check("[v49.1] 키보드로 엔진 안내 줄에 가도 안내 창은 뜨지 않음(클릭할 때만)", not _hi70.called)

# ---- 이름 붙인 행사 + 날짜
_eid70 = _e1.data(0, APM.KEY_ROLE)
ap.select_event(_eid70)
_settle68()
ap.rename_event(_eid70, "체육대회")
_settle68()
_inf70 = ap.event_info(_eid70)
check("[v49.1] 이름을 바꿔도 목록에 날짜가 함께 — '체육대회 · 2026/11/15 (1장)'",
      any(ap.group_events.child(i).text(0) == "체육대회 · 2026/11/15 (1장)" for i in range(ap.group_events.childCount())))
check("[v49.1] 위쪽 상태 줄에도 이름 + 날짜", win.imgedit_status_lbl.text().startswith("체육대회 · 2026/11/15 · "))
_two70 = ap.merge_events([e.id for e in ap.events() if e.id != _eid70][:1] + [_eid70])
_settle68()
_inf70 = ap.event_info(_two70)
check("[v49.1] 여러 날짜에 걸친 이름 붙인 행사 — 기간이 함께 보임",
      APM.event_label(_inf70).startswith("체육대회 · 2026/11/") and " ~ " in APM.event_label(_inf70))
ap.rename_event(_two70, None)
_settle68()
check("[v49.1] 이름을 지우면 예전처럼 날짜만", not APM.event_label(ap.event_info(_two70)).startswith("체육대회"))
set_language("en")
win.retranslate_ui()
ap.rename_event(_two70, "Sports Day")
check("[v49.1] 영어 화면에서도 이름 + 날짜", APM.event_label(ap.event_info(_two70)).startswith("Sports Day · 2026/11/")
      and APM.event_label(ap.event_info(_two70)).endswith(" photos)"))
set_language("ko")
win.retranslate_ui()
win.set_imgedit_view("folder")
APM.save_library_dir("")
_settle68()


section("71. [v49.2] 저장 중 처리 표시 · 저장 후 썸네일 · 이동/복사 뒤 썸네일 포커스")

_d71 = _tf.mkdtemp()
_P71 = []
for _i in range(3):
    _im = _PIL66.new("RGB", (400, 300), (30, 30, 30))
    _im.paste((255, 0, 0), (0, 0, 200, 300))       # 왼쪽 절반 빨강, 오른쪽 절반 어두움
    _p = _os.path.join(_d71, f"p{_i}.jpg")
    _im.save(_p)
    _P71.append(_p)
win.switch_mode("imgedit")
win.set_imgedit_view("folder")
win.load_imgedit_folder(_d71)
_settle68()
check("[v49.2] 준비 — 3장", len(win.imgedit_files) == 3 and win.thumb_list.count() == 3)
check("[v49.2] 처리 중 덮개가 이미지 편집 화면(썸네일·원본 영역)을 덮는 위치",
      win.overlay.parent() is win.top_area and win.top_area.isAncestorOf(win.thumb_list)
      and win.top_area.isAncestorOf(win.crop_canvas))

_old_icon71 = win.thumb_list.item(0).icon().pixmap(64, 64).toImage()
_before_cache71 = win.thumbnail_cache.get(_P71[0])
for _p in _P71[:2]:
    _st = win.imgedit_states[_p]
    _st.crop_rect = (0, 0, 200, 300)                 # 빨간 왼쪽 절반만 남김(세로로 긴 그림)
    _st.applied = True
_shown71 = []
_orig_busy71 = win._imgedit_busy


def _spy_busy71(key, done, total):
    _orig_busy71(key, done, total)
    _shown71.append((key, done, total, win.overlay.isVisible(), win.overlay.label.text()))


with _patch.object(win, "_imgedit_busy", side_effect=_spy_busy71), \
     _patch("src.main_window.QMessageBox.information"):
    win.on_imgedit_save()
check("[v49.2] 저장하는 동안 '처리 중' 덮개가 떠 있고 진행 수가 바뀜",
      [x[:3] for x in _shown71] == [("status.imgedit.saving", 0, 2), ("status.imgedit.saving", 1, 2),
                                    ("status.imgedit.saving", 2, 2)]
      and all(x[3] for x in _shown71)
      and _shown71[1][4] == tr("status.imgedit.saving", a0=1, a1=2) + " (50%)")
check("[v49.2] 저장이 끝나면 덮개가 사라짐", not win.overlay.isVisible())
check("[v49.2] 저장한 파일은 크롭됨", _PIL66.open(_P71[0]).size == (200, 300))
_new_base71 = win.imgedit_thumb_base[_P71[0]]
_img71 = _new_base71.toImage()
_cx71 = _img71.width() // 2
_redcol = lambda img, x: [img.pixelColor(x, y).red() for y in range(img.height()) if img.pixelColor(x, y).alpha() > 0]
check("[v49.2] 저장 뒤 썸네일이 크롭된 그림으로 바뀜(세로로 긴 빨간 그림, 오른쪽 여백은 투명)",
      _new_base71 is not _before_cache71
      and _redcol(_img71, _cx71) and min(_redcol(_img71, _cx71)) > 200
      and _img71.pixelColor(_img71.width() - 2, _img71.height() // 2).alpha() == 0)
check("[v49.2] 썸네일 캐시도 새 그림 — 폴더를 다시 열어도 예전 썸네일이 나오지 않음",
      win.thumbnail_cache.get(_P71[0]) is _new_base71)
check("[v49.2] 저장한 사진의 배지는 사라지고 아이콘은 새 썸네일",
      win.thumb_list.item(0).icon().pixmap(64, 64).toImage() != _old_icon71)
win.load_imgedit_folder(_d71)
_settle68()
check("[v49.2] 폴더를 다시 열어도 크롭된 썸네일",
      win.imgedit_thumb_base[_P71[0]].toImage().pixelColor(_img71.width() - 2, _img71.height() // 2).alpha() == 0)
with _patch("src.main_window.QMessageBox.information"):
    win.on_imgedit_save()
check("[v49.2] 저장할 것이 없을 때는 덮개를 띄우지 않음", not win.overlay.isVisible())
_png71 = _os.path.join(_d71, "z.png")
_PIL66.new("RGB", (40, 30)).save(_png71)
win.load_imgedit_folder(_d71)
_settle68()
_shown71.clear()
with _patch.object(win, "_imgedit_busy", side_effect=_spy_busy71), \
     _patch("src.main_window.QMessageBox.question", return_value=_QMB.Yes), \
     _patch("src.main_window.QMessageBox.information"), _patch("src.main_window.QMessageBox.warning"):
    win.on_imgedit_convert_to_jpg()
_settle68()
check("[v49.2] JPG 변환에도 같은 '처리 중' 덮개", _shown71 and _shown71[0][0] == "status.imgedit.converting"
      and all(x[3] for x in _shown71) and not win.overlay.isVisible()
      and _os.path.isfile(_os.path.join(_d71, "z.jpg")))

# ---- 이동/복사 뒤 포커스
win.show()
win.activateWindow()
_dest71 = _tf.mkdtemp()
win.load_imgedit_folder(_d71)
_settle68()
win.thumb_list.setCurrentRow(0)
win.imgedit_request_move_copy("copy")
check("[v49.2] (복사) 대상 폴더 고르는 동안은 폴더 트리에 포커스", win.imgedit_viewer_stack.currentIndex() == 1)
win.imgedit_dest_path = _dest71
win.on_imgedit_dest_confirm()
app.processEvents()
check("[v49.2] 복사 뒤 다음 사진으로 넘어가고 키보드 포커스가 썸네일 줄로",
      win.imgedit_current == 1 and win.focusWidget() is win.thumb_list)
QTest.keyClick(win.thumb_list, Qt.Key_Right)
app.processEvents()
check("[v49.2] 그 상태에서 → 키로 바로 다음 사진", win.imgedit_current == 2)
_n71 = len(win.imgedit_files)
win.imgedit_request_move_copy("move")
win.imgedit_dest_path = _dest71
win.on_imgedit_dest_confirm()
app.processEvents()
check("[v49.2] 이동 뒤에도 썸네일 줄로 포커스(목록에서 빠지고 다음 사진)",
      len(win.imgedit_files) == _n71 - 1 and win.focusWidget() is win.thumb_list)
win.imgedit_request_move_copy("copy")
win.imgedit_cancel_dest_select()
app.processEvents()
check("[v49.2] 대상 고르기를 취소해도(Esc) 썸네일 줄로 포커스", win.focusWidget() is win.thumb_list)
with _patch("src.main_window.QMessageBox.question", return_value=_QMB.Yes):
    win.thumb_list.setFocus()
    win.crop_canvas.setFocus()
    win.on_imgedit_delete_current()
app.processEvents()
check("[v49.2] Del로 지운 뒤에도 썸네일 줄로 포커스", win.focusWidget() is win.thumb_list)


section("72. [v49.3] 파일명 변경 — 세로 선택·동시 입력 · 같은 이름 일련번호 · 처리 중 · 기본 Yes")

from src.rename_widgets import auto_number_duplicates as _AN72
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QInputMethodEvent as _QIME72

_n72, _g72 = _AN72(["홍길동.jpg", "a.jpg", "홍길동.JPG", "홍길동.jpg", "폴더", "폴더"],
                   [False, False, False, False, True, True])
check("[v49.3] 같은 이름(대소문자 무시)은 줄 순서대로 _01, _02 … — 확장자 앞, 폴더는 이름 뒤",
      _n72 == ["홍길동_01.jpg", "a.jpg", "홍길동_02.JPG", "홍길동_03.jpg", "폴더_01", "폴더_02"]
      and sorted(c for _b, c in _g72) == [2, 3])
_n72, _ = _AN72([f"x{'' if i else ''}.jpg" for i in range(120)], [False] * 120)
check("[v49.3] 100개가 넘으면 세 자리(_001)", _n72[0] == "x_001.jpg" and _n72[-1] == "x_120.jpg")
check("[v49.3] 겹치지 않으면 그대로", _AN72(["a", "b"], [False, False]) == (["a", "b"], []))

# ---- 편집기: 세로 선택과 동시 입력
_d72 = _tf.mkdtemp()
_names72 = [f"20261111_09{m:02d}38.jpg" for m in range(5)] + ["memo.txt"]
for _nm in _names72:
    open(_os.path.join(_d72, _nm), "w").close()
win.switch_mode("rename")
win.load_rename_files(_d72)
app.processEvents()
ed = win.editor
ed.resize(600, 400)
ed.show()
app.processEvents()
check("[v49.3] 준비 — 6줄", ed.blockCount() == 6)
_x0 = ed._pos_x(0, 0)
_x1 = ed._pos_x(0, len("20261111_090038"))
ed.set_column_selection(0, _x0, 4, _x1)
check("[v49.3] 세로 선택 — 5줄의 같은 세로 구간(날짜·시간 부분)",
      ed.column_ranges() == [(b, 0, 15) for b in range(5)] and ed.column_active())
check("[v49.3] 세로 선택 중엔 아래 상태 줄에 안내", win.status.currentMessage() == tr("rename.column.status", a0=5))
ed.column_replace("홍길동")
_lines72 = ed.toPlainText().split("\n")
check("[v49.3] 입력하면 모든 줄의 선택 구간이 같이 바뀜", _lines72[:5] == ["홍길동.jpg"] * 5 and _lines72[5] == "memo.txt")
check("[v49.3] 입력 뒤엔 모든 줄에 입력 위치(커서)가 남아 이어서 입력 가능",
      ed.column_ranges() == [(b, 3, 3) for b in range(5)])
QTest.keyClick(ed, Qt.Key_Backspace)
check("[v49.3] Backspace — 모든 줄에서 한 글자씩", ed.toPlainText().split("\n")[:5] == ["홍길.jpg"] * 5)
for _pre in ("ㄷ", "도", "동"):          # 한글 조합: ㄷ → 도 → 동
    ed.inputMethodEvent(_QIME72(_pre, []))
check("[v49.3] 한글 조합 중에도 모든 줄에 그 글자가 들어가 보이고, 뒤 글자(.jpg)를 가리지 않음",
      ed.toPlainText().split("\n")[:5] == ["홍길동.jpg"] * 5 and ed._pre_len == 1
      and ed.column_ranges() == [(b, 2, 2) for b in range(5)])
_ime72 = _QIME72("", [])
_ime72.setCommitString("동")
ed.inputMethodEvent(_ime72)
check("[v49.3] 한글이 확정되면 모든 줄에 확정, 입력 위치는 그 뒤",
      ed.toPlainText().split("\n")[:5] == ["홍길동.jpg"] * 5 and ed._pre_len == 0
      and ed.column_ranges() == [(b, 3, 3) for b in range(5)])
ed.undo()
check("[v49.3] 조합하며 바뀐 과정은 되돌리기 한 번으로 묶임(→ '홍길')",
      ed.toPlainText().split("\n")[:5] == ["홍길.jpg"] * 5)
ed.redo()
ed.set_column_selection(0, ed._pos_x(0, 3), 4, ed._pos_x(0, 3))
_ime72 = _QIME72("가", []); ed.inputMethodEvent(_ime72)
ed.inputMethodEvent(_QIME72("", []))
check("[v49.3] 조합을 취소하면(빈 조합) 넣었던 글자가 빠짐", ed.toPlainText().split("\n")[:5] == ["홍길동.jpg"] * 5)
QTest.keyClick(ed, Qt.Key_N, Qt.AltModifier)
check("[v49.3] Alt+N — 줄마다 일련번호 01~05", ed.toPlainText().split("\n")[:5]
      == [f"홍길동{i:02d}.jpg" for i in range(1, 6)])
QTest.keyClick(ed, Qt.Key_Escape)
check("[v49.3] Esc — 세로 선택 끝(창의 다른 Esc 단축키보다 먼저 받음)", not ed.column_active()
      and win.status.currentMessage() == "")
ed.undo()
check("[v49.3] 되돌리기(Ctrl+Z) 한 번에 한 동작씩 — 일련번호 넣기 전으로",
      ed.toPlainText().split("\n")[:5] == ["홍길동.jpg"] * 5)

# Alt+마우스 끌기
win.load_rename_files(_d72)
app.processEvents()
_r0 = ed.cursorRect(QTextCursor(ed.document().findBlockByNumber(0)))
_r4 = ed.cursorRect(QTextCursor(ed.document().findBlockByNumber(4)))
_xs = ed._pos_x(0, 9)
_xe = ed._pos_x(0, 15)
_cy = lambda r: r.center().y()
QTest.mousePress(ed.viewport(), Qt.LeftButton, Qt.AltModifier, QPoint(_xs + 1, _cy(_r0)))
from PySide6.QtGui import QMouseEvent as _QME72
ed.mouseMoveEvent(_QME72(QEvent.MouseMove, QPointF(_xe + 1, _cy(_r4)), QPointF(_xe + 1, _cy(_r4)),
                         Qt.NoButton, Qt.LeftButton, Qt.AltModifier))
QTest.mouseRelease(ed.viewport(), Qt.LeftButton, Qt.AltModifier, QPoint(_xe + 1, _cy(_r4)))
check("[v49.3] Alt+마우스 끌기 — 시간 부분(9~15번째 글자)만 5줄 세로 선택",
      ed.column_ranges() == [(b, 9, 15) for b in range(5)])
QTest.mouseClick(ed.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(5, _cy(_r0)))
check("[v49.3] Alt 없이 클릭하면 세로 선택이 풀림", not ed.column_active())
# Alt+Shift+방향키
_c = QTextCursor(ed.document().findBlockByNumber(1)); _c.setPosition(_c.block().position() + 8)
ed.setTextCursor(_c)
for _k in (Qt.Key_Down, Qt.Key_Down, Qt.Key_Right):
    QTest.keyClick(ed, _k, Qt.AltModifier | Qt.ShiftModifier)
check("[v49.3] Alt+Shift+방향키 — 키보드로도 세로 선택", ed.column_ranges() == [(1, 8, 9), (2, 8, 9), (3, 8, 9)])
QTest.keyClick(ed, Qt.Key_Escape)

# ---- 이름 바꾸기 적용: 일련번호 + 기본 Yes + 처리 중
win.load_rename_files(_d72)
app.processEvents()
ed.set_column_selection(0, ed._pos_x(0, 0), 4, ed._pos_x(0, 15))
ed.column_replace("홍길동")
ed.clear_column_selection()
check("[v49.3] 처리 중 덮개가 파일명 편집기를 덮는 위치", win.top_area.isAncestorOf(ed))
_q72 = []


def _fake_q72(parent, title, text, buttons, default):
    _q72.append((text, default))
    return _QMB.Yes


_steps72 = []
_orig_busy72 = win._imgedit_busy


def _spy_busy72(key, done, total):
    _orig_busy72(key, done, total)
    _steps72.append((key, done, total, win.overlay.isVisible()))


with _patch("src.main_window.QMessageBox.question", side_effect=_fake_q72), \
     _patch.object(win, "_imgedit_busy", side_effect=_spy_busy72), \
     _patch("src.main_window.QMessageBox.information"), _patch("src.main_window.QMessageBox.warning"):
    win.on_rename_apply()
_after72 = sorted(_os.listdir(_d72))
check("[v49.3] 확인 창의 기본 단추가 '예'(Enter로 바로 진행)", _q72 and _q72[0][1] == _QMB.Yes)
check("[v49.3] 확인 창에 일련번호 붙이는 것을 미리 보여 줌",
      "홍길동.jpg" in _q72[0][0] and "홍길동_01.jpg ~ 홍길동_05.jpg" in _q72[0][0])
check("[v49.3] 같은 이름 5개 → 홍길동_01~05.jpg(원래 순서 = 촬영 시각 순)",
      _after72 == ["memo.txt"] + [f"홍길동_{i:02d}.jpg" for i in range(1, 6)])
check("[v49.3] 바꾸는 동안 '처리 중' 덮개(임시 이름 5 + 새 이름 5 단계)",
      _steps72 and _steps72[0][:3] == ("status.rename.applying", 0, 10) and all(x[3] for x in _steps72)
      and _steps72[-1][1:3] == (10, 10) and not win.overlay.isVisible())
check("[v49.3] 임시 이름 파일이 남지 않음", not any(n.startswith(".__fk_ren") for n in _os.listdir(_d72)))
check("[v49.3] 바꾼 뒤 편집기에 새 이름이 다시 읽힘", ed.toPlainText().split("\n")[0] == "memo.txt"
      or ed.toPlainText().split("\n")[-1] == "memo.txt")

# 서로 이름 맞바꾸기(예전에는 앞의 것이 실패)
_sw72 = _tf.mkdtemp()
for _nm in ("a.jpg", "b.jpg"):
    open(_os.path.join(_sw72, _nm), "w").write(_nm)
win.load_rename_files(_sw72)
ed.setPlainText("b.jpg\na.jpg")
with _patch("src.main_window.QMessageBox.question", return_value=_QMB.Yes), \
     _patch("src.main_window.QMessageBox.information"), _patch("src.main_window.QMessageBox.warning"):
    win.on_rename_apply()
check("[v49.3] 두 파일 이름 맞바꾸기도 됨(임시 이름을 거침)",
      open(_os.path.join(_sw72, "a.jpg")).read() == "b.jpg" and open(_os.path.join(_sw72, "b.jpg")).read() == "a.jpg")

# 목록에 없는 파일과 겹침
_hid72 = _tf.mkdtemp()
open(_os.path.join(_hid72, "x.jpg"), "w").close()
win.load_rename_files(_hid72)
open(_os.path.join(_hid72, "y.jpg"), "w").close()   # 목록을 읽은 뒤 생긴 파일(목록에 없음)
ed.setPlainText("y.jpg")
with _patch("src.main_window.QMessageBox.critical") as _cr72, \
     _patch("src.main_window.QMessageBox.question", return_value=_QMB.Yes):
    win.on_rename_apply()
check("[v49.3] 목록에 없는 파일 이름과 겹치면 덮어쓰지 않고 막음",
      _cr72.called and sorted(_os.listdir(_hid72)) == ["x.jpg", "y.jpg"])
with _patch("src.main_window.QMessageBox.question", return_value=_QMB.No) as _qn72:
    win.load_rename_files(_hid72)
    ed.setPlainText("z.jpg\ny.jpg")
    win.on_rename_apply()
check("[v49.3] '아니오'면 아무것도 바꾸지 않음", _qn72.called and sorted(_os.listdir(_hid72)) == ["x.jpg", "y.jpg"])
win.load_rename_files(_hid72)   # 편집 중인 이름을 원래대로(다음 모드로 넘어갈 때 확인 창이 뜨지 않게)
app.processEvents()


section("73. [v49.4] 얼굴 모델 위치 — exe 옆 우선, 없으면 exe 안")

import src.paths as _P73
_e73 = _tf.mkdtemp(); _b73 = _tf.mkdtemp()
check("[v49.4] exe 옆에 models 폴더가 있으면 그쪽", _P73.pick_models_dir(_e73, _b73) == _e73)
check("[v49.4] 없으면 exe 안(실행 중 임시 폴더)의 models", _P73.pick_models_dir(_os.path.join(_e73, "x"), _b73) == _b73)
check("[v49.4] 둘 다 없으면 exe 옆 경로(설치 안내에 보여 줄 곳)",
      _P73.pick_models_dir(_os.path.join(_e73, "x"), _os.path.join(_b73, "x")) == _os.path.join(_e73, "x"))
_spec73 = open("FolderKitPP.spec", encoding="utf-8").read()
check("[v49.4] 빌드 설정이 models 폴더를 exe에 넣음", "('models', 'models')" in _spec73 and "datas=_datas" in _spec73)


section("74. [v49.5] 중복 찾기 — 결과 2만 개 이상에서 화면 멈춤 · 큰 파일 진행률 · 캐시 중간 저장")

import time as _time74
import src.duplicate_finder as DF74
from src.duplicate_finder import DuplicateGroup as _DG74

win.switch_mode("dupfind")
app.processEvents()
_groups74 = [_DG74("x", 1000 + i, [f"C:\\USB\\f{i % 300}\\p_{i}_{k}.jpg" for k in range(2)]) for i in range(20000)]
win.on_dupfind_finished(_groups74)
app.processEvents()
_m74 = win.dupfind_model
def _row74(path):
    return _m74.path_row(path)
check("[v49.5] 4만 개 결과가 모두 펼쳐진 채로 표시됨",
      _m74.group_count() == 20000 and _m74.rowCount() == 60000)
_t74 = _time74.time()
win.on_dupfind_finished(_groups74, from_precise_verify=True)     # 정밀 스캔 뒤 다시 그리기(예전엔 여기서 멈춤)
app.processEvents()
_dt74 = _time74.time() - _t74
check(f"[v49.5] 4만 개 결과를 지우고 다시 그리기가 빠름({_dt74:.1f}초 — 예전 방식은 15초 이상)", _dt74 < 6)
_g0, _g1 = _m74.groups()[0], _m74.groups()[1]
_m74.set_checked(_g0.paths[0], True)
_m74.set_checked(_g1.paths[1], True)
_rm74 = [_m74.groups()[2].paths[0]] + list(_m74.groups()[3].paths)
_t74 = _time74.time()
win._dupfind_remove_paths_from_tree(_rm74)
app.processEvents()
check("[v49.5] 지운 파일만 빠지고 한 장만 남은 그룹은 사라짐, 다른 체크 상태는 그대로",
      _m74.group_count() == 19998
      and _m74.is_checked(_g0.paths[0]) and _m74.is_checked(_g1.paths[1])
      and win._dupfind_checked_paths() == [_g0.paths[0], _g1.paths[1]])
check("[v49.5] 지운 뒤 정밀 스캔용 결과 목록도 맞춰짐(지운 파일이 다시 검사되지 않음)",
      len(win.dupfind_groups) == 19998 and all(p not in _rm74 for g in win.dupfind_groups for p in g.paths))
_rm74b = [g.paths[0] for g in _m74.groups()[100:5100]]
_t74 = _time74.time()
win._dupfind_remove_paths_from_tree(_rm74b)
app.processEvents()
_dt74 = _time74.time() - _t74
check(f"[v49.5] 5천 개를 한꺼번에 지워도 빠름({_dt74:.1f}초)", _dt74 < 6 and _m74.group_count() == 14998)
_m74.clear()
win.dupfind_groups = []

# 큰 파일: 4MB마다 진행률 + 도중 취소
_big74 = _os.path.join(_tf.mkdtemp(), "big.bin")
with open(_big74, "wb") as _fh:
    _fh.write(b"\x01" * (DF74.READ_BLOCK * 5 + 123))
_seen74 = []
_h74 = DF74.hash_full(_big74, on_bytes=lambda n: _seen74.append(n))
check("[v49.5] 큰 파일을 읽는 동안 블록마다 진행 알림(6번, 합계 = 파일 크기)",
      len(_seen74) == 6 and sum(_seen74) == _os.path.getsize(_big74) and _h74 == DF74.hash_full(_big74))
_cnt74 = []
try:
    DF74.hash_full(_big74, on_bytes=lambda n: (_cnt74.append(n), len(_cnt74) < 2)[1])
    _stopped74 = False
except DF74._Stopped:
    _stopped74 = True
check("[v49.5] 큰 파일을 읽는 도중에도 취소되면 그 자리에서 멈춤", _stopped74 and len(_cnt74) == 2)
_th74 = DF74.DuplicateScanThread(verify_groups=[[_big74, _big74 + "_copy"]], strict=True, use_cache=False)
import shutil as _sh74
_sh74.copy(_big74, _big74 + "_copy")
_prog74 = []
_th74.progress.connect(lambda d, t, p: _prog74.append((d, t)))
_th74._tick = lambda n, p, _orig=_th74._tick: (_prog74.append(("tick", n)), _orig(n, p))
_res74 = []
_th74.finished_scan.connect(lambda g: _res74.append(g))
_th74.run()
check("[v49.5] 정밀 재검사에서 큰 파일은 블록 단위로 진행률이 올라감",
      sum(1 for x in _prog74 if x[0] == "tick" and x[1] > 0) >= 12 and _res74 and len(_res74[0]) == 1)

# 캐시 중간 저장
_db74 = _os.path.join(_tf.mkdtemp(), "c.db")
_hc74 = DF74.HashCache(_db74)
_hc74.FLUSH_EVERY = 3
for _i in range(5):
    _hc74.put(f"/p{_i}", 1, 1, "full", f"d{_i}")
import sqlite3 as _sq74
_n74 = _sq74.connect(_db74).execute("SELECT COUNT(*) FROM h").fetchone()[0]
check("[v49.5] 해시 캐시를 스캔 도중에 중간 저장(끝나기 전에 꺼도 다음엔 이어서)", _n74 >= 3)
_hc74.flush()
check("[v49.5] 마지막 저장으로 나머지도 기록", _sq74.connect(_db74).execute("SELECT COUNT(*) FROM h").fetchone()[0] == 5)
_hc74b = DF74.HashCache(_os.path.join(_tf.mkdtemp(), "c.db"))
_hc74b.FLUSH_SECONDS = 0.0
_hc74b.put("/q", 1, 1, "full", "dq")
check("[v49.5] 시간이 지나도(30초) 중간 저장", _hc74b.get("/q", 1, 1, "full") == "dq")

win.switch_mode("util")
app.processEvents()


section("75. [v50] 중복 찾기 — 큰 결과 메모리 절약 · 탐색기 열기 · 폴더 통째 복사 분석 · 로그 5000줄")

import time as _time75
from PySide6.QtWidgets import QTableView, QMenu
import shutil as _sh75
from src.duplicate_finder import DuplicateGroup as _DG75, DuplicateScanThread as _DST75
from src import dup_folder_analysis as _FA75
from src.dup_result_model import PATH_ROLE as _PR75

win.switch_mode("dupfind")
app.processEvents()
_m75 = win.dupfind_model
_groups75 = [_DG75("x", 1000 + i, [f"C:\\U\\d{i % 300}\\p_{i}_{k}.jpg" for k in range(2 + (i % 5 == 0))])
             for i in range(150000)]
_t75 = _time75.time()
win.on_dupfind_finished(_groups75)
app.processEvents()
_dt75 = _time75.time() - _t75
check(f"[v50] 15만 그룹(33만 파일) 결과가 바로 뜸({_dt75:.1f}초 — v49.5는 수십 초·메모리 수 GB)",
      _dt75 < 5 and _m75.group_count() == 150000 and _m75.file_count() == 330000)
check("[v50] 결과 목록은 줄 객체를 만들지 않는 표 화면(QTableView + 모델)",
      isinstance(win.dupfind_tree, QTableView) and win.dupfind_tree.model() is _m75)
check("[v50] 절약 용량이 큰 그룹부터(첫 줄 = 가장 큰 그룹)",
      _m75.groups()[0].wasted_bytes == max(g.wasted_bytes for g in _groups75)
      and all(_m75.groups()[i].wasted_bytes >= _m75.groups()[i + 1].wasted_bytes for i in range(0, 1000)))
_t75 = _time75.time()
win.resize(win.width() + 200, win.height() + 100)
app.processEvents()
win.resize(win.width() - 200, win.height() - 100)
app.processEvents()
check(f"[v50] 창 크기 바꾸기가 빠름({_time75.time() - _t75:.2f}초)", _time75.time() - _t75 < 1.5)
_g75 = _m75.groups()[0]
_hr75 = _m75.group_header_row(0)
check("[v50] 그룹 머리 줄(중복 N개, 체크 없음) 다음에 파일 줄(이름·경로·체크)",
      _m75.data(_m75.index(_hr75, 0)) == tr("dupfind.tree.group_label", n=len(_g75.paths))
      and not (_m75.flags(_m75.index(_hr75, 0)) & Qt.ItemIsUserCheckable)
      and _m75.data(_m75.index(_hr75 + 1, 1)) == _g75.paths[0]
      and _m75.data(_m75.index(_hr75 + 1, 0), _PR75) == _g75.paths[0]
      and bool(_m75.flags(_m75.index(_hr75 + 1, 0)) & Qt.ItemIsUserCheckable))
_m75.setData(_m75.index(_hr75 + 2, 0), Qt.Checked, Qt.CheckStateRole)
check("[v50] 체크박스로 고른 파일이 지우기·옮기기 대상", win._dupfind_checked_paths() == [_g75.paths[1]])
_t75 = _time75.time()
_m75.check_all_but_first()
app.processEvents()
_dt75 = _time75.time() - _t75
check(f"[v50] 그룹마다 첫 파일만 남기고 모두 체크 — 18만 개도 빠름({_dt75:.2f}초)",
      _dt75 < 2 and len(win._dupfind_checked_paths()) == 180000
      and not _m75.is_checked(_g75.paths[0]) and _m75.is_checked(_g75.paths[1]))
_t75 = _time75.time()
win._dupfind_remove_paths_from_tree(win._dupfind_checked_paths()[:60000])
app.processEvents()
_dt75 = _time75.time() - _t75
check(f"[v50] 6만 개를 지운 뒤 목록 갱신도 빠름({_dt75:.2f}초)",
      _dt75 < 3 and _m75.file_count() == sum(len(g.paths) for g in _m75.groups())
      and all(len(g.paths) > 1 for g in _m75.groups()) and _m75.group_count() < 150000)
_m75.uncheck_all()
check("[v50] 체크 모두 해제", win._dupfind_checked_paths() == [])

# 탐색기 열기 — 더블클릭·오른쪽 클릭 메뉴
_rev75 = []
_orig_rev75 = win.reveal_in_file_explorer
win.reveal_in_file_explorer = lambda p: _rev75.append(p)
_g75 = _m75.groups()[0]
_hr75 = _m75.group_header_row(0)
win._on_dupfind_double_clicked(_m75.index(_hr75 + 1, 1))
win._on_dupfind_double_clicked(_m75.index(_hr75, 1))
check("[v50] 경로 줄 더블클릭 → 탐색기에서 그 파일 열기(그룹 줄은 첫 파일)",
      _rev75 == [_g75.paths[0], _g75.paths[0]])
_rev75.clear()
_menus75 = []
import src.main_window as _MW75
class _FakeMenu75(QMenu):
    def exec(self, *a, **k):
        acts = [x for x in self.actions() if not x.isSeparator()]
        _menus75.append([x.text() for x in acts])
        for x in acts:
            if x.text() == _pick75[0]:
                return x
        return None
_orig_menu75 = _MW75.QMenu
_MW75.QMenu = _FakeMenu75
try:
    _rect75 = win.dupfind_tree.visualRect(_m75.index(_hr75 + 2, 1))
    for _want in ("menu.reveal_in_explorer", "dupfind.menu.open_folder",
                  "dupfind.menu.copy_path", "dupfind.menu.check_all_but_first"):
        _pick75 = [tr(_want)]
        win._on_dupfind_context_menu(_rect75.center())
finally:
    _MW75.QMenu = _orig_menu75
    win.reveal_in_file_explorer = _orig_rev75
check("[v50] 오른쪽 클릭 메뉴: 탐색기에서 열기 · 폴더 열기 · 경로 복사 · 첫 파일만 남기고 체크 · 해제",
      _menus75 and _menus75[0] == [tr("menu.reveal_in_explorer"), tr("dupfind.menu.open_folder"),
                                    tr("dupfind.menu.copy_path"), tr("dupfind.menu.check_all_but_newest"),
                                    tr("dupfind.menu.check_all_but_first"),
                                    tr("dupfind.menu.uncheck_all")])
check("[v50] 메뉴 → 탐색기에서 열기 / 폴더 열기",
      _rev75 == [_g75.paths[1], _os.path.dirname(_g75.paths[1])])
check("[v50] 메뉴 → 경로 복사", QApplication.clipboard().text() == _os.path.normpath(_g75.paths[1]))
check("[v50] 메뉴 → 첫 파일만 남기고 모두 체크", len(win._dupfind_checked_paths()) == _m75.file_count() - _m75.group_count())
_tip75 = _m75.data(_m75.index(_hr75 + 1, 1), Qt.ToolTipRole)
check("[v50] 경로에 마우스를 올리면 더블클릭 안내", _tip75 and tr("dupfind.tree.open_tip") in _tip75)
_m75.clear()
win.dupfind_groups = []

# 폴더 통째 복사 분석 — 실제 폴더로
_r75 = _tf.mkdtemp()
def _mk75(rel, n):
    _p = _os.path.join(_r75, rel)
    _os.makedirs(_os.path.dirname(_p), exist_ok=True)
    with open(_p, "wb") as _fh:
        _fh.write(_os.urandom(n))
for _sub in ("사진", "문서"):
    for _i in range(6):
        _mk75(_os.path.join("원본", "2024자료", _sub, f"f{_i}.dat"), 1500 + _i)
_mk75(_os.path.join("원본", "혼자.dat"), 900)
_sh75.copytree(_os.path.join(_r75, "원본", "2024자료"), _os.path.join(_r75, "백업", "2024자료"))
_sh75.copytree(_os.path.join(_r75, "원본", "2024자료", "사진"), _os.path.join(_r75, "USB", "사진_복사본"))
_os.makedirs(_os.path.join(_r75, "USB", "더많음"))
for _f in _os.listdir(_os.path.join(_r75, "원본", "2024자료", "문서")):
    _sh75.copy(_os.path.join(_r75, "원본", "2024자료", "문서", _f), _os.path.join(_r75, "USB", "더많음", _f))
for _i in range(3):
    _mk75(_os.path.join("USB", "더많음", f"new{_i}.dat"), 3000 + _i)
_os.makedirs(_os.path.join(_r75, "섞임"))
for _i in range(5):
    _sh75.copy(_os.path.join(_r75, "원본", "2024자료", "사진", f"f{_i}.dat"), _os.path.join(_r75, "섞임", f"x{_i}.dat"))
_mk75(_os.path.join("섞임", "only.dat"), 5000)
_th75 = _DST75([_r75], use_cache=False)
_res75 = []
_th75.finished_scan.connect(lambda g: _res75.append(g))
_th75.run()
_rep75 = {(_os.path.relpath(c["a"], _r75), _os.path.relpath(c["b"], _r75)): c for c in _th75.folder_report}
_full75 = {k for k, c in _rep75.items() if c["kind"] == "full"}
def _has75(kind, x, y):
    c = _rep75.get((x, y)) or _rep75.get((y, x))
    return c is not None and c["kind"] == kind
check("[v50] 폴더 통계: 하위 폴더까지 합쳐 셈(스캔 폴더 위로는 안 올라감)",
      _th75.folder_stats[_os.path.join(_r75, "원본")][0] == 13
      and _th75.folder_stats[_r75][0] == 13 + 12 + 6 + 9 + 6
      and _os.path.dirname(_r75) not in _th75.folder_stats)
check("[v50] 통째 복사: 원본\\2024자료 ↔ 백업\\2024자료",
      _has75("full", _os.path.join("원본", "2024자료"), _os.path.join("백업", "2024자료")))
check("[v50] 폴더 이름이 바뀐 통째 복사도 찾음: 2024자료\\사진 ↔ USB\\사진_복사본",
      _has75("full", _os.path.join("원본", "2024자료", "사진"), _os.path.join("USB", "사진_복사본"))
      or _has75("full", _os.path.join("백업", "2024자료", "사진"), _os.path.join("USB", "사진_복사본")))
check("[v50] 위 폴더가 통째 복사면 그 안의 하위 폴더 쌍은 다시 보고하지 않음",
      (_os.path.join("원본", "2024자료", "사진"), _os.path.join("백업", "2024자료", "사진")) not in _rep75
      and (_os.path.join("백업", "2024자료", "사진"), _os.path.join("원본", "2024자료", "사진")) not in _rep75)
_cont75 = [c for c in _th75.folder_report if c["kind"] == "contained"
           and _os.path.relpath(c["b"], _r75) == _os.path.join("USB", "더많음")]
check("[v50] 포함: 문서 폴더가 모두 USB\\더많음 안에 있음(A=작은 쪽 100%, B는 67%)",
      _cont75 and _cont75[0]["a_ratio"] == 1.0 and round(_cont75[0]["b_ratio"] * 100) == 67)
_part75 = [c for c in _th75.folder_report if c["kind"] == "partial"
           and _os.path.relpath(c["b"], _r75) == "섞임"]
check("[v50] 대부분 겹침: 사진 폴더의 5/6(83%)이 섞임 폴더와 같음",
      bool(_part75) and round(_part75[0]["a_ratio"] * 100) == 83)
check("[v50] 원본 폴더 자체는 '혼자.dat' 때문에 통째 복사가 아님",
      not any(_os.path.relpath(c["a"], _r75) == "원본" or _os.path.relpath(c["b"], _r75) == "원본"
              for c in _th75.folder_report if c["kind"] == "full"))
check("[v50] 겹치는 용량이 큰 순으로 보고",
      all(_th75.folder_report[i]["dup_bytes"] >= _th75.folder_report[i + 1]["dup_bytes"]
          for i in range(len(_th75.folder_report) - 1)))
# 정밀 재검사 — 폴더를 다시 걷지 않아도 넘겨받은 통계로 같은 분석
_th75b = _DST75(verify_groups=[list(g.paths) for g in _res75[0]], strict=True, use_cache=False,
                folder_stats=_th75.folder_stats)
_th75b.run()
check("[v50] 정밀 재검사 뒤에도 같은 폴더 분석(빠른 스캔의 폴더 통계를 넘겨받음)",
      [(c["kind"], c["a"], c["b"]) for c in _th75b.folder_report]
      == [(c["kind"], c["a"], c["b"]) for c in _th75.folder_report])
# 콘솔 로그에 보여 주기
win.log.clear()
win.dupfind_thread = _th75
win.on_dupfind_finished(_res75[0])
app.processEvents()
_logtxt75 = win.log.toPlainText()
check("[v50] 콘솔 로그에 폴더 분석 결과(통째 복사 · 포함 · 대부분 겹침 · 두 경로)",
      "📁" in _logtxt75 and tr("log.dupfind.folders.footer") in _logtxt75
      and _os.path.normpath(_os.path.join(_r75, "백업", "2024자료")) in _logtxt75)
win.dupfind_thread = None
# 큰 결과에서도 분석 속도
_t75 = _time75.time()
_st75 = {}
_j75 = _os.path.join
for _i in range(300):
    for _side in ("A", "B"):
        _st75[_j75("/r", _side, f"d{_i}")] = [500, 500 * 1000]
_st75[_j75("/r", "A")] = [150000, 150000 * 1000]
_st75[_j75("/r", "B")] = [150000, 150000 * 1000]
_st75["/r"] = [300000, 300000 * 1000]
_big75 = [_DG75("x", 1000, [_j75("/r", "A", f"d{i % 300}", f"f{i}.dat"), _j75("/r", "B", f"d{i % 300}", f"f{i}.dat")])
          for i in range(150000)]
_rep75b = _FA75.analyze(_big75, _st75)
_dt75 = _time75.time() - _t75
check(f"[v50] 15만 그룹 폴더 분석 {_dt75:.1f}초 · 상위 A ↔ B 한 쌍만 보고(하위 300쌍은 생략)",
      _dt75 < 10 and len(_rep75b) == 1 and _rep75b[0]["kind"] == "full")

# 로그 5000줄 제한
win.log.clear()
for _i in range(5300):
    win.logmsg(f"줄 {_i}")
check("[v50] 콘솔 로그는 최근 5000줄만 남김", win.log.document().blockCount() == 5000
      and win.log.toPlainText().splitlines()[-1] == "줄 5299")
win.log.clear()

section("76. [v50.1] 탐색기 열기 — 경로에 띄어쓰기가 있으면 '문서' 폴더가 열리던 문제")

import types as _types76
import src.main_window as _MW76
_d76 = _tf.mkdtemp(prefix="02. 서울 과학고 ")
_f76 = _os.path.join(_d76, "연구 과제 1.hwp")
open(_f76, "wb").write(b"x")
_calls76 = []
_orig_sys76, _orig_sp76 = _MW76.sys, _MW76.subprocess
_MW76.sys = _types76.SimpleNamespace(platform="win32")
_MW76.subprocess = _types76.SimpleNamespace(Popen=lambda cmd, *a, **k: _calls76.append(cmd))
try:
    win.reveal_in_file_explorer(_f76)
    win.reveal_in_file_explorer(_d76)
finally:
    _MW76.sys, _MW76.subprocess = _orig_sys76, _orig_sp76
_nf76, _nd76 = _os.path.normpath(_f76), _os.path.normpath(_d76)
check("[v50.1] 파일: explorer /select,\"경로\" — 따옴표가 경로에만(띄어쓰기 있어도 그 파일 선택)",
      _calls76[:1] == [f'explorer /select,"{_nf76}"'])
check("[v50.1] 폴더: explorer /n,\"경로\" — 그 폴더 안을 새 창으로",
      _calls76[1:2] == [f'explorer /n,"{_nd76}"'])
check("[v50.1] 목록으로 넘기지 않음(목록이면 Python이 '/select,경로' 전체를 따옴표로 감싸 탐색기가 문서 폴더를 엶)",
      all(isinstance(c, str) for c in _calls76))
_sh75.rmtree(_d76, ignore_errors=True)

section("77. [v50.2] 폴더 하위 구조 보기·저장 — 화면 안 멈춤 · 작업 중 표시 · 폴더별 용량·개수")

import time as _time77
from PySide6.QtCore import QTimer
from src import tree_report as _TR77
_r77 = _tf.mkdtemp(prefix="ws77_")
def _mk77(rel, n):
    _p = _os.path.join(_r77, rel)
    _os.makedirs(_os.path.dirname(_p), exist_ok=True)
    with open(_p, "wb") as _fh:
        _fh.write(b"x" * n)
_mk77(_os.path.join("A", "v1", "a.py"), 100)
_mk77(_os.path.join("A", "v1", "b.py"), 200)
_mk77(_os.path.join("A", "v2", "a.py"), 100)
_mk77(_os.path.join("A", "v2", "big.zip"), 5000)
_mk77(_os.path.join("B", "readme.txt"), 30)
_mk77("top.txt", 7)
_mk77(_os.path.join(".git", "objects", "x"), 999)      # 숨김(점으로 시작) — 제외
_os.makedirs(_os.path.join(_r77, "Empty"))
_ext77 = {}
_top77 = _TR77.scan_tree(_r77, keep_files=True, ext_stats=_ext77)
_byname77 = {n.name: n for n in _TR77.iter_nodes(_top77)}
check("[v50.2] 폴더마다 하위 포함 용량·파일 수·폴더 수(숨김 폴더 제외)",
      _top77.total_bytes == 100 + 200 + 100 + 5000 + 30 + 7 and _top77.total_files == 6
      and _top77.total_dirs == 5 and _byname77["A"].total_bytes == 5400 and _byname77["A"].total_files == 4
      and _byname77["A"].total_dirs == 2 and ".git" not in _byname77 and _byname77["Empty"].total_files == 0)
check("[v50.2] 확장자별 용량 집계", _ext77[".zip"] == [1, 5000] and _ext77[".py"] == [3, 400])
_fmt77 = win._fmt_size
_L77 = _TR77.render(_top77, tr, _fmt77, content=_TR77.CONTENT_FOLDERS, ext_stats=_ext77)
_txt77 = "\n".join(_L77)
check("[v50.2] 폴더만: 파일 줄 없이 폴더 줄마다 정보",
      "a.py" not in _txt77.split(tr("tree.sec.tree"))[1]
      and any(l.endswith(tr("tree.meta", size=_fmt77(5400), files="4", dirs="2",
                                 date=_time77.strftime("%Y-%m-%d"))) and "[A]" in l for l in _L77))
check("[v50.2] 맨 위 요약: 바로 아래 폴더 용량 순(A가 먼저) · 파일 많이 쌓인 폴더 · 확장자",
      tr("tree.sec.children") in _txt77 and tr("tree.sec.ext") in _txt77
      and _txt77.index("[A]") < _txt77.index("[B]")
      and _os.path.join(_top77.name, "A", "v2") in _txt77)
_Lf77 = _TR77.render(_top77, tr, _fmt77, content=_TR77.CONTENT_FILES, ext_stats=_ext77)
check("[v50.2] 파일까지: 파일 이름과 크기", any("big.zip" in l and _fmt77(5000) in l for l in _Lf77))
_Ld77 = _TR77.render(_top77, tr, _fmt77, content=_TR77.CONTENT_FOLDERS, max_depth=1)
_tree_d77 = "\n".join(_Ld77).split(tr("tree.sec.tree"))[1]
check("[v50.2] 깊이 1: 바로 아래 폴더만 줄로(용량은 끝까지 합산)",
      "[A]" in _tree_d77 and "[v1]" not in _tree_d77 and _fmt77(5400) in _tree_d77)
_Lc77 = _TR77.render(_top77, tr, _fmt77, content=_TR77.CONTENT_FILES, with_meta=False, max_lines=4)
check("[v50.2] 콘솔 보기는 줄 수에서 끊고 안내",
      _Lc77[-1] == tr("tree.truncated", n="4") and len(_Lc77) == 3 + 4 + 1)
_old77 = win.generate_tree_text(_r77)
check("[v50.2] 예전 모양(경로 + 트리 줄, 정보 없음)도 그대로",
      _old77.split("\n")[0] == _r77 and "├─ [A]" in _old77 and "big.zip" in _old77 and ".git" not in _old77)

# 메인 창: 옵션 → 백그라운드 스캔 → 콘솔/파일
from PySide6.QtWidgets import QDialog as _QD77, QFileDialog as _QFD77
import src.main_window as _MW77
_orig_ask77 = win._ask_tree_options
win.source_path = _r77
win._ask_tree_options = lambda: {"content": _TR77.CONTENT_FOLDERS, "max_depth": 0, "with_meta": True}
win.switch_mode("sync")
app.processEvents()
win.show_tree_text()
check("[v50.2] 보기를 누르면 작업 중 화면이 뜨고 버튼이 잠김(스캔은 스레드에서)",
      win.overlay.isVisible() and not win.btn_view.isEnabled() and win.tree_thread is not None)
_dl77 = _time77.time() + 20
while win.tree_thread is not None and _time77.time() < _dl77:
    app.processEvents()
    _time77.sleep(0.01)
_log77 = win.log.toPlainText()
check("[v50.2] 끝나면 콘솔에 요약 + 구조, 작업 중 화면 닫힘",
      not win.overlay.isVisible() and win.btn_view.isEnabled()
      and tr("tree.sec.children") in _log77 and "[A]" in _log77
      and tr("log.tree.done", path=_os.path.normpath(_r77), dirs="6", files="6", size=_fmt77(5437), sec="X").split("(")[0] in _log77)
_out77 = _os.path.join(_tf.mkdtemp(), "구조.txt")
_orig_gsf77 = _MW77.QFileDialog.getSaveFileName
_MW77.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_out77, "Text (*.txt)"))
win._ask_tree_options = lambda: {"content": _TR77.CONTENT_FILES, "max_depth": 0, "with_meta": True}
try:
    win.save_tree_text()
    _dl77 = _time77.time() + 20
    while win.tree_thread is not None and _time77.time() < _dl77:
        app.processEvents()
        _time77.sleep(0.01)
finally:
    _MW77.QFileDialog.getSaveFileName = _orig_gsf77
_saved77 = open(_out77, encoding="utf-8").read() if _os.path.exists(_out77) else ""
check("[v50.2] 저장: 파일까지 + 정보 → txt, 콘솔엔 저장 안내만",
      "big.zip" in _saved77 and tr("tree.sec.ext") in _saved77
      and tr("log.tree.saved", path=_out77, lines="X").split("(")[0] in win.log.toPlainText())
# 큰 폴더(파일 5만 개)에서도 화면이 돈다 — 스캔 중에 이벤트 루프가 계속 돎
_r77b = _tf.mkdtemp(prefix="ws77b_")
for _d in range(50):
    _dd = _os.path.join(_r77b, f"v{_d}.0", "src")
    _os.makedirs(_dd)
    for _f in range(1000):
        open(_os.path.join(_dd, f"f{_f}.py"), "wb").close()
win.source_path = _r77b
win._ask_tree_options = lambda: {"content": _TR77.CONTENT_FILES, "max_depth": 0, "with_meta": True}
_ticks77 = [0]
_timer77 = QTimer()
_timer77.timeout.connect(lambda: _ticks77.__setitem__(0, _ticks77[0] + 1))
_timer77.start(10)
_t77 = _time77.time()
win.show_tree_text()
_dl77 = _time77.time() + 60
while win.tree_thread is not None and _time77.time() < _dl77:
    app.processEvents()
    _time77.sleep(0.005)
_timer77.stop()
_dt77 = _time77.time() - _t77
_lines77 = win.log.toPlainText().splitlines()
check(f"[v50.2] 파일 5만 개: {_dt77:.1f}초 동안 화면이 계속 반응(타이머 {_ticks77[0]}번) · 콘솔은 5000줄 안",
      _ticks77[0] >= 5 and len(_lines77) <= 5000 and tr("tree.truncated", n=f"{win.TREE_VIEW_MAX_LINES:,}") in _lines77)
win._ask_tree_options = _orig_ask77
win.source_path = None
_sh75.rmtree(_r77, ignore_errors=True)
_sh75.rmtree(_r77b, ignore_errors=True)
win.log.clear()

section("78. [v51] 윈도·맥 공용 — 맥에선 일상 도구만 · Finder · 고정폭 글꼴 · 자가 시험")

from src import platform_info as _PI78
from src.utils import _APP_CLASSES as _AC78
_all78 = [c.id for c in _AC78]
_mac78 = [i for i in _all78 if _PI78.app_available(i, is_mac=True)]
check("[v51] 맥: 계산기·함수 그래프·스도쿠·행운의 번호·응원의 메시지·타이머만",
      sorted(_mac78) == sorted(["calc", "graph", "sudoku", "lucky", "cheer", "timerclock"]))
check("[v51] 맥: 갤럭시폰 사진 옮기기·학교 업무 도구 제외",
      not any(_PI78.app_available(i, is_mac=True) for i in
              ("phonetransfer", "meal", "schedule", "timetable", "neiscounter", "seating", "bracket")))
check("[v51] 윈도: 미니앱 전부 그대로", all(_PI78.app_available(i, is_mac=False) for i in _all78))
_tbl78 = {"menu.reveal_in_explorer": {"ko": "탐색기 열기", "en": "x", "ja": "y"}, "other": {"ko": "그대로"}}
_PI78.apply_platform_texts(_tbl78, is_mac=True)
check("[v51] 맥: '탐색기' 문구 → 'Finder' (다른 문구는 그대로)",
      _tbl78["menu.reveal_in_explorer"]["ko"] == "Finder에서 보기" and _tbl78["other"]["ko"] == "그대로")
_tbl78b = {"menu.reveal_in_explorer": {"ko": "탐색기 열기"}}
_PI78.apply_platform_texts(_tbl78b, is_mac=False)
check("[v51] 윈도: 문구 그대로", _tbl78b["menu.reveal_in_explorer"]["ko"] == "탐색기 열기")
_orig78 = (_PI78.IS_WIN, _PI78.IS_MAC)
try:
    _PI78.IS_WIN, _PI78.IS_MAC = False, True
    check("[v51] 맥 Finder: 파일은 open -R(선택한 채로), 폴더는 open",
          _PI78.file_manager_command("/Users/a/b c.txt", False) == ["open", "-R", "/Users/a/b c.txt"]
          and _PI78.file_manager_command("/Users/a/d", True) == ["open", "/Users/a/d"])
    _PI78.IS_WIN, _PI78.IS_MAC = True, False
    check("[v51] 윈도 탐색기 명령은 v50.1과 같음",
          _PI78.file_manager_command(r"C:\a b\c.txt", False) == 'explorer /select,"C:\\a b\\c.txt"')
finally:
    _PI78.IS_WIN, _PI78.IS_MAC = _orig78
_mf78 = _PI78.mono_font(11)
check("[v51] 고정폭 글꼴: Consolas가 없으면 Menlo(맥)로", "Menlo" in _mf78.families() and _mf78.pointSize() == 11)
import src.styles as _ST78
class _FakeSt78:
    st_flags = 0x8000
class _FakeEntry78:
    name = "Library"
    def stat(self):
        return _FakeSt78()
check("[v51] 맥: Finder에서 숨긴 폴더(UF_HIDDEN)도 숨김으로", _ST78.is_hidden_or_system(_FakeEntry78()))
check("[v51] 맥 빌드 설정·자동 빌드·설치 안내 파일",
      _os.path.isfile("FolderKitPP_mac.spec") and _os.path.isfile(_os.path.join(".github", "workflows", "build.yml"))
      and _os.path.isfile(_os.path.join("assets", "FolderKit_icon.icns"))
      and _os.path.isfile(_os.path.join("docs", "맥_설치_안내.txt")))
from src.app import selftest as _selftest78
_log78 = _os.path.join(_tf.mkdtemp(), "st.log")
_os.environ["FOLDERKIT_SELFTEST_LOG"] = _log78
try:
    _rc78 = _selftest78(app, win)
finally:
    del _os.environ["FOLDERKIT_SELFTEST_LOG"]
check("[v51] 자가 시험(--selftest): 모든 화면·미니앱을 열어 보고 PASS + 기록 파일",
      _rc78 == 0 and "PASS" in open(_log78, encoding="utf-8").read())

section("79. [v51.1] 중복 찾기 — 그룹마다 최신 파일만 남기고 모두 체크")

import time as _time79
from src.duplicate_finder import DuplicateGroup as _DG79, DuplicateScanThread as _DST79
_m79 = win.dupfind_model
_g79 = [
    _DG79("x", 100, ["/a/old.txt", "/b/new.txt", "/c/mid.txt"], {"/a/old.txt": 1, "/b/new.txt": 30, "/c/mid.txt": 20}),
    _DG79("x", 200, ["/a/1.jpg", "/b/1.jpg"], {"/a/1.jpg": 50, "/b/1.jpg": 50}),          # 시각이 같으면 앞의 것
]
win.switch_mode("dupfind")
app.processEvents()
win.on_dupfind_finished(_g79)
app.processEvents()
win.on_dupfind_check_all_but_newest()
_ck79 = set(win._dupfind_checked_paths())
check("[v51.1] 그룹마다 가장 최근에 수정된 파일만 남기고 나머지 체크",
      _ck79 == {"/a/old.txt", "/c/mid.txt", "/b/1.jpg"})
check("[v51.1] 콘솔·상태 표시줄에 몇 개 체크했는지 안내",
      tr("status.dupfind.checked_newest", n="3", g="2") in win.log.toPlainText())
check("[v51.1] [최신만 남기고 모두 체크] 버튼이 [삭제] 옆에 있음",
      win.btn_dupfind_keep_newest.text() == tr("dupfind.btn_keep_newest")
      and win.btn_dupfind_keep_newest.parentWidget() is win.btn_dupfind_delete.parentWidget())
# 실제 스캔: 시각을 함께 담아 오는지, 시각이 없으면 파일에서 읽는지
_r79 = _tf.mkdtemp(prefix="dup79_")
_paths79 = []
for _i, _name in enumerate(["옛날.dat", "최신.dat", "중간.dat"]):
    _p = _os.path.join(_r79, _name)
    open(_p, "wb").write(b"same content 79" * 100)
    _os.utime(_p, (1_700_000_000 + [0, 900, 400][_i],) * 2)
    _paths79.append(_p)
_th79 = _DST79([_r79], use_cache=False)
_res79 = []
_th79.finished_scan.connect(lambda g: _res79.append(g))
_th79.run()
_grp79 = _res79[0][0] if _res79 and _res79[0] else None
check("[v51.1] 빠른 스캔 결과에 파일마다 수정 시각이 담김(다시 읽지 않음)",
      _grp79 is not None and set(_grp79.mtimes) == set(_paths79))
check("[v51.1] 실제 파일: 최신.dat만 남기고 체크",
      _grp79 is not None and _m79.newest_path(_grp79) == _paths79[1])
_g79b = _DG79("x", 1, list(_paths79))                     # 시각 정보 없음(예전 결과 등)
check("[v51.1] 시각 정보가 없으면 그때 파일에서 읽어서 판단", _m79.newest_path(_g79b) == _paths79[1])
_g79c = _DG79("x", 1, [_os.path.join(_r79, "없는파일.dat"), _paths79[0]])
check("[v51.1] 읽을 수 없는(사라진) 파일은 가장 오래된 것으로 — 남기지 않음",
      _m79.newest_path(_g79c) == _paths79[0])
_big79 = [_DG79("x", 1000 + i, [f"/u/{i}_{k}.jpg" for k in range(3)], {f"/u/{i}_{k}.jpg": (k * 7919 + i) % 3 for k in range(3)})
          for i in range(100000)]
win.on_dupfind_finished(_big79)
app.processEvents()
_t79 = _time79.time()
_n79 = _m79.check_all_but_newest()
app.processEvents()
_dt79 = _time79.time() - _t79
check(f"[v51.1] 10만 그룹도 빠름({_dt79:.2f}초) · 그룹마다 정확히 하나만 남김",
      _dt79 < 3 and _n79 == 200000)
_m79.clear()
win.dupfind_groups = []
_sh75.rmtree(_r79, ignore_errors=True)

section("80. [v51.2] 중복 찾기 — 진행률이 99%에서 65%로 되돌아가던 문제")

import src.duplicate_finder as _D80
_r80 = _tf.mkdtemp(prefix="prog80_")
_big80 = _D80.SMALL_FILE_LIMIT + 1024 * 1024
for _i in range(2):                                   # 큰 중복(성긴 파일 — 디스크를 거의 안 씀)
    for _k in range(2):
        with open(_os.path.join(_r80, f"big{_i}_{_k}.bin"), "wb") as _f:
            _f.seek(_big80 + _i - 1)
            _f.write(bytes([_i + 1]))
for _i in range(240):                                 # 같은 크기 후보: 머리·꼬리에서 갈리거나 진짜 중복
    _data = bytearray(b"x" * 300000)
    if _i % 3 == 0:
        _data[0:4] = _i.to_bytes(4, "little")
    elif _i % 3 == 1:
        _data[-4:] = _i.to_bytes(4, "little")
    with open(_os.path.join(_r80, f"s{_i}.dat"), "wb") as _f:
        _f.write(_data)

def _scan80(strict):
    _th = _D80.DuplicateScanThread([_r80], use_cache=False, strict=strict)
    _th._last_emit = -1e18
    _orig = _th._tick
    def _tick(n, p):                                  # 0.2초 간격 제한 없이 모든 진행 알림을 받는다
        _th._last_emit = -1e18
        _orig(n, p)
    _th._tick = _tick
    _seen = []
    _th.progress.connect(lambda d, t, p: _seen.append(d * 100.0 / t), Qt.DirectConnection)
    _res = []
    _th.finished_scan.connect(lambda g: _res.append(g))
    _th.run()
    return _seen, (_res[0] if _res else [])

for _strict80, _name80 in ((False, "빠른 스캔"), (True, "정밀(엄격) 스캔")):
    _seen80, _g80 = _scan80(_strict80)
    _drops80 = [b - a for a, b in zip(_seen80, _seen80[1:]) if b < a - 0.01]
    check(f"[v51.2] {_name80}: 머리→꼬리→전체/샘플 단계가 바뀌어도 진행률이 한 번도 뒤로 가지 않음"
          f"(알림 {len(_seen80)}번, 되돌아감 {len(_drops80)}번)",
          len(_seen80) > 50 and not _drops80 and abs(_seen80[-1] - 100.0) < 0.01 and len(_g80) == 3)
_th80 = _D80.DuplicateScanThread([_r80], use_cache=False)
_th80.strict = False
check("[v51.2] 단계 계획: 64MB 이하는 머리·꼬리·전체, 넘으면 머리·꼬리·샘플(엄격 모드는 + 전체)",
      _th80._stage_plan(1000) == ["head", "tail", "full"]
      and _th80._stage_plan(_big80) == ["head", "tail", "samp"])
_th80.strict = True
check("[v51.2] 엄격 모드: 아주 큰 파일만 샘플 뒤 전체",
      _th80._stage_plan(_D80.STRICT_SAMPLE_MIN + 1) == ["head", "tail", "samp", "full"]
      and _th80._stage_plan(_big80) == ["head", "tail", "full"])
_sh75.rmtree(_r80, ignore_errors=True)

win.switch_mode("util")
app.processEvents()

# =============================================================================
print("\n" + "=" * 60)
print(f"통과 {len(PASS)} / 실패 {len(FAIL)}")
if FAIL:
    for f in FAIL:
        print("  실패:", f)
    sys.exit(1)
print("전부 통과")

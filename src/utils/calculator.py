# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 #1: 공학용 계산기 [v01]

## 왜 만들었나 (윈도우 기본 계산기와의 차이)
윈도우 계산기는 연산자를 누르는 순간 앞부분이 먼저 계산되어 사라진다.
`12*3+7` 을 넣으려고 `+`를 누르면 화면에는 이미 `36`만 남아 있어서,
**내가 방금 무슨 식을 넣었는지 전체를 볼 수가 없다.**

이 계산기는 그 반대로 동작한다.

1. **수식 전체를 한 줄에 그대로 유지한다.** `=`(또는 Enter)를 누르기
   전까지 아무것도 계산해서 지워버리지 않는다.
2. 입력하는 동안 **미리보기**로 현재 값만 조용히 보여준다(수식은 그대로).
3. 계산이 끝나도 수식이 입력창에 남아 있어 **바로 이어서 고칠 수 있다.**
4. 계산한 수식은 오른쪽 **기록**에 쌓이고, 클릭하면 그 수식이 입력창으로
   다시 들어온다 — 숫자 하나만 바꿔 다시 계산하는 용도.

## 구조 메모
계산 로직은 이 파일에 없다. 전부 utils/expr.py(안전한 ast 기반 평가기)에
있고, 여기서는 화면과 입력 처리만 담당한다 — 계산기 UI 없이도 수식
평가기만 따로 헤드리스 테스트할 수 있게 하기 위한 분리다.
"""
import json

from PySide6.QtCore import Qt, QEvent, QSize
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QSizePolicy
)

from ..i18n import tr
from ..styles import C, button_style, BTN_NEUTRAL_BG, BTN_DESTRUCTIVE_BG   # button_style은 키패드 전용(ui_kit:allow)
from . import ui_kit as UK
from .base import MiniApp
from .expr import CalcError, evaluate, format_number

# =============================================================================
# 키패드 정의 — (표시 문구, 종류, 삽입 문자열, 롤오버 힌트 키)
# =============================================================================
# 종류(kind)는 **내부 키**다. 표시 문구는 숫자·기호·수학 함수 이름이라
# 언어와 무관하므로 그대로 두지만(π, sin, 7 …), 롤오버 힌트는 i18n을 탄다.
#
#   func   : 함수 — "sin(" 처럼 여는 괄호까지 넣고 커서를 안으로.
#            선택된 부분이 있으면 그것을 감싼다(3+4 선택 후 √ → sqrt(3+4)).
#   const  : 상수(π, e, ans)
#   digit  : 숫자·소수점
#   op     : 연산자·괄호·쉼표
#   act:*  : 동작 버튼(지우기·계승·부호·계산)
_KEYPAD = [
    [("sin", "func", "sin(", "util.calc.tip.trig"),
     ("cos", "func", "cos(", "util.calc.tip.trig"),
     ("tan", "func", "tan(", "util.calc.tip.trig"),
     ("(", "op", "(", None),
     (")", "op", ")", None),
     ("⌫", "act:back", None, "util.calc.tip.back")],

    [("sin⁻¹", "func", "asin(", "util.calc.tip.trig"),
     ("cos⁻¹", "func", "acos(", "util.calc.tip.trig"),
     ("tan⁻¹", "func", "atan(", "util.calc.tip.trig"),
     ("π", "const", "π", None),
     ("e", "const", "e", None),
     ("C", "act:clear", None, "util.calc.tip.clear")],

    [("ln", "func", "ln(", "util.calc.tip.ln"),
     ("log", "func", "log(", "util.calc.tip.log"),
     ("√", "func", "√(", "util.calc.tip.sqrt"),
     ("^", "op", "^", "util.calc.tip.pow"),
     ("!", "act:fact", None, "util.calc.tip.fact"),
     ("÷", "op", "÷", None)],

    [("exp", "func", "exp(", "util.calc.tip.exp"),
     ("mod", "op", "%", "util.calc.tip.mod"),
     ("7", "digit", "7", None), ("8", "digit", "8", None), ("9", "digit", "9", None),
     ("×", "op", "×", None)],

    [("|x|", "func", "abs(", "util.calc.tip.abs"),
     ("1/x", "act:inv", None, "util.calc.tip.inv"),
     ("4", "digit", "4", None), ("5", "digit", "5", None), ("6", "digit", "6", None),
     ("−", "op", "−", None)],

    [("log₂", "func", "log2(", "util.calc.tip.log2"),
     ("ans", "const", "ans", "util.calc.tip.ans"),
     ("1", "digit", "1", None), ("2", "digit", "2", None), ("3", "digit", "3", None),
     ("+", "op", "+", None)],

    [(",", "op", ",", "util.calc.tip.comma"),
     ("±", "act:sign", None, "util.calc.tip.sign"),
     ("0", "digit", "0", None), (".", "digit", ".", None),
     ("=", "act:eq", None, "util.calc.tip.eq")],
]

#: 자릿수 콤보 — 저장·비교는 왼쪽의 **내부 키**로만 하고, 화면 문구는
#: 표시 시점에 만든다(언어를 바꿔도 저장된 설정이 깨지지 않게).
DECIMAL_KEYS = ["auto", "2", "4", "6", "10"]

# [버그 수정] 계산기(입력창+결과+키패드) 영역의 고정 폭. 6열 키패드가
# 버튼 하나당 대략 60px 안팎일 때 편하게 누를 수 있는 크기로 잡았다 —
# 이보다 훨씬 커지면 마우스를 더 멀리 움직여야 해서 오히려 불편해진다.
_CALC_FIXED_WIDTH = 420

#: 기록 보관 개수. 너무 크게 잡으면 QSettings 문자열이 비대해진다.
HISTORY_MAX = 60

_SET_HISTORY = "util.calc.history"
_SET_ANGLE = "util.calc.angle"
_SET_DECIMALS = "util.calc.decimals"
_SET_SEEDED = "util.calc.seeded"   # [v06] 샘플 예제를 이미 넣어줬는지(한 번만)

# [v06] 처음 실행할 때 기록 1번에 미리 넣어 두는 샘플 — 사용자가 어떤 종류의
# 연산이 가능한지 한눈에 보게 하기 위해, 이 계산기가 지원하는 연산자를
# 최대한 넣었다. 삼각함수는 일부러 뺐다 — sin(30) 같은 값은 RAD/DEG 모드에
# 따라 결과가 달라져서, "처음 봤을 때 계산이 이상하다"는 오해를 살 수 있다.
# 그 대신 사칙연산·거듭제곱·계승·나머지·제곱근·로그(두 자리 포함)·자연로그·
# 절댓값·역수·괄호를 전부 담아, RAD/DEG 어느 쪽이든 항상 같은 값(39.25)이
# 나오도록 만들었다.
SAMPLE_EXPR = "12×(3+7)÷4-2^3+5!%7+√(81)-log(1000,10)+ln(e)+abs(0-9)+1/(4)"

# 자동 곱셈 보정이 필요한 앞 글자 — 숫자·닫는 괄호·상수 뒤에 함수나 여는
# 괄호가 오면 "4√(5)"가 아니라 "4×√(5)"로 넣어 준다(윈도우 계산기와 동일한
# 인상을 주면서, 계산 단계에서 문법 오류가 나지 않게 한다).
_AUTO_MUL_AFTER = "0123456789.)πe"


# =============================================================================
class CalculatorWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.ans = 0
        self.angle_mode = "rad"      # 내부 키: "rad" / "deg"
        self.decimals = "auto"       # 내부 키: DECIMAL_KEYS 중 하나
        self.history = []            # [{"expr": str, "result": str}] — 최신이 앞
        self._hist_cursor = -1       # ↑/↓ 로 기록을 훑을 때의 위치
        self._result_expr = None     # 큰 결과가 어느 수식의 값인지(흐리게 처리 판단용)
        self._stepping = False       # ↑/↓ 로 기록을 훑는 중인지(아래 설명 참고)

        self._load_settings()
        self._build_ui()
        self._refresh_history_list()
        self._retranslate()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        s = self._settings
        if s is None:
            return
        angle = s.value(_SET_ANGLE, "rad")
        self.angle_mode = angle if angle in ("rad", "deg") else "rad"
        dec = s.value(_SET_DECIMALS, "auto")
        self.decimals = dec if dec in DECIMAL_KEYS else "auto"
        raw = s.value(_SET_HISTORY, "")
        if raw:
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    self.history = [
                        {"expr": str(it.get("expr", "")), "result": str(it.get("result", ""))}
                        for it in items if isinstance(it, dict) and it.get("expr")
                    ][:HISTORY_MAX]
            except (ValueError, TypeError, AttributeError):
                self.history = []   # 저장값이 깨져 있어도 조용히 빈 기록으로 시작

        if not s.value(_SET_SEEDED, False, type=bool):
            # 이 컴퓨터에서 처음 여는 경우에만 샘플을 넣는다. 한번 넣은 뒤에는
            # 사용자가 "지우기"로 기록을 싹 비워도 다시 채워 넣지 않는다 —
            # seeded 플래그를 계속 True로 남겨 두기 때문.
            try:
                sample_value = evaluate(SAMPLE_EXPR, "rad", 0)
                sample_result = format_number(sample_value, "auto", group=False)
                self.history.insert(0, {"expr": SAMPLE_EXPR, "result": sample_result})
            except CalcError:
                pass   # 만에 하나 계산이 안 되더라도 계산기 자체는 정상 동작해야 한다
            s.setValue(_SET_SEEDED, True)

    def _save_settings(self):
        s = self._settings
        if s is None:
            return
        s.setValue(_SET_ANGLE, self.angle_mode)
        s.setValue(_SET_DECIMALS, self.decimals)
        s.setValue(_SET_HISTORY, json.dumps(self.history[:HISTORY_MAX], ensure_ascii=False))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 왼쪽 카드: 계산(툴바: 각도 단위·소수점, 본문: 수식·결과·키패드, 하단: 결과 복사) ----
        # 키패드 영역은 창을 넓혀도 버튼이 커지지 않도록 **고정 폭**을 가지고,
        # 남는 공간은 전부 오른쪽 기록 카드가 가져간다.
        self.card_calc = UK.Card()
        self.card_calc.setFixedWidth(_CALC_FIXED_WIDTH)
        self.btn_angle = UK.toggle_button()
        self.btn_angle.clicked.connect(self._toggle_angle)
        self.card_calc.add_tool(self.btn_angle)
        self.lbl_dec = UK.body_label()
        self.card_calc.add_tool(self.lbl_dec)
        self.combo_dec = QComboBox()
        self.combo_dec.setMinimumWidth(96)
        for key in DECIMAL_KEYS:
            self.combo_dec.addItem(self._decimal_label(key), key)
        self.combo_dec.setCurrentIndex(DECIMAL_KEYS.index(self.decimals))
        self.combo_dec.currentIndexChanged.connect(self._on_decimals_changed)
        self.card_calc.add_tool(self.combo_dec)

        self.expr = QLineEdit()
        self.expr.setFixedHeight(44)
        self.expr.setFont(QFont("Consolas", 15))
        self.expr.setStyleSheet(
            f"QLineEdit{{background-color:#ffffff;border:1px solid {UK.CANVAS_BORDER};"
            f"border-radius:4px;padding:0 10px;color:{C.WINDOW_FG};}}"
            f"QLineEdit:focus{{border:1px solid {C.UTIL_MAIN};}}")
        self.expr.returnPressed.connect(self.calculate)
        self.expr.textChanged.connect(self._on_text_changed)
        self.expr.installEventFilter(self)
        self.card_calc.add_body(self.expr)

        # 결과 줄 — 왼쪽에 상태(미리보기/오류), 오른쪽에 큰 결과
        self.preview = UK.hint_label()
        self.preview.setWordWrap(False)
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result = QLabel("0")
        self.result.setFixedHeight(38)   # 미리보기 유무로 줄 높이가 들썩이지 않게 고정
        self.result.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.result.setFont(QFont("Consolas", 22, QFont.Bold))
        self.result.setStyleSheet(f"color:{C.UTIL_MAIN};background:transparent;")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        result_row = QHBoxLayout()
        result_row.setSpacing(8)
        result_row.addWidget(self.preview, 1)
        result_row.addWidget(self.result, 2)
        self.card_calc.add_body(result_row)

        # 키패드 — 격자형 키는 규격 예외(ui_kit:allow), v50에서 정한 카테고리 색 규칙을 유지
        pad = QGridLayout()
        pad.setSpacing(5)
        self.card_calc.add_body(pad, 1)
        self._pad_buttons = []
        for r, row in enumerate(_KEYPAD):
            for c, (label, kind, payload, tip_key) in enumerate(row):
                btn = QPushButton(label)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setMinimumHeight(34)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.setStyleSheet(self._key_style(kind))
                btn.setFocusPolicy(Qt.NoFocus)   # 스페이스바가 버튼을 누르지 않도록
                btn.clicked.connect(
                    lambda _=False, k=kind, p=payload: self._on_key(k, p))
                span = 2 if kind == "act:eq" else 1
                pad.addWidget(btn, r, c, 1, span)
                self._pad_buttons.append((btn, tip_key))
        for c in range(6):
            pad.setColumnStretch(c, 1)

        self.btn_copy_result = self.card_calc.add_footer(UK.secondary_button())
        self.btn_copy_result.clicked.connect(self._copy_result)

        # ---- 오른쪽 카드: 기록(가변 — 남는 공간을 전부 차지, 하단: 지우기) ----
        self.card_hist = UK.Card()
        self.lbl_history = self.card_hist.title_label
        self.hist_list = QListWidget()
        self.hist_list.setMinimumWidth(200)
        self.hist_list.setStyleSheet(
            f"QListWidget{{background-color:#ffffff;border:1px solid {UK.CANVAS_BORDER};"
            f"border-radius:4px;}}"
            f"QListWidget::item{{padding:5px 6px;border-bottom:1px solid {C.UTIL_BG};}}"
            f"QListWidget::item:selected{{background-color:{C.UTIL_MAIN};color:#ffffff;}}")
        self.hist_list.itemClicked.connect(self._on_history_clicked)
        self.hist_list.itemDoubleClicked.connect(self._on_history_double_clicked)
        self.hist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hist_list.customContextMenuRequested.connect(self._history_menu)
        self.card_hist.add_body(self.hist_list, 1)
        self.lbl_hist_hint = UK.hint_label()
        self.card_hist.add_body(self.lbl_hist_hint)
        self.btn_clear_hist = self.card_hist.add_footer(UK.danger_button())
        self.btn_clear_hist.clicked.connect(self._clear_history)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        root.addWidget(self.card_calc, 0)
        root.addWidget(self.card_hist, 1)

    def _key_style(self, kind):
        """버튼 카테고리 규칙(v50에서 정한 것)을 그대로 따른다:
        주 실행(=)은 모드 강조색, 지우기류는 중립 슬레이트, 나머지는
        숫자(흰색)/함수(모드 톤 옅은 배경)/연산자(무채색)로 나눈다."""
        if kind == "act:eq":
            return button_style(C.UTIL_MAIN, font_size=16, radius=5)   # ui_kit:allow
        if kind in ("act:back", "act:clear"):
            return button_style(BTN_NEUTRAL_BG, font_size=13, radius=5)   # ui_kit:allow
        if kind == "digit":
            return button_style("#ffffff", fg=C.WINDOW_FG, bold=True, font_size=15,   # ui_kit:allow
                                radius=5,
                                extra="QPushButton:hover{background-color:#eef2f6;}")
        if kind in ("func", "const"):
            return button_style("#fbeef3", fg="#8d1c4a", bold=False, font_size=12,   # ui_kit:allow
                                radius=5,
                                extra="QPushButton:hover{background-color:#f6dde8;}")
        # op / act:fact / act:sign / act:inv
        return button_style("#eceff1", fg=C.WINDOW_FG, bold=True, font_size=14,   # ui_kit:allow
                            radius=5,
                            extra="QPushButton:hover{background-color:#dde3e7;}")

    # -------------------------------------------------------------- 입력 처리
    def eventFilter(self, obj, event):
        """입력창에서 ↑/↓ 로 기록을 훑는다(셸 명령 기록과 같은 감각)."""
        if obj is self.expr and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self._step_history(+1)
                return True
            if event.key() == Qt.Key_Down:
                self._step_history(-1)
                return True
            if event.key() == Qt.Key_Escape:
                self.expr.clear()
                return True
        return super().eventFilter(obj, event)

    def _step_history(self, delta):
        """↑/↓ 로 기록을 훑는다.

        여기서 setText()를 하면 textChanged가 발생하고, 그 핸들러가 "사용자가
        직접 고쳤다"고 판단해 훑고 있던 위치(_hist_cursor)를 -1로 되돌려
        버린다 — 그러면 ↑를 아무리 눌러도 가장 최근 수식에서 제자리걸음을
        한다. 훑는 동안에는 그 초기화를 잠시 막는다."""
        if not self.history:
            return
        self._hist_cursor = max(-1, min(len(self.history) - 1, self._hist_cursor + delta))
        self._stepping = True
        try:
            if self._hist_cursor < 0:
                self.expr.clear()
            else:
                self.expr.setText(self.history[self._hist_cursor]["expr"])
                self.expr.setCursorPosition(len(self.expr.text()))
        finally:
            self._stepping = False

    def _on_key(self, kind, payload):
        if kind == "act:back":
            self.expr.backspace()
        elif kind == "act:clear":
            self.expr.clear()
            self.result.setText("0")
            self._result_expr = None
            self._update_result_freshness()
        elif kind == "act:eq":
            self.calculate()
        elif kind == "act:sign":
            self._toggle_sign()
        elif kind == "act:fact":
            self._insert("!", auto_mul=False)
        elif kind == "act:inv":
            self._insert("1/(", auto_mul=True, wrap=True)
        elif kind == "func":
            self._insert(payload, auto_mul=True, wrap=True)
        elif kind == "const":
            self._insert(payload, auto_mul=True)
        elif payload == "(":
            self._insert(payload, auto_mul=True)
        else:
            self._insert(payload, auto_mul=False)
        self.expr.setFocus()

    def _insert(self, text, auto_mul=False, wrap=False):
        """키패드 입력을 커서 위치에 끼워 넣는다.

        auto_mul: 숫자·닫는 괄호·상수 바로 뒤에 함수/여는 괄호가 오면
                  곱셈 기호를 자동으로 하나 넣는다(4√(5) → 4×√(5)).
        wrap:     선택된 부분이 있으면 그것을 함수로 감싼다
                  (3+4 를 드래그한 뒤 √ → √(3+4) ).
        """
        edit = self.expr
        full = edit.text()

        if wrap and edit.hasSelectedText():
            start = edit.selectionStart()
            sel = edit.selectedText()
            new = full[:start] + text + sel + ")" + full[start + len(sel):]
            edit.setText(new)
            edit.setCursorPosition(start + len(text) + len(sel) + 1)
            return

        pos = edit.selectionStart() if edit.hasSelectedText() else edit.cursorPosition()
        if auto_mul and not edit.hasSelectedText() and pos > 0 \
                and full[pos - 1] in _AUTO_MUL_AFTER:
            edit.insert("×" + text)
        else:
            edit.insert(text)

    def _toggle_sign(self):
        """커서 바로 앞 숫자의 부호를 뒤집는다. 앞에 숫자가 없으면 빼기 기호만
        넣는다 — 윈도우 계산기의 ± 와 같은 감각을 수식 편집 방식으로 옮긴 것."""
        text = self.expr.text()
        pos = self.expr.cursorPosition()
        j = pos
        while j > 0 and (text[j - 1].isdigit() or text[j - 1] == "."):
            j -= 1
        if j == pos:                      # 숫자 위가 아니면 그냥 빼기 기호
            self._insert("−")
            return
        if j > 0 and text[j - 1] in "-−":
            k = j - 1
            if k == 0 or text[k - 1] in "(+-−×÷*/^,%":
                self.expr.setText(text[:k] + text[j:])     # 이미 음수 → 부호 제거
                self.expr.setCursorPosition(max(0, pos - 1))
                return
        self.expr.setText(text[:j] + "−" + text[j:])
        self.expr.setCursorPosition(pos + 1)

    # ---------------------------------------------------------------- 계산
    def _on_text_changed(self, _text):
        """입력하는 동안의 **미리보기**. 수식은 절대 건드리지 않고 값만 보여준다.
        오류일 때는 아무 말도 하지 않는다 — 아직 입력이 끝나지 않은 상태에서
        빨간 경고가 계속 깜빡이면 오히려 방해되기 때문(오류 문구는 = 를 눌렀을
        때만 표시한다)."""
        if not self._stepping:
            self._hist_cursor = -1
        text = self.expr.text().strip()
        if not text:
            self.preview.setText("")
            self._update_result_freshness()
            return
        try:
            value = evaluate(text, self.angle_mode, self.ans)
        except CalcError:
            self.preview.setText("")
            self._update_result_freshness()
            return
        self.preview.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        self.preview.setText("= " + format_number(value, self.decimals))
        self._update_result_freshness()

    def _update_result_freshness(self):
        """큰 결과 숫자는 "마지막으로 = 를 누른 그 수식"의 값이다. 그 뒤에
        수식을 고치기 시작하면 화면의 수식과 큰 숫자가 서로 다른 것을
        가리키게 되므로, 그럴 때는 결과를 흐리게 만들어 "이건 아직 옛날
        값"이라는 것을 눈으로 알 수 있게 한다."""
        stale = (self._result_expr is not None
                 and self.expr.text().strip() != self._result_expr)
        color = "#b9bcc2" if stale else C.UTIL_MAIN
        self.result.setStyleSheet(f"color:{color};background:transparent;")

    def calculate(self):
        text = self.expr.text().strip()
        if not text:
            return
        try:
            value = evaluate(text, self.angle_mode, self.ans)
        except CalcError as e:
            self.preview.setStyleSheet(
                f"color:{BTN_DESTRUCTIVE_BG};font-size:12px;font-weight:bold;"
                "background:transparent;")
            self.preview.setText(tr(e.key, **e.params))
            if self.host:
                self.host.log(tr("util.calc.log.failed", a0=text, a1=tr(e.key, **e.params)))
            return

        self.ans = value
        self._result_expr = text
        shown = format_number(value, self.decimals)
        raw = format_number(value, self.decimals, group=False)
        self.result.setText(shown)
        self._update_result_freshness()
        self.preview.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        self.preview.setText(tr("util.calc.preview.done"))
        self._push_history(text, raw)
        if self.host:
            self.host.log(tr("util.calc.log.done", a0=text, a1=raw))
            self.host.status(tr("util.calc.status.done", a0=raw))
        # 수식은 지우지 않는다 — 이어서 고쳐 다시 계산하는 것이 이 계산기의 핵심.
        self.expr.setFocus()
        self.expr.setCursorPosition(len(self.expr.text()))

    # ---------------------------------------------------------------- 기록
    def _push_history(self, expr_text, result_text):
        if self.history and self.history[0]["expr"] == expr_text \
                and self.history[0]["result"] == result_text:
            return                                  # 같은 수식 연속 계산은 한 줄만
        self.history.insert(0, {"expr": expr_text, "result": result_text})
        del self.history[HISTORY_MAX:]
        self._refresh_history_list()
        self._save_settings()

    def _refresh_history_list(self):
        self.hist_list.clear()
        if not self.history:
            item = QListWidgetItem(tr("util.calc.history.empty"))
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(Qt.gray)
            self.hist_list.addItem(item)
            return
        # 리스트의 실제 폭을 기준으로 라벨 최대 폭을 미리 정해 준다 — 그냥
        # setWordWrap(True)만 걸면, 줄바꿈 폭을 정하기 전에 sizeHint()를
        # 먼저 물어보는 순서라 한 줄로 길게 삐져나온 뒤에야 줄바꿈된다
        # (가로 스크롤바가 생기는 원인). 복사 버튼 폭(22)+여백을 뺀 값을
        # 라벨의 최대 폭으로 미리 못박아 둔다.
        available = max(self.hist_list.viewport().width() - 40, 100)
        for entry in self.history:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry)
            item.setToolTip(tr("util.calc.history.item.tip"))
            self.hist_list.addItem(item)
            row = self._build_history_row(entry, available)
            item.setSizeHint(row.sizeHint())
            self.hist_list.setItemWidget(item, row)

    def _build_history_row(self, entry, label_width):
        """[v06] 기록 한 줄 = 수식/결과 라벨 + 원클릭 복사 버튼.
        오른쪽 클릭 메뉴로도 복사할 수 있지만(수식 복사/결과 복사), 눈에
        바로 보이는 복사 버튼을 하나 더 두면 쓰기 편하다는 요청이 있었다."""
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 4, 4, 4)
        lay.setSpacing(4)

        lbl = QLabel(f"{entry['expr']}\n= {entry['result']}")
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(label_width)
        lbl.setStyleSheet("background:transparent;")
        lay.addWidget(lbl, 1)

        btn = QPushButton("⧉")
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tr("util.calc.history.copy_expr.tip"))
        btn.setStyleSheet(
            f"QPushButton{{background-color:transparent;color:#8a8f98;"
            f"border:1px solid {C.BORDER};border-radius:4px;font-size:12px;}}"
            f"QPushButton:hover{{background-color:{C.UTIL_BG};color:{C.UTIL_MAIN};"
            f"border-color:{C.UTIL_MAIN};}}")
        btn.clicked.connect(lambda: self._quick_copy_expr(entry))
        lay.addWidget(btn, 0, Qt.AlignTop)
        return row

    def _quick_copy_expr(self, entry):
        QGuiApplication.clipboard().setText(entry["expr"])
        if self.host:
            self.host.status(tr("util.calc.status.copied", a0=entry["expr"]))

    def _entry_of(self, item):
        return item.data(Qt.UserRole) if item is not None else None

    def _on_history_clicked(self, item):
        """한 번 클릭 = 수식을 입력창으로 되불러오기(편집용). 계산은 하지 않는다."""
        entry = self._entry_of(item)
        if not entry:
            return
        self.expr.setText(entry["expr"])
        self.expr.setFocus()
        self.expr.setCursorPosition(len(self.expr.text()))

    def _on_history_double_clicked(self, item):
        """두 번 클릭 = 되불러온 뒤 그대로 다시 계산."""
        entry = self._entry_of(item)
        if not entry:
            return
        self.expr.setText(entry["expr"])
        self.calculate()

    def _history_menu(self, pos):
        item = self.hist_list.itemAt(pos)
        entry = self._entry_of(item)
        if not entry:
            return
        menu = QMenu(self)
        act_expr = menu.addAction(tr("util.calc.menu.copy_expr"))
        act_result = menu.addAction(tr("util.calc.menu.copy_result"))
        menu.addSeparator()
        act_del = menu.addAction(tr("util.calc.menu.delete"))
        chosen = menu.exec(self.hist_list.mapToGlobal(pos))
        if chosen is act_expr:
            QGuiApplication.clipboard().setText(entry["expr"])
        elif chosen is act_result:
            QGuiApplication.clipboard().setText(entry["result"])
        elif chosen is act_del:
            self.history = [h for h in self.history if h is not entry]
            self._refresh_history_list()
            self._save_settings()

    def _clear_history(self):
        if not self.history:
            return
        ok = QMessageBox.question(
            self, tr("util.calc.msg.clear_title"), tr("util.calc.msg.clear_body"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ok != QMessageBox.Yes:
            return
        self.history = []
        self._refresh_history_list()
        self._save_settings()

    # ---------------------------------------------------------------- 옵션
    def _toggle_angle(self):
        self.angle_mode = "deg" if self.angle_mode == "rad" else "rad"
        self._update_angle_button()
        self._save_settings()
        self._on_text_changed(self.expr.text())     # 미리보기를 새 모드로 다시 계산

    def _update_angle_button(self):
        self.btn_angle.setText(tr("util.calc.deg") if self.angle_mode == "deg"
                               else tr("util.calc.rad"))
        self.btn_angle.setToolTip(tr("util.calc.angle.tip"))
        self.btn_angle.setChecked(self.angle_mode == "deg")

    def _on_decimals_changed(self, index):
        # 저장은 항상 itemData(내부 키) 기준 — 표시 문구로 저장하면 언어를
        # 바꿨을 때 저장값과 화면이 어긋난다.
        self.decimals = self.combo_dec.itemData(index) or "auto"
        self._save_settings()
        self._on_text_changed(self.expr.text())
        if self.result.text() not in ("", "0"):
            try:
                self.result.setText(format_number(self.ans, self.decimals))
            except (TypeError, ValueError):
                pass

    def _decimal_label(self, key):
        return tr("util.calc.decimals.auto") if key == "auto" \
            else tr("util.calc.decimals.fixed", n=key)

    def _copy_result(self):
        text = format_number(self.ans, self.decimals, group=False)
        QGuiApplication.clipboard().setText(text)
        if self.host:
            self.host.status(tr("util.calc.status.copied", a0=text))

    # ------------------------------------------------------------- 다국어
    def _retranslate(self):
        self.expr.setPlaceholderText(tr("util.calc.expr.placeholder"))
        self.expr.setToolTip(tr("util.calc.expr.tip"))
        self.lbl_dec.setText(tr("util.calc.decimals.label"))
        self.btn_copy_result.setText(tr("util.calc.btn.copy_result"))
        self.btn_copy_result.setToolTip(tr("util.calc.btn.copy_result.tip"))
        self.lbl_history.setText(tr("util.calc.history.title"))
        self.card_calc.set_title(tr("util.calc.title"))
        self.btn_clear_hist.setText(tr("util.calc.btn.clear_history"))
        self.btn_clear_hist.setToolTip(tr("util.calc.btn.clear_history.tip"))
        self.lbl_hist_hint.setText(tr("util.calc.history.hint"))
        self._update_angle_button()
        for i, key in enumerate(DECIMAL_KEYS):
            self.combo_dec.setItemText(i, self._decimal_label(key))
        for btn, tip_key in self._pad_buttons:
            if tip_key:
                btn.setToolTip(tr(tip_key))
        self._refresh_history_list()

    retranslate = _retranslate


# =============================================================================
class CalculatorApp(MiniApp):
    id = "calc"
    icon = "calc"
    category = "math"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = CalculatorWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    # 계산기는 저장할 문서가 없으므로 has_unsaved()는 기본값(False) 그대로.


# =============================================================================
# 번역 조각 — 이 도구가 자기 문구를 직접 들고 다닌다. i18n.py(2000줄)에
# 도구 문구까지 몰아넣으면 도구가 늘수록 그 파일만 계속 비대해진다.
# =============================================================================
TRANSLATIONS = {
    "util.calc.title": {
        "ko": "공학용 계산기", "en": "Scientific Calculator", "ja": "関数電卓"},
    "util.calc.desc": {
        "ko": "수식 전체를 보면서 한 번에 계산하고, 계산한 식을 다시 불러와 고칠 수 있습니다.",
        "en": "See the whole expression, calculate it at once, and reuse past expressions.",
        "ja": "数式全体を見ながら一度に計算し、過去の式を呼び出して編集できます。"},

    "util.calc.expr.placeholder": {
        "ko": "수식을 입력하세요 —  예) 12×(3+7)÷4",
        "en": "Type an expression — e.g. 12×(3+7)÷4",
        "ja": "数式を入力してください — 例) 12×(3+7)÷4"},
    "util.calc.expr.tip": {
        "ko": "Enter = 계산 · ↑/↓ = 이전 수식 불러오기 · Esc = 지우기.\n"
              "키보드로 * / - 를 그대로 입력해도 됩니다.",
        "en": "Enter = calculate · ↑/↓ = recall past expressions · Esc = clear.\n"
              "You can also type * / - directly on the keyboard.",
        "ja": "Enter = 計算 · ↑/↓ = 過去の式を呼び出す · Esc = 消去。\n"
              "キーボードで * / - をそのまま入力しても構いません。"},
    "util.calc.preview.done": {
        "ko": "계산 완료 — 수식을 고쳐서 다시 계산할 수 있습니다.",
        "en": "Done — you can edit the expression and calculate again.",
        "ja": "計算完了 — 数式を直して再計算できます。"},

    "util.calc.rad": {"ko": "RAD", "en": "RAD", "ja": "RAD"},
    "util.calc.deg": {"ko": "DEG", "en": "DEG", "ja": "DEG"},
    "util.calc.angle.tip": {
        "ko": "삼각함수의 각도 단위를 바꿉니다. DEG=도(°), RAD=라디안.",
        "en": "Switches the angle unit for trigonometric functions. DEG = degrees, RAD = radians.",
        "ja": "三角関数の角度単位を切り替えます。DEG=度(°)、RAD=ラジアン。"},

    "util.calc.decimals.label": {
        "ko": "소수점", "en": "Decimals", "ja": "小数点"},
    "util.calc.decimals.auto": {
        "ko": "자동", "en": "Auto", "ja": "自動"},
    "util.calc.decimals.fixed": {
        "ko": "{n}자리", "en": "{n} places", "ja": "{n}桁"},

    "util.calc.btn.copy_result": {
        "ko": "결과 복사", "en": "Copy result", "ja": "結果をコピー"},
    "util.calc.btn.copy_result.tip": {
        "ko": "계산 결과를 클립보드에 복사합니다(천 단위 쉼표 없이).",
        "en": "Copies the result to the clipboard (without thousand separators).",
        "ja": "計算結果をクリップボードにコピーします（桁区切りなし）。"},

    "util.calc.history.title": {"ko": "기록", "en": "History", "ja": "履歴"},
    "util.calc.history.empty": {
        "ko": "아직 계산한 수식이 없습니다.",
        "en": "No calculations yet.",
        "ja": "まだ計算がありません。"},
    "util.calc.history.hint": {
        "ko": "클릭하면 그 수식을 다시 불러옵니다. 두 번 클릭하면 바로 계산하고, "
              "오른쪽 버튼으로 복사·삭제할 수 있습니다.",
        "en": "Click to load an expression back for editing. Double-click to calculate it, "
              "or right-click to copy or delete.",
        "ja": "クリックすると数式を呼び出します。ダブルクリックで即計算、"
              "右クリックでコピー・削除ができます。"},
    "util.calc.history.item.tip": {
        "ko": "클릭: 수식 불러오기 · 두 번 클릭: 바로 계산",
        "en": "Click: load expression · Double-click: calculate now",
        "ja": "クリック: 数式を呼び出す · ダブルクリック: すぐ計算"},
    "util.calc.btn.clear_history": {
        "ko": "지우기", "en": "Clear", "ja": "消去"},
    "util.calc.btn.clear_history.tip": {
        "ko": "저장된 계산 기록을 모두 지웁니다.",
        "en": "Deletes all saved calculation history.",
        "ja": "保存された計算履歴をすべて削除します。"},
    "util.calc.menu.copy_expr": {
        "ko": "수식 복사", "en": "Copy expression", "ja": "数式をコピー"},
    "util.calc.menu.copy_result": {
        "ko": "결과 복사", "en": "Copy result", "ja": "結果をコピー"},
    "util.calc.menu.delete": {
        "ko": "이 항목 삭제", "en": "Delete this entry", "ja": "この項目を削除"},
    "util.calc.msg.clear_title": {
        "ko": "계산 기록 지우기", "en": "Clear history", "ja": "計算履歴の消去"},
    "util.calc.msg.clear_body": {
        "ko": "저장된 계산 기록을 모두 지울까요?",
        "en": "Delete all saved calculation history?",
        "ja": "保存された計算履歴をすべて削除しますか？"},

    # ---- 키패드 롤오버 힌트 ----
    "util.calc.tip.trig": {
        "ko": "삼각함수입니다. 위 DEG/RAD 버튼으로 각도 단위를 정합니다.",
        "en": "Trigonometric function. Set the angle unit with the DEG/RAD button above.",
        "ja": "三角関数です。上の DEG/RAD ボタンで角度単位を決めます。"},
    "util.calc.tip.ln": {
        "ko": "자연로그(밑이 e)입니다.", "en": "Natural logarithm (base e).",
        "ja": "自然対数（底 e）です。"},
    "util.calc.tip.log": {
        "ko": "상용로그(밑이 10). log(값, 밑) 처럼 밑을 직접 적을 수도 있습니다.",
        "en": "Common logarithm (base 10). You can also write log(value, base).",
        "ja": "常用対数（底 10）。log(値, 底) のように底を指定もできます。"},
    "util.calc.tip.log2": {
        "ko": "밑이 2인 로그입니다.", "en": "Logarithm base 2.", "ja": "底 2 の対数です。"},
    "util.calc.tip.sqrt": {
        "ko": "제곱근입니다. 수식을 드래그해 선택한 뒤 누르면 그 부분을 감쌉니다.",
        "en": "Square root. Select part of the expression first to wrap it.",
        "ja": "平方根です。数式を選択してから押すとその部分を囲みます。"},
    "util.calc.tip.pow": {
        "ko": "거듭제곱입니다. 2^10 = 1024",
        "en": "Power. 2^10 = 1024", "ja": "べき乗です。2^10 = 1024"},
    "util.calc.tip.fact": {
        "ko": "계승입니다. 5! = 120 (0 이상의 정수만, 최대 1000)",
        "en": "Factorial. 5! = 120 (non-negative integers up to 1000)",
        "ja": "階乗です。5! = 120（0 以上の整数、最大 1000）"},
    "util.calc.tip.mod": {
        "ko": "나머지입니다. 7 % 3 = 1",
        "en": "Remainder (modulo). 7 % 3 = 1", "ja": "剰余です。7 % 3 = 1"},
    "util.calc.tip.exp": {
        "ko": "e의 거듭제곱입니다. exp(1) = 2.718…",
        "en": "e raised to a power. exp(1) = 2.718…",
        "ja": "e のべき乗です。exp(1) = 2.718…"},
    "util.calc.tip.abs": {
        "ko": "절댓값입니다.", "en": "Absolute value.", "ja": "絶対値です。"},
    "util.calc.tip.inv": {
        "ko": "역수입니다 — 1/( 을 넣습니다.",
        "en": "Reciprocal — inserts 1/( .", "ja": "逆数です — 1/( を挿入します。"},
    "util.calc.tip.ans": {
        "ko": "바로 앞 계산 결과를 수식에 넣습니다.",
        "en": "Inserts the previous result into the expression.",
        "ja": "直前の計算結果を数式に入れます。"},
    "util.calc.tip.comma": {
        "ko": "인수 구분용 쉼표입니다. 예) log(8, 2)",
        "en": "Comma separating arguments. e.g. log(8, 2)",
        "ja": "引数を区切るカンマです。例) log(8, 2)"},
    "util.calc.tip.sign": {
        "ko": "커서 앞 숫자의 부호를 바꿉니다.",
        "en": "Flips the sign of the number before the cursor.",
        "ja": "カーソル手前の数の符号を変えます。"},
    "util.calc.tip.back": {
        "ko": "한 글자 지웁니다.", "en": "Deletes one character.",
        "ja": "1 文字消します。"},
    "util.calc.tip.clear": {
        "ko": "수식을 전부 지웁니다.", "en": "Clears the whole expression.",
        "ja": "数式をすべて消します。"},
    "util.calc.tip.eq": {
        "ko": "수식 전체를 계산합니다(Enter 키와 같습니다). 수식은 지워지지 않습니다.",
        "en": "Calculates the whole expression (same as Enter). The expression is kept.",
        "ja": "数式全体を計算します（Enter と同じ）。数式は消えません。"},

    # ---- 로그·상태바 ----
    "util.calc.log.done": {
        "ko": "[계산기] {a0} = {a1}", "en": "[Calculator] {a0} = {a1}",
        "ja": "[電卓] {a0} = {a1}"},
    "util.calc.log.failed": {
        "ko": "[계산기] 계산 실패: {a0} — {a1}",
        "en": "[Calculator] Failed: {a0} — {a1}",
        "ja": "[電卓] 計算失敗: {a0} — {a1}"},
    "util.calc.status.done": {
        "ko": "계산 결과: {a0}", "en": "Result: {a0}", "ja": "計算結果: {a0}"},
    "util.calc.status.copied": {
        "ko": "복사했습니다: {a0}", "en": "Copied: {a0}", "ja": "コピーしました: {a0}"},

    # ---- 오류 문구(expr.py의 CalcError.key와 1:1로 대응) ----
    "util.calc.err.empty": {
        "ko": "수식이 비어 있습니다.", "en": "The expression is empty.",
        "ja": "数式が空です。"},
    "util.calc.err.syntax": {
        "ko": "수식을 이해할 수 없습니다 — 연산자나 괄호를 확인해 주세요.",
        "en": "Cannot read this expression — check the operators and parentheses.",
        "ja": "数式を解釈できません — 演算子や括弧を確認してください。"},
    "util.calc.err.paren": {
        "ko": "괄호의 짝이 맞지 않습니다.", "en": "Parentheses do not match.",
        "ja": "括弧の対応が取れていません。"},
    "util.calc.err.div_zero": {
        "ko": "0으로 나눌 수 없습니다.", "en": "Cannot divide by zero.",
        "ja": "0 で割ることはできません。"},
    "util.calc.err.domain": {
        "ko": "이 함수에 넣을 수 없는 값입니다(정의역을 벗어났습니다).",
        "en": "That value is outside this function's domain.",
        "ja": "この関数に使えない値です（定義域外）。"},
    "util.calc.err.too_big": {
        "ko": "결과가 너무 커서 계산하지 않았습니다.",
        "en": "The result would be too large, so it was not calculated.",
        "ja": "結果が大きすぎるため計算しませんでした。"},
    "util.calc.err.too_long": {
        "ko": "수식이 너무 깁니다.", "en": "The expression is too long.",
        "ja": "数式が長すぎます。"},
    "util.calc.err.not_allowed": {
        "ko": "계산기에서 쓸 수 없는 표현입니다.",
        "en": "That expression is not allowed in the calculator.",
        "ja": "電卓では使えない表現です。"},
    "util.calc.err.unknown_name": {
        "ko": "모르는 이름입니다: {name}", "en": "Unknown name: {name}",
        "ja": "不明な名前です: {name}"},
    "util.calc.err.unknown_func": {
        "ko": "모르는 함수입니다: {name}", "en": "Unknown function: {name}",
        "ja": "不明な関数です: {name}"},
    "util.calc.err.arg_count": {
        "ko": "{name} 함수에 넣은 값의 개수가 맞지 않습니다.",
        "en": "Wrong number of arguments for {name}.",
        "ja": "{name} 関数の引数の個数が正しくありません。"},
}

# 클래스 본문에서는 아래 TRANSLATIONS가 아직 정의되기 전이라 참조할 수 없어,
# 모듈을 다 읽은 이 시점에 붙여 준다(레지스트리가 이 표를 i18n에 병합한다).
CalculatorApp.tr_table = TRANSLATIONS

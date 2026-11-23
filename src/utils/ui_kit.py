# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 공통 UI 부품 [v34]

11개 미니앱이 각자 정하던 것(카드 모양·버튼 크기·여백·캔버스 배경·우측
패널 폭)을 여기 한 곳으로 모았다. 규칙은 docs/util_ui_rules.md에 적혀
있고, 미니앱은 **이 파일의 부품만** 써야 한다(styles.button_style을 직접
부르는 미니앱 코드는 헤드리스 테스트가 규격 위반으로 잡는다).

핵심 규칙 요약
- 화면 골격은 좌/우 분할(split_lr) 또는 상/하 분할(split_tb) 둘 중 하나.
- 모든 구역은 Card. Card에는 제목 줄(왼쪽 제목 + 오른쪽 툴바)이 반드시
  있고, 하단 footer에 버튼을 오른쪽 정렬로 놓는다.
- 버튼은 주(primary, 카드당 1개)·보조(secondary)·위험(danger) 3등급이고
  크기는 한 가지. 작은 아이콘 조작은 tool_button.
- 캔버스(그래프·간트·달력·표)는 canvas_frame으로 감싸 흰 배경+연한
  테두리로 카드 본문을 꽉 채운다.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget,
    QSizePolicy, QLayout, QDialog, QDialogButtonBox
)

from ..styles import C, button_style, BTN_NEUTRAL_BG, BTN_SECONDARY_SLATE, BTN_DESTRUCTIVE_BG

# ---------------------------------------------------------------- 상수
CARD_SPACING = 10          # 카드 사이
CARD_PADDING = 12          # 카드 안쪽
CTRL_SPACING = 6           # 컨트롤 사이
RIGHT_PANEL_W = 340        # 좌/우 분할에서 오른쪽 카드 폭
BTN_H = 28
BTN_FONT = 12
BTN_PAD = "4px 12px"
TOOL_BTN_SIZE = 24

TITLE_STYLE = f"color:{C.WINDOW_FG};font-weight:bold;font-size:13px;background:transparent;"
BODY_STYLE = f"color:{C.WINDOW_FG};font-size:12px;background:transparent;"
HINT_COLOR = "#5a6068"
HINT_STYLE = f"color:{HINT_COLOR};font-size:11px;background:transparent;"
ERROR_STYLE = "color:#c62828;font-size:12px;background:transparent;"
CANVAS_BORDER = "#d9dde3"

_CARD_STYLE = (f"QFrame#miniCard{{background-color:{C.UTIL_BG};border:1px solid {C.BORDER};"
               f"border-radius:8px;}}")
_CANVAS_STYLE = (f"QFrame#miniCanvas{{background-color:#ffffff;border:1px solid {CANVAS_BORDER};"
                 f"border-radius:4px;}}")


# =============================================================================
# 버튼
# =============================================================================
def _btn(text, bg, *, bold=True):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(BTN_H)
    b.setStyleSheet(button_style(bg, bold=bold, font_size=BTN_FONT, padding=BTN_PAD))
    return b


def primary_button(text=""):
    """카드당 최대 1개 — 실행·생성·적용."""
    return _btn(text, C.UTIL_MAIN)


def secondary_button(text=""):
    """저장·복사·초기화·불러오기 등 보조 동작."""
    return _btn(text, BTN_SECONDARY_SLATE)


def neutral_button(text=""):
    """보조와 같은 등급이지만 톤을 살짝 낮춘 것(취소·닫기 등)."""
    return _btn(text, BTN_NEUTRAL_BG)


def danger_button(text=""):
    """삭제·전체 지우기."""
    return _btn(text, BTN_DESTRUCTIVE_BG)


def tool_button(text=""):
    """제목 줄 툴바용 작은 버튼(◀ ▶ + × 등). 배경 없음."""
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(TOOL_BTN_SIZE, TOOL_BTN_SIZE)
    b.setStyleSheet(
        f"QPushButton{{background:transparent;color:{C.UTIL_MAIN};font-weight:bold;"
        f"border:1px solid {C.UTIL_MAIN};border-radius:4px;font-size:11px;padding:0;}}"
        f"QPushButton:hover{{background:{C.UTIL_MAIN};color:#ffffff;}}"
        f"QPushButton:checked{{background:{C.UTIL_MAIN};color:#ffffff;}}"
        f"QPushButton:disabled{{color:#b0b6bd;border-color:#d0d4da;}}")
    return b


def style_tool_toolbutton(btn, text="⚙"):
    """이미 만들어진 QToolButton(접이식 설정 토글 등)에 tool_button과 같은
    모양을 입힌다 — 카드 툴바에 넣기 위해."""
    btn.setText(text)
    btn.setArrowType(Qt.NoArrow)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedSize(TOOL_BTN_SIZE, TOOL_BTN_SIZE)
    btn.setStyleSheet(
        f"QToolButton{{background:transparent;color:{C.UTIL_MAIN};font-weight:bold;"
        f"border:1px solid {C.UTIL_MAIN};border-radius:4px;font-size:12px;padding:0;}}"
        f"QToolButton:hover{{background:{C.UTIL_MAIN};color:#ffffff;}}"
        f"QToolButton:checked{{background:{C.UTIL_MAIN};color:#ffffff;}}")
    return btn


def toggle_button(text="", checked=False):
    """모드 전환(mRNA/DNA, 일별/주간/월별 등) — 체크 상태로 선택 표시."""
    b = tool_button(text)
    b.setCheckable(True)
    b.setChecked(checked)
    b.setFixedSize(16777215, TOOL_BTN_SIZE)
    b.setMinimumWidth(48)
    b.setMaximumWidth(16777215)
    b.setStyleSheet(b.styleSheet().replace("padding:0;", "padding:0 8px;"))
    return b


def radio_row(labels, checked_index=0):
    """[v38] "둘 중 하나만" 고르는 선택지 — 토글 버튼은 눌린 상태가
    잘 안 보인다는 지적이 있어, 실제 라디오 버튼(원 안에 점)으로 확실히
    구분되게 만든 것. (QButtonGroup, [QRadioButton, ...]) 튜플을 돌려준다
    — group은 파이썬이 들고 있어야 가비지 컬렉션에 안 걸린다."""
    from PySide6.QtWidgets import QButtonGroup, QRadioButton
    group = QButtonGroup()
    group.setExclusive(True)
    buttons = []
    for i, text in enumerate(labels):
        b = QRadioButton(text)
        b.setStyleSheet(f"QRadioButton{{color:{C.WINDOW_FG};font-size:12px;spacing:6px;}}"
                        f"QRadioButton::indicator{{width:14px;height:14px;}}")
        if i == checked_index:
            b.setChecked(True)
        group.addButton(b, i)
        buttons.append(b)
    return group, buttons


# =============================================================================
# 라벨
# =============================================================================
def title_label(text=""):
    lbl = QLabel(text)
    lbl.setStyleSheet(TITLE_STYLE)
    return lbl


def body_label(text=""):
    lbl = QLabel(text)
    lbl.setStyleSheet(BODY_STYLE)
    return lbl


def hint_label(text=""):
    lbl = QLabel(text)
    lbl.setStyleSheet(HINT_STYLE)
    lbl.setWordWrap(True)
    return lbl


def error_label():
    lbl = QLabel("")
    lbl.setStyleSheet(ERROR_STYLE)
    lbl.setWordWrap(True)
    return lbl


# =============================================================================
# 카드
# =============================================================================
class Card(QFrame):
    """제목 줄(제목 + 툴바) / 본문 / 하단 버튼 줄로 이루어진 구역."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("miniCard")
        self.setStyleSheet(_CARD_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(CARD_PADDING, CARD_PADDING - 2, CARD_PADDING, CARD_PADDING)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(CTRL_SPACING)
        self.title_label = title_label(title)
        header.addWidget(self.title_label)
        header.addStretch()
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(CTRL_SPACING)
        header.addLayout(self.toolbar)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(CTRL_SPACING)
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body, 1)

        self.footer = QHBoxLayout()
        self.footer.setSpacing(CTRL_SPACING)
        self.footer.addStretch()
        outer.addLayout(self.footer)
        self._footer_count = 0

    def set_title(self, text):
        self.title_label.setText(text)

    def add_tool(self, widget):
        if isinstance(widget, QLabel):
            widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.toolbar.addWidget(widget)
        return widget

    def add_tool_layout(self, layout):
        self.toolbar.addLayout(layout)
        return layout

    def add_body(self, item, stretch=0):
        if isinstance(item, QLayout):
            self.body.addLayout(item, stretch)
        else:
            self.body.addWidget(item, stretch)
        return item

    def add_footer(self, widget):
        """오른쪽 정렬로 쌓인다 — 마지막에 넣은 것이 맨 오른쪽(주 동작 자리)."""
        self.footer.addWidget(widget)
        self._footer_count += 1
        return widget

    def add_footer_left(self, widget):
        """footer 왼쪽 끝(도움말 등 버튼이 아닌 것)."""
        self.footer.insertWidget(0, widget)
        return widget


# =============================================================================
# 캔버스 프레임
# =============================================================================
def canvas_frame(widget, *, margin=0):
    """캔버스 위젯을 흰 배경 + 연한 테두리로 감싼다. 카드 본문을 꽉 채우도록
    확장 정책을 준다."""
    frame = QFrame()
    frame.setObjectName("miniCanvas")
    frame.setStyleSheet(_CANVAS_STYLE)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margin, margin, margin, margin)
    lay.setSpacing(0)
    lay.addWidget(widget)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return frame


# =============================================================================
# 화면 골격
# =============================================================================
def _root_layout(widget, vertical=False):
    lay = QVBoxLayout(widget) if vertical else QHBoxLayout(widget)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(CARD_SPACING)
    return lay


def split_lr(widget, left, right, *, right_width=RIGHT_PANEL_W, left_stretch=1):
    """좌/우 분할 — 오른쪽은 폭 고정, 왼쪽이 남는 공간을 차지한다.
    `left`/`right`는 위젯(Card) 또는 레이아웃."""
    root = _root_layout(widget)
    if isinstance(left, QLayout):
        root.addLayout(left, left_stretch)
    else:
        root.addWidget(left, left_stretch)
    if isinstance(right, QLayout):
        holder = QWidget()
        holder.setLayout(right)
        right = holder
    right.setFixedWidth(right_width)
    root.addWidget(right)
    return root


def split_tb(widget, top, bottom, *, bottom_stretch=1):
    """상/하 분할 — 위는 필요한 만큼, 아래가 남는 공간을 차지한다."""
    root = _root_layout(widget, vertical=True)
    if isinstance(top, QLayout):
        root.addLayout(top)
    else:
        root.addWidget(top)
    if isinstance(bottom, QLayout):
        root.addLayout(bottom, bottom_stretch)
    else:
        root.addWidget(bottom, bottom_stretch)
    return root


def vstack(*items, spacing=CARD_SPACING):
    """카드를 세로로 쌓는 레이아웃(좌/우 분할의 한쪽에 카드가 여러 개일 때)."""
    lay = QVBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for it in items:
        if isinstance(it, QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    return lay


def hrow(*items, spacing=CTRL_SPACING, stretch_last=False):
    """컨트롤을 한 줄로 늘어놓는 도우미."""
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for i, it in enumerate(items):
        if it is None:
            lay.addStretch()
        elif isinstance(it, QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    if stretch_last:
        lay.addStretch()
    return lay


# ---------------------------------------------------------------- 인쇄(공용)
class PrintCopiesDialog(QDialog):
    """[v43.9] "1쪽/2쪽/4쪽" 인쇄 배치를 고르는 공용 창 — 표 기반 미니앱
    (시간표·좌석표 등)이 함께 쓴다. 1쪽=가로로 꽉 채워 1번, 2쪽=세로
    방향으로 위아래 2번, 4쪽=가로 방향 2행 2열로 4번. 문구는 전부
    호출부가 넘긴다 — 공용 부품은 표시 문구를 직접 갖지 않는다는
    원칙(내부 코드와 화면 문구를 분리) 그대로다."""

    def __init__(self, title, hint, label_1, label_2, label_4, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(hint))
        self.group, buttons = radio_row([label_1, label_2, label_4], checked_index=0)
        self.radio_1, self.radio_2, self.radio_4 = buttons
        row = QHBoxLayout()
        row.addWidget(self.radio_1)
        row.addWidget(self.radio_2)
        row.addWidget(self.radio_4)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def result_copies(self):
        if self.radio_2.isChecked():
            return 2
        if self.radio_4.isChecked():
            return 4
        return 1


def draw_pixmap_fit(painter, pix, rect):
    """pix를 rect 안에 비율을 유지한 채 최대한 크게, 가운데 맞춰 그린다."""
    if pix.width() <= 0 or pix.height() <= 0:
        return
    scale = min(rect.width() / pix.width(), rect.height() / pix.height())
    w, h = pix.width() * scale, pix.height() * scale
    x = rect.x() + (rect.width() - w) / 2
    y = rect.y() + (rect.height() - h) / 2
    painter.save()
    painter.translate(x, y)
    painter.scale(scale, scale)
    painter.drawPixmap(0, 0, pix)
    painter.restore()


def print_pixmap_with_copies(parent, printer, pix, copies):
    """이미 고른 배치(1/2/4)에 맞춰 pix(캔버스 스냅샷)를 인쇄한다 —
    printer는 호출부가 미리 방향(가로/세로)까지 맞춰서 넘긴다."""
    painter = QPainter(printer)
    page = printer.pageRect(QPrinter.DevicePixel)
    if copies == 1:
        draw_pixmap_fit(painter, pix, page)
    elif copies == 2:
        half_h = page.height() / 2
        draw_pixmap_fit(painter, pix, QRectF(page.x(), page.y(), page.width(), half_h))
        draw_pixmap_fit(painter, pix, QRectF(page.x(), page.y() + half_h, page.width(), half_h))
    else:
        half_w, half_h = page.width() / 2, page.height() / 2
        for r in range(2):
            for c in range(2):
                rect = QRectF(page.x() + c * half_w, page.y() + r * half_h, half_w, half_h)
                draw_pixmap_fit(painter, pix, rect)
    painter.end()

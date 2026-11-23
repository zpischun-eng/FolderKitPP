# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 대진표 작성기 [신규]

체육 수업에서 학생을 조 편성하거나 대진표를 짤 때 쓴다. 세 가지 모드를
버튼으로 전환한다 — **조 편성**(피구·농구처럼 팀 스포츠), **토너먼트**
(탁구·배드민턴처럼 1:1 단일 엘리미네이션), **리그**(모두 한 번씩
겨루는 조별리그). 알고리즘은 bracket_solve.py에 있고, 이 파일은 화면
표시(특히 토너먼트의 대진표 트리를 QPainter로 직접 그리는 부분)만
다룬다.
"""
import os
import datetime as _dt

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QIntValidator, QBrush, QFontMetrics
from PySide6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QSpinBox, QScrollArea, QFileDialog, QComboBox, QDialog, QDialogButtonBox,
    QLineEdit, QCheckBox, QListWidget, QListWidgetItem, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QInputDialog, QFrame, QTabWidget, QTreeWidget, QTreeWidgetItem, QGridLayout, QMenu
)

from ..i18n import tr
from ..styles import C, BTN_DESTRUCTIVE_BG
from . import ui_kit as UK
from .base import MiniApp
from . import bracket_solve as B

_SET_ROSTER = "util.bracket.roster"
_SET_EVENTS = "util.bracket.events"
_SET_HISTORY_PATH = "util.bracket.history_path"
_SET_MANUAL_TIERS = "util.bracket.manual_tiers"
_SET_LAST_SERIES_KEY = "util.bracket.last_series_key"

# [신규] 실력 등급별 배경색 — 상(금색)·중(은색)으로 옅게 칠해서 대진표에서
# 어느 등급끼리 겨루는지 한눈에 보이게 한다. 하는 지금처럼 색을 안 칠한다
# (None이면 색 없음).
_TIER_BG = {
    "상": "#ffe9a8",
    "중": "#e3e4e8",
    "하": None,
}


def _set_row_tier_color(item, tier):
    """QTreeWidgetItem의 모든 열(4개) 배경을 등급 색으로 칠한다(등급이
    없거나 "하"면 색을 지워 기본 배경으로 되돌린다)."""
    hexcolor = _TIER_BG.get(tier)
    brush = QBrush(QColor(hexcolor)) if hexcolor else QBrush()
    for col in range(4):
        item.setBackground(col, brush)


def _html_escape(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# =============================================================================
def _mark_female_inline(text, genders):
    """[버그 수정] 리그 표(QTableWidget)는 우리가 직접 점을 겹쳐 그리려고
    하면 줄 수·줄 간격을 Qt의 실제 렌더링과 똑같이 못 맞춰서(스타일·
    글꼴에 따라 달라짐) 점이 엉뚱한 자리(줄 사이·칸 전체 기준)에 찍히는
    문제가 있었다 — 실제로 화면에서 "팀 전체에 점 하나"처럼 보였다.
    좌표를 계산해서 겹쳐 그리는 대신, **여학생 줄의 글자 자체에 "♀"
    표시를 바로 붙여서** 만든다 — 그러면 Qt가 그 줄을 어떻게 배치하든
    표시가 항상 그 학생 이름과 정확히 같은 줄에 남는다(별도 그리기가
    아니라 글자의 일부이므로)."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        if line and i < len(genders) and genders[i]:
            out.append(f"{line} ♀")
        else:
            out.append(line)
    return "\n".join(out)


class _Cell:
    """대진표 화면에 그릴 칸 하나(공통 표현) — 빠른 대진표(튜플)든 학급
    명단 기반 종목(Match 객체)이든 이 형태로 바꿔서 그린다."""
    __slots__ = ("label_a", "label_b", "winner", "note", "clickable", "tier_a", "tier_b",
                "female_a", "female_b")

    def __init__(self, label_a, label_b, winner=None, note="", clickable=False, tier_a=None, tier_b=None,
                female_a=None, female_b=None):
        self.label_a = label_a
        self.label_b = label_b
        self.winner = winner        # None | "a" | "b"
        self.note = note
        self.clickable = clickable  # 클릭해서 결과를 기록할 수 있는 칸인지
        self.tier_a = tier_a        # [신규] 참가자 A의 실력 등급(상/중/하) — 알 수 없으면 None
        self.tier_b = tier_b
        # [v39] 이름이 줄마다 하나씩 들어간 label_a/label_b와 줄 수를 맞춘
        # "그 줄이 여학생인지" 목록 — 대진표에도 여학생 표시를 찍으려고.
        self.female_a = female_a or []
        self.female_b = female_b or []


class _BracketCanvas(QWidget):
    """토너먼트 대진표를 라운드(열)마다 매치(칸)로 그린다. **학급 명단
    기반 종목**에서는 칸을 클릭해 경기 결과(승자·점수)를 기록할 수
    있다 — 두 자리가 다 채워지고 아직 결과가 없는 칸만 클릭에 반응한다
    (부전승·TBD 칸은 클릭해도 할 게 없다)."""

    BOX_W = 170
    LINE_H = 14
    COL_GAP, ROW_GAP = 50, 18

    matchClicked = Signal(int, int)   # (라운드, 그 라운드 안에서의 순번)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cells = []             # list[list[_Cell]]
        self.box_h = 46             # [신규] 복식·단체전처럼 한 칸에 이름이 여러 줄이면 늘어난다
        self._champion_label = None
        self.setStyleSheet("background:#ffffff;")
        self.setMouseTracking(True)
        self._hover_cell = None

    def _calc_box_h(self):
        """모든 칸을 훑어 한쪽 편에 들어가는 최대 줄 수(팀원이 여러
        명이면 여러 줄)를 구하고, 그만큼 칸 높이를 늘린다 — 안 그러면
        복식·단체전에서 팀원 이름이 잘려 보인다(실제로 이런 제보를
        받았다)."""
        max_lines = 1
        for row in self.cells:
            for cell in row:
                for label in (cell.label_a, cell.label_b):
                    max_lines = max(max_lines, label.count("\n") + 1)
        return max(46, max_lines * self.LINE_H * 2 + 14)

    # ------------------------------------------------------------ 데이터 주입
    def set_rounds(self, rounds):
        """빠른 대진표(튜플 (a,b) 목록의 목록) — 클릭으로 기록하지
        않는, 한 번 보고 마는 대진표용."""
        cells = []
        for matches in rounds:
            row = []
            for a, b in matches:
                label_a = a if a else (tr("util.bracket.bye") if b else tr("util.bracket.tbd"))
                label_b = b if b else (tr("util.bracket.bye") if a else tr("util.bracket.tbd"))
                winner = "a" if (a and not b) else ("b" if (b and not a) else None)
                row.append(_Cell(label_a, label_b, winner=winner))
            cells.append(row)
        self.cells = cells
        champ = None
        if rounds:
            a, b = rounds[-1][0]
            champ = a or b
        self._champion_label = tr("util.bracket.champion", a0=champ) if champ else None
        self._refresh()

    def set_event_bracket(self, bracket, entry_tiers=None, label_overrides=None, label_genders=None):
        """학급 명단 기반 종목의 Bracket(Match 객체) — 두 자리가 채워진
        칸은 클릭해서 결과를 기록할 수 있다. entry_tiers를 주면(참가자
        id -> 등급) 그 등급 색으로 각 편의 배경을 칠한다. label_overrides는
        [v39] 오늘 출석 조정(결석·임시 합류)을 반영한 표시용 라벨이고,
        label_genders는 그 줄마다 여학생인지(분홍 점 표시)다."""
        entry_tiers = entry_tiers or {}
        ov = label_overrides or {}
        gd = label_genders or {}
        cells = []
        for matches in bracket.rounds:
            row = []
            for m in matches:
                la = ov.get(m.a, bracket.label(m.a)) if m.a else (tr("util.bracket.bye") if m.b else tr("util.bracket.tbd"))
                lb = ov.get(m.b, bracket.label(m.b)) if m.b else (tr("util.bracket.bye") if m.a else tr("util.bracket.tbd"))
                clickable = (m.a is not None and m.b is not None)
                row.append(_Cell(la, lb, winner=m.winner, note=m.note, clickable=clickable,
                                 tier_a=entry_tiers.get(m.a) if m.a else None,
                                 tier_b=entry_tiers.get(m.b) if m.b else None,
                                 female_a=gd.get(m.a) if m.a else None,
                                 female_b=gd.get(m.b) if m.b else None))
            cells.append(row)
        self.cells = cells
        champ_id = bracket.champion()
        self._champion_label = tr("util.bracket.champion", a0=bracket.label(champ_id)) if champ_id else None
        self._refresh()

    def _refresh(self):
        self.box_h = self._calc_box_h()
        # [버그 수정] setMinimumSize(sizeHint())로 두면, 참가자가 많아
        # 대진표가 한 번이라도 옆으로 넓게 그려지고 나면 이 위젯의
        # "최소 크기" 자체가 그 넓은 값으로 영구히 고정돼 버린다 —
        # 이 캔버스는 스크롤 영역(widgetResizable=False) 안에 있어서
        # 원래 자기 크기 그대로 두고 스크롤로 보는 게 맞는데, 최소
        # 크기까지 그렇게 못박히면 그 스크롤 영역을 포함한 화면 전체
        # (Util 모드 좌/우 스플리터의 오른쪽 칸)의 최소 폭이 같이
        # 커져서, 나중에 스플리터를 오른쪽으로 다시 못 옮기는 현상으로
        # 이어졌다. 실제로 필요한 건 "지금 크기로 맞추기"뿐이라
        # resize()만으로 충분하다.
        self.resize(self.sizeHint())
        self.update()

    def sizeHint(self):
        if not self.cells:
            return QSize(400, 200)
        n_rounds = len(self.cells)
        n_r1 = len(self.cells[0])
        w = n_rounds * (self.BOX_W + self.COL_GAP) + 20
        h = n_r1 * (self.box_h + self.ROW_GAP) + 30
        return QSize(w, h)

    def _positions(self):
        if not self.cells:
            return []
        positions = [[20 + i * (self.box_h + self.ROW_GAP) for i in range(len(self.cells[0]))]]
        for r in range(1, len(self.cells)):
            prev = positions[r - 1]
            positions.append([(prev[2 * i] + prev[2 * i + 1]) / 2 for i in range(len(prev) // 2)])
        return positions

    def _cell_rect(self, r, i, positions=None):
        positions = positions or self._positions()
        xr = 20 + r * (self.BOX_W + self.COL_GAP)
        yc = positions[r][i]
        return QRectF(xr, yc, self.BOX_W, self.box_h)

    # ------------------------------------------------------------- 그리기
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if not self.cells:
            p.end()
            return
        positions = self._positions()
        font = QFont("Arial", 10)
        p.setFont(font)

        for r, row in enumerate(self.cells):
            xr = 20 + r * (self.BOX_W + self.COL_GAP)
            for i, cell in enumerate(row):
                rect = self._cell_rect(r, i, positions)
                yc = rect.y()
                is_hover = cell.clickable and self._hover_cell == (r, i)
                default_bg = "#fff5f9" if is_hover else "#fafafa"

                # [신규] 두 편의 실력 등급 색으로 각 반쪽을 먼저 채운다
                # (없으면 기본 배경) — 등급끼리 대결하는 게 한눈에 보이게.
                p.setPen(Qt.NoPen)
                for half, tier in ((0, cell.tier_a), (1, cell.tier_b)):
                    half_rect = QRectF(xr, yc + half * self.box_h / 2, self.BOX_W, self.box_h / 2)
                    bg_hex = _TIER_BG.get(tier) if tier else None
                    p.setBrush(QColor(bg_hex) if bg_hex else QColor(default_bg))
                    p.drawRect(half_rect)

                p.setPen(QPen(QColor(C.UTIL_MAIN if is_hover else C.BORDER), 1.6 if is_hover else 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                p.drawLine(QPointF(xr, yc + self.box_h / 2), QPointF(xr + self.BOX_W, yc + self.box_h / 2))

                for half, label, side, genders in ((0, cell.label_a, "a", cell.female_a),
                                                    (1, cell.label_b, "b", cell.female_b)):
                    is_winner = cell.winner == side
                    f = QFont("Arial", 10, QFont.Bold if is_winner else QFont.Normal)
                    p.setFont(f)
                    p.setPen(QPen(QColor(C.UTIL_MAIN if is_winner else C.WINDOW_FG)))
                    half_rect = QRectF(xr + 6, yc + half * self.box_h / 2, self.BOX_W - 12, self.box_h / 2)
                    _draw_multiline_with_gender(p, half_rect, label, genders)
                p.setFont(font)

                if cell.note:
                    p.setPen(QPen(QColor("#8a8f98")))
                    p.setFont(QFont("Arial", 8))
                    p.drawText(QRectF(xr + 6, yc + self.box_h + 1, self.BOX_W - 12, 12),
                              Qt.AlignLeft, cell.note)
                    p.setFont(font)

                is_final = (r == len(self.cells) - 1)
                if is_final and self._champion_label:
                    p.setPen(QPen(QColor(C.UTIL_MAIN)))
                    p.setFont(QFont("Arial", 10, QFont.Bold))
                    p.drawText(QRectF(xr, yc + self.box_h + 14, self.BOX_W, 18),
                              Qt.AlignHCenter, self._champion_label)
                    p.setFont(font)

                if r + 1 < len(self.cells):
                    nxt_y = positions[r + 1][i // 2]
                    mid_x = xr + self.BOX_W + self.COL_GAP / 2
                    cur_mid_y = yc + self.box_h / 2
                    nxt_mid_y = nxt_y + self.box_h / 2
                    p.setPen(QPen(QColor(C.BORDER), 1.2))
                    p.drawLine(QPointF(xr + self.BOX_W, cur_mid_y), QPointF(mid_x, cur_mid_y))
                    p.drawLine(QPointF(mid_x, cur_mid_y), QPointF(mid_x, nxt_mid_y))
                    p.drawLine(QPointF(mid_x, nxt_mid_y), QPointF(xr + self.BOX_W + self.COL_GAP, nxt_mid_y))
        p.end()

    # ------------------------------------------------------------- 클릭
    def _cell_at(self, pos):
        positions = self._positions()
        for r, row in enumerate(self.cells):
            for i, cell in enumerate(row):
                if self._cell_rect(r, i, positions).contains(pos):
                    return r, i, cell
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        hit = self._cell_at(pos)
        if hit and hit[2].clickable:
            self.matchClicked.emit(hit[0], hit[1])

    def mouseMoveEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        hit = self._cell_at(pos)
        new_hover = (hit[0], hit[1]) if hit and hit[2].clickable else None
        if new_hover != self._hover_cell:
            self._hover_cell = new_hover
            self.setCursor(Qt.PointingHandCursor if new_hover else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        if self._hover_cell is not None:
            self._hover_cell = None
            self.update()



# =============================================================================
class _LeagueView(QWidget):
    """리그전(조별리그) 화면 — 라운드별 경기를 표로 보여준다. 두 참가자가
    다 채워진(부전승이 아닌) 경기 행을 클릭하면 결과를 기록할 수 있다."""

    matchClicked = Signal(int, int)   # (라운드, 그 라운드 안에서의 순번)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setWordWrap(False)
        # [버그 수정] word-wrap을 켜 두면(이전 버전) 이름이 길어 칸 폭을
        # 넘기는 경우 자동으로 줄이 하나 더 생겨서, 성별 점을 줄 단위로
        # 겹쳐 그릴 때 실제 화면 줄과 어긋나 "팀 전체에 점 하나"처럼
        # 보이는 원인이 됐다. 줄바꿈은 항상 "\n"으로 직접 넣은 자리에서만
        # 일어나게 하면(=word-wrap 끔) 줄 수가 항상 정확히 맞는다.
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.cellClicked.connect(self._on_cell_clicked)
        lay.addWidget(self.table)
        self._row_refs = []   # [(r, i, clickable), ...] — 표의 행 순서와 일치

    def set_headers(self, labels):
        self.table.setHorizontalHeaderLabels(labels)

    def set_league(self, league, entry_tiers=None, label_overrides=None, label_genders=None):
        entry_tiers = entry_tiers or {}
        ov = label_overrides or {}
        gd = label_genders or {}
        self.table.setRowCount(0)
        self._row_refs = []
        for r, matches in enumerate(league.rounds):
            for i, m in enumerate(matches):
                row = self.table.rowCount()
                self.table.insertRow(row)
                clickable = (m.a is not None and m.b is not None)
                la = ov.get(m.a, league.label(m.a)) if m.a else tr("util.bracket.bye")
                lb = ov.get(m.b, league.label(m.b)) if m.b else tr("util.bracket.bye")
                if m.a:
                    la = _mark_female_inline(la, gd.get(m.a) or [])
                if m.b:
                    lb = _mark_female_inline(lb, gd.get(m.b) or [])
                item_round = QTableWidgetItem(tr("util.bracket.round_label", a0=r + 1))
                item_a = QTableWidgetItem(la)
                item_b = QTableWidgetItem(lb)
                # [신규] 실력 등급 색으로 참가자 A·B 칸을 칠한다(등급끼리
                # 대결하는 걸 한눈에 보이게).
                tier_a_bg = _TIER_BG.get(entry_tiers.get(m.a)) if m.a else None
                tier_b_bg = _TIER_BG.get(entry_tiers.get(m.b)) if m.b else None
                if tier_a_bg:
                    item_a.setBackground(QColor(tier_a_bg))
                if tier_b_bg:
                    item_b.setBackground(QColor(tier_b_bg))
                if m.winner == "a":
                    item_a.setForeground(QColor(C.UTIL_MAIN))
                    f = item_a.font(); f.setBold(True); item_a.setFont(f)
                elif m.winner == "b":
                    item_b.setForeground(QColor(C.UTIL_MAIN))
                    f = item_b.font(); f.setBold(True); item_b.setFont(f)
                if m.winner is None and not clickable:
                    result_text = tr("util.bracket.bye")
                elif m.winner is None:
                    result_text = tr("util.bracket.roster.click_to_record")
                else:
                    result_text = m.note or tr("util.bracket.roster.click_to_record")
                item_result = QTableWidgetItem(result_text)
                for item in (item_round, item_a, item_b, item_result):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 0, item_round)
                self.table.setItem(row, 1, item_a)
                self.table.setItem(row, 2, item_b)
                self.table.setItem(row, 3, item_result)
                self._row_refs.append((r, i, clickable))
        self.table.resizeRowsToContents()

    def _on_cell_clicked(self, row, col):
        if row < 0 or row >= len(self._row_refs):
            return
        r, i, clickable = self._row_refs[row]
        if clickable:
            self.matchClicked.emit(r, i)


class _ArrowNavEdit(QLineEdit):
    """[v38] 점수 입력 칸. 화살표 키를 누르면 그 방향으로 이웃한 칸으로
    포커스가 넘어가고, 넘어간 칸의 내용은 바로 다시 칠 수 있게 전체
    선택해 둔다(엑셀 표에서 방향키로 옮겨 다니는 느낌과 같다).
    set_idx/side(0=A,1=B)만 들고 있고, 실제 이웃 칸 목록(grid_a/grid_b)은
    다이얼로그가 그리드를 다 만든 뒤에 채워 넣는다."""

    def __init__(self, set_idx, side, parent=None):
        super().__init__(parent)
        self.set_idx = set_idx
        self.side = side
        self.grid_a = []
        self.grid_b = []

    def keyPressEvent(self, event):
        col = self.grid_a if self.side == 0 else self.grid_b
        other_col = self.grid_b if self.side == 0 else self.grid_a
        target = None
        if event.key() == Qt.Key_Up and self.set_idx > 0:
            target = col[self.set_idx - 1]
        elif event.key() == Qt.Key_Down and self.set_idx < len(col) - 1:
            target = col[self.set_idx + 1]
        elif event.key() in (Qt.Key_Left, Qt.Key_Right):
            target = other_col[self.set_idx] if other_col else None
        if target is not None:
            target.setFocus()
            target.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)


class _RecordResultDialog(QDialog):
    """경기 결과를 기록하는 다이얼로그. 이름을 두 번 늘어놓지 않고
    **참가자 A / 참가자 B를 좌우로 나눈 표**로 보여주고, 세트마다
    점수(숫자)만 3칸씩 입력하면 승패는 자동으로 계산한다(점수를 직접
    비교해 이긴 세트가 더 많은 쪽이 승리).

    [버그 수정] 두 가지를 고쳤다:
    1. QSpinBox는 한글 입력기(IME)가 조합 중인 글자를 막지 못해 숫자
       칸에 한글이 들어가는 문제가 있었다 — QLineEdit + QIntValidator +
       `Qt.ImhDigitsOnly`(입력기에 "이 칸은 숫자만" 이라고 알려주는
       힌트)로 바꿔서 원천적으로 숫자 아닌 문자가 못 들어가게 했다.
    2. 한쪽 점수만 입력하고 다른 쪽을 비워 둬도 그 세트가 그냥 기록되던
       문제가 있었다 — 이제 **양쪽 다 입력해야만** 그 세트를 인정하고,
       빈 세트 다음에 값이 있는 세트가 나오면(예: 2세트를 비우고
       3세트만 입력) 순서 오류로 막는다."""

    def __init__(self, label_a, label_b, current_sets=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.bracket.roster.record.title"))
        self.setMinimumWidth(380)
        self._cleared = False
        lay = QVBoxLayout(self)

        header_row = QHBoxLayout()
        lbl_a = QLabel(label_a)
        lbl_a.setWordWrap(True)
        lbl_a.setStyleSheet("font-weight:bold;background:transparent;")
        lbl_a.setAlignment(Qt.AlignCenter)
        header_row.addWidget(lbl_a, 1)
        lbl_vs = QLabel("vs")
        lbl_vs.setStyleSheet("color:#8a8f98;background:transparent;")
        header_row.addWidget(lbl_vs, 0)
        lbl_b = QLabel(label_b)
        lbl_b.setWordWrap(True)
        lbl_b.setStyleSheet("font-weight:bold;background:transparent;")
        lbl_b.setAlignment(Qt.AlignCenter)
        header_row.addWidget(lbl_b, 1)
        lay.addLayout(header_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.edits_a = []
        self.edits_b = []
        current_sets = current_sets or []
        for set_idx in range(3):
            lbl_set = QLabel(tr("util.bracket.roster.record.set_label", a0=set_idx + 1))
            lbl_set.setAlignment(Qt.AlignCenter)
            grid.addWidget(lbl_set, set_idx, 0)
            edit_a = _ArrowNavEdit(set_idx, 0)
            edit_a.setValidator(QIntValidator(0, 99, edit_a))
            edit_a.setAlignment(Qt.AlignCenter)
            edit_a.setInputMethodHints(Qt.ImhDigitsOnly)   # 한글 입력기가 이 칸에서 조합 모드로 안 들어가게
            edit_a.setFixedWidth(48)
            grid.addWidget(edit_a, set_idx, 1)
            lbl_colon = QLabel(":")
            lbl_colon.setAlignment(Qt.AlignCenter)
            grid.addWidget(lbl_colon, set_idx, 2)
            edit_b = _ArrowNavEdit(set_idx, 1)
            edit_b.setValidator(QIntValidator(0, 99, edit_b))
            edit_b.setAlignment(Qt.AlignCenter)
            edit_b.setInputMethodHints(Qt.ImhDigitsOnly)
            edit_b.setFixedWidth(48)
            grid.addWidget(edit_b, set_idx, 3)
            if set_idx < len(current_sets):
                a_val, b_val = current_sets[set_idx]
                if a_val is not None:
                    edit_a.setText(str(a_val))
                if b_val is not None:
                    edit_b.setText(str(b_val))
            edit_a.textChanged.connect(self._update_preview)
            edit_b.textChanged.connect(self._update_preview)
            self.edits_a.append(edit_a)
            self.edits_b.append(edit_b)
        for edit in self.edits_a + self.edits_b:
            edit.grid_a, edit.grid_b = self.edits_a, self.edits_b
        grid_row = QHBoxLayout()
        grid_row.addStretch()
        grid_row.addLayout(grid)
        grid_row.addStretch()
        lay.addLayout(grid_row)

        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_preview)
        self._update_preview()

        btn_row = QHBoxLayout()
        if current_sets:
            self.btn_clear = QPushButton(tr("util.bracket.roster.record.clear"))
            self.btn_clear.clicked.connect(self._on_clear)
            btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok_clicked)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _validate(self):
        """세트 입력을 검사한다.
        - 양쪽 다 비어 있으면: "치르지 않은 세트"로 보고 건너뜀(문제
          없음).
        - 한쪽만 입력됐으면: 오류(부분 입력).
        - 빈 세트 다음에 값이 채워진 세트가 나오면: 오류(세트를 건너뛰고
          입력함 — 예: 2세트를 비우고 3세트만 입력).
        (ok, 오류 문구, 세트 목록)을 돌려준다."""
        rows = [(ea.text().strip(), eb.text().strip()) for ea, eb in zip(self.edits_a, self.edits_b)]
        sets = []
        seen_empty = False
        for ta, tb in rows:
            both_empty = (ta == "" and tb == "")
            both_filled = (ta != "" and tb != "")
            if both_empty:
                seen_empty = True
                continue
            if seen_empty:
                return False, tr("util.bracket.roster.record.error_skip"), []
            if not both_filled:
                return False, tr("util.bracket.roster.record.error_partial"), []
            sets.append((int(ta), int(tb)))
        return True, "", sets

    def _update_preview(self):
        ok, err, sets = self._validate()
        if not ok:
            self.lbl_preview.setStyleSheet(f"color:{BTN_DESTRUCTIVE_BG};font-weight:bold;background:transparent;")
            self.lbl_preview.setText(err)
            return
        if not sets:
            self.lbl_preview.setStyleSheet("color:#8a8f98;background:transparent;")
            self.lbl_preview.setText(tr("util.bracket.roster.record.enter_scores"))
            return
        a_sets, b_sets, winner = B.compute_sets_result(sets)
        if winner is None:
            self.lbl_preview.setStyleSheet(f"color:{BTN_DESTRUCTIVE_BG};font-weight:bold;background:transparent;")
            self.lbl_preview.setText(tr("util.bracket.roster.record.tied", a0=a_sets, a1=b_sets))
        else:
            self.lbl_preview.setStyleSheet(f"color:{C.UTIL_MAIN};font-weight:bold;background:transparent;")
            self.lbl_preview.setText(tr("util.bracket.roster.record.preview", a0=a_sets, a1=b_sets))

    def _on_ok_clicked(self):
        ok, err, sets = self._validate()
        if not ok:
            return   # 오류 문구가 이미 미리보기에 보이니, 고칠 때까지 닫지 않는다
        self.accept()

    def _on_clear(self):
        self._cleared = True
        self.accept()

    def is_cleared(self):
        return self._cleared

    def result(self):
        """(승자쪽, 세트목록, 요약문구)를 돌려준다. 승자가 없으면
        (None, [], "")."""
        ok, err, sets = self._validate()
        if not ok or not sets:
            return None, [], ""
        a_sets, b_sets, winner = B.compute_sets_result(sets)
        if winner is None:
            return None, [], ""
        return winner, [list(s) for s in sets], f"{a_sets}:{b_sets}"


# =============================================================================
_GENDER_FEMALE_TOKENS = ("여", "f", "female", "woman", "girl", "女")


def _is_female(gender):
    g = (gender or "").strip().lower()
    return any(g.startswith(tok) for tok in _GENDER_FEMALE_TOKENS)


_GENDER_DOT_FILL = "#f6c1d0"
_GENDER_DOT_LINE = "#e79ab3"


def _draw_multiline_with_gender(painter, rect, text, genders, align=Qt.AlignVCenter | Qt.AlignLeft, dot_d=7):
    """[v39] 이름이 줄마다 하나씩 들어간 text를 rect 안에 그리고, genders[i]가
    True인 줄에는 그 줄 텍스트 바로 뒤에 옅은 분홍 점을 찍는다. Qt의 기본
    drawText(멀티라인+세로가운데)와 같은 자리에 오도록, 줄 높이·전체 블록
    높이를 직접 계산해서 한 줄씩 그린다(참가자 표의 단일 줄 델리게이트와
    달리 대진표·리그 표는 팀원이 여러 줄이라 줄 단위로 처리해야 한다)."""
    fm = painter.fontMetrics()
    lines = text.split("\n") if text else [""]
    line_h = fm.height()
    block_h = line_h * len(lines)
    if align & Qt.AlignVCenter:
        top = rect.top() + max(0.0, (rect.height() - block_h) / 2)
    elif align & Qt.AlignBottom:
        top = rect.bottom() - block_h
    else:
        top = rect.top()
    for li, line in enumerate(lines):
        line_rect = QRectF(rect.left(), top + li * line_h, rect.width(), line_h)
        painter.drawText(line_rect, Qt.AlignVCenter | (align & (Qt.AlignLeft | Qt.AlignHCenter | Qt.AlignRight)),
                         line)
        if li < len(genders) and genders[li]:
            tw = fm.horizontalAdvance(line)
            if align & Qt.AlignHCenter:
                cx = line_rect.center().x() + tw / 2 + dot_d / 2 + 3
            else:
                cx = line_rect.left() + tw + dot_d / 2 + 4
            cy = line_rect.center().y()
            pen = painter.pen()
            brush = painter.brush()
            painter.setPen(QPen(QColor(_GENDER_DOT_LINE), 1))
            painter.setBrush(QColor(_GENDER_DOT_FILL))
            painter.drawEllipse(QPointF(cx, cy), dot_d / 2, dot_d / 2)
            painter.setPen(pen)
            painter.setBrush(brush)


class _GenderMarkDelegate(QStyledItemDelegate):
    """[v39] 참가자 표 이름 칸 — 여학생이면 이름·번호 뒤에 옅은 붉은 원을
    하나 그린다(남녀를 한눈에 구분하려고). 성별은 항목의 UserRole+1에
    들어 있고, 그림만 얹을 뿐 글자·체크박스 처리는 기본 델리게이트 그대로."""

    MARK_D = 9
    MARK_FILL = "#f6c1d0"
    MARK_LINE = "#e79ab3"

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.column() != 0 or not _is_female(index.data(Qt.UserRole + 1)):
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
        fm = QFontMetrics(opt.font)
        x = text_rect.left() + fm.horizontalAdvance(opt.text) + 6
        cy = text_rect.center().y()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(self.MARK_LINE), 1))
        painter.setBrush(QColor(self.MARK_FILL))
        painter.drawEllipse(QPointF(x + self.MARK_D / 2, cy), self.MARK_D / 2, self.MARK_D / 2)
        painter.restore()


class _ReassignDialog(QDialog):
    """[v38] 교사 강제 배정 — 짝이 안 맞거나(홀수 인원) 결석으로 팀을
    못 채운 학생을, 이미 만들어진 다른 팀에 추가로 넣는다. 그 팀은
    3인(또는 그 이상) 팀이 되고, 팀 전원이 경기 결과를 똑같이 받는다."""

    def __init__(self, event, roster, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.bracket.roster.reassign.title"))
        self.setMinimumWidth(340)
        self.event = event
        lay = QVBoxLayout(self)

        lay.addWidget(UK.hint_label(tr("util.bracket.roster.reassign.hint")))

        roster_by_sid = {s.sid: s for s in roster}

        lay.addWidget(UK.body_label(tr("util.bracket.roster.reassign.student")))
        self.combo_student = QComboBox()
        # [버그 수정] 예전엔 학급 전체 명단이 나와서 다른 반 학생까지
        # 골라졌다 — 이 라운드에서 팀을 못 이룬 학생(event.unassigned_sids)
        # 만 보여준다. 참가자로 뽑히지도 않은 학생은 애초에 여기 들어올
        # 이유가 없다.
        for sid in event.unassigned_sids:
            s = roster_by_sid.get(sid)
            if s is not None:
                self.combo_student.addItem(s.label(), s.sid)
        lay.addWidget(self.combo_student)

        lay.addWidget(UK.body_label(tr("util.bracket.roster.reassign.team")))
        self.combo_team = QComboBox()
        # [버그 수정] 팀 이름이 줄바꿈 있는 라벨(대진표 칸 안에서만 여러
        # 줄로 보이면 됨)을 그대로 썼더니 콤보 상자가 2줄로 잘려 보였다
        # — 여기서는 쉼표로 이어 한 줄로 보여준다.
        for entry_id, sids in event.entries.items():
            members = ", ".join(roster_by_sid[sid].label() for sid in sids if sid in roster_by_sid)
            self.combo_team.addItem(members or entry_id, entry_id)
        lay.addWidget(self.combo_team)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setEnabled(self.combo_student.count() > 0 and self.combo_team.count() > 0)

    def result(self):
        return self.combo_student.currentData(), self.combo_team.currentData()


class _AttendanceDialog(QDialog):
    """[v39] 오늘 출석 조정 — 팀별 학생을 체크박스로 보여주고(기본 전원
    출석), 결석 처리로 1명만 남는 팀이 생기면 그 자리에서 해결책을 고르게
    한다: (1) 3명 이상 출석한 팀에서 한 명 빌려오기, (2) 그 학생을 다른
    2인 팀에 임시로 합류시키기. 조정은 "오늘만" 적용된다.

    [버그 수정] 콤보 첫 항목이 실제 선택지(예: "OO 빌려오기")로 미리
    잡혀 있어서, 교사가 손도 안 대고 OK를 눌러도 그 선택이 그대로
    적용됐다 — 무엇을 고를지 직접 정하기 전에는 OK가 안 눌리도록
    "선택 안 함"을 기본값으로 넣고, 하나라도 안 정해지면 OK를 막는다.

    [v39] 팀 레벨 균형으로 만든 종목이면(event.level_balance), 빌려오기/
    합류 옵션 중 그 조합이 성립됐을 때 관련 팀 평균이 1.5~2.5를 벗어나는
    것은 아예 목록에서 뺀다 — 출석 조정 때문에 균형이 깨지지 않도록."""

    NONE_DATA = None

    def __init__(self, event, roster, rnd, event_index, date_str, tiers_by_sid=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.bracket.roster.att.title", a0=date_str))
        self.setMinimumWidth(420)
        self.event = event
        self.roster_by_sid = {s.sid: s for s in roster}
        self.team_size = event.team_size
        self.tiers_by_sid = tiers_by_sid or {}
        prev = rnd.adjustment_for(date_str, event_index) or {}
        prev_absent = set(prev.get("absent", []))
        self._prev_transfers = {t["from"]: t for t in prev.get("transfers", [])}

        lay = QVBoxLayout(self)
        lay.addWidget(UK.hint_label(tr("util.bracket.roster.att.hint")))

        self.checks = {}   # sid -> QCheckBox
        for entry_id, sids in event.entries.items():
            box = QFrame()
            box.setStyleSheet(f"QFrame{{border:1px solid {UK.CANVAS_BORDER};border-radius:4px;}}")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(8, 6, 8, 6)
            bl.setSpacing(2)
            row = QHBoxLayout()
            for sid in sids:
                st = self.roster_by_sid.get(sid)
                if st is None:
                    continue
                cb = QCheckBox(st.label())
                cb.setChecked(sid not in prev_absent)
                cb.stateChanged.connect(self._rebuild_fixes)
                self.checks[sid] = cb
                row.addWidget(cb)
            row.addStretch()
            bl.addLayout(row)
            lay.addWidget(box)

        self.lbl_fix_title = UK.body_label(tr("util.bracket.roster.att.fix_title"))
        lay.addWidget(self.lbl_fix_title)
        self.fix_holder = QWidget()
        self.fix_lay = QVBoxLayout(self.fix_holder)
        self.fix_lay.setContentsMargins(0, 0, 0, 0)
        self.fix_lay.setSpacing(4)
        lay.addWidget(self.fix_holder)
        self.fix_combos = {}   # lone entry_id -> QComboBox

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._rebuild_fixes()

    def _base_present(self):
        return {eid: [sid for sid in sids if self.checks.get(sid) is None or self.checks[sid].isChecked()]
                for eid, sids in self.event.entries.items()}

    def _present_with(self, exclude_eid=None):
        """체크 상태에, 지금 다른 콤보들이 고른 이동(exclude_eid의 콤보는
        빼고)까지 반영한 "지금 이대로 두면 각 팀에 몇 명이 남는가" 스냅숏.
        [버그 수정] 예전에는 콤보끼리 서로 몰라서, "혼자 남은 학생 둘을
        서로에게 보내는" 선택을 해도 상대방 쪽 콤보가 여전히 "선택 안
        함"으로 남아 OK가 영영 안 눌렸다 — 이제 콤보 하나를 정하면 그
        선택이 다른 콤보들의 현재 인원수 계산에도 반영되고, 그래서 상대
        팀이 0명이 되면 그 팀의 콤보 자체가 다음 재구성 때 사라진다."""
        present = self._base_present()
        for eid, combo in self.fix_combos.items():
            if eid == exclude_eid:
                continue
            data = combo.currentData()
            if not data:
                continue
            kind, sid, other = data
            if sid in present.get(other, []):
                present[other].remove(sid)
            if sid not in present.get(eid, []):
                present.setdefault(eid, []).append(sid)
        return present

    def _score(self, sid):
        return B.tier_score(self.tiers_by_sid.get(sid))

    def _avg_ok(self, sids):
        """team_size가 짝수 팀 기준일 때만 의미가 있으니, 인원이 있을
        때만 계산 — 빈 팀(0명)은 이 검사 대상이 아니다(그 팀은 이번
        조정으로 사라지는 쪽)."""
        if not sids:
            return True
        avg = sum(self._score(sid) for sid in sids) / len(sids)
        return B.LEVEL_MIN <= avg <= B.LEVEL_MAX

    def _rebuild_fixes(self, *_):
        if getattr(self, "_rebuilding", False):
            return   # 콤보를 다시 만드는 도중에 그 콤보의 선택이 또 신호를 내는 것 방지
        self._rebuilding = True
        try:
            prev_selection = {eid: combo.currentData() for eid, combo in self.fix_combos.items()}
            while self.fix_lay.count():
                it = self.fix_lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.deleteLater()
            self.fix_combos = {}
            base_present = self._base_present()
            base_lone = [eid for eid, sids in base_present.items() if len(sids) == 1] if self.team_size >= 2 else []
            level_balance = bool(self.event.level_balance and self.tiers_by_sid)

            for eid in base_lone:
                # 다른 콤보들이 이미 고른 선택을 반영했을 때도 여전히
                # 이 팀이 1명인지 다시 확인한다 — 다른 콤보가 이 학생을
                # 데려가기로 했다면(0명이 됨) 이 팀은 더 안 보여준다.
                present = self._present_with(exclude_eid=eid)
                if len(present.get(eid, [])) != 1:
                    continue
                lone_sid = present[eid][0]
                row = QHBoxLayout()
                row.addWidget(UK.body_label(tr("util.bracket.roster.att.lone",
                                               a0=self.roster_by_sid[lone_sid].label())))
                combo = QComboBox()
                combo.addItem(tr("util.bracket.roster.att.opt_none"), self.NONE_DATA)
                for other, sids in present.items():
                    if other == eid:
                        continue
                    # [버그 수정] 1명뿐인 다른 팀(=또 다른 혼자 남은 학생)도
                    # "빌려오기" 후보로 넣는다 — 두 학생이 서로 짝이 되는
                    # 가장 자연스러운 해결책인데 예전엔 이 경우가 빠져
                    # 있었다(3명 이상 있는 팀에서만 빌려올 수 있었다).
                    if len(sids) >= 3 or len(sids) == 1:
                        for sid in sids:
                            remaining = [x for x in sids if x != sid]
                            new_pair = [lone_sid, sid]
                            if level_balance and not (self._avg_ok(remaining) and self._avg_ok(new_pair)):
                                continue   # [v39] 이 조합은 어느 한쪽 팀 평균이 1.5~2.5를 벗어남 — 목록에서 뺌
                            combo.addItem(tr("util.bracket.roster.att.opt_borrow",
                                             a0=self.roster_by_sid[sid].label(),
                                             a1=", ".join(self.roster_by_sid[x].label() for x in sids if x != sid)
                                                 or tr("util.bracket.roster.att.opt_borrow_alone")),
                                          ("borrow", sid, other))
                for other, sids in present.items():
                    if other == eid or len(sids) != 2:
                        continue
                    if level_balance and not self._avg_ok(list(sids) + [lone_sid]):
                        continue   # [v39] 3인이 됐을 때 평균이 범위를 벗어남 — 목록에서 뺌
                    combo.addItem(tr("util.bracket.roster.att.opt_join",
                                     a0=", ".join(self.roster_by_sid[x].label() for x in sids)),
                                  ("join", lone_sid, other))
                restore = prev_selection.get(eid)
                if restore is None:
                    saved = self._prev_transfers.get(eid)
                    if saved is not None:
                        restore = ("join", lone_sid, saved["to"]) if saved.get("from") == eid else \
                                  ("borrow", saved["sid"], saved["from"])
                if restore is not None:
                    for k in range(combo.count()):
                        if combo.itemData(k) == restore:
                            combo.setCurrentIndex(k)
                            break
                combo.currentIndexChanged.connect(self._rebuild_fixes)
                row.addWidget(combo, 1)
                holder = QWidget()
                holder.setLayout(row)
                self.fix_lay.addWidget(holder)
                self.fix_combos[eid] = combo

            self.lbl_fix_title.setVisible(bool(self.fix_combos))
            self._update_ok_enabled()
        finally:
            self._rebuilding = False

    def _update_ok_enabled(self, *_):
        """혼자 남은 팀이 하나라도 있는데(다른 콤보에 흡수되지 않고
        여전히 자기 콤보가 떠 있는데) 그중 "선택 안 함"으로 남은 게
        있으면 OK를 막는다 — 교사가 직접 정하기 전엔 저장되지 않는다."""
        all_resolved = all(combo.currentData() is not None for combo in self.fix_combos.values())
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(all_resolved)

    def result(self):
        absent = [sid for sid, cb in self.checks.items() if not cb.isChecked()]
        transfers = []
        for lone_eid, combo in self.fix_combos.items():
            data = combo.currentData()
            if not data:
                continue
            kind, sid, other = data
            if kind == "borrow":
                transfers.append({"sid": sid, "from": other, "to": lone_eid})
            else:
                transfers.append({"sid": sid, "from": lone_eid, "to": other})
        return absent, transfers


class _MergeConflictDialog(QDialog):
    """[v38] 병합 중 같은 경기의 결과가 서로 다를 때, 어느 쪽을 남길지
    교사가 직접 고른다(자동으로 덮어쓰지 않는다)."""

    def __init__(self, conflict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.bracket.roster.merge.conflict_title"))
        self._choice = "local"
        lay = QVBoxLayout(self)
        lay.addWidget(UK.body_label(tr("util.bracket.roster.merge.conflict_label", a0=conflict["label"])))

        self.group, (self.radio_local, self.radio_other) = UK.radio_row(
            [tr("util.bracket.roster.merge.keep_local", a0=self._fmt(conflict["local"])),
             tr("util.bracket.roster.merge.keep_other", a0=self._fmt(conflict["other"]))],
            checked_index=0)
        lay.addWidget(self.radio_local)
        lay.addWidget(self.radio_other)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    @staticmethod
    def _fmt(side):
        sets = ", ".join(f"{a}:{b}" for a, b in side["sets"])
        return f"{side['winner']} ({sets})" if sets else side["winner"] or "?"

    def choice(self):
        return "other" if self.radio_other.isChecked() else "local"


class BracketWidget(QWidget):
    """대진표 작성기 — 학급 명단을 계속 유지하면서, 그날 수업에 참여하는
    학생만 골라 종목별 대진표(토너먼트)나 리그 일정을 만들고 경기 결과를
    기록한다.

    [설계 변경] 예전에는 "빠른 대진표"(참가자를 텍스트로 매번 새로
    입력)와 "학급 명단 기반"(참가자를 팝업창에서 고르는) 두 화면이
    있었는데, 실제로 체육 수업은 거의 항상 "그 시간에 있는 반의
    학생들만" 참여하므로, 명단은 한 번만 올려 두고 **매 수업마다
    참가자만 다시 고르는** 흐름이 훨씬 자연스럽다는 피드백을 받아
    하나로 합쳤다. 명단 올리기/지우기는 자주 쓰는 기능이 아니라
    좌측 맨 아래로 내렸다."""

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.roster = []            # list[B.Student] — 엑셀로 올린 학급 명단(계속 유지됨)
        self.events = []            # list[B.Event] — 지금 고른 시리즈의 모든 라운드를 평평하게 펼친 목록
        self._event_rounds = []     # events[i]가 속한 B.Round(같은 길이) — 삭제·라벨 갱신에 씀
        self.series = None          # [v38] 지금 다루는 시리즈(종목+반). None이면 아직 안 고름
        self._current_event = None
        self._history_path = None   # [신규] 누적 기록 엑셀 파일 경로(한 번 고르면 계속 기억)
        self._manual_tiers = {}     # [신규] {(종목, sid): 등급} — 교사가 직접 매긴 실력 등급(항상 우선)
        self._build_ui()
        self._load_settings()
        self.retranslate()

    # ---------------------------------------------------------------- 화면 구성
    def _build_ui(self):
        # ---- 왼쪽: 종목 설정 카드 + 명단 카드 (폭 고정) ----
        self.card_event = UK.Card()
        self.lbl_event_title = self.card_event.title_label
        self.lbl_event_name = UK.body_label()
        self.card_event.add_body(self.lbl_event_name)
        self.combo_sport = QComboBox()
        for sport in B.SPORT_OPTIONS:
            self.combo_sport.addItem(sport)
        self.combo_sport.currentIndexChanged.connect(self._on_sport_changed)
        self.card_event.add_body(self.combo_sport)
        self.edit_sport_other = QLineEdit()
        self.edit_sport_other.setVisible(False)
        self.edit_sport_other.textChanged.connect(self._update_event_name_preview)
        self.card_event.add_body(self.edit_sport_other)

        self.lbl_format = UK.body_label()
        self.card_event.add_body(self.lbl_format)
        self._format = B.FORMAT_LEAGUE   # [v38] 리그전을 먼저 쓰므로 기본값도 리그전
        self.format_group, (self.radio_format_league, self.radio_format_tournament) = UK.radio_row(
            ["", ""], checked_index=0)   # 문구는 retranslate에서(리그전, 토너먼트 순)
        self.radio_format_league.toggled.connect(
            lambda checked: self._set_format(B.FORMAT_LEAGUE) if checked else None)
        self.radio_format_tournament.toggled.connect(
            lambda checked: self._set_format(B.FORMAT_TOURNAMENT) if checked else None)
        self.card_event.add_body(UK.hrow(self.radio_format_league, self.radio_format_tournament,
                                         stretch_last=True))

        self.lbl_team_size = UK.body_label()
        self.spin_team_size = QSpinBox()
        self.spin_team_size.setRange(1, 15)
        self.spin_team_size.setValue(1)
        self.card_event.add_body(UK.hrow(self.lbl_team_size, self.spin_team_size, stretch_last=True))
        self.lbl_team_size_hint = UK.hint_label()
        self.card_event.add_body(self.lbl_team_size_hint)

        self.lbl_tier_mode = UK.body_label()
        self.combo_tier_mode = QComboBox()
        self.combo_tier_mode.addItem("")   # 0: 무작위 — 문구는 retranslate에서
        self.combo_tier_mode.addItem("")   # 1: 수준별 분리
        self.combo_tier_mode.addItem("")   # 2: 팀 레벨 평균
        self.combo_tier_mode.setCurrentIndex(2)   # [v39] 팀 레벨 평균을 기본값으로
        self.combo_tier_mode.currentIndexChanged.connect(
            lambda _i: self.lbl_tier_mode_hint.setText(self._tier_mode_hint_text()))
        self.card_event.add_body(UK.hrow(self.lbl_tier_mode, self.combo_tier_mode))
        self.lbl_tier_mode_hint = UK.hint_label()
        self.card_event.add_body(self.lbl_tier_mode_hint)

        self.lbl_participant_count = UK.hint_label()
        self.card_event.add_body(self.lbl_participant_count)
        self.lbl_name_preview_title = UK.hint_label()
        self.card_event.add_body(self.lbl_name_preview_title)
        self.lbl_name_preview = QLabel()
        self.lbl_name_preview.setWordWrap(True)
        self.lbl_name_preview.setStyleSheet(f"color:{C.UTIL_MAIN};font-weight:bold;background:transparent;")
        self.card_event.add_body(self.lbl_name_preview)
        self.card_event.body.addStretch(1)

        # [v39.2] "성적 산출"은 학기 말에 한 번 쓰는 기능이라, 매번 쓰는
        # 경기 결과 저장/합치기/생성 줄과 섞이지 않게 따로 한 줄을 쓴다.
        grades_row = QHBoxLayout()
        grades_row.addStretch()
        self.btn_export_grades = UK.secondary_button()
        self.btn_export_grades.clicked.connect(self._on_export_grades)
        grades_row.addWidget(self.btn_export_grades)
        self.card_event.add_body(grades_row)

        self.btn_save_to_excel = self.card_event.add_footer(UK.secondary_button())
        self.btn_save_to_excel.clicked.connect(self._on_save_to_excel)
        self.btn_merge_results = self.card_event.add_footer(UK.secondary_button())
        self.btn_merge_results.clicked.connect(self._on_merge_results)
        self.btn_generate = self.card_event.add_footer(UK.primary_button())
        self.btn_generate.clicked.connect(self._on_generate)

        # 명단 관리(자주 쓰지 않는 기능이라 별도 작은 카드로 아래에)
        self.card_roster = UK.Card()
        self.lbl_roster_title = self.card_roster.title_label
        self.lbl_roster_status = UK.hint_label()
        self.card_roster.add_body(self.lbl_roster_status)
        self.btn_roster_clear = self.card_roster.add_footer(UK.danger_button())
        self.btn_roster_clear.clicked.connect(self._on_roster_clear)
        self.btn_roster_upload = self.card_roster.add_footer(UK.secondary_button())
        self.btn_roster_upload.clicked.connect(self._on_roster_upload)

        left = UK.vstack(self.card_event, self.card_roster)
        left.setStretch(0, 1)

        # ---- 오른쪽 카드: 탭(참가자 선택 / 대진표) ----
        self.card_right = UK.Card()
        self.tabs = QTabWidget()
        self.card_right.add_body(self.tabs, 1)

        self.tab_participants = QWidget()
        self._build_participants_tab(self.tab_participants)
        self.tabs.addTab(self.tab_participants, "")

        self.tab_bracket = QWidget()
        self._build_bracket_tab(self.tab_bracket)
        self.tabs.addTab(self.tab_bracket, "")

        left_holder = QWidget()
        left_holder.setLayout(left)
        left_holder.setFixedWidth(UK.RIGHT_PANEL_W)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        root.addWidget(left_holder)
        root.addWidget(self.card_right, 1)

        self._update_format_buttons()
        self._update_roster_status()
        self._update_event_buttons()

    def _build_participants_tab(self, container):
        lay = QVBoxLayout(container)
        top_row = QHBoxLayout()
        self.lbl_participants_hint = QLabel()
        self.lbl_participants_hint.setWordWrap(True)
        self.lbl_participants_hint.setStyleSheet("color:#6b7280;font-size:11px;background:transparent;")
        top_row.addWidget(self.lbl_participants_hint, 1)
        self.btn_toggle_all_classes = UK.tool_button("▸")
        self.btn_toggle_all_classes.setCheckable(True)
        self.btn_toggle_all_classes.clicked.connect(self._on_toggle_all_classes)
        top_row.addWidget(self.btn_toggle_all_classes, 0, Qt.AlignTop)
        lay.addLayout(top_row)

        self.tree_participants = QTreeWidget()
        self.tree_participants.setColumnCount(4)
        self.tree_participants.setHeaderHidden(False)
        header = self.tree_participants.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree_participants.setItemDelegateForColumn(0, _GenderMarkDelegate(self.tree_participants))
        self.tree_participants.itemChanged.connect(self._on_participant_item_changed)
        self.tree_participants.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_participants.customContextMenuRequested.connect(self._on_participant_context_menu)
        lay.addWidget(self.tree_participants, 1)

    def _on_toggle_all_classes(self):
        if self.btn_toggle_all_classes.isChecked():
            self.tree_participants.expandAll()
            self.btn_toggle_all_classes.setText("▾")
        else:
            self.tree_participants.collapseAll()
            self.btn_toggle_all_classes.setText("▸")

    def _build_bracket_tab(self, container):
        lay = QVBoxLayout(container)

        series_row = QHBoxLayout()
        self.lbl_series = QLabel()
        series_row.addWidget(self.lbl_series)
        self.combo_series = QComboBox()
        self.combo_series.currentIndexChanged.connect(self._on_series_selected)
        series_row.addWidget(self.combo_series, 1)
        self.btn_series_refresh = UK.tool_button("↻")
        self.btn_series_refresh.setToolTip(tr("util.bracket.roster.series.refresh"))
        self.btn_series_refresh.clicked.connect(lambda: self._refresh_series_combo())
        series_row.addWidget(self.btn_series_refresh)
        lay.addLayout(series_row)

        history_row = QHBoxLayout()
        self.lbl_history = QLabel()
        history_row.addWidget(self.lbl_history)
        self.combo_event = QComboBox()
        self.combo_event.currentIndexChanged.connect(self._on_event_selected)
        history_row.addWidget(self.combo_event, 1)
        self.btn_attendance = UK.secondary_button()
        self.btn_attendance.clicked.connect(self._on_attendance)
        history_row.addWidget(self.btn_attendance)
        self.btn_reassign = UK.secondary_button()
        self.btn_reassign.clicked.connect(self._on_reassign_student)
        history_row.addWidget(self.btn_reassign)
        self.btn_event_delete = UK.danger_button()
        self.btn_event_delete.clicked.connect(self._on_event_delete)
        history_row.addWidget(self.btn_event_delete)
        lay.addLayout(history_row)

        self.roster_result_scroll = QScrollArea()
        self.roster_result_scroll.setWidgetResizable(False)
        self.roster_result_scroll.setStyleSheet(f"QScrollArea{{border:1px solid {UK.CANVAS_BORDER};border-radius:4px;background:#ffffff;}}")
        self.roster_bracket_canvas = _BracketCanvas()
        self.roster_bracket_canvas.matchClicked.connect(self._on_roster_match_clicked)
        self.roster_result_scroll.setWidget(self.roster_bracket_canvas)
        lay.addWidget(self.roster_result_scroll, 1)

        self.league_view = _LeagueView()
        self.league_view.matchClicked.connect(self._on_league_match_clicked)
        self.league_view.setVisible(False)
        lay.addWidget(self.league_view, 1)

    # ---------------------------------------------------------------- 형식
    def _set_format(self, fmt):
        self._format = fmt
        self._update_format_buttons()
        self._update_event_name_preview()

    def _update_format_buttons(self):
        self.radio_format_league.setChecked(self._format == B.FORMAT_LEAGUE)
        self.radio_format_tournament.setChecked(self._format == B.FORMAT_TOURNAMENT)

    def _on_sport_changed(self, idx):
        is_other = (self.combo_sport.currentText() == B.SPORT_OTHER)
        self.edit_sport_other.setVisible(is_other)
        self._update_event_name_preview()
        self._refresh_participant_labels()

    def _current_sport_name(self):
        if self.combo_sport.currentText() == B.SPORT_OTHER:
            return self.edit_sport_other.text().strip() or B.SPORT_OTHER
        return self.combo_sport.currentText()

    def _update_event_name_preview(self):
        """[신규] 종목·형식·참가 학급·오늘 날짜를 조합해 종목 이름을
        자동으로 만들어 미리 보여준다(예: 배드민턴_1,2반_리그전_20260918).
        선생님이 따로 이름을 입력할 필요가 없다."""
        students = self._selected_students()
        if not students:
            self.lbl_name_preview.setText(tr("util.bracket.roster.name_preview_empty"))
            return
        name = B.build_event_name(self._current_sport_name(), students, self._format)
        self.lbl_name_preview.setText(name)

    # ---------------------------------------------------------------- 참가자 선택(탭1)
    def _populate_participant_tree(self):
        self.tree_participants.blockSignals(True)
        self.tree_participants.clear()
        by_class = {}
        for s in self.roster:
            by_class.setdefault((s.grade, s.cls), []).append(s)

        def _part_key(v):
            try:
                return (0, int(v))
            except (TypeError, ValueError):
                return (1, v)

        for grade, cls in sorted(by_class.keys(), key=lambda gc: (_part_key(gc[0]), _part_key(gc[1]))):
            students = by_class[(grade, cls)]
            class_item = QTreeWidgetItem(
                [tr("util.bracket.roster.class_label", a0=grade, a1=cls, a2=len(students)), "", "", ""])
            class_item.setFlags(class_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            class_item.setCheckState(0, Qt.Unchecked)
            for s in students:
                child = QTreeWidgetItem([s.label(), "", "", ""])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, Qt.UserRole, s.sid)
                child.setData(0, Qt.UserRole + 1, s.gender)   # [v39] 여학생 표시용
                for col in (1, 2, 3):
                    child.setTextAlignment(col, Qt.AlignCenter)
                class_item.addChild(child)
            self.tree_participants.addTopLevelItem(class_item)
        # [v38] 기본은 접힘 — 반이 많으면 화면을 다 채워버려서 답답하다는
        # 지적이 있었다. 펼치고 싶으면 위쪽 ▸ 버튼으로 한 번에 전부 켠다.
        if self.btn_toggle_all_classes.isChecked():
            self.tree_participants.expandAll()
        self.tree_participants.blockSignals(False)
        self._update_participant_count()
        self._refresh_participant_labels()

    def _refresh_participant_labels(self):
        """[신규→표 형태] 누적 기록에서 지금 고른 종목의 학생별 승패·
        자동 등급·교사 등급을 **각각 다른 열**에 보여준다(이름/승패/
        자동등급/교사등급). 체크 상태는 그대로 두고 글자만 바꾼다.
        실제로 대진표를 짤 때 쓰는 등급(교사 등급이 있으면 그것, 없으면
        자동 등급)에 따라 그 줄 전체를 금색(상)·은색(중)으로 옅게
        칠한다(하는 지금처럼 색을 안 칠함) — 등급을 매기거나 지우려면
        학생을 오른쪽 클릭한다.

        [성능] sid로 학생을 찾을 때 예전에는 명단을 매번 처음부터 끝까지
        훑었다(항목 수 × 명단 크기) — 명단이 큰 학교(전교생 단위)에서는
        이 한 함수 때문에 화면이 몇 초씩 멈춘 원인이었다. 미리
        {sid: 학생} 딕셔너리 하나만 만들어 두면 항목마다 바로 찾아진다.
        """
        sport = self._current_sport_name()
        stats = B.read_history_stats(self._history_path, sport=sport) if self._history_path else {}
        roster_by_sid = {s.sid: s for s in self.roster}
        root_item = self.tree_participants.invisibleRootItem()
        # [성능] setBackground()도 QTreeWidgetItem에서는 itemChanged를 낸다.
        # 그 핸들러(_on_participant_item_changed)가 참가자 수를 다시 세느라
        # 트리 전체를 훑기 때문에, 막지 않으면 "칸 수 × 칸 수"만큼 반복된다
        # (명단이 큰 학교에서 이 함수 하나가 화면을 몇 초씩 멈추게 한
        # 실제 원인이었다). 여기서 만드는 배경색 변경은 사용자 조작이
        # 아니므로 신호를 막아도 안전하고, 끝나고 한 번만 다시 센다.
        self.tree_participants.blockSignals(True)
        for i in range(root_item.childCount()):
            class_item = root_item.child(i)
            for j in range(class_item.childCount()):
                child = class_item.child(j)
                sid = child.data(0, Qt.UserRole)
                student = roster_by_sid.get(sid)
                if student is None:
                    continue
                child.setText(0, student.label())
                entry = stats.get((student.grade, student.cls, student.num, student.name))
                auto_tier = None
                if entry and (entry["wins"] or entry["losses"]):
                    child.setText(1, tr("util.bracket.roster.wl_cell", a0=entry["wins"], a1=entry["losses"]))
                    auto_tier = B.compute_auto_tier(entry["wins"], entry["losses"])
                else:
                    child.setText(1, "")
                child.setText(2, auto_tier or "")
                manual_tier = self._manual_tiers.get((sport, sid))
                child.setText(3, manual_tier or "")
                _set_row_tier_color(child, B.effective_tier(manual_tier, auto_tier))
        self.tree_participants.blockSignals(False)
        self._update_participant_count()

    def _on_participant_context_menu(self, pos):
        """[신규] 참가자(학생)를 오른쪽 클릭하면 실력 등급을 매기거나
        지울 수 있다. 여기서 매긴 등급(수동)은 승률로 추정한 자동
        등급보다 항상 우선한다."""
        item = self.tree_participants.itemAt(pos)
        if item is None or item.parent() is None:
            return   # 반 항목(최상위)이 아니라 학생(자식)만 대상
        sid = item.data(0, Qt.UserRole)
        if sid is None:
            return
        sport = self._current_sport_name()
        current_manual = self._manual_tiers.get((sport, sid))
        menu = QMenu(self)
        tier_actions = {}
        for tier in B.TIER_ORDER:
            text = tr("util.bracket.roster.tier_menu_set", a0=tier)
            if current_manual == tier:
                text += " ✓"
            tier_actions[menu.addAction(text)] = tier
        menu.addSeparator()
        act_clear = menu.addAction(tr("util.bracket.roster.tier_menu_clear"))
        act_clear.setEnabled(current_manual is not None)
        chosen = menu.exec(self.tree_participants.mapToGlobal(pos))
        if chosen in tier_actions:
            self._manual_tiers[(sport, sid)] = tier_actions[chosen]
        elif chosen == act_clear:
            self._manual_tiers.pop((sport, sid), None)
        else:
            return
        self._save_settings()
        self._refresh_participant_labels()

    def _on_participant_item_changed(self, item, column):
        self._update_participant_count()
        self._update_event_name_preview()

    def _selected_students(self):
        sids = set()
        root_item = self.tree_participants.invisibleRootItem()
        for i in range(root_item.childCount()):
            class_item = root_item.child(i)
            for j in range(class_item.childCount()):
                child = class_item.child(j)
                if child.checkState(0) == Qt.Checked:
                    sids.add(child.data(0, Qt.UserRole))
        return [s for s in self.roster if s.sid in sids]

    def _update_participant_count(self):
        n = len(self._selected_students())
        self.lbl_participant_count.setText(tr("util.bracket.roster.participant_count", a0=n))

    # ---------------------------------------------------------------- 생성
    def _on_generate(self):
        students = self._selected_students()
        if len(students) < 2:
            QMessageBox.information(self, tr("util.bracket.roster.generate_title"),
                                   tr("util.bracket.roster.need_more_participants"))
            return
        sport = self._current_sport_name()
        team_size = self.spin_team_size.value()

        # [v38] 시리즈(종목+반) 결정 — 이 참가자들로 이어갈 시리즈를 찾거나
        # 새로 만든다. 파트너 반복 회피는 이제 엑셀이 아니라 **이 시리즈의
        # 모든 이전 라운드**를 본다(저장 여부와 무관하게 항상 정확하다).
        key = B.series_key(sport, students)
        if self.series is None or self.series.key != key:
            path = B.series_file_path(self._history_path, key) if self._history_path else None
            loaded = B.load_series(path) if path else None
            self.series = loaded or B.Series(key, sport, B.classes_label(students))

        # [v38.1] 이전 라운드가 아직 안 끝났으면 새 라운드를 못 만들게
        # 막는다 — "모든 이전 라운드의 결과가 기록돼야 다음 라운드로
        # 넘어갈 수 있다"는 규칙을 여기서 강제한다.
        unfinished = [i + 1 for i, r in enumerate(self.series.rounds) if not r.is_completed()]
        if unfinished:
            QMessageBox.information(
                self, tr("util.bracket.roster.generate_title"),
                tr("util.bracket.roster.round_not_finished",
                   a0=", ".join(str(n) for n in unfinished)))
            return

        roster_by_sid = {s.sid: s for s in self.roster}
        partnership_counts = self.series.partnership_counts(roster_by_sid)

        before = len(self.events)
        _mode = self.combo_tier_mode.currentIndex()
        if _mode == 1:
            self._generate_tier_split_events(students, sport, team_size, partnership_counts)
        elif _mode == 2:
            tiers_by_sid = self._compute_tiers_by_sid(students, sport)
            self._generate_single_event(students, sport, team_size, partnership_counts,
                                        level_balance=True, tiers_by_sid=tiers_by_sid)
        else:
            self._generate_single_event(students, sport, team_size, partnership_counts)
        new_events = self.events[before:]
        if not new_events:
            return

        new_round = B.Round(new_events)
        self.series.rounds.append(new_round)
        self._save_series_file()
        self._save_settings()
        self._sync_events_from_series()
        self._refresh_series_combo(select_key=self.series.key)
        self._check_uneven_teams(new_events, team_size)

    def _check_uneven_teams(self, events, team_size):
        """[v38] 인원이 team_size로 안 나누어떨어지면 몇 명이 팀을 못
        이룬 채로 남는다(결석·홀수 인원 등) — build_event가 이미 이
        학생들을 대진표에 안 넣고 event.unassigned_sids로 빼 뒀으니,
        여기서는 이름을 모아 안내만 한다."""
        if team_size <= 1:
            return
        roster_by_sid = {s.sid: s for s in self.roster}
        names = []
        for ev in events:
            for sid in ev.unassigned_sids:
                s = roster_by_sid.get(sid)
                if s:
                    names.append(s.label())
        if names:
            QMessageBox.information(
                self, tr("util.bracket.roster.generate_title"),
                tr("util.bracket.roster.uneven_team_hint", a0=", ".join(names)))

    def _compute_tiers_by_sid(self, students, sport):
        """[v39] 학생별 "실제로 쓸" 등급 — 교사 등급이 있으면 그것, 없으면
        누적 승률로 추정한 자동 등급. 수준별 분리·팀 레벨 평균 두 모드가
        똑같이 이 계산을 쓴다."""
        tiers_by_sid = {}
        stats = B.read_history_stats(self._history_path, sport=sport) if self._history_path else {}
        for s in students:
            manual = self._manual_tiers.get((sport, s.sid))
            auto = None
            entry = stats.get((s.grade, s.cls, s.num, s.name))
            if entry:
                auto = B.compute_auto_tier(entry["wins"], entry["losses"])
            tiers_by_sid[s.sid] = B.effective_tier(manual, auto)
        return tiers_by_sid

    def _tier_mode_hint_text(self):
        idx = self.combo_tier_mode.currentIndex()
        if idx == 1:
            return tr("util.bracket.roster.tier_mode_hint")
        if idx == 2:
            return tr("util.bracket.roster.tier_mode.level_hint")
        return tr("util.bracket.roster.tier_mode.random_hint")

    def _on_export_grades(self):
        if self.series is None or not self.series.rounds:
            QMessageBox.information(self, tr("util.bracket.roster.btn.export_grades"),
                                   tr("util.bracket.roster.grades.none"))
            return
        roster_by_sid = {s.sid: s for s in self.roster}
        rows = B.compute_series_grade_stats(self.series, roster_by_sid)
        if not rows:
            QMessageBox.information(self, tr("util.bracket.roster.btn.export_grades"),
                                   tr("util.bracket.roster.grades.none"))
            return
        default_name = f"성적_{self.series.key}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.bracket.roster.btn.export_grades"), default_name, "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            B.save_grade_stats_excel(path, rows, sport=self.series.sport, series_label=self.series.class_label)
        except OSError as e:
            QMessageBox.warning(self, tr("util.bracket.roster.btn.export_grades"),
                               tr("util.bracket.roster.grades.save_fail", a0=str(e)))
            return
        if self.host:
            self.host.status(tr("util.bracket.roster.grades.saved_status", a0=len(rows), a1=path))
            self.host.log(tr("util.bracket.roster.grades.saved_status", a0=len(rows), a1=path))

    def _generate_single_event(self, students, sport, team_size, partnership_counts,
                               level_balance=False, tiers_by_sid=None):
        name = B.build_event_name(sport, students, self._format)
        event = B.build_event(name, students, format=self._format, team_size=team_size, sport=sport,
                              partnership_counts=partnership_counts,
                              level_balance=level_balance, tiers_by_sid=tiers_by_sid)
        self.events.append(event)
        self.tabs.setCurrentWidget(self.tab_bracket)
        if self.host:
            self.host.log(tr("util.bracket.log.event_created", a0=name, a1=len(students)))

    def _generate_tier_split_events(self, students, sport, team_size, partnership_counts):
        """[신규] "수준별 분리" — 선택한 참가자를 실력 등급(상/중/하)별로
        나눠, 등급마다 독립된 종목(대진표)을 따로 만든다. 인원이 2명
        미만인 등급은 대진표를 만들 수 없으니 건너뛰고, 어느 등급이
        빠졌는지 안내한다(교사가 그 학생의 등급을 조정하거나, 대진표
        탭에서 부전승 자리를 직접 채워 줄 수 있다)."""
        tiers_by_sid = self._compute_tiers_by_sid(students, sport)
        groups = B.split_by_tier(students, tiers_by_sid)

        created, skipped = [], []
        for tier in B.TIER_ORDER:
            group_students = groups.get(tier, [])
            if len(group_students) < 2:
                if group_students:
                    skipped.append((tier, group_students))
                continue
            name = B.build_event_name(f"{sport}({tier})", group_students, self._format)
            event = B.build_event(name, group_students, format=self._format, team_size=team_size,
                                  sport=sport, partnership_counts=partnership_counts)
            self.events.append(event)
            created.append(event)

        if not created:
            QMessageBox.information(self, tr("util.bracket.roster.generate_title"),
                                   tr("util.bracket.roster.tier_split_none"))
            return
        self.tabs.setCurrentWidget(self.tab_bracket)
        if self.host:
            for event in created:
                self.host.log(tr("util.bracket.log.event_created", a0=event.name,
                                a1=sum(len(ids) for ids in event.entries.values())))
        if skipped:
            names = ", ".join(f"{tier}({len(ss)}명: {', '.join(s.name for s in ss)})" for tier, ss in skipped)
            QMessageBox.information(self, tr("util.bracket.roster.generate_title"),
                                   tr("util.bracket.roster.tier_split_skipped", a0=names))

    def _on_event_delete(self):
        idx = self.combo_event.currentIndex()
        if idx < 0 or idx >= len(self.events):
            return
        reply = QMessageBox.question(
            self, tr("util.bracket.roster.delete_event_title"), tr("util.bracket.roster.delete_event_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        ev = self.events[idx]
        rnd = self._event_rounds[idx] if idx < len(self._event_rounds) else None
        if rnd is not None and self.series is not None:
            if ev in rnd.events:
                rnd.events.remove(ev)
            if not rnd.events and rnd in self.series.rounds:
                self.series.rounds.remove(rnd)
            self._save_series_file()
        self._sync_events_from_series()
        self._update_event_buttons()

    # ---------------------------------------------------------------- [v38] 시리즈·라운드
    def _save_series_file(self):
        """지금 다루는 시리즈를 누적 엑셀과 같은 폴더에 JSON으로 저장한다.
        경기 결과를 기록할 때마다 자동으로 불리므로, 수업이 한 교시에
        안 끝나도 진행 중인 라운드가 그대로 남는다 — 다음 시간에 같은
        시리즈를 고르면 이어서 기록할 수 있다."""
        if not self.series or not self._history_path:
            return
        path = B.series_file_path(self._history_path, self.series.key)
        try:
            B.save_series(path, self.series)
        except OSError:
            return
        self._refresh_series_combo(select_key=self.series.key)

    def _refresh_series_combo(self, select_key=None):
        if select_key is None and self.combo_series.currentIndex() >= 0:
            select_key = self.combo_series.currentData()
        self.combo_series.blockSignals(True)
        self.combo_series.clear()
        keys = [k for k, _p in B.list_series_files(self._history_path)] if self._history_path else []
        if self.series and self.series.key not in keys:
            keys.append(self.series.key)   # 아직 파일로 저장 안 된(엑셀 경로 미지정) 시리즈도 목록엔 보이게
        for key in sorted(keys):
            self.combo_series.addItem(key, key)
        self.combo_series.blockSignals(False)
        if select_key:
            idx = self.combo_series.findData(select_key)
            if idx >= 0:
                self.combo_series.setCurrentIndex(idx)
                self._on_series_selected(idx)
                return
        # [버그 수정] QComboBox는 첫 항목을 addItem()하는 순간 currentIndex가
        # 0으로 자동으로 잡힌다(신호를 막아 놨어도 인덱스 자체는 바뀐다) —
        # 그래서 아래 "< 0"만 보고 다시 선택하려던 기존 코드는 신호가 한
        # 번도 안 불려 self.series가 계속 None으로 남는 문제가 있었다.
        # 조건 없이 지금 인덱스를 그대로 한 번 더 통보한다.
        if self.combo_series.count():
            self._on_series_selected(max(0, self.combo_series.currentIndex()))
        else:
            self._on_series_selected(-1)

    def _on_series_selected(self, idx):
        key = self.combo_series.itemData(idx) if idx >= 0 else None
        if not key:
            self.series = None
            self._sync_events_from_series()
            return
        if self.series is None or self.series.key != key:
            path = B.series_file_path(self._history_path, key) if self._history_path else None
            loaded = B.load_series(path) if path else None
            self.series = loaded or B.Series(key, "", "")
        self._sync_events_from_series()
        self._save_settings()

    def _round_item_label(self, round_index, rnd, ev):
        done, total = rnd.progress()
        status = (tr("util.bracket.roster.round_done") if rnd.is_completed()
                 else tr("util.bracket.roster.round_progress", a0=done, a1=total))
        return tr("util.bracket.roster.round_item", a0=round_index, a1=ev.name, a2=status)

    def _sync_events_from_series(self):
        """self.series.rounds를 평평하게 펼쳐 combo_event/self.events를
        다시 채운다 — 항상 이 함수가 그 둘의 유일한 출처다."""
        self.combo_event.blockSignals(True)
        self.combo_event.clear()
        self.events = []
        self._event_rounds = []
        if self.series:
            for ridx, rnd in enumerate(self.series.rounds, start=1):
                for ev in rnd.events:
                    self.events.append(ev)
                    self._event_rounds.append(rnd)
                    self.combo_event.addItem(self._round_item_label(ridx, rnd, ev))
        self.combo_event.blockSignals(False)
        if self.events:
            last = len(self.events) - 1
            self.combo_event.setCurrentIndex(last)
            self._on_event_selected(last)
        else:
            self._on_event_selected(-1)
        self._update_event_buttons()

    def _update_current_round_label(self):
        idx = self.combo_event.currentIndex()
        if 0 <= idx < len(self._event_rounds):
            rnd = self._event_rounds[idx]
            ridx = self.series.rounds.index(rnd) + 1 if self.series and rnd in self.series.rounds else 1
            self.combo_event.setItemText(idx, self._round_item_label(ridx, rnd, self.events[idx]))

    # ---------------------------------------------------------------- [v38] 교사 강제 배정
    def _on_reassign_student(self):
        if self._current_event is None:
            QMessageBox.information(self, tr("util.bracket.roster.reassign.title"),
                                   tr("util.bracket.roster.need_more_participants"))
            return
        event = self._current_event
        if not event.unassigned_sids:
            QMessageBox.information(self, tr("util.bracket.roster.reassign.title"),
                                   tr("util.bracket.roster.reassign.none_left"))
            return
        dlg = _ReassignDialog(event, self.roster, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        sid, entry_id = dlg.result()
        if not sid or not entry_id:
            return

        # [버그 수정] 팀을 못 이룬 목록에서 빼는 걸 빼먹어서, 다른 팀에
        # 넣은 뒤에도 원래의 "혼자만의 팀" 기록이 대진표에 그대로 남아
        # 있었다. 이제는 unassigned_sids에서만 온전히 빼면 된다(원래
        # 대진표에 들어간 적이 없는 학생이라 지울 레코드도 없다).
        if sid in event.unassigned_sids:
            event.unassigned_sids.remove(sid)
        event.entries.setdefault(entry_id, [])
        if sid not in event.entries[entry_id]:
            event.entries[entry_id].append(sid)
        roster_by_sid = {s.sid: s for s in self.roster}
        label = "\n".join(roster_by_sid[i].label() for i in event.entries[entry_id] if i in roster_by_sid)
        event.bracket.entries[entry_id] = label
        self._save_series_file()
        self._on_event_selected(self.combo_event.currentIndex())
        self._update_event_buttons()
        if self.host:
            self.host.log(tr("util.bracket.log.reassigned", a0=roster_by_sid[sid].name, a1=label))

    def _entry_tiers_for_event(self, event):
        """[신규] 이 종목(event)에 속한 각 참가자(entry)의 실력 등급을
        계산한다 — 그 편의 학생들이 전부 같은(유효) 등급이면 그 등급,
        섞여 있거나 모르면 None(색 안 칠함). 대진표·리그 화면에서 등급
        색으로 참가자 칸을 칠할 때 쓴다."""
        roster_by_sid = {s.sid: s for s in self.roster}
        stats = B.read_history_stats(self._history_path, sport=event.sport) if self._history_path else {}
        result = {}
        for entry_id, sids in event.entries.items():
            tiers = set()
            for sid in sids:
                manual = self._manual_tiers.get((event.sport, sid))
                auto = None
                s = roster_by_sid.get(sid)
                if s and not manual:
                    entry = stats.get((s.grade, s.cls, s.num, s.name))
                    if entry:
                        auto = B.compute_auto_tier(entry["wins"], entry["losses"])
                tiers.add(B.effective_tier(manual, auto))
            result[entry_id] = next(iter(tiers)) if len(tiers) == 1 else None
        return result

    def _on_event_selected(self, idx):
        if idx < 0 or idx >= len(self.events):
            self._current_event = None
            self.roster_result_scroll.setVisible(True)
            self.league_view.setVisible(False)
            self.roster_bracket_canvas.set_event_bracket(B.Bracket({}))
            return
        self._current_event = self.events[idx]
        tiers = self._entry_tiers_for_event(self._current_event)
        display = self._entry_display(self._current_event)
        overrides = {eid: text for eid, (text, _g) in display.items()}
        genders = {eid: g for eid, (_t, g) in display.items()}
        if self._current_event.format == B.FORMAT_LEAGUE:
            self.roster_result_scroll.setVisible(False)
            self.league_view.setVisible(True)
            self.league_view.set_league(self._current_event.bracket, entry_tiers=tiers,
                                        label_overrides=overrides, label_genders=genders)
        else:
            self.league_view.setVisible(False)
            self.roster_result_scroll.setVisible(True)
            self.roster_bracket_canvas.set_event_bracket(self._current_event.bracket, entry_tiers=tiers,
                                                         label_overrides=overrides, label_genders=genders)
        self._update_event_buttons()

    # ---------------------------------------------------------------- [v39] 오늘 출석 조정
    @staticmethod
    def _today_str():
        return _dt.date.today().strftime("%Y%m%d")

    def _round_and_index_of(self, event):
        """event가 속한 (Round, 그 라운드 안 인덱스). 없으면 (None, 0)."""
        for idx, ev in enumerate(self.events):
            if ev is event:
                rnd = self._event_rounds[idx] if idx < len(self._event_rounds) else None
                if rnd is not None and event in rnd.events:
                    return rnd, rnd.events.index(event)
                return rnd, 0
        return None, 0

    def _effective_members(self, event):
        rnd, ei = self._round_and_index_of(event)
        return B.effective_members(event, rnd, self._today_str(), ei)

    def _entry_display(self, event):
        """entry_id -> (표시용 라벨 텍스트, [그 줄이 여학생인지, ...]).
        오늘 출석 조정(결석 '✕결석', 임시 합류 '(임시)')을 반영한다 —
        조정이 없으면 기본 팀원 그대로. 대진표·리그 표·점수 입력 팝업이
        전부 이 함수 하나로 라벨과 성별 표시를 함께 얻는다(따로따로
        계산하면 화면마다 반영 시점이 어긋나기 쉽다 — 실제로 그래서
        생겼던 버그를 여기서 하나로 합쳐 없앴다)."""
        roster_by_sid = {s.sid: s for s in self.roster}
        rnd, ei = self._round_and_index_of(event)
        adj = rnd.adjustment_for(self._today_str(), ei) if rnd is not None else None
        absent = set(adj.get("absent", [])) if adj else set()
        joined = {t["sid"]: t["to"] for t in adj.get("transfers", [])} if adj else {}
        eff = (B.effective_members(event, rnd, self._today_str(), ei) if rnd is not None
              else {eid: list(sids) for eid, sids in event.entries.items()})
        result = {}
        for entry_id, base_sids in event.entries.items():
            lines, genders = [], []
            for sid in base_sids:
                st = roster_by_sid.get(sid)
                if st is None:
                    continue
                if sid in absent:
                    lines.append(tr("util.bracket.roster.att.absent_mark", a0=st.label()))
                    genders.append(_is_female(st.gender))
                elif joined.get(sid) not in (None, entry_id):
                    continue   # 오늘 다른 팀으로 갔음 — 이 팀 라벨에서는 뺀다
                else:
                    lines.append(st.label())
                    genders.append(_is_female(st.gender))
            for sid in eff.get(entry_id, []):
                if sid not in base_sids and sid in roster_by_sid:
                    st = roster_by_sid[sid]
                    lines.append(tr("util.bracket.roster.att.temp_mark", a0=st.label()))
                    genders.append(_is_female(st.gender))
            result[entry_id] = ("\n".join(lines), genders)
        return result

    def _effective_labels(self, event):
        """오늘 출석 조정을 반영한 표시 라벨만 필요할 때(점수 입력 팝업 등)."""
        return {eid: text for eid, (text, _genders) in self._entry_display(event).items()}

    def _entry_genders(self, event):
        """entry_id -> [그 줄이 여학생인지, ...] — 대진표·리그 표에 분홍
        점을 찍을 때 쓴다."""
        return {eid: genders for eid, (_text, genders) in self._entry_display(event).items()}

    def _on_attendance(self):
        if self._current_event is None:
            return
        event = self._current_event
        rnd, ei = self._round_and_index_of(event)
        if rnd is None:
            return
        tiers_by_sid = self._compute_tiers_by_sid(self.roster, event.sport) if event.level_balance else {}
        dlg = _AttendanceDialog(event, self.roster, rnd, ei, self._today_str(),
                               tiers_by_sid=tiers_by_sid, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        absent, transfers = dlg.result()
        rnd.set_adjustment(self._today_str(), ei, absent, transfers)
        self._save_series_file()
        self._on_event_selected(self.combo_event.currentIndex())
        if self.host:
            self.host.log(tr("util.bracket.log.attendance", a0=len(absent), a1=len(transfers)))

    def _update_event_buttons(self):
        self.btn_event_delete.setEnabled(len(self.events) > 0)
        self.btn_save_to_excel.setEnabled(len(self.events) > 0)
        self.btn_reassign.setEnabled(bool(self._current_event and self._current_event.unassigned_sids))
        self.btn_attendance.setEnabled(self._current_event is not None)
        self.btn_export_grades.setEnabled(bool(self.series and self.series.rounds))

    # ---------------------------------------------------------------- 결과 기록
    def _record_via_dialog(self, bracket_or_league, r, i):
        m = bracket_or_league.rounds[r][i]
        if m.a is None or m.b is None:
            return
        ov = self._effective_labels(self._current_event)
        label_a = ov.get(m.a, bracket_or_league.label(m.a))
        label_b = ov.get(m.b, bracket_or_league.label(m.b))
        dlg = _RecordResultDialog(label_a, label_b, current_sets=m.sets, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        if dlg.is_cleared():
            bracket_or_league.clear_result(r, i)
        else:
            winner, sets, note = dlg.result()
            if winner is None:
                QMessageBox.information(self, tr("util.bracket.roster.record.title"),
                                       tr("util.bracket.roster.record.need_scores"))
                return
            bracket_or_league.record(r, i, winner, note, sets=sets)
            # [v39] 실제 출전자 스냅숏 — 오늘 결석·임시 편성이 반영된 구성을
            # 경기 안에 박아 둔다(이후 조정이 바뀌어도 이 경기는 그대로).
            eff = self._effective_members(self._current_event)
            m.side_sids = {"a": list(eff.get(m.a, [])), "b": list(eff.get(m.b, []))}
        self._save_settings()
        self._save_series_file()
        self._update_current_round_label()
        if self.host:
            self.host.log(tr("util.bracket.log.result_recorded", a0=self._current_event.name))

    def _on_roster_match_clicked(self, r, i):
        if self._current_event is None:
            return
        self._record_via_dialog(self._current_event.bracket, r, i)
        # [버그 수정] 여기서 다시 그릴 때 오늘 출석 조정 라벨(결석·임시
        # 합류 표시)을 안 넘겨서, 점수 팝업을 한 번 열었다 닫기만 해도
        # 조정 표시가 사라져 버렸다 — _on_event_selected와 똑같이
        # _entry_display()로 라벨·성별을 같이 넘긴다.
        display = self._entry_display(self._current_event)
        self.roster_bracket_canvas.set_event_bracket(
            self._current_event.bracket, entry_tiers=self._entry_tiers_for_event(self._current_event),
            label_overrides={eid: t for eid, (t, _g) in display.items()},
            label_genders={eid: g for eid, (_t, g) in display.items()})

    def _on_league_match_clicked(self, r, i):
        if self._current_event is None:
            return
        self._record_via_dialog(self._current_event.bracket, r, i)
        display = self._entry_display(self._current_event)   # [버그 수정] 위와 동일
        self.league_view.set_league(
            self._current_event.bracket, entry_tiers=self._entry_tiers_for_event(self._current_event),
            label_overrides={eid: t for eid, (t, _g) in display.items()},
            label_genders={eid: g for eid, (_t, g) in display.items()})

    def _resolve_history_path(self):
        """누적 기록 파일 위치를 정한다. 예전에 고른 적이 있고 그 파일이
        아직 있으면 다시 안 물어보고 그대로 쓴다(계속 이어서 기록) —
        없거나 처음이면 골라 달라고 한다(기존 파일을 고르면 그 뒤에
        이어서 적고, 새 파일명을 적으면 새로 시작한다)."""
        if self._history_path and os.path.exists(self._history_path):
            return self._history_path
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.bracket.roster.history.pick_title"), "대진표_누적기록.xlsx", "Excel (*.xlsx)")
        if not path:
            return None
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        self._history_path = path
        self._save_settings()
        return path

    def _on_save_to_excel(self):
        if self._current_event is None:
            return
        path = self._resolve_history_path()
        if not path:
            return
        event = self._current_event
        roster_by_sid = {s.sid: s for s in self.roster}
        date_str = _dt.date.today().strftime("%Y%m%d")
        rows = []
        newly_saved = []
        for matches in event.bracket.rounds:
            for m in matches:
                if m.winner is None or m.saved:
                    continue
                # [v39] 실제 출전자 스냅숏이 있으면 그것을(결석자 제외·임시
                # 합류자 포함), 없으면 기본 팀원을 쓴다.
                a_sids = B.match_side_sids(event, m, "a") if m.a else []
                b_sids = B.match_side_sids(event, m, "b") if m.b else []
                # [버그 수정] 예전엔 이긴 쪽·진 쪽 모두에게 m.note(참가자
                # A:B로 고정된 스코어)를 그대로 썼다 — 실제 승자가 B이면
                # 이긴 줄에도 "0:2" 같은 A 기준 숫자가 찍혀 헷갈렸다.
                # 이제 참가자 A 줄은 A 관점(is_side_a=True), 참가자 B
                # 줄은 B 관점(is_side_a=False)으로 각각 계산해서, 어느
                # 줄이든 "결과=승"이면 내가 이긴 세트 수가 항상 앞에
                # 오도록 맞춘다.
                rows += B.build_history_rows(event.sport or event.name, event.format, date_str,
                                            roster_by_sid, a_sids, b_sids, m.sets, True)
                rows += B.build_history_rows(event.sport or event.name, event.format, date_str,
                                            roster_by_sid, b_sids, a_sids, m.sets, False)
                newly_saved.append(m)
        if not rows:
            QMessageBox.information(self, tr("util.bracket.roster.history.save_title"),
                                   tr("util.bracket.roster.history.nothing_to_save"))
            return
        try:
            B.append_history(path, rows)
        except ImportError:
            QMessageBox.warning(self, tr("util.bracket.roster.history.save_title"),
                               tr("util.bracket.roster.need_openpyxl"))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("util.bracket.roster.history.save_title"),
                               tr("util.bracket.roster.history.save_error", a0=str(e)))
            return
        for m in newly_saved:
            m.saved = True
        self._save_settings()
        self._save_series_file()
        self._refresh_participant_labels()
        if self.host:
            self.host.status(tr("util.bracket.roster.history.saved_status", a0=len(newly_saved), a1=path))
            self.host.log(tr("util.bracket.log.history_saved", a0=len(newly_saved), a1=path))

    def _on_merge_results(self):
        """[v38] 다른 컴퓨터에서 기록한 같은 시리즈 파일을 골라 지금
        시리즈에 합친다. 없는 라운드·경기는 그대로 가져오고, 서로 다른
        결과가 있으면 하나씩 어느 쪽을 남길지 물어본다."""
        if self.series is None:
            QMessageBox.information(self, tr("util.bracket.roster.merge.title"),
                                   tr("util.bracket.roster.need_more_participants"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, tr("util.bracket.roster.merge.title"), "", "JSON (*.json)")
        if not path:
            return
        try:
            other = B.load_series(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("util.bracket.roster.merge.title"),
                               tr("util.bracket.roster.merge.read_error", a0=str(e)))
            return
        if other is None:
            QMessageBox.warning(self, tr("util.bracket.roster.merge.title"),
                               tr("util.bracket.roster.merge.read_error", a0=""))
            return
        added, filled, conflicts = B.merge_series(self.series, other)
        for conflict in conflicts:
            dlg = _MergeConflictDialog(conflict, parent=self)
            if dlg.exec() == QDialog.Accepted:
                B.apply_conflict_choice(self.series, conflict, dlg.choice())
        self._save_series_file()
        self._sync_events_from_series()
        QMessageBox.information(
            self, tr("util.bracket.roster.merge.title"),
            tr("util.bracket.roster.merge.done", a0=added, a1=filled, a2=len(conflicts)))
        if self.host:
            self.host.log(tr("util.bracket.roster.merge.done", a0=added, a1=filled, a2=len(conflicts)))

    # ---------------------------------------------------------------- 명단(좌측 하단)
    def _on_roster_upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("util.bracket.roster.upload_title"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            students = self.host.run_busy(
                tr("util.bracket.roster.loading"), lambda: B.read_roster_excel(path))
        except ImportError:
            QMessageBox.warning(self, tr("util.bracket.roster.upload_title"),
                               tr("util.bracket.roster.need_openpyxl"))
            return
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, tr("util.bracket.roster.upload_title"),
                               tr("util.bracket.roster.read_error", a0=str(e)))
            return
        if not students:
            QMessageBox.warning(self, tr("util.bracket.roster.upload_title"),
                               tr("util.bracket.roster.empty"))
            return
        self.roster = students
        self._update_roster_status()
        self._populate_participant_tree()
        self._save_settings()
        if self.host:
            self.host.log(tr("util.bracket.log.roster_uploaded", a0=len(students)))

    def _on_roster_clear(self):
        if not self.roster and not self.events:
            return
        reply = QMessageBox.question(
            self, tr("util.bracket.roster.clear_title"), tr("util.bracket.roster.clear_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        # [v38.2] 명단만 지우고 시리즈 파일(라운드 기록)은 그대로 두면,
        # 나중에 같은 종목+반으로 다시 생성할 때 디스크에 남아 있던
        # "안 끝난 이전 라운드"를 그대로 불러와 새 라운드 생성이 막혀
        # 버린다(원인은 QSettings가 아니라 시리즈 JSON 파일이었다).
        # "명단 지우기"는 이 반의 테스트 데이터를 통째로 리셋하는
        # 동작이므로, 지금까지 저장된 시리즈 파일도 함께 지운다.
        for _key, _path in B.list_series_files(self._history_path):
            try:
                os.remove(_path)
            except OSError:
                pass
        self.roster = []
        self.events = []
        self._event_rounds = []
        self.series = None
        self.combo_series.clear()
        self._current_event = None
        self.combo_event.clear()
        self.tree_participants.clear()
        self.roster_bracket_canvas.set_event_bracket(B.Bracket({}))
        self._update_roster_status()
        self._update_event_buttons()
        self._save_settings()

    def _update_roster_status(self):
        if self.roster:
            self.lbl_roster_status.setText(tr("util.bracket.roster.loaded", a0=len(self.roster)))
        else:
            self.lbl_roster_status.setText(tr("util.bracket.roster.none"))

    # ---------------------------------------------------------------- 설정 저장/복원
    def _load_settings(self):
        if self._settings is None:
            return
        self.roster = B.roster_from_json(self._settings.value(_SET_ROSTER, ""))
        # [v38] 종목 대진표는 더 이상 QSettings가 아니라 시리즈 파일에서
        # 관리한다(라운드가 계속 쌓이므로 파일이 훨씬 다루기 쉽다) — 예전에
        # QSettings에 남아 있던 종목은 테스트용이었을 뿐이라 그대로 둔다.
        self._history_path = self._settings.value(_SET_HISTORY_PATH, "") or None
        self._manual_tiers = B.manual_tiers_from_json(self._settings.value(_SET_MANUAL_TIERS, ""))
        self.events = []
        self._event_rounds = []
        self.series = None
        self._update_roster_status()
        self._populate_participant_tree()
        last_key = self._settings.value(_SET_LAST_SERIES_KEY, "") or None
        self._refresh_series_combo(select_key=last_key)
        self._update_event_buttons()

    def _save_settings(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_ROSTER, B.roster_to_json(self.roster))
        self._settings.setValue(_SET_HISTORY_PATH, self._history_path or "")
        self._settings.setValue(_SET_MANUAL_TIERS, B.manual_tiers_to_json(self._manual_tiers))
        self._settings.setValue(_SET_LAST_SERIES_KEY, self.series.key if self.series else "")

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.lbl_event_title.setText(tr("util.bracket.roster.event_title"))
        self.card_right.set_title(tr("util.bracket.title"))
        self.lbl_event_name.setText(tr("util.bracket.roster.lbl.sport"))
        self.edit_sport_other.setPlaceholderText(tr("util.bracket.roster.sport_other_placeholder"))
        self.lbl_format.setText(tr("util.bracket.roster.lbl.format"))
        self.radio_format_league.setText(tr("util.bracket.mode.league"))
        self.radio_format_tournament.setText(tr("util.bracket.mode.tournament"))
        self.lbl_team_size.setText(tr("util.bracket.roster.lbl.team_size"))
        self.lbl_team_size_hint.setText(tr("util.bracket.roster.team_size_hint"))
        self.lbl_tier_mode.setText(tr("util.bracket.roster.lbl.tier_mode"))
        _tier_mode_idx = self.combo_tier_mode.currentIndex()
        self.combo_tier_mode.setItemText(0, tr("util.bracket.roster.tier_mode.random"))
        self.combo_tier_mode.setItemText(1, tr("util.bracket.roster.tier_mode.split"))
        self.combo_tier_mode.setItemText(2, tr("util.bracket.roster.tier_mode.level"))
        self.combo_tier_mode.setCurrentIndex(_tier_mode_idx)
        self.lbl_tier_mode_hint.setText(self._tier_mode_hint_text())
        self.lbl_name_preview_title.setText(tr("util.bracket.roster.name_preview_title"))
        self.btn_generate.setText(tr("util.bracket.btn.generate"))
        self.btn_save_to_excel.setText(tr("util.bracket.roster.btn.save_result"))
        self.btn_merge_results.setText(tr("util.bracket.roster.btn.merge_result"))
        self.btn_export_grades.setText(tr("util.bracket.roster.btn.export_grades"))
        self.lbl_roster_title.setText(tr("util.bracket.roster.title"))
        self.btn_roster_upload.setText(tr("util.bracket.roster.btn.upload"))
        self.btn_roster_clear.setText(tr("util.bracket.roster.btn.clear"))
        self.lbl_participants_hint.setText(tr("util.bracket.roster.participants_hint"))
        self.btn_toggle_all_classes.setToolTip(tr("util.bracket.roster.toggle_all_classes"))
        self.tree_participants.setHeaderLabels([
            tr("util.bracket.roster.col.name"), tr("util.bracket.roster.col.wl"),
            tr("util.bracket.roster.col.auto_tier"), tr("util.bracket.roster.col.manual_tier")])
        self.lbl_series.setText(tr("util.bracket.roster.lbl.series"))
        self.lbl_history.setText(tr("util.bracket.roster.lbl.round"))
        self.btn_reassign.setText(tr("util.bracket.roster.btn.reassign"))
        self.btn_attendance.setText(tr("util.bracket.roster.btn.attendance"))
        self.btn_event_delete.setText(tr("util.bracket.roster.btn.delete_event"))
        self.tabs.setTabText(0, tr("util.bracket.roster.tab.participants"))
        self.tabs.setTabText(1, tr("util.bracket.roster.tab.bracket"))
        self._update_format_buttons()
        self._update_roster_status()
        self._update_participant_count()
        self._update_event_name_preview()
        self.league_view.set_headers([
            tr("util.bracket.round_label", a0=""), tr("util.bracket.roster.col.a"),
            tr("util.bracket.roster.col.b"), tr("util.bracket.roster.col.result")])
# =============================================================================
class BracketApp(MiniApp):
    id = "bracket"
    icon = "bracket"
    category = "class"   # 학교

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = BracketWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.bracket.title": {"ko": "대진표 작성기", "en": "Bracket Maker", "ja": "対戦表作成"},
    "util.bracket.desc": {
        "ko": "학급 명단을 바탕으로 그날 참여하는 학생만 골라 대진표·리그 일정을 만듭니다.",
        "en": "Picks today's participants from the class roster and makes brackets/round-robin schedules.",
        "ja": "クラス名簿からその日の参加者だけを選んで対戦表・リーグ日程を作成します。"},
    "util.bracket.mode.tournament": {"ko": "토너먼트", "en": "Tournament", "ja": "トーナメント"},
    "util.bracket.mode.league": {"ko": "리그(조별리그)", "en": "Round-robin", "ja": "リーグ戦"},
    "util.bracket.btn.generate": {"ko": "생성", "en": "Generate", "ja": "作成"},
    "util.bracket.bye": {"ko": "(부전승)", "en": "(bye)", "ja": "（シード）"},
    "util.bracket.tbd": {"ko": "(승자 미정)", "en": "(TBD)", "ja": "（未定）"},
    "util.bracket.champion": {"ko": "🏆 {a0}", "en": "🏆 {a0}", "ja": "🏆 {a0}"},
    "util.bracket.round_label": {"ko": "{a0}라운드", "en": "Round {a0}", "ja": "第{a0}ラウンド"},

    # ---- 학급 명단 기반(유일한 화면) ----
    "util.bracket.roster.title": {"ko": "학급 명단", "en": "Class Roster", "ja": "クラス名簿"},
    "util.bracket.roster.btn.upload": {"ko": "명단 엑셀 업로드", "en": "Upload Roster", "ja": "名簿アップロード"},
    "util.bracket.roster.btn.clear": {"ko": "명단 지우기", "en": "Clear Roster", "ja": "名簿を消去"},
    "util.bracket.roster.upload_title": {"ko": "명단 엑셀 업로드", "en": "Upload Roster Excel", "ja": "名簿Excelアップロード"},
    "util.bracket.roster.loading": {"ko": "명단 파일 불러오는 중…", "en": "Loading roster file…", "ja": "名簿ファイルを読み込み中…"},
    "util.bracket.roster.need_openpyxl": {
        "ko": "엑셀 파일을 읽으려면 openpyxl 패키지가 필요합니다.\npip install openpyxl 로 설치해 주세요.",
        "en": "Reading Excel files needs the openpyxl package.\nInstall it with: pip install openpyxl",
        "ja": "Excelファイルを読むにはopenpyxlパッケージが必要です。\npip install openpyxl でインストールしてください。"},
    "util.bracket.roster.read_error": {
        "ko": "엑셀을 읽는 중 오류가 발생했습니다: {a0}",
        "en": "Error reading the Excel file: {a0}", "ja": "Excelの読み込み中にエラーが発生しました: {a0}"},
    "util.bracket.roster.empty": {
        "ko": "명단에서 학생을 한 명도 찾지 못했습니다. 학년·반·번호·이름·성별 순서(1행은 머리글)로 되어 있는지 확인해 주세요.",
        "en": "No students found. Check that columns are grade, class, number, name, gender (row 1 is the header).",
        "ja": "生徒が見つかりませんでした。学年・クラス・番号・氏名・性別の順（1行目は見出し）か確認してください。"},
    "util.bracket.roster.loaded": {"ko": "학생 {a0}명 등록됨", "en": "{a0} students registered", "ja": "生徒{a0}人登録済み"},
    "util.bracket.roster.none": {
        "ko": "아직 명단이 없습니다. 엑셀을 올려주세요.",
        "en": "No roster yet. Upload an Excel file.", "ja": "まだ名簿がありません。Excelをアップロードしてください。"},
    "util.bracket.roster.clear_title": {"ko": "명단 지우기", "en": "Clear Roster", "ja": "名簿を消去"},
    "util.bracket.roster.clear_confirm": {
        "ko": "명단과 지금까지 저장된 모든 회차 기록(시리즈 파일)이 함께 사라집니다. 되돌릴 수 없습니다. 계속할까요?",
        "en": "This will delete the roster and every saved session record (series files) for this bracket tool. This can't be undone. Continue?",
        "ja": "名簿とこれまで保存された全てのセッション記録（シリーズファイル）も削除されます。元に戻せません。続けますか？"},
    "util.bracket.roster.event_title": {"ko": "종목", "en": "Event", "ja": "種目"},
    "util.bracket.roster.btn.delete_event": {"ko": "삭제", "en": "Delete", "ja": "削除"},
    "util.bracket.roster.delete_event_title": {"ko": "종목 삭제", "en": "Delete Event", "ja": "種目を削除"},
    "util.bracket.roster.delete_event_confirm": {
        "ko": "이 종목의 대진표와 경기 기록이 함께 삭제됩니다. 계속할까요?",
        "en": "This event's bracket and results will be deleted. Continue?",
        "ja": "この種目の対戦表と試合記録も削除されます。続けますか？"},
    "util.bracket.roster.generate_title": {"ko": "대진표 생성", "en": "Generate", "ja": "作成"},
    "util.bracket.roster.need_more_participants": {
        "ko": "탭1(참가자 선택)에서 참가자를 2명 이상 체크하세요.",
        "en": "Check at least 2 participants in the Participants tab.", "ja": "タブ1（参加者選択）で参加者を2人以上チェックしてください。"},
    "util.bracket.roster.lbl.sport": {"ko": "종목", "en": "Sport", "ja": "種目"},
    "util.bracket.roster.sport_other_placeholder": {"ko": "종목 이름 직접 입력", "en": "Enter sport name", "ja": "種目名を入力"},
    "util.bracket.roster.lbl.format": {"ko": "형식", "en": "Format", "ja": "形式"},
    "util.bracket.roster.lbl.team_size": {"ko": "팀당 인원", "en": "People per team", "ja": "チームあたりの人数"},
    "util.bracket.roster.team_size_hint": {
        "ko": "1=개인전(단식), 2=복식, 3 이상=단체전. 선택한 참가자를 이 인원수만큼씩 무작위로 묶습니다.",
        "en": "1=singles, 2=doubles, 3+=team sport. Randomly groups the checked participants into teams of this size.",
        "ja": "1=個人戦、2=ダブルス、3以上=団体戦。選んだ参加者をこの人数ずつランダムに組みます。"},
    "util.bracket.roster.participant_count": {"ko": "선택된 참가자: {a0}명", "en": "{a0} participants selected", "ja": "選択された参加者：{a0}人"},
    "util.bracket.roster.name_preview_title": {"ko": "만들어질 종목 이름", "en": "This event will be named", "ja": "作成される種目名"},
    "util.bracket.roster.name_preview_empty": {
        "ko": "(참가자를 선택하면 이름이 자동으로 만들어집니다)",
        "en": "(Select participants to auto-generate a name)", "ja": "（参加者を選ぶと名前が自動生成されます）"},
    "util.bracket.roster.btn.save_to_excel": {"ko": "엑셀 결과 저장", "en": "Save Results to Excel", "ja": "Excelに結果を保存"},
    "util.bracket.roster.participants_hint": {
        "ko": "학년·반 이름을 체크하면 그 반 전체가 선택됩니다. 오늘 결석한 학생만 체크를 풀어 주세요.",
        "en": "Checking a grade/class selects all its students. Just uncheck any student absent today.",
        "ja": "学年・クラス名をチェックするとそのクラス全員が選択されます。今日欠席の生徒だけチェックを外してください。"},
    "util.bracket.roster.class_label": {
        "ko": "{a0}학년 {a1}반 ({a2}명)", "en": "Grade {a0} Class {a1} ({a2})", "ja": "{a0}学年{a1}組（{a2}人）"},
    "util.bracket.roster.wl_suffix": {"ko": " [{a0}승 {a1}패]", "en": " [{a0}W {a1}L]", "ja": " [{a0}勝{a1}敗]"},
    "util.bracket.roster.wl_cell": {"ko": "{a0}승 {a1}패", "en": "{a0}W {a1}L", "ja": "{a0}勝{a1}敗"},
    "util.bracket.roster.col.name": {"ko": "이름", "en": "Name", "ja": "氏名"},
    "util.bracket.roster.col.wl": {"ko": "승패", "en": "W-L", "ja": "勝敗"},
    "util.bracket.roster.col.auto_tier": {"ko": "자동등급", "en": "Auto Tier", "ja": "自動等級"},
    "util.bracket.roster.col.manual_tier": {"ko": "교사등급", "en": "Teacher Tier", "ja": "教師等級"},
    "util.bracket.roster.tier_auto": {"ko": " (자동:{a0})", "en": " (auto:{a0})", "ja": " (自動:{a0})"},
    "util.bracket.roster.tier_manual": {"ko": " (등급:{a0})", "en": " (tier:{a0})", "ja": " (等級:{a0})"},
    "util.bracket.roster.tier_menu_set": {"ko": "등급: {a0}", "en": "Tier: {a0}", "ja": "等級：{a0}"},
    "util.bracket.roster.tier_menu_clear": {
        "ko": "등급 지우기(자동 추정으로 되돌리기)", "en": "Clear tier (fall back to auto)", "ja": "等級を消す（自動推定に戻す）"},
    "util.bracket.roster.lbl.tier_mode": {"ko": "실력 고려", "en": "Skill handling", "ja": "実力の扱い"},
    "util.bracket.roster.tier_mode.random": {"ko": "무작위", "en": "Random", "ja": "ランダム"},
    "util.bracket.roster.tier_mode.split": {"ko": "수준별 분리", "en": "Split by tier", "ja": "レベル別に分離"},
    "util.bracket.roster.tier_mode.level": {"ko": "팀 레벨 균형", "en": "Balanced team level", "ja": "チームレベル均衡"},
    "util.bracket.roster.tier_mode.random_hint": {
        "ko": "참가자를 그대로 무작위로 묶습니다(등급은 안 봅니다).",
        "en": "Groups participants at random, without looking at tier.",
        "ja": "参加者をそのままランダムに組みます（等級は見ません）。"},
    "util.bracket.roster.tier_mode.level_hint": {
        "ko": "등급(상=3점/중=2점/하=1점)을 매겨, 모든 팀의 평균 점수가 2에 가깝도록(1.5~2.5 안으로) "
              "팀을 짭니다. 실력이 고른 팀끼리 겨루게 하고 싶을 때 씁니다. 등급은 교사 등급이 "
              "우선이고, 없으면 누적 승률로 추정한 자동 등급을 씁니다(그마저 없으면 '중'으로 봅니다).",
        "en": "Scores tiers (high=3/mid=2/low=1) and builds teams whose average is close to 2 "
              "(kept within 1.5-2.5) — use this to make every team roughly as strong as the others. "
              "Manual tier wins if set; otherwise the auto-estimated tier, or 'mid' if neither exists.",
        "ja": "等級（上=3点/中=2点/下=1点）をつけ、全てのチームの平均点が2に近くなるように"
              "（1.5〜2.5の範囲内で）チームを組みます。実力が揃ったチーム同士で対戦させたい時に使います。"
              "等級は教師の等級が優先され、なければ自動推定等級（それもなければ「中」）を使います。"},
    "util.bracket.roster.tier_mode_hint": {
        "ko": "수준별 분리를 고르면 등급(상/중/하)마다 대진표를 따로 만듭니다. "
              "등급은 학생을 오른쪽 클릭해 직접 매길 수 있고(항상 우선), "
              "안 매긴 학생은 누적 승률로 추정하거나(자동, 참고용) 없으면 '중'으로 봅니다.",
        "en": "Splitting by tier makes a separate bracket per tier (high/mid/low). Right-click "
              "a student to set their tier by hand (always takes priority); otherwise it's "
              "estimated from win rate (auto, for reference) or defaults to 'mid'.",
        "ja": "レベル別に分離すると等級（上/中/下）ごとに別の対戦表を作ります。生徒を右クリックすると"
              "手動で等級を設定できます（常に優先）。設定していない場合は勝率から推定（自動・参考用）"
              "するか、なければ「中」とみなします。"},
    "util.bracket.roster.tier_split_none": {
        "ko": "어느 등급도 2명 이상이 되지 않아 대진표를 만들 수 없습니다. 등급을 조정해 주세요.",
        "en": "No tier has 2 or more participants, so no bracket could be made. Adjust tiers and try again.",
        "ja": "どの等級も2人以上にならず、対戦表を作成できませんでした。等級を調整してください。"},
    "util.bracket.roster.tier_split_skipped": {
        "ko": "인원이 부족해 대진표를 못 만든 등급이 있습니다 — {a0}. "
              "이 학생들의 등급을 다른 등급으로 조정한 뒤 다시 만들어 보세요.",
        "en": "Some tiers had too few participants for a bracket — {a0}. "
              "Adjust these students' tiers and generate again.",
        "ja": "人数が足りず対戦表を作れなかった等級があります — {a0}。"
              "これらの生徒の等級を調整して再度作成してください。"},
    "util.bracket.roster.tab.participants": {"ko": "참가자 선택", "en": "Participants", "ja": "参加者選択"},
    "util.bracket.roster.tab.bracket": {"ko": "대진표", "en": "Bracket", "ja": "対戦表"},
    "util.bracket.roster.click_to_record": {"ko": "클릭해서 기록", "en": "Click to record", "ja": "クリックして記録"},
    "util.bracket.roster.col.a": {"ko": "참가자 A", "en": "Participant A", "ja": "参加者A"},
    "util.bracket.roster.col.b": {"ko": "참가자 B", "en": "Participant B", "ja": "参加者B"},
    "util.bracket.roster.col.result": {"ko": "결과", "en": "Result", "ja": "結果"},
    "util.bracket.roster.record.title": {"ko": "경기 결과 기록", "en": "Record Match Result", "ja": "試合結果の記録"},
    "util.bracket.roster.record.set_label": {"ko": "{a0}세트", "en": "Set {a0}", "ja": "第{a0}セット"},
    "util.bracket.roster.record.enter_scores": {
        "ko": "세트별 점수를 입력하세요", "en": "Enter each set's score", "ja": "各セットの点数を入力してください"},
    "util.bracket.roster.record.tied": {
        "ko": "{a0}:{a1} — 아직 승부가 정해지지 않았습니다", "en": "{a0}:{a1} — no winner yet", "ja": "{a0}:{a1} — まだ勝敗が決まっていません"},
    "util.bracket.roster.record.preview": {"ko": "결과: {a0}:{a1}", "en": "Result: {a0}:{a1}", "ja": "結果：{a0}:{a1}"},
    "util.bracket.roster.record.error_partial": {
        "ko": "한쪽 점수만 입력되었습니다. 양쪽 모두 입력해 주세요.",
        "en": "Only one side's score is entered. Please fill in both sides.",
        "ja": "片方のみ点数が入力されています。両方入力してください。"},
    "util.bracket.roster.record.error_skip": {
        "ko": "빈 세트 다음에 점수가 있습니다. 세트를 건너뛰지 말고 순서대로 입력해 주세요.",
        "en": "A later set has scores after an empty one. Fill sets in order without skipping.",
        "ja": "空のセットの後に点数があります。セットを飛ばさず順番に入力してください。"},
    "util.bracket.roster.record.need_scores": {
        "ko": "승부가 갈리도록 세트 점수를 입력하세요(동률이면 기록할 수 없습니다).",
        "en": "Enter scores that decide a winner (a tie can't be recorded).",
        "ja": "勝敗が決まるようにセットの点数を入力してください（同点は記録できません）。"},
    "util.bracket.roster.record.clear": {"ko": "기록 취소", "en": "Clear Result", "ja": "記録を取り消す"},
    "util.bracket.roster.history.pick_title": {
        "ko": "누적 기록 엑셀 파일 선택(기존 파일을 고르면 이어서 기록합니다)",
        "en": "Choose the cumulative history file (pick an existing one to continue it)",
        "ja": "累積記録Excelファイルを選択（既存ファイルを選ぶと続けて記録します）"},
    "util.bracket.roster.history.save_title": {"ko": "엑셀 결과 저장", "en": "Save Results to Excel", "ja": "Excelに結果を保存"},
    "util.bracket.roster.history.nothing_to_save": {
        "ko": "새로 저장할 경기 결과가 없습니다(이미 다 저장했거나, 아직 기록된 결과가 없습니다).",
        "en": "Nothing new to save (already saved, or no results recorded yet).",
        "ja": "新しく保存する試合結果がありません（既に保存済み、または未記録です）。"},
    "util.bracket.roster.history.save_error": {
        "ko": "저장 중 오류가 발생했습니다: {a0}", "en": "Error while saving: {a0}", "ja": "保存中にエラーが発生しました: {a0}"},
    "util.bracket.roster.history.saved_status": {
        "ko": "경기 결과 {a0}건을 저장했습니다: {a1}", "en": "Saved {a0} results to: {a1}", "ja": "試合結果{a0}件を保存しました: {a1}"},
    "util.bracket.log.roster_uploaded": {
        "ko": "[대진표] 명단 {a0}명을 올렸습니다", "en": "[Bracket] Uploaded a roster of {a0}", "ja": "[対戦表] 名簿{a0}人をアップロードしました"},
    "util.bracket.log.event_created": {
        "ko": "[대진표] 종목 '{a0}'을 만들었습니다({a1}명)",
        "en": "[Bracket] Created event '{a0}' ({a1} participants)", "ja": "[対戦表] 種目「{a0}」を作成しました（{a1}人）"},
    "util.bracket.log.result_recorded": {
        "ko": "[대진표] '{a0}' 경기 결과를 기록했습니다",
        "en": "[Bracket] Recorded a result for '{a0}'", "ja": "[対戦表]「{a0}」の試合結果を記録しました"},
    "util.bracket.log.history_saved": {
        "ko": "[대진표] 경기 결과 {a0}건을 엑셀에 저장: {a1}",
        "en": "[Bracket] Saved {a0} results to Excel: {a1}", "ja": "[対戦表] 試合結果{a0}件をExcelに保存: {a1}"},

    "util.bracket.roster.btn.save_result": {"ko": "경기 결과 저장", "en": "Save Match Results", "ja": "試合結果を保存"},
    "util.bracket.roster.btn.merge_result": {"ko": "경기 결과 합치기", "en": "Merge Match Results", "ja": "試合結果を合わせる"},
    "util.bracket.roster.btn.export_grades": {"ko": "성적 산출", "en": "Export Grades", "ja": "成績算出"},
    "util.bracket.roster.grades.none": {
        "ko": "아직 성적으로 낼 경기 결과가 없습니다. 경기를 먼저 기록해 주세요.",
        "en": "No recorded results yet — record some matches first.",
        "ja": "まだ成績にできる試合結果がありません。先に試合を記録してください。"},
    "util.bracket.roster.grades.save_fail": {"ko": "성적 파일 저장 실패: {a0}", "en": "Failed to save grades file: {a0}",
                                              "ja": "成績ファイルの保存に失敗しました: {a0}"},
    "util.bracket.roster.grades.saved_status": {
        "ko": "학생 {a0}명의 성적을 저장했습니다: {a1}",
        "en": "Saved grades for {a0} students: {a1}", "ja": "生徒{a0}名の成績を保存しました: {a1}"},
    "util.bracket.roster.lbl.series": {"ko": "시리즈", "en": "Series", "ja": "シリーズ"},
    "util.bracket.roster.lbl.round": {"ko": "회차", "en": "Session", "ja": "セッション"},
    "util.bracket.roster.btn.reassign": {"ko": "학생 추가 배정", "en": "Assign Student", "ja": "生徒を追加配置"},
    "util.bracket.roster.series.refresh": {"ko": "시리즈 목록 새로고침", "en": "Refresh series list",
                                            "ja": "シリーズ一覧を更新"},
    "util.bracket.roster.toggle_all_classes": {"ko": "전체 반 펼치기/접기", "en": "Expand/collapse all classes",
                                                "ja": "全クラスを開く/閉じる"},

    "util.bracket.roster.round_item": {"ko": "회차 {a0} · {a1} · {a2}", "en": "Session {a0} · {a1} · {a2}",
                                        "ja": "セッション{a0}・{a1}・{a2}"},
    "util.bracket.roster.round_done": {"ko": "완료", "en": "Done", "ja": "完了"},
    "util.bracket.roster.round_progress": {"ko": "진행 중 {a0}/{a1}", "en": "In progress {a0}/{a1}",
                                            "ja": "進行中 {a0}/{a1}"},
    "util.bracket.roster.uneven_team_hint": {
        "ko": "다음 팀은 인원이 모자랍니다(결석·홀수 인원 등): {a0}\n"
              "\"학생 추가 배정\" 버튼으로 다른 팀에 넣어 3인 팀으로 만들 수 있습니다.",
        "en": "These teams are short a member (absence, odd count, etc.): {a0}\n"
              "Use \"Assign Student\" to add them to another team.",
        "ja": "次のチームは人数が足りません（欠席・奇数人数など）: {a0}\n"
              "「生徒を追加配置」で他のチームに加えられます。"},

    "util.bracket.roster.reassign.title": {"ko": "학생 추가 배정", "en": "Assign Student", "ja": "生徒を追加配置"},
    "util.bracket.roster.reassign.hint": {
        "ko": "결석이나 홀수 인원으로 팀을 못 채운 학생을 다른 팀에 추가로 넣습니다. "
              "그 팀은 인원이 하나 늘고(예: 3인 팀), 경기 결과는 팀 전원이 똑같이 받습니다.",
        "en": "Add a student who couldn't be placed (absence, odd count) into another team. "
              "That team gains one member, and every member shares the same match result.",
        "ja": "欠席や奇数人数でチームに入れなかった生徒を他のチームに追加します。"
              "そのチームは人数が1人増え（例：3人チーム）、試合結果は全員が同じように受け取ります。"},
    "util.bracket.roster.reassign.student": {"ko": "학생", "en": "Student", "ja": "生徒"},
    "util.bracket.roster.reassign.team": {"ko": "배정할 팀", "en": "Team to assign to", "ja": "配置するチーム"},
    "util.bracket.roster.reassign.unassigned_mark": {"ko": "  (미배정)", "en": "  (unassigned)", "ja": "  (未配置)"},
    "util.bracket.roster.btn.attendance": {"ko": "오늘 출석 조정", "en": "Today's Attendance", "ja": "今日の出席調整"},
    "util.bracket.roster.att.title": {"ko": "오늘 출석 조정 ({a0})", "en": "Today's attendance ({a0})", "ja": "今日の出席調整（{a0}）"},
    "util.bracket.roster.att.hint": {
        "ko": "결석한 학생의 체크를 풀면 오늘 경기 기록에서 빠집니다(팀 구성은 그대로). "
              "한 명만 남는 팀이 생기면 아래에서 빌려올 학생이나 합류할 팀을 고르세요. 조정은 오늘만 적용됩니다.",
        "en": "Uncheck absent students to exclude them from today's records (teams stay). "
              "If a team is left with one student, pick a borrowed student or a team to join below. Applies today only.",
        "ja": "欠席した生徒のチェックを外すと今日の記録から除外されます（チーム構成はそのまま）。"
              "1人だけ残るチームがあれば、下で借りる生徒か合流するチームを選んでください。調整は今日のみ適用されます。"},
    "util.bracket.roster.att.fix_title": {"ko": "한 명만 남은 팀 처리", "en": "Teams left with one student", "ja": "1人だけ残ったチームの処理"},
    "util.bracket.roster.att.lone": {"ko": "{a0} 혼자 남음 →", "en": "{a0} is alone →", "ja": "{a0} が1人 →"},
    "util.bracket.roster.att.opt_none": {"ko": "— 팀 선택 —", "en": "— choose a team —", "ja": "— チームを選択 —"},
    "util.bracket.roster.att.opt_borrow": {"ko": "{a0} 빌려오기 (원래 팀: {a1})", "en": "Borrow {a0} (from: {a1})", "ja": "{a0} を借りる（元のチーム: {a1}）"},
    "util.bracket.roster.att.opt_borrow_alone": {"ko": "혼자였음", "en": "was alone", "ja": "1人だった"},
    "util.bracket.roster.att.opt_join": {"ko": "{a0} 팀에 합류(오늘 3인 팀)", "en": "Join team {a0} (3 today)", "ja": "{a0} チームに合流（今日は3人）"},
    "util.bracket.roster.att.absent_mark": {"ko": "{a0} ✕결석", "en": "{a0} ✕absent", "ja": "{a0} ✕欠席"},
    "util.bracket.roster.att.temp_mark": {"ko": "{a0} (임시)", "en": "{a0} (temp)", "ja": "{a0}（臨時）"},
    "util.bracket.log.attendance": {"ko": "[대진표] 오늘 출석 조정 저장 — 결석 {a0}명, 임시 편성 {a1}건",
                                     "en": "[Bracket] Attendance saved — {a0} absent, {a1} transfer(s)",
                                     "ja": "[対戦表] 今日の出席調整を保存 — 欠席{a0}名、臨時編成{a1}件"},
    "util.bracket.roster.reassign.none_left": {
        "ko": "이 회차에는 팀을 못 이룬 학생이 없습니다.",
        "en": "No students are waiting to be assigned in this session.",
        "ja": "このセッションにはチームを組めなかった生徒はいません。"},
    "util.bracket.roster.round_not_finished": {
        "ko": "아직 안 끝난 회차가 있습니다({a0}회차). 그 회차의 경기를 모두 기록한 뒤 새 회차를 만들 수 있습니다.",
        "en": "Session(s) {a0} aren't finished yet. Record all their results before starting a new session.",
        "ja": "まだ終わっていないセッションがあります（{a0}）。そのセッションの試合を全て記録してから新しいセッションを作成できます。"},
    "util.bracket.log.reassigned": {
        "ko": "[대진표] {a0} 학생을 팀({a1})에 추가 배정했습니다",
        "en": "[Bracket] Assigned {a0} to team ({a1})", "ja": "[対戦表] {a0}をチーム（{a1}）に追加配置しました"},

    "util.bracket.roster.merge.title": {"ko": "경기 결과 합치기", "en": "Merge Match Results", "ja": "試合結果を合わせる"},
    "util.bracket.roster.merge.read_error": {"ko": "시리즈 파일을 읽을 수 없습니다: {a0}",
                                              "en": "Couldn't read the series file: {a0}",
                                              "ja": "シリーズファイルを読み込めません: {a0}"},
    "util.bracket.roster.merge.done": {
        "ko": "새 회차 {a0}개 추가, 경기 결과 {a1}건 채움, 충돌 {a2}건 처리했습니다.",
        "en": "Added {a0} new session(s), filled {a1} result(s), resolved {a2} conflict(s).",
        "ja": "新規セッション{a0}件を追加、試合結果{a1}件を補完、競合{a2}件を処理しました。"},
    "util.bracket.roster.merge.conflict_title": {"ko": "결과가 서로 다릅니다", "en": "Results differ",
                                                  "ja": "結果が異なります"},
    "util.bracket.roster.merge.conflict_label": {"ko": "{a0} 경기의 결과가 두 파일에서 다릅니다. 어느 쪽을 남길까요?",
                                                  "en": "\"{a0}\" has different results in the two files. Which should stay?",
                                                  "ja": "「{a0}」の結果が2つのファイルで異なります。どちらを残しますか？"},
    "util.bracket.roster.merge.keep_local": {"ko": "지금 기록 유지: {a0}", "en": "Keep current: {a0}",
                                              "ja": "現在の記録を維持: {a0}"},
    "util.bracket.roster.merge.keep_other": {"ko": "가져온 기록으로 바꾸기: {a0}", "en": "Use imported: {a0}",
                                              "ja": "取り込んだ記録に変更: {a0}"},
}
BracketApp.tr_table = TRANSLATIONS

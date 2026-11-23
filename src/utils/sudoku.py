# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 스도쿠 [v46.1]

9x9 스도쿠를 풀 수 있는 도구. 난이도(쉬움/보통/어려움)는 빈 칸 개수로만
나눈다(1차 범위로 사용자와 합의 — 실제 풀이 테크닉 난이도까지 따지는
정교한 방식은 더 복잡해서 다음 범위로 미뤘다). 숫자 확정 입력과
메모(연필로 후보 숫자 적기)를 처음부터 함께 구현했다(역시 사용자와
합의한 1차 범위).

[v46.1] 처음에는 "틀린 숫자도 일단 반영하고 색으로만 구분"했는데, 그
오답 색이 정답 색과 너무 비슷해 "다 채웠는데 완성이 안 된다"는 지적을
받았다(실제로는 오답이 섞여 있었는데 못 알아챈 것) — 이제는 틀리면
아예 반영하지 않고 그 자리에서 바로 오답 메시지 + 재시도(라이프)
감소로 분명하게 알려준다. 재시도는 3회, 다 떨어지면 재도전/새 퍼즐을
고르는 창이 뜬다. 힌트도 라이프를 하나 쓴다.

생성·검증·완성 판정·라이프 같은 순수 로직은 전부 sudoku_solve.py에
있고, 이 파일은 QPainter로 격자를 그리는 것과 Qt 위젯(난이도·새 게임·
숫자 패드·메모 토글·힌트·라이프 표시)만 담당한다.
"""
import json

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QMessageBox,
    QDialog, QListWidget, QListWidgetItem
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import sudoku_solve as S

_SET_DIFFICULTY = "util.sudoku.difficulty"
_SET_ARCHIVE = "util.sudoku.archive"   # [v46.5] 실패한 퍼즐 보관함(JSON 배열)

_CELL = 52
_GRID = _CELL * 9
_MARGIN = 14

_GIVEN_COLOR = "#1a1a1a"
_ENTRY_COLOR = C.UTIL_MAIN
_CONFLICT_COLOR = "#d32f2f"
_NOTE_COLOR = "#8a909a"
_SELECT_FILL = "#fdeef4"
_THIN_LINE = "#c9ccd1"
_THICK_LINE = "#37474f"

_LIFE_ON = "#43a047"     # 켜진 라이프(초록)
_LIFE_OFF = "#d7dadf"    # 꺼진 라이프(회색)
_WRONG_MSG_COLOR = "#d32f2f"


# =============================================================================
class _LivesIndicator(QWidget):
    """[v46.1] 남은 재시도 횟수를 초록 등 3개로 보여준다 — 설정 카드
    제목줄에 둔다. 오답을 넣거나 힌트를 쓸 때마다 하나씩 꺼진다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lives = S.MAX_LIVES
        self._dot = 12
        self._gap = 5
        w = S.MAX_LIVES * self._dot + (S.MAX_LIVES - 1) * self._gap
        self.setFixedSize(w, self._dot)

    def set_lives(self, lives):
        self.lives = lives
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i in range(S.MAX_LIVES):
            on = i < self.lives
            p.setBrush(QColor(_LIFE_ON if on else _LIFE_OFF))
            x = i * (self._dot + self._gap)
            p.drawEllipse(x, 0, self._dot, self._dot)
        p.end()


class _SudokuCanvas(QWidget):
    """스도쿠 격자를 직접 그린다. 상태(SudokuState)를 직접 들고 있고,
    클릭·키보드 입력도 직접 처리한다 — 숫자 게임은 입력이 매우 잦아서,
    매번 바깥(위젯)으로 콜백을 거치기보다 캔버스가 스스로 처리하는
    쪽이 간결하다. 값이 바뀔 때마다 changed 신호만 보내, 위젯이 완성
    판정 같은 "그 다음 할 일"을 하게 한다."""

    changed = Signal()
    cellSelected = Signal(object)   # (r, c) 또는 None
    wrongEntry = Signal()           # [v46.1] 오답을 입력했을 때
    livesChanged = Signal(int)      # [v46.1] 라이프가 바뀔 때마다(힌트 포함)
    gameOver = Signal()             # [v46.1] 라이프가 0이 됐을 때
    forcedCompletionReady = Signal(object)   # [v46.3] 남은 칸이 전부 유일하게 정해졌을 때(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = None
        self.selected = None
        self.note_mode = False
        self.setFixedSize(_GRID + _MARGIN * 2, _GRID + _MARGIN * 2)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def set_state(self, state):
        self.state = state
        self.selected = None
        self.cellSelected.emit(None)
        self.update()

    def set_note_mode(self, on):
        self.note_mode = on

    def _cell_rect(self, r, c):
        return QRectF(_MARGIN + c * _CELL, _MARGIN + r * _CELL, _CELL, _CELL)

    def _cell_at(self, pos):
        x, y = pos.x() - _MARGIN, pos.y() - _MARGIN
        if x < 0 or y < 0 or x >= _GRID or y >= _GRID:
            return None
        return int(y // _CELL), int(x // _CELL)

    # ---------------------------------------------------------------- 입력
    def mousePressEvent(self, event):
        if self.state is None:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        cell = self._cell_at(pos)
        self.selected = cell
        self.cellSelected.emit(cell)
        self.setFocus()
        self.update()

    def keyPressEvent(self, event):
        if self.state is None or self.selected is None:
            super().keyPressEvent(event)
            return
        key = event.key()
        r, c = self.selected
        if Qt.Key_1 <= key <= Qt.Key_9:
            self.enter_value(key - Qt.Key_0)
            return
        if key in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_0):
            self.erase_selected()
            return
        moves = {Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1),
                Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0)}
        if key in moves:
            dr, dc = moves[key]
            self.selected = (max(0, min(8, r + dr)), max(0, min(8, c + dc)))
            self.cellSelected.emit(self.selected)
            self.update()
            return
        super().keyPressEvent(event)

    def enter_value(self, val):
        """지금 선택된 칸에 val(1~9)을 적는다 — 메모 모드면 후보 숫자를
        켜고 끄고(라이프와 무관), 아니면 정답 여부를 바로 확인한다
        (given 칸이거나 이미 게임 오버면 아무 일도 안 한다).

        [v46.4] val이 보드 전체에 이미 9개 다 채워져 있으면(=그 숫자
        버튼이 꺼져 있는 상태와 같은 조건) 확정 입력은 막는다 — 숫자
        패드 버튼을 비활성화한 것과 똑같이, 키보드로 눌러도 먹히지
        않게 하기 위해서다(메모는 막지 않는다 — 후보를 적어 보는 건
        해롭지 않다).

        [v46.1] changed를 먼저 보내 완성 판정부터 하고, 오답이면 그
        다음에 wrongEntry를 보내 메시지가 덮어쓰도록 순서를 맞췄다 —
        그래야 위젯 쪽에서 "일단 비웠다가 오답 메시지로 채우는" 순서가
        항상 일관된다."""
        if self.state is None or self.selected is None:
            return
        r, c = self.selected
        if self.note_mode:
            self.state.toggle_note(r, c, val)
            self.update()
            self.changed.emit()
            return

        if S.digit_counts(self.state.board)[val] >= 9:
            return

        result = self.state.try_set_value(r, c, val)
        if result is None:
            return   # given 칸이거나 이미 게임 오버 — 입력 자체가 무효
        self.update()
        self.changed.emit()
        if result is False:
            self.wrongEntry.emit()
        else:
            self._check_forced_completion()
        self.livesChanged.emit(self.state.lives)
        if self.state.game_over:
            self.gameOver.emit()

    def erase_selected(self):
        if self.state is None or self.selected is None:
            return
        r, c = self.selected
        if self.state.is_given(r, c):
            return
        self.state.set_value(r, c, S.EMPTY)
        self.update()
        self.changed.emit()

    def _check_forced_completion(self):
        """[v46.3] 남은 빈 칸이 전부 후보가 하나씩만 남은(=논리적으로
        다 정해진) 상태인지 확인해서, 그렇다면 forcedCompletionReady
        신호를 보낸다. 게임이 이미 끝났으면(완성·게임오버) 확인할
        필요가 없다."""
        if self.state is None or self.state.game_over or self.state.is_complete():
            return
        mapping = S.forced_completion(self.state.board)
        if mapping:
            self.forcedCompletionReady.emit(mapping)

    # ---------------------------------------------------------------- 그리기
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if self.state is None:
            p.end()
            return

        conflicts = self.state.conflicts()
        sel = self.selected
        sel_val = None
        if sel is not None:
            v = self.state.board[sel[0]][sel[1]]
            sel_val = v if v != S.EMPTY else None

        # [v46.3 버그 수정] 전에는 "같은 숫자가 든 칸들 각각의 행·열·
        # 박스"까지 넓게 강조했는데, 그건 의도보다 과했다 — 실제로
        # 원하는 건 ① 선택한 칸의 행·열·3x3박스, ② 그 숫자와 같은
        # 숫자가 든 다른 칸들 "자체"(그 칸들의 행·열·박스로는 안
        # 넓힘) 이 둘만, 선택한 칸과 같은 배경색으로 보여주는 것이다.
        highlight = set()
        if sel is not None:
            sr0, sc0 = sel
            for i in range(9):
                highlight.add((sr0, i))
                highlight.add((i, sc0))
            br, bc = (sr0 // 3) * 3, (sc0 // 3) * 3
            for i in range(br, br + 3):
                for j in range(bc, bc + 3):
                    highlight.add((i, j))
            if sel_val is not None:
                for r in range(9):
                    for c in range(9):
                        if self.state.board[r][c] == sel_val:
                            highlight.add((r, c))

        for r in range(9):
            for c in range(9):
                rect = self._cell_rect(r, c)
                fill = None
                if sel == (r, c):
                    fill = _SELECT_FILL
                elif (r, c) in highlight:
                    fill = _SELECT_FILL
                if fill:
                    p.fillRect(rect, QColor(fill))

        # 숫자(확정) · 메모(후보)
        big_font = QFont("Arial", 20)
        bold_font = QFont("Arial", 20)
        bold_font.setBold(True)
        note_font = QFont("Arial", 7)
        for r in range(9):
            for c in range(9):
                rect = self._cell_rect(r, c)
                val = self.state.board[r][c]
                if val != S.EMPTY:
                    is_given = self.state.is_given(r, c)
                    if (r, c) in conflicts:
                        color = _CONFLICT_COLOR
                    elif is_given:
                        color = _GIVEN_COLOR
                    else:
                        color = _ENTRY_COLOR
                    p.setFont(bold_font if is_given else big_font)
                    p.setPen(QColor(color))
                    p.drawText(rect, Qt.AlignCenter, str(val))
                else:
                    notes = self.state.notes[r][c]
                    if notes:
                        p.setFont(note_font)
                        p.setPen(QColor(_NOTE_COLOR))
                        sub_w, sub_h = _CELL / 3.0, _CELL / 3.0
                        for n in notes:
                            idx = n - 1
                            sub_rect = QRectF(rect.left() + (idx % 3) * sub_w,
                                              rect.top() + (idx // 3) * sub_h, sub_w, sub_h)
                            p.drawText(sub_rect, Qt.AlignCenter, str(n))

        # 격자선(3x3 경계는 굵게)
        for i in range(10):
            thick = (i % 3 == 0)
            p.setPen(QPen(QColor(_THICK_LINE if thick else _THIN_LINE), 2.4 if thick else 1.0))
            x = _MARGIN + i * _CELL
            p.drawLine(QPointF(x, _MARGIN), QPointF(x, _MARGIN + _GRID))
            y = _MARGIN + i * _CELL
            p.drawLine(QPointF(_MARGIN, y), QPointF(_MARGIN + _GRID, y))

        # [v46.5] 선택한 칸의 테두리뿐 아니라, 같은 숫자가 든 다른 칸
        # 들에도 똑같은 테두리를 그린다 — 배경 강조와 똑같이 "이 숫자가
        # 어디 어디 있는지"가 테두리로도 바로 보이게 한다.
        if sel is not None:
            p.setPen(QPen(QColor(C.UTIL_MAIN), 2.6))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self._cell_rect(*sel).adjusted(1, 1, -1, -1))
            if sel_val is not None:
                for r in range(9):
                    for c in range(9):
                        if (r, c) != sel and self.state.board[r][c] == sel_val:
                            p.drawRect(self._cell_rect(r, c).adjusted(1, 1, -1, -1))

        p.end()


# =============================================================================
class SudokuWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.difficulty = "medium"
        self._build_ui()
        self._load_settings()
        self._start_new_game()
        self.retranslate()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        self.canvas = _SudokuCanvas()
        self.canvas.changed.connect(self._on_changed)
        self.canvas.wrongEntry.connect(self._on_wrong_entry)
        self.canvas.gameOver.connect(self._on_game_over)
        self.canvas.forcedCompletionReady.connect(self._on_forced_completion_ready)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        center_row.addWidget(self.canvas)
        center_row.addStretch(1)
        center_col = QVBoxLayout()
        center_col.addStretch(1)
        center_col.addLayout(center_row)
        center_col.addStretch(1)
        canvas_host = QWidget()
        canvas_host.setLayout(center_col)

        self.card_board = UK.Card()
        self.card_board.add_body(UK.canvas_frame(canvas_host), 1)

        self.card_controls = UK.Card()
        self.lives_indicator = _LivesIndicator()
        self.canvas.livesChanged.connect(self.lives_indicator.set_lives)
        self.card_controls.add_tool(self.lives_indicator)

        self.diff_group, self.diff_buttons = UK.radio_row(["", "", ""], checked_index=1)
        for b in self.diff_buttons:
            b.toggled.connect(self._on_difficulty_toggled)
        self.card_controls.add_body(UK.vstack(*self.diff_buttons))

        self.btn_new_game = UK.primary_button()
        self.btn_new_game.clicked.connect(self._start_new_game)
        self.card_controls.add_body(self.btn_new_game)

        # [v46.1] 정사각형에 가깝게 — 기본 버튼 높이(28px)보다 훨씬 높였다.
        # [v46.2] 글자 크기도 보드 숫자(20pt)와 맞췄다. secondary_button()
        # 이 이미 자체 스타일시트(배경·패딩 등)에 font-size를 박아 두고
        # 있어서 setFont()만으로는 안 먹는다 — 기존 스타일시트 뒤에
        # font-size 규칙을 덧붙여(나중에 적용된 규칙이 이긴다) 배경·
        # 패딩은 그대로 두고 글자 크기만 키운다.
        pad = QGridLayout()
        pad.setSpacing(6)
        self.digit_buttons = []
        for n in range(1, 10):
            btn = UK.secondary_button()
            btn.setText(str(n))
            btn.setFixedHeight(56)
            btn.setStyleSheet(btn.styleSheet() + "QPushButton{font-size:20px;}")
            btn.clicked.connect(lambda _c=False, v=n: self._on_digit(v))
            pad.addWidget(btn, (n - 1) // 3, (n - 1) % 3)
            self.digit_buttons.append(btn)
        self.card_controls.add_body(pad)

        self.btn_erase = UK.neutral_button()
        self.btn_erase.clicked.connect(self._on_erase)
        self.btn_note_mode = UK.toggle_button()
        self.btn_note_mode.toggled.connect(self._on_note_toggled)
        self.card_controls.add_body(UK.hrow(self.btn_erase, self.btn_note_mode))

        self.btn_hint = UK.secondary_button()
        self.btn_hint.clicked.connect(self._on_hint)
        self.card_controls.add_body(self.btn_hint)

        # [v46.5] 실패한 퍼즐을 나중에 다시 꺼내 풀 수 있는 보관함.
        self.btn_archive = UK.secondary_button()
        self.btn_archive.clicked.connect(self._on_open_archive)
        self.card_controls.add_body(self.btn_archive)

        # [v46.2] 완성·오답 메시지가 작아서 눈에 잘 안 띈다는 지적 —
        # 기본 hint_label(11px)보다 훨씬 크고 굵게 키웠다(_set_status가
        # 색과 함께 글자 크기도 매번 스타일시트로 함께 적용한다 — 색만
        # 바뀌는 setStyleSheet 호출이 글자 크기를 지워버리지 않도록).
        self.lbl_status = UK.hint_label()
        self.lbl_status.setWordWrap(True)
        self.card_controls.add_body(self.lbl_status)
        self.card_controls.body.addStretch(1)

        UK.split_lr(self, self.card_board, self.card_controls, left_stretch=1)

    # ---------------------------------------------------------------- 동작
    def _start_new_game(self):
        self.state = S.new_state(self.difficulty)
        self.canvas.set_state(self.state)
        self.lives_indicator.set_lives(self.state.lives)
        self._set_status("")
        self._update_digit_buttons()
        self.canvas.setFocus()

    def _retry_same_puzzle(self):
        """[v46.1] 라이프를 다 쓰고 "재도전"을 고르면, 같은 문제(solution·
        given)를 그대로 쓰되 보드·메모·라이프만 처음 상태로 되돌린다."""
        old = self.canvas.state
        self.state = S.SudokuState(old.solution, old.given, old.difficulty)
        self.canvas.set_state(self.state)
        self.lives_indicator.set_lives(self.state.lives)
        self._set_status("")
        self._update_digit_buttons()
        self.canvas.setFocus()

    def _on_digit(self, n):
        self.canvas.enter_value(n)
        self.canvas.setFocus()

    def _on_erase(self):
        self.canvas.erase_selected()
        self.canvas.setFocus()

    def _on_note_toggled(self, checked):
        self.canvas.set_note_mode(checked)
        self.canvas.setFocus()

    def _on_hint(self):
        """[v46.1] 힌트도 라이프를 하나 쓴다 — 게임 오버 상태면 아무
        일도 안 한다(apply_hint가 알아서 막지만, 다이얼로그가 중복으로
        뜨지 않도록 여기서도 먼저 막는다)."""
        if self.canvas.state is None or self.canvas.state.game_over:
            return
        self.canvas.state.apply_hint()
        self.canvas.update()
        self.lives_indicator.set_lives(self.canvas.state.lives)
        self._on_changed()
        if self.canvas.state.game_over:
            self._on_game_over()
            return
        self.canvas._check_forced_completion()
        self.canvas.setFocus()

    def _on_difficulty_toggled(self, checked):
        if not checked:
            return
        idx = self.diff_group.checkedId()
        if 0 <= idx < len(S.DIFFICULTY_ORDER):
            self.difficulty = S.DIFFICULTY_ORDER[idx]
            self._save_settings()

    def _on_changed(self):
        if self.canvas.state is not None and self.canvas.state.is_complete():
            self._set_status(tr("util.sudoku.complete_msg"), ok=True)
            # [v46.5] 이 퍼즐이 전에 실패해서 보관함에 들어가 있었다면
            # ― 이제 풀었으니 그 기록은 더 필요 없다.
            self._archive_remove(S.puzzle_id(self.canvas.state.solution))
        else:
            self._set_status("")
        self._update_digit_buttons()

    def _update_digit_buttons(self):
        """[v46.2] 어떤 숫자가 보드 전체에 이미 9개 다 채워졌으면(=더
        놓을 칸이 없으면) 그 숫자 버튼을 비활성화한다."""
        if self.canvas.state is None:
            return
        counts = S.digit_counts(self.canvas.state.board)
        for n, btn in zip(range(1, 10), self.digit_buttons):
            btn.setEnabled(counts[n] < 9)

    def _on_wrong_entry(self):
        """[v46.1] changed가 먼저 상태를 정리한 뒤에 이 신호가 오므로,
        여기서 오답 메시지로 덮어써도 순서가 꼬이지 않는다."""
        self._set_status(tr("util.sudoku.wrong_msg"), ok=False)

    def _on_forced_completion_ready(self, mapping):
        """[v46.3] 남은 칸이 전부 유일하게 정해졌다 — 자동으로 끝낼지
        물어본다. 라이프는 쓰지 않는다(이미 논리적으로 다 풀린 것을
        타이핑만 생략해 주는 것이지, 힌트처럼 도움을 받는 게 아니다)."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("util.sudoku.auto_complete_title"))
        box.setText(tr("util.sudoku.auto_complete_msg"))
        btn_yes = box.addButton(tr("util.sudoku.auto_complete_yes"), QMessageBox.AcceptRole)
        box.addButton(tr("util.sudoku.auto_complete_no"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_yes:
            return
        for (r, c), v in mapping.items():
            self.canvas.state.set_value(r, c, v)
        self.canvas.update()
        self._on_changed()

    def _on_game_over(self):
        """[v46.1] 라이프를 다 썼다 — 재도전/새 퍼즐을 고르는 창을 띄운다.
        [v46.5] 어느 쪽을 고르든, 지금 실패한 퍼즐을 보관함에 저장해
        나중에 다시 꺼내 볼 수 있게 한다(완성하면 보관함에서 자동으로
        지워진다)."""
        self._set_status(tr("util.sudoku.game_over_msg"), ok=False)
        self._archive_save(self.canvas.state)
        box = QMessageBox(self)
        box.setWindowTitle(tr("util.sudoku.game_over_title"))
        box.setText(tr("util.sudoku.game_over_msg"))
        btn_retry = box.addButton(tr("util.sudoku.retry"), QMessageBox.AcceptRole)
        box.addButton(tr("util.sudoku.new_puzzle"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is btn_retry:
            self._retry_same_puzzle()
        else:
            self._start_new_game()

    # ---------------------------------------------------------------- 보관함
    def _load_archive(self):
        """[v46.5] 실패한 퍼즐 목록을 불러온다 — 각 항목은
        {"puzzle_id", "difficulty", "state"} 딕셔너리."""
        if self._settings is None:
            return []
        raw = self._settings.value(_SET_ARCHIVE, "[]")
        try:
            items = json.loads(raw)
            return items if isinstance(items, list) else []
        except (ValueError, TypeError):
            return []

    def _save_archive(self, items):
        if self._settings is None:
            return
        self._settings.setValue(_SET_ARCHIVE, json.dumps(items))

    def _archive_save(self, state):
        """지금 상태를 보관함에 저장한다 — 같은 퍼즐(puzzle_id)이 이미
        있으면 최신 진행 상황으로 덮어쓴다(중복으로 쌓이지 않도록)."""
        pid = S.puzzle_id(state.solution)
        items = self._load_archive()
        items = [it for it in items if it.get("puzzle_id") != pid]
        items.append({"puzzle_id": pid, "difficulty": state.difficulty,
                      "state": state.to_dict()})
        self._save_archive(items)

    def _archive_remove(self, puzzle_id):
        items = self._load_archive()
        new_items = [it for it in items if it.get("puzzle_id") != puzzle_id]
        if len(new_items) != len(items):
            self._save_archive(new_items)

    def _archive_load(self, puzzle_id):
        items = self._load_archive()
        match = next((it for it in items if it.get("puzzle_id") == puzzle_id), None)
        if match is None:
            return
        state = S.SudokuState.from_dict(match["state"])
        self.difficulty = state.difficulty
        self.canvas.set_state(state)
        self.lives_indicator.set_lives(state.lives)
        self._set_status("")
        self._update_digit_buttons()
        self.canvas.setFocus()

    def _on_open_archive(self):
        """[v46.5] 보관함 목록 창 — 불러오기/삭제를 할 수 있다."""
        items = self._load_archive()
        if not items:
            QMessageBox.information(self, tr("util.sudoku.archive_title"),
                                    tr("util.sudoku.archive_empty"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("util.sudoku.archive_title"))
        dlg.resize(320, 280)
        lay = QVBoxLayout(dlg)

        list_widget = QListWidget()
        diff_labels = {"easy": tr("util.sudoku.easy"), "medium": tr("util.sudoku.medium"),
                      "hard": tr("util.sudoku.hard")}
        for it in items:
            board = it["state"]["board"]
            filled = sum(1 for row in board for v in row if v != S.EMPTY)
            diff_text = diff_labels.get(it.get("difficulty"), it.get("difficulty", ""))
            list_item = QListWidgetItem(f"{diff_text} — {filled}/81")
            list_item.setData(Qt.UserRole, it["puzzle_id"])
            list_widget.addItem(list_item)
        lay.addWidget(list_widget)

        btn_row = QHBoxLayout()
        btn_load = UK.primary_button()
        btn_load.setText(tr("util.sudoku.archive_load"))
        btn_delete = UK.neutral_button()
        btn_delete.setText(tr("util.sudoku.archive_delete"))
        btn_close = UK.secondary_button()
        btn_close.setText(tr("util.sudoku.archive_close"))
        btn_row.addWidget(btn_load)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        def do_load():
            sel = list_widget.currentItem()
            if sel is None:
                return
            self._archive_load(sel.data(Qt.UserRole))
            dlg.accept()

        def do_delete():
            sel = list_widget.currentItem()
            if sel is None:
                return
            self._archive_remove(sel.data(Qt.UserRole))
            list_widget.takeItem(list_widget.row(sel))

        btn_load.clicked.connect(do_load)
        btn_delete.clicked.connect(do_delete)
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

    def _set_status(self, text, ok=None):
        """상태 메시지 — 오답/게임오버는 빨간색, 완성은 기본 글자색,
        빈 문자열은 그대로 지운다. [v46.2] 색이 바뀌어도 글자 크기가
        그대로 유지되도록 매번 font-size까지 함께 스타일시트로 적용한다
        (색만 담은 스타일시트를 덮어쓰면 글자 크기가 초기화되어 버린다)."""
        self.lbl_status.setText(text)
        color = _WRONG_MSG_COLOR if ok is False else C.WINDOW_FG
        self.lbl_status.setStyleSheet(
            f"color:{color};font-size:15px;font-weight:bold;background:transparent;")

    # ---------------------------------------------------------------- 수명주기
    def has_unsaved(self):
        return False

    def _load_settings(self):
        if self._settings is None:
            return
        diff = self._settings.value(_SET_DIFFICULTY, "medium")
        if diff not in S.DIFFICULTY_ORDER:
            diff = "medium"
        self.difficulty = diff
        idx = S.DIFFICULTY_ORDER.index(diff)
        self.diff_buttons[idx].setChecked(True)

    def _save_settings(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_DIFFICULTY, self.difficulty)

    def retranslate(self):
        self.card_board.set_title(tr("util.sudoku.title"))
        self.card_controls.set_title(tr("util.sudoku.controls_title"))
        labels = [tr("util.sudoku.easy"), tr("util.sudoku.medium"), tr("util.sudoku.hard")]
        for b, lbl in zip(self.diff_buttons, labels):
            b.setText(lbl)
        self.btn_new_game.setText(tr("util.sudoku.new_game"))
        self.btn_erase.setText(tr("util.sudoku.erase"))
        self.btn_note_mode.setText(tr("util.sudoku.note_mode"))
        self.btn_hint.setText(tr("util.sudoku.hint"))
        self.btn_archive.setText(tr("util.sudoku.archive"))
        self._on_changed()


# =============================================================================
class SudokuApp(MiniApp):
    id = "sudoku"
    icon = "sudoku"
    category = "logic"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = SudokuWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


def _t(ko, en, ja):
    return {"ko": ko, "en": en, "ja": ja}


TRANSLATIONS = {
    "util.sudoku.title": _t("스도쿠", "Sudoku", "数独"),
    "util.sudoku.desc": _t(
        "9x9 스도쿠를 풉니다 — 난이도를 고르고 숫자를 채우거나 메모(연필)로 후보를 적어 보세요.",
        "Solve a 9x9 sudoku — pick a difficulty and fill in numbers, or pencil in candidates.",
        "9x9の数独を解きます — 難易度を選んで数字を入力するか、鉛筆で候補をメモできます。"),
    "util.sudoku.controls_title": _t("설정", "Settings", "設定"),
    "util.sudoku.easy": _t("쉬움", "Easy", "やさしい"),
    "util.sudoku.medium": _t("보통", "Medium", "ふつう"),
    "util.sudoku.hard": _t("어려움", "Hard", "むずかしい"),
    "util.sudoku.new_game": _t("새 게임", "New Game", "新しいゲーム"),
    "util.sudoku.erase": _t("지우기", "Erase", "消す"),
    "util.sudoku.note_mode": _t("메모", "Notes", "メモ"),
    "util.sudoku.hint": _t("힌트", "Hint", "ヒント"),
    "util.sudoku.complete_msg": _t("완성했습니다!", "Solved!", "完成しました！"),
    "util.sudoku.wrong_msg": _t("틀렸습니다! 다시 시도해 보세요.", "Wrong! Try again.", "違います！もう一度どうぞ。"),
    "util.sudoku.game_over_title": _t("재시도 횟수를 모두 썼습니다", "Out of retries", "再試行回数を使い切りました"),
    "util.sudoku.game_over_msg": _t(
        "재시도 횟수를 모두 썼습니다. 같은 문제를 다시 풀어 볼까요, 아니면 새 퍼즐을 받을까요?",
        "You're out of retries. Try the same puzzle again, or get a new one?",
        "再試行回数を使い切りました。同じ問題をもう一度解きますか、それとも新しい問題にしますか？"),
    "util.sudoku.retry": _t("재도전", "Retry", "再挑戦"),
    "util.sudoku.new_puzzle": _t("새 퍼즐", "New Puzzle", "新しい問題"),
    "util.sudoku.auto_complete_title": _t("자동 완성", "Auto-complete", "自動完成"),
    "util.sudoku.auto_complete_msg": _t(
        "남은 칸이 모두 하나의 값으로 정해졌습니다. 자동으로 완성할까요?",
        "Every remaining cell now has only one possible value. Finish automatically?",
        "残りのマスはすべて値が一つに決まりました。自動で完成させますか？"),
    "util.sudoku.auto_complete_yes": _t("완성하기", "Finish", "完成する"),
    "util.sudoku.auto_complete_no": _t("직접 풀기", "Keep solving", "自分で続ける"),
    "util.sudoku.archive": _t("보관함", "Archive", "保管庫"),
    "util.sudoku.archive_title": _t("보관함 — 못다 푼 퍼즐", "Archive — Unfinished puzzles", "保管庫 — 未完成の問題"),
    "util.sudoku.archive_empty": _t("보관함이 비어 있습니다.", "The archive is empty.", "保管庫は空です。"),
    "util.sudoku.archive_load": _t("불러오기", "Load", "読み込む"),
    "util.sudoku.archive_delete": _t("삭제", "Delete", "削除"),
    "util.sudoku.archive_close": _t("닫기", "Close", "閉じる"),
}

SudokuApp.tr_table = TRANSLATIONS

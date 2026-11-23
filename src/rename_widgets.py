# -*- coding: utf-8 -*-
"""
FolderKit — 파일명 변경 모드 전용 에디터 (구 FileRenamer.py 이식)
실시간 하이라이트(RenamerHighlighter), 줄번호 영역(LineNumberArea), 본체(CodeEditor)
"""
import re
from PySide6.QtCore import Qt, QSize, QRect, QRectF, QEvent, QPointF, QPoint, Signal
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QToolTip, QTextEdit, QApplication, QMenu
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QFont, QColor, QPainter, QTextCursor,
    QPen, QBrush, QPolygonF
)

from .styles import C
from .i18n import tr, register_translations

COLUMN_SEL_BG = "#cfe3ff"      # [v49.3] 세로(열) 선택 영역 배경
COLUMN_CARET = "#1f6feb"       # [v49.3] 여러 줄 동시 입력 커서

register_translations({
    "rename.column.menu_number": {"ko": "줄마다 일련번호 넣기 (01, 02, …)  Alt+N",
                                  "en": "Insert sequence numbers per line (01, 02, …)  Alt+N",
                                  "ja": "行ごとに連番を挿入（01, 02, …）  Alt+N"},
    "rename.column.menu_exit": {"ko": "세로 선택 끝내기  Esc", "en": "End column selection  Esc",
                                "ja": "縦選択を終了  Esc"},
    "rename.column.status": {"ko": "세로 선택: {a0}줄 — 입력하면 모든 줄에 함께 들어갑니다",
                             "en": "Column selection: {a0} lines — typing goes into every line",
                             "ja": "縦選択: {a0}行 — 入力するとすべての行に入ります"},
})

# [v11] 파일/폴더 구분을 더 선명하게: 폴더는 실제 폴더처럼 노란색으로 채우고,
# 파일은 흰 문서에 가로줄 3개를 그은 "작성된 문서" 느낌으로 표현한다.
FOLDER_FILL = "#FFC940"
FOLDER_BORDER = "#E0A415"
FILE_FILL = "#FFFFFF"
FILE_BORDER = "#9AA0A6"
FILE_LINE = "#6B7280"


def _draw_file_icon(painter, cx, cy, color=None):
    """[v11] 문서 아이콘 — 흰 바탕 + 얇은 테두리 + 가로줄 3개(작성된 문서 느낌)."""
    x0, y0, w, h = cx - 4, cy - 5, 8, 10
    fold = 3
    pts = QPolygonF([
        QPointF(x0, y0), QPointF(x0 + w - fold, y0), QPointF(x0 + w, y0 + fold),
        QPointF(x0 + w, y0 + h), QPointF(x0, y0 + h),
    ])
    painter.setPen(QPen(QColor(FILE_BORDER), 1))
    painter.setBrush(QBrush(QColor(FILE_FILL)))
    painter.drawPolygon(pts)
    painter.setPen(QPen(QColor(FILE_LINE), 1))
    for dy in (3.2, 5.4, 7.6):
        painter.drawLine(QPointF(x0 + 1.3, y0 + dy), QPointF(x0 + w - 1.3, y0 + dy))


def _draw_folder_icon(painter, cx, cy, color=None):
    """[v11] 폴더 아이콘 — 실제 폴더처럼 노란색으로 채워 파일 아이콘과 뚜렷하게 구분."""
    x0, y0, w, h = cx - 5, cy - 3, 10, 8
    painter.setPen(QPen(QColor(FOLDER_BORDER), 1))
    painter.setBrush(QBrush(QColor(FOLDER_FILL)))
    tab = QPolygonF([
        QPointF(x0, y0), QPointF(x0 + 3.5, y0), QPointF(x0 + 4.7, y0 + 1.3), QPointF(x0, y0 + 1.3),
    ])
    painter.drawPolygon(tab)
    painter.drawRoundedRect(QRectF(x0, y0 + 1, w, h - 1), 1, 1)

# =============================================================================
# 4.5 [v04] 파일명 변경(리네임) 모드 전용 에디터 — 구 FileRenamer.py 이식
#     (PyQt6 → PySide6, 색상만 FolderKit 팔레트(C.RENAME_*)에 맞춰 재조정)
# =============================================================================
class RenamerHighlighter(QSyntaxHighlighter):
    """QPlainTextEdit에 입력되는 텍스트를 실시간으로 검사하여
    원본 대비 변경 여부·오류 여부에 따라 줄 색상을 입히는 클래스."""
    def __init__(self, document, editor):
        super().__init__(document)
        self.editor = editor
        self.invalid_chars = re.compile(r'[<>:"/\\|?*]')

    def highlightBlock(self, text):
        block_num = self.currentBlock().blockNumber()
        if 0 <= block_num < len(self.editor.original_filenames):
            orig_name = self.editor.original_filenames[block_num]
            curr_text = text.strip()
            if curr_text != orig_name:
                fmt = QTextCharFormat()
                fmt.setFontWeight(QFont.Bold)
                if not curr_text or self.invalid_chars.search(curr_text):
                    fmt.setForeground(QColor(C.RENAME_ERROR))
                else:
                    fmt.setForeground(QColor(C.RENAME_CHANGED))
                self.setFormat(0, len(text), fmt)


class LineNumberArea(QWidget):
    """에디터 좌측 줄 번호 영역. 마우스 오버 시 원본 파일명 툴팁,
    클릭 시 해당 줄을 원본으로 복원."""
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            cursor = self.editor.cursorForPosition(event.pos())
            block_number = cursor.blockNumber()
            if 0 <= block_number < len(self.editor.original_filenames):
                curr_text = self.editor.document().findBlockByNumber(block_number).text().strip()
                orig_name = self.editor.original_filenames[block_number]
                if curr_text != orig_name:
                    QToolTip.showText(event.globalPos(), f"↺ {orig_name}")
                    return True
            QToolTip.hideText()
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cursor = self.editor.cursorForPosition(event.pos())
            block_number = cursor.blockNumber()
            if 0 <= block_number < len(self.editor.original_filenames):
                curr_text = self.editor.document().findBlockByNumber(block_number).text().strip()
                orig_name = self.editor.original_filenames[block_number]
                if curr_text != orig_name:
                    self.editor.revert_line(block_number)
        super().mousePressEvent(event)


class CodeEditor(QPlainTextEdit):
    """줄 번호 + 실시간 하이라이팅을 갖춘 파일명 목록 에디터.
    [v09] 파일/폴더 구분 아이콘(📄/📁)은 편집 대상이 아니므로 텍스트에 넣지 않고
    줄번호 영역(gutter)에 그린다 — line_is_dir 리스트로 각 줄이 파일인지 폴더인지 표시."""
    ICON_SLOT = 20  # gutter 안에서 아이콘이 차지하는 폭(px)

    columnModeChanged = Signal(int)   # [v49.3] 세로 선택 줄 수(0이면 끝남)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.original_filenames = []
        self.line_is_dir = []  # [v09] blockNumber -> 폴더 여부(True/False), load 시 채워짐
        self.highlighter = RenamerHighlighter(self.document(), self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.textChanged.connect(self.lineNumberArea.update)
        self.updateLineNumberAreaWidth(0)
        # [v49.3] 세로(열) 선택 — Notepad++처럼 Alt+마우스 끌기(또는 Alt+Shift+방향키)로
        # 여러 줄의 같은 세로 구간을 고르고, 입력하면 모든 줄에 같이 들어간다.
        #   _col_ranges: [(줄 번호, 시작 글자 위치, 끝 글자 위치), ...] — 줄 안에서의 위치
        #   선택 영역은 화면 x좌표(픽셀)로 정한다 — 한글은 영문보다 폭이 넓어서 글자 수로
        #   맞추면 줄마다 세로 위치가 어긋나 보이기 때문이다(Notepad++도 같은 방식).
        self._col_ranges = []
        self._col_anchor = None         # (줄 번호, x) — 끌기·Alt+Shift+방향키의 시작점
        self._col_head = None           # (줄 번호, x) — 지금 끝점
        self._col_dragging = False
        self._pre_len = 0               # 한글 조합 중인 글자 수(각 줄의 입력 위치 뒤에 임시로 들어가 있다)

    def revert_line(self, line_num):
        cursor = QTextCursor(self.document().findBlockByNumber(line_num))
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(self.original_filenames[line_num])

    # =====================================================================
    # [v49.3] 세로(열) 선택 + 여러 줄 동시 입력
    # =====================================================================
    def column_active(self):
        return bool(self._col_ranges)

    def column_ranges(self):
        return list(self._col_ranges)

    def _block_x_to_pos(self, block_no, x):
        """줄 block_no에서 화면 x좌표(뷰포트 기준)에 가장 가까운 글자 위치(줄 안 위치)."""
        block = self.document().findBlockByNumber(block_no)
        if not block.isValid():
            return 0
        rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        cur = self.cursorForPosition(QPoint(int(x), int(rect.center().y())))
        if cur.blockNumber() != block_no:
            return 0 if x <= 0 else block.length() - 1
        return cur.positionInBlock()

    def _pos_x(self, block_no, col):
        block = self.document().findBlockByNumber(block_no)
        cur = QTextCursor(block)
        cur.setPosition(block.position() + max(0, min(col, block.length() - 1)))
        return self.cursorRect(cur).left()

    def set_column_selection(self, anchor_block, anchor_x, head_block, head_x):
        """화면 x좌표 두 개와 줄 번호 두 개로 세로 사각형 선택을 만든다."""
        self._col_anchor = (anchor_block, anchor_x)
        self._col_head = (head_block, head_x)
        b0, b1 = sorted((anchor_block, head_block))
        x0, x1 = sorted((anchor_x, head_x))
        ranges = []
        for b in range(b0, b1 + 1):
            ranges.append((b, self._block_x_to_pos(b, x0), self._block_x_to_pos(b, x1)))
        self._set_ranges(ranges)

    def _set_ranges(self, ranges):
        was = len(self._col_ranges)
        self._col_ranges = [(b, min(s, e), max(s, e)) for b, s, e in ranges]
        self._pre_len = 0
        self._refresh_column_view()
        if len(self._col_ranges) != was:
            self.columnModeChanged.emit(len(self._col_ranges))

    def clear_column_selection(self):
        if not self._col_ranges:
            return
        first = self._col_ranges[0]
        self._col_ranges = []
        self._col_anchor = self._col_head = None
        self._pre_len = 0
        self.setExtraSelections([])
        cur = QTextCursor(self.document().findBlockByNumber(first[0]))
        cur.setPosition(cur.block().position() + first[2])
        self.setTextCursor(cur)
        self.viewport().update()
        self.columnModeChanged.emit(0)

    def _refresh_column_view(self):
        sels = []
        for b, s, e in self._col_ranges:
            if e <= s:
                continue
            block = self.document().findBlockByNumber(b)
            cur = QTextCursor(block)
            cur.setPosition(block.position() + s)
            cur.setPosition(block.position() + e, QTextCursor.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format.setBackground(QColor(COLUMN_SEL_BG))
            sels.append(sel)
        self.setExtraSelections(sels)
        if self._col_ranges:
            # 진짜 커서는 첫 줄 끝점에 둔다(한글 입력기 후보 창이 그 근처에 뜨도록)
            b, s, e = self._col_ranges[0]
            block = self.document().findBlockByNumber(b)
            cur = QTextCursor(block)
            cur.setPosition(block.position() + e)
            self.blockSignals(True)
            self.setTextCursor(cur)
            self.blockSignals(False)
        self.viewport().update()

    def column_replace(self, text):
        """모든 줄의 선택 구간을 text로 바꾼다(되돌리기 한 번에 묶임)."""
        if not self._col_ranges:
            return
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        new = []
        for b, s, e in self._col_ranges:
            block = self.document().findBlockByNumber(b)
            c = QTextCursor(block)
            c.setPosition(block.position() + s)
            c.setPosition(block.position() + e, QTextCursor.KeepAnchor)
            c.insertText(text)
            new.append((b, s + len(text), s + len(text)))
        cur.endEditBlock()
        self._set_ranges(new)

    def column_insert_numbers(self, start=1):
        """줄마다 일련번호(01, 02, …)를 넣는다 — 자릿수는 줄 수에 맞춘다(최소 2자리)."""
        if not self._col_ranges:
            return
        width = max(2, len(str(start + len(self._col_ranges) - 1)))
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        new = []
        for i, (b, s, e) in enumerate(self._col_ranges):
            text = str(start + i).zfill(width)
            block = self.document().findBlockByNumber(b)
            c = QTextCursor(block)
            c.setPosition(block.position() + s)
            c.setPosition(block.position() + e, QTextCursor.KeepAnchor)
            c.insertText(text)
            new.append((b, s + len(text), s + len(text)))
        cur.endEditBlock()
        self._set_ranges(new)

    def _column_delete(self, forward):
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        new = []
        any_sel = any(e > s for _b, s, e in self._col_ranges)
        for b, s, e in self._col_ranges:
            block = self.document().findBlockByNumber(b)
            line_len = block.length() - 1
            if any_sel:
                ds, de = s, e
            elif forward:
                ds, de = s, min(line_len, s + 1)
            else:
                ds, de = max(0, s - 1), s
            if de > ds:
                c = QTextCursor(block)
                c.setPosition(block.position() + ds)
                c.setPosition(block.position() + de, QTextCursor.KeepAnchor)
                c.removeSelectedText()
            new.append((b, ds, ds))
        cur.endEditBlock()
        self._set_ranges(new)

    def _column_key_extend(self, key):
        """Alt+Shift+방향키 — 키보드로 세로 선택 만들기/늘리기."""
        if self._col_anchor is None:
            c = self.textCursor()
            x = self.cursorRect(c).left()
            self._col_anchor = self._col_head = (c.blockNumber(), x)
        hb, hx = self._col_head
        if key == Qt.Key_Up:
            hb = max(0, hb - 1)
        elif key == Qt.Key_Down:
            hb = min(self.blockCount() - 1, hb + 1)
        else:
            col = self._block_x_to_pos(hb, hx)
            block = self.document().findBlockByNumber(hb)
            col = max(0, col - 1) if key == Qt.Key_Left else min(block.length() - 1, col + 1)
            hx = self._pos_x(hb, col)
        ab, ax = self._col_anchor
        self.set_column_selection(ab, ax, hb, hx)

    # ---- 이벤트 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and (e.modifiers() & Qt.AltModifier):
            pos = e.position().toPoint()
            b = self.cursorForPosition(pos).blockNumber()
            self._col_dragging = True
            self.set_column_selection(b, pos.x(), b, pos.x())
            e.accept()
            return
        if self._col_ranges:
            self.clear_column_selection()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._col_dragging:
            pos = e.position().toPoint()
            b = self.cursorForPosition(pos).blockNumber()
            ab, ax = self._col_anchor
            self.set_column_selection(ab, ax, b, pos.x())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._col_dragging and e.button() == Qt.LeftButton:
            self._col_dragging = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def event(self, e):
        # 창 전체에 걸린 Esc 단축키보다 먼저 받아서 세로 선택을 끝낸다
        if e.type() == QEvent.ShortcutOverride and self._col_ranges:
            if e.key() in (Qt.Key_Escape,) or (e.modifiers() & Qt.AltModifier and e.key() == Qt.Key_N):
                e.accept()
                return True
        return super().event(e)

    def keyPressEvent(self, e):
        key, mods = e.key(), e.modifiers()
        if (mods & Qt.AltModifier) and (mods & Qt.ShiftModifier) and \
                key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            self._column_key_extend(key)
            e.accept()
            return
        if not self._col_ranges:
            super().keyPressEvent(e)
            return
        if key == Qt.Key_Escape:
            self.clear_column_selection()
        elif (mods & Qt.AltModifier) and key == Qt.Key_N:
            self.column_insert_numbers()
        elif key == Qt.Key_Backspace:
            self._column_delete(False)
        elif key == Qt.Key_Delete:
            self._column_delete(True)
        elif (mods & Qt.ControlModifier) and key == Qt.Key_V:
            text = QApplication.clipboard().text().splitlines()
            if text:
                self.column_replace(text[0])
        elif (mods & Qt.ControlModifier) and key == Qt.Key_Z:
            self.clear_column_selection()
            self.undo()
        elif key in (Qt.Key_Left, Qt.Key_Right) and not (mods & ~Qt.KeypadModifier):
            # 모든 줄의 입력 위치를 한 칸씩 함께 옮긴다
            step = -1 if key == Qt.Key_Left else 1
            new = []
            for b, s, en in self._col_ranges:
                block = self.document().findBlockByNumber(b)
                p = (s if step < 0 else en) if en > s else max(0, min(block.length() - 1, s + step))
                new.append((b, p, p))
            self._set_ranges(new)
        elif e.text() and e.text().isprintable() and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            self.column_replace(e.text())
        elif key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown,
                     Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            self.clear_column_selection()
            super().keyPressEvent(e)
        e.accept()

    def inputMethodEvent(self, e):
        """한글 입력 — 조합 중인 글자도 모든 줄의 입력 위치에 실제로 넣어 두고(뒤의 글자를
        가리지 않게), 조합이 바뀔 때마다 바꿔 끼운다. 확정되면 확정된 글자로 바꾼다.
        한 글자를 조합하는 동안의 변경은 되돌리기 한 번으로 묶는다."""
        if not self._col_ranges:
            super().inputMethodEvent(e)
            return
        commit, pre = e.commitString(), e.preeditString()
        if not commit and not pre and not self._pre_len:
            e.accept()
            return
        cur = QTextCursor(self.document())
        if self._pre_len:
            cur.joinPreviousEditBlock()
        else:
            cur.beginEditBlock()
        text = commit + pre
        new = []
        for b, s, en in self._col_ranges:
            block = self.document().findBlockByNumber(b)
            c = QTextCursor(block)
            c.setPosition(block.position() + s)
            c.setPosition(block.position() + max(en, s + self._pre_len), QTextCursor.KeepAnchor)
            c.insertText(text)
            p = s + len(commit)
            new.append((b, p, p))
        cur.endEditBlock()
        self._col_ranges = new
        self._pre_len = len(pre)
        self._refresh_column_view()
        e.accept()

    def contextMenuEvent(self, e):
        if not self._col_ranges:
            super().contextMenuEvent(e)
            return
        menu = QMenu(self)
        act_num = menu.addAction(tr("rename.column.menu_number"))
        act_exit = menu.addAction(tr("rename.column.menu_exit"))
        chosen = menu.exec(e.globalPos())
        if chosen is act_num:
            self.column_insert_numbers()
        elif chosen is act_exit:
            self.clear_column_selection()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._col_ranges:
            return
        p = QPainter(self.viewport())
        for b, s, en in self._col_ranges:
            block = self.document().findBlockByNumber(b)
            c = QTextCursor(block)
            c.setPosition(block.position() + en)
            r0 = self.cursorRect(c)
            c.setPosition(block.position() + min(block.length() - 1, en + self._pre_len))
            r1 = self.cursorRect(c)
            if self._pre_len:
                # 조합 중인 글자에 밑줄
                p.setPen(QPen(QColor(C.WINDOW_FG), 1))
                p.drawLine(r0.left(), r0.bottom(), r1.left(), r1.bottom())
            p.setPen(QPen(QColor(COLUMN_CARET), 2))
            p.drawLine(r1.left(), r1.top(), r1.left(), r1.bottom())
        p.end()

    def lineNumberAreaWidth(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        return self.ICON_SLOT + 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor(240, 240, 240))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        height = self.fontMetrics().height()
        current_font = painter.font()
        bold_font = QFont(current_font)
        bold_font.setBold(True)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                is_changed = False
                is_invalid = False
                if 0 <= blockNumber < len(self.original_filenames):
                    current_text = block.text().strip()
                    if current_text != self.original_filenames[blockNumber]:
                        is_changed = True
                        if not current_text or re.search(r'[<>:"/\\|?*]', current_text):
                            is_invalid = True

                if is_changed:
                    painter.setFont(bold_font)
                    painter.setPen(QColor(C.RENAME_ERROR) if is_invalid else QColor(C.RENAME_CHANGED))
                else:
                    painter.setFont(current_font)
                    painter.setPen(Qt.black)

                # [v10] 줄 번호를 먼저(왼쪽), 파일/폴더 구분 아이콘을 그 다음(오른쪽)에 배치
                painter.drawText(0, top, self.lineNumberArea.width() - self.ICON_SLOT - 5, height,
                                 Qt.AlignRight | Qt.AlignVCenter, number)

                if 0 <= blockNumber < len(self.line_is_dir):
                    icon_cx = self.lineNumberArea.width() - self.ICON_SLOT // 2
                    icon_cy = top + height // 2
                    painter.setRenderHint(QPainter.Antialiasing)
                    if self.line_is_dir[blockNumber]:
                        _draw_folder_icon(painter, icon_cx, icon_cy)
                    else:
                        _draw_file_icon(painter, icon_cx, icon_cy)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            blockNumber += 1


# =============================================================================
# [v49.3] 같은 이름 자동 일련번호(순수 함수 — 헤드리스 검사용)
# =============================================================================
NUMBER_SEP = "_"


def auto_number_duplicates(names, is_dir_flags):
    """같은 이름(대소문자 무시 — 윈도우는 구분하지 않는다)이 여러 줄이면, 줄 순서대로
    확장자 앞에 _01, _02 … 를 붙인다. 자릿수는 그 묶음의 개수에 맞춘다(최소 2자리).
    반환: (새 이름 목록, [(묶음의 원래 이름, 개수), ...])"""
    import os
    groups = {}
    for i, name in enumerate(names):
        groups.setdefault(name.casefold(), []).append(i)
    out = list(names)
    numbered = []
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        width = max(2, len(str(len(idxs))))
        base_name = names[idxs[0]]
        for n, i in enumerate(idxs, 1):
            stem, ext = (names[i], "") if is_dir_flags[i] else os.path.splitext(names[i])
            out[i] = f"{stem}{NUMBER_SEP}{str(n).zfill(width)}{ext}"
        numbered.append((base_name, len(idxs)))
    return out, numbered

# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 #5: 학교 일정 [v05]

나이스(NEIS) 학사일정(SchoolSchedule) API로 그 달의 학교 행사를 받아와
달력에 보여준다. "오늘의 급식"과 인증키·학교 코드를 공유한다
(neis_common.py) — 한 번 입력해 두면 두 도구 모두에 바로 적용된다.

## 달력을 직접 그리는 이유
QCalendarWidget은 날짜 하나에 색이나 굵기 정도만 줄 수 있어서, 그 날 무슨
행사가 있는지 "글자로 바로" 보여주기 어렵다. 교사가 한눈에 "이번 달에
뭐가 있더라"를 확인하려면 칸 안에 행사 이름이 직접 보이는 편이 훨씬
유용하다고 판단해, 계산기 키패드·카르노맵 격자와 같은 방식으로
QGridLayout에 칸을 직접 배치했다.
"""
import calendar as _cal
from datetime import date

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QColor, QPainter, QPageLayout
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QDialog, QLineEdit, QTextEdit,
    QFileDialog, QMessageBox, QDialogButtonBox
)

from ..i18n import tr
from ..styles import C, BTN_DESTRUCTIVE_BG
from . import ui_kit as UK
from .base import MiniApp
from . import schedule_solve as S
from . import schedule_local as SL
from . import print_grid as PG
from . import neis_common as N
from .neis_common import NeisSettingsPanel

# 한국 학교 달력의 일반적인 관례대로 일요일부터 시작.
_WEEKDAY_KEYS = ["util.schedule.wd.sun", "util.schedule.wd.mon", "util.schedule.wd.tue",
                 "util.schedule.wd.wed", "util.schedule.wd.thu", "util.schedule.wd.fri",
                 "util.schedule.wd.sat"]
MAX_CHIPS_PER_DAY = 3


class _DayCell(QFrame):
    """달력의 칸 하나. 그 날짜의 행사 이름을 작은 칩으로 몇 개까지 보여주고,
    클릭하면 아래 상세 패널에 전체 내용을 띄운다."""

    def __init__(self, day, in_month, is_today, parent=None):
        super().__init__(parent)
        self.day = day
        self.events = []
        self.setObjectName("dayCell")
        self.setMinimumHeight(74)
        self.setCursor(Qt.PointingHandCursor if in_month else Qt.ArrowCursor)
        self._in_month = in_month
        self._is_today = is_today
        self._selected = False
        self._apply_style()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)

        self.lbl_day = QLabel(str(day) if day else "")
        weight = "bold" if is_today else "normal"
        color = C.UTIL_MAIN if is_today else (C.WINDOW_FG if in_month else "#c6c9ce")
        self.lbl_day.setStyleSheet(
            f"color:{color};font-weight:{weight};font-size:12px;"
            "background:transparent;border:none;")
        lay.addWidget(self.lbl_day)

        self.chip_holder = QVBoxLayout()
        self.chip_holder.setSpacing(1)
        lay.addLayout(self.chip_holder)
        lay.addStretch()

    def _apply_style(self):
        bg = "#ffffff" if self._in_month else "#fafafa"
        border = C.UTIL_MAIN if self._is_today else C.BORDER
        width = 2 if self._is_today else 1
        if self._selected:
            bg = C.UTIL_BG
        self.setStyleSheet(
            f"QFrame#dayCell{{background-color:{bg};border:{width}px solid {border};"
            "border-radius:5px;}")

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style()

    def set_events(self, combined):
        """[v09] combined는 (source, event) 튜플의 목록이다.
        source == "local" — 교사가 직접 입력한 일정(주 자료). 진하게 채운 칩.
        source == "neis"  — 나이스에서 받아온 일정(보조 참고용). 옅은 윤곽선 칩.
        로컬 일정을 먼저 보여준다 — 이게 이제는 주된 자료이기 때문이다."""
        self.events = combined
        while self.chip_holder.count():
            item = self.chip_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        shown = combined[:MAX_CHIPS_PER_DAY]
        for source, ev in shown:
            chip = QLabel(ev.name)
            chip.setWordWrap(False)
            if source == "local":
                chip.setStyleSheet(
                    f"background-color:{C.UTIL_MAIN};color:#ffffff;"
                    "font-size:10px;border-radius:3px;padding:1px 3px;border:none;")
            else:
                chip.setStyleSheet(
                    f"background-color:transparent;color:#8a8f98;"
                    f"font-size:10px;border-radius:3px;padding:0px 2px;border:1px solid {C.BORDER};")
            chip.setToolTip(ev.name + ("\n" + ev.content if ev.content else ""))
            self.chip_holder.addWidget(chip)
        if len(combined) > MAX_CHIPS_PER_DAY:
            more = QLabel(tr("util.schedule.more", a0=len(combined) - MAX_CHIPS_PER_DAY))
            more.setStyleSheet("color:#8a8f98;font-size:9px;background:transparent;border:none;")
            self.chip_holder.addWidget(more)

    def mouseReleaseEvent(self, event):
        if self._in_month and self.day and event.button() == Qt.LeftButton:
            self.clicked_day(self.day)
        super().mouseReleaseEvent(event)

    def clicked_day(self, day):
        parent = self.parent()
        while parent is not None and not hasattr(parent, "select_day"):
            parent = parent.parent()
        if parent is not None:
            parent.select_day(day)


class _EventEditDialog(QDialog):
    """[v09] 일정 추가/수정 창. 제목은 필수, 내용은 선택.
    수정일 때는 name/content를 미리 채워서 연다."""

    def __init__(self, parent, title, name="", content=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lbl_name = QLabel(tr("util.schedule.dlg.lbl_name"))
        lay.addWidget(lbl_name)
        self.edit_name = QLineEdit(name)
        lay.addWidget(self.edit_name)

        lbl_content = QLabel(tr("util.schedule.dlg.lbl_content"))
        lay.addWidget(lbl_content)
        self.edit_content = QTextEdit(content)
        self.edit_content.setFixedHeight(70)
        lay.addWidget(self.edit_content)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.edit_name.setFocus()

    def _on_accept(self):
        if not self.edit_name.text().strip():
            self.edit_name.setStyleSheet("border:1px solid #d32f2f;")
            return
        self.accept()

    def values(self):
        name = self.edit_name.text().strip()
        content = self.edit_content.toPlainText().strip() or None
        return name, content


class ScheduleWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.nam = QNetworkAccessManager(self)
        self._reply = None

        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected_day = None
        self.events_by_day = {}
        self.local_events = SL.load(self._settings)   # [v09] 로컬(직접 입력) 일정 — 전체
        self.local_by_day = {}                         # 지금 보이는 달만 골라 묶은 것
        self.office_code = N.DEFAULT_OFFICE_CODE
        self.school_code = N.DEFAULT_SCHOOL_CODE
        self.school_name = N.DEFAULT_SCHOOL_NAME
        self._cells = {}

        self._build_ui()
        self._load_settings()
        self._retranslate_static()
        self._fetch()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        office, school, school_name, key = N.load(self._settings)
        self.office_code, self.school_code, self.school_name = office, school, school_name
        self.neis_panel.set_values(key, office, school, school_name)

    def _save_settings(self):
        key, office, school, name = self.neis_panel.values()
        N.save(self._settings, key, office, school, name)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 상단 카드: 달력(툴바: ◀ 월 ▶ 오늘 ⚙ / 본문: 요일 머리글 + 달력 칸 / 하단: 엑셀·인쇄) ----
        self.neis_panel = NeisSettingsPanel()
        self.neis_panel.changed.connect(self._on_neis_settings_changed)

        self.card_cal = UK.Card()
        self.btn_prev = UK.tool_button("◀")
        self.btn_prev.clicked.connect(lambda: self._shift_month(-1))
        self.card_cal.add_tool(self.btn_prev)
        self.lbl_month = QLabel()
        self.lbl_month.setAlignment(Qt.AlignCenter)
        self.lbl_month.setFixedWidth(110)
        self.lbl_month.setFont(QFont("", 13, QFont.Bold))
        self.lbl_month.setStyleSheet(f"color:{C.WINDOW_FG};background:transparent;")
        self.card_cal.add_tool(self.lbl_month)
        self.btn_next = UK.tool_button("▶")
        self.btn_next.clicked.connect(lambda: self._shift_month(1))
        self.card_cal.add_tool(self.btn_next)
        self.btn_today = UK.secondary_button()
        self.btn_today.clicked.connect(self._go_today)
        self.card_cal.add_tool(self.btn_today)
        self.card_cal.add_tool(self.neis_panel.toggle)
        self.card_cal.add_body(self.neis_panel.panel)

        cal_host = QWidget()
        cal_host.setStyleSheet("background:transparent;")
        self.cal_grid = QGridLayout(cal_host)
        self.cal_grid.setSpacing(4)
        self.cal_grid.setContentsMargins(6, 6, 6, 6)
        self.weekday_labels = []
        for col, key in enumerate(_WEEKDAY_KEYS):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            color = BTN_DESTRUCTIVE_BG if col in (0, 6) else UK.HINT_COLOR
            lbl.setStyleSheet(f"color:{color};font-weight:bold;font-size:11px;background:transparent;")
            self.cal_grid.addWidget(lbl, 0, col)
            self.weekday_labels.append(lbl)
        for c in range(7):
            self.cal_grid.setColumnStretch(c, 1)
        self.card_cal.add_body(UK.canvas_frame(cal_host), 1)

        self.lbl_status = QLabel()
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{UK.HINT_COLOR};font-size:13px;background:transparent;padding:16px;")
        self.lbl_status.setVisible(False)
        self.card_cal.add_body(self.lbl_status)

        self.btn_import = self.card_cal.add_footer(UK.secondary_button())
        self.btn_import.clicked.connect(self._import_excel)
        self.btn_export = self.card_cal.add_footer(UK.secondary_button())
        self.btn_export.clicked.connect(self._export_excel)
        self.btn_print = self.card_cal.add_footer(UK.secondary_button())
        self.btn_print.clicked.connect(self._print)

        # ---- 하단 카드: 선택한 날의 상세(하단: 일정 추가) ----
        self.card_detail = UK.Card()
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setStyleSheet("background:transparent;")
        self.detail_scroll.setFixedHeight(130)
        self.detail_content = QWidget()
        self.detail_content.setStyleSheet("background:transparent;")
        self.detail_scroll.setWidget(self.detail_content)
        self.detail_lay = QVBoxLayout(self.detail_content)
        self.detail_lay.setSpacing(4)
        self.card_detail.add_body(UK.canvas_frame(self.detail_scroll, margin=4))
        self.btn_add_event = self.card_detail.add_footer(UK.primary_button())
        self.btn_add_event.clicked.connect(lambda: self._add_local_event(self.selected_day))
        self.btn_add_event.setEnabled(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        root.addWidget(self.card_cal, 1)
        root.addWidget(self.card_detail)

    # ------------------------------------------------------------ 달력 구성
    def select_day(self, day):
        if self.selected_day is not None and self.selected_day in self._cells:
            self._cells[self.selected_day].set_selected(False)
        self.selected_day = day
        if day in self._cells:
            self._cells[day].set_selected(True)
        self.btn_add_event.setEnabled(day is not None)
        self._render_detail()

    def _rebuild_calendar(self):
        while self.cal_grid.count() > 7:   # 요일 머리글(7개)은 남기고 칸만 지운다
            item = self.cal_grid.takeAt(7)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cells = {}

        first_weekday, days_in_month = _cal.monthrange(self.year, self.month)
        # Python calendar는 월요일=0 기준이라, 일요일 시작으로 다시 계산한다.
        start_col = (first_weekday + 1) % 7
        today = date.today()
        is_current_month = (today.year == self.year and today.month == self.month)

        row, col = 1, start_col
        for day in range(1, days_in_month + 1):
            is_today = is_current_month and day == today.day
            cell = _DayCell(day, True, is_today)
            self.cal_grid.addWidget(cell, row, col)
            self._cells[day] = cell
            col += 1
            if col > 6:
                col = 0
                row += 1

        for r in range(1, row + 1):
            self.cal_grid.setRowStretch(r, 1)

    def _apply_events(self):
        self.local_by_day = SL.events_for_month(self.local_events, self.year, self.month)
        for day, cell in self._cells.items():
            local = [("local", e) for e in self.local_by_day.get(day, [])]
            neis = [("neis", e) for e in self.events_by_day.get(day, [])]
            cell.set_events(local + neis)
        if self.selected_day is not None:
            self._render_detail()

    def _render_detail(self):
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if self.selected_day is None:
            hint = QLabel(tr("util.schedule.detail.hint"))
            hint.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
            self.detail_lay.addWidget(hint)
            return

        local = self.local_by_day.get(self.selected_day, [])
        neis = self.events_by_day.get(self.selected_day, [])
        if not local and not neis:
            empty = QLabel(tr("util.schedule.detail.no_event", a0=self.selected_day))
            empty.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
            self.detail_lay.addWidget(empty)
            return

        title = QLabel(tr("util.schedule.detail.title", a0=self.selected_day))
        title.setStyleSheet(f"color:{C.UTIL_MAIN};font-weight:bold;font-size:12px;background:transparent;")
        self.detail_lay.addWidget(title)

        for index, ev in enumerate(local):
            self.detail_lay.addWidget(self._build_local_row(self.selected_day, index, ev))
        for ev in neis:
            line = "[NEIS] " + ev.name + (" — " + ev.content if ev.content else "")
            lbl = QLabel("• " + line)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
            self.detail_lay.addWidget(lbl)
        self.detail_lay.addStretch()

    def _build_local_row(self, day, index, ev):
        """[v09] 직접 입력한 일정 한 줄 — 수정(✎)·삭제(×) 버튼이 붙는다.
        나이스 쪽 일정은 서버가 준 참고 자료라 수정 버튼을 달지 않는다."""
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        line = ev.name + (" — " + ev.content if ev.content else "")
        lbl = QLabel("• " + line)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{C.WINDOW_FG};font-size:12px;background:transparent;")
        lay.addWidget(lbl, 1)

        btn_edit = UK.tool_button("✎")
        btn_edit.setToolTip(tr("util.schedule.btn.edit_event.tip"))
        btn_edit.clicked.connect(lambda: self._edit_local_event(day, index))
        lay.addWidget(btn_edit, 0, Qt.AlignTop)

        btn_del = UK.tool_button("×")
        btn_del.setToolTip(tr("util.schedule.btn.delete_event.tip"))
        btn_del.clicked.connect(lambda: self._delete_local_event(day, index))
        lay.addWidget(btn_del, 0, Qt.AlignTop)

        return row

    # ------------------------------------------------------- [v09] 로컬 일정 CRUD
    def _save_local(self):
        SL.save(self._settings, self.local_events)

    def _add_local_event(self, day):
        if day is None:
            return
        dlg = _EventEditDialog(self, title=tr("util.schedule.dlg.add_title"))
        if dlg.exec():
            name, content = dlg.values()
            if not name:
                return
            ymd = f"{self.year:04d}{self.month:02d}{day:02d}"
            self.local_events.append(SL.LocalEvent(ymd, name, content))
            self._save_local()
            self._apply_events()
            if self.host:
                self.host.log(tr("util.schedule.log.event_added", a0=ymd, a1=name))

    def _edit_local_event(self, day, index):
        entries = self.local_by_day.get(day, [])
        if index >= len(entries):
            return
        ev = entries[index]
        dlg = _EventEditDialog(self, title=tr("util.schedule.dlg.edit_title"),
                               name=ev.name, content=ev.content or "")
        if dlg.exec():
            name, content = dlg.values()
            if not name:
                return
            ev.name, ev.content = name, content
            self._save_local()
            self._apply_events()

    def _delete_local_event(self, day, index):
        entries = self.local_by_day.get(day, [])
        if index >= len(entries):
            return
        ev = entries[index]
        self.local_events.remove(ev)
        self._save_local()
        self._apply_events()

    # ------------------------------------------------------------- 엑셀
    def _import_excel(self):
        try:
            import openpyxl  # noqa
        except ImportError:
            QMessageBox.information(self, tr("util.schedule.msg.excel_title"),
                                    tr("util.schedule.msg.need_openpyxl"))
            return

        path, _ = QFileDialog.getOpenFileName(
            self, tr("util.schedule.msg.import_title"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            result = SL.import_excel(path)
        except OSError as e:
            QMessageBox.warning(self, tr("util.schedule.msg.excel_title"),
                                tr("util.schedule.msg.excel_fail", a0=str(e)))
            return

        self.local_events, added, updated = SL.merge_events(self.local_events, result.events)
        self._save_local()
        self._apply_events()
        if self.host:
            self.host.status(tr("util.schedule.status.imported", a0=added, a1=updated, a2=result.skipped))
            self.host.log(tr("util.schedule.log.imported", a0=path, a1=added, a2=updated))

    def _export_excel(self):
        try:
            import openpyxl  # noqa
        except ImportError:
            QMessageBox.information(self, tr("util.schedule.msg.excel_title"),
                                    tr("util.schedule.msg.need_openpyxl"))
            return
        if not self.local_events:
            QMessageBox.information(self, tr("util.schedule.msg.excel_title"),
                                    tr("util.schedule.msg.no_local_events"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.schedule.msg.excel_title"), "school_schedule.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            SL.export_excel(path, self.local_events)
        except OSError as e:
            QMessageBox.warning(self, tr("util.schedule.msg.excel_title"),
                                tr("util.schedule.msg.excel_fail", a0=str(e)))
            return
        if self.host:
            self.host.status(tr("util.schedule.status.excel_saved", a0=path))
            self.host.log(tr("util.schedule.log.excel_saved", a0=path))

    # ------------------------------------------------------------- 인쇄
    def _print(self):
        """[버그 수정 — 근본 원인] HTML `<table>` 인쇄(이전 두 차례 수정
        포함)는 실제 프린터에서 여전히 부족했다 — 칸 내용이 짧으면 표
        전체가 지정한 폭보다 좁게 자동으로 줄어들고, 그 줄어든 표가
        한쪽으로 치우쳐 배치되어 좌우 여백이 크게(비대칭으로) 남았다.
        오늘의 급식과 같은 이유로, 이제 표를 HTML로 만들지 않고
        `print_grid` 모듈로 **직접 그린다** — 여백·칸 폭이 지정한 그대로
        나오고, 칸이 페이지 경계에 걸치면 그리기 전에 새 페이지로 넘겨
        중간에 잘리는 일도 없다. 제목뿐 아니라 상세 내용(content)도
        함께 보여준다."""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(QPageLayout.Landscape)
        printer.setFullPage(True)   # 프린터 드라이버가 강요하는 여백을 무시하고 우리가 직접 정한다

        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(tr("util.schedule.print.dialog_title"))
        if not dlg.exec():
            return
        printer.setFullPage(True)   # 대화상자가 되돌릴 수 있으니 확정 후 다시 강제

        headers = [tr(k) for k in _WEEKDAY_KEYS]
        title = tr("util.schedule.month_label", a0=self.year, a1=self.month)
        week_rows = self._print_grid_weeks()

        painter = QPainter(printer)
        PG.print_calendar(printer, painter, title, C.UTIL_MAIN, headers, week_rows,
                          margin_pt=3 * 2.83465)
        painter.end()
        if self.host:
            self.host.log(tr("util.schedule.log.printed"))

    def _print_grid_weeks(self):
        """이번 달 전체를 일~토 7칸짜리 주(week) 목록으로 만든다. 각
        칸에는 제목과 상세 내용(content)을 함께 담는다(이전엔 제목만
        나왔다)."""
        first_weekday, days_in_month = _cal.monthrange(self.year, self.month)
        start_col = (first_weekday + 1) % 7  # 0=일요일 시작
        today = date.today()

        def _lines_for(day, is_today):
            fg = "#ffffff" if is_today else None
            out = [(str(day), fg or "#444444", True, 12)]
            for e in self.local_by_day.get(day, []):
                text = e.name + (f" — {e.content}" if e.content else "")
                out.append((text, fg or "#000000", False, 10))
            for e in self.events_by_day.get(day, []):
                text = f"[NEIS] {e.name}" + (f" — {e.content}" if e.content else "")
                out.append((text, fg or "#666666", False, 10))
            return out

        weeks = []
        cells = [PG.GridCell([]) for _ in range(start_col)]
        for day in range(1, days_in_month + 1):
            is_today = (self.year == today.year and self.month == today.month and day == today.day)
            cells.append(PG.GridCell(_lines_for(day, is_today),
                                     bg=QColor(C.UTIL_MAIN) if is_today else None))
            if len(cells) == 7:
                weeks.append(cells)
                cells = []
        if cells:
            while len(cells) < 7:
                cells.append(PG.GridCell([]))
            weeks.append(cells)
        return weeks

    # ---------------------------------------------------------------- 조작
    def _on_neis_settings_changed(self):
        _key, office, school, name = self.neis_panel.values()
        self.office_code, self.school_code, self.school_name = office, school, name
        self._save_settings()
        self._fetch()

    def _shift_month(self, delta):
        m = self.month - 1 + delta
        self.year += m // 12
        self.month = m % 12 + 1
        self.selected_day = None
        self._fetch()

    def _go_today(self):
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected_day = today.day
        self._fetch()

    # ---------------------------------------------------------------- 요청
    def _fetch(self):
        self._update_month_label()
        self._rebuild_calendar()
        self._apply_events()   # [v09] 로컬 일정은 네트워크와 무관하게 항상 바로 보인다
        self._render_detail()

        key, _o, _s, _n = self.neis_panel.values()
        if not key:
            self._show_status(tr("util.schedule.status.need_key"))
            return
        self._hide_status()

        if self._reply is not None:
            self._reply.abort()
            self._reply = None

        last_day = _cal.monthrange(self.year, self.month)[1]
        ymd_from = f"{self.year:04d}{self.month:02d}01"
        ymd_to = f"{self.year:04d}{self.month:02d}{last_day:02d}"
        url = S.build_url(key, self.office_code, self.school_code, ymd_from, ymd_to)
        req = QNetworkRequest(QUrl(url))
        reply = self.nam.get(req)
        self._reply = reply
        reply.finished.connect(lambda: self._on_reply_finished(reply))

    def _on_reply_finished(self, reply):
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None

        if reply.error() != QNetworkReply.NoError:
            if reply.error() != QNetworkReply.OperationCanceledError:
                self._show_status(tr("util.schedule.status.network_error", a0=reply.errorString()))
                if self.host:
                    self.host.log(tr("util.schedule.log.network_error", a0=reply.errorString()))
            reply.deleteLater()
            return

        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        result = S.parse(raw)
        self._render(result)

    def _render(self, result: S.ScheduleResult):
        if result.status == "error":
            msg = result.message or tr("util.schedule.status.unknown_error")
            self._show_status(tr("util.schedule.status.error", a0=msg))
            if self.host:
                self.host.log(tr("util.schedule.log.error", a0=msg))
            return

        self._hide_status()
        self.events_by_day = S.events_by_day(result.events) if result.status == "ok" else {}
        self._apply_events()
        if self.host:
            self.host.status(tr("util.schedule.status.done", a0=len(result.events)))
            self.host.log(tr("util.schedule.log.done",
                             a0=f"{self.year}-{self.month:02d}", a1=len(result.events)))

    def _show_status(self, text):
        self.lbl_status.setText(text)
        self.lbl_status.setVisible(True)

    def _hide_status(self):
        self.lbl_status.setVisible(False)

    # ------------------------------------------------------------- 다국어
    def _update_month_label(self):
        self.lbl_month.setText(tr("util.schedule.month_label", a0=self.year, a1=self.month))

    def _retranslate_static(self):
        self.neis_panel.retranslate()
        self.card_cal.set_title(tr("util.schedule.title"))
        self.card_detail.set_title(tr("util.schedule.card.detail"))
        self.btn_today.setText(tr("util.schedule.btn.today"))
        self.btn_import.setText(tr("util.schedule.btn.import"))
        self.btn_import.setToolTip(tr("util.schedule.btn.import.tip"))
        self.btn_export.setText(tr("util.schedule.btn.export"))
        self.btn_export.setToolTip(tr("util.schedule.btn.export.tip"))
        self.btn_print.setText(tr("util.schedule.btn.print"))
        self.btn_print.setToolTip(tr("util.schedule.btn.print.tip"))
        self.btn_add_event.setText(tr("util.schedule.btn.add_event"))
        for lbl, key in zip(self.weekday_labels, _WEEKDAY_KEYS):
            lbl.setText(tr(key))
        self._update_month_label()
        self._render_detail()

    def retranslate(self):
        self._retranslate_static()
        self._fetch()


# =============================================================================
class ScheduleApp(MiniApp):
    id = "schedule"
    icon = "schedule"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = ScheduleWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()


# =============================================================================
TRANSLATIONS = {
    "util.schedule.card.detail": {"ko": "선택한 날의 일정", "en": "Selected day", "ja": "選択した日の予定"},
    "util.schedule.title": {
        "ko": "학교 일정", "en": "School Schedule", "ja": "学校日程"},
    "util.schedule.desc": {
        "ko": "나이스 개방포털에서 월별 학사일정을 달력으로 보여줍니다(인터넷 연결 필요).",
        "en": "Shows the monthly school schedule as a calendar from the NEIS open data portal (needs internet).",
        "ja": "NEIS開放ポータルから月別の学校日程をカレンダーで表示します（インターネット接続が必要）。"},

    "util.schedule.btn.today": {"ko": "이번 달", "en": "This month", "ja": "今月"},
    "util.schedule.month_label": {
        "ko": "{a0}년 {a1}월", "en": "{a0}-{a1:02d}", "ja": "{a0}年{a1}月"},

    "util.schedule.wd.sun": {"ko": "일", "en": "Sun", "ja": "日"},
    "util.schedule.wd.mon": {"ko": "월", "en": "Mon", "ja": "月"},
    "util.schedule.wd.tue": {"ko": "화", "en": "Tue", "ja": "火"},
    "util.schedule.wd.wed": {"ko": "수", "en": "Wed", "ja": "水"},
    "util.schedule.wd.thu": {"ko": "목", "en": "Thu", "ja": "木"},
    "util.schedule.wd.fri": {"ko": "금", "en": "Fri", "ja": "金"},
    "util.schedule.wd.sat": {"ko": "토", "en": "Sat", "ja": "土"},

    "util.schedule.more": {
        "ko": "+{a0}개 더", "en": "+{a0} more", "ja": "他{a0}件"},
    "util.schedule.detail.hint": {
        "ko": "달력에서 날짜를 클릭하면 그날의 일정이 여기에 보입니다.",
        "en": "Click a date on the calendar to see that day's events here.",
        "ja": "カレンダーで日付をクリックすると、その日の予定がここに表示されます。"},
    "util.schedule.detail.title": {
        "ko": "{a0}일의 일정", "en": "Events on the {a0}", "ja": "{a0}日の予定"},
    "util.schedule.detail.no_event": {
        "ko": "{a0}일에는 등록된 일정이 없습니다.",
        "en": "No events on the {a0}.",
        "ja": "{a0}日には登録された予定がありません。"},

    "util.schedule.status.need_key": {
        "ko": "나이스 학사일정을 함께 보려면 위 '학교 설정'에 인증키를 입력하세요. "
              "(직접 입력한 일정은 인증키 없이도 그대로 쓸 수 있습니다.)",
        "en": "To also see NEIS school events, enter your API key in 'School settings' above. "
              "(Your own entries work without a key.)",
        "ja": "NEIS学事日程も見るには上の「学校の設定」に認証キーを入力してください。"
              "（自分で入力した予定はキーなしでも使えます。）"},
    "util.schedule.status.error": {
        "ko": "일정을 받아오지 못했습니다.\n서버 응답: {a0}",
        "en": "Couldn't fetch the schedule.\nServer message: {a0}",
        "ja": "日程を取得できませんでした。\nサーバー応答: {a0}"},
    "util.schedule.status.unknown_error": {
        "ko": "알 수 없는 오류입니다. 인증키와 학교 코드를 확인해 주세요.",
        "en": "Unknown error. Please check your API key and school codes.",
        "ja": "不明なエラーです。認証キーと学校コードを確認してください。"},
    "util.schedule.status.network_error": {
        "ko": "인터넷에 연결할 수 없습니다.\n({a0})",
        "en": "Couldn't reach the internet.\n({a0})",
        "ja": "インターネットに接続できません。\n({a0})"},
    "util.schedule.status.done": {
        "ko": "이번 달 일정 {a0}건", "en": "{a0} events this month", "ja": "今月の予定{a0}件"},

    "util.schedule.log.done": {
        "ko": "[학교일정] {a0} 일정 {a1}건을 불러왔습니다",
        "en": "[Schedule] Loaded {a1} events for {a0}",
        "ja": "[学校日程] {a0}の予定{a1}件を読み込みました"},
    "util.schedule.log.error": {
        "ko": "[학교일정] 오류: {a0}", "en": "[Schedule] Error: {a0}", "ja": "[学校日程] エラー: {a0}"},
    "util.schedule.log.network_error": {
        "ko": "[학교일정] 네트워크 오류: {a0}",
        "en": "[Schedule] Network error: {a0}",
        "ja": "[学校日程] ネットワークエラー: {a0}"},

    "util.schedule.btn.add_event": {
        "ko": "+ 이 날에 일정 추가", "en": "+ Add event on this day", "ja": "+ この日に予定を追加"},
    "util.schedule.btn.edit_event.tip": {
        "ko": "이 일정을 수정합니다.", "en": "Edit this event.", "ja": "この予定を編集します。"},
    "util.schedule.btn.delete_event.tip": {
        "ko": "이 일정을 삭제합니다.", "en": "Delete this event.", "ja": "この予定を削除します。"},
    "util.schedule.dlg.add_title": {
        "ko": "일정 추가", "en": "Add Event", "ja": "予定を追加"},
    "util.schedule.dlg.edit_title": {
        "ko": "일정 수정", "en": "Edit Event", "ja": "予定を編集"},
    "util.schedule.dlg.lbl_name": {
        "ko": "제목", "en": "Title", "ja": "タイトル"},
    "util.schedule.dlg.lbl_content": {
        "ko": "내용(선택)", "en": "Content (optional)", "ja": "内容（任意）"},
    "util.schedule.log.event_added": {
        "ko": "[학교일정] {a0}에 '{a1}' 일정을 추가했습니다",
        "en": "[Schedule] Added '{a1}' on {a0}",
        "ja": "[学校日程] {a0}に「{a1}」を追加しました"},

    "util.schedule.btn.import": {"ko": "엑셀 가져오기", "en": "Import Excel", "ja": "Excel取り込み"},
    "util.schedule.btn.import.tip": {
        "ko": "엑셀 파일(날짜/제목/내용 열)에서 일정을 한꺼번에 가져옵니다.",
        "en": "Bulk-imports events from an Excel file (date/title/content columns).",
        "ja": "Excelファイル（日付・タイトル・内容の列）から予定を一括で取り込みます。"},
    "util.schedule.btn.export": {"ko": "엑셀 출력", "en": "Export Excel", "ja": "Excel出力"},
    "util.schedule.btn.export.tip": {
        "ko": "직접 입력한 일정 전체를 엑셀 파일로 저장합니다.",
        "en": "Saves all your own events to an Excel file.",
        "ja": "自分で入力したすべての予定をExcelファイルに保存します。"},
    "util.schedule.btn.print": {"ko": "인쇄", "en": "Print", "ja": "印刷"},
    "util.schedule.btn.print.tip": {
        "ko": "이번 달 달력을 인쇄합니다.", "en": "Prints this month's calendar.",
        "ja": "今月のカレンダーを印刷します。"},
    "util.schedule.print.dialog_title": {
        "ko": "학교 일정 인쇄", "en": "Print School Schedule", "ja": "学校日程を印刷"},

    "util.schedule.msg.excel_title": {
        "ko": "학교 일정 엑셀", "en": "School Schedule Excel", "ja": "学校日程Excel"},
    "util.schedule.msg.import_title": {
        "ko": "엑셀에서 일정 가져오기", "en": "Import Events from Excel", "ja": "Excelから予定を取り込む"},
    "util.schedule.msg.need_openpyxl": {
        "ko": "엑셀 기능에는 openpyxl 패키지가 필요합니다.\n"
              "명령 프롬프트에서 pip install openpyxl 실행 후 다시 시도해 주세요.",
        "en": "Excel features need the openpyxl package.\n"
              "Run \"pip install openpyxl\" and try again.",
        "ja": "Excel機能には openpyxl パッケージが必要です。\n"
              "\"pip install openpyxl\" を実行してから再度お試しください。"},
    "util.schedule.msg.no_local_events": {
        "ko": "출력할 직접 입력한 일정이 없습니다.",
        "en": "You have no events of your own to export yet.",
        "ja": "出力する自分の予定がまだありません。"},
    "util.schedule.msg.excel_fail": {
        "ko": "파일을 처리하지 못했습니다: {a0}",
        "en": "Couldn't process the file: {a0}",
        "ja": "ファイルを処理できませんでした: {a0}"},
    "util.schedule.status.imported": {
        "ko": "새 일정 {a0}건 추가, {a1}건 갱신(건너뜀 {a2}건).",
        "en": "Added {a0} new events, updated {a1} (skipped {a2}).",
        "ja": "新規{a0}件追加、{a1}件更新（スキップ{a2}件）。"},
    "util.schedule.status.excel_saved": {
        "ko": "엑셀로 저장했습니다: {a0}", "en": "Saved to Excel: {a0}", "ja": "Excelに保存しました: {a0}"},
    "util.schedule.log.imported": {
        "ko": "[학교일정] {a0}에서 새 일정 {a1}건 추가, {a2}건 갱신",
        "en": "[Schedule] From {a0}: added {a1}, updated {a2}",
        "ja": "[学校日程] {a0}から新規{a1}件追加、{a2}件更新"},
    "util.schedule.log.excel_saved": {
        "ko": "[학교일정] 엑셀로 저장: {a0}",
        "en": "[Schedule] Exported to Excel: {a0}",
        "ja": "[学校日程] Excelに保存: {a0}"},
    "util.schedule.log.printed": {
        "ko": "[학교일정] 인쇄했습니다", "en": "[Schedule] Printed", "ja": "[学校日程] 印刷しました"},
}
ScheduleApp.tr_table = {**N.TRANSLATIONS, **TRANSLATIONS}

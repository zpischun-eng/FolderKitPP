# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 시간표 [v43.6]

나이스 교육정보 개방 포털의 공식 hisTimetable API로 학급별 시간표를
보여준다. 인증키·교육청코드·학교코드는 "오늘의 급식"·"학교 일정"과
같은 값을 그대로 쓴다(NeisSettingsPanel 공용).

나이스 응답에는 담당교사 이름이 없어서, 교사 시간표는 "과목 → 담당
교사" 매핑을 한 번 입력받아 역산한다(매핑은 이 도구 안에만 저장되고
밖으로 내보내지 않는다). 서버 오류가 나도 마지막으로 받아온 시간표를
그대로 보여주고 그 사실만 안내한다.

[v43.6] 실사용 피드백을 반영한 큰 개편:
- 교사 시간표가 "지금 고른 학급"에 갇혀 있던 문제 — 교사는 여러 반을
  가르치므로, 한 학급의 슬롯만으로는 절대 완전한 교사 시간표를 만들 수
  없었다. "전체 과목 다운로드"가 훑어 온 전체 학급 데이터(self.survey)를
  교사 시간표에도 그대로 쓴다.
- 학급 시간표는 과목 아래 "담당교사" 이름을, 교사 시간표는 과목 아래
  "그 반"을 보여준다(전에는 둘 다 의미 없는 교실 번호였다).
- 학년·반은 스피너 대신 콤보박스, 교사 모드에서는 아예 숨고 "교사
  선택" 콤보만 보인다.
- 오른쪽 별도 패널을 없애고, 모든 조작을 표 위 한 줄에 모았다 — 표가
  화면 대부분을 쓴다. 교시 행 높이도 전부 똑같이 맞춘다.
- "전체 학급 조사"와 "전체 과목 목록 다운로드"를 버튼 하나로 합쳤다.
"""
from datetime import date, timedelta

from PySide6.QtCore import Qt, QUrl, QEventLoop, QTimer, QRectF
from PySide6.QtGui import QPageLayout, QPainter
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
    QApplication, QComboBox, QDialog
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import timetable_solve as TT
from .neis_common import NeisSettingsPanel
from . import neis_common as N

_SET_GRADE = "util.timetable.grade"
_SET_CLASS = "util.timetable.class"
_SET_MAPPING = "util.timetable.mapping"
_SET_SURVEY = "util.timetable.survey"
_SET_CACHE = "util.timetable.cache"

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri"]
_GRADE_OPTIONS = [str(g) for g in range(1, 7)]
_CLASS_OPTIONS = [str(c) for c in range(1, 16)]
_ROW_HEIGHT = 72   # [v43.7] 모든 교시 행을 이 높이로 통일(전보다 더 크게) — 내용량에 따라 들쭉날쭉해지지 않게



class TimetableWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.nam = QNetworkAccessManager(self)
        self._reply = None
        self.slots = []             # 지금 고른 학급의 이번 주 시간표
        self.mapping = {}           # {과목명: 담당교사}
        self.survey = {}            # {(학년,반): [TimetableSlot, ...]} — "전체 과목 다운로드"가 채움
        self.view_mode = "class"    # "class" | "teacher"
        self._current_date = date.today()
        self._build_ui()
        self._load_settings()
        self.retranslate()
        self._fetch()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        self.card = UK.Card()

        self.btn_prev = UK.tool_button("◀")
        self.btn_prev.clicked.connect(lambda: self._shift_week(-1))
        self.card.add_tool(self.btn_prev)
        self.btn_today = UK.secondary_button()
        self.btn_today.clicked.connect(self._go_today)
        self.card.add_tool(self.btn_today)
        self.btn_next = UK.tool_button("▶")
        self.btn_next.clicked.connect(lambda: self._shift_week(1))
        self.card.add_tool(self.btn_next)
        self.lbl_week = UK.body_label()
        self.card.add_tool(self.lbl_week)

        self.neis_panel = NeisSettingsPanel()
        self.neis_panel.changed.connect(self._on_neis_settings_changed)
        self.card.add_tool(self.neis_panel.toggle)
        self.card.add_body(self.neis_panel.panel)

        # [v43.6] 오른쪽 패널을 없애고, 조작을 전부 표 바로 위 한 줄에
        # 모았다 — 학급/교사 라디오, (학급 모드) 학년·반 콤보 또는
        # (교사 모드) 교사 선택 콤보, 오른쪽 끝에 교사 모드 전용 버튼 2개.
        self.view_mode_group, view_mode_buttons = UK.radio_row(["", ""], checked_index=0)
        self.radio_class_view, self.radio_teacher_view = view_mode_buttons
        self.view_mode_group.idClicked.connect(self._on_view_mode_selected)

        self.lbl_grade = UK.body_label()
        self.combo_grade = QComboBox()
        self.combo_grade.addItems(_GRADE_OPTIONS)
        self.combo_grade.currentIndexChanged.connect(self._on_class_selector_changed)
        self.lbl_class = UK.body_label()
        self.combo_class = QComboBox()
        self.combo_class.addItems(_CLASS_OPTIONS)
        self.combo_class.currentIndexChanged.connect(self._on_class_selector_changed)

        self.lbl_teacher = UK.body_label()
        self.lbl_teacher.setVisible(False)
        self.combo_teacher = QComboBox()
        self.combo_teacher.currentIndexChanged.connect(self._on_teacher_selected)
        self.combo_teacher.setVisible(False)

        control_row = QHBoxLayout()
        control_row.addWidget(self.radio_class_view)
        control_row.addWidget(self.radio_teacher_view)
        control_row.addSpacing(12)
        control_row.addWidget(self.lbl_grade)
        control_row.addWidget(self.combo_grade)
        control_row.addWidget(self.lbl_class)
        control_row.addWidget(self.combo_class)
        control_row.addWidget(self.lbl_teacher)
        control_row.addWidget(self.combo_teacher)
        control_row.addStretch()
        self.btn_download_subjects = UK.secondary_button()
        self.btn_download_subjects.clicked.connect(self._on_download_all_subjects)
        control_row.addWidget(self.btn_download_subjects)
        self.btn_upload_teachers = UK.secondary_button()
        self.btn_upload_teachers.clicked.connect(self._on_upload_teacher_list)
        control_row.addWidget(self.btn_upload_teachers)
        self.btn_print = UK.secondary_button()
        self.btn_print.clicked.connect(self._on_print)
        control_row.addWidget(self.btn_print)
        self.card.add_body(control_row)

        self.hint_teacher = UK.hint_label()
        self.hint_teacher.setWordWrap(True)
        self.hint_teacher.setVisible(False)
        self.card.add_body(self.hint_teacher)

        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.setWordWrap(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.card.add_body(self.table, 1)

        self.lbl_cache_note = UK.hint_label()
        self.lbl_cache_note.setVisible(False)
        self.card.add_body(self.lbl_cache_note)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        root.addWidget(self.card)

    # ---------------------------------------------------------------- 조회
    def _week_bounds(self):
        monday = self._current_date - timedelta(days=self._current_date.weekday())
        friday = monday + timedelta(days=4)
        return monday, friday

    def _shift_week(self, delta):
        self._current_date += timedelta(weeks=delta)
        self._update_week_label()
        self._fetch()

    def _go_today(self):
        self._current_date = date.today()
        self._update_week_label()
        self._fetch()

    def _update_week_label(self):
        monday, friday = self._week_bounds()
        self.lbl_week.setText(f"{monday.strftime('%Y.%m.%d')} ~ {friday.strftime('%m.%d')}")

    def _on_class_selector_changed(self, _v):
        self._save_settings()
        self._fetch()

    def _on_neis_settings_changed(self):
        self._save_settings()
        self._fetch()

    def _fetch(self):
        if self.view_mode == "teacher":
            return   # 교사 모드는 self.survey만 보고, 매주 개별 조회가 필요 없다
        key, office, school, _name = self.neis_panel.values()
        if not key:
            self._show_empty(tr("util.timetable.status.need_key"))
            return
        if self._reply is not None:
            self._reply.abort()
            self._reply = None

        monday, friday = self._week_bounds()
        url = TT.build_url(key, office, school, self.combo_grade.currentText(),
                           self.combo_class.currentText(),
                           monday.strftime("%Y%m%d"), friday.strftime("%Y%m%d"))
        if self.host:
            self.host.busy_start(tr("util.timetable.status.loading"))
        req = QNetworkRequest(QUrl(url))
        reply = self.nam.get(req)
        self._reply = reply
        reply.finished.connect(lambda: self._on_reply_finished(reply))

    def _on_reply_finished(self, reply):
        if self.host:
            self.host.busy_stop()
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None

        if reply.error() != QNetworkReply.NoError:
            reply.deleteLater()
            if reply.error() != QNetworkReply.OperationCanceledError:
                self._use_cache_or_error(tr("util.timetable.status.network_error", a0=reply.errorString()))
            return

        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        result = TT.parse(raw)
        if result.status == "ok":
            self.slots = result.slots
            self._save_cache()
            self.lbl_cache_note.setVisible(False)
            self._render()
        elif result.status == "empty":
            self.slots = []
            self.lbl_cache_note.setVisible(False)
            self._render()
        else:
            msg = result.message or tr("util.timetable.status.unknown_error")
            self._use_cache_or_error(tr("util.timetable.status.error", a0=msg))

    def _use_cache_or_error(self, error_text):
        """[v41] 서버 오류가 나도 마지막으로 받아온 시간표가 있으면 그걸
        그대로 보여주고, 캐시라는 사실만 알려준다 — 화면을 비워 버리면
        수업 중에 아무 정보도 못 보게 되는 게 더 큰 문제라서다."""
        if self.slots:
            self._render()
            self.lbl_cache_note.setVisible(True)
            self.lbl_cache_note.setText(tr("util.timetable.status.cached", a0=error_text))
        else:
            self._show_empty(error_text)
        if self.host:
            self.host.log(tr("util.timetable.log.error", a0=error_text))

    def _show_empty(self, text):
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.lbl_cache_note.setVisible(True)
        self.lbl_cache_note.setText(text)

    # ---------------------------------------------------------------- 표시
    def _setup_table_grid(self, n_periods):
        days_monday, _friday = self._week_bounds()
        days = [days_monday + timedelta(days=i) for i in range(5)]
        self.table.setColumnCount(5)
        self.table.setRowCount(n_periods)
        self.table.setHorizontalHeaderLabels(
            [f"{tr('util.timetable.weekday.' + k)}\n{d.strftime('%m/%d')}" for k, d in zip(_WEEKDAY_KEYS, days)])
        self.table.setVerticalHeaderLabels([tr("util.timetable.period", a0=p) for p in range(1, n_periods + 1)])
        for r in range(n_periods):
            self.table.setRowHeight(r, _ROW_HEIGHT)   # [v43.6] 행마다 내용에 안 맞추고 전부 똑같이
        # [버그 수정] setRowCount로 표가 줄어들 때 Qt는 남는 칸의 예전
        # 내용까지 지워 주지 않는다 — 이번엔 안 채우는 칸에 지난 번(다른
        # 모드·다른 반) 렌더링 결과가 그대로 남아 있었다. 매번 싹 비우고
        # 시작한다(어차피 아래에서 실제로 수업이 있는 칸만 다시 채운다).
        self.table.clearContents()
        return days

    def _set_cell(self, row, col, line1, line2):
        text = line1 + (f"\n{line2}" if line2 else "")
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, col, item)

    def _render(self):
        if self.view_mode == "teacher":
            self._render_teacher()
        else:
            self._render_class()

    def _render_class(self):
        """[버그 수정] 과목 아래 숫자(교실 번호)는 실제로는 별 의미가
        없어서 없앴다 — 대신 그 과목의 **담당교사 이름**을 보여준다
        (매핑이 안 돼 있으면 빈 줄)."""
        by_day = TT.group_by_day(self.slots)
        n_periods = TT.max_period(self.slots)
        days = self._setup_table_grid(n_periods)
        for col, d in enumerate(days):
            ymd = d.strftime("%Y%m%d")
            day_slots = by_day.get(ymd, {})
            for period in range(1, n_periods + 1):
                slot = day_slots.get(period)
                if slot is None:
                    self._set_cell(period - 1, col, "", "")
                else:
                    self._set_cell(period - 1, col, slot.subject, self.mapping.get(slot.subject, ""))

    def _render_teacher(self):
        """[버그 수정] 교사는 여러 반을 가르치므로, 지금 고른 학급 하나의
        슬롯만으로는 절대 완전한 교사 시간표를 만들 수 없었다 —
        "전체 과목 다운로드"가 모아 온 전체 학급 데이터(self.survey)를
        가로질러 그 교사의 모든 수업을 찾는다. 과목 아래에는 교실 번호
        대신 **그 수업이 어느 반인지**를 보여준다.

        [버그 수정] "전체 과목 다운로드"를 아직 한 번도 안 돌렸으면(또는
        업로드한 매핑 엑셀만 재사용한 경우) self.survey가 비어 있어서
        교사 시간표가 통째로 빈 화면이 됐다 — 지금 조회해 둔 학급
        (self.slots)도 함께 반영해서, 최소한 그 학급에서 매핑된 교사는
        바로 보이게 한다."""
        combined_survey = dict(self.survey)
        if self.slots:
            current_key = (self.combo_grade.currentText(), self.combo_class.currentText())
            combined_survey.setdefault(current_key, self.slots)
        tv = TT.teacher_view_all_classes(combined_survey, self.mapping)
        teachers = sorted(tv.keys())
        self._refresh_teacher_combo(teachers)
        selected = self.combo_teacher.currentData()
        rows = tv.get(selected, []) if selected else []
        n_periods = max((r[3] for r in rows), default=6)
        days = self._setup_table_grid(n_periods)
        by_ymd = {d.strftime("%Y%m%d"): i for i, d in enumerate(days)}
        for grade, cls, ymd, period, subject in rows:
            col = by_ymd.get(ymd)
            if col is None or not (1 <= period <= n_periods):
                continue
            self._set_cell(period - 1, col, subject, tr("util.timetable.class_label", a0=grade, a1=cls))

        if not teachers:
            self.hint_teacher.setText(tr("util.timetable.hint.teacher_none"))
        elif selected:
            self.hint_teacher.setText(tr("util.timetable.hint.teacher_single", a0=selected))
        else:
            self.hint_teacher.setText(tr("util.timetable.hint.teacher_multi", a0=len(teachers)))

    def _refresh_teacher_combo(self, teachers):
        """교사 목록이 바뀔 때마다(매핑 업로드 등) 콤보를 다시 채운다 —
        지금 고른 교사가 새 목록에도 있으면 그대로 유지한다. 콤보를
        다시 채우는 동안은 끝까지(선택 복원까지) 신호를 막아야 한다
        — 안 그러면 currentIndexChanged → _on_teacher_selected →
        _render_teacher → 여기로 다시 들어오는 무한 재귀에 빠진다."""
        current = self.combo_teacher.currentData()
        self.combo_teacher.blockSignals(True)
        self.combo_teacher.clear()
        for name in teachers:
            self.combo_teacher.addItem(name, name)
        if current and current in teachers:
            self.combo_teacher.setCurrentIndex(self.combo_teacher.findData(current))
        elif teachers:
            self.combo_teacher.setCurrentIndex(0)
        self.combo_teacher.blockSignals(False)
        self.combo_teacher.setVisible(bool(teachers))
        self.lbl_teacher.setVisible(bool(teachers))

    def _on_teacher_selected(self, _idx):
        self._render_teacher()

    # ---------------------------------------------------------------- 모드 전환
    def _on_view_mode_selected(self, checked_id):
        self.view_mode = "teacher" if checked_id == 1 else "class"
        is_teacher = self.view_mode == "teacher"
        self.lbl_grade.setVisible(not is_teacher)
        self.combo_grade.setVisible(not is_teacher)
        self.lbl_class.setVisible(not is_teacher)
        self.combo_class.setVisible(not is_teacher)
        self.lbl_teacher.setVisible(is_teacher and self.combo_teacher.count() > 0)
        self.combo_teacher.setVisible(is_teacher and self.combo_teacher.count() > 0)
        self.hint_teacher.setVisible(is_teacher)
        self.btn_download_subjects.setVisible(is_teacher)
        self.btn_upload_teachers.setVisible(is_teacher)
        if is_teacher:
            self._render_teacher()
        else:
            self._fetch()

    # ---------------------------------------------------------------- 전체 과목 다운로드·교사 목록 업로드
    def _fetch_slots_sync(self, key, office, school, grade, cls, ymd_from, ymd_to, timeout_ms=15000):
        """"전체 과목 다운로드"에서 1~3학년 x 1~10반을 차례로 조회할 때
        쓴다 — 매 요청마다 콜백 체인을 새로 엮는 대신, 짧게 도는 로컬
        이벤트 루프로 "이번 요청이 끝날 때까지"만 기다린다(요청 하나가
        끝나야 다음 반으로 넘어갈 수 있으므로). 화면이 완전히 멈추지
        않도록 그동안도 Qt 이벤트는 계속 처리된다. 반환: (slots, ok) —
        ok가 False면 진짜 "그 반에 수업이 없음"이 아니라 요청 자체가
        실패한 것이다(호출부가 재시도할지 판단하는 데 쓴다)."""
        url = TT.build_url(key, office, school, str(grade), str(cls), ymd_from, ymd_to)
        loop = QEventLoop()
        reply = self.nam.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        loop.exec()
        timer.stop()
        if reply.error() != QNetworkReply.NoError:
            reply.deleteLater()
            return [], False
        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        result = TT.parse(raw)
        if result.status == "ok":
            return result.slots, True
        if result.status == "empty":
            return [], True   # 진짜로 그 반에 그 주 수업이 없는 것(정상)
        return [], False   # 그 밖의 오류(인증 실패, 서버 오류 등) — 재시도 대상

    def _wait_ms(self, ms):
        """짧게 대기한다(요청 사이 간격) — 나이스 서버가 너무 빠른 연속
        요청에 일부를 조용히 실패시키는 걸로 보여서(실제로 30개 중 극히
        일부 학급만 성공하는 현상이 재현됐다), 요청 사이에 살짝 쉬어
        간다. 대기 중에도 Qt 이벤트는 계속 처리된다(화면 안 멈춤)."""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def _on_download_all_subjects(self):
        """[v43.6] "전체 학급 조사"와 "전체 과목 목록 다운로드"를 버튼
        하나로 합쳤다 — 1~3학년 x 1~10반을 전부 조회해서(self.survey에
        저장, 교사 시간표가 이 데이터를 쓴다) 나온 과목을 곧바로 엑셀로
        저장한다.

        [버그 수정] "교사 시간표가 여전히 한 학급만 보인다"는 증상의
        실제 원인 — 30개 반을 쉬지 않고 연속으로 요청하면 나이스 서버가
        일부 요청을 조용히 실패시키는 것으로 보였다(실제로 재현: 거의
        대부분이 실패하고 1~2개 반만 성공). 예전엔 실패한 반을 그냥
        빈 결과로 취급해 넘어가서, 사용자는 "왜 한 반만 나오지"라고
        느낄 수밖에 없었다. 이제 ① 요청 사이에 짧게 쉬고, ② 실패한
        반은 한 번 더 재시도하고, ③ 끝나면 몇 반에서 실제로 데이터를
        받았는지 숫자로 알려준다."""
        key, office, school, _name = self.neis_panel.values()
        if not key:
            QMessageBox.information(self, tr("util.timetable.subjects.title"), tr("util.timetable.status.need_key"))
            return
        combos = [(g, c) for g in TT.SURVEY_GRADES for c in TT.SURVEY_CLASSES]
        reply = QMessageBox.question(self, tr("util.timetable.subjects.title"),
                                    tr("util.timetable.survey.confirm", a0=len(combos)),
                                    QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        monday, friday = self._week_bounds()
        ymd_from, ymd_to = monday.strftime("%Y%m%d"), friday.strftime("%Y%m%d")
        survey = {}
        failed = []
        total = len(combos)
        if self.host:
            self.host.busy_start(tr("util.timetable.survey.progress", a0=0, a1=total))
        for i, (grade, cls) in enumerate(combos, start=1):
            slots, ok = self._fetch_slots_sync(key, office, school, grade, cls, ymd_from, ymd_to)
            if ok:
                if slots:
                    survey[(str(grade), str(cls))] = slots
            else:
                failed.append((grade, cls))
            if self.host:
                self.host.busy_start(tr("util.timetable.survey.progress", a0=i, a1=total))
            QApplication.processEvents()
            self._wait_ms(150)   # 서버 쪽 순간 과부하로 실패하는 걸 줄이려는 최소한의 간격

        # 실패한 반은 한 번 더 — 대부분 일시적인 거라 재시도로 많이 회복된다
        if failed:
            still_failed = []
            for grade, cls in failed:
                slots, ok = self._fetch_slots_sync(key, office, school, grade, cls, ymd_from, ymd_to)
                if ok:
                    if slots:
                        survey[(str(grade), str(cls))] = slots
                else:
                    still_failed.append((grade, cls))
                QApplication.processEvents()
                self._wait_ms(150)
            failed = still_failed
        if self.host:
            self.host.busy_stop()

        self.survey = survey
        subjects = TT.subjects_of_survey(survey)
        self._save_settings()
        if self.view_mode == "teacher":
            self._render_teacher()
        if self.host:
            self.host.log(tr("util.timetable.log.surveyed", a0=len(subjects)))

        # [버그 수정] 몇 반에서 실제로 데이터를 받았는지 알려준다 — 조용히
        # 넘어가면 "왜 교사 시간표가 한 반밖에 없지"를 알아챌 방법이 없다.
        # (ok_count < total은 정상이다 — 많은 반이 그 주에 수업이 아예
        # 없어서 빈 결과가 나오는 건 실패가 아니다. 경고는 진짜 요청
        # 실패(failed)가 남아 있을 때만 띄운다.)
        ok_count = len(survey)
        if failed:
            QMessageBox.warning(self, tr("util.timetable.subjects.title"),
                               tr("util.timetable.survey.partial", a0=ok_count, a1=total, a2=len(failed)))

        if not subjects:
            QMessageBox.information(self, tr("util.timetable.subjects.title"), tr("util.timetable.subjects.none"))
            return
        default_name = tr("util.timetable.subjects.default_name")
        path, _ = QFileDialog.getSaveFileName(self, tr("util.timetable.subjects.title"), default_name,
                                              "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            TT.save_mapping_template(path, subjects, mapping=self.mapping)
        except ImportError:
            QMessageBox.warning(self, tr("util.timetable.subjects.title"), tr("util.bracket.roster.need_openpyxl"))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("util.timetable.subjects.title"), str(e))
            return
        if self.host:
            self.host.status(tr("util.timetable.subjects.saved", a0=path))

    def _on_upload_teacher_list(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("util.timetable.subjects.upload_title"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            uploaded = TT.read_mapping_excel(path)
        except ImportError:
            QMessageBox.warning(self, tr("util.timetable.subjects.upload_title"),
                               tr("util.bracket.roster.need_openpyxl"))
            return
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("util.timetable.subjects.upload_title"), str(e))
            return
        if not uploaded:
            QMessageBox.information(self, tr("util.timetable.subjects.upload_title"),
                                   tr("util.timetable.subjects.upload_empty"))
            return
        self.mapping.update(uploaded)   # 업로드한 값이 기존 값을 덮어씀(비어 있던 과목도 채움)
        self._save_settings()
        self._render()
        if self.host:
            self.host.log(tr("util.timetable.log.mapping_uploaded", a0=len(uploaded)))

    # ---------------------------------------------------------------- 인쇄
    def _on_print(self):
        """[v43.7] 한 장에 같은 시간표를 1/2/4번 담아 인쇄한다(잘라서 여러
        장 나눠 쓰기 좋게) — 1쪽: 가로로 꽉 채워 1번, 2쪽: 세로 방향으로
        위아래 2번, 4쪽: 가로 방향으로 2행 2열 4번."""
        if self.table.rowCount() == 0:
            return
        dlg = UK.PrintCopiesDialog(
            tr("util.timetable.print.title"), tr("util.timetable.print.hint"),
            tr("util.timetable.print.copies_1"), tr("util.timetable.print.copies_2"),
            tr("util.timetable.print.copies_4"), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        copies = dlg.result_copies()

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(QPageLayout.Portrait if copies == 2 else QPageLayout.Landscape)
        print_dlg = QPrintDialog(printer, self)
        if print_dlg.exec() != QPrintDialog.Accepted:
            return

        UK.print_pixmap_with_copies(self, printer, self.table.grab(), copies)
        if self.host:
            self.host.status(tr("util.timetable.log.printed"))

    # ---------------------------------------------------------------- 저장/불러오기
    def _save_cache(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_CACHE, TT.slots_to_json(self.slots))

    def _load_settings(self):
        if self._settings is None:
            return
        # [버그 수정] 인증키·교육청코드·학교코드를 QSettings에서 읽어 온
        # 적은 있어도(값을 쓸 때만), 이 위젯을 처음 열 때 그 값을 실제로
        # 패널 화면에 채워 넣는 코드가 빠져 있었다 — 오늘의 급식에서
        # 이미 입력해 둔 인증키가 있어도 컴시간 알리미를 열면 항상 빈
        # 칸으로 보였다. 오늘의 급식·학교 일정과 똑같이
        # NC.load()+set_values()로 채운다(세 도구가 같은 값을 그대로 공유).
        office, school, school_name, key = N.load(self._settings)
        self.neis_panel.set_values(key, office, school, school_name)
        self.combo_grade.blockSignals(True)
        self.combo_class.blockSignals(True)
        idx = self.combo_grade.findText(self._settings.value(_SET_GRADE, "1"))
        if idx >= 0:
            self.combo_grade.setCurrentIndex(idx)
        idx = self.combo_class.findText(self._settings.value(_SET_CLASS, "1"))
        if idx >= 0:
            self.combo_class.setCurrentIndex(idx)
        self.combo_grade.blockSignals(False)
        self.combo_class.blockSignals(False)
        self.mapping = TT.mapping_from_json(self._settings.value(_SET_MAPPING, ""))
        self.slots = TT.slots_from_json(self._settings.value(_SET_CACHE, ""))
        self.survey = TT.survey_from_json(self._settings.value(_SET_SURVEY, ""))
        self._update_week_label()

    def _save_settings(self):
        if self._settings is None:
            return
        key, office, school, school_name = self.neis_panel.values()
        N.save(self._settings, key, office, school, school_name)
        self._settings.setValue(_SET_GRADE, self.combo_grade.currentText())
        self._settings.setValue(_SET_CLASS, self.combo_class.currentText())
        self._settings.setValue(_SET_MAPPING, TT.mapping_to_json(self.mapping))
        self._settings.setValue(_SET_SURVEY, TT.survey_to_json(self.survey))

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.card.set_title(tr("util.timetable.card.nav"))
        self.btn_today.setText(tr("util.timetable.btn.today"))
        self.neis_panel.retranslate()
        self._update_week_label()

        self.radio_class_view.setText(tr("util.timetable.btn.class_view"))
        self.radio_teacher_view.setText(tr("util.timetable.btn.teacher_view"))
        (self.radio_teacher_view if self.view_mode == "teacher" else self.radio_class_view).setChecked(True)
        self.lbl_grade.setText(tr("util.timetable.lbl.grade"))
        self.lbl_class.setText(tr("util.timetable.lbl.class"))
        self.lbl_teacher.setText(tr("util.timetable.lbl.teacher"))
        self.btn_download_subjects.setText(tr("util.timetable.btn.download_subjects"))
        self.btn_upload_teachers.setText(tr("util.timetable.btn.upload_teachers"))
        self.btn_print.setText(tr("util.timetable.btn.print"))
        if self.slots or self.survey or self.table.rowCount():
            self._render()


class TimetableApp(MiniApp):
    id = "timetable"
    icon = "timetable"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = TimetableWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.timetable.title": {"ko": "시간표", "en": "Timetable", "ja": "時間表"},
    "util.timetable.desc": {
        "ko": "나이스 공식 API로 학급별 시간표를 봅니다(과목 매핑을 넣으면 교사 시간표도).",
        "en": "Shows the class timetable via NEIS's official API (and teacher schedules with a subject mapping).",
        "ja": "NEIS公式APIで学級別時間表を表示します（教科マッピングで教師の時間表も）。"},

    "util.timetable.card.nav": {"ko": "시간표", "en": "Timetable", "ja": "時間表"},
    "util.timetable.btn.today": {"ko": "이번 주", "en": "This Week", "ja": "今週"},
    "util.timetable.weekday.mon": {"ko": "월", "en": "Mon", "ja": "月"},
    "util.timetable.weekday.tue": {"ko": "화", "en": "Tue", "ja": "火"},
    "util.timetable.weekday.wed": {"ko": "수", "en": "Wed", "ja": "水"},
    "util.timetable.weekday.thu": {"ko": "목", "en": "Thu", "ja": "木"},
    "util.timetable.weekday.fri": {"ko": "금", "en": "Fri", "ja": "金"},
    "util.timetable.period": {"ko": "{a0}교시", "en": "Period {a0}", "ja": "{a0}限"},
    "util.timetable.class_label": {"ko": "{a0}학년{a1}반", "en": "Grade {a0} Class {a1}", "ja": "{a0}学年{a1}組"},

    "util.timetable.btn.class_view": {"ko": "학급 시간표", "en": "Class View", "ja": "学級時間表"},
    "util.timetable.lbl.grade": {"ko": "학년", "en": "Grade", "ja": "学年"},
    "util.timetable.lbl.class": {"ko": "반", "en": "Class", "ja": "組"},
    "util.timetable.lbl.teacher": {"ko": "교사 선택", "en": "Teacher", "ja": "教師選択"},
    "util.timetable.btn.print": {"ko": "인쇄", "en": "Print", "ja": "印刷"},
    "util.timetable.print.title": {"ko": "시간표 인쇄", "en": "Print Timetable", "ja": "時間表印刷"},
    "util.timetable.print.hint": {
        "ko": "한 장에 지금 시간표를 몇 번 담아 인쇄할지 고르세요(잘라서 여러 장 쓸 때 편합니다).",
        "en": "Choose how many copies of this timetable to fit on one sheet (handy for cutting into pieces).",
        "ja": "1枚に今の時間表を何回分印刷するか選んでください（切り分けて使うときに便利です）。"},
    "util.timetable.print.copies_1": {"ko": "1쪽(가로 꽉 채움)", "en": "1 (fill landscape)", "ja": "1枚（横いっぱい）"},
    "util.timetable.print.copies_2": {"ko": "2쪽(세로, 위아래)", "en": "2 (portrait, top/bottom)",
                                       "ja": "2枚（縦、上下）"},
    "util.timetable.print.copies_4": {"ko": "4쪽(가로, 2x2)", "en": "4 (landscape, 2x2)", "ja": "4枚（横、2×2）"},
    "util.timetable.log.printed": {"ko": "시간표를 인쇄했습니다.", "en": "Timetable printed.", "ja": "時間表を印刷しました。"},
    "util.timetable.btn.teacher_view": {"ko": "교사 시간표", "en": "Teacher View", "ja": "教師時間表"},
    "util.timetable.btn.download_subjects": {"ko": "전체 과목 다운로드", "en": "Download All Subjects",
                                              "ja": "全科目ダウンロード"},
    "util.timetable.btn.upload_teachers": {"ko": "교사 목록 업로드", "en": "Upload Teacher List", "ja": "教師リストをアップロード"},
    "util.timetable.survey.confirm": {
        "ko": "1~3학년, 1~10반 — 학급 {a0}개를 전부 조회한 뒤 과목 목록을 엑셀로 저장합니다(이번 주 기준). "
              "학급 수가 많으면 시간이 좀 걸릴 수 있습니다. 계속할까요?",
        "en": "This will query all {a0} classes (grades 1-3, classes 1-10) for this week, then save the "
              "subject list as Excel. It may take a little while. Continue?",
        "ja": "1〜3学年、1〜10組 — 学級{a0}個を全て照会した後、科目リストをExcelで保存します（今週基準）。"
              "学級数が多いと時間がかかる場合があります。続けますか？"},
    "util.timetable.survey.progress": {"ko": "전체 학급 조사 중… ({a0}/{a1})", "en": "Surveying classes… ({a0}/{a1})",
                                        "ja": "全学級調査中…（{a0}/{a1}）"},
    "util.timetable.survey.partial": {
        "ko": "{a1}개 학급 중 {a0}개에서 시간표를 받았습니다(재시도 후에도 {a2}개는 실패). "
              "나이스 서버가 순간적으로 응답하지 않았을 수 있습니다 — 교사 시간표가 빈약해 보이면 "
              "잠시 후 '전체 과목 다운로드'를 다시 눌러 주세요.",
        "en": "Got timetables from {a0} of {a1} classes ({a2} still failed after retrying). The NEIS "
              "server may have been briefly unresponsive — if the teacher view looks incomplete, try "
              "\"Download All Subjects\" again in a bit.",
        "ja": "{a1}学級中{a0}学級から時間表を取得しました（再試行後も{a2}学級は失敗）。"
              "NEISサーバーが一時的に応答しなかった可能性があります — 教師時間表が不完全に見える場合は"
              "しばらくしてから「全科目ダウンロード」をもう一度押してください。"},
    "util.timetable.log.surveyed": {"ko": "[시간표] 전체 학급 조사 완료 — 과목 {a0}개",
                                     "en": "[Timetable] Finished surveying all classes — {a0} subjects",
                                     "ja": "[時間表] 全学級調査完了 — 科目{a0}個"},
    "util.timetable.hint.teacher_none": {
        "ko": "아직 담당교사가 지정된 과목이 없습니다. \"전체 과목 다운로드\" → 담당교사 입력 후 "
              "\"교사 목록 업로드\" 순서로 진행해 주세요.",
        "en": "No subjects have a teacher assigned yet. Use \"Download All Subjects\" → fill in teachers → "
              "\"Upload Teacher List\".",
        "ja": "まだ担当教師が指定された科目がありません。「全科目ダウンロード」→担当教師を入力→"
              "「教師リストをアップロード」の順に進めてください。"},
    "util.timetable.hint.teacher_multi": {
        "ko": "위 콤보에서 교사를 고르면 그 시간표가 표에 채워집니다(지금 {a0}명 매핑됨).",
        "en": "Pick a teacher from the dropdown above to fill in their schedule (currently {a0} mapped).",
        "ja": "上のコンボで教師を選ぶとその時間表が表に入ります（現在{a0}人マッピング済み）。"},
    "util.timetable.hint.teacher_single": {"ko": "{a0} 선생님의 시간표입니다(과목 아래는 담당 반).",
                                            "en": "Showing {a0}'s schedule (class shown below each subject).",
                                            "ja": "{a0}先生の時間表です（科目の下は担当クラス）。"},

    "util.timetable.subjects.title": {"ko": "전체 과목 다운로드", "en": "Download All Subjects",
                                       "ja": "全科目ダウンロード"},
    "util.timetable.subjects.none": {
        "ko": "조회된 과목이 없습니다. 인증키·학교 코드가 맞는지 확인해 주세요.",
        "en": "No subjects were found — check your auth key and school codes.",
        "ja": "照会された科目がありません。認証キー・学校コードを確認してください。"},
    "util.timetable.subjects.default_name": {"ko": "과목_담당교사.xlsx", "en": "subjects_teachers.xlsx",
                                              "ja": "科目_担当教師.xlsx"},
    "util.timetable.subjects.saved": {"ko": "과목 목록을 저장했습니다: {a0}", "en": "Saved subject list: {a0}",
                                       "ja": "科目リストを保存しました: {a0}"},
    "util.timetable.subjects.upload_title": {"ko": "교사 목록 업로드", "en": "Upload Teacher List",
                                              "ja": "教師リストをアップロード"},
    "util.timetable.subjects.upload_empty": {
        "ko": "담당교사가 채워진 줄을 찾지 못했습니다 — 다운로드한 양식의 '담당교사' 칸을 채워서 다시 올려주세요.",
        "en": "No rows with a teacher name were found — fill in the 'Teacher' column of the downloaded "
              "template and upload it again.",
        "ja": "担当教師が入力された行が見つかりませんでした — ダウンロードした雛形の「担当教師」欄を入力して再度アップロードしてください。"},
    "util.timetable.log.mapping_uploaded": {"ko": "[시간표] 교사 목록 업로드 — {a0}개 과목에 담당교사 지정",
                                             "en": "[Timetable] Uploaded teacher list — {a0} subjects mapped",
                                             "ja": "[時間表] 教師リストをアップロード — {a0}科目にマッピング"},

    "util.timetable.status.need_key": {
        "ko": "위 '학교 설정'을 열어 나이스 인증키를 먼저 입력해 주세요.",
        "en": "Open 'School Settings' above and enter your NEIS auth key first.",
        "ja": "上の「学校設定」を開いてNEIS認証キーを先に入力してください。"},
    "util.timetable.status.loading": {"ko": "시간표를 불러오는 중…", "en": "Loading timetable…", "ja": "時間表を読み込み中…"},
    "util.timetable.status.network_error": {"ko": "네트워크 오류: {a0}", "en": "Network error: {a0}",
                                              "ja": "ネットワークエラー: {a0}"},
    "util.timetable.status.unknown_error": {"ko": "알 수 없는 오류입니다. 인증키와 학교 코드를 확인해 주세요.",
                                             "en": "Unknown error — check your auth key and school code.",
                                             "ja": "不明なエラーです。認証キーと学校コードを確認してください。"},
    "util.timetable.status.error": {"ko": "시간표를 가져오지 못했습니다: {a0}", "en": "Couldn't load the timetable: {a0}",
                                     "ja": "時間表を取得できませんでした: {a0}"},
    "util.timetable.status.cached": {
        "ko": "지금 보이는 시간표는 마지막으로 불러온 결과입니다({a0})",
        "en": "Showing the last successfully loaded timetable ({a0})",
        "ja": "表示中の時間表は最後に読み込んだ結果です（{a0}）"},
    "util.timetable.log.error": {"ko": "[시간표] 오류: {a0}", "en": "[Timetable] Error: {a0}", "ja": "[時間表] エラー: {a0}"},
}
TimetableApp.tr_table = TRANSLATIONS

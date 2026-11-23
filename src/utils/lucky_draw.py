# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 행운의 번호 [v44.2]

"Lucky LOTTO" — 수업 발표자 뽑기, 행사 경품·번호표 추첨, 사전 등록
명단 추첨(최대 120명). 계획서: docs/PLAN_v44_lucky_cheer.md 2장.

- 추첨 유형(내부 키): range(번호 범위) / roster(명단 추첨) / combo(조합 뽑기) /
  ticket(번호표 발급)
- 연출은 코어 챔버(물리가 결과를 정함) 하나뿐이다 — 이진 라우터는 목업
  검토 결과 효과가 낮다고 판단해 v44.1에서 뺐다. [뽑기] 한 번으로
  섞기→감속(완전 정지)→바람→포트 흡입까지 전부 자동으로 진행된다("섞기"를
  따로 누를 필요가 없다).
- 추첨 대상·추첨 기록 카드는 어코디언(기본은 접힘)이라 화면이 세로로
  길어지지 않는다.
- 기록은 세션 단위로 자동 저장(QSettings)되어 프로그램을 껐다 켜도 이어진다.
  행사 도중 창을 닫아도 누가 뽑혔는지 잃어버리지 않게.
"""
import html
import json
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextDocument, QGuiApplication
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox, QSpinBox, QLineEdit,
    QCheckBox, QListWidget, QListWidgetItem, QScrollArea, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QMenu,
    QHeaderView, QAbstractItemView
)

from ..config import desktop_file
from ..i18n import tr
from . import ui_kit as UK
from .base import MiniApp
from . import bracket_solve as B
from . import lucky_draw_logic as L
from .anim_kit import FullscreenPresenter
from .lucky_draw_scene import LuckyScene

_P = "util.lucky."
_SET = {k: _P + k for k in ("type", "start", "end", "combo_k", "speed", "theme", "repeat",
                             "exclude", "roster", "names", "source", "class", "session", "label")}


# =============================================================================
# 보조 대화상자
# =============================================================================
class _PasteNamesDialog(QDialog):
    """행사 사전 등록 명단처럼 학년·반이 없는 이름 목록을 붙여 넣는 창."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.lucky.paste.title"))
        self.resize(420, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(UK.hint_label(tr("util.lucky.paste.hint", a0=L.MAX_ENTRIES)))
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        lay.addWidget(self.edit, 1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def names(self):
        return [ln.strip() for ln in self.edit.toPlainText().splitlines() if ln.strip()]


class TicketDialog(QDialog):
    """번호표 발급 결과 — 명단 전원에게 겹치지 않는 번호를 무작위로 준다."""

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.pairs = []
        self.setWindowTitle(tr("util.lucky.ticket.title"))
        self.resize(520, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(UK.hint_label(tr("util.lucky.ticket.hint")))
        self.table = QTableWidget(0, 3)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_shuffle = UK.secondary_button(tr("util.lucky.ticket.reshuffle"))
        self.btn_csv = UK.secondary_button(tr("util.lucky.ticket.csv"))
        self.btn_print = UK.secondary_button(tr("util.lucky.ticket.print"))
        self.btn_close = UK.primary_button(tr("util.lucky.ticket.close"))
        row.addWidget(self.btn_shuffle)
        row.addStretch()
        row.addWidget(self.btn_csv)
        row.addWidget(self.btn_print)
        row.addWidget(self.btn_close)
        lay.addLayout(row)
        self.btn_shuffle.clicked.connect(self.shuffle)
        self.btn_csv.clicked.connect(self._on_csv)
        self.btn_print.clicked.connect(self._on_print)
        self.btn_close.clicked.connect(self.accept)
        self.shuffle()

    def headers(self):
        return [tr("util.lucky.ticket.col.ticket"), tr("util.lucky.ticket.col.name"),
                tr("util.lucky.ticket.col.sub")]

    def shuffle(self):
        self.pairs = L.assign_tickets(self.entries)
        self.table.setHorizontalHeaderLabels(self.headers())
        self.table.setRowCount(len(self.pairs))
        for r, (ticket, e) in enumerate(self.pairs):
            for c, v in enumerate((str(ticket), e.name or str(e.no), e.sub)):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)

    def _on_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("util.lucky.ticket.csv"),
                                              desktop_file(tr("util.lucky.ticket.default_name")), "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            L.export_tickets_csv(path, self.pairs, self.headers())
        except OSError as e:
            QMessageBox.warning(self, tr("util.lucky.ticket.csv"), str(e))

    def ticket_html(self):
        rows = "".join(
            f"<tr><td align='center'><b>{t}</b></td><td>{html.escape(e.name or str(e.no))}</td>"
            f"<td>{html.escape(e.sub)}</td></tr>" for t, e in self.pairs)
        h = "".join(f"<th>{html.escape(x)}</th>" for x in self.headers())
        return (f"<h2>{html.escape(tr('util.lucky.ticket.title'))}</h2>"
                f"<table border='1' cellspacing='0' cellpadding='4' width='100%'><tr>{h}</tr>{rows}</table>")

    def _on_print(self):
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        doc = QTextDocument()
        doc.setHtml(self.ticket_html())
        doc.print_(printer)


# =============================================================================
# 본 위젯
# =============================================================================
class LuckyDrawWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.roster = []           # 엑셀 명단(Student)
        self.names = []            # 붙여 넣은 이름 목록
        self.source = "roster"     # 명단 출처(내부 키): roster | names
        self.session = L.DrawSession()
        self.pending = 0           # 연속 뽑기에서 남은 횟수
        self._loading = True
        self._build_ui()
        self._load_settings()
        self._loading = False
        self.retranslate()
        self._apply_type_visibility()
        self._refresh_all()

    # ================================================================ UI
    def _build_ui(self):
        # ---- 왼쪽: 추첨 화면
        self.scene = LuckyScene()
        self.scene.winnerDecided.connect(self._on_winner)
        self.scene.revealFinished.connect(self._on_reveal_finished)
        self.scene.replayFinished.connect(self._on_replay_finished)
        self.scene.primaryRequested.connect(self._on_draw)
        self.scene.exitFullscreenRequested.connect(self._exit_fullscreen)
        self.presenter = FullscreenPresenter(self.scene)
        self.card_stage = UK.Card()
        self.btn_full_tool = self.card_stage.add_tool(UK.tool_button("⛶"))
        self.btn_full_tool.clicked.connect(self._toggle_fullscreen)
        self.card_stage.add_body(UK.canvas_frame(self.scene), 1)
        self.lbl_stage_hint = self.card_stage.add_footer_left(UK.hint_label())

        # ---- 오른쪽 1: 추첨 설정
        self.card_setup = UK.Card()
        self.type_group, radios = UK.radio_row(["", "", "", ""], checked_index=0)
        self.radio_types = dict(zip(L.DRAW_TYPES, radios))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(UK.CTRL_SPACING)
        for i, t in enumerate(L.DRAW_TYPES):
            grid.addWidget(self.radio_types[t], i // 2, i % 2)
        self.card_setup.add_body(grid)
        self.type_group.buttonClicked.connect(lambda _b: self._on_type_changed())

        self.lbl_range = UK.body_label()
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 9999)
        self.spin_start.setValue(1)
        self.lbl_tilde = UK.body_label("~")
        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 9999)
        self.spin_end.setValue(30)
        self.row_range = UK.hrow(self.lbl_range, self.spin_start, self.lbl_tilde, self.spin_end, None)
        self.card_setup.add_body(self.row_range)
        self._range_timer = QTimer(self)
        self._range_timer.setSingleShot(True)
        self._range_timer.setInterval(350)
        self._range_timer.timeout.connect(self._rebuild_session)
        self.spin_start.valueChanged.connect(lambda _v: self._range_timer.start())
        self.spin_end.valueChanged.connect(lambda _v: self._range_timer.start())

        self.lbl_combo_k = UK.body_label()
        self.spin_combo_k = QSpinBox()
        self.spin_combo_k.setRange(1, 10)
        self.spin_combo_k.setValue(6)
        self.spin_combo_k.valueChanged.connect(lambda _v: self._save_settings())
        self.row_combo = UK.hrow(self.lbl_combo_k, self.spin_combo_k, None)
        self.card_setup.add_body(self.row_combo)

        self.lbl_repeat = UK.body_label()
        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 10)
        self.spin_repeat.valueChanged.connect(lambda _v: self._save_settings())
        self.row_repeat = UK.hrow(self.lbl_repeat, self.spin_repeat, None)
        self.card_setup.add_body(self.row_repeat)

        self.lbl_speed = UK.body_label()
        self.combo_speed = QComboBox()
        self.lbl_theme = UK.body_label()
        self.combo_theme = QComboBox()
        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(UK.CTRL_SPACING)
        for r, (lbl, cb) in enumerate(((self.lbl_speed, self.combo_speed), (self.lbl_theme, self.combo_theme))):
            form.addWidget(lbl, r, 0)
            form.addWidget(cb, r, 1)
        form.setColumnStretch(1, 1)
        self.card_setup.add_body(form)
        for key in L.SPEEDS:
            self.combo_speed.addItem("", key)
        for key in L.THEMES:
            self.combo_theme.addItem("", key)
        self.combo_speed.setCurrentIndex(1)
        self.combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed)

        self.lbl_label = UK.body_label()
        self.edit_label = QLineEdit()
        self.edit_label.textChanged.connect(lambda _t: self._save_settings())
        self.card_setup.add_body(UK.hrow(self.lbl_label, self.edit_label))
        self.chk_exclude = QCheckBox()
        self.chk_exclude.setChecked(True)
        self.chk_exclude.toggled.connect(self._on_exclude_toggled)
        self.card_setup.add_body(self.chk_exclude)
        self.lbl_locked = UK.hint_label()
        self.card_setup.add_body(self.lbl_locked)

        # ---- 오른쪽 2: 대상 목록(명단) — 어코디언, 기본은 접힘(화면이 세로로
        # 너무 길어지는 걸 막는다). 카드 제목 줄의 ▸ 버튼으로 열고 닫는다.
        self.card_pool = UK.Card()
        self.btn_pool_toggle = self.card_pool.add_tool(UK.tool_button("▸"))
        self.btn_pool_toggle.clicked.connect(lambda: self._toggle_accordion("pool"))
        self.pool_body = QWidget()
        pool_lay = QVBoxLayout(self.pool_body)
        pool_lay.setContentsMargins(0, 0, 0, 0)
        pool_lay.setSpacing(UK.CTRL_SPACING)
        self.lbl_pool_status = UK.hint_label()
        pool_lay.addWidget(self.lbl_pool_status)
        self.lbl_class = UK.body_label()
        self.combo_class = QComboBox()
        self.combo_class.currentIndexChanged.connect(self._on_class_changed)
        self.row_class = UK.hrow(self.lbl_class, self.combo_class)
        pool_lay.addLayout(self.row_class)
        self.list_pool = QListWidget()
        self.list_pool.setMinimumHeight(150)
        self.list_pool.itemChanged.connect(self._on_pool_item_changed)
        pool_lay.addWidget(self.list_pool)
        self.btn_template = UK.secondary_button()
        self.btn_template.clicked.connect(self._on_download_template)
        self.row_template = UK.hrow(None, self.btn_template)
        pool_lay.addLayout(self.row_template)
        self.lbl_pool_error = UK.error_label()
        pool_lay.addWidget(self.lbl_pool_error)
        self.card_pool.add_body(self.pool_body)
        self.pool_body.setVisible(False)
        self.btn_roster_clear = self.card_pool.add_footer(UK.danger_button())
        self.btn_roster_clear.clicked.connect(self._on_roster_clear)
        self.btn_paste = self.card_pool.add_footer(UK.secondary_button())
        self.btn_paste.clicked.connect(self._on_paste_names)
        self.btn_upload = self.card_pool.add_footer(UK.secondary_button())
        self.btn_upload.clicked.connect(self._on_roster_upload)

        # ---- 오른쪽 3: 추첨 — [v44.1] "섞기" 버튼을 따로 두지 않는다. [뽑기]
        # 한 번으로 섞기→감속→바람→포트 흡입까지 자동으로 진행된다.
        self.card_draw = UK.Card()
        self.lbl_draw_status = UK.body_label()
        self.lbl_draw_status.setWordWrap(True)
        self.card_draw.add_body(self.lbl_draw_status)
        self.btn_reset = self.card_draw.add_footer(UK.danger_button())
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_draw = self.card_draw.add_footer(UK.primary_button())
        self.btn_draw.clicked.connect(self._on_draw)

        # ---- 오른쪽 4: 기록 — 어코디언, 기본은 접힘.
        self.card_log = UK.Card()
        self.btn_log_toggle = self.card_log.add_tool(UK.tool_button("▸"))
        self.btn_log_toggle.clicked.connect(lambda: self._toggle_accordion("log"))
        self.log_body = QWidget()
        log_lay = QVBoxLayout(self.log_body)
        log_lay.setContentsMargins(0, 0, 0, 0)
        self.list_log = QListWidget()
        self.list_log.setMinimumHeight(140)
        log_lay.addWidget(self.list_log)
        self.card_log.add_body(self.log_body)
        self.log_body.setVisible(False)
        self.btn_file = self.card_log.add_footer(UK.secondary_button())
        self.btn_file.clicked.connect(self._on_file_menu)
        self.btn_replay = self.card_log.add_footer(UK.secondary_button())
        self.btn_replay.clicked.connect(self._on_replay)

        right_inner = QWidget()
        right_lay = UK.vstack(self.card_setup, self.card_pool, self.card_draw, self.card_log)
        right_lay.addStretch(1)
        right_inner.setLayout(right_lay)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_inner)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        UK.split_lr(self, self.card_stage, scroll)

    # ================================================================ 대상 만들기
    def current_type(self):
        for key, rb in self.radio_types.items():
            if rb.isChecked():
                return key
        return "range"

    def _filtered_roster(self):
        cls = self.combo_class.currentData()
        if not cls or cls == "all":
            return list(self.roster)
        grade, c = cls
        return [s for s in self.roster if s.grade == grade and s.cls == c]

    def build_entries(self):
        t = self.current_type()
        if t in ("range", "combo"):
            start, end = self.spin_start.value(), self.spin_end.value()
            return L.range_entries(start, end), abs(end - start) + 1 > L.MAX_ENTRIES
        if self.source == "names":
            return L.name_list_entries(self.names), len(self.names) > L.MAX_ENTRIES
        students = self._filtered_roster()
        return L.roster_entries(students), len(students) > L.MAX_ENTRIES

    def _rebuild_session(self, keep_excluded=False):
        """추첨 대상 설정이 바뀌었을 때 새 세션을 만든다. 기록이 있는
        세션은 설정 칸을 잠가 두므로(초기화 전까지) 여기로 오지 않는다."""
        if self._loading:
            return
        if self.session.rounds:
            return
        entries, truncated = self.build_entries()
        old_excluded = self.session.excluded if keep_excluded else set()
        self.session = L.DrawSession(entries, self.current_type(), self.chk_exclude.isChecked())
        self.session.excluded = {k for k in old_excluded if any(e.key == k for e in entries)}
        self.lbl_pool_error.setText(tr("util.lucky.pool.truncated", a0=L.MAX_ENTRIES) if truncated else "")
        self.scene.set_session(self.session)
        self._save_settings()
        self._refresh_all()

    # ================================================================ 설정 변경
    def _on_type_changed(self):
        self._apply_type_visibility()
        self._rebuild_session()

    def _apply_type_visibility(self):
        t = self.current_type()
        uses_range = t in ("range", "combo")
        for w in (self.lbl_range, self.spin_start, self.lbl_tilde, self.spin_end):
            w.setVisible(uses_range)
        for w in (self.lbl_combo_k, self.spin_combo_k):
            w.setVisible(t == "combo")
        for w in (self.lbl_repeat, self.spin_repeat):
            w.setVisible(t in ("range", "roster"))
        uses_names = t in ("roster", "ticket")
        for w in (self.btn_upload, self.btn_paste, self.btn_roster_clear, self.btn_template):
            w.setVisible(uses_names)
        show_class = uses_names and self.source == "roster" and len(B_class_options(self.roster)) > 1
        self.lbl_class.setVisible(show_class)
        self.combo_class.setVisible(show_class)
        is_ticket = t == "ticket"
        for w in (self.btn_reset, self.chk_exclude, self.lbl_speed, self.combo_speed, self.lbl_theme,
                  self.combo_theme, self.lbl_label, self.edit_label):
            w.setVisible(not is_ticket)
        self.chk_exclude.setVisible(t in ("range", "roster"))
        self.btn_draw.setText(tr("util.lucky.btn.ticket") if is_ticket else tr("util.lucky.btn.draw"))

    def _on_speed_changed(self, _i):
        self.scene.set_speed(self.combo_speed.currentData())
        self._save_settings()

    def _on_theme_changed(self, _i):
        self.scene.set_theme(self.combo_theme.currentData())
        self._save_settings()

    def _on_exclude_toggled(self, on):
        self.session.exclude_winners = bool(on)
        if not self.scene.busy:
            self.scene.sync_pool()
        self._save_settings()
        self._refresh_draw_status()

    def _on_class_changed(self, _i):
        if self._loading:
            return
        self._rebuild_session()

    def _on_pool_item_changed(self, item):
        key = item.data(Qt.UserRole)
        if key is None:
            return
        if item.checkState() == Qt.Checked:
            self.session.excluded.discard(key)
        else:
            self.session.excluded.add(key)
        self.scene.sync_pool()
        self._autosave_session()
        self._refresh_draw_status()

    # ================================================================ 명단
    def _on_download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.seating.template.title"), desktop_file(tr("util.seating.template.default_name")),
            "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            B.save_roster_template(path)
        except ImportError:
            QMessageBox.warning(self, tr("util.seating.template.title"), tr("util.bracket.roster.need_openpyxl"))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("util.seating.template.title"), str(e))
            return
        if self.host:
            self.host.status(tr("util.seating.template.saved", a0=path))

    def _on_roster_upload(self):
        if self._blocked_by_records():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("util.seating.roster.upload_title"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            students = B.read_roster_excel(path)
        except ImportError:
            QMessageBox.warning(self, tr("util.seating.roster.upload_title"), tr("util.bracket.roster.need_openpyxl"))
            return
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("util.seating.roster.upload_title"), str(e))
            return
        if not students:
            QMessageBox.information(self, tr("util.seating.roster.upload_title"),
                                   tr("util.seating.roster.upload_empty"))
            return
        self.set_roster(students)

    def set_roster(self, students):
        """엑셀 명단을 추첨 대상으로 쓴다(테스트에서도 직접 부른다)."""
        self.roster = list(students)
        self.source = "roster"
        self._refresh_class_combo()
        self._apply_type_visibility()
        self._rebuild_session()
        if self.host:
            self.host.log(tr("util.lucky.log.roster", a0=len(self.roster)))

    def set_names(self, names):
        self.names = [n for n in names if n.strip()]
        self.source = "names"
        self._apply_type_visibility()
        self._rebuild_session()
        if self.host:
            self.host.log(tr("util.lucky.log.names", a0=len(self.names)))

    def _on_paste_names(self):
        if self._blocked_by_records():
            return
        dlg = _PasteNamesDialog("\n".join(self.names), self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.set_names(dlg.names())

    def _on_roster_clear(self):
        if self._blocked_by_records():
            return
        if not self.roster and not self.names:
            return
        reply = QMessageBox.question(self, tr("util.lucky.pool.clear_title"), tr("util.lucky.pool.clear_confirm"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.roster = []
        self.names = []
        self.source = "roster"
        self._refresh_class_combo()
        self._apply_type_visibility()
        self._rebuild_session()

    def _refresh_class_combo(self):
        self.combo_class.blockSignals(True)
        prev = self.combo_class.currentData()
        self.combo_class.clear()
        self.combo_class.addItem(tr("util.lucky.class.all"), "all")
        for grade, cls in B_class_options(self.roster):
            self.combo_class.addItem(tr("util.seating.class_label", a0=grade, a1=cls), (grade, cls))
        idx = self.combo_class.findData(prev) if prev is not None else 0
        self.combo_class.setCurrentIndex(max(0, idx))
        self.combo_class.blockSignals(False)

    def _blocked_by_records(self):
        if self.session.rounds:
            QMessageBox.information(self, tr("util.lucky.locked.title"), tr("util.lucky.locked.msg"))
            return True
        return False

    # ================================================================ 추첨
    def _on_draw(self):
        t = self.current_type()
        if t == "ticket":
            self._open_ticket_dialog()
            return
        if self.scene.busy:
            return
        if not self.session.available_keys():
            if self.host:
                self.host.status(tr("util.lucky.status.none_left"))
            self._refresh_draw_status()
            return
        if t == "combo":
            if not self.session.combo_current:
                self.scene.combo_line = None
            self.pending = max(0, self.spin_combo_k.value() - len(self.session.combo_current))
        else:
            self.pending = self.spin_repeat.value()
        if self.scene.request_draw():
            self.pending -= 1
        self.scene.setFocus()
        self._refresh_draw_status()

    def _on_winner(self, key, info):
        label = self.edit_label.text().strip()
        rec = self.session.record(key, label=label, seed=info.get("seed"),
                                  replay=info.get("replay"))
        self._autosave_session()
        self._refresh_log()
        self._refresh_pool_list()
        self._refresh_draw_status()
        if self.host:
            self.host.log(tr("util.lucky.log.winner", a0=rec["order"], a1=rec["no"],
                             a2=rec["name"] or "-"))

    def _on_reveal_finished(self):
        if self.session.draw_type == "combo":
            if len(self.session.combo_current) >= self.spin_combo_k.value() or not self.session.available_keys():
                numbers = self.session.finish_combo()
                self.scene.show_combo(numbers)
                self.pending = 0
                self._autosave_session()
                self._refresh_log()
                self._refresh_draw_status()
                if self.host:
                    self.host.log(tr("util.lucky.log.combo", a0=", ".join(str(n) for n in numbers)))
                return
        if self.pending > 0 and self.session.available_keys():
            if self.scene.request_draw():
                self.pending -= 1
        else:
            self.pending = 0
        self._refresh_draw_status()

    def _on_replay(self):
        item = self.list_log.currentItem()
        idx = item.data(Qt.UserRole) if item is not None else None
        if idx is None:
            if self.host:
                self.host.status(tr("util.lucky.status.pick_record"))
            return
        rec = self.session.rounds[idx]
        if self.scene.play_replay(rec):
            self.scene.setFocus()

    def _on_replay_finished(self):
        self.scene.sync_pool()

    def _on_reset(self):
        if self.scene.busy:
            return
        if self.session.rounds:
            reply = QMessageBox.question(self, tr("util.lucky.reset.title"), tr("util.lucky.reset.confirm"),
                                         QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.session.reset_draws()
        self.pending = 0
        self._rebuild_session(keep_excluded=True)

    def _open_ticket_dialog(self):
        entries, _trunc = self.build_entries()
        entries = [e for e in entries if e.key not in self.session.excluded]
        if not entries:
            QMessageBox.information(self, tr("util.lucky.ticket.title"), tr("util.lucky.ticket.empty"))
            return
        dlg = TicketDialog(entries, self)
        dlg.exec()

    # ================================================================ 어코디언
    def _toggle_accordion(self, which):
        """[v44.1] 추첨 대상·추첨 기록 카드를 열고 닫는다 — 화면이 세로로
        너무 길어지는 걸 막기 위해 기본은 접힘."""
        body, btn = (self.pool_body, self.btn_pool_toggle) if which == "pool" else (self.log_body, self.btn_log_toggle)
        opening = not body.isVisible()
        body.setVisible(opening)
        btn.setText("▾" if opening else "▸")

    # ================================================================ 전체화면
    def _toggle_fullscreen(self):
        self.presenter.title = tr("util.lucky.title")
        self.presenter.toggle()

    def _exit_fullscreen(self):
        if self.presenter.active:
            self.presenter.exit()

    # ================================================================ 파일
    def _on_file_menu(self):
        menu = QMenu(self)
        a_csv = menu.addAction(tr("util.lucky.file.csv"))
        a_save = menu.addAction(tr("util.lucky.file.save"))
        a_open = menu.addAction(tr("util.lucky.file.open"))
        chosen = menu.exec(self.btn_file.mapToGlobal(self.btn_file.rect().bottomLeft()))
        if chosen is a_csv:
            self.export_csv()
        elif chosen is a_save:
            self.save_session_file()
        elif chosen is a_open:
            self.open_session_file()

    def csv_headers(self):
        return [tr("util.lucky.csv.label"), tr("util.lucky.csv.order"), tr("util.lucky.csv.no"),
                tr("util.lucky.csv.name"), tr("util.lucky.csv.at"), tr("util.lucky.csv.seed")]

    def export_csv(self, path=None):
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("util.lucky.file.csv"),
                                                  desktop_file(tr("util.lucky.csv.default_name")), "CSV (*.csv)")
            if not path:
                return None
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            L.export_rounds_csv(path, self.session, self.csv_headers())
        except OSError as e:
            QMessageBox.warning(self, tr("util.lucky.file.csv"), str(e))
            return None
        if self.host:
            self.host.status(tr("util.lucky.file.saved", a0=path))
        return path

    def save_session_file(self, path=None):
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("util.lucky.file.save"),
                                                  desktop_file(tr("util.lucky.session.default_name")),
                                                  "JSON (*.json)")
            if not path:
                return None
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            L.save_session(path, self.session)
        except OSError as e:
            QMessageBox.warning(self, tr("util.lucky.file.save"), str(e))
            return None
        if self.host:
            self.host.status(tr("util.lucky.file.saved", a0=path))
        return path

    def open_session_file(self, path=None):
        if self.scene.busy:
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, tr("util.lucky.file.open"), os.path.dirname(
                desktop_file("x")), "JSON (*.json)")
            if not path:
                return
        try:
            session = L.load_session(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, tr("util.lucky.file.open"), str(e))
            return
        self.apply_session(session)

    def apply_session(self, session):
        self.session = session
        rb = self.radio_types.get(session.draw_type)
        if rb is not None:
            rb.setChecked(True)
        self.chk_exclude.blockSignals(True)
        self.chk_exclude.setChecked(session.exclude_winners)
        self.chk_exclude.blockSignals(False)
        self._apply_type_visibility()
        self.scene.set_session(session)
        self._autosave_session()
        self._refresh_all()

    # ================================================================ 화면 갱신
    def _refresh_all(self):
        self._refresh_pool_list()
        self._refresh_log()
        self._refresh_draw_status()
        self._refresh_lock()

    def _refresh_lock(self):
        locked = bool(self.session.rounds)
        for w in list(self.radio_types.values()) + [self.spin_start, self.spin_end, self.combo_class]:
            w.setEnabled(not locked)
        self.lbl_locked.setText(tr("util.lucky.locked.hint") if locked else "")
        self.lbl_locked.setVisible(locked)

    def _refresh_pool_list(self):
        self.list_pool.blockSignals(True)
        self.list_pool.clear()
        drawn = set(self.session.drawn)
        for e in self.session.entries:
            text = f"{e.no}" + (f"  {e.name}" if e.name else "") + (f"  ({e.sub})" if e.sub else "")
            if e.key in drawn:
                text += "  ✔"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, e.key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if e.key in self.session.excluded else Qt.Checked)
            self.list_pool.addItem(it)
        self.list_pool.blockSignals(False)
        n = len(self.session.entries)
        n_ex = len(self.session.excluded)
        self.lbl_pool_status.setText(tr("util.lucky.pool.status", a0=n, a1=n_ex))
        self.card_pool.set_title(tr("util.lucky.card.pool_n", a0=n))

    def _refresh_log(self):
        self.list_log.clear()
        for combo in reversed(self.session.combos):
            label = f"[{combo['label']}] " if combo.get("label") else ""
            it = QListWidgetItem(tr("util.lucky.log.combo_item", a0=label,
                                    a1=", ".join(str(n) for n in combo["numbers"])))
            it.setData(Qt.UserRole, None)
            self.list_log.addItem(it)
        for idx in range(len(self.session.rounds) - 1, -1, -1):
            r = self.session.rounds[idx]
            label = f"[{r['label']}] " if r.get("label") else ""
            name = f"  {r['name']}" if r.get("name") else ""
            it = QListWidgetItem(tr("util.lucky.log.item", a0=label, a1=r["order"], a2=r["no"], a3=name))
            it.setData(Qt.UserRole, idx)
            self.list_log.addItem(it)
        self.card_log.set_title(tr("util.lucky.card.log_n", a0=len(self.session.rounds) + len(self.session.combos)))
        self._refresh_lock()

    def _refresh_draw_status(self):
        avail = len(self.session.available_keys())
        total = len(self.session.entries)
        if self.current_type() == "ticket":
            self.lbl_draw_status.setText(tr("util.lucky.status.ticket", a0=total - len(self.session.excluded)))
        else:
            self.lbl_draw_status.setText(tr("util.lucky.status.remaining", a0=avail, a1=total))

    # ================================================================ 저장
    def _autosave_session(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET["session"], json.dumps(self.session.to_dict(), ensure_ascii=False))

    def _save_settings(self):
        if self._settings is None or self._loading:
            return
        s = self._settings
        s.setValue(_SET["type"], self.current_type())
        s.setValue(_SET["start"], str(self.spin_start.value()))
        s.setValue(_SET["end"], str(self.spin_end.value()))
        s.setValue(_SET["combo_k"], str(self.spin_combo_k.value()))
        s.setValue(_SET["repeat"], str(self.spin_repeat.value()))
        s.setValue(_SET["speed"], self.combo_speed.currentData())
        s.setValue(_SET["theme"], self.combo_theme.currentData())
        s.setValue(_SET["exclude"], "1" if self.chk_exclude.isChecked() else "0")
        s.setValue(_SET["roster"], B.roster_to_json(self.roster))
        s.setValue(_SET["names"], json.dumps(self.names, ensure_ascii=False))
        s.setValue(_SET["source"], self.source)
        cls = self.combo_class.currentData()
        s.setValue(_SET["class"], json.dumps(cls if cls != "all" else None))
        s.setValue(_SET["label"], self.edit_label.text())
        self._autosave_session()

    def _load_settings(self):
        s = self._settings
        if s is None:
            self.session = L.DrawSession(*self._entries_type())
            self.scene.set_session(self.session)
            return

        def _int(key, default):
            try:
                return int(s.value(_SET[key], default))
            except (TypeError, ValueError):
                return default

        t = s.value(_SET["type"], "range")
        (self.radio_types.get(t) or self.radio_types["range"]).setChecked(True)
        self.spin_start.setValue(_int("start", 1))
        self.spin_end.setValue(_int("end", 30))
        self.spin_combo_k.setValue(_int("combo_k", 6))
        self.spin_repeat.setValue(_int("repeat", 1))
        for combo, key, default in ((self.combo_speed, "speed", "normal"), (self.combo_theme, "theme", "stadium")):
            idx = combo.findData(s.value(_SET[key], default))
            combo.setCurrentIndex(idx if idx >= 0 else combo.findData(default))
        self.chk_exclude.setChecked(s.value(_SET["exclude"], "1") != "0")
        self.roster = B.roster_from_json(s.value(_SET["roster"], ""))
        try:
            self.names = list(json.loads(s.value(_SET["names"], "[]") or "[]"))
        except ValueError:
            self.names = []
        self.source = s.value(_SET["source"], "roster") or "roster"
        self.edit_label.setText(s.value(_SET["label"], "") or "")
        self._refresh_class_combo()
        try:
            cls = json.loads(s.value(_SET["class"], "null") or "null")
        except ValueError:
            cls = None
        if cls:
            idx = self.combo_class.findData(tuple(cls))
            if idx >= 0:
                self.combo_class.setCurrentIndex(idx)
        self.scene.set_theme(self.combo_theme.currentData())
        self.scene.set_speed(self.combo_speed.currentData())
        raw = s.value(_SET["session"], "")
        session = None
        if raw:
            try:
                session = L.DrawSession.from_dict(json.loads(raw))
            except (ValueError, KeyError, TypeError):
                session = None
        if session is None or not session.entries:
            session = L.DrawSession(*self._entries_type())
        self.session = session
        self.scene.set_session(session)

    def _entries_type(self):
        entries, _t = self.build_entries()
        return entries, self.current_type(), self.chk_exclude.isChecked()

    # ================================================================ 다국어
    def retranslate(self):
        self.card_stage.set_title(tr("util.lucky.card.stage"))
        self.btn_full_tool.setToolTip(tr("util.lucky.btn.fullscreen"))
        self.lbl_stage_hint.setText(tr("util.lucky.stage.hint"))
        self.card_setup.set_title(tr("util.lucky.card.setup"))
        for key, rb in self.radio_types.items():
            rb.setText(tr("util.lucky.type." + key))
        self.lbl_range.setText(tr("util.lucky.lbl.range"))
        self.lbl_combo_k.setText(tr("util.lucky.lbl.combo_k"))
        self.lbl_repeat.setText(tr("util.lucky.lbl.repeat"))
        self.lbl_speed.setText(tr("util.lucky.lbl.speed"))
        self.lbl_theme.setText(tr("util.lucky.lbl.theme"))
        for combo, prefix in ((self.combo_speed, "util.lucky.speed."), (self.combo_theme, "util.lucky.theme.")):
            for i in range(combo.count()):
                combo.setItemText(i, tr(prefix + combo.itemData(i)))
        self.lbl_label.setText(tr("util.lucky.lbl.label"))
        self.edit_label.setPlaceholderText(tr("util.lucky.lbl.label_ph"))
        self.chk_exclude.setText(tr("util.lucky.lbl.exclude"))
        self.btn_pool_toggle.setToolTip(tr("util.lucky.btn.toggle"))
        self.btn_log_toggle.setToolTip(tr("util.lucky.btn.toggle"))
        self.lbl_class.setText(tr("util.seating.lbl.class"))
        if self.combo_class.count():
            self.combo_class.setItemText(0, tr("util.lucky.class.all"))
        self.btn_template.setText(tr("util.seating.btn.template"))
        self.btn_upload.setText(tr("util.lucky.btn.upload"))
        self.btn_paste.setText(tr("util.lucky.btn.paste"))
        self.btn_roster_clear.setText(tr("util.lucky.btn.clear"))
        self.card_draw.set_title(tr("util.lucky.card.draw"))
        self.btn_reset.setText(tr("util.lucky.btn.reset"))
        self.btn_file.setText(tr("util.lucky.btn.file"))
        self.btn_replay.setText(tr("util.lucky.btn.replay"))
        self._apply_type_visibility()
        self._refresh_all()
        self.scene.update()


def B_class_options(roster):
    """명단에 있는 (학년, 반) 목록 — 좌석표와 같은 규칙(학년→반 순)."""
    from .seating_solve import class_options
    return class_options(roster)


class LuckyDrawApp(MiniApp):
    id = "lucky"
    icon = "lucky"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = LuckyDrawWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False   # 기록은 뽑을 때마다 자동 저장된다


def _t(ko, en, ja):
    return {"ko": ko, "en": en, "ja": ja}


TRANSLATIONS = {
    "util.lucky.title": _t("행운의 번호", "Lucky Draw", "ラッキー番号"),
    "util.lucky.desc": _t('Lucky LOTTO — 야구공 추첨 드럼으로 번호·명단(최대 120명)을 뽑습니다.', 'Lucky LOTTO — pick numbers or names (up to 120) with a baseball draw drum.', 'Lucky LOTTO — 野球ボールの抽選ドラムで番号・名簿（最大120名）を抽選します。'),
    "util.lucky.card.stage": _t("추첨 화면", "Draw Stage", "抽選画面"),
    "util.lucky.stage.hint": _t('스페이스: 뽑기 · ⛶ 전체화면(Esc)', 'Space: draw · ⛶ full screen (Esc)', 'スペース: 抽選・⛶ 全画面（Esc）'),
    "util.lucky.card.setup": _t("추첨 설정", "Draw Settings", "抽選設定"),
    "util.lucky.type.range": _t("번호 범위", "Number range", "番号範囲"),
    "util.lucky.type.roster": _t("명단 추첨", "Roster draw", "名簿抽選"),
    "util.lucky.type.combo": _t("조합 뽑기", "Combination", "組み合わせ"),
    "util.lucky.type.ticket": _t("번호표 발급", "Issue tickets", "番号札の発行"),
    "util.lucky.lbl.range": _t("번호", "Numbers", "番号"),
    "util.lucky.lbl.combo_k": _t("한 조합의 개수", "Numbers per combination", "1組の個数"),
    "util.lucky.lbl.repeat": _t("한 번에 뽑을 수", "Draws per press", "一度に引く数"),
    "util.lucky.lbl.speed": _t("속도", "Speed", "速度"),
    "util.lucky.lbl.theme": _t("테마", "Theme", "テーマ"),
    "util.lucky.lbl.label": _t("회차 이름", "Round label", "回の名前"),
    "util.lucky.lbl.label_ph": _t("예: 3등 상품, 발표 순서", "e.g. 3rd prize, presentation order",
                                  "例: 3等賞品、発表順"),
    "util.lucky.lbl.exclude": _t("뽑힌 사람은 다음 추첨에서 제외", "Exclude winners from later draws",
                                 "当選者は次の抽選から除外"),
    "util.lucky.speed.fast": _t("빠르게", "Fast", "速い"),
    "util.lucky.speed.normal": _t("보통", "Normal", "普通"),
    "util.lucky.speed.dramatic": _t("극적으로", "Dramatic", "ドラマチック"),
    "util.lucky.theme.stadium": _t("야구장", "Ballpark", "球場"),
    "util.lucky.theme.night": _t("야간 경기", "Night game", "ナイター"),
    "util.lucky.theme.classic": _t("밝은 화면(행사용)", "Bright (events)", "明るい（行事用）"),
    "util.lucky.locked.hint": _t("추첨 기록이 있어 대상 설정이 잠겨 있습니다. [초기화]하면 바꿀 수 있습니다.",
                                 "Target settings are locked while records exist. Press [Reset] to change them.",
                                 "抽選記録があるため対象設定はロック中です。[リセット]で変更できます。"),
    "util.lucky.locked.title": _t("추첨 진행 중", "Draw in progress", "抽選進行中"),
    "util.lucky.locked.msg": _t("이미 뽑은 기록이 있어 명단을 바꿀 수 없습니다. 기록을 저장한 뒤 [초기화]하세요.",
                                "Records already exist, so the list can't change. Save the records, then press [Reset].",
                                "すでに抽選記録があるため名簿を変更できません。記録を保存してから[リセット]してください。"),
    "util.lucky.btn.toggle": _t("펼치기/접기", "Expand/collapse", "開く/閉じる"),

    "util.lucky.card.pool_n": _t("추첨 대상 ({a0}명)", "Draw Targets ({a0})", "抽選対象（{a0}名）"),
    "util.lucky.pool.status": _t("대상 {a0}명 · 제외 {a1}명 (체크를 풀면 결석·제외)",
                                 "{a0} targets · {a1} excluded (uncheck to exclude)",
                                 "対象{a0}名・除外{a1}名（チェックを外すと欠席・除外）"),
    "util.lucky.pool.truncated": _t("최대 {a0}명까지만 추첨할 수 있어 앞의 {a0}명만 넣었습니다.",
                                    "Only the first {a0} were included (maximum {a0}).",
                                    "最大{a0}名までのため、先頭の{a0}名のみ入れました。"),
    "util.lucky.pool.clear_title": _t("명단 지우기", "Clear List", "名簿を削除"),
    "util.lucky.pool.clear_confirm": _t("불러온 명단과 붙여 넣은 이름을 모두 지울까요?",
                                        "Clear the uploaded roster and pasted names?",
                                        "読み込んだ名簿と貼り付けた名前をすべて削除しますか？"),
    "util.lucky.class.all": _t("전체", "All", "全体"),
    "util.lucky.btn.upload": _t("명단 업로드", "Upload", "名簿アップロード"),
    "util.lucky.btn.paste": _t("이름 붙여넣기", "Paste names", "名前を貼り付け"),
    "util.lucky.btn.clear": _t("지우기", "Clear", "削除"),
    "util.lucky.paste.title": _t("이름 붙여넣기", "Paste Names", "名前を貼り付け"),
    "util.lucky.paste.hint": _t("한 줄에 한 명씩 입력하세요(최대 {a0}명). 행사 사전 등록 명단을 그대로 붙여 넣으면 됩니다.",
                                "One name per line (up to {a0}). Paste a pre-registration list as is.",
                                "1行に1名ずつ入力してください（最大{a0}名）。事前登録名簿をそのまま貼り付けできます。"),

    "util.lucky.card.draw": _t("추첨", "Draw", "抽選"),
    "util.lucky.btn.draw": _t("뽑기", "Draw", "抽選"),
    "util.lucky.btn.ticket": _t("번호표 발급", "Issue", "発行"),
    "util.lucky.btn.reset": _t("초기화", "Reset", "リセット"),
    "util.lucky.btn.fullscreen": _t("전체화면", "Full screen", "全画面"),
    "util.lucky.status.remaining": _t("남은 대상 {a0} / {a1}", "{a0} of {a1} remaining", "残り {a0} / {a1}"),
    "util.lucky.status.ticket": _t("{a0}명에게 번호표를 발급합니다.", "Issue tickets to {a0} people.",
                                   "{a0}名に番号札を発行します。"),
    "util.lucky.status.none_left": _t("더 뽑을 대상이 없습니다.", "No one left to draw.", "抽選できる対象がありません。"),
    "util.lucky.status.pick_record": _t("재현할 기록을 목록에서 고르세요.", "Pick a record to replay.",
                                        "再現する記録を選んでください。"),
    "util.lucky.reset.title": _t("초기화", "Reset", "リセット"),
    "util.lucky.reset.confirm": _t("지금까지의 추첨 기록을 모두 지우고 처음부터 다시 할까요? (필요하면 먼저 기록을 저장하세요)",
                                   "Clear all draw records and start over? (Save them first if needed.)",
                                   "これまでの抽選記録をすべて消して最初からやり直しますか？（必要なら先に保存してください）"),

    "util.lucky.card.log_n": _t("추첨 기록 ({a0})", "Records ({a0})", "抽選記録（{a0}）"),
    "util.lucky.btn.file": _t("파일 ▾", "File ▾", "ファイル ▾"),
    "util.lucky.btn.replay": _t("재현", "Replay", "再現"),
    "util.lucky.file.csv": _t("기록 CSV 저장", "Save records (CSV)", "記録をCSV保存"),
    "util.lucky.file.save": _t("세션 저장", "Save session", "セッション保存"),
    "util.lucky.file.open": _t("세션 열기", "Open session", "セッションを開く"),
    "util.lucky.file.saved": _t("저장했습니다: {a0}", "Saved: {a0}", "保存しました: {a0}"),
    "util.lucky.csv.default_name": _t("추첨기록.csv", "draw_records.csv", "抽選記録.csv"),
    "util.lucky.session.default_name": _t("추첨세션.json", "draw_session.json", "抽選セッション.json"),
    "util.lucky.csv.label": _t("회차 이름", "Label", "回の名前"),
    "util.lucky.csv.order": _t("순서", "Order", "順番"),
    "util.lucky.csv.no": _t("번호", "Number", "番号"),
    "util.lucky.csv.name": _t("이름", "Name", "氏名"),
    "util.lucky.csv.at": _t("시각", "Time", "時刻"),
    "util.lucky.csv.seed": _t("시드", "Seed", "シード"),
    "util.lucky.log.item": _t('{a0}{a1}번째 → {a2}{a3}', '{a0}#{a1} → {a2}{a3}', '{a0}{a1}番目 → {a2}{a3}'),
    "util.lucky.log.combo_item": _t("{a0}조합: {a1}", "{a0}Combination: {a1}", "{a0}組み合わせ: {a1}"),
    "util.lucky.log.winner": _t('[행운의 번호] {a0}번째 당첨: {a1} {a2}', '[Lucky] Draw {a0}: {a1} {a2}', '[ラッキー番号] {a0}番目の当選: {a1} {a2}'),
    "util.lucky.log.combo": _t("[행운의 번호] 조합 완성: {a0}", "[Lucky] Combination: {a0}",
                               "[ラッキー番号] 組み合わせ完成: {a0}"),
    "util.lucky.log.roster": _t("[행운의 번호] 명단 {a0}명 불러옴", "[Lucky] Loaded {a0} names",
                                "[ラッキー番号] 名簿{a0}名を読み込み"),
    "util.lucky.log.names": _t("[행운의 번호] 이름 {a0}개 붙여넣음", "[Lucky] Pasted {a0} names",
                               "[ラッキー番号] 名前{a0}件を貼り付け"),

    "util.lucky.ticket.title": _t("번호표 발급", "Issue Tickets", "番号札の発行"),
    "util.lucky.ticket.hint": _t("명단 전원에게 서로 겹치지 않는 번호를 무작위로 하나씩 줍니다.",
                                 "Everyone on the list gets a unique random number.",
                                 "名簿の全員に重複しない番号をランダムに1つずつ付けます。"),
    "util.lucky.ticket.reshuffle": _t("다시 섞기", "Reshuffle", "再シャッフル"),
    "util.lucky.ticket.csv": _t("CSV 저장", "Save CSV", "CSV保存"),
    "util.lucky.ticket.print": _t("인쇄", "Print", "印刷"),
    "util.lucky.ticket.close": _t("닫기", "Close", "閉じる"),
    "util.lucky.ticket.col.ticket": _t("번호표", "Ticket", "番号札"),
    "util.lucky.ticket.col.name": _t("이름", "Name", "氏名"),
    "util.lucky.ticket.col.sub": _t("소속", "Group", "所属"),
    "util.lucky.ticket.default_name": _t("번호표.csv", "tickets.csv", "番号札.csv"),
    "util.lucky.ticket.empty": _t("번호표를 줄 명단이 없습니다. 명단을 업로드하거나 이름을 붙여 넣으세요.",
                                  "No names to issue tickets to. Upload a roster or paste names.",
                                  "番号札を付ける名簿がありません。名簿をアップロードするか名前を貼り付けてください。"),

    # 장면
    "util.lucky.scene.tray": _t("당첨 공 {a0} · 남은 공 {a1}", "Winners {a0} · Balls left {a1}", "当選 {a0} ・残り {a1}"),
    "util.lucky.scene.combo": _t("조합", "Combination", "組み合わせ"),
    "util.lucky.banner.replay": _t("추첨 재현 — {a0}번째 기록", "Replay — record #{a0}", "抽選の再現 — {a0}番目の記録"),
    "util.lucky.msg.idle": _t("뽑기를 누르세요", "Press Draw", "抽選を押してください"),
    "util.lucky.msg.last": _t("지난 당첨 번호", "Last winner", "前回の当選番号"),
    "util.lucky.msg.mixing": _t("공을 섞는 중...", "Mixing the balls...", "ボールを混ぜています..."),
    "util.lucky.msg.slowdown": _t("속도를 줄이는 중...", "Slowing down...", "減速中..."),
    "util.lucky.msg.countdown": _t("곧 뽑습니다!", "Drawing soon!", "まもなく抽選します！"),
    "util.lucky.msg.draw": _t("뽑는 중!", "Drawing!", "抽選中！"),
    "util.lucky.msg.won": _t("당첨!", "Winner!", "当選！"),
}
LuckyDrawApp.tr_table = TRANSLATIONS

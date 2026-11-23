# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 응원의 메시지 [v44]

활로 풍선을 맞히면 오늘의 응원 메시지가 펼쳐진다. 기본 메시지 120개 +
교사가 입력한 메시지 중에서 **날마다 다른 메시지**가 나오도록 덱 방식으로
고른다(규칙은 cheer_logic.py 머리말). 계획서: docs/PLAN_v44_lucky_cheer.md 3장.

메시지 본문은 1차로 한국어만 둔다(계획서 결정). 버튼·안내 등 **화면 UI 문구**는
다른 미니앱과 똑같이 ko/en/ja 3개 언어로 번역한다.
"""
import random as _random
from datetime import date as _date

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QCheckBox, QLabel, QDialog,
    QDialogButtonBox, QPlainTextEdit, QLineEdit, QDateEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QFormLayout, QScrollArea
)

from ..config import desktop_file
from ..i18n import tr, TR
from . import ui_kit as UK
from .base import MiniApp
from . import cheer_logic as CL
from .cheer_messages import CATEGORIES
from .anim_kit import FullscreenPresenter
from .cheer_scene import CheerScene

_SET_USER = "util.cheer.user"
_SET_STATE = "util.cheer.state"
_SET_DIFF = "util.cheer.difficulty"
_SET_COUNT = "util.cheer.count"
_SET_GUIDE = "util.cheer.guide"


def _category_lookup():
    """엑셀의 분류 칸 → 내부 키. 세 언어의 표시 문구와 내부 키 자체를 모두 받는다."""
    table = {}
    for key in CATEGORIES:
        table[key] = key
        entry = TR.get("util.cheer.cat." + key) or {}
        for text in entry.values():
            table[text] = key
    return table


# =============================================================================
# 메시지 편집 창
# =============================================================================
class _MessageEditDialog(QDialog):
    def __init__(self, msg=None, today=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("util.cheer.edit.title_edit" if msg else "util.cheer.edit.title_add"))
        self.resize(460, 320)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edit_text = QPlainTextEdit()
        self.edit_text.setPlaceholderText(tr("util.cheer.edit.text_ph", a0=CL.MAX_TEXT))
        self.edit_text.setFixedHeight(90)
        self.edit_sub = QLineEdit()
        self.edit_sub.setPlaceholderText(tr("util.cheer.edit.sub_ph"))
        self.combo_cat = QComboBox()
        for key in CATEGORIES:
            self.combo_cat.addItem(tr("util.cheer.cat." + key), key)
        self.chk_date = QCheckBox(tr("util.cheer.edit.dated"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate(today.year, today.month, today.day) if today else QDate.currentDate())
        self.date_edit.setEnabled(False)
        self.chk_date.toggled.connect(self.date_edit.setEnabled)
        form.addRow(tr("util.cheer.edit.text"), self.edit_text)
        form.addRow(tr("util.cheer.edit.sub"), self.edit_sub)
        form.addRow(tr("util.cheer.edit.category"), self.combo_cat)
        form.addRow(self.chk_date, self.date_edit)
        lay.addLayout(form)
        lay.addWidget(UK.hint_label(tr("util.cheer.edit.dated_hint")))
        self.err = UK.error_label()
        lay.addWidget(self.err)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        if msg:
            self.edit_text.setPlainText(msg.get("text", ""))
            self.edit_sub.setText(msg.get("sub", ""))
            self.combo_cat.setCurrentIndex(max(0, self.combo_cat.findData(msg.get("category", "cheer"))))
            if msg.get("date"):
                self.chk_date.setChecked(True)
                self.date_edit.setDate(QDate.fromString(msg["date"], "yyyy-MM-dd"))

    def _accept(self):
        if not self.edit_text.toPlainText().strip():
            self.err.setText(tr("util.cheer.edit.empty"))
            return
        self.accept()

    def values(self):
        return {"text": self.edit_text.toPlainText().strip()[:CL.MAX_TEXT],
                "sub": self.edit_sub.text().strip(),
                "category": self.combo_cat.currentData(),
                "date": self.date_edit.date().toString("yyyy-MM-dd") if self.chk_date.isChecked() else None}


class MessageManagerDialog(QDialog):
    """기본 메시지 사용 켜기/끄기 + 교사 메시지 추가·수정·삭제·엑셀 불러오기."""

    COLS = ("enabled", "category", "text", "sub", "date")

    def __init__(self, book, today, on_changed, parent=None):
        super().__init__(parent)
        self.book = book
        self.today = today
        self.on_changed = on_changed
        self.setWindowTitle(tr("util.cheer.manage.title"))
        self.resize(860, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.combo_filter = QComboBox()
        for key in ("all", "base", "user", "dated"):
            self.combo_filter.addItem(tr("util.cheer.manage.filter." + key), key)
        self.combo_filter.currentIndexChanged.connect(lambda _i: self.refresh())
        self.lbl_summary = UK.hint_label()
        top.addWidget(self.combo_filter)
        top.addWidget(self.lbl_summary, 1)
        lay.addLayout(top)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(lambda _it: self._on_edit())
        lay.addWidget(self.table, 1)
        lay.addWidget(UK.hint_label(tr("util.cheer.manage.hint")))
        row = QHBoxLayout()
        self.btn_delete = UK.danger_button(tr("util.cheer.manage.delete"))
        self.btn_template = UK.secondary_button(tr("util.cheer.manage.template"))
        self.btn_import = UK.secondary_button(tr("util.cheer.manage.import"))
        self.btn_edit = UK.secondary_button(tr("util.cheer.manage.edit"))
        self.btn_add = UK.primary_button(tr("util.cheer.manage.add"))
        self.btn_close = UK.neutral_button(tr("util.cheer.manage.close"))
        row.addWidget(self.btn_delete)
        row.addStretch()
        for b in (self.btn_template, self.btn_import, self.btn_edit, self.btn_add, self.btn_close):
            row.addWidget(b)
        lay.addLayout(row)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_import.clicked.connect(self._on_import)
        self.btn_template.clicked.connect(self._on_template)
        self.btn_close.clicked.connect(self.accept)
        self.refresh()

    def _rows(self):
        f = self.combo_filter.currentData()
        msgs = self.book.all_messages()
        if f == "base":
            msgs = [m for m in msgs if m.get("base")]
        elif f == "user":
            msgs = [m for m in msgs if not m.get("base")]
        elif f == "dated":
            msgs = [m for m in msgs if m.get("date")]
        return msgs

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setHorizontalHeaderLabels([tr("util.cheer.manage.col." + c) for c in self.COLS])
        rows = self._rows()
        self.table.setRowCount(len(rows))
        for r, m in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if m.get("enabled", True) else Qt.Unchecked)
            chk.setData(Qt.UserRole, m["id"])
            self.table.setItem(r, 0, chk)
            cat = tr("util.cheer.cat." + m.get("category", "cheer"))
            if not m.get("base"):
                cat += " ✎"
            for c, v in ((1, cat), (2, m.get("text", "")), (3, m.get("sub", "")), (4, m.get("date") or "")):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        n_base = len(self.book.base)
        n_base_on = n_base - len(self.book.base_disabled)
        self.lbl_summary.setText(tr("util.cheer.manage.summary", a0=n_base, a1=n_base_on, a2=len(self.book.user),
                                    a3=len(self.book.pool_ids())))

    def _selected_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        mid = item.data(Qt.UserRole)
        self.book.set_enabled(mid, item.checkState() == Qt.Checked)
        self.on_changed()
        self.refresh()

    def _on_add(self):
        dlg = _MessageEditDialog(None, self.today, self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        self.book.add_user(v["text"], v["sub"], v["category"], v["date"])
        self.on_changed()
        self.refresh()

    def _on_edit(self):
        mid = self._selected_id()
        if not mid or mid.startswith("base_"):
            QMessageBox.information(self, tr("util.cheer.manage.title"), tr("util.cheer.manage.base_readonly"))
            return
        msg = self.book.get(mid)
        dlg = _MessageEditDialog(msg, self.today, self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.book.update_user(mid, **dlg.values())
        self.on_changed()
        self.refresh()

    def _on_delete(self):
        mid = self._selected_id()
        if not mid or mid.startswith("base_"):
            QMessageBox.information(self, tr("util.cheer.manage.title"), tr("util.cheer.manage.base_readonly"))
            return
        reply = QMessageBox.question(self, tr("util.cheer.manage.delete"), tr("util.cheer.manage.delete_confirm"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.book.delete_user(mid)
        self.on_changed()
        self.refresh()

    def template_headers(self):
        return [tr("util.cheer.xl.text"), tr("util.cheer.xl.sub"), tr("util.cheer.xl.category"),
                tr("util.cheer.xl.date")]

    def _on_template(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("util.cheer.manage.template"),
                                              desktop_file(tr("util.cheer.xl.default_name")), "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        samples = [[tr("util.cheer.xl.sample1"), tr("util.cheer.xl.sample1_sub"), tr("util.cheer.cat.cheer"), ""],
                   [tr("util.cheer.xl.sample2"), "", tr("util.cheer.cat.exam"), "2026-11-18"]]
        try:
            CL.save_message_template(path, self.template_headers(), samples)
        except ImportError:
            QMessageBox.warning(self, tr("util.cheer.manage.template"), tr("util.bracket.roster.need_openpyxl"))
        except OSError as e:
            QMessageBox.warning(self, tr("util.cheer.manage.template"), str(e))

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("util.cheer.manage.import"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            rows = CL.read_message_excel(path, _category_lookup())
        except ImportError:
            QMessageBox.warning(self, tr("util.cheer.manage.import"), tr("util.bracket.roster.need_openpyxl"))
            return
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("util.cheer.manage.import"), str(e))
            return
        n = import_rows(self.book, rows)
        self.on_changed()
        self.refresh()
        QMessageBox.information(self, tr("util.cheer.manage.import"), tr("util.cheer.manage.imported", a0=n))


def import_rows(book, rows):
    """엑셀에서 읽은 행을 교사 메시지로 추가한다. 이미 같은 본문이 있으면 건너뛴다."""
    have = {m["text"] for m in book.user}
    n = 0
    for text, sub, cat, dt in rows:
        if text in have:
            continue
        if book.add_user(text, sub, cat, dt):
            have.add(text)
            n += 1
    return n


# =============================================================================
# 본 위젯
# =============================================================================
class CheerWidget(QWidget):
    def __init__(self, host, parent=None, today_func=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.today_func = today_func or _date.today
        self.book = CL.MessageBook()
        self.rng = _random.Random()
        self.today_ids = []
        self.last_mid = None
        self._loading = True
        self._build_ui()
        self._load_settings()
        self._loading = False
        self.retranslate()
        self.start_round()

    # ================================================================ UI
    def _build_ui(self):
        self.scene = CheerScene()
        self.scene.message_of = self.book.get
        self.scene.category_label = lambda key: tr("util.cheer.cat." + key)
        self.scene.balloonPopped.connect(self._on_popped)
        self.scene.cardClosed.connect(self._refresh_today)
        self.scene.missed.connect(self._refresh_today)
        self.scene.exitFullscreenRequested.connect(self._exit_fullscreen)
        self.presenter = FullscreenPresenter(self.scene)

        self.card_stage = UK.Card()
        self.btn_full_tool = self.card_stage.add_tool(UK.tool_button("⛶"))
        self.btn_full_tool.clicked.connect(self._toggle_fullscreen)
        self.card_stage.add_body(UK.canvas_frame(self.scene), 1)
        self.lbl_stage_hint = self.card_stage.add_footer_left(UK.hint_label())

        # ---- 오늘
        self.card_today = UK.Card()
        self.lbl_date = UK.body_label()
        self.lbl_remaining = UK.hint_label()
        self.card_today.add_body(self.lbl_date)
        self.card_today.add_body(self.lbl_remaining)
        self.lbl_diff = UK.body_label()
        self.combo_diff = QComboBox()
        for key in CL.DIFFICULTIES:
            self.combo_diff.addItem("", key)
        self.combo_diff.setCurrentIndex(1)
        self.combo_diff.currentIndexChanged.connect(self._on_diff_changed)
        self.card_today.add_body(UK.hrow(self.lbl_diff, self.combo_diff))
        self.lbl_count = UK.body_label()
        self.spin_count = QSpinBox()
        self.spin_count.setRange(3, 8)
        self.spin_count.setValue(6)
        self.spin_count.valueChanged.connect(self._on_count_changed)
        self.card_today.add_body(UK.hrow(self.lbl_count, self.spin_count, None))
        self.mode_group, radios = UK.radio_row(["", ""], checked_index=0)
        self.radio_modes = dict(zip(CL.MODES, radios))
        self.mode_group.buttonClicked.connect(lambda _b: self._on_mode_changed())
        self.card_today.add_body(UK.hrow(*radios, None))
        self.chk_guide = QCheckBox()
        self.chk_guide.toggled.connect(self._on_guide_toggled)
        self.card_today.add_body(self.chk_guide)
        self.hint_mode = UK.hint_label()
        self.card_today.add_body(self.hint_mode)
        self.btn_fullscreen = self.card_today.add_footer(UK.secondary_button())
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_again = self.card_today.add_footer(UK.primary_button())
        self.btn_again.clicked.connect(self.start_round)

        # ---- 메시지
        self.card_msg = UK.Card()
        self.lbl_summary = UK.hint_label()
        self.card_msg.add_body(self.lbl_summary)
        self.lbl_last_title = UK.body_label()
        self.lbl_last = QLabel()
        self.lbl_last.setWordWrap(True)
        self.lbl_last.setStyleSheet("color:#1a1a1a;font-size:13px;background:#ffffff;border:1px solid #d9dde3;"
                                    "border-radius:4px;padding:6px;")
        self.lbl_last.setMinimumHeight(60)
        self.card_msg.add_body(self.lbl_last_title)
        self.card_msg.add_body(self.lbl_last)
        self.btn_copy = self.card_msg.add_footer(UK.secondary_button())
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_manage = self.card_msg.add_footer(UK.secondary_button())
        self.btn_manage.clicked.connect(self._on_manage)

        right_inner = QWidget()
        right_lay = UK.vstack(self.card_today, self.card_msg)
        right_lay.addStretch(1)
        right_inner.setLayout(right_lay)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_inner)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        UK.split_lr(self, self.card_stage, scroll)

    # ================================================================ 오늘
    def today_str(self):
        return self.today_func().strftime("%Y-%m-%d")

    def date_label(self):
        d = self.today_func()
        return tr("util.cheer.date", a0=d.year, a1=d.month, a2=d.day, a3=tr(f"util.cheer.wd.{d.weekday()}"))

    def start_round(self):
        """오늘의 세트로 풍선을 띄운다(하루 고정이면 같은 날은 같은 메시지)."""
        self.today_ids = self.book.todays_set(self.today_str(), self.spin_count.value(), self.rng)
        self.scene.date_label = self.date_label()
        self.scene.guide_user = self.chk_guide.isChecked()
        self.scene.set_round(self.today_ids, self.combo_diff.currentData())
        self._save_state()
        self._refresh_today()
        self.scene.setFocus()

    def _on_popped(self, mid):
        self.last_mid = mid
        self._refresh_last()
        self._refresh_today()
        if self.host:
            m = self.book.get(mid)
            self.host.log(tr("util.cheer.log.popped", a0=(m or {}).get("text", "")[:40]))

    def _on_diff_changed(self, _i):
        if self._loading:
            return
        self._save_prefs()
        self.scene.set_round(self.today_ids, self.combo_diff.currentData())
        self._refresh_today()

    def _on_count_changed(self, _v):
        if self._loading:
            return
        self._save_prefs()
        self.start_round()

    def _on_mode_changed(self):
        self.book.mode = self.current_mode()
        self._save_state()
        self._refresh_today()

    def current_mode(self):
        for key, rb in self.radio_modes.items():
            if rb.isChecked():
                return key
        return "per_day"

    def _on_guide_toggled(self, on):
        self.scene.guide_user = bool(on)
        self._save_prefs()

    def _on_copy(self):
        m = self.book.get(self.last_mid) if self.last_mid else None
        if not m:
            return
        text = m["text"] + (f" — {m['sub']}" if m.get("sub") else "")
        QGuiApplication.clipboard().setText(text)
        if self.host:
            self.host.status(tr("util.cheer.copied"))

    def _on_manage(self):
        dlg = MessageManagerDialog(self.book, self.today_func(), self._on_book_changed, self)
        dlg.exec()

    def _on_book_changed(self):
        """메시지가 바뀌면 저장하고, 오늘 세트에서 빠진 메시지는 채워 넣는다."""
        self._save_state()
        pool = set(self.book.pool_ids())
        if any(mid not in pool for mid in self.today_ids):
            self.start_round()
        self._refresh_summary()
        self._refresh_last()

    # ================================================================ 전체화면
    def _toggle_fullscreen(self):
        self.presenter.title = tr("util.cheer.title")
        self.presenter.toggle()

    def _exit_fullscreen(self):
        if self.presenter.active:
            self.presenter.exit()

    # ================================================================ 표시
    def _refresh_today(self):
        self.lbl_date.setText(self.date_label())
        self.lbl_remaining.setText(tr("util.cheer.remaining", a0=self.scene.remaining(),
                                      a1=len(self.scene.balloons)))
        self.hint_mode.setText(tr("util.cheer.mode_hint." + self.current_mode()))

    def _refresh_summary(self):
        dated = len(self.book.dated_for(self.today_str()))
        self.lbl_summary.setText(tr("util.cheer.summary", a0=len(self.book.base) - len(self.book.base_disabled),
                                    a1=len([m for m in self.book.user if m.get('enabled', True)]), a2=dated))

    def _refresh_last(self):
        m = self.book.get(self.last_mid) if self.last_mid else None
        if m:
            self.lbl_last.setText(m["text"] + (f"\n— {m['sub']}" if m.get("sub") else ""))
        else:
            self.lbl_last.setText(tr("util.cheer.last_none"))
        self.btn_copy.setEnabled(m is not None)

    # ================================================================ 저장
    def _save_state(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_USER, self.book.user_to_json())
        self._settings.setValue(_SET_STATE, self.book.state_to_json())

    def _save_prefs(self):
        if self._settings is None or self._loading:
            return
        self._settings.setValue(_SET_DIFF, self.combo_diff.currentData())
        self._settings.setValue(_SET_COUNT, str(self.spin_count.value()))
        self._settings.setValue(_SET_GUIDE, "1" if self.chk_guide.isChecked() else "0")

    def _load_settings(self):
        s = self._settings
        if s is None:
            return
        self.book.load(s.value(_SET_USER, ""), s.value(_SET_STATE, ""))
        idx = self.combo_diff.findData(s.value(_SET_DIFF, "normal"))
        self.combo_diff.setCurrentIndex(idx if idx >= 0 else 1)
        try:
            self.spin_count.setValue(int(s.value(_SET_COUNT, "6")))
        except (TypeError, ValueError):
            pass
        self.chk_guide.setChecked(s.value(_SET_GUIDE, "0") == "1")
        self.radio_modes.get(self.book.mode, self.radio_modes["per_day"]).setChecked(True)

    # ================================================================ 다국어
    def retranslate(self):
        self.card_stage.set_title(tr("util.cheer.card.stage"))
        self.btn_full_tool.setToolTip(tr("util.cheer.btn.fullscreen"))
        self.lbl_stage_hint.setText(tr("util.cheer.stage.hint"))
        self.card_today.set_title(tr("util.cheer.card.today"))
        self.lbl_diff.setText(tr("util.cheer.lbl.difficulty"))
        for i in range(self.combo_diff.count()):
            self.combo_diff.setItemText(i, tr("util.cheer.diff." + self.combo_diff.itemData(i)))
        self.lbl_count.setText(tr("util.cheer.lbl.count"))
        for key, rb in self.radio_modes.items():
            rb.setText(tr("util.cheer.mode." + key))
        self.chk_guide.setText(tr("util.cheer.lbl.guide"))
        self.btn_fullscreen.setText(tr("util.cheer.btn.fullscreen"))
        self.btn_again.setText(tr("util.cheer.btn.again"))
        self.card_msg.set_title(tr("util.cheer.card.messages"))
        self.lbl_last_title.setText(tr("util.cheer.lbl.last"))
        self.btn_copy.setText(tr("util.cheer.btn.copy"))
        self.btn_manage.setText(tr("util.cheer.btn.manage"))
        self.scene.date_label = self.date_label()
        self._refresh_today()
        self._refresh_summary()
        self._refresh_last()
        self.scene.update()


class CheerApp(MiniApp):
    id = "cheer"
    icon = "cheer"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = CheerWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


def _t(ko, en, ja):
    return {"ko": ko, "en": en, "ja": ja}


TRANSLATIONS = {
    "util.cheer.title": _t("응원의 메시지", "Cheer Messages", "応援メッセージ"),
    "util.cheer.desc": _t("활로 풍선을 맞혀 오늘의 응원 메시지를 펼칩니다. 날마다 다른 메시지가 나옵니다.",
                          "Shoot balloons with a bow to reveal today's cheer messages — different every day.",
                          "弓で風船を割って今日の応援メッセージを開きます。毎日違うメッセージが出ます。"),
    "util.cheer.card.stage": _t("응원 화면", "Cheer Stage", "応援画面"),
    "util.cheer.stage.hint": _t("눌러서 뒤로 끌었다 놓기 · ⛶ 전체화면(Esc 복귀)",
                                "Press, drag back, release · ⛶ full screen (Esc)",
                                "押して引いて離す・⛶ 全画面（Esc）"),
    "util.cheer.card.today": _t("오늘", "Today", "今日"),
    "util.cheer.date": _t("{a0}년 {a1}월 {a2}일 ({a3})", "{a3}, {a1}/{a2}/{a0}", "{a0}年{a1}月{a2}日（{a3}）"),
    "util.cheer.wd.0": _t("월", "Mon", "月"),
    "util.cheer.wd.1": _t("화", "Tue", "火"),
    "util.cheer.wd.2": _t("수", "Wed", "水"),
    "util.cheer.wd.3": _t("목", "Thu", "木"),
    "util.cheer.wd.4": _t("금", "Fri", "金"),
    "util.cheer.wd.5": _t("토", "Sat", "土"),
    "util.cheer.wd.6": _t("일", "Sun", "日"),
    "util.cheer.remaining": _t("남은 풍선 {a0} / {a1}", "{a0} of {a1} balloons left", "残りの風船 {a0} / {a1}"),
    "util.cheer.lbl.difficulty": _t("난이도", "Difficulty", "難易度"),
    "util.cheer.diff.easy": _t("쉬움(큰 풍선·보조선)", "Easy (big balloons, guide)", "やさしい（大きな風船・補助線）"),
    "util.cheer.diff.normal": _t("보통(약한 바람)", "Normal (light wind)", "ふつう（弱い風）"),
    "util.cheer.diff.hard": _t("어려움(작은 풍선·센 바람)", "Hard (small balloons, strong wind)",
                               "むずかしい（小さな風船・強い風）"),
    "util.cheer.lbl.count": _t("풍선 수", "Balloons", "風船の数"),
    "util.cheer.mode.per_day": _t("하루 고정", "Same all day", "1日固定"),
    "util.cheer.mode.per_run": _t("열 때마다 새로", "New every time", "開くたびに新しく"),
    "util.cheer.mode_hint.per_day": _t("오늘 하루 동안은 다시 열어도 같은 메시지가 나옵니다(반마다 같은 응원).",
                                       "Reopening today shows the same messages (same cheer for every class).",
                                       "今日は開き直しても同じメッセージです（どのクラスでも同じ応援）。"),
    "util.cheer.mode_hint.per_run": _t("[다시 띄우기]를 누를 때마다 다음 메시지가 나옵니다.",
                                       "Each [Launch again] brings the next messages.",
                                       "[もう一度]を押すたびに次のメッセージが出ます。"),
    "util.cheer.lbl.guide": _t("조준 보조선 항상 보이기", "Always show aiming guide", "照準補助線を常に表示"),
    "util.cheer.btn.fullscreen": _t("전체화면", "Full screen", "全画面"),
    "util.cheer.btn.again": _t("다시 띄우기", "Launch again", "もう一度"),
    "util.cheer.card.messages": _t("메시지", "Messages", "メッセージ"),
    "util.cheer.summary": _t("기본 메시지 {a0}개 · 선생님 메시지 {a1}개 · 오늘 지정 {a2}개",
                             "{a0} built-in · {a1} teacher messages · {a2} set for today",
                             "基本{a0}件・先生のメッセージ{a1}件・今日指定{a2}件"),
    "util.cheer.lbl.last": _t("방금 펼친 메시지", "Last revealed message", "直前に開いたメッセージ"),
    "util.cheer.last_none": _t("아직 터뜨린 풍선이 없어요.", "No balloon popped yet.", "まだ割った風船はありません。"),
    "util.cheer.btn.copy": _t("복사", "Copy", "コピー"),
    "util.cheer.btn.manage": _t("메시지 관리", "Manage messages", "メッセージ管理"),
    "util.cheer.copied": _t("메시지를 복사했습니다.", "Message copied.", "メッセージをコピーしました。"),
    "util.cheer.log.popped": _t("[응원의 메시지] 풍선을 터뜨림: {a0}", "[Cheer] Popped: {a0}", "[応援] 風船を割った: {a0}"),

    "util.cheer.cat.cheer": _t("응원", "Cheer", "応援"),
    "util.cheer.cat.quote": _t("격언", "Saying", "格言"),
    "util.cheer.cat.exam": _t("시험", "Exams", "試験"),
    "util.cheer.cat.maker": _t("도전", "Challenge", "挑戦"),

    "util.cheer.manage.title": _t("메시지 관리", "Manage Messages", "メッセージ管理"),
    "util.cheer.manage.filter.all": _t("전체", "All", "すべて"),
    "util.cheer.manage.filter.base": _t("기본 메시지", "Built-in", "基本メッセージ"),
    "util.cheer.manage.filter.user": _t("선생님 메시지", "Teacher", "先生のメッセージ"),
    "util.cheer.manage.filter.dated": _t("날짜 지정", "Dated", "日付指定"),
    "util.cheer.manage.summary": _t("기본 {a0}개(사용 {a1}) · 선생님 {a2}개 · 지금 추첨 대상 {a3}개",
                                    "{a0} built-in ({a1} on) · {a2} teacher · {a3} in rotation",
                                    "基本{a0}件（使用{a1}）・先生{a2}件・現在の対象{a3}件"),
    "util.cheer.manage.hint": _t("체크를 풀면 그 메시지는 나오지 않습니다. 선생님 메시지(✎)는 더블클릭해 고칠 수 있고, "
                                 "날짜를 지정하면 그날 황금 풍선으로 먼저 나옵니다.",
                                 "Uncheck to stop a message. Double-click a teacher message (✎) to edit; "
                                 "a dated message appears first on that day as the golden balloon.",
                                 "チェックを外すとそのメッセージは出ません。先生のメッセージ（✎）はダブルクリックで編集でき、"
                                 "日付を指定するとその日に金色の風船として最初に出ます。"),
    "util.cheer.manage.col.enabled": _t("사용", "On", "使用"),
    "util.cheer.manage.col.category": _t("분류", "Type", "分類"),
    "util.cheer.manage.col.text": _t("본문", "Message", "本文"),
    "util.cheer.manage.col.sub": _t("보조 문구", "Byline", "補足"),
    "util.cheer.manage.col.date": _t("날짜", "Date", "日付"),
    "util.cheer.manage.add": _t("추가", "Add", "追加"),
    "util.cheer.manage.edit": _t("수정", "Edit", "編集"),
    "util.cheer.manage.delete": _t("삭제", "Delete", "削除"),
    "util.cheer.manage.delete_confirm": _t("선택한 메시지를 삭제할까요?", "Delete the selected message?",
                                           "選択したメッセージを削除しますか？"),
    "util.cheer.manage.import": _t("엑셀 불러오기", "Import Excel", "Excel読み込み"),
    "util.cheer.manage.imported": _t("메시지 {a0}개를 추가했습니다(같은 본문은 건너뜀).",
                                     "Added {a0} messages (duplicates skipped).",
                                     "メッセージを{a0}件追加しました（同じ本文はスキップ）。"),
    "util.cheer.manage.template": _t("양식 다운로드", "Download template", "様式ダウンロード"),
    "util.cheer.manage.close": _t("닫기", "Close", "閉じる"),
    "util.cheer.manage.base_readonly": _t("기본 메시지는 고치거나 지울 수 없고, 사용 체크만 끌 수 있습니다. "
                                          "선생님 메시지를 골라 주세요.",
                                          "Built-in messages can only be switched off. Select a teacher message.",
                                          "基本メッセージは編集・削除できず、使用のチェックだけ外せます。先生のメッセージを選んでください。"),
    "util.cheer.edit.title_add": _t("메시지 추가", "Add Message", "メッセージ追加"),
    "util.cheer.edit.title_edit": _t("메시지 수정", "Edit Message", "メッセージ編集"),
    "util.cheer.edit.text": _t("본문", "Message", "本文"),
    "util.cheer.edit.text_ph": _t("{a0}자 이내", "Up to {a0} characters", "{a0}文字以内"),
    "util.cheer.edit.sub": _t("보조 문구", "Byline", "補足"),
    "util.cheer.edit.sub_ph": _t("예: 담임 선생님이", "e.g. From your homeroom teacher", "例: 担任の先生より"),
    "util.cheer.edit.category": _t("분류", "Type", "分類"),
    "util.cheer.edit.dated": _t("날짜 지정", "Show on date", "日付指定"),
    "util.cheer.edit.dated_hint": _t("날짜를 지정하면 그날의 황금 풍선(오늘의 메시지)으로 먼저 나옵니다. 예: 시험 전날, 체육대회.",
                                     "A dated message comes first on that day as the golden balloon — e.g. the day before exams.",
                                     "日付を指定するとその日の金色の風船（今日のメッセージ）として最初に出ます。例: 試験前日、体育祭。"),
    "util.cheer.edit.empty": _t("본문을 입력해 주세요.", "Please enter a message.", "本文を入力してください。"),
    "util.cheer.xl.text": _t("본문", "Message", "本文"),
    "util.cheer.xl.sub": _t("보조 문구", "Byline", "補足"),
    "util.cheer.xl.category": _t("분류", "Type", "分類"),
    "util.cheer.xl.date": _t("날짜(YYYY-MM-DD)", "Date (YYYY-MM-DD)", "日付(YYYY-MM-DD)"),
    "util.cheer.xl.default_name": _t("응원메시지_양식.xlsx", "cheer_messages_template.xlsx", "応援メッセージ_様式.xlsx"),
    "util.cheer.xl.sample1": _t("오늘도 수고했어, 우리 반!", "Great work today, everyone!", "今日もお疲れさま、みんな！"),
    "util.cheer.xl.sample1_sub": _t("담임 선생님이", "Your homeroom teacher", "担任の先生より"),
    "util.cheer.xl.sample2": _t("내일은 지금까지 준비한 만큼만 보여 주면 돼.", "Tomorrow, just show what you've prepared.",
                                "明日はこれまで準備した分だけ見せれば大丈夫。"),

    # 장면
    "util.cheer.scene.title": _t("오늘의 응원", "Today's Cheer", "今日の応援"),
    "util.cheer.scene.all_done": _t("오늘의 메시지를 모두 펼쳤어요!", "You've opened every message for today!",
                                    "今日のメッセージを全部開きました！"),
    "util.cheer.scene.all_done_hint": _t("[다시 띄우기]로 풍선을 다시 띄울 수 있어요.",
                                         "Use [Launch again] to bring the balloons back.",
                                         "[もう一度]で風船をまた浮かべられます。"),
    "util.cheer.scene.wind": _t("바람 {a0} {a1}단계", "Wind {a0} level {a1}", "風 {a0} {a1}段階"),
    "util.cheer.scene.wind_none": _t("바람 없음", "No wind", "無風"),
    "util.cheer.scene.remaining": _t("남은 풍선 {a0} / {a1}", "{a0} / {a1} left", "残り {a0} / {a1}"),
    "util.cheer.scene.power": _t("힘 {a0}%", "Power {a0}%", "力 {a0}%"),
    "util.cheer.scene.how": _t("화면을 눌러 뒤로 끌었다 놓으면 활을 쏠 수 있어요. 금색 풍선이 오늘의 메시지!",
                               "Press, drag back and release to shoot. The gold balloon holds today's message!",
                               "押して後ろに引いて離すと弓を射てます。金色の風船が今日のメッセージ！"),
    "util.cheer.scene.today_message": _t("오늘의 메시지 · {a0}", "Today's message · {a0}", "今日のメッセージ・{a0}"),
    "util.cheer.scene.close_hint": _t("클릭하거나 스페이스를 누르면 닫혀요", "Click or press Space to close",
                                      "クリックかスペースで閉じます"),
}
CheerApp.tr_table = TRANSLATIONS

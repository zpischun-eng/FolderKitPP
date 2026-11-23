# -*- coding: utf-8 -*-
"""
FolderKit — 환경설정 다이얼로그(SettingsDialog) / 동기화 미리보기 다이얼로그(PreviewDialog)
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QRadioButton, QGroupBox,
    QDialogButtonBox, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QPushButton, QSpinBox, QButtonGroup, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from collections import Counter

from .styles import C
from .config import Config
from .sync_core import ONLY_L, ONLY_R, NEWER_L, NEWER_R, CONFLICT, SAME
from .i18n import tr, LANGUAGES, LANGUAGE_LABELS


# =============================================================================
# 4-b. 단축키 도움말 다이얼로그 [v32]
# =============================================================================
class ShortcutsDialog(QDialog):
    """환경설정의 '단축키 보기' 버튼으로 여는, 프로그램 전체 단축키 안내 팝업."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("shortcuts.title"))
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog{{background-color:{C.WINDOW_BG};color:{C.WINDOW_FG};}}"
            f"QLabel{{color:{C.WINDOW_FG};}}")
        lay = QVBoxLayout(self)

        def add_section(title_key, item_keys):
            title = QLabel(f"<b>{tr(title_key)}</b>")
            title.setStyleSheet("font-size:13px;margin-top:6px;")
            lay.addWidget(title)
            for k in item_keys:
                lbl = QLabel(tr(k))
                lbl.setStyleSheet("font-size:12px;padding-left:6px;")
                lbl.setTextFormat(Qt.RichText)
                lay.addWidget(lbl)

        add_section("shortcuts.section_global", ["shortcuts.f5"])
        add_section("shortcuts.section_imgedit", [
            "shortcuts.space", "shortcuts.ctrl_s", "shortcuts.ctrl_z",
            "shortcuts.ctrl_y", "shortcuts.m", "shortcuts.c",
            "shortcuts.s", "shortcuts.esc",
        ])

        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


# =============================================================================
# 5. 환경설정 다이얼로그
# =============================================================================
class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.language_changed = False  # [v25] MainWindow가 저장 후 재번역할지 판단
        self.cache_size_changed = False  # [v37] MainWindow가 저장 후 캐시 재조정할지 판단
        self.quicklinks_changed = False  # [v45] MainWindow가 저장 후 바로가기 목록을 다시 그릴지 판단
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog{{background-color:{C.WINDOW_BG};color:{C.WINDOW_FG};}}"
            f"QGroupBox{{color:{C.WINDOW_FG};font-weight:bold;border:1px solid {C.BORDER};"
            f"border-radius:6px;margin-top:8px;padding:8px;}}"
            f"QGroupBox::title{{subcontrol-origin:margin;left:10px;padding:0 4px;}}"
            f"QRadioButton,QCheckBox,QLabel{{color:{C.WINDOW_FG};}}"
        )
        lay = QVBoxLayout(self)

        # [v25] 언어 — 한국어/English/日本語
        g0 = QGroupBox(tr("settings.group_language"))
        v0 = QHBoxLayout(g0)
        self.lang_radios = {}
        for code in LANGUAGES:
            rb = QRadioButton(LANGUAGE_LABELS[code])
            v0.addWidget(rb)
            self.lang_radios[code] = rb
        self.lang_radios.get(cfg.language, self.lang_radios["ko"]).setChecked(True)
        lay.addWidget(g0)

        # 동기화 방향
        g1 = QGroupBox(tr("settings.group_direction"))
        v1 = QVBoxLayout(g1)
        self.rb_both = QRadioButton(tr("settings.rb_both"))
        self.rb_l2r  = QRadioButton(tr("settings.rb_l2r"))
        self.rb_r2l  = QRadioButton(tr("settings.rb_r2l"))
        for rb in (self.rb_both, self.rb_l2r, self.rb_r2l):
            v1.addWidget(rb)
        {"both": self.rb_both, "l2r": self.rb_l2r, "r2l": self.rb_r2l}[cfg.direction].setChecked(True)
        lay.addWidget(g1)

        # 정책
        g2 = QGroupBox(tr("settings.group_policy"))
        v2 = QVBoxLayout(g2)
        self.cb_backup = QCheckBox(tr("settings.cb_backup"))
        self.cb_backup.setChecked(cfg.backup)
        self.cb_preview = QCheckBox(tr("settings.cb_preview"))
        self.cb_preview.setChecked(cfg.preview)
        self.cb_mirror = QCheckBox(tr("settings.cb_mirror"))
        self.cb_mirror.setChecked(cfg.mirror)
        for cb in (self.cb_backup, self.cb_preview, self.cb_mirror):
            v2.addWidget(cb)
        note = QLabel(tr("settings.policy_note"))
        note.setStyleSheet("color:#666;font-size:11px;")
        v2.addWidget(note)
        lay.addWidget(g2)

        # [v37] 이미지 편집 모드 — 썸네일 캐시 크기
        # 프리셋(라디오) + 직접 입력(스핀박스) 조합. 프리셋을 고르면 스핀박스가
        # 그 값으로 맞춰지고, 스핀박스를 직접 조작하면 자동으로 "직접 입력"이
        # 선택된 것으로 간주한다(별도 라디오 항목 없이, 값이 프리셋과 다르면
        # 자연히 아무 프리셋도 체크되지 않은 상태가 된다).
        g3 = QGroupBox(tr("settings.group_thumbcache"))
        v3 = QVBoxLayout(g3)

        cache_row = QHBoxLayout()
        self.cache_presets = {}
        self.cache_btn_group = QButtonGroup(self)
        self.cache_btn_group.setExclusive(True)
        for value, key in (
            (1000, "settings.cache_low"),
            (3000, "settings.cache_default"),
            (5000, "settings.cache_high"),
            (10000, "settings.cache_veryhigh"),
        ):
            rb = QRadioButton(tr(key))
            cache_row.addWidget(rb)
            self.cache_btn_group.addButton(rb)
            self.cache_presets[value] = rb
        v3.addLayout(cache_row)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel(tr("settings.cache_custom_label")))
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(Config.THUMB_CACHE_MIN, Config.THUMB_CACHE_MAX)
        self.cache_spin.setSingleStep(500)
        self.cache_spin.setSuffix(tr("settings.cache_unit_suffix"))
        self.cache_spin.setValue(cfg.thumb_cache_size)
        custom_row.addWidget(self.cache_spin)
        custom_row.addStretch()
        v3.addLayout(custom_row)

        # 프리셋 라디오 선택 시 스핀박스에 반영
        for value, rb in self.cache_presets.items():
            rb.toggled.connect(
                lambda checked, v=value: self.cache_spin.setValue(v) if checked else None
            )
        # 현재 저장된 값이 프리셋 중 하나와 같으면 그 라디오를 체크
        matching = self.cache_presets.get(cfg.thumb_cache_size)
        if matching:
            matching.setChecked(True)

        self.cache_mem_lbl = QLabel()
        self.cache_mem_lbl.setStyleSheet("color:#666;font-size:11px;")
        v3.addWidget(self.cache_mem_lbl)
        self.cache_spin.valueChanged.connect(self._update_cache_mem_label)
        # [v37] 스핀박스 값이 프리셋과 어긋나면 라디오 체크를 모두 해제해
        # "값은 3500인데 화면엔 기본(3000장)이 선택된 것처럼 보이는" 표시
        # 불일치를 막는다. 반대로 값이 어떤 프리셋과 정확히 같아지면(직접
        # 타이핑으로도) 그 프리셋을 자동으로 체크해 준다.
        self.cache_spin.valueChanged.connect(self._sync_cache_preset_radios)
        self._update_cache_mem_label(cfg.thumb_cache_size)

        lay.addWidget(g3)

        # [v45] 즐겨찾기 바로가기(트리 위에 표시되는 바탕화면/다운로드/메신저
        # 폴더 등) — 추가/삭제/경로 변경을 여기서 한다.
        g4 = QGroupBox(tr("settings.group_quicklinks"))
        v4 = QVBoxLayout(g4)
        note4 = QLabel(tr("settings.quicklinks_note"))
        note4.setWordWrap(True)
        note4.setStyleSheet("color:#666;font-size:11px;")
        v4.addWidget(note4)

        self.quicklinks_table = QTableWidget(0, 2)
        self.quicklinks_table.setHorizontalHeaderLabels(
            [tr("settings.quicklinks_col_label"), tr("settings.quicklinks_col_path")])
        self.quicklinks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.quicklinks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.quicklinks_table.verticalHeader().setVisible(False)
        self.quicklinks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.quicklinks_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.quicklinks_table.setMaximumHeight(160)
        for link in cfg.quick_links:
            self._quicklinks_add_row(link.get("label", ""), link.get("path", ""), link.get("icon"))
        v4.addWidget(self.quicklinks_table)

        qrow = QHBoxLayout()
        btn_ql_add = QPushButton(tr("settings.quicklinks_add"))
        btn_ql_add.clicked.connect(self._on_quicklink_add)
        btn_ql_browse = QPushButton(tr("settings.quicklinks_browse"))
        btn_ql_browse.clicked.connect(self._on_quicklink_browse)
        btn_ql_remove = QPushButton(tr("settings.quicklinks_remove"))
        btn_ql_remove.clicked.connect(self._on_quicklink_remove)
        for b in (btn_ql_add, btn_ql_browse, btn_ql_remove):
            qrow.addWidget(b)
        qrow.addStretch()
        v4.addLayout(qrow)

        lay.addWidget(g4)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        reset_btn = bb.button(QDialogButtonBox.RestoreDefaults)
        reset_btn.setText(tr("settings.reset_btn"))
        reset_btn.setStyleSheet("color:#d32f2f;")
        reset_btn.clicked.connect(self.on_reset_clicked)
        # [v32] 단축키 도움말 — HelpRole로 추가하면 다른 버튼들과 자연스럽게
        # 떨어진 자리(대개 맨 왼쪽)에 배치된다.
        shortcuts_btn = bb.addButton(tr("settings.shortcuts_btn"), QDialogButtonBox.HelpRole)
        shortcuts_btn.clicked.connect(self.on_shortcuts_clicked)
        lay.addWidget(bb)

    def on_shortcuts_clicked(self):
        ShortcutsDialog(self).exec()

    def _quicklinks_add_row(self, label, path, icon=None):
        """[v47] icon은 화면에 보이는 열이 아니라, 첫 번째 칸 아이템의
        UserRole 데이터로만 보관한다 — "바탕화면/다운로드/문서/사진/음악/
        동영상" 같은 탐색기풍 아이콘 종류를 accept() 때 다시 꺼내 저장해,
        설정 창을 열고 닫을 때마다 아이콘이 사용자 아이콘(custom)으로
        초기화되지 않게 한다."""
        row = self.quicklinks_table.rowCount()
        self.quicklinks_table.insertRow(row)
        label_item = QTableWidgetItem(label)
        label_item.setData(Qt.UserRole, icon)
        self.quicklinks_table.setItem(row, 0, label_item)
        self.quicklinks_table.setItem(row, 1, QTableWidgetItem(path))

    def _on_quicklink_add(self):
        self._quicklinks_add_row(tr("settings.quicklinks_new_label"), "")
        self.quicklinks_table.setCurrentCell(self.quicklinks_table.rowCount() - 1, 0)
        self.quicklinks_table.editItem(
            self.quicklinks_table.item(self.quicklinks_table.rowCount() - 1, 0))

    def _on_quicklink_browse(self):
        row = self.quicklinks_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, tr("msg.title.info"), tr("settings.quicklinks_select_row_first"))
            return
        start_dir = self.quicklinks_table.item(row, 1).text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, tr("settings.quicklinks_browse"), start_dir)
        if path:
            self.quicklinks_table.setItem(row, 1, QTableWidgetItem(path))

    def _on_quicklink_remove(self):
        row = self.quicklinks_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, tr("msg.title.info"), tr("settings.quicklinks_select_row_first"))
            return
        self.quicklinks_table.removeRow(row)

    def _update_cache_mem_label(self, value):
        """[v37] 스핀박스 값이 바뀔 때마다 예상 메모리 사용량을 갱신 표시.
        썸네일 1장(72x72 RGBA)의 실측 크기는 20,736바이트 — 여기에 dict/캐시
        관리 오버헤드를 넉넉히 더해 21KB/장으로 어림잡아 계산한다."""
        mb = (value * 21) / 1024
        self.cache_mem_lbl.setText(tr("settings.cache_mem_estimate", mb=f"{mb:.0f}"))

    def _sync_cache_preset_radios(self, value):
        """[v37] 스핀박스 값과 프리셋 라디오 표시를 항상 일치시킨다.
        - 값이 어떤 프리셋과 정확히 같으면 그 라디오를 체크(직접 타이핑으로
          프리셋 숫자와 같아진 경우도 포함)
        - 어떤 프리셋과도 다르면 전부 체크 해제(=화면상 "직접 입력" 상태로
          보이게 함) — 그대로 두면 이전에 눌렀던 프리셋이 계속 체크된
          것처럼 보여 실제 값과 화면 표시가 어긋나 보이는 문제가 있었다."""
        matching = self.cache_presets.get(value)
        if matching and matching.isChecked():
            return  # 이미 일치하는 라디오가 체크되어 있음 — 손댈 것 없음
        self.cache_btn_group.setExclusive(False)
        for v, rb in self.cache_presets.items():
            rb.setChecked(v == value)
        self.cache_btn_group.setExclusive(True)

    def on_reset_clicked(self):
        """[v19] 환경설정 + 최근 작업 히스토리를 전부 초기화(레지스트리/설정 저장소 삭제)."""
        reply = QMessageBox.question(
            self, tr("settings.reset_confirm_title"),
            tr("settings.reset_confirm_body"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        Config.reset_all()
        fresh = Config()  # 방금 비운 저장소에서 다시 읽으면 기본값이 나온다
        self.cfg.direction = fresh.direction
        self.cfg.mirror = fresh.mirror
        self.cfg.backup = fresh.backup
        self.cfg.preview = fresh.preview
        self.cfg.language = fresh.language
        self.cfg.thumb_cache_size = fresh.thumb_cache_size
        self.cfg.quick_links = fresh.quick_links
        {"both": self.rb_both, "l2r": self.rb_l2r, "r2l": self.rb_r2l}[self.cfg.direction].setChecked(True)
        self.cb_backup.setChecked(self.cfg.backup)
        self.cb_preview.setChecked(self.cfg.preview)
        self.cb_mirror.setChecked(self.cfg.mirror)
        self.lang_radios.get(self.cfg.language, self.lang_radios["ko"]).setChecked(True)
        # [v37] setValue()가 valueChanged를 발생시켜 _sync_cache_preset_radios가
        # 자동으로 프리셋 라디오 체크 상태를 맞춰준다(수동 처리 불필요).
        self.cache_spin.setValue(self.cfg.thumb_cache_size)
        self.quicklinks_table.setRowCount(0)
        for link in self.cfg.quick_links:
            self._quicklinks_add_row(link.get("label", ""), link.get("path", ""), link.get("icon"))
        QMessageBox.information(self, tr("settings.reset_done_title"), tr("settings.reset_done_body"))

    def accept(self):
        if self.rb_both.isChecked(): self.cfg.direction = "both"
        elif self.rb_l2r.isChecked(): self.cfg.direction = "l2r"
        else: self.cfg.direction = "r2l"
        self.cfg.backup = self.cb_backup.isChecked()
        self.cfg.preview = self.cb_preview.isChecked()
        self.cfg.mirror = self.cb_mirror.isChecked()
        new_lang = next((code for code, rb in self.lang_radios.items() if rb.isChecked()), self.cfg.language)
        self.language_changed = (new_lang != self.cfg.language)
        self.cfg.language = new_lang
        old_cache_size = self.cfg.thumb_cache_size
        self.cfg.thumb_cache_size = self.cache_spin.value()
        self.cache_size_changed = (self.cfg.thumb_cache_size != old_cache_size)

        # [v45] 바로가기 표 → cfg.quick_links. 라벨/경로 둘 다 빈 줄은 저장하지
        # 않는다(예: '추가'만 누르고 아무것도 입력하지 않은 빈 행).
        # [v47] icon(첫 칸 UserRole)도 함께 저장해, 탐색기풍 아이콘이 설정
        # 창을 열고 닫을 때마다 사용자 아이콘으로 초기화되지 않게 한다.
        new_links = []
        for row in range(self.quicklinks_table.rowCount()):
            label = (self.quicklinks_table.item(row, 0).text() or "").strip()
            path = (self.quicklinks_table.item(row, 1).text() or "").strip()
            icon = self.quicklinks_table.item(row, 0).data(Qt.UserRole)
            if label or path:
                link = {"label": label, "path": path}
                if icon:
                    link["icon"] = icon
                new_links.append(link)
        self.quicklinks_changed = (new_links != self.cfg.quick_links)
        self.cfg.quick_links = new_links

        if self.cfg.mirror and self.cfg.direction == "both":
            QMessageBox.warning(self, tr("settings.mirror_warn_title"), tr("settings.mirror_warn_body"))
        # [v37] 저사양 PC 보호 — 큰 캐시(10000개 초과, 약 200MB 이상)를
        # 선택하면 한 번 더 확인 안내를 보여준다. 값 자체는 이미
        # THUMB_CACHE_MAX(20000)로 상한이 걸려 있어 시스템이 실제로 죽을
        # 정도의 값은 애초에 입력할 수 없다 — 이 메시지는 저사양 PC에서
        # 불필요하게 큰 값을 고르지 않도록 안내하는 참고용일 뿐이다.
        if self.cfg.thumb_cache_size > 10000:
            QMessageBox.information(
                self, tr("settings.cache_warn_title"),
                tr("settings.cache_warn_body", mb=f"{(self.cfg.thumb_cache_size*21)/1024:.0f}")
            )
        self.cfg.save()
        super().accept()


# =============================================================================
# 6. 미리보기 다이얼로그
# =============================================================================
def _state_label(state):
    """[v39] 언어 전환 시 즉시 반영되도록, 모듈 로드 시점에 고정되는 dict 대신
    호출 시점에 tr()을 평가하는 함수로 바꿨다."""
    table = {
        ONLY_L: (tr("sync.state.only_l"), C.LEFT_MAIN),
        ONLY_R: (tr("sync.state.only_r"), C.RIGHT_MAIN),
        NEWER_L: (tr("sync.state.newer_l"), "#e08e0b"),
        NEWER_R: (tr("sync.state.newer_r"), "#e08e0b"),
        CONFLICT: (tr("sync.state.conflict"), "#d32f2f"),
        SAME: (tr("sync.state.same"), "#888888"),
    }
    return table.get(state, (state, "#000"))


def _act_label(act):
    table = {
        ("copy", "L2R"): tr("sync.action.copy_to_right"),
        ("copy", "R2L"): tr("sync.action.copy_to_left"),
        ("delete", "L"): tr("sync.action.delete_from_left"),
        ("delete", "R"): tr("sync.action.delete_from_right"),
    }
    return table.get(act, str(act))


_ACT_KEYS = {("copy", "L2R"), ("copy", "R2L"), ("delete", "L"), ("delete", "R")}


def _summarize_key(act):
    kind, arg = act
    return _act_label(act) if act in _ACT_KEYS else f"{kind}:{arg}"


class PreviewDialog(QDialog):
    """동기화 실행 전 미리보기.
    [v20] 대량 변경(수만~수십만 건)에서 몇 시간씩 "응답 없음"으로 멈추던 문제를 修正.
    원인은 행마다 실제 QCheckBox 위젯을 만들어 setCellWidget으로 끼워 넣던 방식 —
    위젯 인스턴스 생성 비용이 행 수에 비례해 커져서, 20만 행이면 사실상 영원히
    끝나지 않는 수준이 된다. 두 가지로 해결한다.
      1) 체크박스를 별도 위젯이 아니라 QTableWidgetItem 자체의 체크 상태로 처리
         (위젯 인스턴스를 만들지 않아 훨씬 가볍다).
      2) 그래도 사람이 수만~수십만 행을 하나하나 스크롤하며 확인하는 건 애초에
         비현실적이므로, ROW_CAP을 넘는 대량 변경은 행 단위 표(table) 자체를
         만들지 않고 종류별 개수 요약 카드만 보여준다."""
    ROW_CAP = 3000

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.selected = []
        self.setWindowTitle(tr("sync.preview.title"))
        self.setStyleSheet(
            f"QDialog{{background-color:{C.WINDOW_BG};color:{C.WINDOW_FG};}}"
            f"QLabel{{color:{C.WINDOW_FG};}}"
            f"QTableWidget{{background-color:#ffffff;color:{C.WINDOW_FG};"
            f"gridline-color:{C.BORDER};}}"
            f"QHeaderView::section{{background-color:#e8ebef;color:{C.WINDOW_FG};"
            f"padding:4px;border:none;font-weight:bold;}}"
        )
        if len(actions) > self.ROW_CAP:
            self._build_summary_view()
        else:
            self._build_table_view()

    def _summarize(self):
        by_kind = Counter()
        for _, _, act in self.actions:
            kind, arg = act
            by_kind[_summarize_key(act)] += 1
        return by_kind

    def _build_summary_view(self):
        """[v20] 대량(ROW_CAP 초과) 변경 — 행 단위 표 대신 개수 요약만 보여줘서
        수십만 개 위젯을 만드는 일 자체를 하지 않는다(응답 없음 방지)."""
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("sync.preview.too_many", n=f"{len(self.actions):,}")))

        box = QGroupBox(tr("sync.preview.summary_box"))
        box_lay = QVBoxLayout(box)
        for label, count in self._summarize().items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            n = QLabel(tr("sync.preview.count_n", n=f"{count:,}"))
            n.setStyleSheet("font-weight:bold;")
            row.addWidget(n)
            box_lay.addLayout(row)
        lay.addWidget(box)

        warn = QLabel(tr("sync.preview.summary_warning"))
        warn.setStyleSheet(f"color:{C.RENAME_MAIN};")
        warn.setWordWrap(True)
        lay.addWidget(warn)
        lay.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("sync.preview.run_all_n", n=f"{len(self.actions):,}"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _build_table_view(self):
        actions = self.actions
        self.resize(720, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("sync.preview.checked_only_n", n=len(actions))))

        self.table = QTableWidget(len(actions), 4)
        self.table.setHorizontalHeaderLabels([tr("sync.preview.col_run"), tr("sync.preview.col_state"), tr("sync.preview.col_action"), tr("sync.preview.col_file")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)

        # [v20] setCellWidget(QCheckBox) 대신 항목 자체의 체크 상태를 쓴다 —
        # 위젯을 하나도 만들지 않으므로 수천 행에서도 즉시 채워진다.
        self.table.setUpdatesEnabled(False)
        for i, (rel, state, act) in enumerate(actions):
            it0 = QTableWidgetItem()
            it0.setFlags((it0.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            it0.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, it0)

            lbl, color = _state_label(state)
            it1 = QTableWidgetItem(lbl)
            it1.setForeground(QColor(color))
            self.table.setItem(i, 1, it1)

            self.table.setItem(i, 2, QTableWidgetItem(_act_label(act)))
            self.table.setItem(i, 3, QTableWidgetItem(rel))
        self.table.setUpdatesEnabled(True)
        lay.addWidget(self.table)

        row = QHBoxLayout()
        btn_all = QPushButton(tr("sync.preview.select_all"))
        btn_none = QPushButton(tr("sync.preview.select_none"))
        btn_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_none.clicked.connect(lambda: self._set_all_checked(False))
        for b in (btn_all, btn_none):
            b.setStyleSheet(
                "background-color:#78909c;color:#fff;padding:6px 12px;border-radius:4px;")
            row.addWidget(b)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("sync.preview.run_sync"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.table.setUpdatesEnabled(False)
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(state)
        self.table.setUpdatesEnabled(True)

    def accept(self):
        if hasattr(self, "table"):
            self.selected = [
                self.actions[i] for i in range(self.table.rowCount())
                if self.table.item(i, 0).checkState() == Qt.Checked
            ]
        else:
            self.selected = self.actions  # 요약 화면 — 전체 실행
        super().accept()


# =============================================================================
# 6.5 대기 상태 오버레이 — 스캔/동기화 진행 중 조작 차단 + 로그는 계속 노출
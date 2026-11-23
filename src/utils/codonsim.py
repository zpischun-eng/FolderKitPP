# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 코돈시뮬(CodonSim) [신규]

w(주어진 주형 가닥)에서 시작해 x → y → z로 이어지는 변이를 학생이 직접
만들어 보며 조건을 맞춰 가는 화면. 알고리즘·문제 데이터는 전부
codonsim_solve.py에 있고, 이 파일은 카드 배치·클릭 처리·다국어만
담당한다. 화면 구성은 사전에 HTML 목업으로 검토받은 것을 그대로 옮겼다
(w/x/y/z 4단 카드 + 오른쪽 조건 판정판/힌트/<보기> 패널).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QRegularExpressionValidator, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QScrollArea, QFrame
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import codonsim_solve as S

# ---------------------------------------------------------------- 서열 렌더링 색
_CODON_BG = ["#eef3ff", "#fdeef5"]      # codon.py와 같은 코돈 교대 배경(기존 계산기와 통일)
_CHANGED_BG = "#fff59d"
_CHANGED_BORDER = "#f9a825"
_MRNA_FG = "#3949ab"
_BASE_FONT = QFont("Consolas", 10)
_BASE_W, _BASE_H = 20, 22

_STAGES = ["x", "y", "z"]
_PARENT_OF = {"x": "w", "y": "x", "z": "y"}


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _row_container():
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(1)
    return w


def _render_base_row(container, seq, *, clickable=False, on_click=None,
                      selected_pos=None, changed_set=None, is_mrna=False):
    """서열 한 줄을 코돈(3글자) 단위로 묶어 그린다. clickable이면 각 칸이
    버튼이 되어 위치 클릭을 받는다(변이 조작용). changed_set에 든 인덱스는
    노란 배경으로 강조한다(변이로 바뀐/새로 생긴 자리)."""
    layout = container.layout()
    _clear_layout(layout)
    changed_set = changed_set or set()
    group_frame = None
    group_lay = None
    for i, ch in enumerate(seq):
        if i % 3 == 0:
            group_frame = QFrame()
            group_frame.setStyleSheet(
                f"background:{_CODON_BG[(i // 3) % 2]};border-radius:3px;")
            group_lay = QHBoxLayout(group_frame)
            group_lay.setContentsMargins(1, 1, 1, 1)
            group_lay.setSpacing(0)
            layout.addWidget(group_frame)

        is_changed = i in changed_set
        if clickable:
            btn = QPushButton(ch)
            btn.setFixedSize(_BASE_W, _BASE_H)
            btn.setFont(_BASE_FONT)
            btn.setCursor(Qt.PointingHandCursor)
            if i == selected_pos:
                btn.setStyleSheet(
                    f"background:{C.UTIL_MAIN};color:#fff;border:none;border-radius:3px;font-weight:bold;")
            else:
                btn.setStyleSheet("background:transparent;color:#333;border:none;border-radius:3px;")
            btn.clicked.connect(lambda _=False, idx=i: on_click(idx))
            group_lay.addWidget(btn)
        else:
            lbl = QLabel(ch)
            lbl.setFixedSize(_BASE_W, _BASE_H)
            lbl.setFont(_BASE_FONT)
            lbl.setAlignment(Qt.AlignCenter)
            color = _MRNA_FG if is_mrna else "#333333"
            if is_changed:
                lbl.setStyleSheet(
                    f"background:{_CHANGED_BG};border:1px solid {_CHANGED_BORDER};"
                    f"border-radius:3px;color:{color};font-weight:bold;")
            else:
                lbl.setStyleSheet(f"background:transparent;color:{color};")
            group_lay.addWidget(lbl)


def _render_amino_row(container, aminos, *, diff_from=None):
    """아미노산 3문자 약어를 칩으로 나열한다. diff_from(부모 단계의 아미노산
    목록)과 같은 자리 값이 다르면 빨간 테두리, 부모보다 자리가 늘었으면
    점선 테두리(프레임시프트로 새로 생긴 코돈)로 표시한다."""
    layout = container.layout()
    _clear_layout(layout)
    for i, a in enumerate(aminos):
        chip = QLabel(a)
        chip.setFont(QFont("Arial", 9))
        chip.setAlignment(Qt.AlignCenter)
        chip.setFixedHeight(20)
        chip.setMinimumWidth(38)
        chip.setContentsMargins(4, 0, 4, 0)
        if a == "Stop":
            style = "background:#4a1414;color:#ffcdd2;border-radius:4px;"
        else:
            style = "background:#eceff1;color:#37474f;border-radius:4px;"
        if diff_from is not None:
            if i >= len(diff_from):
                style += f"border:1px dashed {_CHANGED_BORDER};"
            elif diff_from[i] != a:
                style += f"border:1px solid {C.UTIL_MAIN};"
        chip.setStyleSheet(style)
        layout.addWidget(chip)
    layout.addStretch()


# =============================================================================
class CodonSimWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.problem = S.PROBLEMS[0]
        self.chain = S.ChainState(self.problem.w_seq)
        self._hint_shown = {"hint1": False, "hint2": False, "answer": False}

        self._build_ui()
        self.retranslate()

    # ------------------------------------------------------------------ UI 뼈대
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)

        # ---- 문제 선택은 w 카드의 툴바에, 직접 입력 줄은 w 카드 본문 맨 위에 ----
        self.lbl_problem = UK.body_label()
        self.combo_problem = QComboBox()
        for p in S.PROBLEMS:
            self.combo_problem.addItem(tr(f"util.codonsim.problem.{p.key}"), p.key)
        self.combo_problem.addItem(tr(f"util.codonsim.problem.{S.FREE_INPUT_KEY}"), S.FREE_INPUT_KEY)
        self.combo_problem.currentIndexChanged.connect(self._on_problem_combo_changed)

        self.lbl_free = UK.body_label()
        self.edit_free = QLineEdit()
        self.edit_free.setFont(QFont("Consolas", 12))
        self.edit_free.returnPressed.connect(self._on_free_apply)
        self.btn_free_apply = UK.primary_button()
        self.btn_free_apply.clicked.connect(self._on_free_apply)
        self.free_row = UK.hrow(self.lbl_free)
        self.free_row.addWidget(self.edit_free, 1)
        self.free_row.addWidget(self.btn_free_apply)
        self.lbl_free_error = UK.error_label()

        # ---- 본문: 좌(체인) + 우(판정판/힌트/보기) ----
        body = QHBoxLayout()
        body.setSpacing(UK.CARD_SPACING)
        root.addLayout(body, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        chain_holder = QWidget()
        chain_holder.setStyleSheet("background:transparent;")
        self.chain_lay = QVBoxLayout(chain_holder)
        self.chain_lay.setContentsMargins(0, 0, 0, 0)
        self.chain_lay.setSpacing(UK.CARD_SPACING)
        scroll.setWidget(chain_holder)
        body.addWidget(scroll, 1)

        self.stage_widgets = {}
        self.w_card = self._build_w_card()
        self.w_card.add_tool(self.lbl_problem)
        self.w_card.add_tool(self.combo_problem)
        self.w_card.body.insertLayout(0, self.free_row)
        self.w_card.body.insertWidget(1, self.lbl_free_error)
        self._set_free_row_visible(False)
        self.chain_lay.addWidget(self.w_card)
        for key in _STAGES:
            card = self._build_stage_card(key)
            self.chain_lay.addWidget(card)
        self.chain_lay.addStretch()

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setStyleSheet("background:transparent;")
        side_scroll.setFixedWidth(UK.RIGHT_PANEL_W)
        side_holder = QWidget()
        side_holder.setStyleSheet("background:transparent;")
        side_lay = QVBoxLayout(side_holder)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(UK.CARD_SPACING)
        side_lay.addWidget(self._build_condition_panel())
        side_lay.addWidget(self._build_hint_panel())
        side_lay.addWidget(self._build_bogi_panel())
        side_lay.addStretch()
        side_scroll.setWidget(side_holder)
        body.addWidget(side_scroll)

    def _set_free_row_visible(self, visible):
        self.lbl_free.setVisible(visible)
        self.edit_free.setVisible(visible)
        self.btn_free_apply.setVisible(visible)
        self.lbl_free_error.setVisible(visible)

    # ------------------------------------------------------------------ w 카드
    def _build_w_card(self):
        card = UK.Card()
        lay = card.body
        self.lbl_w_title = card.title_label

        self.w_dna = _row_container()
        self.w_mrna = _row_container()
        self.w_aa = _row_container()
        self.lbl_w_count = QLabel("")
        self.lbl_w_count.setStyleSheet("color:#5a6068;font-size:11px;background:transparent;")

        for label_key, container in (("dna", self.w_dna), ("mrna", self.w_mrna)):
            row = QHBoxLayout()
            lbl = QLabel()
            lbl.setFixedWidth(50)
            lbl.setStyleSheet("color:#5a6068;font-size:12px;background:transparent;")
            setattr(self, f"lbl_w_row_{label_key}", lbl)
            row.addWidget(lbl)
            row.addWidget(container)
            row.addStretch()
            lay.addLayout(row)

        aa_row = QHBoxLayout()
        self.lbl_w_row_aa = QLabel()
        self.lbl_w_row_aa.setFixedWidth(50)
        self.lbl_w_row_aa.setStyleSheet("color:#5a6068;font-size:12px;background:transparent;")
        aa_row.addWidget(self.lbl_w_row_aa)
        aa_row.addWidget(self.w_aa)
        aa_row.addWidget(self.lbl_w_count)
        lay.addLayout(aa_row)
        return card

    # ------------------------------------------------------------------ x/y/z 카드
    def _build_stage_card(self, key):
        card = UK.Card()
        lay = card.body
        sw = {}
        self.stage_widgets[key] = sw
        sw["card"] = card
        sw["title"] = card.title_label
        sw["badge"] = UK.hint_label()
        card.add_tool(sw["badge"])

        sw["placeholder"] = QLabel()
        sw["placeholder"].setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        sw["placeholder"].setWordWrap(True)
        lay.addWidget(sw["placeholder"])

        sw["body"] = QWidget()
        body_lay = QVBoxLayout(sw["body"])
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(6)
        lay.addWidget(sw["body"])

        # 변이 조작 줄
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        sw["lbl_type"] = QLabel()
        ctrl.addWidget(sw["lbl_type"])
        sw["combo_type"] = QComboBox()
        sw["combo_type"].addItem("", S.MTYPE_INSERT)
        sw["combo_type"].addItem("", S.MTYPE_DELETE)
        sw["combo_type"].addItem("", S.MTYPE_REPLACE)
        sw["combo_type"].currentIndexChanged.connect(lambda _=None, k=key: self._sync_ctrl_visibility(k))
        ctrl.addWidget(sw["combo_type"])

        sw["lbl_pos"] = QLabel()
        ctrl.addWidget(sw["lbl_pos"])
        sw["pos_display"] = QLabel()
        sw["pos_display"].setMinimumWidth(90)
        sw["pos_display"].setStyleSheet("font-size:12px;background:transparent;")
        ctrl.addWidget(sw["pos_display"])

        sw["lbl_len"] = QLabel()
        ctrl.addWidget(sw["lbl_len"])
        sw["len_field"] = QLineEdit("1")
        sw["len_field"].setFixedWidth(36)
        sw["len_field"].setValidator(QIntValidator(1, 99, self))
        sw["len_field"].setInputMethodHints(Qt.ImhDigitsOnly)
        ctrl.addWidget(sw["len_field"])

        sw["lbl_bases"] = QLabel()
        ctrl.addWidget(sw["lbl_bases"])
        sw["bases_field"] = QLineEdit()
        sw["bases_field"].setFixedWidth(70)
        sw["bases_field"].setValidator(QRegularExpressionValidator(r"[ATGCatgc]{0,10}", self))
        sw["bases_field"].textEdited.connect(
            lambda text, f=sw: f["bases_field"].setText(text.upper()))
        ctrl.addWidget(sw["bases_field"])
        ctrl.addStretch()
        body_lay.addLayout(ctrl)

        sw["btn_reset"] = card.add_footer(UK.secondary_button())
        sw["btn_reset"].clicked.connect(lambda _=False, k=key: self._on_reset(k))
        sw["btn_apply"] = card.add_footer(UK.primary_button())
        sw["btn_apply"].clicked.connect(lambda _=False, k=key: self._on_apply(k))

        sw["lbl_error"] = QLabel("")
        sw["lbl_error"].setStyleSheet("color:#c62828;font-size:11px;background:transparent;")
        sw["lbl_error"].setWordWrap(True)
        body_lay.addWidget(sw["lbl_error"])

        # 변경 전
        before_row = QHBoxLayout()
        sw["lbl_before"] = QLabel()
        sw["lbl_before"].setFixedWidth(58)
        sw["lbl_before"].setStyleSheet("color:#5a6068;font-size:12px;background:transparent;")
        before_row.addWidget(sw["lbl_before"])
        sw["before_container"] = _row_container()
        before_row.addWidget(sw["before_container"])
        before_row.addStretch()
        body_lay.addLayout(before_row)

        # 변경 후 (적용 전에는 안내 문구만)
        sw["after_placeholder"] = QLabel()
        sw["after_placeholder"].setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        body_lay.addWidget(sw["after_placeholder"])

        sw["after_body"] = QWidget()
        after_lay = QVBoxLayout(sw["after_body"])
        after_lay.setContentsMargins(0, 0, 0, 0)
        after_lay.setSpacing(4)

        for sub_key in ("after_dna", "after_mrna"):
            row = QHBoxLayout()
            lbl = QLabel()
            lbl.setFixedWidth(58)
            lbl.setStyleSheet("color:#5a6068;font-size:12px;background:transparent;")
            sw[f"lbl_{sub_key}"] = lbl
            row.addWidget(lbl)
            container = _row_container()
            sw[sub_key] = container
            row.addWidget(container)
            row.addStretch()
            after_lay.addLayout(row)

        aa_row = QHBoxLayout()
        sw["lbl_after_aa"] = QLabel()
        sw["lbl_after_aa"].setFixedWidth(58)
        sw["lbl_after_aa"].setStyleSheet("color:#5a6068;font-size:12px;background:transparent;")
        aa_row.addWidget(sw["lbl_after_aa"])
        sw["after_aa"] = _row_container()
        aa_row.addWidget(sw["after_aa"])
        sw["lbl_after_count"] = QLabel("")
        sw["lbl_after_count"].setStyleSheet("color:#5a6068;font-size:11px;background:transparent;")
        aa_row.addWidget(sw["lbl_after_count"])
        after_lay.addLayout(aa_row)

        body_lay.addWidget(sw["after_body"])
        return card

    # ------------------------------------------------------------------ 오른쪽: 조건 판정판
    def _build_condition_panel(self):
        panel = UK.Card()
        lay = panel.body
        self.lbl_cond_title = panel.title_label
        self.cond_list = QVBoxLayout()
        self.cond_list.setSpacing(6)
        lay.addLayout(self.cond_list)
        self.lbl_cond_empty = QLabel()
        self.lbl_cond_empty.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        self.lbl_cond_empty.setWordWrap(True)
        lay.addWidget(self.lbl_cond_empty)
        return panel

    # ------------------------------------------------------------------ 오른쪽: 힌트
    def _build_hint_panel(self):
        panel = UK.Card()
        lay = panel.body
        self.lbl_hint_title = panel.title_label

        self.btn_hint1 = UK.secondary_button()
        self.btn_hint1.clicked.connect(lambda: self._show_hint("hint1"))
        lay.addLayout(UK.hrow(self.btn_hint1, stretch_last=True))
        self.lbl_hint1 = QLabel("")
        self.lbl_hint1.setWordWrap(True)
        self.lbl_hint1.setStyleSheet(
            "font-size:12px;background:#fff;border:1px solid " + C.BORDER + ";border-radius:6px;padding:6px;")
        self.lbl_hint1.setVisible(False)
        lay.addWidget(self.lbl_hint1)

        self.btn_hint2 = UK.secondary_button()
        self.btn_hint2.clicked.connect(lambda: self._show_hint("hint2"))
        lay.addLayout(UK.hrow(self.btn_hint2, stretch_last=True))
        self.lbl_hint2 = QLabel("")
        self.lbl_hint2.setWordWrap(True)
        self.lbl_hint2.setStyleSheet(
            "font-size:12px;background:#fff;border:1px solid " + C.BORDER + ";border-radius:6px;padding:6px;")
        self.lbl_hint2.setVisible(False)
        lay.addWidget(self.lbl_hint2)

        self.btn_answer = UK.secondary_button()
        self.btn_answer.clicked.connect(self._show_answer)
        lay.addLayout(UK.hrow(self.btn_answer, stretch_last=True))
        self.lbl_answer = QLabel("")
        self.lbl_answer.setWordWrap(True)
        self.lbl_answer.setStyleSheet(
            "font-size:12px;background:#fff;border:1px solid " + C.BORDER + ";border-radius:6px;padding:6px;")
        self.lbl_answer.setVisible(False)
        lay.addWidget(self.lbl_answer)

        self.btn_autofill = UK.primary_button()
        self.btn_autofill.clicked.connect(self._on_autofill)
        self.btn_autofill.setVisible(False)
        lay.addLayout(UK.hrow(self.btn_autofill, stretch_last=True))

        self.lbl_hint_empty = QLabel()
        self.lbl_hint_empty.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        self.lbl_hint_empty.setWordWrap(True)
        lay.addWidget(self.lbl_hint_empty)
        return panel

    # ------------------------------------------------------------------ 오른쪽: <보기>
    def _build_bogi_panel(self):
        panel = UK.Card()
        lay = panel.body
        self.lbl_bogi_title = panel.title_label
        self.bogi_list = QVBoxLayout()
        self.bogi_list.setSpacing(8)
        lay.addLayout(self.bogi_list)
        self.lbl_bogi_empty = QLabel()
        self.lbl_bogi_empty.setStyleSheet("color:#8a8f98;font-size:12px;background:transparent;")
        self.lbl_bogi_empty.setWordWrap(True)
        lay.addWidget(self.lbl_bogi_empty)
        return panel

    # ==================================================================
    # 문제 전환
    # ==================================================================
    def _on_problem_combo_changed(self):
        key = self.combo_problem.currentData()
        if key == S.FREE_INPUT_KEY:
            self._set_free_row_visible(True)
            self.edit_free.setFocus()
        else:
            self._set_free_row_visible(False)
            problem = S.problem_by_key(key)
            self._load_problem(problem)

    def _on_free_apply(self):
        seq, errors = S.validate_free_sequence(self.edit_free.text())
        if errors:
            code, params = errors[0]
            self.lbl_free_error.setText(tr(f"util.codonsim.err.{code}", **params))
            return
        self.lbl_free_error.setText("")
        self._load_problem(S.make_free_problem(seq))

    def _load_problem(self, problem):
        self.problem = problem
        self.chain = S.ChainState(problem.w_seq)
        self._hint_shown = {"hint1": False, "hint2": False, "answer": False}
        self.retranslate()

    # ==================================================================
    # 변이 적용 / 초기화 / 클릭
    # ==================================================================
    def _sync_ctrl_visibility(self, key):
        sw = self.stage_widgets[key]
        mtype = sw["combo_type"].currentData()
        is_len = mtype in (S.MTYPE_DELETE, S.MTYPE_REPLACE)
        is_bases = mtype in (S.MTYPE_INSERT, S.MTYPE_REPLACE)
        sw["lbl_len"].setVisible(is_len)
        sw["len_field"].setVisible(is_len)
        sw["lbl_bases"].setVisible(is_bases)
        sw["bases_field"].setVisible(is_bases)

    def _on_base_click(self, key, idx):
        st = self.chain.stages[key]
        st.selected_pos = idx
        self._render_stage(key)

    def _on_apply(self, key):
        st = self.chain.stages[key]
        sw = self.stage_widgets[key]
        if st.selected_pos is None:
            sw["lbl_error"].setText(tr("util.codonsim.err.no_position"))
            return
        mtype = sw["combo_type"].currentData()
        bases = sw["bases_field"].text().strip().upper()
        try:
            length = int(sw["len_field"].text() or "1")
        except ValueError:
            length = 1
        mutation = S.Mutation(mtype, st.selected_pos, bases, length)
        errors = self.chain.apply(key, mutation)
        if errors:
            code, params = errors[0]
            sw["lbl_error"].setText(tr(f"util.codonsim.err.{code}", **params))
            return
        sw["lbl_error"].setText("")
        self._render_all()

    def _on_reset(self, key):
        self.chain.reset(key)
        self.stage_widgets[key]["lbl_error"].setText("")
        self._render_all()

    def _show_hint(self, hint_key):
        self._hint_shown[hint_key] = True
        self._render_hints()

    def _show_answer(self):
        self._hint_shown["answer"] = True
        self._render_hints()

    def _on_autofill(self):
        if not self.problem.answer:
            return
        for key in _STAGES:
            mutation = self.problem.answer.get(key)
            if mutation is None:
                continue
            self.chain.stages[key].selected_pos = mutation.pos
            errors = self.chain.apply(key, mutation)
            if errors:
                break
        self._render_all()

    # ==================================================================
    # 렌더링
    # ==================================================================
    def _render_all(self):
        self._render_w()
        for key in _STAGES:
            self._render_stage(key)
        self._render_conditions()
        self._render_hints()
        self._render_bogi()

    def _render_w(self):
        w = self.chain.w
        _render_base_row(self.w_dna, w.dna)
        _render_base_row(self.w_mrna, w.mrna, is_mrna=True)
        _render_amino_row(self.w_aa, w.aminos)
        self.lbl_w_count.setText(tr("util.codonsim.aa_count", a0=S.distinct_count(w.aminos)))

    def _render_stage(self, key):
        sw = self.stage_widgets[key]
        st = self.chain.stages[key]
        parent_key = _PARENT_OF[key]
        parent_seq = self.chain.parent_seq(key)
        parent_ready = parent_seq is not None

        sw["placeholder"].setVisible(not parent_ready)
        sw["badge"].setVisible(parent_ready)
        sw["btn_apply"].setVisible(parent_ready)
        sw["btn_reset"].setVisible(parent_ready)
        sw["body"].setVisible(parent_ready)
        if not parent_ready:
            sw["placeholder"].setText(
                tr("util.codonsim.stage.not_ready", a0=tr(f"util.codonsim.stage_name.{parent_key}")))
            return

        sw["badge"].setText(tr("util.codonsim.stage.applied") if st.applied else tr("util.codonsim.stage.unapplied"))

        _render_base_row(
            sw["before_container"], parent_seq, clickable=True,
            on_click=lambda idx, k=key: self._on_base_click(k, idx),
            selected_pos=st.selected_pos)

        sw["after_placeholder"].setVisible(not st.applied)
        sw["after_body"].setVisible(st.applied)
        if not st.applied:
            return

        changed = set()
        if st.mutation.type in (S.MTYPE_INSERT, S.MTYPE_REPLACE):
            changed = set(range(st.mutation.pos, st.mutation.pos + len(st.mutation.bases)))
        _render_base_row(sw["after_dna"], st.result.dna, changed_set=changed)
        _render_base_row(sw["after_mrna"], st.result.mrna, is_mrna=True)

        parent_result = self.chain.stage_result(parent_key)
        _render_amino_row(sw["after_aa"], st.result.aminos, diff_from=parent_result.aminos if parent_result else None)
        sw["lbl_after_count"].setText(tr("util.codonsim.aa_count", a0=S.distinct_count(st.result.aminos)))

    def _render_conditions(self):
        _clear_layout(self.cond_list)
        conditions = self.problem.conditions
        self.lbl_cond_empty.setVisible(not conditions)
        if not conditions:
            self.lbl_cond_empty.setText(tr("util.codonsim.cond.empty"))
            return
        for cond in conditions:
            value = S.evaluate_check(cond, self.chain)
            row = QHBoxLayout()
            dot = QFrame()
            dot.setFixedSize(10, 10)
            color = "#8a8f98" if value is None else ("#2e7d32" if value else "#c62828")
            dot.setStyleSheet(f"background:{color};border-radius:5px;")
            row.addWidget(dot, 0, Qt.AlignTop)
            row.setContentsMargins(0, 4, 0, 0)
            status = tr("util.codonsim.cond.pending") if value is None else (
                tr("util.codonsim.cond.met") if value else tr("util.codonsim.cond.unmet"))
            text_lbl = QLabel(tr(f"util.codonsim.cond.{self.problem.key}.{cond.key}") + f"\n{status}")
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("font-size:12px;background:transparent;")
            row.addWidget(text_lbl, 1)
            self.cond_list.addLayout(row)

    def _render_hints(self):
        has_hints = bool(self.problem.hint_keys)
        self.btn_hint1.setVisible(has_hints)
        self.btn_hint2.setVisible(has_hints and len(self.problem.hint_keys) > 1)
        self.btn_answer.setVisible(bool(self.problem.answer))
        self.lbl_hint_empty.setVisible(not has_hints and not self.problem.answer)

        self.lbl_hint1.setVisible(self._hint_shown["hint1"])
        if self._hint_shown["hint1"]:
            self.lbl_hint1.setText(tr(f"util.codonsim.hint.{self.problem.key}.hint1"))
        self.lbl_hint2.setVisible(self._hint_shown["hint2"])
        if self._hint_shown["hint2"]:
            self.lbl_hint2.setText(tr(f"util.codonsim.hint.{self.problem.key}.hint2"))

        self.lbl_answer.setVisible(self._hint_shown["answer"])
        self.btn_autofill.setVisible(self._hint_shown["answer"] and bool(self.problem.answer))
        if self._hint_shown["answer"] and self.problem.answer:
            lines = []
            for key in _STAGES:
                m = self.problem.answer.get(key)
                if m is None:
                    continue
                lines.append(tr(f"util.codonsim.answer_line.{m.type}",
                                 a0=key, a1=m.pos + 1, a2=m.bases, a3=m.length))
            self.lbl_answer.setText("\n".join(lines))

    def _render_bogi(self):
        _clear_layout(self.bogi_list)
        bogi = self.problem.bogi
        self.lbl_bogi_empty.setVisible(not bogi)
        if not bogi:
            self.lbl_bogi_empty.setText(tr("util.codonsim.bogi.empty"))
            return
        for item in bogi:
            box = QVBoxLayout()
            text_lbl = QLabel(tr(f"util.codonsim.bogi.{self.problem.key}.{item.key}"))
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("font-size:12px;background:transparent;")
            box.addWidget(text_lbl)

            btn_row = QHBoxLayout()
            btn_o = QPushButton("O")
            btn_x = QPushButton("X")
            for b in (btn_o, btn_x):
                b.setFixedWidth(36)
                b.setCursor(Qt.PointingHandCursor)
                b.setStyleSheet(UK.secondary_button().styleSheet())
            btn_row.addWidget(btn_o)
            btn_row.addWidget(btn_x)
            btn_row.addStretch()
            box.addLayout(btn_row)

            fb = QLabel("")
            fb.setWordWrap(True)
            fb.setStyleSheet("font-size:11px;color:#8a8f98;background:transparent;")
            box.addWidget(fb)

            def make_handler(choice, spec=item, label=fb):
                def handler():
                    v = S.evaluate_check(spec, self.chain)
                    if v is None:
                        label.setText(tr("util.codonsim.bogi.not_ready"))
                        label.setStyleSheet("font-size:11px;color:#8a8f98;background:transparent;")
                        return
                    correct = (choice == "O") == v
                    label.setText(tr("util.codonsim.bogi.correct") if correct else tr("util.codonsim.bogi.wrong"))
                    label.setStyleSheet(
                        "font-size:11px;background:transparent;color:" + ("#2e7d32" if correct else "#c62828"))
                return handler

            btn_o.clicked.connect(make_handler("O"))
            btn_x.clicked.connect(make_handler("X"))

            wrapper = QWidget()
            wrapper.setLayout(box)
            self.bogi_list.addWidget(wrapper)

    # ==================================================================
    # 다국어
    # ==================================================================
    def retranslate(self):
        self.lbl_problem.setText(tr("util.codonsim.lbl.problem"))
        for i, p in enumerate(S.PROBLEMS):
            self.combo_problem.setItemText(i, tr(f"util.codonsim.problem.{p.key}"))
        self.combo_problem.setItemText(len(S.PROBLEMS), tr(f"util.codonsim.problem.{S.FREE_INPUT_KEY}"))

        self.lbl_free.setText(tr("util.codonsim.lbl.free_seq"))
        self.edit_free.setPlaceholderText(tr("util.codonsim.placeholder.free_seq"))
        self.btn_free_apply.setText(tr("util.codonsim.btn.free_apply"))

        self.lbl_w_title.setText(tr("util.codonsim.stage_title.w"))
        self.lbl_w_row_dna.setText(tr("util.codonsim.row.dna"))
        self.lbl_w_row_mrna.setText(tr("util.codonsim.row.mrna"))
        self.lbl_w_row_aa.setText(tr("util.codonsim.row.aa"))

        for key in _STAGES:
            sw = self.stage_widgets[key]
            sw["title"].setText(
                tr(f"util.codonsim.stage_title.{key}", a0=tr(f"util.codonsim.stage_name.{_PARENT_OF[key]}")))
            sw["lbl_type"].setText(tr("util.codonsim.lbl.type"))
            sw["combo_type"].setItemText(0, tr("util.codonsim.mtype.insert"))
            sw["combo_type"].setItemText(1, tr("util.codonsim.mtype.delete"))
            sw["combo_type"].setItemText(2, tr("util.codonsim.mtype.replace"))
            sw["lbl_pos"].setText(tr("util.codonsim.lbl.pos"))
            sw["lbl_len"].setText(tr("util.codonsim.lbl.len"))
            sw["lbl_bases"].setText(tr("util.codonsim.lbl.bases"))
            sw["btn_apply"].setText(tr("util.codonsim.btn.apply"))
            sw["btn_reset"].setText(tr("util.codonsim.btn.reset"))
            sw["lbl_before"].setText(tr("util.codonsim.row.before"))
            sw["lbl_after_dna"].setText(tr("util.codonsim.row.after"))
            sw["lbl_after_mrna"].setText(tr("util.codonsim.row.mrna"))
            sw["lbl_after_aa"].setText(tr("util.codonsim.row.aa"))
            sw["after_placeholder"].setText(tr("util.codonsim.stage.apply_prompt"))
            st = self.chain.stages[key]
            pos = st.selected_pos
            sw["pos_display"].setText(
                tr("util.codonsim.pos.unset") if pos is None else tr("util.codonsim.pos.set", a0=pos + 1))

        self.lbl_cond_title.setText(tr("util.codonsim.lbl.conditions"))
        self.lbl_hint_title.setText(tr("util.codonsim.lbl.hints"))
        self.btn_hint1.setText(tr("util.codonsim.btn.hint1"))
        self.btn_hint2.setText(tr("util.codonsim.btn.hint2"))
        self.btn_answer.setText(tr("util.codonsim.btn.answer"))
        self.btn_autofill.setText(tr("util.codonsim.btn.autofill"))
        self.lbl_hint_empty.setText(tr("util.codonsim.hint.empty"))
        self.lbl_bogi_title.setText(tr("util.codonsim.lbl.bogi"))

        self._render_all()

    def has_unsaved(self):
        return False


# =============================================================================
class CodonSimApp(MiniApp):
    id = "codonsim"
    icon = "codonsim"
    category = "class"   # 학교(과학) — 기존 코돈표 계산기와 같은 자리

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = CodonSimWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


# =============================================================================
TRANSLATIONS = {
    "util.codonsim.title": {"ko": "코돈시뮬 (CodonSim)", "en": "CodonSim", "ja": "コドンシム（CodonSim）"},
    "util.codonsim.desc": {
        "ko": "w에서 시작해 x→y→z로 이어지는 변이를 직접 만들어 보며 조건을 맞추는 유전 문제 풀이 도구입니다.",
        "en": "Build a w→x→y→z mutation chain yourself and match the given conditions.",
        "ja": "wから始まりx→y→zと続く変異を自分で作りながら条件に合わせる問題演習ツールです。"},

    "util.codonsim.lbl.problem": {"ko": "문제", "en": "Problem", "ja": "問題"},
    "util.codonsim.problem.suneung2019_21": {
        "ko": "2019학년도 수능 생명과학Ⅰ 21번", "en": "2019 CSAT Biology I, Q21",
        "ja": "2019年度修能生命科学Ⅰ 21番"},
    "util.codonsim.problem.free_input": {"ko": "직접 입력", "en": "Custom sequence", "ja": "直接入力"},

    "util.codonsim.lbl.free_seq": {"ko": "주형 가닥(w)", "en": "Template strand (w)", "ja": "鋳型鎖（w）"},
    "util.codonsim.placeholder.free_seq": {
        "ko": "예: TTAGTTACGAGTGG (A/T/G/C만)", "en": "e.g. TTAGTTACGAGTGG (A/T/G/C only)",
        "ja": "例：TTAGTTACGAGTGG（A/T/G/Cのみ）"},
    "util.codonsim.btn.free_apply": {"ko": "이 서열로 시작", "en": "Start with this sequence", "ja": "この配列で開始"},

    "util.codonsim.stage_title.w": {"ko": "w — 주어진 유전자(주형 가닥)", "en": "w — given gene (template strand)",
                                     "ja": "w — 与えられた遺伝子（鋳型鎖）"},
    "util.codonsim.stage_title.x": {"ko": "x — {a0}에 변이 적용", "en": "x — mutate {a0}", "ja": "x — {a0}に変異を適用"},
    "util.codonsim.stage_title.y": {"ko": "y — {a0}에 변이 적용", "en": "y — mutate {a0}", "ja": "y — {a0}に変異を適用"},
    "util.codonsim.stage_title.z": {"ko": "z — {a0}에 변이 적용", "en": "z — mutate {a0}", "ja": "z — {a0}に変異を適用"},
    "util.codonsim.stage_name.w": {"ko": "w", "en": "w", "ja": "w"},
    "util.codonsim.stage_name.x": {"ko": "x", "en": "x", "ja": "x"},
    "util.codonsim.stage_name.y": {"ko": "y", "en": "y", "ja": "y"},
    "util.codonsim.stage.not_ready": {"ko": "먼저 {a0} 단계를 완성해야 이 단계를 만들 수 있어요.",
                                       "en": "Complete stage {a0} first to build this stage.",
                                       "ja": "まず{a0}段階を完成させる必要があります。"},
    "util.codonsim.stage.applied": {"ko": "적용됨", "en": "Applied", "ja": "適用済み"},
    "util.codonsim.stage.unapplied": {"ko": "미적용", "en": "Not applied", "ja": "未適用"},
    "util.codonsim.stage.apply_prompt": {"ko": "적용 버튼을 누르면 결과가 여기 나타납니다.",
                                          "en": "Press Apply to see the result here.",
                                          "ja": "適用ボタンを押すと結果がここに表示されます。"},

    "util.codonsim.row.dna": {"ko": "DNA", "en": "DNA", "ja": "DNA"},
    "util.codonsim.row.mrna": {"ko": "mRNA", "en": "mRNA", "ja": "mRNA"},
    "util.codonsim.row.aa": {"ko": "아미노산", "en": "Amino acids", "ja": "アミノ酸"},
    "util.codonsim.row.before": {"ko": "변경 전", "en": "Before", "ja": "変更前"},
    "util.codonsim.row.after": {"ko": "변경 후", "en": "After", "ja": "変更後"},
    "util.codonsim.aa_count": {"ko": "서로 다른 아미노산 {a0}개", "en": "{a0} distinct amino acids",
                                "ja": "異なるアミノ酸{a0}個"},

    "util.codonsim.lbl.type": {"ko": "종류", "en": "Type", "ja": "種類"},
    "util.codonsim.lbl.pos": {"ko": "위치", "en": "Position", "ja": "位置"},
    "util.codonsim.lbl.len": {"ko": "길이", "en": "Length", "ja": "長さ"},
    "util.codonsim.lbl.bases": {"ko": "염기", "en": "Bases", "ja": "塩基"},
    "util.codonsim.mtype.insert": {"ko": "삽입", "en": "Insert", "ja": "挿入"},
    "util.codonsim.mtype.delete": {"ko": "삭제", "en": "Delete", "ja": "削除"},
    "util.codonsim.mtype.replace": {"ko": "치환", "en": "Replace", "ja": "置換"},
    "util.codonsim.pos.unset": {"ko": "서열을 클릭하세요", "en": "Click a base below", "ja": "配列をクリックしてください"},
    "util.codonsim.pos.set": {"ko": "{a0}번째 염기 앞", "en": "before base {a0}", "ja": "{a0}番目の塩基の前"},
    "util.codonsim.btn.apply": {"ko": "적용", "en": "Apply", "ja": "適用"},
    "util.codonsim.btn.reset": {"ko": "초기화", "en": "Reset", "ja": "リセット"},

    "util.codonsim.err.no_position": {"ko": "먼저 서열에서 변이를 적용할 위치를 클릭하세요.",
                                       "en": "Click a position in the sequence first.",
                                       "ja": "まず配列から変異を適用する位置をクリックしてください。"},
    "util.codonsim.err.bases_invalid": {"ko": "삽입/치환할 염기를 입력하세요 (A/T/G/C).",
                                         "en": "Enter bases to insert/replace (A/T/G/C).",
                                         "ja": "挿入・置換する塩基を入力してください（A/T/G/C）。"},
    "util.codonsim.err.length_invalid": {"ko": "길이는 1 이상이어야 합니다.", "en": "Length must be at least 1.",
                                          "ja": "長さは1以上である必要があります。"},
    "util.codonsim.err.range_invalid": {"ko": "지정한 길이가 서열 범위를 벗어납니다.",
                                         "en": "The length goes past the end of the sequence.",
                                         "ja": "指定した長さが配列の範囲を超えています。"},
    "util.codonsim.err.pos_out_of_range": {"ko": "위치가 서열 범위를 벗어납니다.",
                                            "en": "Position is out of range.", "ja": "位置が配列の範囲外です。"},
    "util.codonsim.err.seq_too_short": {"ko": "서열은 최소 {a0}자 이상 입력하세요.",
                                         "en": "Enter at least {a0} bases.", "ja": "配列は最低{a0}文字以上入力してください。"},
    "util.codonsim.err.seq_too_long": {"ko": "서열은 최대 {a0}자까지 입력할 수 있습니다.",
                                        "en": "Enter at most {a0} bases.", "ja": "配列は最大{a0}文字まで入力できます。"},
    "util.codonsim.err.seq_invalid_char": {"ko": "A/T/G/C만 입력할 수 있습니다.",
                                            "en": "Only A/T/G/C are allowed.", "ja": "A/T/G/Cのみ入力できます。"},

    "util.codonsim.lbl.conditions": {"ko": "조건 판정판", "en": "Conditions", "ja": "条件判定"},
    "util.codonsim.cond.empty": {"ko": "이 문제에는 별도 조건이 없습니다. 자유롭게 변이를 만들어 보세요.",
                                  "en": "This mode has no conditions — explore freely.",
                                  "ja": "この問題には条件がありません。自由に変異を試してみてください。"},
    "util.codonsim.cond.pending": {"ko": "미적용", "en": "Not yet", "ja": "未適用"},
    "util.codonsim.cond.met": {"ko": "충족", "en": "Met", "ja": "充足"},
    "util.codonsim.cond.unmet": {"ko": "미충족", "en": "Not met", "ja": "未充足"},
    "util.codonsim.cond.suneung2019_21.x8": {"ko": "x는 서로 다른 아미노산 8개로 구성",
                                              "en": "x has 8 distinct amino acids",
                                              "ja": "xは異なるアミノ酸8個で構成"},
    "util.codonsim.cond.suneung2019_21.xg": {"ko": "x는 구아닌(G)만 삽입되어 만들어짐",
                                              "en": "x is made by inserting only guanine (G)",
                                              "ja": "xはグアニン（G）のみの挿入で作られる"},
    "util.codonsim.cond.suneung2019_21.y7": {"ko": "y는 서로 다른 아미노산 7개로 구성",
                                              "en": "y has 7 distinct amino acids",
                                              "ja": "yは異なるアミノ酸7個で構成"},
    "util.codonsim.cond.suneung2019_21.zy": {"ko": "z는 y와 아미노산 서열이 동일",
                                              "en": "z has the same amino acid sequence as y",
                                              "ja": "zはyとアミノ酸配列が同一"},

    "util.codonsim.lbl.hints": {"ko": "힌트", "en": "Hints", "ja": "ヒント"},
    "util.codonsim.btn.hint1": {"ko": "힌트 1단계 보기", "en": "Show hint 1", "ja": "ヒント1を見る"},
    "util.codonsim.btn.hint2": {"ko": "힌트 2단계 보기", "en": "Show hint 2", "ja": "ヒント2を見る"},
    "util.codonsim.btn.answer": {"ko": "정답 보기", "en": "Show answer", "ja": "正解を見る"},
    "util.codonsim.btn.autofill": {"ko": "이 값으로 자동 채우기", "en": "Fill in this answer", "ja": "この値で自動入力"},
    "util.codonsim.hint.empty": {"ko": "이 문제에는 힌트/정답이 없습니다.", "en": "No hints or answer for this mode.",
                                  "ja": "この問題にはヒント・正解がありません。"},
    "util.codonsim.hint.suneung2019_21.hint1": {
        "ko": "힌트 1단계 — x는 '삽입' 변이로 만들어집니다.",
        "en": "Hint 1 — x is created by an 'insert' mutation.",
        "ja": "ヒント1 — xは「挿入」変異で作られます。"},
    "util.codonsim.hint.suneung2019_21.hint2": {
        "ko": "힌트 2단계 — 삽입 위치는 서열의 6~9번째 부근이고, 삽입되는 염기는 구아닌(G) 1~2개입니다.",
        "en": "Hint 2 — the insertion is around position 6-9, using 1-2 guanine (G) bases.",
        "ja": "ヒント2 — 挿入位置は配列の6〜9番目付近で、挿入される塩基はグアニン（G）1〜2個です。"},

    "util.codonsim.answer_line.insert": {"ko": "{a0} : {a1}번째 염기 앞에 \"{a2}\" 삽입",
                                          "en": "{a0}: insert \"{a2}\" before base {a1}",
                                          "ja": "{a0}：{a1}番目の塩基の前に「{a2}」を挿入"},
    "util.codonsim.answer_line.delete": {"ko": "{a0} : {a1}번째 염기부터 {a3}개 삭제",
                                          "en": "{a0}: delete {a3} bases from position {a1}",
                                          "ja": "{a0}：{a1}番目の塩基から{a3}個削除"},
    "util.codonsim.answer_line.replace": {"ko": "{a0} : {a1}번째 염기부터 {a3}개를 \"{a2}\"(으)로 치환",
                                           "en": "{a0}: replace {a3} base(s) from position {a1} with \"{a2}\"",
                                           "ja": "{a0}：{a1}番目の塩基から{a3}個を「{a2}」に置換"},

    "util.codonsim.lbl.bogi": {"ko": "<보기>", "en": "<Statements>", "ja": "<選択肢>"},
    "util.codonsim.bogi.empty": {"ko": "이 문제에는 <보기>가 없습니다.", "en": "No statements for this mode.",
                                  "ja": "この問題には選択肢がありません。"},
    "util.codonsim.bogi.not_ready": {"ko": "아직 판단할 수 없어요 — 관련 단계를 먼저 만들어 보세요.",
                                      "en": "Not enough info yet — build the related stage first.",
                                      "ja": "まだ判断できません — 関連する段階を先に作ってください。"},
    "util.codonsim.bogi.correct": {"ko": "✓ 맞았습니다.", "en": "✓ Correct.", "ja": "✓ 正解です。"},
    "util.codonsim.bogi.wrong": {"ko": "✗ 다시 생각해 보세요.", "en": "✗ Try again.", "ja": "✗ もう一度考えてみましょう。"},
    "util.codonsim.bogi.suneung2019_21.g": {"ko": "ㄱ. x는 8종류의 서로 다른 아미노산으로 구성된다.",
                                             "en": "(a) x consists of 8 distinct kinds of amino acids.",
                                             "ja": "ㄱ．xは8種類の異なるアミノ酸で構成される。"},
    "util.codonsim.bogi.suneung2019_21.n": {"ko": "ㄴ. y와 z의 아미노산 서열은 서로 같다.",
                                             "en": "(b) y and z have the same amino acid sequence.",
                                             "ja": "ㄴ．yとzのアミノ酸配列は互いに同じである。"},
    "util.codonsim.bogi.suneung2019_21.d": {"ko": "ㄷ. x를 만들 때 삽입된 염기는 사이토신(C)이다.",
                                             "en": "(c) The base inserted to make x is cytosine (C).",
                                             "ja": "ㄷ．xを作るとき挿入された塩基はシトシン（C）である。"},
}
CodonSimApp.tr_table = TRANSLATIONS

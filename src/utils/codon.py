# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 코돈표 계산기 [신규]

DNA(주형 가닥) 또는 mRNA 서열을 입력하면 표준 유전암호표로 아미노산
서열을 바로 찾아 준다. 반대로 아미노산을 고르면 그 아미노산을 지정하는
코돈을 전부 보여준다(역조회). 전체 64개 코돈표도 참고용으로 늘 볼 수
있다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QComboBox, QTextEdit, QScrollArea, QFrame, QToolButton,
    QRadioButton, QButtonGroup
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import codon_solve as CD

_MODE_MRNA = "mrna"
_MODE_DNA = "dna"

_BASE_ORDER = ["U", "C", "A", "G"]   # 표준 코돈표 배열 순서(첫 글자 기준)


def _html_escape(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class CodonWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.mode = _MODE_MRNA
        self._build_ui()
        self.retranslate()

    def _build_ui(self):
        # ---- 왼쪽 위 카드: 서열 입력(툴바: mRNA/DNA 토글, 하단: 번역) ----
        self.card_input = UK.Card()
        self.btn_mrna = UK.toggle_button()
        self.btn_mrna.clicked.connect(lambda: self._set_mode(_MODE_MRNA))
        self.card_input.add_tool(self.btn_mrna)
        self.btn_dna = UK.toggle_button()
        self.btn_dna.clicked.connect(lambda: self._set_mode(_MODE_DNA))
        self.card_input.add_tool(self.btn_dna)

        self.lbl_seq = UK.body_label()
        self.card_input.add_body(self.lbl_seq)
        self.edit_seq = QLineEdit()
        self.edit_seq.setFont(QFont("Consolas", 13))
        self.edit_seq.returnPressed.connect(self._translate)
        self.card_input.add_body(self.edit_seq)

        # [신규] DNA 모드에서만 보이는 "이 서열이 어느 가닥인지" 선택
        self.lbl_strand_type = UK.body_label()
        self.radio_template = QRadioButton()
        self.radio_template.setChecked(True)
        self.radio_coding = QRadioButton()
        self.strand_group = QButtonGroup(self)
        self.strand_group.addButton(self.radio_template, 0)
        self.strand_group.addButton(self.radio_coding, 1)
        self.strand_row = UK.hrow(self.lbl_strand_type, self.radio_template, self.radio_coding, stretch_last=True)
        self.card_input.add_body(self.strand_row)

        self.chk_first_aug = QCheckBox()
        self.chk_first_aug.setChecked(True)
        self.card_input.add_body(UK.hrow(self.chk_first_aug, stretch_last=True))

        self.card_input.body.addStretch()
        self.lbl_error = UK.error_label()
        self.lbl_error.setVisible(False)
        self.card_input.add_footer_left(self.lbl_error)
        self.btn_translate = self.card_input.add_footer(UK.primary_button())
        self.btn_translate.clicked.connect(self._translate)

        # ---- 왼쪽 아래 카드: 번역 결과 ----
        self.card_result = UK.Card()
        self.lbl_mrna_shown = UK.hint_label()
        self.card_result.add_body(self.lbl_mrna_shown)
        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setMaximumHeight(150)
        self.result_view.setFrameShape(QFrame.NoFrame)
        self.card_result.add_body(UK.canvas_frame(self.result_view, margin=4), 1)

        # ---- 오른쪽 카드: 코돈 조회(역조회 + 전체 코돈표) ----
        self.card_lookup = UK.Card()
        self.lbl_lookup = UK.body_label()
        self.combo_amino = QComboBox()
        for code in CD.AMINO_ORDER:
            self.combo_amino.addItem("", code)
        self.combo_amino.currentIndexChanged.connect(self._update_lookup)
        self.card_lookup.add_body(UK.hrow(self.lbl_lookup, self.combo_amino, stretch_last=True))
        self.lbl_lookup_result = QLabel()
        self.lbl_lookup_result.setWordWrap(True)
        self.lbl_lookup_result.setStyleSheet(f"color:{C.UTIL_MAIN};font-weight:bold;background:transparent;")
        self.card_lookup.add_body(self.lbl_lookup_result)

        self.toggle_table = QToolButton()
        self.toggle_table.setCheckable(True)
        self.toggle_table.setArrowType(Qt.RightArrow)
        self.toggle_table.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_table.setStyleSheet("QToolButton{background:transparent;border:none;font-size:12px;}")
        self.toggle_table.clicked.connect(self._on_toggle_table)
        self.card_lookup.add_body(self.toggle_table)

        self.table_scroll = QScrollArea()
        self.table_scroll.setWidgetResizable(True)
        self.table_scroll.setVisible(False)
        self.table_scroll.setFrameShape(QFrame.NoFrame)
        self.table_view = QTextEdit()
        self.table_view.setReadOnly(True)
        self.table_view.setHtml(self._full_table_html())
        self.table_scroll.setWidget(self.table_view)
        self.card_lookup.add_body(self.table_scroll, 1)
        self.card_lookup.body.addStretch(0)

        left = UK.vstack(self.card_input, self.card_result)
        left.setStretch(1, 1)
        UK.split_lr(self, left, self.card_lookup)

        self._update_mode_buttons()
        self._update_strand_row_visibility()
        self._update_lookup()

    # ---------------------------------------------------------------- 모드
    def _set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        self._update_mode_buttons()
        self._update_strand_row_visibility()
        self.retranslate()

    def _update_strand_row_visibility(self):
        is_dna = (self.mode == _MODE_DNA)
        self.lbl_strand_type.setVisible(is_dna)
        self.radio_template.setVisible(is_dna)
        self.radio_coding.setVisible(is_dna)
        # DNA 모드는 5단계 과정을 전부 보여줘야 해서 결과 영역이 훨씬
        # 크다 — mRNA 모드는 코돈표 한 줄짜리라 짧아도 충분하다.
        self.result_view.setMaximumHeight(16777215 if is_dna else 150)
        self.result_view.setMinimumHeight(320 if is_dna else 0)

    def _update_mode_buttons(self):
        self.btn_mrna.setChecked(self.mode == _MODE_MRNA)
        self.btn_dna.setChecked(self.mode == _MODE_DNA)

    def _on_toggle_table(self):
        show = self.toggle_table.isChecked()
        self.table_scroll.setVisible(show)
        self.toggle_table.setArrowType(Qt.DownArrow if show else Qt.RightArrow)

    # ---------------------------------------------------------------- 계산
    def _translate(self):
        raw = self.edit_seq.text().strip()
        if not raw:
            return
        try:
            if self.mode == _MODE_DNA:
                strand_type = CD.STRAND_TEMPLATE if self.radio_template.isChecked() else CD.STRAND_CODING
                proc = CD.process_dna(raw, strand_type=strand_type,
                                      start_at_first_aug=self.chk_first_aug.isChecked())
            else:
                mrna = raw.upper().replace(" ", "").replace("T", "U")
                result = CD.translate(mrna, start_at_first_aug=self.chk_first_aug.isChecked())
        except CD.SequenceError as e:
            base_kind = tr("util.codon.base_dna") if self.mode == _MODE_DNA else tr("util.codon.base_mrna")
            self.lbl_error.setText(tr("util.codon.error_bad_char", a0=str(e), a1=base_kind))
            self.lbl_error.setVisible(True)
            self.result_view.setHtml("")
            return

        self.lbl_error.setVisible(False)
        self.lbl_mrna_shown.setVisible(False)   # [신규] DNA 단계별 화면 자체에 mRNA가 나오니 예전의 별도 요약 줄은 필요 없다

        if self.mode == _MODE_DNA:
            self.result_view.setHtml(self._dna_process_html(proc))
            if self.host:
                if proc.translation.codons:
                    self.host.log(tr("util.codon.log.translated", a0=len(proc.translation.aminos)))
                else:
                    self.host.log(tr("util.codon.log.no_aug"))
            return

        if not result.codons:
            self.result_view.setHtml(f'<p style="color:#8a8f98;">{_html_escape(tr("util.codon.no_aug"))}</p>')
            if self.host:
                self.host.log(tr("util.codon.log.no_aug"))
            return
        self.result_view.setHtml(self._translation_table_html(result))
        if self.host:
            self.host.log(tr("util.codon.log.translated", a0=len(result.aminos)))

    def _translation_table_html(self, result):
        """mRNA 모드(전사 단계 없이 바로 번역)에서 쓰는, 코돈→아미노산
        표 하나만 보여주는 간단한 결과."""
        rows = []
        for codon, amino in zip(result.codons, result.aminos):
            ko = CD.AMINO_KO.get(amino, amino)
            color = C.UTIL_MAIN if amino == "Stop" else C.WINDOW_FG
            rows.append(
                f'<tr><td style="padding:2px 8px;font-family:Consolas;color:#6b7280;">{codon}</td>'
                f'<td style="padding:2px 8px;color:{color};font-weight:{"bold" if amino=="Stop" else "normal"};">'
                f'{_html_escape(ko)}</td></tr>')
        seq_names = " – ".join(CD.AMINO_KO.get(a, a) for a in result.aminos)
        html = (
            f'<table>{"".join(rows)}</table>'
            f'<p style="margin-top:8px;"><b>{_html_escape(tr("util.codon.sequence_label"))}</b> {_html_escape(seq_names)}</p>'
        )
        if not result.stopped:
            html += f'<p style="color:#8a8f98;font-size:11px;">{_html_escape(tr("util.codon.no_stop_note"))}</p>'
        return html

    # ---------------------------------------------------------------- [신규] DNA 단계별 화면
    @staticmethod
    def _base_span(ch, color="#333333", bg=None, bold=False):
        style = (f"display:inline-block;width:22px;text-align:center;font-family:Consolas;"
                f"font-size:15px;color:{color};" + ("font-weight:bold;" if bold else "")
                + (f"background:{bg};border-radius:3px;" if bg else ""))
        return f'<span style="{style}">{_html_escape(ch)}</span>'

    def _strand_row_html(self, seq, color="#333333"):
        return "".join(self._base_span(ch, color=color) for ch in seq)

    def _connector_row_html(self, n):
        return "".join(self._base_span("|", color="#c6c9ce") for _ in range(n))

    def _codon_grouped_html(self, mrna):
        """mRNA를 3글자씩 번갈아 배경색을 입혀 코돈 단위가 눈에 보이게
        한다(4단계: 코돈으로 묶기)."""
        colors = ["#eef3ff", "#fdeef5"]
        spans = []
        for i, ch in enumerate(mrna):
            bg = colors[(i // 3) % 2]
            spans.append(self._base_span(ch, color="#333333", bg=bg))
        return "".join(spans)

    def _step_block(self, number, title, body_html, note_html=""):
        return (
            f'<div style="margin-bottom:14px;">'
            f'<div style="color:{C.UTIL_MAIN};font-weight:bold;margin-bottom:4px;">'
            f'{tr("util.codon.step_label", a0=number)} {_html_escape(title)}</div>'
            f'<div>{body_html}</div>'
            + (f'<div style="color:#8a8f98;font-size:11px;margin-top:3px;">{note_html}</div>' if note_html else "")
            + '</div>'
        )

    def _dna_process_html(self, proc: CD.DnaProcess):
        """DNA 한 가닥 입력 → 나머지 가닥 → mRNA 합성(전사) → 코돈 분할
        → 아미노산 번역까지, 교과서 순서 그대로 5단계로 보여준다."""
        is_template_input = (proc.strand_type == CD.STRAND_TEMPLATE)
        input_label = tr("util.codon.strand.template") if is_template_input else tr("util.codon.strand.coding")
        other_label = tr("util.codon.strand.coding") if is_template_input else tr("util.codon.strand.template")
        input_seq = proc.input_seq
        other_seq = proc.coding_strand if is_template_input else proc.template_strand
        input_dir = "3' → 5'" if is_template_input else "5' → 3'"
        other_dir = "5' → 3'" if is_template_input else "3' → 5'"

        step1 = self._step_block(
            1, tr("util.codon.step1.title", a0=input_label),
            f'<div style="color:#6b7280;font-size:11px;margin-bottom:2px;">{input_dir}</div>'
            f'<div>{self._strand_row_html(input_seq, color=C.UTIL_MAIN)}</div>')

        step2 = self._step_block(
            2, tr("util.codon.step2.title", a0=other_label),
            f'<div style="color:#6b7280;font-size:11px;">{input_dir}</div>'
            f'<div>{self._strand_row_html(input_seq)}</div>'
            f'<div>{self._connector_row_html(len(input_seq))}</div>'
            f'<div>{self._strand_row_html(other_seq, color="#3949ab")}</div>'
            f'<div style="color:#6b7280;font-size:11px;">{other_dir}</div>',
            note_html=tr("util.codon.step2.note"))

        step3 = self._step_block(
            3, tr("util.codon.step3.title"),
            f'<div style="color:#6b7280;font-size:11px;">{tr("util.codon.step3.coding_label")} (5\' → 3\')</div>'
            f'<div>{self._strand_row_html(proc.coding_strand, color="#3949ab")}</div>'
            f'<div style="height:4px;"></div>'
            f'<div style="color:#6b7280;font-size:11px;">mRNA (5\' → 3\')</div>'
            f'<div>{self._strand_row_html(proc.mrna, color="#c2185b")}</div>',
            note_html=tr("util.codon.step3.note"))

        step4 = self._step_block(
            4, tr("util.codon.step4.title"),
            f'<div>{self._codon_grouped_html(proc.mrna)}</div>',
            note_html=tr("util.codon.step4.note", a0=len(proc.codons)))

        tr_result = proc.translation
        if not tr_result.codons:
            step5_body = f'<p style="color:#8a8f98;">{_html_escape(tr("util.codon.no_aug"))}</p>'
        else:
            step5_body = self._translation_table_html(tr_result)
        step5 = self._step_block(5, tr("util.codon.step5.title"), step5_body)

        return step1 + step2 + step3 + step4 + step5

    def _update_lookup(self):
        code = self.combo_amino.currentData()
        if not code:
            return
        codons = CD.codons_for(code)
        self.lbl_lookup_result.setText(
            tr("util.codon.lookup_result", a0=CD.AMINO_KO.get(code, code), a1=", ".join(codons), a2=len(codons)))

    def _full_table_html(self):
        cells = []
        for b1 in _BASE_ORDER:
            for b2 in _BASE_ORDER:
                row_cells = []
                for b3 in _BASE_ORDER:
                    codon = b1 + b2 + b3
                    amino = CD.CODON_TABLE[codon]
                    ko = CD.AMINO_KO.get(amino, amino)
                    color = C.UTIL_MAIN if amino == "Stop" else "#444"
                    row_cells.append(
                        f'<td style="border:1px solid {C.BORDER};padding:3px 6px;">'
                        f'<span style="font-family:Consolas;color:#6b7280;">{codon}</span> '
                        f'<span style="color:{color};">{_html_escape(ko)}</span></td>')
                cells.append(f"<tr>{''.join(row_cells)}</tr>")
        return f'<table style="border-collapse:collapse;font-size:12px;">{"".join(cells)}</table>'

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.card_input.set_title(tr("util.codon.card.input"))
        self.card_result.set_title(tr("util.codon.card.result"))
        self.card_lookup.set_title(tr("util.codon.card.lookup"))
        self.btn_mrna.setText(tr("util.codon.mode.mrna"))
        self.btn_dna.setText(tr("util.codon.mode.dna"))
        self.lbl_seq.setText(tr("util.codon.lbl.mrna") if self.mode == _MODE_MRNA else tr("util.codon.lbl.dna"))
        self.edit_seq.setPlaceholderText(
            tr("util.codon.placeholder.mrna") if self.mode == _MODE_MRNA else tr("util.codon.placeholder.dna"))
        self.chk_first_aug.setText(tr("util.codon.chk.first_aug"))
        self.btn_translate.setText(tr("util.codon.btn.translate"))
        self.lbl_strand_type.setText(tr("util.codon.lbl.strand_type"))
        self.radio_template.setText(tr("util.codon.strand.template"))
        self.radio_coding.setText(tr("util.codon.strand.coding"))
        self.lbl_lookup.setText(tr("util.codon.lbl.lookup"))
        for i, code in enumerate(CD.AMINO_ORDER):
            self.combo_amino.setItemText(i, CD.AMINO_KO.get(code, code))
        self.toggle_table.setText(tr("util.codon.toggle_table"))
        self._update_lookup()
        self.table_view.setHtml(self._full_table_html())


class CodonApp(MiniApp):
    id = "codon"
    icon = "codon"
    category = "class"   # 학교(과학) — 별도 과학 카테고리 신설 전까지는 학교 아래 둔다

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = CodonWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.codon.title": {"ko": "코돈표 계산기", "en": "Codon Table Calculator", "ja": "コドン表計算機"},
    "util.codon.card.input": {"ko": "서열 입력", "en": "Sequence", "ja": "配列入力"},
    "util.codon.card.result": {"ko": "번역 결과", "en": "Translation", "ja": "翻訳結果"},
    "util.codon.card.lookup": {"ko": "코돈 조회", "en": "Codon lookup", "ja": "コドン検索"},
    "util.codon.desc": {
        "ko": "DNA·mRNA 서열을 아미노산 서열로 번역하고, 코돈표를 조회합니다.",
        "en": "Translates DNA/mRNA sequences into amino acids and looks up the codon table.",
        "ja": "DNA・mRNA配列をアミノ酸配列に翻訳し、コドン表を検索します。"},
    "util.codon.mode.mrna": {"ko": "mRNA 입력", "en": "mRNA input", "ja": "mRNA入力"},
    "util.codon.mode.dna": {"ko": "DNA 입력", "en": "DNA input", "ja": "DNA入力"},
    "util.codon.lbl.mrna": {"ko": "mRNA 서열(5'→3')", "en": "mRNA sequence (5'→3')", "ja": "mRNA配列（5'→3'）"},
    "util.codon.lbl.dna": {"ko": "DNA 서열", "en": "DNA sequence", "ja": "DNA配列"},
    "util.codon.placeholder.mrna": {"ko": "예) AUGUCUUGUUUUUAA", "en": "e.g. AUGUCUUGUUUUUAA", "ja": "例）AUGUCUUGUUUUUAA"},
    "util.codon.placeholder.dna": {"ko": "예) TACAGAACAAAATT", "en": "e.g. TACAGAACAAAATT", "ja": "例）TACAGAACAAAATT"},
    "util.codon.lbl.strand_type": {"ko": "이 서열은:", "en": "This sequence is:", "ja": "この配列は："},
    "util.codon.strand.template": {"ko": "주형 가닥(3'→5')", "en": "Template strand (3'→5')", "ja": "鋳型鎖（3'→5'）"},
    "util.codon.strand.coding": {"ko": "암호화 가닥(5'→3')", "en": "Coding strand (5'→3')", "ja": "コード鎖（5'→3'）"},
    "util.codon.step_label": {"ko": "{a0}단계", "en": "Step {a0}", "ja": "ステップ{a0}"},
    "util.codon.step1.title": {"ko": "입력한 DNA — {a0}", "en": "Input DNA — {a0}", "ja": "入力したDNA — {a0}"},
    "util.codon.step2.title": {"ko": "상보적 결합으로 나머지 가닥 찾기 — {a0}",
                               "en": "Find the complementary strand — {a0}", "ja": "相補的結合で残りの鎖を求める — {a0}"},
    "util.codon.step2.note": {
        "ko": "A는 T와, G는 C와 짝을 이룹니다(상보적 결합). 두 가닥은 서로 반대 방향(3'↔5')입니다.",
        "en": "A pairs with T, G pairs with C (complementary base pairing). The two strands run in opposite directions.",
        "ja": "AはTと、GはCと対になります（相補的結合）。二本の鎖は互いに逆方向（3'↔5'）です。"},
    "util.codon.step3.title": {"ko": "mRNA 합성(전사)", "en": "mRNA synthesis (transcription)", "ja": "mRNA合成（転写）"},
    "util.codon.step3.coding_label": {"ko": "암호화 가닥", "en": "Coding strand", "ja": "コード鎖"},
    "util.codon.step3.note": {
        "ko": "mRNA는 암호화 가닥과 서열이 같고, T만 U로 바뀝니다(RNA 중합효소가 주형 가닥을 상보적으로 복사하기 때문입니다).",
        "en": "mRNA has the same sequence as the coding strand, with T replaced by U (RNA polymerase copies the template strand complementarily).",
        "ja": "mRNAはコード鎖と同じ配列で、TがUに変わるだけです（RNAポリメラーゼが鋳型鎖を相補的に複写するため）。"},
    "util.codon.step4.title": {"ko": "코돈으로 3개씩 묶기", "en": "Group into codons of 3", "ja": "3つずつコドンにまとめる"},
    "util.codon.step4.note": {
        "ko": "코돈 {a0}개로 나뉩니다(색이 번갈아 바뀌는 부분이 코돈 하나).",
        "en": "Split into {a0} codons (each alternating color block is one codon).",
        "ja": "コドン{a0}個に分かれます（色が交互に変わる部分が1つのコドンです）。"},
    "util.codon.step5.title": {"ko": "코돈표로 아미노산 번역", "en": "Translate to amino acids", "ja": "コドン表でアミノ酸に翻訳"},
    "util.codon.chk.first_aug": {
        "ko": "첫 AUG부터 시작", "en": "Start from first AUG", "ja": "最初のAUGから開始"},
    "util.codon.btn.translate": {"ko": "번역하기", "en": "Translate", "ja": "翻訳する"},
    "util.codon.error_bad_char": {
        "ko": "'{a0}'는 올바른 {a1} 염기가 아닙니다.",
        "en": "'{a0}' is not a valid {a1} base.", "ja": "「{a0}」は正しい{a1}塩基ではありません。"},
    "util.codon.base_dna": {"ko": "DNA(A/T/G/C)", "en": "DNA (A/T/G/C)", "ja": "DNA（A/T/G/C）"},
    "util.codon.base_mrna": {"ko": "mRNA(A/U/G/C)", "en": "mRNA (A/U/G/C)", "ja": "mRNA（A/U/G/C）"},
    "util.codon.mrna_from_dna": {"ko": "전사된 mRNA: {a0}", "en": "Transcribed mRNA: {a0}", "ja": "転写されたmRNA: {a0}"},
    "util.codon.no_aug": {
        "ko": "AUG(개시코돈)를 찾지 못했습니다. 체크를 풀거나 서열을 다시 확인하세요.",
        "en": "No AUG (start codon) found. Uncheck the option or check the sequence.",
        "ja": "AUG（開始コドン）が見つかりませんでした。チェックを外すか配列を確認してください。"},
    "util.codon.sequence_label": {"ko": "아미노산 서열:", "en": "Amino acid sequence:", "ja": "アミノ酸配列："},
    "util.codon.no_stop_note": {
        "ko": "※ 종결코돈을 만나지 못하고 서열이 끝났습니다.",
        "en": "※ The sequence ended before reaching a stop codon.",
        "ja": "※ 終止コドンに達する前に配列が終わりました。"},
    "util.codon.lbl.lookup": {"ko": "아미노산으로 코돈 찾기", "en": "Find codons for amino acid", "ja": "アミノ酸からコドンを検索"},
    "util.codon.lookup_result": {
        "ko": "{a0}을 지정하는 코돈({a2}개): {a1}",
        "en": "Codons for {a0} ({a2}): {a1}", "ja": "{a0}を指定するコドン（{a2}個）：{a1}"},
    "util.codon.toggle_table": {"ko": "전체 코돈표 보기", "en": "Show full codon table", "ja": "コドン表全体を表示"},
    "util.codon.log.translated": {
        "ko": "[코돈표] 아미노산 {a0}개로 번역했습니다",
        "en": "[Codon] Translated to {a0} amino acids", "ja": "[コドン表] アミノ酸{a0}個に翻訳しました"},
    "util.codon.log.no_aug": {
        "ko": "[코돈표] AUG를 찾지 못했습니다", "en": "[Codon] No AUG found", "ja": "[コドン表] AUGが見つかりませんでした"},
}
CodonApp.tr_table = TRANSLATIONS

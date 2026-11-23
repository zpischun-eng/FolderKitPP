# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 나이스(NEIS) 글자수 계산기 [v43.4]

글자수·바이트수는 참고 사이트(hjh010501.github.io/neis-counter)와 같은
규칙으로 계산한다. 거기에 더해, 학교생활기록부 기재요령의 "작성 시
유의사항"에 실제로 나오는 금지·유의 표현을 **규칙(키워드+정규식) 기반**으로
찾아 표시한다 — 외부 라이브러리나 인터넷 연결 없이, 지금 입력하는 동안
바로 반응한다.

**이 검사는 적합성을 미리 가늠해 보는 보조 도구일 뿐, 최종 판단을 대신하지
않는다.** 걸렸다고 반드시 틀린 것도, 안 걸렸다고 반드시 안전한 것도
아니다 — 화면에도 이 점을 분명히 적어 둔다.

[v43.4] 숨겨진 AI 맞춤법 검사·세특 일괄 작성 기능(이스터에그)을 완전히
뺐다 — "인증키"는 처음부터 나이스 개방 포털 인증키만을 뜻했고, 이 도구의
별도 AI 인증키는 애초에 쓸 계획이 없었다는 걸 확인받았다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QComboBox,
    QListWidget, QListWidgetItem, QFrame
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import neis_counter_solve as NC
from . import neis_common as N

_SET_LAST_ITEM = "util.neiscounter.last_item"


# =============================================================================
class NeisCounterWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self._build_ui()
        self._load_settings()
        self._recompute()

    def _build_ui(self):
        # ---- 왼쪽 카드: 글 입력(툴바: 항목 선택, 하단 왼쪽: 바이트 수) ----
        self.card_text = UK.Card()
        self.lbl_item = UK.body_label()
        self.card_text.add_tool(self.lbl_item)
        self.combo_item = QComboBox()
        for key in NC.ITEM_ORDER:
            self.combo_item.addItem("", key)   # 문구는 retranslate에서 채운다
        self.combo_item.currentIndexChanged.connect(self._on_item_changed)
        self.card_text.add_tool(self.combo_item)

        self.view = QTextEdit()
        self.view.setPlaceholderText("")
        self.view.setFont(QFont("Consolas", 11))
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.textChanged.connect(self._recompute)
        self.card_text.add_body(UK.canvas_frame(self.view, margin=4), 1)

        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("font-size:13px;background:transparent;")
        self.card_text.add_footer_left(self.lbl_count)

        # ---- 오른쪽 카드: 표현 점검 ----
        self.card_check = UK.Card()
        self.lbl_check_title = self.card_check.title_label
        self.list_flags = QListWidget()
        self.list_flags.setMaximumHeight(220)
        self.list_flags.setStyleSheet(
            f"QListWidget{{border:1px solid {UK.CANVAS_BORDER};border-radius:4px;background:#ffffff;}}")
        self.card_check.add_body(self.list_flags)
        self.lbl_ok = QLabel()
        self.lbl_ok.setStyleSheet("color:#2e7d32;background:transparent;")
        self.lbl_ok.setVisible(False)
        self.card_check.add_body(self.lbl_ok)
        self.lbl_hint = UK.hint_label()
        self.card_check.add_body(self.lbl_hint)
        self.card_check.body.addStretch(1)

        UK.split_lr(self, self.card_text, self.card_check)
        self.retranslate()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        if self._settings is None:
            return
        last = self._settings.value(_SET_LAST_ITEM, "autonomy")
        idx = self.combo_item.findData(last)
        if idx >= 0:
            self.combo_item.setCurrentIndex(idx)

    def _save_settings(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_LAST_ITEM, self.combo_item.currentData())

    def _current_school_name(self):
        """오늘의 급식·학교 일정과 같은 학교 설정(공유 저장소)에서 학교명을
        가져온다 — 이 도구만 따로 학교명을 입력받을 필요가 없다."""
        _office, _school, school_name, _key = N.load(self._settings)
        return school_name

    def _on_item_changed(self):
        """[버그 수정] 항목 콤보박스가 실제로(사용자가) 바뀔 때만 저장한다.
        예전에는 _recompute() 안에서 매번 저장했는데, 위젯을 막 만들 때도
        retranslate()가 _recompute()를 한 번 부르면서 아직 _load_settings()
        전인 "기본값(자율활동)"을 저장해 버려, 그 전에 저장해 둔 값(예:
        개인별세특)을 매번 덮어써 버리는 문제가 있었다."""
        self._save_settings()
        self._recompute()

    # ---------------------------------------------------------------- 계산
    def _recompute(self):
        text = self.view.toPlainText()
        item_key = self.combo_item.currentData() or "autonomy"
        limit = NC.ITEM_LIMITS.get(item_key, 1500)
        wo, wi, nbytes = NC.count_bytes(text)

        over = nbytes > limit
        color = "#d32f2f" if over else C.WINDOW_FG
        self.lbl_count.setStyleSheet(f"font-size:13px;background:transparent;color:{color};")
        self.lbl_count.setText(tr("util.neiscounter.count", a0=wo, a1=wi, a2=nbytes, a3=limit))

        flags = NC.scan(text, school_name=self._current_school_name())
        self.list_flags.clear()
        if flags:
            self.lbl_ok.setVisible(False)
            self.list_flags.setVisible(True)
            self.lbl_check_title.setText(tr("util.neiscounter.flags_title", a0=len(flags)))
            for f in flags:
                label = tr(f"util.neiscounter.cat.{f.category}")
                item = QListWidgetItem(f'[{label}] "{f.matched}"')
                self.list_flags.addItem(item)
        else:
            self.list_flags.setVisible(False)
            self.lbl_check_title.setText(tr("util.neiscounter.flags_title_empty"))
            self.lbl_ok.setVisible(bool(text.strip()))
            self.lbl_ok.setText(tr("util.neiscounter.ok"))

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.card_text.set_title(tr("util.neiscounter.title"))
        self.lbl_item.setText(tr("util.neiscounter.lbl.item"))
        for i, key in enumerate(NC.ITEM_ORDER):
            self.combo_item.setItemText(
                i, tr(f"util.neiscounter.item.{key}", a0=NC.ITEM_LIMITS[key]))
        self.lbl_hint.setText(tr("util.neiscounter.hint"))
        self._recompute()


# =============================================================================
class NeisCounterApp(MiniApp):
    id = "neiscounter"
    icon = "neiscounter"
    category = "class"   # 학교

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = NeisCounterWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.neiscounter.title": {
        "ko": "나이스 글자수 계산기", "en": "NEIS Character Counter", "ja": "NEIS文字数カウンター"},
    "util.neiscounter.desc": {
        "ko": "학생부 서술형 항목의 바이트수를 세고, 기재 유의 표현을 점검합니다.",
        "en": "Counts bytes for school-record fields and flags wording to double-check.",
        "ja": "学生部の記述型項目のバイト数を数え、記載注意表現を点検します。"},
    "util.neiscounter.lbl.item": {"ko": "항목", "en": "Field", "ja": "項目"},
    "util.neiscounter.item.autonomy": {
        "ko": "자율활동 ({a0}바이트)", "en": "Autonomy activity ({a0} bytes)", "ja": "自律活動（{a0}バイト）"},
    "util.neiscounter.item.club": {
        "ko": "동아리활동 ({a0}바이트)", "en": "Club activity ({a0} bytes)", "ja": "クラブ活動（{a0}バイト）"},
    "util.neiscounter.item.career": {
        "ko": "진로활동 ({a0}바이트)", "en": "Career activity ({a0} bytes)", "ja": "進路活動（{a0}バイト）"},
    "util.neiscounter.item.subject": {
        "ko": "교과세특 ({a0}바이트)", "en": "Subject remarks ({a0} bytes)", "ja": "教科特記事項（{a0}バイト）"},
    "util.neiscounter.item.behavior": {
        "ko": "개인별세특(행특) ({a0}바이트)", "en": "Behavior remarks ({a0} bytes)",
        "ja": "行動特性及び総合意見（{a0}バイト）"},
    "util.neiscounter.count": {
        "ko": "공백 제외 {a0}자 · 공백 포함 {a1}자 · {a2} / {a3}바이트",
        "en": "{a0} chars (no space) · {a1} chars (with space) · {a2} / {a3} bytes",
        "ja": "空白除外{a0}字 · 空白含む{a1}字 · {a2} / {a3}バイト"},
    "util.neiscounter.flags_title": {
        "ko": "확인해 볼 표현 {a0}건", "en": "{a0} phrases to double-check", "ja": "確認すべき表現{a0}件"},
    "util.neiscounter.flags_title_empty": {
        "ko": "표현 점검", "en": "Wording check", "ja": "表現の点検"},
    "util.neiscounter.ok": {
        "ko": "걸리는 표현이 없습니다(그래도 마지막 확인은 직접 해 주세요).",
        "en": "Nothing flagged (still worth a final read-through yourself).",
        "ja": "引っかかる表現はありません（最終確認は自分でも行ってください）。"},
    "util.neiscounter.hint": {
        "ko": "이 검사는 학교생활기록부 기재요령의 유의사항을 키워드·정규식으로 "
              "훑어보는 보조 도구입니다. 걸렸다고 반드시 틀린 것은 아니고, 안 걸렸다고 "
              "반드시 안전한 것도 아니니 최종 확인은 직접 해 주세요. 학교명 점검은 "
              "'학교 설정'에 입력된 학교명을 기준으로 합니다.",
        "en": "This is a keyword/regex helper based on the official school-record "
              "guidelines — a flag isn't necessarily wrong, and a clean result isn't a "
              "guarantee. Please make the final call yourself. The school-name check "
              "uses the name saved in 'School settings'.",
        "ja": "この検査は学校生活記録簿の記載要領の注意事項をキーワード・正規表現で"
              "確認する補助ツールです。引っかかっても必ず誤りとは限らず、引っかから"
              "なくても安全とは限りません。最終確認は自分で行ってください。学校名の"
              "点検は「学校の設定」に入力された学校名を基準にします。"},

    "util.neiscounter.cat.lang_test": {
        "ko": "공인어학시험", "en": "Language test", "ja": "公認語学試験"},
    "util.neiscounter.cat.external_contest": {
        "ko": "교외대회·교외상", "en": "External contest/award", "ja": "校外大会・校外賞"},
    "util.neiscounter.cat.mock_exam_score": {
        "ko": "모의고사·학평 성적", "en": "Mock exam score", "ja": "模擬試験・学力評価の成績"},
    "util.neiscounter.cat.paper_book_patent": {
        "ko": "논문·도서출간·특허", "en": "Paper/book/patent", "ja": "論文・書籍出版・特許"},
    "util.neiscounter.cat.overseas": {
        "ko": "해외 활동", "en": "Overseas activity", "ja": "海外活動"},
    "util.neiscounter.cat.scholarship": {
        "ko": "장학생·장학금", "en": "Scholarship", "ja": "奨学生・奨学金"},
    "util.neiscounter.cat.family_status": {
        "ko": "가족의 사회·경제적 지위 암시", "en": "Family status implication", "ja": "家族の社会的・経済的地位の暗示"},
    "util.neiscounter.cat.university_name": {
        "ko": "특정 대학명", "en": "Specific university name", "ja": "特定の大学名"},
    "util.neiscounter.cat.school_name_leak": {
        "ko": "학교명 노출(고교 블라인드)", "en": "School name exposure (blind review)", "ja": "学校名の露出（ブラインド審査）"},
}
NeisCounterApp.tr_table = TRANSLATIONS

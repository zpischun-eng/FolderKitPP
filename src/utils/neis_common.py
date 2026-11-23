# -*- coding: utf-8 -*-
"""
FolderKit++ — 나이스(NEIS) 공통 설정 [v05]

"오늘의 급식"과 "학교 일정"은 둘 다 나이스 개방 포털의 **같은 인증키, 같은
학교 코드**를 쓴다. 그래서 설정 저장 위치와 설정 패널 UI를 여기 한 곳에
모아 두고, 두 미니앱이 그대로 가져다 쓴다 — 인증키를 한 번만 입력하면
두 도구 모두에 바로 적용된다(따로 두 번 입력할 필요가 없다).
"""
import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QToolButton, QListWidget, QListWidgetItem
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK

# [v43.3] 배포용 편의 기능 — 이 앱은 학생이 아니라 교사에게만 배포되고,
# 아래 값은 실제로 쓰는 나이스 개방 포털 인증키다(예시가 아니라 진짜
# 값). 새 컴퓨터에 설치할 때마다 인증키를 따로 전달·기억할 필요 없이,
# 인증키 칸에서 Ctrl+Shift+F10을 누르면 이 값이 그대로 채워진다.
# 화면에는 평소 "예) ..." 형식 힌트로만 보이고(놓치기 쉬운 우연한 조작으로
# 발동하지 않도록 흔치 않은 단축키를 썼다), 실제로 채워 넣으려면 이
# 단축키를 알고 있어야 한다.
# [버그 수정] 처음엔 Ctrl+Alt+Shift+D였는데, 실제 배포 환경에서 전혀
# 반응하지 않고 그냥 'D' 글자만 입력되는 문제가 있었다 — 많은 키보드
# 레이아웃(국제/유럽 자판 포함)에서 Ctrl+Alt를 동시에 누르면 운영체제가
# 이를 AltGr(오른쪽 Alt)로 해석해서, Qt가 온전한 단축키 조합을 보기도
# 전에 OS가 먼저 "그냥 그 글자를 입력하라"는 뜻으로 가로채 버린다.
# Alt를 아예 빼고, 문자 조합 자체가 불가능한 기능키 기반으로 바꿔서
# 이 문제를 원천적으로 피했다(한때 F9를 썼다가, 나이스 글자수
# 계산기의 AI 기능을 완전히 빼면서 그쪽이 쓰던 F10이 비어, 오늘의
# 급식·학교 일정·컴시간 알리미가 전부 Ctrl+Shift+F10 하나로 통일됐다).
#
# [v51.3] 저장소를 공개(public)로 바꾸면서 인증키를 소스에서 뺐다. 이제는
#  - GitHub 자동 빌드: 저장소 Secret "NEIS_KEY"를 빌드 때 src/_build_secrets.py로 써 넣는다
#    (이 파일은 .gitignore — 소스에는 올라가지 않는다)
#  - 직접 실행·빌드: 환경 변수 FOLDERKIT_NEIS_KEY, 또는 src/_build_secrets.py를 손으로 만들어도 된다
#  - 둘 다 없으면 빈 값 — 단축키를 눌러도 아무것도 채워지지 않고, 각자 발급받은 키를 넣으면 된다
def _load_build_key():
    try:
        from .._build_secrets import NEIS_KEY      # 빌드 서버가 만드는 파일(공개 소스엔 없음)
        if NEIS_KEY:
            return NEIS_KEY
    except Exception:
        pass
    return os.environ.get("FOLDERKIT_NEIS_KEY", "")


_MY_NEIS_KEY = _load_build_key()
NEIS_KEY_EXAMPLE = "0123456789abcdef0123456789abcdef"   # 화면 예시(형식만 — 실제 키 아님)
_FILL_KEY_SHORTCUT = "Ctrl+Shift+F10"

SET_KEY = "util.neis.key"
SET_OFFICE = "util.neis.office_code"
SET_SCHOOL = "util.neis.school_code"
SET_SCHOOL_NAME = "util.neis.school_name"

# v04에서 "오늘의 급식"이 혼자 쓰던 이름. 이미 저장해 둔 사람이 인증키를
# 다시 입력하지 않도록, 새 이름 자리에 값이 없을 때만 한 번 옮겨 온다.
_LEGACY_KEY = "util.meal.key"
_LEGACY_OFFICE = "util.meal.office_code"
_LEGACY_SCHOOL = "util.meal.school_code"
_LEGACY_SCHOOL_NAME = "util.meal.school_name"

# 서울특별시교육청 / 선린인터넷고등학교 나이스 코드(공개 식별자 — 인증키와
# 달리 하드코딩해도 안전하다). "오늘의 급식"에서 처음 확인한 값 그대로.
DEFAULT_OFFICE_CODE = "B10"
DEFAULT_SCHOOL_CODE = "7010536"
DEFAULT_SCHOOL_NAME = "선린인터넷고등학교"

PORTAL_URL = "https://open.neis.go.kr/portal/mainPage.do"
_SCHOOL_SEARCH_BASE = "https://open.neis.go.kr/hub/schoolInfo"


class School:
    """학교 검색 결과 한 건."""

    def __init__(self, office_code, office_name, school_code, school_name, address=""):
        self.office_code = office_code
        self.office_name = office_name
        self.school_code = school_code
        self.school_name = school_name
        self.address = address

    def display_text(self):
        return f"{self.school_name} ({self.office_name}" + (f" · {self.address})" if self.address else ")")


class SchoolSearchResult:
    def __init__(self, status, schools=None, message=""):
        self.status = status          # "ok" | "empty" | "error"
        self.schools = schools or []
        self.message = message


def build_school_search_url(key, school_name):
    """[신규] 학교기본정보(schoolInfo) 검색 URL. 다른 학교 선생님이
    교육청코드·학교코드를 몰라도, 학교 이름만 입력하면 이 API로 찾아서
    자동으로 채워 준다."""
    from urllib.parse import urlencode
    params = {
        "KEY": key, "Type": "json",
        "pIndex": "1", "pSize": "100",
        "SCHUL_NM": school_name,
    }
    return f"{_SCHOOL_SEARCH_BASE}?{urlencode(params)}"


def parse_school_search_response(raw: str) -> SchoolSearchResult:
    """schoolInfo 응답(JSON)을 School 목록으로 바꾼다. 나이스는 필수
    파라미터가 빠지면 Type=json이라도 XML로 오류를 돌려주는 경우가
    있어(다른 나이스 API에서 이미 확인한 버릇), JSON 파싱이 아예 안 될
    때도 조용히 오류로 처리한다."""
    import json
    try:
        data = json.loads(raw)
    except ValueError:
        return SchoolSearchResult("error", message="응답을 해석할 수 없습니다.")

    root = data.get("schoolInfo")
    if not isinstance(root, list):
        # RESULT 코드만 있고 데이터가 없는 형태(정의역 밖 학교명 등)
        result_info = data.get("RESULT", {})
        code = result_info.get("CODE", "")
        if code and code != "INFO-000":
            return SchoolSearchResult("empty", message=result_info.get("MESSAGE", ""))
        return SchoolSearchResult("empty")

    rows = []
    for block in root:
        if isinstance(block, dict) and "row" in block:
            rows = block["row"]
            break
    if not rows:
        return SchoolSearchResult("empty")

    schools = [
        School(
            office_code=r.get("ATPT_OFCDC_SC_CODE", ""),
            office_name=r.get("ATPT_OFCDC_SC_NM", ""),
            school_code=r.get("SD_SCHUL_CODE", ""),
            school_name=r.get("SCHUL_NM", ""),
            address=r.get("ORG_RDNMA", "") or "",
        )
        for r in rows if r.get("SD_SCHUL_CODE")
    ]
    return SchoolSearchResult("ok", schools)


def load(settings):
    """QSettings에서 (인증키, 교육청코드, 학교코드, 학교명)을 읽는다.
    settings가 None이면 기본값만 돌려준다."""
    if settings is None:
        return DEFAULT_OFFICE_CODE, DEFAULT_SCHOOL_CODE, DEFAULT_SCHOOL_NAME, ""

    key = settings.value(SET_KEY, "") or ""
    if not key:
        legacy_key = settings.value(_LEGACY_KEY, "") or ""
        if legacy_key:
            key = legacy_key
            settings.setValue(SET_KEY, legacy_key)   # 새 자리로 한 번만 이전

    office = (settings.value(SET_OFFICE, "") or settings.value(_LEGACY_OFFICE, "")
              or DEFAULT_OFFICE_CODE)
    school = (settings.value(SET_SCHOOL, "") or settings.value(_LEGACY_SCHOOL, "")
              or DEFAULT_SCHOOL_CODE)
    school_name = (settings.value(SET_SCHOOL_NAME, "") or settings.value(_LEGACY_SCHOOL_NAME, "")
                   or DEFAULT_SCHOOL_NAME)
    return office, school, school_name, key


def save(settings, key, office, school, school_name):
    if settings is None:
        return
    settings.setValue(SET_KEY, key)
    settings.setValue(SET_OFFICE, office)
    settings.setValue(SET_SCHOOL, school)
    settings.setValue(SET_SCHOOL_NAME, school_name)


# =============================================================================
class NeisSettingsPanel(QWidget):
    """"학교 설정" 접이식 패널 — 인증키 + 교육청코드 + 학교코드 + 학교명.

    "오늘의 급식"·"학교 일정" 양쪽에서 그대로 붙여 쓴다. 값이 바뀔 때마다
    :attr:`changed` 신호를 보내고, 부모(미니앱)는 이 신호를 받아 자기
    화면을 새로 불러오면 된다.
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        self._search_reply = None
        self._search_results = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setArrowType(Qt.RightArrow)
        UK.style_tool_toolbutton(self.toggle, "⚙")   # [v34] 카드 툴바에 놓이는 설정 버튼
        self.toggle.clicked.connect(self._on_toggle)
        lay.addWidget(self.toggle)

        self.panel = QFrame()
        self.panel.setVisible(False)
        self.panel.setObjectName("neisSettingsPanel")
        self.panel.setStyleSheet(
            f"QFrame#neisSettingsPanel{{background-color:#ffffff;border:1px solid {UK.CANVAS_BORDER};"
            "border-radius:4px;}")
        pl = QVBoxLayout(self.panel)
        pl.setSpacing(6)

        key_row = QHBoxLayout()
        self.lbl_key = QLabel()
        key_row.addWidget(self.lbl_key)
        self.edit_key = QLineEdit()
        # [신규] 새 버전을 배부할 때마다 인증키를 따로 알려줘야 하는
        # 불편 때문에 "화면에 안 보이게 감춰서 안 외워도 되게" 해 달라는
        # 요청이 있었다. 이스트에그(숨겨진 단축키/더블클릭)로 노출하는
        # 방식은 화면 공유·빔프로젝터로 수업하는 교실 환경에서 무심코
        # 눌려 학생들에게 그대로 노출될 위험이 있어, 대신 비밀번호
        # 관리자에서 흔히 쓰는 **보이기/숨기기 토글**과 **복사 버튼**을
        # 뒀다 — 기본은 가려져 있고, 누를 때만 의도적으로 보인다.
        self.edit_key.setEchoMode(QLineEdit.Password)
        self.edit_key.setPlaceholderText(f"예) {NEIS_KEY_EXAMPLE}")   # [v51.3] 실제 키는 화면에 안 보임
        self.edit_key.editingFinished.connect(self._emit_changed)
        key_row.addWidget(self.edit_key, 1)

        # [v39.3] 인증키 칸에서 Ctrl+Shift+F10 — 실제 인증키를 그대로
        # 채워 넣는다(교사 전용 배포판 편의 기능).
        #
        # [버그 수정] 단축키가 전혀 반응하지 않던 진짜 원인 — Qt의
        # QShortcut은 context를 무엇으로 두든(WindowShortcut이든
        # ApplicationShortcut이든) 매달린 위젯 자신이 한 번이라도
        # 화면에 표시된 적이 없으면(isVisible()==False) 절대 반응하지
        # 않는다(실제로 재현해서 확인했다). 처음엔 self(패널 전체)에
        # 매달았는데, 이 패널은 meal.py·timetable.py 등에서 toggle·
        # panel 두 조각만 따로 떼어 카드에 붙이고 self 자신은 어디에도
        # addWidget되지 않아(addWidget하면 자식이 그 레이아웃 주인에게
        # 다시 부모로 붙기 때문에) 화면 트리에서 완전히 떨어져 나간
        # "고아" 위젯이었다. self.edit_key(입력칸 자체)로 옮겨도 여전히
        # 안 됐는데, edit_key는 self.panel(접이식 안쪽 내용) 밑에 있고
        # **패널이 기본으로 접혀 있어서**(self.panel.setVisible(False))
        # 패널을 펼치기 전까지는 그 안의 edit_key도 계속 안 보이는
        # 상태였기 때문이다(Qt는 조상까지 전부 보여야 그 위젯도
        # visible로 친다) — 그러면 패널을 먼저 펼쳐야만 단축키가
        # 살아나서, "펼치지 않고도 바로 채운다"는 이 기능의 존재
        # 의미가 없어진다. 그래서 **항상 화면에 보이는** ⚙ 토글
        # 버튼(self.toggle)에 최종적으로 매달았다.
        self._shortcut_fill_key = QShortcut(QKeySequence(_FILL_KEY_SHORTCUT), self.toggle)
        self._shortcut_fill_key.setContext(Qt.ApplicationShortcut)
        self._shortcut_fill_key.activated.connect(self._fill_real_key)

        self.btn_toggle_key = QToolButton()
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.setText("\U0001F441")   # 👁
        self.btn_toggle_key.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_key.clicked.connect(self._on_toggle_key_visibility)
        key_row.addWidget(self.btn_toggle_key)

        self.btn_copy_key = QToolButton()
        self.btn_copy_key.setText("\u29C9")   # ⧉
        self.btn_copy_key.setCursor(Qt.PointingHandCursor)
        self.btn_copy_key.clicked.connect(self._on_copy_key)
        key_row.addWidget(self.btn_copy_key)

        self.btn_get_key = QPushButton()
        self.btn_get_key.setCursor(Qt.PointingHandCursor)
        self.btn_get_key.setStyleSheet(UK.secondary_button().styleSheet())
        self.btn_get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PORTAL_URL)))
        key_row.addWidget(self.btn_get_key)
        pl.addLayout(key_row)

        code_row = QHBoxLayout()
        self.lbl_office = QLabel()
        code_row.addWidget(self.lbl_office)
        self.edit_office = QLineEdit()
        self.edit_office.setFixedWidth(60)
        self.edit_office.editingFinished.connect(self._emit_changed)
        code_row.addWidget(self.edit_office)
        self.lbl_school = QLabel()
        code_row.addWidget(self.lbl_school)
        self.edit_school = QLineEdit()
        self.edit_school.setFixedWidth(90)
        self.edit_school.editingFinished.connect(self._emit_changed)
        code_row.addWidget(self.edit_school)
        self.lbl_school_name = QLabel()
        code_row.addWidget(self.lbl_school_name)
        self.edit_school_name = QLineEdit()
        self.edit_school_name.editingFinished.connect(self._emit_changed)
        self.edit_school_name.returnPressed.connect(self._on_search_school)
        code_row.addWidget(self.edit_school_name, 1)
        self.btn_search_school = QPushButton()
        self.btn_search_school.setCursor(Qt.PointingHandCursor)
        self.btn_search_school.setStyleSheet(UK.secondary_button().styleSheet())
        self.btn_search_school.clicked.connect(self._on_search_school)
        code_row.addWidget(self.btn_search_school)
        pl.addLayout(code_row)

        # [신규] 학교명으로 교육청코드·학교코드를 자동으로 찾아 채우는
        # 목록 — 다른 학교 선생님은 이 두 코드를 모르는 게 당연하므로,
        # 코드 대신 학교 이름만 알면 되게 한다. 결과가 있을 때만 보인다.
        self.list_school_results = QListWidget()
        self.list_school_results.setVisible(False)
        self.list_school_results.setMaximumHeight(120)
        self.list_school_results.itemClicked.connect(self._on_school_selected)
        pl.addWidget(self.list_school_results)

        self.lbl_school_status = QLabel()
        self.lbl_school_status.setStyleSheet("color:#6b7280;font-size:11px;background:transparent;")
        self.lbl_school_status.setVisible(False)
        pl.addWidget(self.lbl_school_status)

        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color:#6b7280;font-size:11px;background:transparent;")
        pl.addWidget(self.lbl_hint)

        lay.addWidget(self.panel)
        self.retranslate()

    def _on_toggle(self):
        show = self.toggle.isChecked()
        self.panel.setVisible(show)

    def _on_toggle_key_visibility(self):
        show = self.btn_toggle_key.isChecked()
        self.edit_key.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)

    def _fill_real_key(self):
        """[v39.3] Ctrl+Shift+F10 — 설정 패널이 접혀 있으면 먼저 펼쳐서
        채워진 값이 바로 눈에 보이게 하고, 인증키 칸에 실제 값을 넣은
        뒤 저장(부모에게 changed 신호)까지 한다."""
        if not _MY_NEIS_KEY:          # [v51.3] 빌드에 키가 안 들어 있으면 아무것도 안 함
            return
        if not self.toggle.isChecked():
            self.toggle.setChecked(True)
            self._on_toggle()
        self.edit_key.setText(_MY_NEIS_KEY)
        self._emit_changed()

    def _on_copy_key(self):
        QGuiApplication.clipboard().setText(self.edit_key.text().strip())

    # ---- 학교 검색 ----
    def _on_search_school(self):
        key = self.edit_key.text().strip()
        name = self.edit_school_name.text().strip()
        if not key:
            self._show_school_status(tr("util.neis.school_search.need_key"))
            return
        if not name:
            self._show_school_status(tr("util.neis.school_search.need_name"))
            return

        if self._search_reply is not None:
            self._search_reply.abort()
            self._search_reply = None

        self._show_school_status(tr("util.neis.school_search.loading"))
        url = build_school_search_url(key, name)
        req = QNetworkRequest(QUrl(url))
        reply = self.nam.get(req)
        self._search_reply = reply
        reply.finished.connect(lambda: self._on_school_search_finished(reply))

    def _on_school_search_finished(self, reply):
        if reply is not self._search_reply:
            reply.deleteLater()
            return
        self._search_reply = None

        if reply.error() != QNetworkReply.NoError:
            if reply.error() != QNetworkReply.OperationCanceledError:
                self._show_school_status(tr("util.neis.school_search.network_error", a0=reply.errorString()))
            reply.deleteLater()
            return

        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        result = parse_school_search_response(raw)

        if result.status == "error":
            self._show_school_status(tr("util.neis.school_search.error"))
            return
        if result.status == "empty" or not result.schools:
            self._show_school_status(tr("util.neis.school_search.empty"))
            return

        self._search_results = result.schools
        self.list_school_results.clear()
        for school in result.schools:
            item = QListWidgetItem(school.display_text())
            self.list_school_results.addItem(item)
        self.list_school_results.setVisible(True)
        self._show_school_status(tr("util.neis.school_search.found", a0=len(result.schools)))

    def _on_school_selected(self, item):
        row = self.list_school_results.row(item)
        if row < 0 or row >= len(self._search_results):
            return
        school = self._search_results[row]
        self.edit_office.setText(school.office_code)
        self.edit_school.setText(school.school_code)
        self.edit_school_name.setText(school.school_name)
        self.list_school_results.setVisible(False)
        self._hide_school_status()
        self._emit_changed()

    def _show_school_status(self, text):
        self.lbl_school_status.setText(text)
        self.lbl_school_status.setVisible(True)

    def _hide_school_status(self):
        self.lbl_school_status.setVisible(False)

    def _emit_changed(self):
        self.changed.emit()

    # ---- 값 읽기/쓰기 ----
    def values(self):
        """(인증키, 교육청코드, 학교코드, 학교명) — 코드류는 비어 있으면
        기본값(선린인터넷고)으로 채워 돌려준다."""
        key = self.edit_key.text().strip()
        office = self.edit_office.text().strip() or DEFAULT_OFFICE_CODE
        school = self.edit_school.text().strip() or DEFAULT_SCHOOL_CODE
        name = self.edit_school_name.text().strip() or DEFAULT_SCHOOL_NAME
        return key, office, school, name

    def set_values(self, key, office, school, school_name):
        self.edit_key.setText(key)
        self.edit_office.setText(office)
        self.edit_school.setText(school)
        self.edit_school_name.setText(school_name)

    def retranslate(self):
        self.toggle.setToolTip(tr("util.neis.settings.toggle"))
        self.lbl_key.setText(tr("util.neis.lbl.key"))
        self.btn_toggle_key.setToolTip(tr("util.neis.btn.toggle_key.tip"))
        self.btn_copy_key.setToolTip(tr("util.neis.btn.copy_key.tip"))
        self.btn_get_key.setText(tr("util.neis.btn.get_key"))
        self.btn_get_key.setToolTip(tr("util.neis.btn.get_key.tip"))
        self.lbl_office.setText(tr("util.neis.lbl.office"))
        self.lbl_school.setText(tr("util.neis.lbl.school"))
        self.lbl_school_name.setText(tr("util.neis.lbl.school_name"))
        self.btn_search_school.setText(tr("util.neis.btn.search_school"))
        self.btn_search_school.setToolTip(tr("util.neis.btn.search_school.tip"))
        self.lbl_hint.setText(tr("util.neis.settings.hint"))


TRANSLATIONS = {
    "util.neis.settings.toggle": {
        "ko": "학교 설정", "en": "School settings", "ja": "学校の設定"},
    "util.neis.settings.hint": {
        "ko": "교육청코드·학교코드는 선린인터넷고등학교 기본값이 이미 들어 있습니다. "
              "다른 학교로 바꾸려면 학교명을 입력하고 '검색' 버튼을 눌러 목록에서 고르세요 "
              "(코드를 직접 몰라도 됩니다). 이 설정은 '오늘의 급식'·'학교 일정'·'컴시간 알리미 간편 버전'이 함께 씁니다.",
        "en": "Office/school codes already default to Sunrin Internet High School. "
              "To use another school, type its name and press 'Search' to pick it from the list "
              "(no need to know the codes yourself). This setting is shared by "
              "'School Lunch', 'School Schedule', and 'Class Timetable'.",
        "ja": "教育庁コード・学校コードには選린インターネット高校の既定値が入っています。"
              "他の学校を使う場合は学校名を入力して「検索」ボタンを押し、リストから選んでください"
              "（コードを直接知らなくても構いません）。この設定は「給食」「学校日程」「時間表」の3つで共有されます。"},
    "util.neis.lbl.key": {"ko": "인증키", "en": "API key", "ja": "認証キー"},
    "util.neis.btn.toggle_key.tip": {
        "ko": "인증키를 화면에 보이거나 다시 가립니다.",
        "en": "Shows or hides the API key on screen.",
        "ja": "認証キーを画面に表示または再度隠します。"},
    "util.neis.btn.copy_key.tip": {
        "ko": "인증키를 화면에 띄우지 않고 클립보드로 복사합니다.",
        "en": "Copies the API key to the clipboard without showing it on screen.",
        "ja": "認証キーを画面に表示せずクリップボードにコピーします。"},
    "util.neis.btn.get_key": {"ko": "발급받기", "en": "Get a key", "ja": "発行を受ける"},
    "util.neis.btn.get_key.tip": {
        "ko": "나이스 교육정보 개방 포털에서 무료로 인증키를 발급받을 수 있는 페이지를 엽니다.",
        "en": "Opens the NEIS open data portal page where you can get a free API key.",
        "ja": "NEIS教育情報開放ポータルで無料の認証キーを発行できるページを開きます。"},
    "util.neis.lbl.office": {"ko": "교육청코드", "en": "Office code", "ja": "教育庁コード"},
    "util.neis.lbl.school": {"ko": "학교코드", "en": "School code", "ja": "学校コード"},
    "util.neis.lbl.school_name": {"ko": "학교명", "en": "School name", "ja": "学校名"},
    "util.neis.btn.search_school": {"ko": "검색", "en": "Search", "ja": "検索"},
    "util.neis.btn.search_school.tip": {
        "ko": "학교명으로 교육청코드·학교코드를 찾아 자동으로 채웁니다.",
        "en": "Looks up the office/school codes by school name and fills them in.",
        "ja": "学校名で教育庁コード・学校コードを検索して自動入力します。"},
    "util.neis.school_search.need_key": {
        "ko": "학교 검색에도 인증키가 필요합니다. 먼저 위에서 인증키를 입력하세요.",
        "en": "School search also needs an API key. Enter it above first.",
        "ja": "学校検索にも認証キーが必要です。先に上で認証キーを入力してください。"},
    "util.neis.school_search.need_name": {
        "ko": "학교명을 입력하세요.", "en": "Enter a school name.", "ja": "学校名を入力してください。"},
    "util.neis.school_search.loading": {
        "ko": "검색 중...", "en": "Searching…", "ja": "検索中…"},
    "util.neis.school_search.found": {
        "ko": "{a0}개 학교를 찾았습니다. 목록에서 골라 주세요.",
        "en": "Found {a0} schools. Pick one from the list.",
        "ja": "{a0}件の学校が見つかりました。リストから選んでください。"},
    "util.neis.school_search.empty": {
        "ko": "해당하는 학교를 찾지 못했습니다. 학교명을 다시 확인해 주세요.",
        "en": "No matching school found. Please check the school name.",
        "ja": "該当する学校が見つかりませんでした。学校名を確認してください。"},
    "util.neis.school_search.error": {
        "ko": "검색 응답을 처리하지 못했습니다.",
        "en": "Couldn't process the search response.",
        "ja": "検索応答を処理できませんでした。"},
    "util.neis.school_search.network_error": {
        "ko": "검색 중 네트워크 오류: {a0}",
        "en": "Network error while searching: {a0}",
        "ja": "検索中にネットワークエラー: {a0}"},
}

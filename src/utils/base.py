# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱(유틸리티 도구) 공통 규약 [v01]

Util 모드에 들어가는 도구 하나하나가 이 파일의 :class:`MiniApp` 을 상속한다.
규약을 이렇게 얇게 유지하는 이유는 단 하나 — **미니앱이 MainWindow를 몰라야**
앞으로 도구가 20개, 30개로 늘어나도 main_window.py(이미 3300줄이 넘는다)가
같이 부풀지 않기 때문이다. 미니앱은 자기 위젯 하나만 만들어 돌려주고,
바깥 세상(콘솔 로그·상태바·환경설정)과는 :class:`UtilHost` 어댑터를 통해서만
이야기한다.

새 도구를 추가하는 절차는 docs/util_miniapp_guide.md 를 참고할 것.
"""
from PySide6.QtCore import QSettings

from ..i18n import tr


# =============================================================================
class UtilHost:
    """미니앱이 바깥(메인 윈도우)에 접근할 수 있는 유일한 통로.

    MainWindow를 통째로 넘기지 않고 이 얇은 어댑터만 넘기는 이유:

    1. 미니앱이 MainWindow의 내부 사정(스택 인덱스, 트리 위젯 이름 등)에
       의존하지 못하게 막는다 — 나중에 메인 레이아웃을 또 바꾸더라도
       미니앱들은 하나도 안 고쳐도 된다.
    2. 테스트할 때 이 클래스 대신 가짜 객체(log를 리스트에 모으는 등)를
       넘기면 미니앱 하나만 따로 헤드리스로 검증할 수 있다.
    """

    #: 환경설정과 같은 저장소를 쓴다 — 조직/앱 이름을 바꾸면 기존 사용자의
    #: 설정(언어·즐겨찾기·캐시 크기 등)이 전부 초기화되어 버리므로,
    #: FolderKit++ 로 이름이 바뀐 뒤에도 이 두 문자열은 그대로 둔다.
    ORG = "SRIHS"
    APP = "FolderSync"

    def __init__(self, window=None):
        self._w = window

    # ---- 메인 윈도우 공용 출력 ----
    def log(self, text):
        """콘솔 로그(접이식)에 한 줄 남긴다 — 4개 기존 모드와 동일한 창구."""
        if self._w is not None:
            self._w.logmsg(text)

    def status(self, text):
        """하단 상태바 문구를 바꾼다."""
        if self._w is not None:
            self._w.status.showMessage(text)

    # ---- 저장소 ----
    @property
    def cfg(self):
        return getattr(self._w, "cfg", None)

    def settings(self):
        return QSettings(self.ORG, self.APP)

    # ---- 대기 표시 ----
    def run_busy(self, text, fn):
        """무거운 동작(fn) 동안 전체 화면을 디밍하고 점 5개짜리 대기
        애니메이션을 보여준다(동기화 모드 등 기존 4개 모드와 같은 연출).
        메인 윈도우가 없는 테스트 환경에서는 그냥 fn()만 실행한다."""
        overlay = getattr(self._w, "overlay", None)
        if overlay is None:
            return fn()
        overlay.start(text)
        try:
            return fn()
        finally:
            overlay.stop()

    def busy_start(self, text):
        """[v41] 네트워크 응답처럼 **비동기**로 끝나는 작업을 기다릴 때
        쓴다 — run_busy는 fn()이 끝날 때까지 화면을 막고 기다리는
        동기 전용이라, QNetworkReply.finished 콜백에서 나중에 끝나는
        요청에는 못 쓴다. 요청을 보내기 직전에 이걸 부르고, 응답이
        오면(성공·실패 모두) busy_stop()을 반드시 짝지어 불러야 한다."""
        overlay = getattr(self._w, "overlay", None)
        if overlay is not None:
            overlay.start(text)

    def busy_stop(self):
        overlay = getattr(self._w, "overlay", None)
        if overlay is not None:
            overlay.stop()

    # ---- 창 숨기기/복귀 ----
    def hide_main_window(self):
        """[v42] 화면 캡쳐처럼 "메인 창이 화면에 없어야" 하는 순간에 쓴다
        (내 창이 다른 창을 가리고 있으면 캡쳐에 찍힌다). 메인 윈도우가
        없는 테스트 환경에서는 아무 일도 안 한다."""
        if self._w is not None:
            self._w.hide()

    def show_main_window(self):
        if self._w is not None:
            self._w.show()
            self._w.raise_()
            self._w.activateWindow()

    # ---- 다른 모드와 연계 ----
    def open_in_image_edit(self, folder_path):
        """[v43] 사진 옮기기처럼 "결과 폴더를 바로 이미지 편집 모드로
        넘기고 싶은" 도구를 위한 진입점. 이미지 편집 모드가 이미 쓰고
        있는 source_path + switch_mode("imgedit") 그대로를 재사용한다."""
        if self._w is None:
            return
        self._w.source_path = folder_path
        self._w.switch_mode("imgedit")


# =============================================================================
class MiniApp:
    """Util 모드에 등록되는 도구 하나.

    하위 클래스가 반드시 정해야 하는 것은 아래 네 개의 **내부 키**와
    :meth:`build` 하나뿐이다. 화면에 보이는 문구는 절대 여기에 직접 쓰지 않고
    i18n 키(`util.<id>.title` / `util.<id>.desc`)로만 정의한다 — 내부 키와
    표시 문구를 섞어 쓰면 언어를 바꾸는 순간 저장된 값과 화면이 어긋난다
    (FolderKit v41 크롭 비율 콤보에서 이미 한 번 겪은 문제).
    """

    id = ""            # 내부 키 — 저장·비교 전용. 화면에 절대 노출되지 않는다.
    icon = ""          # icons.make_app_icon()이 그릴 글리프 종류(내부 키)
    category = "misc"  # 내부 키 — utils/__init__.py의 CATEGORY_ORDER 참고
    hidden = False     # [v43.9] True면 도구 목록·홈 화면·최근 사용에 전혀 안 보인다
                       # (전용 단축키로 직접 열 때만 접근 가능 — 일반적이지 않은 도구용)
    tr_table = {}      # 이 도구만의 번역 조각. 등록 시 i18n.TR에 병합된다.

    # ---- 표시 문구(항상 현재 언어로 그때그때 계산) ----
    def title(self):
        return tr(f"util.{self.id}.title")

    def desc(self):
        return tr(f"util.{self.id}.desc")

    # ---- 생명주기 ----
    def build(self, host: UtilHost):
        """도구의 실제 위젯을 만들어 돌려준다.

        **처음 선택되는 순간에 딱 한 번만** 호출된다(지연 생성). 프로그램이
        켜질 때 모든 도구를 미리 만들면 기동이 느려지므로, 무거운 import도
        전부 이 함수 안에서 하는 것을 권장한다.
        """
        raise NotImplementedError

    def has_unsaved(self) -> bool:
        """다른 모드로 나갈 때 확인 팝업이 필요하면 True.

        계산기처럼 저장할 것이 없는 도구는 기본값(False) 그대로 두면 된다.
        """
        return False

    def retranslate(self):
        """환경설정에서 언어가 바뀐 직후 호출된다.

        아직 build()되지 않은 도구에는 호출되지 않는다(위젯이 없으므로).
        """
        pass

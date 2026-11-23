# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 레지스트리 [v01]

**새 도구를 추가할 때 손대는 파일은 여기 하나뿐이다.**
(1) src/utils/ 아래에 도구 모듈을 만들고, (2) 아래 _APP_CLASSES 목록에 한 줄
추가하면 좌측 목록·홈 카드·검색·다국어에 자동으로 붙는다. main_window.py는
전혀 건드리지 않는다. 자세한 절차는 docs/util_miniapp_guide.md 참고.

importlib로 폴더를 자동 스캔하지 않고 목록을 명시적으로 적는 이유:
PyInstaller가 "코드에 안 보이는" import를 놓쳐서, 개발 PC에서는 되는데
배포한 exe에서만 도구가 사라지는 사고가 나기 때문이다.
"""
from ..i18n import register_translations, tr
from .base import MiniApp, UtilHost
from ..platform_info import app_available
from .calculator import CalculatorApp
from .kmap import KMapApp
from .graph import GraphApp
from .polar import PolarApp
from .meal import MealApp
from .schedule import ScheduleApp
from .neis_counter import NeisCounterApp
from .bracket import BracketApp
from .codon import CodonApp
from .codonsim import CodonSimApp
from .cpusched import CpuSchedApp
from .seating import SeatingApp
from .timetable import TimetableApp
from .phone_transfer import PhoneTransferApp
from .lucky_draw import LuckyDrawApp
from .cheer import CheerApp
from .timerclock import TimerClockApp
from .sudoku import SudokuApp

# 좌측 목록·홈 화면에서 카테고리가 나오는 순서(내부 키). 여기 없는 카테고리는
# 목록 맨 뒤에 붙는다. 앞으로 들어올 도구들을 위해 미리 자리를 잡아 두었다.
# [v06] "graph" 카테고리는 더 안 쓴다 — 함수 그래프(GraphApp)가 "수학"(math)
# 카테고리로 옮겨져 공학용 계산기와 함께 묶였다(사용자 요청: 메뉴를
# 수학/정보컴퓨터/학교로 통합). 카테고리 표시 이름은 i18n.py의
# util.cat.* 에서 바뀐다 — 여기 내부 키(class, logic 등)는 그대로다.
CATEGORY_ORDER = ["math", "logic", "convert", "class", "misc"]

_APP_CLASSES = [
    CalculatorApp,
    KMapApp,
    GraphApp,
    PolarApp,
    MealApp,
    ScheduleApp,
    NeisCounterApp,
    BracketApp,
    CodonApp,
    CodonSimApp,   # [v33] 학교(class) — 코돈시뮬(w→x→y→z 변이 체인, 조건 판정판·보기)
    CpuSchedApp,   # [v32] 정보컴퓨터(logic) — CPU 스케줄링 간트차트
    SeatingApp,    # [v40] 학교(class) — 좌석표(줄 수 지정 무작위 배치)
    TimetableApp,  # [v41] 학교(class) — 컴시간 알리미 간편 버전(나이스 공식 API)
    PhoneTransferApp,  # [v43] 기타(misc) — 갤럭시폰 사진 옮기기(adb, 날짜별 일괄 다운로드)
    LuckyDrawApp,  # [v44] 학교(class) — 행운의 번호(선린 패킷 추첨기: 물리 드럼·이진 라우터)
    CheerApp,      # [v44] 학교(class) — 응원의 메시지(활로 풍선을 맞혀 오늘의 메시지 공개)
    TimerClockApp,  # [v45] 기타(misc) — 타이머/시계(공항·기차역 스플릿플랩 보드)
    SudokuApp,      # [v46] 논리(logic) — 스도쿠(생성·힌트·메모)
    # 예정: RadixApp(convert) ...
]


def category_label(key: str) -> str:
    """카테고리 내부 키 → 현재 언어의 표시 문구."""
    return tr(f"util.cat.{key}")


def build_apps():
    """미니앱 인스턴스를 만들고 각자의 번역 조각을 i18n에 병합한다.

    여기서 만드는 것은 **가벼운 설명 객체**일 뿐, 실제 위젯은 사용자가 그
    도구를 처음 열 때 build()에서 만들어진다(지연 생성).
    """
    apps = []
    for cls in _APP_CLASSES:
        if not app_available(cls.id):      # [v51] 맥에서는 일상 도구만(platform_info.MAC_APP_IDS)
            continue
        app = cls()
        register_translations(getattr(app, "tr_table", None) or {})
        apps.append(app)
    return apps


__all__ = ["MiniApp", "UtilHost", "CATEGORY_ORDER", "build_apps", "category_label"]

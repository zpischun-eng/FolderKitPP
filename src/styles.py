# -*- coding: utf-8 -*-
"""
FolderKit — 색상 팔레트 / 공통 상수
- OS 다크·라이트 테마와 무관하게 항상 동일한 색을 쓰기 위한 고정 팔레트(class C)
- 이미지 편집 모드 상수, 리네임 모드 파일/폴더 아이콘, 제외 패턴 등
"""
import fnmatch
import os

# [v01] FolderKit++ — FolderKit v50의 기능을 그대로 이어받되, Util 모드(미니앱
# 모음)라는 새 축이 추가되면서 프로그램 성격 자체가 "폴더 도구"에서 "폴더 +
# 수업/업무 도구 모음"으로 넓어졌다. 그래서 이름을 바꾸고 버전은 v01부터
# 다시 센다. 저장소(QSettings) 이름은 일부러 그대로 두었다 — 바꾸면 기존
# 사용자의 언어·즐겨찾기·캐시 설정이 전부 초기화된다.
APP_NAME = "FolderKit++"
APP_VERSION = "v51.3"
APP_LEGACY = "FolderKit v50"   # 이 버전이 이어받은 직전 버전(문서·정보 표시용)

# [v42] 아이폰 기본 사진 포맷(HEIC/HEIF) 지원.
# pillow-heif가 설치되어 있으면 Pillow의 Image.open()/save()에 HEIC/HEIF
# 플러그인을 등록한다 — 이후로는 코드 전체에서 이미 쓰고 있는 Image.open(path)
# 호출들이 별도 분기 없이 .heic/.heif 파일도 그대로 열게 된다(썸네일 로더,
# 이미지 편집 모드의 열기/저장 로직 등 모두 자동으로 지원됨). 등록 위치를
# 이 파일로 잡은 이유: styles.py는 거의 모든 다른 모듈이 가장 먼저
# import하는 공통 기반 모듈이라, 어떤 진입점으로 실행하든(FolderKit.py를
# 통한 실제 실행이든, 특정 모듈만 따로 불러오는 테스트/스크립트든) 실제
# 이미지를 열기 전에 이 등록이 항상 먼저 끝나 있음을 보장할 수 있다.
# 설치되어 있지 않으면 조용히 건너뛴다 — HEIC 파일은 다른 미지원 확장자와
# 동일하게 "열 수 없는 이미지"로 처리될 뿐, 프로그램 자체는 정상 동작한다.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

# =============================================================================
# 0. 고정 색상 팔레트 (테마 독립) — 어떤 OS 테마에서도 동일하게 표시
# =============================================================================
class C:
    WINDOW_BG   = "#f4f5f7"   # 전체 창 배경
    WINDOW_FG   = "#1a1a1a"   # 기본 글자색
    BORDER      = "#c4c9d0"

    # 좌/우 구분 색
    LEFT_MAIN   = "#2196F3"   # 좌: 파랑
    LEFT_BG     = "#eaf2fd"   # 좌 트리 배경(옅은 파랑)
    LEFT_SELFG  = "#08488c"   # 좌 선택 폴더 강조 글자색
    RIGHT_MAIN  = "#2e9e44"   # 우: 초록
    RIGHT_BG    = "#eafaef"   # 우 트리 배경(옅은 초록)
    RIGHT_SELFG = "#155d27"   # 우 선택 폴더 강조 글자색

    TREE_FG     = "#1a1a1a"   # 트리 일반 글자색(항상 검정 계열)
    SEL_FG      = "#ffffff"   # 선택 행 글자색

    BTN_COPY_BG = "#607d8b"   # 구조복사 버튼
    BTN_SYNC_BG = "#2196F3"   # 동기화 버튼
    BTN_TOOL_BG = "#4CAF50"   # 상단 툴 버튼
    BTN_SET_BG  = "#546e7a"   # 환경설정 버튼

    LOG_BG      = "#1e1e1e"
    LOG_FG      = "#4CAF50"

    # [v04] 파일명 변경(리네임) 모드 전용 강조색 — 좌(파랑)·우(초록)와 겹치지 않는
    # 제3의 톤을 사용해 "지금은 동기화가 아니라 리네임 모드"임을 한눈에 구분시킴.
    RENAME_MAIN   = "#e08e0b"   # 리네임 모드 강조(주황)
    RENAME_BG     = "#fff8ec"   # 리네임 에디터 배경(옅은 주황)
    RENAME_CHANGED = "#3264fa"  # 변경된 줄 글자색(파랑)
    RENAME_ERROR   = "#dc3232"  # 오류(빈 줄/특수문자) 줄 글자색(빨강)

    # [v05] 이미지 편집 모드 전용 강조색 — 좌(파랑)·리네임(주황)과 겹치지 않는 보라
    IMGEDIT_MAIN  = "#7c4dff"
    IMGEDIT_BG    = "#f3f0ff"
    CROP_LINE     = "#ff7a45"   # 크롭 테두리(점선)/핸들 색
    CROP_HANDLE_FILL = "#ffffff"

    # [v09] 중복 파일 찾기 모드 전용 강조색 — 기존 3색과 겹치지 않는 틸(teal)
    DUPFIND_MAIN  = "#00897b"
    DUPFIND_BG    = "#e8f5f3"
    # [v01] 유틸리티(Util) 모드 전용 강조색 — 기존 네 모드(파랑·주황·보라·틸)와
    # 겹치지 않고, 24px 배지에서도 뚜렷이 구분되는 자홍(라즈베리) 계열.
    # 파괴적 동작의 빨강(#d32f2f)과는 채도·색상이 충분히 달라 혼동되지 않는다.
    UTIL_MAIN     = "#c2185b"
    UTIL_BG       = "#fdeef4"

    # [v10] 함수 그래프의 x/y축 색 — 기존 회색(#9aa0a8)보다 훨씬 진하게 해서
    # 축과 격자선이 뚜렷이 구분되도록 했다(사용자 요청: 축을 진한 색으로).
    AXIS_STRONG   = "#37474f"

    # [v38] 빠른 스캔 버튼 강조색 — 정밀 스캔(틸)과 뚜렷이 구분되는 호박색.
    # "정밀은 신중한 톤, 빠른 쪽은 활동적인 톤"이라는 인상을 주도록 선택.
    DUPFIND_FAST  = "#f9a825"

# [v05] 이미지 편집 모드 상수
# [v42] .heic/.heif(아이폰 기본 사진 포맷) 추가 — pillow-heif가 설치되어
# 있을 때만 실제로 열린다(app.py의 register_heif_opener() 참고). 목록에는
# 항상 포함해 둔다 — 폴더 스캔 단계에서부터 대상으로 잡아야 하고, 만약
# pillow-heif가 없는 환경이라면 열기 시도 자체가 실패하며 기존과 동일하게
# "이미지 열기 실패" 로그로 처리된다(프로그램이 죽지 않음).
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif")
THUMB_SIZE = (72, 72)

# [v41] RATIO_KEYS/BASIS_KEYS는 콤보박스 표시 텍스트가 아니라 "내부적으로
# 저장되는 값"이다 — 크롭 상태(CropState.ratio)가 이 값을 그대로 저장해서
# 이미지마다 유지하고, image_edit.py의 로직도 이 값으로 분기한다("1:1",
# "4:3", "16:9"는 숫자 표기라 원래도 언어와 무관해 그대로 키로 쓴다).
# 예전에는 화면에 보이는 한국어 문구("원본 비율" 등) 자체를 그 값으로
# 저장했었는데, 그러면 언어를 바꾸는 순간 이미 저장해 둔 값과 새로 표시할
# 문구가 어긋나 버린다. 그래서 "키"와 "화면에 보일 문구"를 분리했다 —
# 저장은 키로, 화면 표시는 아래 ratio_label()/basis_label()로 매번 새로
# 계산한다(언어 전환 시 콤보 아이템 텍스트만 갱신하면 저장된 키는 그대로
# 유효하다).
RATIO_KEYS = ["original", "1:1", "4:3", "16:9", "free"]
BASIS_KEYS = ["long_edge", "short_edge", "pixel"]


def ratio_label(key):
    """RATIO_KEYS의 한 값을 현재 언어의 화면 표시 문구로 변환."""
    from .i18n import tr
    if key == "original":
        return tr("imgedit.ratio.original")
    if key == "free":
        return tr("imgedit.ratio.free")
    return key  # "1:1" / "4:3" / "16:9"는 언어와 무관하므로 그대로


def basis_label(key):
    from .i18n import tr
    return tr({"long_edge": "imgedit.basis.long_edge",
               "short_edge": "imgedit.basis.short_edge",
               "pixel": "imgedit.basis.pixel"}.get(key, key))


EDGE_TOL = 8
HANDLE_R = 5

# [v10] 파일/폴더 구분 아이콘은 이모지 대신 코드로 그리는 벡터 아이콘으로 통일(모드 아이콘과 톤 일치)
GUTTER_ICON_COLOR = "#6b7280"

EXCLUDE_PATTERNS = ["~$*", "*.tmp", ".DS_Store", "Thumbs.db", "desktop.ini",
                    "_sync_backup", "*.swp"]


def is_excluded(name: str) -> bool:
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


# [v48] 윈도우 탐색기는 기본 설정에서 "숨김"·"시스템" 속성이 붙은 항목을
# 화면에 보여주지 않는다(예: $RECYCLE.BIN, System Volume Information).
# 이전에는 FolderKit의 여러 화면(파일명 변경 목록, 동기화/구조복사/중복
# 찾기의 폴더 스캔, 구조 텍스트 보기)이 이름 패턴(EXCLUDE_PATTERNS)만
# 검사하고 이 속성은 전혀 확인하지 않아서, 탐색기에는 안 보이는 이런
# OS 보호 폴더가 FolderKit에는 그대로 나타나거나 동기화/스캔 대상에
# 끼어드는 문제가 있었다. 이 함수는 그 속성을 확인해 탐색기와 동일하게
# 걸러낼 수 있게 해 준다.
#
# os.scandir()이 돌려주는 os.DirEntry를 넘기면 스캔 시점에 이미 캐시된
# 정보를 그대로 쓰므로 추가 시스템 호출이 없다(빠름). 문자열 경로를
# 넘겨도 동작한다(os.listdir/os.walk 기반 코드용). 윈도우가 아닌
# 환경(맥/리눅스 — 개발 중 테스트 등)에는 이 속성 자체가 없으므로,
# 그때는 이름이 점(.)으로 시작하는 항목만 숨김으로 취급한다(맥/리눅스의
# 오래된 관례).
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
_UF_HIDDEN = 0x8000   # [v51] 맥 stat.UF_HIDDEN(파이썬 stat 모듈과 같은 값)


def is_hidden_or_system(entry_or_path) -> bool:
    try:
        st = entry_or_path.stat() if hasattr(entry_or_path, "stat") else os.stat(entry_or_path)
        attrs = getattr(st, "st_file_attributes", None)
        if attrs is not None:
            return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
        # [v51] 맥: Finder에서 숨긴 항목(chflags hidden — 예: ~/Library)
        if getattr(st, "st_flags", 0) & _UF_HIDDEN:
            return True
    except OSError:
        pass
    name = entry_or_path.name if hasattr(entry_or_path, "name") \
        else os.path.basename(str(entry_or_path).rstrip("/\\"))
    return name.startswith(".")


# =============================================================================
# 0.5 버튼 활성/비활성 공통 스타일 시스템 [v51]
# =============================================================================
# 예전에는 버튼마다 setStyleSheet()에 background-color/color를 직접 박아
# 넣어서, setEnabled(False)를 호출해도 Qt가 원래 자동으로 넣어주는
# "흐려지는" 효과가 완전히 가려지는 문제가 있었다 — 비활성 버튼이 활성
# 버튼과 똑같아 보였다. button_style()을 거치는 모든 버튼은 카테고리·색과
# 무관하게 비활성일 때 항상 이 톤 하나로 통일된다.
BTN_DISABLED_BG = "#dfe3e8"   # 비활성 배경 — 연한 무채색
BTN_DISABLED_FG = "#a3a9b3"   # 비활성 글자 — 흐린 회색

# 기능별 카테고리 색상(활성 상태). 각 모드의 주 실행 버튼은 그 모드
# 강조색(C.BTN_SYNC_BG, C.RENAME_MAIN, C.IMGEDIT_MAIN, C.DUPFIND_FAST 등)을
# 그대로 쓰고, 아래 세 값은 "모드와 무관하게 항상 같은 뜻"을 갖는 색이다.
BTN_NEUTRAL_BG = "#546e7a"      # 취소·전체 폴더 해제·환경설정 등 모드 무관 유틸리티
BTN_SECONDARY_SLATE = "#607d8b"  # 구조 복사/이동/복사 등 슬레이트 계열 보조 동작
BTN_DESTRUCTIVE_BG = "#d32f2f"   # 삭제 등 파괴적 동작


def button_style(bg, fg="#ffffff", *, bold=True, font_size=None, radius=5,
                  padding=None, extra=""):
    """[v51] 버튼 스타일시트를 한 곳에서 만든다 — 모든 버튼이 이 함수를
    거치게 하면, 개별 버튼마다 :disabled 규칙을 따로 챙기지 않아도 항상
    빠짐없이 붙는다. extra에는 :hover 등 추가 규칙을 그대로 문자열로
    넘기면 된다(예: "QPushButton:hover{background-color:#3f5560;}")."""
    weight = "font-weight:bold;" if bold else "font-weight:normal;"
    fs = f"font-size:{font_size}px;" if font_size else ""
    pad = f"padding:{padding};" if padding else ""
    return (
        f"QPushButton{{background-color:{bg};color:{fg};{weight}{fs}{pad}"
        f"border-radius:{radius}px;border:none;}}"
        f"QPushButton:disabled{{background-color:{BTN_DISABLED_BG};"
        f"color:{BTN_DISABLED_FG};font-weight:normal;}}"
        f"{extra}"
    )


def FLAT_INPUT_STYLE(accent: str) -> str:
    """[v33] 모드별 액션 바 안에 놓인 QLineEdit/QComboBox용 공통 스타일.
    Qt 기본(Fusion) 스타일은 이런 입력창에 진회색 테두리를 그리는데, 이게
    액션 바 자체의 둥근 테두리와 가까이 붙어 있으면 "테두리 안에 또 테두리"
    처럼 겹쳐 보였다. 평소엔 테두리를 투명하게 감춰두고, 포커스가 있을 때만
    그 모드의 강조색으로 살짝 보이게 해 불필요한 시각적 잡음을 없앤다."""
    return (
        f"QLineEdit, QComboBox {{"
        f"background-color:#ffffff; border:1px solid transparent;"
        f"border-radius:5px; padding:0 8px;}}"
        f"QLineEdit:focus, QComboBox:focus, QComboBox:on {{"
        f"border:1px solid {accent};}}"
        f"QComboBox::drop-down {{border:none; width:20px;}}"
    )
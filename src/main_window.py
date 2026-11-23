# -*- coding: utf-8 -*-
"""
FolderKit — 메인 윈도우

[v22] UI 통일 리디자인 1단계(콘셉 A: 탐색기 리본):
  모드별 액션 바(action_bar_frame — 내용은 모드마다 다르지만 패널 높이·
  톤 배경은 통일된 컴포넌트), 콘솔 로그(접이식, 4개 모드 공통).

[v23] UI 통일 리디자인 2단계(콘셉 B: 좌측 액티비티 바):
  모드 세그먼트를 상단에서 좌측 트리 옆 세로 아이콘 바(activity_bar)로 이동해
  "좌측 폴더 트리가 기준"이라는 콘셉을 시각적으로 강화. 환경 설정도 액티비티
  바 하단에 아이콘으로 포함. 새로고침 버튼은 화면에서 제거하고 F5 단축키로만
  동작(요청 반영).

  좌측 폴더 트리 · 콘솔 로그 · 상태바 · 히스토리 콤보를 모든 모드가 공유하고,
  우측 패널 · 하단 실행 버튼만 모드별로 교체되는 4-way 세그먼트 구조.
  (동기화 모드 / 파일명 변경 모드 / 이미지 편집 모드 / 중복 파일 찾기 모드)
"""
import os
import re
import time
import shutil
import sys
import subprocess
import unicodedata
from collections import Counter

from PySide6.QtCore import QEventLoop, QCoreApplication
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, QTimer, QSize, QPoint, QEvent
)
from PySide6.QtGui import (
    QIcon, QFont, QFontMetrics, QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QCheckBox, QFrame, QComboBox,
    QListView, QTreeView, QTableView, QTextEdit, QFileDialog,
    QMessageBox, QAbstractItemView, QStatusBar, QMenu, QInputDialog,
    QStackedWidget, QProgressBar, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QButtonGroup, QScrollArea, QHeaderView, QStyledItemDelegate, QStyleOptionViewItem
)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from send2trash import send2trash
    _HAS_SEND2TRASH = True
except ImportError:
    _HAS_SEND2TRASH = False

from .paths import ICON_PATH
from .styles import (
    C, APP_VERSION, IMAGE_EXTS, THUMB_SIZE, RATIO_KEYS, BASIS_KEYS,
    ratio_label, basis_label, is_excluded, is_hidden_or_system, FLAT_INPUT_STYLE, HEIF_SUPPORT,
    button_style, BTN_NEUTRAL_BG, BTN_SECONDARY_SLATE, BTN_DESTRUCTIVE_BG, BTN_DISABLED_BG
)
from .config import Config, HistoryManager
from .i18n import tr, set_language, get_language, TR
from .sync_core import ScanThread, SyncThread, plan_actions, CONFLICT, SAME, ONLY_L, ONLY_R
from .fs_model import DirOnlyModel, TreeDelegate
from .rename_widgets import auto_number_duplicates, CodeEditor
from .dialogs import SettingsDialog, PreviewDialog
from .common_widgets import BusyOverlay
from .duplicate_finder import DuplicateScanThread, DuplicatePreviewPopover
from .ext_finder import ExtFindThread, FileHit, normalize_ext
from .chip_input import ChipInputWidget
from .image_io import open_oriented, save_keeping_exif, thumbnail_oriented
from .photo_album_panel import (AlbumPanel, event_title, person_title,
                                KIND_EVENT, KIND_PERSON, KIND_MINOR)
from .image_edit import (
    ImageState, CropCanvas, CurvePopover, make_mode_icon, make_quicklink_icon,
    apply_curve_to_image
)

# [v47] 즐겨찾기 바로가기 중 탐색기풍 전용 글리프가 있는 6가지 종류(바탕화면/
# 다운로드/문서/사진/음악/동영상). 이 목록 밖의 항목(메신저 폴더, 사용자가
# 직접 추가한 항목)은 전부 FolderKit 앱 아이콘("custom")을 붙인다.
QUICKLINK_SYSTEM_KINDS = ("desktop", "downloads", "documents", "pictures", "music", "videos")
from .thumbnail_loader import (
    ThumbnailLoaderWorker, ThumbnailCache, ThumbnailLoaderMixin
)
# [v01] Util 모드(미니앱 모음). 개별 도구는 여기서 import하지 않는다 —
# 레지스트리(src/utils/__init__.py)만 알고 있으면 되고, 도구가 늘어도 이
# import 줄은 그대로다.
from .utils import build_apps, category_label, CATEGORY_ORDER, UtilHost
from .platform_info import app_available, mono_font, MONO_CSS
from .utils.panel import UtilPanel


class _ElideLeftDelegate(QStyledItemDelegate):
    """[v44.7] 칸 폭보다 긴 텍스트를 뒤(오른쪽)가 아니라 **앞(왼쪽)을**
    "..."으로 줄인다 — 파일 찾기(확장자로 찾기) 결과 표의 "경로" 칸에
    쓴다. 기본 동작(뒤를 자름)으로는 "C:\\사용자\\...\\깊은폴더"에서
    앞쪽 "C:\\사용자\\" 같은 공통·안 중요한 부분만 남고, 정작 필요한
    "그 파일이 실제로 든 폴더"(가장 뒤쪽)가 통째로 안 보이는 문제가
    있었다. 앞을 자르면 항상 뒤쪽(깊은 경로)이 보인다. 전체 경로는
    여전히 툴팁으로 확인할 수 있다.

    [버그 수정] textElideMode만 바꾸면 경로에 있는 "/" 때문에 Qt가 이걸
    줄바꿈 가능한 단어 경계로 보고, 칸이 좁을 때 생략(...) 대신 **두
    줄로 줄바꿈**해 버렸다(그러면서 행 높이까지 늘어났다). 줄바꿈
    기능(WrapText) 자체를 꺼서 항상 한 줄로, 생략 기호로만 줄게 한다."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.textElideMode = Qt.ElideLeft
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.WrapText


IMGEDIT_VIEW_FOLDER = "folder"   # [v48] 이미지 편집 왼쪽 패널: 폴더 트리
IMGEDIT_VIEW_ALBUM = "album"     # [v48] 이미지 편집 왼쪽 패널: 사진첩



def explorer_command(path, is_dir):
    """[v50.1] 윈도 탐색기 명령 문자열 — 폴더는 그 안을 새 창으로(/n,),
    파일은 부모 폴더를 열고 그 파일을 선택(/select,). 따옴표는 경로에만.
    [v51] 맥(Finder)·리눅스 명령은 platform_info.file_manager_command()."""
    return f'explorer /n,"{path}"' if is_dir else f'explorer /select,"{path}"'

LOG_MAX_LINES = 5000  # [v50] 콘솔 로그 최대 줄 수


class MainWindow(QMainWindow, ThumbnailLoaderMixin):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        set_language(self.cfg.language)  # [v25] UI를 만들기 전에 언어부터 확정
        self.history = HistoryManager()
        self.source_path = None
        self.dest_path = None
        # [v04] 현재 화면 모드: "sync"(폴더 동기화, 기본) / "rename"(파일명 변경) / [v05] "imgedit"(이미지 편집)
        self.mode = "sync"
        self.rename_loaded_dir = ""   # 리네임 에디터에 현재 로드되어 있는 폴더
        # [v05] 리네임 모드: 원본 항목(이름, 폴더 여부) — 파일 목록 다음 서브 폴더 목록 순서로 저장
        self.rename_entries = []      # [(name, is_dir), ...]

        # [v05] 이미지 편집 모드 상태
        self.imgedit_loaded_dir = ""
        self.imgedit_files = []                # 현재 폴더의 이미지 경로 목록
        self.imgedit_states = {}               # path -> ImageState
        self.imgedit_current = -1              # 현재 선택된 이미지 인덱스
        self.imgedit_pending_action = None      # None / "move" / "copy" (M/C로 대상 폴더 선택 중)
        self.imgedit_last_target = {"move": None, "copy": None}
        self.imgedit_curve_popover = None
        # [v48] 왼쪽 패널이 무엇을 보여 주는지 — 내부 키("folder"/"album")
        self.imgedit_view_kind = IMGEDIT_VIEW_FOLDER
        self.imgedit_album_title = ""          # 사진첩에서 연 행사의 이름(상태 줄 앞에 붙인다)

        # [v09] 중복 파일 찾기 모드 상태
        self.dupfind_targets = []              # [v10] 검사 대상 폴더 목록(다중 등록)
        self.dupfind_thread = None
        self.dupfind_groups = []               # list[DuplicateGroup]
        self.dupfind_mode_label = ""           # [v38] 오버레이/로그에 쓸 "정밀/빠른 스캔 중…" 문구
        self._dupfind_verify_source_groups = []  # [v49] 정밀 재검사 시작 시점의 후보(비교용 로그)
        self._dupfind_last_logged_pct = -1     # [v38] 콘솔 로그를 1%당 한 번으로 제한

        # [v44.3] "파일 찾기" 모드의 두 번째 기능 — 확장자로 찾기. 폴더
        # 등록(dupfind_targets)은 중복 찾기와 그대로 공유한다(한 번
        # 등록해 두면 두 기능 다 그 폴더를 검사 대상으로 쓴다).
        self.find_submode = "dup"              # "dup" | "ext" — 지금 보이는 하위 기능
        self.extfind_thread = None
        self.extfind_hits = []                 # list[FileHit]
        self.extfind_extensions = []           # 지금 칩으로 걸려 있는 확장자(표시 순서 유지용)
        self._extfind_sort_key = "size"
        self._extfind_sort_dir = -1            # -1 내림차순, 1 오름차순

        # [v38] 스캔 중 Esc → 일시정지 후 중단 여부 확인. 스캔이 실행 중일 때만
        # 활성화된다(다른 모드의 Esc 동작과 겹치지 않도록 평소엔 꺼둠).
        self.dupfind_esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.dupfind_esc_shortcut.setContext(Qt.ApplicationShortcut)
        self.dupfind_esc_shortcut.setEnabled(False)
        self.dupfind_esc_shortcut.activated.connect(self.on_dupfind_escape_pressed)

        # [v43.9] 갤럭시폰 사진 옮기기처럼 일반적이지 않은 도구는 평소
        # 도구 목록·홈 화면·최근 사용 어디에도 안 보이게 숨겨 두고(각
        # 도구의 hidden=True), 이 단축키를 눌렀을 때만 Util 모드로
        # 전환하면서 바로 연다. self(MainWindow)에 매달아 둔다 — 항상
        # 화면에 떠 있는 실제 창이라, 다른 위젯에 매달았다가 "화면
        # 트리에 없는 고아 위젯이라 단축키가 안 먹는" 문제를 다시 겪지
        # 않는다(인증키 채우기 단축키에서 실제로 있었던 버그).
        self.hidden_tool_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F9"), self)
        if not app_available("phonetransfer"):     # [v51] 맥엔 갤럭시폰 사진 옮기기가 없음
            self.hidden_tool_shortcut.setEnabled(False)
        self.hidden_tool_shortcut.setContext(Qt.ApplicationShortcut)
        self.hidden_tool_shortcut.activated.connect(self._reveal_hidden_tool)

        # [v37] 썸네일 로더 초기화 (비동기 로딩)
        self.init_thumbnail_loader()

        self.setWindowTitle(tr("app.title", version=APP_VERSION))
        self.resize(1280, 780)
        self.setStyleSheet(f"QMainWindow{{background-color:{C.WINDOW_BG};}}")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setup_ui()

    # ---------- [v04] 상단 도구 영역 빌더 ----------
    def _build_sync_tools(self):
        """동기화 모드의 상단 도구 행: 구조 보기/저장 버튼 + 최근 작업 히스토리."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.btn_view = QPushButton(tr("sync.btn_view"))
        self.btn_save = QPushButton(tr("sync.btn_save"))
        self.btn_view.setToolTip(tr("sync.btn_view.tip"))
        self.btn_save.setToolTip(tr("sync.btn_save.tip"))
        for b in (self.btn_view, self.btn_save):
            b.setFixedHeight(34)
            b.setStyleSheet(button_style(C.BTN_TOOL_BG, padding="0 14px"))
            lay.addWidget(b)
        lay.addStretch()

        # 최근 작업 히스토리 콤보박스
        self.combo_history = QComboBox()
        self.combo_history.setFixedHeight(34)
        self.combo_history.setMinimumWidth(260)
        self.combo_history.setView(QListView())
        self.combo_history.setToolTip(tr("sync.combo_history.tip"))
        self.combo_history.setStyleSheet(
            "QComboBox{"
            "background-color:#ffffff;"
            f"color:{C.WINDOW_FG};"
            f"border:1px solid {C.BORDER};"
            "border-radius:6px;"
            "padding:0 30px 0 12px;"
            "font-weight:600;"
            "}"
            f"QComboBox:hover{{border:1px solid {C.BTN_SET_BG};}}"
            "QComboBox::drop-down{"
            "subcontrol-origin:padding;subcontrol-position:top right;"
            "width:28px;border:none;background:transparent;"
            "}"
            "QComboBox::down-arrow{"
            "width:0;height:0;"
            "border-left:5px solid transparent;"
            "border-right:5px solid transparent;"
            f"border-top:6px solid {C.BTN_SET_BG};"
            "margin-right:10px;"
            "}"
            "QComboBox QAbstractItemView{"
            "background-color:#ffffff;"
            f"color:{C.WINDOW_FG};"
            f"border:1px solid {C.BORDER};"
            "border-radius:6px;"
            "padding:4px;"
            "outline:0;"
            f"selection-background-color:{C.BTN_SET_BG};"
            "selection-color:#ffffff;"
            "}")
        lay.addWidget(self.combo_history)

        self.btn_view.clicked.connect(self.show_tree_text)
        self.btn_save.clicked.connect(self.save_tree_text)
        return w

    def _build_rename_tools(self):
        """[v04] 파일명 변경 모드의 상단 도구 행 — 구 FileRenamer 툴바 이식."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.lbl_find = QLabel(tr("rename.lbl_find"))
        lay.addWidget(self.lbl_find)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(tr("rename.find_input.placeholder"))
        self.find_input.setToolTip(tr("rename.find_input.tip"))
        self.find_input.setFixedWidth(120)
        self.find_input.setFixedHeight(34)
        self.find_input.setStyleSheet(FLAT_INPUT_STYLE(C.RENAME_MAIN))
        lay.addWidget(self.find_input)

        self.lbl_replace = QLabel(tr("rename.lbl_replace"))
        lay.addWidget(self.lbl_replace)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText(tr("rename.replace_input.placeholder"))
        self.replace_input.setToolTip(tr("rename.replace_input.tip"))
        self.replace_input.setFixedWidth(120)
        self.replace_input.setFixedHeight(34)
        self.replace_input.setStyleSheet(FLAT_INPUT_STYLE(C.RENAME_MAIN))
        lay.addWidget(self.replace_input)

        self.chk_regex = QCheckBox(tr("rename.chk_regex"))
        self.chk_regex.setToolTip(tr("rename.chk_regex.tip"))
        lay.addWidget(self.chk_regex)

        self.help_lbl = QLabel("❓")
        self.help_lbl.setCursor(Qt.PointingHandCursor)
        self.help_lbl.setStyleSheet(f"color:{C.RENAME_MAIN};font-weight:bold;font-size:15px;")
        self.help_lbl.setToolTip(tr("rename.help.tip"))
        lay.addWidget(self.help_lbl)

        self.btn_temp = QPushButton(tr("rename.btn_temp"))
        self.btn_temp.setToolTip(tr("rename.btn_temp.tip"))
        self.btn_temp.setFixedHeight(34)
        self.btn_temp.setStyleSheet(button_style("#78909c", padding="0 12px"))
        lay.addWidget(self.btn_temp)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)

        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText(tr("rename.prefix_input.placeholder"))
        self.prefix_input.setToolTip(tr("rename.prefix_input.tip"))
        self.prefix_input.setFixedWidth(130)
        self.prefix_input.setFixedHeight(34)
        self.prefix_input.setStyleSheet(FLAT_INPUT_STYLE(C.RENAME_MAIN))
        lay.addWidget(self.prefix_input)

        self.btn_prefix = QPushButton(tr("rename.btn_prefix"))
        self.btn_prefix.setToolTip(tr("rename.btn_prefix.tip"))
        self.btn_prefix.setFixedHeight(34)
        self.btn_prefix.setStyleSheet(button_style("#78909c", padding="0 12px"))
        lay.addWidget(self.btn_prefix)

        line2 = QFrame()
        line2.setFrameShape(QFrame.VLine)
        line2.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line2)

        # [v36] 맥에서 만든 파일이 자모가 분리된 상태(예: ㄱ+ㅏ 따로)로 저장돼
        # 있어서, 탐색기에서는 글자가 깨져 보이지만 FolderKit에서는 멀쩡하게
        # 보여 "고칠 게 없어 보이는" 문제를 해결하는 버튼.
        self.btn_normalize = QPushButton(tr("rename.btn_normalize"))
        self.btn_normalize.setToolTip(tr("rename.btn_normalize.tip"))
        self.btn_normalize.setFixedHeight(34)
        self.btn_normalize.setStyleSheet(button_style("#8e6b3f", padding="0 12px"))
        lay.addWidget(self.btn_normalize)
        lay.addStretch()

        self.btn_temp.clicked.connect(self.on_rename_find_replace)
        self.btn_prefix.clicked.connect(self.on_rename_add_prefix)
        self.btn_normalize.clicked.connect(self.on_rename_normalize_unicode)
        return w

    def _build_rename_editor(self):
        """[v04] 리네임 모드 우측 패널: 트리 헤더와 같은 문법의 헤더 바 + 파일명 에디터.
        테두리를 좌(파랑)·우(초록)와 겹치지 않는 주황으로 둬서 모드 구분이 명확하도록 함."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.rename_header = QLabel(tr("rename.header.idle"))
        self.rename_header.setFixedHeight(24)
        self.rename_header.setStyleSheet(
            f"background-color:{C.RENAME_MAIN};color:#ffffff;"
            f"font-weight:bold;padding:0 10px;")
        lay.addWidget(self.rename_header)

        self.editor = CodeEditor()
        self.editor.columnModeChanged.connect(self._on_rename_column_mode)
        font = mono_font(11)            # [v51] 맥엔 Consolas가 없어 Menlo로
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.editor.setStyleSheet(
            f"QPlainTextEdit{{background-color:{C.RENAME_BG};color:{C.WINDOW_FG};"
            f"border:2px solid {C.RENAME_MAIN};border-top:none;}}")
        lay.addWidget(self.editor, 1)
        return w

    def _on_rename_column_mode(self, lines):
        """[v49.3] 세로 선택 중이면 아래 상태 줄에 안내."""
        if lines:
            self.status.showMessage(tr("rename.column.status", a0=lines))
        else:
            self.status.clearMessage()

    # ---------- [v05] 이미지 편집 모드 빌더 ----------
    def _build_imgedit_tools(self):
        """이미지 편집 모드 상단 도구 행 — 크롭 비율/기준 콤보 + 커브 버튼.
        (계획서 확정: 밝기·회전 슬라이더는 제외)"""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.lbl_ratio = QLabel(tr("imgedit.lbl_ratio"))
        lay.addWidget(self.lbl_ratio)
        self.combo_ratio = QComboBox()
        for key in RATIO_KEYS:
            self.combo_ratio.addItem(ratio_label(key), key)
        self.combo_ratio.setFixedHeight(34)
        self.combo_ratio.setToolTip(tr("imgedit.combo_ratio.tip"))
        self.combo_ratio.setStyleSheet(FLAT_INPUT_STYLE(C.IMGEDIT_MAIN))
        self.combo_ratio.currentIndexChanged.connect(self.on_imgedit_ratio_changed)
        lay.addWidget(self.combo_ratio)

        self.lbl_basis = QLabel(tr("imgedit.lbl_basis"))
        lay.addWidget(self.lbl_basis)
        self.combo_basis = QComboBox()
        for key in BASIS_KEYS:
            self.combo_basis.addItem(basis_label(key), key)
        self.combo_basis.setFixedHeight(34)
        self.combo_basis.setToolTip(tr("imgedit.combo_basis.tip"))
        self.combo_basis.setStyleSheet(FLAT_INPUT_STYLE(C.IMGEDIT_MAIN))
        lay.addWidget(self.combo_basis)

        self.btn_curve = QPushButton(tr("imgedit.btn_curve"))
        self.btn_curve.setToolTip(tr("imgedit.btn_curve.tip"))
        self.btn_curve.setFixedHeight(34)
        self.btn_curve.setStyleSheet(button_style(C.IMGEDIT_MAIN, padding="0 14px"))
        self.btn_curve.clicked.connect(self.on_imgedit_open_curve)
        lay.addWidget(self.btn_curve)

        lay.addStretch()
        self.imgedit_status_lbl = QLabel("")
        self.imgedit_status_lbl.setStyleSheet(f"color:{C.IMGEDIT_MAIN};font-weight:bold;")
        lay.addWidget(self.imgedit_status_lbl)
        return w

    def _build_imgedit_dest_tree(self):
        """[v05] M/C 단축키용 대상 폴더 트리(동기화 모드 우측 트리와 별개 인스턴스로 재사용)."""
        self.model_imgedit_dest = self._make_model("I")
        self.tree_imgedit_dest = self._make_tree(
            "I", self.model_imgedit_dest, C.IMGEDIT_BG, C.IMGEDIT_MAIN,
            lambda: getattr(self, "imgedit_dest_path", None))
        self.tree_imgedit_dest.clicked.connect(self.on_imgedit_dest_clicked)
        self.tree_imgedit_dest.doubleClicked.connect(lambda idx: self.on_imgedit_dest_confirm())
        self.tree_imgedit_dest.customContextMenuRequested.disconnect()
        self.tree_imgedit_dest.customContextMenuRequested.connect(self.show_imgedit_dest_context_menu)
        self.imgedit_dest_path = None

        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.imgedit_dest_hint = QLabel("")
        self.imgedit_dest_hint.setStyleSheet(
            f"background-color:{C.IMGEDIT_MAIN};color:#ffffff;"
            f"font-weight:bold;padding:6px 10px;border-radius:5px;")
        lay.addWidget(self.imgedit_dest_hint)
        lay.addWidget(self.tree_imgedit_dest, 1)
        return wrap

    def _build_imgedit_layout(self):
        """[v11] 이미지 편집 모드 전용 레이아웃.
        기존에는 좌측 트리가 세로 전체를 차지하고 우측에 미리보기+썸네일이 있어
        "트리가 썸네일 영역을 뚫고 지나가는" 것처럼 어색해 보였다는 피드백을 반영해,
        먼저 상하로 나누고(위: 좌우 분할된 트리|뷰어, 아래: 썸네일+정보바 전체 폭)
        구조를 바꾼다.

            ┌─────────────┬─────────────────────┐
            │  좌측 트리   │   이미지 뷰어(테두리)  │   ← imgedit_hsplit(수평, 20:80)
            ├─────────────┴─────────────────────┤  ← hsplit 핸들과 동일한 간격
            │        썸네일 스트립 + 정보 바        │     (고정 높이 — 남는 공간은 전부 위쪽 뷰어가 흡수)
            └─────────────────────────────────────┘

        좌측 트리(tree_source)는 다른 모드와 공유하는 위젯이라, 모드 전환 시
        _ensure_tree_source_parent()가 이 위젯 트리 안으로 옮겨 붙인다.

        [v14] 하단 영역(썸네일+정보 바)은 더 이상 QSplitter로 위쪽과 비율 배분하지
        않는다 — 필요한 만큼만 고정 높이로 차지하게 하고, 창 크기가 커져도 그 여분은
        전부 위쪽 뷰어 영역이 가져가도록 해서 "썸네일 위에 불필요한 빈 공간"이 생기지
        않게 한다. 위·아래 사이 간격도 hsplit의 핸들 폭과 동일하게 맞춘다.
        """
        HANDLE_W = 4  # 트리|뷰어 사이 간격과 동일하게 유지할 기준값

        # ---- 뷰어 영역(크롭 캔버스 ↔ 이동/복사 대상 트리) ----
        self.crop_canvas = CropCanvas()
        self.crop_canvas.cropChanged.connect(self.on_imgedit_crop_changed)
        # [v11] "테두리가 있어야 안정적으로 보인다" — 이미지 뷰어에 테두리 추가
        self.crop_canvas.setStyleSheet(
            f"background-color:{C.IMGEDIT_BG};border:2px solid {C.IMGEDIT_MAIN};border-radius:6px;")

        self.imgedit_viewer_stack = QStackedWidget()
        self.imgedit_viewer_stack.addWidget(self.crop_canvas)                    # index 0: 뷰어
        self.imgedit_viewer_stack.addWidget(self._build_imgedit_dest_tree())     # index 1: 이동/복사 대상 트리

        self.imgedit_hsplit = QSplitter(Qt.Horizontal)
        self.imgedit_hsplit.setHandleWidth(HANDLE_W)
        self.imgedit_hsplit.addWidget(self._build_imgedit_left())   # [v48] [폴더 | 사진첩] + 스택
        self.imgedit_hsplit.addWidget(self.imgedit_viewer_stack)

        # [v16] M/C/Esc 단축키는 이미지 편집 영역 전체(container)를 기준으로 아래쪽에서
        # 등록한다 — 이전에는 imgedit_viewer_stack에만 등록되어 있어서, 썸네일 목록처럼
        # 다른 위젯에 포커스가 가 있을 때(가장 흔한 상황) 단축키가 먹지 않는 회귀
        # 버그가 있었다(Space/Ctrl+S 등도 v14에서 같은 이유로 한 번 고친 적이 있음).
        QShortcut(QKeySequence(Qt.Key_Return), self.tree_imgedit_dest,
                  activated=self.on_imgedit_dest_confirm, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence(Qt.Key_Enter), self.tree_imgedit_dest,
                  activated=self.on_imgedit_dest_confirm, context=Qt.WidgetShortcut)

        # ---- 하단: 썸네일 스트립 + 정보 바(전체 폭, 고정 높이) ----
        bottom_wrap = QWidget()
        v = QVBoxLayout(bottom_wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        # [v14] 항목 크기를 정확히 고정해, 세로 스크롤바 없이 가로 스크롤바만 생기도록 함
        GRID_W = THUMB_SIZE[0] + 16
        GRID_H = THUMB_SIZE[1] + 24
        THUMB_LIST_H = GRID_H + 18  # 가로 스크롤바가 나타나도 잘리지 않도록 여유분 확보

        self.thumb_list = QListWidget()
        self.thumb_list.setViewMode(QListWidget.IconMode)
        self.thumb_list.setIconSize(QSize(*THUMB_SIZE))
        self.thumb_list.setFlow(QListWidget.LeftToRight)
        self.thumb_list.setWrapping(False)
        self.thumb_list.setWordWrap(True)
        self.thumb_list.setUniformItemSizes(True)   # [v12] 모든 항목을 동일 크기로 강제 → 파일명 위치 정렬
        self.thumb_list.setGridSize(QSize(GRID_W, GRID_H))
        self.thumb_list.setFixedHeight(THUMB_LIST_H)
        self.thumb_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)     # [v14] 세로 스크롤 금지
        self.thumb_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)    # 가로만 필요 시 표시
        self.thumb_list.setStyleSheet(
            f"QListWidget{{background-color:#ffffff;border:1px solid {C.BORDER};border-radius:5px;}}"
            f"QListWidget::item{{padding:3px;color:{C.WINDOW_FG};}}"
            f"QListWidget::item:selected{{border:2px solid {C.IMGEDIT_MAIN};border-radius:4px;"
            f"background-color:{C.IMGEDIT_BG};color:{C.WINDOW_FG};}}")
        self.thumb_list.currentRowChanged.connect(self.on_imgedit_thumb_selected)
        # [v48] 사진첩에서 연 행사라면 오른쪽 클릭으로 "다른 행사로 옮기기 / 새 행사로 분리"
        self.thumb_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumb_list.customContextMenuRequested.connect(self._on_thumb_context_menu)
        v.addWidget(self.thumb_list)

        # [v05] 정보 바: 이미지명 · 사이즈 · 용량 표시 + 소형 적용/저장/되돌리기/재실행 버튼
        # [v14] 요청에 따라 버튼 글자 크기는 앱 전반과 동일하게 원복하고(12px),
        # 대신 버튼 자체 높이만 줄여서 패널 전체 세로 크기를 압축한다.
        BTN_H = 22
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(6)
        self.imgedit_info_lbl = QLabel("")
        self.imgedit_info_lbl.setStyleSheet(f"color:{C.WINDOW_FG};font-size:12px;")
        info_row.addWidget(self.imgedit_info_lbl, 1)

        self.btn_imgedit_apply = QPushButton(tr("imgedit.btn_apply"))
        self.btn_imgedit_apply.setFixedSize(60, BTN_H)
        self.btn_imgedit_apply.setToolTip(tr("imgedit.btn_apply.tip"))
        self.btn_imgedit_apply.setStyleSheet(
            button_style(C.IMGEDIT_MAIN, font_size=12))
        self.btn_imgedit_apply.clicked.connect(self.on_imgedit_apply)
        info_row.addWidget(self.btn_imgedit_apply)

        self.btn_imgedit_save = QPushButton(tr("imgedit.btn_save"))
        self.btn_imgedit_save.setFixedSize(60, BTN_H)
        self.btn_imgedit_save.setToolTip(tr("imgedit.btn_save.tip"))
        self.btn_imgedit_save.setStyleSheet(
            button_style(C.IMGEDIT_MAIN, font_size=12))
        self.btn_imgedit_save.clicked.connect(self.on_imgedit_save)
        info_row.addWidget(self.btn_imgedit_save)

        # [v13] 되돌리기/재실행 버튼 — 확정 단축키: 되돌리기=Ctrl+Z, 재실행=Ctrl+Y
        self.btn_imgedit_undo = QPushButton(tr("imgedit.btn_undo"))
        self.btn_imgedit_undo.setFixedSize(68, BTN_H)
        self.btn_imgedit_undo.setToolTip(tr("imgedit.btn_undo.tip"))
        self.btn_imgedit_undo.setStyleSheet(
            button_style("#78909c", font_size=12))
        self.btn_imgedit_undo.clicked.connect(self.on_imgedit_undo)
        info_row.addWidget(self.btn_imgedit_undo)

        self.btn_imgedit_redo = QPushButton(tr("imgedit.btn_redo"))
        self.btn_imgedit_redo.setFixedSize(68, BTN_H)
        self.btn_imgedit_redo.setToolTip(tr("imgedit.btn_redo.tip"))
        self.btn_imgedit_redo.setStyleSheet(
            button_style("#78909c", font_size=12))
        self.btn_imgedit_redo.clicked.connect(self.on_imgedit_redo)
        info_row.addWidget(self.btn_imgedit_redo)

        # [v16] 이동/복사 버튼 — 단축키(M/C)와 동일한 동작을 버튼으로도 제공
        # [v51] 둘 다 "모드 보조 실행" 슬레이트 계열로 통일(예전엔 이동=남색,
        # 복사=중복찾기 모드의 틸을 그대로 빌려 써서 서로도, 다른 모드 색과도
        # 기준 없이 겹쳤었다).
        self.btn_imgedit_move = QPushButton(tr("imgedit.btn_move"))
        self.btn_imgedit_move.setFixedSize(50, BTN_H)
        self.btn_imgedit_move.setToolTip(tr("imgedit.btn_move.tip"))
        self.btn_imgedit_move.setStyleSheet(
            button_style(BTN_SECONDARY_SLATE, font_size=12))
        self.btn_imgedit_move.clicked.connect(lambda: self.imgedit_request_move_copy("move"))
        info_row.addWidget(self.btn_imgedit_move)

        self.btn_imgedit_copy = QPushButton(tr("imgedit.btn_copy"))
        self.btn_imgedit_copy.setFixedSize(50, BTN_H)
        self.btn_imgedit_copy.setToolTip(tr("imgedit.btn_copy.tip"))
        self.btn_imgedit_copy.setStyleSheet(
            button_style(BTN_SECONDARY_SLATE, font_size=12))
        self.btn_imgedit_copy.clicked.connect(lambda: self.imgedit_request_move_copy("copy"))
        info_row.addWidget(self.btn_imgedit_copy)

        # [v43] JPG 일괄 변환 — 현재 폴더 안의 JPG가 아닌 이미지들을 원본은
        # 그대로 둔 채 같은 폴더에 .jpg로 새로 만든다(예: 아이폰 HEIC 사진들).
        self.btn_imgedit_to_jpg = QPushButton(tr("imgedit.btn_to_jpg"))
        self.btn_imgedit_to_jpg.setFixedSize(78, BTN_H)
        self.btn_imgedit_to_jpg.setToolTip(tr("imgedit.btn_to_jpg.tip"))
        self.btn_imgedit_to_jpg.setStyleSheet(
            button_style("#6d4c41", font_size=12))
        self.btn_imgedit_to_jpg.clicked.connect(self.on_imgedit_convert_to_jpg)
        info_row.addWidget(self.btn_imgedit_to_jpg)

        v.addLayout(info_row)

        # [v14] 하단 영역을 정확히 필요한 높이로 고정 — 창을 늘려도 이 영역은 커지지 않고
        # 여분은 전부 위쪽 뷰어(imgedit_hsplit)로 간다. 그래서 "썸네일 위 여백"이 생기지 않는다.
        bottom_wrap.setFixedHeight(THUMB_LIST_H + 4 + BTN_H)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(HANDLE_W)  # 트리|뷰어 사이 간격과 동일하게
        outer.addWidget(self.imgedit_hsplit, 1)
        outer.addWidget(bottom_wrap, 0)
        self.imgedit_container = container

        # [v14] 단축키: 적용=Space, 저장=Ctrl+S, 되돌리기=Ctrl+Z, 재실행=Ctrl+Y
        # 이미지 편집 영역 전체(container)를 기준으로 등록해야, 좌측 트리나
        # 이미지 뷰어에 포커스가 있을 때도 단축키가 동작한다.
        QShortcut(QKeySequence(Qt.Key_Space), container,
                  activated=self.on_imgedit_apply, context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+S"), container,
                  activated=self.on_imgedit_save, context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+Z"), container,
                  activated=self.on_imgedit_undo, context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+Y"), container,
                  activated=self.on_imgedit_redo, context=Qt.WidgetWithChildrenShortcut)
        # [v16] M/C/Esc도 동일하게 container 기준으로 등록(회귀 버그 수정)
        QShortcut(QKeySequence("M"), container,
                  activated=lambda: self.imgedit_request_move_copy("move"),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("C"), container,
                  activated=lambda: self.imgedit_request_move_copy("copy"),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), container,
                  activated=self.imgedit_cancel_dest_select,
                  context=Qt.WidgetWithChildrenShortcut)
        # [v32] 커브 창을 바로 여는 단축키. 이미지 편집 모드에서 이미 쓰이는
        # Space/Ctrl+S/Ctrl+Z/Ctrl+Y/M/C/Esc와 겹치지 않는 단순한 키로 S를 선택.
        QShortcut(QKeySequence("S"), container,
                  activated=self.on_imgedit_open_curve,
                  context=Qt.WidgetWithChildrenShortcut)
        # [v47] Del 키로 현재 선택된 사진을 삭제(확인 팝업에서 예/Enter →
        # 휴지통으로 이동). 별도 버튼은 만들지 않고 단축키로만 제공.
        QShortcut(QKeySequence(Qt.Key_Delete), container,
                  activated=self.on_imgedit_delete_current,
                  context=Qt.WidgetWithChildrenShortcut)

        return container

    def _build_imgedit_actions(self):
        """[v05] 이미지 편집 모드에서는 bottom_stack 자체를 숨기므로(enter_imgedit_mode에서
        setVisible(False)) 인덱스 정렬용 빈 자리표시자만 반환한다. 실제 적용/저장 버튼은
        _build_imgedit_layout의 정보 바에 소형으로 배치되어 있다."""
        return QWidget()

    # ---------- [v09] 중복 파일 찾기 모드 (계획서 5단계) ----------
    def _build_dupfind_tools(self):
        """상단 도구 행 — [v44.3] "중복 찾기"와 "확장자로 찾기" 두 하위
        기능을 세그먼트 버튼으로 오가는 "파일 찾기" 모드의 툴바.
        [v10] 폴더 등록은 좌측 트리 우클릭 → '폴더 추가' 메뉴로 한다(여러
        개 등록 가능) — 이 목록(dupfind_targets)은 두 하위 기능이 공유한다."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # ---- 세그먼트: 중복 파일 찾기 / 확장자로 찾기 ----
        seg_row = QHBoxLayout()
        seg_row.setContentsMargins(0, 0, 0, 0)
        seg_row.setSpacing(0)
        self.findmode_group = QButtonGroup(w)
        self.btn_findmode_dup = QPushButton(tr("findmode.seg_dup"))
        self.btn_findmode_ext = QPushButton(tr("findmode.seg_ext"))
        for i, btn in enumerate((self.btn_findmode_dup, self.btn_findmode_ext)):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            self.findmode_group.addButton(btn, i)
            seg_row.addWidget(btn)
        self.btn_findmode_dup.setChecked(True)
        self._style_findmode_segment()
        self.findmode_group.idClicked.connect(self._on_findmode_selected)
        seg_row.addStretch()
        outer.addLayout(seg_row)

        # ---- 하위 툴바 두 개(스택으로 전환) ----
        self.findmode_toolbar_stack = QStackedWidget()
        self.findmode_toolbar_stack.addWidget(self._build_dupfind_tools_dup())
        self.findmode_toolbar_stack.addWidget(self._build_extfind_tools())
        outer.addWidget(self.findmode_toolbar_stack)
        return w

    def _style_findmode_segment(self):
        """[v44.3] 지금 켜진 세그먼트만 채색, 나머지는 흰 바탕 — 좌/우
        모드 아이콘과 같은 톤(테두리+글자색만 강조색, 켜진 쪽만 배경 채움)."""
        for btn in (self.btn_findmode_dup, self.btn_findmode_ext):
            on = btn.isChecked()
            btn.setStyleSheet(
                f"QPushButton{{background-color:{C.DUPFIND_MAIN if on else '#ffffff'};"
                f"color:{'#ffffff' if on else C.DUPFIND_MAIN};font-weight:bold;"
                f"border:1px solid {C.DUPFIND_MAIN};padding:0 14px;}}")

    def _on_findmode_selected(self, idx):
        """세그먼트 전환 — 툴바·결과 패널·하단 액션 행 세 스택을 함께 넘긴다."""
        self.find_submode = "dup" if idx == 0 else "ext"
        self._style_findmode_segment()
        self.findmode_toolbar_stack.setCurrentIndex(idx)
        self.findmode_result_stack.setCurrentIndex(idx)
        self.findmode_actions_stack.setCurrentIndex(idx)
        self.status.showMessage(
            tr("status.dupfind.no_targets_hint") if idx == 0 else tr("status.extfind.hint"))

    def _build_dupfind_tools_dup(self):
        """중복 찾기 하위 툴바 — 기존 내용 그대로."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.dupfind_path_lbl = QLabel("")
        self.dupfind_path_lbl.setStyleSheet(f"color:{C.WINDOW_FG};")
        lay.addWidget(self.dupfind_path_lbl, 1)

        self.btn_dupfind_clear = QPushButton(tr("dupfind.btn_clear"))
        self.btn_dupfind_clear.setToolTip(tr("dupfind.btn_clear.tip"))
        self.btn_dupfind_clear.setFixedHeight(34)
        self.btn_dupfind_clear.setStyleSheet(
            button_style(BTN_NEUTRAL_BG, padding="0 14px"))
        self.btn_dupfind_clear.clicked.connect(self.dupfind_clear_targets)
        lay.addWidget(self.btn_dupfind_clear)

        self.btn_dupfind_scan_precise = QPushButton(tr("dupfind.btn_scan_precise"))
        self.btn_dupfind_scan_precise.setToolTip(tr("dupfind.btn_scan_precise.tip"))
        self.btn_dupfind_scan_precise.setFixedHeight(34)
        self.btn_dupfind_scan_precise.setStyleSheet(
            button_style(C.DUPFIND_MAIN, padding="0 14px"))
        self.btn_dupfind_scan_precise.setEnabled(False)  # [v49] 빠른 스캔으로 후보를 찾기 전까지는 비활성화
        self.btn_dupfind_scan_precise.clicked.connect(self.on_dupfind_scan_precise_verify)
        lay.addWidget(self.btn_dupfind_scan_precise)

        self.btn_dupfind_scan_fast = QPushButton(tr("dupfind.btn_scan_fast"))
        self.btn_dupfind_scan_fast.setToolTip(tr("dupfind.btn_scan_fast.tip"))
        self.btn_dupfind_scan_fast.setFixedHeight(34)
        self.btn_dupfind_scan_fast.setStyleSheet(
            button_style(C.DUPFIND_FAST, padding="0 14px"))
        self.btn_dupfind_scan_fast.clicked.connect(
            lambda: self.on_dupfind_scan_start(strict=False))
        lay.addWidget(self.btn_dupfind_scan_fast)

        self.btn_dupfind_cancel = QPushButton(tr("dupfind.btn_cancel"))
        self.btn_dupfind_cancel.setToolTip(tr("dupfind.btn_cancel.tip"))
        self.btn_dupfind_cancel.setFixedHeight(34)
        self.btn_dupfind_cancel.setEnabled(False)
        self.btn_dupfind_cancel.setStyleSheet(
            button_style(BTN_NEUTRAL_BG, padding="0 14px"))
        self.btn_dupfind_cancel.clicked.connect(self.on_dupfind_scan_cancel)
        lay.addWidget(self.btn_dupfind_cancel)
        return w

    def _build_extfind_tools(self):
        """확장자로 찾기 하위 툴바 — 칩 입력 + 프리셋 버튼 + 검색/취소."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.extfind_chips = ChipInputWidget(
            accent_color=C.DUPFIND_MAIN,
            placeholder=tr("extfind.chip_placeholder"),
            normalize=normalize_ext)
        lay.addWidget(self.extfind_chips, 1)

        self.btn_extfind_preset_photo = QPushButton(tr("extfind.preset_photo"))
        self.btn_extfind_preset_doc = QPushButton(tr("extfind.preset_doc"))
        self.btn_extfind_preset_video = QPushButton(tr("extfind.preset_video"))
        self.btn_extfind_preset_exe = QPushButton(tr("extfind.preset_exe"))
        preset_specs = [
            (self.btn_extfind_preset_photo, [".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp"]),
            (self.btn_extfind_preset_doc, [".pdf", ".hwp", ".docx", ".xlsx", ".pptx", ".txt"]),
            (self.btn_extfind_preset_video, [".mp4", ".mov", ".avi", ".mkv", ".wmv"]),
            (self.btn_extfind_preset_exe, [".exe", ".msi", ".bat", ".cmd"]),
        ]
        for btn, exts in preset_specs:
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton{{background:#ffffff;color:{C.DUPFIND_MAIN};font-weight:bold;"
                f"border:1px solid {C.DUPFIND_MAIN};border-radius:5px;padding:0 10px;}}"
                f"QPushButton:hover{{background:{C.DUPFIND_BG};}}")
            btn.clicked.connect(lambda _=False, e=exts, b=btn: self._on_extfind_preset(e, b.text()))
            lay.addWidget(btn)

        self.btn_extfind_search = QPushButton(tr("extfind.btn_search"))
        self.btn_extfind_search.setToolTip(tr("extfind.btn_search.tip"))
        self.btn_extfind_search.setFixedHeight(34)
        self.btn_extfind_search.setStyleSheet(button_style(C.DUPFIND_MAIN, padding="0 14px"))
        self.btn_extfind_search.clicked.connect(self.on_extfind_search_start)
        lay.addWidget(self.btn_extfind_search)

        self.btn_extfind_cancel = QPushButton(tr("dupfind.btn_cancel"))
        self.btn_extfind_cancel.setFixedHeight(34)
        self.btn_extfind_cancel.setEnabled(False)
        self.btn_extfind_cancel.setStyleSheet(button_style(BTN_NEUTRAL_BG, padding="0 14px"))
        self.btn_extfind_cancel.clicked.connect(self.on_extfind_search_cancel)
        lay.addWidget(self.btn_extfind_cancel)
        return w

    def _on_extfind_preset(self, exts, label):
        for e in exts:
            self.extfind_chips.add(e)
        self._ensure_console_visible()
        self.logmsg(tr("log.extfind.preset_added", a0=label, a1=", ".join(exts)))

    def _build_dupfind_panel(self):
        """우측 패널 — [v44.3] 중복 찾기 결과(그룹 트리)와 확장자로 찾기
        결과(정렬 가능한 표)를 스택으로 전환한다."""
        self.findmode_result_stack = QStackedWidget()
        self.findmode_result_stack.addWidget(self._build_dupfind_tree())
        self.findmode_result_stack.addWidget(self._build_extfind_table())
        return self.findmode_result_stack

    def _build_dupfind_tree(self):
        """중복 그룹 목록(그룹 머리 줄 + 각 파일 경로에 체크박스).
        [v17] 이미지 파일이 속한 그룹 행에 마우스를 올려 잠시 대기하면, 그 그룹의
        이미지들을 나란히 보여주는 미리보기 팝오버가 뜬다(호버 해제 시 사라짐).
        [v50] 결과 39만 개에서 메모리 5.3GB·창 크기 바꿀 때 버벅임 — 줄마다 항목
        객체를 만들던 QTreeWidget을 "보이는 줄만 물어보는" 표 화면 + 모델
        (DupResultModel)로 바꿨다. 줄을 더블클릭하거나 오른쪽 클릭 →
        "탐색기에서 열기"로 그 파일 위치를 바로 연다."""
        from PySide6.QtGui import QColor
        from .dup_result_model import DupResultModel
        _mc = QColor(C.DUPFIND_MAIN)      # 그룹 머리 줄 배경 = 강조색을 흰색에 14%만 섞은 옅은 색
        _bg = QColor(round(255 - (255 - _mc.red()) * 0.14), round(255 - (255 - _mc.green()) * 0.14),
                     round(255 - (255 - _mc.blue()) * 0.14))
        self.dupfind_model = DupResultModel(self, size_formatter=self._fmt_size, group_bg=_bg)
        t = QTableView()
        self.dupfind_tree = t
        t.setModel(self.dupfind_model)
        vh = t.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.Fixed)       # 줄 높이 고정 = 보이는 줄만 계산
        vh.setDefaultSectionSize(max(20, t.fontMetrics().height() + 6))
        t.setShowGrid(False)
        t.setWordWrap(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        t.setTextElideMode(Qt.ElideMiddle)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setHighlightSections(False)
        t.setColumnWidth(0, 220)
        t.setColumnWidth(1, 420)
        t.setColumnWidth(2, 90)
        t.setStyleSheet(
            f"QTableView{{background-color:{C.DUPFIND_BG};color:{C.TREE_FG};"
            f"border:2px solid {C.DUPFIND_MAIN};border-radius:5px;}}")
        t.doubleClicked.connect(self._on_dupfind_double_clicked)
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._on_dupfind_context_menu)

        # [v17] 호버 미리보기: 마우스 이동을 직접 추적해 500ms 대기 후 팝오버 표시
        t.setMouseTracking(True)
        t.viewport().setMouseTracking(True)
        t.viewport().installEventFilter(self)
        self.dupfind_hover_timer = QTimer(self)
        self.dupfind_hover_timer.setSingleShot(True)
        self.dupfind_hover_timer.timeout.connect(self._show_dupfind_hover_popup)
        self._dupfind_hover_item = None     # [v50] 마우스가 올라간 그룹 번호(없으면 None)
        self._dupfind_hover_pos = None
        self._dupfind_hover_popup = None

        return self.dupfind_tree

    def _dupfind_path_at_row(self, row):
        """[v50] 그 줄의 파일 경로. 그룹 머리 줄이면 그룹의 첫 파일."""
        m = self.dupfind_model
        gi, pos = m.locate_row(row)
        if gi < 0:
            return None
        paths = m.group_paths(gi)
        return paths[max(pos, 0)] if paths else None

    def on_dupfind_check_all_but_newest(self):
        """[v51.1] 그룹마다 가장 최근에 수정된 파일만 남기고 나머지를 모두 체크한다.
        체크만 할 뿐 지우지는 않는다 — [삭제]·[이동]을 눌러야 실제로 정리된다."""
        m = self.dupfind_model
        if m.group_count() == 0:
            return
        n = m.check_all_but_newest()
        self.status.showMessage(tr("status.dupfind.checked_newest", n=f"{n:,}", g=f"{m.group_count():,}"), 8000)
        self.logmsg(tr("status.dupfind.checked_newest", n=f"{n:,}", g=f"{m.group_count():,}"))

    def _on_dupfind_double_clicked(self, index):
        """[v50] 결과 줄 더블클릭 → 탐색기에서 그 파일을 선택한 채로 연다
        (체크박스 칸 더블클릭은 체크만 두 번 바뀌므로 그 칸은 건너뛴다)."""
        if not index.isValid():
            return
        path = self._dupfind_path_at_row(index.row())
        if path:
            self.reveal_in_file_explorer(path)

    def _on_dupfind_context_menu(self, pos):
        """[v50] 오른쪽 클릭 메뉴 — 탐색기에서 열기 · 폴더 열기 · 경로 복사 ·
        (그룹이 너무 많아 손으로 못 고를 때) 그룹마다 첫 파일만 남기고 모두 체크."""
        t = self.dupfind_tree
        row = t.rowAt(pos.y())
        path = self._dupfind_path_at_row(row) if row >= 0 else None
        menu = QMenu(self)
        act_reveal = act_folder = act_copy = None
        if path:
            act_reveal = menu.addAction(tr("menu.reveal_in_explorer"))
            act_folder = menu.addAction(tr("dupfind.menu.open_folder"))
            act_copy = menu.addAction(tr("dupfind.menu.copy_path"))
            menu.addSeparator()
        act_newest = menu.addAction(tr("dupfind.menu.check_all_but_newest"))
        act_all = menu.addAction(tr("dupfind.menu.check_all_but_first"))
        act_none = menu.addAction(tr("dupfind.menu.uncheck_all"))
        has = self.dupfind_model.group_count() > 0
        act_all.setEnabled(has)
        act_newest.setEnabled(has)
        act_none.setEnabled(has)
        chosen = menu.exec(t.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_reveal:
            self.reveal_in_file_explorer(path)
        elif chosen == act_folder:
            self.reveal_in_file_explorer(os.path.dirname(path))
        elif chosen == act_copy:
            QApplication.clipboard().setText(os.path.normpath(path))
            self.status.showMessage(tr("status.dupfind.path_copied"), 3000)
        elif chosen == act_newest:
            self.on_dupfind_check_all_but_newest()
        elif chosen == act_all:
            self.dupfind_model.check_all_but_first()
            self.status.showMessage(tr("status.dupfind.checked_n", n=len(self.dupfind_model.checked_paths())), 5000)
        elif chosen == act_none:
            self.dupfind_model.uncheck_all()

    def _build_extfind_table(self):
        """[v44.3] 확장자로 찾기 결과 — 체크박스·파일명·확장자·경로·크기·
        수정일 컬럼의 정렬 가능한 표. 그룹 트리와 달리 "큰 파일부터",
        "최근 파일부터" 같은 정렬이 더 쓸모 있어서 표로 만들었다.
        [v44.5] 경로 컬럼은 파일이 든 폴더까지만 보여주고(파일명은 이미
        따로 있다), 컬럼 폭은 자유롭게 드래그로 조절할 수 있다. 체크박스
        컬럼 헤더를 클릭하면 전체 선택/해제가 토글되고, 행을 오른쪽
        클릭하면 그 파일이 든 위치를 탐색기로 바로 열 수 있다."""
        self.extfind_table = QTableWidget(0, 6)
        self.extfind_table.setHorizontalHeaderLabels(tr("extfind.table.header").split(","))
        self.extfind_table.setColumnWidth(0, 32)
        self.extfind_table.setColumnWidth(1, 220)
        self.extfind_table.setColumnWidth(2, 70)
        self.extfind_table.setColumnWidth(3, 300)
        self.extfind_table.setColumnWidth(4, 90)
        self.extfind_table.setColumnWidth(5, 130)
        # [v44.5] 기본값(Interactive)을 그대로 두면 이미 드래그로 조절할
        # 수 있지만, 다른 화면에서 쓰는 고정폭 트리 스타일과 헷갈리지
        # 않도록 모든 컬럼에 명시적으로 지정해 둔다.
        header = self.extfind_table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self.extfind_table.horizontalHeaderItem(0).setToolTip(tr("extfind.table.header.check_all_tip"))
        # [v44.7] 경로 칸만 앞쪽을 "..."으로 줄인다 — 칸이 좁아도 그
        # 파일이 실제로 든(가장 깊은) 폴더가 항상 뒤쪽에 보이게 한다.
        self._extfind_path_delegate = _ElideLeftDelegate(self.extfind_table)
        self.extfind_table.setItemDelegateForColumn(3, self._extfind_path_delegate)
        self.extfind_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.extfind_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.extfind_table.verticalHeader().setVisible(False)
        self.extfind_table.setSortingEnabled(False)   # 직접 정렬(체크박스 컬럼이 있어서)
        self.extfind_table.horizontalHeader().sectionClicked.connect(self._on_extfind_header_clicked)
        # [v44.5] 행 오른쪽 클릭 → "탐색기에서 보기"(본체가 이미 갖고
        # 있는 reveal_in_file_explorer를 그대로 재사용한다).
        self.extfind_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.extfind_table.customContextMenuRequested.connect(self._on_extfind_table_context_menu)
        self.extfind_table.setStyleSheet(
            f"QTableWidget{{background-color:{C.DUPFIND_BG};color:{C.TREE_FG};"
            f"border:2px solid {C.DUPFIND_MAIN};border-radius:5px;gridline-color:{C.BORDER};}}"
            f"QHeaderView::section{{background-color:{C.DUPFIND_MAIN};color:#ffffff;"
            f"font-weight:bold;padding:4px;border:none;}}")
        return self.extfind_table

    def _build_dupfind_actions(self):
        """[v44.3] 하단 요약·액션 행도 두 하위 기능이 각자 가진다(스택 전환)."""
        self.findmode_actions_stack = QStackedWidget()
        self.findmode_actions_stack.addWidget(self._build_dupfind_actions_dup())
        self.findmode_actions_stack.addWidget(self._build_extfind_actions())
        return self.findmode_actions_stack

    def _build_dupfind_actions_dup(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        self.dupfind_summary_lbl = QLabel("")
        self.dupfind_summary_lbl.setStyleSheet(f"color:{C.WINDOW_FG};")
        lay.addWidget(self.dupfind_summary_lbl, 1)

        # [v51.1] 그룹마다 최신 파일만 남기고 나머지를 모두 체크 → 바로 일괄 삭제·이동
        self.btn_dupfind_keep_newest = QPushButton(tr("dupfind.btn_keep_newest"))
        self.btn_dupfind_keep_newest.setToolTip(tr("dupfind.btn_keep_newest.tip"))
        self.btn_dupfind_keep_newest.setFixedHeight(40)
        self.btn_dupfind_keep_newest.setStyleSheet(
            button_style(C.DUPFIND_MAIN, font_size=14, radius=6, padding="0 14px"))
        self.btn_dupfind_keep_newest.clicked.connect(self.on_dupfind_check_all_but_newest)
        lay.addWidget(self.btn_dupfind_keep_newest)

        self.btn_dupfind_delete = QPushButton(tr("dupfind.btn_delete"))
        self.btn_dupfind_delete.setToolTip(tr("dupfind.btn_delete.tip"))
        self.btn_dupfind_delete.setFixedHeight(40)
        self.btn_dupfind_delete.setStyleSheet(
            button_style(BTN_DESTRUCTIVE_BG, font_size=14, radius=6, padding="0 14px"))
        self.btn_dupfind_delete.clicked.connect(self.on_dupfind_delete_selected)
        lay.addWidget(self.btn_dupfind_delete)

        self.btn_dupfind_move = QPushButton(tr("dupfind.btn_move"))
        self.btn_dupfind_move.setToolTip(tr("dupfind.btn_move.tip"))
        self.btn_dupfind_move.setFixedHeight(40)
        self.btn_dupfind_move.setStyleSheet(
            button_style(C.DUPFIND_MAIN, font_size=14, radius=6, padding="0 14px"))
        self.btn_dupfind_move.clicked.connect(self.on_dupfind_move_selected)
        lay.addWidget(self.btn_dupfind_move)
        return w

    def _build_extfind_actions(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        self.extfind_summary_lbl = QLabel("")
        self.extfind_summary_lbl.setStyleSheet(f"color:{C.WINDOW_FG};")
        lay.addWidget(self.extfind_summary_lbl, 1)

        self.btn_extfind_delete = QPushButton(tr("dupfind.btn_delete"))
        self.btn_extfind_delete.setToolTip(tr("extfind.btn_delete.tip"))
        self.btn_extfind_delete.setFixedHeight(40)
        self.btn_extfind_delete.setStyleSheet(
            button_style(BTN_DESTRUCTIVE_BG, font_size=14, radius=6, padding="0 14px"))
        self.btn_extfind_delete.clicked.connect(self.on_extfind_delete_selected)
        lay.addWidget(self.btn_extfind_delete)

        self.btn_extfind_move = QPushButton(tr("dupfind.btn_move"))
        self.btn_extfind_move.setToolTip(tr("extfind.btn_move.tip"))
        self.btn_extfind_move.setFixedHeight(40)
        self.btn_extfind_move.setStyleSheet(
            button_style(C.DUPFIND_MAIN, font_size=14, radius=6, padding="0 14px"))
        self.btn_extfind_move.clicked.connect(self.on_extfind_move_selected)
        lay.addWidget(self.btn_extfind_move)
        return w

    # ---------- [v10] 검사 대상 폴더 등록(다중) ----------
    # ---------- [v01] 유틸리티(Util) 모드 ----------
    def _build_util_tools(self):
        """유틸리티 모드의 액션 바 — 다른 모드와 똑같이 "같은 자리에서 내용만
        바뀌는" 패널이다. 여기에는 도구 검색창, 홈으로 돌아가는 버튼, 지금
        열려 있는 도구 이름을 둔다."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.btn_util_home = QPushButton(tr("util.btn.home"))
        self.btn_util_home.setToolTip(tr("util.btn.home.tip"))
        self.btn_util_home.setFixedHeight(34)
        self.btn_util_home.setStyleSheet(button_style(BTN_NEUTRAL_BG, padding="0 12px"))
        # util_panel은 이 함수보다 나중에 만들어지므로, 지금 값을 붙잡지 않고
        # 눌리는 시점에 찾아가도록 람다로 감싼다.
        self.btn_util_home.clicked.connect(lambda: self.util_panel.show_home())
        lay.addWidget(self.btn_util_home)

        self.util_search = QLineEdit()
        self.util_search.setPlaceholderText(tr("util.search.placeholder"))
        self.util_search.setToolTip(tr("util.search.tip"))
        self.util_search.setFixedWidth(180)
        self.util_search.setFixedHeight(34)
        self.util_search.setClearButtonEnabled(True)
        self.util_search.setStyleSheet(FLAT_INPUT_STYLE(C.UTIL_MAIN))
        self.util_search.textChanged.connect(lambda t: self.util_panel.set_filter(t))
        lay.addWidget(self.util_search)

        lay.addStretch()

        self.lbl_util_current_cap = QLabel(tr("util.lbl.current"))
        self.lbl_util_current_cap.setStyleSheet("background:transparent;")
        lay.addWidget(self.lbl_util_current_cap)
        self.lbl_util_current = QLabel("")
        self.lbl_util_current.setStyleSheet(
            f"color:{C.UTIL_MAIN};font-weight:bold;background:transparent;")
        lay.addWidget(self.lbl_util_current)
        return w

    def _build_util_layout(self):
        """좌측 도구 목록 + 우측 작업 영역. 실제 내용은 utils 패키지가 전부
        책임지고, 메인 윈도우는 이 위젯 하나만 스택에 얹는다 — 도구가 늘어도
        main_window.py는 더 이상 커지지 않는다."""
        self.util_host = UtilHost(self)
        self.util_apps = build_apps()
        self.util_panel = UtilPanel(self.util_apps, category_label, CATEGORY_ORDER,
                                    host=self.util_host)
        self.util_panel.toolChanged.connect(self.lbl_util_current.setText)
        return self.util_panel

    def dupfind_add_folder(self, path):
        """좌측 트리 우클릭 → '폴더 추가'로 호출. 중복 등록은 막고, 누적 목록을
        콘솔(로그)에 계속 출력해 사용자가 지금까지 무엇을 등록했는지 바로 확인할 수 있게 한다."""
        norm = os.path.normpath(path)
        if norm in (os.path.normpath(p) for p in self.dupfind_targets):
            self._ensure_console_visible()
            self.logmsg(tr("log.dupfind.already_added", a0=norm))
            return
        self.dupfind_targets.append(norm)
        self._ensure_console_visible()  # [v32] 등록 목록이 콘솔에만 표시되므로 자동으로 펼쳐 보여준다
        self.logmsg(tr("log.dupfind.folder_added", a0=len(self.dupfind_targets), a1=norm))
        self.logmsg(tr("log.dupfind.target_list_header") +
                   "\n    ".join(self.dupfind_targets))
        self._dupfind_refresh_target_label()

    def dupfind_clear_targets(self):
        if not self.dupfind_targets:
            return
        self.dupfind_targets = []
        self._dupfind_refresh_target_label()
        self._ensure_console_visible()  # [v32] 해제됐다는 사실을 콘솔에서 바로 확인할 수 있게
        self.logmsg(tr("log.dupfind.cleared"))

    def _dupfind_refresh_target_label(self):
        if not self.dupfind_targets:
            self.dupfind_path_lbl.setText(tr("dupfind.target.empty"))
        else:
            self.dupfind_path_lbl.setText(tr("dupfind.target.count", n=len(self.dupfind_targets)))

    def on_dupfind_scan_start(self, strict):
        """[v38] strict=True → 정밀 스캔(전체 해시), strict=False → 빠른 스캔(샘플 해시)."""
        if not self.dupfind_targets:
            QMessageBox.information(
                self, tr("msg.title.info"),
                tr("msg.dupfind.no_targets"))
            return
        if self.dupfind_thread is not None and self.dupfind_thread.isRunning():
            return
        # [v10] 스캔 시작 전, 대상 폴더 목록을 팝업으로 한 번 더 확인시킨다.
        preview = "\n".join(f"  · {p}" for p in self.dupfind_targets)
        mode_desc = (tr("msg.dupfind.mode_desc_precise") if strict
                     else tr("msg.dupfind.mode_desc_fast"))
        reply = QMessageBox.question(
            self, tr("msg.title.confirm_targets"),
            tr("msg.dupfind.confirm_scan", a0=len(self.dupfind_targets), a1=mode_desc, a2=preview),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.dupfind_model.clear()
        self.dupfind_groups = []
        self.dupfind_summary_lbl.setText("")
        self.btn_dupfind_scan_precise.setEnabled(False)
        self.btn_dupfind_scan_fast.setEnabled(False)
        self.btn_dupfind_cancel.setEnabled(True)
        self.progress.setValue(0)
        self._dupfind_last_logged_pct = -1
        self.dupfind_mode_label = (tr("status.dupfind.running_precise") if strict
                                    else tr("status.dupfind.running_fast"))
        self.overlay.start(self.dupfind_mode_label, indeterminate=False)
        self.logmsg(tr("log.dupfind.scan_start", a0=tr('label.precise') if strict else tr('label.fast'), a1=len(self.dupfind_targets)))

        # [v38] Esc로 일시정지 → 중단 확인이 가능하도록, 스캔 중에만 단축키를 켠다.
        self.dupfind_esc_shortcut.setEnabled(True)

        self.dupfind_thread = DuplicateScanThread(
            list(self.dupfind_targets), strict=strict)
        self.dupfind_thread.progress.connect(self.on_dupfind_progress)
        self.dupfind_thread.finished_scan.connect(self.on_dupfind_finished)
        self.dupfind_thread.cancelled.connect(self.on_dupfind_cancelled)
        self.dupfind_thread.failed.connect(self.on_dupfind_failed)
        self.dupfind_thread.start()

    def on_dupfind_scan_cancel(self):
        if self.dupfind_thread is not None and self.dupfind_thread.isRunning():
            self.dupfind_thread.cancel()
            self.status.showMessage(tr("status.dupfind.cancelling"))

    def on_dupfind_scan_precise_verify(self):
        """[v49] "정밀 스캔" 버튼 — 빠른 스캔으로 이미 찾아 둔 후보 그룹만
        전체 해시로 다시 확인한다(폴더를 처음부터 다시 훑지 않음). 빠른
        스캔이 후보를 찾아 목록에 표시했을 때만 눌릴 수 있는 상태가 된다."""
        if not self.dupfind_groups:
            return
        if self.dupfind_thread is not None and self.dupfind_thread.isRunning():
            return
        self._dupfind_verify_source_groups = [list(g.paths) for g in self.dupfind_groups]
        total_files = sum(len(g) for g in self._dupfind_verify_source_groups)
        reply = QMessageBox.question(
            self, tr("msg.title.confirm_targets"),
            tr("msg.dupfind.confirm_precise_verify",
               a0=len(self._dupfind_verify_source_groups), a1=total_files),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.btn_dupfind_scan_precise.setEnabled(False)
        self.btn_dupfind_scan_fast.setEnabled(False)
        self.btn_dupfind_cancel.setEnabled(True)
        self.progress.setValue(0)
        self._dupfind_last_logged_pct = -1
        self.dupfind_mode_label = tr("status.dupfind.running_precise_verify")
        self.overlay.start(self.dupfind_mode_label, indeterminate=False)
        self.logmsg(tr("log.dupfind.precise_verify_start",
                        a0=len(self._dupfind_verify_source_groups), a1=total_files))

        # [v38]과 동일하게, 재검사 중에도 Esc로 일시정지 → 중단할 수 있게 한다.
        self.dupfind_esc_shortcut.setEnabled(True)

        self.dupfind_thread = DuplicateScanThread(
            verify_groups=self._dupfind_verify_source_groups, strict=True,
            folder_stats=getattr(self, "_dupfind_folder_stats", None))
        self.dupfind_thread.progress.connect(self.on_dupfind_progress)
        self.dupfind_thread.finished_scan.connect(self.on_dupfind_precise_verify_finished)
        self.dupfind_thread.cancelled.connect(self.on_dupfind_precise_verify_cancelled)
        self.dupfind_thread.failed.connect(self.on_dupfind_precise_verify_failed)
        self.dupfind_thread.start()

    def on_dupfind_precise_verify_finished(self, groups):
        """[v49] 재검사 완료 — 원래 후보 파일 수 대비 실제로 일치한 파일 수를
        로그로 남긴 뒤, 결과 표시 자체는 on_dupfind_finished를 그대로
        재사용한다(그룹/트리/요약 렌더링 로직 중복 방지)."""
        before_files = sum(len(g) for g in self._dupfind_verify_source_groups)
        after_files = sum(len(g.paths) for g in groups)
        removed = before_files - after_files
        self.on_dupfind_finished(groups, from_precise_verify=True)
        self.logmsg(tr("log.dupfind.precise_verify_done",
                        a0=before_files, a1=after_files, a2=removed))
        self._dupfind_log_folder_report()

    def on_dupfind_precise_verify_cancelled(self):
        """[v49] 재검사를 중단해도 원래(빠른 스캔) 결과는 그대로 남아 있으므로,
        정밀 스캔 버튼도 다시 누를 수 있는 상태로 되돌린다."""
        self._dupfind_scan_ended()
        self.logmsg(tr("log.dupfind.cancelled"))
        self.status.showMessage(tr("status.dupfind.cancelled"))
        self.btn_dupfind_scan_precise.setEnabled(bool(self.dupfind_groups))

    def on_dupfind_precise_verify_failed(self, msg):
        self._dupfind_scan_ended()
        self.logmsg(tr("log.dupfind.error", a0=msg))
        QMessageBox.warning(self, tr("msg.title.error"), tr("msg.dupfind.scan_error", a0=msg))
        self.btn_dupfind_scan_precise.setEnabled(bool(self.dupfind_groups))

    def _reveal_hidden_tool(self):
        """[v43.9] Ctrl+Shift+F9 — 목록에 안 보이는 도구(갤럭시폰 사진
        옮기기)를 Util 모드로 전환하면서 바로 연다."""
        self.switch_mode("util")
        self.util_panel.open_app("phonetransfer")

    def on_dupfind_escape_pressed(self):
        """[v38] 스캔 중 Esc — 진행을 잠시 멈추고 중단 여부를 물어본다.
        'OK'면 스캔을 중단하고, 'No'면 멈췄던 지점부터 그대로 이어서 진행한다."""
        if self.dupfind_thread is None or not self.dupfind_thread.isRunning():
            return
        self.dupfind_thread.pause()
        paused_pct = self.progress.value()
        self.overlay.set_progress(paused_pct, tr("status.dupfind.paused_confirm"))
        self.status.showMessage(tr("status.dupfind.paused"))
        self.logmsg(tr("log.dupfind.esc_pressed"))

        reply = QMessageBox.question(
            self, tr("msg.title.confirm_stop_scan"),
            tr("msg.dupfind.confirm_stop"),
            QMessageBox.Ok | QMessageBox.No, QMessageBox.No)

        # 대화상자가 떠 있는 동안 스캔 스레드가 사라졌을 가능성은 거의 없지만
        # (일시정지 중이라 스스로 끝나지 않음) 방어적으로 한 번 더 확인한다.
        if self.dupfind_thread is None:
            return

        if reply == QMessageBox.Ok:
            self.logmsg(tr("log.dupfind.user_stopped"))
            self.dupfind_thread.resume()   # 대기 중이던 체크포인트를 깨워 취소를 인지시킴
            self.on_dupfind_scan_cancel()
        else:
            self.logmsg(tr("log.dupfind.user_continued"))
            self.overlay.set_progress(paused_pct, self.dupfind_mode_label)
            self.status.showMessage(self.dupfind_mode_label)
            self.dupfind_thread.resume()

    def on_dupfind_progress(self, done, total, current_path):
        """[v38] done/total은 이제 파일 개수가 아니라 바이트 수 — 4GB 동영상과
        4KB 문서를 똑같이 '1개'로 세지 않아 진행률이 실제 남은 작업량을 반영한다.
        콘솔 로그는 1%가 바뀔 때만 남겨 대량 파일에서 UI가 밀리지 않게 한다."""
        pct = int(done / total * 100) if total else 0
        self.progress.setValue(pct)
        self.overlay.set_progress(pct, self.dupfind_mode_label)
        if pct != self._dupfind_last_logged_pct:
            self._dupfind_last_logged_pct = pct
            self.logmsg(tr("log.dupfind.progress", a0=pct, a1=current_path))

    def _dupfind_scan_ended(self):
        self.overlay.stop()
        self.btn_dupfind_scan_fast.setEnabled(True)
        self.btn_dupfind_cancel.setEnabled(False)
        self.dupfind_esc_shortcut.setEnabled(False)
        self.dupfind_thread = None

    def on_dupfind_cancelled(self):
        self._dupfind_scan_ended()
        self.logmsg(tr("log.dupfind.cancelled"))
        self.status.showMessage(tr("status.dupfind.cancelled"))

    def on_dupfind_failed(self, msg):
        self._dupfind_scan_ended()
        self.logmsg(tr("log.dupfind.error", a0=msg))
        QMessageBox.warning(self, tr("msg.title.error"), tr("msg.dupfind.scan_error", a0=msg))

    def on_dupfind_finished(self, groups, from_precise_verify=False):
        """스캔 완료 — 그룹별로 트리에 표시. 각 파일 항목은 체크박스로 선택 가능.
        [v49] from_precise_verify=True면 "빠른 스캔으로 찾은 후보를 정밀
        재검사"한 결과라는 뜻 — 막 검증을 마쳤으므로 다시 검증할 필요가
        없어 정밀 스캔 버튼을 다시 비활성화한다(새로 빠른 스캔을 돌려
        후보를 다시 찾아야 재활성화된다)."""
        # [v50] 폴더 분석 결과는 스레드에 들어 있다 — _dupfind_scan_ended()가 스레드를
        # 놓기 전에 받아 둔다. 정밀 재검사는 폴더를 다시 걷지 않으므로, 빠른 스캔이 센
        # 폴더 통계를 기억해 두었다가 넘겨준다.
        th = self.dupfind_thread
        self._dupfind_folder_report = list(getattr(th, "folder_report", None) or [])
        if th is not None and not from_precise_verify:
            self._dupfind_folder_stats = getattr(th, "folder_stats", None)
        self._dupfind_scan_ended()
        self.progress.setValue(100)
        self.dupfind_groups = groups
        # [v50] 결과는 모델에 그룹 목록만 넘긴다(줄 항목을 미리 만들지 않음 —
        # 39만 개도 0.1초, 메모리 몇 백 MB). 절약 용량이 큰 그룹부터 보인다.
        self.dupfind_model.set_groups(groups)
        self.dupfind_tree.scrollToTop()
        total_files = sum(len(g.paths) for g in groups)
        total_wasted = sum(g.wasted_bytes for g in groups)
        if groups:
            self.dupfind_summary_lbl.setText(
                tr("dupfind.summary", n_groups=len(groups), n_files=total_files,
                   size=self._fmt_size(total_wasted)))
        else:
            self.dupfind_summary_lbl.setText(tr("dupfind.summary_empty"))
        self.logmsg(tr("log.dupfind.scan_done", a0=len(groups), a1=total_files, a2=self._fmt_size(total_wasted)))
        self.status.showMessage(tr("status.dupfind.scan_done"))
        # [v49] 빠른 스캔이 후보를 찾았을 때만 정밀 스캔(재검사) 버튼을 켠다.
        # 방금 정밀 재검사를 마친 직후라면(from_precise_verify) 더 검증할
        # 이유가 없으므로 그대로 꺼 둔다.
        self.btn_dupfind_scan_precise.setEnabled(bool(groups) and not from_precise_verify)
        if not from_precise_verify:
            self._dupfind_log_folder_report()

    def _dupfind_log_folder_report(self, report=None):
        """[v50] 통째로 복사된 것으로 보이는 폴더 쌍을 콘솔 로그에 보여 준다.
        (분석은 스캔 스레드가 이미 끝내 둠 — dup_folder_analysis.py)"""
        if report is None:
            report = getattr(self, "_dupfind_folder_report", None)
        if not report:
            return
        from .dup_folder_analysis import count_by_kind, KIND_FULL, KIND_CONTAINED
        n = count_by_kind(report)
        self.logmsg(tr("log.dupfind.folders.header", full=n["full"], contained=n["contained"],
                       partial=n["partial"]))
        for i, c in enumerate(report, 1):
            if c["kind"] == KIND_FULL:
                head = tr("log.dupfind.folders.full", i=i, n=c["a_files"],
                          size=self._fmt_size(c["a_bytes"]))
            elif c["kind"] == KIND_CONTAINED:
                head = tr("log.dupfind.folders.contained", i=i, n=c["a_files"],
                          size=self._fmt_size(c["a_bytes"]), pct=round(c["b_ratio"] * 100))
            else:
                head = tr("log.dupfind.folders.partial", i=i, pct_a=round(c["a_ratio"] * 100),
                          pct_b=round(c["b_ratio"] * 100), size=self._fmt_size(c["dup_bytes"]))
            self.logmsg(head)
            self.logmsg(f"      A: {os.path.normpath(c['a'])}  ({c['a_dup_files']}/{c['a_files']})")
            self.logmsg(f"      B: {os.path.normpath(c['b'])}  ({c['b_dup_files']}/{c['b_files']})")
        self.logmsg(tr("log.dupfind.folders.footer"))
        self.status.showMessage(tr("status.dupfind.folders_found", n=len(report)), 8000)

    # ---------- [v17] 중복 이미지 호버 미리보기 ----------
    def eventFilter(self, obj, event):
        """중복 찾기 트리에서 마우스가 어느 항목 위에 머무는지 직접 추적해,
        잠시 대기 후 이미지 그룹 미리보기 팝오버를 띄운다(호버 해제 시 숨김).
        [v27] 헤더 클릭으로 뜨는 경로 입력창(path_edit_source/dest)의 Esc키·
        포커스 이탈도 여기서 함께 처리해, 아무 일도 없었던 것처럼 조용히
        원래 표시로 되돌린다(탐색기 주소창을 클릭 밖에서 취소하는 것과 동일)."""
        edits = (getattr(self, "path_edit_source", None), getattr(self, "path_edit_dest", None))
        if obj in edits and obj is not None:
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._hide_path_edit(obj)
                return True
            if event.type() == QEvent.FocusOut:
                self._hide_path_edit(obj)
        if hasattr(self, "dupfind_tree") and obj is self.dupfind_tree.viewport():
            if event.type() == QEvent.MouseMove:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                row = self.dupfind_tree.rowAt(pos.y())
                item = self.dupfind_model.locate_row(row)[0] if row >= 0 else None
                if item is not None and item < 0:
                    item = None
                if item != self._dupfind_hover_item:
                    self._dupfind_hover_item = item
                    self.dupfind_hover_timer.stop()
                    self._hide_dupfind_hover_popup()
                    if item is not None:
                        self._dupfind_hover_pos = self.dupfind_tree.viewport().mapToGlobal(pos)
                        self.dupfind_hover_timer.start(500)
            elif event.type() in (QEvent.Leave, QEvent.Wheel):
                self.dupfind_hover_timer.stop()
                self._dupfind_hover_item = None
                self._hide_dupfind_hover_popup()
        return super().eventFilter(obj, event)

    def _show_dupfind_hover_popup(self):
        item = self._dupfind_hover_item
        if item is None:
            return
        # [v50] 마우스가 올라간 줄이 속한 그룹(머리 줄이든 파일 줄이든)
        paths = self.dupfind_model.group_paths(item)
        image_paths = [p for p in paths if p and p.lower().endswith(IMAGE_EXTS)]
        if len(image_paths) < 2:
            return  # 이미지가 아니거나 비교할 게 없으면 표시하지 않음
        self._dupfind_hover_popup = DuplicatePreviewPopover(image_paths, parent=self)
        pos = self._dupfind_hover_pos
        self._dupfind_hover_popup.move(pos.x() + 16, pos.y() + 12)
        self._dupfind_hover_popup.show()

    def _hide_dupfind_hover_popup(self):
        if self._dupfind_hover_popup is not None:
            self._dupfind_hover_popup.close()
            self._dupfind_hover_popup = None

    def _dupfind_checked_paths(self):
        """체크된 파일 항목의 경로 목록을 반환(화면 순서)."""
        return self.dupfind_model.checked_paths()

    def _perform_delete_paths(self, paths, msg_check_empty_key, msg_confirm_key, msg_result_key, on_removed):
        """[v44.3] 체크된 파일들을 휴지통(또는 send2trash가 없으면 영구)으로
        지운다 — 중복 찾기·확장자로 찾기 둘 다 이 로직을 그대로 쓴다.
        다른 건 "무엇을 지우는지 안내 문구"와 "지운 뒤 그 화면 목록을
        어떻게 갱신할지"(on_removed 콜백)뿐이다."""
        if not paths:
            QMessageBox.information(self, tr("msg.title.info"), tr(msg_check_empty_key))
            return
        # [v21] send2trash가 없어도 삭제를 완전히 막지 않고, 영구 삭제로 대체할지 확인한다.
        use_trash = _HAS_SEND2TRASH
        if not use_trash:
            reply = QMessageBox.warning(
                self, tr("msg.title.no_trash"),
                tr("msg.common.no_trash_body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        else:
            reply = QMessageBox.question(
                self, tr("msg.title.confirm"), tr(msg_confirm_key, a0=len(paths)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        ok, fail, removed = 0, [], []
        for p in paths:
            try:
                if use_trash:
                    send2trash(os.path.normpath(p))
                else:
                    os.remove(p)
                ok += 1
                removed.append(p)
                self.logmsg(tr("log.dupfind.deleted", a0=tr('label.trash') if use_trash else tr('label.permanent'), a1=p))
            except OSError as e:
                fail.append(f"{p}\n  → {self._explain_os_error(e)}")
        on_removed(removed)
        msg = tr(msg_result_key, n=ok,
                  mode=tr("label.to_trash") if use_trash else tr("label.permanently"))
        if fail:
            msg += tr("msg.common.fail_list_header") + "\n".join(fail)
            QMessageBox.warning(self, tr("msg.title.done_partial"), msg)
        else:
            QMessageBox.information(self, tr("msg.title.done"), msg)

    def _perform_move_paths(self, paths, msg_check_empty_key, msg_result_key, on_moved):
        """[v44.3] 체크된 파일들을 다른 폴더로 이동 — 중복 찾기·확장자로
        찾기 공용 로직."""
        if not paths:
            QMessageBox.information(self, tr("msg.title.info"), tr(msg_check_empty_key))
            return
        dest = QFileDialog.getExistingDirectory(self, tr("msg.dupfind.pick_move_dest"))
        if not dest:
            return
        ok, fail, moved = 0, [], []
        for p in paths:
            try:
                target = os.path.join(dest, os.path.basename(p))
                shutil.move(p, target)
                ok += 1
                moved.append(p)
                self.logmsg(tr("log.dupfind.moved", a0=p, a1=target))
            except OSError as e:
                fail.append(f"{p} -> {e}")
        on_moved(moved)
        msg = tr(msg_result_key, n=ok)
        if fail:
            msg += tr("msg.common.fail_list_header") + "\n".join(fail)
            QMessageBox.warning(self, tr("msg.title.done_partial"), msg)
        else:
            QMessageBox.information(self, tr("msg.title.done"), msg)

    def on_dupfind_delete_selected(self):
        """체크된 중복 파일을 휴지통으로 삭제(계획서 5.3)."""
        self._perform_delete_paths(
            self._dupfind_checked_paths(),
            "msg.dupfind.check_delete_first", "msg.dupfind.confirm_trash", "msg.dupfind.delete_result",
            self._dupfind_remove_paths_from_tree)

    def on_dupfind_move_selected(self):
        """체크된 중복 파일을 다른 폴더로 이동(계획서 5.3)."""
        self._perform_move_paths(
            self._dupfind_checked_paths(),
            "msg.dupfind.check_move_first", "msg.dupfind.move_result",
            self._dupfind_remove_paths_from_tree)

    # ---------- [v44.3] 확장자로 찾기 ----------
    def on_extfind_search_start(self):
        """[v44.3] 칩으로 걸어 둔 확장자들로 검색을 시작한다 — 대상 폴더는
        중복 찾기와 같은 dupfind_targets를 그대로 쓴다."""
        if not self.dupfind_targets:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.dupfind.no_targets"))
            return
        extensions = self.extfind_chips.values()
        if not extensions:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.extfind.no_extensions"))
            return
        if self.extfind_thread is not None and self.extfind_thread.isRunning():
            return

        self.extfind_table.setRowCount(0)
        self.extfind_hits = []
        self.extfind_summary_lbl.setText("")
        self.btn_extfind_search.setEnabled(False)
        self.btn_extfind_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.overlay.start(tr("status.extfind.running"), indeterminate=True)
        self._ensure_console_visible()
        self.logmsg(tr("log.extfind.search_start", a0=", ".join(extensions), a1=len(self.dupfind_targets)))

        self.dupfind_esc_shortcut.setEnabled(False)  # 중복 찾기 전용 Esc 처리와 겹치지 않게

        self.extfind_thread = ExtFindThread(list(self.dupfind_targets), extensions)
        self.extfind_thread.progress.connect(self.on_extfind_progress)
        self.extfind_thread.finished_find.connect(self.on_extfind_finished)
        self.extfind_thread.cancelled.connect(self.on_extfind_cancelled)
        self.extfind_thread.failed.connect(self.on_extfind_failed)
        self.extfind_thread.start()

    def on_extfind_search_cancel(self):
        if self.extfind_thread is not None and self.extfind_thread.isRunning():
            self.extfind_thread.cancel()
            self.status.showMessage(tr("status.extfind.cancelling"))

    def on_extfind_progress(self, scanned, current_path):
        """[v44.3] 확장자 검색은 전체 대상 파일 수를 미리 알 수 없어(정밀
        스캔처럼 바이트 총량 계산을 먼저 하지 않는다), 진행률 바 대신
        "지금까지 스캔한 파일 수"를 오버레이·콘솔에 그대로 보여준다."""
        self.overlay.set_progress(None, tr("status.extfind.running_count", a0=scanned))
        if scanned % 200 == 0:
            self.logmsg(tr("log.extfind.progress", a0=scanned, a1=current_path))

    def _extfind_scan_ended(self):
        self.overlay.stop()
        self.btn_extfind_search.setEnabled(True)
        self.btn_extfind_cancel.setEnabled(False)
        self.extfind_thread = None

    def on_extfind_cancelled(self):
        self._extfind_scan_ended()
        self.logmsg(tr("log.dupfind.cancelled"))
        self.status.showMessage(tr("status.dupfind.cancelled"))

    def on_extfind_failed(self, msg):
        self._extfind_scan_ended()
        self.logmsg(tr("log.dupfind.error", a0=msg))
        QMessageBox.warning(self, tr("msg.title.error"), tr("msg.dupfind.scan_error", a0=msg))

    def on_extfind_finished(self, hits):
        self._extfind_scan_ended()
        self.extfind_hits = hits
        self._render_extfind_table()
        total_size = sum(h.size for h in hits)
        self.logmsg(tr("log.extfind.search_done", a0=len(hits), a1=self._fmt_size(total_size)))
        self.status.showMessage(tr("status.dupfind.scan_done"))

    def _render_extfind_table(self):
        """[v44.3] 지금 정렬 기준(self._extfind_sort_key/_sort_dir)에 맞춰
        self.extfind_hits를 정렬한 뒤 표를 다시 채운다 — 헤더를 클릭할
        때마다, 검색이 막 끝났을 때 이 함수 하나로 처리한다.
        [v44.5] "경로" 컬럼은 파일이 든 폴더까지만 보여준다(파일명은
        이미 그 앞 컬럼에 있어, 전체 경로를 다 보여주면 길어서 잘리기만
        했다) — 전체 경로는 툴팁으로 여전히 확인할 수 있고, 정렬도
        화면에 보이는 폴더 경로 기준으로 한다."""
        key = self._extfind_sort_key
        rev = self._extfind_sort_dir == -1
        if key == "path":
            rows = sorted(self.extfind_hits, key=lambda h: os.path.dirname(h.path), reverse=rev)
        else:
            rows = sorted(self.extfind_hits, key=lambda h: getattr(h, key), reverse=rev)

        # 다시 그리기 전에 지금 체크돼 있던 경로를 기억해 뒀다가 그대로 복원한다
        # (정렬 기준을 바꿔도 사용자가 체크해 둔 항목이 풀리지 않게).
        checked = self._extfind_checked_paths()

        self.extfind_table.setRowCount(0)
        self.extfind_table.setRowCount(len(rows))
        for r, h in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if h.path in checked else Qt.Unchecked)
            chk.setData(Qt.UserRole, h.path)
            self.extfind_table.setItem(r, 0, chk)
            self.extfind_table.setItem(r, 1, QTableWidgetItem(h.name))
            self.extfind_table.setItem(r, 2, QTableWidgetItem(h.ext))
            path_item = QTableWidgetItem(os.path.dirname(h.path))
            path_item.setToolTip(h.path)   # 폴더까지만 보여주되, 전체 경로는 툴팁으로
            self.extfind_table.setItem(r, 3, path_item)
            self.extfind_table.setItem(r, 4, QTableWidgetItem(self._fmt_size(h.size)))
            self.extfind_table.setItem(r, 5, QTableWidgetItem(self._fmt_mtime(h.mtime)))

        if rows:
            total_size = sum(h.size for h in rows)
            self.extfind_summary_lbl.setText(
                tr("extfind.summary", n=len(rows), size=self._fmt_size(total_size)))
        else:
            self.extfind_summary_lbl.setText(tr("extfind.summary_empty"))

    def _on_extfind_header_clicked(self, col):
        """[v44.5] 체크박스 컬럼(0) 헤더를 클릭하면 전체 선택/해제를
        토글하고, 나머지 컬럼은 예전처럼 정렬 기준이 된다."""
        if col == 0:
            self._on_extfind_toggle_all()
            return
        keys = {1: "name", 2: "ext", 3: "path", 4: "size", 5: "mtime"}
        key = keys.get(col)
        if key is None:
            return
        if self._extfind_sort_key == key:
            self._extfind_sort_dir *= -1
        else:
            self._extfind_sort_key = key
            self._extfind_sort_dir = -1 if key == "size" else 1
        self._render_extfind_table()

    def _on_extfind_toggle_all(self):
        """[v44.5] 전체 선택 — 한 개라도 안 체크된 행이 있으면 전부
        체크하고, 이미 전부 체크돼 있으면 전부 해제한다(같은 헤더를
        다시 누르면 반대로 동작하는 흔한 "전체 선택" 관례)."""
        n = self.extfind_table.rowCount()
        if n == 0:
            return
        all_checked = all(
            self.extfind_table.item(r, 0).checkState() == Qt.Checked for r in range(n))
        new_state = Qt.Unchecked if all_checked else Qt.Checked
        for r in range(n):
            self.extfind_table.item(r, 0).setCheckState(new_state)

    def _on_extfind_table_context_menu(self, pos):
        """[v44.5] 결과 행을 오른쪽 클릭하면 그 파일이 든 위치를 탐색기로
        바로 열 수 있다 — 본체 폴더 트리가 이미 쓰는
        reveal_in_file_explorer()를 그대로 재사용한다."""
        row = self.extfind_table.rowAt(pos.y())
        if row < 0:
            return
        chk_item = self.extfind_table.item(row, 0)
        if chk_item is None:
            return
        path = chk_item.data(Qt.UserRole)
        menu = QMenu(self)
        act_reveal = menu.addAction(tr("menu.reveal_in_explorer"))
        chosen = menu.exec(self.extfind_table.viewport().mapToGlobal(pos))
        if chosen == act_reveal:
            self.reveal_in_file_explorer(path)

    def _extfind_checked_paths(self):
        paths = []
        for r in range(self.extfind_table.rowCount()):
            item = self.extfind_table.item(r, 0)
            if item is not None and item.checkState() == Qt.Checked:
                paths.append(item.data(Qt.UserRole))
        return paths

    def _extfind_remove_paths_from_list(self, removed_paths):
        """삭제/이동 처리된 파일을 결과 목록·표에서 제거한다."""
        removed_set = set(removed_paths)
        self.extfind_hits = [h for h in self.extfind_hits if h.path not in removed_set]
        self._render_extfind_table()

    def on_extfind_delete_selected(self):
        self._perform_delete_paths(
            self._extfind_checked_paths(),
            "msg.extfind.check_delete_first", "msg.dupfind.confirm_trash", "msg.dupfind.delete_result",
            self._extfind_remove_paths_from_list)

    def on_extfind_move_selected(self):
        self._perform_move_paths(
            self._extfind_checked_paths(),
            "msg.extfind.check_move_first", "msg.dupfind.move_result",
            self._extfind_remove_paths_from_list)

    def _dupfind_remove_paths_from_tree(self, removed_paths):
        """삭제/이동 처리된 파일을 트리에서 제거하고, 그룹에 파일이 1개 이하로
        남으면(더 이상 '중복'이 아니므로) 그룹 자체를 제거한다."""
        removed_set = set(removed_paths)
        if not removed_set:
            return
        # [v50] 모델이 그룹 목록(self.dupfind_groups와 같은 객체들)을 직접 고친다 —
        # 체크 상태는 그대로, 한 개만 남은 그룹은 빠진다.
        self.dupfind_model.remove_paths(removed_set)
        # 정밀 스캔(재검사)이 지운 파일을 다시 찾지 않도록 결과 목록도 맞춘다
        for g in self.dupfind_groups:
            g.paths = [p for p in g.paths if p not in removed_set]
        self.dupfind_groups = [g for g in self.dupfind_groups if len(g.paths) > 1]

    def _style_mode_button(self):
        """[v23] 콘셉 B: 좌측 세로 액티비티 바의 모드 아이콘 버튼 — 현재 선택된
        모드만 강조색으로 채워지고, 나머지는 흰 바탕 톤. 버튼 사이 간격이 있는
        세로 배치라 각 버튼을 독립된 둥근 사각형으로 스타일링한다."""
        specs = [("sync", C.LEFT_MAIN), ("rename", C.RENAME_MAIN), ("imgedit", C.IMGEDIT_MAIN),
                  ("dupfind", C.DUPFIND_MAIN), ("util", C.UTIL_MAIN)]
        for name, color in specs:
            btn = self.mode_buttons[name]
            if self.mode == name:
                btn.setStyleSheet(
                    f"QPushButton{{background-color:{color};color:#ffffff;"
                    f"font-weight:bold;border:1px solid {color};border-radius:8px;}}")
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background-color:#ffffff;color:{color};"
                    f"font-weight:bold;border:1px solid {color};border-radius:8px;}}")

    def _style_action_bar(self):
        """[v22] 모드별 액션 바 패널의 배경/테두리를 현재 모드의 옅은 강조색으로
        갱신한다. 내용(버튼 구성)은 모드마다 다르지만, 이 패널 자체의 높이·여백·
        모서리 스타일은 항상 동일해 "같은 자리에서 내용만 바뀐다"는 인상을 준다.
        [v34] 셀렉터를 "QFrame"이 아니라 "QFrame#action_bar_frame"으로 좁혔다.
        Qt에서 QLabel은 내부적으로 QFrame을 상속하는 클래스라서, 이전처럼
        "QFrame{...}"로만 지정하면 이 프레임 안에 있는 모든 QLabel(찾기:,
        크롭 비율: 등)에도 같은 테두리·배경 스타일이 그대로 적용되어, 라벨
        하나하나에 작은 테두리 상자가 생기는 "이중 테두리"처럼 보였다."""
        specs = {
            "sync": (C.LEFT_BG, C.LEFT_MAIN),
            "rename": (C.RENAME_BG, C.RENAME_MAIN),
            "imgedit": (C.IMGEDIT_BG, C.IMGEDIT_MAIN),
            "dupfind": (C.DUPFIND_BG, C.DUPFIND_MAIN),
            "util": (C.UTIL_BG, C.UTIL_MAIN),
        }
        bg, border = specs.get(self.mode, (C.WINDOW_BG, C.BORDER))
        self.action_bar_frame.setStyleSheet(
            f"QFrame#action_bar_frame{{background-color:{bg};border:1px solid {border};"
            f"border-radius:6px;}}")
        # [v44.3] "파일 찾기"(dupfind) 모드는 위에 세그먼트 버튼 줄이 하나
        # 더 있어서(중복 찾기/확장자로 찾기 전환), 다른 모드보다 이 바가
        # 세로로 더 필요하다 — 안 늘리면 세그먼트 줄과 그 아래 도구 줄이
        # 겹쳐 보인다.
        self.action_bar_frame.setFixedHeight(84 if self.mode == "dupfind" else 50)

    # ---------- UI ----------
    def setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # top_area: 좌측 액티비티 바 + (액션 바·트리·실행버튼) 콘텐츠 컬럼을 하나로
        # 묶는다 → 대기 중 디밍 오버레이가 이 영역만 덮고, 진행률/로그/상태바는
        # 항상 노출되도록 하기 위한 컨테이너
        self.top_area = QWidget()
        top_area_lay = QHBoxLayout(self.top_area)
        top_area_lay.setContentsMargins(0, 0, 0, 0)
        top_area_lay.setSpacing(8)
        # [v29] top_area는 아래에서 만드는 main_vsplit(위:작업영역/아래:콘솔)에
        # 넣을 것이므로 여기서는 아직 root에 바로 추가하지 않는다.

        # ---- 좌측 액티비티 바 [v23] 콘셉 B: 모드 세그먼트를 상단에서 좌측
        # 트리 옆 세로 아이콘 바로 이동. "좌측 폴더 트리가 기준"이라는 콘셉을
        # 시각적으로 더 강하게 드러낸다. 환경 설정도 이 바 하단에 아이콘으로
        # 함께 배치하고, 새로고침 버튼은 화면에서 없애는 대신 F5 단축키로만
        # 동작하도록 한다(요청 반영).
        self.activity_bar = QWidget()
        self.activity_bar.setFixedWidth(48)
        act_lay = QVBoxLayout(self.activity_bar)
        act_lay.setContentsMargins(4, 0, 4, 0)
        act_lay.setSpacing(8)

        self.mode_buttons = {}
        mode_specs = [
            ("sync", "mode.sync.tip", "sync", C.LEFT_MAIN),
            ("rename", "mode.rename.tip", "rename", C.RENAME_MAIN),
            ("imgedit", "mode.imgedit.tip", "imgedit", C.IMGEDIT_MAIN),
            ("dupfind", "mode.dupfind.tip", "dupfind", C.DUPFIND_MAIN),
            # [v01] 다섯 번째 모드 — 폴더와 무관한 작은 도구들의 집합.
            ("util", "mode.util.tip", "util", C.UTIL_MAIN),
        ]
        for name, tip_key, icon_kind, color in mode_specs:
            btn = QPushButton(make_mode_icon(icon_kind, color), "")
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(40, 40)
            btn.setToolTip(tr(tip_key))   # [v25] 초등학생도 이해할 수 있는 설명식 롤오버 힌트
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, n=name: self.switch_mode(n))
            act_lay.addWidget(btn)
            self.mode_buttons[name] = btn
        self._style_mode_button()
        act_lay.addStretch()

        self.btn_set = QPushButton(make_mode_icon("settings", C.BTN_SET_BG), "")
        self.btn_set.setIconSize(QSize(22, 22))
        self.btn_set.setFixedSize(40, 40)
        self.btn_set.setToolTip(tr("mode.settings.tip"))
        self.btn_set.setCursor(Qt.PointingHandCursor)
        self.btn_set.setStyleSheet(
            f"QPushButton{{background-color:{C.BTN_SET_BG};border:none;border-radius:8px;}}"
            f"QPushButton:hover{{background-color:#3f5560;}}"
            f"QPushButton:disabled{{background-color:{BTN_DISABLED_BG};}}")
        act_lay.addWidget(self.btn_set)

        top_area_lay.addWidget(self.activity_bar)

        # [v20] F5로 새로고침 — 버튼은 없지만 모드와 무관하게 항상 동작
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_trees)

        # ---- 콘텐츠 컬럼: 모드별 액션 바(내용은 다르지만 패널 스타일은 통일된
        # 컴포넌트) + 트리/작업영역 + 하단 실행 버튼 ----
        content_col = QWidget()
        top_area_lay.addWidget(content_col, 1)
        content_lay = QVBoxLayout(content_col)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(8)

        self.tool_stack = QStackedWidget()
        self.tool_stack.addWidget(self._build_sync_tools())     # index 0
        self.tool_stack.addWidget(self._build_rename_tools())   # index 1
        self.tool_stack.addWidget(self._build_imgedit_tools())  # index 2 [v05]
        self.tool_stack.addWidget(self._build_dupfind_tools())  # index 3 [v09]
        self.tool_stack.addWidget(self._build_util_tools())      # index 4 [v01]

        self.action_bar_frame = QFrame()
        self.action_bar_frame.setObjectName("action_bar_frame")
        self.action_bar_frame.setFixedHeight(50)
        action_bar_lay = QHBoxLayout(self.action_bar_frame)
        action_bar_lay.setContentsMargins(10, 6, 10, 6)
        action_bar_lay.addWidget(self.tool_stack)
        content_lay.addWidget(self.action_bar_frame)

        self.btn_set.clicked.connect(self.open_settings)
        self.combo_history.currentIndexChanged.connect(self.on_history_selected)
        self.refresh_history_combo()

        # 트리 2개 (좌/우 각각 독립 모델 → 헤더에 서로 다른 경로 표시)
        self.splitter = QSplitter(Qt.Horizontal)

        self.model_source = self._make_model("L")
        self.model_dest = self._make_model("R")

        self.tree_source = self._make_tree("L", self.model_source, C.LEFT_BG,
                                           C.LEFT_MAIN, lambda: self.source_path)
        self.tree_source.clicked.connect(self.on_source_clicked)
        self.tree_dest = self._make_tree("R", self.model_dest, C.RIGHT_BG,
                                         C.RIGHT_MAIN, lambda: self.dest_path)
        self.tree_dest.clicked.connect(self.on_dest_clicked)

        # [v45] 즐겨찾기 바로가기(바탕화면/다운로드/메신저 폴더 등) — 각 트리
        # 바로 위에 붙는 작은 목록. 클릭하면 expand_and_select()로 아래
        # 진짜 트리에서 그 경로를 펼쳐 보여준다. 목록 내용은 환경설정에서
        # 추가/삭제/경로 변경이 가능하다(self.cfg.quick_links).
        self.quicklink_list_L = self._build_quicklink_widget(self.tree_source, "L")
        self.quicklink_list_R = self._build_quicklink_widget(self.tree_dest, "R")
        self.refresh_quicklinks()

        # [v04] 우측 패널: 동기화 모드에선 우측(초록) 트리, 리네임 모드에선
        # 파일명 에디터를 보여주는 스택. 좌측 트리는 두 모드에서 그대로 공유.
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._wrap_tree_with_quicklinks(
            self.quicklink_list_R, self.tree_dest))          # index 0: 동기화
        self.right_stack.addWidget(self._build_rename_editor())   # index 1: 리네임
        self.right_stack.addWidget(QWidget())                     # index 2: (미사용 — 이미지 편집은 전용 레이아웃 사용)
        self.right_stack.addWidget(self._build_dupfind_panel())   # index 3: 중복 파일 찾기 [v09]

        # [v45] 이 컨테이너(트리+즐겨찾기 목록)를 통째로 이름 붙여 둔다.
        # _ensure_tree_source_parent()가 모드 전환 때 옮기는 대상은 반드시
        # 이 wrap이어야 한다 — self.tree_source만 옮기면 트리가 즐겨찾기
        # 목록이 들어있는 이 컨테이너에서 쏙 빠져나가 버리고, 빈 컨테이너
        # (즐겨찾기 목록만 덩그러니 남은)만 스플리터에 남는 문제가 생긴다.
        self.tree_source_wrap = self._wrap_tree_with_quicklinks(
            self.quicklink_list_L, self.tree_source)
        self.splitter.addWidget(self.tree_source_wrap)
        self.splitter.addWidget(self.right_stack)
        self.splitter.setSizes([630, 630])  # [v10] 초기값(동기화=50:50) — 표시 후 _set_split_sizes가 정밀 보정

        # [v11] 이미지 편집 모드는 "상하 분할(위: 좌우 트리|뷰어, 아래: 썸네일 전체 폭)"이라는
        # 다른 모드와 다른 레이아웃을 쓰므로, 최상위에 한 겹 더 스택을 두어 전환한다.
        self.mode_area_stack = QStackedWidget()
        self.mode_area_stack.addWidget(self.splitter)               # index 0: 동기화/파일명변경/중복찾기
        self.mode_area_stack.addWidget(self._build_imgedit_layout())  # index 1: 이미지 편집 전용 레이아웃
        # [v01] index 2: 유틸리티 모드. 이 모드는 좌측 폴더 트리를 쓰지 않으므로
        # (계산기·카르노맵 등은 파일시스템과 무관하다) 이미지 편집 모드가 만든
        # 선례 그대로 전용 레이아웃을 한 장 더 쌓는다. 트리는 숨겨진 splitter
        # 안에 그대로 남아 있어 다른 모드로 돌아가면 선택 상태까지 유지된다.
        self.mode_area_stack.addWidget(self._build_util_layout())
        content_lay.addWidget(self.mode_area_stack, 1)

        # 하단 실행 버튼
        # [v04] 동기화 모드(복사+동기화 버튼 2개) ↔ 리네임 모드(적용 버튼 1개)를
        # 같은 높이(52px)·같은 모서리 곡률로 맞춰 전환 시 시각적 연속성을 유지.
        self.bottom_stack = QStackedWidget()

        sync_actions_w = QWidget()
        actions = QHBoxLayout(sync_actions_w)
        actions.setContentsMargins(0, 0, 0, 0)
        self.btn_copy = QPushButton(tr("sync.btn_copy"))
        self.btn_copy.setFixedHeight(40)
        self.btn_copy.setToolTip(tr("sync.btn_copy.tip"))
        self.btn_copy.setStyleSheet(
            button_style(C.BTN_COPY_BG, font_size=14, radius=6))
        self.btn_copy.clicked.connect(self.start_copy_structure)

        self.btn_sync = QPushButton(tr("sync.btn_sync"))
        self.btn_sync.setFixedHeight(40)
        self.btn_sync.setToolTip(tr("sync.btn_sync.tip"))
        self.btn_sync.setStyleSheet(
            button_style(C.BTN_SYNC_BG, font_size=16, radius=6))
        self.btn_sync.clicked.connect(self.start_sync)

        actions.addWidget(self.btn_copy, 1)
        actions.addWidget(self.btn_sync, 2)

        rename_actions_w = QWidget()
        rename_actions = QHBoxLayout(rename_actions_w)
        rename_actions.setContentsMargins(0, 0, 0, 0)
        self.btn_apply = QPushButton(tr("rename.btn_apply"))
        self.btn_apply.setToolTip(tr("rename.btn_apply.tip"))
        self.btn_apply.setFixedHeight(40)
        self.btn_apply.setStyleSheet(
            button_style(C.RENAME_MAIN, font_size=16, radius=6))
        self.btn_apply.clicked.connect(self.on_rename_apply)
        rename_actions.addWidget(self.btn_apply)

        self.bottom_stack.addWidget(sync_actions_w)                    # index 0: 동기화
        self.bottom_stack.addWidget(rename_actions_w)                  # index 1: 리네임
        self.bottom_stack.addWidget(self._build_imgedit_actions())     # index 2: 이미지 편집 [v05]
        self.bottom_stack.addWidget(self._build_dupfind_actions())     # index 3: 중복 파일 찾기 [v09]
        content_lay.addWidget(self.bottom_stack)

        # 대기 상태 디밍 오버레이 (top_area 위에만 덮인다)
        self.overlay = BusyOverlay(self.top_area)

        # 진행률 — [v22] 화면 차지 비용이 작아 모드와 무관하게 항상 노출
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        self.progress.setStyleSheet(
            f"QProgressBar{{background-color:#dfe3e8;color:{C.WINDOW_FG};"
            f"border:1px solid {C.BORDER};border-radius:4px;text-align:center;}}"
            f"QProgressBar::chunk{{background-color:{C.BTN_SYNC_BG};border-radius:4px;}}")

        # [v22] 콘솔 로그 — 접이식 컴포넌트로 통일해 4개 모드 전부에 동일하게 제공
        # (이전에는 이미지 편집 모드에서만 아예 화면에서 사라지고, 나머지 세 모드는
        # 항상 180px를 차지해 통일성이 없었다). 기본은 접힌 상태로 시작.
        self.console_toggle = QPushButton(tr("console.collapsed"))
        self.console_toggle.setFlat(True)
        self.console_toggle.setCursor(Qt.PointingHandCursor)
        self.console_toggle.setFixedHeight(20)
        self.console_toggle.setToolTip(tr("console.tip"))
        self.console_toggle.setStyleSheet(
            f"QPushButton{{text-align:left;border:none;color:{C.WINDOW_FG};"
            f"font-size:11px;padding:0 2px;}}"
            f"QPushButton:hover{{color:{C.BTN_SET_BG};}}")
        self.console_toggle.clicked.connect(self._toggle_console)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(60)  # [v29] 고정 높이 대신 최소 높이만 — 스플리터로 자유롭게 늘려 볼 수 있게
        self.log.setStyleSheet(
            f"background-color:{C.LOG_BG};color:{C.LOG_FG};"
            f"font-family:{MONO_CSS};border-radius:5px;")
        self.log.setVisible(False)  # [v22] 기본 접힘
        # [v50] 로그는 최근 5000줄만 — 줄이 수만 개 쌓이면 창 크기를 바꿀 때마다
        # 전체를 다시 줄바꿈 계산해 버벅인다(6만 줄에서 한 번에 1초 이상).
        self.log.document().setMaximumBlockCount(LOG_MAX_LINES)

        # [v29] "위: 작업 영역, 아래: 콘솔" 세로 스플리터. 콘솔을 펼친 뒤에는
        # 경계선을 마우스로 드래그해서 원하는 만큼 더 크게(또는 작게) 볼 수
        # 있다 — 이전처럼 높이가 고정된 값(180px)에 묶여 있지 않다.
        main_pane = QWidget()
        main_pane_lay = QVBoxLayout(main_pane)
        main_pane_lay.setContentsMargins(0, 0, 0, 0)
        main_pane_lay.setSpacing(8)
        main_pane_lay.addWidget(self.top_area, 1)
        main_pane_lay.addWidget(self.progress)

        console_pane = QWidget()
        console_pane_lay = QVBoxLayout(console_pane)
        console_pane_lay.setContentsMargins(0, 0, 0, 0)
        console_pane_lay.setSpacing(2)
        console_pane_lay.addWidget(self.console_toggle)
        console_pane_lay.addWidget(self.log, 1)

        self.main_vsplit = QSplitter(Qt.Vertical)
        self.main_vsplit.addWidget(main_pane)
        self.main_vsplit.addWidget(console_pane)
        self.main_vsplit.setCollapsible(0, False)  # 위쪽 작업 영역은 완전히 접히지 않게
        # [v32] 아래쪽(콘솔) 칸도 완전히 접히지 않게 한다. [v31]에서 콘솔을
        # 닫을 때 크기를 0으로 되돌리도록 고쳤는데, 이 칸이 "완전히 접힘
        # 허용" 상태였던 탓에 정말로 0까지 줄어들어 콘솔 로그 토글 버튼
        # 자체가 화면에서 사라져버렸다(중복 찾기 모드 등에서 콘솔을 다시
        # 열 방법이 없어지는 문제로 나타남). 접힘을 허용하지 않으면 0을
        # 요청해도 Qt가 "토글 줄만큼의 최소 높이"로 알아서 clamp해 준다.
        self.main_vsplit.setCollapsible(1, False)
        self.main_vsplit.setStretchFactor(0, 1)
        self.main_vsplit.setStretchFactor(1, 0)
        root.addWidget(self.main_vsplit, 1)

        # 하단 상태바 — 선택 폴더의 전체(절대) 경로 표시
        self.status = QStatusBar()
        self.status.setStyleSheet(
            f"QStatusBar{{background-color:#e8ebef;color:{C.WINDOW_FG};"
            f"font-weight:bold;}}"
            f"QStatusBar::item{{border:none;}}")
        self.setStatusBar(self.status)
        self.status.showMessage(tr("status.common.select_hint"))

        self._style_action_bar()  # [v22] 시작 시(동기화 모드) 액션 바 톤을 맞춰 둔다

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "overlay") and self.overlay.isVisible():
            self.overlay.reposition()

    def closeEvent(self, event):
        """[v04] 리네임 모드 / [v05] 이미지 편집 모드에서 미적용·미저장 변경 중 창을 닫으려 하면 확인."""
        if self.has_unsaved_rename_changes() and not self._confirm_discard_rename_changes():
            event.ignore()
            return
        if self.has_unsaved_imgedit_changes() and not self._confirm_discard_imgedit_changes():
            event.ignore()
            return
        self.album_panel.shutdown()   # [v48] 사진첩 분석이 돌고 있으면 멈추고 기다린다
        event.accept()

    def _build_quicklink_widget(self, tree, side):
        """[v47] 트리 하나에 딸린 즐겨찾기 바로가기 — 예전에는 3줄짜리
        목록(QListWidget)이었는데, 문서/사진/음악/동영상이 추가되며 항목이
        늘어 차지하는 영역이 너무 커졌다는 의견을 반영해, 동기화 모드
        우상단의 "최근 작업 히스토리"와 같은 형태(콤보박스)로 바꿨다.
        내용 채우기는 refresh_quicklinks()가 담당(설정이 바뀔 때마다
        다시 부를 수 있도록 생성과 채우기를 분리)."""
        accent = C.LEFT_MAIN if side == "L" else C.RIGHT_MAIN
        combo = QComboBox()
        combo.setFixedHeight(30)
        combo.setView(QListView())
        combo.setToolTip(tr("quicklink.combo.tip"))
        combo.setStyleSheet(
            "QComboBox{"
            "background-color:#ffffff;"
            f"color:{C.WINDOW_FG};"
            f"border:1px solid {C.BORDER};"
            "border-radius:6px;"
            "padding:0 26px 0 8px;"
            "font-size:12px;"
            "}"
            f"QComboBox:hover{{border:1px solid {accent};}}"
            "QComboBox::drop-down{"
            "subcontrol-origin:padding;subcontrol-position:top right;"
            "width:24px;border:none;background:transparent;"
            "}"
            "QComboBox::down-arrow{"
            "width:0;height:0;"
            "border-left:4px solid transparent;"
            "border-right:4px solid transparent;"
            f"border-top:5px solid {accent};"
            "margin-right:8px;"
            "}"
            "QComboBox QAbstractItemView{"
            "background-color:#ffffff;"
            f"color:{C.WINDOW_FG};"
            f"border:1px solid {C.BORDER};"
            "border-radius:6px;"
            "padding:4px;"
            "outline:0;"
            f"selection-background-color:{accent};"
            "selection-color:#ffffff;"
            "}")
        combo.currentIndexChanged.connect(
            lambda i, t=tree, s=side, c=combo: self._on_quicklink_combo_selected(t, s, c, i))
        return combo

    def _wrap_tree_with_quicklinks(self, quicklink_widget, tree):
        """즐겨찾기 콤보박스 + 트리를 세로로 붙인 컨테이너. 스플리터/스택에는
        이 컨테이너를 넣고, tree 객체 자체(self.tree_source 등)는 그대로
        유지되므로 기존 코드의 self.tree_source/self.tree_dest 참조는
        전혀 바뀌지 않는다."""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 4)
        v.setSpacing(4)
        v.addWidget(quicklink_widget)
        v.addWidget(tree, 1)
        return container

    def _quicklink_icon_kind(self, link):
        """[v47] 즐겨찾기 항목이 탐색기풍 6종 아이콘(바탕화면/다운로드/문서/
        사진/음악/동영상) 중 무엇인지, 아니면 FolderKit 앱 아이콘("custom")을
        붙일 대상인지 판별한다. icon 필드가 있으면 그대로 쓰고, 없으면(v46
        이전에 저장된 항목) 라벨 문구를 3개 언어 전부와 비교해 추정한다."""
        icon = link.get("icon")
        if icon in QUICKLINK_SYSTEM_KINDS:
            return icon
        label = link.get("label", "")
        for kind in QUICKLINK_SYSTEM_KINDS:
            if label in TR.get(f"quicklink.default.{kind}", {}).values():
                return kind
        return "custom"

    def _quicklink_icon(self, kind):
        """[v47] 종류별 아이콘을 만든다. 캐시해서 콤보박스를 새로 채울 때마다
        다시 그리지 않도록 한다."""
        if not hasattr(self, "_quicklink_icon_cache"):
            self._quicklink_icon_cache = {}
        if kind not in self._quicklink_icon_cache:
            if kind == "custom":
                self._quicklink_icon_cache[kind] = (
                    QIcon(ICON_PATH) if os.path.exists(ICON_PATH) else QIcon())
            else:
                self._quicklink_icon_cache[kind] = make_quicklink_icon(kind)
        return self._quicklink_icon_cache[kind]

    def refresh_quicklinks(self):
        """[v47] self.cfg.quick_links 내용으로 좌/우 즐겨찾기 콤보박스를
        다시 채운다 — 환경설정에서 추가/삭제/경로 변경 후 호출. 항목 0은
        "최근 작업 히스토리"와 동일한 자리표시자이고, 실제 항목은 그
        아래에 나열된다(최근에 고른 항목이 self.cfg.quick_links의 맨
        앞으로 옮겨져 있으므로 자연히 목록 맨 위에 온다)."""
        for combo in (self.quicklink_list_L, self.quicklink_list_R):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr("quicklink.combo.placeholder"), None)
            for link in self.cfg.quick_links:
                label = link.get("label", "")
                path = link.get("path", "")
                icon = self._quicklink_icon(self._quicklink_icon_kind(link))
                combo.addItem(icon, label, link)
                i = combo.count() - 1
                combo.setItemData(i, path if path else tr("quicklink.path_not_set"), Qt.ToolTipRole)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

    def _on_quicklink_combo_selected(self, tree, side, combo, index):
        """[v47] 바로가기 선택 처리 — "최근 작업 히스토리" 콤보와 동일한
        상호작용 방식: 항목을 고르면 즉시 이동하고, 콤보는 다시 자리표시자로
        되돌아간다(계속 열려 있는 "현재 위치" 표시가 아니라 "바로가기
        점프" 목록이므로). 실제 트리를 손으로 클릭한 것과 완전히 동일하게
        동작하도록, 상태를 직접 손대는 대신 펼치기/스크롤만 하고 나머지는
        진짜 클릭 핸들러(on_source_clicked/on_dest_clicked)에 그대로
        맡긴다."""
        if index <= 0:
            return
        link = combo.itemData(index)
        path = link.get("path", "") if link else ""
        if not path:
            QMessageBox.information(
                self, tr("msg.title.info"), tr("quicklink.path_not_set_body"))
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            return
        model = tree.model()
        idx = model.index(path)
        if not os.path.isdir(path) or not idx.isValid():
            QMessageBox.information(
                self, tr("msg.title.info"), tr("msg.common.path_missing", a0=path))
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            return
        self.expand_and_select(tree, model, path)
        if side == "L":
            self.on_source_clicked(idx)
        else:
            self.on_dest_clicked(idx)
        # [v47] 최근 선택한 항목이 콤보 맨 위로 오도록 self.cfg.quick_links의
        # 순서 자체를 바꾼다(좌·우 콤보가 같은 목록을 공유하므로 한쪽에서
        # 고르면 반대쪽 콤보에도 그대로 반영된다).
        # [v47] itemData()는 Qt의 QVariant를 거치며 파이썬 딱셔너리를 "같은
        # 값"으로 복사해 돌려준다(원본과 동일 객체가 아님) — 그래서 신원
        # (is) 비교가 아니라 내용(==) 비교로 원래 위치를 찾는다.
        pos = next((i for i, l in enumerate(self.cfg.quick_links) if l == link), -1)
        if pos > 0:
            self.cfg.quick_links.insert(0, self.cfg.quick_links.pop(pos))
            self.cfg.save()
        self.refresh_quicklinks()

    def _make_model(self, side):
        m = DirOnlyModel()
        m.setRootPath("")
        m.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)
        # QFileSystemModel은 기본값이 읽기 전용(readOnly=True)이라 setData()로
        # 이름을 바꿔도 디스크에 반영되지 않고 화면만 원래 이름으로 되돌아간다.
        # 이름 변경(인라인 편집) 기능을 실제로 동작시키려면 반드시 꺼야 한다.
        m.setReadOnly(False)
        m.fileRenamed.connect(lambda path, old, new, s=side: self.on_file_renamed(s, path, old, new))
        m.rename_failed.connect(lambda old, new, s=side: self.on_rename_failed(s, old, new))
        return m

    def _make_tree(self, side, model, bg, border, get_sel):
        tv = QTreeView()
        tv.setModel(model)
        tv.setRootIndex(model.index(""))
        tv.setItemDelegate(TreeDelegate(side, get_sel, tv))
        for i in range(1, model.columnCount()):
            tv.hideColumn(i)
        tv.header().setStretchLastSection(True)
        tv._full_path = ""
        tv._model_ref = model
        # 헤더 폭이 바뀌면 경로를 다시 중간 생략 처리
        tv.header().sectionResized.connect(
            lambda *_: self.update_header(tv, model))
        # 우클릭 → 이름 변경 / 삭제
        tv.setContextMenuPolicy(Qt.CustomContextMenu)
        tv.customContextMenuRequested.connect(
            lambda pos, t=tv, m=model, s=side: self.show_tree_context_menu(t, m, s, pos))
        tv.setStyleSheet(
            f"QTreeView{{background-color:{bg};color:{C.TREE_FG};"
            f"border:2px solid {border};border-radius:5px;"
            f"selection-color:{C.SEL_FG};outline:0;}}"
            f"QTreeView::item{{height:24px;color:{C.TREE_FG};}}"
            f"QHeaderView::section{{background-color:{border};color:#ffffff;"
            f"padding:4px;border:none;font-weight:bold;}}")

        # [v27] 헤더(선택 경로 표시줄) 클릭 → 그 자리를 그대로 덮는 경로 입력창으로
        # 전환(탐색기 주소창과 같은 동작). tree_source/tree_dest의 부모 구조는
        # 전혀 건드리지 않으므로 모드 전환 시 트리를 원래 자리로 되돌리는
        # _ensure_tree_source_parent()와 충돌하지 않는다.
        # [v30] 버그 수정: side가 "L"이 아니면 무조건 "R"(우측 트리)로 취급하던
        # 조건 때문에, 이미지 편집 모드의 이동/복사 대상 트리(side="I", 이
        # 함수를 재사용하지만 화면에는 안 보이는 별도 트리)가 self.path_edit_dest를
        # 엉뚱하게 덮어써버려 진짜 우측 트리의 입력창이 보이지 않게 되는 문제가
        # 있었다. "L"/"R" 두 트리에서만 이 기능을 만들도록 명확히 구분한다.
        if side in ("L", "R"):
            tv.header().setSectionsClickable(True)
            edit = QLineEdit(tv)
            edit.setVisible(False)
            edit.setFrame(False)
            edit.setStyleSheet(
                f"QLineEdit{{background-color:#ffffff;color:{C.WINDOW_FG};"
                f"border:2px solid {border};padding:0 6px;font-weight:normal;}}")
            edit.installEventFilter(self)
            edit.returnPressed.connect(
                lambda t=tv, m=model, s=side, e=edit: self._on_pathedit_confirmed(t, m, s, e))
            if side == "L":
                self.path_edit_source = edit
            else:
                self.path_edit_dest = edit
            tv.header().sectionClicked.connect(
                lambda i, t=tv, e=edit: self._show_path_edit(t, e) if i == 0 else None)
        return tv

    def update_header(self, tree, model):
        """트리 헤더에 선택 경로 표시. 폭보다 길면 중간을 …로 생략, 툴팁은 전체."""
        full = getattr(tree, "_full_path", "") or ""
        if not full:
            model.set_header("Name", "")
            return
        fm = QFontMetrics(tree.header().font())
        avail = tree.header().sectionSize(0) - 16
        if avail < 40:
            avail = 40
        elided = fm.elidedText(full, Qt.ElideMiddle, avail)
        model.set_header(elided, full)

    # ---------- [v27] 헤더 클릭 → 경로 직접 입력 ----------
    def _show_path_edit(self, tree, edit):
        """트리 헤더(선택 경로 표시줄)를 클릭하면, 그 자리를 그대로 덮는
        입력창으로 바꿔서 경로를 직접 타이핑할 수 있게 한다(탐색기 주소창과
        같은 동작). Enter를 누르면 그 경로로 이동하고, Esc를 누르거나 다른
        곳을 클릭하면 아무 일도 없었던 것처럼 원래 표시로 되돌아간다.
        [v30] 좌·우 입력창이 동시에 열려 있으면, Enter를 누르지 않고 반대쪽
        헤더를 클릭했을 때 타이핑/붙여넣기가 어느 쪽으로 들어가는지 꼬여서
        헤더가 갱신되지 않는 것처럼 보이는 문제가 있었다. 새로 열기 전에
        반대쪽이 열려 있으면 먼저 닫아, 항상 하나만 열려 있도록 한다."""
        other = self.path_edit_dest if edit is self.path_edit_source else self.path_edit_source
        if other.isVisible():
            self._hide_path_edit(other)

        header = tree.header()
        # [v30] 입력창은 tree의 자식이므로, header의 화면상 위치를 tree 좌표계
        # 기준으로 그대로 겹쳐 놓는다(header도 tree의 자식이라 좌표계가 같다).
        edit.setGeometry(header.geometry())
        full = getattr(tree, "_full_path", "") or ""
        edit.setText(full)
        edit.setVisible(True)
        edit.raise_()
        edit.setFocus(Qt.MouseFocusReason)
        edit.selectAll()

    def _hide_path_edit(self, edit):
        edit.setVisible(False)

    def _on_pathedit_confirmed(self, tree, model, side, edit):
        text = edit.text().strip()
        self._hide_path_edit(edit)
        if not text:
            return
        self._go_to_typed_path(tree, model, side, text)

    def _go_to_typed_path(self, tree, model, side, raw_path):
        """입력받은 경로 문자열로 트리를 이동시킨다. 조상 폴더들을 펼치고
        대상 폴더로 스크롤·선택한 뒤, 트리를 직접 클릭했을 때와 동일한 처리
        (on_source_clicked/on_dest_clicked)를 그대로 호출한다."""
        path = os.path.normpath(raw_path)
        if not os.path.isdir(path):
            self.status.showMessage(tr("pathbar.notfound", path=path))
            self.logmsg(tr("log.common.path_not_found", a0=path))
            return
        idx = model.index(path)
        if not idx.isValid():
            self.status.showMessage(tr("pathbar.notfound", path=path))
            return

        ancestors = []
        cur = idx.parent()
        while cur.isValid():
            ancestors.append(cur)
            cur = cur.parent()
        for a in reversed(ancestors):
            tree.expand(a)
        tree.doItemsLayout()

        if side == "L":
            self.on_source_clicked(idx)
        else:
            self.on_dest_clicked(idx)

        # [v28] QFileSystemModel은 폴더 내용을 배경에서 비동기로 채워 넣기
        # 때문에, 이동 직후 한 번만 스크롤하면 아직 덜 채워진 상태를 기준으로
        # 계산되어 위치가 어긋날 수 있었다. 레이아웃이 안정될 때까지 몇 프레임
        # 동안 스크롤을 다시 맞춰, 목표 폴더가 확실히 맨 위에 오도록 한다.
        # [v35] 처음 얻은 idx를 재시도 내내 그대로 재사용했더니, 그 사이
        # 모델이 계속 채워지면서 idx 자체가 무효화되어(특히 실제 윈도우
        # 환경에서) 헤더 텍스트는 갱신되는데 트리의 강조 표시·스크롤만
        # 조용히 실패하는 경우가 있었다. 재시도마다 경로로 인덱스를 다시
        # 구해, 항상 "그 순간 유효한" 인덱스를 쓰도록 한다.
        self._scroll_tree_to_top(tree, model, path, attempts=8)
        self.logmsg(tr("pathbar.moved", path=path))

    def _scroll_tree_to_top(self, tree, model, path, attempts):
        idx = model.index(path)
        if idx.isValid():
            tree.setCurrentIndex(idx)
            tree.doItemsLayout()
            tree.scrollTo(idx, QAbstractItemView.PositionAtTop)
        if attempts > 0:
            QTimer.singleShot(30, lambda: self._scroll_tree_to_top(tree, model, path, attempts - 1))

    # ---------- 로그 ----------
    def logmsg(self, text):
        self.log.append(text)

    # ---------- 폴더 선택 ----------
    def _toggle(self, tree, idx):
        """클릭한 폴더를 펼치거나 접음(토글)."""
        if tree.isExpanded(idx):
            tree.collapse(idx)
        else:
            tree.expand(idx)

    def ext_stats_text(self, side, folder):
        """선택 폴더의 '직속' 파일을 확장자별로 집계한 문자열 반환."""
        c = Counter()
        try:
            with os.scandir(folder) as it:
                for e in it:
                    if e.is_file(follow_symlinks=False) and not is_excluded(e.name) \
                            and not is_hidden_or_system(e):
                        ext = os.path.splitext(e.name)[1].lower().lstrip(".") or tr("label.no_ext")
                        c[ext] += 1
        except (PermissionError, OSError):
            return tr("log.ext_stats.access_denied", side=side)
        if not c:
            return tr("log.ext_stats.no_direct_files", side=side)
        total = sum(c.values())
        parts = [f"{k}: {n}" for k, n in c.most_common()]
        return tr("log.ext_stats.summary", side=side, total=total) + "   |   ".join(parts)

    def on_source_clicked(self, idx: QModelIndex):
        p = self.model_source.filePath(idx)
        if not os.path.isdir(p):
            return
        # [v04] 리네임 모드에서 다른 폴더로 옮겨가려는데 미적용 변경이 있으면 확인
        if self.mode == "rename" and self.rename_loaded_dir and \
           os.path.normpath(p) != os.path.normpath(self.rename_loaded_dir) and \
           self.has_unsaved_rename_changes():
            if not self._confirm_discard_rename_changes():
                return
        if self.mode == "imgedit" and self.imgedit_loaded_dir and \
           os.path.normpath(p) != os.path.normpath(self.imgedit_loaded_dir) and \
           self.has_unsaved_imgedit_changes():
            if not self._confirm_discard_imgedit_changes():
                return
        self.source_path = p
        self.tree_source._full_path = p
        self.update_header(self.tree_source, self.model_source)
        self._toggle(self.tree_source, idx)
        self.tree_source.viewport().update()
        self.logmsg(tr("log.common.left_selected", a0=p))
        self.logmsg(self.ext_stats_text(tr("label.left"), p))
        self.status.showMessage(tr("status.common.left", a0=p))
        if self.mode == "rename":
            self.load_rename_files(p)
        elif self.mode == "imgedit":
            self.load_imgedit_folder(p)
        elif self.mode == "dupfind":
            self.status.showMessage(tr("status.dupfind.hint_add_folder", a0=p))

    def on_dest_clicked(self, idx: QModelIndex):
        p = self.model_dest.filePath(idx)
        if os.path.isdir(p):
            self.dest_path = p
            self.tree_dest._full_path = p
            self.update_header(self.tree_dest, self.model_dest)
            self._toggle(self.tree_dest, idx)
            self.tree_dest.viewport().update()
            self.logmsg(tr("log.common.right_selected", a0=p))
            self.logmsg(self.ext_stats_text(tr("label.right"), p))
            self.status.showMessage(tr("status.common.right", a0=p))

    # ---------- 최근 작업 히스토리 콤보박스 ----------
    @staticmethod
    def _safe_disconnect(signal, slot):
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass  # 이미 해제되었거나 연결된 적 없는 경우 무시

    def _short(self, path, limit=42):
        if len(path) <= limit:
            return path
        head = path[: limit // 2 - 2]
        tail = path[-(limit // 2 - 1):]
        return f"{head}…{tail}"

    def refresh_history_combo(self):
        """히스토리 목록을 다시 읽어 콤보박스를 채운다. (사용 빈도→최근 순)"""
        self.combo_history.blockSignals(True)
        self.combo_history.clear()
        self.combo_history.addItem(tr("sync.combo_history.placeholder"), None)
        for it in self.history.sorted_items():
            label = tr("sync.combo_history.item", left=self._short(it['left']), right=self._short(it['right']))
            self.combo_history.addItem(label, it)
            i = self.combo_history.count() - 1
            self.combo_history.setItemData(
                i, tr("sync.combo_history.tooltip", left=it['left'], right=it['right']), Qt.ToolTipRole)
        self.combo_history.setCurrentIndex(0)
        self.combo_history.blockSignals(False)

    def on_history_selected(self, index):
        if index <= 0:
            return
        item = self.combo_history.itemData(index)
        if not item:
            return
        left, right = item.get("left", ""), item.get("right", "")
        if not (os.path.isdir(left) and os.path.isdir(right)):
            missing = left if not os.path.isdir(left) else right
            QMessageBox.information(
                self, tr("msg.title.info"), tr("msg.common.path_missing", a0=missing))
            self.history.remove(left, right)
            self.refresh_history_combo()
            return
        self.apply_history_pair(left, right)
        self.combo_history.blockSignals(True)
        self.combo_history.setCurrentIndex(0)
        self.combo_history.blockSignals(False)

    def expand_and_select(self, tree, model, path):
        """path까지 상위 폴더를 모두 펼치고 해당 노드를 선택 상태로 만든다."""
        idx = model.index(path)
        if not idx.isValid():
            return False
        chain = []
        p = idx.parent()
        while p.isValid():
            chain.append(p)
            p = p.parent()
        ancestor_paths = {os.path.normpath(model.filePath(p)) for p in chain}
        ancestor_paths.add(os.path.normpath(path))
        for p in reversed(chain):
            tree.expand(p)
        tree.expand(idx)
        tree.setCurrentIndex(idx)

        def _scroll():
            cur_idx = model.index(path)
            if cur_idx.isValid():
                tree.scrollTo(cur_idx, QAbstractItemView.PositionAtTop)
        _scroll()  # 1차 즉시 시도(이미 캐시된 경로라면 이걸로 충분)

        # QFileSystemModel은 폴더 목록을 백그라운드 스레드에서 비동기로 채운다.
        # 처음 열어보는 경로(콜드 캐시)이거나 상위 폴더에 항목이 많으면 로딩이
        # 꽤 오래 걸릴 수 있어, 정해진 시간이 아니라 '경로 로딩이 실제로 끝났다'는
        # directoryLoaded 시그널을 기준으로 스크롤을 다시 맞춘다. 짧은 시간 간격
        # 재시도는 보조 수단으로만 같이 둔다.
        state = {"n": 0}

        def _on_dir_loaded(loaded_path):
            if os.path.normpath(loaded_path) in ancestor_paths:
                _scroll()
            state["n"] += 1
            if state["n"] >= 60:   # 무한정 연결되어 있지 않도록 안전장치
                self._safe_disconnect(model.directoryLoaded, _on_dir_loaded)

        model.directoryLoaded.connect(_on_dir_loaded)
        # 8초 뒤에는 무조건 연결 해제(네트워크 드라이브 등 극단적으로 느린 경우 대비)
        QTimer.singleShot(8000, lambda: self._safe_disconnect(model.directoryLoaded, _on_dir_loaded))
        # 반응성을 위한 보조 재시도(대부분의 로컬 드라이브는 이 안에서 끝남)
        for delay_ms in (50, 150, 350, 700, 1200, 2000):
            QTimer.singleShot(delay_ms, _scroll)
        return True

    def refresh_trees(self):
        """[v20] 새로고침(F5) — 탐색기 등 외부에서 폴더/파일을 추가·삭제해도
        QFileSystemModel의 내부 캐시 때문에 화면에 바로 반영되지 않는 경우가 있어,
        모델을 통째로 새로 만들어 다시 붙이는 방식으로 확실하게 최신 상태를 가져온다.
        현재 선택돼 있던 경로는 그대로 펼치고 다시 선택해 준다."""
        prev_left, prev_right = self.source_path, self.dest_path

        self.model_source = self._make_model("L")
        self.tree_source.setModel(self.model_source)
        self.tree_source.setRootIndex(self.model_source.index(""))
        self.tree_source._model_ref = self.model_source
        if prev_left:
            self.expand_and_select(self.tree_source, self.model_source, prev_left)

        if hasattr(self, "tree_dest"):
            self.model_dest = self._make_model("R")
            self.tree_dest.setModel(self.model_dest)
            self.tree_dest.setRootIndex(self.model_dest.index(""))
            self.tree_dest._model_ref = self.model_dest
            if prev_right:
                self.expand_and_select(self.tree_dest, self.model_dest, prev_right)

        if hasattr(self, "tree_imgedit_dest"):
            self.model_imgedit_dest = self._make_model("I")
            self.tree_imgedit_dest.setModel(self.model_imgedit_dest)
            self.tree_imgedit_dest.setRootIndex(self.model_imgedit_dest.index(""))
            self.tree_imgedit_dest._model_ref = self.model_imgedit_dest

        self.logmsg(tr("log.common.refreshed"))
        self.status.showMessage(tr("status.common.refreshed"))

    def apply_history_pair(self, left, right):
        if self.expand_and_select(self.tree_source, self.model_source, left):
            self.source_path = left
            self.tree_source._full_path = left
            self.update_header(self.tree_source, self.model_source)
            self.tree_source.viewport().update()
            self.logmsg(tr("log.common.left_selected_history", a0=left))
            self.logmsg(self.ext_stats_text(tr("label.left"), left))
            self.status.showMessage(tr("status.common.left", a0=left))
        if self.expand_and_select(self.tree_dest, self.model_dest, right):
            self.dest_path = right
            self.tree_dest._full_path = right
            self.update_header(self.tree_dest, self.model_dest)
            self.tree_dest.viewport().update()
            self.logmsg(tr("log.common.right_selected_history", a0=right))
            self.logmsg(self.ext_stats_text(tr("label.right"), right))
            self.status.showMessage(tr("status.common.right", a0=right))

    # ---------- 우클릭: 하위 폴더 생성 / 이름 변경 / 삭제 / [v04] 파일명 일괄 변경 ----------
    def show_tree_context_menu(self, tree, model, side, pos):
        idx = tree.indexAt(pos)
        if not idx.isValid():
            return
        tree.setCurrentIndex(idx)
        path = model.filePath(idx)

        menu = QMenu(self)
        act_add = None
        if self.mode == "dupfind" and side == "L":
            # [v47] 중복 찾기 모드에서는 "검사 대상에 추가"를 다른 모드와
            # 동일한 표준 메뉴(탐색기에서 보기/하위폴더 만들기/이름변경/삭제
            # 등) 맨 위에 추가로 얹는다. 예전(v10)에는 이 항목만 단독으로
            # 나오고 나머지 메뉴가 통째로 안 보였는데, 다른 모드와 조작
            # 방식이 달라 보인다는 의견을 반영해 표준 메뉴를 그대로 유지한
            # 채 이 항목만 위에 추가하는 방식으로 바꿨다.
            act_add = menu.addAction(tr("menu.add_dupfind_target"))
            menu.addSeparator()
        act_reveal = menu.addAction(tr("menu.reveal_in_explorer"))
        menu.addSeparator()
        act_new = menu.addAction(tr("menu.create_subfolder"))
        menu.addSeparator()
        act_rename = menu.addAction(tr("menu.rename"))
        act_delete = menu.addAction(tr("menu.delete"))
        act_bulk = None
        if side == "L":
            # [v04] 팝업을 새로 띄우지 않고, 리네임 모드로 전환 + 해당 폴더를 즉시
            # 로드하는 지름길. 좌측 트리에서만 제공(리네임 모드는 좌측 폴더 기준).
            menu.addSeparator()
            act_bulk = menu.addAction(tr("menu.bulk_rename_this_folder"))
        chosen = menu.exec(tree.viewport().mapToGlobal(pos))
        if act_add is not None and chosen == act_add:
            self.dupfind_add_folder(path)
        elif chosen == act_reveal:
            self.reveal_in_file_explorer(path)
        elif chosen == act_new:
            self.create_subfolder(tree, model, idx, path, side)
        elif chosen == act_rename:
            tree.edit(idx)
        elif chosen == act_delete:
            self.delete_folder(tree, model, idx, path, side)
        elif act_bulk is not None and chosen == act_bulk:
            self.enter_rename_mode_for(path)

    def reveal_in_file_explorer(self, path):
        """폴더는 그 폴더 "안"을 바로 보여주고(예: Temp를 선택했으면
        Temp 안의 내용이 보여야 함), 파일은 부모 폴더를 열어 그 파일을
        선택 상태로 하이라이트한다(VS Code의 "Reveal in File Explorer"와
        같은 동작).

        [버그 수정] 폴더일 때 `explorer <경로>`만 주면, 이미 열려 있는
        탐색기 창이 있을 경우 윈도우가 그 창을 재사용하면서 "그 폴더
        안으로 들어가는" 대신 "그 폴더가 보이는 상위 위치에서 선택만
        하는" 것처럼 동작하는 경우가 있다(실제로 이렇게 제보받았다) —
        마치 파일에 쓰는 `/select,`처럼 되어 버린다. **`/n,`**을 붙이면
        기존 창을 재사용하지 않고 항상 그 폴더 "안"으로 들어간 새 창을
        강제로 연다."""
        norm = os.path.normpath(path)
        if not os.path.exists(norm):
            QMessageBox.warning(self, tr("msg.title.open_explorer"), tr("msg.common.path_not_found_body", a0=norm))
            return
        is_dir = os.path.isdir(norm)
        try:
            if sys.platform == "win32":
                # [v50.1 버그 수정] 예전엔 ["explorer", "/select,경로"]처럼 목록으로
                # 넘겼는데, 경로에 띄어쓰기가 있으면 Python이 "/select,경로" 전체를
                # 따옴표로 감싼다 → 탐색기가 명령으로 못 알아듣고 기본 위치(문서)를
                # 연다(중복 찾기 결과 "02. 서울과학고\..."에서 제보). 탐색기가 알아듣는
                # 형태는 따옴표가 경로에만 붙은 explorer /select,"경로" 이므로
                # 명령 문자열을 직접 만들어 넘긴다.
                subprocess.Popen(explorer_command(norm, is_dir))
            else:
                # [v51] 맥은 Finder(open -R = 그 파일을 선택한 채로), 리눅스는 기본 파일 관리자
                from .platform_info import file_manager_command
                subprocess.Popen(file_manager_command(norm, is_dir))
            self.logmsg(tr("log.common.opened_explorer", a0=norm))
        except OSError as e:
            QMessageBox.warning(self, tr("msg.title.open_explorer_failed"), tr("msg.common.open_explorer_error", a0=e))

    def create_subfolder(self, tree, model, idx, path, side):
        label = tr("label.left") if side == "L" else tr("label.right")
        name, ok = QInputDialog.getText(self, tr("msg.title.create_subfolder"), tr("msg.common.enter_folder_name"))
        if not ok or not name.strip():
            return
        name = name.strip()
        new_path = os.path.join(path, name)
        if os.path.exists(new_path):
            QMessageBox.warning(self, tr("msg.title.create_failed"), tr("msg.common.already_exists", a0=name))
            return
        try:
            os.makedirs(new_path)
        except OSError as e:
            QMessageBox.warning(self, tr("msg.title.create_failed"), tr("msg.common.create_folder_error", a0=e))
            return
        self.logmsg(tr("log.common.subfolder_created", a0=label, a1=new_path))
        tree.expand(idx)
        # QFileSystemModel이 새 폴더를 인식할 시간을 살짝 두고 선택 상태로 만든다
        QTimer.singleShot(150, lambda: self._select_new_subfolder(tree, model, new_path))

    def _select_new_subfolder(self, tree, model, path):
        idx = model.index(path)
        if idx.isValid():
            tree.setCurrentIndex(idx)
            tree.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def on_rename_failed(self, side, old_path, new_name):
        """다른 프로그램이 폴더를 사용 중이거나 권한 문제 등으로 rename이
        실패했을 때 안내. (탐색기에서 해당 폴더를 열어 둔 경우가 대표적)"""
        label = tr("label.left") if side == "L" else tr("label.right")
        name = os.path.basename(old_path.rstrip("/\\")) or old_path
        self.logmsg(tr("log.common.rename_failed", a0=label, a1=name, a2=new_name))
        QMessageBox.warning(
            self, tr("msg.title.rename_blocked"),
            tr("msg.common.rename_blocked_body", a0=name))

    def on_file_renamed(self, side, path, old_name, new_name):
        """QFileSystemModel.setData()로 실제 rename이 끝난 뒤 호출됨.
        현재 선택된 동기화 폴더였다면 경로 변수도 함께 갱신한다."""
        old_path = os.path.join(path, old_name)
        new_path = os.path.join(path, new_name)
        label = tr("label.left") if side == "L" else tr("label.right")
        if side == "L" and self.source_path and \
           os.path.normpath(self.source_path) == os.path.normpath(old_path):
            self.source_path = new_path
            self.tree_source._full_path = new_path
            self.update_header(self.tree_source, self.model_source)
        if side == "R" and self.dest_path and \
           os.path.normpath(self.dest_path) == os.path.normpath(old_path):
            self.dest_path = new_path
            self.tree_dest._full_path = new_path
            self.update_header(self.tree_dest, self.model_dest)
        self.logmsg(tr("log.common.renamed", a0=label, a1=old_name, a2=new_name))

    def _explain_os_error(self, e):
        """[v20] 삭제/이름변경 중 자주 나오는 OS 에러를 이해하기 쉬운 설명으로 바꾼다."""
        winerr = getattr(e, "winerror", None)
        if winerr == 32:
            return tr("err.os.in_use")
        if winerr == 5 or isinstance(e, PermissionError):
            return tr("err.os.no_permission")
        if winerr == 145:
            return tr("err.os.dir_not_empty")
        if isinstance(e, FileNotFoundError):
            return tr("err.os.not_found")
        return str(e)

    def delete_folder(self, tree, model, idx, path, side):
        label = tr("label.left") if side == "L" else tr("label.right")
        name = os.path.basename(path.rstrip("/\\")) or path
        ret = QMessageBox.question(
            self, tr("msg.title.confirm_delete"),
            tr("msg.common.confirm_delete_folder", a0=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        # [v21] send2trash가 이 실행 환경에 없다고 해서 삭제 자체를 막지는 않는다.
        # (exe를 빌드한 PC에 send2trash가 실제로 설치되지 않은 채 패키징된 경우
        # 발생할 수 있음 — 휴지통 없이 영구 삭제할지 사용자에게 직접 확인한다.)
        use_trash = _HAS_SEND2TRASH
        if not use_trash:
            reply = QMessageBox.warning(
                self, tr("msg.title.no_trash"),
                tr("msg.common.no_trash_body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        # [v20] 실패 이유를 짐작할 수 있게 설명을 붙이고, 다른 프로그램에서 쓰던
        # 파일을 닫은 뒤 바로 재시도할 수 있도록 "다시 시도" 버튼을 제공한다.
        while True:
            try:
                if use_trash:
                    # QFileSystemModel.filePath()는 경로를 '/'로 반환하는데, Windows의
                    # 휴지통 이동 API(IFileOperation/SHFileOperation)는 이런 슬래시 경로를
                    # 거부하고 E_INVALIDARG([WinError -2147024809] 매개 변수가 틀립니다)를
                    # 내는 경우가 있다. OS 네이티브 구분자(Windows에서는 '\')로 정규화해서
                    # 전달해야 한다.
                    send2trash(os.path.normpath(path))
                else:
                    shutil.rmtree(path)
                break
            except Exception as e:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle(tr("msg.title.delete_failed"))
                box.setText(tr("msg.common.delete_failed_body", name=name))
                box.setInformativeText(self._explain_os_error(e))
                retry_btn = box.addButton(tr("common.btn_retry"), QMessageBox.AcceptRole)
                box.addButton(tr("common.btn_cancel"), QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is not retry_btn:
                    return
        self.logmsg(tr("log.common.deleted", a0=label, a1=tr('label.trash_moved') if use_trash else tr('label.permanent_deleted'), a2=path))
        if side == "L" and self.source_path and \
           os.path.normpath(self.source_path) == os.path.normpath(path):
            self.source_path = None
            self.tree_source._full_path = ""
            self.update_header(self.tree_source, self.model_source)
        if side == "R" and self.dest_path and \
           os.path.normpath(self.dest_path) == os.path.normpath(path):
            self.dest_path = None
            self.tree_dest._full_path = ""
            self.update_header(self.tree_dest, self.model_dest)
        tree.viewport().update()

    # =========================================================================
    # [v04] 파일명 변경(리네임) 모드 — 구 FileRenamer.py 로직 이식
    # =========================================================================
    def switch_mode(self, target):
        """[v05] 3-way 세그먼트 버튼으로 모드 전환. 미적용 변경이 있으면 확인 후 전환."""
        if target == self.mode:
            return
        if self.mode == "rename" and self.has_unsaved_rename_changes():
            if not self._confirm_discard_rename_changes():
                return
        if self.mode == "imgedit" and self.has_unsaved_imgedit_changes():
            if not self._confirm_discard_imgedit_changes():
                return
        # [v01] 유틸리티 모드에도 같은 훅을 미리 걸어 둔다. 계산기는 저장할
        # 것이 없어 항상 False지만, 앞으로 "그래프를 저장하지 않고 나가려는"
        # 도구가 생겼을 때 이 자리를 다시 설계하지 않아도 되도록 해 둔 것.
        if self.mode == "util" and self.util_panel.has_unsaved():
            if not self._confirm_discard_util_changes():
                return
        self._ensure_tree_source_parent(target)
        if target == "sync":
            self.enter_sync_mode()
        elif target == "rename":
            self.enter_rename_mode()
        elif target == "imgedit":
            self.enter_imgedit_mode()
        elif target == "dupfind":
            self.enter_dupfind_mode()
        elif target == "util":
            self.enter_util_mode()

    def _ensure_tree_source_parent(self, mode):
        """[v11] 좌측 트리(tree_source)는 모든 모드가 공유하는 위젯이다. 이미지 편집
        모드만 다른 레이아웃(상하 분할)을 쓰므로, 모드 전환 때마다 트리를 그에 맞는
        컨테이너로 옮겨 붙인다. QSplitter.insertWidget()은 위젯이 기존에 다른 곳에
        있었다면 자동으로 그 자리에서 떼어내 옮겨준다.
        [v45] 옮기는 대상은 tree_source 자신이 아니라 tree_source_wrap(트리 +
        즐겨찾기 바로가기 목록을 함께 담은 컨테이너)이어야 한다 — tree_source만
        옮기면 즐겨찾기 목록만 담긴 빈 컨테이너가 원래 자리에 남아버린다.
        [v48] 이미지 편집 모드의 왼쪽은 이제 [폴더 | 사진첩] 전환 + 스택이고,
        트리는 그 "폴더" 쪽 칸(imgedit_tree_holder)에 들어간다."""
        if mode == "imgedit":
            if self.tree_source_wrap.parent() is not self.imgedit_tree_holder:
                self.imgedit_tree_holder.layout().addWidget(self.tree_source_wrap)
                self.tree_source_wrap.show()
        else:
            if self.tree_source_wrap.parent() is not self.splitter:
                self.splitter.insertWidget(0, self.tree_source_wrap)

    def enter_rename_mode(self):
        self.mode = "rename"
        self.mode_area_stack.setCurrentIndex(0)
        self.tool_stack.setCurrentIndex(1)
        self.right_stack.setCurrentIndex(1)
        self.bottom_stack.setCurrentIndex(1)
        self._set_chrome_visible(True)
        self._set_split_sizes(self.splitter, 30, 70)   # [v24] 동기화 제외 모드는 기본 3:7
        self._style_mode_button()
        self._style_action_bar()
        if self.source_path:
            self.load_rename_files(self.source_path)
        else:
            self.editor.clear()
            self.editor.original_filenames = []
            self.editor.line_is_dir = []
            self.rename_entries = []
            self.rename_loaded_dir = ""
            self.rename_header.setText(tr("rename.header.idle"))
            self.status.showMessage(tr("status.rename.select_hint"))
        self.logmsg(tr("log.mode.rename"))

    def enter_sync_mode(self):
        self.mode = "sync"
        self.mode_area_stack.setCurrentIndex(0)
        self.tool_stack.setCurrentIndex(0)
        self.right_stack.setCurrentIndex(0)
        self.bottom_stack.setCurrentIndex(0)
        self._set_chrome_visible(True)
        self._set_split_sizes(self.splitter, 50, 50)
        self._style_mode_button()
        self._style_action_bar()
        self.logmsg(tr("log.mode.sync"))

    def _set_chrome_visible(self, visible):
        """[v22] 하단 실행 버튼 스택(bottom_stack)의 표시 여부만 제어한다.
        이미지 편집 모드는 적용/저장이 우측 패널 내 소형 버튼으로 대체되어
        있으므로 이 큰 버튼 행만 숨긴다. 진행바·콘솔 로그는 [v22]부터 화면
        차지 비용이 작은 접이식 컴포넌트로 통일되어 모드와 무관하게 항상
        같은 자리에 있다(콘솔은 기본 접힘, 필요할 때 펼침)."""
        self.bottom_stack.setVisible(visible)

    def _toggle_console(self):
        """[v22] 콘솔 로그 접기/펼치기 — 4개 모드 공통.
        [v29] 이제 콘솔은 고정 높이가 아니라 세로 스플리터의 아래쪽 칸이라,
        펼칠 때 적당한 기본 높이(220px)로 한 번 잡아준다 — 그 다음부터는
        경계선을 드래그해서 사용자가 원하는 만큼 자유롭게 늘리거나 줄일 수 있다.
        [v31] 펼칠 때는 크기를 다시 잡아주면서, 정작 접을 때는 그 크기를
        되돌리는 코드가 없어서 트리 영역이 넓어진 공간을 돌려받지 못하고
        빈 칸만 남는 문제가 있었다. 접을 때도 위쪽(트리) 영역이 다시 거의
        전부를 차지하도록 명시적으로 되돌려준다."""
        expanded = self.log.isVisible()
        self.log.setVisible(not expanded)
        self.console_toggle.setText(tr("console.expanded") if not expanded else tr("console.collapsed"))
        total = self.main_vsplit.height()
        if not expanded:
            self.main_vsplit.setSizes([max(total - 220, 100), 220])
        else:
            self.main_vsplit.setSizes([total, 0])

    def _ensure_console_visible(self):
        """[v29] '폴더 하위 구조 보기'처럼 결과가 콘솔에만 출력되는 동작을
        실행할 때, 콘솔이 접혀 있으면 아무것도 안 보여 마치 동작을 안 한
        것처럼 보인다. 그런 동작 직전에 호출해 콘솔을 미리 펼쳐 둔다."""
        if not self.log.isVisible():
            self._toggle_console()

    def _set_split_sizes(self, splitter, first_pct, second_pct):
        """[v10] 모드 전환 시마다 분할 창 크기를 정해진 기본 비율로 리셋.
        동기화·파일명 변경 좌우 = 50:50, 이미지 편집·중복 찾기 좌(트리):우(작업영역) = 20:80,
        이미지 편집 내부 상(트리|뷰어):하(썸네일) = 80:20.

        주의: QSplitter.setSizes([50, 50])처럼 작은 비율 숫자를 그대로 넘기면
        Qt가 그 비율을 무시하고 위젯 sizeHint 기반의 엉뚱한 배분(예: 19:81)을
        해버리는 경우가 있어, 실제 스플리터 크기를 기준으로 목표 픽셀 값을
        직접 계산해서 넘긴다."""
        horizontal = splitter.orientation() == Qt.Horizontal
        total = splitter.width() if horizontal else splitter.height()
        if total <= 1:
            total = 1260 if horizontal else 720  # 창이 아직 표시되기 전 기본값
        avail = max(0, total - splitter.handleWidth())
        first = int(avail * first_pct / (first_pct + second_pct))
        splitter.setSizes([first, avail - first])

    def enter_imgedit_mode(self):
        self.mode = "imgedit"
        self.mode_area_stack.setCurrentIndex(1)
        self.tool_stack.setCurrentIndex(2)
        self.imgedit_viewer_stack.setCurrentIndex(0)
        self._set_chrome_visible(False)
        self._set_split_sizes(self.imgedit_hsplit, 30, 70)   # [v24] 좌: 트리 30% · 우: 뷰어 70%
        # [v14] 하단(썸네일+정보바)은 고정 높이라 별도 비율 지정이 필요 없음 — 남는 공간은
        # 자동으로 위쪽 뷰어(imgedit_hsplit)가 모두 가져간다.
        self._style_mode_button()
        self._style_action_bar()
        if self.imgedit_view_kind == IMGEDIT_VIEW_ALBUM:
            self.album_panel.activate()
            self._load_album_current()
        elif self.source_path:
            self.load_imgedit_folder(self.source_path)
        else:
            self.status.showMessage(tr("status.imgedit.select_hint"))
        self.logmsg(tr("log.mode.imgedit"))

    def enter_dupfind_mode(self):
        """[v09] 중복 파일 찾기 모드 — 계획서 5단계.
        [v10] 좌측 트리에서 우클릭 → '폴더 추가'로 등록한 여러 폴더를 검사 대상으로 삼는다."""
        self.mode = "dupfind"
        self.mode_area_stack.setCurrentIndex(0)
        self.tool_stack.setCurrentIndex(3)
        self.right_stack.setCurrentIndex(3)
        self.bottom_stack.setCurrentIndex(3)
        self._set_chrome_visible(True)
        self._set_split_sizes(self.splitter, 30, 70)   # [v24] 좌: 트리 30% · 우: 결과 70%
        self._style_mode_button()
        self._style_action_bar()
        self._dupfind_refresh_target_label()
        self.status.showMessage(tr("status.dupfind.no_targets_hint"))
        self.logmsg(tr("log.mode.dupfind"))

    def enter_util_mode(self):
        """[v01] 유틸리티 모드 — 폴더 트리 대신 도구 목록을 좌측에 둔다.

        하단 실행 버튼 행(bottom_stack)은 숨긴다: 모드 전체를 아우르는 단일
        실행 동작이 없고, 도구마다 자기 버튼을 갖기 때문이다(이미지 편집
        모드와 같은 판단). 진행바·콘솔 로그·상태바는 다른 모드와 똑같이
        그대로 남아, 미니앱도 계산 결과를 콘솔에 남길 수 있다."""
        self.mode = "util"
        self.mode_area_stack.setCurrentIndex(2)
        self.tool_stack.setCurrentIndex(4)
        self._set_chrome_visible(False)
        self._set_split_sizes(self.util_panel.splitter, 26, 74)
        self._style_mode_button()
        self._style_action_bar()
        self.util_panel.on_enter()
        self.status.showMessage(tr("status.util.hint"))
        self.logmsg(tr("log.mode.util"))

    def _confirm_discard_util_changes(self):
        return QMessageBox.question(
            self, tr("msg.title.confirm"), tr("msg.util.discard_changes"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def enter_rename_mode_for(self, path):
        """좌측 트리 우클릭 → "이 폴더의 파일명 일괄 변경" 지름길.
        별도 팝업 없이 리네임 모드로 전환하면서 해당 폴더를 바로 로드한다."""
        if self.mode == "rename" and self.rename_loaded_dir and \
           os.path.normpath(path) != os.path.normpath(self.rename_loaded_dir) and \
           self.has_unsaved_rename_changes():
            if not self._confirm_discard_rename_changes():
                return
        self.source_path = path
        self.tree_source._full_path = path
        self.update_header(self.tree_source, self.model_source)
        idx = self.model_source.index(path)
        if idx.isValid():
            self.tree_source.setCurrentIndex(idx)
            self.tree_source.scrollTo(idx, QAbstractItemView.PositionAtTop)
        self.logmsg(tr("log.common.left_selected_shortcut", a0=path))
        if self.mode == "rename":
            self.load_rename_files(path)
        else:
            self.enter_rename_mode()

    def has_unsaved_rename_changes(self):
        """에디터 내용이 원본 파일명 목록과 달라졌는지(=아직 적용 안 한 변경) 확인."""
        if self.mode != "rename" or not self.editor.original_filenames:
            return False
        current = [ln.strip() for ln in self.editor.toPlainText().split("\n")]
        orig = self.editor.original_filenames
        if len(current) == len(orig) + 1 and current[-1] == "":
            current = current[:-1]
        return current != orig

    def _confirm_discard_rename_changes(self):
        ret = QMessageBox.question(
            self, tr("msg.title.confirm_changes"),
            tr("msg.rename.discard_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ret == QMessageBox.Yes

    # ---------- [v05] 이미지 편집 모드 로직 ----------
    def has_unsaved_imgedit_changes(self):
        return any(st.applied and not st.saved for st in self.imgedit_states.values())

    def _confirm_discard_imgedit_changes(self):
        ret = QMessageBox.question(
            self, tr("msg.title.confirm_changes"),
            tr("msg.imgedit.discard_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ret == QMessageBox.Yes

    # =========================================================================
    # [v48] 사진첩 — 왼쪽 패널 [폴더 | 사진첩] 전환과 행사 정정
    # =========================================================================
    def _build_imgedit_left(self):
        """왼쪽 패널: 위에 [폴더 | 사진첩] 전환 버튼, 아래에 스택
        (0: 폴더 트리가 들어갈 칸 — 트리는 다른 모드와 공유하므로 모드 전환 때
        _ensure_tree_source_parent()가 옮겨 붙인다, 1: 사진첩 패널)."""
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(0)
        self.btn_view_folder = QPushButton(tr("album.view.folder"))
        self.btn_view_album = QPushButton(tr("album.view.album"))
        self.btn_view_folder.clicked.connect(lambda: self.set_imgedit_view(IMGEDIT_VIEW_FOLDER))
        self.btn_view_album.clicked.connect(lambda: self.set_imgedit_view(IMGEDIT_VIEW_ALBUM))
        for b in (self.btn_view_folder, self.btn_view_album):
            b.setFixedHeight(26)
            row.addWidget(b, 1)
        v.addLayout(row)
        self.imgedit_left_stack = QStackedWidget()
        self.imgedit_tree_holder = QWidget()
        hl = QVBoxLayout(self.imgedit_tree_holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.album_panel = AlbumPanel()
        self.album_panel.albumChosen.connect(self._on_album_chosen)
        self.album_panel.albumChanged.connect(self._on_album_changed)
        self.imgedit_left_stack.addWidget(self.imgedit_tree_holder)   # 0: 폴더
        self.imgedit_left_stack.addWidget(self.album_panel)           # 1: 사진첩
        v.addWidget(self.imgedit_left_stack, 1)
        self._style_imgedit_view_buttons()
        return wrap

    def _style_imgedit_view_buttons(self):
        on = button_style(C.IMGEDIT_MAIN, font_size=12, radius=0)
        off = button_style("#cfd8dc", fg=C.WINDOW_FG, font_size=12, radius=0)
        folder = self.imgedit_view_kind == IMGEDIT_VIEW_FOLDER
        self.btn_view_folder.setStyleSheet(on if folder else off)
        self.btn_view_album.setStyleSheet(off if folder else on)

    def set_imgedit_view(self, kind):
        """왼쪽 패널을 폴더 ↔ 사진첩으로 바꾼다(kind는 내부 키)."""
        if kind == self.imgedit_view_kind:
            return
        if self.has_unsaved_imgedit_changes() and not self._confirm_discard_imgedit_changes():
            return
        self.imgedit_view_kind = kind
        self._style_imgedit_view_buttons()
        album = kind == IMGEDIT_VIEW_ALBUM
        self.imgedit_left_stack.setCurrentIndex(1 if album else 0)
        # 사진첩에서는 여러 장을 골라 한꺼번에 옮길 수 있게 한다
        self.thumb_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection if album else QAbstractItemView.SingleSelection)
        if album:
            self.album_panel.activate()
            self._load_album_current()
        else:
            self.imgedit_album_title = ""
            if self.source_path and os.path.isdir(self.source_path):
                self.load_imgedit_folder(self.source_path)
            else:
                self._load_imgedit_files([], "")

    def _load_album_current(self):
        """[v49] 사진첩에서 지금 고른 것(행사·장소·인물)의 사진을 불러온다."""
        panel = self.album_panel
        if not panel.current_exists():
            self.imgedit_album_title = ""
            self._load_imgedit_files([], panel.library_dir)
            self.imgedit_status_lbl.setText(tr("album.no_event"))
            return
        self.imgedit_album_title = panel.current_title()
        self._load_imgedit_files(panel.current_paths(), panel.library_dir, quiet=True)

    def _load_album_event(self, event_id):   # v48 호환
        self.album_panel.current_event_id = event_id
        self._load_album_current()

    def _on_album_chosen(self):
        if self.has_unsaved_imgedit_changes() and not self._confirm_discard_imgedit_changes():
            return
        self._load_album_current()

    def _on_album_changed(self):
        """분석·정정 뒤 — 지금 보고 있는 것의 사진 구성이 바뀌었으면 다시
        불러온다. 저장하지 않은 편집이 있으면 편집을 지키기 위해 목록은 그대로
        두고, 다음에 다시 고를 때 반영되게 한다."""
        if self.mode != "imgedit" or self.imgedit_view_kind != IMGEDIT_VIEW_ALBUM:
            return
        panel = self.album_panel
        if not panel.current_exists():
            if self.imgedit_files:
                self._load_album_current()
            return
        self.imgedit_album_title = panel.current_title()
        paths = panel.current_paths()
        if paths != self.imgedit_files and not self.has_unsaved_imgedit_changes():
            self._load_imgedit_files(paths, panel.library_dir, quiet=True)
        else:
            # [v49.1] 사진은 그대로이고 이름만 바뀐 경우(이름 바꾸기 등) — 위쪽 상태 줄도 바로 갱신
            self.imgedit_status_lbl.setText(tr("album.title.status", a0=self.imgedit_album_title,
                                               a1=tr("imgedit.thumb_count_cache", n=len(self.imgedit_files),
                                                     cache=self.thumbnail_cache.size())))

    def _selected_thumb_paths(self):
        rows = sorted({self.thumb_list.row(it) for it in self.thumb_list.selectedItems()})
        if not rows and 0 <= self.imgedit_current < len(self.imgedit_files):
            rows = [self.imgedit_current]
        return [self.imgedit_files[r] for r in rows if 0 <= r < len(self.imgedit_files)]

    def _on_thumb_context_menu(self, pos):
        """사진첩에서 연 행사·인물이라면 사진 단위 정정 메뉴(장소는 정정할 것이 없다)."""
        panel = self.album_panel
        kind = panel.current_kind
        if self.imgedit_view_kind != IMGEDIT_VIEW_ALBUM or kind not in (KIND_EVENT, KIND_PERSON, KIND_MINOR) \
                or not panel.current_exists():
            return
        item = self.thumb_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.thumb_list.setCurrentItem(item)
        paths = self._selected_thumb_paths()
        if not paths:
            return
        menu = QMenu(self.thumb_list)
        targets = {}
        if kind == KIND_EVENT:
            current = panel.current_key
            sub = menu.addMenu(tr("album.thumb.move_to"))
            for info in panel.nearby_events(current):
                targets[sub.addAction(tr("album.count", a0=event_title(info), a1=info.count))] = info.id
            sub.addSeparator()
            act_more = sub.addAction(tr("album.thumb.move_more"))
            act_split = menu.addAction(tr("album.thumb.split", a0=len(paths)))
            act_not = None
        else:
            current = panel.current_key if kind == KIND_PERSON else None
            sub = menu.addMenu(tr("album.thumb.move_person"))
            for info in panel.top_persons(exclude_id=current):
                targets[sub.addAction(tr("album.count", a0=person_title(info), a1=info.count))] = info.id
            sub.addSeparator()
            act_more = sub.addAction(tr("album.thumb.move_more"))
            act_split = menu.addAction(tr("album.thumb.new_person", a0=len(paths)))
            act_not = menu.addAction(tr("album.thumb.not_person", a0=len(paths)))
        chosen = menu.exec(self.thumb_list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if kind == KIND_EVENT:
            if chosen is act_split:
                self.album_split_photos(paths)
            elif chosen is act_more:
                target = panel.choose_event_dialog(exclude_id=current)
                if target is not None:
                    self.album_move_photos(paths, target)
            elif chosen in targets:
                self.album_move_photos(paths, targets[chosen])
            return
        if chosen is act_split:
            self.album_split_faces(paths)
        elif chosen is act_not:
            self.album_exclude_faces(paths)
        elif chosen is act_more:
            target = panel.choose_person_dialog(exclude_id=current)
            if target is not None:
                self.album_move_faces(paths, target)
        elif chosen in targets:
            self.album_move_faces(paths, targets[chosen])

    def _confirm_drop_unsaved(self, paths):
        if not any(self.imgedit_states.get(p) and self.imgedit_states[p].applied
                   and not self.imgedit_states[p].saved for p in paths):
            return True
        reply = QMessageBox.question(self, tr("msg.title.confirm_changes"), tr("album.thumb.unsaved"),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def _remove_thumbs(self, paths):
        """옮겨 간 사진을 지금 목록에서만 빼고, 나머지 사진의 편집 상태는 지킨다."""
        gone = set(paths)
        keep_current = self.imgedit_current
        for row in sorted((i for i, p in enumerate(self.imgedit_files) if p in gone), reverse=True):
            p = self.imgedit_files.pop(row)
            self.imgedit_states.pop(p, None)
            self.imgedit_thumb_base.pop(p, None)
            self.thumb_list.takeItem(row)
        if self.imgedit_files:
            self.thumb_list.setCurrentRow(min(max(0, keep_current), len(self.imgedit_files) - 1))
        else:
            self.imgedit_current = -1
            self.crop_canvas.set_image(None)
            self.imgedit_info_lbl.setText(tr("imgedit.no_image"))

    def _album_edit(self, fn, paths):
        """사진 정정 공통 — 정정 직후의 albumChanged로 목록 전체를 다시 불러오지
        않게 잠시 끊고(다른 사진의 편집 상태를 지키려고), 옮겨 간 사진만 뺀다."""
        if not self._confirm_drop_unsaved(paths):
            return False
        self.album_panel.albumChanged.disconnect(self._on_album_changed)
        try:
            fn(paths)
        finally:
            self.album_panel.albumChanged.connect(self._on_album_changed)
        panel = self.album_panel
        if not panel.current_exists():
            # 행사·인물의 사진을 전부 옮겨 그 묶음이 사라졌다
            panel.current_kind = panel.current_key = None
            self._load_album_current()
            return True
        self._remove_thumbs(paths)
        self.imgedit_album_title = panel.current_title()
        self.imgedit_status_lbl.setText(tr("album.title.status", a0=self.imgedit_album_title,
                                           a1=tr("imgedit.thumb_count_cache", n=len(self.imgedit_files),
                                                 cache=self.thumbnail_cache.size())))
        return True

    def album_move_photos(self, paths, target_event_id):
        if self._album_edit(lambda ps: self.album_panel.move_photos(ps, target_event_id), paths):
            self.logmsg(tr("log.album.moved", a0=len(paths)))

    def album_split_photos(self, paths):
        if self._album_edit(self.album_panel.split_photos, paths):
            self.logmsg(tr("log.album.split", a0=len(paths)))

    # [v49] 인물 정정 — 보고 있는 인물(또는 "자주 안 나온 얼굴")의 얼굴만 옮긴다
    def album_move_faces(self, paths, person_id):
        moved = []
        if self._album_edit(lambda ps: moved.append(self.album_panel.move_faces(ps, person_id)), paths):
            self.logmsg(tr("log.album.faces_moved", a0=moved[0] if moved else 0))

    def album_split_faces(self, paths):
        if self._album_edit(self.album_panel.split_faces, paths):
            self.logmsg(tr("log.album.faces_split"))

    def album_exclude_faces(self, paths):
        moved = []
        if self._album_edit(lambda ps: moved.append(self.album_panel.exclude_faces(ps)), paths):
            self.logmsg(tr("log.album.faces_excluded", a0=moved[0] if moved else 0))

    def load_imgedit_folder(self, folder):
        """선택된 폴더의 이미지들을 썸네일 스트립 + 미리보기에 불러온다."""
        if not _HAS_PIL:
            QMessageBox.warning(self, tr("msg.title.info"), tr("msg.imgedit.no_pillow"))
            return
        try:
            files = sorted(
                f for f in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(IMAGE_EXTS)
                and not is_excluded(f) and not is_hidden_or_system(os.path.join(folder, f))
            )
        except OSError as e:
            self.logmsg(tr("log.imgedit.error", a0=e))
            return
        self.imgedit_album_title = ""
        self._load_imgedit_files([os.path.join(folder, f) for f in files], folder)

    def _load_imgedit_files(self, paths, base_dir, quiet=False):
        """[v48] 폴더든 사진첩 행사든, 사진 경로 목록을 썸네일 줄 + 미리보기에 올린다.
        (예전 load_imgedit_folder의 뒷부분을 떼어 낸 것 — 동작은 같다.)
        [v49.1] quiet=True(사진첩)면 "불러오는 중" 대화창을 띄우지 않는다 — 대화창이
        키보드 포커스를 가져가 사진첩 목록을 화살표로 계속 옮길 수 없었다. 다른 항목을
        고르면 앞서 불러오던 것은 알아서 취소된다(세대 검사)."""
        self.imgedit_loaded_dir = base_dir
        self.imgedit_files = list(paths)
        self.imgedit_states = {p: ImageState(p) for p in self.imgedit_files}

        # [v37] 비동기 썸네일 로딩 (기존 동기 로딩 제거)
        if self.imgedit_files:
            self.load_image_thumbnails(self.imgedit_files, base_dir, show_dialog=not quiet)
            if quiet:
                self.imgedit_status_lbl.setText(tr("album.title.status", a0=self.imgedit_album_title,
                                                   a1=tr("imgedit.thumb_loading", n=len(self.imgedit_files)))
                                                if self.imgedit_album_title
                                                else tr("imgedit.thumb_loading", n=len(self.imgedit_files)))
            self.status.showMessage(tr("status.imgedit.loading", a0=base_dir, a1=len(self.imgedit_files)))
            self.logmsg(tr("log.imgedit.entered", a0=base_dir, a1=len(self.imgedit_files)))
        else:
            self.thumb_list.clear()
            self.imgedit_thumb_base = {}
            self.imgedit_current = -1
            self.crop_canvas.set_image(None)
            self.imgedit_info_lbl.setText(tr("imgedit.no_image"))
            self.imgedit_status_lbl.setText(tr("imgedit.no_image"))

    @staticmethod
    def _pil_to_pixmap(pil_img):
        img = pil_img.convert("RGBA")
        qimg = QImage(img.tobytes(), img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    @staticmethod
    def _make_padded_thumb_pixmap(pil_img):
        """[v12] 이미지 비율과 무관하게 항상 THUMB_SIZE 정사각형 아이콘을 만든다(레터박스).
        비율이 제각각인 썸네일이 섞여도 아이콘 상자 크기가 항상 같아서, 파일명이
        모든 항목에서 같은 높이에 정렬된다."""
        img = pil_img.copy()
        img.thumbnail(THUMB_SIZE)
        canvas = Image.new("RGBA", THUMB_SIZE, (0, 0, 0, 0))
        x = (THUMB_SIZE[0] - img.width) // 2
        y = (THUMB_SIZE[1] - img.height) // 2
        canvas.paste(img.convert("RGBA"), (x, y))
        return MainWindow._pil_to_pixmap(canvas)

    @staticmethod
    def _elide_thumb_name(name):
        """[v12] 썸네일 아래 파일명은 최대 2줄까지만 보여주고, 그보다 길면 뒤를
        말줄임(…) 처리한다(전체 이름은 툴팁으로 확인 가능)."""
        max_chars = 20  # 대략 2줄 분량(그리드 폭 기준 경험적 추정치)
        if len(name) <= max_chars:
            return name
        return name[:max_chars - 1] + "…"

    @staticmethod
    def _fmt_size(n):
        """[v05] 바이트 수를 사람이 읽기 좋은 단위(B/KB/MB/GB)로 표시."""
        size = float(n)
        for unit in ("B", "KB", "MB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}GB"

    @staticmethod
    def _fmt_mtime(ts):
        """[v44.3] 수정 시각(epoch 초)을 "YYYY-MM-DD HH:MM"으로 표시 —
        확장자로 찾기 결과 표의 "수정일" 컬럼에 쓴다."""
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        except (OSError, OverflowError, ValueError):
            return "-"

    def _set_thumb_badge(self, row, badge_on):
        """[v05] 적용된 이미지의 썸네일 우상단에 작은 배지(점)를 그려 변경 여부를 표시."""
        if not (0 <= row < len(self.imgedit_files)):
            return
        path = self.imgedit_files[row]
        base = self.imgedit_thumb_base.get(path)
        item = self.thumb_list.item(row)
        if base is None or item is None:
            return
        if not badge_on:
            item.setIcon(QIcon(base))
            return
        pm = QPixmap(base)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r = 12
        p.setBrush(QBrush(QColor(C.IMGEDIT_MAIN)))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(pm.width() - r - 2, 2, r, r)
        p.end()
        item.setIcon(QIcon(pm))

    def _update_imgedit_info(self, st, orig_img):
        """[v05] 정보 바: 이미지명 · 크기(가로x세로) · 용량 · 변경 여부."""
        try:
            size_bytes = os.path.getsize(st.path)
        except OSError:
            size_bytes = 0
        if st.applied and st.crop_rect:
            x0, y0, x1, y1 = st.crop_rect
            dims = f"{int(x1 - x0)}×{int(y1 - y0)}"
        else:
            dims = f"{orig_img.width}×{orig_img.height}"
        badge = tr("imgedit.badge_applied") if (st.applied and not st.saved) else (tr("imgedit.badge_saved") if st.saved else "")
        idx_text = f"{self.imgedit_current + 1}/{len(self.imgedit_files)}" if self.imgedit_files else "0/0"
        self.imgedit_info_lbl.setText(
            f"{idx_text}  {os.path.basename(st.path)}  ·  {dims}  ·  {self._fmt_size(size_bytes)}{badge}")

    def _imgedit_open_error_message(self, path, error):
        """[v44] 이미지를 열지 못했을 때 보여줄 로그 문구를 만든다.
        가장 흔한 원인 하나를 특별 취급한다: 확장자가 .heic/.heif인데
        pillow-heif가 설치되어 있지 않은 경우. 이때는 Pillow가 내놓는
        원래 메시지("cannot identify image file...")가 사용자에게 아무
        단서를 주지 못하므로, 무엇을 설치해야 하는지 바로 알려준다."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".heic", ".heif") and not HEIF_SUPPORT:
            return tr("log.imgedit.heic_not_supported", a0=path)
        if error is None:
            return tr("log.imgedit.thumb_failed_generic", a0=path)
        return tr("log.imgedit.open_failed", a0=path, a1=error)

    def _imgedit_render(self, st):
        """[v05] 상태(st)에 따라 편집 뷰(크롭 오버레이) 또는 적용 결과 미리보기(화면 채움)를 그린다."""
        try:
            img = open_oriented(st.path)   # [v47.2] 세로 사진이 눕지 않게 EXIF 방향대로
        except Exception as e:
            self.logmsg(self._imgedit_open_error_message(st.path, e))
            return
        if st.applied:
            preview = img
            if st.crop_rect:
                x0, y0, x1, y1 = st.crop_rect
                preview = preview.crop((int(x0), int(y0), int(x1), int(y1)))
            preview = apply_curve_to_image(preview, st.curve_points)
            self.crop_canvas.set_preview_image(preview)   # 계획서: 선택 영역만 남은 이미지로 뷰를 채움
        else:
            self.crop_canvas.set_image(img, st.crop_rect, st.ratio, st.curve_points)
        self._update_imgedit_info(st, img)

    def on_imgedit_thumb_selected(self, row):
        if row < 0 or row >= len(self.imgedit_files):
            return
        self.imgedit_current = row
        path = self.imgedit_files[row]
        st = self.imgedit_states[path]
        self.combo_ratio.blockSignals(True)
        self.combo_ratio.setCurrentIndex(max(0, self.combo_ratio.findData(st.ratio)))
        self.combo_ratio.blockSignals(False)
        self._imgedit_render(st)

    def _imgedit_push_undo(self, st):
        """[v09] 되돌리기 스택에 현재 상태를 저장하고 재실행 스택은 비운다(새 편집이 시작됐으므로)."""
        st.undo_stack.append(st.snapshot())
        if len(st.undo_stack) > 50:
            st.undo_stack.pop(0)
        st.redo_stack.clear()

    def on_imgedit_crop_changed(self):
        """[v05] 크롭 영역을 드래그로 바꿀 때마다 즉시 상태에 저장 —
        다른 썸네일로 이동해도 선택 영역이 사라지지 않고 유지된다.
        [v07] "적용" 배지는 오직 저장(Save)했을 때만 사라진다 — 크롭을 다시
        조정한다고 해서 적용 상태/배지를 임의로 취소하지 않는다.
        [v12] 이미 적용된(preview) 이미지 위에 새로 크롭 영역을 그린 경우, 그
        좌표는 "이미 잘린 이미지" 기준이므로 이전 크롭 오프셋을 더해 원본
        이미지 기준 절대 좌표로 합성한다 — 이렇게 하면 "잘라낸 결과를 유지한
        채 그 위에서 다시 자르기"가 정확한 위치에 반영된다."""
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        self._imgedit_push_undo(st)
        new_rect = self.crop_canvas.get_crop_rect()
        if self.crop_canvas.view_mode == "preview" and st.crop_rect and new_rect:
            ox0, oy0, _, _ = st.crop_rect
            nx0, ny0, nx1, ny1 = new_rect
            st.crop_rect = (ox0 + nx0, oy0 + ny0, ox0 + nx1, oy0 + ny1)
        else:
            st.crop_rect = new_rect
        try:
            img = open_oriented(path)
            self._update_imgedit_info(st, img)
        except Exception:
            pass

    def on_imgedit_ratio_changed(self, index):
        key = self.combo_ratio.currentData()
        self.crop_canvas.set_ratio(key)
        if 0 <= self.imgedit_current < len(self.imgedit_files):
            self.imgedit_states[self.imgedit_files[self.imgedit_current]].ratio = key

    def on_imgedit_open_curve(self):
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.imgedit.select_image_first"))
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        pop = CurvePopover(st.curve_points, parent=self)
        pop.curveChanged.connect(self.crop_canvas.set_curve)   # [v05] 드래그 중 실시간 반영
        pop.curveApplied.connect(self.on_imgedit_curve_applied)
        pop.destroyed.connect(lambda: self.on_imgedit_curve_popover_closed(st))
        # 계획서 3.4: 미리보기 이미지 우측 상단에 팝오버로 표시
        top_right = self.crop_canvas.mapToGlobal(QPoint(self.crop_canvas.width() - 20, 10))
        pop.show()
        pop.move(top_right.x() - pop.width(), top_right.y())
        self.imgedit_curve_popover = pop

    def on_imgedit_curve_popover_closed(self, st):
        """[v50] 팝오버가 닫힐 때(적용/바깥 클릭/Esc 등 방식과 무관하게) 실제로
        값이 바뀌었으면 CurvePopover.closeEvent가 curveApplied를 먼저 emit해
        st.curve_points·화면 렌더링까지 이미 다 끝낸 뒤에 이 콜백이 실행된다.
        그래서 여기서는 팝오버 참조 정리만 하면 되고, 예전처럼 캔버스 커브를
        st.curve_points로 되돌리는 처리는 하지 않는다 — 그 처리가 바로 "커브를
        조정한 뒤 다른 곳을 클릭하면 초기화된다"는 문제의 원인이었고, 지금은
        st.curve_points 자체가 이미 최신 값이라 되돌릴 필요도 없을뿐더러,
        미리보기(적용된) 모드에서는 이미 구워 넣은 이미지 위에 커브를 한 번
        더 덧씌우는 부작용까지 있었다."""
        self.imgedit_curve_popover = None

    def on_imgedit_curve_applied(self, points):
        """[v15] 커브 팝오버에서 '적용'(또는 Space)을 누르면 커브를 확정한다.
        크롭 적용과 마찬가지로 실제 내용이 바뀌는 편집이므로, 썸네일에 배지를
        표시하고 저장 대기 상태로 표시한다(이전에는 커브만 조정했을 때 배지가
        누락되는 문제가 있었음)."""
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        self._imgedit_push_undo(st)
        st.curve_points = points
        st.applied = True
        st.saved = False
        self.logmsg(tr("log.imgedit.curve_adjusted", a0=os.path.basename(st.path)))
        self._imgedit_render(st)
        self._set_thumb_badge(self.imgedit_current, True)

    def on_imgedit_apply(self):
        """현재 이미지의 크롭+커브를 확정하고, 선택 영역만 남은 결과로 화면을 채운다.
        썸네일에는 변경 여부를 나타내는 배지가 표시된다(계획서 3.4 워크플로우).
        [v09] 단축키: Space."""
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        self._imgedit_push_undo(st)
        # [v12] crop_rect는 on_imgedit_crop_changed에서 이미 올바르게(체이닝 크롭 합성
        # 포함) 최신 상태로 관리되고 있으므로 여기서 canvas 값으로 재대입하지 않는다 —
        # 재대입하면 preview 위에 새로 그린 로컬 좌표로 절대 좌표를 덮어써 버려 위치가
        # 어긋나는 버그가 생긴다.
        st.ratio = self.combo_ratio.currentData()
        st.applied = True
        st.saved = False
        self._imgedit_render(st)
        self._set_thumb_badge(self.imgedit_current, True)
        self.logmsg(tr("log.imgedit.applied", a0=os.path.basename(path)))

    def on_imgedit_undo(self):
        """[v13] 되돌리기 — 단축키 Ctrl+Z."""
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        if not st.undo_stack:
            self.status.showMessage(tr("status.imgedit.nothing_to_undo"))
            return
        st.redo_stack.append(st.snapshot())
        st.restore(st.undo_stack.pop())
        self._imgedit_render(st)
        self._set_thumb_badge(self.imgedit_current, st.applied and not st.saved)
        self.combo_ratio.blockSignals(True)
        self.combo_ratio.setCurrentIndex(max(0, self.combo_ratio.findData(st.ratio)))
        self.combo_ratio.blockSignals(False)
        self.logmsg(tr("log.imgedit.undone", a0=os.path.basename(path)))

    def on_imgedit_redo(self):
        """[v13] 재실행 — 단축키 Ctrl+Y."""
        if not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        if not st.redo_stack:
            self.status.showMessage(tr("status.imgedit.nothing_to_redo"))
            return
        st.undo_stack.append(st.snapshot())
        st.restore(st.redo_stack.pop())
        self._imgedit_render(st)
        self._set_thumb_badge(self.imgedit_current, st.applied and not st.saved)
        self.combo_ratio.blockSignals(True)
        self.combo_ratio.setCurrentIndex(max(0, self.combo_ratio.findData(st.ratio)))
        self.combo_ratio.blockSignals(False)
        self.logmsg(tr("log.imgedit.redone", a0=os.path.basename(path)))

    def on_imgedit_convert_to_jpg(self):
        """[v43] 현재 폴더 안의 JPG가 아닌 이미지 전부를 .jpg로 변환한다.
        원본 파일은 건드리지 않고, 같은 폴더에 같은 이름의 .jpg를 새로 만든다.
        투명 배경(RGBA/팔레트 투명)은 흰 배경 위에 합성해 자연스럽게 처리하고,
        변환 결과가 기존의 다른 파일과 이름이 겹치면(예: 우연히 동일 이름의
        .jpg가 이미 있음) 그 파일은 건드리지 않고 건너뛴다."""
        if not self.imgedit_files:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.imgedit.no_folder_loaded"))
            return
        targets = [p for p in self.imgedit_files if not p.lower().endswith((".jpg", ".jpeg"))]
        if not targets:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.imgedit.all_already_jpg"))
            return

        reply = QMessageBox.question(
            self, tr("msg.title.confirm"),
            tr("msg.imgedit.confirm_convert_jpg", n=len(targets)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        ok, skipped, fail = 0, [], []
        try:
            ok = self._convert_jpg_targets(targets, skipped, fail)
        finally:
            self.overlay.stop()

        if ok:
            # 새로 생긴 .jpg가 썸네일 목록에도 보이도록 다시 불러온다
            # [v48] 사진첩 보기라면 새 .jpg를 분석해 행사에 붙인 뒤(albumChanged) 다시 불러온다
            if self.imgedit_view_kind == IMGEDIT_VIEW_ALBUM:
                self.album_panel.start_analysis()
            else:
                self.load_imgedit_folder(self.imgedit_loaded_dir)

        msg = tr("msg.imgedit.convert_result", n=ok)
        if skipped:
            msg += tr("msg.imgedit.convert_skipped_n", n=len(skipped))
        if fail:
            msg += tr("msg.common.fail_list_header") + "\n".join(fail)
            QMessageBox.warning(self, tr("msg.title.done_partial"), msg)
        else:
            QMessageBox.information(self, tr("msg.title.done"), msg)

    def _convert_jpg_targets(self, targets, skipped, fail):
        """[v49.2] JPG 변환 반복문(처리 중 덮개와 함께). 반환: 변환한 수."""
        ok = 0
        total = len(targets)
        for n, p in enumerate(targets):
            self._imgedit_busy("status.imgedit.converting", n, total)
            base, _ = os.path.splitext(p)
            dst = base + ".jpg"
            if os.path.exists(dst):
                skipped.append(os.path.basename(dst))
                self.logmsg(tr("log.imgedit.convert_skip_exists", a0=os.path.basename(dst)))
                continue
            try:
                img = open_oriented(p)   # [v47.2] 세로 사진은 세로 그대로 변환
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[-1])
                    img = bg
                else:
                    img = img.convert("RGB")
                save_keeping_exif(img, dst, source_path=p, format="JPEG")
                ok += 1
                self.logmsg(tr("log.imgedit.converted", a0=os.path.basename(p), a1=os.path.basename(dst)))
            except Exception as e:
                fail.append(f"{os.path.basename(p)} -> {e}")
                self.logmsg(tr("log.imgedit.convert_failed", a0=os.path.basename(p), a1=e))
        self._imgedit_busy("status.imgedit.converting", total, total)
        return ok

    # ---------- [v49.2] 저장·변환 공통 도우미 ----------
    def _busy_step(self, key, done, total):
        """[v49.3] 이름 바꾸기 등 다른 모드도 쓰는 이름."""
        self._imgedit_busy(key, done, total)

    def _imgedit_busy(self, key, done, total):
        """여러 장을 처리하는 동안 "처리 중" 덮개(동기화·중복 찾기와 같은 것)를
        띄우고 진행 수를 갱신한다. 처리는 화면과 같은 스레드에서 하므로, 한 장마다
        화면만 다시 그리고 사용자 입력(클릭·단축키)은 처리하지 않는다."""
        text = tr(key, a0=done, a1=total)
        pct = int(done * 100 / total) if total else None
        if not self.overlay.isVisible():
            self.overlay.start(text, indeterminate=False)
        self.overlay.set_progress(pct, text)
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def _refresh_thumb_from_file(self, path):
        """[v49.2] 파일이 바뀐 뒤(저장) 그 썸네일을 새 파일로 다시 만든다. 썸네일
        캐시는 파일 경로로만 찾기 때문에, 여기서 함께 바꿔 두지 않으면 폴더를 다시
        열어도 예전(크롭 전) 썸네일이 나온다."""
        try:
            pm = self._make_padded_thumb_pixmap(thumbnail_oriented(path, THUMB_SIZE))
        except Exception:   # noqa: BLE001 — 썸네일만 못 바꿨을 뿐, 저장은 끝났다
            return False
        self.imgedit_thumb_base[path] = pm
        self.thumbnail_cache.put(path, pm)
        if path in self.imgedit_files:
            item = self.thumb_list.item(self.imgedit_files.index(path))
            if item is not None:
                item.setIcon(QIcon(pm))
        return True

    def _focus_thumbs(self):
        """[v49.2] 이동·복사·삭제 뒤 키보드 포커스를 썸네일 줄로 — 바로 화살표로
        다음 사진을 볼 수 있게(전에는 숨겨진 대상 폴더 트리에 포커스가 남았다)."""
        if self.thumb_list.count():
            self.thumb_list.setFocus(Qt.OtherFocusReason)

    def on_imgedit_save(self):
        """적용(배지) 표시된 이미지만 실제 디스크에 반영(계획서: 원본 덮어쓰기 기본값).
        [v15] 저장 후에는 crop_rect/curve_points를 초기화한다 — 저장으로 파일이 이미
        크롭·커브가 반영된 더 작은 결과로 덮어써졌으므로, 예전(더 큰 원본 기준) 좌표를
        그대로 남겨두면 다음에 이 이미지를 다시 편집할 때 그 자리를 기준으로 또 크롭을
        시도하다가 이미지 경계를 벗어나 까맣게 패딩된 채로 커브가 덧씌워지는 손상이
        발생한다(사용자 피드백으로 발견됨). 저장 시점을 새로운 기준(원본 상태)으로 리셋."""
        targets = [p for p, st in self.imgedit_states.items() if st.applied and not st.saved]
        if not targets:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.imgedit.nothing_to_save"))
            return
        ok, fail = 0, []
        total = len(targets)
        try:
            for n, p in enumerate(targets):
                self._imgedit_busy("status.imgedit.saving", n, total)
                ok += self._save_one_imgedit(p, fail)
            self._imgedit_busy("status.imgedit.saving", total, total)
        finally:
            self.overlay.stop()
        self._after_imgedit_save(ok, fail)

    def _save_one_imgedit(self, p, fail):
        """[v49.2] 한 장 저장(예전 on_imgedit_save의 반복문 본문). 성공하면 1."""
        st = self.imgedit_states[p]
        try:
            # [v47.2] 화면과 같은 방향(EXIF 방향 적용)에서 크롭 좌표를 쓰고,
            # 저장할 때는 방향 태그만 1로 바꿔 촬영 날짜·GPS 등은 지킨다.
            img = open_oriented(p)
            if st.crop_rect:
                x0, y0, x1, y1 = st.crop_rect
                img = img.crop((int(x0), int(y0), int(x1), int(y1)))
            img = apply_curve_to_image(img, st.curve_points)
            save_keeping_exif(img, p, source_path=p)
            st.saved = True
            # [v15] 저장된 파일이 새로운 "원본"이 되었으므로 이전 크롭/커브 좌표는 폐기
            st.applied = False
            st.crop_rect = None
            st.curve_points = [(0, 0), (255, 255)]
            st.undo_stack.clear()
            st.redo_stack.clear()
            self.logmsg(tr("log.imgedit.saved", a0=os.path.basename(p)))
        except Exception as e:
            fail.append(f"{os.path.basename(p)} -> {e}")
            self.logmsg(tr("log.imgedit.save_failed", a0=os.path.basename(p), a1=e))
            return 0
        # [v49.2] 썸네일도 저장된(크롭된) 파일로 바꾼다
        self._refresh_thumb_from_file(p)
        return 1

    def _after_imgedit_save(self, ok, fail):
        for i, path in enumerate(self.imgedit_files):
            st = self.imgedit_states[path]
            self._set_thumb_badge(i, st.applied and not st.saved)
        if 0 <= self.imgedit_current < len(self.imgedit_files):
            cur_st = self.imgedit_states[self.imgedit_files[self.imgedit_current]]
            try:
                self._update_imgedit_info(cur_st, open_oriented(cur_st.path))
            except Exception:
                pass
        msg = tr("msg.imgedit.save_result", n=ok)
        if fail:
            msg += tr("msg.common.fail_list_header") + "\n".join(fail)
            QMessageBox.warning(self, tr("msg.title.done_partial"), msg)
        else:
            QMessageBox.information(self, tr("msg.title.done"), msg)

    # ---------- [v05] 뷰어 단축키 이동/복사 (FastStone 방식, 계획서 3.5) ----------
    def imgedit_request_move_copy(self, action):
        """[v05] 뷰어 단축키 이동(M)/복사(C) — FastStone 방식(계획서 3.5).
        [v16] 현재 이미지에 적용된(배지 붙은) 변경 사항이 있으면, 저장 후 진행할지
        먼저 물어본다. "예"를 선택하면 저장까지 마친 뒤 대상 폴더 선택 화면으로 넘어가고,
        "아니오"를 선택하면 저장하지 않고(디스크의 기존 파일 그대로) 이동/복사를 진행한다."""
        if self.mode != "imgedit" or not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        st = self.imgedit_states[path]
        if st.applied and not st.saved:
            label = tr("label.move") if action == "move" else tr("label.copy")
            reply = QMessageBox.question(
                self, tr("msg.title.confirm_save"),
                tr("msg.imgedit.save_then_action", a0=label),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.on_imgedit_save()

        self.imgedit_pending_action = action
        label = tr("label.move") if action == "move" else tr("label.copy")
        self.imgedit_dest_hint.setText(tr("imgedit.dest_hint", label=label))
        self.imgedit_viewer_stack.setCurrentIndex(1)
        last = self.imgedit_last_target.get(action)
        if last and os.path.isdir(last):
            idx = self.model_imgedit_dest.index(last)
            if idx.isValid():
                self.tree_imgedit_dest.setCurrentIndex(idx)
                self.tree_imgedit_dest.scrollTo(idx, QAbstractItemView.PositionAtCenter)
                self.imgedit_dest_path = last
        self.tree_imgedit_dest.setFocus()
        self.status.showMessage(tr("status.imgedit.pick_dest", a0=label))

    def on_imgedit_dest_clicked(self, idx):
        p = self.model_imgedit_dest.filePath(idx)
        if os.path.isdir(p):
            self.imgedit_dest_path = p
            self._toggle(self.tree_imgedit_dest, idx)

    def show_imgedit_dest_context_menu(self, pos):
        idx = self.tree_imgedit_dest.indexAt(pos)
        if not idx.isValid():
            return
        p = self.model_imgedit_dest.filePath(idx)
        if not os.path.isdir(p):
            return
        self.imgedit_dest_path = p
        label = tr("label.move") if self.imgedit_pending_action == "move" else tr("label.copy")
        menu = QMenu(self.tree_imgedit_dest)
        act = menu.addAction(tr("imgedit.menu_move_copy_here", label=label))
        chosen = menu.exec(self.tree_imgedit_dest.viewport().mapToGlobal(pos))
        if chosen == act:
            self.on_imgedit_dest_confirm()

    def imgedit_cancel_dest_select(self):
        if self.mode != "imgedit" or self.imgedit_viewer_stack.currentIndex() != 1:
            return
        self.imgedit_pending_action = None
        self.imgedit_viewer_stack.setCurrentIndex(0)
        self._focus_thumbs()
        self.status.showMessage(tr("status.imgedit.loaded_dir", a0=self.imgedit_loaded_dir))

    def on_imgedit_dest_confirm(self):
        if self.mode != "imgedit" or self.imgedit_viewer_stack.currentIndex() != 1:
            return
        action = self.imgedit_pending_action
        dest = self.imgedit_dest_path
        if not action or not dest or not os.path.isdir(dest):
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_dest_first"))
            return
        src = self.imgedit_files[self.imgedit_current]
        try:
            if action == "move":
                shutil.move(src, os.path.join(dest, os.path.basename(src)))
            else:
                shutil.copy2(src, os.path.join(dest, os.path.basename(src)))
            self.imgedit_last_target[action] = dest
            self.logmsg(tr("log.imgedit.move_copy", a0=tr('label.move') if action == 'move' else tr('label.copy'), a1=os.path.basename(src), a2=dest))
        except OSError as e:
            QMessageBox.critical(self, tr("msg.title.error"), tr("msg.common.action_failed", a0=tr('label.move') if action == 'move' else tr('label.copy'), a1=e))
            return
        self.imgedit_pending_action = None
        self.imgedit_viewer_stack.setCurrentIndex(0)
        if action == "move":
            # 이동한 이미지는 현재 폴더 목록/썸네일에서 제거하고 다음 이미지로
            del self.imgedit_files[self.imgedit_current]
            self.imgedit_states.pop(src, None)
            self.imgedit_thumb_base.pop(src, None)
            self.thumbnail_cache.cache.pop(src, None)
            self.thumb_list.takeItem(self.imgedit_current)
            if self.imgedit_files:
                new_row = min(self.imgedit_current, len(self.imgedit_files) - 1)
                self.thumb_list.setCurrentRow(new_row)
            else:
                self.crop_canvas.set_image(None)
                self.imgedit_status_lbl.setText(tr("imgedit.no_image"))
        else:
            next_row = min(self.imgedit_current + 1, len(self.imgedit_files) - 1)
            self.thumb_list.setCurrentRow(next_row)
        self._focus_thumbs()
        self.status.showMessage(tr("status.imgedit.loaded_dir", a0=self.imgedit_loaded_dir))

    def on_imgedit_delete_current(self):
        """[v47] 이미지 편집 모드에서 Del 키로 현재 선택된 사진을 삭제한다.
        확인 팝업의 기본 버튼을 '예'로 두어(다른 삭제 확인과 달리) Enter만
        눌러도 바로 진행되게 했다 — 여러 장을 연속으로 정리할 때 Del → Enter
        → Del → Enter로 빠르게 처리할 수 있도록 하기 위함(사용자 요청)."""
        if self.mode != "imgedit" or not (0 <= self.imgedit_current < len(self.imgedit_files)):
            return
        path = self.imgedit_files[self.imgedit_current]
        name = os.path.basename(path)
        reply = QMessageBox.question(
            self, tr("msg.title.confirm_delete"),
            tr("imgedit.confirm_delete_body", a0=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return
        use_trash = _HAS_SEND2TRASH
        if not use_trash:
            reply2 = QMessageBox.warning(
                self, tr("msg.title.no_trash"), tr("msg.common.no_trash_body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply2 != QMessageBox.Yes:
                return
        while True:
            try:
                if use_trash:
                    send2trash(os.path.normpath(path))
                else:
                    os.remove(path)
                break
            except Exception as e:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle(tr("msg.title.delete_failed"))
                box.setText(tr("msg.common.delete_failed_body", name=name))
                box.setInformativeText(self._explain_os_error(e))
                retry_btn = box.addButton(tr("common.btn_retry"), QMessageBox.AcceptRole)
                box.addButton(tr("common.btn_cancel"), QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is not retry_btn:
                    return
        self.logmsg(tr("log.imgedit.deleted", a0=name,
                        a1=tr("label.trash_moved") if use_trash else tr("label.permanent_deleted")))
        del self.imgedit_files[self.imgedit_current]
        self.imgedit_states.pop(path, None)
        self.thumb_list.takeItem(self.imgedit_current)
        if self.imgedit_files:
            new_row = min(self.imgedit_current, len(self.imgedit_files) - 1)
            self.thumb_list.setCurrentRow(new_row)
        else:
            self.crop_canvas.set_image(None)
            self.imgedit_status_lbl.setText(tr("imgedit.no_image"))
        self._focus_thumbs()
        self.status.showMessage(tr("status.imgedit.loaded_dir", a0=self.imgedit_loaded_dir))

    # ---------- [v09] 파일/폴더 구분 아이콘: 편집 텍스트가 아닌 줄번호 영역에 표시 ----------
    def _confirm_include_folders(self):
        """[v05] 일괄 적용(찾아바꾸기/접두사) 시 폴더명 포함 여부를 먼저 확인(계획서 4절 확정)."""
        if not any(is_dir for _, is_dir in self.rename_entries):
            return False
        reply = QMessageBox.question(
            self, tr("msg.title.include_folder_names"),
            tr("msg.rename.include_folders"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def on_rename_normalize_unicode(self):
        """[v36] 맥(Mac)에서 만든 한글 파일명은 "자모 분리"(NFD) 방식으로
        저장되는 경우가 많다 — 한 음절(가)이 초성+중성 두 개의 코드로
        따로 저장되는 식이다. 윈도우 탐색기는 이걸 정상적으로 합쳐서
        보여주지 못해 글자가 깨진 것처럼 보이지만, FolderKit(Qt)은 화면
        표시는 문제없이 해내기 때문에 "고칠 게 안 보이는" 상황이 된다.
        실제 디스크에 저장된 이름 자체를 윈도우가 쓰는 표준 형태(NFC,
        자모가 합쳐진 한 코드)로 바꿔서, 탐색기에서도 정상적으로 보이게
        만드는 기능이다."""
        if not self.rename_loaded_dir:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_folder_first"))
            return
        folder = self.rename_loaded_dir
        fixed, skipped, failed = [], [], []
        for name, is_dir in list(self.rename_entries):
            norm = unicodedata.normalize("NFC", name)
            if norm == name:
                continue  # 이미 정상(NFC) 상태 — 손댈 필요 없음
            src = os.path.join(folder, name)
            dst = os.path.join(folder, norm)
            if os.path.exists(dst):
                skipped.append(name)
                continue
            try:
                tmp = os.path.join(folder, f".__fk_norm_tmp__{os.getpid()}_{len(fixed)}")
                os.rename(src, tmp)
                os.rename(tmp, dst)
                fixed.append((name, norm))
            except OSError as e:
                failed.append((name, str(e)))

        self._ensure_console_visible()
        if fixed:
            self.logmsg(tr("log.rename.nfc_fixed", a0=len(fixed)))
            for old, new in fixed:
                self.logmsg(f"    {old}  ->  {new}")
        if skipped:
            self.logmsg(tr("log.rename.nfc_skipped", a0=len(skipped)))
            for old in skipped:
                self.logmsg(f"    {old}")
        if failed:
            self.logmsg(tr("log.rename.nfc_failed", a0=len(failed)))
            for old, err in failed:
                self.logmsg(f"    {old} — {err}")
        if not fixed and not skipped and not failed:
            self.logmsg(tr("log.rename.nfc_none"))

        self.load_rename_files(folder)
        msg = tr("msg.rename.nfc_fixed_n", n=len(fixed))
        if skipped:
            msg += tr("msg.rename.nfc_skipped_n", n=len(skipped))
        if failed:
            msg += tr("msg.rename.nfc_failed_n", n=len(failed))
        QMessageBox.information(self, tr("msg.title.normalize_done"), msg)

    def load_rename_files(self, folder):
        """선택된 폴더의 파일 목록을 먼저, 그 다음 서브 폴더 목록을 이어서 불러온다(계획서 4절).
        [v09] 파일/폴더 구분 아이콘(📄/📁)은 편집 대상이 아니므로 텍스트에 넣지 않고
        에디터 줄번호 영역(gutter)에 그린다 — 편집 텍스트는 순수 이름만 담는다."""
        self.editor.clear()
        self.editor.original_filenames = []
        self.editor.line_is_dir = []
        self.rename_entries = []
        try:
            with os.scandir(folder) as it:
                entries = list(it)
            files = sorted(e.name for e in entries
                            if e.is_file(follow_symlinks=False) and not is_excluded(e.name)
                            and not is_hidden_or_system(e))
            dirs = sorted(e.name for e in entries
                           if e.is_dir(follow_symlinks=False) and not is_excluded(e.name)
                           and not is_hidden_or_system(e))
            self.rename_entries = [(n, False) for n in files] + [(n, True) for n in dirs]
            lines = [n for n, _ in self.rename_entries]
            if lines:
                self.editor.setPlainText("\n".join(lines))
                self.editor.original_filenames = lines
                self.editor.line_is_dir = [d for _, d in self.rename_entries]
            self.rename_loaded_dir = folder
            fm = QFontMetrics(self.rename_header.font())
            avail = max(160, self.right_stack.width() - 40)
            label = tr("rename.header.loaded", folder=folder, nfiles=len(files), ndirs=len(dirs))
            self.rename_header.setText(fm.elidedText(label, Qt.ElideMiddle, avail))
            self.rename_header.setToolTip(folder)
            self.logmsg(tr("log.rename.entered", a0=folder, a1=len(files), a2=len(dirs)))
            self.status.showMessage(tr("status.rename.loaded_dir", a0=folder))
        except OSError as e:
            self.logmsg(tr("log.rename.error", a0=e))
            self.status.showMessage(tr("status.common.error", a0=e))

    def on_rename_find_replace(self):
        """임시 바꾸기: 찾기/바꾸기(정규식 또는 와일드카드) 일괄 미리보기 치환.
        폴더 포함 여부를 먼저 확인한 뒤, 이름 텍스트에 바로 적용(아이콘은 gutter에 별도 표시라
        더 이상 텍스트에서 떼어낼 필요가 없음)."""
        find_txt = self.find_input.text()
        replace_txt = self.replace_input.text()
        if not find_txt:
            return
        if self.chk_regex.isChecked():
            pattern_str = find_txt
        else:
            pattern_str = re.escape(find_txt).replace(r'\?', '.').replace(r'\*', '.*')
        try:
            regex = re.compile(pattern_str)
        except re.error:
            QMessageBox.warning(self, tr("msg.title.error"), tr("msg.rename.bad_pattern"))
            return
        include_folders = self._confirm_include_folders()
        lines = self.editor.toPlainText().split("\n")
        new_lines = []
        for i, line in enumerate(lines):
            is_dir = self.rename_entries[i][1] if i < len(self.rename_entries) else False
            if is_dir and not include_folders:
                new_lines.append(line)
                continue
            new_lines.append(regex.sub(replace_txt, line))
        self.editor.setPlainText("\n".join(new_lines))
        self.find_input.clear()
        self.replace_input.clear()

    def on_rename_add_prefix(self):
        """접두사 추가: 모든 줄(폴더 포함 여부에 따라) 맨 앞에 텍스트 삽입."""
        prefix = self.prefix_input.text()
        if not prefix:
            return
        include_folders = self._confirm_include_folders()
        lines = self.editor.toPlainText().split("\n")
        new_lines = []
        for i, line in enumerate(lines):
            is_dir = self.rename_entries[i][1] if i < len(self.rename_entries) else False
            if is_dir and not include_folders:
                new_lines.append(line)
                continue
            new_lines.append(prefix + line)
        self.editor.setPlainText("\n".join(new_lines))
        self.prefix_input.clear()

    def _rename_two_phase(self, changes):
        """[v49.3] 바꿀 파일을 모두 임시 이름으로 옮긴 뒤 새 이름으로 — 이름을 서로
        맞바꾸거나 일련번호를 붙이면서 "아직 안 바꾼 다른 파일의 이름"과 부딪치는 일을
        막는다. 그동안 "처리 중" 덮개를 띄우고 다른 입력은 막는다.
        반환: (성공 수, 실패 기록 목록)"""
        folder = self.rename_loaded_dir
        total = len(changes) * 2
        staged, fail_log, success = [], [], 0
        tag = f".__fk_ren_{os.getpid()}_"
        for i, (orig, new, is_dir) in enumerate(changes):
            self._busy_step("status.rename.applying", i, total)
            tmp = os.path.join(folder, f"{tag}{i}")
            try:
                os.rename(os.path.join(folder, orig), tmp)
                staged.append((orig, new, is_dir, tmp))
            except OSError as e:
                # 다른 프로그램에서 사용 중이거나 권한 문제 등으로 실패한 경우를 포함
                fail_log.append(f"{(tr('label.folder_prefix') if is_dir else '')}{orig} -> {e}")
                self.logmsg(tr("log.rename.apply_failed", a0=orig, a1=new, a2=e))
        for j, (orig, new, is_dir, tmp) in enumerate(staged):
            self._busy_step("status.rename.applying", len(changes) + j, total)
            try:
                os.rename(tmp, os.path.join(folder, new))
                success += 1
                self.logmsg(tr("log.rename.applied_one", a0=tr('label.folder_prefix') if is_dir else '', a1=orig, a2=new))
            except OSError as e:
                fail_log.append(f"{(tr('label.folder_prefix') if is_dir else '')}{orig} -> {e}")
                self.logmsg(tr("log.rename.apply_failed", a0=orig, a1=new, a2=e))
                try:
                    os.rename(tmp, os.path.join(folder, orig))   # 원래 이름으로 되돌린다
                except OSError:
                    pass
        self._busy_step("status.rename.applying", total, total)
        return success, fail_log

    def on_rename_apply(self):
        """이름바꾸기(적용): 실제 os.rename 수행. 파일과 폴더 모두 대상(계획서 4절)."""
        if not self.rename_loaded_dir or not self.rename_entries:
            return
        new_lines = [ln.strip() for ln in self.editor.toPlainText().split("\n")]
        orig_count = len(self.rename_entries)
        new_count = len(new_lines)

        if orig_count != new_count:
            if new_count == orig_count + 1 and new_lines[-1] == "":
                new_lines.pop()
            else:
                QMessageBox.critical(
                    self, tr("msg.title.error"),
                    tr("msg.rename.count_mismatch", a0=orig_count, a1=new_count))
                return

        new_names = new_lines
        # [v49.3] 같은 이름이 여러 줄이면 줄 순서대로 _01, _02 … 를 붙인다(세로 선택으로 여러
        # 줄에 같은 이름을 넣은 경우). 붙인 결과는 아래 확인 창에서 미리 보여 준다.
        is_dirs = [d for _n, d in self.rename_entries]
        new_names, numbered = auto_number_duplicates(new_names, is_dirs)
        if len({n.casefold() for n in new_names}) != len(new_names):
            QMessageBox.critical(self, tr("msg.title.error"), tr("msg.rename.still_duplicate"))
            return
        invalid_chars = re.compile(r'[<>:"/\\|?*]')
        for name in new_names:
            if not name:
                QMessageBox.critical(self, tr("msg.title.error"), tr("msg.rename.empty_name"))
                return
            if invalid_chars.search(name):
                QMessageBox.critical(self, tr("msg.title.error"), tr("msg.rename.invalid_chars", a0=name))
                return

        changes = [(orig, new, is_dir) for (orig, is_dir), new in zip(self.rename_entries, new_names)
                   if orig != new]
        changed_dirs = [orig for orig, new, is_dir in changes if is_dir]

        if not changes:
            return
        # 목록에 없는(숨김·시스템) 파일과 이름이 겹치면 덮어쓰지 않도록 미리 막는다
        listed = {o.casefold() for o, _d in self.rename_entries}
        clash = [new for _o, new, _d in changes
                 if new.casefold() not in listed and os.path.exists(os.path.join(self.rename_loaded_dir, new))]
        if clash:
            QMessageBox.critical(self, tr("msg.title.error"), tr("msg.rename.exists_outside", a0=clash[0]))
            return

        confirm_msg = tr("msg.rename.confirm_simple")
        if changed_dirs:
            # [v05] 폴더명 변경은 하위 경로 전체에 영향을 미치므로 대상 폴더 목록을 명시적으로 보여줌
            preview = "\n".join(f"  · {n}" for n in changed_dirs[:15])
            if len(changed_dirs) > 15:
                preview += tr("msg.rename.more_n", n=len(changed_dirs) - 15)
            confirm_msg = tr("msg.rename.confirm_folder_change", n=len(changed_dirs), preview=preview)
        if numbered:
            lines = []
            for base, count in numbered[:8]:
                stem, ext = os.path.splitext(base)
                width = max(2, len(str(count)))
                lines.append(f"  · {base}  →  {stem}_{'1'.zfill(width)}{ext} ~ {stem}_{str(count).zfill(width)}{ext}")
            confirm_msg = tr("msg.rename.auto_numbered", a0="\n".join(lines)) + "\n\n" + confirm_msg

        # [v49.3] 기본 단추를 "예"로 — Enter만 눌러도 바로 진행
        reply = QMessageBox.question(
            self, tr("msg.title.confirm"), confirm_msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return

        success_count, fail_log = 0, []
        try:
            success_count, fail_log = self._rename_two_phase(changes)
        finally:
            self.overlay.stop()

        result_msg = tr("msg.rename.result", n=success_count)
        if fail_log:
            result_msg += tr("msg.common.fail_list_header") + "\n".join(fail_log)
            QMessageBox.warning(self, tr("msg.title.done_partial"), result_msg)
        else:
            QMessageBox.information(self, tr("msg.title.done"), result_msg)
        self.logmsg(tr("log.rename.apply_done", a0=success_count, a1=len(fail_log)))
        # 방금 변경한 폴더를 다시 로드해 에디터를 최신 상태로 새로고침
        self.load_rename_files(self.rename_loaded_dir)

    # ---------- 환경설정 ----------
    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        accepted = dlg.exec()
        # [v19] '초기화' 버튼은 OK/Cancel과 무관하게 즉시 반영되므로, 다이얼로그가
        # 어떻게 닫혔든 히스토리 콤보를 다시 그려서 초기화 결과를 화면에 반영한다.
        self.refresh_history_combo()
        # [v25] 언어가 바뀌었으면(또는 초기화로 기본값 ko가 됐으면) 즉시 재번역한다.
        if get_language() != self.cfg.language:
            set_language(self.cfg.language)
            self.retranslate_ui()
        # [v37] 썸네일 캐시 크기가 바뀌었으면(또는 '초기화'로 기본값이 됐으면)
        # 이미 만들어진 ThumbnailCache에도 즉시 반영한다. resize()는 줄어든
        # 경우 초과분을 바로 정리하므로 별도 재시작이 필요 없다.
        if self.thumbnail_cache.maxsize != self.cfg.thumb_cache_size:
            self.thumbnail_cache.resize(self.cfg.thumb_cache_size)
            self.logmsg(tr("log.settings.cache_size_changed", a0=self.thumbnail_cache.maxsize))
        # [v45] 즐겨찾기 바로가기 — '초기화' 버튼도 OK/Cancel과 무관하게 즉시
        # self.cfg.quick_links를 바꾸므로, 히스토리 콤보와 마찬가지로 다이얼로그가
        # 어떻게 닫혔든 항상 다시 그린다.
        self.refresh_quicklinks()
        if accepted:
            self.logmsg(tr("log.settings.summary", a0=self.cfg.direction, a1=self.cfg.backup, a2=self.cfg.preview, a3=self.cfg.mirror))

    def retranslate_ui(self):
        """[v25] 환경설정에서 언어를 바꾼 직후 호출 — 창을 새로 만들지 않고,
        이미 떠 있는 위젯들의 문구만 새 언어로 다시 채운다."""
        self.setWindowTitle(tr("app.title", version=APP_VERSION))

        for name, key in (("sync", "mode.sync.tip"), ("rename", "mode.rename.tip"),
                          ("imgedit", "mode.imgedit.tip"), ("dupfind", "mode.dupfind.tip"),
                          ("util", "mode.util.tip")):
            self.mode_buttons[name].setToolTip(tr(key))
        self.btn_set.setToolTip(tr("mode.settings.tip"))

        self.console_toggle.setText(
            tr("console.expanded") if self.log.isVisible() else tr("console.collapsed"))
        self.console_toggle.setToolTip(tr("console.tip"))

        self.btn_view.setText(tr("sync.btn_view")); self.btn_view.setToolTip(tr("sync.btn_view.tip"))
        self.btn_save.setText(tr("sync.btn_save")); self.btn_save.setToolTip(tr("sync.btn_save.tip"))
        self.combo_history.setToolTip(tr("sync.combo_history.tip"))
        self.refresh_history_combo()
        self.btn_copy.setText(tr("sync.btn_copy")); self.btn_copy.setToolTip(tr("sync.btn_copy.tip"))
        self.btn_sync.setText(tr("sync.btn_sync")); self.btn_sync.setToolTip(tr("sync.btn_sync.tip"))

        self.lbl_find.setText(tr("rename.lbl_find"))
        self.lbl_replace.setText(tr("rename.lbl_replace"))
        self.find_input.setPlaceholderText(tr("rename.find_input.placeholder"))
        self.find_input.setToolTip(tr("rename.find_input.tip"))
        self.replace_input.setPlaceholderText(tr("rename.replace_input.placeholder"))
        self.replace_input.setToolTip(tr("rename.replace_input.tip"))
        self.chk_regex.setText(tr("rename.chk_regex")); self.chk_regex.setToolTip(tr("rename.chk_regex.tip"))
        self.help_lbl.setToolTip(tr("rename.help.tip"))
        self.btn_temp.setText(tr("rename.btn_temp")); self.btn_temp.setToolTip(tr("rename.btn_temp.tip"))
        self.prefix_input.setPlaceholderText(tr("rename.prefix_input.placeholder"))
        self.prefix_input.setToolTip(tr("rename.prefix_input.tip"))
        self.btn_prefix.setText(tr("rename.btn_prefix")); self.btn_prefix.setToolTip(tr("rename.btn_prefix.tip"))
        self.btn_normalize.setText(tr("rename.btn_normalize")); self.btn_normalize.setToolTip(tr("rename.btn_normalize.tip"))
        if not self.rename_loaded_dir:
            self.rename_header.setText(tr("rename.header.idle"))
        self.btn_apply.setText(tr("rename.btn_apply")); self.btn_apply.setToolTip(tr("rename.btn_apply.tip"))

        self.lbl_ratio.setText(tr("imgedit.lbl_ratio"))
        self.combo_ratio.setToolTip(tr("imgedit.combo_ratio.tip"))
        # [v41] 항목 텍스트만 새 언어로 다시 쓴다 — itemData(내부 키)는 그대로라
        # 현재 선택(및 저장된 크롭 상태의 st.ratio)이 언어 전환으로 흐트러지지 않는다.
        for i in range(self.combo_ratio.count()):
            self.combo_ratio.setItemText(i, ratio_label(self.combo_ratio.itemData(i)))
        self.lbl_basis.setText(tr("imgedit.lbl_basis"))
        self.combo_basis.setToolTip(tr("imgedit.combo_basis.tip"))
        for i in range(self.combo_basis.count()):
            self.combo_basis.setItemText(i, basis_label(self.combo_basis.itemData(i)))
        self.btn_curve.setText(tr("imgedit.btn_curve")); self.btn_curve.setToolTip(tr("imgedit.btn_curve.tip"))
        self.btn_imgedit_apply.setText(tr("imgedit.btn_apply")); self.btn_imgedit_apply.setToolTip(tr("imgedit.btn_apply.tip"))
        self.btn_imgedit_save.setText(tr("imgedit.btn_save")); self.btn_imgedit_save.setToolTip(tr("imgedit.btn_save.tip"))
        self.btn_imgedit_undo.setText(tr("imgedit.btn_undo")); self.btn_imgedit_undo.setToolTip(tr("imgedit.btn_undo.tip"))
        self.btn_imgedit_redo.setText(tr("imgedit.btn_redo")); self.btn_imgedit_redo.setToolTip(tr("imgedit.btn_redo.tip"))
        self.btn_imgedit_move.setText(tr("imgedit.btn_move")); self.btn_imgedit_move.setToolTip(tr("imgedit.btn_move.tip"))
        self.btn_imgedit_copy.setText(tr("imgedit.btn_copy")); self.btn_imgedit_copy.setToolTip(tr("imgedit.btn_copy.tip"))
        self.btn_imgedit_to_jpg.setText(tr("imgedit.btn_to_jpg")); self.btn_imgedit_to_jpg.setToolTip(tr("imgedit.btn_to_jpg.tip"))
        self.btn_view_folder.setText(tr("album.view.folder"))
        self.btn_view_album.setText(tr("album.view.album"))
        self.album_panel.retranslate()

        self.btn_dupfind_clear.setText(tr("dupfind.btn_clear")); self.btn_dupfind_clear.setToolTip(tr("dupfind.btn_clear.tip"))
        self.btn_dupfind_scan_precise.setText(tr("dupfind.btn_scan_precise")); self.btn_dupfind_scan_precise.setToolTip(tr("dupfind.btn_scan_precise.tip"))
        self.btn_dupfind_scan_fast.setText(tr("dupfind.btn_scan_fast")); self.btn_dupfind_scan_fast.setToolTip(tr("dupfind.btn_scan_fast.tip"))
        self.btn_dupfind_cancel.setText(tr("dupfind.btn_cancel")); self.btn_dupfind_cancel.setToolTip(tr("dupfind.btn_cancel.tip"))
        self.dupfind_model.headerDataChanged.emit(Qt.Horizontal, 0, 2)
        self.dupfind_model.layoutChanged.emit()   # 그룹 줄 "중복 N개" 문구도 새 언어로
        self._dupfind_refresh_target_label()
        self.btn_dupfind_delete.setText(tr("dupfind.btn_delete")); self.btn_dupfind_delete.setToolTip(tr("dupfind.btn_delete.tip"))
        self.btn_dupfind_keep_newest.setText(tr("dupfind.btn_keep_newest")); self.btn_dupfind_keep_newest.setToolTip(tr("dupfind.btn_keep_newest.tip"))
        self.btn_dupfind_move.setText(tr("dupfind.btn_move")); self.btn_dupfind_move.setToolTip(tr("dupfind.btn_move.tip"))

        # [v01] 유틸리티 모드 — 액션 바 문구 + 열려 있는 도구들의 내부 문구까지
        # 함께 새 언어로 바꾼다(아직 열지 않은 도구는 위젯 자체가 없으므로 대상 아님).
        self.btn_util_home.setText(tr("util.btn.home")); self.btn_util_home.setToolTip(tr("util.btn.home.tip"))
        self.util_search.setPlaceholderText(tr("util.search.placeholder"))
        self.util_search.setToolTip(tr("util.search.tip"))
        self.lbl_util_current_cap.setText(tr("util.lbl.current"))
        self.util_panel.retranslate()

    # ---------- 기존 기능: 구조 텍스트 ----------
    def generate_tree_text(self, root):
        """구조 문자열(예전과 같은 모양: 폴더·파일, 정보 없음) — 다른 곳·테스트용.
        [v50.2] 실제 버튼은 화면이 멈추지 않도록 TreeScanThread로 따로 돈다."""
        from .tree_report import scan_tree, render, CONTENT_FILES
        top = scan_tree(root, keep_files=True)
        lines = render(top, tr, self._fmt_size, content=CONTENT_FILES, with_meta=False)
        return "\n".join([root] + lines[lines.index(f"[{top.name}]") + 1:])

    TREE_VIEW_MAX_LINES = 4800    # [v50.2] 콘솔은 5000줄까지만 남으므로 구조는 그 안에서 끊는다

    def _ask_tree_options(self):
        """[v50.2] 폴더만/파일까지 · 깊이 · 정보 표시를 고른다. 취소하면 None.
        내부 값은 키(CONTENT_FOLDERS/CONTENT_FILES)로만 다룬다."""
        from PySide6.QtWidgets import QDialog, QRadioButton, QSpinBox, QDialogButtonBox
        from .tree_report import CONTENT_FOLDERS, CONTENT_FILES
        prev = getattr(self, "_tree_opts", None) or {"content": CONTENT_FOLDERS, "max_depth": 0, "with_meta": True}
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("tree.dlg.title"))
        lay = QVBoxLayout(dlg)
        rb_folders = QRadioButton(tr("tree.dlg.folders"))
        rb_files = QRadioButton(tr("tree.dlg.files"))
        (rb_files if prev["content"] == CONTENT_FILES else rb_folders).setChecked(True)
        lay.addWidget(rb_folders)
        lay.addWidget(rb_files)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("tree.dlg.depth")))
        spin = QSpinBox()
        spin.setRange(0, 99)
        spin.setSpecialValueText(tr("tree.dlg.depth_all"))   # 0 = 끝까지
        spin.setValue(prev["max_depth"])
        row.addWidget(spin)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QLabel(tr("tree.dlg.hint"))
        hint.setStyleSheet("color:#667;")
        lay.addWidget(hint)
        chk = QCheckBox(tr("tree.dlg.meta"))
        chk.setChecked(prev["with_meta"])
        lay.addWidget(chk)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        self._tree_opt_dialog = dlg          # 테스트에서 고를 수 있게
        if dlg.exec() != QDialog.Accepted:
            return None
        opts = {"content": CONTENT_FILES if rb_files.isChecked() else CONTENT_FOLDERS,
                "max_depth": spin.value(), "with_meta": chk.isChecked()}
        self._tree_opts = opts
        return opts

    def _start_tree_report(self, opts, out_path=None):
        """[v50.2] 폴더 스캔 → 글자 만들기(→ 저장)를 화면 밖 스레드에서. 그동안 작업 중
        화면에 읽은 폴더·파일 수를 보여 준다."""
        from .tree_report import TreeScanThread
        th = getattr(self, "tree_thread", None)
        if th is not None and th.isRunning():
            return None
        self.btn_view.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.overlay.start(tr("status.tree.scanning", dirs=0, files=0), indeterminate=True)
        th = TreeScanThread(self.source_path, tr, self._fmt_size, content=opts["content"],
                            max_depth=opts["max_depth"], with_meta=opts["with_meta"],
                            out_path=out_path, max_lines=0 if out_path else self.TREE_VIEW_MAX_LINES)
        th.progress.connect(lambda d, f: self.overlay.set_progress(
            None, tr("status.tree.scanning", dirs=f"{d:,}", files=f"{f:,}")))
        th.stage.connect(lambda _s: self.overlay.set_progress(None, tr("status.tree.writing")))
        th.finished_report.connect(self._on_tree_report_done)
        th.failed.connect(self._on_tree_report_failed)
        th.finished.connect(th.deleteLater)
        self.tree_thread = th
        self._tree_t0 = time.monotonic()
        th.start()
        return th

    def _tree_report_ended(self):
        self.overlay.stop()
        self.btn_view.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.tree_thread = None

    def _on_tree_report_done(self, top, lines):
        th = self.tree_thread
        out_path = th.out_path if th is not None else None
        line_count = th.line_count if th is not None else 0
        self._tree_report_ended()
        if lines is not None:                     # 보기 — 콘솔에(이미 4800줄 안으로 잘라 둠)
            self._ensure_console_visible()
            self.log.clear()
            self.log.setPlainText("\n".join(lines))
        self.logmsg(tr("log.tree.done", path=top.path, dirs=f"{top.total_dirs + 1:,}",
                       files=f"{top.total_files:,}", size=self._fmt_size(top.total_bytes),
                       sec=round(time.monotonic() - self._tree_t0, 1)))
        if out_path:
            self.logmsg(tr("log.tree.saved", path=out_path, lines=f"{line_count:,}"))

    def _on_tree_report_failed(self, err):
        self._tree_report_ended()
        if err:
            QMessageBox.warning(self, tr("msg.title.info"), tr("msg.tree.failed", err=err))

    def show_tree_text(self):
        if not self.source_path:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_folder_first"))
            return
        opts = self._ask_tree_options()
        if opts is None:
            return
        self._ensure_console_visible()  # [v29] 결과가 콘솔에만 출력되므로 미리 펼쳐 둔다
        self._start_tree_report(opts)

    def save_tree_text(self):
        if not self.source_path:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_folder_first"))
            return
        opts = self._ask_tree_options()
        if opts is None:
            return
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               os.path.basename(self.source_path) + "_structure.txt")
        path, _ = QFileDialog.getSaveFileName(self, tr("msg.common.save_structure_text"), default,
                                              "Text (*.txt)")
        if path:
            self._start_tree_report(opts, out_path=path)

    # ---------- 기존 기능: 구조만 복사 ----------
    def start_copy_structure(self):
        if not self.source_path or not self.dest_path:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_both_folders"))
            return
        cnt = 0
        base = os.path.basename(self.source_path)
        dst_root = os.path.join(self.dest_path, base)
        for dirpath, dirnames, _ in os.walk(self.source_path):
            dirnames[:] = [d for d in dirnames if not is_excluded(d)
                           and not is_hidden_or_system(os.path.join(dirpath, d))]
            rel = os.path.relpath(dirpath, self.source_path)
            target = os.path.join(dst_root, rel) if rel != "." else dst_root
            os.makedirs(target, exist_ok=True)
            cnt += 1
        self.logmsg(tr("log.common.structure_copy_done", a0=cnt, a1=dst_root))

    # ---------- 신규 기능: 동기화 ----------
    def start_sync(self):
        if not self.source_path or not self.dest_path:
            QMessageBox.information(self, tr("msg.title.info"), tr("msg.common.select_both_folders"))
            return

        # [v18] 동기화 버튼을 누른 "바로 그 시점"에 실제로 어떤 경로가 비교 대상으로
        # 쓰이는지 로그에 명시적으로 한 번 더 남긴다 — "분명히 다른 폴더를 선택했는데
        # 차이가 없다고 나온다"는 문제를 진단하기 위한 확인용 출력.
        self.logmsg(tr("log.sync.debug_click_left", a0=self.source_path))
        self.logmsg(tr("log.sync.debug_click_right", a0=self.dest_path))
        # [v18] "l2r"/"r2l" 같은 코드값은 로그 글꼴에서 소문자 l과 숫자 1이 헷갈릴 수 있어
        # (예: "l2r"이 "12r"처럼 보임), 사람이 읽는 설명을 함께 남긴다. 특히 단방향
        # 설정에서는 "반대쪽에만 있는 파일"이 의도적으로 무시되므로, 시각적으로는
        # 차이가 있어 보여도 "차이 없음"이 나올 수 있다 — 이게 실제로 가장 흔한 원인이다.
        direction_label = {
            "both": tr("sync.direction_desc.both"),
            "l2r": tr("sync.direction_desc.l2r"),
            "r2l": tr("sync.direction_desc.r2l"),
        }.get(self.cfg.direction, self.cfg.direction)
        self.logmsg(tr("log.sync.debug_direction", a0=direction_label, a1=self.cfg.direction))
        if os.path.normpath(self.source_path) == os.path.normpath(self.dest_path):
            self.logmsg(tr("log.sync.same_path_warning"))

        # 하위 폴더 포함 여부 팝업 (기본 예)
        box = QMessageBox(self)
        box.setWindowTitle(tr("msg.title.sync_scope"))
        box.setText(tr("msg.sync.scope_body"))
        yes = box.addButton(tr("msg.sync.scope_yes"), QMessageBox.YesRole)
        no = box.addButton(tr("msg.sync.scope_no"), QMessageBox.NoRole)
        box.addButton(tr("common.btn_cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (yes, no):
            return
        recursive = (clicked is yes)

        self.logmsg(tr("log.sync.analyze_start", a0=recursive, a1=self.cfg.direction))
        # [v18] 실제로 ScanThread에 넘어가는 값도 한 번 더 확인(팝업 처리 도중 값이
        # 바뀔 가능성까지 배제하기 위해 스레드 생성 직전에도 출력)
        self.logmsg(tr("log.sync.debug_scan_start", a0=self.source_path, a1=self.dest_path))

        # 분석(스캔) 단계는 몇 십 초가 걸릴 수 있어 백그라운드 스레드로 실행하고,
        # 그 동안 화면 전체(top_area)를 디밍 오버레이로 덮어 조작을 막는다.
        # (로그 콘솔은 오버레이 밖이라 계속 갱신되어 보임)
        self.btn_sync.setEnabled(False)
        self.overlay.start(tr("status.sync.checking_targets"), indeterminate=True)
        self.scan_thread = ScanThread(self.source_path, self.dest_path, recursive)
        self.scan_thread.finished_scan.connect(self._on_scan_done)
        self.scan_thread.failed.connect(self._on_scan_failed)
        self.scan_thread.start()

    def _on_scan_failed(self, msg):
        self.overlay.stop()
        self.btn_sync.setEnabled(True)
        self.logmsg(tr("log.sync.analyze_failed", a0=msg))
        QMessageBox.warning(self, tr("msg.title.error"), tr("msg.sync.analyze_error", a0=msg))

    def _on_scan_done(self, rows):
        self.overlay.stop()
        # [v18] 스캔 결과 자체를 진단할 수 있도록, 비교된 총 항목 수와 상태별 분포를
        # 먼저 로그에 남긴다(좌·우 스캔에서 몇 개 항목이 발견됐는지 바로 확인 가능).
        from collections import Counter as _Counter
        state_counts = _Counter(s for _, s in rows)
        self.logmsg(tr("log.sync.scan_done", a0=len(rows), a1=', '.join((f'{k}:{v}' for k, v in state_counts.items())) or tr('label.none')))
        actions = plan_actions(rows, self.cfg.direction, self.cfg.mirror)

        n_conf = sum(1 for _, s in rows if s == CONFLICT)
        if n_conf:
            self.logmsg(tr("log.sync.conflicts", a0=n_conf))

        if not actions:
            self.btn_sync.setEnabled(True)
            # [v18] "차이 없음"이 진짜 SAME이라서인지, 단방향 설정 때문에 반대쪽
            # 전용 항목이 그냥 무시된 것인지를 구분해서 알려준다 — 시각적으로는
            # 분명 차이가 있는데 "차이 없음"이라고만 뜨는 혼란을 없애기 위함.
            ignored = [r for r in rows if r[1] not in (SAME, CONFLICT)]
            if ignored and self.cfg.direction != "both":
                skip_state = ONLY_R if self.cfg.direction == "l2r" else ONLY_L
                skip_side = tr("label.right_side") if self.cfg.direction == "l2r" else tr("label.left_side")
                n_skipped = sum(1 for _, s in ignored if s == skip_state)
                msg = tr("msg.sync.one_way_skipped", direction=self.cfg.direction,
                         side=skip_side, n=n_skipped)
                QMessageBox.information(self, tr("msg.title.sync"), msg)
                self.logmsg(tr("log.sync.nothing_but_skipped", a0=skip_side, a1=n_skipped, a2=self.cfg.direction))
                return
            QMessageBox.information(self, tr("msg.title.sync"), tr("msg.sync.no_diff"))
            self.logmsg(tr("log.sync.no_changes"))
            return

        # 미리보기
        if self.cfg.preview:
            dlg = PreviewDialog(actions, self)
            if not dlg.exec():
                self.btn_sync.setEnabled(True)
                self.logmsg(tr("log.sync.user_cancelled"))
                return
            actions = dlg.selected
            if not actions:
                self.btn_sync.setEnabled(True)
                self.logmsg(tr("log.sync.nothing_selected"))
                return

        self.progress.setValue(0)
        self.thread = SyncThread(self.source_path, self.dest_path, actions,
                                 self.cfg.backup)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished_ok.connect(self._on_sync_done)
        # 실행 단계도 동일하게 대기 상태로 표시 (이번엔 %를 알고 있으니 확정 진행바)
        self.overlay.start(tr("status.sync.running"), indeterminate=False)
        self.thread.start()

    def _on_progress(self, pct, msg):
        self.progress.setValue(pct)
        self.logmsg(msg)
        self.overlay.set_progress(pct, tr("status.sync.running"))

    def _on_sync_done(self, ok, total):
        self.overlay.stop()
        self.progress.setValue(100)
        self.btn_sync.setEnabled(True)
        self.logmsg(tr("log.sync.done", a0=ok, a1=total))
        QMessageBox.information(self, tr("msg.title.sync_done"), tr("msg.sync.done_body", a0=ok, a1=total))
        self.tree_source.viewport().update()
        self.tree_dest.viewport().update()
        # 최근 작업 히스토리에 (좌,우) 폴더 쌍 기록 → 콤보박스 갱신
        self.history.record(self.source_path, self.dest_path)
        self.refresh_history_combo()

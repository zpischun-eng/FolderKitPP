# -*- coding: utf-8 -*-
"""
FolderKit++ — Util 모드 본체 패널 [v01]

화면 구성은 기존 모드들과 같은 문법을 그대로 쓴다:

    [ 좌측 목록 30% ] | [ 우측 작업 영역 70% ]

동기화/파일명 변경/중복 찾기 모드에서 왼쪽에 있던 것이 폴더 트리였다면,
Util 모드에서는 그 자리에 **도구 목록**이 들어간다. 오른쪽은 선택한 도구의
화면이고, 아무것도 고르지 않은 처음 상태에서는 홈(카드 그리드)이 보인다.

미니앱 위젯은 **처음 선택되는 순간에 한 번만** 만든다(지연 생성). 그 뒤로는
스택에 그대로 남아 있으므로, 다른 모드에 갔다 돌아와도 입력하던 내용과
계산 기록이 그대로 유지된다.
"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QStackedWidget, QTreeWidget,
    QTreeWidgetItem, QLabel, QFrame
)

from ..i18n import tr
from ..styles import C
from .base import UtilHost
from .home import HomeGrid
from .icons import make_app_icon

#: 트리 항목이 들고 다니는 내부 키 — 표시 문구가 아니라 이 값으로만 분기한다.
ROLE_KIND = Qt.UserRole        # "home" / "category" / "app"
ROLE_ID = Qt.UserRole + 1      # 도구 id 또는 카테고리 키

_SET_LAST_TOOL = "util.last_tool"
_SET_MRU = "util.mru"
MRU_MAX = 3


class UtilPanel(QWidget):
    """Util 모드 전체(좌측 목록 + 우측 작업 영역)."""

    toolChanged = Signal(str)   # 현재 도구의 표시 이름 — 액션 바 라벨용

    def __init__(self, apps, category_label, category_order, host=None, parent=None):
        super().__init__(parent)
        self.apps = apps
        self.by_id = {a.id: a for a in apps}
        # [v43.10] hidden=True인 도구는 처음엔 목록·홈 화면·최근 사용
        # 어디에도 안 보인다 — 다만 완전히 숨기고 끝나는 게 아니라,
        # 전용 단축키로 한 번 열면(reveal_app) 그 실행 동안은 다른
        # 도구처럼 목록·홈 화면에 계속 나타난다("단축키를 매번 눌러야만
        # 접근 가능한" 게 아니라 "단축키는 처음 꺼내는 열쇠일 뿐"이 되게).
        self._revealed = set()
        self.host = host or UtilHost(None)
        self._category_label = category_label
        self._category_order = category_order
        self._pages = {}          # app.id -> (위젯, 스택 인덱스)
        self.current_id = None    # None이면 홈
        self._mru = []

        self._load_state()
        self._build_ui()
        self._rebuild_tree()

    # ------------------------------------------------------------------ 상태
    def _visible_apps(self):
        """hidden=True가 아니거나, 이번 실행 중 한 번이라도 reveal된 도구."""
        return [a for a in self.apps if not getattr(a, "hidden", False) or a.id in self._revealed]

    def reveal_app(self, app_id):
        """[v43.10] 숨겨 둔 도구를 목록·홈 화면에 나타나게 한다 — 전용
        단축키가 이 도구를 열기 직전에 부른다. 이미 revealed면 아무
        일도 안 한다(중복 재구성 방지)."""
        if app_id in self._revealed:
            return
        self._revealed.add(app_id)
        self._rebuild_tree()
        self.home.refresh_apps(self._visible_apps())

    def _load_state(self):
        s = self.host.settings() if self.host else None
        if s is None:
            return
        raw = s.value(_SET_MRU, "")
        if isinstance(raw, str) and raw:
            self._mru = [i for i in raw.split(",") if i][:MRU_MAX]

    def _save_state(self):
        s = self.host.settings() if self.host else None
        if s is None:
            return
        s.setValue(_SET_LAST_TOOL, self.current_id or "")
        s.setValue(_SET_MRU, ",".join(self._mru))

    # --------------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter)

        # ---- 좌측: 도구 목록 ----
        left = QWidget()
        left.setMinimumWidth(160)   # [버그 수정] collapsible=False와 짝을 이뤄 경계선이 항상 잡히게
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setStyleSheet(
            f"QTreeWidget{{background-color:{C.UTIL_BG};border:1px solid {C.BORDER};"
            f"border-radius:6px;padding:4px;color:{C.TREE_FG};}}"
            f"QTreeWidget::item{{height:26px;}}"
            f"QTreeWidget::item:selected{{background-color:{C.UTIL_MAIN};"
            f"color:#ffffff;border-radius:4px;}}")
        self.tree.itemClicked.connect(self._on_tree_clicked)
        left_lay.addWidget(self.tree, 1)

        self.lbl_empty = QLabel()
        self.lbl_empty.setWordWrap(True)
        self.lbl_empty.setVisible(False)
        self.lbl_empty.setStyleSheet(
            "color:#8a8f98;font-size:11px;background:transparent;padding:2px 4px;")
        left_lay.addWidget(self.lbl_empty)

        self.splitter.addWidget(left)

        # ---- 우측: 작업 영역(홈 + 도구별 페이지) ----
        right = QFrame()
        right.setObjectName("util_work_area")
        right.setStyleSheet(
            f"QFrame#util_work_area{{background-color:#ffffff;"
            f"border:1px solid {C.BORDER};border-radius:6px;}}")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(10, 10, 10, 10)

        self.stack = QStackedWidget()
        right_lay.addWidget(self.stack)

        self.home = HomeGrid(self._visible_apps(), self._category_label)
        self.home.appChosen.connect(self.open_app)
        self.stack.addWidget(self.home)      # index 0 = 홈

        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        # [버그 수정] "스플리터를 왼쪽으로 옮긴 뒤엔 다시 오른쪽으로 못
        # 옮긴다"는 문제의 진짜 원인 — 오른쪽(작업 영역)만 collapsible을
        # 꺼 뒀고, 왼쪽(도구 목록)은 기본값(접을 수 있음)이 그대로
        # 남아 있었다. 왼쪽 칸을 충분히 좁게 끌면 Qt가 그 칸을 아예
        # 접어(너비 0) 버리는데, 그 상태에서는 경계선이 창 맨 왼쪽
        # 끝에 붙어 버려서 다시 마우스로 잡고 오른쪽으로 끌어내기가
        # 사실상 불가능해진다("어떤 패널이 가변 폭으로 안 된다"는
        # 인상은 이 증상에서 왔다). 왼쪽도 접히지 않게 하면 경계선이
        # 항상 잡을 수 있는 위치에 남는다.
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

    # ------------------------------------------------------------------ 목록
    def _rebuild_tree(self, keep_selection=True):
        self.tree.clear()

        home_item = QTreeWidgetItem([tr("util.tree.home")])
        home_item.setIcon(0, make_app_icon("home", C.UTIL_MAIN, 18))
        home_item.setData(0, ROLE_KIND, "home")
        self.tree.addTopLevelItem(home_item)

        # 최근 사용 — 도구가 2개 이상 쌓였을 때만 보여준다(하나뿐일 때는
        # 같은 항목이 두 번 나올 뿐이라 오히려 산만하다).
        mru = [i for i in self._mru if i in self.by_id
              and (not getattr(self.by_id[i], "hidden", False) or i in self._revealed)]
        if len(mru) >= 2:
            recent = QTreeWidgetItem([tr("util.tree.recent")])
            recent.setData(0, ROLE_KIND, "category")
            recent.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(recent)
            for app_id in mru:
                recent.addChild(self._make_app_item(self.by_id[app_id]))
            recent.setExpanded(True)

        by_cat = {}
        for app in self._visible_apps():
            by_cat.setdefault(app.category, []).append(app)
        ordered = [c for c in self._category_order if c in by_cat]
        ordered += [c for c in by_cat if c not in ordered]

        for cat in ordered:
            cat_item = QTreeWidgetItem([self._category_label(cat)])
            cat_item.setData(0, ROLE_KIND, "category")
            cat_item.setData(0, ROLE_ID, cat)
            cat_item.setFlags(Qt.ItemIsEnabled)      # 카테고리 자체는 선택 불가
            self.tree.addTopLevelItem(cat_item)
            for app in by_cat[cat]:
                cat_item.addChild(self._make_app_item(app))
            cat_item.setExpanded(True)

        if keep_selection:
            self._select_tree_item(self.current_id)

    def _make_app_item(self, app):
        item = QTreeWidgetItem([app.title()])
        item.setIcon(0, make_app_icon(app.icon, C.UTIL_MAIN, 18))
        item.setData(0, ROLE_KIND, "app")
        item.setData(0, ROLE_ID, app.id)
        item.setToolTip(0, app.desc())
        return item

    def _select_tree_item(self, app_id):
        """트리에서 해당 도구(또는 홈) 항목을 골라 표시한다."""
        it = self.tree.topLevelItem(0)
        if app_id is None:
            self.tree.setCurrentItem(it)
            return
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, ROLE_ID) == app_id:
                    self.tree.setCurrentItem(child)
                    return

    def _on_tree_clicked(self, item, _col):
        kind = item.data(0, ROLE_KIND)
        if kind == "home":
            self.show_home()
        elif kind == "app":
            self.open_app(item.data(0, ROLE_ID))

    # -------------------------------------------------------------- 화면 전환
    def show_home(self):
        self.current_id = None
        self.stack.setCurrentIndex(0)
        self._select_tree_item(None)
        self.toolChanged.emit(tr("util.tree.home"))
        self._save_state()

    def open_app(self, app_id):
        app = self.by_id.get(app_id)
        if app is None:
            self.show_home()
            return

        # [v43.10] 숨겨 둔 도구를 이 경로(전용 단축키 등)로 열면, 그 순간
        # "꺼내진" 걸로 치고 목록·홈 화면에도 나타나게 한다 — 매번 단축키로만
        # 접근해야 하는 게 아니라, 단축키는 "한 번 꺼내는" 용도로만 쓰인다.
        if getattr(app, "hidden", False):
            self.reveal_app(app_id)

        if app_id not in self._pages:
            # 지연 생성 — 여기서 딱 한 번만 위젯을 만든다. 저장된 명단·이력을
            # 읽어 들이는 도구는 여기서 눈에 띄게 멈칫할 수 있어, 그 동안
            # 디밍 오버레이(점 5개 대기 애니메이션)로 "멈춘 게 아니다"를
            # 보여준다 — 앞으로 무거워질 다른 도구의 첫 실행에도 똑같이 적용된다.
            widget = self.host.run_busy(tr("util.log.opening", a0=app.title()), lambda: app.build(self.host))
            index = self.stack.addWidget(widget)
            self._pages[app_id] = (widget, index)
            self.host.log(tr("util.log.opened", a0=app.title()))

        self.stack.setCurrentIndex(self._pages[app_id][1])
        self.current_id = app_id
        self._select_tree_item(app_id)
        self.toolChanged.emit(app.title())

        if not getattr(app, "hidden", False) or app_id in self._revealed:
            self._mru = [app_id] + [i for i in self._mru if i != app_id]
            del self._mru[MRU_MAX:]
        self._rebuild_tree()
        self._save_state()

    # ---------------------------------------------------------------- 바깥 API
    def on_enter(self):
        """Util 모드로 들어올 때마다 호출 — 마지막에 쓰던 도구를 되살린다."""
        if self.current_id is not None:
            self.toolChanged.emit(self.by_id[self.current_id].title())
            return
        s = self.host.settings() if self.host else None
        last = s.value(_SET_LAST_TOOL, "") if s else ""
        if last and last in self.by_id:
            self.open_app(last)
        else:
            self.show_home()

    def set_filter(self, text):
        """액션 바 검색창과 연동 — 좌측 목록과 홈 카드를 함께 걸러낸다."""
        needle = (text or "").strip().lower()
        self.home.apply_filter(needle)

        any_hit = False
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.data(0, ROLE_KIND) == "home":
                top.setHidden(bool(needle))       # 검색 중에는 홈 항목을 숨긴다
                continue
            cat_hit = False
            for j in range(top.childCount()):
                child = top.child(j)
                app = self.by_id.get(child.data(0, ROLE_ID))
                hit = (not needle or app is None
                       or needle in app.title().lower()
                       or needle in app.desc().lower()
                       or needle in app.id.lower())
                child.setHidden(not hit)
                cat_hit = cat_hit or hit
            top.setHidden(not cat_hit)
            any_hit = any_hit or cat_hit
        self.lbl_empty.setVisible(bool(needle) and not any_hit)

    def has_unsaved(self):
        """열려 있는(=이미 만들어진) 도구 중 하나라도 저장 안 된 변경이 있으면 True."""
        return any(app.has_unsaved() for app_id, app in self.by_id.items()
                   if app_id in self._pages)

    def retranslate(self):
        self.lbl_empty.setText(tr("util.search.no_result"))
        self.home.retranslate()
        for app_id in self._pages:
            self.by_id[app_id].retranslate()
        self._rebuild_tree()
        self.toolChanged.emit(
            self.by_id[self.current_id].title() if self.current_id else tr("util.tree.home"))

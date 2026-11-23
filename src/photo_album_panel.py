# -*- coding: utf-8 -*-
"""
FolderKit++ — 이미지 편집 모드의 "사진첩" 패널 [v48, v49]

왼쪽 패널 위의 [폴더 | 사진첩] 중 "사진첩" 쪽 화면이다. 보관함(갤럭시폰
사진 옮기기에서 정한 그 폴더)의 사진을 **행사·장소·인물**로 묶어 보여 주고,
하나를 고르면 그 사진들이 편집 화면 아래 썸네일 줄에 깔린다.

- 분석은 AlbumAnalyzeThread가 뒤에서 한다(새로 생기거나 바뀐 사진만).
  [v49] 단계: 촬영 시각·배경 → 장소(GPS) → 얼굴(엔진이 있을 때만).
- 행사·인물 이름 바꾸기(더블클릭/F2)·합치기는 이 패널의 오른쪽 클릭 메뉴,
  사진 단위 정정(다른 행사/인물로 옮기기, 새로 만들기, 이 사람 아님)은
  썸네일 줄의 오른쪽 클릭 메뉴(main_window)에서 한다.
- 장소는 GPS에서 정해지는 사실이라 정정 메뉴가 없다.
- 지금 고른 것은 (종류, 키) — 종류는 내부 키 KIND_*.
"""
import os

from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QKeySequence, QShortcut, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMenu, QInputDialog, QFileDialog, QMessageBox, QAbstractItemView,
    QApplication, QProgressBar
)

from .i18n import tr, register_translations, get_language
from .styles import C, button_style, BTN_SECONDARY_SLATE
from . import photo_album_core as AC
from . import face_engine as FE
from . import geo_lookup as GEO

SETTINGS_ORG, SETTINGS_APP = "SRIHS", "FolderSync"
LIBRARY_KEY = "util.phonetransfer.library_dir"   # 사진 옮기기와 같은 보관함을 쓴다

KIND_ROLE = Qt.UserRole + 1
KEY_ROLE = Qt.UserRole + 2
EVENT_ID_ROLE = KEY_ROLE        # (v48 호환 이름)
NEARBY_EVENTS = 6               # 썸네일 메뉴의 "다른 행사로 옮기기"에 바로 보여 줄 앞뒤 행사 수
PERSON_MENU_SIZE = 10           # 썸네일 메뉴의 "다른 인물로 옮기기"에 바로 보여 줄 인물 수

# 고른 것의 종류 — 내부 키
KIND_EVENT = "event"
KIND_PLACE = "place"
KIND_PERSON = "person"
KIND_MINOR = "minor_faces"      # 자주 안 나온 얼굴 묶음
KIND_ENGINE_HELP = "engine_help"
KIND_GROUP = "group"            # 맨 위 "행사/장소/인물" 머리 줄(고를 수 없음)

_ENGINE_MSG_KEYS = {
    FE.NO_CV2: "album.persons.no_cv2",
    FE.NO_MODELS: "album.persons.no_models",
    FE.BAD_MODELS: "album.persons.bad_models",
}
_STAGE_KEYS = {
    AC.STAGE_SCAN: "album.stage.scan",
    AC.STAGE_FEATURES: "album.stage.features",
    AC.STAGE_GPS: "album.stage.gps",
    AC.STAGE_FACES: "album.stage.faces",
}


def load_library_dir():
    return QSettings(SETTINGS_ORG, SETTINGS_APP).value(LIBRARY_KEY, "") or ""


def save_library_dir(path):
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(LIBRARY_KEY, path or "")


def event_dates(info):
    """행사 날짜 문자열 — "2026/11/08" 또는 "2026/11/08 ~ 11/09"."""
    start_text, end_text = AC.event_date_texts(info.start, info.end)
    return start_text if end_text is None else tr("album.event.dates_range", a0=start_text, a1=end_text)


def event_label(info):
    """행사 하나의 화면 이름(표시 시점에만 만든다). [v49.1] 이름을 붙여도 날짜는
    함께 보인다 — "학교 축제 · 2026/11/08 (8장)"."""
    if info.name:
        return tr("album.event.named_dated", a0=info.name, a1=event_dates(info), a2=info.count)
    start_text, end_text = AC.event_date_texts(info.start, info.end)
    if end_text is None:
        return tr("album.event.single", a0=start_text, a1=info.count)
    return tr("album.event.range", a0=start_text, a1=end_text, a2=info.count)


def event_title(info):
    """위쪽 상태 줄·썸네일 메뉴에 붙일 이름(장수 없이). 이름이 있으면 날짜도 함께."""
    if info.name:
        return tr("album.event.title_dated", a0=info.name, a1=event_dates(info))
    return event_dates(info)


# ---- [v49] 장소·인물 이름(표시 시점에만 만든다) ----
def place_group_name(group_key):
    if group_key.startswith("KR-"):
        return tr(f"place.sido.{group_key[3:]}")
    cc = group_key[2:]
    key = f"place.country.{cc}"
    text = tr(key)
    return text if text != key else GEO.country_name_en(cc)


def place_leaf_name(key):
    if key == AC.NO_PLACE:
        return tr("place.none")
    if key.startswith("KR-"):
        code = key[3:]
        if code == "00000":
            return tr("place.kr_other")
        return GEO.municipality_name(code, "ko" if get_language() == "ko" else "en") or code
    gid = key.split("-")[2] if key.count("-") >= 2 else "0"
    return GEO.world_city_name(gid) if gid != "0" else tr("place.city_unknown")


def place_title(key):
    if key == AC.NO_PLACE:
        return tr("place.none")
    if key.count("-") == 1:          # 묶음 키(시·도/나라)
        return place_group_name(key)
    return f"{place_group_name(GEO.group_of(key))} {place_leaf_name(key)}"


def person_title(info):
    return info.name or tr("album.person.unnamed", a0=info.id)


# =============================================================================
class AlbumAnalyzeThread(QThread):
    progress = Signal(str, int, int)              # (단계 키, 끝난 수, 전체 수)
    finished_analysis = Signal(object)            # run_analysis의 결과 dict
    failed = Signal(str)

    def __init__(self, library_dir, with_faces, parent=None):
        super().__init__(parent)
        self._library_dir = library_dir
        self._with_faces = with_faces
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        factory = FE.FaceEngine if self._with_faces else None
        try:
            result = AC.run_analysis(self._library_dir, progress=self.progress.emit,
                                     cancelled=lambda: self._cancel, face_engine_factory=factory)
        except Exception as e:   # noqa: BLE001 — 실패해도 화면이 "분석 중"에 갇히지 않게
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        self.finished_analysis.emit(result)


# =============================================================================
class AlbumPanel(QWidget):
    albumChosen = Signal()          # 행사·장소·인물 중 하나를 골랐다(current_kind/current_key)
    albumChanged = Signal()         # 분석·정정으로 구성이 바뀌었다

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library_dir = load_library_dir()
        self.current_kind = None
        self.current_key = None
        self._events = []           # [EventInfo, ...] (최근 행사가 위)
        self._places = {}           # {장소 키: 사진 수}
        self._persons = []          # [PersonInfo, ...]
        self._minor_ids = []
        self._engine = FE.NO_CV2
        self._thread = None
        self._expanded_places = set()
        self._just_activated = None     # [v49.1] 클릭 한 번에 두 번 불러오지 않도록

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        # [v49.1] 키보드(위/아래 화살표 등)로 옮겨도 마우스 클릭과 똑같이 불러온다
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)
        self.tree.setIconSize(QPixmap(28, 28).size())
        self.tree.setStyleSheet(
            f"QTreeWidget{{background:#ffffff;border:1px solid {C.BORDER};border-radius:5px;}}"
            f"QTreeWidget::item{{padding:2px;}}"
            f"QTreeWidget::item:selected{{background:{C.IMGEDIT_BG};color:{C.WINDOW_FG};}}")
        QShortcut(QKeySequence(Qt.Key_F2), self.tree, activated=self._rename_selected,
                  context=Qt.WidgetShortcut)
        self.group_events = self._make_group()
        self.group_places = self._make_group()
        self.group_persons = self._make_group()
        lay.addWidget(self.tree, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{C.WINDOW_FG};font-size:11px;")
        lay.addWidget(self.lbl_status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.btn_library = QPushButton()
        self.btn_library.setStyleSheet(button_style(BTN_SECONDARY_SLATE, font_size=12))
        self.btn_library.clicked.connect(self._on_pick_library)
        self.btn_analyze = QPushButton()
        self.btn_analyze.setStyleSheet(button_style(C.IMGEDIT_MAIN, font_size=12))
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)
        self.btn_regroup = QPushButton()
        self.btn_regroup.setStyleSheet(button_style(BTN_SECONDARY_SLATE, font_size=12))
        self.btn_regroup.clicked.connect(self._on_regroup)
        for b in (self.btn_library, self.btn_regroup, self.btn_analyze):
            b.setFixedHeight(24)
            row.addWidget(b)
        lay.addLayout(row)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        self.retranslate()

    def _make_group(self):
        item = QTreeWidgetItem(self.tree)
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(0, KIND_ROLE, KIND_GROUP)
        f = item.font(0)
        f.setBold(True)
        item.setFont(0, f)
        item.setExpanded(True)
        return item

    # ---------------------------------------------------------------- 상태
    def store(self):
        return AC.AlbumStore(self.library_dir) if self.library_dir else None

    def has_library(self):
        return bool(self.library_dir) and os.path.isdir(self.library_dir)

    def is_analyzing(self):
        return self._thread is not None

    def engine_status(self):
        return self._engine

    def event_info(self, event_id):
        return next((e for e in self._events if e.id == event_id), None)

    def person_info(self, person_id):
        return next((p for p in self._persons if p.id == person_id), None)

    def events(self):
        return list(self._events)

    def persons(self):
        return list(self._persons)

    def places(self):
        return dict(self._places)

    # v48 호환 — 행사를 고른 경우에만 그 id
    @property
    def current_event_id(self):
        return self.current_key if self.current_kind == KIND_EVENT else None

    @current_event_id.setter
    def current_event_id(self, value):
        if value is None:
            self.current_kind = self.current_key = None
        else:
            self.current_kind, self.current_key = KIND_EVENT, value

    def current_exists(self):
        kind, key = self.current_kind, self.current_key
        if kind == KIND_EVENT:
            return self.event_info(key) is not None
        if kind == KIND_PERSON:
            return self.person_info(key) is not None
        if kind == KIND_MINOR:
            return bool(self._minor_ids)
        if kind == KIND_PLACE:
            return any(k == key or (k != AC.NO_PLACE and GEO.group_of(k) == key) for k in self._places)
        return False

    def current_paths(self):
        """지금 고른 것의 사진(절대 경로, 촬영 순)."""
        if not self.has_library() or not self.current_exists():
            return []
        store = self.store()
        kind, key = self.current_kind, self.current_key
        if kind == KIND_EVENT:
            paths = store.photos_of(key)
        elif kind == KIND_PLACE:
            paths = store.photos_of_place(key)
        elif kind == KIND_PERSON:
            paths = store.photos_of_persons([key])
        elif kind == KIND_MINOR:
            paths = store.photos_of_persons(self._minor_ids)
        else:
            paths = []
        return [p for p in paths if os.path.isfile(p)]

    def current_title(self):
        kind, key = self.current_kind, self.current_key
        if not self.current_exists():
            return ""
        if kind == KIND_EVENT:
            return event_title(self.event_info(key))
        if kind == KIND_PLACE:
            return place_title(key)
        if kind == KIND_PERSON:
            return person_title(self.person_info(key))
        if kind == KIND_MINOR:
            return tr("album.persons.minor_title")
        return ""

    def current_face_owner_ids(self):
        """썸네일 정정(인물)에서 "지금 보고 있는 사람"의 id들."""
        if self.current_kind == KIND_PERSON:
            return [self.current_key]
        if self.current_kind == KIND_MINOR:
            return list(self._minor_ids)
        return []

    # ---------------------------------------------------------------- 진입·새로 고침
    def activate(self):
        """사진첩 화면으로 들어올 때 — 보관함 설정을 다시 읽고(사진 옮기기에서
        바꿨을 수 있다), 목록을 보여 준 뒤 새 사진 분석을 시작한다."""
        latest = load_library_dir()
        if latest != self.library_dir:
            self.library_dir = latest
            self.current_kind = self.current_key = None
        self.refresh()
        if self.has_library():
            self.start_analysis()

    def refresh(self):
        self._engine = FE.status()
        self._events, self._places, self._persons, self._minor_ids = [], {}, [], []
        if self.has_library():
            try:
                store = self.store()
                self._events = store.events()
                self._places = store.place_counts()
                if self._engine == FE.OK:
                    self._persons = store.persons()
                    self._minor_ids = store.minor_person_ids()
            except Exception:   # noqa: BLE001 — DB를 못 열어도 화면은 떠야 한다
                pass
        if self.current_kind is not None and not self.current_exists():
            self.current_kind = self.current_key = None
        self._rebuild_tree()
        self._update_status()
        self._update_buttons()

    def _add_item(self, parent, text, kind, key, tip=None):
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, KIND_ROLE, kind)
        item.setData(0, KEY_ROLE, key)
        if tip:
            item.setToolTip(0, tip)
        if kind == self.current_kind and key == self.current_key:
            item.setSelected(True)
            self.tree.setCurrentItem(item)
        return item

    def _rebuild_tree(self):
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        # ---- 행사
        self.group_events.takeChildren()
        self.group_events.setText(0, tr("album.group.events", a0=len(self._events)))
        for info in self._events:
            self._add_item(self.group_events, event_label(info), KIND_EVENT, info.id, tr("album.event.tip"))
        # ---- 장소: 시·도/나라 → 시·군·구/도시
        self.group_places.takeChildren()
        groups = {}
        for key, n in self._places.items():
            if key == AC.NO_PLACE:
                continue
            groups.setdefault(GEO.group_of(key), []).append((key, n))
        located = sum(n for k, n in self._places.items() if k != AC.NO_PLACE)
        self.group_places.setText(0, tr("album.group.places", a0=located))
        order = sorted(groups.items(), key=lambda kv: (not kv[0].startswith("KR-"), -sum(n for _, n in kv[1])))
        for gkey, leaves in order:
            gitem = self._add_item(self.group_places, tr("album.count", a0=place_group_name(gkey),
                                                          a1=sum(n for _, n in leaves)), KIND_PLACE, gkey)
            for key, n in sorted(leaves, key=lambda kn: -kn[1]):
                self._add_item(gitem, tr("album.count", a0=place_leaf_name(key), a1=n), KIND_PLACE, key)
            gitem.setExpanded(gkey in self._expanded_places
                              or (self.current_kind == KIND_PLACE and self.current_key in [k for k, _ in leaves]))
        if self._places.get(AC.NO_PLACE):
            self._add_item(self.group_places, tr("album.count", a0=tr("place.none"), a1=self._places[AC.NO_PLACE]),
                           KIND_PLACE, AC.NO_PLACE, tr("place.none.tip"))
        # ---- 인물
        self.group_persons.takeChildren()
        self.group_persons.setText(0, tr("album.group.persons", a0=len(self._persons)))
        if self._engine != FE.OK:
            self._add_item(self.group_persons, tr("album.persons.need_engine"), KIND_ENGINE_HELP, self._engine,
                           tr(_ENGINE_MSG_KEYS.get(self._engine, "album.persons.no_cv2"), a0=FE.models_dir()))
        else:
            for info in self._persons:
                item = self._add_item(self.group_persons, tr("album.count", a0=person_title(info), a1=info.count),
                                      KIND_PERSON, info.id, tr("album.person.tip"))
                if info.thumb:
                    pm = QPixmap()
                    if pm.loadFromData(info.thumb):
                        item.setIcon(0, QIcon(pm))
            if self._minor_ids:
                n = len(self.store().photos_of_persons(self._minor_ids)) if self.has_library() else 0
                self._add_item(self.group_persons, tr("album.count", a0=tr("album.persons.minor"), a1=n),
                               KIND_MINOR, "minor", tr("album.persons.minor_tip"))
        for g in (self.group_events, self.group_places, self.group_persons):
            g.setExpanded(True)
        self.tree.blockSignals(False)

    def _on_item_expanded(self, item):
        if item.data(0, KIND_ROLE) == KIND_PLACE:
            self._expanded_places.add(item.data(0, KEY_ROLE))

    def _on_item_collapsed(self, item):
        if item.data(0, KIND_ROLE) == KIND_PLACE:
            self._expanded_places.discard(item.data(0, KEY_ROLE))

    def _update_status(self, progress=None):
        if not self.library_dir:
            self.lbl_status.setText(tr("album.status.no_library"))
            return
        if not self.has_library():
            self.lbl_status.setText(tr("album.status.library_missing", a0=self.library_dir))
            return
        if progress is not None:
            stage, done, total = progress
            self.lbl_status.setText(tr("album.status.analyzing_stage", a0=tr(_STAGE_KEYS.get(stage, "album.stage.scan")),
                                       a1=done, a2=total))
            return
        try:
            total, done = self.store().counts()
        except Exception:   # noqa: BLE001
            total, done = 0, 0
        self.lbl_status.setText(tr("album.status.ready", a0=self.library_dir, a1=done, a2=total))

    def _update_buttons(self):
        busy = self.is_analyzing()
        has = self.has_library()
        self.btn_analyze.setText(tr("album.btn.cancel") if busy else tr("album.btn.analyze"))
        self.btn_analyze.setEnabled(has)
        self.btn_regroup.setEnabled(has and not busy and bool(self._events or self._persons))
        self.btn_library.setEnabled(not busy)
        self.progress.setVisible(busy)

    def retranslate(self):
        self.btn_library.setText(tr("album.btn.library"))
        self.btn_library.setToolTip(tr("album.btn.library.tip"))
        self.btn_regroup.setText(tr("album.btn.regroup"))
        self.btn_regroup.setToolTip(tr("album.btn.regroup.tip"))
        self.btn_analyze.setToolTip(tr("album.btn.analyze.tip"))
        self.refresh()

    # ---------------------------------------------------------------- 보관함
    def _on_pick_library(self):
        path = QFileDialog.getExistingDirectory(self, tr("album.pick_library"), self.library_dir or "")
        if not path:
            return
        self.library_dir = path
        save_library_dir(path)
        self.current_kind = self.current_key = None
        self.refresh()
        self.albumChanged.emit()
        self.start_analysis()

    # ---------------------------------------------------------------- 분석
    def start_analysis(self):
        if self.is_analyzing() or not self.has_library():
            return
        thread = AlbumAnalyzeThread(self.library_dir, FE.status() == FE.OK, self)
        thread.progress.connect(self._on_progress)
        thread.finished_analysis.connect(self._on_analysis_finished)
        thread.failed.connect(self._on_analysis_failed)
        self._thread = thread
        self.progress.setRange(0, 0)
        self._update_buttons()
        self._update_status(progress=(AC.STAGE_SCAN, 0, 0))
        thread.start()

    def _on_analyze_clicked(self):
        if self.is_analyzing():
            self._thread.cancel()
            self.btn_analyze.setEnabled(False)
        else:
            self.start_analysis()

    def _on_progress(self, stage, done, total):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self._update_status(progress=(stage, done, total))

    def _finish_thread(self):
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.wait()
            thread.deleteLater()

    def _on_analysis_finished(self, result):
        self._finish_thread()
        self.refresh()
        if result.get("cancelled"):
            self.lbl_status.setText(tr("album.status.cancelled", a0=result.get("analyzed", 0)))
        self.albumChanged.emit()

    def _on_analysis_failed(self, message):
        self._finish_thread()
        self.refresh()
        self.lbl_status.setText(tr("album.status.failed", a0=message))

    def wait_analysis(self, ms=120000):
        """(테스트·종료용) 분석이 끝날 때까지 기다리고 결과를 화면에 반영한다."""
        thread = self._thread
        if thread is not None:
            thread.wait(ms)
            QApplication.processEvents()

    def shutdown(self):
        thread = self._thread
        if thread is not None:
            thread.cancel()
            thread.wait(10000)

    # ---------------------------------------------------------------- 고르기
    def _on_item_clicked(self, item, _col=0):
        kind = item.data(0, KIND_ROLE)
        if kind in (None, KIND_GROUP):
            return
        if kind == KIND_ENGINE_HELP:
            self.show_engine_help()
            return
        key = item.data(0, KEY_ROLE)
        # 클릭하면 currentItemChanged가 먼저 와서 이미 불러왔다 — 같은 것을 두 번 불러오지
        # 않되, 이미 고른 항목을 다시 누르면(예: 키보드로 고른 뒤 클릭) 다시 불러온다.
        if self._just_activated == (kind, key):
            self._just_activated = None
            return
        self.select(kind, key)

    def _on_current_item_changed(self, current, _previous=None):
        """[v49.1] 키보드로 옮긴 경우. 여러 개를 고르는 Ctrl·Shift 조합 중에는
        (합치기용) 불러오지 않는다. 머리 줄·엔진 안내 줄은 건너뛴다(안내 창은 클릭할 때만)."""
        self._just_activated = None
        if current is None:
            return
        kind = current.data(0, KIND_ROLE)
        if kind in (None, KIND_GROUP, KIND_ENGINE_HELP):
            return
        mods = QApplication.queryKeyboardModifiers()   # 마지막 이벤트가 아니라 지금 실제 키 상태
        if mods & (Qt.ControlModifier | Qt.ShiftModifier):
            return
        key = current.data(0, KEY_ROLE)
        self._just_activated = (kind, key)
        self.select(kind, key)

    def select(self, kind, key):
        self.current_kind, self.current_key = kind, key
        self.albumChosen.emit()

    def select_event(self, event_id):   # v48 호환
        self.select(KIND_EVENT, event_id)

    def show_engine_help(self):
        QMessageBox.information(self, tr("album.persons.help_title"),
                                tr(_ENGINE_MSG_KEYS.get(self._engine, "album.persons.no_cv2"), a0=FE.models_dir())
                                + "\n\n" + tr("album.persons.help_body"))

    def _selected(self, kind):
        return [it.data(0, KEY_ROLE) for it in self.tree.selectedItems() if it.data(0, KIND_ROLE) == kind]

    def _selected_event_ids(self):
        return self._selected(KIND_EVENT)

    # ---------------------------------------------------------------- 정정: 이름·합치기
    def _on_item_double_clicked(self, item, _col=0):
        kind, key = item.data(0, KIND_ROLE), item.data(0, KEY_ROLE)
        if kind == KIND_EVENT:
            self.rename_event_dialog(key)
        elif kind == KIND_PERSON:
            self.rename_person_dialog(key)

    def _rename_selected(self):
        item = self.tree.currentItem()
        if item is not None:
            self._on_item_double_clicked(item)

    def _ask_name(self, title_key, current):
        name, ok = QInputDialog.getText(self, tr(title_key), tr("album.rename.prompt"), text=current or "")
        return (name, True) if ok else (None, False)

    def rename_event_dialog(self, event_id):
        info = self.event_info(event_id)
        if info is None:
            return
        name, ok = self._ask_name("album.rename.title", info.name)
        if ok:
            self.rename_event(event_id, name)

    def rename_person_dialog(self, person_id):
        info = self.person_info(person_id)
        if info is None:
            return
        name, ok = self._ask_name("album.person.rename.title", info.name)
        if ok:
            self.rename_person(person_id, name)

    def rename_event(self, event_id, name):
        self.store().rename_event(event_id, name)
        self.refresh()
        self.albumChanged.emit()

    def rename_person(self, person_id, name):
        self.store().rename_person(person_id, name)
        self.refresh()
        self.albumChanged.emit()

    def merge_events(self, event_ids):
        target = self.store().merge_events(event_ids)
        if target is not None and self.current_kind == KIND_EVENT and self.current_key in event_ids:
            self.current_key = target
        self.refresh()
        self.albumChanged.emit()
        return target

    def merge_persons(self, person_ids):
        target = self.store().merge_persons(person_ids)
        if target is not None and self.current_kind == KIND_PERSON and self.current_key in person_ids:
            self.current_key = target
        self.refresh()
        self.albumChanged.emit()
        return target

    def _on_tree_menu(self, pos):
        events, persons = self._selected(KIND_EVENT), self._selected(KIND_PERSON)
        if not events and not persons:
            return
        is_event = bool(events)
        ids = events if is_event else persons
        info = self.event_info(ids[0]) if is_event else self.person_info(ids[0])
        menu = QMenu(self.tree)
        act_rename = menu.addAction(tr("album.menu.rename"))
        act_auto = menu.addAction(tr("album.menu.auto_name") if is_event else tr("album.menu.clear_name"))
        act_merge = menu.addAction(tr("album.menu.merge", a0=len(ids)) if is_event
                                   else tr("album.menu.merge_persons", a0=len(ids)))
        act_rename.setEnabled(len(ids) == 1)
        act_auto.setEnabled(len(ids) == 1 and bool(getattr(info, "name", None)))
        act_merge.setEnabled(len(ids) >= 2)
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is act_rename:
            (self.rename_event_dialog if is_event else self.rename_person_dialog)(ids[0])
        elif chosen is act_auto:
            (self.rename_event if is_event else self.rename_person)(ids[0], None)
        elif chosen is act_merge:
            target = self.merge_events(ids) if is_event else self.merge_persons(ids)
            if target is not None:
                self.select(KIND_EVENT if is_event else KIND_PERSON, target)

    def _on_regroup(self):
        reply = QMessageBox.question(self, tr("album.regroup.title"), tr("album.regroup.body"),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        store = self.store()
        store.regroup()
        if self._engine == FE.OK:
            store.regroup_persons()
        self.refresh()   # 보고 있던 것이 그대로 남아 있으면 선택도 유지된다(사라졌으면 refresh가 비운다)
        self.albumChanged.emit()

    # ---------------------------------------------------------------- 정정: 사진(썸네일 메뉴에서 부름)
    def nearby_events(self, event_id, n=NEARBY_EVENTS):
        """event_id 앞뒤(시간 순)의 행사들 — 경계를 잘못 나눈 경우가 대부분이라
        옮길 곳으로 가장 먼저 보여 준다. 시간 순으로(이른 것부터) 돌려준다."""
        ordered = sorted(self._events, key=lambda e: (e.start, e.id))
        idx = next((i for i, e in enumerate(ordered) if e.id == event_id), None)
        if idx is None:
            return ordered[:n]
        lo, hi = max(0, idx - n // 2), min(len(ordered), idx + n // 2 + 1)
        return [e for e in ordered[lo:hi] if e.id != event_id]

    def top_persons(self, exclude_id=None, n=PERSON_MENU_SIZE):
        """옮길 곳 후보 — 이름 붙인 인물, 그다음 사진이 많은 인물 순(persons()의 순서)."""
        return [p for p in self._persons if p.id != exclude_id][:n]

    def choose_event_dialog(self, exclude_id=None):
        """모든 행사 중에서 하나 고르기. 반환: 행사 id 또는 None."""
        choices = [e for e in self._events if e.id != exclude_id]
        if not choices:
            return None
        labels = [event_label(e) for e in choices]
        label, ok = QInputDialog.getItem(self, tr("album.choose.title"), tr("album.choose.prompt"),
                                         labels, 0, False)
        return choices[labels.index(label)].id if ok else None

    def choose_person_dialog(self, exclude_id=None):
        choices = [p for p in self._persons if p.id != exclude_id]
        if not choices:
            return None
        labels = [tr("album.count", a0=person_title(p), a1=p.count) for p in choices]
        label, ok = QInputDialog.getItem(self, tr("album.choose_person.title"), tr("album.choose_person.prompt"),
                                         labels, 0, False)
        return choices[labels.index(label)].id if ok else None

    def move_photos(self, paths, event_id):
        self.store().move_photos(paths, event_id)
        self.refresh()
        self.albumChanged.emit()

    def split_photos(self, paths):
        event_id = self.store().new_event_with(paths)
        self.refresh()
        self.albumChanged.emit()
        return event_id

    def move_faces(self, paths, person_id):
        n = self.store().move_faces(paths, self.current_face_owner_ids(), person_id)
        self.refresh()
        self.albumChanged.emit()
        return n

    def split_faces(self, paths):
        pid = self.store().new_person_with(paths, self.current_face_owner_ids())
        self.refresh()
        self.albumChanged.emit()
        return pid

    def exclude_faces(self, paths):
        n = self.store().exclude_faces(paths, self.current_face_owner_ids())
        self.refresh()
        self.albumChanged.emit()
        return n


# =============================================================================
TRANSLATIONS = {
    "album.view.folder": {"ko": "폴더", "en": "Folders", "ja": "フォルダ"},
    "place.sido.11": {"ko": "서울", "en": "Seoul", "ja": "ソウル"},
    "place.sido.21": {"ko": "부산", "en": "Busan", "ja": "釜山"},
    "place.sido.22": {"ko": "대구", "en": "Daegu", "ja": "大邱"},
    "place.sido.23": {"ko": "인천", "en": "Incheon", "ja": "仁川"},
    "place.sido.24": {"ko": "광주", "en": "Gwangju", "ja": "光州"},
    "place.sido.25": {"ko": "대전", "en": "Daejeon", "ja": "大田"},
    "place.sido.26": {"ko": "울산", "en": "Ulsan", "ja": "蔚山"},
    "place.sido.29": {"ko": "세종", "en": "Sejong", "ja": "世宗"},
    "place.sido.31": {"ko": "경기", "en": "Gyeonggi", "ja": "京畿"},
    "place.sido.32": {"ko": "강원", "en": "Gangwon", "ja": "江原"},
    "place.sido.33": {"ko": "충북", "en": "Chungbuk", "ja": "忠清北道"},
    "place.sido.34": {"ko": "충남", "en": "Chungnam", "ja": "忠清南道"},
    "place.sido.35": {"ko": "전북", "en": "Jeonbuk", "ja": "全羅北道"},
    "place.sido.36": {"ko": "전남", "en": "Jeonnam", "ja": "全羅南道"},
    "place.sido.37": {"ko": "경북", "en": "Gyeongbuk", "ja": "慶尚北道"},
    "place.sido.38": {"ko": "경남", "en": "Gyeongnam", "ja": "慶尚南道"},
    "place.sido.39": {"ko": "제주", "en": "Jeju", "ja": "済州"},
    "place.country.JP": {"ko": "일본", "en": "Japan", "ja": "日本"},
    "place.country.CN": {"ko": "중국", "en": "China", "ja": "中国"},
    "place.country.TW": {"ko": "대만", "en": "Taiwan", "ja": "台湾"},
    "place.country.HK": {"ko": "홍콩", "en": "Hong Kong", "ja": "香港"},
    "place.country.MO": {"ko": "마카오", "en": "Macao", "ja": "マカオ"},
    "place.country.US": {"ko": "미국", "en": "United States", "ja": "アメリカ"},
    "place.country.CA": {"ko": "캐나다", "en": "Canada", "ja": "カナダ"},
    "place.country.VN": {"ko": "베트남", "en": "Vietnam", "ja": "ベトナム"},
    "place.country.TH": {"ko": "태국", "en": "Thailand", "ja": "タイ"},
    "place.country.PH": {"ko": "필리핀", "en": "Philippines", "ja": "フィリピン"},
    "place.country.SG": {"ko": "싱가포르", "en": "Singapore", "ja": "シンガポール"},
    "place.country.MY": {"ko": "말레이시아", "en": "Malaysia", "ja": "マレーシア"},
    "place.country.ID": {"ko": "인도네시아", "en": "Indonesia", "ja": "インドネシア"},
    "place.country.KH": {"ko": "캄보디아", "en": "Cambodia", "ja": "カンボジア"},
    "place.country.LA": {"ko": "라오스", "en": "Laos", "ja": "ラオス"},
    "place.country.MN": {"ko": "몽골", "en": "Mongolia", "ja": "モンゴル"},
    "place.country.IN": {"ko": "인도", "en": "India", "ja": "インド"},
    "place.country.AU": {"ko": "호주", "en": "Australia", "ja": "オーストラリア"},
    "place.country.NZ": {"ko": "뉴질랜드", "en": "New Zealand", "ja": "ニュージーランド"},
    "place.country.GU": {"ko": "괌", "en": "Guam", "ja": "グアム"},
    "place.country.MP": {"ko": "사이판(북마리아나)", "en": "Northern Mariana Islands", "ja": "北マリアナ諸島"},
    "place.country.FR": {"ko": "프랑스", "en": "France", "ja": "フランス"},
    "place.country.GB": {"ko": "영국", "en": "United Kingdom", "ja": "イギリス"},
    "place.country.DE": {"ko": "독일", "en": "Germany", "ja": "ドイツ"},
    "place.country.IT": {"ko": "이탈리아", "en": "Italy", "ja": "イタリア"},
    "place.country.ES": {"ko": "스페인", "en": "Spain", "ja": "スペイン"},
    "place.country.PT": {"ko": "포르투갈", "en": "Portugal", "ja": "ポルトガル"},
    "place.country.CH": {"ko": "스위스", "en": "Switzerland", "ja": "スイス"},
    "place.country.AT": {"ko": "오스트리아", "en": "Austria", "ja": "オーストリア"},
    "place.country.NL": {"ko": "네덜란드", "en": "Netherlands", "ja": "オランダ"},
    "place.country.BE": {"ko": "벨기에", "en": "Belgium", "ja": "ベルギー"},
    "place.country.CZ": {"ko": "체코", "en": "Czechia", "ja": "チェコ"},
    "place.country.HU": {"ko": "헝가리", "en": "Hungary", "ja": "ハンガリー"},
    "place.country.GR": {"ko": "그리스", "en": "Greece", "ja": "ギリシャ"},
    "place.country.TR": {"ko": "튀르키예", "en": "Türkiye", "ja": "トルコ"},
    "place.country.RU": {"ko": "러시아", "en": "Russia", "ja": "ロシア"},
    "place.country.KP": {"ko": "북한", "en": "North Korea", "ja": "北朝鮮"},
    "place.country.MX": {"ko": "멕시코", "en": "Mexico", "ja": "メキシコ"},
    "place.country.BR": {"ko": "브라질", "en": "Brazil", "ja": "ブラジル"},
    "place.country.AE": {"ko": "아랍에미리트", "en": "United Arab Emirates", "ja": "アラブ首長国連邦"},
    "place.country.EG": {"ko": "이집트", "en": "Egypt", "ja": "エジプト"},
    "album.group.places": {"ko": "장소 ({a0}장)", "en": "Places ({a0})", "ja": "場所（{a0}枚）"},
    "album.group.persons": {"ko": "인물 ({a0})", "en": "People ({a0})", "ja": "人物（{a0}）"},
    "album.count": {"ko": "{a0} ({a1})", "en": "{a0} ({a1})", "ja": "{a0}（{a1}）"},
    "place.none": {"ko": "위치 정보 없음", "en": "No location", "ja": "位置情報なし"},
    "place.none.tip": {
        "ko": "GPS 정보가 없는 사진입니다(카메라의 위치 태그가 꺼져 있었거나, 메신저로 받은 사진 등).",
        "en": "Photos without GPS (location tagging was off, or received via messenger, etc.).",
        "ja": "GPS情報のない写真です（カメラの位置情報タグがオフ、メッセンジャーで受け取った写真など）。"},
    "place.kr_other": {"ko": "대한민국(바다 등)", "en": "Korea (at sea, etc.)", "ja": "韓国（海上など）"},
    "place.city_unknown": {"ko": "(도시 없음)", "en": "(no nearby city)", "ja": "（近くの都市なし）"},
    "album.person.unnamed": {"ko": "인물 {a0}", "en": "Person {a0}", "ja": "人物 {a0}"},
    "album.person.tip": {
        "ko": "더블클릭(F2)으로 이름 붙이기 · 여러 명을 골라 오른쪽 클릭하면 같은 사람으로 합치기",
        "en": "Double-click (F2) to name · select several and right-click to merge as one person",
        "ja": "ダブルクリック（F2）で名前付け · 複数選んで右クリックで同一人物として結合"},
    "album.person.rename.title": {"ko": "인물 이름", "en": "Person's Name", "ja": "人物の名前"},
    "album.persons.need_engine": {"ko": "인물 분류 엔진 설치 필요 (눌러서 안내 보기)",
                                  "en": "Face engine not installed (click for help)",
                                  "ja": "人物分類エンジンが必要です（クリックで案内）"},
    "album.persons.no_cv2": {
        "ko": "얼굴 인식에 필요한 opencv-python이 설치돼 있지 않습니다.",
        "en": "opencv-python, needed for face recognition, is not installed.",
        "ja": "顔認識に必要な opencv-python がインストールされていません。"},
    "album.persons.no_models": {
        "ko": "얼굴 모델 파일이 없습니다. 다음 폴더에 모델 두 개를 넣어 주세요:\n{a0}",
        "en": "Face model files are missing. Put the two model files in:\n{a0}",
        "ja": "顔モデルファイルがありません。次のフォルダにモデル2つを入れてください:\n{a0}"},
    "album.persons.bad_models": {
        "ko": "얼굴 모델 파일이 원본과 다릅니다(손상되었거나 다른 파일). 다시 받아 넣어 주세요:\n{a0}",
        "en": "The face model files don't match the originals (damaged or different). Replace them in:\n{a0}",
        "ja": "顔モデルファイルが原本と異なります（破損または別のファイル）。入れ直してください:\n{a0}"},
    "album.persons.help_title": {"ko": "인물 분류 엔진", "en": "Face Engine", "ja": "人物分類エンジン"},
    "album.persons.help_body": {
        "ko": "인물별 사진첩은 선택 설치 기능입니다.\n"
              "① 명령 프롬프트에서: pip install opencv-python\n"
              "② FolderKitPP_FaceModels.zip을 풀어 나온 models 폴더를 프로그램 폴더에 넣기\n"
              "③ 사진첩을 다시 열면 얼굴 분석이 시작됩니다.\n\n"
              "얼굴 정보는 이 컴퓨터의 보관함 안(.folderkit)에만 저장되고 밖으로 보내지 않습니다.",
        "en": "People albums are an optional feature.\n"
              "① In a command prompt: pip install opencv-python\n"
              "② Unzip FolderKitPP_FaceModels.zip and put the models folder next to the program\n"
              "③ Reopen Albums and face analysis starts.\n\n"
              "Face data stays in the library (.folderkit) on this computer and is never sent anywhere.",
        "ja": "人物別アルバムは任意でインストールする機能です。\n"
              "① コマンドプロンプトで: pip install opencv-python\n"
              "② FolderKitPP_FaceModels.zip を展開し、models フォルダをプログラムのフォルダに入れる\n"
              "③ アルバムを開き直すと顔の分析が始まります。\n\n"
              "顔の情報はこのパソコンの保管フォルダ（.folderkit）にだけ保存され、外部には送りません。"},
    "album.persons.minor": {"ko": "자주 안 나온 얼굴", "en": "Rarely seen faces", "ja": "あまり写っていない顔"},
    "album.persons.minor_title": {"ko": "자주 안 나온 얼굴", "en": "Rarely seen faces", "ja": "あまり写っていない顔"},
    "album.persons.minor_tip": {
        "ko": "사진이 두 장 이하인 얼굴들입니다. 아는 사람이면 썸네일 오른쪽 클릭으로 인물에 넣을 수 있습니다.",
        "en": "Faces in two photos or fewer. If you know them, right-click a thumbnail to assign a person.",
        "ja": "写真が2枚以下の顔です。知っている人ならサムネイルを右クリックして人物に入れられます。"},
    "album.status.analyzing_stage": {"ko": "{a0} {a1}/{a2}", "en": "{a0} {a1}/{a2}", "ja": "{a0} {a1}/{a2}"},
    "album.stage.scan": {"ko": "보관함 훑는 중…", "en": "Scanning library…", "ja": "保管フォルダを確認中…"},
    "album.stage.features": {"ko": "새 사진 분석 중…", "en": "Analyzing new photos…", "ja": "新しい写真を分析中…"},
    "album.stage.gps": {"ko": "장소 읽는 중…", "en": "Reading locations…", "ja": "場所を読み取り中…"},
    "album.stage.faces": {"ko": "얼굴 찾는 중…", "en": "Finding faces…", "ja": "顔を探しています…"},
    "album.menu.clear_name": {"ko": "이름 지우기", "en": "Clear name", "ja": "名前を消す"},
    "album.menu.merge_persons": {"ko": "선택한 {a0}명을 같은 사람으로 합치기", "en": "Merge {a0} selected as one person",
                                 "ja": "選択した{a0}人を同一人物として結合"},
    "album.choose_person.title": {"ko": "옮길 인물", "en": "Move to Person", "ja": "移動先の人物"},
    "album.choose_person.prompt": {"ko": "어느 사람으로 옮길까요?", "en": "Which person?", "ja": "どの人物に移しますか？"},
    "album.thumb.move_person": {"ko": "다른 인물로 옮기기", "en": "Move to another person", "ja": "別の人物へ移動"},
    "album.thumb.new_person": {"ko": "선택한 {a0}장의 얼굴로 새 인물 만들기", "en": "New person from {a0} selected",
                               "ja": "選択した{a0}枚の顔で新しい人物を作る"},
    "album.thumb.not_person": {"ko": "이 사람이 아님 ({a0}장에서 빼기)", "en": "Not this person (remove from {a0})",
                               "ja": "この人ではない（{a0}枚から外す）"},
    "log.album.faces_moved": {"ko": "[사진첩] 얼굴 {a0}개를 다른 인물로 옮겼습니다", "en": "[Albums] Moved {a0} face(s) to another person",
                              "ja": "[アルバム] 顔{a0}件を別の人物へ移動しました"},
    "log.album.faces_split": {"ko": "[사진첩] 새 인물을 만들었습니다", "en": "[Albums] Created a new person",
                              "ja": "[アルバム] 新しい人物を作りました"},
    "log.album.faces_excluded": {"ko": "[사진첩] 얼굴 {a0}개를 인물에서 뺐습니다", "en": "[Albums] Removed {a0} face(s) from the person",
                                 "ja": "[アルバム] 顔{a0}件を人物から外しました"},
    "album.view.album": {"ko": "사진첩", "en": "Albums", "ja": "アルバム"},
    "album.group.events": {"ko": "행사 ({a0})", "en": "Events ({a0})", "ja": "イベント（{a0}）"},
    "album.event.single": {"ko": "{a0} ({a1}장)", "en": "{a0} ({a1} photos)", "ja": "{a0}（{a1}枚）"},
    "album.event.range": {"ko": "{a0} ~ {a1} ({a2}장)", "en": "{a0} ~ {a1} ({a2} photos)", "ja": "{a0} ~ {a1}（{a2}枚）"},
    "album.event.named": {"ko": "{a0} ({a1}장)", "en": "{a0} ({a1} photos)", "ja": "{a0}（{a1}枚）"},
    "album.event.named_dated": {"ko": "{a0} · {a1} ({a2}장)", "en": "{a0} · {a1} ({a2} photos)",
                                "ja": "{a0} · {a1}（{a2}枚）"},
    "album.event.title_dated": {"ko": "{a0} · {a1}", "en": "{a0} · {a1}", "ja": "{a0} · {a1}"},
    "album.event.dates_range": {"ko": "{a0} ~ {a1}", "en": "{a0} ~ {a1}", "ja": "{a0} ~ {a1}"},
    "album.event.tip": {
        "ko": "더블클릭(F2)으로 이름 바꾸기 · 여러 개를 골라 오른쪽 클릭하면 합치기",
        "en": "Double-click (F2) to rename · select several and right-click to merge",
        "ja": "ダブルクリック（F2）で名前変更 · 複数選んで右クリックで結合"},
    "album.status.no_library": {
        "ko": "보관함 폴더가 없습니다. \"보관함\"을 눌러 정하세요(갤럭시폰 사진 옮기기와 같은 폴더를 씁니다).",
        "en": "No library folder yet. Press \"Library\" to choose one (shared with Phone Transfer).",
        "ja": "保管フォルダがありません。「保管先」を押して決めてください（写真転送と同じフォルダを使います）。"},
    "album.status.library_missing": {
        "ko": "보관함 폴더를 찾을 수 없습니다: {a0}", "en": "Library folder not found: {a0}",
        "ja": "保管フォルダが見つかりません: {a0}"},
    "album.status.analyzing": {"ko": "새 사진 분석 중… {a0}/{a1}", "en": "Analyzing new photos… {a0}/{a1}",
                               "ja": "新しい写真を分析中… {a0}/{a1}"},
    "album.status.ready": {"ko": "보관함 {a0} · 분석 {a1}/{a2}장", "en": "Library {a0} · analyzed {a1}/{a2}",
                           "ja": "保管先 {a0} · 分析 {a1}/{a2}枚"},
    "album.status.cancelled": {
        "ko": "분석을 멈췄습니다({a0}장까지). \"분석\"을 누르면 이어서 합니다.",
        "en": "Analysis stopped ({a0} done). Press \"Analyze\" to continue.",
        "ja": "分析を止めました（{a0}枚まで）。「分析」を押すと続きから行います。"},
    "album.status.failed": {"ko": "분석하지 못했습니다: {a0}", "en": "Analysis failed: {a0}", "ja": "分析できませんでした: {a0}"},
    "album.btn.library": {"ko": "보관함", "en": "Library", "ja": "保管先"},
    "album.btn.library.tip": {"ko": "사진첩으로 정리할 보관함 폴더를 고릅니다",
                              "en": "Choose the library folder to organize", "ja": "整理する保管フォルダを選びます"},
    "album.btn.analyze": {"ko": "분석", "en": "Analyze", "ja": "分析"},
    "album.btn.analyze.tip": {"ko": "새로 생기거나 바뀐 사진만 분석해 행사에 붙입니다",
                              "en": "Analyze only new or changed photos and add them to events",
                              "ja": "新しく増えた・変わった写真だけを分析してイベントに加えます"},
    "album.btn.cancel": {"ko": "멈춤", "en": "Stop", "ja": "停止"},
    "album.btn.regroup": {"ko": "다시 분류", "en": "Regroup", "ja": "再分類"},
    "album.btn.regroup.tip": {"ko": "직접 고친 것은 그대로 두고 나머지를 다시 묶습니다",
                              "en": "Regroup everything except what you fixed yourself",
                              "ja": "自分で直したものはそのままにして、残りをまとめ直します"},
    "album.pick_library": {"ko": "보관함 폴더 선택", "en": "Choose Library Folder", "ja": "保管フォルダを選択"},
    "album.rename.title": {"ko": "행사 이름", "en": "Event Name", "ja": "イベント名"},
    "album.rename.prompt": {"ko": "이름(비우면 날짜로 표시):", "en": "Name (leave empty to show the date):",
                            "ja": "名前（空にすると日付で表示）:"},
    "album.menu.rename": {"ko": "이름 바꾸기", "en": "Rename", "ja": "名前を変更"},
    "album.menu.auto_name": {"ko": "날짜 이름으로 되돌리기", "en": "Back to date name", "ja": "日付の名前に戻す"},
    "album.menu.merge": {"ko": "선택한 행사 {a0}개 합치기", "en": "Merge {a0} selected events",
                         "ja": "選択したイベント{a0}件を結合"},
    "album.regroup.title": {"ko": "다시 분류", "en": "Regroup", "ja": "再分類"},
    "album.regroup.body": {
        "ko": "직접 손댄 행사·인물(옮기거나 나누거나 합치거나 이름을 붙인 것)은 그대로 두고, "
              "나머지를 다시 묶습니다.\n계속할까요?",
        "en": "Events and people you changed (moved, split, merged, or named) stay as they are; the rest are regrouped.\nContinue?",
        "ja": "自分で手を加えたイベント・人物（移動・分割・結合・名前付けしたもの）はそのままにして、"
              "残りをまとめ直します。\n続けますか？"},
    "album.choose.title": {"ko": "옮길 행사", "en": "Move to Event", "ja": "移動先のイベント"},
    "album.choose.prompt": {"ko": "어느 행사로 옮길까요?", "en": "Which event?", "ja": "どのイベントに移しますか？"},
    "album.thumb.move_to": {"ko": "다른 행사로 옮기기", "en": "Move to another event", "ja": "別のイベントへ移動"},
    "album.thumb.move_more": {"ko": "목록에서 고르기…", "en": "Choose from list…", "ja": "一覧から選ぶ…"},
    "album.thumb.split": {"ko": "선택한 {a0}장으로 새 행사 만들기", "en": "New event from {a0} selected",
                          "ja": "選択した{a0}枚で新しいイベントを作る"},
    "album.thumb.unsaved": {
        "ko": "옮기려는 사진 중에 저장하지 않은 편집이 있습니다. 편집을 버리고 옮길까요?",
        "en": "Some of these photos have unsaved edits. Discard the edits and move them?",
        "ja": "移動する写真に保存していない編集があります。編集を破棄して移動しますか？"},
    "album.title.status": {"ko": "{a0} · {a1}", "en": "{a0} · {a1}", "ja": "{a0} · {a1}"},
    "album.no_event": {"ko": "왼쪽에서 행사를 고르세요", "en": "Choose an event on the left",
                       "ja": "左でイベントを選んでください"},
    "log.album.moved": {"ko": "[사진첩] {a0}장을 다른 행사로 옮겼습니다", "en": "[Albums] Moved {a0} photo(s) to another event",
                        "ja": "[アルバム] {a0}枚を別のイベントへ移動しました"},
    "log.album.split": {"ko": "[사진첩] {a0}장으로 새 행사를 만들었습니다", "en": "[Albums] Created a new event from {a0} photo(s)",
                        "ja": "[アルバム] {a0}枚で新しいイベントを作りました"},
}
register_translations(TRANSLATIONS)

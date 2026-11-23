# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 갤럭시폰 사진 옮기기 [v43, v47]

adb로 연결된 폰의 DCIM/Camera를 다루는 두 가지 흐름이 한 화면에 있다.

1. **새 사진 가져오기(증분 동기화) [v47]** — 보관함 폴더를 한 번 정해 두면,
   아직 가져오지 않은 사진만 골라 연/월 폴더로 내려받는다. 무엇을 이미
   가져왔는지는 보관함 안의 SQLite 기록(phone_sync_store.py)이 기억한다.
   전송은 워커 스레드(SyncThread)에서 하고, 도중에 취소할 수 있다.
2. **날짜(행사)별 다운로드 [v43]** — 촬영일자가 이어지는 사진을 하나의
   "행사" 구간으로 묶어 보여주고, 고른 행사만 원하는 폴더로 내려받는다
   (학교 행사 사진을 따로 뽑을 때). 이쪽은 전송 기록과 무관하다.

연결은 USB 케이블과 무선(Android 11 이상의 "무선 디버깅") 둘 다 된다
[v47]. 파일명 변경·크롭·화질 조정은 FolderKit++의 기존 이미지 편집 기능을
그대로 잇는다 — "이미지 편집 모드로 전달" 버튼으로 바로 넘어갈 수 있다.
"""
import os
import sqlite3

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QApplication, QDialog, QLineEdit, QProgressBar, QCheckBox
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import phone_solve as PH
from . import phone_sync_store as PS

_SET_LAST_DEST = "util.phonetransfer.last_dest"
_SET_ADB_PATH = "util.phonetransfer.adb_path"
_SET_LIBRARY = "util.phonetransfer.library_dir"     # [v47] 보관함 폴더
_SET_WIFI_ADDR = "util.phonetransfer.wifi_addr"     # [v47] 마지막 무선 연결 주소

# [v47] 아래 값들은 전부 내부 키다 — 저장·비교에만 쓰고, 화면에 보일 때는
# 그 자리에서 tr()로 문구로 바꾼다(화면 문구를 분기 조건으로 쓰지 않는다).
END_DONE = "done"                   # 동기화가 끝까지 갔다
END_CANCELLED = "cancelled"         # 사용자가 취소했다
END_DISCONNECTED = "disconnected"   # 도중에 폰 연결이 끊겼다

FIRST_ALL = "all"                   # 첫 동기화: 폰의 사진을 전부 가져온다
FIRST_MARK = "mark"                 # 첫 동기화: 지금 있는 사진은 가져온 것으로 표시만
FIRST_CANCEL = "cancel"

_END_MESSAGE_KEYS = {
    END_DONE: "util.phonetransfer.sync.end.done",
    END_CANCELLED: "util.phonetransfer.sync.end.cancelled",
    END_DISCONNECTED: "util.phonetransfer.sync.end.disconnected",
}
_CONN_LABEL_KEYS = {
    PH.CONN_USB: "util.phonetransfer.conn.usb",
    PH.CONN_WIFI: "util.phonetransfer.conn.wifi",
}


# =============================================================================
class SyncThread(QThread):
    """[v47] 새 사진을 보관함으로 내려받는 워커.

    Qt 위젯은 건드리지 않고 시그널로만 알린다. 파일 하나를 받을 때마다 바로
    전송 기록에 적기 때문에, 취소하거나 연결이 끊겨도 그때까지 받은 사진은
    다음 번에 다시 받지 않는다(이어받기).
    """

    progress = Signal(int, int, str)        # (끝난 수, 전체 수, 지금 받는 파일 이름)
    finished_sync = Signal(int, int, str)   # (성공 수, 실패 수, 종료 사유 내부 키)

    def __init__(self, photos, library_dir, serial, device_id, parent=None):
        super().__init__(parent)
        self._photos = list(photos)
        self._library_dir = library_dir
        self._serial = serial
        self._device_id = device_id
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _is_cancelled(self):
        return self._cancel

    def _device_still_connected(self):
        return any(serial == self._serial and state == "device" for serial, state in PH.list_devices())

    def run(self):
        ok = failed = 0
        reason = END_DONE
        total = len(self._photos)
        try:
            store = PS.SyncStore(self._library_dir)
            for i, photo in enumerate(self._photos):
                if self._cancel:
                    reason = END_CANCELLED
                    break
                self.progress.emit(i, total, photo.name)
                rel = PS.unique_local_rel(self._library_dir, PS.plan_local_rel(photo))
                local_path = os.path.join(self._library_dir, *rel.split("/"))
                result = PH.pull_file(photo, local_path, serial=self._serial, cancel_check=self._is_cancelled)
                if result == PH.PULL_OK:
                    store.record(self._device_id, photo, PS.STATUS_PULLED, rel)
                    ok += 1
                elif result == PH.PULL_CANCELLED:
                    reason = END_CANCELLED
                    break
                else:
                    failed += 1
                    if not self._device_still_connected():
                        reason = END_DISCONNECTED
                        break
        except Exception:   # noqa: BLE001 — 어떤 경우에도 화면이 "가져오는 중"에 갇히지 않게 끝을 알린다
            failed += 1
        self.progress.emit(ok + failed, total, "")
        self.finished_sync.emit(ok, failed, reason)


# =============================================================================
class WirelessDialog(QDialog):
    """[v47] 무선 연결 창 — 처음 한 번의 페어링과, 매번의 연결.

    무선 디버깅의 연결 포트는 켤 때마다 바뀌므로 주소는 직접 입력하거나
    "자동 찾기"(adb mdns)로 채운다. 연결에 성공하면 connected_addr에 그
    주소가 남고, 창을 닫은 뒤 바깥 화면이 목록을 새로 읽는다.
    """

    def __init__(self, parent=None, last_addr=""):
        super().__init__(parent)
        self.connected_addr = None
        self.setWindowTitle(tr("util.phonetransfer.wifi.title"))
        self.resize(460, 380)
        lay = QVBoxLayout(self)
        lay.setSpacing(UK.CTRL_SPACING + 2)

        self.lbl_guide = UK.body_label(tr("util.phonetransfer.wifi.guide"))
        self.lbl_guide.setWordWrap(True)
        lay.addWidget(self.lbl_guide)

        lay.addWidget(UK.title_label(tr("util.phonetransfer.wifi.pair_title")))
        self.edit_pair_addr = QLineEdit()
        self.edit_pair_addr.setPlaceholderText(tr("util.phonetransfer.wifi.addr_placeholder"))
        self.edit_pair_code = QLineEdit()
        self.edit_pair_code.setPlaceholderText(tr("util.phonetransfer.wifi.code_placeholder"))
        self.edit_pair_code.setMaxLength(6)
        self.edit_pair_code.setFixedWidth(110)
        self.btn_pair = UK.secondary_button(tr("util.phonetransfer.wifi.btn.pair"))
        self.btn_pair.clicked.connect(self._on_pair)
        lay.addLayout(UK.hrow(self.edit_pair_addr, self.edit_pair_code, self.btn_pair))

        lay.addWidget(UK.title_label(tr("util.phonetransfer.wifi.connect_title")))
        self.edit_conn_addr = QLineEdit(last_addr or "")
        self.edit_conn_addr.setPlaceholderText(tr("util.phonetransfer.wifi.addr_placeholder"))
        self.btn_find = UK.secondary_button(tr("util.phonetransfer.wifi.btn.find"))
        self.btn_find.clicked.connect(self._on_find)
        self.btn_connect = UK.primary_button(tr("util.phonetransfer.wifi.btn.connect"))
        self.btn_connect.clicked.connect(self._on_connect)
        lay.addLayout(UK.hrow(self.edit_conn_addr, self.btn_find, self.btn_connect))

        self.lbl_result = UK.hint_label()
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_result)
        lay.addStretch(1)

        self.btn_close = UK.neutral_button(tr("util.phonetransfer.wifi.btn.close"))
        self.btn_close.clicked.connect(self.accept)
        lay.addLayout(UK.hrow(None, self.btn_close))

    @staticmethod
    def _busy(fn):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _on_pair(self):
        addr = PH.normalize_host_port(self.edit_pair_addr.text())
        code = self.edit_pair_code.text().strip()
        if addr is None:
            self.lbl_result.setText(tr("util.phonetransfer.wifi.bad_addr"))
            return
        if not PH.is_valid_pair_code(code):
            self.lbl_result.setText(tr("util.phonetransfer.wifi.bad_code"))
            return
        # [v47.1] 실제로 겪은 실수 — 연결용 주소로 페어링하면 adb가
        # "protocol fault"라는 알기 어려운 오류만 낸다. 미리 막고 안내한다.
        if addr == PH.normalize_host_port(self.edit_conn_addr.text()):
            self.lbl_result.setText(tr("util.phonetransfer.wifi.pair_same_as_connect"))
            return
        ok, raw = self._busy(lambda: PH.pair(addr, code))
        self.lbl_result.setText(tr("util.phonetransfer.wifi.pair_ok") if ok
                                else tr("util.phonetransfer.wifi.pair_fail", a0=raw or "-"))

    def _on_find(self):
        found = self._busy(PH.discover_wireless)
        if found["pairing"] and not self.edit_pair_addr.text().strip():
            self.edit_pair_addr.setText(found["pairing"][0])
        if found["connect"]:
            self.edit_conn_addr.setText(found["connect"][0])
            self.lbl_result.setText(tr("util.phonetransfer.wifi.find_ok", a0=found["connect"][0]))
        else:
            self.lbl_result.setText(tr("util.phonetransfer.wifi.find_none"))

    def _on_connect(self):
        addr = PH.normalize_host_port(self.edit_conn_addr.text())
        if addr is None:
            self.lbl_result.setText(tr("util.phonetransfer.wifi.bad_addr"))
            return
        ok, raw = self._busy(lambda: PH.connect(addr))
        if ok:
            self.connected_addr = addr
            self.lbl_result.setText(tr("util.phonetransfer.wifi.connect_ok", a0=addr))
        else:
            self.lbl_result.setText(tr("util.phonetransfer.wifi.connect_fail", a0=raw or "-"))


# =============================================================================
class PhoneTransferWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.events = []
        self.files = []            # [v47] 폰에서 읽은 전체 파일(증분 동기화의 비교 대상)
        self.serial = None
        self.device_id = None      # [v47] 전송 기록의 기기 구분값(무선 주소가 바뀌어도 같은 폰)
        self.device_model = ""
        self.last_dest = None
        self.adb_path = None
        self.library_dir = None    # [v47] 보관함 폴더
        self.wifi_addr = ""
        self._sync_thread = None
        self._build_ui()
        self._load_settings()
        self.retranslate()
        self._refresh()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_sync)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        self.card_list = UK.Card()
        self.lbl_not_ready = UK.hint_label()
        self.lbl_not_ready.setWordWrap(True)
        self.card_list.add_body(self.lbl_not_ready)
        self.list_events = QListWidget()
        self.list_events.itemChanged.connect(self._on_event_check_changed)
        self.card_list.add_body(self.list_events, 1)
        # [v47.1] 전체 선택 — 행사가 수백 개라 하나씩 체크하기 어렵다는 피드백
        self.chk_all = QCheckBox()
        self.chk_all.clicked.connect(self._on_check_all)
        self.card_list.add_tool(self.chk_all)
        self.lbl_selection = UK.hint_label()
        self.card_list.add_footer_left(self.lbl_selection)

        # ---- [v47] 새 사진 가져오기(증분 동기화) 카드 ----
        self.card_sync = UK.Card()
        self.lbl_sync_hint = UK.hint_label()
        self.lbl_sync_hint.setWordWrap(True)
        self.card_sync.add_body(self.lbl_sync_hint)
        self.lbl_library = UK.hint_label()
        self.lbl_library.setWordWrap(True)
        self.card_sync.add_body(self.lbl_library)
        self.lbl_sync_status = UK.body_label()
        self.lbl_sync_status.setWordWrap(True)
        self.card_sync.add_body(self.lbl_sync_status)
        self.progress_sync = QProgressBar()
        self.progress_sync.setTextVisible(False)
        self.progress_sync.setFixedHeight(8)
        self.progress_sync.setVisible(False)
        self.card_sync.add_body(self.progress_sync)
        self.btn_pick_library = self.card_sync.add_footer(UK.secondary_button())
        self.btn_pick_library.clicked.connect(self._on_pick_library)
        self.btn_open_library = self.card_sync.add_footer(UK.secondary_button())
        self.btn_open_library.clicked.connect(self._on_open_library)
        self.btn_sync_cancel = self.card_sync.add_footer(UK.neutral_button())
        self.btn_sync_cancel.clicked.connect(self._on_sync_cancel)
        self.btn_sync_cancel.setVisible(False)
        self.btn_sync = self.card_sync.add_footer(UK.primary_button())
        self.btn_sync.clicked.connect(self._on_sync)

        self.card_ctrl = UK.Card()
        self.lbl_usage = UK.hint_label()
        self.lbl_usage.setWordWrap(True)
        self.card_ctrl.add_body(self.lbl_usage)
        # [v43.4] adb.exe가 설치돼 있어도 시스템 PATH에는 안 잡혀 있는
        # 경우가 실제로 있었다("진단"에서 "PATH에서 못 찾음"으로 확인됨) —
        # PATH를 직접 고칠 필요 없이, 화면에서 adb.exe 파일을 바로
        # 고를 수 있게 한다. [v47] 같은 줄에 "무선 연결" 버튼을 둔다.
        set_path_row = QHBoxLayout()
        set_path_row.addStretch()
        self.btn_wireless = UK.secondary_button()
        self.btn_wireless.clicked.connect(self._on_wireless)
        set_path_row.addWidget(self.btn_wireless)
        self.btn_set_adb_path = UK.secondary_button()
        self.btn_set_adb_path.clicked.connect(self._on_set_adb_path)
        set_path_row.addWidget(self.btn_set_adb_path)
        self.card_ctrl.add_body(set_path_row)
        self.lbl_adb_path = UK.hint_label()
        self.lbl_adb_path.setWordWrap(True)
        self.card_ctrl.add_body(self.lbl_adb_path)
        self.lbl_status = UK.hint_label()
        self.lbl_status.setWordWrap(True)
        self.card_ctrl.add_body(self.lbl_status)
        self.card_ctrl.body.addStretch(1)
        self.btn_refresh = self.card_ctrl.add_footer(UK.secondary_button())
        self.btn_refresh.clicked.connect(self._refresh)
        self.btn_diagnose = self.card_ctrl.add_footer(UK.secondary_button())
        self.btn_diagnose.clicked.connect(self._on_diagnose)
        self.btn_download = self.card_ctrl.add_footer(UK.primary_button())
        self.btn_download.clicked.connect(self._on_download)

        self.lbl_done = UK.hint_label()
        self.lbl_done.setWordWrap(True)
        self.lbl_done.setVisible(False)
        self.card_ctrl.add_body(self.lbl_done)
        done_row = QHBoxLayout()
        done_row.addStretch()
        self.btn_open_folder = UK.secondary_button()
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        self.btn_open_folder.setVisible(False)
        done_row.addWidget(self.btn_open_folder)
        self.btn_to_imgedit = UK.secondary_button()
        self.btn_to_imgedit.clicked.connect(self._on_open_in_imgedit)
        self.btn_to_imgedit.setVisible(False)
        done_row.addWidget(self.btn_to_imgedit)
        self.card_ctrl.add_body(done_row)

        right = UK.vstack(self.card_sync, self.card_ctrl)
        right.setStretch(1, 1)   # 남는 높이는 아래(연결·다운로드) 카드가 가져간다
        UK.split_lr(self, self.card_list, right)

    def _is_syncing(self):
        return self._sync_thread is not None

    def _update_buttons(self, *_):
        any_checked = any(self.list_events.item(i).checkState() == Qt.Checked
                          for i in range(self.list_events.count()))
        syncing = self._is_syncing()
        self.btn_download.setEnabled(any_checked and not syncing)
        # [v47] 가져오는 중에는 연결을 바꾸거나 목록을 다시 읽지 못하게 한다
        self.btn_refresh.setEnabled(not syncing)
        self.btn_wireless.setEnabled(not syncing)
        self.btn_set_adb_path.setEnabled(not syncing)
        self.btn_sync.setEnabled(bool(self.serial) and not syncing)
        self.list_events.setEnabled(not syncing)
        self.chk_all.setEnabled(not syncing and self.list_events.count() > 0)
        self.btn_sync.setText(tr("util.phonetransfer.sync.btn.sync_selected") if self._selected_events()
                              else tr("util.phonetransfer.sync.btn.sync"))
        self.btn_pick_library.setVisible(not syncing)
        self.btn_open_library.setVisible(not syncing and bool(self.library_dir))
        self.btn_sync_cancel.setVisible(syncing)
        self.progress_sync.setVisible(syncing)

    # ---------------------------------------------------------------- 연결·목록
    def _refresh(self):
        if self._is_syncing():
            return
        if self.host:
            self.host.log(tr("util.phonetransfer.log.refresh_clicked"))
        if not PH.is_adb_available():
            self._set_not_ready(tr("util.phonetransfer.status.no_adb"))
            return
        devices = PH.list_devices()
        # [v47] 케이블과 무선이 같이 떠 있으면 케이블을 먼저 쓴다
        serial = PH.pick_preferred_device(devices)
        if serial is None:
            msg = (tr("util.phonetransfer.status.unauthorized") if devices
                  else tr("util.phonetransfer.status.no_device"))
            self._set_not_ready(msg)
            return
        self.serial = serial
        self.device_id, self.device_model = PH.get_device_identity(serial)
        self.lbl_not_ready.setVisible(False)
        self.list_events.setVisible(True)
        self.files = PH.list_photos(serial=self.serial)
        self.events = PH.group_into_events(self.files)
        self._populate_list()
        self.lbl_status.setText(tr("util.phonetransfer.status.connected",
                                   a0=self.device_model or self.serial, a1=len(self.events),
                                   a2=tr(_CONN_LABEL_KEYS[PH.connection_kind(self.serial)])))
        self._update_sync_summary()

    def _on_wireless(self):
        """[v47] 무선 연결 창을 띄우고, 연결에 성공했으면 목록을 새로 읽는다."""
        dlg = WirelessDialog(self, self.wifi_addr)
        dlg.exec()
        if dlg.connected_addr:
            self.wifi_addr = dlg.connected_addr
            self._save_settings()
            if self.host:
                self.host.log(tr("util.phonetransfer.log.wifi_connected", a0=dlg.connected_addr))
            self._refresh()

    def _on_diagnose(self):
        """[v43.3] "새로고침을 눌러도 반응이 없다"고 느껴질 때를 위한
        버튼 — 실제로 adb를 어디서 찾았는지, adb devices를 실행한 원본
        결과가 뭔지 그대로 보여준다. 이 창의 내용을 그대로 복사해
        보내 주면 원인을 훨씬 빨리 알 수 있다."""
        report = PH.diagnose()
        QMessageBox.information(self, tr("util.phonetransfer.diagnose.title"),
                               PH.format_diagnose_report(report))
        if self.host:
            self.host.log(tr("util.phonetransfer.log.diagnosed"))

    def _on_set_adb_path(self):
        """[v43.4] adb.exe가 설치돼 있어도 PATH에 없으면 아예 못 찾는다
        (실제로 "진단"에서 이 증상이 확인됐다) — PATH를 고치는 대신
        여기서 파일을 직접 골라 지정한다. [v43.7] 파일 선택창만 덜렁
        띄우면 뭘 찾아야 할지 막막하다는 피드백을 받아, 정확히 어디서
        내려받고 어떤 파일을 고르면 되는지 안내창을 먼저 보여준다."""
        QMessageBox.information(self, tr("util.phonetransfer.adb_path.pick_title"),
                               tr("util.phonetransfer.adb_path.guide"))
        path, _ = QFileDialog.getOpenFileName(self, tr("util.phonetransfer.adb_path.pick_title"), "",
                                              "adb (adb.exe adb);;모든 파일 (*)")
        if not path:
            return
        self.adb_path = path
        PH.set_adb_path(path)
        self._save_settings()
        self._update_adb_path_label()
        self._refresh()

    def _update_adb_path_label(self):
        """[v43.7] adb를 사용자가 직접 안 골랐어도, 자동 검색(흔한 설치
        위치)으로 이미 찾은 경로가 있으면 그것도 그대로 보여준다 —
        "왜 하나도 안 알려주면서 위치 지정만 하라는 거냐"는 답답함을
        줄이려고, 지금 실제로 뭘 쓰고 있는지 항상 화면에 남긴다."""
        if self.adb_path:
            self.lbl_adb_path.setText(tr("util.phonetransfer.adb_path.custom", a0=self.adb_path))
            return
        auto = PH.auto_detect_adb_path()
        if auto:
            self.lbl_adb_path.setText(tr("util.phonetransfer.adb_path.auto", a0=auto))
        else:
            self.lbl_adb_path.setText(tr("util.phonetransfer.adb_path.default"))

    def _set_not_ready(self, message):
        self.serial = None
        self.device_id = None
        self.device_model = ""
        self.events = []
        self.files = []
        self.list_events.clear()
        self.list_events.setVisible(False)
        self.lbl_not_ready.setVisible(True)
        self.lbl_not_ready.setText(message)
        self.lbl_status.setText("")
        self._update_buttons()
        self._update_sync_summary()

    @staticmethod
    def _event_label(ev):
        start_text, end_text = PH.event_date_texts(ev)
        if end_text is None:
            return tr("util.phonetransfer.event_label_single", a0=start_text, a1=len(ev))
        return tr("util.phonetransfer.event_label_range", a0=start_text, a1=end_text, a2=len(ev))

    def _populate_list(self, keep_checks=False):
        """keep_checks=True면(언어만 바꿀 때) 이름만 다시 쓰고 체크는 유지한다."""
        checked = {i for i in range(self.list_events.count())
                   if self.list_events.item(i).checkState() == Qt.Checked} if keep_checks else set()
        self.list_events.blockSignals(True)
        self.list_events.clear()
        for i, ev in enumerate(self.events):
            item = QListWidgetItem(self._event_label(ev))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if i in checked else Qt.Unchecked)
            self.list_events.addItem(item)
        self.list_events.blockSignals(False)
        self._after_selection_changed()

    # ---------------------------------------------------------------- [v47.1] 선택
    def _on_event_check_changed(self, *_):
        self._after_selection_changed()

    def _on_check_all(self, checked):
        """전체 선택/해제 — 항목마다 신호가 나가면 새 사진 수를 행사 수만큼
        다시 계산하게 되므로, 신호를 막고 한꺼번에 바꾼 뒤 한 번만 갱신한다."""
        state = Qt.Checked if checked else Qt.Unchecked
        self.list_events.blockSignals(True)
        for i in range(self.list_events.count()):
            self.list_events.item(i).setCheckState(state)
        self.list_events.blockSignals(False)
        self._after_selection_changed()

    def _after_selection_changed(self):
        chosen = self._selected_events()
        count = self.list_events.count()
        self.chk_all.blockSignals(True)
        self.chk_all.setChecked(count > 0 and len(chosen) == count)
        self.chk_all.blockSignals(False)
        if chosen:
            self.lbl_selection.setText(tr("util.phonetransfer.selection", a0=len(chosen),
                                          a1=sum(len(ev) for ev in chosen)))
        else:
            self.lbl_selection.setText("")
        self._update_sync_summary()   # 안에서 _update_buttons()도 부른다(가져오는 중이 아니면)
        if self._is_syncing():
            self._update_buttons()

    # ---------------------------------------------------------------- 다운로드
    def _selected_events(self):
        return [self.events[i] for i in range(self.list_events.count())
                if self.list_events.item(i).checkState() == Qt.Checked]

    def _on_download(self):
        chosen = self._selected_events()
        if not chosen:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("util.phonetransfer.pick_dest"), self.last_dest or "")
        if not dest:
            return
        self.last_dest = dest
        self._save_settings()

        total_files = sum(len(ev) for ev in chosen)

        if self.host:
            self.host.busy_start(tr("util.phonetransfer.status.downloading", a0=0, a1=total_files))
        ok_total = 0
        failed_total = []
        try:
            for ev in chosen:
                def _cb(done, total, _base=ok_total + len(failed_total)):
                    self.lbl_status.setText(
                        tr("util.phonetransfer.status.downloading", a0=_base + done, a1=total_files))
                    QApplication.processEvents()
                ok, failed = PH.pull_event(ev, dest, serial=self.serial, progress_cb=_cb)
                ok_total += ok
                failed_total.extend(failed)
        finally:
            if self.host:
                self.host.busy_stop()

        self.lbl_done.setVisible(True)
        if failed_total:
            self.lbl_done.setText(tr("util.phonetransfer.done_with_failures", a0=ok_total, a1=len(failed_total)))
        else:
            self.lbl_done.setText(tr("util.phonetransfer.done", a0=ok_total, a1=dest))
        self.btn_open_folder.setVisible(True)
        self.btn_to_imgedit.setVisible(True)
        if self.host:
            self.host.log(tr("util.phonetransfer.log.done", a0=ok_total, a1=len(failed_total), a2=dest))

    def _on_open_folder(self):
        if not self.last_dest:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_dest))

    def _on_open_in_imgedit(self):
        if not self.last_dest or not self.host:
            return
        self.host.open_in_image_edit(self.last_dest)

    # ---------------------------------------------------------------- [v47] 새 사진 가져오기
    def _sync_candidates(self):
        """[v47.1] 체크한 행사가 있으면 그 안의 사진만, 없으면 폰 전체."""
        chosen = self._selected_events()
        if chosen:
            return PH.syncable([f for ev in chosen for f in ev.files])
        return PH.syncable(self.files)

    def _update_library_label(self):
        if self.library_dir:
            self.lbl_library.setText(tr("util.phonetransfer.sync.library", a0=self.library_dir))
        else:
            self.lbl_library.setText(tr("util.phonetransfer.sync.library_unset"))

    def _update_sync_summary(self):
        """보관함·연결 상태에 맞춰 "새 사진 몇 장"을 다시 계산해 보여준다.
        가져오는 중에는 진행 문구를 덮어쓰지 않도록 아무 것도 안 한다."""
        if self._is_syncing():
            return
        self._update_buttons()
        if not self.serial:
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.no_device"))
            return
        if not self.library_dir:
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.no_library"))
            return
        if not os.path.isdir(self.library_dir):
            # 보관함이 USB·네트워크 드라이브에 있는데 지금 연결돼 있지 않은 경우 등 —
            # 빈 폴더를 새로 만들어 "처음 가져오기"로 착각하지 않게 여기서 멈춘다.
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.library_missing"))
            return
        candidates = self._sync_candidates()
        try:
            pending = PS.SyncStore(self.library_dir).filter_new(self.device_id, candidates)
        except (sqlite3.Error, OSError):
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.db_error"))
            return
        key = ("util.phonetransfer.sync.status.new_count_selected" if self._selected_events()
               else "util.phonetransfer.sync.status.new_count")
        self.lbl_sync_status.setText(tr(key, a0=len(pending), a1=len(candidates)))

    def _on_pick_library(self):
        """보관함 폴더를 고른다. 골랐으면 True."""
        path = QFileDialog.getExistingDirectory(self, tr("util.phonetransfer.sync.pick_library"),
                                                self.library_dir or "")
        if not path:
            return False
        self.library_dir = path
        self._save_settings()
        self._update_library_label()
        self._update_sync_summary()
        return True

    def _on_open_library(self):
        if self.library_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.library_dir))

    def _ask_first_sync_choice(self, count):
        """이 폰을 이 보관함으로 처음 가져올 때 — 폰에 쌓여 있는 사진을 전부
        받을지, 이미 다른 방법으로 옮겨 둔 것으로 치고 앞으로 찍는 사진만
        받을지 묻는다. 반환값은 내부 키(FIRST_*)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("util.phonetransfer.sync.first.title"))
        box.setText(tr("util.phonetransfer.sync.first.text", a0=count))
        btn_all = box.addButton(tr("util.phonetransfer.sync.first.btn_all"), QMessageBox.AcceptRole)
        btn_mark = box.addButton(tr("util.phonetransfer.sync.first.btn_mark"), QMessageBox.ActionRole)
        box.addButton(tr("util.phonetransfer.sync.first.btn_cancel"), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_all:
            return FIRST_ALL
        if clicked is btn_mark:
            return FIRST_MARK
        return FIRST_CANCEL

    def _on_sync(self):
        if self._is_syncing() or not self.serial:
            return
        if not self.library_dir and not self._on_pick_library():
            return
        if not os.path.isdir(self.library_dir):
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.library_missing"))
            return
        candidates = self._sync_candidates()
        store = PS.SyncStore(self.library_dir)
        try:
            is_first = not store.has_any(self.device_id)
            pending = store.filter_new(self.device_id, candidates)
        except (sqlite3.Error, OSError):
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.db_error"))
            return
        if not pending:
            self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.none_new"))
            return
        # [v47.1] 날짜를 골라 가져올 때는 무엇을 받을지 이미 정한 것이므로 묻지 않는다
        if is_first and not self._selected_events():
            choice = self._ask_first_sync_choice(len(pending))
            if choice == FIRST_CANCEL:
                return
            if choice == FIRST_MARK:
                try:
                    marked = store.mark_all(self.device_id, pending)
                except (sqlite3.Error, OSError):
                    self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.db_error"))
                    return
                self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.marked", a0=marked))
                if self.host:
                    self.host.log(tr("util.phonetransfer.log.sync_marked", a0=marked))
                return
        self._start_sync(pending)

    def _start_sync(self, pending):
        thread = SyncThread(pending, self.library_dir, self.serial, self.device_id, self)
        thread.progress.connect(self._on_sync_progress)
        thread.finished_sync.connect(self._on_sync_finished)
        self._sync_thread = thread
        self.progress_sync.setRange(0, len(pending))
        self.progress_sync.setValue(0)
        self._update_buttons()
        self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.progress", a0=0, a1=len(pending), a2=""))
        if self.host:
            self.host.log(tr("util.phonetransfer.log.sync_start", a0=len(pending), a1=self.library_dir))
        thread.start()

    def _on_sync_progress(self, done, total, name):
        self.progress_sync.setValue(done)
        self.lbl_sync_status.setText(tr("util.phonetransfer.sync.status.progress", a0=done, a1=total, a2=name))

    def _on_sync_cancel(self):
        if self._sync_thread is not None:
            self._sync_thread.cancel()
            self.btn_sync_cancel.setEnabled(False)

    def _on_sync_finished(self, ok, failed, reason):
        thread = self._sync_thread
        self._sync_thread = None
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self.btn_sync_cancel.setEnabled(True)
        self._update_buttons()
        text = tr(_END_MESSAGE_KEYS.get(reason, _END_MESSAGE_KEYS[END_DONE]), a0=ok)
        if failed:
            text += " " + tr("util.phonetransfer.sync.end.failed_suffix", a0=failed)
        self.lbl_sync_status.setText(text)
        if self.host:
            self.host.log(tr("util.phonetransfer.log.sync_done", a0=ok, a1=failed, a2=self.library_dir))

    def _shutdown_sync(self):
        """프로그램을 닫을 때 전송이 돌고 있으면 멈추고 기다린다 — 스레드가
        살아 있는 채로 창이 사라지면 Qt가 비정상 종료한다."""
        thread = self._sync_thread
        if thread is not None:
            thread.cancel()
            thread.wait(10000)

    # ---------------------------------------------------------------- 저장/불러오기
    def _load_settings(self):
        if self._settings is None:
            return
        self.last_dest = self._settings.value(_SET_LAST_DEST, "") or None
        self.adb_path = self._settings.value(_SET_ADB_PATH, "") or None
        self.library_dir = self._settings.value(_SET_LIBRARY, "") or None
        self.wifi_addr = self._settings.value(_SET_WIFI_ADDR, "") or ""
        PH.set_adb_path(self.adb_path)
        self._update_adb_path_label()

    def _save_settings(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_LAST_DEST, self.last_dest or "")
        self._settings.setValue(_SET_ADB_PATH, self.adb_path or "")
        self._settings.setValue(_SET_LIBRARY, self.library_dir or "")
        self._settings.setValue(_SET_WIFI_ADDR, self.wifi_addr or "")

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.card_list.set_title(tr("util.phonetransfer.card.list"))
        self.card_ctrl.set_title(tr("util.phonetransfer.card.ctrl"))
        self.card_sync.set_title(tr("util.phonetransfer.card.sync"))
        self.lbl_sync_hint.setText(tr("util.phonetransfer.sync.hint"))
        self.btn_pick_library.setText(tr("util.phonetransfer.sync.btn.pick_library"))
        self.btn_open_library.setText(tr("util.phonetransfer.sync.btn.open_library"))
        self.btn_sync_cancel.setText(tr("util.phonetransfer.sync.btn.cancel"))
        self.chk_all.setText(tr("util.phonetransfer.check_all"))
        self.btn_wireless.setText(tr("util.phonetransfer.btn.wireless"))
        self._update_library_label()
        self._populate_list(keep_checks=True)   # 행사 이름·선택 요약·새 사진 수도 새 언어로
        self.lbl_usage.setText(tr("util.phonetransfer.usage"))
        self.btn_set_adb_path.setText(tr("util.phonetransfer.btn.set_adb_path"))
        self._update_adb_path_label()
        self.btn_refresh.setText(tr("util.phonetransfer.btn.refresh"))
        self.btn_diagnose.setText(tr("util.phonetransfer.btn.diagnose"))
        self.btn_download.setText(tr("util.phonetransfer.btn.download"))
        self.btn_open_folder.setText(tr("util.phonetransfer.btn.open_folder"))
        self.btn_to_imgedit.setText(tr("util.phonetransfer.btn.to_imgedit"))
        self._update_buttons()


class PhoneTransferApp(MiniApp):
    id = "phonetransfer"
    icon = "phonetransfer"
    category = "misc"
    # [v43.9] 일반적이지 않은 도구라 도구 목록·홈 화면·최근 사용 어디에도
    # 안 보이게 숨긴다 — MainWindow의 Ctrl+Shift+F9로만 열 수 있다.
    hidden = True

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = PhoneTransferWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.phonetransfer.title": {"ko": "갤럭시폰 사진 옮기기", "en": "Phone Photo Transfer", "ja": "Galaxy写真転送"},
    "util.phonetransfer.desc": {
        "ko": "폰의 새 사진만 보관함으로 가져오거나, 촬영일자(행사)별로 골라 내려받습니다(케이블·무선).",
        "en": "Imports only new photos into a library, or downloads by shooting date (cable or wireless).",
        "ja": "新しい写真だけを保管フォルダに取り込むか、撮影日（イベント）別に選んでダウンロードします（ケーブル・無線）。"},

    "util.phonetransfer.card.list": {"ko": "날짜별 사진", "en": "Photos by Date", "ja": "日付別写真"},
    "util.phonetransfer.card.ctrl": {"ko": "연결·다운로드", "en": "Connection & Download", "ja": "接続・ダウンロード"},
    "util.phonetransfer.usage": {
        "ko": "① 폰에서 개발자 옵션·USB 디버깅을 켜고 케이블로 연결(케이블 없이는 \"무선 연결\")\n"
              "② \"새로고침\"으로 사진 목록 가져오기\n"
              "③ 날짜(행사)를 골라 따로 받으려면 체크하고 \"다운로드\"",
        "en": "① Enable Developer Options/USB debugging and connect the cable (or use \"Wireless\")\n"
              "② \"Refresh\" to load photos\n"
              "③ To save specific dates separately, check them and press \"Download\"",
        "ja": "① スマホで開発者向けオプション・USBデバッグを有効にしてケーブル接続（ケーブルなしなら「無線接続」）\n"
              "② 「更新」で写真一覧を取得\n"
              "③ 日付（イベント）を選んで別に保存するにはチェックして「ダウンロード」"},
    "util.phonetransfer.btn.refresh": {"ko": "새로고침", "en": "Refresh", "ja": "更新"},
    "util.phonetransfer.btn.diagnose": {"ko": "진단", "en": "Diagnose", "ja": "診断"},
    "util.phonetransfer.btn.set_adb_path": {"ko": "adb 위치 지정", "en": "Set adb Location", "ja": "adbの場所を指定"},
    "util.phonetransfer.adb_path.pick_title": {"ko": "adb 실행 파일 선택", "en": "Select adb Executable",
                                                "ja": "adb実行ファイルを選択"},
    "util.phonetransfer.adb_path.default": {
        "ko": "adb 위치: 시스템 PATH에서 자동으로 찾습니다.",
        "en": "adb location: searched automatically in the system PATH.",
        "ja": "adbの場所: システムのPATHから自動的に検索します。"},
    "util.phonetransfer.adb_path.auto": {
        "ko": "adb 위치(자동으로 찾음): {a0}",
        "en": "adb location (found automatically): {a0}",
        "ja": "adbの場所（自動検出）: {a0}"},
    "util.phonetransfer.adb_path.guide": {
        "ko": "adb.exe를 아직 설치하지 않았다면:\n"
              "① https://developer.android.com/tools/releases/platform-tools 에서 "
              "\"SDK Platform-Tools for Windows\"를 내려받는다\n"
              "② 내려받은 zip을 아무 폴더에나 통째로 압축 해제한다(예: 바탕화면)\n"
              "③ 다음 화면에서 그 폴더 안의 adb.exe 파일을 고른다\n"
              "(폴더 이름은 보통 platform-tools 입니다 — 그 안에 adb.exe가 있습니다)",
        "en": "If you haven't installed adb.exe yet:\n"
              "① Download \"SDK Platform-Tools for Windows\" from "
              "https://developer.android.com/tools/releases/platform-tools\n"
              "② Extract the downloaded zip anywhere (e.g. your Desktop)\n"
              "③ On the next screen, pick the adb.exe file inside that folder\n"
              "(the folder is usually named platform-tools — adb.exe is inside it)",
        "ja": "adb.exeをまだインストールしていない場合:\n"
              "① https://developer.android.com/tools/releases/platform-tools から"
              "「SDK Platform-Tools for Windows」をダウンロード\n"
              "② ダウンロードしたzipを任意のフォルダに展開（例：デスクトップ）\n"
              "③ 次の画面でそのフォルダ内のadb.exeファイルを選択\n"
              "（フォルダ名は通常platform-tools — その中にadb.exeがあります）"},
    "util.phonetransfer.adb_path.custom": {"ko": "adb 위치(직접 지정): {a0}", "en": "adb location (custom): {a0}",
                                            "ja": "adbの場所（指定済み）: {a0}"},
    "util.phonetransfer.diagnose.title": {"ko": "연결 진단", "en": "Connection Diagnostics", "ja": "接続診断"},
    "util.phonetransfer.log.refresh_clicked": {"ko": "[사진 옮기기] 새로고침을 눌렀습니다",
                                                "en": "[Phone Transfer] Refresh pressed",
                                                "ja": "[写真転送] 更新が押されました"},
    "util.phonetransfer.log.diagnosed": {"ko": "[사진 옮기기] 진단 정보를 확인했습니다",
                                          "en": "[Phone Transfer] Checked diagnostics",
                                          "ja": "[写真転送] 診断情報を確認しました"},
    "util.phonetransfer.btn.download": {"ko": "다운로드", "en": "Download", "ja": "ダウンロード"},
    "util.phonetransfer.btn.open_folder": {"ko": "저장 폴더 열기", "en": "Open Folder", "ja": "保存フォルダを開く"},
    "util.phonetransfer.btn.to_imgedit": {"ko": "이미지 편집 모드로 전달", "en": "Send to Image Editor",
                                           "ja": "画像編集モードに渡す"},
    "util.phonetransfer.pick_dest": {"ko": "저장할 폴더 선택", "en": "Choose Destination Folder", "ja": "保存フォルダを選択"},

    "util.phonetransfer.event_label_single": {"ko": "{a0} ({a1}장)", "en": "{a0} ({a1} photos)", "ja": "{a0}（{a1}枚）"},
    "util.phonetransfer.check_all": {"ko": "전체 선택", "en": "Select All", "ja": "すべて選択"},
    "util.phonetransfer.selection": {"ko": "선택: 행사 {a0}개, {a1}장", "en": "Selected: {a0} event(s), {a1} photos",
                                     "ja": "選択: イベント{a0}件、{a1}枚"},
    "util.phonetransfer.sync.btn.sync_selected": {"ko": "선택만 가져오기", "en": "Get Selected",
                                                   "ja": "選択分を取り込む"},
    "util.phonetransfer.sync.status.new_count_selected": {
        "ko": "선택한 날짜의 새 사진 {a0}장 (선택한 {a1}장 중)", "en": "{a0} new in the selected dates (of {a1})",
        "ja": "選択した日付の新しい写真 {a0}枚（選択した{a1}枚中）"},
    "util.phonetransfer.wifi.pair_same_as_connect": {
        "ko": "페어링 칸에 연결용 주소가 들어 있습니다. 폰에서 \"페어링 코드로 기기 페어링\"을 눌러 뜬 창의 "
              "주소(포트 번호가 다릅니다)를 넣어 주세요.",
        "en": "The pairing box has the connection address. Enter the address shown in the window that opens from "
              "\"Pair device with pairing code\" on the phone (its port is different).",
        "ja": "ペアリング欄に接続用のアドレスが入っています。スマホで「ペア設定コードによるデバイスのペア設定」を"
              "押して表示されたウィンドウのアドレス（ポート番号が違います）を入力してください。"},
    "util.phonetransfer.event_label_range": {"ko": "{a0} ~ {a1} ({a2}장)", "en": "{a0} ~ {a1} ({a2} photos)",
                                              "ja": "{a0}～{a1}（{a2}枚）"},

    "util.phonetransfer.status.no_adb": {
        "ko": "adb를 찾을 수 없습니다. 처음 쓰는 컴퓨터라면 폰에서 개발자 옵션·USB 디버깅을 켜고 "
              "케이블로 연결한 뒤 \"새로고침\"을 눌러 주세요. 이미 adb를 설치했는데도 안 된다면, "
              "PATH에 안 걸려 있을 수 있습니다 — 위 \"adb 위치 지정\"으로 adb.exe 파일을 직접 골라 주세요.",
        "en": "adb wasn't found. If this is a new computer, enable Developer Options/USB debugging "
              "on the phone, connect the cable, then press \"Refresh\". If adb is already installed but "
              "still not found, it may not be on your PATH — use \"Set adb Location\" above to pick adb.exe directly.",
        "ja": "adbが見つかりません。初めて使うパソコンなら、スマホで開発者向けオプション・USBデバッグを"
              "有効にしてケーブルで接続し、「更新」を押してください。すでにadbをインストール済みでも"
              "見つからない場合、PATHに登録されていない可能性があります — 上の「adbの場所を指定」で"
              "adb.exeファイルを直接選んでください。"},
    "util.phonetransfer.status.no_device": {
        "ko": "연결된 폰이 없습니다. 케이블로 연결하고 폰 화면의 허용 팝업을 확인해 주세요.",
        "en": "No phone connected. Connect the cable and confirm the permission popup on the phone.",
        "ja": "接続されたスマホがありません。ケーブルで接続し、スマホ画面の許可ポップアップを確認してください。"},
    "util.phonetransfer.status.unauthorized": {
        "ko": "폰이 연결됐지만 아직 이 컴퓨터를 허용하지 않았습니다 — 폰 화면의 팝업에서 \"허용\"을 눌러 주세요.",
        "en": "Phone connected but not yet authorized — tap \"Allow\" on the phone's popup.",
        "ja": "スマホは接続されていますが、まだこのパソコンが許可されていません — "
              "スマホ画面のポップアップで「許可」を押してください。"},
    "util.phonetransfer.status.connected": {"ko": "{a0} 연결됨({a2}) — 행사 {a1}개",
                                             "en": "{a0} connected ({a2}) — {a1} event(s)",
                                             "ja": "{a0}接続済み（{a2}） — イベント{a1}件"},
    "util.phonetransfer.status.downloading": {"ko": "다운로드 중… ({a0}/{a1})", "en": "Downloading… ({a0}/{a1})",
                                                "ja": "ダウンロード中…（{a0}/{a1}）"},
    "util.phonetransfer.done": {"ko": "{a0}장을 저장했습니다: {a1}", "en": "Saved {a0} photos: {a1}",
                                 "ja": "{a0}枚を保存しました: {a1}"},
    "util.phonetransfer.done_with_failures": {
        "ko": "{a0}장 저장, {a1}장은 실패했습니다(연결이 끊겼거나 파일이 없을 수 있습니다).",
        "en": "Saved {a0}, but {a1} failed (connection may have dropped, or the file no longer exists).",
        "ja": "{a0}枚保存、{a1}枚は失敗しました（接続が切れたかファイルが無い可能性があります）。"},
    "util.phonetransfer.log.done": {
        "ko": "[사진 옮기기] {a0}장 저장, {a1}장 실패 — {a2}",
        "en": "[Phone Transfer] Saved {a0}, failed {a1} — {a2}", "ja": "[写真転送] {a0}枚保存、{a1}枚失敗 — {a2}"},
    # ---- [v47] 새 사진 가져오기(증분 동기화) ----
    "util.phonetransfer.card.sync": {"ko": "새 사진 가져오기", "en": "Get New Photos", "ja": "新しい写真を取り込む"},
    "util.phonetransfer.sync.hint": {
        "ko": "보관함 폴더를 한 번 정해 두면, 아직 가져오지 않은 사진만 연/월 폴더로 가져옵니다. "
              "왼쪽에서 날짜를 체크하면 그 날짜의 사진만 가져옵니다.",
        "en": "Pick a library folder once; only photos not yet imported are saved into year/month folders. "
              "Check dates on the left to import only those dates.",
        "ja": "保管フォルダを一度決めておくと、まだ取り込んでいない写真だけを年/月フォルダに取り込みます。"
              "左で日付にチェックすると、その日付の写真だけを取り込みます。"},
    "util.phonetransfer.sync.library": {"ko": "보관함: {a0}", "en": "Library: {a0}", "ja": "保管フォルダ: {a0}"},
    "util.phonetransfer.sync.library_unset": {
        "ko": "보관함 폴더를 아직 정하지 않았습니다.", "en": "No library folder chosen yet.",
        "ja": "保管フォルダがまだ決まっていません。"},
    "util.phonetransfer.sync.pick_library": {"ko": "보관함 폴더 선택", "en": "Choose Library Folder",
                                              "ja": "保管フォルダを選択"},
    "util.phonetransfer.sync.btn.pick_library": {"ko": "보관함 지정", "en": "Set Library", "ja": "保管先指定"},
    "util.phonetransfer.sync.btn.open_library": {"ko": "보관함 열기", "en": "Open Library", "ja": "保管先を開く"},
    "util.phonetransfer.sync.btn.cancel": {"ko": "취소", "en": "Cancel", "ja": "キャンセル"},
    "util.phonetransfer.sync.btn.sync": {"ko": "새 사진 가져오기", "en": "Get New Photos", "ja": "新着を取り込む"},
    "util.phonetransfer.sync.status.no_device": {
        "ko": "폰을 연결하면 새 사진 수를 알려 드립니다.", "en": "Connect a phone to see how many photos are new.",
        "ja": "スマホを接続すると新しい写真の枚数を表示します。"},
    "util.phonetransfer.sync.status.no_library": {
        "ko": "\"새 사진 가져오기\"를 누르면 보관함 폴더부터 정합니다.",
        "en": "Press \"Get New Photos\" to choose a library folder first.",
        "ja": "「新着を取り込む」を押すと、まず保管フォルダを決めます。"},
    "util.phonetransfer.sync.status.library_missing": {
        "ko": "보관함 폴더를 찾을 수 없습니다. 드라이브가 연결돼 있는지 확인하거나 \"보관함 지정\"으로 다시 골라 주세요.",
        "en": "The library folder can't be found. Check that its drive is connected, or choose it again with \"Set Library\".",
        "ja": "保管フォルダが見つかりません。ドライブが接続されているか確認するか、「保管先指定」で選び直してください。"},
    "util.phonetransfer.sync.status.db_error": {
        "ko": "보관함의 전송 기록을 열 수 없습니다. 폴더에 쓸 수 있는지 확인해 주세요.",
        "en": "Can't open the library's transfer record. Check that the folder is writable.",
        "ja": "保管フォルダの転送記録を開けません。フォルダに書き込めるか確認してください。"},
    "util.phonetransfer.sync.status.new_count": {
        "ko": "새 사진 {a0}장 (폰 전체 {a1}장)", "en": "{a0} new (of {a1} on the phone)",
        "ja": "新しい写真 {a0}枚（スマホ全体 {a1}枚）"},
    "util.phonetransfer.sync.status.none_new": {
        "ko": "새로 가져올 사진이 없습니다.", "en": "Nothing new to import.", "ja": "新しく取り込む写真はありません。"},
    "util.phonetransfer.sync.status.marked": {
        "ko": "지금 폰에 있는 {a0}장을 가져온 것으로 표시했습니다. 앞으로 찍는 사진만 가져옵니다.",
        "en": "Marked the {a0} photos now on the phone as imported. Only photos taken from now on will be fetched.",
        "ja": "今スマホにある{a0}枚を取り込み済みにしました。今後撮る写真だけを取り込みます。"},
    "util.phonetransfer.sync.status.progress": {
        "ko": "가져오는 중… {a0}/{a1}  {a2}", "en": "Importing… {a0}/{a1}  {a2}", "ja": "取り込み中… {a0}/{a1}  {a2}"},
    "util.phonetransfer.sync.end.done": {
        "ko": "{a0}장을 보관함으로 가져왔습니다.", "en": "Imported {a0} photos into the library.",
        "ja": "{a0}枚を保管フォルダに取り込みました。"},
    "util.phonetransfer.sync.end.cancelled": {
        "ko": "취소했습니다 — {a0}장까지 가져왔습니다. 다시 누르면 이어서 가져옵니다.",
        "en": "Cancelled — {a0} imported so far. Press again to continue.",
        "ja": "キャンセルしました — {a0}枚まで取り込みました。もう一度押すと続きから取り込みます。"},
    "util.phonetransfer.sync.end.disconnected": {
        "ko": "폰 연결이 끊겼습니다 — {a0}장까지 가져왔습니다. 다시 연결하고 누르면 이어서 가져옵니다.",
        "en": "The phone disconnected — {a0} imported so far. Reconnect and press again to continue.",
        "ja": "スマホの接続が切れました — {a0}枚まで取り込みました。再接続して押すと続きから取り込みます。"},
    "util.phonetransfer.sync.end.failed_suffix": {
        "ko": "({a0}장 실패 — 다음에 다시 시도합니다)", "en": "({a0} failed — will retry next time)",
        "ja": "（{a0}枚失敗 — 次回もう一度試します）"},
    "util.phonetransfer.sync.first.title": {"ko": "처음 가져오기", "en": "First Import", "ja": "初回の取り込み"},
    "util.phonetransfer.sync.first.text": {
        "ko": "이 폰의 사진을 이 보관함으로 가져오는 것은 처음입니다.\n폰에 사진이 {a0}장 있습니다. 어떻게 할까요?\n\n"
              "• 전부 가져오기 — {a0}장을 모두 보관함으로 가져옵니다.\n"
              "• 지금부터만 — 지금 있는 사진은 이미 옮긴 것으로 표시하고, 앞으로 찍는 사진만 가져옵니다.",
        "en": "This is the first import from this phone into this library.\nThe phone has {a0} photos. What would you like to do?\n\n"
              "• Import all — bring all {a0} photos into the library.\n"
              "• From now on — mark the existing photos as already moved and fetch only future photos.",
        "ja": "このスマホの写真をこの保管フォルダに取り込むのは初めてです。\nスマホに写真が{a0}枚あります。どうしますか？\n\n"
              "• すべて取り込む — {a0}枚をすべて保管フォルダに取り込みます。\n"
              "• これからの分だけ — 今ある写真は移動済みとして記録し、今後撮る写真だけを取り込みます。"},
    "util.phonetransfer.sync.first.btn_all": {"ko": "전부 가져오기", "en": "Import All", "ja": "すべて取り込む"},
    "util.phonetransfer.sync.first.btn_mark": {"ko": "지금부터만", "en": "From Now On", "ja": "これからの分だけ"},
    "util.phonetransfer.sync.first.btn_cancel": {"ko": "취소", "en": "Cancel", "ja": "キャンセル"},
    "util.phonetransfer.log.sync_start": {
        "ko": "[사진 옮기기] 새 사진 {a0}장 가져오기 시작 — {a1}",
        "en": "[Phone Transfer] Importing {a0} new photos — {a1}", "ja": "[写真転送] 新しい写真{a0}枚の取り込み開始 — {a1}"},
    "util.phonetransfer.log.sync_done": {
        "ko": "[사진 옮기기] 새 사진 {a0}장 가져옴, {a1}장 실패 — {a2}",
        "en": "[Phone Transfer] Imported {a0}, failed {a1} — {a2}", "ja": "[写真転送] {a0}枚取り込み、{a1}枚失敗 — {a2}"},
    "util.phonetransfer.log.sync_marked": {
        "ko": "[사진 옮기기] 기존 사진 {a0}장을 가져온 것으로 표시했습니다",
        "en": "[Phone Transfer] Marked {a0} existing photos as imported",
        "ja": "[写真転送] 既存の写真{a0}枚を取り込み済みにしました"},

    # ---- [v47] 무선 연결 ----
    "util.phonetransfer.conn.usb": {"ko": "케이블", "en": "cable", "ja": "ケーブル"},
    "util.phonetransfer.conn.wifi": {"ko": "무선", "en": "wireless", "ja": "無線"},
    "util.phonetransfer.btn.wireless": {"ko": "무선 연결", "en": "Wireless", "ja": "無線接続"},
    "util.phonetransfer.wifi.title": {"ko": "무선 연결", "en": "Wireless Connection", "ja": "無線接続"},
    "util.phonetransfer.wifi.guide": {
        "ko": "폰과 컴퓨터가 같은 와이파이에 연결돼 있어야 합니다(Android 11 이상).\n"
              "① 폰: 설정 → 개발자 옵션 → \"무선 디버깅\"을 켭니다.\n"
              "② 처음 한 번만: \"페어링 코드로 기기 페어링\"을 눌러 나온 주소와 6자리 코드를 아래 \"페어링\"에 입력합니다.\n"
              "③ 무선 디버깅 화면 위쪽의 \"IP 주소 및 포트\"를 아래 \"연결\"에 입력합니다. "
              "포트 번호는 무선 디버깅을 켤 때마다 바뀝니다.",
        "en": "The phone and this computer must be on the same Wi-Fi (Android 11 or later).\n"
              "① Phone: Settings → Developer options → turn on \"Wireless debugging\".\n"
              "② First time only: tap \"Pair device with pairing code\" and enter the address and 6-digit code under \"Pairing\".\n"
              "③ Enter the \"IP address & Port\" shown at the top of that screen under \"Connect\". "
              "The port changes every time wireless debugging is turned on.",
        "ja": "スマホとパソコンが同じWi-Fiに接続されている必要があります（Android 11以上）。\n"
              "① スマホ: 設定 → 開発者向けオプション → 「ワイヤレスデバッグ」をオンにします。\n"
              "② 初回のみ: 「ペア設定コードによるデバイスのペア設定」を押して表示されたアドレスと6桁のコードを下の「ペアリング」に入力します。\n"
              "③ その画面上部の「IPアドレスとポート」を下の「接続」に入力します。"
              "ポート番号はワイヤレスデバッグをオンにするたびに変わります。"},
    "util.phonetransfer.wifi.pair_title": {"ko": "페어링(처음 한 번)", "en": "Pairing (first time only)",
                                            "ja": "ペアリング（初回のみ）"},
    "util.phonetransfer.wifi.connect_title": {"ko": "연결", "en": "Connect", "ja": "接続"},
    "util.phonetransfer.wifi.addr_placeholder": {"ko": "예: 192.168.0.5:37123", "en": "e.g. 192.168.0.5:37123",
                                                  "ja": "例: 192.168.0.5:37123"},
    "util.phonetransfer.wifi.code_placeholder": {"ko": "6자리 코드", "en": "6-digit code", "ja": "6桁コード"},
    "util.phonetransfer.wifi.btn.pair": {"ko": "페어링", "en": "Pair", "ja": "ペアリング"},
    "util.phonetransfer.wifi.btn.find": {"ko": "자동 찾기", "en": "Find", "ja": "自動検索"},
    "util.phonetransfer.wifi.btn.connect": {"ko": "연결", "en": "Connect", "ja": "接続"},
    "util.phonetransfer.wifi.btn.close": {"ko": "닫기", "en": "Close", "ja": "閉じる"},
    "util.phonetransfer.wifi.bad_addr": {
        "ko": "주소는 \"IP:포트\" 형식으로 입력해 주세요(예: 192.168.0.5:37123).",
        "en": "Enter the address as \"IP:port\" (e.g. 192.168.0.5:37123).",
        "ja": "アドレスは「IP:ポート」の形式で入力してください（例: 192.168.0.5:37123）。"},
    "util.phonetransfer.wifi.bad_code": {
        "ko": "페어링 코드는 숫자 6자리입니다.", "en": "The pairing code is 6 digits.",
        "ja": "ペアリングコードは数字6桁です。"},
    "util.phonetransfer.wifi.pair_ok": {
        "ko": "페어링했습니다. 이제 아래 \"연결\"에 IP 주소 및 포트를 입력해 연결하세요.",
        "en": "Paired. Now enter the IP address & port under \"Connect\".",
        "ja": "ペアリングしました。下の「接続」にIPアドレスとポートを入力して接続してください。"},
    "util.phonetransfer.wifi.pair_fail": {
        "ko": "페어링하지 못했습니다. 주소와 코드를 다시 확인해 주세요(코드는 잠시 뒤 바뀝니다).\nadb: {a0}",
        "en": "Pairing failed. Check the address and code again (the code expires quickly).\nadb: {a0}",
        "ja": "ペアリングできませんでした。アドレスとコードをもう一度確認してください（コードはすぐ変わります）。\nadb: {a0}"},
    "util.phonetransfer.wifi.find_ok": {
        "ko": "무선 디버깅이 켜진 폰을 찾았습니다: {a0}", "en": "Found a phone with wireless debugging on: {a0}",
        "ja": "ワイヤレスデバッグがオンのスマホを見つけました: {a0}"},
    "util.phonetransfer.wifi.find_none": {
        "ko": "자동으로 찾지 못했습니다. 폰의 무선 디버깅 화면에 보이는 주소를 직접 입력해 주세요. "
              "기기끼리 통신을 막아 둔 와이파이(학교·공공망 등)에서는 무선 연결이 안 될 수 있습니다.",
        "en": "Nothing found automatically. Type the address shown on the phone's wireless debugging screen. "
              "Wi-Fi networks that block device-to-device traffic (school/public) may not allow wireless connections.",
        "ja": "自動では見つかりませんでした。スマホのワイヤレスデバッグ画面に表示されるアドレスを直接入力してください。"
              "機器間の通信を遮断しているWi-Fi（学校・公共のネットワークなど）では無線接続できないことがあります。"},
    "util.phonetransfer.wifi.connect_ok": {
        "ko": "{a0}에 연결했습니다. 창을 닫으면 사진 목록을 불러옵니다.",
        "en": "Connected to {a0}. Close this window to load the photo list.",
        "ja": "{a0}に接続しました。ウィンドウを閉じると写真一覧を読み込みます。"},
    "util.phonetransfer.wifi.connect_fail": {
        "ko": "연결하지 못했습니다. 포트 번호가 바뀌지 않았는지, 같은 와이파이인지 확인해 주세요.\nadb: {a0}",
        "en": "Couldn't connect. Check that the port hasn't changed and both are on the same Wi-Fi.\nadb: {a0}",
        "ja": "接続できませんでした。ポート番号が変わっていないか、同じWi-Fiかを確認してください。\nadb: {a0}"},
    "util.phonetransfer.log.wifi_connected": {
        "ko": "[사진 옮기기] 무선으로 연결했습니다 — {a0}", "en": "[Phone Transfer] Connected wirelessly — {a0}",
        "ja": "[写真転送] 無線で接続しました — {a0}"},
}
PhoneTransferApp.tr_table = TRANSLATIONS

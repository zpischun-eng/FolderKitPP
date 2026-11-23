# -*- coding: utf-8 -*-
"""
FolderKit — 환경설정 저장/로드(Config) 및 최근 작업 히스토리(HistoryManager)
"""
import os
import json
from datetime import datetime
from PySide6.QtCore import QSettings
from .i18n import tr, TR


def _resolve_special_folder(shell_key, fallback_subdir):
    """[v45] 바탕화면/다운로드 등 윈도우 "특수 폴더"의 실제 경로를 알아낸다.

    단순히 ``~/Desktop`` 처럼 조합만 하면, 그 폴더를 다른 드라이브로
    옮겨둔(예: 재설치가 잦은 학교 PC, OneDrive 폴더 이동 등) 환경에서는
    엉뚱한(존재하지 않는) 경로가 나온다. Windows는 이런 폴더의 실제 위치를
    레지스트리(``HKCU\\...\\Explorer\\User Shell Folders``)에 정확히
    기록해 두므로, 그 값을 먼저 시도하고 실패하면(비Windows 환경 포함)
    기본 조합 경로로 되돌아간다.

    shell_key: 레지스트리 값 이름 — "Desktop"처럼 이름이 있는 것도 있고,
               "다운로드"처럼 이름 없이 GUID로만 등록된 것도 있다.
    fallback_subdir: 레지스트리를 못 읽을 때 "~/<이 이름>"으로 대신 쓸 값.
    """
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value, _ = winreg.QueryValueEx(key, shell_key)
            resolved = os.path.expandvars(value)
            if resolved:
                return resolved
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), fallback_subdir)


def desktop_dir():
    """[FolderKit++ v44] 파일 저장 대화상자의 기본 위치로 쓰는 바탕화면 경로.

    양식 다운로드 등에서 기본 파일명만 넘기면 대화상자가 "현재 작업 폴더"
    (개발 중이면 프로젝트 폴더, exe면 설치 폴더)를 먼저 띄워서 일반 사용자가
    헷갈렸다. 레지스트리의 실제 바탕화면 위치(드라이브를 옮긴 경우 포함)를
    먼저 쓰고, 그 폴더가 없으면 사용자 홈 폴더로 대신한다."""
    path = _resolve_special_folder("Desktop", "Desktop")
    if path and os.path.isdir(path):
        return path
    return os.path.expanduser("~")


def desktop_file(name):
    """바탕화면 안의 파일 경로(저장 대화상자의 기본값)."""
    return os.path.join(desktop_dir(), name)


# [v45] 다운로드 폴더는(바탕화면과 달리) 옛날부터 있던 "이름 붙은" 레지스트리
# 값이 없고, Vista 이후 GUID로만 등록되어 있다 — Microsoft가 고정해 둔 값.
_DOWNLOADS_FOLDER_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"

# [v47] 문서/사진/음악/동영상은 다운로드와 달리 예전부터 있던 "이름 붙은"
# User Shell Folders 레지스트리 값이 그대로 존재한다(Personal/My Pictures/
# My Music/My Video). 즐겨찾기 기본 6종(바탕화면/다운로드/문서/사진/음악/
# 동영상) 시딩에 쓰는 (레지스트리 키, 폴백 하위폴더, 내부 아이콘 종류) 표.
_SYSTEM_QUICKLINK_SPECS = [
    ("desktop", "Desktop", "Desktop"),
    ("downloads", _DOWNLOADS_FOLDER_GUID, "Downloads"),
    ("documents", "Personal", "Documents"),
    ("pictures", "My Pictures", "Pictures"),
    ("music", "My Music", "Music"),
    ("videos", "My Video", "Videos"),
]

# [v49] 학교에서 실제로 쓰는 메신저 프로그램(CoolMessenger)의 수신 파일
# 저장 경로. 다른 메신저는 저장 위치가 제각각이라 자동 인식이 불가능하지만,
# 이 컴퓨터(들)에서는 이 경로로 고정해서 써도 되므로 기본값으로 못박아 둔다.
# 사용자가 환경설정에서 다른 경로로 직접 바꾸면 그 값이 그대로 유지된다
# (아래 마이그레이션은 "아직 비어 있는 경우"에만 채워 넣는다).
_MESSENGER_DEFAULT_PATH = r"C:\Users\User\Documents\CoolMessenger Files\Received Files"

# [v47] 즐겨찾기 스키마 버전 — 이전 버전에서 이미 즐겨찾기를 저장해 둔
# 사용자라도, 새로 추가/변경된 기본값을 한 번은 자동으로 채워 넣기 위한
# 마이그레이션 플래그. quick_links 자체를 덮어쓰지 않고 "새로 생긴 종류가
# 없으면 추가"/"비어 있던 값만 채움" 방식이므로, 사용자가 이미 손댄
# 목록(순서 변경, 삭제, 직접 입력한 경로 등)은 그대로 보존된다.
# v2: 문서/사진/음악/동영상 4종 추가
# v3: [v49] 메신저 폴더 기본 경로(CoolMessenger) 채움
QUICKLINK_SCHEMA_VERSION = 3


class Config:
    # [v37] 이미지 편집 모드 썸네일 캐시 개수 — 사용자가 컴퓨팅 환경에 맞게
    # 조절할 수 있도록 환경설정에 노출한다. 썸네일 1장(72x72 RGBA)은 실측
    # 약 20KB이므로, 개수 x 20KB가 대략적인 메모리 사용량이다.
    THUMB_CACHE_MIN = 500        # 최소값 — 너무 작으면 개선 효과가 거의 없음
    THUMB_CACHE_MAX = 20000      # 최대값 — 약 400MB 이내로 제한(저사양 PC 보호)
    THUMB_CACHE_DEFAULT = 3000   # 기본값 — 약 60MB, 대부분의 사용 패턴에 충분

    def __init__(self):
        s = QSettings("SRIHS", "FolderSync")
        self.direction = s.value("direction", "both")          # both / l2r / r2l
        self.mirror    = s.value("mirror", False, type=bool)   # 삭제 반영(미러)
        self.backup    = s.value("backup", True, type=bool)    # 덮어쓰기/삭제 백업
        self.preview   = s.value("preview", True, type=bool)   # 실행 전 미리보기
        self.language  = s.value("language", "ko")             # [v25] ko/en/ja
        # [v37] 썸네일 캐시 개수 — 저장된 값이 범위를 벗어나면(예: 이전 버전의
        # 값이거나 레지스트리 수동 조작) 안전하게 클램프한다.
        raw_cache = s.value("thumb_cache_size", self.THUMB_CACHE_DEFAULT, type=int)
        self.thumb_cache_size = max(self.THUMB_CACHE_MIN, min(self.THUMB_CACHE_MAX, raw_cache))

        # [v45] 즐겨찾기 바로가기(트리 위 "바탕화면/다운로드/메신저 폴더" 등).
        # 저장된 값이 아예 없으면(최초 실행) 이 컴퓨터의 실제 경로를
        # 레지스트리에서 찾아 기본 항목을 만들어 둔다. 한 번이라도
        # 저장된 적이 있으면(사용자가 이미 손을 댔을 수 있으므로) 그 값을
        # 그대로 쓰고 다시 시드하지 않는다 — 단, [v47] 새로 추가된 종류만
        # 마이그레이션으로 보충한다(아래 참고).
        if s.contains("quick_links"):
            raw_links = s.value("quick_links", "")
            try:
                data = json.loads(raw_links) if raw_links else []
                self.quick_links = data if isinstance(data, list) else []
            except (json.JSONDecodeError, TypeError):
                self.quick_links = []
            self._migrate_quick_links(s)
        else:
            self.quick_links = self.default_quick_links()
            s.setValue("quicklinks_schema_version", QUICKLINK_SCHEMA_VERSION)

    def _migrate_quick_links(self, s):
        """[v47] v45~v46에서 이미 즐겨찾기를 저장해 둔 사용자를 위한 1회성
        보충 시딩. "문서/사진/음악/동영상"처럼 이번에 새로 추가된 기본
        종류가 목록에 하나도 없으면(icon 필드로 판별) 추가해 준다 —
        기존에 사용자가 이미 편집해 둔 항목(순서/이름/삭제 등)은 절대
        건드리지 않는다.
        [v49] 메신저 폴더 기본 경로(CoolMessenger)도 여기서 함께 채운다 —
        단, 아직 경로가 비어 있는 경우에만. 사용자가 환경설정에서 이미
        다른 경로를 직접 입력해 두었다면 그 값을 덮어쓰지 않는다."""
        schema_ver = s.value("quicklinks_schema_version", 1, type=int)
        if schema_ver >= QUICKLINK_SCHEMA_VERSION:
            return
        existing_icons = {link.get("icon") for link in self.quick_links}
        for icon_kind, shell_key, fallback in _SYSTEM_QUICKLINK_SPECS:
            if icon_kind in ("desktop", "downloads"):
                continue  # 이전 버전에도 이미 있던 2종은 건드리지 않음
            if icon_kind in existing_icons:
                continue
            self.quick_links.append({
                "label": tr(f"quicklink.default.{icon_kind}"),
                "path": _resolve_special_folder(shell_key, fallback),
                "icon": icon_kind,
            })
        # [v49] 메신저 폴더로 보이는 항목(icon 필드가 아직 없는 v46 이전 저장분도
        # 포함해 라벨로만 판별 — 아이콘 필드 유무와 무관하게 매칭되도록 함)
        # 중 경로가 비어 있는 것만 기본값을 채운다.
        messenger_labels = set(TR.get("quicklink.default.messenger", {}).values())
        for link in self.quick_links:
            if link.get("label") in messenger_labels and not link.get("path"):
                link["path"] = _MESSENGER_DEFAULT_PATH
        s.setValue("quicklinks_schema_version", QUICKLINK_SCHEMA_VERSION)
        s.setValue("quick_links", json.dumps(self.quick_links, ensure_ascii=False))

    @staticmethod
    def default_quick_links():
        """[v47] 최초 실행 시 시드할 기본 바로가기 — 바탕화면/다운로드/문서/
        사진/음악/동영상(윈도우 탐색기의 가상 경로 폴더 6종) + 메신저 폴더.
        [v49] 메신저 폴더는 이 학교에서 실제로 쓰는 CoolMessenger의 수신
        파일 경로로 기본값을 채워 둔다(다른 메신저를 쓰게 되면 환경설정에서
        직접 바꾸면 된다)."""
        links = [
            {"label": tr(f"quicklink.default.{icon_kind}"),
             "path": _resolve_special_folder(shell_key, fallback),
             "icon": icon_kind}
            for icon_kind, shell_key, fallback in _SYSTEM_QUICKLINK_SPECS
        ]
        # [v47] 메신저 폴더는 6종 가상 경로 폴더가 아니라 사용자가 직접 지정하는
        # 항목이므로, 탐색기풍 글리프 대신 FolderKit 앱 아이콘을 붙인다("custom").
        links.append({"label": tr("quicklink.default.messenger"),
                      "path": _MESSENGER_DEFAULT_PATH, "icon": "custom"})
        return links

    def save(self):
        s = QSettings("SRIHS", "FolderSync")
        s.setValue("direction", self.direction)
        s.setValue("mirror", self.mirror)
        s.setValue("backup", self.backup)
        s.setValue("preview", self.preview)
        s.setValue("language", self.language)
        s.setValue("thumb_cache_size", self.thumb_cache_size)
        s.setValue("quick_links", json.dumps(self.quick_links, ensure_ascii=False))

    @staticmethod
    def reset_all():
        """[v19] 환경설정 다이얼로그의 '초기화' 버튼에서 호출.
        Config/HistoryManager가 공유하는 QSettings("SRIHS","FolderSync") 저장소를
        통째로 비운다(Windows 레지스트리 HKCU\\Software\\SRIHS\\FolderSync 등) —
        동기화 방향·정책 설정과 최근 작업 히스토리가 모두 초기화된다.
        (버전 폴더를 몇 개로 나누어 관리해도 이 두 문자열이 고정되어 있는 한
        모든 버전이 같은 저장소를 공유하므로, 특정 버전만 골라 초기화하는 것은
        불가능하다 — 전체 초기화만 지원한다.)"""
        QSettings("SRIHS", "FolderSync").clear()


# =============================================================================
# 1.5 최근 작업 히스토리 (좌·우 폴더 쌍) — QSettings에 JSON으로 저장
# =============================================================================
class HistoryManager:
    """동기화에 사용한 (좌, 우) 폴더 경로 쌍을 기록.
    - 항목: {"left":, "right":, "count":, "last_used":}
    - [v05] 정렬 기준: 최근 사용(last_used) 내림차순 — 가장 최근에 선택한 항목이 상단에 오도록
      (이전에는 사용 빈도(count) 우선이었으나, 최근 선택 우선으로 변경)
    - 저장된 경로가 더 이상 존재하지 않으면 호출 측(MainWindow)에서 remove() 호출"""
    MAX_ITEMS = 20

    def __init__(self):
        self.s = QSettings("SRIHS", "FolderSync")

    def _load(self) -> list:
        raw = self.s.value("sync_history", "")
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def _save(self, items: list):
        self.s.setValue("sync_history", json.dumps(items, ensure_ascii=False))

    def record(self, left: str, right: str):
        """동기화 성공 시 호출: 있으면 카운트 증가, 없으면 새로 추가."""
        items = self._load()
        now = datetime.now().isoformat(timespec="seconds")
        for it in items:
            if os.path.normpath(it.get("left", "")) == os.path.normpath(left) and \
               os.path.normpath(it.get("right", "")) == os.path.normpath(right):
                it["count"] = it.get("count", 0) + 1
                it["last_used"] = now
                break
        else:
            items.append({"left": left, "right": right, "count": 1, "last_used": now})
        items.sort(key=lambda x: x.get("last_used", ""), reverse=True)
        items = items[: self.MAX_ITEMS]
        self._save(items)

    def remove(self, left: str, right: str):
        """더 이상 존재하지 않는 경로 쌍을 목록에서 제거."""
        items = self._load()
        items = [it for it in items
                 if not (os.path.normpath(it.get("left", "")) == os.path.normpath(left) and
                         os.path.normpath(it.get("right", "")) == os.path.normpath(right))]
        self._save(items)

    def sorted_items(self) -> list:
        """[v05] 최근 선택 항목이 우선이 되도록 last_used 내림차순으로 반환."""
        items = self._load()
        items.sort(key=lambda x: x.get("last_used", ""), reverse=True)
        return items

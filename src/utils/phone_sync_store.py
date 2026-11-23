# -*- coding: utf-8 -*-
"""
FolderKit++ — 갤럭시폰 사진 옮기기 [v47] 전송 기록 저장소(순수 로직, Qt 없음)

"새 사진만 가져오기(증분 동기화)"의 핵심 — 어떤 사진을 이미 가져왔는지를
**보관함 폴더 안의 SQLite 파일 하나**에 적어 둔다.

    <보관함>/.folderkit/phone_sync.db

## 왜 QSettings가 아니라 보관함 폴더 안의 DB인가
1. 사진이 수천~수만 장이라 QSettings(레지스트리)에 넣기엔 너무 크다.
2. 기록이 보관함 폴더와 **함께 움직인다** — 보관함을 USB나 다른 컴퓨터로
   통째로 옮겨도 "어디까지 가져왔는지"가 그대로 따라온다.
3. 나중에 붙일 사진 자동 분류(인물·장소·행사)가 같은 DB에 표를 더해
   쓰기 좋다(파일 경로를 보관함 기준 상대 경로로 적어 두는 이유).

## 같은 사진인지 판단하는 기준(내부 키)
(기기 ID, 폰 안의 경로, 수정 시각(초), 크기) — 화면 문구와는 무관한
값만 쓴다. 크기를 모르는 경우(-1)에는 경로+수정 시각만으로 판단한다.

## 상태(status)는 내부 키로만 저장한다
- "pulled" : 실제로 내려받아 보관함에 저장한 사진
- "marked" : 내려받지는 않았지만 "이미 가져온 것으로 표시"한 사진
             (예전에 다른 방법으로 이미 옮겨 둔 사진을 또 받지 않으려고)
"""
import os
import sqlite3
import time
from contextlib import closing

DB_DIR_NAME = ".folderkit"
DB_FILE_NAME = "phone_sync.db"
SCHEMA_VERSION = 1

STATUS_PULLED = "pulled"
STATUS_MARKED = "marked"

UNKNOWN_SIZE = -1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS transfers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT    NOT NULL,
    remote_path TEXT    NOT NULL,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL DEFAULT -1,
    status      TEXT    NOT NULL,
    local_rel   TEXT,
    synced_at   INTEGER NOT NULL,
    UNIQUE (device_id, remote_path, mtime, size)
);
CREATE INDEX IF NOT EXISTS idx_transfers_device ON transfers (device_id);
"""


def db_path_for(library_dir):
    return os.path.join(library_dir, DB_DIR_NAME, DB_FILE_NAME)


def _size_of(photo):
    size = getattr(photo, "size", None)
    return UNKNOWN_SIZE if size is None else int(size)


class SyncStore:
    """보관함 폴더 하나에 딸린 전송 기록.

    메서드마다 연결을 새로 열고 닫는다 — SQLite 연결은 만든 스레드에서만
    쓸 수 있는데, 이 저장소는 화면(메인 스레드)과 전송 워커(다른 스레드)
    양쪽에서 불리기 때문이다. 호출 횟수가 사진 장수 수준이라 부담이 없다.
    """

    def __init__(self, library_dir):
        self.library_dir = library_dir
        self.db_path = db_path_for(library_dir)

    # ---------------------------------------------------------------- 연결
    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
        conn.commit()
        return conn

    # ---------------------------------------------------------------- 조회
    def known_index(self, device_id):
        """{(remote_path, mtime): {size, ...}} — 이 기기에서 이미 처리한 사진."""
        index = {}
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT remote_path, mtime, size FROM transfers WHERE device_id = ?", (device_id,))
            for remote_path, mtime, size in rows:
                index.setdefault((remote_path, mtime), set()).add(size)
        return index

    def filter_new(self, device_id, photos):
        """photos 중 아직 기록에 없는 것만(순서 유지)."""
        index = self.known_index(device_id)
        return [p for p in photos if not _is_known(index, p)]

    def count(self, device_id, status=None):
        with closing(self._connect()) as conn:
            if status is None:
                row = conn.execute("SELECT COUNT(*) FROM transfers WHERE device_id = ?", (device_id,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM transfers WHERE device_id = ? AND status = ?",
                                   (device_id, status)).fetchone()
        return row[0]

    def has_any(self, device_id):
        return self.count(device_id) > 0

    # ---------------------------------------------------------------- 기록
    def record(self, device_id, photo, status=STATUS_PULLED, local_rel=None):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO transfers "
                "(device_id, remote_path, mtime, size, status, local_rel, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (device_id, photo.remote_path, photo.epoch, _size_of(photo), status, local_rel, int(time.time())))
            conn.commit()

    def mark_all(self, device_id, photos):
        """photos 전부를 "이미 가져온 것"으로 한 번에 표시한다(내려받지 않음).
        이미 기록이 있는 사진은 건드리지 않는다. 반환: 새로 표시한 수."""
        now = int(time.time())
        rows = [(device_id, p.remote_path, p.epoch, _size_of(p), STATUS_MARKED, None, now) for p in photos]
        with closing(self._connect()) as conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO transfers "
                "(device_id, remote_path, mtime, size, status, local_rel, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows)
            conn.commit()
            return conn.total_changes - before


def _is_known(index, photo):
    sizes = index.get((photo.remote_path, photo.epoch))
    if not sizes:
        return False
    size = _size_of(photo)
    # 어느 한쪽이라도 크기를 모르면 경로+수정 시각이 같은 것으로 충분하다고 본다
    if size == UNKNOWN_SIZE or UNKNOWN_SIZE in sizes:
        return True
    return size in sizes


def plan_local_rel(photo):
    """보관함 안에서 이 사진이 놓일 상대 경로(항상 '/' 구분) —
    촬영(수정) 연·월 폴더로 나눈다: 2026/2026-11/20261108_101500.jpg"""
    y, m = photo.mtime.year, photo.mtime.month
    return f"{y:04d}/{y:04d}-{m:02d}/{photo.name}"


def unique_local_rel(library_dir, rel):
    """같은 이름의 파일이 이미 있으면 _2, _3 …을 붙여 덮어쓰지 않게 한다
    (폰에서 편집해 수정 시각만 바뀐 같은 이름의 사진 등)."""
    if not os.path.exists(os.path.join(library_dir, *rel.split("/"))):
        return rel
    folder, name = rel.rsplit("/", 1)
    stem, ext = os.path.splitext(name)
    n = 2
    while True:
        candidate = f"{folder}/{stem}_{n}{ext}"
        if not os.path.exists(os.path.join(library_dir, *candidate.split("/"))):
            return candidate
        n += 1

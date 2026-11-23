# -*- coding: utf-8 -*-
"""
FolderKit++ — 사진첩(행사·장소·인물 자동 분류) 핵심 로직 [v48, v49] (Qt 없음)

[v49] 장소(EXIF GPS → 시·군·구/해외 도시, geo_lookup)와 인물(선택 설치 얼굴
엔진, face_engine)을 더했다. 아래 설명은 v48의 행사 분류이고, 장소·인물은
이 파일 뒤쪽 "[v49]" 구역에 설명이 있다.

보관함 폴더(갤럭시폰 사진 옮기기의 그 보관함)의 사진을 **행사**로 묶는다.
자동 분류는 "초안"이고, 틀린 곳은 사용자가 고친다(옮기기·새 행사로 분리·
합치기·이름 바꾸기). 고친 내용은 다시 분석해도 지켜진다.

## 무엇으로 묶나 — 시간 + 가벼운 배경 비교
사진을 촬영 시각 순으로 늘어놓고 바로 앞 사진과 비교한다.

| 앞 사진과의 시간 간격 | 같은 행사로 보는 조건            |
|-----------------------|----------------------------------|
| 2시간 이내            | 무조건 (강당 → 운동장 이동 등)   |
| 2 ~ 12시간            | 배경이 비슷하면                  |
| 12 ~ 36시간           | 배경이 아주 비슷하면 (이틀짜리 행사) |
| 36시간 넘게           | 다른 행사 (매주 같은 실습실 수업) |

배경 비교는 새 라이브러리 없이 Pillow만 쓴다 — 사진을 아주 작게 줄여
(1) 색 분포(4×4×4 = 64칸 히스토그램)와 (2) 밝기 배치(8×8 흑백)를 뽑아
128바이트 "특징값"으로 저장하고, 두 사진의 특징값 거리(0~1)를 잰다.
내용을 이해하지는 못하지만 "같은 강당", "같은 운동장" 정도는 구분한다.

## 저장
    <보관함>/.folderkit/photo_album.db
- photos : 사진 한 장(보관함 기준 상대 경로, 크기, 수정 시각, 촬영 시각,
           특징값, 속한 행사, 사용자가 직접 정했는지)
- events : 행사(이름 — 비어 있으면 자동 이름, 즉 날짜로 표시)
화면에 보일 문구는 저장하지 않는다 — 자동 이름은 날짜로부터 표시할 때
만든다(언어를 바꿔도 맞게 보이도록, 내부 값과 화면 문구 분리 원칙).

## "직접 고친 것"의 규칙
- 사용자가 손댄 행사는 "확정"(locked=1)이 된다: 사진을 옮겨 넣거나 뺀
  행사, 분리해 만든 행사, 합친 행사, 이름을 바꾼 행사.
- "다시 분류"는 확정된 행사를 통째로 그대로 두고 나머지만 새로 묶는다.
  (사진 한 장만 지키면 그 행사의 다른 사진이 다시 섞여, 사용자가 의도한
  묶음이 깨진다 — 실제로 검사에서 드러난 문제.)
- 옮긴 사진에는 manual=1 도 남긴다(기록용).
- 새 사진이 들어오면 새 사진만 기존 행사에 붙이거나 새 행사를 만든다 —
  이미 분류된 사진은 다시 건드리지 않는다.
"""
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime

from PIL import Image

from .image_io import orientation_of, apply_orientation

DB_DIR_NAME = ".folderkit"
DB_FILE_NAME = "photo_album.db"
SCHEMA_VERSION = 2   # [v49] 장소·인물 칸 추가(v1 DB는 열 때 자동으로 덧붙인다)

ALBUM_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif")

# ---- 행사 묶기 기준(초) ----
NEAR_GAP = 2 * 3600       # 이내면 무조건 같은 행사
MID_GAP = 12 * 3600       # 이내면 배경이 비슷할 때 같은 행사
FAR_GAP = 36 * 3600       # 이내면 배경이 아주 비슷할 때 같은 행사, 넘으면 다른 행사
SIMILAR = 0.30            # 특징값 거리 — 이하면 "비슷하다"
VERY_SIMILAR = 0.18       # 이하면 "아주 비슷하다"

FEATURE_LEN = 128         # 히스토그램 64 + 밝기 배치 64
UNREADABLE = b""          # 열 수 없었던 사진의 특징값(분석은 끝났다는 표시)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT,
    locked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS photos (
    rel      TEXT PRIMARY KEY,
    size     INTEGER NOT NULL,
    mtime    INTEGER NOT NULL,
    taken    INTEGER,
    feature  BLOB,
    event_id INTEGER,
    manual   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_photos_event ON photos (event_id);
CREATE TABLE IF NOT EXISTS persons (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT,
    locked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS faces (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rel       TEXT NOT NULL,
    x REAL, y REAL, w REAL, h REAL,
    score     REAL,
    emb       BLOB NOT NULL,
    thumb     BLOB,
    person_id INTEGER,
    excluded  INTEGER NOT NULL DEFAULT 0,
    manual    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_faces_rel ON faces (rel);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces (person_id);
"""

# [v49] v1(v48.0) DB에 덧붙이는 칸 — 기존 기록(행사·직접 고친 것)은 그대로 둔다
_PHOTO_COLUMNS_V2 = (
    ("lat", "REAL"), ("lon", "REAL"),
    ("place", "TEXT"),                              # 장소 내부 키(geo_lookup.place_key)
    ("gps_done", "INTEGER NOT NULL DEFAULT 0"),     # GPS를 읽었는지
    ("faces_done", "INTEGER NOT NULL DEFAULT 0"),   # 얼굴을 찾았는지
)


def db_path_for(library_dir):
    return os.path.join(library_dir, DB_DIR_NAME, DB_FILE_NAME)


def to_rel(library_dir, path):
    return os.path.relpath(path, library_dir).replace(os.sep, "/")


def to_abs(library_dir, rel):
    return os.path.join(library_dir, *rel.split("/"))


# =============================================================================
# 파일 찾기
# =============================================================================
def scan_library(library_dir):
    """보관함 안의 사진 [(상대 경로, 크기, 수정 시각(초)), ...].
    이름이 "."으로 시작하는 폴더(.folderkit 등)와 파일, 전송 중인 .part는 뺀다."""
    found = []
    for root, dirs, files in os.walk(library_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or not name.lower().endswith(ALBUM_IMAGE_EXTS):
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            found.append((to_rel(library_dir, path), st.st_size, int(st.st_mtime)))
    return found


# =============================================================================
# 촬영 시각 + 특징값
# =============================================================================
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003
_DATETIME_DIGITIZED = 0x9004
_DATETIME = 0x0132


def parse_exif_datetime(text):
    """"2026:11:08 10:15:00" → epoch 초. 형식이 아니거나 0000:00:00이면 None."""
    if not text:
        return None
    if isinstance(text, bytes):
        text = text.decode("ascii", "ignore")
    text = str(text).strip().rstrip("\x00")
    try:
        return int(datetime.strptime(text[:19], "%Y:%m:%d %H:%M:%S").timestamp())
    except (ValueError, OverflowError, OSError):
        return None


def read_taken_time(img):
    """EXIF의 촬영 시각(원본 → 디지털화 → 파일 기록 순) — 없으면 None."""
    try:
        exif = img.getexif()
    except Exception:   # noqa: BLE001
        return None
    try:
        sub = exif.get_ifd(_EXIF_IFD)
    except Exception:   # noqa: BLE001
        sub = {}
    for value in (sub.get(_DATETIME_ORIGINAL), sub.get(_DATETIME_DIGITIZED), exif.get(_DATETIME)):
        ts = parse_exif_datetime(value)
        if ts is not None:
            return ts
    return None


_GPS_IFD = 0x8825


def _rational(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        try:
            return v[0] / v[1]
        except Exception:   # noqa: BLE001
            return None


def _dms_to_deg(dms, ref):
    try:
        d, m, s = (_rational(x) for x in dms)
    except (TypeError, ValueError):
        return None
    if d is None or m is None or s is None:
        return None
    deg = d + m / 60.0 + s / 3600.0
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", "ignore")
    if str(ref).strip().upper() in ("S", "W"):
        deg = -deg
    return deg


def read_gps(img):
    """[v49] EXIF GPS → (위도, 경도). 없거나 이상하면 (None, None)."""
    try:
        gps = img.getexif().get_ifd(_GPS_IFD)
    except Exception:   # noqa: BLE001
        return None, None
    if not gps or 2 not in gps or 4 not in gps:
        return None, None
    lat = _dms_to_deg(gps.get(2), gps.get(1, "N"))
    lon = _dms_to_deg(gps.get(4), gps.get(3, "E"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None, None
    return lat, lon


def read_gps_file(path):
    try:
        with Image.open(path) as img:
            return read_gps(img)
    except Exception:   # noqa: BLE001
        return None, None


def feature_from_image(img):
    """이미 사람이 보는 방향으로 돌려 놓은 RGB 이미지 → 128바이트 특징값."""
    rgb = img.convert("RGB")
    small = rgb.resize((32, 32), Image.Resampling.BILINEAR)
    counts = [0] * 64
    for r, g, b in small.getdata():
        counts[(r >> 6) * 16 + (g >> 6) * 4 + (b >> 6)] += 1
    total = float(sum(counts)) or 1.0
    hist = bytes(min(255, int(round(c / total * 255))) for c in counts)
    layout = bytes(rgb.convert("L").resize((8, 8), Image.Resampling.BILINEAR).getdata())
    return hist + layout


def analyze_file(path, fallback_time):
    """(촬영 시각, 특징값). 열 수 없으면 (fallback_time, UNREADABLE).
    JPEG는 draft()로 작게 디코딩해서 큰 사진도 빠르다. GPS는 read_gps()로 따로."""
    try:
        with Image.open(path) as img:
            taken = read_taken_time(img)
            orientation = orientation_of(img)
            try:
                img.draft("RGB", (128, 128))
            except Exception:   # noqa: BLE001 — draft를 지원하지 않는 형식
                pass
            img.load()
            oriented = apply_orientation(img, orientation)
            feature = feature_from_image(oriented)
    except Exception:   # noqa: BLE001
        return fallback_time, UNREADABLE
    return (taken if taken is not None else fallback_time), feature


def feature_distance(a, b):
    """두 특징값의 거리 0(같음)~1(전혀 다름). 하나라도 없으면 1."""
    if not a or not b or len(a) != FEATURE_LEN or len(b) != FEATURE_LEN:
        return 1.0
    hist = sum(abs(x - y) for x, y in zip(a[:64], b[:64])) / 510.0
    layout = sum(abs(x - y) for x, y in zip(a[64:], b[64:])) / (64 * 255.0)
    return min(1.0, 0.6 * hist + 0.4 * layout)


def same_event(taken_a, feat_a, taken_b, feat_b):
    gap = abs(taken_a - taken_b)
    if gap <= NEAR_GAP:
        return True
    if gap > FAR_GAP:
        return False
    dist = feature_distance(feat_a, feat_b)
    if gap <= MID_GAP:
        return dist <= SIMILAR
    return dist <= VERY_SIMILAR


LOOKAROUND = 20   # 앞뒤로 비교해 볼 사진 수(시간 간격 FAR_GAP 안에서)


def _match_neighbors(photos, i, taken, feat):
    """photos[i]가 붙을 행사 id — 없으면 None.
    바로 앞 사진만 보면 "강당 → 운동장 → (몇 시간 뒤) 다시 강당"에서 마지막
    강당 사진이 떨어져 나가므로, 앞쪽(가까운 순) 최근 사진 여러 장과 비교한다.
    앞에서 못 찾으면 뒤쪽(이미 행사가 있는 사진)과도 비교한다 — 예전 사진을
    나중에 보관함에 넣은 경우를 위해서."""
    for j in range(i - 1, max(-1, i - 1 - LOOKAROUND), -1):
        other = photos[j]
        if taken - other[1] > FAR_GAP:
            break
        if other[3] is not None and same_event(other[1], other[2], taken, feat):
            return other[3]
    for j in range(i + 1, min(len(photos), i + 1 + LOOKAROUND)):
        other = photos[j]
        if other[1] - taken > FAR_GAP:
            break
        if other[3] is not None and same_event(taken, feat, other[1], other[2]):
            return other[3]
    return None


def event_date_texts(start_ts, end_ts):
    """행사 이름이 없을 때 보여 줄 날짜 (시작, 끝) — 하루짜리면 끝은 None.
    사진 옮기기의 날짜 목록과 같은 규칙(시작엔 항상 연도, 해를 넘기면 끝에도)."""
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)
    start_text = start.strftime("%Y/%m/%d")
    if start.date() == end.date():
        return start_text, None
    end_text = end.strftime("%m/%d") if start.year == end.year else end.strftime("%Y/%m/%d")
    return start_text, end_text


# =============================================================================
# [v49] 장소·인물 공통 상수
# =============================================================================
NO_PLACE = "NONE"         # 위치 정보 없는 사진 묶음 — 내부 키
FACE_DIM = 128
PERSON_JOIN = 0.40        # 인물 평균 얼굴과 코사인 유사도가 이 이상이면 같은 사람
                          # (OpenCV가 SFace에 권하는 같은 사람 기준 0.363보다 조금 엄격하게)
MIN_PERSON_PHOTOS = 3     # 사진이 이보다 적은 인물은 "자주 안 나온 얼굴"로 모아 보여 준다


def _unit(v):
    import numpy as np
    n = float(np.linalg.norm(v)) or 1.0
    return (v / n).astype(np.float32)


class PersonInfo:
    __slots__ = ("id", "name", "count", "thumb", "locked")

    def __init__(self, person_id, name, count, thumb, locked):
        self.id, self.name, self.count, self.thumb, self.locked = person_id, name, count, thumb, locked


# =============================================================================
# 저장소
# =============================================================================
class EventInfo:
    __slots__ = ("id", "name", "start", "end", "count")

    def __init__(self, event_id, name, start, end, count):
        self.id, self.name, self.start, self.end, self.count = event_id, name, start, end, count


class AlbumStore:
    """보관함 하나의 사진첩 DB. 메서드마다 연결을 열고 닫는다(분석 워커
    스레드와 화면 양쪽에서 부르기 때문 — phone_sync_store와 같은 방식)."""

    def __init__(self, library_dir):
        self.library_dir = library_dir
        self.db_path = db_path_for(library_dir)

    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.executescript(_SCHEMA)
        have = {row[1] for row in conn.execute("PRAGMA table_info(photos)")}
        for name, decl in _PHOTO_COLUMNS_V2:
            if name not in have:
                conn.execute(f"ALTER TABLE photos ADD COLUMN {name} {decl}")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
        return conn

    # ---------------------------------------------------------------- 파일 목록 맞추기
    def sync_files(self, scanned):
        """폴더를 훑은 결과에 DB를 맞춘다. 없어진 사진은 지우고, 새 사진은
        넣고, 크기·수정 시각이 바뀐 사진(편집해서 저장한 경우 등)은 특징값만
        다시 계산하게 비운다(속한 행사는 그대로). 반환: 지운 수."""
        current = {rel: (size, mtime) for rel, size, mtime in scanned}
        with closing(self._connect()) as conn:
            known = {rel: (size, mtime) for rel, size, mtime in
                     conn.execute("SELECT rel, size, mtime FROM photos")}
            gone = [rel for rel in known if rel not in current]
            conn.executemany("DELETE FROM photos WHERE rel = ?", [(r,) for r in gone])
            conn.executemany("DELETE FROM faces WHERE rel = ?", [(r,) for r in gone])
            for rel, (size, mtime) in current.items():
                old = known.get(rel)
                if old is None:
                    conn.execute("INSERT INTO photos (rel, size, mtime) VALUES (?, ?, ?)", (rel, size, mtime))
                elif old != (size, mtime):
                    # 편집해 저장한 사진 — 특징값·GPS·얼굴을 다시 구한다(속한 행사는 그대로)
                    conn.execute("UPDATE photos SET size = ?, mtime = ?, feature = NULL, gps_done = 0, "
                                 "faces_done = 0 WHERE rel = ?", (size, mtime, rel))
                    conn.execute("DELETE FROM faces WHERE rel = ?", (rel,))
            self._drop_empty_events(conn)
            self._drop_empty_persons(conn)
            conn.commit()
        return len(gone)

    def pending_analysis(self):
        """[(상대 경로, 수정 시각), ...] — 아직 특징값이 없는 사진."""
        with closing(self._connect()) as conn:
            return list(conn.execute("SELECT rel, mtime FROM photos WHERE feature IS NULL ORDER BY rel"))

    def save_analysis(self, rows):
        """rows: [(상대 경로, 촬영 시각, 특징값), ...]"""
        with closing(self._connect()) as conn:
            conn.executemany("UPDATE photos SET taken = ?, feature = ? WHERE rel = ?",
                             [(taken, sqlite3.Binary(feat), rel) for rel, taken, feat in rows])
            conn.commit()

    # ---------------------------------------------------------------- 자동 분류
    def assign_unassigned(self):
        """아직 행사가 없는(분석은 끝난) 사진만 묶는다. 이미 분류된 사진은
        건드리지 않는다. 반환: 새로 묶은 사진 수."""
        with closing(self._connect()) as conn:
            rows = list(conn.execute(
                "SELECT rel, taken, feature, event_id FROM photos "
                "WHERE feature IS NOT NULL AND taken IS NOT NULL ORDER BY taken, rel"))
            photos = [[rel, taken, bytes(feat), event_id] for rel, taken, feat, event_id in rows]
            changed = 0
            for i, photo in enumerate(photos):
                if photo[3] is not None:
                    continue
                rel, taken, feat, _ = photo
                target = _match_neighbors(photos, i, taken, feat)
                if target is None:
                    target = conn.execute("INSERT INTO events (name) VALUES (NULL)").lastrowid
                photo[3] = target
                conn.execute("UPDATE photos SET event_id = ? WHERE rel = ?", (target, rel))
                changed += 1
            conn.commit()
        return changed

    def regroup(self):
        """다시 분류 — 사용자가 손댄(확정된) 행사는 그대로 두고, 나머지 사진은
        행사에서 빼서 새로 묶는다. 반환: 새로 묶은 사진 수."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE photos SET event_id = NULL WHERE "
                "event_id IS NULL OR event_id IN (SELECT id FROM events WHERE locked = 0)")
            self._drop_empty_events(conn)
            conn.commit()
        return self.assign_unassigned()

    # ---------------------------------------------------------------- 조회
    def events(self):
        """[EventInfo, ...] — 최근 행사가 위로."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT e.id, e.name, MIN(p.taken), MAX(p.taken), COUNT(*) FROM events e "
                "JOIN photos p ON p.event_id = e.id GROUP BY e.id ORDER BY MIN(p.taken) DESC, e.id DESC")
            return [EventInfo(*row) for row in rows]

    def photos_of(self, event_id):
        """행사에 속한 사진의 절대 경로(촬영 시각 순)."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT rel FROM photos WHERE event_id = ? ORDER BY taken, rel", (event_id,))
            return [to_abs(self.library_dir, rel) for (rel,) in rows]

    def event_of(self, path):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT event_id FROM photos WHERE rel = ?",
                               (to_rel(self.library_dir, path),)).fetchone()
        return row[0] if row else None

    def counts(self):
        """(전체 사진 수, 분석이 끝난 수)"""
        with closing(self._connect()) as conn:
            total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            done = conn.execute("SELECT COUNT(*) FROM photos WHERE feature IS NOT NULL").fetchone()[0]
        return total, done

    # ---------------------------------------------------------------- 사용자 정정
    @staticmethod
    def _lock_sources(conn, rels):
        """사진을 빼 가는 원래 행사들도 사용자가 손댄 것이므로 확정한다."""
        for rel in rels:
            conn.execute("UPDATE events SET locked = 1 WHERE id = "
                         "(SELECT event_id FROM photos WHERE rel = ?)", (rel,))

    def move_photos(self, paths, event_id):
        """사진들을 다른 행사로 옮긴다(옮겨 간 쪽·빠진 쪽 행사 모두 확정)."""
        rels = [to_rel(self.library_dir, p) for p in paths]
        with closing(self._connect()) as conn:
            self._lock_sources(conn, rels)
            conn.execute("UPDATE events SET locked = 1 WHERE id = ?", (event_id,))
            conn.executemany("UPDATE photos SET event_id = ?, manual = 1 WHERE rel = ?",
                             [(event_id, r) for r in rels])
            self._drop_empty_events(conn)
            conn.commit()

    def new_event_with(self, paths, name=None):
        """사진들로 새 행사를 만든다. 반환: 새 행사 id."""
        rels = [to_rel(self.library_dir, p) for p in paths]
        with closing(self._connect()) as conn:
            self._lock_sources(conn, rels)
            event_id = conn.execute("INSERT INTO events (name, locked) VALUES (?, 1)", (name,)).lastrowid
            conn.executemany("UPDATE photos SET event_id = ?, manual = 1 WHERE rel = ?",
                             [(event_id, r) for r in rels])
            self._drop_empty_events(conn)
            conn.commit()
        return event_id

    def merge_events(self, event_ids):
        """여러 행사를 하나로 — 이름이 있는 행사가 있으면 그쪽(여럿이면 앞의 것),
        없으면 가장 이른 행사로 모은다. 반환: 남은 행사 id."""
        ids = list(dict.fromkeys(event_ids))
        if len(ids) < 2:
            return ids[0] if ids else None
        with closing(self._connect()) as conn:
            marks = ",".join("?" * len(ids))
            rows = list(conn.execute(
                f"SELECT e.id, e.name, MIN(p.taken) FROM events e LEFT JOIN photos p ON p.event_id = e.id "
                f"WHERE e.id IN ({marks}) GROUP BY e.id", ids))
            if not rows:
                return None
            named = [r for r in rows if r[1]]
            pool = named or rows
            target = min(pool, key=lambda r: (r[2] if r[2] is not None else 0, r[0]))[0]
            conn.execute(f"UPDATE photos SET event_id = ?, manual = 1 WHERE event_id IN ({marks})",
                         [target] + ids)
            conn.execute("UPDATE events SET locked = 1 WHERE id = ?", (target,))
            self._drop_empty_events(conn)
            conn.commit()
        return target

    def rename_event(self, event_id, name):
        """이름을 바꾼다. 빈 문자열/None이면 자동 이름(날짜)으로 되돌린다.
        이름을 되돌려도 사용자가 손댄 행사이므로 확정은 유지한다."""
        name = (name or "").strip() or None
        with closing(self._connect()) as conn:
            conn.execute("UPDATE events SET name = ?, locked = 1 WHERE id = ?", (name, event_id))
            conn.commit()

    # =================================================================
    # [v49] 장소
    # =================================================================
    def pending_gps(self):
        with closing(self._connect()) as conn:
            return [r for (r,) in conn.execute("SELECT rel FROM photos WHERE gps_done = 0 ORDER BY rel")]

    def save_gps(self, rows):
        """rows: [(상대 경로, 위도, 경도, 장소 키), ...]"""
        with closing(self._connect()) as conn:
            conn.executemany("UPDATE photos SET lat = ?, lon = ?, place = ?, gps_done = 1 WHERE rel = ?",
                             [(lat, lon, key, rel) for rel, lat, lon, key in rows])
            conn.commit()

    def place_counts(self):
        """{장소 키: 사진 수} — 위치 정보가 없는 사진은 NO_PLACE 키로."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT place, COUNT(*) FROM photos WHERE gps_done = 1 GROUP BY place")
            return {(key or NO_PLACE): n for key, n in rows}

    def photos_of_place(self, key):
        """장소 키(시·군·구/도시) 또는 묶음 키(시·도/나라), 또는 NO_PLACE의 사진."""
        from .geo_lookup import group_of
        with closing(self._connect()) as conn:
            rows = list(conn.execute("SELECT rel, place FROM photos WHERE gps_done = 1 ORDER BY taken, rel"))
        if key == NO_PLACE:
            rels = [rel for rel, place in rows if not place]
        else:
            rels = [rel for rel, place in rows if place and (place == key or group_of(place) == key)]
        return [to_abs(self.library_dir, rel) for rel in rels]

    # =================================================================
    # [v49] 인물
    # =================================================================
    def pending_faces(self):
        with closing(self._connect()) as conn:
            return [r for (r,) in conn.execute(
                "SELECT rel FROM photos WHERE faces_done = 0 ORDER BY taken, rel")]

    def save_faces(self, rel, faces):
        """faces: face_engine.FaceEngine.analyze()의 결과."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM faces WHERE rel = ?", (rel,))
            conn.executemany(
                "INSERT INTO faces (rel, x, y, w, h, score, emb, thumb) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(rel, b[0], b[1], b[2], b[3], score, sqlite3.Binary(emb), sqlite3.Binary(thumb))
                 for b, score, emb, thumb in faces])
            conn.execute("UPDATE photos SET faces_done = 1 WHERE rel = ?", (rel,))
            conn.commit()

    def faces_analyzed(self):
        """(얼굴을 찾은 사진 수, 전체 사진 수)"""
        with closing(self._connect()) as conn:
            done = conn.execute("SELECT COUNT(*) FROM photos WHERE faces_done = 1").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        return done, total

    def assign_faces(self):
        """아직 인물이 없는(빼기로 고른 것 제외) 얼굴을 묶는다. 이미 묶인 얼굴은
        건드리지 않는다. 기존 인물의 평균 얼굴과 코사인 유사도가 PERSON_JOIN 이상이면
        그 인물에, 아니면 새 인물로. 반환: 새로 묶은 얼굴 수. (numpy 필요)"""
        import numpy as np
        with closing(self._connect()) as conn:
            todo = list(conn.execute(
                "SELECT f.id, f.emb FROM faces f JOIN photos p ON p.rel = f.rel "
                "WHERE f.person_id IS NULL AND f.excluded = 0 ORDER BY p.taken, f.id"))
            if not todo:
                return 0
            sums, counts, ids = {}, {}, []
            for pid, emb in conn.execute("SELECT person_id, emb FROM faces WHERE person_id IS NOT NULL"):
                v = np.frombuffer(emb, dtype=np.float32)
                if pid in sums:
                    sums[pid] = sums[pid] + v
                    counts[pid] += 1
                else:
                    sums[pid] = v.copy()
                    counts[pid] = 1
            ids = list(sums)
            centroids = [_unit(sums[i]) for i in ids]
            matrix = np.vstack(centroids) if centroids else np.zeros((0, FACE_DIM), dtype=np.float32)
            updates = []
            for face_id, emb in todo:
                v = np.frombuffer(emb, dtype=np.float32)
                target = None
                if len(ids):
                    sims = matrix @ v
                    best = int(np.argmax(sims))
                    if float(sims[best]) >= PERSON_JOIN:
                        target = ids[best]
                        sums[target] = sums[target] + v
                        counts[target] += 1
                        matrix[best] = _unit(sums[target])
                if target is None:
                    target = conn.execute("INSERT INTO persons (name) VALUES (NULL)").lastrowid
                    ids.append(target)
                    sums[target] = v.copy()
                    counts[target] = 1
                    matrix = np.vstack([matrix, _unit(v)[None, :]])
                updates.append((target, face_id))
            conn.executemany("UPDATE faces SET person_id = ? WHERE id = ?", updates)
            conn.commit()
        return len(updates)

    def regroup_persons(self):
        """다시 분류(인물) — 손댄 인물은 그대로, 나머지 얼굴은 새로 묶는다."""
        with closing(self._connect()) as conn:
            conn.execute("UPDATE faces SET person_id = NULL WHERE manual = 0 AND "
                         "person_id IN (SELECT id FROM persons WHERE locked = 0)")
            self._drop_empty_persons(conn)
            conn.commit()
        return self.assign_faces()

    def persons(self):
        """[PersonInfo, ...] — 사진첩에 보일 인물(사진이 MIN_PERSON_PHOTOS장 이상이거나
        이름을 붙였거나 손댄 인물). 사진이 많은 순. 대표 얼굴은 점수가 가장 높은 것."""
        with closing(self._connect()) as conn:
            rows = list(conn.execute(
                "SELECT p.id, p.name, p.locked, COUNT(DISTINCT f.rel) FROM persons p "
                "JOIN faces f ON f.person_id = p.id GROUP BY p.id"))
            out = []
            for pid, name, locked, n in rows:
                if n < MIN_PERSON_PHOTOS and not name and not locked:
                    continue
                thumb = conn.execute("SELECT thumb FROM faces WHERE person_id = ? ORDER BY score DESC LIMIT 1",
                                     (pid,)).fetchone()
                out.append(PersonInfo(pid, name, n, bytes(thumb[0]) if thumb and thumb[0] else b"", bool(locked)))
        out.sort(key=lambda p: (p.name is None, -p.count, p.id))
        return out

    def _minor_person_ids(self, conn):
        rows = conn.execute(
            "SELECT p.id FROM persons p JOIN faces f ON f.person_id = p.id "
            "WHERE p.name IS NULL AND p.locked = 0 GROUP BY p.id HAVING COUNT(DISTINCT f.rel) < ?",
            (MIN_PERSON_PHOTOS,))
        return [r[0] for r in rows]

    def minor_person_ids(self):
        """"자주 안 나온 얼굴" 묶음에 들어가는 인물들의 id."""
        with closing(self._connect()) as conn:
            return self._minor_person_ids(conn)

    def photos_of_persons(self, person_ids):
        ids = list(person_ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT p.rel FROM faces f JOIN photos p ON p.rel = f.rel "
                f"WHERE f.person_id IN ({marks}) ORDER BY p.taken, p.rel", ids)
            return [to_abs(self.library_dir, rel) for (rel,) in rows]

    def _face_ids(self, conn, paths, from_ids):
        rels = [to_rel(self.library_dir, p) for p in paths]
        ids = list(from_ids)
        if not rels or not ids:
            return []
        out = []
        marks = ",".join("?" * len(ids))
        for rel in rels:
            out += [r[0] for r in conn.execute(
                f"SELECT id FROM faces WHERE rel = ? AND person_id IN ({marks})", [rel] + ids)]
        return out

    def _lock_persons(self, conn, ids):
        conn.executemany("UPDATE persons SET locked = 1 WHERE id = ?", [(i,) for i in ids if i is not None])

    def move_faces(self, paths, from_ids, person_id):
        """사진들 속에서 from_ids 인물의 얼굴을 person_id 인물로 옮긴다."""
        with closing(self._connect()) as conn:
            faces = self._face_ids(conn, paths, from_ids)
            self._lock_persons(conn, list(from_ids) + [person_id])
            conn.executemany("UPDATE faces SET person_id = ?, manual = 1, excluded = 0 WHERE id = ?",
                             [(person_id, f) for f in faces])
            self._drop_empty_persons(conn)
            conn.commit()
        return len(faces)

    def new_person_with(self, paths, from_ids, name=None):
        with closing(self._connect()) as conn:
            faces = self._face_ids(conn, paths, from_ids)
            if not faces:
                return None
            pid = conn.execute("INSERT INTO persons (name, locked) VALUES (?, 1)", (name,)).lastrowid
            self._lock_persons(conn, from_ids)
            conn.executemany("UPDATE faces SET person_id = ?, manual = 1 WHERE id = ?", [(pid, f) for f in faces])
            self._drop_empty_persons(conn)
            conn.commit()
        return pid

    def exclude_faces(self, paths, from_ids):
        """"이 사람이 아님" — 얼굴을 인물에서 빼고, 다시 분류해도 묶지 않는다."""
        with closing(self._connect()) as conn:
            faces = self._face_ids(conn, paths, from_ids)
            self._lock_persons(conn, from_ids)
            conn.executemany("UPDATE faces SET person_id = NULL, excluded = 1, manual = 1 WHERE id = ?",
                             [(f,) for f in faces])
            self._drop_empty_persons(conn)
            conn.commit()
        return len(faces)

    def merge_persons(self, person_ids):
        ids = list(dict.fromkeys(person_ids))
        if len(ids) < 2:
            return ids[0] if ids else None
        with closing(self._connect()) as conn:
            marks = ",".join("?" * len(ids))
            rows = list(conn.execute(
                f"SELECT p.id, p.name, COUNT(f.id) FROM persons p LEFT JOIN faces f ON f.person_id = p.id "
                f"WHERE p.id IN ({marks}) GROUP BY p.id", ids))
            if not rows:
                return None
            named = [r for r in rows if r[1]]
            target = max(named or rows, key=lambda r: (r[2], -r[0]))[0]
            conn.execute(f"UPDATE faces SET person_id = ?, manual = 1 WHERE person_id IN ({marks})", [target] + ids)
            conn.execute("UPDATE persons SET locked = 1 WHERE id = ?", (target,))
            self._drop_empty_persons(conn)
            conn.commit()
        return target

    def rename_person(self, person_id, name):
        name = (name or "").strip() or None
        with closing(self._connect()) as conn:
            conn.execute("UPDATE persons SET name = ?, locked = 1 WHERE id = ?", (name, person_id))
            conn.commit()

    @staticmethod
    def _drop_empty_persons(conn):
        conn.execute("DELETE FROM persons WHERE id NOT IN "
                     "(SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")

    @staticmethod
    def _drop_empty_events(conn):
        conn.execute("DELETE FROM events WHERE id NOT IN "
                     "(SELECT DISTINCT event_id FROM photos WHERE event_id IS NOT NULL)")


STAGE_SCAN = "scan"           # [v49] 분석 단계 — 내부 키(화면 문구는 번역 표에서)
STAGE_FEATURES = "features"
STAGE_GPS = "gps"
STAGE_FACES = "faces"


def run_analysis(library_dir, progress=None, cancelled=None, batch=50, face_engine_factory=None):
    """폴더 훑기 → 새/바뀐 사진 분석(촬영 시각·배경) → 새 사진 행사 묶기 →
    장소(GPS) → [엔진이 있으면] 얼굴 찾기·인물 묶기. 분석 워커가 부른다.

    progress(단계 키, 끝난 수, 전체 수). cancelled() → True면 그 단계에서 그때까지
    한 것만 저장하고 멈춘다(다음에 이어서). face_engine_factory는 FaceEngine을
    만드는 함수 — None이면 인물 단계는 건너뛴다.
    반환: {"analyzed", "grouped", "gps", "faces", "persons_assigned", "cancelled"}"""
    result = {"analyzed": 0, "grouped": 0, "gps": 0, "faces": 0, "persons_assigned": 0, "cancelled": False}

    def report(stage, done, total):
        if progress:
            progress(stage, done, total)

    def stop():
        if cancelled and cancelled():
            result["cancelled"] = True
            return True
        return False

    store = AlbumStore(library_dir)
    report(STAGE_SCAN, 0, 0)
    store.sync_files(scan_library(library_dir))

    # 1) 촬영 시각 + 배경 특징값
    pending = store.pending_analysis()
    rows = []
    for i, (rel, mtime) in enumerate(pending):
        if stop():
            store.save_analysis(rows)
            return result
        taken, feat = analyze_file(to_abs(library_dir, rel), mtime)
        rows.append((rel, taken, feat))
        result["analyzed"] += 1
        if len(rows) >= batch:
            store.save_analysis(rows)
            rows = []
        report(STAGE_FEATURES, i + 1, len(pending))
    store.save_analysis(rows)
    result["grouped"] = store.assign_unassigned()

    # 2) 장소 — EXIF만 읽으므로 빠르다(v48에서 분석한 사진도 여기서 채워진다)
    from .geo_lookup import place_key
    pending = store.pending_gps()
    rows = []
    for i, rel in enumerate(pending):
        if stop():
            store.save_gps(rows)
            return result
        lat, lon = read_gps_file(to_abs(library_dir, rel))
        rows.append((rel, lat, lon, place_key(lat, lon) if lat is not None else None))
        result["gps"] += 1
        if len(rows) >= batch * 4:
            store.save_gps(rows)
            rows = []
        report(STAGE_GPS, i + 1, len(pending))
    store.save_gps(rows)

    # 3) 얼굴 — 선택 설치 엔진이 있을 때만
    if face_engine_factory is not None:
        pending = store.pending_faces()
        if pending:
            engine = face_engine_factory()
            for i, rel in enumerate(pending):
                if stop():
                    break
                found = engine.analyze(to_abs(library_dir, rel))
                store.save_faces(rel, found)
                result["faces"] += len(found)
                report(STAGE_FACES, i + 1, len(pending))
        result["persons_assigned"] = store.assign_faces()
    return result


def now():
    return int(time.time())

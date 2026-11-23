# -*- coding: utf-8 -*-
"""
FolderKit — 중복 파일 찾기 핵심 로직 [v38 고속 엔진]

기존 v37 엔진의 3단계(크기 → 앞 64KB 해시 → 전체 해시)를 유지하되,
TB급 동영상 컬렉션에서 병목이던 "전체 해시" 단계를 대폭 줄이도록 재설계했다.

■ 새 파이프라인 (위에서 아래로, 통과한 것만 다음 단계로)
  0단계  os.scandir 한 번으로 (크기 · mtime · dev/ino) 동시 수집   — 추가 I/O 0
  1단계  파일 크기 그룹화                                          — 추가 I/O 0
  2단계  하드링크/동일 실체 파일 접기 (dev, ino)                   — 추가 I/O 0
  3단계  앞 64KB 해시                                              — 파일당 64KB
  4단계  뒤 64KB 해시  ★신규                                       — 파일당 64KB
  5단계  샘플 해시(파일 전체에 흩뿌린 16 × 1MB) ★신규             — 파일당 16MB
  6단계  전체 해시 (엄격 모드에서만)                               — 파일당 전체

  빠른 모드(기본)는 5단계에서 확정한다. 4GB 동영상 기준으로 읽는 양이
  4096MB → 16MB로 약 250배 줄어든다.

■ 그 밖의 개선
  · 장치(dev)별 동시 실행 수 제한 — HDD는 1~2, SSD/NVMe/NAS는 4~8로 개별 설정
  · hashlib은 GIL을 놓기 때문에 스레드만으로 실제 병렬 해싱이 된다
  · (경로, 크기, mtime) 키의 SQLite 해시 캐시 — 재스캔은 거의 즉시 끝남
  · readinto() + 재사용 버퍼로 TB급에서의 GC 부담 제거
  · 진행률을 "파일 수"가 아니라 "바이트"로 계산 (4GB와 4KB를 같게 세지 않음)
  · progress 시그널을 0.2초 단위로 스로틀 — UI 스레드 폭주 방지

공개 API(DuplicateGroup / DuplicateScanThread 시그널)는 v37과 동일하므로
main_window.py 수정 없이 그대로 교체할 수 있다.
"""
import os
import sys
import time
import errno
import sqlite3
import hashlib
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QThread, Signal, Qt

from .dup_folder_analysis import folder_stats as folder_stats_of, analyze as analyze_folders
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtGui import QPixmap, QImage

try:
    from PIL import Image
    from .image_io import thumbnail_oriented
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from .styles import is_excluded, is_hidden_or_system

# ─────────────────────────────────────────────────────────────────────
# 튜닝 상수
# ─────────────────────────────────────────────────────────────────────
HEAD_BYTES = 64 * 1024          # 3단계: 앞부분
TAIL_BYTES = 64 * 1024          # 4단계: 뒷부분
SAMPLE_CHUNKS = 16              # 5단계: 샘플 개수
SAMPLE_CHUNK_BYTES = 1024 * 1024
SAMPLE_BUDGET = SAMPLE_CHUNKS * SAMPLE_CHUNK_BYTES   # 16MB
READ_BLOCK = 4 * 1024 * 1024    # 전체 해시 시 순차 읽기 블록

# 이 크기 이하는 샘플링 이득보다 오버헤드가 커서 곧바로 전체 해시로 확정한다.
SMALL_FILE_LIMIT = 4 * SAMPLE_BUDGET     # 64MB

# 엄격 모드에서는 어차피 전체를 읽으므로 샘플 단계가 순수 낭비가 될 수 있다.
# 파일이 충분히 커서 샘플 비용(16MB)이 무시할 수준일 때만 예비 필터로 쓴다.
STRICT_SAMPLE_MIN = 16 * SAMPLE_BUDGET   # 256MB — 샘플 오버헤드 ≤ 6%

# 장치 종류별 권장 동시 읽기 수. HDD에서 스레드를 늘리면 탐색(seek)이
# 뒤엉켜 오히려 느려지므로 반드시 낮게 잡는다.
WORKERS_HDD = 2
WORKERS_SSD = 6
WORKERS_NET = 8
DEFAULT_WORKERS = WORKERS_SSD

# 비암호학적 초고속 해시가 있으면 쓰고, 없으면 하드웨어 가속되는 sha1로 대체.
try:
    import xxhash
    def _new_hasher():
        return xxhash.xxh3_128()
    HASH_NAME = "xxh3_128"
except ImportError:
    def _new_hasher():
        return hashlib.sha1()      # 대부분의 최신 CPU에서 SHA-NI로 md5보다 빠름
    HASH_NAME = "sha1"


# ─────────────────────────────────────────────────────────────────────
# 해시 캐시 (SQLite)
# ─────────────────────────────────────────────────────────────────────
class HashCache:
    """(경로, 크기, mtime, 단계)를 키로 해시값을 보관한다.

    파일이 그대로면 두 번째 스캔부터는 디스크를 전혀 읽지 않는다.
    스레드마다 별도 커넥션을 쓰고, 쓰기는 메모리에 모았다가 끝에 한 번에 커밋한다.
    """

    FLUSH_EVERY = 500          # [v49.5] 이만큼 모이거나
    FLUSH_SECONDS = 30.0       # 이만큼 지나면 중간 저장(도중에 꺼도 다음엔 이어서)

    def __init__(self, db_path, enabled=True):
        self.enabled = enabled
        self.db_path = db_path
        self._pending = {}
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._local = threading.local()
        self._ready = False
        if not enabled:
            return
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            con = self._conn()
            con.execute(
                "CREATE TABLE IF NOT EXISTS h ("
                " path TEXT, size INTEGER, mtime INTEGER, kind TEXT, algo TEXT,"
                " digest TEXT, PRIMARY KEY (path, kind, algo))")
            con.execute("PRAGMA journal_mode=WAL")
            con.commit()
            self._ready = True
        except (sqlite3.Error, OSError):
            self.enabled = False

    def _conn(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(self.db_path, timeout=30)
            self._local.con = con
        return con

    def get(self, path, size, mtime, kind):
        if not self.enabled or not self._ready:
            return None
        try:
            row = self._conn().execute(
                "SELECT size, mtime, digest FROM h WHERE path=? AND kind=? AND algo=?",
                (path, kind, HASH_NAME)).fetchone()
        except sqlite3.Error:
            return None
        if row and row[0] == size and row[1] == mtime:
            return row[2]
        return None

    def put(self, path, size, mtime, kind, digest):
        if not self.enabled or not self._ready:
            return
        with self._lock:
            self._pending[(path, kind)] = (path, size, mtime, kind, HASH_NAME, digest)
            due = (len(self._pending) >= self.FLUSH_EVERY
                   or time.monotonic() - self._last_flush >= self.FLUSH_SECONDS)
        # [v49.5] 예전에는 스캔이 끝날 때 한 번만 저장해서, 도중에 끄면 그때까지
        # 읽은 것이 모두 사라지고 다시 실행해도 처음부터였다.
        if due and self._flush_lock.acquire(blocking=False):
            try:
                self._write_pending()
            finally:
                self._flush_lock.release()

    def flush(self):
        if not self.enabled or not self._ready:
            return
        with self._flush_lock:
            self._write_pending()

    def _write_pending(self):
        with self._lock:
            rows = list(self._pending.values())
            self._pending.clear()
            self._last_flush = time.monotonic()
        if not rows:
            return
        try:
            con = self._conn()
            con.executemany("INSERT OR REPLACE INTO h VALUES (?,?,?,?,?,?)", rows)
            con.commit()
        except sqlite3.Error:
            pass


def default_cache_path():
    base = os.environ.get("LOCALAPPDATA") or (
        os.path.expanduser("~/Library/Caches") if sys.platform == "darwin"     # [v51] 맥
        else os.path.expanduser("~/.cache"))
    return os.path.join(base, "FolderKit", "dupfind_hash.db")


# ─────────────────────────────────────────────────────────────────────
# 파일 읽기 · 해시 계산
# ─────────────────────────────────────────────────────────────────────
def _open_sequential(path):
    """전체 읽기용. Windows에서는 순차 접근 힌트를 줘 캐시 효율을 높인다."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_SEQUENTIAL", 0)
    return os.fdopen(os.open(path, flags), "rb", buffering=0)


def hash_head(path, size):
    h = _new_hasher()
    with open(path, "rb", buffering=0) as f:
        h.update(f.read(min(HEAD_BYTES, size)))
    return h.hexdigest()


def hash_tail(path, size):
    """끝부분 64KB. 앞부분(컨테이너 헤더)이 같은 동영상 재인코딩본을
    걸러내는 데 특히 효과가 좋으면서 비용은 seek 한 번뿐이다."""
    n = min(TAIL_BYTES, size)
    h = _new_hasher()
    with open(path, "rb", buffering=0) as f:
        if size > n:
            f.seek(size - n)
        h.update(f.read(n))
    return h.hexdigest()


def hash_sample(path, size):
    """파일 전체에 균등하게 흩뿌린 16개 지점에서 1MB씩만 읽어 해시한다.
    크기·앞·뒤가 모두 같은 상태에서 이 16MB까지 일치하면서 내용이 다를
    확률은 사람이 만든 파일에서는 사실상 0이다."""
    if size <= SAMPLE_BUDGET:
        return hash_full(path, size)
    h = _new_hasher()
    h.update(str(size).encode())          # 크기를 해시에 섞어 넣는다
    step = (size - SAMPLE_CHUNK_BYTES) / (SAMPLE_CHUNKS - 1)
    buf = bytearray(SAMPLE_CHUNK_BYTES)
    view = memoryview(buf)
    with open(path, "rb", buffering=0) as f:
        for i in range(SAMPLE_CHUNKS):
            f.seek(int(i * step))
            got = f.readinto(buf)
            h.update(view[:got])
    return h.hexdigest()


class _Stopped(Exception):
    """[v49.5] 큰 파일을 읽는 도중 취소된 경우."""


def hash_full(path, size=None, on_bytes=None):
    """on_bytes(n): [v49.5] 블록(4MB)을 읽을 때마다 불린다 — 큰 파일을 읽는 동안에도
    진행률이 움직이고, False를 돌려주면(취소) 그 자리에서 멈춘다."""
    h = _new_hasher()
    buf = bytearray(READ_BLOCK)
    view = memoryview(buf)
    with _open_sequential(path) as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            h.update(view[:n])
            if on_bytes is not None and on_bytes(n) is False:
                raise _Stopped()
    return h.hexdigest()


_STAGE_FUNCS = {
    "head": (hash_head, lambda sz: min(HEAD_BYTES, sz)),
    "tail": (hash_tail, lambda sz: min(TAIL_BYTES, sz)),
    "samp": (hash_sample, lambda sz: min(SAMPLE_BUDGET, sz)),
    "full": (hash_full, lambda sz: sz),
}


# ─────────────────────────────────────────────────────────────────────
# 파일 정보
# ─────────────────────────────────────────────────────────────────────
class FileInfo:
    __slots__ = ("path", "size", "mtime", "dev", "ino")

    def __init__(self, path, size, mtime, dev, ino):
        self.path = path
        self.size = size
        self.mtime = mtime
        self.dev = dev
        self.ino = ino


def verify_group(paths, cancel_cb=None):
    """★ 삭제 직전 안전장치.

    빠른 모드는 '샘플이 모두 같으면 같다'고 보는 휴리스틱이라, 크기·앞·뒤가
    모두 같고 중간의 아주 작은 구간만 다른 파일(예: 중간에 박힌 메타데이터
    블록만 다른 동영상)을 놓칠 수 있다.

    그래서 스캔은 빠르게 하되, 사용자가 실제로 지우려고 고른 그룹에 대해서만
    전체 해시로 다시 확인한다. 지우려는 파일은 몇 개 안 되므로 비용이 작고,
    되돌릴 수 없는 작업의 안전성은 엄격 모드와 같아진다.

    반환: list[list[str]] — 내용이 진짜 같은 것끼리 다시 묶은 결과.
          원본이 그대로 1개 그룹으로 나오면 검증 통과.
    """
    by_full = defaultdict(list)
    for p in paths:
        if cancel_cb and cancel_cb():
            return None
        try:
            by_full[hash_full(p)].append(p)
        except OSError:
            continue
    return list(by_full.values())


class DuplicateGroup:
    """실제 내용이 동일한 것으로 확인된 파일 경로들의 묶음."""

    def __init__(self, file_hash, size, paths, mtimes=None):
        self.file_hash = file_hash
        self.size = size
        self.paths = list(paths)
        # [v51.1] 경로 → 수정 시각(ns). "최신 파일만 남기고 체크"에 쓴다(스캔 때 이미 읽은 값)
        self.mtimes = dict(mtimes) if mtimes else {}

    @property
    def wasted_bytes(self):
        return self.size * (len(self.paths) - 1)


# ─────────────────────────────────────────────────────────────────────
# 스캔 스레드
# ─────────────────────────────────────────────────────────────────────
class DuplicateScanThread(QThread):
    """v37과 동일한 시그널 규약. progress의 (done, total)은 파일 수가 아니라
    바이트 수이므로 진행률 바가 실제 남은 작업량을 반영한다."""

    # ★ Signal(int, ...)은 C의 32비트 int로 매핑되어 2GB가 넘는 바이트 수에서
    #   OverflowError가 난다(TB급 스캔에서 반드시 터진다). qlonglong으로 지정한다.
    progress = Signal('qlonglong', 'qlonglong', str)
    finished_scan = Signal(list)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, roots=None, strict=False, workers=None,
                 use_cache=True, include_empty=False, device_profile=None,
                 verify_groups=None, folder_stats=None):
        """
        strict          True면 6단계(전체 해시)까지 수행. 기본 False(샘플로 확정).
        workers         장치당 동시 읽기 스레드 수. None이면 자동.
        use_cache       SQLite 해시 캐시 사용 여부.
        include_empty   0바이트 파일도 중복으로 볼지 여부.
        device_profile  {dev_id: "hdd"|"ssd"|"net"} 형태의 수동 지정(선택).
        verify_groups   [v49] list[list[str]] — 이미 빠른 스캔으로 찾아 둔
                        후보 그룹들. 이 값을 넘기면 roots(폴더)는 무시하고
                        폴더를 처음부터 다시 훑지 않는다 — 이 목록에 있는
                        파일들만 곧바로 전체 해시로 재검증해, 실제로 내용이
                        같은 것끼리만 다시 묶는다(그룹에서 떨어져 나온
                        파일은 결과에서 사라진다).
        folder_stats    [v50] 정밀 재검사 때 빠른 스캔이 세어 둔 폴더별 파일 수·용량
                        (폴더를 다시 걷지 않으므로 넘겨받아 폴더 중복 분석에 쓴다).
        """
        super().__init__()
        self.roots = list(roots) if isinstance(roots, (list, tuple)) else ([roots] if roots else [])
        self.strict = strict
        self.workers = workers
        self.use_cache = use_cache
        self.include_empty = include_empty
        self.device_profile = device_profile or {}
        self.verify_groups = verify_groups

        self._cancel = False
        self._resume_event = threading.Event()
        self._resume_event.set()   # 시작 시에는 일시정지 상태가 아님
        self._cache = None
        self._sems = {}
        self._done_bytes = 0
        self._total_bytes = 0
        # [v51.2] 전체 작업량을 처음에 한 번 어림해 두고(단계별 계획), 단계가 끝날 때마다
        # 탈락한 파일 몫만 빼서 줄여 간다 → 진행률이 뒤로 가지 않는다.
        self._planned = False
        self._left = {}
        self._last_emit = 0.0
        self._emit_lock = threading.Lock()
        self.stats = {}
        # [v50] 폴더 중복 분석 — 끝나면 채워진다(UI는 finished_scan 뒤에 읽는다)
        self.folder_stats = folder_stats
        self.folder_report = []

    def cancel(self):
        self._cancel = True
        self._resume_event.set()   # 일시정지 중 취소되면 즉시 깨어나 종료할 수 있게

    def pause(self):
        """[v38] Esc 키 처리용. 진행 중인 파일 읽기가 끝나는 다음 체크포인트에서
        멈춘다(파일 하나를 읽는 도중에 강제로 끊지는 않는다)."""
        self._resume_event.clear()

    def resume(self):
        self._resume_event.set()

    def _checkpoint(self):
        """취소됐으면 True. 일시정지 상태면 resume()이 호출될 때까지 여기서 대기한다."""
        if self._cancel:
            return True
        self._resume_event.wait()
        return self._cancel

    # ── 진행률 ────────────────────────────────────────────────────
    def _tick(self, nbytes, path):
        with self._emit_lock:
            self._done_bytes += nbytes
            now = time.monotonic()
            if now - self._last_emit < 0.2:
                return
            self._last_emit = now
            done, total = self._done_bytes, self._total_bytes
            # [v51.2] 잠금 안에서 내보낸다 — 여러 읽기 스레드가 동시에 알리면 순서가
            # 뒤바뀌어 막대가 잠깐 뒤로 가는 일이 있었다(신호는 줄만 세우므로 가볍다)
            self.progress.emit(done, max(total, 1), path)

    # ── 장치별 동시 실행 제한 ─────────────────────────────────────
    def _sem_for(self, dev):
        sem = self._sems.get(dev)
        if sem is None:
            if self.workers:
                n = self.workers
            else:
                kind = self.device_profile.get(dev, "ssd")
                n = {"hdd": WORKERS_HDD, "ssd": WORKERS_SSD,
                     "net": WORKERS_NET}.get(kind, DEFAULT_WORKERS)
            sem = threading.Semaphore(n)
            self._sems[dev] = sem
        return sem

    # ── 0단계: 수집 ───────────────────────────────────────────────
    def _collect(self):
        """os.scandir로 걷는다. DirEntry가 디렉터리 항목에서 읽어 캐시해 둔
        stat을 그대로 쓰므로, os.walk + os.path.getsize처럼 파일마다 stat을
        다시 호출하지 않는다(대량 파일에서 체감 차이가 크다)."""
        seen_paths = set()
        out = []
        stack = [os.path.normpath(r) for r in self.roots]
        while stack:
            if self._cancel:
                return None
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    if self._checkpoint():
                        return None
                    try:
                        if e.is_dir(follow_symlinks=False):
                            # [v48] 탐색기가 기본적으로 숨기는 숨김/시스템 폴더는
                            # 중복 검사 대상에서도 제외한다.
                            if not is_excluded(e.name) and not is_hidden_or_system(e):
                                stack.append(e.path)
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                        if is_excluded(e.name) or is_hidden_or_system(e):
                            continue
                        p = os.path.normpath(e.path)
                        if p in seen_paths:
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    seen_paths.add(p)
                    out.append(FileInfo(p, st.st_size, st.st_mtime_ns,
                                        st.st_dev, st.st_ino))
        return out

    # ── 3~6단계 공통: 그룹을 한 단계 더 쪼개기 ────────────────────
    # ── [v51.2] 진행률이 되돌아가지 않게: 남은 작업량 계획 ─────────
    # 예전엔 단계(head → tail → full/samp → full)마다 "지금까지 한 양 + 이번 단계 양"으로
    # 전체량을 새로 잡았다. 그래서 단계 끝마다 99% 가까이 찼다가 다음 단계가 시작되면
    # 전체량이 늘어 65%처럼 뚝 떨어졌다. 이제는 후보 파일마다 "남은 단계"를 들고 있다가
    # 단계가 끝나면 그 단계를 지우고, 탈락한 파일은 통째로 빼서 전체량을 다시 센다.
    def _stage_plan(self, size):
        """이 크기의 파일이 거칠 단계들(run()의 순서와 같아야 한다)."""
        cut = STRICT_SAMPLE_MIN if self.strict else SMALL_FILE_LIMIT
        if size <= cut:
            return ["head", "tail", "full"]
        return ["head", "tail", "samp", "full"] if self.strict else ["head", "tail", "samp"]

    def _left_cost(self):
        return sum(_STAGE_FUNCS[st][1](size) for size, stages in self._left.values() for st in stages)

    def _plan_total(self, groups):
        """스캔 시작 때 한 번 — 지금 후보가 모두 끝까지 간다고 보고 전체량을 잡는다(최대치)."""
        self._left = {fi.path: (fi.size, self._stage_plan(fi.size)) for g in groups for fi in g}
        self._planned = True
        with self._emit_lock:
            self._total_bytes = self._done_bytes + self._left_cost()

    def _shrink_total(self, tasks, survivors, stage):
        """단계가 끝나면: 이 단계를 지우고, 탈락한 파일은 남은 단계까지 통째로 뺀다.
        전체량은 줄기만 하고, 진행률(한 양 ÷ 전체량)은 오르기만 한다."""
        alive = {fi.path for g in survivors for fi in g}
        for fi in tasks:
            ent = self._left.get(fi.path)
            if ent is None:
                continue
            if fi.path not in alive:
                del self._left[fi.path]
            elif stage in ent[1]:
                ent[1].remove(stage)
        with self._emit_lock:
            new_total = self._done_bytes + self._left_cost()
            self._total_bytes = min(self._total_bytes, new_total)

    def _refine(self, groups, stage, pool):
        """groups: list[list[FileInfo]] → 같은 단계 해시끼리 다시 묶어 반환.
        원소가 1개로 줄어든 그룹은 그 자리에서 탈락시킨다."""
        func, cost = _STAGE_FUNCS[stage]
        tasks = [fi for g in groups for fi in g]
        if not tasks:
            return []

        if not self._planned:
            # 정밀 재검사처럼 단계가 하나뿐인 경우 — 예전처럼 이 단계 양만큼
            self._total_bytes = self._done_bytes + sum(cost(fi.size) for fi in tasks)
        results = {}

        def work(fi):
            if self._checkpoint():
                return
            cached = self._cache.get(fi.path, fi.size, fi.mtime, stage) if self._cache else None
            if cached is not None:
                results[fi.path] = cached
                # 읽지는 않았지만 계획한 몫은 끝난 것으로 센다(전체량에 들어 있으므로) —
                # [v51.2] 예전엔 0으로 세서, 캐시가 많으면 막대가 덜 찬 채로 다음 단계로 넘어갔다
                self._tick(cost(fi.size) if self._planned else 0, fi.path)
                return
            sem = self._sem_for(fi.dev)
            streamed = stage == "full"
            with sem:
                if self._checkpoint():
                    return
                try:
                    if streamed:
                        # [v49.5] 큰 파일도 4MB마다 진행률을 올리고, 읽는 도중에도
                        # Esc(일시정지)·취소를 받는다.
                        d = func(fi.path, fi.size,
                                 on_bytes=lambda n: (self._tick(n, fi.path), not self._checkpoint())[1])
                    else:
                        d = func(fi.path, fi.size)
                except _Stopped:
                    return
                except OSError as ex:
                    if ex.errno in (errno.EACCES, errno.ENOENT, errno.EBUSY):
                        return
                    return
                except Exception:
                    return
            results[fi.path] = d
            if self._cache:
                self._cache.put(fi.path, fi.size, fi.mtime, stage, d)
            self._tick(0 if streamed else cost(fi.size), fi.path)

        # 같은 장치 안에서는 경로 순으로 읽어 HDD 헤드 이동을 줄인다.
        tasks.sort(key=lambda fi: (fi.dev, fi.path))
        list(pool.map(work, tasks))
        if self._cancel:
            return None

        out = []
        for g in groups:
            sub = defaultdict(list)
            for fi in g:
                d = results.get(fi.path)
                if d is not None:
                    sub[d].append(fi)
            for members in sub.values():
                if len(members) > 1:
                    out.append(members)
        self.stats[stage] = self.stats.get(stage, 0) + sum(len(g) for g in out)
        if self._planned:
            self._shrink_total(tasks, out, stage)
        return out

    # ── 본체 ──────────────────────────────────────────────────────
    def run(self):
        try:
            t0 = time.monotonic()
            if self.use_cache:
                self._cache = HashCache(default_cache_path())

            alias = {}

            if self.verify_groups is not None:
                # [v49] 정밀 재검사 전용 경로 — 폴더를 걷지 않고, 이미 찾아 둔
                # 후보 그룹의 파일들만 곧바로 전체 해시(stage "full")로
                # 재확인한다. verify_group()과 목적은 같지만(내용이 진짜
                # 같은 것끼리 다시 묶기), 여기서는 캐시·장치별 동시 실행
                # 제한·진행률·일시정지/취소까지 스캔 스레드와 똑같이 누린다.
                groups = []
                for paths in self.verify_groups:
                    fis = []
                    for p in paths:
                        if self._checkpoint():
                            self.cancelled.emit()
                            return
                        try:
                            st = os.stat(p)
                        except OSError:
                            continue  # 그 사이 지워졌거나 이동한 파일 — 조용히 제외
                        fis.append(FileInfo(p, st.st_size, st.st_mtime_ns,
                                             st.st_dev, st.st_ino))
                    if len(fis) > 1:
                        groups.append(fis)
                self.stats["scanned"] = sum(len(g) for g in groups)

                pool_size = max(WORKERS_NET, (self.workers or DEFAULT_WORKERS) * 2)
                with ThreadPoolExecutor(max_workers=pool_size) as pool:
                    groups = self._refine(groups, "full", pool)
                    if groups is None:
                        self.cancelled.emit()
                        return
            else:
                files = self._collect()
                if files is None:
                    self.cancelled.emit()
                    return
                self.stats["scanned"] = len(files)
                self.folder_stats = folder_stats_of(files, self.roots, self.include_empty)

                # 1단계 — 크기
                by_size = defaultdict(list)
                for fi in files:
                    if fi.size == 0 and not self.include_empty:
                        continue
                    by_size[fi.size].append(fi)
                groups = [g for g in by_size.values() if len(g) > 1]
                self.stats["size"] = sum(len(g) for g in groups)

                # 2단계 — 하드링크 접기: 같은 (dev, ino)는 물리적으로 같은 파일이라
                #        읽을 필요가 없다. 대표 하나만 남기고 나머지는 뒤에서 복원.
                folded = []
                for g in groups:
                    reps, seen_ino = [], {}
                    for fi in g:
                        key = (fi.dev, fi.ino)
                        if fi.ino and key in seen_ino:
                            alias.setdefault(seen_ino[key], []).append(fi.path)
                        else:
                            if fi.ino:
                                seen_ino[key] = fi.path
                            reps.append(fi)
                    if len(reps) > 1:
                        folded.append(reps)
                    elif reps and alias.get(reps[0].path):
                        folded.append(reps)      # 하드링크만 있는 그룹도 결과에 남긴다
                groups = folded

                pool_size = max(WORKERS_NET, (self.workers or DEFAULT_WORKERS) * 2)
                self._plan_total(groups)       # [v51.2] 전체량을 처음에 한 번 어림
                with ThreadPoolExecutor(max_workers=pool_size) as pool:
                    for stage in ("head", "tail"):
                        groups = self._refine(groups, stage, pool)
                        if groups is None:
                            self.cancelled.emit()
                            return
                        if not groups:
                            break

                    if groups:
                        # 샘플 단계를 거칠 그룹과, 곧바로 전체 해시로 확정할 그룹을 나눈다.
                        #  · 빠른 모드: 64MB 초과면 샘플로 확정
                        #  · 엄격 모드: 256MB 초과일 때만 샘플을 예비 필터로 쓰고,
                        #    그보다 작으면 샘플을 건너뛰어 중복 읽기를 없앤다.
                        cut = STRICT_SAMPLE_MIN if self.strict else SMALL_FILE_LIMIT
                        big = [g for g in groups if g[0].size > cut]
                        small = [g for g in groups if g[0].size <= cut]

                        confirmed = []
                        if small:
                            r = self._refine(small, "full", pool)
                            if r is None:
                                self.cancelled.emit()
                                return
                            confirmed += r
                        if big:
                            r = self._refine(big, "samp", pool)
                            if r is None:
                                self.cancelled.emit()
                                return
                            if self.strict and r:
                                r = self._refine(r, "full", pool)
                                if r is None:
                                    self.cancelled.emit()
                                    return
                            confirmed += r
                        groups = confirmed

            if self._cache:
                self._cache.flush()

            out = []
            for g in groups or []:
                paths = []
                mtimes = {}
                for fi in g:
                    paths.append(fi.path)
                    mtimes[fi.path] = fi.mtime
                    for a in alias.get(fi.path, []):      # 하드링크 = 같은 파일 → 같은 시각
                        paths.append(a)
                        mtimes[a] = fi.mtime
                if len(paths) > 1:
                    out.append(DuplicateGroup(HASH_NAME, g[0].size, paths, mtimes))

            # [v50] 통째로 복사된 폴더 찾기(15만 그룹 몇 초 — 스레드 안에서)
            if self.folder_stats:
                try:
                    self.folder_report = analyze_folders(out, self.folder_stats,
                                                         cancel_cb=lambda: self._cancel)
                except Exception:
                    self.folder_report = []   # 분석이 실패해도 중복 결과는 그대로 보여 준다

            self.stats["elapsed"] = round(time.monotonic() - t0, 1)
            self.progress.emit(max(self._total_bytes, 1), max(self._total_bytes, 1), "")
            self.finished_scan.emit(out)

        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────
# 미리보기 팝오버 (v37과 동일)
# ─────────────────────────────────────────────────────────────────────
def _load_thumb_pixmap(path, size):
    if not _HAS_PIL:
        return None
    try:
        img = thumbnail_oriented(path, size)   # [v47.2] 세로 사진은 세워서
        canvas = Image.new("RGBA", size, (244, 245, 247, 255))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        canvas.paste(img.convert("RGBA"), (x, y))
        qimg = QImage(canvas.tobytes(), canvas.width, canvas.height,
                      canvas.width * 4, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


class DuplicatePreviewPopover(QWidget):
    MAX_VISIBLE = 5
    THUMB = (140, 140)

    def __init__(self, image_paths, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for p in image_paths:
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(3)

            pic = QLabel()
            pic.setFixedSize(*self.THUMB)
            pic.setAlignment(Qt.AlignCenter)
            pic.setStyleSheet(
                "background-color:#f4f5f7;border:1px solid #d5d8dd;border-radius:4px;")
            pm = _load_thumb_pixmap(p, self.THUMB)
            if pm is not None:
                pic.setPixmap(pm)
            cl.addWidget(pic)

            name = QLabel()
            name.setFixedWidth(self.THUMB[0])
            name.setAlignment(Qt.AlignCenter)
            name.setStyleSheet("font-size:11px;color:#333333;")
            name.setText(name.fontMetrics().elidedText(
                os.path.basename(p), Qt.ElideMiddle, self.THUMB[0]))
            cl.addWidget(name)

            row.addWidget(cell)
        scroll.setWidget(inner)

        visible = max(1, min(len(image_paths), self.MAX_VISIBLE))
        cell_w = self.THUMB[0] + 8
        scroll_w = visible * cell_w
        scroll_h = self.THUMB[1] + 28
        scroll.setFixedSize(scroll_w, scroll_h)
        outer.addWidget(scroll)

        self.setStyleSheet(
            "background-color:#ffffff;border:1px solid #c4c9d0;border-radius:8px;")
        self.setFixedSize(scroll_w + 20, scroll_h + 20)

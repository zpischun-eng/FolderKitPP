# -*- coding: utf-8 -*-
"""
FolderKit — 동기화 핵심 로직 (GUI와 분리 → 테스트 가능)
스캔(scan) → 상태 분류(classify) → 액션 결정(decide/plan_actions) → 실행(SyncThread)
"""
import os
import time
import shutil
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QThread, Signal

from .styles import is_excluded, is_hidden_or_system
from .i18n import tr

# =============================================================================
# 2. 동기화 핵심 로직 (GUI와 분리 → 테스트 가능)
# =============================================================================
@dataclass
class FileInfo:
    rel: str
    size: int
    mtime: float


def scan(root: str, recursive: bool) -> dict:
    """루트 하위 파일을 상대경로 기준으로 수집.

    [v39] os.walk() + 파일마다 별도 os.stat() 호출 대신 os.scandir()을 쓴다.
    scandir가 돌려주는 DirEntry는 파일 시스템에 따라 stat 정보를 디렉터리를
    읽을 때 이미 함께 받아와 캐시해 둔 경우가 많아(Windows는 항상, Linux/macOS는
    대개), 파일마다 별도의 stat 시스템 콜을 다시 하지 않아도 될 때가 많다.
    폴더/파일이 아주 많은 트리에서 체감 차이가 난다. 결과(dict[rel] = FileInfo)는
    기존과 완전히 동일하다."""
    result = {}
    if not root or not os.path.isdir(root):
        return result
    if recursive:
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        # is_dir()/is_file()은 기본적으로 심볼릭 링크를 따라가 판정한다
                        # (os.path.isdir/isfile과 동일) — 기존 os.walk 기반 코드와 같은 분류.
                        if e.is_dir():
                            # os.walk도 기본(followlinks=False)으로는 심볼릭 링크
                            # 디렉터리 안으로는 내려가지 않는다 — 동일하게 처리.
                            # [v48] 탐색기가 기본적으로 숨기는 숨김/시스템 폴더
                            # ($RECYCLE.BIN, System Volume Information 등)는
                            # 동기화 대상에서도 제외한다.
                            if not is_excluded(e.name) and not is_hidden_or_system(e) \
                                    and not e.is_symlink():
                                stack.append(e.path)
                            continue
                        if not e.is_file():
                            continue
                        if is_excluded(e.name) or is_hidden_or_system(e):
                            continue
                        st = e.stat()  # 심볼릭 링크는 대상 파일을 따라가 stat — 기존 os.stat(full)과 동일
                    except OSError:
                        continue
                    rel = os.path.relpath(e.path, root)
                    result[rel] = FileInfo(rel, st.st_size, st.st_mtime)
    else:
        try:
            it = os.scandir(root)
        except OSError:
            return result
        with it:
            for e in it:
                if is_excluded(e.name) or is_hidden_or_system(e):
                    continue
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                result[e.name] = FileInfo(e.name, st.st_size, st.st_mtime)
    return result


# 상태 상수
ONLY_L   = "ONLY_L"    # 좌측에만 있음
ONLY_R   = "ONLY_R"    # 우측에만 있음
NEWER_L  = "NEWER_L"   # 좌측이 최신
NEWER_R  = "NEWER_R"   # 우측이 최신
SAME     = "SAME"      # 동일
CONFLICT = "CONFLICT"  # mtime 동일 + 크기 다름(보류)

MTIME_TOL = 2.0  # FAT/네트워크 오차 허용(초)


def classify(li: dict, ri: dict) -> list:
    """좌/우 스캔 결과를 비교해 상태 목록 생성."""
    rows = []
    keys = sorted(set(li) | set(ri))
    for k in keys:
        l = li.get(k)
        r = ri.get(k)
        if l and not r:
            rows.append((k, ONLY_L))
        elif r and not l:
            rows.append((k, ONLY_R))
        else:
            dt = l.mtime - r.mtime
            if abs(dt) <= MTIME_TOL:
                if l.size == r.size:
                    rows.append((k, SAME))
                else:
                    rows.append((k, CONFLICT))  # 드문 케이스: 보류
            elif dt > 0:
                rows.append((k, NEWER_L))
            else:
                rows.append((k, NEWER_R))
    return rows


def decide(state: str, direction: str):
    """상태 + 방향 정책 → 실제 동작 결정.
    반환: ('copy', 'L2R'|'R2L') | ('delete','L'|'R') | None(=건너뜀)
    mirror(삭제)는 apply 단계에서 별도 처리."""
    if state == SAME or state == CONFLICT:
        return None
    if direction == "both":
        if state == ONLY_L:  return ("copy", "L2R")
        if state == ONLY_R:  return ("copy", "R2L")
        if state == NEWER_L: return ("copy", "L2R")
        if state == NEWER_R: return ("copy", "R2L")
    elif direction == "l2r":
        if state in (ONLY_L, NEWER_L): return ("copy", "L2R")
        # 우측에만 있는 것은 원본(좌) 기준이라 무시(미러 시 삭제 후보)
    elif direction == "r2l":
        if state in (ONLY_R, NEWER_R): return ("copy", "R2L")
    return None


def plan_actions(rows, direction, mirror):
    """실행 계획 생성. mirror=True면 원본에 없는 파일 삭제 계획 추가."""
    actions = []
    for rel, state in rows:
        act = decide(state, direction)
        if act:
            actions.append((rel, state, act))
        elif mirror:
            # 단방향에서만 삭제 의미가 명확
            if direction == "l2r" and state == ONLY_R:
                actions.append((rel, state, ("delete", "R")))
            elif direction == "r2l" and state == ONLY_L:
                actions.append((rel, state, ("delete", "L")))
    return actions


# =============================================================================
# 3. 동기화 실행 스레드
# =============================================================================
class SyncThread(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(int, int)

    def __init__(self, lroot, rroot, actions, backup):
        super().__init__()
        self.lroot = lroot
        self.rroot = rroot
        self.actions = actions
        self.backup = backup
        self.stamp = time.strftime("%Y%m%d_%H%M%S")

    def _backup(self, path, root):
        if not self.backup or not os.path.exists(path):
            return
        rel = os.path.relpath(path, root)
        bdir = os.path.join(root, "_sync_backup", self.stamp, os.path.dirname(rel))
        os.makedirs(bdir, exist_ok=True)
        try:
            shutil.copy2(path, os.path.join(bdir, os.path.basename(rel)))
        except OSError:
            pass

    def run(self):
        total = len(self.actions)
        done = 0
        ok = 0
        for rel, state, act in self.actions:
            kind, arg = act
            try:
                if kind == "copy":
                    if arg == "L2R":
                        src = os.path.join(self.lroot, rel)
                        dst = os.path.join(self.rroot, rel)
                    else:
                        src = os.path.join(self.rroot, rel)
                        dst = os.path.join(self.lroot, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.exists(dst):
                        self._backup(dst, self.rroot if arg == "L2R" else self.lroot)
                    shutil.copy2(src, dst)
                    ok += 1
                    self.progress.emit(int((done + 1) / total * 100),
                                       tr("log.sync.copy", dir=arg, rel=rel))
                elif kind == "delete":
                    tgt = os.path.join(self.lroot if arg == "L" else self.rroot, rel)
                    self._backup(tgt, self.lroot if arg == "L" else self.rroot)
                    if os.path.exists(tgt):
                        os.remove(tgt)
                    ok += 1
                    self.progress.emit(int((done + 1) / total * 100),
                                       tr("log.sync.delete", side=arg, rel=rel))
            except OSError as e:
                self.progress.emit(int((done + 1) / total * 100),
                                   tr("log.sync.failed", rel=rel, error=e))
            done += 1
        self.finished_ok.emit(ok, total)


# =============================================================================
# 3.1 분석(스캔) 실행 스레드 — 좌·우 파일 목록 수집 + 상태 분류를 백그라운드에서 수행
# =============================================================================
class ScanThread(QThread):
    """scan()/classify()는 파일이 많으면 몇 십 초가 걸릴 수 있어 GUI 스레드에서
    직접 실행하면 앱이 응답없음 상태가 된다. 별도 스레드로 분리해 실제로 멈추지
    않게 하고, 완료/실패를 시그널로 알린다."""
    finished_scan = Signal(list)
    failed = Signal(str)

    def __init__(self, lroot, rroot, recursive):
        super().__init__()
        self.lroot = lroot
        self.rroot = rroot
        self.recursive = recursive

    def run(self):
        try:
            # [v39] 좌/우 스캔을 순차가 아니라 동시에 수행한다. 두 폴더가 서로
            # 다른 물리 드라이브(예: 로컬 디스크 ↔ 외장/네트워크 드라이브)에 있을
            # 때 실질적인 시간 단축 효과가 있다. 같은 드라이브에 있어도 각 파일의
            # I/O 자체가 매우 가벼워(scandir 기반) 손해는 거의 없다.
            with ThreadPoolExecutor(max_workers=2) as pool:
                fl = pool.submit(scan, self.lroot, self.recursive)
                fr = pool.submit(scan, self.rroot, self.recursive)
                li = fl.result()
                ri = fr.result()
            rows = classify(li, ri)
            self.finished_scan.emit(rows)
        except OSError as e:
            self.failed.emit(str(e))
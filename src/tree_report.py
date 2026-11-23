# -*- coding: utf-8 -*-
"""
FolderKit++ — 폴더 하위 구조 보기 · 구조 텍스트 저장 [v50.2]

## 왜 바꿨나
workspaces 폴더에 파일이 50만 개를 넘자 "폴더 하위 구조 보기"와 "구조 텍스트 저장"이
화면을 한참 멈춰 세웠다.
- 화면(UI) 스레드에서 폴더를 다 걸었다 → 그동안 창이 얼어붙고 작업 중 표시도 없었다.
- 항목마다 listdir + isdir + isfile + 숨김 속성 확인으로 파일 시스템을 3~4번 물었다
  (50만 개 → 200만 번). os.scandir()은 폴더를 읽을 때 종류·크기·속성을 한 번에 받아 온다.
- 50만 줄을 콘솔에 한꺼번에 넣었다.

## 새로 넣은 정보(폴더마다, 하위 폴더 포함)
- 전체 용량 · 파일 수 · 하위 폴더 수 · 가장 최근 수정일
- 맨 위 요약: 바로 아래 폴더 용량 순 · 파일이 실제로 많이 쌓인 폴더 TOP 20 ·
  확장자별 용량 TOP 15 — "20GB가 어디에 쌓였나"를 바로 찾을 수 있게.

## 옵션(내부 키)
- content: "folders"(폴더만) / "files"(파일까지)
- max_depth: 0이면 끝까지, 1 이상이면 그 깊이까지만 줄로 쓴다(용량·개수는 끝까지 합산)
"""
import os
import time

from PySide6.QtCore import QThread, Signal

from .styles import is_excluded, is_hidden_or_system

CONTENT_FOLDERS = "folders"
CONTENT_FILES = "files"

TOP_HEAVY = 20
TOP_EXT = 15


class DirNode:
    __slots__ = ("name", "path", "dirs", "files", "own_bytes", "own_files",
                 "total_bytes", "total_files", "total_dirs", "latest", "error")

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.dirs = []          # [DirNode] 이름 순
        self.files = None       # [(이름, 크기)] — 파일까지 기록할 때만
        self.own_bytes = 0      # 이 폴더에 "바로" 들어 있는 파일
        self.own_files = 0
        self.total_bytes = 0    # 하위 폴더 포함
        self.total_files = 0
        self.total_dirs = 0
        self.latest = 0.0       # 하위 포함 가장 최근 수정 시각
        self.error = False      # 읽을 수 없는 폴더(권한 등)


def _rel(path, top):
    """맨 위 폴더 기준 경로(…\\a\\b) — 긴 절대 경로 대신."""
    if path == top.path:
        return "[" + top.name + "]"
    return os.path.join(top.name, os.path.relpath(path, top.path))


class _Cancelled(Exception):
    pass


def scan_tree(root, keep_files=False, progress_cb=None, cancel_cb=None, ext_stats=None):
    """root 아래를 한 번 걸어 DirNode 트리를 만든다(탐색기와 같은 숨김·제외 규칙).
    재귀 대신 스택을 써서 아주 깊은 폴더에서도 멈추지 않는다."""
    root = os.path.normpath(root)
    top = DirNode(os.path.basename(root) or root, root)
    order = []                       # 방문 순서(나중에 아래→위로 합산)
    stack = [top]
    n_dirs = n_files = 0
    last_report = 0.0
    while stack:
        node = stack.pop()
        order.append(node)
        subdirs, files = [], []
        try:
            with os.scandir(node.path) as it:
                for e in it:
                    if is_excluded(e.name) or is_hidden_or_system(e):
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            subdirs.append(DirNode(e.name, e.path))
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            files.append((e.name, st.st_size, st.st_mtime))
                    except OSError:
                        continue
        except OSError:
            node.error = True
        subdirs.sort(key=lambda d: d.name.lower())
        node.dirs = subdirs
        node.own_files = len(files)
        own = 0
        latest = 0.0
        for name, size, mt in files:
            own += size
            if mt > latest:
                latest = mt
            if ext_stats is not None:
                ext = os.path.splitext(name)[1].lower() or "(확장자 없음)"
                s = ext_stats.get(ext)
                if s is None:
                    ext_stats[ext] = [1, size]
                else:
                    s[0] += 1
                    s[1] += size
        node.own_bytes = own
        node.latest = latest
        if keep_files:
            files.sort(key=lambda f: f[0].lower())
            node.files = [(f[0], f[1]) for f in files]
        n_dirs += 1
        n_files += len(files)
        stack.extend(reversed(subdirs))
        now = time.monotonic()
        if now - last_report > 0.2:
            last_report = now
            if cancel_cb is not None and cancel_cb():
                raise _Cancelled()
            if progress_cb is not None:
                progress_cb(n_dirs, n_files)
    # 아래에서 위로 합산(order는 부모가 자식보다 먼저 들어 있음)
    for node in reversed(order):
        tb, tf, td, lt = node.own_bytes, node.own_files, len(node.dirs), node.latest
        for d in node.dirs:
            tb += d.total_bytes
            tf += d.total_files
            td += d.total_dirs
            if d.latest > lt:
                lt = d.latest
        node.total_bytes, node.total_files, node.total_dirs, node.latest = tb, tf, td, lt
    if progress_cb is not None:
        progress_cb(n_dirs, n_files)
    return top


def iter_nodes(top):
    stack = [top]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.dirs)


def render(top, t, fmt_size, content=CONTENT_FOLDERS, max_depth=0, with_meta=True,
           ext_stats=None, max_lines=0, scanned_at=None):
    """DirNode 트리 → 문자열 줄 목록. t(key, **kw)는 번역 함수(표시 문구만 바꿈).
    max_lines > 0이면 구조 부분을 그 줄 수에서 끊고 안내 줄을 붙인다(콘솔 보기용)."""
    num = lambda n: f"{n:,}"
    day = lambda ts: time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "-"

    def meta(n):
        return t("tree.meta", size=fmt_size(n.total_bytes), files=num(n.total_files),
                 dirs=num(n.total_dirs), date=day(n.latest))

    lines = []
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(scanned_at or time.time()))
    lines.append(t("tree.header", path=top.path, when=when))
    lines.append(t("tree.total", size=fmt_size(top.total_bytes), files=num(top.total_files),
                   dirs=num(top.total_dirs)))
    opt_content = t("tree.opt.files") if content == CONTENT_FILES else t("tree.opt.folders")
    opt_depth = t("tree.opt.depth_all") if max_depth <= 0 else t("tree.opt.depth_n", n=max_depth)
    lines.append(t("tree.options", content=opt_content, depth=opt_depth))

    if with_meta:
        # 1) 바로 아래 폴더 — 용량 순
        if top.dirs:
            lines.append("")
            lines.append(t("tree.sec.children"))
            for d in sorted(top.dirs, key=lambda d: -d.total_bytes):
                pct = (d.total_bytes * 100 / top.total_bytes) if top.total_bytes else 0
                lines.append(f"  {fmt_size(d.total_bytes):>9}  {pct:5.1f}%  "
                             + t("tree.files_n", n=num(d.total_files)) + f"  [{d.name}]")
        # 2) 파일이 "바로" 많이 쌓인 폴더(조상 폴더는 늘 크므로 자기 파일 용량으로 순위)
        heavy = sorted((n for n in iter_nodes(top) if n.own_bytes > 0), key=lambda n: -n.own_bytes)[:TOP_HEAVY]
        if heavy:
            lines.append("")
            lines.append(t("tree.sec.heavy", n=len(heavy)))
            for i, n in enumerate(heavy, 1):
                lines.append(f"  {i:2}. {fmt_size(n.own_bytes):>9}  "
                             + t("tree.files_n", n=num(n.own_files)) + f"  {_rel(n.path, top)}")
        # 3) 확장자별 용량
        if ext_stats:
            lines.append("")
            lines.append(t("tree.sec.ext"))
            for ext, (cnt, size) in sorted(ext_stats.items(), key=lambda kv: -kv[1][1])[:TOP_EXT]:
                lines.append(f"  {fmt_size(size):>9}  " + t("tree.files_n", n=num(cnt)) + f"  {ext}")
        lines.append("")
        lines.append(t("tree.sec.tree"))

    head_len = len(lines)
    cut = [False]

    def add(s):
        if max_lines and len(lines) - head_len >= max_lines:
            cut[0] = True
            return False
        lines.append(s)
        return True

    add(f"[{top.name}]" + ("  " + meta(top) if with_meta else ""))

    def children(node):
        files = node.files if (content == CONTENT_FILES and node.files) else []
        items = [("d", d) for d in node.dirs] + [("f", f) for f in files]
        n = len(items)
        return ((k, o, i == n - 1) for i, (k, o) in enumerate(items))

    # 스택: [항목 반복자, 접두어, 깊이] — 재귀 없이 깊이 우선으로 쓴다
    stack = [[children(top), "", 1]]
    while stack and not cut[0]:
        it, prefix, depth = stack[-1]
        nxt = next(it, None)
        if nxt is None:
            stack.pop()
            continue
        kind, obj, last = nxt
        conn = "└─ " if last else "├─ "
        if kind == "d":
            if not add(prefix + conn + f"[{obj.name}]" + ("  " + meta(obj) if with_meta else "")
                       + ("  " + t("tree.unreadable") if obj.error else "")):
                break
            if max_depth <= 0 or depth < max_depth:
                stack.append([children(obj), prefix + ("   " if last else "│  "), depth + 1])
        else:
            name, size = obj
            if not add(prefix + conn + name + (f"  ({fmt_size(size)})" if with_meta else "")):
                break
    if cut[0]:
        lines.append(t("tree.truncated", n=num(max_lines)))
    return lines


class TreeScanThread(QThread):
    """구조 보기·저장 — 폴더 스캔부터 글자 만들기·파일 쓰기까지 화면 밖에서 한다."""
    progress = Signal(int, int)          # 지금까지 읽은 폴더 수, 파일 수
    stage = Signal(str)                  # "write" — 글자 만들기·저장 단계로 넘어감
    finished_report = Signal(object, object)   # (DirNode, 줄 목록 — 저장했으면 None)
    failed = Signal(str)                 # 빈 문자열이면 취소

    def __init__(self, root, t, fmt_size, content=CONTENT_FOLDERS, max_depth=0,
                 with_meta=True, out_path=None, max_lines=0, parent=None):
        super().__init__(parent)
        self.root = root
        self.t = t
        self.fmt_size = fmt_size
        self.content = content
        self.max_depth = max_depth
        self.with_meta = with_meta
        self.out_path = out_path
        self.max_lines = max_lines
        self.ext_stats = {}
        self.line_count = 0
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            started = time.time()
            top = scan_tree(self.root, keep_files=(self.content == CONTENT_FILES),
                            progress_cb=lambda d, f: self.progress.emit(d, f),
                            cancel_cb=lambda: self._cancel,
                            ext_stats=self.ext_stats if self.with_meta else None)
            self.stage.emit("write")
            lines = render(top, self.t, self.fmt_size, content=self.content,
                           max_depth=self.max_depth, with_meta=self.with_meta,
                           ext_stats=self.ext_stats, max_lines=self.max_lines,
                           scanned_at=started)
            self.line_count = len(lines)
            if self.out_path:
                with open(self.out_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    f.write("\n")
                lines = None
        except _Cancelled:
            self.failed.emit("")
            return
        except Exception as e:      # 예상 못 한 오류도 화면에 알려 준다
            self.failed.emit(str(e))
            return
        self.finished_report.emit(top, lines)

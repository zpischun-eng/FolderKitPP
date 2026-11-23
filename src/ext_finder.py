# -*- coding: utf-8 -*-
"""
FolderKit — 확장자로 파일 찾기 핵심 로직 (GUI와 분리 → 테스트 가능) [v44.3]

"파일 찾기" 모드의 두 번째 기능. "중복 찾기"와 폴더 등록·스캔 스레드
패턴을 그대로 따르되(같은 좌측 폴더 트리, 같은 시그널 규약), 조건이
"내용이 같은 파일"이 아니라 "확장자가 지정한 목록에 속하는 파일"이라는
점만 다르다. 재귀 스캔 자체는 sync_core.scan()과 같은 os.scandir 패턴
(제외 파일·숨김/시스템 속성 처리 포함)을 그대로 재사용한다.
"""
import os
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from .styles import is_excluded, is_hidden_or_system


@dataclass
class FileHit:
    """확장자 검색 결과 한 줄. path는 절대(정규화된) 경로."""
    path: str
    name: str
    ext: str        # 점 포함 소문자, 예: ".jpg". 확장자가 없는 파일은 "".
    size: int
    mtime: float


def normalize_ext(raw: str) -> str:
    """사용자가 어떻게 입력했든(".JPG", "jpg", " .Jpg ") 비교용 형태로
    통일한다 — 항상 소문자, 항상 앞에 점 하나. 빈 입력은 빈 문자열을
    돌려준다(호출부가 이걸 걸러서 칩으로 안 만든다)."""
    e = raw.strip().lower()
    if not e:
        return ""
    if not e.startswith("."):
        e = "." + e
    return e


def find_by_extension(roots, extensions, cancel_check=None, on_file=None):
    """여러 폴더를 재귀적으로 훑어 확장자가 일치하는 파일을 모은다.

    roots         폴더 경로 목록(list[str]).
    extensions    set[str] — normalize_ext를 거친 확장자들.
    cancel_check  ()->bool. True를 돌려주면 그 시점에서 멈춘다(대용량
                  폴더에서 취소 반응성을 위함). None이면 취소 없이 끝까지.
    on_file       파일을 하나 "찾을" 때마다 (지금까지 스캔한 총 파일 수,
                  FileHit)을 받는 콜백(진행 상황을 실시간으로 보여주기
                  위함). None이면 호출 안 함.

    반환: list[FileHit]. 같은 실제 경로가 여러 root에 걸쳐 있어도
    (한 root가 다른 root 하위 폴더인 경우 등) 한 번만 담는다."""
    hits = []
    seen_paths = set()
    scanned = 0
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        stack = [root]
        while stack:
            if cancel_check and cancel_check():
                return hits
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    if cancel_check and cancel_check():
                        return hits
                    try:
                        if e.is_dir():
                            if not is_excluded(e.name) and not is_hidden_or_system(e) \
                                    and not e.is_symlink():
                                stack.append(e.path)
                            continue
                        if not e.is_file():
                            continue
                        if is_excluded(e.name) or is_hidden_or_system(e):
                            continue
                        scanned += 1
                        _, ext = os.path.splitext(e.name)
                        ext = ext.lower()
                        if ext not in extensions:
                            continue
                        real_path = os.path.normpath(e.path)
                        if real_path in seen_paths:
                            continue
                        seen_paths.add(real_path)
                        st = e.stat()
                    except OSError:
                        continue
                    hit = FileHit(real_path, e.name, ext, st.st_size, st.st_mtime)
                    hits.append(hit)
                    if on_file:
                        on_file(scanned, hit)
    return hits


class ExtFindThread(QThread):
    """확장자로 찾기 백그라운드 스레드. duplicate_finder.DuplicateScanThread와
    같은 시그널 규약(progress/finished/cancelled/failed)을 따라서, 메인
    윈도우 쪽 진행률·취소·오류 처리 코드를 최대한 같은 모양으로 쓸 수
    있게 한다."""

    progress = Signal(int, str)     # (지금까지 스캔한 파일 수, 마지막으로 본 경로)
    finished_find = Signal(list)    # list[FileHit]
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, roots, extensions):
        super().__init__()
        self.roots = list(roots)
        self.extensions = set(extensions)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            def on_file(scanned, hit):
                self.progress.emit(scanned, hit.path)

            hits = find_by_extension(
                self.roots, self.extensions,
                cancel_check=lambda: self._cancel, on_file=on_file)
            if self._cancel:
                self.cancelled.emit()
            else:
                self.finished_find.emit(hits)
        except Exception as e:
            self.failed.emit(str(e))

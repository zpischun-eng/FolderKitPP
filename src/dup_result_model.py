# -*- coding: utf-8 -*-
"""
FolderKit++ — 중복 찾기 결과 목록의 데이터 모델 [v50]

## 왜 바꿨나
예전에는 QTreeWidget에 그룹 줄과 파일 줄을 전부 "항목 객체"로 미리 만들어 넣었다.
250GB 폴더에서 중복 39만 개(그룹 15만 개)가 나오자 항목이 54만 개가 되어
프로그램이 메모리를 5.3GB까지 썼고, 결과가 뜰 때마다 수십 초 멈췄다.

이제 화면(QTreeView)은 이 모델에게 "지금 보이는 몇 십 줄"만 그때그때 물어본다.
모델이 들고 있는 것은 그룹 목록(경로 문자열)과 체크한 경로 집합뿐이다.

## 구조(평평한 목록)
- 그룹 머리 줄(중복 N개, 굵게) 다음에 그 그룹의 파일 줄들이 이어진다
- 열: 0 파일/그룹(파일 줄은 체크박스), 1 경로, 2 크기

## 순서
절약 용량(크기 × (개수 - 1))이 큰 그룹부터 — 다 훑어볼 수 없을 만큼 많을 때
정리 효과가 큰 것부터 처리할 수 있게.
"""
import os
from bisect import bisect_right

from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex

from .i18n import tr

PATH_ROLE = Qt.UserRole          # 파일 줄: 전체 경로(예전 QTreeWidget과 같은 역할 번호)
GROUP_ROW_ROLE = Qt.UserRole + 1  # 그룹 번호(그룹 줄·파일 줄 모두)

COL_NAME, COL_PATH, COL_SIZE = 0, 1, 2


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


class DupResultModel(QAbstractItemModel):
    """그룹 머리 줄과 파일 줄을 한 줄로 늘어놓은 평평한 목록.

    처음엔 2단계 트리(QTreeView)로 만들었는데, 15만 그룹을 띄우는 데만 7~11초가
    걸렸다(트리 화면은 줄마다 펼침·높이를 미리 계산한다). 같은 데이터를 표 화면
    (QTableView, 줄 높이 고정)으로 띄우면 보이는 줄만 계산하므로 50만 줄이 0.1초,
    "첫 파일만 남기고 모두 체크"도 0.1초, 5만 개 빼기도 0.3초.
    그룹 머리 줄은 굵은 글씨 + 옅은 배경.
    줄 번호 → (그룹, 그룹 안 위치)는 그룹 시작 줄 번호 표(_starts)를 이분 탐색해 찾는다.
    """

    def __init__(self, parent=None, size_formatter=None, group_bg=None):
        super().__init__(parent)
        self._group_bg = group_bg    # 그룹 머리 줄 배경색(QColor 또는 None)
        self._groups = []            # [DuplicateGroup] — 절약 용량이 큰 순
        self._starts = []            # 그룹 i의 머리 줄 번호
        self._rows = 0
        self._checked = set()        # 체크한 파일 경로
        self._fmt = size_formatter or fmt_size
        from PySide6.QtGui import QFont
        self._bold = QFont()
        self._bold.setBold(True)

    # ------------------------------------------------------------------ 줄 번호 계산
    def _reindex(self):
        starts, row = [], 0
        for g in self._groups:
            starts.append(row)
            row += 1 + len(g.paths)
        self._starts, self._rows = starts, row

    def locate_row(self, row):
        """줄 번호 → (그룹 번호, 그룹 안 위치). 위치 -1이면 그룹 머리 줄."""
        if row < 0 or row >= self._rows:
            return -1, -1
        gi = bisect_right(self._starts, row) - 1
        return gi, row - self._starts[gi] - 1

    def group_header_row(self, gi):
        return self._starts[gi] if 0 <= gi < len(self._starts) else -1

    # ------------------------------------------------------------------ 데이터 넣기·빼기
    def set_groups(self, groups):
        self.beginResetModel()
        self._groups = sorted(groups, key=lambda g: (-g.wasted_bytes, -g.size))
        self._checked = set()
        self._reindex()
        self.endResetModel()

    def clear(self):
        self.set_groups([])

    def groups(self):
        return self._groups

    def group_count(self):
        return len(self._groups)

    def file_count(self):
        return self._rows - len(self._groups)

    def group_paths(self, gi):
        return list(self._groups[gi].paths) if 0 <= gi < len(self._groups) else []

    def remove_paths(self, removed):
        """지운·옮긴 파일을 빼고, 한 개 이하만 남은 그룹은 없앤다(남은 체크는 유지)."""
        removed = set(removed)
        if not removed:
            return
        self.beginResetModel()
        kept = []
        for g in self._groups:
            if any(p in removed for p in g.paths):
                g.paths = [p for p in g.paths if p not in removed]
            if len(g.paths) > 1:
                kept.append(g)
        self._groups = kept
        self._checked -= removed
        self._reindex()
        self.endResetModel()

    # ------------------------------------------------------------------ 체크
    def checked_paths(self):
        """화면 순서대로."""
        if not self._checked:
            return []
        return [p for g in self._groups for p in g.paths if p in self._checked]

    def is_checked(self, path):
        return path in self._checked

    def path_row(self, path):
        for gi, g in enumerate(self._groups):
            if path in g.paths:
                return self._starts[gi] + 1 + g.paths.index(path)
        return -1

    def set_checked(self, path, on=True):
        row = self.path_row(path)
        if row < 0:
            return False
        return self.setData(self.index(row, COL_NAME), Qt.Checked if on else Qt.Unchecked, Qt.CheckStateRole)

    def check_all_but_first(self):
        """[v50] 그룹마다 첫 파일만 남기고 나머지를 체크 — 15만 그룹을 손으로 고를 수 없을 때."""
        self._checked = {p for g in self._groups for p in g.paths[1:]}
        self._emit_all_checks()

    def newest_path(self, g):
        """[v51.1] 그룹에서 수정 시각이 가장 늦은 파일. 시각이 같으면 목록에서 먼저 나온 것.
        스캔 때 읽어 둔 시각이 없으면 그때 파일에서 읽고, 읽을 수 없는 파일은 가장 오래된 것으로 친다."""
        best, best_t = None, None
        for p in g.paths:
            t = g.mtimes.get(p) if getattr(g, "mtimes", None) else None
            if t is None:
                try:
                    t = os.stat(p).st_mtime_ns
                except OSError:
                    t = -1
            if best_t is None or t > best_t:
                best, best_t = p, t
        return best

    def check_all_but_newest(self):
        """[v51.1] 그룹마다 가장 최근에 수정된 파일만 남기고 나머지를 모두 체크.
        반환: 체크한 파일 수."""
        checked = set()
        for g in self._groups:
            keep = self.newest_path(g)
            checked.update(p for p in g.paths if p != keep)
        self._checked = checked
        self._emit_all_checks()
        return len(checked)

    def uncheck_all(self):
        self._checked = set()
        self._emit_all_checks()

    def _emit_all_checks(self):
        if self._rows:
            self.dataChanged.emit(self.index(0, COL_NAME), self.index(self._rows - 1, COL_NAME),
                                  [Qt.CheckStateRole])

    # ------------------------------------------------------------------ QAbstractItemModel
    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() or row < 0 or row >= self._rows or column < 0 or column > 2:
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index=QModelIndex()):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=QModelIndex()):
        return 3

    def hasChildren(self, parent=QModelIndex()):
        return not parent.isValid()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        gi, pos = self.locate_row(index.row())
        if gi < 0:
            return None
        g = self._groups[gi]
        col = index.column()
        if role == GROUP_ROW_ROLE:
            return gi
        if pos < 0:                                        # 그룹 머리 줄
            if role == Qt.DisplayRole:
                if col == COL_NAME:
                    return tr("dupfind.tree.group_label", n=len(g.paths))
                if col == COL_SIZE:
                    return self._fmt(g.size)
            elif role == Qt.FontRole:
                return self._bold
            elif role == Qt.BackgroundRole and self._group_bg is not None:
                return self._group_bg
            return None
        path = g.paths[pos]                                # 파일 줄
        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return os.path.basename(path)
            if col == COL_PATH:
                return path
            if col == COL_SIZE:
                return self._fmt(g.size)
        elif role == Qt.CheckStateRole and col == COL_NAME:
            return Qt.Checked if path in self._checked else Qt.Unchecked
        elif role == PATH_ROLE:
            return path
        elif role == Qt.ToolTipRole and col in (COL_NAME, COL_PATH):
            return path + "\n" + tr("dupfind.tree.open_tip")
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.CheckStateRole or not index.isValid() or index.column() != COL_NAME:
            return False
        gi, pos = self.locate_row(index.row())
        if pos < 0:
            return False
        path = self._groups[gi].paths[pos]
        on = value in (Qt.Checked, 2) or getattr(value, "value", None) == 2
        if on:
            self._checked.add(path)
        else:
            self._checked.discard(path)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == COL_NAME and self.locate_row(index.row())[1] >= 0:
            base |= Qt.ItemIsUserCheckable
        return base

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            labels = tr("dupfind.tree.header").split(",")
            return labels[section] if section < len(labels) else None
        return None

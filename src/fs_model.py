# -*- coding: utf-8 -*-
"""
FolderKit — 폴더 트리 모델/렌더링
- DirOnlyModel: 하위 '폴더'가 있을 때만 확장 화살표를 보여주는 QFileSystemModel
- TreeDelegate: 선택된 경로를 좌/우 강조색으로 그려주는 렌더러
"""
import os
from PySide6.QtCore import Qt, QModelIndex, Signal
from PySide6.QtWidgets import QFileSystemModel, QStyledItemDelegate, QStyle
from PySide6.QtGui import QColor, QFont

from .styles import C, is_hidden_or_system


# =============================================================================
# 3.5 폴더 전용 모델 — 하위 폴더 없으면 확장 화살표 숨김 + 헤더에 경로 표시
# =============================================================================
class DirOnlyModel(QFileSystemModel):
    """QFileSystemModel 상속.
    - hasChildren(): 실제 '하위 폴더'가 있을 때만 True → 파일만 있는 폴더는 화살표 미표시
    - headerData(): 0번 열 헤더에 선택 경로(생략형) 표시, 툴팁엔 전체 경로
    - setData(): 이름 변경(rename)이 실패하면(예: 다른 프로그램이 폴더 사용 중)
      rename_failed 시그널로 알려서 MainWindow가 안내 팝업을 띄우도록 한다."""
    rename_failed = Signal(str, str)   # (old_full_path, attempted_new_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._htext = "Name"
        self._htip = ""

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        if not self.isDir(parent):
            return False
        path = self.filePath(parent)
        try:
            with os.scandir(path) as it:
                for e in it:
                    # [v48] 하위 폴더가 숨김/시스템 속성뿐이라면(탐색기에서
                    # 안 보이는 경우) 확장 화살표도 보여주지 않는다 —
                    # 안 그러면 화살표를 눌러도 트리 자체(QFileSystemModel)가
                    # 그 폴더를 숨겨서 아무것도 안 나타나는 것처럼 보인다.
                    if e.is_dir(follow_symlinks=False) and not is_hidden_or_system(e):
                        return True   # 하위 폴더 발견 → 즉시 종료(빠름)
            return False              # 하위 폴더 없음 → 화살표 숨김
        except (PermissionError, OSError):
            return True               # 접근 불가 폴더는 화살표 유지(안전)

    def flags(self, index):
        """폴더 이름 우클릭→변경(F2 스타일 인라인 편집)을 위해 편집 가능 플래그 추가.
        QFileSystemModel.setData()가 실제 디스크 rename까지 처리해준다."""
        fl = super().flags(index)
        if index.isValid() and self.isDir(index):
            fl |= Qt.ItemIsEditable
        return fl

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole and index.isValid() and self.isDir(index):
            if value == self.fileName(index):
                return False  # 이름이 그대로면 아무 것도 하지 않음(실패로 취급 안 함)
            old_path = self.filePath(index)
            ok = super().setData(index, value, role)
            if not ok:
                # rename 실패의 대표 원인: 탐색기/다른 프로그램이 폴더를 사용 중,
                # 권한 부족, 동일 이름 존재 등. 원인을 세분화하지 않고 공통 안내.
                self.rename_failed.emit(old_path, value)
            return ok
        return super().setData(index, value, role)

    def set_header(self, text, tip):
        self._htext = text
        self._htip = tip
        self.headerDataChanged.emit(Qt.Horizontal, 0, 0)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and section == 0:
            if role == Qt.DisplayRole:
                return self._htext
            if role == Qt.ToolTipRole:
                return self._htip
        return super().headerData(section, orientation, role)


# =============================================================================
# 4. 트리 델리게이트 — OS 테마 무시, 선택 폴더 강조
# =============================================================================
class TreeDelegate(QStyledItemDelegate):
    """트리 텍스트를 직접 그려 항상 고정 색을 사용.
    선택된 동기화 폴더는 볼드 + 1pt 크게 + 좌우 다른 색."""
    def __init__(self, side, get_sel_path, parent=None):
        super().__init__(parent)
        self.side = side  # 'L' or 'R'
        self.get_sel_path = get_sel_path
        self.sel_fg = C.LEFT_SELFG if side == "L" else C.RIGHT_SELFG
        self.main   = C.LEFT_MAIN  if side == "L" else C.RIGHT_MAIN

    def paint(self, painter, option, index):
        model = index.model()
        path = model.filePath(index) if hasattr(model, "filePath") else ""
        sel_path = self.get_sel_path()
        is_sel_folder = bool(sel_path) and os.path.normpath(path) == os.path.normpath(sel_path)

        painter.save()
        # 배경
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(self.main))
            fg = QColor(C.SEL_FG)
        else:
            fg = QColor(self.sel_fg if is_sel_folder else C.TREE_FG)

        # 폰트
        font = QFont(option.font)
        if is_sel_folder:
            font.setBold(True)
            font.setPointSize(option.font.pointSize() + 1)
        painter.setFont(font)

        # 아이콘
        icon = index.data(Qt.DecorationRole)
        rect = option.rect
        text_x = rect.x() + 4
        if icon is not None:
            try:
                sz = 16
                icon.paint(painter, rect.x() + 2, rect.y() + (rect.height() - sz) // 2,
                           sz, sz)
                text_x = rect.x() + sz + 6
            except Exception:
                pass

        painter.setPen(fg)
        text = index.data(Qt.DisplayRole)
        if text is not None:
            from PySide6.QtCore import QRect
            tr = QRect(text_x, rect.y(), rect.width() - (text_x - rect.x()) - 2, rect.height())
            painter.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, str(text))
        painter.restore()


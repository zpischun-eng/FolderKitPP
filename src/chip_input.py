# -*- coding: utf-8 -*-
"""
FolderKit — 칩(태그) 입력 위젯 [v44.3]

"파일 찾기" 모드의 확장자 입력에 쓴다 — 값을 하나씩 입력해 Enter를
누르면 동그란 칩으로 쌓이고, 칩의 ✕를 누르면 그 값만 뺄 수 있다.
확장자 외의 다른 "여러 값을 칩으로 모으는" 화면에도 그대로 재사용할
수 있도록 표시 문구를 전부 생성자 인자로 받는다(내부 로직과 UI 문구를
분리한다는 프로젝트 원칙 — 이 위젯 자체는 번역 키를 모른다)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QLabel, QPushButton, QSizePolicy, QScrollArea
)

from .styles import C


class ChipInputWidget(QWidget):
    """칩 목록 + 새 값을 입력하는 한 줄짜리 입력창.

    normalize(text)->str 를 생성자에 넘기면, Enter로 확정할 때 그 함수를
    거친 값을 칩으로 쌓는다(빈 문자열을 돌려주면 무시). 이미 있는 값은
    중복으로 다시 추가하지 않는다. 칩이 추가/제거될 때마다 changed
    시그널을 내보낸다 — 호출부는 언제든 self.values()로 지금 칩 목록을
    읽을 수 있다."""

    changed = Signal()

    def __init__(self, accent_color=None, placeholder="", normalize=None, parent=None):
        super().__init__(parent)
        self._accent = accent_color or C.DUPFIND_MAIN
        self._normalize = normalize or (lambda s: s.strip())
        self._values = []   # 표시 순서 유지(집합이 아니라 리스트)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._frame = QWidget()
        self._frame.setStyleSheet(
            f"background:#ffffff;border:1px solid {C.BORDER};border-radius:5px;")
        self._flow = QHBoxLayout(self._frame)
        self._flow.setContentsMargins(6, 4, 6, 4)
        self._flow.setSpacing(6)

        self._chip_area = QWidget()
        self._chip_lay = QHBoxLayout(self._chip_area)
        self._chip_lay.setContentsMargins(0, 0, 0, 0)
        self._chip_lay.setSpacing(6)
        self._flow.addWidget(self._chip_area)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet("border:none;background:transparent;padding:2px;")
        self.edit.setMinimumWidth(90)
        self.edit.returnPressed.connect(self._on_enter)
        self._flow.addWidget(self.edit, 1)

        outer.addWidget(self._frame, 1)

    def _on_enter(self):
        raw = self.edit.text()
        value = self._normalize(raw)
        self.edit.clear()
        if not value or value in self._values:
            return
        self.add(value)

    def add(self, value):
        """코드에서 직접 칩 하나를 추가한다(프리셋 버튼 등) — 이미
        normalize를 거친 값을 넘긴다고 가정한다(_on_enter가 그렇게
        쓴다). 이미 있으면 무시하고, 없으면 칩을 만들고 changed를 낸다."""
        if value in self._values:
            return
        self._values.append(value)
        chip = self._make_chip(value)
        self._chip_lay.addWidget(chip)
        self.changed.emit()

    def _make_chip(self, value):
        chip = QWidget()
        chip.setStyleSheet(
            f"background:{self._accent};border-radius:11px;")
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(5)
        lbl = QLabel(value)
        lbl.setStyleSheet("color:#ffffff;font-weight:bold;background:transparent;")
        lay.addWidget(lbl)
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setCursor(Qt.PointingHandCursor)
        x_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#ffffff;border:none;font-size:11px;}"
            "QPushButton:hover{color:#ffe0e0;}")
        x_btn.clicked.connect(lambda: self._remove(value, chip))
        lay.addWidget(x_btn)
        return chip

    def _remove(self, value, chip_widget):
        if value in self._values:
            self._values.remove(value)
        chip_widget.setParent(None)
        chip_widget.deleteLater()
        self.changed.emit()

    def clear(self):
        while self._chip_lay.count():
            item = self._chip_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._values = []
        self.changed.emit()

    def values(self):
        """지금 칩으로 쌓여 있는 값 목록(추가한 순서 그대로)."""
        return list(self._values)

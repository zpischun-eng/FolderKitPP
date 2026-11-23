# -*- coding: utf-8 -*-
"""
FolderKit++ — Util 모드 홈 화면(도구 카드 그리드) [v01]

좌측 도구 목록만 있으면 "무엇이 있는지" 한눈에 안 들어온다. 그래서 Util
모드에 처음 들어왔을 때 보이는 첫 화면은 카드 그리드로 두었다 —
처음 쓰는 사람은 카드를 훑어보고, 익숙해진 사람은 좌측 목록에서 바로
한 번에 고른다. 같은 도구로 가는 두 개의 문이다.
"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy
)

from ..i18n import tr
from ..styles import C
from .icons import make_app_icon


CARD_W = 250
CARD_H = 96


class AppCard(QFrame):
    """도구 하나를 나타내는 카드. QPushButton으로는 제목+설명 2줄 구성을
    깔끔하게 만들기 어려워 QFrame에 클릭 처리를 직접 붙였다."""

    clicked = Signal(str)      # 내부 키(app.id)를 그대로 흘려보낸다

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app_id = app.id
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._normal = (
            f"QFrame{{background-color:#ffffff;border:1px solid {C.BORDER};"
            f"border-radius:8px;}}")
        self._hover = (
            f"QFrame{{background-color:{C.UTIL_BG};border:1px solid {C.UTIL_MAIN};"
            f"border-radius:8px;}}")
        self.setStyleSheet(self._normal)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(make_app_icon(app.icon, C.UTIL_MAIN, 32).pixmap(QSize(32, 32)))
        icon.setFixedSize(32, 32)
        icon.setStyleSheet("border:none;background:transparent;")
        lay.addWidget(icon, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        self.lbl_title = QLabel(app.title())
        self.lbl_title.setStyleSheet(
            f"color:{C.WINDOW_FG};font-weight:bold;font-size:13px;"
            "border:none;background:transparent;")
        self.lbl_desc = QLabel(app.desc())
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(
            "color:#6b7280;font-size:11px;border:none;background:transparent;")
        text.addWidget(self.lbl_title)
        text.addWidget(self.lbl_desc, 1)
        lay.addLayout(text, 1)

    def retranslate(self, app):
        self.lbl_title.setText(app.title())
        self.lbl_desc.setText(app.desc())

    def enterEvent(self, event):
        self.setStyleSheet(self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._normal)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.app_id)
        super().mouseReleaseEvent(event)


class HomeGrid(QScrollArea):
    """카테고리별로 묶은 카드 그리드."""

    appChosen = Signal(str)

    COLUMNS = 3

    def __init__(self, apps, category_label, parent=None):
        super().__init__(parent)
        self._apps = apps
        self._category_label = category_label
        self._cards = {}          # app.id -> AppCard
        self._section_labels = []  # (QLabel, category_key)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        self.setWidget(inner)
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(10)

        self.lbl_head = QLabel()
        self.lbl_head.setStyleSheet(
            f"color:{C.WINDOW_FG};font-weight:bold;font-size:15px;background:transparent;")
        self._lay.addWidget(self.lbl_head)
        self.lbl_sub = QLabel()
        self.lbl_sub.setStyleSheet("color:#6b7280;font-size:11px;background:transparent;")
        self._lay.addWidget(self.lbl_sub)

        self._build_sections()
        self._lay.addStretch()
        self.retranslate()

    def _build_sections(self):
        by_cat = {}
        for app in self._apps:
            by_cat.setdefault(app.category, []).append(app)

        for cat, apps in by_cat.items():
            lbl = QLabel()
            lbl.setStyleSheet(
                f"color:{C.UTIL_MAIN};font-weight:bold;font-size:12px;"
                "background:transparent;padding-top:6px;")
            self._lay.addWidget(lbl)
            self._section_labels.append((lbl, cat))

            holder = QWidget()
            holder.setStyleSheet("background:transparent;")
            # 카드는 고정 크기라, 이 컨테이너가 세로로 늘어나면 남는 공간이
            # 카드 위아래로 배분되어 제목과 카드 사이가 휑하게 벌어진다.
            # 높이를 내용에 딱 맞춰 고정하고, 남는 공간은 맨 아래 stretch가 갖게 한다.
            holder.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            grid = QGridLayout(holder)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(8)
            for i, app in enumerate(apps):
                card = AppCard(app)
                card.clicked.connect(self.appChosen)
                grid.addWidget(card, i // self.COLUMNS, i % self.COLUMNS)
                self._cards[app.id] = card
            grid.setColumnStretch(self.COLUMNS, 1)
            self._lay.addWidget(holder)

    def refresh_apps(self, apps):
        """[v43.10] 숨겨 둔 도구를 단축키로 꺼내면(hidden→revealed) 홈
        화면에도 바로 나타나야 한다 — 기존 섹션·카드를 전부 지우고
        새 목록으로 다시 만든다."""
        self._apps = apps
        self._cards = {}
        for lbl, _cat in self._section_labels:
            lbl.deleteLater()
        self._section_labels = []
        # lbl_head/lbl_sub 다음에 추가된 위젯(섹션 제목·카드 묶음·마지막 stretch)만 지운다
        while self._lay.count() > 2:
            item = self._lay.takeAt(2)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._build_sections()
        self._lay.addStretch()
        self.retranslate()

    # ---- 검색 필터 ----
    def apply_filter(self, text):
        """액션 바 검색창과 연동. 걸러진 카드는 숨기고, 카드가 하나도 남지
        않은 카테고리는 제목까지 함께 숨긴다."""
        needle = (text or "").strip().lower()
        visible_by_cat = {}
        for app in self._apps:
            hit = (not needle
                   or needle in app.title().lower()
                   or needle in app.desc().lower()
                   or needle in app.id.lower())
            self._cards[app.id].setVisible(hit)
            visible_by_cat[app.category] = visible_by_cat.get(app.category, False) or hit
        for lbl, cat in self._section_labels:
            lbl.setVisible(visible_by_cat.get(cat, False))

    def retranslate(self):
        self.lbl_head.setText(tr("util.home.title"))
        self.lbl_sub.setText(tr("util.home.sub"))
        for lbl, cat in self._section_labels:
            lbl.setText(self._category_label(cat))
        for app in self._apps:
            self._cards[app.id].retranslate(app)

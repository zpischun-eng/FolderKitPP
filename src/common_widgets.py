# -*- coding: utf-8 -*-
"""
FolderKit — 공용 대기 애니메이션/오버레이 위젯
WaveDotsWidget(점 출렁임 인디케이터), BusyOverlay(스캔·동기화 중 조작 차단 레이어)
"""
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PySide6.QtGui import QPainter, QColor

from .styles import C

# =============================================================================
class WaveDotsWidget(QWidget):
    """점들이 파도치듯 위아래로 출렁이는 대기 인디케이터.
    좌/우 트리 색(파랑·초록)을 번갈아 사용해 앱 전체 톤과 맞춘다."""
    DOT_COLORS = ["#5aa9f2", "#5ecf8f", "#5aa9f2", "#5ecf8f", "#5aa9f2"]

    def __init__(self, parent=None, dot_count=5, spacing=24, radius=6):
        super().__init__(parent)
        self.dot_count = dot_count
        self.spacing = spacing
        self.radius = radius
        self._phase = 0.0
        self.setFixedSize(spacing * (dot_count - 1) + radius * 4, radius * 6)
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._phase = 0.0
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.update()

    def _tick(self):
        self._phase += 0.30
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        cx0 = self.radius * 2
        cy = self.height() / 2
        for i in range(self.dot_count):
            offset = math.sin(self._phase + i * 0.85) * (self.radius * 1.4)
            cx = cx0 + i * self.spacing
            color = QColor(self.DOT_COLORS[i % len(self.DOT_COLORS)])
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, cy + offset), self.radius, self.radius)


class BusyOverlay(QWidget):
    """부모 위젯(툴바+트리+실행버튼 영역) 위에 반투명 파스텔 레이어를 올려
    마우스/키 이벤트를 가로챈다. 로그 콘솔·진행률 바·상태바는 이 오버레이
    영역 밖이라 가려지지 않고 계속 갱신되어 보인다."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        # 어두운 디밍 대신, 좌(파랑)·우(초록) 톤을 섞은 파스텔 반투명 배경
        self.setStyleSheet("background-color: rgba(219, 232, 246, 225);")
        self.setCursor(Qt.WaitCursor)
        self.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(14)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"color:{C.LEFT_SELFG}; background:transparent; "
            "font-size:16px; font-weight:700;")
        lay.addWidget(self.label)

        self.wave = WaveDotsWidget(self)
        lay.addWidget(self.wave, 0, Qt.AlignHCenter)

        self._base_text = ""

    def start(self, text, indeterminate=True):
        self._base_text = text
        self.label.setText(text)
        self.wave.start()
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.setVisible(True)
        # [v36] 뒤이어 올 작업이 이벤트 루프로 한 번도 돌아가지 않는 긴
        # 동기 코드(예: 큰 명단 파싱)일 수 있다 — 그 동안은 QTimer도 못
        # 돌아 점 애니메이션이 멈추는 건 물론, processEvents() 한 번만으로는
        # 창 시스템에 따라 이 화면이 아예 안 그려진 채로 몇 초가 지나가
        # "오버레이가 안 뜬다"는 것처럼 보일 수 있다. repaint()로 지금 당장
        # 강제로 한 번 그리고, processEvents()도 두 번 불러 화면에 실제로
        # 반영될 여유를 확실히 준다.
        self.repaint()
        QApplication.processEvents()
        QApplication.processEvents()

    def set_progress(self, pct, text=None):
        """[v44.3] pct가 None이면 "(NN%)" 없이 문구만 갱신한다 — 확장자로
        찾기처럼 전체 대상 파일 수를 미리 알 수 없어 퍼센트 자체가
        의미 없는 작업(스캔한 개수만 계속 늘어나는 경우)에 쓴다."""
        if text:
            self._base_text = text
        if pct is None:
            self.label.setText(self._base_text)
        else:
            self.label.setText(f"{self._base_text} ({pct}%)")

    def stop(self):
        self.wave.stop()
        self.setVisible(False)

    # 오버레이가 떠 있는 동안 부모(top_area) 크기가 바뀌면 같이 맞춘다
    def reposition(self):
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())

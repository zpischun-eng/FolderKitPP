# -*- coding: utf-8 -*-
"""
FolderKit++ — 애니메이션 미니앱 공용 캔버스 [v44]

행운의 번호·응원의 메시지처럼 **초당 60프레임으로 움직이는** 미니앱이
함께 쓰는 기반. 지금까지의 미니앱은 전부 "입력 → 계산 → 정지 화면"이라
이런 부품이 필요 없었다.

- 고정 시간 간격 루프: QTimer(16ms)로 화면을 다시 그리고, 흐른 시간을
  누적해 물리를 PHYS_DT(1/60초) 단위로 진행한다. 한 프레임에 최대
  MAX_STEPS번만 진행해 느린 PC에서 "밀린 스텝을 따라잡다 멈추는" 현상을 막는다.
- 가려지면 멈춤: 다른 도구로 바꾸거나 다른 모드로 나가면(hideEvent) 루프를
  세운다 — 안 보이는 애니메이션이 CPU를 쓰지 않게.
- 논리 좌표 1600x900: 장면은 항상 이 좌표로 그리고, 실제 위젯 크기에 맞춰
  비율을 유지한 채 확대·축소한다(프로젝터·전자칠판 어떤 해상도든 같은 구도).
- 고해상도 배율: 스프라이트 캐시는 devicePixelRatioF()를 반영해 만든다
  (v43.x 이미지 미리보기 화질 버그와 같은 문제를 처음부터 막는다).
- 전체화면 발표 모드: 캔버스만 떼어 전체화면 창에 옮겼다가 Esc로 원래
  자리에 돌려놓는다. 메인 윈도우는 전혀 건드리지 않는다(미니앱은
  MainWindow를 모른다는 원칙 그대로).
"""
import math

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPixmap, QFont, QPen, QRadialGradient, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget, QVBoxLayout

from .anim_physics import PHYS_DT

LOGICAL_W, LOGICAL_H = 1600.0, 900.0
MAX_STEPS = 6


class AnimCanvas(QWidget):
    """장면 하나를 그리는 캔버스. 하위 클래스가 advance(dt)와 paint_scene(p)를 채운다."""

    primaryRequested = Signal()          # 스페이스·엔터·PageDown(발표 리모컨)
    exitFullscreenRequested = Signal()   # Esc

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._acc = 0.0
        self.time = 0.0            # 장면 시간(초) — 물리 스텝 누적
        self.bg_color = QColor("#ffffff")

    # ------------------------------------------------------------ 루프
    def start_loop(self):
        if not self._timer.isActive():
            self._clock.restart()
            self._acc = 0.0
            self._timer.start()

    def stop_loop(self):
        self._timer.stop()

    def is_running(self):
        return self._timer.isActive()

    def _tick(self):
        elapsed = self._clock.restart() / 1000.0
        self._acc += min(elapsed, 0.25)
        steps = 0
        while self._acc >= PHYS_DT and steps < MAX_STEPS:
            self.run_steps(1)
            self._acc -= PHYS_DT
            steps += 1
        if steps >= MAX_STEPS:
            self._acc = 0.0
        self.update()

    def run_steps(self, n):
        """물리를 n스텝 진행한다(테스트에서 화면 없이 직접 부를 수 있다)."""
        for _ in range(n):
            self.time += PHYS_DT
            self.advance(PHYS_DT)

    def advance(self, dt):
        pass

    def showEvent(self, e):
        super().showEvent(e)
        self.start_loop()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_loop()

    # ------------------------------------------------------------ 좌표
    def _transform(self):
        w, h = max(1, self.width()), max(1, self.height())
        scale = min(w / LOGICAL_W, h / LOGICAL_H)
        ox = (w - LOGICAL_W * scale) / 2
        oy = (h - LOGICAL_H * scale) / 2
        return scale, ox, oy

    def to_scene(self, pos):
        scale, ox, oy = self._transform()
        return QPointF((pos.x() - ox) / scale, (pos.y() - oy) / scale)

    def device_scale(self):
        """논리 1단위가 실제 물리 픽셀 몇 개인지(스프라이트 캐시 해상도)."""
        scale, _ox, _oy = self._transform()
        return scale * self.devicePixelRatioF()

    # ------------------------------------------------------------ 그리기
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        scale, ox, oy = self._transform()
        self.paint_backdrop(p, ox, oy, scale)
        p.translate(ox, oy)
        p.scale(scale, scale)
        p.setClipRect(QRectF(0, 0, LOGICAL_W, LOGICAL_H))
        self.paint_scene(p)
        p.end()

    def paint_scene(self, p):
        pass

    def paint_backdrop(self, p, ox, oy, scale):
        """논리 화면(16:9) 바깥 여백을 칠한다 — 캔버스 비율이 16:9가 아닐 때
        위아래(또는 좌우)에 생기는 띠. 기본은 bg_color 한 색."""
        p.fillRect(self.rect(), self.bg_color)

    # ------------------------------------------------------------ 키
    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_PageDown):
            self.primaryRequested.emit()
            return
        if k == Qt.Key_Escape:
            self.exitFullscreenRequested.emit()
            return
        super().keyPressEvent(e)


# =============================================================================
# 전체화면 발표 모드
# =============================================================================
class _PresenterWindow(QWidget):
    """전체화면 창. Alt+F4 등으로 창이 직접 닫혀도 캔버스를 먼저 원래 자리로
    돌려놓는다(그러지 않으면 창과 함께 캔버스까지 지워진다)."""

    def __init__(self, presenter):
        super().__init__(None, Qt.Window)
        self._presenter = presenter

    def closeEvent(self, e):
        if self._presenter.window is self:
            self._presenter.exit()
        super().closeEvent(e)


class FullscreenPresenter:
    """캔버스를 원래 레이아웃에서 떼어 전체화면 창으로 옮기고, 끝나면 되돌린다."""

    def __init__(self, canvas, title=""):
        self.canvas = canvas
        self.title = title
        self.window = None
        self._home_layout = None
        self._home_index = -1

    @property
    def active(self):
        return self.window is not None

    def enter(self):
        if self.window is not None:
            return
        parent = self.canvas.parentWidget()
        lay = parent.layout() if parent is not None else None
        self._home_layout = lay
        self._home_index = lay.indexOf(self.canvas) if lay is not None else -1
        win = _PresenterWindow(self)
        win.setWindowTitle(self.title)
        win.setStyleSheet("background:#000000;")
        v = QVBoxLayout(win)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.canvas)
        self.window = win
        win.showFullScreen()
        self.canvas.show()
        self.canvas.setFocus()

    def exit(self):
        if self.window is None:
            return
        win = self.window
        self.window = None
        if self._home_layout is not None:
            if self._home_index >= 0:
                self._home_layout.insertWidget(self._home_index, self.canvas)
            else:
                self._home_layout.addWidget(self.canvas)
        self.canvas.show()
        win.close()
        win.deleteLater()
        self.canvas.setFocus()

    def toggle(self):
        if self.active:
            self.exit()
        else:
            self.enter()


# =============================================================================
# 스프라이트(공) 캐시
# =============================================================================
class BallSpriteCache:
    """번호가 적힌 공을 미리 그려 둔다 — 120개를 매 프레임 그라데이션·글자로
    새로 그리면 느리다. 캐시 키에 실제 픽셀 크기를 넣으므로 창 크기나 모니터
    배율이 바뀌면 자동으로 새로 그린다.

    [v44.2] 야구공 모양 — 흰 가죽 + 양옆의 붉은 실밥(곡선과 바늘땀). `fill`은
    실밥 색, `ring`은 윤곽선 색이다. 번호는 가운데에 크게 쓴다(실밥은 양옆
    가장자리에만 있어 번호를 가리지 않는다)."""

    def __init__(self):
        self._cache = {}

    def clear(self):
        self._cache.clear()

    def get(self, text, fill, radius_logical, device_scale, text_color="#1b2a49", ring=None):
        px_r = max(4, int(round(radius_logical * device_scale)))
        key = (text, fill, px_r, text_color, ring)
        pix = self._cache.get(key)
        if pix is not None:
            return pix
        size = px_r * 2 + 4
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        c = QPointF(size / 2, size / 2)
        grad = QRadialGradient(QPointF(c.x() - px_r * 0.35, c.y() - px_r * 0.4), px_r * 1.4)
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.65, QColor("#f6f1e6"))
        grad.setColorAt(1.0, QColor("#cdc4b1"))
        p.setPen(QPen(QColor(ring) if ring else QColor("#6b6255"), max(1.0, px_r * 0.05)))
        p.setBrush(QBrush(grad))
        p.drawEllipse(c, px_r, px_r)
        # 실밥 — 양옆에서 휘어 들어오는 곡선 + 짧은 바늘땀(공 밖으로 나가는 부분은 잘라 낸다)
        p.save()
        clip = QPainterPath()
        clip.addEllipse(c, px_r - 0.5, px_r - 0.5)
        p.setClipPath(clip)
        seam = QColor(fill)
        pen = QPen(seam, max(1.2, px_r * 0.08))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for side in (-1, 1):
            ccx = c.x() + side * px_r * 1.68
            rad = px_r * 0.9
            path = QPainterPath()
            for i, a in enumerate(range(-55, 56, 5)):
                ar = math.radians(a)
                pt = QPointF(ccx - side * rad * math.cos(ar), c.y() - rad * math.sin(ar))
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            p.drawPath(path)
            tick = px_r * 0.16
            for a in range(-45, 46, 15):
                ar = math.radians(a)
                dx, dy = -side * math.cos(ar), -math.sin(ar)   # 호의 바깥쪽이 아니라 "호에 수직" 방향
                pt = QPointF(ccx + dx * rad, c.y() + dy * rad)
                p.drawLine(QPointF(pt.x() - dx * tick * 0.5, pt.y() - dy * tick * 0.5),
                           QPointF(pt.x() + dx * tick * 0.5, pt.y() + dy * tick * 0.5))
        p.restore()
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(6, int(px_r * (0.86 if len(text) <= 2 else 0.6))))
        p.setFont(f)
        p.setPen(QColor(text_color))
        p.drawText(QRectF(c.x() - px_r, c.y() - px_r, px_r * 2, px_r * 2), Qt.AlignCenter, text)
        p.end()
        pix.setDevicePixelRatio(device_scale)
        if len(self._cache) > 800:
            self._cache.clear()
        self._cache[key] = pix
        return pix


def draw_sprite_centered(p, pix, x, y):
    """캐시한 스프라이트를 논리 좌표 (x, y)를 중심으로 그린다."""
    w = pix.width() / pix.devicePixelRatio()
    h = pix.height() / pix.devicePixelRatio()
    p.drawPixmap(QPointF(x - w / 2, y - h / 2), pix)

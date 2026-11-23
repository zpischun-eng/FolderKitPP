# -*- coding: utf-8 -*-
"""
FolderKit++ — 응원의 메시지 [v44] 장면

하늘에 떠 있는 풍선을 활로 맞히면 풍선이 터지며 숨은 메시지 카드가 펼쳐진다.
마우스(또는 터치)를 **아무 데서나 눌러 뒤로 끌었다 놓으면** 화살이 날아간다
(새총처럼 — 전자칠판에서 학생이 바로 쏠 수 있게). 황금 풍선 = 오늘의 메시지.
"""
import math
import random as _random

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPen, QBrush, QPainterPath, QLinearGradient, QRadialGradient, QFontMetricsF

from ..i18n import tr
from . import cheer_logic as CL
from .anim_kit import AnimCanvas, LOGICAL_W, LOGICAL_H
from .anim_physics import ParticleSystem, ease_out_cubic

CARD_RECT = QRectF(280, 190, 1040, 470)


def _font(px, bold=False):
    f = QFont()
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


class CheerScene(AnimCanvas):
    balloonPopped = Signal(str)      # 메시지 id
    cardClosed = Signal()
    missed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_color = QColor("#dff1ff")
        self.balloons = []
        self.arrow = None
        self.difficulty = "normal"
        self.params = CL.DIFF_PARAMS["normal"]
        self.wind = 0.0
        self.guide_forced = False     # 3번 연속 빗나가면 자동으로 켜짐
        self.guide_user = False       # 사용자가 켠 보조선
        self.misses = 0
        self.aim_from = None          # 드래그 시작점(장면 좌표)
        self.aim_to = None
        self.card = None              # {"mid", "x", "y", "t", "golden"}
        self.date_label = ""
        self.message_of = lambda mid: None     # 위젯이 넣어 준다(id → 메시지 dict)
        self.category_label = lambda key: key
        self.particles = ParticleSystem()
        self.rng = _random.Random()
        self._clouds = [(_random.Random(i).uniform(0, 1600), _random.Random(i + 50).uniform(40, 330),
                         _random.Random(i + 99).uniform(0.6, 1.3)) for i in range(7)]

    # ================================================================ 설정
    def set_round(self, ids, difficulty="normal", seed=None):
        self.difficulty = difficulty if difficulty in CL.DIFF_PARAMS else "normal"
        self.params = CL.DIFF_PARAMS[self.difficulty]
        rng = _random.Random(seed)
        self.balloons = CL.make_balloons(ids, rng, self.difficulty)
        self.arrow = None
        self.card = None
        self.misses = 0
        self.guide_forced = False
        self._new_wind(rng)
        self.particles.clear()
        self.update()

    def _new_wind(self, rng=None):
        rng = rng or self.rng
        w = self.params["wind"]
        self.wind = rng.uniform(-w, w) if w else 0.0

    @property
    def guide_on(self):
        return self.params["guide"] or self.guide_user or self.guide_forced

    def remaining(self):
        return sum(1 for b in self.balloons if not b.popped)

    # ================================================================ 조작
    def can_shoot(self):
        return self.card is None and self.arrow is None and self.remaining() > 0

    def shoot(self, pull_dx, pull_dy):
        """당긴 벡터로 화살을 쏜다(테스트에서도 직접 부른다)."""
        if not self.can_shoot():
            return False
        vx, vy = CL.launch_velocity(pull_dx, pull_dy)
        if math.hypot(vx, vy) < 150:
            return False
        self.arrow = CL.Arrow(CL.BOW_X, CL.BOW_Y, vx, vy)
        return True

    def close_card(self):
        if self.card is None:
            return False
        self.card = None
        self.cardClosed.emit()
        self.update()
        return True

    def mousePressEvent(self, e):
        self.setFocus()
        if self.card is not None:
            if self.card["t"] > 0.35:
                self.close_card()
            return
        if not self.can_shoot():
            return
        pos = self.to_scene(e.position())
        self.aim_from = pos
        self.aim_to = pos

    def mouseMoveEvent(self, e):
        if self.aim_from is not None:
            self.aim_to = self.to_scene(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        if self.aim_from is None:
            return
        a, b = self.aim_from, self.to_scene(e.position())
        self.aim_from = self.aim_to = None
        self.shoot(b.x() - a.x(), b.y() - a.y())

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and self.card is not None:
            self.close_card()
            return
        super().keyPressEvent(e)

    # ================================================================ 진행
    def advance(self, dt):
        t = self.time
        self.particles.step(dt)
        if self.card is not None:
            self.card["t"] += dt
        if self.arrow is None:
            return
        self.arrow.step(dt, self.wind)
        for b in self.balloons:
            if b.popped:
                continue
            if CL.arrow_hits(self.arrow, b, t, self.params["rx"], self.params["ry"]):
                self._pop(b, t)
                return
        if not self.arrow.alive:
            self.arrow = None
            self.misses += 1
            if self.misses >= 3:
                self.guide_forced = True
            if self.difficulty == "hard":
                self._new_wind()
            self.missed.emit()

    def _pop(self, b, t):
        b.popped = True
        x, y = b.pos(t)
        self.arrow = None
        self.misses = 0
        colors = [b.color, "#ffffff", "#ffd166", "#ef476f", "#06d6a0", "#118ab2"]
        self.particles.burst(self.rng, x, y, [b.color], count=18, speed=(250, 600), size=(6, 12),
                             life=(0.4, 0.8), kind="confetti")
        self.particles.burst(self.rng, x, y, colors, count=60, speed=(150, 700), size=(3, 7),
                             life=(0.7, 1.6), kind="confetti")
        self.card = {"mid": b.mid, "x": x, "y": y, "t": 0.0, "golden": b.golden}
        if self.difficulty == "hard":
            self._new_wind()
        self.balloonPopped.emit(b.mid)

    # ================================================================ 그리기
    def paint_backdrop(self, p, ox, oy, scale):
        # 위 여백은 하늘색, 아래 여백은 풀색 — 창 비율이 달라도 장면이 이어져 보이게.
        w, h = self.width(), self.height()
        mid = oy + LOGICAL_H * scale * 0.5
        p.fillRect(QRectF(0, 0, w, mid), QColor("#bfe3ff"))
        p.fillRect(QRectF(0, mid, w, h - mid), QColor("#8cc970"))

    def paint_scene(self, p):
        self._paint_sky(p)
        self._paint_header(p)
        t = self.time
        for b in self.balloons:
            if not b.popped:
                self._paint_balloon(p, b, t)
        self._paint_archer(p)
        if self.arrow is not None:
            self._paint_arrow(p, self.arrow.x, self.arrow.y, self.arrow.vx, self.arrow.vy)
        for part in self.particles.items:
            a = max(0.0, 1.0 - part.age / part.life)
            c = QColor(part.color)
            c.setAlphaF(a)
            p.save()
            p.translate(part.x, part.y)
            p.rotate(math.degrees(part.angle))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRect(QRectF(-part.size, -part.size * 0.45, part.size * 2, part.size * 0.9))
            p.restore()
        if self.remaining() == 0 and self.card is None and self.balloons:
            p.setPen(QColor("#1f3b57"))
            p.setFont(_font(40, True))
            p.drawText(QRectF(0, 330, LOGICAL_W, 70), Qt.AlignCenter, tr("util.cheer.scene.all_done"))
            p.setFont(_font(22))
            p.drawText(QRectF(0, 400, LOGICAL_W, 40), Qt.AlignCenter, tr("util.cheer.scene.all_done_hint"))
        if self.card is not None:
            self._paint_card(p)

    def _paint_sky(self, p):
        g = QLinearGradient(0, 0, 0, LOGICAL_H)
        g.setColorAt(0.0, QColor("#bfe3ff"))
        g.setColorAt(0.75, QColor("#eef8ff"))
        g.setColorAt(1.0, QColor("#f7fbff"))
        p.fillRect(QRectF(0, 0, LOGICAL_W, LOGICAL_H), g)
        p.setPen(Qt.NoPen)
        for i, (cx, cy, s) in enumerate(self._clouds):
            x = (cx + self.time * 12 * s) % (LOGICAL_W + 300) - 150
            p.setBrush(QColor(255, 255, 255, 200))
            for dx, dy, r in ((0, 0, 38), (34, -12, 30), (64, 0, 34), (30, 12, 32)):
                p.drawEllipse(QPointF(x + dx * s, cy + dy * s), r * s, r * s)
        p.setBrush(QColor("#a7d98b"))
        path = QPainterPath(QPointF(0, 740))
        path.cubicTo(400, 700, 900, 780, 1600, 720)
        path.lineTo(1600, 900)
        path.lineTo(0, 900)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#8cc970"))
        path2 = QPainterPath(QPointF(0, 800))
        path2.cubicTo(500, 770, 1100, 840, 1600, 790)
        path2.lineTo(1600, 900)
        path2.lineTo(0, 900)
        path2.closeSubpath()
        p.drawPath(path2)

    def _paint_header(self, p):
        p.setPen(QColor("#1f3b57"))
        p.setFont(_font(32, True))
        p.drawText(QRectF(40, 20, 900, 46), Qt.AlignLeft | Qt.AlignVCenter, tr("util.cheer.scene.title"))
        p.setFont(_font(18))
        p.setPen(QColor("#44617d"))
        p.drawText(QRectF(40, 64, 900, 28), Qt.AlignLeft | Qt.AlignVCenter, self.date_label)
        # 바람 표시
        box = QRectF(1270, 24, 290, 56)
        p.setPen(QPen(QColor("#9cc3e4"), 2))
        p.setBrush(QColor(255, 255, 255, 190))
        p.drawRoundedRect(box, 12, 12)
        p.setPen(QColor("#1f3b57"))
        p.setFont(_font(17, True))
        if abs(self.wind) < 1:
            txt = tr("util.cheer.scene.wind_none")
        else:
            arrow = "→" if self.wind > 0 else "←"
            txt = tr("util.cheer.scene.wind", a0=arrow, a1=int(abs(self.wind) / 20) + 1)
        p.drawText(box, Qt.AlignCenter, txt)
        p.setFont(_font(16))
        p.setPen(QColor("#44617d"))
        p.drawText(QRectF(1270, 84, 290, 26), Qt.AlignCenter,
                   tr("util.cheer.scene.remaining", a0=self.remaining(), a1=len(self.balloons)))

    def _paint_balloon(self, p, b, t):
        x, y = b.pos(t)
        rx, ry = self.params["rx"], self.params["ry"]
        # 줄
        p.setPen(QPen(QColor(90, 90, 90, 160), 1.6))
        path = QPainterPath(QPointF(x, y + ry + 6))
        for k in range(1, 7):
            yy = y + ry + 6 + k * 16
            xx = x + math.sin(t * 3 + k + b.p1) * 5
            path.lineTo(xx, yy)
        p.drawPath(path)
        base = QColor(b.color)
        g = QRadialGradient(QPointF(x - rx * 0.35, y - ry * 0.4), max(rx, ry) * 1.4)
        g.setColorAt(0.0, base.lighter(170))
        g.setColorAt(0.5, base)
        g.setColorAt(1.0, base.darker(140))
        p.setPen(QPen(base.darker(150), 1.5))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(x, y), rx, ry)
        # 매듭
        knot = QPainterPath(QPointF(x - 7, y + ry + 8))
        knot.lineTo(x + 7, y + ry + 8)
        knot.lineTo(x, y + ry - 2)
        knot.closeSubpath()
        p.setBrush(base.darker(120))
        p.drawPath(knot)
        # 반짝임
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawEllipse(QPointF(x - rx * 0.38, y - ry * 0.42), rx * 0.16, ry * 0.24)
        if b.golden:
            p.setPen(QColor("#7a5a00"))
            p.setFont(_font(max(18, rx * 0.55), True))
            p.drawText(QRectF(x - rx, y - ry, rx * 2, ry * 2), Qt.AlignCenter, "★")

    def _paint_archer(self, p):
        bx, by = CL.BOW_X, CL.BOW_Y
        # 사람 실루엣(단순)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#274c77"))
        p.drawEllipse(QPointF(bx - 70, by - 86), 22, 22)
        body = QPainterPath(QPointF(bx - 92, by - 60))
        body.lineTo(bx - 48, by - 60)
        body.lineTo(bx - 40, by + 40)
        body.lineTo(bx - 100, by + 40)
        body.closeSubpath()
        p.drawPath(body)
        p.setPen(QPen(QColor("#274c77"), 12, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(bx - 70, by + 38), QPointF(bx - 86, by + 112))
        p.drawLine(QPointF(bx - 70, by + 38), QPointF(bx - 50, by + 112))

        # 조준 방향
        pull = QPointF(0, 0)
        if self.aim_from is not None and self.aim_to is not None:
            pull = QPointF(self.aim_to.x() - self.aim_from.x(), self.aim_to.y() - self.aim_from.y())
        d = math.hypot(pull.x(), pull.y())
        if d > 4:
            ang = math.atan2(-pull.y(), -pull.x())
        else:
            ang = math.radians(-35)
        pull_len = min(d, CL.PULL_MAX) / CL.PULL_MAX * 60
        cosA, sinA = math.cos(ang), math.sin(ang)

        def _local_to_world(lx, ly):
            return QPointF(bx + lx * cosA - ly * sinA, by + lx * sinA + ly * cosA)

        # [버그 수정] 활 잡은 팔을 어깨부터 조준 각도로 회전한 좌표계 "안"에서
        # 그리고 있었다 — 조준 방향이 바뀔 때마다 어깨 자체가 활과 함께 홱
        # 돌아가는 것처럼 보여 팔이 이상하게 꺾여 보였다. 어깨는 몸(고정)에
        # 붙여 두고, 손(활 손잡이, grip)만 조준 방향을 따라 움직이게 한 뒤,
        # 그 사이를 팔꿈치로 살짝 굽혀 잇는다(자연스러운 굽힘새를 위한 근사).
        grip = _local_to_world(-6, 0)
        shoulder = QPointF(bx - 55, by - 40)
        seg_dx, seg_dy = grip.x() - shoulder.x(), grip.y() - shoulder.y()
        seg_len = math.hypot(seg_dx, seg_dy) or 1.0
        perp = QPointF(-seg_dy / seg_len, seg_dx / seg_len)
        elbow = QPointF((shoulder.x() + grip.x()) / 2 + perp.x() * 14,
                        (shoulder.y() + grip.y()) / 2 + perp.y() * 14)
        p.setPen(QPen(QColor("#274c77"), 11, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(shoulder, elbow)
        p.drawLine(elbow, grip)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e8b58a"))
        p.drawEllipse(grip, 7, 7)   # 손

        p.save()
        p.translate(bx, by)
        p.rotate(math.degrees(ang))
        # 활(곡선) + 시위 — 활 자체는 이 회전 좌표계 안에서 그린다(활은 곧게
        # 유지한 채 통째로 조준 방향으로 돈다. 팔은 위에서 이미 그렸다).
        bow = QPainterPath(QPointF(-6, -92))
        bow.quadTo(46, 0, -6, 92)
        p.setPen(QPen(QColor("#8d5524"), 8, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(bow)
        p.setPen(QPen(QColor("#4a4a4a"), 2))
        p.drawLine(QPointF(-6, -92), QPointF(-12 - pull_len, 0))
        p.drawLine(QPointF(-12 - pull_len, 0), QPointF(-6, 92))
        if self.arrow is None and self.card is None and self.remaining() > 0:
            self._paint_arrow_local(p, -12 - pull_len + 46, 0)
        p.restore()

        # 보조선
        if self.aim_from is not None and d > 4 and self.guide_on:
            vx, vy = CL.launch_velocity(pull.x(), pull.y())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(31, 59, 87, 140))
            for i, (x, y) in enumerate(CL.trajectory(vx, vy, self.wind)):
                if i % 2 == 0:
                    p.drawEllipse(QPointF(x, y), 4, 4)
        if self.aim_from is not None and d > 4:
            p.setPen(QColor("#1f3b57"))
            p.setFont(_font(18, True))
            p.drawText(QRectF(bx - 120, by + 120, 240, 30), Qt.AlignCenter,
                       tr("util.cheer.scene.power", a0=int(min(d, CL.PULL_MAX) / CL.PULL_MAX * 100)))
        elif self.can_shoot():
            p.setPen(QColor("#44617d"))
            p.setFont(_font(18))
            p.drawText(QRectF(40, 840, 900, 40), Qt.AlignLeft | Qt.AlignVCenter, tr("util.cheer.scene.how"))

    def _paint_arrow_local(self, p, tip_x, tip_y):
        p.setPen(QPen(QColor("#5b3a1a"), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(tip_x - 92, tip_y), QPointF(tip_x - 8, tip_y))
        head = QPainterPath(QPointF(tip_x + 6, tip_y))
        head.lineTo(tip_x - 12, tip_y - 8)
        head.lineTo(tip_x - 12, tip_y + 8)
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#6b7280"))
        p.drawPath(head)
        p.setBrush(QColor("#ef476f"))
        for dy in (-7, 7):
            f = QPainterPath(QPointF(tip_x - 92, tip_y))
            f.lineTo(tip_x - 104, tip_y + dy)
            f.lineTo(tip_x - 80, tip_y + dy)
            f.lineTo(tip_x - 72, tip_y)
            f.closeSubpath()
            p.drawPath(f)

    def _paint_arrow(self, p, x, y, vx, vy):
        p.save()
        p.translate(x, y)
        p.rotate(math.degrees(math.atan2(vy, vx)))
        self._paint_arrow_local(p, 23, 0)
        p.restore()

    def _paint_card(self, p):
        c = self.card
        prog = ease_out_cubic(c["t"] / 0.45)
        tr_ = CARD_RECT
        sx, sy = c["x"], c["y"]
        rect = QRectF(sx + (tr_.left() - sx) * prog, sy + (tr_.top() - sy) * prog,
                      max(20.0, tr_.width() * prog), max(20.0, tr_.height() * prog))
        # 배경 어둡게
        p.fillRect(QRectF(0, 0, LOGICAL_W, LOGICAL_H), QColor(10, 25, 45, int(110 * prog)))
        golden = c["golden"]
        p.setPen(QPen(QColor("#d4a017" if golden else "#9cc3e4"), 6 if golden else 3))
        p.setBrush(QColor("#fffdf5" if golden else "#ffffff"))
        p.drawRoundedRect(rect, 28, 28)
        if prog < 0.95:
            return
        msg = self.message_of(c["mid"]) or {"text": "", "sub": "", "category": "cheer"}
        inner = rect.adjusted(60, 40, -60, -40)
        p.setPen(QColor("#b8860b" if golden else "#44617d"))
        p.setFont(_font(24, True))
        head = tr("util.cheer.scene.today_message", a0=self.date_label) if golden else \
            self.category_label(msg.get("category", "cheer"))
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 34), Qt.AlignLeft | Qt.AlignVCenter,
                   ("★ " if golden else "") + head)
        body = QRectF(inner.left(), inner.top() + 50, inner.width(), inner.height() - 120)
        text = msg.get("text", "")
        size = 60
        while size > 24:
            f = _font(size, True)
            fm = QFontMetricsF(f)
            br = fm.boundingRect(body, Qt.TextWordWrap | Qt.AlignCenter, text)
            if br.height() <= body.height() and br.width() <= body.width():
                break
            size -= 4
        p.setFont(_font(size, True))
        p.setPen(QColor("#1a1a1a"))
        p.drawText(body, Qt.TextWordWrap | Qt.AlignCenter, text)
        if msg.get("sub"):
            p.setFont(_font(24))
            p.setPen(QColor("#5a6068"))
            p.drawText(QRectF(inner.left(), inner.bottom() - 64, inner.width(), 34),
                       Qt.AlignRight | Qt.AlignVCenter, "— " + msg["sub"])
        p.setFont(_font(16))
        p.setPen(QColor("#8a94a3"))
        p.drawText(QRectF(inner.left(), inner.bottom() - 26, inner.width(), 26), Qt.AlignCenter,
                   tr("util.cheer.scene.close_hint"))

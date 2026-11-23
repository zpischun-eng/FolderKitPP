# -*- coding: utf-8 -*-
"""
FolderKit++ — 행운의 번호 [v44.2] 장면(그리기 + 연출 진행)

"Lucky LOTTO" — 야구공이 굴러다니는 추첨 드럼. 뽑기 한 번으로 [섞기 →
감속(완전 정지) → 바람으로 날림 → PORT 흡입]까지 자동으로 진행된다.

  ┌ Lucky LOTTO ───────────────────────────────────────┐
  │ 드럼 + PORT 캡슐                │ 결과 패널(상태 문구 +   │
  │                                │  당첨 번호를 아주 크게) │
  │                                ├────────────────────┤
  │                                │ 당첨 공(전부 보인다)   │
  └────────────────────────────────┴────────────────────┘

[v44.2] 화면 정리 — 프로젝터·전자칠판에서도 읽히도록 글씨를 전부 키우고
(가장 작은 글씨도 논리 좌표로 30px 안팎), 읽기 어려운 잔글씨(부제·PORT
라벨·드럼 정보·시드)는 없앴다. 결과는 "당첨 번호" 하나만 아주 크게 보여
주고, 당첨 공 목록은 공 크기를 개수에 맞춰 자동으로 줄여 **전부** 보이게
한다. 결과를 정하는 것은 이 파일이 아니다 — lucky_draw_logic.DrumSim(물리)이
정하고, 여기서는 그 결과를 보여 준다.
"""
import math
import random as _random

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen, QPainterPath

from ..i18n import tr
from . import lucky_draw_logic as L
from .anim_kit import AnimCanvas, BallSpriteCache, draw_sprite_centered, LOGICAL_W, LOGICAL_H
from .anim_physics import ParticleSystem, ease_out_cubic

# ---------------------------------------------------------------- 배치(논리 좌표 1600x900)
RESULT_RECT = QRectF(880, 100, 680, 370)
TRAY_RECT = QRectF(880, 490, 680, 394)

# ---------------------------------------------------------------- 테마(내부 키 → 색)
PALETTES = {
    "stadium": {  # 기본 — 야구장(잔디 + 흙색 테두리 + 전광판 노랑)
        "bg": "#1c5a32", "grid": "#226a3a", "via": "#2f7d47", "drum_fill": "#0e3a21",
        "drum_edge": "#e8c98a", "accent": "#ffd54f", "text": "#fff8e1", "dim": "#a9cdb0",
        "term_bg": "#0a2b19", "term_fg": "#ffd54f", "term_dim": "#8fbf9b", "panel": "#0c3220",
        "tray": "#0c3220", "warn": "#ff6b6b",
        "balls": ["#c62828"] * 6,
        "confetti": ["#ffd54f", "#ffffff", "#e53935", "#42a5f5", "#66bb6a"],
    },
    "night": {  # 야간 경기(남색 하늘 + 조명 노랑)
        "bg": "#0b1730", "grid": "#10203f", "via": "#1c3160", "drum_fill": "#070f22",
        "drum_edge": "#ffd54f", "accent": "#ffd54f", "text": "#f0f4ff", "dim": "#8ea2c9",
        "term_bg": "#050b18", "term_fg": "#ffe082", "term_dim": "#7f93bd", "panel": "#0c1a33",
        "tray": "#0c1a33", "warn": "#ff6b6b",
        "balls": ["#c62828"] * 6,
        "confetti": ["#ffd54f", "#ffffff", "#ef5350", "#64b5f6", "#81c784"],
    },
    "classic": {  # 일반 행사용 밝은 색
        "bg": "#f5f6fa", "grid": "#eceef5", "via": "#d8dbe6", "drum_fill": "#e3e9f4",
        "drum_edge": "#c2185b", "accent": "#c2185b", "text": "#1a1a1a", "dim": "#5b6472",
        "term_bg": "#1f2433", "term_fg": "#ffd54f", "term_dim": "#aab1c6", "panel": "#ffffff",
        "tray": "#ffffff", "warn": "#d32f2f",
        "balls": ["#c62828"] * 6,
        "confetti": ["#ffd54f", "#c2185b", "#e53935", "#42a5f5", "#66bb6a"],
    },
}

_SCRAMBLE_DIGITS = "0123456789"
_SCRAMBLE_NAME = "가나다라마바사아자차카타파하"


def _sans(px, bold=False):
    f = QFont()
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def _fit_px(text, max_w, max_px, min_px=24, bold=True):
    """text가 max_w 안에 들어가는 가장 큰 글자 크기(px)."""
    px = int(max_px)
    while px > min_px:
        if QFontMetricsF(_sans(px, bold)).horizontalAdvance(text) <= max_w:
            return px
        px -= 4
    return int(min_px)


def _fit_cell(n, w, h, cap=84, minimum=14):
    """n개의 공을 w×h 안에 다 넣을 수 있는 가장 큰 칸 지름. 공이 적으면 크게,
    많으면(최대 120개) 작게 — 어느 쪽이든 전부 보인다."""
    if n <= 0:
        return cap
    for d in range(cap, minimum - 1, -1):
        if int(w // d) * int(h // d) >= n:
            return d
    return minimum


class LuckyScene(AnimCanvas):
    """행운의 번호 캔버스. 결과가 정해지면 winnerDecided, 공개 연출이 끝나면
    revealFinished를 보낸다(연속 뽑기·조합은 위젯이 이어서 부른다)."""

    winnerDecided = Signal(str, object)   # (키, {"seed":..., "replay":...})
    revealFinished = Signal()
    replayFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self.speed = "normal"
        self.theme = "stadium"
        self.pal = PALETTES["stadium"]
        self.sprites = BallSpriteCache()
        self.particles = ParticleSystem()
        self.fx_rng = _random.Random()          # 연출 전용(결과와 무관)
        self.sim = None                         # 드럼(DrumSim)
        self.replay_mode = False
        self.reveal_key = None
        self.last_key = None
        self.combo_line = None                  # 조합 완성 시 결과 패널에 보이는 줄
        self.banner = None                      # (문구, 남은 시간)
        self._entry_idx = {}
        self._prev_port_sub = "closed"
        self._round_pending_finish = False
        self.bg_color = QColor(self.pal["bg"])

    # ================================================================ 설정
    def set_theme(self, theme):
        self.theme = theme if theme in PALETTES else "stadium"
        self.pal = PALETTES[self.theme]
        self.bg_color = QColor(self.pal["bg"])
        self.sprites.clear()
        self.update()

    def set_speed(self, speed):
        self.speed = speed if speed in L.SPEED_PROFILE else "normal"
        if self.sim is not None:
            self.sim.speed = self.speed

    def set_session(self, session):
        """추첨 대상이 바뀌었을 때(새 세션). 드럼을 새로 쌓는다."""
        self.session = session
        self._entry_idx = {e.key: (i, e) for i, e in enumerate(session.entries)} if session else {}
        self.sim = None
        self.reveal_key = None
        self.last_key = session.drawn[-1] if session and session.drawn else None
        self.combo_line = None
        self.replay_mode = False
        self._round_pending_finish = False
        self.particles.clear()
        if session is not None:
            self._ensure_round(force=True)
        self.update()

    def sync_pool(self):
        """결석 제외 등으로 뽑을 수 있는 대상이 바뀌었을 때 — 섞고 있지 않을
        때만 드럼의 공 구성을 맞춘다."""
        if self.session is None or self.busy:
            return
        self._ensure_round(force=True)
        self.update()

    # ================================================================ 상태
    @property
    def busy(self):
        if self.replay_mode:
            return True
        return bool(self.sim is not None and self.sim.busy)

    def is_mixing(self):
        return bool(self.sim is not None and self.sim.phase == "mixing")

    def _ensure_round(self, force=False):
        """드럼 한 회차를 준비한다. 지난 회차가 끝났거나(당첨 공이 나감),
        대상 구성이 바뀌었으면 **지금 공들의 상태에서 이어서** 새 회차를
        만든다."""
        if self.session is None:
            self.sim = None
            return
        keys = self.session.available_keys()
        total = max(1, len(self.session.entries))
        ball_r = L.ball_radius_for(total, L.DRUM_R)
        if self.sim is not None and not force and self.sim.winner is None:
            return
        snap = []
        if self.sim is not None:
            have = {row[0]: row for row in self.sim.world.snapshot()}
            snap = [have[k] for k in keys if k in have]
            missing = [k for k in keys if k not in have]
            # 복원 추첨 등으로 드럼에 다시 넣을 공은 드럼 위쪽에 가지런히 떨어뜨린다.
            for j, k in enumerate(missing):
                x = L.DRUM_CX + ((j % 7) - 3) * ball_r * 2.2
                y = L.DRUM_CY - L.DRUM_R * 0.45 - (j // 7) * ball_r * 2.2
                snap.append([k, x, y, 0.0, 0.0])
        seed = L.new_seed()
        if snap and len(snap) == len(keys):
            self.sim = L.DrumSim(keys, seed, snapshot=snap, ball_radius=ball_r, speed=self.speed)
        else:
            self.sim = L.DrumSim(keys, seed, ball_radius=ball_r, speed=self.speed)
        self._prev_port_sub = "closed"

    # ================================================================ 조작
    def request_draw(self):
        """한 명(한 개)을 뽑는다. 이미 진행 중이거나 뽑을 대상이 없으면 False."""
        if self.session is None or self.busy:
            return False
        keys = self.session.available_keys()
        if not keys:
            return False
        self.replay_mode = False
        self.reveal_key = None
        self.combo_line = None
        self._ensure_round()
        if self.sim is None:
            return False
        return bool(self.sim.start_draw())

    def play_replay(self, record):
        """기록 하나를 같은 장면으로 다시 보여 준다(세션 기록은 바꾸지 않는다)."""
        if self.busy or not record or not record.get("replay"):
            return False
        info = record["replay"]
        self.replay_mode = True
        self.reveal_key = None
        self.combo_line = None
        self.banner = [tr("util.lucky.banner.replay", a0=record.get("order", "")), 2.5]
        self.sim = L.DrumSim.from_replay(record.get("seed"), info)
        self._prev_port_sub = "closed"
        return True

    def show_combo(self, numbers):
        self.combo_line = " · ".join(f"{n:02d}" for n in numbers)
        self.update()

    # ================================================================ 진행
    def advance(self, dt):
        if self.banner:
            self.banner[1] -= dt
            if self.banner[1] <= 0:
                self.banner = None
        self.particles.step(dt)

        if self.sim is None:
            return
        prev_sub = self._prev_port_sub
        won = self.sim.step()
        if won is not None:
            self._on_winner(won, {"seed": self.sim.seed, "replay": self.sim.replay_info()})
        sub = self.sim.port_sub
        if sub == "holding" and prev_sub == "closing":
            c = self.capsule_pt()
            self.particles.burst(self.fx_rng, c.x(), c.y() - 6, self.pal["confetti"], count=70,
                                 speed=(250, 800), size=(4, 9), kind="confetti")
        if self._round_pending_finish and sub == "closed" and prev_sub != "closed":
            self._round_pending_finish = False
            was_replay = self.replay_mode
            self.replay_mode = False
            if not was_replay:
                self._ensure_round(force=True)
            if was_replay:
                self.replayFinished.emit()
            else:
                self.revealFinished.emit()
        self._prev_port_sub = sub

    def _on_winner(self, key, info):
        self.reveal_key = key
        self._round_pending_finish = True
        if not self.replay_mode:
            self.last_key = key
            self.winnerDecided.emit(key, info)

    # ================================================================ 좌표·문구
    def capsule_pt(self):
        """PORT 캡슐 중심 — 드럼 바깥 위쪽. 공이 아주 클 때(인원이 적을 때)도
        화면 위로 넘어가지 않게 오프셋을 제한한다."""
        r = self.sim.ball_r if self.sim else 18.0
        offset = min(r * 2.1, 95.0)
        y = max(66.0, L.DRUM_CY - L.DRUM_R - offset)
        return QPointF(L.DRUM_CX, y)

    def _entry_label(self, key):
        _i, e = self._entry_idx.get(key, (0, None))
        return str(e.no) if e else "?"

    def _ball_color(self, key):
        i, _e = self._entry_idx.get(key, (0, None))
        total = len(self._entry_idx) or 1
        return self.pal["balls"][L.color_bucket(i, total, len(self.pal["balls"]))]

    def _showing_result(self):
        """지금 결과 패널이 "이번에 뽑힌 공"을 보여 주는 중인가(닫힘~사라짐 구간)."""
        return bool(self.sim is not None and self.reveal_key is not None
                    and self.sim.port_sub in ("closing", "holding"))

    def status_text(self):
        """결과 패널 맨 위의 진행 문구 — 지금 뭘 하고 있는지 한 줄로."""
        sim = self.sim
        if sim is None or sim.phase == "idle":
            return tr("util.lucky.msg.last") if self.last_key is not None else tr("util.lucky.msg.idle")
        if sim.phase == "mixing":
            return tr("util.lucky.msg.mixing")
        if sim.phase == "slowdown":
            return tr("util.lucky.msg.slowdown")
        if sim.port_sub == "countdown":
            return tr("util.lucky.msg.countdown")
        if sim.port_sub in ("opening", "sucking"):
            return tr("util.lucky.msg.draw")
        return tr("util.lucky.msg.won")

    # ================================================================ 그리기
    def paint_scene(self, p):
        self._paint_field(p)
        self._paint_header(p)
        self._paint_drum(p)
        self._paint_port(p)
        self._paint_result(p)
        self._paint_tray(p)
        pal = self.pal
        for part in self.particles.items:
            a = max(0.0, 1.0 - part.age / part.life)
            c = QColor(part.color)
            c.setAlphaF(a)
            p.save()
            p.translate(part.x, part.y)
            p.rotate(math.degrees(part.angle))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(0, 0), part.size, part.size)
            p.restore()
        if self.banner:
            p.setFont(_sans(36, True))
            r = QRectF(LOGICAL_W / 2 - 440, 30, 880, 66)
            p.setPen(Qt.NoPen)
            c = QColor(pal["panel"])
            c.setAlpha(240)
            p.setBrush(c)
            p.drawRoundedRect(r, 14, 14)
            p.setPen(QColor(pal["accent"]))
            p.drawText(r, Qt.AlignCenter, self.banner[0])

    def _paint_field(self, p):
        """배경 — 잔디 깎은 줄무늬(야구장). 밝은 테마에서는 아주 옅게."""
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.pal["grid"]))
        for k in range(0, int(LOGICAL_H), 100):
            if (k // 100) % 2 == 0:
                p.drawRect(QRectF(0, k, LOGICAL_W, 100))

    def _paint_header(self, p):
        p.setPen(QColor(self.pal["accent"]))
        p.setFont(_sans(50, True))
        p.drawText(QRectF(40, 14, 380, 76), Qt.AlignLeft | Qt.AlignVCenter, "Lucky LOTTO")

    # ---------------------------------------------------------------- 드럼
    def _paint_drum(self, p):
        pal = self.pal
        cx, cy, R = L.DRUM_CX, L.DRUM_CY, L.DRUM_R
        fill = QColor(pal["drum_fill"])
        fill.setAlpha(240)
        p.setBrush(fill)
        p.setPen(QPen(QColor(pal["drum_edge"]), 8))
        p.drawEllipse(QPointF(cx, cy), R + 4, R + 4)
        sim = self.sim
        spin_level = sim.spin_level if sim else L.SPIN_IDLE / L.SPIN_FAST
        energetic = spin_level > 0.5
        rot = self.time * L.SPIN_FAST * spin_level if sim else self.time * L.SPIN_IDLE
        # 테두리를 따라 도는 점 — 지금 회전 속도를 그대로 보여 준다.
        p.setPen(Qt.NoPen)
        for k in range(48):
            a = rot + k * (2 * math.pi / 48)
            on = (k % 6 == int(self.time * 8) % 6) if energetic else (k % 12 == 0)
            p.setBrush(QColor(pal["accent"] if on else pal["via"]))
            p.drawEllipse(QPointF(cx + math.cos(a) * (R + 18), cy + math.sin(a) * (R + 18)), 4, 4)
        if sim is not None:
            w = sim.world
            ds = self.device_scale()
            for i in w.alive_indices():
                k = w.keys[i]
                if k == self.reveal_key and sim.port_sub in ("closing", "holding"):
                    continue   # 캡슐 애니메이션 쪽에서 따로 그린다
                pix = self.sprites.get(self._entry_label(k), self._ball_color(k), w.r, ds)
                draw_sprite_centered(p, pix, w.xs[i], w.ys[i])
                if w.stuck[i]:
                    p.setPen(QPen(QColor(pal["accent"]), max(1.2, w.r * 0.09)))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(w.xs[i], w.ys[i]), w.r * 1.16, w.r * 1.16)
                    p.setPen(Qt.NoPen)

    # ---------------------------------------------------------------- PORT 캡슐
    def _paint_port(self, p):
        pal = self.pal
        sim = self.sim
        cap = self.capsule_pt()
        r = sim.ball_r if sim else 18.0
        cap_w, cap_h = r * 2.0, r * 3.2
        neck_w = r * 1.15
        neck_top = cap.y() + cap_h / 2
        neck_bot = L.DRUM_CY - L.DRUM_R + 2
        p.setPen(QPen(QColor(pal["drum_edge"]), 3))
        p.setBrush(QColor(pal["panel"]))
        if neck_bot > neck_top:
            p.drawRect(QRectF(cap.x() - neck_w / 2, neck_top, neck_w, neck_bot - neck_top))
        rr = min(cap_w, cap_h) * 0.32
        cap_rect = QRectF(cap.x() - cap_w / 2, cap.y() - cap_h / 2, cap_w, cap_h)
        path = QPainterPath()
        path.addRoundedRect(cap_rect, rr, rr)
        blink = sim.blink if sim else 0.0
        door = sim.door if sim else 0.0
        sub = sim.port_sub if sim else "closed"
        if sub == "countdown":
            base = QColor(pal["accent"])
            base.setAlphaF(0.16 + blink * 0.7)
        elif sub in ("opening", "sucking"):
            base = QColor(pal["accent"])
            base.setAlphaF(0.85)
        else:
            base = QColor(pal["panel"])
        p.setPen(QPen(QColor(pal["drum_edge"]), 3))
        p.setBrush(base)
        p.drawPath(path)
        # 바닥 뚜껑 — door(0닫힘~1열림)만큼 아래에서부터 걷힌다.
        hatch_h = cap_h * 0.42 * (1.0 - door)
        if hatch_h > 0.4:
            p.save()
            p.setClipPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["panel"]))
            p.drawRect(QRectF(cap_rect.left() - 2, cap_rect.bottom() - hatch_h, cap_rect.width() + 4, hatch_h + 4))
            p.restore()
        # 캡슐 안에서 붙잡혀 사라지는 공(스냅 → 대기 → 서서히 사라짐)
        if sim is not None and self.reveal_key is not None and sub in ("closing", "holding"):
            prof = sim.profile
            if sub == "closing":
                f = ease_out_cubic(sim.sub_t / max(0.01, prof["close"]))
                start = sim.winner_pos or (cap.x(), cap.y())
                bx = start[0] + (cap.x() - start[0]) * f
                by = start[1] + (cap.y() - start[1]) * f
                alpha = 1.0
            else:
                bx, by = cap.x(), cap.y()
                alpha = max(0.0, 1.0 - sim.sub_t / max(0.01, prof["hold"]))
            ds = self.device_scale()
            pix = self.sprites.get(self._entry_label(self.reveal_key), self._ball_color(self.reveal_key),
                                   r * 0.85, ds)
            p.save()
            p.setOpacity(alpha)
            draw_sprite_centered(p, pix, bx, by)
            p.restore()

    # ---------------------------------------------------------------- 결과 패널
    def _paint_result(self, p):
        pal = self.pal
        r = RESULT_RECT
        p.setPen(QPen(QColor(pal["drum_edge"]), 5))
        p.setBrush(QColor(pal["term_bg"]))
        p.drawRoundedRect(r, 22, 22)
        sim = self.sim
        idle = sim is None or sim.phase == "idle"
        # 맨 위 한 줄 — 지금 뭘 하고 있는지(크게)
        p.setFont(_sans(40, True))
        p.setPen(QColor(pal["term_dim"] if idle else pal["accent"]))
        p.drawText(QRectF(r.left() + 30, r.top() + 14, r.width() - 60, 62), Qt.AlignLeft | Qt.AlignVCenter,
                   self.status_text())
        body = QRectF(r.left() + 20, r.top() + 84, r.width() - 40, r.height() - 100)

        if self.combo_line and idle:
            p.setPen(QColor(pal["term_fg"]))
            p.setFont(_sans(40, True))
            p.drawText(QRectF(body.left(), body.top(), body.width(), 56), Qt.AlignCenter, tr("util.lucky.scene.combo"))
            px = _fit_px(self.combo_line, body.width() - 30, 96)
            p.setFont(_sans(px, True))
            p.drawText(QRectF(body.left(), body.top() + 66, body.width(), body.height() - 80), Qt.AlignCenter,
                       self.combo_line)
            return
        key = self.reveal_key if self._showing_result() else self.last_key
        in_progress = (not idle) and not self._showing_result()
        _i, e = self._entry_idx.get(key, (0, None)) if key is not None else (0, None)
        if in_progress or e is None:
            p.setPen(QColor(pal["term_dim"]))
            p.setFont(_sans(190, True))
            p.drawText(body, Qt.AlignCenter, "?")
            return
        prof = sim.profile if sim else L.SPEED_PROFILE["normal"]
        if sim is not None and sim.port_sub == "closing":
            prog = ease_out_cubic(sim.sub_t / max(0.01, prof["close"] + prof["hold"]))
        else:
            prog = 1.0
        num_text = str(e.no)
        p.setPen(QColor(pal["term_fg"]))
        if e.name:
            top = QRectF(body.left(), body.top() - 6, body.width(), 170)
            px = _fit_px(num_text, body.width() - 40, 170)
            p.setFont(_sans(px, True))
            p.drawText(top, Qt.AlignCenter, self._scramble(num_text, min(1.0, prog * 1.6), _SCRAMBLE_DIGITS))
            name_prog = max(0.0, (prog - 0.35) / 0.65)
            npx = _fit_px(e.name, body.width() - 40, 84)
            p.setFont(_sans(npx, True))
            p.setPen(QColor(pal["text"]))
            p.drawText(QRectF(body.left(), body.top() + 168, body.width(), 96), Qt.AlignCenter,
                       self._scramble(e.name, name_prog, _SCRAMBLE_NAME))
            if e.sub and prog >= 1.0:
                p.setFont(_sans(34))
                p.setPen(QColor(pal["term_dim"]))
                p.drawText(QRectF(body.left(), body.top() + 262, body.width(), 44), Qt.AlignCenter, e.sub)
        else:
            px = _fit_px(num_text, body.width() - 40, 250)
            p.setFont(_sans(px, True))
            p.drawText(body, Qt.AlignCenter,
                       self._scramble(num_text, min(1.0, prog * 1.6), _SCRAMBLE_DIGITS))

    def _scramble(self, text, prog, pool):
        """공개 연출 — 왼쪽부터 한 글자씩 실제 글자로 고정되고, 그 전엔 숫자가
        빠르게 돌아간다(슬롯 머신처럼)."""
        if prog >= 1.0:
            return text
        fixed = int(max(0.0, prog) * len(text))
        rng = _random.Random(int(self.time * 24))
        return "".join(ch if (i < fixed or ch == " ") else pool[rng.randrange(len(pool))]
                       for i, ch in enumerate(text))

    # ---------------------------------------------------------------- 당첨 공(전부 보임)
    def _paint_tray(self, p):
        pal = self.pal
        r = TRAY_RECT
        p.setPen(QPen(QColor(pal["via"]), 3))
        c = QColor(pal["tray"])
        c.setAlpha(235)
        p.setBrush(c)
        p.drawRoundedRect(r, 22, 22)
        s = self.session
        keys = []
        if s is not None:
            keys = list(s.combo_current) if s.draw_type == "combo" else list(s.drawn)
        remain = len(self.sim.world.alive_indices()) if self.sim else 0
        p.setPen(QColor(pal["text"]))
        p.setFont(_sans(36, True))
        p.drawText(QRectF(r.left() + 28, r.top() + 10, r.width() - 56, 54), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("util.lucky.scene.tray", a0=len(keys), a1=remain))
        area = QRectF(r.left() + 24, r.top() + 72, r.width() - 48, r.height() - 92)
        d = _fit_cell(len(keys), area.width(), area.height())
        cols = max(1, int(area.width() // d))
        ds = self.device_scale()
        for idx, k in enumerate(keys):
            row, col = divmod(idx, cols)
            pix = self.sprites.get(self._entry_label(k), self._ball_color(k), d / 2 - 2, ds)
            draw_sprite_centered(p, pix, area.left() + col * d + d / 2, area.top() + row * d + d / 2)

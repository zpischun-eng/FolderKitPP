# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 타이머/시계 [v45.0]

공항·기차역 안내판 스타일의 스플릿플랩(split-flap) 보드. 사용자와 함께
인터랙티브 HTML 목업을 여러 차례 다듬어(카드 재질감, 중력 가속 이징,
각도별 암전·반짝, 롤러 지지대) 확정한 디자인을 PySide6로 그대로 옮긴
것이다 — 애니메이션 상태 계산은 timer_solve.py(순수 로직, 화면 없이
테스트 가능)가 맡고, 이 파일은 QPainter로 그리는 것과 Qt 위젯(세그먼트
버튼, 프리셋, 시작/정지/리셋)만 담당한다.

- 시계 모드: 시:분:초 6자리, 화면을 꽉 채운다(전체화면 시 90%).
- 타이머 모드: 분:초 4자리를 위쪽에 크게, 프리셋·컨트롤은 아래쪽에.
- 세그먼트(시계/타이머) 버튼의 비활성 쪽은 "일시정지" 버튼과 같은
  채도 낮은 톤(BTN_NEUTRAL_BG)으로 — 선택 안 된 상태가 분명히 드러나게.
- 설명 문구(힌트·안내 텍스트)는 전부 뺐다 — 화면 자체로 충분히 쓸 수
  있게 만드는 게 목표였다.
"""
import math
import time as _time

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from ..i18n import tr
from ..styles import C, BTN_NEUTRAL_BG
from .base import MiniApp
from .anim_kit import AnimCanvas, FullscreenPresenter, LOGICAL_W, LOGICAL_H
from . import timer_solve as T
from . import ui_kit as UK

# ---------------------------------------------------------------- 카드 재질 색상
_CARD_TOP_GRAD = [(0.0, "#565b64"), (0.72, "#2c2f35"), (1.0, "#1a1c1f")]
_CARD_BOTTOM_GRAD = [(0.0, "#121315"), (0.28, "#22252a"), (1.0, "#4c515a")]
_BOARD_BG = "#7d838c"
_DIGIT_COLOR = "#f3f0e8"
_ROLLER_GRAD = [(0.0, "#0e0f11"), (0.38, "#9aa0a8"), (0.5, "#eef0f2"), (0.62, "#9aa0a8"), (1.0, "#0e0f11")]


def _half_gradient(rect, stops):
    grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    for pos, color in stops:
        grad.setColorAt(pos, QColor(color))
    return QBrush(grad)


def _draw_half(p, rect, number, is_top_half, brightness, font):
    """카드 한 쪽 절반(위 또는 아래)을 그린다 — 배경 그라데이션 + 숫자
    (전체 숫자를 그린 뒤 이 절반만 보이도록 clip) + 밝기 오버레이."""
    stops = _CARD_TOP_GRAD if is_top_half else _CARD_BOTTOM_GRAD
    p.fillRect(rect, _half_gradient(rect, stops))

    p.save()
    p.setClipRect(rect)
    full_h = rect.height() * 2
    top = rect.top() if is_top_half else rect.top() - rect.height()
    text_rect = QRectF(rect.left(), top, rect.width(), full_h)
    p.setPen(QColor(_DIGIT_COLOR))
    p.setFont(font)
    p.drawText(text_rect, Qt.AlignCenter, str(number))
    p.restore()

    if brightness < 1.0:
        alpha = max(0, min(255, int((1.0 - brightness) * 235)))
        p.fillRect(rect, QColor(0, 0, 0, alpha))
    elif brightness > 1.0:
        alpha = max(0, min(255, int((brightness - 1.0) * 130)))
        p.fillRect(rect, QColor(255, 255, 255, alpha))


def _draw_hinge(p, rect):
    y = rect.center().y()
    grad = QLinearGradient(rect.left(), y, rect.right(), y)
    grad.setColorAt(0.0, QColor(0, 0, 0, 190))
    grad.setColorAt(0.5, QColor(210, 214, 220, 165))
    grad.setColorAt(1.0, QColor(0, 0, 0, 190))
    p.fillRect(QRectF(rect.left(), y - 2, rect.width(), 4), QBrush(grad))


def _draw_roller(p, cx, cy, roller_h, roller_w):
    grad = QLinearGradient(cx, cy - roller_h / 2, cx, cy + roller_h / 2)
    for pos, color in _ROLLER_GRAD:
        grad.setColorAt(pos, QColor(color))
    p.fillRect(QRectF(cx - roller_w / 2, cy - roller_h / 2, roller_w, roller_h), QBrush(grad))


def draw_flip_card(p, rect, digit: T.FlipDigit, font):
    """자리 하나(FlipDigit)를 rect 안에 그린다 — 롤러(카드 "뒤") →
    고정판(아래→위) → 회전 중인 플랩 순서로, 실제 카드를 파고들지 않게
    롤러를 먼저 깐다."""
    cx, cy = rect.center().x(), rect.center().y()
    roller_h = rect.height() * 0.4
    roller_w = max(4.0, rect.width() * 0.09)
    _draw_roller(p, rect.left(), cy, roller_h, roller_w)
    _draw_roller(p, rect.right(), cy, roller_h, roller_w)

    half_h = rect.height() / 2
    top_rect = QRectF(rect.left(), rect.top(), rect.width(), half_h)
    bot_rect = QRectF(rect.left(), cy, rect.width(), half_h)

    animating = digit.is_animating
    angle = digit.angle() if animating else 0.0
    stator_top_num = digit.target if (animating and angle > 90) else digit.current
    stator_bot_num = digit.current if (animating and angle <= 90) else digit.target

    _draw_half(p, bot_rect, stator_bot_num, False, 1.0, font)
    _draw_half(p, top_rect, stator_top_num, True, 1.0, font)
    _draw_hinge(p, rect)

    if animating:
        scale_y = abs(math.cos(math.radians(angle)))
        brightness = digit.brightness()
        if angle <= 90:
            flap_num, flap_rect, is_top = digit.from_val, top_rect, True
        else:
            flap_num, flap_rect, is_top = digit.target, bot_rect, False
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, max(0.001, scale_y))
        p.translate(-cx, -cy)
        _draw_half(p, flap_rect, flap_num, is_top, brightness, font)
        p.restore()


# =============================================================================
class _SplitFlapCanvas(AnimCanvas):
    """시계·타이머 공용 보드. groups(자리 묶음들)와 그 사이 구분자(:)
    위치만 다르게 받아 그린다 — 시계는 [시시][분분][초초], 타이머는
    [분분][초초]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_color = QColor(_BOARD_BG)
        self.groups = []           # list[list[FlipDigit]]
        self._font = QFont("Impact")
        self._font.setStyleStrategy(QFont.PreferMatch)
        self._font.setWeight(QFont.Black)

    def set_groups(self, groups):
        self.groups = groups

    def advance(self, dt):
        for g in self.groups:
            for d in g:
                d.advance(dt)

    def paint_backdrop(self, p, ox, oy, scale):
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#9aa0a9"))
        grad.setColorAt(1.0, QColor("#7d838c"))
        p.fillRect(self.rect(), QBrush(grad))

    def paint_scene(self, p):
        if not self.groups:
            return
        n_digits = sum(len(g) for g in self.groups)
        n_groups = len(self.groups)
        n_seps = n_groups - 1
        gap = 10.0
        sep_ratio = 0.32   # 구분자(:) 폭 = card_w * sep_ratio — [v45.0] 시계(6자리)가
        # 가로 폭에 많이 묶여 있어, 간격·구분자 폭을 줄여 카드 자체를 더 키웠다.
        n_inner_gaps = n_digits - n_groups          # 같은 그룹 안의 digit 사이 간격 수
        n_sep_gaps = n_seps * 2                      # 구분자 좌우 간격 수

        # [v45.0] "훨씬 크게" 요청 반영 — 가로·세로 두 제약 중 더 작게
        # 나오는 쪽을 기준으로 삼아, 논리 좌표계(1600x900) 안에서 보드를
        # 최대한 꽉 채운다. (AnimCanvas는 항상 16:9로 클립하므로 — 실제
        # 위젯이 더 정사각형에 가까우면 위아래 레터박스가 남는 것 자체는
        # 공용 기반의 고정 사양이라 여기서 더 키울 수 없다. 전체화면
        # 모드에서는 모니터가 보통 16:9에 가까워 이 여백이 거의 없다.)
        available_w = LOGICAL_W * 0.95
        available_h = LOGICAL_H * 0.92
        fixed_gaps_w = n_inner_gaps * gap + n_sep_gaps * gap
        denom = n_digits + n_seps * sep_ratio
        card_w_by_w = max(40.0, (available_w - fixed_gaps_w) / denom)
        card_h_by_w = card_w_by_w / 0.74

        if card_h_by_w <= available_h:
            card_h, card_w = card_h_by_w, card_w_by_w
        else:
            card_h = available_h
            card_w = card_h * 0.74
        sep_w = card_w * sep_ratio

        total_w = n_digits * card_w + n_seps * sep_w + fixed_gaps_w
        x = (LOGICAL_W - total_w) / 2.0
        y = (LOGICAL_H - card_h) / 2.0
        self._font.setPixelSize(max(10, int(card_h * 0.78)))

        for gi, group in enumerate(self.groups):
            for di, digit in enumerate(group):
                rect = QRectF(x, y, card_w, card_h)
                draw_flip_card(p, rect, digit, self._font)
                x += card_w
                if di < len(group) - 1:
                    x += gap
            if gi < len(self.groups) - 1:
                p.setFont(self._font)
                p.setPen(QColor("#2a2d32"))
                sep_rect = QRectF(x, y, sep_w, card_h)
                p.drawText(sep_rect, Qt.AlignCenter, ":")
                x += sep_w + gap


# =============================================================================
class TimerClockWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.mode = "clock"   # 내부 키 — "clock" | "timer"
        self.total_sec = 300
        self.remain_sec = 300
        self.running = False

        self.clock_digits = [T.FlipDigit(0) for _ in range(6)]
        self.timer_digits = [T.FlipDigit(0) for _ in range(4)]
        self._set_timer_digits(self.remain_sec, animate=False)

        self._build_ui()
        self._clock_tick_timer = QTimer(self)
        self._clock_tick_timer.setInterval(1000)
        self._clock_tick_timer.timeout.connect(self._on_clock_tick)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        self._apply_mode()
        self._on_clock_tick()
        self._clock_tick_timer.start()
        self.retranslate()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        """[v45.0] 다른 미니앱들과 같은 통일 UI 규격(ui_kit.Card) 위에
        짓는다 — 세그먼트·전체화면 버튼은 카드 제목줄(툴바)에, 보드는
        본문 대부분을 차지하게, 타이머 컨트롤(프리셋·시작/정지/리셋)은
        그 아래에 작게 — 요청하신 "플립카드는 위, 컨트롤은 아래" 그대로다."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = UK.Card()
        outer.addWidget(self.card, 1)

        self.btn_seg_clock = UK.toggle_button(checked=True)
        self.btn_seg_timer = UK.toggle_button()
        self.btn_seg_clock.clicked.connect(lambda: self._set_mode("clock"))
        self.btn_seg_timer.clicked.connect(lambda: self._set_mode("timer"))
        self.card.add_tool(self.btn_seg_clock)
        self.card.add_tool(self.btn_seg_timer)
        self.btn_fullscreen = self.card.add_tool(UK.tool_button("\u26f6"))
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)

        self.canvas = _SplitFlapCanvas()
        self.canvas.exitFullscreenRequested.connect(self._exit_fullscreen)
        self.canvas.primaryRequested.connect(self._on_primary)
        self.presenter = FullscreenPresenter(self.canvas)
        self.card.add_body(UK.canvas_frame(self.canvas), 1)

        # ---- 타이머 전용 컨트롤(아래쪽, 보드보다 훨씬 작게) ----
        self.timer_controls = QWidget()
        tc = QVBoxLayout(self.timer_controls)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self.preset_buttons = []
        for minutes in (1, 3, 5, 10, 15):
            btn = UK.toggle_button()
            btn.setProperty("minutes", minutes)
            btn.setMinimumWidth(56)
            btn.clicked.connect(lambda _c=False, m=minutes, b=btn: self._on_preset(m, b))
            preset_row.addWidget(btn)
            self.preset_buttons.append(btn)
        tc.addLayout(preset_row)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self.btn_start = UK.primary_button()
        self.btn_pause = UK.neutral_button()
        self.btn_reset = UK.secondary_button()
        self.btn_start.clicked.connect(self._start_timer)
        self.btn_pause.clicked.connect(self._pause_timer)
        self.btn_reset.clicked.connect(self._reset_timer)
        self.btn_pause.setEnabled(False)
        ctrl_row.addWidget(self.btn_start)
        ctrl_row.addWidget(self.btn_pause)
        ctrl_row.addWidget(self.btn_reset)
        tc.addLayout(ctrl_row)

        self.card.add_body(self.timer_controls, 0)
        self._style_segment()

    # ---------------------------------------------------------------- 모드 전환
    def _set_mode(self, mode):
        if mode == self.mode:
            self.btn_seg_clock.setChecked(self.mode == "clock")
            self.btn_seg_timer.setChecked(self.mode == "timer")
            return
        self.mode = mode
        self.btn_seg_clock.setChecked(mode == "clock")
        self.btn_seg_timer.setChecked(mode == "timer")
        self._style_segment()
        self._apply_mode()

    def _apply_mode(self):
        is_timer = self.mode == "timer"
        self.timer_controls.setVisible(is_timer)
        self.canvas.set_groups(
            [self.timer_digits[0:2], self.timer_digits[2:4]] if is_timer
            else [self.clock_digits[0:2], self.clock_digits[2:4], self.clock_digits[4:6]]
        )

    def _style_segment(self):
        """[v45.0] 비활성 쪽은 "일시정지" 버튼과 같은 채도 낮은 톤
        (BTN_NEUTRAL_BG)으로 — 선택 상태가 더 분명히 드러난다.
        UK.toggle_button 바탕 스타일(테두리·크기)은 그대로 두고 배경·
        글자색만 켜짐/꺼짐에 맞춰 덮어쓴다."""
        for btn, on in ((self.btn_seg_clock, self.mode == "clock"),
                       (self.btn_seg_timer, self.mode == "timer")):
            bg = C.UTIL_MAIN if on else BTN_NEUTRAL_BG
            btn.setStyleSheet(
                f"QPushButton{{background:{bg};color:#ffffff;font-weight:bold;"
                f"border:1px solid {bg};border-radius:4px;padding:0 16px;}}"
                f"QPushButton:checked{{background:{bg};color:#ffffff;}}")

    # ---------------------------------------------------------------- 시계
    def _on_clock_tick(self):
        t = _time.localtime()
        vals = [t.tm_hour, t.tm_min, t.tm_sec]
        first = not any(d.progress < 1.0 or d.current for d in self.clock_digits) and \
            self.clock_digits[0].current == 0 and self._clock_virgin()
        for i, v in enumerate(vals):
            tens, ones = divmod(v, 10)
            for di, dv in ((0, tens), (1, ones)):
                digit = self.clock_digits[i * 2 + di]
                if first:
                    digit.set_immediate(dv)
                else:
                    # [주의] 시계는 항상 1초씩만 흐르므로 한 번만 넘어가면
                    # 된다 — flip_sequence_to(촤라락, 여러 번 연속)를 쓰면
                    # 안 된다(특히 초가 59->0으로 "내려갈" 때 체감상 9바퀴
                    # 가까이 도는 심각한 버그가 된다).
                    digit.flip_to(dv)

    def _clock_virgin(self):
        if getattr(self, "_clock_initialized", False):
            return False
        self._clock_initialized = True
        return True

    # ---------------------------------------------------------------- 타이머
    def _set_timer_digits(self, seconds, animate=True, sequence=False):
        """[v45.0] sequence=True면 "촤라락"(지금 값에서 목표까지 1씩
        연속으로) 효과 — 프리셋·리셋처럼 값이 크게 뛸 때 쓴다.
        sequence=False(기본)는 한 번만 넘어간다 — 매초 1씩 줄어드는
        보통의 카운트다운에 쓴다(촤라락을 쓰면 59->58처럼 "내려가는"
        변화가 뒤로 한 바퀴 거의 다 도는 것으로 계산돼 버린다)."""
        mm = min(99, seconds // 60)
        ss = seconds % 60
        vals = T.digits_for_value(mm, 2) + T.digits_for_value(ss, 2)
        for digit, v in zip(self.timer_digits, vals):
            if not animate:
                digit.set_immediate(v)
            elif sequence:
                digit.flip_sequence_to(v)
            else:
                digit.flip_to(v)

    def _on_preset(self, minutes, clicked_btn):
        for b in self.preset_buttons:
            b.setChecked(b is clicked_btn)
        self._pause_timer()
        self.total_sec = minutes * 60
        self.remain_sec = self.total_sec
        self._set_timer_digits(self.remain_sec, animate=True, sequence=True)

    def _start_timer(self):
        if self.running or self.remain_sec <= 0:
            return
        self.running = True
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self._countdown_timer.start()

    def _pause_timer(self):
        self.running = False
        self._countdown_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)

    def _reset_timer(self):
        self._pause_timer()
        self.remain_sec = self.total_sec
        self._set_timer_digits(self.remain_sec, animate=True, sequence=True)

    def _on_countdown_tick(self):
        if self.remain_sec > 0:
            self.remain_sec -= 1
            self._set_timer_digits(self.remain_sec, animate=True)
            if self.remain_sec == 0:
                self._pause_timer()

    def _on_primary(self):
        """스페이스바(발표 리모컨) — 타이머 모드에서 시작/일시정지 토글."""
        if self.mode != "timer":
            return
        self._pause_timer() if self.running else self._start_timer()

    # ---------------------------------------------------------------- 전체화면
    def _toggle_fullscreen(self):
        self.presenter.title = tr("util.timerclock.title")
        self.presenter.toggle()

    def _exit_fullscreen(self):
        if self.presenter.active:
            self.presenter.exit()

    # ---------------------------------------------------------------- 수명주기
    def has_unsaved(self):
        return False

    def retranslate(self):
        self.card.set_title(tr("util.timerclock.title"))
        self.btn_seg_clock.setText(tr("util.timerclock.seg_clock"))
        self.btn_seg_timer.setText(tr("util.timerclock.seg_timer"))
        self.btn_start.setText(tr("util.timerclock.btn_start"))
        self.btn_pause.setText(tr("util.timerclock.btn_pause"))
        self.btn_reset.setText(tr("util.timerclock.btn_reset"))
        for b in self.preset_buttons:
            minutes = b.property("minutes")
            b.setText(tr("util.timerclock.preset_min", a0=minutes))


# =============================================================================
class TimerClockApp(MiniApp):
    id = "timerclock"
    icon = "timerclock"
    category = "misc"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = TimerClockWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


def _t(ko, en, ja):
    return {"ko": ko, "en": en, "ja": ja}


TRANSLATIONS = {
    "util.timerclock.title": _t("타이머", "Timer", "タイマー"),
    "util.timerclock.desc": _t(
        "공항·기차역 안내판 스타일의 스플릿플랩 보드 — 시계 모드와 제한 시간 카운트다운 타이머 모드를 오갑니다.",
        "An airport/train-station style split-flap board — switch between a clock and a countdown timer.",
        "空港・駅の案内板スタイルのスプリットフラップボード — 時計モードとカウントダウンタイマーモードを切り替えます。"),
    "util.timerclock.seg_clock": _t("시계", "Clock", "時計"),
    "util.timerclock.seg_timer": _t("타이머", "Timer", "タイマー"),
    "util.timerclock.btn_start": _t("시작", "Start", "開始"),
    "util.timerclock.btn_pause": _t("일시정지", "Pause", "一時停止"),
    "util.timerclock.btn_reset": _t("리셋", "Reset", "リセット"),
    "util.timerclock.preset_min": _t("{a0}분", "{a0} min", "{a0}分"),
}

TimerClockApp.tr_table = TRANSLATIONS

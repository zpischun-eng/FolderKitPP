# -*- coding: utf-8 -*-
"""
FolderKit++ — 타이머/시계 미니앱 핵심 로직(GUI와 분리) [v45.0]

스플릿플랩(기차역·공항 안내판) 보드 한 자리(0~9)의 애니메이션 상태를
관리한다. 실제 그리기(QPainter)는 timerclock.py가 담당하고, 여기서는
"지금 몇 도 회전했는지, 그래서 어떤 숫자를 보여줘야 하는지, 얼마나
밝은지"만 계산한다 — 화면 없이도 헤드리스로 검증할 수 있게 하기
위함이다. 디자인은 사용자와 함께 HTML 목업(스플릿플랩 보드, 각도별
암전/반짝, 중력 가속)으로 여러 차례 다듬은 것을 그대로 옮긴 것이다.
"""

FLIP_DURATION = 0.9       # 초 — 매초 카운트다운처럼 "한 번만" 넘어갈 때 쓰는 속도
FAST_FLIP_DURATION = 0.1  # 초 — [v45.1] 프리셋·리셋처럼 여러 자리를 연속으로
# "촤라락" 넘길 때 쓰는 속도. 처음엔 FLIP_DURATION을 그대로 썼더니, 0분에서
# 15분으로 바꾸는 것처럼 여러 단계를 거칠 때 1초에 한 장씩 넘어가는 게
# 답답해 보인다는 지적을 받았다 — 목표 숫자가 나올 때까지 지체 없이 빠르게
# 훑고 지나가도록 훨씬 짧게 잡았다.


def ease_gravity(t):
    """중력 가속 느낌의 이징 — 처음엔 느리다가 끝에 급격히 빨라진다.
    화면 목업에서 cubic-bezier(.65,0,.85,.35)로 확인한 곡선을 거듭제곱
    으로 근사했다(시각적으로 충분히 비슷하고 계산이 훨씬 가볍다)."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t ** 2.6


class FlipDigit:
    """자리 하나(0~9)의 애니메이션 상태. 연속으로 flip_to()를 여러 번
    부르면 큐에 쌓여 하나씩 순서대로 넘어간다("촤라락" 효과) — 예를 들어
    5에서 8로 가려면 6→7→8로 세 번 돈다. 큐의 각 항목은 (값, 그 한 걸음에
    걸릴 시간) 튜플이다 — [v45.1] 매초 카운트다운(한 걸음)과 프리셋·리셋
    (여러 걸음을 빠르게 훑고 지나감)의 속도가 서로 다르기 때문이다."""
    __slots__ = ("current", "target", "from_val", "progress", "queue", "duration")

    def __init__(self, value=0):
        self.current = value
        self.target = value
        self.from_val = value
        self.progress = 1.0   # 1.0 = 정지(애니메이션 없음)
        self.queue = []       # list[(value, duration)]
        self.duration = FLIP_DURATION   # 지금 진행 중인 한 걸음의 소요 시간

    def set_immediate(self, n):
        """애니메이션 없이 즉시 값을 바꾼다(최초 표시 등에 쓴다)."""
        self.current = self.target = self.from_val = n
        self.progress = 1.0
        self.queue = []

    def flip_to(self, n, duration=None):
        """n으로 넘어가도록 예약한다. 이미 애니메이션 중이거나 대기열이
        있으면 뒤에 쌓인다. 지금 값과 같고 대기열도 비었으면 아무 일도
        안 한다(불필요한 애니메이션 방지). duration을 안 주면 보통 속도
        (FLIP_DURATION) — 매초 카운트다운처럼 "한 걸음"에 쓴다."""
        if n == self.current and not self.queue and self.progress >= 1.0:
            return
        self.queue.append((n, FLIP_DURATION if duration is None else duration))

    def advance(self, dt):
        """시간을 dt(초)만큼 흘려보낸다 — 매 프레임 호출."""
        if self.progress < 1.0:
            self.progress += dt / self.duration
            if self.progress >= 1.0:
                self.progress = 1.0
                self.current = self.target
        if self.progress >= 1.0 and self.queue:
            self.from_val = self.current
            self.target, self.duration = self.queue.pop(0)
            self.progress = 0.0

    @property
    def is_animating(self):
        return self.progress < 1.0 or bool(self.queue)

    @property
    def pending_value(self):
        """지금 "가고 있는" 값 — 대기열이 있으면 그 마지막 값, 애니메이션
        중이면 target, 둘 다 아니면 current. flip_sequence_to()가 연속
        호출될 때 "지금까지 예약된 마지막 지점"을 알기 위해 쓴다."""
        if self.queue:
            return self.queue[-1][0]
        if self.progress < 1.0:
            return self.target
        return self.current

    def flip_sequence_to(self, n, duration=FAST_FLIP_DURATION):
        """[v45.0] 목업에서 설계한 "촤라락" 효과 — 지금 가고 있는 값에서
        n까지 1씩 올리며(9->0 랩) 한 자리씩 순서대로 넘어가도록 예약한다
        (예: 0에서 5로 가면 1→2→3→4→5로 다섯 번 돈다). flip_to()처럼
        한 번에 건너뛰지 않는다. [v45.1] 기본 속도가 FAST_FLIP_DURATION
        (훨씬 빠름)이다 — 목표 숫자가 나올 때까지 지체 없이 훑고 지나가야
        하는 프리셋·리셋 전용이라, 매초 카운트다운(flip_to 기본 속도)과는
        다르게 움직인다."""
        val = self.pending_value
        steps = (n - val) % 10
        for _ in range(steps):
            val = (val + 1) % 10
            self.flip_to(val, duration=duration)

    def angle(self):
        """지금 회전각(도, 0~180) — 0=정지(앞면 그대로), 180=완전히
        다음 숫자로 넘어감."""
        return ease_gravity(self.progress) * 180.0

    def brightness(self):
        """[v45.0] 화면 목업에서 설계한 "회전 중반(약 45도·135도) 부근
        암전/반짝" 효과를 그대로 따른다. 전반부(0~90도)는 앞면(from_val)
        이 보이며 중반에 어두워지고, 후반부(90~180도)는 뒷면(target)이
        보이며 중반에 밝아진다. 1.0이 평상시 밝기다."""
        a = self.angle()
        if a <= 90:
            p = a / 90.0
            if p < 0.5:
                return 1.0 - p * 2 * 0.85        # 1.0 -> 0.15
            return 0.15 + (p - 0.5) * 2 * 0.25   # 0.15 -> 0.4
        p = (a - 90) / 90.0
        if p < 0.5:
            return 0.4 + p * 2 * 0.5             # 0.4 -> 0.9
        if p < 0.65:
            return 0.9 + (p - 0.5) / 0.15 * 1.7  # 0.9 -> 2.6 (반짝 피크)
        return 2.6 - (p - 0.65) / 0.35 * 1.6     # 2.6 -> 1.0


def digits_for_value(n, width):
    """정수 n을 width자리 숫자 리스트로 바꾼다(예: digits_for_value(5,2)
    -> [0,5]). 음수는 0으로 취급한다."""
    s = str(max(0, int(n))).rjust(width, "0")[-width:]
    return [int(c) for c in s]

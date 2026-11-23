# -*- coding: utf-8 -*-
"""
FolderKit++ — 애니메이션 미니앱 공용 물리/파티클 [v44] (순수 로직, Qt 의존 없음)

행운의 번호(추첨 드럼)와 응원의 메시지(화살·풍선)가 함께 쓴다. Qt를 전혀
import하지 않으므로 헤드리스 테스트에서 화면 없이 그대로 돌려 볼 수 있다.

설계 원칙
- **고정 시간 간격(fixed timestep)** 으로만 진행한다. 같은 시드·같은 입력
  스텝이면 (같은 PC에서) 항상 같은 결과가 나온다 — 추첨 "재현"의 근거.
- 난수는 호출부가 넘긴 random.Random 하나만 쓴다(전역 random 금지).
- numpy 없이 순수 파이썬으로 120개 공을 돌려야 하므로, 공의 상태를
  객체 대신 **평행 리스트**(xs, ys, vxs, vys)로 들고, 충돌 후보는 균일
  격자 공간 분할로 좁힌다.
"""
import math

PHYS_DT = 1.0 / 60.0          # 물리 한 스텝(초)


# =============================================================================
# 원형 드럼 안의 공들
# =============================================================================
def _ang_diff(a, b):
    """두 각도(라디안) 차이를 -π~π로 정규화."""
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


class DrumWorld:
    """원형 용기(드럼) 안에서 튀는 같은 크기의 공들.

    좌표는 "장면 좌표"(행운의 번호 캔버스의 논리 좌표, y가 아래로 증가)를
    그대로 쓴다 — 그리는 쪽이 따로 변환할 필요가 없게.

    [v44.1] 웹 목업으로 여러 차례 다듬은 뒤 정착한 방식 — "미는 힘"이 아니라
    **붙잡기(그립)** 방식이다. 드럼이 돌고 있을 때(spin_rate>0) 벽에 닿은
    공은 그 순간 벽(돌기)과 완전히 같은 각속도로 붙어 돌다가, 90도 안팎
    (70~100도, RELEASE_ARC_MIN~MAX)을 타고 오르면 자연스럽게 풀려나
    떨어진다. 풀려난 직후 벽 바로 옆에서 다시 붙잡히면 "계속 붙어있는"
    것처럼 보이므로, 벽에서 실제로 확실히 떨어져 나간 적(REATTACH_GUARD_K)이
    있어야만 다시 붙잡을 수 있게 막는다. 뽑기의 마지막 단계에서는 드럼이
    완전히 멈추고(spin_rate=0) 대신 아래에서 바람(wind)이 불어 공이
    팝콘처럼 자유롭게 날아다닌다 — 이때는 그립이 전혀 걸리지 않는다.
    """

    GRAVITY = 1100.0
    BALL_RESTITUTION = 0.95   # [v44.1] 0.86→0.95. 이 반발 공식에서 완전탄성(에너지 손실 0)의
                              # 이론적 최댓값이 1.0이라, 그보다 낮게 잡아야 절대 폭주하지 않는다.
    WALL_RESTITUTION = 0.65
    STUCK_BOUNCE = 1.8        # 붙잡힌(고정된) 공에 부딪힌 자유 공이 튕겨나가는 반발 계수
    DAMPING = 0.35            # 초당 속도 감쇠율
    MAX_SPEED = 2600.0
    SOLVER_ITERS = 3          # 겹침 해소 반복 — 쌓였을 때 공이 서로 파묻히지 않게
    RELEASE_ARC_MIN = math.radians(70)   # [v44.1] 붙잡힌 공이 풀려나는 각도 범위 — 90도 안팎
    RELEASE_ARC_MAX = math.radians(100)
    COOL_AFTER_RELEASE = 0.3             # 풀려난 뒤 이 시간(초) 동안은 다시 못 붙는다
    REATTACH_GUARD_K = 3.0               # + 벽에서 공 반지름의 이 배수만큼 안쪽으로 들어와야
                                          #   재부착 가능(짧게 붙었다 떼었다를 반복하며 계속
                                          #   붙어있는 것처럼 보이는 문제를 막는다)
    WIND_UP = 3000.0                     # 드럼이 멈춘 동안(뽑기 마지막 단계) 아래서 부는 바람
    WIND_SIDE = 650.0

    def __init__(self, cx, cy, radius, ball_radius, keys):
        self.cx, self.cy, self.R = float(cx), float(cy), float(radius)
        self.r = float(ball_radius)
        self.keys = list(keys)
        n = len(self.keys)
        self.xs = [0.0] * n
        self.ys = [0.0] * n
        self.vxs = [0.0] * n
        self.vys = [0.0] * n
        self.alive = [True] * n
        # [v44.1] 그립 상태 — stuck인 공은 ang가 벽을 따라 돌며 위치를 직접 정한다.
        self.stuck = [False] * n
        self.ang = [0.0] * n
        self.attach_ang = [0.0] * n
        self.release_arc = [0.0] * n
        self.cool = [0.0] * n
        self.can_reattach = [True] * n
        self.wind_phase = [0.0] * n   # [v44.1] 공마다 다른 바람 위상(아래 randomize_wind_phase 참고)

    # ------------------------------------------------------------ 배치
    def lay_out(self, rng):
        """공을 드럼 바닥부터 육각 배치로 쌓는다. 어떤 공이 어느 자리에
        놓일지는 rng로 섞는다 — 번호순으로 쌓으면 "처음 위쪽에 있던
        번호가 유리하다"는 의심을 살 수 있으므로."""
        order = list(range(len(self.keys)))
        rng.shuffle(order)
        r = self.r
        slots = []
        row = 0
        y = self.cy + self.R - r - 1
        while len(slots) < len(order) and y > self.cy - self.R + r:
            half = math.sqrt(max(0.0, (self.R - r - 1) ** 2 - (y - self.cy) ** 2))
            x = self.cx - half + (r if row % 2 else 0.0)
            while x <= self.cx + half and len(slots) < len(order):
                slots.append((x, y))
                x += 2 * r + 0.5
            y -= r * math.sqrt(3) + 0.5
            row += 1
        while len(slots) < len(order):   # 이론상 오지 않음(면적 비율로 반지름을 정함)
            slots.append((self.cx + rng.uniform(-10, 10), self.cy + rng.uniform(-10, 10)))
        for idx, (x, y) in zip(order, slots):
            self.xs[idx], self.ys[idx] = x, y
            self.vxs[idx] = self.vys[idx] = 0.0

    def quantize(self):
        """상태를 소수 둘째 자리로 맞춘다 — 회차 시작 시점의 상태를 JSON에
        남겼다가 똑같이 되살리기 위해(재현)."""
        for arr in (self.xs, self.ys, self.vxs, self.vys):
            for i, v in enumerate(arr):
                arr[i] = round(v, 2)

    def snapshot(self):
        return [[k, self.xs[i], self.ys[i], self.vxs[i], self.vys[i]]
                for i, k in enumerate(self.keys) if self.alive[i]]

    @classmethod
    def from_snapshot(cls, cx, cy, radius, ball_radius, snap):
        w = cls(cx, cy, radius, ball_radius, [row[0] for row in snap])
        for i, row in enumerate(snap):
            w.xs[i], w.ys[i], w.vxs[i], w.vys[i] = (float(v) for v in row[1:5])
        return w

    def randomize_wind_phase(self, rng):
        """[v44.1] 바람 위상을 공마다 다시 무작위로 정한다. 예전엔 배열
        인덱스(i*1.7)를 그대로 위상으로 썼는데, 그러면 "같은 번호는 매
        회차 항상 같은 바람 위상"이 되어 공정성 검증에서 눈에 띄는 편향이
        나왔다(카이제곱 검정 실패) — 회차마다(뽑기 시작 시) 다시 뽑는다."""
        self.wind_phase = [rng.uniform(0.0, 2 * math.pi) for _ in self.keys]

    # ------------------------------------------------------------ 진행
    def step(self, dt, rng, spin_rate=0.0, wind=0.0, wind_t=0.0, suction=None):
        """한 스텝 진행.

        spin_rate: 지금 드럼이 도는 각속도(rad/s). 0보다 크면 벽에 닿은 자유
            공이 그 순간 벽과 같은 속도로 붙잡힌다(그립).
        wind: 0~1, 드럼이 멈춘 동안(spin_rate=0) 아래서 부는 바람의 세기.
        wind_t: 바람의 흔들림(사인파) 계산에 쓰는 누적 시간(초).
        suction: (px, py, 세기) 또는 None — 포트 흡입.
        반환값: 이번 스텝에 흡입구로 들어간 공의 인덱스(없으면 None).
        """
        n = len(self.keys)
        g = self.GRAVITY
        damp = max(0.0, 1.0 - self.DAMPING * dt)
        R, r = self.R, self.r
        rad = R - r
        spinning = spin_rate > 0.01
        xs, ys, vxs, vys, alive = self.xs, self.ys, self.vxs, self.vys, self.alive
        stuck, ang, attach_ang = self.stuck, self.ang, self.attach_ang
        release_arc, cool, can_reattach = self.release_arc, self.cool, self.can_reattach

        for i in range(n):
            if not alive[i]:
                continue
            if cool[i] > 0.0:
                cool[i] = max(0.0, cool[i] - dt)
            if stuck[i]:
                if spinning:
                    ang[i] += spin_rate * dt
                    nx, ny = math.cos(ang[i]), math.sin(ang[i])
                    vxs[i] = -ny * spin_rate * rad
                    vys[i] = nx * spin_rate * rad
                    xs[i] = self.cx + nx * rad
                    ys[i] = self.cy + ny * rad
                    if abs(_ang_diff(ang[i], attach_ang[i])) > release_arc[i]:
                        stuck[i] = False
                        cool[i] = self.COOL_AFTER_RELEASE
                        can_reattach[i] = False
                    continue
                stuck[i] = False   # 드럼이 멈췄다 — 그립을 풀어준다(팝콘 단계)
            ax, ay = 0.0, g
            if wind > 0:
                # [버그 수정] 흡입 중엔 바람을 약하게 줄였더니, 아직 흡입
                # 사정거리 밖에 있는 공은 중력에 눌려 다시는 안 올라와
                # "영원히 흡입만 기다리는" 정지 상태에 빠질 수 있었다(특히
                # 빠르게 속도에서 재현됨). 흡입 중에도 바람을 그대로 세게
                # 유지한다 — 가까이 오면 흡입력이 지역적으로 훨씬 강하므로
                # (거리 0에서 power 그대로) 여전히 확실하게 붙잡힌다.
                ay -= self.WIND_UP * (0.65 + 0.45 * math.sin(wind_t * 6 + self.wind_phase[i]))
                ax += math.sin(wind_t * 3.3 + self.wind_phase[i] * 1.3) * self.WIND_SIDE
            if suction is not None:
                px, py, power = suction
                dx, dy = px - xs[i], py - ys[i]
                d2 = dx * dx + dy * dy
                reach = (R * 0.62) ** 2
                if d2 < reach:
                    d = math.sqrt(d2) or 1.0
                    f = power * (1.0 - d2 / reach)
                    ax += dx / d * f
                    ay += dy / d * f
            vx = (vxs[i] + ax * dt) * damp
            vy = (vys[i] + ay * dt) * damp
            sp = math.hypot(vx, vy)
            if sp > self.MAX_SPEED:
                vx, vy = vx / sp * self.MAX_SPEED, vy / sp * self.MAX_SPEED
            vxs[i], vys[i] = vx, vy
            xs[i] += vx * dt
            ys[i] += vy * dt
            if not can_reattach[i] and math.hypot(xs[i] - self.cx, ys[i] - self.cy) < R - r * self.REATTACH_GUARD_K:
                can_reattach[i] = True

        for _it in range(self.SOLVER_ITERS):
            self._collide_balls()
            self._collide_wall()
        self._try_attach(spin_rate, rng)

        if suction is not None:
            px, py, _p = suction
            cap = (r * 1.3) ** 2
            best, best_d = None, None
            for i in range(n):
                if not alive[i]:
                    continue
                d2 = (xs[i] - px) ** 2 + (ys[i] - py) ** 2
                if d2 < cap and (best_d is None or d2 < best_d):
                    best, best_d = i, d2
            if best is not None:
                alive[best] = False
                self.stuck[best] = False
                return best
        return None

    def _try_attach(self, spin_rate, rng):
        """드럼이 돌고 있을 때, 벽에 붙어 쉬고 있는(정착한) 자유 공을
        붙잡는다 — 충돌 해소가 다 끝난 뒤 한 번만 판정한다."""
        if spin_rate <= 0.01:
            return
        R, r, cx, cy = self.R, self.r, self.cx, self.cy
        lim = R - r
        xs, ys, alive = self.xs, self.ys, self.alive
        stuck, cool, can_reattach = self.stuck, self.cool, self.can_reattach
        for i in range(len(xs)):
            if not alive[i] or stuck[i] or cool[i] > 0.0 or not can_reattach[i]:
                continue
            dx, dy = xs[i] - cx, ys[i] - cy
            if math.hypot(dx, dy) >= lim - 0.75:
                stuck[i] = True
                self.ang[i] = math.atan2(dy, dx)
                self.attach_ang[i] = self.ang[i]
                self.release_arc[i] = rng.uniform(self.RELEASE_ARC_MIN, self.RELEASE_ARC_MAX)

    def _collide_balls(self):
        r = self.r
        cell = 2.0 * r
        grid = {}
        xs, ys, vxs, vys, alive = self.xs, self.ys, self.vxs, self.vys, self.alive
        for i in range(len(xs)):
            if alive[i]:
                key = (int(xs[i] // cell), int(ys[i] // cell))
                grid.setdefault(key, []).append(i)
        diam2 = (2 * r) ** 2
        e = self.BALL_RESTITUTION
        stuck = self.stuck
        # 각 칸은 자기 칸 + 오른쪽/아래쪽 이웃 4칸만 본다 — 쌍을 두 번 검사하지 않게.
        for (gx, gy), members in grid.items():
            for ox, oy in ((0, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                other = members if (ox, oy) == (0, 0) else grid.get((gx + ox, gy + oy))
                if not other:
                    continue
                same = other is members
                for a_i, a in enumerate(members):
                    xa, ya = xs[a], ys[a]
                    for b in (members[a_i + 1:] if same else other):
                        dx = xs[b] - xa
                        dy = ys[b] - ya
                        d2 = dx * dx + dy * dy
                        if d2 >= diam2 or d2 == 0.0:
                            continue
                        d = math.sqrt(d2)
                        nx, ny = dx / d, dy / d
                        if stuck[a] or stuck[b]:
                            # 붙잡힌 공은 고정 장애물처럼 다룬다 — 자유 공만 완전히 밀어내며 튕겨나간다.
                            s, f = (a, b) if stuck[a] else (b, a)
                            fdx, fdy = xs[f] - xs[s], ys[f] - ys[s]
                            fd = math.hypot(fdx, fdy) or 1.0
                            fnx, fny = fdx / fd, fdy / fd
                            xs[f] = xs[s] + fnx * 2 * r
                            ys[f] = ys[s] + fny * 2 * r
                            rel_n = (vxs[f] - vxs[s]) * fnx + (vys[f] - vys[s]) * fny
                            if rel_n < 0:
                                imp = -rel_n * self.STUCK_BOUNCE
                                vxs[f] += imp * fnx
                                vys[f] += imp * fny
                            xa, ya = xs[a], ys[a]
                            continue
                        push = (2 * r - d) * 0.5
                        xs[a] -= nx * push
                        ys[a] -= ny * push
                        xs[b] += nx * push
                        ys[b] += ny * push
                        xa, ya = xs[a], ys[a]
                        rel = (vxs[b] - vxs[a]) * nx + (vys[b] - vys[a]) * ny
                        if rel < 0:
                            j = -(1 + e) * rel * 0.5
                            vxs[a] -= j * nx
                            vys[a] -= j * ny
                            vxs[b] += j * nx
                            vys[b] += j * ny

    def _collide_wall(self):
        R, r, cx, cy = self.R, self.r, self.cx, self.cy
        lim = R - r
        e = self.WALL_RESTITUTION
        xs, ys, vxs, vys = self.xs, self.ys, self.vxs, self.vys
        for i in range(len(xs)):
            if not self.alive[i] or self.stuck[i]:
                continue
            dx, dy = xs[i] - cx, ys[i] - cy
            d = math.hypot(dx, dy)
            if d > lim and d > 0:
                nx, ny = dx / d, dy / d
                xs[i] = cx + nx * lim
                ys[i] = cy + ny * lim
                vn = vxs[i] * nx + vys[i] * ny
                if vn > 0:
                    vxs[i] -= (1 + e) * vn * nx
                    vys[i] -= (1 + e) * vn * ny

    def alive_indices(self):
        return [i for i, a in enumerate(self.alive) if a]


def ball_radius_for(count, drum_radius, fill_ratio=0.36, max_ratio=0.16):
    """드럼 면적 대비 공 면적이 fill_ratio가 되도록 공 반지름을 정한다.
    인원이 적을 때 공이 지나치게 커지지 않게 드럼 반지름의 max_ratio로 상한."""
    count = max(1, int(count))
    r = drum_radius * math.sqrt(fill_ratio / count)
    return min(r, drum_radius * max_ratio)


# =============================================================================
# 파티클(터짐·색종이)
# =============================================================================
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "age", "size", "color", "spin", "angle", "kind")

    def __init__(self, x, y, vx, vy, life, size, color, kind="dot", spin=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.age = life, 0.0
        self.size, self.color, self.kind = size, color, kind
        self.spin, self.angle = spin, 0.0


class ParticleSystem:
    GRAVITY = 700.0
    MAX = 600

    def __init__(self):
        self.items = []

    def burst(self, rng, x, y, colors, count=40, speed=(200, 650), life=(0.6, 1.4),
              size=(3, 7), kind="dot"):
        for _ in range(count):
            a = rng.uniform(0, 2 * math.pi)
            s = rng.uniform(*speed)
            self.items.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s - 120,
                                       rng.uniform(*life), rng.uniform(*size),
                                       colors[rng.randrange(len(colors))], kind,
                                       rng.uniform(-9, 9)))
        if len(self.items) > self.MAX:
            del self.items[:len(self.items) - self.MAX]

    def step(self, dt):
        keep = []
        for p in self.items:
            p.age += dt
            if p.age >= p.life:
                continue
            p.vy += self.GRAVITY * dt
            p.vx *= (1 - 0.8 * dt)
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            keep.append(p)
        self.items = keep

    def clear(self):
        self.items = []


# =============================================================================
# 기하 도우미
# =============================================================================
def segment_hits_ellipse(x0, y0, x1, y1, cx, cy, rx, ry):
    """선분 (x0,y0)-(x1,y1)이 타원(중심 cx,cy, 반지름 rx,ry)과 만나는지.
    화살이 한 스텝에 풍선을 "뚫고 지나가" 판정을 놓치지 않도록 점이 아니라
    선분으로 검사한다(타원을 단위원으로 늘려서 선분-원 교차로 푼다)."""
    ax, ay = (x0 - cx) / rx, (y0 - cy) / ry
    bx, by = (x1 - cx) / rx, (y1 - cy) / ry
    dx, dy = bx - ax, by - ay
    a = dx * dx + dy * dy
    if a == 0:
        return ax * ax + ay * ay <= 1.0
    t = -(ax * dx + ay * dy) / a
    t = max(0.0, min(1.0, t))
    px, py = ax + dx * t, ay + dy * t
    return px * px + py * py <= 1.0


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def polyline_point(points, t):
    """꺾은선 위에서 전체 길이 비율 t(0~1) 지점의 좌표."""
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0]
    segs = []
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        segs.append(L)
        total += L
    target = max(0.0, min(1.0, t)) * total
    for (p0, p1), L in zip(zip(points, points[1:]), segs):
        if target <= L or L == 0:
            f = 0.0 if L == 0 else target / L
            return p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
        target -= L
    return points[-1]

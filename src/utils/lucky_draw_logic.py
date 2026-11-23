# -*- coding: utf-8 -*-
"""
FolderKit++ — 행운의 번호 [v44.2] 순수 로직 (Qt 의존 없음)

- 추첨 풀(번호 범위·명단), 결석 제외, 당첨자 제외/복원 추첨, 조합 뽑기
- 연출 "코어 챔버"(drum) 하나만 쓴다(이진 라우터는 목업 검토 결과 효과가
  낮다고 판단해 v44.1에서 뺐다). 물리 시뮬레이션이 실제로 결과를 정한다 —
  뽑기를 누르면 [섞기 → 감속(완전 정지) → 바람으로 날림 → PORT 흡입]
  4단계를 거쳐 흡입구에 **먼저 빨려 들어간 공**이 당첨된다. 이 흐름은
  전부 정해진 시간(SPEED_PROFILE)으로만 진행되는 결정적 상태기계라,
  회차 시작 상태(공 위치)와 시드만 기록해 두면 그대로 재현된다 — 사용자가
  버튼을 누른 "시점"은 결과에 영향을 주지 않는다(진행 중 사람이 끼어들
  여지가 없어졌기 때문).
- 번호표 발급, 기록 CSV, 세션 JSON 저장/불러오기

화면 문구는 하나도 갖고 있지 않다 — 여기서 쓰는 값은 전부 언어와 무관한
내부 키다(draw_type "range"/"roster"/"combo"/"ticket", speed
"fast"/"normal"/"dramatic", theme "stadium"/"night"/"classic",
드럼 단계 "idle"/"mixing"/"slowdown"/"wind", 포트 하위 단계
"closed"/"countdown"/"opening"/"sucking"/"closing"/"holding").
"""
import csv
import json
import math
import random as _random
import secrets
from datetime import datetime

from .anim_physics import DrumWorld, ball_radius_for, PHYS_DT

MAX_ENTRIES = 120

DRAW_TYPES = ("range", "roster", "combo", "ticket")
SPEEDS = ("fast", "normal", "dramatic")
THEMES = ("stadium", "night", "classic")

# 뽑기 한 번의 각 단계별 길이(초). 속도 설정에 따라 전체를 늘리고 줄인다.
# mix: 빠르게 섞는 시간 / slowdown: 완전히 멈출 때까지 감속하는 시간 /
# countdown: 멈춘 채 바람만 부는 동안 PORT가 점점 빠르게 깜빡이는 시간 /
# open: 문이 열리는 시간 / close: 공을 붙잡은 뒤 문이 닫히는 시간 /
# hold: 닫힌 채로 서서히 사라지는 시간(이 동안 드럼은 평소 속도로 다시 돈다).
SPEED_PROFILE = {
    "fast":     {"mix": 0.8, "slowdown": 0.35, "countdown": 0.8, "open": 0.10, "close": 0.12, "hold": 0.35},
    "normal":   {"mix": 1.3, "slowdown": 0.55, "countdown": 1.3, "open": 0.12, "close": 0.16, "hold": 0.50},
    "dramatic": {"mix": 2.2, "slowdown": 0.85, "countdown": 2.0, "open": 0.16, "close": 0.20, "hold": 0.70},
}

# 드럼 장면 좌표(행운의 번호 캔버스의 논리 좌표 1600x900 기준)
DRUM_CX, DRUM_CY, DRUM_R = 470.0, 440.0, 330.0
SPIN_FAST = 5.4     # rad/s — 섞을 때 회전 속도
SPIN_IDLE = 1.0     # rad/s — 평소(대기)에도 이 속도로 계속 돈다
SUCTION_POWER = 3000.0


def _ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def new_seed():
    """회차 시드 — 운영체제 난수원(secrets)에서 만든다."""
    return secrets.randbits(63)


# =============================================================================
# 추첨 대상
# =============================================================================
class Entry:
    __slots__ = ("key", "no", "name", "sub")

    def __init__(self, key, no, name="", sub=""):
        self.key = key      # 내부 식별자(저장·비교 전용)
        self.no = int(no)   # 공에 적히는 번호
        self.name = name    # 명단 추첨일 때 이름(번호 범위면 "")
        self.sub = sub      # 보조 정보(학년-반-번호 등)

    def to_dict(self):
        return {"key": self.key, "no": self.no, "name": self.name, "sub": self.sub}

    @classmethod
    def from_dict(cls, d):
        return cls(d["key"], d.get("no", 0), d.get("name", ""), d.get("sub", ""))


def range_entries(start, end):
    start, end = int(start), int(end)
    if end < start:
        start, end = end, start
    end = min(end, start + MAX_ENTRIES - 1)
    return [Entry(f"n{n}", n) for n in range(start, end + 1)]


def roster_entries(students):
    """대진표·좌석표 공용 명단(Student 목록) → 추첨 대상. 공에는 1번부터
    순서대로 번호를 붙인다(명단 번호가 반마다 겹칠 수 있으므로)."""
    out = []
    for i, s in enumerate(students[:MAX_ENTRIES], start=1):
        sub = "-".join(str(v) for v in (s.grade, s.cls, s.num) if str(v))
        out.append(Entry(f"s:{s.sid}", i, s.name, sub))
    return out


def name_list_entries(names):
    """붙여 넣은 이름 목록(한 줄에 한 명) → 추첨 대상. 빈 줄은 건너뛴다."""
    clean = [n.strip() for n in names if n and n.strip()]
    return [Entry(f"p{i}:{nm}", i, nm) for i, nm in enumerate(clean[:MAX_ENTRIES], start=1)]


def color_bucket(entry_index, total, buckets=6):
    """번호대별 색 구간(0~buckets-1) — 인원 수에 맞춰 자동으로 나눈다."""
    if total <= 0:
        return 0
    size = max(1, math.ceil(total / buckets))
    return min(buckets - 1, entry_index // size)


# =============================================================================
# 세션(한 행사·한 수업의 추첨 전체)
# =============================================================================
class DrawSession:
    def __init__(self, entries=None, draw_type="range", exclude_winners=True):
        self.entries = list(entries or [])
        self.draw_type = draw_type
        self.exclude_winners = exclude_winners
        self.excluded = set()        # 결석·제외(체크 해제) 대상 키
        self.drawn = []              # 지금까지 당첨된 키(순서대로, 이번 세션 전체)
        self.combo_current = []      # 조합 뽑기에서 지금 만들고 있는 조합
        self.rounds = []             # 기록(dict 목록)
        self.combos = []             # 완성된 조합들 [{"label":..., "numbers":[...]}]
        self.created = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # ------------------------------------------------------------ 조회
    def by_key(self):
        return {e.key: e for e in self.entries}

    def index_of(self, key):
        for i, e in enumerate(self.entries):
            if e.key == key:
                return i
        return -1

    def available_keys(self):
        """지금 뽑을 수 있는 대상(순서 = entries 순서)."""
        if self.draw_type == "combo":
            blocked = set(self.combo_current)
        elif self.exclude_winners:
            blocked = set(self.drawn)
        else:
            blocked = set()
        return [e.key for e in self.entries if e.key not in self.excluded and e.key not in blocked]

    # ------------------------------------------------------------ 기록
    def record(self, key, label="", seed=None, replay=None):
        """당첨 하나를 기록한다. replay는 재현에 필요한 정보(회차 시작
        상태 스냅숏 + 공 반지름 + 속도 설정 — 이것만 있으면 전 과정이
        결정적으로 그대로 재생된다)."""
        if self.draw_type == "combo":
            self.combo_current.append(key)
        self.drawn.append(key)
        e = self.by_key().get(key)
        rec = {
            "label": label,
            "order": len(self.drawn),
            "key": key,
            "no": e.no if e else None,
            "name": e.name if e else "",
            "seed": seed,
            "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "replay": replay,
        }
        self.rounds.append(rec)
        return rec

    def finish_combo(self):
        """조합 하나를 마무리하고, 정렬된 번호 목록을 돌려준다."""
        by = self.by_key()
        combo = sorted(by[k].no for k in self.combo_current if k in by)
        label = self.rounds[-1].get("label", "") if self.rounds else ""
        self.combos.append({"label": label, "numbers": combo})
        self.combo_current = []
        return combo

    def reset_draws(self):
        self.drawn = []
        self.combo_current = []
        self.rounds = []
        self.combos = []

    # ------------------------------------------------------------ 저장
    def to_dict(self):
        return {
            "schema": 1,
            "created": self.created,
            "draw_type": self.draw_type,
            "exclude_winners": self.exclude_winners,
            "entries": [e.to_dict() for e in self.entries],
            "excluded": sorted(self.excluded),
            "drawn": list(self.drawn),
            "combo_current": list(self.combo_current),
            "rounds": self.rounds,
            "combos": self.combos,
        }

    @classmethod
    def from_dict(cls, d):
        s = cls([Entry.from_dict(x) for x in d.get("entries", [])],
                d.get("draw_type", "range"), bool(d.get("exclude_winners", True)))
        s.excluded = set(d.get("excluded", []))
        s.drawn = list(d.get("drawn", []))
        s.combo_current = list(d.get("combo_current", []))
        s.rounds = list(d.get("rounds", []))
        s.combos = list(d.get("combos", []))
        s.created = d.get("created", s.created)
        return s


def save_session(path, session):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, ensure_ascii=False, indent=1)


def load_session(path):
    with open(path, encoding="utf-8") as f:
        return DrawSession.from_dict(json.load(f))


def export_rounds_csv(path, session, headers):
    """기록을 CSV로 내보낸다. headers는 호출부가 현재 언어로 넘긴다
    (회차 이름, 순서, 번호, 이름, 시각, 시드). 엑셀에서 한글이 깨지지
    않도록 BOM을 붙인다(utf-8-sig)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in session.rounds:
            w.writerow([r.get("label", ""), r.get("order", ""), r.get("no", ""), r.get("name", ""),
                        r.get("at", ""), r.get("seed", "")])


# =============================================================================
# 번호표 발급
# =============================================================================
def assign_tickets(entries, rng=None):
    """명단 전원에게 서로 다른 번호(1~N)를 무작위로 하나씩 준다.
    반환: [(번호표, Entry), ...] — 번호표 순."""
    rng = rng or _random.SystemRandom()
    numbers = list(range(1, len(entries) + 1))
    rng.shuffle(numbers)
    pairs = sorted(zip(numbers, entries), key=lambda p: p[0])
    return pairs


def export_tickets_csv(path, pairs, headers):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for ticket, e in pairs:
            w.writerow([ticket, e.name or e.no, e.sub])

# =============================================================================
# 코어 챔버(물리 드럼) — 유일한 연출 모드
# =============================================================================
class DrumSim:
    """한 회차의 드럼 시뮬레이션. 결과는 물리가 정한다.

    [v44.1] 사람이 "섞기"와 "뽑기"를 따로 누르던 방식을 버리고, 뽑기 한
    번으로 [섞기 → 감속(완전 정지) → 바람으로 날림 → PORT 흡입]까지 전부
    정해진 시간(SPEED_PROFILE)에 맞춰 자동으로 진행한다. 사람이 끼어들
    여지가 없는 결정적 상태기계이므로, `start_draw()`를 부른 그 순간의
    공 배치(스냅숏) + 시드만 있으면 그대로 재현된다.

    드럼 물리 자체(붙잡기·풀림·바람)는 `anim_physics.DrumWorld`가 맡는다.
    """

    def __init__(self, keys, seed, snapshot=None, ball_radius=None, total_count=None, speed="normal"):
        self.seed = seed
        self.rng = _random.Random(seed)
        total = total_count or len(keys)
        self.ball_r = ball_radius or ball_radius_for(total, DRUM_R)
        if snapshot:
            self.world = DrumWorld.from_snapshot(DRUM_CX, DRUM_CY, DRUM_R, self.ball_r, snapshot)
        else:
            self.world = DrumWorld(DRUM_CX, DRUM_CY, DRUM_R, self.ball_r, keys)
            self.world.lay_out(self.rng)
        self.world.quantize()
        self.rng = _random.Random(seed)   # 배치에 난수를 썼든 안 썼든 진행용 난수는 같은 지점에서 시작
        self.speed = speed if speed in SPEED_PROFILE else "normal"

        self.sim_t = 0.0
        self.phase = "idle"        # idle | mixing | slowdown | wind
        self.phase_t = 0.0
        self.port_sub = "closed"   # closed | countdown | opening | sucking | closing | holding
        self.sub_t = 0.0
        self.door = 0.0            # 0=닫힘 1=열림
        self.blink = 0.0
        self.spin_level = SPIN_IDLE / SPIN_FAST

        self.winner = None
        self.winner_pos = None     # 잡힌 순간의 (x, y) — 장면이 캡슐로 스냅하는 애니메이션에 쓴다
        self.start_snapshot = None  # start_draw()를 부른 "그 순간"의 스냅숏(재현 기준점)

    @property
    def profile(self):
        return SPEED_PROFILE[self.speed]

    @property
    def busy(self):
        return self.phase != "idle"

    @property
    def spin_rate(self):
        return SPIN_FAST * self.spin_level

    @property
    def port_point(self):
        """벽 안쪽에서 공이 처음 빨려 들어가는(그립이 걸리지 않는) 지점 — 드럼 천장의 작은 구멍."""
        return DRUM_CX, DRUM_CY - DRUM_R + self.ball_r * 0.2

    # ------------------------------------------------------------ 진행
    def start_draw(self):
        """뽑기 시작. 이미 진행 중이면 아무 일도 하지 않는다."""
        if self.busy or self.winner is not None:
            return False
        # [버그 수정] 스냅숏(snapshot())은 위치·속도만 담고, 그립 상태(붙잡혀
        # 도는 중인지·쿨다운 등)는 담지 않는다 — 대기 중 우연히 붙잡혀 있던
        # 공이 있으면 재현 쪽(스냅숏에서 새로 만든 세계는 항상 안 붙잡힌
        # 상태로 시작)과 갈라져 결과가 달라졌다. 뽑기가 시작되는 이 순간
        # 모든 공을 "안 붙잡힌" 공통 기준선으로 맞춘 뒤 스냅숏을 뜬다.
        w = self.world
        for i in range(len(w.keys)):
            w.stuck[i] = False
            w.cool[i] = 0.0
            w.can_reattach[i] = True
        w.quantize()
        self.start_snapshot = w.snapshot()
        # 대기 중 텀블링이 이미 난수를 여러 번 써 버린 상태라, 여기서 다시
        # 시드를 넣지 않으면 "버튼을 얼마나 기다렸다 눌렀는지"에 따라 결과가
        # 달라져 재현이 깨진다 — 뽑기가 실제로 시작되는 이 순간을 재현의
        # 기준점으로 삼는다. sim_t(바람의 출렁임 위상 계산에 씀)도 함께
        # 0으로 되돌린다 — 안 그러면 대기 시간만큼 바람의 위상이 밀려서
        # 똑같이 갈라진다.
        self.rng = _random.Random(self.seed)
        self.sim_t = 0.0
        self.world.randomize_wind_phase(self.rng)
        self.phase = "mixing"
        self.phase_t = 0.0
        return True

    def _step_port(self, dt):
        prof = self.profile
        self.sub_t += dt
        if self.port_sub == "countdown":
            p = min(1.0, self.sub_t / prof["countdown"])
            freq = 2.0 + p * 9.0   # 깜빡이는 주기가 2Hz → 11Hz로 점점 빨라진다
            self.blink = 0.5 + 0.5 * math.sin(self.sub_t * freq * 2 * math.pi)
            if self.sub_t >= prof["countdown"]:
                self.port_sub = "opening"
                self.sub_t = 0.0
        elif self.port_sub == "opening":
            self.door = min(1.0, self.sub_t / prof["open"])
            if self.sub_t >= prof["open"]:
                self.port_sub = "sucking"
                self.sub_t = 0.0
                self.door = 1.0
        elif self.port_sub == "sucking":
            self.door = 1.0   # 잡힐 때까지 열린 채 유지
        elif self.port_sub == "closing":
            self.door = max(0.0, 1.0 - self.sub_t / prof["close"])
            if self.sub_t >= prof["close"]:
                self.port_sub = "holding"
                self.sub_t = 0.0
                self.door = 0.0
        elif self.port_sub == "holding":
            if self.sub_t >= prof["hold"]:
                self.port_sub = "closed"
                self.sub_t = 0.0
                self.phase = "idle"
                self.phase_t = 0.0

    def step(self):
        """한 스텝(PHYS_DT) 진행. 당첨 공이 나오면 그 키를 돌려준다."""
        dt = PHYS_DT
        self.sim_t += dt
        self.phase_t += dt
        prof = self.profile
        wind = 0.0
        suction = None

        if self.phase == "mixing":
            self.spin_level = 1.0
            if self.phase_t >= prof["mix"]:
                self.phase = "slowdown"
                self.phase_t = 0.0
        elif self.phase == "slowdown":
            f = _ease_in_out(self.phase_t / prof["slowdown"])
            self.spin_level = 1.0 - f   # 완전히 0까지 줄어든다(드럼이 멈춘다)
            if f >= 1.0:
                self.phase = "wind"
                self.phase_t = 0.0
                self.port_sub = "countdown"
                self.sub_t = 0.0
                self.door = 0.0
                self.blink = 0.0
                self.spin_level = 0.0
        elif self.phase == "wind":
            self._step_port(dt)
            self.spin_level = (SPIN_IDLE / SPIN_FAST) if self.port_sub in ("closing", "holding") else 0.0
            if self.port_sub in ("countdown", "opening", "sucking"):
                wind = 1.0
            if self.port_sub == "sucking":
                suction = (self.port_point[0], self.port_point[1], SUCTION_POWER)
        elif self.phase == "idle":
            self.spin_level = SPIN_IDLE / SPIN_FAST

        idx = self.world.step(dt, self.rng, spin_rate=self.spin_rate, wind=wind,
                              wind_t=self.sim_t, suction=suction)
        if idx is not None:
            self.winner = self.world.keys[idx]
            self.winner_pos = (self.world.xs[idx], self.world.ys[idx])
            self.port_sub = "closing"
            self.sub_t = 0.0
            return self.winner
        return None

    # ------------------------------------------------------------ 재현
    def replay_info(self):
        return {"snapshot": self.start_snapshot, "ball_r": self.ball_r, "speed": self.speed}

    @classmethod
    def from_replay(cls, seed, info):
        sim = cls([row[0] for row in info["snapshot"]], seed, snapshot=info["snapshot"],
                  ball_radius=info["ball_r"], speed=info.get("speed", "normal"))
        sim.start_draw()
        return sim


def run_drum_headless(keys, seed, speed="normal", max_seconds=30.0, snapshot=None, total_count=None):
    """화면 없이 드럼 한 회차를 끝까지 돌린다(테스트·재현 검증용).
    반환: (당첨 키, DrumSim)."""
    sim = DrumSim(keys, seed, snapshot=snapshot, total_count=total_count, speed=speed)
    sim.start_draw()
    for _ in range(int(max_seconds / PHYS_DT)):
        k = sim.step()
        if k is not None:
            return k, sim
    return None, sim


def replay_drum_headless(seed, info, max_seconds=30.0):
    sim = DrumSim.from_replay(seed, info)
    for _ in range(int(max_seconds / PHYS_DT)):
        k = sim.step()
        if k is not None:
            return k
    return None

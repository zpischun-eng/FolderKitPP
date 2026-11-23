# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: CPU 스케줄링 간트차트 [신규] — 순수 로직

7개 스케줄링 기법(FCFS/SJF/SRTF/우선순위(비선점·선점)/RR/HRN)을 1단위
정수 시간 틱(tick) 루프로 시뮬레이션한다. 시간을 정수로 제한하는 이유는
교과서 예제가 모두 정수이고, 이렇게 하면 선점형과 비선점형을 같은 루프
구조로 처리할 수 있어서다(매 틱마다 "지금 CPU를 누가 쓸지"만 다시
판단하면 되므로).

## 내부 키 vs 표시 문구
프로세스의 사용자 입력 이름("P1" 등)은 표시에만 쓰고, 색상 배정·정렬
동률 처리·저장은 전부 입력 순서로 부여되는 정수 ``pid``로만 한다.
언어를 바꾸거나 이름을 중복 입력해도 계산 결과가 흔들리지 않게 하기
위해서다.

## 동점(tie) 규칙 — 교재마다 답이 달라지는 지점을 여기서 고정한다
- 선택 기준이 같으면: 도착 시간이 빠른 쪽 → 그래도 같으면 입력 순서(pid)가
  빠른 쪽.
- 선점형(SRTF·선점 우선순위)에서 새 도착의 기준값이 현재 실행 중인
  프로세스와 "같으면" 선점하지 않는다(더 좋아야만 선점).
- RR: 시간 할당량이 끝나는 시점에 새 프로세스가 도착해 있으면, **새
  도착을 먼저 큐 뒤에 넣고 선점된(할당량이 끝난) 프로세스는 그 다음에**
  넣는다.
- HRN: 항상 비선점이며, 프로세스를 고르는 시점마다
  (대기시간+실행시간)/실행시간(응답률)을 다시 계산해 가장 큰 쪽을 고른다.
"""
from collections import deque

# ---------------------------------------------------------------- 내부 키
ALGO_FCFS = "fcfs"
ALGO_SJF = "sjf"          # 최단 작업 우선 — 비선점
ALGO_SRTF = "srtf"        # 최단 잔여시간 우선 — 선점
ALGO_PRIO = "prio"        # 우선순위 — 비선점
ALGO_PRIO_P = "prio_p"    # 우선순위 — 선점
ALGO_RR = "rr"            # 라운드 로빈
ALGO_HRN = "hrn"          # 최고 응답률 우선 — 비선점

ALGO_ORDER = [ALGO_FCFS, ALGO_SJF, ALGO_SRTF, ALGO_PRIO, ALGO_PRIO_P, ALGO_RR, ALGO_HRN]

PRIO_LOW_FIRST = "low_first"    # 숫자가 작을수록 높은 우선순위(기본)
PRIO_HIGH_FIRST = "high_first"  # 숫자가 클수록 높은 우선순위

MAX_PROCS = 8
MAX_TIME_CAP = 100000
_DEFAULT_QUANTUM = 2


# =============================================================================
class Proc:
    """스케줄링 대상 프로세스 하나.

    ``pid``는 입력 순서로 부여되는 내부 키(0부터) — 저장·비교·색상 배정은
    전부 이 값으로 한다. ``name``은 사용자가 입력한 표시용 문자열일 뿐이라
    중복되거나 나중에 바뀌어도 계산에는 영향이 없다.
    """

    def __init__(self, pid, name, arrival, burst, priority=0):
        self.pid = pid
        self.name = name
        self.arrival = max(0, int(arrival))
        self.burst = max(1, int(burst))
        self.priority = int(priority)

    def __repr__(self):
        return f"Proc(pid={self.pid}, name={self.name!r}, arrival={self.arrival}, burst={self.burst}, priority={self.priority})"


class Segment:
    """간트차트의 한 구간. ``pid``가 ``None``이면 CPU 유휴 구간."""

    def __init__(self, start, end, pid):
        self.start = start
        self.end = end
        self.pid = pid


class ProcStat:
    """프로세스 한 개의 완료 통계."""

    def __init__(self, pid, arrival, burst, ct, start):
        self.pid = pid
        self.arrival = arrival
        self.burst = burst
        self.ct = ct                    # 완료 시각(completion time)
        self.start = start              # 최초로 CPU를 받은 시각
        self.tat = ct - arrival         # 반환시간(turnaround time)
        self.wt = self.tat - burst      # 대기시간(waiting time)
        self.rt = start - arrival       # 응답시간(response time)


class Result:
    """시뮬레이션 결과 전체. ``error``가 있으면 나머지 필드는 비어 있다."""

    def __init__(self, segments=None, stats=None, ready_snapshots=None,
                 makespan=0, error=None, error_params=None):
        self.segments = segments or []
        self.stats = stats or {}                    # pid -> ProcStat
        self.ready_snapshots = ready_snapshots or {}  # t -> [pid, ...] (대기 중, 실행 중 제외)
        self.makespan = makespan
        self.error = error              # 내부 오류 키(문자열) 또는 None
        self.error_params = error_params or {}

    @property
    def ok(self):
        return self.error is None

    def _avg(self, attr):
        if not self.stats:
            return 0.0
        return sum(getattr(s, attr) for s in self.stats.values()) / len(self.stats)

    @property
    def avg_wt(self):
        return self._avg("wt")

    @property
    def avg_tat(self):
        return self._avg("tat")

    @property
    def avg_rt(self):
        return self._avg("rt")

    @property
    def cpu_busy(self):
        return sum(seg.end - seg.start for seg in self.segments if seg.pid is not None)

    @property
    def utilization(self):
        """CPU 이용률(0~1). makespan이 0이면 0."""
        if self.makespan <= 0:
            return 0.0
        return self.cpu_busy / self.makespan

    @property
    def throughput(self):
        """단위 시간당 완료된 프로세스 수."""
        if self.makespan <= 0:
            return 0.0
        return len(self.stats) / self.makespan


# =============================================================================
# 검증
# =============================================================================
def validate(procs, quantum=_DEFAULT_QUANTUM):
    """오류 목록을 돌려준다. 비어 있으면 시뮬레이션을 진행해도 안전하다.

    각 항목은 ``(내부_오류_키, {서식_인자})`` 튜플이다 — 화면에 표시할 때는
    ``tr(f"util.cpusched.err.{key}", **params)``로 그때 문구로 바꾼다.
    """
    errors = []
    if not procs:
        errors.append(("empty", {}))
        return errors
    if len(procs) > MAX_PROCS:
        errors.append(("too_many", {"a0": MAX_PROCS}))
    for i, p in enumerate(procs):
        if p.burst < 1:
            errors.append(("burst_invalid", {"a0": i + 1}))
        if p.arrival < 0:
            errors.append(("arrival_invalid", {"a0": i + 1}))
    total = sum(max(p.burst, 0) for p in procs)
    max_arr = max((p.arrival for p in procs), default=0)
    if total + max_arr > MAX_TIME_CAP:
        errors.append(("too_large", {}))
    if quantum < 1:
        errors.append(("quantum_invalid", {}))
    return errors


# =============================================================================
# 선택 기준(키) — 값이 작을수록 우선 선택된다
# =============================================================================
def _key_fcfs(p, remaining, t):
    return (p.arrival, p.pid)


def _key_sjf(p, remaining, t):
    return (remaining[p.pid], p.arrival, p.pid)


def _make_key_prio(prio_dir):
    def _key(p, remaining, t):
        pv = p.priority if prio_dir == PRIO_LOW_FIRST else -p.priority
        return (pv, p.arrival, p.pid)
    return _key


def _key_hrn(p, remaining, t):
    wait = t - p.arrival
    ratio = (wait + p.burst) / p.burst
    return (-ratio, p.arrival, p.pid)  # 응답률이 클수록 우선 → 음수로 뒤집어 "작을수록 우선"에 맞춤


# =============================================================================
# 틱 기반 엔진 — FCFS·SJF·SRTF·우선순위(비선점/선점)·HRN 공용
# =============================================================================
def _simulate_tick(procs, algo, prio_dir=PRIO_LOW_FIRST):
    n = len(procs)
    remaining = {p.pid: p.burst for p in procs}
    by_pid = {p.pid: p for p in procs}
    started = {}
    finished = {}
    segments = []
    ready_snapshots = {}

    preemptive = algo in (ALGO_SRTF, ALGO_PRIO_P)
    key_fn = {
        ALGO_FCFS: _key_fcfs,
        ALGO_SJF: _key_sjf,
        ALGO_SRTF: _key_sjf,             # 잔여시간 기준 — SJF와 같은 키, 선점 여부만 다르다
        ALGO_PRIO: _make_key_prio(prio_dir),
        ALGO_PRIO_P: _make_key_prio(prio_dir),
        ALGO_HRN: _key_hrn,
    }[algo]

    max_time = min(sum(p.burst for p in procs) + max(p.arrival for p in procs) + 1, MAX_TIME_CAP)

    t = 0
    completed = 0
    current_pid = None
    seg_start = None

    while completed < n and t < max_time:
        ready = [p for p in procs if p.arrival <= t and remaining[p.pid] > 0]

        if not ready:
            if current_pid is not None:
                segments.append(Segment(seg_start, t, current_pid))
                current_pid = None
                seg_start = None
            future = [p.arrival for p in procs if remaining[p.pid] > 0 and p.arrival > t]
            if not future:
                break
            next_t = min(future)
            segments.append(Segment(t, next_t, None))
            t = next_t
            continue

        if preemptive:
            best = min(ready, key=lambda p: key_fn(p, remaining, t))
            if current_pid is not None and remaining[current_pid] > 0:
                cur_proc = by_pid[current_pid]
                chosen = best.pid if key_fn(best, remaining, t) < key_fn(cur_proc, remaining, t) else current_pid
            else:
                chosen = best.pid
        else:
            if current_pid is not None and remaining[current_pid] > 0:
                chosen = current_pid
            else:
                chosen = min(ready, key=lambda p: key_fn(p, remaining, t)).pid

        ready_snapshots[t] = [p.pid for p in sorted(ready, key=lambda p: key_fn(p, remaining, t))
                               if p.pid != chosen]

        if chosen != current_pid:
            if current_pid is not None:
                segments.append(Segment(seg_start, t, current_pid))
            current_pid = chosen
            seg_start = t
            if chosen not in started:
                started[chosen] = t

        remaining[chosen] -= 1
        t += 1

        if remaining[chosen] == 0:
            finished[chosen] = t
            completed += 1
            segments.append(Segment(seg_start, t, chosen))
            current_pid = None
            seg_start = None

    if current_pid is not None:
        segments.append(Segment(seg_start, t, current_pid))

    return segments, started, finished, ready_snapshots, t


# =============================================================================
# 라운드 로빈 — 큐 기반(틱 엔진과 별도 — 시간 할당량 단위로 한 번에 실행)
# =============================================================================
def _simulate_rr(procs, quantum):
    quantum = max(1, int(quantum))
    n = len(procs)
    remaining = {p.pid: p.burst for p in procs}
    started = {}
    finished = {}
    segments = []
    ready_snapshots = {}

    by_arrival = sorted(procs, key=lambda p: (p.arrival, p.pid))
    max_time = min(sum(p.burst for p in procs) + max(p.arrival for p in procs) + 1, MAX_TIME_CAP)

    idx = 0
    queue = deque()

    def enqueue_up_to(up_to):
        nonlocal idx
        while idx < n and by_arrival[idx].arrival <= up_to:
            queue.append(by_arrival[idx].pid)
            idx += 1

    enqueue_up_to(0)
    t = 0
    completed = 0

    while completed < n and t < max_time:
        if not queue:
            if idx < n:
                next_t = by_arrival[idx].arrival
                segments.append(Segment(t, next_t, None))
                t = next_t
                enqueue_up_to(t)
                continue
            break

        ready_snapshots[t] = list(queue)
        pid = queue.popleft()
        if pid not in started:
            started[pid] = t
        run_for = min(quantum, remaining[pid])
        seg_end = t + run_for
        remaining[pid] -= run_for
        segments.append(Segment(t, seg_end, pid))
        t = seg_end
        enqueue_up_to(t)          # 이번 슬라이스 중 도착한 프로세스를 먼저 큐 뒤에 넣는다
        if remaining[pid] > 0:
            queue.append(pid)     # 그 다음에 할당량이 끝난(=선점된) 프로세스를 다시 넣는다
        else:
            finished[pid] = t
            completed += 1

    return segments, started, finished, ready_snapshots, t


# =============================================================================
# 공개 API
# =============================================================================
def simulate(procs, algo, quantum=_DEFAULT_QUANTUM, prio_dir=PRIO_LOW_FIRST):
    """스케줄링을 실행해 :class:`Result`를 돌려준다.

    ``procs``는 :class:`Proc` 리스트. 오류가 있으면 :meth:`validate`가 먼저
    걸러내는 것을 전제로 하지만, 이 함수도 방어적으로 다시 확인한다.
    """
    errors = validate(procs, quantum)
    if errors:
        code, params = errors[0]
        return Result(error=code, error_params=params)

    if algo == ALGO_RR:
        segments, started, finished, ready_snapshots, end_t = _simulate_rr(procs, quantum)
    elif algo in ALGO_ORDER:
        segments, started, finished, ready_snapshots, end_t = _simulate_tick(procs, algo, prio_dir)
    else:
        return Result(error="unknown_algo", error_params={})

    stats = {}
    for p in procs:
        if p.pid in finished:
            stats[p.pid] = ProcStat(p.pid, p.arrival, p.burst, finished[p.pid], started[p.pid])

    if len(stats) != len(procs):
        return Result(error="internal_incomplete", error_params={})

    return Result(segments=segments, stats=stats, ready_snapshots=ready_snapshots, makespan=end_t)


# =============================================================================
# 예제 — 화면의 "예제 불러오기" 콤보에서 그대로 쓴다(순수 데이터)
# =============================================================================
class ExamplePreset:
    def __init__(self, key, rows, algo, quantum=_DEFAULT_QUANTUM, prio_dir=PRIO_LOW_FIRST):
        self.key = key                    # 내부 키 — util.cpusched.example.<key> 로 번역
        self.rows = rows                  # [(name, arrival, burst, priority), ...]
        self.algo = algo
        self.quantum = quantum
        self.prio_dir = prio_dir


EXAMPLES = [
    ExamplePreset("fcfs_basic",
                  [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)],
                  ALGO_FCFS),
    ExamplePreset("sjf_basic",
                  [("P1", 0, 6, 0), ("P2", 2, 8, 0), ("P3", 4, 7, 0), ("P4", 5, 3, 0)],
                  ALGO_SJF),
    ExamplePreset("srtf_basic",
                  [("P1", 0, 8, 0), ("P2", 1, 4, 0), ("P3", 2, 9, 0), ("P4", 3, 5, 0)],
                  ALGO_SRTF),
    ExamplePreset("prio_basic",
                  [("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 4), ("P4", 0, 1, 5), ("P5", 0, 5, 2)],
                  ALGO_PRIO, prio_dir=PRIO_LOW_FIRST),
    ExamplePreset("rr_basic",
                  [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)],
                  ALGO_RR, quantum=4),
    ExamplePreset("hrn_basic",
                  [("P1", 0, 3, 0), ("P2", 1, 6, 0), ("P3", 2, 4, 0), ("P4", 3, 5, 0)],
                  ALGO_HRN),
]


def make_procs(rows):
    """[(name, arrival, burst, priority), ...] → [Proc(pid=순서), ...]"""
    return [Proc(i, name, arrival, burst, priority)
            for i, (name, arrival, burst, priority) in enumerate(rows)]

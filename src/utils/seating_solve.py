# -*- coding: utf-8 -*-
"""
FolderKit++ — 좌석표 [v40] 순수 로직 (Qt 의존 없음).

명단을 읽고 저장하는 형식은 대진표 작성기(bracket_solve.py)의
Student/read_roster_excel/roster_to_json 그대로 재사용한다 — 학급
명단 엑셀은 어느 도구에서 쓰든 같은 형식(학년·반·번호·이름·성별)이라
새로 만들 이유가 없다(개발 스펙 문서의 "명단 로딩 재사용" 항목).

좌석 배치 저장도 대진표 시리즈와 같은 방식 — 폴더 하나를 정해 두면
반마다 "좌석표_학년반.json" 파일로 계속 남고, 다음에 열면 마지막으로
섞은 자리 그대로 이어서 쓴다.
"""
import json
import os
import random as _random
import uuid as _uuid

# 명단 형식은 대진표와 완전히 같다 — 여기서 다시 만들지 않고 그대로 가져온다.
from .bracket_solve import Student, read_roster_excel, roster_to_json, roster_from_json  # noqa: F401


def _rng(seed):
    return _random.Random(seed) if seed is not None else _random.Random()


_FEMALE_TOKENS = ("여", "f", "female", "woman", "girl", "女")


def is_female(student):
    g = (getattr(student, "gender", "") or "").strip().lower()
    return g in _FEMALE_TOKENS


class SeatingChart:
    """한 학급의 좌석 배치 하나. seats는 행(줄) 단위 목록이고, seats[r][c]는
    그 자리에 앉은 학생의 Student.sid(빈 자리면 None)다. 0번째 행이
    교탁과 가장 가깝다.

    [v43.8] gender는 seats와 같은 모양의 격자로, 그 **자리 자체**의
    색(성별 구역) 지정이다 — 누가 앉아 있는지와는 별개다. 값은
    "M"(남학생, 옅은 파랑)·"F"(여학생, 옅은 빨강)·"vacant"(공석, 그
    자리엔 아무도 앉히지 않음) 중 하나. 새 배치는 전부 "M"으로
    시작한다(요청대로) — 교사가 자리를 오른쪽 클릭해서 원하는 자리만
    색을 바꾼다.

    [v43.9] reserved는 {(row, col): sid} — 특정 학생을 특정 자리에
    고정한 "지정석" 목록이다. 다시 섞어도 지정석 학생은 항상 그 자리에
    남고, 나머지 학생만 무작위로 채워진다."""

    __slots__ = ("id", "grade", "cls", "cols", "seats", "gender", "reserved")

    def __init__(self, grade, cls, cols, seats, chart_id=None, gender=None, reserved=None):
        self.id = chart_id or _uuid.uuid4().hex[:12]
        self.grade = grade
        self.cls = cls
        self.cols = max(1, int(cols))
        self.seats = seats   # [[sid|None, ...], ...]
        if gender is None:
            gender = [["M"] * self.cols for _ in seats]
        self.gender = gender   # [["M"|"F"|"vacant", ...], ...] — seats와 같은 모양
        self.reserved = reserved if reserved is not None else {}   # {(row, col): sid}

    @property
    def rows(self):
        return len(self.seats)

    def to_dict(self):
        return {"id": self.id, "grade": self.grade, "cls": self.cls, "cols": self.cols,
                "seats": self.seats, "gender": self.gender,
                "reserved": {f"{r}-{c}": sid for (r, c), sid in self.reserved.items()}}

    @classmethod
    def from_dict(cls, d):
        seats = [list(row) for row in d.get("seats", [])]
        raw_gender = d.get("gender")
        cols = int(d.get("cols", 1))
        if raw_gender is None:
            # [하위 호환] gender 정보가 없는 옛 저장 파일 — 전부 "M"으로 채운다.
            gender = [["M"] * cols for _ in seats]
        else:
            gender = [list(row) for row in raw_gender]
        reserved = {}
        for key, sid in (d.get("reserved") or {}).items():
            r_str, _sep, c_str = key.partition("-")
            try:
                reserved[(int(r_str), int(c_str))] = sid
            except ValueError:
                continue
        return cls(d.get("grade", ""), d.get("cls", ""), cols, seats,
                   chart_id=d.get("id"), gender=gender, reserved=reserved)


def class_key(grade, cls):
    return f"{grade}학년{cls}반"


def students_of_class(roster, grade, cls):
    return [s for s in roster if s.grade == grade and s.cls == cls]


def class_options(roster):
    """명단에 있는 (학년, 반) 조합을 학년→반 순으로 중복 없이 뽑는다."""
    seen = []
    for s in roster:
        key = (s.grade, s.cls)
        if key not in seen:
            seen.append(key)

    def _num(v):
        try:
            return (0, int(v))
        except (TypeError, ValueError):
            return (1, str(v))
    seen.sort(key=lambda gc: (_num(gc[0]), _num(gc[1])))
    return seen


def random_layout(students, cols, seed=None, grade="", cls="", gender_grid=None, reserved=None):
    """학생을 줄(분단) 수에 맞춰 무작위로 앉힌다. 인원이 줄 수로 안
    나누어떨어지면 **마지막 줄의 끝자리부터** 빈 자리(None)로 남는다.
    gender_grid를 안 주면(처음 만드는 배치) 전부 "M"인 새 격자로
    시작한다 — [v43.8] 남학생은 "M" 칸에만, 여학생은 "F" 칸에만
    앉는다(성별 정보가 없는 학생은 "남학생"으로 취급 — 기본이 전부
    "M"이므로 자연스럽게 아무 칸에나 앉는 것과 같다). [v43.9]
    reserved({(row,col): sid})를 주면 그 학생들을 먼저 그 자리에
    앉히고, 나머지 자리만 무작위로 채운다."""
    cols = max(1, int(cols))
    rows = max(1, -(-len(students) // cols)) if students else 1   # ceil
    if gender_grid is None:
        gender_grid = [["M"] * cols for _ in range(rows)]
    chart, _overflow = _place_by_gender(students, gender_grid, cols, seed=seed, grade=grade, cls=cls,
                                        reserved=reserved)
    return chart


def _place_by_gender(students, gender_grid, cols, seed=None, grade="", cls="", reserved=None):
    """gender_grid(자리별 성별 지정)를 그대로 두고, 남학생은 "M" 칸에만,
    여학생은 "F" 칸에만 무작위로 앉힌다. "vacant" 칸엔 아무도 안
    앉힌다. reserved로 지정한 학생은 먼저 그 자리에 그대로 앉히고
    (지정석이 vacant 칸이면 지정을 건너뛰고 그 학생도 일반 무작위
    배치 대상이 된다), 나머지 학생만 남은 자리에 무작위로 채운다.
    해당 색 칸이 모자라면(성별 구역과 실제 인원이 안 맞음) 남는
    학생은 비어 있는 다른 칸(공석 제외)에 채운다 — 자리 색과 안 맞더라도
    학생을 자리 배치에서 빠뜨리는 것보다는 낫다. 그래도 자리 자체가
    모자라면 못 앉은 학생 목록을 같이 돌려준다.
    반환: (SeatingChart, overflow_students)."""
    rows = len(gender_grid)
    reserved = dict(reserved or {})
    rng = _rng(seed)

    seats = [[None] * cols for _ in range(rows)]
    reserved_sids = set()
    by_sid = {s.sid: s for s in students}
    for (r, c), sid in reserved.items():
        if not (0 <= r < rows and 0 <= c < cols):
            continue
        if gender_grid[r][c] == "vacant" or sid not in by_sid:
            continue   # 공석으로 바뀌었거나 이미 없는 학생 — 지정석으로 못 앉힌다
        seats[r][c] = sid
        reserved_sids.add(sid)

    pool = [s for s in students if s.sid not in reserved_sids]
    males = [s for s in pool if not is_female(s)]
    females = [s for s in pool if is_female(s)]
    rng.shuffle(males)
    rng.shuffle(females)

    # [버그 수정] 자리 자체는 원래 순서(줄 순서) 그대로 앞에서부터 채운다 —
    # 학생 쪽(males/females)은 이미 섞여 있으니 이것만으로 충분히
    # 무작위 배치가 되고, "인원이 안 맞으면 맨 끝 자리부터 빈다"는 기존
    # 규칙(그리고 테스트)이 그대로 유지된다. 자리 순서까지 섞으면 빈
    # 자리가 아무 데나 튀어서 이 규칙이 깨진다.
    m_cells = [(r, c) for r in range(rows) for c in range(cols)
              if gender_grid[r][c] == "M" and seats[r][c] is None]
    f_cells = [(r, c) for r in range(rows) for c in range(cols)
              if gender_grid[r][c] == "F" and seats[r][c] is None]

    leftover = []
    for i, s in enumerate(males):
        if i < len(m_cells):
            r, c = m_cells[i]
            seats[r][c] = s.sid
        else:
            leftover.append(s)
    for i, s in enumerate(females):
        if i < len(f_cells):
            r, c = f_cells[i]
            seats[r][c] = s.sid
        else:
            leftover.append(s)

    free_cells = [(r, c) for r in range(rows) for c in range(cols)
                  if seats[r][c] is None and gender_grid[r][c] != "vacant"]
    rng.shuffle(free_cells)
    for s, (r, c) in zip(leftover, free_cells):
        seats[r][c] = s.sid
    overflow = leftover[len(free_cells):]

    # 지정석 중 실제로 자리 잡은 것만 저장(공석으로 밀려나 못 앉은 건 제외)
    kept_reserved = {rc: sid for rc, sid in reserved.items() if seats[rc[0]][rc[1]] == sid}
    chart = SeatingChart(grade, cls, cols, seats, gender=[row[:] for row in gender_grid],
                         reserved=kept_reserved)
    return chart, overflow


def reshuffle(chart, students, seed=None):
    """지금 반·줄 수·자리별 성별 지정·지정석은 그대로 두고 나머지
    자리만 다시 섞는다."""
    new_chart, _overflow = _place_by_gender(students, chart.gender, chart.cols, seed=seed,
                                            grade=chart.grade, cls=chart.cls, reserved=chart.reserved)
    return new_chart


class _NumberedSeat:
    """[v43.1] 명단이 아직 없을 때 쓰는 가짜 "학생" — random_layout은
    각 자리 주인의 .sid만 보고 나머지는 신경 안 쓰므로, 번호 문자열
    하나만 들고 있으면 그대로 재사용할 수 있다."""
    __slots__ = ("sid",)

    def __init__(self, number):
        self.sid = str(number)


def set_seat_gender(chart, row, col, value):
    """자리 하나의 성별 지정을 바꾼다("M"/"F"/"vacant"). "vacant"로 바꾸면
    지금 거기 앉은 학생은 그 자리에서 내려온다(호출부가 다른 빈 자리로
    옮겨 주지 않으면 다음 "다시 섞기" 때에야 다시 나타난다 — 위젯
    쪽에서는 seating.py의 _vacate_seat()가 즉시 옮겨 준다). 지정석이었던
    자리를 공석으로 바꾸면 그 지정석도 같이 없어진다."""
    chart.gender[row][col] = value
    if value == "vacant":
        chart.seats[row][col] = None
        chart.reserved.pop((row, col), None)


def find_empty_seat(chart, exclude=None):
    """지금 비어 있고(seats가 None) 공석으로 지정되지 않은 자리를 하나
    찾는다 — 앞줄부터 순서대로. 없으면 None. exclude로 준 자리는
    후보에서 뺀다(방금 그 학생이 있던 자리 자신 등)."""
    for r in range(chart.rows):
        for c in range(chart.cols):
            if (r, c) == exclude:
                continue
            if chart.seats[r][c] is None and chart.gender[r][c] != "vacant":
                return r, c
    return None


def numbered_layout(count, cols, seed=None, gender_grid=None, reserved=None):
    """명단 없이 인원 수만 입력해 1~count번 좌석표를 만든다(신규 미니앱
    개발 스펙 2차 착수 요청 — 명단을 아직 안 올렸어도 우선 테스트해 볼
    수 있게). 나중에 명단을 올리면 random_layout으로 자연스럽게
    바뀐다 — 번호 자체를 "가짜 sid"로 써서 대진표와 똑같은 셔플 로직을
    그대로 재사용한다. gender_grid·reserved를 주면(예: "다시 섞기")
    자리별 성별 지정·지정석을 그대로 유지한 채 배치만 다시 한다."""
    fake_students = [_NumberedSeat(i) for i in range(1, max(0, int(count)) + 1)]
    return random_layout(fake_students, cols, seed=seed, gender_grid=gender_grid, reserved=reserved)


def chart_file_path(save_dir, grade, cls):
    if not save_dir:
        return None
    safe = class_key(grade, cls).replace("/", "_").replace("\\", "_")
    return os.path.join(save_dir, f"좌석표_{safe}.json")


def save_chart(path, chart):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chart.to_dict(), f, ensure_ascii=False, indent=1)


def load_chart(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return SeatingChart.from_dict(data)


def list_chart_files(save_dir):
    """save_dir에 있는 좌석표 파일을 (학년, 반, 경로) 목록으로 돌려준다."""
    if not save_dir or not os.path.isdir(save_dir):
        return []
    out = []
    for fn in sorted(os.listdir(save_dir)):
        if fn.startswith("좌석표_") and fn.endswith(".json"):
            out.append(os.path.join(save_dir, fn))
    return out

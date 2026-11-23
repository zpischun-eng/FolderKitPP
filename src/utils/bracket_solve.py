# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 대진표 작성기(순수 로직) [신규]

체육 수업(탁구·배드민턴처럼 1:1 경기, 농구·피구처럼 팀 경기)에서 학생을
조 편성하거나 대진표를 짤 때 쓴다. 세 가지 방식을 다룬다:

1. **조 편성**(balanced_teams) — N명을 K개 팀으로 최대한 균등하게 나눈다.
2. **토너먼트(단일 엘리미네이션)**(single_elimination) — 참가자 수가 2의
   거듭제곱이 아니면 부전승(bye)을 채워 대진표를 짠다.
3. **리그(라운드 로빈)**(round_robin_schedule) — 모든 참가자가 서로 한
   번씩 겨루는 일정을 원형법(circle method)으로 짠다.

전부 표준 조합론 알고리즘이라 외부 라이브러리가 필요 없다. 난수는
`random.Random(seed)`로 감싸서, seed를 주면 항상 같은 결과가 나오게
했다(테스트가 이 값으로 결과를 고정해서 검증한다) — seed를 안 주면
`random.SystemRandom()`처럼 매번 다르게 섞인다.
"""
import random
import os


def _rng(seed=None):
    return random.Random(seed) if seed is not None else random.Random()


def balanced_teams(names, num_teams, seed=None):
    """names를 무작위로 뒤섞은 뒤 num_teams개 팀에 최대한 균등하게
    나눈다(1명씩 차례로 배분하므로, 인원이 안 맞아도 팀 간 차이가
    최대 1명을 넘지 않는다). 팀 목록(list[list[str]])을 돌려준다."""
    num_teams = max(1, int(num_teams))
    items = list(names)
    _rng(seed).shuffle(items)
    teams = [[] for _ in range(num_teams)]
    for i, name in enumerate(items):
        teams[i % num_teams].append(name)
    return teams


def _next_power_of_two(n):
    p = 1
    while p < n:
        p *= 2
    return p


def single_elimination(names, seed=None):
    """토너먼트(단일 엘리미네이션) 대진표를 만든다. 참가자 수가 2의
    거듭제곱이 아니면 부전승(bye, None으로 표시)을 채운다.

    [버그 수정] 부전승이 2개 이상일 때 그냥 끝에 몰아서 붙이면 부전승
    끼리(None vs None) 짝지어지는 경기가 생길 수 있었다(예: 10명 →
    16자리, 부전승 6개 중 3경기가 None-vs-None이 되어 버렸다 — 실전
    데이터로 검증하다가 실제로 발견함). 부전승 하나하나를 서로 다른
    실제 참가자 뒤에 하나씩 붙여서, 부전승이 항상 서로 다른 경기에
    한 개씩만 들어가게 고쳤다.

    반환값은 라운드의 목록이다. 각 라운드는 (선수1, 선수2) 튜플의
    목록 — 아직 정해지지 않은 자리는 None으로 비어 있다(부전승으로
    이미 정해진 다음 라운드 진출자는 이름이 채워져 있다)."""
    items = list(names)
    _rng(seed).shuffle(items)
    if not items:
        return []
    n = len(items)
    size = _next_power_of_two(n)
    byes = size - n
    bye_after = set(range(n - byes, n)) if byes else set()
    slots = []
    for idx, name in enumerate(items):
        slots.append(name)
        if idx in bye_after:
            slots.append(None)
    round1 = [(slots[i], slots[i + 1]) for i in range(0, size, 2)]
    rounds = [round1]

    current = []
    for a, b in round1:
        if a is None and b is None:
            current.append(None)
        elif a is None:
            current.append(b)
        elif b is None:
            current.append(a)
        else:
            current.append(None)   # 둘 다 있으면 승자 미정(TBD)

    while len(current) > 1:
        nxt_matches = [(current[i], current[i + 1]) for i in range(0, len(current), 2)]
        rounds.append(nxt_matches)
        nxt_current = []
        for a, b in nxt_matches:
            if a is not None and b is None:
                nxt_current.append(a)
            elif b is not None and a is None:
                nxt_current.append(b)
            else:
                nxt_current.append(None)
        current = nxt_current
    return rounds


def round_robin_schedule(names, seed=None):
    """모든 참가자가 서로 한 번씩 겨루는 일정을 원형법(circle method)으로
    짠다. 인원이 홀수면 매 라운드 한 명씩 부전승(None과 짝)이 된다.
    라운드 목록(list[list[(선수1, 선수2)]])을 돌려준다 — 참가자 n명이면
    n-1라운드(홀수면 부전승 포함해서 n라운드)가 된다."""
    items = list(names)
    _rng(seed).shuffle(items)
    if len(items) < 2:
        return []
    if len(items) % 2 == 1:
        items.append(None)
    n = len(items)
    rounds = []
    arr = items[:]
    for _ in range(n - 1):
        pairs = [(arr[i], arr[n - 1 - i]) for i in range(n // 2)]
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


def parse_names(raw_text):
    """줄바꿈으로 구분된 이름 목록을 정리한다 — 빈 줄은 버리고, 앞뒤
    공백을 없애고, 중복은 그대로 둔다(같은 이름을 쓰는 학생이 실제로
    있을 수 있어 임의로 지우지 않는다 — 대신 화면에서 "N번" 같은 순번을
    같이 보여줘 구분하게 한다)."""
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


# =============================================================================
# [신규] 학급 명단 관리 — 반·번호·이름·성별을 엑셀로 한 번 올려 두면
# 계속 유지되고, 여러 종목의 대진표를 만들 때마다 새로 입력할 필요가
# 없다.
# =============================================================================
class Student:
    __slots__ = ("sid", "grade", "cls", "num", "name", "gender", "role")

    def __init__(self, sid, grade, cls, num, name, gender="", role=""):
        self.sid = sid          # 내부 식별자(문자열) — "학년-반-번호-이름"으로 만든다
        self.grade = grade      # 학년
        self.cls = cls          # 반
        self.num = num          # 번호
        self.name = name        # 이름
        self.gender = gender    # 성별(선택)
        # [v44.4] 역할(선택) — "반장"·"부반장"·"출석부"·"칠판"·"실습실" 등
        # 자유 텍스트. 대진표 작성기는 이 값을 읽지도 쓰지도 않고(항상
        # 빈 문자열), 좌석표만 실제로 쓴다 — 명단 형식 자체는 두 미니앱이
        # 공유하되, 역할은 좌석표 쪽 관심사라서 굳이 별도 클래스로
        # 쪼개지 않고 선택 필드 하나로 얹었다.
        self.role = role

    def label(self):
        return f"{self.name}({self.num}번)"

    def to_dict(self):
        return {"sid": self.sid, "grade": self.grade, "cls": self.cls, "num": self.num,
                "name": self.name, "gender": self.gender, "role": self.role}

    @classmethod
    def from_dict(cls, d):
        return cls(d["sid"], d.get("grade", ""), d.get("cls", ""), d.get("num", ""),
                   d.get("name", ""), d.get("gender", ""), d.get("role", ""))


def read_roster_excel(path, with_role=False):
    """명단 엑셀을 읽는다. 1행은 머리글로 보고 건너뛰고, 2행부터
    학년·반·번호·이름·성별(성별은 없어도 됨) 순서로 읽는다. openpyxl이
    없으면 ImportError를 그대로 던진다(호출자가 안내를 보여준다).

    [v44.4] with_role=True면 6번째 컬럼을 역할로 읽는다(좌석표 전용 —
    대진표 작성기는 이 인자를 안 넘겨 기존 그대로 동작한다)."""
    import openpyxl   # noqa: 없으면 여기서 ImportError
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    students = []
    seen_sid = set()
    for r in range(2, ws.max_row + 1):
        grade = ws.cell(row=r, column=1).value
        cls = ws.cell(row=r, column=2).value
        num = ws.cell(row=r, column=3).value
        name = ws.cell(row=r, column=4).value
        gender = ws.cell(row=r, column=5).value
        role = ws.cell(row=r, column=6).value if with_role else None
        if grade is None and cls is None and num is None and name is None:
            continue
        grade_s = str(grade).strip() if grade is not None else ""
        cls_s = str(cls).strip() if cls is not None else ""
        num_s = str(num).strip() if num is not None else ""
        name_s = str(name).strip() if name is not None else ""
        if not name_s:
            continue
        sid = f"{grade_s}-{cls_s}-{num_s}-{name_s}"
        while sid in seen_sid:   # 완전히 같은 학년·반·번호·이름이 중복되면 구분자를 붙인다
            sid += "'"
        seen_sid.add(sid)
        students.append(Student(sid, grade_s, cls_s, num_s, name_s,
                                str(gender).strip() if gender is not None else "",
                                str(role).strip() if role is not None else ""))
    return students


def roster_to_json(students):
    import json
    return json.dumps([s.to_dict() for s in students], ensure_ascii=False)


ROSTER_HEADERS = ["학년", "반", "번호", "이름", "성별"]
ROSTER_HEADERS_WITH_ROLE = ROSTER_HEADERS + ["역할"]


def save_roster_template(path, sample_rows=3, with_role=False):
    """[v43.1] 명단 엑셀을 처음 만드는 사람을 위한 빈 양식 — read_roster_excel이
    기대하는 순서(학년·반·번호·이름·성별) 그대로 머리글만 있고, 보기용
    예시 몇 줄을 옅게 채워 둔다(성별은 비워도 되는 칸이라는 것도 예시로
    보여준다).

    [v44.4] with_role=True면 마지막에 "역할" 컬럼을 더해 6번째 칸에
    예시(반장·부반장 등)를 함께 보여준다(좌석표 전용 — 대진표 작성기는
    이 인자를 안 넘겨 기존 5칸 양식 그대로 받는다)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "명단"
    if with_role:
        ws.append(ROSTER_HEADERS_WITH_ROLE)
        samples = [
            ["1", "1", "1", "홍길동", "남", "반장"],
            ["1", "1", "2", "김영희", "여", "부반장"],
            ["1", "1", "3", "이철수", "", ""],
        ]
    else:
        ws.append(ROSTER_HEADERS)
        samples = [
            ["1", "1", "1", "홍길동", "남"],
            ["1", "1", "2", "김영희", "여"],
            ["1", "1", "3", "이철수", ""],
        ]
    for row in samples[:max(0, sample_rows)]:
        ws.append(row)
    wb.save(path)


def roster_from_json(raw):
    import json
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [Student.from_dict(d) for d in items]


def group_into_teams(students, team_size, seed=None):
    """학생 목록을 무작위로 team_size명씩 묶어 팀(조)을 만든다.
    team_size가 1이면 각자 혼자인 팀(단식/개인전)이 된다. 인원이 딱
    나누어떨어지지 않으면 **마지막 팀만** 인원이 더 적다(대진표에서는
    부전승과 같은 방식으로 처리된다). 팀(튜플: 학생 1명 이상)의 목록을
    돌려준다."""
    team_size = max(1, int(team_size))
    items = list(students)
    _rng(seed).shuffle(items)
    if team_size == 1:
        return [(s,) for s in items]
    teams = []
    i = 0
    while i < len(items):
        teams.append(tuple(items[i:i + team_size]))
        i += team_size
    return teams


def pair_doubles(students, seed=None):
    """(이전 버전과의 호환용) 2명씩 묶는 것은 group_into_teams(...,2,...)
    와 같다."""
    return group_into_teams(students, 2, seed=seed)


# =============================================================================
# [신규] 상태를 유지하는 대진표 — 경기 결과를 기록하면 승자가 다음
# 라운드로 자동으로 올라간다. 저장·불러오기가 가능해서, 대회를 여러
# 날에 나눠 진행해도 이어서 기록할 수 있다.
# =============================================================================
class Match:
    __slots__ = ("a", "b", "winner", "note", "sets", "saved", "side_sids")

    def __init__(self, a=None, b=None, winner=None, note="", sets=None, saved=False, side_sids=None):
        self.a = a              # entry id(문자열) 또는 None
        self.b = b
        self.winner = winner    # None | "a" | "b"
        self.note = note        # 화면에 보여줄 요약(세트 스코어, 예: "2:1")
        self.sets = sets or []  # [[a_score,b_score], ...] — 다시 열어 고칠 때 쓰는 원본 세트 점수
        self.saved = saved      # 누적 엑셀 기록 파일에 이미 저장했는지
        # [v39] 결과를 기록한 순간에 **실제로 뛴 학생**을 편별로 스냅숏으로
        # 남긴다: {"a": [sid, ...], "b": [sid, ...]}. 회차 중간에 결석·임시
        # 편성이 있어도, 이미 기록한 경기는 그때 구성 그대로 남고, 누적 엑셀과
        # 파트너 반복 집계도 이 스냅숏을 기준으로 한다. None이면(옛 기록)
        # 기본 팀원(Event.entries) 기준으로 처리한다.
        self.side_sids = side_sids

    def is_bye(self):
        return (self.a is None) != (self.b is None)

    def is_ready(self):
        """두 자리가 다 채워졌고 아직 결과가 없으면 "경기 가능" 상태."""
        return self.a is not None and self.b is not None and self.winner is None

    def to_dict(self):
        d = {"a": self.a, "b": self.b, "winner": self.winner, "note": self.note,
             "sets": self.sets, "saved": self.saved}
        if self.side_sids:
            d["side_sids"] = self.side_sids
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("a"), d.get("b"), d.get("winner"), d.get("note", ""),
                   sets=d.get("sets"), saved=bool(d.get("saved", False)),
                   side_sids=d.get("side_sids"))


def compute_sets_result(sets):
    """세트별 (A점수, B점수) 목록을 받아 (A가 이긴 세트 수, B가 이긴 세트 수,
    승자쪽("a"|"b"|None))을 돌려준다. 두 점수가 같은 세트는 무효(계산에서
    빠짐)."""
    a_sets = b_sets = 0
    for a, b in sets:
        if a is None or b is None:
            continue
        if a > b:
            a_sets += 1
        elif b > a:
            b_sets += 1
    if a_sets > b_sets:
        winner = "a"
    elif b_sets > a_sets:
        winner = "b"
    else:
        winner = None
    return a_sets, b_sets, winner


class Bracket:
    """entries(id -> 표시용 라벨 dict)를 받아 토너먼트 구조를 만든다.
    부전승은 만들 때 바로 다음 라운드로 넘겨 두고, 그 뒤로는
    record()로 경기 결과를 기록할 때마다 승자가 다음 라운드 자리를
    채운다."""

    def __init__(self, entries, order=None, seed=None):
        self.entries = dict(entries)     # id -> 라벨
        ids = list(order) if order is not None else list(entries.keys())
        if order is None:
            _rng(seed).shuffle(ids)
        self.rounds = self._build(ids)

    def _build(self, ids):
        """[버그 수정] 부전승(None)을 그냥 끝에 몰아서 붙이면, 부전승이
        2개 이상일 때 **둘이 같은 경기에 짝지어지는**(None vs None)
        말이 안 되는 경기가 생길 수 있다(6명일 때 실제로 이 문제가
        나는 걸 확인했다). 그래서 부전승 하나하나를 "마지막 몇 명의
        실제 참가자" 뒤에 각각 하나씩 붙여서, 부전승이 항상 서로 다른
        경기에 한 개씩만 들어가게 한다."""
        if not ids:
            return []
        n = len(ids)
        size = _next_power_of_two(n)
        byes = size - n
        bye_after = set(range(n - byes, n)) if byes else set()
        slots = []
        for idx, pid in enumerate(ids):
            slots.append(pid)
            if idx in bye_after:
                slots.append(None)
        round1 = [Match(slots[i], slots[i + 1]) for i in range(0, size, 2)]
        rounds = [round1]
        current_len = len(round1)
        while current_len > 1:
            rounds.append([Match() for _ in range(current_len // 2)])
            current_len //= 2
        # 부전승은 즉시 승자로 확정하고 다음 라운드로 전파한다.
        for i, m in enumerate(round1):
            if m.is_bye():
                m.winner = "a" if m.a is not None else "b"
                self._propagate_from(rounds, 0, i)
        return rounds

    def _propagate_from(self, rounds, r, i):
        if r + 1 >= len(rounds):
            return
        m = rounds[r][i]
        winner_id = m.a if m.winner == "a" else m.b
        nxt = rounds[r + 1][i // 2]
        if i % 2 == 0:
            nxt.a = winner_id
        else:
            nxt.b = winner_id
        if nxt.is_bye():
            nxt.winner = "a" if nxt.a is not None else "b"
            self._propagate_from(rounds, r + 1, i // 2)

    def record(self, r, i, winner_side, note="", sets=None):
        """r라운드 i번째 경기의 승자를 기록하고, 다음 라운드로 전파한다.
        winner_side는 "a" 또는 "b"."""
        m = self.rounds[r][i]
        m.winner = winner_side
        m.note = note
        m.sets = sets or []
        m.saved = False   # 결과가 바뀌었으니 누적 기록 파일에 다시 저장해야 한다
        self._propagate_from(self.rounds, r, i)

    def clear_result(self, r, i):
        """기록을 취소한다 — 잘못 입력했을 때 되돌리는 용도. 이 경기
        결과에 의존해 채워졌던 다음 라운드 이후의 자리도 함께 비운다."""
        m = self.rounds[r][i]
        m.winner = None
        m.note = ""
        m.sets = []
        m.saved = False
        self._clear_forward(r, i)

    def _clear_forward(self, r, i):
        if r + 1 >= len(self.rounds):
            return
        nxt = self.rounds[r + 1][i // 2]
        if i % 2 == 0:
            nxt.a = None
        else:
            nxt.b = None
        if nxt.winner is not None:
            nxt.winner = None
            nxt.note = ""
            self._clear_forward(r + 1, i // 2)

    def champion(self):
        if not self.rounds:
            return None
        final = self.rounds[-1][0]
        if final.winner == "a":
            return final.a
        if final.winner == "b":
            return final.b
        return None

    def label(self, entry_id):
        return self.entries.get(entry_id, entry_id) if entry_id else None

    def to_dict(self):
        return {
            "entries": self.entries,
            "rounds": [[m.to_dict() for m in rnd] for rnd in self.rounds],
        }

    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.entries = dict(d.get("entries", {}))
        obj.rounds = [[Match.from_dict(md) for md in rnd] for rnd in d.get("rounds", [])]
        return obj


class League:
    """모든 참가자가 서로 한 번씩 겨루는 일정(리그전). Bracket과 달리
    "승자가 다음 라운드로 올라가는" 구조가 없어서 각 라운드는 독립적인
    경기 목록일 뿐이지만, 경기마다 결과(승자·점수)는 똑같이 기록할 수
    있다(Match를 그대로 재사용한다)."""

    def __init__(self, entries, order=None, seed=None):
        self.entries = dict(entries)
        ids = list(order) if order is not None else list(entries.keys())
        if order is None:
            _rng(seed).shuffle(ids)
        self.rounds = self._build(ids)

    def _build(self, ids):
        items = list(ids)
        if len(items) < 2:
            return []
        if len(items) % 2 == 1:
            items = items + [None]
        n = len(items)
        rounds = []
        arr = items[:]
        for _ in range(n - 1):
            rounds.append([Match(arr[i], arr[n - 1 - i]) for i in range(n // 2)])
            arr = [arr[0]] + [arr[-1]] + arr[1:-1]
        return rounds

    def record(self, r, i, winner_side, note="", sets=None):
        m = self.rounds[r][i]
        m.winner = winner_side
        m.note = note
        m.sets = sets or []
        m.saved = False

    def clear_result(self, r, i):
        m = self.rounds[r][i]
        m.winner = None
        m.note = ""
        m.sets = []
        m.saved = False

    def label(self, entry_id):
        return self.entries.get(entry_id, entry_id) if entry_id else None

    def to_dict(self):
        return {"entries": self.entries, "rounds": [[m.to_dict() for m in rnd] for rnd in self.rounds]}

    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.entries = dict(d.get("entries", {}))
        obj.rounds = [[Match.from_dict(md) for md in rnd] for rnd in d.get("rounds", [])]
        return obj


FORMAT_TOURNAMENT = "tournament"
FORMAT_LEAGUE = "league"


class Event:
    """종목 하나(예: "배드민턴_1반_리그전_20260918"). 참가자·형식(토너먼트/
    리그전)·팀당 인원·대진표 상태를 한데 묶어 관리한다. 여러 종목(수업
    시간)을 만들어도 서로 독립적으로 계속 남아 있다."""

    def __init__(self, name, format, team_size, entries, bracket, sport="", unassigned_sids=None,
                level_balance=False):
        self.name = name
        self.format = format        # FORMAT_TOURNAMENT | FORMAT_LEAGUE
        self.team_size = team_size  # 팀(조) 하나당 인원 — 1이면 개인전
        self.entries = entries      # id -> [Student.sid, ...]
        self.bracket = bracket      # Bracket(토너먼트) 또는 League(리그전)
        self.sport = sport          # 누적 기록에 정확한 종목명을 남기려고 따로 저장
        # [v38.1] 팀당 인원으로 안 나누어떨어져 팀을 못 이룬 학생들의 sid.
        # 예전에는 이 학생들을 "혼자만의 팀"으로 대진표에 억지로 끼워
        # 넣었는데, 그러면 "학생 추가 배정"으로 다른 팀에 옮긴 뒤에도
        # 원래의 1인 팀 기록이 대진표에 그대로 남는 문제가 있었다. 아예
        # 대진표에 넣지 않고 여기 따로 들고 있다가, 배정되면 이 목록에서
        # 빠지고 그제서야 진짜 팀(entries)에 들어간다.
        self.unassigned_sids = list(unassigned_sids or [])
        # [v39] "팀 레벨 균형"으로 만든 종목인지 — 그렇다면 출석 조정에서
        # 임시 편성 옵션도 팀 평균이 안 깨지는 것만 보여준다.
        self.level_balance = bool(level_balance)

    def entry_student_ids(self, entry_id):
        return self.entries.get(entry_id, [])

    def to_dict(self):
        return {
            "name": self.name, "format": self.format, "team_size": self.team_size,
            "entries": self.entries, "bracket": self.bracket.to_dict(), "sport": self.sport,
            "unassigned_sids": self.unassigned_sids, "level_balance": self.level_balance,
        }

    @classmethod
    def from_dict(cls, d):
        fmt = d.get("format", FORMAT_TOURNAMENT)
        bracket_cls = League if fmt == FORMAT_LEAGUE else Bracket
        return cls(d.get("name", ""), fmt, int(d.get("team_size", 1)),
                   dict(d.get("entries", {})), bracket_cls.from_dict(d.get("bracket", {})),
                   sport=d.get("sport", ""), unassigned_sids=d.get("unassigned_sids", []),
                   level_balance=d.get("level_balance", False))


def build_event(name, students, format=FORMAT_TOURNAMENT, team_size=1, seed=None, sport="",
                partnership_counts=None, level_balance=False, tiers_by_sid=None):
    """참가 학생 목록으로 새 종목(Event)을 만든다. team_size명씩 묶어
    그 팀(조)을 대진표/리그 참가 단위로 쓰고, format에 따라 토너먼트
    대진표 또는 리그 일정을 만든다.

    팀을 묶는 방식은 셋 중 하나다(먼저 해당하는 것을 쓴다):
    1. level_balance=True — 팀 평균 레벨이 2에 가깝도록 짠다(tiers_by_sid 필요).
    2. partnership_counts가 있으면 — 과거에 덜 겹친 조합을 우선한다.
    3. 그 외 — 무작위로 묶는다."""
    entries = {}
    labels = {}
    _actual_level_balance = bool(level_balance and team_size > 1)
    if _actual_level_balance:
        teams = group_into_teams_by_level(students, team_size, tiers_by_sid or {}, seed=seed)
    elif partnership_counts:
        teams = group_into_teams_avoiding_repeats(students, team_size, partnership_counts, seed=seed)
    else:
        teams = group_into_teams(students, team_size, seed=seed)

    unassigned_sids = []
    if team_size > 1 and teams and len(teams[-1]) < team_size:
        unassigned_sids = [s.sid for s in teams[-1]]
        teams = teams[:-1]

    for i, team in enumerate(teams):
        entry_id = f"e{i}"
        entries[entry_id] = [s.sid for s in team]
        labels[entry_id] = "\n".join(s.label() for s in team)
    order = list(entries.keys())
    _rng(seed).shuffle(order)
    bracket = League(labels, order=order) if format == FORMAT_LEAGUE else Bracket(labels, order=order)
    return Event(name, format, team_size, entries, bracket, sport=sport, unassigned_sids=unassigned_sids,
                level_balance=_actual_level_balance)


def roster_events_to_json(events):
    import json
    return json.dumps([e.to_dict() for e in events], ensure_ascii=False)


def roster_events_from_json(raw):
    import json
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [Event.from_dict(d) for d in items]


# =============================================================================
# [신규] 종목 선택 + 자동 제목 생성 — "배드민턴_1,2반_리그전_20260918" 형식
# =============================================================================
SPORT_OPTIONS = ["배드민턴", "탁구", "농구", "기타"]
SPORT_OTHER = "기타"

FORMAT_SUFFIX = {FORMAT_TOURNAMENT: "토너먼트전", FORMAT_LEAGUE: "리그전"}


def classes_label(students):
    """참가 학생들의 학년·반을 모아 "1학년1반,2학년3반" 형태로 만든다
    (중복 제거, 학년·반 모두 숫자면 숫자 기준으로 정렬)."""
    def _key(v):
        return (0, int(v)) if v.isdigit() else (1, v)
    combos = sorted({(s.grade, s.cls) for s in students}, key=lambda gc: (_key(gc[0]), _key(gc[1])))
    if not combos:
        return ""
    return ",".join(f"{g}학년{c}반" for g, c in combos)


def build_event_name(sport, students, format, date_str=None):
    """종목·참가 학급·형식·날짜를 조합해 자동으로 종목 이름을 만든다.
    예: 배드민턴_1,2반_리그전_20260918"""
    import datetime
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y%m%d")
    cls_part = classes_label(students) or "0명"
    fmt_part = FORMAT_SUFFIX.get(format, format)
    return f"{sport}_{cls_part}_{fmt_part}_{date_str}"


# =============================================================================
# [신규] 누적 기록 엑셀 파일 — 학기 내내 이어서 기록하는 물리적 파일.
# 한 경기(매치)에 여러 명이 참가하면(복식·단체전), **참가한 학생 한 명당
# 한 줄**로 적는다 — 그래야 나중에 "이 학생이 이 종목에서 몇 승 몇 패
# 했는지"를 학생 단위로 바로 집계할 수 있다.
# =============================================================================
HISTORY_HEADERS = ["날짜", "종목", "형식", "학년", "반", "번호", "이름",
                   "결과", "세트결과", "세트스코어", "같은편", "상대"]


def build_history_rows(sport, format, date_str, roster_by_sid, side_sids, opp_sids,
                       sets, is_side_a):
    """한 경기에서 한쪽 편(side_sids)에 대한 기록 행들을 만든다(그 편에
    속한 학생 한 명당 한 줄). roster_by_sid: {sid: Student}.

    [버그 수정] 예전에는 "세트결과"가 대진표 위치(참가자 A·B) 기준으로
    고정되어 있어서, 실제 승자가 B였을 때도 승리한 줄에 A 기준 숫자
    (예: "0:2")가 그대로 찍혀 헷갈렸다("패"인데 세트결과가 "2:1"로
    보이는 등). 이제는 **이 줄(내 편) 기준으로 다시 계산**해서, 어느
    줄이든 "결과=승"이면 세트결과·세트스코어의 앞 숫자가 항상 내가
    이긴 쪽이 되도록 맞춘다 — sets는 항상 (참가자 A 점수, 참가자 B
    점수) 순서로 들어오고, is_side_a가 False면 그 순서를 뒤집어 "내
    점수, 상대 점수" 순서로 바꾼 뒤 계산한다."""
    my_sets = list(sets) if is_side_a else [(b, a) for a, b in sets]
    my_wins = sum(1 for a, b in my_sets if a > b)
    opp_wins = sum(1 for a, b in my_sets if b > a)
    result = "승" if my_wins > opp_wins else ("패" if opp_wins > my_wins else "무")
    set_result_label = f"{my_wins}:{opp_wins}"
    set_score_label = ", ".join(f"{a}:{b}" for a, b in my_sets)

    rows = []
    teammates = [roster_by_sid[sid].name for sid in side_sids if sid in roster_by_sid]
    opponents = [roster_by_sid[sid].name for sid in opp_sids if sid in roster_by_sid]
    for sid in side_sids:
        s = roster_by_sid.get(sid)
        if s is None:
            continue
        mates = [t for t in teammates if t != s.name]
        rows.append({
            "날짜": date_str, "종목": sport, "형식": FORMAT_SUFFIX.get(format, format),
            "학년": s.grade, "반": s.cls, "번호": s.num, "이름": s.name,
            "결과": result, "세트결과": set_result_label, "세트스코어": set_score_label,
            "같은편": ", ".join(mates), "상대": ", ".join(opponents),
        })
    return rows


def append_history(path, rows):
    """누적 기록 엑셀 파일에 새 행들을 이어 붙인다. 파일이 없으면
    머리글과 함께 새로 만들고, 있으면 **기존 내용은 그대로 두고** 그
    다음 줄부터 이어서 적는다(그래서 이전 학기·이전 컴퓨터에서 쓰던
    파일을 그대로 골라도 데이터가 안전하다).

    [버그 수정] "학년"·"세트스코어" 컬럼을 새로 추가하면서, 그 전에
    이미 만들어 둔 파일(옛 머리글)에 그냥 새 형식으로 이어 붙이면 열
    순서가 안 맞아 버린다. 그래서 열 순서가 다르면 **자동으로
    맞춰준다** — 기존 줄은 그대로 두고 새 컬럼(학년·세트스코어) 자리만
    빈칸으로 채워 넣는다(그 전 기록에는 학년을 안 모아서 실제 값을
    알 수 없다 — 빈칸으로 남는다)."""
    import openpyxl   # noqa: 없으면 여기서 ImportError
    import os
    if os.path.exists(path):
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        old_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        if old_headers != HISTORY_HEADERS:
            _migrate_history_sheet(ws, old_headers)
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(HISTORY_HEADERS)
    for row in rows:
        ws.append([row.get(h, "") for h in HISTORY_HEADERS])
    wb.save(path)


def _migrate_history_sheet(ws, old_headers):
    """옛 머리글로 저장된 시트를 지금 HISTORY_HEADERS 순서로 맞춘다.
    기존 데이터 줄은 이름표를 보고 제자리로 옮기고, 새로 생긴 컬럼은
    빈칸으로 둔다."""
    old_rows = []
    for r in range(2, ws.max_row + 1):
        values = [ws.cell(row=r, column=c).value for c in range(1, len(old_headers) + 1)]
        if all(v is None for v in values):
            continue
        old_rows.append(dict(zip(old_headers, values)))
    ws.delete_rows(1, ws.max_row)
    ws.append(HISTORY_HEADERS)
    for row in old_rows:
        ws.append([row.get(h, "") for h in HISTORY_HEADERS])


def read_history_stats(path, sport=None):
    """누적 기록 엑셀을 읽어 학생별(학년+반+번호+이름 기준) 승패 집계를
    돌려준다: {(학년,반,번호,이름): {"wins": n, "losses": n}}. sport를
    주면 그 종목만 집계한다. 파일이 없으면 빈 dict."""
    import openpyxl
    import os
    stats = {}
    if not path or not os.path.exists(path):
        return stats
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    try:
        col = {h: headers.index(h) + 1 for h in HISTORY_HEADERS}
    except ValueError:
        return stats
    for r in range(2, ws.max_row + 1):
        row_sport = ws.cell(row=r, column=col["종목"]).value
        if sport is not None and row_sport != sport:
            continue
        grade = ws.cell(row=r, column=col["학년"]).value
        cls = ws.cell(row=r, column=col["반"]).value
        num = ws.cell(row=r, column=col["번호"]).value
        name = ws.cell(row=r, column=col["이름"]).value
        result = ws.cell(row=r, column=col["결과"]).value
        if name is None:
            continue
        key = (str(grade) if grade is not None else "", str(cls) if cls is not None else "",
              str(num) if num is not None else "", name)
        entry = stats.setdefault(key, {"wins": 0, "losses": 0})
        if result == "승":
            entry["wins"] += 1
        elif result == "패":
            entry["losses"] += 1
    return stats


# =============================================================================
# [신규] 실력 등급 — 자동 등급(누적 승률)과 교사가 직접 매긴 수동 등급을
# **완전히 따로** 관리한다. 항상 **수동 등급이 우선**이다 — 특정 등급의
# 상대와만 계속 겨루면 승률이 실제 실력과 다르게 왜곡될 수 있어서
# (계속 약한 상대만 만나면 승률이 실제보다 높게, 강한 상대만 만나면
# 낮게 나옴), 자동 등급은 "참고용"으로만 쓰고 최종 판단은 교사가 직접
# 조정하게 한다.
# =============================================================================
TIER_HIGH = "상"
TIER_MID = "중"
TIER_LOW = "하"
TIER_ORDER = [TIER_HIGH, TIER_MID, TIER_LOW]
TIER_MIN_GAMES = 3   # 이 경기 수 미만이면 승률로 등급을 추정하지 않는다(표본 부족)


def compute_auto_tier(wins, losses):
    """승패 기록으로 등급을 "추정"한다(참고용). 경기 수가 TIER_MIN_GAMES
    보다 적으면 아직 판단하기엔 데이터가 부족하다고 보고 None을
    돌려준다."""
    total = wins + losses
    if total < TIER_MIN_GAMES:
        return None
    rate = wins / total
    if rate >= 0.6:
        return TIER_HIGH
    if rate <= 0.4:
        return TIER_LOW
    return TIER_MID


def effective_tier(manual_tier, auto_tier):
    """실제로 대진표를 짤 때 쓰는 등급 — **수동 등급이 있으면 항상 그걸
    쓴다.** 수동 등급이 없을 때만 자동(참고용) 등급을 대신 쓴다."""
    return manual_tier or auto_tier


TIER_SCORE = {TIER_HIGH: 3, TIER_MID: 2, TIER_LOW: 1}
LEVEL_TARGET = 2.0
LEVEL_MIN, LEVEL_MAX = 1.5, 2.5


def tier_score(tier):
    """상=3, 중=2, 하=1점. 등급을 모르면(교사·자동 등급 둘 다 없음) 중간값
    2점으로 본다 — 데이터가 없다고 그 학생을 셈에서 빼면 오히려 팀 배정이
    왜곡된다."""
    return TIER_SCORE.get(tier, 2)


def group_into_teams_by_level(students, team_size, tiers_by_sid, seed=None):
    """[v39] "팀 레벨 평균" — 모든 팀의 평균 레벨(상=3/중=2/하=1)이 2에
    가깝도록(1.5~2.5 안으로) 팀을 짠다. 점수로 정렬한 뒤 "뱀 순서"(1팀→
    2팀→…→마지막 팀→마지막 팀→…→1팀→…)로 나눠 담으면 팀별 합계가
    자연히 비슷해지고, 그래도 범위를 벗어난 팀이 있으면 가장 높은 팀과
    가장 낮은 팀 사이에서 극단값 한 명씩을 맞바꿔 가며 좁힌다(전역
    최적은 아니지만 실전에는 충분하다). 인원이 team_size로 안
    나누어떨어지면 남는 인원은 build_event가 처리하도록 마지막 팀으로
    돌려준다(그 팀만 team_size보다 작을 수 있음)."""
    if team_size <= 1:
        return group_into_teams(students, team_size, seed=seed)
    rng = _rng(seed)
    pool = list(students)
    rng.shuffle(pool)   # 같은 점수 안에서는 무작위 — 매번 똑같은 조합만 나오지 않게
    pool.sort(key=lambda s: tier_score(tiers_by_sid.get(s.sid)))

    n_teams = len(pool) // team_size
    if n_teams == 0:
        return [tuple(pool)]
    usable = pool[:n_teams * team_size]
    leftover = pool[n_teams * team_size:]

    teams = [[] for _ in range(n_teams)]
    forward = True
    idx = 0
    while idx < len(usable):
        order = range(n_teams) if forward else range(n_teams - 1, -1, -1)
        for t in order:
            if idx >= len(usable):
                break
            teams[t].append(usable[idx])
            idx += 1
        forward = not forward

    def team_avg(team):
        return sum(tier_score(tiers_by_sid.get(s.sid)) for s in team) / len(team)

    for _ in range(n_teams * 4):
        avgs = [team_avg(t) for t in teams]
        lo = min(range(n_teams), key=lambda i: avgs[i])
        hi = max(range(n_teams), key=lambda i: avgs[i])
        if LEVEL_MIN <= avgs[lo] and avgs[hi] <= LEVEL_MAX:
            break
        if avgs[hi] - avgs[lo] < 1e-9:
            break
        hi_student = max(teams[hi], key=lambda s: tier_score(tiers_by_sid.get(s.sid)))
        lo_student = min(teams[lo], key=lambda s: tier_score(tiers_by_sid.get(s.sid)))
        if hi_student is lo_student:
            break
        teams[hi].remove(hi_student)
        teams[lo].remove(lo_student)
        teams[hi].append(lo_student)
        teams[lo].append(hi_student)

    result = [tuple(t) for t in teams]
    if leftover:
        result.append(tuple(leftover))
    return result


def team_level_average(team, tiers_by_sid):
    return sum(tier_score(tiers_by_sid.get(s.sid)) for s in team) / len(team) if team else 0.0


def manual_tiers_to_json(tiers):
    """{(종목, sid): 등급} -> JSON. QSettings에 저장하는 용도."""
    import json
    return json.dumps({f"{sport}|{sid}": tier for (sport, sid), tier in tiers.items()}, ensure_ascii=False)


def manual_tiers_from_json(raw):
    import json
    if not raw:
        return {}
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    result = {}
    for key, tier in items.items():
        if "|" not in key:
            continue
        sport, sid = key.split("|", 1)
        result[(sport, sid)] = tier
    return result


def read_partnership_counts(path, sport=None):
    """누적 기록 엑셀의 "같은편" 칸을 읽어, 학생 두 명(이름 기준)이 지금
    까지 몇 번이나 같은 편이었는지 센다. {frozenset({이름1,이름2}): 횟수}.
    (한 경기당 그 편에 속한 학생들의 줄마다 서로를 "같은편"으로 적어
    두니, 한 번의 실제 파트너 경험이 2로 집계된다 — 그래도 어차피
    상대적인 비교에만 쓰이니 결과에는 영향이 없다.)"""
    import openpyxl
    import os
    counts = {}
    if not path or not os.path.exists(path):
        return counts
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    try:
        col = {h: headers.index(h) + 1 for h in HISTORY_HEADERS}
    except ValueError:
        return counts
    for r in range(2, ws.max_row + 1):
        row_sport = ws.cell(row=r, column=col["종목"]).value
        if sport is not None and row_sport != sport:
            continue
        name = ws.cell(row=r, column=col["이름"]).value
        mates_raw = ws.cell(row=r, column=col["같은편"]).value
        if not name or not mates_raw:
            continue
        for mate in str(mates_raw).split(","):
            mate = mate.strip()
            if not mate:
                continue
            key = frozenset({name, mate})
            counts[key] = counts.get(key, 0) + 1
    return counts


def group_into_teams_avoiding_repeats(students, team_size, partnership_counts=None, seed=None):
    """team_size명씩 묶는다. partnership_counts가 있으면(과거에 이미
    몇 번 같은 편이었는지), **가장 적게 같은 편이었던 학생들끼리** 먼저
    묶는 탐욕적(greedy) 방법으로 짠다 — 완벽한 최적해는 아니지만,
    매번 무작위로만 섞을 때보다 같은 짝이 반복되는 걸 눈에 띄게
    줄인다."""
    team_size = max(1, int(team_size))
    rng = _rng(seed)
    items = list(students)
    rng.shuffle(items)
    if team_size == 1 or not partnership_counts:
        teams = []
        i = 0
        while i < len(items):
            teams.append(tuple(items[i:i + team_size]))
            i += team_size
        return teams

    def pair_cost(a, b):
        return partnership_counts.get(frozenset({a.name, b.name}), 0)

    remaining = items[:]
    teams = []
    while remaining:
        base = remaining.pop(0)
        team = [base]
        while len(team) < team_size and remaining:
            costs = [sum(pair_cost(m, cand) for m in team) for cand in remaining]
            min_cost = min(costs)
            candidate_idxs = [i for i, c in enumerate(costs) if c == min_cost]
            pick_i = rng.choice(candidate_idxs)
            team.append(remaining.pop(pick_i))
        teams.append(tuple(team))
    return teams


def split_by_tier(students, tiers_by_sid):
    """학생들을 등급별로 나눈다. tiers_by_sid: {sid: 등급_또는_None}.
    등급을 모르는(None) 학생은 "중"으로 취급한다(가장 무난한 기본값 —
    실제로는 참가자 탭에서 언제든 손으로 등급을 지정해 조정할 수
    있다). {등급: [학생, ...]} 형태로 돌려준다."""
    groups = {}
    for s in students:
        tier = tiers_by_sid.get(s.sid) or TIER_MID
        groups.setdefault(tier, []).append(s)
    return groups


# =============================================================================
# [v38] 라운드 관리 — 시리즈(종목+반) 단위로 여러 라운드를 계속 이어간다.
#
# 한 라운드 = 팀 구성 + 그 팀들의 대진표(또는 리그) + 경기 결과(지금까지의
# Event 그대로). 한 시리즈(같은 종목·같은 반)는 학기 내내 라운드를 계속
# 쌓아 간다. 수업이 한 교시에 안 끝나면 진행 중인 라운드를 파일에 그대로
# 저장해 두고, 다음 시간에 같은 시리즈를 불러오면 이어서 기록할 수 있다.
# 새 라운드를 짤 때는 "이 시리즈의 모든 이전 라운드"에서 누가 몇 번 같은
# 편이었는지를 보고 팀을 짠다(엑셀 저장 여부와 무관하게 항상 정확하다).
# =============================================================================
import uuid as _uuid


class Round:
    """시리즈 안의 라운드 하나. 실제 팀 구성·대진표·결과는 그대로 Event가
    들고 있고, Round는 그 위에 "이 라운드를 구분하는 id"만 얹는다(다른
    컴퓨터의 시리즈 파일과 합칠 때 같은 라운드인지 구분하는 열쇠).

    events는 리스트다 — 수준별 분리를 켜면 한 라운드 안에 등급별
    대진표가 여러 개(상/중/하) 생기기 때문이다. 보통은 원소 1개."""

    def __init__(self, events, round_id=None, adjustments=None):
        self.id = round_id or _uuid.uuid4().hex[:12]
        self.events = list(events)
        # [v39] 날짜별 출석 조정: [{"date": "YYYYMMDD", "event_index": 0,
        #   "absent": [sid, ...], "transfers": [{"sid","from","to"}, ...]}, ...]
        # "오늘만" 적용되는 조정이라 날짜로 묶는다 — 다음 수업일에 같은
        # 회차를 열면 그날 조정이 없으므로 기본 팀으로 자동 복귀한다.
        self.adjustments = list(adjustments or [])

    def adjustment_for(self, date_str, event_index):
        for adj in self.adjustments:
            if adj.get("date") == date_str and int(adj.get("event_index", 0)) == event_index:
                return adj
        return None

    def set_adjustment(self, date_str, event_index, absent, transfers):
        """같은 날짜·이벤트의 조정이 있으면 통째로 바꾼다(하루 하나)."""
        self.adjustments = [a for a in self.adjustments
                            if not (a.get("date") == date_str and int(a.get("event_index", 0)) == event_index)]
        self.adjustments.append({"date": date_str, "event_index": event_index,
                                 "absent": list(absent), "transfers": list(transfers)})

    def all_matches(self):
        """이 라운드의 실제 경기(부전승 제외)를 이벤트·행·열과 함께 전부
        모은다: [(event_index, r, i, Match), ...]."""
        out = []
        for ei, ev in enumerate(self.events):
            for r, row in enumerate(ev.bracket.rounds):
                for i, m in enumerate(row):
                    if not m.is_bye():
                        out.append((ei, r, i, m))
        return out

    def progress(self):
        """(끝난 경기 수, 전체 경기 수)."""
        matches = self.all_matches()
        done = sum(1 for _e, _r, _i, m in matches if m.winner is not None)
        return done, len(matches)

    def is_completed(self):
        done, total = self.progress()
        return done == total

    def to_dict(self):
        return {"id": self.id, "events": [e.to_dict() for e in self.events],
                "adjustments": self.adjustments}

    @classmethod
    def from_dict(cls, d):
        return cls([Event.from_dict(ed) for ed in d.get("events", [])], round_id=d.get("id"),
                   adjustments=d.get("adjustments", []))


class Series:
    """종목 하나 + 반 하나를 한 학기 내내 이어가는 단위. rounds는 만든
    순서대로 쌓인다(가장 최근 라운드가 마지막)."""

    def __init__(self, key, sport, class_label, rounds=None):
        self.key = key                  # 파일 이름에도 쓰는 내부 식별자
        self.sport = sport
        self.class_label = class_label  # 사람이 보는 "1학년 3반" 같은 표시용
        self.rounds = rounds or []

    def to_dict(self):
        return {"key": self.key, "sport": self.sport, "class_label": self.class_label,
                "rounds": [r.to_dict() for r in self.rounds]}

    @classmethod
    def from_dict(cls, d):
        return cls(d["key"], d.get("sport", ""), d.get("class_label", ""),
                   rounds=[Round.from_dict(rd) for rd in d.get("rounds", [])])

    def partnership_counts(self, roster_by_sid):
        """이 시리즈의 모든 라운드에서, 학생 두 명(이름 기준)이 몇 번이나
        같은 편이었는지 센다 — group_into_teams_avoiding_repeats가 쓰는
        것과 같은 {frozenset({이름1,이름2}): 횟수} 형태."""
        counts = {}
        for rnd in self.rounds:
            for ev in rnd.events:
                # [v39] 실제로 같이 뛴 짝(경기 스냅숏)을 우선 쓴다 — 회차 안에서
                # 같은 짝은 한 번만 센다. 아직 한 경기도 기록 안 한 이벤트는
                # 기본 팀 구성으로 센다(팀은 짜였으니 반복 회피 대상이다).
                pairs = set()
                for row in ev.bracket.rounds:
                    for m in row:
                        if m.winner is None or not m.side_sids:
                            continue
                        for side in ("a", "b"):
                            names = [roster_by_sid[sid].name for sid in m.side_sids.get(side, [])
                                     if sid in roster_by_sid]
                            for a in range(len(names)):
                                for b in range(a + 1, len(names)):
                                    pairs.add(frozenset({names[a], names[b]}))
                if not pairs:
                    for sids in ev.entries.values():
                        names = [roster_by_sid[sid].name for sid in sids if sid in roster_by_sid]
                        for a in range(len(names)):
                            for b in range(a + 1, len(names)):
                                pairs.add(frozenset({names[a], names[b]}))
                for key in pairs:
                    counts[key] = counts.get(key, 0) + 1
        return counts


def series_key(sport, students):
    """종목+반으로 시리즈를 식별하는 내부 키. 학급이 여러 개 섞여 있으면
    그대로 다 붙는다(반별 수업이 기본이라 보통은 하나만 나온다)."""
    return f"{sport}_{classes_label(students) or '미상'}"


def _sanitize_filename(text):
    import re
    return re.sub(r'[\\/:*?"<>|]', "_", text).strip() or "series"


def series_file_path(history_path, key):
    """누적 기록 엑셀과 같은 폴더에 시리즈 파일을 둔다 — 학기 내내 같은
    폴더에서 관리되고, 다른 컴퓨터로 옮길 때도 엑셀과 함께 챙기면 된다."""
    if not history_path:
        return None
    base_dir = os.path.dirname(os.path.abspath(history_path))
    return os.path.join(base_dir, f"시리즈_{_sanitize_filename(key)}.json")


def list_series_files(history_path):
    """누적 기록 엑셀과 같은 폴더에서 시리즈 파일을 전부 찾아 (key, path)
    목록으로 돌려준다."""
    if not history_path:
        return []
    base_dir = os.path.dirname(os.path.abspath(history_path))
    if not os.path.isdir(base_dir):
        return []
    out = []
    for fn in sorted(os.listdir(base_dir)):
        if fn.startswith("시리즈_") and fn.endswith(".json"):
            out.append((fn[len("시리즈_"):-len(".json")], os.path.join(base_dir, fn)))
    return out


def save_series(path, series):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(series.to_dict(), f, ensure_ascii=False, indent=1)


def load_series(path):
    import json
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Series.from_dict(data)


def merge_series(local, other):
    """다른 컴퓨터에서 가져온 시리즈(other)를 이 시리즈(local)에 합친다.
    라운드는 id로 맞춰 보고, local에 없는 라운드는 통째로 가져온다. 같은
    라운드 안에서는 경기별로 비교해서, local이 비어 있는데 other에 결과가
    있으면 채워 넣는다. **양쪽 다 결과가 있는데 서로 다르면 자동으로
    덮어쓰지 않고** 충돌 목록으로 돌려준다 — 어느 쪽을 남길지는 화면에서
    교사가 고른다.

    반환: (added_rounds, filled_matches, conflicts)
    conflicts의 각 항목: {"round_id", "r", "i", "label", "local", "other"}
    (local/other는 각각 {"winner","sets"} — 화면에 두 결과를 나란히
    보여줄 때 쓴다)
    """
    local_by_id = {rnd.id: rnd for rnd in local.rounds}
    added_rounds = 0
    filled_matches = 0
    conflicts = []

    for ornd in other.rounds:
        lrnd = local_by_id.get(ornd.id)
        if lrnd is None:
            local.rounds.append(ornd)
            local_by_id[ornd.id] = ornd
            added_rounds += 1
            continue

        for ei, oev in enumerate(ornd.events):
            if ei >= len(lrnd.events):
                continue
            lev = lrnd.events[ei]
            for r, orow in enumerate(oev.bracket.rounds):
                if r >= len(lev.bracket.rounds):
                    continue
                for i, om in enumerate(orow):
                    if i >= len(lev.bracket.rounds[r]):
                        continue
                    if om.winner is None:
                        continue
                    lm = lev.bracket.rounds[r][i]
                    if lm.winner is None:
                        lm.winner, lm.note, lm.sets, lm.saved = om.winner, om.note, om.sets, om.saved
                        filled_matches += 1
                    elif lm.winner != om.winner or [list(x) for x in lm.sets] != [list(x) for x in om.sets]:
                        conflicts.append({
                            "round_id": ornd.id, "event_index": ei, "r": r, "i": i,
                            "label": lev.bracket.label(om.a) if om.a else "",
                            "local": {"winner": lm.winner, "sets": list(lm.sets)},
                            "other": {"winner": om.winner, "sets": list(om.sets)},
                        })
    return added_rounds, filled_matches, conflicts


def apply_conflict_choice(local, conflict, choice):
    """merge_series가 돌려준 충돌(conflict dict) 하나를 해결한다. choice가
    'other'면 그 경기를 other 쪽 값으로 덮어쓰고, 'local'이면 이미 local
    값 그대로이므로 아무 것도 하지 않는다."""
    if choice != "other":
        return
    for rnd in local.rounds:
        if rnd.id == conflict["round_id"]:
            m = rnd.events[conflict["event_index"]].bracket.rounds[conflict["r"]][conflict["i"]]
            m.winner = conflict["other"]["winner"]
            m.sets = list(conflict["other"]["sets"])
            m.saved = False
            return


def effective_members(event, rnd, date_str, event_index=0):
    """[v39] 그날 실제로 뛰는 팀원: 기본 팀원(entries) − 그날 결석자 + 그날
    임시 합류자. rnd.adjustment_for(date)가 없으면 기본 팀원 그대로."""
    members = {eid: list(sids) for eid, sids in event.entries.items()}
    adj = rnd.adjustment_for(date_str, event_index) if rnd is not None else None
    if not adj:
        return members
    absent = set(adj.get("absent", []))
    for eid in members:
        members[eid] = [sid for sid in members[eid] if sid not in absent]
    for t in adj.get("transfers", []):
        sid, src, dst = t.get("sid"), t.get("from"), t.get("to")
        if src in members and sid in members[src]:
            members[src].remove(sid)
        members.setdefault(dst, [])
        if sid not in members[dst]:
            members[dst].append(sid)
    return members


def match_side_sids(event, m, side):
    """경기의 한 편(a/b)에 실제로 뛴 학생 — 스냅숏이 있으면 그것, 없으면
    기본 팀원(옛 기록 호환)."""
    if m.side_sids and side in m.side_sids:
        return list(m.side_sids[side])
    entry_id = m.a if side == "a" else m.b
    return list(event.entry_student_ids(entry_id))


# =============================================================================
# [v39] 개인별 성적 산출 — 학기 말에 이 시리즈(종목+반)에 쌓인 모든 회차의
# 경기 결과로 학생별 승패를 집계해 엑셀로 내보낸다.
# =============================================================================
GRADE_HEADERS = ["학년", "반", "번호", "이름", "경기수", "승", "패", "승률(%)"]


def compute_series_grade_stats(series, roster_by_sid):
    """시리즈에 쌓인 모든 회차·모든 경기 결과로 학생별 성적을 낸다.
    출전자는 경기 스냅숏(side_sids)이 있으면 그것을, 없으면(옛 기록·
    조정 없던 경기) 기본 팀원을 쓴다 — 결석·임시 편성이 있었던 경기도
    실제로 뛴 학생만 정확히 센다. 반환: [{sid,grade,cls,num,name,
    games,wins,losses,win_rate}, ...] (학년·반·번호 순 정렬)."""
    stats = {}
    for rnd in series.rounds:
        for ev in rnd.events:
            for row in ev.bracket.rounds:
                for m in row:
                    if m.winner is None or m.is_bye():
                        continue
                    for side in ("a", "b"):
                        for sid in match_side_sids(ev, m, side):
                            if sid not in roster_by_sid:
                                continue
                            e = stats.setdefault(sid, {"games": 0, "wins": 0, "losses": 0})
                            e["games"] += 1
                            if m.winner == side:
                                e["wins"] += 1
                            else:
                                e["losses"] += 1

    def _num_key(v):
        try:
            return (0, int(v))
        except (TypeError, ValueError):
            return (1, str(v))

    rows = []
    for sid, e in stats.items():
        s = roster_by_sid[sid]
        rate = e["wins"] / e["games"] if e["games"] else 0.0
        rows.append({"sid": sid, "grade": s.grade, "cls": s.cls, "num": s.num, "name": s.name,
                    "games": e["games"], "wins": e["wins"], "losses": e["losses"], "win_rate": rate})
    rows.sort(key=lambda r: (str(r["grade"]), str(r["cls"]), _num_key(r["num"])))
    return rows


def save_grade_stats_excel(path, rows, sport="", series_label=""):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "성적"
    ws.append(GRADE_HEADERS)
    for r in rows:
        ws.append([r["grade"], r["cls"], r["num"], r["name"], r["games"], r["wins"], r["losses"],
                   round(r["win_rate"] * 100, 1)])
    wb.save(path)


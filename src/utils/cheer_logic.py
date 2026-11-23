# -*- coding: utf-8 -*-
"""
FolderKit++ — 응원의 메시지 [v44] 순수 로직 (Qt 의존 없음)

메시지 선택 규칙(계획서 3.3)
- 풀(pool) = 사용 켬인 기본 메시지 + 사용 켬인 교사 메시지
- 덱(deck) = 풀 전체를 섞은 순서. 앞에서부터 꺼내 쓰고, 다 쓰면 다시 섞는다
  → 모든 메시지가 한 번씩 나오기 전까지 같은 메시지가 반복되지 않는다.
  다시 섞을 때 직전 덱의 마지막 5개는 새 덱의 앞 5자리에 오지 않게 한다.
- 오늘의 세트 = 그날 처음 실행할 때 풍선 수만큼 꺼내 날짜와 함께 저장.
  같은 날 다시 열면 같은 세트(per_day), 설정을 바꾸면 열 때마다 새로(per_run).
  건너뛴 날(주말·방학)은 덱을 소모하지 않는다(꺼낼 때만 소모하므로).
- 날짜 지정 메시지: 그날은 덱과 관계없이 먼저 배정(첫 번째 = 황금 풍선).
  쓰인 날짜 지정 메시지는 덱의 남은 구간에서 빼서 가까운 날 다시 안 나오게.
- 덱·오늘의 세트에는 메시지 **id만** 저장한다 — 교사가 문구를 고쳐도
  id가 같으면 고친 문구가 그대로 반영된다.

화살·풍선의 움직임도 여기 있다(시간 t의 함수 / 한 스텝 적분) — 화면 없이
충돌 판정까지 테스트할 수 있게.
"""
import json
import math
import random as _random
import uuid as _uuid

from .anim_physics import segment_hits_ellipse
from .cheer_messages import base_message_dicts, CATEGORIES

SCHEMA = 1
MODES = ("per_day", "per_run")
DIFFICULTIES = ("easy", "normal", "hard")
TAIL_GUARD = 5
MAX_TEXT = 120


# =============================================================================
# 메시지 책
# =============================================================================
class MessageBook:
    def __init__(self):
        self.base = base_message_dicts()
        self.user = []                  # [{"id","text","sub","category","date","enabled"}]
        self.base_disabled = set()
        self.deck = []
        self.deck_pos = 0
        self.prev_tail = []
        self.today = {"date": None, "set": []}
        self.mode = "per_day"
        self.prefer_user = True

    # ------------------------------------------------------------ 조회
    def all_messages(self):
        out = []
        for m in self.base:
            d = dict(m)
            d["enabled"] = m["id"] not in self.base_disabled
            d["date"] = None
            out.append(d)
        for m in self.user:
            d = dict(m)
            d["base"] = False
            out.append(d)
        return out

    def by_id(self):
        return {m["id"]: m for m in self.all_messages()}

    def pool_ids(self):
        ids = [m["id"] for m in self.base if m["id"] not in self.base_disabled]
        ids += [m["id"] for m in self.user if m.get("enabled", True)]
        return ids

    def get(self, mid):
        return self.by_id().get(mid)

    # ------------------------------------------------------------ 편집
    def add_user(self, text, sub="", category="cheer", date=None, enabled=True):
        text = (text or "").strip()[:MAX_TEXT]
        if not text:
            return None
        mid = "user_" + _uuid.uuid4().hex[:8]
        self.user.append({"id": mid, "text": text, "sub": (sub or "").strip(),
                          "category": category if category in CATEGORIES else "cheer",
                          "date": date or None, "enabled": bool(enabled)})
        return mid

    def update_user(self, mid, **fields):
        for m in self.user:
            if m["id"] == mid:
                if "text" in fields:
                    t = (fields["text"] or "").strip()[:MAX_TEXT]
                    if t:
                        m["text"] = t
                if "sub" in fields:
                    m["sub"] = (fields["sub"] or "").strip()
                if "category" in fields and fields["category"] in CATEGORIES:
                    m["category"] = fields["category"]
                if "date" in fields:
                    m["date"] = fields["date"] or None
                if "enabled" in fields:
                    m["enabled"] = bool(fields["enabled"])
                return True
        return False

    def delete_user(self, mid):
        before = len(self.user)
        self.user = [m for m in self.user if m["id"] != mid]
        return len(self.user) != before

    def set_enabled(self, mid, enabled):
        if mid.startswith("base_"):
            if enabled:
                self.base_disabled.discard(mid)
            else:
                self.base_disabled.add(mid)
            return True
        return self.update_user(mid, enabled=enabled)

    # ------------------------------------------------------------ 덱
    def _new_deck(self, rng):
        pool = self.pool_ids()
        user_ids = {m["id"] for m in self.user}
        if self.prefer_user:
            users = [i for i in pool if i in user_ids]
            bases = [i for i in pool if i not in user_ids]
            rng.shuffle(users)
            rng.shuffle(bases)
            n = len(pool)
            deck = [None] * n
            if users:
                # 교사 메시지를 덱 앞쪽 절반에 고르게 흩뿌린다.
                half = max(len(users), n // 2)
                step = half / len(users)
                for k, uid in enumerate(users):
                    deck[min(n - 1, int(k * step))] = uid
            it = iter(bases)
            deck = [d if d is not None else next(it) for d in deck]
        else:
            deck = list(pool)
            rng.shuffle(deck)
        # 직전 덱의 마지막 몇 개가 새 덱 맨 앞에 오지 않게(덱 경계 반복 방지)
        tail = set(self.prev_tail)
        if tail and len(deck) > 2 * TAIL_GUARD:
            for i in range(min(TAIL_GUARD, len(deck))):
                if deck[i] in tail:
                    for j in range(len(deck) - 1, TAIL_GUARD - 1, -1):
                        if deck[j] not in tail:
                            deck[i], deck[j] = deck[j], deck[i]
                            break
        self.deck = deck
        self.deck_pos = 0

    def _sync_deck(self, rng):
        """풀이 바뀌었으면(삭제·끄기·추가) 덱을 맞춘다."""
        pool = set(self.pool_ids())
        if not self.deck:
            return
        new_deck = []
        pos = self.deck_pos
        for i, mid in enumerate(self.deck):
            if mid in pool:
                new_deck.append(mid)
            elif i < self.deck_pos:
                pos -= 1
        self.deck = new_deck
        self.deck_pos = max(0, pos)
        missing = [m for m in self.pool_ids() if m not in set(self.deck)]
        for mid in missing:
            lo = self.deck_pos
            remaining = len(self.deck) - lo
            if mid.startswith("user_") and self.prefer_user:
                hi = lo + max(0, remaining // 2)
            else:
                hi = len(self.deck)
            self.deck.insert(rng.randint(lo, max(lo, hi)), mid)

    def draw_next(self, rng, exclude=()):
        pool_n = len(self.pool_ids())
        if pool_n == 0:
            return None
        exclude = set(exclude)
        if len(exclude & set(self.pool_ids())) >= pool_n:
            return None
        self._sync_deck(rng)
        for _ in range(pool_n * 3 + 2):
            if self.deck_pos >= len(self.deck):
                self.prev_tail = self.deck[-TAIL_GUARD:]
                self._new_deck(rng)
                if not self.deck:
                    return None
            mid = self.deck[self.deck_pos]
            self.deck_pos += 1
            if mid not in exclude:
                return mid
        return None

    def _consume_from_remaining(self, mid):
        """날짜 지정으로 쓰인 메시지를 "이미 쓴" 구간으로 옮긴다 — 덱의 남은
        구간에서 그냥 지우면 다음 동기화(_sync_deck)가 "풀에 있는데 덱에
        없다"며 다시 넣어 버리므로, 지우지 않고 포인터 앞쪽으로 옮긴다."""
        if mid not in self.deck:
            self.deck.insert(self.deck_pos, mid)
            self.deck_pos += 1
            return
        i = self.deck.index(mid)
        if i >= self.deck_pos:
            del self.deck[i]
            self.deck.insert(self.deck_pos, mid)
            self.deck_pos += 1

    def dated_for(self, date_str):
        return [m["id"] for m in self.user if m.get("enabled", True) and m.get("date") == date_str]

    def todays_set(self, date_str, n, rng=None):
        """오늘 띄울 메시지 id 목록(첫 번째 = 황금 풍선). date_str은 "YYYY-MM-DD"."""
        rng = rng or _random.Random()
        n = max(1, int(n))
        pool = set(self.pool_ids())
        if self.mode == "per_day" and self.today.get("date") == date_str:
            ids = [i for i in self.today.get("set", []) if i in pool]
            if len(ids) < n:
                while len(ids) < n:
                    nxt = self.draw_next(rng, exclude=ids)
                    if nxt is None:
                        break
                    ids.append(nxt)
                self.today = {"date": date_str, "set": ids}
            return ids[:n]
        ids = []
        for mid in self.dated_for(date_str)[:n]:
            ids.append(mid)
            self._consume_from_remaining(mid)
        while len(ids) < n:
            nxt = self.draw_next(rng, exclude=ids)
            if nxt is None:
                break
            ids.append(nxt)
        self.today = {"date": date_str, "set": ids}
        return ids

    # ------------------------------------------------------------ 저장
    def user_to_json(self):
        return json.dumps({"schema": SCHEMA, "user_messages": self.user,
                           "base_disabled": sorted(self.base_disabled)}, ensure_ascii=False)

    def state_to_json(self):
        return json.dumps({"schema": SCHEMA, "deck": self.deck, "deck_pos": self.deck_pos,
                           "prev_tail": self.prev_tail, "today": self.today, "mode": self.mode,
                           "prefer_user": self.prefer_user}, ensure_ascii=False)

    def load(self, user_json, state_json):
        try:
            u = json.loads(user_json) if user_json else {}
        except ValueError:
            u = {}
        try:
            st = json.loads(state_json) if state_json else {}
        except ValueError:
            st = {}
        self.user = [m for m in u.get("user_messages", []) if isinstance(m, dict) and m.get("id")]
        base_ids = {m["id"] for m in self.base}
        # 기본 메시지 목록이 업데이트돼도 교사의 "사용 끄기"는 id 기준으로 유지한다.
        self.base_disabled = {i for i in u.get("base_disabled", []) if i in base_ids}
        self.deck = list(st.get("deck", []))
        self.deck_pos = int(st.get("deck_pos", 0) or 0)
        self.prev_tail = list(st.get("prev_tail", []))
        self.today = st.get("today") or {"date": None, "set": []}
        self.mode = st.get("mode", "per_day") if st.get("mode") in MODES else "per_day"
        self.prefer_user = bool(st.get("prefer_user", True))


# =============================================================================
# 엑셀 불러오기/양식
# =============================================================================
def save_message_template(path, headers, samples):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in samples:
        ws.append(row)
    for col, width in zip("ABCD", (48, 16, 10, 14)):
        ws.column_dimensions[col].width = width
    wb.save(path)


def read_message_excel(path, category_lookup):
    """1행은 머리글. 본문·보조 문구·분류·날짜(YYYY-MM-DD) 순서.
    category_lookup: 표시 문구(각 언어)·내부 키 → 내부 키. 모르는 값은 cheer."""
    import openpyxl
    from datetime import date, datetime
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = []
    for r in range(2, ws.max_row + 1):
        text = ws.cell(row=r, column=1).value
        if text is None or not str(text).strip():
            continue
        sub = ws.cell(row=r, column=2).value
        cat = ws.cell(row=r, column=3).value
        dt = ws.cell(row=r, column=4).value
        if isinstance(dt, (datetime, date)):
            dt = dt.strftime("%Y-%m-%d")
        elif dt is not None:
            dt = str(dt).strip()[:10] or None
        key = category_lookup.get(str(cat).strip() if cat is not None else "", "cheer")
        rows.append((str(text).strip(), str(sub).strip() if sub is not None else "", key, dt))
    return rows


# =============================================================================
# 활쏘기 — 풍선·화살
# =============================================================================
BOW_X, BOW_Y = 190.0, 640.0
GRAVITY = 900.0
V_MAX = 1750.0
PULL_MAX = 260.0

DIFF_PARAMS = {
    "easy":   {"rx": 60.0, "ry": 72.0, "wind": 0.0,   "sway": 0.6, "guide": True},
    "normal": {"rx": 50.0, "ry": 61.0, "wind": 70.0,  "sway": 1.0, "guide": False},
    "hard":   {"rx": 41.0, "ry": 51.0, "wind": 170.0, "sway": 1.5, "guide": False},
}

BALLOON_COLORS = ["#ef476f", "#4cc9f0", "#06d6a0", "#8f6bff", "#ff9f1c", "#f15bb5", "#00bbf9", "#90be6d"]
GOLD = "#f4c430"


class Balloon:
    __slots__ = ("mid", "bx", "by", "ax", "ay", "w1", "w2", "p1", "p2", "color", "golden", "popped")

    def __init__(self, mid, bx, by, ax, ay, w1, w2, p1, p2, color, golden):
        self.mid, self.bx, self.by = mid, bx, by
        self.ax, self.ay, self.w1, self.w2, self.p1, self.p2 = ax, ay, w1, w2, p1, p2
        self.color, self.golden, self.popped = color, golden, False

    def pos(self, t):
        return (self.bx + self.ax * math.sin(self.w1 * t + self.p1),
                self.by + self.ay * math.sin(self.w2 * t + self.p2))


def make_balloons(ids, rng, difficulty="normal", area=(760.0, 150.0, 1500.0, 600.0)):
    """메시지 id마다 풍선을 하나씩, 서로 너무 붙지 않게 흩어 놓는다(첫 id = 황금)."""
    prm = DIFF_PARAMS.get(difficulty, DIFF_PARAMS["normal"])
    x0, y0, x1, y1 = area
    placed = []
    out = []
    min_d = 150.0
    for k, mid in enumerate(ids):
        best = None
        for _try in range(60):
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            d = min((math.hypot(x - px, y - py) for px, py in placed), default=1e9)
            if best is None or d > best[0]:
                best = (d, x, y)
            if d >= min_d:
                break
        _d, x, y = best
        placed.append((x, y))
        sway = prm["sway"]
        out.append(Balloon(mid, x, y, rng.uniform(10, 28) * sway, rng.uniform(8, 20) * sway,
                           rng.uniform(0.6, 1.3), rng.uniform(0.8, 1.6), rng.uniform(0, 6.28),
                           rng.uniform(0, 6.28), GOLD if k == 0 else BALLOON_COLORS[k % len(BALLOON_COLORS)],
                           k == 0))
    return out


def launch_velocity(pull_dx, pull_dy):
    """활시위를 (pull_dx, pull_dy)만큼 뒤로 당겼을 때(당긴 방향의 반대로) 날아가는 속도."""
    d = math.hypot(pull_dx, pull_dy)
    if d < 1e-6:
        return 0.0, 0.0
    power = min(d, PULL_MAX) / PULL_MAX
    v = V_MAX * power
    return -pull_dx / d * v, -pull_dy / d * v


class Arrow:
    __slots__ = ("x", "y", "vx", "vy", "px", "py", "alive", "age")

    def __init__(self, x, y, vx, vy):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.px, self.py = x, y
        self.alive = True
        self.age = 0.0

    def step(self, dt, wind=0.0):
        self.px, self.py = self.x, self.y
        self.vx += wind * dt
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.age += dt
        if self.x > 1700 or self.y > 1000 or self.x < -100 or self.age > 6:
            self.alive = False

    def tip(self, length=46.0):
        sp = math.hypot(self.vx, self.vy) or 1.0
        return self.x + self.vx / sp * length * 0.5, self.y + self.vy / sp * length * 0.5

    def prev_tip(self, length=46.0):
        sp = math.hypot(self.vx, self.vy) or 1.0
        return self.px + self.vx / sp * length * 0.5, self.py + self.vy / sp * length * 0.5


def arrow_hits(arrow, balloon, t, rx, ry):
    x0, y0 = arrow.prev_tip()
    x1, y1 = arrow.tip()
    cx, cy = balloon.pos(t)
    return segment_hits_ellipse(x0, y0, x1, y1, cx, cy, rx, ry)


def trajectory(vx, vy, wind=0.0, seconds=1.1, dt=1 / 30.0, x=BOW_X, y=BOW_Y):
    pts = []
    for _ in range(int(seconds / dt)):
        vx += wind * dt
        vy += GRAVITY * dt
        x += vx * dt
        y += vy * dt
        pts.append((x, y))
    return pts

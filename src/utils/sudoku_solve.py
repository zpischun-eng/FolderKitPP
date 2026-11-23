# -*- coding: utf-8 -*-
"""
FolderKit++ — 스도쿠 미니앱 핵심 로직(GUI와 분리) [v46.0]

문제 생성(완성 보드 → 유일해를 지키며 칸 빼기), 규칙 검증, 완성 판정,
힌트를 전부 화면 없이 계산한다 — 헤드리스 테스트로 검증하기 위함이다.

난이도는 "빈 칸 개수"로만 나눈다(사용자와 합의한 1차 범위) — 내부 키
("easy"|"medium"|"hard")만 저장·비교하고, 화면 표시 문구는 GUI 쪽에서
i18n으로 변환한다(언어와 로직을 분리하는 이 프로젝트의 원칙).
"""
import random

SIZE = 9
BOX = 3
EMPTY = 0

# [빈 칸 개수로 난이도 구분] — 45칸 중 이만큼을 비운다.
DIFFICULTY_BLANKS = {
    "easy": 36,
    "medium": 46,
    "hard": 54,
}
DIFFICULTY_ORDER = ["easy", "medium", "hard"]

# [v46.1] 재시도(라이프) 시스템 — 오답을 넣거나 힌트를 쓸 때마다 하나씩
# 줄어든다. 0이 되면 그 판은 "실패"로 끝난다(게임 오버).
MAX_LIVES = 3


class SudokuState:
    """퍼즐 하나의 전체 상태.

    - solution: 9x9 정답(절대 안 바뀜)
    - given: 9x9 문제로 주어진 고정 숫자(0=빈칸, 절대 안 바뀜)
    - board: 9x9 지금 화면에 보이는 값(given으로 시작, 사용자가 채워 감)
    - notes: 9x9 각 칸의 메모(연필) 숫자 집합
    - lives: 남은 재시도 횟수(MAX_LIVES에서 시작)
    - game_over: 라이프가 0이 되어 이 판을 더 진행할 수 없는지

    [v46.1] 예전에는 "틀린 숫자도 일단 보드에 반영하고, 색으로만
    구분"했는데 — 그 오답 색(분홍 계열)이 정답 색과 너무 비슷해 보여서
    사용자가 오답을 알아채지 못하는 문제가 있었다("다 채웠는데 완성이
    안 된다"는 지적의 실제 원인). 이제는 **정답과 다르면 아예 보드에
    반영하지 않고** 그 자리에서 바로 오답임을 알리고 라이프를 깎는
    방식으로 바꿨다 — 모호한 색 구분 대신 분명한 신호를 준다."""
    __slots__ = ("solution", "given", "board", "notes", "difficulty",
                "lives", "game_over")

    def __init__(self, solution, given, difficulty="medium"):
        self.solution = solution
        self.given = given
        self.board = [row[:] for row in given]
        self.notes = [[set() for _ in range(SIZE)] for _ in range(SIZE)]
        self.difficulty = difficulty
        self.lives = MAX_LIVES
        self.game_over = False

    def is_given(self, r, c):
        return self.given[r][c] != EMPTY

    def set_value(self, r, c, val):
        """given(고정 숫자) 칸은 바꿀 수 없다. val=0이면 지운다(메모도
        함께 지워진다 — 숫자를 확정하면서 후보를 남겨 둘 이유는 없다).
        정답인지 여부는 따지지 않고 그대로 반영한다 — 힌트·내부적으로
        직접 값을 넣을 때 쓴다. 사용자의 실제 입력 시도는 대신
        try_set_value()를 쓴다."""
        if self.is_given(r, c):
            return False
        self.board[r][c] = val
        if val != EMPTY:
            self.notes[r][c] = set()
        return True

    def try_set_value(self, r, c, val):
        """[v46.1] 사용자가 실제로 숫자를 입력했을 때 쓴다 — 정답
        (solution)과 비교해서, 맞으면 보드에 반영하고 True를, 틀리면
        보드는 그대로 둔(반영하지 않은) 채 라이프를 하나 깎고 False를
        돌려준다. given 칸이거나 이미 게임 오버 상태면 아무 일도 하지
        않고 None을 돌려준다(입력 자체가 무효)."""
        if self.is_given(r, c) or self.game_over:
            return None
        if val == self.solution[r][c]:
            self.board[r][c] = val
            self.notes[r][c] = set()
            return True
        self.lives -= 1
        if self.lives <= 0:
            self.lives = 0
            self.game_over = True
        return False

    def toggle_note(self, r, c, val):
        """메모(연필) 숫자를 켜고 끈다. 확정 숫자가 있는 칸이나 given
        칸에는 메모를 달 수 없다."""
        if self.is_given(r, c) or self.board[r][c] != EMPTY:
            return False
        if val in self.notes[r][c]:
            self.notes[r][c].discard(val)
        else:
            self.notes[r][c].add(val)
        return True

    def conflicts(self):
        return find_conflicts(self.board)

    def is_complete(self):
        return is_complete(self.board)

    def to_dict(self):
        """[v46.5] 저장(보관함)용 — JSON으로 바로 직렬화할 수 있는
        딕셔너리로 바꾼다(notes는 set이라 JSON이 못 다루므로 리스트로
        바꿔 담는다)."""
        return {
            "solution": self.solution,
            "given": self.given,
            "board": self.board,
            "notes": [[sorted(s) for s in row] for row in self.notes],
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_dict(cls, data):
        """to_dict()로 저장했던 딕셔너리에서 상태를 복원한다. 라이프는
        항상 MAX_LIVES로 다시 채운다 — 보관함에서 불러오는 건 그 퍼즐에
        "다시 도전"하는 것이기 때문이다(실패했던 상태 그대로 게임
        오버로 시작하면 아무 의미가 없다)."""
        st = cls(data["solution"], data["given"], data.get("difficulty", "medium"))
        st.board = [row[:] for row in data["board"]]
        st.notes = [[set(s) for s in row] for row in data["notes"]]
        st.lives = MAX_LIVES
        st.game_over = False
        return st

    def apply_hint(self):
        """빈 칸 하나를 정답으로 채운다 — (r, c, value) 또는(더 이상 빈
        칸이 없거나 게임 오버면) None을 돌려준다. [v46.1] 힌트도 라이프를
        하나 깎는다(공짜가 아니다)."""
        if self.game_over:
            return None
        h = hint_cell(self)
        if h is None:
            return None
        r, c, v = h
        self.board[r][c] = v
        self.notes[r][c] = set()
        self.lives -= 1
        if self.lives <= 0:
            self.lives = 0
            self.game_over = True
        return h


def _box_origin(r, c):
    return (r // BOX) * BOX, (c // BOX) * BOX


def is_valid_placement(board, r, c, val):
    """board[r][c]에 val을 놓아도 행·열·3x3박스 규칙을 어기지 않는지
    (그 칸 자신은 비교에서 제외한다)."""
    if val == EMPTY:
        return True
    for i in range(SIZE):
        if i != c and board[r][i] == val:
            return False
        if i != r and board[i][c] == val:
            return False
    br, bc = _box_origin(r, c)
    for i in range(br, br + BOX):
        for j in range(bc, bc + BOX):
            if (i, j) != (r, c) and board[i][j] == val:
                return False
    return True


def find_conflicts(board):
    """board 전체를 훑어 규칙을 어기는 칸들의 좌표 집합을 돌려준다
    (화면에서 그 칸들을 빨갛게 표시하는 데 쓴다)."""
    conflicts = set()
    for r in range(SIZE):
        for c in range(SIZE):
            v = board[r][c]
            if v != EMPTY and not is_valid_placement(board, r, c, v):
                conflicts.add((r, c))
    return conflicts


def is_complete(board):
    """모든 칸이 차 있고 규칙을 만족하면 완성."""
    for row in board:
        if EMPTY in row:
            return False
    return len(find_conflicts(board)) == 0


def digit_counts(board):
    """[v46.2] 1~9 각 숫자가 board 전체에 몇 번 나와 있는지 — 어떤
    숫자가 이미 9개 다 채워졌는지(그래서 그 숫자 버튼을 꺼야 하는지)
    판단하는 데 쓴다."""
    counts = {d: 0 for d in range(1, SIZE + 1)}
    for row in board:
        for v in row:
            if v != EMPTY:
                counts[v] += 1
    return counts


def forced_completion(board):
    """[v46.3] 남은 빈 칸이 하나라도 있고, 그 "모든" 빈 칸이 각자
    후보 숫자를 정확히 하나씩만 가지고 있으면(=더 고민할 것 없이
    논리적으로 값이 다 정해진 상태) {(r,c): value, ...} 매핑을 돌려
    준다. 빈 칸이 없거나, 하나라도 후보가 0개·2개 이상인 칸이 있으면
    None — "자동 완성을 제안해도 되는 상태"인지 판단하는 데 쓴다."""
    result = {}
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == EMPTY:
                cands = _candidates(board, r, c)
                if len(cands) != 1:
                    return None
                result[(r, c)] = cands[0]
    return result or None


def _generate_full_board(rng):
    """무작위로 가득 찬 유효한 스도쿠 정답판을 백트래킹으로 만든다."""
    board = [[EMPTY] * SIZE for _ in range(SIZE)]

    def backtrack(pos):
        if pos == SIZE * SIZE:
            return True
        r, c = divmod(pos, SIZE)
        nums = list(range(1, 10))
        rng.shuffle(nums)
        for v in nums:
            if is_valid_placement(board, r, c, v):
                board[r][c] = v
                if backtrack(pos + 1):
                    return True
                board[r][c] = EMPTY
        return False

    backtrack(0)
    return board


def _candidates(board, r, c):
    used = set(board[r])
    used.update(board[i][c] for i in range(SIZE))
    br, bc = _box_origin(r, c)
    used.update(board[i][j] for i in range(br, br + BOX) for j in range(bc, bc + BOX))
    return [v for v in range(1, 10) if v not in used]


def _count_solutions(board, limit=2):
    """해의 개수를 limit까지만 센다 — 유일해 검증용으로 2개째를 찾는
    순간 멈춰서, 매번 전체를 다 세지 않아도 되게 한다(성능).

    [성능] 그냥 "맨 처음 빈 칸"을 채우는 대신, **후보 숫자가 가장 적은
    빈 칸**(MRV — Minimum Remaining Values)을 먼저 채운다. 막다른 길을
    훨씬 빨리 찾아내 가지치기가 크게 빨라진다 — 빈 칸이 많은 어려움
    난이도에서 생성 시간이 1초를 넘기던 것을 체감 가능한 수준으로
    줄였다."""
    count = 0

    def backtrack():
        nonlocal count
        if count >= limit:
            return
        best = None   # (칸 좌표, 후보 목록) — 후보 수가 가장 적은 빈 칸
        for r in range(SIZE):
            for c in range(SIZE):
                if board[r][c] != EMPTY:
                    continue
                cands = _candidates(board, r, c)
                if not cands:
                    return   # 이 칸은 둘 데가 없다 — 막다른 길, 가지치기
                if best is None or len(cands) < len(best[1]):
                    best = ((r, c), cands)
                    if len(cands) == 1:
                        break   # 더 줄어들 수 없으니 바로 확정
            else:
                continue
            break
        if best is None:
            count += 1   # 빈 칸이 더 없다 — 완성된 해 하나 발견
            return
        (r, c), cands = best
        for v in cands:
            if count >= limit:
                return
            board[r][c] = v
            backtrack()
            board[r][c] = EMPTY

    backtrack()
    return count


def generate_puzzle(difficulty="medium", rng=None):
    """난이도(내부 키)에 맞춰 (solution, given) 쌍을 만든다. 칸을 무작위
    순서로 하나씩 비워 보면서, 비웠을 때도 해가 유일하면 그대로 두고
    아니면 되돌린다 — 항상 유일해가 보장된 문제만 돌려준다."""
    if rng is None:
        rng = random.Random()
    solution = _generate_full_board(rng)
    given = [row[:] for row in solution]

    target_blanks = DIFFICULTY_BLANKS.get(difficulty, DIFFICULTY_BLANKS["medium"])
    cells = [(r, c) for r in range(SIZE) for c in range(SIZE)]
    rng.shuffle(cells)

    blanks = 0
    for (r, c) in cells:
        if blanks >= target_blanks:
            break
        backup = given[r][c]
        given[r][c] = EMPTY
        if _count_solutions(given, limit=2) == 1:
            blanks += 1
        else:
            given[r][c] = backup

    return solution, given


def new_state(difficulty="medium", rng=None):
    solution, given = generate_puzzle(difficulty, rng)
    return SudokuState(solution, given, difficulty)


def puzzle_id(solution):
    """[v46.5] solution(정답판)을 81자리 숫자 문자열로 바꿔 그 퍼즐의
    고유 식별자로 쓴다 — 보관함에서 "같은 퍼즐"인지 구분하거나, 지금
    풀고 있는 퍼즐을 완성했을 때 보관함에서 그 기록을 지우는 데 쓴다."""
    return "".join(str(v) for row in solution for v in row)


def hint_cell(state):
    """빈 칸 중 하나를 무작위로 골라 (r, c, 정답)을 돌려준다(빈 칸이
    없으면 None)."""
    empties = [(r, c) for r in range(SIZE) for c in range(SIZE)
               if state.board[r][c] == EMPTY]
    if not empties:
        return None
    r, c = random.choice(empties)
    return r, c, state.solution[r][c]

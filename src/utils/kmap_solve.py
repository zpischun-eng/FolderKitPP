# -*- coding: utf-8 -*-
"""
FolderKit++ — 카르노맵 좌표 계산 + 논리식 최소화 [v02]

이 파일에는 Qt 코드가 한 줄도 없다. 화면(kmap.py)과 완전히 분리해 둔 이유는
"카르노맵을 눌렀을 때 논리식이 맞게 나오는가"를 위젯 없이도 검증할 수 있게
하기 위해서다 — 계산기의 expr.py와 같은 이유다.

## 2~6변수를 어떻게 하나의 규칙으로 다루는가
전통적인 카르노맵은 4변수까지만 "눈으로 인접한 칸을 묶는" 방식이 통한다.
5·6변수는 보통 4×4 격자를 2개(5변수) 또는 4개(6변수) 늘어놓고, **격자 사이의
인접성은 눈이 아니라 계산으로 처리**하는 것이 표준적인 접근이다. 그래서 이
모듈은:

1. 변수 개수에 따라 "바깥쪽(격자를 나누는) 변수"와 "안쪽(한 격자 안의 행·열)
   변수"를 나누고,
2. 격자 위 칸 하나하나를 민텀(minterm) 번호로 정확히 대응시키고(그레이 코드
   순서),
3. 실제 최소화는 **Quine–McCluskey 알고리즘**으로 민텀 집합 전체를 놓고
   계산한다. 이렇게 하면 격자가 몇 개로 쪼개져 있든, 격자를 넘나드는 인접
   관계까지 포함해 항상 정확한 최소 논리식이 나온다(사람이 눈으로 여러 격자를
   넘나들며 묶기는 어렵지만, 계산은 격자 모양과 무관하다).
"""
import itertools

# =============================================================================
# 1) 격자 레이아웃 — 변수를 "바깥(격자 선택) / 행 / 열"로 나누는 규칙
# =============================================================================
# 변수는 항상 var[0]이 최상위 비트(MSB)다. 그 중 앞쪽 몇 개를 바깥(격자를
# 나누는) 변수로, 그다음을 행, 그다음을 열에 배정한다.
#
#   outer_rows : 격자를 세로로 몇 번 나눌지 결정하는 비트 수(0 또는 1)
#   outer_cols : 격자를 가로로 몇 번 나눌지 결정하는 비트 수(0 또는 1)
#   rows/cols  : 격자 하나 안에서 행/열에 쓰는 비트 수
LAYOUTS = {
    2: dict(outer_rows=0, outer_cols=0, rows=1, cols=1),
    3: dict(outer_rows=0, outer_cols=0, rows=1, cols=2),
    4: dict(outer_rows=0, outer_cols=0, rows=2, cols=2),
    # [v07] 5·6변수도 단일 테이블로 표현한다. 예전(v02)에는 5변수를 격자
    # 2장, 6변수를 격자 4장으로 나눠 그렸는데, 열(또는 행)에 3비트 그레이
    # 코드를 쓰면 굳이 여러 장으로 나누지 않아도 "옆 칸은 1비트만 다르다"는
    # 카르노맵의 성질이 표 하나 안에서 그대로 유지된다(그레이 코드는 순환
    # 구조라 마지막 열과 첫 열도 1비트만 다르다). 최소화 알고리즘은 표
    # 모양과 아예 무관하므로(민텀 집합만 본다) 정확성에는 영향이 없다.
    5: dict(outer_rows=0, outer_cols=0, rows=2, cols=3),   # 단일 테이블 4행×8열
    6: dict(outer_rows=0, outer_cols=0, rows=3, cols=3),   # 단일 테이블 8행×8열
}


def get_layout(num_vars: int) -> dict:
    """레이아웃 + 각 축에 배정된 변수 인덱스(0-based, 0이 MSB)를 함께 돌려준다."""
    spec = LAYOUTS[num_vars]
    idx = 0
    outer_row_bits = list(range(idx, idx + spec["outer_rows"])); idx += spec["outer_rows"]
    outer_col_bits = list(range(idx, idx + spec["outer_cols"])); idx += spec["outer_cols"]
    row_bits = list(range(idx, idx + spec["rows"])); idx += spec["rows"]
    col_bits = list(range(idx, idx + spec["cols"])); idx += spec["cols"]
    assert idx == num_vars, "레이아웃의 비트 수 합이 변수 개수와 맞지 않음"
    return dict(spec, outer_row_bits=outer_row_bits, outer_col_bits=outer_col_bits,
                row_bits=row_bits, col_bits=col_bits,
                outer_row_count=2 ** spec["outer_rows"],
                outer_col_count=2 ** spec["outer_cols"],
                row_count=2 ** spec["rows"], col_count=2 ** spec["cols"])


# 1비트/2비트/3비트 그레이 코드 순서. 카르노맵에서 칸이 이 순서로 배치되어야
# "옆 칸으로 한 칸 움직이면 딱 한 비트만 바뀐다"는 성질이 성립한다.
# 3비트 표는 순환 구조라 마지막 항목(100)과 첫 항목(000)도 1비트만 다르다 —
# 그래서 8칸을 하나로 이어 붙여도(5·6변수 단일 테이블) 표 끝과 시작이
# 자연스럽게 이어진다.
_GRAY_1BIT = [(0,), (1,)]
_GRAY_2BIT = [(0, 0), (0, 1), (1, 1), (1, 0)]
_GRAY_3BIT = [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0),
              (1, 1, 0), (1, 1, 1), (1, 0, 1), (1, 0, 0)]


def gray_bits(nbits: int, index: int):
    if nbits == 0:
        return ()
    if nbits == 1:
        return _GRAY_1BIT[index]
    if nbits == 2:
        return _GRAY_2BIT[index]
    if nbits == 3:
        return _GRAY_3BIT[index]
    raise ValueError(f"지원하지 않는 비트 수: {nbits}")


def gray_label(nbits: int, index: int) -> str:
    return "".join(str(b) for b in gray_bits(nbits, index))


def cell_minterm(layout: dict, outer_row_idx: int, outer_col_idx: int,
                  row_idx: int, col_idx: int) -> int:
    """격자 위 한 칸의 좌표 → 민텀 번호. 그레이 코드로 각 축의 비트를 얻어
    변수 위치에 맞게 다시 조립한 뒤, 자리값(2의 거듭제곱)을 곱해 더한다."""
    n = (len(layout["outer_row_bits"]) + len(layout["outer_col_bits"])
         + len(layout["row_bits"]) + len(layout["col_bits"]))
    bits = [0] * n
    for pos, b in zip(layout["outer_row_bits"], gray_bits(layout["outer_rows"], outer_row_idx)):
        bits[pos] = b
    for pos, b in zip(layout["outer_col_bits"], gray_bits(layout["outer_cols"], outer_col_idx)):
        bits[pos] = b
    for pos, b in zip(layout["row_bits"], gray_bits(layout["rows"], row_idx)):
        bits[pos] = b
    for pos, b in zip(layout["col_bits"], gray_bits(layout["cols"], col_idx)):
        bits[pos] = b
    return sum(b << (n - 1 - pos) for pos, b in enumerate(bits))


def minterm_bits(minterm: int, num_vars: int):
    """민텀 번호 → (MSB부터) 비트 튜플. 툴팁 등 표시용."""
    return tuple((minterm >> (num_vars - 1 - i)) & 1 for i in range(num_vars))


# =============================================================================
# 2) Quine–McCluskey 최소화
# =============================================================================
# 반환값 규약:
#   - 항상 거짓(민텀이 하나도 없음)          → []  (화면에는 "0")
#   - 항상 참(모든 민텀이 1)                 → [('-',) * num_vars]  (화면에는 "1")
#   - 그 외                                  → 곱항(product term) 튜플의 리스트
#     튜플의 각 자리는 0 / 1 / '-'(무관항, 이 자리 변수는 이 항에 나타나지 않음)

# 이 한도를 넘으면 Petrick's method(모든 경우의 수를 정확히 비교하는 방식)
# 대신 탐욕(그리디) 방식으로 바꾼다. 사용자가 클릭할 때마다 즉시 다시
# 계산해야 하므로(v01 계산기의 POW_MAX_DIGITS와 같은 이유), 병적인 입력
# 하나가 클릭 반응을 멈추게 해서는 안 된다.
PETRICK_STATE_CAP = 20000


def minimize_sop(minterms, num_vars: int):
    minterms = set(minterms)
    full = 1 << num_vars
    if not minterms:
        return []
    if len(minterms) == full:
        return [tuple(["-"] * num_vars)]

    primes = _prime_implicants(minterms, num_vars)
    chart = {m: [p for p in primes if _covers(p, m, num_vars)] for m in minterms}

    essential = set()
    covered = set()
    for m, plist in chart.items():
        if len(plist) == 1:
            essential.add(plist[0])
    for p in essential:
        covered |= _covered_minterms(p, minterms, num_vars)

    remaining = minterms - covered
    if not remaining:
        return sorted(essential, key=_term_sort_key)

    remaining_options = {m: [p for p in chart[m]] for m in remaining}
    chosen = _select_cover(remaining, remaining_options)
    return sorted(essential | chosen, key=_term_sort_key)


def _term_sort_key(term):
    # 리터럴이 적은(더 간단한) 항을 앞으로, 그다음은 보기 좋으라고 사전순.
    # 튜플 안에 int(0/1)와 str('-')가 섞여 있으면 비교 연산자가 없어 정렬이
    # 실패하므로, 비교용으로만 '-'를 정수 2로 바꿔 자료형을 통일한다.
    literal_count = sum(1 for b in term if b != "-")
    return (literal_count, _cmp_key(term))


def _cmp_key(term):
    """항 하나를 항상 같은 순서로 비교할 수 있는 값으로 바꾼다.

    파이썬은 문자열('-')의 해시값을 실행할 때마다 무작위로 바꾼다
    (PYTHONHASHSEED). 그래서 집합(set)에 담긴 항들을 그냥 훑으면 실행할
    때마다 순서가 달라지고, 최소 항 개수·리터럴 수가 정확히 같은 동점
    상황에서 `min()`이 "먼저 나온 것"을 고르다 보니 **같은 카르노맵인데
    실행할 때마다 다른(둘 다 맞지만 모양이 다른) 논리식이 나오는** 문제가
    생긴다. 이 함수로 항을 항상 정수 튜플로 바꿔 비교하면 그런 우연이
    끼어들 자리가 없어진다."""
    return tuple(2 if b == "-" else b for b in term)


def _covers(term, minterm, num_vars) -> bool:
    for i in range(num_vars):
        if term[i] != "-" and term[i] != ((minterm >> (num_vars - 1 - i)) & 1):
            return False
    return True


def _covered_minterms(term, universe, num_vars):
    return {m for m in universe if _covers(term, m, num_vars)}


def _prime_implicants(minterms, num_vars):
    """민텀을 1의 개수(popcount)로 묶고, 한 비트만 다른 항끼리 반복해서
    합쳐 나간다. 더 이상 합쳐지지 않고 남는 항이 소항(prime implicant)이다."""
    groups = {}
    for m in minterms:
        bits = tuple((m >> (num_vars - 1 - i)) & 1 for i in range(num_vars))
        groups.setdefault(bin(m).count("1"), set()).add(bits)

    primes = set()
    current = groups
    while True:
        used = set()
        next_groups = {}
        keys = sorted(current.keys())
        for k in keys:
            if (k + 1) not in current:
                continue
            for t1 in current[k]:
                for t2 in current[k + 1]:
                    diff = [i for i in range(num_vars) if t1[i] != t2[i]]
                    if len(diff) == 1 and t1[diff[0]] != "-" and t2[diff[0]] != "-":
                        merged = list(t1)
                        merged[diff[0]] = "-"
                        merged = tuple(merged)
                        ones = sum(1 for b in merged if b == 1)
                        next_groups.setdefault(ones, set()).add(merged)
                        used.add(t1)
                        used.add(t2)
        for k in keys:
            for t in current[k]:
                if t not in used:
                    primes.add(t)
        if not next_groups:
            break
        current = next_groups
    return primes


def _select_cover(remaining, options):
    """Petrick's method — 남은 민텀을 전부 덮는 조합 중 항 개수(그다음
    리터럴 총합)가 가장 작은 것을 정확히 찾는다. 상태 수가 한도를 넘으면
    탐욕(그리디) 방식으로 안전하게 전환한다."""
    ms = sorted(remaining)
    products = [frozenset([p]) for p in options[ms[0]]]
    products = _prune_supersets(products)
    overflowed = False

    for m in ms[1:]:
        if len(products) * len(options[m]) > PETRICK_STATE_CAP:
            overflowed = True
            break
        new_products = set()
        for term_set in products:
            for p in options[m]:
                new_products.add(frozenset(term_set | {p}))
        products = _prune_supersets(new_products)
        if len(products) > PETRICK_STATE_CAP:
            overflowed = True
            break

    if overflowed:
        return _greedy_cover(remaining, options)

    # 항 개수 -> 리터럴 총합 -> (동점이면) 내용 자체로 비교해 항상 같은
    # 결과가 나오게 한다. 이 셋째 기준이 없으면 함께 집합(set)을 순회하는
    # 순서에 따라 결과가 실행마다 달라질 수 있다.
    best = min(products, key=lambda s: (
        len(s),
        sum(sum(1 for b in p if b != "-") for p in s),
        tuple(sorted(_cmp_key(p) for p in s)),
    ))
    return set(best)


def _prune_supersets(sets_):
    """이미 있는 더 작은 조합을 포함하는(즉, 항이 더 많기만 한) 조합은
    절대 최선이 될 수 없으므로 미리 걸러 상태 폭발을 억제한다."""
    ordered = sorted(sets_, key=len)
    kept = []
    for s in ordered:
        if not any(k <= s for k in kept):
            kept.append(s)
    return kept


def _greedy_cover(remaining, options):
    """상태 수가 너무 커졌을 때의 안전한 대안 — 매번 "아직 안 덮인 민텀을
    가장 많이 덮는 항"을 고르고, 동점이면 리터럴이 적은(더 간단한) 항을
    고른다. 항상 정확히 최소는 아닐 수 있지만 즉시 응답해야 하는 UI에서는
    이 편이 안전하다."""
    remaining = set(remaining)
    chosen = set()
    all_candidates = {p for plist in options.values() for p in plist}
    while remaining:
        def score(p):
            cov = sum(1 for m in remaining if p in options.get(m, ()))
            literals = sum(1 for b in p if b != "-")
            return (-cov, literals, _cmp_key(p))   # 셋째 기준으로 동점을 항상 같게 끊는다
        best = min(all_candidates, key=score)
        chosen.add(best)
        remaining = {m for m in remaining if best not in options.get(m, ())}
    return chosen


# =============================================================================
# 3) 항 ↔ 문자열
# =============================================================================
def term_literals(term, names):
    """항 하나를 (부정 여부, 변수 이름) 목록으로. 표시(overline/apostrophe)는
    호출하는 쪽(kmap.py)이 원하는 형식으로 최종 조립한다."""
    return [(names[i], term[i] == 0) for i in range(len(term)) if term[i] != "-"]


def term_to_plain(term, names) -> str:
    lits = term_literals(term, names)
    if not lits:
        return "1"
    return "".join(f"{n}'" if neg else n for n, neg in lits)


def expr_to_plain(terms, names) -> str:
    if not terms:
        return "0"
    return " + ".join(term_to_plain(t, names) for t in terms)


def format_minterms(minterms) -> str:
    return ",".join(str(m) for m in sorted(minterms))


def literal_count(terms) -> int:
    return sum(sum(1 for b in t if b != "-") for t in terms)

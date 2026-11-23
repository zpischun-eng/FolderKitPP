# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 코돈시뮬(CodonSim) [신규] — 순수 로직

기출 문제 하나를 골라 w(주어진 주형 가닥)에서 시작해 x → y → z로 이어지는
변이를 사용자가 직접 만들어 보며 조건을 맞춰 가는 학습 도구. 전사(DNA→mRNA)
· 번역(코돈표 조회)은 기존 코돈표 계산기(codon_solve.py)의 것을 그대로
가져다 쓰고, 이 파일은 그 위에 "변이 적용 → 조건 판정 → <보기> 채점"만
얹는다.

## 조건/<보기>를 하나의 스펙으로 다루는 이유
"x는 아미노산 8개", "x에는 G만 삽입됨", "z는 y와 아미노산 서열이 같음" 같은
판정은 겉보기엔 다 달라 보이지만 사실 몇 가지 검사 종류(distinct_count,
insert_base_only, same_amino_as)의 조합일 뿐이다. 조건 판정판의 체크리스트도
<보기> ㄱ/ㄴ/ㄷ의 채점도 똑같은 CheckSpec.evaluate()로 처리한다 — 문항마다
판정 함수를 새로 짜지 않고 데이터(내부 키 kind + 인자)만 다르게 얹는 구조라,
문제를 추가할 때 코드를 새로 안 짜도 된다.
"""
from . import codon_solve as CD

# =============================================================================
MTYPE_INSERT = "insert"
MTYPE_DELETE = "delete"
MTYPE_REPLACE = "replace"

STAGE_ORDER = ["w", "x", "y", "z"]

MAX_SEQ_LEN = 200
MIN_SEQ_LEN = 3


# =============================================================================
class SeqAnalysis:
    """서열 하나(DNA)를 전사·번역까지 미리 계산해 둔 결과."""

    def __init__(self, dna):
        self.dna = dna
        self.mrna = CD.transcribe_from_template(dna)
        result = CD.translate(self.mrna)
        self.codons = result.codons
        self.aminos = result.aminos


def analyze(dna):
    return SeqAnalysis(dna)


def distinct_count(aminos):
    return len({a for a in aminos if a != "Stop"})


class Mutation:
    """변이 하나 — 부모 서열에 적용해 자식 서열을 만든다.

    ``pos``는 0-기반 삽입/삭제/치환 시작 위치, ``bases``는 삽입/치환에 쓸
    염기(삭제에서는 빈 문자열), ``length``는 삭제/치환에서 지울 길이다.
    """

    def __init__(self, mtype, pos, bases="", length=0):
        self.type = mtype
        self.pos = pos
        self.bases = bases.upper()
        self.length = length


def apply_mutation(seq, mutation):
    pos, bases, length = mutation.pos, mutation.bases, mutation.length
    if mutation.type == MTYPE_INSERT:
        return seq[:pos] + bases + seq[pos:]
    if mutation.type == MTYPE_DELETE:
        return seq[:pos] + seq[pos + length:]
    if mutation.type == MTYPE_REPLACE:
        return seq[:pos] + bases + seq[pos + length:]
    raise ValueError(f"unknown mutation type: {mutation.type}")


def validate_mutation(parent_len, mutation):
    """오류 없으면 빈 목록. 있으면 (내부_오류_키, {서식_인자}) 목록."""
    errors = []
    if mutation.pos < 0 or mutation.pos > parent_len:
        errors.append(("pos_out_of_range", {}))
    if mutation.type in (MTYPE_INSERT, MTYPE_REPLACE):
        if not mutation.bases or any(b not in "ATGC" for b in mutation.bases):
            errors.append(("bases_invalid", {}))
    if mutation.type in (MTYPE_DELETE, MTYPE_REPLACE):
        if mutation.length < 1:
            errors.append(("length_invalid", {}))
        elif mutation.pos + mutation.length > parent_len:
            errors.append(("range_invalid", {}))
    return errors


def validate_free_sequence(seq):
    """[직접 입력] 모드에서 사용자가 넣은 w 서열 검증."""
    seq = (seq or "").upper().replace(" ", "")
    errors = []
    if len(seq) < MIN_SEQ_LEN:
        errors.append(("seq_too_short", {"a0": MIN_SEQ_LEN}))
    elif len(seq) > MAX_SEQ_LEN:
        errors.append(("seq_too_long", {"a0": MAX_SEQ_LEN}))
    if any(ch not in "ATGC" for ch in seq):
        errors.append(("seq_invalid_char", {}))
    return seq, errors


# =============================================================================
# 체인 상태 — w(고정) → x → y → z. Qt에 전혀 의존하지 않아 단독 테스트 가능.
# =============================================================================
class StageState:
    def __init__(self):
        self.mutation = None     # Mutation | None
        self.result = None       # SeqAnalysis | None
        self.applied = False
        self.selected_pos = None  # 화면에서 클릭으로 지정한 위치(0-기반)


class ChainState:
    def __init__(self, w_seq):
        self.w_seq = w_seq
        self.w = analyze(w_seq)
        self.stages = {"x": StageState(), "y": StageState(), "z": StageState()}

    def parent_key(self, stage_key):
        return STAGE_ORDER[STAGE_ORDER.index(stage_key) - 1]

    def stage_result(self, stage_key):
        """w/x/y/z 어느 쪽이든 현재 결과(SeqAnalysis)를 돌려준다. 아직
        적용 전이면 None."""
        if stage_key == "w":
            return self.w
        st = self.stages[stage_key]
        return st.result if st.applied else None

    def parent_seq(self, stage_key):
        r = self.stage_result(self.parent_key(stage_key))
        return r.dna if r else None

    def apply(self, stage_key, mutation):
        parent_seq = self.parent_seq(stage_key)
        if parent_seq is None:
            raise ValueError("parent stage not ready")
        errors = validate_mutation(len(parent_seq), mutation)
        if errors:
            return errors
        new_seq = apply_mutation(parent_seq, mutation)
        st = self.stages[stage_key]
        st.mutation = mutation
        st.result = analyze(new_seq)
        st.applied = True
        # 위 단계가 바뀌면 아래 단계는 다시 만들어야 한다(연쇄 무효화).
        idx = STAGE_ORDER.index(stage_key)
        for k in STAGE_ORDER[idx + 1:]:
            self.reset(k)
        return []

    def reset(self, stage_key):
        st = self.stages[stage_key]
        st.mutation = None
        st.result = None
        st.applied = False
        st.selected_pos = None


# =============================================================================
# 조건 / <보기> 공용 판정 스펙
# =============================================================================
CHECK_DISTINCT_COUNT = "distinct_count"      # args=(n,)               stage의 서로 다른 아미노산 수 == n
CHECK_INSERT_BASE_ONLY = "insert_base_only"  # args=(base,)            stage가 그 염기만으로 삽입됐는지
CHECK_SAME_AMINO_AS = "same_amino_as"        # args=(other_stage,)     stage와 other_stage의 아미노산 서열이 같은지


class CheckSpec:
    def __init__(self, key, kind, stage, *args):
        self.key = key        # 표시 문구 조회용 내부 키(문제별 네임스페이스는 호출 쪽에서 조합)
        self.kind = kind
        self.stage = stage
        self.args = args


def evaluate_check(spec, chain):
    """조건/<보기> 공통 판정. 아직 판정할 수 없으면 None, 아니면 True/False."""
    result = chain.stage_result(spec.stage)
    if result is None:
        return None

    if spec.kind == CHECK_DISTINCT_COUNT:
        (n,) = spec.args
        return distinct_count(result.aminos) == n

    if spec.kind == CHECK_INSERT_BASE_ONLY:
        (base,) = spec.args
        st = chain.stages.get(spec.stage)
        if st is None or st.mutation is None:
            return None
        return st.mutation.type == MTYPE_INSERT and set(st.mutation.bases) == {base}

    if spec.kind == CHECK_SAME_AMINO_AS:
        (other_stage,) = spec.args
        other_result = chain.stage_result(other_stage)
        if other_result is None:
            return None
        return result.aminos == other_result.aminos

    return None


# =============================================================================
# 문제 프리셋 — 화면의 "문제 선택" 콤보에서 그대로 쓴다(순수 데이터)
# =============================================================================
class Problem:
    def __init__(self, key, w_seq, conditions=None, bogi=None, answer=None,
                 hint_keys=None):
        self.key = key                  # util.codonsim.problem.<key> 로 번역
        self.w_seq = w_seq
        self.conditions = conditions or []   # [CheckSpec, ...]
        self.bogi = bogi or []               # [CheckSpec, ...]
        self.answer = answer or {}           # {"x": Mutation, "y": Mutation, "z": Mutation}
        self.hint_keys = hint_keys or []     # ["hint1","hint2"] → util.codonsim.hint.<key>.<hint_key>


# 직접 입력 모드를 나타내는 문제 키(프리셋 목록에는 없고, 콤보 맨 끝에 별도로 둔다)
FREE_INPUT_KEY = "free_input"

PROBLEMS = [
    Problem(
        key="suneung2019_21",
        w_seq="TTAGTTACGAGTGGTGGCTGCCCATTGTA",
        conditions=[
            CheckSpec("x8", CHECK_DISTINCT_COUNT, "x", 8),
            CheckSpec("xg", CHECK_INSERT_BASE_ONLY, "x", "G"),
            CheckSpec("y7", CHECK_DISTINCT_COUNT, "y", 7),
            CheckSpec("zy", CHECK_SAME_AMINO_AS, "z", "y"),
        ],
        bogi=[
            CheckSpec("g", CHECK_DISTINCT_COUNT, "x", 8),
            CheckSpec("n", CHECK_SAME_AMINO_AS, "z", "y"),
            CheckSpec("d", CHECK_INSERT_BASE_ONLY, "x", "C"),
        ],
        answer={
            "x": Mutation(MTYPE_INSERT, 6, "GG"),
            "y": Mutation(MTYPE_REPLACE, 6, "T", 1),
            "z": Mutation(MTYPE_REPLACE, 8, "T", 1),
        },
        hint_keys=["hint1", "hint2"],
    ),
]


def problem_by_key(key):
    return next((p for p in PROBLEMS if p.key == key), None)


def make_free_problem(w_seq):
    """[직접 입력] 모드 — 조건·<보기>·정답 없이 w→x→y→z 탐색만 가능."""
    return Problem(key=FREE_INPUT_KEY, w_seq=w_seq)

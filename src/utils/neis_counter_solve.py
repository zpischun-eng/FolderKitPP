# -*- coding: utf-8 -*-
"""
FolderKit++ — 나이스(NEIS) 글자수 계산기: 순수 로직 [신규]

바이트 계산 규칙은 참고 사이트(hjh010501.github.io/neis-counter)와 같다 —
한글은 3바이트, 영어·숫자·특수문자·띄어쓰기는 1바이트, 엔터(줄바꿈)는
2바이트로 센다.

금지어 검사는 교육부훈령 「학교생활기록 작성 및 관리지침」과 학교생활기록부
기재요령(작성 시 유의사항, 초·중·고 공통)에 실제로 나열된 항목을 바탕으로
한다. **다만 이 검사는 "적합한지 느낌을 잡는 보조 도구"일 뿐, 법적·행정적
판단을 대신하지 않는다** — 키워드가 걸렸다고 반드시 위반은 아니고, 안
걸렸다고 반드시 안전한 것도 아니다. 마지막 확인은 항상 사람이 해야 한다
(화면 안내 문구에도 이 점을 분명히 적어 둔다).
"""
import re

# =============================================================================
# 바이트/글자수 계산
# =============================================================================
_HANGUL_RANGES = (
    (0xAC00, 0xD7A3),   # 완성형 한글 음절
    (0x1100, 0x11FF),   # 한글 자모
    (0x3130, 0x318F),   # 한글 호환 자모
)


def _is_hangul(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _HANGUL_RANGES)


def count_bytes(text: str):
    """(공백제외 글자수, 공백포함 글자수, 바이트수)를 돌려준다.
    "공백제외"는 스페이스바(공백 문자)만 뺀 글자수다(줄바꿈은 글자수에는
    포함되지만 "공백"으로 취급하지 않는다 — 나이스 화면의 관례와 같다)."""
    if not text:
        return 0, 0, 0
    chars_with_space = len(text)
    chars_without_space = len(text) - text.count(" ")
    total_bytes = 0
    for ch in text:
        if ch == "\n":
            total_bytes += 2
        elif _is_hangul(ch):
            total_bytes += 3
        else:
            total_bytes += 1
    return chars_without_space, chars_with_space, total_bytes


# 항목별 입력 가능 바이트(2026년 고교학점제 전면 도입 반영 — 진로활동·
# 개인별세특(행특)이 줄었다). 내부 키는 화면 문구와 분리한다(사용자 원칙).
ITEM_LIMITS = {
    "autonomy": 1500,      # 자율활동
    "club": 1500,          # 동아리활동
    "career": 1500,        # 진로활동
    "subject": 1500,       # 교과세특
    "behavior": 900,       # 개인별세특(행동특성 및 종합의견)
}
ITEM_ORDER = ["autonomy", "club", "career", "subject", "behavior"]


# =============================================================================
# 기재 금지·유의 표현 검사(규칙 기반 — 키워드 + 정규식 보강)
# =============================================================================
class Flag:
    """검사에서 걸린 한 건. category는 내부 키(화면 문구는 위젯이 tr()로
    변환), matched는 실제로 걸린 문구, span은 (시작, 끝) 인덱스."""

    __slots__ = ("category", "matched", "span")

    def __init__(self, category, matched, span):
        self.category = category
        self.matched = matched
        self.span = span


# 공인어학시험 — 정규식(영문 약어는 대소문자 무관, 한글 표기도 함께)
_RE_LANG_TEST = re.compile(
    r"(TOEIC\s*Speaking|TOEIC|TOEFL|TEPS|IELTS|HSK|JLPT|OPIc|TOEIC-?S|"
    r"토익\s*스피킹|토익|토플|텝스|아이엘츠|오픽)",
    re.IGNORECASE,
)

# 교외 대회/상 — "교외" 명시 + 대회/상 계열, 또는 전형적인 교외상 명칭
_RE_EXTERNAL_CONTEST = re.compile(
    r"(교외\s*(경시)?대회|교외상|전국\s*(경시)?대회|((\S+협회|\S+단체|\S+연합회)\s*(장)?상)|"
    r"표창장|감사장|공로상)"
)

# 모의고사/학력평가 성적 지표 — 두 부류가 함께 나올 때만 걸리게(공출현)
_RE_MOCK_EXAM = re.compile(r"(모의고사|전국연합학력평가|모의평가|학력평가)")
_RE_SCORE_METRIC = re.compile(r"(원점수|표준점수|백분위|석차\s*등급|석차|등급)")

# 논문/도서출간/특허/지식재산권
_RE_PAPER_BOOK_PATENT = re.compile(
    r"(논문\s*(투고|등재|발표)?|학회\s*(지)?\s*(등재|발표|투고)?|도서\s*출간|출간\s*(사실)?|"
    r"발명\s*특허|지식재산권|특허\s*(출원|등록))"
)

# 해외 활동(어학연수·해외봉사 등)
_RE_OVERSEAS = re.compile(r"(어학\s*연수|해외\s*(연수|봉사|캠프|교류|인턴|탐방))")

# 장학생/장학금
_RE_SCHOLARSHIP = re.compile(r"(장학생|장학금)")

# 부모·친인척의 사회·경제적 지위 암시 — 가족 지칭어 + 지위/직업어의 공출현
_RE_FAMILY_TERM = re.compile(r"(아버지|어머니|부모님|아빠|엄마|삼촌|이모|고모|외삼촌|친인척)")
_RE_STATUS_TERM = re.compile(
    r"(의사|변호사|검사|판사|교수|대기업|사장|대표이사|회장|임원|박사|고위\s*공직자|재벌)"
)

# 특정 대학명(주요 대학 위주 — 전수 목록은 아니다. 이름 뒤에 "대학교/대"가
# 붙는 형태만 잡아 일반 단어("대학", "학과" 등)와는 구분한다.
_UNIVERSITY_NAMES = [
    "서울대", "연세대", "고려대", "서강대", "성균관대", "한양대", "중앙대", "경희대",
    "한국외대", "한국외국어대", "서울시립대", "건국대", "동국대", "홍익대", "숙명여대",
    "이화여대", "국민대", "숭실대", "세종대", "광운대", "명지대", "상명대", "가톨릭대",
    "덕성여대", "동덕여대", "서울여대", "성신여대", "아주대", "인하대", "단국대",
    "한국항공대", "KAIST", "카이스트", "포스텍", "POSTECH", "유니스트", "UNIST",
    "디지스트", "DGIST", "지스트", "GIST", "부산대", "경북대", "전남대", "전북대",
    "충남대", "충북대", "강원대", "제주대", "한국교원대", "인천대", "안양대", "가천대",
    "수원대", "한림대", "강릉원주대", "목포대", "순천대", "창원대", "경상국립대",
    "서울과학기술대", "서울교대", "경인교대", "공주교대", "청주교대", "전주교대",
    "진주교대", "부산교대", "대구교대", "광주교대", "춘천교대", "육군사관학교",
    "해군사관학교", "공군사관학교", "경찰대학", "삼육대", "성공회대", "협성대",
    "평택대", "대진대", "신한대", "한세대", "차의과학대", "을지대", "건양대",
    "극동대", "청운대", "서울대학교", "연세대학교", "고려대학교",
]
_RE_UNIVERSITY = re.compile(
    "(" + "|".join(re.escape(n) for n in sorted(set(_UNIVERSITY_NAMES), key=len, reverse=True)) + ")"
)


def scan(text: str, school_name: str = "") -> list:
    """text를 검사해 Flag 목록을 돌려준다(발견 순서, 문구 안 등장 위치
    기준). school_name이 주어지면 그 학교명(고교 블라인드 위반)도 함께
    본다."""
    flags = []

    def _add_all(pattern, category):
        for m in pattern.finditer(text):
            flags.append(Flag(category, m.group(0), m.span()))

    _add_all(_RE_LANG_TEST, "lang_test")
    _add_all(_RE_EXTERNAL_CONTEST, "external_contest")
    _add_all(_RE_PAPER_BOOK_PATENT, "paper_book_patent")
    _add_all(_RE_OVERSEAS, "overseas")
    _add_all(_RE_SCHOLARSHIP, "scholarship")
    _add_all(_RE_UNIVERSITY, "university_name")

    # 모의고사/학평 — 시험 단어와 성적 지표 단어가 함께 있을 때만
    if _RE_MOCK_EXAM.search(text) and _RE_SCORE_METRIC.search(text):
        for m in _RE_MOCK_EXAM.finditer(text):
            flags.append(Flag("mock_exam_score", m.group(0), m.span()))

    # 가족 지위 암시 — 가족어와 지위어가 함께 있을 때만(가장 불확실한 항목)
    if _RE_FAMILY_TERM.search(text) and _RE_STATUS_TERM.search(text):
        for m in _RE_FAMILY_TERM.finditer(text):
            flags.append(Flag("family_status", m.group(0), m.span()))

    # 학교명 노출(고교 블라인드) — 현재 설정된 학교명 또는 그 줄임말
    name = (school_name or "").strip()
    if name:
        candidates = {name}
        for suffix in ("등학교", "고등학교", "중학교", "초등학교"):
            if name.endswith(suffix):
                candidates.add(name[: -len(suffix)])
        for cand in candidates:
            if len(cand) < 2:
                continue
            for m in re.finditer(re.escape(cand), text):
                flags.append(Flag("school_name_leak", m.group(0), m.span()))

    flags.sort(key=lambda f: f.span[0])
    return flags


CATEGORY_KEYS = [
    "lang_test", "external_contest", "mock_exam_score", "paper_book_patent",
    "overseas", "scholarship", "family_status", "university_name", "school_name_leak",
]

# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 코돈표 계산기(순수 로직) [신규]

수능 생명과학에서 반복적으로 나오는 계산: DNA(주형 가닥) → mRNA(전사) →
아미노산 서열(번역)을 표준 유전암호표(64개 코돈)로 그대로 조회한다.
카르노맵의 진리표처럼, 이 파일도 "표를 정확히 찾아보는" 성격의 순수
로직이라 외부 라이브러리가 필요 없다.

## 전사(DNA → mRNA) 방향에 대한 가정

이 파일은 **입력한 DNA 주형 가닥이 3'→5' 방향으로 나열되어 있다고
가정**한다(교과서 문제에서 가장 흔한 표기). RNA 중합효소가 주형 가닥을
3'→5' 방향으로 읽으면서 мRNA를 5'→3' 방향으로 합성하기 때문에, **입력
순서를 뒤집을 필요 없이 각 염기를 상보 염기로만 바꾸면**(T는 U로) 된다.
이 가정이 안 맞는 문제(주형 가닥이 5'→3'으로 주어진 경우)라면 mRNA를
직접 입력하는 쪽을 쓰면 된다 — 그래서 위젯에는 "DNA 주형가닥" 입력과
"mRNA 직접 입력" 두 가지를 모두 둔다.
"""

# 표준 유전암호(RNA 코돈표) — 3문자 약어(Phe, Leu, ...)를 내부 키로 쓰고,
# 화면에 보여줄 한글 이름은 AMINO_KO에 따로 둔다(내부 키·표시 문구 분리).
CODON_TABLE = {
    "UUU": "Phe", "UUC": "Phe", "UUA": "Leu", "UUG": "Leu",
    "CUU": "Leu", "CUC": "Leu", "CUA": "Leu", "CUG": "Leu",
    "AUU": "Ile", "AUC": "Ile", "AUA": "Ile", "AUG": "Met",
    "GUU": "Val", "GUC": "Val", "GUA": "Val", "GUG": "Val",
    "UCU": "Ser", "UCC": "Ser", "UCA": "Ser", "UCG": "Ser",
    "CCU": "Pro", "CCC": "Pro", "CCA": "Pro", "CCG": "Pro",
    "ACU": "Thr", "ACC": "Thr", "ACA": "Thr", "ACG": "Thr",
    "GCU": "Ala", "GCC": "Ala", "GCA": "Ala", "GCG": "Ala",
    "UAU": "Tyr", "UAC": "Tyr", "UAA": "Stop", "UAG": "Stop",
    "CAU": "His", "CAC": "His", "CAA": "Gln", "CAG": "Gln",
    "AAU": "Asn", "AAC": "Asn", "AAA": "Lys", "AAG": "Lys",
    "GAU": "Asp", "GAC": "Asp", "GAA": "Glu", "GAG": "Glu",
    "UGU": "Cys", "UGC": "Cys", "UGA": "Stop", "UGG": "Trp",
    "CGU": "Arg", "CGC": "Arg", "CGA": "Arg", "CGG": "Arg",
    "AGU": "Ser", "AGC": "Ser", "AGA": "Arg", "AGG": "Arg",
    "GGU": "Gly", "GGC": "Gly", "GGA": "Gly", "GGG": "Gly",
}

AMINO_KO = {
    "Phe": "페닐알라닌", "Leu": "류신", "Ile": "아이소류신", "Met": "메싸이오닌",
    "Val": "발린", "Ser": "세린", "Pro": "프롤린", "Thr": "트레오닌",
    "Ala": "알라닌", "Tyr": "타이로신", "His": "히스티딘", "Gln": "글루타민",
    "Asn": "아스파라진", "Lys": "라이신", "Asp": "아스파트산", "Glu": "글루탐산",
    "Cys": "시스테인", "Trp": "트립토판", "Arg": "아르지닌", "Gly": "글라이신",
    "Stop": "종결",
}

# 화면의 아미노산 선택 목록에 쓸 순서(START/STOP은 따로 취급)
AMINO_ORDER = ["Met", "Leu", "Ile", "Val", "Phe", "Ser", "Pro", "Thr", "Ala",
              "Tyr", "His", "Gln", "Asn", "Lys", "Asp", "Glu", "Cys", "Trp",
              "Arg", "Gly", "Stop"]

_DNA_TO_MRNA = {"A": "U", "T": "A", "G": "C", "C": "G"}


class SequenceError(Exception):
    """서열에 A/T/G/C(또는 U) 말고 다른 글자가 있을 때."""
    pass


def _clean(seq: str) -> str:
    return seq.upper().replace(" ", "").replace("\n", "").replace("\t", "")


def transcribe_from_template(dna_template: str) -> str:
    """DNA 주형 가닥(3'→5' 방향으로 주어졌다고 가정)을 mRNA(5'→3')로
    바꾼다. 각 염기를 상보 염기로 바꾸고 T는 U로 옮긴다(순서는 그대로
    유지 — 파일 맨 위 설명 참고)."""
    seq = _clean(dna_template)
    out = []
    for ch in seq:
        if ch not in _DNA_TO_MRNA:
            raise SequenceError(ch)
        out.append(_DNA_TO_MRNA[ch])
    return "".join(out)


class Translation:
    def __init__(self, codons, aminos, stopped, start_index):
        self.codons = codons       # ["AUG","UCU",...]
        self.aminos = aminos       # ["Met","Ser",...] (마지막이 "Stop"일 수 있음)
        self.stopped = stopped     # 종결코돈으로 끝났는지
        self.start_index = start_index


def translate(mrna: str, start_at_first_aug: bool = False) -> Translation:
    """mRNA를 3염기씩 끊어 코돈표로 아미노산 서열을 만든다. 종결코돈을
    만나면 그 자리에서 멈춘다(종결코돈 자체도 목록의 마지막 항목으로
    포함해서, "여기서 끝난다"는 걸 화면에서 보여줄 수 있게 한다).
    잘 모르는 코돈(정의 밖 글자 등)을 만나면 그 앞까지만 돌려준다."""
    seq = _clean(mrna)
    for ch in seq:
        if ch not in "AUGC":
            raise SequenceError(ch)

    start = 0
    if start_at_first_aug:
        idx = seq.find("AUG")
        if idx == -1:
            return Translation([], [], False, -1)
        start = idx

    codons, aminos = [], []
    stopped = False
    i = start
    while i + 3 <= len(seq):
        codon = seq[i:i + 3]
        amino = CODON_TABLE.get(codon)
        if amino is None:
            break
        codons.append(codon)
        aminos.append(amino)
        if amino == "Stop":
            stopped = True
            break
        i += 3
    return Translation(codons, aminos, stopped, start)


def codons_for(amino_code: str):
    """이 아미노산(3문자 약어)을 지정하는 코돈을 전부 찾는다(정렬된 목록)."""
    return sorted(c for c, a in CODON_TABLE.items() if a == amino_code)


# =============================================================================
# [신규] DNA → mRNA(전사) → 코돈 → 아미노산까지, 과정을 한 단계씩 볼 수
# 있게 만든 처리 — 수능 생명과학에서 "주형 가닥/암호화 가닥을 구분하고,
# 상보적 결합으로 mRNA를 만든 뒤, 3개씩 끊어 코돈을 읽는" 순서 그대로
# 데이터를 만들어 둔다(화면은 이 데이터를 순서대로 보여주기만 하면 됨).
# =============================================================================
_DNA_COMPLEMENT = {"A": "T", "T": "A", "G": "C", "C": "G"}

STRAND_TEMPLATE = "template"    # 주형 가닥(3'→5') — RNA 중합효소가 읽는 가닥
STRAND_CODING = "coding"        # 암호화 가닥(5'→3') — mRNA와 서열이 같음(T→U만 다름)


def complement_dna(seq: str) -> str:
    """DNA 서열의 각 염기를 상보 염기로 바꾼다(순서는 그대로 유지—
    두 가닥을 나란히 써서 같은 위치가 서로 짝을 이루는 걸 보여줄
    때 쓴다)."""
    out = []
    for ch in seq:
        if ch not in _DNA_COMPLEMENT:
            raise SequenceError(ch)
        out.append(_DNA_COMPLEMENT[ch])
    return "".join(out)


class DnaProcess:
    """DNA 한 가닥 입력부터 아미노산까지, 단계별로 볼 수 있는 모든
    중간 데이터를 담는다."""

    def __init__(self, input_seq, strand_type, template_strand, coding_strand,
                mrna, codons, translation):
        self.input_seq = input_seq            # 사용자가 입력한 그대로(정리된 서열)
        self.strand_type = strand_type        # STRAND_TEMPLATE | STRAND_CODING
        self.template_strand = template_strand  # 항상 3'→5' 방향, DNA(A/T/G/C)
        self.coding_strand = coding_strand      # 항상 5'→3' 방향, DNA(A/T/G/C)
        self.mrna = mrna                        # 5'→3' 방향, RNA(A/U/G/C)
        self.codons = codons                    # 3개씩 끊은 mRNA 코돈 목록(번역 시작 위치 반영)
        self.translation = translation          # Translation(번역 결과)


def process_dna(input_seq: str, strand_type: str = STRAND_TEMPLATE,
                start_at_first_aug: bool = False) -> DnaProcess:
    """DNA 한 가닥(주형 또는 암호화 가닥, 사용자가 어느 쪽인지 알려 줌)을
    입력받아, 나머지 가닥 → mRNA(전사) → 코돈 분할 → 아미노산 번역까지
    한 번에 계산해 각 단계 데이터를 모두 돌려준다.

    DNA 두 가닥은 서로 반대 방향(antiparallel)이라, **입력한 순서를
    뒤집지 않고** 각 위치의 염기를 상보 염기로만 바꾸면 나머지 가닥이
    된다(주형 가닥이 3'→5', 암호화 가닥이 5'→3'로 서로 마주 보고
    있다고 가정 — 교과서에서 흔히 쓰는 표기와 같다). 암호화 가닥은
    mRNA와 서열이 완전히 같다(T가 U로 바뀌는 것만 다르다) — 그래서
    RNA 중합효소가 주형 가닥을 상보적으로 복사하면 결과적으로
    암호화 가닥과 같은 서열의 mRNA가 만들어진다."""
    seq = _clean(input_seq)
    for ch in seq:
        if ch not in _DNA_COMPLEMENT:
            raise SequenceError(ch)

    complement = complement_dna(seq)
    if strand_type == STRAND_TEMPLATE:
        template_strand, coding_strand = seq, complement
    else:
        coding_strand, template_strand = seq, complement

    mrna = coding_strand.replace("T", "U")
    n_codons = len(mrna) // 3
    codons = [mrna[i:i + 3] for i in range(0, n_codons * 3, 3)]
    translation = translate(mrna, start_at_first_aug=start_at_first_aug)

    return DnaProcess(seq, strand_type, template_strand, coding_strand, mrna, codons, translation)

# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 극좌표 그래프 [신규] — 순수 로직

r = f(θ) 형태의 극좌표 함수를 θ에 대해 훑어(sweep) x = r·cosθ, y = r·sinθ로
바꾼 뒤 평면에 그린다. 원리는 함수 그래프(graph_solve.py)의 "x를 훑어
y=f(x)를 계산"과 똑같고, 훑는 변수가 x 대신 θ라는 점만 다르다 — 그래서
안전한 수식 평가기(expr.py)를 그대로 재사용한다("theta"라는 이름의 변수로
넘긴다).

각도 모드(RAD/DEG)는 함수 그래프·공학용 계산기와 통일성을 맞추려고 넣었다
— 식 안의 삼각함수(예: cos(theta))는 evaluate()가 angle_mode에 맞춰 계산해
주지만, θ 자체를 x=r·cosθ로 바꾸는 이 파일의 계산은 항상 파이썬
math 모듈(라디안 기준)을 쓰므로, DEG 모드일 때는 θ를 라디안으로 한 번 더
바꿔 준다.

**등각(1:1 비율)이 반드시 필요하다** — 원 r=2를 그렸는데 화면에서
타원처럼 보이면 극좌표 그래프로서는 틀린 그림이다. 그래서 이 모듈은
x/y 두 축의 눈금 폭을 항상 같게 맞추는 것을 전제로 설계되어 있고, 실제
그 등각 처리는 화면(위젯)에서 "가로세로 중 더 좁은 쪽 기준으로 두 축을
같은 배율로 맞추는" 방식으로 이루어진다(공학용 계산기의 반올림 처리처럼,
이 프로젝트가 이미 여러 번 써 온 "정확도를 지키는 근사" 방식과 같은
성격).
"""
import math

from . import expr as E

MIN_SPAN = 1e-6
MAX_SPAN = 1e12


class PolarSampleResult:
    def __init__(self, thetas, rs, xs, ys, error=None):
        self.thetas = thetas
        self.rs = rs
        self.xs = xs
        self.ys = ys
        self.error = error   # 사람이 읽을 오류 문구(있으면) — 그래도 일부는 그려질 수 있다


def sample(expr_text: str, theta_min: float, theta_max: float, n: int,
          angle_mode: str = "rad") -> PolarSampleResult:
    """θ를 [theta_min, theta_max] 구간에서 n개로 훑어 r=f(θ)를 계산하고,
    x=r·cosθ, y=r·sinθ로 바꾼다. r이 음수여도 별도 처리가 필요 없다 —
    cosθ·sinθ와 곱해지는 순간 방향이 저절로 반대쪽(원점 대칭)으로
    뒤집히기 때문이다(극좌표의 표준 규약).

    한 점에서 계산이 안 되면(정의역 밖 등) 그 점만 None으로 비워 두고
    나머지는 계속 그린다 — 함수 그래프와 같은 태도."""
    try:
        tree = E.parse_expr(expr_text)
    except E.CalcError as e:
        return PolarSampleResult([], [], [], [], error=str(e))

    n = max(2, int(n))
    step = (theta_max - theta_min) / (n - 1) if n > 1 else 0.0
    thetas, rs, xs, ys = [], [], [], []
    first_error = None
    for i in range(n):
        theta = theta_min + step * i
        try:
            r = E.eval_tree(tree, angle_mode, 0, {"theta": theta})
        except E.CalcError as e:
            if first_error is None:
                first_error = str(e)
            thetas.append(theta)
            rs.append(None)
            xs.append(None)
            ys.append(None)
            continue
        if not isinstance(r, (int, float)) or not math.isfinite(r):
            thetas.append(theta)
            rs.append(None)
            xs.append(None)
            ys.append(None)
            continue
        theta_rad = theta if angle_mode == "rad" else math.radians(theta)
        thetas.append(theta)
        rs.append(r)
        xs.append(r * math.cos(theta_rad))
        ys.append(r * math.sin(theta_rad))

    all_none = all(x is None for x in xs)
    error = first_error if all_none else None
    return PolarSampleResult(thetas, rs, xs, ys, error=error)


def build_segments(xs, ys):
    """None(정의 안 되는 점)에서 구간을 끊는다 — 함수 그래프의 점근선
    처리와 같은 이유(끊긴 곡선을 직선으로 잇지 않기 위해)."""
    segments = []
    current = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            if current:
                segments.append(current)
                current = []
            continue
        current.append((x, y))
    if current:
        segments.append(current)
    return segments


def auto_bounds(xs, ys, pad_ratio: float = 0.15):
    """훑은 점들을 다 담을 수 있는 (xmin, xmax, ymin, ymax)를 구한다.
    등각을 맞추는 건 위젯의 몫이라, 여기서는 데이터 자체의 바운딩
    박스만 넉넉히(pad_ratio만큼 여유를 두고) 돌려준다."""
    valid = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if not valid:
        return -5.0, 5.0, -5.0, 5.0
    xs_v = [p[0] for p in valid]
    ys_v = [p[1] for p in valid]
    xmin, xmax = min(xs_v), max(xs_v)
    ymin, ymax = min(ys_v), max(ys_v)
    if xmax - xmin < MIN_SPAN:
        xmin, xmax = xmin - 1, xmax + 1
    if ymax - ymin < MIN_SPAN:
        ymin, ymax = ymin - 1, ymax + 1
    pad_x = (xmax - xmin) * pad_ratio
    pad_y = (ymax - ymin) * pad_ratio
    return xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax + pad_y


def clamp_span(span: float) -> float:
    return max(MIN_SPAN, min(MAX_SPAN, span))


# 자주 쓰는 극좌표 곡선 — 빠른 삽입용 예시(내부 키는 화면 문구와 분리).
PRESETS = [
    ("cardioid", "1+cos(theta)", 0.0, 2 * math.pi),
    ("rose3", "cos(3*theta)", 0.0, 2 * math.pi),
    ("rose4", "cos(2*theta)", 0.0, 2 * math.pi),
    ("circle", "3", 0.0, 2 * math.pi),
    ("spiral", "theta", 0.0, 4 * math.pi),
    ("lemniscate_approx", "sqrt(abs(4*cos(2*theta)))", 0.0, 2 * math.pi),
]

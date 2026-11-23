# -*- coding: utf-8 -*-
"""
FolderKit++ — 함수 그래프: 표본화 + 눈금 계산 [v03]

카르노맵의 kmap_solve.py와 같은 이유로 Qt 코드를 한 줄도 넣지 않았다 —
"이 함수를 이 구간에서 그리면 값이 맞는가"를 화면 없이도 검증하기 위해서다.

## 계산은 expr.py를 그대로 재사용한다
공학용 계산기가 쓰는 안전한 수식 평가기(ast 기반, eval() 없음)를 그대로
쓴다. 다른 점은 딱 하나 — x라는 변수 자리가 하나 늘어난다는 것뿐이다.
같은 안전장치(위험한 코드 거부, 무거운 계산 사전 차단)가 그래프에도 그대로
적용된다.

## "정의 안 됨"과 "점근선"은 다르게 다룬다
- **정의역 밖(예: √(음수))** — 그 점만 건너뛴다(끊긴 구간으로 남는다).
- **점근선(예: tan(x)가 π/2를 지날 때)** — 각 점은 계산상 문제가 없지만
  옆 점과 값이 터무니없이 벌어진다. 이걸 그냥 이어 그리면 세로로 뚝 떨어지는
  가짜 직선이 생긴다. 그래서 표본을 다 구한 뒤 "화면에 보이는 세로 폭보다
  훨씬 큰 도약"을 찾아 선을 끊는다(:func:`build_segments`).
"""
import math

from . import expr as E

# 이 오류들은 x값과 무관하게 항상 나는 오류다(문법 오류, 모르는 변수/함수 등).
# 이런 경우는 표본 하나하나 다 계산해 볼 필요 없이 그 자리에서 바로
# "이 함수 자체가 잘못됐다"고 판단해 계산을 멈춘다.
STRUCTURAL_KEYS = {
    "util.calc.err.syntax", "util.calc.err.not_allowed", "util.calc.err.unknown_name",
    "util.calc.err.unknown_func", "util.calc.err.arg_count", "util.calc.err.empty",
    "util.calc.err.too_long",
}

MIN_SPAN = 1e-9      # 이보다 더 확대할 수 없다(0으로 나누기 방지)
MAX_SPAN = 1e12       # 이보다 더 축소할 수 없다(의미 없는 스케일 방지)


class SampleResult:
    __slots__ = ("xs", "ys", "error", "error_params")

    def __init__(self, xs, ys, error, error_params=None):
        self.xs = xs     # x좌표 목록
        self.ys = ys     # y값 목록(정의되지 않은 자리는 None)
        self.error = error   # 함수 전체가 잘못됐을 때만 채워지는 i18n 키
        self.error_params = error_params or {}   # tr(error, **error_params)로 채워 쓴다


def sample(expr_text: str, xmin: float, xmax: float, n: int, angle_mode: str = "rad") -> SampleResult:
    """구간 [xmin, xmax]를 n개 점으로 나눠 f(x)를 계산한다."""
    text = (expr_text or "").strip()
    if not text:
        return SampleResult([], [], "util.calc.err.empty")
    if n < 2:
        n = 2

    try:
        tree = E.parse_expr(text)
    except E.CalcError as e:
        return SampleResult([], [], e.key, e.params)

    # 가운데 지점 하나로 먼저 찔러 본다 — 문법·미지수 오류는 x가 뭐든
    # 항상 똑같이 나므로, 이 한 번의 시도로 "이 함수 자체가 잘못됐는지"를
    # 안전하게 판단할 수 있다(운 나쁘게 점근선 위에 걸리는 경우와는
    # error.key 종류로 구분된다 — domain/div_zero/too_big은 구조적 오류가
    # 아니라 "그 지점에서만" 정의되지 않는 것이므로 계속 진행한다).
    probe_x = xmin + (xmax - xmin) / 2
    try:
        E.eval_tree(tree, angle_mode, 0, {"x": probe_x})
    except E.CalcError as e:
        if e.key in STRUCTURAL_KEYS:
            return SampleResult([], [], e.key, e.params)

    xs = [xmin + (xmax - xmin) * i / (n - 1) for i in range(n)]
    ys = []
    for x in xs:
        try:
            y = E.eval_tree(tree, angle_mode, 0, {"x": x})
            ys.append(float(y))
        except E.CalcError:
            ys.append(None)
    return SampleResult(xs, ys, None)


def robust_y_range(values, pad_ratio: float = 0.12):
    """자동 Y축 범위. 최댓값·최솟값을 그대로 쓰지 않고 2~98 백분위수를 쓰는
    이유: tan(x)처럼 점근선 근처에서 값이 순간적으로 아주 커지는 함수가 하나
    섞여 있으면, 그 값 하나 때문에 나머지 곡선이 전부 한 줄로 눌려 보이게
    된다. 백분위수를 쓰면 그런 극단값 한둘에 스케일 전체가 휘둘리지 않는다.
    """
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return (-10.0, 10.0)
    lo = _percentile(vals, 0.02)
    hi = _percentile(vals, 0.98)
    if hi - lo < 1e-9:
        center = (hi + lo) / 2
        span = max(abs(center) * 0.5, 1.0)
        return (center - span, center + span)
    pad = (hi - lo) * pad_ratio
    return (lo - pad, hi + pad)


def _percentile(sorted_vals, p):
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = p * (len(sorted_vals) - 1)
    lo_i = int(math.floor(idx))
    hi_i = int(math.ceil(idx))
    if lo_i == hi_i:
        return sorted_vals[lo_i]
    frac = idx - lo_i
    return sorted_vals[lo_i] * (1 - frac) + sorted_vals[hi_i] * frac


def build_segments(xs, ys, ymin: float, ymax: float, jump_factor: float = 3.5):
    """이어 그릴 수 있는 구간(연속선)들로 쪼갠다.

    (1) 정의되지 않은 점(None)에서 끊고,
    (2) 화면 세로 폭(ymax-ymin)의 jump_factor배보다 큰 도약이 있으면
        점근선으로 보고 끊는다.
    """
    height = max(ymax - ymin, 1e-9)
    threshold = jump_factor * height
    segments = []
    current = []
    prev_y = None
    for x, y in zip(xs, ys):
        if y is None or not math.isfinite(y):
            if current:
                segments.append(current)
                current = []
            prev_y = None
            continue
        if prev_y is not None and abs(y - prev_y) > threshold:
            if current:
                segments.append(current)
                current = []
        current.append((x, y))
        prev_y = y
    if current:
        segments.append(current)
    return segments


# =============================================================================
# 눈금(그리드 선 위치) 계산 — 이른바 "nice numbers" 알고리즘(Heckbert 방식).
# 1/2/5 × 10ⁿ 꼴의 간격만 쓰기 때문에 "0.37, 0.74, 1.11…" 같은 눈금이
# 나오지 않고 항상 "0, 0.5, 1, 1.5…"처럼 사람이 읽기 좋은 값이 나온다.
# =============================================================================
def _nice_num(value: float, round_down_to_nice: bool) -> float:
    if value <= 0:
        return 0.0
    exp = math.floor(math.log10(value))
    frac = value / (10 ** exp)
    if round_down_to_nice:
        if frac < 1.5:
            nice = 1
        elif frac < 3:
            nice = 2
        elif frac < 7:
            nice = 5
        else:
            nice = 10
    else:
        if frac <= 1:
            nice = 1
        elif frac <= 2:
            nice = 2
        elif frac <= 5:
            nice = 5
        else:
            nice = 10
    return nice * (10 ** exp)


def nice_ticks(vmin: float, vmax: float, target_count: int = 6):
    """[vmin, vmax]를 넉넉히 덮는 "보기 좋은" 눈금 위치 목록."""
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if vmax - vmin < 1e-12:
        vmin, vmax = vmin - 1, vmax + 1

    span = _nice_num(vmax - vmin, False)
    step = _nice_num(span / max(target_count - 1, 1), True)
    if step <= 0:
        step = 1.0

    graph_min = math.floor(vmin / step) * step
    graph_max = math.ceil(vmax / step) * step

    ticks = []
    count = int(round((graph_max - graph_min) / step)) + 1
    count = min(count, 200)   # 부동소수점 오차로 무한 루프에 빠지지 않도록
    for i in range(count):
        ticks.append(round(graph_min + i * step, 10))
    return ticks


def clamp_span(span: float) -> float:
    return max(MIN_SPAN, min(MAX_SPAN, span))


# =============================================================================
# [v10] x절편 / y절편
# =============================================================================
def find_x_intercepts(segments):
    """x절편(y=0이 되는 지점)을 찾는다. **끊긴 구간(segment) 내부에서만**
    부호 변화를 찾는 것이 핵심이다 — tan(x)처럼 점근선을 지나면서 -∞에서
    +∞로 "부호가 바뀌는" 것처럼 보이는 경우를 실제 근으로 착각하지 않기
    위해서다(build_segments가 이미 점근선에서 구간을 끊어 놓았으므로,
    같은 구간 안의 부호 변화는 항상 진짜 근이다)."""
    roots = []
    for seg in segments:
        for x, y in seg:
            if y == 0.0:
                roots.append(x)
        for i in range(len(seg) - 1):
            x1, y1 = seg[i]
            x2, y2 = seg[i + 1]
            if y1 == 0.0 or y2 == 0.0:
                continue
            if (y1 < 0) != (y2 < 0):
                t = y1 / (y1 - y2)
                roots.append(x1 + t * (x2 - x1))

    roots.sort()
    deduped = []
    for r in roots:
        if not deduped or abs(r - deduped[-1]) > 1e-6:
            deduped.append(r)
    return deduped


def y_intercept(expr_text: str, angle_mode: str = "rad"):
    """y절편(x=0에서의 값). 정의되지 않으면(예: 1/x, log(x)) None."""
    try:
        return E.evaluate(expr_text, angle_mode, 0, {"x": 0.0})
    except E.CalcError:
        return None


# =============================================================================
# [v11] x축 추적 + 접선/수직선 — 수치 미분
# =============================================================================
def value_at(expr_text: str, x0: float, angle_mode: str = "rad"):
    """f(x0). 정의되지 않으면 None(팝업 없이 그 자리에서 조용히 처리하는
    이 프로젝트의 일관된 태도 — 그래프의 빈 구간과 같은 논리)."""
    try:
        v = E.evaluate(expr_text, angle_mode, 0, {"x": x0})
    except E.CalcError:
        return None
    return v if isinstance(v, (int, float)) else None


def numeric_slope(expr_text: str, x0: float, view_span: float, angle_mode: str = "rad"):
    """x0에서의 기울기를 중심차분(수치 미분)으로 근사한다 — 기호 미분이
    아니다. 이 프로젝트가 이미 쓰고 있는 "정확한 근사치" 방식과 같은
    성격이다(카르노맵의 Petrick 한도, Y축 자동범위의 백분위수 클리핑 등).

    h를 고정값이나 x0 크기가 아니라 **지금 보이는 x축 폭(view_span)에
    비례**해서 정한다 — 그래야 많이 확대했을 때는 h도 작아지고, 축소했을
    때는 h도 커져서 화면 배율과 무관하게 항상 안정적인 근사 기울기가
    나온다(그래프를 확대해서 접선을 살펴보는 용도에 훨씬 잘 맞는다).
    """
    h = max(abs(view_span) * 1e-4, 1e-9)
    y1 = value_at(expr_text, x0 + h, angle_mode)
    y2 = value_at(expr_text, x0 - h, angle_mode)
    if y1 is None or y2 is None:
        return None
    slope = (y1 - y2) / (2 * h)
    if not math.isfinite(slope):
        return None
    return slope


def normal_slope(tangent_slope):
    """접선과 수직인 직선의 기울기(-1/m). 접선이 수평(m=0)이면 수직선이라
    None을 돌려준다 — 호출하는 쪽이 "수직선(기울기 없음)"으로 그린다."""
    if tangent_slope is None:
        return None
    if abs(tangent_slope) < 1e-12:
        return None
    return -1.0 / tangent_slope

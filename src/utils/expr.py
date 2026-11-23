# -*- coding: utf-8 -*-
"""
FolderKit++ — 수식 평가기 [v01]

공학용 계산기 미니앱이 쓰는 "문자열 수식 → 숫자" 변환기.
파이썬 표준 라이브러리(ast, math)만 쓴다 — sympy/numpy 같은 무거운 의존성을
끌어들이면 PyInstaller 산출물이 수십 MB 부풀고 빌드도 느려지기 때문이다.

## 왜 eval()을 안 쓰는가
`eval("2+3")`은 한 줄이면 되지만, 같은 자리에 `__import__('os').system(...)`도
들어갈 수 있다. 여기서는 수식을 ast.parse()로 **구문 트리**로 바꾼 뒤,
미리 허용한 노드 종류(사칙연산·괄호·숫자·화이트리스트 함수 호출)만 직접
계산한다. 허용 목록에 없는 것이 하나라도 나오면 계산 자체를 거부한다.

## 처리 순서
    표시용 기호 정규화(× ÷ − √ π ^) → 계승(!) 변환 → 암시적 곱셈 보정
      → ast.parse → 화이트리스트 평가

## 계산이 멈추지 않도록
`9^9^9` 같은 수식은 파이썬이 정직하게 계산하려다 프로그램이 통째로 멈춘다.
거듭제곱과 계승은 **계산하기 전에** 결과 자릿수를 추정해서 한도를 넘으면
바로 오류로 돌려보낸다(POW_MAX_DIGITS / FACTORIAL_MAX).
"""
import ast
import math

# =============================================================================
# 한도 — 이 값을 넘는 계산은 시도조차 하지 않는다(UI 멈춤 방지)
# =============================================================================
POW_MAX_DIGITS = 10000   # 거듭제곱 결과의 최대 자릿수 추정치
FACTORIAL_MAX = 1000     # n! 의 최대 n

# 결과를 "자동" 서식으로 보여줄 때의 유효숫자 개수. 파이썬 float가 실제로
# 보장하는 정밀도(약 15~17자리)보다 조금 낮게 잡아, 0.1+0.2가
# 0.30000000000000004로 보이는 부동소수점 잡음을 자연스럽게 걷어낸다.
SIG_DIGITS = 14


class CalcError(Exception):
    """계산 실패. 화면에 보일 문구가 아니라 **i18n 키**를 들고 다닌다 —
    오류 메시지도 한/영/일로 번역되어야 하기 때문이다."""

    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


# =============================================================================
# 1) 표시용 기호 → 파이썬 문법
# =============================================================================
# 화면에는 "4 × √(5)"처럼 사람이 읽기 좋은 기호를 그대로 보여주고(윈도우
# 계산기와 같은 인상), 계산 직전에만 파이썬 문법으로 바꾼다.
_SYMBOLS = {
    "×": "*", "✕": "*", "·": "*",
    "÷": "/",
    "−": "-", "–": "-", "—": "-",   # 유니코드 빼기/대시들
    "√": "sqrt",
    "π": "pi",
    "^": "**",
    "，": ",", "（": "(", "）": ")",  # 전각 입력 보정
}


def normalize(text: str) -> str:
    for src, dst in _SYMBOLS.items():
        text = text.replace(src, dst)
    return text


# =============================================================================
# 2) 계승(!) — 후위 연산자라 ast가 모른다. factorial(...) 호출로 바꿔 준다.
# =============================================================================
def _expand_factorial(s: str) -> str:
    """`5!` → `factorial(5)`, `(2+3)!` → `factorial((2+3))`,
    `sin(1)!` → `factorial(sin(1))` 로 바꾼다.

    '!' 앞에 붙은 피연산자의 시작 위치를 뒤에서 앞으로 훑어 찾는다.
    괄호로 끝나면 짝이 맞는 여는 괄호까지, 거기에 함수 이름이 붙어 있으면
    그 이름까지 함께 감싼다.
    """
    guard = 0
    while "!" in s:
        guard += 1
        if guard > 100:                      # 병적인 입력에 대한 안전장치
            raise CalcError("util.calc.err.syntax")
        i = s.index("!")
        j = i - 1
        while j >= 0 and s[j] == " ":
            j -= 1
        if j < 0:
            raise CalcError("util.calc.err.syntax")

        if s[j] == ")":
            depth = 0
            k = j
            while k >= 0:
                if s[k] == ")":
                    depth += 1
                elif s[k] == "(":
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            if k < 0:
                raise CalcError("util.calc.err.paren")
            m = k - 1                        # 여는 괄호 앞의 함수 이름까지 포함
            while m >= 0 and (s[m].isalnum() or s[m] == "_"):
                m -= 1
            start = m + 1
        elif s[j].isalnum() or s[j] == "_" or s[j] == ".":
            k = j
            while k >= 0 and (s[k].isalnum() or s[k] == "_" or s[k] == "."):
                k -= 1
            start = k + 1
        else:
            raise CalcError("util.calc.err.syntax")

        s = s[:start] + "factorial(" + s[start:i] + ")" + s[i + 1:]
    return s


# =============================================================================
# 3) 암시적 곱셈 — 아주 좁은 범위만
# =============================================================================
# `2(3+4)` `2pi` 처럼 곱셈 기호를 생략해도 계산되게 한다. 다만 규칙을 넓히면
# 멀쩡한 이름을 잘못 쪼갠다 — 단순히 "숫자 뒤에 여는 괄호"로만 판단하면
# `log2(8)`이 `log2*(8)`이 되어 버린다(숫자 2가 함수 이름의 일부인데도
# 앞의 숫자로 오인). 그래서 정규식 대신 한 글자씩 훑으면서, 그 숫자가
# **이름의 꼬리인지 진짜 수인지**까지 확인한다.
def _insert_implicit_mul(s: str) -> str:
    out = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        is_pi = (s.startswith("pi", i)
                 and (i + 2 >= n or not (s[i + 2].isalnum() or s[i + 2] == "_")))
        if ch == "(" or is_pi:
            j = len(out) - 1
            while j >= 0 and out[j] == " ":
                j -= 1
            if j >= 0 and (out[j].isdigit() or out[j] == "." or out[j] == ")"):
                if out[j] == ")":
                    out.append("*")            # `)(` 또는 `)pi`
                else:
                    k = j
                    while k >= 0 and (out[k].isdigit() or out[k] == "."):
                        k -= 1
                    # 숫자 덩어리 앞이 글자면 log2·log10 같은 이름의 일부다 → 건드리지 않음
                    if k < 0 or not (out[k].isalpha() or out[k] == "_"):
                        out.append("*")
        out.append(ch)
        i += 1
    return "".join(out)


# =============================================================================
# 4) 화이트리스트
# =============================================================================
_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Call,
    ast.Name, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub,
)


def _deg_wrap(fn, angle_mode, inverse=False):
    """각도 모드(DEG)일 때 삼각함수 입·출력을 도(°) 단위로 바꿔 주는 껍데기."""
    if inverse:
        def g(x):
            v = fn(x)
            return math.degrees(v) if angle_mode == "deg" else v
        return g

    def f(x):
        return fn(math.radians(x)) if angle_mode == "deg" else fn(x)
    return f


def _safe_factorial(x):
    if isinstance(x, float):
        if not x.is_integer():
            raise CalcError("util.calc.err.domain")
        x = int(x)
    if x < 0:
        raise CalcError("util.calc.err.domain")
    if x > FACTORIAL_MAX:
        raise CalcError("util.calc.err.too_big")
    return math.factorial(x)


def _log(x, base=None):
    return math.log(x) if base is None else math.log(x, base)


def build_functions(angle_mode="rad"):
    """현재 각도 모드에 맞춘 함수 표를 만든다."""
    return {
        # 삼각함수 — DEG 모드에서는 입력을(역함수는 출력을) 도 단위로 처리
        "sin": _deg_wrap(math.sin, angle_mode),
        "cos": _deg_wrap(math.cos, angle_mode),
        "tan": _deg_wrap(math.tan, angle_mode),
        "asin": _deg_wrap(math.asin, angle_mode, inverse=True),
        "acos": _deg_wrap(math.acos, angle_mode, inverse=True),
        "atan": _deg_wrap(math.atan, angle_mode, inverse=True),
        # 쌍곡선함수는 각도 모드와 무관
        "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        # 지수·로그
        "sqrt": math.sqrt, "exp": math.exp,
        "ln": math.log, "log": lambda x, b=10: math.log(x, b), "log2": math.log2,
        # 기타
        "abs": abs, "factorial": _safe_factorial,
        "round": round, "floor": math.floor, "ceil": math.ceil,
        "trunc": math.trunc,
        "min": min, "max": max, "gcd": math.gcd,
        "degrees": math.degrees, "radians": math.radians,
        "hypot": math.hypot,
    }


CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


# =============================================================================
# 5) 평가기
# =============================================================================
class _Evaluator:
    def __init__(self, angle_mode="rad", ans=0, variables=None):
        self.fns = build_functions(angle_mode)
        self.names = dict(CONSTANTS)
        # [v03] 그래프 미니앱이 f(x)를 계산할 때 쓰는 자리 — 계산기는 이
        # 인자를 아예 넘기지 않으므로(variables=None) 기존 동작에 아무런
        # 영향이 없다.
        if variables:
            self.names.update(variables)
        self.names["ans"] = ans

    def eval(self, node):
        if not isinstance(node, _ALLOWED_NODES):
            raise CalcError("util.calc.err.not_allowed")

        if isinstance(node, ast.Expression):
            return self.eval(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise CalcError("util.calc.err.not_allowed")
            return node.value

        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            raise CalcError("util.calc.err.unknown_name", name=node.id)

        if isinstance(node, ast.UnaryOp):
            v = self.eval(node.operand)
            return +v if isinstance(node.op, ast.UAdd) else -v

        if isinstance(node, ast.BinOp):
            return self._binop(node)

        if isinstance(node, ast.Call):
            return self._call(node)

        raise CalcError("util.calc.err.not_allowed")

    def _binop(self, node):
        op = type(node.op)
        a = self.eval(node.left)
        b = self.eval(node.right)

        if op in _BIN_OPS:
            return _BIN_OPS[op](a, b)

        if op is ast.Div:
            if b == 0:
                raise CalcError("util.calc.err.div_zero")
            return a / b

        if op is ast.FloorDiv:
            if b == 0:
                raise CalcError("util.calc.err.div_zero")
            return a // b

        if op is ast.Mod:
            if b == 0:
                raise CalcError("util.calc.err.div_zero")
            return a % b

        if op is ast.Pow:
            return self._pow(a, b)

        raise CalcError("util.calc.err.not_allowed")

    @staticmethod
    def _pow(a, b):
        """거듭제곱 — 계산 **전에** 결과 크기를 추정해서 한도를 넘으면 거부.
        이 방어선이 없으면 `9^9^9` 한 번에 프로그램이 응답 없음 상태가 된다."""
        try:
            if a == 0 and b < 0:
                raise CalcError("util.calc.err.div_zero")
            if abs(a) > 1 and b > 0:
                digits = b * math.log10(abs(a))
                if digits > POW_MAX_DIGITS:
                    raise CalcError("util.calc.err.too_big")
            result = a ** b
        except CalcError:
            raise
        except OverflowError:
            raise CalcError("util.calc.err.too_big")
        except (ValueError, ZeroDivisionError):
            raise CalcError("util.calc.err.domain")
        if isinstance(result, complex):
            # (-8) ** 0.5 처럼 실수 범위를 벗어나는 경우
            raise CalcError("util.calc.err.domain")
        return result

    def _call(self, node):
        if not isinstance(node.func, ast.Name):
            raise CalcError("util.calc.err.not_allowed")
        name = node.func.id
        fn = self.fns.get(name)
        if fn is None:
            raise CalcError("util.calc.err.unknown_func", name=name)
        if node.keywords:
            raise CalcError("util.calc.err.not_allowed")
        args = [self.eval(a) for a in node.args]
        try:
            return fn(*args)
        except CalcError:
            raise
        except ZeroDivisionError:
            raise CalcError("util.calc.err.div_zero")
        except ValueError:
            raise CalcError("util.calc.err.domain")
        except OverflowError:
            raise CalcError("util.calc.err.too_big")
        except TypeError:
            raise CalcError("util.calc.err.arg_count", name=name)


def parse_expr(text: str):
    """수식 문자열을 구문 트리로. [v03] 그래프 미니앱은 함수 하나를 x값
    수백 개에 대해 반복 계산해야 하는데, 매번 문자열을 처음부터 다시
    파싱하면 낭비가 크다. 그래서 "문자열 → 트리"(이 함수, 한 번만)와
    "트리 → 값"(:func:`eval_tree`, 여러 번)을 분리해 둔다.
    """
    if text is None:
        raise CalcError("util.calc.err.empty")
    src = normalize(text).strip()
    if not src:
        raise CalcError("util.calc.err.empty")
    if len(src) > 2000:
        raise CalcError("util.calc.err.too_long")

    src = _expand_factorial(src)
    src = _insert_implicit_mul(src)

    try:
        return ast.parse(src, mode="eval")
    except SyntaxError:
        raise CalcError("util.calc.err.syntax")


def eval_tree(tree, angle_mode: str = "rad", ans=0, variables=None):
    """이미 파싱된 트리를 계산한다. variables는 {"x": 1.5}처럼 이름→값
    사전으로, 그래프 미니앱이 f(x)의 x 자리에 값을 채워 넣을 때 쓴다."""
    value = _Evaluator(angle_mode, ans, variables).eval(tree)

    if isinstance(value, float):
        if math.isnan(value):
            raise CalcError("util.calc.err.domain")
        if math.isinf(value):
            raise CalcError("util.calc.err.too_big")
    if not isinstance(value, (int, float)):
        raise CalcError("util.calc.err.not_allowed")
    return value


def evaluate(text: str, angle_mode: str = "rad", ans=0, variables=None):
    """수식 문자열을 계산해 int 또는 float를 돌려준다.

    실패하면 항상 :class:`CalcError` 를 던진다 — 호출하는 쪽은 이 예외 하나만
    잡으면 되고, 사용자에게 보일 문구는 err.key를 tr()에 넣어 만든다.
    """
    tree = parse_expr(text)
    return eval_tree(tree, angle_mode, ans, variables)


# =============================================================================
# 6) 결과 표시 서식
# =============================================================================
def format_number(value, decimals="auto", group=True) -> str:
    """계산 결과를 화면용 문자열로.

    decimals: "auto"(불필요한 0을 지운 최대 12자리) 또는 정수(고정 자릿수)
    group:    천 단위 쉼표 — 읽기 편하지만, 기록에 저장되는 원본 값과
              복사되는 값에는 넣지 않는다(다시 수식에 붙여 넣을 때 깨지므로).
    """
    if isinstance(value, int):
        s = str(value)
        return _group(s) if group else s

    av = abs(value)
    if value != 0 and (av >= 1e16 or av < 1e-6):
        s = f"{value:.10e}"
        mant, exp = s.split("e")
        mant = mant.rstrip("0").rstrip(".")
        return f"{mant}e{int(exp)}"

    if decimals == "auto":
        # 소수점 이하 자릿수를 고정하면 큰 수에서 float 잡음이 그대로 드러난다
        # (예: 1234567.891 → "1234567.891000000061"). 자릿수를 "유효숫자
        # SIG_DIGITS개"로 환산해서 잡아야 크기와 무관하게 깔끔하다.
        mag = math.floor(math.log10(av)) if av > 0 else 0
        dec = max(0, SIG_DIGITS - int(mag) - 1)
        s = f"{value:.{dec}f}".rstrip("0").rstrip(".")
    else:
        s = f"{value:.{int(decimals)}f}"
    if s in ("-0", "-0.0", ""):
        s = "0"
    return _group(s) if group else s


def _group(s: str) -> str:
    """정수부에만 천 단위 쉼표를 넣는다."""
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "e" in s or "E" in s:
        return ("-" if neg else "") + s
    head, _, tail = s.partition(".")
    if len(head) > 4:                      # 1000까지는 그냥 두는 편이 덜 산만하다
        head = f"{int(head):,}"
    out = head + ("." + tail if tail else "")
    return ("-" if neg else "") + out

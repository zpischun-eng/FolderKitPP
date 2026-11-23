# -*- coding: utf-8 -*-
"""
FolderKit++ — 나이스 급식 정보: URL 생성 + 응답 해석 [v04]

카르노맵의 kmap_solve.py, 함수 그래프의 graph_solve.py와 같은 이유로
Qt·네트워크 코드를 한 줄도 넣지 않았다 — "이 응답을 이렇게 해석하는 게
맞는가"를 실제 인터넷 연결 없이도 검증하기 위해서다. 실제 HTTP 요청은
미니앱 위젯(meal.py)이 Qt의 QNetworkAccessManager로 보내고, 그 결과(바이트)를
이 파일의 함수에 넘겨 해석만 맡긴다.

## NEIS Open API 개요
급식식단정보 API는 교육청코드(ATPT_OFCDC_SC_CODE) + 학교코드(SD_SCHUL_CODE)
+ 날짜(MLSV_YMD, YYYYMMDD)로 그날의 급식을 돌려준다. 인증키(KEY)는 나이스
교육정보 개방 포털(https://open.neis.go.kr)에서 개인이 신청해 발급받는다.

## 알아두면 좋은 실제 동작(직접 확인함)
`Type=json`을 요청해도, 필수 파라미터가 빠졌을 때는 NEIS가 **JSON이 아니라
XML**로 오류를 돌려준다. 그래서 이 파일은 JSON 해석이 실패하면 같은 문자열을
XML로 한 번 더 시도한다(:func:`parse`).
"""
import json as _json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

BASE_URL = "https://open.neis.go.kr/hub/mealServiceDietInfo"

# MMEAL_SC_CODE — 나이스가 정한 끼니 구분 코드. 이 미니앱은 "중식"을
# 우선으로 요청한다(사용자 요청: 날짜별 급식(중식) 정보).
MEAL_LUNCH = "2"
MEAL_BREAKFAST = "1"
MEAL_DINNER = "3"

# 서울특별시교육청 / 선린인터넷고등학교의 나이스 코드. 두 개의 독립된
# 출처(학사일정·공시정보 안내 페이지)에서 같은 값으로 확인했다. 이 두 값은
# 개인정보가 아니라 학교를 가리키는 공개 식별자라 기본값으로 코드에 넣어도
# 안전하다 — 인증키와는 성격이 다르다(그건 절대 하드코딩하지 않는다).
DEFAULT_OFFICE_CODE = "B10"
DEFAULT_SCHOOL_CODE = "7010536"
DEFAULT_SCHOOL_NAME = "선린인터넷고등학교"


class MealEntry:
    """급식 한 끼(예: 중식) 정보."""

    def __init__(self, meal_code, meal_name, dishes, calorie=None, origin=None,
                 nutrition=None, ymd=None):
        self.meal_code = meal_code
        self.meal_name = meal_name
        self.dishes = dishes          # 요리명 목록(줄 단위로 이미 나뉜 상태)
        self.calorie = calorie        # 예: "1055.0 Kcal"
        self.origin = origin          # 원산지 정보, 줄 목록 또는 None
        self.nutrition = nutrition    # 영양 정보, 줄 목록 또는 None
        self.ymd = ymd                # [v08] "20260915" 형태 — 주간 조회에서 날짜 구분용


class MealResult:
    """응답 해석 결과. status는 셀 중 하나:
    "ok"    — meals에 1개 이상의 MealEntry
    "empty" — 요청은 정상, 그날 급식 데이터가 없음(주말/방학 등)
    "error" — 인증키 오류, 파라미터 오류, 응답 형식을 못 알아본 경우 등
    """

    def __init__(self, status, meals=None, message=None):
        self.status = status
        self.meals = meals or []
        self.message = message   # error/empty일 때 서버가 준 원문 메시지(한국어)


def build_url(key, office_code, school_code, ymd=None, meal_code=None,
              ymd_from=None, ymd_to=None):
    """호출할 전체 URL을 만든다. 실제 요청(Qt)과 테스트가 이 함수 하나를
    같이 써서, "무엇을 보냈는지"가 항상 하나로 일치한다.

    [v08] ymd(하루) 대신 ymd_from/ymd_to(기간)를 넘기면 그 기간 전체를
    한 번에 요청한다 — 주간 급식표에 쓴다. NEIS는 MLSV_FROM_YMD/
    MLSV_TO_YMD라는 별도 파라미터로 기간 조회를 받는다(하루짜리
    MLSV_YMD와는 자리가 다르다).
    """
    params = {
        "KEY": key,
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
    }
    if ymd_from and ymd_to:
        params["MLSV_FROM_YMD"] = ymd_from
        params["MLSV_TO_YMD"] = ymd_to
    else:
        params["MLSV_YMD"] = ymd
    if meal_code:
        params["MMEAL_SC_CODE"] = meal_code
    return BASE_URL + "?" + urlencode(params)


def parse(raw_text: str) -> MealResult:
    """서버가 돌려준 원문(바이트를 디코딩한 문자열)을 해석한다.

    JSON으로 먼저 시도하고, 실패하면 XML로 한 번 더 시도한다 — 위에서 설명한
    "필수값 누락일 때는 Type=json이어도 XML로 온다"는 실제 동작 때문이다.
    둘 다 실패하면 "이해할 수 없는 응답"으로 처리한다.
    """
    if raw_text is None or not raw_text.strip():
        return MealResult("error", message=None)

    try:
        data = _json.loads(raw_text)
    except ValueError:
        result = _parse_error_xml(raw_text)
        if result is None:
            return MealResult("error", message=None)
        return result
    return _parse_json(data)


def _parse_json(data: dict) -> MealResult:
    if "mealServiceDietInfo" in data:
        try:
            rows = data["mealServiceDietInfo"][1]["row"]
        except (KeyError, IndexError, TypeError):
            return MealResult("error", message=None)
        meals = [_row_to_entry(r) for r in rows]
        return MealResult("ok", meals)

    result = data.get("RESULT") or {}
    code = result.get("CODE", "")
    message = result.get("MESSAGE") or None
    if code == "INFO-200":   # 정상 요청이지만 그날 데이터가 없음
        return MealResult("empty", message=message)
    return MealResult("error", message=message)


def _parse_error_xml(text: str):
    """`<RESULT><CODE>..</CODE><MESSAGE>..</MESSAGE></RESULT>` 형태만
    다룬다 — 성공 응답은 언제나 JSON으로 오므로, XML은 오류 통지 전용."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    code_el = root.find("CODE")
    if code_el is None:
        return None
    msg_el = root.find("MESSAGE")
    message = msg_el.text if msg_el is not None else None
    code = code_el.text or ""
    if code == "INFO-200":
        return MealResult("empty", message=message)
    return MealResult("error", message=message)


def _row_to_entry(row: dict) -> MealEntry:
    return MealEntry(
        meal_code=row.get("MMEAL_SC_CODE", ""),
        meal_name=row.get("MMEAL_SC_NM", ""),
        dishes=_split_lines(row.get("DDISH_NM", "")),
        calorie=row.get("CAL_INFO") or None,
        origin=_split_lines(row.get("ORPLC_INFO", "")) or None,
        nutrition=_split_lines(row.get("NTR_INFO", "")) or None,
        ymd=row.get("MLSV_YMD") or None,
    )


def group_by_date(meals):
    """[v08] 주간 조회 결과를 날짜별로 묶는다({"20260915": [MealEntry, ...]}).
    같은 날짜에 여러 끼(조식+중식 등)가 있으면 같은 리스트에 순서대로 쌓인다."""
    by_date = {}
    for m in meals:
        if not m.ymd:
            continue
        by_date.setdefault(m.ymd, []).append(m)
    return by_date


def _split_lines(text):
    """NEIS는 여러 줄을 `<br/>`로 이어 하나의 문자열에 담아 보낸다.
    알레르기 유발 식재료 번호(예: "김치5.6.9.")는 안전 정보라 그대로 둔다 —
    지우면 알레르기가 있는 학생에게 오히려 해가 될 수 있다."""
    if not text:
        return []
    parts = [p.strip() for p in text.split("<br/>")]
    return [p for p in parts if p]

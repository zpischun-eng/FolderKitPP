# -*- coding: utf-8 -*-
"""
FolderKit++ — 나이스 학사일정: URL 생성 + 응답 해석 [v05]

meal_solve.py와 같은 구조·이유다 — Qt·네트워크 코드 없이 "이 응답을 이렇게
해석하는 게 맞는가"를 검증한다. 나이스의 학사일정(SchoolSchedule) API는
교육청코드 + 학교코드 + 기간(AA_FROM_YMD~AA_TO_YMD)으로 그 기간의 학교
행사를 돌려준다 — "오늘의 급식"과 인증키·학교 코드를 공유한다
(neis_common.py 참고).
"""
import json as _json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

BASE_URL = "https://open.neis.go.kr/hub/SchoolSchedule"


class ScheduleEvent:
    """행사 하나. ymd는 "20260901" 형태의 8자리 문자열(그대로 보관 —
    날짜 계산은 호출하는 쪽이 필요할 때만 datetime으로 바꾼다)."""

    def __init__(self, ymd, name, content=None, day_type=None):
        self.ymd = ymd
        self.name = name
        self.content = content      # 상세 내용, 없으면 None
        self.day_type = day_type    # 예: "휴업일" — 없으면 None


class ScheduleResult:
    """status: "ok"(events 1개 이상) / "empty"(그 기간에 행사 없음) / "error" """

    def __init__(self, status, events=None, message=None):
        self.status = status
        self.events = events or []
        self.message = message


def build_url(key, office_code, school_code, ymd_from, ymd_to):
    params = {
        "KEY": key,
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "AA_FROM_YMD": ymd_from,
        "AA_TO_YMD": ymd_to,
    }
    return BASE_URL + "?" + urlencode(params)


def parse(raw_text: str) -> ScheduleResult:
    """meal_solve.parse()와 같은 순서: JSON으로 먼저 시도하고, 실패하면
    (필수 파라미터 누락 등으로 XML 오류가 온 경우) XML로 한 번 더 시도한다."""
    if raw_text is None or not raw_text.strip():
        return ScheduleResult("error", message=None)

    try:
        data = _json.loads(raw_text)
    except ValueError:
        result = _parse_error_xml(raw_text)
        if result is None:
            return ScheduleResult("error", message=None)
        return result
    return _parse_json(data)


def _parse_json(data: dict) -> ScheduleResult:
    if "SchoolSchedule" in data:
        try:
            rows = data["SchoolSchedule"][1]["row"]
        except (KeyError, IndexError, TypeError):
            return ScheduleResult("error", message=None)
        events = [_row_to_event(r) for r in rows]
        return ScheduleResult("ok", events)

    result = data.get("RESULT") or {}
    code = result.get("CODE", "")
    message = result.get("MESSAGE") or None
    if code == "INFO-200":
        return ScheduleResult("empty", message=message)
    return ScheduleResult("error", message=message)


def _parse_error_xml(text: str):
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
        return ScheduleResult("empty", message=message)
    return ScheduleResult("error", message=message)


def _row_to_event(row: dict) -> ScheduleEvent:
    return ScheduleEvent(
        ymd=row.get("AA_YMD", ""),
        name=row.get("EVENT_NM", "") or "",
        content=row.get("EVENT_CNTNT") or None,
        day_type=row.get("SBTR_DD_SC_NM") or None,
    )


def events_by_day(events):
    """월 하나에 대한 이벤트 목록을 "그 달의 며칟날(1~31)"로 묶어 준다.
    캘린더 화면이 칸마다 바로 찾아 쓸 수 있게 하기 위함."""
    by_day = {}
    for ev in events:
        if len(ev.ymd) != 8:
            continue
        try:
            day = int(ev.ymd[6:8])
        except ValueError:
            continue
        by_day.setdefault(day, []).append(ev)
    return by_day

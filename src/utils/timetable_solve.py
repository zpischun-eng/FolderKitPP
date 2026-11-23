# -*- coding: utf-8 -*-
"""
FolderKit++ — 컴시간 알리미 간편 버전: URL 생성 + 응답 해석 [v41]

meal_solve.py·schedule_solve.py와 같은 구조·이유다 — Qt·네트워크 코드
없이 "이 응답을 이렇게 해석하는 게 맞는가"만 검증한다. 비공식 컴시간
파싱 대신 나이스 교육정보 개방 포털의 **공식** hisTimetable API를
쓴다(신규 미니앱 개발 스펙 문서 3번 항목) — 학교 사이트 구조가 바뀌어도
깨지지 않는다.

나이스 응답에는 **담당교사 이름이 없다.** 그래서 학급별 시간표는 API
응답만으로 완전히 만들어지지만, 교사별 시간표는 "과목 → 담당교사"
매핑을 앱 안에서 한 번 입력받아 역산하는 방식으로 만든다(이 모듈의
teacher_view가 그 역산을 한다). 매핑 자체는 여기서 저장 형식만
정의하고, 실제 저장은 위젯 쪽 QSettings가 담당한다.
"""
import json as _json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

BASE_URL = "https://open.neis.go.kr/hub/hisTimetable"

# [v43.4] "전체 학급 조사"(교사 시간표용 전체 과목 목록을 만들 때) 훑는
# 범위 — 대부분의 고등학교가 이 안에 들어간다. 실제로 없는 학년·반을
# 조회해도 나이스가 그냥 빈 결과를 주므로, 넉넉하게 잡아도 안전하다.
SURVEY_GRADES = (1, 2, 3)
SURVEY_CLASSES = tuple(range(1, 11))


class TimetableSlot:
    """한 교시의 수업 하나. ymd는 "20260901" 형태 8자리 문자열."""

    def __init__(self, ymd, period, subject, room=None):
        self.ymd = ymd
        self.period = int(period) if period not in (None, "") else 0
        self.subject = subject or ""
        self.room = room or None

    def to_dict(self):
        return {"ymd": self.ymd, "period": self.period, "subject": self.subject, "room": self.room}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("ymd"), d.get("period", 0), d.get("subject", ""), d.get("room"))


class TimetableResult:
    """status: "ok"(slots 1개 이상) / "empty"(그 기간에 시간표 없음) / "error" """

    def __init__(self, status, slots=None, message=None):
        self.status = status
        self.slots = slots or []
        self.message = message


def build_url(key, office_code, school_code, grade, class_nm, ymd_from, ymd_to):
    params = {
        "KEY": key,
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "GRADE": grade,
        "CLASS_NM": class_nm,
        "TI_FROM_YMD": ymd_from,
        "TI_TO_YMD": ymd_to,
    }
    return BASE_URL + "?" + urlencode(params)


def parse(raw_text: str) -> TimetableResult:
    """JSON으로 먼저 시도하고, 실패하면(필수 파라미터 누락 등으로 XML
    오류가 온 경우) XML로 한 번 더 시도한다 — meal_solve.parse()와 같은
    순서."""
    if raw_text is None or not raw_text.strip():
        return TimetableResult("error", message=None)

    try:
        data = _json.loads(raw_text)
    except ValueError:
        result = _parse_error_xml(raw_text)
        if result is None:
            return TimetableResult("error", message=None)
        return result
    return _parse_json(data)


def _parse_json(data: dict) -> TimetableResult:
    if "hisTimetable" in data:
        try:
            rows = data["hisTimetable"][1]["row"]
        except (KeyError, IndexError, TypeError):
            return TimetableResult("error", message=None)
        slots = [_row_to_slot(r) for r in rows]
        return TimetableResult("ok", slots)

    result = data.get("RESULT") or {}
    code = result.get("CODE", "")
    message = result.get("MESSAGE") or None
    if code == "INFO-200":
        return TimetableResult("empty", message=message)
    return TimetableResult("error", message=message)


def _row_to_slot(r):
    ymd = r.get("ALL_TI_YMD") or r.get("TI_YMD") or ""
    return TimetableSlot(ymd, r.get("PERIO"), r.get("ITRT_CNTNT") or "", r.get("CLRM_NM"))


def _parse_error_xml(text: str):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    code_el = root.find("CODE")
    if code_el is None:
        return None
    code = (code_el.text or "").strip()
    message_el = root.find("MESSAGE")
    message = (message_el.text or "").strip() if message_el is not None else None
    if code == "INFO-200":
        return TimetableResult("empty", message=message)
    return TimetableResult("error", message=message)


# ---------------------------------------------------------------- 가공
def group_by_day(slots):
    """ymd -> {period: TimetableSlot}."""
    out = {}
    for s in slots:
        out.setdefault(s.ymd, {})[s.period] = s
    return out


def max_period(slots, default=6):
    return max((s.period for s in slots), default=default) or default


def subjects_of(slots):
    """등장 순서를 유지한, 중복 없는 과목명 목록(매핑 표에 쓴다)."""
    seen = []
    for s in slots:
        if s.subject and s.subject not in seen:
            seen.append(s.subject)
    return seen


def teacher_view(slots, mapping):
    """mapping: {과목명: 교사명}. 반환: {교사명: [(ymd, period, subject, room), ...]}
    (날짜·교시 순 정렬). 매핑에 없는 과목은 그 교사에게 안 들어간다."""
    out = {}
    for s in slots:
        teacher = mapping.get(s.subject)
        if not teacher:
            continue
        out.setdefault(teacher, []).append((s.ymd, s.period, s.subject, s.room))
    for lst in out.values():
        lst.sort(key=lambda t: (t[0], t[1]))
    return out


def teacher_view_all_classes(survey, mapping):
    """[v43.6] 교사 시간표는 그 교사가 실제로 들어가는 **모든 반**을
    가로질러야 한다 — 한 반의 슬롯만으로는 절대 완전한 교사 시간표를
    만들 수 없다(그 교사가 다른 반에서 하는 수업이 안 보이므로). survey는
    "전체 과목 다운로드"가 훑어 온 {(학년,반): [TimetableSlot, ...]}
    전체다. 반환: {교사명: [(학년, 반, ymd, period, subject), ...]}
    (날짜·교시 순 정렬) — 담당 반을 알 수 있도록 subject 대신 (학년,반)도
    같이 담는다."""
    out = {}
    for (grade, cls), slots in survey.items():
        for s in slots:
            teacher = mapping.get(s.subject)
            if not teacher:
                continue
            out.setdefault(teacher, []).append((grade, cls, s.ymd, s.period, s.subject))
    for lst in out.values():
        lst.sort(key=lambda t: (t[2], t[3]))
    return out


def mapping_to_json(mapping):
    return _json.dumps(mapping, ensure_ascii=False)


def mapping_from_json(raw):
    if not raw:
        return {}
    try:
        data = _json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def subjects_to_json(subjects):
    return _json.dumps(list(subjects), ensure_ascii=False)


def subjects_from_json(raw):
    if not raw:
        return []
    try:
        data = _json.loads(raw)
    except ValueError:
        return []
    return [str(s) for s in data] if isinstance(data, list) else []


MAPPING_HEADERS = ["과목", "담당교사"]


def save_mapping_template(path, subjects, mapping=None):
    """[v43.3] "전체 과목 목록 다운로드" — 지금까지 이 도구로 조회했던
    모든 과목(known_subjects, 위젯이 매주 조회할 때마다 누적)을 엑셀
    한 줄씩으로 내보낸다. 이미 입력해 둔 담당교사가 있으면 그 값을
    그대로 채워서 내보낸다 — 다시 받아도 지금까지 입력한 걸 안 잃는다."""
    import openpyxl
    mapping = mapping or {}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "과목-담당교사"
    ws.append(MAPPING_HEADERS)
    for subject in subjects:
        ws.append([subject, mapping.get(subject, "")])
    wb.save(path)


def read_mapping_excel(path):
    """save_mapping_template과 같은 형식(1행 머리글, 과목·담당교사 순)의
    엑셀을 읽어 {과목: 담당교사} dict로 돌려준다. 담당교사 칸이 빈
    과목은 dict에 안 들어간다(아직 안 정한 과목이므로)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    mapping = {}
    for r in range(2, ws.max_row + 1):
        subject = ws.cell(row=r, column=1).value
        teacher = ws.cell(row=r, column=2).value
        subject_s = str(subject).strip() if subject is not None else ""
        teacher_s = str(teacher).strip() if teacher is not None else ""
        if subject_s and teacher_s:
            mapping[subject_s] = teacher_s
    return mapping


def slots_to_json(slots):
    return _json.dumps([s.to_dict() for s in slots], ensure_ascii=False)


def slots_from_json(raw):
    if not raw:
        return []
    try:
        data = _json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [TimetableSlot.from_dict(d) for d in data]


def survey_to_json(survey):
    """survey: {(학년,반): [TimetableSlot, ...]} -> JSON. 튜플 키는 JSON에
    못 쓰므로 "학년-반" 문자열로 바꿔서 저장한다."""
    obj = {f"{grade}-{cls}": [s.to_dict() for s in slots] for (grade, cls), slots in survey.items()}
    return _json.dumps(obj, ensure_ascii=False)


def survey_from_json(raw):
    if not raw:
        return {}
    try:
        data = _json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, rows in data.items():
        grade, _sep, cls = key.partition("-")
        if not _sep:
            continue
        out[(grade, cls)] = [TimetableSlot.from_dict(d) for d in rows]
    return out


def subjects_of_survey(survey):
    """survey({(학년,반): [TimetableSlot,...]}) 전체에서 등장 순서를
    유지한, 중복 없는 과목명 목록을 뽑는다 — "전체 과목 다운로드"가
    쓴다."""
    seen = []
    for slots in survey.values():
        for subject in subjects_of(slots):
            if subject not in seen:
                seen.append(subject)
    return seen

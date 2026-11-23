# -*- coding: utf-8 -*-
"""
FolderKit++ — 학교 일정: 로컬(직접 입력) 연간계획 [v09]

나이스 학사일정 API에는 보통 공휴일·휴업일 정도만 있고, 학교가 실제로
운영하는 세부 연간계획(중간고사 기간, 체육대회, 동아리 발표 등)은 없는
경우가 많다(사용자가 직접 확인한 문제). 그래서 이 파일은 **교사가 직접
입력하는 일정**을 다룬다 — 나이스 데이터를 대체하는 주된 자료가 된다.

Qt·네트워크 코드를 넣지 않은 이유는 다른 *_solve.py 파일들과 같다:
QSettings 저장, 엑셀 읽기/쓰기(openpyxl)를 화면 없이도 검증하기 위해서다.
실제 QSettings 객체는 schedule.py가 만들어 이 파일의 함수에 넘긴다.
"""
import json
from datetime import date, datetime

SET_LOCAL_EVENTS = "util.schedule.local_events"

# 엑셀 열 이름(1행 머리글) — 가져오기/내보내기가 서로 맞춰 쓴다.
EXCEL_HEADERS = ["날짜", "제목", "내용"]


class LocalEvent:
    """교사가 직접 입력한 일정 한 건."""

    def __init__(self, ymd, name, content=None):
        self.ymd = ymd            # "20260915"
        self.name = name
        self.content = content    # 없으면 None

    def to_dict(self):
        return {"ymd": self.ymd, "name": self.name, "content": self.content}

    @staticmethod
    def from_dict(d):
        return LocalEvent(str(d.get("ymd", "")), str(d.get("name", "")), d.get("content") or None)


def load(settings):
    """저장된 전체 로컬 일정을 불러온다(연도 구분 없이 전부 — 여러 학년도가
    섞여도 각 이벤트가 자기 날짜를 들고 있으니 상관없다)."""
    if settings is None:
        return []
    raw = settings.value(SET_LOCAL_EVENTS, "")
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    return [LocalEvent.from_dict(d) for d in items
            if isinstance(d, dict) and d.get("ymd") and d.get("name")]


def save(settings, events):
    if settings is None:
        return
    settings.setValue(SET_LOCAL_EVENTS, json.dumps([e.to_dict() for e in events], ensure_ascii=False))


def events_for_month(events, year, month):
    """그 달에 해당하는 이벤트만 골라 "며칟날"로 묶는다(달력 칸에 바로
    쓰기 좋은 모양). 반환값의 리스트는 `events`의 실제 객체를 그대로
    담으므로, 여기서 얻은 항목을 수정/삭제하면 원본에도 반영된다."""
    prefix = f"{year:04d}{month:02d}"
    by_day = {}
    for e in events:
        if len(e.ymd) == 8 and e.ymd.startswith(prefix):
            try:
                day = int(e.ymd[6:8])
            except ValueError:
                continue
            by_day.setdefault(day, []).append(e)
    return by_day


def parse_ymd_cell(value):
    """엑셀 셀 값을 8자리 YYYYMMDD 문자열로 정규화한다.
    openpyxl은 날짜 서식의 셀을 datetime으로 읾어 주므로 그 경우와,
    "2026-09-15" / "20260915" 같은 문자열 두 경우를 모두 받는다."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
    if len(digits) == 8:
        try:
            datetime.strptime(digits, "%Y%m%d")
        except ValueError:
            return None
        return digits
    return None


class ImportResult:
    def __init__(self, events, skipped):
        self.events = events      # list[LocalEvent] — 새로 읽어들인 것들
        self.skipped = skipped    # 형식이 안 맞아 건너뛴 줄 수


def merge_events(existing, incoming):
    """[버그 수정] 엑셀로 가져온 일정을 기존 목록에 합친다. **같은
    날짜(ymd) + 같은 제목(name)**이 이미 있으면 그 내용(content)만
    갱신하고 새로 추가하지 않는다 — 화면에서 입력한 내용을 그대로 엑셀로
    받았을 때 통째로 중복 등록되던 문제를 고친 것이다. 날짜·제목이 다르면
    새 일정으로 추가한다.

    반환값: (합쳐진 목록, 새로 추가된 건수, 갱신된 건수).
    `existing`은 그대로 두고 새 목록을 돌려준다(제자리에서 바꾸지 않음)."""
    merged = list(existing)
    index = {(e.ymd, e.name): e for e in merged}
    added = 0
    updated = 0
    for ev in incoming:
        key = (ev.ymd, ev.name)
        match = index.get(key)
        if match is not None:
            if match.content != ev.content:
                match.content = ev.content
                updated += 1
        else:
            merged.append(ev)
            index[key] = ev
            added += 1
    return merged, added, updated


def import_excel(path):
    """엑셀 파일(.xlsx)에서 날짜/제목/내용 3열을 읽는다. 1행은 머리글로
    보고 건너뛴다. openpyxl이 없으면 ImportError를 그대로 던진다 — 호출하는
    쪽(위젯)이 안내 메시지를 보여주는 걸로 처리한다."""
    import openpyxl   # noqa: 없으면 여기서 ImportError — 호출자가 처리
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    events = []
    skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row is None or all(c is None for c in row):
            continue
        ymd_raw = row[0] if len(row) > 0 else None
        name_raw = row[1] if len(row) > 1 else None
        content_raw = row[2] if len(row) > 2 else None

        ymd = parse_ymd_cell(ymd_raw)
        name = str(name_raw).strip() if name_raw is not None else ""
        if not ymd or not name:
            skipped += 1
            continue
        content = str(content_raw).strip() if content_raw not in (None, "") else None
        events.append(LocalEvent(ymd, name, content))
    return ImportResult(events, skipped)


def export_excel(path, events):
    """현재 로컬 일정 전체를 날짜순으로 정렬해 .xlsx로 저장한다."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "일정"
    ws.append(EXCEL_HEADERS)
    for e in sorted(events, key=lambda x: x.ymd):
        pretty = f"{e.ymd[:4]}-{e.ymd[4:6]}-{e.ymd[6:8]}" if len(e.ymd) == 8 else e.ymd
        ws.append([pretty, e.name, e.content or ""])
    wb.save(path)

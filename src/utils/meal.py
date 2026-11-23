# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 #4: 오늘의 급식 [v08]

나이스(NEIS) 교육정보 개방 포털의 급식식단정보 Open API로 날짜별(또는
주간) 중식 정보를 받아온다. 다른 미니앱과 달리 인터넷 연결이 필요하다.

## [v08] 내용을 QTextEdit로 그리는 이유
v04~v07은 요리명을 QLabel 여러 개로(카드 하나에 줄줄이) 그렸다. 그 방식은
마우스로 드래그해도 한 줄씩만 선택되고, 인쇄할 방법도 없었다. 이번에는
읽기 전용 QTextEdit에 HTML로 그린다 — 그러면:
1. 마우스 드래그로 여러 줄을 한 번에 선택해 복사할 수 있고,
2. QTextEdit이 들고 있는 QTextDocument를 그대로 프린터에 넘길 수 있다.

## 일별/주간
일별은 그날 하루, 주간은 **오늘이 포함된 주의 월~금**을 표로 보여준다.
날짜 선택기(달력)는 두 모드가 함께 쓴다 — 일별일 때는 고른 날짜 하루,
주간일 때는 고른 날짜가 속한 주의 월~금이 기준이 된다(처음 열었을 때는
오늘 날짜가 기준이라 "오늘이 포함된 월~금"이 된다).
"""
import calendar
from datetime import date, timedelta

from PySide6.QtCore import Qt, QUrl, QDate, QMarginsF
from PySide6.QtGui import QPageLayout, QTextDocument, QColor, QPainter
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTextEdit
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import meal_solve as M
from . import print_grid as PG
from . import neis_common as N
from .neis_common import NeisSettingsPanel

_WEEKDAY_SHORT_KEYS = ["util.meal.wd.mon", "util.meal.wd.tue", "util.meal.wd.wed",
                       "util.meal.wd.thu", "util.meal.wd.fri", "util.meal.wd.sat",
                       "util.meal.wd.sun"]


def _width_attrs(width_px, n_cols):
    """(표 전체 width 속성값, 칸 하나의 width 속성값)을 만든다.
    width_px가 없으면(화면 표시용) 퍼센트 속성을, 있으면(인쇄용) 정확한
    정수 픽셀 값을 돌려준다 — 이유는 _build_weekly_html의 설명 참고."""
    if width_px:
        total = max(int(width_px), n_cols)
        return total, total // n_cols
    return "100%", f"{100 // n_cols}%"


def _fs(px_size, width_px):
    """스타일 속성에 그대로 이어붙일 `font-size:...;` 조각(또는 빈 문자열)
    을 만든다.

    인쇄용(width_px 있음)은 **`pt`(포인트, 절대 단위)**로 정확한 크기를
    낸다 — Qt의 리치 텍스트 엔진이 인쇄 시 작은 `px` 글자 크기를 사실상
    렌더링하지 못하는 현상을 직접 확인했다.

    [버그 수정] 화면(width_px=None)은 **빈 문자열**을 낸다 — 이유는
    `_small()`의 설명을 보라. 화면에서 글자를 작게 보이고 싶은 자리는
    이 함수 대신 `_small()`로 감싼다."""
    if width_px:
        return f"font-size:{max(6, round(px_size * 0.75))}pt;"
    return ""


def _small(text, width_px):
    """화면에서 "작게" 보여야 하는 텍스트를 감싼다.

    [버그 수정] Ctrl+휠(Qt의 zoomIn/zoomOut)로 확대해도 표 안의 글자는
    전혀 커지지 않고 제목만 커지던 문제의 원인을 직접 실험으로 확인했다
    — Qt 리치 텍스트 엔진은 `font-size`가 **명시적으로 지정된** 글자에는
    zoom 배율을 아예 적용하지 않는다(px든 pt든 마찬가지). 반면 크기를
    전혀 지정하지 않은 글자, 그리고 `<small>`/`<big>`처럼 **상대적인**
    크기 태그는 zoom에 반응한다(실측으로 확인: 확대 시 높이가 약 2.7배
    커짐). 그래서 화면에서는 절대 크기 대신 이 태그를 쓴다.

    인쇄용(width_px 있음)에서는 `_fs()`가 이미 정확한 pt 크기를 주므로
    그대로 둔다(여기서 감싸면 오히려 상대·절대 크기가 겹쳐 계산된다)."""
    if width_px:
        return text
    return f"<small>{text}</small>"


class MealWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.nam = QNetworkAccessManager(self)
        self._reply = None
        self._current_date = date.today()
        self.mode = "daily"   # "daily" / "weekly" / "monthly"
        self._last_result = None   # [버그 수정] 인쇄 시 원본 데이터로 다시 그리기 위해 보관

        self.office_code = N.DEFAULT_OFFICE_CODE
        self.school_code = N.DEFAULT_SCHOOL_CODE
        self.school_name = N.DEFAULT_SCHOOL_NAME

        self._build_ui()
        self._load_settings()
        self._retranslate_static()
        self._fetch()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        office, school, school_name, key = N.load(self._settings)
        self.office_code, self.school_code, self.school_name = office, school, school_name
        self.neis_panel.set_values(key, office, school, school_name)

    def _save_settings(self):
        key, office, school, name = self.neis_panel.values()
        N.save(self._settings, key, office, school, name)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 상단 카드: 날짜/보기 방식(툴바에 일별·주간·월별 토글, 설정 ⚙, 하단에 인쇄) ----
        self.neis_panel = NeisSettingsPanel()
        self.neis_panel.changed.connect(self._on_neis_settings_changed)

        self.card_nav = UK.Card()
        self.btn_daily = UK.toggle_button()
        self.btn_daily.clicked.connect(lambda: self._set_mode("daily"))
        self.card_nav.add_tool(self.btn_daily)
        self.btn_weekly = UK.toggle_button()
        self.btn_weekly.clicked.connect(lambda: self._set_mode("weekly"))
        self.card_nav.add_tool(self.btn_weekly)
        self.btn_monthly = UK.toggle_button()
        self.btn_monthly.clicked.connect(lambda: self._set_mode("monthly"))
        self.card_nav.add_tool(self.btn_monthly)
        self.card_nav.add_tool(self.neis_panel.toggle)

        self.btn_prev = UK.tool_button("◀")
        self.btn_prev.clicked.connect(lambda: self._shift_date(-1))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setFixedWidth(110)
        self.date_edit.dateChanged.connect(self._on_date_changed)
        self.btn_next = UK.tool_button("▶")
        self.btn_next.clicked.connect(lambda: self._shift_date(1))
        self.btn_today = UK.secondary_button()
        self.btn_today.clicked.connect(self._go_today)
        self.lbl_weekday = QLabel()
        self.lbl_weekday.setStyleSheet(f"color:{C.WINDOW_FG};font-weight:bold;background:transparent;")
        self.card_nav.add_body(UK.hrow(self.btn_prev, self.date_edit, self.btn_next, self.btn_today,
                                       self.lbl_weekday, stretch_last=True))
        self.card_nav.add_body(self.neis_panel.panel)

        self.btn_print = self.card_nav.add_footer(UK.secondary_button())
        self.btn_print.clicked.connect(self._print)

        # ---- 하단 카드: 급식 내용(읽기 전용 텍스트 — 드래그 선택 복사 + 인쇄) ----
        self.card_view = UK.Card()
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setStyleSheet("QTextEdit{background-color:#ffffff;border:none;padding:6px;}")
        self.card_view.add_body(UK.canvas_frame(self.view), 1)

        UK.split_tb(self, self.card_nav, self.card_view)
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        self.btn_daily.setChecked(self.mode == "daily")
        self.btn_weekly.setChecked(self.mode == "weekly")
        self.btn_monthly.setChecked(self.mode == "monthly")

    # ---------------------------------------------------------------- 조작
    def _on_neis_settings_changed(self):
        _key, office, school, name = self.neis_panel.values()
        self.office_code, self.school_code, self.school_name = office, school, name
        self._save_settings()
        self._fetch()

    def _set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        self._update_mode_buttons()
        self._fetch()

    def _shift_date(self, delta_days):
        if self.mode == "weekly":
            self.date_edit.setDate(self.date_edit.date().addDays(delta_days * 7))
        elif self.mode == "monthly":
            self.date_edit.setDate(self.date_edit.date().addMonths(delta_days))
        else:
            self.date_edit.setDate(self.date_edit.date().addDays(delta_days))

    def _go_today(self):
        self.date_edit.setDate(QDate.currentDate())

    def _on_date_changed(self, qdate):
        self._current_date = date(qdate.year(), qdate.month(), qdate.day())
        self._update_weekday_label()
        self._fetch()

    def _update_weekday_label(self):
        names_key = [
            "util.meal.weekday.mon", "util.meal.weekday.tue", "util.meal.weekday.wed",
            "util.meal.weekday.thu", "util.meal.weekday.fri", "util.meal.weekday.sat",
            "util.meal.weekday.sun",
        ]
        self.lbl_weekday.setText(tr(names_key[self._current_date.weekday()]))

    def _week_bounds(self):
        """고른 날짜가 속한 주의 월요일·금요일. 처음 열었을 때는 고른 날짜가
        오늘이므로 자연히 "오늘이 포함된 월~금"이 된다."""
        monday = self._current_date - timedelta(days=self._current_date.weekday())
        friday = monday + timedelta(days=4)
        return monday, friday

    def _month_bounds(self):
        """고른 날짜가 속한 달의 1일과 마지막 날."""
        first = self._current_date.replace(day=1)
        last_day = calendar.monthrange(first.year, first.month)[1]
        last = first.replace(day=last_day)
        return first, last

    # ---------------------------------------------------------------- 요청
    def _fetch(self):
        key, _office, _school, _name = self.neis_panel.values()
        if not key:
            self._show_status(tr("util.meal.status.need_key"))
            return

        if self._reply is not None:
            self._reply.abort()
            self._reply = None

        self._show_status(tr("util.meal.status.loading"))
        if self.mode == "weekly":
            monday, friday = self._week_bounds()
            url = M.build_url(key, self.office_code, self.school_code,
                              ymd_from=monday.strftime("%Y%m%d"),
                              ymd_to=friday.strftime("%Y%m%d"), meal_code=M.MEAL_LUNCH)
        elif self.mode == "monthly":
            first, last = self._month_bounds()
            url = M.build_url(key, self.office_code, self.school_code,
                              ymd_from=first.strftime("%Y%m%d"),
                              ymd_to=last.strftime("%Y%m%d"), meal_code=M.MEAL_LUNCH)
        else:
            ymd = self._current_date.strftime("%Y%m%d")
            url = M.build_url(key, self.office_code, self.school_code, ymd=ymd,
                              meal_code=M.MEAL_LUNCH)
        req = QNetworkRequest(QUrl(url))
        reply = self.nam.get(req)
        self._reply = reply
        reply.finished.connect(lambda: self._on_reply_finished(reply))

    def _on_reply_finished(self, reply):
        if reply is not self._reply:
            reply.deleteLater()   # 이미 취소되고 새 요청이 나간 뒤 도착한 응답
            return
        self._reply = None

        if reply.error() != QNetworkReply.NoError:
            if reply.error() != QNetworkReply.OperationCanceledError:
                self._show_status(tr("util.meal.status.network_error", a0=reply.errorString()))
                if self.host:
                    self.host.log(tr("util.meal.log.network_error", a0=reply.errorString()))
            reply.deleteLater()
            return

        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        result = M.parse(raw)
        self._render(result)

    # ---------------------------------------------------------------- 표시
    def _show_status(self, text):
        html = (f'<div style="text-align:center;color:#8a8f98;font-size:13px;'
                f'padding:24px;">{_html_escape(text)}</div>')
        self.view.setHtml(html)

    def _render(self, result: M.MealResult):
        if result.status == "error":
            msg = result.message or tr("util.meal.status.unknown_error")
            self._show_status(tr("util.meal.status.error", a0=msg))
            if self.host:
                self.host.log(tr("util.meal.log.error", a0=msg))
            return

        self._last_result = result   # [버그 수정] 인쇄 시 화면 문서를 되읽지 않고 원본 데이터로 다시 그리기 위해 보관
        if self.mode == "weekly":
            self._render_weekly(result)
        elif self.mode == "monthly":
            self._render_monthly(result)
        else:
            self._render_daily(result)

    def _render_daily(self, result: M.MealResult):
        if result.status == "empty" or not result.meals:
            self._show_status(tr("util.meal.status.empty"))
            if self.host:
                self.host.log(tr("util.meal.log.empty", a0=self._current_date.isoformat()))
            return

        self.view.setHtml(self._build_daily_html(result))

        first = result.meals[0]
        if self.host:
            self.host.status(tr("util.meal.status.done", a0=first.meal_name, a1=len(first.dishes)))
            self.host.log(tr("util.meal.log.done",
                             a0=self._current_date.isoformat(), a1=first.meal_name))

    def _build_daily_html(self, result: M.MealResult, width_px=None) -> str:
        return "".join(_meal_block_html(meal, width_px) for meal in result.meals)

    def _render_weekly(self, result: M.MealResult):
        monday, friday = self._week_bounds()
        html, total_dishes = self._build_weekly_html(result, monday, friday)
        self.view.setHtml(html)
        if self.host:
            self.host.status(tr("util.meal.status.weekly_done", a0=total_dishes))
            self.host.log(tr("util.meal.log.weekly_done",
                             a0=monday.isoformat(), a1=friday.isoformat()))

    def _build_weekly_html(self, result: M.MealResult, monday, friday, width_px=None):
        """[버그 수정] 표 폭·칸 폭을 CSS `style="width:...`가 아니라 **HTML
        width 속성**으로 지정한다. Qt의 리치 텍스트 엔진은 `<table>`에서
        CSS width를 사실상 무시하고 옛 HTML4 스타일의 width 속성만 존중한다
        (직접 픽셀 단위로 그려서 확인함). 화면에 붙어 있는 QTextEdit에서는
        `width="100%"`(속성)가 위젯 폭을 기준으로 정상 동작하지만, 인쇄용
        문서는 위젯에 붙어 있지 않은 독립 문서라 퍼센트가 기준으로 삼을
        폭이 없어 동작하지 않는다 — 그래서 인쇄할 때는 `width_px`로 실제
        프린터 페이지 폭을 픽셀 값으로 직접 넘겨받는다.
        """
        by_date = M.group_by_date(result.meals) if result.status == "ok" else {}
        days = [monday + timedelta(days=i) for i in range(5)]
        table_w, col_w = _width_attrs(width_px, 5)

        cells = []
        total_dishes = 0
        for d in days:
            ymd = d.strftime("%Y%m%d")
            entries = by_date.get(ymd, [])
            header = f"{tr(_WEEKDAY_SHORT_KEYS[d.weekday()])} {d.month}/{d.day}"
            is_today = (d == date.today())

            if entries:
                dish_html = "<br>".join(_html_escape(x) for e in entries for x in e.dishes)
                cal = entries[0].calorie
                total_dishes += sum(len(e.dishes) for e in entries)
                cal_color = "#ffffff" if is_today else "#9aa0a8"
                cal_html = (f'<div style="color:{cal_color};{_fs(10, width_px)}margin-top:4px;">'
                           f'{_small(_html_escape(cal), width_px)}</div>') if cal else ""
                body = dish_html + cal_html
            else:
                empty_color = "#ffffff" if is_today else "#c6c9ce"
                body = f'<span style="color:{empty_color};">{_html_escape(tr("util.meal.status.empty_short"))}</span>'

            # [버그 수정] "오늘" 표시를 헤더 칩 하나가 아니라 **칸 전체
            # 배경**으로 넓히고, 메뉴 글자도 흰색으로 바꿔 더 눈에 띄게
            # 했다(요청 반영).
            if is_today:
                td_style = (f"border:1px solid {C.BORDER};padding:8px;vertical-align:top;"
                           f"background:{C.UTIL_MAIN};color:#ffffff;{_fs(13, width_px)}")
                head_style = "color:#ffffff;"
            else:
                td_style = f"border:1px solid {C.BORDER};padding:8px;vertical-align:top;{_fs(13, width_px)}"
                head_style = "background:#f3f0f2;color:#444;"
            cells.append(
                f'<td width="{col_w}" style="{td_style}"><div style="{head_style}padding:3px 6px;'
                f'border-radius:4px;font-weight:bold;{_fs(12, width_px)}margin-bottom:6px;">'
                f'{_html_escape(header)}</div><br>{body}</td>')

        title = tr("util.meal.weekly.title", a0=f"{monday.month}/{monday.day}", a1=f"{friday.month}/{friday.day}")
        html = (
            f'<h3 style="color:{C.UTIL_MAIN};margin-bottom:8px;">{_html_escape(title)}</h3>'
            f'<table width="{table_w}" cellspacing="0" style="border-collapse:collapse;table-layout:fixed;">'
            f'<tr>{"".join(cells)}</tr></table>'
            f'<p style="color:#8a8f98;{_fs(10, width_px)}margin-top:10px;">'
            f'{_small(_html_escape(tr("util.meal.allergy_note")), width_px)}</p>'
        )
        return html, total_dishes

    def _render_monthly(self, result: M.MealResult):
        first, last = self._month_bounds()
        html, total_dishes, has_any = self._build_monthly_html(result, first, last)
        if not has_any:
            self._show_status(tr("util.meal.status.empty"))
            if self.host:
                self.host.log(tr("util.meal.log.empty", a0=first.strftime("%Y-%m")))
            return
        self.view.setHtml(html)
        if self.host:
            self.host.status(tr("util.meal.status.monthly_done", a0=total_dishes))
            self.host.log(tr("util.meal.log.monthly_done", a0=first.strftime("%Y-%m")))

    def _build_monthly_html(self, result: M.MealResult, first, last, width_px=None):
        """[버그 수정] 토요일·일요일은 급식이 없는 날(공휴일)이라 애초에
        표에 넣을 이유가 없다 — 주간 급식표가 이미 월~금만 보여주는 것과
        맞춰, 월별도 **월~금 5칸**만 그린다(일반 탁상 달력의 토·일 칸을
        아예 없앤 모양). 이전/다음 달에 걸치는 칸은 옅게 비워 둔다."""
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
        by_date = M.group_by_date(result.meals) if result.status == "ok" else {}
        table_w, col_w = _width_attrs(width_px, 5)

        header_cells = "".join(
            f'<th width="{col_w}" style="border:1px solid {C.BORDER};padding:4px;'
            f'background:#f3f0f2;color:#444;{_fs(11, width_px)}">{tr(k)}</th>'
            for k in _WEEKDAY_SHORT_KEYS[:5])

        total_dishes = 0
        has_any = False
        row_htmls = []
        for week in weeks:
            cells = []
            for d in week[:5]:   # 월~금만(토·일은 뒤에 버림)
                in_month = (d.month == first.month)
                ymd = d.strftime("%Y%m%d")
                entries = by_date.get(ymd) if in_month else None
                is_today = (d == date.today())

                if entries:
                    has_any = True
                    total_dishes += sum(len(e.dishes) for e in entries)
                    dish_html = "<br>".join(_html_escape(x) for e in entries for x in e.dishes)
                    cal = entries[0].calorie
                    cal_color = "#ffffff" if is_today else "#9aa0a8"
                    dish_color = "color:#ffffff;" if is_today else ""
                    cal_html = (f'<div style="color:{cal_color};{_fs(9, width_px)}">'
                               f'{_small(_html_escape(cal), width_px)}</div>' if cal else "")
                    body = (f'<div style="{dish_color}{_fs(10, width_px)}line-height:1.3;margin-top:2px;">'
                           f'{_small(dish_html, width_px)}</div>{cal_html}')
                else:
                    body = ""

                # [버그 수정] "오늘"은 칸 전체를 채워 눈에 잘 띄게 하고
                # (주간 급식표와 통일), 날짜·메뉴 글자는 흰색으로 바꾼다.
                if is_today:
                    td_style = (f"border:1px solid {C.BORDER};padding:4px;vertical-align:top;"
                               f"background:{C.UTIL_MAIN};")
                    num_html = f'<span style="color:#ffffff;font-weight:bold;{_fs(11, width_px)}">{d.day}</span>'
                else:
                    bg = "background:#fafafa;" if not in_month else ""
                    td_style = f"border:1px solid {C.BORDER};padding:4px;vertical-align:top;{bg}"
                    num_color = "#444" if in_month else "#c6c9ce"
                    num_html = f'<span style="color:{num_color};font-weight:bold;{_fs(11, width_px)}">{d.day}</span>'
                cells.append(f'<td width="{col_w}" style="{td_style}">{num_html}{body}</td>')
            row_htmls.append(f"<tr>{''.join(cells)}</tr>")

        title = tr("util.meal.monthly.title", a0=first.year, a1=first.month)
        html = (
            f'<h3 style="color:{C.UTIL_MAIN};margin-bottom:8px;">{_html_escape(title)}</h3>'
            f'<table width="{table_w}" cellspacing="0" style="border-collapse:collapse;table-layout:fixed;">'
            f'<tr>{header_cells}</tr>{"".join(row_htmls)}</table>'
            f'<p style="color:#8a8f98;{_fs(10, width_px)}margin-top:10px;">'
            f'{_small(_html_escape(tr("util.meal.allergy_note")), width_px)}</p>'
        )
        return html, total_dishes, has_any

    # ---------------------------------------------------------------- 인쇄
    def _print(self):
        """지금 보이는 내용(일별/주간표/월간 달력)을 인쇄한다.

        [버그 수정 — 3차] HTML `<table>`로 인쇄하는 방식(2차 수정에서
        HTML4 width 속성으로 바꾼 것)도 실제 프린터에서는 부족했다 —
        실측해 보니 칸에 내용이 짧으면 표 전체가 지정한 폭보다 좁게
        자동으로 줄어들고, 그 줄어든 표가 한쪽으로 치우쳐 배치되어
        좌우 여백이 크게(때로는 비대칭으로, 예: 좌 23mm·우 57mm) 남았다.
        Qt의 리치 텍스트 엔진은 결국 `<table>` 치수를 우리가 지정한
        그대로 믿을 수 없다는 뜻이라, **주간·월별 표는 이제 HTML이
        아니라 `print_grid` 모듈로 직접 그린다**(칸 위치·폭을 우리가
        직접 계산해 그리므로 여백도 폭도 지정한 그대로 나온다). 그
        모듈은 칸이 페이지 경계에 걸치면 그 칸을 그리기 전에 새
        페이지로 넘겨, 중간에 잘리는 일도 없다. 일별은 표가 아니라
        간단한 목록이라 기존 HTML 인쇄를 그대로 쓴다."""
        if self._last_result is None:
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(QPageLayout.Landscape)
        printer.setFullPage(True)   # 프린터 드라이버가 강요하는 여백을 무시하고 우리가 직접 정한다

        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(tr("util.meal.print.dialog_title"))
        if not dlg.exec():
            return
        printer.setFullPage(True)   # 대화상자가 되돌릴 수 있으니 확정 후 다시 강제

        margin_pt = 3 * 2.83465   # 좌우 여백 최소화 요청 반영(약 3mm)

        if self.mode == "daily":
            page_width = printer.pageRect(QPrinter.Point).width()
            doc = QTextDocument()
            doc.setHtml(self._build_daily_html(self._last_result, width_px=page_width))
            doc.setTextWidth(page_width)
            doc.print_(printer)
        else:
            headers = [tr(k) for k in _WEEKDAY_SHORT_KEYS[:5]]
            if self.mode == "weekly":
                monday, friday = self._week_bounds()
                week_rows = [self._weekly_grid_cells(self._last_result, monday)]
                title = tr("util.meal.weekly.title", a0=f"{monday.month}/{monday.day}",
                          a1=f"{friday.month}/{friday.day}")
            else:
                first, last = self._month_bounds()
                week_rows = self._monthly_grid_weeks(self._last_result, first, last)
                title = tr("util.meal.monthly.title", a0=first.year, a1=first.month)
            painter = QPainter(printer)
            PG.print_calendar(printer, painter, title, C.UTIL_MAIN, headers, week_rows,
                              margin_pt=margin_pt, footer_text=tr("util.meal.allergy_note"))
            painter.end()

        if self.host:
            self.host.log(tr("util.meal.log.printed"))

    def _weekly_grid_cells(self, result: M.MealResult, monday):
        """주간 인쇄용 칸 5개(월~금)를 만든다. 화면용 HTML과 같은 정보를
        `print_grid.GridCell`로 옮긴 것뿐이다."""
        by_date = M.group_by_date(result.meals) if result.status == "ok" else {}
        today = date.today()
        cells = []
        for i in range(5):
            d = monday + timedelta(days=i)
            ymd = d.strftime("%Y%m%d")
            entries = by_date.get(ymd, [])
            is_today = (d == today)
            fg = "#ffffff" if is_today else None
            header = f"{tr(_WEEKDAY_SHORT_KEYS[d.weekday()])} {d.month}/{d.day}"
            lines = [(header, fg or "#444444", True, 11.5)]
            if entries:
                for e in entries:
                    for dish in e.dishes:
                        lines.append((dish, fg or "#000000", False, 10))
                cal = entries[0].calorie
                if cal:
                    lines.append((cal, fg or "#9aa0a8", False, 9))
            else:
                lines.append((tr("util.meal.status.empty_short"), fg or "#c6c9ce", False, 10))
            cells.append(PG.GridCell(lines, bg=QColor(C.UTIL_MAIN) if is_today else None))
        return cells

    def _monthly_grid_weeks(self, result: M.MealResult, first, last):
        """월별 인쇄용 주(week) 목록을 만든다 — 각 주는 월~금 칸 5개."""
        by_date = M.group_by_date(result.meals) if result.status == "ok" else {}
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
        today = date.today()
        out = []
        for week in weeks:
            cells = []
            for d in week[:5]:
                in_month = (d.month == first.month)
                ymd = d.strftime("%Y%m%d")
                entries = by_date.get(ymd) if in_month else None
                is_today = (d == today)
                fg = "#ffffff" if is_today else None
                lines = [(str(d.day), fg or "#444444", True, 11.5)]
                if entries:
                    for e in entries:
                        for dish in e.dishes:
                            lines.append((dish, fg or "#000000", False, 10))
                    cal = entries[0].calorie
                    if cal:
                        lines.append((cal, fg or "#9aa0a8", False, 9))
                cells.append(PG.GridCell(lines, bg=QColor(C.UTIL_MAIN) if is_today else None,
                                         faded=not in_month))
            out.append(cells)
        return out

    # ------------------------------------------------------------- 다국어
    def _retranslate_static(self):
        self.neis_panel.retranslate()
        self.card_nav.set_title(tr("util.meal.card.nav"))
        self.card_view.set_title(tr("util.meal.title"))
        self.btn_daily.setText(tr("util.meal.btn.daily"))
        self.btn_weekly.setText(tr("util.meal.btn.weekly"))
        self.btn_monthly.setText(tr("util.meal.btn.monthly"))
        self.btn_today.setText(tr("util.meal.btn.today"))
        self.btn_print.setText(tr("util.meal.btn.print"))
        self.btn_print.setToolTip(tr("util.meal.btn.print.tip"))
        self._update_weekday_label()

    def retranslate(self):
        self._retranslate_static()
        # 지금 화면이 오류/안내 문구였다면 새 언어로 다시 표시되도록 재요청.
        self._fetch()


def _html_escape(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _meal_block_html(meal: M.MealEntry, width_px=None) -> str:
    cal_html = (f'<span style="color:#6b7280;{_fs(12, width_px)}">'
               f'({_small(_html_escape(meal.calorie), width_px)})</span>' if meal.calorie else "")
    if meal.dishes:
        items = "".join(f"<li>{_html_escape(d)}</li>" for d in meal.dishes)
        body = f'<ul style="margin-top:4px;">{items}</ul>'
    else:
        body = f'<p style="color:#8a8f98;">{_html_escape(tr("util.meal.status.empty"))}</p>'
    name = meal.meal_name or tr("util.meal.default_meal_name")
    return (
        f'<h3 style="color:{C.UTIL_MAIN};margin-bottom:2px;">{_html_escape(name)} {cal_html}</h3>'
        f'{body}'
        f'<p style="color:#8a8f98;{_fs(10, width_px)}">'
        f'{_small(_html_escape(tr("util.meal.allergy_note")), width_px)}</p>'
    )


# =============================================================================
class MealApp(MiniApp):
    id = "meal"
    icon = "meal"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = MealWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()


# =============================================================================
TRANSLATIONS = {
    "util.meal.card.nav": {"ko": "날짜 선택", "en": "Date", "ja": "日付選択"},
    "util.meal.title": {
        "ko": "오늘의 급식", "en": "School Lunch", "ja": "今日の給食"},
    "util.meal.desc": {
        "ko": "나이스 개방포털에서 날짜별·주간 중식 정보를 받아옵니다(인터넷 연결 필요).",
        "en": "Fetches the daily or weekly lunch menu from the NEIS open data portal (needs internet).",
        "ja": "NEIS開放ポータルから日付別・週別の給食（昼食）情報を取得します（インターネット接続が必要）。"},

    "util.meal.btn.daily": {"ko": "일별", "en": "Daily", "ja": "日別"},
    "util.meal.btn.weekly": {"ko": "주간", "en": "Weekly", "ja": "週別"},
    "util.meal.btn.today": {"ko": "오늘", "en": "Today", "ja": "今日"},
    "util.meal.btn.print": {"ko": "인쇄", "en": "Print", "ja": "印刷"},
    "util.meal.btn.print.tip": {
        "ko": "지금 보이는 급식 내용을 인쇄합니다.",
        "en": "Prints what's currently shown.",
        "ja": "現在表示されている内容を印刷します。"},
    "util.meal.print.dialog_title": {
        "ko": "급식 인쇄", "en": "Print Lunch Menu", "ja": "給食を印刷"},
    "util.meal.default_meal_name": {"ko": "중식", "en": "Lunch", "ja": "昼食"},
    "util.meal.allergy_note": {
        "ko": "요리명 뒤 숫자는 알레르기 유발 식재료 번호입니다. 마우스로 드래그하면 내용을 선택해 복사할 수 있습니다.",
        "en": "Numbers after a dish name indicate potential allergens. Drag to select and copy the text.",
        "ja": "料理名の後の数字はアレルギー誘発食材の番号です。ドラッグで選択してコピーできます。"},

    "util.meal.status.need_key": {
        "ko": "위 '학교 설정'을 열어 나이스 인증키를 먼저 입력해 주세요.",
        "en": "Open 'School settings' above and enter your NEIS API key first.",
        "ja": "上の「学校の設定」を開いてNEIS認証キーを先に入力してください。"},
    "util.meal.status.loading": {
        "ko": "불러오는 중…", "en": "Loading…", "ja": "読み込み中…"},
    "util.meal.status.empty": {
        "ko": "이 날짜엔 급식 정보가 없습니다(주말·방학 등).",
        "en": "No meal information for this date (weekend, break, etc.).",
        "ja": "この日は給食情報がありません（週末・休み等）。"},
    "util.meal.status.empty_short": {
        "ko": "정보 없음", "en": "No data", "ja": "情報なし"},
    "util.meal.status.error": {
        "ko": "정보를 받아오지 못했습니다.\n서버 응답: {a0}",
        "en": "Couldn't fetch the information.\nServer message: {a0}",
        "ja": "情報を取得できませんでした。\nサーバー応答: {a0}"},
    "util.meal.status.unknown_error": {
        "ko": "알 수 없는 오류입니다. 인증키와 학교 코드를 확인해 주세요.",
        "en": "Unknown error. Please check your API key and school codes.",
        "ja": "不明なエラーです。認証キーと学校コードを確認してください。"},
    "util.meal.status.network_error": {
        "ko": "인터넷에 연결할 수 없습니다.\n({a0})",
        "en": "Couldn't reach the internet.\n({a0})",
        "ja": "インターネットに接続できません。\n({a0})"},
    "util.meal.status.done": {
        "ko": "{a0} {a1}개 요리", "en": "{a0}: {a1} dishes", "ja": "{a0} {a1}品"},
    "util.meal.status.weekly_done": {
        "ko": "이번 주 요리 {a0}개", "en": "{a0} dishes this week", "ja": "今週の料理{a0}品"},
    "util.meal.weekly.title": {
        "ko": "주간 급식표 ({a0} ~ {a1})", "en": "Weekly Menu ({a0} ~ {a1})",
        "ja": "週間給食表 ({a0} ~ {a1})"},
    "util.meal.monthly.title": {
        "ko": "{a0}년 {a1}월 급식표", "en": "Monthly Menu — {a0}-{a1:02d}",
        "ja": "{a0}年{a1}月 給食表"},
    "util.meal.btn.monthly": {"ko": "월별", "en": "Monthly", "ja": "月別"},
    "util.meal.status.monthly_done": {
        "ko": "이번 달 요리 {a0}개", "en": "{a0} dishes this month", "ja": "今月の料理{a0}品"},
    "util.meal.log.monthly_done": {
        "ko": "[급식] {a0} 월간 정보를 불러왔습니다",
        "en": "[Meal] Loaded monthly info for {a0}",
        "ja": "[給食] {a0}の月間情報を読み込みました"},

    "util.meal.log.done": {
        "ko": "[급식] {a0} {a1} 정보를 불러왔습니다",
        "en": "[Meal] Loaded {a1} for {a0}",
        "ja": "[給食] {a0} {a1}情報を読み込みました"},
    "util.meal.log.weekly_done": {
        "ko": "[급식] {a0}~{a1} 주간 정보를 불러왔습니다",
        "en": "[Meal] Loaded weekly info for {a0}~{a1}",
        "ja": "[給食] {a0}〜{a1}の週間情報を読み込みました"},
    "util.meal.log.empty": {
        "ko": "[급식] {a0}에는 정보가 없습니다",
        "en": "[Meal] No data for {a0}",
        "ja": "[給食] {a0}には情報がありません"},
    "util.meal.log.error": {
        "ko": "[급식] 오류: {a0}", "en": "[Meal] Error: {a0}", "ja": "[給食] エラー: {a0}"},
    "util.meal.log.network_error": {
        "ko": "[급식] 네트워크 오류: {a0}",
        "en": "[Meal] Network error: {a0}",
        "ja": "[給食] ネットワークエラー: {a0}"},
    "util.meal.log.printed": {
        "ko": "[급식] 인쇄했습니다", "en": "[Meal] Printed", "ja": "[給食] 印刷しました"},

    "util.meal.weekday.mon": {"ko": "월요일", "en": "Monday", "ja": "月曜日"},
    "util.meal.weekday.tue": {"ko": "화요일", "en": "Tuesday", "ja": "火曜日"},
    "util.meal.weekday.wed": {"ko": "수요일", "en": "Wednesday", "ja": "水曜日"},
    "util.meal.weekday.thu": {"ko": "목요일", "en": "Thursday", "ja": "木曜日"},
    "util.meal.weekday.fri": {"ko": "금요일", "en": "Friday", "ja": "金曜日"},
    "util.meal.weekday.sat": {"ko": "토요일", "en": "Saturday", "ja": "土曜日"},
    "util.meal.weekday.sun": {"ko": "일요일", "en": "Sunday", "ja": "日曜日"},

    "util.meal.wd.mon": {"ko": "월", "en": "Mon", "ja": "月"},
    "util.meal.wd.tue": {"ko": "화", "en": "Tue", "ja": "火"},
    "util.meal.wd.wed": {"ko": "수", "en": "Wed", "ja": "水"},
    "util.meal.wd.thu": {"ko": "목", "en": "Thu", "ja": "木"},
    "util.meal.wd.fri": {"ko": "금", "en": "Fri", "ja": "金"},
    "util.meal.wd.sat": {"ko": "토", "en": "Sat", "ja": "土"},
    "util.meal.wd.sun": {"ko": "일", "en": "Sun", "ja": "日"},
}
MealApp.tr_table = {**N.TRANSLATIONS, **TRANSLATIONS}

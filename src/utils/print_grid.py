# -*- coding: utf-8 -*-
"""
FolderKit++ — 여러 미니앱(오늘의 급식, 학교 일정)이 공통으로 쓰는
"달력/표 형태를 프린터에 직접 그리기" 도우미.

## 왜 HTML 인쇄를 그만뒀나

표를 HTML(`<table>`)로 만들어 `QTextDocument.print_()`로 인쇄하는 방식을
두 번 고쳤지만(HTML4 width 속성으로 바꾸기, pt 단위로 바꾸기), 실제
프린터에서는 여전히 문제가 있었다 — 실측해 보니 `table-layout:fixed`와
칸별 `width` 속성을 함께 줘도, 내용이 비어 있거나 짧은 칸이 있으면 표
전체가 지정한 폭보다 좁게 자동으로 줄어들고, 그 줄어든 표가 페이지
안에서 한쪽으로 치우쳐 배치된다(실제 프린터에서는 왼쪽 23mm, 오른쪽
57mm처럼 비대칭으로 남는 걸 확인). 즉 Qt의 리치 텍스트 엔진은 `<table>`
치수를 우리가 지정한 그대로 믿을 수 없다.

그래서 표를 HTML로 만들지 않고, **이 모듈이 QPainter로 칸 하나하나의
위치·크기를 직접 계산해서 그린다.** 여백도 칸 폭도 우리가 정한 값
그대로 나오고, 셀이 페이지 경계에서 잘리는 것도 그리기 전에 남은
공간을 확인해서 안 맞으면 새 페이지로 넘기는 방식으로 원천적으로
막는다.

## 좌표는 왜 전부 "장치 픽셀"로 계산하나

`QPainter(printer)`로 직접 그리면 좌표가 pt(포인트)가 아니라 **프린터의
실제 장치 픽셀**(HighResolution 모드에서는 보통 1000dpi가 넘는다)로
해석된다 — pt 단위 좌표를 그냥 넘기면 종이 왼쪽 위 아주 작은 영역에만
그려진다(우리가 겪은 원래 버그와 같은 증상이 QPainter 레벨에서도
재현됨). `painter.scale()`로 보정하는 방법도 시도했지만, 그 상태에서
`drawText()`를 쓰면 폰트 힌팅이 깨져 글자가 이상한 도형처럼 보이는
문제가 있었다(직접 렌더링해서 확인함). 그래서 스케일 변환을 쓰지 않고,
이 모듈에 들어오는 모든 pt 값(여백·글자 크기 등)을 **함수 맨 앞에서
한 번에 장치 픽셀로 환산**해 그 이후로는 순수하게 픽셀 좌표만 다룬다.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QFont, QFontMetrics
from PySide6.QtPrintSupport import QPrinter


class GridCell:
    """표의 칸 하나. lines는 (문구, 글자색, 굵게 여부, 포인트 크기)
    튜플의 목록 — 위에서부터 한 줄씩 그린다. bg는 칸 전체 배경색
    (QColor 또는 None)."""

    __slots__ = ("lines", "bg", "faded")

    def __init__(self, lines, bg=None, faded=False):
        self.lines = lines
        self.bg = bg
        self.faded = faded   # 다른 달에 걸치는 칸처럼 옅게 표시할지


def _font(pixel_size, bold=False):
    font = QFont()
    font.setFamily("Arial")
    font.setPixelSize(max(1, round(pixel_size)))
    font.setBold(bold)
    return font


def _wrapped_height_px(text, font, avail_w_px):
    """[버그 수정] 긴 문구(예: 일정 제목 + 상세 내용)가 칸 폭을 넘기면
    이전에는 옆 칸까지 침범하거나 잘려서 안 보였다. 실제로 몇 줄로
    접힐지를 미리 계산해서 칸 높이에 반영하고, 그릴 때도 같은 폭으로
    줄바꿈되게 한다."""
    fm = QFontMetrics(font)
    rect = fm.boundingRect(0, 0, max(1, int(avail_w_px)), 100000,
                           Qt.TextWordWrap, text)
    return rect.height()


def measure_row_height_px(cells, pad_pt, dpi_scale, col_w, min_height_px=0.0):
    """이 행에서 가장 높은 칸의 높이(패딩 포함, 픽셀)를 구한다. 줄바꿈이
    생기는 긴 문구도 실제로 몇 줄이 될지 계산해서 반영한다."""
    pad_px = pad_pt * dpi_scale
    avail_w = col_w - pad_px * 2
    tallest = min_height_px
    for cell in cells:
        h = pad_px * 2
        for text, _color, bold, size in cell.lines:
            h += _wrapped_height_px(text, _font(size * dpi_scale, bold), avail_w)
        tallest = max(tallest, h)
    return tallest


def _draw_header_row(painter, x0, y, col_w, labels, header_pt, dpi_scale, border_color, bg):
    """요일/열 머리글 행을 그리고, 그 높이(픽셀)를 돌려준다."""
    font = _font(header_pt * dpi_scale, bold=True)
    h = _wrapped_height_px("가", font, col_w) + 8 * dpi_scale
    painter.setFont(font)
    for i, label in enumerate(labels):
        rect = QRectF(x0 + i * col_w, y, col_w, h)
        painter.fillRect(rect, QColor(bg))
        painter.setPen(QPen(QColor(border_color), 1))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor("#444444")))
        painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, label)
    return h


def _draw_row(painter, x0, y, col_w, row_h, cells, pad_pt, dpi_scale, border_color):
    """칸 목록 한 행을 (x0, y)부터 그린다(모든 좌표는 이미 픽셀). 긴
    문구는 칸 폭에 맞춰 자동으로 줄바꿈된다."""
    pad_px = pad_pt * dpi_scale
    avail_w = col_w - pad_px * 2
    for i, cell in enumerate(cells):
        rect = QRectF(x0 + i * col_w, y, col_w, row_h)
        if cell.bg is not None:
            painter.fillRect(rect, cell.bg)
        painter.setPen(QPen(QColor(border_color), 1))
        painter.drawRect(rect)

        ty = y + pad_px
        for text, color, bold, size in cell.lines:
            font = _font(size * dpi_scale, bold=bold)
            painter.setFont(font)
            c = QColor("#c6c9ce") if (cell.faded and color in ("#444444", "#444")) else QColor(color)
            painter.setPen(QPen(c))
            line_h = _wrapped_height_px(text, font, avail_w)
            text_rect = QRectF(x0 + i * col_w + pad_px, ty, avail_w, line_h)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.TextWordWrap, text)
            ty += line_h


def print_calendar(printer, painter, title, title_color, header_labels, week_rows,
                   margin_pt, border_color="#d0d3d8", pad_pt=5, header_pt=10.5,
                   header_bg="#f3f0f2", footer_text=None, footer_pt=8):
    """표 전체(제목 + 요일 머리글 + 여러 주)를 인쇄한다. 한 주(week_rows의
    한 원소 = GridCell 리스트)가 남은 페이지 공간보다 높으면, 그 주를
    그리기 **전에** 새 페이지로 넘겨서 중간에 잘리지 않게 한다. 새
    페이지에서는 요일 머리글을 다시 그려 어느 페이지를 봐도 요일을 바로
    알 수 있게 한다.

    호출하는 쪽이 QPainter를 열고(printer에 begin) 이 함수 호출이 끝난
    뒤 end()해야 한다(여러 표를 한 인쇄 작업에 이어 그릴 수 있도록).
    margin_pt 등 모든 크기 인자는 **포인트(pt)** 단위로 받고, 이 함수가
    내부에서 장치 픽셀로 환산해 그린다."""
    dpi_scale = printer.resolution() / 72.0
    margin_px = margin_pt * dpi_scale

    page_rect_pt = printer.paperRect(QPrinter.Point)
    x0, y0 = margin_px, margin_px
    usable_w = page_rect_pt.width() * dpi_scale - margin_px * 2
    usable_bottom = page_rect_pt.height() * dpi_scale - margin_px
    n_cols = len(header_labels)
    col_w = usable_w / n_cols

    y = y0
    title_h = 0
    if title:
        title_font = _font(15 * dpi_scale, bold=True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(title_color)))
        title_h = _wrapped_height_px(title, title_font, usable_w) * 1.05
        painter.drawText(QRectF(x0, y, usable_w, title_h), Qt.AlignLeft | Qt.AlignVCenter, title)
        y += title_h + 4 * dpi_scale

    header_h = _draw_header_row(painter, x0, y, col_w, header_labels, header_pt, dpi_scale,
                                border_color, header_bg)
    y += header_h

    for cells in week_rows:
        row_h = measure_row_height_px(cells, pad_pt, dpi_scale, col_w)
        if y + row_h > usable_bottom and y > y0 + title_h + header_h:
            printer.newPage()
            y = y0
            header_h = _draw_header_row(painter, x0, y, col_w, header_labels, header_pt, dpi_scale,
                                        border_color, header_bg)
            y += header_h
        _draw_row(painter, x0, y, col_w, row_h, cells, pad_pt, dpi_scale, border_color)
        y += row_h

    if footer_text:
        footer_font = _font(footer_pt * dpi_scale)
        painter.setFont(footer_font)
        painter.setPen(QPen(QColor("#8a8f98")))
        footer_h = _wrapped_height_px(footer_text, footer_font, usable_w)
        painter.drawText(QRectF(x0, y + 6 * dpi_scale, usable_w, footer_h), Qt.AlignLeft, footer_text)

# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 #3: 함수 그래프 [v03]

f(x) 형태의 식을 입력하면 즉시 곡선을 그린다. 여러 함수를 동시에 그려
비교할 수 있고, 마우스 휠로 확대/축소, 드래그로 이동한다.

## 왜 matplotlib을 쓰지 않았나
FolderKit++는 PyInstaller로 배포되는 가벼운 도구다. matplotlib(+numpy)를
끌어들이면 배포 파일이 수십 MB 늘고 빌드 시간도 크게 늘어난다. 카르노맵
아이콘을 QPainter로 직접 그린 것과 같은 이유로, 여기서도 좌표축·격자·곡선을
전부 QPainter로 직접 그린다. 수식 계산도 계산기와 같은 안전한 평가기
(expr.py, ast 기반)를 그대로 재사용한다 — eval()을 쓰지 않으므로 위험한
코드가 껴 있어도 실행되지 않는다.

## 화면 갱신 전략
드래그로 화면을 움직이는 동안에는 표본 수를 줄여(《_DRAG_SAMPLES》) 매
프레임 다시 계산해도 버벅이지 않게 하고, 드래그가 끝나는 순간 원래 해상도로
한 번 더 계산해 선명한 그림으로 마무리한다(그래프 계산기 앱들이 흔히 쓰는
방식과 같다).
"""
import json

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QFont, QPainter, QPen, QColor, QPolygonF, QGuiApplication,
    QPainterPath, QCursor, QPixmap
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QScrollArea, QFrame, QSizePolicy, QFileDialog, QMenu
)

from ..i18n import tr
from ..styles import C, BTN_DESTRUCTIVE_BG
from . import ui_kit as UK
from .base import MiniApp
from . import graph_solve as G

PALETTE = ["#1e88e5", "#43a047", "#fb8c00", "#8e24aa", "#00897b", "#3949ab"]
MAX_FUNCTIONS = 6

# [v11] x축 추적선 색 — 드래그 중(보라색)과 고정된 뒤(회색 점선)를 구분한다.
# PALETTE의 보라(#8e24aa)와 살짝 다른 톤을 써서, 그 색을 쓰는 함수 곡선과도
# 눈으로 구별된다.
_TRACE_PURPLE = "#9c27b0"
_TRACE_GRAY = "#9aa0a8"
_PIN_RED = "#d32f2f"
_TRACE_HIT_TOL = 8.0   # 클릭이 축/점에 "닿았다"고 볼 픽셀 반경
DEFAULT_XMIN, DEFAULT_XMAX = -10.0, 10.0

_POINT_CURSOR = None   # [v34] 그래프 위를 지날 때 쓰는 커스텀 커서(지연 생성, 캐시)


def _point_cursor():
    """작은 흰 속 + 보라 테두리 원 모양 커서 — 고정점 표시와 같은 스타일이라
    '여기를 클릭하면 이 표시가 남는다'는 게 바로 연상된다."""
    global _POINT_CURSOR
    if _POINT_CURSOR is None:
        size = 14
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        pt = QPainter(pm)
        pt.setRenderHint(QPainter.Antialiasing, True)
        pt.setPen(QPen(QColor(_TRACE_PURPLE), 1.6))
        pt.setBrush(QColor("#ffffff"))
        pt.drawEllipse(QRectF(1.4, 1.4, size - 2.8, size - 2.8))
        pt.end()
        _POINT_CURSOR = QCursor(pm, size // 2, size // 2)
    return _POINT_CURSOR

_FULL_SAMPLES_MIN = 240
_FULL_SAMPLES_MAX = 1200
_DRAG_SAMPLES = 220   # 드래그 중에는 이만큼만 — 매끄러운 반응이 먼저다

_SET_FUNCTIONS = "util.graph.functions"
_SET_VIEW = "util.graph.view"
_SET_ANGLE = "util.graph.angle"


# =============================================================================
class _FunctionRow(QWidget):
    """함수 하나 = 색 스와치 + 수식 입력창 + 표시 여부 체크박스 + 삭제 버튼."""

    changed = Signal()
    removeRequested = Signal(object)

    def __init__(self, color, text="", visible=True, parent=None):
        super().__init__(parent)
        self.color = color

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.chk_visible = QCheckBox()
        self.chk_visible.setChecked(visible)
        self.chk_visible.setToolTip(tr("util.graph.row.visible.tip"))
        self.chk_visible.stateChanged.connect(lambda _=None: self.changed.emit())
        lay.addWidget(self.chk_visible)

        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(22, 22)
        self.btn_color.setCursor(Qt.PointingHandCursor)
        self.btn_color.setToolTip(tr("util.graph.row.color.tip"))
        self.btn_color.clicked.connect(self._cycle_color)
        self._apply_color_style()
        lay.addWidget(self.btn_color)

        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText(tr("util.graph.row.placeholder"))
        self.edit.setFont(QFont("Consolas", 12))
        self.edit.textChanged.connect(lambda _=None: self.changed.emit())
        lay.addWidget(self.edit, 1)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color:{BTN_DESTRUCTIVE_BG};font-size:10px;background:transparent;")
        self.lbl_error.setFixedWidth(0)   # 오류 있을 때만 폭을 늘려 보여준다
        lay.addWidget(self.lbl_error)

        self.btn_remove = QPushButton("×")
        self.btn_remove.setFixedSize(22, 22)
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.setToolTip(tr("util.graph.row.remove.tip"))
        self.btn_remove.setStyleSheet(UK.tool_button().styleSheet())
        self.btn_remove.clicked.connect(lambda: self.removeRequested.emit(self))
        lay.addWidget(self.btn_remove)

    def _apply_color_style(self):
        self.btn_color.setStyleSheet(
            f"QPushButton{{background-color:{self.color};border:1px solid #00000022;"
            "border-radius:4px;}")

    def _cycle_color(self):
        idx = PALETTE.index(self.color) if self.color in PALETTE else -1
        self.color = PALETTE[(idx + 1) % len(PALETTE)]
        self._apply_color_style()
        self.changed.emit()

    def set_error(self, text):
        if text:
            self.lbl_error.setText(text)
            self.lbl_error.setFixedWidth(160)
            self.edit.setStyleSheet(f"border:1px solid {BTN_DESTRUCTIVE_BG};")
        else:
            self.lbl_error.setText("")
            self.lbl_error.setFixedWidth(0)
            self.edit.setStyleSheet("")

    def to_dict(self):
        return {"text": self.edit.text(), "color": self.color,
                "visible": self.chk_visible.isChecked()}


# =============================================================================
class _GraphCanvas(QWidget):
    """좌표축·격자·곡선을 직접 그리는 캔버스. 표본 계산부터 화면 좌표 변환,
    마우스 확대/축소·이동까지 전부 이 클래스 하나가 맡는다."""

    rangeChanged = Signal(float, float, float, float)   # xmin,xmax,ymin,ymax
    errorsChanged = Signal(object)                        # {row_id: err_text_or_None}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.functions = []      # [{"id":..., "text":..., "color":..., "visible":bool}]
        self.angle_mode = "rad"
        self.auto_y = True
        self.xmin, self.xmax = DEFAULT_XMIN, DEFAULT_XMAX
        self.ymin, self.ymax = -10.0, 10.0

        self._segments = {}      # id -> list[segment]; segment = [(x,y),...]
        self._intercepts = {}    # [v10] id -> {"x": [...], "y": value_or_None}
        self.show_intercepts = True

        # [v12] x축 추적(드래그로 값 확인) + 여러 점에 각자 접선/법선을
        # 동시에 그릴 수 있는 "고정된 점" 목록. 예전에는 버튼으로 접선/
        # 수직선 "모드"를 켜고 곡선 위 점 하나만 대상으로 삼았는데,
        # 이제는 곡선 위 점을 클릭하면 그 점이 목록에 추가되고(원이
        # 계속 남아 있음), 그 점을 오른쪽 클릭하면 뜨는 메뉴로 접선·
        # 법선을 각각 그리거나 지울 수 있다 — 여러 점에 동시에 그릴 수
        # 있고, 새 점을 골라도 이전 점·직선이 사라지지 않는다.
        self._trace_x = None          # 추적/고정된 x값(없으면 None)
        self._trace_dragging = False  # 드래그 중(보라색)인지 고정(회색 점선)인지
        self._trace_is_hover = False  # [v34] 지금 표시된 추적선이 클릭/드래그로 만든 게 아니라 단순 호버 미리보기인지
        self._pinned_points = []      # [{"x":.., "fid":.., "tangent":bool, "normal":bool}, ...]
        self._trace_input = None      # x값을 직접 입력하는 작은 입력창(지연 생성)
        self._editing_pin = None      # [v45.2] 지금 _trace_input이 편집 중인 대상이
        # 추적선(None)이 아니라 특정 고정점이면 그 dict를 가리킨다 — 입력을
        # 확정하면 trace_x 대신 이 점의 x를 바꾼다(그 자리로 점이 이동한다).
        self._errors = {}        # id -> i18n key or None
        self._dragging = False
        self._drag_last_px = None

        self._margin_left = 48
        self._margin_bottom = 26
        self._margin_top = 12
        self._margin_right = 12

    # ------------------------------------------------------------ 바깥 API
    def set_functions(self, functions):
        self.functions = functions
        self._resample()

    def set_angle_mode(self, mode):
        self.angle_mode = mode
        self._resample()

    def set_auto_y(self, auto):
        self.auto_y = auto
        self._resample()

    def set_show_intercepts(self, show):
        self.show_intercepts = show
        self._resegment()

    def _pinned_point_y(self, pt):
        """이 고정점의 함수·x에서 현재 y값을 계산한다(함수식이 그 뒤
        바뀌었을 수도 있어 매번 다시 계산한다). 함수가 없어졌거나
        그 x에서 정의되지 않으면 None."""
        f = next((f for f in self.functions if f["id"] == pt["fid"] and f.get("visible", True)), None)
        if f is None:
            return None
        return G.value_at(f["text"], pt["x"], self.angle_mode)

    def _pin_point(self, x, fid):
        """곡선 위 점을 클릭해서 새 고정점을 만든다(이미 같은 자리가
        있으면 다시 안 만든다)."""
        for pt in self._pinned_points:
            if pt["fid"] == fid and abs(pt["x"] - x) < 1e-9:
                return
        self._pinned_points.append({"x": x, "fid": fid, "tangent": False, "normal": False})
        self.update()

    def set_x_range(self, xmin, xmax):
        if xmax <= xmin:
            return
        span = G.clamp_span(xmax - xmin)
        self.xmin, self.xmax = xmin, xmin + span
        self._resample()

    def set_y_range(self, ymin, ymax):
        if ymax <= ymin:
            return
        self.auto_y = False
        self.ymin, self.ymax = ymin, ymin + G.clamp_span(ymax - ymin)
        # [v45.2] 여기서도 X 기준 배율에 맞춰 실제로 보이는 범위로
        # 다시 맞춘다 — 그러지 않으면 Y를 수동 입력했을 때 등각이
        # 깨져 X 범위가 다시 화면을 벗어나거나 안 채울 수 있다.
        self._sync_y_to_plot_height()
        self._resegment()

    def reset_view(self):
        self.xmin, self.xmax = DEFAULT_XMIN, DEFAULT_XMAX
        self.auto_y = True
        self._resample()

    # ------------------------------------------------------------ 계산
    def _plot_rect(self):
        r = self.rect()
        return QRectF(r.left() + self._margin_left, r.top() + self._margin_top,
                     max(1, r.width() - self._margin_left - self._margin_right),
                     max(1, r.height() - self._margin_top - self._margin_bottom))

    def _sample_count(self, dragging=False):
        if dragging:
            return _DRAG_SAMPLES
        width = max(int(self._plot_rect().width()), 1)
        return max(_FULL_SAMPLES_MIN, min(_FULL_SAMPLES_MAX, width))

    def _resample(self, dragging=False, freeze_auto_y=False):
        n = self._sample_count(dragging)
        raw = {}
        errors = {}
        for f in self.functions:
            if not f.get("visible", True):
                continue
            res = G.sample(f["text"], self.xmin, self.xmax, n, self.angle_mode)
            raw[f["id"]] = res
            errors[f["id"]] = None if res.error is None else tr(res.error, **res.error_params)
        self._raw = raw
        self._errors = errors
        self.errorsChanged.emit(dict(errors))
        self._update_y_and_segments(freeze_auto_y=freeze_auto_y)

    def _update_y_and_segments(self, freeze_auto_y=False):
        """[버그 수정] freeze_auto_y=True면 "Y 자동"이 켜져 있어도 Y
        범위를 다시 계산하지 않는다 — 마우스를 누른 채 화면을 끄는(패닝)
        도중에 매 순간 Y 범위가 새로 계산되면, 확대·축소가 패닝과 함께
        일어나는 것처럼 보이는 문제가 있었다(실제로 이런 제보를 받았다).
        이제 드래그하는 동안은 Y 범위를 그대로 두고(순수 패닝), 손을
        놓는 순간에만 최종 X 범위에 맞춰 한 번 다시 계산한다."""
        if self.auto_y and not freeze_auto_y:
            all_vals = [y for res in self._raw.values() for y in res.ys if y is not None]
            self.ymin, self.ymax = G.robust_y_range(all_vals)
        self._sync_y_to_plot_height()
        self._resegment()

    def _sync_y_to_plot_height(self):
        """[v45.2 버그 수정] "X 입력 범위가 화면에 보이는 X축 범위와
        다르다"는 지적의 원인 — X·Y 배율을 등각으로 맞추면서, 그동안은
        "더 좁은 쪽"(보통 Y)을 기준으로 삼았다. 그러면 X 쪽 배율이
        Y보다 넉넉한 경우, 화면 가로 폭의 일부만 써서 X 범위(xmin~xmax)
        를 그리고 양옆이 비어, 정작 X 입력란에 적은 값과 실제로 꽉 차
        보이는 X 범위가 어긋났다. _scale()이 이제 "보통은 X, 필요하면
        Y" 기준으로 배율을 고르므로, 여기서는 그 배율로 plot 높이
        전체가 실제로 보여주는 Y 범위를 역산해 self.ymin/ymax에 반영
        하기만 한다 — **xmin/xmax는 절대 안 건드린다**(X를 함께
        조정하면 그 변화가 다음 샘플링에 영향을 줘 값이 끝없이 불어나는
        문제가 있었다). X가 기준으로 선택된 경우엔 Y가 화면에 꽉 차게
        넓어지고, Y가 기준으로 선택된 경우엔(함수 값이 크게 움직일 때)
        Y는 그대로이고 X 쪽이 화면 일부에만 그려지는, 등각 그래프의
        정상적인 트레이드오프로 돌아간다."""
        plot = self._plot_rect()
        s = self._scale(plot)
        if s <= 0:
            return
        visible_yspan = plot.height() / s
        cy = (self.ymin + self.ymax) / 2
        self.ymin = cy - visible_yspan / 2
        self.ymax = cy + visible_yspan / 2

    def _resegment(self):
        self._segments = {}
        self._intercepts = {}   # [v10] id -> {"x": [x1,x2,...], "y": value_or_None}
        for fid, res in self._raw.items():
            segs = G.build_segments(res.xs, res.ys, self.ymin, self.ymax)
            self._segments[fid] = segs
            if self.show_intercepts:
                f = next((f for f in self.functions if f["id"] == fid), None)
                x_roots = G.find_x_intercepts(segs)
                y_val = G.y_intercept(f["text"], self.angle_mode) if f else None
                self._intercepts[fid] = {"x": x_roots, "y": y_val}
        self.rangeChanged.emit(self.xmin, self.xmax, self.ymin, self.ymax)
        self.update()

    # ------------------------------------------------------------ 좌표 변환
    def _scale(self, plot):
        """[버그 수정] X·Y 배율을 **항상 똑같이** 맞춘다(등각). 예전엔
        X·Y를 각각 화면 폭·높이에 맞춰 독립적으로 늘렸는데, 이러면 두
        방향의 "1칸"이 화면에서 서로 다른 길이로 그려져서, 실제로는
        접선과 수직인 법선이 화면에서는 삐뚜름하게 보이는 문제가
        있었다(실제로 이런 제보를 받았다 — x범위가 8.5칸, y범위가
        1.5칸처럼 크게 차이 나는 경우일수록 더 두드러진다).

        [v45.2 버그 수정] 등각을 맞출 때 "더 좁은 쪽"(min)을 기준으로
        삼았더니, Y 쪽이 더 좁은 흔한 경우에 X 범위(xmin~xmax)가 화면
        가로 폭의 일부에만 작게 그려지고 양옆이 비어, X 입력란 값과
        실제로 화면에 보이는 X 범위가 어긋나는 문제가 있었다("함수가
        X축 전 범위에서 그려지지 않는다"는 지적). 이제 **항상 X를
        기준으로 고정**한다 — X 범위는 항상 화면 가로 폭을 꽉 채우고,
        Y 쪽의 실제 표시 범위는 이 배율에 맞춰 _sync_y_to_plot_height()
        가 역산한다(함수 값이 크게 움직이는 구간에서는 Y가 그만큼
        넓게 — 즉 세로로 멀리 뻗어 보이는 식으로 — 늘어난다. 보기엔
        납작해 보일 수 있지만, "X 범위를 지정한 대로 화면 전체에
        그린다"는 걸 우선한 정상적인 결과다). **xmin/xmax는 여기서
        절대 바꾸지 않는다**(Y만 따라가게 하고 X도 같이 움직이게
        했더니, 그 변화가 다음 샘플링에 다시 영향을 줘 값이 끝없이
        불어나는 버그가 있었다)."""
        xspan = max(1e-9, self.xmax - self.xmin)
        return plot.width() / xspan

    def _to_px(self, x, y, plot=None):
        plot = plot or self._plot_rect()
        s = self._scale(plot)
        cx = (self.xmin + self.xmax) / 2
        cy = (self.ymin + self.ymax) / 2
        ccx = plot.left() + plot.width() / 2
        ccy = plot.top() + plot.height() / 2
        return QPointF(ccx + (x - cx) * s, ccy - (y - cy) * s)

    def _to_data(self, px, py, plot=None):
        plot = plot or self._plot_rect()
        s = self._scale(plot)
        if s == 0:
            return (self.xmin, self.ymin)
        cx = (self.xmin + self.xmax) / 2
        cy = (self.ymin + self.ymax) / 2
        ccx = plot.left() + plot.width() / 2
        ccy = plot.top() + plot.height() / 2
        x = cx + (px - ccx) / s
        y = cy - (py - ccy) / s
        return (x, y)

    # ------------------------------------------------------- [v11] x축 추적
    def _axis_row_px(self, plot):
        """x축이 화면에 보이면 그 픽셀 y좌표, 안 보이면(0이 Y범위 밖이면)
        플롯 아래쪽 테두리를 대신 쓴다 — 그래야 축이 안 보이는 상태로
        확대/이동해 있어도 추적 기능을 계속 쓸 수 있다."""
        if self.ymin <= 0 <= self.ymax:
            return self._to_px(0, 0, plot).y()
        return plot.bottom()

    def _trace_values(self):
        """지금 고정/추적 중인 x에서, 보이는 함수마다 y값을 계산한다.
        정의되지 않는 함수는 결과에서 빠진다(점을 안 찍는다)."""
        if self._trace_x is None:
            return {}
        values = {}
        for f in self.functions:
            if not f.get("visible", True):
                continue
            y = G.value_at(f["text"], self._trace_x, self.angle_mode)
            if y is not None and self.ymin - 1e9 <= y <= self.ymax + 1e9:
                values[f["id"]] = y
        return values

    # ------------------------------------------------------------ 그리기
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        plot = self._plot_rect()

        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawRect(plot)

        self._draw_grid_and_ticks(p, plot)
        self._draw_axes(p, plot)
        self._draw_curves(p, plot)
        if self.show_intercepts:
            self._draw_intercepts(p, plot)
        if self._trace_x is not None:
            self._draw_trace(p, plot)
        self._draw_pinned_points(p, plot)
        self._draw_error_labels(p, plot)
        p.end()

    def _draw_grid_and_ticks(self, p, plot):
        """[버그 수정] 격자 무늬(칸 전체를 가로지르는 옅은 줄)를 없애고,
        축에 붙은 **짧은 눈금 표시**와 숫자만 남긴다."""
        p.setClipRect(plot)
        tick_pen = QPen(QColor("#9aa0a8"), 1)
        font = QFont("Arial", 8)
        p.setFont(font)

        x_axis_row = self._to_px(self.xmin, 0, plot).y() if self.ymin <= 0 <= self.ymax else plot.bottom()
        y_axis_col = self._to_px(0, self.ymin, plot).x() if self.xmin <= 0 <= self.xmax else plot.left()
        tick_len = 4

        for tx in G.nice_ticks(self.xmin, self.xmax):
            pt = self._to_px(tx, self.ymin, plot)
            p.setPen(tick_pen)
            p.drawLine(QPointF(pt.x(), x_axis_row - tick_len), QPointF(pt.x(), x_axis_row + tick_len))
        for ty in G.nice_ticks(self.ymin, self.ymax):
            pt = self._to_px(self.xmin, ty, plot)
            p.setPen(tick_pen)
            p.drawLine(QPointF(y_axis_col - tick_len, pt.y()), QPointF(y_axis_col + tick_len, pt.y()))
        p.setClipping(False)

        p.setPen(QPen(QColor("#6b7280")))
        for tx in G.nice_ticks(self.xmin, self.xmax):
            if abs(tx) < 1e-9:
                continue   # 원점의 "0"은 _draw_axes가 따로 표시한다(겹침 방지)
            pt = self._to_px(tx, self.ymin, plot)
            if plot.left() - 1 <= pt.x() <= plot.right() + 1:
                p.drawText(QRectF(pt.x() - 24, plot.bottom() + 5, 48, 16),
                          Qt.AlignHCenter | Qt.AlignTop, _fmt_tick(tx))
        for ty in G.nice_ticks(self.ymin, self.ymax):
            if abs(ty) < 1e-9:
                continue
            pt = self._to_px(self.xmin, ty, plot)
            if plot.top() - 1 <= pt.y() <= plot.bottom() + 1:
                p.drawText(QRectF(0, pt.y() - 8, plot.left() - 8, 16),
                          Qt.AlignRight | Qt.AlignVCenter, _fmt_tick(ty))

    def _draw_axes(self, p, plot):
        """[버그 수정] x/y축을 **완전히 같은 펜**으로, 이전보다 살짝 더
        두껍고 진하게 그린다. 두 축이 서로 다른 두께로 보이던 것은 축의
        픽셀 위치가 정수+0.5에 딱 맞지 않아 안티앨리어싱이 선을 옆 픽셀에
        살짝 걸쳐 그리면서 한쪽만 번져 보이던 것이었다 — 그래서 그리기
        직전에 좌표를 픽셀 격자에 딱 맞춰(0.5 단위) 스냅한다."""
        p.setClipRect(plot)
        axis_pen = QPen(QColor(C.AXIS_STRONG), 2.4)
        axis_pen.setCapStyle(Qt.FlatCap)
        p.setPen(axis_pen)
        x_axis_visible = self.xmin <= 0 <= self.xmax
        y_axis_visible = self.ymin <= 0 <= self.ymax

        if x_axis_visible:
            x0 = _snap(self._to_px(0, self.ymin, plot).x())
            p.drawLine(QPointF(x0, plot.top()), QPointF(x0, plot.bottom()))
            self._draw_arrowhead(p, QPointF(x0, plot.top()), "up")
            p.setPen(axis_pen)   # [버그 수정] 화살표가 펜을 NoPen으로 바꿔 버려서, 그 다음에
                                 # 그리는 x축(가로선)이 보이지 않던 실제 원인이었다 — 복원해야 한다.
        if y_axis_visible:
            y0 = _snap(self._to_px(self.xmin, 0, plot).y())
            p.drawLine(QPointF(plot.left(), y0), QPointF(plot.right(), y0))
            self._draw_arrowhead(p, QPointF(plot.right(), y0), "right")
        p.setClipping(False)

        if x_axis_visible and y_axis_visible:
            origin = self._to_px(0, 0, plot)
            p.setPen(QPen(QColor(C.AXIS_STRONG)))
            p.setBrush(QColor(C.AXIS_STRONG))
            p.drawEllipse(origin, 2.4, 2.4)
            font = QFont("Arial", 9)
            p.setFont(font)
            p.drawText(QRectF(origin.x() - 18, origin.y() + 4, 15, 14),
                      Qt.AlignRight | Qt.AlignTop, "O")

    def _draw_arrowhead(self, p, tip, direction):
        """축 끝(플롯 경계)에 작은 삼각형 화살표를 그린다. direction은
        "up"(y축 양의 방향, 위쪽) 또는 "right"(x축 양의 방향, 오른쪽)."""
        draw_arrowhead(p, tip, direction, C.AXIS_STRONG)

    def _draw_curves(self, p, plot):
        p.setClipRect(plot)
        for f in self.functions:
            if not f.get("visible", True):
                continue
            segs = self._segments.get(f["id"], [])
            pen = QPen(QColor(f["color"]), 2.2)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            for seg in segs:
                if len(seg) < 2:
                    if seg:
                        p.drawPoint(self._to_px(*seg[0], plot))
                    continue
                poly = QPolygonF([self._to_px(x, y, plot) for x, y in seg])
                p.drawPolyline(poly)
        p.setClipping(False)

    def _draw_intercepts(self, p, plot):
        """[v10] 함수마다 x절편(그 함수 색의 속이 빈 원)과 y절편(같은 색
        속이 찬 원)을 찍고, 옆에 좌표를 작게 적는다. 절편이 여러 개일
        수 있어 x절편은 전부, y절편은 함수당 하나만 찍는다."""
        p.setClipRect(plot)
        font = QFont("Arial", 8)
        p.setFont(font)
        fm = p.fontMetrics()
        for f in self.functions:
            if not f.get("visible", True):
                continue
            info = self._intercepts.get(f["id"])
            if not info:
                continue
            color = QColor(f["color"])

            for rx in info["x"]:
                if not (self.xmin <= rx <= self.xmax):
                    continue
                pt = self._to_px(rx, 0.0, plot)
                p.setPen(QPen(color, 1.4))
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(pt, 3.2, 3.2)
                # 점 위쪽을 기본 자리로 하되, 플롯 위쪽 경계에 걸리면
                # 아래로 뒤집는다(x축 눈금 숫자와는 안 겹치게 최소 간격 유지).
                label = f"({_fmt1(rx)}, 0)"
                w = fm.horizontalAdvance(label) + 6
                rect = self._label_rect_near(plot, pt, w, 14, "above")
                self._draw_label(p, rect, Qt.AlignCenter, label, color)

            yv = info["y"]
            if yv is not None and isinstance(yv, (int, float)) and self.ymin <= yv <= self.ymax \
                    and self.xmin <= 0 <= self.xmax:
                pt = self._to_px(0.0, yv, plot)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(pt, 3.2, 3.2)
                label = f"(0, {_fmt1(yv)})"
                w = fm.horizontalAdvance(label) + 6
                rect = self._label_rect_near(plot, pt, w, 14, "right")
                self._draw_label(p, rect, Qt.AlignLeft | Qt.AlignVCenter, label, color)
        p.setClipping(False)

    def _draw_label(self, p, rect, align, text, color):
        """글자 자체에 흰 테두리(스트로크)를 둘러 축·곡선과 겹쳐도 읽히게
        한다. 이전에는 글자 뒤에 반투명 흰 상자를 깔았는데, 그 상자가
        y=0 근처 등에서 그래프 선을 옅게 가려 보인다는 지적을 받아
        상자를 없앴다 — 다른 요소를 가리지 않으면서도 글자는 또렷하다."""
        draw_text_label(p, rect, align, text, color)

    def _label_rect_near(self, plot, pt, w, h, prefer):
        """pt(픽셀 좌표) 주변에 라벨 상자를 두되, 그래프 영역을 벗어나면
        반대쪽으로 뒤집는다. prefer는 'above'|'below'|'right'|'left' 중 하나."""
        gap = 6
        if prefer == "above":
            rect = QRectF(pt.x() - w / 2, pt.y() - gap - h, w, h)
            if rect.top() < plot.top():
                rect.moveTop(pt.y() + gap)
        elif prefer == "below":
            rect = QRectF(pt.x() - w / 2, pt.y() + gap, w, h)
            if rect.bottom() > plot.bottom():
                rect.moveBottom(pt.y() - gap)
        elif prefer == "left":
            rect = QRectF(pt.x() - gap - w, pt.y() - h / 2, w, h)
            if rect.left() < plot.left():
                rect.moveLeft(pt.x() + gap)
        else:  # "right"
            rect = QRectF(pt.x() + gap, pt.y() - h / 2, w, h)
            if rect.right() > plot.right():
                rect.moveRight(pt.x() - gap)
        if rect.top() < plot.top():
            rect.moveTop(plot.top())
        if rect.bottom() > plot.bottom():
            rect.moveBottom(plot.bottom())
        return rect

    def _draw_error_labels(self, p, plot):
        y = plot.top() + 4
        font = QFont("Arial", 9)
        p.setFont(font)
        for f in self.functions:
            err = self._errors.get(f["id"])
            if not err or not f.get("visible", True):
                continue
            p.setPen(QPen(QColor(f["color"])))
            text = f'{f["text"]}: {err}'
            p.drawText(QRectF(plot.left() + 6, y, plot.width() - 12, 16),
                      Qt.AlignLeft | Qt.AlignVCenter, text)
            y += 15

    def _draw_trace(self, p, plot):
        """[v11] x축 추적선 — 드래그 중이면 보라색, 손을 떼면 회색 점선으로
        고정된다. 각 함수와 만나는 지점에서 y축까지 수평선을 그어 그
        값을 표시한다. 접선/수직선 모드가 켜져 있고 대상 함수가 골라져
        있으면 그 점을 지나는 직선도 함께 그린다."""
        color = QColor(_TRACE_PURPLE) if self._trace_dragging else QColor(_TRACE_GRAY)
        pen = QPen(color, 1.6)
        if not self._trace_dragging:
            pen.setStyle(Qt.DashLine)

        p.setClipRect(plot)
        p.setPen(pen)
        x_px = self._to_px(self._trace_x, self.ymin, plot).x()
        p.drawLine(QPointF(x_px, plot.top()), QPointF(x_px, plot.bottom()))

        values = self._trace_values()
        y_axis_visible = self.xmin <= 0 <= self.xmax
        for f in self.functions:
            fid = f["id"]
            if fid not in values:
                continue
            y = values[fid]
            if not (self.ymin <= y <= self.ymax):
                continue
            pt = self._to_px(self._trace_x, y, plot)

            if y_axis_visible:
                y0_px = self._to_px(0.0, y, plot)
                p.setPen(pen)
                p.drawLine(pt, y0_px)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(y0_px, 3.0, 3.0)

            p.setPen(QPen(color, 1.3))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(pt, 3.8, 3.8)
        p.setClipping(False)

        # x축 위 손잡이 — 색깔 글자에 흰 테두리를 둘러 축 눈금과 겹쳐도
        # 읽히게 한다. 소수점 첫째 자리까지만.
        axis_y = self._axis_row_px(plot)
        label_x = _fmt1(self._trace_x)
        font = QFont("Arial", 9)
        p.setFont(font)
        fm = p.fontMetrics()
        bw = fm.horizontalAdvance(label_x) + 10
        box = QRectF(x_px - bw / 2, axis_y + 5, bw, 16)
        self._draw_label(p, box, Qt.AlignCenter, label_x, color)

        # y축 위 값 라벨 — [버그 수정] 전에는 항상 plot 왼쪽 바깥(기존
        # Y축 눈금 자리)에 적어서, X 범위가 좌우 대칭에 가까워 Y축이
        # 화면 한가운데 오면 라벨이 한참 떨어진 화면 맨 왼쪽에 작게
        # 찍혀 거의 안 보였다. 이제 추적선과 Y축이 만나는 지점 바로
        # 옆에 적는다(그 지점이 plot 왼쪽/오른쪽 절반 어디인지에 따라
        # 라벨을 반대쪽에 둬서 곡선과 되도록 안 겹치게 한다).
        if y_axis_visible:
            for f in self.functions:
                fid = f["id"]
                if fid not in values:
                    continue
                y = values[fid]
                if not (self.ymin <= y <= self.ymax):
                    continue
                y0_px = self._to_px(0.0, y, plot)
                label_y = _fmt1(y)
                w_lbl = fm.horizontalAdvance(label_y) + 8
                if y0_px.x() - plot.left() < plot.width() / 2:
                    y_rect = QRectF(y0_px.x() + 7, y0_px.y() - 7, w_lbl, 14)
                else:
                    y_rect = QRectF(y0_px.x() - 7 - w_lbl, y0_px.y() - 7, w_lbl, 14)
                self._draw_label(p, y_rect, Qt.AlignCenter, label_y, color)


    def _draw_pinned_points(self, p, plot):
        """[신규] 고정점 목록을 하나씩 그린다 — 접선·법선이 있는 점은
        빨간 원으로, 없는 점은 그 함수 색 테두리(흰 배경)로 그린다.
        여러 점이 각자 접선·법선을 동시에 가질 수 있고, 새 점을 찍어도
        예전 점·직선은 그대로 남는다.

        [v45.2 버그 수정] 발(수선)만 그리고 그 발이 가리키는 실제 좌표
        값(라벨)을 표시하지 않던 것, 그리고 그 라벨을 눌러 x값을 바꿔
        점을 옮기는 기능이 빠져 있던 것을 복구했다 — 추적선(_draw_trace)
        과 같은 라벨 그리기 패턴을 고정점에도 적용한다. 접선·법선이
        있으면 그 직선의 방정식도 구해 직선이 화면에서 가장 위쪽(y값이
        가장 큰 지점)에 걸리는 자리에 적어 둔다."""
        y_axis_visible = self.xmin <= 0 <= self.xmax
        axis_y_row = self._axis_row_px(plot)
        font = QFont("Arial", 9)
        for pt in self._pinned_points:
            f = next((f for f in self.functions if f["id"] == pt["fid"]), None)
            if f is None:
                continue
            y0 = self._pinned_point_y(pt)
            if y0 is None or not (self.ymin <= y0 <= self.ymax):
                continue
            has_line = pt["tangent"] or pt["normal"]
            mark_color = QColor(_PIN_RED) if has_line else QColor(f["color"])
            dot_px = self._to_px(pt["x"], y0, plot)

            p.setClipRect(plot)
            # 발선(x축·y축까지) — 추적선과 같은 스타일, 옅게.
            foot_pen = QPen(QColor(f["color"]), 1.0, Qt.DashLine)
            p.setPen(foot_pen)
            axis_y_px = self._to_px(pt["x"], 0, plot).y() if self.ymin <= 0 <= self.ymax else plot.bottom()
            p.drawLine(dot_px, QPointF(dot_px.x(), axis_y_px))
            if y_axis_visible:
                y0_px = self._to_px(0.0, y0, plot)
                p.drawLine(dot_px, y0_px)

            for mode, on in (("tangent", pt["tangent"]), ("normal", pt["normal"])):
                if not on:
                    continue
                slope = G.numeric_slope(f["text"], pt["x"], self.xmax - self.xmin, self.angle_mode)
                if mode == "normal":
                    slope = G.normal_slope(slope)
                line_pen = QPen(mark_color, 1.6)
                line_pen.setStyle(Qt.DotLine if mode == "tangent" else Qt.DashDotLine)
                p.setPen(line_pen)
                if slope is None:
                    p1 = self._to_px(pt["x"], self.ymin, plot)
                    p2 = self._to_px(pt["x"], self.ymax, plot)
                    data_p1 = (pt["x"], self.ymin)
                    data_p2 = (pt["x"], self.ymax)
                else:
                    y_at_xmin = y0 + slope * (self.xmin - pt["x"])
                    y_at_xmax = y0 + slope * (self.xmax - pt["x"])
                    p1 = self._to_px(self.xmin, y_at_xmin, plot)
                    p2 = self._to_px(self.xmax, y_at_xmax, plot)
                    data_p1 = (self.xmin, y_at_xmin)
                    data_p2 = (self.xmax, y_at_xmax)
                p.drawLine(p1, p2)
                self._draw_line_equation(p, plot, font, mark_color, slope, pt["x"], y0,
                                         data_p1, data_p2)

            p.setPen(QPen(mark_color, 1.6))
            p.setBrush(QColor("#ffffff") if not has_line else mark_color)
            p.drawEllipse(dot_px, 5.0, 5.0)
            p.setClipping(False)

            # [v45.2] 발(수선)의 좌표 라벨 — x축 위 손잡이(클릭하면 입력
            # 창이 열려 x를 바꿀 수 있다) + y축 옆 값.
            label_x = _fmt1(pt["x"])
            p.setFont(font)
            fm = p.fontMetrics()
            bw = fm.horizontalAdvance(label_x) + 10
            box = QRectF(dot_px.x() - bw / 2, axis_y_row + 5, bw, 16)
            self._draw_label(p, box, Qt.AlignCenter, label_x, mark_color)

            if y_axis_visible:
                y0_px = self._to_px(0.0, y0, plot)
                label_y = _fmt1(y0)
                # [버그 수정] 전에는 Y축이 화면 어디에 있든 항상 plot
                # 왼쪽 바깥(기존 Y축 눈금이 있는 자리)에 값을 적었다 —
                # X 범위를 좌우 대칭에 가깝게 잡으면(흔한 경우) Y축이
                # 화면 한가운데 오는데, 그러면 라벨이 Y축에서 한참 떨어진
                # 화면 맨 왼쪽에 작게 찍혀 있어 거의 눈에 띄지 않았다
                # ("표시가 안 된다"고 느껴질 정도로). 이제 Y축과 수선이
                # 만나는 바로 그 지점 옆에 적는다 — 그 지점이 plot
                # 왼쪽 절반에 있으면 라벨을 오른쪽에, 오른쪽 절반에
                # 있으면 왼쪽에 둬서 곡선과 되도록 안 겹치게 한다.
                w_lbl = fm.horizontalAdvance(label_y) + 8
                if y0_px.x() - plot.left() < plot.width() / 2:
                    y_rect = QRectF(y0_px.x() + 7, y0_px.y() - 7, w_lbl, 14)
                else:
                    y_rect = QRectF(y0_px.x() - 7 - w_lbl, y0_px.y() - 7, w_lbl, 14)
                self._draw_label(p, y_rect, Qt.AlignCenter, label_y, mark_color)

    def _line_equation_text(self, slope, px, py):
        """[v45.2] 점(px, py)을 지나고 기울기 slope인 직선의 방정식
        문자열. slope가 None이면 수직선(x = c)."""
        if slope is None:
            return f"x = {_fmt1(px)}"
        intercept = py - slope * px
        slope_s = _fmt1(slope)
        if intercept >= 0:
            return f"y = {slope_s}x + {_fmt1(intercept)}"
        return f"y = {slope_s}x - {_fmt1(-intercept)}"

    def _draw_line_equation(self, p, plot, font, color, slope, px, py, data_p1, data_p2):
        """[v45.2] 접선·법선의 방정식을, 그 직선이 화면(plot 영역) 안에서
        y값이 가장 큰(가장 위쪽) 지점 근처에 적는다.

        [버그 수정] 처음엔 "직선의 양 끝(xmin에서의 값, xmax에서의 값)
        중 더 큰 쪽"만 봤는데, 기울기가 가팔라서 그 두 끝이 **둘 다**
        Y범위를 벗어나는 경우(직선이 plot 영역을 위아래로 가로질러
        지나가는 경우) 후보가 하나도 안 남아 방정식이 통째로 안 보이는
        문제가 있었다. 이제 직선이 plot 사각형의 네 변(xmin·xmax·ymin·
        ymax)과 실제로 만나는 모든 점을 구해서, 그중 y가 가장 큰 점을
        고른다 — 직선이 화면을 가로지르기만 해도 항상 방정식을 찾는다."""
        eps = 1e-9
        candidates = []
        if slope is None:
            if self.xmin - eps <= px <= self.xmax + eps:
                candidates.append((px, self.ymax))
        else:
            intercept = py - slope * px
            for bx in (self.xmin, self.xmax):
                by = slope * bx + intercept
                if self.ymin - eps <= by <= self.ymax + eps:
                    candidates.append((bx, by))
            if abs(slope) > eps:
                for by in (self.ymin, self.ymax):
                    bx = (by - intercept) / slope
                    if self.xmin - eps <= bx <= self.xmax + eps:
                        candidates.append((bx, by))
        if not candidates:
            return
        anchor = max(candidates, key=lambda c: c[1])
        anchor_y = min(self.ymax, max(self.ymin, anchor[1]))
        anchor_px = self._to_px(anchor[0], anchor_y, plot)

        text = self._line_equation_text(slope, px, py)
        p.setFont(font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 8
        # 위쪽 끝에 붙이되 plot 위 경계를 넘지 않게, 살짝 안쪽으로.
        rect = QRectF(min(max(anchor_px.x() - w / 2, plot.left() + 2), plot.right() - w - 2),
                      max(anchor_px.y() - 18, plot.top() + 2), w, 15)
        self._draw_label(p, rect, Qt.AlignCenter, text, color)

    def _pinned_point_at(self, pos, plot):
        """화면 좌표 pos 근처에 있는 고정점을 찾는다(없으면 None)."""
        for pt in self._pinned_points:
            y = self._pinned_point_y(pt)
            if y is None or not (self.ymin <= y <= self.ymax):
                continue
            dot = self._to_px(pt["x"], y, plot)
            if _dist(pos, dot) <= _TRACE_HIT_TOL:
                return pt
        return None

    def _show_pin_context_menu(self, pt, global_pos):
        """고정점을 오른쪽 클릭하면 뜨는 메뉴 — 접선·법선을 각각 그리거나
        (이미 그려져 있으면) 지운다."""
        menu = QMenu(self)
        act_tan = menu.addAction(
            tr("util.graph.ctx.remove_tangent") if pt["tangent"] else tr("util.graph.ctx.add_tangent"))
        act_norm = menu.addAction(
            tr("util.graph.ctx.remove_normal") if pt["normal"] else tr("util.graph.ctx.add_normal"))
        menu.addSeparator()
        act_del = menu.addAction(tr("util.graph.ctx.remove_point"))
        chosen = menu.exec(global_pos)
        if chosen == act_tan:
            pt["tangent"] = not pt["tangent"]
        elif chosen == act_norm:
            pt["normal"] = not pt["normal"]
        elif chosen == act_del:
            self._pinned_points.remove(pt)
        self.update()

    def _draw_crosshair(self, p, plot):
        # [v34] 마우스를 그래프 위에 올리면 이제 곧바로 x축 추적선이
        # 따라오므로(아래 mouseMoveEvent), 별도의 십자선+좌표 팝업은
        # 정보가 겹쳐 없앴다.
        return

    # ------------------------------------------------------------ 상호작용
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resample()

    def wheelEvent(self, event):
        factor = 0.85 if event.angleDelta().y() > 0 else 1 / 0.85
        plot = self._plot_rect()
        pos = event.position() if hasattr(event, "position") else event.posF()
        data_x, data_y = self._to_data(pos.x(), pos.y(), plot)

        new_w = G.clamp_span((self.xmax - self.xmin) * factor)
        ratio_x = (data_x - self.xmin) / (self.xmax - self.xmin)
        self.xmin = data_x - ratio_x * new_w
        self.xmax = self.xmin + new_w

        if not self.auto_y:
            new_h = G.clamp_span((self.ymax - self.ymin) * factor)
            ratio_y = (data_y - self.ymin) / (self.ymax - self.ymin)
            self.ymin = data_y - ratio_y * new_h
            self.ymax = self.ymin + new_h

        self._resample()
        event.accept()

    def mousePressEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.posF()
        plot = self._plot_rect()

        if event.button() == Qt.RightButton:
            hit = self._pinned_point_at(pos, plot)
            if hit is not None:
                global_pos = self.mapToGlobal(pos.toPoint())
                self._show_pin_context_menu(hit, global_pos)
            return

        if event.button() != Qt.LeftButton:
            return

        axis_y = self._axis_row_px(plot)

        # 1) 고정된 추적점이 있을 때: 축 위 손잡이(숫자 입력) 또는 곡선 위
        #    점(새 고정점 만들기)을 먼저 확인한다 — 새 추적/이동보다 우선.
        #    [v45.2] 이 손잡이를 고정점 손잡이보다 먼저 확인해야 한다 —
        #    손을 뗄 때 자동으로 고정점이 하나 생기는 기존 동작 때문에
        #    추적선과 고정점 손잡이가 같은 자리에 겹치는 경우가 흔한데,
        #    그때는 "지금 편집 중인 추적선"이 우선이어야 자연스럽다.
        if self._trace_x is not None and not self._trace_dragging:
            handle_x = self._to_px(self._trace_x, 0, plot).x()
            if _dist(pos, QPointF(handle_x, axis_y + 13)) <= _TRACE_HIT_TOL + 6:
                self._open_trace_input(QPointF(handle_x, axis_y))
                return
            for fid, y in self._trace_values().items():
                dot = self._to_px(self._trace_x, y, plot)
                if _dist(pos, dot) <= _TRACE_HIT_TOL:
                    self._pin_point(self._trace_x, fid)
                    return

        # 1.5) [v45.2] 고정점들의 x축 손잡이(좌표 라벨) — 눌러서 숫자를
        #      바꾸면 그 점이 그 x로 이동한다. 추적선 손잡이와 겹치지
        #      않는 경우에만 여기까지 내려온다.
        for pt in self._pinned_points:
            handle_x = self._to_px(pt["x"], 0, plot).x()
            if _dist(pos, QPointF(handle_x, axis_y + 13)) <= _TRACE_HIT_TOL + 6:
                self._open_trace_input(QPointF(handle_x, axis_y), editing_pin=pt)
                return

        # 2) x축 근처를 누르면 새 추적을 시작한다.
        axis_y = self._axis_row_px(plot)
        if abs(pos.y() - axis_y) <= _TRACE_HIT_TOL and plot.left() <= pos.x() <= plot.right():
            self._hide_trace_input()
            self._trace_dragging = True
            self._trace_is_hover = False
            x, _y = self._to_data(pos.x(), pos.y(), plot)
            self._trace_x = max(self.xmin, min(self.xmax, x))
            self.update()
            return

        # 3) 그 외에는 기존과 같이 화면 이동(팬).
        self._dragging = True
        self._drag_last_px = (pos.x(), pos.y())
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.posF()
        plot = self._plot_rect()

        if self._trace_dragging:
            x, _y = self._to_data(pos.x(), pos.y(), plot)
            self._trace_x = max(self.xmin, min(self.xmax, x))
            self.update()
            return

        if self._dragging and self._drag_last_px is not None:
            last_x, last_y = self._drag_last_px
            dx_px = pos.x() - last_x
            dy_px = pos.y() - last_y
            s = self._scale(plot)
            if s:
                shift_x = dx_px / s
                self.xmin -= shift_x
                self.xmax -= shift_x
                if not self.auto_y:
                    shift_y = dy_px / s
                    self.ymin += shift_y
                    self.ymax += shift_y
            self._drag_last_px = (pos.x(), pos.y())
            self._resample(dragging=True, freeze_auto_y=True)
            self.update()
            return

        # [버그 수정] "그래프 영역 아무 데나"가 아니라 실제로 곡선에
        # 커서가 닿아 있을 때만 커스텀 포인터 + 추적선이 켜지게 한다.
        # 클릭·드래그로 시작하는 기존 추적(위 _trace_dragging)은 그대로
        # 남겨 뒀다 — 손을 떼도 그 자리에 고정되는 성질까지 똑같다.
        hover_x = self._curve_hover_x(pos, plot) if plot.contains(pos) else None
        if hover_x is not None:
            self._trace_x = hover_x
            self._trace_is_hover = True
            self.setCursor(_point_cursor())
        else:
            if self._trace_is_hover:
                self._trace_x = None
                self._trace_is_hover = False
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def _curve_hover_x(self, pos, plot):
        """커서가 어떤 함수의 곡선에라도 닿아 있으면(픽셀 허용범위 안) 그
        x(데이터 좌표)를 돌려준다. 아무 곡선에도 안 닿아 있으면 None —
        그래프 배경(곡선에서 먼 빈 자리)에서는 커스텀 커서·추적선이
        켜지지 않게 하는 판정이다."""
        x, _y = self._to_data(pos.x(), pos.y(), plot)
        if not (self.xmin <= x <= self.xmax):
            return None
        for f in self.functions:
            if not f.get("visible", True):
                continue
            y = G.value_at(f["text"], x, self.angle_mode)
            if y is None or not (self.ymin <= y <= self.ymax):
                continue
            curve_py = self._to_px(x, y, plot).y()
            if abs(curve_py - pos.y()) <= _TRACE_HIT_TOL:
                return x
        return None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._trace_dragging:
            self._trace_dragging = False
            # [사용성 개선] 손을 뗄 때 함수가 딱 하나만 보이면 그 함수의
            # 점을 자동으로 고정점에 추가한다 — 곡선 위 점을 따로
            # 클릭해야 한다는 걸 몰라서 "어떻게 하는지 모르겠다"는 피드백을
            # 받았다. 여러 함수가 겹쳐 있을 때는 어느 것을 고를지 애매해
            # 여전히 점을 직접 클릭해야 한다.
            values = self._trace_values()
            if len(values) == 1:
                self._pin_point(self._trace_x, next(iter(values)))
            self.update()
            return
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._drag_last_px = None
            self.setCursor(Qt.ArrowCursor)
            self._resample()   # 마무리로 한 번 더 — 고해상도로 선명하게

    # ---------------------------------------------------- [v11] x값 직접 입력
    def _open_trace_input(self, anchor_px, editing_pin=None):
        """[v45.2] editing_pin을 안 주면(기본) 기존처럼 추적선(trace_x)의
        x를 편집한다. editing_pin에 고정점 dict를 주면, 입력을 확정했을
        때 그 점의 x를 바꾼다 — 즉 그 점이 입력한 x 위치로 옮겨간다."""
        if self._trace_input is None:
            self._trace_input = QLineEdit(self)
            self._trace_input.setFixedWidth(70)
            self._trace_input.setStyleSheet(
                f"QLineEdit{{border:1px solid {_TRACE_PURPLE};border-radius:3px;"
                "padding:1px 4px;background:#ffffff;}")
            self._trace_input.returnPressed.connect(self._apply_trace_input)
            self._trace_input.editingFinished.connect(self._hide_trace_input)
        self._editing_pin = editing_pin
        start_x = editing_pin["x"] if editing_pin is not None else self._trace_x
        self._trace_input.setText(_fmt_tick(start_x))
        self._trace_input.move(int(anchor_px.x() - 35), int(anchor_px.y() + 6))
        self._trace_input.show()
        self._trace_input.setFocus()
        self._trace_input.selectAll()

    def _apply_trace_input(self):
        if self._trace_input is None:
            return
        try:
            x = float(self._trace_input.text())
        except ValueError:
            self._hide_trace_input()
            return
        x = max(self.xmin, min(self.xmax, x))
        if self._editing_pin is not None:
            # [v45.2] 고정점 편집 중이었다면 그 점을 이 x로 옮긴다(같은
            # 자리에 이미 다른 점이 있으면 합치지 않고 그대로 둔다 —
            # 겹친 점은 _pin_point와 달리 여기서는 막지 않는다. 사용자가
            # 의도적으로 숫자를 입력한 결과이기 때문이다).
            self._editing_pin["x"] = x
        else:
            self._trace_x = x
            self._trace_is_hover = False
        self._hide_trace_input()
        self.update()

    def _hide_trace_input(self):
        if self._trace_input is not None:
            self._trace_input.hide()
        self._editing_pin = None

    def clear_trace(self):
        self._trace_x = None
        self._trace_dragging = False
        self._trace_is_hover = False
        self._pinned_points = []
        self._hide_trace_input()
        self.update()

    def leaveEvent(self, event):
        if self._trace_is_hover:
            self._trace_x = None
            self._trace_is_hover = False
        if not self._dragging and not self._trace_dragging:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.clear_trace()
        self.reset_view()


def _snap(v):
    """선을 픽셀 격자에 정확히 맞춰 스냅한다(정수 + 0.5) — 안티앨리어싱이
    선을 옆 픽셀에 걸쳐 그리며 한쪽만 번져 보이는 것을 막는다."""
    return int(round(v)) + 0.5


def _dist(p1, p2):
    return ((p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2) ** 0.5


def _fmt_tick(v: float) -> str:
    if abs(v) < 1e-9:
        return "0"
    if abs(v) >= 1000 or abs(v) < 0.01:
        return f"{v:.2e}"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _fmt1(v: float) -> str:
    """[버그 수정] 좌표 라벨(절편·추적값)은 소수점 첫째 자리까지만 보여
    준다 — 넷째 자리까지 나오던 것을 사용자가 짧게 줄여 달라고 요청했다."""
    if abs(v) < 0.05:
        return "0"
    return f"{v:.1f}"


# =============================================================================
# [v45.3] 함수 그래프와 극좌표 그래프가 함께 쓰는 그리기 헬퍼 — 축 화살표,
# 흰 테두리를 두른 라벨 텍스트. 원래 _GraphCanvas의 메서드였던 것을
# 모듈 레벨 함수로 뽑아, polar.py도 똑같은 모양으로 그릴 수 있게 했다.
def draw_arrowhead(p, tip, direction, color):
    """축(또는 임의의 방향선) 끝에 작은 삼각형 화살표를 그린다. direction은
    "up"|"down"|"left"|"right" 중 하나."""
    size = 7.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    if direction == "up":
        poly = QPolygonF([tip, QPointF(tip.x() - size * 0.5, tip.y() + size),
                          QPointF(tip.x() + size * 0.5, tip.y() + size)])
    elif direction == "down":
        poly = QPolygonF([tip, QPointF(tip.x() - size * 0.5, tip.y() - size),
                          QPointF(tip.x() + size * 0.5, tip.y() - size)])
    elif direction == "left":
        poly = QPolygonF([tip, QPointF(tip.x() + size, tip.y() - size * 0.5),
                          QPointF(tip.x() + size, tip.y() + size * 0.5)])
    else:  # "right"
        poly = QPolygonF([tip, QPointF(tip.x() - size, tip.y() - size * 0.5),
                          QPointF(tip.x() - size, tip.y() + size * 0.5)])
    p.drawPolygon(poly)


def draw_text_label(p, rect, align, text, color):
    """글자 자체에 흰 테두리(스트로크)를 둘러 축·곡선과 겹쳐도 읽히게
    한다(뒤에 반투명 상자를 까는 대신)."""
    fm = p.fontMetrics()
    tw = fm.horizontalAdvance(text)
    if align & Qt.AlignHCenter:
        x = rect.center().x() - tw / 2
    elif align & Qt.AlignRight:
        x = rect.right() - tw
    else:
        x = rect.left()
    if align & Qt.AlignVCenter:
        y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
    elif align & Qt.AlignBottom:
        y = rect.bottom() - fm.descent()
    else:
        y = rect.top() + fm.ascent()

    path = QPainterPath()
    path.addText(QPointF(x, y), p.font(), text)
    p.setPen(QPen(QColor(255, 255, 255), 3.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)


# =============================================================================
class GraphWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.angle_mode = "rad"
        self._row_seq = 0
        self.rows = []   # list[_FunctionRow]

        self._build_ui()
        self._load_settings()
        if not self.rows:
            self._add_row("sin(x)")
        self._push_functions()
        self._retranslate_static()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        s = self._settings
        if s is None:
            return
        angle = s.value(_SET_ANGLE, "rad")
        self.angle_mode = angle if angle in ("rad", "deg") else "rad"
        self._update_angle_button()

        raw = s.value(_SET_FUNCTIONS, "")
        if raw:
            try:
                items = json.loads(raw)
                for it in items[:MAX_FUNCTIONS]:
                    if isinstance(it, dict) and it.get("text"):
                        color = it.get("color") if it.get("color") in PALETTE else PALETTE[len(self.rows) % len(PALETTE)]
                        self._add_row(it["text"], color, bool(it.get("visible", True)))
            except (ValueError, TypeError, AttributeError):
                pass

        raw_view = s.value(_SET_VIEW, "")
        if raw_view:
            try:
                v = json.loads(raw_view)
                xmin, xmax = float(v["xmin"]), float(v["xmax"])
                if xmax > xmin:
                    self.canvas.xmin, self.canvas.xmax = xmin, xmax
                self.canvas.auto_y = bool(v.get("auto_y", True))
                if not self.canvas.auto_y:
                    ymin, ymax = float(v["ymin"]), float(v["ymax"])
                    if ymax > ymin:
                        self.canvas.ymin, self.canvas.ymax = ymin, ymax
            except (ValueError, TypeError, KeyError):
                pass
        self._sync_range_fields()
        self.chk_auto_y.setChecked(self.canvas.auto_y)

    def _save_settings(self):
        s = self._settings
        if s is None:
            return
        s.setValue(_SET_ANGLE, self.angle_mode)
        s.setValue(_SET_FUNCTIONS, json.dumps(
            [row.to_dict() for row in self.rows], ensure_ascii=False))
        s.setValue(_SET_VIEW, json.dumps({
            "xmin": self.canvas.xmin, "xmax": self.canvas.xmax,
            "ymin": self.canvas.ymin, "ymax": self.canvas.ymax,
            "auto_y": self.canvas.auto_y,
        }))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 왼쪽 카드: 함수 목록 + 범위(툴바: 각도 단위·추가, 하단: 초기화·이미지) ----
        self.card_funcs = UK.Card()
        self.btn_angle = UK.toggle_button()
        self.btn_angle.clicked.connect(self._toggle_angle)
        self.card_funcs.add_tool(self.btn_angle)
        self.btn_add = UK.tool_button("+")
        self.btn_add.clicked.connect(lambda: self._add_row_interactive())
        self.card_funcs.add_tool(self.btn_add)

        self.rows_holder = QVBoxLayout()
        self.rows_holder.setSpacing(4)
        self.card_funcs.add_body(self.rows_holder)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};")
        self.card_funcs.add_body(sep)

        self.lbl_x = UK.body_label("X")
        self.edit_xmin = QLineEdit()
        self.edit_xmin.setFixedWidth(60)
        self.edit_xmin.editingFinished.connect(self._on_range_edited)
        self.lbl_x_to = UK.body_label("~")
        self.edit_xmax = QLineEdit()
        self.edit_xmax.setFixedWidth(60)
        self.edit_xmax.editingFinished.connect(self._on_range_edited)
        self.card_funcs.add_body(UK.hrow(self.lbl_x, self.edit_xmin, self.lbl_x_to, self.edit_xmax, stretch_last=True))

        self.chk_auto_y = QCheckBox()
        self.chk_auto_y.setChecked(True)
        self.chk_auto_y.stateChanged.connect(self._on_auto_y_toggled)
        self.lbl_y = UK.body_label("Y")
        self.edit_ymin = QLineEdit()
        self.edit_ymin.setFixedWidth(60)
        self.edit_ymin.editingFinished.connect(self._on_range_edited)
        self.lbl_y_to = UK.body_label("~")
        self.edit_ymax = QLineEdit()
        self.edit_ymax.setFixedWidth(60)
        self.edit_ymax.editingFinished.connect(self._on_range_edited)
        self.card_funcs.add_body(UK.hrow(self.chk_auto_y, self.lbl_y, self.edit_ymin, self.lbl_y_to, self.edit_ymax,
                                         stretch_last=True))

        self.chk_intercepts = QCheckBox()
        self.chk_intercepts.setChecked(True)
        self.chk_intercepts.stateChanged.connect(self._on_intercepts_toggled)
        self.card_funcs.add_body(UK.hrow(self.chk_intercepts, stretch_last=True))

        self.lbl_trace_hint = QLabel()
        self.lbl_trace_hint.setWordWrap(True)
        self.lbl_trace_hint.setStyleSheet(f"color:{C.UTIL_MAIN};font-size:11px;background:transparent;")
        self.card_funcs.add_body(self.lbl_trace_hint)
        self.lbl_hint = UK.hint_label()
        self.card_funcs.add_body(self.lbl_hint)
        self.card_funcs.body.addStretch(1)

        self.btn_reset = self.card_funcs.add_footer(UK.secondary_button())
        self.btn_reset.clicked.connect(self._reset_view)
        self.btn_export_image = self.card_funcs.add_footer(UK.secondary_button())
        self.btn_export_image.clicked.connect(self._export_image)

        # ---- 오른쪽 카드: 그래프 캔버스 ----
        self.card_canvas = UK.Card()
        self.canvas = _GraphCanvas()
        self.canvas.rangeChanged.connect(self._on_canvas_range_changed)
        self.canvas.errorsChanged.connect(self._on_errors_changed)
        self.card_canvas.add_body(UK.canvas_frame(self.canvas), 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        self.card_funcs.setFixedWidth(UK.RIGHT_PANEL_W)
        root.addWidget(self.card_funcs)
        root.addWidget(self.card_canvas, 1)

    # ------------------------------------------------------------- 함수 목록
    def _add_row(self, text="", color=None, visible=True):
        if len(self.rows) >= MAX_FUNCTIONS:
            return None
        color = color or PALETTE[len(self.rows) % len(PALETTE)]
        row = _FunctionRow(color, text, visible)
        row.id = self._row_seq
        self._row_seq += 1
        row.changed.connect(self._on_row_changed)
        row.removeRequested.connect(self._on_row_remove)
        self.rows.append(row)
        self.rows_holder.addWidget(row)
        return row

    def _add_row_interactive(self):
        if len(self.rows) >= MAX_FUNCTIONS:
            if self.host:
                self.host.status(tr("util.graph.status.max_functions", a0=MAX_FUNCTIONS))
            return
        self._add_row("")
        self._update_add_button()
        self._push_functions()
        self.rows[-1].edit.setFocus()

    def _on_row_remove(self, row):
        self.rows.remove(row)
        self.rows_holder.removeWidget(row)
        row.deleteLater()
        self._update_add_button()
        self._push_functions()

    def _on_row_changed(self):
        self._push_functions()

    def _update_add_button(self):
        self.btn_add.setEnabled(len(self.rows) < MAX_FUNCTIONS)
        self.btn_add.setToolTip(
            tr("util.graph.btn.add.tip") if len(self.rows) < MAX_FUNCTIONS
            else tr("util.graph.btn.add.max_tip", a0=MAX_FUNCTIONS))

    def _push_functions(self):
        functions = [{"id": row.id, "text": row.edit.text(), "color": row.color,
                     "visible": row.chk_visible.isChecked()} for row in self.rows]
        self.canvas.set_functions(functions)
        self._save_settings()

    # ---------------------------------------------------------------- 범위
    def _sync_range_fields(self):
        self.edit_xmin.setText(_fmt_tick(self.canvas.xmin))
        self.edit_xmax.setText(_fmt_tick(self.canvas.xmax))
        self.edit_ymin.setText(_fmt_tick(self.canvas.ymin))
        self.edit_ymax.setText(_fmt_tick(self.canvas.ymax))
        self.edit_ymin.setEnabled(not self.canvas.auto_y)
        self.edit_ymax.setEnabled(not self.canvas.auto_y)

    def _on_canvas_range_changed(self, xmin, xmax, ymin, ymax):
        self._sync_range_fields()
        self._save_settings()

    def _on_errors_changed(self, errors):
        for row in self.rows:
            row.set_error(errors.get(row.id))

    def _on_range_edited(self):
        try:
            xmin = float(self.edit_xmin.text())
            xmax = float(self.edit_xmax.text())
            if xmax > xmin:
                self.canvas.set_x_range(xmin, xmax)
        except ValueError:
            pass
        if not self.canvas.auto_y:
            try:
                ymin = float(self.edit_ymin.text())
                ymax = float(self.edit_ymax.text())
                if ymax > ymin:
                    self.canvas.set_y_range(ymin, ymax)
            except ValueError:
                pass
        self._sync_range_fields()

    def _on_auto_y_toggled(self, _state):
        self.canvas.set_auto_y(self.chk_auto_y.isChecked())
        self._sync_range_fields()
        self._save_settings()

    def _reset_view(self):
        self.canvas.clear_trace()
        self.canvas.reset_view()
        self.chk_auto_y.setChecked(True)
        self._sync_range_fields()

    def _on_intercepts_toggled(self, _state):
        self.canvas.set_show_intercepts(self.chk_intercepts.isChecked())

    def _export_image(self):
        """[v10] 지금 보이는 그래프를 PNG로 저장한다. 캔버스를 그대로
        캡처하므로 화면에 보이는 것과 똑같은 그림이 나온다."""
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.graph.msg.export_title"), "graph.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pixmap = self.canvas.grab()
        ok = pixmap.save(path, "PNG")
        if self.host:
            if ok:
                self.host.status(tr("util.graph.status.image_saved", a0=path))
                self.host.log(tr("util.graph.log.image_saved", a0=path))
            else:
                self.host.status(tr("util.graph.status.image_fail"))

    def _toggle_angle(self):
        self.angle_mode = "deg" if self.angle_mode == "rad" else "rad"
        self._update_angle_button()
        self.canvas.set_angle_mode(self.angle_mode)
        self._save_settings()

    def _update_angle_button(self):
        self.btn_angle.setText(tr("util.calc.deg") if self.angle_mode == "deg"
                               else tr("util.calc.rad"))
        self.btn_angle.setChecked(self.angle_mode == "deg")

    # ------------------------------------------------------------- 다국어
    def _retranslate_static(self):
        self._update_angle_button()
        self.card_funcs.set_title(tr("util.graph.card.funcs"))
        self.card_canvas.set_title(tr("util.graph.title"))
        self.btn_add.setToolTip(tr("util.graph.btn.add.tip"))
        self.lbl_hint.setText(tr("util.graph.hint"))
        self.chk_auto_y.setText(tr("util.graph.chk.auto_y"))
        self.btn_reset.setText(tr("util.graph.btn.reset"))
        self.btn_reset.setToolTip(tr("util.graph.btn.reset.tip"))
        self.chk_intercepts.setText(tr("util.graph.chk.intercepts"))
        self.chk_intercepts.setToolTip(tr("util.graph.chk.intercepts.tip"))
        self.lbl_trace_hint.setText(tr("util.graph.trace.hint"))
        self.btn_export_image.setText(tr("util.graph.btn.export_image"))
        self.btn_export_image.setToolTip(tr("util.graph.btn.export_image.tip"))
        for row in self.rows:
            row.edit.setPlaceholderText(tr("util.graph.row.placeholder"))
            row.chk_visible.setToolTip(tr("util.graph.row.visible.tip"))
            row.btn_color.setToolTip(tr("util.graph.row.color.tip"))
            row.btn_remove.setToolTip(tr("util.graph.row.remove.tip"))
        self._update_add_button()
        self._push_functions()   # 오류 문구도 새 언어로 다시 계산되게

    def retranslate(self):
        self._retranslate_static()


# =============================================================================
class GraphApp(MiniApp):
    id = "graph"
    icon = "graph"
    category = "math"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = GraphWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()


# =============================================================================
TRANSLATIONS = {
    "util.graph.card.funcs": {"ko": "함수와 범위", "en": "Functions & range", "ja": "関数と範囲"},
    "util.graph.title": {
        "ko": "함수 그래프", "en": "Function Grapher", "ja": "関数グラフ"},
    "util.graph.desc": {
        "ko": "f(x) 형태의 함수를 입력하면 즉시 그래프로 보여줍니다. 여러 함수를 겹쳐 비교할 수 있습니다.",
        "en": "Type f(x) and see it graphed instantly. Overlay several functions to compare them.",
        "ja": "f(x) の形の関数を入力すると、その場でグラフを表示します。複数の関数を重ねて比較できます。"},

    "util.graph.row.placeholder": {
        "ko": "예) sin(x), x^2-3, 1/x", "en": "e.g. sin(x), x^2-3, 1/x",
        "ja": "例) sin(x), x^2-3, 1/x"},
    "util.graph.row.visible.tip": {
        "ko": "이 그래프를 보이거나 숨깁니다.", "en": "Shows or hides this curve.",
        "ja": "このグラフを表示・非表示にします。"},
    "util.graph.row.color.tip": {
        "ko": "클릭하면 선 색이 바뀝니다.", "en": "Click to cycle the line color.",
        "ja": "クリックすると線の色が変わります。"},
    "util.graph.row.remove.tip": {
        "ko": "이 함수를 지웁니다.", "en": "Removes this function.",
        "ja": "この関数を削除します。"},

    "util.graph.btn.add.tip": {
        "ko": "함수를 하나 더 추가합니다.", "en": "Adds another function.",
        "ja": "関数をもう1つ追加します。"},
    "util.graph.btn.add.max_tip": {
        "ko": "함수는 최대 {a0}개까지 동시에 그릴 수 있습니다.",
        "en": "You can graph up to {a0} functions at once.",
        "ja": "関数は最大{a0}個まで同時に描画できます。"},
    "util.graph.status.max_functions": {
        "ko": "함수는 최대 {a0}개까지 추가할 수 있습니다.",
        "en": "You can add up to {a0} functions.",
        "ja": "関数は最大{a0}個まで追加できます。"},

    "util.graph.chk.auto_y": {"ko": "Y 자동", "en": "Auto Y", "ja": "Y 自動"},
    "util.graph.btn.reset": {"ko": "보기 초기화", "en": "Reset view", "ja": "表示を初期化"},
    "util.graph.btn.reset.tip": {
        "ko": "확대·이동한 화면을 원래대로 되돌립니다(더블클릭해도 됩니다).",
        "en": "Restores the default view (double-click also works).",
        "ja": "拡大・移動した表示を元に戻します（ダブルクリックでも可）。"},
    "util.graph.hint": {
        "ko": "마우스 휠로 확대·축소, 드래그로 이동합니다. 커서를 올리면 좌표가 보입니다. "
              "[버그 수정] 가로세로 배율을 항상 같게 맞춰서(등각) 접선·법선이 화면에서도 "
              "정확히 직각으로 보이게 했습니다 — 그래서 X·Y 범위가 크게 다르면 한쪽에 "
              "여백이 남을 수 있습니다(각도가 정확한 대신 생기는 정상적인 현상입니다).",
        "en": "Scroll to zoom, drag to pan. Hover to see coordinates. The aspect ratio is "
              "always kept 1:1 so tangent/normal lines look genuinely perpendicular on screen "
              "— if X and Y ranges differ a lot, one side may show extra margin (a normal "
              "trade-off for angle accuracy).",
        "ja": "ホイールで拡大縮小、ドラッグで移動します。カーソルを合わせると座標が表示されます。"
              "縦横比は常に1:1に保たれ、接線・法線が画面上でも正確に直角に見えるようにしています"
              "— X・Y範囲が大きく異なる場合、片側に余白が出ることがあります（角度の正確さのための"
              "正常な現象です）。"},

    "util.graph.chk.intercepts": {"ko": "절편 표시", "en": "Show intercepts", "ja": "切片を表示"},
    "util.graph.chk.intercepts.tip": {
        "ko": "각 함수의 x절편·y절편을 점과 좌표로 표시합니다.",
        "en": "Marks each function's x- and y-intercepts with a dot and coordinates.",
        "ja": "各関数のx切片・y切片を点と座標で表示します。"},
    "util.graph.btn.export_image": {"ko": "이미지로 저장", "en": "Save as Image", "ja": "画像として保存"},
    "util.graph.btn.export_image.tip": {
        "ko": "지금 보이는 그래프를 PNG 파일로 저장합니다.",
        "en": "Saves the current graph as a PNG file.",
        "ja": "現在のグラフをPNGファイルとして保存します。"},
    "util.graph.msg.export_title": {
        "ko": "그래프 이미지로 저장", "en": "Save Graph as Image", "ja": "グラフを画像として保存"},
    "util.graph.status.image_saved": {
        "ko": "이미지로 저장했습니다: {a0}", "en": "Saved as image: {a0}", "ja": "画像として保存しました: {a0}"},
    "util.graph.status.image_fail": {
        "ko": "이미지 저장에 실패했습니다.", "en": "Failed to save the image.", "ja": "画像の保存に失敗しました。"},
    "util.graph.log.image_saved": {
        "ko": "[함수그래프] 이미지로 저장: {a0}",
        "en": "[Grapher] Saved as image: {a0}",
        "ja": "[関数グラフ] 画像として保存: {a0}"},

    "util.graph.trace.hint": {
        "ko": "x축을 클릭·드래그하면 값을 추적하고, 손을 떼면 고정됩니다(축 위 숫자를 "
              "클릭하면 직접 입력 가능). 곡선 위의 점(●)을 클릭하면 그 점이 표시로 남고, "
              "그 점을 마우스 오른쪽 클릭하면 접선·법선을 그리거나 지울 수 있습니다 — "
              "여러 점에 동시에 그릴 수 있고, 새 점을 찍어도 이전 점은 사라지지 않습니다.",
        "en": "Drag along the x-axis to trace values; release to lock it in place (click "
              "the number on the axis to type an exact value). Click a curve point (●) to "
              "pin it, then right-click that point to draw or remove its tangent/normal "
              "line — multiple points can have lines at once, and picking a new point "
              "doesn't remove earlier ones.",
        "ja": "x軸をドラッグすると値を追跡し、指を離すと固定されます（軸上の数字をクリックで"
              "直接入力可）。曲線上の点（●）をクリックすると印が残り、その点を右クリックすると"
              "接線・法線を描いたり消したりできます — 複数の点に同時に描けて、新しい点を選んでも"
              "以前の点は消えません。"},
    "util.graph.ctx.add_tangent": {"ko": "접선 그리기", "en": "Draw Tangent Line", "ja": "接線を描く"},
    "util.graph.ctx.remove_tangent": {"ko": "접선 지우기", "en": "Remove Tangent Line", "ja": "接線を消す"},
    "util.graph.ctx.add_normal": {"ko": "법선 그리기", "en": "Draw Normal Line", "ja": "法線を描く"},
    "util.graph.ctx.remove_normal": {"ko": "법선 지우기", "en": "Remove Normal Line", "ja": "法線を消す"},
    "util.graph.ctx.remove_point": {"ko": "이 점 지우기", "en": "Remove This Point", "ja": "この点を消す"},
}
GraphApp.tr_table = TRANSLATIONS

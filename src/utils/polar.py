# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 극좌표 그래프 [신규]

r = f(θ) 형태의 곡선(심장형, 장미선 등)을 그린다. 함수 그래프(graph.py)와
뼈대는 비슷하지만, **가로세로 배율을 항상 같게 맞춘다(등각)** — 이게
극좌표 그래프에서는 타협할 수 없는 조건이다(원이 타원처럼 보이면 그래프
자체가 잘못된 것이므로). 그래서 확대/이동도 두 축을 항상 같은 비율로
움직인다.
"""
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QComboBox, QScrollArea, QFrame, QSizePolicy, QFileDialog
)

from ..i18n import tr
from ..styles import C, BTN_DESTRUCTIVE_BG
from . import ui_kit as UK
from .base import MiniApp
from . import polar_solve as P
from .graph import (PALETTE, MAX_FUNCTIONS, _snap, _dist, _fmt1,
                    draw_arrowhead, draw_text_label, _PIN_RED)

_SET_ANGLE = "util.polar.angle_mode"
_SET_FUNCTIONS = "util.polar.functions"
_SET_RANGE = "util.polar.theta_range"


def _fmt_tick(v: float) -> str:
    if abs(v) < 1e-9:
        return "0"
    if abs(v) >= 1000 or abs(v) < 0.01:
        return f"{v:.2e}"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


# =============================================================================
class _PolarRow(QWidget):
    """함수 하나 = 색 스와치 + 수식 입력창 + 표시 여부 체크박스 + 삭제 버튼.
    graph.py의 _FunctionRow와 구조는 같지만 이 도구만의 문구(tr 키)를 써야
    해서 따로 둔다."""

    def __init__(self, color, text="", visible=True, parent=None, on_changed=None, on_remove=None):
        super().__init__(parent)
        self.color = color
        self._on_changed = on_changed

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.chk_visible = QCheckBox()
        self.chk_visible.setChecked(visible)
        self.chk_visible.setToolTip(tr("util.polar.row.visible.tip"))
        self.chk_visible.stateChanged.connect(lambda _=None: self._emit())
        lay.addWidget(self.chk_visible)

        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(22, 22)
        self.btn_color.setCursor(Qt.PointingHandCursor)
        self.btn_color.setToolTip(tr("util.polar.row.color.tip"))
        self.btn_color.clicked.connect(self._cycle_color)
        self._apply_color_style()
        lay.addWidget(self.btn_color)

        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText(tr("util.polar.row.placeholder"))
        self.edit.setFont(QFont("Consolas", 12))
        self.edit.textChanged.connect(lambda _=None: self._emit())
        lay.addWidget(self.edit, 1)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color:{BTN_DESTRUCTIVE_BG};font-size:10px;background:transparent;")
        self.lbl_error.setFixedWidth(0)
        lay.addWidget(self.lbl_error)

        self.btn_remove = QPushButton("×")
        self.btn_remove.setFixedSize(22, 22)
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.setToolTip(tr("util.polar.row.remove.tip"))
        self.btn_remove.setStyleSheet(UK.tool_button().styleSheet())
        self.btn_remove.clicked.connect(lambda: on_remove(self) if on_remove else None)
        lay.addWidget(self.btn_remove)

    def _emit(self):
        if self._on_changed:
            self._on_changed()

    def _apply_color_style(self):
        self.btn_color.setStyleSheet(
            f"QPushButton{{background-color:{self.color};border:1px solid #00000022;"
            "border-radius:4px;}")

    def _cycle_color(self):
        idx = PALETTE.index(self.color) if self.color in PALETTE else -1
        self.color = PALETTE[(idx + 1) % len(PALETTE)]
        self._apply_color_style()
        self._emit()

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
        return {"text": self.edit.text(), "color": self.color, "visible": self.chk_visible.isChecked()}


# =============================================================================
class _PolarCanvas(QWidget):
    """등각(가로세로 배율 동일) 좌표계로 극좌표 곡선을 그린다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self.functions = []       # [{"id","text","color","visible"}]
        self.angle_mode = "rad"
        self.theta_min, self.theta_max = 0.0, 2 * math.pi
        self.xmin, self.xmax, self.ymin, self.ymax = -5.0, 5.0, -5.0, 5.0
        self._raw = {}             # id -> PolarSampleResult
        self._segments = {}        # id -> segments
        self._dragging = False
        self._drag_last_px = None
        self._press_px = None     # [v45.3] 누른 위치 — 손을 뗄 때 거의
        # 안 움직였으면 "클릭"으로 보고 그 자리에 점을 찍는다(드래그와
        # 구분하기 위함).
        self._hover = None
        self._clicked_point = None   # [v45.3] (x, y) 또는 None — 클릭해서
        # 찍은 점. 원점과 점선으로 잇고 (r, θ) 값을 표시한다.

    # ------------------------------------------------------------ 데이터
    def set_functions(self, functions):
        self.functions = functions
        self._resample()

    def set_angle_mode(self, mode):
        self.angle_mode = mode
        self._resample()

    def set_theta_range(self, tmin, tmax):
        self.theta_min, self.theta_max = tmin, tmax
        self._resample()

    def reset_view(self):
        self.xmin, self.xmax, self.ymin, self.ymax = -5.0, 5.0, -5.0, 5.0
        self._clicked_point = None
        self.update()

    def fit_view(self):
        """지금 그려진 모든 곡선이 화면에 딱 맞게 범위를 다시 잡는다."""
        pts = []
        for fid, res in self._raw.items():
            for x, y in zip(res.xs, res.ys):
                if x is not None and y is not None:
                    pts.append((x, y))
        if not pts:
            self.reset_view()
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.xmin, self.xmax, self.ymin, self.ymax = P.auto_bounds(xs, ys)
        self.update()

    errorsChanged_cb = None   # 위젯이 채워 줌: fid -> error text 콜백

    def _resample(self, n=800):
        self._raw = {}
        self._segments = {}
        errors = {}
        for f in self.functions:
            text = f["text"].strip()
            if not text:
                errors[f["id"]] = None
                continue
            res = P.sample(text, self.theta_min, self.theta_max, n, self.angle_mode)
            self._raw[f["id"]] = res
            self._segments[f["id"]] = P.build_segments(res.xs, res.ys)
            errors[f["id"]] = res.error
        if self.errorsChanged_cb:
            self.errorsChanged_cb(errors)
        self.update()

    # ------------------------------------------------------------ 좌표 변환
    def _plot_rect(self):
        r = self.rect()
        margin = 30
        return QRectF(margin, 10, max(1, r.width() - margin - 10), max(1, r.height() - 20))

    def _scale(self, plot):
        xspan = max(1e-9, self.xmax - self.xmin)
        yspan = max(1e-9, self.ymax - self.ymin)
        return min(plot.width() / xspan, plot.height() / yspan)

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
            return (0.0, 0.0)
        cx = (self.xmin + self.xmax) / 2
        cy = (self.ymin + self.ymax) / 2
        ccx = plot.left() + plot.width() / 2
        ccy = plot.top() + plot.height() / 2
        x = cx + (px - ccx) / s
        y = cy - (py - ccy) / s
        return (x, y)

    # ------------------------------------------------------------- 그리기
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        plot = self._plot_rect()

        self._draw_ticks(p, plot)
        self._draw_axes(p, plot)
        self._draw_curves(p, plot)
        self._draw_clicked_point(p, plot)
        if self._hover is not None:
            self._draw_crosshair(p, plot)
        p.end()

    def _draw_ticks(self, p, plot):
        s = self._scale(plot)
        if s <= 0:
            return
        step = _nice_step((plot.width() / s))
        pen = QPen(QColor("#9aa0a8"), 1)
        p.setPen(pen)
        font = QFont("Arial", 8)
        p.setFont(font)
        cx = (self.xmin + self.xmax) / 2
        cy = (self.ymin + self.ymax) / 2
        x0_px = self._to_px(0, cy, plot).x() if self.ymin <= 0 <= self.ymax else None
        y0_px = self._to_px(cx, 0, plot).y() if self.xmin <= 0 <= self.xmax else None
        axis_x_row = y0_px if y0_px is not None else plot.bottom()
        axis_y_col = x0_px if x0_px is not None else plot.left()

        k0 = math.floor(self.xmin / step)
        k1 = math.ceil(self.xmax / step)
        for k in range(int(k0), int(k1) + 1):
            tx = k * step
            if tx == 0 or not (self.xmin <= tx <= self.xmax):
                continue
            pt = self._to_px(tx, cy, plot)
            p.drawLine(QPointF(pt.x(), axis_x_row - 4), QPointF(pt.x(), axis_x_row + 4))
            p.drawText(QRectF(pt.x() - 20, axis_x_row + 5, 40, 14), Qt.AlignHCenter | Qt.AlignTop, _fmt_tick(tx))

        k0 = math.floor(self.ymin / step)
        k1 = math.ceil(self.ymax / step)
        for k in range(int(k0), int(k1) + 1):
            ty = k * step
            if ty == 0 or not (self.ymin <= ty <= self.ymax):
                continue
            pt = self._to_px(cx, ty, plot)
            p.drawLine(QPointF(axis_y_col - 4, pt.y()), QPointF(axis_y_col + 4, pt.y()))
            p.drawText(QRectF(0, pt.y() - 8, axis_y_col - 6, 16), Qt.AlignRight | Qt.AlignVCenter, _fmt_tick(ty))

    def _draw_axes(self, p, plot):
        """[v45.3] 함수 그래프(graph.py)와 똑같이 x축·y축 양의 방향
        끝에 화살표를 붙였다 — 두 그래프 도구의 생김새를 통일했다."""
        p.setClipRect(plot)
        pen = QPen(QColor(C.AXIS_STRONG), 2.0)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        y_axis_visible = self.ymin <= 0 <= self.ymax
        x_axis_visible = self.xmin <= 0 <= self.xmax
        if y_axis_visible:
            y0 = _snap(self._to_px(0, 0, plot).y())
            p.drawLine(QPointF(plot.left(), y0), QPointF(plot.right(), y0))
            draw_arrowhead(p, QPointF(plot.right(), y0), "right", C.AXIS_STRONG)
            p.setPen(pen)   # 화살표가 펜을 바꾸므로(NoPen) 복원해야 다음 선이 보인다.
        if x_axis_visible:
            x0 = _snap(self._to_px(0, 0, plot).x())
            p.drawLine(QPointF(x0, plot.top()), QPointF(x0, plot.bottom()))
            draw_arrowhead(p, QPointF(x0, plot.top()), "up", C.AXIS_STRONG)
        p.setClipping(False)
        if x_axis_visible and y_axis_visible:
            origin = self._to_px(0, 0, plot)
            p.setBrush(QColor(C.AXIS_STRONG))
            p.setPen(Qt.NoPen)
            p.drawEllipse(origin, 2.2, 2.2)

    def _draw_curves(self, p, plot):
        p.setClipRect(plot)
        for f in self.functions:
            if not f.get("visible", True):
                continue
            segs = self._segments.get(f["id"])
            if not segs:
                continue
            pen = QPen(QColor(f["color"]), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            for seg in segs:
                if len(seg) < 2:
                    continue
                poly = QPolygonF([self._to_px(x, y, plot) for x, y in seg])
                p.drawPolyline(poly)
        p.setClipping(False)

    def _draw_clicked_point(self, p, plot):
        """[v45.3] 그래프 영역을 클릭하면 찍히는 점 — 원점과 점선으로
        잇고, 그 점의 (r, θ) 값을 근처에 적는다. 함수 그래프(graph.py)
        의 고정점·발선 그리기 패턴을 그대로 가져왔다."""
        if self._clicked_point is None:
            return
        x, y = self._clicked_point
        if not (self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax):
            return
        pt_px = self._to_px(x, y, plot)
        origin_px = self._to_px(0, 0, plot)

        p.setClipRect(plot)
        foot_pen = QPen(QColor(_PIN_RED), 1.2, Qt.DashLine)
        p.setPen(foot_pen)
        p.drawLine(origin_px, pt_px)
        p.setPen(QPen(QColor(_PIN_RED), 1.6))
        p.setBrush(QColor(_PIN_RED))
        p.drawEllipse(pt_px, 5.0, 5.0)
        p.setClipping(False)

        r = math.hypot(x, y)
        theta_rad = math.atan2(y, x)
        theta_disp = theta_rad if self.angle_mode == "rad" else math.degrees(theta_rad)
        unit = "" if self.angle_mode == "rad" else "°"
        label = f"(r={_fmt1(r)}, \u03b8={_fmt1(theta_disp)}{unit})"
        font = QFont("Arial", 9)
        p.setFont(font)
        fm = p.fontMetrics()
        w_lbl = fm.horizontalAdvance(label) + 8
        # 점이 plot 오른쪽 절반에 있으면 라벨을 왼쪽에, 왼쪽 절반에
        # 있으면 오른쪽에 둬서 곡선·화면 가장자리와 덜 겹치게 한다.
        if pt_px.x() - plot.left() < plot.width() / 2:
            rect = QRectF(pt_px.x() + 8, pt_px.y() - 18, w_lbl, 16)
        else:
            rect = QRectF(pt_px.x() - 8 - w_lbl, pt_px.y() - 18, w_lbl, 16)
        # 플롯 영역을 벗어나지 않도록 안쪽으로 당긴다.
        rect.moveLeft(min(max(rect.left(), plot.left() + 2), plot.right() - w_lbl - 2))
        if rect.top() < plot.top() + 2:
            rect.moveTop(pt_px.y() + 8)
        draw_text_label(p, rect, Qt.AlignCenter, label, _PIN_RED)

    def _draw_crosshair(self, p, plot):
        if not plot.contains(QPointF(*self._hover_px)):
            return
        x, y = self._hover
        r = math.hypot(x, y)
        theta = math.degrees(math.atan2(y, x))
        text = f"x={_fmt1(x)}, y={_fmt1(y)}  (r={_fmt1(r)}, θ={_fmt1(theta)}°)"
        p.setPen(QPen(QColor("#6b7280")))
        p.setFont(QFont("Arial", 10))
        p.drawText(QRectF(plot.left() + 6, plot.top() + 4, plot.width() - 12, 18),
                  Qt.AlignLeft | Qt.AlignVCenter, text)

    # ------------------------------------------------------------ 마우스
    def wheelEvent(self, event):
        plot = self._plot_rect()
        pos = event.position() if hasattr(event, "position") else event.posF()
        data_x, data_y = self._to_data(pos.x(), pos.y(), plot)
        factor = 0.85 if event.angleDelta().y() > 0 else 1 / 0.85
        for attr_min, attr_max, center in (("xmin", "xmax", data_x), ("ymin", "ymax", data_y)):
            lo, hi = getattr(self, attr_min), getattr(self, attr_max)
            span = P.clamp_span((hi - lo) * factor)
            ratio = (center - lo) / (hi - lo) if hi != lo else 0.5
            new_lo = center - span * ratio
            setattr(self, attr_min, new_lo)
            setattr(self, attr_max, new_lo + span)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            pos = event.position() if hasattr(event, "position") else event.posF()
            self._drag_last_px = (pos.x(), pos.y())
            self._press_px = (pos.x(), pos.y())   # [v45.3] 클릭 판정용
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.posF()
        plot = self._plot_rect()
        if self._dragging and self._drag_last_px is not None:
            s = self._scale(plot)
            dx = (pos.x() - self._drag_last_px[0]) / s if s else 0
            dy = (pos.y() - self._drag_last_px[1]) / s if s else 0
            self.xmin -= dx; self.xmax -= dx
            self.ymin += dy; self.ymax += dy
            self._drag_last_px = (pos.x(), pos.y())
        if plot.contains(pos):
            self._hover = self._to_data(pos.x(), pos.y(), plot)
            self._hover_px = (pos.x(), pos.y())
        else:
            self._hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # [v45.3] 누른 자리에서 거의 안 움직였으면(패닝이 아니라)
            # "클릭"으로 보고, 그 자리에 점을 찍는다 — 원점과 점선으로
            # 잇고 (r, θ) 값을 보여준다(함수 그래프의 "곡선 위 점 클릭"
            # 과 같은 느낌이지만, 극좌표에서는 곡선 위가 아니어도 그래프
            # 영역 어디든 클릭해서 그 지점을 조사할 수 있게 했다).
            pos = event.position() if hasattr(event, "position") else event.posF()
            if self._press_px is not None and _dist(
                    QPointF(*self._press_px), pos) <= 4.0:
                plot = self._plot_rect()
                if plot.contains(pos):
                    self._clicked_point = self._to_data(pos.x(), pos.y(), plot)
            self._dragging = False
            self._drag_last_px = None
            self._press_px = None
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def mouseDoubleClickEvent(self, event):
        self.reset_view()

    def leaveEvent(self, event):
        self._hover = None
        self.update()


def _nice_step(target_px_span_in_units, target_ticks=8):
    if target_px_span_in_units <= 0:
        return 1.0
    raw = target_px_span_in_units / target_ticks
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


# =============================================================================
class PolarWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.angle_mode = "rad"
        self.rows = []
        self._build_ui()
        self._load_settings()
        self._push_functions()

    def _build_ui(self):
        # ---- 왼쪽 카드: 곡선 목록 + 범위(툴바: 각도 단위·추가, 하단: 화면에 맞추기·초기화·이미지) ----
        self.card_funcs = UK.Card()
        self.btn_angle = UK.toggle_button("RAD")
        self.btn_angle.clicked.connect(self._toggle_angle)
        self.card_funcs.add_tool(self.btn_angle)
        self.btn_add = UK.tool_button("+")
        self.btn_add.clicked.connect(lambda: self._add_row_interactive())
        self.card_funcs.add_tool(self.btn_add)

        self.rows_lay = QVBoxLayout()
        self.rows_lay.setSpacing(4)
        self.card_funcs.add_body(self.rows_lay)

        self.lbl_preset = UK.body_label()
        self.combo_preset = QComboBox()
        for key, _text, _tmin, _tmax in P.PRESETS:
            self.combo_preset.addItem("", key)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_chosen)
        preset_row = UK.hrow(self.lbl_preset)
        preset_row.addWidget(self.combo_preset, 1)
        self.card_funcs.add_body(preset_row)

        self.lbl_range = UK.body_label()
        self.edit_tmin = QLineEdit("0")
        self.edit_tmin.setFixedWidth(70)
        self.edit_tmin.editingFinished.connect(self._on_range_edited)
        self.lbl_to = UK.body_label("~")
        self.edit_tmax = QLineEdit("6.283")
        self.edit_tmax.setFixedWidth(70)
        self.edit_tmax.editingFinished.connect(self._on_range_edited)
        self.card_funcs.add_body(UK.hrow(self.lbl_range, self.edit_tmin, self.lbl_to, self.edit_tmax,
                                         stretch_last=True))

        self.lbl_hint = UK.hint_label()
        self.card_funcs.add_body(self.lbl_hint)
        self.card_funcs.body.addStretch(1)

        self.btn_fit = self.card_funcs.add_footer(UK.secondary_button())
        self.btn_fit.clicked.connect(lambda: self.canvas.fit_view())
        self.btn_reset = self.card_funcs.add_footer(UK.secondary_button())
        self.btn_reset.clicked.connect(lambda: self.canvas.reset_view())
        self.btn_export_image = self.card_funcs.add_footer(UK.secondary_button())
        self.btn_export_image.clicked.connect(self._export_image)

        # ---- 오른쪽 카드: 극좌표 캔버스 ----
        self.card_canvas = UK.Card()
        self.canvas = _PolarCanvas()
        self.canvas.errorsChanged_cb = self._on_errors
        self.card_canvas.add_body(UK.canvas_frame(self.canvas), 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        self.card_funcs.setFixedWidth(UK.RIGHT_PANEL_W)
        root.addWidget(self.card_funcs)
        root.addWidget(self.card_canvas, 1)

        self._add_row("cos(3*theta)", PALETTE[0])
        self.retranslate()

    # -------------------------------------------------------------- 행 관리
    def _add_row(self, text="", color=None):
        if color is None:
            color = PALETTE[len(self.rows) % len(PALETTE)]
        row = _PolarRow(color, text, True, on_changed=self._push_functions,
                        on_remove=self._remove_row)
        row.edit.setPlaceholderText(tr("util.polar.row.placeholder"))
        self.rows.append(row)
        self.rows_lay.addWidget(row)
        return row

    def _add_row_interactive(self):
        if len(self.rows) >= MAX_FUNCTIONS:
            return
        self._add_row("")
        self._update_add_button()
        self._push_functions()

    def _remove_row(self, row):
        if len(self.rows) <= 1:
            return
        self.rows.remove(row)
        self.rows_lay.removeWidget(row)
        row.deleteLater()
        self._update_add_button()
        self._push_functions()

    def _update_add_button(self):
        self.btn_add.setEnabled(len(self.rows) < MAX_FUNCTIONS)

    def _on_preset_chosen(self, idx):
        if idx < 0:
            return
        key = self.combo_preset.itemData(idx)
        preset = next((pr for pr in P.PRESETS if pr[0] == key), None)
        if preset is None:
            return
        _key, text, tmin, tmax = preset
        if len(self.rows) < MAX_FUNCTIONS:
            self._add_row(text)
        else:
            self.rows[-1].edit.setText(text)
        self.edit_tmin.setText(_fmt1(tmin) if tmin else "0")
        self.edit_tmax.setText(f"{tmax:.3f}")
        self._on_range_edited()
        self._update_add_button()
        self._push_functions()

    def _on_range_edited(self):
        try:
            tmin = float(self.edit_tmin.text())
            tmax = float(self.edit_tmax.text())
            if tmax <= tmin:
                raise ValueError
        except ValueError:
            self._sync_range_fields()
            return
        self.canvas.set_theta_range(tmin, tmax)
        self._save_settings()

    def _sync_range_fields(self):
        self.edit_tmin.setText(_fmt1(self.canvas.theta_min))
        self.edit_tmax.setText(_fmt1(self.canvas.theta_max))

    def _push_functions(self):
        functions = []
        for i, row in enumerate(self.rows):
            functions.append({"id": i, "text": row.edit.text(), "color": row.color,
                             "visible": row.chk_visible.isChecked()})
        self.canvas.set_functions(functions)
        self._save_settings()

    def _on_errors(self, errors):
        for i, row in enumerate(self.rows):
            row.set_error(errors.get(i) or "")

    def _toggle_angle(self):
        self.angle_mode = "deg" if self.angle_mode == "rad" else "rad"
        self.btn_angle.setText(self.angle_mode.upper())
        self.canvas.set_angle_mode(self.angle_mode)
        self._save_settings()

    def _export_image(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("util.polar.msg.export_title"), "polar.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        ok = self.canvas.grab().save(path, "PNG")
        if self.host:
            if ok:
                self.host.status(tr("util.polar.status.image_saved", a0=path))
                self.host.log(tr("util.polar.log.image_saved", a0=path))
            else:
                self.host.status(tr("util.polar.status.image_fail"))

    # -------------------------------------------------------------- 설정
    def _load_settings(self):
        if self._settings is None:
            return
        mode = self._settings.value(_SET_ANGLE, "rad")
        self.angle_mode = mode if mode in ("rad", "deg") else "rad"
        self.btn_angle.setText(self.angle_mode.upper())
        self.canvas.angle_mode = self.angle_mode

        raw_range = self._settings.value(_SET_RANGE, "")
        if raw_range:
            try:
                tmin, tmax = (float(v) for v in raw_range.split(","))
                self.canvas.theta_min, self.canvas.theta_max = tmin, tmax
                self._sync_range_fields()
            except (ValueError, TypeError):
                pass

        raw = self._settings.value(_SET_FUNCTIONS, "")
        if raw:
            import json
            try:
                items = json.loads(raw)
                for row in self.rows:
                    self.rows_lay.removeWidget(row)
                    row.deleteLater()
                self.rows = []
                for it in items[:MAX_FUNCTIONS]:
                    self._add_row(it.get("text", ""), it.get("color"))
                    self.rows[-1].chk_visible.setChecked(it.get("visible", True))
                if not self.rows:
                    self._add_row("")
            except (ValueError, TypeError, KeyError):
                pass
        self._update_add_button()

    def _save_settings(self):
        if self._settings is None:
            return
        import json
        self._settings.setValue(_SET_ANGLE, self.angle_mode)
        self._settings.setValue(_SET_RANGE, f"{self.canvas.theta_min},{self.canvas.theta_max}")
        self._settings.setValue(_SET_FUNCTIONS, json.dumps([r.to_dict() for r in self.rows]))

    # -------------------------------------------------------------- 다국어
    def retranslate(self):
        self.btn_angle.setText(self.angle_mode.upper())
        self.card_funcs.set_title(tr("util.polar.card.funcs"))
        self.card_canvas.set_title(tr("util.polar.title"))
        self.btn_add.setToolTip(tr("util.polar.btn.add.tip"))
        self.lbl_preset.setText(tr("util.polar.lbl.preset"))
        for i, (key, _text, _tmin, _tmax) in enumerate(P.PRESETS):
            self.combo_preset.setItemText(i, tr(f"util.polar.preset.{key}"))
        self.lbl_range.setText(tr("util.polar.lbl.range"))
        self.btn_fit.setText(tr("util.polar.btn.fit"))
        self.btn_reset.setText(tr("util.polar.btn.reset"))
        self.btn_export_image.setText(tr("util.polar.btn.export_image"))
        self.lbl_hint.setText(tr("util.polar.hint"))
        for row in self.rows:
            row.edit.setPlaceholderText(tr("util.polar.row.placeholder"))
            row.chk_visible.setToolTip(tr("util.polar.row.visible.tip"))
            row.btn_color.setToolTip(tr("util.polar.row.color.tip"))
            row.btn_remove.setToolTip(tr("util.polar.row.remove.tip"))


# =============================================================================
class PolarApp(MiniApp):
    id = "polar"
    icon = "polar"
    category = "math"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = PolarWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.polar.title": {"ko": "극좌표 그래프", "en": "Polar Grapher", "ja": "極座標グラフ"},
    "util.polar.card.funcs": {"ko": "곡선과 범위", "en": "Curves & range", "ja": "曲線と範囲"},
    "util.polar.desc": {
        "ko": "r=f(θ) 형태의 극좌표 함수(심장형·장미선 등)를 그립니다.",
        "en": "Plots polar curves r=f(θ) such as cardioids and rose curves.",
        "ja": "r=f(θ)形式の極座標関数（心臓形・バラ曲線など）を描きます。"},
    "util.polar.btn.add.tip": {"ko": "함수를 추가합니다.", "en": "Add a function.", "ja": "関数を追加します。"},
    "util.polar.row.placeholder": {"ko": "예) 1+cos(theta)", "en": "e.g. 1+cos(theta)", "ja": "例）1+cos(theta)"},
    "util.polar.row.visible.tip": {"ko": "체크를 풀면 이 곡선을 숨깁니다.", "en": "Uncheck to hide this curve.", "ja": "チェックを外すとこの曲線を隠します。"},
    "util.polar.row.color.tip": {"ko": "클릭하면 다른 색으로 바뀝니다.", "en": "Click to cycle colors.", "ja": "クリックすると色が変わります。"},
    "util.polar.row.remove.tip": {"ko": "이 함수를 없앱니다.", "en": "Remove this function.", "ja": "この関数を削除します。"},
    "util.polar.lbl.preset": {"ko": "예시 곡선", "en": "Preset curve", "ja": "例の曲線"},
    "util.polar.preset.cardioid": {"ko": "심장형(cardioid)", "en": "Cardioid", "ja": "心臓形（カージオイド）"},
    "util.polar.preset.rose3": {"ko": "장미선 3잎", "en": "Rose curve (3 petals)", "ja": "バラ曲線（花びら3枚）"},
    "util.polar.preset.rose4": {"ko": "장미선 4잎", "en": "Rose curve (4 petals)", "ja": "バラ曲線（花びら4枚）"},
    "util.polar.preset.circle": {"ko": "원(r=3)", "en": "Circle (r=3)", "ja": "円（r=3）"},
    "util.polar.preset.spiral": {"ko": "나선(spiral)", "en": "Spiral", "ja": "螺旋（スパイラル）"},
    "util.polar.preset.lemniscate_approx": {"ko": "연주형 근사(lemniscate)", "en": "Lemniscate (approx.)", "ja": "連珠形近似（レムニスケート）"},
    "util.polar.lbl.range": {"ko": "θ 범위", "en": "θ range", "ja": "θの範囲"},
    "util.polar.btn.fit": {"ko": "화면에 맞추기", "en": "Fit to view", "ja": "画面に合わせる"},
    "util.polar.btn.reset": {"ko": "보기 초기화", "en": "Reset view", "ja": "表示を初期化"},
    "util.polar.btn.export_image": {"ko": "이미지로 저장", "en": "Save as Image", "ja": "画像として保存"},
    "util.polar.hint": {
        "ko": "θ는 각도(라디안/도)입니다 — 식에는 'theta'로 씁니다. 마우스 휠로 확대·축소, "
              "드래그로 이동합니다. 원이 타원처럼 보이지 않도록 항상 가로세로 비율을 같게 맞춥니다.",
        "en": "θ is the angle (radians/degrees) — write it as 'theta' in expressions. Scroll to "
              "zoom, drag to pan. The aspect ratio is always kept 1:1 so circles never look like ellipses.",
        "ja": "θは角度（ラジアン/度）です — 式には「theta」と書きます。ホイールで拡大縮小、"
              "ドラッグで移動します。円が楕円に見えないよう縦横比は常に1:1に保たれます。"},
    "util.polar.msg.export_title": {"ko": "그래프 이미지로 저장", "en": "Save Graph as Image", "ja": "グラフを画像として保存"},
    "util.polar.status.image_saved": {"ko": "이미지로 저장했습니다: {a0}", "en": "Saved as image: {a0}", "ja": "画像として保存しました: {a0}"},
    "util.polar.status.image_fail": {"ko": "이미지 저장에 실패했습니다.", "en": "Failed to save the image.", "ja": "画像の保存に失敗しました。"},
    "util.polar.log.image_saved": {
        "ko": "[극좌표그래프] 이미지로 저장: {a0}", "en": "[Polar] Saved as image: {a0}", "ja": "[極座標グラフ] 画像として保存: {a0}"},
}
PolarApp.tr_table = TRANSLATIONS

# -*- coding: utf-8 -*-
"""
FolderKit — 이미지 편집 모드 핵심 (구 ImageCrop, Tkinter → PySide6 포팅)
- ImageState: 이미지 1장의 독립 편집 상태(크롭 영역/커브)
- build_lut / _natural_cubic_spline_coeffs / apply_curve_to_image: 레이어 커브(자연 삼차 스플라인)
- CropCanvas: 크롭 지정(점선 테두리+원형 핸들) + 적용 결과 미리보기 위젯
- CurvePopover: 우측 상단 팝오버로 뜨는 커브 편집 그래프
- make_mode_icon: 모드 전환 세그먼트 버튼용 아이콘을 코드로 그려서 생성
"""
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QImage, QIcon, QPolygonF,
    QShortcut, QKeySequence
)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from .styles import C, RATIO_KEYS, EDGE_TOL, HANDLE_R
from .i18n import tr, register_translations

ZOOM_STEP = 1.25        # [v49.1] Ctrl+휠 한 칸에 이만큼 확대/축소
ZOOM_MAX_PIXEL = 8.0    # [v49.1] 원본 한 픽셀이 화면에서 최대 이만큼(논리 픽셀) 커질 때까지

register_translations({
    "imgedit.zoom.tip": {
        "ko": "Ctrl+마우스 휠: 확대/축소 · 확대 중 휠: 위아래 이동, Shift+휠: 좌우 이동 · "
              "가운데 버튼 끌기: 이동 · 가운데 버튼 두 번 클릭: 화면에 맞춤",
        "en": "Ctrl+wheel: zoom · while zoomed, wheel: scroll up/down, Shift+wheel: left/right · "
              "middle-drag: pan · middle double-click: fit to window",
        "ja": "Ctrl+ホイール: 拡大/縮小 · 拡大中ホイール: 上下移動、Shift+ホイール: 左右移動 · "
              "中ボタンドラッグ: 移動 · 中ボタンダブルクリック: 画面に合わせる"},
    "imgedit.zoom.badge": {"ko": "{a0}%", "en": "{a0}%", "ja": "{a0}%"},
})

# =============================================================================
# 6b. [v05] 이미지 편집 모드 — 데이터 모델 / 크롭 캔버스 / 커브 팝오버
# =============================================================================
class ImageState:
    """이미지 한 장에 대한 독립적인 편집 상태(계획서 3.6). 다른 이미지와 절대 공유되지 않는다."""

    def __init__(self, path):
        self.path = path
        self.crop_rect = None          # (x0,y0,x1,y1) — 원본 이미지 픽셀 좌표계, None=전체
        self.ratio = RATIO_KEYS[0]
        self.curve_points = [(0, 0), (255, 255)]  # 계획서 3.4: 커브 1개(전 채널 공통)
        self.applied = False           # "적용"을 눌러 확정했는지
        self.saved = False             # "저장"까지 반영됐는지
        self.undo_stack = []           # [v09] 되돌리기용 스냅샷 스택(이미지별 독립)
        self.redo_stack = []           # [v09] 재실행용 스냅샷 스택

    def snapshot(self):
        """[v09] 되돌리기/재실행을 위한 현재 편집 상태 스냅샷."""
        return {
            "crop_rect": self.crop_rect,
            "ratio": self.ratio,
            "curve_points": list(self.curve_points),
            "applied": self.applied,
            "saved": self.saved,
        }

    def restore(self, snap):
        self.crop_rect = snap["crop_rect"]
        self.ratio = snap["ratio"]
        self.curve_points = list(snap["curve_points"])
        self.applied = snap["applied"]
        self.saved = snap["saved"]


def _natural_cubic_spline_coeffs(xs, ys):
    """[v08] 자연 삼차 스플라인(Natural Cubic Spline) 계수 계산 (Thomas 알고리즘).
    '자연(natural)' 경계 조건은 양 끝 포인트에서 2차 도함수(곡률)를 정확히 0으로 고정한다 —
    즉 양 끝 포인트에는 그 바깥쪽으로 곡선을 당기는 가상의 콘트롤 포인트가 존재하지 않고,
    끝점에서 휘어짐이 자연스럽게 사그라들도록(직선에 가깝게) 마무리된다. Catmull-Rom처럼
    각 구간을 이웃 4점만으로 근사하는 국소(local) 보간과 달리, 전체 포인트를 하나의
    연립방정식으로 동시에 풀어 전 구간이 매끄럽게(1차·2차 도함수 모두 연속) 이어진다."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    alpha = [0.0] * n
    for i in range(1, n - 1):
        alpha[i] = (3 / h[i]) * (ys[i + 1] - ys[i]) - (3 / h[i - 1]) * (ys[i] - ys[i - 1])
    l = [1.0] * n
    mu = [0.0] * n
    z = [0.0] * n
    for i in range(1, n - 1):
        l[i] = 2 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]
    c = [0.0] * n
    b = [0.0] * n
    d = [0.0] * n
    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (ys[j + 1] - ys[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3
        d[j] = (c[j + 1] - c[j]) / (3 * h[j])
    return b, c, d


def build_lut(points):
    """[v08] 지정한 모든 (x,y) 포인트를 정확히 지나면서 전 구간이 매끄럽게 이어지는
    자연 삼차 스플라인(Natural Cubic Spline)의 0~255 룩업테이블을 만든다.
    (포토샵 커브와 동일한 전역 보간 방식 — 국소 보간인 Catmull-Rom 대신 사용)
    대각선 위로 움직이면 밝아지고 아래로 움직이면 어두워지는 효과가 반영되도록
    실제 y값을 그대로 매핑에 사용한다."""
    dedup = {}
    for x, y in points:
        dedup[round(x)] = y
    if 0 not in dedup:
        dedup[0] = min(dedup.values()) if dedup else 0
    if 255 not in dedup:
        dedup[255] = max(dedup.values()) if dedup else 255
    pts = sorted(dedup.items())
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    lut = [0] * 256
    if n < 2:
        return list(range(256))
    if n == 2:
        x0, y0 = pts[0]
        x1, y1 = pts[1]
        for x in range(256):
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0
            lut[x] = max(0, min(255, round(y0 + (y1 - y0) * t)))
        return lut
    b, c, d = _natural_cubic_spline_coeffs(xs, ys)
    seg = 0
    for x in range(256):
        while seg < n - 2 and x > xs[seg + 1]:
            seg += 1
        dx = x - xs[seg]
        y = ys[seg] + b[seg] * dx + c[seg] * dx ** 2 + d[seg] * dx ** 3
        lut[x] = max(0, min(255, round(y)))
    return lut


def apply_curve_to_image(pil_img, points):
    """[v05] 커브(전 채널 공통 LUT)를 PIL 이미지에 적용해 새 이미지를 반환."""
    if points == [(0, 0), (255, 255)]:
        return pil_img
    lut = build_lut(points)
    if pil_img.mode == "RGBA":
        r, g, b, a = pil_img.split()
        r, g, b = r.point(lut), g.point(lut), b.point(lut)
        return Image.merge("RGBA", (r, g, b, a))
    rgb = pil_img.convert("RGB")
    r, g, b = rgb.split()
    r, g, b = r.point(lut), g.point(lut), b.point(lut)
    return Image.merge("RGB", (r, g, b))


class CropCanvas(QWidget):
    """[v05] 이미지 미리보기 + 크롭 영역 지정(마우스 드래그) 위젯.
    - 테두리: 점선 / 꼭짓점: 작은 원형 핸들 (계획서 3.2 확정 스펙)
    - 영역 밖은 어둡게 처리
    """
    cropChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        # [v12] 커스텀 paintEvent를 가진 QWidget은 이 속성이 없으면 스타일시트의
        # background-color/border가 그려지지 않는다(테두리 미적용 버그의 원인).
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color:{C.IMGEDIT_BG};border-radius:6px;")
        self.pil_img = None
        self.qpix = None
        self.img_rect = QRect()          # 위젯 좌표계에서 이미지가 그려지는 영역
        self.crop_rect = None            # 원본 이미지 좌표계 (x0,y0,x1,y1)
        self.ratio = RATIO_KEYS[0]
        self.curve_points = [(0, 0), (255, 255)]  # [v05] 현재 화면에 실시간 반영할 커브
        self.view_mode = "edit"          # [v05] "edit"(크롭 지정) / "preview"(적용 결과로 화면 채움)
        self._drag_mode = None           # None / "new" / "move" / handle index(0~3)
        self._drag_start = None
        self._drag_rect0 = None
        # [v49.1] 확대/축소 — zoom은 "화면에 맞춤" 크기에 대한 배율(1.0 = 맞춤).
        # view_center는 화면 가운데에 오는 원본 이미지 좌표(창 크기가 바뀌어도
        # 같은 곳을 보도록 원본 좌표로 기억한다).
        self.zoom = 1.0
        self.view_center = None
        self._fit_scale = 1.0
        self._disp_img = None            # 커브까지 반영한 화면용 이미지(원본 크기)
        self._full_qpix = None           # 확대했을 때 쓰는 원본 해상도 픽스맵(필요할 때 만든다)
        self._pan_last = None            # 가운데 버튼으로 끌어 옮기는 중의 마지막 위치
        self.setToolTip(tr("imgedit.zoom.tip"))

    # ---------- 외부 API ----------
    def set_image(self, pil_img, crop_rect=None, ratio=RATIO_KEYS[0], curve_points=None):
        """편집 모드: 원본 이미지 + 크롭 오버레이(점선/원형 핸들)를 보여준다.
        [v05] curve_points를 넘기면 밝기 커브 효과를 화면에 바로 반영한다(실제 밝아지고
        어두워지는 효과가 즉시 보이도록)."""
        self.view_mode = "edit"
        self.pil_img = pil_img
        self.ratio = ratio
        self.crop_rect = crop_rect if crop_rect else None
        self.curve_points = curve_points if curve_points else [(0, 0), (255, 255)]
        self._reset_zoom()
        self._recompute_layout()
        self.update()

    def set_preview_image(self, pil_img):
        """[v05] 적용 결과 미리보기: 크롭+커브가 이미 반영된 최종 이미지로 화면 뷰를
        가득 채우고, 크롭 오버레이는 표시하지 않는다. 클릭하면 다시 편집 모드로 전환."""
        self.view_mode = "preview"
        self.pil_img = pil_img
        self.crop_rect = None
        self.curve_points = [(0, 0), (255, 255)]  # 이미 baked된 이미지이므로 추가 적용 안 함
        self._reset_zoom()
        self._recompute_layout()
        self.update()

    def set_curve(self, points):
        """[v05] 커브 팝오버에서 값이 바뀔 때 화면에 즉시 반영(라이브 프리뷰)."""
        self.curve_points = points if points else [(0, 0), (255, 255)]
        self._recompute_layout()
        self.update()

    def set_ratio(self, ratio):
        self.ratio = ratio

    def get_crop_rect(self):
        return self.crop_rect

    # ---------- 좌표 변환 ----------
    def _recompute_layout(self):
        if not self.pil_img:
            self.img_rect = QRect()
            return
        iw, ih = self.pil_img.size
        w, h = max(1, self.width() - 16), max(1, self.height() - 16)
        scale = min(w / iw, h / ih)
        self._fit_scale = scale
        dw, dh = max(1, int(iw * scale)), max(1, int(ih * scale))
        disp_img = self.pil_img
        if self.curve_points and self.curve_points != [(0, 0), (255, 255)]:
            disp_img = apply_curve_to_image(disp_img, self.curve_points)
        self._disp_img = disp_img
        self._full_qpix = None
        self._update_geometry()
        img = disp_img.convert("RGB") if disp_img.mode not in ("RGB", "RGBA") else disp_img
        qimg = QImage(img.tobytes(), img.width, img.height,
                       img.width * (4 if img.mode == "RGBA" else 3),
                       QImage.Format_RGBA8888 if img.mode == "RGBA" else QImage.Format_RGB888)
        # [버그 수정] 화질이 4000x3000 원본인데도 계단 현상이 보일 만큼
        # 저해상도로 보이던 원인 — 고해상도(DPI 확대) 모니터에서
        # devicePixelRatio를 전혀 고려하지 않고 있었다. 위젯의 "논리
        # 픽셀" 크기(dw, dh)만큼만 QPixmap을 만들어 두면, 150% 배율
        # 모니터에서는 그 화면에 실제로 필요한 물리 픽셀 수(dw*1.5,
        # dh*1.5)보다 훨씬 적은 픽셀로 그려지고, Qt가 화면에 낼 때 그걸
        # 다시 늘려 그리면서 원본 해상도와 무관하게 뭉개져 보인다.
        # devicePixelRatio만큼 더 큰 픽셀맵을 만들고 setDevicePixelRatio로
        # "이건 그만큼 배율이 적용된 그림"이라고 알려주면, Qt가 그
        # 배율을 감안해서 선명하게 그린다.
        dpr = self.devicePixelRatioF()
        self.qpix = QPixmap.fromImage(qimg).scaled(
            max(1, round(dw * dpr)), max(1, round(dh * dpr)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.qpix.setDevicePixelRatio(dpr)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recompute_layout()

    # ---------- [v49.1] 확대/축소 ----------
    def _reset_zoom(self):
        self.zoom = 1.0
        self.view_center = None
        self._pan_last = None

    def max_zoom(self):
        """원본 한 픽셀이 화면에서 ZOOM_MAX_PIXEL배(논리 픽셀)까지 커질 때까지."""
        return max(1.0, ZOOM_MAX_PIXEL / max(1e-6, self._fit_scale))

    def _update_geometry(self):
        """zoom·view_center로 img_rect(위젯 좌표의 이미지 영역)를 정한다.
        이미지가 창보다 작은 방향은 가운데에 두고, 큰 방향은 빈 곳이 생기지
        않게 가장자리를 막는다. 크롭 좌표 변환은 모두 img_rect를 쓰므로
        확대한 상태에서도 크롭이 그대로 동작한다."""
        if not self.pil_img:
            self.img_rect = QRect()
            return
        iw, ih = self.pil_img.size
        s = self._fit_scale * self.zoom
        dw, dh = max(1, int(round(iw * s))), max(1, int(round(ih * s)))
        if self.view_center is None:
            self.view_center = (iw / 2, ih / 2)
        cx, cy = self.view_center
        W, H = self.width(), self.height()

        def place(size, view, center):
            if size <= view - 16:
                return (view - size) // 2
            pos = int(round(view / 2 - center * s))
            return max(view - 8 - size, min(8, pos))

        x, y = place(dw, W, cx), place(dh, H, cy)
        self.img_rect = QRect(x, y, dw, dh)
        # 막혀서 실제로 보이는 가운데로 view_center를 맞춰 둔다(다음 확대의 기준)
        self.view_center = ((W / 2 - x) / s, (H / 2 - y) / s)

    def zoom_percent(self):
        if not self.pil_img:
            return 100
        return int(round(self._fit_scale * self.zoom * 100))

    def set_zoom(self, zoom, anchor=None):
        """zoom 배율로 바꾼다. anchor(위젯 좌표)를 주면 그 아래의 이미지 지점이
        확대/축소 뒤에도 같은 자리에 머문다(마우스 커서 기준 확대)."""
        if not self.pil_img:
            return
        zoom = max(1.0, min(self.max_zoom(), zoom))
        if anchor is not None and not self.img_rect.isEmpty():
            ax, ay = anchor
            s0 = self._fit_scale * self.zoom
            px, py = (ax - self.img_rect.x()) / s0, (ay - self.img_rect.y()) / s0
            s1 = self._fit_scale * zoom
            W, H = self.width(), self.height()
            self.view_center = (px + (W / 2 - ax) / s1, py + (H / 2 - ay) / s1)
        self.zoom = zoom
        if zoom == 1.0:
            self.view_center = None
        self._update_geometry()
        self.update()

    def pan_by(self, dx, dy):
        """화면을 위젯 픽셀 단위로 옮긴다(확대한 상태에서만 의미가 있다)."""
        if not self.pil_img or self.zoom <= 1.0:
            return
        s = self._fit_scale * self.zoom
        cx, cy = self.view_center
        self.view_center = (cx - dx / s, cy - dy / s)
        self._update_geometry()
        self.update()

    def wheelEvent(self, e):
        """Ctrl+휠: 마우스 위치를 기준으로 확대/축소.
        확대한 상태에서 그냥 휠은 위아래, Shift+휠은 좌우로 옮긴다."""
        if not self.pil_img:
            return super().wheelEvent(e)
        delta = e.angleDelta().y() or e.angleDelta().x()
        if e.modifiers() & Qt.ControlModifier:
            if delta:
                steps = delta / 120.0
                pos = e.position()
                self.set_zoom(self.zoom * (ZOOM_STEP ** steps), anchor=(pos.x(), pos.y()))
            e.accept()
            return
        if self.zoom > 1.0 and delta:
            if e.modifiers() & Qt.ShiftModifier:
                self.pan_by(delta / 2, 0)
            else:
                self.pan_by(e.angleDelta().x() / 2, e.angleDelta().y() / 2)
            e.accept()
            return
        super().wheelEvent(e)

    def mouseDoubleClickEvent(self, e):
        """가운데 버튼 두 번 클릭 → 화면에 맞춤으로 되돌리기."""
        if e.button() == Qt.MiddleButton:
            self.set_zoom(1.0)
            return
        super().mouseDoubleClickEvent(e)

    def _ensure_full_qpix(self):
        if self._full_qpix is None and self._disp_img is not None:
            img = self._disp_img
            img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
            qimg = QImage(img.tobytes(), img.width, img.height,
                          img.width * (4 if img.mode == "RGBA" else 3),
                          QImage.Format_RGBA8888 if img.mode == "RGBA" else QImage.Format_RGB888)
            self._full_qpix = QPixmap.fromImage(qimg)
        return self._full_qpix

    def _to_widget(self, ox, oy):
        if not self.pil_img or self.img_rect.isEmpty():
            return QPointF(0, 0)
        iw, ih = self.pil_img.size
        sx = self.img_rect.width() / iw
        sy = self.img_rect.height() / ih
        return QPointF(self.img_rect.x() + ox * sx, self.img_rect.y() + oy * sy)

    def _to_orig(self, wx, wy):
        iw, ih = self.pil_img.size
        sx = self.img_rect.width() / iw
        sy = self.img_rect.height() / ih
        ox = (wx - self.img_rect.x()) / sx
        oy = (wy - self.img_rect.y()) / sy
        return max(0, min(iw, ox)), max(0, min(ih, oy))

    def _aspect(self):
        if self.ratio == "1:1":
            return 1.0
        if self.ratio == "4:3":
            return 4 / 3
        if self.ratio == "16:9":
            return 16 / 9
        if self.ratio == "original" and self.pil_img:
            iw, ih = self.pil_img.size
            return iw / ih
        return None  # "free"

    def _handle_points(self):
        if not self.crop_rect:
            return []
        x0, y0, x1, y1 = self.crop_rect
        pts = [self._to_widget(x0, y0), self._to_widget(x1, y0),
               self._to_widget(x1, y1), self._to_widget(x0, y1)]
        return pts

    # ---------- 마우스 이벤트 ----------
    def mousePressEvent(self, e):
        if self.pil_img and e.button() == Qt.MiddleButton:
            pos = e.position() if hasattr(e, "position") else e.pos()
            self._pan_last = (pos.x(), pos.y())
            self.setCursor(Qt.ClosedHandCursor)
            return
        if not self.pil_img or e.button() != Qt.LeftButton:
            return
        # [v12] 이전에는 preview(적용 결과) 상태에서 클릭하면 원본 편집 화면으로
        # 되돌아갔는데, "크롭한 이미지를 유지한 채 그 위에 다시 크롭"을 원한다는
        # 피드백에 따라 제거했다. preview 상태에서도 그냥 그대로 드래그해서 새
        # 크롭 영역을 그릴 수 있다(아래 로직은 view_mode와 무관하게 동일하게 동작).
        pos = e.position() if hasattr(e, "position") else e.pos()
        wx, wy = pos.x(), pos.y()
        for i, p in enumerate(self._handle_points()):
            if abs(p.x() - wx) <= EDGE_TOL and abs(p.y() - wy) <= EDGE_TOL:
                self._drag_mode = i
                self._drag_rect0 = self.crop_rect
                return
        if self.crop_rect:
            x0, y0 = self._to_widget(self.crop_rect[0], self.crop_rect[1]).toTuple()
            x1, y1 = self._to_widget(self.crop_rect[2], self.crop_rect[3]).toTuple()
            if x0 <= wx <= x1 and y0 <= wy <= y1:
                self._drag_mode = "move"
                self._drag_start = self._to_orig(wx, wy)
                self._drag_rect0 = self.crop_rect
                return
        ox, oy = self._to_orig(wx, wy)
        self._drag_mode = "new"
        self._drag_start = (ox, oy)
        self.crop_rect = (ox, oy, ox, oy)

    def mouseMoveEvent(self, e):
        if self._pan_last is not None:
            pos = e.position() if hasattr(e, "position") else e.pos()
            lx, ly = self._pan_last
            self._pan_last = (pos.x(), pos.y())
            self.pan_by(pos.x() - lx, pos.y() - ly)
            return
        if not self.pil_img or self._drag_mode is None:
            return
        pos = e.position() if hasattr(e, "position") else e.pos()
        ox, oy = self._to_orig(pos.x(), pos.y())
        aspect = self._aspect()

        if self._drag_mode == "new":
            sx, sy = self._drag_start
            if aspect:
                w = ox - sx
                h = w / aspect if aspect else (oy - sy)
                self.crop_rect = (sx, sy, sx + w, sy + h)
            else:
                self.crop_rect = (sx, sy, ox, oy)
        elif self._drag_mode == "move":
            sx, sy = self._drag_start
            x0, y0, x1, y1 = self._drag_rect0
            dx, dy = ox - sx, oy - sy
            iw, ih = self.pil_img.size
            w, h = x1 - x0, y1 - y0
            nx0 = max(0, min(iw - w, x0 + dx))
            ny0 = max(0, min(ih - h, y0 + dy))
            self.crop_rect = (nx0, ny0, nx0 + w, ny0 + h)
        elif isinstance(self._drag_mode, int):
            x0, y0, x1, y1 = self._drag_rect0
            corner = self._drag_mode
            if corner == 0:
                x0, y0 = ox, oy
            elif corner == 1:
                x1, y0 = ox, oy
            elif corner == 2:
                x1, y1 = ox, oy
            elif corner == 3:
                x0, y1 = ox, oy
            if aspect:
                w = abs(x1 - x0)
                h = w / aspect
                if corner in (0, 1):
                    # [v50] 위쪽 꼭짓점(0=좌상단/1=우상단)을 드래그하는 중이므로
                    # 지금 막 옮긴 y0가 아니라, 안 건드린 아래쪽 y1이 고정 기준점이어야
                    # 한다. 예전에는 corner와 무관하게 항상 "y1 = y0 ± h"로 계산해서
                    # 위쪽 꼭짓점을 드래그해도 고정되어 있어야 할 아래쪽 변(y1 — 즉
                    # 반대편 두 꼭짓점이 공유하는 좌표)이 함께 움직여 버렸다. 그중에서도
                    # 가로축(x0 또는 x1)까지 같이 움직이는 대각선 반대쪽 꼭짓점(우상단을
                    # 끌 때의 좌하단, 좌상단을 끌 때의 우하단)은 가만히 있어야 정상인데
                    # y좌표가 딸려 움직여서 유독 눈에 띄게 이상해 보였다.
                    y0 = y1 - h if y1 >= y0 else y1 + h
                else:
                    # 아래쪽 꼭짓점(2=우하단/3=좌하단)을 드래그하는 중 — 위쪽 y0가
                    # 고정 기준점이므로 그대로 두고 y1만 다시 계산한다(기존 방식).
                    y1 = y0 + h if y1 >= y0 else y0 - h
            self.crop_rect = (x0, y0, x1, y1)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            return
        if self._drag_mode is not None and self.crop_rect:
            x0, y0, x1, y1 = self.crop_rect
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            if x1 - x0 < 10 or y1 - y0 < 10:
                self.crop_rect = None
            else:
                self.crop_rect = (x0, y0, x1, y1)
            self.cropChanged.emit()
        self._drag_mode = None
        self.update()

    # ---------- 그리기 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.zoom > 1.0 and self.pil_img and not self.img_rect.isEmpty():
            # [v49.1] 확대 중 — 원본 해상도 픽스맵에서 화면에 보이는 부분만 잘라 그린다
            # (확대한 크기만큼 거대한 픽스맵을 만들지 않으려고).
            full = self._ensure_full_qpix()
            vis = self.img_rect.intersected(self.rect())
            s = self._fit_scale * self.zoom
            src = QRectF((vis.x() - self.img_rect.x()) / s, (vis.y() - self.img_rect.y()) / s,
                         vis.width() / s, vis.height() / s)
            p.setRenderHint(QPainter.SmoothPixmapTransform, s < 2.0)
            p.drawPixmap(QRectF(vis), full, src)
        elif self.qpix and not self.img_rect.isEmpty():
            p.drawPixmap(self.img_rect, self.qpix)
        if self.crop_rect and self.pil_img:
            x0, y0 = self._to_widget(self.crop_rect[0], self.crop_rect[1]).toTuple()
            x1, y1 = self._to_widget(self.crop_rect[2], self.crop_rect[3]).toTuple()
            crop_w = QRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
            # 영역 밖 어둡게
            dim = QColor(0, 0, 0, 110)
            p.fillRect(QRect(self.img_rect.left(), self.img_rect.top(), self.img_rect.width(), max(0, crop_w.top() - self.img_rect.top())), dim)
            p.fillRect(QRect(self.img_rect.left(), crop_w.bottom(), self.img_rect.width(), max(0, self.img_rect.bottom() - crop_w.bottom())), dim)
            p.fillRect(QRect(self.img_rect.left(), crop_w.top(), max(0, crop_w.left() - self.img_rect.left()), crop_w.height()), dim)
            p.fillRect(QRect(crop_w.right(), crop_w.top(), max(0, self.img_rect.right() - crop_w.right()), crop_w.height()), dim)
            # 점선 테두리
            pen = QPen(QColor(C.CROP_LINE))
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(crop_w)
            # 꼭짓점 원형 핸들
            p.setPen(QPen(QColor(C.CROP_LINE), 1.5))
            p.setBrush(QBrush(QColor(C.CROP_HANDLE_FILL)))
            for pt in self._handle_points():
                p.drawEllipse(pt, HANDLE_R, HANDLE_R)
        if self.view_mode == "preview" and self.pil_img and not self.crop_rect:
            p.setPen(QPen(QColor("#ffffff")))
            p.setBrush(QBrush(QColor(0, 0, 0, 140)))
            hint = tr("imgedit.crop_reapply_hint")
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(hint)
            pad = 6
            box = QRect(self.img_rect.left() + 8, self.img_rect.bottom() - 26, tw + pad * 2, 20)
            p.drawRoundedRect(box, 4, 4)
            p.drawText(box, Qt.AlignCenter, hint)
        if self.zoom > 1.0 and self.pil_img:
            # [v49.1] 확대 배율 표시(왼쪽 위)
            text = tr("imgedit.zoom.badge", a0=self.zoom_percent())
            fm = p.fontMetrics()
            box = QRect(10, 10, fm.horizontalAdvance(text) + 14, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 150)))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QPen(QColor("#ffffff")))
            p.drawText(box, Qt.AlignCenter, text)
        p.end()


class CurvePopover(QWidget):
    """[v05] 레이어 커브 편집 팝오버 — 미리보기 우측 상단에 표시, 적용 시 자동으로 사라짐(계획서 3.4).
    [v50] Qt.Popup 창은 바깥(예: 크롭 캔버스)을 클릭하거나 Esc를 누르면 자동으로
    닫히는데, 예전에는 "적용" 버튼/Space를 눌러야만 조정한 커브가 확정되고
    그 외의 방식으로 닫히면 조정 내용이 그냥 버려졌다. 그래서 커브를 만지다가
    바로 이어서 크롭 영역을 클릭/드래그하려고 하면(그 클릭이 팝오버를 닫히게
    만듦) 방금 만진 커브가 사라지는 것처럼 보이는 문제가 있었다. 이제는 어떤
    방식으로 닫히든(적용 버튼/Space/바깥 클릭/Esc) 그 시점의 커브 값을 그대로
    확정한다 — 다만 애초에 아무것도 바꾸지 않고 열었다 닫은 경우까지 "적용됨"
    으로 처리하지 않도록, 처음 열었을 때와 값이 달라졌을 때만 확정한다."""
    curveApplied = Signal(list)
    curveChanged = Signal(list)  # [v05] 드래그 중 실시간 미리보기용

    GRAPH = 200
    PAD = 16

    def __init__(self, points, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.points = list(points) if points else [(0, 0), (255, 255)]
        self._initial_points = list(self.points)  # [v50] 변경 여부 판별 기준
        self._drag_idx = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)
        self.graph = QWidget()
        self.graph.setFixedSize(self.GRAPH + self.PAD * 2, self.GRAPH + self.PAD * 2)
        self.graph.paintEvent = self._paint_graph
        self.graph.mousePressEvent = self._graph_press
        self.graph.mouseMoveEvent = self._graph_move
        self.graph.mouseReleaseEvent = self._graph_release
        outer.addWidget(self.graph)
        hint = QLabel(tr("imgedit.curve_hint"))
        hint.setStyleSheet("color:#666666;font-size:11px;")
        outer.addWidget(hint)
        btn_row = QHBoxLayout()
        btn_reset = QPushButton(tr("imgedit.curve_reset"))
        btn_apply = QPushButton(tr("label.apply"))
        btn_apply.setToolTip("Space")
        btn_apply.setStyleSheet(f"background-color:{C.IMGEDIT_MAIN};color:#fff;font-weight:bold;border-radius:5px;padding:4px 12px;")
        btn_reset.clicked.connect(self._reset)
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_row.addWidget(btn_apply)
        # [v15] 메인 이미지 편집 화면과 동일하게, 팝오버 안에서도 Space로 적용할 수 있게
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._apply,
                  context=Qt.WidgetWithChildrenShortcut)
        outer.addLayout(btn_row)
        self.setStyleSheet("background-color:#ffffff;border:1px solid #c4c9d0;border-radius:8px;")

    def _pt_to_widget(self, x, y):
        gx = self.PAD + (x / 255) * self.GRAPH
        gy = self.PAD + self.GRAPH - (y / 255) * self.GRAPH
        return QPointF(gx, gy)

    def _widget_to_pt(self, wx, wy):
        x = (wx - self.PAD) / self.GRAPH * 255
        y = (self.GRAPH - (wy - self.PAD)) / self.GRAPH * 255
        return max(0, min(255, round(x))), max(0, min(255, round(y)))

    def _paint_graph(self, e):
        p = QPainter(self.graph)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.graph.rect(), QColor("#f4f5f7"))
        p.setPen(QPen(QColor("#d5d8dd"), 1))
        for i in range(1, 4):
            gx = self.PAD + self.GRAPH * i / 4
            gy = self.PAD + self.GRAPH * i / 4
            p.drawLine(int(gx), self.PAD, int(gx), self.PAD + self.GRAPH)
            p.drawLine(self.PAD, int(gy), self.PAD + self.GRAPH, int(gy))
        p.setPen(QPen(QColor(C.IMGEDIT_MAIN), 2))
        pts = sorted(self.points, key=lambda pt: pt[0])
        lut = build_lut(pts)
        path_pts = [self._pt_to_widget(x, lut[x]) for x in range(0, 256, 3)]
        path_pts.append(self._pt_to_widget(255, lut[255]))
        for i in range(len(path_pts) - 1):
            p.drawLine(path_pts[i], path_pts[i + 1])
        p.setBrush(QBrush(QColor(C.IMGEDIT_MAIN)))
        for pt in pts:
            p.drawEllipse(self._pt_to_widget(*pt), 4, 4)
        p.end()

    def _nearest_point_idx(self, wx, wy):
        for i, pt in enumerate(self.points):
            wp = self._pt_to_widget(*pt)
            if abs(wp.x() - wx) <= 6 and abs(wp.y() - wy) <= 6:
                return i
        return None

    def _graph_press(self, e):
        wx, wy = e.position().x(), e.position().y()
        idx = self._nearest_point_idx(wx, wy)
        if e.button() == Qt.RightButton:
            if idx is not None and 0 < self.points[idx][0] < 255:
                self.points.pop(idx)
                self.graph.update()
                self.curveChanged.emit(list(self.points))
            return
        if idx is not None:
            self._drag_idx = idx
        else:
            x, y = self._widget_to_pt(wx, wy)
            self.points.append((x, y))
            self._drag_idx = len(self.points) - 1
        self.graph.update()
        self.curveChanged.emit(list(self.points))

    def _graph_move(self, e):
        if self._drag_idx is None:
            return
        x, y = self._widget_to_pt(e.position().x(), e.position().y())
        if self.points[self._drag_idx][0] in (0, 255) and x not in (0, 255):
            x = self.points[self._drag_idx][0]  # 양끝 포인트는 x 고정, y만 이동
        self.points[self._drag_idx] = (x, y)
        self.graph.update()
        self.curveChanged.emit(list(self.points))  # [v05] 드래그 중 실시간 반영(대각선 위=밝게/아래=어둡게)

    def _graph_release(self, e):
        self._drag_idx = None

    def _reset(self):
        self.points = [(0, 0), (255, 255)]
        self.graph.update()
        self.curveChanged.emit(list(self.points))

    def _apply(self):
        self.close()

    def closeEvent(self, event):
        """[v50] 팝오버가 닫히는 모든 경로(적용 버튼/Space/바깥 클릭/Esc)를
        여기 한 곳에서 처리한다 — 열었을 때와 비교해 실제로 값이 바뀐
        경우에만 확정 신호를 보낸다(아무것도 안 바꾸고 닫았을 때 괜히
        "적용됨" 배지가 붙는 것을 방지)."""
        if self.points != self._initial_points:
            self.curveApplied.emit(list(self.points))
        super().closeEvent(event)


def make_mode_icon(kind, color):
    """[v10] 모드 전환 세그먼트 버튼용 아이콘. 네 모드 모두 같은 스타일
    (색상 원형 배지 + 흰색 글리프)로 통일해 룩앤필 일관성을 맞춘다."""
    SIZE = 24
    pix = QPixmap(SIZE, SIZE)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # 배지 배경(모드 강조색으로 꽉 채운 원) — 모든 아이콘이 이 위에서 시작
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawEllipse(1, 1, SIZE - 2, SIZE - 2)

    pen = QPen(QColor("#ffffff"), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "sync":
        # [v11] 앱 아이콘(폴더 + 좌우 동기화 화살표)과 같은 모티브를 배지 스타일로 재해석
        folder = QPolygonF([
            QPointF(4, 8), QPointF(9, 8), QPointF(10.3, 9.4),
            QPointF(20, 9.4), QPointF(20, 19), QPointF(4, 19),
        ])
        p.drawPolygon(folder)
        p.drawLine(QPointF(7, 12.3), QPointF(14.5, 12.3))
        p.drawLine(QPointF(9.5, 16.7), QPointF(17, 16.7))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(14.5, 10.3), QPointF(17.5, 12.3), QPointF(14.5, 14.3)]))
        p.drawPolygon(QPolygonF([QPointF(9.5, 14.7), QPointF(6.5, 16.7), QPointF(9.5, 18.7)]))
    elif kind == "rename":
        # [v33] 연필 + 지우개 아이콘 — 대각선으로 기울인 연필 몸통 끝에 사각
        # 지우개를 붙여 "이름을 쓰고 지운다"는 의미가 한눈에 들어오게 한다
        # (기존 아이콘이 무엇을 그린 건지 알아보기 어렵다는 의견 반영).
        p.save()
        p.translate(SIZE / 2, SIZE / 2)
        p.rotate(-45)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(-9, 0), QPointF(-6, -1.8), QPointF(-6, 1.8)]))  # 연필 촉
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(-6, -1.8, 9, 3.6))  # 연필 몸통
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(3, -2.1, 3.6, 4.2), 1, 1)  # 지우개
        p.restore()
    elif kind == "imgedit":
        p.drawRoundedRect(5, 6, 14, 12, 2, 2)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(9.2, 10.2), 1.3, 1.3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(6.5, 16), QPointF(10.5, 11.5))
        p.drawLine(QPointF(10.5, 11.5), QPointF(13, 14))
        p.drawLine(QPointF(13, 14), QPointF(15.5, 11))
        p.drawLine(QPointF(15.5, 11), QPointF(17.5, 16))
    elif kind == "dupfind":
        # 겹쳐진 문서 2장 — 내용이 같은 파일을 찾는다는 의미
        p.drawRoundedRect(5, 7, 10, 11, 2, 2)
        p.drawRoundedRect(9, 5, 10, 11, 2, 2)
    elif kind == "util":
        # [버그 수정] 예전에는 2x2로 똑같이 생긴 작은 사각형 4개였는데,
        # 서로 다른 도구가 모여 있다는 느낌이 더 잘 살도록 네 칸을 각각
        # 다른 모양(X·삼각형·사각형·원)으로 바꿨다. 크기도 이전보다
        # 살짝 키웠다. 도구 하나를 콕 집어 상징하지 않는 중립적인 조합은
        # 그대로 유지한다(특정 도구 아이콘을 쓰면 도구가 늘어날 때 뜻이
        # 안 맞아진다).
        white_pen = QPen(QColor("#ffffff"), 1.9)
        white_pen.setCapStyle(Qt.RoundCap)
        white_pen.setJoinStyle(Qt.RoundJoin)

        # 좌상단: X — [버그 수정] 대각선으로 뻗는 모양이라 사각형과 같은
        # bounding box를 써도 훨씬 커 보였다("모서리까지 뻗는 대각선" 대
        # "네 변으로 둘러싸인 면"의 차이). 사각형과 비슷한 크기로 보이도록
        # 한 변(6.6) 대신 살짝 줄인 5.2로 좁혔다(중심은 그대로 (8,8)).
        p.setPen(white_pen)
        p.drawLine(QPointF(5.4, 5.4), QPointF(10.6, 10.6))
        p.drawLine(QPointF(10.6, 5.4), QPointF(5.4, 10.6))

        # 우상단: 정삼각형(위 꼭짓점)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        tri = QPolygonF([QPointF(15.8, 4.6), QPointF(19.3, 11.1), QPointF(12.3, 11.1)])
        p.drawPolygon(tri)

        # 좌하단: 사각형(기존 모양 유지, 살짝 확대)
        p.drawRoundedRect(QRectF(4.9, 12.6, 6.6, 6.6), 1.3, 1.3)

        # 우하단: 원
        p.drawEllipse(QRectF(12.5, 12.6, 6.6, 6.6))
    elif kind == "settings":
        # [v24] 환경 설정 — 톱니바퀴. 흰색 이빨(8개)+몸통을 그리고, 가운데
        # 구멍은 배지 배경색(=버튼 배경색)으로 다시 채워 도넛 모양을 낸다.
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        cx, cy = SIZE / 2, SIZE / 2
        p.translate(cx, cy)
        for i in range(8):
            p.save()
            p.rotate(i * 45)
            p.drawRoundedRect(QRectF(-1.3, -7.6, 2.6, 3.0), 0.8, 0.8)
            p.restore()
        p.drawEllipse(QPointF(0, 0), 4.6, 4.6)
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(QPointF(0, 0), 2.3, 2.3)
        p.translate(-cx, -cy)

    p.end()
    return QIcon(pix)


# [v47] 즐겨찾기 바로가기 콤보박스용 작은 아이콘 — 윈도우 탐색기의 바탕화면/
# 다운로드/문서/사진/음악/동영상 폴더 아이콘과 "똑같지는 않아도 비슷한 느낌"이
# 나도록, 색이 있는 작은 폴더 실루엣 위에 흰색 글리프를 얹는 방식으로 통일했다.
QUICKLINK_ICON_COLORS = {
    "desktop": "#5b6178",
    "downloads": "#2e9e44",
    "documents": "#2196F3",
    "pictures": "#f39c12",
    "music": "#9b59b6",
    "videos": "#e74c3c",
}


def make_quicklink_icon(kind):
    SIZE = 18
    pix = QPixmap(SIZE, SIZE)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    color = QUICKLINK_ICON_COLORS.get(kind, "#8e97b8")
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    folder = QPolygonF([
        QPointF(2, 5), QPointF(7.2, 5), QPointF(8.6, 6.6),
        QPointF(16, 6.6), QPointF(16, 15.3), QPointF(2, 15.3),
    ])
    p.drawPolygon(folder)

    pen = QPen(QColor("#ffffff"), 1.3)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "desktop":
        # 모니터 + 받침대
        p.drawRect(QRectF(5.6, 9.0, 6.8, 4.4))
        p.drawLine(QPointF(7.4, 13.4), QPointF(7.4, 14.4))
        p.drawLine(QPointF(11.0, 13.4), QPointF(11.0, 14.4))
        p.drawLine(QPointF(6.4, 14.4), QPointF(11.6, 14.4))
    elif kind == "downloads":
        # 아래로 향하는 화살표 + 받침선
        p.drawLine(QPointF(9, 8.2), QPointF(9, 12.6))
        p.drawLine(QPointF(9, 12.6), QPointF(6.9, 10.6))
        p.drawLine(QPointF(9, 12.6), QPointF(11.1, 10.6))
        p.drawLine(QPointF(6.3, 14.1), QPointF(11.7, 14.1))
    elif kind == "documents":
        # 문서 줄 3개
        p.drawLine(QPointF(6.2, 9.1), QPointF(11.8, 9.1))
        p.drawLine(QPointF(6.2, 11.3), QPointF(11.8, 11.3))
        p.drawLine(QPointF(6.2, 13.5), QPointF(9.7, 13.5))
    elif kind == "pictures":
        # 사진: 해 + 산
        p.drawRoundedRect(QRectF(5.6, 8.6, 6.8, 5.6), 1, 1)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(7.2, 10.4), 0.75, 0.75)
        p.drawPolygon(QPolygonF([
            QPointF(6.0, 13.7), QPointF(8.2, 10.9), QPointF(9.7, 12.6),
            QPointF(10.8, 11.3), QPointF(12.0, 13.7),
        ]))
    elif kind == "music":
        # 8분음표 2개
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(7.0, 13.2), 1.1, 1.1)
        p.drawEllipse(QPointF(10.9, 12.4), 1.1, 1.1)
        p.setPen(pen)
        p.drawLine(QPointF(8.1, 13.2), QPointF(8.1, 8.6))
        p.drawLine(QPointF(12.0, 12.4), QPointF(12.0, 7.9))
        p.drawLine(QPointF(8.1, 8.6), QPointF(12.0, 7.9))
    elif kind == "videos":
        # 재생 삼각형
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(7.2, 8.8), QPointF(7.2, 14.0), QPointF(11.8, 11.4),
        ]))

    p.end()
    return QIcon(pix)


# =============================================================================
# 7. 메인 윈도우
# =============================================================================
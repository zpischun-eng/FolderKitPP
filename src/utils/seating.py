# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: 좌석표 [v40]

학급별로 줄(분단) 수를 고르면 무작위 좌석 배치를 만든다. 명단 형식·
저장 방식은 대진표 작성기와 같은 것을 그대로 재사용한다(신규 미니앱
개발 스펙 문서의 1번 항목, 1차 범위) — 고정석 지정, 짝 금지, 이전
배치 반복 회피 같은 2차 범위는 이번에는 넣지 않았다(범위 확정 필요).
"""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QFontMetrics, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea,
    QFileDialog, QMessageBox, QSpinBox, QMenu, QDialog, QCheckBox
)

from ..config import desktop_file
from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import bracket_solve as B
from . import seating_solve as S

_SET_ROSTER = "util.seating.roster"
_SET_SAVE_DIR = "util.seating.save_dir"
_SET_COLS = "util.seating.cols"
_SET_HEADCOUNT = "util.seating.headcount"

_SEAT_W, _SEAT_H = 96, 60
_SEAT_GAP = 10
_AISLE_EVERY = 0   # [2차 범위] 분단 사이 통로 폭을 넓게 두려면 여기에 넣으면 됨


class _SeatCanvas(QWidget):
    """좌석 그리드를 직접 그린다 — 아래가 교탁 쪽, 위가 교실 뒤쪽이다
    (실제 교실에서 칠판을 마주 보고 앉은 모습 그대로). seats[0]이 교탁과
    가장 가까운 줄(앞줄)이라는 데이터 순서는 그대로 두고, **그리는
    순서만** 아래에서 위로 뒤집는다.

    [v43.3] 칸을 클릭해서 자리를 서로 바꿀 수 있다 — 한 칸을 클릭하면
    선택(파란 테두리)되고, 이어서 다른 칸을 클릭하면 두 칸의 내용이
    맞바뀐다(빈 자리와 맞바꾸면 그 학생이 원하는 자리로, 빈 자리는
    원래 자리로 옮겨진다). 같은 칸을 다시 클릭하면 선택이 취소된다.

    [v43.8] 칸을 오른쪽 클릭하면 그 자리의 성별 구역(공석/여학생/
    남학생)을 바꾸는 메뉴가 뜬다 — 남학생 칸은 옅은 파랑, 여학생 칸은
    옅은 빨강, 공석은 빗금으로 표시한다."""

    cell_clicked = Signal(int, int)      # (row_index, col_index) — 왼쪽 클릭(자리 맞바꾸기)
    cell_right_clicked = Signal(int, int, object)   # (row_index, col_index, 화면 좌표 QPoint) — 오른쪽 클릭

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#ffffff;")
        self.chart = None
        self.roster_by_sid = {}
        self.selected_cell = None   # (row_index, col_index) 또는 None
        # [v44.4] 역할 보기 — 기본은 꺼져 있어 기존 화면 그대로다.
        # [v44.6] 칸 자체 크기는 켜고 끄는 것과 무관하게 항상 고정이다
        # (_SEAT_H) — 이전에는 켜면 칸이 더 높아지도록 했었는데, 그러면
        # 체크박스를 누를 때마다 전체 배치가 다시 흐르며(reflow) 화면이
        # "출렁이는" 느낌을 준다는 지적을 받았다. 이제는 고정된 칸 안에서
        # 번호·이름·역할 세 줄의 배치만 바뀐다(paintEvent 참고).
        self.show_role = False
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.NoContextMenu)   # 기본 컨텍스트메뉴 대신 mousePressEvent에서 직접 처리

    def set_chart(self, chart, roster_by_sid):
        self.chart = chart
        self.roster_by_sid = roster_by_sid
        self._relayout()
        self.update()

    def set_show_role(self, on):
        """[v44.4] "역할 보기" 체크박스와 연결. [v44.6] 칸 크기 자체는
        안 바뀌므로 다시 배치(_relayout)할 필요 없이 다시 그리기만 하면
        된다 — 스크롤 위치·전체 크기가 유지된다."""
        if self.show_role == on:
            return
        self.show_role = on
        self.update()

    def _relayout(self):
        if self.chart is None:
            self.setMinimumSize(200, 200)
            return
        w = self.chart.cols * (_SEAT_W + _SEAT_GAP) + _SEAT_GAP
        h = self.chart.rows * (_SEAT_H + _SEAT_GAP) + _SEAT_GAP + 46
        self.setMinimumSize(max(200, w), max(200, h))

    def _geometry(self):
        """지금 그려진 그리드의 기준 좌표들 — paintEvent와 mousePressEvent가
        똑같은 계산을 두 번 짜지 않도록 한 곳에 모아 둔다."""
        total_w = self.chart.cols * (_SEAT_W + _SEAT_GAP) + _SEAT_GAP
        x0 = max(_SEAT_GAP, (self.width() - total_w) / 2)
        n_rows = self.chart.rows
        grid_top = 10
        grid_bottom = grid_top + n_rows * (_SEAT_H + _SEAT_GAP) - _SEAT_GAP
        return x0, grid_top, grid_bottom, total_w

    def cell_rect(self, row_index, col_index):
        """row_index(데이터 순서, 0=앞줄)·col_index로 그 칸의 화면 사각형을
        구한다 — paintEvent가 실제로 그리는 자리와 정확히 같다."""
        x0, grid_top, grid_bottom, _total_w = self._geometry()
        y = grid_bottom - (row_index + 1) * _SEAT_H - row_index * _SEAT_GAP
        x = x0 + col_index * (_SEAT_W + _SEAT_GAP)
        return QRectF(x, y, _SEAT_W, _SEAT_H)

    def _cell_at(self, pos):
        if self.chart is None:
            return None
        for row_index in range(self.chart.rows):
            for col_index in range(self.chart.cols):
                if self.cell_rect(row_index, col_index).contains(pos):
                    return row_index, col_index
        return None

    def mousePressEvent(self, event):
        if self.chart is None:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        cell = self._cell_at(pos)
        if cell is None:
            return
        row_index, col_index = cell
        if event.button() == Qt.LeftButton:
            self.cell_clicked.emit(row_index, col_index)
        elif event.button() == Qt.RightButton:
            global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") \
                else event.globalPos()
            self.cell_right_clicked.emit(row_index, col_index, global_pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # [버그 수정] 글자(특히 작은 "번호" 글자)가 깨져 보이던 문제 —
        # 텍스트 안티앨리어싱을 명시적으로 켜지 않고 있었다(도형에만
        # Antialiasing을 켰었다). 고해상도(DPI 확대) 모니터일수록
        # 작은 한글 글자는 이게 없으면 계단 현상이 두드러진다. 인쇄도
        # 이 화면을 그대로 캡처해서 찍으므로 같은 문제가 그대로
        # 옮겨졌었다 — 여기 하나를 고치면 화면·인쇄 둘 다 해결된다.
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if self.chart is None:
            p.end()
            return

        x0, grid_top, grid_bottom, total_w = self._geometry()
        name_font = QFont("", 11)
        # [버그 수정 v44.6] "번호" 글자가 흐릿하게(뭉개져) 보인다는 지적 —
        # 옅은 회색(#6b7280)이 작은 글자에서 대비가 낮아 흐려 보이는
        # 영향이 컸다. 굵게(Bold)와 더 짙은 색(#4b5563)으로 바꿔 또렷하게
        # 보이도록 했다.
        # [버그 수정 v44.8] 그런데 그때 크기까지 10→11pt로 키우면서,
        # 번호를 그리는 칸(고정 13px 높이)보다 실제 글자가 더 커져
        # 버렸다 — Qt는 글자가 그리기 영역보다 크면 잘라내지 않고 그냥
        # 넘치게 그리므로, 번호 아래쪽이 곧바로 시작되는 이름 영역까지
        # 침범했고, **나중에 그려지는 이름 글자가 그 위에 덮어써져서**
        # 번호가 뭉개진 것처럼 보였다(요청하신 대로 크기는 이전인 10pt로
        # 되돌렸다). 재발을 막기 위해, 이제는 매직 넘버(13px) 대신
        # QFontMetrics로 이 폰트가 실제 필요로 하는 높이를 재서 번호
        # 영역과 이름 시작 위치를 정한다 — 폰트가 다시 바뀌어도 항상
        # 서로 안 겹친다.
        num_font = QFont("", 10)
        num_font.setBold(True)
        num_h = QFontMetrics(num_font).height() + 2
        # [v44.4] 역할 글자 — 이름보다 한 단계 작게, "역할 보기"가 켜져
        # 있을 때만 쓴다.
        role_font = QFont("", 9)
        # [v43.1] row_index 0(교탁과 가장 가까운 줄)을 화면 맨 아래에 그린다
        # — 그 위로 갈수록 뒷줄이 되어, "아래=교탁, 위=교실 뒤"가 된다.
        for row_index, row in enumerate(self.chart.seats):
            for col_index, sid in enumerate(row):
                rect = self.cell_rect(row_index, col_index)
                selected = self.selected_cell == (row_index, col_index)
                gender = self.chart.gender[row_index][col_index] if self.chart.gender else "M"
                is_vacant = gender == "vacant"
                # [v43.8] 자리 색 — 남학생 칸은 옅은 파랑, 여학생 칸은 옅은
                # 빨강, 공석은 빗금 무늬로 확실히 다르게 보이게 한다.
                if is_vacant:
                    fill = QColor("#e5e7eb")
                elif gender == "F":
                    fill = QColor("#fbe4e6" if not selected else "#f6c9cd")
                else:
                    fill = QColor("#dcebfb" if not selected else "#bfdcf7")
                if sid is None:
                    pen_color = C.UTIL_MAIN if selected else C.BORDER
                    p.setPen(QPen(QColor(pen_color), 2.4 if selected else 1, Qt.DashLine))
                else:
                    p.setPen(QPen(QColor(C.UTIL_MAIN), 2.4 if selected else 1))
                p.setBrush(fill)
                p.drawRoundedRect(rect, 6, 6)
                if is_vacant:
                    p.save()
                    p.setClipRect(rect)
                    p.setPen(QPen(QColor("#c3c8d1"), 1))
                    step = 8
                    n_lines = int((rect.width() + rect.height()) // step) + 1
                    for k in range(n_lines):
                        offset = k * step - rect.height()
                        p.drawLine(QPointF(rect.left() + offset, rect.bottom()),
                                  QPointF(rect.left() + offset + rect.height(), rect.top()))
                    p.restore()
                if sid is not None:
                    st = self.roster_by_sid.get(sid)
                    if st is not None:
                        p.setFont(num_font)
                        p.setPen(QPen(QColor("#4b5563")))
                        p.drawText(QRectF(rect.left(), rect.top() + 2, rect.width(), num_h),
                                  Qt.AlignHCenter, f"{st.num}번")
                        # [v44.6] 칸 높이는 역할 보기와 무관하게 항상
                        # 고정이다 — 역할이 있으면 이름 영역을 줄여 그
                        # 아래에 역할 한 줄을 더 넣고, 없으면 이름
                        # 영역이 칸 나머지를 전부 쓴다(세로 사이즈
                        # 자체가 안 바뀌니 체크박스를 눌러도 화면이
                        # 출렁이지 않는다).
                        # [v44.8] 이름 시작 위치(name_top)는 번호 영역
                        # 바로 아래(rect.top() + 2 + num_h)부터다 — 이제
                        # 번호가 실제로 차지하는 높이만큼만 비켜서
                        # 그려지므로 겹칠 일이 없다.
                        show_role_here = self.show_role and st.role
                        name_top = rect.top() + 2 + num_h
                        name_h = (rect.bottom() - 18 - name_top) if show_role_here \
                            else (rect.bottom() - name_top)
                        p.setFont(name_font)
                        p.setPen(QPen(QColor(C.WINDOW_FG)))
                        p.drawText(QRectF(rect.left(), name_top, rect.width(), name_h),
                                  Qt.AlignHCenter | Qt.AlignVCenter, st.name)
                        if show_role_here:
                            p.setFont(role_font)
                            p.setPen(QPen(QColor(C.UTIL_MAIN)))
                            p.drawText(QRectF(rect.left(), rect.bottom() - 17, rect.width(), 15),
                                      Qt.AlignHCenter, st.role)
                    else:
                        # [v43.1] 명단이 없을 때(numbered_layout) — sid 자체가
                        # "가짜 학생"이 아니라 번호 문자열이다. 번호만 크게 보여준다.
                        p.setFont(name_font)
                        p.setPen(QPen(QColor(C.WINDOW_FG)))
                        p.drawText(rect, Qt.AlignCenter, tr("util.seating.number_seat", a0=sid))
                elif is_vacant:
                    p.setFont(num_font)
                    p.setPen(QPen(QColor("#8b95a5")))
                    p.drawText(rect, Qt.AlignCenter, tr("util.seating.vacant"))

        podium = QRectF(x0, grid_bottom + _SEAT_GAP, total_w - _SEAT_GAP, 28)
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.setBrush(QColor(C.UTIL_BG))
        p.drawRoundedRect(podium, 4, 4)
        p.setFont(QFont("", 11, QFont.Bold))
        p.setPen(QPen(QColor(C.WINDOW_FG)))
        p.drawText(podium, Qt.AlignCenter, tr("util.seating.podium"))
        p.end()


class SeatingWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.roster = []
        self.save_dir = None
        self.chart = None
        self.headcount_mode = False
        self._build_ui()
        self._load_settings()
        self.retranslate()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        self.canvas = _SeatCanvas()
        self.canvas.cell_clicked.connect(self._on_cell_clicked)
        self.canvas.cell_right_clicked.connect(self._on_cell_right_clicked)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        left = UK.canvas_frame(scroll)

        self.card_class = UK.Card()
        self.lbl_class = UK.body_label()
        self.combo_class = QComboBox()
        self.combo_class.currentIndexChanged.connect(self._on_class_selected)
        self.card_class.add_body(UK.hrow(self.lbl_class, self.combo_class))
        self.lbl_roster_status = UK.hint_label()
        self.card_class.add_body(self.lbl_roster_status)

        # [v43.1] 명단이 아직 없어도 우선 인원 수만으로 좌석표를 만들어
        # 볼 수 있게 — 명단을 올리면 이 줄은 숨고 위의 반 선택으로 넘어간다.
        self.lbl_headcount = UK.body_label()
        self.spin_headcount = QSpinBox()
        self.spin_headcount.setRange(1, 80)
        self.spin_headcount.setValue(20)
        self.btn_generate_numbered = UK.primary_button()
        self.btn_generate_numbered.clicked.connect(self._on_generate_numbered)
        self.headcount_row = UK.hrow(self.lbl_headcount, self.spin_headcount, self.btn_generate_numbered)
        self.card_class.add_body(self.headcount_row)

        template_row = QHBoxLayout()
        template_row.addStretch()
        self.btn_template = UK.secondary_button()
        self.btn_template.clicked.connect(self._on_download_template)
        template_row.addWidget(self.btn_template)
        self.card_class.add_body(template_row)

        self.btn_roster_upload = self.card_class.add_footer(UK.secondary_button())
        self.btn_roster_upload.clicked.connect(self._on_roster_upload)
        self.btn_roster_clear = self.card_class.add_footer(UK.danger_button())
        self.btn_roster_clear.clicked.connect(self._on_roster_clear)

        self.card_seat = UK.Card()
        self.lbl_cols = UK.body_label()
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 12)
        self.spin_cols.setValue(4)
        self.spin_cols.valueChanged.connect(self._on_cols_changed)
        self.card_seat.add_body(UK.hrow(self.lbl_cols, self.spin_cols))
        # [v44.4] 역할 보기 — 기본은 꺼짐(요청대로 "기본은 감추고"). 체크하면
        # 캔버스가 각 학생 칸에 역할(반장·부반장 등)을 추가로 보여준다.
        self.chk_show_role = QCheckBox()
        self.chk_show_role.toggled.connect(self._on_show_role_toggled)
        self.card_seat.add_body(UK.hrow(self.chk_show_role))
        self.hint_seat = UK.hint_label()
        self.hint_seat.setWordWrap(True)
        self.card_seat.add_body(self.hint_seat)
        self.card_seat.body.addStretch(1)
        self.btn_reshuffle = self.card_seat.add_footer(UK.primary_button())
        self.btn_reshuffle.clicked.connect(self._on_reshuffle)

        self.card_save = UK.Card()
        self.lbl_save_dir = UK.hint_label()
        self.lbl_save_dir.setWordWrap(True)
        self.card_save.add_body(self.lbl_save_dir)
        self.btn_pick_dir = self.card_save.add_footer(UK.secondary_button())
        self.btn_pick_dir.clicked.connect(self._on_pick_save_dir)
        self.btn_print = self.card_save.add_footer(UK.secondary_button())
        self.btn_print.clicked.connect(self._on_print)

        # [v43.3] 좌석표는 줄(분단)이 많으면 가로로 아주 넓어지는 표라,
        # 오른쪽 세로 패널(340px 고정)로는 화면을 낭비하게 된다. 캔버스를
        # 위쪽에 크게 두고, 설정 카드 3개는 아래에 가로로 나란히 놓는다
        # (화면 대부분을 배치표가 쓰고, 설정은 아래에서 접근).
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(UK.CARD_SPACING)
        bottom_row.addWidget(self.card_class, 1)
        bottom_row.addWidget(self.card_seat, 1)
        bottom_row.addWidget(self.card_save, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UK.CARD_SPACING)
        root.addWidget(left, 1)
        root.addLayout(bottom_row, 0)

    # ---------------------------------------------------------------- 명단
    def _on_roster_upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("util.seating.roster.upload_title"), "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            students = B.read_roster_excel(path, with_role=True)
        except ImportError:
            QMessageBox.warning(self, tr("util.seating.roster.upload_title"),
                               tr("util.bracket.roster.need_openpyxl"))
            return
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("util.seating.roster.upload_title"), str(e))
            return
        if not students:
            QMessageBox.information(self, tr("util.seating.roster.upload_title"),
                                   tr("util.seating.roster.upload_empty"))
            return
        self.roster = students
        self.chart = None
        self._refresh_class_combo()
        self._update_roster_status()
        self._save_settings()
        if self.host:
            self.host.log(tr("util.seating.log.roster_uploaded", a0=len(students)))

    def _on_roster_clear(self):
        if not self.roster:
            return
        reply = QMessageBox.question(
            self, tr("util.seating.roster.clear_title"), tr("util.seating.roster.clear_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.roster = []
        self.chart = None
        self.combo_class.clear()
        self.canvas.set_chart(None, {})
        self._update_roster_status()
        self._save_settings()

    def _update_roster_status(self):
        self.lbl_roster_status.setText(tr("util.seating.roster.status", a0=len(self.roster)))
        self._update_headcount_visibility()

    def _update_headcount_visibility(self):
        """명단이 없을 때만 '인원 수로 만들기'를 보여준다 — 명단을 올리면
        반 선택 쪽으로 완전히 넘어간다(문서·요청 그대로: 명단이 있으면
        실제 이름, 없으면 임시 번호)."""
        has_roster = bool(self.roster)
        self.combo_class.setVisible(has_roster)
        self.lbl_class.setVisible(has_roster)
        for i in range(self.headcount_row.count()):
            w = self.headcount_row.itemAt(i).widget()
            if w is not None:
                w.setVisible(not has_roster)

    def template_default_path(self):
        """[v44] 양식 저장 대화상자가 처음 여는 위치 — 바탕화면. 파일명만 넘기던
        예전에는 대화상자가 "현재 작업 폴더"(개발 중이면 프로젝트 폴더, exe면
        설치 폴더)를 먼저 띄워 일반 사용자가 저장한 파일을 못 찾곤 했다."""
        return desktop_file(tr("util.seating.template.default_name"))

    def _on_download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.seating.template.title"), self.template_default_path(), "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            B.save_roster_template(path, with_role=True)
        except ImportError:
            QMessageBox.warning(self, tr("util.seating.template.title"), tr("util.bracket.roster.need_openpyxl"))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("util.seating.template.title"), str(e))
            return
        if self.host:
            self.host.status(tr("util.seating.template.saved", a0=path))

    def _on_generate_numbered(self):
        """[v43.1] 명단 없이 인원 수만으로 1~N번 좌석표를 만든다. 나중에
        명단을 올리면 자동으로 실제 이름 기반으로 넘어간다."""
        count = self.spin_headcount.value()
        self.chart = S.numbered_layout(count, self.spin_cols.value())
        self.headcount_mode = True
        self._save_settings()
        self._redraw()
        if self.host:
            self.host.log(tr("util.seating.log.numbered_generated", a0=count))

    def _refresh_class_combo(self, select=None):
        self.combo_class.blockSignals(True)
        self.combo_class.clear()
        for grade, cls in S.class_options(self.roster):
            self.combo_class.addItem(tr("util.seating.class_label", a0=grade, a1=cls), (grade, cls))
        self.combo_class.blockSignals(False)
        if select:
            idx = self.combo_class.findData(select)
            if idx >= 0:
                self.combo_class.setCurrentIndex(idx)
                return
        if self.combo_class.count():
            self.combo_class.setCurrentIndex(0)
            self._on_class_selected(0)

    def _current_class(self):
        return self.combo_class.currentData()

    # ---------------------------------------------------------------- 좌석
    def _on_class_selected(self, _idx):
        gc = self._current_class()
        if not gc:
            self.chart = None
            self.canvas.set_chart(None, {})
            return
        self.headcount_mode = False
        grade, cls = gc
        path = S.chart_file_path(self.save_dir, grade, cls) if self.save_dir else None
        loaded = S.load_chart(path) if path else None
        students = S.students_of_class(self.roster, grade, cls)
        if loaded is not None and loaded.cols and len(students) <= loaded.cols * loaded.rows:
            self.chart = loaded
            self.spin_cols.blockSignals(True)
            self.spin_cols.setValue(loaded.cols)
            self.spin_cols.blockSignals(False)
        else:
            self.chart = S.random_layout(students, self.spin_cols.value(), grade=grade, cls=cls)
            self._save_chart()
        self._redraw()

    def _on_show_role_toggled(self, checked):
        """[v44.4] 체크박스는 그리기에만 영향을 준다 — chart나 명단 데이터
        자체는 그대로라 저장할 것도, 다시 배치할 것도 없다."""
        self.canvas.set_show_role(checked)

    def _on_cols_changed(self, _v):
        if self.headcount_mode:
            if self.chart is not None:
                self._on_generate_numbered()
            return
        gc = self._current_class()
        if not gc:
            return
        grade, cls = gc
        students = S.students_of_class(self.roster, grade, cls)
        self.chart = S.random_layout(students, self.spin_cols.value(), grade=grade, cls=cls)
        self._save_chart()
        self._redraw()

    def _on_reshuffle(self):
        if self.chart is None:
            return
        if self.headcount_mode:
            self.chart = S.numbered_layout(self.spin_headcount.value(), self.chart.cols,
                                           gender_grid=self.chart.gender, reserved=self.chart.reserved)
            self._redraw()
            if self.host:
                self.host.log(tr("util.seating.log.reshuffled_numbered"))
            return
        gc = self._current_class()
        if not gc:
            return
        grade, cls = gc
        students = S.students_of_class(self.roster, grade, cls)
        self.chart = S.reshuffle(self.chart, students)
        self._save_chart()
        self._redraw()
        if self.host:
            self.host.log(tr("util.seating.log.reshuffled", a0=grade, a1=cls))

    def _on_cell_clicked(self, row, col):
        """[v43.3] 칸을 클릭해서 자리를 서로 바꾼다 — 첫 클릭은 선택(파란
        테두리로 표시), 다른 칸을 이어서 클릭하면 두 칸이 맞바뀐다.
        빈 자리와 맞바꾸면 그 학생이 원하는 자리로 옮겨지고, 빈 자리는
        원래 있던 자리로 온다 — "빈 칸 위치를 직접 정하고 싶다"는
        요청을 이 스왑 하나로 해결한다(빈 자리를 원하는 데로 보내면
        되므로). 명단 없이 번호로 배치한 경우에도 똑같이 동작한다."""
        if self.chart is None:
            return
        selected = self.canvas.selected_cell
        if selected is None:
            self.canvas.selected_cell = (row, col)
            self.canvas.update()
            return
        if selected == (row, col):
            self.canvas.selected_cell = None   # 같은 칸을 다시 클릭 → 선택 취소
            self.canvas.update()
            return
        r1, c1 = selected
        self.chart.seats[r1][c1], self.chart.seats[row][col] = \
            self.chart.seats[row][col], self.chart.seats[r1][c1]
        self.canvas.selected_cell = None
        self._save_chart()
        self._redraw()

    def _on_cell_right_clicked(self, row, col, global_pos):
        """[v43.8] 자리를 오른쪽 클릭하면 그 자리의 성별 구역을 바꾸는
        메뉴가 뜬다 — 공석/여학생/남학생. 공석으로 바꾸면 그 자리에
        있던 학생은 내려오고, 이후 무작위 배치·엑셀 업로드 배치 전부
        이 지정을 따른다(남학생은 남학생 칸에만, 여학생은 여학생
        칸에만). [v43.9] 지정석도 여기서 고른다 — 특정 학생(번호)을
        이 자리에 고정하면, 이후 다시 섞어도 그 학생은 항상 이 자리에
        앉고 다른 학생은 이 자리에 배정되지 않는다."""
        if self.chart is None:
            return
        is_reserved_here = self.chart.reserved.get((row, col)) is not None
        menu = QMenu(self)
        act_vacant = menu.addAction(tr("util.seating.menu.vacant"))
        act_female = menu.addAction(tr("util.seating.menu.female"))
        act_male = menu.addAction(tr("util.seating.menu.male"))
        menu.addSeparator()
        reserve_menu = menu.addMenu(tr("util.seating.menu.reserve"))
        reserve_actions = {}
        for sid, label in self._reservable_people():
            act = reserve_menu.addAction(label)
            reserve_actions[act] = sid
        act_unreserve = None
        if is_reserved_here:
            menu.addSeparator()
            act_unreserve = menu.addAction(tr("util.seating.menu.unreserve"))
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is act_vacant:
            self._vacate_seat(row, col)
        elif chosen is act_female:
            S.set_seat_gender(self.chart, row, col, "F")
        elif chosen is act_male:
            S.set_seat_gender(self.chart, row, col, "M")
        elif chosen is act_unreserve:
            self.chart.reserved.pop((row, col), None)
        elif chosen in reserve_actions:
            self._reserve_seat(row, col, reserve_actions[chosen])
        else:
            return
        self.canvas.selected_cell = None
        self._save_chart()
        self._redraw()

    def _reservable_people(self):
        """지정석 메뉴에 나열할 (sid, 표시 문구) 목록 — 명단이 있으면
        실제 학생, 없으면(인원 수 모드) 지금 배치에 쓰인 번호들."""
        if self.roster:
            return [(s.sid, s.label()) for s in self.roster]
        if self.chart is None:
            return []
        sids = sorted({sid for row in self.chart.seats for sid in row if sid}, key=lambda v: int(v))
        return [(sid, tr("util.seating.number_seat", a0=sid)) for sid in sids]

    def _vacate_seat(self, row, col):
        """[버그 수정] 학생이 앉아 있는 자리를 공석으로 지정하면 그 학생이
        그냥 사라져서(화면에서 안 보임) "다시 섞기"를 해야만 다시
        나타났다 — 빈 자리(아직 아무도 없는 칸)가 남아 있으면 그
        학생을 그 자리로 바로 옮겨서, 다시 섞기 없이도 계속 자리에
        남아 있게 한다."""
        moved_sid = self.chart.seats[row][col]
        S.set_seat_gender(self.chart, row, col, "vacant")
        if not moved_sid:
            return
        empty = S.find_empty_seat(self.chart, exclude=(row, col))
        if empty is not None:
            r2, c2 = empty
            self.chart.seats[r2][c2] = moved_sid
            reserved_here = self.chart.reserved.pop((row, col), None)
            if reserved_here:
                self.chart.reserved[(r2, c2)] = reserved_here

    def _reserve_seat(self, row, col, sid):
        """이 자리를 sid 학생의 지정석으로 정한다 — 그 학생이 지금 다른
        자리에 있으면 그 자리와 맞바꾸고, 그 학생의 다른 지정석이
        있었다면(한 사람은 지정석 하나만) 그건 해제한다."""
        for key in [k for k, v in self.chart.reserved.items() if v == sid]:
            del self.chart.reserved[key]
        for r in range(self.chart.rows):
            for c in range(self.chart.cols):
                if self.chart.seats[r][c] == sid and (r, c) != (row, col):
                    self.chart.seats[r][c], self.chart.seats[row][col] = \
                        self.chart.seats[row][col], self.chart.seats[r][c]
                    break
        if self.chart.seats[row][col] != sid:
            self.chart.seats[row][col] = sid
        self.chart.reserved[(row, col)] = sid

    def _redraw(self):
        # [v43.3] _redraw()는 항상 "완전히 새 판" 상태에서 불린다(스왑 완료
        # 후, 다시 섞기, 반 전환 등) — 진행 중이던 칸 선택은 여기서 정리한다.
        self.canvas.selected_cell = None
        roster_by_sid = {s.sid: s for s in self.roster}
        self.canvas.set_chart(self.chart, roster_by_sid)

    def _save_chart(self):
        if not self.chart or not self.save_dir or self.headcount_mode:
            return   # 인원 수 모드는 특정 반에 매인 게 아니라 파일로 자동 저장하지 않는다
        gc = self._current_class()
        if not gc:
            return
        path = S.chart_file_path(self.save_dir, *gc)
        try:
            S.save_chart(path, self.chart)
        except OSError:
            pass

    # ---------------------------------------------------------------- 저장 위치·인쇄
    def _on_pick_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("util.seating.save.pick_title"), self.save_dir or "")
        if not d:
            return
        self.save_dir = d
        self._update_save_dir_label()
        self._save_settings()
        self._save_chart()

    def _update_save_dir_label(self):
        self.lbl_save_dir.setText(
            tr("util.seating.save.dir_set", a0=self.save_dir) if self.save_dir
            else tr("util.seating.save.dir_unset"))

    def _on_print(self):
        """[v43.9] 시간표와 같은 방식 — 한 장에 좌석표를 1/2/4번 담아
        인쇄한다(잘라서 여러 장 나눠 쓰기 좋게)."""
        if self.chart is None:
            return
        dlg = UK.PrintCopiesDialog(
            tr("util.seating.print.title"), tr("util.seating.print.hint"),
            tr("util.seating.print.copies_1"), tr("util.seating.print.copies_2"),
            tr("util.seating.print.copies_4"), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        copies = dlg.result_copies()

        printer = QPrinter(QPrinter.HighResolution)
        # [v43.1] 좌석표는 줄(분단)이 가로로 넓게 나열되는 표라 A4 세로보다
        # 가로가 훨씬 자연스럽다 — 2쪽(세로로 위아래 2번)만 세로로 찍고,
        # 나머지는 가로로 맞춰 둔다(사용자가 매번 방향을 바꿀 필요 없게).
        printer.setPageOrientation(QPageLayout.Portrait if copies == 2 else QPageLayout.Landscape)
        dlg2 = QPrintDialog(printer, self)
        if dlg2.exec() != QPrintDialog.Accepted:
            return
        UK.print_pixmap_with_copies(self, printer, self.canvas.grab(), copies)
        if self.host:
            self.host.status(tr("util.seating.log.printed"))

    # ---------------------------------------------------------------- 저장/불러오기
    def _load_settings(self):
        if self._settings is None:
            return
        self.roster = B.roster_from_json(self._settings.value(_SET_ROSTER, ""))
        self.save_dir = self._settings.value(_SET_SAVE_DIR, "") or None
        cols = self._settings.value(_SET_COLS, "4")
        try:
            self.spin_cols.setValue(int(cols))
        except (TypeError, ValueError):
            pass
        try:
            self.spin_headcount.setValue(int(self._settings.value(_SET_HEADCOUNT, "20")))
        except (TypeError, ValueError):
            pass
        self._update_roster_status()
        self._update_save_dir_label()
        self._refresh_class_combo()

    def _save_settings(self):
        if self._settings is None:
            return
        self._settings.setValue(_SET_ROSTER, B.roster_to_json(self.roster))
        self._settings.setValue(_SET_SAVE_DIR, self.save_dir or "")
        self._settings.setValue(_SET_COLS, str(self.spin_cols.value()))
        self._settings.setValue(_SET_HEADCOUNT, str(self.spin_headcount.value()))

    # ---------------------------------------------------------------- 다국어
    def retranslate(self):
        self.card_class.set_title(tr("util.seating.card.class"))
        self.lbl_class.setText(tr("util.seating.lbl.class"))
        self.lbl_headcount.setText(tr("util.seating.lbl.headcount"))
        self.btn_generate_numbered.setText(tr("util.seating.btn.generate_numbered"))
        self.btn_template.setText(tr("util.seating.btn.template"))
        self.btn_roster_upload.setText(tr("util.seating.btn.upload"))
        self.btn_roster_clear.setText(tr("util.seating.btn.clear"))
        self._update_roster_status()

        self.card_seat.set_title(tr("util.seating.card.seat"))
        self.lbl_cols.setText(tr("util.seating.lbl.cols"))
        self.chk_show_role.setText(tr("util.seating.chk.show_role"))
        self.chk_show_role.setToolTip(tr("util.seating.chk.show_role.tip"))
        self.hint_seat.setText(tr("util.seating.hint"))
        self.btn_reshuffle.setText(tr("util.seating.btn.reshuffle"))

        self.card_save.set_title(tr("util.seating.card.save"))
        self.btn_pick_dir.setText(tr("util.seating.btn.pick_dir"))
        self.btn_print.setText(tr("util.seating.btn.print"))
        self._update_save_dir_label()
        self.canvas.update()


class SeatingApp(MiniApp):
    id = "seating"
    icon = "seating"
    category = "class"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = SeatingWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


TRANSLATIONS = {
    "util.seating.title": {"ko": "좌석표", "en": "Seating Chart", "ja": "座席表"},
    "util.seating.desc": {
        "ko": "학급 명단으로 줄(분단) 수에 맞춰 무작위 좌석표를 만듭니다.",
        "en": "Randomly arranges a class roster into a seating chart by number of columns.",
        "ja": "学級名簿を列（分団）数に合わせてランダムに配置する座席表を作ります。"},
    "util.seating.podium": {"ko": "교탁", "en": "Teacher's desk", "ja": "教卓"},

    "util.seating.card.class": {"ko": "학급 명단", "en": "Class Roster", "ja": "学級名簿"},
    "util.seating.lbl.class": {"ko": "반 선택", "en": "Class", "ja": "クラス選択"},
    "util.seating.lbl.headcount": {"ko": "인원 수", "en": "Headcount", "ja": "人数"},
    "util.seating.btn.generate_numbered": {"ko": "번호로 배치 만들기", "en": "Generate by Number", "ja": "番号で配置作成"},
    "util.seating.btn.template": {"ko": "입력 양식 다운로드", "en": "Download Input Template", "ja": "入力の雛形をダウンロード"},
    "util.seating.template.title": {"ko": "명단 양식 다운로드", "en": "Download Roster Template", "ja": "名簿の雛形をダウンロード"},
    "util.seating.template.default_name": {"ko": "명단_양식.xlsx", "en": "roster_template.xlsx", "ja": "名簿_雛形.xlsx"},
    "util.seating.template.saved": {"ko": "명단 양식을 저장했습니다: {a0}", "en": "Saved roster template: {a0}",
                                     "ja": "名簿の雛形を保存しました: {a0}"},
    "util.seating.number_seat": {"ko": "{a0}번", "en": "#{a0}", "ja": "{a0}番"},
    "util.seating.vacant": {"ko": "공석", "en": "Vacant", "ja": "空席"},
    "util.seating.menu.vacant": {"ko": "공석", "en": "Vacant", "ja": "空席"},
    "util.seating.menu.female": {"ko": "여학생", "en": "Female student", "ja": "女子生徒"},
    "util.seating.menu.male": {"ko": "남학생", "en": "Male student", "ja": "男子生徒"},
    "util.seating.menu.reserve": {"ko": "지정석", "en": "Assign Seat", "ja": "指定席"},
    "util.seating.menu.unreserve": {"ko": "지정석 해제", "en": "Clear Assigned Seat", "ja": "指定席を解除"},
    "util.seating.print.title": {"ko": "좌석표 인쇄", "en": "Print Seating Chart", "ja": "座席表印刷"},
    "util.seating.print.hint": {
        "ko": "한 장에 지금 배치를 몇 번 담아 인쇄할지 고르세요(잘라서 여러 장 쓸 때 편합니다).",
        "en": "Choose how many copies of this layout to fit on one sheet (handy for cutting into pieces).",
        "ja": "1枚に今の配置を何回分印刷するか選んでください（切り分けて使うときに便利です）。"},
    "util.seating.print.copies_1": {"ko": "1쪽(가로 꽉 채움)", "en": "1 (fill landscape)", "ja": "1枚（横いっぱい）"},
    "util.seating.print.copies_2": {"ko": "2쪽(세로, 위아래)", "en": "2 (portrait, top/bottom)",
                                     "ja": "2枚（縦、上下）"},
    "util.seating.print.copies_4": {"ko": "4쪽(가로, 2x2)", "en": "4 (landscape, 2x2)", "ja": "4枚（横、2×2）"},
    "util.seating.log.numbered_generated": {"ko": "[좌석표] 명단 없이 {a0}명 번호로 좌석표 생성",
                                             "en": "[Seating] Generated a numbered layout for {a0} seats",
                                             "ja": "[座席表] 名簿なしで{a0}名分の番号座席表を作成"},
    "util.seating.log.reshuffled_numbered": {"ko": "[좌석표] 번호 배치를 다시 섞음",
                                              "en": "[Seating] Reshuffled the numbered layout",
                                              "ja": "[座席表] 番号配置を再シャッフル"},
    "util.seating.class_label": {"ko": "{a0}학년 {a1}반", "en": "Grade {a0} Class {a1}", "ja": "{a0}学年{a1}組"},
    "util.seating.btn.upload": {"ko": "학생 명단 업로드", "en": "Upload Student Roster", "ja": "生徒名簿アップロード"},
    "util.seating.btn.clear": {"ko": "명단 지우기", "en": "Clear Roster", "ja": "名簿を削除"},
    "util.seating.roster.status": {"ko": "학생 {a0}명 등록됨", "en": "{a0} students registered", "ja": "生徒{a0}名登録済み"},
    "util.seating.roster.upload_title": {"ko": "명단 엑셀 업로드", "en": "Upload Roster Excel", "ja": "名簿Excelアップロード"},
    "util.seating.roster.upload_empty": {"ko": "명단에서 학생을 찾지 못했습니다. 학년·반·번호·이름 순서를 확인해 주세요.",
                                         "en": "No students found — check the grade/class/number/name column order.",
                                         "ja": "名簿から生徒が見つかりませんでした。学年・組・番号・氏名の順序を確認してください。"},
    "util.seating.roster.clear_title": {"ko": "명단 지우기", "en": "Clear Roster", "ja": "名簿を削除"},
    "util.seating.roster.clear_confirm": {
        "ko": "명단을 지우면 지금 화면의 좌석표도 다시 만들어야 합니다. 계속할까요?",
        "en": "Clearing the roster means the current seating chart will need to be rebuilt. Continue?",
        "ja": "名簿を削除すると、現在の座席表も作り直す必要があります。続けますか？"},

    "util.seating.card.seat": {"ko": "좌석 배치", "en": "Seating", "ja": "座席配置"},
    "util.seating.lbl.cols": {"ko": "줄 수(분단)", "en": "Columns", "ja": "列数（分団）"},
    "util.seating.chk.show_role": {"ko": "역할 보기", "en": "Show Roles", "ja": "役割を表示"},
    "util.seating.chk.show_role.tip": {
        "ko": "역할 보기 — 명단 엑셀의 '역할' 칸(반장·부반장·출석부·칠판·실습실 등)을 자리마다 함께 보여줍니다. 역할이 없는 학생은 그대로 비워 둡니다.",
        "en": "Show Roles — Displays each student's role (class leader, board duty, lab duty, etc.) from the roster's 'Role' column on their seat. Students with no role show nothing extra.",
        "ja": "役割を表示 — 名簿Excelの「役割」欄（学級委員・副委員長・出席簿係・黒板係・実習室係など）を各席に一緒に表示します。役割がない生徒はそのまま空欄です。"},
    "util.seating.hint": {
        "ko": "자리를 오른쪽 클릭하면 공석·여학생·남학생·지정석을 정할 수 있습니다.",
        "en": "Right-click a seat to set vacant, female, male, or an assigned seat.",
        "ja": "席を右クリックすると空席・女子生徒・男子生徒・指定席を設定できます。"},
    "util.seating.btn.reshuffle": {"ko": "랜덤 배정", "en": "Random Assignment", "ja": "ランダム配置"},

    "util.seating.card.save": {"ko": "저장·인쇄", "en": "Save & Print", "ja": "保存・印刷"},
    "util.seating.save.pick_title": {"ko": "좌석표 저장 폴더 선택", "en": "Choose Seating Chart Folder",
                                      "ja": "座席表保存フォルダを選択"},
    "util.seating.save.dir_unset": {
        "ko": "저장 폴더가 아직 없습니다 — 정하기 전까지는 반을 바꿔도 자리가 저장되지 않습니다.",
        "en": "No save folder set yet — layouts won't be saved across class switches until you pick one.",
        "ja": "保存フォルダがまだありません — 設定するまでクラスを切り替えると配置は保存されません。"},
    "util.seating.save.dir_set": {"ko": "저장 폴더: {a0}", "en": "Save folder: {a0}", "ja": "保存フォルダ: {a0}"},
    "util.seating.btn.pick_dir": {"ko": "저장 폴더 선택", "en": "Choose Folder", "ja": "保存フォルダ選択"},
    "util.seating.btn.print": {"ko": "인쇄", "en": "Print", "ja": "印刷"},

    "util.seating.log.roster_uploaded": {"ko": "[좌석표] 명단 {a0}명 업로드", "en": "[Seating] Uploaded {a0} students",
                                          "ja": "[座席表] 名簿{a0}名アップロード"},
    "util.seating.log.reshuffled": {"ko": "[좌석표] {a0}학년 {a1}반 자리 다시 섞음",
                                     "en": "[Seating] Reshuffled grade {a0} class {a1}",
                                     "ja": "[座席表] {a0}学年{a1}組の席を再シャッフル"},
    "util.seating.log.printed": {"ko": "좌석표를 인쇄했습니다", "en": "Printed the seating chart", "ja": "座席表を印刷しました"},
}
SeatingApp.tr_table = TRANSLATIONS

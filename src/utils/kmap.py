# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 #2: 카르노맵 논리식 생성기 [v02]

칸을 클릭할 때마다(0 ↔ 1) 그 즉시 최소화된 논리식(SOP, 곱의 합)을 다시
계산해 보여준다. 2변수부터 6변수까지 지원한다.

## 5·6변수는 왜 격자를 여러 개로 나누는가
전통적인 카르노맵은 "옆 칸이 딱 1비트만 다르다"는 성질(그레이 코드)을 이용해
사람이 눈으로 묶는 도구다. 이 성질은 4×4 격자 하나 안에서는 유지되지만,
5·6변수를 억지로 한 장의 2차원 격자에 눌러 담으면 자리마다 인접 규칙이
달라져서 오히려 눈으로 읽기 더 어려워진다. 그래서 5변수는 격자 2장(가로로
나열), 6변수는 격자 4장(2×2로 나열)으로 나누는 표준적인 방식을 따른다.

**격자를 나누더라도 정답은 항상 정확하다.** 화면에 보이는 격자 배치는
사람이 값을 입력하고 읽기 위한 것일 뿐이고, 실제 최소화는 격자 모양과
무관하게 전체 민텀 집합을 놓고 Quine–McCluskey로 계산한다
(자세한 설명은 kmap_solve.py 참고).
"""
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QScrollArea, QFrame, QSizePolicy, QMessageBox,
    QFileDialog, QApplication
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as UK
from .base import MiniApp
from . import kmap_solve as K

DEFAULT_NAMES = ["A", "B", "C", "D", "E", "F"]
CELL_SIZE = 40

_SET_NUM_VARS = "util.kmap.num_vars"
_SET_NAMES = "util.kmap.names"


# =============================================================================
class _Cell(QPushButton):
    """카르노맵의 칸 하나. 값(0/1)과 자기 민텀 번호를 들고 다닌다.

    [v34] 마우스를 누른 채 여러 칸을 지나가면 지나간 칸이 각각 토글된다
    (드래그로 칠하기). 같은 칸 안에서 커서가 흔들려도 반복 토글되지 않게
    "드래그 중 마지막으로 들어간 칸"만 기억해 두고, 그 칸과 다른 칸에
    들어올 때만 토글한다 — 벗어났다가 같은 칸에 다시 들어오면 그때는
    다시 토글된다(자연스러운 페인트 동작).

    실제 마우스 이벤트는 이 클래스가 직접 처리하고(super()를 부르지 않아
    QAbstractButton의 기본 클릭 처리를 타지 않는다), 프로그램에서
    ``cell.click()``으로 누르는 경우(테스트 등)는 Qt가 이 오버라이드를
    건너뛰고 바로 ``clicked`` 시그널을 내보내므로, 그 시그널에 연결해 둔
    기존 토글 핸들러가 그대로 동작한다 — 두 경로가 서로 겹치지 않는다.
    """

    def __init__(self, minterm, num_vars, parent=None):
        super().__init__("0", parent)
        self.minterm = minterm
        self.value = 0
        self.setFixedSize(CELL_SIZE, CELL_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"m{minterm} = " + "".join(
            str(b) for b in K.minterm_bits(minterm, num_vars)))
        self._drag_last = None   # 드래그 중 마지막으로 진입한 칸(끝나면 None)
        # [버그 수정] 드래그 토글을 만들면서 실제 마우스 경로가 이 칸의
        # 값만 바꾸고 KMapWidget에는 전혀 알리지 않게 돼 있었다(논리식이
        # 다시 계산되지 않던 원인) — on_toggle에 KMapWidget이 자기 콜백을
        # 심어 두면, toggle()이 호출될 때마다(클릭이든 드래그든) 그 콜백이
        # 함께 불린다.
        self.on_toggle = None
        self._apply_style()

    def toggle(self):
        self.value = 1 - self.value
        self.setText(str(self.value))
        self._apply_style()
        if self.on_toggle is not None:
            self.on_toggle(self)

    def set_value(self, v):
        self.value = v
        self.setText(str(v))
        self._apply_style()

    def _apply_style(self):
        if self.value:
            self.setStyleSheet(
                f"QPushButton{{background-color:{C.UTIL_MAIN};color:#ffffff;"
                f"font-weight:bold;font-size:14px;border:1px solid {C.UTIL_MAIN};"
                f"border-radius:4px;}}"
                f"QPushButton:hover{{background-color:#a91650;}}")
        else:
            self.setStyleSheet(
                f"QPushButton{{background-color:#ffffff;color:#9aa0a8;"
                f"font-size:14px;border:1px solid {C.BORDER};border-radius:4px;}}"
                f"QPushButton:hover{{background-color:{C.UTIL_BG};}}")

    # ---------------------------------------------------------------- 드래그 토글
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.toggle()
        self._drag_last = self
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_last is None:
            super().mouseMoveEvent(event)
            return
        gpos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        target = QApplication.widgetAt(gpos)
        if isinstance(target, _Cell) and target is not self._drag_last:
            target.toggle()
            self._drag_last = target
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_last is not None:
            self.releaseMouse()
            self._drag_last = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _HeaderLabel(QLabel):
    def __init__(self, text, corner=False):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(CELL_SIZE, CELL_SIZE if not corner else CELL_SIZE)
        weight = "normal" if corner else "bold"
        size = "10px" if corner else "12px"
        color = "#8a8f98" if corner else C.WINDOW_FG
        self.setStyleSheet(
            f"background:transparent;font-weight:{weight};font-size:{size};color:{color};")


class _SubgridWidget(QFrame):
    """격자 한 장 — 행/열 그레이 코드 헤더 + 칸들. 5·6변수일 때 이런 게 여러
    장 생긴다. n<=4일 때는 이 위젯이 딱 하나만 만들어진다."""

    def __init__(self, layout_def, outer_row_idx, outer_col_idx, num_vars,
                 row_var_names, col_var_names, title, parent=None):
        super().__init__(parent)
        self.cells = {}   # (row_idx, col_idx) -> _Cell
        self.setStyleSheet(f"QFrame{{background-color:#ffffff;border:1px solid {C.BORDER};"
                           f"border-radius:6px;}}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(4)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"color:{C.UTIL_MAIN};font-weight:bold;font-size:11px;"
                "background:transparent;border:none;")
            outer.addWidget(lbl)

        grid = QGridLayout()
        grid.setSpacing(2)
        outer.addLayout(grid)

        # [v07] 줄바꿈으로 나눠 보여준다("AB\CDE"처럼 한 줄에 붙여 쓰면
        # 5·6변수처럼 글자가 많아질 때 더 헷갈린다) — 위 줄엔 행 변수,
        # 아래 줄엔 열 변수.
        corner = _HeaderLabel(f"{row_var_names}\n{col_var_names}", corner=True)
        grid.addWidget(corner, 0, 0)

        row_count = layout_def["row_count"]
        col_count = layout_def["col_count"]
        for c in range(col_count):
            grid.addWidget(_HeaderLabel(K.gray_label(layout_def["cols"], c)), 0, c + 1)
        for r in range(row_count):
            grid.addWidget(_HeaderLabel(K.gray_label(layout_def["rows"], r)), r + 1, 0)

        for r in range(row_count):
            for c in range(col_count):
                m = K.cell_minterm(layout_def, outer_row_idx, outer_col_idx, r, c)
                cell = _Cell(m, num_vars)
                grid.addWidget(cell, r + 1, c + 1)
                self.cells[(r, c)] = cell


# =============================================================================
class KMapWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.num_vars = 4
        self.names = DEFAULT_NAMES[:4]
        self.minterm_to_cell = {}    # minterm -> _Cell (모든 서브그리드 통틀어)
        self.values = set()          # 현재 1인 민텀들

        self._load_settings()
        self._build_ui()
        self._rebuild_grid()

    # ---------------------------------------------------------------- 설정
    def _load_settings(self):
        s = self._settings
        if s is None:
            return
        try:
            n = int(s.value(_SET_NUM_VARS, 4))
        except (TypeError, ValueError):
            n = 4
        self.num_vars = n if n in K.LAYOUTS else 4
        raw = s.value(_SET_NAMES, "")
        if raw:
            names = [x.strip() for x in raw.split(",") if x.strip()]
            if len(names) >= self.num_vars:
                self.names = names[:self.num_vars]
        if len(self.names) < self.num_vars:
            self.names = DEFAULT_NAMES[:self.num_vars]

    def _save_settings(self):
        s = self._settings
        if s is None:
            return
        s.setValue(_SET_NUM_VARS, self.num_vars)
        s.setValue(_SET_NAMES, ",".join(self.names))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 왼쪽 카드: 카르노맵(툴바: 변수 개수·이름, 본문: f()= 입력 + 격자, 하단: 전체 0/1) ----
        self.card_map = UK.Card()
        self.lbl_nvars = UK.body_label()
        self.card_map.add_tool(self.lbl_nvars)
        self.combo_nvars = QComboBox()
        for n in range(2, 7):
            self.combo_nvars.addItem(str(n), n)
        self.combo_nvars.setCurrentIndex(self.num_vars - 2)
        self.combo_nvars.currentIndexChanged.connect(self._on_nvars_changed)
        self.card_map.add_tool(self.combo_nvars)
        self.lbl_names = UK.body_label()
        self.card_map.add_tool(self.lbl_names)
        self.names_input = QLineEdit(",".join(self.names))
        self.names_input.setFixedWidth(150)
        self.names_input.editingFinished.connect(self._on_names_edited)
        self.card_map.add_tool(self.names_input)

        self.lbl_fx = UK.body_label()
        self.minterm_field = QLineEdit()
        self.minterm_field.setPlaceholderText("1,2,4,5,6,10")
        self.minterm_field.editingFinished.connect(self._on_minterm_field_edited)
        mrow = UK.hrow(self.lbl_fx)
        mrow.addWidget(self.minterm_field, 1)
        self.card_map.add_body(mrow)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setStyleSheet("background:transparent;")
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background:transparent;")
        self.grid_scroll.setWidget(self.grid_host)
        self.card_map.add_body(UK.canvas_frame(self.grid_scroll, margin=6), 1)

        self.lbl_minterms = UK.hint_label()
        self.lbl_minterms.setMaximumWidth(760)
        self.card_map.add_body(self.lbl_minterms)

        self.btn_all0 = self.card_map.add_footer(UK.secondary_button())
        self.btn_all0.clicked.connect(self._set_all(0))
        self.btn_all1 = self.card_map.add_footer(UK.secondary_button())
        self.btn_all1.clicked.connect(self._set_all(1))

        # ---- 오른쪽 카드: 최소화된 논리식 ----
        self.card_result = UK.Card()
        self.lbl_expr_title = self.card_result.title_label
        self.expr_view = QLabel("0")
        self.expr_view.setTextFormat(Qt.RichText)
        self.expr_view.setWordWrap(True)
        self.expr_view.setFont(QFont("Consolas", 17, QFont.Bold))
        self.expr_view.setStyleSheet(
            f"color:{C.UTIL_MAIN};background-color:#ffffff;border:1px solid {UK.CANVAS_BORDER};"
            "border-radius:4px;padding:12px;")
        self.expr_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.expr_view.setMinimumHeight(70)
        self.card_result.add_body(self.expr_view)
        self.lbl_stats = UK.hint_label()
        self.card_result.add_body(self.lbl_stats)
        self.card_result.body.addStretch()
        self.btn_excel = self.card_result.add_footer(UK.secondary_button())
        self.btn_excel.clicked.connect(self._export_excel)
        self.btn_copy = self.card_result.add_footer(UK.primary_button())
        self.btn_copy.clicked.connect(self._copy_expr)

        UK.split_lr(self, self.card_map, self.card_result)

        self._retranslate_static()

    def _set_all(self, value):
        def handler():
            for cell in self.minterm_to_cell.values():
                cell.set_value(value)
            self.values = set(self.minterm_to_cell.keys()) if value else set()
            self._recompute()
        return handler

    # ------------------------------------------------------------- 격자 구성
    def _rebuild_grid(self):
        # 이전 격자를 통째로 새로 만든다 — 변수 개수가 바뀌면 칸 수 자체가
        # 달라지므로 기존 칸을 재활용할 수 없다.
        old = self.grid_host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    # deleteLater()만 걸면 실제 삭제가 다음 이벤트 루프 차례로
                    # 미뤄져, 그사이에 새 격자를 그리면 화면 캡처(또는 빠른
                    # 재클릭) 시점에 옛 칸과 새 칸이 겹쳐 보일 수 있다.
                    # setParent(None)으로 화면 트리에서 즉시 떼어낸 뒤 삭제를
                    # 예약한다.
                    w.setParent(None)
                    w.deleteLater()
            QWidget().setLayout(old)   # 기존 레이아웃을 grid_host에서 떼어낸다

        layout_def = K.get_layout(self.num_vars)

        # 격자들을 감싸는 안쪽 위젯 하나를 새로 만들고, 그 왼쪽 위에 딱 붙게
        # 바깥쪽에서 stretch로 밀어준다. QGridLayout을 grid_host에 바로 붙이면
        # 스크롤 영역이 넓을 때 격자가 가운데로 퍼져 보이는 문제가 있었다.
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        outer_grid = QGridLayout(inner)
        outer_grid.setSpacing(10)

        wrap = QHBoxLayout(self.grid_host)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(inner, 0, Qt.AlignTop | Qt.AlignLeft)
        wrap.addStretch(1)

        self.minterm_to_cell = {}
        row_names = "".join(self.names[i] for i in layout_def["row_bits"])
        col_names = "".join(self.names[i] for i in layout_def["col_bits"])

        for orow in range(layout_def["outer_row_count"]):
            for ocol in range(layout_def["outer_col_count"]):
                title = self._subgrid_title(layout_def, orow, ocol)
                sub = _SubgridWidget(layout_def, orow, ocol, self.num_vars,
                                     row_names, col_names, title)
                outer_grid.addWidget(sub, orow, ocol)
                for cell in sub.cells.values():
                    self.minterm_to_cell[cell.minterm] = cell
                    cell.on_toggle = self._on_cell_toggled
                    cell.clicked.connect(cell.toggle)

        # 저장돼 있던 값(또는 변수 개수를 바꾸기 전 값 중 겹치는 민텀)을 복원
        for m in list(self.values):
            if m in self.minterm_to_cell:
                self.minterm_to_cell[m].set_value(1)
        self.values = {m for m in self.values if m in self.minterm_to_cell}
        self._update_fx_label()
        self._recompute()

    def _subgrid_title(self, layout_def, orow, ocol):
        parts = []
        if layout_def["outer_row_bits"]:
            bits = K.gray_bits(layout_def["outer_rows"], orow)
            for pos, b in zip(layout_def["outer_row_bits"], bits):
                parts.append(f"{self.names[pos]}={b}")
        if layout_def["outer_col_bits"]:
            bits = K.gray_bits(layout_def["outer_cols"], ocol)
            for pos, b in zip(layout_def["outer_col_bits"], bits):
                parts.append(f"{self.names[pos]}={b}")
        return "  ".join(parts)

    def _on_cell_toggled(self, cell):
        """toggle()이 호출될 때마다(실제 마우스 드래그든, 프로그램의
        click()이든) 불린다 — 여기서 민텀 집합을 갱신하고 다시 계산한다."""
        if cell.value:
            self.values.add(cell.minterm)
        else:
            self.values.discard(cell.minterm)
        self._recompute()

    # ---------------------------------------------------------------- 계산
    def _recompute(self):
        """클릭 즉시 호출된다 — 여기서 매번 처음부터 다시 최소화한다.
        n=6에서도 최악의 경우 0.1초 안팎이라(kmap_solve의 안전장치 덕분)
        클릭할 때마다 다시 계산해도 화면이 밀리지 않는다."""
        terms = K.minimize_sop(self.values, self.num_vars)
        html = self._expr_html(terms)
        self.expr_view.setText(html)

        n_terms = len(terms)
        n_lits = K.literal_count(terms)
        self.lbl_stats.setText(tr("util.kmap.stats", a0=n_terms, a1=n_lits))
        # [버그 수정] 콤마만 있고 공백이 없는 긴 문자열(민텀이 많을 때, 예:
        # 전체 1이면 "0,1,2,...,63")은 QLabel의 자동 줄바꿈이 끊을 지점을
        # 못 찾아 통째로 한 줄에 욱여넣으려 한다 — 그 결과 이 레이블의
        # sizeHint가 1000px 이상으로 치솟아 카르노맵 위젯 전체가 넓어지고,
        # 그걸 맞추려고 옆의 도구 목록 스플리터가 밀려나는 버그로 이어졌다.
        # format_minterms() 자체(입력창·엑셀 출력에도 쓰인다)는 압축된 형태
        # 그대로 두고, 이 레이블에 넣을 때만 콤마 뒤에 공백을 붙여 줄바꿈이
        # 가능한 지점을 만들어 준다.
        minterms_display = K.format_minterms(self.values).replace(",", ", ") or "—"
        self.lbl_minterms.setText(
            tr("util.kmap.minterms", a0=minterms_display,
               a1=len(self.values), a2=1 << self.num_vars))

        plain = K.expr_to_plain(terms, self.names)
        self._last_plain = plain
        if self.host:
            self.host.status(tr("util.kmap.status", a0=plain))
        self._sync_minterm_field()

    # -------------------------------------------------------- minterm 입력창
    def _update_fx_label(self):
        self.lbl_fx.setText(f"f({','.join(self.names)}) =")

    def _sync_minterm_field(self):
        """표 상태 -> 입력창. 그리드를 클릭했을 때나 계산이 끝날 때마다
        불려서, 입력창이 늘 지금 켜진 민텀 목록을 그대로 보여주게 한다.
        setText()는 editingFinished를 다시 일으키지 않으므로 되돌림
        걱정 없이 그냥 불러도 안전하다."""
        self.minterm_field.setText(K.format_minterms(self.values))

    def _on_minterm_field_edited(self):
        """입력창 -> 표. "1,2,4,5,6,10" 같은 콤마 목록을 읽어 그만큼 칸을
        켠다. 범위를 벗어난 값이나 숫자가 아닌 항목은 조용히 걸러낸다 —
        계산기가 잘못된 수식에 팝업을 띄우지 않는 것과 같은 태도다."""
        full = 1 << self.num_vars
        new_values = set()
        for part in self.minterm_field.text().split(","):
            part = part.strip()
            if not part:
                continue
            try:
                v = int(part)
            except ValueError:
                continue
            if 0 <= v < full:
                new_values.add(v)

        for m, cell in self.minterm_to_cell.items():
            cell.set_value(1 if m in new_values else 0)
        self.values = new_values
        self._recompute()   # 내부에서 _sync_minterm_field()도 함께 불러 정리된 형태로 보여준다

    # -------------------------------------------------------------- 엑셀
    def _export_excel(self):
        try:
            import openpyxl
        except ImportError:
            if self.host:
                self.host.status(tr("util.kmap.status.need_openpyxl"))
            QMessageBox.information(self, tr("util.kmap.msg.excel_title"),
                                    tr("util.kmap.msg.need_openpyxl"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.kmap.msg.excel_title"),
            f"kmap_{self.num_vars}var.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "K-map"
        layout_def = K.get_layout(self.num_vars)
        row_names = "".join(self.names[i] for i in layout_def["row_bits"])
        col_names = "".join(self.names[i] for i in layout_def["col_bits"])

        ws.cell(1, 1, f"{row_names}\\{col_names}")
        for c in range(layout_def["col_count"]):
            ws.cell(1, c + 2, K.gray_label(layout_def["cols"], c))
        for r in range(layout_def["row_count"]):
            ws.cell(r + 2, 1, K.gray_label(layout_def["rows"], r))
            for c in range(layout_def["col_count"]):
                m = K.cell_minterm(layout_def, 0, 0, r, c)
                ws.cell(r + 2, c + 2, self.minterm_to_cell[m].value)

        result_row = layout_def["row_count"] + 3
        ws.cell(result_row, 1, tr("util.kmap.excel.minterms"))
        ws.cell(result_row, 2, K.format_minterms(self.values))
        ws.cell(result_row + 1, 1, tr("util.kmap.excel.expr"))
        ws.cell(result_row + 1, 2, getattr(self, "_last_plain", "0"))

        try:
            wb.save(path)
        except OSError as e:
            QMessageBox.warning(self, tr("util.kmap.msg.excel_title"),
                                tr("util.kmap.msg.excel_fail", a0=str(e)))
            return
        if self.host:
            self.host.status(tr("util.kmap.status.excel_saved", a0=path))
            self.host.log(tr("util.kmap.log.excel_saved", a0=path))

    def _expr_html(self, terms):
        """부정 리터럴에 윗줄(overline)을 그어 표시 — 교과서 표기와 같은 인상."""
        if not terms:
            return "0"
        if terms == [tuple(["-"] * self.num_vars)]:
            return "1"
        term_htmls = []
        for t in terms:
            lits = K.term_literals(t, self.names)
            parts = [
                f'<span style="text-decoration:overline;">{n}</span>' if neg else n
                for n, neg in lits
            ]
            term_htmls.append("".join(parts))
        return " + ".join(term_htmls)

    # ---------------------------------------------------------------- 옵션
    def _on_nvars_changed(self, index):
        new_n = self.combo_nvars.itemData(index)
        if new_n == self.num_vars:
            return
        if self.values:
            ok = QMessageBox.question(
                self, tr("util.kmap.msg.change_title"),
                tr("util.kmap.msg.change_body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ok != QMessageBox.Yes:
                self.combo_nvars.blockSignals(True)
                self.combo_nvars.setCurrentIndex(self.num_vars - 2)
                self.combo_nvars.blockSignals(False)
                return
        self.num_vars = new_n
        if len(self.names) < new_n:
            self.names = self.names + DEFAULT_NAMES[len(self.names):new_n]
        else:
            self.names = self.names[:new_n]
        self.names_input.setText(",".join(self.names))
        self.values = set()
        self._rebuild_grid()
        self._save_settings()
        if self.host:
            self.host.log(tr("util.kmap.log.nvars_changed", a0=new_n))

    def _on_names_edited(self):
        raw = [x.strip() for x in self.names_input.text().split(",") if x.strip()]
        # 이름이 모자라거나 겹치면 조용히 기본값으로 채워 넣는다 — 계산기가
        # 잘못된 수식에 팝업을 띄우지 않는 것과 같은 태도: 입력 도중의 상태를
        # 방해하지 않는다.
        seen = set()
        cleaned = []
        for name in raw[:self.num_vars]:
            if name and name not in seen:
                cleaned.append(name)
                seen.add(name)
        while len(cleaned) < self.num_vars:
            for cand in DEFAULT_NAMES:
                if cand not in seen:
                    cleaned.append(cand)
                    seen.add(cand)
                    break
        self.names = cleaned[:self.num_vars]
        self.names_input.setText(",".join(self.names))
        self._rebuild_grid()
        self._save_settings()

    def _copy_expr(self):
        text = getattr(self, "_last_plain", "0")
        QGuiApplication.clipboard().setText(text)
        if self.host:
            self.host.status(tr("util.kmap.status.copied", a0=text))

    # ------------------------------------------------------------- 다국어
    def _retranslate_static(self):
        self.lbl_nvars.setText(tr("util.kmap.lbl.nvars"))
        self.combo_nvars.setToolTip(tr("util.kmap.nvars.tip"))
        self.lbl_names.setText(tr("util.kmap.lbl.names"))
        self.names_input.setToolTip(tr("util.kmap.names.tip"))
        self.names_input.setPlaceholderText(tr("util.kmap.names.placeholder"))
        self.btn_all0.setText(tr("util.kmap.btn.all0"))
        self.btn_all0.setToolTip(tr("util.kmap.btn.all0.tip"))
        self.btn_all1.setText(tr("util.kmap.btn.all1"))
        self.btn_all1.setToolTip(tr("util.kmap.btn.all1.tip"))
        self.lbl_expr_title.setText(tr("util.kmap.expr.title"))
        self.card_map.set_title(tr("util.kmap.title"))
        self.btn_copy.setText(tr("util.kmap.btn.copy"))
        self.btn_copy.setToolTip(tr("util.kmap.btn.copy.tip"))
        self.btn_excel.setText(tr("util.kmap.btn.excel"))
        self.btn_excel.setToolTip(tr("util.kmap.btn.excel.tip"))
        self.minterm_field.setToolTip(tr("util.kmap.minterm_field.tip"))
        self._update_fx_label()

    def retranslate(self):
        self._retranslate_static()
        self._recompute()


# =============================================================================
class KMapApp(MiniApp):
    id = "kmap"
    icon = "kmap"
    category = "logic"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = KMapWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()


# =============================================================================
TRANSLATIONS = {
    "util.kmap.title": {
        "ko": "카르노맵 (논리식 최적화)", "en": "Karnaugh Map (Logic Minimizer)",
        "ja": "カルノー図（論理式の最適化）"},
    "util.kmap.desc": {
        "ko": "칸을 클릭해 0/1을 정하면 그 즉시 최소화된 논리식을 보여줍니다. 2~6변수 지원.",
        "en": "Click cells to set 0/1 and instantly see the minimized expression. Supports 2–6 variables.",
        "ja": "セルをクリックして0/1を決めると、その場で最小化された論理式を表示します。2〜6変数対応。"},

    "util.kmap.lbl.nvars": {"ko": "변수 개수", "en": "Variables", "ja": "変数の数"},
    "util.kmap.nvars.tip": {
        "ko": "카르노맵의 변수 개수를 바꿉니다(2~6개). 5개 이상은 격자를 여러 장으로 나눠 보여줍니다.",
        "en": "Changes the number of variables (2–6). Five or more splits the map into several grids.",
        "ja": "カルノー図の変数の数を変えます（2〜6個）。5個以上は複数の表に分けて表示します。"},
    "util.kmap.lbl.names": {"ko": "변수 이름", "en": "Variable names", "ja": "変数名"},
    "util.kmap.names.tip": {
        "ko": "쉼표로 구분해 변수 이름을 바꿀 수 있습니다. 예) P,Q,R,S",
        "en": "Comma-separated variable names. e.g. P,Q,R,S",
        "ja": "カンマ区切りで変数名を変更できます。例) P,Q,R,S"},
    "util.kmap.names.placeholder": {
        "ko": "예) A,B,C,D", "en": "e.g. A,B,C,D", "ja": "例) A,B,C,D"},

    "util.kmap.btn.all0": {"ko": "전체 0", "en": "All 0", "ja": "全て0"},
    "util.kmap.btn.all0.tip": {
        "ko": "모든 칸을 0으로 되돌립니다.", "en": "Resets every cell to 0.",
        "ja": "すべてのセルを0に戻します。"},
    "util.kmap.btn.all1": {"ko": "전체 1", "en": "All 1", "ja": "全て1"},
    "util.kmap.btn.all1.tip": {
        "ko": "모든 칸을 1로 채웁니다.", "en": "Sets every cell to 1.",
        "ja": "すべてのセルを1にします。"},

    "util.kmap.expr.title": {
        "ko": "최소화된 논리식 (곱의 합)", "en": "Minimized Expression (SOP)",
        "ja": "最小化された論理式（積和形）"},
    "util.kmap.stats": {
        "ko": "항 {a0}개 · 리터럴 {a1}개",
        "en": "{a0} term(s) · {a1} literal(s)",
        "ja": "項 {a0}個 · リテラル {a1}個"},
    "util.kmap.minterms": {
        "ko": "Σm({a0}) — 1인 칸 {a1}/{a2}개",
        "en": "Σm({a0}) — {a1}/{a2} cells set to 1",
        "ja": "Σm({a0}) — 1のセル {a1}/{a2}個"},

    "util.kmap.btn.copy": {"ko": "논리식 복사", "en": "Copy expression", "ja": "論理式をコピー"},
    "util.kmap.btn.copy.tip": {
        "ko": "부정은 A' 형태(아포스트로피)로 복사됩니다.",
        "en": "Negation is copied using an apostrophe, like A'.",
        "ja": "否定は A' の形（アポストロフィ）でコピーされます。"},
    "util.kmap.status": {
        "ko": "논리식: {a0}", "en": "Expression: {a0}", "ja": "論理式: {a0}"},
    "util.kmap.status.copied": {
        "ko": "복사했습니다: {a0}", "en": "Copied: {a0}", "ja": "コピーしました: {a0}"},
    "util.kmap.log.nvars_changed": {
        "ko": "[카르노맵] 변수 개수를 {a0}개로 변경",
        "en": "[K-map] Changed to {a0} variables",
        "ja": "[カルノー図] 変数の数を{a0}個に変更"},

    "util.kmap.msg.change_title": {
        "ko": "변수 개수 변경", "en": "Change variable count", "ja": "変数の数の変更"},
    "util.kmap.msg.change_body": {
        "ko": "변수 개수를 바꾸면 지금 표시된 값이 초기화될 수 있습니다. 계속할까요?",
        "en": "Changing the variable count may reset the current values. Continue?",
        "ja": "変数の数を変えると、現在の値がリセットされることがあります。続けますか？"},

    "util.kmap.minterm_field.tip": {
        "ko": "민텀 번호를 쉼표로 구분해 한 번에 입력합니다. 예) 1,2,4,5,6,10 — "
              "표를 클릭해도 이 칸의 내용이 그만큼 바뀝니다.",
        "en": "Enter minterm numbers separated by commas, e.g. 1,2,4,5,6,10 — "
              "clicking the table updates this field too.",
        "ja": "ミンタームの番号をカンマで区切って一度に入力します。例) 1,2,4,5,6,10 — "
              "表をクリックしてもこの欄が更新されます。"},

    "util.kmap.btn.excel": {"ko": "엑셀 출력", "en": "Export Excel", "ja": "Excel出力"},
    "util.kmap.btn.excel.tip": {
        "ko": "지금 표의 상태와 최소화된 논리식을 엑셀 파일로 저장합니다.",
        "en": "Saves the current table and the minimized expression to an Excel file.",
        "ja": "現在の表の状態と最小化された論理式をExcelファイルに保存します。"},
    "util.kmap.msg.excel_title": {
        "ko": "카르노맵 엑셀 출력", "en": "Export K-map to Excel", "ja": "カルノー図をExcelに出力"},
    "util.kmap.msg.need_openpyxl": {
        "ko": "엑셀 출력에는 openpyxl 패키지가 필요합니다.\n"
              "명령 프롬프트에서 pip install openpyxl 실행 후 다시 시도해 주세요.",
        "en": "Excel export needs the openpyxl package.\n"
              "Run \"pip install openpyxl\" and try again.",
        "ja": "Excel出力には openpyxl パッケージが必要です。\n"
              "\"pip install openpyxl\" を実行してから再度お試しください。"},
    "util.kmap.status.need_openpyxl": {
        "ko": "openpyxl이 설치되어 있지 않습니다.",
        "en": "openpyxl is not installed.",
        "ja": "openpyxlがインストールされていません。"},
    "util.kmap.msg.excel_fail": {
        "ko": "파일을 저장하지 못했습니다: {a0}",
        "en": "Couldn't save the file: {a0}",
        "ja": "ファイルを保存できませんでした: {a0}"},
    "util.kmap.status.excel_saved": {
        "ko": "엑셀로 저장했습니다: {a0}", "en": "Saved to Excel: {a0}", "ja": "Excelに保存しました: {a0}"},
    "util.kmap.log.excel_saved": {
        "ko": "[카르노맵] 엑셀로 저장: {a0}",
        "en": "[K-map] Exported to Excel: {a0}",
        "ja": "[カルノー図] Excelに保存: {a0}"},
    "util.kmap.excel.minterms": {"ko": "민텀", "en": "Minterms", "ja": "ミンターム"},
    "util.kmap.excel.expr": {"ko": "논리식", "en": "Expression", "ja": "論理式"},
}
KMapApp.tr_table = TRANSLATIONS

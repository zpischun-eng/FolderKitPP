# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱: CPU 스케줄링 간트차트 [신규]

프로세스(이름·도착·실행시간·우선순위)를 여러 개 입력하고 기법을 고르면
간트차트로 실행 순서를 그려 준다. 알고리즘은 전부 cpusched_solve.py에
있고, 이 파일은 입력 표·옵션·캔버스·결과 패널만 담당한다.

## 숫자 입력에 QSpinBox를 안 쓰는 이유
대진표(bracket.py)에서 이미 겪은 문제다 — QSpinBox는 한글 입력기(IME)가
조합 중인 글자를 막지 못해 숫자 칸에 한글이 섞여 들어간다. 그래서 표의
숫자 칸은 QLineEdit + QIntValidator + ``Qt.ImhDigitsOnly``로 만든다.
"""
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QFont, QPainter, QPen, QBrush, QColor, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QScrollArea, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QAbstractItemView
)

from ..i18n import tr
from ..styles import C
from . import ui_kit as K
from .base import MiniApp
from . import cpusched_solve as S

PALETTE = ["#1e88e5", "#43a047", "#fb8c00", "#8e24aa", "#00897b",
           "#3949ab", "#c2185b", "#6d4c41"]
IDLE_COLOR = "#d5d8dd"

_SET_ROWS = "util.cpusched.rows"          # "이름,도착,실행,우선순위;이름,..." 형태
_SET_ALGO = "util.cpusched.algo"
_SET_QUANTUM = "util.cpusched.quantum"
_SET_PRIO_DIR = "util.cpusched.prio_dir"
_SET_UNIT_PX = "util.cpusched.unit_px"

_COL_NAME, _COL_ARRIVAL, _COL_BURST, _COL_PRIORITY = range(4)
_DEFAULT_ROWS = [("P1", 0, 5, 2), ("P2", 1, 3, 1), ("P3", 2, 8, 3), ("P4", 3, 6, 2)]
_UNIT_MIN, _UNIT_MAX, _UNIT_DEFAULT = 14, 60, 32


def _color_for(pid):
    return PALETTE[pid % len(PALETTE)]


# =============================================================================
class _NumCell(QLineEdit):
    """표 안의 숫자 입력 칸. IME 조합 중 문자가 끼어드는 문제를 원천적으로
    막기 위해 QSpinBox 대신 QLineEdit + QIntValidator를 쓴다."""

    def __init__(self, value, minimum=0, maximum=999, parent=None):
        super().__init__(str(value), parent)
        self.setValidator(QIntValidator(minimum, maximum, self))
        self.setInputMethodHints(Qt.ImhDigitsOnly)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#ffffff;border:1px solid #d0d4da;border-radius:4px;")

    def int_value(self, default=0):
        try:
            return int(self.text())
        except ValueError:
            return default


# =============================================================================
class _GanttCanvas(QWidget):
    """간트차트 본체. QPainter로 직접 그린다(대진표·함수 그래프와 같은 방식) —
    막대 개수가 보통 10~20개뿐이라 무거운 라이브러리 없이도 충분하다."""

    ROW_H = 46
    TOP_PAD = 10
    LEFT_PAD = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.names = {}          # pid -> name
        self.unit_px = _UNIT_DEFAULT
        self.play_t = None       # None이면 전체 표시, 정수면 그 시각까지만
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_result(self, result, names):
        self.result = result
        self.names = names
        self.play_t = None
        self._relayout()

    def set_unit_px(self, px):
        self.unit_px = px
        self._relayout()

    def set_play_t(self, t):
        self.play_t = t
        self.update()

    def _relayout(self):
        if not self.result or not self.result.ok:
            self.setFixedSize(400, 160)
            self.update()
            return
        makespan = max(self.result.makespan, 1)
        w = self.LEFT_PAD * 2 + makespan * self.unit_px + 40
        h = self.TOP_PAD + self.ROW_H + 40
        self.setFixedSize(int(w), int(h))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if not self.result or not self.result.ok:
            p.end()
            return

        limit = self.play_t if self.play_t is not None else self.result.makespan
        y = self.TOP_PAD
        x0 = self.LEFT_PAD
        font = QFont("Arial", 10)
        p.setFont(font)

        for seg in self.result.segments:
            s, e = seg.start, seg.end
            if s >= limit:
                continue
            e = min(e, limit)
            if e <= s:
                continue
            rx = x0 + s * self.unit_px
            rw = (e - s) * self.unit_px
            rect = QRectF(rx, y, rw, self.ROW_H - 6)
            if seg.pid is None:
                p.setBrush(QBrush(QColor(IDLE_COLOR)))
                p.setPen(QPen(QColor("#b7bcc4"), 1))
            else:
                color = _color_for(seg.pid)
                p.setBrush(QBrush(QColor(color)))
                p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawRoundedRect(rect, 3, 3)

            if seg.pid is not None and rw >= 18:
                p.setPen(QPen(QColor("#ffffff")))
                label = self.names.get(seg.pid, str(seg.pid))
                p.drawText(rect, Qt.AlignCenter, label)

            # 경계 시각 숫자
            p.setPen(QPen(QColor("#5a6068")))
            p.drawText(QRectF(rx - 10, y + self.ROW_H - 4, 20, 16), Qt.AlignCenter, str(s))
            if e == limit or seg is self.result.segments[-1]:
                p.drawText(QRectF(rx + rw - 10, y + self.ROW_H - 4, 20, 16), Qt.AlignCenter, str(e))

        # 재생 중 현재 시각 세로선
        if self.play_t is not None:
            lx = x0 + self.play_t * self.unit_px
            p.setPen(QPen(QColor("#d32f2f"), 2))
            p.drawLine(int(lx), y - 4, int(lx), y + self.ROW_H + 4)

        p.end()


# =============================================================================
class CpuSchedWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self._settings = host.settings() if host else None
        self.result = None
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(400)
        self._play_timer.timeout.connect(self._play_tick)

        self._build_ui()
        self._load_settings()
        self._recalc()

    # ------------------------------------------------------------------ 설정
    def _load_settings(self):
        s = self._settings
        rows = list(_DEFAULT_ROWS)
        algo = S.ALGO_FCFS
        quantum = 2
        prio_dir = S.PRIO_LOW_FIRST
        unit_px = _UNIT_DEFAULT
        if s is not None:
            raw = s.value(_SET_ROWS, "")
            if raw:
                parsed = self._parse_rows_text(raw)
                if parsed:
                    rows = parsed
            algo = s.value(_SET_ALGO, algo)
            if algo not in S.ALGO_ORDER:
                algo = S.ALGO_FCFS
            try:
                quantum = int(s.value(_SET_QUANTUM, quantum))
            except (TypeError, ValueError):
                quantum = 2
            prio_dir = s.value(_SET_PRIO_DIR, prio_dir)
            if prio_dir not in (S.PRIO_LOW_FIRST, S.PRIO_HIGH_FIRST):
                prio_dir = S.PRIO_LOW_FIRST
            try:
                unit_px = int(s.value(_SET_UNIT_PX, unit_px))
            except (TypeError, ValueError):
                unit_px = _UNIT_DEFAULT

        self._fill_table(rows)
        idx = self.combo_algo.findData(algo)
        self.combo_algo.setCurrentIndex(idx if idx >= 0 else 0)
        self.quantum_field.setText(str(max(1, quantum)))
        idx2 = self.combo_prio_dir.findData(prio_dir)
        self.combo_prio_dir.setCurrentIndex(idx2 if idx2 >= 0 else 0)
        self.unit_slider.setValue(max(_UNIT_MIN, min(_UNIT_MAX, unit_px)))
        self._update_option_visibility()

    def _save_settings(self):
        s = self._settings
        if s is None:
            return
        s.setValue(_SET_ROWS, self._rows_to_text())
        s.setValue(_SET_ALGO, self.combo_algo.currentData())
        s.setValue(_SET_QUANTUM, self.quantum_field.int_value(2))
        s.setValue(_SET_PRIO_DIR, self.combo_prio_dir.currentData())
        s.setValue(_SET_UNIT_PX, self.unit_slider.value())

    @staticmethod
    def _parse_rows_text(raw):
        rows = []
        for chunk in raw.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split(",")
            if len(parts) != 4:
                continue
            name, a, b, pr = parts
            try:
                rows.append((name, int(a), int(b), int(pr)))
            except ValueError:
                continue
        return rows

    def _rows_to_text(self):
        return ";".join(",".join(str(v) for v in row) for row in self._read_rows())

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # ---- 상단: 입력 카드(좌) + 결과 카드(우) — 같은 줄이라 높이가 자동으로 같아진다 ----
        self.card_input = K.Card()
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(200)
        self.card_input.add_body(K.canvas_frame(self.table))

        self.lbl_example = K.body_label()
        self.card_input.add_tool(self.lbl_example)
        self.combo_example = QComboBox()
        for preset in S.EXAMPLES:
            self.combo_example.addItem(tr(f"util.cpusched.example.{preset.key}"), preset.key)
        self.combo_example.currentIndexChanged.connect(self._on_example_selected)
        self.card_input.add_tool(self.combo_example)

        # 기법 옵션 줄(본문 아래)
        self.lbl_algo = K.body_label()
        self.combo_algo = QComboBox()
        for algo in S.ALGO_ORDER:
            self.combo_algo.addItem(tr(f"util.cpusched.algo.{algo}"), algo)
        self.combo_algo.currentIndexChanged.connect(self._on_algo_changed)
        self.lbl_quantum = K.body_label()
        self.quantum_field = _NumCell(2, 1, 999)
        self.quantum_field.setFixedWidth(50)
        self.quantum_field.editingFinished.connect(self._recalc)
        self.lbl_prio_dir = K.body_label()
        self.combo_prio_dir = QComboBox()
        self.combo_prio_dir.addItem(tr("util.cpusched.priodir.low"), S.PRIO_LOW_FIRST)
        self.combo_prio_dir.addItem(tr("util.cpusched.priodir.high"), S.PRIO_HIGH_FIRST)
        self.combo_prio_dir.currentIndexChanged.connect(self._recalc)
        self.card_input.add_body(K.hrow(self.lbl_algo, self.combo_algo, self.lbl_quantum, self.quantum_field,
                                        self.lbl_prio_dir, self.combo_prio_dir, stretch_last=True))

        self.lbl_error = K.error_label()
        self.card_input.add_footer_left(self.lbl_error)
        self.btn_del_row = self.card_input.add_footer(K.danger_button())
        self.btn_del_row.clicked.connect(self._delete_selected_rows)
        self.btn_add_row = self.card_input.add_footer(K.secondary_button())
        self.btn_add_row.clicked.connect(self._add_row)
        self.btn_run = self.card_input.add_footer(K.primary_button())
        self.btn_run.clicked.connect(self._recalc)

        self.card_result = K.Card()
        self.lbl_result_title = self.card_result.title_label
        self.result_table = QTableWidget(0, 5)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setSelectionMode(QTableWidget.NoSelection)
        self.result_table.setMaximumHeight(200)
        self.card_result.add_body(K.canvas_frame(self.result_table))
        self.lbl_summary = K.body_label()
        self.lbl_summary.setWordWrap(True)
        self.card_result.add_body(self.lbl_summary)
        self.btn_export_excel = self.card_result.add_footer(K.secondary_button())
        self.btn_export_excel.clicked.connect(self._export_excel)
        self.btn_export_png = self.card_result.add_footer(K.secondary_button())
        self.btn_export_png.clicked.connect(self._export_png)

        top_row = QHBoxLayout()
        top_row.setSpacing(K.CARD_SPACING)
        top_row.addWidget(self.card_input, 1)
        top_row.addWidget(self.card_result, 1)

        # ---- 하단: 간트차트 카드 — 툴바에 칸 너비·재생 조작, 본문은 캔버스가 꽉 채운다 ----
        self.card_gantt = K.Card()
        self.lbl_zoom = K.body_label()
        self.card_gantt.add_tool(self.lbl_zoom)
        self.unit_slider = QSlider(Qt.Horizontal)
        self.unit_slider.setRange(_UNIT_MIN, _UNIT_MAX)
        self.unit_slider.setValue(_UNIT_DEFAULT)
        self.unit_slider.setFixedWidth(140)
        self.unit_slider.valueChanged.connect(self._on_zoom_changed)
        self.card_gantt.add_tool(self.unit_slider)
        self.btn_play_reset = self.card_gantt.add_tool(K.tool_button("⏮"))
        self.btn_play_reset.clicked.connect(self._play_reset)
        self.btn_play_step_back = self.card_gantt.add_tool(K.tool_button("◀"))
        self.btn_play_step_back.clicked.connect(lambda: self._play_step(-1))
        self.btn_play_toggle = self.card_gantt.add_tool(K.tool_button("▶"))
        self.btn_play_toggle.clicked.connect(self._play_toggle)
        self.btn_play_step_fwd = self.card_gantt.add_tool(K.tool_button("▶|"))
        self.btn_play_step_fwd.clicked.connect(lambda: self._play_step(1))

        self.canvas = _GanttCanvas()
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setFrameShape(QFrame.NoFrame)
        self.canvas_scroll.setStyleSheet("background:transparent;")
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setMinimumHeight(140)
        self.card_gantt.add_body(K.canvas_frame(self.canvas_scroll), 1)
        self.lbl_play_queue = K.hint_label()
        self.card_gantt.add_footer_left(self.lbl_play_queue)

        K.split_tb(self, top_row, self.card_gantt)

        self._retranslate_static()

    # ------------------------------------------------------------------ 표
    def _fill_table(self, rows):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row in rows:
            self._append_row(row)
        self.table.blockSignals(False)

    def _append_row(self, row):
        name, arrival, burst, priority = row
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, _COL_NAME, QTableWidgetItem(str(name)))
        self.table.setCellWidget(r, _COL_ARRIVAL, _NumCell(arrival, 0, 9999))
        self.table.setCellWidget(r, _COL_BURST, _NumCell(max(1, burst), 1, 9999))
        self.table.setCellWidget(r, _COL_PRIORITY, _NumCell(priority, 0, 9999))

    def _add_row(self):
        n = self.table.rowCount()
        if n >= S.MAX_PROCS:
            self.lbl_error.setText(tr("util.cpusched.err.too_many", a0=S.MAX_PROCS))
            return
        self._append_row((f"P{n + 1}", 0, 3, 0))

    def _delete_selected_rows(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            rows = [self.table.rowCount() - 1] if self.table.rowCount() else []
        for r in rows:
            self.table.removeRow(r)
        self._recalc()

    def _read_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, _COL_NAME)
            name = name_item.text().strip() if name_item else ""
            if not name:
                name = f"P{r + 1}"
            arrival_w = self.table.cellWidget(r, _COL_ARRIVAL)
            burst_w = self.table.cellWidget(r, _COL_BURST)
            prio_w = self.table.cellWidget(r, _COL_PRIORITY)
            arrival = arrival_w.int_value(0) if arrival_w else 0
            burst = burst_w.int_value(1) if burst_w else 1
            priority = prio_w.int_value(0) if prio_w else 0
            rows.append((name, arrival, burst, priority))
        return rows

    # ------------------------------------------------------------------ 계산
    def _on_algo_changed(self):
        self._update_option_visibility()
        self._recalc()

    def _update_option_visibility(self):
        algo = self.combo_algo.currentData()
        is_rr = algo == S.ALGO_RR
        is_prio = algo in (S.ALGO_PRIO, S.ALGO_PRIO_P)
        self.lbl_quantum.setVisible(is_rr)
        self.quantum_field.setVisible(is_rr)
        self.lbl_prio_dir.setVisible(is_prio)
        self.combo_prio_dir.setVisible(is_prio)

    def _on_example_selected(self):
        key = self.combo_example.currentData()
        preset = next((p for p in S.EXAMPLES if p.key == key), None)
        if preset is None:
            return
        self._fill_table(preset.rows)
        idx = self.combo_algo.findData(preset.algo)
        if idx >= 0:
            self.combo_algo.setCurrentIndex(idx)
        self.quantum_field.setText(str(preset.quantum))
        idx2 = self.combo_prio_dir.findData(preset.prio_dir)
        if idx2 >= 0:
            self.combo_prio_dir.setCurrentIndex(idx2)
        self._update_option_visibility()
        self._recalc()

    def _on_zoom_changed(self, value):
        self.canvas.set_unit_px(value)
        self._save_settings()

    def _recalc(self):
        self._play_pause()
        rows = self._read_rows()
        procs = S.make_procs(rows)
        algo = self.combo_algo.currentData()
        quantum = self.quantum_field.int_value(2)
        prio_dir = self.combo_prio_dir.currentData()

        errors = S.validate(procs, quantum)
        if errors:
            code, params = errors[0]
            self.lbl_error.setText(tr(f"util.cpusched.err.{code}", **params))
            self.result = None
            self.canvas.set_result(None, {})
            self.result_table.setRowCount(0)
            self.lbl_summary.setText("")
            self._save_settings()
            return

        self.lbl_error.setText("")
        self.result = S.simulate(procs, algo, quantum=quantum, prio_dir=prio_dir)
        names = {p.pid: p.name for p in procs}
        self._names = names

        if not self.result.ok:
            self.lbl_error.setText(tr(f"util.cpusched.err.{self.result.error}", **self.result.error_params))
            self.canvas.set_result(None, {})
            self.result_table.setRowCount(0)
            self.lbl_summary.setText("")
            self._save_settings()
            return

        self.canvas.set_result(self.result, names)
        self._fill_result_table(names)
        self._update_summary()
        self.unit_slider_range_guard()
        self._save_settings()

    def unit_slider_range_guard(self):
        # 캔버스 폭 갱신 후 스크롤 위치를 처음으로 되돌린다(재계산 직후 혼란 방지).
        self.canvas_scroll.horizontalScrollBar().setValue(0)

    def _fill_result_table(self, names):
        self.result_table.setRowCount(0)
        for pid in sorted(self.result.stats.keys()):
            st = self.result.stats[pid]
            r = self.result_table.rowCount()
            self.result_table.insertRow(r)
            self.result_table.setItem(r, 0, QTableWidgetItem(names.get(pid, str(pid))))
            self.result_table.setItem(r, 1, QTableWidgetItem(str(st.ct)))
            self.result_table.setItem(r, 2, QTableWidgetItem(str(st.tat)))
            self.result_table.setItem(r, 3, QTableWidgetItem(str(st.wt)))
            self.result_table.setItem(r, 4, QTableWidgetItem(str(st.rt)))

    def _update_summary(self):
        r = self.result
        self.lbl_summary.setText(
            tr("util.cpusched.summary",
               a0=f"{r.avg_wt:.2f}", a1=f"{r.avg_tat:.2f}", a2=f"{r.avg_rt:.2f}",
               a3=f"{r.utilization * 100:.1f}", a4=f"{r.throughput:.3f}"))

    # ------------------------------------------------------------------ 단계 재생
    def _play_reset(self):
        self._play_pause()
        self.canvas.set_play_t(0)
        self._update_play_queue_label(0)

    def _play_toggle(self):
        if self._play_timer.isActive():
            self._play_pause()
        else:
            if self.result is None or not self.result.ok:
                return
            if self.canvas.play_t is None:
                self.canvas.set_play_t(0)
            self._play_timer.start()
            self.btn_play_toggle.setText("⏸")

    def _play_pause(self):
        self._play_timer.stop()
        self.btn_play_toggle.setText("▶")

    def _play_tick(self):
        self._play_step(1)

    def _play_step(self, direction):
        if self.result is None or not self.result.ok:
            return
        t = self.canvas.play_t if self.canvas.play_t is not None else 0
        t = max(0, min(self.result.makespan, t + direction))
        self.canvas.set_play_t(t)
        self._update_play_queue_label(t)
        if t >= self.result.makespan:
            self._play_pause()

    def _update_play_queue_label(self, t):
        if self.result is None or not self.result.ok:
            self.lbl_play_queue.setText("")
            return
        snap_t = max(0, min(t, self.result.makespan - 1)) if self.result.makespan else 0
        queue_pids = self.result.ready_snapshots.get(snap_t)
        if queue_pids is None:
            keys = sorted(k for k in self.result.ready_snapshots if k <= snap_t)
            queue_pids = self.result.ready_snapshots[keys[-1]] if keys else []
        names = [self._names.get(pid, str(pid)) for pid in queue_pids]
        text = " → ".join(names) if names else tr("util.cpusched.queue.empty")
        self.lbl_play_queue.setText(tr("util.cpusched.queue.label", a0=t, a1=text))

    # ------------------------------------------------------------------ 내보내기
    def _export_png(self):
        if self.result is None or not self.result.ok:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.cpusched.msg.export_title"), "cpusched.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pixmap = self.canvas.grab()
        ok = pixmap.save(path, "PNG")
        if self.host:
            if ok:
                self.host.status(tr("util.cpusched.status.image_saved", a0=path))
                self.host.log(tr("util.cpusched.log.image_saved", a0=path))
            else:
                self.host.status(tr("util.cpusched.status.image_fail"))

    def _export_excel(self):
        try:
            import openpyxl
        except ImportError:
            if self.host:
                self.host.status(tr("util.cpusched.status.need_openpyxl"))
            QMessageBox.information(self, tr("util.cpusched.msg.excel_title"),
                                    tr("util.cpusched.msg.need_openpyxl"))
            return
        if self.result is None or not self.result.ok:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("util.cpusched.msg.excel_title"), "cpusched.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Gantt"
        ws.cell(1, 1, tr("util.cpusched.excel.segment_start"))
        ws.cell(1, 2, tr("util.cpusched.excel.segment_end"))
        ws.cell(1, 3, tr("util.cpusched.excel.segment_proc"))
        for i, seg in enumerate(self.result.segments):
            ws.cell(i + 2, 1, seg.start)
            ws.cell(i + 2, 2, seg.end)
            ws.cell(i + 2, 3, self._names.get(seg.pid, tr("util.cpusched.idle")) if seg.pid is not None
                    else tr("util.cpusched.idle"))

        ws2 = wb.create_sheet(tr("util.cpusched.excel.sheet_stats"))
        headers = [tr("util.cpusched.result.col.name"), tr("util.cpusched.result.col.ct"),
                   tr("util.cpusched.result.col.tat"), tr("util.cpusched.result.col.wt"),
                   tr("util.cpusched.result.col.rt")]
        for c, h in enumerate(headers, start=1):
            ws2.cell(1, c, h)
        for r, pid in enumerate(sorted(self.result.stats.keys()), start=2):
            st = self.result.stats[pid]
            ws2.cell(r, 1, self._names.get(pid, str(pid)))
            ws2.cell(r, 2, st.ct)
            ws2.cell(r, 3, st.tat)
            ws2.cell(r, 4, st.wt)
            ws2.cell(r, 5, st.rt)

        try:
            wb.save(path)
        except OSError as e:
            QMessageBox.warning(self, tr("util.cpusched.msg.excel_title"),
                                tr("util.cpusched.msg.excel_fail", a0=str(e)))
            return
        if self.host:
            self.host.status(tr("util.cpusched.status.excel_saved", a0=path))
            self.host.log(tr("util.cpusched.log.excel_saved", a0=path))

    # ------------------------------------------------------------------ 다국어
    def _retranslate_static(self):
        self.setWindowTitle(tr("util.cpusched.title"))
        self.card_input.set_title(tr("util.cpusched.lbl.input_title"))
        self.card_gantt.set_title(tr("util.cpusched.lbl.gantt_title"))
        self.table.setHorizontalHeaderLabels([
            tr("util.cpusched.col.name"), tr("util.cpusched.col.arrival"),
            tr("util.cpusched.col.burst"), tr("util.cpusched.col.priority")])
        self.btn_add_row.setText(tr("util.cpusched.btn.add_row"))
        self.btn_del_row.setText(tr("util.cpusched.btn.del_row"))
        self.lbl_example.setText(tr("util.cpusched.lbl.example"))
        self.lbl_algo.setText(tr("util.cpusched.lbl.algo"))
        self.lbl_quantum.setText(tr("util.cpusched.lbl.quantum"))
        self.lbl_prio_dir.setText(tr("util.cpusched.lbl.prio_dir"))
        self.btn_run.setText(tr("util.cpusched.btn.run"))
        self.lbl_zoom.setText(tr("util.cpusched.lbl.zoom"))
        self.lbl_result_title.setText(tr("util.cpusched.lbl.result_title"))
        self.result_table.setHorizontalHeaderLabels([
            tr("util.cpusched.result.col.name"), tr("util.cpusched.result.col.ct"),
            tr("util.cpusched.result.col.tat"), tr("util.cpusched.result.col.wt"),
            tr("util.cpusched.result.col.rt")])
        self.btn_export_png.setText(tr("util.cpusched.btn.export_png"))
        self.btn_export_excel.setText(tr("util.cpusched.btn.export_excel"))

        for i, algo in enumerate(S.ALGO_ORDER):
            self.combo_algo.setItemText(i, tr(f"util.cpusched.algo.{algo}"))
        self.combo_prio_dir.setItemText(0, tr("util.cpusched.priodir.low"))
        self.combo_prio_dir.setItemText(1, tr("util.cpusched.priodir.high"))
        for i, preset in enumerate(S.EXAMPLES):
            self.combo_example.setItemText(i, tr(f"util.cpusched.example.{preset.key}"))

    def retranslate(self):
        self._retranslate_static()
        if self.result is not None and self.result.ok:
            self._update_summary()
            names = getattr(self, "_names", {})
            self._fill_result_table(names)
            self.canvas.update()
            self._update_play_queue_label(self.canvas.play_t or 0)
        elif self.result is not None and not self.result.ok:
            self.lbl_error.setText(tr(f"util.cpusched.err.{self.result.error}", **self.result.error_params))


# =============================================================================
class CpuSchedApp(MiniApp):
    id = "cpusched"
    icon = "cpusched"
    category = "logic"

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = CpuSchedWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False


# =============================================================================
TRANSLATIONS = {
    "util.cpusched.title": {
        "ko": "CPU 스케줄링 (간트차트)", "en": "CPU Scheduling (Gantt Chart)",
        "ja": "CPUスケジューリング（ガントチャート）"},
    "util.cpusched.desc": {
        "ko": "프로세스를 여러 개 등록하고 스케줄링 기법에 따라 간트차트가 어떻게 그려지는지 보여줍니다.",
        "en": "Register several processes and see how the Gantt chart differs by scheduling algorithm.",
        "ja": "複数のプロセスを登録し、スケジューリング方式によってガントチャートがどう変わるかを表示します。"},

    "util.cpusched.col.name": {"ko": "이름", "en": "Name", "ja": "名前"},
    "util.cpusched.col.arrival": {"ko": "도착 시간", "en": "Arrival", "ja": "到着時間"},
    "util.cpusched.col.burst": {"ko": "실행 시간", "en": "Burst", "ja": "実行時間"},
    "util.cpusched.col.priority": {"ko": "우선순위", "en": "Priority", "ja": "優先度"},

    "util.cpusched.btn.add_row": {"ko": "행 추가", "en": "Add row", "ja": "行を追加"},
    "util.cpusched.btn.del_row": {"ko": "선택 행 삭제", "en": "Delete selected", "ja": "選択行を削除"},
    "util.cpusched.lbl.example": {"ko": "예제", "en": "Example", "ja": "サンプル"},

    "util.cpusched.lbl.algo": {"ko": "기법", "en": "Algorithm", "ja": "方式"},
    "util.cpusched.lbl.quantum": {"ko": "시간 할당량", "en": "Quantum", "ja": "タイムクアンタム"},
    "util.cpusched.lbl.prio_dir": {"ko": "우선순위 방향", "en": "Priority direction", "ja": "優先度の方向"},
    "util.cpusched.priodir.low": {"ko": "숫자가 작을수록 높음", "en": "Lower number = higher priority",
                                   "ja": "数字が小さいほど高い"},
    "util.cpusched.priodir.high": {"ko": "숫자가 클수록 높음", "en": "Higher number = higher priority",
                                    "ja": "数字が大きいほど高い"},
    "util.cpusched.btn.run": {"ko": "실행", "en": "Run", "ja": "実行"},
    "util.cpusched.lbl.zoom": {"ko": "칸 너비", "en": "Cell width", "ja": "セル幅"},

    "util.cpusched.btn.play_reset": {"ko": "처음으로", "en": "Reset", "ja": "先頭へ"},
    "util.cpusched.queue.label": {"ko": "t={a0}  대기 큐: {a1}", "en": "t={a0}  Ready queue: {a1}",
                                   "ja": "t={a0}  待ち行列: {a1}"},
    "util.cpusched.queue.empty": {"ko": "(없음)", "en": "(empty)", "ja": "（なし）"},

    "util.cpusched.lbl.result_title": {"ko": "결과", "en": "Results", "ja": "結果"},
    "util.cpusched.lbl.input_title": {"ko": "프로세스 입력", "en": "Processes", "ja": "プロセス入力"},
    "util.cpusched.lbl.gantt_title": {"ko": "간트차트", "en": "Gantt chart", "ja": "ガントチャート"},
    "util.cpusched.result.col.name": {"ko": "이름", "en": "Name", "ja": "名前"},
    "util.cpusched.result.col.ct": {"ko": "완료", "en": "CT", "ja": "完了"},
    "util.cpusched.result.col.tat": {"ko": "반환", "en": "TAT", "ja": "反転"},
    "util.cpusched.result.col.wt": {"ko": "대기", "en": "WT", "ja": "待機"},
    "util.cpusched.result.col.rt": {"ko": "응답", "en": "RT", "ja": "応答"},

    "util.cpusched.summary": {
        "ko": "평균 대기시간: {a0}   평균 반환시간: {a1}   평균 응답시간: {a2}\nCPU 이용률: {a3}%   처리량: {a4} 개/단위시간",
        "en": "Avg wait: {a0}   Avg turnaround: {a1}   Avg response: {a2}\nCPU utilization: {a3}%   Throughput: {a4} /unit time",
        "ja": "平均待ち時間: {a0}   平均反転時間: {a1}   平均応答時間: {a2}\nCPU利用率: {a3}%   スループット: {a4} 個/単位時間"},

    "util.cpusched.btn.export_png": {"ko": "간트차트 PNG로 저장", "en": "Save Gantt chart as PNG",
                                      "ja": "ガントチャートをPNGで保存"},
    "util.cpusched.btn.export_excel": {"ko": "결과 Excel로 저장", "en": "Save results as Excel",
                                        "ja": "結果をExcelで保存"},
    "util.cpusched.idle": {"ko": "유휴", "en": "Idle", "ja": "アイドル"},

    "util.cpusched.msg.export_title": {"ko": "간트차트 이미지 저장", "en": "Save Gantt Chart Image",
                                        "ja": "ガントチャート画像を保存"},
    "util.cpusched.msg.excel_title": {"ko": "결과 Excel 저장", "en": "Save Results Excel",
                                       "ja": "結果Excelを保存"},
    "util.cpusched.msg.need_openpyxl": {
        "ko": "Excel 저장에는 openpyxl 패키지가 필요합니다.",
        "en": "Saving to Excel requires the openpyxl package.",
        "ja": "Excel保存にはopenpyxlパッケージが必要です。"},
    "util.cpusched.msg.excel_fail": {"ko": "Excel 저장 실패: {a0}", "en": "Failed to save Excel: {a0}",
                                      "ja": "Excel保存に失敗しました: {a0}"},

    "util.cpusched.status.image_saved": {"ko": "간트차트 이미지 저장됨: {a0}",
                                          "en": "Gantt chart image saved: {a0}",
                                          "ja": "ガントチャート画像を保存しました: {a0}"},
    "util.cpusched.status.image_fail": {"ko": "이미지 저장 실패", "en": "Failed to save image",
                                         "ja": "画像の保存に失敗しました"},
    "util.cpusched.status.need_openpyxl": {"ko": "openpyxl 패키지가 필요합니다.",
                                            "en": "The openpyxl package is required.",
                                            "ja": "openpyxlパッケージが必要です。"},
    "util.cpusched.status.excel_saved": {"ko": "Excel 저장됨: {a0}", "en": "Excel saved: {a0}",
                                          "ja": "Excelを保存しました: {a0}"},
    "util.cpusched.log.image_saved": {"ko": "간트차트 이미지를 저장했습니다: {a0}",
                                       "en": "Saved the Gantt chart image: {a0}",
                                       "ja": "ガントチャート画像を保存しました: {a0}"},
    "util.cpusched.log.excel_saved": {"ko": "결과를 Excel로 저장했습니다: {a0}",
                                       "en": "Saved the results as Excel: {a0}",
                                       "ja": "結果をExcelで保存しました: {a0}"},

    "util.cpusched.excel.segment_start": {"ko": "시작", "en": "Start", "ja": "開始"},
    "util.cpusched.excel.segment_end": {"ko": "종료", "en": "End", "ja": "終了"},
    "util.cpusched.excel.segment_proc": {"ko": "프로세스", "en": "Process", "ja": "プロセス"},
    "util.cpusched.excel.sheet_stats": {"ko": "통계", "en": "Stats", "ja": "統計"},

    "util.cpusched.err.empty": {"ko": "프로세스를 1개 이상 등록하세요.",
                                 "en": "Register at least one process.",
                                 "ja": "プロセスを1つ以上登録してください。"},
    "util.cpusched.err.too_many": {"ko": "프로세스는 최대 {a0}개까지 등록할 수 있습니다.",
                                    "en": "You can register up to {a0} processes.",
                                    "ja": "プロセスは最大{a0}個まで登録できます。"},
    "util.cpusched.err.burst_invalid": {"ko": "{a0}행: 실행 시간은 1 이상이어야 합니다.",
                                         "en": "Row {a0}: burst time must be at least 1.",
                                         "ja": "{a0}行目: 実行時間は1以上である必要があります。"},
    "util.cpusched.err.arrival_invalid": {"ko": "{a0}행: 도착 시간은 0 이상이어야 합니다.",
                                           "en": "Row {a0}: arrival time must be 0 or more.",
                                           "ja": "{a0}行目: 到着時間は0以上である必要があります。"},
    "util.cpusched.err.too_large": {"ko": "입력한 시간 범위가 너무 큽니다. 값을 줄여 주세요.",
                                     "en": "The time range is too large. Please reduce the values.",
                                     "ja": "入力した時間の範囲が大きすぎます。値を小さくしてください。"},
    "util.cpusched.err.quantum_invalid": {"ko": "시간 할당량은 1 이상이어야 합니다.",
                                           "en": "Quantum must be at least 1.",
                                           "ja": "タイムクアンタムは1以上である必要があります。"},
    "util.cpusched.err.unknown_algo": {"ko": "알 수 없는 기법입니다.", "en": "Unknown algorithm.",
                                        "ja": "不明な方式です。"},
    "util.cpusched.err.internal_incomplete": {"ko": "계산 중 오류가 발생했습니다.",
                                               "en": "An internal error occurred during calculation.",
                                               "ja": "計算中にエラーが発生しました。"},

    "util.cpusched.algo.fcfs": {"ko": "FCFS (도착 순서)", "en": "FCFS (First-Come, First-Served)",
                                 "ja": "FCFS（到着順）"},
    "util.cpusched.algo.sjf": {"ko": "SJF (최단 작업 우선, 비선점)", "en": "SJF (Shortest Job First, non-preemptive)",
                                "ja": "SJF（最短ジョブ優先・非プリエンプティブ）"},
    "util.cpusched.algo.srtf": {"ko": "SRTF (최단 잔여시간 우선, 선점)",
                                 "en": "SRTF (Shortest Remaining Time First, preemptive)",
                                 "ja": "SRTF（最短残余時間優先・プリエンプティブ）"},
    "util.cpusched.algo.prio": {"ko": "우선순위 (비선점)", "en": "Priority (non-preemptive)",
                                 "ja": "優先度（非プリエンプティブ）"},
    "util.cpusched.algo.prio_p": {"ko": "우선순위 (선점)", "en": "Priority (preemptive)",
                                   "ja": "優先度（プリエンプティブ）"},
    "util.cpusched.algo.rr": {"ko": "라운드 로빈 (RR)", "en": "Round Robin (RR)", "ja": "ラウンドロビン（RR）"},
    "util.cpusched.algo.hrn": {"ko": "HRN (최고 응답률 우선)", "en": "HRN (Highest Response Ratio Next)",
                                "ja": "HRN（最高応答率優先）"},

    "util.cpusched.example.fcfs_basic": {"ko": "FCFS 예제 (24,3,3)", "en": "FCFS example (24,3,3)",
                                          "ja": "FCFS例（24,3,3）"},
    "util.cpusched.example.sjf_basic": {"ko": "SJF 예제", "en": "SJF example", "ja": "SJF例"},
    "util.cpusched.example.srtf_basic": {"ko": "SRTF 예제", "en": "SRTF example", "ja": "SRTF例"},
    "util.cpusched.example.prio_basic": {"ko": "우선순위 예제", "en": "Priority example", "ja": "優先度の例"},
    "util.cpusched.example.rr_basic": {"ko": "RR 예제 (할당량 4)", "en": "RR example (quantum 4)",
                                        "ja": "RR例（クアンタム4）"},
    "util.cpusched.example.hrn_basic": {"ko": "HRN 예제", "en": "HRN example", "ja": "HRN例"},
}
CpuSchedApp.tr_table = TRANSLATIONS

# -*- coding: utf-8 -*-
"""
FolderKit++ — 미니앱 아이콘 [v01]

모드 아이콘(image_edit.make_mode_icon)과 **같은 문법**으로 그린다:
색을 꽉 채운 원형 배지 + 그 위에 흰색 선으로 그린 글리프. 이렇게 해야
좌측 액티비티 바의 모드 아이콘들과 Util 모드 안의 도구 아이콘들이
한 가족처럼 보인다. 이미지 파일(PNG)을 쓰지 않고 코드로 그리는 것도
기존 방식 그대로다 — 해상도에 무관하고 배포 파일도 늘지 않는다.
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QIcon


def make_app_icon(kind: str, color: str, size: int = 24) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # 배지(원) — 모드 아이콘과 동일한 규칙
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawEllipse(1, 1, size - 2, size - 2)

    # 24 기준으로 그린 뒤 실제 크기에 맞춰 축척
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor("#ffffff"), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "calc":
        # 계산기 — 본체 + 표시창 + 키 4개
        p.drawRoundedRect(QRectF(6, 4.5, 12, 15), 2, 2)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(8, 6.5, 8, 3), 0.8, 0.8)
        for cx in (9.2, 12, 14.8):
            for cy in (12.6, 16.2):
                p.drawEllipse(QPointF(cx, cy), 0.95, 0.95)
    elif kind == "home":
        # 도구 모음 홈 — 2x2 타일(앱 서랍)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        for x in (5.5, 13):
            for y in (5.5, 13):
                p.drawRoundedRect(QRectF(x, y, 5.5, 5.5), 1.2, 1.2)
    elif kind == "kmap":
        # 카르노맵 — 3x3 격자선 + 체크무늬로 채운 칸(0/1이 섞여 있는 표를 연상)
        pen.setWidthF(1.1)
        p.setPen(pen)
        for i in range(4):
            x = 5 + i * 4.67
            p.drawLine(QPointF(x, 5), QPointF(x, 19))
            y = 5 + i * 4.67
            p.drawLine(QPointF(5, y), QPointF(19, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        for (cx, cy) in [(0, 0), (1, 1), (2, 0)]:
            x = 5 + cx * 4.67
            y = 5 + cy * 4.67
            p.drawRect(QRectF(x + 0.6, y + 0.6, 3.47, 3.47))
    elif kind == "graph":
        # 함수 그래프 — L자 좌표축 + 곡선 하나(사인 곡선 느낌)
        pen.setWidthF(1.3)
        p.setPen(pen)
        p.drawLine(QPointF(5.5, 5), QPointF(5.5, 19))     # y축
        p.drawLine(QPointF(5.5, 19), QPointF(19.5, 19))   # x축
        path_pen = QPen(QColor("#ffffff"), 1.7)
        path_pen.setCapStyle(Qt.RoundCap)
        p.setPen(path_pen)
        pts = [QPointF(6.5, 16), QPointF(9.5, 8), QPointF(12.5, 15.5),
               QPointF(15.5, 9), QPointF(18.5, 13)]
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])
    elif kind == "meal":
        # 급식 — 밥그릇(반원) + 위로 오르는 김(수증기) 두 줄
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.drawArc(QRectF(5.5, 11, 13, 9), 0, -180 * 16)
        p.drawLine(QPointF(5.5, 11), QPointF(18.5, 11))
        steam_pen = QPen(QColor("#ffffff"), 1.3)
        steam_pen.setCapStyle(Qt.RoundCap)
        p.setPen(steam_pen)
        p.drawLine(QPointF(9.5, 9), QPointF(8.5, 5.5))
        p.drawLine(QPointF(14.5, 9), QPointF(15.5, 5.5))
    elif kind == "schedule":
        # 학교 일정 — 달력(사각 틀 + 상단 구분선 + 걸이 두 개 + 오늘 표시 점)
        pen.setWidthF(1.3)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(5, 6, 14, 13), 1.5, 1.5)
        p.drawLine(QPointF(5, 10), QPointF(19, 10))
        p.drawLine(QPointF(8.5, 4.5), QPointF(8.5, 7.5))
        p.drawLine(QPointF(15.5, 4.5), QPointF(15.5, 7.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRoundedRect(QRectF(13.3, 12.3, 3.4, 3.4), 0.8, 0.8)
    elif kind == "neiscounter":
        # 나이스 글자수 계산기 — 문서(줄 3개) + 오른쪽에 체크 표시
        pen.setWidthF(1.3)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(5, 4.5, 11, 15), 1.3, 1.3)
        for y in (8.5, 11.5, 14.5):
            p.drawLine(QPointF(7, y), QPointF(13, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(16.5, 16.5), 3.6, 3.6)
        check_pen = QPen(QColor(color), 1.6)
        check_pen.setCapStyle(Qt.RoundCap)
        check_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(check_pen)
        p.drawLine(QPointF(15, 16.6), QPointF(16.2, 17.8))
        p.drawLine(QPointF(16.2, 17.8), QPointF(18.2, 15.2))
    elif kind == "polar":
        # 극좌표 그래프 — 중심에서 뻗어나가는 장미선 느낌의 곡선 3개
        p.setBrush(Qt.NoBrush)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.drawEllipse(QPointF(12, 12), 1.6, 1.6)
        for ang in (90, 210, 330):
            rad = math.radians(ang)
            cx, cy = 12 + 6.5 * math.cos(rad), 12 - 6.5 * math.sin(rad)
            path_pts = []
            for i in range(9):
                a = math.radians(ang - 40 + i * 10)
                rr = 1.5 + 5.5 * math.sin(math.radians((i / 8) * 180))
                path_pts.append(QPointF(12 + rr * math.cos(a), 12 - rr * math.sin(a)))
            for i in range(len(path_pts) - 1):
                p.drawLine(path_pts[i], path_pts[i + 1])
    elif kind == "bracket":
        # 대진표 — 토너먼트 브래킷 모양(선 3개가 오른쪽으로 모이는 형태)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.drawLine(QPointF(5, 6), QPointF(10, 6))
        p.drawLine(QPointF(5, 12), QPointF(10, 12))
        p.drawLine(QPointF(5, 18), QPointF(10, 18))
        p.drawLine(QPointF(10, 6), QPointF(10, 9))
        p.drawLine(QPointF(10, 12), QPointF(10, 9))
        p.drawLine(QPointF(10, 9), QPointF(14, 9))
        p.drawLine(QPointF(10, 18), QPointF(10, 15))
        p.drawLine(QPointF(14, 9), QPointF(14, 15))
        p.drawLine(QPointF(10, 15), QPointF(14, 15))
        p.drawLine(QPointF(14, 12), QPointF(19, 12))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(19.5, 12), 1.8, 1.8)
    elif kind == "cpusched":
        # CPU 스케줄링 — 길이가 다른 가로 막대 3개(간트차트를 단순화한 모양)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(4, 4.5, 15, 3), 1, 1)
        p.drawRoundedRect(QRectF(4, 10.5, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(4, 16.5, 13, 3), 1, 1)

    elif kind == "seating":
        # 좌석표 — 위쪽 교탁(가로 막대) + 아래 책상 2x3 그리드
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(6, 3.5, 12, 2.6), 1, 1)
        for row in (8, 13.5, 19):
            for col in (5, 13.5):
                p.drawRoundedRect(QRectF(col, row, 6, 4.2), 1, 1)

    elif kind == "timetable":
        # 컴시간 알리미 — 작은 달력형 격자(2행 x 4열 칸)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2, 2)
        p.drawLine(QPointF(3.5, 9.5), QPointF(20.5, 9.5))
        for x in (8, 12.3, 16.6):
            p.drawLine(QPointF(x, 4.5), QPointF(x, 19.5))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(4.6, 5.6, 2.4, 2.4), 0.6, 0.6)

    elif kind == "phonetransfer":
        # 갤럭시폰 사진 옮기기 — 휴대폰 외곽 + 안에 작은 사진 아이콘
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(7, 3, 10, 18), 2, 2)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(8.6, 6, 6.8, 6.8), 1, 1)
        p.drawEllipse(QPointF(12, 17.5), 1.1, 1.1)

    elif kind == "codon":
        # 코돈표 계산기 — DNA 이중나선을 간단히(지그재그 두 가닥 + 연결선)
        pen.setWidthF(1.4)
        p.setPen(pen)
        pts_a, pts_b = [], []
        for i in range(5):
            t = i / 4.0
            y = 5 + t * 14
            xa = 8 + 4 * math.sin(t * math.pi * 2)
            xb = 16 - 4 * math.sin(t * math.pi * 2)
            pts_a.append(QPointF(xa, y))
            pts_b.append(QPointF(xb, y))
        for i in range(len(pts_a) - 1):
            p.drawLine(pts_a[i], pts_a[i + 1])
            p.drawLine(pts_b[i], pts_b[i + 1])
        for i in range(len(pts_a)):
            if i % 2 == 0:
                p.drawLine(pts_a[i], pts_b[i])

    elif kind == "codonsim":
        # 코돈시뮬 — w→x→y→z 연쇄를 점 4개 + 화살표 3개로 단순화
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        xs = [4.5, 9.5, 14.5, 19.5]
        for x in xs:
            p.drawEllipse(QPointF(x, 12), 2.0, 2.0)
        pen.setWidthF(1.3)
        p.setPen(pen)
        for x0, x1 in zip(xs, xs[1:]):
            p.drawLine(QPointF(x0 + 2.2, 12), QPointF(x1 - 2.2, 12))

    elif kind == "lucky":
        # 행운의 번호 — 원형 드럼 + 안의 공 3개 + 위쪽 포트
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(12, 13), 7.5, 7.5)
        p.drawLine(QPointF(12, 5.5), QPointF(12, 3))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        for cx, cy in ((9.4, 15.6), (14.6, 15.6), (12, 11.2)):
            p.drawEllipse(QPointF(cx, cy), 2.0, 2.0)

    elif kind == "timerclock":
        # 타이머 — 시계 원 + 짧은(시침)·긴(분침) 바늘 + 위쪽 버튼 꼭지
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(12, 13), 7.5, 7.5)
        p.drawLine(QPointF(12, 4), QPointF(10.5, 2.3))
        p.drawLine(QPointF(12, 4), QPointF(13.5, 2.3))
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.drawLine(QPointF(12, 13), QPointF(12, 8.5))
        p.drawLine(QPointF(12, 13), QPointF(15.2, 14.6))

    elif kind == "sudoku":
        # 스도쿠 — 3x3 굵은 테두리 격자 + 안쪽 가는 선 + 점 몇 개(숫자 암시)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(3, 3, 18, 18))
        thin = QPen(QColor(color), 1.0)
        p.setPen(thin)
        for i in (1, 2):
            x = 3 + i * 6
            p.drawLine(QPointF(x, 3), QPointF(x, 21))
            y = 3 + i * 6
            p.drawLine(QPointF(3, y), QPointF(21, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        for (cx, cy) in ((6, 6), (15, 9), (9, 15), (18, 18)):
            p.drawEllipse(QPointF(cx, cy), 1.3, 1.3)

    elif kind == "cheer":
        # 응원의 메시지 — 풍선(타원+매듭+줄) + 비스듬히 날아가는 화살
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(11, 3.5, 8.5, 10))
        p.drawLine(QPointF(15.2, 13.5), QPointF(14.2, 20.5))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.drawLine(QPointF(4, 18), QPointF(11.5, 10.5))
        p.drawLine(QPointF(11.5, 10.5), QPointF(9, 10.8))
        p.drawLine(QPointF(11.5, 10.5), QPointF(11.2, 13))

    else:
        # 알 수 없는 종류 — 가운데 점 하나(자리 표시). 예외를 던지지 않는 편이
        # 낫다: 새 도구를 만들다가 아이콘 종류를 아직 안 정했을 때도 목록이
        # 정상적으로 뜨고, 아이콘만 밋밋하게 보일 뿐이다.
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(12, 12), 3.2, 3.2)

    p.end()
    return QIcon(pix)

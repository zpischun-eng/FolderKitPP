# -*- coding: utf-8 -*-
"""
FolderKit++ — 윈도·맥 공용 처리 [v51]

소스 하나로 윈도 exe와 맥 앱(.app)을 함께 만든다. 운영체제마다 다른 부분은
되도록 이 파일 한 곳에 모은다.

- 맥에서 빼는 것(제약이 큰 기능은 과감히 제외 — 사용자 결정)
  · 갤럭시폰 사진 옮기기(adb)
  · 학교 업무·수업용 미니앱(급식·학사일정·나이스·시간표·좌석표·대진표·카르노맵·
    극좌표·코돈·CPU 스케줄링) — 계산기·함수 그래프·스도쿠·행운의 번호·
    응원의 메시지·타이머처럼 "그냥 쓰는 도구"만 남긴다
- 맥에서 바꾸는 것
  · 탐색기 → Finder (open -R), 화면 문구도 "Finder"로
  · Consolas(윈도 전용 고정폭 글꼴) → Menlo
  · 숨김 파일: 점(.)으로 시작 + Finder 숨김 표시(UF_HIDDEN)
"""
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# 맥에서도 보이는 미니앱(내부 키). 여기 없는 미니앱은 맥에서 목록에 아예 안 나온다.
MAC_APP_IDS = ("calc", "graph", "sudoku", "lucky", "cheer", "timerclock")


def app_available(app_id, is_mac=None):
    """이 운영체제에서 그 미니앱을 보여 줄지."""
    if is_mac is None:
        is_mac = IS_MAC
    return (not is_mac) or app_id in MAC_APP_IDS


def mono_font(size, bold=False):
    """고정폭 글꼴 — 윈도는 Consolas, 맥은 Menlo, 그 밖엔 시스템 고정폭."""
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies(["Consolas", "Menlo", "Monaco", "DejaVu Sans Mono", "Courier New"])
    f.setStyleHint(QFont.Monospace)
    f.setPointSize(size)
    f.setBold(bold)
    return f


MONO_CSS = "Consolas,Menlo,Monaco,'Courier New',monospace"

# 맥에서 "탐색기"를 "Finder"로 바꿔 보여 줄 문구(키 → 언어별). 내부 키는 그대로.
MAC_TEXT_OVERRIDES = {
    "msg.title.open_explorer": {"ko": "Finder에서 보기", "en": "Show in Finder", "ja": "Finderで表示"},
    "log.common.opened_explorer": {"ko": "[Finder에서 보기] {a0}", "en": "[Show in Finder] {a0}",
                                   "ja": "[Finderで表示] {a0}"},
    "msg.title.open_explorer_failed": {"ko": "Finder 열기 실패", "en": "Could not open Finder",
                                       "ja": "Finderを開けませんでした"},
    "msg.common.open_explorer_error": {"ko": "Finder를 여는 중 오류가 발생했습니다:\n{a0}",
                                       "en": "An error occurred while opening Finder:\n{a0}",
                                       "ja": "Finderを開く際にエラーが発生しました:\n{a0}"},
    "menu.reveal_in_explorer": {"ko": "Finder에서 보기", "en": "Show in Finder", "ja": "Finderで表示"},
    "dupfind.tree.open_tip": {"ko": "더블클릭: Finder에서 보기 · 오른쪽 클릭: 메뉴",
                              "en": "Double-click: show in Finder · Right-click: menu",
                              "ja": "ダブルクリック: Finderで表示 · 右クリック: メニュー"},
}


def apply_platform_texts(table, is_mac=None):
    """맥이면 번역표(table = i18n.TR)의 해당 문구를 위 값으로 덮어쓴다."""
    if is_mac is None:
        is_mac = IS_MAC
    if is_mac:
        for key, entry in MAC_TEXT_OVERRIDES.items():
            table[key] = dict(table.get(key, {}), **entry)


def file_manager_command(path, is_dir):
    """파일 관리자에서 열기 명령(윈도 탐색기 / 맥 Finder / 리눅스 기본 앱)."""
    if IS_WIN:
        return f'explorer /n,"{path}"' if is_dir else f'explorer /select,"{path}"'
    if IS_MAC:
        return ["open", path] if is_dir else ["open", "-R", path]
    import os
    return ["xdg-open", path if is_dir else os.path.dirname(path)]

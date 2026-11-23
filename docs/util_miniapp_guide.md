# 미니앱(유틸리티 도구) 추가 가이드

FolderKit++ v01 기준. 이 문서 하나만 보고도 새 도구를 붙일 수 있게 쓰는 것이 목표다.

---

## 0. 설계 원칙 세 줄 요약

1. **미니앱은 MainWindow를 모른다.** `UtilHost` 어댑터를 통해서만 콘솔 로그·상태바·설정에 접근한다.
2. **새 도구를 추가할 때 `main_window.py`는 건드리지 않는다.** 손대는 파일은 `src/utils/__init__.py` 한 줄뿐이다.
3. **내부 키와 표시 문구를 절대 섞지 않는다.** 저장·비교는 `id` 같은 내부 키로만, 화면 문구는 `tr()`로만.
4. **[v34] 화면은 `src/utils/ui_kit.py`의 부품(Card·버튼·canvas_frame·split)만으로 만든다.** 규칙은 `docs/util_ui_rules.md` 참고 — 골격 2종, 카드마다 제목 줄, 버튼 3등급 1크기.

---

## 1. 파일 만들기

`src/utils/mytool.py`

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ..i18n import tr
from ..styles import C, button_style
from .base import MiniApp


class MyToolWidget(QWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host                      # log() / status() / settings() / cfg
        lay = QVBoxLayout(self)
        self.lbl = QLabel()
        lay.addWidget(self.lbl)
        self.retranslate()

    def retranslate(self):
        self.lbl.setText(tr("util.mytool.hello"))


class MyToolApp(MiniApp):
    id = "mytool"          # 내부 키 — 화면에 절대 노출되지 않는다
    icon = "mytool"        # icons.make_app_icon()에 글리프를 추가해야 한다
    category = "logic"     # CATEGORY_ORDER 참고

    def __init__(self):
        self._widget = None

    def build(self, host):
        self._widget = MyToolWidget(host)
        return self._widget

    def retranslate(self):
        if self._widget is not None:
            self._widget.retranslate()

    def has_unsaved(self):
        return False       # 저장할 문서가 있는 도구라면 여기서 판단


TRANSLATIONS = {
    "util.mytool.title": {"ko": "내 도구", "en": "My Tool", "ja": "マイツール"},
    "util.mytool.desc":  {"ko": "설명 한 줄", "en": "One-line description", "ja": "説明"},
    "util.mytool.hello": {"ko": "안녕", "en": "Hello", "ja": "こんにちは"},
}
MyToolApp.tr_table = TRANSLATIONS   # 클래스 본문에서는 아직 참조 불가라 여기서 붙인다
```

`util.<id>.title` 과 `util.<id>.desc` 두 키는 **필수**다 — 좌측 목록·홈 카드·검색이 이 값을 쓴다.

## 2. 레지스트리에 등록

`src/utils/__init__.py`

```python
from .mytool import MyToolApp

_APP_CLASSES = [
    CalculatorApp,
    MyToolApp,      # ← 이 한 줄
]
```

끝이다. 좌측 목록·홈 카드·검색·다국어·최근 사용 목록에 자동으로 붙는다.

## 3. 아이콘 글리프 추가

`src/utils/icons.py` 의 `make_app_icon()` 에 `elif kind == "mytool":` 가지를 하나 넣는다.
24×24 좌표계에 흰색 선으로 그리면 된다(원형 배지는 공통 코드가 이미 그려 준다).
빠뜨려도 죽지는 않고 기본 점 아이콘이 나온다.

---

## 4. 지켜야 할 규칙

### 버튼 색 (v50에서 정한 규칙을 그대로 승계)

| 성격 | 색 | 상수 |
|---|---|---|
| 주 실행 | 모드 강조색 | `C.UTIL_MAIN` |
| 보조 실행 | 슬레이트 | `BTN_SECONDARY_SLATE` |
| 중립·유틸리티(취소·초기화) | 진한 슬레이트 | `BTN_NEUTRAL_BG` |
| 파괴적 동작(삭제) | 빨강 | `BTN_DESTRUCTIVE_BG` |

반드시 `styles.button_style()`을 거칠 것. 직접 `setStyleSheet`에 배경색을 박으면
비활성(`setEnabled(False)`) 상태가 활성과 똑같이 보이는 문제가 되살아난다.

### 무거운 의존성 금지

matplotlib·numpy·sympy 등을 끌어들이면 PyInstaller 산출물이 수십 MB 늘고 빌드도 느려진다.
그래프는 `QPainter`로, 수식 처리는 표준 `ast`로 해결하는 것을 우선 검토할 것
(계산기가 그 방식의 실제 예다 — `src/utils/expr.py`).

무거운 import가 꼭 필요하면 **`build()` 안에서** import 한다. 프로그램 기동 시간에
영향을 주지 않는다(미니앱은 처음 열릴 때 한 번만 build된다).

### 단축키는 위젯 안으로

`QShortcut`을 쓸 때는 `setContext(Qt.WidgetWithChildrenShortcut)`으로 범위를 좁힌다.
`ApplicationShortcut`으로 등록하면 다른 모드(예: 이미지 편집의 Space/Del)와 충돌한다.

### 시간이 걸리는 작업은 스레드로

Qt 위젯은 메인 스레드에서만 만지고, 워커에서는 시그널로 결과만 넘긴다.
FolderKit의 `ThumbnailLoaderWorker`·`DuplicateScanThread`가 참고 예시다.

### 저장은 QSettings, 키는 `util.<id>.*`

`host.settings()`가 돌려주는 `QSettings("SRIHS", "FolderSync")`를 쓴다.
조직/앱 이름은 절대 바꾸지 말 것 — 바꾸면 기존 사용자의 언어·즐겨찾기·캐시 설정이
전부 초기화된다.

---

## 4-1. [v44] 움직이는 화면(애니메이션)이 필요한 도구

추첨기·게임처럼 초당 60프레임으로 움직이는 화면은 `src/utils/anim_kit.py`의
`AnimCanvas`를 상속한다(행운의 번호·응원의 메시지가 실제 예).

- `advance(dt)`에 한 스텝의 진행을, `paint_scene(p)`에 그리기를 쓴다. 좌표는 항상
  **논리 1600×900** — 실제 창 크기에 맞춘 확대·축소는 캔버스가 한다.
- 물리는 고정 간격(`PHYS_DT`=1/60초)으로만 진행한다. 결과가 걸린 계산(추첨 등)은
  Qt 없는 순수 모듈에 두고(`anim_physics.py`, `*_logic.py`), 난수는 시드를 받은
  `random.Random` 하나만 쓴다 → 헤드리스 테스트에서 `run_steps(n)`으로 화면 없이
  검증할 수 있고, 시드를 기록하면 재현도 된다.
- 다른 도구로 넘어가면(hide) 루프가 자동으로 멈춘다.
- 전체화면 발표는 `FullscreenPresenter(canvas)`의 `enter()/exit()` — 캔버스만 떼어
  전체화면 창으로 옮겼다 되돌리므로 MainWindow·UtilHost를 고칠 필요가 없다.
- 공처럼 반복해 그리는 것은 `BallSpriteCache`로 미리 그려 둔다(고해상도 배율 반영).
- 저장 대화상자의 기본 위치는 `config.desktop_file(파일명)`(바탕화면)을 쓴다 —
  파일명만 넘기면 개발 폴더·설치 폴더가 먼저 떠서 사용자가 헷갈린다.

## 5. 검증

```bash
QT_QPA_PLATFORM=offscreen python3 tests_headless.py
```

새 도구를 추가했으면 이 파일에 섹션을 하나 늘려 최소한
(1) 열기/지연 생성, (2) 핵심 동작 1~2개, (3) 언어 3종 전환 시 예외 없음
을 확인하는 것을 권장한다.

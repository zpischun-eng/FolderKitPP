# 미니앱 UI 규격 v1 (v34~)

11개 미니앱이 각자 정하던 배치·버튼·여백을 한 벌의 규칙으로 통일한다.
부품은 전부 `src/utils/ui_kit.py`에 있고, **미니앱은 이 부품만 쓴다**.
`styles.button_style()`을 미니앱에서 직접 부르면 헤드리스 테스트가 규격
위반으로 잡는다(격자형 키패드처럼 정말 예외가 필요한 줄에만
`# ui_kit:allow` 주석을 붙인다).

## A. 화면 골격은 두 가지

| 골격 | 쓰는 앱 | 부품 |
|---|---|---|
| 좌/우 분할 — 입력(좌) → 결과·캔버스(우), 한쪽 폭 고정 340px | kmap, graph, polar, bracket, codon, codonsim, neis | `split_lr()` 또는 `setFixedWidth(RIGHT_PANEL_W)` |
| 상/하 분할 — 설정(상, 필요한 높이만) → 큰 본문(하, 남는 공간 전부) | calc*, meal, schedule, cpusched | `split_tb()` |

\* 계산기는 키패드가 커지면 안 되므로 왼쪽 카드를 고정 폭으로 두는 좌/우 변형.

카드 두 개를 같은 줄에 나란히 두면(cpusched 상단) 높이가 자동으로 같아진다.

## B. 모든 구역은 카드, 모든 카드에는 제목 줄

- `Card(title)` — 배경 `UTIL_BG`, 테두리 `BORDER`, 둥근 모서리 8px, 안쪽 여백 12px.
  맨바닥(`self` 위)에 위젯을 바로 놓지 않는다.
- 제목 줄 = 왼쪽 제목(13px bold) + 오른쪽 **툴바**(`card.add_tool`). 그 카드에만
  관계된 콤보·토글·작은 조작(예제 선택, 변수 개수, RAD/DEG, ◀ ▶ 재생, 칸 너비
  슬라이더, ⚙ 설정)은 전부 툴바로 간다.
- 본문 = `card.add_body`. 폼처럼 위에서부터 채우는 카드는 마지막에
  `card.body.addStretch()`.
- 하단 버튼 줄 = `card.add_footer` (오른쪽 정렬). 설명·오류 문구는
  `card.add_footer_left`.
- 캔버스(그래프·간트·달력·표·텍스트 편집기)는 `canvas_frame()`으로 감싸
  **흰 배경 + 연한 테두리**로 카드 본문을 꽉 채운다. 핑크 카드 위에 흰 캔버스가
  "떠 보이지" 않게 여백 없이 채우는 것이 핵심.

## C. 버튼은 3등급 × 1크기

| 등급 | 부품 | 색 | 용도 | 카드당 |
|---|---|---|---|---|
| 주 | `primary_button` | `UTIL_MAIN` | 실행·생성·번역·적용 | 최대 1개, footer 맨 오른쪽 |
| 보조 | `secondary_button` | 슬레이트 | 저장·복사·초기화·불러오기 | 여러 개, 주 버튼 왼쪽 |
| 위험 | `danger_button` | 빨강 | 삭제·전체 지우기 | 최소, footer 맨 왼쪽 |

- 크기는 한 가지: 높이 28px, 글자 12px, padding `4px 12px`.
- 작은 조작(◀ ▶ + × ✎ ⚙)은 `tool_button` (24×24, 테두리만).
- 모드 전환(mRNA/DNA, 일별/주간/월별, 토너먼트/리그, RAD/DEG)은 `toggle_button`
  (체크 = 자홍 채움). 스타일을 직접 바꾸지 말고 `setChecked()`만 쓴다.
- 세로로 길게 늘어난 100% 폭 버튼은 금지 — footer에 가로로 놓는다.
- 격자형 키패드(계산기)는 예외 — `_key_style`에 `# ui_kit:allow`.

## D. 여백·글자·색

- 카드 사이 `CARD_SPACING`=10, 카드 안 `CARD_PADDING`=12, 컨트롤 사이 `CTRL_SPACING`=6.
- 글자: 제목 `title_label`(13 bold) / 본문 `body_label`(12) / 힌트·설명
  `hint_label`(11, `HINT_COLOR` 하나) / 오류 `error_label`(12 빨강, 팝업 금지).
- 도움말 문단은 카드 본문 맨 아래에 `hint_label`로.

## E. 앱 간 공통 위치

- 앱 전체 설정(나이스 학교 설정·인증키)은 **첫 카드 툴바의 ⚙ 버튼**
  (`NeisSettingsPanel.toggle`을 `card.add_tool`에, `.panel`을 `card.add_body`에).
- 저장 계열(PNG/Excel/인쇄/복사)은 **결과 카드 footer의 보조 버튼**.

## 새 미니앱 체크리스트

1. 골격을 A에서 하나 고른다.
2. 구역마다 `Card()`를 만들고 `retranslate()`에서 `set_title(tr(...))`.
3. 콤보·토글·작은 조작은 툴바, 버튼은 footer, 나머지는 본문.
4. 버튼은 `primary/secondary/danger/tool/toggle_button`만.
5. 캔버스는 `canvas_frame()`.
6. `tests_headless.py`의 "UI 규격" 섹션이 통과하는지 확인.

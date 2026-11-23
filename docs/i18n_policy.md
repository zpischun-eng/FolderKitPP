# FolderKit 다국어(i18n) 정책 — 적용 범위와 새 언어 추가 체크리스트

이 문서는 "다국어가 화면 일부에만 적용되고 팝업/콘솔/특정 콤보박스는
빠지는" 문제가 v38→v41에 걸쳐 세 번이나 반복된 뒤에 작성됐다. 앞으로
언어를 추가하거나 새 화면을 만들 때 이 문서를 체크리스트로 쓴다.

## 1. 적용 범위 — "사용자 눈에 보이는 문자열은 예외 없이 전부"

아래 항목 중 어느 하나라도 빠지면 "일부만 다국어"라는 문제가 재발한다.

| 범주 | 예시 | 흔히 빠지는 이유 |
|---|---|---|
| 버튼·라벨·툴팁 | 메뉴 버튼, 콤보박스 라벨 | (1차 적용 때부터 대체로 잘 됨) |
| 표준 QMessageBox 팝업 | `QMessageBox.information/question/warning/critical(...)` | — |
| **커스텀 QMessageBox 인스턴스** | `box = QMessageBox(self); box.setText(...); box.addButton(...)` | 정적 메서드만 검색하면 놓친다 |
| 콘솔 로그 | `self.logmsg(...)` | "로그는 개발자용"이라고 착각하기 쉬움 |
| 상태바 | `self.status.showMessage(...)` | 존재 자체를 잊기 쉬움 |
| 컨텍스트 메뉴 항목 | `menu.addAction("...")` | 메뉴는 팝업으로 안 치기 쉬움 |
| QInputDialog / QFileDialog 제목·라벨 | `QFileDialog.getExistingDirectory(self, "...")` | 팝업 검색 패턴에서 제외되기 쉬움 |
| QProgressDialog 라벨·취소 버튼 | `QProgressDialog("...", "취소", ...)` | 별도 위젯이라 누락되기 쉬움 |
| 커스텀 다이얼로그(다른 파일) | `dialogs.py`의 미리보기 다이얼로그 | "메인 파일만 봤음" — 다른 모듈 확인 누락 |
| **로그/메시지 틀 안에 끼워 넣는 변수 값** | `direction_label = {"both": "양방향..."}` 처럼, 문장 틀은 tr()로 감쌌지만 그 안에 넣는 단어 자체가 하드코딩 | 제일 놓치기 쉬움 — 아래 2절 참고 |
| 콤보박스/드롭다운 항목 | 크롭 비율, 정렬 기준 등 | 내부 상태값과 얽혀 있으면 "일부러 뺀 것"처럼 보임 (3절 참고) |
| 개발자 콘솔 `print()` | 패키징된 exe에선 안 보이지만 디버그 실행 시 보임 | "안 보이니까 상관없다"고 넘기기 쉬움 |

## 2. 검증 방법 — grep이 아니라 AST로 전수조사

`grep "안녕\|취소\|확인"` 같은 키워드 검색은 표현이 다양해서 반드시
빠뜨린다. 대신 **소스 코드의 모든 문자열 리터럴**을 한글 포함 여부로
훑는 스크립트를 새 언어를 추가할 때마다(또는 새 화면을 만들 때마다)
돌린다:

```python
import ast, glob

def has_hangul(s):
    return any('\uac00' <= ch <= '\ud7a3' for ch in s)

for fname in sorted(glob.glob("src/*.py")):
    if fname.endswith("i18n.py"):
        continue  # 번역표 자체는 제외
    src = open(fname, encoding="utf-8").read()
    tree = ast.parse(src)
    # 독립적인 문자열 statement(주석 대용 docstring/설명 블록)는 제외
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
           and isinstance(node.value.value, str):
            doc_lines.update(range(node.lineno, node.end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
           and has_hangul(node.value) and node.lineno not in doc_lines:
            print(fname, node.lineno, repr(node.value)[:80])
        elif isinstance(node, ast.JoinedStr):
            txt = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if has_hangul(txt) and node.lineno not in doc_lines:
                print(fname, node.lineno, repr(txt)[:80])
```

이 스크립트의 출력이 **0줄**이 될 때까지 반복한다. "번역표(i18n.py)
자체"만 예외로 둔다 — 그 외 모든 소스 파일이 대상이다.

## 3. 핵심 원칙 — 내부 코드(값)와 UI 표시(문구)는 원천 분리한다

이건 이번 프로젝트에서 크롭 비율 콤보박스가 두 번이나 문제를 일으킨
근본 원인이다. 규칙은 이렇다:

> **화면에 보이는 문구를 프로그램 내부 로직의 판단 기준이나 저장값으로
> 절대 쓰지 않는다.** 내부에는 언어와 무관한 안정적인 "키"(영문 식별자,
> enum, 코드값)만 저장·비교·분기하고, 그 키를 화면에 표시할 때만
> `tr()`로 그 순간의 언어에 맞는 문구로 변환한다.

체크리스트:
- [ ] `if some_value == "확인"` 처럼 번역 가능한 문자열과 직접 비교하는
      코드가 있는가? → 있다면 그 값은 애초에 번역되면 안 되는 내부
      키였어야 한다.
  - 실제 있었던 문제: `if self.ratio == "원본 비율"`, `CropState.ratio`가
    콤보박스의 "보이는 텍스트 그 자체"를 저장.
- [ ] 콤보박스/드롭다운에 `addItems(["문구1", "문구2"])`처럼 화면 문구를
      직접 채워 넣고, 그 `currentText()`를 저장하거나 비교에 쓰는가?
      → `addItem(화면_문구, 내부_키)`로 바꾸고, 저장·비교는
      `currentData()`/`findData()`로 한다. 언어가 바뀌면
      `setItemText(i, 새_문구)`로 항목 텍스트만 갱신하고 `itemData`는
      건드리지 않는다(선택 상태가 그대로 유지된다).
- [ ] dict의 key로 화면 문구를 쓰고 있는가(`{"양방향": ..., "단방향": ...}`)?
      → key는 코드값("both"/"one_way")으로, 화면 문구는 값을 표시할
      때 `tr()`로 계산한다.
- [ ] 파일명, 설정 파일에 저장되는 값, DB/캐시 키에 화면 문구를 그대로
      쓰고 있는가? → 이것도 같은 문제다. 저장 형식은 항상 키 기준.

이 원칙을 지키면 "언어를 나중에 추가했더니 저장된 상태가 깨진다"는
문제 자체가 애초에 발생하지 않는다.

## 4. 새 언어를 추가할 때 순서

1. `src/i18n.py`의 `LANGUAGES`/`LANGUAGE_LABELS`에 새 언어 코드 추가.
2. `TR` 딕셔너리의 **모든** 키에 그 언어의 번역을 채운다(빠진 키가 있으면
   `tr()`가 fallback으로 다른 언어를 보여주게 되어 있는지 `i18n.py`의
   구현을 확인 — fallback이 없다면 키 이름 자체가 화면에 노출된다).
3. 위 2절의 AST 스크립트를 돌려 하드코딩된 한글(혹은 원래 언어) 문자열이
   없는지 재확인 — 이건 새 언어를 추가하는 것과 무관하게 항상 통과해
   있어야 하는 상태이지만, 회귀가 없었는지 다시 한번 확인하는 차원.
4. 3절의 원칙(내부 키 vs 화면 문구 분리)을 지키고 있는 콤보박스/상태값이
   여전히 잘 동작하는지, 언어를 오가며 상태가 안 깨지는지 실제로
   테스트한다(예: 이미지 A/B에 각각 다른 옵션을 선택해 두고 언어를 여러
   번 전환해도 각자의 선택이 올바르게 복원되는지).

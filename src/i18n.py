# -*- coding: utf-8 -*-
"""
FolderKit — 다국어(i18n) 지원 [v25]

환경설정에서 언어를 고르면(한국어/영어/일본어) 메뉴·버튼명·롤오버 힌트가
전부 그 언어로 바뀐다. 구조는 단순하게: 문자열 하나마다 "키"를 붙이고,
그 키에 대응하는 한/영/일 3개 번역을 딕셔너리(TR)에 나란히 적어 둔다.

사용법:
    from .i18n import tr
    btn.setText(tr("sync.btn_view"))
    btn.setToolTip(tr("sync.btn_view.tip"))

동적으로 값을 끼워 넣어야 하는 문자열은 {중괄호} 자리표시자를 쓰고
tr(key, folder=..., n=...)처럼 키워드 인자로 채운다.

[범위 안내] 이번 1차 적용은 화면에 상시 노출되는 버튼·라벨·롤오버 힌트·
환경설정 다이얼로그를 대상으로 한다. 크롭 비율/기준 콤보 항목("원본 비율" 등)은
내부적으로 그 텍스트 자체를 상태값으로 저장하고 있어(예: CropState.ratio),
지금 번역하면 언어를 바꿀 때 저장된 크롭 상태가 깨질 수 있어 이번 범위에서는
제외했다(추후 "표시 라벨"과 "내부 값"을 분리하는 리팩터링이 필요). 실행 중
콘솔 로그에 찍히는 상세 메시지들도 이번 범위 밖이며 한국어로 유지된다.
"""

LANGUAGES = ["ko", "en", "ja"]
LANGUAGE_LABELS = {"ko": "한국어", "en": "English", "ja": "日本語"}

_lang = "ko"


def set_language(lang: str):
    global _lang
    if lang in LANGUAGES:
        _lang = lang


def get_language() -> str:
    return _lang


def register_translations(table: dict):
    """[v01] 미니앱이 자기 번역 조각을 이 표에 얹는다.

    도구 문구까지 이 파일에 전부 적으면, 도구가 늘어날수록 i18n.py만 계속
    비대해진다(이미 2000줄). 그래서 각 미니앱 모듈이 자기 TRANSLATIONS를
    들고 있다가 등록 시점에 여기로 병합하는 방식을 쓴다.

    이미 있는 키는 덮어쓰지 않는다 — 도구가 실수로 공용 키(예: msg.title.info)와
    같은 이름을 쓰더라도 본체 문구가 조용히 바뀌어 버리는 사고를 막기 위해서다.
    """
    if not table:
        return
    for key, entry in table.items():
        if key not in TR:
            TR[key] = entry


def tr(key: str, **kwargs) -> str:
    entry = TR.get(key)
    if not entry:
        return key
    text = entry.get(_lang) or entry.get("ko") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


# =============================================================================
# 번역 테이블
# =============================================================================
TR = {
    # ---- 창 제목 ----
    "app.title": {
        "ko": "FolderKit++ {version} — 폴더·이미지 도구 + 유틸리티 모음",
        "en": "FolderKit++ {version} — Folder & Image Tools + Utilities",
        "ja": "FolderKit++ {version} — フォルダ・画像ツール + ユーティリティ",
    },

    # ---- 좌측 액티비티 바: 모드 아이콘 롤오버 힌트 ----
    "mode.sync.tip": {
        "ko": "폴더 동기화 — 왼쪽 폴더와 오른쪽 폴더의 내용을 서로 맞춰주는 기능입니다.",
        "en": "Folder Sync — Makes the contents of the left folder and the right folder match each other.",
        "ja": "フォルダ同期 — 左のフォルダと右のフォルダの中身を同じにそろえる機能です。",
    },
    "mode.rename.tip": {
        "ko": "파일명 변경 — 폴더 안에 있는 여러 파일의 이름을 한 번에 바꿔주는 기능입니다.",
        "en": "Rename Files — Renames many files inside a folder all at once.",
        "ja": "ファイル名変更 — フォルダの中の複数のファイル名を一度に変える機能です。",
    },
    "mode.imgedit.tip": {
        "ko": "이미지 편집 — 사진을 원하는 크기로 자르고 밝기를 조절하는 기능입니다.",
        "en": "Image Editing — Crops photos to the size you want and adjusts brightness.",
        "ja": "画像編集 — 写真を好きなサイズに切り取り、明るさを整える機能です。",
    },
    "mode.dupfind.tip": {
        "ko": "파일 찾기 — 폴더 안에서 똑같이 생긴 파일을 찾거나(중복 찾기), 원하는 확장자의 파일만 골라 찾는 기능입니다.",
        "en": "Find Files — Finds duplicate files, or files matching extensions you choose.",
        "ja": "ファイル検索 — フォルダの中の重複ファイルを探すか、指定した拡張子のファイルだけを検索する機能です。",
    },
    "mode.settings.tip": {
        "ko": "환경 설정 — 동기화 방향이나 언어처럼, 프로그램이 동작하는 기본 방식을 바꾸는 곳입니다.",
        "en": "Settings — Change how the program behaves by default, such as sync direction or language.",
        "ja": "環境設定 — 同期の方向や言語など、プログラムの基本的な動き方を変える場所です。",
    },

    # ---- 콘솔 로그 토글 ----
    "console.collapsed": {"ko": "▸ 콘솔 로그", "en": "▸ Console Log", "ja": "▸ コンソールログ"},
    "console.expanded": {"ko": "▾ 콘솔 로그", "en": "▾ Console Log", "ja": "▾ コンソールログ"},
    "console.tip": {
        "ko": "콘솔 로그 — 눌러서 펼치면, 프로그램이 지금까지 무슨 작업을 했는지 자세한 기록을 볼 수 있습니다.",
        "en": "Console Log — Click to expand and see a detailed record of what the program has done so far.",
        "ja": "コンソールログ — クリックして開くと、プログラムがこれまでに行った作業の詳しい記録が見られます。",
    },

    # ---- 동기화 모드 도구 ----
    "sync.btn_view": {"ko": "폴더 하위 구조 보기", "en": "View Folder Structure", "ja": "フォルダ構造を見る"},
    "sync.btn_view.tip": {
        "ko": "폴더 하위 구조 보기 — 왼쪽 폴더창에서 선택한 폴더 안에 어떤 폴더들이 들어있는지, 그 모양을 글자로 보여주는 기능입니다.",
        "en": "View Folder Structure — Shows, as text, what folders are inside the folder you selected on the left.",
        "ja": "フォルダ構造を見る — 左側で選んだフォルダの中に、どんなフォルダが入っているかを文字で見せる機能です。",
    },
    "sync.btn_save": {"ko": "구조 텍스트 저장", "en": "Save Structure as Text", "ja": "構造をテキスト保存"},
    "sync.btn_save.tip": {
        "ko": "구조 텍스트 저장 — 방금 본 폴더 구조를 글자 파일(txt)로 저장해서, 나중에 다시 열어볼 수 있게 해주는 기능입니다.",
        "en": "Save Structure as Text — Saves the folder structure you just viewed as a text (.txt) file so you can open it again later.",
        "ja": "構造をテキスト保存 — 今見たフォルダ構造をテキスト（txt）ファイルとして保存し、あとでまた開けるようにする機能です。",
    },
    "sync.combo_history.placeholder": {
        "ko": "최근 작업 히스토리...",
        "en": "Recent history...",
        "ja": "最近の作業履歴...",
    },
    "sync.combo_history.tip": {
        "ko": "최근 작업 히스토리 — 예전에 동기화했던 왼쪽·오른쪽 폴더 짝을 다시 골라서 빠르게 불러오는 기능입니다.",
        "en": "Recent History — Quickly reload a left/right folder pair you synced before.",
        "ja": "最近の作業履歴 — 以前同期した左右のフォルダの組み合わせを、また選んですぐに呼び出す機能です。",
    },
    "sync.btn_copy": {
        "ko": "좌측 구조를 우측으로 복사 (폴더만)",
        "en": "Copy Left Structure to Right (Folders Only)",
        "ja": "左の構造を右へコピー（フォルダのみ）",
    },
    "sync.btn_copy.tip": {
        "ko": "좌측 구조를 우측으로 복사 — 왼쪽에 있는 폴더 모양(폴더 이름들)만 그대로 오른쪽에도 만들어주는 기능입니다. 파일 내용은 옮기지 않습니다.",
        "en": "Copy Left Structure to Right — Recreates only the folder names from the left side on the right side. File contents are not copied.",
        "ja": "左の構造を右へコピー — 左側のフォルダの形（フォルダ名）だけを右側にも作る機能です。ファイルの中身は移動しません。",
    },
    "sync.btn_sync": {
        "ko": ">>>  좌 · 우 폴더 동기화  <<<",
        "en": ">>>  Sync Left & Right Folders  <<<",
        "ja": ">>>  左右フォルダを同期する  <<<",
    },
    "sync.btn_sync.tip": {
        "ko": "좌·우 폴더 동기화 — 왼쪽과 오른쪽 폴더의 파일들을 비교해서, 서로 다른 부분을 맞춰주는 기능입니다. 실행 전에 무엇이 바뀌는지 미리 보여줍니다.",
        "en": "Sync Left & Right Folders — Compares the files in the left and right folders and matches up the differences. Shows a preview before making changes.",
        "ja": "左右フォルダを同期する — 左右のフォルダのファイルを比べて、違うところをそろえる機能です。実行する前に、何が変わるかを先に見せてくれます。",
    },

    # ---- 파일명 변경 모드 도구 ----
    "rename.lbl_find": {"ko": "찾기:", "en": "Find:", "ja": "検索:"},
    "rename.lbl_replace": {"ko": "→ 바꾸기:", "en": "→ Replace:", "ja": "→ 置換:"},
    "rename.find_input.placeholder": {"ko": "찾을 단어", "en": "word to find", "ja": "検索する単語"},
    "rename.find_input.tip": {
        "ko": "찾을 단어 — 파일 이름 중에서 바꾸고 싶은 글자를 여기에 입력하세요.",
        "en": "Word to Find — Type the text you want to change in the file names here.",
        "ja": "検索する単語 — ファイル名の中で変えたい文字をここに入力します。",
    },
    "rename.replace_input.placeholder": {"ko": "바꿀 단어", "en": "new word", "ja": "置き換える単語"},
    "rename.replace_input.tip": {
        "ko": "바꿀 단어 — 위에서 찾은 글자를 대신할 새 글자를 여기에 입력하세요.",
        "en": "New Word — Type the text that should replace the word you found above.",
        "ja": "置き換える単語 — 上で見つけた文字の代わりに入れる新しい文字をここに入力します。",
    },
    "rename.chk_regex": {"ko": "정규식", "en": "Regex", "ja": "正規表現"},
    "rename.chk_regex.tip": {
        "ko": "정규식 — 체크하면 단순히 글자만 찾는 게 아니라, 좀 더 똑똑한 규칙(패턴)으로 파일 이름을 찾을 수 있습니다. 옆의 물음표를 누르면 사용법을 볼 수 있어요.",
        "en": "Regex — When checked, you can search using smarter patterns instead of plain text. Click the question mark next to it to see how it works.",
        "ja": "正規表現 — チェックすると、単純な文字だけでなく、もっと賢いルール（パターン）でファイル名を探せます。横の「？」を押すと使い方が見られます。",
    },
    "rename.help.tip": {
        "ko": (
            "<b>[정규표현식 사용법 — 쉽게 설명]</b><br>"
            "정규식을 체크하면 더 세밀한 규칙으로 찾을 수 있어요.<br><br>"
            "• <b>^</b> : 이름의 맨 앞 (예: <code>^AB</code> ➔ 맨 앞이 AB인 것만)<br>"
            "• <b>$</b> : 이름의 맨 뒤 (예: <code>AB$</code> ➔ 맨 뒤가 AB인 것만)<br>"
            "• <b>.</b> : 아무 글자 하나 (예: <code>A.C</code> ➔ AAC, ABC 등)<br>"
            "• <b>*</b> : 바로 앞 글자가 0개 이상 반복 (예: <code>A.*C</code> ➔ AC, ABC, ABBC 등)<br>"
            "• <b>\\d</b> : 숫자 하나 (예: <code>\\d+</code> ➔ 숫자 묶음)"
        ),
        "en": (
            "<b>[How to use Regex — simple guide]</b><br>"
            "When checked, you can search with finer rules.<br><br>"
            "• <b>^</b>: start of the name (e.g. <code>^AB</code> → only names starting with AB)<br>"
            "• <b>$</b>: end of the name (e.g. <code>AB$</code> → only names ending with AB)<br>"
            "• <b>.</b>: any one character (e.g. <code>A.C</code> → AAC, ABC, etc.)<br>"
            "• <b>*</b>: the character before repeats 0 or more times (e.g. <code>A.*C</code> → AC, ABC, ABBC, etc.)<br>"
            "• <b>\\d</b>: any one digit (e.g. <code>\\d+</code> → a run of digits)"
        ),
        "ja": (
            "<b>[正規表現の使い方 — かんたん説明]</b><br>"
            "チェックすると、もっと細かいルールで探せます。<br><br>"
            "• <b>^</b> : 名前の先頭（例: <code>^AB</code> → 先頭がABのものだけ）<br>"
            "• <b>$</b> : 名前の末尾（例: <code>AB$</code> → 末尾がABのものだけ）<br>"
            "• <b>.</b> : 任意の1文字（例: <code>A.C</code> → AAC, ABC など）<br>"
            "• <b>*</b> : 直前の文字が0回以上繰り返す（例: <code>A.*C</code> → AC, ABC, ABBC など）<br>"
            "• <b>\\d</b> : 数字1文字（例: <code>\\d+</code> → 数字の並び）"
        ),
    },
    "rename.btn_temp": {"ko": "임시 바꾸기", "en": "Preview Rename", "ja": "仮に変更"},
    "rename.btn_temp.tip": {
        "ko": "임시 바꾸기 — 실제로 저장하지 않고, 이름이 어떻게 바뀔지 화면에서 미리 보여주는 기능입니다.",
        "en": "Preview Rename — Shows how the names would change on screen, without actually saving anything yet.",
        "ja": "仮に変更 — 実際には保存せず、名前がどう変わるかを画面で先に見せる機能です。",
    },
    "rename.prefix_input.placeholder": {"ko": "추가할 접두사", "en": "prefix to add", "ja": "追加する接頭辞"},
    "rename.prefix_input.tip": {
        "ko": "추가할 접두사 — 모든 파일 이름의 맨 앞에 똑같이 붙일 글자를 입력하세요. (예: '2026_'을 붙이면 모든 파일 이름 앞에 2026_이 붙어요)",
        "en": "Prefix to Add — Type the text to attach to the very front of every file name (e.g. '2026_' adds 2026_ before every file name).",
        "ja": "追加する接頭辞 — すべてのファイル名の先頭に同じように付ける文字を入力します（例：「2026_」を付けると、全ファイル名の先頭に2026_が付きます）。",
    },
    "rename.btn_prefix": {"ko": "접두사 추가", "en": "Add Prefix", "ja": "接頭辞を追加"},
    "rename.btn_prefix.tip": {
        "ko": "접두사 추가 — 왼쪽 칸에 입력한 글자를 모든 파일 이름의 맨 앞에 붙여주는 기능입니다.",
        "en": "Add Prefix — Attaches the text you typed on the left to the front of every file name.",
        "ja": "接頭辞を追加 — 左の欄に入力した文字を、すべてのファイル名の先頭に付ける機能です。",
    },
    "rename.btn_normalize": {"ko": "이름 정규화(Mac 호환)", "en": "Normalize Names (Mac)", "ja": "名前を正規化（Mac互換）"},
    "rename.btn_normalize.tip": {
        "ko": "이름 정규화 — 맥(Mac)에서 만든 파일은 한글 자모가 따로 저장돼 있어서, 윈도우 탐색기에서는 글자가 깨져 보일 수 있습니다. 이 버튼을 누르면 그런 파일 이름들을 윈도우가 정상적으로 알아보는 형태로 실제로 고쳐줍니다.",
        "en": "Normalize Names — Files made on a Mac sometimes store Korean letters split into separate parts, which can look broken in Windows Explorer. This button actually rewrites those file names into the form Windows displays correctly.",
        "ja": "名前を正規化 — Macで作られたファイルはハングルの字母が分解されて保存されていることがあり、Windowsのエクスプローラーでは文字が壊れて見える場合があります。このボタンはそのファイル名を、Windowsが正しく表示できる形に実際に書き換えます。",
    },
    "rename.header.idle": {
        "ko": "파일명 변경 — 좌측에서 폴더를 먼저 선택하세요",
        "en": "Rename Files — First select a folder on the left",
        "ja": "ファイル名変更 — まず左側でフォルダを選んでください",
    },
    "rename.header.loaded": {
        "ko": "파일명 변경: {folder}  (파일 {nfiles}개 · 폴더 {ndirs}개)",
        "en": "Rename Files: {folder}  ({nfiles} files · {ndirs} folders)",
        "ja": "ファイル名変更: {folder}  (ファイル{nfiles}個・フォルダ{ndirs}個)",
    },
    "rename.btn_apply": {"ko": "이름바꾸기 (적용)", "en": "Rename (Apply)", "ja": "名前変更（適用）"},
    "rename.btn_apply.tip": {
        "ko": "이름바꾸기 (적용) — 지금까지 설정한 대로 실제 파일 이름을 바꾸는 기능입니다. 누르면 바로 적용되니, 결과를 잘 확인한 뒤에 눌러주세요.",
        "en": "Rename (Apply) — Actually renames the files according to the settings above. This takes effect immediately, so check the result carefully before clicking.",
        "ja": "名前変更（適用） — これまで設定した通りに、実際のファイル名を変える機能です。押すとすぐに適用されるので、結果をよく確認してから押してください。",
    },

    # ---- 이미지 편집 모드 도구 ----
    "imgedit.lbl_ratio": {"ko": "크롭 비율:", "en": "Crop Ratio:", "ja": "切り取り比率:"},
    "imgedit.combo_ratio.tip": {
        "ko": "크롭 비율 — 사진을 어떤 가로세로 비율로 자를지 고르는 곳입니다. (예: 1:1을 고르면 정사각형으로 잘라요)",
        "en": "Crop Ratio — Choose the width-to-height ratio to crop the photo to (e.g. 1:1 crops it into a square).",
        "ja": "切り取り比率 — 写真をどんな縦横比で切り取るかを選ぶところです（例：1:1を選ぶと正方形に切り取ります）。",
    },
    "imgedit.lbl_basis": {"ko": "기준:", "en": "Basis:", "ja": "基準:"},
    "imgedit.combo_basis.tip": {
        "ko": "기준 — 크롭 영역의 크기를 정할 때, 사진의 긴 변을 기준으로 할지 짧은 변을 기준으로 할지 고르는 곳입니다.",
        "en": "Basis — Choose whether the crop size is based on the photo's longer side or its shorter side.",
        "ja": "基準 — 切り取り範囲の大きさを決めるとき、写真の長い辺を基準にするか短い辺を基準にするかを選ぶところです。",
    },
    "imgedit.btn_curve": {"ko": "커브", "en": "Curve", "ja": "カーブ"},
    "imgedit.btn_curve.tip": {
        "ko": "커브 (S) — 사진이 너무 어둡거나 밝을 때, 밝기와 명암을 세밀하게 조절할 수 있는 창을 열어주는 기능입니다.",
        "en": "Curve (S) — Opens a window where you can finely adjust brightness and contrast if the photo is too dark or too bright.",
        "ja": "カーブ（S） — 写真が暗すぎたり明るすぎたりするとき、明るさとコントラストを細かく調整できる画面を開く機能です。",
    },
    "imgedit.btn_apply": {"ko": "적용", "en": "Apply", "ja": "適用"},
    "imgedit.btn_apply.tip": {
        "ko": "적용 (Space) — 지금 정한 크롭 영역을 이 사진에 실제로 반영하는 기능입니다.",
        "en": "Apply (Space) — Actually applies the crop area you set to this photo.",
        "ja": "適用（Space） — 今決めた切り取り範囲を、この写真に実際に反映する機能です。",
    },
    "imgedit.btn_save": {"ko": "저장", "en": "Save", "ja": "保存"},
    "imgedit.btn_save.tip": {
        "ko": "저장 (Ctrl+S) — 적용한 편집 내용을 실제 파일로 저장하는 기능입니다.",
        "en": "Save (Ctrl+S) — Saves the edits you applied to the actual file.",
        "ja": "保存（Ctrl+S） — 適用した編集内容を、実際のファイルとして保存する機能です。",
    },
    "imgedit.btn_undo": {"ko": "되돌리기", "en": "Undo", "ja": "元に戻す"},
    "imgedit.btn_undo.tip": {
        "ko": "되돌리기 (Ctrl+Z) — 방금 한 편집을 한 단계 전으로 되돌리는 기능입니다.",
        "en": "Undo (Ctrl+Z) — Reverts your last edit by one step.",
        "ja": "元に戻す（Ctrl+Z） — 直前に行った編集を1つ前の状態に戻す機能です。",
    },
    "imgedit.btn_redo": {"ko": "재실행", "en": "Redo", "ja": "やり直す"},
    "imgedit.btn_redo.tip": {
        "ko": "재실행 (Ctrl+Y) — 되돌리기로 취소했던 편집을 다시 적용하는 기능입니다.",
        "en": "Redo (Ctrl+Y) — Re-applies an edit that you had undone.",
        "ja": "やり直す（Ctrl+Y） — 元に戻すで取り消した編集を、もう一度適用する機能です。",
    },
    "imgedit.btn_move": {"ko": "이동", "en": "Move", "ja": "移動"},
    "imgedit.btn_move.tip": {
        "ko": "이동 (M) — 지금 보고 있는 사진 파일을 다른 폴더로 옮기는 기능입니다.",
        "en": "Move (M) — Moves the photo you're currently viewing to a different folder.",
        "ja": "移動（M） — 今見ている写真ファイルを別のフォルダへ移す機能です。",
    },
    "imgedit.btn_copy": {"ko": "복사", "en": "Copy", "ja": "コピー"},
    "imgedit.btn_copy.tip": {
        "ko": "복사 (C) — 지금 보고 있는 사진 파일을 다른 폴더에 똑같이 하나 더 만드는 기능입니다.",
        "en": "Copy (C) — Makes a duplicate of the photo you're currently viewing in a different folder.",
        "ja": "コピー（C） — 今見ている写真ファイルと同じものを、別のフォルダにもう1つ作る機能です。",
    },

    # ---- 중복 파일 찾기 모드 도구 ----
    "dupfind.target.empty": {
        "ko": "좌측 트리에서 폴더를 우클릭 → '폴더 추가'로 검사 대상을 등록하세요",
        "en": "Right-click a folder on the left tree → 'Add Folder' to register a target to scan",
        "ja": "左のツリーでフォルダを右クリック→「フォルダ追加」で検査対象を登録してください",
    },
    "dupfind.target.count": {
        "ko": "검사 대상 {n}개 폴더 등록됨 (하단 콘솔에서 목록 확인)",
        "en": "{n} target folder(s) registered (see the list in the console below)",
        "ja": "検査対象 {n}個のフォルダが登録済み（下部のコンソールで一覧を確認）",
    },
    "dupfind.btn_clear": {"ko": "전체 폴더 해제", "en": "Clear All Folders", "ja": "全フォルダ解除"},
    "dupfind.btn_clear.tip": {
        "ko": "전체 폴더 해제 — 지금까지 등록해둔 검사 대상 폴더를 전부 선택 해제(삭제)하는 기능입니다. 콘솔 로그에서 해제된 것을 확인할 수 있습니다.",
        "en": "Clear All Folders — Deselects (removes) every target folder you've registered so far. Check the console log to confirm they were cleared.",
        "ja": "全フォルダ解除 — これまで登録した検査対象フォルダをすべて選択解除（削除）する機能です。コンソールログで解除されたことを確認できます。",
    },
    "dupfind.btn_scan_precise": {"ko": "정밀 스캔", "en": "Precise Scan", "ja": "精密スキャン"},
    "dupfind.btn_scan_precise.tip": {
        "ko": "정밀 스캔 — 빠른 스캔으로 찾은 후보들만 다시 전체 내용을 처음부터 끝까지 읽어 "
              "확인합니다(폴더를 처음부터 다시 훑지 않음). 진짜로 내용이 같은 파일만 남기고, "
              "아니었던 파일은 목록에서 빠집니다. 빠른 스캔으로 후보를 찾은 뒤에만 누를 수 있습니다.",
        "en": "Precise Scan — Re-checks only the candidates already found by Fast Scan, reading "
              "each one's entire content (it does not rescan the folders from scratch). Files "
              "that turn out not to truly match are removed from the list. Only available after "
              "a Fast Scan has found candidates.",
        "ja": "精密スキャン — 高速スキャンで見つかった候補だけを対象に、内容を最初から最後まで"
              "読み直して確認します（フォルダを最初から再スキャンしません）。本当に内容が同じ"
              "ファイルだけが残り、そうでなかったものはリストから外れます。高速スキャンで候補が"
              "見つかった後にのみ押せます。",
    },
    "dupfind.btn_scan_fast": {"ko": "빠른 스캔", "en": "Fast Scan", "ja": "高速スキャン"},
    "dupfind.btn_scan_fast.tip": {
        "ko": "빠른 스캔 — 파일 앞·뒤 일부와 내부 여러 지점을 소량만 읽어 빠르게 후보를 "
              "확정합니다. 동영상처럼 큰 파일이 많을 때 훨씬 빠르지만, 극히 드물게(파일 중간의 "
              "아주 작은 부분만 다른 경우) 오탐이 있을 수 있으니 삭제 전에는 다시 한 번 "
              "확인하세요.",
        "en": "Fast Scan — Reads only small samples from the start, end, and several points "
              "inside each file to confirm candidates quickly. Much faster with many large "
              "files (e.g. videos), but in rare cases (a tiny differing section in the middle "
              "of a file) it can misclassify — double-check before deleting.",
        "ja": "高速スキャン — ファイルの先頭・末尾と内部の複数地点を少量だけ読んで候補を素早く"
              "確定します。動画のような大きなファイルが多い場合はずっと速いですが、ごくまれに"
              "（ファイル中間のごく一部だけ異なる場合）誤判定の可能性があるため、削除前にもう"
              "一度確認してください。",
    },
    "dupfind.btn_cancel": {"ko": "취소", "en": "Cancel", "ja": "キャンセル"},
    "dupfind.btn_cancel.tip": {
        "ko": "취소 — 지금 진행 중인 중복 파일 검사를 멈추는 기능입니다.",
        "en": "Cancel — Stops the duplicate-file scan currently in progress.",
        "ja": "キャンセル — 今進んでいる重複ファイル検査を止める機能です。",
    },
    "dupfind.tree.header": {
        "ko": "파일 / 그룹,경로,크기",
        "en": "File / Group,Path,Size",
        "ja": "ファイル／グループ,パス,サイズ",
    },
    "dupfind.btn_delete": {"ko": "선택 삭제(휴지통)", "en": "Delete Selected (to Recycle Bin)", "ja": "選択項目を削除（ごみ箱へ）"},
    "dupfind.btn_delete.tip": {
        "ko": "선택 삭제(휴지통) — 체크한 중복 파일들을 휴지통으로 보내는 기능입니다. 실수해도 휴지통에서 다시 꺼낼 수 있어요.",
        "en": "Delete Selected (to Recycle Bin) — Sends the checked duplicate files to the Recycle Bin. If you make a mistake, you can still restore them from there.",
        "ja": "選択項目を削除（ごみ箱へ） — チェックした重複ファイルをごみ箱に送る機能です。間違えてもごみ箱から戻せます。",
    },
    "dupfind.btn_move": {"ko": "선택 항목 다른 폴더로 이동", "en": "Move Selected to Another Folder", "ja": "選択項目を別フォルダへ移動"},
    "dupfind.btn_move.tip": {
        "ko": "선택 항목 다른 폴더로 이동 — 체크한 중복 파일들을 삭제하지 않고, 지정한 다른 폴더로 옮겨서 따로 모아두는 기능입니다.",
        "en": "Move Selected to Another Folder — Instead of deleting, moves the checked duplicate files into a folder you choose, to keep them together.",
        "ja": "選択項目を別フォルダへ移動 — チェックした重複ファイルを削除せず、指定した別のフォルダへ移してまとめておく機能です。",
    },

    # ---- [v44.3] 파일 찾기 — 세그먼트(중복 찾기 / 확장자로 찾기) ----
    "findmode.seg_dup": {"ko": "중복 파일 찾기", "en": "Find Duplicates", "ja": "重複ファイル検索"},
    "findmode.seg_ext": {"ko": "확장자로 찾기", "en": "Find by Extension", "ja": "拡張子で検索"},

    "extfind.chip_placeholder": {
        "ko": "확장자 입력 후 Enter (예: pdf)",
        "en": "Type an extension and press Enter (e.g. pdf)",
        "ja": "拡張子を入力してEnter（例: pdf）",
    },
    "extfind.preset_photo": {"ko": "사진", "en": "Photos", "ja": "写真"},
    "extfind.preset_doc": {"ko": "문서", "en": "Documents", "ja": "文書"},
    "extfind.preset_video": {"ko": "영상", "en": "Videos", "ja": "動画"},
    "extfind.preset_exe": {"ko": "실행", "en": "Programs", "ja": "実行ファイル"},

    "extfind.btn_search": {"ko": "검색", "en": "Search", "ja": "検索"},
    "extfind.btn_search.tip": {
        "ko": "검색 — 등록해 둔 폴더들 안에서, 지금 걸어 둔 확장자들에 해당하는 파일을 전부 찾아 목록으로 보여줍니다.",
        "en": "Search — Looks through the registered folders and lists every file matching the extensions you've added.",
        "ja": "検索 — 登録したフォルダの中から、今追加した拡張子に一致するファイルを全て探してリストに表示します。",
    },

    "extfind.table.header": {
        "ko": ",파일명,확장자,경로,크기,수정일",
        "en": ",Name,Extension,Path,Size,Modified",
        "ja": ",ファイル名,拡張子,パス,サイズ,更新日",
    },
    "extfind.table.header.check_all_tip": {
        "ko": "클릭하면 전체를 선택하거나 선택을 전부 해제합니다.",
        "en": "Click to select or deselect all rows.",
        "ja": "クリックすると全て選択、またはすべて選択解除します。",
    },
    "extfind.summary": {
        "ko": "총 {n}개 · {size}",
        "en": "{n} file(s) · {size}",
        "ja": "合計{n}個・{size}",
    },
    "extfind.summary_empty": {
        "ko": "조건에 맞는 파일이 발견되지 않았습니다.",
        "en": "No files matched.",
        "ja": "条件に合うファイルは見つかりませんでした。",
    },
    "extfind.btn_delete.tip": {
        "ko": "선택 삭제(휴지통) — 체크한 파일들을 휴지통으로 보내는 기능입니다. 실수해도 휴지통에서 다시 꺼낼 수 있어요.",
        "en": "Delete Selected (to Recycle Bin) — Sends the checked files to the Recycle Bin. If you make a mistake, you can still restore them from there.",
        "ja": "選択項目を削除（ごみ箱へ） — チェックしたファイルをごみ箱に送る機能です。間違えてもごみ箱から戻せます。",
    },
    "extfind.btn_move.tip": {
        "ko": "선택 항목 다른 폴더로 이동 — 체크한 파일들을 삭제하지 않고, 지정한 다른 폴더로 옮겨서 따로 모아두는 기능입니다.",
        "en": "Move Selected to Another Folder — Instead of deleting, moves the checked files into a folder you choose, to keep them together.",
        "ja": "選択項目を別フォルダへ移動 — チェックしたファイルを削除せず、指定した別のフォルダへ移してまとめておく機能です。",
    },

    "msg.extfind.no_extensions": {
        "ko": "먼저 찾을 확장자를 하나 이상 입력해 주세요(직접 입력하거나 프리셋 버튼을 눌러 주세요).",
        "en": "Add at least one extension first (type one, or click a preset button).",
        "ja": "まず検索する拡張子を1つ以上入力してください（直接入力するか、プリセットボタンを押してください）。",
    },
    "msg.extfind.check_delete_first": {
        "ko": "삭제할 파일을 먼저 체크해 주세요.",
        "en": "Check at least one file to delete first.",
        "ja": "削除するファイルを先にチェックしてください。",
    },
    "msg.extfind.check_move_first": {
        "ko": "이동할 파일을 먼저 체크해 주세요.",
        "en": "Check at least one file to move first.",
        "ja": "移動するファイルを先にチェックしてください。",
    },

    "status.extfind.hint": {
        "ko": "좌측 트리에서 우클릭으로 검사할 폴더를 등록하고, 확장자를 입력한 뒤 '검색'을 눌러 주세요.",
        "en": "Right-click in the tree to register folders, add extensions, then click 'Search'.",
        "ja": "左のツリーで右クリックしてフォルダを登録し、拡張子を入力してから「検索」を押してください。",
    },
    "status.extfind.running": {"ko": "확장자로 찾는 중…", "en": "Searching by extension…", "ja": "拡張子で検索中…"},
    "status.extfind.running_count": {
        "ko": "확장자로 찾는 중… (지금까지 {a0}개 확인)",
        "en": "Searching by extension… ({a0} files scanned so far)",
        "ja": "拡張子で検索中…（これまでに{a0}個確認）",
    },
    "status.extfind.cancelling": {"ko": "검색 취소 중…", "en": "Cancelling search…", "ja": "検索をキャンセル中…"},

    "log.extfind.preset_added": {
        "ko": "[파일 찾기] '{a0}' 프리셋 확장자 추가: {a1}",
        "en": "[Find] Added '{a0}' preset extensions: {a1}",
        "ja": "[ファイル検索] 「{a0}」プリセット拡張子を追加: {a1}",
    },
    "log.extfind.search_start": {
        "ko": "[파일 찾기] 확장자로 찾기 시작 — {a0} (대상 폴더 {a1}개)",
        "en": "[Find] Starting extension search — {a0} ({a1} target folder(s))",
        "ja": "[ファイル検索] 拡張子検索開始 — {a0}（対象フォルダ{a1}個）",
    },
    "log.extfind.progress": {
        "ko": "[파일 찾기] {a0}개 확인 — {a1}",
        "en": "[Find] {a0} files scanned — {a1}",
        "ja": "[ファイル検索] {a0}個確認 — {a1}",
    },
    "log.extfind.search_done": {
        "ko": "[파일 찾기] 검색 완료 — {a0}개, 총 {a1}",
        "en": "[Find] Search complete — {a0} file(s), {a1} total",
        "ja": "[ファイル検索] 検索完了 — {a0}個、合計{a1}",
    },

    # ---- 환경설정 다이얼로그 ----
    "settings.title": {"ko": "환경 설정", "en": "Settings", "ja": "環境設定"},
    "settings.group_language": {"ko": "언어", "en": "Language", "ja": "言語"},
    "settings.group_direction": {"ko": "동기화 방향", "en": "Sync Direction", "ja": "同期の方向"},
    "settings.rb_both": {"ko": "양방향 (양쪽을 최신으로 일치) — 권장", "en": "Both ways (match both sides to the newest) — recommended", "ja": "双方向（両方を最新に一致）— おすすめ"},
    "settings.rb_l2r": {"ko": "좌 → 우 (좌측 기준)", "en": "Left → Right (based on left)", "ja": "左→右（左を基準）"},
    "settings.rb_r2l": {"ko": "우 → 좌 (우측 기준)", "en": "Right → Left (based on right)", "ja": "右→左（右を基準）"},
    "settings.group_policy": {"ko": "정책", "en": "Policy", "ja": "ポリシー"},
    "settings.cb_backup": {"ko": "덮어쓰기/삭제 시 백업 보관 (_sync_backup) — 권장", "en": "Keep a backup on overwrite/delete (_sync_backup) — recommended", "ja": "上書き・削除時にバックアップを保管（_sync_backup）— おすすめ"},
    "settings.cb_preview": {"ko": "실행 전 미리보기 사용 (끄면 고속 즉시 실행) — 권장", "en": "Show a preview before running (turn off for instant, faster execution) — recommended", "ja": "実行前にプレビューを使う（オフにすると高速に即実行）— おすすめ"},
    "settings.cb_mirror": {"ko": "삭제 반영(미러): 원본에 없는 파일을 대상에서 삭제  ⚠ 위험", "en": "Mirror deletions: delete files on the target that don't exist on the source  ⚠ Risky", "ja": "削除を反映（ミラー）：元にないファイルを対象側で削除  ⚠ 危険"},
    "settings.policy_note": {
        "ko": "· 미러는 단방향(좌→우/우→좌)에서만 동작합니다.\n· 미러를 켜지 않으면 어느 쪽에서도 파일이 삭제되지 않습니다(안전).",
        "en": "· Mirror only works in one-way mode (Left→Right / Right→Left).\n· If Mirror is off, no files are deleted on either side (safe).",
        "ja": "・ミラーは一方向（左→右／右→左）のときだけ動作します。\n・ミラーをオンにしなければ、どちら側のファイルも削除されません（安全）。",
    },
    "settings.reset_btn": {"ko": "환경설정 초기화", "en": "Reset Settings", "ja": "設定を初期化"},
    "settings.reset_confirm_title": {"ko": "초기화 확인", "en": "Confirm Reset", "ja": "初期化の確認"},
    "settings.reset_confirm_body": {
        "ko": "환경설정(동기화 방향·정책)과 최근 작업 히스토리를 모두 초기화합니다.\n이 작업은 되돌릴 수 없습니다.\n\n계속하시겠습니까?",
        "en": "This resets all settings (sync direction/policy) and recent history.\nThis action cannot be undone.\n\nContinue?",
        "ja": "環境設定（同期方向・ポリシー）と最近の作業履歴をすべて初期化します。\nこの操作は元に戻せません。\n\n続けますか？",
    },
    "settings.reset_done_title": {"ko": "완료", "en": "Done", "ja": "完了"},
    "settings.reset_done_body": {
        "ko": "환경설정과 히스토리를 초기화했습니다.",
        "en": "Settings and history have been reset.",
        "ja": "環境設定と履歴を初期化しました。",
    },
    "settings.mirror_warn_title": {"ko": "안내", "en": "Notice", "ja": "お知らせ"},
    "settings.mirror_warn_body": {
        "ko": "미러 삭제는 양방향에서 위험하여 무시됩니다.\n단방향을 선택하세요.",
        "en": "Mirror deletion is risky in two-way mode, so it will be ignored.\nPlease choose a one-way direction.",
        "ja": "ミラー削除は双方向では危険なため無視されます。\n一方向を選んでください。",
    },

    # ---- [v27] 헤더 클릭 → 경로 직접 입력 ----
    "pathbar.notfound": {
        "ko": "입력하신 경로를 찾을 수 없습니다: {path}",
        "en": "Couldn't find the path you entered: {path}",
        "ja": "入力されたパスが見つかりません: {path}",
    },
    "pathbar.moved": {
        "ko": "[주소이동] 입력한 경로로 이동했습니다: {path}",
        "en": "[Go to Path] Moved to the entered path: {path}",
        "ja": "[アドレス移動] 入力したパスへ移動しました: {path}",
    },

    # ---- [v32] 단축키 도움말 ----
    "settings.shortcuts_btn": {"ko": "단축키 보기", "en": "View Shortcuts", "ja": "ショートカットを見る"},
    # [v37] 이미지 편집 모드 — 썸네일 캐시 크기 설정
    "settings.group_thumbcache": {"ko": "이미지 편집 — 썸네일 캐시", "en": "Image Editing — Thumbnail Cache", "ja": "画像編集 — サムネイルキャッシュ"},
    "settings.cache_low": {"ko": "가벼움 (1,000장)", "en": "Light (1,000)", "ja": "軽量（1,000枚）"},
    "settings.cache_default": {"ko": "기본 (3,000장) — 권장", "en": "Default (3,000) — recommended", "ja": "標準（3,000枚）— おすすめ"},
    "settings.cache_high": {"ko": "넉넉함 (5,000장)", "en": "High (5,000)", "ja": "多め（5,000枚）"},
    "settings.cache_veryhigh": {"ko": "매우 넉넉함 (10,000장)", "en": "Very High (10,000)", "ja": "非常に多い（10,000枚）"},
    "settings.cache_custom_label": {"ko": "직접 입력:", "en": "Custom:", "ja": "直接入力："},
    "settings.cache_unit_suffix": {"ko": "장", "en": " images", "ja": "枚"},
    "settings.cache_mem_estimate": {
        "ko": "예상 메모리 사용량: 약 {mb}MB (여러 폴더를 오가며 작업할 때 큰 값일수록 재방문이 빨라집니다)",
        "en": "Estimated memory usage: ~{mb}MB (a larger value speeds up revisiting folders when working across several folders)",
        "ja": "推定メモリ使用量：約{mb}MB（複数のフォルダを行き来する際、値が大きいほど再訪問が速くなります）",
    },
    "settings.cache_warn_title": {"ko": "안내", "en": "Notice", "ja": "お知らせ"},
    "settings.cache_warn_body": {
        "ko": "선택한 캐시 크기는 최대 약 {mb}MB의 메모리를 사용할 수 있습니다.\n"
              "저사양 PC(예: 메모리 4GB 이하)에서는 다른 프로그램과 함께 사용 시\n"
              "느려질 수 있으니, 컴퓨터 사양을 고려해 값을 선택해 주세요.",
        "en": "The selected cache size may use up to approximately {mb}MB of memory.\n"
              "On lower-spec PCs (e.g. 4GB RAM or less), this may cause slowdowns when\n"
              "running alongside other programs — please choose a value that fits your PC.",
        "ja": "選択したキャッシュサイズは最大約{mb}MBのメモリを使用する可能性があります。\n"
              "低スペックPC（例：メモリ4GB以下）では、他のプログラムと併用すると\n"
              "動作が遅くなることがあります。PCのスペックに合わせて選択してください。",
    },
    "shortcuts.title": {"ko": "전체 단축키", "en": "All Shortcuts", "ja": "すべてのショートカット"},
    "shortcuts.section_global": {"ko": "공통 (모든 모드)", "en": "Global (All Modes)", "ja": "共通（全モード）"},
    "shortcuts.f5": {
        "ko": "<b>F5</b> — 새로고침: 좌·우 폴더 목록을 다시 불러옵니다.",
        "en": "<b>F5</b> — Refresh: reloads the left/right folder lists.",
        "ja": "<b>F5</b> — 更新：左右のフォルダ一覧を読み込み直します。",
    },
    "shortcuts.section_imgedit": {"ko": "이미지 편집 모드", "en": "Image Editing Mode", "ja": "画像編集モード"},
    "shortcuts.space": {
        "ko": "<b>Space</b> — 지금 정한 크롭 영역을 사진에 적용합니다.",
        "en": "<b>Space</b> — Applies the crop area you set to the photo.",
        "ja": "<b>Space</b> — 今決めた切り取り範囲を写真に適用します。",
    },
    "shortcuts.ctrl_s": {
        "ko": "<b>Ctrl+S</b> — 적용한 편집 내용을 파일로 저장합니다.",
        "en": "<b>Ctrl+S</b> — Saves the applied edits to the file.",
        "ja": "<b>Ctrl+S</b> — 適用した編集内容をファイルに保存します。",
    },
    "shortcuts.ctrl_z": {
        "ko": "<b>Ctrl+Z</b> — 방금 한 편집을 한 단계 되돌립니다.",
        "en": "<b>Ctrl+Z</b> — Undoes the last edit by one step.",
        "ja": "<b>Ctrl+Z</b> — 直前の編集を1つ戻します。",
    },
    "shortcuts.ctrl_y": {
        "ko": "<b>Ctrl+Y</b> — 되돌렸던 편집을 다시 적용합니다.",
        "en": "<b>Ctrl+Y</b> — Re-applies an edit you undid.",
        "ja": "<b>Ctrl+Y</b> — 元に戻した編集をやり直します。",
    },
    "shortcuts.m": {
        "ko": "<b>M</b> — 지금 보는 사진을 다른 폴더로 이동합니다.",
        "en": "<b>M</b> — Moves the current photo to another folder.",
        "ja": "<b>M</b> — 今見ている写真を別のフォルダへ移動します。",
    },
    "shortcuts.c": {
        "ko": "<b>C</b> — 지금 보는 사진을 다른 폴더로 복사합니다.",
        "en": "<b>C</b> — Copies the current photo to another folder.",
        "ja": "<b>C</b> — 今見ている写真を別のフォルダへコピーします。",
    },
    "shortcuts.s": {
        "ko": "<b>S</b> — 커브(밝기·명암 조절) 창을 바로 엽니다.",
        "en": "<b>S</b> — Opens the Curve (brightness/contrast) window directly.",
        "ja": "<b>S</b> — カーブ（明るさ・コントラスト調整）画面をすぐに開きます。",
    },
    "shortcuts.esc": {
        "ko": "<b>Esc</b> — 이동/복사할 대상 폴더 선택을 취소합니다.",
        "en": "<b>Esc</b> — Cancels selecting a destination folder for move/copy.",
        "ja": "<b>Esc</b> — 移動・コピー先フォルダの選択をキャンセルします。",
    },

    # ==== [v38] 팝업/콘솔/상태바 메시지 전체 국제화 ====
    # 기존 1차 적용 범위(버튼·라벨·롤오버 힌트·설정 다이얼로그) 밖에 있던
    # QMessageBox 팝업, 콘솔 로그(logmsg), 상태바(showMessage) 문구를 모두 포함한다.
    "msg.title.info": {
        "ko": "안내",
        "en": "Notice",
        "ja": "お知らせ",
    },
    "msg.title.error": {
        "ko": "오류",
        "en": "Error",
        "ja": "エラー",
    },
    "msg.title.confirm": {
        "ko": "확인",
        "en": "Confirm",
        "ja": "確認",
    },
    "msg.title.done": {
        "ko": "완료",
        "en": "Done",
        "ja": "完了",
    },
    "msg.title.done_partial": {
        "ko": "완료 (일부 실패)",
        "en": "Done (Some Failed)",
        "ja": "完了（一部失敗）",
    },
    "msg.title.sync": {
        "ko": "동기화",
        "en": "Sync",
        "ja": "同期",
    },
    "msg.title.sync_done": {
        "ko": "동기화 완료",
        "en": "Sync Complete",
        "ja": "同期完了",
    },
    "msg.title.create_failed": {
        "ko": "생성 실패",
        "en": "Creation Failed",
        "ja": "作成失敗",
    },
    "msg.title.no_trash": {
        "ko": "휴지통 기능을 사용할 수 없음",
        "en": "Recycle Bin Unavailable",
        "ja": "ごみ箱機能が使用できません",
    },
    "msg.title.confirm_changes": {
        "ko": "변경 내용 확인",
        "en": "Confirm Changes",
        "ja": "変更内容の確認",
    },
    "log.dupfind.already_added": {
        "ko": "[중복찾기] 이미 등록된 폴더입니다: {a0}",
        "en": "[Duplicate Finder] Folder already registered: {a0}",
        "ja": "[重複ファイル検索] すでに登録済みのフォルダです: {a0}",
    },
    "log.dupfind.folder_added": {
        "ko": "[중복찾기] 폴더 추가 ({a0}번째): {a1}",
        "en": "[Duplicate Finder] Folder added (#{a0}): {a1}",
        "ja": "[重複ファイル検索] フォルダ追加（{a0}番目）: {a1}",
    },
    "log.dupfind.cleared": {
        "ko": "[중복찾기] 전체 폴더 해제 — 등록되어 있던 검사 대상을 모두 지웠습니다.",
        "en": "[Duplicate Finder] Cleared all folders — every registered target has been removed.",
        "ja": "[重複ファイル検索] 全フォルダ解除 — 登録していた検査対象をすべて削除しました。",
    },
    "msg.dupfind.no_targets": {
        "ko": "좌측 트리에서 폴더를 우클릭해 '폴더 추가'로 검사 대상을 먼저 등록하세요.",
        "en": "Right-click a folder in the left tree and choose 'Add Folder' to register a target first.",
        "ja": "左のツリーでフォルダを右クリックし、「フォルダ追加」で検査対象を先に登録してください。",
    },
    "status.dupfind.no_targets_hint": {
        "ko": "좌측 트리에서 폴더를 우클릭해 '폴더 추가'로 검사 대상을 등록하세요.",
        "en": "Right-click a folder in the left tree and choose 'Add Folder' to register a target.",
        "ja": "左のツリーでフォルダを右クリックし、「フォルダ追加」で検査対象を登録してください。",
    },
    "msg.title.confirm_targets": {
        "ko": "검사 대상 확인",
        "en": "Confirm Targets",
        "ja": "検査対象の確認",
    },
    "msg.dupfind.confirm_scan": {
        "ko": "다음 {a0}개 폴더(및 하위 폴더 전체)를 {a1}으로 검사합니다.\n\n{a2}\n\n계속하시겠습니까?",
        "en": "The following {a0} folder(s) (and all subfolders) will be scanned using {a1}.\n\n{a2}\n\nContinue?",
        "ja": "次の{a0}個のフォルダ（およびすべてのサブフォルダ）を{a1}で検査します。\n\n{a2}\n\n続行しますか？",
    },
    "msg.dupfind.confirm_precise_verify": {
        "ko": "빠른 스캔으로 찾은 {a0}개 그룹({a1}개 파일)만 정밀 재검사합니다.\n"
              "폴더를 처음부터 다시 훑지는 않습니다.\n\n계속하시겠습니까?",
        "en": "This will precisely re-check only the {a0} group(s) ({a1} file(s)) already found "
              "by Fast Scan. It will not rescan the folders from scratch.\n\nContinue?",
        "ja": "高速スキャンで見つかった{a0}個のグループ（{a1}個のファイル）だけを精密に再検査します。"
              "フォルダを最初から再スキャンすることはありません。\n\n続行しますか？",
    },
    "log.dupfind.scan_start": {
        "ko": "[중복찾기] {a0} 스캔 시작 — 대상 {a1}개 폴더",
        "en": "[Duplicate Finder] {a0} scan started — {a1} target folder(s)",
        "ja": "[重複ファイル検索] {a0}スキャン開始 — 対象{a1}個のフォルダ",
    },
    "log.dupfind.precise_verify_start": {
        "ko": "[중복찾기] 정밀 재검사 시작 — 후보 {a0}개 그룹, {a1}개 파일",
        "en": "[Duplicate Finder] Precise re-check started — {a0} candidate group(s), {a1} file(s)",
        "ja": "[重複ファイル検索] 精密再検査開始 — 候補{a0}個のグループ、{a1}個のファイル",
    },
    "log.dupfind.precise_verify_done": {
        "ko": "[중복찾기] 정밀 재검사 완료 — {a0}개 파일 중 {a1}개가 실제로 일치, {a2}개는 목록에서 제외됨",
        "en": "[Duplicate Finder] Precise re-check done — {a1} of {a0} file(s) truly matched, {a2} removed from the list",
        "ja": "[重複ファイル検索] 精密再検査完了 — {a0}個中{a1}個のファイルが実際に一致、{a2}個をリストから除外",
    },
    "status.dupfind.cancelling": {
        "ko": "[중복찾기] 취소 중…",
        "en": "[Duplicate Finder] Cancelling…",
        "ja": "[重複ファイル検索] キャンセル中…",
    },
    "status.dupfind.paused": {
        "ko": "[중복찾기] 일시 정지 — 확인 대기 중…",
        "en": "[Duplicate Finder] Paused — waiting for confirmation…",
        "ja": "[重複ファイル検索] 一時停止 — 確認待ち…",
    },
    "log.dupfind.esc_pressed": {
        "ko": "[중복찾기] Esc — 스캔을 일시 정지하고 중단 여부를 확인합니다.",
        "en": "[Duplicate Finder] Esc — pausing the scan to confirm whether to stop.",
        "ja": "[重複ファイル検索] Esc — スキャンを一時停止し、中止するか確認します。",
    },
    "msg.title.confirm_stop_scan": {
        "ko": "스캔 중단 확인",
        "en": "Confirm Stop",
        "ja": "スキャン中止の確認",
    },
    "msg.dupfind.confirm_stop": {
        "ko": "스캔을 잠시 멈췄습니다.\n\n스캔을 중단하시겠습니까?\n('No'를 누르면 멈춘 지점부터 계속 진행합니다.)",
        "en": "The scan has been paused.\n\nDo you want to stop it?\n(Press 'No' to continue from where it paused.)",
        "ja": "スキャンを一時停止しました。\n\nスキャンを中止しますか？\n（「No」を押すと、停止した地点から続行します。）",
    },
    "log.dupfind.user_stopped": {
        "ko": "[중복찾기] 사용자가 중단을 선택했습니다.",
        "en": "[Duplicate Finder] The user chose to stop.",
        "ja": "[重複ファイル検索] ユーザーが中止を選択しました。",
    },
    "log.dupfind.user_continued": {
        "ko": "[중복찾기] 사용자가 계속 진행을 선택했습니다 — 스캔을 재개합니다.",
        "en": "[Duplicate Finder] The user chose to continue — resuming the scan.",
        "ja": "[重複ファイル検索] ユーザーが続行を選択しました — スキャンを再開します。",
    },
    "log.dupfind.progress": {
        "ko": "[중복찾기] {a0}% — {a1}",
        "en": "[Duplicate Finder] {a0}% — {a1}",
        "ja": "[重複ファイル検索] {a0}% — {a1}",
    },
    "log.dupfind.cancelled": {
        "ko": "[중복찾기] 스캔 취소됨",
        "en": "[Duplicate Finder] Scan cancelled",
        "ja": "[重複ファイル検索] スキャンがキャンセルされました",
    },
    "status.dupfind.cancelled": {
        "ko": "[중복찾기] 스캔이 취소되었습니다.",
        "en": "[Duplicate Finder] The scan was cancelled.",
        "ja": "[重複ファイル検索] スキャンがキャンセルされました。",
    },
    "log.dupfind.error": {
        "ko": "[중복찾기] 오류: {a0}",
        "en": "[Duplicate Finder] Error: {a0}",
        "ja": "[重複ファイル検索] エラー: {a0}",
    },
    "msg.dupfind.scan_error": {
        "ko": "검사 중 오류가 발생했습니다:\n{a0}",
        "en": "An error occurred during the scan:\n{a0}",
        "ja": "検査中にエラーが発生しました:\n{a0}",
    },
    "log.dupfind.scan_done": {
        "ko": "[중복찾기] 스캔 완료: 그룹 {a0}개, 파일 {a1}개, 절약 가능 {a2}",
        "en": "[Duplicate Finder] Scan complete: {a0} group(s), {a1} file(s), {a2} reclaimable",
        "ja": "[重複ファイル検索] スキャン完了: {a0}グループ、{a1}ファイル、削減可能 {a2}",
    },
    "status.dupfind.scan_done": {
        "ko": "[중복찾기] 스캔 완료",
        "en": "[Duplicate Finder] Scan complete",
        "ja": "[重複ファイル検索] スキャン完了",
    },
    "msg.dupfind.check_delete_first": {
        "ko": "삭제할 파일을 먼저 체크하세요.",
        "en": "Please check the files to delete first.",
        "ja": "削除するファイルを先にチェックしてください。",
    },
    "msg.common.no_trash_body": {
        "ko": "이 프로그램에 휴지통 삭제 기능(send2trash)이 포함되어 있지 않습니다.\n휴지통 없이 영구적으로 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.",
        "en": "This program doesn't include the Recycle Bin feature (send2trash).\nDelete permanently without using the Recycle Bin? This cannot be undone.",
        "ja": "このプログラムにはごみ箱機能（send2trash）が含まれていません。\nごみ箱を使わずに完全に削除しますか？この操作は元に戻せません。",
    },
    "msg.dupfind.confirm_trash": {
        "ko": "체크된 {a0}개 파일을 휴지통으로 삭제하시겠습니까?",
        "en": "Send the {a0} checked file(s) to the Recycle Bin?",
        "ja": "チェックした{a0}個のファイルをごみ箱に送りますか？",
    },
    "log.dupfind.deleted": {
        "ko": "[중복찾기] 삭제({a0}): {a1}",
        "en": "[Duplicate Finder] Deleted ({a0}): {a1}",
        "ja": "[重複ファイル検索] 削除（{a0}）: {a1}",
    },
    "msg.dupfind.check_move_first": {
        "ko": "이동할 파일을 먼저 체크하세요.",
        "en": "Please check the files to move first.",
        "ja": "移動するファイルを先にチェックしてください。",
    },
    "log.dupfind.moved": {
        "ko": "[중복찾기] 이동: {a0} → {a1}",
        "en": "[Duplicate Finder] Moved: {a0} → {a1}",
        "ja": "[重複ファイル検索] 移動: {a0} → {a1}",
    },
    "status.dupfind.hint_add_folder": {
        "ko": "[중복찾기] {a0} — 우클릭 메뉴에서 '폴더 추가'를 선택하면 검사 대상에 등록됩니다.",
        "en": "[Duplicate Finder] {a0} — Choose 'Add Folder' from the right-click menu to register it as a target.",
        "ja": "[重複ファイル検索] {a0} — 右クリックメニューの「フォルダ追加」を選ぶと検査対象に登録されます。",
    },
    "status.common.select_hint": {
        "ko": "폴더를 선택하면 선택한 폴더의 전체(절대) 경로가 표시됩니다.",
        "en": "Selecting a folder shows its full (absolute) path here.",
        "ja": "フォルダを選択すると、その完全な（絶対）パスがここに表示されます。",
    },
    "log.common.path_not_found": {
        "ko": "[주소이동] 경로를 찾을 수 없습니다: {a0}",
        "en": "[Go to Path] Path not found: {a0}",
        "ja": "[アドレス移動] パスが見つかりません: {a0}",
    },
    "log.common.left_selected": {
        "ko": "[좌] 선택: {a0}",
        "en": "[Left] Selected: {a0}",
        "ja": "[左] 選択: {a0}",
    },
    "status.common.left": {
        "ko": "[좌] {a0}",
        "en": "[Left] {a0}",
        "ja": "[左] {a0}",
    },
    "log.common.right_selected": {
        "ko": "[우] 선택: {a0}",
        "en": "[Right] Selected: {a0}",
        "ja": "[右] 選択: {a0}",
    },
    "status.common.right": {
        "ko": "[우] {a0}",
        "en": "[Right] {a0}",
        "ja": "[右] {a0}",
    },
    "msg.common.path_missing": {
        "ko": "해당 경로가 존재하지 않습니다.\n{a0}",
        "en": "That path does not exist.\n{a0}",
        "ja": "そのパスは存在しません。\n{a0}",
    },
    "log.common.refreshed": {
        "ko": "[새로고침] 좌·우 폴더 트리를 다시 불러왔습니다.",
        "en": "[Refresh] Reloaded both the left and right folder trees.",
        "ja": "[更新] 左右のフォルダツリーを再読み込みしました。",
    },
    "status.common.refreshed": {
        "ko": "좌·우 폴더 트리를 새로고침했습니다.",
        "en": "Refreshed both folder trees.",
        "ja": "左右のフォルダツリーを更新しました。",
    },
    "log.common.left_selected_history": {
        "ko": "[좌] 선택(히스토리): {a0}",
        "en": "[Left] Selected (from history): {a0}",
        "ja": "[左] 選択（履歴）: {a0}",
    },
    "log.common.right_selected_history": {
        "ko": "[우] 선택(히스토리): {a0}",
        "en": "[Right] Selected (from history): {a0}",
        "ja": "[右] 選択（履歴）: {a0}",
    },
    "msg.title.open_explorer": {
        "ko": "탐색기 열기",
        "en": "Open in Explorer",
        "ja": "エクスプローラーを開く",
    },
    "msg.common.path_not_found_body": {
        "ko": "경로를 찾을 수 없습니다:\n{a0}",
        "en": "Could not find the path:\n{a0}",
        "ja": "パスが見つかりません:\n{a0}",
    },
    "log.common.opened_explorer": {
        "ko": "[탐색기 열기] {a0}",
        "en": "[Open in Explorer] {a0}",
        "ja": "[エクスプローラーを開く] {a0}",
    },
    "msg.title.open_explorer_failed": {
        "ko": "탐색기 열기 실패",
        "en": "Failed to Open Explorer",
        "ja": "エクスプローラーを開けません",
    },
    "msg.common.open_explorer_error": {
        "ko": "탐색기를 여는 중 오류가 발생했습니다:\n{a0}",
        "en": "An error occurred while opening Explorer:\n{a0}",
        "ja": "エクスプローラーを開く際にエラーが発生しました:\n{a0}",
    },
    "msg.title.create_subfolder": {
        "ko": "하위 폴더 생성",
        "en": "Create Subfolder",
        "ja": "サブフォルダの作成",
    },
    "msg.common.enter_folder_name": {
        "ko": "새 폴더 이름을 입력하세요:",
        "en": "Enter the new folder name:",
        "ja": "新しいフォルダ名を入力してください:",
    },
    "log.common.subfolder_created": {
        "ko": "[{a0}] 하위 폴더 생성: {a1}",
        "en": "[{a0}] Subfolder created: {a1}",
        "ja": "[{a0}] サブフォルダを作成: {a1}",
    },
    "msg.common.already_exists": {
        "ko": "'{a0}' 항목이 이미 존재합니다.",
        "en": "'{a0}' already exists.",
        "ja": "「{a0}」はすでに存在します。",
    },
    "msg.common.create_folder_error": {
        "ko": "폴더 생성 중 오류가 발생했습니다:\n{a0}",
        "en": "An error occurred while creating the folder:\n{a0}",
        "ja": "フォルダの作成中にエラーが発生しました:\n{a0}",
    },
    "log.common.rename_failed": {
        "ko": "[{a0}] 이름 변경 실패: {a1} → {a2} (사용 중이거나 권한 없음)",
        "en": "[{a0}] Rename failed: {a1} → {a2} (in use or no permission)",
        "ja": "[{a0}] 名前変更失敗: {a1} → {a2}（使用中または権限なし）",
    },
    "msg.title.rename_blocked": {
        "ko": "이름 변경 불가",
        "en": "Cannot Rename",
        "ja": "名前を変更できません",
    },
    "msg.common.rename_blocked_body": {
        "ko": "'{a0}' 폴더를 사용 중이어서 이름을 바꿀 수 없습니다.\n\n탐색기 등 다른 프로그램에서 이 폴더를 열어 두었거나, 폴더 안의\n파일이 다른 프로그램에서 열려 있는 경우 발생할 수 있습니다.\n해당 프로그램을 닫은 뒤 다시 시도해 주세요.",
        "en": "The folder '{a0}' is in use, so it can't be renamed.\n\nThis can happen when Explorer or another program has this folder open, or when a file inside it is open in another program.\nClose that program and try again.",
        "ja": "「{a0}」フォルダが使用中のため、名前を変更できません。\n\nエクスプローラーや他のプログラムでこのフォルダを開いていたり、\n中のファイルが別のプログラムで開かれている場合に発生することがあります。\nそのプログラムを閉じてから、もう一度お試しください。",
    },
    "log.common.renamed": {
        "ko": "[{a0}] 이름 변경: {a1} → {a2}",
        "en": "[{a0}] Renamed: {a1} → {a2}",
        "ja": "[{a0}] 名前変更: {a1} → {a2}",
    },
    "msg.title.confirm_delete": {
        "ko": "삭제 확인",
        "en": "Confirm Delete",
        "ja": "削除の確認",
    },
    "msg.common.confirm_delete_folder": {
        "ko": "'{a0}' 폴더를 정말 삭제하시겠습니까?\n(휴지통으로 이동합니다)",
        "en": "Are you sure you want to delete the folder '{a0}'?\n(It will be moved to the Recycle Bin.)",
        "ja": "本当に「{a0}」フォルダを削除しますか？\n（ごみ箱に移動します）",
    },
    "log.common.deleted": {
        "ko": "[{a0}] 삭제({a1}): {a2}",
        "en": "[{a0}] Deleted ({a1}): {a2}",
        "ja": "[{a0}] 削除（{a1}）: {a2}",
    },
    "log.mode.rename": {
        "ko": "[모드] 파일명 변경 모드로 전환",
        "en": "[Mode] Switched to Rename mode",
        "ja": "[モード] ファイル名変更モードに切り替え",
    },
    "log.mode.sync": {
        "ko": "[모드] 동기화 모드로 전환",
        "en": "[Mode] Switched to Sync mode",
        "ja": "[モード] 同期モードに切り替え",
    },
    "log.mode.imgedit": {
        "ko": "[모드] 이미지 편집 모드로 전환",
        "en": "[Mode] Switched to Image Editing mode",
        "ja": "[モード] 画像編集モードに切り替え",
    },
    "log.mode.dupfind": {
        "ko": "[모드] 중복 파일 찾기 모드로 전환",
        "en": "[Mode] Switched to Duplicate Finder mode",
        "ja": "[モード] 重複ファイル検索モードに切り替え",
    },
    "status.rename.select_hint": {
        "ko": "좌측 트리에서 폴더를 선택하면 해당 폴더의 파일/서브폴더 목록이 표시됩니다.",
        "en": "Selecting a folder in the left tree shows its files and subfolders here.",
        "ja": "左のツリーでフォルダを選択すると、そのファイルとサブフォルダの一覧が表示されます。",
    },
    "status.imgedit.select_hint": {
        "ko": "좌측 트리에서 폴더를 선택하면 해당 폴더의 이미지가 표시됩니다.",
        "en": "Selecting a folder in the left tree shows its images here.",
        "ja": "左のツリーでフォルダを選択すると、その画像が表示されます。",
    },
    "log.common.left_selected_shortcut": {
        "ko": "[좌] 선택(우클릭 바로가기): {a0}",
        "en": "[Left] Selected (right-click shortcut): {a0}",
        "ja": "[左] 選択（右クリックショートカット）: {a0}",
    },
    "msg.rename.discard_confirm": {
        "ko": "적용하지 않은 파일명 변경 내용이 있습니다.\n버리고 계속하시겠습니까?",
        "en": "There are unapplied rename changes.\nDiscard them and continue?",
        "ja": "適用されていないファイル名変更があります。\n破棄して続行しますか？",
    },
    "msg.imgedit.discard_confirm": {
        "ko": "저장하지 않은 이미지 편집 내용이 있습니다.\n버리고 계속하시겠습니까?",
        "en": "There are unsaved image edits.\nDiscard them and continue?",
        "ja": "保存されていない画像編集があります。\n破棄して続行しますか？",
    },
    "msg.imgedit.no_pillow": {
        "ko": "Pillow 패키지가 설치되어 있지 않아 이미지 편집을 사용할 수 없습니다.\npip install Pillow 로 설치해 주세요.",
        "en": "The Pillow package isn't installed, so image editing is unavailable.\nInstall it with: pip install Pillow",
        "ja": "Pillowパッケージがインストールされていないため、画像編集を使用できません。\npip install Pillow でインストールしてください。",
    },
    "log.imgedit.error": {
        "ko": "[이미지편집] 오류: {a0}",
        "en": "[Image Edit] Error: {a0}",
        "ja": "[画像編集] エラー: {a0}",
    },
    "status.imgedit.loading": {
        "ko": "[이미지편집] {a0} ({a1}개 로드 중...)",
        "en": "[Image Edit] {a0} (loading {a1} item(s)...)",
        "ja": "[画像編集] {a0}（{a1}件読み込み中...）",
    },
    "log.imgedit.entered": {
        "ko": "[이미지편집] 모드 진입: {a0} ({a1}개)",
        "en": "[Image Edit] Entered: {a0} ({a1} item(s))",
        "ja": "[画像編集] モード開始: {a0}（{a1}件）",
    },
    "log.imgedit.open_failed": {
        "ko": "[이미지편집] 이미지 열기 실패: {a0} ({a1})",
        "en": "[Image Edit] Failed to open image: {a0} ({a1})",
        "ja": "[画像編集] 画像を開けませんでした: {a0}（{a1}）",
    },
    "msg.imgedit.select_image_first": {
        "ko": "먼저 편집할 이미지를 선택하세요.",
        "en": "Please select an image to edit first.",
        "ja": "先に編集する画像を選択してください。",
    },
    "log.imgedit.curve_adjusted": {
        "ko": "[이미지편집] 커브 조정: {a0}",
        "en": "[Image Edit] Curve adjusted: {a0}",
        "ja": "[画像編集] カーブ調整: {a0}",
    },
    "log.imgedit.applied": {
        "ko": "[이미지편집] 적용: {a0}",
        "en": "[Image Edit] Applied: {a0}",
        "ja": "[画像編集] 適用: {a0}",
    },
    "status.imgedit.nothing_to_undo": {
        "ko": "[이미지편집] 더 이상 되돌릴 내용이 없습니다.",
        "en": "[Image Edit] Nothing left to undo.",
        "ja": "[画像編集] これ以上元に戻せる内容がありません。",
    },
    "log.imgedit.undone": {
        "ko": "[이미지편집] 되돌리기: {a0}",
        "en": "[Image Edit] Undone: {a0}",
        "ja": "[画像編集] 元に戻す: {a0}",
    },
    "status.imgedit.nothing_to_redo": {
        "ko": "[이미지편집] 다시 실행할 내용이 없습니다.",
        "en": "[Image Edit] Nothing left to redo.",
        "ja": "[画像編集] これ以上やり直せる内容がありません。",
    },
    "log.imgedit.redone": {
        "ko": "[이미지편집] 재실행: {a0}",
        "en": "[Image Edit] Redone: {a0}",
        "ja": "[画像編集] やり直し: {a0}",
    },
    "msg.imgedit.nothing_to_save": {
        "ko": "저장할 변경 내용이 없습니다. (적용된 이미지가 없음)",
        "en": "There are no changes to save. (No images have been applied.)",
        "ja": "保存する変更がありません。（適用された画像がありません）",
    },
    "log.imgedit.saved": {
        "ko": "[이미지편집] 저장: {a0}",
        "en": "[Image Edit] Saved: {a0}",
        "ja": "[画像編集] 保存: {a0}",
    },
    "log.imgedit.save_failed": {
        "ko": "[이미지편집] 저장 실패: {a0} ({a1})",
        "en": "[Image Edit] Save failed: {a0} ({a1})",
        "ja": "[画像編集] 保存失敗: {a0}（{a1}）",
    },
    "msg.title.confirm_save": {
        "ko": "저장 확인",
        "en": "Confirm Save",
        "ja": "保存の確認",
    },
    "msg.imgedit.save_then_action": {
        "ko": "현재 이미지에 적용된 변경 사항이 있습니다.\n저장한 후 {a0}하시겠습니까?",
        "en": "There are unsaved changes applied to the current image.\nSave it and then {a0}?",
        "ja": "現在の画像に適用された変更があります。\n保存してから{a0}しますか？",
    },
    "status.imgedit.pick_dest": {
        "ko": "[이미지편집] {a0}할 대상 폴더를 선택하세요 (Enter로 확정, Esc로 취소)",
        "en": "[Image Edit] Select the destination folder to {a0} to (Enter to confirm, Esc to cancel)",
        "ja": "[画像編集] {a0}先のフォルダを選択してください（Enterで確定、Escでキャンセル）",
    },
    "status.imgedit.loaded_dir": {
        "ko": "[이미지편집] {a0}",
        "en": "[Image Edit] {a0}",
        "ja": "[画像編集] {a0}",
    },
    "msg.common.select_dest_first": {
        "ko": "먼저 대상 폴더를 선택하세요.",
        "en": "Please select a destination folder first.",
        "ja": "先に対象フォルダを選択してください。",
    },
    "log.imgedit.move_copy": {
        "ko": "[이미지편집] {a0}: {a1} → {a2}",
        "en": "[Image Edit] {a0}: {a1} → {a2}",
        "ja": "[画像編集] {a0}: {a1} → {a2}",
    },
    "msg.common.action_failed": {
        "ko": "{a0} 실패:\n{a1}",
        "en": "{a0} failed:\n{a1}",
        "ja": "{a0}に失敗しました:\n{a1}",
    },
    "msg.title.include_folder_names": {
        "ko": "폴더명 포함 여부",
        "en": "Include Folder Names?",
        "ja": "フォルダ名を含めるか",
    },
    "msg.rename.include_folders": {
        "ko": "폴더명도 포함해서 변경하시겠습니까?\n(아니오를 선택하면 파일명에만 적용됩니다)",
        "en": "Apply the change to folder names as well?\n(Choosing No applies it to file names only.)",
        "ja": "フォルダ名も含めて変更しますか？\n（「いいえ」を選ぶとファイル名のみに適用されます）",
    },
    "msg.common.select_folder_first": {
        "ko": "좌측에서 폴더를 먼저 선택하세요.",
        "en": "Please select a folder on the left first.",
        "ja": "先に左側でフォルダを選択してください。",
    },
    "log.rename.nfc_fixed": {
        "ko": "[이름정규화] {a0}개 파일명을 자모 결합(NFC) 형태로 고쳤습니다:",
        "en": "[Normalize Names] Fixed {a0} filename(s) to composed (NFC) form:",
        "ja": "[名前正規化] {a0}個のファイル名を結合形式（NFC）に修正しました:",
    },
    "log.rename.nfc_skipped": {
        "ko": "[이름정규화] {a0}개는 같은 이름이 이미 있어 건너뛰었습니다:",
        "en": "[Normalize Names] Skipped {a0} file(s) because a file with the same name already exists:",
        "ja": "[名前正規化] {a0}個は同名のファイルがすでに存在するためスキップしました:",
    },
    "log.rename.nfc_failed": {
        "ko": "[이름정규화] {a0}개는 오류로 실패했습니다:",
        "en": "[Normalize Names] {a0} file(s) failed due to an error:",
        "ja": "[名前正規化] {a0}個はエラーのため失敗しました:",
    },
    "log.rename.nfc_none": {
        "ko": "[이름정규화] 자모 분리된 파일명이 없습니다 — 모두 정상입니다.",
        "en": "[Normalize Names] No decomposed filenames found — everything is already normal.",
        "ja": "[名前正規化] 分解された（未結合の）ファイル名はありません — すべて正常です。",
    },
    "msg.title.normalize_done": {
        "ko": "이름 정규화 완료",
        "en": "Normalization Complete",
        "ja": "名前正規化完了",
    },
    "log.rename.entered": {
        "ko": "[이름변경] 모드 진입: {a0} (파일 {a1}개, 폴더 {a2}개 로드)",
        "en": "[Rename] Entered: {a0} (loaded {a1} file(s), {a2} folder(s))",
        "ja": "[名前変更] モード開始: {a0}（ファイル{a1}個、フォルダ{a2}個を読み込み）",
    },
    "status.rename.loaded_dir": {
        "ko": "[이름변경] {a0}",
        "en": "[Rename] {a0}",
        "ja": "[名前変更] {a0}",
    },
    "log.rename.error": {
        "ko": "[이름변경] 오류: {a0}",
        "en": "[Rename] Error: {a0}",
        "ja": "[名前変更] エラー: {a0}",
    },
    "status.common.error": {
        "ko": "오류: {a0}",
        "en": "Error: {a0}",
        "ja": "エラー: {a0}",
    },
    "msg.rename.bad_pattern": {
        "ko": "잘못된 검색어 패턴이거나 정규식 문법 오류입니다.",
        "en": "Invalid search pattern or regular-expression syntax error.",
        "ja": "検索パターンが不正か、正規表現の構文エラーです。",
    },
    "msg.rename.count_mismatch": {
        "ko": "원본 항목 개수({a0}개)와 현재 목록의 줄 수({a1}개)가 일치하지 않습니다.",
        "en": "The number of original items ({a0}) doesn't match the number of lines in the current list ({a1}).",
        "ja": "元の項目数（{a0}個）と現在のリストの行数（{a1}個）が一致しません。",
    },
    "msg.rename.empty_name": {
        "ko": "이름은 비어있을 수 없습니다.",
        "en": "A name cannot be empty.",
        "ja": "名前を空にすることはできません。",
    },
    "msg.rename.invalid_chars": {
        "ko": "이름 '{a0}'에 사용할 수 없는 문자가 포함되어 있습니다.",
        "en": "The name '{a0}' contains characters that can't be used.",
        "ja": "名前「{a0}」に使用できない文字が含まれています。",
    },
    "log.rename.applied_one": {
        "ko": "[이름변경] {a0}{a1} → {a2}",
        "en": "[Rename] {a0}{a1} → {a2}",
        "ja": "[名前変更] {a0}{a1} → {a2}",
    },
    "log.rename.apply_failed": {
        "ko": "[이름변경] 실패: {a0} → {a1} ({a2})",
        "en": "[Rename] Failed: {a0} → {a1} ({a2})",
        "ja": "[名前変更] 失敗: {a0} → {a1}（{a2}）",
    },
    "log.rename.apply_done": {
        "ko": "[이름변경] 적용 완료: {a0}건 성공, {a1}건 실패",
        "en": "[Rename] Done: {a0} succeeded, {a1} failed",
        "ja": "[名前変更] 適用完了: 成功{a0}件、失敗{a1}件",
    },
    "log.settings.cache_size_changed": {
        "ko": "[설정] 썸네일 캐시 크기 변경: {a0}개",
        "en": "[Settings] Thumbnail cache size changed: {a0}",
        "ja": "[設定] サムネイルキャッシュサイズを変更: {a0}個",
    },
    "log.settings.summary": {
        "ko": "[설정] 방향={a0} 백업={a1} 미리보기={a2} 미러={a3}",
        "en": "[Settings] direction={a0} backup={a1} preview={a2} mirror={a3}",
        "ja": "[設定] 方向={a0} バックアップ={a1} プレビュー={a2} ミラー={a3}",
    },
    "log.common.saved": {
        "ko": "[저장] {a0}",
        "en": "[Save] {a0}",
        "ja": "[保存] {a0}",
    },
    "msg.common.select_both_folders": {
        "ko": "좌·우 폴더를 모두 선택하세요.",
        "en": "Please select both the left and right folders.",
        "ja": "左右両方のフォルダを選択してください。",
    },
    "log.common.structure_copy_done": {
        "ko": "[구조복사] 완료: {a0}개 폴더 → {a1}",
        "en": "[Copy Structure] Done: {a0} folder(s) → {a1}",
        "ja": "[構造コピー] 完了: {a0}個のフォルダ → {a1}",
    },
    "log.sync.debug_click_left": {
        "ko": "[동기화] ▶ 버튼 클릭 시점 확인 — 좌: {a0}",
        "en": "[Sync] ▶ Checked at button click — Left: {a0}",
        "ja": "[同期] ▶ ボタンクリック時点の確認 — 左: {a0}",
    },
    "log.sync.debug_click_right": {
        "ko": "[동기화] ▶ 버튼 클릭 시점 확인 — 우: {a0}",
        "en": "[Sync] ▶ Checked at button click — Right: {a0}",
        "ja": "[同期] ▶ ボタンクリック時点の確認 — 右: {a0}",
    },
    "log.sync.debug_direction": {
        "ko": "[동기화] ▶ 현재 동기화 방향 설정: {a0}  (코드값: '{a1}')",
        "en": "[Sync] ▶ Current sync direction: {a0}  (code: '{a1}')",
        "ja": "[同期] ▶ 現在の同期方向設定: {a0}（コード値: '{a1}'）",
    },
    "log.sync.same_path_warning": {
        "ko": "[동기화] ⚠ 좌·우 경로가 완전히 동일합니다 — 이 경우 항상 '차이 없음'이 나옵니다.",
        "en": "[Sync] ⚠ The left and right paths are identical — this will always report 'no differences'.",
        "ja": "[同期] ⚠ 左右のパスが完全に同一です — この場合、常に「差分なし」になります。",
    },
    "log.sync.analyze_start": {
        "ko": "[동기화] 분석 시작 (하위포함={a0}, 방향={a1})",
        "en": "[Sync] Starting analysis (include subfolders={a0}, direction={a1})",
        "ja": "[同期] 分析開始（サブフォルダを含む={a0}、方向={a1}）",
    },
    "log.sync.debug_scan_start": {
        "ko": "[동기화] ▶ 스캔 시작 직전 확인 — 좌: {a0}  /  우: {a1}",
        "en": "[Sync] ▶ Checked just before scan start — Left: {a0}  /  Right: {a1}",
        "ja": "[同期] ▶ スキャン開始直前の確認 — 左: {a0}　/　右: {a1}",
    },
    "log.sync.analyze_failed": {
        "ko": "[오류] 분석 실패: {a0}",
        "en": "[Error] Analysis failed: {a0}",
        "ja": "[エラー] 分析失敗: {a0}",
    },
    "msg.sync.analyze_error": {
        "ko": "대상 분석 중 오류가 발생했습니다:\n{a0}",
        "en": "An error occurred while analyzing the targets:\n{a0}",
        "ja": "対象の分析中にエラーが発生しました:\n{a0}",
    },
    "log.sync.scan_done": {
        "ko": "[동기화] 스캔 완료 — 비교된 항목 총 {a0}개 ({a1})",
        "en": "[Sync] Scan complete — {a0} item(s) compared in total ({a1})",
        "ja": "[同期] スキャン完了 — 比較された項目 合計{a0}個（{a1}）",
    },
    "log.sync.conflicts": {
        "ko": "[주의] 충돌(보류) {a0}건: mtime 동일·크기 다름 → 자동 처리 안 함",
        "en": "[Notice] {a0} conflict(s) held back: same mtime, different size → not handled automatically",
        "ja": "[注意] 競合（保留） {a0}件: mtime同一・サイズ違い → 自動処理しません",
    },
    "log.sync.nothing_but_skipped": {
        "ko": "[동기화] 실행할 작업 없음 — 다만 {a0} 전용 항목 {a1}개가 단방향 설정으로 무시됨 (방향: {a2})",
        "en": "[Sync] Nothing to do — but {a1} item(s) only on the {a0} side were ignored due to the one-way setting (direction: {a2})",
        "ja": "[同期] 実行する作業なし — ただし{a0}専用の項目{a1}個が一方向設定により無視されました（方向: {a2}）",
    },
    "msg.sync.no_diff": {
        "ko": "차이가 없습니다. 이미 동기화 상태입니다.",
        "en": "There's no difference. It's already in sync.",
        "ja": "差分はありません。すでに同期済みです。",
    },
    "log.sync.no_changes": {
        "ko": "[동기화] 변경할 항목 없음",
        "en": "[Sync] Nothing to change",
        "ja": "[同期] 変更する項目なし",
    },
    "log.sync.user_cancelled": {
        "ko": "[동기화] 사용자 취소",
        "en": "[Sync] Cancelled by the user",
        "ja": "[同期] ユーザーによるキャンセル",
    },
    "log.sync.nothing_selected": {
        "ko": "[동기화] 선택된 항목 없음",
        "en": "[Sync] No items selected",
        "ja": "[同期] 選択された項目なし",
    },
    "log.sync.done": {
        "ko": "[동기화] 완료: {a0}/{a1} 처리",
        "en": "[Sync] Done: {a0}/{a1} processed",
        "ja": "[同期] 完了: {a0}/{a1} 処理",
    },
    "msg.sync.done_body": {
        "ko": "{a0}/{a1} 항목 처리 완료",
        "en": "{a0}/{a1} item(s) processed",
        "ja": "{a0}/{a1}件の処理が完了しました",
    },
    "label.left": {
        "ko": "L",
        "en": "L",
        "ja": "L",
    },
    "label.right": {
        "ko": "R",
        "en": "R",
        "ja": "R",
    },
    "label.move": {
        "ko": "이동",
        "en": "Move",
        "ja": "移動",
    },
    "label.copy": {
        "ko": "복사",
        "en": "Copy",
        "ja": "コピー",
    },
    "label.precise": {
        "ko": "정밀",
        "en": "Precise",
        "ja": "精密",
    },
    "label.fast": {
        "ko": "빠른",
        "en": "Fast",
        "ja": "高速",
    },
    "label.trash": {
        "ko": "휴지통",
        "en": "Recycle Bin",
        "ja": "ごみ箱",
    },
    "label.permanent": {
        "ko": "영구",
        "en": "Permanent",
        "ja": "完全",
    },
    "label.trash_moved": {
        "ko": "휴지통 이동",
        "en": "moved to Recycle Bin",
        "ja": "ごみ箱へ移動",
    },
    "label.permanent_deleted": {
        "ko": "영구 삭제",
        "en": "permanently deleted",
        "ja": "完全削除",
    },
    "label.folder_prefix": {
        "ko": "[폴더] ",
        "en": "[Folder] ",
        "ja": "[フォルダ] ",
    },
    "label.no_ext": {
        "ko": "(확장자없음)",
        "en": "(no extension)",
        "ja": "（拡張子なし）",
    },
    "label.none": {
        "ko": "없음",
        "en": "none",
        "ja": "なし",
    },
    "err.os.in_use": {
        "ko": "다른 프로그램(탐색기 미리보기, 편집기, 실행 중인 프로그램 등)이 이 폴더 안의 파일을 사용하고 있어서 처리하지 못했습니다.\n해당 파일을 열어둔 프로그램을 닫은 뒤 다시 시도해 주세요.",
        "en": "Couldn't complete this because another program (Explorer preview, an editor, a running app, etc.) is using a file inside this folder.\nClose that program and try again.",
        "ja": "別のプログラム（エクスプローラーのプレビュー、エディタ、実行中のアプリなど）がこのフォルダ内のファイルを使用しているため処理できませんでした。\nそのファイルを開いているプログラムを閉じてから、もう一度お試しください。",
    },
    "err.os.no_permission": {
        "ko": "접근 권한이 없어 처리하지 못했습니다.\n읽기 전용 속성이 설정되어 있거나, 관리자 권한이 필요한 폴더일 수 있습니다.",
        "en": "Couldn't complete this due to a permissions issue.\nThe item may be read-only, or the folder may require administrator rights.",
        "ja": "アクセス権限がないため処理できませんでした。\n読み取り専用属性が設定されているか、管理者権限が必要なフォルダの可能性があります。",
    },
    "err.os.dir_not_empty": {
        "ko": "폴더 안에 아직 남아 있는 항목이 있어 처리하지 못했습니다.",
        "en": "Couldn't complete this because the folder still contains items.",
        "ja": "フォルダ内にまだ項目が残っているため処理できませんでした。",
    },
    "err.os.not_found": {
        "ko": "이미 삭제되었거나 경로를 찾을 수 없습니다. 새로고침(F5) 후 다시 확인해 보세요.",
        "en": "It may already be deleted, or the path can't be found. Try refreshing (F5) and checking again.",
        "ja": "すでに削除されているか、パスが見つかりません。更新（F5）してからもう一度ご確認ください。",
    },
    "log.ext_stats.access_denied": {
        "ko": "[{side}] 폴더 접근 불가",
        "en": "[{side}] Cannot access the folder",
        "ja": "[{side}] フォルダにアクセスできません",
    },
    "log.ext_stats.no_direct_files": {
        "ko": "[{side}] 직속 파일 없음 (하위 폴더만 있거나 빈 폴더)",
        "en": "[{side}] No direct files (only subfolders, or the folder is empty)",
        "ja": "[{side}] 直下にファイルなし（サブフォルダのみ、または空フォルダ）",
    },
    "log.ext_stats.summary": {
        "ko": "[{side}] 직속 파일 총 {total}개   │   ",
        "en": "[{side}] {total} direct file(s) total   │   ",
        "ja": "[{side}] 直下のファイル 合計{total}個   │   ",
    },
    "log.dupfind.target_list_header": {
        "ko": "[중복찾기] 현재 검사 대상 목록:\n    ",
        "en": "[Duplicate Finder] Current target list:\n    ",
        "ja": "[重複ファイル検索] 現在の検査対象一覧:\n    ",
    },
    "log.sync.copy": {
        "ko": "복사 {dir}: {rel}",
        "en": "Copy {dir}: {rel}",
        "ja": "コピー {dir}: {rel}",
    },
    "log.sync.delete": {
        "ko": "삭제 {side}: {rel}",
        "en": "Delete {side}: {rel}",
        "ja": "削除 {side}: {rel}",
    },
    "log.sync.failed": {
        "ko": "실패: {rel} ({error})",
        "en": "Failed: {rel} ({error})",
        "ja": "失敗: {rel} ({error})",
    },

    # ==== [v40] 마저 찾은 팝업/메뉴/커스텀 다이얼로그 국제화 ====
    "common.btn_cancel": {
        "ko": "취소",
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "common.btn_retry": {
        "ko": "다시 시도",
        "en": "Retry",
        "ja": "再試行",
    },
    "label.apply": {
        "ko": "적용",
        "en": "Apply",
        "ja": "適用",
    },
    "label.left_side": {
        "ko": "좌측",
        "en": "the left side",
        "ja": "左側",
    },
    "label.right_side": {
        "ko": "우측",
        "en": "the right side",
        "ja": "右側",
    },
    "label.permanently": {
        "ko": "영구적으로",
        "en": "permanently",
        "ja": "完全に",
    },
    "label.to_trash": {
        "ko": "휴지통으로",
        "en": "to the Recycle Bin",
        "ja": "ごみ箱へ",
    },
    "menu.add_dupfind_target": {
        "ko": "폴더 추가 (중복 검사 대상)",
        "en": "Add Folder (duplicate-scan target)",
        "ja": "フォルダ追加（重複検査対象）",
    },
    "menu.reveal_in_explorer": {
        "ko": "탐색기 열기",
        "en": "Open in Explorer",
        "ja": "エクスプローラーを開く",
    },
    "menu.create_subfolder": {
        "ko": "하위 폴더 생성",
        "en": "Create Subfolder",
        "ja": "サブフォルダの作成",
    },
    "menu.rename": {
        "ko": "이름 변경",
        "en": "Rename",
        "ja": "名前の変更",
    },
    "menu.delete": {
        "ko": "삭제",
        "en": "Delete",
        "ja": "削除",
    },
    "menu.bulk_rename_this_folder": {
        "ko": "이 폴더의 파일명 일괄 변경",
        "en": "Bulk-rename files in this folder",
        "ja": "このフォルダのファイル名を一括変更",
    },
    "tree.header": {
        "ko": "📁 {path}   ({when} 기준)",
        "en": "📁 {path}   (as of {when})",
        "ja": "📁 {path}   ({when} 時点)",
    },
    "tree.total": {
        "ko": "전체: {size} · 파일 {files}개 · 폴더 {dirs}개 (하위 폴더 포함, 숨김·시스템 항목 제외)",
        "en": "Total: {size} · {files} file(s) · {dirs} folder(s) (incl. subfolders, hidden/system excluded)",
        "ja": "合計: {size} · ファイル{files}個 · フォルダ{dirs}個(サブフォルダ含む、隠し・システム除外)",
    },
    "tree.options": {
        "ko": "보기 옵션: {content} · {depth}",
        "en": "Options: {content} · {depth}",
        "ja": "表示オプション: {content} · {depth}",
    },
    "tree.opt.folders": {"ko": "폴더만", "en": "Folders only", "ja": "フォルダのみ"},
    "tree.opt.files": {"ko": "파일까지", "en": "Folders and files", "ja": "ファイルまで"},
    "tree.opt.depth_all": {"ko": "깊이 끝까지", "en": "All levels", "ja": "全階層"},
    "tree.opt.depth_n": {"ko": "{n}단계까지", "en": "Up to {n} level(s)", "ja": "{n}階層まで"},
    "tree.meta": {
        "ko": "{size} · 파일 {files} · 폴더 {dirs} · 최근 {date}",
        "en": "{size} · {files} files · {dirs} folders · latest {date}",
        "ja": "{size} · ファイル{files} · フォルダ{dirs} · 最新{date}",
    },
    "tree.files_n": {"ko": "파일 {n}개", "en": "{n} file(s)", "ja": "ファイル{n}個"},
    "tree.sec.children": {
        "ko": "── 바로 아래 폴더 (용량 큰 순, 하위 포함) ──",
        "en": "── Immediate subfolders (largest first, incl. subfolders) ──",
        "ja": "── 直下のフォルダ(容量の大きい順、サブフォルダ含む) ──",
    },
    "tree.sec.heavy": {
        "ko": "── 파일이 직접 많이 쌓인 폴더 TOP {n} (그 폴더에 바로 들어 있는 파일 용량) ──",
        "en": "── Top {n} folders by files stored directly in them ──",
        "ja": "── ファイルが直接多くたまったフォルダ TOP {n}(そのフォルダ直下のファイル容量) ──",
    },
    "tree.sec.ext": {
        "ko": "── 확장자별 용량 (큰 순) ──",
        "en": "── Size by file extension (largest first) ──",
        "ja": "── 拡張子別の容量(大きい順) ──",
    },
    "tree.sec.tree": {"ko": "── 폴더 구조 ──", "en": "── Folder structure ──", "ja": "── フォルダ構造 ──"},
    "tree.unreadable": {"ko": "(읽을 수 없음)", "en": "(unreadable)", "ja": "(読み取り不可)"},
    "tree.truncated": {
        "ko": "… 콘솔에는 구조를 {n}줄까지만 보여 줍니다. 전체는 [구조 텍스트 저장]으로 파일에 저장하세요.",
        "en": "… The console shows only the first {n} lines of the structure. Use [Save Structure as Text] for everything.",
        "ja": "… コンソールには構造を{n}行までしか表示しません。全体は[構造をテキスト保存]でファイルに保存してください。",
    },
    "tree.dlg.title": {"ko": "폴더 구조 옵션", "en": "Folder Structure Options", "ja": "フォルダ構造のオプション"},
    "tree.dlg.folders": {
        "ko": "폴더만 (추천 — 파일이 많아도 한눈에)",
        "en": "Folders only (recommended — readable even with many files)",
        "ja": "フォルダのみ(おすすめ — ファイルが多くても一目で)",
    },
    "tree.dlg.files": {
        "ko": "파일까지 (파일 이름·크기 모두 — 파일이 많으면 아주 길어짐)",
        "en": "Folders and files (every name and size — very long with many files)",
        "ja": "ファイルまで(名前・サイズすべて — ファイルが多いと非常に長くなる)",
    },
    "tree.dlg.depth": {"ko": "보여 줄 깊이", "en": "Levels to show", "ja": "表示する階層"},
    "tree.dlg.depth_all": {"ko": "끝까지", "en": "All", "ja": "すべて"},
    "tree.dlg.meta": {
        "ko": "폴더마다 용량·파일 수·폴더 수·최근 수정일, 맨 위에 용량 요약 표시",
        "en": "Show size, file/folder counts and latest date per folder, plus a size summary on top",
        "ja": "フォルダごとに容量・ファイル数・フォルダ数・最終更新日、先頭に容量のまとめを表示",
    },
    "tree.dlg.hint": {
        "ko": "깊이를 줄여도 용량·개수는 맨 아래까지 모두 합쳐서 셉니다.",
        "en": "Sizes and counts always include every level, even when fewer levels are shown.",
        "ja": "階層を減らしても、容量・個数は最下層まですべて合算します。",
    },
    "status.tree.scanning": {
        "ko": "폴더 구조를 읽는 중… 폴더 {dirs}개 · 파일 {files}개",
        "en": "Reading folder structure… {dirs} folder(s) · {files} file(s)",
        "ja": "フォルダ構造を読み込み中… フォルダ{dirs}個 · ファイル{files}個",
    },
    "status.tree.writing": {
        "ko": "구조 글자를 만드는 중…",
        "en": "Building the structure text…",
        "ja": "構造テキストを作成中…",
    },
    "log.tree.done": {
        "ko": "[구조] {path} — 폴더 {dirs}개 · 파일 {files}개 · {size} ({sec}초)",
        "en": "[Structure] {path} — {dirs} folder(s) · {files} file(s) · {size} ({sec}s)",
        "ja": "[構造] {path} — フォルダ{dirs}個 · ファイル{files}個 · {size}({sec}秒)",
    },
    "log.tree.saved": {
        "ko": "[구조] 저장했습니다: {path} ({lines}줄)",
        "en": "[Structure] Saved: {path} ({lines} lines)",
        "ja": "[構造] 保存しました: {path}({lines}行)",
    },
    "msg.tree.failed": {
        "ko": "폴더 구조를 만들지 못했습니다.\n{err}",
        "en": "Could not build the folder structure.\n{err}",
        "ja": "フォルダ構造を作成できませんでした。\n{err}",
    },
    "dupfind.tree.open_tip": {
        "ko": "더블클릭: 탐색기에서 열기 · 오른쪽 클릭: 메뉴",
        "en": "Double-click: open in Explorer · Right-click: menu",
        "ja": "ダブルクリック: エクスプローラーで開く · 右クリック: メニュー",
    },
    "dupfind.menu.open_folder": {
        "ko": "들어 있는 폴더 열기",
        "en": "Open containing folder",
        "ja": "格納フォルダを開く",
    },
    "dupfind.menu.copy_path": {
        "ko": "경로 복사",
        "en": "Copy path",
        "ja": "パスをコピー",
    },
    "dupfind.btn_keep_newest": {
        "ko": "최신만 남기고 모두 체크",
        "en": "Check all but newest",
        "ja": "最新だけ残して全チェック",
    },
    "dupfind.btn_keep_newest.tip": {
        "ko": "중복 그룹마다 가장 최근에 수정된 파일 하나만 남기고 나머지를 모두 체크합니다.\n체크만 하므로, 확인한 뒤 [삭제] 또는 [이동]을 눌러 한꺼번에 정리하세요.",
        "en": "In every duplicate group, keep only the most recently modified file and check all the others.\nIt only checks them — review, then press [Delete] or [Move] to clean up at once.",
        "ja": "重複グループごとに最も新しく更新されたファイルを1つだけ残し、残りをすべてチェックします。\nチェックするだけなので、確認してから[削除]または[移動]でまとめて整理してください。",
    },
    "dupfind.menu.check_all_but_newest": {
        "ko": "그룹마다 최신 파일만 남기고 모두 체크",
        "en": "Check all except the newest file of each group",
        "ja": "各グループの最新ファイル以外をすべてチェック",
    },
    "status.dupfind.checked_newest": {
        "ko": "[중복찾기] 그룹 {g}개에서 최신 파일만 남기고 {n}개를 체크했습니다. 확인 후 [삭제] 또는 [이동]을 누르세요.",
        "en": "[Duplicate Finder] Checked {n} file(s), keeping the newest in each of {g} group(s). Review, then press [Delete] or [Move].",
        "ja": "[重複ファイル検索] {g}グループで最新ファイルだけ残し、{n}個をチェックしました。確認後[削除]または[移動]を押してください。",
    },
    "dupfind.menu.check_all_but_first": {
        "ko": "그룹마다 첫 파일만 남기고 모두 체크",
        "en": "Check all except the first file of each group",
        "ja": "各グループの最初のファイル以外をすべてチェック",
    },
    "dupfind.menu.uncheck_all": {
        "ko": "체크 모두 해제",
        "en": "Uncheck all",
        "ja": "チェックをすべて解除",
    },
    "status.dupfind.path_copied": {
        "ko": "경로를 클립보드에 복사했습니다.",
        "en": "Path copied to the clipboard.",
        "ja": "パスをクリップボードにコピーしました。",
    },
    "status.dupfind.checked_n": {
        "ko": "{n}개 파일을 체크했습니다(그룹마다 첫 파일은 남김).",
        "en": "Checked {n} file(s) (the first file of each group is kept).",
        "ja": "{n}個のファイルをチェックしました(各グループの最初のファイルは残します)。",
    },
    "status.dupfind.folders_found": {
        "ko": "복사된 것으로 보이는 폴더 {n}쌍 — 콘솔 로그에서 확인하세요.",
        "en": "{n} folder pair(s) look like copies — see the console log.",
        "ja": "コピーと思われるフォルダ{n}組 — コンソールログを確認してください。",
    },
    "log.dupfind.folders.header": {
        "ko": "[중복찾기] 📁 폴더 분석 — 통째 복사 {full}쌍 · 한쪽이 다른 쪽에 포함 {contained}쌍 · 대부분 겹침 {partial}쌍 (겹치는 용량이 큰 순)",
        "en": "[Duplicate Finder] 📁 Folder analysis — {full} full copy pair(s) · {contained} contained · {partial} mostly overlapping (largest first)",
        "ja": "[重複ファイル検索] 📁 フォルダ分析 — 丸ごとコピー{full}組 · 片方が他方に包含{contained}組 · ほぼ重複{partial}組(重複容量の大きい順)",
    },
    "log.dupfind.folders.full": {
        "ko": "  {i}. [통째 복사] 두 폴더의 파일 {n}개({size})가 서로 모두 같음",
        "en": "  {i}. [Full copy] all {n} file(s) ({size}) are identical in both folders",
        "ja": "  {i}. [丸ごとコピー] 両フォルダのファイル{n}個({size})がすべて同じ",
    },
    "log.dupfind.folders.contained": {
        "ko": "  {i}. [포함] A의 파일 {n}개({size})가 모두 B에도 있음 (B 파일의 {pct}%가 A와 같음)",
        "en": "  {i}. [Contained] all {n} file(s) ({size}) in A also exist in B ({pct}% of B matches A)",
        "ja": "  {i}. [包含] Aのファイル{n}個({size})がすべてBにもある(Bのファイルの{pct}%がAと同じ)",
    },
    "log.dupfind.folders.partial": {
        "ko": "  {i}. [대부분 겹침] A의 {pct_a}%, B의 {pct_b}%가 서로 같음 (겹치는 용량 {size})",
        "en": "  {i}. [Mostly overlapping] {pct_a}% of A and {pct_b}% of B are identical ({size} overlap)",
        "ja": "  {i}. [ほぼ重複] Aの{pct_a}%、Bの{pct_b}%が同じ(重複容量{size})",
    },
    "log.dupfind.folders.footer": {
        "ko": "[중복찾기] 폴더째 정리하기 전에 탐색기에서 두 폴더를 직접 확인하세요(결과 목록에서 더블클릭하면 열림). 하위 폴더 포함, 숨김·시스템 파일과 0바이트 파일은 세지 않음.",
        "en": "[Duplicate Finder] Check both folders in Explorer before removing a whole folder (double-click a result to open it). Subfolders included; hidden/system and 0-byte files not counted.",
        "ja": "[重複ファイル検索] フォルダごと整理する前に、エクスプローラーで両方のフォルダを確認してください(結果をダブルクリックで開く)。サブフォルダを含み、隠し・システム・0バイトのファイルは数えません。",
    },
    "dupfind.tree.group_label": {
        "ko": "중복 {n}개",
        "en": "{n} duplicate(s)",
        "ja": "重複{n}個",
    },
    "dupfind.summary": {
        "ko": "중복 그룹 {n_groups}개 · 파일 {n_files}개 · 절약 가능 용량 {size}",
        "en": "{n_groups} group(s) · {n_files} file(s) · {size} reclaimable",
        "ja": "重複グループ{n_groups}個・ファイル{n_files}個・削減可能容量 {size}",
    },
    "dupfind.summary_empty": {
        "ko": "중복 파일이 발견되지 않았습니다.",
        "en": "No duplicate files were found.",
        "ja": "重複ファイルは見つかりませんでした。",
    },
    "msg.dupfind.mode_desc_precise": {
        "ko": "정밀 스캔(전체 내용을 끝까지 읽어 확인 — 가장 정확하지만 느림)",
        "en": "Precise Scan (reads the entire content to confirm — most accurate but slower)",
        "ja": "精密スキャン（内容全体を読んで確認 — 最も正確ですが遅い）",
    },
    "msg.dupfind.mode_desc_fast": {
        "ko": "빠른 스캔(일부만 읽어 빠르게 확인 — 매우 드물게 오탐 가능)",
        "en": "Fast Scan (reads only part of the file to confirm quickly — very rarely may misclassify)",
        "ja": "高速スキャン（一部だけ読んで素早く確認 — ごくまれに誤判定の可能性あり）",
    },
    "status.dupfind.running_precise": {
        "ko": "정밀 스캔 진행 중입니다…",
        "en": "Running precise scan…",
        "ja": "精密スキャン実行中…",
    },
    "status.dupfind.running_precise_verify": {
        "ko": "정밀 재검사 진행 중입니다…(찾은 후보만 대상)",
        "en": "Running precise re-check… (candidates only)",
        "ja": "精密再検査実行中…（候補のみ対象）",
    },
    "status.dupfind.running_fast": {
        "ko": "빠른 스캔 진행 중입니다…",
        "en": "Running fast scan…",
        "ja": "高速スキャン実行中…",
    },
    "status.dupfind.paused_confirm": {
        "ko": "일시 정지됨 — 중단 여부를 확인해 주세요",
        "en": "Paused — please confirm whether to stop",
        "ja": "一時停止中 — 中止するか確認してください",
    },
    "msg.dupfind.delete_result": {
        "ko": "{n}개 파일을 {mode} 삭제했습니다.",
        "en": "{mode} {n} file(s).",
        "ja": "{n}個のファイルを{mode}削除しました。",
    },
    "msg.dupfind.move_result": {
        "ko": "{n}개 파일을 이동했습니다.",
        "en": "Moved {n} file(s).",
        "ja": "{n}個のファイルを移動しました。",
    },
    "msg.dupfind.pick_move_dest": {
        "ko": "이동할 폴더 선택",
        "en": "Select Folder to Move To",
        "ja": "移動先フォルダを選択",
    },
    "msg.common.fail_list_header": {
        "ko": "\n\n[실패 목록]\n",
        "en": "\n\n[Failures]\n",
        "ja": "\n\n[失敗リスト]\n",
    },
    "imgedit.no_image": {
        "ko": "이미지 없음",
        "en": "No image",
        "ja": "画像なし",
    },
    "imgedit.badge_applied": {
        "ko": "  ·  적용됨",
        "en": "  ·  Applied",
        "ja": "  ・  適用済み",
    },
    "imgedit.badge_saved": {
        "ko": "  ·  저장됨",
        "en": "  ·  Saved",
        "ja": "  ・  保存済み",
    },
    # [v49.2] 저장·JPG 변환 중 "처리 중" 덮개 문구
    "status.imgedit.saving": {
        "ko": "이미지 저장 중… {a0}/{a1}",
        "en": "Saving images… {a0}/{a1}",
        "ja": "画像を保存中… {a0}/{a1}",
    },
    "status.imgedit.converting": {
        "ko": "JPG로 변환 중… {a0}/{a1}",
        "en": "Converting to JPG… {a0}/{a1}",
        "ja": "JPGに変換中… {a0}/{a1}",
    },
    "msg.imgedit.save_result": {
        "ko": "{n}개 이미지를 저장했습니다.",
        "en": "Saved {n} image(s).",
        "ja": "{n}個の画像を保存しました。",
    },
    "imgedit.dest_hint": {
        "ko": "[{label}] 대상 폴더 선택 후 Enter 또는 우클릭 · Esc=취소",
        "en": "[{label}] Select a destination folder, then Enter or right-click · Esc=cancel",
        "ja": "[{label}] 対象フォルダを選択後、Enterまたは右クリック・Esc=キャンセル",
    },
    "imgedit.menu_move_copy_here": {
        "ko": "이 폴더로 {label}",
        "en": "{label} to This Folder",
        "ja": "このフォルダへ{label}",
    },
    "imgedit.crop_reapply_hint": {
        "ko": "적용됨 · 드래그하면 이 결과 위에 다시 크롭",
        "en": "Applied · Drag to crop again on top of this result",
        "ja": "適用済み・ドラッグするとこの結果の上に再度クロップ",
    },
    "imgedit.curve_hint": {
        "ko": "클릭: 포인트 추가 · 드래그: 이동 · 우클릭: 포인트 삭제",
        "en": "Click: add point · Drag: move · Right-click: delete point",
        "ja": "クリック: ポイント追加・ドラッグ: 移動・右クリック: ポイント削除",
    },
    "imgedit.curve_reset": {
        "ko": "초기화",
        "en": "Reset",
        "ja": "リセット",
    },
    "imgedit.thumb_loading": {
        "ko": "썸네일 로딩 중... ({n}개)",
        "en": "Loading thumbnails... ({n})",
        "ja": "サムネイル読み込み中...（{n}個）",
    },
    "imgedit.thumb_count_cache": {
        "ko": "{n}개 이미지 (캐시: {cache})",
        "en": "{n} image(s) (cache: {cache})",
        "ja": "{n}個の画像（キャッシュ: {cache}）",
    },
    "imgedit.thumb_loading_cancelled": {
        "ko": "로딩 취소됨",
        "en": "Loading cancelled",
        "ja": "読み込みキャンセル",
    },
    "imgedit.thumb_error": {
        "ko": "오류: {error}",
        "en": "Error: {error}",
        "ja": "エラー: {error}",
    },
    "msg.common.delete_failed_body": {
        "ko": "'{name}' 삭제 중 문제가 발생했습니다.",
        "en": "A problem occurred while deleting '{name}'.",
        "ja": "「{name}」の削除中に問題が発生しました。",
    },
    "msg.title.delete_failed": {
        "ko": "삭제 실패",
        "en": "Delete Failed",
        "ja": "削除失敗",
    },
    "msg.common.save_structure_text": {
        "ko": "구조 텍스트 저장",
        "en": "Save Structure as Text",
        "ja": "構造テキストの保存",
    },
    # [v49.3] 같은 이름 자동 일련번호 · 처리 중 · 겹침 오류
    "msg.rename.auto_numbered": {
        "ko": "같은 이름이 여러 개라 줄 순서대로 일련번호를 붙입니다:\n{a0}",
        "en": "Some names are the same, so sequence numbers are added in line order:\n{a0}",
        "ja": "同じ名前が複数あるため、行の順に連番を付けます:\n{a0}",
    },
    "msg.rename.still_duplicate": {
        "ko": "일련번호를 붙여도 이름이 겹칩니다. 겹치는 이름을 고쳐 주세요.",
        "en": "Names still overlap even after numbering. Please fix the overlapping names.",
        "ja": "連番を付けても名前が重複します。重複している名前を直してください。",
    },
    "msg.rename.exists_outside": {
        "ko": "'{a0}' 이름의 파일이 폴더에 이미 있습니다(목록에 보이지 않는 숨김·시스템 파일). 다른 이름을 써 주세요.",
        "en": "A file named '{a0}' already exists in the folder (a hidden/system file not in the list). Use another name.",
        "ja": "'{a0}' という名前のファイルがフォルダにすでにあります（一覧に出ない隠し・システムファイル）。別の名前にしてください。",
    },
    "status.rename.applying": {
        "ko": "이름 바꾸는 중… {a0}/{a1}",
        "en": "Renaming… {a0}/{a1}",
        "ja": "名前を変更中… {a0}/{a1}",
    },
    "msg.rename.confirm_simple": {
        "ko": "정말로 이름을 변경하시겠습니까?",
        "en": "Are you sure you want to rename these?",
        "ja": "本当に名前を変更しますか？",
    },
    "msg.rename.more_n": {
        "ko": "\n  … 외 {n}개",
        "en": "\n  … and {n} more",
        "ja": "\n  … 他{n}個",
    },
    "msg.rename.confirm_folder_change": {
        "ko": "다음 {n}개 폴더의 이름이 변경됩니다.\n폴더명 변경은 하위 파일/폴더 경로 전체에 영향을 미치며 되돌리기 어렵습니다.\n\n{preview}\n\n정말로 진행하시겠습니까?",
        "en": "The following {n} folder(s) will be renamed.\nRenaming a folder affects the paths of everything inside it and is hard to undo.\n\n{preview}\n\nAre you sure you want to proceed?",
        "ja": "次の{n}個のフォルダの名前が変更されます。\nフォルダ名の変更は中のすべてのファイル/フォルダのパスに影響し、元に戻すのが困難です。\n\n{preview}\n\n本当に続行しますか？",
    },
    "msg.rename.result": {
        "ko": "총 {n}개의 이름이 변경되었습니다.",
        "en": "{n} item(s) were renamed.",
        "ja": "合計{n}個の名前が変更されました。",
    },
    "msg.rename.nfc_fixed_n": {
        "ko": "{n}개 이름을 고쳤습니다.",
        "en": "Fixed {n} name(s).",
        "ja": "{n}個の名前を修正しました。",
    },
    "msg.rename.nfc_skipped_n": {
        "ko": "\n{n}개는 이름이 겹쳐 건너뛰었습니다.",
        "en": "\n{n} were skipped due to a name conflict.",
        "ja": "\n{n}個は名前が重複していたためスキップしました。",
    },
    "msg.rename.nfc_failed_n": {
        "ko": "\n{n}개는 오류로 실패했습니다.",
        "en": "\n{n} failed due to an error.",
        "ja": "\n{n}個はエラーで失敗しました。",
    },
    "msg.title.sync_scope": {
        "ko": "동기화 범위",
        "en": "Sync Scope",
        "ja": "同期範囲",
    },
    "msg.sync.scope_body": {
        "ko": "하위 폴더까지 모두 포함하여 동기화할까요?\n· 예(권장): 모든 하위 폴더 재귀 동기화\n· 아니오: 현재 폴더의 파일만 비교",
        "en": "Include all subfolders in the sync?\n· Yes (recommended): Recursively sync all subfolders\n· No: Compare only the files in the current folder",
        "ja": "サブフォルダもすべて含めて同期しますか？\n・はい（推奨）: すべてのサブフォルダを再帰的に同期\n・いいえ: 現在のフォルダのファイルのみ比較",
    },
    "msg.sync.scope_yes": {
        "ko": "예 (하위 포함)",
        "en": "Yes (Include Subfolders)",
        "ja": "はい（サブフォルダ含む）",
    },
    "msg.sync.scope_no": {
        "ko": "아니오 (현재만)",
        "en": "No (Current Folder Only)",
        "ja": "いいえ（現在のみ）",
    },
    "status.sync.checking_targets": {
        "ko": "업데이트 대상 확인 중입니다…",
        "en": "Checking items to update…",
        "ja": "更新対象を確認中…",
    },
    "status.sync.running": {
        "ko": "동기화 진행 중입니다…",
        "en": "Sync in progress…",
        "ja": "同期実行中…",
    },
    "sync.direction_desc.both": {
        "ko": "양방향(both) — 양쪽 다 서로에게 없는 파일을 복사",
        "en": "Two-way (both) — copies files missing on either side to the other",
        "ja": "双方向（both） — 両側にない相手のファイルを互いにコピー",
    },
    "sync.direction_desc.l2r": {
        "ko": "좌→우 단방향(l2r) — 우측에만 있는 파일은 무시(복사 안 함)",
        "en": "Left→Right one-way (l2r) — files only on the right are ignored (not copied)",
        "ja": "左→右 一方向（l2r） — 右側のみにあるファイルは無視（コピーしない）",
    },
    "sync.direction_desc.r2l": {
        "ko": "우→좌 단방향(r2l) — 좌측에만 있는 파일은 무시(복사 안 함)",
        "en": "Right→Left one-way (r2l) — files only on the left are ignored (not copied)",
        "ja": "右→左 一方向（r2l） — 左側のみにあるファイルは無視（コピーしない）",
    },
    "msg.sync.one_way_skipped": {
        "ko": "현재 동기화 방향이 단방향으로 설정되어 있어({direction}),\n{side}에만 있는 항목 {n}개는 정책상 무시되었습니다.\n(그 방향으로도 복사하려면 환경설정에서 '양방향'으로 바꿔주세요)",
        "en": "The sync direction is currently set to one-way ({direction}),\nso {n} item(s) found only on {side} were ignored by policy.\n(To copy that way too, switch to 'Two-way' in Settings.)",
        "ja": "現在、同期方向が一方向（{direction}）に設定されているため、\n{side}にのみ存在する項目{n}個はポリシー上無視されました。\n（その方向にもコピーするには、設定で「双方向」に変更してください）",
    },
    "sync.combo_history.item": {
        "ko": "[좌] {left}  ↔  [우] {right}",
        "en": "[Left] {left}  ↔  [Right] {right}",
        "ja": "[左] {left}  ↔  [右] {right}",
    },
    "sync.combo_history.tooltip": {
        "ko": "[좌] {left}\n[우] {right}",
        "en": "[Left] {left}\n[Right] {right}",
        "ja": "[左] {left}\n[右] {right}",
    },
    "sync.preview.title": {
        "ko": "동기화 미리보기 — 실행할 항목 확인",
        "en": "Sync Preview — Confirm Items to Run",
        "ja": "同期プレビュー — 実行項目の確認",
    },
    "sync.preview.too_many": {
        "ko": "총 {n}개 항목입니다.\n항목 수가 너무 많아 하나하나 목록으로 표시하지 않고 종류별 개수만 보여드립니다.",
        "en": "There are {n} item(s) in total.\nToo many to list individually, so only counts by type are shown.",
        "ja": "合計{n}個の項目です。\n項目数が多すぎるため、一つずつではなく種類別の件数のみ表示します。",
    },
    "sync.preview.summary_box": {
        "ko": "실행될 작업 요약",
        "en": "Summary of Actions",
        "ja": "実行される作業の概要",
    },
    "sync.preview.count_n": {
        "ko": "{n}개",
        "en": "{n}",
        "ja": "{n}個",
    },
    "sync.preview.summary_warning": {
        "ko": "체크박스로 개별 항목을 골라내는 대신, 전체를 실행하거나 전체를 취소해야 합니다.\n특정 파일만 제외하고 싶다면 먼저 해당 폴더를 옮기거나 이름을 바꿔 대상에서 빼주세요.",
        "en": "Instead of picking individual items with checkboxes, you must run all or cancel all.\nTo exclude specific files, move or rename that folder first to remove it from the target.",
        "ja": "チェックボックスで個別に選ぶ代わりに、全件実行するか全件キャンセルする必要があります。\n特定のファイルだけ除外したい場合は、先にそのフォルダを移動または名前変更して対象から外してください。",
    },
    "sync.preview.run_all_n": {
        "ko": "전체 {n}개 실행",
        "en": "Run All {n}",
        "ja": "全{n}個実行",
    },
    "sync.preview.checked_only_n": {
        "ko": "총 {n}개 항목. 체크된 항목만 실행합니다.",
        "en": "There are {n} item(s) in total. Only checked items will run.",
        "ja": "合計{n}個の項目。チェックした項目のみ実行します。",
    },
    "sync.preview.col_run": {
        "ko": "실행",
        "en": "Run",
        "ja": "実行",
    },
    "sync.preview.col_state": {
        "ko": "상태",
        "en": "State",
        "ja": "状態",
    },
    "sync.preview.col_action": {
        "ko": "동작",
        "en": "Action",
        "ja": "動作",
    },
    "sync.preview.col_file": {
        "ko": "파일(상대경로)",
        "en": "File (relative path)",
        "ja": "ファイル（相対パス）",
    },
    "sync.preview.select_all": {
        "ko": "전체 선택",
        "en": "Select All",
        "ja": "すべて選択",
    },
    "sync.preview.select_none": {
        "ko": "전체 해제",
        "en": "Deselect All",
        "ja": "すべて解除",
    },
    "sync.preview.run_sync": {
        "ko": "동기화 실행",
        "en": "Run Sync",
        "ja": "同期実行",
    },
    "sync.state.only_l": {
        "ko": "좌측에만 있음",
        "en": "Left only",
        "ja": "左側のみ",
    },
    "sync.state.only_r": {
        "ko": "우측에만 있음",
        "en": "Right only",
        "ja": "右側のみ",
    },
    "sync.state.newer_l": {
        "ko": "좌측이 최신",
        "en": "Left is newer",
        "ja": "左側が最新",
    },
    "sync.state.newer_r": {
        "ko": "우측이 최신",
        "en": "Right is newer",
        "ja": "右側が最新",
    },
    "sync.state.conflict": {
        "ko": "충돌(보류)",
        "en": "Conflict (held)",
        "ja": "競合（保留）",
    },
    "sync.state.same": {
        "ko": "동일",
        "en": "Same",
        "ja": "同一",
    },
    "sync.action.copy_to_right": {
        "ko": "→ 우측으로 복사",
        "en": "→ Copy to right",
        "ja": "→ 右側へコピー",
    },
    "sync.action.copy_to_left": {
        "ko": "← 좌측으로 복사",
        "en": "← Copy to left",
        "ja": "← 左側へコピー",
    },
    "sync.action.delete_from_left": {
        "ko": "좌측에서 삭제",
        "en": "Delete from left",
        "ja": "左側から削除",
    },
    "sync.action.delete_from_right": {
        "ko": "우측에서 삭제",
        "en": "Delete from right",
        "ja": "右側から削除",
    },

    # ==== [v40] 개발자 콘솔(print) 디버그 메시지 국제화 ====
    "dbg.thumb.error_path": {
        "ko": "[썸네일] 오류 {path}: {error}",
        "en": "[Thumbnail] Error {path}: {error}",
        "ja": "[サムネイル] エラー {path}: {error}",
    },
    "dbg.thumb.load_failed": {
        "ko": "[썸네일 로드 실패] {path}: {error}",
        "en": "[Thumbnail Load Failed] {path}: {error}",
        "ja": "[サムネイル読み込み失敗] {path}: {error}",
    },
    "dbg.thumb.pixmap_failed": {
        "ko": "[Pixmap 변환 실패]: {error}",
        "en": "[Pixmap Conversion Failed]: {error}",
        "ja": "[Pixmap変換失敗]: {error}",
    },
    "dbg.thumb.ui_update_failed": {
        "ko": "[UI 업데이트 실패] {error}",
        "en": "[UI Update Failed] {error}",
        "ja": "[UI更新失敗] {error}",
    },
    "dbg.thumb.load_done": {
        "ko": "[썸네일] 로드 완료: {n}개 이미지",
        "en": "[Thumbnail] Load complete: {n} image(s)",
        "ja": "[サムネイル] 読み込み完了: {n}個の画像",
    },
    "dbg.thumb.load_cancelled": {
        "ko": "[썸네일] 로드 중단",
        "en": "[Thumbnail] Load cancelled",
        "ja": "[サムネイル] 読み込み中止",
    },
    "dbg.thumb.error": {
        "ko": "[썸네일] 오류: {error}",
        "en": "[Thumbnail] Error: {error}",
        "ja": "[サムネイル] エラー: {error}",
    },

    # ==== [v41] 크롭 비율/기준 콤보 — 내부 키/표시 라벨 분리 후 번역 ====
    "imgedit.ratio.original": {
        "ko": "원본 비율",
        "en": "Original ratio",
        "ja": "元の比率",
    },
    "imgedit.ratio.free": {
        "ko": "자유",
        "en": "Free",
        "ja": "自由",
    },
    "imgedit.basis.long_edge": {
        "ko": "긴 변 기준",
        "en": "Long edge",
        "ja": "長辺基準",
    },
    "imgedit.basis.short_edge": {
        "ko": "짧은 변 기준",
        "en": "Short edge",
        "ja": "短辺基準",
    },
    "imgedit.basis.pixel": {
        "ko": "픽셀 지정",
        "en": "Pixel size",
        "ja": "ピクセル指定",
    },

    # ==== [v43] "JPG로 변환" 일괄 변환 기능 ====
    "imgedit.btn_to_jpg": {
        "ko": "JPG로 변환",
        "en": "To JPG",
        "ja": "JPGに変換",
    },
    "imgedit.btn_to_jpg.tip": {
        "ko": "현재 폴더 안의 JPG가 아닌 이미지(HEIC, PNG, WEBP 등) 전부를 .jpg로 새로 만듭니다. 원본 파일은 그대로 두고, 같은 폴더에 같은 이름의 .jpg 파일이 추가로 생깁니다.",
        "en": "Creates a .jpg copy of every non-JPG image (HEIC, PNG, WEBP, etc.) in the current folder. Original files are left untouched — a new .jpg with the same name is added alongside each one.",
        "ja": "現在のフォルダ内のJPG以外の画像（HEIC、PNG、WEBPなど）すべてを.jpgとして新規作成します。元のファイルはそのまま残り、同じ名前の.jpgファイルが同じフォルダに追加されます。",
    },
    "msg.imgedit.no_folder_loaded": {
        "ko": "변환할 이미지가 없습니다. 좌측에서 이미지가 있는 폴더를 먼저 선택하세요.",
        "en": "There are no images to convert. Please select a folder with images on the left first.",
        "ja": "変換する画像がありません。左側で画像のあるフォルダを先に選択してください。",
    },
    "msg.imgedit.all_already_jpg": {
        "ko": "이 폴더의 이미지는 모두 이미 JPG입니다.",
        "en": "All images in this folder are already JPG.",
        "ja": "このフォルダの画像はすべてすでにJPGです。",
    },
    "msg.imgedit.confirm_convert_jpg": {
        "ko": "JPG가 아닌 이미지 {n}개를 같은 폴더에 .jpg로 새로 만듭니다.\n원본 파일은 그대로 유지됩니다.\n\n계속하시겠습니까?",
        "en": "This will create .jpg copies of {n} non-JPG image(s) in the same folder.\nOriginal files will be kept as-is.\n\nContinue?",
        "ja": "JPG以外の画像{n}個を同じフォルダに.jpgとして新規作成します。\n元のファイルはそのまま残ります。\n\n続行しますか？",
    },
    "log.imgedit.convert_skip_exists": {
        "ko": "[이미지편집] JPG 변환 건너뜀(이미 존재): {a0}",
        "en": "[Image Edit] Skipped JPG conversion (already exists): {a0}",
        "ja": "[画像編集] JPG変換をスキップ（既存）: {a0}",
    },
    "log.imgedit.converted": {
        "ko": "[이미지편집] JPG로 변환: {a0} → {a1}",
        "en": "[Image Edit] Converted to JPG: {a0} → {a1}",
        "ja": "[画像編集] JPGに変換: {a0} → {a1}",
    },
    "log.imgedit.convert_failed": {
        "ko": "[이미지편집] JPG 변환 실패: {a0} ({a1})",
        "en": "[Image Edit] JPG conversion failed: {a0} ({a1})",
        "ja": "[画像編集] JPG変換失敗: {a0}（{a1}）",
    },
    "msg.imgedit.convert_result": {
        "ko": "{n}개 이미지를 JPG로 변환했습니다.",
        "en": "Converted {n} image(s) to JPG.",
        "ja": "{n}個の画像をJPGに変換しました。",
    },
    "msg.imgedit.convert_skipped_n": {
        "ko": "\n{n}개는 같은 이름의 .jpg가 이미 있어 건너뛰었습니다.",
        "en": "\n{n} were skipped because a .jpg with the same name already exists.",
        "ja": "\n{n}個は同名の.jpgがすでに存在したためスキップしました。",
    },

    # ==== [v44] HEIC 미지원 환경 진단 메시지 ====
    "log.imgedit.heic_not_supported": {
        "ko": "[이미지편집] {a0} — HEIC/HEIF 파일을 열려면 pillow-heif 설치가 필요합니다. (pip install pillow-heif 후 프로그램을 다시 시작해 주세요. 실행 파일(exe)로 쓰고 계시다면 pillow-heif를 포함해서 다시 빌드해야 합니다.)",
        "en": "[Image Edit] {a0} — Opening HEIC/HEIF files requires pillow-heif. (Run \"pip install pillow-heif\" and restart the program. If you're using a built .exe, it needs to be rebuilt with pillow-heif included.)",
        "ja": "[画像編集] {a0} — HEIC/HEIFファイルを開くにはpillow-heifのインストールが必要です。（\"pip install pillow-heif\" を実行してからプログラムを再起動してください。exeファイルをお使いの場合は、pillow-heifを含めて再ビルドする必要があります。）",
    },
    "log.imgedit.thumb_failed_generic": {
        "ko": "[이미지편집] 썸네일 생성 실패: {a0}",
        "en": "[Image Edit] Failed to generate thumbnail: {a0}",
        "ja": "[画像編集] サムネイル生成失敗: {a0}",
    },

    # ==== [v45] 즐겨찾기 바로가기(바탕화면/다운로드/메신저 폴더) ====
    "quicklink.default.desktop": {
        "ko": "바탕화면",
        "en": "Desktop",
        "ja": "デスクトップ",
    },
    "quicklink.default.downloads": {
        "ko": "다운로드",
        "en": "Downloads",
        "ja": "ダウンロード",
    },
    "quicklink.default.messenger": {
        "ko": "메신저 폴더",
        "en": "Messenger Folder",
        "ja": "メッセンジャーフォルダ",
    },
    "quicklink.path_not_set": {
        "ko": "경로가 아직 설정되지 않았습니다 — 환경설정에서 지정하세요.",
        "en": "Path not set yet — set it in Settings.",
        "ja": "パスがまだ設定されていません — 設定で指定してください。",
    },
    "quicklink.path_not_set_body": {
        "ko": "이 바로가기는 아직 경로가 설정되지 않았습니다.\n환경설정(⚙) → \"즐겨찾기 바로가기\"에서 경로를 지정해 주세요.",
        "en": "This shortcut doesn't have a path set yet.\nGo to Settings (⚙) → \"Quick-Access Shortcuts\" to set one.",
        "ja": "このショートカットにはまだパスが設定されていません。\n設定（⚙）→「お気に入りショートカット」でパスを指定してください。",
    },
    "settings.group_quicklinks": {
        "ko": "즐겨찾기 바로가기",
        "en": "Quick-Access Shortcuts",
        "ja": "お気に入りショートカット",
    },
    "settings.quicklinks_note": {
        "ko": "좌·우 트리 위에 표시되는 바로가기 목록입니다. 기본으로 등록된 \"바탕화면\"/\"다운로드\"의 경로가 실제 환경과 다르면 아래에서 바꿔 주세요. \"메신저 폴더\"는 사용 중인 메신저 프로그램이 파일을 저장하는 실제 폴더 경로를 직접 지정해야 합니다.",
        "en": "These shortcuts appear above the left/right trees. If the default \"Desktop\"/\"Downloads\" paths don't match your setup, change them below. For \"Messenger Folder\", set the actual folder your messenger app saves files to.",
        "ja": "左右のツリーの上に表示されるショートカット一覧です。デフォルトの「デスクトップ」/「ダウンロード」のパスが実際の環境と異なる場合は、下で変更してください。「メッセンジャーフォルダ」は、使用中のメッセンジャーアプリが実際にファイルを保存するフォルダを指定してください。",
    },
    "settings.quicklinks_col_label": {
        "ko": "이름",
        "en": "Name",
        "ja": "名前",
    },
    "settings.quicklinks_col_path": {
        "ko": "경로",
        "en": "Path",
        "ja": "パス",
    },
    "settings.quicklinks_add": {
        "ko": "추가",
        "en": "Add",
        "ja": "追加",
    },
    "settings.quicklinks_browse": {
        "ko": "찾아보기...",
        "en": "Browse...",
        "ja": "参照...",
    },
    "settings.quicklinks_remove": {
        "ko": "삭제",
        "en": "Remove",
        "ja": "削除",
    },
    "settings.quicklinks_new_label": {
        "ko": "새 바로가기",
        "en": "New Shortcut",
        "ja": "新しいショートカット",
    },
    "settings.quicklinks_select_row_first": {
        "ko": "먼저 목록에서 항목을 선택하세요.",
        "en": "Please select an item in the list first.",
        "ja": "先にリストから項目を選択してください。",
    },

    # ==== [v47] 즐겨찾기 바로가기 확장(문서/사진/음악/동영상) + 콤보박스화 ====
    "quicklink.default.documents": {
        "ko": "문서",
        "en": "Documents",
        "ja": "ドキュメント",
    },
    "quicklink.default.pictures": {
        "ko": "사진",
        "en": "Pictures",
        "ja": "ピクチャ",
    },
    "quicklink.default.music": {
        "ko": "음악",
        "en": "Music",
        "ja": "ミュージック",
    },
    "quicklink.default.videos": {
        "ko": "동영상",
        "en": "Videos",
        "ja": "ビデオ",
    },
    "quicklink.combo.placeholder": {
        "ko": "⭐ 즐겨찾기 바로가기",
        "en": "⭐ Quick-Access Shortcuts",
        "ja": "⭐ お気に入りショートカット",
    },
    "quicklink.combo.tip": {
        "ko": "즐겨찾기 바로가기 — 자주 쓰는 폴더로 바로 이동합니다. 최근에 고른 항목이 목록 맨 위로 올라옵니다.",
        "en": "Quick-access shortcuts — jump straight to a frequently used folder. The most recently used one moves to the top of the list.",
        "ja": "お気に入りショートカット — よく使うフォルダへすぐに移動します。最近選んだ項目がリストの一番上に表示されます。",
    },

    # ==== [v47] 이미지 편집 모드 — Del 키로 이미지 삭제 ====
    "imgedit.confirm_delete_body": {
        "ko": "이 사진을 삭제하시겠습니까?\n'{a0}'\n(휴지통으로 이동합니다)",
        "en": "Delete this photo?\n'{a0}'\n(It will be moved to the Recycle Bin.)",
        "ja": "この写真を削除しますか？\n「{a0}」\n（ごみ箱に移動します）",
    },
    "log.imgedit.deleted": {
        "ko": "[이미지편집] 삭제({a1}): {a0}",
        "en": "[Image Edit] Deleted ({a1}): {a0}",
        "ja": "[画像編集] 削除（{a1}）: {a0}",
    },
}


# =============================================================================
# [v01] Util 모드(미니앱 모음) 공통 문구
# =============================================================================
# 도구 하나하나의 문구는 여기 넣지 않는다 — 각 미니앱 모듈이 자기 번역표를
# 들고 있다가 등록될 때 register_translations()로 이 TR에 병합한다. 그래야
# 도구가 늘어날 때마다 이 파일만 계속 비대해지는 일이 없다.
TR.update({
    "mode.util.tip": {
        "ko": "유틸리티 — 계산기처럼 수업이나 업무에서 자주 쓰는 작은 도구들을 모아 둔 곳입니다.",
        "en": "Utilities — A collection of small tools for everyday class and office work, such as a calculator.",
        "ja": "ユーティリティ — 電卓など、授業や業務でよく使う小さな道具を集めた場所です。",
    },
    "log.mode.util": {
        "ko": "[모드] 유틸리티",
        "en": "[Mode] Utilities",
        "ja": "[モード] ユーティリティ",
    },
    "status.util.hint": {
        "ko": "왼쪽 목록이나 가운데 카드에서 사용할 도구를 고르세요.",
        "en": "Pick a tool from the list on the left or from the cards in the middle.",
        "ja": "左のリストか中央のカードから使う道具を選んでください。",
    },
    "util.tree.home": {
        "ko": "전체 도구", "en": "All tools", "ja": "すべての道具",
    },
    "util.tree.recent": {
        "ko": "최근 사용", "en": "Recently used", "ja": "最近使った道具",
    },
    "util.home.title": {
        "ko": "유틸리티 도구 모음",
        "en": "Utility tools",
        "ja": "ユーティリティ道具箱",
    },
    "util.home.sub": {
        "ko": "카드를 누르면 도구가 열립니다. 도구는 앞으로 계속 추가됩니다.",
        "en": "Click a card to open a tool. More tools will be added over time.",
        "ja": "カードを押すと道具が開きます。道具は今後も追加されます。",
    },
    "util.search.placeholder": {
        "ko": "도구 검색", "en": "Search tools", "ja": "道具を検索",
    },
    "util.search.tip": {
        "ko": "도구 이름이나 설명의 일부를 입력하면 목록이 걸러집니다.",
        "en": "Type part of a tool's name or description to filter the list.",
        "ja": "道具の名前や説明の一部を入力すると一覧が絞り込まれます。",
    },
    "util.search.no_result": {
        "ko": "검색 결과가 없습니다.", "en": "No tools matched.", "ja": "該当する道具がありません。",
    },
    "util.btn.home": {
        "ko": "도구 모음", "en": "All tools", "ja": "道具箱",
    },
    "util.btn.home.tip": {
        "ko": "도구 목록(홈 화면)으로 돌아갑니다.",
        "en": "Goes back to the tool list (home screen).",
        "ja": "道具の一覧（ホーム画面）に戻ります。",
    },
    "util.lbl.current": {
        "ko": "도구:", "en": "Tool:", "ja": "道具:",
    },
    "util.log.opened": {
        "ko": "[유틸리티] 도구 열기: {a0}",
        "en": "[Utilities] Opened tool: {a0}",
        "ja": "[ユーティリティ] 道具を開きました: {a0}",
    },
    "util.log.opening": {
        "ko": "{a0} 불러오는 중…",
        "en": "Loading {a0}…",
        "ja": "{a0}を読み込み中…",
    },
    # ---- 카테고리(내부 키 → 표시 문구) ----
    "util.cat.math": {"ko": "수학", "en": "Math", "ja": "数学"},
    "util.cat.logic": {"ko": "정보컴퓨터", "en": "Info & Computing", "ja": "情報コンピュータ"},
    "util.cat.graph": {"ko": "그래프", "en": "Graphs", "ja": "グラフ"},
    "util.cat.convert": {"ko": "변환", "en": "Conversion", "ja": "変換"},
    "util.cat.class": {"ko": "학교", "en": "School", "ja": "学校"},
    "util.cat.misc": {"ko": "기타", "en": "Others", "ja": "その他"},
    "msg.util.discard_changes": {
        "ko": "저장하지 않은 내용이 있습니다. 그래도 다른 모드로 이동할까요?",
        "en": "There are unsaved changes. Switch to another mode anyway?",
        "ja": "保存していない内容があります。それでも他のモードに移動しますか？",
    },
})


# [v51] 맥에서는 "탐색기" 문구를 "Finder"로(내부 키는 그대로) — platform_info.py
from .platform_info import apply_platform_texts as _apply_platform_texts  # noqa: E402
_apply_platform_texts(TR)

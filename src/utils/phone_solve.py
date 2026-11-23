# -*- coding: utf-8 -*-
"""
FolderKit++ — 갤럭시폰 사진 옮기기 [v43] 순수 로직 (adb 래퍼 + 날짜 묶기)

신규 미니앱 개발 스펙 문서 4번 항목, 1차 범위("일자별 일괄 다운로드"로
범위를 좁힘 — 파일명 변경·크롭·화질 조정은 FolderKit++의 기존 기능을
그대로 잇는다). 연결 방식은 adb — 소수 인원(본인 및 지인 교사)용으로는
구현 대비 안정성이 가장 좋다는 문서의 판단을 그대로 따른다.

## 이 모듈은 실제 폰이 연결돼 있어야 끝까지 동작한다
`is_adb_available()`은 시스템에 adb 실행 파일이 있는지만 보고, 그
뒤의 `list_devices()`·`list_photos()`·`pull_event()`는 실제로 adb
프로세스를 실행한다 — 이 개발 환경(폰이 연결되지 않은 컨테이너)에서는
`is_adb_available()`이 False이거나, adb가 있어도 연결된 폰이 없어
빈 결과만 나온다. **순수 파싱 함수(parse_devices_output·
parse_find_output·group_into_events)는 실제 adb 출력 텍스트만 있으면
폰 없이도 검증할 수 있어, 여기 로직은 헤드리스로 충분히 확인했다.
다만 adb 프로세스를 실제로 실행하는 부분과 "최초 연결 시 USB 디버깅
허용 팝업" 같은 실기 특유의 동작은 실제 폰으로 확인이 필요하다.**
"""
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

ADB_BIN = "adb"

# [v43.4] adb.exe가 시스템 PATH에 없는 경우가 실제로 있었다(설치는 했지만
# PATH에 안 걸린 경우가 흔하다) — 사용자가 화면에서 adb.exe 파일을 직접
# 골라 지정하면 그 경로를 PATH보다 먼저 쓴다. 모듈 전역으로 두는 이유는
# 위젯이 시작할 때 한 번 설정해 두면 이 모듈의 모든 함수가 자동으로
# 그 경로를 쓰게 하기 위해서다(매 호출마다 경로를 넘길 필요가 없다).
_custom_adb_path = None


def set_adb_path(path):
    """[v43.4] 사용자가 직접 고른 adb 실행 파일 경로를 기억해 둔다.
    빈 값을 주면(None, "") 다시 자동 검색으로 돌아간다."""
    global _custom_adb_path
    _custom_adb_path = path or None


def get_adb_path():
    return _custom_adb_path


def _candidate_adb_paths():
    """[v43.7] "직접 지정" 없이도 adb.exe가 흔히 있을 만한 자리들 —
    시스템 PATH에 없어도 이 자리들은 자동으로 확인한다. 목록 끝의
    "이 프로그램과 같은 폴더"는, 나중에 platform-tools 폴더를 통째로
    복사해 같이 배포하면(문서가 원래 말한 "실행파일을 앱에 동봉") 이
    설정 자체가 아예 필요 없어지도록 미리 마련해 둔 자리다."""
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Android", "Sdk", "platform-tools", "adb.exe"))
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        program_files = os.environ.get(env_name)
        if program_files:
            candidates.append(os.path.join(program_files, "Android", "android-sdk", "platform-tools", "adb.exe"))
    try:
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates.append(os.path.join(base_dir, "platform-tools", "adb.exe"))
        candidates.append(os.path.join(base_dir, "adb", "adb.exe"))
        candidates.append(os.path.join(base_dir, "adb.exe"))
    except (OSError, ValueError):
        pass
    return candidates


def auto_detect_adb_path():
    """흔한 설치 위치를 순서대로 확인해 처음 발견되는 실제 파일 경로를
    돌려준다(없으면 None). "adb 위치 지정" 버튼을 누르기 전에, 사용자가
    아무 것도 안 해도 이미 찾아지는 경우를 최대한 늘리는 게 목적이다."""
    for path in _candidate_adb_paths():
        if path and os.path.isfile(path):
            return path
    return None


def effective_adb_path():
    """지금 실제로 쓰이는(또는 쓰일) adb 경로 — 우선순위: ① 사용자가
    직접 지정한 경로 ② 시스템 PATH에서 찾은 adb ③ 흔한 설치 위치에서
    자동으로 찾은 adb. 셋 다 없으면 None."""
    if _custom_adb_path and os.path.isfile(_custom_adb_path):
        return _custom_adb_path
    found_in_path = shutil.which(ADB_BIN)
    if found_in_path:
        return found_in_path
    return auto_detect_adb_path()


def resolve_adb_bin():
    """실제로 실행할 adb 명령 — effective_adb_path()가 찾은 경로를
    쓰고, 그마저 없으면(정말 아무 데도 없음) "adb" 그대로 돌려줘서
    시도라도 해 보게 한다(실패하면 다른 함수들이 안전하게 처리한다)."""
    return effective_adb_path() or ADB_BIN


REMOTE_DIR = "/sdcard/DCIM/Camera"
EVENT_MAX_GAP_DAYS = 1   # 사진 날짜 사이 간격이 이 안쪽이면 같은 "행사"로 묶는다

# [v43.3] Windows에서 --windowed(콘솔 없는) 배포판으로 adb.exe처럼 콘솔
# 프로그램을 subprocess로 띄우면, 콘솔 창이 잠깐 번쩍이거나(가장 흔함)
# 드물게는 표준입출력 파이프 연결이 꼬여 멈춰 버리는 경우가 있다.
# CREATE_NO_WINDOW를 주면 이 문제를 막는다. 이 속성은 Windows에만
# 있어서, 다른 OS에서는 getattr로 안전하게 0(아무 효과 없음)을 쓴다.
_NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PhotoFile:
    """폰 안의 사진(또는 동영상) 파일 하나."""

    __slots__ = ("remote_path", "name", "mtime", "size", "epoch")

    def __init__(self, remote_path, mtime, size=None):
        self.remote_path = remote_path
        self.name = remote_path.rsplit("/", 1)[-1]
        self.mtime = mtime   # datetime
        # [v47] 증분 동기화용 — size는 바이트(모르면 None), epoch는 수정
        # 시각을 초 단위 정수로 바꾼 값(전송 기록의 비교 기준).
        self.size = size
        self.epoch = int(mtime.timestamp())

    @property
    def date(self):
        return self.mtime.date()


class PhotoEvent:
    """연속된 날짜로 묶인 사진 구간 하나(화면의 "행사" 단위)."""

    def __init__(self, files):
        self.files = sorted(files, key=lambda f: f.mtime)

    @property
    def start_date(self):
        return self.files[0].date

    @property
    def end_date(self):
        return self.files[-1].date

    def __len__(self):
        return len(self.files)


def is_adb_available():
    return effective_adb_path() is not None


def parse_devices_output(raw):
    """`adb devices` 출력 → [(serial, state), ...]. 첫 줄("List of devices
    attached")은 건너뛴다."""
    devices = []
    for line in raw.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        devices.append((serial.strip(), state.strip()))
    return devices


def list_devices():
    if not is_adb_available():
        return []
    try:
        result = subprocess.run([resolve_adb_bin(), "devices"], capture_output=True, text=True, timeout=10,
                                creationflags=_NO_WINDOW_FLAG)
    except Exception:   # noqa: BLE001 — adb 실행 자체가 예상 못 한 방식으로 실패해도 화면은 안전하게 빈 목록으로
        return []
    return parse_devices_output(result.stdout)


def parse_find_output(raw):
    """`find <dir> -type f -printf '%T@ %p\\n'` 출력 → PhotoFile 목록.
    toybox find(안드로이드 기본 내장)는 -printf를 지원해서, 수정 시각
    (초 단위 UNIX epoch)과 경로를 한 줄에 공백으로 구분해 뽑을 수 있다
    — ls -la의 로캘·포맷 차이에 안 흔들리는 방식이라 이걸 쓴다.

    [v47] 크기까지 뽑는 `'%T@ %s %p\\n'` 형식도 같이 읽는다 — 경로는 항상
    "/"로 시작하므로, 시각 다음 토큰이 "/"로 시작하지 않는 숫자면 그게
    크기다. 예전 형식(크기 없음)의 줄은 size=None으로 그대로 읽힌다."""
    files = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        ts_str, rest = line.split(" ", 1)
        try:
            mtime = datetime.fromtimestamp(float(ts_str))
        except (ValueError, OSError, OverflowError):
            continue
        size = None
        if not rest.startswith("/") and " " in rest:
            size_str, path = rest.split(" ", 1)
            if size_str.isdigit() and path.startswith("/"):
                size, rest = int(size_str), path
        files.append(PhotoFile(rest, mtime, size))
    return files


def _run_find(serial, remote_dir, fmt):
    cmd = [resolve_adb_bin()] + (["-s", serial] if serial else []) + [
        "shell", f"find {remote_dir} -type f -printf '{fmt}\\n'"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                            creationflags=_NO_WINDOW_FLAG)
    return parse_find_output(result.stdout)


def list_photos(serial=None, remote_dir=REMOTE_DIR):
    """[v47] 크기까지 함께 가져온다(증분 동기화에서 "같은 파일인지"와
    "끝까지 다 받았는지" 확인에 쓴다). 폰의 find가 %s를 못 알아들어 아무
    것도 안 나오면, v43의 형식(시각+경로)으로 한 번 더 시도한다."""
    if not is_adb_available():
        return []
    try:
        files = _run_find(serial, remote_dir, "%T@ %s %p")
        if not files:
            files = _run_find(serial, remote_dir, "%T@ %p")
    except Exception:   # noqa: BLE001
        return []
    return files


def group_into_events(files, max_gap_days=EVENT_MAX_GAP_DAYS):
    """날짜 단위로 모으고, 연속된(간격이 max_gap_days 이하인) 날짜를
    하나의 PhotoEvent로 합친다. 최근 행사가 먼저 오도록 정렬한다."""
    if not files:
        return []
    by_date = {}
    for f in files:
        by_date.setdefault(f.date, []).append(f)
    dates = sorted(by_date.keys())

    groups = [[dates[0]]]
    for d in dates[1:]:
        if (d - groups[-1][-1]).days <= max_gap_days:
            groups[-1].append(d)
        else:
            groups.append([d])

    events = [PhotoEvent([f for d in g for f in by_date[d]]) for g in groups]
    events.sort(key=lambda e: e.end_date, reverse=True)
    return events


def event_date_texts(event):
    """[v47.1] 행사 목록에 보일 날짜 문자열 (시작, 끝) — 끝이 없으면(하루짜리)
    끝은 None. 폰에는 작년 사진도 섞여 있어 "12/28"만으로는 몇 년도인지
    헷갈리므로 시작 날짜에는 항상 연도를 붙인다. 끝 날짜는 같은 해면
    월/일만, 해를 넘기면(12/31 ~ 1/1) 연도까지 붙인다."""
    start, end = event.start_date, event.end_date
    start_text = start.strftime("%Y/%m/%d")
    if start == end:
        return start_text, None
    end_text = end.strftime("%m/%d") if start.year == end.year else end.strftime("%Y/%m/%d")
    return start_text, end_text


def pull_event(event, dest_dir, serial=None, progress_cb=None):
    """event에 속한 파일을 전부 dest_dir로 내려받는다(파일마다 adb pull
    한 번). 실패한 파일은 건너뛰고 계속 진행한다. progress_cb(done, total)을
    파일 하나 끝날 때마다 부른다. 반환: (성공 수, 실패한 파일명 목록)."""
    os.makedirs(dest_dir, exist_ok=True)
    ok = 0
    failed = []
    total = len(event.files)
    for i, f in enumerate(event.files, start=1):
        cmd = [resolve_adb_bin()] + (["-s", serial] if serial else []) + ["pull", f.remote_path, dest_dir]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                    creationflags=_NO_WINDOW_FLAG)
            if result.returncode == 0:
                ok += 1
            else:
                failed.append(f.name)
        except Exception:   # noqa: BLE001
            failed.append(f.name)
        if progress_cb:
            progress_cb(i, total)
    return ok, failed


def diagnose():
    """[v43.3] "새로고침을 눌러도 화면에 아무 반응이 없다"는 상황을
    위한 진단 정보 — adb 실행 파일 경로, `adb devices`를 실제로 실행한
    원본 출력(표준출력·표준에러·종료 코드)까지 전부 담아서 돌려준다.
    list_devices()처럼 조용히 빈 목록으로 넘어가지 않고, 무슨 일이
    있었는지 그대로 보여줘서 화면에 붙여 넣어 알려줄 수 있게 한다."""
    report = {
        "adb_path": effective_adb_path(),
        "adb_available": is_adb_available(),
        "devices_stdout": None, "devices_stderr": None,
        "devices_returncode": None, "devices_exception": None,
    }
    if not report["adb_available"]:
        return report
    try:
        result = subprocess.run([resolve_adb_bin(), "devices"], capture_output=True, text=True, timeout=10,
                                creationflags=_NO_WINDOW_FLAG)
        report["devices_stdout"] = result.stdout
        report["devices_stderr"] = result.stderr
        report["devices_returncode"] = result.returncode
    except Exception as e:   # noqa: BLE001 — 진단용이라 어떤 예외든 원문 그대로 보여준다
        report["devices_exception"] = f"{type(e).__name__}: {e}"
    return report


def format_diagnose_report(report):
    """diagnose()의 결과를 화면에 그대로 보여줄 수 있는 여러 줄 문자열로."""
    lines = [
        f"adb 실행 파일: {report['adb_path'] or '(PATH에서 못 찾음)'}",
        f"is_adb_available(): {report['adb_available']}",
    ]
    if report["devices_exception"]:
        lines.append(f"adb devices 실행 중 예외: {report['devices_exception']}")
    elif report["devices_returncode"] is not None:
        lines.append(f"adb devices 종료 코드: {report['devices_returncode']}")
        lines.append(f"adb devices 표준출력:\n{report['devices_stdout'] or '(비어 있음)'}")
        if report["devices_stderr"]:
            lines.append(f"adb devices 표준에러:\n{report['devices_stderr']}")
    return "\n".join(lines)


# =============================================================================
# [v47] 무선 연결(Android 11 이상의 "무선 디버깅") + 증분 동기화용 내려받기
# =============================================================================
# 이 구역도 위쪽과 마찬가지로, 출력 텍스트를 해석하는 함수(parse_*,
# is_wireless_serial, pick_preferred_device, normalize_host_port)는 폰 없이
# 헤드리스로 검증했다. **adb pair / adb connect / adb mdns services를 실제로
# 실행하는 부분은 실제 폰과 같은 와이파이 환경에서 확인이 필요하다.**

# 연결 종류 — 화면 문구가 아니라 내부 키(표시는 위젯이 tr()로 바꾼다)
CONN_USB = "usb"
CONN_WIFI = "wifi"

# 한 파일 전송 결과 — 내부 키
PULL_OK = "ok"
PULL_FAILED = "failed"
PULL_CANCELLED = "cancelled"

_HOST_PORT_RE = re.compile(r"^([0-9A-Za-z][0-9A-Za-z_.\-]*):(\d{1,5})$")
_PAIR_CODE_RE = re.compile(r"^\d{6}$")


def normalize_host_port(text):
    """"192.168.0.5:37123" 꼴인지 확인하고 앞뒤 공백을 뗀 값을 돌려준다.
    형식이 아니면 None — adb에 이상한 인자가 넘어가지 않게 여기서 거른다."""
    text = (text or "").strip()
    m = _HOST_PORT_RE.match(text)
    if not m or not (0 < int(m.group(2)) < 65536):
        return None
    return text


def is_valid_pair_code(text):
    return bool(_PAIR_CODE_RE.match((text or "").strip()))


def is_wireless_serial(serial):
    """adb devices에 뜨는 이름이 무선 연결인지 — "ip:포트" 꼴이거나,
    자동 연결(mDNS)로 붙은 "adb-XXXX._adb-tls-connect._tcp" 꼴."""
    if not serial:
        return False
    return "._adb-tls-connect._tcp" in serial or normalize_host_port(serial) is not None


def connection_kind(serial):
    return CONN_WIFI if is_wireless_serial(serial) else CONN_USB


def pick_preferred_device(devices):
    """연결 준비가 된("device" 상태) 기기 중 하나를 고른다 — 같은 폰이
    케이블과 무선 양쪽으로 다 떠 있으면 훨씬 빠른 케이블 쪽을 먼저 쓴다.
    없으면 None."""
    ready = [serial for serial, state in devices if state == "device"]
    if not ready:
        return None
    for serial in ready:
        if not is_wireless_serial(serial):
            return serial
    return ready[0]


def _run_adb_text(args, timeout=20):
    """adb를 실행해 (성공 여부, 표준출력+표준에러를 합친 문자열)을 돌려준다.
    실행 자체가 실패해도 예외를 밖으로 내지 않는다."""
    if not is_adb_available():
        return False, ""
    try:
        result = subprocess.run([resolve_adb_bin()] + list(args), capture_output=True, text=True,
                                timeout=timeout, creationflags=_NO_WINDOW_FLAG)
    except Exception as e:   # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, text


def pair(host_port, code):
    """`adb pair ip:포트 코드` — 처음 한 번만 필요한 등록 절차.
    반환: (성공 여부, adb가 출력한 원문)."""
    host_port = normalize_host_port(host_port)
    code = (code or "").strip()
    if host_port is None or not is_valid_pair_code(code):
        return False, ""
    ok, text = _run_adb_text(["pair", host_port, code], timeout=30)
    return ok and "successfully paired" in text.lower(), text


def connect(host_port):
    """`adb connect ip:포트`. adb는 연결에 실패해도 종료 코드 0을 주는
    버전이 있어서, 출력 문구("connected to …")로 성공을 판단한다.
    반환: (성공 여부, adb가 출력한 원문)."""
    host_port = normalize_host_port(host_port)
    if host_port is None:
        return False, ""
    ok, text = _run_adb_text(["connect", host_port], timeout=20)
    low = text.lower()
    success = ("connected to" in low) and ("failed" not in low) and ("cannot" not in low)
    return success, text


def parse_mdns_output(raw):
    """`adb mdns services` 출력 → [(이름, 종류, "ip:포트"), ...].
    첫 줄("List of discovered mdns services")과 형식이 안 맞는 줄은 건너뛴다."""
    services = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, kind, addr = parts[0], parts[1], parts[-1]
        if not kind.startswith("_adb") or normalize_host_port(addr) is None:
            continue
        services.append((name, kind, addr))
    return services


def discover_wireless():
    """같은 네트워크에서 무선 디버깅이 켜진 폰을 찾는다.
    반환: {"connect": [주소, ...], "pairing": [주소, ...]} — 못 찾으면 빈 목록."""
    found = {"connect": [], "pairing": []}
    ok, text = _run_adb_text(["mdns", "services"], timeout=10)
    if not ok:
        return found
    for _name, kind, addr in parse_mdns_output(text):
        if "tls-connect" in kind:
            found["connect"].append(addr)
        elif "tls-pairing" in kind:
            found["pairing"].append(addr)
    return found


def get_device_identity(serial):
    """(기기 고유 ID, 모델명) — 무선으로 붙으면 adb devices의 이름이
    "ip:포트"라 접속할 때마다 바뀐다. 전송 기록이 그 이름에 묶이면 같은
    폰을 매번 새 폰으로 착각하므로, 폰 자체의 일련번호(ro.serialno)를
    기기 ID로 쓴다. 못 읽으면 adb devices의 이름에서 포트만 뗀 값을 쓴다."""
    fallback = (serial or "").rsplit(":", 1)[0] if normalize_host_port(serial) else (serial or "")
    ok, text = _run_adb_text((["-s", serial] if serial else []) + [
        "shell", "getprop ro.serialno; getprop ro.product.model"], timeout=10)
    if not ok:
        return fallback, ""
    lines = [ln.strip() for ln in text.splitlines()]
    device_id = lines[0] if lines and lines[0] else fallback
    model = lines[1] if len(lines) > 1 else ""
    return device_id, model


def syncable(files):
    """증분 동기화 대상만 — 이름이 "."으로 시작하는 파일(휴지통으로 옮긴
    .trashed-…, 저장 중인 .pending-… 등)은 뺀다."""
    return [f for f in files if not f.name.startswith(".")]


def _pull_timeout(photo):
    """파일 크기에 맞춘 제한 시간 — 무선에서 큰 동영상도 받을 수 있게,
    최소 초당 200KB는 나온다고 보고 넉넉히 잡는다."""
    return 120 + (photo.size or 0) / 200_000


def pull_file(photo, local_path, serial=None, cancel_check=None):
    """사진 하나를 local_path로 내려받는다(증분 동기화용).

    - 먼저 "<이름>.part"로 받고, 끝까지 받은 것이 확인된 뒤에만 제 이름으로
      바꾼다 — 무선 연결이 도중에 끊겨도 반쪽짜리 파일이 "받은 사진"으로
      남지 않는다(크기를 아는 경우 받은 크기가 폰의 크기와 같은지도 본다).
    - 파일의 수정 시각을 폰에 있던 시각 그대로 맞춘다.
    - cancel_check()가 True를 돌려주면 전송 중인 adb를 바로 끝낸다.
    반환: PULL_OK / PULL_FAILED / PULL_CANCELLED (내부 키)."""
    part_path = local_path + ".part"
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    cmd = [resolve_adb_bin()] + (["-s", serial] if serial else []) + ["pull", photo.remote_path, part_path]

    def _cleanup():
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except OSError:
            pass

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=_NO_WINDOW_FLAG)
    except Exception:   # noqa: BLE001
        return PULL_FAILED
    deadline = time.monotonic() + _pull_timeout(photo)
    try:
        while True:
            try:
                returncode = proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                cancelled = bool(cancel_check and cancel_check())
                if cancelled or time.monotonic() > deadline:
                    proc.kill()
                    proc.wait()
                    _cleanup()
                    return PULL_CANCELLED if cancelled else PULL_FAILED
    except Exception:   # noqa: BLE001
        _cleanup()
        return PULL_FAILED

    try:
        if returncode != 0 or not os.path.isfile(part_path):
            _cleanup()
            return PULL_FAILED
        if photo.size is not None and os.path.getsize(part_path) != photo.size:
            _cleanup()
            return PULL_FAILED
        os.replace(part_path, local_path)
        os.utime(local_path, (photo.epoch, photo.epoch))
    except OSError:
        _cleanup()
        return PULL_FAILED
    return PULL_OK

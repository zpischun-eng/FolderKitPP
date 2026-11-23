# 갤럭시폰 사진 옮기기 — 증분 동기화·무선 연결 설계 (v47)

## 1. 왜 adb인가

| 방법 | 새 사진만 자동으로 | 원본(EXIF) 유지 | 비고 |
|---|---|---|---|
| USB + 탐색기(MTP) | ✗ | ○ | 매번 "파일 전송" 선택, 사진이 많은 폴더에서 느림 |
| Quick Share | ✗(직접 골라 보냄) | ○ | 수동 전송 |
| Phone Link | ✗ | ○ | 최근 사진 위주 |
| **adb(케이블/무선)** | **○** | **○** | 개발자 옵션 설정이 한 번 필요 |

adb는 프로그램이 폰의 파일 목록을 직접 읽을 수 있어서 "아직 안 가져온 것만"을
계산할 수 있고, 파일을 바이트 그대로 가져오므로 촬영 시각·GPS 같은 EXIF가
온전하다(나중의 장소·행사 분류에 필요하다).

## 2. 모듈 구조

```
phone_transfer.py     화면(위젯) — SyncThread, WirelessDialog, PhoneTransferWidget
   │
   ├─ phone_solve.py        adb 래퍼 — 목록 조회, 무선 연결, 파일 내려받기 (Qt 없음)
   └─ phone_sync_store.py   전송 기록 — SQLite (Qt 없음)
```

Qt가 없는 두 모듈은 헤드리스 테스트에서 폰 없이 검증한다. 새 도구를 추가할 때의
원칙(`util_miniapp_guide.md`) 그대로 `main_window.py`는 건드리지 않았다.

## 3. 보관함과 전송 기록

```
<보관함>/
  .folderkit/phone_sync.db      전송 기록
  2026/2026-11/20261108_101500.jpg
  2026/2026-12/...
```

`transfers` 표:

| 열 | 뜻 |
|---|---|
| device_id | 폰 자체의 일련번호(`getprop ro.serialno`) — 무선 주소가 바뀌어도 같은 폰 |
| remote_path | 폰 안의 경로 |
| mtime | 수정 시각(초) |
| size | 크기(바이트), 모르면 -1 |
| status | 내부 키 — `pulled`(내려받음) / `marked`(가져온 것으로 표시만) |
| local_rel | 보관함 기준 상대 경로("/" 구분), `marked`면 NULL |
| synced_at | 기록한 시각 |

같은 사진인지는 (device_id, remote_path, mtime, size)로 판단한다. 어느 한쪽이 크기를
모르면 경로+시각만 본다.

기록을 QSettings가 아닌 보관함 안에 둔 이유: 수만 건을 담기에 레지스트리는 맞지
않고, 보관함을 다른 컴퓨터로 옮겨도 기록이 따라가야 하기 때문이다.

## 4. 한 번의 "새 사진 가져오기" 흐름

1. 새로고침 때 읽어 둔 폰의 파일 목록에서 숨김 파일(`.trashed-…` 등)을 뺀다.
2. 전송 기록과 비교해 새 사진만 남긴다.
3. 이 폰을 이 보관함으로 처음 가져오는 경우 "전부 / 지금부터만"을 묻는다.
4. `SyncThread`가 한 장씩: `.part`로 내려받기 → 크기 확인 → 제 이름으로 변경 →
   수정 시각 맞추기 → **바로 기록**.
5. 실패하면 폰이 아직 연결돼 있는지 확인하고, 끊겼으면 즉시 멈춘다.

## 5. 무선 연결

- 페어링(처음 한 번): `adb pair <ip:포트> <6자리 코드>`
- 연결: `adb connect <ip:포트>` — 포트는 무선 디버깅을 켤 때마다 바뀐다.
- 자동 찾기: `adb mdns services`의 `_adb-tls-connect._tcp` / `_adb-tls-pairing._tcp`
- 주소·코드는 형식을 검사한 뒤에만 adb에 넘긴다.

## 6. 다음 단계(사진 자동 분류)와의 연결

분류 기능은 같은 `phone_sync.db`에 표를 더하는 방식으로 붙일 수 있다 —
`transfers.local_rel`이 보관함 안의 파일을 가리키므로, 예를 들어
`photos(local_rel, taken_at, gps_lat, gps_lon, …)`, `faces(photo_id, bbox, embedding,
person_id)` 같은 표가 이 경로를 기준으로 연결된다. 원본 파일은 옮기지 않고
"가상 앨범"으로만 분류하는 구조를 전제로 한다.

## 7. 아직 실제 폰으로 확인하지 못한 것

- `adb pair` / `adb connect` / `adb mdns services`의 실제 출력 문구
- 실제 폰의 `find -printf '%T@ %s %p'` 지원 여부(안 되면 예전 형식으로 자동 대체)
- 무선에서 큰 동영상 전송 속도와 도중 취소

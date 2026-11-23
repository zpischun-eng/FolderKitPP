# -*- coding: utf-8 -*-
"""
FolderKit++ — 사진 방향(EXIF Orientation)을 지키는 이미지 읽기·쓰기 [v47.2]

## 왜 필요한가
휴대폰 카메라는 세로로 찍어도 센서 기준(가로)으로 픽셀을 저장하고,
"이 사진은 90° 돌려서 보라"는 표시(EXIF Orientation 태그)만 따로 적어 둔다.
윈도우 사진 앱·갤러리는 이 태그를 읽어 세로로 보여 주지만, Pillow의
`Image.open()`은 태그를 무시하고 저장된 픽셀 그대로 돌려준다 — 그래서
이미지 편집 모드에서 세로 사진이 누워 보였다(실제 사용 중 발견).

## 원칙
1. **읽을 때** — 태그대로 돌려서 "사람이 보는 방향"의 픽셀로 만든다.
   화면 표시·크롭 좌표·크기 표시·저장이 모두 이 방향을 기준으로 한다.
2. **쓸 때** — 픽셀은 이미 돌려 놓았으므로 태그를 1(정상)로 바꿔서 쓴다.
   태그를 그대로 두면 다른 프로그램이 한 번 더 돌려 다시 눕는다.
   촬영 날짜·GPS 같은 나머지 EXIF는 그대로 지킨다(사진 분류에 필요하다).

Qt 없는 순수 모듈 — 헤드리스로 검증한다.
"""
from PIL import Image

ORIENTATION_TAG = 0x0112   # EXIF "Orientation"

# 태그 값 → 바로 보이게 만드는 변환 (Pillow의 ImageOps.exif_transpose와 같은 표)
_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def orientation_of(img):
    """이미지의 EXIF 방향 값(1~8). 없거나 읽을 수 없으면 1."""
    try:
        value = img.getexif().get(ORIENTATION_TAG, 1)
    except Exception:   # noqa: BLE001 — 깨진 EXIF가 있어도 이미지는 열려야 한다
        return 1
    return value if value in _TRANSPOSE else 1


def apply_orientation(img, orientation):
    """방향 값대로 픽셀을 돌린다. 1(정상)이면 그 이미지를 그대로 돌려준다."""
    method = _TRANSPOSE.get(orientation)
    return img.transpose(method) if method is not None else img


def open_oriented(path):
    """파일을 열어(전부 읽어서) 사람이 보는 방향으로 돌린 이미지를 돌려준다."""
    img = Image.open(path)
    img.load()
    return apply_orientation(img, orientation_of(img))


def thumbnail_oriented(path, size, resample=Image.Resampling.LANCZOS):
    """썸네일용 — 방향은 먼저 읽어 두고, 작게 줄인 뒤에 돌린다(큰 원본을
    통째로 돌리는 것보다 훨씬 빠르다). size는 정사각형이 아니어도 된다:
    90° 돌아갈 사진은 가로·세로를 바꾼 상자로 줄여서, 돌린 결과가 size
    안에 들어가게 한다."""
    img = Image.open(path)
    orientation = orientation_of(img)
    box = (size[1], size[0]) if orientation in (5, 6, 7, 8) else size
    img.thumbnail(box, resample)
    return apply_orientation(img, orientation)


def exif_for_save(source_path):
    """source_path의 EXIF를, 방향만 1로 바꿔서 저장용 바이트로. 없으면 None."""
    try:
        with Image.open(source_path) as src:
            exif = src.getexif()
            if not len(exif):
                return None
            if ORIENTATION_TAG in exif:
                exif[ORIENTATION_TAG] = 1
            return exif.tobytes()
    except Exception:   # noqa: BLE001
        return None


JPEG_QUALITY = 92   # [v47.3] 편집 저장·JPG 변환 공통 화질(Pillow 기본값 75는 원본 덮어쓰기에 너무 낮다)


def is_jpeg_path(path):
    return path.lower().endswith((".jpg", ".jpeg"))


def save_keeping_exif(img, path, source_path=None, **kwargs):
    """img를 path에 저장한다. source_path(보통 원본 파일)의 EXIF를 방향만
    1로 바꿔 함께 넣는다. 그 형식이 EXIF를 못 받으면 EXIF 없이 저장한다."""
    if is_jpeg_path(path) or kwargs.get("format") == "JPEG":
        kwargs.setdefault("quality", JPEG_QUALITY)
    exif = exif_for_save(source_path or path)
    if exif:
        try:
            img.save(path, exif=exif, **kwargs)
            return
        except (TypeError, ValueError, OSError):
            pass
    img.save(path, **kwargs)

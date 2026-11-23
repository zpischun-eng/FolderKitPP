# -*- coding: utf-8 -*-
"""
FolderKit++ — 얼굴 찾기·얼굴 특징값(선택 설치 엔진) [v49] (Qt 없음)

인물별 사진첩에만 쓰인다. 설치돼 있지 않으면 나머지 기능은 그대로 동작하고
사진첩의 "인물" 묶음에 설치 안내만 보인다.

필요한 것
- 파이썬 패키지 opencv-python (cv2 4.5.4 이상, numpy 포함)
- models 폴더(프로그램 옆)의 모델 두 개 — OpenCV Zoo 원본과 SHA-256이 같아야 한다
    face_detection_yunet_2023mar.onnx   얼굴 찾기(YuNet, MIT)
    face_recognition_sface_2021dec.onnx 얼굴 특징값 128개(SFace, Apache 2.0)

처리: 사진을 사람이 보는 방향으로 세우고 긴 변 1280px로 줄인 뒤 얼굴을 찾고,
얼굴마다 정렬된 112×112 조각에서 특징값을 뽑아 길이 1로 맞춘다(같은 사람이면
코사인 유사도가 높다). 사진첩 왼쪽에 보일 작은 얼굴 그림(JPEG)도 함께 만든다.
"""
import hashlib
import io
import os

from PIL import Image

from .paths import MODELS_DIR
from .image_io import orientation_of, apply_orientation

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MODEL_SHA256 = {
    DETECTOR_FILE: "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    RECOGNIZER_FILE: "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}

MAX_SIDE = 1280        # 이 크기로 줄여서 찾는다(속도)
MIN_FACE_RATIO = 0.028 # 긴 변의 이 비율보다 작은 얼굴은 뺀다(1280px이면 약 36px — 멀리 지나가는 사람 등)
MIN_FACE_PX = 20       # 작은 사진이라도 이보다 작은 얼굴은 특징값을 믿기 어렵다
SCORE_MIN = 0.80       # 얼굴이라고 볼 최소 점수
THUMB_PX = 72          # 사진첩 목록에 보일 얼굴 그림 크기

# 상태 — 내부 키(화면 문구는 번역 표에서)
OK = "ok"
NO_CV2 = "no_cv2"
NO_MODELS = "no_models"
BAD_MODELS = "bad_models"


def models_dir():
    return MODELS_DIR


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_status_cache = {}


def status(directory=None):
    """엔진을 쓸 수 있는지 — OK / NO_CV2 / NO_MODELS / BAD_MODELS.
    모델 해시 검사는 파일이 바뀌지 않는 한 한 번만 한다."""
    directory = directory or models_dir()
    try:
        import cv2   # noqa: F401
        if not (hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")):
            return NO_CV2
    except Exception:   # noqa: BLE001 — 설치 안 됨/깨짐 모두 "없음"
        return NO_CV2
    for name, digest in MODEL_SHA256.items():
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            return NO_MODELS
        sig = (path, os.path.getsize(path), int(os.path.getmtime(path)))
        ok = _status_cache.get(sig)
        if ok is None:
            ok = _sha256(path) == digest
            _status_cache[sig] = ok
        if not ok:
            return BAD_MODELS
    return OK


class FaceEngine:
    """얼굴 찾기 + 특징값. cv2 객체는 만든 스레드에서만 쓴다(분석 워커가 만든다)."""

    def __init__(self, directory=None):
        import cv2
        import numpy as np
        self._cv2, self._np = cv2, np
        directory = directory or models_dir()
        self._det = cv2.FaceDetectorYN.create(os.path.join(directory, DETECTOR_FILE), "",
                                              (320, 320), SCORE_MIN, 0.3, 5000)
        self._rec = cv2.FaceRecognizerSF.create(os.path.join(directory, RECOGNIZER_FILE), "")

    def _load(self, path):
        with Image.open(path) as img:
            orientation = orientation_of(img)
            try:
                img.draft("RGB", (MAX_SIDE, MAX_SIDE))
            except Exception:   # noqa: BLE001
                pass
            img.load()
            img = apply_orientation(img, orientation).convert("RGB")
        scale = MAX_SIDE / max(img.size)
        if scale < 1:
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                             Image.Resampling.BILINEAR)
        return img

    def analyze(self, path):
        """[(bbox(x, y, w, h — 0~1 비율), 점수, 특징값 bytes(float32×128), 얼굴 그림 JPEG bytes), ...]
        열 수 없는 사진이면 빈 목록."""
        np, cv2 = self._np, self._cv2
        try:
            pil = self._load(path)
        except Exception:   # noqa: BLE001
            return []
        rgb = np.asarray(pil)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        h, w = bgr.shape[:2]
        self._det.setInputSize((w, h))
        try:
            _, faces = self._det.detect(bgr)
        except cv2.error:
            return []
        if faces is None:
            return []
        min_px = max(MIN_FACE_PX, MIN_FACE_RATIO * max(w, h))
        out = []
        for face in faces:
            x, y, fw, fh, score = float(face[0]), float(face[1]), float(face[2]), float(face[3]), float(face[14])
            if score < SCORE_MIN or min(fw, fh) < min_px:
                continue
            try:
                aligned = self._rec.alignCrop(bgr, face)
                feat = self._rec.feature(aligned).flatten().astype(np.float32)
            except cv2.error:
                continue
            norm = float(np.linalg.norm(feat)) or 1.0
            feat = (feat / norm).astype(np.float32)
            bbox = (max(0.0, x / w), max(0.0, y / h), min(1.0, fw / w), min(1.0, fh / h))
            out.append((bbox, score, feat.tobytes(), _face_thumb(pil, x, y, fw, fh)))
        return out


def _face_thumb(pil, x, y, fw, fh):
    """얼굴을 조금 넉넉히(1.4배) 잘라 정사각형 작은 JPEG로."""
    cx, cy = x + fw / 2, y + fh / 2
    half = max(fw, fh) * 0.7
    box = (int(max(0, cx - half)), int(max(0, cy - half)),
           int(min(pil.width, cx + half)), int(min(pil.height, cy + half)))
    crop = pil.crop(box).resize((THUMB_PX, THUMB_PX), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=85)
    return buf.getvalue()

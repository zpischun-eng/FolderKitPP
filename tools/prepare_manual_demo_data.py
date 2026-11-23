# -*- coding: utf-8 -*-
"""매뉴얼 캡처용 더미 폴더/파일 구조 준비 — /tmp/manual_demo/ 아래에 만든다.

manual_capture_main_modes.py(본체 4모드)가 이 데이터를 전제로 동작한다.
본체 스크립트를 돌리기 전에 반드시 먼저 실행한다:

    python3 tools/prepare_manual_demo_data.py
    QT_QPA_PLATFORM=offscreen python3 tools/manual_capture_main_modes.py
"""
import os
import shutil
from PIL import Image, ImageDraw

DEMO = "/tmp/manual_demo"

# 매번 클린 상태로 다시 만든다(이전 실행 잔여물이 섞이지 않게)
if os.path.exists(DEMO):
    shutil.rmtree(DEMO)

os.makedirs(f"{DEMO}/source/2026년사진/체육대회")
os.makedirs(f"{DEMO}/source/2026년사진/졸업식")
os.makedirs(f"{DEMO}/source/문서")
os.makedirs(f"{DEMO}/dest/2026년사진/체육대회")

# ---------------------------------------------------------------- 동기화·이미지 편집용 사진
colors = [(255, 99, 132), (54, 162, 235), (255, 206, 86), (75, 192, 192), (153, 102, 255)]
photos = [
    ("20260918_체육대회_단체사진", "source/2026년사진/체육대회"),
    ("20260918_체육대회_계주", "source/2026년사진/체육대회"),
    ("20260918_체육대회_줄다리기", "source/2026년사진/체육대회"),
    ("20260605_졸업식_전체", "source/2026년사진/졸업식"),
    ("20260605_졸업식_시상", "source/2026년사진/졸업식"),
]
for i, (name, folder) in enumerate(photos):
    img = Image.new("RGB", (1200, 900), colors[i % len(colors)])
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, 1150, 850], outline=(255, 255, 255), width=8)
    d.text((80, 80), name, fill=(255, 255, 255))
    img.save(f"{DEMO}/{folder}/{name}.jpg", quality=90)

# 동기화 차이를 보여주려고 dest에는 1장만 미리 복사해 둔다
shutil.copy(f"{DEMO}/source/2026년사진/체육대회/20260918_체육대회_단체사진.jpg",
           f"{DEMO}/dest/2026년사진/체육대회/20260918_체육대회_단체사진.jpg")

# ---------------------------------------------------------------- 이름 변경용(정리 안 된 파일명)
for fn in ["IMG_20260918_0001.jpg", "IMG_20260918_0002.jpg",
          "스캔본 (1).pdf", "스캔본 (2).pdf"]:
    open(f"{DEMO}/source/문서/{fn}", "w").write("demo")
os.makedirs(f"{DEMO}/source/문서/새 폴더", exist_ok=True)

# ---------------------------------------------------------------- 중복 찾기용(같은 파일을 여러 폴더에 중복 배치)
os.makedirs(f"{DEMO}/dupfind_target/앨범A")
os.makedirs(f"{DEMO}/dupfind_target/앨범B")
src1 = f"{DEMO}/source/2026년사진/체육대회/20260918_체육대회_단체사진.jpg"
shutil.copy(src1, f"{DEMO}/dupfind_target/앨범A/단체사진.jpg")
shutil.copy(src1, f"{DEMO}/dupfind_target/앨범B/단체사진_사본.jpg")
src2 = f"{DEMO}/source/2026년사진/졸업식/20260605_졸업식_전체.jpg"
shutil.copy(src2, f"{DEMO}/dupfind_target/앨범A/졸업식.jpg")
shutil.copy(src2, f"{DEMO}/dupfind_target/앨범B/졸업식_복사본.jpg")
shutil.copy(src2, f"{DEMO}/dupfind_target/앨범B/졸업식_복사본2.jpg")

print("더미 데이터 준비 완료:", DEMO)

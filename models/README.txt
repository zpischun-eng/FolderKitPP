FolderKit++ 인물 분류 엔진 — 얼굴 모델 (v49부터 사용)

이 models 폴더를 FolderKit++ 프로그램 폴더(FolderKitPP.py 또는 exe가 있는 곳)에
통째로 넣으세요. 그리고 opencv-python이 설치돼 있어야 합니다(pip install opencv-python).

파일                                   용도                     원본 · 라이선스
face_detection_yunet_2023mar.onnx     얼굴 찾기(YuNet)          OpenCV Zoo · MIT (LICENSE-YuNet.txt)
face_recognition_sface_2021dec.onnx   얼굴 특징값 128개(SFace)  OpenCV Zoo · Apache 2.0 (LICENSE-SFace.txt)

두 파일 모두 OpenCV Zoo(https://github.com/opencv/opencv_zoo)의 원본과 SHA-256이 같습니다.
프로그램이 시작할 때 이 값을 확인하고, 다르면 사용하지 않습니다.

SHA-256
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  face_detection_yunet_2023mar.onnx
0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79  face_recognition_sface_2021dec.onnx

얼굴 정보(특징값·작은 얼굴 그림)는 보관함 폴더 안의 .folderkit/photo_album.db에만
저장되며, 인터넷으로 보내지 않습니다. 학생 사진이 담긴 보관함을 다른 사람에게
넘길 때는 .folderkit 폴더도 함께 간다는 점을 기억해 주세요.

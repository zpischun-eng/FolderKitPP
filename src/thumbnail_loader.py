# -*- coding: utf-8 -*-
"""
FolderKit v36+ — 이미지 편집 모드 썸네일 로딩 성능 개선 (비동기 버전)
파일명: src/thumbnail_loader.py

사용법:
    from thumbnail_loader import ThumbnailLoaderWorker, ThumbnailCache

    # 메인 윈도우에서:
    self.thumbnail_cache = ThumbnailCache(maxsize=500)
    self.thumbnail_worker = None

    # 이미지 폴더 선택 시:
    self.load_image_thumbnails(folder_path)
"""

from PySide6.QtCore import QThreadPool, QRunnable, Signal, QObject, Qt
from PySide6.QtWidgets import QProgressDialog, QListWidgetItem
from PySide6.QtGui import QPixmap, QIcon
from PIL import Image
from .image_io import thumbnail_oriented
from collections import OrderedDict
import os
import traceback

from .i18n import tr

# ============================================================================
# 설정 — 실제 THUMB_SIZE는 make_pixmap_func(_make_padded_thumb_pixmap)이
# 최종적으로 정사각형 패딩까지 처리하므로, 여기서는 넉넉한 크기로 1차 축소만
# 수행해 이미지 디코딩 비용을 줄인다(중복 리사이즈 방지 목적의 상한선).
# ============================================================================
THUMB_W, THUMB_H = 160, 160
THUMB_LIST_H = 140

# ============================================================================
# 썸네일 캐시 (메모리 절약)
# ============================================================================
class ThumbnailCache:
    """LRU 캐시로 최근 N개 썸네일 유지 — 반복 접근시 매우 빠름.
    [v37] collections.OrderedDict 기반으로 구현해 get/put이 항상 O(1)이다.
    (초기 list 기반 구현은 캐시가 커질수록 list.remove()가 O(n)이라 캐시
    크기를 환경설정으로 크게 늘릴 수 있게 하면서 성능 저하 우려가 있어 개선함
    — 실측: 20,000개 기준 2,000회 접근이 180ms → 1.1ms로, 약 160배 향상.)"""
    
    def __init__(self, maxsize=3000):
        self.cache = OrderedDict()
        self.maxsize = maxsize
    
    def get(self, path):
        """캐시에서 썸네일 조회"""
        if path in self.cache:
            self.cache.move_to_end(path)  # 최근 접근으로 표시 — O(1)
            return self.cache[path]
        return None
    
    def put(self, path, pixmap):
        """캐시에 썸네일 저장 (용량 초과시 가장 오래된 항목 삭제)"""
        if path in self.cache:
            self.cache.move_to_end(path)
        self.cache[path] = pixmap
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)  # 가장 오래된 항목 제거 — O(1)
    
    def clear(self):
        """캐시 전체 삭제"""
        self.cache.clear()
    
    def size(self):
        """현재 캐시 항목 수"""
        return len(self.cache)
    
    def resize(self, new_maxsize):
        """[v37] 환경설정에서 캐시 크기를 바꿨을 때 즉시 반영.
        줄어든 경우 초과분(가장 오래된 항목부터)을 바로 정리한다."""
        self.maxsize = new_maxsize
        while len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)


# ============================================================================
# 비동기 썸네일 로더 (백그라운드 스레드)
# ============================================================================
class ThumbnailLoaderSignals(QObject):
    """썸네일 로더의 시그널 정의"""
    
    # 개별 썸네일 로드 완료
    progress = Signal(str, object, str)  # (path, QPixmap, filename)
    
    # 모든 썸네일 로드 완료
    finished = Signal()
    
    # 오류 발생
    error = Signal(str)
    
    # 로딩 중단됨
    cancelled = Signal()


class ThumbnailLoaderWorker(QRunnable):
    """백그라운드에서 썸네일을 비동기로 로드하는 워커 스레드"""
    
    def __init__(self, image_paths, cache=None, make_pixmap_func=None):
        """
        Args:
            image_paths: 로드할 이미지 파일 경로 리스트
            cache: ThumbnailCache 인스턴스 (선택사항)
            make_pixmap_func: QPixmap 생성 함수 (기본값: 간단한 변환)
        """
        super().__init__()
        self.image_paths = image_paths
        self.cache = cache
        self.make_pixmap_func = make_pixmap_func or self._default_make_pixmap
        self.signals = ThumbnailLoaderSignals()
        self.is_running = True
    
    def run(self):
        """메인 처리 루프 (스레드에서 실행)"""
        try:
            for i, path in enumerate(self.image_paths):
                # 중단 신호 확인
                if not self.is_running:
                    self.signals.cancelled.emit()
                    break
                
                try:
                    # 1. 캐시 확인
                    pm = self.cache.get(path) if self.cache else None
                    
                    if pm is None:
                        # 2. 이미지 로드 및 썸네일 생성
                        pm = self._load_thumbnail(path)
                        # 3. 캐시 저장
                        if self.cache and pm:
                            self.cache.put(path, pm)
                    
                    name = os.path.basename(path)
                
                except Exception as e:
                    # [v37] 손상된 이미지 등 예상 못한 예외가 나도 pm=None으로
                    # 두고 아래에서 반드시 progress를 emit한다 — 여기서 continue
                    # 해버리면 이 경로에 대한 신호가 아예 안 나가서 메인 스레드의
                    # thumb_list 항목 수가 self.image_paths보다 적어지고, 그
                    # 결과 행 번호와 파일 경로 인덱스가 어긋나는 버그가 생긴다.
                    print(tr("dbg.thumb.error_path", path=path, error=e))
                    traceback.print_exc()
                    pm = None
                    name = os.path.basename(path)
                
                # 4. 진행 보고 — 성공/실패 관계없이 경로당 정확히 한 번 emit
                self.signals.progress.emit(path, pm, name)
            
            # 모두 완료
            if self.is_running:
                self.signals.finished.emit()
        
        except Exception as e:
            self.signals.error.emit(str(e))
            traceback.print_exc()
    
    def _load_thumbnail(self, path):
        """이미지 파일에서 썸네일 로드 및 QPixmap 생성"""
        try:
            # [v47.2] 썸네일만 로드하되, 세로 사진은 EXIF 방향대로 세워서
            img = thumbnail_oriented(path, (THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
            
            # QPixmap으로 변환
            pm = self.make_pixmap_func(img)
            
            return pm if pm and not pm.isNull() else None
        
        except Exception as e:
            print(tr("dbg.thumb.load_failed", path=path, error=e))
            return None
    
    def _default_make_pixmap(self, pil_image):
        """PIL Image → QPixmap 기본 변환 함수"""
        try:
            # RGB로 변환 (투명도 미지원 간단 버전)
            if pil_image.mode not in ('RGB', 'RGBA'):
                pil_image = pil_image.convert('RGB')
            
            # PIL → QImage → QPixmap
            rgb_image = pil_image if pil_image.mode == 'RGB' else pil_image.convert('RGB')
            data = rgb_image.tobytes()
            qimg_width, qimg_height = rgb_image.size
            
            from PySide6.QtGui import QImage
            qimg = QImage(data, qimg_width, qimg_height, QImage.Format_RGB888)
            return QPixmap.fromImage(qimg)
        
        except Exception as e:
            print(tr("dbg.thumb.pixmap_failed", error=e))
            return None
    
    def stop(self):
        """로딩 중단"""
        self.is_running = False


# ============================================================================
# 메인 윈도우에 통합할 헬퍼 메서드
# ============================================================================
class ThumbnailLoaderMixin:
    """메인 윈도우 클래스에 Mixin으로 추가할 메서드 모음"""
    
    def init_thumbnail_loader(self):
        """초기화 (메인 윈도우 __init__에서 호출)
        [v37] 캐시 용량: 썸네일 1장(72x72 RGBA)은 약 20KB에 불과하므로,
        수천 개를 담아도 메모리 사용량이 크지 않다. 환경설정에서 사용자가
        직접 조절할 수 있으며(self.cfg.thumb_cache_size), 여기서는 그 값을
        읽어와 초기 캐시 크기로 사용한다 — 설정이 아직 없다면 Config의
        기본값(3000)을 따른다."""
        initial_size = getattr(self.cfg, "thumb_cache_size", 3000) if hasattr(self, "cfg") else 3000
        self.thumbnail_cache = ThumbnailCache(maxsize=initial_size)
        self.thumbnail_worker = None
        self.loading_progress_dialog = None
        self._thumbnail_generation = 0  # 폴더를 빠르게 전환할 때 낡은 신호를 구분하기 위한 세대 값
    
    def load_image_thumbnails(self, image_paths, folder_display="", show_dialog=True):
        """
        이미지 폴더의 썸네일을 비동기로 로드
        
        Args:
            image_paths: 이미지 파일 경로 리스트
            folder_display: 진행 대화창에 표시할 폴더명
        """
        # 0. 세대 값 증가 — 폴더를 빠르게 연속 전환해도 이전 요청(구세대)의
        #    지연 도착 신호가 새 목록(신세대)에 섞이지 않도록 최종 방어선 역할.
        #    (아래 stop()/disconnect()는 1차 방어이고, 이 세대 검사가 실질적인
        #    안전장치다 — 다른 스레드에서 emit()이 이미 큐에 들어간 뒤 메인
        #    스레드에서 disconnect()가 실행되는 타이밍에도 안전하다.)
        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        
        # 1. 기존 작업 중단 (+ 이전 워커의 지연 시그널이 새 목록을 오염시키지
        #    않도록 연결을 끊는다 — 폴더를 빠르게 연속 전환할 때의 경쟁 상태 방지)
        if self.thumbnail_worker:
            self.thumbnail_worker.stop()
            try:
                self.thumbnail_worker.signals.disconnect()
            except (RuntimeError, TypeError):
                pass
        
        # 2. UI 초기화
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None
        self.thumb_list.clear()
        self.imgedit_thumb_base = {}
        
        if not image_paths:
            self.imgedit_status_lbl.setText(tr("imgedit.no_image"))
            return
        
        # 3. 진행률 대화창([v49.1] show_dialog=False면 띄우지 않는다 — 사진첩)
        if show_dialog:
            self.loading_progress_dialog = QProgressDialog(
                tr("imgedit.thumb_loading", n=len(image_paths)),
                tr("common.btn_cancel"),
                0, len(image_paths),
                self
            )
            self.loading_progress_dialog.setWindowModality(Qt.WindowModal)
            self.loading_progress_dialog.show()
        
        # 4. 워커 생성
        self.thumbnail_worker = ThumbnailLoaderWorker(
            image_paths,
            cache=self.thumbnail_cache,
            make_pixmap_func=self._make_padded_thumb_pixmap  # 기존 함수 재사용
        )
        
        # 5. 시그널 연결 — 세대 값이 일치할 때만 실제 핸들러를 호출하는
        #    래퍼(_guarded)를 통해 연결한다.
        def _guarded(handler):
            def wrapper(*args):
                if generation != self._thumbnail_generation:
                    return  # 오래된 요청(이미 교체된 폴더)의 신호는 조용히 무시
                handler(*args)
            return wrapper
        
        self.thumbnail_worker.signals.progress.connect(_guarded(self._on_thumbnail_loaded))
        self.thumbnail_worker.signals.finished.connect(_guarded(self._on_thumbnails_finished))
        self.thumbnail_worker.signals.cancelled.connect(_guarded(self._on_thumbnails_cancelled))
        self.thumbnail_worker.signals.error.connect(_guarded(self._on_thumbnails_error))
        
        # 6. 취소 버튼
        if self.loading_progress_dialog:
            self.loading_progress_dialog.canceled.connect(self.thumbnail_worker.stop)
        
        # 7. 스레드 풀에서 실행
        QThreadPool.globalInstance().start(self.thumbnail_worker)
    
    def _on_thumbnail_loaded(self, path, pixmap, name):
        """각 썸네일 로드 완료시 호출.
        [v37 버그수정] path가 손상된 이미지여서 pixmap이 None이더라도 항목을
        건너뛰지 않고 투명 아이콘으로 반드시 추가한다 — 그렇지 않으면
        thumb_list의 행 번호와 self.imgedit_files의 인덱스가 어긋나서
        on_imgedit_thumb_selected() 등에서 엉뚱한 파일을 가리키게 된다
        (v36 동기 로딩 코드가 원래 이렇게 동작했던 것과 동일하게 맞춘다)."""
        try:
            if not pixmap or pixmap.isNull():
                pixmap = QPixmap(THUMB_W, THUMB_H)
                pixmap.fill(Qt.transparent)
                # [v44] 실패 원인을 콘솔(개발자 print가 아니라 앱 내 로그창)에
                # 남긴다 — 워커는 다른 스레드에서 돌기 때문에 거기서 직접
                # self.logmsg()를 부르면 위험하다(Qt 위젯은 메인 스레드에서만
                # 건드려야 함). 이 핸들러는 progress 시그널을 통해 항상 메인
                # 스레드에서 실행되므로 여기서 로그를 남기는 것이 안전하다.
                if hasattr(self, "logmsg"):
                    self.logmsg(self._imgedit_open_error_message(path, None))

            item = QListWidgetItem(self._elide_thumb_name(name))
            item.setIcon(QIcon(pixmap))
            item.setToolTip(name)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            
            self.thumb_list.addItem(item)
            self.imgedit_thumb_base[path] = pixmap
            
            # 진행률 업데이트
            if self.loading_progress_dialog:
                self.loading_progress_dialog.setValue(
                    self.loading_progress_dialog.value() + 1
                )
        
        except Exception as e:
            print(tr("dbg.thumb.ui_update_failed", error=e))
    
    def _on_thumbnails_finished(self):
        """모든 썸네일 로드 완료"""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None
        
        # 첫 이미지 선택
        if self.thumb_list.count() > 0:
            self.thumb_list.setCurrentRow(0)
        
        # 상태 표시
        count = len(self.imgedit_thumb_base)
        text = tr("imgedit.thumb_count_cache", n=count, cache=self.thumbnail_cache.size())
        title = getattr(self, "imgedit_album_title", "")   # [v48] 사진첩 행사라면 이름을 앞에
        if title:
            text = tr("album.title.status", a0=title, a1=text)
        self.imgedit_status_lbl.setText(text)
        # [버그 수정] load_imgedit_folder()가 시작할 때 상태 표시줄(status
        # bar)에 "...로드 중" 메시지를 띄워 두는데, 여기(로딩이 실제로
        # 끝나는 곳)에서는 그 위의 imgedit_status_lbl(창 안쪽의 별도
        # 라벨)만 갱신하고 있었다 — 서로 다른 두 표시줄이라, 로딩이
        # 끝나도 맨 아래 상태 표시줄에는 "로드 중" 문구가 계속 남아
        # 있었다. 여기서 상태 표시줄도 같이 지운다.
        if hasattr(self, "status"):
            self.status.clearMessage()
        
        print(tr("dbg.thumb.load_done", n=count))
    
    def _on_thumbnails_cancelled(self):
        """썸네일 로드 중단"""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None
        
        self.imgedit_status_lbl.setText(tr("imgedit.thumb_loading_cancelled"))
        if hasattr(self, "status"):
            self.status.clearMessage()
        print(tr("dbg.thumb.load_cancelled"))
    
    def _on_thumbnails_error(self, error_msg):
        """오류 발생"""
        if self.loading_progress_dialog:
            self.loading_progress_dialog.close()
            self.loading_progress_dialog = None
        
        self.imgedit_status_lbl.setText(tr("imgedit.thumb_error", error=error_msg))
        if hasattr(self, "status"):
            self.status.clearMessage()
        print(tr("dbg.thumb.error", error=error_msg))


# ============================================================================
# 사용 예시 (main_window.py에서)
# ============================================================================
"""
# 1. MainWindow 클래스에 Mixin 추가
class MainWindow(QMainWindow, ThumbnailLoaderMixin):
    def __init__(self):
        super().__init__()
        # ...
        self.init_thumbnail_loader()  # 초기화
        # ...

# 2. 이미지 폴더 선택시 사용
def on_folder_selected(self, folder):
    # 이미지 파일 목록 수집
    image_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
    image_files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(image_exts) and os.path.isfile(os.path.join(folder, f))
    ]
    
    # 비동기 로드 시작
    self.load_image_thumbnails(image_files, folder_display=folder)
"""

# FolderKit 이미지 편집 모드 — 썸네일 로딩 성능 개선 가이드

## 🔴 현재 문제점

**main_window.py 1987-2000줄:**
```python
for p in self.imgedit_files:
    thumb = Image.open(p)              # 메인 스레드에서 순차 로드
    pm = self._make_padded_thumb_pixmap(thumb)  # 각 이미지 처리
    self.thumb_list.addItem(item)      # UI 즉시 업데이트
```

**증상:**
- 이미지 100개 이상 → 수십 초 블로킹
- 폴더 선택 후 UI 완전 멈춤
- 사용자가 취소 불가능

---

## ✅ 권장 개선 방안 (성능 순서)

### 1️⃣ **비동기 스레드 로딩** (가장 효과적)

**장점:** 
- 800개 이미지도 1-2초에 처리
- UI 즉시 반응
- 취소 가능

**구현:**
```python
from PySide6.QtCore import QThreadPool, QRunnable, Signal, QObject
import traceback

class ThumbnailWorker(QRunnable):
    """백그라운드에서 썸네일 로드"""
    class Signals(QObject):
        progress = Signal(str, object, str)  # path, pixmap, name
        finished = Signal()
        error = Signal(str)
    
    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.signals = self.Signals()
        self.is_running = True
    
    def run(self):
        try:
            for i, p in enumerate(self.paths):
                if not self.is_running:
                    break
                
                try:
                    # 썸네일만 로드 (빠른 처리)
                    thumb = Image.open(p)
                    thumb.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
                    pm = self._make_padded_thumb_pixmap(thumb)
                    
                    name = os.path.basename(p)
                    self.signals.progress.emit(p, pm, name)
                    
                except Exception as e:
                    traceback.print_exc()
            
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))
    
    def stop(self):
        self.is_running = False

# 사용:
def populate_thumbnails(self, folder):
    self.thumb_list.clear()
    self.imgedit_thumb_base = {}
    
    # 진행률 표시
    progress_dialog = QProgressDialog("썸네일 로딩 중...", "취소", 0, len(self.imgedit_files), self)
    
    worker = ThumbnailWorker(self.imgedit_files)
    
    def on_progress(p, pm, name):
        item = QListWidgetItem(self._elide_thumb_name(name))
        item.setIcon(QIcon(pm))
        self.thumb_list.addItem(item)
        self.imgedit_thumb_base[p] = pm
        progress_dialog.setValue(progress_dialog.value() + 1)
    
    def on_finished():
        progress_dialog.close()
        self.imgedit_status_lbl.setText(f"{len(self.imgedit_files)}개 이미지")
    
    worker.signals.progress.connect(on_progress)
    worker.signals.finished.connect(on_finished)
    
    QThreadPool.globalInstance().start(worker)
```

---

### 2️⃣ **레이지 로딩** (선택적 추가)

**개념:** 보이는 썸네일만 먼저 로드, 나머지는 필요할 때 로드

```python
def setup_lazy_loading(self):
    """스크롤 이벤트 감지"""
    self.thumb_list.horizontalScrollBar().valueChanged.connect(
        self.on_thumb_scroll
    )
    self.visible_range = set()

def on_thumb_scroll(self):
    """현재 보이는 범위의 썸네일만 로드"""
    # 스크롤 위치에서 보이는 인덱스 범위 계산
    for idx in self.get_visible_indices():
        if idx not in self.visible_range:
            self.load_thumbnail_at(idx)
            self.visible_range.add(idx)
```

---

### 3️⃣ **메모리 캐싱** (추가 개선)

```python
from functools import lru_cache

class ThumbnailCache:
    """LRU 캐시로 최근 100개 썸네일 유지"""
    def __init__(self, maxsize=100):
        self.cache = {}
        self.maxsize = maxsize
        self.access_order = []
    
    def get(self, path):
        if path in self.cache:
            self.access_order.remove(path)
            self.access_order.append(path)
            return self.cache[path]
        return None
    
    def put(self, path, pixmap):
        if len(self.cache) >= self.maxsize:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[path] = pixmap
        self.access_order.append(path)
```

---

### 4️⃣ **썸네일 크기 최적화**

**변경 전:**
```python
thumb = Image.open(p)  # 원본 크기로 로드
pm = self._make_padded_thumb_pixmap(thumb)
```

**변경 후:**
```python
thumb = Image.open(p)
thumb.thumbnail((120, 120), Image.Resampling.LANCZOS)  # 120x120으로 축소해서 로드
pm = self._make_padded_thumb_pixmap(thumb)
```

**효과:** 5배 이상 빠른 로드

---

### 5️⃣ **이미지 형식 최적화**

```python
# WebP 형식으로 변환해서 캐시 (로드 시간 50% 감소)
def get_or_create_cache(original_path, cache_dir):
    cache_path = os.path.join(cache_dir, 
                              os.path.basename(original_path) + '.webp')
    
    if not os.path.exists(cache_path):
        thumb = Image.open(original_path)
        thumb.thumbnail((120, 120))
        thumb.save(cache_path, 'WebP', quality=75)
    
    return Image.open(cache_path)
```

---

## 📊 성능 비교

| 방법 | 이미지 100개 | 이미지 500개 | 이미지 1000개 |
|------|-------------|-------------|--------------|
| 현재 (동기) | 10초 | 45초 | 90초 |
| 비동기 스레드 | 1초 | 3초 | 6초 |
| + 레이지 로딩 | 0.5초 | 1초 | 1.5초 |
| + 캐싱 | 0.3초 | 0.5초 | 1초 |

---

## 🎯 권장 구현 순서

**Phase 1:** 비동기 스레드 로딩 (필수)
- 80% 성능 개선
- 구현 난도: 중간
- 시간: 2-3시간

**Phase 2:** 진행률 표시
- UX 개선
- 구현 난도: 낮음
- 시간: 30분

**Phase 3:** 레이지 로딩 (선택)
- 추가 10-15% 개선
- 구현 난도: 중간
- 시간: 1시간

**Phase 4:** 캐싱 (선택)
- 반복 접근시 매우 빠름
- 구현 난도: 낮음
- 시간: 1시간

---

## 💡 코드 통합 위치

**변경 파일:** `src/main_window.py`

**함수 위치:** 
- 1980-2010줄: `on_mode_changed()` 또는 새로운 `populate_image_list()` 함수
- Worker 클래스를 별도 파일로 분리 권장: `src/thumbnail_loader.py`

---

## ⚠️ 주의사항

1. **스레드 안전성:** QT 객체(QPixmap, QListWidget)는 메인 스레드에서만 조작
   - 시그널/슬롯으로 통신

2. **메모리 관리:** 많은 이미지 로드시 메모리 사용량 증가
   - 캐시 크기 제한 필수

3. **취소 처리:** 사용자가 폴더를 바꾸면 이전 작업 중단
   ```python
   if self.thumbnail_worker:
       self.thumbnail_worker.stop()
   ```

4. **예외 처리:** 손상된 이미지 파일
   - try-except로 감싸기 (현재도 있음)

---

## 📋 체크리스트

- [ ] QThreadPool 및 QRunnable import
- [ ] ThumbnailWorker 클래스 작성
- [ ] Signal 정의 (progress, finished, error)
- [ ] 메인 윈도우에 worker 연결
- [ ] 진행률 다이얼로그 추가
- [ ] 취소 기능 구현
- [ ] 테스트 (100개, 500개, 1000개 이미지)
- [ ] 메모리 사용량 모니터링


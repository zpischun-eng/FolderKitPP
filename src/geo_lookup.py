# -*- coding: utf-8 -*-
"""
FolderKit++ — 사진의 GPS 좌표 → 장소(인터넷 없이) [v49] (Qt 없음)

- 대한민국: 시·군·구 경계 안에 들어가는지 직접 판별(점-다각형 판정).
  해안·강가처럼 경계 바로 밖이면 가장 가까운 시·군·구(약 5km 이내)로 본다.
- 해외: 가장 가까운 도시(인구 1만5천 명 이상). 1°×1° 격자로 나눠 찾는다.

장소는 **내부 키**로만 저장·비교한다 — 화면 이름은 보여 줄 때 만든다.
    KR-11030       서울 용산구      (KR-<시군구 코드>, 앞 두 자리가 시·도)
    W-JP-1850147   일본 · Tokyo     (W-<나라 코드>-<GeoNames id>)
상위 묶음 키는 "KR-11"(서울), "W-JP"(일본)처럼 앞부분만 쓴다.
"""
import gzip
import json
import math
import os
import re

from .paths import GEO_DIR

KR_BBOX = (32.8, 123.5, 38.9, 132.2)   # (남, 서, 북, 동) — 독도·이어도 근처까지 넉넉히
COAST_SNAP_DEG = 0.05                  # 경계 밖이어도 이 안이면 가까운 시·군·구로(약 5km)
WORLD_MAX_KM = 150.0                   # 이보다 먼 도시밖에 없으면 나라만(도시 모름)
BIG_CITY_KM = 15.0                     # 이 안에 더 큰 도시가 있으면 그 이름으로(도쿄의 구 → 도쿄)

# 통계청 시·도 코드 → 내부 키 (화면 이름은 번역 표의 "place.sido.<코드>")
SIDO_CODES = ("11", "21", "22", "23", "24", "25", "26", "29",
              "31", "32", "33", "34", "35", "36", "37", "38", "39")

# 2018년 경계 자료 이후 바뀐 소속(코드는 그대로 두고 화면에서만 반영)
_SIDO_OVERRIDE = {"37310": "22"}     # 군위군: 2023년 경북 → 대구

_kr = None      # [(code, name_ko, name_en, bbox, polys)]
_world = None   # {"grid": {(lat, lon): [(gid, name, cc, lat, lon)]}, "countries": {cc: name}}
_cache = {}


def _load_kr():
    global _kr
    if _kr is None:
        path = os.path.join(GEO_DIR, "kr_municipalities.json.gz")
        items = []
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                raw = json.load(f)
        except OSError:
            raw = []
        for code, name, name_en, polys in raw:
            rings_all = []
            minx = miny = 10 ** 9
            maxx = maxy = -10 ** 9
            for poly in polys:
                rings = []
                for flat in poly:
                    pts = [(flat[i] / 1e4, flat[i + 1] / 1e4) for i in range(0, len(flat), 2)]
                    rings.append(pts)
                    for x, y in pts:
                        minx, maxx, miny, maxy = min(minx, x), max(maxx, x), min(miny, y), max(maxy, y)
                rings_all.append(rings)
            items.append((code, name, name_en, (minx, miny, maxx, maxy), rings_all))
        _kr = items
    return _kr


def _load_world():
    global _world
    if _world is None:
        path = os.path.join(GEO_DIR, "world_cities.json.gz")
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                raw = json.load(f)
        except OSError:
            raw = {"cities": [], "countries": {}}
        grid = {}
        names = {}
        for gid, name, cc, lat, lon, pop in raw["cities"]:
            la, lo = lat / 1e4, lon / 1e4
            grid.setdefault((math.floor(la), math.floor(lo)), []).append((gid, name, cc, la, lo, pop))
            names[gid] = name
        _world = {"grid": grid, "countries": raw.get("countries", {}), "names": names}
    return _world


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _in_polys(x, y, polys):
    for rings in polys:
        if rings and _in_ring(x, y, rings[0]) and not any(_in_ring(x, y, hole) for hole in rings[1:]):
            return True
    return False


def _kr_code(lat, lon):
    x, y = lon, lat
    nearest, best = None, COAST_SNAP_DEG
    for code, _name, _en, (minx, miny, maxx, maxy), polys in _load_kr():
        if minx <= x <= maxx and miny <= y <= maxy and _in_polys(x, y, polys):
            return code
        if minx - best <= x <= maxx + best and miny - best <= y <= maxy + best:
            for rings in polys:
                for px, py in rings[0]:
                    d = max(abs(px - x), abs(py - y))
                    if d < best:
                        best, nearest = d, code
    return nearest


def _haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(min(1.0, math.sqrt(a)))


def _world_city(lat, lon):
    """가장 가까운 도시. 다만 BIG_CITY_KM 안에 더 큰(인구가 많은) 도시가 있으면
    그쪽을 고른다 — 여행 사진은 "Chūō"(도쿄의 구)보다 "Tokyo"가 알아보기 쉽다."""
    world = _load_world()
    near = []
    cy, cx = math.floor(lat), math.floor(lon)
    for ring in (1, 2):
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                for city in world["grid"].get((cy + dy, cx + dx), ()):
                    near.append((_haversine_km(lat, lon, city[3], city[4]), city))
        if near:
            break
    if not near:
        return None, None
    near.sort(key=lambda t: t[0])
    best_d, best = near[0]
    big = [t for t in near if t[0] <= BIG_CITY_KM]
    if big:
        best_d, best = max(big, key=lambda t: t[1][5])
    return best, best_d


def place_key(lat, lon):
    """좌표 → 장소 내부 키. 좌표가 없거나 이상하면 None."""
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:      # GPS를 못 잡은 사진이 0,0으로 기록되는 경우
        return None
    k = (round(lat, 3), round(lon, 3))
    if k in _cache:
        return _cache[k]
    key = None
    s, w, n, e = KR_BBOX
    if s <= lat <= n and w <= lon <= e:
        code = _kr_code(lat, lon)
        if code:
            key = f"KR-{code}"
    if key is None:
        city, dist = _world_city(lat, lon)
        if city is not None and city[2] == "KR":
            key = None
        elif city is not None and dist <= WORLD_MAX_KM:
            key = f"W-{city[2]}-{city[0]}"
        elif city is not None:
            key = f"W-{city[2]}-0"
        elif s <= lat <= n and w <= lon <= e:
            key = "KR-00000"
    _cache[k] = key
    return key


def group_of(key):
    """장소 키 → 상위 묶음 키(시·도 또는 나라)."""
    if key.startswith("KR-"):
        code = key[3:]
        return "KR-" + _SIDO_OVERRIDE.get(code, code[:2])
    parts = key.split("-")
    return f"W-{parts[1]}" if len(parts) >= 2 else key


_SI_GU = re.compile(r"^(.+?시)(.+구)$")


def municipality_name(code, lang="ko"):
    for c, name, name_en, _bbox, _polys in _load_kr():
        if c == code:
            if lang == "ko":
                m = _SI_GU.match(name)
                return f"{m.group(1)} {m.group(2)}" if m else name
            return name_en
    return ""


def world_city_name(gid):
    return _load_world()["names"].get(int(gid), "")


def country_name_en(cc):
    return _load_world()["countries"].get(cc, cc)

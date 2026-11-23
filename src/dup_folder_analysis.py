# -*- coding: utf-8 -*-
"""
FolderKit++ — 중복 찾기 결과로 "통째로 복사된 폴더" 찾기 [v50]

## 무엇을 찾나
중복 파일이 수십만 개 나와도, 대개는 누군가 폴더 하나를 통째로 복사해 둔 경우다
(USB 백업, "자료_복사본", 옛 노트북에서 옮긴 폴더…). 그런 폴더 쌍을 찾아 알려 주면
파일을 하나하나 고르지 않고 폴더 단위로 정리할 수 있다.

- 통째 복사(full)   : 두 폴더의 파일이 서로 빠짐없이 같다
- 포함(contained)   : 한쪽 폴더의 파일이 모두 다른 쪽에도 있다(다른 쪽엔 더 있음)
- 대부분 겹침(partial): 한쪽 폴더 파일의 80% 이상이 다른 쪽에도 있다

## 어떻게
1) 폴더마다 (하위 폴더 포함) 파일 수·용량을 센다 — folder_stats()
2) 중복 그룹의 파일 두 개 a, b마다 "a가 든 폴더 ↔ b가 든 폴더" 쌍에 점수를 준다.
   두 폴더 이름이 같으면 한 단계 위 폴더 쌍에도 점수를 준다
   (D:\\백업\\2024자료\\사진\\1.jpg ↔ E:\\2024자료\\사진\\1.jpg 이면
    사진↔사진, 2024자료↔2024자료 둘 다). 그래서 위쪽 폴더 쌍의 점수에는 아래쪽
   폴더 쌍의 점수가 모두 들어 있다.
3) 폴더 쌍마다 "양쪽 폴더 파일 중 상대 폴더에도 있는 비율"을 구해 분류한다.
4) 이미 보고한 폴더 쌍 안쪽의 폴더 쌍은 다시 보고하지 않는다(위 폴더가 통째
   복사면 그 안의 하위 폴더도 당연히 통째 복사이므로).

파일 이름이 바뀌었어도 내용이 같으면 바로 위 폴더 쌍까지는 점수를 받는다.
"""
import os
from collections import defaultdict

KIND_FULL = "full"
KIND_CONTAINED = "contained"
KIND_PARTIAL = "partial"

PARTIAL_RATIO = 0.8        # 이만큼 겹치면 "대부분 겹침"
MIN_FILES = 3              # 파일이 이보다 적은 폴더는 보고하지 않음(우연한 겹침)
GROUP_MEMBER_CAP = 20      # 한 그룹에서 짝을 지을 파일 수 상한(같은 파일 천 개 → 50만 쌍 방지)


def folder_stats(files, roots, include_empty=False):
    """files: FileInfo(path, size) 목록 → {폴더: [파일 수, 용량]} (하위 폴더 포함).
    스캔한 폴더(roots)보다 위로는 올라가지 않는다."""
    root_set = {os.path.normcase(os.path.normpath(r)) for r in roots}
    chains = {}                    # 폴더 → 위로 올라가며 거치는 폴더들(스캔 폴더까지)
    stats = defaultdict(lambda: [0, 0])

    def chain(d):
        c = chains.get(d)
        if c is not None:
            return c
        out = []
        cur = d
        while True:
            out.append(cur)
            if os.path.normcase(cur) in root_set:
                break
            up = os.path.dirname(cur)
            if up == cur:
                break
            cached = chains.get(up)
            if cached is not None:
                out.extend(cached)
                break
            cur = up
        chains[d] = out
        return out

    for fi in files:
        if fi.size == 0 and not include_empty:
            continue
        for d in chain(os.path.dirname(fi.path)):
            s = stats[d]
            s[0] += 1
            s[1] += fi.size
    return dict(stats)


def _is_under(child, parent):
    if len(child) <= len(parent):
        return False
    return child.startswith(parent) and child[len(parent)] in ("\\", "/")


def analyze(groups, stats, max_report=40, cancel_cb=None):
    """groups: DuplicateGroup(size, paths) 목록, stats: folder_stats() 결과.
    반환: 보고할 폴더 쌍 dict 목록(겹치는 용량이 큰 순)."""
    if not groups or not stats:
        return []
    # 쌍 → [왼쪽 파일 수, 왼쪽 용량, 오른쪽 파일 수, 오른쪽 용량]
    acc = defaultdict(lambda: [0, 0, 0, 0])
    for n, g in enumerate(groups):
        if cancel_cb is not None and n % 2000 == 0 and cancel_cb():
            return []
        paths = g.paths[:GROUP_MEMBER_CAP]
        if len(paths) < 2:
            continue
        credited = defaultdict(set)     # 이 그룹 안에서: (쌍, 쪽) → 이미 센 파일
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = paths[i], paths[j]
                da, db = os.path.dirname(a), os.path.dirname(b)
                while da != db:
                    if da < db:
                        key, fa, fb = (da, db), a, b
                    else:
                        key, fa, fb = (db, da), b, a
                    credited[(key, 0)].add(fa)
                    credited[(key, 1)].add(fb)
                    if _is_under(da, db) or _is_under(db, da):
                        break       # 한쪽이 다른 쪽 안 — 더 올라가면 같은 폴더가 된다
                    if os.path.basename(da) != os.path.basename(db):
                        break       # 폴더 이름이 다르면 복사 경로가 여기서 갈라진 것
                    ua, ub = os.path.dirname(da), os.path.dirname(db)
                    if ua == da or ub == db or ua not in stats or ub not in stats:
                        break       # 드라이브 맨 위·스캔 폴더 바깥
                    da, db = ua, ub
        size = g.size
        for (key, side), fs in credited.items():
            r = acc[key]
            r[side * 2] += len(fs)
            r[side * 2 + 1] += len(fs) * size

    cands = []
    for (pa, pb), (na, ba, nb, bb) in acc.items():
        sa, sb = stats.get(pa), stats.get(pb)
        if not sa or not sb:
            continue
        ta, tb = sa[0], sb[0]
        if ta < MIN_FILES or tb < MIN_FILES:
            continue
        ra, rb = na / ta, nb / tb
        full_a, full_b = na >= ta, nb >= tb
        if full_a and full_b:
            kind = KIND_FULL
        elif full_a or full_b:
            kind = KIND_CONTAINED
            if full_b:                       # 늘 "왼쪽(a)이 오른쪽(b)에 다 들어 있다"로 맞춘다
                pa, pb, na, ba, nb, bb, sa, sb, ra, rb = pb, pa, nb, bb, na, ba, sb, sa, rb, ra
        elif max(ra, rb) >= PARTIAL_RATIO:
            kind = KIND_PARTIAL
            if rb > ra:
                pa, pb, na, ba, nb, bb, sa, sb, ra, rb = pb, pa, nb, bb, na, ba, sb, sa, rb, ra
        else:
            continue
        cands.append({
            "kind": kind, "a": pa, "b": pb,
            "a_files": sa[0], "a_bytes": sa[1], "a_dup_files": na, "a_dup_bytes": ba, "a_ratio": min(ra, 1.0),
            "b_files": sb[0], "b_bytes": sb[1], "b_dup_files": nb, "b_dup_bytes": bb, "b_ratio": min(rb, 1.0),
            "dup_bytes": min(ba, bb),      # 이 쌍을 정리하면 아낄 수 있는 용량(대략)
        })

    # 겹치는 용량이 큰 순 → 위 폴더 쌍이 아래 폴더 쌍보다 먼저 온다(점수를 다 포함하므로).
    # 용량이 같으면(위 폴더에 겹치는 파일이 더 없음) 통째 복사 > 포함 > 대부분 겹침,
    # 그다음 더 깊은 쪽 — "원본\2024자료 ↔ 백업\2024자료 통째 복사"가
    # "백업이 원본에 포함"보다 더 정확한 설명이다.
    rank = {KIND_FULL: 0, KIND_CONTAINED: 1, KIND_PARTIAL: 2}
    cands.sort(key=lambda c: (-c["dup_bytes"], rank[c["kind"]], -(len(c["a"]) + len(c["b"]))))

    def within(x, y, rx, ry):
        return (x == rx or _is_under(x, rx)) and (y == ry or _is_under(y, ry))

    reported = []
    for c in cands:
        a, b = c["a"], c["b"]
        skip = False
        for r in reported:
            ra_, rb_ = r["a"], r["b"]
            if within(a, b, ra_, rb_) or within(a, b, rb_, ra_):
                skip = True        # 이미 보고한 쌍의 안쪽
                break
            if r["dup_bytes"] >= c["dup_bytes"] and (within(ra_, rb_, a, b) or within(ra_, rb_, b, a)):
                skip = True        # 이미 보고한 쌍을 감싸기만 하고 더 겹치는 파일이 없음
                break
        if skip:
            continue
        reported.append(c)
        if len(reported) >= max_report:
            break
    return reported


def count_by_kind(report):
    out = {KIND_FULL: 0, KIND_CONTAINED: 0, KIND_PARTIAL: 0}
    for c in report:
        out[c["kind"]] += 1
    return out

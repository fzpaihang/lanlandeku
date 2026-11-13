# -*- coding: utf-8 -*-
"""昵称索引：把网页那份 uid → 昵称 索引搬到本地，让 APK 能按昵称查人。

数据源：GitHub Pages 的 data/lookup-index.json（refresh.yml 每次抓取后自动重建）
缓存：  <应用数据目录>/lookup-index.json
策略：  启动时后台加载，绝不阻塞界面；
        6 小时内不重复下载；
        下载失败就用旧缓存；
        完全没数据时自动降级为「只能按 UID 查」，原功能一点不受影响。
"""
import io
import json
import os
import ssl
import threading
import time
import urllib.request

import lookup_core as L

URLS = (
    "https://fzpaihang.github.io/lanlandeku/data/lookup-index.json",
    "https://cdn.jsdelivr.net/gh/fzpaihang/lanlandeku@main/data/lookup-index.json",
)

DATA_DIR = getattr(L, "DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(DATA_DIR, "lookup-index.json")
CHECK_GAP = 6 * 3600        # 两次联网检查的最小间隔
TIMEOUT = 20
SCAN_CAP = 600              # 单次搜索最多收集这么多命中，避免超大结果集

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_lock = threading.Lock()
_players = []               # [(uid, name, server_key, server_name, lv)]
_state = "idle"             # idle | loading | ready | empty
_source = ""                # cache | net | ""
_started = False


def state():
    return _state


def count():
    with _lock:
        return len(_players)


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fzjh-lookup"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as r:
        return r.read()


def _parse(raw):
    """lookup-index.json → 扁平列表。榜单在前，5 转在后，重名都能被搜到。"""
    d = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    out = []
    seen = set()
    for p in d.get("players") or []:
        if not isinstance(p, dict) or p.get("u") is None:
            continue
        name = str(p.get("n") or "").strip()
        if not name:
            continue
        try:
            uid = int(p["u"])
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append((uid, name, str(p.get("s") or "taptap"),
                    str(p.get("sn") or ""), p.get("lv")))
    for it in d.get("zhuan5") or []:
        if not isinstance(it, list) or len(it) < 2 or it[0] is None:
            continue
        name = str(it[1] or "").strip()
        if not name:
            continue
        try:
            uid = int(it[0])
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append((uid, name, "taptap", "苍松迎客", None))
    return out


def _read_cache():
    try:
        with io.open(CACHE, encoding="utf-8") as f:
            rows = _parse(f.read())
        return rows, os.path.getmtime(CACHE)
    except Exception:
        return [], 0


def _write_cache(raw):
    tmp = CACHE + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
        if os.path.exists(CACHE):
            os.remove(CACHE)
        os.rename(tmp, CACHE)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _load_blocking():
    """先吃本地缓存让功能立刻可用，再视情况联网刷新。"""
    global _players, _state, _source

    rows, mtime = _read_cache()
    if rows:
        with _lock:
            _players = rows
        _state, _source = "ready", "cache"

    if mtime and time.time() - mtime < CHECK_GAP:
        if not rows:
            _state = "empty"
        return

    raw = None
    for url in URLS:
        try:
            raw = _fetch(url)
            break
        except Exception:
            continue

    if not raw:
        _state = "ready" if rows else "empty"
        return

    try:
        fresh = _parse(raw)
    except Exception:
        _state = "ready" if rows else "empty"
        return

    if not fresh:
        _state = "ready" if rows else "empty"
        return

    _write_cache(raw)
    with _lock:
        _players = fresh
    _state, _source = "ready", "net"


def load_async(on_done=None):
    """后台加载，不阻塞 UI。on_done(状态, 条数) 会在后台线程里被调用。"""
    global _started, _state
    if _started:
        return
    _started = True
    _state = "loading"

    def run():
        try:
            _load_blocking()
        except Exception:
            _state = "ready" if _players else "empty"
        if on_done:
            try:
                on_done(_state, count())
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()


def search(text, limit=8):
    """本地模糊匹配：完全相等 > 前缀 > 包含。返回 list[dict]。"""
    q = str(text or "").strip().lower()
    if not q:
        return []
    with _lock:
        snap = _players
    if not snap:
        return []

    hits = []
    for uid, name, key, sname, lv in snap:
        n = name.lower()
        if n == q:
            score = 0
        elif n.startswith(q):
            score = 1
        elif q in n:
            score = 2
        else:
            continue
        hits.append((score, -(lv or 0), uid, name, key, sname, lv))
        if len(hits) >= SCAN_CAP:
            break

    hits.sort()
    return [{"u": h[2], "n": h[3], "s": h[4], "sn": h[5], "lv": h[6]}
            for h in hits[:limit]]


def get(uid):
    key = str(uid or "").strip()
    if not key.isdigit():
        return None
    with _lock:
        for u, n, k, sn, lv in _players:
            if str(u) == key:
                return {"u": u, "n": n, "s": k, "sn": sn, "lv": lv}
    return None

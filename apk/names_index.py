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
MAX_LOCAL = 500             # 本地补录保留条数（用户查过的角色）

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_lock = threading.Lock()
_players = []               # [(uid, name, server_key, server_name, lv)]
_hidden = set()             # 不允许查询的 uid（来自 lookup-index.json 的 hidden 字段）
_state = "idle"             # idle | loading | ready | empty
_source = ""                # cache | net | ""
_started = False

# 本地补录：用户查过的角色，即使不在榜单/普查名单里，也应该能按昵称再搜到。
# 存在 ANDROID_PRIVATE/local-names.json，与远端索引合并后参与 search()。
LOCAL = os.path.join(DATA_DIR, "local-names.json")
_local = []                 # [(uid, name, server_key, server_name, lv)]


def state():
    return _state


def count():
    return len(_all_rows())


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fzjh-lookup"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as r:
        return r.read()


def _parse_hidden(raw):
    """抽出索引里的隐藏名单：[[uid, server], ...] → {uid}。"""
    try:
        d = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return set(str(x[0]) for x in (d.get("hidden") or [])
                   if isinstance(x, (list, tuple)) and x and x[0] is not None)
    except Exception:
        return set()


def _parse(raw):
    """lookup-index.json → 扁平列表。榜单在前，5 转在后，重名都能被搜到。

    隐藏名单在构建侧已经剔除，这里再挡一次：即使拿到旧索引也不会漏。
    """
    d = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    blocked = _parse_hidden(raw)
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
        if str(uid) in blocked or uid in seen:
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
        if str(uid) in blocked or uid in seen:
            continue
        seen.add(uid)
        out.append((uid, name, "taptap", "苍松迎客", None))
    return out


def _read_local():
    """读本地补录（用户查过的角色）。失败就当作空。"""
    try:
        with io.open(LOCAL, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    out = []
    for p in d.get("players") or []:
        try:
            uid = int(p.get("u"))
        except (TypeError, ValueError):
            continue
        name = str(p.get("n") or "").strip()
        if not name:
            continue
        out.append((uid, name, str(p.get("s") or "taptap"),
                    str(p.get("sn") or ""), p.get("lv")))
    return out


def _write_local(rows):
    """原子写回本地补录。最多留 MAX_LOCAL 条（新的在前）。"""
    tmp = LOCAL + ".tmp"
    try:
        items = [{"u": u, "n": n, "s": k, "sn": sn, "lv": lv}
                 for (u, n, k, sn, lv) in rows[:MAX_LOCAL]]
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"players": items}, ensure_ascii=False,
                               separators=(",", ":")))
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, LOCAL)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def remember(uid, name, server_key="", server_name="", lv=None):
    """查询成功后调用：把这个角色记进本地补录，下次能按昵称搜到。

    这是「查完 UID 之后应该能按昵称搜回来」这个需求的落地点。
    远端索引只覆盖榜单 + 苍松 5 转普查，散人查过也不会进去，
    所以必须在本机留一份，并且立刻参与 search()。
    """
    global _local
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return False
    name = str(name or "").strip()
    if not name:
        return False
    with _lock:
        rows = [r for r in _local if r[0] != uid]
        rows.insert(0, (uid, name, str(server_key or "taptap"),
                        str(server_name or ""), lv))
        _local = rows
        _write_local(rows)
    return True


def _all_rows():
    """远端索引 ∪ 本地补录；同一 uid 以本地为准（昵称可能改过）。"""
    with _lock:
        local = list(_local)
        snap = list(_players)
    if not local:
        return snap
    overridden = set(r[0] for r in local)
    return local + [r for r in snap if r[0] not in overridden]


def _read_cache():
    """读缓存时同步恢复隐藏名单——离线也不能让隐藏玩家被搜出来。"""
    global _hidden
    try:
        with io.open(CACHE, encoding="utf-8") as f:
            raw = f.read()
        rows = _parse(raw)
        with _lock:
            _hidden = _parse_hidden(raw)
        return rows, os.path.getmtime(CACHE)
    except Exception:
        return [], 0


def _write_cache(raw):
    tmp = CACHE + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, CACHE)      # remove+rename 之间有空窗，直接 replace 一步到位
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _load_blocking():
    """先吃本地缓存让功能立刻可用，再视情况联网刷新。"""
    global _players, _state, _source, _hidden

    global_local = _read_local()
    if global_local:
        with _lock:
            _local[:] = global_local

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
        _hidden = _parse_hidden(raw)
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
    snap = _all_rows()
    with _lock:
        blocked = set(_hidden)
    if not snap:
        return []

    hits = []
    for uid, name, key, sname, lv in snap:
        if str(uid) in blocked:
            continue
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


def is_hidden(uid):
    """该 uid 是否属于隐私名单（APK 查询前会用它拦截）。"""
    with _lock:
        return str(uid or "").strip() in _hidden


def get(uid):
    key = str(uid or "").strip()
    if not key.isdigit() or is_hidden(key):
        return None
    for u, n, k, sn, lv in _all_rows():
        if str(u) == key:
            return {"u": u, "n": n, "s": k, "sn": sn, "lv": lv}
    return None

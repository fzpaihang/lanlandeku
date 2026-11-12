# -*- coding: utf-8 -*-
"""腾讯云函数（SCF）入口：按 UID 实时查玩家档案。

调用方式（函数 URL / API 网关，GET）：
    /?uid=21079747122&server=taptap_3

返回：
    成功  {"ok": true,  "data": {...档案...}, "elapsedMs": 3200}
    失败  {"ok": false, "code": "NOT_FOUND", "message": "…"}

环境变量（SCF 控制台 → 函数配置 → 环境变量）：
    FZJH_SERVERS  GitHub Actions 里那个同名 Secret 原样贴进来（JSON 数组，含五区 uuid/account/channel）
    FZJH_HOTVER   游戏热更版本号，如 18464（游戏更新后往上调）
    FZJH_ORIGIN   允许跨域的站点，默认 https://fzpaihang.github.io

同目录必须存在：fetch.py / lookup_core.py / aes_pure.py / names.json
（由 scripts/build_api_zip.py 从 apk/ 复制打包，不要手改这几份副本）
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import lookup_core as L  # noqa: E402
import fetch as F        # noqa: E402
import urllib.parse      # noqa: E402
import urllib.request    # noqa: E402

# SCF 只有 /tmp 可写；缓存写不进去时 lookup_core 会静默忽略
L.CACHE_PATH = "/tmp/fzjh_lookup_cache.json"

DEFAULT_ORIGIN = os.environ.get("FZJH_ORIGIN") or "https://fzpaihang.github.io"
DEFAULT_SERVER = "taptap_3"
CACHE_TTL = 60          # 成功结果复用 60 秒，挡住连点与重复刷新
NOT_FOUND_TTL = 15      # 「查无此人」只压 15 秒，避免一次限流把用户挡一分钟
BOARD_TTL = 6 * 3600    # 榜单（补福缘/排名）成功缓存
BOARD_FAIL_TTL = 600    # 榜单拿不到时，10 分钟内不再重试，避免每次查询都等超时

_HOTVER = None
_CACHE = {}
_BOARD = {}


def _allowed_origin(event):
    """只放行自己的站点和本地调试，避免别人白嫖接口额度。"""
    hdrs = event.get("headers") or {}
    origin = ""
    for k, v in hdrs.items():
        if str(k).lower() == "origin":
            origin = v
            break
    if not origin:
        return DEFAULT_ORIGIN
    ok = origin == DEFAULT_ORIGIN or origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost")
    return origin if ok else DEFAULT_ORIGIN


def _cors(event):
    return {
        "Access-Control-Allow-Origin": _allowed_origin(event),
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }


def _query(event):
    """兼容 SCF 函数 URL / API 网关 v1、v2 三种 event 结构。"""
    q = event.get("queryString")
    if isinstance(q, dict):
        return q
    if isinstance(q, str) and q:
        out = {}
        for pair in q.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k] = urllib.parse.unquote(v)
        return out
    if isinstance(event.get("queryStringParameters"), dict):
        return event["queryStringParameters"]
    return {}


def _resp(event, status, payload):
    return {
        "statusCode": status,
        "headers": _cors(event),
        "isBase64Encoded": False,
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _servers():
    """复用 fetch.load_servers()，它已支持 FZJH_SERVERS 环境变量（与 CI 同一个值）。"""
    return F.load_servers()


def _board_short(key, cache=None, days=1):
    """榜单只用来补 福缘/排名/门派：3 秒拿不到就算了，别拖慢查询。"""
    now = time.time()
    rec = _BOARD.get(key)
    if rec:
        ts, rows = rec
        ttl = BOARD_TTL if rows else BOARD_FAIL_TTL
        if now - ts < ttl:
            return rows
    try:
        req = urllib.request.Request(L.INDEX_URL % key, headers={"User-Agent": "fzjh-api"})
        ctx = getattr(F, "ctx", None)
        with urllib.request.urlopen(req, timeout=3, context=ctx) as r:
            rows = json.loads(r.read().decode("utf-8")).get("rows") or []
        _BOARD[key] = (now, rows)
        return rows
    except Exception:
        _BOARD[key] = (now, [])
        return []


L.fetch_board = _board_short


def _noop(_msg):
    pass


def _auto_lookup(uid, servers, cache, hotver):
    """自动探测：先按 UID 位数猜分区（7 位→苍松、10 位→4399、11 位→丹凤/白鹤/墨羽），
    猜不中再依次试。被限流（20616）的区只在最后集中退避重试一次，
    避免把五个区一起打满。"""
    order = L.order_servers(servers, uid)
    limited = []
    for i, srv in enumerate(order):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, _noop)
        if ec not in (0,):
            limited.append(srv)
        if i < len(order) - 1:
            time.sleep(0.4)

    for srv in limited:
        time.sleep(1.5)
        data, _ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, _noop)
    return None


def main_handler(event, context=None):
    global _HOTVER
    t0 = time.time()

    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return _resp(event, 204, {})

    q = _query(event)
    uid_raw = str(q.get("uid") or "").strip()
    server = str(q.get("server") or DEFAULT_SERVER).strip() or DEFAULT_SERVER

    if not uid_raw.isdigit() or not (5 <= len(uid_raw) <= 12):
        return _resp(event, 400, {
            "ok": False, "code": "BAD_UID",
            "message": "UID 应该是 5–12 位纯数字（游戏个人信息页里那个角色 ID）",
        })
    uid = int(uid_raw)

    try:
        servers = _servers()
    except SystemExit as e:
        return _resp(event, 500, {
            "ok": False, "code": "CONFIG",
            "message": "服务端缺少配置：%s（检查 FZJH_SERVERS / FZJH_HOTVER 环境变量）" % e,
        })
    except Exception as e:
        return _resp(event, 500, {"ok": False, "code": "CONFIG", "message": "配置读取失败：%s" % e})

    by_key = {s["key"]: s for s in servers}
    if server != L.AUTO_SERVER and server not in by_key:
        return _resp(event, 400, {
            "ok": False, "code": "BAD_SERVER",
            "message": "未知分区：%s" % server,
            "servers": [{"key": s["key"], "name": s["name"]} for s in servers],
        })

    ck = "%s|%s" % (uid, server)
    hit = _CACHE.get(ck)
    if hit and time.time() - hit[0] < (NOT_FOUND_TTL if hit[1].get("code") == "NOT_FOUND" else CACHE_TTL):
        payload = dict(hit[1])
        payload["cached"] = True
        return _resp(event, 200 if payload.get("ok") else 404, payload)

    if _HOTVER is None:
        _HOTVER = int(os.environ.get("FZJH_HOTVER") or servers[0]["hotver"] or 18464)

    cache = {"hotver": _HOTVER}
    try:
        if server == L.AUTO_SERVER:
            prof = _auto_lookup(uid, servers, cache, _HOTVER)
        else:
            prof = L.lookup(uid, server=server, cfg={"servers": servers, "hotver": _HOTVER}, cache=cache)
    except Exception as e:
        return _resp(event, 500, {"ok": False, "code": "ERROR", "message": "查询异常：%s" % e})

    # 版本号被自动校正过就记住，后续请求直接用新值
    try:
        hv = int(cache.get("hotver") or _HOTVER)
        if hv != _HOTVER:
            _HOTVER = hv
    except Exception:
        pass

    if not prof:
        if server == L.AUTO_SERVER:
            payload = {
                "ok": False, "code": "NOT_FOUND",
                "message": "五个分区都没查到这个 UID，确认是游戏内的角色 ID 吗？",
            }
        else:
            name = by_key.get(server, {}).get("name") or server
            payload = {
                "ok": False, "code": "NOT_FOUND",
                "message": "在「%s」没查到这个 UID，分区选对了吗？" % name,
            }
        _CACHE[ck] = (time.time(), payload)   # NOT_FOUND 短暂缓存
        return _resp(event, 404, payload)

    prof["source"] = "live"
    payload = {"ok": True, "data": prof, "elapsedMs": int((time.time() - t0) * 1000)}
    _CACHE[ck] = (time.time(), payload)
    return _resp(event, 200, payload)

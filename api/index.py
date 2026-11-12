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
import threading
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


def _hard_timeout(fn, seconds, default=None):
    """线程级硬超时。urlopen 的 timeout 管不住 DNS 解析，
    国内访问 github.io 时可能整段挂住，这里兜住总时长。"""
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(seconds)
    if th.is_alive():
        return default
    return box.get("v", default)


def _board_short(key, cache=None, days=1):
    """榜单只用来补 福缘/排名/门派。优先读部署包内置的 boards/<key>.json（零网络），
    读不到才回落到站点拉取（线程硬超时 3 秒），绝不拖慢查询。"""
    now = time.time()
    rec = _BOARD.get(key)
    if rec:
        ts, rows = rec
        ttl = BOARD_TTL if rows else BOARD_FAIL_TTL
        if now - ts < ttl:
            return rows

    packed = os.path.join(BASE, "boards", key + ".json")
    if os.path.isfile(packed):
        try:
            with open(packed, "r", encoding="utf-8") as f:
                rows = json.load(f).get("rows") or []
            _BOARD[key] = (now, rows)
            return rows
        except Exception:
            pass

    def _fetch():
        req = urllib.request.Request(L.INDEX_URL % key, headers={"User-Agent": "fzjh-api"})
        with urllib.request.urlopen(req, timeout=4, context=getattr(F, "ctx", None)) as r:
            return json.loads(r.read().decode("utf-8")).get("rows") or []

    rows = _hard_timeout(_fetch, 3.0, None)
    if rows is None:                      # 超时或异常：记失败，10 分钟内不再试
        _BOARD[key] = (now, [])
        return []
    _BOARD[key] = (now, rows)
    return rows


L.fetch_board = _board_short


def _fast_single(uid, srv, cache, hotver, note):
    """云函数版单区查询：重试压到 2 次、退避 0.8 秒，
    版本号探测加 5 秒硬超时，保证整体落在 15 秒函数超时内。"""
    for attempt in range(2):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            return None                       # 服务端明确回「没有这个角色」
        if ec in (20616, -1) and attempt == 0:
            time.sleep(0.8)                   # 限流冷却后只重试一次
            continue
        break

    hv = _hard_timeout(lambda: L._redetect_hotver(srv, hotver), 5.0, None)
    if hv and hv != hotver:
        cache["hotver"] = hv
        data, _ec = L.try_one(dict(srv, hotver=hv), uid, hv)
        if data:
            return L._finish(uid, srv, data, cache, hv, note)
    return None


L._lookup_single = _fast_single


def _noop(_msg):
    pass


def _auto_lookup(uid, servers, cache, hotver, deadline=None):
    """自动探测：只按 UID 位数猜**前 2 个**候选区，不轮询五区。
    五区全试（10+ 次请求）必然触发 20616 限流，导致全部失败——
    宁可快速返回「没查到，换个分区」，也不要让用户等 15 秒后拿到同样的结果。"""
    order = L.order_servers(servers, uid)[:2]
    for i, srv in enumerate(order):
        if deadline and time.time() > deadline:
            break
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, _noop)
        if i < len(order) - 1:
            time.sleep(0.5)
    return None


def _diag():
    """分阶段网络诊断（?diag=1）：DNS / TCP / TLS / 握手 / 查询 各自耗时。
    只返回耗时与 IP，不含任何凭据，可安全暴露。"""
    import socket
    import ssl

    out = {"ok": True, "python": sys.version.split()[0], "steps": []}
    host = urllib.parse.urlparse(F.DOMAIN).hostname
    port = 443

    def mark(name, t, extra=None):
        rec = {"step": name, "ms": int((time.time() - t) * 1000)}
        if extra is not None:
            rec["info"] = extra
        out["steps"].append(rec)

    t = time.time()
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        ips = sorted({i[4][0] for i in infos})
        mark("DNS 解析", t, ips)
    except Exception as e:
        mark("DNS 解析", t, "失败: %s: %s" % (type(e).__name__, e))
        return out

    t = time.time()
    sk = None
    try:
        sk = socket.create_connection((host, port), timeout=8)
        mark("TCP 连接", t, sk.getpeername())
    except Exception as e:
        mark("TCP 连接", t, "失败: %s: %s" % (type(e).__name__, e))
        return out
    finally:
        if sk:
            sk.close()

    t = time.time()
    try:
        raw = socket.create_connection((host, port), timeout=8)
        sctx = ssl.create_default_context()
        sctx.check_hostname = False
        sctx.verify_mode = ssl.CERT_NONE
        with sctx.wrap_socket(raw, server_hostname=host) as ss:
            mark("TLS 握手", t, ss.version())
    except Exception as e:
        mark("TLS 握手", t, "失败: %s: %s" % (type(e).__name__, e))

    try:
        t = time.time()
        keys = F.handshake(F.server_cfg(dict(F.load_servers()[0], hotver=int(
            os.environ.get("FZJH_HOTVER") or 18464))), time.time())
        mark("exchange_publickey 握手", t, "keys=%s" % ",".join(sorted(keys.keys())))

        srv = dict(F.load_servers()[0], hotver=int(os.environ.get("FZJH_HOTVER") or 18464))
        t = time.time()
        d = F.api_post(F.server_cfg(srv), "get_user_info", {"userid": 21079729670, "type": 0}, keys, time.time())
        mark("get_user_info 查询", t, "errcode=%s" % d.get("errcode"))
    except Exception as e:
        mark("协议调用", t, "失败: %s: %s" % (type(e).__name__, e))

    # 单个协议往返（丹凤区）：看是否触发 20616 限流
    try:
        srv3 = dict([s for s in F.load_servers() if s["key"] == "taptap_3"][0])
        srv3["hotver"] = int(os.environ.get("FZJH_HOTVER") or 18464)
        t = time.time()
        data, ec = L.try_one(srv3, 21079729670, srv3["hotver"])
        mark("try_one 丹凤（单次）", t, "errcode=%s%s" % (ec, "" if data else " ← 失败/限流"))
    except Exception as e:
        mark("try_one 丹凤（单次）", t, "异常: %s: %s" % (type(e).__name__, e))

    # 榜单：内置文件 vs 网络
    t = time.time()
    p = os.path.join(BASE, "boards", "taptap_3.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                rows = json.load(f).get("rows") or []
            mark("榜单（内置文件）", t, "%d 行" % len(rows))
        except Exception as e:
            mark("榜单（内置文件）", t, "读取失败: %s" % e)
    else:
        mark("榜单（内置文件）", t, "未打包 boards/taptap_3.json")

    t = time.time()
    try:
        req = urllib.request.Request(L.INDEX_URL % "taptap_3", headers={"User-Agent": "fzjh-api"})
        with urllib.request.urlopen(req, timeout=4, context=getattr(F, "ctx", None)) as r:
            rows = json.loads(r.read().decode("utf-8")).get("rows") or []
        mark("榜单（网络 github.io）", t, "%d 行" % len(rows))
    except Exception as e:
        mark("榜单（网络 github.io）", t, "失败: %s: %s" % (type(e).__name__, str(e)[:80]))

    # 完整 lookup（含重试与版本号校正），硬超时 8 秒，超时也能拿到结论
    hv = int(os.environ.get("FZJH_HOTVER") or 18464)
    try:
        servers = F.load_servers()
    except Exception as e:
        mark("完整 lookup", time.time(), "配置读取失败: %s" % e)
        return out

    box = {}

    def _run():
        try:
            box["v"] = L.lookup(21079729670, server="taptap_3",
                                cfg={"servers": servers, "hotver": hv}, cache={"hotver": hv})
        except Exception as e:
            box["e"] = "%s: %s" % (type(e).__name__, e)

    t = time.time()
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(8)
    if th.is_alive():
        mark("完整 lookup", t, "超过 8 秒仍在跑（这就是函数超时的原因）")
    elif box.get("e"):
        mark("完整 lookup", t, "异常: %s" % box["e"])
    else:
        p = box.get("v")
        mark("完整 lookup", t, (p or {}).get("name") or "未查到")

    return out


def main_handler(event, context=None):
    global _HOTVER
    t0 = time.time()

    if (event.get("httpMethod") or "").upper() == "OPTIONS":
        return _resp(event, 204, {})

    q = _query(event)
    if str(q.get("diag") or "") == "1":
        return _resp(event, 200, _diag())
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
            prof = _auto_lookup(uid, servers, cache, _HOTVER, deadline=t0 + 10)
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
                "message": "自动模式按 UID 位数猜了最可能的 2 个分区，都没查到。"
                           "点上方分区条指定一个区再试（或确认 UID 是否写错）。",
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

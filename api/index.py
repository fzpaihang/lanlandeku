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
    hdrs = _normalize_event(event).get("headers") or {}
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


def _normalize_event(event):
    """把各家云的 event 统一成 dict。

    腾讯云 SCF : dict（含 queryString / body / httpMethod）
    阿里云 FC  : bytes（原始请求体，GET 时为空）
    控制台测试 : str
    """
    if isinstance(event, (bytes, bytearray)):
        try:
            event = bytes(event).decode("utf-8", "replace")
        except Exception:
            return {}
    if isinstance(event, str):
        txt = event.strip()
        if not txt:
            return {}
        try:
            obj = json.loads(txt)
        except Exception:
            return {}
        return obj if isinstance(obj, dict) else {}
    return event if isinstance(event, dict) else {}


def _query(event):
    """从各种 event 结构里挖出参数：query 参数、JSON body、扁平 dict 都支持。"""
    ev = _normalize_event(event)

    # 阿里云 POST 时 event 解析出来就是参数字典本身
    if isinstance(ev.get("uid"), str) or isinstance(ev.get("server"), str) or ev.get("diag"):
        return ev

    for k in ("queryParameters", "queryStringParameters"):
        v = ev.get(k)
        if isinstance(v, dict):
            return v

    q = ev.get("queryString")
    if isinstance(q, str) and q:
        out = {}
        for pair in q.split("&"):
            if "=" in pair:
                a, b = pair.split("=", 1)
                out[a] = urllib.parse.unquote(b)
        return out

    body = ev.get("body")
    if isinstance(body, str) and body.strip():
        txt = body.strip()
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        if "=" in txt:                      # 兼容表单 / query 风格 body
            out = {}
            for pair in txt.split("&"):
                if "=" in pair:
                    a, b = pair.split("=", 1)
                    out[a] = urllib.parse.unquote(b)
            return out
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

# 会话密钥按分区复用：一次查询从「握手+查询」2 个请求降到 1 个，限流压力减半
_KEYS = {}
KEYS_TTL = 180


def _fast_try_one(srv, uid, hotver):
    """与 L.try_one 等价，但复用握手会话，并加硬超时——
    服务端限流时会静默挂住连接（不返回 20616），必须自己掐断。"""
    srv = dict(srv)
    srv["hotver"] = hotver
    cfg = F.server_cfg(srv)
    key = srv["key"]

    def _do():
        rec = _KEYS.get(key)
        if rec and time.time() - rec[0] < KEYS_TTL:
            keys = rec[1]
        else:
            keys = F.handshake(cfg, time.time())
            _KEYS[key] = (time.time(), keys)
        return F.api_post(cfg, "get_user_info", {"userid": uid, "type": 0}, keys, time.time())

    try:
        d = _hard_timeout(_do, 6.0, None)
    except Exception:
        d = None
    if d is None:
        _KEYS.pop(key, None)      # 会话可能已失效，下次重新握手
        return None, -1
    data = d.get("data")
    ec = d.get("errcode")
    if ec == 0 and isinstance(data, dict) and data.get("name"):
        return data, 0
    if ec == 20616:
        _KEYS.pop(key, None)
    return None, ec


L.try_one = _fast_try_one

# 全局节流：多实例各自计数，不精确，但足以避免把自己打到限流
_RATE = {"window": 0, "count": 0}
RATE_LIMIT = 30      # 每实例每分钟最多 30 次真实查询


def _rate_ok():
    win = int(time.time() // 60)
    if _RATE["window"] != win:
        _RATE["window"] = win
        _RATE["count"] = 0
    if _RATE["count"] >= RATE_LIMIT:
        return False
    _RATE["count"] += 1
    return True


def _fast_single(uid, srv, cache, hotver, note):
    """云函数版单区查询：最多试 2 次、退避 1.5 秒。
    限流时尽快失败并给出明确提示，而不是反复重试把窗口拖长。"""
    for attempt in range(2):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            return None                       # 服务端明确回「没有这个角色」
        if ec in (20616, -1):
            cache["_limited"] = ec            # 让上层区分「限流」和「真没这人」
            if attempt == 0:
                time.sleep(1.5)
                continue
        break
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
        if ec in (20616, -1):
            cache["_limited"] = ec
        if i < len(order) - 1:
            time.sleep(0.5)
    return None


def _diag():
    """分阶段网络诊断（?diag=1）。每一步都有硬超时 + 总预算，
    保证自身绝不超过函数超时。只返回耗时/状态，不含凭据。"""
    import socket
    import ssl

    out = {"ok": True, "python": sys.version.split()[0], "steps": []}
    deadline = time.time() + 15
    MARK = object()

    def mark(name, t, extra=None):
        rec = {"step": name, "ms": int((time.time() - t) * 1000)}
        if extra is not None:
            rec["info"] = extra
        out["steps"].append(rec)

    def probe(name, fn, limit=6.0):
        left = deadline - time.time()
        if left < 0.8:
            mark(name, time.time(), "跳过（诊断预算用尽）")
            return MARK
        t = time.time()
        v = _hard_timeout(fn, min(limit, left), MARK)
        if v is MARK:
            mark(name, t, "超过 %.0f 秒无响应（连接被静默丢弃）" % min(limit, left))
        else:
            mark(name, t, v)
        return v

    host = urllib.parse.urlparse(F.DOMAIN).hostname
    hv = int(os.environ.get("FZJH_HOTVER") or 18464)

    # 0) 对照：函数能不能访问普通公网站点
    def _baidu():
        req = urllib.request.Request("https://www.baidu.com/", headers={"User-Agent": "fzjh-api"})
        with urllib.request.urlopen(req, timeout=4, context=getattr(F, "ctx", None)) as r:
            return "HTTP %s" % r.status
    probe("公网对照 baidu.com", _baidu, 5.0)

    def _dns():
        return socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    probe("DNS 解析", _dns, 5.0)

    def _tcp():
        sk = socket.create_connection((host, 443), timeout=5)
        peer = sk.getpeername()[0]
        sk.close()
        return peer
    probe("TCP 连接", _tcp, 6.0)

    def _tls():
        raw = socket.create_connection((host, 443), timeout=5)
        c = ssl.create_default_context()
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        with c.wrap_socket(raw, server_hostname=host) as ss:
            return ss.version()
    probe("TLS 握手", _tls, 6.0)

    try:
        servers = F.load_servers()
        srv0 = dict(servers[0], hotver=hv)
    except BaseException as e:
        # load_servers 用 SystemExit 报配置错误，它不是 Exception 子类，必须抓 BaseException
        mark("读取分区配置", time.time(), "失败: %s: %s" % (type(e).__name__, e))
        return out

    def _hs():
        keys = F.handshake(F.server_cfg(dict(srv0)), time.time())
        return "keys=%s" % ",".join(sorted(keys.keys()))
    probe("exchange_publickey 握手", _hs, 8.0)

    def _one():
        srv = [s for s in servers if s["key"] == "taptap_3"][0]
        data, ec = L.try_one(dict(srv), 21079729670, hv)
        return "errcode=%s%s" % (ec, " → " + (data or {}).get("name", "") if data else "")
    probe("try_one 丹凤（线上实现）", _one, 10.0)

    t = time.time()
    pth = os.path.join(BASE, "boards", "taptap_3.json")
    if os.path.isfile(pth):
        try:
            with open(pth, "r", encoding="utf-8") as f:
                rows = json.load(f).get("rows") or []
            mark("榜单（内置文件）", t, "%d 行" % len(rows))
        except Exception as e:
            mark("榜单（内置文件）", t, "读取失败: %s" % e)
    else:
        mark("榜单（内置文件）", t, "未打包 boards/taptap_3.json")

    def _full():
        return L.lookup(21079729670, server="taptap_3",
                        cfg={"servers": servers, "hotver": hv}, cache={"hotver": hv})
    left = max(2.0, deadline - time.time())
    t = time.time()
    v = _hard_timeout(_full, min(10.0, left), MARK)
    if v is MARK:
        mark("完整 lookup", t, "超时未返回")
    else:
        mark("完整 lookup", t, (v or {}).get("name") or "未查到")

    return out


def main_handler(event, context=None):
    global _HOTVER
    t0 = time.time()

    ev = _normalize_event(event)
    method = (ev.get("httpMethod")
              or (ev.get("requestContext") or {}).get("http", {}).get("method")
              or "GET").upper()
    if method == "OPTIONS":
        return _resp(event, 204, {})

    q = _query(event)
    if str(q.get("diag") or "") == "1":
        return _resp(event, 200, _diag())
    uid_raw = str(q.get("uid") or "").strip()
    server = str(q.get("server") or DEFAULT_SERVER).strip() or DEFAULT_SERVER

    if not uid_raw:
        return _resp(event, 200, {
            "ok": True, "service": "fzjh-lookup",
            "message": "POST 一个 JSON：{\"uid\":\"21079729670\",\"server\":\"taptap_3\"}；"
                       "或 GET ?uid=...&server=...",
        })
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

    if not _rate_ok():
        return _resp(event, 429, {
            "ok": False, "code": "BUSY",
            "message": "查询太频繁了，请等 30 秒再试（游戏接口有频率限制）。",
        })

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
        if cache.get("_limited"):
            payload = {
                "ok": False, "code": "BUSY",
                "message": "游戏接口正在限流（查询太密集），请等 30 秒后再试。",
            }
            return _resp(event, 429, payload)
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

# 阿里云 FC 的「请求处理程序」填 index.handler（腾讯云填 index.main_handler）
handler = main_handler

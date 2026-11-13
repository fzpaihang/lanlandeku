# -*- coding: utf-8 -*-
"""Vercel 函数：按 UID 实时查档案，并把 uid → 昵称 归档回仓库。

    GET /api/query?uid=7257325&server=taptap
    GET /api/query?diag=1                 # 分阶段网络诊断（含出口 IP）

返回：
    成功  {"ok": true, "data": {...档案...}, "elapsedMs": 3200, "archived": "ok"}
    失败  {"ok": false, "code": "NOT_FOUND" | "BUSY" | "BAD_UID" | "CONFIG"}

环境变量（Vercel → Project → Settings → Environment Variables）：
    FZJH_SERVERS  与 GitHub Secret 里同名值**完全一致**（JSON 数组，含五区 uuid/account/channel）
    FZJH_HOTVER   游戏热更版本号，如 18464（游戏更新后往上调）
    FZJH_ORIGIN   允许跨域的站点，默认 https://fzpaihang.github.io
    GH_TOKEN      fine-grained PAT，只勾本仓库的 Contents: Read and write
    GH_REPO       fzpaihang/lanlandeku

协议核心只有 apk/ 一份源，这里只做引用，不复制代码。
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(ROOT, "apk")
for _p in (APK, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lookup_core as L  # noqa: E402
import fetch as F        # noqa: E402

# Vercel 只有 /tmp 可写；lookup_core 的 save_cache 失败会静默忽略
L.CACHE_PATH = "/tmp/fzjh_lookup_cache.json"

DEFAULT_ORIGIN = os.environ.get("FZJH_ORIGIN") or "https://fzpaihang.github.io"
DEFAULT_SERVER = "taptap_3"
CACHE_TTL = 600          # 成功结果复用 10 分钟：游戏接口限流很紧，重复查同一个人不该再发请求
NOT_FOUND_TTL = 20       # 「查无此人」只压 20 秒，避免一次限流把用户挡一分钟
BOARD_TTL = 6 * 3600     # 榜单（补福缘/排名）缓存
QUERY_BUDGET = 22        # 单次查询总预算（秒），留出余量给 30 秒的函数上限

GH_PATH = "data/extra-names.json"
GH_MAX_ITEMS = 5000      # 归档文件上限，约 300 KB

_HOTVER = None
_CACHE = {}
_BOARD = {}
_KEYS = {}
KEYS_TTL = 180
_RATE = {"window": 0, "count": 0}
RATE_LIMIT = 40          # 每实例每分钟最多 40 次真实查询


# ---------------------------------------------------------------- 工具

def _hard_timeout(fn, seconds, default=None):
    """线程级硬超时。urlopen 的 timeout 管不住 DNS 解析，
    服务端限流时也会静默挂住连接，必须自己掐断。"""
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


def _origin(o):
    """只放行自己的站点和本地调试，避免别人白嫖接口额度。"""
    o = (o or "").strip()
    if not o:
        return DEFAULT_ORIGIN
    if o == DEFAULT_ORIGIN or o.startswith("http://127.0.0.1") or o.startswith("http://localhost"):
        return o
    return DEFAULT_ORIGIN


def _rate_ok():
    win = int(time.time() // 60)
    if _RATE["window"] != win:
        _RATE["window"] = win
        _RATE["count"] = 0
    if _RATE["count"] >= RATE_LIMIT:
        return False
    _RATE["count"] += 1
    return True


# ---------------------------------------------------------------- 榜单（内置文件）

def _board_local(key, cache=None, days=1):
    """榜单只用来补 福缘/排名/门派。直接读仓库里的 data/servers/<key>/gaoshoubang.json，
    零网络请求——查 github.io 在国内会挂几十秒。"""
    now = time.time()
    rec = _BOARD.get(key)
    if rec and now - rec[0] < BOARD_TTL:
        return rec[1]
    p = os.path.join(ROOT, "data", "servers", key, "gaoshoubang.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            rows = json.load(f).get("rows") or []
    except Exception:
        rows = []
    _BOARD[key] = (now, rows)
    return rows


L.fetch_board = _board_local


# ---------------------------------------------------------------- 查询（会话复用 + 硬超时）

def _fast_try_one(srv, uid, hotver):
    """与 L.try_one 等价，但复用握手会话：一次查询从 2 个请求降到 1 个，限流压力减半。"""
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

    d = _hard_timeout(_do, 6.0, None)
    if d is None:
        _KEYS.pop(key, None)          # 会话可能已失效，下次重新握手
        return None, -1
    data = d.get("data")
    ec = d.get("errcode")
    if ec == 0 and isinstance(data, dict) and data.get("name"):
        return data, 0
    if ec == 20616:
        _KEYS.pop(key, None)
    return None, ec


L.try_one = _fast_try_one


def _noop(_msg):
    pass


def _fast_single(uid, srv, cache, hotver, note):
    """单区查询：最多试 2 次、退避 1.2 秒。限流时尽快失败并给明确提示，
    而不是反复重试把窗口越拖越长。"""
    for attempt in range(2):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            return None                     # 服务端明确回「没有这个角色」
        if ec in (20616, -1):
            cache["_limited"] = ec
            if attempt == 0:
                time.sleep(1.2)
                continue
        break
    return None


L._lookup_single = _fast_single


def _auto_lookup(uid, servers, cache, hotver, deadline):
    """自动模式：只按 UID 位数猜**前 2 个**候选区，不轮询五区。
    五区全试（10+ 次请求）必然触发 20616，宁可快速返回「换个分区再试」。"""
    order = L.order_servers(servers, uid)[:2]
    for i, srv in enumerate(order):
        if time.time() > deadline:
            break
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, _noop)
        if ec in (20616, -1):
            cache["_limited"] = ec
        if i < len(order) - 1:
            time.sleep(0.4)
    return None


# ---------------------------------------------------------------- 归档

def _gh(method, url, payload=None, timeout=6):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + os.environ["GH_TOKEN"])
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "fzjh-lookup")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout, context=F.ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def _archive(prof):
    """把 uid → 昵称 写回仓库的 data/extra-names.json。

    只写「查询确实成功」的结果，昵称来自游戏接口而不是用户输入，无法伪造。
    任何失败都不影响本次查询的返回，只记一个状态码。
    """
    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("GH_REPO")
    if not token or not repo:
        return "off"

    uid = str(prof.get("uid") or "")
    name = (prof.get("name") or "").strip()
    if not uid or not name:
        return "skip"

    url = "https://api.github.com/repos/%s/contents/%s" % (repo, GH_PATH)
    rec = {
        "u": int(uid) if uid.isdigit() else uid,
        "n": name,
        "s": prof.get("server") or "",
        "sn": prof.get("serverName") or "",
        "lv": prof.get("lv"),
        "ts": int(time.time()),
    }

    for attempt in range(2):
        try:
            sha = None
            db = {"items": []}
            try:
                cur = _gh("GET", url + "?ref=main")
                sha = cur.get("sha")
                db = json.loads(base64.b64decode(cur.get("content") or "").decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise

            items = db.get("items") or []
            hit = next((x for x in items if str(x.get("u")) == uid), None)
            if hit:
                if (hit.get("n") or "") == name:
                    return "same"          # 昵称没变，不产生无意义的提交
                alias = [a for a in (hit.get("a") or []) if a]
                if hit.get("n") and hit["n"] not in alias:
                    alias.append(hit["n"])
                hit.update(rec)
                hit["a"] = alias[-3:]      # 改名后老昵称仍可搜到，只留最近 3 个
            else:
                if len(items) >= GH_MAX_ITEMS:
                    return "full"
                items.append(rec)

            db["items"] = items
            db["count"] = len(items)
            db["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
            body = {
                "message": "归档昵称：%s（%s）" % (name, uid),
                "content": base64.b64encode(
                    json.dumps(db, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).decode("ascii"),
                "branch": "main",
            }
            if sha:
                body["sha"] = sha
            _gh("PUT", url, body)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt == 0:
                time.sleep(0.6)            # 并发提交撞车，重读一次再写
                continue
            return "http%d" % e.code
        except Exception as e:
            return type(e).__name__
    return "conflict"


# ---------------------------------------------------------------- 诊断

def _diag():
    out = {"ok": True, "python": sys.version.split()[0], "region": os.environ.get("VERCEL_REGION", ""), "steps": []}
    deadline = time.time() + 20
    MARK = object()

    def mark(name, t, extra=None):
        rec = {"step": name, "ms": int((time.time() - t) * 1000)}
        if extra is not None:
            rec["info"] = extra
        out["steps"].append(rec)

    def probe(name, fn, limit=6.0):
        left = deadline - time.time()
        if left < 0.8:
            mark(name, time.time(), "跳过（预算用尽）")
            return MARK
        t = time.time()
        v = _hard_timeout(fn, min(limit, left), MARK)
        mark(name, t, "超过 %.0f 秒无响应" % min(limit, left) if v is MARK else v)
        return v

    def _ip():
        req = urllib.request.Request("https://api.ipify.org?format=json",
                                     headers={"User-Agent": "fzjh-api"})
        with urllib.request.urlopen(req, timeout=4, context=F.ctx) as r:
            return json.loads(r.read().decode("utf-8")).get("ip")
    probe("出口 IP", _ip, 5.0)

    hv = int(os.environ.get("FZJH_HOTVER") or 18464)
    try:
        servers = F.load_servers()
    except BaseException as e:      # load_servers 用 SystemExit 报配置错误
        mark("读取分区配置", time.time(), "失败: %s: %s" % (type(e).__name__, e))
        return out
    mark("读取分区配置", time.time(), "%d 个分区" % len(servers))

    srv = dict(servers[0], hotver=hv)

    def _hs():
        keys = F.handshake(F.server_cfg(dict(srv)), time.time())
        return "keys=%s" % ",".join(sorted(keys.keys()))
    probe("exchange_publickey 握手", _hs, 8.0)

    def _one():
        data, ec = L.try_one(dict(srv), 7257325, hv)
        return "errcode=%s%s" % (ec, (" → " + (data or {}).get("name", "")) if data else "")
    probe("try_one 苍松（7257325）", _one, 10.0)

    t = time.time()
    rows = _board_local("taptap")
    mark("榜单（内置文件）", t, "%d 行" % len(rows))

    mark("归档配置", time.time(),
         "GH_TOKEN=%s GH_REPO=%s" % ("有" if os.environ.get("GH_TOKEN") else "缺失",
                                     os.environ.get("GH_REPO") or "缺失"))
    return out


# ---------------------------------------------------------------- 入口

class handler(BaseHTTPRequestHandler):
    server_version = "fzjh-lookup"

    def log_message(self, *a):
        pass

    def _cors(self, origin):
        self.send_header("Access-Control-Allow-Origin", _origin(origin))
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Vary", "Origin")

    def _send(self, status, payload, origin=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self._cors(origin)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors(self.headers.get("Origin"))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()

    def _run(self):
        global _HOTVER
        t0 = time.time()
        origin = self.headers.get("Origin")

        u = urllib.parse.urlparse(self.path or "/")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if self.command == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if 0 < n < 8192:
                    obj = json.loads(self.rfile.read(n).decode("utf-8", "replace"))
                    if isinstance(obj, dict):
                        q.update({k: str(v) for k, v in obj.items()})
            except Exception:
                pass

        if str(q.get("diag") or "") == "1":
            self._send(200, _diag(), origin)
            return

        uid_raw = str(q.get("uid") or "").strip()
        server = str(q.get("server") or DEFAULT_SERVER).strip() or DEFAULT_SERVER

        if not uid_raw:
            self._send(200, {
                "ok": True, "service": "fzjh-lookup",
                "message": "GET ?uid=21079729670&server=taptap_3；或 POST {\"uid\":\"...\"}；?diag=1 看诊断",
            }, origin)
            return

        if not uid_raw.isdigit() or not (5 <= len(uid_raw) <= 12):
            self._send(400, {
                "ok": False, "code": "BAD_UID",
                "message": "UID 应该是 5–12 位纯数字（游戏个人信息页里那个角色 ID）",
            }, origin)
            return
        uid = int(uid_raw)

        try:
            servers = F.load_servers()
        except BaseException as e:
            self._send(500, {
                "ok": False, "code": "CONFIG",
                "message": "服务端缺少配置：%s（检查 FZJH_SERVERS / FZJH_HOTVER）" % e,
            }, origin)
            return

        by_key = {s["key"]: s for s in servers}
        if server != L.AUTO_SERVER and server not in by_key:
            self._send(400, {
                "ok": False, "code": "BAD_SERVER",
                "message": "未知分区：%s" % server,
                "servers": [{"key": s["key"], "name": s["name"]} for s in servers],
            }, origin)
            return

        ck = "%s|%s" % (uid, server)
        hit = _CACHE.get(ck)
        if hit:
            ttl = NOT_FOUND_TTL if hit[1].get("code") == "NOT_FOUND" else CACHE_TTL
            if time.time() - hit[0] < ttl:
                payload = dict(hit[1])
                payload["cached"] = True
                payload["elapsedMs"] = int((time.time() - t0) * 1000)   # 命中缓存时重算，别复用上次的耗时
                self._send(200 if payload.get("ok") else 404, payload, origin)
                return

        if _HOTVER is None:
            _HOTVER = int(os.environ.get("FZJH_HOTVER") or servers[0]["hotver"] or 18464)

        if not _rate_ok():
            self._send(429, {
                "ok": False, "code": "BUSY",
                "message": "查询太频繁了，请等 30 秒再试（游戏接口有频率限制）。",
            }, origin)
            return

        cache = {"hotver": _HOTVER}
        try:
            if server == L.AUTO_SERVER:
                prof = _auto_lookup(uid, servers, cache, _HOTVER, t0 + QUERY_BUDGET)
            else:
                prof = L.lookup(uid, server=server,
                                cfg={"servers": servers, "hotver": _HOTVER}, cache=cache)
        except Exception as e:
            self._send(500, {"ok": False, "code": "ERROR", "message": "查询异常：%s" % e}, origin)
            return

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
                self._send(429, payload, origin)
                return
            if server == L.AUTO_SERVER:
                payload = {
                    "ok": False, "code": "NOT_FOUND",
                    "message": "自动模式按 UID 位数猜了最可能的 2 个分区，都没查到。"
                               "点下方分区按钮指定一个区再试（或确认 UID 是否写错）。",
                }
            else:
                payload = {
                    "ok": False, "code": "NOT_FOUND",
                    "message": "在「%s」没查到这个 UID，分区选对了吗？"
                               % (by_key.get(server, {}).get("name") or server),
                }
            _CACHE[ck] = (time.time(), payload)
            self._send(404, payload, origin)
            return

        prof["source"] = "live"
        payload = {
            "ok": True,
            "data": prof,
            "elapsedMs": int((time.time() - t0) * 1000),
            "archived": _archive(prof),
        }
        _CACHE[ck] = (time.time(), payload)
        self._send(200, payload, origin)

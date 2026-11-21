# -*- coding: utf-8 -*-
"""放置江湖 · 高手榜抓取（自包含，不依赖任何外部项目）

链路（逆向结论见原项目 README 第 8 章）：
  1) POST /api/service/exchange_publickey  用设备 uuid 换本会话密钥（JHHU02 容器，密钥静态）
  2) POST /api/v5/get_board/<boardType> {"page":N}  用 JHHU03 会话密钥加密请求 / 解密响应
  3) 响应尾部填充字符是 '0'，需剥掉才能当 JSON 解析

用法:
  python fetch.py                # 抓高手榜全部页 -> data/servers/<key>/gaoshoubang.json
  python fetch.py --board 1      # 指定榜单类型（1=高手榜，写入 gaoshoubang.json）
  python fetch.py --board 4      # 名人堂（指标=江湖阅历，写入 hall.json；每区仅 10 人）
  python fetch.py --max-pages 3  # 只抓前 3 页（调试用）
"""
import io
import hashlib
import json
import os
import random
import ssl
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from Crypto.Cipher import AES  # noqa: E402

DOMAIN = "https://android.fzjh.xiaohoutiaotiao.com"
# iOS 端走另一个域名，且必须 platform=ios + channel=ios 三个一起对才握手成功
# （channel 填 fzjh / fzjh3 会 500）。分区可在 config.json 里用
# "domain" / "platform" 覆盖这两个默认值，见 server_cfg()。
DOMAIN_IOS = "https://ios.fzjh.xiaohoutiaotiao.com"
SALT = b"ed24bd36b1a87f60bebaca65538a590c"
K02 = b"cbIhHHuYQIJ1JkwlLupIvNIvdQDfNxSF"   # JHHU02，握手响应用
IV02 = b"PcIQIZifRalhZ88n"
TAG = b"0"
SLEEP = 0.6          # 页间隔：太快会触发 20616 请求错误（限速）

# 展示用的时间一律按北京时间（UTC+8）格式化。
# GitHub Actions 的 runner 是 UTC，直接用 time.localtime 会写成 UTC，导致页面显示差 8 小时。
BJ_OFFSET = 8 * 3600


def bj_time(ts, fmt="%Y-%m-%d %H:%M"):
    return time.strftime(fmt, time.gmtime(float(ts) + BJ_OFFSET))


def bj_date(ts):
    return bj_time(ts, "%Y-%m-%d")
RETRY = 3
# 限流（errcode=20616「请求错误」）专用退避阶梯，单位秒。
# 普通错误的 3s/6s 对限流毫无意义：一轮 8 页总共只花 5 秒，
# 冷却 3 秒等于立刻再撞一次。实测 11-20 12:49（墨羽惊鸿第 2 页）与
# 11-21 06:39（苍松迎客第 8 页）都是翻页中途被限流打断，整轮作废后
# 该区当天就没有数据，网页上表现为「11-19 直接跳到 11-21」。
RATE_BACKOFF = (15, 45, 90)
# 本轮撞限流的次数；>0 时后续翻页间隔自动翻倍，避免刚恢复就把限额又打满。
RATE_HITS = 0

BOARD_CN = {1: "高手榜", 4: "名人堂"}

# 每个榜写哪个文件名。高手榜沿用历史文件名 gaoshoubang.json（下游脚本按它取数据），
# 名人堂单独存 hall.json，两者互不覆盖。
BOARD_FILE = {1: "gaoshoubang.json", 4: "hall.json"}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def load_cfg():
    """配置来源优先级：环境变量 > config.json

    环境变量用于 CI（GitHub Actions Secrets），避免把凭据写进仓库：
      FZJH_UUID / FZJH_ACCOUNT / FZJH_HOTVER / FZJH_CHANNEL
    """
    cfg = {}
    p = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(p):
        with io.open(p, encoding="utf-8") as f:
            cfg = json.load(f)

    env_uuid = os.environ.get("FZJH_UUID")
    env_acc = os.environ.get("FZJH_ACCOUNT")
    env_hv = os.environ.get("FZJH_HOTVER")

    if env_uuid:
        cfg["uuid"] = env_uuid.strip()
    if env_acc:
        cfg["account"] = int(str(env_acc).strip())
    if env_hv:
        cfg["hotver"] = int(str(env_hv).strip())
    if os.environ.get("FZJH_CHANNEL"):
        cfg["channel"] = os.environ["FZJH_CHANNEL"].strip()

    # 校验放到 load_servers 里做：多服务器时 uuid/account 在 servers 数组内，
    # 顶层可能只有 hotver/ver 这类公共项。
    if not cfg.get("hotver"):
        blob = os.environ.get("FZJH_SERVERS")
        if blob:
            try:
                d = json.loads(blob)
                if isinstance(d, dict) and d.get("hotver"):
                    cfg["hotver"] = d["hotver"]
            except Exception:
                pass
    if not cfg.get("hotver"):
        raise SystemExit("缺少配置：hotver（config.json 或 FZJH_HOTVER）")
    cfg["hotver"] = int(str(cfg["hotver"]).strip())
    cfg.setdefault("ver", "2.1.02")
    cfg.setdefault("channel", "taptap")
    cfg.setdefault("device", "")
    return cfg


def make_nouce(rng=random):
    """6 位，65~122 之间，排除 [ \\ ] ^ _ ` 与 e（Http.lua:67）"""
    out = []
    while len(out) < 6:
        c = rng.randint(65, 122)
        if (90 < c < 97) or c == 101:
            continue
        out.append(chr(c))
    return "".join(out)


def _first_byte_key(s):
    """比较器只比首字节（有符号），@0x610850"""
    return (ord(s[0]) - 256 if ord(s[0]) > 127 else ord(s[0])) if s else 0


def make_sig(nouce, t):
    parts = [nouce, "%.14g" % float(t), SALT.decode()]
    parts.sort(key=_first_byte_key)
    return hashlib.md5("".join(parts).encode("ascii")).hexdigest()


def domain_of(cfg):
    """分区自己的域名，没配就用安卓默认值。"""
    return (cfg or {}).get("domain") or DOMAIN


def build_headers(cfg, t):
    nouce = make_nouce()
    platform = cfg.get("platform") or "android"
    h = {
        "uuid": cfg["uuid"],
        "userid": str(cfg["account"]),
        "sig": make_sig(nouce, t),
        "time": "%.14g" % float(t),
        "nouce": nouce,
        "device": cfg.get("device", ""),
        "ver": cfg.get("ver", "2.1.02"),
        "hotver": str(cfg["hotver"]),
        "platform": platform,
        "timezone": "8",
        "channel": cfg.get("channel", "taptap"),
        "package": "",
        "age": "-2",
        "pkname": "com.xhtt.app.fzjh",
        "pksig": "",
    }
    if platform != "android":
        # iOS 客户端不带这四项（BaseHttp.lua:160 只在 android 下设置 pkname/pksig）
        for k in ("pkname", "pksig"):
            h.pop(k, None)
    return h


def decrypt(raw, key, iv):
    body = bytes(bytearray.fromhex(raw.decode()))[6:]
    return AES.new(key, AES.MODE_CBC, iv).decrypt(body[: len(body) // 16 * 16])


def handshake(cfg, t):
    h = build_headers(cfg, t)
    req = urllib.request.Request(domain_of(cfg) + "/api/service/exchange_publickey", data=b"", method="POST")
    for k, v in h.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        raw = r.read()
    txt = decrypt(raw, K02, IV02).rstrip(b"\x00").decode("utf-8", "replace")
    a = txt.find('"data":"')
    if a < 0:
        raise RuntimeError("握手失败: " + txt[:200])
    s = txt[a + 8:]
    end = s.rfind('"')
    arr = json.loads(s[:end].replace('\\"', '"'))
    return {e["h"]: (e.get("k", ""), e.get("i", "")) for e in arr}


def api_post(cfg, path, body, keys, t):
    k, iv = keys["FZJH03"]
    key = k.encode()
    ivb = iv.encode() if iv else b"\x00" * 16
    plain = json.dumps(body, separators=(",", ":")).encode()
    pad = 16 - len(plain) % 16
    ct = AES.new(key, AES.MODE_CBC, ivb).encrypt(plain + TAG * pad)
    data = (b"FZJH03" + ct).hex().encode()
    h = build_headers(cfg, t)
    req = urllib.request.Request(domain_of(cfg) + "/api/v5/" + path, data=data, method="POST")
    for kk, vv in h.items():
        req.add_header(kk, vv)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        raw = r.read().strip()
    txt = decrypt(raw, key, ivb).decode("utf-8", "replace")
    txt = txt.rstrip("\x00").rstrip("0").rstrip("\x00")
    a = txt.find("{")
    z = txt.rfind("}")
    return json.loads(txt[a:z + 1] if a >= 0 and z > a else txt)


def rows_of(d):
    cur = d.get("data")
    for p in ("body", "list"):
        cur = cur.get(p) if isinstance(cur, dict) else None
    return cur if isinstance(cur, list) else []


def is_rate_limited(d):
    """是不是限流（20616「请求错误」）。这既不是成功也不是版本问题，冷却后必须重试。"""
    return (d or {}).get("errcode") == 20616


def post_with_retry(cfg, path, body, keys, t, tries=None):
    """请求失败（含空响应导致解析失败）自动重试。

    退避分两条线：
      - 限流 20616：按 RATE_BACKOFF（15s/45s/90s）冷却，且多给两次机会。
        这类失败是「请求太密」而不是「请求不可能成功」，等一等基本都能过。
        冷却期间还顺带换一次会话密钥：连续被限流时旧密钥也可能被判可疑。
      - 其它错误：按老规矩 3s/6s。
    限流时服务端会返回空包，api_post 会抛 JSON 解析异常，这里一并兜住。
    """
    global RATE_HITS
    last = {"errcode": -1, "errmsg": "未发起请求"}
    n = tries or RETRY
    i = 0        # 常规重试计数
    j = 0        # 限流冷却计数（独立额度，不吃掉常规重试）
    while i < n:
        try:
            d = api_post(cfg, path, body, keys, t)
            if d.get("errcode") == 0:
                return d
            last = d
        except Exception as e:
            last = {"errcode": -1, "errmsg": "%s: %s" % (type(e).__name__, e)}
        rate = is_rate_limited(last)
        if rate:
            RATE_HITS += 1
            # 限流不消耗常规重试额度：最多再给 len(RATE_BACKOFF) 次冷却机会。
            if j < len(RATE_BACKOFF):
                wait = RATE_BACKOFF[min(j, len(RATE_BACKOFF) - 1)]
                print("      ~ 限流 20616，冷却 %ds 后重试 %s（第 %d 次）" % (
                    wait, path, j + 1))
                time.sleep(wait)
                try:
                    keys = handshake(cfg, time.time())
                except Exception:
                    pass
                j += 1
                continue
            break
        if i < n - 1:
            time.sleep(3 + i * 3)
        i += 1
    return last


VERSION_ERR_HINTS = ("版本过低", "请退出重进")


def detect_hotver(cfg, keys, t, span=80):
    """自动探测服务端接受的 hotver。

    游戏每次更新 hotver 都会变（实测 18432→18443→18450→18464），写死在配置里迟早过期，
    过期后所有接口都返回「游戏版本过低」。这里从配置值起逐个往上试，命中即返回。

    注意限流（20616「请求错误」）要单独处理：它既不是成功也不是版本问题，
    冷却后重试同一个版本号，仍失败就继续试下一个，不能据此判定放弃。

    返回 (可用的 hotver, 该版本下第 1 页的响应)；探测失败返回 (None, 最后一次响应)。
    """
    base = int(cfg.get("hotver") or 0)
    last = None
    for hv in range(base, base + span):
        c = dict(cfg)
        c["hotver"] = hv
        for attempt in range(2):
            try:
                d = api_post(c, "get_board/1", {"page": 1}, keys, t)
            except Exception as e:
                d = {"errcode": -1, "errmsg": "%s" % type(e).__name__}
            code = d.get("errcode")
            msg = d.get("errmsg") or ""
            last = d
            if code == 0:
                return hv, d
            if code == 20616:      # 限流：冷却后重试同一版本
                if attempt == 0:
                    time.sleep(1.8)
                    continue
                break              # 仍限流，换下一个试试
            break                  # 其他错误，跳出内层判断
        # 只有「版本过低」才能说明是版本号不对，其它错误都不该盲目往上加
        msg = (last or {}).get("errmsg") or ""
        if not any(hint in msg for hint in VERSION_ERR_HINTS):
            if (last or {}).get("errcode") == 20616:
                time.sleep(0.8)
                continue           # 一直是限流，继续试下一个版本
            return None, last
        time.sleep(0.4)
    return None, last


def update_history(rows, now_ts, out_dir, drop=None):
    """把本次经验值记成快照，供「经验变化」页做增长对比。

    - 每次刷新记一条（带时间戳），所以两次刷新之间也能看出涨了多少
    - 距上次记录不足 5 分钟则覆盖上一条，避免误重跑产生 0 差值干扰
    - 只保留最近 8 天，且最多 60 条
    """
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "exp-history.json")

    drop = set(str(u) for u in (drop or ()))

    hist = {"snapshots": []}
    if os.path.exists(p):
        try:
            with io.open(p, encoding="utf-8") as f:
                hist = json.load(f)
        except Exception:
            hist = {"snapshots": []}

    snaps = list(hist.get("snapshots", []))
    entry = {
        "ts": int(now_ts),
        "date": bj_date(now_ts),
        "time": bj_time(now_ts, "%H:%M"),
        "exp": {str(r["userid"]): r["exp"] for r in rows if r.get("exp") is not None},
        # 榜单口径的快照：经验变化页只认 src=="profile" 的快照，
        # 这条一定会被 merge_exp.py 用档案值覆盖成 profile；覆盖不了（档案抓失败）时
        # 也不会被当成增长基准，避免「第一次抓到的榜单落后值」污染基准。
        "src": "board",
    }

    if snaps and int(now_ts) - snaps[-1].get("ts", 0) < 300:
        snaps[-1] = entry           # 5 分钟内重跑：覆盖，不留 0 差值的点
    else:
        snaps.append(entry)

    cutoff = int(now_ts) - 8 * 86400
    snaps = [s for s in snaps if s.get("ts", 0) >= cutoff][-60:]
    if drop:
        for snap in snaps:
            for u in list(snap.get("exp", {})):
                if u in drop:
                    del snap["exp"][u]

    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updatedAt": bj_time(now_ts, "%Y-%m-%d %H:%M:%S"),
                   "snapshots": snaps}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)
    return len(snaps)


def probe(cfg):
    """只做连通性验证：握手 + 拉第 1 页，不写任何文件。用于 CI 上判断出口 IP 能否访问游戏服。"""
    t = time.time()
    print("[probe] 握手…")
    try:
        keys = handshake(cfg, t)
    except Exception as e:
        print("[probe] ✗ 握手失败：%s: %s" % (type(e).__name__, e))
        return 2
    print("[probe] ✓ 握手成功")

    # 顺带验证版本号，游戏一更新 hotver 就会过期
    hv, d = detect_hotver(cfg, keys, t)
    if hv is None:
        msg = (d or {}).get("errmsg") or "无法确定可用版本号"
        print("[probe] ✗ %s" % msg)
        return 1
    if hv != int(cfg["hotver"]):
        print("[probe] 版本号需校正：%s → %s（游戏刚更新，属正常）" % (cfg["hotver"], hv))

    rs = rows_of(d)
    print("[probe] get_board/1 -> errcode=%s errmsg=%s rows=%d" % (
        d.get("errcode"), d.get("errmsg") or "-", len(rs)))
    if d.get("errcode") == 0 and rs:
        print("[probe] ✓ 第一名：%s（%s）" % (
            rs[0].get("name"), rs[0].get("real_menpai") or rs[0].get("menpai")))
        return 0
    print("[probe] ✗ 数据未取到")
    return 1


def load_hidden():
    """读取 data/hidden.json → {uid: set(server)}；server 为空表示全部服务器"""
    path = os.path.join(BASE_DIR, "data", "hidden.json")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with io.open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return out
    for x in (d.get("players") or []):
        uid = str(x.get("uid") or "").strip()
        if not uid:
            continue
        out.setdefault(uid, set())
        if x.get("server"):
            out[uid].add(str(x["server"]))
    return out


def hidden_uids_for(hidden, server_key):
    """该分区下需要完全隐藏的 uid 集合"""
    return set(u for u, servers in hidden.items()
               if not servers or server_key in servers)


def load_shadow():
    """读取 data/hidden.json 里带 "shadow": true 的玩家 → {uid: set(server)}

    影子玩家和普通隐藏玩家一样，照旧从公开榜单 / 昵称索引里整条剔除；
    区别是他们自己用口令打开网页时，前端会按「原始名次」把这些行插回榜单，
    让本人看到自己（含真实名次）。别人不带口令，看到的还是剔除后的榜单。

    名单只有一份真源（data/hidden.json），这里只多认一个 shadow 标记，
    避免再维护一份影子名单跟 hidden.json 漂移。
    """
    path = os.path.join(BASE_DIR, "data", "hidden.json")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with io.open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return out
    players = d.get("players")
    if not isinstance(players, list):
        return out
    for x in players:
        if not isinstance(x, dict) or not x.get("shadow"):
            continue
        uid = str(x.get("uid") or "").strip()
        if not uid:
            continue
        out.setdefault(uid, set())
        if x.get("server"):
            out[uid].add(str(x["server"]))
    return out


def shadow_uids_for(shadow, server_key):
    """该分区下的影子玩家 uid 集合"""
    return set(u for u, servers in shadow.items()
               if not servers or server_key in servers)


SHADOW_PATH = os.path.join(BASE_DIR, "data", "shadow.json")


def read_shadow():
    """读 data/shadow.json（不存在或坏了都返回空结构，绝不抛）"""
    try:
        with io.open(SHADOW_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def drop_shadow_server(server_key):
    """该分区已无影子玩家：把旧记录从 data/shadow.json 摘掉，返回是否真的删了。"""
    doc = read_shadow()
    servers = doc.get("servers")
    if not isinstance(servers, dict) or server_key not in servers:
        return False
    servers.pop(server_key, None)
    doc["servers"] = servers
    tmp = SHADOW_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SHADOW_PATH)
    return True


def write_shadow_server(server_key, rows, board_total, t):
    """把该分区的影子行写进 data/shadow.json，其它分区原样保留。

    rows 必须是「从榜单剔除隐藏玩家之前」抄下来的原始行，rank 就是游戏原始名次。
    这里只负责榜单侧字段；经验 / 等级由 merge_exp.py 用档案值覆盖，
    与公开榜完全同一个口径（否则影子榜的经验会和别人对不上）。

    为什么单独一个文件而不是塞进 gaoshoubang.json：网页是纯静态的，
    任何放在 data/ 下的东西都能被直接 GET 到。影子名单本身在 hidden.json 里
    已经公开写着，所以这里不新增暴露面；真正的门槛是前端只在带口令时才读它。
    """
    doc = read_shadow()
    servers = doc.get("servers")
    if not isinstance(servers, dict):
        servers = {}
    prev = {}
    for x in ((servers.get(server_key) or {}).get("rows") or []):
        try:
            prev[str(x.get("userid"))] = int(x.get("rank"))
        except (TypeError, ValueError):
            pass

    out_rows = []
    for x in rows:
        y = dict(x)
        try:
            cur = int(y.get("rank"))
        except (TypeError, ValueError):
            cur = None
        pr = prev.get(str(y.get("userid")))
        y["prevRank"] = pr
        y["delta"] = (pr - cur) if (pr and cur) else None
        out_rows.append(y)

    servers[server_key] = {
        "server": server_key,
        "updatedAt": bj_time(t, "%Y-%m-%d %H:%M:%S"),
        "updatedTs": int(t),
        "boardTotal": int(board_total),
        "rows": out_rows,
    }
    doc["servers"] = servers
    doc["updatedAt"] = bj_time(t, "%Y-%m-%d %H:%M:%S")
    doc["updatedTs"] = int(t)

    os.makedirs(os.path.dirname(SHADOW_PATH), exist_ok=True)
    tmp = SHADOW_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SHADOW_PATH)
    return len(out_rows)


def load_hidden_fields():
    """读取 data/hidden-fields.json → {uid: (set(server), set(field))}

    与 hidden.json 的「整条剔除」不同：这里的人照样出现在榜单、档案、查询结果里，
    只是把指定字段（skills 武学列表 / prepared 准备位 / newSkills 近期新增）藏起来。
    server 为空表示所有分区。
    """
    path = os.path.join(BASE_DIR, "data", "hidden-fields.json")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with io.open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return out
    for x in (d.get("players") or []):
        uid = str(x.get("uid") or "").strip()
        if not uid:
            continue
        servers, fields = out.setdefault(uid, (set(), set()))
        if x.get("server"):
            servers.add(str(x["server"]))
        for k in (x.get("hide") or []):
            if str(k).strip():
                fields.add(str(k).strip())
    return out


def hidden_fields_for(hidden_fields, server_key):
    """该分区下需要字段级隐藏的 {uid: set(field)}"""
    out = {}
    for uid, (servers, fields) in hidden_fields.items():
        if not servers or server_key in servers:
            if fields:
                out[uid] = set(fields)
    return out


def load_servers():
    """返回服务器列表：[{key,name,channel,uuid,account,ver,hotver,device}]

    来源优先级：
      1) 环境变量 FZJH_SERVERS（JSON 数组，CI 用，一个 Secret 装全部服务器）
      2) config.json 的 servers 字段
      3) config.json 顶层单套凭据（旧格式，兼容）
    """
    cfg = load_cfg()
    raw = os.environ.get("FZJH_SERVERS")
    items = None
    if raw:
        try:
            data = json.loads(raw)
        except Exception as e:
            raise SystemExit("FZJH_SERVERS 不是合法 JSON：%s" % e)
        # 兼容两种写法：直接贴数组，或把整个 config.json 贴进来
        if isinstance(data, dict):
            items = data.get("servers") or []
            if not items:
                raise SystemExit("FZJH_SERVERS 里没有 servers 字段")
            for k in ("hotver", "ver", "device"):
                if data.get(k) and not cfg.get(k):
                    cfg[k] = data[k]
        else:
            items = data
    elif isinstance(cfg.get("servers"), list):
        items = cfg["servers"]

    if not items:
        items = [{
            "key": cfg.get("channel", "default"),
            "name": cfg.get("name") or "默认分区",
            "channel": cfg.get("channel", "taptap"),
            "uuid": cfg.get("uuid"),
            "account": cfg.get("account"),
            "default": True,
        }]

    out = []
    seen = set()
    for i, s in enumerate(items):
        key = str(s.get("key") or s.get("channel") or ("s%d" % i)).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "key": key,
            "name": s.get("name") or key,
            "channel": s.get("channel") or key,
            "uuid": s.get("uuid"),
            "account": s.get("account"),
            "ver": s.get("ver") or cfg.get("ver", "2.1.02"),
            "hotver": s.get("hotver") or cfg.get("hotver"),
            "device": s.get("device", cfg.get("device", "")),
            "default": bool(s.get("default")) or i == 0,
            "maxRank": s.get("maxRank"),
            # 只进昵称索引、不进榜单的名次上限（例如其他服：榜前 50、索引前 100）
            "indexRank": s.get("indexRank"),
            # 协议层覆盖项：iOS 分区必须同时给 domain / platform / channel=ios
            "domain": s.get("domain"),
            "platform": s.get("platform"),
        })

    for s in out:
        miss = [k for k in ("uuid", "account", "hotver") if not s.get(k)]
        if miss:
            raise SystemExit("服务器 %s 缺少配置：%s" % (s["key"], "、".join(miss)))
    return out


def server_cfg(srv):
    """把服务器配置转成 build_headers/handshake 需要的 cfg 结构"""
    return {
        "uuid": srv["uuid"],
        "account": int(srv["account"]) if str(srv["account"]).isdigit() else srv["account"],
        "hotver": srv["hotver"],
        "ver": srv.get("ver", "2.1.02"),
        "channel": srv["channel"],
        "device": srv.get("device", ""),
        # 只有 iOS 这类非安卓分区才会带这两项，缺省即安卓默认域
        "domain": srv.get("domain"),
        "platform": srv.get("platform"),
    }


def server_dir(key):
    return os.path.join(BASE_DIR, "data", "servers", key)


def write_index(servers):
    """给前端用的服务器清单（不含任何凭据）"""
    items = [{"key": s["key"], "name": s["name"], "default": s["default"]} for s in servers]
    p = os.path.join(BASE_DIR, "data", "servers", "index.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"servers": items}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)


def fetch_server(srv, board, max_pages):
    """抓单个服务器：榜单 + 经验快照，写到 data/servers/<key>/"""
    cfg = server_cfg(srv)
    out_dir = server_dir(srv["key"])
    os.makedirs(out_dir, exist_ok=True)
    t = time.time()
    print("[1/3] 握手…")
    keys = handshake(cfg, t)

    # 游戏更新后旧 hotver 会报「游戏版本过低」，这里自动往上探测一次并纠正
    hv, _first = detect_hotver(cfg, keys, t)
    if hv is None:
        print("      ✗ 版本号无法确定（可能维护中或接口异常），本轮跳过")
        return 1
    if hv != int(cfg["hotver"]):
        print("      版本号自动校正：%s → %s（游戏刚更新）" % (cfg["hotver"], hv))
        cfg["hotver"] = hv
        keys = handshake(cfg, t)      # 换版本号后重新握手，保证会话一致
    print("      会话密钥 FZJH03 = %s" % keys["FZJH03"][0])

    print("[2/3] 抓取 %s（每页 10 条，间隔 %.1fs）…" % (BOARD_CN.get(board, board), SLEEP))
    max_rank = srv.get("maxRank")
    # 只进索引、不进榜单的名次上限：需要多抓几页，抓完再把 50 之后的部分单独存
    idx_rank = srv.get("indexRank")
    if board != 1:
        # maxRank / indexRank 是「高手榜 + 昵称索引」的口径，只对 board=1 有意义。
        # 名人堂每区固定 10 行，套用 maxRank 会把它截成更少的人，
        # 而 index-extra.json 是高手榜专属，也不该由别的榜来写/删。
        max_rank, idx_rank = None, None
        limit = 0
    else:
        limit = max(int(max_rank or 0), int(idx_rank or 0))
    rows, seen = [], set()
    stale = 0
    err_page = None
    for p in range(1, max_pages + 1):
        d = post_with_retry(cfg, "get_board/%d" % board, {"page": p}, keys, t)
        rs = rows_of(d)
        if d.get("errcode") != 0:
            # 翻页中途报错 ≠ 榜单到头：此时手上可能只有前一两页，写盘会把榜单
            # 截成 10~20 人；下游 fetch_profiles 还会按这份榜单删掉其余档案。
            # 整轮放弃（保持上一版不动），等下一轮 cron 重试。
            err_page = (p, d.get("errcode"))
            print("      ✗ 第 %d 页报错（errcode=%s）" % (p, d.get("errcode")))
            break
        if not rs:
            print("      第 %d 页结束（没有更多数据）" % p)
            break
        added = 0
        for r in rs:
            uid = r.get("userid")
            if uid and uid not in seen:
                seen.add(uid)
                rows.append(r)
                added += 1
        print("      第 %2d 页 +%2d 条  累计 %d" % (p, added, len(rows)))
        # 抓满 max(maxRank, indexRank) 名就停（例如其他服：榜 50、索引 100）
        if limit and len(rows) >= limit:
            rows = rows[:limit]
            print("      已抓满前 %d 名，停止%s" % (
                limit, "（其中 %d 名只进索引）" % (limit - int(max_rank)) if idx_rank and limit > int(max_rank or 0) else ""))
            break
        stale = stale + 1 if added == 0 else 0
        if stale >= 2:
            print("      连续无新增，停止")
            break
        # 本轮撞过限流就把页间隔翻倍：刚恢复时最容易第二次超限。
        time.sleep(SLEEP * (2 if RATE_HITS else 1))

    if err_page:
        # 抓到一半报错：宁可整轮作废，也不要写一份残缺榜单。
        # 残缺榜单会让「经验快照」少人、让下榜清理误删档案，恢复起来比重抓贵得多。
        print("!! 第 %d 页报错，本轮作废，保留上一版文件不动（已抓到 %d 条不入库）"
              % (err_page[0], len(rows)))
        return 1

    if not rows:
        print("!! 没抓到任何数据，保留上一版文件不动")
        return 1

    out_rows = []
    for i, r in enumerate(rows, 1):
        out_rows.append({
            "rank": i,
            "userid": r.get("userid"),
            "name": r.get("name") or "",
            "menpai": r.get("real_menpai") or r.get("menpai") or "",
            "lv": r.get("lv"),
            "kongfu": round(r.get("kongfu") or 0, 2),
            "exp": r.get("exp"),
            "money": r.get("money"),
            "yueli": r.get("yueli"),
            "xiayi": r.get("xiayi"),
            "looks": r.get("looks"),
            "fuyuan": r.get("fuyuan"),
            "age": r.get("age"),
            "sex": r.get("sex"),
            "wuxing": r.get("wuxing"),
            "inheritCount": r.get("inheritCount"),
        })

    # 隐私名单：整条从榜单剔除（不是只遮数值）
    # 注意这里是 hidden.json 里的「全部」该区玩家（含 shadow:true 的影子玩家），
    # 名人堂（board=4）也按这个全集剔除，不做影子豁免。
    hidden = load_hidden()
    drop = hidden_uids_for(hidden, srv["key"])
    # 影子玩家（hidden.json 里带 "shadow": true）要在剔除之前抄一份原始行：
    # 此时 rank 还是游戏原始名次，剔除后被重排的 rank 已经不是真实名次了。
    shadow_uids = shadow_uids_for(load_shadow(), srv["key"])
    shadow_rows = [dict(x) for x in out_rows if str(x["userid"]) in shadow_uids]
    board_total_all = len(rows)
    if drop:
        keep = [x for x in out_rows if str(x["userid"]) not in drop]
        if len(keep) != len(out_rows):
            print("      已从榜单移除隐藏玩家 %d 位" % (len(out_rows) - len(keep)))
        out_rows = keep
        for i, x in enumerate(out_rows, 1):
            x["rank"] = i

    # 榜单只保留前 maxRank 名；maxRank 之后的部分另存 index-extra.json，
    # 仅供 build_lookup_index.py 生成昵称索引用（页面上看不到这些人）。
    board_rows = out_rows[: int(max_rank)] if max_rank else out_rows
    extra_rows = []
    if idx_rank and int(idx_rank) > len(board_rows):
        extra_rows = out_rows[len(board_rows): int(idx_rank)]
    for i, x in enumerate(board_rows, 1):
        x["rank"] = i

    # 排名变化：与上一版对比（按榜取各自的文件，名人堂读的是上一版 hall.json）
    cur_path = os.path.join(out_dir, BOARD_FILE.get(board, "board%d.json" % board))
    prev_rank = {}
    has_prev = os.path.exists(cur_path)
    if has_prev:
        try:
            with io.open(cur_path, encoding="utf-8") as f:
                for x in json.load(f).get("rows", []):
                    prev_rank[x["userid"]] = x["rank"]
        except Exception:
            pass
    for x in board_rows:
        pr = prev_rank.get(x["userid"])
        x["prevRank"] = pr
        x["delta"] = (pr - x["rank"]) if pr else None

    payload = {
        "board": BOARD_CN.get(board, "榜%d" % board),
        "boardType": board,
        "updatedAt": bj_time(t, "%Y-%m-%d %H:%M:%S"),
        "updatedTs": int(t),
        "hasPrev": has_prev,
        "total": len(board_rows),
        "rows": board_rows,
    }
    tmp = cur_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, cur_path)

    # 索引专用名单：字段精简，只留搜索/展示要用的
    # 这是高手榜专属文件（build_lookup_index.py 按 maxRank 之后的名次建索引），
    # 别的榜既不写也不删，否则会把高手榜那份索引清空。
    ip = os.path.join(out_dir, "index-extra.json")
    if board != 1:
        pass
    elif idx_rank:
        # 本轮没抓满 indexRank（限流/中途断页）时不要写空表：
        # 那会把索引从 100 名直接砍到 maxRank，而且没有任何报错。
        # 宁可用上一版（最多多出几个已下榜的人），也不能莫名少一半。
        if len(out_rows) < int(idx_rank) and os.path.exists(ip):
            print("      本轮只抓到 %d 名（目标 %d），保留上一版索引名单不动" % (
                len(out_rows), int(idx_rank)))
        else:
            ipay = {
                "updatedAt": payload["updatedAt"],
                "updatedTs": int(t),
                "from": len(board_rows) + 1,
                "to": len(board_rows) + len(extra_rows),
                "rows": [{
                    "rank": x["rank"],
                    "userid": x["userid"],
                    "name": x["name"],
                    "menpai": x["menpai"],
                    "lv": x["lv"],
                    "exp": x["exp"],
                } for x in extra_rows],
            }
            itmp = ip + ".tmp"
            with io.open(itmp, "w", encoding="utf-8") as f:
                json.dump(ipay, f, ensure_ascii=False, indent=1)
            os.replace(itmp, ip)
    elif os.path.exists(ip):
        # 分区不再配置 indexRank 时，删掉上一轮留下的名单，避免索引里残留已下榜的人
        try:
            os.remove(ip)
        except OSError:
            pass

    # 快照里保留影子玩家（drop 减去影子）：
    # 他们本来就在公开榜时代进过快照，用户要求别把历史抹掉；
    # 他们的档案现在也照抓，merge_exp 会继续沿用上一轮的值，不会断档。
    # exp-history.json 记的是「高手榜名次的经验趋势」，名人堂（阅历榜）不参与，
    # 否则会把同一批人的经验快照按名人堂名次重写一遍。
    n_hist = None
    if board == 1:
        n_hist = update_history(board_rows, t, out_dir, drop - shadow_uids)

    # 影子榜：给被剔除的隐藏玩家单独留一份「原始名次」的行，本人带口令打开
    # 网页时才由前端把这些行插回榜单（别人不带口令看不到）。
    # 用的是剔除前抄下来的 shadow_rows，rank 才是游戏真实名次。
    if board != 1:
        import_shadow = False   # 影子榜（data/shadow.json）只属于高手榜
    else:
        import_shadow = True
    if import_shadow and shadow_uids:
        n_sh = write_shadow_server(srv["key"], shadow_rows, board_total_all, t)
        print("      影子榜 %d 人（原始榜共 %d 人，含未公开的）" % (n_sh, board_total_all))
    elif import_shadow and drop_shadow_server(srv["key"]):
        print("      影子榜：本分区已无影子玩家，清掉旧记录")

    print("[3/3] 已写入 %s" % cur_path)
    print("      榜单 %d 人  |  更新于 %s" % (len(board_rows), payload["updatedAt"]))
    if idx_rank:
        print("      索引名单 %d 人（第 %d–%d 名）" % (
            len(extra_rows), len(board_rows) + 1, len(board_rows) + len(extra_rows)))
    if n_hist is not None:
        print("      经验快照：%d 条在库（保留最近 8 天）" % n_hist)
    # 高手榜的第三列数值是武学；名人堂是江湖阅历（yueli），别在日志里叫错名字。
    metric = "阅历" if board == 4 else "武学"
    for x in board_rows[:3]:
        val = x["yueli"] if board == 4 else x["kongfu"]
        print("      #%d %s（%s）%s %s" % (x["rank"], x["name"], x["menpai"], metric, val))
    return 0



def main():
    args = sys.argv[1:]
    servers = load_servers()

    # --server 先解析出来，probe 和抓取都用同一份目标列表
    # 支持逗号分隔多个分区（例如一条定时任务同时跑 三个区：「--server taptap_2,taptap_3」）
    if "--server" in args:
        want = args[args.index("--server") + 1]
        keys = [x.strip() for x in want.split(",") if x.strip()]
        targets = [s for s in servers if s["key"] in keys]
        missing = [k for k in keys if k not in [s["key"] for s in servers]]
        if missing or not targets:
            raise SystemExit("没有这些服务器：%s（可选：%s）" % (
                "、".join(missing or keys), "、".join(s["key"] for s in servers)))
    else:
        targets = servers

    if "--probe" in args:
        ok = True
        for i, s in enumerate(targets, 1):
            print("--- [%d/%d] %s（%s）---" % (i, len(targets), s["name"], s["channel"]))
            # 打出来方便在 CI 日志里确认 Secret 里的 maxRank 有没有生效
            print("[probe] 抓取上限：%s" % (
                ("前 %s 名" % s["maxRank"]) if s.get("maxRank") else "不限（全量）"))
            if probe(server_cfg(s)) != 0:
                ok = False
            if i < len(targets):
                time.sleep(1.5)
        return 0 if ok else 1

    # probe 是只读的，只有真要抓数据时才刷新分区清单
    write_index(servers)

    board = 1
    max_pages = 40
    if "--board" in args:
        board = int(args[args.index("--board") + 1])
    if "--max-pages" in args:
        max_pages = int(args[args.index("--max-pages") + 1])

    rc = 0
    for i, s in enumerate(targets, 1):
        print("\n===== [%d/%d] %s · %s =====" % (i, len(targets), s["name"], s["channel"]))
        try:
            if fetch_server(s, board, max_pages) != 0:
                rc = 1
        except Exception as e:
            print("!! 抓取失败：%s: %s" % (type(e).__name__, e))
            rc = 1
        if i < len(targets):
            time.sleep(2)
    return rc


if __name__ == "__main__":
    sys.exit(main())

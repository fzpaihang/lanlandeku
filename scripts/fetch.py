# -*- coding: utf-8 -*-
"""放置江湖 · 高手榜抓取（自包含，不依赖任何外部项目）

链路（逆向结论见原项目 README 第 8 章）：
  1) POST /api/service/exchange_publickey  用设备 uuid 换本会话密钥（JHHU02 容器，密钥静态）
  2) POST /api/v5/get_board/<boardType> {"page":N}  用 JHHU03 会话密钥加密请求 / 解密响应
  3) 响应尾部填充字符是 '0'，需剥掉才能当 JSON 解析

用法:
  python fetch.py                # 抓高手榜全部页 -> data/gaoshoubang.json
  python fetch.py --board 1      # 指定榜单类型（1=高手榜）
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
SALT = b"ed24bd36b1a87f60bebaca65538a590c"
K02 = b"cbIhHHuYQIJ1JkwlLupIvNIvdQDfNxSF"   # JHHU02，握手响应用
IV02 = b"PcIQIZifRalhZ88n"
TAG = b"0"
SLEEP = 0.6          # 页间隔：太快会触发 20616 请求错误（限速）
RETRY = 3

BOARD_CN = {1: "高手榜"}

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

    missing = [k for k in ("uuid", "account", "hotver") if not cfg.get(k)]
    if missing:
        raise SystemExit("缺少配置：%s（可用 config.json 或 FZJH_* 环境变量提供）" % "、".join(missing))
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


def build_headers(cfg, t):
    nouce = make_nouce()
    return {
        "uuid": cfg["uuid"],
        "userid": str(cfg["account"]),
        "sig": make_sig(nouce, t),
        "time": "%.14g" % float(t),
        "nouce": nouce,
        "device": cfg.get("device", ""),
        "ver": cfg.get("ver", "2.1.02"),
        "hotver": str(cfg["hotver"]),
        "platform": "android",
        "timezone": "8",
        "channel": cfg.get("channel", "taptap"),
        "package": "",
        "age": "-2",
        "pkname": "com.xhtt.app.fzjh",
        "pksig": "",
    }


def decrypt(raw, key, iv):
    body = bytes(bytearray.fromhex(raw.decode()))[6:]
    return AES.new(key, AES.MODE_CBC, iv).decrypt(body[: len(body) // 16 * 16])


def handshake(cfg, t):
    h = build_headers(cfg, t)
    req = urllib.request.Request(DOMAIN + "/api/service/exchange_publickey", data=b"", method="POST")
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
    req = urllib.request.Request(DOMAIN + "/api/v5/" + path, data=data, method="POST")
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


def post_with_retry(cfg, path, body, keys, t):
    for i in range(RETRY):
        d = api_post(cfg, path, body, keys, t)
        if d.get("errcode") == 0:
            return d
        if i < RETRY - 1:
            time.sleep(3)
    return d


def update_history(rows, now_ts):
    """把本次经验值记成快照，供「经验变化」页做增长对比。

    - 每次刷新记一条（带时间戳），所以两次刷新之间也能看出涨了多少
    - 距上次记录不足 5 分钟则覆盖上一条，避免误重跑产生 0 差值干扰
    - 只保留最近 8 天，且最多 60 条
    """
    p = os.path.join(BASE_DIR, "data", "exp-history.json")
    lt = time.localtime(now_ts)

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
        "date": time.strftime("%Y-%m-%d", lt),
        "time": time.strftime("%H:%M", lt),
        "exp": {str(r["userid"]): r["exp"] for r in rows if r.get("exp") is not None},
    }

    if snaps and int(now_ts) - snaps[-1].get("ts", 0) < 300:
        snaps[-1] = entry           # 半小时内重跑：覆盖，不留 0 差值的点
    else:
        snaps.append(entry)

    cutoff = int(now_ts) - 8 * 86400
    snaps = [s for s in snaps if s.get("ts", 0) >= cutoff][-60:]

    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updatedAt": time.strftime("%Y-%m-%d %H:%M:%S", lt),
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

    d = post_with_retry(cfg, "get_board/1", {"page": 1}, keys, t)
    rs = rows_of(d)
    print("[probe] get_board/1 -> errcode=%s errmsg=%s rows=%d" % (
        d.get("errcode"), d.get("errmsg") or "-", len(rs)))
    if d.get("errcode") == 0 and rs:
        print("[probe] ✓ 第一名：%s（%s）" % (
            rs[0].get("name"), rs[0].get("real_menpai") or rs[0].get("menpai")))
        return 0
    print("[probe] ✗ 数据未取到")
    return 1


def main():
    cfg = load_cfg()
    args = sys.argv[1:]
    if "--probe" in args:
        return probe(cfg)

    board = 1
    max_pages = 40
    if "--board" in args:
        board = int(args[args.index("--board") + 1])
    if "--max-pages" in args:
        max_pages = int(args[args.index("--max-pages") + 1])

    t = time.time()
    print("[1/3] 握手…")
    keys = handshake(cfg, t)
    print("      会话密钥 FZJH03 = %s" % keys["FZJH03"][0])

    print("[2/3] 抓取 %s（每页 10 条，间隔 %.1fs）…" % (BOARD_CN.get(board, board), SLEEP))
    rows, seen = [], set()
    stale = 0
    for p in range(1, max_pages + 1):
        d = post_with_retry(cfg, "get_board/%d" % board, {"page": p}, keys, t)
        rs = rows_of(d)
        if d.get("errcode") != 0 or not rs:
            print("      第 %d 页结束（errcode=%s）" % (p, d.get("errcode")))
            break
        added = 0
        for r in rs:
            uid = r.get("userid")
            if uid and uid not in seen:
                seen.add(uid)
                rows.append(r)
                added += 1
        print("      第 %2d 页 +%2d 条  累计 %d" % (p, added, len(rows)))
        stale = stale + 1 if added == 0 else 0
        if stale >= 2:
            print("      连续无新增，停止")
            break
        time.sleep(SLEEP)

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
        })

    # 排名变化：与上一版对比
    cur_path = os.path.join(BASE_DIR, "data", "gaoshoubang.json")
    prev_rank = {}
    has_prev = os.path.exists(cur_path)
    if has_prev:
        try:
            with io.open(cur_path, encoding="utf-8") as f:
                for x in json.load(f).get("rows", []):
                    prev_rank[x["userid"]] = x["rank"]
        except Exception:
            pass
    for x in out_rows:
        pr = prev_rank.get(x["userid"])
        x["prevRank"] = pr
        x["delta"] = (pr - x["rank"]) if pr else None

    payload = {
        "board": BOARD_CN.get(board, "榜%d" % board),
        "boardType": board,
        "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "updatedTs": int(t),
        "hasPrev": has_prev,
        "total": len(out_rows),
        "rows": out_rows,
    }
    tmp = cur_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, cur_path)

    n_hist = update_history(out_rows, t)

    print("[3/3] 已写入 %s" % cur_path)
    print("      共 %d 人  |  更新于 %s" % (len(out_rows), payload["updatedAt"]))
    print("      经验快照：%d 条在库（保留最近 8 天）" % n_hist)
    for x in out_rows[:3]:
        print("      #%d %s（%s）武学 %s" % (x["rank"], x["name"], x["menpai"], x["kongfu"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

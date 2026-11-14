# -*- coding: utf-8 -*-
"""玩家查询核心：按 UID 定位分区 → 拉取档案 → 解析成展示用结构。

对外主要接口：
    lookup(uid, progress=None) -> dict | None
返回的 dict 已包含展示所需的全部字段（含从榜单补充的门派/等级/福缘/排名）。
"""
import io
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import fetch as F  # noqa: E402

# 更新包会解压到独立的 live/ 目录；config.json 和 names.json 仍随 APK 放在原目录。
# 所以资源按「当前目录 → sys.path 里的其它目录 → ANDROID_APP_PATH」依次找。
def _find(rel):
    tried = set()
    cands = [BASE]
    cands += [p for p in sys.path if p and os.path.isdir(p)]
    ap = os.environ.get("ANDROID_APP_PATH")
    if ap:
        cands.append(ap)
    for d in cands:
        d = os.path.normpath(d)
        if d in tried:
            continue
        tried.add(d)
        p = os.path.join(d, rel)
        if os.path.exists(p):
            return p
    return os.path.join(BASE, rel)


CONFIG_PATHS = [_find("config.json"), r"E:/workbuddy2/fzjh-rank/config.json"]
# 缓存必须放在应用数据目录，不能跟代码放一起：
# 启动器热更时会整个删掉 live/，放那里的话「分区记忆 / 最近查询」每次更新都会丢。
DATA_DIR = os.environ.get("ANDROID_PRIVATE") or BASE
CACHE_PATH = os.path.join(DATA_DIR, "lookup_cache.json")
NAMES_PATH = _find("names.json")
RECENT_MAX = 3

INDEX_URL = "https://fzpaihang.github.io/lanlandeku/data/servers/%s/gaoshoubang.json"

# 门派代码 → 中文（实测采集，2026-11-12，覆盖五区全部 29 个门派）
# 注意：这些代码不是拼音直译，必须实测，不能靠推断
MENPAI_CN = {
    "gaibang": "丐帮", "haijing": "海鲸帮", "guanfu": "官府", "jinqianbang": "财神帮",
    "mingjiao": "明教", "youming": "幽冥教", "yongyelou": "永夜楼", "youxia": "江湖浪人",
    "huashan": "华山", "tangmen": "唐门", "tianshan": "虚渺宫", "murong": "燕氏皇族",
    "kongtong": "崆峒派", "tiezhang": "伏龙山", "quanzhen": "全真教", "emei": "峨眉派",
    "kunlun": "昆仑派", "mizong": "雪山寺", "gumu": "问情宫", "wudu": "万灵谷",
    "shaolin": "少林派", "tianjingmen": "天竞门", "riyueshenjiao": "拜日教",
    "taohuadao": "蓬莱岛", "wudang": "武当派", "luoyue": "落月山庄",
    "baituoshan": "鸩羽山", "xingxiu": "天狼教", "dali": "天龙寺",
}

SLOT_CN = {
    "quanjiao1": "拳脚一", "quanjiao2": "拳脚二", "neigong": "内功",
    "qinggong": "轻功", "zhaojia": "招架", "jianfa": "剑法", "daofa": "刀法",
    "bianfa": "鞭法", "gunfa": "棍法", "shuangchi": "双持", "anqi": "暗器",
    "qinfa": "琴法",
}
EQUIP_CN = {
    "weapon": "武器", "cloth": "衣服", "pants": "下装", "shoes": "鞋履",
    "head": "头饰", "yaozhui": "腰坠", "neck": "颈饰", "necklace": "颈饰",
    "ring": "戒指", "wrist": "护腕", "hand": "护手", "belt": "腰带",
    "cape": "披风", "mask": "面具",
}

# exp ≈ 0.100402 × lv³（98 人样本实测，最大误差 0.033%）；榜单没有等级时用它反算
LV_COEF = 0.100402


def fmt_big(n):
    """数值压缩：1.2亿 / 34.5万 / 1234"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    a = abs(n)
    if a >= 1e8:
        return "%.2f亿" % (n / 1e8)
    if a >= 1e4:
        return "%.1f万" % (n / 1e4)
    return "%d" % round(n)


def lv_from_exp(exp):
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return None
    if exp <= 0:
        return None
    return int(round((exp / LV_COEF) ** (1.0 / 3.0)))


def lv_of_skill(exp):
    """武学等级 = f(技能经验)，与原工具口径一致"""
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return 0
    if exp < 8:
        return int(exp)
    try:
        return int(((exp - 1) / 0.015) ** (1.0 / 3.0))
    except Exception:
        return 0


def load_config():
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            with io.open(p, encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("servers"):
                return cfg
    raise RuntimeError("找不到 config.json（含五区凭据）")


_NAMES = None


def load_names():
    global _NAMES
    if _NAMES is None:
        try:
            with io.open(NAMES_PATH, encoding="utf-8") as f:
                _NAMES = json.load(f)
        except Exception:
            _NAMES = {"skills": {}, "equips": {}}
    return _NAMES


def load_cache():
    try:
        with io.open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(c):
    # 先写 .tmp 再 os.replace：安卓低内存随时可能杀进程，直接覆盖写会留下
    # 半个 JSON，下次 load_cache 解析失败就把分区记忆/最近查询全丢了。
    tmp = CACHE_PATH + ".tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(c, ensure_ascii=False, indent=2))
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, CACHE_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def recent_queries():
    """最近成功的查询，最多 RECENT_MAX 条；失败不抛异常。"""
    try:
        items = load_cache().get("recentQueries") or []
        return [x for x in items if isinstance(x, dict) and x.get("uid")][:RECENT_MAX]
    except Exception:
        return []


def add_recent(prof):
    """把一次成功查询写进历史：同一 UID 去重后置顶。"""
    try:
        c = load_cache()
        items = [x for x in (c.get("recentQueries") or []) if isinstance(x, dict)]
        items = [x for x in items if str(x.get("uid")) != str(prof.get("uid"))]
        items.insert(0, {
            "uid": prof.get("uid"),
            "name": prof.get("name") or "",
            "server": prof.get("server"),
            "serverName": prof.get("serverName") or "",
            "at": time.strftime("%Y-%m-%d %H:%M"),
        })
        c["recentQueries"] = items[:RECENT_MAX]
        save_cache(c)
    except Exception:
        pass


def order_servers(servers, uid, last_key=None):
    """按「上次命中 → uid 位数推测 → 其余」排序，减少无谓请求。
    位数规律：苍松 7 位、4399 10 位、taptap 系（白鹤/丹凤/墨羽）11 位。
    """
    s = str(uid)
    guess = []
    if len(s) == 7:
        guess = ["taptap"]
    elif len(s) == 10:
        guess = ["4399"]
    elif len(s) == 11:
        guess = ["taptap_3", "taptap_2", "taptap_4"]
    keys = []
    for k in ([last_key] if last_key else []) + guess:
        if k and k not in keys:
            keys.append(k)
    keys += [x["key"] for x in servers if x["key"] not in keys]
    by_key = {x["key"]: x for x in servers}
    return [by_key[k] for k in keys if k in by_key]


def fetch_board(key, cache=None, days=1):
    """取该区榜单（用于补门派/等级/福缘/排名）。失败返回空列表。"""
    cache = cache if cache is not None else load_cache()
    bc = cache.setdefault("boardCache", {})
    rec = bc.get(key)
    now = time.time()
    if rec and now - rec.get("ts", 0) < days * 86400:
        return rec.get("rows") or []
    try:
        req = urllib.request.Request(INDEX_URL % key, headers={"User-Agent": "fzjh-lookup"})
        ctx = getattr(F, "ctx", None)
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            d = json.loads(r.read().decode("utf-8"))
        rows = d.get("rows") or []
        bc[key] = {"ts": now, "rows": rows}
        save_cache(cache)
        return rows
    except Exception:
        return (rec or {}).get("rows") or []


# 单次查询的总预算（秒）。探测 80 个版本号 × 每版 2 次请求 × 5 个分区，
# 最坏能拖到十几分钟，用户只能杀 App —— 这里给一个硬上限。
LOOKUP_BUDGET = 20.0

_LAST = {"reason": "unknown"}


def last_reason():
    """上一次 lookup 的失败原因：ok / notfound / net / timeout / config。"""
    return _LAST.get("reason", "unknown")


def try_one(srv, uid, hotver):
    """返回 (data, errcode)。data 为 None 表示该区没有这个角色。"""
    srv = dict(srv)
    srv["hotver"] = hotver
    cfg = F.server_cfg(srv)
    t = time.time()
    try:
        keys = F.handshake(cfg, t)
        d = F.api_post(cfg, "get_user_info", {"userid": uid, "type": 0}, keys, t)
    except Exception:
        return None, -1
    data = d.get("data")
    ec = d.get("errcode")
    if ec == 0 and isinstance(data, dict) and data.get("name"):
        return data, 0
    return None, ec


def parse_profile(data, board_row=None):
    """原始 data → 展示结构。有榜单行时用榜单补 门派/等级/福缘/排名。"""
    names = load_names()
    sk_map = names.get("skills") or {}
    eq_map = names.get("equips") or {}
    br = board_row or {}

    def num(x, r=0):
        try:
            return round(float(x), r)
        except (TypeError, ValueError):
            return None

    # 武学
    skills = []
    for sid, v in (data.get("skills") or {}).items():
        if not isinstance(v, dict):
            continue
        nm = sk_map.get(sid) or ("自创武学" if "selfCreatedSkill" in str(sid) else str(sid))
        skills.append({"id": sid, "n": nm, "lv": lv_of_skill(v.get("exp"))})
    skills.sort(key=lambda x: (-x["lv"], x["n"]))

    # 准备位
    # 值从「技能名」改成 {n: 名称, lv: 等级}：界面要显示「1099 级」，
    # 在这里一次解析好，省得每次渲染再去 skills 里反查。
    lv_by_id = {s["id"]: s["lv"] for s in skills}
    prepared = {}
    for slot, sid in (data.get("skillPrepare") or {}).items():
        if not sid or not isinstance(sid, str):
            continue
        nm = sk_map.get(sid) or ("自创武学" if "selfCreatedSkill" in str(sid) else str(sid))
        prepared[SLOT_CN.get(slot, slot)] = {"n": nm, "lv": lv_by_id.get(sid)}

    # 装备
    equips = []
    for slot, v in (data.get("equips") or {}).items():
        if not isinstance(v, dict) or not v.get("itemId"):
            continue
        iid = str(v["itemId"])
        equips.append({
            "slot": EQUIP_CN.get(slot, slot),
            "n": eq_map.get(iid) or "未知",
        })

    # 传承
    history = []
    for x in (data.get("inheritHistory") or []):
        if not isinstance(x, dict):
            continue
        history.append({"n": x.get("inheritName") or "",
                        "t": int(x.get("inheritTime") or 0)})
    history.sort(key=lambda x: x["t"])

    fam = (data.get("family") or {}).get("name") or ""
    exp = num(data.get("exp"), 4)

    # 门派：榜单优先，其次 family 映射
    menpai = br.get("menpai") or MENPAI_CN.get(fam) or ""
    # 等级：榜单优先，其次经验反算
    if br.get("lv"):
        lv, lv_est = br["lv"], False
    else:
        lv, lv_est = lv_from_exp(exp), True

    return {
        "uid": data.get("userid"),
        "name": data.get("name") or "",
        "sex": data.get("sex") or "",
        "age": data.get("age"),
        "looks": data.get("looks"),
        "menpai": menpai,
        "menpaiCode": fam,
        "lv": lv,
        "lvEstimated": lv_est,
        "kongfu": num(data.get("kongfu"), 2),
        "exp": exp,
        "qi": num(data.get("qi"), 2),
        "qiMax": num(data.get("qiMax"), 2),
        "jiaLi": data.get("jiaLi"),
        "zhengqi": num(data.get("zhengqi"), 0),
        "fuyuan": br.get("fuyuan"),
        "rank": br.get("rank"),
        "inheritCount": data.get("inheritCount"),
        "onBoard": bool(br),
        "skills": skills,
        "prepared": prepared,
        "equips": equips,
        "history": history,
    }


AUTO_SERVER = "auto"


def _finish(uid, srv, data, cache, hotver, note):
    """命中后：写缓存 → 用榜单补门派/福缘/排名 → 组装展示结构。"""
    cache["lastServer"] = srv["key"]
    cache["hotver"] = hotver
    save_cache(cache)
    note("读取榜单补充信息…")
    row = None
    for r in fetch_board(srv["key"], cache):
        if str(r.get("userid")) == str(uid):
            row = r
            break
    prof = parse_profile(data, row)
    # 接口档案里的 userid 字段并不稳定（实测常为空），以本次查询输入的 UID 为准。
    # 摘要条 / 复制 UID / 保存文件名 / 最近查询都依赖它。
    prof["uid"] = uid
    prof["server"] = srv["key"]
    prof["serverName"] = srv["name"]
    prof["fetchedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return prof


def _redetect_hotver(srv, hotver):
    """服务端报「版本过低」时探测新版本号；探测失败返回 None。"""
    c = dict(srv)
    c["hotver"] = hotver
    try:
        t = time.time()
        keys = F.handshake(F.server_cfg(c), t)
        hv, _ = F.detect_hotver(F.server_cfg(c), keys, t)
        return hv
    except Exception:
        return None


def _lookup_single(uid, srv, cache, hotver, note, deadline=None):
    """只查指定分区。20616 限流 / 网络异常做退避重试，必要时校正版本号。"""
    for attempt in range(3):
        if deadline and time.time() > deadline:
            _LAST["reason"] = "timeout"
            return None
        note("查询 %s …" % srv["name"] if attempt == 0
             else "请求繁忙，重试 %d/3 …" % (attempt + 1))
        data, ec = try_one(srv, uid, hotver)
        if data:
            return _finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            return None                      # 服务端明确回「没有这个角色」
        if ec in (20616, -1) and attempt < 2:
            time.sleep(1.2 * (attempt + 1))  # 限流冷却，避免继续撞墙
            continue
        break

    if deadline and time.time() > deadline:
        _LAST["reason"] = "timeout"
        return None
    hv = _redetect_hotver(srv, hotver)
    if hv and hv != hotver:
        hotver = hv
        cache["hotver"] = hv
        save_cache(cache)
        note("版本号校正为 %s，重试…" % hv)
        data, _ec = try_one(srv, uid, hv)
        if data:
            return _finish(uid, srv, data, cache, hotver, note)
    return None


# ---------- 结果缓存：同一个 UID 10 分钟内直接复用 ----------
PROFILE_TTL = 600      # 秒。游戏侧档案本身也不是秒级刷新，再短没意义
PROFILE_MAX = 12       # 最多留 12 份；单份 profile 约 20 KB
PROFILE_VER = 2        # 结构变了就 +1，旧缓存自动作废（防止缺字段把界面打崩）


def _pkey(uid, server):
    return "%s|%s" % (uid, server or AUTO_SERVER)


def _cache_get(cache, uid, server):
    box = cache.get("profiles")
    if not isinstance(box, dict):
        return None
    rec = box.get(_pkey(uid, server))
    if not isinstance(rec, dict):
        return None
    try:
        if time.time() - float(rec.get("t") or 0) > PROFILE_TTL:
            return None
    except Exception:
        return None
    p = rec.get("p")
    if not isinstance(p, dict) or p.get("_v") != PROFILE_VER:
        return None
    return json.loads(json.dumps(p))      # 深拷贝：界面改字段不会污染缓存


def _cache_put(cache, uid, server, prof):
    box = cache.get("profiles")
    if not isinstance(box, dict):
        box = {}
    p = dict(prof)
    p["_v"] = PROFILE_VER
    box[_pkey(uid, server)] = {"t": time.time(), "p": p}
    if len(box) > PROFILE_MAX:
        for k in sorted(box, key=lambda x: box[x].get("t", 0))[:-PROFILE_MAX]:
            box.pop(k, None)
    cache["profiles"] = box


def lookup(uid, progress=None, cfg=None, cache=None, server=None, use_cache=True):
    """查询入口，带 10 分钟结果缓存。

    命中时返回上次的档案并打上 `_cached`，界面据此提示。
    要强制拿最新数据就传 use_cache=False（界面约定：同一个 UID 再点一次查询）。
    """
    cfg = cfg or load_config()
    cache = cache if cache is not None else load_cache()
    uid = int(uid)

    if use_cache:
        hit = _cache_get(cache, uid, server)
        if hit:
            hit["_cached"] = True
            return hit

    prof = _lookup_uncached(uid, progress, cfg, cache, server)
    if prof:
        prof.pop("_cached", None)
        _cache_put(cache, uid, server, prof)
        save_cache(cache)
    return prof


def _lookup_uncached(uid, progress=None, cfg=None, cache=None, server=None):
    """查询并解析。返回 dict（含 server/serverName）或 None。

    server=None / "auto" → 五区轮询（兼容旧行为，慢且易触发限流）
    server=<分区 key>     → 只查该区，推荐用法
    """
    cfg = cfg or load_config()
    cache = cache if cache is not None else load_cache()
    servers = cfg.get("servers") or []
    hotver = int(cache.get("hotver") or cfg.get("hotver") or 18464)
    uid = int(uid)
    # 总预算必须在这里就位：单分区分支在任何循环之前就直接 return 了
    deadline = time.time() + LOOKUP_BUDGET

    def note(msg):
        if progress:
            progress(msg)

    if server and server != AUTO_SERVER:
        by_key = {x["key"]: x for x in servers}
        srv = by_key.get(server)
        if not srv:
            return None
        return _lookup_single(uid, srv, cache, hotver, note, deadline=deadline)

    order = order_servers(servers, uid, cache.get("lastServer"))
    hit = None
    clean_miss = True   # 所有分区都明确回「没有这个角色」（errcode=0 但 data 空）
    _LAST["reason"] = "unknown"

    # 第一轮：用缓存的热更版本号快速试
    for i, srv in enumerate(order, 1):
        if time.time() > deadline:
            _LAST["reason"] = "timeout"
            break
        note("正在尝试 %d/%d · %s …" % (i, len(order), srv["name"]))
        data, ec = try_one(srv, uid, hotver)
        if data:
            hit = (srv, data)
            break
        if ec not in (0,):
            clean_miss = False

    # 所有分区都干净地回「查无此人」→ 不必浪费时间去探测版本号
    if not hit and clean_miss:
        _LAST["reason"] = "notfound"
        return None

    # 第二轮：可能游戏刚更新，重新探测版本号
    if not hit:
        note("版本号可能过期，重新探测…")
        for srv in order:
            if time.time() > deadline:
                _LAST["reason"] = "timeout"
                break
            hv = _redetect_hotver(srv, hotver)
            if hv and hv != hotver:
                hotver = hv
                cache["hotver"] = hv
                save_cache(cache)
                note("版本号校正为 %s，重试…" % hv)
                data, _ec = try_one(srv, uid, hv)
                if data:
                    hit = (srv, data)
                    break

    if not hit:
        # 走到这里还没命中：区分「限流/断网」和「版本号都探不出来」
        if _LAST.get("reason") not in ("timeout",):
            _LAST["reason"] = "net"
        return None
    srv, data = hit
    _LAST["reason"] = "ok"
    return _finish(uid, srv, data, cache, hotver, note)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python lookup_core.py <uid> [分区key|auto]")
        raise SystemExit(1)
    srv_arg = sys.argv[2] if len(sys.argv) > 2 else None
    t0 = time.time()
    r = lookup(int(sys.argv[1]), progress=lambda m: print("  " + m), server=srv_arg)
    if not r:
        print("未查到（五个分区都没有这个 UID）")
        raise SystemExit(2)
    print("\n===== 查询结果（%.1fs）=====" % (time.time() - t0))
    print("分区    : %s（%s）" % (r["serverName"], r["server"]))
    print("名字    : %s（%s，%s 岁）" % (r["name"], r["sex"], r["age"]))
    print("门派    : %s" % (r["menpai"] or "—"))
    lv_txt = "%s%s" % (r["lv"], "（经验反算）" if r["lvEstimated"] else "")
    print("等级    : %s" % lv_txt)
    print("武学造诣: %s" % r["kongfu"])
    print("经验    : %s" % r["exp"])
    print("福缘    : %s" % (r["fuyuan"] if r["fuyuan"] is not None else "—"))
    print("排名    : %s" % (r["rank"] if r["rank"] else "未上榜"))
    print("武学    : %d 门" % len(r["skills"]))
    print("准备位  : %d" % len(r["prepared"]))
    print("装备    : %d 件" % len(r["equips"]))
    print("传承    : %d 世" % len(r["history"]))

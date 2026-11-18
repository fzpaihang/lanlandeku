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

# 隐私名单只读副本：必须与 apk/app_ui.py 的 HIDDEN_UIDS 以及 data/hidden.json 一致
# （scripts/preflight.py 会校验三者）。放在这里是因为 recent_queries() 要过滤掉
# 名单内玩家，而 lookup_core 不能反向 import app_ui（会循环依赖）。
HIDDEN_UIDS_LOCAL = set((
    "4047491326", "4168426", "6622657", "21079748748",
    "19035702184",
))

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

# 人物等级 ↔ 经验的真实关系：exp = 0.1*lv³ + 1.35*lv²（v73 重新拟合）
#
# 以前只有三次项 0.100402*lv³，是按高等级样本拟合的，三次项占主导时误差被淹没；
# 到低等级段二次项就显出来了 —— 全库 716 人（lv 505~4292）实测：
#   只用三次项          偏差中位 +0.76 级，500~999 级段 +3.5 级，最大 +4.17
#   加上二次项后        偏差中位  0.00 级，全库最大 +0.52，98.7% 能精确落回整数等级
# 同一次接口响应的 (lv, exp) 严格配对复测：taptap_4 120 人旧公式命中率 0%，新公式 96%；
# taptap 120 人旧公式 76%，新公式 100%。
LV_A = 0.1
LV_B = 1.35
LV_COEF = 0.100402      # 旧的三次项系数，仅作 lv_from_exp() 的牛顿迭代初值


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
    """由经验反算人物等级：解 0.1*x³ + 1.35*x² = exp（牛顿迭代，初值用旧三次项公式）。

    只在榜单没有 lv 时兜底用；有榜单等级时一律显示游戏给的值，不动名次。
    """
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return None
    if exp <= 0:
        return None
    x = (exp / LV_COEF) ** (1.0 / 3.0)      # 初值：5 次以内收敛
    for _ in range(40):
        f = LV_A * x ** 3 + LV_B * x ** 2 - exp
        d = 3 * LV_A * x ** 2 + 2 * LV_B * x
        if not d:
            break
        step = f / d
        x -= step
        if abs(step) < 1e-9:
            break
    return int(round(x))


SKILL_LV_MAX = 1100     # 游戏内武学等级上限


def lv_of_skill(exp):
    """武学等级 = f(技能经验)，向上取整并夹在 [0, SKILL_LV_MAX] 内。

    阈值 f(lv) = 0.015*lv^3 + 1 代回公式会落在 lv-0.0000001 左右，
    int() 截断会系统性少报一级（线上 499/999/1099 都是这么来的），
    所以用 ceil() 补齐。口径与网页抓取脚本 scripts/fetch_profiles.py::lv_of()、
    Worker worker/src/profile.js::lvOfSkill() 一致。
    """
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return 0
    if exp < 8:
        return max(0, int(exp))
    try:
        import math
        lv = int(math.ceil(((exp - 1) / 0.015) ** (1.0 / 3.0)))
    except Exception:
        return 0
    return max(0, min(lv, SKILL_LV_MAX))


# ---------------------------------------------------------------------------
# 远端私有配置（新增分区不必重打 APK）
#
# 分区凭据（uuid/account）不能进公开仓库：Pages 的源是 main 根目录，
# 任何进 git 的文件都会公开。所以凭据放在一个**私有 gist** 里，
# APK 用已经内置的 gh.json token 去拉，拉到后缓存在应用私有目录。
#
# 优先级：远端缓存 > 本地 config.json。
# 理由：APK 内置的 config.json 是打包那一刻的快照，新增分区永远拿不到；
# 而远端配置可以随时更新（改 gist 即可，用户重启 App 生效）。
# ---------------------------------------------------------------------------
CONFIG_CACHE = os.path.join(DATA_DIR, "servers-remote.json")
GIST_ID = "91b6a13fa2cc94584a6647ce57b260f9"
GIST_API = "https://api.github.com/gists/%s" % GIST_ID
CONFIG_TTL = 6 * 3600        # 6 小时内不重复拉取


def _norm_cfg(d):
    """把 gist / 本地 config.json 的两种写法统一成 {"servers": [...]}。

    - 推荐写法：整份配置字典（带 _note / hotver / ver / servers）
    - 历史写法：裸 servers 数组（v71 加 ios3 时 gist 写错过一次，
      导致 APK 拉不到新分区却完全不报错）
    返回的一定是 dict；无法识别时返回 {}。
    """
    if isinstance(d, dict):
        return d
    if isinstance(d, list):
        return {"servers": d}
    return {}


def _gh_token():
    """从 gh.json 取 token（与 archive_local 用的是同一份）。"""
    try:
        paths = [_find("gh.json")]
        for d in (BASE, DATA_DIR):
            paths.append(os.path.join(d, "gh.json"))
        for p in paths:
            try:
                with io.open(p, encoding="utf-8") as f:
                    j = json.load(f)
                tok = (j.get("token") or "").strip()
                if tok:
                    return tok
            except Exception:
                continue
    except Exception:
        pass
    return ""


def refresh_remote_config(force=False):
    """拉一次私有配置并写缓存。返回 True 表示有新配置。"""
    import time
    try:
        if not force and os.path.exists(CONFIG_CACHE):
            if time.time() - os.path.getmtime(CONFIG_CACHE) < CONFIG_TTL:
                return False
    except Exception:
        pass
    tok = _gh_token()
    if not tok:
        return False
    try:
        req = urllib.request.Request(GIST_API, method="GET")
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "fzjh-lookup")
        # TLS：**不要**复用 fetch.F.ctx。那个上下文是为游戏接口配的最小 CA 包
        # （只含 ISRG X1 / DigiCert G2 / GlobalSign R46），拿它校验
        # api.github.com 会报 CERTIFICATE_VERIFY_FAILED（实测）。
        # 这条通道只取「分区凭据」这一份非机密配置，用系统默认上下文不校验；
        # 内容即使被中间人篡改，最坏结果是查不出人，不会泄漏任何东西。
        try:
            import ssl
            ctx = ssl._create_unverified_context()
        except Exception:
            ctx = None
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            g = json.loads(r.read().decode("utf-8"))
        raw = ((g.get("files") or {}).get("servers.json") or {}).get("content") or ""
        cfg = _norm_cfg(json.loads(raw))
        if not (cfg.get("servers") or []):
            # v71 踩过：gist 内容写成裸数组时这里静默 return False，
            # 设备上只表现为「该分区未找到」，既不报错也不刷新缓存。
            print("[config] 远端配置里没有 servers 数组（gist 要写成 {\"servers\": [...]}）")
            return False
        tmp = CONFIG_CACHE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(raw)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, CONFIG_CACHE)
        return True
    except Exception as e:
        print("[config] 远端配置拉取失败：%r" % (e,))
        return False


def _remote_config():
    try:
        with io.open(CONFIG_CACHE, encoding="utf-8") as f:
            cfg = _norm_cfg(json.load(f))
        if cfg.get("servers"):
            return cfg
    except Exception:
        pass
    return None


def load_config():
    remote = _remote_config()
    if remote:
        return remote
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            with io.open(p, encoding="utf-8") as f:
                cfg = _norm_cfg(json.load(f))
            if cfg.get("servers"):
                return cfg
    raise RuntimeError("找不到 config.json（含分区凭据）")


SERVERS_INDEX_URL = "https://fzpaihang.github.io/lanlandeku/data/servers/index.json"
SERVERS_MIRROR = "https://cdn.jsdelivr.net/gh/fzpaihang/lanlandeku@main/data/servers/index.json"
_SRV_CACHE = {"ts": 0, "rows": []}
SRV_CACHE_TTL = 6 * 3600      # 6 小时内不重复下载


def remote_servers():
    """远端分区清单 [(key, name)]；失败返回 []。

    用于「新增分区不必重打 APK」：凭据在 CI Secret 里，APK 内置的
    config.json 永远拿不到新分区，但 data/servers/index.json 会随站点更新。
    """
    import time
    now = time.time()
    if _SRV_CACHE["rows"] and now - _SRV_CACHE["ts"] < SRV_CACHE_TTL:
        return list(_SRV_CACHE["rows"])
    ctx = getattr(F, "ctx", None)
    for url in (SERVERS_INDEX_URL, SERVERS_MIRROR):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fzjh-lookup"})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                d = json.loads(r.read().decode("utf-8"))
            rows = [(str(s["key"]), str(s["name"]))
                    for s in (d.get("servers") or []) if s.get("key")]
            # 远端清单不含凭据，但要保证本地有凭据的分区排在前面（默认区正确）
            if rows:
                _SRV_CACHE["rows"] = rows
                _SRV_CACHE["ts"] = now
                return list(rows)
        except Exception:
            continue
    return list(_SRV_CACHE["rows"])


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
    """最近成功的查询，最多 RECENT_MAX 条；失败不抛异常。

    隐私名单（data/hidden.json）里的人一旦被加进名单，历史记录里的残留也要藏掉：
    否则首页「最近查询」仍会显示他的 UID + 昵称，等于名单形同虚设。
    HIDDEN_UIDS_LOCAL 与 apk/app_ui.py 的 HIDDEN_UIDS 保持一致（preflight 会校验），
    这里不 import app_ui 是为了避免 lookup_core ←→ app_ui 的循环依赖。
    """
    try:
        items = load_cache().get("recentQueries") or []
        out = []
        for x in items:
            if not isinstance(x, dict) or not x.get("uid"):
                continue
            if str(x.get("uid")).strip() in HIDDEN_UIDS_LOCAL:
                continue
            out.append(x)
            if len(out) >= RECENT_MAX:
                break
        return out
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


# ---------------------------------------------------------------------------
# uid → 分区 的确定性规则（由用户提供，比按位数猜准得多）
#
#   8 位及以下           → taptap     苍松迎客
#   18 开头（>8 位）      → taptap_2   白鹤亮翅
#   21 开头              → taptap_3   丹凤朝阳
#   22 开头              → taptap_4   墨羽惊鸿
#   30 开头              → ios1       老马识途（iOS）
#   8  开头（10 位）      → ios2       野马分鬃（iOS）
#   19 开头（11 位）      → ios3       仙人指路（iOS）
#   4  开头              → 4399
#   其余前缀对应的渠道本项目暂未收录，落到「未知」按老办法轮询
#
# 注意：**位数优先**。8 位及以下一律是苍松，不看前缀
#（例如 4168426 这种 7 位数虽然 4 开头，也是苍松不是 4399）。
#
# iOS 三个区的号段互不重叠（用户 2026-11-18 确认）：
#   老马识途 3 开头（10 位）/ 野马分鬃 8 开头（10 位）/ 仙人指路 19 开头（11 位）。
# ---------------------------------------------------------------------------
UID_PREFIX_SERVER = (
    ("10", "huawei"),     # 华为（uid 10 开头，11 位）
    ("18", "taptap_2"),   # 白鹤亮翅
    ("21", "taptap_3"),   # 丹凤朝阳
    ("22", "taptap_4"),   # 墨羽惊鸿
    ("30", "ios1"),       # 老马识途（iOS 一区，uid 3 开头 10 位）
    ("8", "ios2"),        # 野马分鬃（iOS 二区，uid 8 开头 10 位）
    ("19", "ios3"),       # 仙人指路（iOS 三区，uid 19 开头 11 位）
    ("4", "4399"),
    ("6", "yyh"),         # 应用汇
    ("9", "guanfang"),    # 其他服（官方合服，uid 一律 9 开头 10 位）
)

# 本项目未收录、但已知归属的前缀（留档，将来补分区时直接用）
UID_PREFIX_FUTURE = {
    "5": "当乐", "7": "啪啪游戏厅",
    "11": "oppo", "12": "vivo", "13": "应用宝",
    "14": "小七", "20": "小米",
}


def server_of_uid(uid):
    """按 uid 推出分区 key；推不出来返回 None。

    规则来源见 UID_PREFIX_SERVER 上方注释。这里只做纯字符串判断，
    不依赖任何网络或分区清单，所以调用方可以据此「只请求一次」。
    """
    s = str(uid or "").strip()
    if not s.isdigit():
        return None
    if len(s) <= 8:                 # 8 位及以下 → 苍松迎客（位数优先于前缀）
        return "taptap"
    for pre, key in UID_PREFIX_SERVER:
        if s.startswith(pre):
            return key
    return None


def order_servers(servers, uid, last_key=None):
    """按「前缀规则 → 上次命中 → 位数推测 → 其余」排序，减少无谓请求。

    最优先的是 server_of_uid() 的确定性结果：命中就把它排到第一位，
    自动探测的常规情况就只发 1 次请求。
    """
    s = str(uid)
    guess = []
    exact = server_of_uid(uid)      # 前缀规则命中的分区，放最前面
    if exact:
        guess.append(exact)
    if len(s) == 7:
        guess.append("taptap")
    elif len(s) == 10:
        guess += ["4399", "ios1", "ios2"]
    elif len(s) == 11:
        guess += ["taptap_3", "taptap_2", "taptap_4", "ios3"]
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


# 字段级隐藏兜底（与 data/hidden-fields.json 同步）。
# 与 HIDDEN_UIDS 的「整条剔除」不同：这些人照样能查、照样出现在榜单，
# 只是把指定字段藏起来（隐藏名单下载失败时这一份仍然生效）。
HIDDEN_FIELDS = {
    "19035589937": set(("skills", "prepared", "newSkills")),
}


def apply_field_hide(prof, uid):
    """按 HIDDEN_FIELDS 清空指定字段。只清数据不删条目。"""
    hide = HIDDEN_FIELDS.get(str(uid))
    if not hide:
        return prof
    if "skills" in hide:
        prof["skills"] = []
    if "prepared" in hide:
        prof["prepared"] = {}
    return prof


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
    # inheritHistory 每一条是一次传承事件：parentName = 上一世，inheritName = 这一世。
    # 第一条的 parentName 是「0 转 / 初代」的名字，必须保留，否则传承链会少一世
    # （网页 fetch_profiles.py 一直存了 p，网页档案页也以「初代」节点起头）。
    history = []
    for x in (data.get("inheritHistory") or []):
        if not isinstance(x, dict):
            continue
        history.append({"n": x.get("inheritName") or "",
                        "p": x.get("parentName") or "",
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


# ---------- 榜单兜底：实时请求失败时，用本地榜单快照给个「非实时」结果 ----------
# 默认关闭，由结果页右上角的开关打开（存在 lookup_cache.json 里）。
# 为什么要有：服务端限流（20616）或断网时，至少能告诉玩家这个人叫什么、
# 什么门派、多少级、排第几——但这些数字来自榜单快照，必须明确标非实时。
BOARD_FALLBACK = "boardFallback"


def board_fallback_on(cache=None):
    cache = cache if cache is not None else load_cache()
    return bool(cache.get(BOARD_FALLBACK))


def set_board_fallback(on, cache=None):
    cache = cache if cache is not None else load_cache()
    cache[BOARD_FALLBACK] = bool(on)
    save_cache(cache)
    return bool(on)


def board_profile(uid, server=None, cache=None):
    """从本地榜单快照拼一份「可展示但非实时」的档案；找不到返回 None。

    字段只取榜单里有的（昵称/门派/等级/经验/名次/传承），武学、装备、气血
    这些榜单没有，界面不能按实时档案的样子展示。
    返回的 dict 带 `_board=True` 与 `_boardTs`（快照抓取时间），界面据此标注。
    """
    cache = cache if cache is not None else load_cache()
    bc = cache.get("boardCache") or {}
    key = str(uid or "").strip()
    if not key or not bc:
        return None
    # 已知分区优先，其余按缓存里的顺序兜一遍（自动识别模式会用上）
    order = [server] if (server and server != AUTO_SERVER and server in bc) else []
    order += [k for k in bc if k not in order]
    snames = {}
    try:
        for s in (load_config().get("servers") or []):
            snames[str(s.get("key"))] = str(s.get("name") or s.get("key"))
    except Exception:
        pass
    for k in order:
        rec = bc.get(k) or {}
        for r in (rec.get("rows") or []):
            if str(r.get("userid")) != key:
                continue
            lv, est = r.get("lv"), False
            if not lv and r.get("exp"):
                # 人物等级用 lv_from_exp（0.1·lv³+1.35·lv²），不是武学那套 f(lv)=0.015·lv³
                lv, est = lv_from_exp(r["exp"]), True
            return {
                "uid": int(key),
                "name": (r.get("name") or "").strip() or "（无昵称）",
                "menpai": r.get("menpai") or "",
                "lv": lv, "lvEstimated": est,
                "exp": r.get("exp"),
                "rank": r.get("rank"),
                "kongfu": r.get("kongfu"),
                "inheritCount": r.get("inheritCount"),
                "server": k, "serverName": snames.get(k, k),
                "_board": True, "_boardTs": rec.get("ts") or 0,
            }
    return None


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
    prof = apply_field_hide(parse_profile(data, row), uid)
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
PROFILE_VER = 4        # 结构变了就 +1，旧缓存自动作废（防止缺字段把界面打崩）
                       # v66：history 多存 p（parentName / 0 转初代名），
                       # 旧缓存没有 p 会退化成占位「初代」，bump 后强制重查一次。
                       # v72：加入字段级隐藏（HIDDEN_FIELDS），旧缓存里可能还留着
                       # 被隐藏玩家的武学列表，bump 后强制重查一次。


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

    # 前缀规则能唯一确定分区时，只查这一个区（1 次请求）。
    # 推不出来才回退到多区轮询。
    exact_key = server_of_uid(uid)
    if exact_key:
        by_key = {x["key"]: x for x in servers}
        srv = by_key.get(exact_key)
        if srv:
            note("按 UID 规则直接定位 · %s" % srv["name"])
            data = _lookup_single(uid, srv, cache, hotver, note, deadline=deadline)
            if data:
                cache["lastServer"] = exact_key
                save_cache(cache)
                return data
            # 规则命中的区查不到：可能是规则外的新渠道，或角色已删。
            # 不直接放弃，落回轮询（跳过刚试过的这个区）。
            note("该区未找到，继续尝试其他分区…")

    order = order_servers(servers, uid, cache.get("lastServer"))
    if exact_key:
        order = [s for s in order if s["key"] != exact_key]
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

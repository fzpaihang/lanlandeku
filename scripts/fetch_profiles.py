# -*- coding: utf-8 -*-
"""抓取高手榜全部玩家的详情，产出 data/servers/<key>/profiles/<uid>.json

每个档案只保留页面要用的字段（技能 id/等级、装备、准备位等），由
merge_exp.py 再把经验写回榜单。旧版曾写入 data/players.json，已废弃。

依赖：
  data/servers/<key>/gaoshoubang.json  榜单（先用 fetch.py 生成）
  data/names.json                     技能/装备中文名（由 build_names.py 生成）

用法:
  python scripts/fetch_profiles.py              # 抓全部（约 100 次请求，1 分钟左右）
  python scripts/fetch_profiles.py --limit 5    # 只抓前 5 名（调试）
  python scripts/fetch_profiles.py --only 3413862 3464549
  python scripts/fetch_profiles.py --server "taptap,taptap_2" --hall-only
                                                # 名人堂批次：只抓本区 hall.json 的人（每区 ≤10 人），
                                                # 需先跑 fetch.py --board 4 生成 hall.json
"""
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import fetch as F  # noqa: E402  复用握手 / 加密 / 请求
from lv_formula import lv_from_exp  # noqa: E402  人物等级反算（纯计算，无第三方依赖）

# 档案抓取不再自己 sleep：所有请求都走 F.post_with_retry，
# 那里的 _pace_wait() 按 fetch.PACE 统一限速（撞限流抬 25%、成功回落 20%），
# 撞上限流由那里的「换会话密钥重试」兜住。榜单翻页和档案抓取共用同一个节奏，
# 才不会两边各撞各的；档案接口几乎每份都先撞一次限流（2026-11-21 实测）。
NEW_DAYS = 30          # 「近期新增」保留天数
KEEP_DAYS = 30         # 掉榜档案保留天数：超期没再上榜才删（回归后仍可查）

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


SKILL_LV_MAX = 1100     # 游戏内武学等级上限


def lv_of(exp):
    """武学等级由技能经验换算，向上取整并封顶。

    阈值 f(lv) = 0.015*lv^3 + 1 代回公式时，浮点结果会落在 lv-0.0000001 左右，
    原来的 int() 截断会系统性少报一级（线上 499/999/1099 都是这么来的）。
    改用 ceil() 补齐，并夹在 [0, SKILL_LV_MAX] 内。
    口径与 apk/lookup_core.py::lv_of_skill()、worker/src/profile.js::lvOfSkill() 一致。
    """
    if not isinstance(exp, (int, float)):
        return 0
    if exp < 8:
        return max(0, int(exp))
    try:
        import math
        lv = int(math.ceil(((exp - 1) / 0.015) ** (1.0 / 3.0)))
    except Exception:
        return 0
    return max(0, min(lv, SKILL_LV_MAX))



def _days_ago(today, n):
    """'2026-11-10' 往前推 n 天 → '2026-10-11'"""
    import datetime
    try:
        d = datetime.date(*[int(x) for x in today.split("-")])
        return (d - datetime.timedelta(days=n)).isoformat()
    except Exception:
        return "0000-00-00"


def slim(p, board_row, names, old=None, today=None):
    """把服务器返回的完整档案压成页面要用的精简结构

    old: 上一版档案（用来 diff 出「近期新增武学」），首次抓取传 None
    """
    sk_map = names.get("skills", {})
    eq_map = names.get("equips", {})

    def skill_name(sid):
        """技能 id → 中文名

        自创武学的 id 形如 `<uid>_selfCreatedSkill_8495`，技能表里没有，也没地方
        取名字，统一显示「自创武学」，避免把一串 id 甩给用户。
        """
        if sid in sk_map:
            return sk_map[sid]
        if "selfCreatedSkill" in str(sid):
            return "自创武学"
        return sid

    skills = []
    for sid, v in (p.get("skills") or {}).items():
        if not isinstance(v, dict):
            continue
        skills.append({
            "id": sid,
            "n": skill_name(sid),
            "lv": lv_of(v.get("exp")),
        })
    skills.sort(key=lambda x: (-x["lv"], x["n"]))

    prep_raw = p.get("skillPrepare") or {}
    prepared = {}
    for slot, sid in prep_raw.items():
        if not sid or not isinstance(sid, str):
            continue
        prepared[SLOT_CN.get(slot, slot)] = skill_name(sid)

    equips = []
    for slot, v in (p.get("equips") or {}).items():
        if not isinstance(v, dict) or not v.get("itemId"):
            continue
        iid = str(v["itemId"])
        nm = eq_map.get(iid)
        equips.append({
            "slot": EQUIP_CN.get(slot, slot),
            "n": nm or "未知",
            "known": bool(nm),
            "raw": iid,
        })

    def num(x, r=0):
        try:
            return round(float(x), r)
        except (TypeError, ValueError):
            return None

    # ---- 传承链（曾用名）：每条的 parentName 是上一世，inheritName 是这一世 ----
    history = []
    for x in (p.get("inheritHistory") or []):
        if not isinstance(x, dict):
            continue
        history.append({
            "n": x.get("inheritName") or "",
            "p": x.get("parentName") or "",
            "t": int(x.get("inheritTime") or 0),
        })
    history.sort(key=lambda x: x["t"])

    # ---- 近期新增武学：与上一版档案比对 ----
    new_skills = []
    if old:
        old_ids = set(s.get("id") for s in (old.get("skills") or []))
        carried = old.get("newSkills") or []
        # 继承仍在 30 天内的旧记录
        for e in carried:
            if e.get("date") and today and e["date"] > today:
                continue
            new_skills.append(e)
        # 这次新出现的
        for s in skills:
            if s["id"] not in old_ids:
                new_skills.append({"id": s["id"], "n": s["n"], "date": today})
        # 去重（保留最早日期）+ 按日期倒序
        dedup = {}
        for e in new_skills:
            k = e.get("id")
            if not k:
                continue
            if k not in dedup or e.get("date", "") < dedup[k].get("date", ""):
                dedup[k] = e
        new_skills = sorted(dedup.values(), key=lambda x: x.get("date", ""), reverse=True)
        # 掉 30 天前的
        if today:
            new_skills = [e for e in new_skills if e.get("date", "") >= _days_ago(today, NEW_DAYS)]

    return {
        "name": p.get("name") or (board_row or {}).get("name") or "",
        "sex": p.get("sex"),
        "age": p.get("age"),
        "looks": p.get("looks"),
        "menpai": (board_row or {}).get("menpai") or "",
        "kongfu": num(p.get("kongfu"), 2),
        "exp": num(p.get("exp"), 0),
        "qi": num(p.get("qi"), 0),
        "qiMax": num(p.get("qiMax"), 0),
        "jiaLi": p.get("jiaLi"),
        "zhengqi": p.get("zhengqi"),
        "inheritCount": p.get("inheritCount"),
        "fuyuan": (board_row or {}).get("fuyuan"),
        # 等级按档案自己的经验反算，与榜单页同口径（榜单 lv 是「上次点榜」的旧值）
        "lv": lv_from_exp(num(p.get("exp"), 0)) or (board_row or {}).get("lv"),
        "rank": (board_row or {}).get("rank"),
        "skills": skills,
        "newSkills": new_skills,
        "history": history,
        "prepared": prepared,
        "equips": equips,
    }


def apply_field_hide(prof, hide):
    """字段级隐藏：把 data/hidden-fields.json 里指定的字段清空。

    只清数据不删条目——玩家本人照样出现在榜单、档案、查询结果里，
    等级 / 经验 / 装备 / 传承等其它信息照常显示。
    """
    if not hide:
        return prof
    if "skills" in hide:
        prof["skills"] = []
    if "prepared" in hide:
        prof["prepared"] = {}
    if "newSkills" in hide:
        prof["newSkills"] = []
    return prof


def prune_profiles(out_dir, targets, now=None):
    """清理「长期没再上榜」的旧档案，返回 (删除数, 保留数)。

    - 还在本轮目标里的一律不动。
    - 掉榜但 updatedTs 在 KEEP_DAYS 天内的先留着：他可能只是暂时掉出 100 名，
      回来时档案还在，配合 exp-history 里延续的经验值（merge_exp.py「继承掉榜」），
      就能正常看到两次经验变化、也能点开武学/装备详情。
    - 读不到 updatedTs 的保守保留（宁可多留一份，也不要误删）。
    """
    now = time.time() if now is None else now
    deadline = now - KEEP_DAYS * 86400
    valid = set(str(u) for u in targets)
    removed = kept = 0
    for fn in os.listdir(out_dir):
        if not fn.endswith(".json") or fn[:-5] in valid:
            continue
        fp = os.path.join(out_dir, fn)
        try:
            with io.open(fp, "r", encoding="utf-8") as f:
                ts = int((json.load(f) or {}).get("updatedTs") or 0)
        except (OSError, ValueError, TypeError):
            ts = 0
        if not ts or ts >= deadline:
            kept += 1
            continue
        try:
            os.remove(fp)
            removed += 1
        except OSError:
            pass
    return removed, kept


def fetch_server(srv, names, args):
    """抓单个服务器的玩家档案，写到 data/servers/<key>/profiles/"""
    cfg = F.server_cfg(srv)
    out_dir0 = F.server_dir(srv["key"])
    board_path = os.path.join(out_dir0, "gaoshoubang.json")
    if not os.path.exists(board_path):
        print("!! %s 还没有榜单数据，先跑 fetch.py --server %s" % (srv["name"], srv["key"]))
        return 1
    with io.open(board_path, encoding="utf-8") as f:
        board = json.load(f)
    rows = {r["userid"]: r for r in board.get("rows", [])}

    # 只进昵称索引的 51–100 名（fetch.py 的 indexRank 产出）：也要抓档案，
    # 否则索引里能搜到人、点开却没有档案。排在榜单之后，保持名次顺序。
    extra = []
    ep = os.path.join(out_dir0, "index-extra.json")
    if os.path.exists(ep):
        try:
            with io.open(ep, encoding="utf-8") as f:
                extra = [r for r in (json.load(f).get("rows") or []) if r.get("userid")]
        except Exception:
            extra = []
    for r in extra:
        rows.setdefault(r["userid"], r)

    # 名人堂（boardType=4，fetch.py --board 4 产出同目录 hall.json）：每区最多 10 人，
    # 里面可能有前百高手榜里没有的人。这些人的档案也必须抓，否则页面上点开没有详情。
    # 同名次口径：同一 uid 同时在高手榜和名人堂时，setdefault 保证高手榜那行优先
    # （档案里的名次/门派按高手榜算，和以前完全一致）。
    hall = []
    hp = os.path.join(out_dir0, "hall.json")
    if os.path.exists(hp):
        try:
            with io.open(hp, encoding="utf-8") as f:
                hall = [r for r in (json.load(f).get("rows") or []) if r.get("userid")]
        except Exception:
            hall = []
    for r in hall:
        rows.setdefault(r["userid"], r)

    # --hall-only（refresh.yml 的名人堂分批任务）：目标集合只取本区 hall.json 的人。
    # 前百高手榜 / index-extra 仍然读进来补 rows（slim() 要从 rows 取
    # menpai/fuyuan/rank，同一玩家按高手榜那行算，口径和以前一致），
    # 但它们不进目标集合；也不做 maxRank / --limit 截断 —— 名人堂每区最多 10 人。
    hall_only = "--hall-only" in args
    if hall_only and not hall:
        print("!! %s 还没有名人堂数据，先跑 fetch.py --board 4 --server %s" % (srv["name"], srv["key"]))
        return 1

    if "--only" in args:
        i = args.index("--only")
        targets = [int(x) for x in args[i + 1:] if x.isdigit()]
    elif hall_only:
        targets = [r["userid"] for r in hall]
        print("      名人堂批次：只抓本区 hall.json 的 %d 位（不抓前百 / 索引 extra）" % len(targets))
    else:
        targets = [r["userid"] for r in board.get("rows", [])]
        targets += [r["userid"] for r in extra if r["userid"] not in set(targets)]
        if "--limit" in args:
            targets = targets[: int(args[args.index("--limit") + 1])]
        else:
            # 双保险：榜单可能因抓取失败保留上一版（人数会超过 maxRank），
            # 这里再按上限截断一次，避免多抓几十份档案。
            # 上限取 max(maxRank, indexRank)：只有榜单前 50，但索引要前 100。
            caps = []
            for k in ("maxRank", "indexRank"):
                try:
                    v = int(srv.get(k) or 0)
                except (TypeError, ValueError):
                    v = 0
                if v:
                    caps.append(v)
            cap = max(caps) if caps else 0
            if cap and len(targets) > cap:
                print("      目标 %d 人超过抓取上限 %d，按上限截断" % (len(targets), cap))
                targets = targets[:cap]

        # 名人堂的行排在上面的上限截断之后追加：maxRank/--limit 是「高手榜前 N 名」的口径，
        # 名人堂每区最多 10 人且页内详情依赖档案，不能被截掉。
        if hall:
            seen_t = set(targets)
            add = [r["userid"] for r in hall if r["userid"] not in seen_t]
            targets += add
            print("      名人堂玩家 %d 位也抓档案（其中 %d 位不在高手榜）" % (len(hall), len(add)))

    # 字段级隐藏：这些人照常抓、照常出现在榜单和档案里，只清空指定字段
    hide_fields = F.hidden_fields_for(F.load_hidden_fields(), srv["key"])
    if hide_fields:
        print("      字段级隐藏 %d 位：%s" % (
            len(hide_fields),
            ", ".join("%s(%s)" % (u, "/".join(sorted(f))) for u, f in hide_fields.items())))

    # 影子玩家（hidden.json 里带 "shadow": true）先从隐藏名单里摘出来：
    # 公开榜里没有他们（照旧剔除），但影子榜要和他们同口径的经验 / 等级，
    # 所以档案照抓、不删。公开网页不展示他们，门槛在
    # 「前端只有带口令才读 data/shadow.json」这一层。
    shadow_uids = F.shadow_uids_for(F.load_shadow(), srv["key"])

    # 隐私名单：跳过这些玩家，并删掉已存在的档案文件
    hidden_uids = F.hidden_uids_for(F.load_hidden(), srv["key"]) - shadow_uids
    if shadow_uids:
        srows = ((F.read_shadow().get("servers") or {}).get(srv["key"]) or {}).get("rows") or []
        in_board = set(rows)
        added = 0
        for r in srows:
            uid = r.get("userid")
            if not uid or str(uid) in hidden_uids:
                continue
            # 影子玩家掉出真榜后，board 里没有他的行，这里用影子行补
            # （slim() 只从 board_row 取 menpai/fuyuan/rank，缺了会变空）
            if uid not in in_board:
                rows[uid] = r
                added += 1
            if "--only" not in args and uid not in targets:
                targets.append(uid)
        print("      影子玩家 %d 位：档案照抓（其中 %d 位不在公开榜）" % (len(shadow_uids), added))

    if hidden_uids:
        before = len(targets)
        targets = [u for u in targets if str(u) not in hidden_uids]
        print("      跳过隐藏玩家 %d 位（%d → %d 份）" % (before - len(targets), before, len(targets)))
        hd = os.path.join(out_dir0, "profiles")
        for u in hidden_uids:
            fp = os.path.join(hd, "%s.json" % u)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                    print("      已删除隐藏玩家的档案文件：%s.json" % u)
                except OSError:
                    pass

    t = time.time()
    print("[1/3] 握手…")
    keys = F.handshake(cfg, t)

    # 与 fetch.py 一致：游戏更新后旧 hotver 会报「版本过低」，自动校正
    hv, _ = F.detect_hotver(cfg, keys, t)
    if hv is None:
        print("      ✗ 版本号无法确定（可能维护中或接口异常），本轮跳过")
        return 1
    if hv != int(cfg["hotver"]):
        print("      版本号自动校正：%s → %s（游戏刚更新）" % (cfg["hotver"], hv))
        cfg["hotver"] = hv
        keys = F.handshake(cfg, t)

    print("[2/3] 抓取 %d 份档案（自适应节奏，起始 %.1fs/份）…" % (len(targets), F.PACE))
    players, fail = {}, []
    olds = {}
    prof_dir = os.path.join(out_dir0, "profiles")
    today = F.bj_date(t)
    for i, uid in enumerate(targets, 1):
        try:
            # 先读上一版，供「新增武学」比对；写盘在最后统一做
            op = os.path.join(prof_dir, "%s.json" % uid)
            if os.path.exists(op):
                try:
                    with io.open(op, encoding="utf-8") as f:
                        olds[uid] = json.load(f)
                except Exception:
                    olds[uid] = None
            d = F.post_with_retry(cfg, "get_user_info", {"userid": uid, "type": 0}, keys, t)
            data = d.get("data")
            # errcode=0 但 data 可能是空对象（账号不在该区时会这样），
            # 不能当成成功，否则会把已有的好档案覆盖成空壳
            if d.get("errcode") == 0 and isinstance(data, dict) and (data.get("name") or data.get("userid")):
                players[str(uid)] = apply_field_hide(
                    slim(data, rows.get(uid), names,
                         old=olds.get(uid), today=today),
                    hide_fields.get(str(uid)))
                if i % 20 == 0 or i == len(targets):
                    print("      %d/%d  uid=%s %s" % (i, len(targets), uid,
                                                     players[str(uid)]["name"]))
            else:
                fail.append({"userid": uid, "errcode": d.get("errcode"), "errmsg": d.get("errmsg")})
                print("      %d/%d  uid=%s 失败 errcode=%s" % (i, len(targets), uid, d.get("errcode")))
        except Exception as e:
            fail.append({"userid": uid, "error": str(e)})
            print("      %d/%d  uid=%s 异常 %s" % (i, len(targets), uid, e))

    if fail and "--only" not in args:
        retry_ids = [f["userid"] for f in fail]
        print("[2.5/3] 失败 %d 份，冷却后再补一轮…" % len(retry_ids))
        time.sleep(20)
        still = []
        for uid in retry_ids:
            try:
                d = F.post_with_retry(cfg, "get_user_info", {"userid": uid, "type": 0}, keys, t)
                data = d.get("data")
                if d.get("errcode") == 0 and isinstance(data, dict) and (data.get("name") or data.get("userid")):
                    players[str(uid)] = apply_field_hide(
                        slim(data, rows.get(uid), names,
                             old=olds.get(uid), today=today),
                        hide_fields.get(str(uid)))
                    print("      补抓成功 uid=%s %s" % (uid, players[str(uid)]["name"]))
                else:
                    still.append(uid)
                    print("      补抓仍失败 uid=%s errcode=%s" % (uid, d.get("errcode")))
            except Exception as e:
                still.append(uid)
                print("      补抓异常 uid=%s %s" % (uid, e))
        fail = [f for f in fail if f["userid"] in still]

    if not players:
        print("!! 一份都没抓到，保留上一版不动")
        return 1

    # 每人一个小文件，页面点击时才请求，避免首屏加载 1.5MB
    out_dir = prof_dir
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for uid, prof in players.items():
        prof["updatedAt"] = F.bj_time(t, "%Y-%m-%d %H:%M:%S")
        prof["updatedTs"] = int(t)
        p = os.path.join(out_dir, "%s.json" % uid)
        # 原子写：先写 .tmp 再 os.replace，避免进程被杀/磁盘满时留下半截 JSON
        # （半截档案会被页面当 404 处理，也可能让 fetch_profiles 下一轮读旧值失败）
        tmp = p + ".tmp"
        try:
            with io.open(tmp, "w", encoding="utf-8") as f:
                json.dump(prof, f, ensure_ascii=False, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        written += 1

    removed = kept_dropped = 0
    if ("--only" not in args and "--limit" not in args
            and "--hall-only" not in args and not fail):
        # 只有本轮 100% 抓成功才敢清理。否则一旦上游漏抓（或接口限流少给几页），
        # 这里会把没抓到的人当成「已下榜」整批删档 —— 2026-11-15 就这么删过 49 份。
        removed, kept_dropped = prune_profiles(out_dir, targets)
        if kept_dropped:
            print("      掉榜未满 %d 天的档案保留 %d 份（等回归后仍可查）" % (KEEP_DAYS, kept_dropped))
    elif fail:
        print("      本轮有 %d 份抓取失败，跳过旧档案清理（避免误删）" % len(fail))

    total = sum(os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir)) / 1024.0
    print("[3/3] 已写入 %s" % out_dir)
    print("      本轮写入 %d 份 / 失败 %d 份  |  目录合计 %.0f KB%s" % (
        written, len(fail), total,
        ("，清理旧文件 %d 个" % removed) if removed else ""))
    k = list(players)[0]
    u = players[k]
    print("      样例 %s：武学 %d 门，准备位 %d 个，装备 %d 件" % (
        u["name"], len(u["skills"]), len(u["prepared"]), len(u["equips"])))
    return 0



def main():
    args = sys.argv[1:]
    servers = F.load_servers()

    with io.open(os.path.join(BASE, "data", "names.json"), encoding="utf-8") as f:
        names = json.load(f)

    if "--server" in args:
        want = args[args.index("--server") + 1]
        # 支持逗号分隔多个分区，与 fetch.py 保持一致
        keys = [x.strip() for x in want.split(",") if x.strip()]
        targets = [s for s in servers if s["key"] in keys]
        missing = [k for k in keys if k not in [s["key"] for s in servers]]
        if missing or not targets:
            raise SystemExit("没有这些服务器：%s（可选：%s）" % (
                "、".join(missing or keys), "、".join(s["key"] for s in servers)))
    else:
        targets = servers

    rc = 0
    for i, srv in enumerate(targets, 1):
        print("\n===== [%d/%d] %s · %s =====" % (i, len(targets), srv["name"], srv["channel"]))
        try:
            if fetch_server(srv, names, args) != 0:
                rc = 1
        except Exception as e:
            print("!! 抓取失败：%s: %s" % (type(e).__name__, e))
            rc = 1
        if i < len(targets):
            time.sleep(2)
    return rc


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""抓取高手榜全部玩家的详情，产出 data/players.json（供页面点击弹窗用）

依赖：
  data/gaoshoubang.json  榜单（先用 fetch.py 生成）
  data/names.json        技能/装备中文名（由 build_names.py 生成）

用法:
  python scripts/fetch_profiles.py              # 抓全部（约 100 次请求，1 分钟左右）
  python scripts/fetch_profiles.py --limit 5    # 只抓前 5 名（调试）
  python scripts/fetch_profiles.py --only 3413862 3464549
"""
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import fetch as F  # noqa: E402  复用握手 / 加密 / 请求

SLEEP = 0.7
NEW_DAYS = 30          # 「近期新增」保留天数

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


def lv_of(exp):
    """武学等级由经验换算（与原工具一致）"""
    if not isinstance(exp, (int, float)):
        return 0
    if exp < 8:
        return int(exp)
    try:
        return int(((exp - 1) / 0.015) ** (1.0 / 3.0))
    except Exception:
        return 0



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
        "lv": (board_row or {}).get("lv"),
        "rank": (board_row or {}).get("rank"),
        "skills": skills,
        "newSkills": new_skills,
        "history": history,
        "prepared": prepared,
        "equips": equips,
    }


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

    if "--only" in args:
        i = args.index("--only")
        targets = [int(x) for x in args[i + 1:] if x.isdigit()]
    else:
        targets = [r["userid"] for r in board.get("rows", [])]
        if "--limit" in args:
            targets = targets[: int(args[args.index("--limit") + 1])]
        else:
            # 双保险：榜单可能因抓取失败保留上一版（人数会超过 maxRank），
            # 这里再按上限截断一次，避免多抓几十份档案。
            mr = srv.get("maxRank")
            if mr:
                try:
                    mr = int(mr)
                except (TypeError, ValueError):
                    mr = 0
                if mr and len(targets) > mr:
                    print("      榜单 %d 人超过抓取上限 %d，按上限截断" % (len(targets), mr))
                    targets = targets[:mr]

    # 隐私名单：跳过这些玩家，并删掉已存在的档案文件
    hidden_uids = F.hidden_uids_for(F.load_hidden(), srv["key"])
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

    print("[2/3] 抓取 %d 份档案（间隔 %.2fs）…" % (len(targets), SLEEP))
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
                players[str(uid)] = slim(data, rows.get(uid), names,
                                         old=olds.get(uid), today=today)
                if i % 20 == 0 or i == len(targets):
                    print("      %d/%d  uid=%s %s" % (i, len(targets), uid,
                                                     players[str(uid)]["name"]))
            else:
                fail.append({"userid": uid, "errcode": d.get("errcode"), "errmsg": d.get("errmsg")})
                print("      %d/%d  uid=%s 失败 errcode=%s" % (i, len(targets), uid, d.get("errcode")))
        except Exception as e:
            fail.append({"userid": uid, "error": str(e)})
            print("      %d/%d  uid=%s 异常 %s" % (i, len(targets), uid, e))
        time.sleep(SLEEP)

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
                    players[str(uid)] = slim(data, rows.get(uid), names,
                                             old=olds.get(uid), today=today)
                    print("      补抓成功 uid=%s %s" % (uid, players[str(uid)]["name"]))
                else:
                    still.append(uid)
                    print("      补抓仍失败 uid=%s errcode=%s" % (uid, d.get("errcode")))
            except Exception as e:
                still.append(uid)
                print("      补抓异常 uid=%s %s" % (uid, e))
            time.sleep(1.2)
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
        with io.open(p, "w", encoding="utf-8") as f:
            json.dump(prof, f, ensure_ascii=False, separators=(",", ":"))
        written += 1

    # 清掉已下榜玩家的旧文件：只删「本轮目标之外」的，抓取失败的保留旧版
    removed = 0
    if "--only" not in args and "--limit" not in args:
        valid = set(str(u) for u in targets)
        for fn in os.listdir(out_dir):
            if fn.endswith(".json") and fn[:-5] not in valid:
                try:
                    os.remove(os.path.join(out_dir, fn))
                    removed += 1
                except OSError:
                    pass

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
        targets = [s for s in servers if s["key"] == want]
        if not targets:
            raise SystemExit("没有这个服务器：%s（可选：%s）" % (
                want, "、".join(s["key"] for s in servers)))
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成跨区昵称索引：data/lookup-index.json

用途：查询页允许输入「昵称」而不是 UID。前端加载这一份索引（约 30KB），
在本地做模糊匹配，找到 uid 后复用原有的实时查询链路。

数据来源：各分区 gaoshoubang.json（榜单快照，随定时任务更新）。
隐私：hidden.json 里的玩家在生成榜单时已被剔除，这里天然拿不到。

用法： python scripts/build_lookup_index.py
"""
import io
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SERVERS = os.path.join(DATA, "servers")
OUT = os.path.join(DATA, "lookup-index.json")


def load_index_json():
    p = os.path.join(SERVERS, "index.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f).get("servers") or []
    except Exception:
        return []


def load_zhuan5():
    """苍松迎客 8 万普查里「传承 5 转」的玩家（[uid, 昵称]）。

    这部分人不在榜单上，但都是老玩家，用昵称搜得着比逐个查快得多。
    单独放在 data/cangsong-5zhuan.json，由 export_5zhuan 从普查表导出。
    """
    p = os.path.join(DATA, "cangsong-5zhuan.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f).get("players") or []
    except Exception:
        return []


def load_extra_names():
    """APK 查过的角色（data/extra-names.json）。

    这是**全局共享**的关键一环：任何用户查一次没收录的角色，APK 会把它
    POST 进 extra-names.json；这里把它并进 lookup-index.json，
    其他所有用户下次就都能按昵称搜到。没人被收录过，就永远是搜不到。
    """
    p = os.path.join(DATA, "extra-names.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f).get("items") or []
    except Exception:
        return []


def load_hidden():
    """返回 (uid 黑名单, [[uid, server], ...])。

    榜单生成时已剔除这些人，但 8 万普查导出的 5 转名单是另一条数据链路，
    必须在这里再挡一次，否则隐藏玩家会借昵称索引重新出现。
    """
    p = os.path.join(DATA, "hidden.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            rows = json.load(f).get("players") or []
    except Exception:
        return set(), []
    blocked, out = set(), []
    for x in rows:
        uid = str(x.get("uid") or "").strip()
        if not uid:
            continue
        blocked.add(uid)
        out.append([int(uid), str(x.get("server") or "")])
    return blocked, out


def main():
    hidden, hidden_out = load_hidden()
    servers = load_index_json()
    if not servers:
        # 兜底：直接从目录名推导
        names = {
            "taptap": "苍松迎客", "taptap_2": "白鹤亮翅", "taptap_3": "丹凤朝阳",
            "taptap_4": "墨羽惊鸿", "4399": "4399",
        }
        servers = [{"key": k, "name": v} for k, v in names.items()]

    players = []
    seen = set()
    boards = 0

    for srv in servers:
        key = srv.get("key")
        p = os.path.join(SERVERS, key, "gaoshoubang.json")
        if not os.path.isfile(p):
            continue
        try:
            with io.open(p, encoding="utf-8") as f:
                rows = json.load(f).get("rows") or []
        except Exception:
            continue
        boards += 1
        for r in rows:
            uid = r.get("userid")
            name = (r.get("name") or "").strip()
            if not uid or not name or str(uid) in hidden:
                continue
            k = (str(uid), key)
            if k in seen:
                continue
            seen.add(k)
            players.append({
                "u": int(uid),
                "n": name,
                "s": key,
                "sn": srv.get("name") or key,
                "lv": r.get("lv"),
                "m": r.get("menpai") or "",
                "r": r.get("rank"),
            })

    # 合并 APK 查过的角色：全局共享，别人查过的我也能搜到
    extra_added = 0
    for it in load_extra_names():
        if not isinstance(it, dict):
            continue
        uid = it.get("u")
        name = str(it.get("n") or "").strip()
        if uid is None or not name or str(uid) in hidden:
            continue
        key = str(it.get("s") or "taptap")
        k = (str(uid), key)
        if k in seen:
            # 榜单里已有：昵称以榜单为准（榜单是最新抓的），只补等级
            continue
        seen.add(k)
        extra_added += 1
        players.append({
            "u": int(uid),
            "n": name,
            "s": key,
            "sn": it.get("sn") or key,
            "lv": it.get("lv"),
            "m": "",
            "r": None,
        })

    # 按等级降序，前端同名多区时优先展示强的
    players.sort(key=lambda x: (-(x.get("lv") or 0), x["n"]))

    # 5 转玩家：不塞进 players，单独一组 [uid, 昵称]，前端合并时优先用榜单的
    zhuan5 = [x for x in load_zhuan5()
              if isinstance(x, list) and len(x) >= 2 and str(x[0]) not in hidden]
    board_uids = set(str(p["u"]) for p in players)
    zhuan5 = [x for x in zhuan5 if str(x[0]) not in board_uids]

    out = {
        "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updatedTs": int(time.time()),
        "boards": boards,
        "count": len(players),
        "players": players,
        "zhuan5": zhuan5,
        # 供 APK 在查询前拦截：这些 uid 不允许拉档案
        "hidden": hidden_out,
    }
    # 熔断：上游拉取失败时宁可让本轮失败，也不能静默把索引写成只剩榜单几百人，
    # 否则 APK 与网页会一起搜不到人，而且没人会收到告警。
    total = len(players) + len(zhuan5)
    prev_total = 0
    try:
        with io.open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        prev_total = int(old.get("count") or 0) + len(old.get("zhuan5") or [])
    except Exception:
        prev_total = 0
    if prev_total >= 500 and total < prev_total * 0.7:
        raise SystemExit(
            "索引人数从 %d 掉到 %d（-%.0f%%），疑似上游数据缺失，拒绝写入"
            % (prev_total, total, (1 - total / float(prev_total)) * 100))

    tmp = OUT + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, OUT)

    size = os.path.getsize(OUT)
    print("已生成 %s：%d 个分区 / %d 名玩家（含查过的 %d 人）/ 5 转 %d 人 / %.1f KB"
          % (OUT, boards, len(players), extra_added, len(zhuan5), size / 1024.0))


if __name__ == "__main__":
    main()

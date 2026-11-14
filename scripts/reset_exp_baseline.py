#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把经验快照的基准点重置为「当前这批档案值」。

背景：
  早先的快照（11 号那批）是直接从排行榜取的 exp，榜单个值是浮点且对不活跃玩家
  会长期不动；后来 merge_exp.py 把榜单 exp 改写成档案（get_user_info）的整数。
  两者混在一起算差值，就会出现「21.7 万」「-3.2 万」这种一眼假的增量 ——
  口径不同，差出来的不是真增长。

做法：
  对每个分区，用**档案值**重写一条基准快照（日期取今天），旧快照全部丢掉。
  之后每天的刷新都是同一口径，差值才是真的。

用法：
  python scripts/reset_exp_baseline.py            # 全部分区
  python scripts/reset_exp_baseline.py taptap_4   # 只重置某个分区
"""
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS = os.path.join(ROOT, "data", "servers")
BJ = 8 * 3600


def load(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write(path, obj, indent=None):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=indent,
                           separators=(",", ":") if indent is None else None))
    os.replace(tmp, path)


def reset(key):
    board_path = os.path.join(SERVERS, key, "gaoshoubang.json")
    board = load(board_path)
    if not board or not board.get("rows"):
        return None
    rows = board["rows"]
    prof_dir = os.path.join(SERVERS, key, "profiles")

    exp_map = {}
    from_profile = 0
    for r in rows:
        uid = str(r.get("userid"))
        p = load(os.path.join(prof_dir, uid + ".json")) or {}
        p_exp = p.get("exp")
        if isinstance(p_exp, (int, float)) and p_exp > 0:
            exp_map[uid] = p_exp
            from_profile += 1
        elif isinstance(r.get("exp"), (int, float)):
            # 没有档案就沿用榜单值：单个人口径不一致好过没有基准
            exp_map[uid] = r["exp"]

    now = time.time()
    entry = {
        "ts": int(now),
        "date": time.strftime("%Y-%m-%d", time.gmtime(now + BJ)),
        "time": time.strftime("%H:%M", time.gmtime(now + BJ)),
        "exp": exp_map,
        "src": "profile",
        "fresh": from_profile,
        "reset": "baseline-rebuilt",
    }
    hist_path = os.path.join(SERVERS, key, "exp-history.json")
    old = load(hist_path) or {}
    old_n = len(old.get("snapshots") or [])
    write(hist_path, {
        "updatedAt": entry["date"] + " " + entry["time"] + ":00",
        "snapshots": [entry],
    })
    return (len(rows), from_profile, old_n)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    keys = [only] if only else sorted(
        d for d in os.listdir(SERVERS)
        if os.path.isdir(os.path.join(SERVERS, d)))
    for k in keys:
        r = reset(k)
        if not r:
            print("  %-9s 跳过（没有榜单数据）" % k)
            continue
        total, prof, old_n = r
        print("  %-9s %3d 人 | 档案口径 %3d | 旧快照 %d 条 → 1 条基准"
              % (k, total, prof, old_n))


if __name__ == "__main__":
    main()

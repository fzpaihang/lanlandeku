#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把角色档案的经验合并进榜单，统一经验口径。

背景：get_board（排行榜）对不活跃玩家会长期返回旧值，而 get_user_info（档案）
更新更勤。榜单经验因此常比档案低 0.2%~1%，表现为「好几天不动，某天突然暴涨」。

规则：
  - 名次 rank 保留游戏原始值，**不按经验重排**（经验高但名次靠后是允许的）
  - 榜单原始经验存到 expBoard，方便回溯；exp 改写成档案值
  - 档案抓取失败（文件过旧）的玩家保留榜单经验，绝不倒退
  - 当天经验快照同步改写，保证「区间增长」用的是同一口径

用法：
  python scripts/merge_exp.py              # 全部分区
  python scripts/merge_exp.py --server taptap
"""
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SERVERS = os.path.join(DATA, "servers")
BJ_OFFSET = 8 * 3600

# 档案与榜单的时间差容忍：同一次刷新里档案晚 1~3 分钟，留 2 小时余量
FRESH_GAP = 2 * 3600
# 快照与榜单抓取时间差在这个范围内，视为同一轮，直接改写而不是新增
SNAP_GAP = 900


def bj_date(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(float(ts) + BJ_OFFSET))


def bj_time(ts, fmt="%Y-%m-%d %H:%M:%S"):
    return time.strftime(fmt, time.gmtime(float(ts) + BJ_OFFSET))


def load(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write(path, obj, indent=None):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=indent, separators=(",", ":") if indent is None else None))
    os.replace(tmp, path)


def merge_server(key, verbose=True):
    board_path = os.path.join(SERVERS, key, "gaoshoubang.json")
    board = load(board_path)
    if not board:
        return None
    rows = board.get("rows") or []
    if not rows:
        return None

    board_ts = int(board.get("updatedTs") or os.path.getmtime(board_path))
    prof_dir = os.path.join(SERVERS, key, "profiles")

    used = kept = 0
    max_delta = 0
    max_who = ""
    for r in rows:
        uid = str(r.get("userid"))
        board_exp = r.get("exp")
        # 只在首次合并时记录榜单原值：重复执行不能把 expBoard 覆盖成档案值
        if "expBoard" not in r:
            r["expBoard"] = board_exp

        p = load(os.path.join(prof_dir, uid + ".json"))
        p_ts = int((p or {}).get("updatedTs") or 0)
        p_exp = (p or {}).get("exp")

        if p and p_exp and p_ts and p_ts >= board_ts - FRESH_GAP:
            r["exp"] = p_exp
            r["expSrc"] = "profile"
            used += 1
            if isinstance(board_exp, (int, float)):
                base = r.get("expBoard", board_exp)
                d = abs(p_exp - base) if isinstance(base, (int, float)) else 0
                if d > max_delta:
                    max_delta, max_who = d, r.get("name") or uid
        else:
            r["expSrc"] = "board"
            kept += 1

    board["expSrc"] = "mixed"      # 表格里可能混着两种来源，逐行看 expSrc
    board["mergedAt"] = bj_time(time.time())
    write(board_path, board, indent=1)

    # 经验快照：把本轮快照的 exp 换成合并后的值
    hist_path = os.path.join(SERVERS, key, "exp-history.json")
    hist = load(hist_path) or {"snapshots": []}
    snaps = hist.get("snapshots") or []
    exp_map = {}
    for r in rows:
        if r.get("exp") is not None:
            exp_map[str(r.get("userid"))] = r["exp"]

    entry = {
        "ts": board_ts or int(time.time()),
        "date": bj_date(board_ts or time.time()),
        "time": bj_time(board_ts or time.time(), "%H:%M"),
        "exp": exp_map,
        "src": "profile",
    }
    if snaps and abs(int(snaps[-1].get("ts", 0)) - entry["ts"]) <= SNAP_GAP:
        snaps[-1] = entry                      # 同一轮：直接改写，避免出现两条
    elif snaps and snaps[-1].get("date") == entry["date"]:
        snaps[-1] = entry                      # 同一天手动重跑：覆盖最后一条
    else:
        snaps.append(entry)
    hist["snapshots"] = snaps[-60:]
    hist["updatedAt"] = bj_time(time.time())
    write(hist_path, hist)

    if verbose:
        pct = (max_delta / 1e8) if max_delta else 0
        print("  %-9s %3d 人 | 用档案 %3d | 保留榜单 %3d | 最大差 %.0f 万（%s）"
              % (key, len(rows), used, kept, max_delta / 1e4, max_who))
        if pct:
            pass
    return {"key": key, "total": len(rows), "used": used, "kept": kept}


def main():
    want = None
    if "--server" in sys.argv:
        want = sys.argv[sys.argv.index("--server") + 1]
        want = [x.strip() for x in want.split(",") if x.strip()]

    keys = want or sorted([
        d for d in os.listdir(SERVERS)
        if os.path.isdir(os.path.join(SERVERS, d)) and d != "__pycache__"
    ])

    print("合并档案经验 → 榜单")
    total_used = total_kept = 0
    for k in keys:
        if not os.path.isfile(os.path.join(SERVERS, k, "gaoshoubang.json")):
            continue
        r = merge_server(k)
        if r:
            total_used += r["used"]
            total_kept += r["kept"]
    print("完成：档案经验 %d 人 / 保留榜单 %d 人" % (total_used, total_kept))


if __name__ == "__main__":
    main()

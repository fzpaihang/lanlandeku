# -*- coding: utf-8 -*-
"""看门狗：找出「今天该更新却没更新」的榜单，供 watchdog.yml 自动补跑。

为什么需要它：刷新链路上任何一环失败（最典型是游戏接口限流 20616 让翻页中途
断掉、整轮作废），那个区当天就没有数据，网页上会表现为「11-19 的数据直接
跳到 11-21」。fetch.py 里已经有单页冷却重试，refresh.yml 里也有整轮 3 次重试，
但仍然存在「三次都撞上限流窗口」的可能，这里做最后一道兜底。

用法（CI）：
  python scripts/check_stale.py >> "$GITHUB_OUTPUT"
用法（本地看当前状态）：
  python scripts/check_stale.py --hours 26

输出两行 key=value：
  servers=taptap,taptap_4      # 高手榜过期的分区（逗号分隔，空表示都新鲜）
  hall=1                       # 名人堂过期则为 1，否则 0
退出码恒为 0：本脚本只负责报告，是否补跑由工作流决定。
"""
import argparse
import calendar
import io
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(BASE_DIR, "data", "servers")


def read_json(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def updated_ts(payload):
    """文件里的更新时间（秒）。优先 updatedTs，退回解析 updatedAt 的北京时间。

    必须用 calendar.timegm 而不是 time.mktime：updatedAt 记的是北京时间（UTC+8），
    timegm 把字符串当 UTC 解析、时区无关；mktime 会按「运行机器本地时区」解析，
    在 UTC+8 的机器上就会把时间算早 8 小时（本地自测过，差 28800 秒）。
    """
    if not isinstance(payload, dict):
        return 0
    ts = payload.get("updatedTs")
    if isinstance(ts, (int, float)) and ts > 0:
        return float(ts)
    s = payload.get("updatedAt") or ""
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M:%S")) - 8 * 3600
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=26,
                    help="高手榜多久没更新算过期（每区一天一轮，默认 26 小时）")
    ap.add_argument("--hall-hours", type=float, default=30,
                    help="名人堂多久没更新算过期（每天 20:00 一轮，默认 30 小时）")
    a = ap.parse_args()

    idx = read_json(os.path.join(SERVER_DIR, "index.json")) or {}
    keys = [s.get("key") for s in (idx.get("servers") or []) if s.get("key")]
    if not keys:
        # index.json 缺失时退回扫目录，别因为一个文件就让看门狗瞎掉
        keys = sorted(d for d in os.listdir(SERVER_DIR)
                      if os.path.isdir(os.path.join(SERVER_DIR, d))) if os.path.isdir(SERVER_DIR) else []

    now = time.time()
    stale, fresh = [], []
    for k in keys:
        p = os.path.join(SERVER_DIR, k, "gaoshoubang.json")
        if not os.path.exists(p):
            stale.append(k)
            continue
        age = (now - updated_ts(read_json(p))) / 3600.0
        (stale if age > a.hours else fresh).append(k)
        print("# %-12s %5.1f 小时前" % (k, age), file=sys.stderr)

    hall_path = os.path.join(SERVER_DIR, "..", "hall.json")
    hall_stale = 0
    hall_age = None
    if os.path.exists(hall_path):
        hall_age = (now - updated_ts(read_json(hall_path))) / 3600.0
        if hall_age > a.hall_hours:
            hall_stale = 1
    else:
        # 没有汇总文件时按分区各自 hall.json 判（现阶段是每区一份）
        hall_ages = []
        for k in keys:
            hp = os.path.join(SERVER_DIR, k, "hall.json")
            if os.path.exists(hp):
                hall_ages.append((now - updated_ts(read_json(hp))) / 3600.0)
        if hall_ages and max(hall_ages) > a.hall_hours:
            hall_stale = 1
        hall_age = max(hall_ages) if hall_ages else None

    print("# 过期高手榜：%s" % ("、".join(stale) or "无"), file=sys.stderr)
    print("# 名人堂最大年龄：%s" % ("%.1f 小时" % hall_age if hall_age is not None else "无数据"),
          file=sys.stderr)
    print("servers=%s" % ",".join(stale))
    print("hall=%d" % hall_stale)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
  hall=hall_b1,hall_b3         # 名人堂过期批次（hall_b1/b2/b3，空表示都新鲜）

名人堂按批次判（2026-11-26 起十一区拆成三批定时抓，见 plan_refresh.HALL_BATCHES）：
哪一批的 hall.json 超过 --hall-hours 没更新就派那一批，不用为一批过期把十一区全跑一遍。
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

# 名人堂分批定义只留一份在 plan_refresh.py（cron → 批次 → 分区都归它管），
# 这里 import 进来判过期，加批次时不用改两处。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_refresh import HALL_BATCHES  # noqa: E402


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

    # 名人堂按批次判：十一区拆成三批定时抓（plan_refresh.HALL_BATCHES），
    # 每批只看自己那几个区的 hall.json，任一批过期就只补那一批，
    # 不用为一批过期把十一区 950 份档案全重抓一遍（那正是会超时的原因）。
    hall_stale_batches = []
    for batch, bkeys in HALL_BATCHES.items():
        b_path = os.path.join(SERVER_DIR, "..", "hall.json")
        b_age = None
        if os.path.exists(b_path):
            # 汇总文件存在就全批共用它（现阶段不产出，留作以后合并成单文件）
            b_age = (now - updated_ts(read_json(b_path))) / 3600.0
        else:
            b_ages = []
            for k in bkeys:
                hp = os.path.join(SERVER_DIR, k, "hall.json")
                if os.path.exists(hp):
                    b_ages.append((now - updated_ts(read_json(hp))) / 3600.0)
            b_age = max(b_ages) if b_ages else None
        if b_age is None:
            print("# %-8s 无数据（该批 hall.json 还没产出）" % batch, file=sys.stderr)
            hall_stale_batches.append(batch)
        else:
            print("# %-8s %5.1f 小时前" % (batch, b_age), file=sys.stderr)
            if b_age > a.hall_hours:
                hall_stale_batches.append(batch)

    print("# 过期高手榜：%s" % ("、".join(stale) or "无"), file=sys.stderr)
    print("# 过期名人堂批次：%s" % ("、".join(hall_stale_batches) or "无"), file=sys.stderr)
    print("servers=%s" % ",".join(stale))
    print("hall=%s" % ",".join(hall_stale_batches))
    return 0


if __name__ == "__main__":
    sys.exit(main())

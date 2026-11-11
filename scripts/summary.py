# -*- coding: utf-8 -*-
"""输出一份 Markdown 摘要，供 GitHub Actions 的 Step Summary 使用（支持多分区）"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
SRV_DIR = os.path.join(DATA, "servers")


def read_json(p):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    print("### 刷新结果\n")

    idx = read_json(os.path.join(SRV_DIR, "index.json"))
    servers = (idx or {}).get("servers") or []

    if not servers:
        print("- **没有找到分区数据**（data/servers/index.json 缺失，说明本轮抓取没跑起来）")
        return 1

    # 单分区任务只看本次目标，避免把没参与本轮的分区也列进来
    args = sys.argv[1:]
    if "--server" in args:
        want = args[args.index("--server") + 1]
        keys = [x.strip() for x in want.split(",") if x.strip()]
        servers = [s for s in servers if s.get("key") in keys]
        if not servers:
            print("- **本次目标分区 `%s` 不在 index.json 里** ❌" % want)
            return 1

    ok = True
    for s in servers:
        key, name = s.get("key"), s.get("name") or s.get("key")
        d = read_json(os.path.join(SRV_DIR, key, "gaoshoubang.json"))
        if not d:
            print("- **%s**：没有榜单数据 ❌" % name)
            ok = False
            continue

        line = "- **%s**：%d 人，更新于 %s" % (name, d.get("total", 0), d.get("updatedAt"))

        pd = os.path.join(SRV_DIR, key, "profiles")
        if os.path.isdir(pd):
            n = len([f for f in os.listdir(pd) if f.endswith(".json")])
            line += "，档案 %d 份" % n

        h = read_json(os.path.join(SRV_DIR, key, "exp-history.json"))
        if h:
            snaps = h.get("snapshots", [])
            if snaps:
                line += "，经验快照 %d 条（最近 %s %s）" % (
                    len(snaps), snaps[-1].get("date", ""), snaps[-1].get("time", ""))

        print(line)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

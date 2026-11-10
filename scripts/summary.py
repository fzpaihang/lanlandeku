# -*- coding: utf-8 -*-
"""输出一份 Markdown 摘要，供 GitHub Actions 的 Step Summary 使用"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "data")


def main():
    print("### 刷新结果\n")
    ok = True

    p = os.path.join(D, "gaoshoubang.json")
    if os.path.exists(p):
        try:
            d = json.load(io.open(p, encoding="utf-8"))
            print("- 榜单：**%d 人**，更新于 %s" % (d.get("total", 0), d.get("updatedAt")))
        except Exception as e:
            print("- 榜单：解析失败 %s" % e)
            ok = False
    else:
        print("- 榜单：**未生成**")
        ok = False

    pd = os.path.join(D, "profiles")
    if os.path.isdir(pd):
        files = [f for f in os.listdir(pd) if f.endswith(".json")]
        size = sum(os.path.getsize(os.path.join(pd, f)) for f in files) / 1024.0
        print("- 档案：%d 份，%.0f KB" % (len(files), size))

    h = os.path.join(D, "exp-history.json")
    if os.path.exists(h):
        try:
            d = json.load(io.open(h, encoding="utf-8"))
            snaps = d.get("snapshots", [])
            tail = ("，最近 %s %s" % (snaps[-1]["date"], snaps[-1]["time"])) if snaps else ""
            print("- 经验快照：%d 条%s" % (len(snaps), tail))
        except Exception:
            pass

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 html 里 assets 引用的 ?v= 刷成文件内容哈希。

改完 style.css / *.js 后跑一次即可，不用再手动递增版本号；
内容没变则不会改动文件，可以放心重复执行。

用法： python scripts/stamp_assets.py
"""
import hashlib
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["index.html", "exp.html"]
REF = re.compile(r'(href|src)="(\./assets/[^"?]+\.(?:css|js))(?:\?v=[^"]*)?"')


def digest(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:8]


def stamp(page):
    path = os.path.join(ROOT, page)
    with open(path, "rb") as f:
        src = f.read().decode("utf-8")

    seen = []

    def rep(m):
        attr, url = m.group(1), m.group(2)
        target = os.path.normpath(os.path.join(ROOT, url))
        if not os.path.exists(target):
            print("  ! 引用不存在：%s（%s）" % (url, page))
            return m.group(0)
        h = digest(target)
        seen.append("%s=%s" % (os.path.basename(url), h))
        return '%s="%s?v=%s"' % (attr, url, h)

    out = REF.sub(rep, src)
    if out != src:
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
        return True, seen
    return False, seen


def main():
    changed = 0
    for page in PAGES:
        hit, seen = stamp(page)
        changed += 1 if hit else 0
        print("%-11s %s  %s" % (page, "更新" if hit else "无需改动", " ".join(seen)))
    print("完成：%d 个页面被更新" % changed)


if __name__ == "__main__":
    main()

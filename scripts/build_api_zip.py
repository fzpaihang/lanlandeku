#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包腾讯云 SCF 部署包：api/build/fzjh-lookup-api.zip

包里 = api/index.py（入口）+ apk/ 下已跑通的协议核心（fetch / lookup_core / aes_pure / names.json）。
协议核心**只有 apk/ 一份源**，这里只做复制，避免两份代码各自漂移。

用法： python scripts/build_api_zip.py [--stage-only]
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "api")
APK = os.path.join(ROOT, "apk")
DATA = os.path.join(ROOT, "data", "servers")
BUILD = os.path.join(API, "build")
STAGE = os.path.join(BUILD, "staging")
ZIP_PATH = os.path.join(BUILD, "fzjh-lookup-api.zip")

# 源文件 → 包内文件名
COPIES = [
    (os.path.join(API, "index.py"), "index.py"),
    (os.path.join(APK, "fetch.py"), "fetch.py"),
    (os.path.join(APK, "lookup_core.py"), "lookup_core.py"),
    (os.path.join(APK, "aes_pure.py"), "aes_pure.py"),
    (os.path.join(APK, "names.json"), "names.json"),
]


def main():
    for src, _ in COPIES:
        if not os.path.exists(src):
            raise SystemExit("缺少源文件：%s" % src)

    if os.path.isdir(STAGE):
        # 逐个删文件而不是 rmtree：部分环境把 rmtree 重定向到回收站会失败
        for name in os.listdir(STAGE):
            path = os.path.join(STAGE, name)
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
    os.makedirs(STAGE, exist_ok=True)

    for src, name in COPIES:
        shutil.copy2(src, os.path.join(STAGE, name))

    # 榜单打包：补排名/福缘/门派用，104 KB，避免云函数每次查都去连 github.io
    boards_dir = os.path.join(STAGE, "boards")
    os.makedirs(boards_dir, exist_ok=True)
    n_boards = 0
    if os.path.isdir(DATA):
        for key in sorted(os.listdir(DATA)):
            src = os.path.join(DATA, key, "gaoshoubang.json")
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(boards_dir, key + ".json"))
                n_boards += 1
    print("已打包榜单 %d 个分区" % n_boards)

    # 语法自检：包里的每个 .py 都要能编译
    for name in os.listdir(STAGE):
        if name.endswith(".py"):
            path = os.path.join(STAGE, name)
            with open(path, "r", encoding="utf-8") as f:
                compile(f.read(), path, "exec")

    if "--stage-only" in sys.argv:
        print("已生成 staging：%s" % STAGE)
        return

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for root_dir, _dirs, files in os.walk(STAGE):
            for fname in sorted(files):
                full = os.path.join(root_dir, fname)
                arc = os.path.relpath(full, STAGE).replace(os.sep, "/")
                z.write(full, arc)

    size = os.path.getsize(ZIP_PATH)
    print("部署包：%s（%.1f KB）" % (ZIP_PATH, size / 1024.0))
    with zipfile.ZipFile(ZIP_PATH) as z:
        for info in z.infolist():
            print("  %-18s %7d 字节" % (info.filename, info.file_size))


if __name__ == "__main__":
    main()

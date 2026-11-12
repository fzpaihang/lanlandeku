# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询 —— 启动器

职责（尽量保持稳定，非必要不改）：
  1. 比对远程版本号
  2. 有新版本就下载 code.zip → 校验 → 解压到 live/
  3. 把 live/ 插到 sys.path 最前面，加载 app_ui 启动界面
  4. 任何一步失败都静默回退到 APK 内置代码，保证一定能打开

因此日常改界面/逻辑只需要更新远程 code.zip，用户不必重装 APK。
"""
import hashlib
import io
import json
import os
import shutil
import sys
import traceback
import zipfile

import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_BASE = "https://fzpaihang.github.io/lanlandeku/apk/update/"
# 安卓上 ANDROID_PRIVATE 是应用可写目录；桌面调试时退回脚本目录
DATA_DIR = os.environ.get("ANDROID_PRIVATE") or HERE
LIVE_DIR = os.path.join(DATA_DIR, "live")
VERSION_FILE = os.path.join(LIVE_DIR, "version.txt")

REQUIRED = ("app_ui.py", "lookup_core.py", "fetch.py", "aes_pure.py")


def log(msg):
    try:
        print("[launcher] %s" % msg)
    except Exception:
        pass


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "fzjh-lookup"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local_version():
    try:
        with io.open(VERSION_FILE, encoding="utf-8") as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def is_valid_dir(d):
    """检查代码包是否完整且能编译通过——避免把坏包放进来导致打不开"""
    for f in REQUIRED:
        p = os.path.join(d, f)
        if not os.path.exists(p):
            log("缺少文件 %s" % f)
            return False
        try:
            with io.open(p, encoding="utf-8") as fp:
                compile(fp.read(), p, "exec")
        except Exception as e:
            log("%s 语法检查失败：%s" % (f, e))
            return False
    return True


def install(ver, md5):
    log("发现新版本 v%s，开始下载" % ver)
    blob = http_get(UPDATE_BASE + "code.zip", 20)
    if md5:
        got = hashlib.md5(blob).hexdigest()
        if got != md5:
            raise RuntimeError("md5 不匹配（本地 %s，期望 %s）" % (got, md5))

    tmp = LIVE_DIR + ".new"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        root = os.path.normpath(tmp)
        for n in z.namelist():
            if n.endswith("/"):
                continue
            target = os.path.normpath(os.path.join(tmp, n))
            if not target.startswith(root + os.sep):   # 防目录穿越
                continue
            parent = os.path.dirname(target)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with z.open(n) as src, open(target, "wb") as out:
                out.write(src.read())

    if not is_valid_dir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("代码包校验不通过，已丢弃")

    with io.open(os.path.join(tmp, "version.txt"), "w", encoding="utf-8") as f:
        f.write(str(ver))

    if os.path.isdir(LIVE_DIR):
        shutil.rmtree(LIVE_DIR, ignore_errors=True)
    os.rename(tmp, LIVE_DIR)
    log("已切换到 v%s" % ver)


def ensure_code():
    """返回可用代码目录；None 表示用 APK 内置代码"""
    remote_ver = 0
    md5 = ""
    try:
        raw = http_get(UPDATE_BASE + "version.json", 5)
        info = json.loads(raw.decode("utf-8"))
        remote_ver = int(info.get("version") or 0)
        md5 = info.get("md5") or ""
    except Exception as e:
        log("检查更新失败（忽略）：%s" % e)

    if remote_ver and remote_ver > local_version():
        try:
            install(remote_ver, md5)
        except Exception as e:
            log("更新未完成，继续用现有版本：%s" % e)

    if os.path.isdir(LIVE_DIR) and os.path.exists(os.path.join(LIVE_DIR, "app_ui.py")):
        return LIVE_DIR
    return None


def main():
    code_dir = ensure_code()
    if code_dir:
        sys.path.insert(0, code_dir)
        log("加载更新包：%s" % code_dir)
    else:
        log("加载 APK 内置代码")

    for m in ("app_ui", "lookup_core", "fetch", "aes_pure"):
        sys.modules.pop(m, None)

    import app_ui
    app_ui.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("启动失败，回退到内置代码\n" + traceback.format_exc())
        if LIVE_DIR in sys.path:
            sys.path.remove(LIVE_DIR)
        for m in ("app_ui", "lookup_core", "fetch", "aes_pure"):
            sys.modules.pop(m, None)
        import app_ui as _fallback
        _fallback.run()

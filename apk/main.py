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
import ssl
import sys
import traceback
import zipfile

import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_BASE = "https://fzpaihang.github.io/lanlandeku/apk/update/"
UPDATE_MIRROR = "https://cdn.jsdelivr.net/gh/fzpaihang/lanlandeku@main/apk/update/"
# 安卓上 ANDROID_PRIVATE 是应用可写目录；桌面调试时退回脚本目录
DATA_DIR = os.environ.get("ANDROID_PRIVATE") or HERE
LIVE_DIR = os.path.join(DATA_DIR, "live")
VERSION_FILE = os.path.join(LIVE_DIR, "version.txt")

REQUIRED = ("app_ui.py", "lookup_core.py", "fetch.py", "aes_pure.py")

# 更新包签名公钥（Ed25519，私钥只在本地 .keys/ 里，不进仓库）
UPDATE_PUBKEY = bytes.fromhex(
    "22d04f4b1494904f306117f2c1bdb07df7b7b3c7cc4cf7ddf191739b7f80bf0e")


def verify_package(meta, blob):
    """校验更新包签名。

    签名同时覆盖 version/md5/size 三个字段和整包字节，任一处被改都会失败。
    返回 True/False；老格式（无 sig 字段）返回 None，调用方按「未签名」处理。
    """
    sig_hex = (meta or {}).get("sig") or ""
    if not sig_hex:
        return None
    try:
        import ed25519
        msg = ("%s|%s|%s|" % (meta.get("version"), meta.get("md5"),
                              meta.get("size"))).encode("utf-8") + blob
        return ed25519.verify(UPDATE_PUBKEY, msg, bytes.fromhex(sig_hex))
    except Exception as e:
        log("验签异常：%r" % (e,))
        return False


def log(msg):
    try:
        print("[launcher] %s" % msg)
    except Exception:
        pass


def _ca_file():
    """找内置 CA 包（p4a 的 Python 不带 Android 系统根证书）。

    新 APK 会把它放在 app 目录；热更包也会带一份到 live/，老 APK 更新一次
    之后同样能吃到校验。
    """
    cands = []
    app = os.environ.get("ANDROID_APP_PATH")
    if app:
        cands.append(os.path.join(app, "cacert.pem"))
    cands.append(os.path.join(HERE, "cacert.pem"))
    cands.append(os.path.join(LIVE_DIR, "cacert.pem"))
    for p in cands:
        if os.path.exists(p):
            return p
    return None


def _ssl_ctx():
    ca = _ca_file()
    if ca:
        ctx = ssl.create_default_context(cafile=ca)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        log("TLS 校验已开启（CA: %s）" % os.path.basename(ca))
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    log("未找到内置 CA，更新通道暂不校验证书（内容仍由签名保证）")
    return ctx


SSL_CTX = _ssl_ctx()


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "fzjh-lookup"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()


def fetch_update(name, timeout):
    """主源失败自动切 jsDelivr 镜像；两个都失败才抛错。"""
    last = None
    for base in (UPDATE_BASE, UPDATE_MIRROR):
        try:
            return http_get(base + name, timeout)
        except Exception as e:
            last = e
            log("更新源 %s 失败：%s" % (base.split("/")[2], e))
    raise last


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


def install(ver, md5, meta=None):
    log("发现新版本 v%s，开始下载" % ver)
    blob = fetch_update("code.zip", 25)
    if md5:
        got = hashlib.md5(blob).hexdigest()
        if got != md5:
            raise RuntimeError("md5 不匹配（本地 %s，期望 %s）" % (got, md5))

    # md5 是同一个通道取回来的，能改包的人也能改 md5；签名才是真正的校验
    verdict = verify_package(meta or {"version": ver, "md5": md5,
                                      "size": len(blob)}, blob)
    if verdict is False:
        raise RuntimeError("更新包签名校验失败，已丢弃")
    if verdict is None:
        log("更新包未签名（旧格式），仅校验 md5")

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
    meta = {}
    try:
        raw = fetch_update("version.json", 8)
        info = json.loads(raw.decode("utf-8"))
        meta = info
        remote_ver = int(info.get("version") or 0)
        md5 = info.get("md5") or ""
    except Exception as e:
        log("检查更新失败（忽略）：%s" % e)

    if remote_ver and remote_ver > local_version():
        try:
            install(remote_ver, md5, meta)
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

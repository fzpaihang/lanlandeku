# -*- coding: utf-8 -*-
"""生成 APK 热更包：apk/update/code.zip + version.json

热更只更新代码，不碰安装包。用户重启 App 时启动器会比对 version.json，
发现新版本就下载、校验、解压到 live/，下次启动即生效。

用法： python scripts/pack_update.py "本次更新说明"
"""
import hashlib
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(ROOT, "apk")
OUT = os.path.join(APK, "update")

# 启动器会把 live/ 插到 sys.path 最前面，这里的模块必须都带上。
# main.py 的 REQUIRED 只校验最早那 4 个，新增模块靠 app_ui 里的 try/except 兜底，
# 这样万一某个包漏了文件，也只是降级而不会打不开。
FILES = [
    "app_ui.py",
    "lookup_core.py",
    "fetch.py",
    "aes_pure.py",
    "names_index.py",
    "archive_local.py",
    "webview_overlay.py",
    "skill_groups.py",
    "skill_class.py",
]


def main():
    notes = sys.argv[1] if len(sys.argv) > 1 else "更新"
    os.makedirs(OUT, exist_ok=True)

    ver = 0
    vf = os.path.join(OUT, "version.json")
    if os.path.exists(vf):
        try:
            with io.open(vf, encoding="utf-8") as f:
                ver = int(json.load(f).get("version") or 0)
        except Exception:
            ver = 0
    new_ver = ver + 1

    missing = [f for f in FILES if not os.path.exists(os.path.join(APK, f))]
    if missing:
        raise SystemExit("缺少文件：%s" % ", ".join(missing))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, 9) as z:
        for name in FILES:
            z.write(os.path.join(APK, name), name)
    blob = buf.getvalue()

    with open(os.path.join(OUT, "code.zip"), "wb") as f:
        f.write(blob)

    info = {
        "version": new_ver,
        "md5": hashlib.md5(blob).hexdigest(),
        "size": len(blob),
        "notes": notes,
        "builtAt": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }
    with io.open(vf, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")

    print("已生成 v%d：%d 个文件 / %.1f KB / md5 %s"
          % (new_ver, len(FILES), len(blob) / 1024.0, info["md5"]))
    print("说明：%s" % notes)


if __name__ == "__main__":
    main()

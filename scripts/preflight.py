# -*- coding: utf-8 -*-
"""发布前自检：一条命令跑完所有「忘了就会出事」的检查。

背景：这个项目的坑大多是「不报错但没生效」——缓存戳没刷、热更包没重打、
两份 names.json 漂移、等级口径三处不一致、隐私名单硬编码与 json 不同步。
这些都靠人记，本脚本把它们变成可执行检查。

用法：
  python scripts/preflight.py           # 全部检查
  python scripts/preflight.py --fix     # 额外跑 stamp_assets.py 修缓存戳
  python scripts/preflight.py --quiet   # 只打印失败/警告

退出码：0 = 无失败（允许有 WARN）；1 = 有 FAIL。

不做的事：不改业务代码、不提交、不访问网络。
"""
import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

try:
    # 用 reconfigure 而不是新建 TextIOWrapper：本脚本会 import apk/fetch.py，
    # 它也会包装 stdout，多套一层会让旧包装器被回收并关掉底层 buffer。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(ROOT, "apk")
QUIET = "--quiet" in sys.argv

results = []   # (level, name, detail)


def ok(name, detail=""):
    results.append(("PASS", name, detail))


def warn(name, detail=""):
    results.append(("WARN", name, detail))


def fail(name, detail=""):
    results.append(("FAIL", name, detail))


def read(path, mode="r"):
    if mode == "rb":
        with open(path, "rb") as f:
            return f.read()
    with io.open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 1. 语法
def check_python_syntax():
    bad, n = [], 0
    skip = ("__pycache__", os.sep + "api" + os.sep + "build", "node_modules", ".wrangler")
    for base, dirs, files in os.walk(ROOT):
        if any(s.strip(os.sep) in base for s in skip):
            continue
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", ".wrangler")]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(base, fn)
            n += 1
            try:
                ast.parse(read(p))
            except SyntaxError as e:
                bad.append("%s:%s %s" % (os.path.relpath(p, ROOT), e.lineno, e.msg))
    if bad:
        fail("Python 语法", "；".join(bad[:5]))
    else:
        ok("Python 语法", "%d 个文件" % n)


def node_bin():
    p = shutil.which("node")
    if p:
        return p
    cand = r"C:/Users/shaob/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
    return cand if os.path.exists(cand) else None


def check_js_syntax():
    node = node_bin()
    targets = sorted(
        os.path.join("assets", f) for f in os.listdir(os.path.join(ROOT, "assets"))
        if f.endswith(".js")
    )
    if not node:
        warn("JS 语法", "未找到 node，已跳过（%d 个文件）" % len(targets))
        return
    bad = []
    for rel in targets:
        p = subprocess.run([node, "--check", os.path.join(ROOT, rel)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            bad.append("%s: %s" % (rel, p.stderr.decode("utf-8", "replace").strip().splitlines()[:1]))
    if bad:
        fail("JS 语法", "；".join(str(x) for x in bad[:3]))
    else:
        ok("JS 语法", "%d 个文件（%s）" % (len(targets), os.path.basename(node)))


# ------------------------------------------------------------ 2. 缓存戳
REF_RE = re.compile(r"assets/([\w.\-]+\.(?:js|css))(?:\?v=([0-9a-fA-F]+))?")


def check_stamps():
    from hashlib import md5
    pages = [f for f in os.listdir(ROOT) if f.endswith(".html")]
    bad, stale, total = [], [], 0
    for page in sorted(pages):
        html = read(os.path.join(ROOT, page))
        for name, ver in REF_RE.findall(html):
            if not name.endswith((".js", ".css")):
                continue
            fp = os.path.join(ROOT, "assets", name)
            if not os.path.exists(fp):
                bad.append("%s 引用不存在的 assets/%s" % (page, name))
                continue
            total += 1
            cur = md5(read(fp, "rb")).hexdigest()[:8]
            if not ver:
                stale.append("%s -> %s 无 ?v=" % (page, name))
            elif ver.lower() != cur:
                stale.append("%s -> %s?v=%s 实际 %s" % (page, name, ver, cur))
    if bad:
        fail("缓存戳", "；".join(bad))
    elif stale:
        fail("缓存戳", "需跑 stamp_assets.py：" + "；".join(stale[:4]))
    else:
        ok("缓存戳", "%d 处引用均为最新" % total)


# -------------------------------------------------------- 3. 热更包一致性
def load_pack_module():
    p = os.path.join(ROOT, "scripts", "pack_update.py")
    spec = importlib.util.spec_from_file_location("pack_update", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check_update_pack():
    vf = os.path.join(APK, "update", "version.json")
    zf = os.path.join(APK, "update", "code.zip")
    if not os.path.exists(vf) or not os.path.exists(zf):
        warn("热更包", "version.json / code.zip 不齐，跳过")
        return
    try:
        info = json.loads(read(vf))
    except Exception as e:
        fail("热更包", "version.json 解析失败：%r" % (e,))
        return
    blob = read(zf, "rb")
    problems = []
    if hashlib.md5(blob).hexdigest() != info.get("md5"):
        problems.append("md5 不匹配")
    if len(blob) != info.get("size"):
        problems.append("size 不匹配")
    if not info.get("sig"):
        problems.append("缺 sig")

    try:
        pk = load_pack_module()
        missing = [f for f in pk.FILES + pk.EXTRA if not os.path.exists(os.path.join(APK, f))]
        if missing:
            problems.append("包内清单缺文件：%s" % ", ".join(missing))
        # 启动器 REQUIRED 必须都在热更包里，否则新装机会降级
        tree = ast.parse(read(os.path.join(APK, "main.py")))
        required = []
        for n in tree.body:
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "REQUIRED" for t in n.targets):
                required = list(ast.literal_eval(n.value))
        not_packed = [f for f in required if f not in pk.FILES]
        if not_packed:
            problems.append("REQUIRED 不在热更包：%s" % ", ".join(not_packed))
    except Exception as e:
        problems.append("读取打包清单失败：%r" % (e,))

    # 热更包内容是否与源码逐字节一致。
    # 不能用 mtime：git 检出 / reset 会把文件时间刷新，导致整包被误判为「源码更新」。
    try:
        with zipfile.ZipFile(zf) as z:
            names = set(z.namelist())
            diff = []
            for f in pk.FILES + pk.EXTRA:
                if f not in names:
                    diff.append(f + "（包里缺）")
                elif z.read(f) != read(os.path.join(APK, f), "rb"):
                    diff.append(f)
        if diff:
            problems.append("热更包与源码不一致，需重新打包：%s" % ", ".join(diff[:4]))
    except Exception as e:
        problems.append("热更包比对失败：%r" % (e,))

    # 本地验签（需私钥；没有私钥就跳过，不误报）
    key = os.path.join(ROOT, ".keys", "update.key")
    if os.path.exists(key) and os.path.exists(os.path.join(APK, "ed25519.py")):
        try:
            sys.path.insert(0, APK)
            import ed25519
            seed = read(key, "rb")
            msg = ("%s|%s|%s|" % (info["version"], info["md5"], info["size"])).encode() + blob
            if not ed25519.verify(ed25519.public_key(seed), msg, bytes.fromhex(info["sig"])):
                problems.append("Ed25519 验签失败")
        except Exception as e:
            problems.append("验签异常：%r" % (e,))

    if problems:
        fail("热更包 v%s" % info.get("version"), "；".join(problems[:4]))
    else:
        ok("热更包 v%s" % info.get("version"),
           "%.1f KB / md5 %s… / 验签通过" % (len(blob) / 1024.0, str(info.get("md5"))[:12]))


# ------------------------------------------------------------ 4. 等级口径
def check_level_parity():
    cases = [8, 7, 5.9, 0, -1, 0.015 * 92 ** 3 + 1, 0.015 * 93 ** 3 + 1,
             0.015 * 499 ** 3 + 1, 0.015 * 500 ** 3 + 1,
             0.015 * 999 ** 3 + 1, 0.015 * 1099 ** 3 + 1,
             0.015 * 1100 ** 3 + 1, 0.015 * 1200 ** 3 + 1, 19965001.0]
    try:
        sys.path.insert(0, APK)
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import lookup_core as L            # noqa: E402
        import fetch_profiles as P         # noqa: E402
        diffs = []
        for c in cases:
            a, b = L.lv_of_skill(c), P.lv_of(c)
            if a != b:
                diffs.append("exp=%.0f apk=%s scripts=%s" % (c, a, b))
        if diffs:
            fail("等级口径", "；".join(diffs[:3]))
        else:
            ok("等级口径", "apk 与 scripts 一致（满级 %s）" % L.lv_of_skill(cases[11]))
    except Exception as e:
        fail("等级口径", "导入失败：%r" % (e,))
        return

    # Worker 不导出 lvOfSkill，只能做源码级断言
    try:
        src = read(os.path.join(ROOT, "worker", "src", "profile.js"))
        if "Math.ceil" not in src or "SKILL_LV_MAX" not in src or "Math.trunc(Math.pow" in src:
            warn("等级口径(worker)", "profile.js 可能不是 ceil 口径（未上线，仅提示）")
    except Exception:
        pass

    # 云函数 staging 是构建产物，过期只提示
    st = os.path.join(ROOT, "api", "build", "staging", "lookup_core.py")
    if os.path.exists(st):
        s = read(st)
        if "ceil" not in s:
            warn("云函数 staging", "仍是旧 int() 副本；恢复云函数前先跑 build_api_zip.py")


# --------------------------------------------------------- 5. 两份 names
def check_names():
    a = os.path.join(ROOT, "data", "names.json")
    b = os.path.join(APK, "names.json")
    if not (os.path.exists(a) and os.path.exists(b)):
        fail("names.json", "文件缺失")
        return
    ha = hashlib.md5(read(a, "rb")).hexdigest()
    hb = hashlib.md5(read(b, "rb")).hexdigest()
    if ha != hb:
        fail("names.json", "两份已漂移：data=%s… apk=%s…" % (ha[:8], hb[:8]))
    else:
        ok("names.json", "两份一致 %s…" % ha[:8])


# ------------------------------------------------------- 6. 隐私名单同步
def check_hidden():
    try:
        d = json.loads(read(os.path.join(ROOT, "data", "hidden.json")))
        want = {str(p["uid"]) for p in d.get("players", [])}
    except Exception as e:
        fail("隐私名单", "data/hidden.json 读取失败：%r" % (e,))
        return
    try:
        tree = ast.parse(read(os.path.join(APK, "app_ui.py")))
        got = None
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HIDDEN_UIDS" for t in n.targets):
                call = n.value
                if isinstance(call, ast.Call) and call.args:
                    got = {str(x) for x in ast.literal_eval(call.args[0])}
                else:
                    got = {str(x) for x in ast.literal_eval(call)}
                break
        if got is None:
            warn("隐私名单", "app_ui.py 里没找到 HIDDEN_UIDS 兜底集合")
        elif got != want:
            fail("隐私名单", "app_ui 兜底 %s ≠ hidden.json %s" % (sorted(got), sorted(want)))
        else:
            ok("隐私名单", "%d 人，APK 兜底与 json 一致" % len(want))
    except Exception as e:
        fail("隐私名单", "解析 app_ui.py 失败：%r" % (e,))


# ------------------------------------------------- 7. 经验快照窗口完整性
def check_exp_window():
    """经验变化页的基准 = 「3 天前或更早里最近的一条」。

    如果某个分区中间缺了一天快照，基准会被迫退到更早那天，区间变成 4~5 天，
    页面头部就会显示「4 天」而不是「3 天」——2026-11-14 那次手工重建基准
    删掉墨羽惊鸿 11-14 快照，就是这么让 taptap_4 变成 4 天的（已修）。
    这里只做提示，缺一天可能只是当天 cron 没跑或游戏服不通，不代表数据坏了。
    """
    srv_dir = os.path.join(ROOT, "data", "servers")
    if not os.path.isdir(srv_dir):
        return
    loose = []
    for key in sorted(os.listdir(srv_dir)):
        p = os.path.join(srv_dir, key, "exp-history.json")
        if not os.path.isfile(p):
            continue
        try:
            snaps = [s for s in (json.loads(read(p)).get("snapshots") or [])
                     if s.get("src") == "profile"]
        except Exception:
            loose.append("%s(读取失败)" % key)
            continue
        snaps.sort(key=lambda s: int(s.get("ts") or 0))
        if len(snaps) < 2:
            continue
        latest_ts = int(snaps[-1]["ts"])
        cutoff = latest_ts - 3 * 86400
        base = None
        for s in reversed(snaps):
            if int(s["ts"]) <= cutoff:
                base = s
                break
        if base is None:
            continue                      # 攒不满 3 天，页面自己会挂横幅
        days = (latest_ts - int(base["ts"])) / 86400.0
        if days > 3.25:
            loose.append("%s %.1f 天（%s）" % (key, days, base.get("date", "?")))
    if loose:
        warn("经验快照窗口", "基准超过 3 天：%s" % "；".join(loose[:4]))
    else:
        ok("经验快照窗口", "各分区基准均在 3 天内")


# -------------------------------------------- 6.1 字段级隐藏名单同步
def check_hidden_fields():
    """data/hidden-fields.json 与 apk/lookup_core.py 的 HIDDEN_FIELDS 兜底必须一致。

    与 hidden.json 的区别：这里的人不剔除，只把 skills/prepared/newSkills 清空。
    网页侧靠 fetch_profiles.py 写盘时清空，APK 侧靠 HIDDEN_FIELDS 兜底 +
    parse_profile 后的 apply_field_hide()，两边都改了才算数。
    """
    fp = os.path.join(ROOT, "data", "hidden-fields.json")
    if not os.path.exists(fp):
        ok("字段级隐藏", "无 data/hidden-fields.json，跳过")
        return
    try:
        d = json.loads(read(fp))
        want = {}
        for p in (d.get("players") or []):
            uid = str(p.get("uid") or "").strip()
            if uid:
                want[uid] = set(str(x) for x in (p.get("hide") or []))
    except Exception as e:
        fail("字段级隐藏", "data/hidden-fields.json 读取失败：%r" % (e,))
        return
    try:
        tree = ast.parse(read(os.path.join(APK, "lookup_core.py")))

        def _val(node):
            """字面量或 set(...)/frozenset(...)/tuple(...) 包装，都还原成 set。"""
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("set", "frozenset", "tuple", "list") and node.args:
                return set(str(x) for x in ast.literal_eval(node.args[0]))
            return set(str(x) for x in ast.literal_eval(node))

        got = None
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HIDDEN_FIELDS" for t in n.targets):
                # 值可能是 set(...) 调用，ast.literal_eval 直接吃整个 dict 会炸，
                # 所以逐 key/value 还原
                node = n.value
                if not isinstance(node, ast.Dict):
                    break
                got = {}
                for k, v in zip(node.keys, node.values):
                    got[str(ast.literal_eval(k))] = _val(v)
                break
        if got is None:
            warn("字段级隐藏", "lookup_core.py 里没找到 HIDDEN_FIELDS 兜底")
        elif got != want:
            fail("字段级隐藏", "APK 兜底 %s ≠ json %s" % (got, want))
        else:
            ok("字段级隐藏", "%d 人，APK 兜底与 json 一致" % len(want))
    except Exception as e:
        fail("字段级隐藏", "解析 lookup_core.py 失败：%r" % (e,))


# ------------------------------------------------------------------ main
def main():
    if "--fix" in sys.argv:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "stamp_assets.py")],
                           cwd=ROOT)
        print("--- stamp_assets.py 退出码 %d\n" % p.returncode)

    check_python_syntax()
    check_js_syntax()
    check_stamps()
    check_update_pack()
    check_level_parity()
    check_names()
    check_hidden()
    check_hidden_fields()
    check_exp_window()

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    for level, name, detail in results:
        if QUIET and level == "PASS":
            continue
        print("[%s] %-18s %s" % (level, name, detail))
    print("\n%d 项通过 / %d 项警告 / %d 项失败" %
          (len(results) - len(fails) - len(warns), len(warns), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""加一个分区：一条命令改完 7 处 + 同步凭据 + 抓首轮数据。

以前加一个区（ios1 / ios2 / ios3 三次）每次都要手工改下面 7 个地方，
改漏了不会报错，只表现为「自动识别分区不准」或「APK 里看不到这个区」。
这个脚本把 7 处集中到一处，改完自动跑 --verify 复查。

用法：
  python scripts/add_server.py --key ios4 --name 新服名 --channel xxx \\
      --uuid 0123456789abcdef --account 1234567890 --maxRank 50 \\
      --prefix 29 --uid-len 11 --hours 12 --dry-run

  python scripts/add_server.py ... --apply      # 真改

参数怎么来的（照 docs/网页维护操作手册.md §2.5）：
  channel / uuid / account  从该分区客户端的 shared_prefs/extends.xml 与
                            Cocos2dxPrefsFile.xml 取，和以往一样。
  --platform ios + --domain  只有 iOS 分区需要，缺一项握手就 500。
  --prefix                   该区 uid 的开头数字，用于自动识别分区。
  --uid-len                  uid 位数，用来补「位数兜底猜测」。
  --hours                    北京时间几点跑（脚本换算成 UTC cron）。

改到的 7 处：
  1. config.json                servers 数组
  2. apk/lookup_core.py         UID_PREFIX_SERVER（+ order_servers 位数兜底）
  3. apk/app_ui.py              _servers() 内置兜底列表
  4. scripts/plan_refresh.py    SCHEDULE_MAP + LABELS
  5. .github/workflows/refresh.yml       cron 注释 + schedule + server 选项
  6. .github/workflows/merge-exp.yml     server 选项
  7. scripts/build_lookup_index.py       兜底名字表

之后还要（脚本会提示，不自动跑，因为要联网 / 要人等）：
  python scripts/sync_creds.py --apply        同步 gist + CI Secret
  python scripts/fetch.py --server <key> --probe
  python scripts/fetch.py --server <key>
  python scripts/fetch_profiles.py --server <key>
  python scripts/merge_exp.py --server <key>
  python scripts/build_lookup_index.py
  python scripts/pack_update.py "新增第 N 区「xxx」"
  python scripts/publish.py "..." <文件...>
"""
import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.json")


def die(msg):
    print("[add_server] 错误：%s" % msg)
    raise SystemExit(1)


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    # 先写 .tmp 再 os.replace：中途失败不会留下半个文件。
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def replace_once(path, old, new, what):
    """在 path 里把 old 换成 new；old 必须恰好出现一次。"""
    text = read(path)
    n = text.count(old)
    if n == 0:
        die("%s：找不到锚点，文件可能已改版 —— 手动处理\n  期望片段：%r" % (what, old[:80]))
    if n > 1:
        die("%s：锚点出现 %d 次，不唯一 —— 手动处理\n  片段：%r" % (what, n, old[:80]))
    write(path, text.replace(old, new))
    print("  [ok] %s" % what)


def utc_cron(hours):
    """北京时间 N 点 → UTC cron 表达式。"""
    h = (int(hours) - 8) % 24
    return "0 %d * * *" % h, int(hours)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="分区 key，如 ios4 / taptap_5")
    ap.add_argument("--name", required=True, help="中文名，如 老马识途")
    ap.add_argument("--channel", required=True, help="接口 channel")
    ap.add_argument("--uuid", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--prefix", required=True, help="uid 开头数字，如 29")
    ap.add_argument("--uid-len", type=int, default=0, help="uid 位数（10/11），0=不补位数兜底")
    ap.add_argument("--maxRank", type=int, default=50)
    ap.add_argument("--indexRank", type=int, default=0)
    ap.add_argument("--platform", default="", help="ios 分区填 ios")
    ap.add_argument("--domain", default="", help="iOS 分区填 https://ios.fzjh.xiaohoutiaotiao.com")
    ap.add_argument("--hours", type=int, required=True, help="北京时间几点跑（0-23）")
    ap.add_argument("--dry-run", action="store_true", help="只检查现状，不改文件")
    ap.add_argument("--apply", action="store_true", help="真改（不写则与 --dry-run 等价，防手滑）")
    a = ap.parse_args()

    key, name = a.key.strip(), a.name.strip()
    if not re.match(r"^[a-z0-9_]+$", key):
        die("key 只能小写字母/数字/下划线：%r" % key)
    if a.platform and a.platform != "android" and not a.domain:
        die("非 android 分区必须同时给 --domain，否则握手必 500")

    cron, bj = utc_cron(a.hours)
    print("== 加分区 %s（%s）  cron=%s UTC = %02d:00 北京" % (key, name, cron, bj))

    # 时段冲突检查：一个 cron 只能对应一批分区，撞了会让两个区互相抢数据。
    plan_text = read(os.path.join(ROOT, "scripts/plan_refresh.py"))
    m = re.search(r'"%s": \("([^"]*)"' % re.escape(cron), plan_text)
    if m and key not in m.group(1).split(","):
        die("cron %s 已被「%s」占用，换个 --hours（避免两个区抢同一时段）"
            % (cron, m.group(1)))

    # ---------- 现状检查（幂等） ----------
    cfg = json.loads(read(CONFIG))
    servers = cfg.get("servers") or []
    keys = [s.get("key") for s in servers]
    already = key in keys
    print("   config.json 现有 %d 个分区；已存在 %s : %s"
          % (len(servers), key, "是" if already else "否"))
    if a.dry_run or not a.apply:
        for path, needle in (
            ("apk/lookup_core.py", '"%s", "%s"' % (a.prefix, key)),
            ("apk/app_ui.py", '("%s", "%s")' % (key, name)),
            ("scripts/plan_refresh.py", '"%s": "%s"' % (key, name)),
            ("scripts/build_lookup_index.py", '"%s": "%s"' % (key, name)),
            (".github/workflows/refresh.yml", "          - %s" % key),
            (".github/workflows/merge-exp.yml", "          - %s" % key),
        ):
            hit = needle in read(os.path.join(ROOT, path))
            print("   %-38s %s → %s" % (path, needle[:34], "已存在" if hit else "缺"))
        print("\n[dry-run] 未改任何文件。确认无误后加 --apply 真正执行。")
        return 0

    if already:
        print("   分区已存在于 config.json，跳过重复插入")

    # ---------- 1. config.json ----------
    if not already:
        ent = {
            "key": key,
            "name": name,
            "channel": a.channel,
            "uuid": a.uuid,
            "account": int(a.account),
        }
        if a.maxRank:
            ent["maxRank"] = a.maxRank
        if a.indexRank:
            ent["indexRank"] = a.indexRank
        if a.platform:
            ent["platform"] = a.platform
        if a.domain:
            ent["domain"] = a.domain
        servers.append(ent)
        cfg["servers"] = servers
        write(CONFIG, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        print("  [ok] config.json 追加 %s（共 %d 个分区）" % (key, len(servers)))

    # ---------- 2. apk/lookup_core.py ----------
    p = os.path.join(ROOT, "apk/lookup_core.py")
    if ('"%s", "%s"' % (a.prefix, key)) not in read(p):
        anchor = '    ("19", "ios3"),       # 仙人指路（iOS 三区，uid 19 开头 11 位）\n'
        if anchor not in read(p):
            anchor = '    ("4", "4399"),\n'
        replace_once(
            p, anchor,
            anchor + '    ("%s", "%s"),       # %s（uid %s 开头）\n'
            % (a.prefix, key, name, a.prefix),
            "lookup_core.py UID_PREFIX_SERVER")
    else:
        print("  [skip] lookup_core.py 前缀已在")

    # order_servers 的位数兜底
    if a.uid_len in (10, 11):
        t = read(p)
        old = ('    elif len(s) == 10:\n        guess += ["4399", "ios1", "ios2"]\n'
               if a.uid_len == 10 else
               '    elif len(s) == 11:\n        guess += ["taptap_3", "taptap_2", "taptap_4", "ios3"]\n')
        if old in t:
            new = old.replace('"]\n', '", "%s"]\n' % key)
            write(p, t.replace(old, new))
            print("  [ok] lookup_core.py order_servers %d 位兜底 += %s" % (a.uid_len, key))
        elif '"%s"' % key in t.split("def order_servers")[1].split("def ")[0]:
            print("  [skip] order_servers 已含 %s" % key)
        else:
            print("  [warn] order_servers 的 %d 位兜底行没找到，请手工补 %s" % (a.uid_len, key))

    # ---------- 3. apk/app_ui.py ----------
    p = os.path.join(ROOT, "apk/app_ui.py")
    if '("%s", "%s")' % (key, name) not in read(p):
        replace_once(
            p, '("ios3", "仙人指路")]',
            '("ios3", "仙人指路"),\n                ("%s", "%s")]' % (key, name),
            "app_ui.py _servers() 兜底列表")
    else:
        print("  [skip] app_ui.py 兜底已在")

    # ---------- 4. scripts/plan_refresh.py ----------
    p = os.path.join(ROOT, "scripts/plan_refresh.py")
    t = read(p)
    if ('"%s"' % key) not in t:
        t = t.replace(
            '    "0 2 * * *": ("ios3", "仙人指路"),       # 10:00 北京时间\n',
            '    "0 2 * * *": ("ios3", "仙人指路"),       # 10:00 北京时间\n'
            '    "%s": ("%s", "%s"),       # %02d:00 北京时间\n' % (cron, key, name, bj))
        write(p, t)
        print("  [ok] plan_refresh.py SCHEDULE_MAP += %s" % cron)
    else:
        print("  [skip] plan_refresh.py 已有 %s" % key)
    t = read(p)
    if '"%s": "%s"' % (key, name) not in t:
        t = t.replace('    "ios3": "仙人指路",\n',
                      '    "ios3": "仙人指路",\n    "%s": "%s",\n' % (key, name))
        write(p, t)
        print("  [ok] plan_refresh.py LABELS += %s" % key)
    else:
        print("  [skip] plan_refresh.py LABELS 已有")

    # ---------- 5. workflows ----------
    p = os.path.join(ROOT, ".github/workflows/refresh.yml")
    t = read(p)
    if ("          - %s\n" % key) not in t:
        t = t.replace("          - ios3\n",
                      "          - ios3\n          - %s\n" % key)
        write(p, t)
        print("  [ok] refresh.yml server 选项 += %s" % key)
    else:
        print("  [skip] refresh.yml server 选项已有")
    t = read(p)
    hh = "%02d:00" % bj
    if ("cron: '%s'" % cron) not in t:
        t = t.replace("    - cron: '0 2 * * *'    # 10:00 仙人指路\n",
                      "    - cron: '0 2 * * *'    # 10:00 仙人指路\n"
                      "    - cron: '%s'    # %s %s\n" % (cron, hh, name))
        t = t.replace("#   0 2 * * *   → 当日 10:00  仙人指路（ios3）\n",
                      "#   0 2 * * *   → 当日 10:00  仙人指路（ios3）\n"
                      "#   %s   → %s %02d:00  %s（%s）\n"
                      % (cron, "次日" if bj < 8 else "当日", bj, name, key))
        write(p, t)
        print("  [ok] refresh.yml cron += %s" % cron)
    else:
        print("  [skip] refresh.yml cron 已有")

    p = os.path.join(ROOT, ".github/workflows/merge-exp.yml")
    t = read(p)
    if ("          - %s\n" % key) not in t:
        t = t.replace("          - ios3\n",
                      "          - ios3\n          - %s\n" % key)
        write(p, t)
        print("  [ok] merge-exp.yml server 选项 += %s" % key)
    else:
        print("  [skip] merge-exp.yml server 选项已有")

    # ---------- 6. scripts/build_lookup_index.py ----------
    p = os.path.join(ROOT, "scripts/build_lookup_index.py")
    if '"%s": "%s"' % (key, name) not in read(p):
        replace_once(p, '"ios2": "野马分鬃", "ios3": "仙人指路",\n',
                     '"ios2": "野马分鬃", "ios3": "仙人指路",\n            "%s": "%s",\n'
                     % (key, name),
                     "build_lookup_index.py 兜底名字表")
    else:
        print("  [skip] build_lookup_index.py 兜底已有")

    # ---------- 复查 ----------
    print("\n== 复查 7 处 ==")
    checks = [
        ("config.json", key in [s.get("key") for s in json.loads(read(CONFIG)).get("servers", [])]),
        ("apk/lookup_core.py 前缀", ('"%s", "%s"' % (a.prefix, key)) in read(os.path.join(ROOT, "apk/lookup_core.py"))),
        ("apk/app_ui.py 兜底", ('("%s", "%s")' % (key, name)) in read(os.path.join(ROOT, "apk/app_ui.py"))),
        ("plan_refresh.py cron", cron in read(os.path.join(ROOT, "scripts/plan_refresh.py"))),
        ("plan_refresh.py LABELS", ('"%s": "%s"' % (key, name)) in read(os.path.join(ROOT, "scripts/plan_refresh.py"))),
        ("refresh.yml", ("          - %s\n" % key) in read(os.path.join(ROOT, ".github/workflows/refresh.yml"))),
        ("merge-exp.yml", ("          - %s\n" % key) in read(os.path.join(ROOT, ".github/workflows/merge-exp.yml"))),
        ("build_lookup_index.py", ('"%s": "%s"' % (key, name)) in read(os.path.join(ROOT, "scripts/build_lookup_index.py"))),
    ]
    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print("  %s %s" % ("[PASS]" if ok else "[FAIL]", n))
    if bad:
        die("有 %d 处没改成功：%s" % (len(bad), ", ".join(bad)))

    print("""
== 下一步（按顺序，前两条必须做） ==
  python scripts/sync_creds.py --apply           # 同步私有 gist + CI Secret
  python scripts/sync_creds.py --check           # 复查 11 → %d 个分区
  python scripts/fetch.py --server %s --probe
  python scripts/fetch.py --server %s
  python scripts/fetch_profiles.py --server %s
  python scripts/merge_exp.py --server %s
  python scripts/build_lookup_index.py
  python scripts/stamp_assets.py
  python scripts/pack_update.py "新增分区「%s」：自动识别 %s 开头、昵称检索、榜单与档案接入"
  python scripts/preflight.py
  python scripts/publish.py "<说明>" <改动文件...>
  # 设备验收前务必清缓存：
  #   adb shell run-as com.fzjh.fzjhlookup rm -f files/servers-remote.json files/lookup-index.json
""" % (len(servers), key, key, key, key, name, a.prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main())

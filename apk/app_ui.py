# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询（Android / 桌面均可运行）

选定分区 → 输入 UID → 拉取并展示该玩家完整档案。
默认只查选中的分区；「自动探测」逐区尝试，仅作兜底保留。
界面用 Kivy 构建；网络与解析逻辑在 lookup_core.py。
"""
import json
import os
import threading
import traceback

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput

import lookup_core as L

# ---------- 中文字体：安卓系统自带，按优先级找一个 ----------
_CN_CANDIDATES = [
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/DroidSansChinese.ttf",
    "/system/fonts/NotoSansHans-Regular.otf",
]
FONT = "Roboto"
for _p in _CN_CANDIDATES:
    if os.path.exists(_p):
        try:
            LabelBase.register(name="CN", fn_regular=_p)
            FONT = "CN"
            break
        except Exception:
            pass

C_BG = (0.965, 0.957, 0.937, 1)      # 宣纸
C_CARD = (1, 1, 1, 1)
C_INK = (0.12, 0.14, 0.16, 1)
C_INK2 = (0.29, 0.32, 0.38, 1)
C_MUTED = (0.54, 0.57, 0.61, 1)
C_ACCENT = (0.55, 0.18, 0.16, 1)     # 朱砂
C_SOFT = (0.95, 0.91, 0.89, 1)
C_LINE = (0.91, 0.89, 0.85, 1)
C_OK = (0.18, 0.48, 0.36, 1)


def lab(text, size=13, color=C_INK, bold=False, height=None, halign="left", markup=False):
    w = Label(
        text=text, font_name=FONT, font_size=sp(size), color=color,
        bold=bold, halign=halign, valign="middle", markup=markup,
        size_hint_y=None, height=dp(height if height else size * 1.9),
    )
    w.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
    return w


class Card(BoxLayout):
    """白底圆角卡片（Kivy 用 canvas 画圆角矩形）"""

    def __init__(self, **kw):
        super(Card, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*C_CARD)
            self._rect = RoundedRectangle(radius=[dp(10)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size


class KV(BoxLayout):
    """一格数值：上方小标题，下方大数字"""

    def __init__(self, key, **kw):
        super(KV, self).__init__(orientation="vertical", padding=(dp(9), dp(5)),
                                 spacing=0, **kw)
        self.add_widget(lab(key, 9, C_MUTED, height=13))
        self.val = lab("—", 14, C_INK, bold=True, height=20)
        self.add_widget(self.val)

    def set(self, v):
        self.val.text = str(v)


class CnSpinnerOption(SpinnerOption):
    """下拉项也用中文字体，避免选项变方块"""

    def __init__(self, **kw):
        kw.setdefault("font_name", FONT)
        kw.setdefault("font_size", sp(13))
        kw.setdefault("color", C_INK)
        super(CnSpinnerOption, self).__init__(**kw)


class PlayerLookup(App):
    AUTO_LABEL = "自动探测（不推荐）"

    def build(self):
        self.title = "玩家查询"
        self.prof = None
        self.busy = False

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        # ---- 标题 ----
        head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(52))
        head.add_widget(lab("江湖 · 玩家查询", 20, C_INK, bold=True, height=30))
        head.add_widget(lab("选定分区，输入 UID 查询", 10.5, C_MUTED, height=16))
        root.add_widget(head)

        # ---- 分区选择 ----
        self.servers = self._servers()
        names = [n for _k, n in self.servers] + [self.AUTO_LABEL]
        row_srv = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        lbl = lab("分区", 12, C_INK2, height=42)
        lbl.size_hint_x = None
        lbl.width = dp(44)
        row_srv.add_widget(lbl)
        self.spin = Spinner(
            text=self._name_of(self._picked_key()) or names[0], values=names,
            font_name=FONT, font_size=sp(13), color=C_INK,
            background_color=C_SOFT, background_normal="",
            option_cls=CnSpinnerOption,
        )
        row_srv.add_widget(self.spin)
        self.spin.bind(text=lambda inst, v: self._save_pick(v))
        root.add_widget(row_srv)

        # ---- 输入行 ----
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.inp = TextInput(
            text="", hint_text="例如 21079729670", font_name=FONT, font_size=sp(15),
            multiline=False, input_type="number", padding=[dp(10), dp(12)],
            background_color=(1, 1, 1, 1), foreground_color=C_INK, cursor_color=C_ACCENT,
        )
        self.inp.bind(on_text_validate=lambda *a: self.start())
        row.add_widget(self.inp)

        self.btn = Button(
            text="查询", font_name=FONT, font_size=sp(14), bold=True,
            size_hint_x=None, width=dp(84),
            background_color=C_ACCENT, background_normal="", color=(1, 1, 1, 1),
        )
        self.btn.bind(on_release=lambda *a: self.start())
        row.add_widget(self.btn)
        root.add_widget(row)

        # ---- 状态 ----
        self.status = lab("就绪", 11, C_MUTED, height=18)
        root.add_widget(self.status)

        # ---- 结果区（可滚动）----
        sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8),
                              padding=(0, 0, 0, dp(10)))
        self.body.bind(minimum_height=self.body.setter("height"))
        sv.add_widget(self.body)
        root.add_widget(sv)

        self._empty_hint()
        return root

    # ---------- 分区选择 ----------
    @staticmethod
    def _servers():
        try:
            cfg = L.load_config()
            out = [(str(s["key"]), str(s["name"]))
                   for s in (cfg.get("servers") or []) if s.get("key")]
            if out:
                return out
        except Exception:
            pass
        return [("taptap", "苍松迎客"), ("taptap_2", "白鹤亮翅"),
                ("taptap_3", "丹凤朝阳"), ("taptap_4", "墨羽惊鸿"),
                ("4399", "4399")]

    def _picked_key(self):
        """记住上次选的区；首次默认丹凤朝阳。自动探测永不做默认值。"""
        try:
            c = L.load_cache()
        except Exception:
            c = {}
        key = c.get("pickedServer") or c.get("lastServer")
        if key in dict(self.servers):
            return key
        return "taptap_3" if "taptap_3" in dict(self.servers) else self.servers[0][0]

    def _name_of(self, key):
        return dict(self.servers).get(key)

    def key_of(self, name):
        if name == self.AUTO_LABEL:
            return "auto"
        for k, n in self.servers:
            if n == name:
                return k
        return "auto"

    def _save_pick(self, name):
        key = self.key_of(name)
        if key == "auto":
            return
        try:
            c = L.load_cache()
            c["pickedServer"] = key
            L.save_cache(c)
        except Exception:
            pass

    # ---------- 占位 ----------
    def _empty_hint(self):
        self.body.clear_widgets()
        c = Card(orientation="vertical", size_hint_y=None, height=dp(120),
                 padding=(dp(16), dp(18)), spacing=dp(6))
        c.add_widget(lab("选好分区，输入 UID 开始查询", 14, C_INK2, bold=True, height=22))
        c.add_widget(lab("默认只查选中的分区：请求少、速度快，也不容易被服务器限流；选择会被记住",
                         11, C_MUTED, height=36))
        c.add_widget(lab("不确定在哪个区时，才用列表最后的「自动探测」逐区尝试；UID 是角色 ID，不是登录账号",
                         11, C_MUTED, height=36))
        self.body.add_widget(c)

    # ---------- 查询 ----------
    def start(self):
        if self.busy:
            return
        raw = (self.inp.text or "").strip()
        if not raw.isdigit():
            self.set_status("请输入纯数字 UID", C_ACCENT)
            return
        self.busy = True
        self.btn.disabled = True
        self.btn.text = "查询中"
        self.set_status("连接中…", C_ACCENT)
        key = self.key_of(self.spin.text)
        threading.Thread(target=self._worker, args=(int(raw), key), daemon=True).start()

    def _worker(self, uid, server):
        try:
            prof = L.lookup(uid, server=server, progress=lambda m: Clock.schedule_once(
                lambda dt, msg=m: self.set_status(msg, C_ACCENT)))
        except Exception:
            err = traceback.format_exc()[-300:]
            Clock.schedule_once(lambda dt: self._fail("查询异常\n" + err))
            return
        Clock.schedule_once(lambda dt: self._done(prof, server))

    def _done(self, prof, server="auto"):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询"
        if not prof:
            if server == "auto":
                self._fail("五个分区都没有这个 UID\n确认是游戏内的角色 ID 吗？")
            else:
                self._fail("在「%s」没查到这个 UID\n分区选对了吗？请求繁忙时请稍后重试"
                           % (self._name_of(server) or server))
            return
        self.prof = prof
        self.set_status("查询成功 · %s" % prof["serverName"], C_OK)
        self._render(prof)

    def _fail(self, msg):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询"
        self.set_status(msg.split("\n")[0], C_ACCENT)
        self.body.clear_widgets()
        c = Card(orientation="vertical", size_hint_y=None, height=dp(110),
                 padding=(dp(16), dp(16)), spacing=dp(4))
        c.add_widget(lab("没查到", 15, C_ACCENT, bold=True, height=24))
        for line in msg.split("\n"):
            c.add_widget(lab(line, 11, C_MUTED, height=20))
        self.body.add_widget(c)

    def set_status(self, text, color=C_MUTED):
        self.status.text = text
        self.status.color = color

    # ---------- 渲染 ----------
    def _render(self, p):
        self.body.clear_widgets()

        # 名片
        c = Card(orientation="vertical", size_hint_y=None, height=dp(96),
                 padding=(dp(14), dp(10)), spacing=dp(2))
        c.add_widget(lab(p["name"], 20, C_INK, bold=True, height=28))
        sub = " · ".join([x for x in [p["serverName"], p["menpai"],
                                      (p["sex"] + " " if p["sex"] else "") +
                                      (str(p["age"]) + " 岁" if p["age"] else "")] if x])
        c.add_widget(lab(sub, 11.5, C_MUTED, height=18))
        rk = ("榜上第 %s 名" % p["rank"]) if p.get("rank") else "未上榜"
        c.add_widget(lab(rk, 11, C_INK2, height=18))
        self.body.add_widget(c)

        # 数值网格 2 列
        grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(6))
        vals = [
            ("等级", ("%s" % p["lv"]) + ("（估）" if p.get("lvEstimated") else "") if p["lv"] else "—"),
            ("武学造诣", ("%.2f" % p["kongfu"]) if p.get("kongfu") is not None else "—"),
            ("经验", L.fmt_big(p["exp"]) if hasattr(L, "fmt_big") else self._big(p["exp"])),
            ("福缘", p["fuyuan"] if p.get("fuyuan") is not None else "—"),
            ("气血", self._big(p.get("qiMax"))),
            ("家产", self._big(p.get("jiaLi"))),
            ("侠义", self._big(p.get("zhengqi"))),
            ("转数", ("%s 转" % p["inheritCount"]) if p.get("inheritCount") else "—"),
        ]
        for k, v in vals:
            cell = Card(orientation="vertical", size_hint_y=None, height=dp(56),
                        padding=(dp(10), dp(6)), spacing=0)
            cell.add_widget(lab(k, 9.5, C_MUTED, height=14))
            cell.add_widget(lab(str(v), 15, C_INK, bold=True, height=24))
            grid.add_widget(cell)
        grid.height = dp(56) * 4 + dp(6) * 3
        self.body.add_widget(grid)

        # 准备位
        if p["prepared"]:
            self._section("准备位（%d）" % len(p["prepared"]))
            c2 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(12), dp(8)))
            c2.height = dp(8) + dp(22) * len(p["prepared"]) + dp(8)
            for slot, nm in p["prepared"].items():
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab(slot, 11, C_MUTED, height=22))
                row.add_widget(lab(nm, 11.5, C_INK2, height=22, halign="right"))
                c2.add_widget(row)
            self.body.add_widget(c2)

        # 装备
        if p["equips"]:
            self._section("装备（%d）" % len(p["equips"]))
            c3 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(12), dp(8)))
            c3.height = dp(8) + dp(22) * len(p["equips"]) + dp(8)
            for e in p["equips"]:
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab(e["slot"], 11, C_MUTED, height=22))
                row.add_widget(lab(e["n"], 11.5, C_INK2, height=22, halign="right"))
                c3.add_widget(row)
            self.body.add_widget(c3)

        # 传承
        if p["history"]:
            self._section("传承（%d 世）" % len(p["history"]))
            c4 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(12), dp(8)))
            c4.height = dp(8) + dp(22) * len(p["history"]) + dp(8)
            for h in p["history"]:
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab("第 %d 世" % (p["history"].index(h) + 1), 10.5, C_MUTED, height=22))
                row.add_widget(lab(h["n"] or "—", 11.5, C_INK2, height=22, halign="right"))
                c4.add_widget(row)
            self.body.add_widget(c4)

        # 武学
        skills = p["skills"]
        if skills:
            self._section("武学（%d 门）" % len(skills))
            c5 = Card(orientation="vertical", size_hint_y=None, spacing=dp(1),
                      padding=(dp(12), dp(8)))
            show = skills[:60]
            c5.height = dp(8) + dp(21) * len(show) + dp(8)
            for i, s in enumerate(show, 1):
                row = BoxLayout(size_hint_y=None, height=dp(21))
                row.add_widget(lab(str(i), 9.5, C_MUTED, height=21))
                row.add_widget(lab(s["n"], 11.5, C_INK2, height=21))
                row.add_widget(lab(str(s["lv"]), 11, C_INK2, height=21, halign="right"))
                c5.add_widget(row)
            self.body.add_widget(c5)
            if len(skills) > len(show):
                self.body.add_widget(lab("仅显示前 %d 门，完整数据请用「保存数据」" % len(show),
                                         10, C_MUTED, height=20, halign="center"))

        # 保存按钮
        self.btn_save = Button(
            text="保存数据（JSON）", font_name=FONT, font_size=sp(13),
            size_hint_y=None, height=dp(44),
            background_color=C_SOFT, background_normal="", color=C_ACCENT,
        )
        self.btn_save.bind(on_release=lambda *a: self.save())
        self.body.add_widget(self.btn_save)

        self.footer = lab("数据时间：%s" % p.get("fetchedAt", ""), 10, C_MUTED,
                          height=20, halign="center")
        self.body.add_widget(self.footer)

    def _section(self, title):
        self.body.add_widget(lab(title, 12, C_INK2, bold=True, height=dp(24)))

    def _big(self, n):
        try:
            n = float(n)
        except (TypeError, ValueError):
            return "—"
        a = abs(n)
        if a >= 1e8:
            return "%.2f亿" % (n / 1e8)
        if a >= 1e4:
            return "%.1f万" % (n / 1e4)
        return "%d" % round(n)

    def save(self):
        if not self.prof:
            return
        try:
            d = App.get_running_app().user_data_dir
            if not os.path.isdir(d):
                os.makedirs(d)
            fn = "%s_%s.json" % (self.prof["name"] or "player", self.prof["uid"])
            path = os.path.join(d, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.prof, ensure_ascii=False, indent=2))
            self.set_status("已保存：%s" % path, C_OK)
        except Exception as e:
            self.set_status("保存失败：%s" % e, C_ACCENT)


def run():
    """启动主界面（供启动器调用）"""
    PlayerLookup().run()


if __name__ == "__main__":
    run()

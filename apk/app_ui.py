# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询（Android / 桌面均可运行）

方案 A：浅色纸感 + 朱砂红。Kivy 没有 CSS 的 body 背景，
整屏底色由 Root 在 canvas.before 里画出来，Card 负责白底圆角卡片。
"""
import io
import json
import os
import sys
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

# ---------- 设计令牌：浅色纸感 + 朱砂红 ----------
C_BG = (0.969, 0.957, 0.925, 1)          # #F7F4EC 米白纸
C_CARD = (1, 1, 1, 1)                    # #FFFFFF
C_SOFT = (0.945, 0.937, 0.910, 1)        # #F1EFE8 提示条
C_ACCENT_SOFT = (0.980, 0.925, 0.906, 1)  # #FAECE7
C_INK = (0.173, 0.165, 0.149, 1)         # #2C2A26
C_INK2 = (0.420, 0.396, 0.357, 1)        # #6B655B
C_MUTED = (0.533, 0.529, 0.502, 1)       # #888780
C_ACCENT = (0.659, 0.204, 0.184, 1)      # #A8342F 朱砂
C_LINE = (0.902, 0.878, 0.827, 1)        # #E6E0D3
C_OK = (0.145, 0.427, 0.310, 1)


def code_version():
    """当前跑的是热更包还是 APK 内置代码，只在「关于」里展示。"""
    for d in sys.path[:3]:
        try:
            p = os.path.join(d, "version.txt")
            if os.path.isfile(p):
                with io.open(p, encoding="utf-8") as f:
                    v = (f.read() or "").strip()
                if v:
                    return "v" + v
        except Exception:
            pass
    return "内置版"


def lab(text, size=13, color=C_INK, bold=False, height=None, halign="left", markup=False):
    w = Label(
        text=text, font_name=FONT, font_size=sp(size), color=color,
        bold=bold, halign=halign, valign="middle", markup=markup,
        size_hint_y=None, height=dp(height if height else size * 1.9),
    )
    w.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
    return w


class Root(BoxLayout):
    """整屏米白底：Kivy 的 BoxLayout 默认透明，必须自己画。"""

    def __init__(self, **kw):
        super(Root, self).__init__(**kw)
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class Card(BoxLayout):
    """白底圆角卡片，可选 1px 边框（focus 时换朱砂）。"""

    def __init__(self, bg=None, border=None, radius=10, **kw):
        super(Card, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        bg = bg or C_CARD
        with self.canvas.before:
            self._bd_color = None
            if border:
                self._bd_color = Color(*border)
                self._bd = RoundedRectangle(radius=[dp(radius + 1)],
                                            pos=self.pos, size=self.size)
            Color(*bg)
            self._rect = RoundedRectangle(radius=[dp(radius)],
                                          pos=(self.x + 1, self.y + 1),
                                          size=(self.width - 2, self.height - 2))
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        if self._bd_color is not None:
            self._bd.pos = self.pos
            self._bd.size = self.size
        self._rect.pos = (self.x + 1, self.y + 1)
        self._rect.size = (self.width - 2, self.height - 2)

    def set_border(self, color):
        if self._bd_color is not None:
            self._bd_color.rgba = color


class FieldCard(Card):
    """输入卡：聚焦时边框变朱砂。"""

    def __init__(self, **kw):
        kw.setdefault("border", C_LINE)
        super(FieldCard, self).__init__(**kw)


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
        kw.setdefault("font_size", sp(14))
        kw.setdefault("color", C_INK)
        super(CnSpinnerOption, self).__init__(**kw)


class PlayerLookup(App):
    AUTO_LABEL = "自动探测（不推荐）"
    # 没有历史时给的示例（均为丹凤朝阳）
    EXAMPLES = [
        {"uid": 21079729670, "name": "刘小年", "server": "taptap_3", "serverName": "丹凤朝阳"},
        {"uid": 21079747122, "name": "观云者", "server": "taptap_3", "serverName": "丹凤朝阳"},
    ]

    def build(self):
        self.title = "玩家查询"
        self.prof = None
        self.busy = False
        self.hint_open = False

        root = Root(orientation="vertical", padding=(dp(20), dp(16), dp(20), dp(12)),
                    spacing=dp(12))

        # ---- 标题：建立层级，副标题不再与说明卡重复 ----
        head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(56), spacing=dp(2))
        head.add_widget(lab("江湖 · 玩家查询", 20, C_INK, bold=True, height=30))
        head.add_widget(lab("按分区查角色档案与榜单信息", 12, C_MUTED, height=20))
        root.add_widget(head)

        # ---- 分区：label + 下拉 + ▾，让「可点」看得见 ----
        self.servers = self._servers()
        names = [n for _k, n in self.servers] + [self.AUTO_LABEL]
        row_srv = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        lbl = lab("分区", 12, C_INK2, height=48)
        lbl.size_hint_x = None
        lbl.width = dp(44)
        row_srv.add_widget(lbl)
        picker = BoxLayout(spacing=0)
        self.spin = Spinner(
            text=self._name_of(self._picked_key()) or names[0], values=names,
            font_name=FONT, font_size=sp(14), color=C_INK,
            background_color=C_CARD, background_normal="",
            option_cls=CnSpinnerOption,
        )
        picker.add_widget(self.spin)
        arrow = lab("▾", 15, C_ACCENT, bold=True, height=48, halign="center")
        arrow.size_hint_x = None
        arrow.width = dp(30)
        picker.add_widget(arrow)
        row_srv.add_widget(picker)
        self.spin.bind(text=lambda inst, v: self._save_pick(v))
        root.add_widget(row_srv)

        # ---- 输入卡：label + 输入框(focus 描边) + 全宽 48px 主按钮 ----
        self.field = FieldCard(orientation="vertical", size_hint_y=None,
                               padding=(dp(16), dp(14)), spacing=dp(10))
        self.field.bind(minimum_height=self.field.setter("height"))
        self.field.add_widget(lab("角色 UID", 12, C_INK2, height=20))
        self.inp = TextInput(
            text="", hint_text="例如 21079729670", font_name=FONT, font_size=sp(15),
            multiline=False, input_type="number", padding=[dp(12), dp(12)],
            size_hint_y=None, height=dp(48),
            background_color=(0, 0, 0, 0), background_normal="", background_active="",
            foreground_color=C_INK, hint_text_color=C_MUTED, cursor_color=C_ACCENT,
        )
        self.inp.bind(on_text_validate=lambda *a: self.start())
        self.inp.bind(focus=lambda inst, v: self.field.set_border(C_ACCENT if v else C_LINE))
        self.field.add_widget(self.inp)
        self.btn = Button(
            text="查询玩家", font_name=FONT, font_size=sp(15), bold=True,
            size_hint_y=None, height=dp(48),
            background_color=C_ACCENT, background_normal="", color=(1, 1, 1, 1),
        )
        self.btn.bind(on_release=lambda *a: self.start())
        self.field.add_widget(self.btn)
        root.add_widget(self.field)

        # ---- 只放业务状态，不暴露版本号 ----
        self.status = lab("选择分区并输入 UID", 12, C_MUTED, height=20)
        root.add_widget(self.status)

        # ---- 结果区（可滚动）----
        sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12),
                              padding=(0, 0, 0, dp(12)))
        self.body.bind(minimum_height=self.body.setter("height"))
        sv.add_widget(self.body)
        root.add_widget(sv)

        self._show_idle()
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

    # ---------- 空状态：提示条 + 最近查询 ----------
    def _show_idle(self):
        self.body.clear_widgets()
        self.body.add_widget(self._hint_widget())
        self.body.add_widget(self._recent_widget())

    def _hint_widget(self):
        c = Card(bg=C_SOFT, orientation="vertical", size_hint_y=None,
                 padding=(dp(14), dp(10)), spacing=dp(6))
        row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
        row.add_widget(lab("UID 是游戏内角色 ID，不是登录账号", 12, C_INK2, height=28))
        q = lab("？", 13, C_ACCENT, bold=True, height=28, halign="center")
        q.size_hint_x = None
        q.width = dp(32)
        row.add_widget(q)
        c.add_widget(row)
        if self.hint_open:
            c.add_widget(lab("默认只查选中的分区，速度快、不易被限流；分区选择会被记住。",
                             11.5, C_INK2, height=36))
            c.add_widget(lab("不确定在哪个区时，用列表最后的「自动探测」逐区尝试。",
                             11.5, C_INK2, height=36))
            c.add_widget(lab("关于 · 当前 %s · 数据来自游戏接口" % code_version(),
                             11, C_MUTED, height=20))
        c.bind(minimum_height=c.setter("height"))
        c.bind(on_touch_down=lambda inst, t: self._hint_touch(inst, t))
        return c

    def _hint_touch(self, inst, touch):
        if inst.collide_point(*touch.pos):
            self.hint_open = not self.hint_open
            self._show_idle()
            return True
        return False

    def _recent_widget(self):
        items = L.recent_queries()
        has = bool(items)
        rows = items[:3] if has else self.EXAMPLES
        c = Card(orientation="vertical", size_hint_y=None,
                 padding=(dp(16), dp(12)), spacing=dp(8))
        c.add_widget(lab("最近查询" if has else "试试示例 UID", 14, C_INK,
                         bold=True, height=24))
        if not has:
            c.add_widget(lab("下面是丹凤朝阳的示例角色，点一下自动填入",
                             11.5, C_MUTED, height=20))
        for r in rows:
            txt = "%s  ·  %s" % (r.get("uid"), r.get("name") or r.get("serverName") or "")
            b = Button(
                text=txt, font_name=FONT, font_size=sp(13), halign="left",
                size_hint_y=None, height=dp(48),
                background_color=C_SOFT, background_normal="", color=C_INK,
            )
            b.bind(on_release=lambda inst, u=r.get("uid"), k=r.get("server"): self._fill(u, k))
            c.add_widget(b)
        c.bind(minimum_height=c.setter("height"))
        return c

    def _fill(self, uid, server_key=None):
        if uid is None:
            return
        self.inp.text = str(uid)
        if server_key and server_key in dict(self.servers):
            nm = self._name_of(server_key)
            if nm:
                self.spin.text = nm
        self.set_status("已填入 %s，点「查询玩家」开始" % uid, C_INK2)

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
        self.btn.text = "查询中…"
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
        self.btn.text = "查询玩家"
        if not prof:
            if server == "auto":
                self._fail("五个分区都没有这个 UID\n确认是游戏内的角色 ID 吗？")
            else:
                self._fail("该分区未找到，试试「自动探测」\n确认分区选对了吗？请求繁忙请稍后重试")
            return
        self.prof = prof
        L.add_recent(prof)
        self.set_status("查询成功 · %s" % prof["serverName"], C_OK)
        self._render(prof)

    def _fail(self, msg):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询玩家"
        self.set_status(msg.split("\n")[0], C_ACCENT)
        self.body.clear_widgets()
        c = Card(orientation="vertical", size_hint_y=None,
                 padding=(dp(16), dp(14)), spacing=dp(6))
        c.add_widget(lab("没查到", 15, C_ACCENT, bold=True, height=24))
        for line in msg.split("\n"):
            c.add_widget(lab(line, 11.5, C_INK2, height=22))
        c.bind(minimum_height=c.setter("height"))
        self.body.add_widget(c)
        self.body.add_widget(self._recent_widget())

    def set_status(self, text, color=C_MUTED):
        self.status.text = text
        self.status.color = color

    # ---------- 渲染 ----------
    def _render(self, p):
        self.body.clear_widgets()

        c = Card(orientation="vertical", size_hint_y=None, height=dp(96),
                 padding=(dp(16), dp(12)), spacing=dp(2))
        c.add_widget(lab(p["name"], 20, C_INK, bold=True, height=28))
        sub = " · ".join([x for x in [p["serverName"], p["menpai"],
                                      (p["sex"] + " " if p["sex"] else "") +
                                      (str(p["age"]) + " 岁" if p["age"] else "")] if x])
        c.add_widget(lab(sub, 12, C_MUTED, height=18))
        rk = ("榜上第 %s 名" % p["rank"]) if p.get("rank") else "未上榜"
        c.add_widget(lab(rk, 11.5, C_INK2, height=18))
        self.body.add_widget(c)

        grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(10))
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
                        padding=(dp(12), dp(6)), spacing=0)
            cell.add_widget(lab(k, 10, C_MUTED, height=14))
            cell.add_widget(lab(str(v), 15, C_INK, bold=True, height=24))
            grid.add_widget(cell)
        grid.height = dp(56) * 4 + dp(10) * 3
        self.body.add_widget(grid)

        if p["prepared"]:
            self._section("准备位（%d）" % len(p["prepared"]))
            c2 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(14), dp(8)))
            c2.height = dp(8) + dp(22) * len(p["prepared"]) + dp(8)
            for slot, nm in p["prepared"].items():
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab(slot, 11.5, C_MUTED, height=22))
                row.add_widget(lab(nm, 12, C_INK2, height=22, halign="right"))
                c2.add_widget(row)
            self.body.add_widget(c2)

        if p["equips"]:
            self._section("装备（%d）" % len(p["equips"]))
            c3 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(14), dp(8)))
            c3.height = dp(8) + dp(22) * len(p["equips"]) + dp(8)
            for e in p["equips"]:
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab(e["slot"], 11.5, C_MUTED, height=22))
                row.add_widget(lab(e["n"], 12, C_INK2, height=22, halign="right"))
                c3.add_widget(row)
            self.body.add_widget(c3)

        if p["history"]:
            self._section("传承（%d 世）" % len(p["history"]))
            c4 = Card(orientation="vertical", size_hint_y=None, spacing=dp(2),
                      padding=(dp(14), dp(8)))
            c4.height = dp(8) + dp(22) * len(p["history"]) + dp(8)
            for i, h in enumerate(p["history"], 1):
                row = BoxLayout(size_hint_y=None, height=dp(22))
                row.add_widget(lab("第 %d 世" % i, 11, C_MUTED, height=22))
                row.add_widget(lab(h["n"] or "—", 12, C_INK2, height=22, halign="right"))
                c4.add_widget(row)
            self.body.add_widget(c4)

        skills = p["skills"]
        if skills:
            self._section("武学（%d 门）" % len(skills))
            c5 = Card(orientation="vertical", size_hint_y=None, spacing=dp(1),
                      padding=(dp(14), dp(8)))
            show = skills[:60]
            c5.height = dp(8) + dp(21) * len(show) + dp(8)
            for i, s in enumerate(show, 1):
                row = BoxLayout(size_hint_y=None, height=dp(21))
                row.add_widget(lab(str(i), 10, C_MUTED, height=21))
                row.add_widget(lab(s["n"], 12, C_INK2, height=21))
                row.add_widget(lab(str(s["lv"]), 11.5, C_INK2, height=21, halign="right"))
                c5.add_widget(row)
            self.body.add_widget(c5)
            if len(skills) > len(show):
                self.body.add_widget(lab("仅显示前 %d 门，完整数据请用「保存数据」" % len(show),
                                         10.5, C_MUTED, height=20, halign="center"))

        self.btn_save = Button(
            text="保存数据（JSON）", font_name=FONT, font_size=sp(13),
            size_hint_y=None, height=dp(48),
            background_color=C_SOFT, background_normal="", color=C_ACCENT,
        )
        self.btn_save.bind(on_release=lambda *a: self.save())
        self.body.add_widget(self.btn_save)

        self.footer = lab("数据时间：%s" % p.get("fetchedAt", ""), 10.5, C_MUTED,
                          height=20, halign="center")
        self.body.add_widget(self.footer)

    def _section(self, title):
        self.body.add_widget(lab(title, 13, C_INK2, bold=True, height=dp(26)))

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

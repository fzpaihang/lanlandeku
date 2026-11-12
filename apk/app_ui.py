# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询（Android / 桌面均可运行）

第二版：做减法 + 重排信息架构。
查询态 / 结果态分离，结果态把表单折叠成一行摘要；
层级靠字号、留白和分隔线建立，不再靠一层层白卡片。
"""
import io
import json
import os
import re
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

# ---------- 设计令牌：纸色底 + 极少量朱砂 ----------
C_BG = (0.980, 0.969, 0.941, 1)          # #FAF7F0
C_SOFT = (0.945, 0.937, 0.910, 1)        # #F1EFE8
C_ACCENT_SOFT = (0.980, 0.925, 0.906, 1)  # #FAECE7
C_INK = (0.173, 0.165, 0.149, 1)         # #2C2A26
C_INK2 = (0.420, 0.396, 0.357, 1)        # #6B655B
C_MUTED = (0.533, 0.529, 0.502, 1)       # #888780
C_ACCENT = (0.659, 0.204, 0.184, 1)      # #A8342F
C_LINE = (0.910, 0.886, 0.839, 1)        # #E8E2D6


def hex_of(c):
    return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in c[:3])


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


def split_num(v):
    """「16.82亿」→（数字本体, 单位），单位用更小更淡的字号。"""
    m = re.match(r"^([+-]?[\d.]+)(亿|万|转|世)?$", str(v).strip())
    if not m:
        return str(v), ""
    return m.group(1), m.group(2) or ""


def lab(text, size=13, color=C_INK, bold=False, height=None, halign="left", markup=False):
    w = Label(
        text=text, font_name=FONT, font_size=sp(size), color=color,
        bold=bold, halign=halign, valign="middle", markup=markup,
        size_hint_y=None, height=dp(height if height is not None else size * 1.9),
    )
    w.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
    return w


def txt_button(text, color=C_ACCENT, width=None, height=48, size=13):
    b = Button(
        text=text, font_name=FONT, font_size=sp(size), color=color,
        background_color=(0, 0, 0, 0), background_normal="",
        size_hint_y=None, height=dp(height),
    )
    if width is not None:
        b.size_hint_x = None
        b.width = dp(width)
    return b


class Root(BoxLayout):
    """整屏纸色底：Kivy 的 BoxLayout 默认透明，必须自己画。"""

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


class HLine(BoxLayout):
    """1px 分隔线，代替白卡片做分组。"""

    def __init__(self, color=None, thickness=1, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(thickness))
        super(HLine, self).__init__(**kw)
        from kivy.graphics import Color, Rectangle
        with self.canvas:
            self._c = Color(*(color or C_LINE))
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size

    def set_color(self, color):
        self._c.rgba = color


class Chip(BoxLayout):
    """浅朱砂底的小徽章（结果态唯一保留的容器）。"""

    def __init__(self, text, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(30))
        kw.setdefault("size_hint_x", None)
        super(Chip, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*C_ACCENT_SOFT)
            self._bg = RoundedRectangle(radius=[dp(15)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        self.label = lab(text, 12, C_ACCENT, bold=True, height=30, halign="center")
        self.add_widget(self.label)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def set_text(self, t):
        self.label.text = t


class CnSpinnerOption(SpinnerOption):
    def __init__(self, **kw):
        kw.setdefault("font_name", FONT)
        kw.setdefault("font_size", sp(14))
        kw.setdefault("color", C_INK)
        super(CnSpinnerOption, self).__init__(**kw)


class PlayerLookup(App):
    AUTO_LABEL = "自动探测（不推荐）"
    EXAMPLES = [
        {"uid": 21079729670, "name": "刘小年", "server": "taptap_3", "serverName": "丹凤朝阳"},
        {"uid": 21079747122, "name": "观云者", "server": "taptap_3", "serverName": "丹凤朝阳"},
    ]

    def build(self):
        self.title = "玩家查询"
        self.prof = None
        self.busy = False
        self.hint_open = False
        self.prep_open = False
        self.mode = "query"

        root = Root(orientation="vertical", padding=(dp(20), dp(16), dp(20), dp(12)),
                    spacing=dp(12))

        # 顶部状态化容器：查询态放表单，结果态放一行摘要
        self.top = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        self.top.bind(minimum_height=self.top.setter("height"))
        root.add_widget(self.top)

        sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12),
                              padding=(0, 0, 0, dp(12)))
        self.body.bind(minimum_height=self.body.setter("height"))
        sv.add_widget(self.body)
        root.add_widget(sv)

        self._build_query_widgets()
        self._build_result_summary()
        self.show_query()
        return root

    # ---------- 查询态控件（复用实例，切回时保留输入与分区） ----------
    def _build_query_widgets(self):
        head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(56), spacing=dp(2))
        head.add_widget(lab("江湖 · 玩家查询", 20, C_INK, bold=True, height=30))
        head.add_widget(lab("按分区查角色档案与榜单信息", 12, C_MUTED, height=20))

        self.servers = self._servers()
        names = [n for _k, n in self.servers] + [self.AUTO_LABEL]
        row_srv = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        pre = lab("分区：", 13, C_MUTED, height=48)
        pre.size_hint_x = None
        pre.width = dp(52)
        row_srv.add_widget(pre)
        # Spinner 去掉白底，视觉上就是一行文字链接；点击仍用 Kivy 原生下拉
        self.spin = Spinner(
            text=self._name_of(self._picked_key()) or names[0], values=names,
            font_name=FONT, font_size=sp(14), color=C_INK, halign="left",
            background_color=(0, 0, 0, 0), background_normal="",
            size_hint_y=None, height=dp(48), option_cls=CnSpinnerOption,
        )
        self.spin.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
        self.spin.bind(text=lambda inst, v: self._save_pick(v))
        row_srv.add_widget(self.spin)
        more = lab("切换", 12, C_ACCENT, bold=True, height=48, halign="right")
        more.size_hint_x = None
        more.width = dp(48)
        row_srv.add_widget(more)

        # 输入区：无白卡，只有下边框；focus 时边框转朱砂
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(lab("角色 UID", 12, C_MUTED, height=20))
        self.inp = TextInput(
            text="", hint_text="例如 21079729670", font_name=FONT, font_size=sp(16),
            multiline=False, input_type="number", padding=[dp(2), dp(10)],
            size_hint_y=None, height=dp(48),
            background_color=(0, 0, 0, 0), background_normal="", background_active="",
            foreground_color=C_INK, hint_text_color=C_MUTED, cursor_color=C_ACCENT,
        )
        self.inp.bind(on_text_validate=lambda *a: self.start())
        form.add_widget(self.inp)
        self.inp_line = HLine(color=C_LINE, thickness=1)
        self.inp.bind(focus=lambda inst, v: self.inp_line.set_color(C_ACCENT if v else C_LINE))
        form.add_widget(self.inp_line)

        self.btn = Button(
            text="查询玩家", font_name=FONT, font_size=sp(15), bold=True,
            size_hint_y=None, height=dp(48),
            background_color=C_ACCENT, background_normal="", color=(1, 1, 1, 1),
        )
        self.btn.bind(on_release=lambda *a: self.start())

        # 只在失败/查询中显示；成功不宣告
        self.q_status = lab("", 12, C_MUTED, height=0)

        self.query_widgets = [head, row_srv, form, self.btn, self.q_status]

    def _build_result_summary(self):
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(12))
        self.summary = lab("", 14, C_INK2, height=48)
        bar.add_widget(self.summary)
        edit = txt_button("修改", C_ACCENT, width=56, height=48)
        edit.bind(on_release=lambda *a: self.show_query())
        bar.add_widget(edit)
        self.result_widgets = [bar, HLine()]

    # ---------- 状态切换 ----------
    def show_query(self):
        self.mode = "query"
        self.top.clear_widgets()
        for w in self.query_widgets:
            self.top.add_widget(w)
        self.set_status("")
        self._show_idle()

    def show_result(self, p):
        self.mode = "result"
        self.prof = p
        self.top.clear_widgets()
        for w in self.result_widgets:
            self.top.add_widget(w)
        self.summary.text = "%s · %s" % (p["serverName"], p.get("uid") or "")
        self.prep_open = False     # 换一个新结果时重新收起
        self._render(p)

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

    # ---------- 查询态空状态 ----------
    def _show_idle(self):
        self.body.clear_widgets()
        self.body.add_widget(self._hint_widget())
        self.body.add_widget(self._recent_widget())

    def _hint_widget(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row.add_widget(lab("UID 是游戏内角色 ID，不是登录账号", 13, C_INK2, height=40))
        q = lab("？", 14, C_ACCENT, bold=True, height=40, halign="center")
        q.size_hint_x = None
        q.width = dp(32)
        row.add_widget(q)
        box.add_widget(row)
        if self.hint_open:
            box.add_widget(lab("默认只查选中的分区，速度快、不易被限流；分区选择会被记住。",
                               12, C_INK2, height=34))
            box.add_widget(lab("不确定在哪个区时，用列表最后的「自动探测」逐区尝试。",
                               12, C_INK2, height=34))
            box.add_widget(lab("关于 · 当前 %s · 数据来自游戏接口" % code_version(),
                               12, C_MUTED, height=22))
        box.add_widget(HLine())
        box.bind(on_touch_down=lambda inst, t: self._hint_touch(inst, t))
        return box

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
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        box.bind(minimum_height=box.setter("height"))
        box.add_widget(lab("最近查询" if has else "试试示例 UID", 14, C_INK,
                           bold=True, height=28))
        if not has:
            box.add_widget(lab("下面是丹凤朝阳的示例角色，点一下自动填入",
                               12, C_MUTED, height=22))
        for r in rows:
            b = txt_button("%s  ·  %s" % (r.get("uid"), r.get("name") or r.get("serverName") or ""),
                           color=C_INK2, height=48, size=13)
            b.halign = "left"
            b.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
            b.bind(on_release=lambda inst, u=r.get("uid"), k=r.get("server"): self._fill(u, k))
            box.add_widget(b)
            box.add_widget(HLine())
        return box

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
            Clock.schedule_once(lambda dt: self._fail("查询异常", err))
            return
        Clock.schedule_once(lambda dt: self._done(prof, server))

    def _done(self, prof, server="auto"):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询玩家"
        if not prof:
            if server == "auto":
                self._fail("五个分区都没有这个 UID", "确认是游戏内的角色 ID 吗？")
            else:
                self._fail("该分区未找到，试试「自动探测」", "确认分区选对了吗？请求繁忙请稍后重试")
            return
        L.add_recent(prof)
        self.set_status("")
        self.show_result(prof)   # 成功不宣告，直接把结果推到首屏

    def _fail(self, title, detail):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询玩家"
        self.set_status(title, C_ACCENT)
        self.body.clear_widgets()
        bar = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4),
                        padding=(dp(12), dp(10)))
        bar.bind(minimum_height=bar.setter("height"))
        bar.add_widget(lab(title, 14, C_ACCENT, bold=True, height=24))
        bar.add_widget(lab(detail, 12, C_INK2, height=24))
        self.body.add_widget(bar)
        self.body.add_widget(HLine())
        self.body.add_widget(self._recent_widget())

    def set_status(self, text, color=C_MUTED):
        self.q_status.text = text or ""
        self.q_status.color = color
        self.q_status.height = dp(24) if text else dp(0)

    # ---------- 结果态：无白卡，靠字号与留白分层 ----------
    def _render(self, p):
        self.body.clear_widgets()

        # 结果头：名字是主角，名次做成浅朱砂徽章
        head = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(12))
        head.add_widget(lab(p["name"], 26, C_INK, height=44))
        rank_txt = ("榜上第 %s 名" % p["rank"]) if p.get("rank") else "未上榜"
        head.add_widget(Chip(rank_txt, width=dp(120)))
        self.body.add_widget(head)

        sub = " · ".join([x for x in [p["serverName"], p["menpai"],
                                      (p["sex"] + " " if p["sex"] else "") +
                                      (str(p["age"]) + " 岁" if p["age"] else "")] if x])
        self.body.add_widget(lab(sub, 14, C_INK2, height=26))
        self.body.add_widget(HLine())

        # 8 项指标：2×4 无边框网格，单位降级次色
        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(12), dp(14)))
        vals = [
            ("等级", "%s" % p["lv"] + ("（估）" if p.get("lvEstimated") else "") if p["lv"] else "—"),
            ("武学造诣", ("%.2f" % p["kongfu"]) if p.get("kongfu") is not None else "—"),
            ("经验", L.fmt_big(p["exp"])),
            ("福缘", p["fuyuan"] if p.get("fuyuan") is not None else "—"),
            ("气血", L.fmt_big(p.get("qiMax"))),
            ("家产", L.fmt_big(p.get("jiaLi"))),
            ("侠义", L.fmt_big(p.get("zhengqi"))),
            ("转数", ("%s 转" % p["inheritCount"]) if p.get("inheritCount") else "—"),
        ]
        for k, v in vals:
            cell = BoxLayout(orientation="vertical", size_hint_y=None,
                             height=dp(48), spacing=0)
            cell.add_widget(lab(k, 11, C_MUTED, height=16))
            num, unit = split_num(v)
            big = 20 if k == "武学造诣" else 18
            markup = num
            if unit:
                markup += "[size=12][color=%s]%s[/color][/size]" % (hex_of(C_MUTED), unit)
            cell.add_widget(lab(markup, big, C_INK, height=30, markup=True))
            grid.add_widget(cell)
        grid.height = dp(48) * 4 + dp(14) * 3
        self.body.add_widget(grid)
        self.body.add_widget(HLine())

        # 准备位：槽位 · 技能 键值对列表，默认收起前 4 条
        self._kv_section("准备位", list((p["prepared"] or {}).items()), p)

        if p["equips"]:
            self._plain_section("装备（%d）" % len(p["equips"]),
                                [(e["slot"], e["n"]) for e in p["equips"]])
        if p["history"]:
            self._plain_section("传承（%d 世）" % len(p["history"]),
                                [("第 %d 世" % i, h["n"] or "—")
                                 for i, h in enumerate(p["history"], 1)])
        skills = p["skills"] or []
        if skills:
            show = skills[:60]
            self._plain_section("武学（%d 门）" % len(skills),
                                [(s["n"], str(s["lv"])) for s in show])
            if len(skills) > len(show):
                self.body.add_widget(lab("仅显示前 %d 门" % len(show),
                                         12, C_MUTED, height=22, halign="center"))

        # 底部文字按钮收口
        foot = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(12))
        b1 = txt_button("复制 UID")
        b1.bind(on_release=lambda *a: self.copy_uid())
        b2 = txt_button("保存数据", color=C_INK2)
        b2.bind(on_release=lambda *a: self.save())
        b3 = txt_button("再查一个")
        b3.bind(on_release=lambda *a: self.again())
        for b in (b1, b2, b3):
            foot.add_widget(b)
        self.body.add_widget(foot)

    def _kv_section(self, title, rows, p):
        self.body.add_widget(lab(title, 14, C_INK, bold=True, height=28))
        show = rows if self.prep_open else rows[:4]
        for slot, nm in show:
            self._kv_row(slot, nm)
        if len(rows) > 4:
            b = txt_button("展开全部 %d 项" % len(rows) if not self.prep_open else "收起",
                           color=C_ACCENT, height=48, size=13)
            b.bind(on_release=lambda *a: self._toggle_prep(p))
            self.body.add_widget(b)
        self.body.add_widget(HLine())

    def _toggle_prep(self, p):
        self.prep_open = not self.prep_open
        self._render(p)

    def _kv_row(self, left, right):
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(12))
        l = lab(str(left), 12, C_MUTED, height=34)
        l.size_hint_x = None
        l.width = dp(90)
        row.add_widget(l)
        row.add_widget(lab(str(right), 13, C_INK2, height=34, halign="right"))
        self.body.add_widget(row)
        self.body.add_widget(HLine())

    def _plain_section(self, title, rows):
        self.body.add_widget(lab(title, 14, C_INK, bold=True, height=28))
        for left, right in rows:
            self._kv_row(left, right)
        self.body.add_widget(HLine())

    # ---------- 结果态动作 ----------
    def copy_uid(self):
        uid = str((self.prof or {}).get("uid") or "")
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(uid)
            self.summary.text = "已复制 UID · %s" % uid
        except Exception:
            # p4a 可能没打包 clipboard provider：降级为填回输入框
            self.inp.text = uid
            self.show_query()
            self.set_status("剪贴板不可用，UID 已填回输入框", C_INK2)

    def again(self):
        self.inp.text = ""
        self.show_query()

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
            self.summary.text = "已保存 JSON"
        except Exception as e:
            self.summary.text = "保存失败：%s" % e


def run():
    PlayerLookup().run()


if __name__ == "__main__":
    run()

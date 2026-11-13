# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询（Android / 桌面均可运行）

第三版：参考网页高手榜的详情展示。
属性区仍保持 2x4 无边框网格；只在「短标签成组」的准备位/装备用 Pill 胶囊，
武学加搜索与展开，传承用竖向时间线并展示 inheritTime 日期。
"""
import io
import json
import os
import re
import sys
import threading
import time
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

# 这两个模块是后加的，必须允许缺失：老版本 APK 里没有它们，
# 任何 import 失败都只能降级为「纯 UID 查询」，不能让 App 打不开。
try:
    import names_index as NI
except Exception:
    NI = None
try:
    import archive_local as AL
except Exception:
    AL = None
try:
    import webview_overlay as WV
except Exception:
    WV = None

# 安卓返回键的两种 keycode：老版本 SDL 给 27(ESC)，新版本给 AC_BACK
_BACK_KEYS = (27, 1073742094)

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

# 网页的标题用宋体（--serif），安卓上优先找系统自带的衬线中文字体，没有就退回黑体
_SERIF_CANDIDATES = [
    "/system/fonts/NotoSerifCJK-Regular.ttc",
    "/system/fonts/NotoSerifSC-Regular.otf",
    "/system/fonts/SourceHanSerifSC-Regular.otf",
    "/system/fonts/DroidSerif-Regular.ttf",
]
SERIF = FONT
for _p in _SERIF_CANDIDATES:
    if os.path.exists(_p):
        try:
            LabelBase.register(name="CNSerif", fn_regular=_p)
            SERIF = "CNSerif"
            break
        except Exception:
            pass

C_BG = (0.965, 0.957, 0.937, 1)          # #F6F4EF 页面底色，与网页 --bg 一致
C_CARD = (1.0, 1.0, 1.0, 1)              # #FFFFFF 卡片
C_SOFT = (0.945, 0.937, 0.910, 1)        # #F1EFE8
C_ACCENT_SOFT = (0.953, 0.906, 0.894, 1)  # #F3E7E4，与网页 --accent-soft 一致
C_INK = (0.122, 0.137, 0.157, 1)         # #1F2328
C_INK2 = (0.290, 0.322, 0.376, 1)        # #4A5260
C_MUTED = (0.376, 0.408, 0.459, 1)       # #606870 加深：原先 #8A919C 在手机上发灰发虚
C_ACCENT = (0.549, 0.184, 0.157, 1)      # #8C2F28
C_ACCENT_DK = (0.478, 0.153, 0.122, 1)   # #7A271F 按钮按下
C_LINE = (0.867, 0.847, 0.808, 1)        # #DDD8CE 边框略加深，边界更清楚
C_LINE2 = (0.941, 0.925, 0.890, 1)       # #F0ECE3



def hex_of(c):
    return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in c[:3])


def fmt_date(t):
    """inheritTime 是秒级时间戳，按北京时间格式化成网页口径的 24-02。"""
    try:
        t = int(t or 0)
        return time.strftime("%y-%m", time.gmtime(t + 8 * 3600)) if t > 0 else ""
    except Exception:
        return ""


def code_version():
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
    m = re.match(r"^([+-]?[\d.]+)(亿|万|转|世|次|级)?$", str(v).strip())
    if not m:
        return str(v), ""
    return m.group(1), m.group(2) or ""


def lab(text, size=13, color=C_INK, bold=False, height=None, halign="left",
        markup=False, serif=False):
    w = Label(
        text=text, font_name=(SERIF if serif else FONT), font_size=sp(size), color=color,
        bold=bold, halign=halign, valign="middle", markup=markup,
        size_hint_y=None, height=dp(height if height is not None else size * 1.9),
    )
    w.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
    return w


WEB_BASE = "https://fzpaihang.github.io/lanlandeku/"

# 隐私名单兜底（与 data/hidden.json 同步）。昵称索引下载失败 / 用旧缓存时，
# 这一份仍然生效，保证任何情况下都不会对这些 uid 发起查询。
HIDDEN_UIDS = set(("4047491326", "4168426", "6622657", "21079748748"))


def open_url(url):
    """用系统浏览器打开链接。

    安卓上 webbrowser 模块不一定实现，所以优先走 Intent；
    桌面调试时 Intent 不存在，自动回退到 webbrowser。
    """
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        it = Intent(Intent.ACTION_VIEW)
        it.setData(Uri.parse(url))
        act.startActivity(it)
        return True
    except Exception:
        pass
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


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


class Seal(BoxLayout):
    """网页左上角那个红印章：44×44、圆角 10、白字竖排。"""

    def __init__(self, text="查\n询", side=44, radius=10, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("size", (dp(side), dp(side)))
        kw.setdefault("pos_hint", {"center_y": 0.5})
        super(Seal, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*C_ACCENT)
            self._bg = RoundedRectangle(radius=[dp(radius)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        self.add_widget(lab(text, 14, (1, 1, 1, 1), bold=True, height=side,
                            halign="center", serif=True))

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class Card(BoxLayout):
    """白底圆角卡片：结果区、查询区都用它，对应网页 .lk-result。"""

    def __init__(self, radius=14, pad=16, bg=None, border=None, spacing=10, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("padding", (dp(pad), dp(pad), dp(pad), dp(pad)))
        kw.setdefault("spacing", dp(spacing))
        super(Card, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle, Line
        self._r = dp(radius)
        with self.canvas.before:
            Color(*(bg or C_CARD))
            self._bg = RoundedRectangle(radius=[self._r], pos=self.pos, size=self.size)
            Color(*(border or C_LINE))
            self._ln = Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                               self._r), width=1)
        self.bind(pos=self._sync, size=self._sync)
        self.bind(minimum_height=self.setter("height"))

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height, self._r)


class RoundInput(TextInput):
    """白底圆角输入框：对应网页 .lk-input（48 高、圆角 12、聚焦变强调色）。"""

    def __init__(self, radius=12, **kw):
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        kw.setdefault("background_active", "")
        kw.setdefault("padding", [dp(14), dp(13)])
        super(RoundInput, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle, Line
        self._r = dp(radius)
        with self.canvas.before:
            Color(*C_CARD)
            self._bg = RoundedRectangle(radius=[self._r], pos=self.pos, size=self.size)
            self._lnc = Color(*C_LINE)
            self._ln = Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                               self._r), width=1)
        self.bind(pos=self._sync, size=self._sync, focus=self._on_focus)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height, self._r)

    def _on_focus(self, _inst, value):
        self._ln.width = 1.6 if value else 1
        self._lnc.rgba = C_ACCENT if value else C_LINE


class PrimaryButton(Button):
    """实心强调色圆角按钮：对应网页 .lk-btn（48 高、圆角 12、按下变深）。"""

    def __init__(self, radius=12, **kw):
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        kw.setdefault("color", (1, 1, 1, 1))
        super(PrimaryButton, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            self._c = Color(*C_ACCENT)
            self._bg = RoundedRectangle(radius=[dp(radius)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync, state=self._on_state)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _on_state(self, _inst, value):
        self._c.rgba = C_ACCENT_DK if value == "down" else C_ACCENT


class RoundSpinner(Spinner):
    """白底圆角分区选择器：对应网页 .lk-select。"""

    def __init__(self, radius=12, **kw):
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        super(RoundSpinner, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle, Line
        self._r = dp(radius)
        with self.canvas.before:
            Color(*C_CARD)
            self._bg = RoundedRectangle(radius=[self._r], pos=self.pos, size=self.size)
            Color(*C_LINE)
            self._ln = Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                               self._r), width=1)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height, self._r)


class Chip(BoxLayout):
    """结果头名次徽章（结果态唯一保留的独立容器）。"""

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
        self.label = lab(text, 13.5, C_ACCENT, bold=True, height=30, halign="center")
        self.add_widget(self.label)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def set_text(self, t):
        self.label.text = t


class Pill(BoxLayout):
    """短标签胶囊：槽位灰小字 + 名称深粗字。只用于准备位/装备这类短键值对。"""

    def __init__(self, key, val, accent=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        kw.setdefault("spacing", dp(6))
        kw.setdefault("padding", (dp(10), 0, dp(10), 0))
        super(Pill, self).__init__(orientation="horizontal", **kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*(C_ACCENT if accent else C_ACCENT_SOFT))
            self._bg = RoundedRectangle(radius=[dp(20)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        k = lab(str(key), 11, (1, 1, 1, 1) if accent else C_MUTED, height=40)
        k.size_hint_x = None
        k.width = dp(46)
        self.add_widget(k)
        self.add_widget(lab(str(val), 13, (1, 1, 1, 1) if accent else C_INK,
                            bold=True, height=40))
        self.key_text = str(key)
        self.val_text = str(val)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class CnSpinnerOption(SpinnerOption):
    """分区下拉选项：白底深字 + 细分隔线。

    Kivy 默认的 SpinnerOption 用半透明灰色 button atlas，叠在页面上又灰又糊，
    这里全部改成实色，字也加大加粗，点按时变强调色。
    """

    def __init__(self, **kw):
        kw.setdefault("font_name", FONT)
        kw.setdefault("font_size", sp(16))
        kw.setdefault("color", C_INK)
        kw.setdefault("bold", True)
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(56))
        kw.setdefault("background_color", C_CARD)
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        super(CnSpinnerOption, self).__init__(**kw)
        # 再强制一次：某些 Kivy 版本会在构造后套用默认主题
        self.background_normal = ""
        self.background_down = ""
        self.background_color = C_CARD
        from kivy.graphics import Color, Line
        with self.canvas.after:
            Color(*C_LINE)
            self._sep = Line(width=1)
        self.bind(pos=self._sync_sep, size=self._sync_sep, state=self._on_state)
        self._sync_sep()

    def _sync_sep(self, *a):
        if getattr(self, "_sep", None) is not None:
            self._sep.points = [self.x + dp(12), self.y,
                                self.right - dp(12), self.y]

    def _on_state(self, _inst, st):
        self.color = C_ACCENT if st == "down" else C_INK


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
        self.skill_open = False
        self.skill_query = ""
        self.mode = "query"
        self._hits = []
        self._sug_ev = None
        self._web = None

        root = Root(orientation="vertical", padding=(dp(20), dp(16), dp(20), dp(12)),
                    spacing=dp(12))
        self.top = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        self.top.bind(minimum_height=self.top.setter("height"))
        root.add_widget(self.top)

        sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12),
                              padding=(0, 0, 0, dp(12)))
        self.body.bind(minimum_height=self.body.setter("height"))
        self.body.bind(pos=self._body_sync, size=self._body_sync)
        sv.add_widget(self.body)
        root.add_widget(sv)

        self._build_query_widgets()
        self._build_result_summary()
        self.show_query()

        # 内嵌浏览器打开时，返回键先关网页，而不是退出 App
        try:
            from kivy.core.window import Window
            Window.bind(on_keyboard=self._on_key)
        except Exception:
            pass

        # 昵称索引后台加载，绝不阻塞界面；加载完只更新一行提示
        if NI:
            NI.load_async(lambda st, n: Clock.schedule_once(
                lambda dt: self._on_names_ready(st, n)))
        return root

    def _on_names_ready(self, st, n):
        if st == "ready" and n:
            if self.mode == "query":
                self.set_status("昵称索引已就绪（%d 个），可以按昵称搜" % n, C_MUTED)
        elif st == "empty":
            if self.mode == "query":
                self.set_status("昵称索引不可用，先按 UID 查", C_MUTED)
        if self.inp.text and not self.inp.text.strip().isdigit():
            self._do_search(self.inp.text)

    def _build_query_widgets(self):
        # 顶部：印章 + 标题 + 副标题（对应网页 .hero 里的 .brand）
        head = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54),
                         spacing=dp(13))
        head.add_widget(Seal("查\n询", 48))
        title_col = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(54),
                              spacing=dp(0))
        t = lab("玩家查询", 24, C_INK, bold=True, height=34, serif=True)
        title_col.add_widget(t)
        title_col.add_widget(lab("放置江湖 · 昵称或 UID 查实时档案", 13, C_INK2, height=22))
        head.add_widget(title_col)

        self.web_btn = txt_button("高手榜 ›", C_ACCENT, width=82, height=54, size=14)
        self.web_btn.bind(on_release=lambda *a: self._open_web())
        head.add_widget(self.web_btn)

        self.servers = self._servers()
        names = [n for _k, n in self.servers] + [self.AUTO_LABEL]

        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        form.bind(minimum_height=form.setter("height"))

        self.inp = RoundInput(
            text="", hint_text="输入昵称或 UID", font_name=FONT, font_size=sp(17),
            multiline=False, input_type="text",
            size_hint_y=None, height=dp(52),
            foreground_color=C_INK, hint_text_color=C_INK2, cursor_color=C_ACCENT,
        )
        self.inp.bind(on_text_validate=lambda *a: self.start())
        self.inp.bind(text=self._on_query_text)
        form.add_widget(self.inp)

        # 昵称候选提示行：默认折叠，有结果才展开（网页里是下拉列表，这里用弹层）
        self.sug = Button(
            text="", font_name=FONT, font_size=sp(14.5), halign="left", valign="middle",
            size_hint_y=None, height=dp(0), opacity=0,
            background_color=(0, 0, 0, 0), background_normal="", color=C_ACCENT,
        )
        self.sug.bind(width=lambda inst, v: setattr(inst, "text_size", (v - dp(4), None)))
        self.sug.bind(on_release=lambda *a: self._show_candidates())
        form.add_widget(self.sug)

        self.btn = PrimaryButton(
            text="查询玩家", font_name=FONT, font_size=sp(16.5), bold=True,
            size_hint_y=None, height=dp(52),
        )
        self.btn.bind(on_release=lambda *a: self.start())
        form.add_widget(self.btn)

        row_srv = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52),
                            spacing=dp(10))
        pre = lab("分区", 14.5, C_INK2, bold=True, height=52)
        pre.size_hint_x = None
        pre.width = dp(46)
        row_srv.add_widget(pre)
        self.spin = RoundSpinner(
            text=self._name_of(self._picked_key()) or names[0], values=names,
            font_name=FONT, font_size=sp(16), color=C_INK, halign="left",
            size_hint_y=None, height=dp(52), option_cls=CnSpinnerOption,
        )
        self.spin.bind(width=lambda inst, v: setattr(inst, "text_size", (v - dp(30), None)))
        self.spin.bind(text=lambda inst, v: self._save_pick(v))
        row_srv.add_widget(self.spin)
        form.add_widget(row_srv)

        self.q_status = lab("", 13.5, C_INK2, height=0)
        form.add_widget(self.q_status)

        form.add_widget(lab("输入昵称命中时会自动切到该角色所在区；UID 为 5–12 位数字。",
                            13, C_INK2, height=24))
        form.add_widget(lab("当前代码版本：%s" % code_version(), 12.5, C_MUTED, height=22))

        self.query_widgets = [head, form]

    def _build_result_summary(self):
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(12))
        self.summary = lab("", 14, C_INK2, height=48)
        bar.add_widget(self.summary)
        web = txt_button("榜单", C_INK2, width=52, height=48, size=12.5)
        web.bind(on_release=lambda *a: self._open_web(self._result_uid()))
        bar.add_widget(web)
        edit = txt_button("修改", C_ACCENT, width=52, height=48)
        edit.bind(on_release=lambda *a: self.show_query())
        bar.add_widget(edit)
        self.result_widgets = [bar, HLine()]

    def _result_uid(self):
        p = self.prof or {}
        return p.get("uid") or p.get("userid")

    def _open_web(self, uid=None):
        """打开网页高手榜：带上当前分区，查过人的话顺带高亮他。"""
        key = (self.prof or {}).get("server") if self.mode == "result" else None
        if key not in dict(self.servers):
            key = self._picked_key()
        q = []
        if key in dict(self.servers):
            q.append("s=" + key)
        if uid:
            q.append("me=" + str(uid))
        url = WEB_BASE + ("?" + "&".join(q) if q else "")
        if self._open_in_app(url):
            return
        if open_url(url):
            return
        msg = "没有可用的浏览器，打不开网页"
        self.set_status(msg, C_ACCENT)
        if self.mode == "result" and self.summary.text != msg:
            keep = self.summary.text
            self.summary.text = msg
            Clock.schedule_once(lambda dt: setattr(self.summary, "text", keep), 3)

    def _open_in_app(self, url):
        """优先用内嵌 WebView 打开；不支持或失败返回 False，由调用方回退外部浏览器。"""
        if not WV:
            self._web_fail("缺少 webview_overlay 模块（热更包不完整）")
            return False
        try:
            if self._web is None:
                self._web = WV.WebOverlay()
            self._web.open(url)
            return True
        except Exception as e:
            detail = ""
            try:
                detail = self._web.last_error or ""
            except Exception:
                pass
            self._web_fail("%s: %s%s" % (
                type(e).__name__, str(e)[:130],
                ("｜" + detail) if detail and detail not in str(e) else ""))
            self._web = None          # 下次重新尝试创建
            return False

    def _web_fail(self, msg):
        """把内嵌失败的原因留在页面上，用户回来还能看到，方便定位。"""
        self.set_status("内嵌网页失败，已改用浏览器", C_ACCENT)
        self.body.clear_widgets()
        self._set_body_card(True)
        self.body.add_widget(lab("内嵌网页打开失败", 18, C_ACCENT, bold=True, height=32))
        d = lab(msg, 13.5, C_INK2, height=1)
        d.bind(texture_size=lambda inst, sz: setattr(inst, "height", sz[1] + dp(6)))
        self.body.add_widget(d)
        self.body.add_widget(lab("已改用系统浏览器。把上面这段字发我即可定位。",
                                13, C_MUTED, height=28))

    def _on_key(self, _win, key, *args):
        """返回键：网页开着就先关网页，其它情况交回 Kivy 默认处理。"""
        if key in _BACK_KEYS and self._web is not None and self._web.is_open():
            try:
                self._web.close()
            except Exception:
                self._web = None
            return True
        return False

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
        self.prep_open = False
        self.skill_open = False
        self.skill_query = ""
        self._render(p)

    # ---------- 分区 ----------
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
    def _set_body_card(self, on):
        """结果态把内容区包成白卡（对应网页 .lk-result），查询态恢复无底色。"""
        from kivy.graphics import Color, RoundedRectangle, Line
        self.body.canvas.before.clear()
        if not on:
            self._body_bg = None
            self.body.padding = (0, 0, 0, dp(12))
            return
        self.body.padding = (dp(14), dp(14), dp(14), dp(14))
        self._body_r = dp(14)
        with self.body.canvas.before:
            Color(*C_CARD)
            self._body_bg = RoundedRectangle(radius=[self._body_r],
                                             pos=self.body.pos, size=self.body.size)
            Color(*C_LINE)
            self._body_ln = Line(rounded_rectangle=(self.body.x, self.body.y,
                                                    self.body.width, self.body.height,
                                                    self._body_r), width=1)
        self._body_sync()

    def _body_sync(self, *a):
        if getattr(self, "_body_bg", None) is None:
            return
        self._body_bg.pos = self.body.pos
        self._body_bg.size = self.body.size
        self._body_ln.rounded_rectangle = (self.body.x, self.body.y,
                                           self.body.width, self.body.height, self._body_r)

    def _show_idle(self):
        self._set_body_card(False)
        self.body.clear_widgets()
        self.body.add_widget(self._hint_widget())
        self.body.add_widget(self._recent_widget())

    def _hint_widget(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row.add_widget(lab("UID 是游戏内角色 ID，不是登录账号", 14.5, C_INK2, height=40))
        q = lab("？", 14, C_ACCENT, bold=True, height=40, halign="center")
        q.size_hint_x = None
        q.width = dp(32)
        row.add_widget(q)
        box.add_widget(row)
        if self.hint_open:
            box.add_widget(lab("默认只查选中的分区，速度快、不易被限流；分区选择会被记住。",
                               13.5, C_INK2, height=38))
            box.add_widget(lab("不确定在哪个区时，用列表最后的「自动探测」逐区尝试。",
                               13.5, C_INK2, height=38))
            box.add_widget(lab("关于 · 当前 %s · 数据来自游戏接口" % code_version(),
                               13, C_MUTED, height=26))
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
                               13.5, C_INK2, height=26))
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

    # ---------- 昵称搜索 ----------
    def _on_query_text(self, _inst, value):
        if self._sug_ev:
            try:
                self._sug_ev.cancel()
            except Exception:
                pass
        self._sug_ev = Clock.schedule_once(lambda dt: self._do_search(value), 0.3)

    def _do_search(self, value):
        text = (value or "").strip()
        if not text or text.isdigit():
            return self._hide_sug()
        if not NI:
            return self._hide_sug()
        if NI.state() == "loading":
            self._show_sug("昵称索引加载中…（直接输 UID 也能查）", [])
            return
        hits = NI.search(text, 8)
        self._hits = hits
        if not hits:
            self._show_sug("没找到「%s」，试试完整昵称或直接输 UID" % text, [])
            return
        if len(hits) == 1:
            h = hits[0]
            self._show_sug("找到「%s · %s」，点这里填入" % (h["n"], h["sn"] or h["s"]), hits)
        else:
            self._show_sug("找到 %d 个，点这里选择" % len(hits), hits)

    def _show_sug(self, text, hits):
        if not hasattr(self, "sug"):
            return
        self.sug.text = text
        self.sug.height = dp(36)
        self.sug.opacity = 1.0 if hits else 0.55
        self.sug.disabled = not bool(hits)

    def _hide_sug(self):
        if not hasattr(self, "sug"):
            return
        self.sug.text = ""
        self.sug.height = dp(0)
        self.sug.opacity = 0
        self._hits = []

    def _show_candidates(self):
        hits = self._hits or []
        if not hits:
            return
        from kivy.uix.popup import Popup

        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        sv = ScrollView(do_scroll_x=False)
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        inner.bind(minimum_height=inner.setter("height"))

        pop = None
        for h in hits:
            tail = h["sn"] or h["s"]
            label = "%s  ·  %s%s" % (h["n"], tail, ("  lv%s" % h["lv"]) if h["lv"] else "")
            b = Button(text=label, font_name=FONT, font_size=sp(16), halign="left",
                       valign="middle", size_hint_y=None, height=dp(54),
                       background_color=C_SOFT, background_normal="", color=C_INK)
            b.bind(width=lambda inst, v: setattr(inst, "text_size", (v - dp(20), None)))
            b.bind(on_release=lambda inst, x=h: self._pick(x))
            inner.add_widget(b)

        sv.add_widget(inner)
        box.add_widget(sv)
        pop = Popup(title="选择角色", title_font=FONT, title_size=sp(17),
                    content=box, size_hint=(0.9, 0.62),
                    background_color=C_BG, separator_color=C_ACCENT)
        self._popup = pop
        pop.open()

    def _pick(self, h):
        try:
            self._popup.dismiss()
        except Exception:
            pass
        self._fill(h["u"], h["s"])
        self._hide_sug()
        self.set_status("已选中「%s」，点「查询玩家」开始" % h["n"], C_INK2)

    # ---------- 查询 ----------
    def start(self):
        if self.busy:
            return
        raw = (self.inp.text or "").strip()
        if not raw:
            self.set_status("请输入昵称或 UID", C_ACCENT)
            return
        if raw.isdigit():
            return self._begin(int(raw))

        # 非纯数字 → 当作昵称搜本地索引
        hits = NI.search(raw, 8) if NI else []
        hits = [h for h in hits if not self._hidden(h["u"])]
        if not hits:
            if NI and NI.state() == "loading":
                self.set_status("昵称索引还在加载，稍等一下，或直接输 UID", C_ACCENT)
            elif not NI:
                self.set_status("当前版本不支持昵称查询，请输入 UID", C_ACCENT)
            else:
                self.set_status("没找到「%s」，试试完整昵称或直接输 UID" % raw, C_ACCENT)
            return
        if len(hits) == 1:
            self._fill(hits[0]["u"], hits[0]["s"])
            self._begin(int(hits[0]["u"]))
            return
        self._hits = hits
        self._show_candidates()

    def _hidden(self, uid):
        """隐私名单：内置兜底 ∪ 索引里的 hidden 字段。"""
        k = str(uid or "").strip()
        if k in HIDDEN_UIDS:
            return True
        try:
            return bool(NI and NI.is_hidden(k))
        except Exception:
            return False

    def _deny(self):
        """名单内角色：不发请求，也不保留上一次的档案。"""
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询玩家"
        self.prof = None
        if self.mode != "query":
            self.show_query()
        self.set_status("该角色不支持查询", C_ACCENT)
        self.body.clear_widgets()
        self._set_body_card(True)
        self.body.add_widget(lab("无法查询", 20, C_ACCENT, bold=True, height=34))
        self.body.add_widget(lab("该角色已设置为不公开档案，无法查看详细信息。",
                                 14, C_INK2, height=30))
        self.body.add_widget(lab("请换一个 UID 或昵称再试。", 13.5, C_MUTED, height=26))

    def _begin(self, uid):
        if self._hidden(uid):
            self._deny()
            return
        self.busy = True
        self.btn.disabled = True
        self.btn.text = "查询中…"
        self.set_status("连接中…", C_ACCENT)
        key = self.key_of(self.spin.text)
        threading.Thread(target=self._worker, args=(uid, key), daemon=True).start()

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
        # 先本地记账（一定不丢），再尽力同步到仓库；同步失败完全不影响展示
        if AL:
            try:
                AL.record(prof)
                if AL.configured():
                    AL.sync_async()
            except Exception:
                pass
        self.set_status("")
        self.show_result(prof)

    def _fail(self, title, detail):
        self.busy = False
        self.btn.disabled = False
        self.btn.text = "查询玩家"
        self.set_status(title, C_ACCENT)
        self._set_body_card(True)
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
        self.q_status.height = dp(28) if text else dp(0)

    # ---------- 结果态 ----------
    def _render(self, p):
        self._set_body_card(True)
        self.body.clear_widgets()

        head = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(12))
        head.add_widget(lab(p["name"], 24, C_INK, bold=True, height=44, serif=True))
        rank_txt = ("榜上第 %s 名" % p["rank"]) if p.get("rank") else "未上榜"
        head.add_widget(Chip(rank_txt, width=dp(120)))
        self.body.add_widget(head)

        parts = [p["serverName"], p["menpai"],
                 (p["sex"] + " " if p["sex"] else "") +
                 (str(p["age"]) + " 岁" if p["age"] else "")]
        if p.get("looks") is not None:
            try:
                parts.append("容貌 %s" % format(int(p["looks"]), ",d"))
            except (TypeError, ValueError):
                pass
        self.body.add_widget(lab(" · ".join([x for x in parts if x]),
                                14, C_INK2, height=26))
        self.body.add_widget(HLine())

        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(12), dp(14)))
        vals = [
            ("等级", "%s" % p["lv"] + ("（估）" if p.get("lvEstimated") else "") if p["lv"] else "—"),
            ("武学造诣", ("%.2f" % p["kongfu"]) if p.get("kongfu") is not None else "—"),
            ("经验", L.fmt_big(p["exp"])),
            ("福缘", p["fuyuan"] if p.get("fuyuan") is not None else "—"),
            ("气血", L.fmt_big(p.get("qiMax"))),
            ("加力", L.fmt_big(p.get("jiaLi"))),
            ("正气", L.fmt_big(p.get("zhengqi"))),
            ("传承", ("%s 次" % p["inheritCount"]) if p.get("inheritCount") else "—"),
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

        prep = list((p["prepared"] or {}).items())
        if prep:
            self._pill_section("准备位 %d 个" % len(prep), prep, p, collapsible=True)
        if p["equips"]:
            self._pill_section("装备 %d 件" % len(p["equips"]),
                               [(e["slot"], e["n"]) for e in p["equips"]])
        self._timeline_section(p)
        self._skill_section(p)

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

    # ---------- 短标签胶囊（准备位 / 装备） ----------
    def _pill_section(self, title, rows, p=None, collapsible=False):
        self.body.add_widget(lab(title, 14, C_INK, bold=True, height=28))
        show = rows if (not collapsible or self.prep_open) else rows[:4]
        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(8), dp(8)))
        for k, v in show:
            grid.add_widget(Pill(k, v))
        n = (len(show) + 1) // 2
        grid.height = dp(40) * n + dp(8) * max(0, n - 1)
        self.body.add_widget(grid)
        if collapsible and len(rows) > 4:
            b = txt_button("展开全部 %d 项" % len(rows) if not self.prep_open else "收起",
                           color=C_ACCENT, height=48, size=13)
            b.bind(on_release=lambda *a: self._toggle_prep(p))
            self.body.add_widget(b)
        self.body.add_widget(HLine())

    def _toggle_prep(self, p):
        self.prep_open = not self.prep_open
        self._render(p)

    # ---------- 传承竖向时间线 ----------
    def _timeline_section(self, p):
        rows = p["history"] or []
        if not rows:
            return
        self.body.add_widget(lab("传承历程 · %d 转" % len(rows), 14, C_INK,
                                bold=True, height=28))
        for i, h in enumerate(rows, 1):
            last = i == len(rows)   # 末项就是当前角色
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
            idx = lab(str(i), 11, C_MUTED, height=34)
            idx.size_hint_x = None
            idx.width = dp(22)
            row.add_widget(idx)
            row.add_widget(lab(h["n"] or "—", 13, C_ACCENT if last else C_INK2,
                               bold=last, height=34))
            dt = lab(fmt_date(h.get("t")), 11, C_MUTED, height=34, halign="right")
            dt.size_hint_x = None
            dt.width = dp(56)
            row.add_widget(dt)
            self.body.add_widget(row)
            self.body.add_widget(HLine(color=C_ACCENT if last else C_LINE))
        self.body.add_widget(HLine())

    # ---------- 武学：默认 10 条 + 展开全部 + 仅展开后的搜索 ----------
    def _skill_section(self, p):
        skills = p["skills"] or []
        if not skills:
            return
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))
        head = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        head.add_widget(lab("武学 %d 门" % len(skills), 14, C_INK, bold=True, height=32))
        self.skill_toggle = txt_button("", C_ACCENT, width=dp(150), height=32, size=12)
        self.skill_toggle.bind(on_release=lambda *a: self._toggle_skill(p))
        head.add_widget(self.skill_toggle)
        box.add_widget(head)

        self.skill_search = TextInput(
            text=self.skill_query, hint_text="搜索武学名称", font_name=FONT,
            font_size=sp(13), multiline=False, padding=[dp(10), dp(10)],
            size_hint_y=None, height=dp(44),
            background_color=(0, 0, 0, 0), background_normal="", background_active="",
            foreground_color=C_INK, hint_text_color=C_MUTED, cursor_color=C_ACCENT,
        )
        self.skill_search.bind(text=lambda inst, v: self._on_skill_search(v, p))
        box.add_widget(self.skill_search)
        box.add_widget(HLine())

        self.skill_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        self.skill_list.bind(minimum_height=self.skill_list.setter("height"))
        box.add_widget(self.skill_list)
        self.body.add_widget(box)
        self._sync_skill_ui(p)

    def _sync_skill_ui(self, p):
        n = len(p["skills"] or [])
        self.skill_toggle.text = "收起" if self.skill_open else ("展开全部 %d 门" % n)
        self.skill_search.height = dp(44) if self.skill_open else dp(0)
        self.skill_search.opacity = 1.0 if self.skill_open else 0.0
        self.skill_search.disabled = not self.skill_open
        self._render_skill_list(p)

    def _render_skill_list(self, p):
        self.skill_list.clear_widgets()
        items = list(p["skills"] or [])
        q = (self.skill_query or "").strip()
        if q:
            items = [s for s in items if q in str(s["n"])]
        elif not self.skill_open:
            items = items[:10]
        if not items:
            self.skill_list.add_widget(lab("没有匹配的武学", 12, C_MUTED, height=34))
            self.skill_list.height = dp(34)
            return
        for s in items:
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
            row.add_widget(lab(s["n"], 13, C_INK2, height=34))
            lv = lab("%s 级" % s["lv"], 11, C_MUTED, height=34, halign="right")
            lv.size_hint_x = None
            lv.width = dp(72)
            row.add_widget(lv)
            self.skill_list.add_widget(row)
            self.skill_list.add_widget(HLine())
        self.skill_list.height = dp(35) * len(items)

    def _toggle_skill(self, p):
        self.skill_open = not self.skill_open
        if not self.skill_open:
            self.skill_query = ""
            self.skill_search.text = ""
        self._sync_skill_ui(p)

    def _on_skill_search(self, v, p):
        self.skill_query = v
        self._render_skill_list(p)

    # ---------- 结果态动作 ----------
    def copy_uid(self):
        uid = str((self.prof or {}).get("uid") or "")
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(uid)
            self.summary.text = "已复制 UID · %s" % uid
        except Exception:
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

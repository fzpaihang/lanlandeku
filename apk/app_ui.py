# -*- coding: utf-8 -*-
"""放置江湖 · 玩家查询（Android / 桌面均可运行）

第三版：参考网页高手榜的详情展示。
属性区仍保持 2x4 无边框网格；只在「短标签成组」的准备位/装备用 Pill 胶囊，
武学加搜索与展开，传承用竖向时间线并展示 inheritTime 日期。
"""

# ---------------------------------------------------------------------------
# 这两行必须在任何 kivy 模块之前执行。
# keyboard_mode 只在 Window 创建时读一次（Window 在 import kivy.uix.* 时就被创建），
# 运行到 App.run() 里再 Config.set 是无效的 —— 之前一直卡在默认的 single 模式，
# Kivy 便拒绝申请系统键盘（日志 "virtual keyboard not allowed, single mode"），
# 点输入框自然什么都不弹。
# ---------------------------------------------------------------------------
try:
    from kivy.config import Config as _KC
    _KC.set("kivy", "keyboard_mode", "system")
except Exception:
    pass

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
from kivy.metrics import Metrics, dp
from kivy.metrics import sp as _sp_raw
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

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
try:
    import skill_groups as SG          # 武学分类表，缺失时退化成不分组
except Exception:
    SG = None
try:
    import native_input as NATIVE      # 安卓原生输入框，绕开 Kivy 软键盘
except Exception:
    NATIVE = None
try:
    import inline_input as INLINE      # 盖在输入框上的原生 EditText（正常键盘）
except Exception:
    INLINE = None


# ---------- 屏幕适配 ----------
# 模拟器分辨率 900×1600 / 240dpi = 600dp 宽，真机通常只有 360~412dp。
# 写死 dp 的尺寸在模拟器上宽松、到手机上就挤，所以这里统一按「逻辑宽度」分档。
# 注意不能在此处 import Window：此时 Kivy 还没创建窗口，
# 提前建窗会让 run() 里设置的软键盘配置失效。
def vp_w():
    """当前视口逻辑宽度（dp）。"""
    try:
        from kivy.core.window import Window
        return float(Window.width) / max(float(Metrics.density), 0.01)
    except Exception:
        return 360.0


def vp_h():
    try:
        from kivy.core.window import Window
        return float(Window.height) / max(float(Metrics.density), 0.01)
    except Exception:
        return 640.0


def sp(v):
    """字体尺寸。

    Kivy 的 sp 会乘系统字体缩放（真机常见 1.15~1.3）。本页所有行高都是固定
    dp，完全跟随放大就会把文字顶出容器，所以把缩放限在 1.12 以内。
    """
    try:
        f = max(1.0, min(float(Metrics.fontscale or 1.0), 1.12))
    except Exception:
        f = 1.0
    return v * float(Metrics.density) * f


def hp():
    """内容区左右留白（dp）。

    宽度超过 520dp 时不再拉满，而是把内容收窄居中——否则在 600dp 的模拟器
    或平板上，卡片会被抻成一条长条，和手机上的观感完全不是一回事。
    320dp 以下把留白收到 10dp，给内容多让出 12dp。
    """
    w = vp_w()
    if w >= 520:
        return max(16.0, (w - 520.0) / 2.0)
    if w < 340:
        return 10.0
    return 16.0

# 安卓返回键的两种 keycode：老版本 SDL 给 27(ESC)，新版本给 AC_BACK
_BACK_KEYS = (27, 1073742094)

# 中文字体。**首选打进 APK 的 NotoSansSC 子集**（scripts/build_font_subset.py 生成），
# 这样任何 ROM 上字形都一致；系统字体只在老 APK（热更包不带 .ttf）上兜底。
#
# 系统字体为什么不可靠：
# - .ttc 是字体集合，Kivy/FreeType 只能取第 0 个 face，NotoSansCJK-Regular.ttc 的
#   第 0 个 face 是日文，中文会按日文字形渲染（连简体「门」都没有，直接变豆腐块）。
# - NotoSansSC-*.otf 是纯 CJK 子集，不含拉丁，UID / 数字 / "/" / "·" 会全变方块。
# - NotoSansCJKsc-Regular.ttf 只有部分 ROM 有；DroidSansFallback 在 Android 9 后已移除。
# 三条全落空时 FONT 会退回 Roboto（不含中文）→ 全屏豆腐块。MuMu 是 AOSP，一定有
# 第一个文件，所以这个故障在模拟器上永远复现不出来。
def _local_font():
    """定位打包进 APK 的字体：__file__ 目录（热更时是 live/）→ ANDROID_APP_PATH → sys.path。"""
    rel = os.path.join("fonts", "NotoSansSC-Regular.ttf")
    cands = [os.path.dirname(os.path.abspath(__file__))]
    ap = os.environ.get("ANDROID_APP_PATH")
    if ap:
        cands.append(ap)
    cands += [p for p in sys.path if p and os.path.isdir(p)]
    seen = set()
    for d in cands:
        d = os.path.normpath(d)
        if d in seen:
            continue
        seen.add(d)
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            return p
    return ""


# 厂商 ROM 的中文字体（各家路径不同，命中就用）。M 系列不在此列：MiSansLatin 不含中文。
_VENDOR_FONTS = [
    "/system/fonts/MiSans-Regular.ttf",
    "/system/fonts/MiSans-Normal.ttf",
    "/system/fonts/HarmonyOS_Sans_SC_Regular.ttf",
    "/system/fonts/HarmonyOS_Sans_SC.ttf",
    "/system/fonts/OPPOSans-Regular.ttf",
    "/system/fonts/OPPO_Sans_Regular.ttf",
    "/system/fonts/vivoSans-Regular.ttf",
    "/system/fonts/SourceHanSansSC-Regular.otf",
]

FONT = "Roboto"
FONT_SRC = "内置 Roboto（无中文）"
_lp = _local_font()
_CN_PAIRS = [(_lp, None)] if _lp else []
_CN_PAIRS += [
    ("/system/fonts/NotoSansCJKsc-Regular.ttf", None),
    ("/system/fonts/DroidSansFallback.ttf", None),
] + [(p, None) for p in _VENDOR_FONTS] + [
    ("/system/fonts/NotoSansCJK-Regular.ttc", None),   # 最后兜底，可能是日文字形
]

for _reg, _bold in _CN_PAIRS:
    if _reg and os.path.exists(_reg):
        try:
            LabelBase.register(
                name="CN", fn_regular=_reg,
                fn_bold=_bold if (_bold and os.path.exists(_bold)) else None,
            )
            FONT = "CN"
            FONT_SRC = "打包子集" if _reg == _lp else os.path.basename(_reg)
            break
        except Exception:
            pass

# 最后一档：扫 /system/fonts 里名字像中文字体的单体文件。注册失败也不影响（只是回到 Roboto）。
if FONT == "Roboto":
    try:
        for _fn in sorted(os.listdir("/system/fonts")):
            _low = _fn.lower()
            if not _low.endswith((".ttf", ".otf")):
                continue
            if not any(k in _low for k in ("cjk", "han", "hei", "song", "sc", "chinese")):
                continue
            if "latin" in _low:
                continue
            try:
                LabelBase.register(name="CN", fn_regular="/system/fonts/" + _fn)
                FONT, FONT_SRC = "CN", _fn
                break
            except Exception:
                continue
    except Exception:
        pass

# 标题的衬线体：只在存在「单体简体宋体」时才启用。
# NotoSerifCJK-Regular.ttc 同样是集合、默认日文字形，宁可退回黑体也不要用它。
_SERIF_CANDIDATES = [
    "/system/fonts/NotoSerifSC-Regular.otf",
    "/system/fonts/SourceHanSerifSC-Regular.otf",
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

# 「江湖」两个字要有一点印章的笔锋，所以单独用衬线体渲染。
# 系统里唯一可用的中文衬线是 NotoSerifCJK 的 .ttc（face 0 是日文），
# 但「江」「湖」这两字的日文与简体字形完全一致，只在这里用不会出问题。
SEAL = FONT
_SEAL_CANDIDATES = [
    "/system/fonts/NotoSerifCJK-Regular.ttc",
    "/system/fonts/NotoSerifSC-Regular.otf",
]
for _p in _SEAL_CANDIDATES:
    if os.path.exists(_p):
        try:
            LabelBase.register(name="CNSeal", fn_regular=_p)
            SEAL = "CNSeal"
            break
        except Exception:
            pass

print("[font] FONT=%s(%s) SERIF=%s SEAL=%s" % (FONT, FONT_SRC, SERIF, SEAL))

# 色板：以「高手榜」那页为基准统一（暖米底 + 深绛红），三页共用同一套。
# 原先主色 #8C2F28 偏橙、详情页顶栏又是另一种红，两个红放在一起就散了。
C_BG = (0.973, 0.961, 0.945, 1)          # #F8F5F1 页面底色
C_CARD = (1.0, 1.0, 1.0, 1)              # #FFFFFF 卡片
C_SOFT = (0.949, 0.937, 0.914, 1)        # #F2EFE9 次级底（搜索框/占位块）
C_ACCENT_SOFT = (0.976, 0.894, 0.859, 1)  # #F9E4DB 强调浅底（胶囊/徽章），太浅在白卡上会消失
C_INK = (0.165, 0.145, 0.133, 1)         # #2A2522 主文字，暖黑（原先偏冷 #1F2328）
C_INK2 = (0.376, 0.337, 0.302, 1)        # #60564D 次文字
C_MUTED = (0.545, 0.498, 0.455, 1)       # #8B7F74 弱文字 / 标签
# 顶栏和按钮拆成两个色：原来是同一个 #7B2D26，整页像一大块暗红。
# 顶栏压到浅一档的绛棕当框架，按钮提亮成朱砂当行动点，强调文字单独留深色。
C_BAR = (0.549, 0.290, 0.243, 1)         # #8C4A3E 原顶栏底色（v24 起顶栏改浅底，保留备用）
C_SEAL = (0.482, 0.176, 0.149, 1)        # #7B2D26 「江湖」印章底色
C_TONE = (0.706, 0.353, 0.243, 1)        # #B45A3E 结果页顶部装饰条（比印章浅一档）
C_BTN = (0.761, 0.353, 0.227, 1)         # #C25A3A 主按钮
C_BTN_DK = (0.678, 0.290, 0.180, 1)      # #AD4A2E 按钮按下
C_ACCENT = (0.659, 0.282, 0.173, 1)      # #A8482C 强调文字 / 聚焦描边
C_LINE = (0.898, 0.871, 0.835, 1)        # #E5DED5 卡片描边
C_LINE2 = (0.945, 0.929, 0.906, 1)       # #F1EDE7 行内细线



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
        markup=False, serif=False, shorten=False, font=None):
    """单行文本。shorten=True 时宽度不够用省略号，而不是折行溢出到控件外面。

    Kivy 的 Label **不会裁切超出高度的文字**：text_size 的宽一旦塌到 0，
    每个汉字会各占一行，而 height 只够一行，多出来的字就画到控件外，
    把下面的列表盖住（「武学 206 门」被压成竖排就是这么来的）。
    """
    w = Label(
        text=text, font_name=(font or (SERIF if serif else FONT)), font_size=sp(size), color=color,
        bold=bold, halign=halign, valign="middle", markup=markup,
        shorten=shorten, shorten_from="right",
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


def _android_activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _js(v):
    """把 Python str 变成 java.lang.String。

    ContentValues.put / Intent.putExtra 都有好几个重载（String / Integer /
    Long / byte[] / CharSequence…），pyjnius 不做自动类型收敛时会抛
    "No methods called put"。和 setText 那个坑同源，所以统一走这里 cast。
    """
    from jnius import autoclass, cast
    return cast("java.lang.String", autoclass("java.lang.String")(v))


def save_to_download(filename, text):
    """把文本写进公共「下载」目录，返回给人看的路径。

    Android 10+ 走 MediaStore，不需要任何存储权限；10 以下直接抛错让用户改用
    分享（老系统要 WRITE_EXTERNAL_STORAGE，为存一个 json 申请读写权限不值得）。
    """
    from jnius import autoclass
    version = autoclass("android.os.Build$VERSION")
    if int(version.SDK_INT) < 29:
        raise RuntimeError("系统低于 Android 10，请用「分享文本」")

    Downloads = autoclass("android.provider.MediaStore$Downloads")
    ContentValues = autoclass("android.content.ContentValues")

    values = ContentValues()
    values.put(_js("_display_name"), _js(filename))
    values.put(_js("mime_type"), _js("application/json"))
    values.put(_js("relative_path"), _js("Download"))

    resolver = _android_activity().getContentResolver()
    uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
    if uri is None:
        raise RuntimeError("系统拒绝创建文件")
    out = resolver.openOutputStream(uri)
    try:
        out.write(text.encode("utf-8"))
        out.flush()
    finally:
        out.close()
    return "下载/" + filename


def share_text(filename, text):
    """走系统分享面板发出去。key 用字面量，避免静态字段类型在 pyjnius 里对不上。"""
    from jnius import autoclass
    Intent = autoclass("android.content.Intent")
    intent = Intent()
    intent.setAction(_js("android.intent.action.SEND"))
    intent.setType(_js("text/plain"))
    intent.putExtra(_js("android.intent.extra.SUBJECT"), _js("玩家档案 " + filename))
    intent.putExtra(_js("android.intent.extra.TEXT"), _js(text))
    chooser = Intent.createChooser(intent, _js("分享玩家档案"))
    _android_activity().startActivity(chooser)


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
            self._bgc = Color(*C_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def on_touch_down(self, touch):
        # 原生输入框只盖住输入框那一小块，点别处时 Kivy 会收到触摸 →
        # 这时把原生框收掉，否则它会一直浮在页面上面（还会盖住分区下拉）。
        if INLINE is not None and INLINE.showing():
            INLINE.hide()
        return super(Root, self).on_touch_down(touch)


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


def gap(h=8):
    """纯占位：用来在卡片里拉开组间距，比塞空洞的 Label 干净。"""
    return Widget(size_hint_y=None, height=dp(h))


class ToneBar(BoxLayout):
    """结果页顶部的朱砂色装饰条（纯色块，不含文字）。

    分区名和 UID 放在它下面、页面米色底上：红块只做「这一页是档案」的色标，
    文字仍然用深色压在最容易读的底色上。
    """

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 0)
        super(ToneBar, self).__init__(orientation="vertical", **kw)
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            self._c = Color(*C_TONE)
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


class AppBar(BoxLayout):
    """浅米底顶栏 + 红印章，复刻网页高手榜的头部。

    原来这里是整条深绛红，和下面的米色内容各自成块。改成浅底之后，
    页面只有一个视觉焦点——左边那枚「江湖」印章，和高手榜一致。
    """

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(58))
        kw.setdefault("padding", (dp(14), 0, dp(10), 0))
        kw.setdefault("spacing", dp(10))
        super(AppBar, self).__init__(orientation="horizontal", **kw)
        from kivy.graphics import Color, Rectangle
        # 顶栏和页面同色，且不画分隔线：那条 1px 横线在手机上很抢眼，
        # 像给页面横切了一刀。头部靠印章和字号自己立住，不靠线。
        # Color 必须存下来：结果页要把这块底色切成朱砂红。
        with self.canvas.before:
            self._bgc = Color(*C_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

        # 返回键常驻，通过宽度/透明度切显隐，避免反复增删控件
        self.back = Button(
            text="‹", font_name=FONT, font_size=sp(26), bold=True,
            color=C_INK, size_hint_x=None, width=0, opacity=0,
            background_color=(0, 0, 0, 0), background_normal="",
        )
        self.add_widget(self.back)

        # 红印章：44×44、圆角 10、绛红底白字，竖排「江湖」
        self.seal = BoxLayout(orientation="vertical", size_hint=(None, None),
                              size=(0, 0), spacing=0, opacity=0)
        from kivy.graphics import Color as _C, RoundedRectangle
        with self.seal.canvas.before:
            _C(*C_SEAL)
            self._seal_bg = RoundedRectangle(radius=[dp(10)], pos=self.seal.pos,
                                             size=self.seal.size)
        self.seal.bind(pos=self._seal_sync, size=self._seal_sync)
        self.seal.add_widget(lab("江", 13, (1, 1, 1, 1), height=22, halign="center",
                                 bold=True, font=SEAL))
        self.seal.add_widget(lab("湖", 13, (1, 1, 1, 1), height=22, halign="center",
                                 bold=True, font=SEAL))
        self.add_widget(self.seal)

        self.col = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(58),
                             spacing=0, size_hint_x=1)
        self.title_lab = lab("", 16, C_INK, bold=True, height=30, serif=True,
                             shorten=True)
        self.sub_lab = lab("", 11, C_MUTED, height=20, shorten=True)
        self.col.add_widget(self.title_lab)
        self.col.add_widget(self.sub_lab)
        self.add_widget(self.col)

        self.right_btn = Button(
            text="", font_name=FONT, font_size=sp(12.5), color=C_ACCENT,
            size_hint_x=None, width=0, opacity=0,
            background_color=(0, 0, 0, 0), background_normal="",
        )
        self.add_widget(self.right_btn)

        # 副标题可点：结果页的 UID 点一下就复制，省掉底栏一个按钮
        self._sub_cb = None
        self.sub_lab.bind(on_touch_down=self._sub_touch)

    def bind_sub(self, fn):
        """给副标题挂点击回调（结果页用来点 UID 复制）。"""
        self._sub_cb = fn

    def _sub_touch(self, inst, touch):
        if self._sub_cb and inst.collide_point(*touch.pos):
            self._sub_cb()
            return True
        return False

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _seal_sync(self, *a):
        self._seal_bg.pos = self.seal.pos
        self._seal_bg.size = self.seal.size

    def _set_tone(self, dark):
        """结果页顶栏换成朱砂红底 + 白字（查询页保持米色，只有印章是红的）。

        红色块和下面米色卡片形成明确的分层，也把分区名从正文里「提」出来。
        """
        if dark:
            self._bgc.rgba = C_SEAL
            self.title_lab.color = (1, 1, 1, 1)
            self.sub_lab.color = (1, 1, 1, 0.72)
            self.back.color = (1, 1, 1, 1)
            self.right_btn.color = (1, 1, 1, 1)
        else:
            self._bgc.rgba = C_BG
            self.title_lab.color = C_INK
            self.sub_lab.color = C_INK2
            self.back.color = C_INK
            self.right_btn.color = C_ACCENT

    def set_content(self, title="", sub="", right="", back=False, seal=False,
                    dark=False):
        self._set_tone(dark)
        self.title_lab.text = title or ""
        self.sub_lab.text = sub or ""
        if seal:
            # 查询页：不放主标题，只留一行说明，和印章一起垂直居中
            self.seal.size = (dp(44), dp(44))
            self.seal.opacity = 1
            self.title_lab.height = dp(0)
            self.sub_lab.font_size = sp(14)
            self.sub_lab.color = C_INK          # 原来是 C_INK2，真机上偏灰，加深
            self.sub_lab.height = dp(24)
            self.col.padding = (0, dp(17), 0, dp(17))
        else:
            self.seal.size = (0, 0)
            self.seal.opacity = 0
            self.title_lab.font_size = sp(16)
            self.title_lab.color = C_INK
            self.sub_lab.font_size = sp(11)
            self.sub_lab.color = C_MUTED
            if sub:
                self.title_lab.height = dp(30)
                self.sub_lab.height = dp(20)
                self.col.padding = (0, dp(4), 0, dp(4))
            else:
                self.title_lab.height = dp(58)
                self.sub_lab.height = dp(0)
                self.col.padding = (0, 0, 0, 0)
        self.back.width = dp(26) if back else dp(0)
        self.back.opacity = 1 if back else 0
        self.right_btn.text = right or ""
        self.right_btn.width = dp(72) if right else dp(0)
        self.right_btn.opacity = 1 if right else 0

    def bind_back(self, fn):
        old = getattr(self, "_back_cb", None)
        if old:
            try:
                self.back.unbind(on_release=old)
            except Exception:
                pass
        self._back_cb = fn
        self.back.bind(on_release=fn)

    def bind_right(self, fn):
        old = getattr(self, "_right_cb", None)
        if old:
            try:
                self.right_btn.unbind(on_release=old)
            except Exception:
                pass
        self._right_cb = fn
        self.right_btn.bind(on_release=fn)


def _sdl_start_text_input():
    """直接调 SDL_StartTextInput，兜底把软键盘真正挂到 Kivy 上。

    安卓上 Kivy 只在 request_keyboard 时让 SDL 申请文本输入；内嵌网页把输入法
    抢走之后，这条链路有时不会重建，表现为「点了输入框没键盘 / 打了字不进去」。
    这里直接戳一下原生接口，重复调用无副作用。
    """
    if not ("ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ):
        return
    try:
        import ctypes
    except Exception:
        return
    for name in ("libSDL2.so", None):
        try:
            lib = ctypes.CDLL(name) if name else ctypes.CDLL(None)
            fn = getattr(lib, "SDL_StartTextInput")
        except Exception:
            continue
        try:
            fn.restype = None
            fn()
        except Exception:
            pass
        return


def _sdl_stop_text_input():
    """SDL_StopTextInput：收键盘时告诉 SDL 别再往 Kivy 送文本。"""
    if not ("ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ):
        return
    try:
        import ctypes
    except Exception:
        return
    for name in ("libSDL2.so", None):
        try:
            lib = ctypes.CDLL(name) if name else ctypes.CDLL(None)
            fn = getattr(lib, "SDL_StopTextInput")
        except Exception:
            continue
        try:
            fn.restype = None
            fn()
        except Exception:
            pass
        return


class RoundInput(TextInput):
    """白底圆角输入框：对应网页 .lk-input（48 高、圆角 12、聚焦变强调色）。

    bg 可换底色：武学搜索框放在白卡里，用浅灰底才不会「看不见」（原来它是全透明
    背景，在白卡上只剩一行漂浮的字，根本不像输入框）。
    """

    def __init__(self, radius=12, bg=None, native_title=None, native_ok_text="确定",
                 on_native_ok=None, use_native=True, **kw):
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        kw.setdefault("background_active", "")
        kw.setdefault("padding", [dp(14), dp(13)])
        super(RoundInput, self).__init__(**kw)
        # 原生输入框：Kivy 的软键盘在部分 ROM 上完全失效（点框不出键盘、只能粘贴），
        # 点这里就弹系统的 EditText，中文/长按粘贴都由系统负责。
        self.native_title = native_title
        self.native_ok_text = native_ok_text
        self.on_native_ok = on_native_ok
        self.use_native = use_native
        self._native_ok = None
        self._ime_on = False
        self._inline = False
        from kivy.graphics import Color, RoundedRectangle, Line
        self._r = dp(radius)
        with self.canvas.before:
            Color(*(bg or C_CARD))
            self._bg = RoundedRectangle(radius=[self._r], pos=self.pos, size=self.size)
            self._lnc = Color(*C_LINE)
            self._ln = Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                               self._r), width=1)
        self.bind(pos=self._sync, size=self._sync, focus=self._on_focus)

    # ---------- 系统键盘：直连 SDL ----------
    def _android(self):
        """安卓 + jnius 可用？决定走 SDL 直连还是普通桌面行为。"""
        if not self.use_native or NATIVE is None:
            return False
        try:
            from kivy.utils import platform
            if platform != "android":
                return False
        except Exception:
            return False
        if self._native_ok is None:
            try:
                self._native_ok = NATIVE.available()
            except Exception:
                self._native_ok = False
        return bool(self._native_ok)

    def _bind_ime(self):
        """聚焦时接管输入。

        优先走「原生 EditText 内联覆盖」（inline_input.py）：它是真正的文本控件，
        输入法给的是普通拼音键盘，长按菜单也是系统那套（可跟随 App locale 显示中文）。

        为什么不用 SDL 自带的目标：那个 DummyEdit 是 View 子类，inputType 写死在
        Java 的 onCreateInputConnection 里（老版 SDL 给的是 VISIBLE_PASSWORD=0x91），
        输入法会当密码框切成安全键盘，Python 侧改不了。

        inline 不可用时退回 SDL_StartTextInput（安全键盘，但至少能输数字）。
        """
        if not self._android():
            return
        if self._show_inline():
            return
        try:
            from kivy.core.window import Window
            Window.unbind(on_textinput=self._ime_text, on_key_down=self._ime_key)
            Window.bind(on_textinput=self._ime_text, on_key_down=self._ime_key)
        except Exception:
            return
        self._ime_on = True
        _sdl_start_text_input()

    def _show_inline(self):
        """把自己的位置换算成安卓像素，盖一个 EditText 上去。"""
        if INLINE is None or not INLINE.available():
            return False
        try:
            from kivy.core.window import Window
            wx, wy = self.to_window(self.x, self.y)
            top = Window.height - (wy + self.height)
            ok = INLINE.show((wx, top, self.width, self.height), self.text,
                             on_text=self._from_inline, on_done=self._inline_done)
            if ok:
                self._ime_on = True
                self._inline = True
            return ok
        except Exception as e:
            print("[input] inline failed: %r" % (e,))
            return False

    def _from_inline(self, val):
        """原生框里的文字回写到 Kivy 控件（不回调回去，避免来回打架）。"""
        self.text = val

    def _inline_done(self):
        """IME 上点「完成」：当成回车处理（查 UID 时直接发起查询）。"""
        self.dispatch("on_text_validate")

    def _unbind_ime(self):
        if not self._android():
            return
        if self._inline:
            self._inline = False
            try:
                if INLINE is not None:
                    INLINE.hide()
            except Exception:
                pass
            return
        try:
            from kivy.core.window import Window
            Window.unbind(on_textinput=self._ime_text, on_key_down=self._ime_key)
        except Exception:
            pass
        self._ime_on = False
        _sdl_stop_text_input()

    # Kivy 内部可能从这几个入口触发，统一转给上面两个实现
    def _bind_keyboard(self):
        if self._android():
            return self._bind_ime()
        return super(RoundInput, self)._bind_keyboard()

    def _unbind_keyboard(self):
        if self._android():
            return self._unbind_ime()
        return super(RoundInput, self)._unbind_keyboard()

    def show_keyboard(self):
        if self._android():
            return self._bind_ime()
        return super(RoundInput, self).show_keyboard()

    def hide_keyboard(self):
        if self._android():
            return self._unbind_ime()
        return super(RoundInput, self).hide_keyboard()

    def _ime_text(self, _win, text):
        if not self._ime_on or not text:
            return
        self.insert_text(text)

    def _ime_key(self, _win, key, _scancode, _codepoint, _mods):
        """按键：SDL 的 IME 走 commitText 给 on_textinput，退格/回车得单独接。"""
        if not self._ime_on:
            return False
        if key == 8:                       # 退格
            self.do_backspace()
            return True
        if key in (13, 271):               # 回车
            if self.multiline:
                self.insert_text("\n")
            else:
                self.dispatch("on_text_validate")
            return True
        if key == 27:                      # ESC：收键盘
            self.focus = False
            return True
        # 可打印字符交给 on_textinput：SDL 对同一个字符既发 key_down 又发
        # textinput，这里再插一次就会变成 "11"。只保留退格/回车/ESC。
        return False

    def _open_native(self):
        title = self.native_title or self.hint_text or "输入内容"
        ok = NATIVE.ask(title, initial=self.text, hint=self.hint_text,
                        ok_text=self.native_ok_text, on_ok=self._apply_native)
        if not ok:                       # 环境不支持就走回老路
            self.focus = True

    def _apply_native(self, txt):
        txt = (txt or "").strip()
        self.text = txt
        cb = self.on_native_ok
        if cb:
            try:
                cb(txt)
            except Exception as e:
                print("[input] 回调失败：%r" % (e,))

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height, self._r)

    def on_touch_down(self, touch):
        in_box = self.collide_point(*touch.pos)
        # 双击输入框 = 弹原生输入框：键盘被系统/输入法搞挂时的兜底，也方便长文本粘贴
        if in_box and touch.is_double_tap and self._android():
            self._open_native()
            return True
        was_focus = self.focus
        handled = super(RoundInput, self).on_touch_down(touch)
        # 已聚焦时再点一次：用户可能用返回键收起了键盘，这里重新唤一次
        if in_box and was_focus:
            self.show_keyboard()
        return handled

    def _on_focus(self, _inst, value):
        self._ln.width = 1.6 if value else 1
        self._lnc.rgba = C_ACCENT if value else C_LINE
        # Kivy 2.3 失焦后前景色会掉成浅灰（看起来像占位符），每次焦点变化刷回主色
        self.foreground_color = C_INK
        self.disabled_foreground_color = C_INK
        if value:
            self._bind_ime()
            # 聚焦全选：点进输入框就该能直接覆盖，否则新输入会追加到旧内容后面
            if self.text:
                Clock.schedule_once(lambda dt: self.select_all(), 0.05)
        else:
            self._unbind_ime()


class PrimaryButton(Button):
    """实心强调色圆角按钮：对应网页 .lk-btn（48 高、圆角 12、按下变深）。"""

    def __init__(self, radius=12, **kw):
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        kw.setdefault("color", (1, 1, 1, 1))
        super(PrimaryButton, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            self._c = Color(*C_BTN)
            self._bg = RoundedRectangle(radius=[dp(radius)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync, state=self._on_state)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _on_state(self, _inst, value):
        self._c.rgba = C_BTN_DK if value == "down" else C_BTN


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
        self.label = lab(text, 11.5, C_ACCENT, bold=True, height=30, halign="center",
                         shorten=True)
        self.add_widget(self.label)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def set_text(self, t):
        self.label.text = t


class PillButton(Button):
    """浅粉胶囊文字按钮：列表行右侧的「填入」。

    原来是裸的红字，没有点击区也没有可点感，手指不好按。
    """

    def __init__(self, text, width=46, height=26, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("size", (dp(width), dp(height)))
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("text", text)
        kw.setdefault("font_name", FONT)
        kw.setdefault("font_size", sp(10.5))
        kw.setdefault("color", C_ACCENT)
        kw.setdefault("bold", True)
        super(PillButton, self).__init__(**kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            self._c = Color(*C_ACCENT_SOFT)
            self._bg = RoundedRectangle(radius=[dp(height / 2.0)], pos=self.pos,
                                        size=self.size)
        self.bind(pos=self._sync, size=self._sync, state=self._on_state)

    def _sync(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _on_state(self, _inst, st):
        self._c.rgba = C_BTN if st == "down" else C_ACCENT_SOFT
        self.color = (1, 1, 1, 1) if st == "down" else C_ACCENT


class KVRow(BoxLayout):
    """键值对行：槽位（固定 56dp 灰字）+ 技能名 + 右侧等级。

    替掉准备位的粉色胶囊：胶囊有底色又装在白卡里是双层容器，宽度还随名字变，
    12 项只露 4 项；改成一列一行后同样高度能放 6 行、完全对齐。
    """

    def __init__(self, key, val, tail="", **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        kw.setdefault("spacing", dp(8))
        super(KVRow, self).__init__(orientation="horizontal", **kw)
        k = lab(str(key), 10.5, C_MUTED, height=40, shorten=True)
        k.size_hint_x = None
        k.width = dp(44)
        self.add_widget(k)
        self.add_widget(lab(str(val), 12.5, C_INK, height=40, shorten=True))
        t = lab(str(tail or ""), 10.5, C_MUTED, height=40, halign="right", shorten=True)
        t.size_hint_x = None
        t.width = dp(64)
        self.add_widget(t)


class Pill(BoxLayout):
    """短标签胶囊：槽位灰小字 + 名称深粗字。只用于准备位/装备这类短键值对。"""

    def __init__(self, key, val, accent=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(38))
        kw.setdefault("spacing", dp(5))
        kw.setdefault("padding", (dp(10), 0, dp(10), 0))
        super(Pill, self).__init__(orientation="horizontal", **kw)
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*(C_ACCENT if accent else C_ACCENT_SOFT))
            self._bg = RoundedRectangle(radius=[dp(19)], pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        k = lab(str(key), 10.5, (1, 1, 1, 1) if accent else C_MUTED, height=38,
                shorten=True)
        k.size_hint_x = None
        k.width = dp(36)
        self.add_widget(k)
        self.add_widget(lab(str(val), 12.5, (1, 1, 1, 1) if accent else C_INK,
                            bold=True, height=38, shorten=True))
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
        self.skill_open_groups = set()   # 展开的武学分组
        self.skill_group_limit = {}      # 分组内已显示条数
        self.mode = "query"
        self._hits = []
        self._sug_ev = None
        self._web = None
        self._cached_uid = None      # 上一次命中的缓存 UID，再查一次就绕过缓存

        root = Root(orientation="vertical", padding=0, spacing=0)
        # 全站统一顶栏：查询页 / 结果页只换内容，不换壳
        self.tone_bar = ToneBar()
        self.appbar = AppBar()
        self.appbar.bind_right(lambda *a: self._open_web())
        self.appbar.bind_back(lambda *a: self.show_query())

        sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12),
                              padding=(dp(16), dp(14), dp(16), dp(18)))
        self.body.bind(minimum_height=self.body.setter("height"))
        self.body.bind(pos=self._body_sync, size=self._body_sync)

        # 顶栏不固定：以前钉在窗口顶部，滚动时印章和正文像两块脱开的贴纸，
        # 内容从下面穿过去。放进 ScrollView 后它就是页面自己的头部，随内容一起走。
        self.inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        self.inner.bind(minimum_height=self.inner.setter("height"))
        self.inner.add_widget(self.tone_bar)     # 先加 = 视觉最上面（vertical 逆序铺）
        self.inner.add_widget(self.appbar)
        self.inner.add_widget(self.body)
        sv.add_widget(self.inner)
        self.sv = sv
        root.add_widget(sv)

        # 结果态固定底栏：主操作不该滚到最底才看得见
        self.foot = BoxLayout(orientation="horizontal", size_hint_y=None, height=0,
                              spacing=dp(8), padding=(dp(16), dp(8), dp(16), dp(10)))
        root.add_widget(self.foot)

        self._build_query_widgets()
        self.show_query()

        # 内嵌浏览器打开时，返回键先关网页，而不是退出 App
        try:
            from kivy.core.window import Window
            Window.bind(on_keyboard=self._on_key)
            Window.bind(on_resize=self._on_resize)
        except Exception:
            pass

        try:
            print("[ui] viewport %.0f x %.0f dp · density %.2f · fontscale %.2f "
                  "· hpad %.0f" % (vp_w(), vp_h(), Metrics.density,
                                   Metrics.fontscale or 1.0, hp()))
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
        self.servers = self._servers()
        names = [n for _k, n in self.servers] + [self.AUTO_LABEL]

        # 表单装进一张卡片。原来 label 和输入框平铺在底色上：白块贴在米底上
        # 几乎看不出边界，label 和内框并排也谈不上分组。
        card = Card(radius=16, pad=14, spacing=12)
        card.bind(minimum_height=card.setter("height"))
        self.form_card = card

        grp = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(5))
        grp.bind(minimum_height=grp.setter("height"))
        grp.add_widget(lab("分区", 12, C_MUTED, height=16))
        self.spin = RoundSpinner(
            text=self._name_of(self._picked_key()) or names[0], values=names,
            font_name=FONT, font_size=sp(15), color=C_INK, halign="left",
            size_hint_y=None, height=dp(46), option_cls=CnSpinnerOption,
        )
        self.spin.bind(width=lambda inst, v: setattr(inst, "text_size", (v - dp(30), None)))
        self.spin.bind(text=lambda inst, v: self._save_pick(v))
        grp.add_widget(self.spin)
        card.add_widget(grp)

        grp2 = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(5))
        grp2.bind(minimum_height=grp2.setter("height"))
        grp2.add_widget(lab("昵称 / UID", 12, C_MUTED, height=16))
        self.inp = RoundInput(
            text="", hint_text="输入昵称或 UID", font_name=FONT, font_size=sp(16),
            multiline=False, input_type="text",
            size_hint_y=None, height=dp(46),
            foreground_color=C_INK, hint_text_color=C_MUTED, cursor_color=C_ACCENT,
            native_title="输入昵称或 UID", native_ok_text="查询",
            on_native_ok=self._after_native_query,
        )
        self.inp.bind(on_text_validate=lambda *a: self.start())
        self.inp.bind(text=self._on_query_text)
        grp2.add_widget(self.inp)

        # 昵称候选提示行：默认折叠，有结果才展开（网页里是下拉列表，这里用弹层）
        self.sug = Button(
            text="", font_name=FONT, font_size=sp(13.5), halign="left", valign="middle",
            size_hint_y=None, height=dp(0), opacity=0,
            background_color=(0, 0, 0, 0), background_normal="", color=C_ACCENT,
        )
        self.sug.bind(width=lambda inst, v: setattr(inst, "text_size", (v - dp(4), None)))
        self.sug.bind(on_release=lambda *a: self._show_candidates())
        grp2.add_widget(self.sug)
        card.add_widget(grp2)

        card.add_widget(gap(8))
        self.btn = PrimaryButton(
            text="查询玩家", font_name=FONT, font_size=sp(16), bold=True,
            size_hint_y=None, height=dp(48),
        )
        self.btn.bind(on_release=lambda *a: self.start())
        card.add_widget(self.btn)

        self.q_status = lab("", 12.5, C_INK2, height=0, shorten=True)
        card.add_widget(self.q_status)

        # 说明收进卡片底部：它属于表单，不该漂在按钮下面自成一行
        card.add_widget(lab("UID 5–12 位数字 · 输入昵称自动切到该角色所在区",
                            11, C_MUTED, height=16, shorten=True))

    def _flash(self, text):
        """在顶栏副标题上短暂提示一句，两秒后恢复成原来的上下文。

        必须带序号：如果这 2.2 秒内用户切了页，`set_content` 已经把副标题换成
        新页面的文案，此时再写回旧值会把「UID xxx」留在查询页顶栏上。
        """
        try:
            keep = self.appbar.sub_lab.text
            self.appbar.sub_lab.text = text
            self._flash_seq = getattr(self, "_flash_seq", 0) + 1
            seq = self._flash_seq

            def _restore(_dt):
                if seq != getattr(self, "_flash_seq", 0):
                    return
                self.appbar.sub_lab.text = keep

            Clock.schedule_once(_restore, 2.2)
        except Exception:
            pass

    def _drop_flash(self):
        """切页时调用：让还没执行的 _flash 恢复动作失效。"""
        self._flash_seq = getattr(self, "_flash_seq", 0) + 1

    def _drop_popup(self):
        """切页时关掉导出弹窗，否则它会盖在新页面上。"""
        p = getattr(self, "_pop", None)
        if p is None:
            return
        self._pop = None
        try:
            p.dismiss()
        except Exception:
            pass

    def _set_foot(self, on):
        """结果态把操作条固定在底部；查询态归零，不占位。

        底栏只放两个动作：「导出」（次要，纯文字）+「再查一个」（主按钮）。
        之前并排三个按钮，360dp 下主按钮被挤成一坨，所以导出收成图标式文字按钮、
        宽度写死 84dp，剩下的全给主按钮。
        """
        self.foot.clear_widgets()
        if not on:
            self.foot.height = 0
            return
        # 左右留白跟内容区一致，按钮边缘和上面卡片的边对齐
        pad = hp()
        self.foot.padding = (dp(pad), dp(8), dp(pad), dp(10))
        self.foot.height = dp(62)

        exp = txt_button("导出", C_ACCENT, width=84, height=46, size=14)
        exp.bind(on_release=lambda *a: self._export_menu())
        self.foot.add_widget(exp)

        again = PrimaryButton(text="再查一个", font_name=FONT, font_size=sp(15),
                              bold=True, size_hint=(1, None), height=dp(46))
        again.shorten = True
        again.bind(on_release=lambda *a: self.again())
        self.foot.add_widget(again)

    # ---------- 导出 / 分享 ----------
    def _export_name(self):
        p = self.prof or {}
        raw = "%s_%s" % (p.get("name") or "player", p.get("uid") or "")
        # 文件名里不能有路径分隔符和 shell 敏感字符
        safe = re.sub(r'[\\/:*?"<>|\s]+', "_", raw).strip("_")
        return (safe or "player") + ".json"

    def _export_text(self):
        p = self.prof or {}
        return json.dumps(p, ensure_ascii=False, indent=2)

    def _export_menu(self):
        """导出方式二选一：写进公共「下载」目录，或走系统分享。"""
        if not self.prof:
            return
        from kivy.uix.popup import Popup

        # 用 Card 自己画白底：Popup 默认背景图在这套 p4a 主题里是半透明的，
        # 深色字压上去几乎看不见。background_color 设全透明后只留 Card。
        box = Card(pad=16, spacing=10, size_hint_y=1)
        box.add_widget(lab("导出「%s」的档案" % (self.prof.get("name") or ""),
                           14, C_INK, bold=True, height=30, shorten=True))
        box.add_widget(lab("完整 JSON，含等级 / 经验 / 武学 / 装备 / 传承",
                           11.5, C_MUTED, height=22, shorten=True))

        save = PrimaryButton(text="保存到「下载」", font_name=FONT, font_size=sp(15),
                             size_hint_y=None, height=dp(46))
        share = PrimaryButton(text="分享文本", font_name=FONT, font_size=sp(15),
                              size_hint_y=None, height=dp(46))
        cancel = txt_button("取消", C_INK2, height=40, size=14)

        pop = Popup(title="", content=box, size_hint=(None, None),
                    size=(dp(304), dp(286)), separator_height=0,
                    title_size=dp(0), background_color=(0, 0, 0, 0),
                    auto_dismiss=True)
        self._pop = pop
        pop.bind(on_dismiss=lambda *a: setattr(self, "_pop", None))
        save.bind(on_release=lambda *a: (pop.dismiss(), self._export_save()))
        share.bind(on_release=lambda *a: (pop.dismiss(), self._export_share()))
        cancel.bind(on_release=lambda *a: pop.dismiss())
        for w in (save, share, cancel):
            box.add_widget(w)
        pop.open()

    def _export_save(self):
        fn, text = self._export_name(), self._export_text()
        try:
            where = save_to_download(fn, text)
            self._flash("已保存到 %s" % where)
        except Exception as e:
            print("[export] 保存失败：%r" % (e,))
            self._flash("保存失败，试试「分享文本」")
            self._export_fail(e)

    def _export_share(self):
        fn, text = self._export_name(), self._export_text()
        try:
            share_text(fn, text)
            self._flash("已打开分享面板")
        except Exception as e:
            print("[export] 分享失败：%r" % (e,))
            self._flash("分享失败：%s" % e)

    def _export_fail(self, e):
        """保存失败时把原因写进状态行，别只闪一句就没了。"""
        try:
            self.set_status("导出失败：%s" % (str(e)[:60] or type(e).__name__), C_ACCENT)
        except Exception:
            pass

    def _result_uid(self):
        p = self.prof or {}
        return p.get("uid") or p.get("userid")

    def _open_web(self, uid=None):
        """打开网页高手榜：带上当前分区，查过人的话顺带高亮他。"""
        # 先放掉输入框焦点，免得 App 输入框和网页输入框抢同一个输入法
        try:
            if getattr(self, "inp", None) is not None and self.inp.focus:
                self.inp.focus = False
        except Exception:
            pass
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
        if self.mode == "result":
            self._flash(msg)

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

    def _scroll_top(self):
        try:
            self.sv.scroll_y = 1
        except Exception:
            pass

    def _apply_metrics(self):
        """按当前视口宽度重排留白。断点是按宽度算的，旋转/分屏后必须重算。"""
        pad = hp()
        self.appbar.padding = (dp(pad), 0, dp(pad), 0)
        if self.mode == "query":
            self.body.padding = (dp(pad), dp(14), dp(pad), dp(18))
        # 结果态是白卡：内边距由 _set_body_card 固定成 14，这里不能改，
        # 否则旋转/分屏后卡片内容会突然贴边（原来就是 14 与 12 来回跳）

    def _on_resize(self, _win, _w, _h):
        Clock.schedule_once(lambda dt: self._relayout(), 0.12)

    def _relayout(self):
        self._apply_metrics()
        if self.mode == "result":
            self._set_foot(True)

    def show_query(self):
        self.mode = "query"
        self.prof = None
        self._hide_inline()
        self._drop_flash()
        self._drop_popup()
        self._set_foot(False)
        # 顶部不放「高手榜」：页面底部已经有入口卡，一个动作不占两个位置
        self.tone_bar.height = 0
        self.appbar.set_content(title="", sub="放置江湖 · 多平台自助查询",
                                right="", back=False, seal=True)
        self.appbar.bind_sub(None)
        self._apply_metrics()
        self.body.spacing = dp(12)
        self._set_body_card(False)
        self.body.clear_widgets()
        self.body.add_widget(self.form_card)
        self.body.add_widget(self._recent_card())
        self.body.add_widget(self._entry_card())
        self.set_status("")
        self._scroll_top()

    def show_result(self, p):
        self.mode = "result"
        self.prof = p
        self._hide_inline()
        self._drop_flash()
        self._drop_popup()
        # 顶栏不再放「修改」：左边的 ‹ 就是回查询页，同一个动作不占两个位置，
        # 少一个按钮也把标题行的空间让给分区名。
        self.tone_bar.height = dp(36)
        self.appbar.set_content(title=p["serverName"],
                                sub="UID %s" % (p.get("uid") or ""),
                                right="", back=True)
        self.appbar.bind_sub(lambda: self.copy_uid())
        self.prep_open = False
        self.skill_open = False
        self.skill_query = ""
        self.skill_open_groups = set()
        self.skill_group_limit = {}
        self._render(p)
        self._set_foot(True)
        self._scroll_top()

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
        self.show_query()

    def _entry_card(self):
        """查询页底部的「高手榜」入口 + UID 说明。

        查询页下半屏原来是纯空白（约 40% 屏高），页面没有任何内容锚点；
        入口卡既补上了这块，也把「高手榜」从顶栏角落挪到了明确的位置。
        """
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        box.bind(minimum_height=box.setter("height"))

        card = Card(radius=16, pad=13, bg=C_ACCENT_SOFT, border=C_ACCENT_SOFT,
                    spacing=0)
        card.bind(minimum_height=card.setter("height"))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42),
                        spacing=dp(8))
        col = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(42),
                        spacing=0)
        col.add_widget(lab("全服高手榜", 13.5, C_ACCENT, bold=True, height=24,
                           shorten=True))
        col.add_widget(lab("全服排名 · 分区与门派筛选 · 经验变化", 10.5, C_MUTED,
                           height=18, shorten=True))
        row.add_widget(col)
        ar = lab("›", 18, C_ACCENT, height=42, halign="right")
        ar.size_hint_x = None
        ar.width = dp(16)
        row.add_widget(ar)
        card.add_widget(row)
        card.bind(on_touch_down=lambda inst, t: self._entry_touch(inst, t))
        box.add_widget(card)
        box.add_widget(self._hint_row())
        return box

    def _entry_touch(self, inst, touch):
        if inst.collide_point(*touch.pos):
            self._open_web()
            return True
        return False

    def _hint_row(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        box.bind(minimum_height=box.setter("height"))
        row = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
        row.add_widget(lab("UID 是游戏内角色 ID，不是登录账号", 10.5, C_MUTED,
                           height=24, shorten=True))
        q = lab("收起" if self.hint_open else "？", 10.5, C_ACCENT, bold=True,
                height=24, halign="right")
        q.size_hint_x = None
        q.width = dp(34)
        row.add_widget(q)
        box.add_widget(row)
        if self.hint_open:
            box.add_widget(lab("默认只查选中的分区，速度快、不易被限流；分区选择会被记住。",
                               10.5, C_MUTED, height=16, shorten=True))
            box.add_widget(lab("不确定在哪个区时，用列表最后的「自动探测」逐区尝试。",
                               10.5, C_MUTED, height=16, shorten=True))
            box.add_widget(lab("当前代码版本：%s · 数据来自游戏接口" % code_version(),
                               10, C_MUTED, height=15))
        box.bind(on_touch_down=lambda inst, t: self._hint_touch(inst, t))
        return box

    def _hint_touch(self, inst, touch):
        if inst.collide_point(*touch.pos):
            self.hint_open = not self.hint_open
            self._show_idle()
            return True
        return False

    def _recent_card(self):
        hist = L.recent_queries()
        has = bool(hist)
        # 历史不足 3 条时用示例补齐：否则查过一两次之后，下半屏又是一片空
        rows = [(r, False) for r in hist[:3]]
        if len(rows) < 3:
            seen = set(str(r.get("uid")) for r, _ in rows)
            for e in self.EXAMPLES:
                if str(e.get("uid")) in seen:
                    continue
                rows.append((e, True))
                seen.add(str(e.get("uid")))
                if len(rows) >= 3:
                    break

        card = Card(radius=16, pad=14, spacing=0)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(lab("最近查询" if has else "试试示例 UID", 13, C_INK,
                            bold=True, height=26, shorten=True))
        card.add_widget(lab("点右侧胶囊把 UID 填进输入框" if not has else "",
                            10.5, C_MUTED, height=17 if not has else 0, shorten=True))
        card.add_widget(gap(2 if has else 6))
        for i, (r, is_ex) in enumerate(rows):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
            nm = r.get("name") or r.get("serverName") or ""
            b = txt_button(("%s  ·  %s" % (r.get("uid"), nm)) if nm else "%s" % r.get("uid"),
                           color=C_INK, height=48, size=13)
            b.halign = "left"
            b.shorten = True
            b.bind(width=lambda inst, v: setattr(inst, "text_size", (v, None)))
            b.bind(on_release=lambda inst, u=r.get("uid"), k=r.get("server"): self._fill(u, k))
            row.add_widget(b)
            pill = PillButton("示例" if is_ex else "填入", width=52 if is_ex else 46)
            pill.bind(on_release=lambda inst, u=r.get("uid"), k=r.get("server"): self._fill(u, k))
            row.add_widget(pill)
            card.add_widget(row)
            if i < len(rows) - 1:
                card.add_widget(HLine())
        return card

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
    def _after_native_query(self, txt):
        """原生输入框点了「查询」：文字已回填，直接发起查询。"""
        if (txt or "").strip():
            self.start()

    def start(self):
        if self.busy:
            return
        raw = (self.inp.text or "").strip()
        if not raw:
            self.set_status("请输入昵称或 UID", C_ACCENT)
            return
        if raw.isdigit():
            uid = int(raw)
            # 同一个 UID 连点两次查询 = 绕过缓存强制刷新。
            # 不额外加刷新按钮：右上角已经被删过两次，用户明确不想在那里放操作。
            force = (getattr(self, "_cached_uid", None) == uid)
            return self._begin(uid, force=force)

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

    def _begin(self, uid, force=False):
        if self._hidden(uid):
            self._deny()
            return
        self.busy = True
        self.btn.disabled = True
        self.btn.text = "查询中…"
        self.set_status("连接中…" if force else "连接中…（10 分钟内查过会直接给结果）",
                        C_ACCENT)
        key = self.key_of(self.spin.text)
        threading.Thread(target=self._worker, args=(uid, key, force),
                         daemon=True).start()

    def _worker(self, uid, server, force=False):
        try:
            prof = L.lookup(uid, server=server, use_cache=not force,
                            progress=lambda m: Clock.schedule_once(
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
        # 缓存命中：告诉用户这是旧结果，并且下次同一 UID 再查会绕过缓存
        if prof.get("_cached"):
            self._cached_uid = prof.get("uid")
            self._flash("10 分钟内的结果 · 再查一次可刷新")
        else:
            self._cached_uid = None
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
        # 以前这里直接 clear_widgets 重建一个「错误卡 + 示例」页，查询表单被一起清掉，
        # 用户看到错误后没有任何输入入口，只能返回键乱试。改成先还原查询页，
        # 再把错误卡插到最上面。
        self.show_query()
        err = Card(radius=16, pad=14, spacing=4)
        err.bind(minimum_height=err.setter("height"))
        err.add_widget(lab(title, 14, C_ACCENT, bold=True, height=24, shorten=True))
        err.add_widget(lab(detail, 12, C_INK2, height=22, shorten=True))
        # Kivy 的 add_widget 默认 index=0（插在 children 头部），而 vertical 布局是
        # 逆序铺的：children 末尾才是视觉第一行。所以置顶要显式插到末尾。
        self.body.add_widget(err, index=len(self.body.children))
        self._scroll_top()

    def _hide_inline(self):
        """切页时收掉盖在上面的原生输入框。"""
        if INLINE is None:
            return
        try:
            INLINE.hide()
        except Exception:
            pass

    def set_status(self, text, color=C_MUTED):
        self.q_status.text = text or ""
        self.q_status.color = color
        self.q_status.height = dp(28) if text else dp(0)

    # ---------- 结果态 ----------
    def _render(self, p):
        """结果页：拆成 6 张卡片。

        原来所有内容塞在一张白卡里，靠 HLine 分隔——一屏能数出十条线，
        反而成了没有分块的表格。卡片边界替代大部分分割线之后，
        线只留在真正的列表内部（准备位、传承），密度立刻降下来。
        """
        self._set_body_card(False)
        self.body.padding = (dp(hp()), dp(12), dp(hp()), dp(14))
        self.body.spacing = dp(12)
        self.body.clear_widgets()

        # ① 身份卡
        idc = Card(radius=16, pad=14, spacing=4)
        idc.bind(minimum_height=idc.setter("height"))
        head = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        head.add_widget(lab(p["name"], 22, C_INK, bold=True, height=36, serif=True,
                            shorten=True))
        # 名次和「进榜」合成一个胶囊：拆成两个右侧元素会上下堆叠，重心全压在右边
        rank_txt = ("第 %s 名 ›" % p["rank"]) if p.get("rank") else "未上榜"
        rank = PillButton(rank_txt, width=84, height=28)
        if p.get("rank"):
            rank.bind(on_release=lambda *a: self._open_web(self._result_uid()))
        head.add_widget(rank)
        idc.add_widget(head)

        meta = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(6))
        parts = [p["menpai"],
                 (p["sex"] + " " if p["sex"] else "") +
                 (str(p["age"]) + " 岁" if p["age"] else "")]
        if p.get("looks") is not None:
            try:
                parts.append("容貌 %s" % format(int(p["looks"]), ",d"))
            except (TypeError, ValueError):
                pass
        meta.add_widget(lab(" · ".join([x for x in parts if x]), 12.5, C_INK2,
                            height=26, shorten=True))
        idc.add_widget(meta)
        self.body.add_widget(idc)

        # ② 数据卡：主指标 19sp，次指标 16sp，中间一条浅线分档
        num = Card(radius=16, pad=14, spacing=8)
        num.bind(minimum_height=num.setter("height"))
        pri = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(12))
        lv_txt = ("%s" % p["lv"] + ("（估）" if p.get("lvEstimated") else "")) if p["lv"] else "—"
        kf_txt = ("%.2f" % p["kongfu"]) if p.get("kongfu") is not None else "—"
        for k, v in (("等级", lv_txt), ("武学造诣", kf_txt)):
            cell = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(54),
                             spacing=0)
            cell.add_widget(lab(k, 10.5, C_MUTED, height=16))
            cell.add_widget(lab(v, 19, C_INK, height=36, bold=True, shorten=True))
            pri.add_widget(cell)
        num.add_widget(pri)
        num.add_widget(HLine())

        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(10), dp(6)))
        vals = [
            ("经验", L.fmt_big(p["exp"])),
            ("福缘", p["fuyuan"] if p.get("fuyuan") is not None else "—"),
            ("气血", L.fmt_big(p.get("qiMax"))),
            ("加力", L.fmt_big(p.get("jiaLi"))),
            ("正气", L.fmt_big(p.get("zhengqi"))),
            ("传承", ("%s 次" % p["inheritCount"]) if p.get("inheritCount") else "—"),
        ]
        for k, v in vals:
            cell = BoxLayout(orientation="vertical", size_hint_y=None,
                             height=dp(44), spacing=0)
            cell.add_widget(lab(k, 10.5, C_MUTED, height=15))
            num_txt, unit = split_num(v)
            markup = num_txt
            if unit:
                markup += "[size=11][color=%s]%s[/color][/size]" % (hex_of(C_INK2), unit)
            cell.add_widget(lab(markup, 15.5, C_INK, height=29, markup=True, shorten=True))
            grid.add_widget(cell)
        grid.height = dp(44) * 3 + dp(6) * 2
        num.add_widget(grid)
        self.body.add_widget(num)

        # ③ 准备位
        prep = list((p["prepared"] or {}).items())
        if prep:
            rows = []
            for k, v in prep:
                info = v if isinstance(v, dict) else {"n": v, "lv": None}
                rows.append((k, info.get("n") or "",
                             ("%s 级" % info["lv"]) if info.get("lv") else ""))
            self.body.add_widget(self._kv_card("准备位 %d 个" % len(prep), rows,
                                               collapsible=True))

        # ④ 装备
        if p["equips"]:
            self.body.add_widget(self._pill_card(
                "装备 %d 件" % len(p["equips"]),
                [(e["slot"], e["n"]) for e in p["equips"]]))

        # ⑤ 传承
        if p["history"]:
            self.body.add_widget(self._timeline_card(p))

        # ⑥ 武学
        self.body.add_widget(self._skill_card(p))

    # ---------- 准备位 ----------
    def _kv_card(self, title, rows, collapsible=False, limit=6):
        card = Card(radius=16, pad=14, spacing=0)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(lab(title, 13, C_INK, bold=True, height=26, shorten=True))
        show = rows if (not collapsible or self.prep_open) else rows[:limit]
        for i, (k, v, tail) in enumerate(show):
            card.add_widget(KVRow(k, v, tail))
            if i < len(show) - 1:
                card.add_widget(HLine())
        if collapsible and len(rows) > limit:
            card.add_widget(gap(2))
            b = txt_button("收起" if self.prep_open else "展开全部 %d 项" % len(rows),
                           color=C_ACCENT, height=34, size=12)
            b.bind(on_release=lambda *a: self._toggle_prep())
            card.add_widget(b)
        return card

    # ---------- 装备 ----------
    def _pill_card(self, title, rows):
        card = Card(radius=16, pad=14, spacing=8)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(lab(title, 13, C_INK, bold=True, height=26, shorten=True))
        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(7), dp(7)))
        for k, v in rows:
            grid.add_widget(Pill(k, v))
        n = (len(rows) + 1) // 2
        grid.height = dp(38) * n + dp(7) * max(0, n - 1)
        card.add_widget(grid)
        return card

    def _toggle_prep(self, *a):
        self.prep_open = not self.prep_open
        if self.prof:
            self._render(self.prof)

    # ---------- 传承 ----------
    def _timeline_card(self, p):
        rows = p["history"] or []
        card = Card(radius=16, pad=14, spacing=0)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(lab("传承历程 · %d 转" % len(rows), 13, C_INK,
                            bold=True, height=26, shorten=True))
        for i, h in enumerate(rows, 1):
            last = i == len(rows)   # 末项就是当前角色
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
            idx = lab(str(i), 10.5, C_ACCENT if last else C_MUTED, height=36,
                      bold=last)
            idx.size_hint_x = None
            idx.width = dp(16)
            row.add_widget(idx)
            row.add_widget(lab(h["n"] or "—", 12.5, C_ACCENT if last else C_INK2,
                               bold=last, height=36, shorten=True))
            dt = lab(fmt_date(h.get("t")), 10.5, C_MUTED, height=36, halign="right")
            dt.size_hint_x = None
            dt.width = dp(48)
            row.add_widget(dt)
            card.add_widget(row)
            # 末项不再画那条贯通整屏的深红线：它像一道分割条，把最后一转切断了
            if not last:
                card.add_widget(HLine())
        return card

    # ---------- 武学：按类型分组折叠 + 常驻搜索 ----------
    def _skill_card(self, p):
        skills = p["skills"] or []
        card = Card(radius=16, pad=14, spacing=8)
        card.bind(minimum_height=card.setter("height"))
        head = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(8))
        head.add_widget(lab("武学 %d 门" % len(skills), 13, C_INK, bold=True,
                            height=26, shorten=True))
        # 一门武学可以有多个可准备位置（太玄经=拳脚+内功+招架），组内会重复出现
        hint = lab("按可准备位置", 10.5, C_MUTED, height=26, halign="right", shorten=True)
        hint.size_hint_x = None
        hint.width = dp(72)
        head.add_widget(hint)
        card.add_widget(head)

        # 搜索框必须自己画底：原来背景全透明，放在白卡上只剩一行漂浮的字，
        # 完全看不出是个输入框。
        self.skill_search = RoundInput(
            text=self.skill_query, hint_text="搜索武学名称", font_name=FONT,
            font_size=sp(12.5), multiline=False, padding=[dp(12), dp(11)],
            size_hint_y=None, height=dp(40), bg=C_SOFT,
            foreground_color=C_INK, hint_text_color=C_INK2, cursor_color=C_ACCENT,
            native_title="搜索武学名称",
        )
        self.skill_search.bind(text=lambda inst, v: self._on_skill_search(v, p))
        card.add_widget(self.skill_search)

        self.skill_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=0)
        self.skill_list.bind(minimum_height=self.skill_list.setter("height"))
        card.add_widget(self.skill_list)
        self._render_skill_list(p)
        return card

    def _skill_row(self, s):
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        row.add_widget(lab(s["n"], 12.5, C_INK2, height=42, shorten=True))
        lv = lab("%s 级" % s["lv"], 10.5, C_MUTED, height=42, halign="right")
        lv.size_hint_x = None
        lv.width = dp(64)
        row.add_widget(lv)
        return row

    def _group_head(self, cat, n):
        opened = cat in self.skill_open_groups
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        a = lab("▼" if opened else "▶", 12, C_MUTED, height=46, halign="center")
        a.size_hint_x = None
        a.width = dp(18)
        row.add_widget(a)
        row.add_widget(lab(cat, 13, C_INK, bold=True, height=46, shorten=True))
        t = lab("%d 门" % n, 10.5, C_MUTED, height=46, halign="right")
        t.size_hint_x = None
        t.width = dp(44)
        row.add_widget(t)
        row.bind(on_touch_down=lambda inst, touch, c=cat: self._group_touch(inst, touch, c))
        return row

    def _group_touch(self, inst, touch, cat):
        if inst.collide_point(*touch.pos):
            if cat in self.skill_open_groups:
                self.skill_open_groups.discard(cat)
            else:
                self.skill_open_groups.add(cat)
            if self.prof:
                self._render_skill_list(self.prof)
            return True
        return False

    def _more_group(self, cat, p):
        self.skill_group_limit[cat] = self.skill_group_limit.get(cat, 8) + 20
        self._render_skill_list(p)

    def _render_skill_list(self, p):
        self.skill_list.clear_widgets()
        q = (self.skill_query or "").strip()
        if q:
            # 搜索时跨组平铺，不分组；上限 200 条防止一次建太多控件
            items = [s for s in (p["skills"] or []) if q in str(s["n"])][:200]
            if not items:
                self.skill_list.add_widget(lab("没有匹配的武学", 12, C_MUTED, height=40))
                return
            self.skill_list.add_widget(lab("匹配 %d 门" % len(items), 10.5, C_MUTED,
                                           height=22, shorten=True))
            for i, s in enumerate(items):
                self.skill_list.add_widget(self._skill_row(s))
                if i < len(items) - 1:
                    self.skill_list.add_widget(HLine())
            return

        groups = SG.group(p["skills"]) if SG else [("全部", p["skills"] or [])]
        for cat, items in groups:
            self.skill_list.add_widget(self._group_head(cat, len(items)))
            if cat in self.skill_open_groups:
                limit = self.skill_group_limit.get(cat, 8)
                show = items[:limit]
                for i, s in enumerate(show):
                    self.skill_list.add_widget(self._skill_row(s))
                    if i < len(show) - 1:
                        self.skill_list.add_widget(HLine())
                if limit < len(items):
                    b = txt_button("显示更多（还剩 %d 门）" % (len(items) - limit),
                                   color=C_ACCENT, height=36, size=11.5)
                    b.bind(on_release=lambda inst, c=cat: self._more_group(c, p))
                    self.skill_list.add_widget(b)
                self.skill_list.add_widget(gap(4))
            # 组标题之间不再画线：15 组就是 15 条，整块看起来像 Excel

    def _on_skill_search(self, v, p):
        self.skill_query = v
        self._render_skill_list(p)

    # ---------- 结果态动作 ----------
    def copy_uid(self):
        uid = str((self.prof or {}).get("uid") or "")
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(uid)
            self._flash("已复制 UID · %s" % uid)
        except Exception:
            self.inp.text = uid
            self.show_query()
            self.set_status("剪贴板不可用，UID 已填回输入框", C_INK2)

    def again(self):
        self.inp.text = ""
        self.show_query()


def _patch_ime_watchdog():
    """关掉 Kivy 的软键盘看门狗。

    真机实测（一加 Ace 6T / Android 17 / 搜狗输入法）：
      mServedView=org.libsdl.app.DummyEdit   mInputShown=true
    说明 SDL 已经把系统键盘拉起来了，但 WindowSDL 每 0.2 秒查一次
    is_keyboard_shown()，安卓上这个返回值靠不住，一为 False 就 release_keyboard，
    刚弹出来的键盘立刻被收走 —— 表现就是「点了没反应 / 闪一下就没了」。

    这里把那次轮询换成永不释放的空实现，键盘由 TextInput 的失焦和返回键负责收起。
    """
    try:
        from kivy.core.window import Window
        cls = type(Window)
        if getattr(cls, "_ime_watchdog_off", False):
            return
        cls._check_keyboard_shown = lambda self, dt: False
        cls._ime_watchdog_off = True
        print("[input] IME watchdog disabled")
    except Exception as e:
        print("[input] watchdog patch failed: %r" % (e,))


def run():
    # 安卓上 Kivy 默认不申请虚拟键盘（启动日志会打印
    _patch_ime_watchdog()
    # keyboard_mode 已在文件顶部（任何 kivy import 之前）设成 system，
    # 这里不要再设一次 —— 此时 Window 早就建好了，设了也不会生效。
    PlayerLookup().run()


if __name__ == "__main__":
    run()

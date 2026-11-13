# -*- coding: utf-8 -*-
"""在 App 内嵌浏览器：用安卓原生 WebView 盖在 Kivy 之上

为什么不用 Kivy 控件：Kivy 没有 HTML 渲染器，排行榜这种表格页面没法用 Label 复原。
为什么不用外部浏览器：用户要求留在 App 里看。

实现要点（踩过的坑都写在这里，改之前先读）：
1. Kivy 的 Python 主线程**不是**安卓 UI 线程，所有 View 的创建 / 修改都必须
   通过 activity.runOnUiThread 投递，否则会抛
   "Only the original thread that created a view hierarchy can touch its views"。
2. WebView 与 SDL 的 SurfaceView 是同一个窗口里的兄弟节点。SurfaceView 的
   surface 默认在窗口**下面**，所以后添加的普通 View 能正常盖住它——但前提是
   容器有不透明背景，否则会看到 Kivy 的画面透出来。
3. WebViewClient / OnClickListener 这些 Java 对象必须由 Python 侧强引用持有，
   否则可能被 GC 回收导致崩溃。
4. 任何一步失败都直接抛异常，交给调用方回退到系统浏览器——宁可用外部浏览器，
   也不能让"点按钮没反应"。
"""

import threading

# 安卓 View 常量（避免额外 autoclass）
_VISIBLE = 0
_GONE = 8
_MATCH = -1
_WRAP = -2
_VERTICAL = 1
_HORIZONTAL = 0


def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _dp(activity, value):
    return int(round(activity.getResources().getDisplayMetrics().density * value))


def available():
    """当前环境能不能用内嵌浏览器（桌面调试时为 False）。"""
    try:
        _activity()
        from jnius import autoclass  # noqa: F401
        return True
    except Exception:
        return False


class WebOverlay(object):
    """惰性创建、复用同一个 WebView，关闭只是隐藏。"""

    def __init__(self):
        self._root = None
        self._web = None
        self._client = None
        self._listener = None
        self._visible = False
        self._last_url = ""

    # ---------------------------------------------------------------- 对外
    def is_open(self):
        return self._visible

    def open(self, url):
        if not url:
            raise ValueError("url 为空")
        if self._root is not None:
            self._show(url)
        else:
            # 首次创建 WebView 时系统要初始化浏览器内核，给足时间（含冷启动约 1 秒）
            self._run_ui(lambda: self._build(url), timeout=6.0)
        self._visible = True
        self._last_url = url

    def close(self):
        """从 Kivy 线程调用（返回键）。点击关闭按钮走 _hide_now，不重复投递。"""
        if self._root is None:
            self._visible = False
            return
        if not self._visible:
            return
        self._run_ui(self._hide_now)

    def _hide_now(self):
        """必须在 UI 线程执行。点击回调本身就在 UI 线程，直接改可见性即可。"""
        try:
            self._root.setVisibility(_GONE)
        except Exception:
            pass
        self._visible = False

    def reload(self):
        if self._web is not None and self._last_url:
            web = self._web
            url = self._last_url
            self._run_ui(lambda: web.loadUrl(url))

    # ---------------------------------------------------------------- 内部
    def _run_ui(self, fn, timeout=3.0):
        """把 fn 投递到安卓 UI 线程执行，并等它跑完；出错就原样抛回。

        必须等：View 创建失败时要能让调用方知道，好回退到系统浏览器。
        阻塞时间按毫秒计（创建几个 View），不会卡住界面。
        """
        from jnius import PythonJavaClass, java_method

        activity = _activity()
        box = {}
        done = threading.Event()

        class _Task(PythonJavaClass):
            __javainterfaces__ = ["java/lang/Runnable"]
            __javacontext__ = "app"

            @java_method("()V")
            def run(self):
                try:
                    fn()
                except Exception as e:      # 不能抛回 Java
                    box["err"] = e
                finally:
                    done.set()

        activity.runOnUiThread(_Task())
        if not done.wait(timeout):
            raise RuntimeError("UI 线程无响应")
        if "err" in box:
            raise box["err"]

    def _build(self, url):
        from jnius import autoclass

        activity = _activity()
        LinearLayout = autoclass("android.widget.LinearLayout")
        LayoutParams = autoclass("android.widget.LinearLayout$LayoutParams")
        ViewGroupLP = autoclass("android.view.ViewGroup$LayoutParams")
        TextView = autoclass("android.widget.TextView")
        Button = autoclass("android.widget.Button")
        WebView = autoclass("android.webkit.WebView")
        WebViewClient = autoclass("android.webkit.WebViewClient")
        Color = autoclass("android.graphics.Color")
        TypedValue = autoclass("android.util.TypedValue")
        Gravity = autoclass("android.view.Gravity")

        root = LinearLayout(activity)
        root.setOrientation(_VERTICAL)
        root.setBackgroundColor(Color.WHITE)

        # ---- 顶栏：标题 + 关闭 ----
        bar = LinearLayout(activity)
        bar.setOrientation(_HORIZONTAL)
        bar.setBackgroundColor(Color.parseColor("#8C2F28"))
        bar.setGravity(Gravity.CENTER_VERTICAL)
        pad = _dp(activity, 12)
        bar.setPadding(pad, _dp(activity, 6), pad // 2, _dp(activity, 6))

        title = TextView(activity)
        title.setText("高手榜")
        title.setTextColor(Color.WHITE)
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16)
        bar.addView(title, LayoutParams(0, _WRAP, 1.0))

        btn = Button(activity)
        btn.setText("关闭")
        btn.setTextColor(Color.WHITE)
        btn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15)
        btn.setBackgroundColor(Color.TRANSPARENT)
        btn.setPadding(_dp(activity, 14), 0, _dp(activity, 14), 0)
        # 注意：回调在 UI 线程执行，只能调 _hide_now，不能再往 UI 线程投递（会死锁）
        self._listener = self._make_click_listener(self._hide_now)
        btn.setOnClickListener(self._listener)
        bar.addView(btn, LayoutParams(_WRAP, _WRAP))

        # ---- WebView ----
        web = WebView(activity)
        settings = web.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setUseWideViewPort(True)
        settings.setLoadWithOverviewMode(True)
        settings.setBuiltInZoomControls(False)
        settings.setDisplayZoomControls(False)
        settings.setSupportZoom(False)
        self._client = WebViewClient()          # 强引用，防 GC
        web.setWebViewClient(self._client)
        web.setBackgroundColor(Color.WHITE)
        web.loadUrl(url)

        root.addView(bar, LayoutParams(_MATCH, _WRAP))
        root.addView(web, LayoutParams(_MATCH, 0, 1.0))

        activity.addContentView(root, ViewGroupLP(_MATCH, _MATCH))
        self._root = root
        self._web = web

    def _show(self, url):
        root = self._root
        web = self._web
        self._run_ui(lambda: root.setVisibility(_VISIBLE))
        if url != self._last_url:
            self._run_ui(lambda: web.loadUrl(url))

    def _make_click_listener(self, fn):
        from jnius import PythonJavaClass, java_method

        class _Click(PythonJavaClass):
            __javainterfaces__ = ["android/view/View$OnClickListener"]
            __javacontext__ = "app"

            @java_method("(Landroid/view/View;)V")
            def onClick(self, _view):
                try:
                    fn()
                except Exception:
                    pass

        return _Click()

# -*- coding: utf-8 -*-
"""在 App 内嵌浏览器：用安卓原生 WebView 盖在 Kivy 之上

为什么不用 Kivy 控件：Kivy 没有 HTML 渲染器，排行榜这种表格页面没法用 Label 复原。
为什么不用外部浏览器：用户要求留在 App 里看。

踩过的坑（改之前先读）：
1. Kivy 的 Python 主线程**不是**安卓 UI 线程，View 的创建 / 修改必须走
   activity.runOnUiThread，否则抛 "Only the original thread ... can touch its views"。
2. 点击「关闭」的回调本身就在 UI 线程，必须调 _hide_now() 直接改可见性；
   再往 UI 线程投递并等待 = 死锁，按钮会完全失效。
3. jnius 对方法签名很挑：setTextSize(int, float) 第二参数要给浮点；
   LinearLayout$LayoutParams(int,int,float) 这类三参构造也容易匹配失败。
   所以这里一律用 ViewGroup.LayoutParams + 显式像素高度，避开权重构造。
4. **pyjnius 1.7 不会把 Python str 自动转成 Java CharSequence**：
   `btn.setText("关闭")` 会抛 `JavaException: No methods called setText ...`，
   导致整个 WebView 创建失败、静默回退系统浏览器（v14 就是这个症状）。
   必须 `autoclass("java.lang.String")("关闭")` 显式构造。
5. 任何一步失败都要留下可读的原因，让界面显示出来，而不是静默跳浏览器。
6. **关闭时只 setVisibility(GONE) 是不够的**：系统输入法里 mServedView 会一直
   指向这个隐藏的 WebView（ThreadedInputConnection），之后软键盘弹出来也只会
   把字送进看不见的网页，Kivy 的 TextInput 一个字符都收不到 —— 用户看到的就是
   「搜索框被禁用了，打不了字」。所以关闭时必须 hideSoftInput + clearFocus，
   并把整个 root 从窗口视图树里 removeView 掉（下次打开重新创建）。
"""

import threading

_VISIBLE = 0
_GONE = 8
_MATCH = -1
_WRAP = -2
_VERTICAL = 1
_HORIZONTAL = 0


def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _metrics(activity):
    m = activity.getResources().getDisplayMetrics()
    return float(m.density), int(m.heightPixels)


def _imm(context):
    """拿到 InputMethodManager。"""
    from jnius import autoclass, cast
    Context = autoclass("android.content.Context")
    InputMethodManager = autoclass("android.view.inputmethod.InputMethodManager")
    return cast("android.view.inputmethod.InputMethodManager",
                context.getSystemService(Context.INPUT_METHOD_SERVICE))


def precheck():
    """返回 (是否可用, 原因)。在真正开网页前先探测，失败原因能直接显示给用户。"""
    try:
        _activity()
        from jnius import autoclass  # noqa: F401
        autoclass("android.webkit.WebView")
        autoclass("android.widget.LinearLayout")
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:120])


class WebOverlay(object):
    """惰性创建、复用同一个 WebView，关闭只是隐藏。"""

    def __init__(self):
        self._root = None
        self._web = None
        self._client = None
        self._listener = None
        self._visible = False
        self._last_url = ""
        self._warn = ""             # 非致命警告（顶栏没做出来等）
        self.last_error = ""        # 致命错误，交给界面显示

    # ---------------------------------------------------------------- 对外
    def is_open(self):
        return self._visible

    def open(self, url):
        if not url:
            raise ValueError("url 为空")
        self.last_error = ""
        try:
            ok, why = precheck()
            if not ok:
                raise RuntimeError("环境不支持：%s" % why)
            if self._root is not None:
                self._show(url)
            else:
                self._run_ui(lambda: self._build(url), timeout=6.0)
            self._visible = True
            self._last_url = url
        except Exception as e:
            self.last_error = "%s: %s" % (type(e).__name__, str(e)[:160])
            raise

    def close(self):
        """从 Kivy 线程调用（返回键）。"""
        if self._root is None:
            self._visible = False
            return
        if not self._visible:
            return
        self._run_ui(self._hide_now)

    def _hide_now(self):
        """必须在 UI 线程执行。点击回调本身就在 UI 线程，直接处理。

        不能只 setVisibility(GONE)：输入法的 mServedView 会一直指向隐藏的
        WebView，之后 Kivy 的输入框就再也收不到字（见文件头第 6 条）。
        这里依次收起键盘、清焦点、把 root 从窗口摘掉，下次打开重新创建。
        """
        web, root = self._web, self._root
        self._visible = False
        try:
            if web is not None:
                _imm(web.getContext()).hideSoftInputFromWindow(
                    web.getWindowToken(), 0)
        except Exception:
            pass
        try:
            if web is not None:
                web.clearFocus()
        except Exception:
            pass
        removed = False
        try:
            if root is not None and root.getParent() is not None:
                # getParent() 的声明类型是 ViewParent，上面没有 removeView，
                # 必须转成 ViewGroup 才能调（否则 pyjnius 抛 No methods called removeView）
                from jnius import cast
                parent = cast("android.view.ViewGroup", root.getParent())
                parent.removeView(root)
                removed = True
        except Exception:
            removed = False
        try:
            if web is not None and not removed:
                web.loadUrl("about:blank")     # 断开网页里的输入连接
        except Exception:
            pass
        if removed:
            # 视图已经摘掉，顺手 destroy 释放 Chromium 资源（每次打开都是新 WebView，
            # 不 destroy 的话连续开关十几次会持续吃内存）
            try:
                if web is not None:
                    web.destroy()
            except Exception:
                pass
            # 下一次 open() 会因为 _root 为 None 而重新建一个 WebView
            self._root = None
            self._web = None
        else:
            # 摘不掉就退化成隐藏，至少别挡着 App 界面
            try:
                if root is not None:
                    root.setVisibility(_GONE)
            except Exception:
                pass

    def reload(self):
        if self._web is not None and self._last_url:
            web, url = self._web, self._last_url
            self._run_ui(lambda: web.loadUrl(url))

    # ---------------------------------------------------------------- 内部
    def _run_ui(self, fn, timeout=6.0):
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
                except Exception as e:
                    box["err"] = e
                finally:
                    done.set()

        try:
            activity.runOnUiThread(_Task())
        except TypeError:
            # 部分 pyjnius 版本需要显式 cast 才能把 Python 代理当 Runnable 传进去
            from jnius import cast
            activity.runOnUiThread(cast("java/lang/Runnable", _Task()))
        if not done.wait(timeout):
            raise RuntimeError("UI 线程 %s 秒内无响应" % timeout)
        if "err" in box:
            raise box["err"]

    def _build(self, url):
        from jnius import autoclass

        activity = _activity()
        LinearLayout = autoclass("android.widget.LinearLayout")
        ViewGroupLP = autoclass("android.view.ViewGroup$LayoutParams")
        WebView = autoclass("android.webkit.WebView")
        WebViewClient = autoclass("android.webkit.WebViewClient")
        Color = autoclass("android.graphics.Color")

        density, screen_h = _metrics(activity)
        bar_h = int(round(density * 50))

        root = LinearLayout(activity)
        root.setOrientation(_VERTICAL)
        try:
            root.setBackgroundColor(Color.WHITE)
        except Exception:
            pass

        # ---- WebView（核心，失败就必须整体回退） ----
        web = WebView(activity)
        try:
            st = web.getSettings()
            st.setJavaScriptEnabled(True)
            st.setDomStorageEnabled(True)
            st.setUseWideViewPort(True)
            st.setLoadWithOverviewMode(True)
        except Exception as e:
            self._warn = "设置项跳过 %s" % type(e).__name__
        self._client = WebViewClient()        # 强引用，防 GC
        web.setWebViewClient(self._client)
        try:
            web.setBackgroundColor(Color.WHITE)
        except Exception:
            pass
        web.loadUrl(url)

        # ---- 顶栏（装饰，失败也不影响网页显示） ----
        made_bar = False
        try:
            bar = self._make_bar(activity, bar_h)
            root.addView(bar, ViewGroupLP(_MATCH, bar_h))
            made_bar = True
        except Exception as e:
            self._warn = "顶栏失败 %s: %s" % (type(e).__name__, str(e)[:80])

        # 不用权重：给 WebView 显式像素高度，避免 jnius 匹配三参构造失败
        web_h = max(200, screen_h - (bar_h if made_bar else 0))
        root.addView(web, ViewGroupLP(_MATCH, web_h))
        activity.addContentView(root, ViewGroupLP(_MATCH, _MATCH))

        self._root = root
        self._web = web

    def _make_bar(self, activity, bar_h):
        """顶栏只放一个关闭按钮——网页本身已有标题，少一个控件少一处失败点。"""
        from jnius import autoclass

        LinearLayout = autoclass("android.widget.LinearLayout")
        ViewGroupLP = autoclass("android.view.ViewGroup$LayoutParams")
        Button = autoclass("android.widget.Button")
        Color = autoclass("android.graphics.Color")
        Gravity = autoclass("android.view.Gravity")

        bar = LinearLayout(activity)
        bar.setOrientation(_HORIZONTAL)
        try:
            bar.setBackgroundColor(Color.parseColor("#8C2F28"))
            bar.setGravity(Gravity.END | Gravity.CENTER_VERTICAL)
        except Exception:
            pass

        btn = Button(activity)
        # pyjnius 1.7 不会把 python str 自动转成 CharSequence，setText 会抛
        # "No methods called setText ... matching your arguments"。
        # 必须显式构造 java.lang.String，这是 v14 内嵌打开失败的真正原因。
        JavaString = autoclass("java.lang.String")
        btn.setText(JavaString("关闭"))
        try:
            btn.setTextColor(Color.WHITE)
            btn.setTextSize(2, 15.0)          # (unit, float)
            btn.setBackgroundColor(Color.TRANSPARENT)
        except Exception:
            pass
        self._listener = self._make_click_listener(self._hide_now)
        btn.setOnClickListener(self._listener)
        bar.addView(btn, ViewGroupLP(_WRAP, bar_h))
        return bar

    def _show(self, url):
        root, web = self._root, self._web
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

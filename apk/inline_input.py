# -*- coding: utf-8 -*-
"""内联输入框：一个盖在 Kivy 输入框位置上的原生 EditText。

为什么不用 SDL 自带的输入目标：
  SDL 用的是 `org.libsdl.app.DummyEdit`，它是个 `View` 子类，`inputType` 写死在
  Java 的 `onCreateInputConnection()` 里，老版本 SDL 给的是
  `TYPE_CLASS_TEXT | TYPE_TEXT_VARIATION_VISIBLE_PASSWORD`（0x91，真机 dumpsys 可验证）。
  对输入法来说这就是密码框，搜狗会切成安全键盘（没有中文）。Python 侧改不了 View 的
  EditorInfo，只能换成自己 new 的 EditText。

  附带好处：EditText 自带系统文本菜单（复制/粘贴/全选），语言跟随系统，
  中文机就是中文，不需要额外改 App locale（改 locale 会触发配置变更把
  Activity 干掉，真机上踩过）。

两条硬约束（都踩过）：
  1. 所有 View 操作必须在 Android 主线程（SDLActivity）执行，Python 跑在 SDLThread，
     直接建 View 会抛 CalledFromWrongThreadException → 统一 runOnUiThread + Event 等待；
  2. 不要每次点击都 addContentView / removeView：反复创建销毁会留下输入法的
     光标放大镜之类残留窗口。这里只建一次，之后用 VISIBLE / GONE 切换。
"""

import threading

_KEEP = {
    "root": None, "edit": None, "params": None, "refs": None,
    "on_text": None, "on_done": None, "visible": False,
}


def _px(v):
    try:
        return int(round(float(v)))
    except Exception:
        return 0


def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def available():
    try:
        from jnius import autoclass
        autoclass("org.kivy.android.PythonActivity")
        return True
    except Exception:
        return False


def showing():
    return bool(_KEEP.get("visible"))


def _run_ui(fn, timeout=6.0):
    """在 Android 主线程执行 fn 并等它结束。"""
    from jnius import autoclass, cast, PythonJavaClass, java_method

    activity = _activity()
    if activity is None:
        raise RuntimeError("no activity")
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

    task = _Task()
    try:
        activity.runOnUiThread(task)
    except TypeError:
        activity.runOnUiThread(cast("java/lang/Runnable", task))
    if not done.wait(timeout):
        raise RuntimeError("UI thread timeout")
    if "err" in box:
        raise box["err"]
    _KEEP["task"] = task


def _ensure(activity):
    """建一次控件（必须在 UI 线程调用）。"""
    if _KEEP.get("edit") is not None:
        return

    from jnius import autoclass, PythonJavaClass, java_method

    FrameLayout = autoclass("android.widget.FrameLayout")
    FrameLayoutLP = autoclass("android.widget.FrameLayout$LayoutParams")
    EditText = autoclass("android.widget.EditText")
    InputType = autoclass("android.text.InputType")
    Gravity = autoclass("android.view.Gravity")
    Color = autoclass("android.graphics.Color")
    GradientDrawable = autoclass("android.graphics.drawable.GradientDrawable")

    density = float(activity.getResources().getDisplayMetrics().density)

    edit = EditText(activity)
    edit.setSingleLine(True)
    edit.setGravity(Gravity.CENTER_VERTICAL)
    edit.setTextSize(2, 17.0)
    edit.setInputType(InputType.TYPE_CLASS_TEXT)      # 普通文本 → 普通拼音键盘
    edit.setPadding(int(14 * density), 0, int(14 * density), 0)
    edit.setTextColor(Color.parseColor("#2A2724"))
    edit.setHintTextColor(Color.parseColor("#8A8578"))
    try:
        edit.setSelectAllOnFocus(True)
    except Exception:
        pass

    bg = GradientDrawable()
    bg.setShape(GradientDrawable.RECTANGLE)
    bg.setColor(Color.WHITE)
    bg.setStroke(int(round(1.6 * density)), Color.parseColor("#8C2F28"))
    bg.setCornerRadius(12 * density)
    edit.setBackground(bg)

    class _Watcher(PythonJavaClass):
        __javainterfaces__ = ["android/text/TextWatcher"]
        __javacontext__ = "app"

        @java_method("(Landroid/text/Editable;)V")
        def afterTextChanged(self, s):
            cb = _KEEP.get("on_text")
            if cb is None:
                return
            try:
                val = str(s.toString()) if s is not None else ""
            except Exception:
                val = ""
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: cb(val), 0)

        @java_method("(Ljava/lang/CharSequence;III)V")
        def onTextChanged(self, s, start, before, count):
            pass

        @java_method("(Ljava/lang/CharSequence;II)V")
        def beforeTextChanged(self, s, start, count, after):
            pass

    class _Action(PythonJavaClass):
        __javainterfaces__ = ["android/widget/TextView$OnEditorActionListener"]
        __javacontext__ = "app"

        @java_method("(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z")
        def onEditorAction(self, _v, _action_id, _event):
            cb = _KEEP.get("on_done")
            if cb:
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: cb(), 0)
            return True

    watcher, action = _Watcher(), _Action()
    edit.addTextChangedListener(watcher)
    edit.setOnEditorActionListener(action)

    root = FrameLayout(activity)
    root.addView(edit, FrameLayoutLP(1, 1))
    params = FrameLayoutLP(1, 1)
    root.setVisibility(8)                      # GONE，先不显示
    activity.addContentView(root, params)

    _KEEP.update({"root": root, "edit": edit, "params": params,
                  "refs": (watcher, action)})


def show(rect, text="", on_text=None, on_done=None):
    """在 rect=(left, top, width, height)（安卓像素，左上角原点）显示输入框。"""
    if not available():
        return False
    _KEEP["on_text"] = on_text
    _KEEP["on_done"] = on_done
    left, top, w, h = (_px(rect[0]), _px(rect[1]), _px(rect[2]), _px(rect[3]))

    def work():
        from jnius import autoclass
        activity = _activity()
        _ensure(activity)
        FrameLayoutLP = autoclass("android.widget.FrameLayout$LayoutParams")
        JavaString = autoclass("java.lang.String")
        Context = autoclass("android.content.Context")

        edit = _KEEP["edit"]
        root = _KEEP["root"]
        outer = _KEEP["params"]

        outer.leftMargin = left
        outer.topMargin = top
        outer.width = max(1, w)
        outer.height = max(1, h)
        root.setLayoutParams(outer)
        edit.setLayoutParams(FrameLayoutLP(max(1, w), max(1, h)))

        edit.setText(JavaString(text or ""))
        n = len(text or "")
        try:
            if n:
                edit.setSelection(0, n)      # 有旧内容就全选，直接打字即覆盖
            else:
                edit.setSelection(0)
        except Exception:
            pass

        root.setVisibility(0)                # VISIBLE
        edit.requestFocus()
        imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
        imm.showSoftInput(edit, 0)
        _KEEP["visible"] = True

    try:
        _run_ui(work)
        return True
    except Exception as e:
        print("[inline] show failed: %r" % (e,))
        return False


def text():
    edit = _KEEP.get("edit")
    if edit is None:
        return ""
    try:
        raw = edit.getText()
        return raw if isinstance(raw, str) else str(raw.toString())
    except Exception:
        return ""


def hide():
    """收起：清焦点 + 隐藏键盘 + 置为 GONE（不销毁，避免输入法残留窗口）。"""
    if _KEEP.get("edit") is None or not _KEEP.get("visible"):
        _KEEP["visible"] = False
        return

    def work():
        from jnius import autoclass
        activity = _activity()
        edit = _KEEP["edit"]
        root = _KEEP["root"]
        # 先断开回写：下面要清空输入框，否则 TextWatcher 会把 "" 写回 Kivy
        _KEEP["on_text"] = None
        try:
            Context = autoclass("android.content.Context")
            imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
            imm.hideSoftInputFromWindow(edit.getWindowToken(), 0)
        except Exception:
            pass
        try:
            # 清掉选中和内容：输入法的选区拖柄（蓝色水滴）是挂在文本选区上的，
            # 只清焦点不清选区，它就会一直留在屏幕上
            edit.setSelection(0)
            edit.setText(autoclass("java.lang.String")(""))
            edit.clearFocus()
        except Exception:
            pass
        try:
            root.setVisibility(8)            # GONE
        except Exception:
            pass
        _KEEP["visible"] = False

    try:
        _run_ui(work, timeout=4.0)
    except Exception as e:
        print("[inline] hide failed: %r" % (e,))
        _KEEP["visible"] = False

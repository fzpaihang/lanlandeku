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
  2. 早期版本只建一次、用 VISIBLE / GONE 切换，但搜狗这类输入法会在收起后
     把选区拖柄（蓝色小水滴）留在屏幕上两三秒。现在收起时直接 removeView，
     让输入法同步销毁会话；代价是每次点开重建一个 EditText（几毫秒）。
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
    # 千万别开 setSelectAllOnFocus：一获得焦点就全选，出现选区就会有拖柄
    # （蓝色小水滴），收起时还得等它淡出。
    try:
        edit.setSelectAllOnFocus(False)
    except Exception:
        pass
    try:
        # IME_FLAG_NO_EXTRACT_UI(0x10000000) | IME_FLAG_NO_FULLSCREEN(0x02000000)
        # 搜狗在「全屏/抽取编辑」模式下会在自己的窗口里画一颗蓝色浮标（光标指示），
        # 关掉这两个模式它就不画了。
        edit.setImeOptions(0x10000000 | 0x02000000)
    except Exception:
        pass

    bg = GradientDrawable()
    bg.setShape(GradientDrawable.RECTANGLE)
    bg.setColor(Color.WHITE)
    bg.setStroke(int(round(1.6 * density)), Color.parseColor("#8C2F28"))
    bg.setCornerRadius(12 * density)
    edit.setBackground(bg)

    class _TouchEater(PythonJavaClass):
        """把落在覆盖框上的触摸吃掉，不让 TextView 自己处理。

        TextView 处理 ACTION_DOWN 时会画一个「插入点手柄」（那颗蓝/绿色小水滴），
        位置就在点击点，而且部分 ROM 不自动收回。我们不需要点击定位光标
        （光标固定在末尾），所以直接吞掉最干净。
        """
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, e):
            try:
                if e.getActionMasked() == 0:
                    v.requestFocus()
            except Exception:
                pass
            return True

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

        # 注意：beforeTextChanged 是 (CharSequence, start, count, after) —— 三个 int。
        # 少写一个会把签名对成 2 个 int，Android 每次调用都抛 NotImplementedError，
        # 输入法的选区/光标状态跟着乱，屏幕上的拖柄就一直挂着不掉。
        @java_method("(Ljava/lang/CharSequence;III)V")
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

    try:
        _KEEP["eater"] = _TouchEater()
        edit.setOnTouchListener(_KEEP["eater"])
    except Exception as e:
        print("[inline] touch eater failed: %r" % (e,))

    _KEEP.update({"root": root, "edit": edit, "params": params,
                  "refs": (watcher, action)})


def show(rect, text="", on_text=None, on_done=None, style=None):
    """在 rect=(left, top, width, height)（安卓像素，左上角原点）显示输入框。

    style 用来让覆盖层长得像它盖住的那个控件：
      {"font_px": 21.9, "bg": "#F2EFE9", "stroke": "#A8482C",
       "hint": "搜索武学名称", "text": "#2A2522"}
    不传就退回白底红框 17sp 的默认样式。
    """
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

        st = style or {}
        try:
            px = float(st.get("font_px") or 17.0)
            # TypedValue: PX=0 / DIP=1 / SP=2。必须是 0——写成 1 会被当成 dp，
            # 再乘一次屏幕密度，字就大了一倍多（真机上字会顶出输入框）。
            edit.setTextSize(0, px)
        except Exception:
            pass
        try:
            hint = st.get("hint") or ""
            edit.setHint(JavaString(hint) if hint else JavaString(""))
        except Exception:
            pass
        try:
            GradientDrawable = autoclass("android.graphics.drawable.GradientDrawable")
            Color = autoclass("android.graphics.Color")
            bg2 = GradientDrawable()
            bg2.setShape(GradientDrawable.RECTANGLE)
            bg2.setColor(Color.parseColor(st.get("bg") or "#FFFFFF"))
            bg2.setStroke(int(round(1.6 * float(activity.getResources()
                                                .getDisplayMetrics().density))),
                          Color.parseColor(st.get("stroke") or "#8C2F28"))
            bg2.setCornerRadius(12 * float(activity.getResources()
                                           .getDisplayMetrics().density))
            edit.setBackground(bg2)
            if st.get("text"):
                edit.setTextColor(Color.parseColor(st["text"]))
        except Exception:
            pass

        edit.setText(JavaString(text or ""))
        n = len(text or "")
        try:
            # 光标放末尾，不要全选：只要有选区，输入法就会画出选择手柄
            # （那颗蓝色小水滴），收起时还要淡出两三秒才消失。想覆盖就直接删。
            edit.setSelection(n)
        except Exception:
            pass

        root.setVisibility(0)                # VISIBLE
        try:
            # 三件事一起做，目标是「系统不画插入点手柄」：
            #  1) 光标不可见；
            #  2) 光标 drawable 置空（部分 ROM 只看 drawable，不看 cursorVisible）；
            #  3) 不让长按进选择模式。
            edit.setCursorVisible(False)
            try:
                edit.setTextCursorDrawable(None)
            except Exception:
                pass
            try:
                edit.setLongClickable(False)
            except Exception:
                pass
        except Exception:
            pass
        try:
            edit.setSelection(0)          # 先放行首，聚焦时搜狗不画浮标
        except Exception:
            pass
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


def move_to(rect):
    """只挪位置（页面重排后用），不重建控件、不走焦点流程。"""
    if _KEEP.get("edit") is None:
        return False
    left, top, w, h = (_px(rect[0]), _px(rect[1]), _px(rect[2]), _px(rect[3]))

    def work():
        from jnius import autoclass
        edit = _KEEP["edit"]
        outer = _KEEP["params"]
        outer.leftMargin = left
        outer.topMargin = top
        outer.width = max(1, w)
        outer.height = max(1, h)
        _KEEP["root"].setLayoutParams(outer)
        FrameLayoutLP = autoclass("android.widget.FrameLayout$LayoutParams")
        edit.setLayoutParams(FrameLayoutLP(max(1, w), max(1, h)))

    try:
        _run_ui(work, timeout=3.0)
        return True
    except Exception as e:
        print("[inline] move failed: %r" % (e,))
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
        Context = autoclass("android.content.Context")
        imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
        try:
            # 关键在于「先清选区并通知输入法，再让控件消失」。
            # 只 order 成 GONE → 清选区的话，输入法那边还留着旧的选区状态，
            # 拖柄（蓝色小水滴）会在屏幕上慢慢淡出两三秒才没。
            edit.setCursorVisible(False)
            # 先把输入类型清成 TYPE_NULL：框架会认为这个控件不再接受输入，
            # 挂在它上面的光标手柄/选择手柄随之销毁（只 removeView 带不走它们）。
            try:
                edit.setInputType(0)
            except Exception:
                pass
            edit.clearFocus()
            edit.setSelection(0)
            edit.setText(autoclass("java.lang.String")(""))
            # 主动把「选区已空」推给输入法，拖柄立即撤掉
            try:
                imm.updateSelection(edit, 0, 0, -1, -1)
            except Exception:
                pass
            imm.hideSoftInputFromWindow(edit.getWindowToken(), 0)
        except Exception:
            pass
        try:
            imm.restartInput(edit)
        except Exception:
            pass
        # 直接把这个 View 从窗口里摘掉：输入法会同步销毁选区拖柄，
        # 而不是慢慢淡出（真机上搜狗那种拖柄能挂两三秒）。
        try:
            from jnius import cast, autoclass
            parent = root.getParent()
            if parent is not None:
                cast("android.view.ViewGroup", parent).removeView(root)
        except Exception as e:
            print("[inline] removeView failed: %r" % (e,))
            try:
                root.setVisibility(8)
            except Exception:
                pass
        # 下次 show() 会重新建一套（重建只要几毫秒）
        _KEEP.update({"root": None, "edit": None, "params": None})

        # 关键：输入法/光标浮标是在它们自己的窗口里画的，收起后如果宿主不重绘，
        # 那一块像素就停在上一帧 —— 屏幕上看起来就是「光标残影一直不走」。
        # 这里强制整棵视图树重绘一次（invalidate + requestLayout）。
        try:
            decor = activity.getWindow().getDecorView()
            decor.invalidate()
            decor.requestLayout()
            root.getParent() and root.getParent().invalidate()
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

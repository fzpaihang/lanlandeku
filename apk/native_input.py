# -*- coding: utf-8 -*-
"""原生输入弹窗：绕开 Kivy 的软键盘链路。

背景（用户真机实测）：点输入框不弹键盘，长按只有「粘贴」，Kivy 一个字符都收不到。
Kivy 的 TextInput 依赖 request_keyboard → SDL_StartTextInput → SDLActivity 的
InputConnection，链条上任何一环被 ROM 掐掉就整条失效；而且这套链路在 MuMu 上
复现不出来（模拟器里输入法窗口高度为 0），改之前只能瞎猜。

这里改成直接弹一个 Android 原生 EditText：输入法、中文、长按粘贴全部交给系统，
Kivy 只负责把结果写回自己的 TextInput。原生控件对 adb 注入同样有效，所以这次
连「能不能打字」都能在模拟器里验。

    import native_input as NI
    NI.ask("输入昵称或 UID", initial=self.text, hint="", on_ok=cb)
"""

_KEEP = []          # 持有 PythonJavaClass / Dialog 引用，防止被 GC 提前回收
_MAX_KEEP = 4


def available():
    """能否用原生弹窗（只在安卓 + jnius 可用时成立）。"""
    try:
        from jnius import autoclass
        autoclass("org.kivy.android.PythonActivity")
        return True
    except Exception:
        return False


def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def _jstr(s):
    """必须显式构造 java.lang.String：pyjnius 不会把 Python str 转 CharSequence。"""
    from jnius import autoclass
    return autoclass("java.lang.String")(s or "")


def _text_of(edit_text):
    """读 EditText 内容。pyjnius 有的版本把 Editable 直接转成 str，
    有的返回 Java 对象（此时才有 toString），两种都要兜住。"""
    try:
        raw = edit_text.getText()
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return str(raw.toString())
    except Exception:
        return str(raw)


def _dispatch(fn, *a):
    """回调统一扔回 Kivy 主线程，避免在 Java UI 线程里碰界面。"""
    if fn is None:
        return
    try:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: fn(*a), 0)
    except Exception:
        try:
            fn(*a)
        except Exception:
            pass


def _keep(*objs):
    _KEEP.append(objs)
    while len(_KEEP) > _MAX_KEEP:
        _KEEP.pop(0)


def ask(title, initial="", hint="", ok_text="确定", on_ok=None, on_cancel=None):
    """弹出原生输入框。True 表示已交给系统，False 表示环境不支持。"""
    if not available():
        return False
    try:
        activity = _activity()
        from jnius import autoclass, cast, PythonJavaClass, java_method
    except Exception:
        return False

    def build():
        try:
            Builder = autoclass("android.app.AlertDialog$Builder")
            EditText = autoclass("android.widget.EditText")
            InputType = autoclass("android.text.InputType")
            Context = autoclass("android.content.Context")
            Gravity = autoclass("android.view.Gravity")

            density = float(activity.getResources().getDisplayMetrics().density)

            et = EditText(activity)
            et.setText(_jstr(initial))
            et.setSingleLine(True)
            et.setTextSize(2, 17.0)
            et.setGravity(Gravity.CENTER_VERTICAL)
            # TYPE_CLASS_TEXT：同时给中文输入法和数字键，别锁成纯数字——昵称要中文
            et.setInputType(InputType.TYPE_CLASS_TEXT)
            try:
                et.setSelectAllOnFocus(True)
            except Exception:
                pass
            pad = int(round(14 * density))
            et.setPadding(pad, int(round(8 * density)), pad, int(round(8 * density)))
            if hint:
                et.setHint(_jstr(hint))

            class _Ok(PythonJavaClass):
                __javainterfaces__ = ["android/content/DialogInterface$OnClickListener"]
                __javacontext__ = "app"

                @java_method("(Landroid/content/DialogInterface;I)V")
                def onClick(self, _dlg, _which):
                    txt = _text_of(et)
                    print("[native_input] ok which=%s txt=%r" % (_which, txt))
                    _dispatch(on_ok, txt)

            class _Cancel(PythonJavaClass):
                __javainterfaces__ = ["android/content/DialogInterface$OnClickListener"]
                __javacontext__ = "app"

                @java_method("(Landroid/content/DialogInterface;I)V")
                def onClick(self, _dlg, _which):
                    _dispatch(on_cancel)

            class _Focus(PythonJavaClass):
                __javainterfaces__ = ["java/lang/Runnable"]
                __javacontext__ = "app"

                @java_method("()V")
                def run(self):
                    # 弹窗出来后主动要一次键盘：部分 ROM 不会自动弹
                    try:
                        et.requestFocus()
                        imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
                        imm.showSoftInput(et, 0)
                    except Exception:
                        pass

            ok_l, cancel_l, focus_l = _Ok(), _Cancel(), _Focus()

            builder = Builder(activity)
            builder.setTitle(_jstr(title))
            builder.setView(et)
            builder.setPositiveButton(
                cast("java/lang/CharSequence", _jstr(ok_text)), ok_l)
            builder.setNegativeButton(
                cast("java/lang/CharSequence", _jstr("取消")), cancel_l)
            dialog = builder.create()
            dialog.setCanceledOnTouchOutside(True)
            dialog.show()
            try:
                activity.runOnUiThread(focus_l)
            except Exception:
                pass
            _keep(dialog, ok_l, cancel_l, focus_l)
        except Exception as e:
            print("[native_input] 弹窗失败：%r" % (e,))

    class _Show(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]
        __javacontext__ = "app"

        @java_method("()V")
        def run(self):
            build()

    show = _Show()
    try:
        activity.runOnUiThread(show)
    except TypeError:
        # 部分 pyjnius 版本不认 Python 代理，必须显式 cast；类名要用 JNI 斜杠写法
        try:
            activity.runOnUiThread(cast("java/lang/Runnable", show))
        except Exception as e:
            print("[native_input] 无法切到 UI 线程：%r" % (e,))
            return False
    except Exception as e:
        print("[native_input] 无法切到 UI 线程：%r" % (e,))
        return False
    _keep(show)
    return True

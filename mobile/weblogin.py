#!/usr/bin/env python3
"""Android WebView 网盘登录模块（pyjnius）。

在 Kivy 界面上叠加原生 WebView 覆盖层，用户在真实网盘页面完成登录
（含验证码/短信/扫码——浏览器引擎渲染，无需逆向任何网盘协议），
登录后从 CookieManager 提取 Cookie 永久保存。

设计要点：
- 所有 Android UI 操作经 runOnUiThread 执行（Kivy 主线程非 UI 线程）
- 桌面 UA 加载（v1.8.1）：移动 UA 会被网盘 302 到"下载客户端"页
- 顶部双按钮：✕ 返回首页（放弃登录）/ ✓ 完成登录（提取 Cookie）；
  返回键/手势走 request_back()（网页后退→关闭登录层）
- 后台线程轮询 CookieManager，特征键命中自动关闭并回调
- 任何一步失败抛 WebLoginError，调用方回退到手动粘贴 Cookie 路径
- 非 Android 环境下 available() 为 False，纯 Python 逻辑可 mock 测试
"""
import os
import threading
import time

try:
    from jnius import autoclass, PythonJavaClass, java_method
    _JNIUS_OK = True
except Exception:  # 非 Android / 无 pyjnius：占位保证类定义可加载
    _JNIUS_OK = False
    PythonJavaClass = object
    autoclass = None

    def java_method(*_a, **_k):
        def deco(fn):
            return fn
        return deco


DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class WebLoginError(Exception):
    pass


def available():
    """仅在 Android（p4a 环境）且 pyjnius 可用时启用。"""
    if not _JNIUS_OK:
        return False
    return ("ANDROID_PRIVATE" in os.environ
            or "ANDROID_ARGUMENT" in os.environ)


def _activity():
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity


class _Runnable(PythonJavaClass):
    __javainterfaces__ = ["java/lang/Runnable"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    @java_method("()V")
    def run(self):
        self._fn()


class _ClickListener(PythonJavaClass):
    __javainterfaces__ = ["android/view/View$OnClickListener"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    @java_method("(Landroid/view/View;)V")
    def onClick(self, view):
        self._fn()


_STATE = {"root": None, "webview": None, "poller": None,
          "on_close": None, "on_cancel": None, "done": False,
          "closed": threading.Event()}


def _run_ui(fn):
    _activity().runOnUiThread(_Runnable(fn))


def _jcolor(argb):
    """ARGB 颜色字面量转 Java int（带符号 32 位）。

    0xFF2563EB 等超出 Java Integer.MAX_VALUE，pyjnius 传参会抛
    OverflowError——v1.7.0 真机"网盘卡片点击无反应"根因之一。
    """
    return argb - 0x100000000 if argb >= 0x80000000 else argb


def _ui_open(url, title, on_manual_done, on_cancel):
    """在 UI 线程挂载覆盖层：[完成登录按钮 + WebView] 全屏。

    分步执行并标记失败步骤（真机诊断）：关键步骤失败抛
    WebLoginError（消息含步骤名）；非关键步骤（配色/Cookie/缩放）
    失败跳过，不阻塞登录层弹出。
    """
    def _step(name, fn, critical=True):
        try:
            return fn()
        except Exception as e:
            if critical:
                raise WebLoginError(
                    f"步骤[{name}]失败: {type(e).__name__}: {e}")
            return None

    LinearLayout = _step("加载LinearLayout类",
                         lambda: autoclass("android.widget.LinearLayout"))
    Button = _step("加载Button类",
                   lambda: autoclass("android.widget.Button"))
    WebView = _step("加载WebView类",
                    lambda: autoclass("android.webkit.WebView"))
    LayoutParams = _step("加载LayoutParams类",
                         lambda: autoclass(
                             "android.view.ViewGroup$LayoutParams"))
    activity = _step("获取Activity", _activity)

    root = _step("构造容器", lambda: LinearLayout(activity))
    _step("容器纵向排列",
          lambda: root.setOrientation(LinearLayout.VERTICAL), critical=False)

    bar = _step("构造按钮栏容器", lambda: LinearLayout(activity))
    _step("按钮栏横向排列",
          lambda: bar.setOrientation(LinearLayout.HORIZONTAL), critical=False)
    LLParams = _step("加载LinearLayout$LayoutParams类",
                     lambda: autoclass(
                         "android.widget.LinearLayout$LayoutParams"))

    btn_back = _step("构造返回首页按钮", lambda: Button(activity))
    _step("返回按钮文字", lambda: btn_back.setText("✕ 返回首页"),
          critical=False)
    _step("返回按钮配色",
          lambda: (btn_back.setBackgroundColor(_jcolor(0xFF475569)),
                   btn_back.setTextColor(_jcolor(0xFFFFFFFF))), critical=False)
    _step("返回按钮绑定点击", lambda: btn_back.setOnClickListener(
        _ClickListener(on_cancel)))
    _step("返回按钮入栏", lambda: bar.addView(
        btn_back, LLParams(0, 160, 1.0)))

    btn_done = _step("构造完成登录按钮", lambda: Button(activity))
    _step("完成按钮文字", lambda: btn_done.setText("✓ 完成登录"),
          critical=False)
    _step("完成按钮配色",
          lambda: (btn_done.setBackgroundColor(_jcolor(0xFF2563EB)),
                   btn_done.setTextColor(_jcolor(0xFFFFFFFF))), critical=False)
    _step("完成按钮绑定点击", lambda: btn_done.setOnClickListener(
        _ClickListener(on_manual_done)))
    _step("完成按钮入栏", lambda: bar.addView(
        btn_done, LLParams(0, 160, 1.0)))

    _step("按钮栏入容器", lambda: root.addView(bar, LayoutParams(-1, 160)))

    wv = _step("构造WebView", lambda: WebView(activity))

    def _cfg():
        settings = wv.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setSupportZoomControls(True)
        # 桌面 UA + 宽视口：Android WebView 默认移动 UA 会被多数网盘
        # 302 到"下载客户端"引导页（v1.8.0 真机"点卡片打开的是下载
        # App 页"根因）；桌面 UA 让服务端返回 PC 版登录页
        settings.setUserAgentString(DESKTOP_UA)
        settings.setUseWideViewPort(True)
        settings.setLoadWithOverviewMode(True)
    _step("WebView基础配置", _cfg, critical=False)

    def _cookie():
        CookieManager = autoclass("android.webkit.CookieManager")
        cm = CookieManager.getInstance()
        cm.setAcceptCookie(True)
        try:
            cm.setAcceptThirdPartyCookies(wv, True)
        except Exception:
            pass
    _step("CookieManager配置", _cookie, critical=False)

    _step("加载登录页", lambda: wv.loadUrl(url))
    _step("WebView入容器", lambda: root.addView(wv, LayoutParams(-1, -1)))
    _step("挂载到窗口", lambda: activity.addContentView(
        root, LayoutParams(-1, -1)))

    _STATE["root"] = root
    _STATE["webview"] = wv
    _STATE["closed"].clear()


def _ui_close():
    """在 UI 线程卸载覆盖层（Android 无 removeContentView，用 removeView）。"""
    root = _STATE["root"]
    if root is None:
        return
    try:
        parent = root.getParent()
        if parent is not None:
            parent.removeView(root)
    finally:
        _STATE["root"] = None
        _STATE["webview"] = None
        _STATE["closed"].set()


def current_cookies(url):
    """取 WebView 里 url 域的 Cookie（含 httpOnly）。失败返回 None。"""
    box = {}

    def grab():
        try:
            CookieManager = autoclass("android.webkit.CookieManager")
            cm = CookieManager.getInstance()
            try:
                cm.flush()
            except Exception:
                pass
            box["cookie"] = cm.getCookie(url)
        except Exception as e:
            box["err"] = str(e)

    try:
        _run_ui(grab)
        for _ in range(50):  # 等 UI 线程回写，最多 2.5s
            if "cookie" in box or "err" in box:
                break
            time.sleep(0.05)
    except Exception as e:
        raise WebLoginError(f"读取 Cookie 失败: {e}")
    if "err" in box:
        raise WebLoginError(f"读取 Cookie 失败: {box['err']}")
    return box.get("cookie")


def open_login(url, auth_keys=(), on_done=None, title="登录",
               on_cancel=None):
    """打开 WebView 登录层。

    url: 登录页地址（桌面 UA 加载，避免移动端跳"下载App"引导页）
    auth_keys: 登录成功特征 Cookie 键（如百度 BDUSS）；命中即自动完成
    on_done(cookie_str, auto: bool): 完成回调（手动按钮或特征命中）
    on_cancel(): 放弃登录回调（✕ 返回首页按钮或返回键触发）
    返回 True 表示已打开；失败抛 WebLoginError（调用方回退手动路径）。
    """
    if not _JNIUS_OK:
        raise WebLoginError("pyjnius 不可用")
    if _STATE["root"] is not None:
        raise WebLoginError("已有登录窗口打开中")

    _STATE["on_cancel"] = on_cancel
    _STATE["done"] = False
    done_once = threading.Event()

    def _finish(auto):
        if done_once.is_set():
            return
        done_once.set()
        _STATE["done"] = True
        _STATE["on_cancel"] = None
        cookie = None
        try:
            cookie = current_cookies(url)
        except Exception:
            pass
        try:
            _run_ui(_ui_close)
        except Exception:
            # post 失败（几乎不可能）：只重置状态；绝不在非 UI 线程
            # 直接操作视图（Android 会抛 CalledFromWrongThread）
            _STATE["root"] = None
            _STATE["webview"] = None
            _STATE["closed"].set()
        poller = _STATE["poller"]
        if poller is not None:
            poller["stop"] = True
            _STATE["poller"] = None
        if on_done is not None:
            try:
                on_done(cookie or "", auto)
            except Exception:
                pass

    def _cancel():
        # ✕ 返回首页按钮：放弃登录（不提取 Cookie，不触发 on_done）
        close_login()

    # UI 层挂载结果必须确认回传：runOnUiThread 是异步 post，异常不会
    # 传播回调用方——v1.7.0 的 fire-and-forget 让挂载失败完全静默，
    # 表象即"点击卡片无反应"。
    opened = {}
    opened_evt = threading.Event()
    aborted = []

    def _safe_open():
        try:
            if aborted:
                return  # 等待期已判超时失败，不再挂载（防幽灵层）
            _ui_open(url, title, lambda: _finish(False),
                     lambda: _cancel())
            if aborted:
                # 极小窗口：挂载完成才发现已被判超时 → 立即撤下
                try:
                    parent = _STATE["root"].getParent()
                    if parent is not None:
                        parent.removeView(_STATE["root"])
                except Exception:
                    pass
                _STATE["root"] = None
                _STATE["webview"] = None
                _STATE["closed"].set()
                return
            opened["ok"] = True
        except Exception as e:
            opened["err"] = f"{type(e).__name__}: {e}"
        finally:
            opened_evt.set()

    try:
        _run_ui(_safe_open)
    except Exception as e:
        raise WebLoginError(f"无法调度UI线程: {e}")
    if not opened_evt.wait(8.0):
        aborted.append(True)
        _STATE["closed"].set()
        raise WebLoginError("UI线程8秒无响应（UI线程可能被阻塞）")
    if not opened.get("ok"):
        _STATE["closed"].set()
        raise WebLoginError(f"登录层挂载失败: {opened.get('err')}")

    def _poll():
        keys = [k.lower() for k in auth_keys]
        while not _STATE["closed"].is_set():
            p = _STATE["poller"]
            if p is None or p.get("stop"):
                return
            if keys:
                try:
                    c = current_cookies(url)
                    if c and all(f"{k}=" in c.lower() for k in keys):
                        _finish(True)
                        return
                except Exception:
                    pass
            time.sleep(1.2)

    t = threading.Thread(target=_poll, daemon=True)
    _STATE["poller"] = {"stop": False}
    t.start()
    return True


def is_open():
    return _STATE["root"] is not None


def close_login():
    """放弃登录、直接关闭登录层（✕ 按钮或返回键触发）。

    不提取 Cookie、不触发 on_done；若 open_login 传入了 on_cancel
    则回调之（调用方用于更新界面状态）。
    """
    if _STATE["root"] is None and _STATE["poller"] is None:
        return
    poller = _STATE["poller"]
    if poller is not None:
        poller["stop"] = True
        _STATE["poller"] = None
    try:
        _run_ui(_ui_close)
    except Exception:
        # post 失败：只重置状态，绝不在非 UI 线程操作视图
        _STATE["root"] = None
        _STATE["webview"] = None
        _STATE["closed"].set()
    cb = _STATE.get("on_cancel")
    _STATE["on_cancel"] = None
    if cb is not None and not _STATE.get("done"):
        try:
            cb()
        except Exception:
            pass


def request_back():
    """Android 返回键/手势语义（登录层打开时）：

    网页有后退历史（如登录页→验证页）则 webView.goBack()；
    无历史则关闭登录层返回 App（等价 ✕ 返回首页）。

    返回 True 表示登录层在前台且已处理；False 表示当前无登录层，
    调用方应继续自己的返回逻辑（如切回首页屏）。
    """
    if _STATE["root"] is None:
        return False
    probe = {}

    def _probe():
        wv = _STATE["webview"]
        try:
            probe["goback"] = bool(wv is not None and wv.canGoBack())
        except Exception:
            probe["goback"] = False

    try:
        _run_ui(_probe)
        for _ in range(30):  # 等 UI 线程回写，最多 1.5s
            if "goback" in probe:
                break
            time.sleep(0.05)
    except Exception:
        pass
    if probe.get("goback"):
        def _back():
            try:
                wv = _STATE["webview"]
                if wv is not None:
                    wv.goBack()
            except Exception:
                pass
        try:
            _run_ui(_back)
        except Exception:
            pass
        return True
    close_login()
    return True

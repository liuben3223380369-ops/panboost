#!/usr/bin/env python3
"""Android WebView 网盘登录模块（pyjnius）。

在 Kivy 界面上叠加原生 WebView 登录层，用户在真实网盘页面完成登录
（含验证码/短信/扫码——浏览器引擎渲染，无需逆向任何网盘协议），
登录后从 CookieManager 提取 Cookie 永久保存。

设计要点：
- 所有 Android UI 操作经 runOnUiThread 执行（Kivy 主线程非 UI 线程）
- v1.8.4 修复真机"蓝灰黑三色弹窗无内容 + 点击闪退"：
  ① 闪退：_ClickListener 此前内联创建未持 Python 强引用——pyjnius
    官方文档明确 proxy 只存指针不持引用，CPython 引用计数归零立即
    GC，Java 侧点击已死 proxy 必 native crash。现所有回调对象强
    引用存 _STATE（click_cbs）
  ② 三色弹窗：Dialog(activity) 用默认 floating 主题，AOSP
    PhoneWindow.generateLayout()（2403-2407 行）会强制
    setLayout(WRAP_CONTENT, WRAP_CONTENT)——窗口 wrap 后 WebView
    高度塌陷成 0，只剩 160px 按钮栏（灰✕+蓝✓）和深色窗口背景
    （黑）。现 show() 后显式 getWindow().setLayout(-1,-1) 全屏
    （show 用 getAttributes() 注册窗口，此后 setLayout 直接改
    注册参数对象立即生效；放在 setContentView 前会被覆盖）
  ③ 加固：WebView 渲染进程崩溃（onRenderProcessGone）不处理时
    系统默认杀整个 App——桥接类转发返回 true，Python 侧记日志
    并自动关层
- v1.8.3 全屏 Dialog 承载（根治"无法返回"）：
  Android 10+ 手势导航的返回手势不产生键盘事件，直接调 Activity
  onBackPressed()——此前 addContentView 覆盖层方案下，SDL trap=1
  会把手势整个吞掉（无反应），trap=0 则退出整个 App，OnKeyListener
  只能收硬件键收不到手势。改 Dialog 后：手势/返回键自动 cancel
  Dialog（系统标准行为），OnCancelListener 接到回调做"网页后退→
  关层"，这是唯一在系统层面可靠的手势返回路径
- v1.8.3 onPageStarted 导航观测（根治"其他网盘仍跳下载App"）：
  shouldOverrideUrlLoading 对服务端 302 重定向无效（官方文档），
  网盘 H5 壳"跳下载App"很多正是 302 落地；onPageStarted 是一切
  导航必经点，在此记录导航日志（真机可取回诊断）并拦截市场类 URL
- v1.8.2 导航守卫：WebViewClient（Java 桥接类 PanWebViewClient）
  拦截一切非 http/https 导航（intent://market:// 等逃逸通道）
- 桌面 UA（v1.8.1）：移动 UA 会被网盘 302 到"下载客户端"页
- 顶部双按钮：✕ 返回首页（放弃登录）/ ✓ 完成登录（提取 Cookie）
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


_STATE = {"root": None, "webview": None, "dialog": None, "poller": None,
          "on_close": None, "on_cancel": None, "done": False,
          "client_cb": None, "key_cb": None, "cancel_cb": None,
          "click_cbs": None,
          "nav_log": [],
          "closed": threading.Event()}


# WebView 导航黑名单（onPageStarted 守卫用）：市场/商店类 URL 直接
# 停止加载——这些是"跳到下载网盘APP界面"的最终落地页
MARKET_PREFIXES = (
    "market://", "https://market.android.com",
    "https://play.google.com/store",
    "https://android.myapp.com", "https://appgallery.huawei.com",
    "https://samsungapps.com", "https://app.mi.com",
    "https://www.coolapk.com",)


def _run_ui(fn):
    _activity().runOnUiThread(_Runnable(fn))


def _jcolor(argb):
    """ARGB 颜色字面量转 Java int（带符号 32 位）。

    0xFF2563EB 等超出 Java Integer.MAX_VALUE，pyjnius 传参会抛
    OverflowError——v1.7.0 真机"网盘卡片点击无反应"根因之一。
    """
    return argb - 0x100000000 if argb >= 0x80000000 else argb


def _decide_url(url, parse_intent=None):
    """WebView 导航策略（纯函数，离线可测）。

    返回 (block, load_url)：
    - http/https → (False, None) 放行 WebView 正常加载
    - intent:// 且提供 parse_intent → 解析出 http(s) 的
      browser_fallback_url 则 (True, fallback)（拦截原跳转、
      在 WebView 内加载 fallback 网页——Chrome 的标准约定）
    - 其余（market:// tmast:// appmarket:// 微信/网盘私有 scheme、
      file:// javascript: about: 空 URL…）→ (True, None) 一律拦截
      ——这正是"跳到下载网盘APP界面"的逃逸通道。

    依据：Android 官方文档——无 WebViewClient 时页面发起的导航交给
    系统 Activity Manager 分发（应用市场/网盘App 接管）。
    """
    if not url:
        return (True, None)
    u = url.strip()
    if u.startswith(("http://", "https://")):
        return (False, None)
    if u.startswith("intent://") and parse_intent is not None:
        try:
            fb = parse_intent(u)
        except Exception:
            fb = None
        if fb and str(fb).startswith(("http://", "https://")):
            return (True, str(fb))
    return (True, None)


def _parse_intent_uri(url):
    """解析 intent:// URI 取 browser_fallback_url（真机路径）。

    安全加固：addCategory(BROWSABLE) + setComponent(None) +
    setSelector(None)，防 intent scheme hijacking（页面定向拉起
    App 私有组件）。
    """
    if not _JNIUS_OK:
        return None
    Intent = autoclass("android.content.Intent")
    i = Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
    i.addCategory(Intent.CATEGORY_BROWSABLE)
    i.setComponent(None)
    i.setSelector(None)
    return i.getStringExtra("browser_fallback_url")


class _UrlLoadingCallback(PythonJavaClass):
    """实现 Java 桥接类 PanWebViewClient$UrlLoadingCallback（接口）。

    pyjnius 基于 java.lang.reflect.Proxy 只能实现接口，WebViewClient
    是抽象类——所以经 Java 桥接类转发（见 java_classes/）。

    v1.8.3 增补 onPageStarted/onPageFinished：
    - onPageStarted 记导航日志（_STATE["nav_log"]，真机诊断用）
      + 市场黑名单拦截（wv.stopLoading）——302 落地不经过
      shouldOverrideUrlLoading，这里是唯一可靠守卫点
    - onPageFinished 落日志（页面加载完成时间线）

    v1.8.4 增补 onRenderGone：WebView 渲染进程崩溃转发——不处理
    时系统默认杀掉整个 App（真机闪退路径之一）。
    """
    __javainterfaces__ = [
        "org/panboost/panwebview/PanWebViewClient$UrlLoadingCallback"]
    __javacontext__ = "app"

    def __init__(self, handle, on_nav=None, on_render_gone=None):
        super().__init__()
        self._handle = handle
        self._on_nav = on_nav
        self._on_render_gone = on_render_gone

    @java_method("(Ljava/lang/String;)Z")
    def onUrlLoading(self, url):
        return bool(self._handle(url))

    @java_method("(Ljava/lang/String;)V")
    def onPageStarted(self, url):
        if self._on_nav is not None:
            try:
                self._on_nav(url, started=True)
            except Exception:
                pass

    @java_method("(Ljava/lang/String;)V")
    def onPageFinished(self, url):
        if self._on_nav is not None:
            try:
                self._on_nav(url, started=False)
            except Exception:
                pass

    @java_method("()V")
    def onRenderGone(self):
        if self._on_render_gone is not None:
            try:
                self._on_render_gone()
            except Exception:
                pass


class _CancelListener(PythonJavaClass):
    """Dialog 取消监听（v1.8.3 手势返回的核心）。

    Android 10+ 手势导航的返回手势直接 cancel Dialog（系统标准
    行为，不产生键盘事件）——OnCancelListener 是接口，pyjnius 可
    直接实现。硬件返回键同样走 Dialog.cancel()。
    """
    __javainterfaces__ = ["android/content/DialogInterface$OnCancelListener"]
    __javacontext__ = "app"

    def __init__(self, on_cancel):
        super().__init__()
        self._on_cancel = on_cancel

    @java_method("(Landroid/content/DialogInterface;)V")
    def onCancel(self, dialog):
        try:
            self._on_cancel()
        except Exception:
            pass


class _BackKeyListener(PythonJavaClass):
    """WebView 层返回键拦截（View$OnKeyListener 是接口，可直接实现）。

    WebView 抢到焦点后 KEYCODE_BACK 默认被 WebView 消费（goBack），
    不会经过 SDL surface——Kivy 层拦不到，必须在 WebView 层挂监听。
    """
    __javainterfaces__ = ["android/view/View$OnKeyListener"]

    def __init__(self, on_back):
        super().__init__()
        self._on_back = on_back

    @java_method("(Landroid/view/View;ILandroid/view/KeyEvent;)Z")
    def onKey(self, view, key_code, event):
        # KEYCODE_BACK=4；ACTION_UP=1 时处理（DOWN+UP 只触发一次）。
        # onKey 在 UI 线程回调——on_back 内部必须同步操作 WebView，
        # 绝不能 _run_ui 同步等待（死锁）
        if key_code == 4 and event.getAction() == 1:
            try:
                self._on_back()
            except Exception:
                pass
            return True  # 消费：阻止 WebView goBack / 系统默认退出
        return False


def _ui_open(url, title, on_manual_done, on_cancel, on_key_back):
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
    # v1.8.4：点击回调必须存 Python 强引用——pyjnius 官方文档明确
    # proxy 只存指针不持引用，内联创建引用计数归零立即被 GC，
    # Java 侧点击已死 proxy 直接 native crash（真机"点击就闪退"根因）
    click_back = _step("构造返回按钮点击回调",
                       lambda: _ClickListener(on_cancel))
    _step("返回按钮绑定点击", lambda: btn_back.setOnClickListener(click_back))
    _step("返回按钮入栏", lambda: bar.addView(
        btn_back, LLParams(0, 160, 1.0)))

    btn_done = _step("构造完成登录按钮", lambda: Button(activity))
    _step("完成按钮文字", lambda: btn_done.setText("✓ 完成登录"),
          critical=False)
    _step("完成按钮配色",
          lambda: (btn_done.setBackgroundColor(_jcolor(0xFF2563EB)),
                   btn_done.setTextColor(_jcolor(0xFFFFFFFF))), critical=False)
    click_done = _step("构造完成按钮点击回调",
                       lambda: _ClickListener(on_manual_done))
    _step("完成按钮绑定点击", lambda: btn_done.setOnClickListener(click_done))
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
        # v1.8.4：网页加载前 WebView 默认黑底（真机深色窗口背景下
        # 观感即"黑色空白"），设白底更接近网页观感
        wv.setBackgroundColor(_jcolor(0xFFFFFFFF))
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

    # v1.8.2 导航守卫：必须设置 WebViewClient（否则页面 location.href
    # / intent:// / market:// 导航全部逃逸到系统 intent 分发——真机
    # "跳到下载网盘APP界面"根因）。回调对象强引用存 _STATE 防 GC
    # （pyjnius 文档：proxy 被 Python GC 后 Java 回调崩溃）
    def _handle_url(u):
        block, load = _decide_url(u, _parse_intent_uri)
        if load:
            try:
                wv.loadUrl(load)
            except Exception:
                pass
        return block

    # v1.8.3 onPageStarted 导航观测（WebViewClient 回调在 UI 线程，
    # 可同步操作 WebView）：
    # - 记导航日志（真机诊断"到底跳去了哪"，最多留 50 条）
    # - 市场黑名单拦截：302 落地不经过 shouldOverrideUrlLoading，
    #   onPageStarted 是唯一可靠守卫点；命中即停载并记原因
    def _on_nav(u, started):
        log = _STATE["nav_log"]
        log.append(("start" if started else "done", time.strftime("%H:%M:%S"),
                    u[:180]))
        del log[:-50]
        if started and u.lower().startswith(MARKET_PREFIXES):
            log.append(("block", time.strftime("%H:%M:%S"),
                        "市场URL已拦截: " + u[:150]))
            try:
                wv.stopLoading()
            except Exception:
                pass

    # v1.8.4 渲染进程崩溃处理：onRenderProcessGone 不处理时系统
    # 默认杀掉整个 App（真机闪退路径之一）。记日志并自动关层
    # （onRenderGone 在 UI 线程回调，runOnUiThread 在 UI 线程调用
    # 时立即同步执行，dismiss 后 WebView 随层销毁）
    def _on_render_gone():
        log = _STATE["nav_log"]
        log.append(("crash", time.strftime("%H:%M:%S"),
                    "WebView渲染进程崩溃，已自动关闭登录层"))
        del log[:-50]
        try:
            close_login()
        except Exception:
            pass

    client_cb = _step("构造导航回调",
                      lambda: _UrlLoadingCallback(_handle_url, _on_nav,
                                                  _on_render_gone))
    PanWebViewClient = _step(
        "加载PanWebViewClient类",
        lambda: autoclass("org.panboost.panwebview.PanWebViewClient"))
    client = _step("构造WebViewClient",
                   lambda: PanWebViewClient(client_cb))
    _step("设置WebViewClient", lambda: wv.setWebViewClient(client))

    # v1.8.2 返回键：WebView 抢焦点后自己消费 KEYCODE_BACK，必须在
    # View 层挂 OnKeyListener 拦截（硬件返回键兜底；手势返回走
    # Dialog 的 OnCancelListener，见下）
    key_cb = _step("构造返回键监听", lambda: _BackKeyListener(on_key_back))
    _step("WebView可获焦点",
          lambda: (wv.setFocusable(True),
                   wv.setFocusableInTouchMode(True)), critical=False)
    _step("挂载返回键监听", lambda: wv.setOnKeyListener(key_cb))

    _step("加载登录页", lambda: wv.loadUrl(url))
    _step("WebView入容器", lambda: root.addView(wv, LayoutParams(-1, -1)))

    # v1.8.3 全屏 Dialog 承载（根治"无法返回"）：
    # Android 10+ 手势返回直接 cancel Dialog（系统标准行为），不再
    # 依赖键盘事件（此前 addContentView 覆盖层方案下手势被 SDL
    # trap 吞掉或退出整个 App，OnKeyListener 也收不到手势）。
    # OnCancelListener 是接口，pyjnius 可直接实现（_CancelListener）。
    Dialog = _step("加载Dialog类", lambda: autoclass("android.app.Dialog"))
    dialog = _step("构造Dialog", lambda: Dialog(activity))
    cancel_cb = _step("构造取消监听", lambda: _CancelListener(on_cancel))
    _step("Dialog可取消", lambda: dialog.setCancelable(True))
    _step("挂载取消监听", lambda: dialog.setOnCancelListener(cancel_cb))
    _step("Dialog装载内容", lambda: dialog.setContentView(root))
    _step("显示Dialog", lambda: dialog.show())
    # v1.8.4 关键修复：floating 主题的 Dialog 在 setContentView 时
    # 被 PhoneWindow.generateLayout() 强制 setLayout(WRAP_CONTENT,
    # WRAP_CONTENT)（AOSP 源码实锤）——窗口 wrap 后 WebView 高度
    # 塌陷成 0，真机表象即"蓝灰黑三色弹窗、网页什么都没有"。
    # show() 后显式全屏：show 用 getAttributes() 注册窗口，此后
    # setLayout 直接改注册参数对象，立即生效
    _step("Dialog全屏", lambda: dialog.getWindow().setLayout(-1, -1),
          critical=False)

    _STATE["root"] = root
    _STATE["webview"] = wv
    _STATE["dialog"] = dialog
    _STATE["client_cb"] = client_cb
    _STATE["key_cb"] = key_cb
    _STATE["cancel_cb"] = cancel_cb
    _STATE["click_cbs"] = (click_back, click_done)
    _STATE["closed"].clear()


def _ui_close():
    """在 UI 线程关闭登录层（v1.8.3 Dialog.dismiss 为主，removeView 兜底）。

    dismiss 关闭整个 Dialog 窗口（contentView 随之卸下）；失败时回退
    v1.8.2 的 removeView（防幽灵层）。必须清空全部强引用字段——
    dialog/webview/client 回调被 Python GC 后 Java 侧回调会崩溃。
    """
    dialog = _STATE["dialog"]
    root = _STATE["root"]
    if dialog is None and root is None:
        return
    try:
        if dialog is not None:
            dialog.dismiss()
        elif root is not None:
            parent = root.getParent()
            if parent is not None:
                parent.removeView(root)
    except Exception:
        try:
            if root is not None:
                parent = root.getParent()
                if parent is not None:
                    parent.removeView(root)
        except Exception:
            pass
    finally:
        _STATE["root"] = None
        _STATE["webview"] = None
        _STATE["dialog"] = None
        _STATE["client_cb"] = None
        _STATE["key_cb"] = None
        _STATE["cancel_cb"] = None
        _STATE["click_cbs"] = None
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
            _STATE["dialog"] = None
            _STATE["cancel_cb"] = None
            _STATE["click_cbs"] = None
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

    def _key_back():
        # WebView 层返回键/手势（onKey 在 UI 线程回调，必须同步操作，
        # 不能 _run_ui 同步等待——probe 会排到 onKey 之后造成死等）：
        # 网页可后退先 goBack，否则关闭登录层。close_login 内部的
        # _run_ui 是异步 post（onKey 返回后执行），安全。
        wv = _STATE["webview"]
        try:
            if wv is not None and wv.canGoBack():
                wv.goBack()
                return
        except Exception:
            pass
        _cancel()

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
                     lambda: _cancel(), _key_back)
            if aborted:
                # 极小窗口：挂载完成才发现已被判超时 → 立即撤下
                # （_ui_close 关 Dialog 为主，本函数已在 UI 线程，
                # 同步调用安全）
                _ui_close()
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


def nav_log():
    """导航日志快照（v1.8.3 真机诊断"到底跳去了哪"）。

    返回 [("start"|"done"|"block", "HH:MM:SS", url), ...] 最近 50 条；
    登录层关闭后不清空，调用方可随时取走落盘。
    """
    return list(_STATE["nav_log"])


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
        _STATE["dialog"] = None
        _STATE["cancel_cb"] = None
        _STATE["click_cbs"] = None
        _STATE["closed"].set()
    cb = _STATE.get("on_cancel")
    _STATE["on_cancel"] = None
    if cb is not None and not _STATE.get("done"):
        try:
            cb()
        except Exception:
            pass


def request_back():
    """Kivy 层键盘返回键兜底（登录层打开时）。

    v1.8.3 起 Android 10+ 手势导航与硬件返回键均由 Dialog 系统级
    处理（自动 cancel → OnCancelListener），不经过本函数；仅当
    返回键事件仍漏到 Kivy 层时由此兜底：
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

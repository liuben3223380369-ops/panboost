#!/usr/bin/env python3
"""Android WebView 网盘登录模块（pyjnius）。

在 Kivy 界面上叠加原生 WebView 登录层，用户在真实网盘页面完成登录
（含验证码/短信/扫码——浏览器引擎渲染，无需逆向任何网盘协议），
登录后从 CookieManager 提取 Cookie 永久保存。

设计要点：
- 所有 Android UI 操作经 runOnUiThread 执行（Kivy 主线程非 UI 线程）
- v1.9.0 登录层 UI 重构 + 网页版 URL 实锤（真机反馈第六轮）：
  ① "顶部三个色块没有文字"：✕/✓ 双按钮的 setText/setTextColor
    与整块 WebView 配置一样走 critical=False——pyjnius 对 setText
    多重载（int/CharSequence/char[]）解析在部分真机失败，失败被
    静默吞掉，用户只看到两个色块不知是什么。重构为标准登录页
    布局：深色标题栏（✕ + "网盘名 · 网页登录"）+ 黄色提示条 +
    WebView + 底部通栏"已完成登录"大按钮（蓝底白字 17sp）；
    文字三级保险 _set_text（str 直传 → java.lang.String 对象 →
    失败记 nav_log），颜色 _set_text_color 双保险（int 直传 →
    Color.rgb 回退）
  ② "夸克/阿里云盘打开是下载页"：登录 URL 落在产品宣传页——
    LinkSwift v1.1.4 @match 清单实锤网页版真实路径：阿里
    www.alipan.com/drive/、天翼 cloud.189.cn/web/、移动云盘
    yun.139.com（pans.py 修正，移动 domains 补 139.com）；
    桌面 UA 原与整块 _cfg 一起被吞——配置拆分独立 step +
    getUserAgentString 读回验证记 nav_log（真机可诊断）
  ③ "UC 不能打开"：drive.uc.cn 域名经 LinkSwift @match 与 AList
    驱动文档双源确认无误，问题同②（UA/拦截链路），随②根治
- v1.8.5 修复"点击卡片即被误记已登录 + 部分网盘三色区域无内容"：
  ① 误记已登录：✓ 完成登录此前只看"Cookie 非空"——登录页游客
    Cookie（BAIDUID 等）也非空，一点就记账（真机反馈实锤）。
    参考网盘解析项目（LinkSwift / netdisk-fast-download）的登录态
    判定思路：特征凭证命中才算登录。现在 _finish 在关层前校验
    auth_keys 全部命中，未命中 Toast 提示且保持登录层打开
  ② 三色区域：v1.8.4 的 show() 后 setLayout(-1,-1) 在真机上仍被
    floating 主题的强制 wrap 压回（generateLayout 时机）——改用
    非 floating 全屏主题构造 Dialog（Theme_Light_NoActionBar_
    Fullscreen，API 1+），窗口天生 MATCH_PARENT，不依赖任何时机
  ③ 空白屏兜底：登录 URL 302 到 app scheme/市场页被拦截后
    WebView 停在空白——拦截后回退重载登录页（2 次），仍被拦则
    显示说明页（避免"什么都没有"的黑/白屏）
  ④ WebView 先入容器后加载（未 attach 就 loadUrl 在部分 ROM 上
    不渲染）；高度改 weight=1（LinearLayout 标准剩余空间分配）
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

# v1.9.0 登录层配色（集中管理，全部经 _jcolor 转 Java int）
C_BAR_BG = 0xFF0F172A    # 标题栏：深石板蓝黑
C_TIP_BG = 0xFFFEF3C7    # 提示条：浅黄
C_TIP_FG = 0xFF92400E    # 提示条文字：深棕（浅黄底高对比）
C_DONE_BG = 0xFF2563EB   # 完成按钮：主题蓝
C_WHITE = 0xFFFFFFFF     # 白字（标题栏/按钮）
C_ERR = 0xFFDC2626       # 校验失败提示：红（v1.9.2）
DONE_BTN_TEXT = "✓  已完成登录，保存 Cookie"
# v2.1.0 浏览模式（已登录直入我的网盘）
BROWSE_BTN_TEXT = "✓  已复制链接，去下载"
BROWSE_TIP_TEXT = "在你的网盘中浏览文件，复制文件/分享链接后点底部按钮"


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
          "click_cbs": None, "btn_done": None,
          "retired": [],
          "nav_log": [],
          "session": 0,
          "closed": threading.Event()}


# WebView 导航黑名单（onPageStarted 守卫用）：市场/商店类 URL 直接
# 停止加载——这些是"跳到下载网盘APP界面"的最终落地页
MARKET_PREFIXES = (
    "market://", "https://market.android.com",
    "https://play.google.com/store",
    "https://android.myapp.com", "https://appgallery.huawei.com",
    "https://samsungapps.com", "https://app.mi.com",
    "https://www.coolapk.com",)

# v1.8.5 拦截说明页：scheme/市场跳转被拦 2 次后显示（替代空白屏）
_BLOCKED_HTML = (
    "<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
    "content=\"width=device-width,initial-scale=1\"></head>"
    "<body style=\"font-family:sans-serif;padding:24px;background:#fff;"
    "color:#334155\"><h2>已阻止跳转到网盘客户端</h2>"
    "<p>该网盘页面试图打开 App 或应用市场，PanBoost 已在网页内拦截。</p>"
    "<p>若登录页无法正常显示：请点左上角 ✕ 返回，到「账号」页选择该"
    "网盘对应域名，在浏览器登录后粘贴 Cookie 保存即可。</p></body></html>")


def _run_ui(fn):
    _activity().runOnUiThread(_Runnable(fn))


def _toast(msg):
    """UI 线程弹 Android Toast（v1.8.5 登录凭证校验提示）。

    runOnUiThread 在 UI 线程调用时立即同步执行（AOSP 文档），
    按钮 onClick 与 poller 线程两处调用都安全；任何失败静默
    （Toast 不可用不应阻塞登录流程）。
    """
    def _show():
        try:
            Toast = autoclass("android.widget.Toast")
            Toast.makeText(_activity(), _jstr(msg), 0).show()
        except Exception:
            pass
    try:
        _run_ui(_show)
    except Exception:
        pass


def _jcolor(argb):
    """ARGB 颜色字面量转 Java int（带符号 32 位）。

    0xFF2563EB 等超出 Java Integer.MAX_VALUE，pyjnius 传参会抛
    OverflowError——v1.7.0 真机"网盘卡片点击无反应"根因之一。
    """
    return argb - 0x100000000 if argb >= 0x80000000 else argb


def _set_text(view, text):
    """TextView 文字三级保险（v1.9.0 真机"按钮无字色块"根因修复）。

    pyjnius 方法解析对 setText 多重载（int/CharSequence/char[]）
    在部分真机 ROM 匹配失败，且 _step(critical=False) 会把失败
    静默吞掉——真机表象即"顶部色块没有文字"。三级尝试：
    ① str 直传（绝大多数环境 OK）
    ② java.lang.String 对象（Java 侧类型精确，绕过重载解析）
    ③ 返回 False，调用方记 nav_log（真机可诊断）
    """
    try:
        view.setText(text)
        return True
    except Exception:
        pass
    try:
        view.setText(autoclass("java.lang.String")(text))
        return True
    except Exception:
        pass
    return False


def _set_text_color(view, argb):
    """文字颜色双保险：int 直传失败时用 Color.rgb(r,g,b)（返回
    Java int 值，同类型回传，无 Python int ↔ Java int 溢出转换）。

    argb 为 0xFFrrggbb 字面量（_jcolor 只在直传分支内转换）。
    """
    try:
        view.setTextColor(_jcolor(argb))
        return True
    except Exception:
        pass
    try:
        r, g, b = (argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF
        Color = autoclass("android.graphics.Color")
        view.setTextColor(Color.rgb(r, g, b))
        return True
    except Exception:
        return False


def _jstr(s):
    """Python str 转 java.lang.String 对象（v1.9.2）。

    Toast.makeText 等多重载方法（int/CharSequence）在部分真机
    ROM 上 pyjnius 解析失败——与 setText 同款问题（v1.9.0 实锤）。
    失败时返回原样 str（调用方 try/except 兜底）。
    """
    try:
        return autoclass("java.lang.String")(s)
    except Exception:
        return s


def _merge_cookies(*parts):
    """合并多域 Cookie 字符串（v1.9.2 多域探测）。

    网盘登录跳转常把 Cookie 种在关联域（如百度在
    passport.baidu.com 登录、pan.baidu.com 使用）——只查登录页
    URL 会漏。分号拆键值合并，后出现的键覆盖先前值。
    返回合并串；全空返回 None。
    """
    out = {}
    for part in parts:
        if not part:
            continue
        for kv in part.split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                out[k.strip()] = v
    return "; ".join(f"{k}={v}" for k, v in out.items()) if out else None


def _gather_cookies(urls):
    """遍历 urls 逐域取 Cookie 并合并（v1.9.2）。

    返回 (cookie, err)：任一域取到即有 cookie；err 为最后一次
    异常文本（诊断用）。单域失败不中断其余域。
    """
    cookie = None
    err = None
    for u in urls:
        try:
            c = current_cookies(u)
        except Exception as e:
            err = f"{u}: {e}"
            continue
        if c:
            cookie = _merge_cookies(cookie, c)
    return cookie, err


def _nudge_button():
    """校验失败时把"保存"按钮文字改为红色提示 3 秒（v1.9.2）。

    真机 v1.9.1 反馈"点保存没反应"：凭证校验未通过时仅弹
    Toast——该通道在部分真机 ROM 上静默失败，用户看不到任何
    变化。按钮文字是 v1.9.0 真机验证过的三级保险通道（可靠），
    直接在按钮上反馈"未检测到凭证"，3 秒后恢复原文与白字。
    """
    btn = _STATE.get("btn_done")
    if btn is None:
        return
    _STATE["nudge_seq"] = _STATE.get("nudge_seq", 0) + 1
    seq = _STATE["nudge_seq"]

    def _apply():
        if _set_text(btn, "✗ 未检测到登录凭证，完成登录后再点"):
            _set_text_color(btn, C_ERR)

    def _restore():
        if seq != _STATE.get("nudge_seq") or _STATE.get("done"):
            return
        _set_text(btn, DONE_BTN_TEXT)
        _set_text_color(btn, C_WHITE)

    try:
        _run_ui(_apply)
        threading.Timer(3.0, lambda: _run_ui(_restore)).start()
    except Exception:
        pass


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


def _ui_open(url, title, on_manual_done, on_cancel, on_key_back,
             browse=False):
    """在 UI 线程挂载覆盖层：[完成登录按钮 + WebView] 全屏。

    分步执行并标记失败步骤（真机诊断）：关键步骤失败抛
    WebLoginError（消息含步骤名）；非关键步骤（配色/Cookie/缩放）
    失败跳过，不阻塞登录层弹出。
    """
    # v2.1.0 会话总闸：本层存活期间 session 不变；关闭（或新开
    # 层）即递增作废——旧层的一切迟到回调（渲染崩溃/导航/按键/
    # 取消/点击）按会话校验后直接忽略，不再误操作新层或已清理
    # 状态（真机"已登录点卡片闪退"的竞态总闸）
    sid = _STATE["session"]

    def _only_now(fn):
        def wrap(*a, **k):
            if _STATE["session"] != sid:
                return
            return fn(*a, **k)
        return wrap

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
    TextView = _step("加载TextView类",
                     lambda: autoclass("android.widget.TextView"))
    WebView = _step("加载WebView类",
                    lambda: autoclass("android.webkit.WebView"))
    LayoutParams = _step("加载LayoutParams类",
                         lambda: autoclass(
                             "android.view.ViewGroup$LayoutParams"))
    activity = _step("获取Activity", _activity)

    root = _step("构造容器", lambda: LinearLayout(activity))
    _step("容器纵向排列",
          lambda: root.setOrientation(LinearLayout.VERTICAL), critical=False)

    # v1.9.0 登录层 UI 重构：此前顶部双按钮（灰✕蓝✓小按钮）真机上
    # 文字不显示（setText/setTextColor 被静默吞掉），用户只看到
    # "三个色块"完全不知道是什么。重构为标准登录页布局——
    # 深色标题栏（✕ + "网盘名 · 网页登录"）/ 黄色提示条 / WebView /
    # 底部通栏"已完成登录"大按钮；文字经 _set_text 三级保险设置
    LLParams = _step("加载LinearLayout$LayoutParams类",
                     lambda: autoclass(
                         "android.widget.LinearLayout$LayoutParams"))

    titlebar = _step("构造标题栏", lambda: LinearLayout(activity))
    _step("标题栏横向排列",
          lambda: titlebar.setOrientation(LinearLayout.HORIZONTAL),
          critical=False)
    _step("标题栏底色",
          lambda: titlebar.setBackgroundColor(_jcolor(C_BAR_BG)),
          critical=False)

    # ✕ 关闭（左，白字 22sp）：点击放弃登录返回首页
    tv_close = _step("构造关闭按钮", lambda: TextView(activity))
    _step("关闭按钮文字", lambda: _set_text(tv_close, "✕"), critical=False)
    _step("关闭按钮字色", lambda: _set_text_color(tv_close, C_WHITE),
          critical=False)
    _step("关闭按钮字号", lambda: tv_close.setTextSize(22.0), critical=False)
    _step("关闭按钮居中", lambda: tv_close.setGravity(17), critical=False)
    # v1.8.4：点击回调必须存 Python 强引用——pyjnius 官方文档明确
    # proxy 只存指针不持引用，内联创建引用计数归零立即被 GC，
    # Java 侧点击已死 proxy 直接 native crash（真机"点击就闪退"根因）
    click_close = _step("构造关闭点击回调",
                        lambda: _ClickListener(_only_now(on_cancel)))
    _step("关闭按钮绑定点击",
          lambda: tv_close.setOnClickListener(click_close))
    _step("关闭按钮入栏", lambda: titlebar.addView(tv_close,
                                                  LLParams(240, -1)))

    # 标题（weight 撑满剩余宽度，白字 19sp 居中）
    tv_title = _step("构造标题", lambda: TextView(activity))
    _step("标题文字",
          lambda: _set_text(tv_title, f"{title} · 网页登录"), critical=False)
    _step("标题字色", lambda: _set_text_color(tv_title, C_WHITE),
          critical=False)
    _step("标题字号", lambda: tv_title.setTextSize(19.0), critical=False)
    _step("标题居中", lambda: tv_title.setGravity(17), critical=False)
    _step("标题入栏", lambda: titlebar.addView(
        tv_title, LLParams(0, -1, 1.0)))

    # 右侧对称占位（240px 与 ✕ 区等宽，标题视觉真居中）
    tv_spacer = _step("构造标题右占位", lambda: TextView(activity))
    _step("右占位入栏", lambda: titlebar.addView(tv_spacer,
                                                LLParams(240, -1)))

    _step("标题栏入容器", lambda: root.addView(titlebar,
                                               LayoutParams(-1, 170)))

    # 提示条（浅黄底深棕字）：明确告诉用户操作路径
    tv_tip = _step("构造提示条", lambda: TextView(activity))
    _step("提示条文字",
          lambda: _set_text(
              tv_tip, BROWSE_TIP_TEXT if browse else
              "在下方页面登录账号，完成后点底部按钮保存 Cookie"),
          critical=False)
    _step("提示条底色",
          lambda: tv_tip.setBackgroundColor(_jcolor(C_TIP_BG)),
          critical=False)
    _step("提示条字色", lambda: _set_text_color(tv_tip, C_TIP_FG),
          critical=False)
    _step("提示条字号", lambda: tv_tip.setTextSize(13.0), critical=False)
    _step("提示条居中", lambda: tv_tip.setGravity(17), critical=False)
    _step("提示条入容器", lambda: root.addView(tv_tip,
                                               LayoutParams(-1, 110)))

    wv = _step("构造WebView", lambda: WebView(activity))

    # v1.9.0 配置拆分：原 _cfg 闭包任何一行抛异常，整块配置被
    # critical=False 静默吞掉——setUserAgentString 若排在异常行之后
    # 就根本没执行，真机 WebView 仍用默认移动 UA，网盘 302 到
    # "下载客户端"页（真机"夸克/UC 是下载页"根因之一）。每项独立
    # step + 桌面 UA 读回验证（结果记 nav_log，真机可诊断）
    _step("启用JS", lambda: wv.getSettings().setJavaScriptEnabled(True),
          critical=False)
    _step("启用DOM存储", lambda: wv.getSettings().setDomStorageEnabled(True),
          critical=False)

    def _apply_ua():
        s = wv.getSettings()
        s.setUserAgentString(DESKTOP_UA)
        ok = False
        try:
            ok = (str(s.getUserAgentString()) == DESKTOP_UA)
        except Exception:
            pass
        log = _STATE["nav_log"]
        log.append(("ua", time.strftime("%H:%M:%S"),
                    "桌面UA已生效" if ok else "桌面UA设置失败(移动UA会跳下载页)"))
        del log[:-50]
        return ok
    _step("设置桌面UA", _apply_ua, critical=False)
    _step("宽视口", lambda: (wv.getSettings().setUseWideViewPort(True),
                             wv.getSettings().setLoadWithOverviewMode(True)),
          critical=False)
    # v1.8.4：网页加载前 WebView 默认黑底（真机深色窗口背景下
    # 观感即"黑色空白"），设白底更接近网页观感
    _step("WebView白底", lambda: wv.setBackgroundColor(_jcolor(0xFFFFFFFF)),
          critical=False)

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
    # v1.8.5 拦截回退：登录 URL 302 到 app scheme 被拦后 WebView
    # 停在空白（真机"三色区域无内容"的另一半根因）。拦截后回退
    # 重载登录页（最多 2 次，防 302 循环），仍被拦则显示说明页
    scheme_hits = {"n": 0}

    def _fallback_after_block(kind, u):
        log = _STATE["nav_log"]
        log.append(("block", time.strftime("%H:%M:%S"),
                    f"{kind}已拦截: " + u[:150]))
        del log[:-50]
        try:
            if scheme_hits["n"] < 2:
                scheme_hits["n"] += 1
                wv.loadUrl(url)
            else:
                wv.loadData(_BLOCKED_HTML, "text/html", "utf-8")
        except Exception:
            pass

    def _handle_url(u):
        block, load = _decide_url(u, _parse_intent_uri)
        if load:
            try:
                wv.loadUrl(load)
            except Exception:
                pass
        elif block:
            # 私有 scheme（quark:// alipan:// 等）：拦截 + 回退
            _fallback_after_block("Scheme跳转", u)
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
            try:
                wv.stopLoading()
            except Exception:
                pass
            _fallback_after_block("市场URL", u)

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
                      lambda: _UrlLoadingCallback(
                          _only_now(_handle_url), _only_now(_on_nav),
                          _only_now(_on_render_gone)))
    PanWebViewClient = _step(
        "加载PanWebViewClient类",
        lambda: autoclass("org.panboost.panwebview.PanWebViewClient"))
    client = _step("构造WebViewClient",
                   lambda: PanWebViewClient(client_cb))
    _step("设置WebViewClient", lambda: wv.setWebViewClient(client))

    # v1.8.2 返回键：WebView 抢焦点后自己消费 KEYCODE_BACK，必须在
    # View 层挂 OnKeyListener 拦截（硬件返回键兜底；手势返回走
    # Dialog 的 OnCancelListener，见下）
    key_cb = _step("构造返回键监听",
                   lambda: _BackKeyListener(_only_now(on_key_back)))
    _step("WebView可获焦点",
          lambda: (wv.setFocusable(True),
                   wv.setFocusableInTouchMode(True)), critical=False)
    _step("挂载返回键监听", lambda: wv.setOnKeyListener(key_cb))

    # v1.8.5：先入容器后加载（未 attach 就 loadUrl 在部分 ROM 上
    # 不渲染）；高度 0 + weight 1.0 是 LinearLayout 分配剩余空间的
    # 标准做法（比 MATCH_PARENT 更稳，即使外层窗口测量异常也能
    # 拿到按钮栏以外的全部高度）
    _step("WebView入容器", lambda: root.addView(wv, LLParams(-1, 0, 1.0)))
    _step("加载登录页", lambda: wv.loadUrl(url))

    # v1.9.0 底部通栏"已完成登录"大按钮：蓝底白字 17sp 高对比 +
    # 文字三级保险，替代原顶部小 ✓ 按钮（真机无字色块）
    btn_done = _step("构造完成按钮", lambda: TextView(activity))
    _step("完成按钮文字",
          lambda: _set_text(
              btn_done, BROWSE_BTN_TEXT if browse else DONE_BTN_TEXT),
          critical=False)
    _step("完成按钮底色",
          lambda: btn_done.setBackgroundColor(_jcolor(C_DONE_BG)),
          critical=False)
    _step("完成按钮字色", lambda: _set_text_color(btn_done, C_WHITE),
          critical=False)
    _step("完成按钮字号", lambda: btn_done.setTextSize(17.0), critical=False)
    _step("完成按钮居中", lambda: btn_done.setGravity(17), critical=False)
    click_done = _step("构造完成点击回调",
                       lambda: _ClickListener(_only_now(on_manual_done)))
    _step("完成按钮绑定点击",
          lambda: btn_done.setOnClickListener(click_done))
    _step("完成按钮入容器", lambda: root.addView(btn_done,
                                                  LayoutParams(-1, 190)))

    # v1.8.3 全屏 Dialog 承载（根治"无法返回"）：
    # Android 10+ 手势返回直接 cancel Dialog（系统标准行为），不再
    # 依赖键盘事件（此前 addContentView 覆盖层方案下手势被 SDL
    # trap 吞掉或退出整个 App，OnKeyListener 也收不到手势）。
    # OnCancelListener 是接口，pyjnius 可直接实现（_CancelListener）。
    Dialog = _step("加载Dialog类", lambda: autoclass("android.app.Dialog"))

    # v1.8.5 根治三色弹窗：默认 Dialog 是 floating 主题，AOSP
    # PhoneWindow.generateLayout() 对 floating 窗口强制
    # setLayout(WRAP_CONTENT, WRAP_CONTENT)——v1.8.4 在 show()
    # 后补 setLayout(-1,-1) 真机仍被压回（wrap 测量已定型）。
    # 用非 floating 全屏主题构造（Theme_Light_NoActionBar_
    # Fullscreen，API 1+），窗口天生 MATCH_PARENT；主题构造失败
    # 回退默认（保留 v1.8.4 行为兜底）
    def _new_dialog():
        try:
            R_style = autoclass("android.R$style")
            return Dialog(activity, R_style.Theme_Light_NoActionBar_Fullscreen)
        except Exception:
            return Dialog(activity)
    dialog = _step("构造全屏Dialog", _new_dialog)
    cancel_cb = _step("构造取消监听",
                      lambda: _CancelListener(_only_now(on_cancel)))
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
    _STATE["click_cbs"] = (click_close, click_done)
    _STATE["btn_done"] = btn_done
    _STATE["closed"].clear()


def _retire(*keys):
    """把 _STATE 指定字段的对象作为一批移入退休列表（v1.9.1 防回收闪退）。

    pyjnius 的 PythonJavaClass 被 Python GC 回收后，Java 侧持有的
    接口指针随即失效——此后任何 Java 回调（如 Chromium 迟到的
    onPageFinished）都是 native 崩溃。关闭登录层后对象不立即交给
    GC，按批（一次关闭的全部对象为一个 dict）进退休列表保留最近
    6 批（即最近 6 次登录，内存可忽略不计），彻底封死"关闭瞬间
    飞行回调"窗口。
    """
    batch = {}
    for k in keys:
        v = _STATE.get(k)
        if v is not None:
            batch[k] = v
        _STATE[k] = None
    if batch:
        rl = _STATE.setdefault("retired", [])
        rl.append(batch)
        del rl[:-6]


def _ui_close():
    """在 UI 线程关闭登录层（v1.9.1 根治"登录完成后直接闪退"）。

    真机 v1.9.0 实锤：登录保存 Cookie 后 App 闪退。根因——
    dismiss() 不会同步终止 Chromium 渲染流水线：登录成功后网盘页面
    连续跳转，in-flight 的 onPageStarted/Finished/shouldOverride-
    UrlLoading 等 IPC 回调仍排在 UI 线程消息队列中、于本函数之后
    执行；旧版此刻把 client_cb 置 None，Python 对象被 GC，Java 桥
    PanWebViewClient 对已回收对象回调 → SIGSEGV。v1.8.5 及之前
    用户从未真正走通登录（色块/错 URL），此关闭路径在真机上首次
    执行即暴露。

    三层防御：
    ① dismiss 前切断回调源：stopLoading + setWebViewClient(None)
       + setOnKeyListener(None) + setOnCancelListener(None)——
       AOSP WebViewClient 分发处判空，解绑后飞行回调不再进
       Python（每步独立 try，个别 ROM 缺方法不影响其余）；
    ② Dialog.dismiss 为主、removeView 兜底（v1.8.2 防幽灵层）；
    ③ 全部对象（含 webview/dialog/root）经 _retire 进退休列表，
       即使解绑在个别 ROM 上未生效，回调对象仍存活不会闪退。
    ④会话作废（v2.1.0）：session 递增，旧层一切在途/迟到回调
      一律忽略。
    """
    _STATE["session"] += 1
    dialog = _STATE["dialog"]
    root = _STATE["root"]
    wv = _STATE["webview"]
    if dialog is None and root is None:
        return
    if wv is not None:
        for _unbind in (
                lambda: wv.stopLoading(),
                lambda: wv.setWebViewClient(None),
                lambda: wv.setOnKeyListener(None)):
            try:
                _unbind()
            except Exception:
                pass
    if dialog is not None:
        try:
            dialog.setOnCancelListener(None)
        except Exception:
            pass
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
    _retire("root", "webview", "dialog", "client_cb", "key_cb",
            "cancel_cb", "click_cbs", "btn_done")
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
               on_cancel=None, cookie_urls=()):
    """打开 WebView 登录层。

    url: 登录页地址（桌面 UA 加载，避免移动端跳"下载App"引导页）
    auth_keys: 登录成功特征 Cookie 键（如百度 BDUSS）；命中即自动完成
    on_done(cookie_str, auto: bool): 完成回调（手动按钮或特征命中）
    on_cancel(): 放弃登录回调（✕ 返回首页按钮或返回键触发）
    cookie_urls: 额外 Cookie 采集域 URL（v1.9.2 多域探测；与登录
        页 URL 合并遍历，特征 Cookie 种在关联域也能命中）
    返回 True 表示已打开；失败抛 WebLoginError（调用方回退手动路径）。
    """
    if not _JNIUS_OK:
        raise WebLoginError("pyjnius 不可用")
    if _STATE["root"] is not None:
        raise WebLoginError("已有登录窗口打开中")
    # v2.1.0：作废上一会话一切迟到回调（上一层的渲染崩溃等
    # 回调此刻才到也直接忽略）
    _STATE["session"] += 1

    _STATE["on_cancel"] = on_cancel
    _STATE["done"] = False
    done_once = threading.Event()
    # v1.9.2 多域探测序列：网盘全部关联域 + 登录页 URL（最后，
    # 同键时登录页域优先）。登录跳转把 Cookie 种在关联域的场景
    # （如百度 passport↔pan）不再漏采
    probe_urls = tuple(cookie_urls) + (url,)

    def _finish(auto):
        if done_once.is_set():
            return
        # v1.9.2 全链路埋点：点击→多域采集→校验逐环节写导航日志
        # （只记 Cookie 键名不记值，防泄漏），真机"没反应"类问题
        # nav-*.log 直接定位卡在哪一步
        log = _STATE["nav_log"]
        log.append(("click", time.strftime("%H:%M:%S"),
                    "手动点击保存" if not auto else "特征Cookie自动命中"))
        del log[:-80]
        cookie, cerr = _gather_cookies(probe_urls)
        # v1.8.5 登录凭证校验（根治"点卡片就记已登录"）：登录页
        # 游客 Cookie（BAIDUID 等）也非空，"Cookie 非空"绝不等于
        # 已登录——参考网盘解析项目的判定思路，auth_keys 全部命中
        # 才算登录成功。未命中（v1.9.2 反馈强化）：按钮文字变红色
        # 提示（三级保险通道，真机可靠）+ Toast 双保险 + 登录层
        # 保持打开（不关层、不回调、不记账，完成登录后再点即可）
        keys = [k.lower() for k in auth_keys]
        ok = bool(cookie) and all(f"{k}=" in cookie.lower() for k in keys)
        ck = sorted({p.split("=", 1)[0].strip()
                     for p in (cookie or "").split(";") if "=" in p})
        log.append(("check", time.strftime("%H:%M:%S"),
                    f"凭证校验={'通过' if ok or not keys else '未通过'}"
                    f" 已有Cookie键={ck} 等待特征键={keys}"
                    + (f" 采集异常[{cerr}]" if cerr else "")))
        del log[:-80]
        if keys and not ok:
            _nudge_button()
            _toast(f"未检测到{title}的登录凭证，请先在页面完成登录")
            return
        done_once.set()
        _STATE["done"] = True
        _STATE["on_cancel"] = None
        try:
            _run_ui(_ui_close)
        except Exception:
            # post 失败（几乎不可能）：只重置状态（对象入退休列表
            # 防 GC 闪退）；绝不在非 UI 线程直接操作视图（Android
            # 会抛 CalledFromWrongThread）
            _retire("root", "webview", "dialog", "client_cb", "key_cb",
                    "cancel_cb", "click_cbs", "btn_done")
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
        # v2.1.0 首轮延迟 3s：层 show 后的 Chromium 启动渲染窗口
        # 绝不与"特征命中秒关层"竞争（Cookie 仍活着的重登场景）
        time.sleep(3.0)
        while not _STATE["closed"].is_set():
            p = _STATE["poller"]
            if p is None or p.get("stop"):
                return
            if keys:
                try:
                    c, _ = _gather_cookies(probe_urls)
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


def open_browse(url, title="网盘", on_close=None):
    """打开网盘浏览层（v2.1.0：已登录直入网页版文件页）。

    已登录用户点卡片：带 Cookie 直开网页版"我的文件"页——用户在
    WebView 里浏览/长按复制文件或分享链接，点底部按钮回到下载
    屏粘贴加速。不再走登录层：已登录再开登录页时 poller 首轮特
    征即命中，层 show 后 1-2s 被秒关，dismiss 与 Chromium 启动渲
    染竞争即真机"已登录点卡片闪退"根因；且已登录用户要的是
    "进我账号选东西下载"，不是再看一遍登录页。

    导航守卫/桌面 UA/返回键/渲染崩溃处理与登录层完全一致；无
    poller、无 Cookie 采集校验（浏览不动账簿）。
    on_close(): 层关闭（✕/返回键/手势/底部按钮）后回调（调用方
        切下载屏引导粘贴链接；回调在 Android UI 线程执行，只做
        调度不做 IO——v2.0.1 教训）。
    返回 True 表示已打开；失败抛 WebLoginError。
    """
    if not _JNIUS_OK:
        raise WebLoginError("pyjnius 不可用")
    if _STATE["root"] is not None:
        raise WebLoginError("已有窗口打开中")
    _STATE["session"] += 1
    _STATE["on_cancel"] = on_close
    _STATE["done"] = False
    _STATE["nav_log"] = []

    def _end():
        # 底部"去下载"按钮：关层 + on_close（_ui_close 标准
        # 三层防御 + 会话作废；本函数在 Android UI 线程执行）
        _STATE["done"] = True
        try:
            _run_ui(_ui_close)
        except Exception:
            _retire("root", "webview", "dialog", "client_cb", "key_cb",
                    "cancel_cb", "click_cbs", "btn_done")
            _STATE["closed"].set()
        cb = _STATE.get("on_cancel")
        _STATE["on_cancel"] = None
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

    def _cancel():
        close_login()

    def _key_back():
        # 网页可后退先 goBack（浏览模式核心操作），否则关层
        wv = _STATE["webview"]
        try:
            if wv is not None and wv.canGoBack():
                wv.goBack()
                return
        except Exception:
            pass
        _cancel()

    opened = {}
    opened_evt = threading.Event()
    aborted = []

    def _safe_open():
        try:
            if aborted:
                return
            _ui_open(url, title, _end, _cancel, _key_back, browse=True)
            if aborted:
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
        raise WebLoginError(f"浏览层挂载失败: {opened.get('err')}")
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
        # post 失败：只重置状态（对象入退休列表防 GC 闪退），
        # 绝不在非 UI 线程操作视图
        _retire("root", "webview", "dialog", "client_cb", "key_cb",
                "cancel_cb", "click_cbs", "btn_done")
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

#!/usr/bin/env python3
"""Android 网盘登录模块（独立 LoginActivity，v3.2.0 全面重构）。

用户在真实网盘页面完成登录（含验证码/短信/扫码——浏览器引擎渲染，
无需逆向任何网盘协议），登录后从 CookieManager 提取 Cookie 永久保存。

v3.2.0 重构（真机反馈"登录页不能展示信息"——Dialog 层在部分真机
上完全不出现或 WebView 区空白，两症状并存）：
登录/浏览从 android.app.Dialog 弹窗改为独立 LoginActivity 全屏页面
（Java 侧完整实现 UI + WebView + Cookie 采集校验 + 自动轮询 + 导航
守卫，见 java_classes/LoginActivity.java）。跨 JNI 从"每秒轮询 +
每次导航回调 + 每个按钮点击"缩到"一次启动 + 一次结果回调"，
pyjnius 在 UI 操作上的多重载解析/静默失败风险整体消除。

架构收益（对比 v1.8~v3.1 的 Dialog 方案）：
- 登录页是系统级 Activity 窗口：显示/焦点/生命周期由系统窗口
  管理器保证，不再依赖 Dialog 的 show 时序、主题 wrap 行为与
  PhoneWindow 测量竞争（"层不出现/三色块/WebView 塌陷"三族
  真机问题一次性根除）
- LoginActivity 在前台时 Kivy 宿主整体 onPause：SDL 渲染、
  触摸分发、返回键 trap 全部不再竞争
- WebView 的导航守卫/渲染崩溃/返回键全部留在 Java 侧（编译期
  类型检查），无跨 JNI 回调 GC 窗口；文字/颜色 Java 直接设置
  （Python 侧 setText 多重载解析失败的静默色块问题不复存在）
- 返回键/手势：onBackPressed 系统标准路径（canGoBack 先退
  网页再退出），彻底摆脱 SDL trap

跨 JNI 面只剩两处：
1. LoginActivity.start(activity, url, title, keysCsv, urlsCsv,
   ua, browse, cb) 静态启动——全参数 java.lang.String/boolean，
   单一方法无重载歧义，失败同步抛出（fire-and-forget 根治）
2. Callback.onLoginResult/onLoginCancel 一次性结果回调——
   PythonJavaClass 实现；Python 侧强引用存 _STATE["callback"]，
   结果后进 retired 列表防 GC（Java 侧同时置 sCallback=null，
   双端防护）

本模块保留的纯函数（_decide_url/_merge_cookies/_gather_cookies/
_parse_intent_uri）与 LoginActivity.java 内的 Java 实现同规格——
作为行为规格参照 + 离线可测（smoke 直接测行为），运行路径全部
在 Java 侧。

任何一步失败抛 WebLoginError，调用方回退到手动粘贴 Cookie 路径。
非 Android 环境下 available() 为 False，纯 Python 逻辑可 mock 测试。
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

# WebView 导航黑名单（与 LoginActivity.java MARKET_PREFIXES 同规格）：
# 市场/商店类 URL 直接停止加载——这些是"跳到下载网盘APP界面"的最终
# 落地页（onPageStarted 守卫，302 落地不经过 shouldOverrideUrlLoading）
MARKET_PREFIXES = (
    "market://", "https://market.android.com",
    "https://play.google.com/store",
    "https://android.myapp.com", "https://appgallery.huawei.com",
    "https://samsungapps.com", "https://app.mi.com",
    "https://www.coolapk.com",)


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


class _LoginCallback(PythonJavaClass):
    """LoginActivity$Callback 的 Python 实现（v3.2.0）。

    onLoginResult/onLoginCancel 在 Android UI 线程回调——内部只做
    内存状态切换 + 调用调用方回调（约定零 IO 零 Kivy 操作：磁盘
    日志与界面更新由调用方延迟调度，v2.0.1 教训）。异常全吞（Java
    侧已 catch Throwable 双保险，这里再兜一层）。
    """
    __javainterfaces__ = ["org/panboost/login/LoginActivity$Callback"]
    __javacontext__ = "app"

    def __init__(self, on_result, on_cancel):
        super().__init__()
        self._on_result = on_result
        self._on_cancel = on_cancel

    @java_method("(Ljava/lang/String;Z)V")
    def onLoginResult(self, cookie, auto):
        try:
            self._on_result(cookie, auto)
        except Exception:
            pass

    @java_method("()V")
    def onLoginCancel(self):
        try:
            self._on_cancel()
        except Exception:
            pass


class _Runnable(PythonJavaClass):
    """java.lang Runnable（current_cookies 诊断取 Cookie 用）。"""
    __javainterfaces__ = ["java/lang/Runnable"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    @java_method("()V")
    def run(self):
        self._fn()


_STATE = {"callback": None, "retired": [], "session": 0,
          "closed": threading.Event(), "done": False}


def _jstr(s):
    """Python str 转 java.lang.String 对象。

    putExtra/setText 等**多重载**方法在部分真机 ROM 上 pyjnius
    解析失败（v1.9.0 实锤）——LoginActivity.start 全参数显式传
    java.lang.String，Java 侧类型精确匹配无重载歧义。
    失败时返回原样 str（调用方 try/except 兜底）。
    """
    try:
        return autoclass("java.lang.String")(s)
    except Exception:
        return s


def _retire(*keys):
    """把 _STATE 指定字段的对象作为一批移入退休列表（v1.9.1 防回收闪退）。

    pyjnius 的 PythonJavaClass 被 Python GC 回收后，Java 侧持有的
    接口指针随即失效——此后任何 Java 回调都是 native 崩溃。结果
    回调后对象不立即交给 GC，按批（一次登录的全部对象为一个 dict）
    进退休列表保留最近 6 批（即最近 6 次登录，内存可忽略不计），
    彻底封死"结果回调瞬间飞行事件"窗口。
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


def _merge_cookies(*parts):
    """合并多域 Cookie 字符串（v1.9.2 多域探测，规格参照）。

    网盘登录跳转常把 Cookie 种在关联域（如百度在
    passport.baidu.com 登录、pan.baidu.com 使用）——只查登录页
    URL 会漏。分号拆键值合并，后出现的键覆盖先前值。
    返回合并串；全空返回 None。（运行路径在 LoginActivity.java
    gatherCookies，此函数供离线测试与规格对照）
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
    """遍历 urls 逐域取 Cookie 并合并（v1.9.2，规格参照）。

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


def _decide_url(url, parse_intent=None):
    """WebView 导航策略（纯函数，离线可测，规格参照）。

    返回 (block, load_url)：
    - http/https → (False, None) 放行 WebView 正常加载
    - intent:// 且提供 parse_intent → 解析出 http(s) 的
      browser_fallback_url 则 (True, fallback)（拦截原跳转、
      在 WebView 内加载 fallback 网页——Chrome 的标准约定）
    - 其余（market:// tmast:// appmarket:// 微信/网盘私有 scheme、
      file:// javascript: about: 空 URL…）→ (True, None) 一律拦截
      ——这正是"跳到下载网盘APP界面"的逃逸通道。

    运行路径在 LoginActivity.java onUrlLoading/parseIntentFallback
    （同规格实现）；此函数供离线测试。
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
    """解析 intent:// URI 取 browser_fallback_url（规格参照）。

    安全加固：addCategory(BROWSABLE) + setComponent(None) +
    setSelector(None)，防 intent scheme hijacking（页面定向拉起
    App 私有组件）。（运行路径在 LoginActivity.java
    parseIntentFallback，同规格）
    """
    if not _JNIUS_OK:
        return None
    Intent = autoclass("android.content.Intent")
    i = Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
    i.addCategory(Intent.CATEGORY_BROWSABLE)
    i.setComponent(None)
    i.setSelector(None)
    return i.getStringExtra("browser_fallback_url")


def current_cookies(url):
    """取 WebView 里 url 域的 Cookie（含 httpOnly）。失败返回 None。

    v3.2.0 起运行采集在 LoginActivity.java（Java 侧）；本函数保留
    供 Python 侧诊断调用与离线 mock 测试（v1.9.1 曾误删此函数致
    点保存必失败——防回归门禁要求符号存在）。
    """
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
        _activity().runOnUiThread(_Runnable(grab))
        for _ in range(50):  # 等 UI 线程回写，最多 2.5s
            if "cookie" in box or "err" in box:
                break
            time.sleep(0.05)
    except Exception as e:
        raise WebLoginError(f"读取 Cookie 失败: {e}")
    if "err" in box:
        raise WebLoginError(f"读取 Cookie 失败: {box['err']}")
    return box.get("cookie")


def _start_activity(url, title, auth_keys, cookie_urls, browse,
                    on_result, on_cancel):
    """启动 LoginActivity（内部公共路径，v3.2.0 核心）。

    单一静态方法调用：全参数显式 java.lang.String/boolean，无重载
    歧义；任何失败同步抛出（fire-and-forget 根治，v1.7.0 教训）。
    返回 _LoginCallback（调用方存 _STATE 防回收）。
    """
    cb = _LoginCallback(on_result, on_cancel)
    keys_csv = ",".join(k for k in auth_keys if k)
    urls_csv = ",".join(u for u in cookie_urls if u)
    try:
        LoginActivity = autoclass("org.panboost.login.LoginActivity")
        activity = _activity()
        LoginActivity.start(
            activity, _jstr(url), _jstr(title or "登录"),
            _jstr(keys_csv), _jstr(urls_csv),
            _jstr(DESKTOP_UA), bool(browse), cb)
    except Exception as e:
        # 启动失败：回调对象不可能再被 Java 触发，直接入退休
        # 列表防回收窗口，异常同步抛给调用方
        _STATE.setdefault("retired", []).append({"callback": cb})
        raise WebLoginError(
            f"登录页启动失败: {type(e).__name__}: {e}")
    return cb


def open_login(url, auth_keys=(), on_done=None, title="登录",
               on_cancel=None, cookie_urls=()):
    """打开网盘登录页（独立 Activity）。

    url: 登录页地址（桌面 UA 加载，避免移动端跳"下载App"引导页）
    auth_keys: 登录成功特征 Cookie 键（如百度 BDUSS）；命中即自动完成
    on_done(cookie_str, auto: bool): 完成回调（手动按钮或特征命中；
        在 Android UI 线程执行，零工作零 IO——磁盘/界面操作由调用
        方延迟调度）
    on_cancel(): 放弃登录回调（✕ / 返回键 / 系统回收兜底触发）
    cookie_urls: 额外 Cookie 采集域 URL（多域探测；与登录页 URL
        合并遍历，特征 Cookie 种在关联域也能命中）
    返回 True 表示已打开；失败抛 WebLoginError（调用方回退手动路径）。
    """
    if not _JNIUS_OK:
        raise WebLoginError("pyjnius 不可用")
    if _STATE["callback"] is not None:
        raise WebLoginError("已有登录窗口打开中")
    # 会话总闸（v2.1.0 语义保留）：新开页即递增作废上一会话
    _STATE["session"] += 1
    _STATE["done"] = False
    done_once = threading.Event()

    def _on_result(cookie, auto):
        if done_once.is_set():
            return
        done_once.set()
        _STATE["done"] = True
        _retire("callback")
        _STATE["closed"].set()
        if on_done is not None:
            try:
                on_done(cookie or "", bool(auto))
            except Exception:
                pass

    def _on_cancel():
        if done_once.is_set():
            return
        done_once.set()
        _retire("callback")
        _STATE["closed"].set()
        if on_cancel is not None:
            try:
                on_cancel()
            except Exception:
                pass

    _STATE["closed"].clear()
    _STATE["callback"] = _start_activity(
        url, title, auth_keys, tuple(cookie_urls), False,
        _on_result, _on_cancel)
    return True


def open_browse(url, title="网盘", on_close=None):
    """打开网盘浏览页（独立 Activity，v2.1.0 语义 + v3.2.0 承载）。

    已登录用户点卡片：带 Cookie 直开网页版"我的文件"页——用户在
    WebView 里浏览/长按复制文件或分享链接，点底部"已复制链接，
    去下载"按钮回到下载屏粘贴加速。无特征校验、无自动轮询
    （浏览不动账簿）；on_close(): 页面关闭（✕/返回键/底部按钮）
    后回调（在 Android UI 线程执行，只做调度不做 IO）。
    返回 True 表示已打开；失败抛 WebLoginError。
    """
    if not _JNIUS_OK:
        raise WebLoginError("pyjnius 不可用")
    if _STATE["callback"] is not None:
        raise WebLoginError("已有窗口打开中")
    _STATE["session"] += 1
    ended = threading.Event()

    def _on_result(_cookie, _auto):
        # 浏览模式底部按钮：不采集 Cookie，直接走关闭回调
        if ended.is_set():
            return
        ended.set()
        _retire("callback")
        _STATE["closed"].set()
        if on_close is not None:
            try:
                on_close()
            except Exception:
                pass

    def _on_cancel():
        # ✕ / 返回键 / 系统回收：同为关闭（浏览模式无"放弃"语义）
        if ended.is_set():
            return
        ended.set()
        _retire("callback")
        _STATE["closed"].set()
        if on_close is not None:
            try:
                on_close()
            except Exception:
                pass

    _STATE["closed"].clear()
    _STATE["callback"] = _start_activity(
        url, title, (), (), True, _on_result, _on_cancel)
    return True


def nav_log():
    """导航日志快照（真机诊断"到底跳去了哪"）。

    LoginActivity.java 侧维护（"kind|epochMillis|msg"），本函数取回
    转换为 (kind, "HH:MM:SS", msg) 三元组列表（与历史版本同格式，
    调用方落盘逻辑无需变更）；最近 80 条。
    """
    out = []
    if not _JNIUS_OK:
        return out
    try:
        LoginActivity = autoclass("org.panboost.login.LoginActivity")
        raw = LoginActivity.dumpNavLog()
        for item in raw:
            parts = str(item).split("|", 2)
            if len(parts) == 3:
                kind, ts, msg = parts
                try:
                    hhmm = time.strftime(
                        "%H:%M:%S", time.localtime(float(ts) / 1000.0))
                except Exception:
                    hhmm = ts
                out.append((kind, hhmm, msg[:180]))
    except Exception:
        pass
    return out


def is_open():
    """登录/浏览页是否存活（结果回调后即 False）。"""
    return _STATE["callback"] is not None


def close_login():
    """放弃登录、直接关闭登录页（✕ 按钮或返回键触发）。

    不提取 Cookie、不触发 on_done；Java 侧 onDestroy 兜底会回调
    onLoginCancel → open_login 的 on_cancel（调用方用于更新界面）。
    """
    if _STATE["callback"] is None:
        return
    try:
        if _JNIUS_OK:
            LoginActivity = autoclass("org.panboost.login.LoginActivity")
            LoginActivity.finishSelf()
    except Exception:
        _retire("callback")
        _STATE["closed"].set()


def request_back():
    """Kivy 层键盘返回键兜底（保留接口兼容）。

    v3.2.0 起登录页在前台时 Kivy 宿主整体 onPause 收不到按键——
    系统返回键由 LoginActivity.onBackPressed 系统级处理；本函数
    仅为兼容既有调用点。
    """
    close_login()

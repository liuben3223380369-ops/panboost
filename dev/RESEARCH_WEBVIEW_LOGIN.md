# Android WebView 内嵌网盘登录页（Kivy/pyjnius 场景）技术调研简报

调研日期：2026-10-19
调研对象：Kivy + python-for-android（p4a，sdl2 bootstrap）+ pyjnius，无 Java 源码，内嵌原生 WebView 打开百度网盘 / 夸克网盘 / 123 云盘官方登录页遇到的两个真机问题（A：被引导到"下载 App"页；B：返回键无法关闭 WebView 层）。

调研方式：Android 官方文档（经 developer.android.google.cn 镜像）、pyjnius / p4a / Kivy / SDL 官方源码（GitHub raw / jsdelivr / GitHub API 多通道抓取并逐行验证）、三个真机验证过的开源 Kivy+WebView 项目（razzbee、xiaoyaoking、Novfensec/NfsWebview）、对 pan.baidu.com / passport.baidu.com / pan.quark.cn / www.123pan.com 的实际 HTTP 请求与页面脚本逆向（一手数据）。StackOverflow 经 StackExchange API 检索（正文受 Cloudflare 拦截，引用其问题标题与链接）。

---

## 执行摘要

问题 A 的根因已由 Android 官方文档直接证实：**未调用 setWebViewClient 时，WebView 对页面发起的任何导航（含 JS location 跳转与 intent://、market:// 等非 http scheme）默认"交给系统的 Activity Manager 选择处理器"**，即跳出 WebView 走系统 Intent 分发，直达应用市场或拉起目标 App。修复必须设置 WebViewClient 并在 shouldOverrideUrlLoading 中拦截。

但 pyjnius 的 PythonJavaClass 底层是 java.lang.reflect.Proxy.newProxyInstance（源码已验证），**只能实现 Java 接口，不能继承 WebViewClient 这个抽象类**；社区成熟方案（razzbee / NfsWebview 等真机项目）都是"自定义 Java 桥接类 extends WebViewClient + 自定义回调接口"，通过 buildozer 的 `android.add_src` 把少量 Java 源码编进 APK。同名重载问题 pyjnius 已内建支持：`java_method(签名, name=...)`。

问题 B 的根因是一个三层叠加：其一，`android.map_key` 在现代 p4a（2019 起，Python3 bootstrap）中**已不存在**（源码验证，仅剩 `KEYCODE_BACK = 4` 常量）；其二，SDL 官方头文件证实 `SDL_ANDROID_TRAP_BACK_BUTTON` hint 默认为 "0"，此时**返回键由系统处理，根本不会产生 SDL 键盘事件**，Kivy 的 Window.on_keyboard 自然收不到 27（Kivy 源码中确有 `key_map[1073742094] = 27` 的 Android 特判，但前提是事件能到达 SDL）；其三，WebView 获得焦点后返回键会被 WebView 自身消费（goBack）。修复：设 `SDL_ANDROID_TRAP_BACK_BUTTON=1` + 给 WebView 挂 `View.OnKeyListener`（纯接口，pyjnius 可直接实现，无需 Java 桥）。

---

## 问题 1：未设置 WebViewClient 时，导航如何分发？"下载 App 引导页"的链路

### 结论

**分发行为（官方文档原句，逐字）**：

> "If a WebViewClient is not provided, by default WebView will ask Activity Manager to choose the proper handler for the URL. If a WebViewClient is provided, returning true causes the current WebView to abort loading the URL, while returning false causes the WebView to continue loading the URL as usual."

即：未提供 WebViewClient 时，WebView 默认把 URL 交给系统的 Activity Manager 去选择处理器——对 http(s) 链接表现为拉起系统浏览器，对 `intent://`、`market://`、`tmast://` 等私有 scheme 则按 ACTION_VIEW 分发给已安装的对应 App（应用市场、目标网盘 App 等）。**链接点击、JS `location.href` 赋值、HTTP 30x 重定向都会走到这条默认路径，从而跳出 WebView**。设置了 WebViewClient 且 shouldOverrideUrlLoading 返回 true，则当前 WebView 中止加载，由宿主 App 全权决定动作。

官方文档同时明确了三个边界（直接决定拦截代码怎么写）：
- `loadUrl()` 发起的导航**不会**回调 shouldOverrideUrlLoading（App 自己发起的无需拦截）；
- **POST 请求不回调** shouldOverrideUrlLoading；
- 该回调**可能对子帧和非 HTTP(S) scheme 触发**（即 intent://、market://、tel: 都会经过这里，必须在返回 true 前自己分流，不能直接 loadUrl 一个非 http scheme）。

**"跳到下载 App 界面"最可能的技术链路**（结合对百度网盘移动版页面脚本的一手逆向）：

1. 网盘页 JS 判定为移动环境（见问题 5：检测维度不止 UA），主动改写导航。实测百度网盘移动版 HTML 内联脚本中存在 `window.location.href = jumptourl`（延迟 100ms 执行），目标为 `market://` / `intent://...;package=com.baidu.netdisk;...;end` 类地址；
2. WebView 无 WebViewClient → Chromium WebView 将该导航请求转交系统 Activity Manager（上述官方默认行为）；
3. 系统解析 `intent://` 的 `package=` 或 `market://details?id=` → 拉起应用市场或网盘 App，用户看到"打开客户端/下载 App"界面。

**可执行修复**：设置 WebViewClient；shouldOverrideUrlLoading 中仅放行 http/https（白名单），其余一律 `return true` 拦截；对 `intent://` 按"问题 3"的方式解析 fallback。百度网盘实测还有一条捷径：URL 带 `adapt=pc` 参数（官方脚本自带机制）可直接进 PC 视图（详见问题 5）。

### 来源

- Android 官方 WebViewClient 文档（含上述原句，经 developer.android.google.cn 镜像全文抓取验证）：https://developer.android.com/reference/android/webkit/WebViewClient
- 百度网盘移动版 pan.baidu.com 页面内联 platform 脚本（本次调研 curl 实测逆向，含 `jumptourl` 跳转逻辑与 `adapt=pc` 参数处理）

---

## 问题 2：pyjnius 覆写 WebViewClient 的正确写法

### 结论

**核心事实（源码级验证）：pyjnius 的 PythonJavaClass 不能直接继承 WebViewClient。**

pyjnius 的 `jnius/jnius_proxy.pxi`（master 分支）中 `create_proxy_instance` 的实现为：

```python
Proxy = autoclass('java.lang.reflect.Proxy')
NativeInvocationHandler = autoclass('org.jnius.NativeInvocationHandler')
j_interfaces = [find_javaclass(x) for x in j_interfaces]
j_obj = Proxy.newProxyInstance(classLoader, j_interfaces, nih)
```

即 PythonJavaClass 的实例 = `java.lang.reflect.Proxy.newProxyInstance(classLoader, 接口数组, InvocationHandler)`。`java.lang.reflect.Proxy` 只接受接口类型，`android.webkit.WebViewClient` 是抽象类而非接口，直接声明 `__javainterfaces__ = ['android/webkit/WebViewClient']` 会在构造时抛 IllegalArgumentException。pyjnius 官方文档也明确写着："You can only implement Java interfaces. You cannot sub-class a java object."

社区真机验证过的方案（razzbee/kivy-android-webview、xiaoyaoking/kivy-android-webview、Novfensec/NfsWebview 三个项目一致采用）：**写一个极小的 Java 桥接类 extends WebViewClient，把回调转发给一个自定义 Java 接口，Python 侧用 PythonJavaClass 实现该接口**，Java 桥接类通过 buildozer 的 `android.add_src` 编进 APK（不需要改 p4a 本体）。

**签名选择（minSdk 24）**：官方文档证实两个签名——

- `shouldOverrideUrlLoading(WebView, WebResourceRequest)`：API 24+ 推荐版本；
- `shouldOverrideUrlLoading(WebView, String)`：**"deprecated in API level 24"**，但弃用不等于不调用。AOSP frameworks/base 的 WebViewClient 抽象类中新签名默认实现会转调旧签名（Chromium WebView 分发回调时按"子类覆写了哪个就调哪个"兼容处理），因此**只覆写 String 版本在 API 24+ 设备上依然有效**；但为了两个版本都兜住，Java 桥接类中两个签名都 override 并转发给接口的两个方法最稳妥（下面的示例代码即如此）。

**同名重载：pyjnius 原生支持。** `java_method(java_signature, name=None)` 的 `name` 参数官方说明原文："The name of the method will be the name of the Python method by default. You can still force it, **in case of multiple signature with the same Java method name**."——Python 侧用两个不同的方法名，都通过 `name='shouldOverrideUrlLoading'` 映射到同一 Java 方法。`jnius_proxy.pxi` 中方法注册表按 `(Java方法名, 签名)` 二元组索引（`self.__javamethods__[(attr.__javaname__ or x, signature)] = attr`），重载不会互相覆盖。若 Java 调到了未实现的方法，pyjnius 会打印 "Python/java method missing" 并抛 NotImplementedError（invoke 捕获后返回 None，不会闪退，但回调失效）。

**完整可用代码**（PythonJavaClass 语法、重载、强引用保持均已按源码与官方文档核对）：

Java 桥接类（保存为 `java_classes/panwebview/PanWebViewClient.java`）：

```java
package com.myapp.panwebview;

import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;

public class PanWebViewClient extends WebViewClient {

    public interface PanWebViewClientInterface {
        boolean onUrlLoading(WebView view, String url);          // 对应旧签名
        boolean onUrlLoadingNew(WebView view, WebResourceRequest request); // 对应新签名
    }

    private final PanWebViewClientInterface cb;

    public PanWebViewClient(PanWebViewClientInterface cb) {
        super();
        this.cb = cb;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
        return cb.onUrlLoading(view, url);
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        return cb.onUrlLoadingNew(view, request);
    }
}
```

buildozer.spec 中（这是"无 Java 工程"项目接入 Java 源码的官方途径，razzbee README 同款做法）：

```ini
android.add_src = java_classes/panwebview/PanWebViewClient.java
```

Python 侧：

```python
from jnius import autoclass, PythonJavaClass, java_method

PanWebViewClientJava = autoclass('com.myapp.panwebview.PanWebViewClient')

class PanWebViewCallback(PythonJavaClass):
    # 内部接口用 $ 语法；APK 自带的类必须用 app classloader（pyjnius 文档规定）
    __javainterfaces__ = ['com/myapp/panwebview/PanWebViewClient$PanWebViewClientInterface']
    __javacontext__ = 'app'

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    # 旧签名 (WebView, String) -> boolean
    @java_method('(Landroid/webkit/WebView;Ljava/lang/String;)Z')
    def onUrlLoading(self, view, url):
        return self.owner.handle_url(url)

    # 新签名 (WebView, WebResourceRequest) -> boolean
    @java_method('(Landroid/webkit/WebView;Landroid/webkit/WebResourceRequest;)Z')
    def onUrlLoadingNew(self, view, request):
        return self.owner.handle_url(request.getUrl().toString())

# 使用（注意：回调对象必须以 Python 强引用持有，否则 GC 后 Java 回调崩溃——pyjnius 文档明确警告）
self._client_cb = PanWebViewCallback(self)
client = PanWebViewClientJava(self._client_cb)
webview.setWebViewClient(client)
```

补充要点：WebView/WebSettings 的其余操作（setJavaScriptEnabled、setDomStorageEnabled、setUserAgentString、setSupportMultipleWindows 等）都是普通 Java 方法调用，autoclass 后直接用，不需要桥接；p4a 自带的 `webview` bootstrap 源码（PythonActivity.java）里有一份官方 Java 参考实现（shouldOverrideUrlLoading 中白名单 file/127.0.0.1、其余 startActivity 交给系统），可作为策略参考。

### 来源

- pyjnius 官方 API 文档（PythonJavaClass / java_method / name 参数 / __javacontext__ / 强引用警告）：https://github.com/kivy/pyjnius/blob/master/docs/source/api.rst
- pyjnius 代理实现源码：https://github.com/kivy/pyjnius/blob/master/jnius/jnius_proxy.pxi
- WebViewClient 双签名与弃用说明：https://developer.android.com/reference/android/webkit/WebViewClient
- razzbee/kivy-android-webview（Java 桥接 + android.add_src 完整真机方案）：https://github.com/razzbee/kivy-android-webview
- Novfensec/NfsWebview（同为接口桥接模式）：https://github.com/Novfensec/NfsWebview
- p4a webview bootstrap 官方 Java 参考实现：https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/bootstraps/webview/build/src/main/java/org/kivy/android/PythonActivity.java

---

## 问题 3：intent:// URI 的标准处理

### 结论

**intent:// 是 Chrome 定义的 URI 编码 Intent 格式**，形如：

```
intent://scan/#Intent;scheme=zxing;package=com.google.zxing.client.android;S.browser_fallback_url=http%3A%2F%2Fexample.com%2F;end
```

Android 官方 `Intent.parseUri(String uri, int flags)`（API 4+）负责解析，flags 传 `URI_INTENT_SCHEME`（常量值 1），官方文档原句："This URI may encode the action, category, and other intent fields"；fragment 内的 `;键=值;` 序列中，`S.xxx=` 是 String extra、`i.xxx=` 是 int extra（官方文档 URI_ANDROID_APP_SCHEME 一节的示例明确给出该语法）——因此 `S.browser_fallback_url` 解析出来就是一个普通 String extra，用 `getStringExtra('browser_fallback_url')` 取。这是 Chrome 浏览器（非系统 WebView）约定：目标 App 不存在时改开 fallback 网页。

pyjnius 写法（纯 autoclass 调用，无需桥接）：

```python
from jnius import autoclass
Intent = autoclass('android.content.Intent')

def parse_intent_uri(url):
    """返回 ('load', fallback_url) / ('block', None) / ('external', intent)"""
    try:
        # URI_INTENT_SCHEME = 1
        i = Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
    except Exception:          # URISyntaxException 等
        return ('block', None)
    # 安全加固（防 intent scheme hijacking，见 SO 55352164）
    i.addCategory(Intent.CATEGORY_BROWSABLE)   # 'android.intent.category.BROWSABLE'
    i.setComponent(None)
    i.setSelector(None)
    fallback = i.getStringExtra('browser_fallback_url')
    if fallback and fallback.startswith('http'):
        return ('load', fallback)
    return ('block', None)
```

**scheme 放行清单（结合 SO 高赞实践与网盘场景）**：

| scheme | 处理 |
|---|---|
| http / https | 放行（return false 让 WebView 加载） |
| intent:// | 按上式解析；有 http(s) 的 browser_fallback_url 则在 WebView 内加载 fallback，否则拦截 |
| market:// 、tmast:// 、appmarket:// 等市场协议 | **拦截**（这正是"下载 App"逃逸通道；如确需下载可自建确认弹层后手动 startActivity） |
| tel: 、mailto: 、sms: 、geo: | 放行给系统（登录场景几乎不出现，放行可保证不误伤；SO 4338305 / 18874282 为 tel:/mailto: 的经典处理案例） |
| about: 、data: 、blob: 、javascript: | 拦截或按需放行 |
| file:// | 默认拦截（安全） |

安全提示：解析 intent:// 后必须 `setComponent(None)` + `setSelector(None)` 并追加 BROWSABLE category，否则页面可以定向拉起 App 的私有组件（intent scheme hijacking，见引用 SO 问题）。

### 来源

- Android 官方 Intent.parseUri / URI_INTENT_SCHEME / extras 语法：https://developer.android.com/reference/android/content/Intent
- Chrome intent:// 与 browser_fallback_url 机制问答（StackExchange API 检索）：https://stackoverflow.com/questions/34197933/how-do-you-call-an-android-app-and-get-a-result-back-from-a-web-page-in-chrome
- browser_fallback_url 引入版本讨论：https://stackoverflow.com/questions/34158613/when-was-s-browser-fallback-url-introduced-in-chrome
- intent scheme hijacking 防护：https://stackoverflow.com/questions/55352164/how-to-use-correct-intents-for-a-webview-on-vulnerable-intent-scheme-hijacking
- tel:/mailto: 处理经典案例：https://stackoverflow.com/questions/4338305/android-webview-tel-links-show-web-page-not-found 、https://stackoverflow.com/questions/18874282/webview-email-link-mailto

---

## 问题 4：p4a/Kivy 的返回键链路与拦截方案

### 结论

**完整事件链（每一步均经源码验证）**：

```
Android KEYCODE_BACK(4)
  → SDLActivity.dispatchKeyEvent → SDLSurface(View.OnKeyListener).onKey
  → SDLActivity.handleKeyEvent: ACTION_DOWN → onNativeKeyDown(4)（return true 消费事件）
  → SDL native: KEYCODE_BACK → SDL_SCANCODE_AC_BACK → SDL 键盘事件 SDLK_AC_BACK = 1073742094
  → Kivy _window_sdl2.pyx poll → ('keydown', mod, 1073742094, scancode, None)
  → kivy/core/window/window_sdl2.py 第 209-211 行（Android 特判）:
        elif platform == 'android':
            # map android back button to escape
            self.key_map[1073742094] = 27
  → dispatch('on_keyboard', 27, ...)   ← keycode 确实是 27（escape）
```

**四个关键事实：**

1. **`android.map_key` 在现代 p4a 中不存在。** develop 分支 `pythonforandroid/recipes/android/src/android/_android.pyx` 全文（343 行）只有 `KEYCODE_BACK = 4` 等常量表，无 map_key 函数；v2019.06.06、v2020.06.02、v2022.03.13、0.7.0 各 tag 的 android 模块中同样没有。`map_key(KEYCODE_BACK, 27)` 是 Python2/老 p4a（pygame provider 时代）的 API，且键码映射职责现已内置进 Kivy 的 window_sdl2.py（如上），不需要也无法再调用。

2. **on_keyboard 收不到 27 的第一层根因：SDL hint 默认值。** SDL 官方 `include/SDL_hints.h` 对 `SDL_HINT_ANDROID_TRAP_BACK_BUTTON` 的注释原文：

   > "0" - Back button will be handled as usual for system. (default)
   > "1" - Back button will be trapped, allowing you to handle the key press manually. ... will show up as an SDL_KEYDOWN / SDL_KEYUP pair with a keycode of SDL_SCANCODE_AC_BACK.

   **默认 "0" 时返回键由系统处理（触发 SDLActivity.onBackPressed → super，默认退出 App），根本不产生 SDL 键盘事件，Kivy 自然收不到 27。** 修复（两种等价方式，任选）：
   - 在 main.py 的第一行、任何 kivy import 之前：
     ```python
     import os
     os.environ['SDL_ANDROID_TRAP_BACK_BUTTON'] = '1'
     ```
     （SDL 的 GetHint 对未显式 SetHint 的 hint 会回落读取同名进程环境变量；且该 hint 是运行时查询——SDLActivity.onBackPressed 每次都调 nativeGetHintBoolean，时序安全。CPython 的 os.environ 赋值会同步到 C 层 putenv，同进程的 SDL 可见。）
   - 或 buildozer.spec 里 `android.add_manifest = ./manifest_extra.txt`，文件中加：
     ```xml
     <meta-data android:name="SDL_ANDROID_TRAP_BACK_BUTTON" android:value="1" />
     ```
     （SDL 的 getManifestEnvironmentVariables 机制，SDL_android.c 源码中可见该方法绑定。）

3. **第二层根因：WebView 抢焦点消费返回键。** 用户点击登录页后 WebView 获得焦点，KEYCODE_BACK 走到 WebView 自身（默认行为 goBack）而不经过 SDL surface——即使 trapBack=1 Kivy 也收不到。**修复：给 WebView 挂 `View.OnKeyListener`（View.OnKeyListener 是接口，pyjnius 可直接实现，无需 Java 桥），在 WebView 层拦截：**

   ```python
   from jnius import PythonJavaClass, java_method

   class WebBackKeyHandler(PythonJavaClass):
       __javainterfaces__ = ['android/view/View$OnKeyListener']   # 系统接口，默认 system loader
       # __javacontext__ = 'system'  # 默认即 system，可省略

       def __init__(self, on_back):
           super().__init__()
           self.on_back = on_back

       @java_method('(Landroid/view/View;ILandroid/view/KeyEvent;)Z')
       def onKey(self, v, keyCode, event):
           # KEYCODE_BACK=4, ACTION_DOWN=0, ACTION_UP=1
           if keyCode == 4 and event.getAction() == 1:
               self.on_back()      # 关闭 WebView 层
               return True         # 消费，阻止 WebView goBack / 系统默认
           return False

   self._back_handler = WebBackKeyHandler(self.close_webview_layer)  # 持强引用！
   webview.setFocusable(True)
   webview.setFocusableInTouchMode(True)
   webview.setOnKeyListener(self._back_handler)
   ```

4. **onKeyDown / dispatchKeyEvent 覆写与 PythonActivity 继承：不可用（Proxy 限制）与过重（不推荐）。** PythonActivity 是编译进 APK 的 Java 类；pyjnius 无法"继承"它（同问题 2 的 Proxy 限制，KeyEvent.Callback 系回调也不是接口）。理论上可通过 `android.add_src` 提供一个 `MyActivity extends PythonActivity` 并改 AndroidManifest 的 launchable-activity 实现覆写，但这要动构建链和 manifest，收益低于上面的 OnKeyListener 方案，不推荐。

**落地组合**：`SDL_ANDROID_TRAP_BACK_BUTTON=1`（兜底：WebView 无焦点时 Kivy 层收 27）+ `WebView.setOnKeyListener`（WebView 有焦点时直接拦）。两层覆盖后无论焦点在哪，返回键都归你处理。

**附**：p4a 对 SDL 的补丁（bootstraps/sdl2/build/src/patches/SDLActivity.java.patch、SDLSurface.java.patch）只改软键盘 inputType 与触摸拦截，不涉及按键分发，上述链路分析不受 p4a 补丁影响。

### 来源

- p4a android 模块源码（无 map_key，仅 KEYCODE_BACK=4）：https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/recipes/android/src/android/_android.pyx
- Kivy 2.3.0 window_sdl2.py（key_map[1073742094]=27 的 Android 特判）：https://github.com/kivy/kivy/blob/2.3.0/kivy/core/window/window_sdl2.py
- SDL 官方 SDL_hints.h（TRAP_BACK 默认 "0" 语义）：https://github.com/libsdl-org/SDL/blob/release-2.26.x/include/SDL_hints.h
- SDL SDLActivity.java（dispatchKeyEvent/handleKeyEvent/onNativeKeyDown/onBackPressed）：https://github.com/libsdl-org/SDL/blob/release-2.26.x/android-project/app/src/main/java/org/libsdl/app/SDLActivity.java
- p4a sdl2 bootstrap PythonActivity（extends SDLActivity）与 SDL 补丁：https://github.com/kivy/python-for-android/tree/develop/pythonforandroid/bootstraps/sdl2
- View.OnKeyListener 官方接口：https://developer.android.com/reference/android/view/View.OnKeyListener

---

## 问题 5：网盘"桌面模式"与 PC 登录页

### 结论（一手实测 + 脚本逆向）

**百度网盘**：

- 服务端按 UA 切换页面：同一 `https://pan.baidu.com/`，桌面 UA 返回标题"百度网盘-免费云盘丨文件共享软件…"（PC 版壳），移动 UA 返回"百度网盘，让美好永远陪伴"（H5 版壳）——均 200，切换在服务端内容层完成。
- **H5 版内嵌的官方跳转脚本（本次实测逆向）逻辑**：将 `/wap/home` 映射为 `/disk/home`、`/wap/view` 映射为 `/disk/home?adapt=pc&fr=ftw`、`/wap/shareview?surl=X` 映射为 `/s/X?...&adapt=pc&fr=ftw`，然后 `setTimeout(..., 100)` 执行 `window.location.href = jumptourl`；**URL 已带 `adapt=pc` 参数时不跳转**；UA 含 `PC-Windows` / `PC-Mac`（百度网盘桌面客户端内嵌标识）时也跳过。
- **可直接使用的结论**：
  - PC 登录页：`https://passport.baidu.com/v2/?login`（实测 HTTP 200，CSP 引用 ppui-static-pc PC 静态资源，为 PC 版统一登录页），登录态 cookie（BDUSS 等）与 pan.baidu.com 同域互通，登录后跳回网盘。
  - 网盘页强制 PC 视图：`https://pan.baidu.com/disk/home?adapt=pc&fr=ftw`（`adapt=pc` 是百度自家脚本使用的官方参数）。
  - 这解释了"设了桌面 UA 仍见引导页"的一种可能：即使 UA 是桌面版，某些入口/分享链接仍会先落 H5 壳再由脚本跳转；用对入口 URL + adapt=pc 参数可绕开。

**夸克网盘**：`https://pan.quark.cn/` 为 SPA（阿里系 quark-cloud-drive 前端），对桌面 UA 直接提供网页版布局（实测 PC UA 返回"夸克网盘 - 网页版丨客户端下载…"页面；对数据中心 IP 的 HEAD 请求返回 503，属 CDN 策略，真机浏览器不受影响）。无独立 PC 登录域名，登录页在 SPA 内（手机号验证码/支付宝授权）。建议直接以桌面 UA 打开 `https://pan.quark.cn/`，拦截其 `scheme` 跳转即可。

**123 云盘**：`https://www.123pan.com/` 实测（桌面 UA，200，97KB 完整 HTML）：标题"123云盘官网 - 免费不限速|下载免登录|直链CDN|省钱好服务"，页面内**未检出任何"打开APP/客户端下载"引导词、无 UA/环境检测脚本**。123pan 是网页优先产品，WebView 内直接打开即可，无需特殊处理。

**WebView/移动环境检测特征（UA 之外）**：业界通用检测面包括 `window.__wxjs_environment`（微信 H5：微信内为 'miniprogram'/'browser'，微信官方小程序 web-view 文档使用）、`window.WebViewJavascriptBridge`（iOS App 内嵌 JS 桥，同名开源库的事实标准）、`window.webkit.messageHandlers`（iOS WKWebView）、`window.Android`/原生注入对象、`ontouchstart` in window / `navigator.maxTouchPoints > 0`（触屏能力——**设了桌面 UA 仍被判为移动环境的常见原因**）、`window.matchMedia('(pointer: coarse)')`、屏幕尺寸/viewport。对本次实测的百度网盘 H5 壳，其跳转脚本仅依赖 UA（PC-Windows/PC-Mac 判定）+ adapt 参数 + 路由匹配，未见上述深层特征；若换入口 URL 后仍被引导，优先排查 UA 是否残留 `; wv)` 或 `Mobile` 片段，其次用 `evaluateJavascript` 注入探测脚本观察页面判定变量。

### 来源

- pan.baidu.com 双 UA 实测 + H5 版内联跳转脚本逆向（本次调研一手数据）
- passport.baidu.com/v2/?login 实测（HTTP 200，PC 资源引用）
- www.123pan.com 桌面 UA 实测（无引导、无检测脚本）
- pan.quark.cn 桌面 UA 实测（PC 布局标题；SPA）
- 微信小程序 web-view 组件文档（__wxjs_environment 使用方）：https://developers.weixin.qq.com/miniprogram/dev/framework/ability/web-view.html

---

## 问题 6：JS 跳转逃逸的其余防线

### 结论（官方文档逐条核实）

- **`setSupportMultipleWindows(boolean)`**（API 1）：官方原文——默认 false；**设为 true 时必须实现 `WebChromeClient.onCreateWindow`**，否则新窗口请求无处落地；**多窗口禁用（默认 false）时，`window.open()` 与 `target="_blank"` 链接"被当作顶层导航，替换当前 WebView 中的页面"**——这条非常关键：它意味着按钮墙里最常见的 `target="_blank"` 跳市场链接，在默认配置下会走 shouldOverrideUrlLoading，可以被问题 2 的拦截器统一拦掉。若开启多窗口（true），新窗口 URL 改走 onCreateWindow 回调（需要你在其中自建 WebView 并把 url 递给拦截逻辑），拦截面更复杂。**对本场景建议保持默认 false，少开一条不可控通道。**
- **`setJavaScriptCanOpenWindowsAutomatically(boolean)`**（API 1）：允许 JS **无用户手势**执行 `window.open()`，默认 false（官方原文："The default is false: attempts without a user gesture will fail and do nothing"），且**该手势要求独立于 setSupportMultipleWindows 强制生效**。保持默认 false，即可天然免疫"脚本自动弹窗跳 App"。
- **onCreateWindow 的作用**：仅在 `setSupportMultipleWindows(true)` 时被回调，承载 window.open/target=_blank 的新窗口创建；本场景不开多窗口即无需实现。
- **按钮墙能否靠拦截 URL 解决**：分两类——(1) **跳转类**（`<a target=_blank>`、`location.href='market://...'`、`intent://` 自动跳转）：可以，正是问题 2 拦截器 + 默认多窗口配置的用武之地，实测百度 H5 壳的跳转就是 `location.href` 赋值，必经 shouldOverrideUrlLoading；(2) **DOM 展示类**（页面内"打开客户端"横幅、二维码引导块）：不是导航，URL 拦截无效，只能要么忽略（用户不点它就没影响），要么在 `onPageFinished` 后 `evaluateJavascript` 注入 CSS/JS 隐藏（对登录主流程通常没必要）。

**网盘场景最终防线组合**：WebViewClient 拦截（问题 2）+ intent:// fallback 解析（问题 3）+ 多窗口保持关闭 + JS 自动开窗保持关闭 + （可选）DownloadListener 处理下载类按钮（避免下载 intent 逃逸）。

### 来源

- Android 官方 WebSettings 文档（setSupportMultipleWindows / setJavaScriptCanOpenWindowsAutomatically 全部原句）：https://developer.android.com/reference/android/webkit/WebSettings
- WebChromeClient.onCreateWindow：https://developer.android.com/reference/android/webkit/WebChromeClient

---

## 综合落地清单（按优先级）

1. **buildozer.spec**：`android.add_src = java_classes/panwebview/PanWebViewClient.java`（问题 2 桥接类）；`android.add_manifest` 或 main.py 顶部设 `SDL_ANDROID_TRAP_BACK_BUTTON=1`（问题 4）。
2. **WebView 初始化**（pyjnius，主线程/UI 线程执行）：setJavaScriptEnabled(true)、setDomStorageEnabled(true)、桌面 UA（保留纯 Chrome/Windows 串，勿带 wv）、setUseWideViewPort(true)、setLoadWithOverviewMode(true)；**不调用 setSupportMultipleWindows(true)**。
3. **setWebViewClient(PanWebViewClient 桥接实例)**；handle_url 策略：http/https 放行；intent:// 走 parseUri 取 browser_fallback_url；market/tmast 等一律拦截。
4. **webview.setOnKeyListener(WebBackKeyHandler)** 关闭 WebView 层；同时在 Kivy 层保留 Window.on_keyboard 拦 27 的代码（trapBack=1 后它将真正生效）。
5. **入口 URL**：百度 `passport.baidu.com/v2/?login` 或 `pan.baidu.com/disk/home?adapt=pc&fr=ftw`；夸克 `pan.quark.cn`（桌面 UA）；123pan `www.123pan.com`（零处理）。
6. **强引用纪律**：所有 PythonJavaClass 实例（WebViewClient 回调、OnKeyListener）挂在 App/self 的属性上，防止 GC 导致回调崩溃（pyjnius 文档明确警告）。

## 局限性说明

- 夸克网盘对数据中心 IP 返回 503，其 SPA 内部检测逻辑未能完全逆向，结论基于 PC UA 页面实测与公开信息；
- StackOverflow 正文受 Cloudflare 拦截，相关引用基于 StackExchange API 元数据（标题/链接/票数），未逐字核对答案正文；
- Chromium WebView 对"shouldOverrideUrlLoading 新旧签名选择调用"的兼容策略基于 AOSP 抽象类源码与官方弃用说明的推断，未逐行核对 Chromium 侧 WebViewChromium 实现，故报告建议在 Java 桥接中双签名都覆写以消除不确定性；
- `os.environ` 方式设置 SDL hint 依赖"SDL GetHint 环境变量回落 + CPython putenv 同步"两个机制，已在 SDL 头文件注释与运行时查询语义上交叉验证，但未在真机上实测，如遇不生效可改用 manifest meta-data 方式（两者等价）。

## 参考文献

1. [Android Developers: WebViewClient](https://developer.android.com/reference/android/webkit/WebViewClient)
2. [Android Developers: WebSettings](https://developer.android.com/reference/android/webkit/WebSettings)
3. [Android Developers: Intent (parseUri / URI_INTENT_SCHEME)](https://developer.android.com/reference/android/content/Intent)
4. [Android Developers: View.OnKeyListener](https://developer.android.com/reference/android/view/View.OnKeyListener)
5. [pyjnius 官方 API 文档（api.rst）](https://github.com/kivy/pyjnius/blob/master/docs/source/api.rst)
6. [pyjnius 源码：jnius/jnius_proxy.pxi（Proxy 机制与方法表）](https://github.com/kivy/pyjnius/blob/master/jnius/jnius_proxy.pxi)
7. [python-for-android：android 模块源码 _android.pyx（无 map_key）](https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/recipes/android/src/android/_android.pyx)
8. [python-for-android：sdl2 bootstrap PythonActivity.java](https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java)
9. [python-for-android：webview bootstrap PythonActivity.java（官方 WebViewClient 参考）](https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/bootstraps/webview/build/src/main/java/org/kivy/android/PythonActivity.java)
10. [python-for-android：sdl2 bootstrap SDL 补丁目录](https://github.com/kivy/python-for-android/tree/develop/pythonforandroid/bootstraps/sdl2/build/src/patches)
11. [Kivy 2.3.0 源码：kivy/core/window/window_sdl2.py（返回键映射 27）](https://github.com/kivy/kivy/blob/2.3.0/kivy/core/window/window_sdl2.py)
12. [SDL 2.26 源码：include/SDL_hints.h（SDL_HINT_ANDROID_TRAP_BACK_BUTTON）](https://github.com/libsdl-org/SDL/blob/release-2.26.x/include/SDL_hints.h)
13. [SDL 2.26 源码：SDLActivity.java（按键分发链）](https://github.com/libsdl-org/SDL/blob/release-2.26.x/android-project/app/src/main/java/org/libsdl/app/SDLActivity.java)
14. [razzbee/kivy-android-webview（Java 桥接真机方案）](https://github.com/razzbee/kivy-android-webview)
15. [Novfensec/NfsWebview（接口桥接模式）](https://github.com/Novfensec/NfsWebview)
16. [StackOverflow: How do you call an Android app and get a result back from a web page in Chrome?（intent:// 与 browser_fallback_url）](https://stackoverflow.com/questions/34197933/how-do-you-call-an-android-app-and-get-a-result-back-from-a-web-page-in-chrome)
17. [StackOverflow: When was S.browser_fallback_url introduced in Chrome?](https://stackoverflow.com/questions/34158613/when-was-s-browser-fallback-url-introduced-in-chrome)
18. [StackOverflow: How to use correct intents for a WebView on vulnerable intent scheme hijacking](https://stackoverflow.com/questions/55352164/how-to-use-correct-intents-for-a-webview-on-vulnerable-intent-scheme-hijacking)
19. [StackOverflow: Android WebView tel: links（scheme 分流案例）](https://stackoverflow.com/questions/4338305/android-webview-tel-links-show-web-page-not-found)
20. [StackOverflow: Webview email link mailto](https://stackoverflow.com/questions/18874282/webview-email-link-mailto)
21. [微信小程序 web-view 组件文档（__wxjs_environment）](https://developers.weixin.qq.com/miniprogram/dev/framework/ability/web-view.html)
22. [百度网盘 pan.baidu.com 移动版页面脚本（本次调研实测逆向）](https://pan.baidu.com/)
23. [百度统一登录页（实测可访问）](https://passport.baidu.com/v2/?login)
24. [123 云盘官网（实测网页优先，无引导墙）](https://www.123pan.com/)
25. [夸克网盘（实测 PC 布局）](https://pan.quark.cn/)

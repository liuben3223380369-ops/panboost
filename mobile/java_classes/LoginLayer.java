package org.panboost.login;

import android.app.Activity;
import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.panboost.panwebview.PanWebViewClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 网盘登录/浏览全屏层（v3.2.2 架构：addContentView 叠加在主 Activity
 * 的 SDL surface 之上）。
 *
 * v3.2.0/v3.2.1 用独立 LoginActivity 承载登录页，真机实锤"登录完成
 * 返回后 UI 纯黑卡住"且 applog 停在"打开网页登录"（后续回调链日志
 * 全缺失）——根因是 p4a SDL2 bootstrap 在"同进程第二个 Activity
 * finish 返回"场景下，SDL/Kivy 主循环的 resume 事件不可靠，Clock
 * 永不恢复（Translucent 主题防 onStop 也救不回）。
 *
 * v3.2.2 结构性根治：登录层回到主 Activity 内（addContentView 叠加
 * View，非 Dialog 弹窗）——**主 Activity 从不退场**：
 * - 无第二个 Activity、无 finish、无 resume 竞争——SDL surface
 *   与 Kivy 主循环全程存活，回调链（on_done → Clock →
 *   _after_login）必然执行
 * - 全屏不透明 View 层盖在 SDL surface 上 = 完整的原生页面视觉
 *   （标题栏 + 提示条 + WebView + 底部大按钮），无弹窗感
 * - 手势/返回键：主入口换成自定义 PanMainActivity（extends
 *   PythonActivity，经 p4a --android-entrypoint 注册进 manifest），
 *   onBackPressed 先问本层 handleBack()——WebView 可后退先退网页，
 *   否则关层；无层时走 SDL 默认。v1.8.3 当年因 SDL trap 吞手势
 *   被迫弃用 View 层的问题，由重写主 Activity 的 onBackPressed
 *   根治
 * - 触摸不穿透：层在 SDL surface 之上，WebView 消费全部触摸
 *   （v1.8.2 已验证）
 *
 * 跨 JNI 面与 v3.2.0 相同：start(...) 一次 + 结果回调一次；其余
 * （Cookie 特征校验/多域采集/自动轮询/导航守卫/拦截回退/按钮红字）
 * 全部 Java 侧实现（从 v3.2.1 平移，编译期类型保证）。
 *
 * 一次性回调幂等保护：任何关闭路径（底部按钮/✕/返回键/渲染崩溃）
 * 只发一次结果；关闭时同步 detachWebView（Chromium GPU 资源立即
 * 释放——主 Activity 的 EGL surface 不受影响，因为 SDL surface
 * 从未销毁）。
 */
public final class LoginLayer {

    /** Python 侧结果回调（pyjnius PythonJavaClass 实现转发）。 */
    public interface Callback {
        void onLoginResult(String cookie, boolean auto);
        void onLoginCancel();
    }

    // ---- 层状态（同一时刻最多一层） ----
    private static View sRoot;
    private static WebView sWebView;
    private static TextView sBtnDone;
    private static Callback sCallback;
    private static Activity sActivity;
    private static String sLoginUrl;
    private static String[] sAuthKeys;
    private static String[] sCookieUrls;
    private static boolean sBrowse;
    private static boolean sFinished;
    private static int sSchemeHits;

    /** 导航日志（静态：层关闭后仍可取，真机诊断）。 */
    private static final List<String> sNavLog = new ArrayList<String>();

    private static final String LOGIN_TIP =
            "在下方页面登录账号，完成后点底部按钮保存 Cookie";
    private static final String BROWSE_TIP =
            "在你的网盘中浏览文件，复制文件/分享链接后点底部按钮";
    private static final String LOGIN_BTN = "✓  已完成登录，保存 Cookie";
    private static final String BROWSE_BTN = "✓  已复制链接，去下载";
    private static final String NUDGE_TXT =
            "✗ 未检测到登录凭证，完成登录后再点";

    /** 市场/商店 URL 黑名单（onPageStarted 守卫：302 落地不经过
     *  shouldOverrideUrlLoading，这里是唯一可靠拦截点）。 */
    private static final String[] MARKET_PREFIXES = {
            "market://", "https://market.android.com",
            "https://play.google.com/store",
            "https://android.myapp.com", "https://appgallery.huawei.com",
            "https://samsungapps.com", "https://app.mi.com",
            "https://www.coolapk.com"};

    /** scheme/市场跳转被拦 2 次后的说明页（替代空白屏）。 */
    private static final String BLOCKED_HTML =
            "<html><head><meta charset=\"utf-8\">"
            + "<meta name=\"viewport\" content=\"width=device-width,"
            + "initial-scale=1\"></head>"
            + "<body style=\"font-family:sans-serif;padding:24px;"
            + "background:#fff;color:#334155\">"
            + "<h2>已阻止跳转到网盘客户端</h2>"
            + "<p>该网盘页面试图打开 App 或应用市场，PanBoost 已在网页内拦截。</p>"
            + "<p>若登录页无法正常显示：请点左上角 ✕ 返回，到「账号」页"
            + "选择该网盘对应域名，在浏览器登录后粘贴 Cookie 保存即可。</p>"
            + "</body></html>";

    private LoginLayer() {
    }

    /**
     * 打开登录/浏览层（Python 侧唯一入口）。
     *
     * 全参数 String/boolean——单一静态方法无重载歧义，pyjnius 解析
     * 失败在调用点同步抛出（fire-and-forget 根治）。
     *
     * @param act 主 Activity（PanMainActivity/PythonActivity 实例）
     * @param url 登录页/文件页 URL
     * @param title 网盘名（标题栏显示）
     * @param authKeysCsv 登录特征 Cookie 键（逗号分隔，空=免校验）
     * @param cookieUrlsCsv 额外 Cookie 采集域 URL（逗号分隔）
     * @param ua WebView UA（桌面 UA，防移动 UA 被跳"下载App"页）
     * @param browse true=浏览模式（底部按钮"去下载"，不校验凭证）
     * @param cb 结果回调（onLoginResult / onLoginCancel，UI 线程）
     */
    public static void start(final Activity act, final String url,
                             final String title, final String authKeysCsv,
                             final String cookieUrlsCsv, final String ua,
                             final boolean browse, final Callback cb) {
        if (act == null || url == null || url.length() == 0) {
            throw new IllegalArgumentException("login layer: no activity/url");
        }
        // v3.2.3：全部构建必须发生在 UI 线程——pyjnius 静态方法从
        // Kivy 的 SDL 线程直接调用，v3.2.2 在 SDL 线程构建视图 +
        // addContentView + 构造消息调度器（读主循环内部队列），
        // 真机（部分 ROM 上从 SDL 线程取主循环得 null）在调度器
        // 构造里 NPE 崩溃（队列字段空引用）。runOnUiThread 回调在
        // UI 线程执行时主循环必然存活（UI 框架本身在跑）；构建
        // 失败经 onLoginCancel 通知，Python 状态机不悬空
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    startOnUiThread(act, url, title, authKeysCsv,
                                    cookieUrlsCsv, ua, browse, cb);
                } catch (Throwable t) {
                    log("open", "build-fail|" + t);
                    if (cb != null) {
                        try {
                            cb.onLoginCancel();
                        } catch (Throwable ignored) {
                        }
                    }
                }
            }
        });
    }

    /** 实际构建（仅 UI 线程调用；参数已由 start 校验）。 */
    private static void startOnUiThread(Activity act, String url,
                                        String title, String authKeysCsv,
                                        String cookieUrlsCsv, String ua,
                                        boolean browse, Callback cb) {
        if (sRoot != null) {
            // 已有层：先按取消关闭（同线程同步），再开新层
            closeOnUiThread(true);
        }
        sActivity = act;
        sCallback = cb;
        sLoginUrl = url;
        sAuthKeys = splitCsv(authKeysCsv);
        sCookieUrls = splitCsv(cookieUrlsCsv);
        sBrowse = browse;
        sFinished = false;
        sSchemeHits = 0;
        log("open", (browse ? "browse|" : "login|") + url);
        View root = buildViews(act, ua, title);
        act.addContentView(root, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        sRoot = root;
    }

    /**
     * 返回键/手势入口（PanMainActivity.onBackPressed 转发）。
     *
     * 层开着：WebView 可后退先退网页，否则按取消关闭；返回 true
     * 表示已消费。层没开：返回 false（走 SDL 默认行为）。
     */
    public static boolean handleBack(Activity act) {
        if (sRoot == null || sWebView == null) {
            return false;
        }
        if (sWebView.canGoBack()) {
            try {
                sWebView.goBack();
            } catch (Throwable ignored) {
            }
            return true;
        }
        closeLayer(true);
        return true;
    }

    /** Python 侧主动关闭（close_login/request_back 兼容路径）。 */
    public static void closeLayer() {
        closeLayer(true);
    }

    /** 层是否开着。 */
    public static boolean isOpen() {
        return sRoot != null;
    }

    /** 导航日志快照（"kind|epochMillis|msg" 数组）。 */
    public static String[] dumpNavLog() {
        synchronized (sNavLog) {
            return sNavLog.toArray(new String[0]);
        }
    }

    public static void clearNavLog() {
        synchronized (sNavLog) {
            sNavLog.clear();
        }
    }

    private static void log(String kind, String msg) {
        synchronized (sNavLog) {
            sNavLog.add(kind + "|" + System.currentTimeMillis()
                    + "|" + (msg == null ? "" : msg));
            int overflow = sNavLog.size() - 80;
            if (overflow > 0) {
                sNavLog.subList(0, overflow).clear();
            }
        }
    }

    /** 标题栏（✕ + 网盘名）+ 黄色提示条 + WebView + 底部大按钮。 */
    private static View buildViews(final Activity act, String ua,
                                   String title) {
        float d = act.getResources().getDisplayMetrics().density;
        int pxBar = (int) (48 * d);
        int pxBtn = (int) (52 * d);
        int pxEdge = (int) (56 * d);

        LinearLayout root = new LinearLayout(act);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFFF1F5F9);

        LinearLayout bar = new LinearLayout(act);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setBackgroundColor(0xFF0F172A);

        TextView tvClose = new TextView(act);
        tvClose.setText("✕");
        tvClose.setTextColor(0xFFFFFFFF);
        tvClose.setTextSize(22);
        tvClose.setGravity(Gravity.CENTER);
        tvClose.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                closeLayer(true);
            }
        });
        bar.addView(tvClose, new LinearLayout.LayoutParams(pxEdge, pxBar));

        TextView tvTitle = new TextView(act);
        tvTitle.setText((title == null || title.length() == 0
                ? "网盘" : title)
                + (sBrowse ? " · 我的网盘" : " · 网页登录"));
        tvTitle.setTextColor(0xFFFFFFFF);
        tvTitle.setTextSize(18);
        tvTitle.setGravity(Gravity.CENTER);
        bar.addView(tvTitle, new LinearLayout.LayoutParams(0, pxBar, 1f));

        TextView spacer = new TextView(act);
        bar.addView(spacer, new LinearLayout.LayoutParams(pxEdge, pxBar));

        root.addView(bar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, pxBar));

        TextView tvTip = new TextView(act);
        tvTip.setText(sBrowse ? BROWSE_TIP : LOGIN_TIP);
        tvTip.setBackgroundColor(0xFFFEF3C7);
        tvTip.setTextColor(0xFF92400E);
        tvTip.setTextSize(13);
        tvTip.setGravity(Gravity.CENTER);
        tvTip.setPadding(0, (int) (8 * d), 0, (int) (8 * d));
        root.addView(tvTip, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        WebView wv = new WebView(act);
        wv.setBackgroundColor(0xFFFFFFFF);
        WebSettings s = wv.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        if (ua != null && ua.length() > 0) {
            s.setUserAgentString(ua);
            boolean ok = ua.equals(s.getUserAgentString());
            log("ua", ok ? "desktop-ok" : "desktop-fail");
        }
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        try {
            cm.setAcceptThirdPartyCookies(wv, true);
        } catch (Throwable ignored) {
        }
        wv.setWebViewClient(new PanWebViewClient(sBridge));
        root.addView(wv, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        sWebView = wv;

        TextView btnDone = new TextView(act);
        btnDone.setText(sBrowse ? BROWSE_BTN : LOGIN_BTN);
        btnDone.setTextColor(0xFFFFFFFF);
        btnDone.setTextSize(17);
        btnDone.setGravity(Gravity.CENTER);
        btnDone.setBackgroundColor(0xFF2563EB);
        btnDone.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                onDoneClicked(act);
            }
        });
        root.addView(btnDone, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, pxBtn));
        sBtnDone = btnDone;

        wv.loadUrl(sLoginUrl);
        startPolling();
        return root;
    }

    /** 底部按钮：多域采集 Cookie → 特征校验 → 通过则回调关闭。 */
    private static void onDoneClicked(Activity act) {
        if (sFinished) {
            return;
        }
        String c = gatherCookies();
        if (!sBrowse && sAuthKeys.length > 0 && !checkAuth(c, sAuthKeys)) {
            log("check", "auth-fail");
            nudgeButton(act);
            toast(act, "未检测到登录凭证，请先在页面完成登录");
            return;
        }
        notifyResult(c, false);
    }

    /** 幂等结果通知：只发一次；回调异常吞掉（结果已保 Cookie）。 */
    private static void notifyResult(String cookie, boolean auto) {
        if (sFinished) {
            return;
        }
        sFinished = true;
        log("result", (auto ? "auto|" : "manual|")
                + (cookie == null ? "" : String.valueOf(cookie.length())));
        Callback cb = sCallback;
        sCallback = null;
        // 先关层（含 WebView 释放）再回调——回调进 Python 时层已
        // 完全退场，Kivy 侧界面操作（_after_login）立即安全执行
        closeLayer(false);
        if (cb != null) {
            try {
                cb.onLoginResult(cookie == null ? "" : cookie, auto);
            } catch (Throwable t) {
                log("cberr", String.valueOf(t));
            }
        }
    }

    /** 幂等取消通知（✕/返回键/渲染崩溃）。 */
    private static void notifyCancel() {
        if (sFinished) {
            return;
        }
        sFinished = true;
        log("result", "cancel");
        Callback cb = sCallback;
        sCallback = null;
        closeLayer(false);
        if (cb != null) {
            try {
                cb.onLoginCancel();
            } catch (Throwable t) {
                log("cberr", String.valueOf(t));
            }
        }
    }

    /**
     * 关闭层（同步 detach WebView 清理序列）。
     *
     * notify 参数：true=作为"取消"通知回调（✕/返回键路径由调用方
     * 决定）；内部清理一致。经典序列：stopLoading → about:blank →
     * removeView → destroy。主 Activity 的 EGL surface 从未销毁
     * （View 叠加不触发生命周期事件），Chromium 释放无竞争。
     */
    private static void closeLayer(boolean notify) {
        // v3.2.3：removeView 与 WebView 销毁一律 UI 线程
        //（runOnUiThread 在 UI 线程被调时同步执行，其余线程 post）
        final Activity act = sActivity;
        final boolean n = notify;
        final Runnable task = new Runnable() {
            @Override
            public void run() {
                closeOnUiThread(n);
            }
        };
        if (act != null) {
            act.runOnUiThread(task);
        } else {
            task.run();
        }
    }

    /** 实际关闭（仅 UI 线程调用；幂等由 sRoot 判空保证）。 */
    private static void closeOnUiThread(boolean notify) {
        if (sRoot == null) {
            return;
        }
        stopPolling();
        Activity act = sActivity;
        View root = sRoot;
        WebView wv = sWebView;
        sRoot = null;
        sWebView = null;
        sBtnDone = null;
        sActivity = null;
        try {
            if (wv != null) {
                wv.stopLoading();
                wv.loadUrl("about:blank");
                wv.setWebViewClient(null);
                ViewGroup parent = (ViewGroup) wv.getParent();
                if (parent != null) {
                    parent.removeView(wv);
                }
            }
        } catch (Throwable t) {
            log("detach", String.valueOf(t));
        }
        try {
            ViewGroup rp = (ViewGroup) root.getParent();
            if (rp != null) {
                rp.removeView(root);
            }
        } catch (Throwable ignored) {
        }
        try {
            if (wv != null) {
                wv.destroy();
            }
        } catch (Throwable ignored) {
        }
        if (notify && !sFinished) {
            sFinished = true;
            log("result", "cancel-close");
            Callback cb = sCallback;
            sCallback = null;
            if (cb != null) {
                try {
                    cb.onLoginCancel();
                } catch (Throwable t) {
                    log("cberr", String.valueOf(t));
                }
            }
        }
        if (act != null) {
            try {
                CookieManager.getInstance().flush();
            } catch (Throwable ignored) {
            }
        }
    }

    // ---- PanWebViewClient.UrlLoadingCallback（纯 Java，无跨 JNI）----

    private static final PanWebViewClient.UrlLoadingCallback sBridge =
            new PanWebViewClient.UrlLoadingCallback() {

        @Override
        public boolean onUrlLoading(String url) {
            if (url == null) {
                return true;
            }
            String u = url.trim();
            if (u.startsWith("http://") || u.startsWith("https://")) {
                return false;
            }
            log("block", u);
            if (u.startsWith("intent://")) {
                String fb = parseIntentFallback(u);
                if (fb != null && sWebView != null) {
                    try {
                        sWebView.loadUrl(fb);
                    } catch (Throwable ignored) {
                    }
                    return true;
                }
            }
            fallbackAfterBlock();
            return true;
        }

        @Override
        public void onPageStarted(String url) {
            log("start", url);
            if (url != null && sWebView != null) {
                String lu = url.toLowerCase(Locale.US);
                for (String p : MARKET_PREFIXES) {
                    if (lu.startsWith(p)) {
                        try {
                            sWebView.stopLoading();
                        } catch (Throwable ignored) {
                        }
                        log("block", "market|" + url);
                        fallbackAfterBlock();
                        break;
                    }
                }
            }
        }

        @Override
        public void onPageFinished(String url) {
            log("done", url);
        }

        @Override
        public void onRenderGone() {
            log("crash", "render-process-gone");
            notifyCancel();
        }
    };

    /** intent:// 的 browser_fallback_url（Chrome 标准约定）；加固：
     *  BROWSABLE category + 清 component/selector（防 scheme 劫持）。 */
    private static String parseIntentFallback(String uri) {
        try {
            android.content.Intent it = android.content.Intent.parseUri(
                    uri, android.content.Intent.URI_INTENT_SCHEME);
            it.addCategory(android.content.Intent.CATEGORY_BROWSABLE);
            it.setComponent(null);
            it.setSelector(null);
            String fb = it.getStringExtra("browser_fallback_url");
            if (fb == null) {
                return null;
            }
            fb = fb.trim();
            if (fb.startsWith("http://") || fb.startsWith("https://")) {
                return fb;
            }
        } catch (Throwable ignored) {
        }
        return null;
    }

    /** 拦截回退：重载登录页（最多 2 次防 302 循环），仍被拦则说明页。 */
    private static void fallbackAfterBlock() {
        WebView wv = sWebView;
        if (wv == null) {
            return;
        }
        try {
            if (sSchemeHits < 2) {
                sSchemeHits++;
                wv.loadUrl(sLoginUrl);
            } else {
                wv.loadData(BLOCKED_HTML, "text/html", "utf-8");
            }
        } catch (Throwable ignored) {
        }
    }

    // ---- Cookie 采集与校验（Java 侧完整实现）----

    /** 多域采集合并（cookieUrls + 登录页域；同键后值覆盖=登录页优先）。 */
    private static String gatherCookies() {
        CookieManager cm = CookieManager.getInstance();
        LinkedHashMap<String, String> merged =
                new LinkedHashMap<String, String>();
        try {
            cm.flush();
        } catch (Throwable ignored) {
        }
        String[] urls = new String[sCookieUrls.length + 1];
        System.arraycopy(sCookieUrls, 0, urls, 0, sCookieUrls.length);
        urls[sCookieUrls.length] = sLoginUrl;
        for (String u : urls) {
            if (u == null || u.length() == 0) {
                continue;
            }
            String c;
            try {
                c = cm.getCookie(u);
            } catch (Throwable t) {
                log("ckerr", u + "|" + t);
                continue;
            }
            if (c == null || c.length() == 0) {
                continue;
            }
            for (String kv : c.split(";")) {
                int eq = kv.indexOf('=');
                if (eq <= 0) {
                    continue;
                }
                merged.put(kv.substring(0, eq).trim(),
                        kv.substring(eq + 1).trim());
            }
        }
        if (merged.isEmpty()) {
            return null;
        }
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : merged.entrySet()) {
            if (sb.length() > 0) {
                sb.append("; ");
            }
            sb.append(e.getKey()).append('=').append(e.getValue());
        }
        return sb.toString();
    }

    /** 特征凭证校验：auth_keys 全部命中（大小写不敏感）才算登录。 */
    private static boolean checkAuth(String cookie, String[] keys) {
        if (cookie == null || cookie.length() == 0) {
            return false;
        }
        String lc = cookie.toLowerCase(Locale.US);
        for (String k : keys) {
            String kk = k.toLowerCase(Locale.US).trim();
            if (kk.length() == 0) {
                continue;
            }
            if (!lc.contains(kk + "=")) {
                return false;
            }
        }
        return true;
    }

    // ---- 特征 Cookie 自动检测轮询（View.postDelayed，首轮 3s）----

    private static final Runnable sPollRunnable = new Runnable() {
        @Override
        public void run() {
            if (sFinished || sBrowse || sAuthKeys.length == 0) {
                return;
            }
            String c = gatherCookies();
            if (checkAuth(c, sAuthKeys)) {
                notifyResult(c, true);
                return;
            }
            WebView wv = sWebView;
            if (wv != null) {
                wv.postDelayed(this, 1200);
            }
        }
    };

    private static void startPolling() {
        // 首轮 3s：页面启动渲染窗口与"特征命中秒关层"绝不竞争
        //（v2.1.0 教训）。v3.2.3：View.postDelayed 挂到已 attach 的
        // View 上，由 UI 框架内部的调度通道执行——不再自建调度
        // 器，规避 ROM 上主循环取空返回的崩溃路径
        WebView wv = sWebView;
        if (!sBrowse && sAuthKeys.length > 0 && wv != null) {
            wv.removeCallbacks(sPollRunnable);
            wv.postDelayed(sPollRunnable, 3000);
        }
    }

    private static void stopPolling() {
        WebView wv = sWebView;
        if (wv != null) {
            wv.removeCallbacks(sPollRunnable);
        }
    }

    // ---- 校验失败反馈（按钮红字 3s + Toast 双保险）----

    private static void nudgeButton(Activity act) {
        final TextView btn = sBtnDone;
        if (btn == null) {
            return;
        }
        final CharSequence old = btn.getText();
        btn.setText(NUDGE_TXT);
        btn.setTextColor(0xFFDC2626);
        btn.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (sFinished || btn != sBtnDone || sBtnDone == null) {
                    return;
                }
                sBtnDone.setText(old);
                sBtnDone.setTextColor(0xFFFFFFFF);
            }
        }, 3000);
    }

    private static void toast(Context ctx, String msg) {
        try {
            Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show();
        } catch (Throwable ignored) {
        }
    }

    private static String[] splitCsv(String s) {
        if (s == null) {
            return new String[0];
        }
        s = s.trim();
        if (s.length() == 0) {
            return new String[0];
        }
        return s.split(",");
    }
}

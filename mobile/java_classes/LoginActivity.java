package org.panboost.login;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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
 * 网盘登录/浏览独立页面（v3.2.0 重构核心，替代 v1.8~v3.1 的
 * android.app.Dialog 弹窗承载方案）。
 *
 * 真机反馈"登录页不能展示信息"（层完全不出现 / WebView 区空白）
 * 的根治：登录层从 Dialog 改为系统级全屏 Activity——窗口显示、
 * 焦点、生命周期由系统窗口管理器保证，不再依赖 Dialog 的 show
 * 时序、主题 wrap 行为与 PhoneWindow 测量竞争（v1.8.4 起三族
 * 真机问题的共同根源一次性消除）。
 *
 * 架构收益：
 * - 本页在前台时 Kivy 宿主整体 onPause：SDL 渲染/触摸/返回键
 *   trap 全部不再竞争（此前 Dialog 方案下三层混战）
 * - WebView 的导航守卫/渲染崩溃/返回键全部留在 Java 侧（编译期
 *   类型检查），无跨 JNI 回调延迟与 GC 窗口；文字/颜色 Java 直
 *   设置（Python 侧 setText 多重载解析失败的"无字色块"不复存在）
 * - 返回键/手势走 onBackPressed 系统标准路径（canGoBack 先退
 *   网页再退出），彻底摆脱 SDL trap
 *
 * 跨 JNI 面只剩两处（pyjnius 静默失败风险整体消除）：
 * 1. start(Context, ...) 静态启动方法——全参数 java.lang.String/
 *    boolean，单一方法无重载歧义，失败同步抛给 Python
 * 2. Callback.onLoginResult/onLoginCancel 结果回调——一次性，
 *    Python 侧 PythonJavaClass 强引用存 _STATE（weblogin），
 *    用后置 sCallback=null + Python 侧退休列表双端防 GC
 *
 * 生命周期安全（幂等通知）：任何退出路径（完成按钮/自动检测/
 * ✕/返回键/系统回收渲染崩溃）只发一次结果；onDestroy 兜底发
 * cancel——Python 状态机绝不悬空等待。
 *
 * 通过 buildozer.spec android.add_src 编进 APK、
 * android.add_activities 注册进 manifest（p4a --add-activity）。
 */
public class LoginActivity extends Activity
        implements PanWebViewClient.UrlLoadingCallback {

    /** Python 侧结果回调（pyjnius PythonJavaClass 实现转发）。 */
    public interface Callback {
        void onLoginResult(String cookie, boolean auto);
        void onLoginCancel();
    }

    /** 启动前置的回调（Java 静态字段持引用；Python 侧同步持强
     *  引用并在结果后退休——双端防 GC，v1.8.4 教训）。 */
    public static Callback sCallback;
    /** 当前存活实例（finishSelf 用；防叠兜底）。 */
    public static LoginActivity sInstance;
    /** 导航日志（静态：页面销毁后仍可取，真机诊断）。 */
    private static final List<String> sNavLog = new ArrayList<String>();

    private static final String X_URL = "panboost.url";
    private static final String X_TITLE = "panboost.title";
    private static final String X_KEYS = "panboost.keys";
    private static final String X_CKS = "panboost.cks";
    private static final String X_UA = "panboost.ua";
    private static final String X_BROWSE = "panboost.browse";

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

    private WebView wv;
    private TextView btnDone;
    private String loginUrl;
    private String title;
    private String[] authKeys;
    private String[] cookieUrls;
    private String ua;
    private boolean browse;
    private boolean finished;
    private Handler handler;
    private int schemeHits;

    /**
     * 启动登录/浏览页（Python 侧唯一入口）。
     *
     * 全参数 String/boolean——单一静态方法无重载歧义，pyjnius
     * 解析失败在调用点同步抛出（fire-and-forget 根治，v1.7.0 教训）。
     *
     * @param ctx 宿主 Activity（PythonActivity）
     * @param url 登录页/文件页 URL
     * @param title 网盘名（标题栏显示）
     * @param authKeysCsv 登录特征 Cookie 键（逗号分隔，空=免校验）
     * @param cookieUrlsCsv 额外 Cookie 采集域 URL（逗号分隔）
     * @param ua WebView UA（桌面 UA，防移动 UA 被跳"下载App"页）
     * @param browse true=浏览模式（底部按钮"去下载"，不校验凭证）
     * @param cb 结果回调（onLoginResult / onLoginCancel）
     */
    public static void start(Context ctx, String url, String title,
                             String authKeysCsv, String cookieUrlsCsv,
                             String ua, boolean browse, Callback cb) {
        sCallback = cb;
        Intent i = new Intent(ctx, LoginActivity.class);
        i.putExtra(X_URL, url);
        i.putExtra(X_TITLE, title == null ? "" : title);
        i.putExtra(X_KEYS, authKeysCsv == null ? "" : authKeysCsv);
        i.putExtra(X_CKS, cookieUrlsCsv == null ? "" : cookieUrlsCsv);
        i.putExtra(X_UA, ua == null ? "" : ua);
        i.putExtra(X_BROWSE, browse);
        ctx.startActivity(i);
    }

    /** Python 侧主动关闭（close_login/request_back 兼容路径）。 */
    public static void finishSelf() {
        LoginActivity a = sInstance;
        if (a != null) {
            a.finished = true;
            a.finish();
        }
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

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (sInstance != null && !sInstance.isFinishing()) {
            // 防叠兜底（launchMode 默认 standard；Python 侧单实例
            // 闸已挡，这里 Java 侧再兜一层）
            log("open", "duplicate-finish");
            finished = true;
            finish();
            return;
        }
        sInstance = this;
        Intent i = getIntent();
        loginUrl = i.getStringExtra(X_URL);
        title = i.getStringExtra(X_TITLE);
        authKeys = splitCsv(i.getStringExtra(X_KEYS));
        cookieUrls = splitCsv(i.getStringExtra(X_CKS));
        ua = i.getStringExtra(X_UA);
        browse = i.getBooleanExtra(X_BROWSE, false);
        finished = false;
        schemeHits = 0;
        handler = new Handler(Looper.getMainLooper());
        log("open", (browse ? "browse|" : "login|") + loginUrl);
        if (loginUrl == null || loginUrl.length() == 0) {
            log("open", "no-url-finish");
            notifyCancel();
            return;
        }
        setContentView(buildViews());
    }

    /** 标题栏（✕ + 网盘名）+ 黄色提示条 + WebView + 底部大按钮。 */
    private View buildViews() {
        float d = getResources().getDisplayMetrics().density;
        int pxBar = (int) (48 * d);
        int pxBtn = (int) (52 * d);
        int pxEdge = (int) (56 * d);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFFF1F5F9);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setBackgroundColor(0xFF0F172A);

        TextView tvClose = new TextView(this);
        tvClose.setText("✕");
        tvClose.setTextColor(0xFFFFFFFF);
        tvClose.setTextSize(22);
        tvClose.setGravity(Gravity.CENTER);
        tvClose.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                notifyCancel();
            }
        });
        bar.addView(tvClose, new LinearLayout.LayoutParams(pxEdge, pxBar));

        TextView tvTitle = new TextView(this);
        tvTitle.setText((title == null || title.length() == 0
                ? "网盘" : title)
                + (browse ? " · 我的网盘" : " · 网页登录"));
        tvTitle.setTextColor(0xFFFFFFFF);
        tvTitle.setTextSize(18);
        tvTitle.setGravity(Gravity.CENTER);
        bar.addView(tvTitle, new LinearLayout.LayoutParams(0, pxBar, 1f));

        TextView spacer = new TextView(this);
        bar.addView(spacer, new LinearLayout.LayoutParams(pxEdge, pxBar));

        root.addView(bar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, pxBar));

        TextView tvTip = new TextView(this);
        tvTip.setText(browse ? BROWSE_TIP : LOGIN_TIP);
        tvTip.setBackgroundColor(0xFFFEF3C7);
        tvTip.setTextColor(0xFF92400E);
        tvTip.setTextSize(13);
        tvTip.setGravity(Gravity.CENTER);
        tvTip.setPadding(0, (int) (8 * d), 0, (int) (8 * d));
        root.addView(tvTip, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        wv = new WebView(this);
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
        wv.setWebViewClient(new PanWebViewClient(this));
        root.addView(wv, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        btnDone = new TextView(this);
        btnDone.setText(browse ? BROWSE_BTN : LOGIN_BTN);
        btnDone.setTextColor(0xFFFFFFFF);
        btnDone.setTextSize(17);
        btnDone.setGravity(Gravity.CENTER);
        btnDone.setBackgroundColor(0xFF2563EB);
        btnDone.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                onDoneClicked();
            }
        });
        root.addView(btnDone, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, pxBtn));

        wv.loadUrl(loginUrl);
        return root;
    }

    /** 底部按钮：多域采集 Cookie → 特征校验 → 通过则回传退出。 */
    private void onDoneClicked() {
        if (finished || isFinishing()) {
            return;
        }
        String c = gatherCookies();
        if (!browse && authKeys.length > 0 && !checkAuth(c, authKeys)) {
            log("check", "auth-fail");
            nudgeButton();
            toast("未检测到登录凭证，请先在页面完成登录");
            return;
        }
        notifyResult(c, false);
    }

    /** 幂等结果通知：只发一次；回调异常吞掉（结果已保 Cookie）。 */
    private void notifyResult(String cookie, boolean auto) {
        if (finished || isFinishing()) {
            return;
        }
        finished = true;
        log("result", (auto ? "auto|" : "manual|")
                + (cookie == null ? "" : String.valueOf(cookie.length())));
        Callback cb = sCallback;
        sCallback = null;
        if (cb != null) {
            try {
                cb.onLoginResult(cookie == null ? "" : cookie, auto);
            } catch (Throwable t) {
                log("cberr", String.valueOf(t));
            }
        }
        finish();
    }

    /** 幂等取消通知（✕/返回键/渲染崩溃/系统回收兜底）。 */
    private void notifyCancel() {
        if (finished || isFinishing()) {
            return;
        }
        finished = true;
        log("result", "cancel");
        Callback cb = sCallback;
        sCallback = null;
        if (cb != null) {
            try {
                cb.onLoginCancel();
            } catch (Throwable t) {
                log("cberr", String.valueOf(t));
            }
        }
        finish();
    }

    /** 返回键/手势（Activity 系统标准路径）：网页可后退先退网页。 */
    @Override
    public void onBackPressed() {
        if (wv != null && wv.canGoBack()) {
            wv.goBack();
            return;
        }
        notifyCancel();
    }

    // ---- PanWebViewClient.UrlLoadingCallback（纯 Java，无跨 JNI）----

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
            if (fb != null) {
                if (wv != null) {
                    try {
                        wv.loadUrl(fb);
                    } catch (Throwable ignored) {
                    }
                }
                return true;
            }
        }
        fallbackAfterBlock();
        return true;
    }

    /** intent:// 的 browser_fallback_url（Chrome 标准约定）；加固：
     *  BROWSABLE category + 清 component/selector（防 scheme 劫持）。 */
    private String parseIntentFallback(String uri) {
        try {
            Intent it = Intent.parseUri(uri, Intent.URI_INTENT_SCHEME);
            it.addCategory(Intent.CATEGORY_BROWSABLE);
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
    private void fallbackAfterBlock() {
        if (wv == null) {
            return;
        }
        try {
            if (schemeHits < 2) {
                schemeHits++;
                wv.loadUrl(loginUrl);
            } else {
                wv.loadData(BLOCKED_HTML, "text/html", "utf-8");
            }
        } catch (Throwable ignored) {
        }
    }

    @Override
    public void onPageStarted(String url) {
        log("start", url);
        if (url != null && wv != null) {
            String lu = url.toLowerCase(Locale.US);
            for (String p : MARKET_PREFIXES) {
                if (lu.startsWith(p)) {
                    try {
                        wv.stopLoading();
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

    // ---- Cookie 采集与校验（Java 侧完整实现，与 weblogin.py 纯函数同规格）----

    /** 多域采集合并（cookieUrls + 登录页域；同键后值覆盖=登录页优先）。 */
    private String gatherCookies() {
        CookieManager cm = CookieManager.getInstance();
        LinkedHashMap<String, String> merged =
                new LinkedHashMap<String, String>();
        try {
            cm.flush();
        } catch (Throwable ignored) {
        }
        String[] urls = new String[cookieUrls.length + 1];
        System.arraycopy(cookieUrls, 0, urls, 0, cookieUrls.length);
        urls[cookieUrls.length] = loginUrl;
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
    private boolean checkAuth(String cookie, String[] keys) {
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

    // ---- 特征 Cookie 自动检测轮询（Handler 主线程，首轮 3s）----

    private final Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (finished || isFinishing() || browse) {
                return;
            }
            if (authKeys.length > 0) {
                String c = gatherCookies();
                if (checkAuth(c, authKeys)) {
                    notifyResult(c, true);
                    return;
                }
            }
            if (handler != null) {
                handler.postDelayed(this, 1200);
            }
        }
    };

    @Override
    protected void onResume() {
        super.onResume();
        // 首轮 3s：页面启动渲染窗口与"特征命中秒关页"绝不竞争
        //（v2.1.0 教训：dismiss 与 Chromium 启动渲染竞争即闪退）
        if (!browse && authKeys.length > 0 && handler != null) {
            handler.removeCallbacks(pollRunnable);
            handler.postDelayed(pollRunnable, 3000);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (handler != null) {
            handler.removeCallbacks(pollRunnable);
        }
        try {
            CookieManager.getInstance().flush();
        } catch (Throwable ignored) {
        }
    }

    @Override
    protected void onDestroy() {
        if (!finished) {
            // 兜底：系统回收/异常退出路径也发取消——Python 状态机
            // 绝不悬空等待（幂等：notifyCancel 自查 finished）
            notifyCancel();
        }
        if (sInstance == this) {
            sInstance = null;
        }
        if (wv != null) {
            try {
                wv.destroy();
            } catch (Throwable ignored) {
            }
            wv = null;
        }
        handler = null;
        super.onDestroy();
    }

    // ---- 校验失败反馈（按钮红字 3s + Toast 双保险）----

    private void nudgeButton() {
        if (btnDone == null || handler == null) {
            return;
        }
        final TextView btn = btnDone;
        final CharSequence old = btn.getText();
        btn.setText(NUDGE_TXT);
        btn.setTextColor(0xFFDC2626);
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (finished || isFinishing() || btn != btnDone) {
                    return;
                }
                btnDone.setText(old);
                btnDone.setTextColor(0xFFFFFFFF);
            }
        }, 3000);
    }

    private void toast(String msg) {
        try {
            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
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

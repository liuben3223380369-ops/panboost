package org.panboost.panwebview;

import android.graphics.Bitmap;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebView;
import android.webkit.WebResourceRequest;
import android.webkit.WebViewClient;

/**
 * WebViewClient Java 桥接类（v1.8.4）。
 *
 * pyjnius 的 PythonJavaClass 基于 java.lang.reflect.Proxy，只能实现
 * 接口、不能继承 WebViewClient 抽象类——所以用本桥接类 extends
 * WebViewClient，把回调转发给自定义接口 UrlLoadingCallback（Python
 * 侧用 PythonJavaClass 实现该接口）。
 *
 * 通过 buildozer.spec 的 android.add_src 编进 APK（官方机制，无需
 * 改 p4a 本体）。两个重载签名都覆写：API 24+ 走 WebResourceRequest
 * 版，旧设备走 String 版。
 *
 * v1.8.3 新增 onPageStarted / onPageFinished 转发：
 * shouldOverrideUrlLoading 对服务端 302 重定向与 POST 导航无效
 * （Android 官方文档明确）——网盘 H5 壳"跳下载App"很多正是 302
 * 落地，必须 onPageStarted（一切导航必经点，含 302 落地）做守卫。
 *
 * v1.8.4 新增 onRenderProcessGone 转发：WebView 渲染进程崩溃时
 * 若不处理（返回 false 或不覆写），系统默认杀掉整个宿主 App
 * （真机闪退路径之一）——覆写并返回 true 表示应用自行处理，
 * Python 侧记日志并自动关闭登录层。
 */
public class PanWebViewClient extends WebViewClient {

    /**
     * Python 侧回调接口。
     * onUrlLoading: 返回 true 表示拦截（不加载），false 放行。
     * onPageStarted / onPageFinished: 导航观测（日志 + 守卫）。
     * onRenderGone: WebView 渲染进程崩溃（v1.8.4 防杀加固）。
     */
    public interface UrlLoadingCallback {
        boolean onUrlLoading(String url);
        void onPageStarted(String url);
        void onPageFinished(String url);
        void onRenderGone();
    }

    private final UrlLoadingCallback cb;

    public PanWebViewClient(UrlLoadingCallback cb) {
        super();
        this.cb = cb;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
        return cb.onUrlLoading(url);
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view,
                                            WebResourceRequest request) {
        return cb.onUrlLoading(request.getUrl().toString());
    }

    @Override
    public void onPageStarted(WebView view, String url, Bitmap favicon) {
        cb.onPageStarted(url);
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        cb.onPageFinished(url);
    }

    @Override
    public boolean onRenderProcessGone(WebView view,
                                       RenderProcessGoneDetail detail) {
        // 返回 true 表示应用自行处理（不处理时系统默认杀整个 App）。
        // Python 侧回调异常也绝不让它漏出去杀 App。
        try {
            cb.onRenderGone();
        } catch (Throwable t) {
            // 吞掉：保住宿主进程优先
        }
        return true;
    }
}

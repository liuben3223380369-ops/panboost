package org.panboost.panwebview;

import android.graphics.Bitmap;
import android.webkit.WebView;
import android.webkit.WebResourceRequest;
import android.webkit.WebViewClient;

/**
 * WebViewClient Java 桥接类（v1.8.3）。
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
 */
public class PanWebViewClient extends WebViewClient {

    /**
     * Python 侧回调接口。
     * onUrlLoading: 返回 true 表示拦截（不加载），false 放行。
     * onPageStarted / onPageFinished: 导航观测（日志 + 守卫）。
     */
    public interface UrlLoadingCallback {
        boolean onUrlLoading(String url);
        void onPageStarted(String url);
        void onPageFinished(String url);
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
}

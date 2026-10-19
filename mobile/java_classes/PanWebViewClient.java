package org.panboost.panwebview;

import android.webkit.WebView;
import android.webkit.WebResourceRequest;
import android.webkit.WebViewClient;

/**
 * WebViewClient Java 桥接类（v1.8.2）。
 *
 * pyjnius 的 PythonJavaClass 基于 java.lang.reflect.Proxy，只能实现
 * 接口、不能继承 WebViewClient 抽象类——所以用本桥接类 extends
 * WebViewClient，把 shouldOverrideUrlLoading 转发给自定义接口
 * UrlLoadingCallback（Python 侧用 PythonJavaClass 实现该接口）。
 *
 * 通过 buildozer.spec 的 android.add_src 编进 APK（官方机制，无需
 * 改 p4a 本体）。两个重载签名都覆写：API 24+ 走 WebResourceRequest
 * 版，旧设备走 String 版。
 */
public class PanWebViewClient extends WebViewClient {

    /** Python 侧回调接口：返回 true 表示拦截（不加载），false 放行。 */
    public interface UrlLoadingCallback {
        boolean onUrlLoading(String url);
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
}

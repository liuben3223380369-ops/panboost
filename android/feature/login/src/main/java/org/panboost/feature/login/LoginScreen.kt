package org.panboost.feature.login

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.network.QuarkApi


/**
 * 夸克登录屏（第 4 周：原生 WebView）。
 *
 * 原生 AndroidView+WebView 是官方成熟路径（无 Kivy 时代的
 * Dialog 时序/SDL 线程/双 Activity 黑屏坑——那些全是 Python 桥
 * 接层的问题，Compose 嵌原生 WebView 无此负担）：
 * - 桌面 UA 加载 pan.quark.cn（防移动 UA 跳"下载App"引导页）
 * - WebViewClient.onPageFinished 检查 CookieManager 里
 *   __pus/__puus（登录特征键，YunX 实锤）→ LoginViewModel
 *   .onLoginCookie(完整串) 存 CookieStore → onLoggedIn() 导航
 * - 已登录直入：LaunchedEffect 检查 CookieStore 非空即回调
 */
@Composable
fun LoginScreen(
    onLoggedIn: () -> Unit,
    viewModel: LoginViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.checkExistingLogin() }
    LaunchedEffect(uiState.loggedIn) {
        if (uiState.loggedIn) onLoggedIn()
    }
    LoginScreenContent(
        loginUrl = QuarkApi.LOGIN_URL,
        desktopUa = DESKTOP_UA,
        loading = uiState.loading,
        onCookie = viewModel::onLoginCookie,
    )
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
internal fun LoginScreenContent(
    loginUrl: String,
    desktopUa: String,
    loading: Boolean,
    onCookie: (String) -> Unit,
) {
    Scaffold(topBar = { TopAppBar(title = { Text("登录夸克网盘") }) }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(
                text = "在下方页面登录账号（支持验证码/短信/扫码）",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            var webView by remember { mutableStateOf<WebView?>(null) }
            AndroidView(
                factory = { context ->
                    WebView(context).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.userAgentString = desktopUa
                        settings.useWideViewPort = true
                        settings.loadWithOverviewMode = true
                        CookieManager.getInstance().apply {
                            setAcceptCookie(true)
                            setAcceptThirdPartyCookies(this@apply, true)
                        }
                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView, url: String?) {
                                super.onPageFinished(view, url)
                                val cookie = CookieManager.getInstance()
                                    .getCookie(QuarkApi.COOKIE_DOMAIN) ?: return
                                if (QuarkApi.AUTH_COOKIE_KEYS.any {
                                        cookie.contains("$it=", ignoreCase = true)
                                    }) {
                                    onCookie(cookie)
                                }
                            }
                        }
                        webView = this
                        loadUrl(loginUrl)
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )
            Button(
                onClick = {
                    webView?.url?.let { url ->
                        val cookie = CookieManager.getInstance()
                            .getCookie(QuarkApi.COOKIE_DOMAIN)
                        if (url.startsWith("https://pan.quark.cn") && cookie != null) {
                            onCookie(cookie)
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
            ) {
                Text("我已完成登录")
            }
        }
    }
}

private val DESKTOP_UA =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@Preview(showBackground = true)
@Composable
private fun LoginScreenPreview() {
    MaterialTheme {
        LoginScreenContent(
            loginUrl = "https://pan.quark.cn/",
            desktopUa = DESKTOP_UA,
            loading = false,
            onCookie = {},
        )
    }
}

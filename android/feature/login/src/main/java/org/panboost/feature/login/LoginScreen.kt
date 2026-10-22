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
import org.panboost.core.domain.PanCatalog

/**
 * 通用网盘登录屏（v4.3.0：数据驱动的 18 网盘登录）。
 *
 * 路由参数 panKey 决定登录页 URL / Cookie 采集域 / 特征键
 * （PanCatalog）。WebView onPageFinished 检查特征键命中 →
 * 自动保存返回；"我已完成登录"按钮兜底（Cookie 存在即保存——
 * authKeys 空的网盘走此路径记"未验证"，v3.2.8 同语义）。
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
        panName = viewModel.pan.name,
        loginUrl = viewModel.pan.loginUrl,
        cookieDomain = "https://${viewModel.pan.domains.first()}",
        authKeys = viewModel.pan.authKeys,
        loading = uiState.loading,
        onCookie = viewModel::onLoginCookie,
    )
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@SuppressLint("SetJavaScriptEnabled")
@Composable
internal fun LoginScreenContent(
    panName: String,
    loginUrl: String,
    cookieDomain: String,
    authKeys: List<String>,
    loading: Boolean,
    onCookie: (String) -> Unit,
) {
    Scaffold(topBar = { TopAppBar(title = { Text("登录$panName") }) }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(
                text = if (authKeys.isEmpty()) {
                    "在下方页面登录（该网盘登录态不存 Cookie，保存网页 Cookie 供下载尝试）"
                } else {
                    "在下方页面登录账号（支持验证码/短信/扫码）"
                },
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
                        settings.userAgentString = DESKTOP_UA
                        settings.useWideViewPort = true
                        settings.loadWithOverviewMode = true
                        CookieManager.getInstance().setAcceptCookie(true)
                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView, url: String?) {
                                super.onPageFinished(view, url)
                                val cookie = CookieManager.getInstance()
                                    .getCookie(cookieDomain) ?: return
                                if (authKeys.isNotEmpty() && authKeys.all {
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
                    webView?.let { view ->
                        val cookie = CookieManager.getInstance().getCookie(cookieDomain)
                        if (cookie != null &&
                            (authKeys.isEmpty() || view.url.orEmpty()
                                .contains(cookieDomain.removePrefix("https://")))
                        ) {
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
            panName = "夸克网盘",
            loginUrl = "https://pan.quark.cn/",
            cookieDomain = "https://quark.cn",
            authKeys = listOf("__pus", "__puus"),
            loading = false,
            onCookie = {},
        )
    }
}

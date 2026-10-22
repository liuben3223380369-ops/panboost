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

/**
 * 通用网盘登录屏（v5.1.1 采集域修正）。
 *
 * v5.1.0 及之前的 bug：Cookie 采集域用 PanCatalog domains.first()
 * （夸克 = quark.cn），而 __puus/__pus 实际种在登录页 host
 * （pan.quark.cn）——采到的 Cookie 不全，带去 API 即 401/空列表。
 * v5.1.1：多域合并采集（登录页 host 优先 + PanCatalog 全部域），
 * 同键以更精确域（后采集）覆盖。
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
        collectDomains = viewModel.pan.domains + loginHost(viewModel.pan.loginUrl),
        authKeys = viewModel.pan.authKeys,
        loading = uiState.loading,
        onCookie = viewModel::onLoginCookie,
    )
}

/** 登录页 host（夸克 = pan.quark.cn）。 */
private fun loginHost(loginUrl: String): String = try {
    android.net.Uri.parse(loginUrl).host ?: ""
} catch (_: Exception) {
    ""
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@SuppressLint("SetJavaScriptEnabled")
@Composable
internal fun LoginScreenContent(
    panName: String,
    loginUrl: String,
    collectDomains: List<String>,
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
                                val cookie = collectCookie(collectDomains)
                                if (authKeys.isNotEmpty() && cookie != null &&
                                    authKeys.all {
                                        cookie.contains("$it=", ignoreCase = true)
                                    }
                                ) {
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
            var manualHint by remember { mutableStateOf("") }
            Button(
                onClick = {
                    val cookie = collectCookie(collectDomains)
                    // v5.2.1：手动保存严格校验特征键（此前"Cookie 非空"
                    // 即存——无关跟踪 Cookie 也算，存下的快照请求必失败，
                    // 真机"登录 3 秒即失效"根因之一）
                    val complete = cookie != null && (
                            authKeys.isEmpty() ||
                                    authKeys.all {
                                        cookie!!.contains("$it=", ignoreCase = true)
                                    }
                            )
                    if (complete) {
                        onCookie(cookie!!)
                    } else {
                        manualHint = "未检测到完整登录凭证（${authKeys.joinToString("/")}）——请先在页面完成登录再点此按钮"
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
            ) {
                Text("我已完成登录")
            }
            if (manualHint.isNotEmpty()) {
                Text(
                    text = manualHint,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
        }
    }
}

/**
 * 多域 Cookie 合并采集（v5.1.1）。
 *
 * 顺序：PanCatalog domains 先、登录页 host 最后（更精确域的值
 * 覆盖同键）——夸克 __puus 种在 pan.quark.cn，只查 quark.cn 会
 * 拿不全（v5.1.0 空 Cookie 带去 API 即 401/空列表的根因）。
 */
private fun collectCookie(domains: List<String>): String? {
    val cm = CookieManager.getInstance()
    val merged = linkedMapOf<String, String>()
    for (d in domains) {
        if (d.isBlank()) continue
        val raw = try {
            cm.getCookie("https://$d")
        } catch (_: Exception) {
            null
        } ?: continue
        for (kv in raw.split(";")) {
            val k = kv.substringBefore("=").trim()
            val v = kv.substringAfter("=").trim()
            if (k.isNotEmpty() && v.isNotEmpty()) merged[k] = v
        }
    }
    return if (merged.isEmpty()) null
        else merged.entries.joinToString("; ") { "${it.key}=${it.value}" }
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
            collectDomains = listOf("quark.cn", "pan.quark.cn"),
            authKeys = listOf("__pus", "__puus"),
            loading = false,
            onCookie = {},
        )
    }
}

package org.panboost.core.network.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.panboost.core.domain.AccountRepository
import org.panboost.core.domain.PanCatalog
import org.panboost.core.logging.AppLog
import org.panboost.core.network.QuarkApi
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

/**
 * 网络层 Hilt 装配（v5.3.0 拦截器泛化重写）。
 *
 * v5.2.x 及之前的架构错误（用户实锤"问题依旧"+"不要写死夸克"）：
 * - Cookie 查询域写死 pan.quark.cn/quark.cn，而 API 请求 host 是
 *   drive-pc.quark.cn——RFC 6265 下应**按请求 host 查** getCookie，
 *   才能拿到"会发给该 host 的全部 cookie"（含父域 .quark.cn 的
 *   __puus/__uid/kps 等），查错域集合可能缺键（真机反复失败的
 *   根因）。
 * - 拦截器只服务夸克——UC 等同源网盘接入即坏。
 *
 * v5.3.0：**通用网盘 Cookie 拦截器**——按请求 host 反查 PanCatalog
 * 网盘域（任意网盘自动工作）；Cookie 三层供给：
 * 1. WebView 全局 Cookie 罐实时读（按请求 host + 该网盘全部域，
 *    登录后一切轮换自动反映）
 * 2. 持久快照合并（手动粘贴兜底；同键实时值优先）
 * 3. 响应 Set-Cookie 写回罐+快照（保活闭环）
 */
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    /**
     * 通用网盘 Cookie 拦截器（v5.3.0：网盘无关）。
     *
     * - host 匹配：请求 host 的任意后缀 == PanCatalog 某网盘的某域
     * - Cookie 供给：该网盘全部域的 WebView 罐实时值（按域逐个查，
     *   覆盖种在任何 host/domain 的键）+ 快照兜底合并
     * - 保活：响应 Set-Cookie 合并回罐与快照
     * - UA/Referer 仅对夸克系（clouddrive API 需要 UA=夸克客户端）
     */
    private class PanCookieInterceptor(
        private val accounts: AccountRepository,
        private val appLog: AppLog,
    ) : Interceptor {

        override fun intercept(chain: Interceptor.Chain): Response {
            val request = chain.request()
            val host = request.url.host
            val pan = PanCatalog.all.firstOrNull { pan ->
                pan.domains.any { host == it || host.endsWith(".$it") }
            }

            val builder = request.newBuilder()
            var snapshot = ""
            if (pan != null) {
                if (pan.key == "quark") {
                    // 夸克 clouddrive API：客户端 UA + Referer（quark-auto-save 实战规格）
                    builder.header("User-Agent", QuarkApi.CLIENT_UA)
                        .header("Referer", QuarkApi.REFERER)
                        .header("Origin", "https://pan.quark.cn")
                }
                snapshot = accounts.getCookie(pan.key).orEmpty()
                val live = liveCookie(pan, host)
                val merged = mergeCookie(live, snapshot)
                if (merged.isNotBlank()) {
                    builder.header("Cookie", merged)
                    appLog.info(
                        "net",
                        "${request.method} ${request.url.encodedPath.take(56)}" +
                                " [${pan.key}] cookie 实时${live.length}/快照${snapshot.length}",
                    )
                } else {
                    appLog.warn(
                        "net",
                        "${request.method} ${request.url.encodedPath.take(56)}" +
                                " [${pan.key}] 无 Cookie（未登录或已失效）",
                    )
                }
            }

            val started = System.currentTimeMillis()
            val resp = chain.proceed(builder.build())
            appLog.info(
                "net",
                "${request.method} ${request.url.encodedPath.take(56)} → ${resp.code}" +
                        "（${System.currentTimeMillis() - started}ms）",
            )

            // Set-Cookie 保活（写回罐 + 快照）
            if (pan != null) {
                try {
                    val setCookies = resp.headers("Set-Cookie")
                    if (setCookies.isNotEmpty()) {
                        var merged = snapshot
                        var renewed = 0
                        for (kv in setCookies) {
                            val part = kv.substringBefore(";")
                            val k = part.substringBefore("=").trim()
                            val v = part.substringAfter("=").trim()
                            if (k.isNotEmpty() && v.isNotEmpty()) {
                                merged = setKv(merged, k, v)
                                renewed++
                            }
                        }
                        if (merged.isNotBlank()) {
                            writeBack(pan, merged)
                            accounts.setCookie(pan.key, merged)
                            appLog.info("net", "[${pan.key}] Cookie 保活：续期 $renewed 个键")
                        }
                    }
                } catch (_: Exception) {
                }
            }
            return resp
        }

        /** 实时读 WebView 罐：按请求 host + 该网盘全部域逐个查询合并。 */
        private fun liveCookie(pan: org.panboost.core.domain.PanInfo, requestHost: String): String {
            return try {
                val cm = android.webkit.CookieManager.getInstance()
                val hosts = (listOf(requestHost) + pan.domains + pan.loginUrl
                    .removePrefix("https://").removePrefix("http://")
                    .substringBefore("/"))
                    .filter { it.isNotBlank() }
                    .distinct()
                val kv = linkedMapOf<String, String>()
                for (h in hosts) {
                    val raw = try {
                        cm.getCookie("https://$h")
                    } catch (_: Exception) {
                        null
                    } ?: continue
                    for (c in raw.split(";")) {
                        val k = c.substringBefore("=").trim()
                        val v = c.substringAfter("=").trim()
                        if (k.isNotEmpty() && v.isNotEmpty()) kv[k] = v
                    }
                }
                kv.entries.joinToString("; ") { "${it.key}=${it.value}" }
            } catch (_: Exception) {
                ""
            }
        }

        /** 快照合并（live 优先，快照补缺）。 */
        private fun mergeCookie(live: String, snapshot: String): String {
            if (live.isBlank()) return snapshot.trim()
            if (snapshot.isBlank()) return live
            val kv = linkedMapOf<String, String>()
            for (c in snapshot.split(";")) {
                val k = c.substringBefore("=").trim()
                if (k.isNotEmpty()) kv[k] = c.substringAfter("=").trim()
            }
            for (c in live.split(";")) {
                val k = c.substringBefore("=").trim()
                if (k.isNotEmpty()) kv[k] = c.substringAfter("=").trim()
            }
            return kv.entries.joinToString("; ") { "${it.key}=${it.value}" }
        }

        /** Set-Cookie 写回 WebView 罐（保活闭环）。 */
        private fun writeBack(pan: org.panboost.core.domain.PanInfo, merged: String) {
            try {
                val cm = android.webkit.CookieManager.getInstance()
                for (c in merged.split("; ")) {
                    val k = c.substringBefore("=").trim()
                    if (k.isNotEmpty()) {
                        for (d in pan.domains) {
                            cm.setCookie("https://$d", c)
                        }
                    }
                }
                cm.flush()
            } catch (_: Exception) {
            }
        }

        private fun setKv(cookie: String, k: String, v: String): String {
            val parts = cookie.split("; ").filter { it.isNotBlank() }.toMutableList()
            val idx = parts.indexOfFirst {
                it.substringBefore("=").trim().equals(k, ignoreCase = true)
            }
            val kv = "$k=$v"
            if (idx >= 0) parts[idx] = kv else parts.add(kv)
            return parts.joinToString("; ")
        }
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(
        accounts: AccountRepository,
        appLog: AppLog,
    ): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(PanCookieInterceptor(accounts, appLog))
            .addInterceptor(org.panboost.core.network.PersonaInterceptor())
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .dispatcher(
                okhttp3.Dispatcher().apply {
                    maxRequests = 1024
                    maxRequestsPerHost = 1024
                }
            )
            .connectionPool(
                okhttp3.ConnectionPool(1024, 30, TimeUnit.SECONDS)
            )
            .build()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl(QuarkApi.BASE_URL)
            .client(client)
            .build()

    @Provides
    @Singleton
    fun provideQuarkApi(retrofit: Retrofit): QuarkApi =
        retrofit.create(QuarkApi::class.java)

    // v5.2.0：分享链接解析 API（同一 Retrofit/OkHttp/拦截器链）
    @Provides
    @Singleton
    fun provideQuarkShareApi(retrofit: Retrofit): org.panboost.core.network.QuarkShareApi =
        retrofit.create(org.panboost.core.network.QuarkShareApi::class.java)

    // v5.0.0：123 云盘分享 API（独立 baseUrl 的第二 Retrofit）
    @Provides
    @Singleton
    @javax.inject.Named("pan123")
    fun providePan123Retrofit(client: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl(org.panboost.core.network.Pan123ShareApi.BASE_URL)
            .client(client)
            .build()

    @Provides
    @Singleton
    fun providePan123ShareApi(
        @javax.inject.Named("pan123") retrofit: Retrofit,
    ): org.panboost.core.network.Pan123ShareApi =
        retrofit.create(org.panboost.core.network.Pan123ShareApi::class.java)

    /** 直链下载请求体工厂（JSON {"fids":[...]}）。 */
    @Provides
    @Singleton
    fun provideFidsBodyFactory(): org.panboost.core.network.FidsBodyFactory =
        org.panboost.core.network.FidsBodyFactory()
}

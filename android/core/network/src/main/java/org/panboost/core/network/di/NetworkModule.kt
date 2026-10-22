package org.panboost.core.network.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.panboost.core.domain.AccountRepository
import org.panboost.core.network.QuarkApi
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Qualifier
import javax.inject.Singleton

/**
 * 网络层 Hilt 装配（第 4 周）。
 *
 * 单一 OkHttp（UA/Referer/Cookie 拦截器——每次请求从 CookieStore
 * 读最新值，登录后立即生效）+ Retrofit（BASE_URL 夸克云端）+
 * 下载专用 OkHttp（同样的头策略，直链下载走它——夸克直链校验
 * Referer，YunX 实锤）。
 */
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    /**
     * 夸克 API 头策略 + Set-Cookie 保活（v5.1.0：401 根治）。
     *
     * v3.2.8 drive._merge_set_cookie 的原生等价：__puus/__pus 约
     * 3 小时过期（直链签名校验关键字段），每次 API 响应的
     * Set-Cookie 合并回 CookieStore 持久化——登录态持续保活。
     * 漏掉这段是 v5.0.0 网盘浏览 401 的根因（Cookie 过期）。
     */
    private class QuarkHeaderInterceptor(
        private val accounts: AccountRepository,
        private val appLog: org.panboost.core.logging.AppLog,
    ) : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val builder: Request.Builder = chain.request().newBuilder()
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .header("Referer", QuarkApi.REFERER)
                .header("Origin", "https://pan.quark.cn")
            val old = accounts.getCookie("quark") ?: ""
            if (old.isNotEmpty()) builder.header("Cookie", old)
            val started = System.currentTimeMillis()
            val resp = chain.proceed(builder.build())
            // v5.2.0：全链路请求日志（日志屏此前"不记录"的根因——网络层零日志）
            appLog.info(
                "net",
                "${chain.request().method} ${chain.request().url.encodedPath.take(60)}"
                        + " → ${resp.code}（${System.currentTimeMillis() - started}ms）",
            )
            // Set-Cookie 合并保活（新值覆盖同键旧值）
            try {
                var merged = old
                var renewed = 0
                for (kv in resp.headers("Set-Cookie")) {
                    val part = kv.substringBefore(";")
                    val k = part.substringBefore("=").trim()
                    val v = part.substringAfter("=").trim()
                    if (k.isNotEmpty() && v.isNotEmpty()) {
                        merged = setKv(merged, k, v)
                        renewed += 1
                    }
                }
                if (merged != old && merged.isNotEmpty()) {
                    accounts.setCookie("quark", merged)
                    appLog.info("net", "Cookie 保活：续期 $renewed 个键")
                }
            } catch (_: Exception) {
            }
            return resp
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
        appLog: org.panboost.core.logging.AppLog,
    ): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(QuarkHeaderInterceptor(accounts, appLog))
            .addInterceptor(org.panboost.core.network.PersonaInterceptor())
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            // v5.1.0：512/1024 线程并发前置条件（默认 64 会饿死高并发）
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

    // v4.2.0：分享链接解析 API（同一 Retrofit/OkHttp/拦截器链）
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

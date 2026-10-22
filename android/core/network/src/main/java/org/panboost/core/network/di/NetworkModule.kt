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

    /** 夸克 API 头策略（客户端 UA + Referer + 登录 Cookie）。 */
    private class QuarkHeaderInterceptor(
        private val accounts: AccountRepository,
    ) : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val builder: Request.Builder = chain.request().newBuilder()
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .header("Referer", QuarkApi.REFERER)
                .header("Origin", "https://pan.quark.cn")
            accounts.getCookie("quark")?.let {
                builder.header("Cookie", it)
            }
            return chain.proceed(builder.build())
        }
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(accounts: AccountRepository): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(QuarkHeaderInterceptor(accounts))
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
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

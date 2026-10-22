package org.panboost.core.network

import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response

/**
 * 拟人化请求头（v5.1.0：v3.2.8 PersonaKit 的原生等价——防风控）。
 *
 * - Accept / Accept-Language 浏览器风格补全（用户显式头优先）
 * - Accept-Encoding 固定 identity：Range 分段下载必须禁用透明压缩，
 *   否则 Content-Length 与解压后字节错位会写坏文件（v3.2.8 实锤）
 * - Chrome UA 时补 Sec-Fetch 头组（站点指纹一致性）
 */
class PersonaInterceptor : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        val ua = req.header("User-Agent") ?: DEFAULT_UA
        val builder = req.newBuilder()
            .header("Accept", ACCEPT)
            .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
            .header("Accept-Encoding", "identity")
        if (CHROME_UA.containsMatchIn(ua)) {
            builder.header("Sec-Fetch-Dest", "document")
                .header("Sec-Fetch-Mode", "navigate")
                .header("Sec-Fetch-Site", "cross-site")
                .header("Sec-Fetch-User", "?1")
        }
        return chain.proceed(builder.build())
    }

    companion object {
        private const val DEFAULT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        private const val ACCEPT =
            "text/html,application/xhtml+xml,application/xml;q=0.9," +
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
        private val CHROME_UA = Regex("Chrome/|Chromium/|Edg/", RegexOption.IGNORE_CASE)

        /** UA 轮换池（v3.2.8 UARotator——403 风控时换 UA 重试）。 */
        val UA_POOL = listOf(
            DEFAULT_UA,
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )

        @Volatile
        private var uaCursor: Int = 0

        /** 取下一个轮换 UA（线程安全游标）。 */
        fun nextUa(): String = synchronized(this) {
            uaCursor = (uaCursor + 1) % UA_POOL.size
            UA_POOL[uaCursor]
        }
    }
}

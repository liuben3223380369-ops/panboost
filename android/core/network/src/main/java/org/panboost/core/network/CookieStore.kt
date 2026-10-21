package org.panboost.core.network

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 登录 Cookie 存储（第 4 周）。
 *
 * SharedPreferences 同步 API——体量小（单网盘 Cookie 串）、
 * 读写频率低（登录/每次请求拦截读取），无需 DataStore 的
 * 协程复杂度。第 5 周多网盘扩展时改 key 维度即可。
 */
@Singleton
class CookieStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val prefs = context.getSharedPreferences("panboost_cookies", Context.MODE_PRIVATE)

    /** 夸克登录 Cookie（完整串，登录页 WebView 采集）。 */
    fun getQuark(): String? = prefs.getString(KEY_QUARK, null)

    fun setQuark(cookie: String) {
        prefs.edit().putString(KEY_QUARK, cookie).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    private companion object {
        const val KEY_QUARK = "quark"
    }
}

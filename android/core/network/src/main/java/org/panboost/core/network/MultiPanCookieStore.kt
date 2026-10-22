package org.panboost.core.network

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.panboost.core.domain.AccountEntry
import org.panboost.core.domain.AccountRepository
import org.panboost.core.domain.PanCatalog
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 多网盘 Cookie 存储（v4.3.0：v3.2.8 多网盘账簿原生重建）。
 *
 * SharedPreferences 单文件多 key（pan_key → cookie 串）；
 * 版本号自增触发 StateFlow 重发——账号页/登录屏实时刷新。
 * 夸克旧字段（v4.0~v4.2 单网盘时代）自动迁移到新 key。
 */
@Singleton
class MultiPanCookieStore @Inject constructor(
    @ApplicationContext context: Context,
) : AccountRepository {

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _version = MutableStateFlow(0)
    val version: StateFlow<Int> = _version.asStateFlow()

    init {
        // v4.2 迁移：旧单网盘字段 quark → cookies:quark
        val legacy = prefs.getString("quark", null)
        if (legacy != null) {
            prefs.edit()
                .putString(cookieKey("quark"), legacy)
                .remove("quark")
                .apply()
        }
    }

    override fun observeAll(): kotlinx.coroutines.flow.Flow<List<AccountEntry>> =
        _version.map {
            PanCatalog.all.map { pan ->
                val cookie = getCookie(pan.key)
                AccountEntry(
                    pan = pan,
                    hasCookie = cookie != null,
                    verified = isVerified(pan.key, cookie),
                )
            }
        }

    override fun getCookie(panKey: String): String? =
        prefs.getString(cookieKey(panKey), null)

    override fun setCookie(panKey: String, cookie: String) {
        prefs.edit().putString(cookieKey(panKey), cookie).apply()
        _version.value += 1
    }

    override fun remove(panKey: String) {
        prefs.edit().remove(cookieKey(panKey)).apply()
        _version.value += 1
    }

    override fun isVerified(panKey: String, cookie: String?): Boolean {
        val keys = PanCatalog.byKey(panKey)?.authKeys ?: return false
        if (keys.isEmpty() || cookie.isNullOrEmpty()) return false
        return keys.all { cookie.contains("$it=", ignoreCase = true) }
    }

    private fun cookieKey(panKey: String) = "cookies:$panKey"

    private companion object {
        const val PREFS_NAME = "panboost_cookies"
    }
}

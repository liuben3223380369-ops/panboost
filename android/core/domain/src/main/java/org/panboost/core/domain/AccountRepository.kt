package org.panboost.core.domain

import kotlinx.coroutines.flow.Flow

/**
 * 网盘账号条目（v4.3.0 账号管理屏模型）。
 *
 * verified：特征 Cookie 键全部命中（authKeys 为空的网盘永远
 * false——登录态在 localStorage，只能存 Cookie 供下载尝试，
 * 显示"未验证"——v3.2.8 账簿同语义）。
 */
data class AccountEntry(
    val pan: PanInfo,
    val hasCookie: Boolean,
    val verified: Boolean,
)

/**
 * 账号仓库接口（v4.3.0）。
 *
 * 实现于 :core:network（CookieStore 多网盘化）。
 * observeAll：账簿流（Cookie 变化驱动账号页实时刷新）。
 */
interface AccountRepository {
    fun observeAll(): Flow<List<AccountEntry>>
    fun getCookie(panKey: String): String?
    fun setCookie(panKey: String, cookie: String)
    fun remove(panKey: String)
    /** 特征键校验（authKeys 全部命中才 true）。 */
    fun isVerified(panKey: String, cookie: String?): Boolean
}

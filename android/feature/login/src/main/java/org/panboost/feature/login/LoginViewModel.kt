package org.panboost.feature.login

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.panboost.core.domain.AccountRepository
import org.panboost.core.domain.PanCatalog
import javax.inject.Inject

/**
 * 通用网盘登录 ViewModel（v4.3.0：v3.2.8 18 网盘登录的等价回补）。
 *
 * panKey 经路由参数注入（SavedStateHandle）；登录页 URL/Cookie
 * 采集域/特征键全部由 PanCatalog 数据驱动——新增网盘零代码。
 * WebView 侧命中特征 Cookie → 存账簿（多网盘 CookieStore）→
 * loggedIn 驱动返回账号页。
 */
@HiltViewModel
class LoginViewModel @Inject constructor(
    private val accounts: AccountRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    val panKey: String = savedStateHandle.get<String>("panKey") ?: "quark"

    val pan = PanCatalog.byKey(panKey) ?: PanCatalog.byKey("quark")!!

    private val _uiState = MutableStateFlow(
        LoginUiState(loggedIn = accounts.isVerified(panKey, accounts.getCookie(panKey)))
    )
    val uiState: StateFlow<LoginUiState> = _uiState.asStateFlow()

    /** 已有 Cookie（历史登录）直入。 */
    fun checkExistingLogin() {
        if (!_uiState.value.loggedIn && accounts.getCookie(panKey) != null) {
            _uiState.value = LoginUiState(loggedIn = true, loading = false)
        }
    }

    /** WebView 采集到的 Cookie（特征键已由页面侧校验）。 */
    fun onLoginCookie(cookie: String) {
        if (_uiState.value.loggedIn) return
        accounts.setCookie(panKey, cookie)
        _uiState.value = LoginUiState(
            loggedIn = true,
            loading = false,
            verified = accounts.isVerified(panKey, cookie),
        )
    }
}

data class LoginUiState(
    val loggedIn: Boolean = false,
    val loading: Boolean = false,
    val verified: Boolean = false,
)

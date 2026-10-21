package org.panboost.feature.login

import androidx.lifecycle.ViewModel
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.panboost.core.network.CookieStore
import javax.inject.Inject

/**
 * 登录屏 ViewModel（第 4 周 MVI）。
 *
 * onLoginCookie：WebView 侧检测到登录特征 Cookie（__pus/
 * __puus 命中）→ 存 CookieStore（网络层拦截器此后每次请求
 * 自动携带）→ loggedIn 置位驱动导航 home。
 */
@HiltViewModel
class LoginViewModel @Inject constructor(
    private val cookieStore: CookieStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LoginUiState())
    val uiState: StateFlow<LoginUiState> = _uiState.asStateFlow()

    /** 已有 Cookie（历史登录）直入 home。 */
    fun checkExistingLogin() {
        if (!_uiState.value.loggedIn && !cookieStore.getQuark().isNullOrEmpty()) {
            _uiState.value = LoginUiState(loggedIn = true, loading = false)
        }
    }

    fun onLoginCookie(cookie: String) {
        if (_uiState.value.loggedIn) return
        cookieStore.setQuark(cookie)
        _uiState.value = LoginUiState(loggedIn = true, loading = false)
    }
}

data class LoginUiState(
    val loggedIn: Boolean = false,
    val loading: Boolean = false,
)

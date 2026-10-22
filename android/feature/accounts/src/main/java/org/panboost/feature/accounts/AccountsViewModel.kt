package org.panboost.feature.accounts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.MutableStateFlow
import org.panboost.core.domain.AccountRepository
import javax.inject.Inject

/**
 * 账号屏 ViewModel（v4.3.0：v3.2.8 账簿回补）。
 *
 * entries 直通车：AccountRepository.observeAll（Cookie 版本号
 * 驱动——登录/删除/粘贴即时刷新徽标）。Remove 清 Cookie；
 * SavePaste 手动粘贴 Cookie（登录失败兜底路径，v3.2.8 同款）。
 */
@HiltViewModel
class AccountsViewModel @Inject constructor(
    private val accounts: AccountRepository,
) : ViewModel() {

    private val _dialog = MutableStateFlow(DialogState())
    private val _snackbar = MutableStateFlow<String?>(null)

    val uiState: StateFlow<AccountsUiState> =
        kotlinx.coroutines.flow.combine(
            accounts.observeAll(), _dialog, _snackbar,
        ) { entries, dialog, snackbar ->
            AccountsUiState(
                entries = entries,
                pasteDialogFor = dialog.panKey,
                pasteValue = dialog.value,
                snackbar = snackbar,
            )
        }.stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = AccountsUiState(),
        )

    fun onIntent(intent: AccountsIntent) {
        when (intent) {
            // Login 由 UI 层直接导航（无需仓库操作）
            is AccountsIntent.Login -> Unit
            is AccountsIntent.Remove -> {
                accounts.remove(intent.panKey)
                _snackbar.value = "已删除该网盘的登录 Cookie"
            }
            is AccountsIntent.OpenPasteDialog ->
                _dialog.update { DialogState(panKey = intent.panKey) }
            AccountsIntent.ClosePasteDialog ->
                _dialog.update { DialogState() }
            is AccountsIntent.PasteValueChanged ->
                _dialog.update { it.copy(value = intent.value) }
            AccountsIntent.SavePaste -> savePaste()
            AccountsIntent.SnackbarShown -> _snackbar.value = null
        }
    }

    private fun savePaste() {
        val panKey = _dialog.value.panKey ?: return
        val value = _dialog.value.value.trim()
        if (value.isEmpty()) return
        accounts.setCookie(panKey, value)
        _dialog.update { DialogState() }
        _snackbar.value = "Cookie 已保存" +
                if (accounts.isVerified(panKey, value)) "（登录态验证通过）" else "（未验证——可尝试下载）"
    }

    private data class DialogState(
        val panKey: String? = null,
        val value: String = "",
    )
}

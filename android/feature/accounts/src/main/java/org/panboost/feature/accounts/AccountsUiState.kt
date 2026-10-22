package org.panboost.feature.accounts

import org.panboost.core.domain.AccountEntry

/**
 * 账号屏 UiState（v4.3.0 MVI）。
 *
 * entries 为 18 网盘账簿（Cookie 变化实时驱动）；
 * pasteDialogFor 为手动粘贴 Cookie 对话框目标网盘。
 */
data class AccountsUiState(
    val entries: List<AccountEntry> = emptyList(),
    val pasteDialogFor: String? = null,
    val pasteValue: String = "",
    val snackbar: String? = null,
) {
    val verifiedCount: Int get() = entries.count { it.verified }
}

sealed interface AccountsIntent {
    data class Login(val panKey: String) : AccountsIntent
    data class Remove(val panKey: String) : AccountsIntent
    data class OpenPasteDialog(val panKey: String) : AccountsIntent
    data object ClosePasteDialog : AccountsIntent
    data class PasteValueChanged(val value: String) : AccountsIntent
    data object SavePaste : AccountsIntent
    data object SnackbarShown : AccountsIntent
}

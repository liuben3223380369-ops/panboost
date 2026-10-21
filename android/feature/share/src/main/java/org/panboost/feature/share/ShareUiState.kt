package org.panboost.feature.share

import org.panboost.core.domain.ShareFile

/**
 * 分享屏 UiState（v4.2.0 MVI）。
 *
 * files 为解析结果；selected 为勾选集（按 url 去重）；
 * resolving 标记解析中（防重复点击）；snackbar 一次性消息。
 */
data class ShareUiState(
    val shareUrl: String = "",
    val passcode: String = "",
    val resolving: Boolean = false,
    val files: List<ShareFile> = emptyList(),
    val selected: Set<String> = emptySet(),
    val snackbar: String? = null,
) {
    val selectedCount: Int get() = selected.size
    val allSelected: Boolean get() = files.isNotEmpty() && selected.size == files.size
    val canDownload: Boolean get() = selected.isNotEmpty() && !resolving
}

sealed interface ShareIntent {
    data class UrlChanged(val url: String) : ShareIntent
    data class PasscodeChanged(val code: String) : ShareIntent
    data object Parse : ShareIntent
    data class Toggle(val file: ShareFile) : ShareIntent
    data object ToggleAll : ShareIntent
    data object DownloadSelected : ShareIntent
    data object SnackbarShown : ShareIntent
}

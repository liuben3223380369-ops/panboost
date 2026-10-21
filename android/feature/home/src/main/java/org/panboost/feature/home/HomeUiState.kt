package org.panboost.feature.home

import org.panboost.core.domain.DriveFile

/**
 * 首屏 UiState（第 4 周 MVI）。
 *
 * files 为当前目录列表（进入文件夹即整体替换）；
 * path 为面包屑栈（fid→名称，根为"我的网盘"）；
 * downloading 标记"点文件取直链中"（防连点）；
 * snackbar 一次性消息（下载已发起/错误）。
 */
data class HomeUiState(
    val loading: Boolean = false,
    val files: List<DriveFile> = emptyList(),
    val path: List<Breadcrumb> = listOf(Breadcrumb("0", "我的网盘")),
    val downloading: DriveFile? = null,
    val snackbar: String? = null,
) {
    val currentFid: String get() = path.last().fid
}

data class Breadcrumb(val fid: String, val name: String)

/** 首屏意图。 */
sealed interface HomeIntent {
    data object Refresh : HomeIntent
    data class OpenDir(val dir: DriveFile) : HomeIntent
    data object NavigateUp : HomeIntent
    data class DownloadFile(val file: DriveFile) : HomeIntent
    data object SnackbarShown : HomeIntent
}

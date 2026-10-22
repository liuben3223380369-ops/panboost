package org.panboost.feature.home

import org.panboost.core.domain.DriveFile

/**
 * 首屏 UiState（v5.1.1 增强）。
 *
 * files 为当前目录列表（进入文件夹即整体替换）；
 * path 为面包屑栈（fid→名称，根为"我的网盘"）；
 * downloading 标记"点文件取直链中"（防连点）；
 * snackbar 一次性消息；
 * error（v5.1.1）：持久错误态——加载失败不再只闪一次 Snackbar，
 * 网盘 Tab 显示错误卡片+重试/去登录按钮（根因：登录后回 Tab
 * 列表仍空且无任何提示）。
 */
data class HomeUiState(
    val loading: Boolean = false,
    val files: List<DriveFile> = emptyList(),
    val path: List<Breadcrumb> = listOf(Breadcrumb("0", "我的网盘")),
    val downloading: DriveFile? = null,
    val snackbar: String? = null,
    val error: String? = null,
) {
    val currentFid: String get() = path.last().fid

    /** 空态可显示（非加载中且无内容）。 */
    val showEmpty: Boolean get() = !loading && files.isEmpty()
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

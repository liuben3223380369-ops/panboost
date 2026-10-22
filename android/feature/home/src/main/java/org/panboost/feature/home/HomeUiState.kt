package org.panboost.feature.home

import org.panboost.core.domain.AccountEntry
import org.panboost.core.domain.DriveFile

/**
 * 首屏 UiState（v5.2.0 网盘选择层）。
 *
 * v5.1.1 用户实锤"网盘界面不会显示网盘等内容让使用者选择进入"——
 * 网盘 Tab 此前硬编码直入夸克文件列表，缺 v3.2.8 首页宫格的
 * "选网盘"步骤。v5.2.0：顶部网盘选择条（已登录/已存 Cookie 的
 * 网盘 chips），选中后进入该网盘文件列表；非夸克网盘显示
 * "浏览下载即将接入"占位（Cookie 已存好，等待逐家接 API）。
 */
data class HomeUiState(
    val loading: Boolean = false,
    val files: List<DriveFile> = emptyList(),
    val path: List<Breadcrumb> = listOf(Breadcrumb("0", "我的网盘")),
    val downloading: DriveFile? = null,
    val snackbar: String? = null,
    val error: String? = null,
    /** 网盘选择层（v5.2.0）：已登录/已存 Cookie 的网盘。 */
    val availablePans: List<AccountEntry> = emptyList(),
    /** 当前选中网盘 key（默认夸克——唯一已接浏览 API 的网盘）。 */
    val selectedPan: String = "quark",
) {
    val currentFid: String get() = path.last().fid
    val showEmpty: Boolean get() = !loading && files.isEmpty()
    /** 选中网盘的中文名。 */
    val selectedPanName: String
        get() = availablePans.firstOrNull { it.pan.key == selectedPan }
            ?.pan?.name ?: "夸克网盘"
}

data class Breadcrumb(val fid: String, val name: String)

/** 首屏意图。 */
sealed interface HomeIntent {
    data object Refresh : HomeIntent
    /** 切换网盘（v5.2.0）。 */
    data class SelectPan(val panKey: String) : HomeIntent
    data class OpenDir(val dir: DriveFile) : HomeIntent
    data object NavigateUp : HomeIntent
    data class DownloadFile(val file: DriveFile) : HomeIntent
    data object SnackbarShown : HomeIntent
}

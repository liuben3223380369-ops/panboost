package org.panboost.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.panboost.core.domain.AccountEntry
import org.panboost.core.domain.AccountRepository
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadTask
import java.util.UUID
import javax.inject.Inject

/**
 * 首屏 ViewModel（v5.2.0 网盘选择层）。
 *
 * 账户流（已登录/已存 Cookie 网盘）与文件状态合并——网盘 Tab
 * 顶部显示网盘选择条（v3.2.8 首页宫格语义）；切换网盘重置路径
 * 并加载；非夸克网盘不拉 API（UI 显示接入预告，Cookie 已存好）。
 */
@HiltViewModel
class HomeViewModel @Inject constructor(
    // v6.6.0：双仓库（夸克 + UC——OpenList quark_uc 同源实证）；
    // 其余网盘逐家接入（ROADMAP P0#5）
    private val quarkDrive: org.panboost.core.network.QuarkDriveRepository,
    private val ucDrive: org.panboost.core.network.UcDriveRepository,
    private val tianyiDrive: org.panboost.core.network.TianyiDriveRepository,
    private val downloadRepository: DownloadRepository,
    accountRepository: AccountRepository,
) : ViewModel() {

    /** 当前选中网盘的仓库（v6.6.0：quark/uc 均可浏览下载）。 */
    private val driveRepository: DriveRepository
        get() = when (selectedPan.value) {
            "uc" -> ucDrive
            "tianyi" -> tianyiDrive
            else -> quarkDrive
        }

    private val selectedPan = MutableStateFlow("quark")
    private val panel = MutableStateFlow(HomeUiState())

    val uiState: StateFlow<HomeUiState> = combine(
        panel,
        accountRepository.observeAll(),
        selectedPan,
    ) { p, accounts, sel ->
        p.copy(
            availablePans = accounts.filter { it.hasCookie },
            selectedPan = sel,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = HomeUiState(),
    )

    init {
        load(panel.value.currentFid)
    }

    fun onIntent(intent: HomeIntent) {
        when (intent) {
            HomeIntent.Refresh -> load(panel.value.currentFid)
            is HomeIntent.SelectPan -> selectPan(intent.panKey)
            is HomeIntent.OpenDir -> openDir(intent.dir)
            HomeIntent.NavigateUp -> navigateUp()
            is HomeIntent.DownloadFile -> downloadFile(intent.file)
            HomeIntent.SnackbarShown -> panel.update { it.copy(snackbar = null) }
        }
    }

    private fun selectPan(panKey: String) {
        if (panKey == selectedPan.value) return
        selectedPan.value = panKey
        panel.update {
            it.copy(
                path = listOf(Breadcrumb("0", "我的网盘")),
                files = emptyList(),
                error = null,
            )
        }
        load("0")
    }

    private fun load(fid: String) {
        if (panel.value.loading) return  // 防抖
        // v6.6.0：夸克 + UC 已接浏览 API（其余网盘 UI 占位，Cookie 已存）
        if (selectedPan.value !in SUPPORTED_BROWSE) return
        panel.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                val files = driveRepository.listFiles(fid)
                panel.update { it.copy(loading = false, files = files) }
            } catch (e: Exception) {
                panel.update {
                    it.copy(
                        loading = false,
                        error = e.message?.take(120)
                            ?: "加载失败（${e.javaClass.simpleName}）",
                    )
                }
            }
        }
    }

    private fun openDir(dir: DriveFile) {
        panel.update {
            it.copy(path = it.path + Breadcrumb(dir.fid, dir.name))
        }
        load(dir.fid)
    }

    private fun navigateUp() {
        val state = panel.value
        if (state.path.size <= 1) return
        panel.update { it.copy(path = state.path.dropLast(1)) }
        load(panel.value.currentFid)
    }

    private fun downloadFile(file: DriveFile) {
        val state = panel.value
        if (state.downloading != null) return
        panel.update { it.copy(downloading = file) }
        viewModelScope.launch {
            try {
                // v6.3.0：多直链解析（4 条 CDN 节点轮换——总吞吐×N）
                val urls = driveRepository.getDownloadUrls(file.fid, 4)
                if (urls.isEmpty()) {
                    throw IllegalStateException("直链解析失败（空响应）")
                }
                downloadRepository.enqueue(
                    DownloadTask(
                        id = UUID.randomUUID().toString(),
                        url = urls[0],
                        extraUrls = urls.drop(1),
                        fileName = file.name,
                        mimeType = guessMime(file.name),
                        totalBytes = file.size,
                        // v6.6.0：动态传当前网盘（Worker 泛化上下文）
                        panKey = selectedPan.value,
                    )
                )
                panel.update {
                    it.copy(
                        downloading = null,
                        snackbar = "已开始下载「${file.name}」——到下载页查看进度",
                    )
                }
            } catch (e: Exception) {
                panel.update {
                    it.copy(
                        downloading = null,
                        snackbar = "获取直链失败：${e.message?.take(60)}",
                    )
                }
            }
        }
    }

    private companion object {
        /** v7.0.0：已接浏览 API 的网盘（夸克/UC 同源家族+天翼 Cookie 直连）。 */
        val SUPPORTED_BROWSE = setOf("quark", "uc", "tianyi")
    }

    private fun guessMime(name: String): String = when {
        name.endsWith(".apk", true) -> "application/vnd.android.package-archive"
        name.endsWith(".mp4", true) -> "video/mp4"
        name.endsWith(".mp3", true) -> "audio/mpeg"
        name.endsWith(".zip", true) -> "application/zip"
        name.endsWith(".bin", true) -> "application/octet-stream"
        else -> "application/octet-stream"
    }
}

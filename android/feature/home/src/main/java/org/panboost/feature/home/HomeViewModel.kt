package org.panboost.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadTask
import java.util.UUID
import javax.inject.Inject

/**
 * 首屏 ViewModel（v5.1.1 生命周期刷新）。
 *
 * v5.1.0 及之前的结构性缺陷：init 只在 ViewModel 创建时加载一次
 * ——用户先开网盘 Tab（未登录→失败）→去账号页登录→回 Tab，
 * 同一实例不再刷新，列表永空。修复：
 * - Refresh 由 HomeScreen 的 ON_RESUME 生命周期事件触发（每次
 *   Tab 回前台都重拉；loading 中自动跳过防抖）
 * - 加载失败写入持久 error（UI 显示错误卡片+重试按钮，不再只
 *   闪一次 Snackbar）
 */
@HiltViewModel
class HomeViewModel @Inject constructor(
    private val driveRepository: DriveRepository,
    private val downloadRepository: DownloadRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        load(_uiState.value.currentFid)
    }

    fun onIntent(intent: HomeIntent) {
        when (intent) {
            HomeIntent.Refresh -> load(_uiState.value.currentFid)
            is HomeIntent.OpenDir -> openDir(intent.dir)
            HomeIntent.NavigateUp -> navigateUp()
            is HomeIntent.DownloadFile -> downloadFile(intent.file)
            HomeIntent.SnackbarShown -> _uiState.update {
                it.copy(snackbar = null)
            }
        }
    }

    private fun load(fid: String) {
        if (_uiState.value.loading) return  // 防抖
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                val files = driveRepository.listFiles(fid)
                _uiState.update { it.copy(loading = false, files = files) }
            } catch (e: Exception) {
                _uiState.update {
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
        _uiState.update {
            it.copy(path = it.path + Breadcrumb(dir.fid, dir.name))
        }
        load(dir.fid)
    }

    private fun navigateUp() {
        val state = _uiState.value
        if (state.path.size <= 1) return
        _uiState.update { it.copy(path = state.path.dropLast(1)) }
        load(_uiState.value.currentFid)
    }

    private fun downloadFile(file: DriveFile) {
        val state = _uiState.value
        if (state.downloading != null) return
        _uiState.update { it.copy(downloading = file) }
        viewModelScope.launch {
            try {
                val url = driveRepository.getDownloadUrl(file.fid)
                downloadRepository.enqueue(
                    DownloadTask(
                        id = UUID.randomUUID().toString(),
                        url = url,
                        fileName = file.name,
                        mimeType = guessMime(file.name),
                        totalBytes = file.size,
                    )
                )
                _uiState.update {
                    it.copy(downloading = null, snackbar = "已开始下载「${file.name}」——到下载页查看进度")
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(downloading = null, snackbar = "获取直链失败：${e.message?.take(60)}")
                }
            }
        }
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

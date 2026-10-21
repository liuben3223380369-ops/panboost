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
 * 首屏 ViewModel（第 4 周链路核心：浏览 → 下载）。
 *
 * - OpenDir：push 面包屑 + 拉子目录列表（整列替换）
 * - DownloadFile：取直链（QuarkDriveRepository）→ enqueue 真实
 *   下载任务（UrlDownloadWorker，OkHttp 流式）→ snackbar 引导
 *   去下载屏；失败（Cookie 过期等）snackbar 展示错误
 * - 防连点：downloading 标记在途时忽略再次点击
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
            is HomeIntent.DownloadFile ->downloadFile(intent.file)
            HomeIntent.SnackbarShown -> _uiState.update {
                it.copy(snackbar = null)
            }
        }
    }

    private fun load(fid: String) {
        _uiState.update { it.copy(loading = true) }
        viewModelScope.launch {
            try {
                val files = driveRepository.listFiles(fid)
                _uiState.update { it.copy(loading = false, files = files) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(loading = false, snackbar = "加载失败：${e.message?.take(60)}")
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
